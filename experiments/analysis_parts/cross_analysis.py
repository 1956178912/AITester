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

    2.1 改进联动：details[].contamination_risk_level（high/medium/low/unknown/
    not_applicable，由 run_benchmark._compute_contamination_risk_level 产出）
    与 passed 交叉，验证"污染效应"是否真实存在——若 high 风险任务成功率
    显著高于 low 风险任务，提示系统确实在"背出"黄金补丁而非真正定位根因。
    not_applicable（无黄金补丁材料，N7 口径）与 unknown（检测腿没测成——BM 轮
    起崩溃腿不再折成 low）计入独立分桶展示，但**不进入** high vs low 对照
    （无法分类的样本不参与污染效应对比）。
    BP 轮（2026-10-22）把「这一行根本没记录级别」从沉默里领出来：改前一条
    `if not level: continue` 把键不存在 / 值为 null / 空串 / 其他假值四种形状
    一起丢掉，既不进桶也不计数，读者只看到 `by_risk_level` 的合计比行数少
    （或者整节 available=False 消失）。本轮**只加披露**：`n_details` /
    `unobserved`（按形状分档）/ `unobserved_total`，桶的键集合与各桶数值逐位不变，
    缺席行仍然不进对照——分档不是把它们判成某一档。

    与 statistical_analysis.contamination_view_summary 的分工差异（BP 轮起可对账）：
    本函数把缺席行记进 `unobserved`，后者按批次 IX 的历史口径把它们并计进
    `unknown`，并披露 `unknown_of_which_absent`；两数因此恒满足
    `view.unknown == len(by_level["unknown"]) + cross.unobserved_total`。

    Returns:
        {"available": bool,
         "by_risk_level": {"high": {tasks, passed, success_rate},
                            "medium": {...}, "low": {...},
                            "unknown": {...}, "not_applicable": {...}},
         "high_vs_low_success_delta": float | None,
         "n_details": int,
         "unobserved": {"key_absent", "value_null", "value_blank", "other_falsy"},
         "unobserved_total": int}
        没有任何一行记录过级别时 available=False（`reason` 点名是"没有行"还是
        "有行但都没记录"）；两档不齐时 delta 为 None 且 `delta_missing_buckets`
        点出缺哪一档。
    """
    observed = 0
    unobserved: dict[str, int] = {"key_absent": 0, "value_null": 0, "value_blank": 0, "other_falsy": 0}
    by_level: dict[str, dict[str, Any]] = {}
    for row in details:
        if "contamination_risk_level" not in row:
            unobserved["key_absent"] += 1
            continue
        level = row.get("contamination_risk_level")
        if level is None:
            unobserved["value_null"] += 1
            continue
        # 只把「精确空串」算未记录：空白串在批次 IX 的消费侧是真值、会自成一档，
        # 改前本函数同样把它记作观测到（str(level) 进桶）——口径不动，恒等式才无条件成立。
        if level == "":
            unobserved["value_blank"] += 1
            continue
        # 其余假值（False / 0）：改前同样被 `if not level` 丢弃，方向不变，只是改后有名有姓
        if not level:
            unobserved["other_falsy"] += 1
            continue
        observed += 1
        stat = by_level.setdefault(str(level), {"tasks": 0, "passed": 0})
        stat["tasks"] += 1
        if row.get("passed"):
            stat["passed"] += 1
    disclosure = {"n_details": len(details), "unobserved": unobserved, "unobserved_total": sum(unobserved.values())}
    if observed == 0:
        # 改前这里返回 {"available": False, "by_risk_level": {}}——整节从报告里消失，
        # "这批 30 行全都没记录" 与 "根本没有行" 同形。判定方向不变（仍然 available=False）。
        return {
            "available": False,
            "by_risk_level": {},
            "reason": "no_rows" if not details else "no_level_recorded",
            **disclosure,
        }
    result: dict[str, Any] = {"available": True, "by_risk_level": {}, **disclosure}
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
    else:
        # docstring 声明 float | None；改前两档不齐时是「键不存在」，消费方 .get() 到
        # 的 None 与「真值 None」同形——本轮把 None 落到位，并点名缺哪一档。
        result["high_vs_low_success_delta"] = None
        result["delta_missing_buckets"] = [lv for lv, r in (("high", high_rate), ("low", low_rate)) if r is None]
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
