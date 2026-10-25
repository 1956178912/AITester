#!/usr/bin/env python3
"""Q11 论文数字-SRC 一致性审计工具（`scripts/tools/audit_paper_numbers.py`）的回归锁定。

覆盖：
1. **paper 缺失 → CI 安全**（工具 exit 0，paper_present=false）；
2. 数字声明识别（百分比 / p 值 / 样本量 / 货币 / 比例 / DOI / 计数）；
3. SRC 窗口覆盖计算（covered / citation-covered / uncovered 三分类）；
4. 段落级引文覆盖（引用在段首时，段内数字共享来源）；
5. SRC 引用有效性（仓库路径 / ADR 编号 / BASELINE 键；无效 → failure）；
6. 引文卫生（缺 key、缺 DOI/arXiv 且无 TODO → failure；带 TODO → pending 不 fail；
   重复 DOI、未引用条目）；
7. TODO 清单与 Markdown 渲染；
8. `--strict` 退出码（引用无效 / 覆盖率不达标 → 1）。

测试使用 tmp_path 微型论文夹具，不依赖真实 paper/（paper/ 按 .gitignore 排除）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "audit_paper_numbers.py"
_spec = importlib.util.spec_from_file_location("_audit_paper_numbers", _SCRIPT)
assert _spec and _spec.loader
audit_mod = importlib.util.module_from_spec(_spec)
sys.modules["_audit_paper_numbers"] = audit_mod
_spec.loader.exec_module(audit_mod)

_DRAFT = """// TODO(submit): author block

= Introduction
Our pipeline detects 15.8% of tasks versus 44.8% for the prompt-only arm
($n=261$ pooled; exact $p=0.0001$). Costs are \\$0.0259 per task.
// SRC: experiments/results/main_batch/statistical_report_3seed_pooled.md;
//      BASELINE.yaml#benchmark.

= Results
External work reports 0.46% to 3.84% misleading tests (@zhao2026misguidance).
Another 40/60 split without any source.

= Threats
Unannotated claim: 50 programs and p < 1e-7 here.
"""

_BIB = """@article{zhao2026misguidance,
  title = {Misguidance},
  note = {DOI: 10.1145/3832204; arXiv:2607.22883}
}

@misc{aitester2026artifact,
  title = {Artifact},
  howpublished = {Zenodo}
  % TODO(ref): DOI 归档后回填
}
"""


def _make_paper(tmp_path: Path, draft: str = _DRAFT, bib: str = _BIB) -> Path:
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "draft.typ").write_text(draft, encoding="utf-8")
    (paper / "refs.bib").write_text(bib, encoding="utf-8")
    return paper


class TestPaperAbsent:
    def test_missing_paper_is_ci_safe(self, tmp_path):
        audit = audit_mod.build_audit(tmp_path / "missing", window=12)
        assert audit["paper_present"] is False
        assert audit["failures"] == []
        assert "跳过" in audit["note"]

    def test_main_exits_zero_when_paper_missing(self, tmp_path):
        rc = audit_mod.main(["--paper-dir", str(tmp_path / "missing")])
        assert rc == 0


class TestNumericDetection:
    def test_detects_percentage(self, tmp_path):
        claims = audit_mod.detect_numeric_claims(["we reach 44.8% detection"])
        assert claims and claims[0]["kind"] == "percentage"

    def test_detects_p_value(self, tmp_path):
        claims = audit_mod.detect_numeric_claims(["exact $p=0.0001$ here"])
        assert any(c["kind"] == "p_value" for c in claims)

    def test_detects_sample_size(self, tmp_path):
        claims = audit_mod.detect_numeric_claims(["pooled $n=261$ tasks"])
        assert any(c["kind"] == "sample_size" for c in claims)

    def test_detects_ratio_and_count(self):
        assert audit_mod.detect_numeric_claims(["19/35 measurable"])[0]["kind"] == "ratio"
        assert audit_mod.detect_numeric_claims(["50 programs in total"])[0]["kind"] == "count"

    def test_typst_math_times_not_currency(self):
        """`2$times$2` 的数学模式不得被误判为货币声明。"""
        claims = audit_mod.detect_numeric_claims([f"a 2{chr(36)}times{chr(36)}2 design"])
        assert all(c["kind"] != "currency" for c in claims)

    def test_comment_and_src_lines_ignored(self):
        claims = audit_mod.detect_numeric_claims(["// SRC: 50 programs", "// 44.8% comment"])
        assert claims == []


class TestCoverage:
    def test_src_window_coverage(self):
        lines = ["we see 44.8% here", "filler", "// SRC: artifacts/a.md"]
        claims = audit_mod.detect_numeric_claims(lines)
        cov = audit_mod.compute_coverage(claims, [2], window=5, draft_lines=lines)
        assert cov["covered_src_claims"] == 1
        assert cov["uncovered"] == []

    def test_window_excludes_far_claims(self):
        lines = ["44.8% claim"] + ["filler"] * 20 + ["// SRC: artifacts/a.md"]
        claims = audit_mod.detect_numeric_claims(lines)
        cov = audit_mod.compute_coverage(claims, [21], window=5, draft_lines=lines)
        assert cov["covered_src_claims"] == 0
        assert len(cov["uncovered"]) == 1

    def test_paragraph_citation_coverage(self):
        lines = [
            "Zhao et al. (@zhao2026misguidance) report:",
            "misguided tests rise from 0.46% to 3.84%;",
            "effective tests fall from 8.51% to 2.98%.",
        ]
        claims = audit_mod.detect_numeric_claims(lines)
        cov = audit_mod.compute_coverage(claims, [], window=5, draft_lines=lines)
        assert cov["covered_citation_claims"] == len(claims)
        assert cov["traceable_ratio"] == pytest.approx(1.0)

    def test_citation_does_not_leak_across_paragraphs(self):
        lines = ["Stats 44.8% here.", "", "Unrelated paragraph (@zhao2026misguidance)."]
        claims = audit_mod.detect_numeric_claims(lines)
        cov = audit_mod.compute_coverage(claims, [], window=1, draft_lines=lines)
        assert cov["covered_citation_claims"] == 0
        assert len(cov["uncovered"]) == 1


class TestSrcValidation:
    def test_invalid_repo_path_is_failure(self, tmp_path):
        tokens = [(3, "experiments/results/does_not_exist_xyz/")]
        details, failures = audit_mod.validate_src_tokens(tokens, tmp_path)
        assert any("不存在" in f for f in failures)
        assert details[0]["kind"] == "path"

    def test_existing_path_ok(self, tmp_path):
        (tmp_path / "artifacts").mkdir()
        (tmp_path / "artifacts" / "report.md").write_text("x", encoding="utf-8")
        _, failures = audit_mod.validate_src_tokens([(1, "artifacts/report.md")], tmp_path)
        assert failures == []

    def test_experiments_results_relative_fallback(self, tmp_path):
        target = tmp_path / "experiments" / "results" / "emse_demo_20261017"
        target.mkdir(parents=True)
        _, failures = audit_mod.validate_src_tokens([(1, "emse_demo_20261017/")], tmp_path)
        assert failures == []

    def test_adr_validation(self, tmp_path):
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "0021-repair-zero-measurement-artifact.md").write_text("x", encoding="utf-8")
        _, ok = audit_mod.validate_src_tokens([(1, "ADR-0021")], tmp_path)
        assert ok == []
        _, bad = audit_mod.validate_src_tokens([(1, "ADR-9999")], tmp_path)
        assert any("ADR" in f for f in bad)

    def test_baseline_key_validation(self, tmp_path):
        (tmp_path / "BASELINE.yaml").write_text("benchmark:\n  detection: 0.448\n", encoding="utf-8")
        good = [(1, "BASELINE.yaml#benchmark.detection")]
        bad = [(2, "BASELINE.yaml#benchmark.missing")]
        _, ok_failures = audit_mod.validate_src_tokens(good, tmp_path)
        _, bad_failures = audit_mod.validate_src_tokens(bad, tmp_path)
        assert ok_failures == []
        assert any("键不存在" in f for f in bad_failures)

    def test_prose_tokens_ignored(self, tmp_path):
        details, failures = audit_mod.validate_src_tokens([(1, "artifact"), (1, "documents.")], tmp_path)
        assert failures == []
        assert all(d["kind"] == "prose" for d in details)


class TestBibAudit:
    def test_missing_cited_key_is_failure(self, tmp_path):
        result = audit_mod.audit_bib(_make_paper(tmp_path) / "refs.bib", "See @missing_key_2026 for details.")
        assert "missing_key_2026" in result["missing_keys"]
        assert any("不在 refs.bib" in f for f in result["failures"])

    def test_entry_without_identifier_and_without_todo_is_failure(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{k, title={T}, year={2026}}\n", encoding="utf-8")
        result = audit_mod.audit_bib(bib, "Cite @k.")
        assert any("缺少 DOI/arXiv" in f for f in result["failures"])

    def test_entry_with_todo_is_pending_not_failure(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@misc{k, title={T}}\n% TODO(ref): 补 DOI\n", encoding="utf-8")
        result = audit_mod.audit_bib(bib, "Cite @k.")
        assert result["failures"] == []
        assert any("TODO" in w for w in result.get("warnings", []))

    def test_duplicate_doi_detected(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{a, note={DOI: 10.1145/1}}\n@article{b, note={DOI: 10.1145/1}}\n", encoding="utf-8")
        result = audit_mod.audit_bib(bib, "Cite @a and @b.")
        assert result["duplicate_dois"]

    def test_unused_entry_listed(self, tmp_path):
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{unused, note={DOI: 10.1145/2}}\n", encoding="utf-8")
        result = audit_mod.audit_bib(bib, "No citation here.")
        assert result["unused_entries"] == ["unused"]


class TestEndToEnd:
    def test_build_audit_counts_and_sections(self, tmp_path, monkeypatch):
        paper = _make_paper(tmp_path)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert audit["paper_present"] is True
        assert audit["coverage"]["total_claims"] >= 2
        assert audit["src_count"] == 1
        assert [s["title"] for s in audit["sections"]] == ["Introduction", "Results", "Threats"]

    def test_markdown_render_contains_sections(self, tmp_path, monkeypatch):
        paper = _make_paper(tmp_path)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        md = audit_mod.render_markdown(audit_mod.build_audit(paper, window=5))
        for heading in ("## 1. 数字声明覆盖率（块级近似）", "## 2. SRC 引用有效性", "## 3. 引文卫生", "## 4. TODO"):
            assert heading in md

    def test_todos_listed(self, tmp_path, monkeypatch):
        paper = _make_paper(tmp_path)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        files = {t["file"] for t in audit["todos"]}
        assert "draft.typ" in files

    def test_json_and_md_outputs(self, tmp_path, monkeypatch):
        paper = _make_paper(tmp_path)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        out_json = tmp_path / "audit.json"
        out_md = tmp_path / "audit.md"
        rc = audit_mod.main(["--paper-dir", str(paper), "--window", "5", "--json", str(out_json), "--md", str(out_md)])
        assert rc == 0
        assert json.loads(out_json.read_text(encoding="utf-8"))["paper_present"] is True
        assert "数字声明覆盖率" in out_md.read_text(encoding="utf-8")

    def test_strict_fails_on_invalid_src_and_low_coverage(self, tmp_path, monkeypatch):
        draft = "= Introduction\nNumbers 44.8% with no source at all.\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        rc = audit_mod.main(["--paper-dir", str(paper), "--window", "2", "--strict", "--min-coverage", "0.9"])
        assert rc == 1

    def test_strict_passes_for_fully_traceable_paper(self, tmp_path, monkeypatch):
        paper = _make_paper(tmp_path)
        # 夹具 SRC 引用的工件在 PROJECT_ROOT（monkeypatch 到 tmp_path）下必须存在
        artifact = tmp_path / "experiments" / "results" / "main_batch" / "statistical_report_3seed_pooled.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("report", encoding="utf-8")
        (tmp_path / "BASELINE.yaml").write_text("benchmark:\n  detection: 0.448\n", encoding="utf-8")
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        rc = audit_mod.main(["--paper-dir", str(paper), "--window", "5", "--strict", "--min-coverage", "0.5"])
        assert rc == 0


class TestCjkUnrenderable:
    """CR 轮（2026-10-25）：可排版文本里不得有 CJK。

    实测事故：本轮编译论文时 tectonic 报
    `could not represent character "档" (0x6863) in font "ec-lmr10"`，而**编译退出码
    是 0**——`refs.bib` 两个条目把中文写进了 `note`，note 进 .bbl 被原样排版，
    Latin Modern 没有中文字形 ⇒ PDF 参考文献处出现缺字符。判据由此从「看编译
    警告」升级为「可执行检查」。
    """

    def test_bib_field_with_cjk_fails(self, tmp_path):
        bib = """@misc{broken2026,
  title = {A Paper},
  note  = {DOI 归档后回填（2026-10-25 检索）}
}
"""
        paper = _make_paper(tmp_path, bib=bib)
        result = audit_mod.audit_bib(paper / "refs.bib", "")
        assert any("中文字符" in failure for failure in result["failures"]), result["failures"]
        assert result["cjk_entries"] and result["cjk_entries"][0]["key"] == "broken2026"

    def test_bib_comment_line_with_cjk_is_allowed(self, tmp_path):
        """bib 里的 `%` 行是注释，不进 .bbl ⇒ 不该被判红。"""
        bib = """% 这条注释是中文，但它不排版
@misc{fine2026,
  title = {A Paper},
  note  = {arXiv:2601.09695}
}
"""
        paper = _make_paper(tmp_path, bib=bib)
        result = audit_mod.audit_bib(paper / "refs.bib", "")
        assert not any("中文字符" in failure for failure in result["failures"]), result["failures"]

    def test_draft_line_with_cjk_fails(self, tmp_path, monkeypatch):
        draft = "= Introduction\n我们的流水线检出 44.8% 的任务。\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_draft_comment_with_cjk_is_allowed(self, tmp_path, monkeypatch):
        """稿件里的 `%` 之后是注释，不排版 ⇒ 不该被判红。"""
        draft = "= Introduction\n% 这一行是中文注释\nWe detect 44.8% of tasks.\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert not any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_escaped_percent_is_not_a_comment_start(self, tmp_path):
        """`\\%` 是转义百分号，不开启注释 ⇒ 其后的中文仍算正文（会被排版）。"""
        assert audit_mod._strip_comment(r"we cover 100\% 覆盖率") == r"we cover 100\% 覆盖率"
        assert audit_mod._strip_comment(r"we cover 100% 覆盖率") == "we cover 100"

    def test_pmlr_publisher_counts_as_identifier(self, tmp_path):
        """PMLR 不分配 DOI（CR 轮一手核验）：publisher={PMLR} 是正当标识。"""
        bib = """@inproceedings{liu26ct,
  title     = {TestExplora},
  publisher = {PMLR},
  note      = {PMLR v306; the PMLR record lists no DOI}
}
"""
        paper = _make_paper(tmp_path, bib=bib)
        result = audit_mod.audit_bib(paper / "refs.bib", "")
        assert "liu26ct" not in result["entries_without_identifier"], result["entries_without_identifier"]
        assert not any("缺少 DOI/arXiv" in failure for failure in result["failures"]), result["failures"]


class TestSubmissionPackageCoherence:
    """CS 轮（2026-10-26）：投稿包自洽——`paper/SUBMISSION.md` 是投稿前最后一道
    人工清单，它自己必须与稿件/投稿材料一致。

    CS 轮实测：该表已与工件脱节四处（页数写 54 实测 55/57、表数写 22 实测 19、
    TODO 数写 14 实测 18、refs.bib 标识口径漏 `publisher={PMLR}`），而它**没有任何
    机制能发现自己过期**——审稿人看到的正是这张表。
    """

    @staticmethod
    def _make_pkg(tmp_path, pages=55, tables=19, todos=18, draft_tables=19, cover_todos=5, title_todos=13):
        paper = tmp_path / "paper"
        (paper / "tex").mkdir(parents=True)
        body = "\n".join(r"\begin{table}" for _ in range(draft_tables))
        (paper / "tex" / "manuscript.tex").write_text(body, encoding="utf-8")
        (paper / "tex" / "manuscript.log").write_text(
            f"Output written on manuscript.xdv ({pages} pages, 200 bytes).\n", encoding="utf-8"
        )
        (paper / "cover_letter.tex").write_text("TODO x\n" * cover_todos, encoding="utf-8")
        (paper / "title_page.tex").write_text("TODO y\n" * title_todos, encoding="utf-8")
        (paper / "SUBMISSION.md").write_text(
            "| `tex/manuscript.tex` | `tex/manuscript.pdf` | "
            f"{pages}（含附录） |\n"
            f"| 表格 | 稿件 {tables} 张表全部编号 |\n"
            f"- 共 {todos} 处待填标记\n",
            encoding="utf-8",
        )
        return paper

    def test_consistent_package_passes(self, tmp_path):
        paper = self._make_pkg(tmp_path)
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert result["failures"] == [], result["failures"]
        assert result["claims"]["tables"] == {"claimed": 19, "measured": 19}
        assert result["claims"]["todo_marks"] == {"claimed": 18, "measured": 18}

    def test_table_count_drift_fails(self, tmp_path):
        """表数声明与稿件实测不符 ⇒ 红。"""
        paper = self._make_pkg(tmp_path, draft_tables=3)
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("tables" in f for f in result["failures"]), result["failures"]

    def test_todo_count_drift_fails(self, tmp_path):
        """TODO 数声明与投稿材料实测不符 ⇒ 红。"""
        paper = self._make_pkg(tmp_path, cover_todos=3)
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("todo_marks" in f for f in result["failures"]), result["failures"]

    def test_page_count_drift_fails(self, tmp_path):
        """页数声明与 xdv 日志不符 ⇒ 红。"""
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.log").write_text(
            "Output written on manuscript.xdv (61 pages).\n", encoding="utf-8"
        )
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("pages" in f for f in result["failures"]), result["failures"]

    def test_missing_log_skips_page_claim(self, tmp_path):
        """构建产物不在场 ⇒ 页数判据跳过并披露，不判红。"""
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.log").unlink()
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert not any("pages" in f for f in result["failures"]), result["failures"]
        assert any("manuscript.log" in note for note in result["notes"]), result["notes"]

    def test_missing_submission_file_skips_whole_surface(self, tmp_path):
        """投稿包不在场 ⇒ 整个判定面跳过（不是红）。"""
        paper = self._make_pkg(tmp_path)
        (paper / "SUBMISSION.md").unlink()
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert result["present"] is False
        assert result["failures"] == []

    def test_abstract_word_count_is_measured_not_asserted(self, tmp_path):
        """摘要词数必须由源文件实测（口径显式：去 `%` 注释行、连字符复合词）。"""
        draft = (
            "\\begin{abstract}\n"
            "% SRC: docs/study/EXTERNAL_READINGS_2026-10-25.md; experiments/results/x.json\n"
            "We study one detection-first artifact with three seeds.\n"
            "\\end{abstract}\n"
        )
        normal, strict = audit_mod.abstract_word_counts(draft)
        # 注释行不得计入（否则路径与文件名被当正文）
        assert normal == 8, normal
        assert strict == 9, strict  # detection-first 拆成 2 词

    def test_abstract_over_limit_fails(self, tmp_path):
        """摘要超过期刊上限 ⇒ 红。"""
        long_body = " ".join(["word"] * 260)
        draft = f"\\begin{{abstract}}\n{long_body}\n\\end{{abstract}}\n"
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.tex").write_text(draft, encoding="utf-8")
        result = audit_mod.audit_submission_package(paper, draft)
        assert any("超过期刊上限" in f for f in result["failures"]), result["failures"]

    def test_abstract_margin_is_disclosed(self, tmp_path):
        """余量不足 5 词 ⇒ 披露（不阻断，但必须写进 notes）。"""
        body = " ".join(["word"] * 247)
        draft = f"\\begin{{abstract}}\n{body}\n\\end{{abstract}}\n"
        paper = self._make_pkg(tmp_path)
        result = audit_mod.audit_submission_package(paper, draft)
        assert not any("超过期刊上限" in f for f in result["failures"]), result["failures"]
        assert any("只剩" in note for note in result["notes"]), result["notes"]

    def test_title_page_claims_are_checked(self, tmp_path):
        """title page 的摘要词数 / 页数声明必须与实测一致。"""
        paper = self._make_pkg(tmp_path)
        (paper / "title_page.tex").write_text(
            "\\item Abstract: 999 words (journal limit: 150--250)\n"
            "\\item Manuscript body: 54 pages including appendices\n",
            encoding="utf-8",
        )
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("title_page_abstract_words" in f for f in result["failures"]), result["failures"]
        assert any("title_page_pages" in f for f in result["failures"]), result["failures"]

    def test_submission_abstract_words_checked(self, tmp_path):
        """投稿包说明里的摘要词数声明必须与实测一致。"""
        paper = self._make_pkg(tmp_path)
        text = (paper / "SUBMISSION.md").read_text(encoding="utf-8")
        text = text.replace("- 共 18 处待填标记", "- 稿件 777 词\n- 共 18 处待填标记")
        (paper / "SUBMISSION.md").write_text(text, encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("submission_abstract_words" in f for f in result["failures"]), result["failures"]

    def test_latex_citation_key_missing_from_bib_fails(self, tmp_path):
        r"""LaTeX 稿件的 `\citet{key}` 若不在 refs.bib ⇒ 必须报「引用无效」。

        CW 轮实测的判据缺口：审计器过去只从**Typst 风格**的 `@key` 取引用键，
        LaTeX 的 `\cite{key}` 从未参与 bib 存在性检查 ⇒ 正文一次引入 8 个尚不存在
        的新键，审计器一声不吭（该轮正文已渲染成 `?`）。
        """
        paper = _make_paper(tmp_path)
        (paper / "refs.bib").write_text(
            "@misc{known2026,\n  title = {Known},\n  note = {arXiv:2601.00001v1}\n}\n", encoding="utf-8"
        )
        draft = "We follow \\citet{known2026} and \\citet{ghost2026}.\n"
        (paper / "draft.typ").write_text(draft, encoding="utf-8")
        result = audit_mod.audit_bib(paper / "refs.bib", draft)
        assert "ghost2026" in result["missing_keys"], result["missing_keys"]
        assert "known2026" not in result["missing_keys"], result["missing_keys"]
        assert any("ghost2026" in f for f in result["failures"]), result["failures"]

    def test_latex_citation_key_present_in_bib_passes(self, tmp_path):
        r"""LaTeX 稿件的 `\citet{key}` 在 refs.bib 中 ⇒ 不报。"""
        paper = _make_paper(tmp_path)
        (paper / "refs.bib").write_text(
            "@misc{known2026,\n  title = {Known},\n  note = {arXiv:2601.00001v1}\n}\n", encoding="utf-8"
        )
        draft = "We follow \\citet{known2026}.\n"
        result = audit_mod.audit_bib(paper / "refs.bib", draft)
        assert result["missing_keys"] == [], result["missing_keys"]

    def test_cover_letter_arxiv_must_be_in_bib_and_cited(self, tmp_path):
        """投稿信提到的 arXiv 号必须既在 refs.bib、又被正文引用。

        CV 轮：`paper/` 按双盲纪律不入库 ⇒ 改正文不会自动带动投稿信。上一轮手工
        同步过一次，下一轮必然漂——此判据把「投稿信引了正文没引的文献」变成红线。
        """
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "refs.bib").write_text(
            "@misc{alpha2026,\n  title = {A},\n  note = {arXiv:2601.00001v1}\n}\n", encoding="utf-8"
        )
        (paper / "tex" / "manuscript.tex").write_text(
            "\\begin{abstract}\nword word word word word word word word\n\\end{abstract}\n"
            "We follow \\citet{alpha2026}.\n",
            encoding="utf-8",
        )
        (paper / "cover_letter.tex").write_text("See arXiv:2601.00001 for context.\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert not [f for f in result["failures"] if "arXiv" in f], result["failures"]

    def test_cover_letter_arxiv_absent_from_bib_fails(self, tmp_path):
        """投稿信提到 refs.bib 里没有的 arXiv ⇒ 红。"""
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "refs.bib").write_text(
            "@misc{alpha2026,\n  note = {arXiv:2601.00001v1}\n}\n", encoding="utf-8"
        )
        (paper / "tex" / "manuscript.tex").write_text(
            "\\begin{abstract}\nword word word word word word word word word\n\\end{abstract}\n"
            "We follow \\citet{alpha2026}.\n",
            encoding="utf-8",
        )
        (paper / "cover_letter.tex").write_text("See arXiv:2699.99999 for context.\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("2699.99999" in f for f in result["failures"]), result["failures"]

    def test_cover_letter_arxiv_not_cited_in_body_fails(self, tmp_path):
        """投稿信提到、正文却没引的文献 ⇒ 红。"""
        paper = self._make_pkg(tmp_path)
        (paper / "tex" / "refs.bib").write_text(
            "@misc{alpha2026,\n  note = {arXiv:2601.00001v1}\n}\n", encoding="utf-8"
        )
        (paper / "tex" / "manuscript.tex").write_text(
            "\\begin{abstract}\nword word word word word word word word word\n\\end{abstract}\nWe follow nobody.\n",
            encoding="utf-8",
        )
        (paper / "cover_letter.tex").write_text("See arXiv:2601.00001 for context.\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("正文没有引用" in f for f in result["failures"]), result["failures"]

    def test_real_cover_letter_arxiv_are_all_cited(self):
        """真树：投稿信提到的每个 arXiv 号都必须在 refs.bib 且被正文引用。"""
        paper = Path(__file__).resolve().parents[1] / "paper"
        draft = paper / "tex" / "manuscript.tex"
        if not (paper / "cover_letter.tex").exists() or not draft.exists():
            pytest.skip("paper/ 不入库（.gitignore 双盲纪律）——真树校验仅在本地稿件在场时执行")
        result = audit_mod.audit_submission_package(paper, draft.read_text(encoding="utf-8"))
        surface = result.get("cover_letter_arxiv")
        assert surface, "投稿信里应有 arXiv 号（若为 0 则本判据面未被触发，需重新设计）"
        assert all(surface["cited"].values()), surface
        assert all(key for key in surface["in_bib"].values()), surface

    def test_conflicting_claims_fail(self, tmp_path):
        """同一项出现两个不同声明 ⇒ 红（登记面自相矛盾）。"""
        paper = self._make_pkg(tmp_path)
        text = (paper / "SUBMISSION.md").read_text(encoding="utf-8")
        (paper / "SUBMISSION.md").write_text(text + "| 稿件 22 张表 |\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert any("多个不同值" in f for f in result["failures"]), result["failures"]
