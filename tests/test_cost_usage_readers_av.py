"""AV 轮（2026-10-21，零 LLM）：T1/B2 成本链的 token 值域与未知金额形状。

AU 轮把实验侧三个活聚合器接回共享值域后，`analyze_t1_b2_main_batch.add_cost`
（逐 seed 成本，真实批次 18 个读数）仍用 `tm.get(...) or 0`：上游
`token_metrics` 的 `None`（AN 的拒绝）被折成 0，单侧未知变成部分和；
`True` 当 1、负数编出负金额、`nan`/`inf` 进报告、字符串让整次分析抛
`TypeError`。BASELINE 片段渲染又把未知金额印成 YAML 字符串 `None`。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from experiments import analyze_t1_b2_main_batch as t1

_ROOT = Path(__file__).resolve().parents[1]
_BATCH = _ROOT / "experiments/results/t_round_b2_main_batch_20261018"
_REPORT = _BATCH / "ANALYSIS_REPORT.json"
_FRAGMENT = _BATCH / "BASELINE_FRAGMENT.yaml"

_PRICE = {"input_per_mtok": 0.3, "output_per_mtok": 1.2, "currency": "USD"}


def _clean_metrics() -> dict[str, Any]:
    return {"total_input_tokens": 12, "total_output_tokens": 34}


class TestAddCostTokenDomain:
    def test_clean_metrics_price_as_before(self) -> None:
        stats = {"cost_usd": None, "token_metrics": _clean_metrics()}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] == 4.4e-05
        assert "cost_unpriced_reason" not in stats

    @pytest.mark.parametrize("token_metrics", [None, {}], ids=["null", "empty"])
    def test_absent_metrics_keep_historical_zero(self, token_metrics: Any) -> None:
        stats = {"cost_usd": None, "token_metrics": token_metrics}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] == 0.0
        assert "cost_unpriced_reason" not in stats

    def test_metrics_key_absent_keeps_historical_zero(self) -> None:
        stats = {"cost_usd": None}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] == 0.0

    @pytest.mark.parametrize(
        ("field", "reason"),
        [
            ("total_input_tokens", "token_metric_unreadable:total_input_tokens"),
            ("total_output_tokens", "token_metric_unreadable:total_output_tokens"),
        ],
    )
    def test_null_side_blocks_the_whole_amount(self, field: str, reason: str) -> None:
        metrics = _clean_metrics()
        metrics[field] = None
        stats = {"cost_usd": None, "token_metrics": metrics}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == reason

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (True, "token_not_count:total_input_tokens:bool"),
            ("12", "token_not_count:total_input_tokens:str"),
            (1.5, "token_not_count:total_input_tokens:float"),
            (-5, "token_negative:total_input_tokens"),
            (float("nan"), "token_not_finite:total_input_tokens"),
            (float("inf"), "token_not_finite:total_input_tokens"),
        ],
        ids=["bool", "str", "float", "negative", "nan", "inf"],
    )
    def test_bad_counts_are_named_not_multiplied(self, value: Any, reason: str) -> None:
        metrics = _clean_metrics()
        metrics["total_input_tokens"] = value
        stats = {"cost_usd": None, "token_metrics": metrics}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == reason

    def test_non_object_metrics_named_once_without_raising(self) -> None:
        stats = {"cost_usd": None, "token_metrics": "abc"}
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == "token_metrics_not_object:str"

    def test_both_sides_unreadable_keep_both_reasons_in_order(self) -> None:
        stats = {
            "cost_usd": None,
            "token_metrics": {"total_input_tokens": None, "total_output_tokens": "34"},
        }
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == (
            "token_metric_unreadable:total_input_tokens|token_not_count:total_output_tokens:str"
        )

    def test_arm_stats_feed_the_same_gate(self) -> None:
        batch = {
            "results": {
                "aitester": {
                    "details": [],
                    "token_metrics": {"total_input_tokens": True, "total_output_tokens": 34},
                }
            }
        }
        stats = t1.arm_stats(batch, "aitester")
        t1.add_cost(stats, _PRICE)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == "token_not_count:total_input_tokens:bool"


class TestBaselineFragmentMoneyShapes:
    def _report(self) -> dict[str, Any]:
        return json.loads(_REPORT.read_text(encoding="utf-8"))

    def test_unknown_money_renders_yaml_null(self) -> None:
        report = copy.deepcopy(self._report())
        report["cost"]["actual_est_usd"] = None
        report["cost"]["preflight_estimate_usd"] = None
        report["cost"]["amended_estimate_usd"] = None
        report["cost"]["budget_usd"] = None
        report["pooled"]["aitester"]["cost_usd"] = None
        frag = t1.render_baseline_fragment(report)
        assert "actual_est_usd: null" in frag
        assert "preflight_estimate_usd: null" in frag
        assert "amended_estimate_usd: null" in frag
        assert "budget_usd: null" in frag
        assert "cost_usd: null" in frag
        assert "actual_est_usd: None" not in frag
        assert "cost_usd: None" not in frag

    def test_unknown_money_parses_as_none_not_string(self) -> None:
        report = copy.deepcopy(self._report())
        report["cost"]["actual_est_usd"] = None
        report["pooled"]["aitester"]["cost_usd"] = None
        parsed = yaml.safe_load(t1.render_baseline_fragment(report))
        block = parsed["b2_main_batch_t_round"]
        assert block["cost"]["actual_est_usd"] is None
        assert block["pooled_261_per_arm"]["aitester"]["cost_usd"] is None

    def test_real_report_fragment_is_byte_identical(self) -> None:
        if not _FRAGMENT.exists() or not _REPORT.exists():
            pytest.skip("T1/B2 受保护工件不在盘上")
        assert t1.render_baseline_fragment(self._report()) == _FRAGMENT.read_text(encoding="utf-8")

    def test_real_per_seed_costs_reproduce(self) -> None:
        if not _REPORT.exists():
            pytest.skip("T1/B2 受保护工件不在盘上")
        report = self._report()
        entry, reason = t1._load_price_entry(_ROOT / "experiments/price_table.json")
        assert reason is None
        n = 0
        for per in report["per_seed"].values():
            for label in ("new", "original"):
                for stats in (per.get(label) or {}).values():
                    recomputed = {"token_metrics": stats.get("token_metrics")}
                    t1.add_cost(recomputed, entry, reason)
                    assert recomputed.get("cost_usd") == stats.get("cost_usd")
                    n += 1
        assert n == 18
