"""
1.4 改进：轻量级事件总线（节点间通信解耦层，默认纯观测，不改路由）。

背景：
    当前智能体间通信依赖 LangGraph 状态图（src/graph/workflow.py），节点间
    通过共享状态字典（AITesterState）传递数据。紧耦合在节点数量增长后
    成为瓶颈（新增节点需改 state schema + 路由函数 + 所有消费方）。
    本模块引入轻量级事件总线：节点间通信抽象为事件
    （PlanGenerated / TestsExecuted / PatchApplied / DebuggerDiagnosed ...），
    解耦"事件发布方"与"事件消费方"。

设计约束（保持历史行为零变化）：
    - **纯观测层**（默认口径）：事件发布/订阅不影响 LangGraph 路由与
      状态传递——LangGraph 仍是事实来源，事件总线是"旁路"；
    - 订阅者：纯 Python 回调（observability 层 / trace 记录 / 未来并行
      节点调度器），异常隔离（单个订阅者失败不影响其他订阅者与主流程）；
    - 线程安全：发布/订阅经锁保护（--parallel 多任务并发场景）；
    - 事件 schema：frozen dataclass（不可变载荷，避免发布方事后改写）；
    - 开关：EVENT_BUS_ENABLE（默认 true——纯观测零成本；设 false 时
      全部 publish/subscribe 为 no-op，保留消融能力）。

事件类型（与现有节点一一对应，命名取自文档建议）：
    PlanGenerated   planner 节点产出测试计划后
    TestsExecuted   executor 节点执行测试后（含 passed/coverage）
    PatchApplied    patch_applier 节点写盘后（含 applied 标志）
    DebuggerDiagnosed  debugger 节点诊断后（含 error_category/fix_strategy_tag）
    WorkflowCompleted  工作流收尾（含 test_passed/iteration/error_category）
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

# 事件载荷上限（trace 观测用截断；避免把大代码全文塞进事件总线）
_MAX_CODE_CHARS = 200


class Event:
    """事件基类（事件名 + 载荷 + 迭代轮次）。"""

    EVENT_NAME: str = "event"

    def __init__(self, payload: dict[str, Any] | None = None, iteration: int = 0) -> None:
        self.payload: dict[str, Any] = payload or {}
        self.iteration = iteration

    def summary(self) -> dict[str, Any]:
        """可 JSON 序列化的事件摘要（trace 记录 / 观测层消费）。"""
        return {"event": self.EVENT_NAME, "iteration": self.iteration, "payload": dict(self.payload)}


class PlanGenerated(Event):
    """planner 节点产出测试计划。"""

    EVENT_NAME: str = "plan_generated"

    def __init__(
        self,
        task_uuid: str = "",
        function_name: str = "",
        test_case_count: int = 0,
        cfg_cyclomatic: int | None = None,
        iteration: int = 0,
    ) -> None:
        super().__init__(
            payload={
                "task_uuid": task_uuid,
                "function_name": function_name,
                "test_case_count": test_case_count,
                "cfg_cyclomatic": cfg_cyclomatic,
            },
            iteration=iteration,
        )


class TestsExecuted(Event):
    """executor 节点执行测试（含 passed / coverage）。"""

    __test__ = False  # 阻止 pytest 把事件类当测试类收集
    EVENT_NAME: str = "tests_executed"

    def __init__(
        self,
        task_uuid: str = "",
        passed: bool = False,
        coverage: float | None = None,
        error_category: str = "",
        iteration: int = 0,
    ) -> None:
        super().__init__(
            payload={
                "task_uuid": task_uuid,
                "passed": passed,
                "coverage": coverage,
                "error_category": error_category,
            },
            iteration=iteration,
        )


class PatchApplied(Event):
    """patch_applier 节点补丁写盘结果（applied 标志 + 代码长度）。"""

    EVENT_NAME: str = "patch_applied"

    def __init__(
        self,
        task_uuid: str = "",
        applied: bool = False,
        new_code_chars: int = 0,
        postprocess_labels: list[str] | None = None,
        iteration: int = 0,
    ) -> None:
        payload: dict[str, Any] = {
            "task_uuid": task_uuid,
            "applied": applied,
            "new_code_chars": new_code_chars,
        }
        if postprocess_labels:
            payload["postprocess_labels"] = list(postprocess_labels)
        super().__init__(payload=payload, iteration=iteration)


class DebuggerDiagnosed(Event):
    """debugger 节点诊断结果（error_category + 结构化修复策略标签）。"""

    EVENT_NAME: str = "debugger_diagnosed"

    def __init__(
        self,
        task_uuid: str = "",
        error_category: str = "",
        fix_strategy_tag: str = "",
        fix_strategy_action: str = "",
        iteration: int = 0,
    ) -> None:
        super().__init__(
            payload={
                "task_uuid": task_uuid,
                "error_category": error_category,
                "fix_strategy_tag": fix_strategy_tag,
                "fix_strategy_action": fix_strategy_action,
            },
            iteration=iteration,
        )


class WorkflowCompleted(Event):
    """工作流收尾（最终 test_passed / iteration / 最终错误类别）。"""

    EVENT_NAME: str = "workflow_completed"

    def __init__(
        self, task_uuid: str = "", test_passed: bool = False, iteration: int = 0, final_error_category: str = ""
    ) -> None:
        super().__init__(
            payload={
                "task_uuid": task_uuid,
                "test_passed": test_passed,
                "final_error_category": final_error_category,
            },
            iteration=iteration,
        )


Subscriber = Callable[[Event], None]


def _event_bus_enabled() -> bool:
    """事件总线开关（EVENT_BUS_ENABLE，默认 true——纯观测零路由影响；
    设 false 时 publish/subscribe 为 no-op，消融"事件层本身"的成本）。"""
    return os.getenv("EVENT_BUS_ENABLE", "true").lower() not in ("false", "0")


class EventBus:
    """轻量级进程内事件总线（发布-订阅 + 异常隔离 + 线程安全）。

    语义（与 LangGraph 的关系）：
    - LangGraph 状态图仍是事实来源（路由/状态传递不经本总线）；
    - 本总线是"旁路观测层"：订阅者可把事件写入 trace、统计、
      未来并行节点调度（消费方自行决定是否用于路由，总线不强制）；
    - 发布顺序 = 订阅顺序（FIFO，保持观测时序稳定）；
    - 单订阅者异常 → 记 WARNING 后继续（隔离故障，不阻断主流程）。
    """

    def __init__(self) -> None:
        # 订阅者注册表（事件名 → 订阅者列表，FIFO 调用）
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._lock = threading.Lock()
        # 事件计数（观测层：各事件发布次数，get_event_stats 消费）
        self._counts: dict[str, int] = {}

    def subscribe(self, event_name: str, subscriber: Subscriber) -> None:
        """订阅事件（event_name = 事件的 EVENT_NAME，如 "patch_applied"）。

        重复订阅同一 subscriber 不去重（允许同一回调挂多个事件名；
        挂同一事件名两次会调两次——语义明确，调用方自决）。
        """
        with self._lock:
            self._subscribers.setdefault(event_name, []).append(subscriber)

    def publish(self, event: Event) -> None:
        """发布事件（开关关闭时 no-op；线程安全；订阅者异常隔离）。"""
        if not _event_bus_enabled():
            return
        name = event.EVENT_NAME
        with self._lock:
            subs = list(self._subscribers.get(name, []))
            self._counts[name] = self._counts.get(name, 0) + 1
        for sub in subs:
            try:
                sub(event)
            except Exception as e:
                logger.warning("事件总线订阅者异常（隔离，不阻断主流程）%s: %s", name, e)

    def stats(self) -> dict[str, Any]:
        """观测统计（各事件发布次数 + 已订阅事件名）。"""
        with self._lock:
            return {"counts": dict(self._counts), "subscribed": sorted(self._subscribers.keys())}

    def clear(self) -> None:
        """清空订阅者与统计（测试隔离 / 进程重启口径）。"""
        with self._lock:
            self._subscribers.clear()
            self._counts.clear()


# 进程级单例（与 LLM 客户端缓存 / RAG 检索器同口径：全局共享，
# --parallel 线程安全；测试经 get_event_bus().clear() 隔离）
_bus = EventBus()


def get_event_bus() -> EventBus:
    """获取进程级事件总线单例。"""
    return _bus


def publish_event(event: Event) -> None:
    """便捷发布（经进程级单例；开关关闭时 no-op）。"""
    _bus.publish(event)


# ─── 节点接线辅助（各节点收尾处调一行，保持"纯函数节点 + 旁路事件"）──────
def publish_tests_executed(state: Mapping[str, Any], passed: bool, coverage: float | None = None) -> None:
    """executor 节点收尾接线（TestsExecuted 事件）。"""
    publish_event(
        TestsExecuted(
            task_uuid=str(state.get("task_uuid", "")),
            passed=passed,
            coverage=coverage,
            error_category=str(state.get("error_category", "")),
            iteration=int(state.get("iteration", 0)),
        )
    )


def publish_patch_applied(state: Mapping[str, Any], applied: bool, new_code: str) -> None:
    """patch_applier 节点收尾接线（PatchApplied 事件，含 1.1 后处理标签）。"""
    labels = state.get("postprocess_labels")
    publish_event(
        PatchApplied(
            task_uuid=str(state.get("task_uuid", "")),
            applied=applied,
            new_code_chars=len(new_code or ""),
            postprocess_labels=list(labels) if labels else None,
            iteration=int(state.get("iteration", 0)),
        )
    )


def publish_debugger_diagnosed(state: Mapping[str, Any], error_category: str) -> None:
    """debugger 节点收尾接线（DebuggerDiagnosed 事件，含 2.1 策略标签）。"""
    publish_event(
        DebuggerDiagnosed(
            task_uuid=str(state.get("task_uuid", "")),
            error_category=error_category,
            fix_strategy_tag=str(state.get("fix_strategy_tag") or ""),
            fix_strategy_action=str(state.get("fix_strategy_action") or ""),
            iteration=int(state.get("iteration", 0)),
        )
    )


def publish_workflow_completed(state: Mapping[str, Any], test_passed: bool, final_error_category: str = "") -> None:
    """工作流收尾接线（WorkflowCompleted 事件）。"""
    publish_event(
        WorkflowCompleted(
            task_uuid=str(state.get("task_uuid", "")),
            test_passed=test_passed,
            iteration=int(state.get("iteration", 0)),
            final_error_category=final_error_category,
        )
    )
