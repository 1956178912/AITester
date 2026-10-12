"""P0-A-2（2026-10-12 独立评审落地）：规格优先生成（Spec-First Generation）。

背景（独立评审报告 §6 / 优化方案 P0-A，三源同向证据）：
    1. 项目自身阴性结果：plain_llm_df（检出优先协议）detection 44.8% vs
       aitester 完整编排 15.8%（−28pp）；48.6% 样本"全绿未检出"——
       根因是 Planner 读**缺陷代码**派生 expected_output，Generator 把
       实现行为当期望值（oracle-from-implementation），断言在 buggy 上
       全绿，检出被系统性抹掉；
    2. Zhao et al.（ISSTA 2026）misguidance effect：缺陷代码入提示会
       诱发"断言错误行为"的测试；
    3. Google Spec-Driven Test Generation（SpecOps '26）：生产代码上仅
       文档化前条件/后条件/未定义行为即 bug detection +9.8pp（p=0.0352）。

本模块实现 `DETECTION_SPEC_MODE=replace` 臂：Generator prompt 中的
"目标代码"块替换为**规约文档**（签名 + NL 规约 + SpecExpr 形式化子句 +
生成纪律）——LLM 只依据契约生成测试，接触不到实现细节，从源头切断
oracle-from-implementation 锚点。

设计口径（与 ADR-0003 一致：默认关，新开关独立）：
    - DETECTION_SPEC_MODE 缺省 "off"（历史口径：目标代码照常注入）；
    - "replace" 时仅当规约材料非空才替换（无材料 → 空串 → 调用方保持
      历史口径，不产出"无代码无规约"的空洞提示）；
    - 纯字符串渲染（零 LLM / 零子进程），失败路径保守返回空串；
    - 与 ORACLE_CONTEXT_MINIMAL 消融档同口径：minimal 时调用方不构建
      本段（该档意图是"无额外上下文"对照臂）。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_SPEC_MODE = "DETECTION_SPEC_MODE"
# 合法取值（其余值按 "off" 处理并记 warning——保守：不认识的模式不改行为）
_SPEC_MODES = ("off", "replace")


def detection_spec_mode() -> str:
    """规格优先模式开关（DETECTION_SPEC_MODE：off=历史口径 / replace=规约文档替代实现代码）。

    默认 "off"：Generator prompt 与历史逐字节一致。实验层显式设
    "replace" 启用 P0-A-2 对照臂（建议与 plain_llm_df 臂同基准跑
    3 种子，判据 McNemar p<0.01 且 δ≥+10pp）。
    """
    raw = (os.getenv(_ENV_SPEC_MODE, "off") or "off").strip().lower()
    if raw not in _SPEC_MODES:
        logger.warning("DETECTION_SPEC_MODE=%r 未识别（可选：off/replace），按 off 处理", raw)
        return "off"
    return raw


def _extract_signature_line(source_code: str, function_name: str) -> str:
    """从源码提取目标函数签名行（保守：失败 / 未找到 → 空串）。

    只取签名（不取函数体——replace 模式的全部意义就是不暴露实现）。
    标注类型注解（若有）一并保留：注解是规约信息而非实现细节。
    """
    if not source_code or not function_name:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return ""
    for node in tree.body:  # 顶层函数 + 顶层类的直接方法（与 extract_signature_params 同口径）
        target = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                    target = sub
                    break
        if target is None:
            continue
        prefix = "async def" if isinstance(target, ast.AsyncFunctionDef) else "def"
        try:
            args = ast.unparse(target.args)
        except Exception:  # pragma: no cover - unparse 失败保守降级
            return ""
        returns = f" -> {ast.unparse(target.returns)}" if target.returns is not None else ""
        return f"{prefix} {target.name}({args}){returns}"
    return ""


def _docstring_of(source_code: str, function_name: str) -> str:
    """提取目标函数 docstring（若有）——文档化契约是规格材料的一部分。"""
    if not source_code or not function_name:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return ""
    for node in tree.body:
        target = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                    target = sub
                    break
        if target is None:
            continue
        doc = ast.get_docstring(target)
        return (doc or "").strip()
    return ""


def _bullet_list(items: list[str], label: str) -> list[str]:
    """把一组规约子句渲染为 "- label：item" 行（空组不产行）。"""
    return [f"- {label}：{item}" for item in items if item and item.strip()]


def build_spec_replace_section(
    test_plan: dict[str, Any] | None,
    target_code: str,
    module_name: str = "",
    target_function: str = "",
) -> str:
    """渲染规格优先提示段（规约文档，替代目标代码注入 Generator prompt）。

    Args:
        test_plan: Planner 产出的测试计划（含 logic_analysis 的 NL 规约
            与 *_expr 形式化子句）；None / 无规约材料 → 空串。
        target_code: 被测源码（**只用于提取签名与 docstring**，函数体
            不进入产物——replace 模式的核心纪律）。
        module_name: 模块名（import 约束用）。
        target_function: 目标函数名（签名提取用；缺省时从 test_plan
            的 function_name 回退）。

    Returns:
        规格文档字符串；无任何规约材料时返回空串（调用方保持历史口径，
        即继续注入目标代码——不产出"无代码无规约"的空洞提示）。
    """
    if not isinstance(test_plan, dict):
        return ""
    fn = target_function or test_plan.get("function_name") or ""
    logic = test_plan.get("logic_analysis")
    logic = logic if isinstance(logic, dict) else {}

    # 规约材料三源：NL 通道 / SpecExpr 形式化通道 / 边界情况
    pre_nl = [str(c) for c in (logic.get("preconditions") or []) if str(c).strip()]
    post_nl = [str(c) for c in (logic.get("postconditions") or []) if str(c).strip()]
    inv_nl = [str(c) for c in (logic.get("invariants") or []) if str(c).strip()]
    edge = [str(c) for c in (logic.get("edge_cases") or []) if str(c).strip()]
    pre_expr = [str(c) for c in (logic.get("preconditions_expr") or []) if str(c).strip()]
    post_expr = [str(c) for c in (logic.get("postconditions_expr") or []) if str(c).strip()]
    inv_expr = [str(c) for c in (logic.get("invariants_expr") or []) if str(c).strip()]
    docstring = _docstring_of(target_code, fn)

    has_material = any([pre_nl, post_nl, inv_nl, edge, pre_expr, post_expr, inv_expr, docstring])
    if not has_material:
        return ""  # 无规约材料：调用方保持历史口径（注入目标代码）

    lines: list[str] = [
        "【规格优先模式（Spec-First）：本提示刻意不包含实现代码】",
        "请仅依据以下规约文档与函数签名生成测试。实现细节未知且**不得臆测**——",
        "照猜想中的实现行为写断言（oracle-from-implementation）会系统性抹掉缺陷检出，",
        "是本模式要杜绝的首要失败形态。",
        "",
    ]
    sig = _extract_signature_line(target_code, fn)
    if sig:
        lines.append(f"函数签名：{sig}")
    if module_name:
        lines.append(f"被测模块名：{module_name}（import 必须 `from {module_name} import ...`）")
    if docstring:
        lines.append("")
        lines.append("【文档化契约（docstring）】")
        lines.append(docstring)

    nl_lines: list[str] = []
    nl_lines.extend(_bullet_list(pre_nl, "前置条件"))
    nl_lines.extend(_bullet_list(post_nl, "后置条件"))
    nl_lines.extend(_bullet_list(inv_nl, "不变量"))
    nl_lines.extend(_bullet_list(edge, "边界情况"))
    if nl_lines:
        lines.append("")
        lines.append("【自然语言规约（期望值的唯一合法来源）】")
        lines.extend(nl_lines)

    expr_lines: list[str] = []
    expr_lines.extend(_bullet_list(pre_expr, "前置（可执行）"))
    expr_lines.extend(_bullet_list(post_expr, "后置（可执行）"))
    expr_lines.extend(_bullet_list(inv_expr, "不变量（可执行）"))
    if expr_lines:
        lines.append("")
        lines.append("【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】")
        lines.extend(expr_lines)

    lines.append("")
    lines.append("【生成纪律】")
    lines.append("1. 每个测试必须断言上述规约中可判定的性质（后置 / 不变量 / 边界）；")
    lines.append("2. 期望值只能来自规约与 docstring 约定；规约未覆盖的行为禁止臆造具体值——")
    lines.append("   改用记录实际行为的探索性断言并在 docstring 标注需人工确认；")
    lines.append("3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；")
    lines.append("4. 不得访问规约与签名之外的属性 / 符号。")
    return "\n".join(lines)


__all__ = [
    "build_spec_replace_section",
    "detection_spec_mode",
]
