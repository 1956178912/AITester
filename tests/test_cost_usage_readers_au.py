"""AU 回归锁：实验侧成本/用量聚合器必须走共享值域（2026-10-21）。

改前实测（零 LLM 探针）三处同族缺口：

1. `spec_examples_generator.estimate_cost_usd` 对 usage **没有值域门**：
   `input_tokens=None` + `output_tokens=1000000` → `$2.0`（把未知输入读成免费），
   `True` 当 1、`"12"` 当 12、负数编出负数金额、`nan` 产出非有限金额；
2. `oracle_examples_replay.generation_summary` 自己用 `int(u.get(...) or 0)` 求和，
   AT 的 `token_write_reasons` 标记在汇总里**完全消失**，报告读起来像"完整且为 0"；
3. `run_b8_injection._cost_usd` 把聚合 `token_metrics` 的上游拒绝（`None`）折成 0，
   NaN/Inf/bool/负价一路进 `REPORT.json` 与 README。

判据：金额所需的每个 token 字段都必须经 `count_reason` / `token_metric_reading`
判定——**读不动不给数字**（None + 机制名），**缺席才是历史 0**，**拒绝标记在场时
已收下部分的和也不得冒充完整和**。事件计数（`llm_calls`）与 token 金额分离。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import oracle_examples_replay as oer
from experiments import run_b8_injection as rb8
from experiments import spec_examples_generator as seg

_ROOT = Path(__file__).resolve().parents[1]
_NAN = float("nan")
_INF = float("inf")


def _price_table() -> dict[str, Any]:
    return {
        "models": {
            "m": {
                "currency": "USD",
                "input_per_mtok": 1.0,
                "output_per_mtok": 2.0,
                "source": "unit",
                "as_of": "2026-10-21",
            }
        }
    }


def _usage(**over: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    usage.update(over)
    return usage


def _generation(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "task_id": "t1",
        "status": "ok",
        "model": "m",
        "usage": {
            "input_tokens": 1_000,
            "output_tokens": 500,
            "total_tokens": 1_500,
            "llm_calls": 1,
            "cache_hits": 0,
        },
        "examples": [],
    }
    row.update(over)
    return row


# ─── 1. estimate_cost_usd：金额所需的 token 字段逐个过值域 ─────────────────────


class TestEstimateCostUsageDomain:
    def test_clean_usage_unchanged(self) -> None:
        assert seg.estimate_cost_usd("m", _usage(), _price_table()) == 3.0

    def test_zero_usage_is_zero_cost(self) -> None:
        assert seg.estimate_cost_usd("m", {"input_tokens": 0, "output_tokens": 0}, _price_table()) == 0.0

    def test_absent_fields_are_historical_zero(self) -> None:
        assert seg.estimate_cost_usd("m", {}, _price_table()) == 0.0
        assert seg.estimate_cost_usd("m", {"output_tokens": 1_000_000}, _price_table()) == 2.0

    def test_present_null_input_is_unreadable_not_zero(self) -> None:
        assert seg.estimate_cost_usd("m", _usage(input_tokens=None), _price_table()) is None

    def test_present_null_output_is_unreadable_not_zero(self) -> None:
        assert seg.estimate_cost_usd("m", _usage(output_tokens=None), _price_table()) is None

    @pytest.mark.parametrize("bad", [True, False, "12", 1.5, -1, _NAN, _INF])
    def test_bad_input_domain_rejected(self, bad: Any) -> None:
        assert seg.estimate_cost_usd("m", _usage(input_tokens=bad), _price_table()) is None

    @pytest.mark.parametrize("bad", [True, "5", 2.5, -3, _NAN, _INF])
    def test_bad_output_domain_rejected(self, bad: Any) -> None:
        assert seg.estimate_cost_usd("m", _usage(output_tokens=bad), _price_table()) is None

    @pytest.mark.parametrize("usage", [None, [], ["input_tokens"], "usage", 3])
    def test_non_object_usage_is_unreadable(self, usage: Any) -> None:
        assert seg.estimate_cost_usd("m", usage, _price_table()) is None

    def test_token_write_marker_blocks_cost(self) -> None:
        usage = _usage(token_write_reasons={"input_tokens": 1})
        assert seg.estimate_cost_usd("m", usage, _price_table()) is None

    def test_cache_write_marker_does_not_block_direct_cost(self) -> None:
        usage = _usage(cache_write_reasons={"cache_avoided_tokens": 1})
        assert seg.estimate_cost_usd("m", usage, _price_table()) == 3.0

    def test_usage_block_reason_names_the_mechanism(self) -> None:
        assert seg.usage_block_reason_for(_usage(input_tokens=None)) == "token_metric_unreadable:input_tokens"
        assert seg.usage_block_reason_for(_usage(input_tokens="12")) == "token_not_count:input_tokens:str"
        assert seg.usage_block_reason_for(_usage(input_tokens=True)) == "token_not_count:input_tokens:bool"
        assert seg.usage_block_reason_for(_usage(input_tokens=-1)) == "token_negative:input_tokens"
        assert seg.usage_block_reason_for(_usage(input_tokens=_NAN)) == "token_not_finite:input_tokens"
        assert seg.usage_block_reason_for(_usage(token_write_reasons={"output_tokens": 2})) == (
            "token_write_rejected:output_tokens"
        )
        assert seg.usage_block_reason_for(_usage()) is None

    def test_usage_block_reason_non_object(self) -> None:
        assert seg.usage_block_reason_for(None) == "usage_not_object:NoneType"
        assert seg.usage_block_reason_for([]) == "usage_not_object:list"

    def test_cost_block_reason_price_precedence(self) -> None:
        table = {"models": {}}
        assert seg.cost_block_reason("m", _usage(input_tokens=None), table) == "model_unregistered"

    def test_cost_block_reason_usage_when_price_ok(self) -> None:
        table = _price_table()
        assert seg.cost_block_reason("m", _usage(input_tokens=None), table) == ("token_metric_unreadable:input_tokens")
        assert seg.cost_block_reason("m", _usage(), table) is None

    def test_price_only_reason_stays_price_only(self) -> None:
        assert seg.price_block_reason_for("m", _price_table()) is None
        assert seg.price_block_reason_for("missing", _price_table()) == "model_unregistered"


# ─── 2. _usage_delta：标记必须随差值一起带走 ─────────────────────────────────


class TestUsageDelta:
    def test_clean_delta_unchanged(self) -> None:
        before = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "llm_calls": 1}
        after = {"input_tokens": 30, "output_tokens": 9, "total_tokens": 39, "llm_calls": 3}
        delta = seg._usage_delta(before, after)
        assert delta["input_tokens"] == 20
        assert delta["output_tokens"] == 4
        assert delta["total_tokens"] == 24
        assert delta["llm_calls"] == 2
        assert "usage_delta_reasons" not in delta
        assert "token_write_reasons" not in delta
        assert "cache_write_reasons" not in delta

    def test_unreadable_snapshot_yields_none(self) -> None:
        delta = seg._usage_delta({"input_tokens": 10}, {"input_tokens": None})
        assert delta["input_tokens"] is None
        assert "token_metric_unreadable:input_tokens" in delta["usage_delta_reasons"]

    def test_token_write_marker_delta_preserved(self) -> None:
        before = {"input_tokens": 10, "token_write_reasons": {}}
        after = {"input_tokens": 10, "token_write_reasons": {"input_tokens": 1}}
        delta = seg._usage_delta(before, after)
        assert delta["token_write_reasons"] == {"input_tokens": 1}

    def test_cache_write_marker_delta_preserved(self) -> None:
        after = {"cache_write_reasons": {"cache_avoided_tokens": 2}}
        delta = seg._usage_delta({}, after)
        assert delta["cache_write_reasons"] == {"cache_avoided_tokens": 2}

    def test_marker_without_delta_is_absent(self) -> None:
        snap = {"input_tokens": 10, "token_write_reasons": {"input_tokens": 1}}
        delta = seg._usage_delta(snap, dict(snap))
        assert "token_write_reasons" not in delta


# ─── 3. generation_summary：标记与坏值不得消失在汇总里 ────────────────────────


class TestGenerationSummary:
    def test_clean_summary_unchanged(self) -> None:
        gens = [
            _generation(task_id="t1"),
            _generation(
                task_id="t2",
                usage={
                    "input_tokens": 2_000,
                    "output_tokens": 1_000,
                    "total_tokens": 3_000,
                    "llm_calls": 2,
                    "cache_hits": 1,
                },
            ),
        ]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] == 3_000
        assert summary["output_tokens"] == 1_500
        assert summary["llm_calls"] == 3
        assert summary["cache_hits"] == 1
        assert summary["estimated_cost_usd"] == pytest.approx(0.006, rel=1e-12)
        assert "cost_unpriced_reason" not in summary
        assert "token_reading_reasons" not in summary
        assert "cache_reading_reasons" not in summary

    def test_write_marker_makes_token_and_cost_unreadable(self) -> None:
        gens = [
            _generation(task_id="t1"),
            _generation(
                task_id="t2",
                usage={
                    "input_tokens": 0,
                    "output_tokens": 1_000,
                    "total_tokens": 1_000,
                    "llm_calls": 1,
                    "cache_hits": 0,
                    "token_write_reasons": {"input_tokens": 1},
                },
            ),
        ]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] is None
        assert summary["output_tokens"] is None
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "token_write_rejected:input_tokens"
        assert summary["token_reading_reasons"]["token_write_rejected:input_tokens"] == 1
        assert summary["llm_calls"] == 2

    def test_unreadable_input_field_blocks_tokens_and_cost(self) -> None:
        gens = [_generation(usage={"input_tokens": "1000", "output_tokens": 500, "llm_calls": 1})]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] is None
        assert summary["output_tokens"] is None
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "token_not_count:input_tokens:str"
        assert summary["token_reading_reasons"]["token_not_count:input_tokens:str"] == 1
        assert summary["llm_calls"] == 1

    def test_bad_calls_do_not_kill_readable_tokens(self) -> None:
        gens = [_generation(usage={"input_tokens": 1_000, "output_tokens": 500, "llm_calls": True})]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] == 1_000
        assert summary["output_tokens"] == 500
        assert summary["estimated_cost_usd"] == pytest.approx(0.002, rel=1e-12)
        assert summary["llm_calls"] is None
        assert summary["token_reading_reasons"]["token_not_count:llm_calls:bool"] == 1

    def test_non_object_usage_makes_all_readings_unreadable(self) -> None:
        gens = [_generation(usage="bad")]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] is None
        assert summary["output_tokens"] is None
        assert summary["estimated_cost_usd"] is None
        assert summary["token_reading_reasons"]["token_usage_not_object:str"] == 1
        assert summary["per_task"][0]["llm_calls"] is None

    def test_cache_marker_blocks_cache_column_only(self) -> None:
        gens = [
            _generation(
                usage={
                    "input_tokens": 1_000,
                    "output_tokens": 500,
                    "total_tokens": 1_500,
                    "llm_calls": 1,
                    "cache_hits": 2,
                    "cache_avoided_tokens": 0,
                    "cache_write_reasons": {"cache_avoided_tokens": 1},
                }
            )
        ]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["input_tokens"] == 1_000
        assert summary["estimated_cost_usd"] == pytest.approx(0.002, rel=1e-12)
        assert summary["cache_hits"] is None
        assert summary["cache_reading_reasons"]["cache_write_rejected:cache_avoided_tokens"] == 1

    def test_price_failure_reason_has_precedence(self) -> None:
        gens = [_generation(usage={"input_tokens": None, "output_tokens": 1})]
        summary = oer.generation_summary(gens, {"models": {}})
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "model_unregistered"

    def test_per_task_calls_use_domain_reader(self) -> None:
        gens = [_generation(usage={"input_tokens": 1_000, "output_tokens": 500, "llm_calls": "9"})]
        summary = oer.generation_summary(gens, _price_table())
        assert summary["per_task"][0]["llm_calls"] is None


# ─── 4. 多采样 usage_totals：同一套聚合口径 ──────────────────────────────────


class TestMultisampleUsageTotals:
    def test_clean_totals_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        usages = iter(
            [
                {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "llm_calls": 1, "cache_hits": 0},
                {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160, "llm_calls": 1, "cache_hits": 0},
            ]
        )

        def fake(material: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "task_id": kwargs.get("task_id"),
                "status": "ok",
                "examples": [{"input": [1], "expected": 1}],
                "usage": next(usages),
                "model": "m",
            }

        monkeypatch.setattr(seg, "generate_spec_examples", fake)
        record = seg.generate_examples_multisample({"function_name": "f"})
        assert record["usage_totals"] == {
            "input_tokens": 220,
            "output_tokens": 90,
            "total_tokens": 310,
            "llm_calls": 2,
            "cache_hits": 0,
        }
        assert "usage_reasons" not in record

    def test_marker_in_one_sample_blocks_totals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        usages = iter(
            [
                {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "llm_calls": 1, "cache_hits": 0},
                {
                    "input_tokens": 0,
                    "output_tokens": 40,
                    "total_tokens": 40,
                    "llm_calls": 1,
                    "cache_hits": 0,
                    "token_write_reasons": {"input_tokens": 1},
                },
            ]
        )

        def fake(material: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "task_id": kwargs.get("task_id"),
                "status": "ok",
                "examples": [{"input": [1], "expected": 1}],
                "usage": next(usages),
                "model": "m",
            }

        monkeypatch.setattr(seg, "generate_spec_examples", fake)
        record = seg.generate_examples_multisample({"function_name": "f"})
        assert record["usage_totals"]["input_tokens"] is None
        assert record["usage_totals"]["output_tokens"] is None
        assert record["usage_totals"]["total_tokens"] is None
        assert record["usage_totals"]["llm_calls"] == 2
        assert record["usage_reasons"]["token_write_rejected:input_tokens"] == 1


class TestOracleReadingRendering:
    def test_none_readings_render_as_unreadable_not_none(self) -> None:
        assert oer._reading_text(None) == "不可读"
        assert oer._reading_text(0) == "0"


# ─── 5. run_b8：聚合 token_metrics 的上游拒绝不得折 0 ───────────────────────


class TestRunB8CostReading:
    def test_clean_cost_unchanged(self) -> None:
        cost, reasons = rb8._cost_usd({"total_input_tokens": 1_000_000, "total_output_tokens": 0}, 1.0, 2.0)
        assert cost == 1.0
        assert reasons == {}

    def test_absent_fields_are_historical_zero(self) -> None:
        cost, reasons = rb8._cost_usd({"total_output_tokens": 1_000_000}, 1.0, 2.0)
        assert cost == 2.0
        assert reasons == {}

    @pytest.mark.parametrize(
        ("metrics", "code"),
        [
            ({"total_input_tokens": None, "total_output_tokens": 1}, "token_metric_unreadable:total_input_tokens"),
            ({"total_input_tokens": 1, "total_output_tokens": None}, "token_metric_unreadable:total_output_tokens"),
            ({"total_input_tokens": True, "total_output_tokens": 1}, "token_not_count:total_input_tokens:bool"),
            ({"total_input_tokens": -1, "total_output_tokens": 1}, "token_negative:total_input_tokens"),
            ({"total_input_tokens": _NAN, "total_output_tokens": 1}, "token_not_finite:total_input_tokens"),
            ({"total_input_tokens": _INF, "total_output_tokens": 1}, "token_not_finite:total_input_tokens"),
            ({"total_input_tokens": "1", "total_output_tokens": 1}, "token_not_count:total_input_tokens:str"),
        ],
    )
    def test_unreadable_metric_gives_no_cost(self, metrics: dict[str, Any], code: str) -> None:
        cost, reasons = rb8._cost_usd(metrics, 1.0, 2.0)
        assert cost is None
        assert reasons == {code: 1}

    def test_non_object_metrics_gives_no_cost(self) -> None:
        cost, reasons = rb8._cost_usd(["bad"], 1.0, 2.0)
        assert cost is None
        assert reasons == {"token_metrics_not_object:list": 1}

    def test_arm_summary_carries_reasons_only_when_unreadable(self) -> None:
        loaded = {
            "details": [],
            "token_metrics": {"total_input_tokens": 1_000_000, "total_output_tokens": 0},
            "injection_records": [],
            "meta": {},
            "batch_path": "x",
            "batch_sha256": "0" * 64,
            "data": {},
        }
        ok = rb8._arm_summary(loaded, 1.0, 2.0)
        assert ok["cost_usd_standard_price"] == 1.0
        assert "cost_usd_standard_price_reasons" not in ok

        loaded["token_metrics"] = {"total_input_tokens": None, "total_output_tokens": 1_000_000}
        bad = rb8._arm_summary(loaded, 1.0, 2.0)
        assert bad["cost_usd_standard_price"] is None
        assert bad["cost_usd_standard_price_reasons"] == {"token_metric_unreadable:total_input_tokens": 1}

    def test_smoke_cost_none_and_reasoned(self, tmp_path: Path) -> None:
        arm_dir = tmp_path / "_harness_smoke" / "arm_on"
        arm_dir.mkdir(parents=True)
        batch = arm_dir / "benchmark_x.json"
        batch.write_text(
            json.dumps(
                {
                    "results": {
                        "on": {
                            "details": [],
                            "token_metrics": {
                                "total_input_tokens": None,
                                "total_output_tokens": 1_000_000,
                                "total_tokens": 1_000_000,
                            },
                        }
                    },
                    "provenance": {},
                }
            ),
            encoding="utf-8",
        )
        rows = rb8._load_harness_smoke(tmp_path, 1.0, 2.0)
        assert rows[0]["cost_usd_standard_price"] is None
        assert rows[0]["cost_usd_standard_price_reasons"] == {"token_metric_unreadable:total_input_tokens": 1}

    def test_cost_text_never_wears_dollar_shape_when_none(self) -> None:
        assert rb8._cost_text(None, {"token_metric_unreadable:total_input_tokens": 1}) == (
            "—（无法估算：token_metric_unreadable:total_input_tokens×1）"
        )
        assert rb8._cost_text(1.5, {}) == "$1.5"


# ─── 6. 源码锁：宽松折叠不得回潮 ─────────────────────────────────────────────


class TestNoLooseCostFoldRegression:
    def test_estimate_cost_has_no_usage_or_zero(self) -> None:
        source = (_ROOT / "experiments" / "spec_examples_generator.py").read_text(encoding="utf-8")
        assert 'usage.get("input_tokens", 0) or 0' not in source
        assert 'usage.get("output_tokens", 0) or 0' not in source
        assert "usage_block_reason_for" in source

    def test_generation_summary_uses_shared_aggregate(self) -> None:
        source = (_ROOT / "experiments" / "oracle_examples_replay.py").read_text(encoding="utf-8")
        assert 'int(u.get("input_tokens", 0) or 0)' not in source
        assert 'int(u.get("output_tokens", 0) or 0)' not in source
        assert "aggregate_row_token_usage" in source

    def test_run_b8_cost_uses_metric_reading(self) -> None:
        source = (_ROOT / "experiments" / "run_b8_injection.py").read_text(encoding="utf-8")
        assert 'float(tm.get("total_input_tokens") or 0)' not in source
        assert 'float(tm.get("total_output_tokens") or 0)' not in source
