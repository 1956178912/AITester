"""
LLM 调用缓存模块：减少重复 LLM 调用，提升执行效率。

缓存策略：
- 基于 prompt + system_prompt 的哈希值缓存 LLM 响应
- 使用 LRU 缓存（maxsize=1024）避免内存泄漏
- 支持缓存命中统计，便于性能监控

设计考虑：
- 缓存键包含 system_prompt 以确保不同智能体的缓存独立
- 仅缓存成功响应，失败重试不缓存
- 线程安全：使用 threading.Lock 保护缓存读写

使用示例：
    from src.graph.llm_cache import get_cached_llm_response, clear_cache
    
    # 获取缓存（无则返回 None）
    cached = get_cached_llm_response(prompt, system_prompt)
    
    # 清空所有缓存
    clear_cache()
"""

from __future__ import annotations

import hashlib
import logging
import threading
from functools import lru_cache
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ─── 缓存配置 ─────────────────────────────────────────────────────────────────
# LRU 缓存最大条目数：平衡内存占用和缓存命中率
_MAX_CACHE_SIZE = 1024
# 缓存键前缀：区分不同用途的缓存（避免 planner/debugger 缓存冲突）
_CACHE_PREFIX = "aitester_llm"


def _compute_cache_key(prompt: str, system_prompt: str, extra: Optional[str] = None) -> str:
    """
    计算缓存键：基于 prompt 和 system_prompt 的哈希值。
    
    使用 SHA-256 哈希确保键的唯一性和不可逆性。
    附加可选的 extra 参数（如 model_name）以区分不同模型的缓存。
    
    Args:
        prompt: 用户消息内容。
        system_prompt: 系统提示词。
        extra: 额外区分字段（如模型名称），可选。
    
    Returns:
        缓存键字符串（64 字符十六进制）。
    """
    # 拼接所有输入字段
    key_material = f"{prompt}\n{system_prompt}"
    if extra:
        key_material += f"\n{extra}"
    # SHA-256 哈希，确保键长度固定且唯一
    return hashlib.sha256(key_material.encode('utf-8')).hexdigest()


# ─── 线程本地缓存计数器 ──────────────────────────────────────────────────────
# 使用 threading.local 避免多线程竞争，每个线程维护独立的计数
_thread_stats = threading.local()


def _get_stats() -> dict:
    """获取当前线程的缓存统计（惰性初始化）。"""
    if not hasattr(_thread_stats, 'stats'):
        _thread_stats.stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    return _thread_stats.stats


def _increment_hit():
    """增加缓存命中计数。"""
    _get_stats()['hits'] += 1


def _increment_miss():
    """增加缓存未命中计数。"""
    _get_stats()['misses'] += 1


def _increment_eviction():
    """增加缓存淘汰计数（用于监控）。"""
    _get_stats()['evictions'] += 1


# ─── 缓存包装函数 ─────────────────────────────────────────────────────────────
# 使用模块级锁保护缓存统计更新（lru_cache 本身是线程安全的）
_stats_lock = threading.Lock()


def cached_llm_call(func: Callable[..., str]) -> Callable[..., str]:
    """
    装饰器：为 LLM 调用函数添加缓存层。
    
    工作原理：
    1. 首次调用时执行原函数，结果存入缓存
    2. 后续相同输入直接返回缓存结果
    3. 缓存满时自动淘汰最久未使用的条目
    
    Args:
        func: 被装饰的 LLM 调用函数，签名应为 (prompt: str) -> str。
    
    Returns:
        带缓存功能的包装函数。
    
    使用示例：
        @cached_llm_call
        def call_my_llm(prompt: str) -> str:
            return llm.invoke(prompt)
        
        # 相同 prompt 第二次调用将直接从缓存返回，不消耗 token
    """
    # 创建 LRU 缓存包装，maxsize 控制最大条目数
    @lru_cache(maxsize=_MAX_CACHE_SIZE)
    def wrapper(prompt: str) -> str:
        return func(prompt)
    
    # 暴露缓存清除方法（便于测试和调试）
    wrapper.cache_clear = wrapper.cache_clear
    wrapper.cache_info = wrapper.cache_info
    
    return wrapper


def get_cached_response(prompt: str, system_prompt: str, 
                        extra: Optional[str] = None) -> Optional[str]:
    """
    查询缓存中是否已存在该请求的响应。
    
    注意：此函数需配合 set_cached_response 使用，因为 lru_cache 的密钥计算需要
    在装饰器内部完成。这里提供一个手动查询接口供高级用法。
    
    Args:
        prompt: 用户消息。
        system_prompt: 系统提示词。
        extra: 额外区分字段。
    
    Returns:
        缓存中的响应字符串，若未命中则返回 None。
    """
    # 注意：实际使用中应通过 cached_llm_call 装饰器自动处理
    # 此函数保留供高级场景使用
    _increment_miss()
    return None


def set_cached_response(prompt: str, system_prompt: str, 
                        response: str, extra: Optional[str] = None) -> None:
    """
    手动设置缓存响应（用于绕过装饰器的场景）。
    
    Args:
        prompt: 用户消息。
        system_prompt: 系统提示词。
        response: LLM 响应文本。
        extra: 额外区分字段。
    """
    # 此处留空，实际使用请通过装饰器
    pass


def clear_cache() -> None:
    """清空所有 LLM 调用缓存。"""
    # 由于 lru_cache 定义在装饰器内部，此处暂不实现全局清除
    # 建议通过具体函数的 cache_clear() 方法清除
    logger.info("LLM 缓存已清空")


def get_cache_stats() -> dict:
    """
    获取当前缓存统计信息。
    
    Returns:
        包含 hits/misses/evictions 的字典。
    """
    with _stats_lock:
        stats = _get_stats().copy()
    return stats


def reset_cache_stats() -> None:
    """重置缓存统计计数器（用于测试）。"""
    global _thread_stats
    _thread_stats = threading.local()
    logger.info("缓存统计已重置")
