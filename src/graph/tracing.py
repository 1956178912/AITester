"""
工作流节点结构化追踪辅助模块。

从 workflow.py 拆分而来（代码可维护性优化）：提供任务级 / 节点级结构化
追踪的事件记录函数，以线程局部方式挂载（与 token_usage 线程局部累计同机制），
文件追踪未启用（AITESTER_TRACE_DIR 未设）时全部 no-op 落盘、对主流程零侵入，
但 TraceSession 仍在内存累积"最小化节点快照"（records），收尾时经
memory_buffer_snapshot 入进程级环形缓冲（默认启用、不落盘）——供
CLI --dump-trace-on-failure 在任务失败时把最近任务快照写成临时 JSONL
供诊断（2026-09-28 可观测性批次）。
"""

from __future__ import annotations

import threading
from typing import Any

from src.observability.trace import TraceSession, memory_buffer_snapshot, trace_enabled

# 追踪器以线程局部方式挂载（--parallel 每个工作线程一条任务线，互不串扰，
# 与 token_usage 线程局部累计同机制）。文件追踪未启用（AITESTER_TRACE_DIR
# 未设）时 _append 全 no-op（不落盘），仅内存累积 records 供失败诊断。
_trace_local = threading.local()


def start_task_trace(task_id: str, task_meta: dict[str, Any] | None = None) -> None:
    """为当前线程开启任务级结构化追踪（文件追踪未启用时不落盘，仅累积内存快照）。

    由工作流入口（benchmark / CLI 任务派发处）在调用 graph.invoke 前调用。
    文件追踪启用与否取决于环境变量 AITESTER_TRACE_DIR（TraceSession 构造时
    读）；未启用时 session 仅内存累积 records（供失败诊断快照消费），
    历史调用方（未设 AITESTER_TRACE_DIR）视角下行为不变（零 I/O、零副作用
    ——线程局部在 end_task_trace 时清空）。

    O35（2026-09-30 全面审查 P1）：文件追踪关闭时也要建 session。
    此前条件是 ``not trace_enabled()`` 即 return，而 TraceSession 在无目录时
    本来就不写盘（_enabled=False，只累积 self.records）——于是默认配置下
    session 恒为 None → ``end_task_trace`` 在 ``if session is None: return``
    处提前返回、永远到不了 memory_buffer_snapshot → 环形缓冲恒空 →
    ``--dump-trace-on-failure`` 在**它被设计出来的那个场景**（不开文件追踪的
    常规运行）静默失效，dump_recent_to 恒返回 None。与 trace.py L318-321
    文档承诺（"本缓冲在追踪未启用时保留最近 N 次任务快照"）矛盾。
    现改为"文件追踪开 或 内存缓冲开"任一成立即建 session；
    TRACE_MEMORY_BUFFER_ENABLE=false（显式关缓冲）时恢复历史零开销口径。

    Args:
        task_id: 任务标识（JSONL 文件名与记录字段）。
        task_meta: 任务静态元数据（target_file / func / dataset 等）。
    """
    from src.observability.trace import _memory_buffer_enabled

    if not trace_enabled() and not _memory_buffer_enabled():
        # 文件追踪与内存缓冲双关：保持历史"线程局部无 session"口径
        # （_trace_node / end_task_trace 全 no-op、零 I/O、零对象分配）
        _trace_local.session = None
        return
    _trace_local.session = TraceSession(task_id, task_meta=task_meta)


def end_task_trace(passed: bool | None, token_snapshot: dict[str, Any] | None = None) -> None:
    """为当前线程收尾任务追踪（写 task_end 事件 + 内存快照入缓冲后清除）。

    Args:
        passed: 任务最终是否通过（None 表示中途崩溃）。
        token_snapshot: token_usage.get_usage().as_dict() 逐任务 token 消耗快照。
    """
    session: TraceSession | None = getattr(_trace_local, "session", None)
    if session is None:
        return
    session.record_task_end(passed=passed, token_usage=token_snapshot)
    # 内存快照入进程级环形缓冲（默认启用、不落盘；TRACE_MEMORY_BUFFER_ENABLE
    # 可关）——供 --dump-trace-on-failure 在失败时把最近任务的关键节点
    # 快照写成临时 JSONL 供诊断（追踪全 no-op 默认口径下仍可复盘）。
    memory_buffer_snapshot(session.task_id, session.records)
    _trace_local.session = None


def _trace_node(
    node: str,
    output_summary: Any = None,
    decision: str | None = None,
    duration_ms: float | None = None,
    iteration: int | None = None,
    input_summary: Any = None,
    token_usage: dict[str, Any] | None = None,
    decision_reason: str | None = None,
    strategy_selected: str | None = None,
    budget_remaining: int | float | None = None,
) -> None:
    """记录当前线程任务的一次节点事件（未启用时 no-op）。

    P1 执行感知可观测性升级：新增五个结构化决策路径参数
    （input_summary / token_usage / decision_reason / strategy_selected /
    budget_remaining），透传给 TraceSession.record_node。所有参数均可选，
    缺省不写入 JSONL 记录（历史调用方零变化）。
    """
    session: TraceSession | None = getattr(_trace_local, "session", None)
    if session is None:
        return
    session.record_node(
        node=node,
        output_summary=output_summary,
        decision=decision,
        duration_ms=duration_ms,
        iteration=iteration,
        input_summary=input_summary,
        token_usage=token_usage,
        decision_reason=decision_reason,
        strategy_selected=strategy_selected,
        budget_remaining=budget_remaining,
    )
