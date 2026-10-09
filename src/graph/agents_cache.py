"""Agent 实例复用缓存（S7 拆分自 nodes.py，2026-10-08 R3）。

集中两个 Agent 实例复用缓存簇（被多个节点共享）：
- ExecutorAgent 沙箱配置分键缓存（_get_or_create_executor_agent /
  clear_executor_agent_cache）；
- 通用按类名分键缓存（get_or_create_agent / clear_agent_instance_cache /
  _get_or_create_debugger_agent）。
nodes.py 通过 `from .agents_cache import ...` re-export，保持
`from src.graph.nodes import get_or_create_agent` 等历史导入路径不变。
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any

from src.graph.flags import _agent_reuse_enabled

if TYPE_CHECKING:
    # 仅供 mypy 解析类型注解；运行时用函数内延迟 import（从 src.graph.nodes
    # 取，保持测试 patch "src.graph.nodes.ExecutorAgent/DebuggerAgent" 可 mock）
    from src.agents.debugger import DebuggerAgent
    from src.agents.executor import ExecutorAgent

_executor_agent_cache: dict[tuple[Any, ...], ExecutorAgent] = {}


_executor_agent_cache_lock = threading.Lock()


def _get_or_create_executor_agent(
    *,
    timeout: int,
    use_docker: bool,
    use_venv: bool,
    auto_install_deps: bool,
    dep_install_timeout: int,
    docker_image: str,
) -> ExecutorAgent:
    """获取（或创建）按沙箱配置分键复用的 ExecutorAgent 实例。"""
    # 延迟 import（非模块顶层）：从 src.graph.nodes 取 ExecutorAgent，使测试
    # patch("src.graph.nodes.ExecutorAgent") 的 mock 能作用到本函数（历史 mock 口径）。
    from src.graph.nodes import ExecutorAgent

    if os.getenv("AITESTER_EXECUTOR_AGENT_CACHE", "1") == "0":
        return ExecutorAgent(
            timeout=timeout,
            use_docker=use_docker,
            use_venv=use_venv,
            auto_install_deps=auto_install_deps,
            dep_install_timeout=dep_install_timeout,
            docker_image=docker_image,
        )
    key = (timeout, use_docker, use_venv, auto_install_deps, dep_install_timeout, docker_image)
    agent = _executor_agent_cache.get(key)
    if agent is not None:
        return agent
    with _executor_agent_cache_lock:
        agent = _executor_agent_cache.get(key)
        if agent is not None:
            return agent
        agent = ExecutorAgent(
            timeout=timeout,
            use_docker=use_docker,
            use_venv=use_venv,
            auto_install_deps=auto_install_deps,
            dep_install_timeout=dep_install_timeout,
            docker_image=docker_image,
        )
        # 容量保护：键空间实际为"沙箱配置组合数"（远小于 16），超限 FIFO 淘汰
        # （与 llm_client 客户端缓存同口径）
        if len(_executor_agent_cache) >= 16:
            _executor_agent_cache.pop(next(iter(_executor_agent_cache)))
        _executor_agent_cache[key] = agent
    return agent


def clear_executor_agent_cache() -> None:
    """清空 ExecutorAgent 复用缓存（测试 / 配置切换时调用，恢复每次新建口径）。"""
    with _executor_agent_cache_lock:
        _executor_agent_cache.clear()


_agent_instance_cache: dict[str, Any] = {}


_agent_instance_cache_lock = threading.Lock()


_MAX_CACHED_AGENTS = 16


def get_or_create_agent(agent_cls: type) -> Any:
    """获取（或创建）复用的 Agent 实例（委托按类名分键的模块级缓存）。

    测试以 MagicMock 替换 agent_cls 时，"复用语义"保持原口径：MagicMock
    自身即被 patch 的"类"（构造/实例行为由 mock 定义），直接调用
    agent_cls() 而不走缓存（避免 mock 实例与真实类共享缓存键）。真实类
    走 DCL + FIFO 缓存路径。
    """
    if not _agent_reuse_enabled():
        return agent_cls()
    # MagicMock / 非类对象（测试 patch 场景）：直接构造，不污染模块缓存
    # （MagicMock 类无 __name__ 属性，构造/实例行为由 mock 定义，跨测试复用
    # 会产生 mock 实例与真实类缓存键错位——与按次新建的历史口径等价）
    if not isinstance(agent_cls, type):
        return agent_cls()
    # 真实类：按类名分键 DCL + FIFO 缓存
    key = agent_cls.__name__
    agent = _agent_instance_cache.get(key)
    if agent is not None:
        return agent
    with _agent_instance_cache_lock:
        agent = _agent_instance_cache.get(key)
        if agent is not None:
            return agent
        agent = agent_cls()
        if len(_agent_instance_cache) >= _MAX_CACHED_AGENTS:
            _agent_instance_cache.pop(next(iter(_agent_instance_cache)))
        _agent_instance_cache[key] = agent
    return agent


def clear_agent_instance_cache() -> None:
    """清空 Agent 实例复用缓存（测试 / 配置切换时调用，恢复每次新建口径）。"""
    with _agent_instance_cache_lock:
        _agent_instance_cache.clear()


def _get_or_create_debugger_agent() -> DebuggerAgent:
    """获取（或创建）复用的 DebuggerAgent 实例（委托 get_or_create_agent）。"""
    # 延迟 import（非模块顶层）：从 src.graph.nodes 取 DebuggerAgent，使测试
    # patch("src.graph.nodes.DebuggerAgent") 的 mock 能作用到本函数（历史 mock 口径）。
    from src.graph.nodes import DebuggerAgent

    agent = get_or_create_agent(DebuggerAgent)
    # 测试以 MagicMock 替换 DebuggerAgent 时（非 type），isinstance 校验不适用
    # 且 get_or_create_agent 已按"非 type → 直接构造"语义返回 mock 实例；
    # 真实类路径才做 isinstance 收窄（mypy 友好），mock 路径直返（测试口径）。
    if not isinstance(DebuggerAgent, type):
        return agent
    assert isinstance(agent, DebuggerAgent)
    return agent


__all__ = [
    "_get_or_create_debugger_agent",
    "_get_or_create_executor_agent",
    "clear_agent_instance_cache",
    "clear_executor_agent_cache",
    "get_or_create_agent",
]
