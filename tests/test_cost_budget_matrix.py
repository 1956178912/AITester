#!/usr/bin/env python3
"""覆盖率补口 + 成本闸语义锁定：任务级预算（`src/budget/cost_budget.py`）。

动机（EMSE 多轮优化批次）：预算闸是**成本主张的可信度底座**——
论文报告 `$/task 0.0259 vs 0.0045`，若闸本身有分支未测，
"成本受控"就只是自述。该模块的四个环境解析函数（开关 / token 上限 /
费用上限 / 单价）此前各有一半分支未覆盖。

覆盖目标（coverage.xml 记录）：54-55、62-63、70-71 行（三个解析函数的
异常回退分支）。
零 LLM、零网络、无线程外副作用。
"""

from __future__ import annotations

import pytest

from src.budget.cost_budget import (
    BudgetExceededError,
    BudgetSnapshot,
    _budget_enabled,
    _budget_tokens_limit,
    _budget_usd_limit,
    _usd_per_1k,
    attach_budget,
    check_budget,
    current_budget,
    get_budget_stats,
    get_process_budget_stats,
    is_budget_exceeded,
    record_usage_and_check,
    reset_budget,
    set_task_token_cap,
)


@pytest.fixture(autouse=True)
def _reset_budget_state() -> None:
    """每个用例前后复位线程局部/进程级状态（防跨用例污染）。"""
    reset_budget()
    yield
    reset_budget()


class TestEnvParsingBranches:
    """四个解析函数的"合法 / 非法 / 缺省"三态——非法值必须回退默认（不是 0）。"""

    def test_budget_enabled_values(self, monkeypatch: pytest.MonkeyPatch):
        for raw, expected in (("true", True), ("1", True), ("on", True), ("false", False), ("", False)):
            monkeypatch.setenv("COST_BUDGET_ENABLE", raw)
            assert _budget_enabled() is expected, raw

    def test_tokens_limit_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_TOKENS", "50000")
        assert _budget_tokens_limit() == 50000
        monkeypatch.setenv("COST_BUDGET_TOKENS", "not-a-number")
        assert _budget_tokens_limit() == 0  # 非法 → 不限（0），不抛异常

    def test_usd_limit_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_USD", "1.25")
        assert _budget_usd_limit() == pytest.approx(1.25)
        monkeypatch.setenv("COST_BUDGET_USD", "abc")
        assert _budget_usd_limit() == 0

    def test_usd_per_1k_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_USD_PER_1K", "0.002")
        assert _usd_per_1k() == pytest.approx(0.002)
        monkeypatch.setenv("COST_USD_PER_1K", "N/A")
        assert _usd_per_1k() == 0


class TestBudgetGate:
    def test_disabled_budget_always_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1")
        assert check_budget(consumed_delta_tokens=10_000) is True

    def test_token_cap_blocks_after_limit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1000")
        assert check_budget(consumed_delta_tokens=500) is True
        assert check_budget(consumed_delta_tokens=600) is False
        assert is_budget_exceeded() is True

    def test_usd_cap_requires_price_table(self, monkeypatch: pytest.MonkeyPatch):
        """费用口径在未配单价时不生效（默认 0 → 不因费用拦任务）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "0")
        monkeypatch.setenv("COST_BUDGET_USD", "0.001")
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        assert check_budget(consumed_delta_tokens=10_000_000) is True

    def test_usd_cap_blocks_with_price_table(self, monkeypatch: pytest.MonkeyPatch):
        """USD 侧需 `COST_BUDGET_USD > 0` **且** `COST_USD_PER_1K > 0`，
        且费用由调用方通过 `consumed_delta_usd` 传入（tokens 不自动换算）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100000")
        monkeypatch.setenv("COST_BUDGET_USD", "0.01")
        monkeypatch.setenv("COST_USD_PER_1K", "1.0")
        assert check_budget(consumed_delta_tokens=1, consumed_delta_usd=0.005) is True
        assert check_budget(consumed_delta_tokens=1, consumed_delta_usd=0.006) is False

    def test_usd_side_inactive_without_price_table(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100000")
        monkeypatch.setenv("COST_BUDGET_USD", "0.001")
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        assert check_budget(consumed_delta_tokens=1, consumed_delta_usd=999.0) is True

    def test_record_usage_and_check_accumulates(self, monkeypatch: pytest.MonkeyPatch):
        """累计到上限才拦（限 200：3×60=180 通过，第 4 次 240 超限）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "200")
        assert record_usage_and_check(30, 30) is True
        assert record_usage_and_check(30, 30) is True
        assert record_usage_and_check(30, 30) is True
        assert record_usage_and_check(30, 30) is False

    def test_budget_exceeded_error_carries_context(self):
        err = BudgetExceededError(consumed=120, limit=100, unit="tokens")
        assert err.consumed == 120 and err.limit == 100 and err.unit == "tokens"
        assert "100" in str(err) and "tokens" in str(err)

    def test_snapshot_and_stats_shapes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "200")
        set_task_token_cap(150)
        snap = current_budget()
        assert isinstance(snap, BudgetSnapshot)
        stats = get_budget_stats()
        assert isinstance(stats, dict)
        proc = get_process_budget_stats()
        assert isinstance(proc, dict)

    def test_attach_budget_overrides_thread_state(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1000")
        attach_budget(BudgetSnapshot(consumed_tokens=999, token_limit=1000))
        assert is_budget_exceeded() is False
        assert current_budget().consumed_tokens >= 999
