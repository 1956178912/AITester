#!/usr/bin/env python3
"""R 轮覆盖率补齐：示例自校验 safe-AST 求值分支 + 示例编译边界。

背景：R-2 新增 `self_validate_examples`（约 180 行源码）使全量行覆盖
96.52%→96.30%（低于 ratchet 水位 96.40%）。本文件只补既有分支（不改产品语义），
确保 ratchet 只升不降。R-3 的 run_benchmark 属 experiments/ 不在 --cov=src 范围。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.specs.spec_ir import parse_logic_analysis
from src.specs.spec_ir_v2 import (
    _compile_example_assertions,
    compile_spec_oracle,
    evaluate_guarded_expression,
    self_validate_examples,
)


class TestGuardedExpressionBranches:
    @pytest.mark.parametrize(
        ("expr", "env", "expected"),
        [
            ("5", {}, (True, 5)),
            ("3.5", {}, (True, 3.5)),
            ("'s'", {}, (True, "s")),
            ("None", {}, (True, None)),
            ("True", {}, (True, True)),
            ("x", {"x": 7}, (True, 7)),
            ("[1, x]", {"x": 2}, (True, [1, 2])),
            ("(1, x)", {"x": 3}, (True, (1, 3))),
            ("not x", {"x": False}, (True, True)),
            ("-x", {"x": 4}, (True, -4)),
            ("+x", {"x": 4}, (True, 4)),
            ("x and y", {"x": 1, "y": 2}, (True, 2)),
            ("x and y", {"x": 0, "y": 2}, (True, 0)),
            ("x or y", {"x": 0, "y": 3}, (True, 3)),
            ("x or y", {"x": 5, "y": 0}, (True, 5)),
            ("x + y", {"x": 2, "y": 3}, (True, 5)),
            ("x - y", {"x": 5, "y": 3}, (True, 2)),
            ("x * y", {"x": 2, "y": 4}, (True, 8)),
            ("x / y", {"x": 8, "y": 2}, (True, 4.0)),
            ("x // y", {"x": 9, "y": 2}, (True, 4)),
            ("x % y", {"x": 9, "y": 2}, (True, 1)),
            ("x == y", {"x": 1, "y": 1}, (True, True)),
            ("x != y", {"x": 1, "y": 2}, (True, True)),
            ("x < y", {"x": 1, "y": 2}, (True, True)),
            ("x <= y", {"x": 2, "y": 2}, (True, True)),
            ("x > y", {"x": 3, "y": 2}, (True, True)),
            ("x >= y", {"x": 2, "y": 2}, (True, True)),
            ("x in y", {"x": 1, "y": [1, 2]}, (True, True)),
            ("x not in y", {"x": 3, "y": [1, 2]}, (True, True)),
            ("x is y", {"x": None, "y": None}, (True, True)),
            ("x is not y", {"x": 1, "y": 2}, (True, True)),
            ("1 < x < 3", {"x": 2}, (True, True)),
            ("1 < x < 3", {"x": 5}, (True, False)),
            # 不可求值：白名单/名称/语法/长度/节点数
            ("x if y else 0", {"x": 1, "y": True}, (False, None)),
            ("len(x) == 1", {"x": [1]}, (False, None)),
            ("x.attr", {"x": 1}, (False, None)),
            ("x[0]", {"x": [1]}, (False, None)),
            ("lambda: 1", {}, (False, None)),
            ("[i for i in x]", {"x": [1]}, (False, None)),
            ("{'a': 1}", {}, (False, None)),
            ("{1, 2}", {}, (False, None)),
            ("y", {"x": 1}, (False, None)),
            ("x / 0", {"x": 1}, (False, None)),
            ("(", {}, (False, None)),
            ("", {}, (False, None)),
            (None, {}, (False, None)),
            ("a" * 600, {}, (False, None)),
            ("-" * 250 + "x", {"x": 1}, (False, None)),
        ],
    )
    def test_expression_matrix(self, expr: Any, env: dict[str, Any], expected: tuple[bool, Any]) -> None:
        evaluable, value = evaluate_guarded_expression(expr, env)
        assert (evaluable, value) == expected

    def test_unsupported_compare_op_returns_unevaluable(self) -> None:
        # ast.NotEq 等已覆盖；构造不在白名单的 op 走解析期白名单拒绝
        assert evaluate_guarded_expression("x @ y", {"x": 1, "y": 2}) == (False, None)


class TestSelfValidateAuditBranches:
    def _spec(self, post: list[str], pre: list[str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"function_name": "f", "postconditions_expr": post}
        if pre is not None:
            data["preconditions_expr"] = pre
        spec = parse_logic_analysis(data)
        assert spec is not None
        return spec

    def test_no_post_clause_returns_early(self) -> None:
        spec = self._spec([])
        kept, audit = self_validate_examples(spec, ["a"], [{"input": [1], "expected": 1}])
        assert len(kept) == 1 and audit["n_no_post_clause"] == 1

    def test_empty_and_none_inputs(self) -> None:
        spec = self._spec(["r >= 0"])
        assert self_validate_examples(None, None, None)[1]["n_input"] == 0
        assert self_validate_examples(spec, ["a"], "not-a-list")[1]["n_input"] == 0
        assert self_validate_examples(spec, ["a"], [{"bad": 1}, "x"])[1]["n_input"] == 0

    def test_precondition_false_kept_audit(self) -> None:
        spec = self._spec(["r >= 0"], pre=["a > 0"])
        kept, audit = self_validate_examples(spec, ["a"], [{"input": [-5], "expected": 0}])
        assert len(kept) == 1  # 前件 False 不丢弃（保守）
        assert audit["n_precondition_false_kept"] == 1

    def test_partially_validated_and_no_env(self) -> None:
        spec = self._spec(["isinstance(r, int)", "r >= 0"])
        # isinstance 不可求值、r>=0 可求值 → partially validated；不可机检子句保留
        kept, audit = self_validate_examples(spec, ["a"], [{"input": [1], "expected": 1}])
        assert len(kept) == 1 and audit["n_partially_validated"] == 1
        # 无变量映射（signature 与 input 不匹配）→ unevaluable 保留
        kept2, audit2 = self_validate_examples(spec, ["x", "y"], [{"input": [1], "expected": 2}])
        assert len(kept2) == 1 and audit2["n_unevaluable"] >= 1

    def test_partial_pass_then_contradiction_dropped(self) -> None:
        spec = self._spec(["r >= 0", "r == a"])
        kept, audit = self_validate_examples(spec, ["a"], [{"input": [5], "expected": 3}])
        assert kept == [] and audit["n_dropped"] == 1 and "postcondition_false" in audit["reasons"]


class TestCompileExampleBoundaryBranches:
    def test_invalid_examples_dropped(self) -> None:
        lines, stats = _compile_example_assertions(
            [
                "not-a-dict",
                {"input": [1]},
                {"expected": 1},
                {"input": [object()], "expected": 1},
                {"input": [1], "expected": 1},
            ],
            ["a"],
            "f",
        )
        assert stats["input"] == 5 and stats["dropped"] == 4
        assert len(lines) == 1

    def test_signature_none_rules(self) -> None:
        lines, stats = _compile_example_assertions([{"input": [1, 2], "expected": 3}], None, "f")
        assert lines == [] and stats["dropped"] == 1
        lines2, _ = _compile_example_assertions([{"input": 5, "expected": 6}], None, "f")
        assert len(lines2) == 1 and "f(5)" in lines2[0]

    def test_arity_zero_and_one_rules(self) -> None:
        lines0, _stats0 = _compile_example_assertions([{"input": [], "expected": 1}], [], "f")
        assert len(lines0) == 1 and "f()" in lines0[0]
        lines_bad, stats_bad = _compile_example_assertions([{"input": [1], "expected": 1}], [], "f")
        assert lines_bad == [] and stats_bad["dropped"] == 1
        # 单参：长度 1 list → f(x)；长度≠1 list → 兼容旧格式 f(list)
        lines1, _ = _compile_example_assertions([{"input": [9], "expected": 9}], ["a"], "f")
        assert len(lines1) == 1 and "f(9)" in lines1[0]
        lines2, _ = _compile_example_assertions([{"input": [[1, 2]], "expected": 3}], ["a"], "f")
        assert len(lines2) == 1 and "f([1, 2])" in lines2[0]
        lines3, _ = _compile_example_assertions([{"input": [1, 2, 3], "expected": 6}], ["a"], "f")
        assert len(lines3) == 1 and "f([1, 2, 3])" in lines3[0]

    def test_witness_binding_multiparam_branch(self, monkeypatch) -> None:
        from src.specs import spec_ir_v2 as v2

        monkeypatch.setattr(v2, "_precondition_witness_binding", lambda pre, params: {"a": 1, "b": 2})
        spec = parse_logic_analysis(
            {
                "function_name": "add",
                "preconditions": ["a > 0", "b > 0"],
                "preconditions_expr": ["a > 0", "b > 0"],
                "postconditions_expr": ["r == a + b"],
            }
        )
        assert spec is not None
        code = compile_spec_oracle(spec, "target_mod", "add", signature_params=["a", "b"])
        assert "a, b = 1, 2" in code or "a = 1" in code
        assert "r == a + b" in code or "assert" in code
