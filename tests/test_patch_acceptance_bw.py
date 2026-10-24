"""BW 轮（2026-10-23）：补丁接收链的「分母不可见」——收口锁。

缺陷形态（零 LLM；普查工具 `scripts/tools/bw_patch_acceptance_census.py`）：

- `patch_precision`（R53，预注册 E3 要求的指标）自写入起报告面 **0 读者**；
- `patch_plausible_evidence` / `patch_plausible_invariant_violation`（P0-2）
  是 `plausible` 的唯一可复核依据与 `correct=1 ∧ plausible=0` 的显式观测，只写不读；
- `patch_abstain_signals`（批次 V，ADR-0020）只写不读，弃权精确率无处可读；
- `patch_validated` / `patch_validate_verdict`（批次 XVI）只有测试读者，
  filtered success 的覆盖率在报告面缺席。

四组判定值本身**忠实**；沉默在分母与输入可达域上：

- `patch_precision=None` 只表示 `plausible=0`；而 `plausible=1 ∧ repair_rate=None`
  的行写侧保守取 `correct=0` ⇒ `precision=0.0`，把「无 gold 材料」写成「测了且错」；
- `correct=1 ∧ plausible=0` 让接收集与正确集不是包含关系（归档 139 行）；
- 弃权门在「失败且无补丁」的行上没有可抑制对象，却与真正抑制同记 `abstained=True`；
- 验证层两个最强输入（`repo_verification` / `deterministic_repair_status`）
  在整个归档里**可达域为空**，`validated=True` 全部来自最弱的 `patch_evidence_level`。

修复口径：**纯读侧**。判定核、写入端、归档行一处不动（`src/` 零改动），
只补单一事实源 + 分档统计 + 报告面章节 + 批次摘要行。判定值与方向不变。

锁的形状（沿用 BQ/BT/BU/BV 纪律）：全归档读数（11197 / 8012 / 1331 / 607 / 139 /
283 / 685 / 3605 / 3037 …）是**实测读数**，登记在手册并附复现命令，不在这里锁死
（新批次一旦落盘就会漂移）。本文件锁的是：①键名/词表与判定核同源、②折叠语义
（字符串布尔、缺键 ≠ 0）、③分档恒等式、④报告面逐格与脚注、⑤批次摘要行、
⑥五份具名冻结批次的逐档读数。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
from experiments._patch_acceptance import (
    ABSTAINED_KEY,
    ABSTAIN_BUCKETS,
    ABSTAIN_SIGNALS_KEY,
    CORRECT_GOLD_INCORRECT,
    CORRECT_KEY,
    CORRECT_MEASURED,
    CORRECT_NO_GOLD,
    CORRECT_UNRECORDED,
    EVIDENCE_KEY,
    INVARIANT_KEY,
    PATCH_KEY,
    PLAUSIBLE_KEY,
    PRECISION_KEY,
    VALIDATED_KEY,
    VALIDATE_VERDICT_KEY,
    abstain_applicable,
    abstain_bucket,
    abstain_signal_names,
    abstain_signals,
    correct,
    correct_status,
    evidence_basis,
    evidence_mismatch,
    evidence_plausible,
    filtered_success,
    flag,
    invariant_flag,
    invariant_recomputed,
    patch_present,
    plausible,
    precision_expected,
    precision_mismatch,
    precision_stored,
    recompute_abstention,
    recompute_validation,
    validated,
    validation_inputs,
    validation_verdict,
)
from experiments.statistical_analysis import patch_acceptance_stats
from src.tools.patch_abstain import patch_abstain_signal_names
from src.tools.patch_validate import patch_validate_verdict_names

ROOT = Path(__file__).resolve().parents[1]

#: 具名冻结批次：逐档读数由 `scripts/tools/bw_patch_acceptance_census.py --segment c` 复核。
#: 五份覆盖五种形态：R53 后 P0-2 前的旧臂 / 只落弃权键的臂 / flag 记真且排除集判对的臂 /
#: 大量无 gold 的低精确率臂 / 四键齐备的现代臂。
PINNED_BATCHES: dict[str, dict[str, Any]] = {
    "experiments/results/main_batch/benchmark_synthetic_20261007_185941.json": {
        "n_rows": 261,
        "acc_recorded": 261,
        "plausible": 11,
        "correct": 0,
        "pc": 0,
        "pi": 11,
        "ic": 0,
        "iic": 250,
        "no_gold": 0,
        "gold_correct": 0,
        "gold_incorrect": 11,
        "precision_mismatch": 0,
        "invariant": {"flag_unrecorded": 261},
        "evidence": {
            "n_recorded": 0,
            "n_unrecorded": 261,
            "basis": {"evidence_unrecorded": 261},
            "n_plausible_without_evidence": 11,
            "n_mismatch": 0,
        },
        "abstain": {
            "n_recorded": 0,
            "n_abstained": 0,
            "n_no_effect": 0,
            "n_actionable": 0,
            "n_suppressed": 0,
            "suppressed_status": {},
            "n_signal_nonempty": 0,
            "n_multi_signal": 0,
            "signals": {},
            "n_abstain_mismatch": 0,
            "n_signal_mismatch": 0,
        },
        "validate": {
            "n_recorded": 0,
            "n_validated": 0,
            "n_unvalidated": 0,
            "n_no_input": 0,
            "n_unvalidated_without_input": 0,
            "verdict": {},
            "evidence_level_values": {},
            "n_passed": 0,
            "n_passed_abstained": 0,
            "n_passed_not_abstained": 0,
            "n_filtered_success": 0,
            "n_verdict_mismatch": 0,
            "n_validated_mismatch": 0,
        },
    },
    "experiments/results/llm_logic_ab_20261010_202129/c3/benchmark_quixbugs_20261010_210638.json": {
        "n_rows": 46,
        "acc_recorded": 46,
        "plausible": 45,
        "correct": 32,
        "pc": 32,
        "pi": 13,
        "ic": 0,
        "iic": 1,
        "no_gold": 9,
        "gold_correct": 32,
        "gold_incorrect": 4,
        "precision_mismatch": 0,
        "invariant": {"flag_unrecorded": 46},
        "evidence": {
            "n_recorded": 0,
            "n_unrecorded": 46,
            "basis": {"evidence_unrecorded": 46},
            "n_plausible_without_evidence": 45,
            "n_mismatch": 0,
        },
        "abstain": {
            "n_recorded": 46,
            "n_abstained": 32,
            "n_no_effect": 0,
            "n_actionable": 32,
            "n_suppressed": 11,
            "suppressed_status": {"correct": 11},
            "n_signal_nonempty": 32,
            "n_multi_signal": 15,
            "signals": {
                "patch_evidence_level": 19,
                "specificity_gate_verdict": 20,
                "test_regenerated_pass_unverified": 8,
            },
            "n_abstain_mismatch": 0,
            "n_signal_mismatch": 0,
        },
        "validate": {
            "n_recorded": 0,
            "n_validated": 0,
            "n_unvalidated": 0,
            "n_no_input": 0,
            "n_unvalidated_without_input": 0,
            "verdict": {},
            "evidence_level_values": {},
            "n_passed": 0,
            "n_passed_abstained": 0,
            "n_passed_not_abstained": 0,
            "n_filtered_success": 0,
            "n_verdict_mismatch": 0,
            "n_validated_mismatch": 0,
        },
    },
    "experiments/results/pilot_mdo_full50/benchmark_quixbugs_20261011_122633.json": {
        "n_rows": 100,
        "acc_recorded": 100,
        "plausible": 28,
        "correct": 36,
        "pc": 28,
        "pi": 0,
        "ic": 8,
        "iic": 64,
        "no_gold": 0,
        "gold_correct": 28,
        "gold_incorrect": 0,
        "precision_mismatch": 0,
        "invariant": {"violation": 8, "flag_true": 8},
        "evidence": {
            "n_recorded": 100,
            "n_unrecorded": 0,
            "basis": {"applied": 28, "no_patch": 52, "rejected": 20},
            "n_plausible_without_evidence": 0,
            "n_mismatch": 0,
        },
        "abstain": {
            "n_recorded": 100,
            "n_abstained": 20,
            "n_no_effect": 0,
            "n_actionable": 20,
            "n_suppressed": 0,
            "suppressed_status": {},
            "n_signal_nonempty": 20,
            "n_multi_signal": 20,
            "signals": {"patch_evidence_level": 20, "source_patched_unverified": 20},
            "n_abstain_mismatch": 0,
            "n_signal_mismatch": 0,
        },
        "validate": {
            "n_recorded": 100,
            "n_validated": 28,
            "n_unvalidated": 72,
            "n_no_input": 52,
            "n_unvalidated_without_input": 52,
            "verdict": {"evidence": 28, "unvalidated": 72},
            "evidence_level_values": {"none": 20, "null": 52, "sbfl": 28},
            "n_passed": 24,
            "n_passed_abstained": 0,
            "n_passed_not_abstained": 24,
            "n_filtered_success": 22,
            "n_verdict_mismatch": 0,
            "n_validated_mismatch": 0,
        },
    },
    "experiments/results/emse_calib_quixbugs_20261014/benchmark_quixbugs_20261014_165103.json": {
        "n_rows": 50,
        "acc_recorded": 50,
        "plausible": 25,
        "correct": 2,
        "pc": 2,
        "pi": 23,
        "ic": 0,
        "iic": 25,
        "no_gold": 23,
        "gold_correct": 2,
        "gold_incorrect": 0,
        "precision_mismatch": 0,
        "invariant": {},
        "evidence": {
            "n_recorded": 50,
            "n_unrecorded": 0,
            "basis": {"applied": 25, "no_patch": 1, "rejected": 24},
            "n_plausible_without_evidence": 0,
            "n_mismatch": 0,
        },
        "abstain": {
            "n_recorded": 50,
            "n_abstained": 23,
            "n_no_effect": 0,
            "n_actionable": 23,
            "n_suppressed": 0,
            "suppressed_status": {},
            "n_signal_nonempty": 23,
            "n_multi_signal": 22,
            "signals": {"patch_evidence_level": 22, "source_patched_unverified": 23},
            "n_abstain_mismatch": 0,
            "n_signal_mismatch": 0,
        },
        "validate": {
            "n_recorded": 50,
            "n_validated": 25,
            "n_unvalidated": 25,
            "n_no_input": 2,
            "n_unvalidated_without_input": 2,
            "verdict": {"evidence": 25, "unvalidated": 25},
            "evidence_level_values": {"keyword": 1, "none": 22, "null": 2, "sbfl": 25},
            "n_passed": 20,
            "n_passed_abstained": 0,
            "n_passed_not_abstained": 20,
            "n_filtered_success": 19,
            "n_verdict_mismatch": 0,
            "n_validated_mismatch": 0,
        },
    },
    "experiments/results/t_round_b2_main_batch_20261018/seed44/benchmark_synthetic_20261018_120845.json": {
        "n_rows": 261,
        "acc_recorded": 261,
        "plausible": 14,
        "correct": 10,
        "pc": 10,
        "pi": 4,
        "ic": 0,
        "iic": 247,
        "no_gold": 0,
        "gold_correct": 10,
        "gold_incorrect": 4,
        "precision_mismatch": 0,
        "invariant": {},
        "evidence": {
            "n_recorded": 261,
            "n_unrecorded": 0,
            "basis": {"applied": 14, "no_patch": 247},
            "n_plausible_without_evidence": 0,
            "n_mismatch": 0,
        },
        "abstain": {
            "n_recorded": 261,
            "n_abstained": 224,
            "n_no_effect": 31,
            "n_actionable": 193,
            "n_suppressed": 185,
            "suppressed_status": {"correct": 2, "gold_incorrect": 183},
            "n_signal_nonempty": 224,
            "n_multi_signal": 111,
            "signals": {
                "detection_first_status": 177,
                "specificity_gate_verdict": 45,
                "test_regenerated_pass_unverified": 113,
            },
            "n_abstain_mismatch": 0,
            "n_signal_mismatch": 0,
        },
        "validate": {
            "n_recorded": 261,
            "n_validated": 14,
            "n_unvalidated": 247,
            "n_no_input": 247,
            "n_unvalidated_without_input": 247,
            "verdict": {"evidence": 14, "unvalidated": 247},
            "evidence_level_values": {"null": 247, "sbfl": 14},
            "n_passed": 187,
            "n_passed_abstained": 185,
            "n_passed_not_abstained": 2,
            "n_filtered_success": 2,
            "n_verdict_mismatch": 0,
            "n_validated_mismatch": 0,
        },
    },
}


# ═══ 1. 键名与词表的单一事实源 ═══════════════════════════════════════════════


class TestKeyRegistry:
    def test_writer_still_emits_every_key(self) -> None:
        source = (ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        for key in (
            PLAUSIBLE_KEY,
            CORRECT_KEY,
            PRECISION_KEY,
            EVIDENCE_KEY,
            INVARIANT_KEY,
            ABSTAINED_KEY,
            ABSTAIN_SIGNALS_KEY,
            VALIDATED_KEY,
            VALIDATE_VERDICT_KEY,
        ):
            assert f'"{key}"' in source, key

    def test_signal_vocab_is_the_detector_vocab(self) -> None:
        assert abstain_signal_names() == patch_abstain_signal_names()
        assert set(abstain_signal_names()) == {
            "test_regenerated_pass_unverified",
            "detection_first_status",
            "specificity_gate_verdict",
            "patch_evidence_level",
            "source_patched_unverified",
        }

    def test_verdict_vocab_is_the_detector_vocab(self) -> None:
        assert set(patch_validate_verdict_names()) == {
            "gold",
            "deterministic",
            "evidence",
            "unvalidated",
            "not_applicable",
        }

    def test_abstain_buckets_are_the_four_passed_patch_combinations(self) -> None:
        assert ABSTAIN_BUCKETS == (
            "passed_with_patch",
            "passed_no_patch",
            "failed_with_patch",
            "failed_no_patch",
        )


# ═══ 2. 折叠语义：缺键 ≠ 0，字符串布尔不得用 bool() ═══════════════════════════


class TestFlagFolding:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (True, 1),
            (False, 0),
            (1, 1),
            (0, 0),
            ("true", 1),
            ("TRUE", 1),
            ("yes", 1),
            ("on", 1),
            ("1", 1),
            ("false", 0),
            ("no", 0),
            ("off", 0),
            ("0", 0),
            (None, None),
            ("", None),
            ("maybe", None),
            (2, None),
        ],
    )
    def test_flag_folds_explicitly(self, raw: Any, expected: int | None) -> None:
        assert flag(raw) == expected

    def test_string_false_is_not_truthy(self) -> None:
        assert flag("false") == 0
        assert bool("false") is True  # 这正是不能用 bool() 的原因

    def test_missing_key_is_none_not_zero(self) -> None:
        assert plausible({}) is None
        assert correct({}) is None
        assert validated({}) is None
        assert invariant_flag({}) is None
        assert validation_verdict({}) == "unrecorded"

    def test_present_but_null_is_none(self) -> None:
        assert plausible({PLAUSIBLE_KEY: None}) is None
        assert correct({CORRECT_KEY: None}) is None
        assert validated({VALIDATED_KEY: None}) is None


class TestCorrectStatus:
    def test_correct_is_measured(self) -> None:
        assert correct_status({CORRECT_KEY: 1}) == CORRECT_MEASURED

    def test_zero_with_gold_is_gold_incorrect(self) -> None:
        assert correct_status({CORRECT_KEY: 0, "repair_rate": 0.0}) == CORRECT_GOLD_INCORRECT

    def test_zero_without_gold_is_not_an_error(self) -> None:
        assert correct_status({CORRECT_KEY: 0}) == CORRECT_NO_GOLD
        assert correct_status({CORRECT_KEY: 0, "repair_rate": None}) == CORRECT_NO_GOLD

    def test_missing_correct_key(self) -> None:
        assert correct_status({}) == CORRECT_UNRECORDED


class TestPrecision:
    def test_expected_is_none_only_when_denominator_is_zero(self) -> None:
        assert precision_expected({PLAUSIBLE_KEY: 0, CORRECT_KEY: 1}) is None
        assert precision_expected({PLAUSIBLE_KEY: 1, CORRECT_KEY: 1}) == 1.0
        assert precision_expected({PLAUSIBLE_KEY: 1, CORRECT_KEY: 0}) == 0.0
        assert precision_expected({PLAUSIBLE_KEY: 1}) is None

    def test_stored_rejects_bool_and_string(self) -> None:
        assert precision_stored({PRECISION_KEY: True}) is None
        assert precision_stored({PRECISION_KEY: "0.5"}) is None
        assert precision_stored({PRECISION_KEY: 0.5}) == 0.5

    def test_mismatch_distinguishes_none_from_zero(self) -> None:
        assert precision_mismatch({PLAUSIBLE_KEY: 0, CORRECT_KEY: 0, PRECISION_KEY: None}) is False
        assert precision_mismatch({PLAUSIBLE_KEY: 1, CORRECT_KEY: 0, PRECISION_KEY: 0.0}) is False
        assert precision_mismatch({PLAUSIBLE_KEY: 1, CORRECT_KEY: 0, PRECISION_KEY: None}) is True
        assert precision_mismatch({PLAUSIBLE_KEY: 0, CORRECT_KEY: 0, PRECISION_KEY: 0.0}) is True
        assert precision_mismatch({PLAUSIBLE_KEY: 1, CORRECT_KEY: 1, PRECISION_KEY: 0.5}) is True


class TestEvidence:
    def test_basis_vocabulary(self) -> None:
        assert evidence_basis({}) == "evidence_unrecorded"
        assert evidence_basis({EVIDENCE_KEY: None}) == "other:non_mapping"
        assert evidence_basis({EVIDENCE_KEY: {}}) == "other:None"
        assert evidence_basis({EVIDENCE_KEY: {"basis": "applied"}}) == "applied"

    def test_only_two_bases_imply_plausible(self) -> None:
        assert evidence_plausible("applied") == 1
        assert evidence_plausible("applied_then_rejected") == 1
        assert evidence_plausible("rejected") == 0
        assert evidence_plausible("no_patch") == 0
        assert evidence_plausible("no_state") == 0
        assert evidence_plausible("evidence_unrecorded") is None
        assert evidence_plausible("other:None") is None

    def test_mismatch_ignores_unrecorded_and_unknown(self) -> None:
        assert evidence_mismatch({PLAUSIBLE_KEY: 1}) is False
        assert evidence_mismatch({PLAUSIBLE_KEY: 1, EVIDENCE_KEY: {"basis": "applied"}}) is False
        assert evidence_mismatch({PLAUSIBLE_KEY: 1, EVIDENCE_KEY: {"basis": "rejected"}}) is True
        assert evidence_mismatch({PLAUSIBLE_KEY: 0, EVIDENCE_KEY: {"basis": "applied"}}) is True
        assert evidence_mismatch({PLAUSIBLE_KEY: 1, EVIDENCE_KEY: {"basis": "weird"}}) is False


class TestInvariant:
    def test_recomputed_needs_both_values(self) -> None:
        assert invariant_recomputed({PLAUSIBLE_KEY: 0, CORRECT_KEY: 1}) is True
        assert invariant_recomputed({PLAUSIBLE_KEY: 0, CORRECT_KEY: 0}) is False
        assert invariant_recomputed({PLAUSIBLE_KEY: 1, CORRECT_KEY: 1}) is False
        assert invariant_recomputed({PLAUSIBLE_KEY: 0}) is None

    def test_flag_absence_is_not_false(self) -> None:
        assert invariant_flag({INVARIANT_KEY: True}) == 1
        assert invariant_flag({INVARIANT_KEY: "false"}) == 0
        assert invariant_flag({}) is None


class TestAbstainPrimitives:
    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            ({"passed": 1, PATCH_KEY: "diff"}, "passed_with_patch"),
            ({"passed": 1}, "passed_no_patch"),
            ({"passed": 0, PATCH_KEY: "diff"}, "failed_with_patch"),
            ({"passed": 0}, "failed_no_patch"),
        ],
    )
    def test_bucket_covers_all_four(self, row: dict[str, Any], expected: str) -> None:
        assert abstain_bucket(row) == expected

    def test_only_failed_without_patch_has_no_actionable_object(self) -> None:
        assert abstain_applicable({"passed": 1}) is True
        assert abstain_applicable({"passed": 0, PATCH_KEY: "diff"}) is True
        assert abstain_applicable({"passed": 0}) is False

    def test_patch_presence_is_whitespace_aware(self) -> None:
        assert patch_present({PATCH_KEY: "  "}) is False
        assert patch_present({PATCH_KEY: "diff"}) is True

    def test_signals_are_never_guessed(self) -> None:
        assert abstain_signals({}) == []
        assert abstain_signals({ABSTAIN_SIGNALS_KEY: None}) == []
        assert abstain_signals({ABSTAIN_SIGNALS_KEY: "patch_evidence_level"}) == []
        assert abstain_signals({ABSTAIN_SIGNALS_KEY: ["a", 1]}) == ["a", "1"]


class TestValidationPrimitives:
    def test_inputs_are_only_available_evidence(self) -> None:
        assert validation_inputs({}) == ()
        assert validation_inputs({"repo_verification": None}) == ()
        assert validation_inputs({"repo_verification": {}}) == ("repo_verification",)
        assert validation_inputs({"deterministic_repair_status": {}}) == ("deterministic_repair_status",)
        assert validation_inputs({"patch_evidence_level": "none"}) == ("patch_evidence_level",)
        assert validation_inputs({"patch_evidence_level": None}) == ()
        assert validation_inputs({"repo_verification": {}, "patch_evidence_level": "sbfl"}) == (
            "repo_verification",
            "patch_evidence_level",
        )

    def test_verdict_is_the_archived_value(self) -> None:
        assert validation_verdict({VALIDATE_VERDICT_KEY: "gold"}) == "gold"
        assert validation_verdict({VALIDATE_VERDICT_KEY: None}) == "None"
        assert validation_verdict({}) == "unrecorded"

    def test_filtered_success_needs_three_conditions(self) -> None:
        base = {"passed": True, "patch_abstained": False, "patch_validated": True}
        assert filtered_success(base) is True
        assert filtered_success({**base, "passed": False}) is False
        assert filtered_success({**base, "patch_abstained": True}) is False
        assert filtered_success({**base, "patch_validated": False}) is False


# ═══ 3. 判定核重跑（只读对账） ═══════════════════════════════════════════════


class TestRecomputeKernels:
    def test_abstention_matches_signals(self) -> None:
        assert recompute_abstention({"source_patched_unverified": True}) == {
            "abstain": True,
            "signals": ["source_patched_unverified"],
        }
        assert recompute_abstention({"patch_evidence_level": "sbfl"}) == {"abstain": False, "signals": []}

    def test_validation_matches_evidence_order(self) -> None:
        assert recompute_validation({})["verdict"] == "unvalidated"
        assert recompute_validation({"patch_evidence_level": "sbfl"})["verdict"] == "evidence"
        assert recompute_validation({"deterministic_repair_status": {"patch_produced": True}})["verdict"] == (
            "deterministic"
        )
        assert (
            recompute_validation({"repo_verification": {"passed": True}, "patch_evidence_level": "sbfl"})["verdict"]
            == "gold"
        )
        assert recompute_validation(None) == {"validated": False, "verdict": "not_applicable", "signals": []}


# ═══ 4. 统计分档与恒等式 ═════════════════════════════════════════════════════


def _stats_row(
    task_id: str,
    *,
    plausible_value: int,
    correct_value: int,
    repair_rate: float | None,
    basis: str,
    passed: bool = True,
    patch: str | None = "diff",
    abstained: bool = False,
    signals: list[str] | None = None,
    validated_value: bool = False,
    verdict: str = "unvalidated",
    level: str | None = None,
    source_unverified: bool = False,
) -> dict[str, Any]:
    precision = correct_value / plausible_value if plausible_value else None
    row: dict[str, Any] = {
        "task_id": task_id,
        "passed": passed,
        PATCH_KEY: patch,
        PLAUSIBLE_KEY: plausible_value,
        CORRECT_KEY: correct_value,
        PRECISION_KEY: precision,
        "repair_rate": repair_rate,
        EVIDENCE_KEY: {"basis": basis},
        ABSTAINED_KEY: abstained,
        ABSTAIN_SIGNALS_KEY: signals or [],
        VALIDATED_KEY: validated_value,
        VALIDATE_VERDICT_KEY: verdict,
        "patch_evidence_level": level,
        "source_patched_unverified": source_unverified,
    }
    return row


def _fixture_rows() -> list[dict[str, Any]]:
    """四行覆盖四种接收形态 + 一行 legacy（无任何 BW 键）。"""
    return [
        _stats_row(
            "t1",
            plausible_value=1,
            correct_value=1,
            repair_rate=1.0,
            basis="applied",
            validated_value=True,
            verdict="evidence",
            level="sbfl",
        ),
        _stats_row(
            "t2",
            plausible_value=1,
            correct_value=0,
            repair_rate=0.0,
            basis="applied",
            abstained=True,
            signals=["source_patched_unverified"],
            source_unverified=True,
        ),
        _stats_row(
            "t3",
            plausible_value=1,
            correct_value=0,
            repair_rate=None,
            basis="applied_then_rejected",
            abstained=True,
            signals=["patch_evidence_level"],
            level="none",
        ),
        _stats_row(
            "t4",
            plausible_value=0,
            correct_value=1,
            repair_rate=1.0,
            basis="rejected",
            passed=False,
            validated_value=True,
            verdict="gold",
            level=None,
        )
        | {"repo_verification": {"passed": True}},
        {"task_id": "t5"},
    ]


class TestStatsIdentities:
    def test_empty_rows_yield_zero_counts(self) -> None:
        out = patch_acceptance_stats([])
        assert out["n_rows"] == 0
        assert out["acceptance"]["n_recorded"] == 0
        assert out["acceptance"]["precision"]["value"] is None
        assert out["acceptance"]["coverage"]["value"] is None
        assert out["abstain"]["suppressed_precision"]["value"] is None
        assert out["validate"]["filtered_coverage_passed"] is None

    def test_acceptance_partition_identity(self) -> None:
        a = patch_acceptance_stats(_fixture_rows())["acceptance"]
        assert (
            a["n_plausible_correct"]
            + a["n_plausible_incorrect"]
            + a["n_implausible_correct"]
            + a["n_implausible_incorrect"]
            == a["n_recorded"]
        )
        assert a["n_plausible"] == a["n_plausible_correct"] + a["n_plausible_incorrect"]
        assert a["n_correct"] == a["n_plausible_correct"] + a["n_implausible_correct"]
        assert a["precision"]["value"] == a["n_plausible_correct"] / a["n_plausible"]
        assert a["precision"]["union_value"] == a["n_correct"] / (a["n_plausible"] + a["n_implausible_correct"])
        assert a["precision"]["gold_value"] == a["n_gold_correct"] / a["n_plausible_gold"]
        assert a["coverage"]["value"] == a["n_plausible"] / a["n_recorded"]
        assert a["selective_risk"]["value"] == a["n_plausible_incorrect"] / a["n_plausible"]
        assert a["selective_risk"]["gold_value"] == a["n_gold_incorrect"] / a["n_plausible_gold"]
        assert sum(a["correct_status"].values()) == a["n_recorded"]

    def test_evidence_basis_partition_identity(self) -> None:
        e = patch_acceptance_stats(_fixture_rows())["evidence"]
        assert sum(e["basis"].values()) == patch_acceptance_stats(_fixture_rows())["n_rows"]
        assert e["n_recorded"] + e["n_unrecorded"] == patch_acceptance_stats(_fixture_rows())["n_rows"]
        assert e["n_implied_plausible"] == e["basis"].get("applied", 0) + e["basis"].get("applied_then_rejected", 0)

    def test_abstain_bucket_identity(self) -> None:
        out = patch_acceptance_stats(_fixture_rows())
        ab = out["abstain"]
        assert sum(sum(counter.values()) for counter in ab["buckets"].values()) == ab["n_recorded"]
        assert ab["n_abstained"] + ab["n_not_abstained"] + ab["n_other"] == ab["n_recorded"]
        assert ab["n_actionable"] + ab["n_no_effect"] == ab["n_abstained"]
        assert ab["n_recorded"] + ab["n_unrecorded"] == out["n_rows"]

    def test_suppressed_precision_has_two_denominators(self) -> None:
        ab = patch_acceptance_stats(_fixture_rows())["abstain"]
        assert ab["n_suppressed"] == 2
        assert ab["suppressed_status"] == {CORRECT_GOLD_INCORRECT: 1, CORRECT_NO_GOLD: 1}
        assert ab["suppressed_precision"]["value"] == 1.0
        assert ab["suppressed_precision"]["all_value"] == 0.5

    def test_validate_partition_identity(self) -> None:
        va = patch_acceptance_stats(_fixture_rows())["validate"]
        assert va["n_validated"] + va["n_unvalidated"] + va["n_other"] == va["n_recorded"]
        assert sum(va["verdict"].values()) == va["n_recorded"]
        assert va["n_passed"] == va["n_passed_abstained"] + va["n_passed_not_abstained"]
        assert va["filtered_coverage_passed"] == va["n_filtered_success"] / va["n_passed"]
        assert va["filtered_coverage_passed_not_abstained"] == (va["n_filtered_success"] / va["n_passed_not_abstained"])

    def test_no_input_and_unvalidated_are_separate_cells(self) -> None:
        va = patch_acceptance_stats(_fixture_rows())["validate"]
        assert va["n_no_input"] == 1
        assert va["n_unvalidated_without_input"] == 1
        assert va["n_unvalidated"] == 2
        assert va["input_counts"] == {"repo_verification": 1, "patch_evidence_level": 2}

    def test_correct_rate_mismatch_is_counted(self) -> None:
        row = _stats_row("x", plausible_value=1, correct_value=1, repair_rate=0.0, basis="applied")
        assert patch_acceptance_stats([row])["acceptance"]["correct_rate_mismatch"] == 1

    def test_buckets_split_suppressed_from_no_effect(self) -> None:
        rows = [
            _stats_row(
                "a",
                plausible_value=1,
                correct_value=0,
                repair_rate=0.0,
                basis="applied",
                abstained=True,
                signals=["patch_evidence_level"],
                level="none",
            ),
            _stats_row(
                "b",
                plausible_value=1,
                correct_value=0,
                repair_rate=0.0,
                basis="applied",
                passed=False,
                patch=None,
                abstained=True,
                signals=["patch_evidence_level"],
                level="none",
            ),
        ]
        ab = patch_acceptance_stats(rows)["abstain"]
        assert ab["n_abstained"] == 2
        assert ab["n_actionable"] == 1
        assert ab["n_no_effect"] == 1
        assert ab["buckets"]["passed_with_patch"]["abstained"] == 1
        assert ab["buckets"]["failed_no_patch"]["abstained"] == 1

    def test_signal_domain_separates_null_from_missing(self) -> None:
        ab = patch_acceptance_stats(_fixture_rows())["abstain"]
        assert ab["signal_domain"]["patch_evidence_level"] == {"recorded": 2, "null": 2}
        assert ab["signal_domain"]["source_patched_unverified"] == {"recorded": 4}
        assert ab["signal_domain"]["test_regenerated_pass_unverified"] == {"missing": 4}
        assert sum(sum(counter.values()) for counter in ab["signal_domain"].values()) == 4 * len(ab["signal_domain"])

    def test_four_way_partition_names_the_malformed_bucket(self) -> None:
        a = patch_acceptance_stats(_fixture_rows())["acceptance"]
        assert sum(a["plausible"].values()) == a["n_recorded"]
        assert sum(a["correct"].values()) == a["n_recorded"]
        assert sum(a["cross"].values()) == a["n_recorded"]
        assert a["cross"].get("other", 0) == 0

    def test_acceptance_requires_all_three_keys(self) -> None:
        partial = {"task_id": "p", PLAUSIBLE_KEY: 1, CORRECT_KEY: 1}
        assert patch_acceptance_stats([partial])["acceptance"]["n_recorded"] == 0
        full = {**partial, PRECISION_KEY: 1.0}
        assert patch_acceptance_stats([full])["acceptance"]["n_recorded"] == 1

    def test_other_evidence_basis_is_named_not_recorded(self) -> None:
        row = _stats_row("x", plausible_value=1, correct_value=1, repair_rate=1.0, basis="applied")
        row[EVIDENCE_KEY] = None
        e = patch_acceptance_stats([row])["evidence"]
        assert e["n_recorded"] == 0
        assert e["n_other"] == 1
        assert e["basis"] == {"other:non_mapping": 1}

    def test_precision_mismatch_is_counted(self) -> None:
        row = _stats_row("x", plausible_value=1, correct_value=1, repair_rate=1.0, basis="applied")
        row[PRECISION_KEY] = 0.5
        assert patch_acceptance_stats([row])["acceptance"]["precision_mismatch"] == 1

    def test_abstain_and_signal_mismatches_are_counted(self) -> None:
        silent = _stats_row("a", plausible_value=1, correct_value=0, repair_rate=0.0, basis="applied", abstained=True)
        ab = patch_acceptance_stats([silent])["abstain"]
        assert ab["n_abstain_mismatch"] == 1
        assert ab["n_signal_mismatch"] == 0
        wrong_signal = _stats_row(
            "b",
            plausible_value=1,
            correct_value=0,
            repair_rate=0.0,
            basis="applied",
            abstained=True,
            signals=["patch_evidence_level"],
            level=None,
        )
        ab = patch_acceptance_stats([wrong_signal])["abstain"]
        assert ab["n_abstain_mismatch"] == 1
        assert ab["n_signal_mismatch"] == 1

    def test_validation_mismatches_are_counted(self) -> None:
        wrong_verdict = _stats_row(
            "v1",
            plausible_value=1,
            correct_value=1,
            repair_rate=1.0,
            basis="applied",
            validated_value=True,
            verdict="gold",
            level="sbfl",
        )
        va = patch_acceptance_stats([wrong_verdict])["validate"]
        assert va["n_verdict_mismatch"] == 1
        assert va["n_validated_mismatch"] == 0
        wrong_flag = _stats_row(
            "v2",
            plausible_value=1,
            correct_value=1,
            repair_rate=1.0,
            basis="applied",
            validated_value=True,
            verdict="not_applicable",
            level=None,
        )
        va = patch_acceptance_stats([wrong_flag])["validate"]
        assert va["n_validated_mismatch"] == 1
        assert va["n_verdict_mismatch"] == 0

    def test_no_input_counts_regardless_of_validated_value(self) -> None:
        row = _stats_row(
            "v",
            plausible_value=1,
            correct_value=1,
            repair_rate=1.0,
            basis="applied",
            validated_value=True,
            verdict="not_applicable",
            level=None,
        )
        va = patch_acceptance_stats([row])["validate"]
        assert va["n_no_input"] == 1
        assert va["n_unvalidated_without_input"] == 0


# ═══ 5. 报告面 ═════════════════════════════════════════════════════════════════


class TestReportSurface:
    @staticmethod
    def _analysis(rows: list[dict]) -> dict[str, Any]:
        return ar_mod.build_analysis(
            {
                "dataset": "demo",
                "results": {
                    "aitester": {
                        "details": rows,
                        "total_functions": len(rows),
                        "passed_count": sum(1 for r in rows if r.get("passed")),
                        "success_rate": 100.0,
                        "avg_coverage": 0.3,
                        "avg_iterations": 1.5,
                        "avg_elapsed_seconds": 1.5,
                        "total_time": 3.0,
                    }
                },
            }
        )

    def _md(self) -> str:
        return ar_mod.render_markdown(self._analysis(_fixture_rows()), "demo.json")

    def test_build_analysis_exposes_the_new_key(self) -> None:
        per = self._analysis(_fixture_rows())["per_baseline"]["aitester"]
        assert per["patch_acceptance"]["acceptance"]["n_plausible"] == 3
        assert per["patch_acceptance"]["abstain"]["n_suppressed"] == 2

    def test_new_key_moves_no_existing_judgment_value(self) -> None:
        with_keys = self._analysis(_fixture_rows())["per_baseline"]["aitester"]
        bw_keys = {
            PLAUSIBLE_KEY,
            CORRECT_KEY,
            PRECISION_KEY,
            EVIDENCE_KEY,
            INVARIANT_KEY,
            ABSTAINED_KEY,
            ABSTAIN_SIGNALS_KEY,
            VALIDATED_KEY,
            VALIDATE_VERDICT_KEY,
        }
        stripped = [{k: v for k, v in row.items() if k not in bw_keys} for row in _fixture_rows()]
        base = self._analysis(stripped)["per_baseline"]["aitester"]
        for key in ("total_functions", "passed_count", "success_rate", "avg_coverage"):
            assert with_keys[key] == base[key], key

    def test_acceptance_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 5 | 4 | 3 | 2 | 1 | 2 | 1 | 1 | 33.3% | 50.0% | 50.0% | 75.0% | 66.7% |" in md
        assert "| **合计** | 5 | 4 | 3 | 2 | 1 | 2 | 1 | 1 | 33.3% | 50.0% | 50.0% | 75.0% | 66.7% |" in md

    def test_evidence_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 4 | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 3 | 0 | 0 |" in md
        assert "| **合计** | 4 | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 3 | 0 | 0 |" in md

    def test_abstain_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 4 | 2 | 2 | 0 | 2 | 1 | 100.0% | 2 | 0 | 0 | 0 | 0 |" in md
        assert "| **合计** | 4 | 2 | 2 | 0 | 2 | 1 | 100.0% | 2 | 0 | 0 | 0 | 0 |" in md

    def test_validate_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 4 | 2 | 2 | 1 | 1 | 3 | 2 | 1 | 1 | 33.3% | 100.0% | 0 | 0 |" in md
        assert "| **合计** | 4 | 2 | 2 | 1 | 1 | 3 | 2 | 1 | 1 | 33.3% | 100.0% | 0 | 0 |" in md

    def test_all_four_tables_have_consistent_cell_counts(self) -> None:
        md = self._md()
        lines = md.splitlines()
        heading = "## 补丁接收链的覆盖率与分母（BW：`patch_precision` / 证据 / 弃权 / 验证的读侧）"
        tables: list[list[str]] = [[]]
        for line in lines[lines.index(heading) + 1 :]:
            if line.startswith("## "):
                break
            if line.startswith("|"):
                tables[-1].append(line)
            elif tables[-1]:
                tables.append([])
        tables = [t for t in tables if t]
        # 每表 = 表头 + 分隔行 + 单基线行 + 合计行。
        assert [[len(ln.split("|")) - 2 for ln in t] for t in tables] == [
            [14, 14, 14, 14],
            [12, 12, 12, 12],
            [13, 13, 13, 13],
            [14, 14, 14, 14],
        ], tables

    def test_three_precisions_are_three_denominators(self) -> None:
        md = self._md()
        assert "三个精确率是三个分母，不是三个估计" in md
        assert "1 行 `correct=1 ∧ plausible=0`" in md
        assert "剔除 1 行「无 gold 材料」" in md

    def test_precision_none_is_not_zero(self) -> None:
        md = self._md()
        assert "**不得读作 0，也不得读作「无 gold」**" in md

    def test_selective_risk_is_reported_with_coverage(self) -> None:
        md = self._md()
        assert "`选择性风险` = 接受集判错 / plausible" in md
        assert "66.7%" in md

    def test_correct_zero_is_split_into_two_causes(self) -> None:
        md = self._md()
        assert "gold 判错 1 行 / 无 gold 材料 1 行" in md
        assert "**不是判错**" in md

    def test_correct_zero_split_covers_implausible_rows_too(self) -> None:
        extra = _stats_row(
            "t7",
            plausible_value=0,
            correct_value=0,
            repair_rate=0.0,
            basis="rejected",
            passed=False,
        )
        md = ar_mod.render_markdown(self._analysis([*_fixture_rows(), extra]), "demo.json")
        assert "gold 判错 2 行 / 无 gold 材料 1 行" in md

    def test_invariant_flag_absence_is_not_a_pass(self) -> None:
        md = self._md()
        assert "布尔键为真 0 行、**键缺席 1 行**" in md
        assert "缺席不得读作「未违反」" in md

    def test_legacy_cohort_is_not_read_as_zero_plausible(self) -> None:
        md = self._md()
        assert "接收链未记录 1 行（早于 R53）" in md
        assert "**不等于**「plausible=0」" in md

    def test_abstain_denominators_are_disclosed(self) -> None:
        md = self._md()
        assert "0 行是「失败且无补丁」" in md
        assert "`可抑制` = 2 行" in md
        assert "两个数都要报" in md
        domain_part = md.split("信号域（已记录行的键状态）：", 1)[1].split("。", 1)[0]
        for name in abstain_signal_names():
            assert f"`{name}`" in domain_part

    def test_validation_says_unvalidated_is_not_failed(self) -> None:
        md = self._md()
        assert "`unvalidated` ≠ 「验证过且失败」" in md
        assert "1 行**根本没有可用的验证输入**" in md
        assert "两个最强输入在整个归档里**可达域为空**" in md

    def test_artifact_caveat_is_registered_not_hidden(self) -> None:
        md = self._md()
        assert "ADR-0021" in md
        assert "本轮**未重跑**回放" in md

    def test_external_calibers_are_named(self) -> None:
        md = self._md()
        assert "selective prediction" in md
        assert "覆盖率为 0 时风险是**未定义**" in md
        assert "弃权精确率" in md

    def test_section_absent_when_no_rows(self) -> None:
        md = ar_mod.render_markdown(self._analysis([]), "demo.json")
        assert "## 补丁接收链的覆盖率与分母" not in md

    def test_ratio_helper_prints_dash_for_zero_denominator(self) -> None:
        assert ar_mod._ratio_text(0, 0) == "—"
        assert ar_mod._ratio_text(1, 4) == "25.0%"


# ═══ 6. 批次摘要接线（run_main_batch） ═════════════════════════════════════════


class TestSummaryLine:
    @staticmethod
    def _write_batch(tmp_path: Path, rows: list[dict]) -> Path:
        payload = {
            "dataset": "demo",
            "results": {
                "aitester": {
                    "details": rows,
                    "success_rate": 100.0,
                    "effective_total": len(rows),
                    "harness_invalid_count": 0,
                }
            },
        }
        path = tmp_path / "benchmark_demo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_summary_prints_acceptance_and_validation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import experiments.run_main_batch as main_mod

        rows = _fixture_rows()[:2]
        main_mod._print_r4_summary(self._write_batch(tmp_path, rows))
        out = capsys.readouterr().out
        assert "BW 补丁接收链: 已记录 2/2" in out
        assert "plausible 2（无 gold 0）" in out
        assert "correct 1（交 1、排除集判对 0）" in out
        assert "精确率 50.0% / gold 50.0%，覆盖率 100.0%" in out
        assert "BW 弃权/验证: abstained 1/2" in out
        assert "抑制 passed 1、精确率 100.0%" in out
        assert "validated 1/2" in out
        assert "filtered success 1/2" in out

    def test_summary_filtered_denominator_is_passed_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import experiments.run_main_batch as main_mod

        failed = _stats_row(
            "t6",
            plausible_value=0,
            correct_value=0,
            repair_rate=None,
            basis="no_patch",
            passed=False,
            patch=None,
        )
        rows = [*_fixture_rows()[:2], failed]
        main_mod._print_r4_summary(self._write_batch(tmp_path, rows))
        out = capsys.readouterr().out
        assert "已记录 3/3" in out
        assert "filtered success 1/2" in out

    def test_summary_does_not_print_zero_for_legacy_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import experiments.run_main_batch as main_mod

        main_mod._print_r4_summary(self._write_batch(tmp_path, [{"task_id": "t1"}]))
        out = capsys.readouterr().out
        assert "BW 补丁接收链" not in out
        assert "BW 弃权/验证" not in out


# ═══ 7. 具名冻结批次 ═══════════════════════════════════════════════════════════


def _reading(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = patch_acceptance_stats(rows)
    a, e, ab, va = out["acceptance"], out["evidence"], out["abstain"], out["validate"]
    return {
        "n_rows": out["n_rows"],
        "acc_recorded": a["n_recorded"],
        "plausible": a["n_plausible"],
        "correct": a["n_correct"],
        "pc": a["n_plausible_correct"],
        "pi": a["n_plausible_incorrect"],
        "ic": a["n_implausible_correct"],
        "iic": a["n_implausible_incorrect"],
        "no_gold": a["n_plausible_no_gold"],
        "gold_correct": a["n_gold_correct"],
        "gold_incorrect": a["n_gold_incorrect"],
        "precision_mismatch": a["precision_mismatch"],
        "invariant": a["invariant"],
        "evidence": {
            "n_recorded": e["n_recorded"],
            "n_unrecorded": e["n_unrecorded"],
            "basis": e["basis"],
            "n_plausible_without_evidence": e["n_plausible_without_evidence"],
            "n_mismatch": e["n_mismatch"],
        },
        "abstain": {
            "n_recorded": ab["n_recorded"],
            "n_abstained": ab["n_abstained"],
            "n_no_effect": ab["n_no_effect"],
            "n_actionable": ab["n_actionable"],
            "n_suppressed": ab["n_suppressed"],
            "suppressed_status": ab["suppressed_status"],
            "n_signal_nonempty": ab["n_signal_nonempty"],
            "n_multi_signal": ab["n_multi_signal"],
            "signals": ab["signals"],
            "n_abstain_mismatch": ab["n_abstain_mismatch"],
            "n_signal_mismatch": ab["n_signal_mismatch"],
        },
        "validate": {
            "n_recorded": va["n_recorded"],
            "n_validated": va["n_validated"],
            "n_unvalidated": va["n_unvalidated"],
            "n_no_input": va["n_no_input"],
            "n_unvalidated_without_input": va["n_unvalidated_without_input"],
            "verdict": va["verdict"],
            "evidence_level_values": va["evidence_level_values"],
            "n_passed": va["n_passed"],
            "n_passed_abstained": va["n_passed_abstained"],
            "n_passed_not_abstained": va["n_passed_not_abstained"],
            "n_filtered_success": va["n_filtered_success"],
            "n_verdict_mismatch": va["n_verdict_mismatch"],
            "n_validated_mismatch": va["n_validated_mismatch"],
        },
    }


@pytest.mark.parametrize("rel", sorted(PINNED_BATCHES))
def test_pinned_batch_reads_as_registered(rel: str) -> None:
    path = ROOT / rel
    if not path.exists():
        pytest.skip(
            "登记批次不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
    assert path.exists(), rel
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        r
        for blk in (doc.get("results") or {}).values()
        for r in (blk or {}).get("details") or []
        if isinstance(r, dict)
    ]
    assert _reading(rows) == PINNED_BATCHES[rel], rel


def test_census_tool_reads_the_same_pinned_batches() -> None:
    """普查工具的 C 段从本文件的 `PINNED_BATCHES` 解析读数（AST 字面量），防止两边漂移。"""
    tool = ROOT / "scripts" / "tools" / "bw_patch_acceptance_census.py"
    source = tool.read_text(encoding="utf-8")
    assert "PINNED_BATCHES" in source
    assert "tests/test_patch_acceptance_bw.py" in source
    assert "ast.literal_eval" in source
    tree = ast.parse(source)
    assert any(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))
