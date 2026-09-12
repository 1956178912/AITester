"""
RAG 检索器单例与检索质量指标辅助模块。

从 workflow.py 拆分而来（代码可维护性优化）：承载 TestCaseRetriever 的单例
初始化（双重检查锁定）、初始化失败短路标志，以及单次检索质量指标的构建。
节点函数通过 `from .rag import ...` 复用，避免重复初始化 ChromaDB 客户端。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from config import RAG_COLLECTION_NAME, RAG_PERSIST_PATH, RAG_TTL_SECONDS

logger = logging.getLogger(__name__)

# 可选导入 RAG 检索器（未安装 chromadb 时优雅降级，不影响主流程）
# 使用延迟导入而非 top-level import，避免 chromadb 未安装时整个项目无法启动
try:
    from src.rag.retriever import TestCaseRetriever

    RAG_MODULE_AVAILABLE = True
except ImportError:
    RAG_MODULE_AVAILABLE = False
    TestCaseRetriever = None
    logger.info("RAG 模块未就绪（chromadb 未安装），将跳过检索增强")

# ─── RAG 检索器单例 ────────────────────────────────────────────────────────────
# _rag_retriever 模块级缓存：避免每次节点调用都重新初始化 ChromaDB 客户端
# ChromaDB 客户端初始化涉及模型加载和向量存储打开，耗时 2-6 秒
# 单例化后整个工作流执行期间只初始化一次
_rag_retriever = None
# 线程锁：保护单例初始化的双重检查锁定，确保多线程环境下的安全性
_rag_lock = threading.Lock()
# RAG 初始化失败标志：一旦构造抛异常即置位，后续节点调用直接返回 None 不再重试
# （ChromaDB 持久目录损坏/模型下载失败属持续性故障，重复初始化只浪费 2-6s/次）
_rag_init_failed = False


def get_rag_retriever():
    """
    获取 RAG 检索器单例实例（线程安全版本）。

    使用双重检查锁定模式（Double-Checked Locking）：
    - 第一次检查（无锁）：若已初始化直接返回，避免后续调用的锁开销
    - 加锁后第二次检查：防止多线程并发时多次初始化

    保证 ChromaDB 客户端在整个工作流执行期间只初始化一次，
    避免每个节点都创建新实例导致的 2-6 秒重复初始化开销。

    Returns:
        TestCaseRetriever 实例。若 RAG 模块不可用则返回 None。
    """
    global _rag_retriever, _rag_init_failed
    # 初始化曾失败（持久目录损坏、模型下载失败等持续性故障）：直接返回 None，
    # 不再每节点调用都重付 2-6s 初始化 + 重复 warning。此前 except 分支把
    # _rag_retriever 置回 None 是 no-op（变量本就是 None），快路径检查失效，
    # 每个 generator/executor/debugger 节点都会重复尝试初始化
    if _rag_init_failed:
        return None
    # 第一次检查：无锁快速路径，已初始化时直接返回
    if _rag_retriever is not None:
        return _rag_retriever
    # 加锁进行二次检查和初始化
    with _rag_lock:
        # 第二次检查：防止多线程并发时多次初始化
        if _rag_retriever is None and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
            try:
                # P1 优化：此前总是无参构造（内存模式，进程重启数据全丢）。
                # 现由 config 控制持久化路径（默认项目下 rag_data/）与 TTL，
                # 保证跨实验运行的历史用例/修复案例可复用；RAG_PERSIST_PATH
                # 设为空字符串可回退内存模式。
                _rag_retriever = TestCaseRetriever(
                    collection_name=RAG_COLLECTION_NAME,
                    persist_path=RAG_PERSIST_PATH or None,
                    ttl_seconds=RAG_TTL_SECONDS,
                )
                logger.info("RAG 检索器单例已初始化（持久化=%s）", RAG_PERSIST_PATH or "内存模式")
            except Exception as e:
                logger.warning("RAG 检索器初始化失败，将跳过 RAG 增强: %s", e)
                # 持续性故障标志：后续 get_rag_retriever() 直接返回 None 不再重试。
                # 此前此处仅把 _rag_retriever 置 None（本就是 None，no-op），
                # 每个 generator/executor/debugger 节点都会重复尝试初始化
                _rag_init_failed = True
    return _rag_retriever


def _build_rag_stat(rag_refs: list | None, kind: str) -> dict[str, Any] | None:
    """构建一次 RAG 检索的质量指标记录（P1：消融实验单独报告检索质量）。

    容错：参考案例元素可能是 dict（正常）或 str（测试 mock），
    相似度缺失时记 0.0，不中断主流程。

    Args:
        rag_refs: 一次检索返回的参考案例列表（None 表示未启用 RAG）。
        kind: 检索类型（"test_cases" 或 "repairs"）。

    Returns:
        指标字典；未检索（rag_refs 为 None）时返回 None。
    """
    if rag_refs is None:
        return None
    sim_values = [float(c.get("similarity", 0.0) or 0.0) for c in rag_refs if isinstance(c, dict)]
    return {
        "kind": kind,
        "results": len(rag_refs),
        "max_similarity": max(sim_values) if sim_values else None,
        "avg_similarity": (sum(sim_values) / len(sim_values)) if sim_values else None,
    }
