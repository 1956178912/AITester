#!/usr/bin/env python3
"""报告→工件对账门禁（`scripts/gates/check_artifact_doc_consistency.py`）的回归锁定。

锁定三件事（对应本轮 EMSE 审计发现的三类真实缺陷）：

1. **解析不静默丢行/丢列**：`plain_llm` / `plain_llm_df` 这类含下划线的臂名、
   `mean(MS\\|det=1)` 这类转义竖线列头、`Δ均值` 这类会被 `.lower()` 折叠为
   `δ均值` 的列头——都必须被正确识别（本项目三处解析陷阱各对应一次真实故障）；
2. **对账真的会失败**：人为把文档数值/结论标签改错，门禁必须报错（防"永远绿"）；
3. **再生成优先**：源批次在场时以生成器输出为工件（CI 场景，派生物不入库），
   且从任意 CWD 调用结果一致。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import ClassVar

import pytest

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_artifact_doc_consistency.py"
_spec = importlib.util.spec_from_file_location("_artifact_doc_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_artifact_doc_gate"] = gate
_spec.loader.exec_module(gate)

_ARTIFACT = gate.DEFAULT_ARTIFACT
_DOC = gate.DEFAULT_DOCS[0]
_MAIN_BATCH = Path("experiments/results/main_batch")
_HAS_ARTIFACT = _ARTIFACT.is_file()
_HAS_BATCH = bool(sorted(_MAIN_BATCH.glob("benchmark_synthetic_*.json")))


class TestParsingTraps:
    def test_arm_names_with_underscore_are_not_dropped(self):
        assert _HAS_ARTIFACT, "盘上派生物缺席（应由 make mutation-det-correlation 生成）"
        table = gate._parse_markdown_table(_ARTIFACT.read_text(encoding="utf-8"))
        assert sorted(table) == ["aitester", "plain_llm", "plain_llm_df"], sorted(table)

    def test_escaped_pipe_header_keeps_column_count(self):
        """`mean(MS\\|det=1)` 的转义竖线若被当分隔符，行会错位成 12 列。"""
        line = "| aitester | 10 | 556 | 605 | 13.06% | 0.9968 | 0.8705 | 0.1263 | 0.1805 | 0.1892 | 可鉴别 |"
        assert len(gate._split_row(line)) == 11
        header = "| 臂 | 批次文件数 | 配对 n | detection 可测 n | detection 率 | mean(MS\\|det=1) | mean(MS\\|det=0) | Δ均值 | Pearson | Spearman | 饱和判定 |"
        assert len(gate._split_row(header)) == 11

    def test_delta_column_survives_lowercase_folding(self):
        """`.lower()` 把 `Δ`(U+0394) 折叠为 `δ`(U+03B4)——两形态都必须映射。"""
        assert gate._COLUMNS.get(gate._norm("Δ均值")) == "mean_delta"
        assert gate._COLUMNS.get(gate._norm("δ均值")) == "mean_delta"

    @pytest.mark.skipif(not _HAS_ARTIFACT, reason="派生物缺席")
    def test_all_columns_mapped_for_every_arm(self):
        table = gate._parse_markdown_table(_ARTIFACT.read_text(encoding="utf-8"))
        for arm, row in table.items():
            missing = [c for c in gate._COLUMNS.values() if c not in row]
            assert not missing, (arm, missing)


class TestComparisonActuallyFails:
    _DOC_TABLE = (
        "| 臂 | 批次文件数 | 配对 n | detection 可测 n | detection 率 | mean(MS\\|det=1) | "
        "mean(MS\\|det=0) | Δ均值 | Pearson | Spearman | 饱和判定 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
        "{rows}\n"
    )
    _ROW = "| {arm} | 10 | {pairs} | 600 | {rate}% | 0.99 | 0.87 | {delta} | {pearson} | 0.10 | {sat} |"

    def _doc_table(self, rows: list[str]) -> str:
        return self._DOC_TABLE.format(rows="\n".join(rows))

    def test_identical_tables_pass(self):
        # 三臂齐全（缺臂会被门禁判为失败——这是设计意图，见下一条用例）。
        artifact = {arm: dict.fromkeys(gate._COLUMNS.values(), "1") for arm in gate.ARMS}
        doc = {arm: dict(row) for arm, row in artifact.items()}
        assert gate.compare_tables(artifact, doc) == []

    def test_numeric_drift_fails(self):
        artifact = {arm: dict.fromkeys(gate._COLUMNS.values(), "0.1805") for arm in gate.ARMS}
        for row in artifact.values():
            row["saturation"] = "可鉴别"
        doc = {arm: dict(row) for arm, row in artifact.items()}
        doc["aitester"]["pearson"] = "-0.0562"
        problems = gate.compare_tables(artifact, doc)
        assert [p.column for p in problems] == ["pearson"]
        assert problems[0].arm == "aitester"

    def test_conclusion_label_flip_fails(self):
        """本轮审计最典型的缺陷：同一事实两种结论（近饱和 ↔ 无鉴别力（饱和））。"""
        artifact = {arm: dict.fromkeys(gate._COLUMNS.values(), "1") for arm in gate.ARMS}
        for row in artifact.values():
            row["saturation"] = "**无鉴别力（饱和）**"
        doc = {arm: dict(row) for arm, row in artifact.items()}
        doc["aitester"]["saturation"] = "近饱和，谨慎解读"
        problems = gate.compare_tables(artifact, doc)
        assert any(p.column == "saturation" and p.arm == "aitester" for p in problems)

    def test_missing_arm_is_reported_not_skipped(self):
        artifact = {"aitester": dict.fromkeys(gate._COLUMNS.values(), "1")}
        problems = gate.compare_tables(artifact, artifact)
        assert len(problems) == 2  # plain_llm / plain_llm_df 缺失必须报错
        assert {p.arm for p in problems} == {"plain_llm", "plain_llm_df"}


@pytest.mark.skipif(not (_HAS_ARTIFACT or _HAS_BATCH), reason="既无源批次也无派生物")
class TestEndToEnd:
    def test_gate_passes_on_repo_state(self):
        assert gate.main([]) == 0

    def test_fallback_mode_passes(self):
        assert gate.main(["--no-regenerate"]) == 0

    def test_tampered_doc_fails(self, tmp_path: Path):
        tampered = tmp_path / "doc.md"
        text = _DOC.read_text(encoding="utf-8").replace("0.1805", "0.1999")
        assert text != _DOC.read_text(encoding="utf-8"), "锚点数值未找到——文档已变更，请更新锚点"
        tampered.write_text(text, encoding="utf-8")
        assert gate.main(["--doc", str(tampered)]) == 1

    @pytest.mark.skipif(not _HAS_BATCH, reason="源批次缺席（CI 精简环境）")
    def test_regeneration_is_used_when_source_batches_present(self):
        text = gate._regenerate_artifact_text()
        assert text is not None and "| 臂 |" in text
        table = gate._parse_markdown_table(text)
        assert sorted(table) == ["aitester", "plain_llm", "plain_llm_df"]
        # 再生成结果必须与盘上派生物逐单元格一致（否则说明派生物已过期）。
        if _HAS_ARTIFACT:
            on_disk = gate._parse_markdown_table(_ARTIFACT.read_text(encoding="utf-8"))
            assert table == on_disk


class TestT10DeclarationCheck:
    """T-10（通过率混淆）声明对账：严格口径必须显式声明。

    背景：T-10 匹配子集有两种口径——严格（pattern×seed，29 行 / 25 可测）与
    宽松（仅 pattern，62 行 / 55 可测）。文档若只引宽松值，读者无法判断口径；
    本门禁要求**严格口径的行数与可测数同时在场**。
    """

    _FACTS: ClassVar[dict[str, int]] = {
        "strict_rows": 29,
        "strict_measurable": 25,
        "loose_rows": 62,
        "loose_measurable": 55,
        "unmatched_rows": 199,
        "unmatched_detections": 38,
        "df_passed": 7,
    }

    @pytest.mark.skipif(not (_HAS_ARTIFACT or _HAS_BATCH), reason="既无源批次也无派生物")
    def test_recompute_returns_both_calibers(self):
        facts = gate._recompute_pass_matched_facts()
        assert facts is not None, "源批次在场却无法复算"
        assert facts["strict_rows"] > 0 and facts["strict_measurable"] > 0
        assert facts["strict_rows"] < facts["loose_rows"], "严格口径必须严于宽松口径"
        assert facts["df_passed"] == 7

    def test_check_reports_missing_strict_caliber(self, tmp_path, monkeypatch):
        """文档只写宽松口径（62 行）时必须报错——这正是本轮修掉的漂移形态。"""
        doc = tmp_path / "loose_only.md"
        doc.write_text("匹配子集 62 行 / 55 可测检出 0", encoding="utf-8")
        monkeypatch.setattr(gate, "_T10_ANCHOR_DOCS", (doc,))
        problems = gate.check_t10_docs(self._FACTS)
        assert len(problems) == 2, problems  # 缺行数 + 缺可测数
        assert any("严格口径" in p for p in problems)

    def test_check_passes_when_both_calibers_declared(self, tmp_path, monkeypatch):
        doc = tmp_path / "ok.md"
        doc.write_text("严格口径 29 行 / 25 可测；宽松口径 62 行 / 55 可测", encoding="utf-8")
        monkeypatch.setattr(gate, "_T10_ANCHOR_DOCS", (doc,))
        assert gate.check_t10_docs(self._FACTS) == []

    def test_check_reports_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "_T10_ANCHOR_DOCS", (tmp_path / "absent.md",))
        problems = gate.check_t10_docs(self._FACTS)
        assert len(problems) == 1 and "文件缺失" in problems[0]

    @pytest.mark.skipif(not (_HAS_ARTIFACT or _HAS_BATCH), reason="既无源批次也无派生物")
    def test_repo_docs_declare_strict_caliber(self):
        """仓库现状自检：VALIDITY / EVALUATION_SCOPE 必须已声明严格口径。"""
        facts = gate._recompute_pass_matched_facts()
        assert facts is not None
        assert gate.check_t10_docs(facts) == []


class TestRelDisplayNameAndRecomputeGuards:
    """门禁自身的健壮性分支（覆盖率收口：本轮扩展引入的新分支）。"""

    def test_rel_falls_back_to_absolute_path_outside_repo(self, tmp_path):
        """仓库外路径不得让 `relative_to` 抛错（显示名不能成为崩溃面）。"""
        outside = tmp_path / "x.md"
        assert gate._rel(outside) == str(outside)

    def test_rel_uses_relative_path_inside_repo(self):
        inside = gate._REPO_ROOT / "README.md"
        assert gate._rel(inside) == "README.md"

    def test_recompute_returns_none_when_batch_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)  # 无 experiments/… 目录
        assert gate._recompute_pass_matched_facts() is None

    def test_recompute_returns_none_when_no_seed_batches(self, tmp_path, monkeypatch):
        batch = tmp_path / "experiments" / "results" / "main_batch"
        batch.mkdir(parents=True)
        (batch / "benchmark_synthetic_20261006_140906.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
        # 文件名不匹配 `benchmark_synthetic_20261006_1*.json` → 无候选 → None
        assert gate._recompute_pass_matched_facts() is None


class TestStatusRegisterCoverageCheck:
    """状态登记册 §1 的覆盖率声明必须与 `coverage.xml` 实测相符（防文档自我美化）。

    G6（2026-10-16）：返回值扩成 ``(问题清单, 是否真正对过账)``——此前
    "coverage.xml 缺席"与"对账通过"都返回空清单，调用方一律打 `[OK]`，而 CI 里
    该步骤排在 coverage.xml 生成之前，于是这道对账常年假绿（从未真正运行）。
    同日修正对账口径：锚定 §1 声明行 + 容差（逐位相等不可满足：
    分支覆盖同源码连跑两次即抖 ±1 分支 = 0.016pp，`graph/nodes.py` 行覆盖
    同源码两次相差约 6 行 = 总行覆盖 0.035pp），声明行缺失按不通过处置。
    """

    def test_coverage_absent_skips_and_reports_not_checked(self, tmp_path, monkeypatch):
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("任何内容", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", tmp_path / "absent.xml")
        problems, checked = gate.check_status_register()
        assert problems == []
        assert checked is False, "缺席必须报“未对账”，不得被读作通过"

    def test_coverage_absent_fails_when_required(self, tmp_path, monkeypatch):
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("任何内容", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", tmp_path / "absent.xml")
        problems, checked = gate.check_status_register(require_coverage=True)
        assert checked is False
        assert len(problems) == 1 and "不得跳过" in problems[0], problems

    def test_register_missing_is_a_problem_not_a_skip(self, tmp_path, monkeypatch):
        """登记册入库、与 coverage 产物无关——缺席属仓库级问题，不得静默放行。"""
        monkeypatch.setattr(gate, "_STATUS_REGISTER", tmp_path / "absent.md")
        monkeypatch.setattr(gate, "_COVERAGE_XML", tmp_path / "absent.xml")
        problems, checked = gate.check_status_register()
        assert checked is False
        assert len(problems) == 1 and "文件缺失" in problems[0], problems

    def test_reports_stale_coverage_numbers(self, tmp_path, monkeypatch):
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9123" branch-rate="0.8456" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("| 总行覆盖 | **90.00%** |\n| 总分支覆盖 | **80.00%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is True
        assert len(problems) == 2, problems
        assert any("总行覆盖 90.00%" in p and "91.23%" in p for p in problems), problems
        assert any("总分支覆盖 80.00%" in p and "84.56%" in p for p in problems), problems

    def test_passes_when_numbers_match(self, tmp_path, monkeypatch):
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9280" branch-rate="0.8727" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("| 总行覆盖 | **92.80%** |\n| 总分支覆盖 | **87.27%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert (problems, checked) == ([], True)

    def test_measurement_jitter_within_tolerance_passes(self, tmp_path, monkeypatch):
        """分支覆盖逐次抖动 ±1 分支（0.016pp）属测量噪声，不得据此判文档说谎。

        实测依据（2026-10-16）：同一份源码连跑两次全量得 87.56% 与 87.54%。
        逐位相等口径不可满足，只会把常年假绿换成随机真红。
        """
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9293" branch-rate="0.8754" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("| 总行覆盖 | **92.96%** |\n| 总分支覆盖 | **87.56%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert (problems, checked) == ([], True)

    def test_tolerance_boundary_is_tight_but_absorbs_jitter(self, tmp_path, monkeypatch):
        """容差边界：吸收实测量级的抖动，但不放过任何超过噪声的错报。

        实测抖动量级（2026-10-16，同源码连跑）：分支 0.016pp、`graph/nodes.py`
        行覆盖约 6 行 → 总行覆盖 0.035pp；2026-10-18 首次真实 CI 实测**跨平台**
        分支差 0.13pp（ubuntu 92.66 vs macOS 92.79，同 Python 3.14）→ 容差校准为
        0.20pp（≈1.5× 跨平台差），仍不放过超过观测噪声的错报。
        """
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9290" branch-rate="0.8750" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        # 行 +0.09pp（抖动量级内 → 通过）；分支 +0.22pp（超出跨平台校准后的容差 → 转红）
        reg.write_text("| 总行覆盖 | **92.99%** |\n| 总分支覆盖 | **87.72%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is True
        assert len(problems) == 1, problems
        assert "总分支覆盖" in problems[0] and "+0.22pp" in problems[0], problems

    def test_declaration_beyond_tolerance_reports_both_sides(self, tmp_path, monkeypatch):
        """容差是双向的：文档**高报**（美化）与低报同样计为问题。"""
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9280" branch-rate="0.8727" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("| 总行覆盖 | **93.05%** |\n| 总分支覆盖 | **86.95%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is True
        assert len(problems) == 2, problems
        assert any("+0.25pp" in p for p in problems), problems
        assert any("-0.32pp" in p for p in problems), problems

    def test_number_elsewhere_in_doc_does_not_satisfy_reconciliation(self, tmp_path, monkeypatch):
        """旧口径漏判面：实测值出现在正文别处（如历史勘误）不算 §1 已声明。"""
        cov = tmp_path / "coverage.xml"
        cov.write_text(
            '<coverage line-rate="0.9280" branch-rate="0.8727" lines-valid="100" branches-valid="10"/>',
            encoding="utf-8",
        )
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("> 勘误：上一版曾写 92.80% 与 87.27%，均已过期。", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is True
        assert len(problems) == 2, problems
        assert all("未找到" in p for p in problems), problems

    def test_missing_coverage_xml_attribute_fails_closed(self, tmp_path, monkeypatch):
        """coverage.xml 缺 line-rate/branch-rate → 解析失败，不得计入已对账。"""
        cov = tmp_path / "coverage.xml"
        cov.write_text('<coverage lines-valid="100"/>', encoding="utf-8")
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("| 总行覆盖 | **92.80%** |\n| 总分支覆盖 | **87.27%** |", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is False
        assert len(problems) == 1 and "解析失败" in problems[0], problems

    def test_corrupt_coverage_xml_reports_problem(self, tmp_path, monkeypatch):
        cov = tmp_path / "coverage.xml"
        cov.write_text("<not-xml", encoding="utf-8")
        reg = tmp_path / "PROJECT_STATUS_REGISTER.md"
        reg.write_text("anything", encoding="utf-8")
        monkeypatch.setattr(gate, "_STATUS_REGISTER", reg)
        monkeypatch.setattr(gate, "_COVERAGE_XML", cov)
        problems, checked = gate.check_status_register()
        assert checked is False, "解析失败 = 没对上账，不得计入“已对账”"
        assert len(problems) == 1 and "解析失败" in problems[0]
