"""R-2 示例自校验过滤器测试（确定性后置子句校验；零 LLM/零网络）。

覆盖：
1. **安全求值硬边界**：拒绝 Call（含 len/isinstance/__import__）、属性访问、下标、
   lambda、推导式、dict/set、f-string/walrus；表达式长度上限与 AST 节点上限；
   名称缺失/除零等异常 → ``unevaluable``（保守放行）。
2. **post_false 过滤**：可机检后置子句为 False 的示例被丢弃并计原因；其余保留；
   多后置子句任一 False 即丢弃；前件 False 仅审计不丢弃。
3. **零变化**：无 examples / env 关闭 → 不过滤、产物零变化。
4. **审计计数**：enabled/n_input/n_kept/n_dropped/n_fully/n_partially/
   n_no_post_clause/n_unevaluable/n_precondition_false_kept/reasons 键位稳定。
5. **编译器集成**：丢弃的示例不进入 oracle 断言，保留的进入；header examples=N
   为过滤后条数；全部被丢且无其它材料 → 空串。
6. **2 个 hallucination 真实用例**（P-1 实际锚材料）：弱后置子句无法判定其
   期望值矛盾 → 过滤器**不命中**（诚实记录上界）；另加一个可机检矛盾的反例
   证明过滤器在规约表达力足够时有效。
7. **重放审计集成**：aggregate_arm 汇总 examples_self_validation 键。
"""

from __future__ import annotations

from typing import Any

import pytest

import experiments.oracle_examples_replay as p1
from src.specs.spec_ir_v2 import (
    compile_spec_oracle,
    evaluate_guarded_expression,
    examples_self_validation_enabled,
    self_validate_examples,
)

_TARGET_MOD = "r2_probe_mod"


def _spec(
    *,
    post: list[str] | None = None,
    pre: list[str] | None = None,
    examples: Any = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {"function_name": "f", "postconditions_expr": list(post or [])}
    if pre:
        spec["preconditions_expr"] = list(pre)
    if examples is not None:
        spec["examples"] = list(examples)
    return spec


def _compile(spec: dict[str, Any], params: list[str] | None = None) -> str:
    return compile_spec_oracle(spec, target_module=_TARGET_MOD, target_function="f", signature_params=params)


@pytest.fixture(autouse=True)
def _default_filter_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认开启（opt-out 语义）：测试基线显式清掉可能残留的关闭 env。"""
    monkeypatch.delenv("SPEC_EXAMPLES_SELF_VALIDATE", raising=False)


# ═══ 1. 安全求值硬边界 ═════════════════════════════════════════════════════
class TestGuardedEvalBoundaries:
    @pytest.mark.parametrize(
        "expr",
        [
            "__import__('os').system('true')",
            "len(result)",
            "isinstance(result, int)",
            "result.__class__",
            "arr[0]",
            "result[0]",
            "(lambda: 1)()",
            "[x for x in result]",
            "{x: 1 for x in result}",
            "f'{result}'",
        ],
    )
    def test_rejects_unsafe_constructs(self, expr: str) -> None:
        evaluable, value = evaluate_guarded_expression(expr, {"result": [1, 2], "arr": [1, 2]})
        assert evaluable is False
        assert value is None

    def test_rejects_over_length_expression(self) -> None:
        expr = "result" + " + 1" * 200
        assert len(expr) > 500
        assert evaluate_guarded_expression(expr, {"result": 1})[0] is False

    def test_rejects_over_node_budget(self) -> None:
        expr = "1" + "+1" * 150  # 301 字符 < 500，但 AST 节点数 > 200
        assert len(expr) < 500
        assert evaluate_guarded_expression(expr, {"result": 1})[0] is False

    def test_missing_name_unevaluable(self) -> None:
        assert evaluate_guarded_expression("unknown_name > 0", {"result": 1})[0] is False

    def test_exception_unevaluable(self) -> None:
        assert evaluate_guarded_expression("a / b > 0", {"a": 1, "b": 0})[0] is False

    @pytest.mark.parametrize(
        ("expr", "env", "expected"),
        [
            ("result >= 0", {"result": 1}, (True, True)),
            ("result >= 0", {"result": -1}, (True, False)),
            ("a + b == result", {"a": 2, "b": 3, "result": 5}, (True, True)),
            ("not (result == 0)", {"result": 4}, (True, True)),
            ("result in [1, 2, 3]", {"result": 2}, (True, True)),
            ("0 <= result <= 10", {"result": 10}, (True, True)),
            ("result is None", {"result": None}, (True, True)),
            ("result == [1, 2]", {"result": [1, 2]}, (True, True)),
            ("result == (1, 2)", {"result": (1, 2)}, (True, True)),
        ],
    )
    def test_whitelisted_expressions(self, expr: str, env: dict[str, Any], expected: tuple[bool, Any]) -> None:
        assert evaluate_guarded_expression(expr, env) == expected


# ═══ 2. post_false 过滤 ═════════════════════════════════════════════════════
class TestPostconditionFiltering:
    def test_post_false_example_dropped(self) -> None:
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 6}])
        kept, audit = self_validate_examples(spec, ["a", "b"])
        assert kept == []
        assert audit["n_dropped"] == 1
        assert audit["reasons"] == {"postcondition_false": 1}

    def test_post_true_example_kept(self) -> None:
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 5}])
        kept, audit = self_validate_examples(spec, ["a", "b"])
        assert len(kept) == 1
        assert audit["n_dropped"] == 0
        assert audit["n_fully_validated"] == 1

    def test_any_false_post_clause_drops(self) -> None:
        spec = _spec(
            post=["result >= 0", "result == a + b"],
            examples=[{"input": [2, 3], "expected": -5}],
        )
        kept, audit = self_validate_examples(spec, ["a", "b"])
        assert kept == []
        assert audit["reasons"] == {"postcondition_false": 1}

    def test_multi_param_input_mapping(self) -> None:
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 5}])
        _kept, audit = self_validate_examples(spec, ["a", "b"])
        assert audit["n_fully_validated"] == 1

    def test_single_param_args_list_unwrapped(self) -> None:
        spec = _spec(post=["result == x * 2"], examples=[{"input": [3], "expected": 6}])
        _kept, audit = self_validate_examples(spec, ["x"])
        assert audit["n_fully_validated"] == 1

    def test_r_and_result_alias(self) -> None:
        spec_r = _spec(post=["r == x"], examples=[{"input": [3], "expected": 3}])
        spec_result = _spec(post=["result == x"], examples=[{"input": [3], "expected": 3}])
        for spec in (spec_r, spec_result):
            _kept, audit = self_validate_examples(spec, ["x"])
            assert audit["n_fully_validated"] == 1

    def test_no_post_clause_kept(self) -> None:
        spec = _spec(examples=[{"input": [1], "expected": 2}])
        kept, audit = self_validate_examples(spec, ["x"])
        assert len(kept) == 1
        assert audit["n_no_post_clause"] == 1

    def test_unevaluable_post_kept(self) -> None:
        spec = _spec(post=["isinstance(result, int)"], examples=[{"input": [1], "expected": 2}])
        kept, audit = self_validate_examples(spec, ["x"])
        assert len(kept) == 1
        assert audit["n_unevaluable"] == 1

    def test_precondition_false_kept_with_audit(self) -> None:
        spec = _spec(
            pre=["x > 0"],
            post=["result == x"],
            examples=[{"input": [-1], "expected": -1}],
        )
        kept, audit = self_validate_examples(spec, ["x"])
        assert len(kept) == 1  # 前件 False 仅审计，不丢弃（保守放行）
        assert audit["n_precondition_false_kept"] == 1

    def test_env_off_disables_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_EXAMPLES_SELF_VALIDATE", "false")
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 6}])
        kept, audit = self_validate_examples(spec, ["a", "b"])
        assert len(kept) == 1
        assert audit["enabled"] is False
        assert audit["n_dropped"] == 0

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("0", False), ("false", False), ("off", False), ("true", True), ("1", True), ("garbage", True)],
    )
    def test_env_gate(self, monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
        monkeypatch.setenv("SPEC_EXAMPLES_SELF_VALIDATE", value)
        assert examples_self_validation_enabled() is expected

    def test_audit_keys_stable(self) -> None:
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 5}])
        _kept, audit = self_validate_examples(spec, ["a", "b"])
        assert set(audit) == {
            "enabled",
            "n_input",
            "n_kept",
            "n_dropped",
            "n_fully_validated",
            "n_partially_validated",
            "n_no_post_clause",
            "n_unevaluable",
            "n_precondition_false_kept",
            "reasons",
        }


# ═══ 3. 零变化与编译器集成 ═════════════════════════════════════════════════
class TestCompilerIntegration:
    def test_dropped_example_not_in_oracle(self) -> None:
        spec = _spec(
            post=["result == a + b"],
            examples=[
                {"input": [2, 3], "expected": 5},
                {"input": [2, 3], "expected": 6},  # 与后置矛盾 → 丢弃
            ],
        )
        code = _compile(spec, ["a", "b"])
        assert "examples=1" in code
        assert "_specir_norm_return(f(2, 3)) == _specir_norm_return(5)" in code
        assert "_specir_norm_return(6)" not in code

    def test_all_dropped_keeps_machine_checkable_post_channel(self) -> None:
        """示例全被丢：不进入 oracle 示例断言，但可编译后置子句通道仍保留。"""
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 6}])
        code = _compile(spec, ["a", "b"])
        assert "examples=" not in code
        assert "_specir_norm_return" not in code
        assert "assert r == a + b" in code  # 后置子句通道不受示例过滤影响

    def test_env_off_keeps_example(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_EXAMPLES_SELF_VALIDATE", "0")
        spec = _spec(post=["result == a + b"], examples=[{"input": [2, 3], "expected": 6}])
        code = _compile(spec, ["a", "b"])
        assert "examples=1" in code
        assert "_specir_norm_return(6)" in code

    def test_no_examples_zero_change(self) -> None:
        spec = _spec(post=["result == a + b"])
        code_on = _compile(spec, ["a", "b"])
        spec_off = dict(spec)
        spec_off["examples"] = []
        code_off = _compile(spec_off, ["a", "b"])
        assert code_on == code_off
        assert "examples=" not in code_on and "_specir_norm_return" not in code_on


# ═══ 4. 2 个 hallucination 真实用例（弱后置 → 不命中） + 可机检反例 ═════════
class TestHallucinationCases:
    def test_parenthesization_hallucination_not_caught_by_weak_post(self) -> None:
        """P-1 真实锚材料：post 仅 isinstance(result, bool) → '(((' 期望 True 不被拦截。"""
        spec = _spec(
            post=["isinstance(result, bool)"],
            examples=[{"input": ["((("], "expected": True}],
        )
        kept, audit = self_validate_examples(spec, ["parens"])
        assert len(kept) == 1
        assert audit["n_dropped"] == 0
        assert audit["n_unevaluable"] == 1

    def test_knapsack_hallucination_not_caught_by_weak_post(self) -> None:
        """P-1 真实锚材料：post 仅 isinstance(int)/result>=0 → 期望 0 不被拦截。"""
        spec = _spec(
            post=["isinstance(result, int)", "result >= 0"],
            examples=[{"input": [5, [[5, 10]]], "expected": 0}],
        )
        kept, audit = self_validate_examples(spec, ["capacity", "items"])
        assert len(kept) == 1
        assert audit["n_dropped"] == 0
        assert audit["n_partially_validated"] == 1  # result>=0 可求值 True；isinstance 不可机检

    def test_expressive_post_catches_contradiction(self) -> None:
        """反例：当规约把语义编码为可机检表达式时，幻觉期望会被拦截。"""
        spec = _spec(post=["result == 10"], examples=[{"input": [5, [[5, 10]]], "expected": 0}])
        kept, audit = self_validate_examples(spec, ["capacity", "items"])
        assert kept == []
        assert audit["reasons"] == {"postcondition_false": 1}


# ═══ 5. 重放审计集成 ═══════════════════════════════════════════════════════
def test_aggregate_arm_includes_filter_audit() -> None:
    audit = {
        "enabled": True,
        "n_input": 2,
        "n_kept": 1,
        "n_dropped": 1,
        "n_fully_validated": 1,
        "n_partially_validated": 0,
        "n_no_post_clause": 0,
        "n_unevaluable": 0,
        "n_precondition_false_kept": 0,
        "reasons": {"postcondition_false": 1},
    }
    task = {
        "task_id": "t",
        "injection": {},
        "examples_generation": {"status": "reused", "examples": [{"input": 1, "expected": 2}]},
        "examples_self_validation": audit,
        "conditions": {
            p1.CONDITION_A: {"status": "not_run", "counts": {}, "unclassifiable": {}},
            p1.CONDITION_B: {
                "status": "ok",
                "counts": {"correct": 1, "fp": 0, "silent": 0, "misguided": 0, "unavailable": 0},
                "n_oracle_tests": 1,
            },
        },
    }
    aggregate = p1.aggregate_arm([task])
    summary = aggregate["examples_self_validation"]
    assert summary["n_input"] == 2
    assert summary["n_dropped"] == 1
    assert summary["n_tasks_with_drop"] == 1
    assert summary["reasons"] == {"postcondition_false": 1}
