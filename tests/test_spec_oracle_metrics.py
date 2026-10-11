"""P0-3 / P0-4（REVIEW_2026_FRONTIER I-07，2026-10-10）：逻辑通道对齐 + 行级注入指标。

锁定三件事：

1. **判定一致性**（P0-3）：``compile_readiness``（度量通道）与
   ``compile_spec_oracle``（注入通道）共用 ``spec_ir_v2._clause_is_compilable``
   单一判据——同一组子句两通道判定必须一致（rate == 1.0 ⇔ 产物非空）。
   修复前 expr 通道缺"标识符绑定门"，``spec_compile_rate`` 是**上界**
   （离线可达性实证：子句过白名单 73.3% vs 端到端 compiler 非空 18.7%）。
2. **精准别名**（P0-3 配套）：prompt 契约（SPEC_EXPR_CONTRACT_SECTION，
   templates.py:48/50）文档化的结果变量名 ``result`` 由注入通道**同义归一**
   为绑定名 ``r``（逐字节同产物），且**不放宽**安全口径——危险调用 /
   属性逃逸 / 真正的未知标识符仍被拒。
3. **行级指标**（P0-4）：``spec_oracle_injected`` / ``spec_oracle_verdict``
   取值正确性（开关关 → None/"not_attempted"；产物空 → "compiled_empty"；
   注入 → "injected"；执行后升级 "injected_and_passed" /
   "injected_and_failed"）+ 默认关回归（SPEC_IR_DSL_ENABLE /
   SPEC_ORACLE_EXEC_ENABLE 默认 false，历史口径零变化）。

已知假阴性（P2-L3 表达力缺口，本轮**不修**，见 TestKnownFalseNegative）：
推导式绑定变量（``all(x > 0 for x in xs)`` 的 ``x``）被 ast.Name 全收集口径
当作未知标识符 → 两通道一致拒绝（假阴性）；修复需自由变量分析（表达力批次），
此处以 strict xfail 钉住，防止未来被误当成回归。
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.graph.nodes import (
    _SPEC_ORACLE_VERDICT_COMPILED_EMPTY,
    _SPEC_ORACLE_VERDICT_INJECTED,
    _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED,
    _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED,
    _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED,
    _append_spec_oracle_to_test,
    _append_spec_oracle_to_test_with_verdict,
    _spec_oracle_injection_verdict,
    _spec_oracle_verdict_after_run,
)
from src.graph.state import AITesterState, create_initial_state
from src.specs.spec_ir_v2 import (
    _clause_is_compilable,
    _compile_single_clause,
    _default_known_names,
    _known_names_for_signature,
    compile_readiness,
    compile_spec_oracle,
    spec_ir_dsl_enabled,
)

# 任务说明指定的 8 条一致性用例：(子句, 与注入侧相同的绑定上下文签名)。
CONSISTENCY_CASES: list[tuple[str, list[str]]] = [
    ("all(x > 0 for x in xs)", ["xs"]),
    ("any(c.isdigit() for c in s)", ["s"]),
    ("xs != None implies len(xs) > 0", ["xs"]),
    ("n is an integer", ["n"]),
    ("r == a + b", ["a", "b"]),
    ("len(r) > 0", ["x"]),
    ("r == sorted(xs)", ["xs"]),
    ("xs[i] > 0", ["xs", "i"]),
]
# 期望判定（与上表同序）：前 2 条 = 推导式假阴性（P2-L3）；第 3/4 条 =
# 非 Python 表达式形态（implies 未知名 / "n is an integer" 语法非法）；
# 后 4 条 = 受限 DSL 内可编译。
EXPECTED_COMPILABLE: list[bool] = [False, False, False, False, True, True, True, True]

# 可编译规约材料（与 tests/test_2026_10_05_review_batch.py 同形状）
_SPEC_COMPILABLE: dict = {
    "schema_version": "1",
    "source": "test",
    "function_name": "double",
    "preconditions": [],
    "postconditions": ["r == x * 2"],
    "invariants": [],
    "boundaries": [{"input": 4, "expected": 8, "rationale": ""}],
    "oracle_kind": "postcondition",
}
# 有规约材料但全不可编译（纯 NL 子句）→ 编译产物为空
_SPEC_UNCOMPILABLE: dict = {
    "schema_version": "1",
    "source": "test",
    "function_name": "double",
    "preconditions": [],
    "postconditions": ["结果必须为正"],
    "invariants": [],
    "boundaries": [{"input": 4, "expected": 8, "rationale": ""}],
    "oracle_kind": "postcondition",
}

_LLM_TEST = "def test_llm():\n    assert True\n"


def _injection_state(spec_ir: dict | None) -> dict:
    """构造 _generator_node / 注入纯函数所需的 state（含签名材料）。"""
    state = create_initial_state(
        "u-p0-metrics",
        "target_mod.py",
        "def double(x):\n    return x * 2\n",
        3,
        module_name="target_mod",
        target_function="double",
    )
    state["spec_ir"] = spec_ir
    return dict(state)


# ─── 1. 判定一致性（P0-3 核心）─────────────────────────────────────────────


@pytest.mark.unit
class TestChannelConsistency:
    """度量通道与注入通道对同一子句的判定必须一致（上界→实际值）。"""

    @pytest.mark.parametrize(("clause", "signature"), CONSISTENCY_CASES)
    def test_readiness_matches_oracle_injection(self, clause: str, signature: list[str]) -> None:
        """单子句 spec：rate == 1.0 ⇔ compile_spec_oracle 产出非空（双向）。"""
        spec = {"postconditions_expr": [clause]}
        rate = compile_readiness(spec, signature)
        code = compile_spec_oracle(spec, "mod_x", "fn_x", signature_params=signature)
        assert rate in (0.0, 1.0)
        assert (rate == 1.0) is (code != ""), f"两通道判定不一致：{clause!r} rate={rate} code={bool(code)}"

    def test_expected_verdicts_are_locked(self) -> None:
        """逐条钉住期望判定（含已知假阴性与非表达式形态）。"""
        actual = [compile_readiness({"postconditions_expr": [c]}, s) == 1.0 for c, s in CONSISTENCY_CASES]
        assert actual == EXPECTED_COMPILABLE

    def test_multi_clause_rate_equals_compiled_clause_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多子句 spec：rate 的分母/分子与产物里的断言条数同口径。"""
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")  # 见证段会追加断言行，隔离
        spec = {"postconditions_expr": [c for c, _ in CONSISTENCY_CASES]}
        signature = ["xs", "s", "n", "a", "b", "i"]
        code = compile_spec_oracle(spec, "mod_x", "fn_x", signature_params=signature)
        assert code != ""
        compiled = sum(1 for line in code.splitlines() if line.strip().startswith("assert"))
        assert compile_readiness(spec, signature) == pytest.approx(compiled / len(CONSISTENCY_CASES))

    def test_unknown_identifier_upper_bound_regression(self) -> None:
        """核心回归：未知标识符子句修复前被计为可编译（上界），现两通道同拒。"""
        spec = {"postconditions_expr": ["r == total"]}
        assert compile_readiness(spec, ["x"]) == 0.0
        assert compile_spec_oracle(spec, "m", "f", signature_params=["x"]) == ""

    def test_unknown_identifier_in_mixed_spec(self) -> None:
        spec = {"preconditions_expr": ["b != 0", "r == total"]}
        assert compile_readiness(spec, ["b", "r"]) == 0.5

    def test_channel_selection_matches_oracle(self) -> None:
        """expr 通道存在即选中（即便全为空串），不回落 NL——与注入侧同口径。"""
        spec = {"preconditions_expr": [""], "preconditions": ["x > 0"]}
        assert compile_readiness(spec) == 0.0
        assert compile_spec_oracle(spec, "m", "f", signature_params=["x"]) == ""

    def test_signature_binding_context_matches_injection(self) -> None:
        """签名感知：度量侧传入与注入侧相同的 signature_params（否则度量成下界）。"""
        spec = {"postconditions_expr": ["r == first + second"]}
        assert compile_readiness(spec) == 0.0  # 默认绑定集合下不可编译
        assert compile_readiness(spec, ["first", "second"]) == 1.0
        assert compile_spec_oracle(spec, "m", "add", signature_params=["first", "second"]) != ""


@pytest.mark.unit
class TestResultAliasPrecision:
    """P0-3 配套：契约结果变量名 result → 绑定名 r 的精准同义归一。

    依据：SPEC_EXPR_CONTRACT_SECTION（src/prompts/templates.py:48/50，产出
    *_expr 通道的文档化契约）以 `result` 表示返回值（"result[0]"、
    "result == sorted(result)"），ORACLE_ENHANCE 契约（:93）同；而注入通道
    绑定名为 r。归一是同义替换，不是放宽未知标识符门。
    """

    @pytest.mark.parametrize("kind", ["postcondition", "invariant"])
    def test_result_and_r_produce_identical_product(self, kind: str) -> None:
        known = _default_known_names()
        from_result = _compile_single_clause("result == sorted(result)", kind, "m", "f", known)
        from_r = _compile_single_clause("r == sorted(r)", kind, "m", "f", known)
        assert from_result == from_r == "assert r == sorted(r)"

    def test_alias_preserves_rest_of_clause_bytes(self) -> None:
        """只替换整名 result：其余字形 / 数字格式逐字节保留（不做 ast.unparse 重排）。"""
        known = _default_known_names()
        assert (
            _compile_single_clause("abs(result * b - a) < 1e-9", "postcondition", "m", "f", known)
            == "assert abs(r * b - a) < 1e-9"
        )
        assert _compile_single_clause("result[0] > 0", "postcondition", "m", "f", known) == "assert r[0] > 0"

    def test_alias_applies_inside_oracle_product(self) -> None:
        code = compile_spec_oracle(
            {"postconditions_expr": ["result == sorted(result)"]}, "m", "f", signature_params=["r"]
        )
        assert "assert r == sorted(r)" in code
        assert "assert result == sorted(result)" not in code

    def test_alias_not_applied_to_preconditions(self) -> None:
        """前置条件无结果变量：result 在 pre 里仍是未知标识符 → 不编译。"""
        assert _compile_single_clause("result > 0", "precondition", "m", "f", _default_known_names()) == ""

    def test_alias_not_applied_when_result_is_signature_param(self) -> None:
        """函数真有名为 result 的参数时，result 是入参而非返回值 → 不归一。"""
        known = _known_names_for_signature(["result"])
        assert _compile_single_clause("result > 0", "postcondition", "m", "f", known) == "assert result > 0"

    def test_alias_does_not_widen_unknown_names(self) -> None:
        known = _default_known_names()
        assert _clause_is_compilable("results > 0", "postcondition", known) is False
        assert _clause_is_compilable("result_x > 0", "postcondition", known) is False
        assert _clause_is_compilable("r == total", "postcondition", known) is False

    @pytest.mark.parametrize(
        "bad",
        [
            'open("/etc/passwd") is None',  # 白名单外调用（双引号过形态门，走白名单门）
            'eval("1") == 1',
            'exec("x") is None',
            '__import__("os") is None',
            "result.__class__ == int",  # 属性逃逸
            "result.real_part > 0",
            "r.__class__.__mro__[0] == int",
        ],
    )
    def test_dangerous_forms_still_rejected(self, bad: str) -> None:
        """安全口径不放宽：白名单 / 属性逃逸门照旧（含 result 别名形态）。"""
        known = _default_known_names()
        assert _clause_is_compilable(bad, "postcondition", known) is False
        assert _compile_single_clause(bad, "postcondition", "m", "f", known) == ""


# ─── 2. 行级指标：spec_oracle_injected / spec_oracle_verdict（P0-4）─────────


@pytest.mark.unit
class TestInjectionVerdicts:
    """_spec_oracle_injection_verdict：开关守门 + 注入 + 三值判定。"""

    def test_switch_off_not_attempted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """默认关：原文返回、injected=None、verdict="not_attempted"（历史口径零变化）。"""
        monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
        merged, injected, verdict = _spec_oracle_injection_verdict(_LLM_TEST, _injection_state(_SPEC_COMPILABLE))  # type: ignore[arg-type]
        assert merged == _LLM_TEST
        assert injected is None
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED

    def test_switch_on_no_material_not_attempted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开但无规约材料：未尝试编译 → None / "not_attempted"。"""
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        merged, injected, verdict = _spec_oracle_injection_verdict(_LLM_TEST, _injection_state(None))  # type: ignore[arg-type]
        assert merged == _LLM_TEST
        assert injected is None
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED

    def test_switch_on_compiled_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """尝试编译但产物为空：False / "compiled_empty"（≠ 未尝试）。"""
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        merged, injected, verdict = _spec_oracle_injection_verdict(_LLM_TEST, _injection_state(_SPEC_UNCOMPILABLE))  # type: ignore[arg-type]
        assert merged == _LLM_TEST
        assert injected is False
        assert verdict == _SPEC_ORACLE_VERDICT_COMPILED_EMPTY

    def test_switch_on_injected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """注入成功：产物追加、True / "injected"。"""
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        merged, injected, verdict = _spec_oracle_injection_verdict(_LLM_TEST, _injection_state(_SPEC_COMPILABLE))  # type: ignore[arg-type]
        assert injected is True
        assert verdict == _SPEC_ORACLE_VERDICT_INJECTED
        assert "test_specir_v2_oracle" in merged
        assert merged.startswith(_LLM_TEST)

    def test_legacy_two_tuple_wrapper_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """兼容包装：既有二元返回契约不破坏（R1c 调用方 / 既有测试）。"""
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        state = _injection_state(_SPEC_COMPILABLE)
        merged2, injected2 = _append_spec_oracle_to_test(_LLM_TEST, state)  # type: ignore[arg-type]
        merged3, injected3, verdict3 = _append_spec_oracle_to_test_with_verdict(_LLM_TEST, state)  # type: ignore[arg-type]
        assert (merged2, injected2) == (merged3, injected3)
        assert verdict3 == _SPEC_ORACLE_VERDICT_INJECTED


@pytest.mark.unit
class TestGeneratorWritesMetricKeys:
    """_generator_node 把两个行级指标写进 update（结果行可读的前提）。"""

    def _run(self, state: dict) -> dict:
        mock_agent = MagicMock()
        mock_agent.generate.return_value = _LLM_TEST
        with (
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
            patch("src.graph.nodes.ENABLE_RAG", False),
        ):
            from src.graph.nodes import _generator_node

            return _generator_node(state)  # type: ignore[arg-type]

    def test_default_off_writes_none_and_not_attempted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
        update = self._run(_injection_state(_SPEC_COMPILABLE))
        assert update["spec_oracle_injected"] is None
        assert update["spec_oracle_verdict"] == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED
        assert "test_specir_v2_oracle" not in update["generated_test"]

    def test_on_injected_writes_true_and_injected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        update = self._run(_injection_state(_SPEC_COMPILABLE))
        assert update["spec_oracle_injected"] is True
        assert update["spec_oracle_verdict"] == _SPEC_ORACLE_VERDICT_INJECTED
        assert "test_specir_v2_oracle" in update["generated_test"]

    def test_on_compiled_empty_writes_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        update = self._run(_injection_state(_SPEC_UNCOMPILABLE))
        assert update["spec_oracle_injected"] is False
        assert update["spec_oracle_verdict"] == _SPEC_ORACLE_VERDICT_COMPILED_EMPTY
        assert "test_specir_v2_oracle" not in update["generated_test"]


@pytest.mark.unit
class TestVerdictAfterRun:
    """_spec_oracle_verdict_after_run：执行后升级（保守，宁缺毋滥）。"""

    def _state(self, injected: object, verdict: object) -> dict:
        return {"spec_oracle_injected": injected, "spec_oracle_verdict": verdict}

    def _result(self, passed: bool, failed: list[dict] | None = None, output: str = "") -> dict:
        return {"passed": passed, "failed_cases": failed or [], "output": output}

    def test_all_green_upgrades_to_passed(self) -> None:
        got = _spec_oracle_verdict_after_run(self._state(True, "injected"), self._result(True))  # type: ignore[arg-type]
        assert got == _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED

    def test_oracle_case_failure_upgrades_to_failed(self) -> None:
        failed = [{"name": "test_generated.py::test_specir_v2_oracle", "error": "AssertionError"}]
        got = _spec_oracle_verdict_after_run(self._state(True, "injected"), self._result(False, failed))  # type: ignore[arg-type]
        assert got == _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED

    def test_smt_witness_failure_upgrades_to_failed(self) -> None:
        failed = [{"name": "test_generated.py::test_specir_v2_smt_witness_1", "error": "AssertionError"}]
        got = _spec_oracle_verdict_after_run(self._state(True, "injected"), self._result(False, failed))  # type: ignore[arg-type]
        assert got == _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED

    def test_other_test_failure_without_oracle_pass_line_stays_undecided(self) -> None:
        """失败清单不含 oracle 且输出无 oracle PASSED 行 → 不臆测（保留 injected）。"""
        failed = [{"name": "test_generated.py::test_llm", "error": "AssertionError"}]
        got = _spec_oracle_verdict_after_run(self._state(True, "injected"), self._result(False, failed))  # type: ignore[arg-type]
        assert got is None

    def test_other_test_failure_with_oracle_pass_line_upgrades_to_passed(self) -> None:
        """pytest -v 显式 PASSED 行 → oracle 用例通过（LLM 断言失败不影响其判定）。"""
        failed = [{"name": "test_generated.py::test_llm", "error": "AssertionError"}]
        output = "test_generated.py::test_specir_v2_oracle PASSED [ 50%]\ntest_generated.py::test_llm FAILED [100%]"
        got = _spec_oracle_verdict_after_run(self._state(True, "injected"), self._result(False, failed, output))  # type: ignore[arg-type]
        assert got == _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED

    @pytest.mark.parametrize(
        ("injected", "verdict"),
        [(None, "not_attempted"), (False, "compiled_empty"), (None, None), (True, "injected_and_passed")],
    )
    def test_no_upgrade_when_not_injected_this_round(self, injected: object, verdict: object) -> None:
        assert _spec_oracle_verdict_after_run(self._state(injected, verdict), self._result(True)) is None  # type: ignore[arg-type]


# ─── 3. state 键存在性（结果行可读的前提）───────────────────────────────────


@pytest.mark.unit
class TestStateKeys:
    def test_typed_dict_declares_both_keys(self) -> None:
        assert "spec_oracle_injected" in AITesterState.__annotations__
        assert "spec_oracle_verdict" in AITesterState.__annotations__

    def test_initial_state_defaults_none(self) -> None:
        state = create_initial_state("u", "m.py", "x = 1\n", 3)
        assert state["spec_oracle_injected"] is None
        assert state["spec_oracle_verdict"] is None


@pytest.mark.unit
class TestExecutorNodeWritesVerdict:
    """_executor_node 真把升级后的 verdict 写进 update（行级可读的最后一环）。"""

    def _run(self, verdict_state: dict, fake_result: dict) -> dict:
        from src.graph import nodes as nodes_mod

        state = {
            "target_code": "def double(x):\n    return x * 2\n",
            "target_file": "/tmp/target_mod.py",
            "module_name": "target_mod",
            "generated_test": _LLM_TEST,
            "iteration": 0,
            **verdict_state,
        }
        with (
            patch.object(nodes_mod, "ExecutorAgent") as executor_cls,
            patch("src.graph.nodes.ENABLE_RAG", False),
        ):
            executor_cls.return_value.execute.return_value = fake_result
            return nodes_mod._executor_node(state)  # type: ignore[arg-type]

    def test_injected_all_green_writes_passed(self) -> None:
        update = self._run(
            {"spec_oracle_injected": True, "spec_oracle_verdict": _SPEC_ORACLE_VERDICT_INJECTED},
            {"passed": True, "output": "1 passed", "coverage": 100.0, "failed_cases": []},
        )
        assert update["spec_oracle_verdict"] == _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED

    def test_injected_oracle_failure_writes_failed(self) -> None:
        update = self._run(
            {"spec_oracle_injected": True, "spec_oracle_verdict": _SPEC_ORACLE_VERDICT_INJECTED},
            {
                "passed": False,
                "output": "1 failed",
                "coverage": 50.0,
                "failed_cases": [{"name": "test_generated.py::test_specir_v2_oracle", "error": "AssertionError"}],
            },
        )
        assert update["spec_oracle_verdict"] == _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED

    def test_not_injected_leaves_key_untouched(self) -> None:
        update = self._run(
            {"spec_oracle_injected": False, "spec_oracle_verdict": _SPEC_ORACLE_VERDICT_COMPILED_EMPTY},
            {"passed": False, "output": "1 failed", "coverage": 50.0, "failed_cases": [{"name": "test_a"}]},
        )
        assert "spec_oracle_verdict" not in update


# ─── 4. 默认关回归（ADR-0003：默认路径行为与历史一致）──────────────────────


@pytest.mark.unit
class TestDefaultOffRegression:
    def test_switches_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.graph.nodes import _spec_oracle_exec_enabled

        monkeypatch.delenv("SPEC_IR_DSL_ENABLE", raising=False)
        monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
        assert spec_ir_dsl_enabled() is False
        assert _spec_oracle_exec_enabled() is False

    def test_historical_nl_channel_values_unchanged(self) -> None:
        """NL 通道历史口径逐值锁定（默认绑定集合 / 分母口径不变）。"""
        assert compile_readiness(None) == 0.0
        assert compile_readiness({}) == 0.0
        assert compile_readiness({"preconditions": []}) == 0.0
        assert compile_readiness({"preconditions": ["x 为正"], "postconditions": ["结果非空"]}) == 0.0
        assert (
            compile_readiness(
                {
                    "preconditions": ["x >= 0", "x 不能为负"],
                    "postconditions": ["r > 0", "结果必须为正"],
                    "invariants": ["r <= abs(x)"],
                }
            )
            == 3 / 5
        )
        assert compile_readiness({"preconditions": ["x > 0", "x 为正"]}) == 0.5
        assert compile_readiness({"preconditions": ["os.system('x') == 0"]}) == 0.0

    def test_oracle_none_signature_binding_unchanged(self) -> None:
        """signature_params=None 的历史绑定集合与产物结构不变。"""
        spec = {
            "preconditions": ["a == b"],
            "postconditions": ["r > 0"],
            "invariants": [],
            "boundaries": [{"input": 5, "expected": 6, "rationale": ""}],
        }
        code = compile_spec_oracle(spec, "m", "f", signature_params=None)
        assert "x = 5" in code  # 历史口径：边界输入绑定到 x
        assert "r = f(x)" in code
        assert "assert r > 0" in code


# ─── 5. 已知假阴性（P2-L3，本轮不修，strict xfail 钉住）────────────────────


@pytest.mark.unit
class TestKnownFalseNegative:
    """推导式绑定变量被标识符门误杀——两通道一致拒绝（假阴性，非口径漂移）。"""

    def test_current_behavior_is_consistent_rejection(self) -> None:
        spec = {"postconditions_expr": ["all(x > 0 for x in xs)"]}
        assert compile_readiness(spec, ["xs"]) == 0.0
        assert compile_spec_oracle(spec, "m", "f", signature_params=["xs"]) == ""

    @pytest.mark.xfail(
        strict=True,
        reason="P2-L3 表达力缺口：ast.Name 全收集口径把推导式绑定变量 x 当未知标识符；"
        "修复需自由变量分析（表达力批次，本轮范围外）",
    )
    def test_comprehension_bound_variable_should_compile(self) -> None:
        assert compile_readiness({"postconditions_expr": ["all(x > 0 for x in xs)"]}, ["xs"]) == 1.0


# ─── 6. 端到端（真实 pytest 子进程）：注入产物执行 → 行级 verdict 可归因 ────


@pytest.mark.integration
class TestEndToEndOracleExecution:
    """compile → 注入 → 真实 pytest 执行 → 行级判定（P0-4 全链路）。

    证据链：`result`/`r` 两种写法产出同一断言且真跑通过；注入 oracle 失败时
    失败清单含 `test_specir_v2_oracle` → verdict="injected_and_failed"
    （"注入 oracle 造成的红"首次可与 LLM 断言造成的红分离）。
    """

    def _execute(self, tmp_path, post: str) -> dict:
        from src.agents.executor_output import parse_failed_cases

        spec = {
            "preconditions_expr": [],
            "postconditions_expr": [post],
            "invariants_expr": [],
            "boundaries": [{"input": 4, "expected": 8, "rationale": "t"}],
        }
        oracle = compile_spec_oracle(spec, "target_mod", "double", signature_params=["x"])
        assert oracle, f"oracle 不应为空：{post!r}"
        (tmp_path / "target_mod.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
        (tmp_path / "test_generated.py").write_text(f"{_LLM_TEST}\n\n{oracle}", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_generated.py", "-v", "--tb=short", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        return {"passed": proc.returncode == 0, "output": output, "failed_cases": parse_failed_cases(output)}

    @pytest.mark.parametrize("post", ["result == x * 2", "r == x * 2"])
    def test_alias_and_binding_name_both_pass_end_to_end(self, tmp_path, post: str) -> None:
        result = self._execute(tmp_path, post)
        assert result["passed"] is True
        state = {"spec_oracle_injected": True, "spec_oracle_verdict": _SPEC_ORACLE_VERDICT_INJECTED}
        assert _spec_oracle_verdict_after_run(state, result) == _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED  # type: ignore[arg-type]

    def test_failing_oracle_is_attributable_to_verdict(self, tmp_path) -> None:
        result = self._execute(tmp_path, "result == x * 3")  # 注入断言必然失败
        assert result["passed"] is False
        assert any("test_specir_v2_oracle" in case["name"] for case in result["failed_cases"])
        state = {"spec_oracle_injected": True, "spec_oracle_verdict": _SPEC_ORACLE_VERDICT_INJECTED}
        assert _spec_oracle_verdict_after_run(state, result) == _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED  # type: ignore[arg-type]
