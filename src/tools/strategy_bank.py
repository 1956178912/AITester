"""
策略银行（Strategy Bank，默认关）。

背景（P1 跨文件修复引擎突破 + 可观测性方向）：
    当前 `failure_kb.py` 是"失败案例知识库"（离线积累 → 在线 prompt 片段注入），
    粒度是"同类错误的历史案例"。策略银行更进一步：从工具调用轨迹（TraceSession
    结构化决策路径字段：decision_reason / strategy_selected / budget_remaining）
    中**挖掘失败签名（failure signature）**，建立"失败签名 → 策略"映射表，
    在预算约束下为仓库级修复提供策略选择（而非让 LLM 每次从零猜测）。

    2026 年 TraceCoder / 多策略辩论等框架的核心思想是：把历史执行轨迹中
    "哪些策略在哪些失败模式下有效"沉淀为可查询的策略库，新任务按失败
    签名检索最匹配策略，避免重复空转（对应文档 assessment §2.2 记录的
    "0/7 单源任务"缺口的策略侧解法）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `STRATEGY_BANK_ENABLE=false`（默认）时，本模块零行为变化：
      工作流图零改动，节点消费策略银行的路径不启用；
    - 策略银行是**纯静态映射表**（JSON 文件加载 + 签名匹配，零 LLM 成本）：
      签名 = (error_category, fix_strategy_tag, cross_file: bool)，
      策略 = {"strategy": str, "budget_hint": str, "prompt_hint": str}；
    - 在线消费侧（`select_strategy`）只读，不改写源文件；离线积累侧
      （`record_strategy_outcome`）把每次修复的 (签名, 策略, 是否成功)
      追加到策略库 JSON（供离线分析挖掘高频有效策略，不自动改写源）；
    - 签名匹配失败（无匹配条目）时返回 None（保守降级，调用方走历史
      单补丁口径，不阻断修复主流程）。

使用方式（_debugger_node 集成）：
    from src.tools.strategy_bank import select_strategy, strategy_bank_enabled

    if strategy_bank_enabled():
        strategy = select_strategy(error_category="assertion", fix_tag="logic_error", cross_file=False)
        if strategy:
            # 把 strategy["prompt_hint"] 注入 debugger prompt
            ...
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# 策略库默认路径（experiments/results 下，与 failure_knowledge_base.json 同目录）
_DEFAULT_BANK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experiments",
    "results",
    "strategy_bank.json",
)

# 签名 → 策略 映射的进程内缓存（文件 mtime 变化时失效重载）
_bank_lock = threading.Lock()
_bank_cache: dict[str, Any] | None = None
_bank_mtime: float = 0.0

# ─── 策略有效性加权（outcome 成功率消费，ESDA Phase 1）────────────────────
# 在 select_strategy 的三级匹配结果上叠加 outcome 成功率加权：
# 同签名下多个候选策略条目时，优先选择历史成功率更高的策略。
# 保守口径：无 outcome 数据时（首次运行 / outcome 为空）权重全 1.0，
# 匹配优先级不变（历史口径逐样本等价）；outcomes 存在时按
# success_rate = success_count / total_count 加权（无 outcome 记录的
# 策略条目权重 1.0 不惩罚，避免冷启动偏差）。


def _strategy_success_rate(bank: dict[str, Any]) -> dict[str, float]:
    """聚合 outcomes 统计，返回策略名 → 成功率映射（纯数据，零 LLM 成本）。

    Args:
        bank: 已加载的策略库字典（含 strategies / outcomes 字段）。

    Returns:
        {策略名: 成功率}（无 outcome 记录的策略名不出现，调用方用 .get 1.0 兜底）。
    """
    outcomes: list[dict[str, Any]] = bank.get("outcomes") or []
    stats: dict[str, dict[str, int]] = {}
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        name = str(o.get("strategy") or "").strip()
        if not name:
            continue
        s = stats.setdefault(name, {"total": 0, "success": 0})
        s["total"] += 1
        if o.get("success"):
            s["success"] += 1
    return {name: (st["success"] / st["total"] if st["total"] > 0 else 1.0) for name, st in stats.items()}


def _rank_strategy_entries(
    candidates: list[dict[str, Any]],
    success_rates: dict[str, float],
) -> list[dict[str, Any]]:
    """按历史成功率对候选策略条目排序（同成功率时保持原始顺序，稳定 tie-break）。

    Args:
        candidates: 匹配命中的策略条目列表（来自三级匹配，最多 3 条）。
        success_rates: 策略名 → 成功率映射（.get(name, 1.0) 兜底）。

    Returns:
        排序后的条目列表（成功率降序；无 outcome 数据的条目权重 1.0 排前）。
    """
    if len(candidates) <= 1:
        return list(candidates)
    return sorted(candidates, key=lambda e: success_rates.get(str(e.get("strategy") or ""), 1.0), reverse=True)


def strategy_bank_enabled() -> bool:
    """策略银行开关（STRATEGY_BANK_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("STRATEGY_BANK_ENABLE", "false").lower() == "true"


def _bank_path() -> str:
    """策略库文件路径（支持 STRATEGY_BANK_PATH 环境变量覆盖，便于测试隔离）。"""
    return os.environ.get("STRATEGY_BANK_PATH", _DEFAULT_BANK_PATH)


def _load_bank(path: str | None = None) -> dict[str, Any]:
    """加载策略库 JSON（缺失 / 损坏时返回空库，保守降级，不阻断修复）。"""
    global _bank_cache, _bank_mtime
    bank_file = path or _bank_path()
    with _bank_lock:
        try:
            mtime = os.path.getmtime(bank_file)
            if _bank_cache is not None and mtime == _bank_mtime:
                return _bank_cache
            with open(bank_file, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {"strategies": []}
            _bank_cache = data
            _bank_mtime = mtime
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("策略库加载失败（降级为空库，不阻断修复）: %s", e)
            return {"strategies": []}


def _make_signature(
    error_category: str,
    fix_strategy_tag: str | None = None,
    cross_file: bool = False,
) -> tuple[str, str | None, bool]:
    """把三元组归一为失败签名（error_category 小写，None 归一为 "unknown"）。"""
    return (error_category.strip().lower() or "unknown", (fix_strategy_tag or "").strip().lower() or None, cross_file)


def select_strategy(
    error_category: str,
    fix_strategy_tag: str | None = None,
    cross_file: bool = False,
    budget_hint: str | None = None,
    path: str | None = None,
) -> dict[str, Any] | None:
    """按失败签名检索策略银行，返回最匹配的策略条目（无匹配时 None）。

    匹配优先级（保守口径，命中即返回）：
    1. 精确匹配：(error_category, fix_strategy_tag, cross_file) 三元组全命中；
    2. 次级匹配：(error_category, cross_file) 二元组命中（fix_strategy_tag 通配）；
    3. 末级匹配：仅 error_category 命中（cross_file / tag 通配）；
    4. 预算约束：若指定 budget_hint（"low"|"medium"|"high"），仅返回
       strategy["budget"] 与 budget_hint 匹配的条目（无预算标签的条目通配）。

    策略有效性加权（ESDA Phase 1）：
    三级匹配命中的候选条目若有多条（同签名下多个策略变体），
    按 outcomes 聚合的历史成功率加权排序，返回成功率最高者。
    无 outcome 数据时（首次运行 / 冷启动）权重全 1.0，匹配优先级不变
    （历史口径逐样本等价）。

    Args:
        error_category: 当前任务的错误类别（assertion / runtime / syntax / ...）。
        fix_strategy_tag: 修复策略标签（来自 state["fix_strategy_tag"]，可选）。
        cross_file: 是否跨文件修复任务（CROSS_FILE_ENABLE=true 时 True）。
        budget_hint: 预算档位（可选，"low"|"medium"|"high"）。
        path: 策略库文件路径（None 时读 STRATEGY_BANK_PATH / 默认路径）。

    Returns:
        策略条目字典（含 strategy / prompt_hint / budget 字段）；无匹配时 None。
    """
    bank = _load_bank(path)
    strategies: list[dict[str, Any]] = bank.get("strategies", [])
    if not strategies:
        return None
    sig = _make_signature(error_category, fix_strategy_tag, cross_file)
    exact_matches: list[dict[str, Any]] = []
    partial_matches: list[dict[str, Any]] = []
    category_matches: list[dict[str, Any]] = []
    for entry in strategies:
        if not isinstance(entry, dict):
            continue
        entry_cat = str(entry.get("error_category", "")).lower()
        entry_tag = str(entry.get("fix_strategy_tag", "") or "").lower() or None
        entry_cross = bool(entry.get("cross_file", False))
        _budget_ok = entry.get("budget") in (None, "any", budget_hint) if budget_hint else True
        if not _budget_ok:
            continue
        # 1. 精确匹配（收集全部命中，非首个）
        if entry_cat == sig[0] and entry_tag == sig[1] and entry_cross == sig[2]:
            exact_matches.append(entry)
        # 2. 次级匹配（tag 通配）
        elif entry_cat == sig[0] and entry_cross == sig[2]:
            partial_matches.append(entry)
        # 3. 末级匹配（仅 category 通配）
        elif entry_cat == sig[0]:
            category_matches.append(entry)
    # 按匹配级别选择候选集（精确 > 次级 > 末级），再按成功率加权排序
    candidates = exact_matches or partial_matches or category_matches
    if not candidates:
        return None
    success_rates = _strategy_success_rate(bank)
    ranked = _rank_strategy_entries(candidates, success_rates)
    return ranked[0] if ranked else None


def record_strategy_outcome(
    signature: tuple[str, str | None, bool],
    strategy: str,
    success: bool,
    task_id: str = "",
    path: str | None = None,
) -> None:
    """把一次修复的 (签名, 策略, 是否成功) 追加到策略库 JSON（离线积累侧）。

    纯追加（不改写已有条目）：策略库是"策略有效性统计"的积累表，
    离线分析（analyze_failures.py 同口径）负责挖掘高频有效策略并
    人工审核后更新 source of truth。本函数只做"在线观测层"的记录，
    不影响在线消费侧（select_strategy 读的是同一文件的 strategies 字段，
    本函数追加的是 outcomes 字段，二者不交叉）。

    写盘失败静默降级（纯观测层，不阻断修复主流程）。
    """
    bank_file = path or _bank_path()
    try:
        os.makedirs(os.path.dirname(bank_file) or ".", exist_ok=True)
        data: dict[str, Any] = {"strategies": [], "outcomes": []}
        if os.path.isfile(bank_file):
            with open(bank_file, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        entry = {
            "error_category": signature[0],
            "fix_strategy_tag": signature[1],
            "cross_file": signature[2],
            "strategy": strategy,
            "success": success,
            "task_id": task_id,
        }
        data.setdefault("outcomes", []).append(entry)
        with open(bank_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.debug("策略库 outcome 记录写盘失败（忽略，纯观测层）: %s", e)


def strategy_bank_stats(path: str | None = None) -> dict[str, Any]:
    """策略库观测统计（供 get_workflow_stats 消费，纯读操作）。"""
    bank = _load_bank(path)
    strategies: list[dict[str, Any]] = bank.get("strategies", [])
    outcomes: list[dict[str, Any]] = bank.get("outcomes", [])
    success_count = sum(1 for o in outcomes if isinstance(o, dict) and o.get("success"))
    return {
        "enabled": strategy_bank_enabled(),
        "strategy_count": len(strategies),
        "outcome_count": len(outcomes),
        "success_rate": (success_count / len(outcomes)) if outcomes else 0.0,
    }


__all__ = [
    "record_strategy_outcome",
    "select_strategy",
    "strategy_bank_enabled",
    "strategy_bank_stats",
]
