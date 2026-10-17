#!/usr/bin/env python3
"""M-1 规格增广双臂分析脚本契约测试（零 LLM；纯函数纪律 + 端到端临时工件）。

锁定对象 `experiments/emse_docstring_augment_analysis.py`：
- 预注册判定常量（88% 成功线 / 78% 失败线 / 0.05 confirm / 0.10 trend /
  non-inferiority δ ≥ −5pp / MDE reference n=35）与 `PREREG_CONSTANTS` 单一事实源；
- 三态判定边界（confirmed / trend / not_confirmed + 失败线独立标记）与
  **non-inferiority 独立标记**（不改变 verdict）；
- 对比方向与分母口径（41 缺陷程序口径、双方 detection 非 None 才配对）；
- 已知 McNemar 精确值与 MDE 复算；输入 sha256；
- 审计面：`spec_augment_applied` 命中分布 + `spec_replace_applied` 互斥核验；
- fail-closed（缺臂 / 行数或行集合异常 / 可判定配对为 0）；
- JSON/Markdown 输出 + CLI 退出码。

背景：按"有入库测试锁定契约的 emse 脚本必须入库"纪律随本测试入库。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from experiments.emse_docstring_augment_analysis import (
    CONFIRM_P,
    CONTROL_ARM,
    FAIL_LINE,
    MDE_REFERENCE_N,
    NON_INFERIORITY_MARGIN_PP,
    PREREG_CONSTANTS,
    PREREG_FILE,
    PRIMARY_ARM,
    PRIMARY_CONTRAST,
    SUCCESS_LINE,
    TREND_P,
    MissingArtifactError,
    build_analysis,
    decide,
    load_augment_rows,
    main,
    mechanism_declaration,
    render_markdown,
    validate_arm_rows,
)
from experiments.emse_quixbugs_specir_expand import mcnemar_exact_p, mde_two_proportion

# 41 缺陷程序口径 + 9 测试驱动任务（与 QuixBugs 50 任务同构）
_DEFECT_IDS = [f"quixbugs__prog{i:02d}" for i in range(41)]
_TEST_IDS = [f"quixbugs__prog{i:02d}_test" for i in range(9)]


def _det(positive: set[str]) -> dict[str, float | None]:
    """41 缺陷 id 命中集合为 1、其余 0；测试驱动 id 恒 None（不进分母）。"""
    det: dict[str, float | None] = {}
    for tid in _DEFECT_IDS:
        det[tid] = 1.0 if tid in positive else 0.0
    for tid in _TEST_IDS:
        det[tid] = None
    return det


def _first_n(n: int) -> set[str]:
    return set(_DEFECT_IDS[:n])


def _write_batch(
    path: Path,
    arm: str,
    detection: dict[str, float | None],
    *,
    spec_augment_applied: str | None = "attempted_augmented",
    spec_replace_applied: str | None = None,
    specificity_gate_verdict: str | None = "specific_red",
) -> Path:
    ids = [*_DEFECT_IDS, *_TEST_IDS]
    details = [
        {
            "task_id": tid,
            "detection_rate": detection.get(tid),
            "spec_augment_applied": spec_augment_applied,
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
        assert SUCCESS_LINE == 0.88
        assert FAIL_LINE == 0.78
        assert CONFIRM_P == 0.05
        assert TREND_P == 0.10
        assert NON_INFERIORITY_MARGIN_PP == -5.0
        assert MDE_REFERENCE_N == 35

    def test_arm_names_and_prereg_pointer(self) -> None:
        assert CONTROL_ARM == "plain_llm_df"
        assert PRIMARY_ARM == "plain_llm_df_doc_augment"
        assert PREREG_FILE == "docs/emse/EMSE_DOCSTRING_AUGMENT_PREREG_2026-10-17.md"
        assert PRIMARY_CONTRAST == "augment_vs_df"

    def test_prereg_constants_single_source(self) -> None:
        assert PREREG_CONSTANTS == {
            "success_line": SUCCESS_LINE,
            "fail_line": FAIL_LINE,
            "confirm_p": CONFIRM_P,
            "trend_p": TREND_P,
            "non_inferiority_margin_pp": NON_INFERIORITY_MARGIN_PP,
            "mde_reference_n": MDE_REFERENCE_N,
            "primary_contrast": PRIMARY_CONTRAST,
        }


# ─── 三态判定 + non-inferiority 独立标记 ───────────────────────────────────
class TestDecide:
    def test_confirmed_requires_rate_and_p(self) -> None:
        d = decide(_c(0.03), 0.88)
        assert d["verdict"] == "confirmed"
        assert d["conditions"]["absolute_line"]["met"] is True
        assert d["conditions"]["one_sided_p_lt_0.05"] is True
        assert d["conditions"]["direction_positive"] is True
        assert d["fail_line_triggered"] is False

    def test_absolute_line_boundary_is_inclusive(self) -> None:
        """88% 绝对线含边界（rate == threshold 视为达标）。"""
        d = decide(_c(0.01), 0.88)
        assert d["conditions"]["absolute_line"]["met"] is True
        assert d["verdict"] == "confirmed"

    def test_rate_below_success_line_blocks_confirmed_and_trend(self) -> None:
        """trend 也要求绝对线达标：rate < 88% 即使 p<0.10 ∧ δ>0 仍 not_confirmed。"""
        d = decide(_c(0.03, 6.0), 0.87)
        assert d["verdict"] == "not_confirmed"
        assert d["conditions"]["absolute_line"]["met"] is False

    def test_trend_band(self) -> None:
        d = decide(_c(0.07, 5.0), 0.90)
        assert d["verdict"] == "trend"
        assert d["conditions"]["absolute_line"]["met"] is True

    def test_not_confirmed_high_p(self) -> None:
        d = decide(_c(0.20), 0.95)
        assert d["verdict"] == "not_confirmed"

    def test_not_confirmed_negative_direction(self) -> None:
        d = decide(_c(0.07, -8.0), 0.90)
        assert d["verdict"] == "not_confirmed"
        assert d["conditions"]["direction_positive"] is False

    def test_fail_line_flagged_independently(self) -> None:
        d = decide(_c(0.5, -20.0), 0.70)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is True
        assert d["non_inferiority"]["met"] is False

    def test_non_inferiority_boundary_inclusive(self) -> None:
        """δ = −5.0pp 恰好满足非劣边界（≥ −5pp 含边界）。"""
        d = decide(_c(0.5, -5.0), 0.80)
        assert d["non_inferiority"]["met"] is True
        assert d["non_inferiority"]["role"] == "independent_marker"
        assert d["non_inferiority"]["margin_pp"] == NON_INFERIORITY_MARGIN_PP

    def test_non_inferiority_fails_below_margin(self) -> None:
        d = decide(_c(1.0, -5.01), 0.85)
        assert d["non_inferiority"]["met"] is False

    def test_non_inferiority_independent_of_verdict(self) -> None:
        """verdict 可为 not_confirmed 而 non-inferiority 仍成立（独立标记）。"""
        d = decide(_c(1.0, -2.0), 0.73)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is True
        assert d["non_inferiority"]["met"] is True

    def test_rate_none_safe(self) -> None:
        d = decide(_c(1.0, 0.0), None)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is None
        assert d["conditions"]["absolute_line"]["met"] is None
        assert d["non_inferiority"]["met"] is None


# ─── 已知值与 MDE 复算 ──────────────────────────────────────────────────────
class TestKnownStatistics:
    def test_known_mcnemar_values(self) -> None:
        # 6:0 单向 = 0.5^6 = 0.015625；6:1 单向 = P(X≥6|n=7) = 8/128 = 0.0625
        assert mcnemar_exact_p(6, 0) == pytest.approx(0.03125)
        assert mcnemar_exact_p(6, 1) == pytest.approx(0.125)
        assert mcnemar_exact_p(0, 0) == 1.0

    def test_mde_recompute(self) -> None:
        # 与预注册披露一致：n≈35 → ≈16.6pp；n=41 → ≈15.3pp
        assert mde_two_proportion(MDE_REFERENCE_N) == pytest.approx(16.57, abs=0.01)
        assert mde_two_proportion(41) == pytest.approx(15.31, abs=0.01)


# ─── 41 口径 / 行集校验（fail-closed）──────────────────────────────────────
class TestRowValidation:
    def test_validate_empty_arm_raises(self) -> None:
        with pytest.raises(MissingArtifactError, match="无任务行"):
            validate_arm_rows("augment", {})

    def test_validate_row_count_mismatch(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}, "t2": {"detection_rate": 0.0}}
        with pytest.raises(MissingArtifactError, match="行数异常"):
            validate_arm_rows("augment", rows, expected_rows=3)

    def test_validate_id_set_mismatch(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}}
        with pytest.raises(MissingArtifactError, match="task_id 集合"):
            validate_arm_rows("augment", rows, expected_ids={"t2"})

    def test_validate_ok(self) -> None:
        rows = {"t1": {"detection_rate": 1.0}}
        assert validate_arm_rows("augment", rows, expected_rows=1, expected_ids={"t1"}) is None


# ─── 加载器补审计字段 ──────────────────────────────────────────────────────
class TestLoadAugmentRows:
    def test_enriches_spec_augment_applied(self, tmp_path: Path) -> None:
        path = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, _det(_first_n(31)))
        rows = load_augment_rows(path, PRIMARY_ARM)
        assert len(rows) == 50
        assert {row["spec_augment_applied"] for row in rows.values()} == {"attempted_augmented"}

    def test_missing_field_defaults_none(self, tmp_path: Path) -> None:
        """旧批次无该字段（或值为 null）→ 行摘要补 None，不 KeyError。"""
        path = tmp_path / "old.json"
        path.write_text(
            json.dumps(
                {
                    "results": {
                        PRIMARY_ARM: {
                            "details": [{"task_id": "quixbugs__prog00", "detection_rate": 1.0}],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        rows = load_augment_rows(path, PRIMARY_ARM)
        assert rows["quixbugs__prog00"]["spec_augment_applied"] is None


# ─── 机制指标声明 ───────────────────────────────────────────────────────────
class TestMechanismDeclaration:
    def test_declaration_without_report(self) -> None:
        decl = mechanism_declaration()
        assert decl["producer"] == "experiments/misguided_metrics.py"
        assert decl["caliber_doc"] == "docs/design/misguided_effective_metric.md"
        assert decl["classes"] == ["effective", "misguided", "both_pass", "both_fail"]
        assert decl["status"] == "external_declared"
        assert decl["primary_arm"] == PRIMARY_ARM
        assert "report" not in decl

    def test_declaration_with_report_sha256(self, tmp_path: Path) -> None:
        report = tmp_path / "MISGUIDED_REPORT.json"
        report.write_text(json.dumps({"arms": {}}), encoding="utf-8")
        decl = mechanism_declaration(report)
        assert decl["report"] == str(report)
        assert decl["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


# ─── 端到端：两臂 + 三态 + 非劣 + 审计面 ───────────────────────────────────
def _pair(
    tmp_path: Path,
    df_positive: set[str],
    aug_positive: set[str],
    *,
    df_audit: str | None = None,
    aug_audit: str | None = "attempted_augmented",
) -> dict[str, Any]:
    df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(df_positive), spec_augment_applied=df_audit)
    aug = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, _det(aug_positive), spec_augment_applied=aug_audit)
    return build_analysis(df, aug)


class TestTwoArmAnalysis:
    def test_confirmed_state(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, common | set(_DEFECT_IDS[31:37]))
        assert out["verdict"] == "confirmed"
        assert out["conditions"]["absolute_line"]["rate"] == pytest.approx(37 / 41, abs=1e-4)
        assert out["conditions"]["one_sided_p_lt_0.05"] is True
        c = out["contrast"][PRIMARY_CONTRAST]
        assert c["a_only"] == 6 and c["b_only"] == 0
        assert c["n_pairs"] == 41
        assert c["ratio"] == "6:0"
        assert c["p_one_sided"] == pytest.approx(0.0156, abs=1e-4)
        assert c["p_two_sided"] == pytest.approx(0.0312, abs=1e-4)
        assert c["delta_pp"] == pytest.approx(6 / 41 * 100, abs=0.01)
        # 分母口径：41 缺陷程序；9 个测试驱动任务 detection None 不进分母
        assert out["detection"]["augment"]["denominator_rows"] == 41
        assert out["detection"]["augment"]["measurable"] == 41
        assert out["detection"]["augment"]["positive"] == 37
        assert out["non_inferiority"]["met"] is True

    def test_trend_state(self, tmp_path: Path) -> None:
        """rate≥88% ∧ p∈[0.05,0.10) ∧ δ>0 → trend。"""
        common = _first_n(31)
        aug = common | set(_DEFECT_IDS[32:38])  # aug 37
        df = common | {_DEFECT_IDS[31]}  # df 32；6:1
        out = _pair(tmp_path, df, aug)
        assert out["verdict"] == "trend"
        assert out["fail_line_triggered"] is False
        c = out["contrast"][PRIMARY_CONTRAST]
        assert c["ratio"] == "6:1"
        assert c["p_one_sided"] == pytest.approx(0.0625, abs=1e-4)

    def test_not_confirmed_state(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, common)
        assert out["verdict"] == "not_confirmed"
        assert out["contrast"][PRIMARY_CONTRAST]["delta_pp"] == 0.0
        assert out["contrast"][PRIMARY_CONTRAST]["p_one_sided"] == 1.0
        # non-inferiority 仍成立（δ=0 ≥ −5pp；独立标记不改变 verdict）
        assert out["non_inferiority"]["met"] is True

    def test_fail_line_state(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, _first_n(30))
        assert out["verdict"] == "not_confirmed"
        assert out["fail_line_triggered"] is True
        assert out["detection"]["augment"]["rate"] == pytest.approx(30 / 41, abs=1e-4)
        assert out["non_inferiority"]["met"] is True  # δ=−2.44pp 仍在 −5pp 内

    def test_audit_surface_and_input_sha256(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, common | set(_DEFECT_IDS[31:37]), df_audit=None)
        audit = out["audit"]
        assert audit["spec_augment_applied"]["df"] == {"none": 50}
        assert audit["spec_augment_applied"]["augment"] == {"attempted_augmented": 50}
        assert audit["spec_augment_applied"]["augment_41"] == {"attempted_augmented": 41}
        # 互斥核验：augment 臂不得出现 replace 审计值
        assert audit["spec_replace_applied"]["augment"] == {"none": 50}
        assert audit["denominators"]["arm_rows"] == 50
        assert audit["denominators"]["defect_program_ids_41"] == 41
        assert audit["denominators"]["measurable_pairs_augment_vs_df"] == 41
        for key in ("df", "augment"):
            entry = out["inputs"][key]
            assert len(entry["sha256"]) == 64
            assert entry["sha256"] == hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()

    def test_mde_block_reported(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, common)
        assert out["mde"]["reference_n"] == 35
        assert out["mde"]["mde_pp_at_reference_n"] == pytest.approx(16.57, abs=0.01)
        assert out["mde"]["observed_n_pairs"] == 41
        assert "16.6pp" in out["mde"]["disclosure"]

    def test_boundary_tasks_fallback_audit(self, tmp_path: Path) -> None:
        """node.py（空 human_spec）+ 9 测试驱动任务回落 → attempted_fallback=10。"""
        aug_rows = load_augment_rows(
            _write_batch(
                tmp_path / "aug.json", PRIMARY_ARM, _det(_first_n(31)), spec_augment_applied="attempted_fallback"
            ),
            PRIMARY_ARM,
        )
        assert {row["spec_augment_applied"] for row in aug_rows.values()} == {"attempted_fallback"}

    def test_mechanism_declared_in_report(self, tmp_path: Path) -> None:
        report = tmp_path / "MISGUIDED_REPORT.json"
        report.write_text(json.dumps({"report": "stub"}), encoding="utf-8")
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(_first_n(31)), spec_augment_applied=None)
        aug = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, _det(_first_n(31)))
        out = build_analysis(df, aug, misguided_report=report)
        assert out["mechanism"]["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
        assert out["mechanism"]["status"] == "external_declared"


# ─── fail-closed：缺臂 / 异常工件 ───────────────────────────────────────────
class TestFailClosed:
    def test_missing_arm_file(self, tmp_path: Path) -> None:
        aug = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, _det(_first_n(31)))
        with pytest.raises(MissingArtifactError, match="工件缺失"):
            build_analysis(tmp_path / "nope.json", aug)

    def test_wrong_arm_key(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(_first_n(31)))
        bad_aug = _write_batch(tmp_path / "bad.json", "some_other_arm", _det(_first_n(31)))
        with pytest.raises(MissingArtifactError, match="缺失或 details"):
            build_analysis(df, bad_aug)

    def test_row_count_mismatch_between_arms(self, tmp_path: Path) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(_first_n(31)))
        aug_path = tmp_path / "aug.json"
        aug_path.write_text(
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
            build_analysis(df, aug_path)

    def test_zero_measurable_pairs(self, tmp_path: Path) -> None:
        none_det = {tid: None for tid in [*_DEFECT_IDS, *_TEST_IDS]}
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, none_det, spec_augment_applied=None)
        aug = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, none_det)
        with pytest.raises(MissingArtifactError, match="可判定配对为 0"):
            build_analysis(df, aug)


# ─── Markdown / CLI ─────────────────────────────────────────────────────────
class TestMarkdownAndCli:
    def test_render_markdown_contains_verdict_and_audit(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, common | set(_DEFECT_IDS[31:37]))
        md = render_markdown(out)
        assert "verdict：`confirmed`" in md
        assert "augment_vs_df（主）" in md
        assert "spec_augment_applied" in md
        assert "spec_replace_applied" in md
        assert "non-inferiority" in md
        assert "MDE" in md
        assert "`not_confirmed`" not in md  # 本构造为 confirmed，不得串态

    def test_render_markdown_fail_line_marker(self, tmp_path: Path) -> None:
        common = _first_n(31)
        out = _pair(tmp_path, common, _first_n(30))
        md = render_markdown(out)
        assert "⚠️ 触发" in md

    def test_cli_writes_json_and_markdown(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        common = _first_n(31)
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(common), spec_augment_applied=None)
        aug = _write_batch(tmp_path / "aug.json", PRIMARY_ARM, _det(common | set(_DEFECT_IDS[31:37])))
        out_json = tmp_path / "report.json"
        out_md = tmp_path / "report.md"
        rc = main(["--df", str(df), "--augment", str(aug), "--out", str(out_json), "--markdown", str(out_md)])
        assert rc == 0
        report = json.loads(out_json.read_text(encoding="utf-8"))
        assert report["verdict"] == "confirmed"
        assert report["non_inferiority"]["met"] is True
        assert out_md.is_file() and "verdict：`confirmed`" in out_md.read_text(encoding="utf-8")
        assert "verdict=confirmed" in capsys.readouterr().out

    def test_cli_fail_closed_exit_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        df = _write_batch(tmp_path / "df.json", CONTROL_ARM, _det(_first_n(31)), spec_augment_applied=None)
        rc = main(["--df", str(df), "--augment", str(tmp_path / "missing.json")])
        assert rc == 1
        assert "✗" in capsys.readouterr().err
