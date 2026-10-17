"""D1（N-5）回归锁：COST_BUDGET_USD 生产记账接线（USD 上限真实生效）。

背景（N-4 真实 LLM 探针实测 D1，P0）
------------------------------------
`COST_BUDGET_USD` 此前是"纸面开关"：`llm_client._record_response_usage` 只把
token 增量传给 `check_budget`，`consumed_delta_usd` 恒 0 →
`BudgetSnapshot.consumed_usd` 恒 0 → USD 上限永不触发。

N-5 修复：新增 `src/budget/pricing.py`（价目表 USD 估算，回退
`COST_USD_PER_1K`，无价目**不编造价格**并记审计事件）；`_record_response_usage`
在预算启用时计算 USD 增量并走 `record_usage_and_check`——token 与 USD 两通道
在同一 `budget.exceeded` 标志上触发停止通道；`COST_BUDGET_ENABLE=false`
零行为差异（不做价目 IO）。

本文件锁定：
1. 价目估算（price_table 命中 / 非 USD / 未登记 / 缺失文件 / 回退价 / 零与负 token）；
2. 预算累计与触发（consumed_usd 不再恒 0；USD 与 token 同口径 exceeded/停止）；
3. 生产接线（`_record_response_usage`：priced/unpriced/disabled/回退价/异常 fail-closed）；
4. 审计面（process stats `usd_pricing_unavailable_events`、一次性 WARNING、
   `BudgetExceededError.unit == "usd"`）。
"""

from __future__ import annotations

import json
import logging

import pytest

from src.budget import cost_budget, pricing
from src.budget.cost_budget import (
    BudgetExceededError,
    check_budget,
    get_budget_stats,
    get_process_budget_stats,
    is_budget_exceeded,
    record_usage_and_check,
    reset_budget,
)

_KEY_ENV = ("COST_BUDGET_ENABLE", "COST_BUDGET_TOKENS", "COST_BUDGET_USD", "COST_USD_PER_1K")


@pytest.fixture(autouse=True)
def _clean_budget_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例独立：清预算 env / 线程快照 / 价目缓存 / 未计价告警去重。"""
    for key in _KEY_ENV:
        monkeypatch.delenv(key, raising=False)
    reset_budget()
    pricing.reset_price_table_cache()
    cost_budget._usd_unpriced_warned.clear()


# ─────────────────────────── 1. 价目估算 ───────────────────────────


class TestPricingEstimate:
    def test_price_table_known_model(self) -> None:
        """deepseek-flash：in $0.3/M、out $1.2/M（price_table.json 登记口径）。"""
        usd, source = pricing.estimate_usd("deepseek-flash", 1_000_000, 1_000_000)
        assert usd == pytest.approx(1.5, rel=1e-9)
        assert source == "price_table:deepseek-flash"

    def test_known_model_small_usage(self) -> None:
        usd, source = pricing.estimate_usd("deepseek-flash", 1000, 500)
        assert usd == pytest.approx(1000 * 0.3 / 1e6 + 500 * 1.2 / 1e6)
        assert source.startswith("price_table:")

    def test_zero_tokens_zero_usd(self) -> None:
        assert pricing.estimate_usd("deepseek-flash", 0, 0) == (0.0, "zero_tokens")

    def test_negative_tokens_clamped(self) -> None:
        usd, _ = pricing.estimate_usd("deepseek-flash", -100, 10)
        assert usd is not None and usd >= 0
        assert usd == pytest.approx(10 * 1.2 / 1e6)

    def test_unpriced_model_returns_none(self) -> None:
        """未登记模型：不编造价格（None），由调用方记审计事件。"""
        assert pricing.estimate_usd("unknown-model", 100, 100) == (None, "unpriced")

    def test_non_usd_currency_treated_unpriced(self) -> None:
        """qwen-long 价目为 CNY → 无汇率事实源，不换算（诚实条款）。"""
        usd, source = pricing.estimate_usd("qwen-long", 1_000_000, 0)
        assert usd is None and source == "unpriced"

    def test_cost_usd_per_1k_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_USD_PER_1K", "2.0")
        usd, source = pricing.estimate_usd("unknown-model", 1000, 500)
        assert usd == pytest.approx(1.5 * 2.0)
        assert source == "cost_usd_per_1k"

    def test_bad_fallback_value_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """回退价坏值不在 pricing 层 fail-closed（check_budget 已 fail-closed），
        pricing 按"未配置"处理 → unpriced（不重复计数/重复告警）。"""
        monkeypatch.setenv("COST_USD_PER_1K", "0.0O6")
        assert pricing.estimate_usd("unknown-model", 10, 10) == (None, "unpriced")

    def test_missing_price_table_degrades(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", tmp_path / "missing.json")
        pricing.reset_price_table_cache()
        monkeypatch.setenv("COST_USD_PER_1K", "1.0")
        usd, source = pricing.estimate_usd("deepseek-flash", 1000, 0)
        assert usd == pytest.approx(1.0)  # 回退价：1000/1000 * 1.0
        assert source == "cost_usd_per_1k"

    def test_malformed_price_table_degrades(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        bad = tmp_path / "price_table.json"
        bad.write_text("{not-json", encoding="utf-8")
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", bad)
        pricing.reset_price_table_cache()
        assert pricing.estimate_usd("deepseek-flash", 1000, 0) == (None, "unpriced")

    def test_cache_reset_picks_up_changes(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        table = tmp_path / "price_table.json"
        table.write_text(
            json.dumps({"models": {"m1": {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "currency": "USD"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", table)
        pricing.reset_price_table_cache()
        assert pricing.estimate_usd("m1", 1_000_000, 0)[0] == pytest.approx(1.0)
        table.write_text(
            json.dumps({"models": {"m1": {"input_per_mtok": 2.0, "output_per_mtok": 4.0, "currency": "USD"}}}),
            encoding="utf-8",
        )
        pricing.reset_price_table_cache()
        assert pricing.estimate_usd("m1", 1_000_000, 0)[0] == pytest.approx(2.0)


# ─────────────────────────── 2. 预算累计/触发 ───────────────────────────


class TestUsdBudgetAccumulation:
    def test_usd_exceeded_without_per_1k_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """D1 核心：USD 增量由内部计价产生时，无需 COST_USD_PER_1K 也须触发。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.001")
        assert check_budget(consumed_delta_usd=0.0004) is True
        assert check_budget(consumed_delta_usd=0.0007) is False
        assert is_budget_exceeded() is True
        stats = get_budget_stats()
        assert stats["consumed_usd"] == pytest.approx(0.0011)
        assert stats["unit"] == "usd"
        assert stats["exceeded"] is True

    def test_explicit_usd_when_per_1k_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.01")
        monkeypatch.setenv("COST_USD_PER_1K", "1.0")
        assert check_budget(consumed_delta_usd=0.009) is True
        assert check_budget(consumed_delta_usd=0.002) is False

    def test_disabled_zero_behavior_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """COST_BUDGET_ENABLE 未设：开关前置早退，不记账/不触发（历史口径零差异）。"""
        assert check_budget(consumed_delta_usd=999.0) is True
        assert get_budget_stats()["consumed_usd"] == 0.0  # 关闭时不做任何记账（历史口径）
        assert is_budget_exceeded() is False

    def test_bad_per_1k_still_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "1.0")
        monkeypatch.setenv("COST_USD_PER_1K", "0.0O6")
        assert check_budget(consumed_delta_usd=0.0) is False
        assert get_process_budget_stats()["budget_misconfigured_events"] >= 1

    def test_record_usage_and_check_production_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`record_usage_and_check(usd_cost=...)` 是生产消费入口（D1 前零调用）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.001")
        assert record_usage_and_check(1000, 500, usd_cost=0.0005) is True
        assert record_usage_and_check(1, 1, usd_cost=0.0006) is False


# ─────────────────────────── 3. 生产接线（_record_response_usage） ───────────────────────────


class TestLlmClientUsdWiring:
    def _usage(self, input_tokens: int = 2000, output_tokens: int = 1000) -> dict[str, int]:
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def test_priced_model_records_usd_and_triggers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """D1 修复主断言：priced 模型记账后 consumed_usd 非 0 且 USD 上限触发。"""
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.0005")
        reset_budget()
        allowed = _record_response_usage(self._usage(), "deepseek-flash")
        stats = get_budget_stats()
        expected = 2000 * 0.3 / 1e6 + 1000 * 1.2 / 1e6
        assert stats["consumed_usd"] == pytest.approx(expected), "consumed_usd 仍为 0（D1 复发）"
        assert allowed is False and stats["exceeded"] is True
        assert get_process_budget_stats()["budget_exceeded_events"] >= 1
        err = __import__("src.agents.base_agent", fromlist=["_budget_exceeded_error"])._budget_exceeded_error()
        assert isinstance(err, BudgetExceededError)
        assert err.unit == "usd"
        # 可诊断性：USD 口径下异常消息的数值/单位必须同口径（不得把 token 数
        # 当美元展示，也不得显示 token_limit=0 作为 USD 上限）。
        assert "$" in str(err), f"USD 异常消息缺美元符号：{err}"
        assert "$0.000" in str(err) or "$0.00" in str(err)
        assert err.consumed == pytest.approx(2000 * 0.3 / 1e6 + 1000 * 1.2 / 1e6)
        assert err.limit == pytest.approx(0.0005)
        assert "tokens" not in str(err)

    def test_token_and_usd_share_stop_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """USD 触发与 token 触发走同一 exceeded 标志（同口径停止通道）。"""
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100000")  # token 侧远未到
        monkeypatch.setenv("COST_BUDGET_USD", "0.0001")
        reset_budget()
        assert _record_response_usage(self._usage(), "deepseek-flash") is False
        assert is_budget_exceeded() is True

    def test_disabled_does_not_touch_pricing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """disabled 零差异：不触发价目计算（即使估算器抛异常也不影响主流程）。"""
        from src.agents import llm_client

        monkeypatch.delenv("COST_BUDGET_ENABLE", raising=False)
        monkeypatch.setattr(
            "src.budget.pricing.estimate_usd",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("disabled 时不得调用 pricing")),
        )
        reset_budget()
        assert llm_client._record_response_usage(self._usage(), "deepseek-flash") is True
        assert get_budget_stats()["consumed_usd"] == 0.0

    def test_unpriced_model_audited_not_fabricated(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.000001")
        reset_budget()
        before = get_process_budget_stats()["usd_pricing_unavailable_events"]
        with caplog.at_level(logging.WARNING):
            allowed = _record_response_usage(self._usage(100, 10), "unregistered-model")
        assert allowed is True, "无价目不应因未知价格误杀"
        assert get_budget_stats()["consumed_usd"] == 0.0, "无价目不得编造 USD"
        assert get_process_budget_stats()["usd_pricing_unavailable_events"] == before + 1
        assert any("无可用美元价目" in rec.getMessage() for rec in caplog.records), "缺一次性可诊断告警"

    def test_fallback_price_used_when_model_unpriced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "10")
        monkeypatch.setenv("COST_USD_PER_1K", "1.0")
        reset_budget()
        before = get_process_budget_stats()["usd_pricing_unavailable_events"]
        assert _record_response_usage(self._usage(2100, 0), "unregistered-model") is True
        assert get_budget_stats()["consumed_usd"] == pytest.approx(2.1)  # 2100/1000*1.0
        assert get_process_budget_stats()["usd_pricing_unavailable_events"] == before

    def test_pricing_exception_fail_closed_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """O14 口径：预算启用时记账异常 fail-closed 上抛（不静默吞）。"""
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "1.0")
        monkeypatch.setattr(
            "src.budget.pricing.estimate_usd",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pricing boom")),
        )
        reset_budget()
        with pytest.raises(RuntimeError, match="预算记账异常"):
            _record_response_usage(self._usage(), "deepseek-flash")

    def test_multi_provider_price_missing_policy_documented(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多 provider 价格缺失策略：不编造价格、不误杀、审计可见（不是静默 0）。"""
        from src.agents.llm_client import _record_response_usage

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.00001")
        reset_budget()
        for model in ("agnes-3.0-flash", "qwen-long"):
            assert _record_response_usage(self._usage(10, 10), model) is True
        stats = get_process_budget_stats()
        assert stats["usd_pricing_unavailable_events"] >= 2
        assert get_budget_stats()["consumed_usd"] == 0.0
