"""RAG 检索质量与 Token 效率主题函数（从 analyze_results.py 拆分，0.7 债务项 1.6）。

所有函数均为纯函数，只消费 details[] 与 baseline 级字段，
不依赖文件系统或模块级状态。运行期逻辑与原 analyze_results.py 完全一致。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def _iter_rag_stats(details: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """遍历 details[].rag_stats 中的 dict 记录，跳过非 dict 元素。

    2026-09-27 round10 P2：rag_stats 元素正常为 dict（kind/results/max_
    similarity），但历史落盘 / 手动编辑的 JSON 可能混入字符串或数字
    （非 dict 元素调 .get 会 AttributeError 使 build_analysis 整体崩溃）。
    统一经此生成器遍历，非 dict 元素静默跳过（口径：贡献 0 检索记录）。
    """
    for row in details:
        for s in row.get("rag_stats") or []:
            if not isinstance(s, dict):
                continue
            yield s


def _token_metrics_from_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    """旧版 JSON（无 baseline 级 token_metrics）兜底：从逐任务 token_usage 累加。"""
    total_input = sum((r.get("token_usage") or {}).get("input_tokens", 0) for r in details)
    total_output = sum((r.get("token_usage") or {}).get("output_tokens", 0) for r in details)
    total_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in details)
    total = len(details)
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_llm_calls": total_calls,
        "avg_tokens_per_task": round((total_input + total_output) / total, 2) if total > 0 else 0,
    }


def _rag_by_kind_from_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 指标自动汇总：按检索类型（test_cases vs repairs）分解检索质量。

    从 details[].rag_stats 逐条累计（每条记录 kind / results / max_similarity），
    分析"参考测试风格"与"参考修复方案"两类检索各自的命中率与相似度水平。

    Returns:
        {"test_cases": {retrievals, hits, hit_rate, avg_max_similarity},
         "repairs": {...}}；无 rag_stats 时返回空 dict。
    """
    per_kind: dict[str, dict[str, Any]] = {}
    for s in _iter_rag_stats(details):
        kind = s.get("kind", "unknown")
        stat = per_kind.setdefault(kind, {"retrievals": 0, "hits": 0, "sims": []})
        stat["retrievals"] += 1
        if s.get("results", 0) > 0:
            stat["hits"] += 1
        if s.get("max_similarity") is not None:
            stat["sims"].append(s["max_similarity"])
    result: dict[str, Any] = {}
    for kind, stat in per_kind.items():
        sims = stat.pop("sims")
        stat["hit_rate"] = round(stat["hits"] / stat["retrievals"], 4) if stat["retrievals"] else 0.0
        stat["avg_max_similarity"] = round(sum(sims) / len(sims), 4) if sims else None
        result[kind] = stat
    return result


def _rag_hit_by_failure_category(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 指标自动汇总：RAG 命中 × 失败类别交叉表。

    仅统计失败任务（passed=False），按 error_category 分组（1.1 细化后
    rag_retrieval_empty / patch_validation_failed 单独成组），记录组内
    "至少一次 RAG 检索命中"的任务数，用于分析 RAG 对哪些错误类型修复
    帮助最大（命中占比高 = 检索增强实际发生）。

    Returns:
        {error_category: {"total": 任务数, "with_hit": RAG 有命中的任务数}}；
        无失败任务时返回空 dict。
    """
    cross: dict[str, dict[str, int]] = {}
    for r in details:
        if r.get("passed"):
            continue
        cat = r.get("error_category") or "unknown"
        stat = cross.setdefault(cat, {"total": 0, "with_hit": 0})
        stat["total"] += 1
        if any(s.get("results", 0) > 0 for s in _iter_rag_stats([r])):
            stat["with_hit"] += 1
    return cross


def _rag_token_efficiency(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG Token 效率增益：对比启用/禁用 RAG 任务的 Token 消耗与迭代次数。

    2.3 改进：当前仅报告 Hit Rate/MRR，本函数从 details[].rag_enabled
    （或 rag_stats 非空推断）把任务分为"启用 RAG"与"未启用 RAG"两组，
    对比两组的平均 Token / 平均迭代 / 成功率，回答"RAG 检索是否值得其
    检索 + 提示注入的 Token 开销"。

    分组口径：
    - rag_stats 非空（任务内发生过检索）= 启用 RAG 组；
    - 其余 = 未启用 RAG 组（含 RAG 关闭时的历史任务）。
    - 两组任一为空时 available=False（无法对比）。

    Returns:
        {"available": bool, "rag_group": {tasks, avg_tokens, avg_iterations, success_rate},
         "no_rag_group": {...}, "token_delta_ratio": float,
         "iteration_delta": int}
    """
    rag_rows: list[dict[str, Any]] = []
    no_rag_rows: list[dict[str, Any]] = []
    for row in details:
        is_rag = bool(row.get("rag_stats")) or row.get("rag_enabled")
        (rag_rows if is_rag else no_rag_rows).append(row)
    if not rag_rows or not no_rag_rows:
        return {"available": False, "observed_rag_tasks": len(rag_rows), "observed_no_rag_tasks": len(no_rag_rows)}

    def _group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        # 2026-09-26 round10 P2：iterations/total_tokens 可能为非数字
        # （历史 JSON 混入异常值），int()/float() 崩溃使 build_analysis
        # 失败——安全归一（解析失败回退 0，口径不变：贡献 0）
        from experiments.analysis_parts.convergence_analysis import _safe_float, _safe_int

        avg_tokens = (
            round(sum(_safe_float((r.get("token_usage") or {}).get("total_tokens", 0) or 0) for r in rows) / n, 2)
            if n
            else 0.0
        )
        avg_iterations = round(sum(_safe_int(r.get("iterations", 0) or 0) for r in rows) / n, 2) if n else 0.0
        success_rate = round(sum(1 for r in rows if r.get("passed")) / n, 4) if n else 0.0
        return {"tasks": n, "avg_tokens": avg_tokens, "avg_iterations": avg_iterations, "success_rate": success_rate}

    rag_stat = _group_stats(rag_rows)
    no_rag_stat = _group_stats(no_rag_rows)
    token_delta_ratio = (
        round(rag_stat["avg_tokens"] / no_rag_stat["avg_tokens"], 4) if no_rag_stat["avg_tokens"] else None
    )
    iteration_delta = round(rag_stat["avg_iterations"] - no_rag_stat["avg_iterations"], 2)
    return {
        "available": True,
        "rag_group": rag_stat,
        "no_rag_group": no_rag_stat,
        "token_delta_ratio": token_delta_ratio,
        "iteration_delta": iteration_delta,
    }


def _rag_similarity_distribution(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 检索结果相关性分布：avg_max_similarity 的直方图分桶。

    2.3 改进：当前仅报告 Hit Rate 和 MRR，本函数把各检索记录的最高相似度
    按 0.1 步长分桶（0.0-0.1 ... 0.9-1.0），输出分布直方图，用于观察
    "检索结果是普遍低相关还是集中在高相关"，辅助判断检索库质量。

    Returns:
        {"available": bool, "histogram": {"0.0-0.1": n, ...},
         "total_retrievals": int, "avg_max_similarity": float | None}
    """
    bins = {f"{i * 0.1:.1f}-{(i + 1) * 0.1:.1f}": 0 for i in range(10)}
    total = 0
    sims: list[float] = []
    for s in _iter_rag_stats(details):
        ms = s.get("max_similarity")
        if ms is None:
            continue
        total += 1
        # 2026-09-27 round10 P1：相似度值可能为非数值（"0.5"/dict 等
        # 坏 JSON 混入）→ float() 崩溃使整份 build_analysis 失败，加
        # try/except 跳过该条目（口径：非数值值不计入检索统计）
        try:
            val = float(ms)
        except (TypeError, ValueError):
            total -= 1
            continue
        sims.append(val)
        # 归一化到 0.0-1.0（相似度可能 >1 或 <0，保守截断到 [0, 1]）
        # 2026-09-27 round10 P1：旧实现仅钳位上界 min(...,9)，负相似度
        # （-0.1 → int(-1.0)=-1 → bins 键 KeyError）使整份分析崩溃，
        # 下界一并钳位到 0（分桶落 0.0-0.1 桶，与"低相关"语义一致）
        idx = max(0, min(int(val * 10), 9))
        bins[f"{idx * 0.1:.1f}-{(idx + 1) * 0.1:.1f}"] += 1
        # 2026-09-27 round10 P2：均值按截断后口径计算（与"分桶截断到
        # [0,1]"注释一致）——旧实现 sims 存原始值，相似度 1.5 会让
        # avg_max_similarity 报告 1.5，与分桶 0.9-1.0 自相矛盾
        sims[-1] = min(max(val, 0.0), 1.0)
    if total == 0:
        return {"available": False, "histogram": {}, "total_retrievals": 0}
    return {
        "available": True,
        "histogram": {k: v for k, v in bins.items() if v > 0},
        "total_retrievals": total,
        "avg_max_similarity": round(sum(sims) / len(sims), 4) if sims else None,
    }
