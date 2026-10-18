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

from src.utils.env_utils import env_flag

_RECALL_K_DEFAULT = 3
_RELEVANT_THRESHOLD_DEFAULT = 0.7


def _recall_enabled() -> bool:
    """RAG_RETRIEVAL_RECALL_ENABLE=true 时启用 Recall@k 观测（默认关）。"""
    return env_flag("RAG_RETRIEVAL_RECALL_ENABLE")


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


def _evaluate_recall(
    refs: list[dict[str, Any]] | None,
    *,
    k: int | None,
    threshold: float | None,
) -> tuple[float | None, int]:
    """一次解析有效 k、直接计数相关条数，返回 (Recall@k, 整数相关数)。

    A22（2026-10-18 第三方审查 P2）修复的单一事实源：

    - 历史缺陷：`retrieval_relevance()` 先用内部默认 k（如 3）算出比例
      Recall@k，再用 `effective_k = k if (k and len(refs) >= k) else len(refs)`
      反推相关数——`k=None` 且 `len(refs) > 默认 k` 时 `effective_k=len(refs)`
      把分母放大，得到**多于实际 top-k 相关数**的计数（如 top-3 内 2 个相关、
      refs 共 4 条 → round(2/3*4)=3）。比例舍入后再反推整数本身也不可逆。
    - 现口径：有效 k 只解析一次（显式 k 优先，否则 RAG_RECALL_K），
      top-k 切片与相关判定在同一函数内完成，**直接返回整数相关数**；
      Recall@k 由同一计数派生（`count / effective_k`），两条对外 API
      观察到的相关数与比例严格自洽。

    可测量性（保守 None 口径，与 compute_recall_at_k 文档一致）：
    refs 为 None / 空、开关关闭、len(refs) < k、k 非正 → `(None, 0)`；
    否则 `(round(count/k, 4), count)`，count ∈ [0, k]。
    """
    if refs is None or not refs:
        return None, 0
    if not _recall_enabled():
        return None, 0
    effective_k = _recall_k() if k is None else int(k)
    if effective_k <= 0 or len(refs) < effective_k:
        return None, 0
    eff_threshold = _relevant_threshold() if threshold is None else float(threshold)
    top_k = refs[:effective_k]
    relevant_count = sum(
        1 for r in top_k if isinstance(r, dict) and float(r.get("similarity", 0.0) or 0.0) >= eff_threshold
    )
    return round(relevant_count / effective_k, 4), relevant_count


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

    A22：与 `retrieval_relevance()` 共用 `_evaluate_recall()` 的**一次解析
    + 直接整数计数**口径（有效 k 只解析一次，比例由整数计数派生，不做
    反向整数还原）。

    Args:
        refs: RAG 检索结果列表（每项含 similarity 字段；None 表示未启用
            RAG / 无历史案例）。
        k: 显式 k（None 时读 RAG_RECALL_K，默认 3）。
        threshold: 显式"相关"阈值（None 时读 RAG_RECALL_RELEVANT_THRESHOLD，
            默认 0.7）。

    Returns:
        - refs 为 None / 空列表 → None（不可测量，保守口径）；
        - RAG_RETRIEVAL_RECALL_ENABLE=false（默认）→ None（历史口径零变化）；
        - 否则 → |相关数| / k ∈ [0.0, 1.0]（len(refs) < k 时按不可测量记
          None——检索结果不足 k 个时分母缩小会抬高数值）。
    """
    recall, _relevant_count = _evaluate_recall(refs, k=k, threshold=threshold)
    return recall


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

    A22（2026-10-18 第三方审查 P2）：`retrieval_relevant_count` 直接取
    `_evaluate_recall()` 返回的**整数相关数**——历史实现用
    `round(recall * effective_k)` 从已舍入比例反推，且 `k=None` 时
    `effective_k` 误用 `len(refs)`（refs 多于默认 k 时计数被放大）。

    用途：实验分析侧做"检索质量 ↔ 生成质量"相关分析（STVR RQ2：
    检索策略对生成质量的差异化影响）——若 retrieval_relevance 与
    mutation_score / detection_rate 正相关，则 RAG 的增益可归因
    到"检索到了真正相关的案例"；若不相关或负相关，则增益来自
    "检索量"而非"检索质量"（审稿人核心可归因性追问）。
    """
    total = len(refs) if refs else 0
    recall, relevant_count = _evaluate_recall(refs, k=k, threshold=threshold)
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
