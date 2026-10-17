"""
2.2 改进：控制流图（CFG）级别静态分析。

背景：
    当前 Logic-driven CoT 的核心是 PlannerAgent 生成 logic_analysis（输入域、
    输出域、前置/后置条件、边界情况），但缺少对**控制流路径**的显式建模——
    分支条件、循环边界、异常路径。本模块提供纯 AST 静态分析
    （零 LLM 成本、可复算），产出 CFG 摘要，注入 Planner prompt 使
    测试用例覆盖更系统化（按路径覆盖而非 LLM 自由发挥）。

分析内容（针对目标函数，target_function 缺省时分析全部顶层函数）：
    - branch_conditions: 条件表达式列表（if/elif/while/for 的 cond、
      三元表达式），每条带行号——分支路径枚举的基础；
    - loop_boundaries: 循环结构（for/while，含迭代器形态）及行号，
      循环边界（0 次迭代 / 1 次 / N 次）是测试系统化覆盖的经典路径；
    - exception_paths: try/except/raise 结构，每条 except 的异常类型
      与 raise 的异常类——异常路径覆盖（正常/异常双路径）；
    - cyclomatic_estimate: 圈复杂度近似（1 + 分支数 + 循环数），
      供"路径复杂度"观测与多候选/降级策略消费；
    - return_points: return 语句位置列表（多返回点 = 多出口路径）。

设计约束（与 code_analyzer / code_context 同口径）：
    - 纯 AST 静态分析，不执行被测代码（安全）；
    - 解析失败返回空摘要（保守降级，不阻断 Planner 主流程）；
    - 输出 JSON 可序列化（供 state / trace / prompt 注入复用）。
"""

from __future__ import annotations

import ast
import logging
from typing import Any

from src.utils.env_utils import env_flag_opt_out, env_int

logger = logging.getLogger(__name__)

# 摘要的字符预算（注入 Planner prompt 时截断，防超长代码摘要撑爆上下文）
# F 轮加固：改经 env_int 容错解析——模块级裸 int() 在坏值时于 **import 期**
# 抛 ValueError（一个拼错的环境变量即让本叶子模块不可导入，且本模块被
# planner.py 顶层导入，故障面会向上扩散）；env_int 记 WARNING 后回退默认值。
_CFG_SUMMARY_MAX_CHARS = env_int("CFG_SUMMARY_MAX_CHARS", 1500)


def _cond_expr_text(node: ast.AST, source_lines: list[str]) -> str:
    """条件表达式 → 单行文本（ast.unparse 优先，源码行兜底）。"""
    try:
        return ast.unparse(node)[:120]
    except Exception:
        line_no = getattr(node, "lineno", 0)
        if line_no and 1 <= line_no <= len(source_lines):
            return source_lines[line_no - 1].strip()[:120]
        return "?"


def _function_node(code: str, func_name: str | None) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """按名取顶层函数节点；func_name 为 None 时取第一个顶层函数。"""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (func_name is None or node.name == func_name):
            return node
    return None


def analyze_control_flow(code: str, func_name: str | None = None) -> dict[str, Any]:
    """静态分析目标函数的控制流图（CFG 摘要，零 LLM 成本）。

    Args:
        code: 被测代码全文（AST 解析）。
        func_name: 目标函数名；None 时分析第一个顶层函数（Planner 默认口径）。

    Returns:
        CFG 摘要 dict（JSON 可序列化）：
        - "func_name": str | None（实际分析的函数；代码不可解析时 None）
        - "branch_conditions": [ {line, expr} ... ]
        - "loop_boundaries": [ {line, kind: "for"|"while", iterator} ... ]
        - "exception_paths": [ {line, kind: "raise"|"except", types} ... ]
        - "return_points": [ {line, value} ... ]
        - "cyclomatic_estimate": int（1 + 分支 + 循环）
        - "path_hint": str（路径覆盖建议文本，注入 prompt 用）

        代码不可解析时返回全空摘要（func_name 可能非 None，但各列表为空，
        cyclomatic_estimate=1，保守口径）。
    """
    empty: dict[str, Any] = {
        "func_name": func_name,
        "branch_conditions": [],
        "loop_boundaries": [],
        "exception_paths": [],
        "return_points": [],
        "cyclomatic_estimate": 1,
        "path_hint": "",
    }
    source_lines = code.splitlines()
    func_node = _function_node(code, func_name)
    if func_node is None:
        return empty

    branches: list[dict[str, Any]] = []
    loops: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    returns: list[dict[str, Any]] = []

    for node in ast.walk(func_node):
        # 分支条件（if / elif / while / 三元表达式）
        if isinstance(node, ast.If):
            branches.append({"line": node.lineno, "expr": _cond_expr_text(node.test, source_lines)})
        elif isinstance(node, ast.While):
            branches.append({"line": node.lineno, "expr": _cond_expr_text(node.test, source_lines)})
            loops.append({"line": node.lineno, "kind": "while", "iterator": ""})
        elif isinstance(node, ast.For):
            try:
                it = ast.unparse(node.iter)[:80]
            except Exception:
                it = "?"
            loops.append({"line": node.lineno, "kind": "for", "iterator": it})
        elif isinstance(node, ast.IfExp):
            branches.append({"line": node.lineno, "expr": "ternary: " + _cond_expr_text(node.test, source_lines)})
        # 异常路径（raise / except / try）
        elif isinstance(node, ast.Raise):
            types: list[str] = []
            if node.exc is not None:
                types = [
                    n.id if isinstance(n, ast.Name) else (ast.unparse(n) if isinstance(n, ast.Call) else "?")
                    for n in ([node.exc] if _is_exception_node(node.exc) else [])
                ]
            exceptions.append({"line": node.lineno, "kind": "raise", "types": types})
        elif isinstance(node, ast.ExceptHandler):
            types = []
            if node.type is not None:
                if isinstance(node.type, ast.Tuple):
                    types = [_exc_type_name(elt) for elt in node.type.elts]
                else:
                    types = [_exc_type_name(node.type)]
            exceptions.append({"line": node.lineno, "kind": "except", "types": types})
        # 多出口
        elif isinstance(node, ast.Return):
            if node.value is not None:
                try:
                    val = ast.unparse(node.value)[:60]
                except Exception:
                    val = "?"
            else:
                val = "None"
            returns.append({"line": node.lineno, "value": val})

    # 去重（ast.walk 中 elif 的 If 节点不重复出现；但嵌套同名条件可能重复）
    seen: set[tuple[Any, Any]] = set()
    branches_dedup: list[dict[str, Any]] = []
    for b in branches:
        k = (b["line"], b["expr"])
        if k not in seen:
            seen.add(k)
            branches_dedup.append(b)

    cyclomatic = 1 + len(branches_dedup) + len(loops)
    func_actual = func_node.name

    # 路径覆盖建议（注入 prompt 的文本形式；预算内截断）
    hint_parts: list[str] = []
    if branches_dedup:
        hint_parts.append(
            f"分支 {len(branches_dedup)} 处（第 " + ", ".join(str(b["line"]) for b in branches_dedup[:8]) + " 行）"
        )
    if loops:
        hint_parts.append("循环 " + ", ".join(f"{x['kind']}@{x['line']}" for x in loops[:5]))
    if exceptions:
        hint_parts.append(
            "异常路径 "
            + ", ".join((f"{e['kind']}[{','.join(e['types'])}]" if e["types"] else e["kind"]) for e in exceptions[:5])
        )
    if returns:
        hint_parts.append(f"出口 {len(returns)} 个")
    if hint_parts:
        path_hint = "控制流摘要：" + "；".join(hint_parts) + f"（圈复杂度估计 {cyclomatic}）。"
        path_hint += "请为每条分支/循环/异常路径生成对应测试用例，避免只测主路径。"
        if len(path_hint) > _CFG_SUMMARY_MAX_CHARS:
            path_hint = path_hint[:_CFG_SUMMARY_MAX_CHARS]
    else:
        path_hint = "控制流简单（单一路径，无分支/循环/异常）。"

    return {
        "func_name": func_actual,
        "branch_conditions": branches_dedup,
        "loop_boundaries": loops,
        "exception_paths": exceptions,
        "return_points": returns,
        "cyclomatic_estimate": cyclomatic,
        "path_hint": path_hint,
    }


def _is_exception_node(node: ast.AST) -> bool:
    """raise 的 exc 是否为异常类型节点（Name/Call 视为可命名）。"""
    return isinstance(node, (ast.Name, ast.Call))


def _exc_type_name(node: ast.AST) -> str:
    """异常类型节点 → 名称文本（Name→id，Call→func 名，其余 unparse）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return node.func.id if isinstance(node.func, ast.Name) else ast.unparse(node)
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def cfg_analysis_enabled() -> bool:
    """CFG 分析开关（CFG_ANALYSIS_ENABLE，默认 true——纯静态零成本，
    注入 prompt 为增量信息，不改变历史 LLM 调用次数；设 false 回退
    历史口径，供 A/B 消融）。"""
    return env_flag_opt_out("CFG_ANALYSIS_ENABLE")


def build_cfg_prompt_section(cfg: dict[str, Any] | None) -> str:
    """CFG 摘要 → prompt 注入段落（Planner/Generator 共用；None/空摘要时
    返回空串 = 历史口径零变化）。"""
    if not cfg_analysis_enabled() or not cfg:
        return ""
    hint = cfg.get("path_hint", "")
    if not hint:
        return ""
    return (
        "\n【控制流分析（CFG 静态层，2.2）】\n"
        f"函数 {cfg.get('func_name') or 'unknown'} 的 {hint}\n"
        f"分支明细：{[b['expr'] for b in cfg.get('branch_conditions', [])[:6]]}\n"
        f"循环明细：{[x['kind'] + '(' + (x['iterator'] or 'cond') + ')' for x in cfg.get('loop_boundaries', [])[:4]]}\n"
        f"异常明细：{[e['kind'] + (':' + ','.join(e['types']) if e['types'] else '') for e in cfg.get('exception_paths', [])[:4]]}\n"
    )


# ─── 路径枚举（结构接地·SPARC 第 1 阶段，独立审查 2026-10-10 落地）─────────
# 背景：报告建议 4（结构接地）指出"逻辑通道应从 oracle 注入转为结构接地"。
# SPARC（arXiv:2602.16671）第 1 阶段"CFG 分析提取执行路径"的纯静态落地——
# 把函数的 if/elif/else 分支组合枚举为独立路径，作为"路径定向测试合成"
# （后续需 LLM 的提示注入）的静态输入。此前的 analyze_control_flow 只产出
# CFG 摘要（branch_conditions 等），不枚举"到达某路径需满足的条件组合"。

# 路径数上限（防指数爆炸）：决策路径数随 if 数量指数增长，硬性截断
# （F 轮加固：同上，经 env_int 容错解析，坏值不再于 import 期崩溃）
_PATH_MAX_DEFAULT = env_int("PATH_ENUM_MAX_PATHS", 32)
# 循环边界三路径的语义标签（循环边界覆盖是系统化测试的经典三路径）
_LOOP_BOUNDARY_LABELS: tuple[str, ...] = ("0次迭代", "1次迭代", "N次迭代")


def _if_cond_text(node: ast.AST) -> str:
    """if 条件 → 单行文本（ast.unparse 优先，源码行兜底）。"""
    try:
        return ast.unparse(node)[:100]
    except Exception:
        return "?"


def _walk_block_paths(
    stmts: list[ast.stmt],
    conds: list[str],
    lines: list[int],
    paths: list[dict[str, Any]],
    max_paths: int,
) -> None:
    """递归枚举语句块的控制流路径（DFS，结果 append 到 paths）。

    口径：
    - 空块 → 记录一条路径（当前 conds/lines 快照）；
    - if → then 分支（条件真）+ else 分支（条件假）两条分叉，均追加
      后续语句（tail）以模拟控制流合并；
    - 循环（while/for）→ 三种边界路径（0次/1次/N次迭代），不展开循环体
      （展开会无限 / 指数爆炸）；
    - 其他语句 → 不改变路径，继续 tail。

    Args:
        stmts: 当前语句块。
        conds: 到达当前点的条件描述序列。
        lines: 到达当前点经过的分支行号序列。
        paths: 输出路径列表（原地 append）。
        max_paths: 路径数上限（超出即停，防爆炸）。
    """
    if len(paths) >= max_paths:
        return
    if not stmts:
        paths.append({"conditions": list(conds), "branch_lines": list(lines)})
        return
    head = stmts[0]
    tail = stmts[1:]
    if isinstance(head, ast.If):
        cond = _if_cond_text(head.test)
        # then 分支：条件为真 → 走 body 再走 tail（控制流合并）
        _walk_block_paths(
            list(head.body) + tail,
            [*conds, f"满足 {cond}"],
            [*lines, head.lineno],
            paths,
            max_paths,
        )
        # else 分支：条件为假 → 走 orelse（elif 链天然递归）再走 tail
        _walk_block_paths(
            list(head.orelse) + tail if head.orelse else tail,
            [*conds, f"不满足 {cond}"],
            [*lines, head.lineno],
            paths,
            max_paths,
        )
        return
    if isinstance(head, (ast.While, ast.For)):
        # 循环三边界路径（不展开循环体）
        for label in _LOOP_BOUNDARY_LABELS:
            _walk_block_paths(tail, [*conds, f"循环 {label}"], [*lines, head.lineno], paths, max_paths)
        return
    # 普通语句：不改变路径
    _walk_block_paths(tail, conds, lines, paths, max_paths)


def enumerate_paths(
    code: str,
    func_name: str | None = None,
    max_paths: int | None = None,
) -> dict[str, Any]:
    """枚举目标函数的独立执行路径（CFG 路径枚举，零 LLM 成本）。

    背景（独立审查 2026-10-10 落地，报告建议 4 结构接地的静态基础）：
        SPARC（arXiv:2602.16671）第 1 阶段"CFG 分析提取执行路径"的纯静态
        落地——把函数的 if/elif/else 分支组合枚举为独立路径，作为"路径定向
        测试合成"（后续需 LLM 的提示注入）的静态输入。此前的
        analyze_control_flow 只产出 CFG 摘要（branch_conditions 等），不枚举
        "到达某路径需满足的条件组合"——本函数补齐该缺口。

    简化口径（保守，防指数爆炸）：
        - 只枚举 if/elif/else 的分支组合（决策路径），每条路径 = 条件序列
          （"满足 x>0" / "不满足 x>0" 的依次组合）；
        - 循环（while/for）不展开循环体，标注为 0 次 / 1 次 / N 次三种边界
          路径（循环边界覆盖是系统化测试的经典三路径）；
        - 路径数上限 max_paths（默认 32，可用 PATH_ENUM_MAX_PATHS 覆盖），
          超出时截断并标记 truncated=True。

    Args:
        code: 被测代码全文（AST 解析）。
        func_name: 目标函数名；None 时取第一个顶层函数。
        max_paths: 路径数上限（None 用默认 32）。

    Returns:
        {
          "func_name": str | None（代码不可解析时 None）,
          "paths": [ { "conditions": [str, ...], "branch_lines": [int, ...] } ... ],
          "total_paths": int（截断前理论路径数，即 paths 截断时已枚举到的上界）,
          "truncated": bool,
        }
        代码不可解析 / 无目标函数时 paths=[] 且 truncated=False（保守）。
    """
    limit = max_paths if max_paths is not None else _PATH_MAX_DEFAULT
    func_node = _function_node(code, func_name)
    if func_node is None:
        return {"func_name": func_name, "paths": [], "total_paths": 0, "truncated": False}
    paths: list[dict[str, Any]] = []
    # 用比 limit 多 1 探测是否截断（若实际路径数 > limit，paths 停在 limit，
    # 但需要知道"还有更多"）
    _walk_block_paths(list(func_node.body), [], [], paths, limit + 1)
    truncated = len(paths) > limit
    if truncated:
        paths = paths[:limit]
    return {
        "func_name": func_node.name,
        "paths": paths,
        "total_paths": len(paths),
        "truncated": truncated,
    }


def build_paths_prompt_section(paths_result: dict[str, Any] | None) -> str:
    """路径枚举结果 → prompt 注入段落（路径定向合成的提示基础）。

    与 build_cfg_prompt_section 同口径：None / 空路径 / 单一路径时返回空串
    （单一路径 = 无分支，注入无增量）。默认零行为变化（本段落由调用方在
    开关开启时拼接，见 planner/generator 的接线点）。
    """
    if not paths_result:
        return ""
    paths = paths_result.get("paths") or []
    if len(paths) <= 1:
        return ""
    lines: list[str] = []
    for i, p in enumerate(paths[:8], start=1):
        cond = " 且 ".join(p["conditions"]) if p["conditions"] else "（无条件，主路径）"
        lines.append(f"路径 {i}：{cond}")
    if paths_result.get("truncated"):
        lines.append(f"（…路径数超过 {len(paths)} 条，已截断，仅展示前 8 条）")
    return (
        f"\n【独立执行路径（结构接地·路径定向，共 {len(paths)} 条）】\n"
        + "\n".join(lines)
        + "\n请为上述每条路径生成对应测试用例，确保分支组合全覆盖（路径定向测试合成）。"
    )
