"""跨主题交叉分析函数（从 analyze_results.py 拆分，0.7 债务项 1.6）。

包含数据污染交叉分析与 venv 缓存统计快照，
函数间无耦合，依赖 detect_contamination（experiments.contamination_check）。
"""

from __future__ import annotations

from typing import Any

# _contamination_cross_analysis 的 docstring 引用 detect_contamination 名称，
# 但函数体实际只消费 details[].contamination_risk_level（由 build_analysis 里
# detect_contamination 产出后写入 details），本文件不直接调用 → 不 import 该符号，
# 避免 F401 死导入


def _contamination_cross_analysis(details: list[dict[str, Any]]) -> dict[str, Any]:
    """5.3 失败分析 × 污染检测交叉：高污染风险任务是否具有更高修复成功率。

    2.1 改进联动：details[].contamination_risk_level（high/medium/low，由
    contamination_check.detect_contamination 产出）与 passed 交叉，验证
    "污染效应"是否真实存在——若 high 风险任务成功率显著高于 low 风险任务，
    提示系统确实在"背出"黄金补丁而非真正定位根因。

    Returns:
        {"available": bool,
         "by_risk_level": {"high": {tasks, passed, success_rate},
                            "medium": {...}, "low": {...}},
         "high_vs_low_success_delta": float | None}
        无 contamination_risk_level 字段时 available=False。
    """
    observed = 0
    by_level: dict[str, dict[str, Any]] = {}
    for row in details:
        level = row.get("contamination_risk_level")
        if not level:
            continue
        observed += 1
        stat = by_level.setdefault(str(level), {"tasks": 0, "passed": 0})
        stat["tasks"] += 1
        if row.get("passed"):
            stat["passed"] += 1
    if observed == 0:
        return {"available": False, "by_risk_level": {}}
    result: dict[str, Any] = {"available": True, "by_risk_level": {}}
    for level, stat in by_level.items():
        total = stat["tasks"]
        result["by_risk_level"][level] = {
            "tasks": total,
            "passed": stat["passed"],
            "success_rate": round(stat["passed"] / total, 4) if total else 0.0,
        }
    high_rate = result["by_risk_level"].get("high", {}).get("success_rate")
    low_rate = result["by_risk_level"].get("low", {}).get("success_rate")
    if high_rate is not None and low_rate is not None:
        result["high_vs_low_success_delta"] = round(high_rate - low_rate, 4)
    return result


def _venv_cache_stats_snapshot() -> dict[str, Any] | None:
    """4.4 依赖缓存命中率统计：读取 ExecutorAgent venv 磁盘缓存的命中数据。

    缓存统计由 src/tools/dependency.py 维护（按依赖组合复用 venv），
    此处仅做只读快照，供分析报告输出缓存复用效率。导入失败或统计
    为空（尚无缓存事件）时返回 None，渲染时跳过章节，不崩溃。

    4.4 改进：额外附带缓存容量信息（总大小 + 是否超告警阈值），
    超限时输出清理建议（只监控不自动清理）。
    """
    try:
        from src.tools.dependency import check_venv_cache_size, get_venv_cache_stats
    except Exception:
        return None
    stats = get_venv_cache_stats()
    if stats.get("total", 0) == 0:
        # 尚无缓存事件时仍可提供容量监控（目录可能存在历史 venv）
        try:
            size = check_venv_cache_size()
            return {**size, "hits": 0, "creates": 0, "total": 0, "hit_rate": 0.0}
        except Exception:
            return None
    try:
        size = check_venv_cache_size()
        stats.update(size)
    except Exception:
        pass
    return stats
