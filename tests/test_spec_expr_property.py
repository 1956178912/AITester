#!/usr/bin/env python3
"""A-14（2026-10-16）：SpecExpr 编译器的 property-based 模糊测试（hypothesis）。

独立评审 A-14：对受限表达式 DSL 的**归因闭合性**做不变式级验证——
随机（含对抗性）输入下，逐条归因 API `clause_reject_reason` 恒满足：

1. **闭集性（核心，10^4 级例）**：返回恒 ∈ `SPEC_REJECT_REASONS ∪ {None}`，
   任意类型输入（str / None / int / bytes / list / dict / 深嵌套 / CJK /
   运算符杂烩 / lambda / 海象 / 切片）一律不抛异常；
2. **形态门蕴含**：`is_expression_clause` 为 True 的输入，其拒绝原因必不含
   形态门家族（natural_language / parse_error / too_long / empty /
   not_a_string）——只可能是编译器后端拒绝（unsupported_* / unknown_name）；
3. **可编译蕴含形态**：`clause_reject_reason(...) is None` ⇒
   `is_expression_clause(...)` 为 True（可编译 ⊆ 可解析形态，防判定门漂移）；
4. **聚合守恒**：`spec_reject_reasons` 的键集 ⊆ 闭集，且逐条 API 与聚合
   口径一致（无 *_expr 通道时 NL 通道逐条 == 聚合计数）；空白子句按历史
   口径既不入分母也不计数。

hypothesis 为测试链依赖（requirements.txt 已声明；缺失时整文件跳过）。
"""

from __future__ import annotations

from typing import Any

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis 未安装（测试链依赖）")

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.specs.spec_ir_v2 import (  # noqa: E402
    SPEC_REJECT_REASONS,
    clause_reject_reason,
    is_expression_clause,
    spec_expr_grammar_terminals,
    spec_reject_reasons,
)

_TERMINALS = spec_expr_grammar_terminals()
_ALLOWED_CALLS = _TERMINALS["calls"]
_ALLOWED_ATTRS = _TERMINALS["attrs"]

# 形态门家族（is_expression_clause 为 True 后不可再出现的拒绝原因）
_FORM_GATE_REASONS = {"natural_language", "parse_error", "too_long", "empty", "not_a_string"}
# 后端拒绝家族（形态通过后允许出现的原因）
_BACKEND_REASONS = {"unsupported_syntax", "unsupported_operator", "unknown_name"}

_NAMES = ["x", "y", "n", "a", "b", "arr", "items", "result", "r", "s", "value"]
_KINDS = st.sampled_from(["precondition", "postcondition", "invariant", "boundary", "", "unknown"])
_SIGPARAMS = st.one_of(
    st.none(),
    st.lists(st.sampled_from([*_NAMES, "other"]), max_size=6),
    st.just([]),
)

# 结构化"近似合法"表达式模板：命中白名单接受/拒绝的深路径
_TEMPLATES = st.sampled_from(
    [
        "{a} == {b}",
        "{a} != {b}",
        "{a} < {b} or {a} >= 0",
        "({a} + {b}) % 2 == 0",
        "{a} in {b}",
        "not {a}",
        "isinstance({a}, int)",
        "len({a}) > 0",
        "sorted({a}) == sorted({b})",
        "{a}.upper() == {b}",
        "{a}[0] == {b}",
        "{a}[1:3] == {b}",
        "{a}.get({b}) is None",
        "all({a} > 0 for x in {b})",
        "any({a} == x for x in {b})",
        "[x for x in {a} if x]",
        "lambda x: x + 1",
        "({a} := {b})",
        "{a} > {b} if {a} else {b}",
        "open({a}).read()",
        "__import__({a})",
        "{a}.__class__ == int",
    ]
)

_token_soup = st.lists(
    st.sampled_from(
        [
            "x",
            "y",
            "arr",
            "result",
            "1",
            "0",
            "-2",
            "3.14",
            "+",
            "-",
            "*",
            "/",
            "%",
            "**",
            "==",
            "!=",
            "<",
            ">",
            "<=",
            ">=",
            "and",
            "or",
            "not",
            "in",
            "is",
            "lambda",
            ":=",
            ":",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}",
            ",",
            ".",
            "'",
            '"',
            "_",
            " ",
            "\n",
            "中",
            "句",
            "→",
            "…",
            "\\",
        ]
    ),
    min_size=0,
    max_size=14,
).map("".join)

_textual_clause = st.one_of(
    st.text(max_size=60),  # 任意 unicode
    _token_soup,  # 运算符/括号/CJK 杂烩
    _TEMPLATES.flatmap(
        lambda t: st.tuples(st.sampled_from(_NAMES), st.sampled_from(_NAMES)).map(lambda ab: t.format(a=ab[0], b=ab[1]))
    ),
    st.sampled_from(_ALLOWED_CALLS).flatmap(
        lambda c: st.sampled_from(["x", "arr", "1"]).map(lambda arg: f"{c}({arg}) == x")
    ),
    st.sampled_from(_ALLOWED_ATTRS).flatmap(lambda a: st.sampled_from(_NAMES).map(lambda n: f"{n}.{a} == 1")),
    st.just(""),
    st.just(" "),
    st.just("x = 1"),  # 语句形态（eval 解析失败）
    st.just("x[1:3:0] == y[::-1]"),
)

_any_clause = st.one_of(
    _textual_clause,
    st.none(),
    st.integers(),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.binary(max_size=16),
    st.lists(st.integers(), max_size=4),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
)

_string_clause = st.one_of(_textual_clause, st.just("\t"), st.text(alphabet="ab ()[]=.", max_size=30))


@settings(max_examples=5000, deadline=None)
@given(clause=_any_clause, kind=_KINDS, params=_SIGPARAMS)
def test_reject_reason_is_closed_set(clause: Any, kind: str, params: Any) -> None:
    """闭集性：任意输入 × 任意 kind/签名 → 不抛异常且归因 ∈ 闭集 ∪ {None}。"""
    reason = clause_reject_reason(clause, kind, params)
    assert reason is None or reason in SPEC_REJECT_REASONS, (clause, kind, reason)


@settings(max_examples=1200, deadline=None)
@given(clause=_any_clause, kind=_KINDS)
def test_expression_form_excludes_form_gate_reasons(clause: Any, kind: str) -> None:
    """形态门蕴含：过 is_expression_clause 的输入，原因 ∈ 后端家族 ∪ {None}。"""
    if is_expression_clause(clause):
        reason = clause_reject_reason(clause, kind, ["x", "arr"])
        assert reason is None or reason in _BACKEND_REASONS, (clause, kind, reason)


@settings(max_examples=1200, deadline=None)
@given(clause=_any_clause, kind=_KINDS)
def test_compilable_implies_expression_form(clause: Any, kind: str) -> None:
    """可编译蕴含形态：reason None ⇒ is_expression_clause True（判定门不漂移）。"""
    if clause_reject_reason(clause, kind, ["x", "arr"]) is None:
        assert is_expression_clause(clause), clause


@settings(max_examples=400, deadline=None)
@given(
    pre=st.lists(_string_clause, max_size=4),
    post=st.lists(_string_clause, max_size=4),
    inv=st.lists(_string_clause, max_size=4),
)
def test_aggregate_matches_per_clause(pre: list[str], post: list[str], inv: list[str]) -> None:
    """聚合守恒：键集 ⊆ 闭集；无 *_expr 通道时聚合 == 逐条（空白不入分母不计数）。

    注意 spec 形状 = logic_analysis 层级（`_select_compile_channels` 直接从
    spec 读 preconditions/postconditions/invariants[*_expr]；nodes 侧调用
    传的即 `parse_logic_analysis(...)` 的产物）。
    """
    spec = {"preconditions": pre, "postconditions": post, "invariants": inv}
    counts = spec_reject_reasons(spec, ["x", "arr"])
    assert set(counts) <= SPEC_REJECT_REASONS, counts
    expected: dict[str, int] = {}
    for clause in pre:
        if not clause.strip():
            continue
        r = clause_reject_reason(clause, "precondition", ["x", "arr"])
        if r:
            expected[r] = expected.get(r, 0) + 1
    for clause in post + inv:
        if not clause.strip():
            continue
        r = clause_reject_reason(clause, "postcondition", ["x", "arr"])
        if r:
            expected[r] = expected.get(r, 0) + 1
    assert counts == expected, (counts, expected)


@pytest.mark.unit
class TestStripDriftRegression:
    """A-14 反例回归：strip 敏感的尾部控制分隔符（\\x1c-\\x1f，Python 视其为空白）
    下，形态门与归因门必须同口径——property 测试首跑反例 "0\\x1f" 的确定性锁定
    （修复：归因门/白名单调用统一走 strip 后文本）。"""

    @pytest.mark.parametrize("clause", ["0\x1f", "x == 1\x1e", "\x1cy == 2", "x == 1\x1d", "x == 1\x1f"])
    def test_control_separator_not_form_gate_reason(self, clause: str) -> None:
        """尾部控制分隔符不得引发"形态 True、归因 parse_error"漂移。"""
        reason = clause_reject_reason(clause, "precondition", ["x", "y"])
        if reason in _FORM_GATE_REASONS:
            assert not is_expression_clause(clause), (clause, reason)

    def test_control_separator_clause_is_compilable(self) -> None:
        # 修复前：is_expression_clause("0\x1f") 为 True 但归因 parse_error（门漂移）
        assert is_expression_clause("0\x1f")
        assert clause_reject_reason("0\x1f", "precondition", ["x"]) is None


@pytest.mark.unit
class TestLateParseGateDriftRegression:
    """H5 反例回归：**晚期 parse 门**不得回形态门家族标签。

    property 测试第二起反例（2026-10-16 H 轮，run 4 由 hypothesis 命中并入库回放）：
    ``"0,"``。尾随逗号让子句成为 1-元组——形态门、白名单门、``mode="eval"`` 解析
    全部通过，只有拼成 ``assert (0,)`` 语句时才 SyntaxError（且该断言恒真）。
    修复前该门返回 ``parse_error``，即"形态 True、归因形态门家族"的第二种门漂移
    （首起为 A-14 的 ``"0\\x1f"``）；现按 SPEC_REJECT_REASONS 文档改判
    ``unsupported_syntax``（= 可解析为表达式但编译产物是恒真断言）。

    本类把该反例钉成确定性用例：hypothesis 的例库若被清理，此处的覆盖不随之消失。
    """

    @pytest.mark.parametrize("clause", ["0,", "1 == 1,", "x > 0,", "x,"])
    def test_trailing_comma_is_backend_reason_not_form_gate(self, clause: str) -> None:
        """形态门判 True 的尾随逗号子句 → 归因必须落在后端家族。"""
        assert is_expression_clause(clause), clause
        reason = clause_reject_reason(clause, "precondition", ["x", "arr"])
        assert reason in _BACKEND_REASONS, (clause, reason)
        assert reason not in _FORM_GATE_REASONS, (clause, reason)

    def test_trailing_comma_is_unsupported_syntax(self) -> None:
        """精确标签：恒真断言族（与 lambda / 海象同族），非"语法错"。"""
        assert clause_reject_reason("0,", "precondition", ["x"]) == "unsupported_syntax"

    def test_legitimate_comma_clauses_still_compile(self) -> None:
        """改正不得波及合法逗号形态（元组成员 / 调用实参 / in 元组）。"""
        for clause in ("x in (1, 2, 3)", "isinstance(x, int)", "max(x, arr) > 0"):
            assert clause_reject_reason(clause, "precondition", ["x", "arr"]) is None, clause
