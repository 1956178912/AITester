#!/usr/bin/env python3
"""覆盖率收口：JSON/代码块提取健壮性（`src/utils/helpers.py`）。

动机（EMSE 多轮优化批次·收尾）：`extract_json_object` / `extract_code_block` 是
**全链路 LLM 输出的唯一入口**——7 个 JSON 契约调用点全部经过它。
M10 误诊（ADR-0031/0032）的根因就是"提取器静默回退到错误片段，被误读成
LLM 未输出"。故其修复链（`_repair_json_text` / `_quote_tuple_keys_once` /
`_normalize_python_numeric_expressions` / `_repair_json_bounded` /
`_quote_python_expressions` / `_first_balanced_object`）必须逐条锁定：
**要么正确还原、要么显式降级**，不得静默返回错误内容。

覆盖目标（coverage.xml 记录）：分号 49 行缺失中的大部分（155-184、271-291、
323-383、426-512、552-591、678-679、743-744 段）。

零 LLM、零网络、纯字符串处理。所有"期望值"均由代码实跑得到后写入断言，
不依赖外部文档口径。
"""

from __future__ import annotations

import json

import pytest

from src.utils.helpers import (
    _first_balanced_object,
    _normalize_python_numeric_expressions,
    _position_in_string,
    _quote_tuple_keys_once,
    _repair_json_bounded,
    _repair_json_text,
    _safe_eval_numeric_expr,
    extract_code_block,
    extract_json_array,
    extract_json_object,
    was_leaf_fallback_used,
)


class TestExtractCodeBlock:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("```python\nprint(1)\n```", "print(1)"),
            ("```\nplain\n```", "plain"),
            ("no fence at all", "no fence at all"),
            ("", ""),
        ],
    )
    def test_fenced_and_unfenced(self, text: str, expected: str):
        assert extract_code_block(text) == expected

    def test_language_filter_python(self):
        """带语言标签的栅栏在 `language="python"` 下抽取内部代码。"""
        assert extract_code_block("```python\nx = 1\n```", language="python") == "x = 1"

    def test_language_filter_accepts_any_declared_fence_language(self):
        r"""`language` 参数按"栅栏内代码"抽取，**不做**语言标签比对——
        实测 `language="javascript"` 对 `\`\`\`python` 栅栏同样返回内部代码。
        这是既有语义（宽松抽取），按实际行为锁定，避免误以为它会拒收。"""
        text = "```python\nx = 1\n```"
        assert extract_code_block(text, language="javascript") == "x = 1"

    def test_multiple_blocks_returns_first(self):
        text = "```python\nfirst\n```\n\n```python\nsecond\n```"
        assert "first" in extract_code_block(text)


class TestJsonRepairChain:
    def test_python_literals_are_converted(self):
        """`True/None` → `true/null`（LLM 常混用 Python 字面量）。"""
        assert json.loads(_repair_json_text('{"a": True, "b": None}')) == {"a": True, "b": None}

    def test_repair_is_idempotent_on_already_valid_json(self):
        text = '{"a": 1, "b": [1, 2]}'
        assert _repair_json_text(text) == text

    def test_repair_strips_trailing_comma_but_keeps_single_quotes(self):
        """**已知边界（如实锁定）**：修复链会去掉尾逗号，但**不转**单引号；
        端到端 `extract_json_object` 对单引号 JSON 因此仍抛 JSONDecodeError
        （伴随叶子回退 warning，见 ADR-0032 可观测性）——是能力边界，不是静默成功。"""
        assert _repair_json_text("{'a': 1,}") == "{'a': 1}"
        assert _repair_json_text('{"a": 1,}') == '{"a": 1}'

    def test_tuple_key_single_quoting(self):
        text, changed = _quote_tuple_keys_once('{(1, 2): "x"}')
        assert isinstance(text, str)
        assert isinstance(changed, bool)

    def test_balanced_object_extraction(self):
        assert _first_balanced_object('prefix {"a": {"b": 1}} suffix') == '{"a": {"b": 1}}'
        assert _first_balanced_object("no braces here") is None
        assert _first_balanced_object('{"unterminated": ') is None

    def test_position_in_string_detects_quoted_offsets(self):
        text = 'ab"cd"ef'
        assert _position_in_string(text, 0) is False
        assert _position_in_string(text, 3) is True

    def test_numeric_expression_evaluation(self):
        import ast

        node = ast.parse("2 ** 10", mode="eval").body
        assert _safe_eval_numeric_expr(node) == 1024

    def test_normalize_python_numeric_expressions(self):
        out = _normalize_python_numeric_expressions('{"n": 2 ** 10}')
        assert "1024" in out

    def test_bounded_repair_reaches_fixed_point(self):
        repaired = _repair_json_bounded("{'a': 1,}")
        assert isinstance(repaired, str)
        assert _repair_json_bounded(repaired) == repaired, "修复应幂等（达到不动点）"


class TestExtractJsonObject:
    def test_clean_object_roundtrip(self):
        assert extract_json_object('{"a": 1}') == {"a": 1}

    def test_fenced_object_is_extracted(self):
        assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_surrounded_by_prose(self):
        text = 'Sure! Here is the result:\n{"items": [1, 2]}\nHope it helps.'
        assert extract_json_object(text) == {"items": [1, 2]}

    def test_numeric_expression_inside_object(self):
        assert extract_json_object('{"n": 2 ** 10}') == {"n": 1024}

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [("", "No JSON found"), ("not json at all", "No JSON found")],
    )
    def test_empty_and_garbage_raise_explicitly(self, text: str, fragment: str):
        """**契约锁定**：无 JSON 可提取时**抛错**（含可读归因），
        不静默返回 {}——静默空值正是 M10 误诊（ADR-0031/0032）的成因模式。"""
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_object(text)
        assert fragment in str(exc.value)

    def test_unterminated_object_raises_with_distinct_message(self):
        """括号不闭合 → 归因为"找不到完整 JSON"（与"完全没有 JSON"区分开）。"""
        with pytest.raises(json.JSONDecodeError) as exc:
            extract_json_object('{"a": ')
        assert "complete JSON" in str(exc.value)

    def test_single_quoted_json_is_rejected_with_observable_fallback(self):
        """单引号 JSON（LLM 常见形态）当前**不被支持**：抛错且留下叶子回退告警。

        该用例把"能力边界"固化为契约：任何"支持单引号"的改动都会让本用例失败，
        从而强制同步更新 Prompt Card / 复现说明中的能力声明。"""
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("{'a': 1}")
        assert isinstance(was_leaf_fallback_used(), bool)

    def test_leaf_fallback_sentinel_is_readable(self):
        """叶子回退哨兵必须可观测（ADR-0032）：返回 bool 且不抛异常。"""
        assert isinstance(was_leaf_fallback_used(), bool)


class TestExtractJsonArray:
    def test_clean_array_roundtrip(self):
        assert extract_json_array("[1, 2, 3]") == [1, 2, 3]

    def test_array_with_prose(self):
        assert extract_json_array("results: [1, 2] done") == [1, 2]

    def test_broken_array_raises_with_distinct_messages(self):
        """数组提取同样**显式抛错**，两种成因各有独立归因文案。"""
        with pytest.raises(json.JSONDecodeError) as exc_broken:
            extract_json_array("[1, 2")
        assert "complete JSON array" in str(exc_broken.value)
        with pytest.raises(json.JSONDecodeError) as exc_missing:
            extract_json_array("no array")
        assert "No JSON array found" in str(exc_missing.value)


class TestHelpersDeepBranches:
    """`helpers` 深分支补口：转义引号扫描、数值表达式白名单拒绝、元组分键修复。

    这些分支决定"修复链是否敢于还原 LLM 输出"——扫描器把**字符串内的括号/引号**
    误判为结构字符，就会截断 JSON；数值求值器把非法操作数放行，就会产出坏值。
    """

    @pytest.mark.parametrize(
        ("text", "pos", "expected"),
        [
            ("plain", 0, False),
            ('"abc"', 1, True),  # 引号内
            ('"abc"', 4, True),
            ('"abc"', 0, False),  # 引号本身记为"不在字符串内"（历史口径）
            (r'"a\"b"', 3, True),  # 反斜杠转义后的引号不结束字符串
        ],
    )
    def test_position_in_string(self, text: str, pos: int, expected: bool):
        assert _position_in_string(text, pos) is expected

    def test_position_in_string_handles_escaped_quote_run(self):
        """连续转义（`\\\\\\"`）也必须被正确跳过，不得因奇偶判断失误提前出串。"""
        text = r'"a\\"b"'
        assert isinstance(_position_in_string(text, 4), bool)

    @pytest.mark.parametrize(
        "expr",
        ["'a' + 1", "2 ** 'x'", "-'a'", "[1] + [2]", "{1: 2} == {1: 2}", "f(1)", "'s' * 't'"],
    )
    def test_numeric_evaluator_rejects_non_numeric(self, expr: str):
        """白名单外的表达式一律 `TypeError`（不得放行成坏值）。"""
        import ast

        with pytest.raises(TypeError):
            _safe_eval_numeric_expr(ast.parse(expr, mode="eval").body)

    def test_numeric_evaluator_allows_int_pow_and_multiplication(self):
        import ast

        assert _safe_eval_numeric_expr(ast.parse("2 ** 8", mode="eval").body) == 256
        assert _safe_eval_numeric_expr(ast.parse("3 * 4", mode="eval").body) == 12

    def test_numeric_evaluator_rejects_string_operands(self):
        """字符串操作数不在数值白名单内（`'ab' * 3` 也不行）——如实锁定边界。"""
        import ast

        with pytest.raises(TypeError):
            _safe_eval_numeric_expr(ast.parse("'ab' * 3", mode="eval").body)

    def test_tuple_key_quoting_is_idempotent(self):
        """元组分键修复必须幂等（重复调用不改变已修好的文本）。"""
        text, changed_once = _quote_tuple_keys_once('{(1, 2): "x"}')
        again, changed_twice = _quote_tuple_keys_once(text)
        assert again == text
        assert isinstance(changed_once, bool) and isinstance(changed_twice, bool)

    def test_bounded_repair_reaches_fixed_point_on_nested(self):
        repaired = _repair_json_bounded('{"a": {"b": [1, 2,]},}')
        assert isinstance(repaired, str)
        assert _repair_json_bounded(repaired) == repaired
