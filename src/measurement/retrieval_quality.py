"""Recall@k 检索质量观测（STVR 实证研究批次，零 LLM 成本）。

背景：STVR（Software: Testing, Verification & Reliability）投稿导向的实证
研究设计要求把 RAG 检索的"领域知识注入"机制的**贡献可归因性**做量化——
"检索到的历史案例是否真的命中了目标失败模式"不能只看 avg_similarity
（相似度 ≠ 相关性命中率）。本模块提供**检索精度**观测层：

    Recall@k = |top-k 检索结果中"相关"案例数| / k

其中"相关"的判定口径（保守、确定性，零 LLM）：
    - 案例 similarity >= RAG_RECALL_RELEVANT_THRESHOLD（默认 0.7，与
      RAG_RELEVANCE_THRESHOLD 同量级）→ 判定为"相关"；
    - 检索结果为空（无历史案例 / RAG 未启用）→ Recall@k 记 None
      （不可测量，保守口径，与 _m1_metrics 的 None 占位一致）；
    - RAG_RETRIEVAL_RECALL_ENABLE=false（默认）时本函数返回 None
      （历史口径零变化）。

本函数是**纯函数**（不触碰 ChromaDB / 不读文件系统 / 不发网络），
供 src/graph/rag.py 的 _build_rag_stat_with_relevance 调用，把
recall_at_k 写进结果行的 rag_stats，使实验分析侧
（experiments/analysis_parts/rag_analysis.py）能直接消费
"检索质量 ↔ 生成质量"相关性（STVR 审稿人核心关注点）。

开关（环境变量，默认关，历史口径零变化）：
    - RAG_RETRIEVAL_RECALL_ENABLE：true 时计算 recall_at_k，否则恒 None
    - RAG_RECALL_K：top-k 的 k（默认 3，与 retrieve_test_cases top_k 一致）
    - RAG_RECALL_RELEVANT_THRESHOLD：判定"相关"的 similarity 下限（默认 0.7）

口径纪律（与 _m1_metrics 的 None 保守口径一致）：
    - 不可测量（无检索结果 / RAG 关闭）→ None，**不**记 0.0；
      0.0 的语义是"检索到了 k 个案例但 0 个相关"（检索质量差），
      与"根本没检索"（None）必须区分，防止分母缩小抬高分数。
"""

from __future__ import annotations

import os
from typing import Any

_RECALL_K_DEFAULT = 3
_RELEVANT_THRESHOLD_DEFAULT = 0.7


def _recall_enabled() -> bool:
    """RAG_RETRIEVAL_RECALL_ENABLE=true 时启用 Recall@k 观测（默认关）。"""
    return os.getenv("RAG_RETRIEVAL_RECALL_ENABLE", "false").lower() == "true"


def _recall_k() -> int:
    """Recall@k 的 k（默认 3，与 retrieve_test_cases 的 top_k 口径一致）。

    非法值（非正整数 / 越界）回退 3（保守，避免 k=0 除零或 k 过大
    超出实际 top_k 截断口径）。
    """
    raw = os.getenv("RAG_RECALL_K", "")
    try:
        v = int(raw)
        return v if 1 <= v <= 20 else _RECALL_K_DEFAULT
    except ValueError:
        return _RECALL_K_DEFAULT


def _relevant_threshold() -> float:
    """判定"相关"的 similarity 下限（默认 0.7，与 RAG_RELEVANCE_THRESHOLD 同量级）。"""
    raw = os.getenv("RAG_RECALL_RELEVANT_THRESHOLD", "")
    try:
        v = float(raw)
        return max(0.0, min(v, 1.0))
    except ValueError:
        return _RELEVANT_THRESHOLD_DEFAULT


def compute_recall_at_k(
    refs: list[dict[str, Any]] | None,
    *,
    k: int | None = None,
    threshold: float | None = None,
) -> float | None:
    """计算 Recall@k（纯函数，零 LLM 成本，保守 None 口径）。

    定义：
        Recall@k = |{r ∈ top-k : similarity(r) >= threshold}| / k

    判定"相关"用的是 similarity >= threshold（检索器侧已按
    similarity 降序排列，top-k 即前 k 个），而非"检索到 k 个案例"
    —— 避免把"检索器总能填满 k 个（即使低相关）"误报为高质量。

    Args:
        refs: RAG 检索结果列表（每项含 similarity 字段；None 表示未启用
            RAG / 无历史案例）。
        k: 显式 k（None 时读 RAG_RECALL_K，默认 3）。
        threshold: 显式"相关"阈值（None 时读 RAG_RECALL_RELEVANT_THRESHOLD，
            默认 0.7）。

    Returns:
        - refs 为 None / 空列表 → None（不可测量，保守口径）；
        - RAG_RETRIEVAL_RECALL_ENABLE=false（默认）→ None（历史口径零变化）；
        - 否则 → |相关数| / k ∈ [0.0, 1.0]（k 取 min(k, len(refs))，
          检索结果不足 k 个时分母按实际可用数计，避免"案例不够"被
          误报为"召回率低"——分母缩小 = 检索质量无法评估，记 None）。
    """
    if refs is None or not refs:
        return None  # 无检索结果 / RAG 未启用 → 不可测量
    if not _recall_enabled():
        return None  # 开关关 → 历史口径零变化
    if k is None:
        k = _recall_k()
    if threshold is None:
        threshold = _relevant_threshold()
    # 分母：取 min(k, len(refs))；若检索结果不足 k 个，召回率无法在
    # 完整 top-k 上评估（保守 None，避免分母缩小抬高数值）
    if len(refs) < k:
        return None
    top_k = refs[:k]
    relevant = sum(1 for r in top_k if isinstance(r, dict) and float(r.get("similarity", 0.0) or 0.0) >= threshold)
    return round(relevant / k, 4)


def retrieval_relevance(
    refs: list[dict[str, Any]] | None,
    *,
    k: int | None = None,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """检索相关性质量观测（STVR 可归因性要求，纯函数零 LLM）。

    返回 {"retrieval_relevance": Recall@k, "retrieval_relevant_count": n,
    "retrieval_total_refs": len(refs)}；refs 为空 / RAG 关闭时
    返回 {"retrieval_relevance": None, "retrieval_relevant_count": 0,
    "retrieval_total_refs": 0}（键集合同构，None 占位，与
    _m1_metrics 的保守口径一致）。

    用途：实验分析侧做"检索质量 ↔ 生成质量"相关分析（STVR RQ2：
    检索策略对生成质量的差异化影响）——若 retrieval_relevance 与
    mutation_score / detection_rate 正相关，则 RAG 的增益可归因
    到"检索到了真正相关的案例"；若不相关或负相关，则增益来自
    "检索量"而非"检索质量"（审稿人核心可归因性追问）。
    """
    total = len(refs) if refs else 0
    recall = compute_recall_at_k(refs, k=k, threshold=threshold)
    relevant_count = 0
    if recall is not None and refs:
        # 开关开启且可测量时，相关数 = round(recall * k)（k 取实际 min(k, len)）
        effective_k = k if (k and len(refs) >= k) else len(refs)
        relevant_count = round(recall * effective_k)
    return {
        "retrieval_relevance": recall,
        "retrieval_relevant_count": relevant_count,
        "retrieval_total_refs": total,
    }


def rag_stat_with_recall(
    refs: list[dict[str, Any]] | None,
    kind: str,
    relevance_filtered: int = 0,
    relevance_filter_rate: float = 0.0,
) -> dict[str, Any] | None:
    """_build_rag_stat_with_relevance 的 Recall@k 增强版（STVR 批次新增）。

    在既有 rag_stat（kind / results / max_similarity / avg_similarity /
    relevance_filtered / relevance_filter_rate）基础上追加
    recall_at_k + retrieval_relevance 字段。RAG_RETRIEVAL_RECALL_ENABLE
    默认关时 recall_at_k=None / retrieval_relevance=None（键集合仍同构，
    历史 JSON 消费方零变化）。
    """
    from src.graph.rag import _build_rag_stat_with_relevance

    base = _build_rag_stat_with_relevance(refs, kind, relevance_filtered, relevance_filter_rate)
    if base is None:
        return None
    recall = compute_recall_at_k(refs)
    base["recall_at_k"] = recall
    rel = retrieval_relevance(refs)
    base["retrieval_relevance"] = rel.get("retrieval_relevance") if rel else None
    base["retrieval_relevant_count"] = rel.get("retrieval_relevant_count", 0) if rel else 0
    return base
