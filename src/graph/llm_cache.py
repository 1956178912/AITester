"""
LLM 调用缓存模块：减少重复 LLM 调用，提升执行效率。

缓存策略：
- 基于 (prompt, system_prompt, extra) 计算 SHA-256 缓存键，LRU 淘汰（maxsize=1024）
- 线程安全：单一锁保护缓存与统计读写
- 提供命中率统计（hits/misses/evictions），供性能监控

设计考虑：
- 缓存键包含 system_prompt，确保不同智能体的缓存相互独立
- 命中时 O(1) 返回并更新 LRU 顺序；未命中时插入并可能淘汰最久未用条目
- clear_cache() 真正清空缓存；reset_cache_stats() 清零计数器（用于测试）

使用示例：
    from src.graph.llm_cache import get_cached_response, set_cached_response

    # 查询缓存（无则返回 None）
    cached = get_cached_response(prompt, system_prompt)
    if cached is None:
        cached = call_llm(prompt, system_prompt)
        set_cached_response(prompt, system_prompt, cached)
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps

logger = logging.getLogger(__name__)

# ─── 缓存配置 ─────────────────────────────────────────────────────────────────
# LRU 缓存最大条目数：平衡内存占用和缓存命中率
_MAX_CACHE_SIZE = 1024
# 缓存键前缀：区分不同用途的缓存（避免 planner/debugger 缓存冲突）
_CACHE_PREFIX = "aitester_llm"


def _compute_cache_key(prompt: str, system_prompt: str, extra: str | None = None) -> str:
    """
    计算缓存键：基于 prompt 和 system_prompt 的 SHA-256 哈希值。

    附加可选的 extra 参数（如 model_name）以区分不同模型的缓存。

    Args:
        prompt: 用户消息内容。
        system_prompt: 系统提示词。
        extra: 额外区分字段（如模型名称），可选。

    Returns:
        缓存键字符串（含前缀，64 字符十六进制哈希）。
    """
    key_material = f"{prompt}\n{system_prompt}"
    if extra:
        key_material += f"\n{extra}"
    return f"{_CACHE_PREFIX}:{hashlib.sha256(key_material.encode('utf-8')).hexdigest()}"


# ─── 全局 LRU 缓存存储 ────────────────────────────────────────────────────────
# OrderedDict 实现 LRU：新访问放末尾，淘汰时取最久未用的头部条目
_cache_store: OrderedDict[str, str] = OrderedDict()
# 缓存统计计数器（hits/misses/evictions）
_cache_stats: dict[str, int] = {"hits": 0, "misses": 0, "evictions": 0}
# 单一锁保护 _cache_store 与 _cache_stats 的原子读写
_cache_lock = threading.Lock()


def _cache_get(key: str) -> str | None:
    """
    从缓存读取条目，命中时更新 LRU 顺序。

    Args:
        key: 缓存键。

    Returns:
        命中返回缓存值，未命中返回 None。
    """
    with _cache_lock:
        if key in _cache_store:
            # LRU：命中后移到末尾（最近使用）
            _cache_store.move_to_end(key)
            _cache_stats["hits"] += 1
            return _cache_store[key]
        _cache_stats["misses"] += 1
        return None


def _cache_set(key: str, value: str) -> None:
    """
    写入缓存条目，超过 maxsize 时淘汰最久未用条目。

    Args:
        key: 缓存键。
        value: 缓存值（LLM 响应文本）。
    """
    with _cache_lock:
        if key in _cache_store:
            _cache_store.move_to_end(key)
            _cache_store[key] = value
            return
        _cache_store[key] = value
        _cache_store.move_to_end(key)
        # 超出容量则淘汰头部（最久未用）条目
        while len(_cache_store) > _MAX_CACHE_SIZE:
            _cache_store.popitem(last=False)
            _cache_stats["evictions"] += 1


# ─── 装饰器：为 LLM 调用函数添加缓存层 ────────────────────────────────────────
def cached_llm_call(func: Callable[..., str]) -> Callable[..., str]:
    """
    装饰器：为 LLM 调用函数添加缓存层。

    工作原理：
    1. 首次调用时执行原函数，结果存入缓存（键含函数限定名，隔离不同智能体）
    2. 后续相同输入直接返回缓存结果，不重复消耗 token
    3. 缓存满时自动淘汰最久未使用的条目

    Args:
        func: 被装饰的 LLM 调用函数，签名应为 (prompt: str) -> str。

    Returns:
        带缓存功能的包装函数。

    使用示例：
        @cached_llm_call
        def call_my_llm(prompt: str) -> str:
            return llm.invoke(prompt)
    """

    @wraps(func)
    def wrapper(prompt: str) -> str:
        key = _compute_cache_key(prompt, func.__qualname__)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = func(prompt)
        _cache_set(key, result)
        return result

    return wrapper


# ─── 手动缓存接口（供绕过装饰器的场景）───────────────────────────────────────
def get_cached_response(prompt: str, system_prompt: str, extra: str | None = None) -> str | None:
    """
    查询缓存中是否已存在该请求的响应。

    Args:
        prompt: 用户消息。
        system_prompt: 系统提示词。
        extra: 额外区分字段（如模型名称）。

    Returns:
        缓存中的响应字符串，若未命中则返回 None。
    """
    key = _compute_cache_key(prompt, system_prompt, extra)
    return _cache_get(key)


def set_cached_response(prompt: str, system_prompt: str, response: str, extra: str | None = None) -> None:
    """
    手动写入缓存响应（用于绕过装饰器的场景）。

    Args:
        prompt: 用户消息。
        system_prompt: 系统提示词。
        response: LLM 响应文本。
        extra: 额外区分字段（如模型名称）。
    """
    key = _compute_cache_key(prompt, system_prompt, extra)
    _cache_set(key, response)


def clear_cache() -> None:
    """清空所有 LLM 调用缓存（保留统计计数器，如需一并清零用 reset_cache_stats）。"""
    with _cache_lock:
        _cache_store.clear()
    logger.info("LLM 缓存已清空")


def get_cache_stats() -> dict[str, int]:
    """
    获取当前缓存统计信息。

    Returns:
        包含 hits/misses/evictions 的字典。
    """
    with _cache_lock:
        return dict(_cache_stats)


def reset_cache_stats() -> None:
    """重置缓存统计计数器（用于测试）。"""
    with _cache_lock:
        for key in _cache_stats:
            _cache_stats[key] = 0
    logger.info("缓存统计已重置")
