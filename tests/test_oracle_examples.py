"""P-1 规格可执行示例通道契约测试（examples 解析/编译/生成器/重放/自含检出 demo）。

覆盖五块（≥25 例）：
1. **数据通道**（`src/specs/spec_ir.py`）：`examples` 透传、≤5 截断、非法形状
   丢弃不抛、空示例不写键、NaN/非字面量/非 JSON 形态拒绝、schema 校验 findings。
2. **编译器**（`src/specs/spec_ir_v2.compile_spec_oracle`）：逐示例断言
   （单参/多参/0 参/签名未知）、repr 字面量、零 eval/exec、同一崩溃安全
   harness（AssertionError re-raise、Exception→skip）、示例优先于退化绑定、
   非法示例丢弃、**无示例产物与 O-1 逐字节不变**。
3. **生成器**（`experiments/spec_examples_generator.py`）：spec-only prompt
   （不含缺陷代码）、strict JSON（围栏/裸 list/前后文本）、非法 schema 降级
   空+原因、LLM 失败透传 error、usage/token 快照差、cache namespace 设置与
   恢复、价目表成本估算（缺失不编造）。
4. **重放工具**（`experiments/oracle_examples_replay.py`）：任务过滤/驱动任务
   开关/limit、A/B 条件聚合计数、任务级类别优先级与 A→B 转移、示例注入
   SpecIR（`_build_spec`）与无示例清理。
5. **自含检出 demo**：buggy/fixed fixture 证明"无示例 oracle 不检出、加正确
   示例 oracle 检出"（通道具备检出能力，而非"全 skip 假安全"）。

零 LLM/零网络（生成器 LLM 全部 mock）。
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import experiments.oracle_examples_replay as p1
import experiments.spec_examples_generator as gen
from src.specs.spec_ir import parse_examples, parse_logic_analysis, validate_spec_ir
from src.specs.spec_ir_v2 import compile_spec_oracle, normalize_return_value

_TARGET_MOD = "p1_probe_mod"


# ─── 工具 ──────────────────────────────────────────────────────────────────
def _spec(
    *, pre_expr: list[str] | None = None, post_expr: list[str] | None = None, examples: Any = None
) -> dict[str, Any]:
    spec: dict[str, Any] = {"function_name": "f"}
    if pre_expr:
        spec["preconditions_expr"] = list(pre_expr)
    if post_expr:
        spec["postconditions_expr"] = list(post_expr)
    if examples is not None:
        spec["examples"] = examples
    return spec


def _compile(spec: dict[str, Any], params: list[str] | None = None) -> str:
    return compile_spec_oracle(spec, target_module=_TARGET_MOD, target_function="f", signature_params=params)


def _exec_oracle(code: str, module_attrs: dict[str, Any]) -> dict[str, Any]:
    """受控命名空间 exec 生成的 oracle 代码（被测模块以 sys.modules 桩注入）。"""
    module = types.ModuleType(_TARGET_MOD)
    for name, value in module_attrs.items():
        setattr(module, name, value)
    previous = sys.modules.get(_TARGET_MOD)
    sys.modules[_TARGET_MOD] = module
    try:
        namespace: dict[str, Any] = {}
        exec(compile(code, "<p1-oracle>", "exec"), namespace)
    finally:
        if previous is None:
            sys.modules.pop(_TARGET_MOD, None)
        else:
            sys.modules[_TARGET_MOD] = previous
    return namespace


def _run_oracle(code: str, module_attrs: dict[str, Any]) -> None:
    _exec_oracle(code, module_attrs)["test_specir_v2_oracle"]()


# ═══ 1. 数据通道 ═══════════════════════════════════════════════════════════
class TestExamplesParsing:
    def test_parse_examples_passthrough(self) -> None:
        out = parse_examples([{"input": [2, 3], "expected": 5}, {"input": 1, "expected": 1}])
        assert out == [{"input": [2, 3], "expected": 5}, {"input": 1, "expected": 1}]

    def test_parse_examples_truncates_to_five(self) -> None:
        raw = [{"input": i, "expected": i} for i in range(9)]
        assert len(parse_examples(raw)) == 5

    def test_parse_examples_drops_invalid_shapes(self) -> None:
        raw = [
            {"bad": 1},
            {"input": 1},
            {"expected": 1},
            "not-a-dict",
            {"input": float("nan"), "expected": 1},
            {"input": 1, "expected": float("inf")},
            {"input": {1, 2}, "expected": 1},
            {"input": [1, 2], "expected": {"ok": 3}},
        ]
        assert parse_examples(raw) == [{"input": [1, 2], "expected": {"ok": 3}}]

    def test_parse_examples_non_list_returns_empty(self) -> None:
        assert parse_examples(None) == []
        assert parse_examples({"input": 1, "expected": 2}) == []

    def test_parse_examples_deduplicates(self) -> None:
        out = parse_examples([{"input": [1], "expected": 2}, {"input": [1], "expected": 2}])
        assert len(out) == 1

    def test_parse_logic_analysis_carries_examples(self) -> None:
        spec = parse_logic_analysis(
            {
                "function_name": "add",
                "postconditions_expr": ["result == a + b"],
                "examples": [{"input": [2, 3], "expected": 5}],
            }
        )
        assert spec is not None
        assert spec["examples"] == [{"input": [2, 3], "expected": 5}]

    def test_parse_logic_analysis_omits_empty_examples_key(self) -> None:
        spec = parse_logic_analysis({"function_name": "add", "postconditions_expr": ["result == a + b"]})
        assert spec is not None
        assert "examples" not in spec
        spec2 = parse_logic_analysis({"function_name": "add", "examples": [{"bad": 1}]})
        assert spec2 is not None
        assert "examples" not in spec2

    def test_examples_only_material_yields_spec(self) -> None:
        spec = parse_logic_analysis({"function_name": "f", "examples": [{"input": 1, "expected": 2}]})
        assert spec is not None
        assert spec["examples"] == [{"input": 1, "expected": 2}]

    def test_validate_spec_ir_examples_findings(self) -> None:
        base = {"schema_version": "1", "function_name": "f", "oracle_kind": "postcondition"}
        assert validate_spec_ir({**base, "examples": [{"input": 1, "expected": 1}]}) == []
        findings = validate_spec_ir({**base, "examples": [{"input": 1}, "bad"]})
        assert any("example_0_missing" in f for f in findings)
        too_many = validate_spec_ir({**base, "examples": [{"input": i, "expected": i} for i in range(6)]})
        assert any("examples_too_many" in f for f in too_many)


# ═══ 2. 编译器示例通道 ═════════════════════════════════════════════════════
class TestCompilerExamples:
    def test_single_param_example_assertion(self) -> None:
        code = _compile(_spec(examples=[{"input": 3, "expected": 6}]), ["x"])
        assert "assert _specir_norm_return(f(3)) == _specir_norm_return(6)" in code
        assert "examples=1" in code

    def test_single_param_container_input_repr(self) -> None:
        code = _compile(_spec(examples=[{"input": [1, 2], "expected": 3}]), ["xs"])
        assert "assert _specir_norm_return(f([1, 2])) == _specir_norm_return(3)" in code

    def test_single_param_args_list_unwrapped(self) -> None:
        """input 契约 = 位置实参列表：单参 input=[x] → f(x)（含 x 为容器）。"""
        code = _compile(_spec(examples=[{"input": [[1, 2]], "expected": 3}]), ["xs"])
        assert "assert _specir_norm_return(f([1, 2])) == _specir_norm_return(3)" in code
        code2 = _compile(_spec(examples=[{"input": [3], "expected": 9}]), ["x"])
        assert "assert _specir_norm_return(f(3)) == _specir_norm_return(9)" in code2

    def test_multi_param_examples_expand_positionally(self) -> None:
        code = _compile(
            _spec(examples=[{"input": [2, 3], "expected": 5}, {"input": [], "expected": 0}]),
            ["a", "b"],
        )
        assert "assert _specir_norm_return(f(2, 3)) == _specir_norm_return(5)" in code
        # 元数不匹配的示例丢弃（不抛）
        assert "assert f() == 0" not in code
        assert "examples=1" in code

    def test_zero_param_example(self) -> None:
        code = _compile(_spec(examples=[{"input": [], "expected": 42}]), [])
        assert "assert _specir_norm_return(f()) == _specir_norm_return(42)" in code

    def test_unknown_signature_accepts_scalar_only(self) -> None:
        code = _compile(_spec(examples=[{"input": 7, "expected": 8}, {"input": [1], "expected": 2}]), None)
        assert "assert _specir_norm_return(f(7)) == _specir_norm_return(8)" in code
        assert "assert f([1])" not in code

    def test_unsafe_expected_dropped(self) -> None:
        spec = _spec(examples=[{"input": 1, "expected": 2}])
        spec["examples"].append({"input": 2, "expected": object()})  # 绕过解析层直接构造
        code = _compile(spec, ["x"])
        assert "object" not in code
        assert "examples=1" in code

    def test_examples_channel_no_eval_exec(self) -> None:
        code = _compile(_spec(examples=[{"input": {"k": [1]}, "expected": 5}]), ["x"])
        assert "eval(" not in code and "exec(" not in code
        import ast

        ast.parse(code)

    def test_examples_inside_crash_safe_harness(self) -> None:
        code = _compile(_spec(examples=[{"input": 3, "expected": 6}]), ["x"])
        assert "try:" in code
        assert "except AssertionError:" in code
        assert 'pytest.skip(f"oracle-unavailable:' in code
        # skip 只出现在 except 分支（防全 skip 假安全）
        assert code.index("except Exception as exc:") < code.index("pytest.skip(")

    def test_example_assertion_failure_propagates(self) -> None:
        code = _compile(_spec(examples=[{"input": 2, "expected": 100}]), ["x"])
        with pytest.raises(AssertionError):
            _run_oracle(code, {"f": lambda x: x})

    def test_example_crash_becomes_skip(self) -> None:
        code = _compile(_spec(examples=[{"input": "not-int", "expected": 1}]), ["x"])
        with pytest.raises(pytest.skip.Exception, match="oracle-unavailable: TypeError"):
            _run_oracle(code, {"f": lambda x: x + 1})

    def test_examples_placed_before_degenerate_binding(self) -> None:
        """示例断言必须先于退化的字面量绑定/调用执行（语义信号不被仪器噪声抢占）。"""
        code = _compile(
            {"function_name": "f", "preconditions_expr": ["x > 0"], "examples": [{"input": 5, "expected": 5}]},
            ["x"],
        )
        assert code.index("assert f(5) == 5") < code.index("x = 0") if "x = 0" in code else True

    def test_no_examples_byte_identical_to_oid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无示例（缺 key / 空 list / 全部非法）产物与 O-1 逐字节一致。"""
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        specs = [
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"]),
            _spec(post_expr=["result == x + 1"]),
            {"function_name": "f"},
            _spec(pre_expr=["a + b > 0"], post_expr=["result == a + b"]),
        ]
        sigs: list[list[str] | None] = [["x"], ["x"], ["x"], ["a", "b"]]
        for base, sig in zip(specs, sigs, strict=True):
            golden = _compile(base, sig)
            assert _compile({**base, "examples": []}, sig) == golden
            assert _compile({**base, "examples": [{"bad": 1}, {"input": 1}]}, sig) == golden
            assert "examples=" not in golden

    def test_no_examples_bytes_stable_across_recompile(self) -> None:
        spec = _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], examples=[{"input": 3, "expected": 6}])
        assert _compile(spec, ["x"]) == _compile(spec, ["x"])
        no_examples = {k: v for k, v in spec.items() if k != "examples"}
        assert _compile(no_examples, ["x"]) == _compile(no_examples, ["x"])

    def test_examples_only_no_degenerate_call(self) -> None:
        code = _compile(_spec(examples=[{"input": 2, "expected": 4}]), ["x"])
        assert "assert _specir_norm_return(f(2)) == _specir_norm_return(4)" in code
        assert "x = 0" not in code and "r = f(x)" not in code
        assert "examples=1" in code


# ═══ 2b. 返回值表示归一（P-1.1） ═══════════════════════════════════════════
class TestReturnValueNormalization:
    def test_tuple_recursive_to_list(self) -> None:
        assert normalize_return_value((1, (2, 3))) == [1, [2, 3]]

    def test_nested_containers_recursed(self) -> None:
        assert normalize_return_value([(1, [2, (3,)])]) == [[1, [2, [3]]]]

    def test_generator_to_list(self) -> None:
        assert normalize_return_value(iter([1, 2, 3])) == [1, 2, 3]

    def test_iterator_is_one_shot(self) -> None:
        """归一按契约一次性消费 iterator；同一对象二次归一得到空 list（语义已消费）。"""
        generator = (x for x in (1, 2))
        assert normalize_return_value(generator) == [1, 2]
        assert normalize_return_value(generator) == []

    def test_str_bytes_bytearray_unchanged(self) -> None:
        assert normalize_return_value("abc") == "abc"
        assert normalize_return_value(b"abc") == b"abc"
        assert normalize_return_value(bytearray(b"ab")) == bytearray(b"ab")

    def test_dict_not_converted_but_values_normalized(self) -> None:
        out = normalize_return_value({"a": (1, 2), "b": [3]})
        assert out == {"a": [1, 2], "b": [3]}
        assert isinstance(out, dict)  # 不得把 dict 当 iterator 展开

    def test_scalars_and_set_unchanged(self) -> None:
        assert normalize_return_value(3) == 3
        assert normalize_return_value(2.5) == 2.5
        assert normalize_return_value(None) is None
        assert normalize_return_value(True) is True
        assert normalize_return_value({1, 2}) == {1, 2}  # set 不是 Iterator，原样

    def test_generated_code_contains_normalizer_when_examples(self) -> None:
        code = _compile(_spec(examples=[{"input": [2, 3], "expected": [2, 3]}]), ["a", "b"])
        assert "from collections.abc import Iterator" in code
        assert "def _specir_norm_return(value):" in code
        assert "_specir_norm_return(f(2, 3)) == _specir_norm_return([2, 3])" in code
        import ast

        ast.parse(code)

    def test_no_examples_has_no_normalizer(self) -> None:
        code = _compile(_spec(post_expr=["result == x"]), ["x"])
        assert "_specir_norm_return" not in code
        assert "from collections.abc import Iterator" not in code

    def test_normalized_comparison_detects_tuple_returning_buggy(self) -> None:
        """fixed 返回 tuple、期望为 list：归一后通过；buggy 返回换序 tuple → 检出。"""
        spec = {"function_name": "f", "examples": [{"input": [2, 3], "expected": [2, 3]}]}
        code = _compile(spec, ["a", "b"])
        with pytest.raises(AssertionError):
            _run_oracle(code, {"f": lambda a, b: (b, a)})  # buggy：换序
        _run_oracle(code, {"f": lambda a, b: (a, b)})  # fixed：tuple 表示，归一后通过

    def test_normalized_comparison_detects_generator_returning_buggy(self) -> None:
        spec = {"function_name": "f", "examples": [{"input": [2, 3], "expected": [2, 3]}]}
        code = _compile(spec, ["a", "b"])
        with pytest.raises(AssertionError):
            _run_oracle(code, {"f": lambda a, b: iter([b, a])})
        _run_oracle(code, {"f": lambda a, b: (x for x in (a, b))})


# ═══ 3. 生成器（mock LLM） ═════════════════════════════════════════════════
class TestGenerator:
    def test_build_prompt_spec_only(self) -> None:
        material = {
            "function_name": "add",
            "postconditions": ["返回值等于两数之和"],
            "edge_cases": ["a=0"],
        }
        prompt = gen.build_spec_examples_prompt(material, ["a", "b"])
        assert "add" in prompt and "参数名" in prompt and "a、b" in prompt
        # spec-only 证明：把"缺陷实现"作为 sentinel 塞进 material 之外不出现
        assert "return a + b + 999" not in prompt

    def test_prompt_excludes_unrelated_code_material(self) -> None:
        """生成器只接受规约字段；调用方即使误传代码键也不会进入 prompt。"""
        material = {"function_name": "f", "target_code": "def f():\n    return 1"}
        prompt = gen.build_spec_examples_prompt(material, None)
        assert "def f():" not in prompt
        assert "return 1" not in prompt

    def test_parse_response_fenced_json(self) -> None:
        text = '```json\n{"examples": [{"input": [2, 3], "expected": 5}]}\n```'
        examples, reason = gen.parse_examples_response(text)
        assert examples == [{"input": [2, 3], "expected": 5}]
        assert reason is None

    def test_parse_response_bare_list_and_text_wrapper(self) -> None:
        examples, _ = gen.parse_examples_response('[{"input": 1, "expected": 2}]')
        assert examples == [{"input": 1, "expected": 2}]
        examples2, _ = gen.parse_examples_response('结果如下：{"examples": [{"input": 3, "expected": 4}]} 完毕')
        assert examples2 == [{"input": 3, "expected": 4}]

    def test_parse_response_invalid_json_reason(self) -> None:
        assert gen.parse_examples_response("not json") == ([], "json_parse_error")
        assert gen.parse_examples_response("") == ([], "empty_response")

    def test_parse_response_schema_invalid_reason(self) -> None:
        examples, reason = gen.parse_examples_response('{"examples": [{"bad": 1}]}')
        assert examples == []
        assert reason == "schema_invalid_or_no_valid_example"

    def test_generate_success_with_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "512")
        monkeypatch.setattr(
            gen,
            "_call_examples_llm",
            lambda prompt, temperature=0.0: '{"examples": [{"input": [1, 2], "expected": 3}]}',
        )
        record = gen.generate_spec_examples({"function_name": "add"}, signature_params=["a", "b"], task_id="t1")
        assert record["status"] == "ok"
        assert record["examples"] == [{"input": [1, 2], "expected": 3}]
        assert record["reason"] is None
        assert record["prompt_sha256"] and record["response_sha256"]
        assert record["task_id"] == "t1"

    def test_generate_llm_error_soft_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(prompt: str, temperature: float = 0.0) -> str:
            raise RuntimeError("network down")

        monkeypatch.setattr(gen, "_call_examples_llm", boom)
        record = gen.generate_spec_examples({"function_name": "f"})
        assert record["status"] == "error"
        assert record["examples"] == []
        assert "llm_error:RuntimeError" in str(record["reason"])

    def test_generate_usage_delta_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        snapshots = iter(
            [
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
                {
                    "input_tokens": 120,
                    "output_tokens": 80,
                    "total_tokens": 200,
                    "llm_calls": 1,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                },
            ]
        )
        monkeypatch.setattr(gen, "_usage_snapshot", lambda: next(snapshots))
        monkeypatch.setattr(gen, "_call_examples_llm", lambda prompt, temperature=0.0: '{"examples": []}')
        record = gen.generate_spec_examples({"function_name": "f"})
        assert record["usage"]["input_tokens"] == 120
        assert record["usage"]["output_tokens"] == 80
        assert record["usage"]["llm_calls"] == 1

    def test_generate_cache_namespace_restored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "outer")
        seen: dict[str, str] = {}

        def fake(prompt: str, temperature: float = 0.0) -> str:
            seen["ns"] = os.environ.get("AITESTER_CACHE_NAMESPACE", "")
            return '{"examples": []}'

        monkeypatch.setattr(gen, "_call_examples_llm", fake)
        record = gen.generate_spec_examples({"function_name": "f"}, cache_namespace="inner")
        assert seen["ns"] == "inner"
        assert record["cache_namespace"] == "inner"
        assert os.environ.get("AITESTER_CACHE_NAMESPACE") == "outer"

    def test_estimate_cost_usd(self) -> None:
        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost = gen.estimate_cost_usd("deepseek-flash", usage)
        assert cost == pytest.approx(0.0003 + 0.0006, rel=1e-6)
        assert gen.estimate_cost_usd("unknown-model", usage) is None


# ═══ 4. 重放工具 ═══════════════════════════════════════════════════════════
def _row(task_id: str) -> dict[str, Any]:
    return {"task_id": task_id, "task_metadata": {"suggested_function": "f"}}


class TestReplayHelpers:
    def test_filter_rows_task_ids_and_limit(self) -> None:
        rows = [_row("q__b"), _row("q__a"), _row("q__a_test")]
        out = p1._filter_rows(rows, limit=0, include_driver=False, task_ids=["q__a", "q__b"])
        assert [r["task_id"] for r in out] == ["q__a", "q__b"]
        assert p1._filter_rows(rows, limit=1, include_driver=False, task_ids=[]) == [_row("q__a")]

    def test_filter_rows_include_driver(self) -> None:
        rows = [_row("q__a"), _row("q__a_test")]
        assert [r["task_id"] for r in p1._filter_rows(rows, limit=0, include_driver=True, task_ids=[])] == [
            "q__a",
            "q__a_test",
        ]

    def test_build_spec_with_examples(self) -> None:
        material = {"function_name": "add", "postconditions_expr": ["result == a + b"]}
        spec_a = p1._build_spec(material, None)
        assert spec_a is not None and "examples" not in spec_a
        spec_b = p1._build_spec(material, [{"input": [1, 2], "expected": 3}])
        assert spec_b is not None and spec_b["examples"] == [{"input": [1, 2], "expected": 3}]

    def test_category_priority(self) -> None:
        def rec(counts: dict[str, int], status: str = "ok") -> dict[str, Any]:
            return {"conditions": {p1.CONDITION_A: {"status": status, "counts": counts}}}

        assert p1._category_of(rec({"correct": 0, "fp": 1, "silent": 9}), p1.CONDITION_A) == "fp"
        assert p1._category_of(rec({"correct": 1, "fp": 5, "silent": 0}), p1.CONDITION_A) == "correct"
        assert p1._category_of(rec({"correct": 0, "fp": 0, "misguided": 2, "silent": 0}), p1.CONDITION_A) == "misguided"
        assert p1._category_of(rec({}, status="not_run"), p1.CONDITION_A) == "unavailable"

    def test_aggregate_arm_counts_and_transitions(self) -> None:
        def task(cat_a: dict[str, int], cat_b: dict[str, int]) -> dict[str, Any]:
            return {
                "task_id": "t",
                "injection": {p1.CONDITION_A: {"injected": True}, p1.CONDITION_B: {"injected": True}},
                "examples_generation": {"status": "ok", "examples": [{"input": 1, "expected": 2}]},
                "conditions": {
                    p1.CONDITION_A: {"status": "ok", "counts": {**cat_a, "unavailable": 0}, "n_oracle_tests": 1},
                    p1.CONDITION_B: {"status": "ok", "counts": {**cat_b, "unavailable": 0}, "n_oracle_tests": 1},
                },
            }

        tasks = [
            task(
                {"correct": 0, "fp": 0, "silent": 1, "misguided": 0},
                {"correct": 1, "fp": 0, "silent": 0, "misguided": 0},
            )
        ]
        aggregate = p1.aggregate_arm(tasks)
        assert aggregate["conditions"][p1.CONDITION_A]["counts"]["silent"] == 1
        assert aggregate["conditions"][p1.CONDITION_B]["counts"]["correct"] == 1
        assert aggregate["task_category_transitions"] == {"silent->correct": 1}
        assert aggregate["transition_tasks"][0]["task_id"] == "t"

    def test_aggregate_arm_unavailable_not_in_denominator(self) -> None:
        task = {
            "task_id": "t",
            "injection": {},
            "examples_generation": {"status": "ok", "examples": []},
            "conditions": {
                p1.CONDITION_A: {
                    "status": "ok",
                    "counts": {"correct": 0, "fp": 0, "silent": 0, "misguided": 0, "unavailable": 2},
                    "n_oracle_tests": 2,
                },
                p1.CONDITION_B: {
                    "status": "ok",
                    "counts": {"correct": 0, "fp": 0, "silent": 0, "misguided": 0, "unavailable": 2},
                    "n_oracle_tests": 2,
                },
            },
        }
        aggregate = p1.aggregate_arm([task])
        cond = aggregate["conditions"][p1.CONDITION_A]
        assert cond["n_classifiable"] == 0
        assert cond["n_unavailable"] == 2
        assert cond["rates_of_classifiable"]["correct"] is None

    def test_generation_summary_cost(self) -> None:
        generations = [
            {
                "status": "ok",
                "examples": [{"input": 1, "expected": 2}],
                "usage": {"input_tokens": 1000, "output_tokens": 500, "llm_calls": 1, "cache_hits": 0},
                "model": "deepseek-flash",
                "prompt_sha256": "x",
                "wall_s": 0.1,
                "task_id": "t1",
            }
        ]
        summary = p1.generation_summary(generations, gen.load_price_table())
        assert summary["status_counts"] == {"ok": 1}
        assert summary["llm_calls"] == 1
        assert summary["estimated_cost_usd"] == pytest.approx(0.0009, rel=1e-6)

    def test_recover_artifact_arms_unknown_arm_fail_closed(self, tmp_path: Path) -> None:
        payload = {"results": [], "metadata": {"arms": ["plain_llm_df"]}}
        path = tmp_path / "a.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(p1.mm.ArtifactError):
            p1._resolve_selection([path], ["nope"])


# ═══ 5. 自含检出 demo（buggy vs fixed fixture） ═════════════════════════════
_BUGGY = {"f": lambda a, b: a - b}  # off-by-sign 缺陷：a+b 应为 a-b
_FIXED = {"f": lambda a, b: a + b}
# 无示例臂：前件断言 + 边界绑定（两侧实现都满足前件、无后件断言 → silent）
_SPEC_NO_EXAMPLES = {
    "function_name": "f",
    "preconditions_expr": ["a >= 0", "b >= 0"],
    "boundaries": [{"input": [2, 3], "expected": 5}],
}
_SPEC_WITH_EXAMPLE = {
    **_SPEC_NO_EXAMPLES,
    "examples": [{"input": [2, 3], "expected": 5}],
}


class TestSelfContainedDetectionDemo:
    def test_no_example_oracle_does_not_detect_buggy(self) -> None:
        """无示例：只有前件断言（buggy/fixed 都满足）→ 不检出（silent）。"""
        code = _compile(_SPEC_NO_EXAMPLES, ["a", "b"])
        assert code
        assert "_specir_norm_return(f(2, 3))" not in code
        _run_oracle(code, _BUGGY)  # 不抛异常 = 未检出
        _run_oracle(code, _FIXED)

    def test_correct_example_oracle_detects_buggy(self) -> None:
        """加正确示例：oracle 在 buggy 上断言失败（检出），在 fixed 上通过。"""
        code = _compile(_SPEC_WITH_EXAMPLE, ["a", "b"])
        assert code
        assert "assert _specir_norm_return(f(2, 3)) == _specir_norm_return(5)" in code
        with pytest.raises(AssertionError):
            _run_oracle(code, _BUGGY)  # 缺陷被机器化示例断言检出
        _run_oracle(code, _FIXED)  # 正确实现不误报

    def test_wrong_example_would_false_positive_fixed(self) -> None:
        """反证：示例期望值错误会在 fixed 上误报（示例质量决定语义质量）。"""
        spec = {**_SPEC_NO_EXAMPLES, "examples": [{"input": [2, 3], "expected": 6}]}
        code = _compile(spec, ["a", "b"])
        with pytest.raises(AssertionError):
            _run_oracle(code, _FIXED)


# ═══ 6. P-1.1 复用既有示例（零 LLM） ═══════════════════════════════════════
class TestReuseExamples:
    @staticmethod
    def _report(tmp_path: Path) -> Path:
        payload = {
            "schema_version": "oracle_examples_metric/1",
            "report": {
                "arms": [
                    {
                        "tasks": [
                            {
                                "task_id": "t1",
                                "examples_generation": {
                                    "status": "ok",
                                    "examples": [{"input": [2, 3], "expected": 5}],
                                    "prompt_sha256": "abc",
                                },
                            },
                            {
                                "task_id": "t2",
                                "examples_generation": {"status": "ok", "examples": [], "prompt_sha256": "def"},
                            },
                        ]
                    },
                    {
                        "tasks": [
                            {
                                "task_id": "t1",
                                "examples_generation": {
                                    "status": "ok",
                                    "examples": [{"input": [9], "expected": 9}],
                                    "prompt_sha256": "dup",
                                },
                            }
                        ]
                    },
                ]
            },
            "run_meta": {"body_digest": "digest-1"},
        }
        path = tmp_path / "report.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_load_reused_examples(self, tmp_path: Path) -> None:
        path = self._report(tmp_path)
        records, provenance = p1._load_reused_examples(path)
        assert records["t1"]["status"] == "reused"
        assert records["t1"]["examples"] == [{"input": [2, 3], "expected": 5}]  # 首臂优先
        assert records["t2"]["examples"] == []
        assert provenance["body_digest"] == "digest-1"
        assert provenance["n_reused_tasks"] == 2
        assert provenance["sha256"]

    def test_condition_examples_accepts_reused_status(self) -> None:
        """P-1.1：reuse 记录 status=reused 时示例必须仍进入 B 臂（A 恒空）。"""
        generation = {"status": "reused", "examples": [{"input": [1], "expected": 2}]}
        assert p1._condition_examples(generation, p1.CONDITION_A) == []
        assert p1._condition_examples(generation, p1.CONDITION_B) == [{"input": [1], "expected": 2}]

    def test_load_reused_missing_fail_closed(self, tmp_path: Path) -> None:
        with pytest.raises(p1.ReuseExamplesError, match="不存在"):
            p1._load_reused_examples(tmp_path / "missing.json")

    def test_load_reused_invalid_structure(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"report": {}}), encoding="utf-8")
        with pytest.raises(p1.ReuseExamplesError, match="结构不合法"):
            p1._load_reused_examples(path)

    def test_main_reuse_missing_fail_closed(self, tmp_path: Path) -> None:
        # W 轮测试卫生：p1.main 是 CLI 生命周期入口，会对进程环境
        # `os.environ.setdefault("LLM_MAX_OUTPUT_TOKENS", ...)`（批内沿用口径，
        # CLI 退出即回收，不在 main 内恢复）。测试内调用属于"把 CLI 当库用"，
        # 必须自行快照恢复，避免向同进程后续测试泄漏（该泄漏曾使
        # test_closeout_k_base_agent 的默认包络旧缓存回退用例按文件配对顺序
        # 随机转红）。
        previous = os.environ.get("LLM_MAX_OUTPUT_TOKENS")
        try:
            assert p1.main(["--reuse-examples", str(tmp_path / "missing.json"), "--out", str(tmp_path / "out")]) == 2
        finally:
            if previous is None:
                os.environ.pop("LLM_MAX_OUTPUT_TOKENS", None)
            else:
                os.environ["LLM_MAX_OUTPUT_TOKENS"] = previous
