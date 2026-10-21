"""AW 轮（2026-10-21，零 LLM）：T1/B2 逐臂统计的 token_metrics 形状与事件计数。

AV 把 `add_cost` 的两个 token 字段接回共享值域后，同一份载荷在进入 `add_cost`
之前先经过 `arm_stats`：那里仍写 `res.get("token_metrics") or {}`，真值非对象
（`"abc"` / `True`）让 `.get` 抛 AttributeError、整次分析中止；假值非对象
（`[]` / `""` / `0`）被静默改写成 `{}`，"载荷坏了"变成"没有 metrics"；
`calls` 直接取 `tm.get("total_llm_calls")`，bool / 数字字符串 / 小数 / 负数
原样进逐 seed 报告，而池化列走 `sum_token_metric_values` 会拒绝同一份值——
同一报告里逐 seed 与池化对同一次读数给出互斥事实。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import analyze_t1_b2_main_batch as t1

_ROOT = Path(__file__).resolve().parents[1]
_BATCH = _ROOT / "experiments/results/t_round_b2_main_batch_20261018"
_REPORT = _BATCH / "ANALYSIS_REPORT.json"

_PRICE = {"input_per_mtok": 0.3, "output_per_mtok": 1.2, "currency": "USD"}


def _batch(token_metrics: Any = ..., *, with_key: bool = True) -> dict[str, Any]:
    arm: dict[str, Any] = {"details": []}
    if with_key:
        arm["token_metrics"] = token_metrics
    return {"results": {"aitester": arm}}


class TestArmStatsCallsDomain:
    def test_clean_calls_read_as_int(self) -> None:
        metrics = {"total_llm_calls": 7, "total_input_tokens": 12, "total_output_tokens": 34}
        stats = t1.arm_stats(_batch(metrics), "aitester")
        assert stats["calls"] == 7
        assert "calls_reason" not in stats
        assert stats["token_metrics"] == metrics

    @pytest.mark.parametrize("metrics", [None, {}], ids=["null", "empty"])
    def test_absent_metrics_keep_historical_zero(self, metrics: Any) -> None:
        stats = t1.arm_stats(_batch(metrics), "aitester")
        assert stats["calls"] == 0
        assert "calls_reason" not in stats
        assert stats["token_metrics"] is metrics

    def test_metrics_key_absent_keeps_historical_zero(self) -> None:
        stats = t1.arm_stats(_batch(with_key=False), "aitester")
        assert stats["calls"] == 0
        assert "calls_reason" not in stats
        assert stats["token_metrics"] is None

    def test_absent_calls_field_keeps_historical_zero(self) -> None:
        stats = t1.arm_stats(_batch({"total_input_tokens": 5}), "aitester")
        assert stats["calls"] == 0
        assert "calls_reason" not in stats

    def test_null_calls_named_not_zero(self) -> None:
        stats = t1.arm_stats(_batch({"total_llm_calls": None}), "aitester")
        assert stats["calls"] is None
        assert stats["calls_reason"] == "token_metric_unreadable:total_llm_calls"

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (True, "token_not_count:total_llm_calls:bool"),
            ("12", "token_not_count:total_llm_calls:str"),
            (10.0, "token_not_count:total_llm_calls:float"),
            (-5, "token_negative:total_llm_calls"),
            (float("nan"), "token_not_finite:total_llm_calls"),
            (float("inf"), "token_not_finite:total_llm_calls"),
        ],
        ids=["bool", "str", "float", "negative", "nan", "inf"],
    )
    def test_bad_calls_are_named_not_copied(self, value: Any, reason: str) -> None:
        stats = t1.arm_stats(_batch({"total_llm_calls": value}), "aitester")
        assert stats["calls"] is None
        assert stats["calls_reason"] == reason

    @pytest.mark.parametrize("metrics", ["abc", True, [], ""], ids=["str", "bool", "list", "empty-str"])
    def test_non_object_metrics_do_not_raise_and_are_preserved(self, metrics: Any) -> None:
        stats = t1.arm_stats(_batch(metrics), "aitester")
        assert stats["calls"] is None
        assert stats["calls_reason"] == f"token_metrics_not_object:{type(metrics).__name__}"
        assert stats["token_metrics"] is metrics

    def test_non_object_metrics_feed_add_cost_the_same_reason(self) -> None:
        stats = t1.arm_stats(_batch([]), "aitester")
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == "token_metrics_not_object:list"
        assert stats["calls_reason"] == "token_metrics_not_object:list"

    def test_calls_and_token_amounts_are_independent(self) -> None:
        stats = t1.arm_stats(
            _batch({"total_llm_calls": True, "total_input_tokens": 12, "total_output_tokens": 34}),
            "aitester",
        )
        t1.add_cost(stats, _PRICE)
        assert stats["calls"] is None
        assert stats["calls_reason"] == "token_not_count:total_llm_calls:bool"
        assert stats["cost_usd"] == 4.4e-05
        assert "cost_unpriced_reason" not in stats

    def test_bad_tokens_do_not_block_calls(self) -> None:
        stats = t1.arm_stats(
            _batch({"total_llm_calls": 3, "total_input_tokens": True, "total_output_tokens": 34}),
            "aitester",
        )
        t1.add_cost(stats, _PRICE)
        assert stats["calls"] == 3
        assert "calls_reason" not in stats
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == "token_not_count:total_input_tokens:bool"


class TestRealBatchCalls:
    def _report(self) -> dict[str, Any]:
        return json.loads(_REPORT.read_text(encoding="utf-8"))

    def test_stored_per_seed_calls_reproduce(self) -> None:
        if not _REPORT.exists():
            pytest.skip("T1/B2 受保护工件不在盘上")
        n = 0
        for arms in self._report()["per_seed"].values():
            for label in ("new", "original"):
                for stats in (arms.get(label) or {}).values():
                    reading = t1.token_metric_reading(stats["token_metrics"], "total_llm_calls")
                    assert reading["value"] == stats["calls"]
                    n += 1
        assert n == 18

    def test_raw_new_arms_reproduce_through_arm_stats(self) -> None:
        if not _REPORT.exists():
            pytest.skip("T1/B2 受保护工件不在盘上")
        report = self._report()
        n = 0
        for seed in (42, 43, 44):
            files = sorted((_BATCH / f"seed{seed}").glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
            if not files:
                pytest.skip("原始批次文件不在盘上")
            batch = json.loads(files[-1].read_text(encoding="utf-8"))
            for arm in t1.ARMS:
                stats = t1.arm_stats(batch, arm)
                assert stats["calls"] == report["per_seed"][str(seed)]["new"][arm]["calls"]
                assert stats["token_metrics"] == report["per_seed"][str(seed)]["new"][arm]["token_metrics"]
                n += 1
        assert n == 9


class TestArmStatsSourceLock:
    def test_no_shape_rewrite_and_no_raw_calls(self) -> None:
        import inspect

        source = inspect.getsource(t1.arm_stats)
        assert 'res.get("token_metrics") or {}' not in source
        assert 'tm.get("total_llm_calls")' not in source
        assert 'token_metric_reading(tm, "total_llm_calls")' in source
