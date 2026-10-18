"""T3c（2026-10-18）：spec_smt 后件 ``result`` → ``r`` 别名归一修复测试。

背景（T3b 实测）：SpecIR 表达式通道契约要求后件结果变量写 ``result``，
而 ``spec_smt._collect_post_constraints`` 的自由变量域为 ``{"r"}``——含
``result`` 的后件/不变式子句在排序推断的"自由名必须属于自由变量域"门被
整体保守拒绝（T3b 批 110/166 expr error 子句即此因，占 66%）。

本文件锁定修复口径：
- 仅后件/不变式组做 token 感知（AST Name 节点）归一，前件路径零变化；
- 参数名确实为 ``result`` 时不归一（历史行为）；``r`` 形式子句逐位不变；
- 归一后子句可达求解器（sat/unsat）；``usable_bool`` 保留原始子句文本；
- 解析失败/白名单拒绝仍走保守拒绝路径（不得因归一放行坏子句）。
"""

from __future__ import annotations

import logging

import pytest

from src.specs.spec_smt import (
    _RESULT_ALIAS_NAME,
    _RESULT_VAR_NAME,
    _normalize_result_alias,
    check_postcondition_consistency,
    check_precondition_vacuity,
    smt_available,
)

requires_z3 = pytest.mark.skipif(not smt_available(), reason="z3-solver 未安装（pip install aitester[formal]）")


class TestNormalizeHelper:
    def test_result_name_rewritten_to_r(self) -> None:
        assert _normalize_result_alias("result > 0") == "r > 0"
        assert _normalize_result_alias("0 <= result < 10") == "0 <= r < 10"

    def test_r_form_clause_bit_identical(self) -> None:
        # 无 result 出现 → 原样返回原文（逐位不变，不引入 ast.unparse 格式化漂移）
        for clause in ("r > 0", "r == 0 or n > 0", "a  %  b  ==  0"):
            assert _normalize_result_alias(clause) == clause

    def test_string_literal_and_attribute_not_rewritten(self) -> None:
        # token 感知：字符串字面量里的 "result" / 属性名 .result 不是 Name 节点
        assert _normalize_result_alias('result == "result"') == "r == 'result'"
        assert _normalize_result_alias("obj.result > 0") == "obj.result > 0"
        assert _normalize_result_alias("result") == "r"

    def test_parse_failure_conservative_fallback(self) -> None:
        # 语法不合法 → 保守回退原文（由上层既有形态门/白名单处理）
        assert _normalize_result_alias("result >") == "result >"
        assert _normalize_result_alias("result = 1") == "result = 1"
        assert _normalize_result_alias("") == ""


class TestCollectorBehavior:
    @requires_z3
    def test_collector_uses_normalized_sorts_and_keeps_original_text(self) -> None:
        import z3

        from src.specs import spec_smt

        spec = {"postconditions": ["result > 0", "r > 0"]}
        bundle = spec_smt._collect_post_constraints(spec, ["x"], z3)
        assert bundle is not None
        assert bundle[1] == {"r": "Int"}  # 排序推断用归一后子句
        assert bundle[2] == ["result > 0", "r > 0"]  # usable_bool 保留原始文本

    @requires_z3
    def test_param_named_result_is_not_normalized(self) -> None:
        import z3

        from src.specs import spec_smt

        # 签名参数确实叫 result → 不归一（防把输入变量改写为结果变量）
        bundle = spec_smt._collect_post_constraints({"postconditions": ["result > 0"]}, ["result"], z3)
        assert bundle is not None
        assert bundle[1] == {"result": "Int"}
        assert "r" not in bundle[1]


class TestPostconditionConsistency:
    @requires_z3
    def test_result_clause_reaches_solver_and_is_sat(self) -> None:
        result = check_postcondition_consistency({"postconditions": ["result > 0"]}, ["x"])
        assert result["status"] == "sat"
        assert result["clauses"] == 1
        assert _RESULT_VAR_NAME in result["variables"]  # 归一后自由结果变量为 r
        assert _RESULT_ALIAS_NAME not in result["variables"]

    @requires_z3
    def test_contradictory_result_clauses_are_unsat(self) -> None:
        result = check_postcondition_consistency({"postconditions": ["result > 0", "result < 0"]}, ["x"])
        assert result["status"] == "unsat"
        assert result["clauses"] == 2

    @requires_z3
    def test_result_and_r_are_the_same_variable(self, caplog: pytest.LogCaptureFixture) -> None:
        # result 与 r 混用 → 归一后同一变量：r == r 恒真（sat）
        assert check_postcondition_consistency({"postconditions": ["result == r"]}, ["x"])["status"] == "sat"
        # 归一失败未能同变量时该式可满足；同变量时 result-r==5 无解 → unsat
        with caplog.at_level(logging.WARNING):
            result = check_postcondition_consistency({"postconditions": ["result - r == 5"]}, ["x"])
        assert result["status"] == "unsat"
        # UNSAT 告警绑定**原始子句文本**（可解释性：不把 r 化文本当用户子句）
        assert "result - r == 5" in caplog.text

    @requires_z3
    def test_param_named_result_keeps_historical_behavior(self) -> None:
        result = check_postcondition_consistency({"postconditions": ["result > 0"]}, ["result"])
        assert result["status"] == "sat"
        assert result["variables"] == ["result"]  # 未归一：result 是输入参数

    @requires_z3
    def test_non_expression_and_whitelist_rejected_still_rejected(self) -> None:
        # 非表达式（中文 NL）→ skipped，clauses=0
        assert check_postcondition_consistency({"postconditions": ["后件是中文描述"]}, ["x"])["status"] == "skipped"
        # 白名单外调用（open）→ skipped，不得因归一放行
        rejected = check_postcondition_consistency({"postconditions": ["open('f').read() == result"]}, ["x"])
        assert rejected["status"] == "skipped"
        assert rejected["clauses"] == 0

    @requires_z3
    def test_precondition_path_unchanged(self) -> None:
        # 别名归一仅作用于后件组：前件含 result 仍按历史口径保守跳过
        assert check_precondition_vacuity({"preconditions": ["result > 0"]}, ["x"])["status"] == "skipped"
        # 前件正常表达式行为不变
        assert check_precondition_vacuity({"preconditions": ["x > 0"]}, ["x"])["status"] == "sat"
