"""执行反馈轨迹 + 奖励信号 + 迭代策略（S7 拆分自 nodes.py，2026-10-08 R3）。

从 `src/graph/nodes.py` 拆出的 trace/reward 簇：这 6 个纯函数（观测层轨迹追加、
多维奖励信号、动态迭代策略建议与温度映射）内聚且无模块级状态——不依赖
nodes.py 的 agent 实例缓存 / 硬错误类别常量 / executor 缓存，仅依赖
`config`（EXECUTION_TIMEOUT / TEMPERATURE）与 `src.graph.state`（AITesterState），
故可安全独立成模块。nodes.py 通过 `from .trace_reward import ...` re-export，
保持 `from src.graph.nodes import _record_execution_trace` 等历史导入路径逐字节不变
（workflow.py 的 re-export 与全部测试导入路径零改动）。
"""

from __future__ import annotations

import logging
from typing import Any

from config import EXECUTION_TIMEOUT, TEMPERATURE
from src.graph.state import AITesterState

logger = logging.getLogger(__name__)


def _record_execution_trace(
    state: AITesterState,
    passed: bool,
    coverage: float,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """3.2 执行反馈轨迹：把本次 Executor 执行追加到 state["execution_trace"]。

    轨迹为纯观测层（默认常开）：每次执行记录"通过/失败、相对上一轮的
    覆盖率变化、墙钟耗时"与保守线性归一的多维奖励信号
    （correctness / efficiency / simplicity），供未来执行反馈驱动的微调
    备料。轨迹不参与工作流路由决策，写入失败不阻断主流程（观测层
    失败不应改变被测系统行为，口径与 tracing 一致）。

    Args:
        state: 当前状态（已含上一轮 execution_trace 前缀）。
        passed: 本次测试是否通过。
        coverage: 本次覆盖率百分比（0-100，未测得时 0.0）。
        elapsed_seconds: 本次 Executor 节点墙钟耗时（秒）。

    Returns:
        追加本次记录后的完整 execution_trace 列表。
    """
    # 上一轮覆盖率从入参轨迹前缀读取（首轮为 None，与调用方口径一致）；
    # 调用方 _executor_node 已用同一公式计算过覆盖变化，此处仅服务
    # 追加的轨迹记录，避免重复全轨迹扫描
    trace = list(state.get("execution_trace") or [])
    prev_coverage = trace[-1].get("coverage") if trace else None
    coverage_delta = round(coverage - prev_coverage, 2) if prev_coverage is not None else None

    # 3.2 改进：基于历史轨迹的动态迭代策略调整——根据前几轮的
    # 覆盖率变化趋势，动态建议后续迭代的 temperature 或提示策略。
    # 保守口径：仅输出"建议"到 state["iteration_strategy_suggestion"]，
    # 不直接改变 LLM 调用参数（温度调整需经 BaseAgent 消费，此处只做观测层建议）。
    # 若前 2 轮覆盖率持续下降（delta < 0 两次），建议"降低 temperature
    # + 收紧提示"（当前路径过于发散）；若覆盖率停滞（delta ≈ 0 两次），
    # 建议"切换修复视角"（如从最小改动切到根因修复）
    # 注意：本函数只负责"追加轨迹"，保持返回轨迹列表的历史口径；
    # 策略建议由调用方（_executor_node）单独经 _suggest_iteration_strategy 计算
    # 并写入 state["iteration_strategy_suggestion"]（观测层，不参与路由）
    return _append_trace_record(
        state,
        trace,
        passed=passed,
        coverage=coverage,
        coverage_delta=coverage_delta,
        elapsed_seconds=elapsed_seconds,
    )


def _patch_line_delta_for_reward(state: AITesterState) -> int | None:
    """P2-5：估算本轮补丁的行数变化（|补丁后 − 原代码|，None = 无法度量）。

    信号源：state["last_applied_repair"]["original_code"]（patch_applier
    写盘成功时的原文暂存）与 state["target_code"]（executor 本轮实测的
    补丁后代码）。两者齐备时行数差即补丁体量；任一缺失（无补丁轮 /
    写盘被拒）返回 None（simplicity 保守记 0）。
    """
    last_repair = state.get("last_applied_repair") or {}
    original_code = last_repair.get("original_code")
    current_code = state.get("target_code")
    if not original_code or not current_code:
        return None
    return abs(len(str(current_code).splitlines()) - len(str(original_code).splitlines()))


def _append_trace_record(
    state: AITesterState,
    trace: list[dict[str, Any]],
    passed: bool,
    coverage: float,
    coverage_delta: float | None,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """把本次执行记录追加到轨迹列表（3.2 观测层，写入失败不阻断主流程）。"""
    reward_signals = _compute_reward_signals(
        passed,
        coverage_delta,
        elapsed_seconds,
        patch_line_delta=_patch_line_delta_for_reward(state),
    )
    trace.append(
        {
            "iteration": state.get("iteration", 0),
            "passed": passed,
            "coverage": coverage,
            "coverage_delta": coverage_delta,
            "elapsed_seconds": elapsed_seconds,
            "reward_signals": reward_signals,
        }
    )
    return trace


def _compute_reward_signals(
    passed: bool,
    coverage_delta: float | None,
    elapsed_seconds: float,
    patch_line_delta: int | None = None,
) -> dict[str, float]:
    """计算多维度奖励信号（3.2 保守线性归一，供执行反馈 RL 备料）。

    Args:
        passed: 测试是否通过。
        coverage_delta: 相对上一轮覆盖率变化（首轮为 None）。
        elapsed_seconds: 本次执行耗时（秒）。
        patch_line_delta: 本轮补丁的行数变化（|补丁后行数 − 原代码行数|，
            P2-5 注入；None = 无补丁来源，无法度量）。

    Returns:
        {"correctness": 0.0-1.0, "efficiency": 0.0-1.0,
         "simplicity": 0.0-1.0} 的保守归一奖励信号。

    P2-5（2026-10-05 独立审查）：simplicity 此前与 efficiency 同源（都是
    elapsed 线性归一，仅分母 ×2）——"简单性"名不副实，作为 RL 备料会引入
    系统性噪声。现改为真实的补丁简洁度度量：|行数变化| 越小信号越高
    （线性归一，30 行饱和为 0——BOOSTAPR 式最小改动偏好的信号化）；
    None（无补丁/无来源）保守记 0.0（不奖励无法度量的维度）。
    """
    correctness = 1.0 if passed else 0.0
    # efficiency 沿用历史口径（基于 EXECUTION_TIMEOUT 的线性归一）
    efficiency = max(0.0, round(1.0 - elapsed_seconds / EXECUTION_TIMEOUT, 3))
    simplicity = 0.0 if patch_line_delta is None else max(0.0, round(1.0 - abs(patch_line_delta) / 30.0, 3))
    return {
        "correctness": round(correctness, 4),
        "efficiency": efficiency,
        "simplicity": simplicity,
    }


def _suggest_iteration_strategy(trace: list[dict[str, Any]], coverage_delta: float | None) -> str | None:
    """3.2 改进：基于历史轨迹动态调整后续迭代策略（纯观测层建议）。

    Args:
        trace: 完整执行轨迹（含本次，已追加）。
        coverage_delta: 本次覆盖率变化。

    Returns:
        策略建议字符串（None 表示无需调整，保持默认）：
        - "lower_temperature": 前 2 轮覆盖率持续下降，建议降低温度收紧提示；
        - "switch_repair_view": 覆盖率停滞 2 轮，建议切换修复视角；
        - "keep": 无需调整。
    """
    if len(trace) < 2:
        return None  # 首轮无历史，不调整
    # 覆盖率 delta 过滤 None 后按 float 归一（trace 中 coverage_delta 可能缺失/非数值）
    # 2026-09-26 round10 P1：非数值 delta（"n/a"/dict 等历史落盘异常值）float()
    # 抛 ValueError 使 executor 节点崩溃 → try/except 跳过该条目（口径：非数值
    # delta 视为无信号，与 None 同语义），默认数值路径零变化
    recent_deltas: list[float] = []
    for t in trace[-3:-1]:
        val = t.get("coverage_delta")
        if val is None:
            continue
        try:
            recent_deltas.append(float(val))
        except (TypeError, ValueError):
            continue
    if not recent_deltas:
        return None
    declining = all(d < 0 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    stagnant = all(abs(d) < 0.5 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    if declining:
        return "lower_temperature"
    if stagnant:
        return "switch_repair_view"
    return None


def _dynamic_temperature_from_suggestion(suggestion: str | None) -> float | None:
    """3.3 改进：把迭代策略建议映射为动态 temperature（真正接线，非观测层）。

    此前 iteration_strategy_suggestion 仅记录不改变路由（观测层）。本函数
    把建议映射为实际采样温度，供 Generator / Debugger 节点在 LLM 调用时
    透传覆盖（_call_llm_with_cache 的 temperature 参数）：

    - "lower_temperature"：覆盖率连降 → 温度减半（下限 0.0），收紧采样发散；
    - 其他建议 / None：不覆盖（返回 None，沿用 config.TEMPERATURE）。

    Args:
        suggestion: executor 节点写入的迭代策略建议字符串。

    Returns:
        覆盖后的温度（None 表示不覆盖，沿用默认）。
    """
    if suggestion == "lower_temperature":
        # TEMPERATURE=0 时减半仍为 0（无收紧空间）→ 返回 None 沿用默认，
        # 避免"覆盖为 0.0"的无意义透传（2026-09-26 全面审查修复）
        if TEMPERATURE <= 0.0:
            logger.info("动态策略（3.3）：TEMPERATURE 已为 0，无可收紧空间，不覆盖")
            return None
        lowered = round(max(0.0, TEMPERATURE * 0.5), 3)
        logger.info("动态策略（3.3）：覆盖率连降，temperature %.2f → %.2f", TEMPERATURE, lowered)
        return lowered
    return None


__all__ = [
    "_append_trace_record",
    "_compute_reward_signals",
    "_dynamic_temperature_from_suggestion",
    "_patch_line_delta_for_reward",
    "_record_execution_trace",
    "_suggest_iteration_strategy",
]
