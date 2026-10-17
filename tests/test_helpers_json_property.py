#!/usr/bin/env python3
"""A-13（2026-10-17 独立评审）：helpers JSON 修复家族 + AST 补丁应用的
property-based 模糊测试（hypothesis）。

覆盖对象与不变式（均为**纯函数**、LLM 输出鲁棒性关键面）：

A. `extract_json_object` / `extract_json_array`（LLM 响应解析入口）：
   1. **异常纪律**：任意文本输入下，要么返回正确类型（dict/list），
      要么抛 `json.JSONDecodeError`——**不得抛其他类型异常**
      （TypeError/RecursionError/AttributeError 等都是缺陷）；
   2. **直通不变式**：对任意 JSON 可序列化对象，`json.dumps` 的文本
      经提取必得原对象（含 markdown 围栏包裹形态）；
   3. **数组/对象对称**：数组提取器不接受裸对象输入时按 JSONDecodeError
      或明确降级处理，不静默返回错类型。

B. `_repair_json_bounded` / `extract_code_block`：
   1. 任意字符串不抛异常、返回 str（修复器是纯文本变换）；
   2. 围栏代码块直通。

C. `replace_function_code`（AST 精确替换，补丁落地核心）：
   1. **无效新代码零伤害**：new code 语法错误 → `(source, False)` 且
      原码逐字节返回；
   2. **未命中零伤害**：函数名不存在 → `(source, False)`；
   3. **成功路径保结构**：替换成功 ⇒ 结果可解析、目标函数体已更新、
      其余顶层函数集合不变；
   4. **坏源失败有界**：源码头部损坏（前 N 行语法错误）时不得 panic
      （抛 SyntaxError 属文档化契约，本测试只锁定"其他函数不受影响"
      的成功路径不变式）。

hypothesis 为测试链依赖（缺失时整文件跳过，与 test_spec_expr_property 同口径）。
"""

from __future__ import annotations

import ast
import json
from typing import Any

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis 未安装（测试链依赖）")

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.tools.code_analyzer import replace_function_code  # noqa: E402
from src.utils.helpers import (  # noqa: E402
    _repair_json_bounded,
    extract_code_block,
    extract_json_array,
    extract_json_object,
)

# JSON 可序列化值策略（dict 键限 str——JSON 对象键恒为字符串）
_json_values: st.SearchStrategy[Any] = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=40),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=4),
    max_leaves=12,
)
_json_objects = st.dictionaries(st.text(max_size=10), _json_values, max_size=5)
_json_arrays = st.lists(_json_values, max_size=5)
# 对抗性文本：含括号/引号/围栏/截断 JSON 的杂烩
_hostile_text = st.one_of(
    st.text(max_size=120),
    st.builds(
        lambda a, b: f"{a}{b}",
        st.sampled_from(["{", "[", '"', "```json\n", "\n```", "}", "]", ","]),
        st.text(max_size=30),
    ),
    st.builds(lambda o, tail: json.dumps(o) + tail, _json_objects, st.sampled_from(["", " trailing", "}", "```"])),
)

_SETTINGS = settings(max_examples=300, deadline=None)


# ─── A. JSON 提取家族 ────────────────────────────────────────────────────


class TestExtractJsonFamily:
    @given(text=st.text(max_size=200))
    @settings(max_examples=400, deadline=None)
    def test_object_extraction_exception_discipline(self, text: str) -> None:
        """任意文本：dict 或 JSONDecodeError，不得其他异常。"""
        try:
            result = extract_json_object(text)
        except json.JSONDecodeError:
            return
        assert isinstance(result, dict)

    @given(text=st.text(max_size=200))
    @settings(max_examples=400, deadline=None)
    def test_array_extraction_exception_discipline(self, text: str) -> None:
        try:
            result = extract_json_array(text)
        except json.JSONDecodeError:
            return
        assert isinstance(result, list)

    @given(obj=_json_objects)
    @_SETTINGS
    def test_object_passthrough_plain(self, obj: dict[str, Any]) -> None:
        """直通：json.dumps(obj) 提取必得原对象。"""
        assert extract_json_object(json.dumps(obj)) == obj

    @given(obj=_json_objects)
    @_SETTINGS
    def test_object_passthrough_fenced(self, obj: dict[str, Any]) -> None:
        """markdown 围栏形态直通。"""
        fenced = f"```json\n{json.dumps(obj)}\n```"
        assert extract_json_object(fenced) == obj

    @given(arr=_json_arrays)
    @_SETTINGS
    def test_array_passthrough_plain(self, arr: list[Any]) -> None:
        assert extract_json_array(json.dumps(arr)) == arr

    @given(text=_hostile_text)
    @_SETTINGS
    def test_repair_bounded_never_raises(self, text: str) -> None:
        """修复器是纯文本变换：任意输入不抛异常、返回 str。"""
        out = _repair_json_bounded(text)
        assert isinstance(out, str)


# ─── B. 代码块提取 ───────────────────────────────────────────────────────


class TestExtractCodeBlock:
    @given(text=st.text(max_size=200))
    @settings(max_examples=300, deadline=None)
    def test_never_raises_and_returns_str(self, text: str) -> None:
        out = extract_code_block(text)
        assert isinstance(out, str)

    def test_fenced_passthrough(self) -> None:
        # 实现口径：围栏内容直通，尾部换行被 strip（raw 输入同口径）
        body = "def f():\n    return 1\n"
        assert extract_code_block(f"```python\n{body}```") == body.strip()
        assert extract_code_block(f"```\n{body}```") == body.strip()
        assert extract_code_block(body) == body.strip()


# ─── C. AST 函数替换 ─────────────────────────────────────────────────────

_SOURCE = '''"""module docstring"""


def alpha(x):
    return x + 1


def beta(y):
    return y * 2


class Holder:
    def method(self):
        return 0
'''

_NEW_ALPHA = '''def alpha(x):
    """replaced"""
    return x + 100
'''


def _top_level_function_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


class TestReplaceFunctionCode:
    def test_invalid_new_code_zero_harm(self) -> None:
        """新代码语法错误 → 原码逐字节返回 + False（零伤害锁定）。"""
        out, ok = replace_function_code(_SOURCE, "alpha", "def alpha(:\n    pass")
        assert ok is False
        assert out == _SOURCE

    def test_missing_function_zero_harm(self) -> None:
        out, ok = replace_function_code(_SOURCE, "nonexistent", _NEW_ALPHA)
        assert ok is False
        assert out == _SOURCE

    def test_success_preserves_structure(self) -> None:
        out, ok = replace_function_code(_SOURCE, "alpha", _NEW_ALPHA)
        assert ok is True
        ast.parse(out)  # 结果可解析
        # 目标函数体已更新
        assert extract_helper(out, "alpha") is not None
        assert "x + 100" in out
        # 其余顶层函数集合不变
        assert _top_level_function_names(out) == _top_level_function_names(_SOURCE)

    @given(new_body=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), max_size=20))
    @settings(max_examples=150, deadline=None)
    def test_arbitrary_new_body_never_panics(self, new_body: str) -> None:
        """任意新函数体文本：要么成功替换（结果可解析），要么零伤害回滚。"""
        new_code = f"def alpha(x):\n    return {new_body!r}\n"
        out, ok = replace_function_code(_SOURCE, "alpha", new_code)
        if ok:
            ast.parse(out)
            assert "alpha" in out
        else:
            assert out == _SOURCE

    def test_class_method_not_confused_with_top_level(self) -> None:
        """类内同名方法不得被顶层替换误伤（AST 边界纪律）。

        K 轮（2026-10-17）修复零断言违规（check_zero_assert_tests 门禁实证）：
        原用例只在 `if ok:` 分支里 `ast.parse(out)` 且无断言——实测 `method`
        不在顶层函数集合 → 替换被拒（ok=False）→ if 分支根本不执行，属
        "零断言测试"（对行为零校验却计入覆盖率）。现锁两条硬边界：
        拒绝路径必须**逐字节回滚**（零伤害），成功路径必须可解析；两条路径
        都断言"类内方法定义仍在"，防未来实现改为命中类内方法时误删方法。
        """
        out, ok = replace_function_code(_SOURCE, "method", _NEW_ALPHA.replace("alpha", "method"))
        if ok:
            assert ast.parse(out) is not None
        else:
            assert out == _SOURCE, "拒绝路径必须逐字节回滚（零伤害契约）"
        assert "def method(self):" in out, "类内方法定义不得被误删/改名"


def extract_helper(source: str, name: str) -> str | None:
    from src.tools.code_analyzer import extract_function_code

    return extract_function_code(source, name)
