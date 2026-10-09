"""spec_smt 深层分支补齐（2026-10-08，76% → 90%+）。

补齐 test_spec_smt.py 未覆盖的深层分支（z3 已安装后全部可测）：
- _safe_eval 的 BoolOp 短路 / UnaryOp USub/UAdd / Compare/BinOp 越界 / Call 关键字；
- _infer_sorts 的布尔标记 / 排序冲突 / 浮点&除法升 Real / 语法错误；
- _translate 的常量/名称/布尔/一元/比较/二元各节点；
- _model_value 的非标量值；
- 防御性 except（翻译失败 / 见证复核失败）。
"""

from __future__ import annotations

import ast

import pytest
import z3

from src.specs import spec_smt

# ═══ 1. _safe_eval 深层分支（AST 节点越界 + 短路）═════════════════════════════


class TestSafeEvalDeepBranches:
    def test_expr_unwrap(self):
        node = ast.Expr(value=ast.Constant(value=42))
        assert spec_smt._safe_eval(node, {}) == 42

    def test_boolop_and_short_circuit(self):
        node = ast.BoolOp(op=ast.And(), values=[ast.Constant(False), ast.Constant(True)])
        assert spec_smt._safe_eval(node, {}) is False

    def test_boolop_or_short_circuit(self):
        node = ast.BoolOp(op=ast.Or(), values=[ast.Constant(True), ast.Constant(False)])
        assert spec_smt._safe_eval(node, {}) is True

    def test_unary_usub_and_uadd(self):
        assert spec_smt._safe_eval(ast.UnaryOp(op=ast.USub(), operand=ast.Constant(5)), {}) == -5
        assert spec_smt._safe_eval(ast.UnaryOp(op=ast.UAdd(), operand=ast.Constant(5)), {}) == 5

    def test_unary_invert_rejected(self):
        node = ast.UnaryOp(op=ast.Invert(), operand=ast.Constant(1))
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._safe_eval(node, {})

    def test_compare_in_rejected(self):
        node = ast.Compare(left=ast.Constant(1), ops=[ast.In()], comparators=[ast.Constant([1])])
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._safe_eval(node, {})

    def test_binop_bitwise_rejected(self):
        node = ast.BinOp(left=ast.Constant(1), op=ast.BitOr(), right=ast.Constant(2))
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._safe_eval(node, {})

    def test_call_keywords_rejected(self):
        node = ast.Call(
            func=ast.Name(id="abs"),
            args=[ast.Constant(-1)],
            keywords=[ast.keyword(arg="x", value=ast.Constant(1))],
        )
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._safe_eval(node, {})


# ═══ 2. _infer_sorts 深层分支（布尔标记 / 冲突 / 升 Real）══════════════════════


class TestInferSortsDeepBranches:
    def test_bool_bare_name(self):
        sorts = spec_smt._infer_sorts(["flag"], frozenset({"flag"}))
        assert sorts == {"flag": "Bool"}

    def test_bool_compare_true(self):
        sorts = spec_smt._infer_sorts(["flag == True"], frozenset({"flag"}))
        assert sorts["flag"] == "Bool"

    def test_bool_numeric_conflict(self):
        # x 被 "x and y" 标记 Bool，又作为 "x / y" 的 Div 操作数升 Real
        # → Bool×Real 冲突（_meet 返回 False）→ 整体不可翻译 → None
        assert spec_smt._infer_sorts(["x / y > 0", "x and y"], frozenset({"x", "y"})) is None

    def test_float_compare_promotes_real(self):
        sorts = spec_smt._infer_sorts(["x > 0.5"], frozenset({"x"}))
        assert sorts["x"] == "Real"

    def test_div_promotes_real(self):
        sorts = spec_smt._infer_sorts(["x / y > 0"], frozenset({"x", "y"}))
        assert sorts["x"] == "Real"
        assert sorts["y"] == "Real"

    def test_boolop_marks_operands(self):
        sorts = spec_smt._infer_sorts(["x and y"], frozenset({"x", "y"}))
        assert sorts == {"x": "Bool", "y": "Bool"}

    def test_not_marks_operand_bool(self):
        sorts = spec_smt._infer_sorts(["not flag"], frozenset({"flag"}))
        assert sorts["flag"] == "Bool"

    def test_free_name_returns_none(self):
        assert spec_smt._infer_sorts(["r > 0"], frozenset({"x"})) is None

    def test_syntax_error_returns_none(self):
        assert spec_smt._infer_sorts(["x >"], frozenset({"x"})) is None

    def test_mark_bool_usub_operand(self):
        # "-x" 的 USub 操作数 bool_ctx=False，不标记 Bool → 保持 Int
        sorts = spec_smt._infer_sorts(["-x > 0"], frozenset({"x"}))
        assert sorts["x"] == "Int"

    def test_float_promote_conflict(self):
        # x 被 bare 子句标记 Bool，又作为 Compare 左值与 float 比较升 Real → 冲突 None
        assert spec_smt._infer_sorts(["x", "x > 0.5"], frozenset({"x"})) is None

    def test_div_promote_conflict(self):
        # x 被标记 Bool，又作为 Div 操作数升 Real → 冲突 None
        assert spec_smt._infer_sorts(["x", "x / y > 0"], frozenset({"x", "y"})) is None


# ═══ 3. _translate 深层分支（常量/名称/布尔/一元/比较/二元）════════════════════


class TestTranslateDeepBranches:
    def test_constant_str_rejected(self):
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(ast.Constant(value="hello"), {}, z3)

    def test_name_not_in_sorts_rejected(self):
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(ast.Name(id="x"), {}, z3)

    def test_boolop_or(self):
        node = ast.BoolOp(op=ast.Or(), values=[ast.Constant(True), ast.Constant(False)])
        expr = spec_smt._translate(node, {}, z3)
        # Or(True, False) 经 simplify 后为字面 True
        assert z3.is_true(z3.simplify(expr))

    def test_unary_not_and_usub(self):
        not_node = ast.UnaryOp(op=ast.Not(), operand=ast.Constant(True))
        assert z3.is_false(z3.simplify(spec_smt._translate(not_node, {}, z3)))
        sub_node = ast.UnaryOp(op=ast.USub(), operand=ast.Constant(5))
        assert z3.simplify(spec_smt._translate(sub_node, {}, z3)) == -5

    def test_unary_unsupported_rejected(self):
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(ast.UnaryOp(op=ast.Invert(), operand=ast.Constant(1)), {}, z3)

    @pytest.mark.parametrize(
        "op_cls, comparator",
        [
            (ast.Eq, 1),
            (ast.NotEq, 1),
            (ast.Lt, 1),
            (ast.LtE, 1),
            (ast.Gt, 1),
            (ast.GtE, 1),
        ],
    )
    def test_compare_ops(self, op_cls, comparator):
        node = ast.Compare(left=ast.Constant(0), ops=[op_cls()], comparators=[ast.Constant(comparator)])
        expr = spec_smt._translate(node, {}, z3)
        assert expr is not None  # 六种比较操作符均成功翻译

    def test_compare_in_rejected(self):
        # comparators 合法（int 可翻译），op=In 走 else 抛 _Untranslatable
        node = ast.Compare(left=ast.Constant(1), ops=[ast.In()], comparators=[ast.Constant(1)])
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(node, {}, z3)

    @pytest.mark.parametrize("op_cls", [ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod])
    def test_binop_ops(self, op_cls):
        node = ast.BinOp(left=ast.Constant(6), op=op_cls(), right=ast.Constant(2))
        expr = spec_smt._translate(node, {}, z3)
        assert expr is not None  # 五种二元操作符均成功翻译

    def test_binop_bitwise_rejected(self):
        node = ast.BinOp(left=ast.Constant(1), op=ast.BitOr(), right=ast.Constant(2))
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(node, {}, z3)

    def test_translate_name_by_sort(self):
        # Int / Real / Bool 三种排序的 Name 翻译
        assert spec_smt._translate(ast.Name(id="n"), {"n": "Int"}, z3) is not None
        assert spec_smt._translate(ast.Name(id="x"), {"x": "Real"}, z3) is not None
        assert spec_smt._translate(ast.Name(id="f"), {"f": "Bool"}, z3) is not None


# ═══ 4. _model_value 非标量值 ══════════════════════════════════════════════════


class TestModelValueDeepBranches:
    def test_int_value(self):
        assert spec_smt._model_value(z3, z3.IntVal(5)) == 5

    def test_real_value_integer_denominator(self):
        assert spec_smt._model_value(z3, z3.RealVal("2")) == 2

    def test_real_value_fraction(self):
        assert spec_smt._model_value(z3, z3.RealVal("1/2")) == 0.5

    def test_bool_value(self):
        assert spec_smt._model_value(z3, z3.BoolVal(True)) is True
        assert spec_smt._model_value(z3, z3.BoolVal(False)) is False

    def test_string_value_rejected(self):
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._model_value(z3, z3.StringVal("hello"))


# ═══ 5. 见证生成的防御性分支（复核失败 / optimize 异常 / smt 缺失）════════════


class TestGenerateWitnessesDefensive:
    def test_smt_unavailable_returns_empty(self, monkeypatch):
        monkeypatch.setattr(spec_smt, "smt_available", lambda: False)
        spec = {"preconditions": ["x > 0"]}
        assert spec_smt.generate_spec_witnesses(spec, ["x"]) == []

    def test_witness_python_recheck_failure_dropped(self):
        # 见证复核：z3 模型值在 Python 下不满足子句 → 丢弃（返回 [] 或空）
        # 构造不可翻译的子句（如调用 len）→ _collect_pre_constraints 返回 None
        spec = {"preconditions": ["len(x) > 0"]}
        assert spec_smt.generate_spec_witnesses(spec, ["x"]) == []

    def test_unsupported_clause_skipped(self):
        # 白名单拦截 / 非表达式子句 → 无可翻译前件 → []
        spec = {"preconditions": ["os.system('ls')"]}
        assert spec_smt.generate_spec_witnesses(spec, ["x"]) == []


# ═══ 6. check_precondition_vacuity 防御性分支 ══════════════════════════════════


class TestCheckPreconditionVacuityDefensive:
    def test_smt_unavailable_skipped(self, monkeypatch):
        monkeypatch.setattr(spec_smt, "smt_available", lambda: False)
        assert spec_smt.check_precondition_vacuity({"preconditions": ["x > 0"]}, ["x"])["status"] == "skipped"

    def test_unsat_detected(self):
        # x > 0 and x < 0 → UNSAT（空洞规约）
        spec = {"preconditions": ["x > 0", "x < 0"]}
        result = spec_smt.check_precondition_vacuity(spec, ["x"])
        assert result["status"] == "unsat"


# ═══ 7. 剩余防御性分支（坏值回退 / 越界节点 / 属性访问）═══════════════════════


class TestRemainingDefensiveBranches:
    def test_max_witnesses_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("SPEC_SMT_MAX_WITNESSES", "abc")
        assert spec_smt._max_witnesses() == 3

    def test_translate_attribute_rejected(self):
        # Attribute 节点（非白名单）→ 函数末尾 raise _Untranslatable
        node = ast.Attribute(value=ast.Name(id="x"), attr="real")
        with pytest.raises(spec_smt._Untranslatable):
            spec_smt._translate(node, {"x": "Int"}, z3)


# ═══ 8. S11 配套：非 Bool 算术子句过滤（前件见证层）═══════════════════════════


class TestNonBoolClauseFiltering:
    """is_expression_clause 放宽后，算术子句（非 Bool）被前件见证层过滤。"""

    def test_pure_arithmetic_precondition_skipped(self):
        # "x + 1" 是算术表达式（非 Bool）→ 无有效前件约束 → []
        assert spec_smt.generate_spec_witnesses({"preconditions": ["x + 1"]}, ["x"]) == []

    def test_mixed_clauses_keep_bool_only(self):
        # 混合（比较 + 算术）→ 只保留 Bool 子句，clauses 不含算术
        witnesses = spec_smt.generate_spec_witnesses({"preconditions": ["x > 0", "x + 1"]}, ["x"])
        assert witnesses
        for w in witnesses:
            assert w["clauses"] == ["x > 0"]

    def test_bare_bool_precondition_witness(self):
        # bare bool 前件 "flag" → Bool 约束 → 生成见证（S11 修复后不再被误判）
        witnesses = spec_smt.generate_spec_witnesses({"preconditions": ["flag"]}, ["flag"])
        assert witnesses
        assert witnesses[0]["inputs"] == {"flag": True}
