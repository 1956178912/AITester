"""
G2 风险分级人工回路（Risk Approval，默认关）。

背景（gap_report 2026-09-28 P0 缺口 G2）：
    当前仓库已有三组可直接消费的信号——错误分类置信度
    （error_classifier.classify_with_confidence）、补丁影响面
    （patch_applier / cross_file 的变更行数、文件数、契约结果）与任务级预算
    （cost_budget.get_budget_stats）——但缺少一个独立的“风险分级”模块，
    无法把“低风险自动合入 / 中风险人工确认 / 高风险强制审查”落成结构化
    可消费的输出。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `RISK_APPROVAL_ENABLE=false`（默认）时本模块零行为变化：
      工作流主拓扑零改动，benchmark / CLI 仅在显式开启时写入风险分级字段；
    - 风险打分是**纯静态、零 LLM 成本**的三因子加权模型：
      1) 错误置信度因子（confidence 越低，风险越高）；
      2) 补丁影响面因子（变更行数 / 文件数 / 契约缺失符号）；
      3) 预算消耗因子（消耗/上限比例，未配置预算时按 0 处理）；
    - 分级输出：`low` / `medium` / `high`；审批动作：
      `low` → `auto_merge`，`medium` → `human_confirm`，`high` → `force_review`。
    - 默认阈值与权重均可经环境变量覆盖，但默认值刻意保守（中/高阈值偏严，
      避免“低风险自动合入”误放行高影响面补丁）。

使用方式（benchmark / CLI 消费）：
    from src.graph.risk_approval import risk_approval_enabled, assess_task_risk

    if risk_approval_enabled():
        result = assess_task_risk(
            confidence=0.3,
            changed_lines=220,
            changed_files=3,
            contract_missing_symbols=["Rule_L101"],
            budget_ratio=0.9,
        )
        # result["risk_level"] / result["approval_action"] / result["risk_score"]
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── 默认参数（保守口径；环境变量覆盖）──────────────────────────────────────
_DEFAULT_WEIGHTS: dict[str, float] = {"confidence": 0.4, "impact": 0.4, "budget": 0.2}
_DEFAULT_THRESHOLDS: dict[str, float] = {"medium": 0.35, "high": 0.65}
# 影响面因子的保守映射：small / medium / large 三级
_SMALL_CHANGED_LINES = 30
_MEDIUM_CHANGED_LINES = 120
_SMALL_CHANGED_FILES = 1
_MEDIUM_CHANGED_FILES = 2


def risk_approval_enabled() -> bool:
    """风险分级人工回路开关（RISK_APPROVAL_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("RISK_APPROVAL_ENABLE", "false").lower() == "true"


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """读取环境变量浮点值（解析失败时回退默认值，并夹在 [minimum, maximum]）。"""
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """读取环境变量整数值（解析失败时回退默认值，并夹在 [minimum, maximum]）。"""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


@dataclass
class RiskAssessment:
    """风险分级结果（纯数据，供 JSON / 报告 / 人工回路消费）。

    属性:
        risk_score: 0.0-1.0 的归一化风险分（越高越危险）。
        risk_level: low / medium / high。
        approval_action: auto_merge / human_confirm / force_review。
        factors: 三因子明细（confidence / impact / budget 各自归一化分数）。
        reasons: 可读的原因说明列表（供报告输出）。
    """

    risk_score: float
    risk_level: str
    approval_action: str
    factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转 dict（JSON 可序列化）。"""
        return {
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level,
            "approval_action": self.approval_action,
            "factors": self.factors,
            "reasons": self.reasons,
        }


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """夹取到 [minimum, maximum]（保守：越界时不报错，直接截断）。"""
    return max(minimum, min(maximum, value))


def _confidence_factor(confidence: float | None) -> tuple[float, str]:
    """错误置信度因子：confidence 越低，风险越高（1 - confidence）。"""
    if confidence is None:
        return 1.0, "no_confidence: 无置信度信号，按保守高风险处理"
    conf = _clamp(float(confidence))
    factor = 1.0 - conf
    if factor >= 0.5:
        reason = f"low_confidence({conf:.2f}): 分类置信度低"
    elif factor >= 0.2:
        reason = f"medium_confidence({conf:.2f}): 分类置信度中等"
    else:
        reason = f"high_confidence({conf:.2f}): 分类置信度较高"
    return factor, reason


def _impact_factor(
    changed_lines: int | None,
    changed_files: int | None,
    contract_missing_symbols: list[str] | None,
    full_file_patch: bool | None = None,
) -> tuple[float, str]:
    """补丁影响面因子：行数 / 文件数 / 契约破坏 / 全文件替换。

    保守口径：任一强信号（契约缺失符号、全文件替换）直接顶到 0.9；
    行数与文件数按分段线性打分（small=0.2 / medium=0.5 / large=0.8）。
    """
    lines = int(changed_lines or 0)
    files = int(changed_files or 0)
    missing = [s for s in (contract_missing_symbols or []) if str(s).strip()]

    if lines <= _SMALL_CHANGED_LINES and files <= _SMALL_CHANGED_FILES:
        base = 0.2
    elif lines <= _MEDIUM_CHANGED_LINES and files <= _MEDIUM_CHANGED_FILES:
        base = 0.5
    else:
        base = 0.8

    reasons: list[str] = []
    factor = base
    if missing:
        factor = max(factor, 0.9)
        reasons.append(f"contract_missing({len(missing)}): 命名契约缺失符号")
    if full_file_patch:
        factor = max(factor, 0.9)
        reasons.append("full_file_patch: 全文件替换路径")
    if lines > _MEDIUM_CHANGED_LINES or files > _MEDIUM_CHANGED_FILES:
        reasons.append(f"large_impact(lines={lines},files={files})")
    elif lines > _SMALL_CHANGED_LINES or files > _SMALL_CHANGED_FILES:
        reasons.append(f"medium_impact(lines={lines},files={files})")
    else:
        reasons.append(f"small_impact(lines={lines},files={files})")
    return _clamp(factor), "; ".join(reasons)


def _budget_factor(budget_ratio: float | None, budget_exceeded: bool | None = None) -> tuple[float, str]:
    """预算消耗因子：ratio=consumed/limit（未配置预算时传 None → 0）。"""
    if budget_exceeded is True:
        return 1.0, "budget_exceeded: 预算已超限"
    if budget_ratio is None:
        return 0.0, "budget_unconfigured: 未启用预算，因子为 0"
    ratio = _clamp(float(budget_ratio))
    if ratio >= 0.9:
        return 1.0, f"budget_high({ratio:.2f})"
    if ratio >= 0.6:
        return 0.7, f"budget_medium({ratio:.2f})"
    return 0.3 if ratio >= 0.3 else 0.1, f"budget_low({ratio:.2f})"


def assess_task_risk(
    confidence: float | None = None,
    changed_lines: int | None = None,
    changed_files: int | None = None,
    contract_missing_symbols: list[str] | None = None,
    full_file_patch: bool | None = None,
    budget_ratio: float | None = None,
    budget_exceeded: bool | None = None,
) -> RiskAssessment:
    """按三因子加权模型评估单任务风险（纯数据，零 LLM 成本）。

    Args:
        confidence: 错误分类置信度（0-1，None 表示无信号，按保守 1.0 风险处理）。
        changed_lines: 补丁变更行数（None 按 0）。
        changed_files: 补丁变更文件数（None 按 1）。
        contract_missing_symbols: 命名契约缺失符号列表（非空即强风险信号）。
        full_file_patch: 是否走全文件替换路径（True 即强风险信号）。
        budget_ratio: 预算消耗比例（consumed/limit，None 表示未配置预算）。
        budget_exceeded: 是否已触发预算超限（True 时预算因子直接顶格）。

    Returns:
        RiskAssessment（risk_score / risk_level / approval_action / factors / reasons）。
    """
    weight_conf = _env_float("RISK_WEIGHT_CONFIDENCE", _DEFAULT_WEIGHTS["confidence"], 0.0, 1.0)
    weight_impact = _env_float("RISK_WEIGHT_IMPACT", _DEFAULT_WEIGHTS["impact"], 0.0, 1.0)
    weight_budget = _env_float("RISK_WEIGHT_BUDGET", _DEFAULT_WEIGHTS["budget"], 0.0, 1.0)
    total_weight = weight_conf + weight_impact + weight_budget
    if total_weight <= 0:
        total_weight = 1.0
        weight_conf = weight_impact = weight_budget = 1.0 / 3.0

    medium_threshold = _env_float("RISK_THRESHOLD_MEDIUM", _DEFAULT_THRESHOLDS["medium"], 0.0, 1.0)
    high_threshold = _env_float("RISK_THRESHOLD_HIGH", _DEFAULT_THRESHOLDS["high"], 0.0, 1.0)

    conf_score, conf_reason = _confidence_factor(confidence)
    impact_score, impact_reason = _impact_factor(
        changed_lines, changed_files, contract_missing_symbols, full_file_patch
    )
    budget_score, budget_reason = _budget_factor(budget_ratio, budget_exceeded)

    risk_score = (weight_conf * conf_score + weight_impact * impact_score + weight_budget * budget_score) / total_weight
    risk_score = round(_clamp(risk_score), 4)

    if risk_score >= high_threshold:
        risk_level = "high"
        approval_action = "force_review"
    elif risk_score >= medium_threshold:
        risk_level = "medium"
        approval_action = "human_confirm"
    else:
        risk_level = "low"
        approval_action = "auto_merge"

    reasons = [conf_reason, impact_reason, budget_reason]
    logger.info(
        "G2 风险分级：level=%s action=%s score=%.3f (conf=%.2f impact=%.2f budget=%.2f)",
        risk_level,
        approval_action,
        risk_score,
        conf_score,
        impact_score,
        budget_score,
    )
    return RiskAssessment(
        risk_score=risk_score,
        risk_level=risk_level,
        approval_action=approval_action,
        factors={"confidence": conf_score, "impact": impact_score, "budget": budget_score},
        reasons=reasons,
    )


def build_risk_summary(
    confidence: float | None,
    changed_lines: int | None,
    changed_files: int | None,
    contract_missing_symbols: list[str] | None,
    full_file_patch: bool | None,
    budget_ratio: float | None,
    budget_exceeded: bool | None,
) -> dict[str, Any]:
    """构建 benchmark 结果行可直接 JSON 序列化的风险摘要 dict。

    设计目标：
        - 单任务结果行新增 `risk_summary` 字段时，调用方只需用本函数一行生成；
        - 默认关时调用方通常不会调用本函数，避免历史口径变化。

    Returns:
        可直接嵌入 JSON 的 dict（包含 enabled=False 占位，保持键集合同构）。
    """
    enabled = risk_approval_enabled()
    if not enabled:
        return {
            "enabled": False,
            "risk_score": None,
            "risk_level": None,
            "approval_action": None,
            "factors": {},
            "reasons": [],
        }
    result = assess_task_risk(
        confidence=confidence,
        changed_lines=changed_lines,
        changed_files=changed_files,
        contract_missing_symbols=contract_missing_symbols,
        full_file_patch=full_file_patch,
        budget_ratio=budget_ratio,
        budget_exceeded=budget_exceeded,
    )
    return {"enabled": True, **result.to_dict()}


__all__ = [
    "RiskAssessment",
    "assess_task_risk",
    "build_risk_summary",
    "risk_approval_enabled",
]
