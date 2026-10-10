"""U9（2026-10-05 系统性审查落地）兼容 shim：实现已下沉 src/budget/token_usage。

旧导入路径 `from src.graph.token_usage import X` 保持可用（re-export 同一
对象）；新代码请直接 `from src.budget.token_usage import X`（agents 层
依赖倒置修复）。私有锁/注册表（_usage_lock / _registry_lock / _thread_local）
一并显式转发——旧路径测试直接访问这些私有名，star-import 不带下划线名。
"""

from src.budget.token_usage import *  # noqa: F403
from src.budget.token_usage import (
    TokenUsage,
    _registry,
    _registry_lock,
    _thread_local,
    _usage_lock,
    attach_usage,
    get_usage,
    global_usage,
    record_cache_hit_usage,
    record_usage,
    reset,
)

__all__ = [
    "TokenUsage",
    "_registry",
    "_registry_lock",
    "_thread_local",
    "_usage_lock",
    "attach_usage",
    "get_usage",
    "global_usage",
    "record_cache_hit_usage",
    "record_usage",
    "reset",
]
