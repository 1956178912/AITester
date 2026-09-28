"""
ANNEAL-lite：故障频率驱动的修复策略切换（默认关）。

背景（P1 闭环进化 + 神经符号融合方向）：
    当前 DebuggerAgent 对同一类故障在 N 轮迭代中反复使用相同策略
    （"每次都从头来"），缺乏对"为什么会反复失败"的结构性响应。
    ANNEAL（Neural-Symbolic Program Repair）的核心洞察是：当 Agent
    反复在同一类故障上失败时，不应修改模型权重，而是**切换符号组件**——
    将当前策略升级为更强工具（如 ASSERTION 高频 → 先跑 oracle_enhancer
    再修复；RUNTIME 高频 → 强制启用 runtime_probe 捕获变量快照）。

    本模块提供 ANNEAL-lite 的最小落地（保守、零 LLM 成本）：
    1. 故障频率计数器：从 repair_history 统计同一 (error_category,
       target_module) 在近期迭代中的出现频次；
    2. 策略切换规则表：高频故障（≥ K 次）触发"强化策略"映射
       （符号组件 = 策略映射表，非模型权重）；
    3. 确定性回滚：开关关闭 / 频次不足时返回 None，策略映射表
       回退默认口径（历史行为逐字节不变）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `FAILURE_FREQUENCY_ENABLE=false`（默认）时，本模块零行为变化；
    - 开关开启后，仅当同一 (error_category, target_module) 在
      repair_history 中出现 ≥ N 次（N 由 FAILURE_FREQUENCY_THRESHOLD 控制，
      默认 2）时触发策略切换；
    - 策略切换是**配置级**（修改策略映射表条目），非代码修改，
      确定性可回滚（恢复默认映射表）；
    - 高频故障的"强化策略"是纯文本提示（注入 Debugger prompt 尾部），
      零额外 LLM 调用成本。

使用方式（_debugger_node 集成）：
    from src.tools.failure_frequency import (
        failure_frequency_enabled,
        detect_high_frequency_failure,
        get_escalated_strategy_hint,
    )

    if failure_frequency_enabled():
        sig = detect_high_frequency_failure(state["repair_history"], state.get("error_category"), state.get("module_name"))
        if sig:
            hint = get_escalated_strategy_hint(sig)
            if hint:
                query += "\n\n" + hint
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 默认故障频率阈值（同一 error_category 在 repair_history 中出现 ≥ N 次时触发）
_DEFAULT_THRESHOLD = 2


def failure_frequency_enabled() -> bool:
    """故障频率策略切换开关（FAILURE_FREQUENCY_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("FAILURE_FREQUENCY_ENABLE", "false").lower() == "true"


def _failure_frequency_threshold() -> int:
    """故障频率阈值（FAILURE_FREQUENCY_THRESHOLD，默认 2；≤1 视为 2）。"""
    try:
        n = int(os.getenv("FAILURE_FREQUENCY_THRESHOLD", str(_DEFAULT_THRESHOLD)))
    except ValueError:
        n = _DEFAULT_THRESHOLD
    return max(2, n)


def _recent_window() -> int:
    """统计窗口（REPAIR_HISTORY_WINDOW，默认 5 = 最近 5 轮修复历史）。

    保守口径：窗口过大会让"很久以前的高频故障"污染当前策略；
    过小则信号不足。默认 5 与 _MAX_REPAIR_HISTORY 同口径。
    """
    try:
        n = int(os.getenv("REPAIR_HISTORY_WINDOW", "5"))
    except ValueError:
        n = 5
    return max(2, min(n, 10))


def detect_high_frequency_failure(
    repair_history: list[dict[str, Any]] | None,
    current_category: str | None,
    target_module: str | None = None,
) -> dict[str, Any] | None:
    """检测当前故障类别是否在近期迭代中反复出现（高频故障判定）。

    统计口径（保守、纯数据，零 LLM 成本）：
    - 取 repair_history 最近 _recent_window() 轮；
    - 按 error_category 统计出现频次（target_module 非 None 时按
      (error_category, target_module) 联合统计）；
    - 当前 error_category 频次 ≥ 阈值时返回高频故障信号；
    - 否则返回 None（不触发策略切换，历史口径不变）。

    Args:
        repair_history: PatchApplier 累计的修复历史（每轮含
            iteration / error_category / patch_applied 等字段）。
        current_category: 当前任务的错误类别（str，如 "assertion"）。
        target_module: 被测模块名（可选，提供时按 (category, module) 联合统计）。

    Returns:
        高频故障信号字典 {"category", "module", "count", "threshold"}；
        非高频时返回 None。
    """
    if not repair_history or not current_category:
        return None
    threshold = _failure_frequency_threshold()
    window = _recent_window()
    recent = repair_history[-window:]
    cat = current_category.strip().lower()
    mod = target_module.strip().lower() if target_module else None

    count = 0
    for h in recent:
        h_cat = str(h.get("error_category", "")).strip().lower()
        if h_cat != cat:
            continue
        if mod:
            h_mod = str(h.get("module_name") or h.get("target_module") or "").strip().lower()
            if h_mod and h_mod != mod:
                continue
        count += 1

    if count < threshold:
        return None
    return {
        "category": cat,
        "module": mod,
        "count": count,
        "threshold": threshold,
    }


# 高频故障 → 强化策略映射表（符号组件：可确定性回滚的配置级映射）
# 每条映射：{"category": 故障类别, "hint": 注入 prompt 的强化提示文本,
#             "tool": 建议启用的工具（观测层，不自动开关其他模块）}
_ESCALATED_STRATEGY_MAP: list[dict[str, str]] = [
    {
        "category": "assertion",
        "hint": (
            "【高频故障强化（ANNEAL-lite）】断言失败在近 N 轮中反复出现，"
            "单纯 LLM 修复断言路径已收敛失效。请优先启用规约驱动预言增强"
            "（oracle_enhancer）重新生成断言，而非直接修改代码逻辑。"
            "若断言预期值本身错误，修正测试预期值而非修改被测代码。"
        ),
        "tool": "oracle_enhancer",
    },
    {
        "category": "runtime",
        "hint": (
            "【高频故障强化（ANNEAL-lite）】运行时异常在近 N 轮中反复出现，"
            "静态 traceback 分析已收敛失效。请优先捕获运行时变量快照"
            "（runtime_probe）辅助定位根因，而非仅依赖异常栈文本推理。"
        ),
        "tool": "runtime_probe",
    },
    {
        "category": "index_error",
        "hint": (
            "【高频故障强化（ANNEAL-lite）】索引越界在近 N 轮中反复出现，"
            "说明边界检查修复未生效。请系统性地检查所有循环/切片/下标"
            "访问的边界条件（空容器、负数索引、越界偏移），而非仅修复"
            "触发异常的那一行。"
        ),
        "tool": "boundary_audit",
    },
    {
        "category": "type_error",
        "hint": (
            "【高频故障强化（ANNEAL-lite）】类型错误在近 N 轮中反复出现，"
            "说明类型对齐修复未收敛。请核对所有函数调用的参数类型与"
            "返回值类型（使用静态类型检查 mypy 层），而非仅修复触发"
            "TypeError 的那一行。"
        ),
        "tool": "type_repair_layer",
    },
    {
        "category": "timeout",
        "hint": (
            "【高频故障强化（ANNEAL-lite）】执行超时在近 N 轮中反复出现，"
            "说明死循环/无限递归的终止条件修复未生效。请系统性地检查"
            "所有循环的终止条件与递归的基准情形，添加明确的边界退出。"
        ),
        "tool": "termination_audit",
    },
]

# 类别 → 强化策略映射（查表用）
_ESCALATED_BY_CATEGORY: dict[str, dict[str, str]] = {e["category"]: e for e in _ESCALATED_STRATEGY_MAP}


def get_escalated_strategy_hint(signal: dict[str, Any] | None) -> str | None:
    """根据高频故障信号获取强化策略提示文本（注入 Debugger prompt 尾部）。

    Args:
        signal: detect_high_frequency_failure 返回的信号字典；None 时返回 None。

    Returns:
        强化策略提示文本（非空字符串）；无匹配策略 / signal 为 None 时返回 None。
    """
    if not signal:
        return None
    cat = str(signal.get("category", "")).strip().lower()
    entry = _ESCALATED_BY_CATEGORY.get(cat)
    if not entry:
        return None
    count = int(signal.get("count", 0))
    threshold = int(signal.get("threshold", 2))
    # 把提示中的 "N 轮" 占位替换为实际频次
    return entry["hint"].replace("近 N 轮", f"近 {count} 轮（阈值 {threshold}）")


def get_escalated_strategy_tool(signal: dict[str, Any] | None) -> str | None:
    """根据高频故障信号获取建议启用的工具名（观测层，不自动开关其他模块）。

    Args:
        signal: detect_high_frequency_failure 返回的信号字典；None 时返回 None。

    Returns:
        建议工具名（如 "oracle_enhancer" / "runtime_probe"）；无匹配时 None。
    """
    if not signal:
        return None
    cat = str(signal.get("category", "")).strip().lower()
    entry = _ESCALATED_BY_CATEGORY.get(cat)
    return entry.get("tool") if entry else None


def failure_frequency_stats() -> dict[str, Any]:
    """故障频率策略切换的观测统计（供 get_workflow_stats 消费，纯读操作）。"""
    return {
        "enabled": failure_frequency_enabled(),
        "threshold": _failure_frequency_threshold(),
        "recent_window": _recent_window(),
        "escalated_categories": sorted(_ESCALATED_BY_CATEGORY.keys()),
    }


__all__ = [
    "detect_high_frequency_failure",
    "failure_frequency_enabled",
    "failure_frequency_stats",
    "get_escalated_strategy_hint",
    "get_escalated_strategy_tool",
]
