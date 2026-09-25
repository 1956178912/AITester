"""
2.1 改进：真实语义嵌入钩子（可选依赖，默认零外部依赖保守口径）。

背景：
    experiments/contamination_check.py 的语义级污染检测当前使用"token 词袋
    余弦"作为 CodeBERT 嵌入余弦的零依赖保守代理。本模块提供可接入真实
    嵌入模型的钩子，使污染检测在装有嵌入库时自动升级为"真实语义嵌入余弦"，
    未安装时透明回退到词袋余弦（保持历史保守口径不变）。

设计约束（与 contamination_check 一致：零默认外部依赖、可复算）：
    - 默认行为：embed_text() 按优先级尝试已安装的嵌入后端
      （sentence-transformers → chromadb DefaultEmbeddingFunction），
      全部缺失时返回 None；调用方（contamination_check）收到 None 时
      自动回退 token 词袋余弦，行为与未接入时完全一致。
    - 显式指定：环境变量 EMBEDDING_BACKEND 可强制选择后端
      （"sentence_transformers" / "chromadb" / "none"），便于实验对照。
    - cosine_similarity() 用 numpy 实现（项目已依赖 numpy），缺失时
      纯 Python 回退，不引入新硬依赖。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 嵌入后端选择（环境变量 EMBEDDING_BACKEND，默认 auto）：
# - "auto"（默认）：按优先级尝试 sentence-transformers → chromadb，
#   首个可用即采用；都不可用返回 None（调用方回退词袋余弦）。
# - "sentence_transformers" / "chromadb"：强制指定后端（缺失时报错并回退 None）。
# - "none"：禁用真实嵌入，强制返回 None（保持词袋余弦保守口径，
#   用于实验 A/B 对照"真实嵌入 vs 词袋代理"）。
_EMBEDDING_BACKEND_ENV = "EMBEDDING_BACKEND"

# 模块级嵌入后端缓存（避免每次调用重复加载重型模型）
_backend_cache: dict[str, Any] = {"instance": None, "name": None}
_backend_initialized: bool = False


def _backend_choice() -> str:
    """解析 EMBEDDING_BACKEND 环境变量（小写，默认 auto）。"""
    return os.getenv(_EMBEDDING_BACKEND_ENV, "auto").strip().lower()


def _load_backend() -> tuple[str | None, Any]:
    """加载嵌入后端（模块级缓存，仅首次真正加载）。

    Returns:
        (backend_name, embed_fn)；不可用时 (None, None)。
        backend_name ∈ {"sentence_transformers", "chromadb"}。
    """
    global _backend_cache, _backend_initialized
    if _backend_initialized:
        return _backend_cache["name"], _backend_cache["instance"]

    choice = _backend_choice()
    instance: Any = None
    name: str | None = None

    if choice in ("auto", "sentence_transformers"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            instance = SentenceTransformer("all-MiniLM-L6-v2")
            name = "sentence_transformers"
            logger.info("嵌入后端已加载: sentence_transformers(all-MiniLM-L6-v2)")
        except ImportError:
            if choice == "sentence_transformers":
                logger.warning("EMBEDDING_BACKEND=sentence_transformers 但未安装 sentence-transformers，回退 None")
            instance, name = None, None

    if instance is None and choice in ("auto", "chromadb"):
        try:
            from chromadb import EmbeddingFunction  # type: ignore  # noqa: F401
            from chromadb.utils.embedding_functions import (  # type: ignore
                DefaultEmbeddingFunction,
            )

            instance = DefaultEmbeddingFunction()
            name = "chromadb"
            logger.info("嵌入后端已加载: chromadb(DefaultEmbeddingFunction)")
        except Exception:
            if choice == "chromadb":
                logger.warning("EMBEDDING_BACKEND=chromadb 但 chromadb 嵌入不可用，回退 None")
            instance, name = None, None

    _backend_cache = {"instance": instance, "name": name}
    _backend_initialized = True
    return name, instance


def _embed_with_backend(instance: Any, text: str) -> list[float] | None:
    """用已加载的 instance 嵌入单条文本（不同后端调用口径不同）。"""
    if instance is None:
        return None
    backend = _backend_cache.get("name")
    try:
        if backend == "sentence_transformers":
            vec = instance.encode(text, normalize_embeddings=True)
            return [float(x) for x in vec]
        if backend == "chromadb":
            vecs = instance([text])
            if not vecs:
                return None
            return [float(x) for x in vecs[0]]
    except Exception as e:
        logger.warning("嵌入后端 %s 嵌入失败（回退 None）: %s", backend, e)
        return None
    return None


def embed_text(text: str) -> list[float] | None:
    """返回单条文本/代码的语义嵌入向量（真实嵌入，未接入时 None）。

    后端优先级（EMBEDDING_BACKEND=auto 时）：
        sentence-transformers > chromadb DefaultEmbeddingFunction > None。
    EMBEDDING_BACKEND=none 时强制返回 None（保持词袋余弦保守口径）。

    接入方亦可 monkeypatch 本函数（contamination_check._embed_code 委托到
    本钩子），提供自定义 CodeBERT / 本地嵌入实现。

    Args:
        text: 待嵌入文本（contamination_check 传入两补丁修改行 token 拼接串）。

    Returns:
        float 列表（真实嵌入向量）；未接入嵌入模型或空文本时 None。
    """
    choice = _backend_choice()
    if choice == "none":
        return None
    if not text or not text.strip():
        # 空文本无有效 token：嵌入无意义，返回 None 让调用方回退
        # （contamination_check 空补丁时 semantic 回退词袋余弦 0.0，
        # 避免把空文本嵌入余弦误算成高相似）
        return None
    _name, instance = _load_backend()
    if instance is None:
        return None
    return _embed_with_backend(instance, text)


def backend_name() -> str | None:
    """当前生效的嵌入后端名（sentence_transformers / chromadb）；未接入时 None。

    供污染检测报告标注"语义级相似度来源"（真实嵌入 vs 词袋代理）。
    """
    choice = _backend_choice()
    if choice == "none":
        return None
    name, instance = _load_backend()
    return name if instance is not None else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """两向量余弦相似度（-1.0 ~ 1.0；contamination_check 语义级消费）。

    用 numpy 计算（项目已依赖 numpy，零新增硬依赖）；numpy 缺失时纯 Python
    回退。维度不一致或零向量返回 0.0（保守，不报错）。

    Args:
        a: 向量 A（float 列表）。
        b: 向量 B（float 列表）。

    Returns:
        余弦相似度（0.0-1.0，已夹取非负保守口径，与词袋余弦口径可比）。
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    try:
        import numpy as np

        va = np.asarray(a, dtype=float)
        vb = np.asarray(b, dtype=float)
        na = float(np.linalg.norm(va))
        nb = float(np.linalg.norm(vb))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return round(max(0.0, float(np.dot(va, vb)) / (na * nb)), 4)
    except ImportError:
        # numpy 缺失：纯 Python 回退
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return round(max(0.0, dot / (na * nb)), 4)
