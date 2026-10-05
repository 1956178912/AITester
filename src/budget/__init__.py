"""src.budget：任务级成本预算与 token 记账基础包（U9，2026-10-05 系统性审查落地）。

背景（2026-10-05 独立系统性审查）：
    cost_budget / token_usage 原位于 src/graph/（编排层），但主要消费方是
    src/agents/（base_agent 前置预算守卫、llm_client 记账）——"下层依赖
    上层"的分层倒置靠函数级延迟 import 掩盖。本包把这两个**纯数据、无
    编排依赖**的基础模块下沉为独立基础包，agents 层直接依赖 src.budget，
    分层恢复 cli → graph → agents → budget/tools 单向。

旧导入路径兼容：src/graph/cost_budget.py 与 src/graph/token_usage.py
保留为 re-export shim，`from src.graph.cost_budget import X` 与
`from src.budget.cost_budget import X` 取到同一对象（测试与外部消费方
不受影响）。
"""

from src.budget.cost_budget import (
    BudgetExceededError,
    BudgetSnapshot,
    attach_budget,
    check_budget,
    current_budget,
    get_budget_stats,
    get_process_budget_stats,
    is_budget_exceeded,
    record_usage_and_check,
    reset_budget,
)
from src.budget.token_usage import (
    TokenUsage,
    attach_usage,
    get_usage,
    global_usage,
    record_usage,
    reset,
)

__all__ = [
    "BudgetExceededError",
    "BudgetSnapshot",
    "TokenUsage",
    "attach_budget",
    "attach_usage",
    "check_budget",
    "current_budget",
    "get_budget_stats",
    "get_process_budget_stats",
    "get_usage",
    "global_usage",
    "is_budget_exceeded",
    "record_usage",
    "record_usage_and_check",
    "reset",
    "reset_budget",
]
