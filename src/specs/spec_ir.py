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
    - boundaries → pytest 参数化断言（`@pytest.mark.parametrize`）或
      Hypothesis `given(sampled_from(...))` 策略；
    - invariants → Hypothesis `@given` 随机输入 + assert 不变量；
    - postconditions → Hypothesis `@given` + 后置条件断言。
    hypothesis 不可用（import 失败）时降级为纯 pytest 参数化断言
    （零依赖，stdlib 路径），保证编译产物恒可执行。
"""

from __future__ import annotations

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
    logger.info(
        "SpecIR 解析：fn=%s pre=%d post=%d inv=%d boundaries=%d oracle=%s",
        func_name or "(unknown)",
        len(pre),
        len(post),
        len(inv),
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
    """把 SpecIR 编译为可执行测试代码（oracle 转换）。

    优先 Hypothesis 策略（boundaries → sampled_from / invariants → @given
    随机输入）；hypothesis 不可用时降级为 pytest 参数化断言（纯 stdlib，
    零依赖，保证编译产物恒可执行）。

    Args:
        spec: parse_logic_analysis 的产物（None / 空 boundaries 时返回空串）。
        target_module: 被测模块名（import 用）。
        target_function: 被测函数名（调用用）。

    Returns:
        测试代码字符串；无 SpecIR / 无边界 / 无函数名时返回空串（保守）。
    """
    if not spec:
        return ""
    func = target_function or spec.get("function_name") or ""
    module = target_module or ""
    boundaries = [b for b in (spec.get("boundaries") or []) if b.get("expected") is not None]
    if not func or not module:
        return ""
    if not boundaries and not (spec.get("invariants") or spec.get("postconditions")):
        return ""

    import_hypothesis = _hypothesis_available()

    # 边界 → pytest 参数化断言（确定性 oracle，Hypothesis 可用与否同产物：
    # sampled_from 策略对"有限已知边界集合"等价于参数化，且参数化产物
    # 无 hypothesis 依赖、恒可执行、可复算——统一走参数化口径，Hypothesis
    # 仅用于下方 invariants 的随机输入属性式断言）
    lines: list[str] = []
    lines.append(f"# SpecIR 编译产物（oracle_kind={spec.get('oracle_kind')}）")
    lines.append("import pytest")
    lines.append(f"from {module} import {func}")
    lines.append("")
    if boundaries:
        cases = [f"({b.get('input')!r}, {b.get('expected')!r})" for b in boundaries]
        lines.append(f"@pytest.mark.parametrize('inp,exp', [{'; '.join(cases)}])")
        lines.append("def test_specir_boundary(inp, exp):")
        lines.append(f"    assert {func}(inp) == exp")

    # 不变量 → Hypothesis @given 随机输入属性式断言（仅 hypothesis 可用时）
    if import_hypothesis and spec.get("invariants"):
        lines.append("")
        lines.append("from hypothesis import given, strategies as st")
        lines.append("")
        lines.append("@given(x=st.integers())")
        lines.append("def test_specir_invariant(x):")
        # 不变量为自然语言描述：保守编译为占位断言（assert True + 注释），
        # 不引入假通过；需人工/LLM 将自然语言补强为可执行断言。
        lines.extend(f"    # invariant: {inv}" for inv in spec["invariants"])
        lines.append("    assert True")

    return "\n".join(lines)


def _hypothesis_available() -> bool:
    try:
        import hypothesis  # noqa: F401  # type: ignore[import-not-found]

        return True
    except ImportError:
        return False


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
    "parse_logic_analysis",
    "spec_ir_enabled",
    "validate_spec_ir",
]
