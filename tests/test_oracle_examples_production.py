"""Q-1 示例通道生产接线测试（Planner 契约 + 开关 + 无 Planner 生成器 + 审计字段）。

覆盖（≥25 例，零真实 LLM / 零网络，生成器全程 mock）：
1. 双门开关：``SPEC_ORACLE_EXAMPLES_ENABLE ∧ SPEC_ORACLE_EXEC_ENABLE`` 才生效；
   默认关 → False。
2. Planner prompt 契约：关闭时 prompt 逐字节不变（同一 query + 无契约段）；
   开启时追加 examples 契约段（≤3 条 / JSON 形状 / 期望值由规格推导 / 小输入）；
   删契约负控（常量清空 → prompt 与关闭时一致）。
3. Planner 输出净化：≤3 条、非法丢弃、关闭时删除 examples 键。
4. 链路生效：planner examples → parse_logic_analysis → nodes 注入编译为逐示例
   断言（N-3 材料解析器真实路径）；关闭时即使材料带 examples 也剥离 → 产物与
   无示例口径逐字节一致。
5. 无 Planner 臂生成器：双门开时每任务 +1 次调用（max_examples=3、spec-only
   材料）、成功并入锚材料；失败/空/异常透传（不修改锚材料、不抛）。
6. 行字段：``spec_oracle_examples_source/count`` 成功/失败两分支键位一致；
   planner / spec_generator / none 三值来源判定。
7. env 门禁登记：两个新键在 env_budget.yaml 与 run_benchmark env_snapshot 清单，
   `check_env_budget --check` / `check_env_snapshot_keys` 门禁均通过。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import experiments.run_benchmark as rb
import src.agents.planner as planner_mod
import src.graph.nodes as nodes
from src.agents.planner import PlannerAgent, spec_oracle_examples_enabled
from src.datasets.dataset_loader import BenchmarkTask
from src.specs import compile_spec_oracle, parse_logic_analysis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CODE = "def add(a, b):\n    return a + b\n"
_BASE_RESPONSE: dict[str, Any] = {
    "function_name": "add",
    "description": "两整数相加",
    "logic_analysis": {
        "input_domain": "整数 a, b",
        "output_domain": "整数和",
        "preconditions": ["a, b 为整数"],
        "postconditions": ["result == a + b"],
        "edge_cases": ["a=0", "b=0"],
        "preconditions_expr": ["isinstance(a, int) and isinstance(b, int)"],
        "postconditions_expr": ["result == a + b"],
    },
    "test_cases": [{"name": "t1", "input": {"a": 1, "b": 2}, "expected": 3}],
}


def _make_planner() -> PlannerAgent:
    return PlannerAgent()


def _plan(plan_agent: PlannerAgent, response: dict[str, Any], query_sink: list[str] | None = None) -> dict[str, Any]:
    """mock LLM：记录 query 并返回给定 JSON 响应（零真实调用）。"""

    def _fake(query: str, **_kwargs: Any) -> str:
        if query_sink is not None:
            query_sink.append(query)
        return json.dumps(response)

    with patch.object(plan_agent, "_call_llm_with_cache", side_effect=_fake):
        return plan_agent.plan(_CODE, target_function="add")


def _enable(monkeypatch: pytest.MonkeyPatch, *, exec_on: bool = True, examples_on: bool = True) -> None:
    monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true" if exec_on else "false")
    monkeypatch.setenv("SPEC_ORACLE_EXAMPLES_ENABLE", "true" if examples_on else "false")


def _disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
    monkeypatch.delenv("SPEC_ORACLE_EXAMPLES_ENABLE", raising=False)


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="repo__repo-1",
        repo_name="repo/repo",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "test"},
    )


# ═══ 1. 双门开关 ═══════════════════════════════════════════════════════════
class TestGate:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _disable(monkeypatch)
        assert spec_oracle_examples_enabled() is False

    def test_both_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        assert spec_oracle_examples_enabled() is True

    def test_exec_off_examples_on_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch, exec_on=False, examples_on=True)
        assert spec_oracle_examples_enabled() is False

    def test_examples_off_exec_on_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch, exec_on=True, examples_on=False)
        assert spec_oracle_examples_enabled() is False

    def test_generator_gate_matches_planner_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import experiments.spec_examples_generator as gen

        _enable(monkeypatch)
        assert gen.spec_examples_production_enabled() is True
        monkeypatch.setenv("SPEC_ORACLE_EXAMPLES_ENABLE", "false")
        assert gen.spec_examples_production_enabled() is False


# ═══ 2. Planner prompt 契约 ════════════════════════════════════════════════
class TestPlannerPrompt:
    def test_off_prompt_byte_identical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关闭：两次 plan 的 query 逐字节相同，且不含 examples 契约段。"""
        _disable(monkeypatch)
        q1: list[str] = []
        q2: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, q1)
        _plan(_make_planner(), _BASE_RESPONSE, q2)
        assert q1 == q2
        assert "【规格可执行示例" not in q1[0]

    def test_on_prompt_appends_contract_exactly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开启：query = 关闭 query + examples 契约段（逐字节追加，不改原段）。"""
        _disable(monkeypatch)
        off_q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, off_q)
        _enable(monkeypatch)
        on_q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, on_q)
        assert on_q[0] == off_q[0] + planner_mod.SPEC_EXPR_EXAMPLES_SECTION

    def test_on_prompt_contract_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, q)
        prompt = q[0]
        assert "【规格可执行示例" in prompt
        assert "最多 3 条" in prompt
        assert '"examples": [{"input": [...], "expected": ...}]' in prompt
        assert "由规格" in prompt and "推导" in prompt
        assert "输入尽量小" in prompt

    def test_negative_control_deleted_contract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """删契约负控：常量清空后即使开关开，prompt 与关闭时逐字节一致。"""
        _disable(monkeypatch)
        off_q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, off_q)
        _enable(monkeypatch)
        monkeypatch.setattr(planner_mod, "SPEC_EXPR_EXAMPLES_SECTION", "")
        on_q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, on_q)
        assert on_q[0] == off_q[0]

    def test_off_prompt_with_exec_off_but_examples_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch, exec_on=False, examples_on=True)
        q: list[str] = []
        _plan(_make_planner(), _BASE_RESPONSE, q)
        assert "【规格可执行示例" not in q[0]


# ═══ 3. Planner 输出净化 ═══════════════════════════════════════════════════
def _response_with_examples(examples: list[Any]) -> dict[str, Any]:
    response = json.loads(json.dumps(_BASE_RESPONSE))
    response["logic_analysis"]["examples"] = examples
    return response


class TestPlannerSanitize:
    def test_truncates_to_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        raw = [{"input": [i, i + 1], "expected": 2 * i + 1} for i in range(5)]
        result = _plan(_make_planner(), _response_with_examples(raw))
        examples = result["logic_analysis"]["examples"]
        assert len(examples) == 3
        assert examples[0] == {"input": [0, 1], "expected": 1}

    def test_invalid_examples_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        raw = [
            {"input": [1, 2], "expected": 3},
            {"bad": 1},
            {"input": 1},
            "not-a-dict",
            {"input": [float("nan")], "expected": 1},
            {"input": [2, 3], "expected": 5},
        ]
        result = _plan(_make_planner(), _response_with_examples(raw))
        assert result["logic_analysis"]["examples"] == [
            {"input": [1, 2], "expected": 3},
            {"input": [2, 3], "expected": 5},
        ]

    def test_disabled_removes_examples_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch, examples_on=False)
        result = _plan(_make_planner(), _response_with_examples([{"input": [1, 2], "expected": 3}]))
        assert "examples" not in result["logic_analysis"]

    def test_enabled_keeps_valid_examples(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        result = _plan(_make_planner(), _response_with_examples([{"input": [1, 2], "expected": 3}]))
        assert result["logic_analysis"]["examples"] == [{"input": [1, 2], "expected": 3}]


# ═══ 4. 链路生效（planner examples → oracle 逐示例断言）════════════════════
def _state_from_logic(logic_analysis: dict[str, Any]) -> Any:
    spec = parse_logic_analysis(logic_analysis)
    assert spec is not None
    return {
        "spec_ir": spec,
        "module_name": "add_mod",
        "target_function": "add",
        "target_code": _CODE,
    }


class TestPipeline:
    def test_planner_examples_compile_to_assertions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        result = _plan(
            _make_planner(),
            _response_with_examples([{"input": [2, 3], "expected": 5}]),
        )
        state = _state_from_logic(result["logic_analysis"])
        merged, injected, verdict = nodes._append_spec_oracle_to_test_with_verdict(
            "def test_llm():\n    assert True\n", state
        )
        assert injected is True
        assert verdict == "injected"
        assert "_specir_norm_return(add(2, 3)) == _specir_norm_return(5)" in merged
        assert "examples=1" in merged

    def test_disabled_strips_examples_and_matches_no_example_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _disable(monkeypatch)
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        monkeypatch.setenv("SPEC_ORACLE_EXEC_ENABLE", "true")
        logic = (
            dict(planner_mod._BASE_RESPONSE["logic_analysis"])
            if hasattr(planner_mod, "_BASE_RESPONSE")
            else dict(_BASE_RESPONSE["logic_analysis"])
        )
        logic["examples"] = [{"input": [2, 3], "expected": 5}]
        state = _state_from_logic(logic)
        merged, injected, verdict = nodes._append_spec_oracle_to_test_with_verdict(
            "def test_llm():\n    assert True\n", state
        )
        spec_without = dict(state["spec_ir"])
        spec_without.pop("examples", None)
        expected_code = compile_spec_oracle(
            spec_without, target_module="add_mod", target_function="add", signature_params=["a", "b"]
        )
        assert injected is True
        assert verdict == "injected"
        # nodes 追加口径 = 原文 + "\n\n\n" + oracle 产物（原文末尾自带换行）
        assert merged == "def test_llm():\n    assert True\n" + "\n\n\n" + expected_code
        assert "examples=" not in merged


# ═══ 5. 无 Planner 臂：spec_generator 接线 ══════════════════════════════════
def _anchor_state(**anchor_extra: Any) -> Any:
    return {
        "task_id": "quixbugs__add",
        "target_code": _CODE,
        "target_function": "add",
        "spec_anchor": anchor_extra,
    }


class TestSpecGeneratorWiring:
    def _mock_gen(self, monkeypatch: pytest.MonkeyPatch, *, enabled: bool, result: dict[str, Any] | Exception):
        import experiments.spec_examples_generator as gen

        calls: list[dict[str, Any]] = []

        def _fake(material: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append({"material": material, **kwargs})
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(gen, "spec_examples_production_enabled", lambda: enabled)
        monkeypatch.setattr(gen, "generate_spec_examples", _fake)
        return calls

    def test_off_no_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._mock_gen(monkeypatch, enabled=False, result={"status": "ok", "examples": []})
        state = _anchor_state(logic_analysis={"function_name": "add", "postconditions": ["r == a+b"]})
        assert rb._attach_generated_spec_examples(state) == 0
        assert calls == []

    def test_on_attaches_examples(self, monkeypatch: pytest.MonkeyPatch) -> None:
        examples = [{"input": [2, 3], "expected": 5}]
        calls = self._mock_gen(monkeypatch, enabled=True, result={"status": "ok", "examples": examples})
        state = _anchor_state(logic_analysis={"function_name": "add", "postconditions": ["r == a+b"]})
        assert rb._attach_generated_spec_examples(state) == 1
        assert len(calls) == 1
        assert calls[0]["max_examples"] == 3  # 生产 ≤3 契约
        assert calls[0]["signature_params"] == ["a", "b"]
        assert state["spec_anchor"]["logic_analysis"]["examples"] == examples

    def test_on_empty_result_no_mutation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._mock_gen(monkeypatch, enabled=True, result={"status": "empty", "examples": [], "reason": "x"})
        state = _anchor_state(logic_analysis={"function_name": "add", "postconditions": ["r == a+b"]})
        before = json.dumps(state["spec_anchor"], sort_keys=True)
        assert rb._attach_generated_spec_examples(state) == 0
        assert json.dumps(state["spec_anchor"], sort_keys=True) == before

    def test_on_exception_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._mock_gen(monkeypatch, enabled=True, result=RuntimeError("boom"))
        state = _anchor_state(logic_analysis={"function_name": "add", "postconditions": ["r == a+b"]})
        assert rb._attach_generated_spec_examples(state) == 0
        assert "examples" not in state["spec_anchor"]["logic_analysis"]

    def test_human_spec_only_anchor_builds_logic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        examples = [{"input": [1], "expected": 2}]
        calls = self._mock_gen(monkeypatch, enabled=True, result={"status": "ok", "examples": examples})
        state = _anchor_state(human_spec="add(a,b) 返回两数之和", function_name="add")
        assert rb._attach_generated_spec_examples(state) == 1
        assert calls[0]["material"]["human_spec"] == "add(a,b) 返回两数之和"
        logic = state["spec_anchor"]["logic_analysis"]
        assert logic["function_name"] == "add"
        assert logic["examples"] == examples

    def test_no_anchor_no_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._mock_gen(monkeypatch, enabled=True, result={"status": "ok", "examples": []})
        state: Any = {"task_id": "t", "target_code": _CODE, "target_function": "add"}
        assert rb._attach_generated_spec_examples(state) == 0
        assert calls == []


# ═══ 6. 行字段（成功/失败键位一致 + 三值来源）══════════════════════════════
class TestRowFields:
    def test_off_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _disable(monkeypatch)
        state = {"spec_ir": {"examples": [{"input": [1], "expected": 2}]}}
        assert rb._spec_oracle_examples_fields(state) == {
            "spec_oracle_examples_source": "none",
            "spec_oracle_examples_count": 0,
        }

    def test_planner_from_spec_ir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        state = {"spec_ir": {"examples": [{"input": [1], "expected": 2}, {"input": [2], "expected": 4}]}}
        assert rb._spec_oracle_examples_fields(state) == {
            "spec_oracle_examples_source": "planner",
            "spec_oracle_examples_count": 2,
        }

    def test_planner_from_test_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        state = {"test_plan": {"logic_analysis": {"examples": [{"input": [1], "expected": 2}]}}}
        assert rb._spec_oracle_examples_fields(state)["spec_oracle_examples_source"] == "planner"

    def test_spec_generator_from_anchor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        state = {
            "spec_anchor": {"logic_analysis": {"examples": [{"input": [1], "expected": 2}]}},
        }
        assert rb._spec_oracle_examples_fields(state) == {
            "spec_oracle_examples_source": "spec_generator",
            "spec_oracle_examples_count": 1,
        }

    def test_none_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        assert rb._spec_oracle_examples_fields(None)["spec_oracle_examples_source"] == "none"

    def test_failure_branch_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _disable(monkeypatch)
        row = rb._build_task_result(_make_task(), 0.1, None, diagnosis="probe", error_category="error")
        assert row["spec_oracle_examples_source"] == "none"
        assert row["spec_oracle_examples_count"] == 0

    def test_success_branch_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable(monkeypatch)
        final_state = {"spec_ir": {"examples": [{"input": [1, 2], "expected": 3}]}}
        row = rb._build_task_result(_make_task(), 0.1, final_state)
        assert row["spec_oracle_examples_source"] == "planner"
        assert row["spec_oracle_examples_count"] == 1


# ═══ 7. env 门禁登记 ═══════════════════════════════════════════════════════
class TestEnvGates:
    def test_env_budget_yaml_contains_both_keys(self) -> None:
        text = (PROJECT_ROOT / "docs" / "env_budget.yaml").read_text(encoding="utf-8")
        assert "SPEC_ORACLE_EXAMPLES_ENABLE" in text
        assert "AITESTER_POSTPROCESS_WARN_S" in text

    def test_manual_registration_keeps_postprocess_key(self) -> None:
        import importlib.util

        gate_path = PROJECT_ROOT / "scripts" / "gates" / "check_env_budget.py"
        spec = importlib.util.spec_from_file_location("check_env_budget_q1", gate_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert "AITESTER_POSTPROCESS_WARN_S" in module.MANUALLY_REGISTERED

    def test_env_budget_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "gates" / "check_env_budget.py"), "--check"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_env_snapshot_keys_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "gates" / "check_env_snapshot_keys.py")],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
