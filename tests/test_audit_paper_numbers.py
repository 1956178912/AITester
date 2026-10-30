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
import os
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "audit_paper_numbers.py"
_spec = importlib.util.spec_from_file_location("_audit_paper_numbers", _SCRIPT)
assert _spec and _spec.loader
audit_mod = importlib.util.module_from_spec(_spec)
sys.modules["_audit_paper_numbers"] = audit_mod
_spec.loader.exec_module(audit_mod)


def _write_build(base_dir: Path, stem: str, pages: int, inputs: tuple[str, ...] = ()) -> int:
    """写一份**PDF 口径**的成功构建产物（log + pdf），返回 PDF 字节数。

    为什么夹具必须用 PDF 口径：CX 轮实测发现，原判据读的是 tectonic 的 `.xdv`
    日志，而那一行「Output written on … (N pages」在 tectonic 日志里**根本不存在**
    ⇒ 判据永远走「跳过」分支 ⇒ 一次也没红过；场上的日志甚至是一份**失败构建**
    的残留。旧夹具把这条坏口径固化了下来，等于把缺陷锁进了测试。
    """
    payload = b"%PDF-1.7\n" + b"x" * (100 + pages)
    nbytes = len(payload)
    (base_dir / f"{stem}.pdf").write_bytes(payload)
    log = base_dir / f"{stem}.log"
    log.write_text(
        f"Output written on {stem}.pdf ({pages} pages, {nbytes} bytes).\n",
        encoding="utf-8",
    )
    newest = log.stat().st_mtime
    for name in inputs:
        src = base_dir / name
        if src.exists():
            newest = max(newest, src.stat().st_mtime)
    os.utime(log, (newest + 1, newest + 1))
    return nbytes


_DRAFT = """// TODO(submit): author block

= Introduction
[TODO(submit): fill corresponding author email]
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

    def test_email_address_is_not_a_citation_key(self, tmp_path):
        """邮箱里的 `@域名` 不得被当成引用键（2026-10-29：通讯邮箱落稿后
        `a1956178912@outlook.com` 被截成假键 @outlook，前置判据误红）。"""
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{k, note={DOI: 10.1145/1}}\n", encoding="utf-8")
        result = audit_mod.audit_bib(bib, "Corresponding: \\email{a1956178912@outlook.com}; see @k for details.")
        assert result["missing_keys"] == []
        assert result["failures"] == []

    def test_paragraph_citations_ignore_emails(self):
        """段落引文归属同样剥离邮箱：第一段只有邮箱 ⇒ 无引文键；第二段真键保留。"""
        blocks = audit_mod._paragraph_citations(
            ["Contact a1956178912@outlook.com for data.", "", "@zhao2026misguidance reports 44.8%."]
        )
        assert blocks[0] == set()
        assert "zhao2026misguidance" in blocks[1]

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

    def test_find_todos_uses_typst_comment_syntax(self, tmp_path, monkeypatch):
        """DE 轮（2026-10-26）：Typst 的行注释是 `//`，不是 `%`。

        DA 轮的实现一律剥 `%` ⇒ `// TODO` 被误列、`% TODO` 反被剥掉；旧测试
        还把 `% TODO` 当成 Typst 注释，通过但证明的是错误语言规则。
        """
        draft = (
            "= Introduction\n"
            "// TODO(ref): comment, not a placeholder\n"
            "[TODO(submit): real]\n"
            "% TODO(body): percent is not a typst comment\n"
        )
        bib = "@article{k, title={T}, note={DOI: 10.1145/1}}\n% TODO(ref): comment TODO in bib\n"
        paper = _make_paper(tmp_path, draft=draft, bib=bib)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert [(t["file"], t["line"]) for t in audit["todos"]] == [("draft.typ", 3), ("draft.typ", 4)]

    def test_find_todos_uses_tex_comment_syntax(self, tmp_path, monkeypatch):
        """TeX 的 `%` 是注释；`//` 不是（会原样排版，因此 `// TODO` 要列入）。"""
        draft = (
            "\\section{Introduction}\n"
            "% TODO(ref): comment, not a placeholder\n"
            "[TODO(submit): real]\n"
            "// TODO(slash): not a tex comment\n"
        )
        paper = tmp_path / "paper"
        (paper / "tex").mkdir(parents=True)
        (paper / "tex" / "manuscript.tex").write_text(draft, encoding="utf-8")
        (paper / "tex" / "refs.bib").write_text("@article{k, note={DOI: 10.1145/1}}\n", encoding="utf-8")
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert [(t["file"], t["line"]) for t in audit["todos"]] == [
            ("manuscript.tex", 3),
            ("manuscript.tex", 4),
        ]

    def test_typst_block_comment_todo_is_ignored(self, tmp_path, monkeypatch):
        """跨行块注释里的 TODO 不排版，不进清单。"""
        draft = "= Introduction\n/* TODO(ref): spans\n   two lines */\n[TODO(submit): real]\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert [(t["file"], t["line"]) for t in audit["todos"]] == [("draft.typ", 4)]

    def test_bib_percent_inside_field_is_literal(self):
        """BibTeX 字段值括号内的 `%` 是字面量：里面的 TODO 仍要列入。"""
        bib = "@misc{k,\n  note={100% TODO(fill)}\n}\n% TODO(comment): ignored\n"
        stripped = audit_mod._strip_comments(bib, ".bib")
        assert "TODO(fill)" in stripped
        assert "TODO(comment)" not in stripped

    def test_bib_escaped_quote_does_not_swallow_following_comments(self):
        """`{\\"a}` 是转义引号（LaTeX 变音符），不是字符串边界。

        DF 轮实测：`author = {Sch{\\"a}fer, ...}` 让剥注释器误入字符串态，
        后面紧随的 `% HITS（…）` 中文注释未被剥掉，被算成前一条目的字段值 ⇒
        `refs.bib` 被误判「字段值含中文」。转义引号不得切换字符串态。
        """
        bib = '@article{k,\n  author = {Sch{\\"a}fer, Max},\n  title = {T}\n}\n% 中文注释\n@misc{j, title={X}}\n'
        stripped = audit_mod._strip_comments(bib, ".bib")
        assert "中文注释" not in stripped
        assert 'Sch{\\"a}fer' in stripped
        assert audit_mod._cjk_hits_text(bib, ".bib") == []

    def test_typst_comment_lexer_protects_strings_raw_and_urls(self):
        """`//` 在字符串 / raw / URL 里不是注释；真正的行注释被剥掉。"""
        in_string = audit_mod._strip_typst_comments('"https://x" // trailing')
        assert in_string.startswith('"https://x"') and "trailing" not in in_string
        in_raw = audit_mod._strip_typst_comments("`// raw` // trailing")
        assert in_raw.startswith("`// raw`") and "trailing" not in in_raw
        in_url = audit_mod._strip_typst_comments("see https://example.com // trailing")
        assert in_url.startswith("see https://example.com") and "trailing" not in in_url
        assert "trailing" not in audit_mod._strip_typst_comments("// trailing\nbody")
        assert "b" not in audit_mod._strip_typst_comments("a /* b */ c").replace("a", "").replace("c", "")

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

    def test_pre_build_skips_stale_artifact_reconciliation(self, tmp_path, monkeypatch):
        """DG 轮：源文件改过、产物必然过期时，构建前档不得把「还没构建」判成失实。

        反例就是本判据自身：`build_paper.sh` 第一步跑 `audit --strict`，而
        `refs.bib` 一改，产物过期判据立刻红 ⇒ 脚本永远进不到编译步骤。
        """
        paper = _make_paper(tmp_path)
        tex = paper / "tex"
        tex.mkdir()
        source = tex / "manuscript.tex"
        source.write_text("body", encoding="utf-8")
        pdf = tex / "manuscript.pdf"
        pdf.write_bytes(b"x" * 1234)
        log = tex / "manuscript.log"
        log.write_text("Output written on manuscript.pdf (12 pages, 1234 bytes).\n", encoding="utf-8")
        os.utime(log, (1000, 1000))
        os.utime(pdf, (1000, 1000))
        os.utime(source, (2000, 2000))
        (paper / "SUBMISSION.md").write_text("| `manuscript.pdf` | 12 |\n", encoding="utf-8")
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)

        post = audit_mod.build_audit(paper, window=5)
        assert any("修改时间晚于" in f for f in post["failures"]), post["failures"]

        pre = audit_mod.build_audit(paper, window=5, pre_build=True)
        assert not any("修改时间晚于" in f for f in pre["failures"]), pre["failures"]
        assert any("构建前档" in note for note in pre["submission"]["notes"])

    def test_pre_build_still_blocks_source_defects(self, tmp_path, monkeypatch):
        """构建前档只免掉产物对账，**不放行源侧缺陷**（中文照样判红）。"""
        draft = "= Introduction\n这一段含中文，编译后 Latin Modern 无字形。\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        rc = audit_mod.main(
            ["--paper-dir", str(paper), "--window", "5", "--strict", "--pre-build", "--min-coverage", "0"]
        )
        assert rc == 1


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
        """Typst 的 `//` 之后是注释，不排版 ⇒ 不该被判红。"""
        draft = "= Introduction\n// 这一行是中文注释\nWe detect 44.8% of tasks.\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert not any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_typst_block_comment_with_cjk_is_allowed(self, tmp_path, monkeypatch):
        draft = "= Introduction\n/* 中文注释\n   跨行 */\nWe detect 44.8% of tasks.\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert not any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_typst_percent_is_not_a_comment(self, tmp_path, monkeypatch):
        """Typst 的 `%` 不是注释 ⇒ 其后的中文是正文，应判红。"""
        draft = "= Introduction\n% 中文不是 Typst 注释\n"
        paper = _make_paper(tmp_path, draft=draft)
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_tex_comment_with_cjk_is_allowed(self, tmp_path, monkeypatch):
        """TeX 的 `%` 之后是注释，不排版 ⇒ 不该被判红。"""
        draft = "\\section{Introduction}\n% 这一行是中文注释\nWe detect 44.8% of tasks.\n"
        paper = tmp_path / "paper"
        (paper / "tex").mkdir(parents=True)
        (paper / "tex" / "manuscript.tex").write_text(draft, encoding="utf-8")
        (paper / "tex" / "refs.bib").write_text("@article{k, note={DOI: 10.1145/1}}\n", encoding="utf-8")
        monkeypatch.setattr(audit_mod, "PROJECT_ROOT", tmp_path)
        audit = audit_mod.build_audit(paper, window=5)
        assert not any("中文字符" in failure for failure in audit["failures"]), audit["failures"]

    def test_escaped_percent_is_not_a_comment_start(self, tmp_path):
        """`\\%`（奇数反斜杠）是转义百分号；`\\\\%`（偶数）才是注释起点。"""
        assert audit_mod._strip_comment(r"we cover 100\% 覆盖率") == r"we cover 100\% 覆盖率"
        assert audit_mod._strip_comment(r"we cover 100% 覆盖率") == "we cover 100"
        assert audit_mod._strip_comment(r"a\\% b") == r"a\\"
        assert audit_mod._strip_comment(r"a\\\% b") == r"a\\\% b"

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

    DA 轮（2026-10-26）：TODO 数口径再修正——只数**会被排版**的 `[TODO(` 占位符
    （注释里的约定举例不计、按 token 不按行）。CS 轮把「18」按旧口径钉进 SUBMISSION.md
    时，其逐文件拆分（5 + 11 = 16 行）与 token 总数（18）本来就对不上；DA 轮实测
    真值 = 14（投稿信 4 + title page 10），声明面与三例新锁同轮对齐。
    """

    @staticmethod
    def _make_pkg(
        tmp_path,
        pages=62,
        tables=19,
        todos=18,
        draft_tables=19,
        cover_todos=5,
        title_todos=13,
        cover_pages=3,
        title_doc_pages=2,
    ):
        paper = tmp_path / "paper"
        (paper / "tex").mkdir(parents=True)
        body = "\n".join(r"\begin{table}" for _ in range(draft_tables))
        (paper / "tex" / "manuscript.tex").write_text(body, encoding="utf-8")
        _write_build(paper / "tex", "manuscript", pages, inputs=("manuscript.tex",))
        # DA 轮（2026-10-26）口径：`todo_marks` 只数会被排版的 `[TODO(` 占位符 token，
        # 夹具必须用真实占位符形态（裸 `TODO x` 在旧口径下能碰巧对账，但锁不住新判据）。
        (paper / "cover_letter.tex").write_text("[TODO(submit): x]\n" * cover_todos, encoding="utf-8")
        (paper / "title_page.tex").write_text("[TODO(confirm): y]\n" * title_todos, encoding="utf-8")
        _write_build(paper, "cover_letter", cover_pages, inputs=("cover_letter.tex",))
        _write_build(paper, "title_page", title_doc_pages, inputs=("title_page.tex",))
        (paper / "SUBMISSION.md").write_text(
            "| `tex/manuscript.tex` | `tex/manuscript.pdf` | "
            f"{pages}（含附录） |\n"
            f"| `cover_letter.tex` | `cover_letter.pdf` | {cover_pages} |\n"
            f"| `title_page.tex` | `title_page.pdf` | {title_doc_pages} |\n"
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

    def test_comment_todo_lines_not_counted(self, tmp_path):
        """DA 轮（2026-10-26）：约定注释里的 `[TODO(` 不计数——注释不进 PDF，作者
        无需（也不能）去填它。旧口径按整文件 token 计 ⇒ 会指示作者把约定说明一起删掉。"""
        paper = self._make_pkg(tmp_path)
        (paper / "cover_letter.tex").write_text(
            "% 纪律：待作者确认处一律写 [TODO(confirm): …] / [TODO(submit): …]，**不预填**。\n"
            + "[TODO(submit): x]\n" * 5,
            encoding="utf-8",
        )
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert result["claims"]["todo_marks"] == {"claimed": 18, "measured": 18}, result["claims"]

    def test_todo_marks_counts_tokens_per_line(self, tmp_path):
        """`todo_marks` 是 token 口径（`line.count("[TODO(")`）：同一行两个占位符计 2，
        与「行数」口径（CS 轮曾出现 16 ≠ 18 的两套数字互相对不上）显式区分。"""
        paper = self._make_pkg(tmp_path, cover_todos=0, title_todos=0)
        (paper / "cover_letter.tex").write_text(
            "[TODO(submit): a] and [TODO(submit): b] on one line\n", encoding="utf-8"
        )
        (paper / "SUBMISSION.md").write_text("- 共 2 处待填标记\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(
            paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8")
        )
        assert result["claims"]["todo_marks"] == {"claimed": 2, "measured": 2}, result["claims"]

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

    def test_bib_entry_count_claim_must_match_actual(self, tmp_path):
        """`refs.bib` N 条 的声明必须等于实测条目数（CX 轮新增）。

        动机：CW 轮给 refs.bib 加了十条后，投稿包对照表仍写「35 条」；CX 轮手改时
        先写成 46，而实测是 56 ⇒ **手写数字本身就是失实来源**，必须由机器对账。
        """
        paper = self._make_pkg(tmp_path)
        (paper / "refs.bib").write_text(
            "@misc{a2026,\n  title = {A}\n}\n@misc{b2026,\n  title = {B}\n}\n", encoding="utf-8"
        )
        (paper / "tex" / "refs.bib").write_text(
            "@misc{a2026,\n  title = {A}\n}\n@misc{b2026,\n  title = {B}\n}\n", encoding="utf-8"
        )
        (paper / "SUBMISSION.md").write_text("`refs.bib` 5 条：条目说明\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(paper, "\begin{abstract}word\\end{abstract}")
        assert any("bib_entries" in f for f in result["failures"]), result["failures"]
        (paper / "SUBMISSION.md").write_text("`refs.bib` 2 条：条目说明\n", encoding="utf-8")
        result = audit_mod.audit_submission_package(paper, "\begin{abstract}word\\end{abstract}")
        assert not [f for f in result["failures"] if "bib_entries" in f], result["failures"]

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


class TestSubmissionPageCountSource:
    """CX 轮（2026-10-26）：页数声明的**测量源**判据。

    CS 轮定的口径是「从 `tex/manuscript.log` 取 `Output written on … (N pages`；
    取不到 ⇒ 披露跳过，不判红」。CX 轮实测这道判据**一次也没红过**：
      - tectonic 的日志里根本没有那一行（它写的是 `.xdv`）⇒ 每次都走跳过分支；
      - 场上的日志恰是**失败构建**的残留（`Fatal error occurred, no output PDF
        file produced!`）⇒ 一个失败产物被当成「测量源在场」，把「缺测量」伪装
        成「无差异」；
      - 于是 SUBMISSION.md 里「55 页」从写下起**没有任何机制在核**，而真 LaTeX
        编译的实测值是 **62 页**。
    """

    @staticmethod
    def _audit(paper):
        return audit_mod.audit_submission_package(paper, (paper / "tex" / "manuscript.tex").read_text(encoding="utf-8"))

    def test_pdf_page_count_is_measured_from_build(self, tmp_path):
        """PDF 口径的构建日志 ⇒ 页数被实测并与声明对上。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path, pages=62)
        result = self._audit(paper)
        assert result["failures"] == [], result["failures"]
        assert result["claims"]["pages"] == {"claimed": 62, "measured": 62}

    def test_xdv_output_is_rejected(self, tmp_path):
        """日志写的是 `.xdv`（DVI 口径）⇒ 红：DVI 页数不是投稿 PDF 页数。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.log").write_text(
            "Output written on manuscript.xdv (55 pages, 200 bytes).\n", encoding="utf-8"
        )
        result = self._audit(paper)
        assert any("DVI/xdv 口径" in f for f in result["failures"]), result["failures"]

    def test_failed_build_log_is_rejected(self, tmp_path):
        """构建日志是失败构建 ⇒ 红（失败产物不得充当测量源）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.log").write_text(
            "! Emergency stop.\n!  ==> Fatal error occurred, no output PDF file produced!\n",
            encoding="utf-8",
        )
        result = self._audit(paper)
        assert any("失败构建" in f for f in result["failures"]), result["failures"]

    def test_log_without_output_line_is_rejected(self, tmp_path):
        """日志在场但没有 pdftex 的收尾行 ⇒ 红（不得静默跳过）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.log").write_text("nothing useful here\n", encoding="utf-8")
        result = self._audit(paper)
        assert any("页数声明无来源" in f for f in result["failures"]), result["failures"]

    def test_log_and_pdf_must_be_the_same_build(self, tmp_path):
        """日志字节数 ≠ PDF 实际字节数 ⇒ 红（日志与 PDF 不是同一次产物）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        (paper / "tex" / "manuscript.pdf").write_bytes(b"%PDF-1.7\nsomething else")
        result = self._audit(paper)
        assert any("不是同一次构建" in f for f in result["failures"]), result["failures"]

    def test_stale_build_is_rejected(self, tmp_path):
        """输入源比构建日志新 ⇒ 红（PDF 对应旧稿，页数声明是旧的）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        tex = paper / "tex" / "manuscript.tex"
        future = tex.stat().st_mtime + 3600
        os.utime(tex, (future, future))
        result = self._audit(paper)
        assert any("过期" in f for f in result["failures"]), result["failures"]

    def test_missing_build_is_disclosed_not_failed(self, tmp_path):
        """没有构建产物 ⇒ 只披露，不判红（无物可核 ≠ 声明失实）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path)
        for name in (
            "tex/manuscript.log",
            "tex/manuscript.pdf",
            "cover_letter.log",
            "cover_letter.pdf",
            "title_page.log",
            "title_page.pdf",
        ):
            (paper / name).unlink()
        result = self._audit(paper)
        assert result["failures"] == [], result["failures"]
        assert any("无物可核" in n for n in result["notes"]), result["notes"]

    def test_cover_letter_pages_claim_must_match(self, tmp_path):
        """投稿信页数声明与实测不符 ⇒ 红（CW 轮加段后已从 2 页变 3 页）。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path, cover_pages=3)
        text = (paper / "SUBMISSION.md").read_text(encoding="utf-8")
        (paper / "SUBMISSION.md").write_text(
            text.replace("| `cover_letter.pdf` | 3 |", "| `cover_letter.pdf` | 2 |"),
            encoding="utf-8",
        )
        result = self._audit(paper)
        assert any("cover_letter_pages" in f for f in result["failures"]), result["failures"]

    def test_title_page_doc_pages_claim_must_match(self, tmp_path):
        """title page 自身页数声明与实测不符 ⇒ 红。"""
        paper = TestSubmissionPackageCoherence._make_pkg(tmp_path, title_doc_pages=2)
        text = (paper / "SUBMISSION.md").read_text(encoding="utf-8")
        (paper / "SUBMISSION.md").write_text(
            text.replace("| `title_page.pdf` | 2 |", "| `title_page.pdf` | 5 |"),
            encoding="utf-8",
        )
        result = self._audit(paper)
        assert any("title_page_doc_pages" in f for f in result["failures"]), result["failures"]
