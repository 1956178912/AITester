"""EI 轮（2026-10-27）：单次调用时间预算必须兑现 5.4 预算封顶判定面。

背景：EH 轮把 `LLM_CALL_BUDGET_SECONDS` 的判定改成 monotonic + 每次请求前
复查，并引入 `LlmCallBudgetExceeded` 作为确定性控制流信号。但该类被建成
`RuntimeError` 的**兄弟类**，而编排层所有"预算封顶"读者只认
`BudgetExceededError`：

- `_planner_node` / `_generator_node` / `_debugger_node` 的
  `isinstance(e, BudgetExceededError)` → 超时只走一般故障降级；
- 三节点据此写 `state["budget_exceeded"]` → `determine_stop_reason` 的
  `StopReason.BUDGET_EXCEEDED` 永不产生。

后果：时间预算封顶在工件里被记成"未知故障"，实验口径把"卡死被止损"与
"LLM 真故障"混为一谈，`.env.example` 承诺的"触发 5.4 预算封顶"未兑现。

本文件锁定修复后的口径：
1. `LlmCallBudgetExceeded` 是 `BudgetExceededError` 子类，且携带秒级
   口径（`unit="seconds"`、`limit=配置值`、`consumed=None` 表示未知）；
2. planner / generator / debugger 收到该异常时与 token/USD 超限同待遇
   ——降级产物不变，但 `budget_exceeded` / `error_category` 必须落盘；
3. planner 的降级更新经 `determine_stop_reason` 可达 `BUDGET_EXCEEDED`。

纪律：零 LLM / 零网络 / 零子进程。三个节点复用既有 harness 的 mock 单点
（`tests.test_nodes_j4_*` / `tests.test_debugger_node_branches`），不重造骨架。
"""

from __future__ import annotations

import pytest

from src.agents.base_agent import LlmCallBudgetExceeded
from src.budget.cost_budget import BudgetExceededError
from src.graph.state import create_initial_state
from src.graph.workflow import StopReason, determine_stop_reason
from tests.test_debugger_node_branches import _base_state as _debugger_state
from tests.test_debugger_node_branches import _mock_debugger_agent, _run_debugger
from tests.test_nodes_j4_generator_sections import _run_generator
from tests.test_nodes_j4_generator_sections import _state as _generator_state
from tests.test_nodes_j4_planner_specir import _planner_update

_TIMEOUT_MESSAGE = "LLM 调用超过全局预算 600s，快速失败"


def _timeout(*, limit: int | None = None) -> LlmCallBudgetExceeded:
    """构造一次时间预算耗尽（节点用例不传 limit，确保红因落在标记逻辑本身）。"""
    if limit is None:
        return LlmCallBudgetExceeded(_TIMEOUT_MESSAGE)
    return LlmCallBudgetExceeded(_TIMEOUT_MESSAGE, limit=limit)


@pytest.mark.unit
class TestExceptionTaxonomy:
    """时间预算异常必须落在 5.4 预算封顶的捕获面内。"""

    def test_is_budget_exceeded_error_subclass(self) -> None:
        assert issubclass(LlmCallBudgetExceeded, BudgetExceededError), (
            "编排层读者用 isinstance(e, BudgetExceededError) 判预算封顶；兄弟类会让时间预算封顶永久不可达"
        )

    def test_carries_seconds_caliber_without_fake_consumption(self) -> None:
        exc = _timeout(limit=600)
        # 超预算发生在"下一次请求之前"，没有可报的已消耗秒数 → None（未知），
        # 不得像真实超限那样伪造数值。
        assert exc.consumed is None
        assert exc.limit == 600
        assert exc.unit == "seconds"
        assert str(exc) == _TIMEOUT_MESSAGE, "消息由调用点构造，不经父类数值模板重写"

    def test_limit_defaults_to_none(self) -> None:
        # 兼容不带 limit 的构造点：属性仍在，数值未知就写 None。
        exc = LlmCallBudgetExceeded("超时")
        assert exc.limit is None
        assert exc.unit == "seconds"


@pytest.mark.unit
class TestNodeReadersTreatTimeoutAsBudgetCap:
    """三个节点的预算封顶标记：时间预算与 token/USD 超限同待遇。"""

    def test_planner_timeout_marks_budget_exceeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = _planner_update(monkeypatch, plan_side_effect=_timeout())
        assert out["budget_exceeded"] is True
        assert out["test_plan"]["logic_degraded"] is True

    def test_generator_timeout_degrades_and_marks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        update, _agent = _run_generator(monkeypatch, _generator_state(), generate_side_effect=_timeout())
        assert update["generated_test"] == ""
        assert update["budget_exceeded"] is True

    def test_debugger_timeout_marks_category(self) -> None:
        agent = _mock_debugger_agent()
        agent.debug.side_effect = _timeout()
        result = _run_debugger(_debugger_state(), agent)
        assert result["error_category"] == "budget_exceeded"
        assert result["budget_exceeded"] is True
        assert result["patch"] == ""


@pytest.mark.unit
class TestStopReasonReachable:
    """用户可见承诺：时间预算封顶必须能产生 BUDGET_EXCEEDED 终止原因。"""

    def test_planner_timeout_reaches_budget_stop_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = _planner_update(monkeypatch, plan_side_effect=_timeout())
        state = create_initial_state(
            "ei-budget-cap",
            "target_mod.py",
            "def double(x):\n    return x * 2\n",
            0,
            module_name="target_mod",
            target_function="double",
        )
        state.update(out)
        assert determine_stop_reason(state) is StopReason.BUDGET_EXCEEDED
