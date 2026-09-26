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


def _closure_names(
    focus: str,
    top_level_funcs: dict[str, ast.AST],
    depth: int,
) -> dict[str, list[str]]:
    """BFS 构建焦点函数的调用链闭包（P0 1.1 分层代码压缩）。

    depth=1：焦点直接调用的同文件函数（历史行为）；
    depth>=2：继续展开每一层被调函数自身的直接调用（最多到 depth 层）。

    Returns:
        {函数名: [直接调用的顶层函数名...]}，key 集即"保留哪些函数"的
        完整集合（含 focus 自身及其调用链所有层）。
    """
    if focus not in top_level_funcs:
        return {}
    closure: dict[str, list[str]] = {}
    # BFS 分层展开；visited 防止环路；max_depth 控制展开层数
    visited: set[str] = set()
    frontier: list[str] = [focus]
    for _level in range(max(0, depth)):
        next_frontier: list[str] = []
        for name in frontier:
            if name in visited:
                continue
            visited.add(name)
            node = top_level_funcs.get(name)
            if node is None:
                continue
            called = sorted(n for n in _collect_called_names(node) if n in top_level_funcs and n != name)
            closure[name] = called
            next_frontier.extend(c for c in called if c not in visited)
        if not next_frontier:
            break
        frontier = next_frontier
    # 把前沿中尚未展开的函数也加入闭包 keys（depth 截止点）
    for name in frontier:
        if name not in closure:
            closure[name] = []
    return closure


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


def _build_header(source_lines: list[str], tree: ast.Module) -> str:
    """收集模块级 import 语句（含 from X import Y），拼接为文件头。"""
    segments: list[str] = [
        _slice_source(source_lines, node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    return "\n".join(segments)


def _collect_top_level_funcs(tree: ast.Module) -> dict[str, ast.AST]:
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
        text = _slice_source(source_lines, segment) if isinstance(segment, ast.AST) else _render_segment(segment)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _is_direct_dep(focus: str, candidate: str, top_level_funcs: dict[str, ast.AST]) -> bool:
    """判断 candidate 是否为 focus 的一层直接依赖（焦点体内直接调用）。"""
    focus_node = top_level_funcs.get(focus)
    if focus_node is None:
        return False
    return candidate in _collect_called_names(focus_node)


def _trim_focus_related(
    kept: dict[str, object],
    focus: str,
    top_level_funcs: dict[str, ast.AST],
    depth: int = 1,
) -> dict[str, object]:
    """裁剪为"焦点 + 调用链 depth 层依赖"的最小保留集合。"""
    allowed = {focus}
    for name in _closure_names(focus, top_level_funcs, depth):
        allowed.add(name)
    return {name: seg for name, seg in kept.items() if name in allowed}


def _apply_focus_budget(
    header: str,
    kept: dict[str, object],
    focus: str,
    top_level_funcs: dict[str, ast.AST],
    source_lines: list[str],
    max_chars: int,
    result: str,
    depth: int = 1,
) -> str:
    """焦点函数存在时的逐层预算裁剪：无关函数丢弃 → 函数体首尾截断 → 只留焦点。

    优先级"焦点 > 调用链 depth 层依赖 > 无关函数"，每一层裁完即检查预算，
    三层都放不下时返回最后一层结果（仍由调用方走字符级兜底）。
    """
    if len(kept) > 1:
        result = _assemble(header, _trim_focus_related(kept, focus, top_level_funcs, depth), source_lines)
        if len(result) <= max_chars:
            return result
    # 第二层：焦点 + 调用链依赖，焦点函数体截断为"首尾各 N 行"
    truncated = _truncate_long_body(source_lines, top_level_funcs[focus])
    minimal_kept = _trim_focus_related(kept, focus, top_level_funcs, depth)
    minimal_kept[focus] = SimpleNamespace(_prebuilt_text=truncated)
    result = _assemble(header, minimal_kept, source_lines)
    if len(result) <= max_chars:
        return result
    # 第三层：极端预算，只留截断焦点
    return _assemble(header, {focus: SimpleNamespace(_prebuilt_text=truncated)}, source_lines)


def extract_focused_code(
    source: str,
    focus_function: str | None = None,
    max_chars: int = 3000,
    depth: int = 1,
) -> str:
    """基于 AST 提取与目标函数相关的最小代码上下文。

    保留 import、目标函数及其调用链 depth 层依赖的辅助函数；组装结果
    超过 max_chars 时按"焦点 > depth 层依赖 > 无关函数"优先级丢弃，
    并允许对超长函数体做首尾截断。

    Args:
        source: 原始 Python 源码全文。
        focus_function: 焦点函数/方法名（如 "divide"）；None 时保留全部顶层函数。
        max_chars: 输出最大字符预算（默认 3000，与 truncate_code 一致）。
        depth: 调用链展开层数（P0 1.1 分层代码压缩）：1 = 焦点直接调用的
            辅助函数（历史行为）；2 = 再展开一层被调函数的依赖（跨文件
            任务的"目标函数 → 被调用函数（1-2 层）→ 相关类定义"口径）。
            仅当 focus_function 在源码中存在时生效。

    Returns:
        截取后的代码片段。源码为空或无法解析时原样返回，
        由调用方（truncate_code）继续做字符级硬截断兜底。
    """
    result, _focus_resolved = extract_focused_code_detail(
        source,
        focus_function=focus_function,
        max_chars=max_chars,
        depth=depth,
    )
    return result


def extract_focused_code_detail(
    source: str,
    focus_function: str | None = None,
    max_chars: int = 3000,
    depth: int = 1,
) -> tuple[str, bool]:
    """带解析结果的 extract_focused_code（2026-09-26 全面审查 C-1 新增）。

    返回 (code, focus_resolved)：focus_resolved 为 True 表示焦点函数在源码
    中存在且 AST 截取成功；False 表示原样返回（AST 解析失败 / 无顶层函数 /
    焦点函数不在源码中），调用方可据此决定降级路径（如 extract_function_context
    返回 None 让上游走全文件兜底）。

    目的：消除 extract_function_context 此前"靠 result == source_code 反推 +
    再做一次 ast.parse"的重复解析（大文件 ~200ms 翻倍）。
    """
    if not source or not source.strip():
        return source, False

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        logger.debug("AST 解析失败，extract_focused_code 原样返回，交由字符级截断兜底")
        return source, False

    source_lines = source.splitlines()
    header = _build_header(source_lines, tree)
    top_level_funcs = _collect_top_level_funcs(tree)

    if not top_level_funcs:
        # 纯模块（无函数）：只有 import 头 + 常量等，交给字符级截断控制长度
        return source, False

    # ── 确定保留集合 ───────────────────────────────────────────────────────
    kept: dict[str, object] = {}
    focus_resolved = False
    if focus_function and focus_function in top_level_funcs:
        kept[focus_function] = top_level_funcs[focus_function]
        focus_resolved = True
        # 调用链闭包：焦点函数 depth 层内直接调用的同文件函数
        closure = _closure_names(focus_function, top_level_funcs, max(1, depth))
        for called in closure:
            if called != focus_function and called in top_level_funcs:
                kept[called] = top_level_funcs[called]
    else:
        # 无焦点（或焦点名不在源码中）：保留全部顶层函数，按预算裁剪
        kept = dict(top_level_funcs)

    # ── 按预算逐层裁剪（仅当焦点函数确实存在于源码中才启用焦点优先策略）────
    result = _assemble(header, kept, source_lines)
    if len(result) <= max_chars:
        return result, focus_resolved

    focus_in_source = bool(focus_function and focus_function in top_level_funcs)
    if focus_in_source:
        result = _apply_focus_budget(
            header,
            kept,
            str(focus_function),
            top_level_funcs,
            source_lines,
            max_chars,
            result,
            depth=max(1, depth),
        )

    # 最终兜底：交给字符级硬截断（truncate_code 会处理超长返回）
    if len(result) > max_chars:
        logger.info("AST 截取仍超预算（%d 字符），回退字符级截断", len(result))
    return result, focus_resolved
