#!/usr/bin/env python3
"""覆盖率补口 + 安全护栏锁定：SpecExpr DSL 的 AST 白名单与自由变量分析。

动机（EMSE 多轮优化批次）：`src/specs/spec_ir_v2.py` 是"规格优先"主张的度量内核
（`spec_compile_rate` 由此产出），其 AST 白名单是**安全门**——v4 放行冒号/切片后
新增的两类暴露形态（lambda、海象）依赖 `visit_Lambda` / `visit_NamedExpr` 拦截。
这些分支此前未覆盖，属"安全门无测试"的高风险状态。

覆盖目标（coverage.xml 记录）：355、379、619、646-660、675、687-699、727 等行与对应分支。
全部用例纯 AST 分析，零 LLM、零网络、零子进程、确定性。
"""

from __future__ import annotations

import ast

import pytest

from src.specs.spec_ir_v2 import (
    _comprehension_target_names,
    _free_names,
    _lambda_param_names,
    _whitelist_check,
    clause_reject_reason,
    is_expression_clause,
)


class TestWhitelistVisitorGuards:
    """四类违例形态逐条锁定（每类都是"LLM 话术"进入规约的入口）。"""

    def test_lambda_is_rejected_by_design(self):
        """lambda 子句恒真（`assert lambda ...`）→ 一律拒，且不进 generic_visit。"""
        violations = _whitelist_check("(lambda x: x > 0)")
        assert any("lambda" in v for v in violations), violations

    def test_walrus_is_rejected_by_design(self):
        """海象赋值 `(x := 5)` 自 v2 起不是合法规约子句。"""
        violations = _whitelist_check("(y := 5) > 0")
        assert any("walrus" in v for v in violations), violations

    def test_attribute_escape_is_rejected(self):
        """属性白名单外的访问（如 `.__class__`）必须被拒。

        注意 `.real` / `.value` 等**在**白名单内（`_ALLOWED_ATTRS`），
        故用真正越界的 dunder 属性作为越界样例。
        """
        violations = _whitelist_check("obj.__class__ == int")
        assert any(v.startswith("attr_escape:") for v in violations), violations

    def test_allowlisted_numeric_attr_is_accepted(self):
        assert _whitelist_check("value.real > 0") == []

    def test_allowlisted_attribute_is_accepted(self):
        """白名单内属性（如 len 之外的既定项）不得误报。"""
        violations = _whitelist_check("len(items) > 0")
        assert violations == [], violations

    def test_opaque_call_form_is_rejected(self):
        """下标调用 / lambda 调用等 opaque 形态进 `dangerous_call:(opaque)`。"""
        violations = _whitelist_check("[f][0]() > 0")
        assert any("opaque" in v or "dangerous_call" in v for v in violations), violations

    def test_safe_expression_passes_clean(self):
        assert _whitelist_check("n >= 0 and result == n * 2") == []


class TestFormGateAndExpressionClause:
    """形态门（v4 语法面）与表达式子句识别。"""

    @pytest.mark.parametrize(
        "clause",
        ["a > 0", "n >= 0 and result == n", "items[0] == 1", "x in (1, 2, 3)", 's[0] == "a"'],
    )
    def test_accepted_expression_forms(self, clause: str):
        assert is_expression_clause(clause) is True, clause

    @pytest.mark.parametrize("clause", ["", "   ", None, 123, "如果 n 大于 0 则返回 n"])
    def test_non_expression_forms_rejected(self, clause: object):
        assert is_expression_clause(clause) is False, repr(clause)

    def test_slice_is_rejected_by_form_gate(self):
        """切片 `s[:3]` **不是**合法规约形态（v4 的冒号放行针对字符串字面量
        内容，而非 Python 切片语法）——按真实语义锁定，避免误以为支持。"""
        assert is_expression_clause("s[:3] == 'abc'") is False
        assert is_expression_clause("s[0:3] == 'abc'") is False

    def test_colon_inside_double_quoted_literal_is_allowed(self):
        """v4 放行的冒号形态：**双引号**字面量内的冒号（如键值/时间分隔）。

        单一引号 `'...'` **不在**字符白名单内（`_EXPR_TOKEN_RE` 只收 `"`）——
        这是可编译率的一个真实约束，按实际语义锁定并登记，避免误用。
        """
        assert is_expression_clause('sep == ":"') is True
        assert is_expression_clause('key == "a:b"') is True

    def test_single_quoted_literal_is_rejected_by_token_whitelist(self):
        """单引号字面量被形态门拒绝（已知约束，非缺陷）——LLM 产出单引号
        子句会降级为 NL 注释，故 spec_compile_rate 的分子不含此类子句。"""
        assert is_expression_clause("sep == ':'") is False
        assert is_expression_clause("s[0] == 'a'") is False

    def test_reject_reason_is_non_empty_for_prose(self):
        reason = clause_reject_reason("如果 n 大于 0，则返回值应为 n 的两倍", "postcondition")
        assert reason, "散文式子句必须给出拒绝原因"

    def test_reject_reason_empty_for_valid_clause_with_binding(self):
        """`result` 与 `n` 均需在绑定上下文内（signature_params）方可编译，
        否则归因为 `unknown_name`——这是"未绑定名"门的真实语义。"""
        assert clause_reject_reason("result == n * 2", "postcondition", ["n"]) is None
        assert clause_reject_reason("result == n * 2", "postcondition") == "unknown_name"

    @pytest.mark.parametrize("clause", ["0,", "1 == 1,", "x > 0,", "result > 0,"])
    def test_trailing_comma_hits_late_parse_gate(self, clause: str):
        """尾随逗号使子句成为 1-元组（恒真），拼成 `assert <tuple>` 缺 msg → SyntaxError。

        这是 `_clause_reject_reason_for_known` 的**晚期 parse 门**（eval 解析成功
        之后、拼 `assert` 语句再解析一次）唯一已知的确定性触发形态：形态门放行、
        白名单门放行、`mode="eval"` 也成功（逗号让它成为合法的元组表达式），
        只有语句级二次解析才失败。

        归因口径（H5，2026-10-16）：本门返回 **`unsupported_syntax`** 而非
        `parse_error`——按 SPEC_REJECT_REASONS 的文档，前者正是"可解析为表达式但
        编译产物是恒真断言"，与 lambda / 海象同族；后者意味着"语法错"，而此处
        形态门已判 True。改正前该标签冲撞违反 test_spec_expr_property 不变式 2。

        覆盖率意义：本门此前只能被 hypothesis 模糊测试碰运气命中，是修掉 config
        档位预设 env 泄漏（H1）之后**唯一残留**的行覆盖漂移源——连跑两次 CI 口径
        全量，逐行比对只差这 2 行（总行覆盖 92.9432% / 92.9314%，0.012pp）。补此
        确定性用例后两次全量逐行比对**零漂移**（15739/16934 两次逐位相同）。
        """
        assert clause_reject_reason(clause, "postcondition") == "unsupported_syntax", clause

    def test_late_parse_gate_is_distinguishable_from_unknown_name_gate(self):
        """显式绑定后仍走晚期 parse 门——排除"其实是被未绑定名门拒掉"的误读。"""
        assert clause_reject_reason("n >= 0,", "postcondition") == "unknown_name"
        assert clause_reject_reason("n >= 0,", "postcondition", ["n"]) == "unsupported_syntax"


class TestComprehensionTargetNames:
    def test_single_name_target(self):
        node = ast.parse("[x for x in range(3)]", mode="eval").body
        assert isinstance(node, ast.ListComp)
        assert _comprehension_target_names(node.generators[0].target) == {"x"}

    def test_tuple_target(self):
        node = ast.parse("[a + b for a, b in pairs]", mode="eval").body
        assert isinstance(node, ast.ListComp)
        assert _comprehension_target_names(node.generators[0].target) == {"a", "b"}

    def test_list_target(self):
        node = ast.parse("[a for [a] in nested]", mode="eval").body
        assert isinstance(node, ast.ListComp)
        assert _comprehension_target_names(node.generators[0].target) == {"a"}

    def test_starred_target_is_conservatively_ignored(self):
        """`*rest` 罕见形态保守不计入（引用时按未绑定拒绝）。"""
        node = ast.parse("[a for a, *rest in rows]", mode="eval").body
        assert isinstance(node, ast.ListComp)
        assert _comprehension_target_names(node.generators[0].target) == {"a"}

    def test_non_name_target_returns_empty(self):
        node = ast.parse("[1 for _ in range(1)]", mode="eval").body
        assert isinstance(node, ast.ListComp)
        assert _comprehension_target_names(node.generators[0].target) == {"_"}


class TestLambdaParamNames:
    def test_positional_and_kwonly_and_varargs(self):
        node = ast.parse("lambda a, b=1, *args, c, **kwargs: a", mode="eval").body
        assert isinstance(node, ast.Lambda)
        names = _lambda_param_names(node.args)
        assert {"a", "b", "args", "c", "kwargs"} <= set(names)

    def test_no_params(self):
        node = ast.parse("lambda: 1", mode="eval").body
        assert isinstance(node, ast.Lambda)
        assert _lambda_param_names(node.args) == frozenset()


class TestFreeNames:
    """自由变量分析：决定"子句是否引用未绑定名"（误判会导致合法规约被拒）。"""

    def test_simple_name_is_free(self):
        node = ast.parse("n + 1", mode="eval").body
        assert _free_names(node) == {"n"}

    def test_bound_name_is_not_free(self):
        node = ast.parse("n + 1", mode="eval").body
        assert _free_names(node, frozenset({"n"})) == set()

    def test_list_comp_target_binds_inside(self):
        node = ast.parse("[x * k for x in items]", mode="eval").body
        free = _free_names(node)
        assert "x" not in free
        assert {"items", "k"} <= free

    def test_dict_comp_key_and_value_are_scanned(self):
        node = ast.parse("{k: v for k, v in pairs}", mode="eval").body
        assert isinstance(node, ast.DictComp)
        free = _free_names(node)
        assert "k" not in free and "v" not in free
        assert "pairs" in free

    def test_lambda_body_binds_params_but_defaults_evaluate_outside(self):
        node = ast.parse("lambda x, y=outer: x + y", mode="eval").body
        free = _free_names(node)
        assert "x" not in free
        assert "outer" in free, "默认值在外层作用域求值，必须计入自由变量"

    def test_nested_comprehension_second_iter_sees_first_target(self):
        node = ast.parse("[a + b for a in xs for b in ys[a]]", mode="eval").body
        free = _free_names(node)
        assert "a" not in free and "b" not in free
        assert {"xs", "ys"} <= free

    def test_comprehension_condition_is_scanned(self):
        node = ast.parse("[x for x in xs if x > limit]", mode="eval").body
        free = _free_names(node)
        assert "limit" in free

    def test_generator_expression_is_supported(self):
        node = ast.parse("sum(x for x in xs)", mode="eval").body
        assert isinstance(node, ast.Call)
        free = _free_names(node)
        assert "xs" in free
