"""覆盖率补口：`helpers.py` 边界分支（2026-10-19 工程质量轮）。

目标：把全量覆盖率中仍缺失的**可达**分支固化为契约——字符串转义扫描、
数值表达式求值的类型门、字符串内位置保护、超长数值兜底，以及
`extract_json_array` / `extract_json_object` 的叶子回退失败路径。

不可达分支（如 `_safe_eval_numeric_expr` 的 `non-numeric operand`）不在本文件
强行覆盖：递归求值器只会返回数值或抛错，该分支属防御性死代码，伪造 mock 会
让测试失去行为约束意义。AA-5 进一步把"为何不可达"从推断升级为证据——门文法
逐字节钉住 + 扫描器分歧枚举，结论登记在 ROUND4 覆盖率审计。
"""

from __future__ import annotations

import ast
import itertools
import json

import pytest

from src.utils import helpers
from src.utils.helpers import (
    _first_balanced_object,
    _normalize_python_numeric_expressions,
    _quote_python_expressions,
    _safe_eval_numeric_expr,
    extract_json_array,
    extract_json_object,
    was_leaf_fallback_used,
)


class TestFirstBalancedObjectEscapes:
    def test_escaped_quote_inside_string_does_not_end_object(self) -> None:
        """字符串内的 `\\"` 必须被跳过，不能把后续 `}` 误判为对象结束。"""
        text = r'{"a": "x\"y"} tail'
        assert _first_balanced_object(text) == r'{"a": "x\"y"}'


class TestNumericExpressionGuards:
    def test_float_pow_operand_rejected(self) -> None:
        """幂运算只接受 int 指数/底数（float 会产生精度漂移，保守拒绝）。"""
        with pytest.raises(TypeError, match="int-only"):
            _safe_eval_numeric_expr(ast.parse("2.0 ** 3", mode="eval").body)

    def test_expression_inside_json_string_is_not_rewritten(self) -> None:
        """字符串内的表达式不是值位置，必须逐字节保留（位置保护分支）。"""
        text = '{"s": "a:[10**18]"}'
        assert _normalize_python_numeric_expressions(text) == text

    def test_non_numeric_evaluator_result_keeps_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """求值器若返回非数值（防御路径），原样保留交既有降级链。"""
        monkeypatch.setattr(helpers, "_safe_eval_numeric_expr", lambda _node: "not-a-number")
        text = '{"n": 1 + 1}'
        assert _normalize_python_numeric_expressions(text) == text

    def test_too_many_digits_keeps_original(self) -> None:
        """结果位数超上限（4096）时原样保留，防超长整数进入下游。"""
        text = '{"n": 10**4096}'
        assert _normalize_python_numeric_expressions(text) == text


class TestJsonLeafFallbacks:
    def test_array_uses_leaf_when_outer_bracket_unbalanced(self) -> None:
        """外层数组不闭合时，仍可从最内层完整数组恢复（档 2 成功路径）。"""
        assert extract_json_array("[[1, 2]") == [1, 2]

    def test_array_leaf_parse_failure_raises_with_distinct_message(self) -> None:
        """叶子片段本身非法 JSON 时必须继续降级并显式抛错，不静默返回。"""
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_array("[[1, 2,]")
        assert "complete JSON array" in str(exc.value)

    def test_object_with_no_leaf_candidates_raises(self) -> None:
        """`{` 后无任何完整叶子对象 → 走 825 的假分支后统一抛错。"""
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_object("{bad")
        assert "complete JSON" in str(exc.value)

    def test_object_tail_scan_skips_unparseable_leaves(self) -> None:
        """三个叶子均不可解析时，尾扫逐个失败后抛错（不返回坏片段）。"""
        text = '{"a": {"bad1": }, "b": {"bad2": }, "c": {"bad3": }}'
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_object(text)
        assert "complete JSON" in str(exc.value)

    def test_array_falls_through_tier2_when_leaf_invalid(self) -> None:
        """AA-5：档 1 括号片段与档 2 最内层叶子**均**非法时逐档降级后抛错。

        `[a, b]` 无引号，括号法与其四种语法修复档都救不回；档 2 的正则叶子
        命中的还是同一片段，`json.loads` 再失败一次（该"叶子命中但仍非法"
        的落空弧此前无测试经过），最终显式抛错、不静默返回坏片段。
        """
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_array("here is the list: [a, b]")
        assert "complete JSON array" in str(exc.value)

    def test_object_tier2_cannot_rescue_bare_backslash_fragment(self) -> None:
        """AA-5：字符串外的裸反斜杠让两个扫描器分歧——首对象修复档救援不了。

        `_find_balanced_json` 把 `\\}` 当转义吞掉 → 深度归不了零 → 返回 None，
        档 1 整体跳过；`_first_balanced_object` 只在串内认转义，取到
        `{"a": 1\\}`，但该片段自身含非法转义，raw + 四条修复候选全部失败
        （helpers 首对象档的返回分支因此实测恒不可达，见 ROUND4 审计）。
        本例锁定**当前可观察口径**：继续降级到叶子档、取**最后**一个对象并
        置叶子哨兵——若日后有人改造修复器使首对象被救回，此测试会失败，
        那是需要显式复核语义变更的信号，不是顺手回归。
        """
        assert extract_json_object('{"a": 1\\}{"b": 2}') == {"b": 2}
        assert was_leaf_fallback_used() is True

    def test_value_position_gate_grammar_is_what_makes_safe_eval_rejects_dead(self) -> None:
        """AA-5：锁住值位置正则门的文法——它就是 `_safe_eval` 拒绝分支不可达的前提。

        `_safe_eval` 只经该正则门（模块级 `_JSON_VALUE_EXPR_PATTERN`）进入，门只放行
        「引号字符串」后接 `* 整数` 或 `+ 引号字符串`，故求值器永远见不到 Mult 的
        int×str、非常规运算符、Constant/BinOp 之外的节点，也永远见不到"求值结果非
        字符串"（465 的假分支）——四条拒绝线因此恒不可达。门一旦放宽，本测试的
        逐字节文法钉先红，提示同步复核求值器与 ROUND4 登记。
        """
        # 1) 文法本体逐字节钉住（放宽/收紧都会先在这里失败，而非静默改变语义）
        assert helpers._JSON_VALUE_EXPR_PATTERN.pattern == (
            r':\s*("(?:[^"\\]|\\.)*"(?:\s*\*\s*\d+|\s*\+\s*"(?:[^"\\]|\\.)*")+)'
        )
        gate = helpers._JSON_VALUE_EXPR_PATTERN
        atoms = ['"a"', '"\\n"', '""', '"中"']
        ops = ["*3", " * 12", "*0", '+"b"', '+ "\\t"', '+""']
        checked = 0
        for depth in (1, 2, 3):
            for combo in itertools.product(atoms + ops, repeat=depth):
                match = gate.search(f'{{"k": {"".join(combo)},}}')
                if match is None:
                    continue
                checked += 1
                expr = match.group(1)
                body = ast.parse(expr, mode="eval").body
                for node in ast.walk(body):
                    assert isinstance(node, (ast.Constant, ast.BinOp, ast.Add, ast.Mult)), (expr, type(node))
                    if not isinstance(node, ast.BinOp):
                        continue
                    assert isinstance(node.op, (ast.Add, ast.Mult)), expr
                    if isinstance(node.op, ast.Mult):
                        # Mult 右侧恒为门内 `\d+` 产出的 int 常量 → 反向 441/443 不可达
                        assert isinstance(node.right, ast.Constant), expr
                        assert isinstance(node.right.value, int), expr
                # 门内文法恒求到字符串 → 465 "非字符串保持原样" 分支不可达
                rewritten = _quote_python_expressions(f'{{"k": {expr}}}')
                assert rewritten != f'{{"k": {expr}}}', (expr, rewritten)
                assert isinstance(json.loads(rewritten)["k"], str), expr
        assert checked > 100, f"文法枚举样本过少（{checked}），本锁将失去约束力"
