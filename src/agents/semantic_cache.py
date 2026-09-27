"""
5.1 改进：语义级 LLM 缓存（嵌入向量相似度匹配，默认关保持历史口径）。

背景：
    现有 LLM 文件缓存基于 prompt 的 md5 精确匹配——语义相同但措辞不同的
    prompt（如修复轮次间温度微调、prompt 模板小改）无法命中，反复消耗
    token。本模块在文件缓存之上加一层**进程内语义索引**：
    - 索引材料：从文件缓存条目（src/cache/*.json）中取 prompt 文本做嵌入；
    - 命中判定：新 prompt 的嵌入与索引条目的余弦相似度 >=
      SEMANTIC_CACHE_THRESHOLD（默认 0.92）→ 视为语义命中，直接返回该
      条目的缓存响应（省一次 LLM 调用）；
    - 嵌入后端：复用 src/utils/embedding_utils.embed_text（CodeBERT →
      sentence-transformers → chromadb → None 级联），**嵌入不可用时
      自动降级为精确缓存口径**（零行为变化，不阻断主流程）；
    - 索引规模：仅扫描最近 SEMANTIC_CACHE_MAX_ENTRIES 个缓存文件
      （默认 256，按 mtime 取新），避免全目录扫描 + 嵌入推理的成本失控。

与 contamination_check 的关系：同用 embedding_utils 钩子，但独立开关
（SEMANTIC_CACHE_ENABLE，默认 false）——污染检测是"检测"语义，
语义缓存是"复用"语义，互不影响。

开关（环境变量，调用期读取，保留测试的 patch.dict 切换能力）：
    SEMANTIC_CACHE_ENABLE    默认 false（开启语义级匹配）
    SEMANTIC_CACHE_THRESHOLD 余弦阈值，默认 0.92（保守：宁可漏命中不可误命中）
    SEMANTIC_CACHE_MAX_ENTRIES 索引扫描的缓存文件数上限，默认 256
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _semantic_cache_enabled() -> bool:
    """语义缓存开关（SEMANTIC_CACHE_ENABLE，默认 false 保持历史精确缓存口径）。"""
    return os.getenv("SEMANTIC_CACHE_ENABLE", "false").lower() in ("true", "1", "on")


def _semantic_threshold() -> float:
    """余弦相似度阈值（SEMANTIC_CACHE_THRESHOLD，默认 0.92 保守口径）。"""
    try:
        v = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))
    except ValueError:
        v = 0.92
    return max(0.0, min(1.0, v))


def _max_index_entries() -> int:
    """索引扫描文件数上限（SEMANTIC_CACHE_MAX_ENTRIES，默认 256）。"""
    try:
        n = int(os.getenv("SEMANTIC_CACHE_MAX_ENTRIES", "256"))
    except ValueError:
        n = 256
    return max(8, min(n, 4096))


@dataclass
class _SemanticEntry:
    """语义索引条目：一个缓存文件的嵌入向量 + 响应文本。"""

    cache_file: str
    prompt: str
    response: str
    embedding: list[float] = field(default_factory=list)


class SemanticCacheIndex:
    """进程内语义缓存索引（嵌入向量 + 余弦命中判定）。

    设计约束：
    - 索引只增不删（进程生命周期内）；同 cache_file 重复 upsert 时
      更新向量（嵌入后端切换场景），键唯一；
    - 命中判定 O(N·D)（N = 索引条目数 ≤ SEMANTIC_CACHE_MAX_ENTRIES，
      D = 向量维度 ~384-768）：N=256、D=768 时约 20 万次乘法，
      纯 Python ~几十 ms，相比一次 LLM 调用（秒级）可接受；
      命中概率随任务数增长而上升（同任务多轮修复 prompt 高度相似）；
    - 嵌入后端不可用时索引为空（upsert 跳过），find 恒返回 None
      （降级精确缓存口径，零行为变化）。
    """

    def __init__(self) -> None:
        self._entries: dict[str, _SemanticEntry] = {}
        self._lock = threading.Lock()
        # 观测统计：命中/未命中计数（get_semantic_cache_stats 消费）
        self._hits: int = 0
        self._misses: int = 0
        self._embed_failures: int = 0

    def upsert(self, cache_file: str, prompt: str, response: str) -> bool:
        """把缓存条目做嵌入后加入索引（嵌入失败时记统计并返回 False）。"""
        if not _semantic_cache_enabled():
            return False
        if not prompt or not response:
            return False
        # 嵌入（惰性导入：embedding_utils 本身零硬依赖，加载安全）
        from src.utils.embedding_utils import embed_text

        vec = embed_text(prompt)
        if vec is None:
            with self._lock:
                self._embed_failures += 1
            return False
        with self._lock:
            self._entries[cache_file] = _SemanticEntry(
                cache_file=cache_file, prompt=prompt, response=response, embedding=vec
            )
        return True

    def find(self, prompt: str) -> tuple[str, str] | None:
        """按语义相似度查找缓存响应。

        Args:
            prompt: 当前 LLM 调用的 user_message 文本。

        Returns:
            (命中的 cache_file, 缓存响应文本)；无命中或嵌入不可用时 None。
            命中统计 +1（get_semantic_cache_stats 观测）。
        """
        if not _semantic_cache_enabled():
            return None
        from src.utils.embedding_utils import embed_text

        vec = embed_text(prompt)
        if vec is None:
            with self._lock:
                self._embed_failures += 1
                self._misses += 1
            return None
        threshold = _semantic_threshold()
        best_file: str | None = None
        best_score = 0.0
        best_response: str | None = None
        with self._lock:
            items = list(self._entries.values())
        if not items:
            with self._lock:
                self._misses += 1
            return None
        # 余弦相似度（嵌入已 L2 归一化时等价点积；保守用完整余弦公式）
        import math

        pq = math.sqrt(sum(x * x for x in vec))
        for entry in items:
            e = entry.embedding
            pe = math.sqrt(sum(x * x for x in e))
            if pq == 0.0 or pe == 0.0:
                continue
            dot = sum(a * b for a, b in zip(vec, e, strict=False))
            score = dot / (pq * pe)
            if score > best_score:
                best_score = score
                best_file = entry.cache_file
                best_response = entry.response
        if best_file is not None and best_response is not None and best_score >= threshold:
            with self._lock:
                self._hits += 1
            logger.info(
                "5.1 语义缓存命中：similarity=%.3f (threshold=%.2f) file=%s",
                best_score,
                threshold,
                os.path.basename(best_file),
            )
            return best_file, best_response
        with self._lock:
            self._misses += 1
        return None

    def stats(self) -> dict[str, int]:
        """观测统计（命中/未命中/嵌入失败/索引条目数）。"""
        with self._lock:
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "embed_failures": self._embed_failures,
            }


# 进程内单例（与 LLM 文件缓存 LRU 同口径：进程级共享，--parallel 线程安全）
_index = SemanticCacheIndex()
_index_lock = threading.Lock()


def get_semantic_index() -> SemanticCacheIndex:
    """获取进程内语义缓存索引单例。"""
    return _index


def build_semantic_index_from_cache_dir(cache_dir: str, max_entries: int | None = None) -> int:
    """从文件缓存目录构建语义索引（扫描最近 max_entries 个 .json 文件）。

    惰性构建：每轮 LLM 调用前的"精确缓存未命中"路径调用（带节流——
    每 _REBUILD_INTERVAL 秒才重扫一次目录，嵌入推理成本可控）。

    Args:
        cache_dir: 文件缓存目录（AITESTER_LLM_CACHE_DIR 口径）。
        max_entries: 扫描文件数上限（None 时读 SEMANTIC_CACHE_MAX_ENTRIES）。

    Returns:
        本次成功加入索引的条目数（嵌入失败/文件损坏的跳过）。
    """
    if not _semantic_cache_enabled():
        return 0
    limit = max_entries if max_entries is not None else _max_index_entries()
    try:
        import glob as _glob

        files = _glob.glob(os.path.join(cache_dir, "*.json"))
    except OSError:
        return 0
    if not files:
        return 0
    # 按 mtime 取最近 limit 个（缓存文件不可变，读入即嵌入）
    with contextlib.suppress(OSError):
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    files = files[:limit]
    index = get_semantic_index()
    added = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
            prompt = str(data.get("prompt", ""))
            response = str(data.get("response", ""))
            if index.upsert(f, prompt, response):
                added += 1
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue  # 损坏文件跳过（与文件缓存读侧"半截 JSON 降级重调"同口径）
    if added:
        logger.info("5.1 语义缓存索引：新增 %d 条（目录 %s，扫描 %d 文件）", added, cache_dir, len(files))
    return added


def find_semantic_cache(cache_file: str, prompt: str, response_for_update: str | None = None) -> tuple[str, str] | None:
    """语义命中查找 + 新条目入索引的复合入口（_call_llm_with_cache 接线点）。

    流程：
    1. 索引未命中时按需从 cache_file 所在目录补建（节流 60s）；
    2. find(prompt) 命中 → 返回 (cache_file, response)；
    3. 未命中且提供了 response_for_update（LLM 调用成功后）→ 新条目
       入索引（下轮近似 prompt 可命中）。

    Args:
        cache_file: 本次调用的文件缓存键路径（索引条目的归属键）。
        prompt: 本次 LLM 调用的 user_message。
        response_for_update: 非 None 时把该响应作为新条目入索引（调用后路径）。

    Returns:
        (命中的 cache_file, 响应文本) 或 None（降级精确缓存口径）。
    """
    index = get_semantic_index()
    hit = index.find(prompt)
    if hit is not None:
        return hit
    if response_for_update is not None:
        index.upsert(cache_file, prompt, response_for_update)
    return None


# 索引重建节流（秒）：同一进程内每 _REBUILD_INTERVAL 秒最多重扫一次目录
_REBUILD_INTERVAL = 60.0
_last_rebuild_ts: float = 0.0
_rebuild_ts_lock = threading.Lock()


def maybe_rebuild_semantic_index(cache_dir: str) -> int:
    """带节流的索引重建入口（_call_llm_with_cache 精确未命中路径调用）。

    节流内（距上次 < 60s）返回 0 不重扫（嵌入推理成本可控，
    进程内索引持续增长的场景由 upsert 路径覆盖）。
    """
    global _last_rebuild_ts
    import time as _time

    with _rebuild_ts_lock:
        now = _time.time()
        if now - _last_rebuild_ts < _REBUILD_INTERVAL:
            return 0
        _last_rebuild_ts = now
    return build_semantic_index_from_cache_dir(cache_dir)


def get_semantic_cache_stats() -> dict[str, int | float | bool]:
    """语义缓存观测统计（供 get_workflow_stats / 实验汇总消费）。"""
    s = get_semantic_index().stats()
    return {
        **s,
        "enabled": _semantic_cache_enabled(),
        "threshold": _semantic_threshold(),
        "max_entries": _max_index_entries(),
    }


def reset_semantic_index() -> None:
    """清空语义索引与统计（测试隔离 / 嵌入后端切换时调用）。"""
    global _last_rebuild_ts
    with _index_lock:
        _index._entries.clear()
        _index._hits = 0
        _index._misses = 0
        _index._embed_failures = 0
        _last_rebuild_ts = 0.0


__all__ = [
    "SemanticCacheIndex",
    "build_semantic_index_from_cache_dir",
    "find_semantic_cache",
    "get_semantic_cache_stats",
    "get_semantic_index",
    "maybe_rebuild_semantic_index",
    "reset_semantic_index",
]
