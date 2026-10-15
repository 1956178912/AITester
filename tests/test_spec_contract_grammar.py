"""W2/T1（2026-10-11 独立评审落地）提示-文法契约 + 拒绝原因归因测试。

背景（CONSOLIDATED_REVIEW_AND_PLAN.md §3.3 / F14，独立评审真实 LLM 调用实测）：
    独立评审用真实 LLM 调用定位到"逻辑驱动"失效根因——planner 要求 LLM 产出
    规约时，LLM **系统性输出自然语言**（`preconditions[0] = "text 为 str 类型"`、
    `postconditions[0] = "成功时返回 int 类型结果"`），而 src/specs/spec_ir_v2.py
    的白名单编译器只接受形式表达式 → compile_spec_oracle 产出 0 字节、日志记
    "SpecIR v2 oracle 产物自检失败，保守丢弃"、全量 1,607 行里 spec_compile_rate
    中位数 0.200 / 47.6% 为 0。

本文件锁定本轮两处修复（纯字符串断言 + 纯函数调用，**零真实 LLM 调用**）：
    1. planner 规约提示里的 SpecExpr 文法段：BNF / 5 正例 / 5 反例 / 自检指令
       确实存在（防未来被删），且白名单终结符与编译器真实白名单逐字一致
       （防提示-文法契约再次漂移）；正例逐条真的可编译、反例逐条真的被拒
       且拒绝原因分类与提示标注一致；
    2. spec_ir_v2 的通道级失败归因：clause_reject_reason 与 _clause_is_compilable
       判定一致（单一事实源）、spec_reject_reasons 聚合计数与通道口径正确、
       空 / None 保守降级不抛异常、返回值可 JSON 序列化写入结果行。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.agents.planner import (
    SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES,
    SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES,
    SPEC_EXPR_GRAMMAR_SECTION,
    PlannerAgent,
)
from src.specs import compile_readiness
from src.specs.spec_ir_v2 import (
    SPEC_REJECT_REASONS,
    _ALLOWED_ATTRS,
    _ALLOWED_CALL_NAMES,
    _clause_is_compilable,
    _known_names_for_signature,
    _whitelist_check,
    clause_reject_reason,
    is_expression_clause,
    spec_expr_grammar_terminals,
    spec_reject_reasons,
)

# 测试用被测函数签名（绑定上下文 = {r} ∪ 参数名 ∪ 白名单名 ∪ 常量）
# v4（2026-10-15）：补 counts——字典读 API 正例 all(v > 0 for v in counts.values())
# 需要该绑定名（提示示例用真实感参数名，测试签名随之扩展）。
_PARAMS = ["a", "b", "text", "counts"]


# ─── 1. 提示段内容：BNF + 正反例 + 自检指令 ─────────────────────────────────


def test_prompt_section_contains_bnf_and_selfcheck() -> None:
    """文法段必须含 BNF 产生式与输出前自检指令（防未来被删）。"""
    section = SPEC_EXPR_GRAMMAR_SECTION
    assert "::=" in section, "文法段必须给出 BNF 产生式"
    for nonterminal in (
        "<clause>",
        "<or>",
        "<and>",
        "<not>",
        "<cmp>",
        "<arith>",
        "<term>",
        "<unary>",
        "<atom>",
        "<call>",
        "<func>",
        "<attr>",
    ):
        assert nonterminal in section, f"BNF 缺少产生式 {nonterminal}"
    # 三个 *_expr 字段名与"正例 / 反例 / 自检"三节标题必须点名
    for marker in ("preconditions_expr", "postconditions_expr", "invariants_expr", "正例", "反例", "输出前自检"):
        assert marker in section, f"文法段缺少 {marker}"


def test_prompt_section_renders_every_example() -> None:
    """10 正例 / 6 反例必须逐条出现在提示文本里（常量与提示绑定，不可只留常量）。"""
    section = SPEC_EXPR_GRAMMAR_SECTION
    assert len(SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES) == 10, "提示契约要求 10 个正例（v3 量化 + 字符串方法 + v4 切片/字典读 API/set）"
    assert len(SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES) == 6, "提示契约要求 6 个反例（v4 增 lambda 护栏反例）"
    for clause, _kind, _note in SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES:
        assert clause in section, f"正例未渲染进提示：{clause}"
    for clause, reason, _note in SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES:
        assert clause in section, f"反例未渲染进提示：{clause}"
        assert f"拒绝原因：{reason}" in section, f"反例未标注拒绝原因 {reason}：{clause}"


def test_prompt_section_names_operators_truthfully() -> None:
    """提示必须点名真实算子集：比较 / 布尔 / 链式比较 / result 语义 / 位运算告诫。"""
    section = SPEC_EXPR_GRAMMAR_SECTION
    for op in ("==", "!=", "<=", ">=", "and", "or", "not", "is not", "not in"):
        assert op in section, f"文法段缺少算子 {op}"
    # 真实失败形态（中文 NL 描述句）必须作为反例出现在提示里
    assert "text 为 str 类型" in section
    assert "成功时返回 int 类型结果" in section
    # 单引号 / 花括号 / f-string 等字符白名单边界必须写明（实测被拒）；
    # v4：冒号放行后的边界（切片与字符串内合法、lambda/海象被拒）也要写明
    assert "单引号" in section
    assert "切片" in section
    assert "lambda" in section
    assert "海象" in section
    assert "位运算符" in section
    # v3：白名单内字符串方法（正例侧点名）与白名单外方法（反例侧点名）都要在
    assert "startswith" in section
    assert "title" in section  # v3 反例：刻意不收的方法
    # 未知标识符反例照旧
    assert "total" in section
    # v3 量化产生式与循环变量作用域说明必须点名
    assert "<quant>" in section
    assert "all(" in section and "any(" in section


def test_bnf_claimed_operators_are_really_accepted() -> None:
    """BNF 里列出的算子 / atom 形态必须真的可编译（防提示承诺编译器不认的算子）。"""
    forms = (
        # <cmp>：比较 / 同一性 / 成员 / 链式比较
        "a == b",
        "a != b",
        "a < b",
        "a <= b",
        "a > b",
        "a >= b",
        "a is None",
        "a is not None",
        "a in [1, 2]",
        "a not in [1, 2]",
        "0 <= a < 10",
        # <or> / <and> / <not>
        "a > 0 and b > 0",
        "a == 0 or b == 0",
        "not a",
        # <arith> / <term> / <unary>
        "a + b == 0",
        "a - b == 0",
        "a * b == 0",
        "a / b == 1",
        "a // b == 0",
        "a % b == 0",
        "a**2 == 4",
        "-a < 0",
        # <atom>：下标 / 白名单属性 / 元组 / 列表字面量 / 白名单调用
        "a[0] == 1",
        "a.value == 1",
        "a.real > 0",
        "a.imag == 0",
        "(a, b) == (1, 2)",
        "a in [1, 2, 3]",
        "len(text) > 0",
        "abs(a) >= 0",
        "isinstance(a, int)",
        "0.5 < a",
        'text != ""',
        # v3（P0-A-1）：有限域量化（all/any 推导式；循环变量作用域内绑定）
        "all(x > 0 for x in a)",
        "any(x == b for x in a)",
        "not any(x < 0 for x in a)",
        "all(ch.isdigit() for ch in text)",
        "all(a >= 0 for i in range(len(a)))",
        "any(text[i] == b for i in enumerate(text))",
        # v3：字符串纯方法白名单
        'text.startswith("a")',
        'text.endswith("z")',
        'text.split(",") != []',
        '",".join(text) != ""',
        'text.strip() != ""',
        "text.lower() == text",
        "text.isdigit()",
        'text.replace("a", "b") != text',
        # v4（2026-10-15 批次六）：字符串 is* 家族补全 + 字典读 API + set/sum/bool/hasattr
        "text.isupper()",
        "text.islower() or text.isupper()",
        "len(counts) == len(counts.keys())",
        "all(v > 0 for v in counts.values())",
        "counts.get(a, 0) >= 0",
        "len(set(a)) == len(a)",
        "sum(a) >= 0",
        "bool(a) is True",
        'hasattr(a, "x") or a is None',
        # v4：切片（冒号入字符类；负步长 / 开边界 / 嵌套调用上界均合法）
        "text[0:2] == \"ab\"",
        "text[:2] == \"ab\"",
        "text[1:] == \"bc\"",
        "text[::-1] == \"ba\"",
        "text[:len(text) - 1] == \"a\"",
        "a[0:1] == (1,)",
        # v3：迭代域白名单内建（range/enumerate 单独出现亦无害）
        "range(3) == range(3)",
    )
    known = _known_names_for_signature(_PARAMS)
    for form in forms:
        assert _clause_is_compilable(form, "postcondition", known), f"BNF 声称支持但编译器拒绝：{form}"
        assert clause_reject_reason(form, "postcondition", _PARAMS) is None, f"BNF 声称支持但被归因拒绝：{form}"


# ─── 2. 提示白名单 == 编译器真实白名单（防漂移）─────────────────────────────


def test_prompt_grammar_terminals_match_compiler_whitelist() -> None:
    """BNF 里的 <func> / <attr> 必须与 spec_ir_v2 的真实白名单逐字一致。

    这是 F14 根因（提示-文法契约断裂）的永久回归防线：白名单由
    spec_expr_grammar_terminals() 从代码常量渲染，下一轮扩文法时提示自动跟随。
    """
    terminals = spec_expr_grammar_terminals()
    assert terminals["calls"] == sorted(_ALLOWED_CALL_NAMES)
    assert terminals["attrs"] == sorted(_ALLOWED_ATTRS)
    # v4（2026-10-15 批次六）：+ sum/set/bool/hasattr（纯内建，diag3 实测）
    assert terminals["calls"] == [
        "abs",
        "all",
        "any",
        "bool",
        "enumerate",
        "float",
        "hasattr",
        "int",
        "isinstance",
        "len",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
    ]
    # v4（2026-10-15 批次六）：+ 字典读 API（values/keys/items/get）+
    # 字符串 is* 家族补全（isupper/islower）+ 整数纯方法（bit_length）
    assert terminals["attrs"] == [
        "bit_length",
        "count",
        "endswith",
        "find",
        "get",
        "imag",
        "isalnum",
        "isalpha",
        "isdigit",
        "islower",
        "isspace",
        "isupper",
        "items",
        "join",
        "keys",
        "lower",
        "lstrip",
        "real",
        "replace",
        "rstrip",
        "split",
        "startswith",
        "strip",
        "upper",
        "value",
        "values",
    ]
    # v3（P0-A-1）：量化承载调用单独导出（planner BNF 的 <quant> 产生式渲染源）
    assert terminals["quantifiers"] == ["all", "any"]
    for name in terminals["calls"]:
        assert name in SPEC_EXPR_GRAMMAR_SECTION, f"提示未列出白名单函数 {name}"
    for attr in terminals["attrs"]:
        assert attr in SPEC_EXPR_GRAMMAR_SECTION, f"提示未列出白名单属性 {attr}"
    # S6b 实测补入的真实算子（提示必须包含，否则类型判定子句被系统性丢弃）
    assert "isinstance" in SPEC_EXPR_GRAMMAR_SECTION


# ─── 3. 提示正例：逐条真的可编译 ─────────────────────────────────────────────


@pytest.mark.parametrize(("clause", "kind", "_note"), SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES)
def test_prompt_positive_examples_are_compilable(clause: str, kind: str, _note: str) -> None:
    """提示里的每条正例都必须过形态门 + 白名单门 + 标识符门（契约不可自相矛盾）。"""
    assert is_expression_clause(clause), f"正例不是表达式形态：{clause}"
    assert _whitelist_check(clause) == [], f"正例有白名单违例：{clause}"
    assert _clause_is_compilable(clause, kind, _known_names_for_signature(_PARAMS)), f"正例不可编译：{clause}"
    assert clause_reject_reason(clause, kind, _PARAMS) is None, f"正例被归因为拒绝：{clause}"


# ─── 4. 提示反例：逐条真的被拒，且原因分类与标注一致 ────────────────────────


@pytest.mark.parametrize(("clause", "reason", "_note"), SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES)
def test_prompt_negative_examples_rejected_with_labeled_reason(clause: str, reason: str, _note: str) -> None:
    """提示里的每条反例都必须真的被拒，且提示标注的原因分类 == 代码真实归因。"""
    assert not _clause_is_compilable(clause, "postcondition", _known_names_for_signature(_PARAMS))
    assert clause_reject_reason(clause, "postcondition", _PARAMS) == reason
    assert reason in SPEC_REJECT_REASONS


def test_real_nl_failure_form_classified_natural_language() -> None:
    """F14 实测真实失败形态：中文自然语言规约 → 归因 natural_language。

    这是"47.6% 为 0 里有多少是 NL 形态"这一问题的判定内核：planner 产出的
    NL 子句必须能被标记为 NL 形态，而不是被笼统记为"不可编译"。
    """
    nl_clauses = ("text 为 str 类型", "成功时返回 int 类型结果")
    for clause in nl_clauses:
        assert is_expression_clause(clause) is False
        assert _clause_is_compilable(clause, "precondition", _known_names_for_signature(_PARAMS)) is False
        assert clause_reject_reason(clause, "precondition", _PARAMS) == "natural_language"
    # 混合规约（NL 通道回退口径）：两条 NL 子句全部归因 NL
    spec = {"preconditions": ["text 为 str 类型"], "postconditions": ["成功时返回 int 类型结果"]}
    assert spec_reject_reasons(spec) == {"natural_language": 2}
    assert compile_readiness(spec) == 0.0
    # 长中文句同样归 NL（内容信号优先于长度门，避免根因被 too_long 掩盖）
    long_nl = "该函数的输入参数必须满足以下全部条件" * 12
    # 断言与 _MAX_CLAUSE_LEN 单一事实源对账（防字面量漂移）
    from src.specs.spec_ir_v2 import _MAX_CLAUSE_LEN

    assert len(long_nl) > _MAX_CLAUSE_LEN
    assert clause_reject_reason(long_nl) == "natural_language"
    # 无空格中文短句恰好是合法 Python 标识符（能 parse）——仍必须归 NL，
    # 否则"能 parse ⇒ 形式子句"的判据会把最常见的 NL 形态误记为语法问题
    assert clause_reject_reason("文本必须为非空字符串") == "natural_language"
    # 反向边界：中文只出现在字符串字面量内时是**形式子句**被字符白名单拦下
    assert clause_reject_reason('text != "你好"') == "unsupported_syntax"


def test_reject_reason_taxonomy_is_closed() -> None:
    """归因返回值必须落在闭合集合内（下游 schema 可据此校验）。"""
    expected = {
        "natural_language",
        "unsupported_syntax",
        "unsupported_operator",
        "unknown_name",
        "parse_error",
        "too_long",
        "empty",
        "not_a_string",
    }
    assert set(SPEC_REJECT_REASONS) == expected
    observed = {clause_reject_reason(c, "postcondition", _PARAMS) for c in _CONSISTENCY_CORPUS}
    observed.discard(None)
    assert {
        "natural_language",
        "unsupported_syntax",
        "unsupported_operator",
        "unknown_name",
        "parse_error",
        "too_long",
        "empty",
    } <= observed
    assert observed <= SPEC_REJECT_REASONS


# ─── 5. 归因与判定一致（单一事实源）+ 聚合计数 ──────────────────────────────

# 覆盖全部分类的语料（含实测真实失败形态、字符白名单边界、白名单外算子、未绑定名）
_CONSISTENCY_CORPUS = (
    "b != 0",  # 可编译
    "len(text) > 0",  # 可编译
    "result == a + b",  # 可编译（后置/不变量）
    "0 <= a < 10",  # 可编译（链式比较）
    "text 为 str 类型",  # natural_language（真实失败形态）
    "文本必须为非空字符串",  # natural_language（无空格中文句：恰好是合法标识符，能 parse）
    "text is str type",  # natural_language（ASCII 散文，英文 NL 兜底）
    "a && b",  # parse_error（语法错）
    "result = a + b",  # parse_error（赋值不是表达式）
    "r == total",  # unknown_name
    'result.title() == "Abc"',  # unsupported_operator（v3：title 刻意不入白名单）
    'open("x")',  # unsupported_operator
    "a == 'x'",  # unsupported_syntax（单引号字符串）
    'result == {"a": 1}',  # unsupported_syntax（v4：冒号已放行，花括号字典字面量仍被字符门拦下）
    "lambda r: r > 0",  # unsupported_syntax（v4 护栏：lambda 子句无断言语义）
    "(x := 5)",  # unsupported_syntax（v4 护栏：海象赋值）
    'text != "你好"',  # unsupported_syntax（形式子句被字符白名单拦下，非 NL）
    "x" * 201,  # too_long（201 个 'x' 拼接：可解析 + 单条 >200 字符，长度门命中）
    "",  # empty
    # v4：切片形态（冒号放行后归"可编译"——与 _CONSISTENCY_CORPUS 的判定一致性
    # 由 test_reject_reason_none_iff_compilable 全覆盖，此处显式记录迁移事实）
    "text[0:2] == \"ab\"",
    "result == text[::-1]",
)


def test_reject_reason_none_iff_compilable() -> None:
    """clause_reject_reason 与 _clause_is_compilable 必须同判（重构后单一事实源）。"""
    known = _known_names_for_signature(_PARAMS)
    for kind in ("precondition", "postcondition", "invariant"):
        for clause in _CONSISTENCY_CORPUS:
            reason = clause_reject_reason(clause, kind, _PARAMS)
            assert (reason is None) is _clause_is_compilable(clause, kind, known), f"判定/归因不一致：{clause!r}"
            if reason is not None:
                assert reason in SPEC_REJECT_REASONS


def test_result_alias_scope_matches_prompt_claim() -> None:
    """提示声称 result 只用于后置 / 不变量：前置条件里出现 result 必须被拒。"""
    assert clause_reject_reason("result == a + b", "precondition", ["a", "b"]) == "unknown_name"
    assert clause_reject_reason("result == a + b", "postcondition", ["a", "b"]) is None
    assert clause_reject_reason("result == a + b", "invariant", ["a", "b"]) is None


def test_spec_reject_reasons_aggregates_mixed_spec() -> None:
    """混合规约的聚合计数正确，且与 compile_readiness 对账。"""
    spec: dict[str, Any] = {
        # 前置：1 条可编译 + 1 条 NL + 1 条 result 越界（前置无结果变量）
        "preconditions_expr": ["b != 0", "text 为 str 类型", "result == a + b"],
        # 后置：1 条可编译 + 1 条未绑定名 + 1 条空白（不进分母）
        "postconditions_expr": ["result == a + b", "r == total", "   "],
    }
    # 5 条非空子句，2 条可编译 → 3 条被拒，其中 1 条 NL、2 条未绑定标识符
    assert spec_reject_reasons(spec, _PARAMS) == {"natural_language": 1, "unknown_name": 2}
    assert compile_readiness(spec, _PARAMS) == pytest.approx(2 / 5)
    # 对账：非空子句数 - 被拒数 == 可编译数
    nonblank = 5
    compiled = nonblank - sum(spec_reject_reasons(spec, _PARAMS).values())
    assert compile_readiness(spec, _PARAMS) == pytest.approx(compiled / nonblank)


def test_reject_reasons_follow_consumed_channel() -> None:
    """归因与 compile_readiness 同通道口径：*_expr 存在时不看 NL 通道，反之回退。"""
    spec = {"preconditions": ["text 为 str 类型"], "preconditions_expr": ["b != 0"]}
    assert spec_reject_reasons(spec, ["b"]) == {}
    assert compile_readiness(spec, ["b"]) == 1.0
    # 表达式通道为空（[]）→ 回退 NL 通道 → NL 子句被归因（历史口径）
    fallback = {"preconditions": ["text 为 str 类型"], "preconditions_expr": []}
    assert spec_reject_reasons(fallback) == {"natural_language": 1}
    assert compile_readiness(fallback) == 0.0


def test_reject_reasons_respect_signature_binding() -> None:
    """签名三态口径与 compile_readiness 一致（0 参函数里参数名不可绑定）。"""
    spec = {"preconditions_expr": ["b != 0"]}
    assert spec_reject_reasons(spec, ["b"]) == {}
    assert spec_reject_reasons(spec, []) == {"unknown_name": 1}
    assert spec_reject_reasons(spec, None) == {}  # None = 历史默认集合含 b
    assert compile_readiness(spec, []) == 0.0


@pytest.mark.parametrize(
    "spec",
    [
        None,
        {},
        {"preconditions_expr": []},
        {"preconditions": ["", "   "]},
        {"postconditions_expr": ["", None]},
        {"preconditions_expr": [None, 123]},
    ],
)
def test_reject_reasons_conservative_on_empty_or_polluted_spec(spec: Any) -> None:
    """空规约 / None / 空白 / 类型污染 → 保守降级，不抛异常、不进计数。"""
    assert spec_reject_reasons(spec) == {}
    assert compile_readiness(spec) == 0.0


def test_clause_reject_reason_handles_non_string_and_blank() -> None:
    """非 str / 空白子句的归因不抛异常（上游类型污染的兜底观测）。"""
    assert clause_reject_reason(None) == "not_a_string"
    assert clause_reject_reason(123) == "not_a_string"
    assert clause_reject_reason(["b != 0"]) == "not_a_string"
    assert clause_reject_reason("") == "empty"
    assert clause_reject_reason("   ") == "empty"


def test_reject_reasons_json_serializable_for_result_rows() -> None:
    """聚合结果必须可直接写入实验结果行（JSON 可序列化）。"""
    spec = {"preconditions_expr": ["b != 0", "text 为 str 类型"], "postconditions_expr": ["r == total"]}
    payload = json.dumps({"spec_reject_reasons": spec_reject_reasons(spec, _PARAMS)}, ensure_ascii=False)
    assert json.loads(payload)["spec_reject_reasons"] == {"natural_language": 1, "unknown_name": 1}
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in spec_reject_reasons(spec, _PARAMS).items())


# ─── 6. 提示注入门控（DSL 开关关 → prompt 零变化）──────────────────────────


def test_grammar_section_injected_iff_dsl_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPEC_IR_DSL_ENABLE=true 时文法段进查询；默认关时 prompt 零变化（ADR-0003）。"""
    raw_response = json.dumps(
        {
            "function_name": "divide",
            "description": "除法",
            "logic_analysis": {
                "input_domain": "数对",
                "output_domain": "商",
                "preconditions": ["b 不为零"],
                "preconditions_expr": ["b != 0"],
                "postconditions": [],
                "edge_cases": [],
            },
            "test_cases": [],
        },
        ensure_ascii=False,
    )
    captured: list[str] = []

    def fake_call(query: str, **_: Any) -> str:
        captured.append(query)
        return raw_response

    agent = PlannerAgent()
    monkeypatch.setattr(agent, "_call_llm_with_cache", fake_call)

    monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
    agent.plan("def divide(a, b):\n    return a / b\n", "divide")
    assert captured, "planner 未调用 LLM 桩"
    assert "::=" in captured[-1], "DSL 开启时文法段必须注入查询"
    assert "<clause>" in captured[-1]
    assert SPEC_EXPR_GRAMMAR_SECTION in captured[-1]

    captured.clear()
    monkeypatch.delenv("SPEC_IR_DSL_ENABLE", raising=False)
    agent.plan("def divide(a, b):\n    return a / b\n", "divide")
    assert captured, "planner 未调用 LLM 桩"
    assert "::=" not in captured[-1], "默认关时 prompt 必须零变化"
    assert SPEC_EXPR_GRAMMAR_SECTION not in captured[-1]


# ─── 7. v3（2026-10-12 P0-A-1）文法升阶：量化 / 字符串方法 / 作用域纪律 ──────


class TestV3QuantifierScoping:
    """有限域量化子句的可编译化 + 循环变量作用域纪律（防 NameError 假红断言）。"""

    @pytest.mark.parametrize(
        "clause",
        (
            "all(x > 0 for x in a)",
            "any(x == b for x in a)",
            "not all(x > 0 for x in a)",
            "all(ch.isdigit() for ch in text)",
            "all(a >= 0 for i in range(len(a)))",
            "all(a[i] > 0 for i in range(3))",
            "any(text[i] == b for i in enumerate(text))",
            "all(x > 0 for x in a) and any(x == b for x in a)",
        ),
    )
    def test_quantifier_clauses_compilable(self, clause: str) -> None:
        """全称 / 存在量化（all/any 推导式）在参数绑定时可编译。"""
        assert _clause_is_compilable(clause, "postcondition", _known_names_for_signature(_PARAMS)), clause
        assert clause_reject_reason(clause, "postcondition", _PARAMS) is None, clause

    @pytest.mark.parametrize(
        ("clause", "reason"),
        (
            # 推导式外引用循环变量 → 运行期 NameError，必须拒（防 gold 上假红）
            ("all(x > 0 for x in a) and x > 5", "unknown_name"),
            ("x > 0 and all(y > 0 for y in a)", "unknown_name"),
            # 迭代域含未绑定名 → 照旧拒
            ("all(x > 0 for x in items)", "unknown_name"),
            # 白名单外调用在量化体内照样被拦（不因扩文法放宽）
            ("all(open(x) for x in a)", "unsupported_operator"),
            ("all(x.system for x in a)", "unsupported_operator"),
        ),
    )
    def test_quantifier_scope_discipline(self, clause: str, reason: str) -> None:
        """作用域纪律：越界引用 / 危险调用在量化子句内仍被拒。"""
        assert clause_reject_reason(clause, "postcondition", _PARAMS) == reason, clause

    def test_quantifier_compiles_to_executable_assert(self) -> None:
        """量化子句经 compile_spec_oracle 产出 ast.parse 通过的可执行断言。"""
        import ast

        from src.specs.spec_ir_v2 import compile_spec_oracle

        spec = {
            "postconditions_expr": ["all(x > 0 for x in a)"],
            "boundaries": [{"input": [1, 2, 3]}],
        }
        code = compile_spec_oracle(spec, target_module="m", target_function="f", signature_params=["a"])
        assert code, "量化后置条件应产出 oracle"
        assert "assert all(x > 0 for x in a)" in code
        ast.parse(code)  # 产物必须可执行

    def test_nested_comprehension_scoping(self) -> None:
        """嵌套推导式：内层循环变量在内层体内绑定，不泄漏到外层自由名集合。"""
        # a[i][j]：i 外层绑定、j 内层绑定；text 为参数名——应可编译
        clause = "all(a[i][j] > 0 for i in range(len(a)) for j in range(len(a[i])))"
        assert _clause_is_compilable(clause, "postcondition", _known_names_for_signature(_PARAMS)), clause


class TestV3StringMethodWhitelist:
    """v3 字符串纯方法白名单（回应评审 C1：高频不可编译子句来源）。"""

    @pytest.mark.parametrize(
        "clause",
        (
            'text.startswith("a")',
            'text.endswith("z")',
            'text.split(",") != []',
            '",".join(text) != ""',
            'text.strip() != ""',
            'text.lstrip() != "" and text.rstrip() != ""',
            "text.lower() == text",
            "text.upper() != text",
            "text.isdigit()",
            "text.isalpha()",
            "text.isalnum()",
            "text.isspace()",
            'text.find("x") >= 0',
            'text.count("a") > 0',
            'text.replace("a", "b") != text',
            'result.startswith("ok")',
        ),
    )
    def test_string_methods_compilable(self, clause: str) -> None:
        """白名单内字符串纯方法全部可编译（含 result 别名归一）。"""
        assert _clause_is_compilable(clause, "postcondition", _known_names_for_signature(_PARAMS)), clause
        assert clause_reject_reason(clause, "postcondition", _PARAMS) is None, clause

    @pytest.mark.parametrize(
        ("clause", "reason"),
        (
            ('result.title() == "Abc"', "unsupported_operator"),
            ('result.center(10) == "abc"', "unsupported_operator"),
            ('result.encode() == b"x"', "unsupported_operator"),
            ('result.format() == "x"', "unsupported_operator"),
        ),
    )
    def test_non_whitelisted_methods_rejected(self, clause: str, reason: str) -> None:
        """刻意不收的方法（title/center/encode/format）照旧被拒（反例教学形态）。"""
        assert clause_reject_reason(clause, "postcondition", _PARAMS) == reason, clause

    def test_method_call_gate_no_double_reject(self) -> None:
        """方法调用不被调用名白名单二次拦截（T1b 同类同门冲突的 v3 修复）。"""
        assert _whitelist_check('text.startswith("a")') == []
        assert _whitelist_check('",".join(text)') == []
        # 非白名单属性链仍被拦
        assert any(v.startswith("attr_escape:") for v in _whitelist_check("text.title()"))

    def test_string_method_spec_aggregation(self) -> None:
        """含字符串方法子句的规约：归因为空、compile_readiness 满分。"""
        spec = {
            "preconditions_expr": ['text.startswith("a")'],
            "postconditions_expr": ['text.isdigit() or text == ""'],
        }
        assert spec_reject_reasons(spec, _PARAMS) == {}
        assert compile_readiness(spec, _PARAMS) == 1.0


# ─── 5. 内建类型名值位置放行（2026-10-14 EMSE SpecExpr 诊断批次） ───


class TestBuiltinTypeNamesValuePosition:
    """`isinstance(x, str)` 的类型名以裸 Name（参数位置）出现——调用白名单
    只覆盖调用位置，值位置的内建类型名须放行（运行期恒有定义，无 NameError
    假红风险）。2026-10-14 实测：合成集 *_expr 子句 str×6/int×7/list×1
    被误判 unknown_name。"""

    @pytest.mark.parametrize(
        ("clause", "params"),
        [
            ("isinstance(x, str)", ["x"]),
            ("isinstance(x, int) or isinstance(x, float)", ["x"]),
            ("isinstance(items, list) and len(items) > 0", ["items"]),
            ("isinstance(x, (int, float))", ["x"]),
            ("isinstance(text, str) and len(text) > 0", ["text"]),
        ],
    )
    def test_builtin_type_names_accepted_in_value_position(self, clause: str, params: list[str]) -> None:
        assert clause_reject_reason(clause, "precondition", params) is None, clause

    def test_non_builtin_unknown_name_still_rejected(self) -> None:
        """用户符号（模块级常量/未绑定名）照旧 unknown_name——不放宽危险面。"""
        assert clause_reject_reason("_STOCK[sku] == qty", "postcondition", ["sku", "qty"]) == "unknown_name"
        assert clause_reject_reason("total > 0", "postcondition", ["x"]) == "unknown_name"
        # 非白名单调用在算子门即被拦（dangerous_call），到不了标识符门
        assert clause_reject_reason("helper(x) > 0", "postcondition", ["x"]) == "unsupported_operator"

    def test_type_name_gate_does_not_leak_into_other_reasons(self) -> None:
        """类型名放行只影响标识符门；算子门/形态门不受影响。"""
        assert clause_reject_reason("x.title()", "postcondition", ["x"]) == "unsupported_operator"
        assert clause_reject_reason("x 为 str 类型", "precondition", ["x"]) == "natural_language"


# ─── 7. v4（2026-10-15 批次六）：切片 + lambda/海象护栏 + 白名单扩容 ──────────
# 实测依据：emse_dsl_diag3（719 Planner 缓存条目 / 607 去重子句，零 LLM）——
# unsupported_syntax 拒绝 5 条全部是冒号形态（4 切片 + 1 字符串内冒号）；
# 算子级违例 Top 为 sum×3 / set×3 / hasattr×2 / values×3 / isupper×1 /
# bit_length×1 / bool×1 / get×1。域名属性（successor/outgoing_nodes）与
# 模块链（collections.abc.Sequence）刻意不收（任意属性链 = 注入面）。
_V4_SLICE_FORMS = (
    "text[0:2] == \"ab\"",  # 闭边界
    "text[:2] == \"ab\"",  # 开下界
    "text[1:] == \"bc\"",  # 开上界
    "text[::-1] == \"ba\"",  # 负步长
    "text[:len(text) - 1] == \"a\"",  # 调用作上界
    "text[1:3] == text[0:2]",  # 双边切片比较
)


class TestV4SliceSupport:
    """v4：冒号入字符白名单——切片与双引号字符串内冒号可编译。"""

    @pytest.mark.parametrize("clause", _V4_SLICE_FORMS)
    def test_slice_forms_compile(self, clause: str) -> None:
        assert clause_reject_reason(clause, "postcondition", ["text"]) is None, clause

    def test_colon_inside_double_quoted_string_compiles(self) -> None:
        """字符串字面量内的冒号不再被字符门整体误拒（diag3 实测形态）。"""
        assert clause_reject_reason('result.startswith("result: ")', "postcondition", []) is None

    def test_single_quote_still_rejected(self) -> None:
        """单引号仍在字符门外（自检①要求字符串一律双引号，未放宽）。"""
        assert clause_reject_reason("a == 'x'", "postcondition", ["a"]) == "unsupported_syntax"

    def test_dict_literal_still_rejected(self) -> None:
        """花括号仍在字符门外——字典/集合字面量与 f-string 保守不收。"""
        assert clause_reject_reason('result == {"a": 1}', "postcondition", []) == "unsupported_syntax"
        assert clause_reject_reason('result == f"{a}"', "postcondition", ["a"]) == "unsupported_syntax"

    def test_slice_clause_compiles_to_assert_line(self) -> None:
        """切片子句必须真的注入为 assert 行（度量=注入，P0-3 单一事实源）。"""
        from src.specs.spec_ir_v2 import compile_spec_oracle

        spec = {"preconditions_expr": [], "postconditions_expr": ["result == text[::-1]"], "invariants_expr": []}
        code = compile_spec_oracle(spec, "m", "rev", signature_params=["text"])
        assert "assert r == text[::-1]" in code


class TestV4NoAssertSemanticsGuardrails:
    """v4 护栏：冒号放行后新暴露的两种无断言语义形态必须被拒（防假断言）。"""

    @pytest.mark.parametrize(
        "clause",
        [
            "lambda r: r > 0",  # 裸 lambda（BNF 无关键字参数产生式 ⇒ 只能裸出现）
            "lambda a, b: a > b",
            "(x := 5)",  # 海象赋值
            "text[0:2] == \"ab\" and (x := 1)",  # 嵌套海象
        ],
    )
    def test_lambda_and_walrus_rejected(self, clause: str) -> None:
        reason = clause_reject_reason(clause, "postcondition", ["a", "b", "text", "r"])
        assert reason == "unsupported_syntax", f"{clause} 应归 unsupported_syntax，实得 {reason}"

    def test_guardrail_reason_in_closed_set(self) -> None:
        assert clause_reject_reason("lambda r: r > 0", "postcondition", ["r"]) in SPEC_REJECT_REASONS

    def test_lambda_in_whitelist_check_reports_violation(self) -> None:
        from src.specs.spec_ir_v2 import _whitelist_check

        violations = _whitelist_check("lambda r: r > 0")
        assert any(v.startswith("no_assert_semantics:") for v in violations), violations

    def test_guardrail_does_not_block_ordinary_clauses(self) -> None:
        """护栏只拦 lambda/海象；普通子句（含推导式/比较/调用）不受影响。"""
        assert clause_reject_reason("all(x > 0 for x in a)", "invariant", ["a"]) is None
        assert clause_reject_reason("text[1:] != text", "postcondition", ["text"]) is None


class TestV4WhitelistExtensions:
    """v4 白名单扩容：纯内建调用 + 纯只读属性（逐条实测依据见模块 docstring）。"""

    @pytest.mark.parametrize(
        "clause",
        [
            "len(set(a)) == len(a)",  # set：去重判定（diag3 ×3）
            "sum(a) >= 0",  # sum（diag3 ×3）
            "bool(a) is True",  # bool（diag3 ×1）
            'hasattr(a, "x") or a is None',  # hasattr：鸭子类型（diag3 ×2）
            "all(v > 0 for v in counts.values())",  # values（diag3 ×3）
            "len(counts) == len(counts.keys())",  # keys（values 同族）
            "all(k in counts for k in counts.items())",  # items（values 同族）
            'counts.get(a, 0) >= 0',  # get（diag3 ×1）
            "text.isupper()",  # isupper（diag3 ×1）
            "text.islower() or text.isupper()",  # islower（isupper 同族）
            "result <= n.bit_length()",  # bit_length（diag3 ×1）
        ],
    )
    def test_new_whitelist_entries_compile(self, clause: str) -> None:
        assert clause_reject_reason(clause, "postcondition", ["a", "counts", "text", "n"]) is None, clause

    @pytest.mark.parametrize(
        "clause",
        [
            'counts.setdefault(a, 0)',  # 字典写方法刻意不收
            "counts.pop(a)",  # 字典写方法刻意不收
            "text.title()",  # v3 起刻意不收（反例教学形态）
            "node.successor",  # 域名属性：任意属性链是注入面（diag3 ×5）
            "collections.abc.Sequence",  # 模块链（diag3 实测）
            "heapq.heappushpop(a, b)",  # 模块链 + 非白名单调用
            "fibonacci(a - 1)",  # 被测函数自递归：语义扩展留待后续（diag3 ×4+1+1）
        ],
    )
    def test_deliberately_excluded_forms_still_rejected(self, clause: str) -> None:
        reason = clause_reject_reason(clause, "postcondition", ["a", "b", "node", "counts", "text"])
        assert reason == "unsupported_operator", f"{clause} 应归 unsupported_operator，实得 {reason}"

    def test_dangerous_calls_still_rejected_after_extension(self) -> None:
        """扩容不得放宽危险调用（既有哨兵，v4 复锁）。"""
        for bad in ("open('x')", "eval('1')", "exec('x')", "__import__('os')", "list(a)", "dict(a)"):
            assert _whitelist_check(bad) != [], bad
