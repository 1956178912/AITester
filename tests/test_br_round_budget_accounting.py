"""BR 轮（2026-10-22 第三方集中复审）N02：坏 token 记账必须阻断重试与实例预算。

根因（报告 N02）：`_record_response_usage` 的拒绝分支只查 `COST_BUDGET_ENABLE`，
而 AM1 的实例级 `set_task_token_cap()` 自足生效；env 关闭时拒绝被吞成
`return True`，坏 usage 既不累计也不锁死，重试/故障转移继续付费。修复口径：

1. 有效预算 = env 开关 **或** 实例 cap > 0（与 `check_budget()` 前置守卫一致）；
2. 拒绝时锁存 `budget.exceeded`，后续调用一律快速失败；
3. 抛 `BudgetAccountingError`（继承 `BudgetExceededError`），重试器与故障转移
   均不得吞掉——它是控制流信号，不是瞬态 API 失败。
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.agents.base_agent as ba
from src.agents.llm_client import _record_response_usage, _retry_with_exponential_backoff
from src.budget.cost_budget import (
    BudgetAccountingError,
    BudgetExceededError,
    budget_effective,
    is_budget_exceeded,
    mark_budget_exceeded,
    reset_budget,
    set_task_token_cap,
)
from src.budget.token_usage import reset as reset_usage

_BAD_USAGE = {"input_tokens": "100", "output_tokens": 5}


@pytest.fixture(autouse=True)
def _clean_budget(monkeypatch):
    """每个用例独立的预算/用量线程状态（env 默认关，cap 由用例显式设）。"""
    monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
    reset_budget()
    reset_usage()
    yield
    reset_budget()
    reset_usage()


class TestEffectiveBudgetPredicate:
    def test_env_off_without_cap_is_not_effective(self):
        assert budget_effective() is False

    def test_env_off_with_instance_cap_is_effective(self, monkeypatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        set_task_token_cap(100)
        assert budget_effective() is True

    def test_env_on_is_effective(self, monkeypatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        assert budget_effective() is True

    def test_mark_budget_exceeded_latches(self):
        assert is_budget_exceeded() is False
        mark_budget_exceeded("unit-test")
        assert is_budget_exceeded() is True


class TestRecordResponseUsageRefusal:
    def test_instance_cap_bad_usage_raises_and_locks(self, monkeypatch):
        """分支 B：env 关闭 + 实例 cap 生效 → 必须停止，不得 return True。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        reset_budget()
        set_task_token_cap(100)

        with pytest.raises(BudgetAccountingError, match="记账被拒绝"):
            _record_response_usage(_BAD_USAGE, "m")

        assert is_budget_exceeded() is True

    def test_env_budget_bad_usage_raises_accounting_error(self, monkeypatch):
        """分支 A：env 开启 → 专用异常（不是可重试的裸 RuntimeError）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        reset_budget()

        with pytest.raises(BudgetExceededError):
            _record_response_usage(_BAD_USAGE, "m")

        assert is_budget_exceeded() is True

    def test_accounting_error_is_budget_exceeded_subclass(self):
        """既有 `except BudgetExceededError` 消费点无需改动即可捕获。"""
        assert issubclass(BudgetAccountingError, BudgetExceededError)

    def test_no_effective_budget_keeps_historical_disclosure(self):
        """无任何预算约束时保持历史口径（披露后继续，不锁死）。"""
        assert _record_response_usage(_BAD_USAGE, "m") is True
        assert is_budget_exceeded() is False


class TestRetryChainStops:
    def test_retry_wrapper_does_not_retry_budget_error(self):
        calls = []

        def _boom():
            calls.append(1)
            raise BudgetAccountingError(["token_not_count:input_tokens:str"])

        with pytest.raises(BudgetAccountingError):
            _retry_with_exponential_backoff(
                _boom,
                max_retries=3,
                base_wait=0.01,
                non_retryable_exceptions=(BudgetExceededError,),
                pre_retry_check=lambda: None,
            )

        assert len(calls) == 1  # 首次即止，无 4 次付费请求

    def test_call_llm_does_not_retry_or_failover_on_accounting_error(self, monkeypatch):
        """真实调用链：假 provider 返回坏 usage，invoke 只允许发生一次。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        reset_budget()
        set_task_token_cap(100)
        monkeypatch.setattr(ba, "_get_all_api_configs", lambda: [("k", "https://t.example.com/v1", "m")])

        response = SimpleNamespace(
            usage_metadata={"input_tokens": "100", "output_tokens": 5},
            response_metadata={"finish_reason": "stop"},
            content="ok",
        )
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = response
        monkeypatch.setattr(ba, "_get_or_create_chat_client", lambda *a, **k: fake_llm)

        agent = ba.BaseAgent.__new__(ba.BaseAgent)
        agent.system_prompt = "sys"

        with pytest.raises(BudgetExceededError):
            agent._call_llm("hello")

        assert fake_llm.invoke.call_count == 1
        assert is_budget_exceeded() is True

    def test_call_llm_precheck_blocks_after_latch(self, monkeypatch):
        """锁存后下一次调用在前置守卫即失败（不再发起请求）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        reset_budget()
        set_task_token_cap(100)
        mark_budget_exceeded("previous accounting refusal")
        monkeypatch.setattr(ba, "_get_all_api_configs", lambda: [("k", "https://t.example.com/v1", "m")])
        fake_llm = MagicMock()
        monkeypatch.setattr(ba, "_get_or_create_chat_client", lambda *a, **k: fake_llm)

        agent = ba.BaseAgent.__new__(ba.BaseAgent)
        agent.system_prompt = "sys"

        with pytest.raises(BudgetExceededError):
            agent._call_llm("hello")

        assert fake_llm.invoke.call_count == 0


class TestUnmeasurableLatchSurvivesLegitAccounting:
    """R02（2026-10-23 全量集中复审 P1）：锁存不得被并发合法记账清除。

    复现（报告 M04）：cap=100，坏 usage 先锁存 exceeded=True；随后合法
    10 token 记账——旧 `check_budget()` 按已计量重新计算并把 exceeded
    覆盖回 False、返回放行，共享预算实例下等于解除了坏 usage 任务的停止
    状态。修复后 `unmeasurable_latched` 独立锁存，直至 reset_budget()。
    """

    def test_latch_survives_below_cap_legit_usage(self, monkeypatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        monkeypatch.setenv("COST_BUDGET_USD", "0")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "0")
        monkeypatch.setenv("COST_USD_PER_1K", "0")
        reset_budget()
        set_task_token_cap(100)

        mark_budget_exceeded("mock unmeasurable usage")
        assert is_budget_exceeded() is True

        from src.budget.cost_budget import check_budget

        assert check_budget(10) is False  # 在途合法响应（低于 cap）不得放行
        assert is_budget_exceeded() is True  # 停止位保持
        assert check_budget(0) is False  # 后续前置检查同样拒绝

    def test_latch_cleared_only_by_reset(self, monkeypatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        reset_budget()
        set_task_token_cap(100)

        mark_budget_exceeded("mock")
        reset_budget()  # 任务边界显式 reset 是唯一解除点
        set_task_token_cap(100)

        from src.budget.cost_budget import check_budget

        assert is_budget_exceeded() is False
        assert check_budget(10) is True

    def test_real_exceed_still_blocks_without_latch(self, monkeypatch):
        """对照：未锁存时正常超限语义不变（重新计算可自行触发阻断）。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "false")
        monkeypatch.setenv("COST_BUDGET_USD", "0")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "0")
        monkeypatch.setenv("COST_USD_PER_1K", "0")
        reset_budget()
        set_task_token_cap(100)

        from src.budget.cost_budget import check_budget

        assert check_budget(50) is True
        assert check_budget(60) is False  # 110 >= 100 真实超限
        assert is_budget_exceeded() is True
