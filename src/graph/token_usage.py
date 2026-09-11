"""
LLM Token 消耗统计模块（P0 效率指标：完整系统 vs Plain LLM 的性价比对比）。

背景：
    完整多智能体系统每个任务要经过 Planner → Generator → Executor(多轮) →
    Debugger 多次 LLM 调用，token 消耗远多于单次调用基线。若性能没有优势，
    性价比反而不如 Plain LLM。实验必须记录每个任务的 token 消耗作为效率指标。

设计：
    - 线程局部累计（threading.local）：--parallel 模式下每个工作线程（任务）
      独立累计，互不串扰；
    - 每次 LLM 调用成功后由 BaseAgent 调用 record_usage() 累加；
    - 跨线程聚合（global_usage）供实验汇总；
    - 所有计数均为"本进程内、缓存未命中时"的真实 API 消耗。

使用方式（benchmark 入口）：
    from src.graph.token_usage import get_usage, reset
    reset()                      # 每个任务/基线开始前重置本线程
    ... 运行工作流 ...
    usage = get_usage()          # 取本线程累计
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """单个作用域（线程/任务）的 token 消耗快照。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    by_model: dict[str, int] = field(default_factory=dict)  # 模型名 → total_tokens

    def merge(self, other: TokenUsage) -> None:
        """把另一个快照累加到自身（用于跨线程聚合）。"""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.llm_calls += other.llm_calls
        for model, tokens in other.by_model.items():
            self.by_model[model] = self.by_model.get(model, 0) + tokens

    def as_dict(self) -> dict:
        """转为可 JSON 序列化的字典。"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "by_model": dict(self.by_model),
        }


# ─── 线程局部累计器 ─────────────────────────────────────────────────────────────
_thread_local = threading.local()
# 跨线程聚合：{thread_id: TokenUsage}，由 _registry_lock 保护。
# 已退出线程的条目刻意保留（不清理）：基准运行结束时 global_usage() 需聚合
# 全部已完成任务（worker 线程已退出）的 token 消耗；条目数受并发线程规模
# 限制（常驻线程池场景），量级可忽略
_registry: dict[int, TokenUsage] = {}
_registry_lock = threading.Lock()


def _current_usage() -> TokenUsage:
    """获取（必要时创建）当前线程的累计器。"""
    usage: TokenUsage | None = getattr(_thread_local, "usage", None)
    if usage is None:
        usage = TokenUsage()
        _thread_local.usage = usage
        with _registry_lock:
            _registry[threading.get_ident()] = usage
    return usage


def record_usage(input_tokens: int, output_tokens: int, model: str = "") -> None:
    """记录一次 LLM 调用的 token 消耗（累加到当前线程）。

    Args:
        input_tokens: 本次调用的输入 token 数。
        output_tokens: 本次调用的输出 token 数。
        model: 产生本次消耗的模型名（用于 by_model 分桶，可为空）。
    """
    usage = _current_usage()
    usage.input_tokens += input_tokens
    usage.output_tokens += output_tokens
    usage.total_tokens += input_tokens + output_tokens
    usage.llm_calls += 1
    if model:
        usage.by_model[model] = usage.by_model.get(model, 0) + input_tokens + output_tokens


def get_usage() -> TokenUsage:
    """获取当前线程的 token 消耗快照（不影响累计器，可重复调用）。"""
    return _current_usage()


def reset() -> TokenUsage:
    """重置当前线程累计器，并返回重置前的快照。

    用于"每个任务/基线开始前清零"的实验隔离语义。

    Returns:
        重置前本线程已累计的 TokenUsage。
    """
    previous = get_usage()
    fresh = TokenUsage()
    _thread_local.usage = fresh
    with _registry_lock:
        _registry[threading.get_ident()] = fresh
    return previous


def global_usage() -> TokenUsage:
    """聚合所有线程的 token 消耗（快照，含已退出线程的条目）。

    跨线程求和，供实验结束时输出全局效率指标：基准运行结束时聚合需包含
    全部已完成任务（worker 线程已退出）的消耗，故此处不做死线程清理——
    僵尸条目在后续 _current_usage/reset（新批次任务开始记录时）被机会性
    清掉，保证长进程多批次场景下 global_usage 不被历史批次污染。

    Returns:
        全进程聚合的 TokenUsage。
    """
    total = TokenUsage()
    with _registry_lock:
        for usage in _registry.values():
            total.merge(usage)
    return total
