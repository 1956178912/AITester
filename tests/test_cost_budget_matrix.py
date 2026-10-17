#!/usr/bin/env python3
"""覆盖率补口 + 成本闸语义锁定：任务级预算（`src/budget/cost_budget.py`）。

动机（EMSE 多轮优化批次）：预算闸是**成本主张的可信度底座**——
论文报告 `$/task 0.0259 vs 0.0045`，若闸本身有分支未测，
"成本受控"就只是自述。该模块的环境解析（开关 / token 上限 / 费用上限 /
单价）此前各有一半分支未覆盖。

G 轮（2026-10-16）口径变更：三项数值配置收敛到单一解析器
``_read_budget_number``，返回值补"是否可用"位——坏值（拼错、负数）不再
回退成 ``0 = 不限``，而是让 ``check_budget`` fail-closed。原"异常回退分支"
（旧 54-55 / 62-63 / 70-71 行）随之消失，本文件改为锁定新三态语义。
零 LLM、零网络、无线程外副作用。
"""

from __future__ import annotations

import pytest

from src.budget.cost_budget import (
    BudgetExceededError,
    BudgetSnapshot,
    _budget_enabled,
    _read_budget_number,
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
    """配置解析的"合法 / 非法 / 缺省"三态（G 轮起坏值 ≠ 未配置）。"""

    def test_budget_enabled_values(self, monkeypatch: pytest.MonkeyPatch):
        for raw, expected in (("true", True), ("1", True), ("on", True), ("false", False), ("", False)):
            monkeypatch.setenv("COST_BUDGET_ENABLE", raw)
            assert _budget_enabled() is expected, raw

    def test_tokens_limit_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        """（G 轮口径变更披露）此前坏值断言为 `== 0`，注释写"非法 → 不限（0），
        不抛异常"——即开了预算闸却拼错上限时守卫**静默失效、无上限烧 token**。
        现坏值返回 ``(0, False)``，由 check_budget fail-closed。
        """
        monkeypatch.setenv("COST_BUDGET_TOKENS", "50000")
        assert _read_budget_number("COST_BUDGET_TOKENS", integer=True) == (50000, True)
        monkeypatch.setenv("COST_BUDGET_TOKENS", "not-a-number")
        assert _read_budget_number("COST_BUDGET_TOKENS", integer=True) == (0, False)

    def test_usd_limit_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_USD", "1.25")
        assert _read_budget_number("COST_BUDGET_USD", integer=False) == (1.25, True)
        monkeypatch.setenv("COST_BUDGET_USD", "abc")
        assert _read_budget_number("COST_BUDGET_USD", integer=False) == (0, False)

    def test_usd_per_1k_parses_and_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_USD_PER_1K", "0.002")
        assert _read_budget_number("COST_USD_PER_1K", integer=False) == (0.002, True)
        monkeypatch.setenv("COST_USD_PER_1K", "N/A")
        assert _read_budget_number("COST_USD_PER_1K", integer=False) == (0, False)

    def test_unset_or_blank_is_legitimate_not_misconfigured(self, monkeypatch: pytest.MonkeyPatch):
        """未设置 / 空串 = 合法的"未配置"（可用位 True），不得触发 fail-closed。"""
        monkeypatch.delenv("COST_BUDGET_TOKENS", raising=False)
        assert _read_budget_number("COST_BUDGET_TOKENS", integer=True) == (0, True)
        monkeypatch.setenv("COST_BUDGET_TOKENS", "   ")
        assert _read_budget_number("COST_BUDGET_TOKENS", integer=True) == (0, True)

    def test_negative_limit_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """负上限是配置错误（不是"不限"），同样 fail-closed。"""
        monkeypatch.setenv("COST_BUDGET_TOKENS", "-1")
        assert _read_budget_number("COST_BUDGET_TOKENS", integer=True) == (0, False)


class TestMisconfiguredFailClosed:
    """G 轮：预算闸启用但配置坏值 → 阻断 LLM 调用（不得静默无上限）。"""

    def test_bad_tokens_limit_blocks_llm_calls(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "500k")
        reset_budget()
        assert check_budget(consumed_delta_tokens=1) is False
        assert is_budget_exceeded() is True

    def test_bad_usd_per_1k_blocks_llm_calls(self, monkeypatch: pytest.MonkeyPatch):
        """单价拼错（字母 O）此前让费用口径静默失效，现阻断。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "1000")
        monkeypatch.setenv("COST_USD_PER_1K", "0.0O6")
        reset_budget()
        assert check_budget(consumed_delta_tokens=1) is False

    def test_misconfig_counted_separately_from_real_exceed(self, monkeypatch: pytest.MonkeyPatch):
        """配置错误单独计数，不污染"任务烧爆预算"的超限事件数。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "abc")
        reset_budget()
        before = get_process_budget_stats()
        check_budget(consumed_delta_tokens=1)
        after = get_process_budget_stats()
        assert after["budget_misconfigured_events"] == before["budget_misconfigured_events"] + 1
        assert after["budget_exceeded_events"] == before["budget_exceeded_events"]
        assert after["tasks_capped"] == before["tasks_capped"] + 1

    def test_switch_off_bad_value_keeps_historical_behavior(self, monkeypatch: pytest.MonkeyPatch):
        """开关关闭时坏值不阻断——守卫未启用即不裁决（历史口径零变化）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "abc")
        reset_budget()
        assert check_budget(consumed_delta_tokens=10) is True

    def test_valid_config_still_enforces_limit(self, monkeypatch: pytest.MonkeyPatch):
        """合法配置行为不变：未达上限放行，达到即阻断。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100")
        reset_budget()
        assert check_budget(consumed_delta_tokens=50) is True
        assert check_budget(consumed_delta_tokens=60) is False


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
        """仅 token 增量不自动计价（USD 由生产接线经 pricing 计算；check_budget 本身
        不根据 token 推算 USD）→ 未传 usd 时不因费用拦任务。"""
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

    def test_usd_side_active_without_per_1k_config(self, monkeypatch: pytest.MonkeyPatch):
        """D1（N-5）口径更新：显式 USD 增量不再依赖 COST_USD_PER_1K 配置。

        旧口径把"是否配置 COST_USD_PER_1K"当作 USD 侧生效闸（且生产路径从未传
        usd → USD 上限恒不触发，N-4 D1）。现 USD 增量由生产接线按价目表计算，
        显式 delta 直接累计判定；本用例锁"无 per_1k 仍触发"。
        """
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100000")
        monkeypatch.setenv("COST_BUDGET_USD", "0.001")
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        assert check_budget(consumed_delta_tokens=1, consumed_delta_usd=0.0005) is True
        assert check_budget(consumed_delta_tokens=1, consumed_delta_usd=999.0) is False

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
