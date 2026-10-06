"""SpecIR 核心实现（R7，2026-09-30 独立审查 P0）。

SpecIR（Specification Intermediate Representation）把自然语言
`logic_analysis` 规约解析为受限的机器可执行 IR，并编译为
Hypothesis 属性策略 / pytest 参数化断言（确定性 oracle）。

SpecIR 结构（JSON Schema 描述）：
    {
      "schema_version": "1",
      "source": "docstring" | "type" | "logic_analysis" | "handwritten",
      "function_name": str,
      "preconditions":  [str, ...],   # 前置条件（输入约束）
      "postconditions": [str, ...],   # 后置条件（输出约束）
      "invariants":     [str, ...],   # 不变量（任意时刻成立）
      "boundaries": [                   # 确定性边界锚点
          {"input": Any, "expected": Any, "rationale": str}, ...
      ],
      "oracle_kind": "boundary" | "invariant" | "postcondition"
    }

可执行化（compile）：
    - boundaries → pytest 参数化断言（`@pytest.mark.parametrize`），
      确定性 oracle、零非标准库依赖、产物恒可执行；
    - pre/post/invariant 为自然语言，本层不生成测试（R1a 2026-10-05
      修复：历史版本对 invariants 产出 `assert True` 占位断言——恒真
      断言即假通过通道，已移除）；表达式形态子句由 v2 DSL
      （spec_ir_v2.compile_spec_oracle）编译为可执行断言，
      绑定上下文经 extract_signature_params（R1b）按函数签名扩展。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "SPEC_IR_ENABLE"
_SCHEMA_VERSION = "1"

# 边界三元组上限（与 logic_spec.derive_boundary_triplets 同口径，防 prompt 过长）
_DEFAULT_BOUNDARIES_MAX = 20
_ENV_BOUNDARIES_MAX = "SPEC_IR_BOUNDARIES_MAX"


def spec_ir_enabled() -> bool:
    """SpecIR 开关（SPEC_IR_ENABLE=true 时启用，默认 false 保持历史口径）。

    默认关闭：logic_analysis 解析 / 编译产物为"追加字段"，开启后
    Planner → Generator 主链路零变化（与 ADR-0003 默认关口径一致）。
    """
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def _boundaries_max() -> int:
    try:
        return int(os.getenv(_ENV_BOUNDARIES_MAX, str(_DEFAULT_BOUNDARIES_MAX)))
    except ValueError:
        return _DEFAULT_BOUNDARIES_MAX


def parse_logic_analysis(
    logic_analysis: dict[str, Any] | None,
    boundary_triplets: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """把 Planner 的 logic_analysis（自然语言字段）+ 确定性边界三元组
    解析为 SpecIR 字典。

    Args:
        logic_analysis: Planner 输出的 logic_analysis dict（input_domain /
            output_domain / preconditions / postconditions / edge_cases 等
            自然语言字段，缺失/空 dict 时返回 None——保守降级）。
        boundary_triplets: logic_spec.derive_boundary_triplets 的产物
            [(input, expected, rationale), ...]（AST 确定性推导，非 LLM），
            映射为 SpecIR 的 boundaries 数组（机器可执行边界锚点）。

    Returns:
        SpecIR 字典；logic_analysis 为空 / 无任何规约材料时返回 None。
    """
    if not logic_analysis or not isinstance(logic_analysis, dict):
        return None
    # 兼容多种字段名（Planner prompt 的历史 + 新版字段）
    func_name = (
        logic_analysis.get("function_name")
        or logic_analysis.get("target_function")
        or logic_analysis.get("function")
        or ""
    )
    pre = _as_str_list(logic_analysis.get("preconditions") or logic_analysis.get("pre_conditions"))
    post = _as_str_list(logic_analysis.get("postconditions") or logic_analysis.get("post_conditions"))
    inv = _as_str_list(
        logic_analysis.get("invariants") or logic_analysis.get("invariant") or logic_analysis.get("invariants_list")
    )
    # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道字段透传——
    # SPEC_EXPR_CONTRACT_SECTION（prompt 契约段）要求 LLM 在 NL 子句之外
    # 并行输出可机器执行的 *_expr 子句；此处原样带入 SpecIR，由
    # spec_ir_v2.compile_readiness 分通道计率（expr 通道 ASCII 白名单 +
    # ast 判定，NL 通道维持历史保守口径）。
    pre_expr = _as_str_list(logic_analysis.get("preconditions_expr"))
    post_expr = _as_str_list(logic_analysis.get("postconditions_expr"))
    inv_expr = _as_str_list(logic_analysis.get("invariants_expr"))
    # 规约来源：docstring 驱动（LLM 从 docstring 抽取）vs 手写
    source = logic_analysis.get("spec_source") or ("docstring" if func_name else "logic_analysis")

    # 边界三元组（确定性锚点）：(input, expected, rationale) → SpecIR boundaries
    boundaries: list[dict[str, Any]] = []
    if boundary_triplets:
        for t in boundary_triplets[: _boundaries_max()]:
            if isinstance(t, dict):
                boundaries.append(
                    {
                        "input": t.get("input"),
                        "expected": t.get("expected"),
                        "rationale": t.get("rationale", ""),
                    }
                )
            elif isinstance(t, (list, tuple)) and len(t) >= 2:
                boundaries.append(
                    {
                        "input": t[0],
                        "expected": t[1],
                        "rationale": str(t[2]) if len(t) > 2 else "",
                    }
                )
    # 若 logic_analysis 的 edge_cases 含结构化边界（dict 带 input/expected），
    # 也映射进 boundaries（自然语言 edge 已归一为 str，结构化边界从原始值抽取——
    # _as_str_list 会把 dict 包成 str，丢失结构）
    _raw_edges = logic_analysis.get("edge_cases")
    _structured_edges = _raw_edges if isinstance(_raw_edges, list) else []
    boundaries.extend(
        {
            "input": e.get("input"),
            "expected": e.get("expected"),
            "rationale": e.get("rationale", ""),
        }
        for e in _structured_edges
        if isinstance(e, dict) and ("input" in e or "expected" in e)
    )

    # 保守：无任何规约材料（无前置/后置/不变量/边界/函数名）时返回 None
    if not (pre or post or inv or boundaries or func_name):
        return None

    spec: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "source": source,
        "function_name": func_name,
        "preconditions": pre,
        "postconditions": post,
        "invariants": inv,
        "boundaries": boundaries,
        "oracle_kind": _infer_oracle_kind(pre, post, inv, boundaries),
    }
    # AC1：表达式通道字段（非空才写键——历史 spec 无该键，消费方按缺省
    # 空列表处理，schema 向后兼容）
    if pre_expr:
        spec["preconditions_expr"] = pre_expr
    if post_expr:
        spec["postconditions_expr"] = post_expr
    if inv_expr:
        spec["invariants_expr"] = inv_expr
    logger.info(
        "SpecIR 解析：fn=%s pre=%d post=%d inv=%d expr(pre/post/inv)=%d/%d/%d boundaries=%d oracle=%s",
        func_name or "(unknown)",
        len(pre),
        len(post),
        len(inv),
        len(pre_expr),
        len(post_expr),
        len(inv_expr),
        len(boundaries),
        spec["oracle_kind"],
    )
    return spec


def validate_spec_ir(spec: dict[str, Any] | None) -> list[str]:
    """SpecIR schema 强校验（纯观测，返回 findings 列表；空 spec 返回 ["empty_spec"]）。

    校验口径（与 logic_spec.validate_logic_spec 同构）：
    - schema_version 缺失/非 "1" → finding；
    - function_name 空 → finding（无目标函数无法编译 oracle）；
    - boundaries 条目缺 input/expected → finding；
    - oracle_kind 不在枚举内 → finding。
    全部通过时返回空列表（零 findings）。
    """
    if not spec:
        return ["empty_spec"]
    findings: list[str] = []
    if spec.get("schema_version") != _SCHEMA_VERSION:
        findings.append(f"schema_version_invalid:{spec.get('schema_version')}")
    if not spec.get("function_name"):
        findings.append("function_name_missing")
    for i, b in enumerate(spec.get("boundaries") or []):
        if "input" not in b or "expected" not in b:
            findings.append(f"boundary_{i}_missing_input_or_expected")
    valid_kinds = ("boundary", "invariant", "postcondition")
    if spec.get("oracle_kind") not in valid_kinds:
        findings.append(f"oracle_kind_invalid:{spec.get('oracle_kind')}")
    return findings


def _infer_oracle_kind(pre: list[str], post: list[str], inv: list[str], boundaries: list[dict[str, Any]]) -> str:
    """按规约材料丰富度推断主要 oracle 类型（保守：boundary 优先）。"""
    if boundaries:
        return "boundary"
    if inv:
        return "invariant"
    if post:
        return "postcondition"
    return "boundary"


def compile_to_hypothesis(
    spec: dict[str, Any] | None,
    target_module: str = "",
    target_function: str = "",
) -> str:
    """把 SpecIR 的 boundaries 编译为可执行 pytest 参数化断言（oracle 转换）。

    R1a（2026-10-05 审查 P0 修复）后的口径：
    - 仅 boundaries（确定性边界锚点）可机器化 → pytest 参数化断言
      （无 hypothesis 依赖、恒可执行、可复算）；
    - pre/post/invariant 为自然语言，本层**不**生成任何测试函数
      （历史版本对 invariants 产出 `assert True` 占位——恒真断言即
      oracle_validator 识别的假通过模式，已移除）；表达式形态子句的
      可执行编译由 v2 DSL 层（spec_ir_v2.compile_spec_oracle）承担。

    Args:
        spec: parse_logic_analysis 的产物（None / 空 boundaries 时返回空串）。
        target_module: 被测模块名（import 用）。
        target_function: 被测函数名（调用用）。

    Returns:
        测试代码字符串；无 SpecIR / 无边界 / 无函数名 / 无模块名时
        返回空串（保守——不产出无断言的空测试文件）。
    """
    if not spec:
        return ""
    func = target_function or spec.get("function_name") or ""
    module = target_module or ""
    boundaries = [b for b in (spec.get("boundaries") or []) if b.get("expected") is not None]
    if not func or not module:
        return ""
    if not boundaries:
        # NL pre/post/invariant 无法机器化（v2 DSL 层负责表达式子句），
        # 无 boundaries 即无可执行断言材料 → 保守返回空串
        return ""

    # R1a（2026-10-05 审查 P0 修复）：两处编译缺陷——
    # ① 参数化列表此前用 `'; '.join(cases)` 拼接，≥2 条边界时产物为
    #   `[(a, b); (c, d)]`（SyntaxError，Python 列表字面量不接受分号），
    #   改为 `', '.join`；
    # ② invariants（自然语言）此前编译为 `@given` + `assert True` 占位——
    #   恒真断言正是 oracle_validator 识别的假通过模式（v1 自己产出假通过
    #   通道）。修复口径：NL 不变量不可机器化 → 只产出注释，不生成任何
    #   测试函数；可机器化的表达式子句由 v2 DSL（spec_ir_v2）负责编译。
    #   因此本函数现只编译 boundaries 参数化断言；无 boundaries 时返回
    #   空串（不产出"只有 import 无断言"的空测试文件）。
    if not boundaries:
        return ""

    lines: list[str] = []
    lines.append(f"# SpecIR 编译产物（oracle_kind={spec.get('oracle_kind')}）")
    lines.append("import pytest")
    lines.append(f"from {module} import {func}")
    lines.append("")
    cases = [f"({b.get('input')!r}, {b.get('expected')!r})" for b in boundaries]
    lines.append(f"@pytest.mark.parametrize('inp,exp', [{', '.join(cases)}])")
    lines.append("def test_specir_boundary(inp, exp):")
    lines.append(f"    assert {func}(inp) == exp")

    # NL 不变量溯源注释（不生成测试函数——杜绝 v1 历史的 assert True 假通过）
    if spec.get("invariants"):
        lines.append("")
        lines.extend(f"# invariant（未机器化，见 spec_ir_v2 DSL 层）: {inv}" for inv in spec["invariants"])

    return "\n".join(lines)


def _hypothesis_available() -> bool:
    """hypothesis 可用性探测（R1a 后编译产物不再依赖 hypothesis，仅保留探测）。

    用途：实验层若需评估"hypothesis 可用环境占比"仍可调用；主编译路径
    （compile_to_hypothesis）已与 hypothesis 解耦（纯 pytest 参数化口径）。
    """
    try:
        import hypothesis  # noqa: F401  # type: ignore[import-not-found]

        return True
    except ImportError:
        return False


def extract_signature_params(
    source_code: str,
    function_name: str,
) -> list[str] | None:
    """从源码提取目标函数的参数名列表（R1b，签名感知绑定的材料源）。

    用途：spec_ir_v2.compile_spec_oracle 的绑定上下文（known_names）
    此前硬编码 {r,x,a,b,y}，多参数 / 关键字参数 / 自定义参数名函数的
    规约子句一律不可编译（审查 R6）；本函数从被测函数 AST 签名提取
    真实参数名，供编译层按签名动态扩展绑定集合。

    口径（保守）：
    - 排除 *args / **kwargs（规约子句不应引用可变参数）与约定俗成的
      self / cls（方法场景首个参数）；
    - 搜索范围：顶层函数定义 + 顶层类的直接方法（嵌套函数不参与）；
    - 返回 None 的三种情况（调用方降级回默认绑定集合 {r,x,a,b,y}，
      行为不变）：function_name 缺失 / 源码解析失败 / 未找到目标函数；
    - 返回 [] 表示"签名已知且无参数"（0 参函数——与"未找到"的 None
      显式区分，编译层走 0 参保守分支）。
    """
    if not source_code or not function_name:
        return None
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return None

    def _params_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        params: list[str] = []
        args = node.args
        positional = list(args.posonlyargs) + list(args.args)
        for p in positional:
            if p.arg in ("self", "cls") and not params:
                continue  # 方法首参（self/cls）不是规约绑定变量
            params.append(p.arg)
        params.extend(p.arg for p in args.kwonlyargs)
        # vararg/kwarg 不纳入：规约子句引用 *args/**kwargs 无法静态绑定
        return params

    for node in tree.body:  # 顶层函数 + 顶层类的直接方法（嵌套不参与）
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return _params_of(node)
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                    return _params_of(sub)
    return None


def _as_str_list(value: Any) -> list[str]:
    """把 dict/list/str 字段归一为 list[str]（保守：非 list 时包一层）。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, dict):
        return [str(v) for v in value.values() if str(v).strip()]
    return [str(value)] if str(value).strip() else []


__all__ = [
    "compile_to_hypothesis",
    "extract_signature_params",
    "parse_logic_analysis",
    "spec_ir_enabled",
    "validate_spec_ir",
]
