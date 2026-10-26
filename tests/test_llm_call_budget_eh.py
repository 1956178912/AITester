"""EH 轮：LLM 全局预算（`LLM_CALL_BUDGET_SECONDS`）的兑现面。

背景（文档承诺 vs 实现）：
- `docs/COST_MODEL.md`：单次调用墙钟上限「超限快速失败，不继续发请求」；
- `config.py`：预算覆盖「故障转移 × 模型 × 重试」整段，超出即快速失败。

实现有两处缺口，承诺因此不成立：
1. **墙钟源**：截止点用 `time.time()` 计算。NTP 阶跃校正 / VM 快照恢复 /
   笔记本改时间都会让墙钟回拨，截止点随之后移——预算永不触发，单任务
   仍可无限卡住（这正是 0.7 债务项 2.2 要防的事故）。项目自身在
   `src/api/api_health.py` 已把熔断冷却定为 monotonic 口径并写明
   「不受系统时间回拨影响」，调用预算应与之一致。
2. **检查粒度**：截止检查只在「换模型/换 API」时进行。同一模型内的
   重试阶梯（1s/2s/4s）与 429 退避（最长 30s）在越预算后仍会继续
   **发请求**，与「不继续发请求」相反；最后一个模型耗尽预算时最终抛出的
   还是「已尝试所有 API」，预算信号被吞掉。

纪律：零 LLM、零网络、零真实等待——`time.monotonic` 换成可手动推进的
假时钟，`time.sleep` 换成「记录时长 + 推进假时钟」，`invoke` 用 fake 客户端。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.agents import base_agent

_CFG = [("key-1", "https://api.example.com/v1", "model-1")]


class _Clock:
    """可手动推进的单调时钟替身（`__call__` 无副作用，可安全重复读取）。"""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> tuple[_Clock, list[float]]:
    """把 `base_agent` 看到的 monotonic 与 sleep 都接到假时钟上。"""
    fake = _Clock()
    sleeps: list[float] = []
    monkeypatch.setattr(base_agent.time, "monotonic", fake)

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake.advance(seconds)

    monkeypatch.setattr(base_agent.time, "sleep", _sleep)
    return fake, sleeps


def _agent() -> base_agent.BaseAgent:
    agent = base_agent.BaseAgent.__new__(base_agent.BaseAgent)
    agent.system_prompt = "sys"
    return agent


def _patch_configs(monkeypatch: pytest.MonkeyPatch, configs: list[tuple[str, str, str]] | None = None) -> None:
    monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(configs or _CFG))


class TestBudgetClockSource:
    """缺口 1：截止判定必须与墙钟解耦。"""

    def test_deadline_survives_wall_clock_rollback(self, clock: tuple[_Clock, list[float]], monkeypatch):
        """墙钟回拨（甚至停走）时预算仍按真实流逝时间触发。

        构造：假 monotonic 在「建客户端」阶段推进 11s（预算 10s）；墙钟冻结
        在 1000.0。旧实现用 time.time() 算截止点与判定，永远越不过预算，
        会把请求发出去；新实现 monotonic 已越限，必须在发请求前失败。
        """
        fake, _ = clock
        monkeypatch.setattr(base_agent, "LLM_CALL_BUDGET_SECONDS", 10)
        monkeypatch.setattr(base_agent.time, "time", lambda: 1_000.0)
        _patch_configs(monkeypatch)
        calls = {"invoke": 0}

        def _invoke(messages: Any, **kwargs: Any) -> Any:
            calls["invoke"] += 1
            return SimpleNamespace(content="ok", response_metadata={"finish_reason": "stop"})

        def _client(*args: Any, **kwargs: Any) -> Any:
            fake.advance(11.0)
            return SimpleNamespace(invoke=_invoke)

        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", _client)

        with pytest.raises(RuntimeError, match="全局预算"):
            _agent()._call_llm("hello")
        assert calls["invoke"] == 0, "预算耗尽后不得再发请求"

    def test_deadline_not_derived_from_wall_clock(self, clock: tuple[_Clock, list[float]], monkeypatch):
        """预算截止点不得再由 time.time() 派生（源码锁，防回潮）。"""
        assert "time.time() + LLM_CALL_BUDGET_SECONDS" not in Path(base_agent.__file__).read_text(encoding="utf-8")
        assert "time.monotonic() + LLM_CALL_BUDGET_SECONDS" in Path(base_agent.__file__).read_text(encoding="utf-8")


class TestBudgetPerRequest:
    """缺口 2：预算检查必须发生在每一次真实请求之前。"""

    def test_retry_ladder_cannot_outlive_budget(self, clock: tuple[_Clock, list[float]], monkeypatch):
        """重试退避把预算耗尽后，不得再发下一次请求。

        预算 5s；退避 1s+2s+4s：第 3 次请求后假时钟到 7s（>5s），第 4 次
        重试必须被预算拦下。旧实现只在换模型时检查，会发满 4 次请求，最后
        以「已尝试所有 API」收口——预算信号被吞。
        """
        _, sleeps = clock
        monkeypatch.setattr(base_agent, "LLM_CALL_BUDGET_SECONDS", 5)
        _patch_configs(monkeypatch)
        calls = {"invoke": 0}

        def _invoke(messages: Any, **kwargs: Any) -> Any:
            calls["invoke"] += 1
            raise RuntimeError("network boom")

        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: SimpleNamespace(invoke=_invoke))

        with pytest.raises(RuntimeError, match="全局预算"):
            _agent()._call_llm("hello", max_retries=3)
        assert calls["invoke"] == 3, "第 4 次请求发生在预算耗尽之后，必须被拦下"
        assert sleeps == [1, 2, 4]

    def test_rate_limit_wait_clamped_to_remaining_budget(self, clock: tuple[_Clock, list[float]], monkeypatch):
        """429 退避不得超过剩余预算（旧行为固定睡 30s）。"""
        fake, sleeps = clock
        monkeypatch.setattr(base_agent, "LLM_CALL_BUDGET_SECONDS", 10)
        _patch_configs(monkeypatch)
        monkeypatch.setattr(base_agent, "_is_rate_limit_error", lambda e: True)
        monkeypatch.setattr(base_agent, "_extract_retry_after_seconds", lambda e: 30.0)

        def _invoke(messages: Any, **kwargs: Any) -> Any:
            fake.advance(9.5)
            raise RuntimeError("429 too many requests")

        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: SimpleNamespace(invoke=_invoke))

        with pytest.raises(RuntimeError, match="全局预算"):
            _agent()._call_llm("hello", max_retries=0)
        assert sleeps == [0.5], "只允许睡到预算截止点，不得睡满 30s"

    def test_budget_is_runtime_error_for_callers(self):
        """预算异常保持 RuntimeError 兼容面（既有调用方只捕 RuntimeError）。"""
        assert issubclass(base_agent.LlmCallBudgetExceeded, RuntimeError)


class TestBudgetWithinLimits:
    """预算内零行为变化：正常调用照常返回。"""

    def test_within_budget_call_succeeds(self, clock: tuple[_Clock, list[float]], monkeypatch):
        fake, sleeps = clock
        monkeypatch.setattr(base_agent, "LLM_CALL_BUDGET_SECONDS", 600)
        _patch_configs(monkeypatch)

        def _invoke(messages: Any, **kwargs: Any) -> Any:
            fake.advance(1.0)
            return SimpleNamespace(
                content="  ok  ",
                response_metadata={"finish_reason": "stop"},
                usage_metadata=None,
            )

        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: SimpleNamespace(invoke=_invoke))

        assert _agent()._call_llm("hello") == "ok"
        assert sleeps == []
