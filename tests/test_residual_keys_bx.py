"""BX 轮（2026-10-23）：写而不读键池最后两键的读侧收口——锁。

缺陷形态（零 LLM；普查工具 `scripts/tools/bx_residual_keys_census.py`）：

- `risk_summary` 全归档 8,864 行在场、`enabled=True` **0 行**——`risk_level` /
  `approval_action` / `risk_score` 全 `None`、`pause_requested=False`。通道关闭
  的占位与「开启了且判低风险」「判定无需暂停」在按字段读取时同形；键缺席
  2,333 行同样不是低风险。`contract_status`（BL 起写入）在归档 0 行在场。
- `mdo_crash_rate` 4,044 行在场，输入域折叠成五层（未跑 2,312 / 材料缺 122 /
  不可测 986 / 暂定池 530 / 实测 94）；`mdo_pool_floor_ok=False` 是两义键
  （530 暂定池 + 986 默认值）；crash 分母是**全池 n**，而五个可评估计数
  （`mdo_status` / `mdo_evaluable` / `mdo_non_terminating` / `mdo_probe_invalid` /
  `mdo_no_effective_pass`）归档 0 行在场 ⇒ 可评估分母不可复算。

修复口径：**纯读侧**。`src/` 零改动；新增 `experiments/_residual_keys.py`
（单一事实源）+ `statistical_analysis.residual_keys_stats` + 报告面章节 +
批次摘要行。判定值、方向、归档行一处不动。

锁的形状（沿用 BQ/BT/BU/BV/BW 纪律）：全归档读数（11,197 / 8,864 / 2,333 /
4,044 / 2,312 / 122 / 986 / 530 / 94 / 15/3,200 / 12/7,190 …）是**实测读数**，
登记在手册并附复现命令，不在这里锁死（新批次一旦落盘就会漂移）。本文件锁的是：
①键名/词表与写入端同源、②五层输入域语义（含字符串布尔与缺键）、③值域
`None` ≠ `0` 与整数反推、④分档恒等式、⑤报告面逐格与脚注、⑥批次摘要行、
⑦三份具名冻结批次的逐档读数。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

import experiments._residual_keys as rk_mod
import experiments.analyze_results as ar_mod
from experiments._residual_keys import (
    CRASH_KEY,
    CRASH_LAYERS,
    CRASH_MATERIAL_ABSENT,
    CRASH_MEASURED,
    CRASH_NOT_MEASURABLE,
    CRASH_NOT_RUN,
    CRASH_PROVISIONAL,
    CRASH_UNMEASURED_LAYERS,
    MDO_EVALUABILITY_KEYS,
    RISK_CONTRACT_STATUS_KEY,
    RISK_KEY,
    RISK_PAUSE_KEY,
    RISK_PLACEHOLDER_FIELDS,
    _pooled,
    _reconstruct_count,
    _value_summary,
    crash_layer,
    mdo_crash_stats,
    residual_keys_stats,
    risk_summary_stats,
)
from experiments.statistical_analysis import residual_keys_stats as sa_residual_keys_stats

ROOT = Path(__file__).resolve().parents[1]

#: 具名冻结批次：逐档读数由 `scripts/tools/bx_residual_keys_census.py --segment c` 复核。
#: 三份覆盖三种形态：现代臂（材料缺 0、值全零）/ 五层齐备且含非零实测的臂 /
#: 早于 MDO 落盘的旧臂（键整列缺席，`absent ≠ 0`）。
PINNED_BATCHES: dict[str, dict[str, Any]] = {
    "experiments/results/t_round_b2_main_batch_20261018/seed42/benchmark_synthetic_20261018_100552.json": {
        "n_rows": 261,
        "risk": {
            "present": 261,
            "absent": 0,
            "enabled_true": 0,
            "enabled_false": 261,
            "enabled_missing": 0,
            "shapes": {"approval_action|enabled|factors|pause_requested|reasons|risk_level|risk_score": 261},
            "level_nonnull": 0,
            "level": {},
            "action": {},
            "score": {"n": 0, "mean": None, "median": None, "min": None, "max": None},
            "pause": {"true": 0, "false": 261, "absent": 0, "other": 0},
            "contract_status": {"present": 0, "absent": 261},
            "placeholder_mismatch": 0,
            "distribution_readable": False,
        },
        "crash": {
            "present": 261,
            "absent": 0,
            "layers": {
                "not_run": 0,
                "material_absent": 0,
                "not_measurable": 200,
                "provisional_pool": 48,
                "measured": 13,
            },
            "reasons": {"test_not_green_on_base(rc=1)": 200},
            "value_nonnull": 13,
            "zero": 13,
            "nonzero": 0,
            "value": {"n": 13, "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
            "pooled": {"n_unique": 13, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 447, "rate": 0.0},
            "raw_present": 48,
            "raw_zero": 48,
            "raw_nonzero": 0,
            "raw_pooled": {"n_unique": 48, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 624, "rate": 0.0},
            "floor_false": 248,
            "floor_provisional": 48,
            "floor_other": 200,
            "provisional_missing": 0,
            "evaluability": 0,
        },
    },
    "experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json": {
        "n_rows": 100,
        "risk": {
            "present": 100,
            "absent": 0,
            "enabled_true": 0,
            "enabled_false": 100,
            "enabled_missing": 0,
            "shapes": {"approval_action|enabled|factors|pause_requested|reasons|risk_level|risk_score": 100},
            "level_nonnull": 0,
            "level": {},
            "action": {},
            "score": {"n": 0, "mean": None, "median": None, "min": None, "max": None},
            "pause": {"true": 0, "false": 100, "absent": 0, "other": 0},
            "contract_status": {"present": 0, "absent": 100},
            "placeholder_mismatch": 0,
            "distribution_readable": False,
        },
        "crash": {
            "present": 100,
            "absent": 0,
            "layers": {
                "not_run": 0,
                "material_absent": 18,
                "not_measurable": 29,
                "provisional_pool": 47,
                "measured": 6,
            },
            "reasons": {
                "baseline_timeout": 4,
                "no_gold_material": 18,
                "test_not_green_on_base(rc=1)": 25,
            },
            "value_nonnull": 6,
            "zero": 4,
            "nonzero": 2,
            "value": {"n": 6, "mean": 0.0098, "median": 0.0, "min": 0.0, "max": 0.0294},
            "pooled": {
                "n_unique": 6,
                "n_ambiguous": 0,
                "n_failed": 0,
                "n_crash": 2,
                "n_pool": 192,
                "rate": 0.010416666666666666,
            },
            "raw_present": 47,
            "raw_zero": 47,
            "raw_nonzero": 0,
            "raw_pooled": {"n_unique": 47, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 670, "rate": 0.0},
            "floor_false": 76,
            "floor_provisional": 47,
            "floor_other": 29,
            "provisional_missing": 18,
            "evaluability": 0,
        },
    },
    "experiments/results/main_batch/benchmark_synthetic_20261007_185941.json": {
        "n_rows": 261,
        "risk": {
            "present": 261,
            "absent": 0,
            "enabled_true": 0,
            "enabled_false": 261,
            "enabled_missing": 0,
            "shapes": {"approval_action|enabled|factors|pause_requested|reasons|risk_level|risk_score": 261},
            "level_nonnull": 0,
            "level": {},
            "action": {},
            "score": {"n": 0, "mean": None, "median": None, "min": None, "max": None},
            "pause": {"true": 0, "false": 261, "absent": 0, "other": 0},
            "contract_status": {"present": 0, "absent": 261},
            "placeholder_mismatch": 0,
            "distribution_readable": False,
        },
        "crash": {
            "present": 0,
            "absent": 261,
            "layers": {"not_run": 0, "material_absent": 0, "not_measurable": 0, "provisional_pool": 0, "measured": 0},
            "reasons": {},
            "value_nonnull": 0,
            "zero": 0,
            "nonzero": 0,
            "value": {"n": 0, "mean": None, "median": None, "min": None, "max": None},
            "pooled": {"n_unique": 0, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 0, "rate": None},
            "raw_present": 0,
            "raw_zero": 0,
            "raw_nonzero": 0,
            "raw_pooled": {"n_unique": 0, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 0, "rate": None},
            "floor_false": 0,
            "floor_provisional": 0,
            "floor_other": 0,
            "provisional_missing": 0,
            "evaluability": 0,
        },
    },
}


# ═══ 1. 键名与词表的单一事实源 ═══════════════════════════════════════════════


class TestKeyRegistry:
    def test_key_names_are_the_archive_keys(self) -> None:
        assert RISK_KEY == "risk_summary"
        assert CRASH_KEY == "mdo_crash_rate"

    def test_five_layers_are_ordered_from_unrun_to_readable(self) -> None:
        assert CRASH_LAYERS == (
            CRASH_NOT_RUN,
            CRASH_MATERIAL_ABSENT,
            CRASH_NOT_MEASURABLE,
            CRASH_PROVISIONAL,
            CRASH_MEASURED,
        )
        assert len(set(CRASH_LAYERS)) == 5

    def test_unmeasured_layers_are_the_three_without_a_canonical_value(self) -> None:
        assert CRASH_UNMEASURED_LAYERS == (CRASH_NOT_RUN, CRASH_MATERIAL_ABSENT, CRASH_NOT_MEASURABLE)
        assert CRASH_MEASURED not in CRASH_UNMEASURED_LAYERS
        assert CRASH_PROVISIONAL not in CRASH_UNMEASURED_LAYERS

    def test_placeholder_fields_are_the_three_judgment_columns(self) -> None:
        assert RISK_PLACEHOLDER_FIELDS == ("risk_level", "approval_action", "risk_score")
        assert RISK_PAUSE_KEY == "pause_requested"
        assert RISK_CONTRACT_STATUS_KEY == "contract_status"

    def test_evaluability_keys_are_mdo_prefixed(self) -> None:
        assert MDO_EVALUABILITY_KEYS == (
            "mdo_status",
            "mdo_evaluable",
            "mdo_non_terminating",
            "mdo_probe_invalid",
            "mdo_no_effective_pass",
        )
        assert all(key.startswith("mdo_") for key in MDO_EVALUABILITY_KEYS)

    def test_mdo_as_dict_emits_the_evaluability_keys(self) -> None:
        """分档口径的键必须由写入端产出，否则「归档 0 行在场」是另一回事。"""
        from src.measurement.mdo import MDOResult

        payload = MDOResult(
            available=True,
            pool_size=40,
            pool_floor_ok=True,
            mutant_trigger_rate=0.5,
            mutant_discrimination_rate=0.2,
            crash_rate=0.1,
            status="measured",
        ).as_dict()
        for key in MDO_EVALUABILITY_KEYS:
            assert key in payload, key

    def test_mdo_provisional_moves_raw_values_off_the_canonical_keys(self) -> None:
        from src.measurement.mdo import MDOResult

        payload = MDOResult(
            available=True,
            pool_size=2,
            pool_floor_ok=False,
            mutant_trigger_rate=1.0,
            mutant_discrimination_rate=1.0,
            crash_rate=0.0,
            status="provisional_pool",
        ).as_dict()
        assert payload["crash_rate"] is None
        assert payload["mtr"] is None and payload["mdr"] is None
        assert payload["mdo_provisional"] is True
        assert payload["mdo_raw"]["crash_rate"] == 0.0


# ═══ 2. 五层输入域：缺键 ≠ 未跑，字符串布尔不得用 bool() 折叠 ═══════════════════


class TestCrashLayer:
    def test_key_absence_is_not_a_layer(self) -> None:
        assert crash_layer({"task_id": "t1"}) is None

    def test_measured_needs_available_true_and_no_provisional_flag(self) -> None:
        assert crash_layer({CRASH_KEY: 0.0, "mdo_available": True}) == CRASH_MEASURED
        assert crash_layer({CRASH_KEY: 0.0, "mdo_available": True, "mdo_provisional": False}) == CRASH_MEASURED

    def test_provisional_flag_true_routes_to_provisional_pool(self) -> None:
        assert (
            crash_layer({CRASH_KEY: None, "mdo_available": True, "mdo_provisional": True, "mdo_raw": {}})
            == CRASH_PROVISIONAL
        )

    def test_available_false_is_not_measurable_regardless_of_reason(self) -> None:
        assert crash_layer({CRASH_KEY: None, "mdo_available": False}) == CRASH_NOT_MEASURABLE
        assert (
            crash_layer({CRASH_KEY: None, "mdo_available": False, "mdo_not_available_reason": "baseline_timeout"})
            == CRASH_NOT_MEASURABLE
        )

    def test_available_none_with_reason_is_material_absent(self) -> None:
        assert (
            crash_layer({CRASH_KEY: None, "mdo_available": None, "mdo_not_available_reason": "no_gold_material"})
            == CRASH_MATERIAL_ABSENT
        )

    @pytest.mark.parametrize("reason", [None, "", "   ", 0, False, [], {}])
    def test_available_none_without_a_usable_reason_is_not_run(self, reason: Any) -> None:
        assert (
            crash_layer({CRASH_KEY: None, "mdo_available": None, "mdo_not_available_reason": reason}) == CRASH_NOT_RUN
        )

    def test_missing_available_is_not_run_when_no_reason(self) -> None:
        assert crash_layer({CRASH_KEY: None}) == CRASH_NOT_RUN
        assert crash_layer({CRASH_KEY: None, "mdo_not_available_reason": "no_gold_material"}) == CRASH_MATERIAL_ABSENT

    @pytest.mark.parametrize("flag", ["True", "False", 1, 0])
    def test_string_and_int_booleans_are_not_identity_true(self, flag: Any) -> None:
        """`available` 用 `is True` 判定：字符串/整数不得折叠成布尔（BW 纪律）。"""
        assert crash_layer({CRASH_KEY: None, "mdo_available": flag}) == CRASH_NOT_RUN
        assert (
            crash_layer({CRASH_KEY: None, "mdo_available": flag, "mdo_not_available_reason": "r"})
            == CRASH_MATERIAL_ABSENT
        )

    def test_measured_requires_provisional_identity_true(self) -> None:
        assert crash_layer({CRASH_KEY: 0.0, "mdo_available": True, "mdo_provisional": "true"}) == CRASH_MEASURED

    @pytest.mark.parametrize(
        ("row", "want"),
        [
            ({CRASH_KEY: None, "mdo_available": None}, CRASH_NOT_RUN),
            (
                {CRASH_KEY: None, "mdo_available": None, "mdo_not_available_reason": "no_gold_material"},
                CRASH_MATERIAL_ABSENT,
            ),
            ({CRASH_KEY: None, "mdo_available": False, "mdo_not_available_reason": "x"}, CRASH_NOT_MEASURABLE),
            ({CRASH_KEY: None, "mdo_available": True, "mdo_provisional": True}, CRASH_PROVISIONAL),
            ({CRASH_KEY: 0.0, "mdo_available": True}, CRASH_MEASURED),
        ],
    )
    def test_every_key_present_row_lands_in_exactly_one_layer(self, row: dict, want: str) -> None:
        assert crash_layer(row) == want
        assert want in CRASH_LAYERS


# ═══ 3. `risk_summary` 分档 ═══════════════════════════════════════════════════


def _risk_rows() -> list[dict[str, Any]]:
    return [
        {"task_id": "absent"},
        {RISK_KEY: "not-a-dict"},
        {
            RISK_KEY: {
                "enabled": True,
                "risk_level": "medium",
                "approval_action": "human_confirm",
                "risk_score": 0.5,
                "pause_requested": True,
                RISK_CONTRACT_STATUS_KEY: "ok",
            }
        },
        {
            RISK_KEY: {
                "enabled": True,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                RISK_PAUSE_KEY: False,
            }
        },
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
                RISK_PAUSE_KEY: False,
            }
        },
        # 双重非空但只算一次 mismatch（每行一次，不按字段叠加）。
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": "low",
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": ["x"],
                RISK_PAUSE_KEY: False,
            }
        },
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {"confidence": 0.1},
                "reasons": [],
            }
        },
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": ["r"],
            }
        },
        {RISK_KEY: {"risk_level": None, "approval_action": None, "risk_score": None}},
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
                RISK_PAUSE_KEY: None,
            }
        },
        {
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
                RISK_CONTRACT_STATUS_KEY: None,
            }
        },
    ]


class TestRiskSummaryStats:
    def _stats(self) -> dict[str, Any]:
        return risk_summary_stats(_risk_rows())

    def test_presence_partition(self) -> None:
        out = self._stats()
        assert out["n_rows"] == 11
        assert out["n_key_present"] == 10
        assert out["n_key_absent"] == 1
        assert out["n_non_dict"] == 1

    def test_enabled_is_tri_state(self) -> None:
        out = self._stats()
        assert out["enabled"] == {"enabled_true": 2, "enabled_false": 6, "enabled_missing": 1}
        assert sum(out["enabled"].values()) == out["n_key_present"] - out["n_non_dict"]

    def test_placeholder_mismatch_counts_each_row_once(self) -> None:
        assert self._stats()["placeholder_mismatch"] == 3

    def test_disabled_placeholders_do_not_enter_level_or_score(self) -> None:
        out = self._stats()
        assert out["level"] == {"medium": 1, "None": 1}
        assert out["level_nonnull"] == 1
        assert out["action"] == {"human_confirm": 1, "None": 1}
        assert out["score"] == {"n": 1, "mean": 0.5, "median": 0.5, "min": 0.5, "max": 0.5}

    def test_enabled_without_a_level_is_disclosed(self) -> None:
        out = self._stats()
        assert out["n_enabled_unscored"] == 1
        assert out["level_nonnull"] + out["n_enabled_unscored"] == out["enabled"]["enabled_true"]

    def test_level_on_a_disabled_row_is_not_readable(self) -> None:
        """enabled=False 行残留的 level 只是写侧缺陷，不得计成「级别可读」。"""
        out = self._stats()
        assert out["placeholder_mismatch"] == 3
        assert out["level_nonnull"] == 1

    def test_pause_is_partitioned_including_non_boolean(self) -> None:
        out = self._stats()
        assert out["pause"] == {"true": 1, "false": 3, "absent": 4, "other": 1}
        assert sum(out["pause"].values()) == out["n_key_present"] - out["n_non_dict"]

    def test_contract_status_presence_is_not_truthiness(self) -> None:
        out = self._stats()
        assert out["contract_status"] == {"present": 2, "absent": 7}
        assert sum(out["contract_status"].values()) == out["n_key_present"] - out["n_non_dict"]

    def test_schema_shapes_are_key_level_and_sum_to_docs(self) -> None:
        out = self._stats()
        assert sum(out["schema_shapes"].values()) == out["n_key_present"] - out["n_non_dict"]
        assert (
            out["schema_shapes"]["approval_action|contract_status|enabled|pause_requested|risk_level|risk_score"] == 1
        )

    def test_distribution_is_unreadable_without_an_enabled_row(self) -> None:
        rows = [{"task_id": "t1", RISK_KEY: {"enabled": False, "risk_level": None}}]
        out = risk_summary_stats(rows)
        assert out["enabled"]["enabled_true"] == 0
        assert out["level_nonnull"] == 0
        assert out["distribution_readable"] is False

    def test_empty_input_returns_none_not_zero_for_score(self) -> None:
        out = risk_summary_stats([])
        assert out["n_rows"] == 0 and out["n_key_present"] == 0
        assert out["score"]["mean"] is None and out["score"]["n"] == 0
        assert out["distribution_readable"] is False

    def test_zero_score_is_a_real_value(self) -> None:
        rows = [{"task_id": "t1", RISK_KEY: {"enabled": True, "risk_level": "low", "risk_score": 0.0}}]
        out = risk_summary_stats(rows)
        assert out["score"]["n"] == 1 and out["score"]["mean"] == 0.0

    def test_key_absence_is_not_counted_as_disabled(self) -> None:
        out = risk_summary_stats([{"task_id": "t1"}, {"task_id": "t2"}])
        assert out["n_key_absent"] == 2
        assert out["enabled"]["enabled_false"] == 0


# ═══ 4. 值域与整数反推 ═════════════════════════════════════════════════════════


class TestValueAndPooling:
    def test_empty_value_summary_is_none_not_zero(self) -> None:
        assert _value_summary([]) == {"n": 0, "mean": None, "median": None, "min": None, "max": None}

    def test_value_summary_keeps_zero(self) -> None:
        out = _value_summary([0.0, 0.5])
        assert out == {"n": 2, "mean": 0.25, "median": 0.25, "min": 0.0, "max": 0.5}

    def test_reconstruction_returns_none_for_incomplete_inputs(self) -> None:
        assert _reconstruct_count(None, 10) is None
        assert _reconstruct_count(0.5, None) is None
        assert _reconstruct_count(0.5, 0) is None
        assert _reconstruct_count(0.5, -1) is None
        assert _reconstruct_count(0.5, "10") is None
        assert _reconstruct_count("0.5", 10) is None

    def test_booleans_are_not_pool_sizes_or_rates(self) -> None:
        assert _reconstruct_count(0.5, True) is None
        assert _reconstruct_count(True, 4) is None

    def test_unique_reconstruction(self) -> None:
        assert _reconstruct_count(0.25, 4) == [1]
        assert _reconstruct_count(0.0, 4) == [0]
        assert _reconstruct_count(1.0, 4) == [4]
        assert _reconstruct_count(0.3333, 3) == [1]

    def test_four_digit_rounding_can_be_ambiguous(self) -> None:
        """n=20000 时 1/2/3 个崩溃都四舍五入到 0.0001——不得替调用方选一个。"""
        assert _reconstruct_count(0.0001, 20000) == [1, 2, 3]

    def test_pooled_empty_is_none_not_zero(self) -> None:
        out = _pooled([])
        assert out == {"n_unique": 0, "n_ambiguous": 0, "n_failed": 0, "n_crash": 0, "n_pool": 0, "rate": None}

    def test_pooled_sums_integer_numerators_over_full_pools(self) -> None:
        out = _pooled([(0.0, 4), (0.25, 4)])
        assert out == {"n_unique": 2, "n_ambiguous": 0, "n_failed": 0, "n_crash": 1, "n_pool": 8, "rate": 0.125}

    def test_pooled_rate_is_exact_not_rounded(self) -> None:
        assert _pooled([(0.3333, 3)])["rate"] == 1 / 3

    def test_pooled_counts_failures_without_guessing(self) -> None:
        out = _pooled([(None, 4), (0.0, None)])
        assert out["n_failed"] == 2 and out["n_pool"] == 0 and out["rate"] is None

    def test_pooled_counts_ambiguity_without_guessing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rk_mod, "_reconstruct_count", lambda rate, size: [0, 1] if rate == 0.5 else [0])
        out = rk_mod._pooled([(0.5, 4), (0.0, 2)])
        assert out["n_ambiguous"] == 1
        assert out["n_unique"] == 1
        assert out["n_crash"] == 0
        assert out["n_pool"] == 2


# ═══ 5. `mdo_crash_rate` 分档、值域与两义键 ═════════════════════════════════════


def _crash_rows() -> list[dict[str, Any]]:
    return [
        {"task_id": "absent"},
        {CRASH_KEY: None, "mdo_available": None},
        {CRASH_KEY: None, "mdo_available": None, "mdo_not_available_reason": "no_gold_material"},
        {
            CRASH_KEY: None,
            "mdo_available": False,
            "mdo_not_available_reason": "test_not_green_on_base(rc=1)",
            "mdo_pool_floor_ok": False,
        },
        {
            CRASH_KEY: 0.0,
            "mdo_available": True,
            "mdo_pool_size": 4,
            "mdo_provisional": False,
            "mdo_pool_floor_ok": True,
            "mdo_status": "measured",
            "mdo_not_available_reason": "must_not_be_counted",
        },
        {
            CRASH_KEY: 0.25,
            "mdo_available": True,
            "mdo_pool_size": 4,
            "mdo_provisional": False,
            "mdo_pool_floor_ok": True,
            "mdo_evaluable": 4,
        },
        {
            CRASH_KEY: None,
            "mdo_available": True,
            "mdo_provisional": True,
            "mdo_pool_size": 2,
            "mdo_pool_floor_ok": False,
            "mdo_raw": {"crash_rate": 0.5},
        },
        {
            CRASH_KEY: None,
            "mdo_available": True,
            "mdo_provisional": True,
            "mdo_pool_size": 2,
            "mdo_pool_floor_ok": False,
        },
        {CRASH_KEY: None, "mdo_available": True, "mdo_pool_size": 4, "mdo_pool_floor_ok": True},
        {CRASH_KEY: None, "mdo_available": None, "mdo_pool_floor_ok": False},
    ]


class TestMdoCrashStats:
    def _stats(self) -> dict[str, Any]:
        return mdo_crash_stats(_crash_rows())

    def test_presence_partition(self) -> None:
        out = self._stats()
        assert out["n_rows"] == 10
        assert out["n_key_present"] == 9
        assert out["n_key_absent"] == 1

    def test_layers_partition_the_key_present_rows(self) -> None:
        out = self._stats()
        assert out["layers"] == {
            "not_run": 2,
            "material_absent": 1,
            "not_measurable": 1,
            "provisional_pool": 2,
            "measured": 3,
        }
        assert sum(out["layers"].values()) == out["n_key_present"]

    def test_reasons_cover_exactly_the_unmeasured_layers(self) -> None:
        out = self._stats()
        assert out["unmeasured_reasons"] == {
            "<none>": 2,
            "no_gold_material": 1,
            "test_not_green_on_base(rc=1)": 1,
        }
        assert sum(out["unmeasured_reasons"].values()) == sum(out["layers"][layer] for layer in CRASH_UNMEASURED_LAYERS)

    def test_measured_reason_is_not_counted(self) -> None:
        assert "must_not_be_counted" not in self._stats()["unmeasured_reasons"]

    def test_none_is_not_zero(self) -> None:
        out = self._stats()
        assert out["n_value_nonnull"] == 2
        assert out["n_value_null"] == 7
        assert out["n_zero"] == 1
        assert out["n_nonzero"] == 1
        assert out["value"] == {"n": 2, "mean": 0.125, "median": 0.125, "min": 0.0, "max": 0.25}

    def test_measured_layer_with_a_null_value_is_not_counted_as_value(self) -> None:
        out = self._stats()
        assert out["layers"]["measured"] == 3
        assert out["n_value_nonnull"] == 2

    def test_pooled_uses_the_full_pool_of_value_rows(self) -> None:
        pooled = self._stats()["pooled"]
        assert pooled == {"n_unique": 2, "n_ambiguous": 0, "n_failed": 0, "n_crash": 1, "n_pool": 8, "rate": 0.125}

    def test_provisional_raw_is_separate_from_measured(self) -> None:
        raw = self._stats()["provisional_raw"]
        assert raw["n_present"] == 1
        assert raw["n_missing"] == 1
        assert raw["n_zero"] == 0 and raw["n_nonzero"] == 1
        assert raw["pooled"]["n_crash"] == 1 and raw["pooled"]["n_pool"] == 2

    def test_floor_false_is_a_two_meaning_key(self) -> None:
        out = self._stats()
        assert out["floor_false"] == 4
        assert out["floor_false_provisional"] == 2
        assert out["floor_false_other"] == 2
        assert out["floor_false"] == out["floor_false_provisional"] + out["floor_false_other"]

    def test_provisional_flag_missing_counts_absence_not_false(self) -> None:
        assert self._stats()["provisional_flag_missing"] == 5

    def test_evaluability_is_recorded_when_any_key_is_present(self) -> None:
        out = self._stats()
        assert out["n_evaluability_recorded"] == 2
        assert out["evaluability_keys"] == list(MDO_EVALUABILITY_KEYS)

    def test_empty_input_returns_null_pool_rate(self) -> None:
        out = mdo_crash_stats([])
        assert out["n_rows"] == 0
        assert out["pooled"]["rate"] is None
        assert out["value"]["mean"] is None
        assert sum(out["layers"].values()) == 0

    def test_key_absence_is_not_not_run(self) -> None:
        out = mdo_crash_stats([{"task_id": "t1"}])
        assert out["n_key_absent"] == 1
        assert out["layers"]["not_run"] == 0

    def test_residual_keys_stats_wraps_both_readings(self) -> None:
        out = residual_keys_stats(_crash_rows())
        assert out["n_rows"] == 10
        assert out["risk_summary"]["n_key_present"] == 0
        assert out["mdo_crash"]["n_key_present"] == 9


# ═══ 6. 报告面 ═════════════════════════════════════════════════════════════════


def _fixture_rows() -> list[dict[str, Any]]:
    return [
        {"task_id": "t1", "passed": True},
        {
            "task_id": "t2",
            "passed": False,
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
                RISK_PAUSE_KEY: False,
            },
            "mdo_available": None,
            CRASH_KEY: None,
        },
        {
            "task_id": "t3",
            "passed": True,
            RISK_KEY: {
                "enabled": True,
                "risk_level": "medium",
                "approval_action": "human_confirm",
                "risk_score": 0.5,
                "factors": {"confidence": 0.1},
                "reasons": ["r"],
                RISK_PAUSE_KEY: True,
                RISK_CONTRACT_STATUS_KEY: "ok",
                "extra": 1,
            },
            "mdo_available": True,
            CRASH_KEY: 0.0,
            "mdo_pool_size": 4,
            "mdo_provisional": False,
            "mdo_pool_floor_ok": True,
        },
        {
            "task_id": "t4",
            "passed": False,
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
            },
            "mdo_available": True,
            CRASH_KEY: None,
            "mdo_pool_size": 2,
            "mdo_provisional": True,
            "mdo_pool_floor_ok": False,
            "mdo_raw": {"crash_rate": 0.5},
            "mdo_status": "provisional_pool",
        },
        {
            "task_id": "t5",
            "passed": True,
            RISK_KEY: {
                "enabled": False,
                "risk_level": None,
                "approval_action": None,
                "risk_score": None,
                "factors": {},
                "reasons": [],
                RISK_PAUSE_KEY: False,
            },
            "mdo_available": False,
            CRASH_KEY: None,
            "mdo_pool_size": 0,
            "mdo_pool_floor_ok": False,
            "mdo_not_available_reason": "test_not_green_on_base(rc=1)",
        },
    ]


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
                        "success_rate": 60.0,
                        "avg_coverage": 0.3,
                        "avg_iterations": 1.0,
                        "avg_elapsed_seconds": 1.0,
                        "total_time": 5.0,
                    }
                },
            }
        )

    def _md(self) -> str:
        return ar_mod.render_markdown(self._analysis(_fixture_rows()), "demo.json")

    def test_build_analysis_exposes_the_new_key(self) -> None:
        per = self._analysis(_fixture_rows())["per_baseline"]["aitester"]
        assert per["residual_keys"]["risk_summary"]["n_key_present"] == 4
        assert per["residual_keys"]["mdo_crash"]["layers"]["provisional_pool"] == 1

    def test_new_reader_moves_no_existing_judgment_value(self) -> None:
        with_keys = self._analysis(_fixture_rows())["per_baseline"]["aitester"]
        stripped = [{k: v for k, v in row.items() if k not in {RISK_KEY, CRASH_KEY}} for row in _fixture_rows()]
        base = self._analysis(stripped)["per_baseline"]["aitester"]
        for key in ("total_functions", "passed_count", "success_rate", "avg_coverage", "avg_iterations"):
            assert with_keys[key] == base[key], key

    def test_risk_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 5 | 4 | 1 | 1 | 3 | 2 | 1 | 1 | 1 | 2 | 1 | 1 |" in md
        assert "| **合计** | 5 | 4 | 1 | 1 | 3 | 2 | 1 | 1 | 1 | 2 | 1 | 1 |" in md

    def test_crash_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 5 | 1 | 0 | 1 | 1 | 1 | 1 | 1 | 0 | 2 | 1 | 0.00% | 0.00% |" in md
        assert "| **合计** | 5 | 1 | 0 | 1 | 1 | 1 | 1 | 1 | 0 | 2 | 1 | 0.00% | 0.00% |" in md

    def test_both_tables_have_consistent_cell_counts(self) -> None:
        lines = self._md().splitlines()
        heading = "## 写而不读键池的收口（BX：`risk_summary` 与 `mdo_crash_rate` 的读侧）"
        tables: list[list[str]] = [[]]
        for line in lines[lines.index(heading) + 1 :]:
            if line.startswith("## "):
                break
            if line.startswith("|"):
                tables[-1].append(line)
            elif tables[-1]:
                tables.append([])
        tables = [t for t in tables if t]
        assert [[len(ln.split("|")) - 2 for ln in t] for t in tables] == [[13, 13, 13, 13], [14, 14, 14, 14]]

    def test_disabled_placeholder_is_not_low_risk(self) -> None:
        md = self._md()
        assert "`enabled=False` 是**通道关闭**的占位" in md
        assert "**`level=None` 不是 `low`**" in md
        assert "`pause_requested=False` 也不是「判定无需暂停」" in md

    def test_key_absence_is_not_low_risk(self) -> None:
        md = self._md()
        assert "键缺席 1 行（早于该键落盘）不等于低风险" in md

    def test_contract_status_absence_is_disclosed(self) -> None:
        md = self._md()
        assert "`contract_status`（BL 起才写入）在 4 行在场记录里 1 行出现" in md
        assert "「缺失符号为空可不可信」在归档上无证据" in md

    def test_risk_levels_are_ordinal_not_probabilities(self) -> None:
        md = self._md()
        assert "NIST SP 800-30" in md
        assert "不是概率" in md

    def test_five_layers_are_disclosed(self) -> None:
        md = self._md()
        assert "未跑 1 / 材料缺 0" in md
        assert "不可测 1 / 暂定池 1 / 实测 1，合计 = 键在场 4" in md
        assert "键缺席 1（早于 MDO 落盘）" in md

    def test_unmeasured_reasons_are_listed(self) -> None:
        md = self._md()
        assert "`<none>` 1、`test_not_green_on_base(rc=1)` 1" in md

    def test_floor_false_two_meaning_is_disclosed(self) -> None:
        md = self._md()
        assert "`mdo_pool_floor_ok=False` 是**两义键**" in md
        assert "2 行 = 暂定池 1 + 不可测 1" in md
        assert "**不是池不足**" in md

    def test_denominator_caliber_is_disclosed(self) -> None:
        md = self._md()
        assert "crash 率 = `crashed / 全池 n`" in md
        assert "与 MTR/MDR 的**可评估**分母不同" in md
        assert "可评估分母**无法从归档复算**" in md
        assert "crash 率不得与 MDR 相除或相减" in md

    def test_value_domain_none_is_not_zero(self) -> None:
        md = self._md()
        assert "**`None` 不是 0**" in md
        assert "`0.0` 1 行 = 实测零崩溃" in md
        assert "空 3 行 = 未测或被出口拦截" in md

    def test_two_calibers_of_crash_rate_are_kept_apart(self) -> None:
        md = self._md()
        assert "与池化 0/4 = 0.00% 是两个口径" in md
        assert "暂定池 1 行的原始值在 `mdo_raw`" in md
        assert "**不与实测合并**" in md

    def test_reconstruction_is_disclosed(self) -> None:
        md = self._md()
        assert "round(c/n,4)==rate" in md
        assert "歧义 0 行 / 失败 0 行" in md

    def test_external_calibers_are_named(self) -> None:
        md = self._md()
        assert "Google Play `vitals.crashrate`" in md
        assert "per-session vs per-request" in md
        assert "crash 率必须带分母" in md

    def test_section_absent_when_no_rows(self) -> None:
        md = ar_mod.render_markdown(self._analysis([]), "demo.json")
        assert "## 写而不读键池的收口" not in md

    def test_ratio_helper_prints_two_decimals_and_dash(self) -> None:
        assert ar_mod._ratio_text2(15, 3200) == "0.47%"
        assert ar_mod._ratio_text2(0, 3) == "0.00%"
        assert ar_mod._ratio_text2(1, 0) == "—"


# ═══ 7. 批次摘要接线（run_main_batch） ═════════════════════════════════════════


class TestSummaryLine:
    @staticmethod
    def _write_batch(tmp_path: Path, rows: list[dict]) -> Path:
        payload = {
            "dataset": "demo",
            "results": {
                "aitester": {
                    "details": rows,
                    "success_rate": 60.0,
                    "effective_total": len(rows),
                    "harness_invalid_count": 0,
                }
            },
        }
        path = tmp_path / "benchmark_demo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_summary_prints_the_residual_pool(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import experiments.run_main_batch as main_mod

        main_mod._print_r4_summary(self._write_batch(tmp_path, _fixture_rows()))
        out = capsys.readouterr().out
        assert "BX 残池: risk 通道开启 1/4" in out
        assert "键缺席 1，level 可读 1" in out
        assert "mdo_crash 实测 1（值 1、零 1，池化 0/4 = 0.00%）" in out
        assert "＋暂定池 1（raw 1）" in out
        assert "未跑 1 / 材料缺 0 / 不可测 1；键缺席 1" in out

    def test_summary_omits_the_line_without_rows(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import experiments.run_main_batch as main_mod

        main_mod._print_r4_summary(self._write_batch(tmp_path, []))
        assert "BX 残池" not in capsys.readouterr().out

    def test_summary_reports_key_absence_not_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import experiments.run_main_batch as main_mod

        main_mod._print_r4_summary(self._write_batch(tmp_path, [{"task_id": "t1"}]))
        out = capsys.readouterr().out
        assert "risk 通道开启 0/0" in out
        assert "mdo_crash 实测 0" in out
        assert "键缺席 1" in out


# ═══ 8. 具名冻结批次（逐档读数由普查工具 C 段同源复核） ═════════════════════════


def _reading(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = residual_keys_stats(rows)
    r, c = out["risk_summary"], out["mdo_crash"]
    return {
        "n_rows": out["n_rows"],
        "risk": {
            "present": r["n_key_present"],
            "absent": r["n_key_absent"],
            "enabled_true": r["enabled"]["enabled_true"],
            "enabled_false": r["enabled"]["enabled_false"],
            "enabled_missing": r["enabled"]["enabled_missing"],
            "shapes": r["schema_shapes"],
            "level_nonnull": r["level_nonnull"],
            "level": r["level"],
            "action": r["action"],
            "score": r["score"],
            "pause": r["pause"],
            "contract_status": r["contract_status"],
            "placeholder_mismatch": r["placeholder_mismatch"],
            "distribution_readable": r["distribution_readable"],
        },
        "crash": {
            "present": c["n_key_present"],
            "absent": c["n_key_absent"],
            "layers": c["layers"],
            "reasons": c["unmeasured_reasons"],
            "value_nonnull": c["n_value_nonnull"],
            "zero": c["n_zero"],
            "nonzero": c["n_nonzero"],
            "value": c["value"],
            "pooled": c["pooled"],
            "raw_present": c["provisional_raw"]["n_present"],
            "raw_zero": c["provisional_raw"]["n_zero"],
            "raw_nonzero": c["provisional_raw"]["n_nonzero"],
            "raw_pooled": c["provisional_raw"]["pooled"],
            "floor_false": c["floor_false"],
            "floor_provisional": c["floor_false_provisional"],
            "floor_other": c["floor_false_other"],
            "provisional_missing": c["provisional_flag_missing"],
            "evaluability": c["n_evaluability_recorded"],
        },
    }


@pytest.mark.parametrize("rel", sorted(PINNED_BATCHES))
def test_pinned_batch_reads_as_registered(rel: str) -> None:
    path = ROOT / rel
    assert path.exists(), rel
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        r
        for blk in (doc.get("results") or {}).values()
        for r in (blk or {}).get("details") or []
        if isinstance(r, dict)
    ]
    assert _reading(rows) == PINNED_BATCHES[rel], rel


def test_absent_key_batch_is_not_a_zero_readout() -> None:
    rel = "experiments/results/main_batch/benchmark_synthetic_20261007_185941.json"
    pinned = PINNED_BATCHES[rel]["crash"]
    assert pinned["present"] == 0 and pinned["absent"] == 261
    assert pinned["pooled"]["rate"] is None


def test_pinned_batches_show_zero_enabled_and_zero_contract_status() -> None:
    for rel, pinned in PINNED_BATCHES.items():
        assert pinned["risk"]["enabled_true"] == 0, rel
        assert pinned["risk"]["contract_status"]["present"] == 0, rel
        assert pinned["risk"]["distribution_readable"] is False, rel
        assert pinned["crash"]["evaluability"] == 0, rel


def test_census_tool_reads_the_same_pinned_batches() -> None:
    """普查工具的 C 段从本文件的 `PINNED_BATCHES` 解析读数，防止两边漂移。"""
    tool = ROOT / "scripts" / "tools" / "bx_residual_keys_census.py"
    source = tool.read_text(encoding="utf-8")
    assert "PINNED_BATCHES" in source
    assert "tests/test_residual_keys_bx.py" in source
    assert "ast.literal_eval" in source
    tree = ast.parse(source)
    assert any(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))


# ═══ 9. 接线与写入端形状锁 ═════════════════════════════════════════════════════


class TestWiringLocks:
    def test_statistical_analysis_reexports_the_same_reader(self) -> None:
        assert sa_residual_keys_stats([]) == residual_keys_stats([])
        assert sa_residual_keys_stats(_fixture_rows()) == residual_keys_stats(_fixture_rows())

    def test_run_main_batch_imports_the_reader(self) -> None:
        source = (ROOT / "experiments" / "run_main_batch.py").read_text(encoding="utf-8")
        assert "residual_keys_stats" in source
        assert "BX 残池" in source

    def test_analyze_results_wires_the_reader_per_baseline(self) -> None:
        source = (ROOT / "experiments" / "analyze_results.py").read_text(encoding="utf-8")
        assert '"residual_keys": _residual_keys(details)' in source
        assert "写而不读键池的收口" in source

    def test_risk_writer_disabled_branch_is_the_placeholder_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.graph.risk_approval import build_risk_summary

        monkeypatch.delenv("RISK_APPROVAL_ENABLE", raising=False)
        out = build_risk_summary(
            confidence=0.9,
            changed_lines=1,
            changed_files=1,
            contract_missing_symbols=[],
            full_file_patch=False,
            budget_ratio=None,
            budget_exceeded=None,
            contract_status="ok",
        )
        assert out["enabled"] is False
        assert out["risk_level"] is None and out["approval_action"] is None and out["risk_score"] is None
        assert out["pause_requested"] is False
        assert out["contract_status"] == "ok"

    def test_risk_writer_enabled_branch_can_request_pause(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.graph.risk_approval import build_risk_summary

        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        out = build_risk_summary(
            confidence=0.1,
            changed_lines=500,
            changed_files=9,
            contract_missing_symbols=["Rule_L101"],
            full_file_patch=True,
            budget_ratio=None,
            budget_exceeded=None,
            contract_status="ok",
        )
        assert out["enabled"] is True
        assert out["risk_level"] == "high"
        assert out["approval_action"] == "force_review"
        assert out["pause_requested"] is True
        assert out["contract_status"] == "ok"

    def test_two_keys_are_the_only_remaining_pool_members(self) -> None:
        """BX 之后池应为空：普查工具 A 段会断言之，这里锁住它读的是哪两个键。"""
        tool = (ROOT / "scripts" / "tools" / "bx_residual_keys_census.py").read_text(encoding="utf-8")
        assert "risk_summary" in tool and "mdo_crash_rate" in tool
        assert "12908" in tool and "76488" in tool
