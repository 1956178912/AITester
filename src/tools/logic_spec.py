"""
M10（2026-09-29 审查 P0）：可检查规约——schema 强校验 + AST 边界三元组推导。

背景：
    "逻辑驱动"测试生成可静默退化为空规约（LLM 不输出 logic_analysis 时
    静默填 5 个空字段），"逻辑驱动"主张不可证伪。本模块提供两层配套：
    1. schema 强校验（validate_logic_spec）：对 Planner 输出的 logic_analysis
       做必填字段 + 类型 + 非空校验，校验失败时返回 findings（纯观测）；
       LOGIC_SPEC_STRICT_ENABLE=true（默认 false）时提升为 ValueError；
    2. AST 边界三元组推导（derive_boundary_triplets）：从被测代码的 AST
       分支条件确定性推导 (input, expected, rationale) 三元组，不依赖
       LLM，供 Generator prompt 注入"确定性边界锚点"（替代 LLM 自由
       发挥的边界值生成）。

设计口径（保守、零 LLM 成本、默认关）：
    - LOGIC_SPEC_STRICT_ENABLE=false（默认）时，本模块零行为变化：
      调用方（planner.py / nodes.py）按历史静默兜底口径执行；
    - 开启时，validate_logic_spec 在 Planner 输出后做 schema 校验，
      校验失败 → findings 非空 + logic_degraded=True（纯观测标记，
      供实验层"空值率 = 0"指标消费）；
    - derive_boundary_triplets 是纯 AST 静态分析（零 LLM 成本），
      提取 Compare / If / For 分支条件中的边界值（>= / <= / == / !=
      比较操作数的数值常量 / 字符串长度 / 容器长度），产出
      [(input, expected, rationale), ...] 三元组列表（最多
      BOUNDARY_TRIPLETS_MAX 条，默认 20，防 prompt 过长）。

消费方式：
    - Planner 节点：validate_logic_spec(test_plan["logic_analysis"])
      → findings 非空时把 findings 渲染为"规约缺陷清单"段落注入
      下一轮 Generator prompt（引导 LLM 补强逻辑分析）；
    - Generator 节点：derive_boundary_triplets(target_code)
      → 非空时把三元组渲染为"确定性边界锚点"段落注入 prompt
      （替代 LLM 自由生成的边界值，提升 boundary_shift 变异
      kill rate）。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_STRICT = "LOGIC_SPEC_STRICT_ENABLE"
_ENV_TRIPLETS_MAX = "BOUNDARY_TRIPLETS_MAX"
_DEFAULT_TRIPLETS_MAX = 20


def logic_spec_strict_enabled() -> bool:
    """M10 强校验开关（LOGIC_SPEC_STRICT_ENABLE=true 时启用，默认 false）。"""
    return os.getenv(_ENV_STRICT, "false").lower() in ("true", "1", "on")


def _triplets_max() -> int:
    """AST 边界三元组上限（BOUNDARY_TRIPLETS_MAX，默认 20）。"""
    try:
        return int(os.getenv(_ENV_TRIPLETS_MAX, str(_DEFAULT_TRIPLETS_MAX)))
    except ValueError:
        return _DEFAULT_TRIPLETS_MAX


# ─── 1. schema 强校验 ──────────────────────────────────────────────────────────


def validate_logic_spec(logic_analysis: dict[str, Any] | None) -> list[dict[str, Any]]:
    """对 Planner 输出的 logic_analysis 做 schema 强校验（纯数据，零 LLM 成本）。

    校验规则（保守口径，仅标记不阻断）：
    - logic_analysis 为 None / 空 dict → finding "missing"；
    - 必填字段缺失（input_domain / output_domain / preconditions /
      postconditions / edge_cases）→ finding "missing_field"；
    - 必填字段值为空串 / 空列表 → finding "empty_field"；
    - preconditions / postconditions / edge_cases 非列表类型 → finding
      "wrong_type"。

    Args:
        logic_analysis: Planner 输出的 logic_analysis 字典（可为 None）。

    Returns:
        findings 列表（空 = 校验通过；非空 = 存在 schema 缺陷）。
        每项含 {"type": str, "field": str, "message": str}。
    """
    findings: list[dict[str, Any]] = []
    if logic_analysis is None:
        findings.append({"type": "missing", "field": "logic_analysis", "message": "logic_analysis 整体缺失"})
        return findings
    if not isinstance(logic_analysis, dict) or not logic_analysis:
        findings.append({"type": "missing", "field": "logic_analysis", "message": "logic_analysis 为空或非 dict"})
        return findings

    # 必填字段及其期望类型
    required_str_fields = ("input_domain", "output_domain")
    required_list_fields = ("preconditions", "postconditions", "edge_cases")

    for field in required_str_fields:
        if field not in logic_analysis:
            findings.append({"type": "missing_field", "field": field, "message": f"必填字段 {field} 缺失"})
        elif not isinstance(logic_analysis[field], str) or not logic_analysis[field].strip():
            findings.append({"type": "empty_field", "field": field, "message": f"字段 {field} 为空串或非 str"})

    for field in required_list_fields:
        if field not in logic_analysis:
            findings.append({"type": "missing_field", "field": field, "message": f"必填字段 {field} 缺失"})
        elif not isinstance(logic_analysis[field], list):
            findings.append({"type": "wrong_type", "field": field, "message": f"字段 {field} 非 list 类型"})
        elif len(logic_analysis[field]) == 0:
            findings.append({"type": "empty_field", "field": field, "message": f"字段 {field} 为空列表"})

    return findings


def build_logic_spec_findings_section(findings: list[dict[str, Any]] | None) -> str:
    """把 schema 校验 findings 渲染为 prompt 注入段落（空时返回空串）。"""
    if not findings:
        return ""
    lines = [f"【规约缺陷清单（M10 schema 校验，共 {len(findings)} 条）】"]
    for i, f in enumerate(findings[:10], start=1):
        lines.append(f"{i}. [{f.get('type', '?')}] {f.get('field', '?')}: {f.get('message', '')}")
    lines.append(
        "请在下一轮测试生成中补强逻辑分析（非空 input_domain / output_domain / preconditions / postconditions / edge_cases）。"
    )
    return "\n".join(lines)


# ─── 2. AST 边界三元组推导 ───────────────────────────────────────────────────


def derive_boundary_triplets(
    target_code: str,
    focus_function: str | None = None,
    max_triplets: int | None = None,
) -> list[dict[str, Any]]:
    """从被测代码 AST 分支条件确定性推导边界三元组（零 LLM 成本）。

    提取规则（保守、高召回低误伤）：
    - Compare 节点（>= / <= / == / != / < / >）：操作数为数值常量时
      产出 (input=常量±1, expected=比较结果翻转, rationale=行号+运算符)；
      操作数为 len(x) 调用时产出 (input=x 长度边界, expected=...,
      rationale=...)；
    - If / While 条件中的 BoolOp（and/or）：子条件递归处理；
    - 仅提取 focus_function 内的分支（focus_function 非 None 时），
      否则全文件提取（防 prompt 过长，截断到 max_triplets 条）。

    Args:
        target_code: 被测代码全文。
        focus_function: 焦点函数名（None = 全文件）。
        max_triplets: 三元组上限（None = 读环境变量 BOUNDARY_TRIPLETS_MAX，
            默认 20）。

    Returns:
        [{"input": int|float|str, "expected": str, "rationale": str, "line": int}, ...]
        input 为类型化数值（P0：比较常量 ±1 直接产出 int/float，不产数字
        字符串——下游 SpecIR v2 字面量绑定需要真实类型）；空列表 = 无边界
        条件可推导 / target_code 为空 / 语法错误。
    """
    if not target_code or not target_code.strip():
        return []
    if max_triplets is None:
        max_triplets = _triplets_max()
    if max_triplets <= 0:
        return []

    try:
        tree = ast.parse(target_code)
    except (SyntaxError, ValueError):
        logger.debug("M10 AST 边界三元组推导降级：语法解析失败")
        return []

    # 如果指定了焦点函数，仅提取该函数内的节点
    target_funcs: set[str] | None = {focus_function} if focus_function else None

    triplets: list[dict[str, Any]] = []

    # M10：预扫描所有 FunctionDef/AsyncFunctionDef，缓存 (name, start_line,
    # end_line) 区间，用于 _is_in_focus 的"节点在 focus_function 子树内"
    # 判定（避免每节点走 ast.walk 全树 O(N²) 开销）。
    _func_ranges: list[tuple[str, int, int]] = []
    if target_funcs is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _func_ranges.extend([(node.name, getattr(node, "lineno", 0), getattr(node, "end_lineno", 0))])

    def _is_in_focus(node: ast.AST) -> bool:
        if target_funcs is None:
            return True
        node_lineno = getattr(node, "lineno", 0)
        return any(name in target_funcs and start <= node_lineno <= (end or start) for name, start, end in _func_ranges)

    _seen_lines: set[int] = set()  # M10：去重——If.test 与 Compare 同节点，仅保留首条

    for node in ast.walk(tree):
        if not _is_in_focus(node):
            continue
        if isinstance(node, ast.Compare):
            _node_line = getattr(node, "lineno", 0)
            if _node_line in _seen_lines:
                continue
            triplet = _extract_compare_triplet(node)
            if triplet:
                _seen_lines.add(_node_line)
                triplets.append(triplet)
                if len(triplets) >= max_triplets:
                    break
        elif isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            _node_line = getattr(node, "lineno", 0)
            if _node_line in _seen_lines:
                continue
            triplet = _extract_compare_triplet(node.test)
            if triplet:
                _seen_lines.add(_node_line)
                triplets.append(triplet)
                if len(triplets) >= max_triplets:
                    break

    if triplets:
        logger.info(
            "M10 AST 边界三元组推导：%d 条（focus_function=%s, max=%d）",
            len(triplets),
            focus_function,
            max_triplets,
        )
    return triplets


def _extract_compare_triplet(node: ast.Compare) -> dict[str, Any] | None:
    """从单个 Compare 节点提取边界三元组（非 Compare / 无常量操作数时返回 None）。"""
    if not isinstance(node, ast.Compare):
        return None
    # 仅处理单操作符比较（a < b, a >= c 等；a < b < c 链式比较跳过）
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return None
    op = node.ops[0]
    comparator = node.comparators[0]
    left = node.left

    # 提取数值常量操作数（左或右）
    const_val = _extract_numeric_const(comparator)
    if const_val is None:
        const_val = _extract_numeric_const(left)
        if const_val is None:
            return None

    # 根据运算符推导边界输入（P0：input 产出类型化数值而非数字字符串——
    # 字符串型 input 流入 SpecIR v2 编译会被绑定为 str 字面量，int 型被测
    # 函数运行期 TypeError，"确定性检出"变假检出；prompt 渲染 f-string
    # 对 int/float 与等值字符串输出一致，不影响注入段落）
    op_name = _op_name(op)
    if isinstance(op, ast.GtE):  # x >= N → 边界输入 N-1（不满足）/ N（满足）
        input_val: Any = const_val - 1
        expected = f"< {const_val}（不满足）/ = {const_val}（满足）"
    elif isinstance(op, ast.LtE):  # x <= N → 边界输入 N+1（不满足）/ N（满足）
        input_val = const_val + 1
        expected = f"> {const_val}（不满足）/ = {const_val}（满足）"
    elif isinstance(op, ast.Eq):  # x == N → 边界输入 N（满足）/ N±1（不满足）
        input_val = const_val
        expected = f"= {const_val}（满足）/ ≠ {const_val}（不满足）"
    elif isinstance(op, ast.NotEq):  # x != N → 边界输入 N（不满足）/ N±1（满足）
        input_val = const_val
        expected = f"= {const_val}（不满足）/ ≠ {const_val}（满足）"
    elif isinstance(op, ast.Gt):  # x > N → 边界输入 N（不满足）/ N+1（满足）
        input_val = const_val + 1
        expected = f"= {const_val}（不满足）/ > {const_val}（满足）"
    elif isinstance(op, ast.Lt):  # x < N → 边界输入 N（不满足）/ N-1（满足）
        input_val = const_val - 1
        expected = f"= {const_val}（不满足）/ < {const_val}（满足）"
    else:  # In / NotIn（容器成员）
        input_val = const_val
        expected = "在容器内（满足）/ 不在容器内（不满足）"

    return {
        "input": input_val,
        "expected": expected,
        "rationale": f"第 {node.lineno} 行：{op_name} 比较（常量 {const_val}）",
        "line": node.lineno,
    }


def _extract_numeric_const(node: ast.AST) -> float | int | None:
    """提取节点的值（数值常量时返回 int/float，否则 None）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    # -1 等负数常量：UnaryOp(USub, Constant(1))
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -node.operand.value
    return None


def _op_name(op: ast.AST) -> str:
    """把 AST 运算符节点映射为可读字符串。"""
    if isinstance(op, ast.Gt):
        return ">"
    if isinstance(op, ast.GtE):
        return ">="
    if isinstance(op, ast.Lt):
        return "<"
    if isinstance(op, ast.LtE):
        return "<="
    if isinstance(op, ast.Eq):
        return "=="
    if isinstance(op, ast.NotEq):
        return "!="
    if isinstance(op, ast.In):
        return "in"
    if isinstance(op, ast.NotIn):
        return "not in"
    return "?"


def build_boundary_triplets_section(
    triplets: list[dict[str, Any]] | None,
) -> str:
    """把 AST 边界三元组渲染为 Generator prompt 注入段落（空时返回空串）。"""
    if not triplets:
        return ""
    lines = [f"【确定性边界锚点（M10 AST 推导，共 {len(triplets)} 条）】"]
    for i, t in enumerate(triplets[:15], start=1):
        lines.append(f"{i}. 输入 {t.get('input')} → 预期 {t.get('expected')}（{t.get('rationale', '')}）")
    lines.append("请优先使用上述确定性边界值作为测试输入，提升 boundary_shift 变异 kill rate。")
    return "\n".join(lines)


__all__ = [
    "build_boundary_triplets_section",
    "build_logic_spec_findings_section",
    "derive_boundary_triplets",
    "logic_spec_strict_enabled",
    "validate_logic_spec",
]
