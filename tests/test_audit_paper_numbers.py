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
