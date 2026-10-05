"""U9（2026-10-05 系统性审查落地）兼容 shim：实现已下沉 src/budget/cost_budget。

旧导入路径 `from src.graph.cost_budget import X` 保持可用（re-export 同一
对象）；新代码请直接 `from src.budget.cost_budget import X`（agents 层
依赖倒置修复，分层 cli → graph → agents → budget/tools）。
"""

from src.budget.cost_budget import *  # noqa: F403
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

__all__ = [
    "BudgetExceededError",
    "BudgetSnapshot",
    "attach_budget",
    "check_budget",
    "current_budget",
    "get_budget_stats",
    "get_process_budget_stats",
    "is_budget_exceeded",
    "record_usage_and_check",
    "reset_budget",
]
