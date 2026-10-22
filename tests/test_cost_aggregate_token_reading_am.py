"""AM 回归锁：成本表聚合的行级 token 读取（2026-10-21）。

缺陷族（`experiments.statistical_analysis.cost_analysis`）：
1. `tu.get("input_tokens") or 0` / `output_tokens` / `total_tokens` 把在场坏值
   （`"100"` 直接让 `+=` 崩溃、`True` 收下当 1、`1.5` 参与计价、`nan`/`inf`
   产出非有限金额、负数抵减总量）折成可计价数字；
2. by_model 的键/值不做值域判定（bool / 负数 / 非字符串键被求和），求和与
   总量不符时仍照单计价；
3. 正值行缺 input/output 时按 0 计价，编出 `$0`（"免费"假象）；
4. S11 把 bool / 小数 / `inf` 读成"有记账"的正向证据，放行断裂臂。

处置（真批次 783 行全部 int 自洽 ⇒ 三臂读数与返回域逐键不变）：
- 行级三元组走共享 `row_token_counts`；`token_usage` 非对象或字段在场却不是
  非负整数 ⇒ **读不动**：总量/金额一律 `None`，写 `n_token_unreadable_rows`；
- 正值 + 缺字段同样是读不动（缺字段不是 0，不得显示部分和）；整键缺席 / `None`
  仍按 AE2 的历史 0 读（AK 下界负责披露）；只有 total 缺席而 in/out 双全时按
  两者之和读；
- 拆分矛盾 / by_model 归因矛盾 ⇒ token 总量可读、只废金额；
- `by_model_reason` 判定体迁入 `src.budget.token_usage`，报告与成本表共用；
- S11 正向证据改走 `count_reason` 值域。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from experiments import emse_stats_report as rep
from experiments import statistical_analysis as sa
from src.budget.token_usage import by_model_reason

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]

_PRICES: dict[str, Any] = {
    "models": {
        "m1": {
            "input_per_mtok": 1.0,
            "output_per_mtok": 2.0,
            "currency": "USD",
            "source": "test",
            "as_of": "2026-10-21",
        }
    }
}
_UNPRICED: dict[str, Any] = {"models": {}}

_LEGACY_COST_KEYS = {
    "baseline",
    "n_tasks",
    "input_tokens",
    "output_tokens",
    "by_model",
    "missing_models",
    "unattributed_tokens",
    "cost",
    "cost_per_task",
    "currency",
    "priced",
    "token_accounting_ok",
    "token_accounting_reason",
    "token_zero_rows",
}
_AM_KEYS = {
    "n_token_unreadable_rows",
    "token_reading_reasons",
    "n_token_money_blocked_rows",
    "token_money_reasons",
}


_OMIT = object()


def _usage(**overrides: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "total_tokens": 2_000_000,
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "llm_calls": 1,
        "by_model": {"m1": 2_000_000},
    }
    usage.update(overrides)
    return usage


def _row(usage: Any = _OMIT, *, omit_usage: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": "t", "detection_rate": 0.0}
    if not omit_usage:
        row["token_usage"] = _usage() if usage is _OMIT else usage
    return row


def _cost(usage: Any, prices: dict[str, Any] = _PRICES) -> dict[str, Any]:
    return sa.cost_analysis({"a": [_row(usage)]}, prices)[0]


# ─── 1. 共享归因谓词 ───────────────────────────────────────────────────────


class TestByModelPredicate:
    def test_clean_sum_has_no_reason(self) -> None:
        assert by_model_reason({"m1": 10, "m2": 5}, 15) is None

    def test_non_string_key_is_named(self) -> None:
        assert by_model_reason({1: 10}, 10) == "by_model_key_not_str:int"

    @pytest.mark.parametrize(
        ("value", "code"),
        [
            (True, "token_not_count:by_model:m1:bool"),
            (1.5, "token_not_count:by_model:m1:float"),
            (math.nan, "token_not_finite:by_model:m1"),
            (math.inf, "token_not_finite:by_model:m1"),
            (-5, "token_negative:by_model:m1"),
        ],
        ids=["bool", "float", "nan", "inf", "negative"],
    )
    def test_bad_value_is_named(self, value: Any, code: str) -> None:
        assert by_model_reason({"m1": value}, 0) == code

    def test_sum_mismatch_is_named(self) -> None:
        assert by_model_reason({"m1": 9}, 10) == "by_model_sum_mismatch"

    def test_report_and_cost_table_agree_on_attribution(self) -> None:
        """同一坏归因：报告 §4.1 与成本表都必须废金额（一份判定，两处消费）。"""
        usage = _usage(by_model={"m1": True})
        cost = _cost(usage)
        assert cost["token_money_reasons"] == {"token_not_count:by_model:m1:bool": 1}
        eff = rep.cost_effectiveness_block([_row(usage)])
        assert eff["total_usd"] is None
        assert eff["token_money_reasons"] == {"token_not_count:by_model:m1:bool": 1}


# ─── 2. 读不动：值域与形状 ─────────────────────────────────────────────────


class TestValueDomainUnreadable:
    @pytest.mark.parametrize(
        ("usage", "code"),
        [
            (_usage(input_tokens="1000000"), "token_not_count:input_tokens:str"),
            (_usage(total_tokens=True), "token_not_count:total_tokens:bool"),
            (_usage(total_tokens=1.5), "token_not_count:total_tokens:float"),
            (_usage(total_tokens=math.nan), "token_not_finite:total_tokens"),
            (_usage(total_tokens=math.inf), "token_not_finite:total_tokens"),
            (_usage(input_tokens=-1), "token_negative:input_tokens"),
            (_usage(input_tokens=None), "token_not_count:input_tokens:NoneType"),
            ([1, 2], "token_usage_not_object:list"),
            ("100", "token_usage_not_object:str"),
            (object(), "token_usage_not_object:object"),
        ],
        ids=["str", "bool", "float", "nan", "inf", "negative", "null_field", "list", "str_root", "object"],
    )
    def test_bad_reading_blocks_totals_and_money(self, usage: Any, code: str) -> None:
        out = _cost(usage)
        assert (out["input_tokens"], out["output_tokens"], out["unattributed_tokens"]) == (None, None, None)
        assert out["by_model"] == {}
        assert (out["cost"], out["cost_per_task"], out["priced"]) == (None, None, False)
        assert out["n_token_unreadable_rows"] == 1
        assert out["token_reading_reasons"] == {code: 1}
        assert not (_AM_KEYS - {"n_token_unreadable_rows", "token_reading_reasons"}) & set(out)

    def test_one_bad_row_nulls_the_whole_arm(self) -> None:
        rows = sa.cost_analysis({"a": [_row(_usage()), _row(_usage(input_tokens="x"))]}, _PRICES)
        out = rows[0]
        assert out["input_tokens"] is None
        assert out["output_tokens"] is None
        assert out["cost"] is None
        assert out["n_token_unreadable_rows"] == 1


# ─── 3. AE2 缺席口径：整键缺席 / null 仍是历史 0 ────────────────────────────


class TestAbsentCompatibility:
    def test_missing_key_reads_as_zero_without_am_keys(self) -> None:
        out = sa.cost_analysis({"a": [_row(omit_usage=True)]}, _PRICES)[0]
        assert (out["input_tokens"], out["output_tokens"], out["unattributed_tokens"]) == (0, 0, 0)
        assert set(out) == _LEGACY_COST_KEYS
        assert "cost_caliber" not in out

    def test_null_usage_reads_as_zero_without_am_keys(self) -> None:
        out = _cost(None)
        assert (out["input_tokens"], out["output_tokens"]) == (0, 0)
        assert set(out) == _LEGACY_COST_KEYS

    def test_full_zero_triple_is_a_zero_row(self) -> None:
        out = _cost({"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}})
        assert (out["input_tokens"], out["output_tokens"], out["cost"]) == (0, 0, None)
        assert not _AM_KEYS & set(out)

    def test_partial_zero_triple_is_a_zero_row(self) -> None:
        out = _cost({"total_tokens": 0})
        assert (out["input_tokens"], out["output_tokens"], out["unattributed_tokens"]) == (0, 0, 0)
        assert not _AM_KEYS & set(out)


# ─── 4. 部分三元组：正值 + 缺字段是读不动，不是 0 ───────────────────────────


class TestPartialTriple:
    def test_positive_total_without_split_is_unreadable(self) -> None:
        out = _cost({"total_tokens": 100, "by_model": {"m1": 100}})
        assert (out["input_tokens"], out["output_tokens"], out["cost"]) == (None, None, None)
        assert out["token_reading_reasons"] == {
            "token_field_absent:input_tokens": 1,
            "token_field_absent:output_tokens": 1,
        }

    @pytest.mark.parametrize(
        ("usage", "missing"),
        [
            ({"input_tokens": 40, "by_model": {"m1": 40}}, ["total_tokens", "output_tokens"]),
            ({"output_tokens": 60, "by_model": {"m1": 60}}, ["total_tokens", "input_tokens"]),
        ],
        ids=["input_only", "output_only"],
    )
    def test_positive_single_field_is_unreadable(self, usage: dict[str, Any], missing: list[str]) -> None:
        out = _cost(usage)
        assert out["input_tokens"] is None and out["output_tokens"] is None
        assert out["token_reading_reasons"] == {f"token_field_absent:{name}": 1 for name in missing}

    def test_total_absent_but_split_present_still_prices(self) -> None:
        """成本只需 in/out：total 缺席按两者之和读，金额可算且无 AM 键。"""
        out = _cost({"input_tokens": 1_000_000, "output_tokens": 1_000_000, "by_model": {"m1": 2_000_000}})
        assert (out["input_tokens"], out["output_tokens"]) == (1_000_000, 1_000_000)
        assert out["cost"] == pytest.approx(3.0)
        assert not _AM_KEYS & set(out)

    def test_total_absent_split_with_bad_attribution_blocks_money(self) -> None:
        out = _cost({"input_tokens": 40, "output_tokens": 60, "by_model": {"m1": 90}})
        assert (out["input_tokens"], out["output_tokens"]) == (40, 60)
        assert out["cost"] is None
        assert out["token_money_reasons"] == {"by_model_sum_mismatch": 1}

    def test_total_absent_with_bad_split_is_unreadable(self) -> None:
        out = _cost({"input_tokens": 40, "output_tokens": "60"})
        assert out["input_tokens"] is None
        assert "token_not_count:output_tokens:str" in out["token_reading_reasons"]


# ─── 5. 矛盾：只废金额，token 总量仍可读 ────────────────────────────────────


class TestMoneyOnlyBlocking:
    def test_split_mismatch_keeps_totals(self) -> None:
        out = _cost(_usage(total_tokens=100, input_tokens=30, output_tokens=60, by_model={"m1": 100}))
        assert (out["input_tokens"], out["output_tokens"]) == (30, 60)
        assert out["cost"] is None
        assert out["n_token_money_blocked_rows"] == 1
        assert out["token_money_reasons"] == {"token_split_mismatch": 1}
        assert "n_token_unreadable_rows" not in out

    @pytest.mark.parametrize(
        ("by_model", "code"),
        [
            ({"m1": 90}, "by_model_sum_mismatch"),
            ({"m1": True}, "token_not_count:by_model:m1:bool"),
            ({"m1": -100}, "token_negative:by_model:m1"),
            ({1: 100}, "by_model_key_not_str:int"),
            ("m1", "by_model_not_object:str"),
        ],
        ids=["sum", "bool", "negative", "key", "not_object"],
    )
    def test_bad_attribution_blocks_money(self, by_model: Any, code: str) -> None:
        out = _cost(_usage(by_model=by_model))
        assert (out["input_tokens"], out["output_tokens"]) == (1_000_000, 1_000_000)
        assert out["cost"] is None
        assert out["token_money_reasons"] == {code: 1}

    def test_attribution_with_zero_basis_still_blocks(self) -> None:
        """三元组 0 而 by_model 声称有 token：照 0 计价会编出"免费"。"""
        out = _cost({"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {"m1": 10}})
        assert out["cost"] is None
        assert out["token_money_reasons"] == {"by_model_sum_mismatch": 1}

    def test_non_object_attribution_with_zero_basis_still_blocks(self) -> None:
        usage = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": "x"}
        out = _cost(usage)
        assert out["cost"] is None
        assert out["token_money_reasons"] == {"by_model_not_object:str": 1}

    def test_missing_attribution_blocks_full_amount(self) -> None:
        """N04（2026-10-22 第三方复审 P1）：缺归因的正 token 不得由已知价格补齐。

        历史口径（本测试原名 test_missing_attribution_is_unattributed_not_blocked）：
        `unattributed_tokens=100` 但全额仍按整臂 100 计价——未知 token 被其他行
        的单价覆盖。现在全额不可计算 + 点名 `attribution_missing_rows`，可归因
        部分只作小计。
        """
        out = _cost({"total_tokens": 100, "input_tokens": 40, "output_tokens": 60})
        assert out["unattributed_tokens"] == 100
        assert out["cost"] is None
        assert out["n_unattributed_rows"] == 1
        assert out["token_money_reasons"] == {"attribution_missing_rows:1": 1}
        assert out["n_token_money_blocked_rows"] == 1

    def test_empty_attribution_blocks_full_amount(self) -> None:
        out = _cost({"total_tokens": 100, "input_tokens": 40, "output_tokens": 60, "by_model": {}})
        assert out["unattributed_tokens"] == 100
        assert out["cost"] is None
        assert out["token_money_reasons"] == {"attribution_missing_rows:1": 1}

    def test_money_blocked_row_does_not_null_good_rows(self) -> None:
        rows = sa.cost_analysis(
            {
                "a": [
                    _row(_usage(total_tokens=100, input_tokens=30, output_tokens=60, by_model={"m1": 100})),
                    _row(_usage(total_tokens=200, input_tokens=90, output_tokens=110, by_model={"m1": 200})),
                ]
            },
            _PRICES,
        )
        out = rows[0]
        assert (out["input_tokens"], out["output_tokens"]) == (120, 170)
        assert out["cost"] is None
        assert out["n_token_money_blocked_rows"] == 1


# ─── 6. S11：正向证据必须是计数 ─────────────────────────────────────────────


class TestS11EvidenceDomain:
    @pytest.mark.parametrize(
        "usage",
        [
            {"total_tokens": True, "input_tokens": 0, "output_tokens": 0, "by_model": {}},
            {"total_tokens": 1.5, "input_tokens": 0, "output_tokens": 0, "by_model": {}},
            {"total_tokens": math.inf, "input_tokens": 0, "output_tokens": 0, "by_model": {}},
            {"total_tokens": "100", "input_tokens": 0, "output_tokens": 0, "by_model": {}},
            {"total_tokens": -5, "input_tokens": 0, "output_tokens": 0, "by_model": {}},
        ],
        ids=["bool", "float", "inf", "str", "negative"],
    )
    def test_corrupt_positive_is_not_accounting(self, usage: dict[str, Any]) -> None:
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}
        sanity = sa.token_accounting_sanity([{"token_usage": usage}, {"token_usage": zero}, {"token_usage": zero}])
        assert sanity["n_without_accounting"] == 3
        assert sanity["computable"] is False

    @pytest.mark.parametrize(
        "by_model",
        [{"m1": True}, {"m1": -5}, {1: 5}, {"m1": 1.5}],
        ids=["bool", "negative", "key", "float"],
    )
    def test_corrupt_attribution_is_not_accounting(self, by_model: dict[Any, Any]) -> None:
        usage = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": by_model}
        assert sa._row_has_token_accounting({"token_usage": usage}) is False

    def test_legit_int_evidence_still_counts(self) -> None:
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}
        legit = {"total_tokens": 100, "input_tokens": 40, "output_tokens": 60}
        rows = [{"token_usage": legit}, {"token_usage": legit}, {"token_usage": zero}]
        sanity = sa.token_accounting_sanity(rows)
        assert (sanity["n_without_accounting"], sanity["computable"]) == (1, True)

    def test_cache_bool_is_not_positive_evidence(self) -> None:
        usage = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
            "cache_hits": True,
        }
        assert sa._row_has_token_accounting({"token_usage": usage}) is False


# ─── 7. 呈现层：None → —，缺口单列，不混进"只差价目" ───────────────────────


class TestRendering:
    def _text(self, rows: list[dict[str, Any]], prices: dict[str, Any] = _PRICES, det: dict | None = None) -> str:
        return "\n".join(sa._cost_report_lines(rows, prices, det))

    def _mixed_arm(self) -> list[dict[str, Any]]:
        """配一个可计价臂 + 一个含读不动行的臂：否则整份报告走早退分支无表格。"""
        return sa.cost_analysis(
            {"good": [_row()], "bad": [_row(), _row(_usage(input_tokens="x"))]},
            _PRICES,
        )

    def test_unreadable_tokens_render_dash(self) -> None:
        text = self._text(self._mixed_arm())
        assert "| bad | 2 | — | — | — | — |" in text
        assert "| good | 1 | 1000000 | 1000000 | 3.0000 | USD |" in text

    def test_unreadable_tokens_render_dash_with_detection_column(self) -> None:
        text = self._text(self._mixed_arm(), det={"good": 50.0, "bad": 50.0})
        assert "| bad | 2 | — | — | — | — | — |" in text

    def test_unreadable_note_names_mechanism(self) -> None:
        text = self._text(self._mixed_arm())
        assert "**token 读数缺口（AM）**" in text
        assert "token_not_count:input_tokens:str←1 行" in text
        assert "不折 0、不给部分和" in text

    def test_money_blocked_keeps_token_cells_but_not_money(self) -> None:
        usage = _usage(total_tokens=100, input_tokens=30, output_tokens=60, by_model={"m1": 100})
        rows = sa.cost_analysis({"good": [_row()], "bad": [_row(usage)]}, _PRICES)
        text = self._text(rows)
        assert "| bad | 1 | 30 | 60 | — | — |" in text
        assert "只废金额" in text

    def test_blocked_arms_are_not_filed_under_price_only(self) -> None:
        data = {
            "good": [_row()],
            "bad": [_row(_usage(input_tokens="x"))],
            "mix": [_row(_usage(total_tokens=100, input_tokens=30, output_tokens=60, by_model={"m1": 100}))],
            "noprice": [_row({"total_tokens": 100, "input_tokens": 40, "output_tokens": 60, "by_model": {"m9": 100}})],
        }
        text = self._text(sa.cost_analysis(data, _PRICES))
        assert "注：1 个基线未计价——noprice" in text
        assert "注：3 个基线未计价" not in text
        assert "`bad`" in text and "`mix`" in text

    def test_all_unreadable_heading_is_not_price_registration(self) -> None:
        text = self._text(sa.cost_analysis({"a": [_row(_usage(input_tokens="x"))]}, _UNPRICED), _UNPRICED)
        assert "**成本不可计算**" in text
        assert "（无可用 token 观测）" in text
        assert "**价目未登记**" not in text
        assert "补齐方式：在 experiments/price_table.json" not in text

    def test_money_blocked_without_prices_is_not_price_registration(self) -> None:
        usage = _usage(total_tokens=100, input_tokens=30, output_tokens=60, by_model={"m1": 100})
        rows = sa.cost_analysis({"a": [_row(usage)]}, _UNPRICED)
        text = self._text(rows, _UNPRICED)
        assert "**成本不可计算**" in text
        assert "拆分/归因矛盾" in text

    def test_s11_zero_arm_keeps_historical_price_heading(self) -> None:
        """AM 标题判定只认自己的两个新状态；S11 断裂的历史文本仍由既有锁覆盖。"""
        zero = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}
        rows = sa.cost_analysis({"a": [_row(zero)]}, _UNPRICED)
        text = self._text(rows, _UNPRICED)
        assert "**价目未登记**" in text
        assert "**成本不可计算**" not in text

    def test_clean_arm_text_is_unchanged(self) -> None:
        text = self._text([_cost(_usage())])
        expected_head = [
            "成本口径：$/task = (Σ输入 token × 输入单价 + Σ输出 token × 输出单价) / 任务数；",
            "价目来自 experiments/price_table.json（模型级登记，含来源与生效日期）；",
            "token 行级来源 = 结果行 token_usage（input_tokens / output_tokens）；",
            "多模型异价的基线无法按 in/out 拆分归属，成本诚实降级为未计价（—）。",
            "",
            "| Baseline | 任务数 | 输入 token | 输出 token | 成本/任务 | 币种 |",
            "|----------|--------|-----------|-----------|-----------|------|",
            "| a | 1 | 1000000 | 1000000 | 3.0000 | USD |",
        ]
        assert text.splitlines() == expected_head
        for marker in ("AM", "下界", "NOT_COMPUTABLE", "缓存"):
            assert marker not in text


# ─── 8. 真实主批：读数与返回域逐键不变 ─────────────────────────────────────


def _main_batch_rows() -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in _MAIN_BATCH_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for arm, block in data["results"].items():
            merged.setdefault(arm, []).extend(block["details"])
    return merged


class TestRealMainBatch:
    def test_all_783_rows_are_readable_and_self_consistent(self) -> None:
        arms = _main_batch_rows()
        assert sum(len(rows) for rows in arms.values()) == 783
        for rows in arms.values():
            for row in rows:
                reading = sa._row_cost_tokens(row)
                assert reading["counts"] is not None, row.get("task_id")
                assert reading["reasons"] == []
                assert (
                    reading["usage"].get("by_model") is None
                    or by_model_reason(reading["usage"]["by_model"], reading["counts"][0]) is None
                )

    def test_three_arms_read_unchanged(self) -> None:
        price = json.loads((_ROOT / "experiments/price_table.json").read_text(encoding="utf-8"))
        by_arm = {r["baseline"]: r for r in sa.cost_analysis(_main_batch_rows(), price)}
        expected = {
            "aitester": (1_581_326, 5_234_651, 6.755979000000001),
            "plain_llm": (142_783, 694_881, 0.8766921),
            "plain_llm_df": (152_103, 950_127, 1.1857833),
        }
        for arm, (inp, out, cost) in expected.items():
            row = by_arm[arm]
            assert (row["input_tokens"], row["output_tokens"]) == (inp, out)
            assert row["cost"] == pytest.approx(cost)
            assert not _AM_KEYS & set(row)
        assert by_arm["plain_llm_df"]["cost_caliber"] == "recorded_lower_bound"
        assert "cost_caliber" not in by_arm["aitester"]

    def test_real_batch_report_has_no_am_note(self) -> None:
        price = json.loads((_ROOT / "experiments/price_table.json").read_text(encoding="utf-8"))
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(_main_batch_rows(), price), price))
        assert "token 读数缺口（AM）" not in text
