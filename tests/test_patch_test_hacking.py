"""patch_test_hacking 完整单元测试（2026-10-08，87% → 100%）。

此前无专门测试文件（仅被集成间接覆盖 87%）。补齐三类作弊信号检测的
全分支：_is_hardcoded_branch（常量比较→返回常量的各边界）、
_is_swallow_body（吞异常形态）、detect_test_hacking（信号收集 + 降级）。
零 LLM / 零网络（纯 AST 差集）。
"""

from __future__ import annotations

import ast

from src.tools.patch_test_hacking import (
    _is_const_node,
    _is_hardcoded_branch,
    _is_swallow_body,
    _node_signatures,
    detect_test_hacking,
    test_hacking_signal_names,
)

# ═══ 1. _is_const_node ════════════════════════════════════════════════════════


class TestIsConstNode:
    def test_constant_true(self):
        assert _is_const_node(ast.Constant(value=1)) is True

    def test_all_const_tuple_true(self):
        assert _is_const_node(ast.Tuple(elts=[ast.Constant(1), ast.Constant(2)])) is True

    def test_non_const_tuple_false(self):
        assert _is_const_node(ast.Tuple(elts=[ast.Constant(1), ast.Name(id="x")])) is False

    def test_name_false(self):
        assert _is_const_node(ast.Name(id="x")) is False


# ═══ 2. _is_hardcoded_branch ══════════════════════════════════════════════════


class TestIsHardcodedBranch:
    def test_non_compare_test_false(self):
        node = ast.If(test=ast.Name(id="x"), body=[], orelse=[])
        assert _is_hardcoded_branch(node) is False

    def test_non_const_comparator_false(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Name(id="y")]),
            body=[],
            orelse=[],
        )
        assert _is_hardcoded_branch(node) is False

    def test_body_not_single_return_false(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Pass()],
            orelse=[],
        )
        assert _is_hardcoded_branch(node) is False

    def test_single_return_const_true(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Constant(0))],
            orelse=[],
        )
        assert _is_hardcoded_branch(node) is True

    def test_orelse_single_const_return_true(self):
        # 双臂硬编码：if 与 else 均为单一常量 return → True
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Constant(0))],
            orelse=[ast.Return(value=ast.Constant(1))],
        )
        assert _is_hardcoded_branch(node) is True

    def test_orelse_not_single_return_false(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Constant(0))],
            orelse=[ast.Pass()],
        )
        assert _is_hardcoded_branch(node) is False

    def test_ops_not_eq_in_false(self):
        # 操作符非 Eq / In（如 Lt）→ False
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Lt()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Constant(0))],
            orelse=[],
        )
        assert _is_hardcoded_branch(node) is False

    def test_return_non_const_false(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Name(id="y"))],
            orelse=[],
        )
        assert _is_hardcoded_branch(node) is False

    def test_orelse_return_non_const_false(self):
        node = ast.If(
            test=ast.Compare(left=ast.Name(id="x"), ops=[ast.Eq()], comparators=[ast.Constant(1)]),
            body=[ast.Return(value=ast.Constant(0))],
            orelse=[ast.Return(value=ast.Name(id="y"))],
        )
        assert _is_hardcoded_branch(node) is False


# ═══ 3. _is_swallow_body ══════════════════════════════════════════════════════


class TestIsSwallowBody:
    def test_pass_true(self):
        assert _is_swallow_body([ast.Pass()]) is True

    def test_single_const_return_true(self):
        assert _is_swallow_body([ast.Return(value=ast.Constant(0))]) is True

    def test_non_swallow_false(self):
        assert _is_swallow_body([ast.Expr(value=ast.Constant(1))]) is False


# ═══ 4. _node_signatures ══════════════════════════════════════════════════════


class TestNodeSignatures:
    def test_collects_assert_and_swallow(self):
        code = "def f(x):\n    assert x > 0\n    try:\n        pass\n    except Exception:\n        pass\n"
        sigs, assert_count, swallows = _node_signatures(code)
        assert assert_count == 1
        assert len(swallows) == 1  # 吞异常 ExceptHandler
        assert sigs


# ═══ 5. detect_test_hacking ═══════════════════════════════════════════════════


class TestDetectTestHacking:
    def test_empty_code_returns_clean(self):
        assert detect_test_hacking("", "def f(): pass") == {"suspected": False, "signals": []}

    def test_syntax_error_returns_clean(self):
        assert detect_test_hacking("def f(:", "def f(): pass") == {"suspected": False, "signals": []}

    def test_hardcoded_branch_detected(self):
        original = "def f(x):\n    return x * 2\n"
        patched = "def f(x):\n    if x == 1:\n        return 0\n    return x * 2\n"
        result = detect_test_hacking(original, patched)
        assert result["suspected"] is True
        assert "hardcoded_input_branch" in result["signals"]

    def test_assert_weakened_detected(self):
        original = "def f(x):\n    assert x > 0\n    return x\n"
        patched = "def f(x):\n    return x\n"
        result = detect_test_hacking(original, patched)
        assert "assert_weakened" in result["signals"]

    def test_exception_swallow_detected(self):
        original = "def f(x):\n    return 1 / x\n"
        patched = "def f(x):\n    try:\n        return 1 / x\n    except ZeroDivisionError:\n        pass\n"
        result = detect_test_hacking(original, patched)
        assert "exception_swallow_added" in result["signals"]

    def test_signal_names(self):
        assert test_hacking_signal_names() == (
            "hardcoded_input_branch",
            "assert_weakened",
            "exception_swallow_added",
        )
