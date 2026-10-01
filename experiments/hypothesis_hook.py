"""
N1（2026-09-29 审查 P2）：hypothesis 属性测试钩子（默认关）。

历史口径：LLM 生成的测试用例是"样本驱动"的（针对具体输入写具体期望），
边界/输入域覆盖依赖 O4 oracle_validator + M10 boundary_triplets（纯 AST），
无"属性测试"（property-based testing）维度——同一函数的"交换律 / 幂等性 /
不变量"等属性无系统生成。

本模块提供 hypothesis 集成钩子（`HYPOTHESIS_ENABLE=true` 时启用，
默认 false 保持历史样本驱动口径零变化）：

- `hypothesis_enabled()` — 开关判定（环境变量读取）。
- `build_property_prompt_section(function_name, signature, docstring)` —
  生成注入 Generator prompt 的属性测试指令片段（"请同时生成 1–2 条
  hypothesis 风格属性断言：不变量 + 边界"）。纯字符串，零 LLM 成本。
- `generate_property_test_stub(function_name, signature)` — 生成
  hypothesis 测试桩代码（`@given(st.from_type(...))` 骨架），
  供 LLM 在 prompt 引导下补全具体属性。

验收指标（N1）：HYPOTHESIS_ENABLE=true 时 LLM 生成的测试套件中
含 hypothesis 风格属性断言（import hypothesis + @given）的比例 ≥ 10%。
"""

from __future__ import annotations

import os

__all__ = [
    "build_property_prompt_section",
    "generate_property_test_stub",
    "hypothesis_enabled",
]


def hypothesis_enabled() -> bool:
    """N1 属性测试钩子开关（默认 false 保持历史样本驱动口径）。"""
    return os.getenv("HYPOTHESIS_ENABLE", "false").lower() in ("true", "1", "on")


def build_property_prompt_section(
    function_name: str,
    signature: str = "",
    docstring: str = "",
) -> str:
    """生成 hypothesis 属性测试指令片段（注入 Generator prompt 尾部）。

    Args:
        function_name: 被测函数名。
        signature: 函数签名（如 "x: int, y: int"）。
        docstring: 函数文档字符串（属性断言的语义来源）。

    Returns:
        prompt 注入文本（开关关闭时调用方不应调用本函数）。
    """
    parts = [
        "【N1 属性测试要求】（HYPOTHESIS_ENABLE=true）",
        f"针对函数 `{function_name}`{f'（{signature}）' if signature else ''}，",
        "请额外生成 1–2 条 hypothesis 风格属性断言：",
    ]
    if docstring:
        parts.append(f"  函数语义参考：{docstring.strip()[:200]}")
    parts.extend(
        [
            "  1. 不变量断言（invariant）：对任意合法输入，输出满足",
            "     由文档字符串 / 类型注解推导的不变量（如非负、有序、",
            "     自反性 x->f(x)==x 等）；",
            "  2. 边界/随机断言（boundary/randomized）：对 st.from_type(",
            "     参数类型) 生成的随机输入，断言函数不抛意外异常且",
            "     输出类型与签名一致。",
            "格式：import hypothesis.strategies as st; @given(st.integers()) ...",
        ]
    )
    return "\n".join(parts)


def generate_property_test_stub(
    function_name: str,
    signature: str = "",
) -> str:
    """生成 hypothesis 测试桩代码骨架（LLM 补全具体属性）。

    Args:
        function_name: 被测函数名。
        signature: 参数签名（如 "x: int, y: int"），用于 @given 装饰器。

    Returns:
        可直接插入测试文件的 Python 代码字符串（含 import + 桩函数）。
    """
    _params = signature.split(",") if signature else []
    _strategy_args = ", ".join(
        [f"st.from_type({p.split(':')[0].strip()})" for p in _params if ":" in p] or ["st.data()"]
    )
    _param_names = ", ".join([p.split(":")[0].strip() for p in _params]) or "data"
    _given_args = _strategy_args
    return (
        f"import hypothesis.strategies as st\n"
        f"from hypothesis import given, settings\n\n"
        f"@given({_given_args})\n"
        f"def test_{function_name}_property_invariant({_param_names}):\n"
        f'    """N1 属性测试桩：由 hypothesis 生成随机输入，断言不变量。"""\n'
        f"    result = {function_name}({_param_names})\n"
        f"    # TODO: 补充不变量断言（如 assert result >= 0 / assert 类型一致）\n"
        f"    assert result is not None or isinstance(result, (int, float, str, list, dict))\n"
    )
