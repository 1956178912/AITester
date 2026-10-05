"""
G4 AgentTelemetry 故障检测基准（失败签名 → 已知模式匹配器，默认关）。

背景（gap_report 2026-09-28 P1 缺口 G4）：
    当前 trace.py 的 JSONL 已实现节点级决策记录（覆盖率 98%），
    但缺少"Agent 特有失败模式基准"——即把结构化 trace 中的失败签名
    （error_category / decision / strategy_selected / budget_remaining /
    iteration）映射到已知 Agent 失败模式（如 LLM 空响应循环、多候选
    全拒绝、预算早停、跨文件拓扑错配等），供规模化调试与周报消费。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `AGENT_TELEMETRY_ENABLE=false`（默认）时本模块零行为变化：
      纯离线匹配器，不接入工作流主链路；
    - 匹配器是**纯静态、零 LLM 成本**的"失败签名 → 已知模式"查表，
      与 strategy_bank 的签名结构同构（error_category + 状态信号），
      未来可直接喂给 strategy_bank 做策略侧挖掘；
    - 失败模式库是内置常量表（_KNOWN_FAILURE_PATTERNS），覆盖
      当前 17 类 ErrorCategory 中最具 Agent 特征的子集 + 跨节点组合
      模式（如"iteration 递增但 correctness 恒 0"= 修复不收敛）；
    - 输出为结构化 dict（模式名 / 命中次数 / 示例 task_id），供
      周报 / Markdown 渲染消费，不自动改写任何源文件。

使用方式（离线分析）：
    from src.observability.agent_telemetry import match_failure_patterns, agent_telemetry_enabled

    if agent_telemetry_enabled():
        report = match_failure_patterns(trace_records)
        # report["patterns"] = {模式名: {"count": int, "examples": [task_id, ...]}}
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ─── 已知 Agent 失败模式库（保守可解释；纯静态查表，零 LLM 成本）──────────
# 每个模式 = (pattern_name, 判定函数)；判定函数接收单条 trace 记录 dict，
# 返回 True（命中）/ False（未命中）。
# 设计口径：
#   - 单节点特征（decision / error_category / strategy_selected）；
#   - 跨节点组合特征（iteration 递增 + correctness 恒 0 + 预算超限）；
#   - 与 17 类 ErrorCategory 中最具 Agent 特征的子集对齐
#     （LLM 空响应 / JSON 解析失败 / 多候选全拒绝 / 执行轨迹丢失 /
#       预算超限 / 契约破坏 等），其余通用类（assertion / runtime）
#     由 error_category 直接命中"分类器已知类别"模式。

_FAILURE_PATTERN_NAMES: tuple[str, ...] = (
    "llm_empty_response_loop",
    "llm_json_parse_failure_loop",
    "multi_candidate_all_rejected",
    "execution_trace_missing",
    "budget_early_stop",
    "contract_break_rewrite",
    "import_break_after_rewrite",
    "repair_not_converging",
    "cross_file_topology_mismatch",
    "known_error_category_hit",
    # P2 注入扫描回归基准（2026-10 批次·续二）
    "injection_detected",
)


def agent_telemetry_enabled() -> bool:
    """AgentTelemetry 开关（AGENT_TELEMETRY_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("AGENT_TELEMETRY_ENABLE", "false").lower() == "true"


def _pattern_llm_empty_response_loop(record: dict[str, Any]) -> bool:
    """LLM 空响应循环：decision=debug + error_category=llm_empty_response。"""
    category = str(record.get("error_category", "")).lower()
    decision = str(record.get("decision", "")).lower()
    return category == "llm_empty_response" and decision in ("debug", "regenerate", "")


def _pattern_llm_json_parse_failure_loop(record: dict[str, Any]) -> bool:
    """LLM JSON 解析失败循环：decision=debug + error_category=llm_json_parse_failed。"""
    category = str(record.get("error_category", "")).lower()
    decision = str(record.get("decision", "")).lower()
    return category == "llm_json_parse_failed" and decision in ("debug", "regenerate", "")


def _pattern_multi_candidate_all_rejected(record: dict[str, Any]) -> bool:
    """多候选全拒绝：error_category=multi_candidate_all_rejected。"""
    return str(record.get("error_category", "")).lower() == "multi_candidate_all_rejected"


def _pattern_execution_trace_missing(record: dict[str, Any]) -> bool:
    """执行轨迹丢失：error_category=execution_trace_missing。"""
    return str(record.get("error_category", "")).lower() == "execution_trace_missing"


def _pattern_budget_early_stop(record: dict[str, Any]) -> bool:
    """预算早停：budget_remaining=0 或 error_category=budget_exceeded。"""
    budget_remaining = record.get("budget_remaining")
    category = str(record.get("error_category", "")).lower()
    if budget_remaining in (0, "0"):
        return True
    return category in ("budget_exceeded", "llm_budget_exceeded")


def _pattern_contract_break_rewrite(record: dict[str, Any]) -> bool:
    """契约破坏重写：contract_missing_symbols 非空。"""
    missing = record.get("contract_missing_symbols") or []
    return bool(missing)


def _pattern_import_break_after_rewrite(record: dict[str, Any]) -> bool:
    """导入破坏：error_category=import_error 且 iteration >= 1（重写后才发现）。"""
    category = str(record.get("error_category", "")).lower()
    iteration = record.get("iteration", 0)
    try:
        iteration = int(iteration)
    except (TypeError, ValueError):
        iteration = 0
    return category == "import_error" and iteration >= 1


def _pattern_repair_not_converging(record: dict[str, Any]) -> bool:
    """修复不收敛：iteration >= MAX（保守阈值 5）且 correctness=0。"""
    iteration = record.get("iteration", 0)
    try:
        iteration = int(iteration)
    except (TypeError, ValueError):
        iteration = 0
    reward_signals = record.get("reward_signals") or {}
    correctness = reward_signals.get("correctness", 0) if isinstance(reward_signals, dict) else 0
    try:
        correctness = float(correctness)
    except (TypeError, ValueError):
        correctness = 0.0
    return iteration >= 5 and correctness == 0.0


def _pattern_cross_file_topology_mismatch(record: dict[str, Any]) -> bool:
    """跨文件拓扑错配：cross_file=True 且 error_category in (import_error, syntax)。"""
    cross_file = record.get("cross_file")
    category = str(record.get("error_category", "")).lower()
    if cross_file in (True, "true", "True", 1):
        return category in ("import_error", "syntax", "type_error")
    return False


def _pattern_known_error_category_hit(record: dict[str, Any]) -> bool:
    """已知错误类别命中：error_category 非空且非 unknown / 非空串。"""
    category = str(record.get("error_category", "")).strip()
    return bool(category) and category.lower() != "unknown"


def _pattern_injection_detected(record: dict[str, Any]) -> bool:
    """P2 注入扫描回归基准联动（2026-10 批次·续二）：

    记录含 `injection_findings`（输入侧 detect_prompt_injection 命中的特征名列表，
    由 _generator_node / planner 在 prompt 构建期写入 trace）且非空 → 判命中。
    用途：把"任务文本被检出注入"作为可度量的失败模式接入 G4 周报，
    配合 experiments/injection_benchmark_samples.json 回归基准（P2 缺口
    "注入扫描无回归基准" 的观测侧落点——本模式只消费 trace 中已记的
    findings，不重跑启发式，零 LLM 成本）。
    """
    findings = record.get("injection_findings")
    return isinstance(findings, list) and len(findings) > 0


_PATTERns_detectors_alias = None  # 占位防误用（_PATTERN_DETECTORS 在下方定义）

_PATTERN_DETECTORS: dict[str, Any] = {
    "llm_empty_response_loop": _pattern_llm_empty_response_loop,
    "llm_json_parse_failure_loop": _pattern_llm_json_parse_failure_loop,
    "multi_candidate_all_rejected": _pattern_multi_candidate_all_rejected,
    "execution_trace_missing": _pattern_execution_trace_missing,
    "budget_early_stop": _pattern_budget_early_stop,
    "contract_break_rewrite": _pattern_contract_break_rewrite,
    "import_break_after_rewrite": _pattern_import_break_after_rewrite,
    "repair_not_converging": _pattern_repair_not_converging,
    "cross_file_topology_mismatch": _pattern_cross_file_topology_mismatch,
    "known_error_category_hit": _pattern_known_error_category_hit,
    # P2 注入扫描回归基准（2026-10 批次·续二）：消费 trace 中 injection_findings 字段
    "injection_detected": _pattern_injection_detected,
}


def match_failure_patterns(
    trace_records: list[dict[str, Any]],
    examples_per_pattern: int = 3,
) -> dict[str, Any]:
    """在 trace JSONL 记录上跑已知失败模式匹配器（纯离线，零 LLM 成本）。

    Args:
        trace_records: TraceSession 产出的 JSONL 记录列表（node / task_end 事件
            均兼容；无 error_category 字段的记录跳过该模式判定，不崩）。
        examples_per_pattern: 每个模式保留的示例 task_id 数（默认 3，避免周报过长）。

    Returns:
        结构化报告 dict：
            {
              "patterns": {模式名: {"count": int, "examples": [task_id, ...]}},
              "total_records": int,
              "matched_records": int,   # 至少命中一个模式的记录数
              "unmatched_records": int  # 未命中任何模式的记录数
            }
    """
    pattern_hits: dict[str, list[str]] = {name: [] for name in _FAILURE_PATTERN_NAMES}
    matched = 0
    total = len(trace_records)

    for record in trace_records:
        if not isinstance(record, dict):
            continue
        task_id = str(record.get("task", "unknown"))
        record_matched = False
        for pattern_name, detector in _PATTERN_DETECTORS.items():
            try:
                hit = detector(record)
            except Exception:
                # 模式判定失败保守降级（不误报，不崩主流程）
                hit = False
            if hit:
                pattern_hits[pattern_name].append(task_id)
                record_matched = True
        if record_matched:
            matched += 1

    patterns: dict[str, dict[str, Any]] = {}
    for name in _FAILURE_PATTERN_NAMES:
        examples = pattern_hits[name][:examples_per_pattern]
        patterns[name] = {"count": len(pattern_hits[name]), "examples": examples}

    report = {
        "patterns": patterns,
        "total_records": total,
        "matched_records": matched,
        "unmatched_records": total - matched,
    }
    logger.info(
        "G4 AgentTelemetry：共 %d 条记录，%d 条命中至少一个失败模式，%d 条未命中",
        total,
        matched,
        total - matched,
    )
    return report


def render_telemetry_report(report: dict[str, Any]) -> str:
    """把 match_failure_patterns 的输出渲染为 Markdown 周报章节（纯文本，零 I/O）。

    Args:
        report: match_failure_patterns 返回的结构化 dict。

    Returns:
        Markdown 文本（可直接追加进 CHANGELOG / 周报）。
    """
    lines = [
        "## G4 AgentTelemetry 故障检测基准（失败模式匹配）",
        "",
        f"- 总记录数: {report.get('total_records', 0)}",
        f"- 命中至少一个模式的记录数: {report.get('matched_records', 0)}",
        f"- 未命中任何模式的记录数: {report.get('unmatched_records', 0)}",
        "",
        "| 失败模式 | 命中次数 | 示例 task_id（前 3） |",
        "|----------|----------|----------------------|",
    ]
    for pattern_name, info in report.get("patterns", {}).items():
        examples = ", ".join(info.get("examples", [])) or "—"
        lines.append(f"| {pattern_name} | {info.get('count', 0)} | {examples} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "agent_telemetry_enabled",
    "match_failure_patterns",
    "render_telemetry_report",
]
