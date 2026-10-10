"""D1 修复层测试：LLM JSON 输出的语法级保守修复。

背景（实测）：4,041 个缓存响应的结构裁决显示 **188/621（30%）** Planner 形态
响应无法 ``json.loads``，经 `nodes.py:269` 的 ``except json.JSONDecodeError``
走到 ``_get_default_test_plan``（``test_cases=[]``），使 Generator 约 30% 任务
拿不到测试计划——never-red 通道的主因候选。

修复层只做**语法级**修复，绝不改语义，且**不使用 eval**：
- ``_repair_json_text``：尾随逗号、值位置未加引号的 Python 字面量；
- ``_quote_python_expressions``：值位置的纯字面量表达式（自写受限求值器）；
- ``_first_balanced_object``：多对象背靠背拼接时取首个。

实测净回收：可解析 427/621 → 554/621（+20.5pp）。
"""

from __future__ import annotations

import json

import pytest

from src.utils.helpers import (
    _first_balanced_object,
    _quote_python_expressions,
    _repair_json_text,
    extract_json_object,
)


class TestTrailingCommaAndLiterals:
    """``_repair_json_text``：尾随逗号 + 值位置 Python 字面量。"""

    def test_trailing_comma_in_object(self) -> None:
        assert json.loads(_repair_json_text('{"a":1,}')) == {"a": 1}

    def test_trailing_comma_in_array(self) -> None:
        assert json.loads(_repair_json_text('{"a":[1,2,]}')) == {"a": [1, 2]}

    @pytest.mark.parametrize(
        ("src", "expected"),
        [
            ('{"a":None}', {"a": None}),
            ('{"a":True}', {"a": True}),
            ('{"a":False}', {"a": False}),
        ],
    )
    def test_unquoted_python_literals(self, src: str, expected: dict) -> None:
        assert json.loads(_repair_json_text(src)) == expected

    def test_literal_inside_string_not_touched(self) -> None:
        """字符串**内部**的 None 不得被替换（负向后瞻的作用）。"""
        src = '{"desc":"expected None here"}'
        assert json.loads(_repair_json_text(src)) == {"desc": "expected None here"}


class TestSafeExpressionQuoting:
    """``_quote_python_expressions``：受限求值，绝不触达可执行构造。"""

    def test_string_repeat_is_quoted(self) -> None:
        out = _quote_python_expressions('{"key":"a"*3}')
        assert json.loads(out) == {"key": "aaa"}

    def test_string_concat_is_quoted(self) -> None:
        out = _quote_python_expressions('{"a":"ab"+"cd"}')
        assert json.loads(out) == {"a": "abcd"}

    def test_oversized_repeat_is_truncated_not_dropped(self) -> None:
        """超长重复**截断**而非拒绝——保用例其余字段，远优于整任务空计划。"""
        out = _quote_python_expressions('{"key":"a"*100000}', max_len=64)
        got = json.loads(out)["key"]
        assert got == "a" * 64
        assert len(got) == 64

    @pytest.mark.parametrize(
        "dangerous",
        [
            '{"a":os.system("ls")}',
            '{"a":__import__("os")}',
            '{"a":open("/etc/passwd").read()}',
            '{"a":eval("1+1")}',
            '{"a":(lambda: 1)()}',
        ],
    )
    def test_executable_constructs_are_rejected(self, dangerous: str) -> None:
        """**安全核心**：非字面量构造必须原样保留（不被求值、不被替换）。"""
        assert _quote_python_expressions(dangerous) == dangerous

    def test_plain_json_unchanged(self) -> None:
        src = '{"a":"normal","b":2,"c":[1,2]}'
        assert _quote_python_expressions(src) == src

    def test_no_quotes_returns_as_is(self) -> None:
        assert _quote_python_expressions("{'a':1}") == "{'a':1}"


class TestFirstBalancedObject:
    """``_first_balanced_object``：多对象拼接取首个。"""

    def test_concatenated_objects_returns_first(self) -> None:
        text = '{"function_name":"a"}\n{"function_name":"b"}'
        assert _first_balanced_object(text) == '{"function_name":"a"}'

    def test_nested_braces_respected(self) -> None:
        text = '{"a":{"b":1}}{"c":2}'
        assert _first_balanced_object(text) == '{"a":{"b":1}}'

    def test_brace_inside_string_not_counted(self) -> None:
        text = '{"a":"}{"}'
        assert _first_balanced_object(text) == '{"a":"}{"}'

    def test_unbalanced_returns_none(self) -> None:
        assert _first_balanced_object('{"a":1') is None

    def test_no_brace_returns_none(self) -> None:
        assert _first_balanced_object("no json") is None


class TestExtractEndToEnd:
    """``extract_json_object`` 端到端：修复层接入后的整体行为。"""

    def test_concatenated_objects_picks_first_with_plan(self) -> None:
        text = (
            '{"function_name":"alpha","logic_analysis":{"a":1},"test_cases":[]}\n'
            '{"function_name":"beta","logic_analysis":{"a":2},"test_cases":[]}'
        )
        got = extract_json_object(text)
        assert got["function_name"] == "alpha"

    def test_python_expression_recovered(self) -> None:
        text = '{"function_name":"f","logic_analysis":{},"test_cases":[{"input_args":{"key":"a"*3}}]}'
        got = extract_json_object(text)
        assert got["test_cases"][0]["input_args"]["key"] == "aaa"

    def test_unquoted_none_recovered(self) -> None:
        text = '{"function_name":"f","logic_analysis":{},"test_cases":[{"expected_output":None}]}'
        got = extract_json_object(text)
        assert got["test_cases"][0]["expected_output"] is None

    def test_normal_json_unchanged(self) -> None:
        text = '{"function_name":"f","logic_analysis":{"input_domain":"x"},"test_cases":[]}'
        assert extract_json_object(text) == json.loads(text)

    def test_markdown_fenced_still_works(self) -> None:
        text = '```json\n{"function_name":"f","logic_analysis":{},"test_cases":[]}\n```'
        assert extract_json_object(text)["function_name"] == "f"

    def test_garbage_raises(self) -> None:
        import json as _json

        with pytest.raises(_json.JSONDecodeError):
            extract_json_object("这不是 JSON，也没有花括号")


class TestTupleKeys:
    """``_quote_tuple_keys_once`` / ``_repair_json_bounded``：元组作键的修复。

    D1 残余主因：LLM 写 ``{(0,1):5}``（Python 合法、JSON 非法）。
    """

    def test_numeric_tuple_key_quoted(self) -> None:
        from src.utils.helpers import _repair_json_bounded

        out = _repair_json_bounded('{"m":{(0,1):5,"n":2},}')
        assert json.loads(out) == {"m": {"(0,1)": 5, "n": 2}}

    def test_bounded_repair_handles_compound_damage(self) -> None:
        """复合损坏（元组键 + 尾随逗号 + 未加引号字面量）一次收敛。"""
        from src.utils.helpers import _repair_json_bounded

        out = _repair_json_bounded('{"m":{(0,1):5,},"v":None,}')
        assert json.loads(out) == {"m": {"(0,1)": 5}, "v": None}

    def test_string_content_is_never_modified(self) -> None:
        """**关键正确性**：字符串内部的 `{`/`,` 不得被当作键位置。

        实测反例：``"n=1：单节点，返回 {"(0,0)": 0}"`` —— 早期实现会误改
        并制造新语法错误，把**本来可解析**的响应改坏。本用例锁定防回归。
        """
        from src.utils.helpers import _repair_json_bounded

        original = json.dumps(
            {"desc": "返回 {(0,0): 0} 形式", "edge_cases": ['n=1：返回 {"(0,0)": 0}']},
            ensure_ascii=False,
        )
        assert json.loads(_repair_json_bounded(original)) == json.loads(original)

    def test_already_valid_json_untouched(self) -> None:
        from src.utils.helpers import _repair_json_bounded

        src = '{"a":1,"b":[{"c":2}]}'
        assert _repair_json_bounded(src) == src

    def test_string_valued_tuple_key_left_alone(self) -> None:
        """含字符串的元组键（``("a",1):2``）刻意不处理——保守失败。"""
        from src.utils.helpers import _repair_json_bounded

        src = '{"m":{("a",1):2}}'
        assert _repair_json_bounded(src) == src
