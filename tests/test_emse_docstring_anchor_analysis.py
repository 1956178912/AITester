#!/usr/bin/env python3
"""docstring 独立锚三臂分析脚本契约测试（零 LLM；纯函数纪律 + 端到端临时工件）。

锁定对象 `experiments/emse_docstring_anchor_analysis.py`：
- 预注册判定常量（65% 成功线 / 55% 失败线 / 0.05 confirm / 0.10 trend）与
  `PREREG_CONSTANTS` 单一事实源；
- 三态判定边界（confirmed / trend / not_confirmed + 失败线独立标记）；
- 对比方向与分母口径（41 缺陷程序口径、双方 detection 非 None 才配对）；
- 已知 McNemar 精确值与 MDE 复算；
- fail-closed（缺臂 / 行数或行集合异常 / 可判定配对为 0）；
- 三臂端到端（secondary 语义）+ JSON/Markdown 输出。

背景：脚本按"有入库测试锁定契约的 emse 脚本必须入库"纪律随本测试入库——否则
fresh clone 收集即 ImportError。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from experiments.emse_docstring_anchor_analysis import (
    CONFIRM_P,
    CONTROL_ARM,
    FAIL_LINE,
    MISGUIDED_DROP_TARGET,
    PREREG_CONSTANTS,
    PREREG_FILE,
    PRIMARY_ARM,
    PRIMARY_CONTRAST,
    SECONDARY_CONTRAST,
    SUCCESS_LINE,
    TREND_P,
    UNION_ARM,
    MissingArtifactError,
    build_analysis,
    decide,
    main,
    mechanism_declaration,
    render_markdown,
    validate_arm_rows,
)
from experiments.emse_quixbugs_specir_expand import mcnemar_exact_p, mde_two_proportion

# 41 缺陷程序口径 + 9 测试驱动任务（与 QuixBugs 50 任务同构）
_DEFECT_IDS = [f"quixbugs__prog{i:02d}" for i in range(41)]
_TEST_IDS = [f"quixbugs__prog{i:02d}_test" for i in range(9)]


def _det_map(defect_positives: int, *, none_ids: set[str] | None = None) -> dict[str, float | None]:
    """构造 detection 映射：41 缺陷 id 前 N 个为 1、其余 0；测试驱动 id 恒 None。"""
    det: dict[str, float | None] = {}
    for index, tid in enumerate(_DEFECT_IDS):
        det[tid] = 1.0 if index < defect_positives else 0.0
    for tid in _TEST_IDS:
        det[tid] = None
    for tid in none_ids or set():
        det[tid] = None
    return det


def _write_batch(
    path: Path,
    arm: str,
    detection: dict[str, float | None],
    *,
    spec_replace_applied: str | None = "attempted_replaced",
    specificity_gate_verdict: str | None = "specific_red",
) -> Path:
    ids = [*_DEFECT_IDS, *_TEST_IDS]
    details = [
        {
            "task_id": tid,
            "detection_rate": detection.get(tid),
            "spec_replace_applied": spec_replace_applied,
            "specificity_gate_verdict": specificity_gate_verdict,
        }
        for tid in ids
    ]
    path.write_text(json.dumps({"results": {arm: {"details": details}}}), encoding="utf-8")
    return path


def _c(p_one_sided: float, delta_pp: float = 8.0) -> dict[str, Any]:
    return {"p_one_sided": p_one_sided, "delta_pp": delta_pp}


# ─── 预注册常量锁定 ─────────────────────────────────────────────────────────
class TestPreregConstants:
    def test_constants_match_prereg(self) -> None:
        """判定常量与预注册 §3 逐项对齐（改常量必须先改预注册）。"""
        assert SUCCESS_LINE == 0.65
        assert FAIL_LINE == 0.55
        assert CONFIRM_P == 0.05
        assert TREND_P == 0.10
        assert MISGUIDED_DROP_TARGET == 0.30

    def test_arm_names_and_prereg_pointer(self) -> None:
        assert CONTROL_ARM == "plain_llm_df"
        assert PRIMARY_ARM == "plain_llm_df_doc"
        assert UNION_ARM == "plain_llm_df_doc_union"
        assert PREREG_FILE == "docs/emse/EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md"
        assert PRIMARY_CONTRAST == "doc_vs_df"
        assert SECONDARY_CONTRAST == "union_vs_df"

    def test_prereg_constants_single_source(self) -> None:
        assert PREREG_CONSTANTS == {
            "success_line": SUCCESS_LINE,
            "fail_line": FAIL_LINE,
            "confirm_p": CONFIRM_P,
            "trend_p": TREND_P,
            "misguided_drop_target": MISGUIDED_DROP_TARGET,
            "primary_contrast": PRIMARY_CONTRAST,
            "secondary_contrast": SECONDARY_CONTRAST,
        }


# ─── 三态判定 ───────────────────────────────────────────────────────────────
class TestDecide:
    def test_confirmed_requires_rate_and_p(self) -> None:
        d = decide(_c(0.03), 0.65)
        assert d["verdict"] == "confirmed"
        assert d["conditions"]["absolute_line"]["met"] is True
        assert d["conditions"]["one_sided_p_lt_0.05"] is True
        assert d["conditions"]["direction_positive"] is True
        assert d["fail_line_triggered"] is False

    def test_rate_below_success_line_blocks_confirmed(self) -> None:
        d = decide(_c(0.03, 6.0), 0.64)
        assert d["verdict"] == "trend"  # p<0.05<0.10 且 δ>0，但未达 65% 绝对线
        assert d["conditions"]["absolute_line"]["met"] is False

    def test_trend_band(self) -> None:
        d = decide(_c(0.07, 5.0), 0.66)
        assert d["verdict"] == "trend"

    def test_not_confirmed_high_p(self) -> None:
        d = decide(_c(0.20), 0.70)
        assert d["verdict"] == "not_confirmed"

    def test_not_confirmed_negative_direction(self) -> None:
        d = decide(_c(0.07, -8.0), 0.70)
        assert d["verdict"] == "not_confirmed"

    def test_fail_line_flagged_independently(self) -> None:
        d = decide(_c(0.5, -20.0), 0.45)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is True
        assert FAIL_LINE > 0.45

    def test_rate_none_safe(self) -> None:
        d = decide(_c(1.0, 0.0), None)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is None
        assert d["conditions"]["absolute_line"]["met"] is None


# ─── 已知值与 MDE 复算 ──────────────────────────────────────────────────────
class TestKnownStatistics:
    def test_known_mcnemar_values(self) -> None:
        # 7:0 双侧 = 2 * 0.5^7 = 0.015625；8:1 双侧 = 2*(1+9)/512 = 0.0390625
        assert mcnemar_exact_p(7, 0) == pytest.approx(0.015625)
        assert mcnemar_exact_p(8, 1) == pytest.approx(0.0390625)
        assert mcnemar_exact_p(0, 0) == 1.0

    def test_mde_recompute(self) -> None:
        # 与评审口径一致：n≈35 → ≈16.6pp；n=41 → ≈15.3pp
        assert mde_two_proportion(35) == pytest.approx(16.57, abs=0.01)
        assert mde_two_proportion(41) == pytest.approx(15.31, abs=0.01)


# ─── 41 口径 / 行集校验（fail-closed）──────────────────────────────────────
class TestRowValidation:
    def test_validate_empty_arm_raises(self) -> None:
        with pytest.raises(MissingArtifactError, match="无任务行"):
            validate_arm_rows("doc", {})

    def test_validate_row_count_mismatch(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}, "t2": {"detection_rate": 0.0}}
        with pytest.raises(MissingArtifactError, match="行数异常"):
            validate_arm_rows("doc", rows, expected_rows=3)

    def test_validate_id_set_mismatch(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}}
        with pytest.raises(MissingArtifactError, match="task_id 集合"):
            validate_arm_rows("doc", rows, expected_ids={"t2"})

    def test_validate_ok(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}}
        # 校验通过 = 返回 None 且不抛（显式断言，零断言门禁要求）
        assert validate_arm_rows("doc", rows, expected_rows=1, expected_ids={"t1"}) is None


# ─── 机制指标声明 ───────────────────────────────────────────────────────────
class TestMechanismDeclaration:
    def test_declaration_without_report(self) -> None:
        decl = mechanism_declaration()
        assert decl["producer"] == "experiments/misguided_metrics.py"
        assert decl["caliber_doc"] == "docs/design/misguided_effective_metric.md"
        assert decl["classes"] == ["effective", "misguided", "both_pass", "both_fail"]
        assert decl["misguided_drop_target"] == MISGUIDED_DROP_TARGET
        assert decl["status"] == "external_declared"
        assert "report" not in decl

    def test_declaration_with_report_sha256(self, tmp_path: Path) -> None:
        report = tmp_path / "MISGUIDED_REPORT.json"
        report.write_text(json.dumps({"arms": {}}), encoding="utf-8")
        decl = mechanism_declaration(report)
        assert decl["report"] == str(report)
        assert decl["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


# ─── 端到端：三臂 + 三态 + 审计面 ───────────────────────────────────────────
def _three_arm_analysis(
    tmp_path: Path,
    *,
    df_positives: int,
    doc_positives: int,
    union_positives: int | None = None,
) -> dict[str, Any]:
    df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(df_positives), spec_replace_applied=None)
    doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(doc_positives))
    union = (
        _write_batch(tmp_path / "union.json", UNION_ARM, _det_map(union_positives))
        if union_positives is not None
        else None
    )
    return build_analysis(df, doc, union)


class TestThreeArmAnalysis:
    def test_confirmed_state(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=27, union_positives=27)
        assert out["verdict"] == "confirmed"
        assert out["conditions"]["absolute_line"]["rate"] == pytest.approx(27 / 41, abs=1e-4)
        assert out["conditions"]["one_sided_p_lt_0.05"] is True
        doc_vs_df = out["contrast"][PRIMARY_CONTRAST]
        assert doc_vs_df["a_only"] == 7 and doc_vs_df["b_only"] == 0
        assert doc_vs_df["n_pairs"] == 41
        assert doc_vs_df["ratio"] == "7:0"
        assert doc_vs_df["p_one_sided"] == pytest.approx(0.0078, abs=1e-4)
        assert doc_vs_df["p_two_sided"] == pytest.approx(0.0156, abs=1e-4)
        assert doc_vs_df["delta_pp"] == pytest.approx(7 / 41 * 100, abs=0.01)
        assert doc_vs_df["mde_pp"] == pytest.approx(mde_two_proportion(41), abs=0.01)
        # 分母口径：41 缺陷程序；9 个测试驱动任务 detection None 不进分母
        assert out["detection"]["doc"]["denominator_rows"] == 41
        assert out["detection"]["doc"]["measurable"] == 41
        assert out["detection"]["doc"]["positive"] == 27
        # 次级对比存在且标 role=secondary
        assert out["secondary"] is not None
        assert out["secondary"]["role"] == "secondary"
        assert out["secondary"]["verdict"] == "confirmed"
        assert SECONDARY_CONTRAST in out["contrast"]

    def test_trend_state(self, tmp_path: Path) -> None:
        # doc 25/41 = 61.0%：高于失败线、低于成功线；双向不一致 7:0 → p<0.05 → trend
        out = _three_arm_analysis(tmp_path, df_positives=18, doc_positives=25)
        assert out["verdict"] == "trend"
        assert out["fail_line_triggered"] is False
        assert out["detection"]["doc"]["rate"] == pytest.approx(25 / 41, abs=1e-4)
        assert out["secondary"] is None  # 未提供 union

    def test_not_confirmed_state(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=20, union_positives=20)
        assert out["verdict"] == "not_confirmed"
        assert out["contrast"][PRIMARY_CONTRAST]["delta_pp"] == 0.0
        assert out["contrast"][PRIMARY_CONTRAST]["p_one_sided"] == 1.0
        assert out["secondary"]["verdict"] == "not_confirmed"

    def test_fail_line_state(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=15)
        assert out["verdict"] == "not_confirmed"
        assert out["fail_line_triggered"] is True
        assert out["detection"]["doc"]["rate"] == pytest.approx(15 / 41, abs=1e-4)

    def test_audit_surface_and_input_sha256(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=27, union_positives=27)
        audit = out["audit"]
        assert audit["spec_replace_applied"]["doc"]["attempted_replaced"] == 50
        assert audit["spec_replace_applied"]["df"]["none"] == 50  # 对照臂无锚字段（sra=None）
        assert audit["denominators"]["arm_rows"] == 50
        assert audit["denominators"]["defect_program_ids_41"] == 41
        assert audit["denominators"]["measurable_pairs_doc_vs_df"] == 41
        assert audit["detection_none_rows"]["doc_41"] == 0
        for key in ("df", "doc", "union"):
            entry = out["inputs"][key]
            assert len(entry["sha256"]) == 64
            assert entry["sha256"] == hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()

    def test_union_missing_secondary_reported(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=27)
        assert out["secondary"] is None
        assert "union" not in out["detection"]
        assert "union" not in out["audit"]["spec_replace_applied"]
        assert "union" not in out["inputs"]

    def test_mechanism_declared_in_report(self, tmp_path: Path) -> None:
        report = tmp_path / "MISGUIDED_REPORT.json"
        report.write_text(json.dumps({"report": "stub"}), encoding="utf-8")
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(27))
        out = build_analysis(df, doc, misguided_report=report)
        assert out["mechanism"]["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
        assert out["mechanism"]["status"] == "external_declared"


# ─── fail-closed：缺臂 / 异常工件 ───────────────────────────────────────────
class TestFailClosed:
    def test_missing_arm_file(self, tmp_path: Path) -> None:
        doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(27))
        with pytest.raises(MissingArtifactError, match="工件缺失"):
            build_analysis(tmp_path / "nope.json", doc)

    def test_wrong_arm_key(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        bad_doc = _write_batch(tmp_path / "bad.json", "some_other_arm", _det_map(27))
        with pytest.raises(MissingArtifactError, match="缺失或 details"):
            build_analysis(df, bad_doc)

    def test_row_count_mismatch_between_arms(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        doc_path = tmp_path / "doc.json"
        doc_path.write_text(
            json.dumps(
                {
                    "results": {
                        PRIMARY_ARM: {
                            "details": [
                                {"task_id": "quixbugs__prog00", "detection_rate": 1.0},
                                {"task_id": "quixbugs__prog01", "detection_rate": 0.0},
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(MissingArtifactError, match="行数异常"):
            build_analysis(df, doc_path)

    def test_zero_measurable_pairs(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20, none_ids=set(_DEFECT_IDS)))
        doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(27, none_ids=set(_DEFECT_IDS)))
        with pytest.raises(MissingArtifactError, match="可判定配对为 0"):
            build_analysis(df, doc)

    def test_union_missing_file(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(27))
        with pytest.raises(MissingArtifactError, match="工件缺失"):
            build_analysis(df, doc, tmp_path / "no_union.json")


# ─── Markdown / CLI ─────────────────────────────────────────────────────────
class TestMarkdownAndCli:
    def test_render_markdown_contains_verdict_and_audit(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=27, union_positives=27)
        md = render_markdown(out)
        assert "verdict：`confirmed`" in md
        assert "doc_vs_df（主）" in md
        assert "union_vs_df（次级）" in md
        assert "spec_replace_applied" in md
        assert "doc（处理 A）" in md
        assert "机制指标" in md
        assert "MDE" in md
        assert "`not_confirmed`" not in md  # 本构造为 confirmed，不得串态

    def test_render_markdown_union_missing_note(self, tmp_path: Path) -> None:
        out = _three_arm_analysis(tmp_path, df_positives=20, doc_positives=27)
        md = render_markdown(out)
        assert "union 臂未提供" in md

    def test_cli_writes_json_and_markdown(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        doc = _write_batch(tmp_path / "doc.json", PRIMARY_ARM, _det_map(27))
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        rc = main(["--df", str(df), "--doc", str(doc), "--out", str(out_json), "--markdown", str(out_md)])
        assert rc == 0
        report = json.loads(out_json.read_text(encoding="utf-8"))
        assert report["verdict"] == "confirmed"
        assert out_md.is_file() and "verdict：`confirmed`" in out_md.read_text(encoding="utf-8")
        captured = capsys.readouterr().out
        assert "verdict=confirmed" in captured

    def test_cli_fail_closed_exit_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det_map(20))
        rc = main(["--df", str(df), "--doc", str(tmp_path / "missing.json")])
        assert rc == 1
        assert "✗" in capsys.readouterr().err
