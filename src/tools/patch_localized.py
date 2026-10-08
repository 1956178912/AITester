"""定位锚定的局部编辑通道（R4 原型，2026-10-08，默认关）。

背景（ADR-0024 反事实，2026-10-07）：
    `P(correct | FL 命中) = 15.8%` < `P(correct | FL 未命中) = 64.7%`——谱系
    定位命中与修复成功**负相关**，根因是补丁生成走"整文件重写"，根本不消费
    定位信号（ADR-0018 立项动机同源；PRepair ACL'26 arXiv:2604.05963 对
    "over-editing"的系统性刻画与之互证）。本模块把 FaultLocalizer 的结构化
    定位（function_name + line 区间 + Top-3 候选）转化为 edit_intents 的
    **局部性约束**：prompt 层要求 LLM 的 old_str 锚点落在定位候选函数内，
    观测层确定性校验锚点局部化占比——把"生成侧不消费定位"从反事实推断
    细化为可观测、可 A/B 的命题。

设计口径（承接 ADR-0003 默认关 / ADR-0028·0020 观测层先行纪律）：
    - LOCALIZED_EDIT_ENABLE（默认 false）且 EDIT_INTENT_ENABLE 均开启、且
      结构化定位可用时才生效——二者缺一时零行为变化；
    - 本模块为**纯观测 + prompt 约束**，不强制过滤越界意图（阻断档须先
      A/B 确认"不压制 correct 补丁"才转正，与 ADR-0028 fl_constraint_verdict
      的转正纪律一致）；
    - 模块级定位（"<module>"）/ 无候选函数 / 锚点不可定位时保守放行
      （constrained=False，不误杀 import 调整等合法模块级修复）。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "LOCALIZED_EDIT_ENABLE"


def localized_edit_enabled() -> bool:
    """定位锚定编辑通道开关（默认关；依赖 EDIT_INTENT_ENABLE 才生效）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def _candidate_functions(loc: dict[str, Any] | None) -> list[str]:
    """从定位结果提取候选函数名（叶子名归一去重，与 fl_constraint_verdict 同口径）。"""
    if not loc:
        return []
    candidates = loc.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        candidates = [loc]
    names: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        leaf = str(cand.get("function_name") or "").rsplit(".", maxsplit=1)[-1]
        if leaf and leaf not in seen:
            seen.add(leaf)
            names.append(leaf)
    return names


def _function_ranges(code: str) -> list[tuple[int, int, str]]:
    """提取 (start_line, end_line, function_name) 列表（含嵌套，1-based 闭区间）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        (node.lineno, node.end_lineno or node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _anchor_line(code: str, anchor: str) -> int:
    """锚点在 code 中的起始行号（1-based）；找不到返回 -1。"""
    idx = code.find(anchor)
    if idx < 0:
        return -1
    return code.count("\n", 0, idx) + 1


def build_localized_edit_section(loc: dict[str, Any] | None) -> str:
    """把定位结果渲染为"局部编辑约束"prompt 段（无有效候选 → 空串）。

    约束口径：要求 edit_intents 的每条 old_str 锚点落在定位候选函数体内，
    不得重写函数签名、不得改动其他无关函数——把定位信号从"告知"升级为
    "行为约束"。
    """
    names = [n for n in _candidate_functions(loc) if n != "<module>"]
    if not names:
        return ""
    top = str(loc.get("function_name") or "").rsplit(".", maxsplit=1)[-1] if loc else names[0]
    line_start = loc.get("line_start") if loc else None
    line_end = loc.get("line_end") if loc else None
    lines = [
        "【局部编辑约束（定位锚定，LOCALIZED_EDIT_ENABLE）】",
        f"缺陷定位在函数 `{top}`" + (f"（L{line_start}-L{line_end}）" if line_start is not None else "") + "。",
        "请在 edit_intents 中**只修改定位函数体内的代码**：每条 old_str 锚点必须",
        "完整落在上述候选函数体内，不得重写函数签名、不得改动其他无关函数、",
        "不得整文件重写。修改点越少、越贴近定位区间越好。",
    ]
    if len(names) > 1:
        lines.append("候选函数（按可能性降序）：" + "、".join(f"`{n}`" for n in names) + "。")
    return "\n".join(lines)


def validate_edit_localization(
    code: str,
    intents: list[dict[str, str]],
    loc: dict[str, Any] | None,
) -> dict[str, Any]:
    """计算 edit_intents 的局部化合规观测（纯静态，零 LLM；不强制过滤）。

    对每条 intent 计算 old_str 锚点行号，判定是否落在任一候选函数
    [start, end] 内。锚点找不到 / 落在候选外 → 记 violation（观测，
    不拒绝）；无候选 / 模块级定位 → constrained=False（无法约束，放行）。

    Returns:
        {"localized_count": int, "total": int, "constrained": bool,
         "candidate_functions": [str], "violations": [str],
         "localized_ratio": float}
    """
    total = len(intents)
    names = _candidate_functions(loc)
    if not names or "<module>" in names:
        # 无候选 / 模块级定位：无函数区间可约束，保守放行（不误杀模块级修复）
        return {
            "localized_count": total,
            "total": total,
            "constrained": False,
            "candidate_functions": names,
            "violations": [],
            "localized_ratio": 1.0 if total else 0.0,
        }
    ranges = _function_ranges(code)
    name_to_ranges: dict[str, list[tuple[int, int]]] = {}
    for start, end, name in ranges:
        name_to_ranges.setdefault(name, []).append((start, end))
    localized = 0
    violations: list[str] = []
    for idx, intent in enumerate(intents, start=1):
        anchor = intent.get("old_str", "")
        line = _anchor_line(code, anchor)
        if line < 0:
            violations.append(f"intent_{idx}_anchor_not_found")
            continue
        if any(start <= line <= end for name in names for start, end in name_to_ranges.get(name, [])):
            localized += 1
        else:
            violations.append(f"intent_{idx}_outside_candidates:L{line}")
    return {
        "localized_count": localized,
        "total": total,
        "constrained": True,
        "candidate_functions": names,
        "violations": violations,
        "localized_ratio": (localized / total) if total else 0.0,
    }


__all__ = [
    "build_localized_edit_section",
    "localized_edit_enabled",
    "validate_edit_localization",
]
