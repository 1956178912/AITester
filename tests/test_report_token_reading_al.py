"""AL 回归锁：报告 §4.1 的行级 token 读取与检出分母（2026-10-21）。

缺陷族（`experiments/emse_stats_report.cost_effectiveness_block`）：
1. `usage.get("input_tokens") or 0` / `output_tokens` 把缺席、null、`"100"`、`True`、
   负数、`nan`/`inf` 折成可计价数字——同一个坏行在 ext（AI 值域）读不动，在 §4.1 却
   编出金额；
2. `token_usage` 非对象的行在检出计数**之前**被 `continue`，检出分母随记账好坏缩水；
3. 正 token 行无 `by_model` 归因、拆分与总量矛盾、`by_model` 求和与 total 不符时，
   金额要么静默漏行、要么拿矛盾数字计价；
4. 缓存命中解释的零消耗行被计入 AK 的"零记账下界"，违反 AK 边界⑥。

处置：行级三元组改走共享 `src.budget.token_usage.row_token_counts`；读不动 ⇒
`total_tokens` / `total_usd` / 两个比值一律 `None` + 机制名；拆分/归因不一致 ⇒ 只废金额；
检出计数与 token 可读性解耦；缓存证据零行不计入下界。真批次 783 行全部干净，
三臂读数与返回域逐位不变（本文末节直接读入库工件复算）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import emse_stats_report as rep

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]

_PRICES: dict[str, dict[str, Any]] = {
    "m1": {
        "input_per_mtok": 1.0,
        "output_per_mtok": 2.0,
        "currency": "USD",
        "source": "test",
        "as_of": "2026-10-21",
    }
}

_LEGACY_EFF_KEYS = {
    "total_tokens",
    "n_rows_with_tokens_positive",
    "n_priced_rows",
    "n_unpriceable_rows",
    "total_usd",
    "n_detections",
    "n_detection_measurable",
    "usd_per_detection",
    "tokens_per_detection",
}

_MISSING = object()


def _usage(
    total: Any = 2_000_000,
    *,
    inp: Any = 1_000_000,
    out: Any = 1_000_000,
    by_model: Any = _MISSING,
) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "total_tokens": total,
        "input_tokens": inp,
        "output_tokens": out,
        "llm_calls": 1,
    }
    usage["by_model"] = {"m1": total} if by_model is _MISSING else by_model
    return usage


def _row(usage: Any = _MISSING, *, detection: float | None = 1.0, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": "t", "detection_rate": detection, **extra}
    if usage is not _MISSING:
        row["token_usage"] = usage
    return row


def _eff(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rep.cost_effectiveness_block(rows, _PRICES)


def _main_batch_rows() -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in _MAIN_BATCH_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for arm, block in data["results"].items():
            merged.setdefault(arm, []).extend(block["details"])
    return merged


# ─── 1. 三元组读不动：不给部分和（改前 `or 0` 折成可计价 0） ────────────────────
class TestUnreadableTriple:
    @pytest.mark.parametrize(
        ("usage", "code"),
        [
            ({}, "token_field_absent:total_tokens"),
            (
                {"total_tokens": "100", "input_tokens": 100, "output_tokens": 0},
                "token_not_count:total_tokens:str",
            ),
            (
                {"total_tokens": True, "input_tokens": 100, "output_tokens": 0},
                "token_not_count:total_tokens:bool",
            ),
            (
                {"total_tokens": 100.5, "input_tokens": 100, "output_tokens": 0},
                "token_not_count:total_tokens:float",
            ),
            (
                {"total_tokens": float("nan"), "input_tokens": 100, "output_tokens": 0},
                "token_not_finite:total_tokens",
            ),
            (
                {"total_tokens": float("inf"), "input_tokens": 100, "output_tokens": 0},
                "token_not_finite:total_tokens",
            ),
            (
                {"total_tokens": -1, "input_tokens": 100, "output_tokens": 0},
                "token_negative:total_tokens",
            ),
            (
                {"total_tokens": 100, "input_tokens": "100", "output_tokens": 0},
                "token_not_count:input_tokens:str",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100},
                "token_field_absent:output_tokens",
            ),
        ],
    )
    def test_no_totals_and_no_ratios_without_a_readable_triple(self, usage: dict[str, Any], code: str) -> None:
        out = _eff([_row(usage)])
        assert out["total_tokens"] is None
        assert out["total_usd"] is None
        assert out["usd_per_detection"] is None
        assert out["tokens_per_detection"] is None
        assert out["n_token_unreadable_rows"] == 1
        assert out["n_priced_rows"] == 0
        assert out["token_reading_reasons"][code] == 1

    def test_all_missing_fields_are_named_not_collapsed(self) -> None:
        out = _eff([_row({})])
        assert out["token_reading_reasons"] == {
            "token_field_absent:input_tokens": 1,
            "token_field_absent:output_tokens": 1,
            "token_field_absent:total_tokens": 1,
        }

    def test_absent_token_usage_is_not_zero(self) -> None:
        out = _eff([_row()])
        assert out["total_tokens"] is None and out["total_usd"] is None
        assert out["token_reading_reasons"] == {"token_usage_absent": 1}

    @pytest.mark.parametrize(("usage", "type_name"), [(None, "NoneType"), (["x"], "list"), ("x", "str")])
    def test_non_object_token_usage_is_named(self, usage: Any, type_name: str) -> None:
        out = _eff([_row(usage)])
        assert out["total_tokens"] is None
        assert out["token_reading_reasons"] == {f"token_usage_not_object:{type_name}": 1}

    def test_one_bad_row_poisons_the_aggregate_not_the_priced_rows(self) -> None:
        out = _eff([_row(_usage()), _row({"total_tokens": "100", "input_tokens": 100, "output_tokens": 0})])
        assert out["n_priced_rows"] == 1
        assert out["n_token_unreadable_rows"] == 1
        assert out["total_tokens"] is None and out["total_usd"] is None

    def test_reading_key_absent_when_every_row_is_readable(self) -> None:
        out = _eff([_row(_usage())])
        assert "n_token_unreadable_rows" not in out
        assert "token_reading_reasons" not in out


# ─── 2. 检出分母与 token 可读性解耦（改前非对象 usage 在计数前被 continue） ─────
class TestDetectionDenominator:
    def test_row_without_token_usage_still_counts_into_detection(self) -> None:
        out = _eff([_row(detection=1.0), _row(_usage(), detection=0.0)])
        assert (out["n_detections"], out["n_detection_measurable"]) == (1, 2)
        assert out["tokens_per_detection"] is None, "分母在、分子不可读 ⇒ 不给 0"

    def test_bad_token_value_does_not_shrink_the_detection_denominator(self) -> None:
        out = _eff([_row({"total_tokens": -1}, detection=1.0), _row(_usage(), detection=1.0)])
        assert (out["n_detections"], out["n_detection_measurable"]) == (2, 2)

    def test_none_detection_stays_out_of_the_denominator(self) -> None:
        out = _eff([_row(_usage(), detection=None)])
        assert (out["n_detections"], out["n_detection_measurable"]) == (0, 0)

    def test_non_object_usage_row_is_not_a_free_skip(self) -> None:
        """改前：token_usage 为 None 的行在检出计数前 continue ⇒ 分母少 1。"""
        out = _eff([_row(None, detection=1.0)])
        assert out["n_detection_measurable"] == 1
        assert out["n_detections"] == 1


# ─── 3. 金额归因不一致：token 总量仍可读，金额不拿局部和冒充全额 ────────────────
class TestMoneyBlocked:
    @pytest.mark.parametrize(
        ("usage", "code"),
        [
            (
                {"total_tokens": 100, "input_tokens": 60, "output_tokens": 60, "by_model": {"m1": 100}},
                "token_split_mismatch",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0},
                "token_field_absent:by_model",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": None},
                "by_model_not_object:NoneType",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": "m1"},
                "by_model_not_object:str",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {}},
                "by_model_empty",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {1: 100}},
                "by_model_key_not_str:int",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": -1}},
                "token_negative:by_model:m1",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": "100"}},
                "token_not_count:by_model:m1:str",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": True}},
                "token_not_count:by_model:m1:bool",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": 1.5}},
                "token_not_count:by_model:m1:float",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": float("nan")}},
                "token_not_finite:by_model:m1",
            ),
            (
                {"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {"m1": 50}},
                "by_model_sum_mismatch",
            ),
            (
                {
                    "total_tokens": 100,
                    "input_tokens": 100,
                    "output_tokens": 0,
                    "by_model": {"a": 60, "b": 30},
                },
                "by_model_sum_mismatch",
            ),
        ],
    )
    def test_tokens_stay_readable_but_money_is_withheld(self, usage: dict[str, Any], code: str) -> None:
        out = _eff([_row(usage)])
        assert out["total_tokens"] == 100.0
        assert out["tokens_per_detection"] == 100.0
        assert out["total_usd"] is None
        assert out["usd_per_detection"] is None
        assert out["n_token_money_blocked_rows"] == 1
        assert out["token_money_reasons"] == {code: 1}
        assert out["n_priced_rows"] == 0

    def test_blocked_row_does_not_become_a_partial_sum(self) -> None:
        rows = [_row(_usage()), _row({"total_tokens": 100, "input_tokens": 60, "output_tokens": 60})]
        out = _eff(rows)
        assert out["n_priced_rows"] == 1
        assert out["total_tokens"] == 2_000_100.0
        assert out["total_usd"] is None, "3.0 只是可计价行的局部和，不能冒充总额"
        assert out["tokens_per_detection"] == 1_000_050.0

    def test_multi_model_row_with_matching_sum_is_unpriceable_not_blocked(self) -> None:
        usage = {"total_tokens": 100, "input_tokens": 50, "output_tokens": 50, "by_model": {"a": 50, "b": 50}}
        out = _eff([_row(usage)])
        assert out["n_unpriceable_rows"] == 1
        assert out["n_unpriceable_reasons"] == {"multi_model_row": 1}
        assert out["total_usd"] == 0.0
        assert "n_token_money_blocked_rows" not in out

    def test_unregistered_model_stays_an_unpriceable_row_not_a_block(self) -> None:
        out = _eff([_row(_usage(by_model={"mystery": 2_000_000}))])
        assert out["n_unpriceable_reasons"] == {"model_unregistered": 1}
        assert out["total_usd"] == 0.0
        assert "n_token_money_blocked_rows" not in out

    def test_priced_and_blocked_rows_keep_separate_counters(self) -> None:
        rows = [
            _row(_usage()),
            _row({"total_tokens": 100, "input_tokens": 100, "output_tokens": 0, "by_model": {}}),
        ]
        out = _eff(rows)
        assert out["n_priced_rows"] == 1
        assert out["n_token_money_blocked_rows"] == 1
        assert out["n_rows_with_tokens_positive"] == 1, "该键沿用 AB 口径（计价 + 不可计价）"

    def test_mechanism_key_absent_when_attribution_is_consistent(self) -> None:
        out = _eff([_row(_usage())])
        assert "n_token_money_blocked_rows" not in out
        assert "token_money_reasons" not in out


# ─── 4. AK 零行下界与缓存证据的边界（AK 边界⑥） ───────────────────────────────
class TestZeroRowCaliber:
    def test_explicit_zero_row_is_counted_and_costs_zero(self) -> None:
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "llm_calls": 0, "by_model": {}}
        out = _eff([_row(zero, generated_test="def test_x(): pass")])
        assert out["n_zero_token_rows"] == 1
        assert out["n_zero_token_output_rows"] == 1
        assert out["total_tokens"] == 0.0
        assert out["total_usd"] == 0.0
        assert "n_token_money_blocked_rows" not in out, "零 token 行无需归因"

    def test_cache_explained_zero_is_not_a_lower_bound_row(self) -> None:
        zero = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_calls": 0,
            "by_model": {},
            "cache_hits": 1,
            "cache_avoided_tokens": 1748,
        }
        out = _eff([_row(zero, generated_test="def test_x(): pass")])
        assert "n_zero_token_rows" not in out, "命中解释的真实 0 不是记账缺口"
        assert out["cache_hits"] == 1 and out["cache_avoided_tokens"] == 1748
        assert out["total_usd"] == 0.0

    def test_cache_fields_present_without_hits_stay_a_zero_row(self) -> None:
        zero = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
            "cache_hits": 0,
            "cache_avoided_tokens": 0,
        }
        out = _eff([_row(zero)])
        assert out["n_zero_token_rows"] == 1

    def test_invalid_cache_value_is_not_positive_evidence(self) -> None:
        zero = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
            "cache_hits": -1,
            "cache_avoided_tokens": 0,
        }
        out = _eff([_row(zero)])
        assert out["n_zero_token_rows"] == 1, "坏缓存值不得被读成'有缓存'"
        assert out["cache_hits"] is None
        assert "token_negative:cache_hits" in out["cache_reading_reasons"]

    def test_zero_row_subset_requires_generated_test(self) -> None:
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}
        out = _eff([_row(zero), _row(zero, generated_test="   ")])
        assert out["n_zero_token_rows"] == 2
        assert "n_zero_token_output_rows" not in out


# ─── 5. 干净批次：读数与返回域不变 ─────────────────────────────────────────────
class TestCleanBatchDomain:
    def test_clean_row_readings_are_exact(self) -> None:
        out = _eff([_row(_usage())])
        assert out["total_tokens"] == 2_000_000.0
        assert out["total_usd"] == pytest.approx(3.0)
        assert out["usd_per_detection"] == pytest.approx(3.0)
        assert out["tokens_per_detection"] == 2_000_000.0
        assert out["n_priced_rows"] == 1
        assert out["n_rows_with_tokens_positive"] == 1

    def test_clean_return_domain_is_the_legacy_key_set(self) -> None:
        out = _eff([_row(_usage())])
        assert set(out) == _LEGACY_EFF_KEYS

    def test_explicit_zero_row_keeps_legacy_zero_reading(self) -> None:
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "llm_calls": 0, "by_model": {}}
        out = _eff([_row(zero, detection=0.0)])
        assert out["total_tokens"] == 0.0
        assert out["total_usd"] == 0.0
        assert set(out) == _LEGACY_EFF_KEYS | {"n_zero_token_rows"}


# ─── 6. 真批次：783 行全干净，三臂读数逐位不变 ────────────────────────────────
class TestRealBatchReadings:
    @classmethod
    def setup_class(cls) -> None:
        cls.rows = _main_batch_rows()
        # 真路径：省略 price_table ⇒ 读仓内真表（与报告调用一致）。
        cls.blocks = {arm: rep.cost_effectiveness_block(rows) for arm, rows in cls.rows.items()}

    def test_every_arm_has_no_al_reading_keys(self) -> None:
        for arm, out in self.blocks.items():
            assert "n_token_unreadable_rows" not in out, arm
            assert "n_token_money_blocked_rows" not in out, arm

    def test_priced_readings_are_bit_identical(self) -> None:
        expected = {
            "aitester": (6.755979, 261),
            "plain_llm": (0.876692, 261),
            "plain_llm_df": (1.185783, 226),
        }
        for arm, (usd, n_priced) in expected.items():
            out = self.blocks[arm]
            assert out["total_usd"] == usd, arm
            assert out["n_priced_rows"] == n_priced, arm

    def test_detection_denominator_is_recomputable_from_rows(self) -> None:
        for arm, rows in self.rows.items():
            det = sum(1 for r in rows if r.get("detection_rate") is not None)
            hits = sum(1 for r in rows if r.get("detection_rate") == 1.0)
            out = self.blocks[arm]
            assert (out["n_detections"], out["n_detection_measurable"]) == (hits, det), arm

    def test_token_total_is_recomputable_from_rows(self) -> None:
        for arm, rows in self.rows.items():
            total = sum(r["token_usage"]["total_tokens"] for r in rows)
            assert self.blocks[arm]["total_tokens"] == pytest.approx(total), arm

    def test_pooled_zero_rows_are_35_and_all_have_output(self) -> None:
        for arm in ("aitester", "plain_llm"):
            assert "n_zero_token_rows" not in self.blocks[arm], arm
        out = self.blocks["plain_llm_df"]
        assert out["n_zero_token_rows"] == 35
        assert out["n_zero_token_output_rows"] == 35


# ─── 7. 呈现：None ⇒ `—`，AL 机制只在真发生时落行 ──────────────────────────────
def _arms_data(rows_by_arm: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {arm: {"cost": rep.cost_block(rows), "cost_eff": _eff(rows)} for arm, rows in rows_by_arm.items()}


class TestRendering:
    def test_unreadable_tokens_render_dashes_not_zero(self) -> None:
        text = "\n".join(rep._render_cost_section(_arms_data({"a": [_row()]})))
        assert "| `a` | 1/1 | — | — | — | — |" in text

    def test_al_note_names_the_mechanism_and_the_decoupling(self) -> None:
        text = "\n".join(rep._render_cost_section(_arms_data({"a": [_row()]})))
        assert "**token 行级读取（AL）**" in text
        assert "token_usage_absent×1" in text
        assert "检出数只由 `detection_rate` 决定" in text

    def test_money_block_is_disclosed_with_tokens_still_shown(self) -> None:
        usage = {"total_tokens": 100, "input_tokens": 60, "output_tokens": 60}
        text = "\n".join(rep._render_cost_section(_arms_data({"a": [_row(usage)]})))
        assert "1 行金额被阻断（token_split_mismatch×1）" in text
        assert "| 100 |" in text
        assert "金额与 $/detection 记 `—`" in text

    def test_clean_arm_gains_no_al_lines(self) -> None:
        text = "\n".join(rep._render_cost_section(_arms_data({"a": [_row(_usage())]})))
        assert "token 行级读取（AL）" not in text
        assert "token_money_reasons" not in text

    def test_cache_zero_arm_gains_no_al_lines(self) -> None:
        zero = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
            "cache_hits": 1,
            "cache_avoided_tokens": 1748,
        }
        text = "\n".join(rep._render_cost_section(_arms_data({"a": [_row(zero)]})))
        assert "token 行级读取（AL）" not in text
        assert "缓存口径（AJ）" in text

    def test_rendered_table_rows_keep_their_cell_count(self) -> None:
        rows = {
            "a": [_row()],
            "b": [_row({"total_tokens": 100, "input_tokens": 60, "output_tokens": 60})],
            "c": [_row(_usage())],
        }
        lines = rep._render_cost_section(_arms_data(rows))
        headers = [i for i, ln in enumerate(lines) if ln.startswith("|---")]
        assert headers
        for h in headers:
            n_cells = lines[h - 1].count("|")
            for ln in lines[h + 1 :]:
                if not ln.startswith("|"):
                    break
                assert ln.count("|") == n_cells, ln
