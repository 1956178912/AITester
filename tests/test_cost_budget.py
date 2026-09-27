"""
5.4 任务级 LLM token/费用预算硬上限单元测试（cost_budget 模块）。

覆盖：
- 开关默认关闭（历史口径零行为变化）；
- token 预算：超限时 check_budget 返回 False + BudgetExceededError 可构造；
- 费用预算：需 COST_USD_PER_1K 配合才生效；
- 线程局部隔离（--parallel 口径）与 reset_budget；
- 进程级统计（get_process_budget_stats）。
"""

from __future__ import annotations

import pytest

from src.graph.cost_budget import (
    BudgetExceededError,
    check_budget,
    get_budget_stats,
    get_process_budget_stats,
    is_budget_exceeded,
    record_usage_and_check,
    reset_budget,
)


@pytest.fixture(autouse=True)
def _clean_budget_env(monkeypatch):
    """每个用例前重置预算相关环境变量（默认关）。"""
    monkeypatch.delenv("COST_BUDGET_ENABLE", raising=False)
    monkeypatch.delenv("COST_BUDGET_TOKENS", raising=False)
    monkeypatch.delenv("COST_BUDGET_USD", raising=False)
    monkeypatch.delenv("COST_USD_PER_1K", raising=False)
    reset_budget()
    yield
    reset_budget()


class TestBudgetDisabled:
    """默认关闭：全部调用返回 True（历史口径）。"""

    def test_check_budget_disabled_always_true(self) -> None:
        for i in range(100):
            assert check_budget(consumed_delta_tokens=1000) is True

    def test_record_usage_and_check_disabled(self) -> None:
        assert record_usage_and_check(5000, 5000) is True

    def test_is_budget_exceeded_false_when_disabled(self) -> None:
        assert is_budget_exceeded() is False

    def test_snapshot_default(self) -> None:
        s = get_budget_stats()
        assert s["enabled"] is False
        assert s["exceeded"] is False
        assert s["unit"] == "none"


class TestTokenBudget:
    """COST_BUDGET_ENABLE=true + COST_BUDGET_TOKENS 上限。"""

    def test_within_budget_allows(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1000")
        assert check_budget(consumed_delta_tokens=600) is True
        assert is_budget_exceeded() is False

    def test_exceeds_budget_blocks(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1000")
        assert check_budget(consumed_delta_tokens=1500) is False
        assert is_budget_exceeded() is True
        s = get_budget_stats()
        assert s["exceeded"] is True
        assert s["consumed_tokens"] == 1500
        assert s["token_limit"] == 1000

    def test_zero_limit_means_unlimited(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.delenv("COST_BUDGET_TOKENS", raising=False)
        # 无 token 上限且无费用上限 → 永不超限
        assert check_budget(consumed_delta_tokens=10**9) is True

    def test_budget_error_message(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100")
        check_budget(consumed_delta_tokens=100)
        err = BudgetExceededError(consumed=100, limit=100, unit="tokens")
        assert "预算耗尽" in str(err)
        assert err.consumed == 100


class TestUsdBudget:
    """费用口径：COST_BUDGET_USD 需 COST_USD_PER_1K 配合。"""

    def test_usd_without_price_disabled(self, monkeypatch) -> None:
        """未配费用单价时费用上限不生效（保守：无计价信息不封顶）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.01")
        # 无 COST_USD_PER_1K → 费用口径不生效，token 口径未配 → 永不超限
        assert check_budget(consumed_delta_usd=10.0) is True

    def test_usd_exceeded_blocks(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_USD", "0.01")
        monkeypatch.setenv("COST_USD_PER_1K", "0.001")
        # 记录 10000 tokens（=$0.01）达到上限
        assert check_budget(consumed_delta_tokens=10000) is True  # 未配 token 上限
        # 注意：check_budget 的 usd 累计来自 consumed_delta_usd 参数（费用口径
        # 由调用方按 COST_USD_PER_1K 换算后传入），token 消耗本身不自动计价。
        assert check_budget(consumed_delta_tokens=10000, consumed_delta_usd=0.02) is False


class TestThreadIsolation:
    """线程局部累计（--parallel 每任务独立口径，与 token_usage 一致）。"""

    def test_reset_budget_resets_consumed(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100")
        check_budget(consumed_delta_tokens=100)
        assert is_budget_exceeded() is True
        reset_budget()
        assert is_budget_exceeded() is False
        assert get_budget_stats()["consumed_tokens"] == 0


class TestProcessStats:
    """进程级预算统计（观测层）。"""

    def test_exceeded_event_counted(self, monkeypatch) -> None:
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "10")
        before = get_process_budget_stats()["budget_exceeded_events"]
        check_budget(consumed_delta_tokens=10)
        after = get_process_budget_stats()
        assert after["budget_exceeded_events"] == before + 1
        assert after["tasks_capped"] >= 1
