"""M10 边界三元组 / 类型推断私有纯函数分支补测（2026-10-02 审查）。

背景：`tools/logic_spec.py`（`_extract_compare_triplet` / `_op_name` /
`_extract_numeric_const` / `_is_in_focus`）与 `tools/type_repair.py`
（`_infer_literal_type`）均为多分支纯函数，但既有测试只覆盖主路径，
coverage.xml 显示两文件合计约 30 个分支未覆盖。本文件逐一补测
分支矩阵（比较运算符全集 / 负常量 / 非常量 / 焦点过滤 / 字面量类型集），
零 subprocess、零 LLM，CI 稳定。
"""

from __future__ import annotations

import ast

import pytest

from src.tools.logic_spec import (
    _extract_compare_triplet,
    _extract_numeric_const,
    _op_name,
    derive_boundary_triplets,
)
from src.tools.type_repair import _infer_literal_type


def _compare(code: str) -> ast.Compare:
    """从单行表达式提取 Compare 节点。"""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            return node
    raise AssertionError(f"表达式 {code!r} 无 Compare 节点")


def _triplet(code: str) -> dict | None:
    return _extract_compare_triplet(_compare(code))


@pytest.mark.unit
class TestExtractCompareTriplet:
    """_extract_compare_triplet 运算符矩阵与常量位置。"""

    @pytest.mark.parametrize(
        ("expr", "expected_input"),
        [
            ("x >= 10", "9"),  # GtE → N-1
            ("x <= 10", "11"),  # LtE → N+1
            ("x == 10", "10"),  # Eq → N
            ("x != 10", "10"),  # NotEq → N
            ("x > 10", "11"),  # Gt → N+1
            ("x < 10", "9"),  # Lt → N-1
        ],
    )
    def test_operator_inputs(self, expr, expected_input):
        t = _triplet(expr)
        assert t is not None, f"{expr} 应提取成功"
        assert t["input"] == expected_input

    def test_constant_on_left(self):
        """常量在左侧（10 < x）→ 从 left 提取常量（comparator 无常量时回退）。"""
        t = _triplet("10 < x")
        assert t is not None
        # Lt 分支：input = const-1 = 9（常量 10 从 left 提取成功）
        assert t["input"] == "9"
        assert "10" in t["expected"]

    def test_negative_constant(self):
        """-1 负常量：UnaryOp(USub, Constant) 路径。"""
        t = _triplet("x >= -1")
        assert t is not None
        assert t["input"] == "-2"  # -1 - 1

    def test_float_constant(self):
        t = _triplet("x > 0.5")
        assert t is not None
        assert "1.5" in t["input"] or "0.5" in t["input"]

    def test_non_compare_returns_none(self):
        """非 Compare 节点 → None（类型守卫）。"""
        assert _extract_compare_triplet(ast.parse("f(1)").body[0].value) is None  # type: ignore[arg-type]

    def test_chained_compare_returns_none(self):
        """链式比较（a < b < c）多操作符 → None。"""
        assert _extract_compare_triplet(_compare("1 < x < 3")) is None

    def test_no_numeric_const_returns_none(self):
        """两侧均非数值常量（x == y）→ None。"""
        assert _triplet("x == y") is None

    def test_in_operator_else_branch(self):
        """In/NotIn → else 分支（容器成员口径；常量须在左侧否则提前 None）。"""
        t = _triplet("1 in x")
        assert t is not None
        assert "容器" in t["expected"]

    def test_notin_operator_else_branch(self):
        t = _triplet("1 not in x")
        assert t is not None
        assert "容器" in t["expected"]


@pytest.mark.unit
class TestExtractNumericConst:
    """_extract_numeric_const 常量提取矩阵。"""

    def _const(self, expr: str):
        return _extract_numeric_const(ast.parse(expr).body[0].value)  # type: ignore[attr-defined]

    def test_int(self):
        assert self._const("42") == 42

    def test_float(self):
        assert self._const("3.14") == 3.14

    def test_bool_is_int_subclass_path(self):
        # bool 是 int 子类 → isinstance(v, (int, float)) 命中（返回 True/1）
        assert self._const("True") in (True, 1)

    def test_negative(self):
        assert self._const("-7") == -7

    def test_negative_float(self):
        assert self._const("-2.5") == -2.5

    def test_str_returns_none(self):
        assert self._const('"abc"') is None

    def test_name_returns_none(self):
        assert self._const("some_var") is None

    def test_call_returns_none(self):
        assert self._const("len(x)") is None

    def test_double_negation(self):
        # UnaryOp(USub, UnaryOp(...))：operand 非 Constant → None（保守）
        assert self._const("--7") is None or self._const("--7") == 7


@pytest.mark.unit
class TestOpName:
    """_op_name 运算符 → 可读字符串映射（全分支）。"""

    @pytest.mark.parametrize(
        ("expr", "name"),
        [
            ("a > b", ">"),
            ("a >= b", ">="),
            ("a < b", "<"),
            ("a <= b", "<="),
            ("a == b", "=="),
            ("a != b", "!="),
            ("a in b", "in"),
            ("a not in b", "not in"),
        ],
    )
    def test_all_known_ops(self, expr, name):
        cmp = _compare(expr)
        assert _op_name(cmp.ops[0]) == name

    def test_unknown_op_returns_question(self):
        """is 运算符不在映射表 → '?' 兜底分支。"""
        cmp = _compare("a is b")
        assert _op_name(cmp.ops[0]) == "?"


@pytest.mark.unit
class TestDeriveBoundaryTripletsFocus:
    """derive_boundary_triplets 焦点过滤与边界。"""

    CODE = (
        "def alpha(x):\n"
        "    if x >= 10:\n"
        "        return 1\n"
        "    return 0\n"
        "\n"
        "def beta(y):\n"
        "    if y <= 5:\n"
        "        return 2\n"
        "    return 3\n"
    )

    def test_focus_alpha_excludes_beta(self):
        out = derive_boundary_triplets(self.CODE, focus_function="alpha")
        assert out, "alpha 内比较应提取"
        assert all(t["line"] <= 4 for t in out), f"越界焦点: {out}"

    def test_focus_beta_only(self):
        out = derive_boundary_triplets(self.CODE, focus_function="beta")
        assert out
        assert all(t["line"] > 4 for t in out)

    def test_focus_nonexistent_function_returns_empty(self):
        out = derive_boundary_triplets(self.CODE, focus_function="nonexistent")
        assert out == []

    def test_no_focus_full_file(self):
        out = derive_boundary_triplets(self.CODE, focus_function=None)
        assert len(out) >= 2

    def test_zero_max_triplets_returns_empty(self):
        assert derive_boundary_triplets(self.CODE, max_triplets=0) == []

    def test_negative_max_triplets_returns_empty(self):
        assert derive_boundary_triplets(self.CODE, max_triplets=-5) == []

    def test_max_triplets_caps_output(self):
        out = derive_boundary_triplets(self.CODE, focus_function=None, max_triplets=1)
        assert len(out) == 1

    def test_empty_code(self):
        assert derive_boundary_triplets("") == []
        assert derive_boundary_triplets("   ") == []

    def test_syntax_error_returns_empty(self):
        assert derive_boundary_triplets("def broken(:\n") == []

    def test_async_function_focus(self):
        """AsyncFunctionDef 区间预扫描路径（焦点在 async 函数）。"""
        code = "async def agamma(z):\n    if z == 3:\n        return 1\n    return 0\n"
        out = derive_boundary_triplets(code, focus_function="agamma")
        assert out, "async 函数内比较应提取"

    def test_if_compare_dedup(self):
        """if 条件中的 Compare 与独立 Compare 同行 → _seen_lines 去重保留首条。"""
        code = "def f(x):\n    if x > 1 and x < 100:\n        return 1\n    return 0\n"
        out = derive_boundary_triplets(code, focus_function="f")
        # 去重口径：同一 lineno 只保留一条
        lines = [t["line"] for t in out]
        assert len(lines) == len(set(lines)), f"同行重复未去重: {lines}"


@pytest.mark.unit
class TestInferLiteralType:
    """type_repair._infer_literal_type 字面量类型矩阵（全分支）。"""

    @pytest.mark.parametrize(
        ("expr", "label"),
        [
            ("True", "bool"),
            ("1", "int"),
            ("1.5", "float"),
            ("'s'", "str"),
            ("b'x'", "bytes"),
            ("None", "None"),
            ("[1]", "list"),
            ("(1, 2)", "tuple"),
            ("{'a': 1}", "dict"),
            ("{1, 2}", "set"),
        ],
    )
    def test_known_literals(self, expr, label):
        node = ast.parse(expr, mode="eval").body
        assert _infer_literal_type(node) == label

    def test_name_returns_none(self):
        node = ast.parse("x", mode="eval").body
        assert _infer_literal_type(node) is None

    def test_binop_returns_none(self):
        node = ast.parse("1 + 2", mode="eval").body
        assert _infer_literal_type(node) is None

    def test_call_returns_none(self):
        node = ast.parse("f()", mode="eval").body
        assert _infer_literal_type(node) is None
