"""定位锚定的局部编辑通道（R4，2026-10-08，默认关）。

背景（ADR-0024 反事实，2026-10-07）：
    `P(correct | FL 命中) = 15.8%` < `P(correct | FL 未命中) = 64.7%`——谱系
    定位命中与修复成功**负相关**，根因是补丁生成走"整文件重写"，根本不消费
    定位信号（ADR-0018 立项动机同源；PRepair ACL'26 arXiv:2604.05963 对
    "over-editing"的系统性刻画与之互证）。本模块把 FaultLocalizer 的结构化
    定位（function_name + line 区间 + Top-3 候选）转化为 edit_intents 的
    **局部性约束**，观测层确定性校验锚点局部化占比——把"生成侧不消费定位"
    从反事实推断细化为可观测、可 A/B 的命题。

约束粒度（2026-10-08 R4 A/B 首测修正）：
    首版用**函数级**约束（锚点落在候选函数体内），A/B 实测 repair 逐任务
    一致（8/50，差异 0）、localized_ratio 恒 1.0——根因是单函数任务上
    "候选函数 = 整个被测代码"，函数级约束**空洞**。本版升级为**行级**约束：
    主判定改用 FaultLocalizer 的 `line_start`/`line_end`（缺陷语句行）加减
    窗口 `LOCALIZED_EDIT_WINDOW`（默认 3 行），锚点必须落在缺陷行附近；
    候选缺 line 信息时才回退函数级（AST 函数定义范围）。

设计口径（承接 ADR-0003 默认关 / ADR-0028·0020 观测层先行纪律）：
    - LOCALIZED_EDIT_ENABLE（默认 false）且 EDIT_INTENT_ENABLE 均开启、且
      结构化定位可用时才生效——二者缺一时零行为变化；
    - 本模块为**纯观测 + prompt 约束**，不强制过滤越界意图（阻断档须先
      A/B 确认"不压制 correct 补丁"才转正，与 ADR-0028 转正纪律一致）；
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
_ENV_WINDOW = "LOCALIZED_EDIT_WINDOW"
_DEFAULT_WINDOW = 3


def localized_edit_enabled() -> bool:
    """定位锚定编辑通道开关（默认关；依赖 EDIT_INTENT_ENABLE 才生效）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def _window() -> int:
    """缺陷行窗口参数（LOCALIZED_EDIT_WINDOW，默认 3 行，下限 0）。"""
    try:
        return max(0, int(os.getenv(_ENV_WINDOW, str(_DEFAULT_WINDOW))))
    except ValueError:
        return _DEFAULT_WINDOW


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


def _candidate_line_windows(loc: dict[str, Any] | None, window: int) -> list[tuple[int, int]]:
    """提取候选缺陷行窗口 [(lo, hi)]——lo=max(1, line_start-W)、hi=line_end+W。

    只用 FaultLocalizer 给的结构化缺陷行（line_start/line_end），不查 AST；
    任一候选缺 line 信息即跳过（调用方据窗口列表是否为空决定行级 vs 函数级）。
    """
    if not loc:
        return []
    candidates = loc.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        candidates = [loc]
    windows: list[tuple[int, int]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        try:
            line_start = int(cand.get("line_start") or 0)
            line_end = int(cand.get("line_end") or line_start)
        except (TypeError, ValueError):
            continue
        if line_start <= 0:
            continue
        windows.append((max(1, line_start - window), line_end + window))
    return windows


def build_localized_edit_section(loc: dict[str, Any] | None) -> str:
    """把定位结果渲染为"局部编辑约束"prompt 段（无有效候选 → 空串）。

    约束口径（行级）：要求 edit_intents 的每条 old_str 锚点落在缺陷语句行
    （FaultLocalizer 的 line_start/line_end）附近，不得整函数/整文件重写。
    """
    names = [n for n in _candidate_functions(loc) if n != "<module>"]
    if not names:
        return ""
    top = str(loc.get("function_name") or "").rsplit(".", maxsplit=1)[-1] if loc else names[0]
    line_start = loc.get("line_start") if loc else None
    line_end = loc.get("line_end") if loc else None
    lines = [
        "【局部编辑约束（定位锚定，LOCALIZED_EDIT_ENABLE）】",
        f"缺陷定位在函数 `{top}`"
        + (f"（缺陷语句 L{line_start}-L{line_end}）" if line_start is not None else "")
        + "。",
        "请在 edit_intents 中**只修改上述缺陷语句行附近的代码**：每条 old_str 锚点",
        "必须落在缺陷语句行（含上下少量上下文）范围内，不得重写整个函数、不得改动",
        "无关代码、不得整文件重写。修改点越少、越贴近缺陷行越好。",
    ]
    if len(names) > 1:
        lines.append("候选函数（按可能性降序）：" + "、".join(f"`{n}`" for n in names) + "。")
    return "\n".join(lines)


def validate_edit_localization(
    code: str,
    intents: list[dict[str, str]],
    loc: dict[str, Any] | None,
    window: int | None = None,
) -> dict[str, Any]:
    """计算 edit_intents 的局部化合规观测（纯静态，零 LLM；不强制过滤）。

    主判定（行级）：锚点行号落在任一候选缺陷行窗口 [line_start-W, line_end+W]
    内；候选缺 line 信息时回退函数级（锚点落在候选函数定义范围内）。
    锚点找不到 → anchor_not_found；落在窗口/函数外 → outside 类 violation
    （观测，不拒绝）。无候选 / 模块级定位 → constrained=False（放行）。

    Returns:
        {"localized_count": int, "total": int, "constrained": bool,
         "candidate_functions": [str], "window": int, "mode": "line"|"function"|"none",
         "violations": [str], "localized_ratio": float}
    """
    total = len(intents)
    names = _candidate_functions(loc)
    win = _window() if window is None else window
    if not names or "<module>" in names:
        # 无候选 / 模块级定位：无缺陷行可约束，保守放行（不误杀模块级修复）
        return {
            "localized_count": total,
            "total": total,
            "constrained": False,
            "candidate_functions": names,
            "window": win,
            "mode": "none",
            "violations": [],
            "localized_ratio": 1.0 if total else 0.0,
        }
    line_windows = _candidate_line_windows(loc, win)
    localized = 0
    violations: list[str] = []
    if line_windows:
        mode = "line"
        for idx, intent in enumerate(intents, start=1):
            line = _anchor_line(code, intent.get("old_str", ""))
            if line < 0:
                violations.append(f"intent_{idx}_anchor_not_found")
            elif any(lo <= line <= hi for lo, hi in line_windows):
                localized += 1
            else:
                violations.append(f"intent_{idx}_outside_window:L{line}")
    else:
        # 候选缺 line 信息 → 回退函数级（AST 函数定义范围）
        mode = "function"
        name_to_ranges: dict[str, list[tuple[int, int]]] = {}
        for start, end, name in _function_ranges(code):
            name_to_ranges.setdefault(name, []).append((start, end))
        for idx, intent in enumerate(intents, start=1):
            line = _anchor_line(code, intent.get("old_str", ""))
            if line < 0:
                violations.append(f"intent_{idx}_anchor_not_found")
            elif any(start <= line <= end for name in names for start, end in name_to_ranges.get(name, [])):
                localized += 1
            else:
                violations.append(f"intent_{idx}_outside_candidates:L{line}")
    return {
        "localized_count": localized,
        "total": total,
        "constrained": True,
        "candidate_functions": names,
        "window": win,
        "mode": mode,
        "violations": violations,
        "localized_ratio": (localized / total) if total else 0.0,
    }


__all__ = [
    "build_localized_edit_section",
    "localized_edit_enabled",
    "validate_edit_localization",
]
