"""
基于 AST 的智能代码截取模块（P0 大文件上下文丢失问题的解决方案）。

背景：
    BaseAgent.truncate_code 此前对超长代码做"头尾各半"的字符级硬截断
    （默认 3000 字符，约 100 行）。SWE-bench 等真实项目的源文件通常
    数百行，硬截断会让 LLM 看不到目标函数及其依赖的辅助函数，
    导致生成/修复效果显著劣化。

策略（extract_focused_code）：
    1. 解析源文件 AST，失败（非法 Python）时原样返回，由调用方走字符级兜底；
    2. 保留所有模块级 import 语句（依赖关系的前提）；
    3. 若指定 focus_function：保留该函数/方法，以及它直接调用的
       同文件内其他函数（一层依赖闭包）；
    4. 未指定 focus_function：保留全部顶层函数；
    5. 组装结果仍超 max_chars 时，按"焦点 > 直接依赖 > 无关函数"
       优先级丢弃无关函数；对超长函数体做"首尾各 N 行 + 中间省略"截断。

使用方式：
    from src.tools.code_context import extract_focused_code
    focused = extract_focused_code(source, focus_function="divide", max_chars=3000)
"""

from __future__ import annotations

import ast
import logging
from types import SimpleNamespace

logger = logging.getLogger(__name__)

# 超长函数体截断时，首尾各保留的常量行数（中间以省略标记替代）。
# 取值 8 行：足够覆盖典型函数的入参/边界检查与返回逻辑，
# 同时把单函数占用压到 ~16 行以内，为多个函数留出预算。
_LONG_BODY_KEEP_HEAD_LINES = 8
_LONG_BODY_KEEP_TAIL_LINES = 8
# 中间省略标记（对 LLM 显式表达"此处有代码被截断"）
_OMISSION_MARKER = "# ... (truncated)"


def _slice_source(source_lines: list[str], node: ast.AST) -> str:
    """按 AST 节点的行号范围（1-based）从源码切出对应文本。"""
    start = getattr(node, "lineno", 1) or 1
    end = getattr(node, "end_lineno", start) or start
    return "\n".join(source_lines[start - 1 : end])


def _collect_called_names(func: ast.AST) -> set[str]:
    """收集函数体内直接调用/引用的顶层名称（一层闭包，不递归展开）。"""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _find_body_indent(body_lines: list[str]) -> int:
    """找到函数体的首个非注释行缩进深度（省略标记的缩进参考）。"""
    for line in body_lines[1:]:
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            return len(line) - len(stripped)
    return 4


def _truncate_long_body(source_lines: list[str], func_node: ast.AST) -> str:
    """对超长函数做"首尾各 N 行 + 中间省略"截断，保留签名与返回逻辑。"""
    start = getattr(func_node, "lineno", 1) or 1
    end = getattr(func_node, "end_lineno", start) or start
    body_lines = source_lines[start - 1 : end]
    if len(body_lines) <= _LONG_BODY_KEEP_HEAD_LINES + _LONG_BODY_KEEP_TAIL_LINES:
        return "\n".join(body_lines)
    head = body_lines[:_LONG_BODY_KEEP_HEAD_LINES]
    tail = body_lines[-_LONG_BODY_KEEP_TAIL_LINES:]
    indent = " " * _find_body_indent(body_lines)
    return "\n".join(head) + f"\n{indent}{_OMISSION_MARKER}\n" + "\n".join(tail)


def _build_header(source_lines: list[str], tree: ast.AST) -> str:
    """收集模块级 import 语句（含 from X import Y），拼接为文件头。"""
    segments: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            segments.append(_slice_source(source_lines, node))
    return "\n".join(segments)


def _collect_top_level_funcs(tree: ast.AST) -> dict[str, ast.AST]:
    """收集顶层函数，以及类体内的方法（方法名本身作为 key）。"""
    funcs: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.setdefault(member.name, member)
    return funcs


def _render_segment(segment: object) -> str:
    """渲染保留段：AST 节点按行号切源码；SimpleNamespace 占位段取预构建文本。"""
    if isinstance(segment, SimpleNamespace):
        return str(getattr(segment, "_prebuilt_text", ""))
    return str(segment)


def _assemble(header: str, kept: dict[str, object], source_lines: list[str]) -> str:
    """按保留集合组装代码片段（import 头 + 各函数段，双换行分隔）。"""
    parts: list[str] = []
    if header:
        parts.append(header)
    for segment in kept.values():
        if isinstance(segment, ast.AST):
            text = _slice_source(source_lines, segment)
        else:
            text = _render_segment(segment)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _is_direct_dep(focus: str, candidate: str, top_level_funcs: dict[str, ast.AST]) -> bool:
    """判断 candidate 是否为 focus 的一层直接依赖（焦点体内直接调用）。"""
    focus_node = top_level_funcs.get(focus)
    if focus_node is None:
        return False
    return candidate in _collect_called_names(focus_node)


def extract_focused_code(
    source: str,
    focus_function: str | None = None,
    max_chars: int = 3000,
) -> str:
    """基于 AST 提取与目标函数相关的最小代码上下文。

    保留 import、目标函数及其直接依赖的辅助函数；组装结果超过
    max_chars 时按"焦点 > 直接依赖 > 无关函数"优先级丢弃，
    并允许对超长函数体做首尾截断。

    Args:
        source: 原始 Python 源码全文。
        focus_function: 焦点函数/方法名（如 "divide"）；None 时保留全部顶层函数。
        max_chars: 输出最大字符预算（默认 3000，与 truncate_code 一致）。

    Returns:
        截取后的代码片段。源码为空或无法解析时原样返回，
        由调用方（truncate_code）继续做字符级硬截断兜底。
    """
    if not source or not source.strip():
        return source

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        logger.debug("AST 解析失败，extract_focused_code 原样返回，交由字符级截断兜底")
        return source

    source_lines = source.splitlines()
    header = _build_header(source_lines, tree)
    top_level_funcs = _collect_top_level_funcs(tree)

    if not top_level_funcs:
        # 纯模块（无函数）：只有 import 头 + 常量等，交给字符级截断控制长度
        return source

    # ── 确定保留集合 ───────────────────────────────────────────────────────
    kept: dict[str, object] = {}
    if focus_function and focus_function in top_level_funcs:
        kept[focus_function] = top_level_funcs[focus_function]
        # 一层依赖：焦点函数直接调用的同文件内函数
        for called in _collect_called_names(top_level_funcs[focus_function]):
            if called in top_level_funcs and called != focus_function:
                kept[called] = top_level_funcs[called]
    else:
        # 无焦点（或焦点名不在源码中）：保留全部顶层函数，按预算裁剪
        kept = dict(top_level_funcs)

    # ── 按预算逐层裁剪（仅当焦点函数确实存在于源码中才启用焦点优先策略）────
    result = _assemble(header, kept, source_lines)
    if len(result) <= max_chars:
        return result

    if focus_function and focus_function in top_level_funcs:
        # 第一层裁剪：丢弃与焦点无关的函数（import + 焦点 + 直接依赖）
        if len(kept) > 1:
            minimal_kept = {
                name: seg
                for name, seg in kept.items()
                if name == focus_function or _is_direct_dep(focus_function, name, top_level_funcs)
            }
            result = _assemble(header, minimal_kept, source_lines)
            if len(result) <= max_chars:
                return result
        # 第二层裁剪：焦点函数体超长 → 首尾截断
        focus_node = top_level_funcs[focus_function]
        truncated = _truncate_long_body(source_lines, focus_node)
        minimal_kept = {name: seg for name, seg in kept.items() if _is_direct_dep(focus_function, name, top_level_funcs)}
        minimal_kept[focus_function] = SimpleNamespace(_prebuilt_text=truncated)
        result = _assemble(header, minimal_kept, source_lines)
        if len(result) <= max_chars:
            return result
        # 极端情况：只剩焦点仍超预算 → 只留 import + 截断焦点
        last_resort = {focus_function: SimpleNamespace(_prebuilt_text=truncated)}
        result = _assemble(header, last_resort, source_lines)
        if len(result) <= max_chars:
            return result

    # 最终兜底：交给字符级硬截断（truncate_code 会处理超长返回）
    logger.info("AST 截取仍超预算（%d 字符），回退字符级截断", len(result))
    return result
