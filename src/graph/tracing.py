"""
工作流节点结构化追踪辅助模块。

从 workflow.py 拆分而来（代码可维护性优化）：提供任务级 / 节点级结构化
追踪的事件记录函数，以线程局部方式挂载（与 token_usage 线程局部累计同机制），
未启用（AITESTER_TRACE_DIR 未设）时全部 no-op，对主流程零侵入。
"""

from __future__ import annotations

import threading
from typing import Any

from src.observability.trace import TraceSession, trace_enabled

# 追踪器以线程局部方式挂载（--parallel 每个工作线程一条任务线，互不串扰，
# 与 token_usage 线程局部累计同机制）。未启用（AITESTER_TRACE_DIR 未设）时
# 全部 no-op，对主流程零侵入。
_trace_local = threading.local()


def start_task_trace(task_id: str, task_meta: dict[str, Any] | None = None) -> None:
    """为当前线程开启任务级结构化追踪（未启用时 no-op）。

    由工作流入口（benchmark / CLI 任务派发处）在调用 graph.invoke 前调用。

    Args:
        task_id: 任务标识（JSONL 文件名与记录字段）。
        task_meta: 任务静态元数据（target_file / func / dataset 等）。
    """
    if not trace_enabled():
        return
    _trace_local.session = TraceSession(task_id, task_meta=task_meta)


def end_task_trace(passed: bool | None, token_snapshot: dict[str, Any] | None = None) -> None:
    """为当前线程收尾任务追踪（写 task_end 事件后清除）。

    Args:
        passed: 任务最终是否通过（None 表示中途崩溃）。
        token_snapshot: token_usage.get_usage().as_dict() 逐任务 token 消耗快照。
    """
    session: TraceSession | None = getattr(_trace_local, "session", None)
    if session is None:
        return
    session.record_task_end(passed=passed, token_usage=token_snapshot)
    _trace_local.session = None


def _trace_node(
    node: str,
    output_summary: Any = None,
    decision: str | None = None,
    duration_ms: float | None = None,
    iteration: int | None = None,
) -> None:
    """记录当前线程任务的一次节点事件（未启用时 no-op）。"""
    session: TraceSession | None = getattr(_trace_local, "session", None)
    if session is None:
        return
    session.record_node(
        node=node,
        output_summary=output_summary,
        decision=decision,
        duration_ms=duration_ms,
        iteration=iteration,
    )
