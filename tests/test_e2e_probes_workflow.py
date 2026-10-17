#!/usr/bin/env python3
"""N-1 探针模块契约测试：`scripts/tools/e2e_probes_workflow.py`（零 LLM / 零网络）。

锁定四组行为：

1. **探针清单契约**：PROBES 被框架发现（无加载错误）、名称唯一/kebab-case、
   group 合法、requires_llm 的探针数与超时、全部 func 零参可调用；
2. **零 LLM 探针逻辑**（真实调用，快）：workflow 装配子进程、executor 沙箱、
   安全守卫（危险 API / 命名契约 / 测试黑客 / 确定性修复 / 快照回滚）、
   trace 脱敏、事件总线、FL_spectral / fault localizer / multi-candidate；
3. **负控与分类**：mock 出失败形态时探针返回 fail/error/skip（不得静默 pass）；
   repair 探针必须区分"模型未产出"（skip）与"功能故障"（fail）；
4. **辅助函数**：连续多 JSON 文档解析（CLI 多文件 --json 口径）、尾部截断。

真实 LLM 探针在测试中一律 mock（PlannerAgent / GeneratorAgent / DebuggerAgent /
ExecutorAgent / run_cmd / invoke_workflow），零网络、零 API 配额。
"""

from __future__ import annotations

import importlib
import json
import re
from typing import Any

import pytest

import scripts.tools.e2e_probes_workflow as probes_mod
from scripts.tools.e2e_probe import Probe, ProbeOutcome, discover_probes

_ALLOWED_GROUPS = {"cli", "workflow", "agents", "repair", "safety", "observability", "localization"}


def _by_name() -> dict[str, Probe]:
    return {probe.name: probe for probe in probes_mod.PROBES}


# ─── 1. 探针清单契约 ────────────────────────────────────────────────────────
class TestProbeInventory:
    def test_framework_discovers_module_without_errors(self) -> None:
        probes, errors = discover_probes(["scripts.tools.e2e_probes_workflow"])
        assert errors == []
        assert len(probes) == len(probes_mod.PROBES)

    def test_at_least_ten_probes(self) -> None:
        assert len(probes_mod.PROBES) >= 10

    def test_names_unique_and_kebab_case(self) -> None:
        names = [probe.name for probe in probes_mod.PROBES]
        assert len(names) == len(set(names))
        for name in names:
            assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), name

    def test_groups_are_declared(self) -> None:
        groups = {probe.group for probe in probes_mod.PROBES}
        assert groups <= _ALLOWED_GROUPS
        # 任务书要求的分组必须都在场
        assert {"cli", "workflow", "agents", "repair", "safety", "localization"} <= groups

    def test_llm_probe_split_and_timeouts(self) -> None:
        llm = [probe for probe in probes_mod.PROBES if probe.requires_llm]
        zero = [probe for probe in probes_mod.PROBES if not probe.requires_llm]
        assert len(llm) >= 5, "至少 5 个真实 LLM 探针（CLI/workflow/agents/repair）"
        assert len(zero) >= 10, "零 LLM 子集至少 10 个探针"
        for probe in llm:
            assert probe.timeout_s >= 300.0, f"LLM 探针 {probe.name} 超时过短"

    def test_all_funcs_zero_arg_callable(self) -> None:
        import inspect

        for probe in probes_mod.PROBES:
            assert callable(probe.func)
            signature = inspect.signature(probe.func)
            assert not signature.parameters, f"{probe.name} 探针函数必须零参数"

    def test_descriptions_non_empty(self) -> None:
        for probe in probes_mod.PROBES:
            assert probe.description.strip(), f"{probe.name} 缺 description"

    def test_required_coverage_areas_present(self) -> None:
        """任务书 7 组覆盖面必须都有探针。"""
        names = {probe.name for probe in probes_mod.PROBES}
        required_fragments = [
            "cli-help",
            "cli-list-examples",
            "cli-check-dataset-quixbugs",
            "cli-run-json-single",
            "cli-run-multi-parallel",
            "workflow-fast-assembly",
            "workflow-logic-assembly",
            "workflow-logic-invoke",
            "agents-planner-structured-plan",
            "agents-generator-parseable-tests",
            "agents-executor-run",
            "repair-debugger-patch-chain",
            "repair-graph-loop",
            "safety-dangerous-api-guard",
            "safety-naming-contract-guard",
            "safety-test-hacking-detection",
            "safety-deterministic-repair",
            "safety-patch-rollback",
            "observability-trace-redaction",
            "observability-event-bus",
            "analysis-fl-spectral-topk",
            "analysis-fault-localizer-gold",
            "analysis-multi-candidate",
        ]
        missing = [name for name in required_fragments if name not in names]
        assert not missing, f"缺探针: {missing}"


# ─── 2. CLI 探针（mock run_cmd，零子进程）───────────────────────────────────
_HELP_OUT = "Commands:\n  run\n  list-examples\n  check-dataset\n  clean-venv-cache\n"


class TestCliProbes:
    def test_cli_help_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, _HELP_OUT, ""))
        outcome = probes_mod.probe_cli_help()
        assert outcome.status == "pass"

    def test_cli_help_fail_when_subcommand_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, "Commands:\n  run\n", ""))
        outcome = probes_mod.probe_cli_help()
        assert outcome.status == "fail"
        assert "缺少子命令" in outcome.detail

    def test_cli_help_error_on_nonzero_rc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (2, "", "boom"))
        assert probes_mod.probe_cli_help().status == "error"

    def test_cli_list_examples_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = "可用示例文件（共 2 个）\n  • buggy_library.py\n  • calculator.py\n使用示例：\n  python main.py run examples/calculator.py\n"
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, out, ""))
        outcome = probes_mod.probe_cli_list_examples()
        assert outcome.status == "pass"
        assert "calculator.py" in outcome.detail

    def test_cli_list_examples_fails_on_dunder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = "可用示例文件（共 2 个）\n  • __init__.py\n  • calculator.py\n使用示例：\n  python main.py run examples/__init__.py\n"
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, out, ""))
        outcome = probes_mod.probe_cli_list_examples()
        assert outcome.status == "fail"

    def test_cli_check_dataset_pass_records_redaction_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = (
            "ℹ 数据集 quixbugs 共加载 50 个任务\n"
            "── quixbugs__bitcount ──\n"
            "ℹ ✓ 全量质量检查通过（50 个任务无加载问题）\n"
            "ℹ 路径 /Users/x/.<REDACTED_KEY>\n"
        )
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, out, ""))
        outcome = probes_mod.probe_cli_check_dataset()
        assert outcome.status == "pass"
        assert outcome.evidence["task_count"] == 50
        assert outcome.evidence["redacted_path_segments"] == 1

    def test_cli_check_dataset_fail_when_tasks_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, "共加载 3 个任务\n", ""))
        assert probes_mod.probe_cli_check_dataset().status == "fail"

    def test_cli_run_json_single_pass_and_uses_verbose(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {
            "success": True,
            "file": "/repo/examples/calculator.py",
            "passed": True,
            "coverage": 88.0,
            "iterations": 1,
            "event_bus": {},
            "cost_budget": {},
        }
        captured: dict[str, Any] = {}

        def _fake_run_cmd(cmd: list[str], **kwargs: Any) -> tuple[int, str, str]:
            captured["cmd"] = cmd
            return 0, json.dumps(payload, indent=2), ""

        monkeypatch.setattr(probes_mod, "run_cmd", _fake_run_cmd)
        outcome = probes_mod.probe_cli_run_json_single()
        assert outcome.status == "pass"
        assert "--verbose" in captured["cmd"], "探针必须覆盖 --json --verbose 组合（N-1 实测缺陷回归面）"
        assert outcome.evidence["passed"] is True

    def test_cli_run_json_single_fail_on_polluted_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, "ℹ 提示：...\n{}", ""))
        outcome = probes_mod.probe_cli_run_json_single()
        assert outcome.status == "fail"

    def test_cli_run_multi_parallel_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        docs = [
            {"file": "/x/mod_a.py", "passed": True},
            {"file": "/x/mod_b.py", "passed": False},
        ]
        stdout = "\n".join(json.dumps(doc, indent=2) for doc in docs)
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (1, stdout, ""))
        outcome = probes_mod.probe_cli_run_multi_parallel()
        assert outcome.status == "pass"
        assert outcome.evidence["payload_count"] == 2
        assert outcome.evidence["passed_count"] == 1

    def test_cli_run_multi_parallel_fail_on_count_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "run_cmd", lambda *a, **kw: (0, json.dumps({"file": "a.py"}), ""))
        outcome = probes_mod.probe_cli_run_multi_parallel()
        assert outcome.status == "fail"


# ─── 3. workflow 探针 ───────────────────────────────────────────────────────
_FAST_SNAPSHOT: dict[str, Any] = {
    "active_profile": "fast",
    "nodes": ["planner", "generator", "executor", "debugger", "patch_applier"],
    "edges": [
        "planner->generator",
        "generator->executor",
        "executor->debugger",
        "debugger->patch_applier",
        "patch_applier->executor",
    ],
    "flags": {},
}
_LOGIC_SNAPSHOT: dict[str, Any] = {
    "active_profile": "logic",
    "nodes": ["planner", "generator", "executor", "debugger", "patch_applier", "mutation_advisor"],
    "edges": [
        "planner->generator",
        "generator->executor",
        "executor->mutation_advisor",
        "mutation_advisor->generator",
        "debugger->patch_applier",
    ],
    "flags": {"DETECTION_FIRST_ENABLE": "true", "FL_SPECTRAL_ENABLE": "true"},
}


class TestWorkflowProbes:
    def test_fast_assembly_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "_inspect_workflow", lambda profile: dict(_FAST_SNAPSHOT))
        outcome = probes_mod.probe_workflow_fast_assembly()
        assert outcome.status == "pass"

    def test_fast_assembly_fails_on_extra_logic_node(self, monkeypatch: pytest.MonkeyPatch) -> None:
        snapshot = dict(_FAST_SNAPSHOT)
        snapshot["nodes"] = [*_FAST_SNAPSHOT["nodes"], "mutation_advisor"]
        monkeypatch.setattr(probes_mod, "_inspect_workflow", lambda profile: snapshot)
        assert probes_mod.probe_workflow_fast_assembly().status == "fail"

    def test_fast_assembly_propagates_inspect_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "_inspect_workflow", lambda profile: ProbeOutcome("error", "子进程失败"))
        assert probes_mod.probe_workflow_fast_assembly().status == "error"

    def test_logic_assembly_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probes_mod, "_inspect_workflow", lambda profile: dict(_LOGIC_SNAPSHOT))
        outcome = probes_mod.probe_workflow_logic_assembly()
        assert outcome.status == "pass"

    def test_logic_assembly_fails_without_mutation_advisor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        snapshot = dict(_LOGIC_SNAPSHOT)
        snapshot["nodes"] = [node for node in _LOGIC_SNAPSHOT["nodes"] if node != "mutation_advisor"]
        monkeypatch.setattr(probes_mod, "_inspect_workflow", lambda profile: snapshot)
        assert probes_mod.probe_workflow_logic_assembly().status == "fail"

    def test_logic_invoke_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        final_state: dict[str, Any] = {
            "test_plan": {"function_name": "add", "test_cases": [{"case_name": "basic"}]},
            "generated_test": "def test_add():\n    assert add(2, 3) == 5\n",
            "execution_trace": [{"passed": False}],
            "test_passed": True,
            "iteration": 0,
        }
        monkeypatch.setattr(probes_mod, "invoke_workflow", lambda *a, **kw: (final_state, 1.5))
        outcome = probes_mod.probe_workflow_logic_invoke()
        assert outcome.status == "pass"
        assert outcome.evidence["stop_reason"] == "test_passed"
        assert outcome.evidence["checks"]["execution_trace_present"] is True

    def test_logic_invoke_fails_when_terminal_fields_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        final_state: dict[str, Any] = {
            "target_file": "",
            "test_plan": None,
            "generated_test": "",
            "execution_trace": [],
        }
        monkeypatch.setattr(probes_mod, "invoke_workflow", lambda *a, **kw: (final_state, 0.1))
        outcome = probes_mod.probe_workflow_logic_invoke()
        assert outcome.status == "fail"

    def test_logic_invoke_error_on_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*a: Any, **kw: Any) -> Any:
            raise RuntimeError("graph crash")

        monkeypatch.setattr(probes_mod, "invoke_workflow", _boom)
        assert probes_mod.probe_workflow_logic_invoke().status == "error"


# ─── 4. agents 探针 ─────────────────────────────────────────────────────────
class _FakePlanner:
    def __init__(self) -> None:
        self.result: dict[str, Any] = {
            "function_name": "add",
            "logic_analysis": {"postconditions": ["返回值等于 a + b"]},
            "test_cases": [{"case_name": "basic", "input_args": "(2, 3)", "expected_output": "5"}],
            "logic_degraded": False,
        }

    def plan(self, target_code: str, target_function: str | None = None) -> dict[str, Any]:
        return dict(self.result)


class _FakeGenerator:
    def __init__(
        self, code: str = "from e2e_calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    ) -> None:
        self.code = code

    def generate(self, *args: Any, **kwargs: Any) -> str:
        return self.code


class TestAgentProbes:
    def test_planner_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.planner as planner_mod

        monkeypatch.setattr(planner_mod, "PlannerAgent", _FakePlanner)
        outcome = probes_mod.probe_agents_planner_structured_plan()
        assert outcome.status == "pass"
        assert outcome.evidence["test_cases"] == 1

    def test_planner_skip_when_model_produces_no_cases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.planner as planner_mod

        class _Empty(_FakePlanner):
            def __init__(self) -> None:
                self.result = {"function_name": "add", "logic_analysis": {}, "test_cases": []}

        monkeypatch.setattr(planner_mod, "PlannerAgent", _Empty)
        outcome = probes_mod.probe_agents_planner_structured_plan()
        assert outcome.status == "skip"

    def test_planner_fail_on_bad_case_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.planner as planner_mod

        class _Bad(_FakePlanner):
            def __init__(self) -> None:
                self.result = {
                    "function_name": "add",
                    "logic_analysis": {},
                    "test_cases": [{"case_name": "x"}],
                }

        monkeypatch.setattr(planner_mod, "PlannerAgent", _Bad)
        assert probes_mod.probe_agents_planner_structured_plan().status == "fail"

    def test_generator_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.generator as generator_mod

        monkeypatch.setattr(generator_mod, "GeneratorAgent", _FakeGenerator)
        outcome = probes_mod.probe_agents_generator_parseable()
        assert outcome.status == "pass"
        assert outcome.evidence["test_functions"] == 1

    def test_generator_fail_on_unparseable_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.generator as generator_mod

        monkeypatch.setattr(generator_mod, "GeneratorAgent", lambda: _FakeGenerator("def broken(:\n"))
        assert probes_mod.probe_agents_generator_parseable().status == "fail"

    def test_generator_skip_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.generator as generator_mod

        monkeypatch.setattr(generator_mod, "GeneratorAgent", lambda: _FakeGenerator(""))
        assert probes_mod.probe_agents_generator_parseable().status == "skip"

    def test_executor_probe_real_run(self) -> None:
        """执行器探针真实调用（本地 pytest 子进程，零 LLM）。"""
        outcome = probes_mod.probe_agents_executor_run()
        assert outcome.status == "pass"
        assert outcome.evidence["pass_case"]["passed"] is True


# ─── 5. repair 探针（mock LLM，验证分类纪律）──────────────────────────────
class _FakeExecutor:
    """首次执行失败、应用补丁后通过的 Executor 替身。"""

    def __init__(self, timeout: int = 60) -> None:
        self.calls = 0

    def execute(self, test_code: str, target_file: str, target_function: str | None = None) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {"passed": False, "output": "AssertionError: 5 != -1", "failed_cases": [{"name": "test_add"}]}
        return {"passed": True, "output": "1 passed", "failed_cases": []}


class _FakeDebugger:
    def __init__(self, patch: str = "def add(a, b):\n    return a + b\n") -> None:
        self.patch = patch

    def debug(self, **kwargs: Any) -> dict[str, Any]:
        return {"patch": self.patch, "error_category": "assertion", "root_cause": "减法冒充加法"}


class TestRepairProbe:
    def test_repair_chain_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.debugger as debugger_mod
        import src.agents.executor as executor_mod

        executor = _FakeExecutor()
        monkeypatch.setattr(executor_mod, "ExecutorAgent", lambda timeout=60: executor)
        monkeypatch.setattr(debugger_mod, "DebuggerAgent", _FakeDebugger)
        outcome = probes_mod.probe_repair_debugger_patch_chain()
        assert outcome.status == "pass"
        assert outcome.evidence["patch_applied"] is True
        assert outcome.evidence["after_passed"] is True

    def test_repair_chain_skip_when_model_produces_no_patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.debugger as debugger_mod
        import src.agents.executor as executor_mod

        monkeypatch.setattr(executor_mod, "ExecutorAgent", lambda timeout=60: _FakeExecutor())
        monkeypatch.setattr(debugger_mod, "DebuggerAgent", lambda: _FakeDebugger(patch=""))
        outcome = probes_mod.probe_repair_debugger_patch_chain()
        assert outcome.status == "skip"
        assert "model_nonproduction" in outcome.detail

    def test_repair_chain_fail_when_patch_applied_but_test_still_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.debugger as debugger_mod
        import src.agents.executor as executor_mod

        class _AlwaysFail(_FakeExecutor):
            def execute(self, test_code: str, target_file: str, target_function: str | None = None) -> dict[str, Any]:
                return {"passed": False, "output": "still failing", "failed_cases": [{"name": "test_add"}]}

        monkeypatch.setattr(executor_mod, "ExecutorAgent", lambda timeout=60: _AlwaysFail())
        monkeypatch.setattr(debugger_mod, "DebuggerAgent", _FakeDebugger)
        outcome = probes_mod.probe_repair_debugger_patch_chain()
        assert outcome.status == "fail"


class TestRepairGraphProbe:
    """真实 graph 修复环探针（mock invoke_workflow；分类纪律同任务书）。"""

    _BUGGY = 'def add(a, b):\n    """Return the sum of a and b."""\n    return a - b\n'
    _FIXED = 'def add(a, b):\n    """Return the sum of a and b."""\n    return a + b\n'

    def _state(self, *, applied: bool, test_passed: bool, patch: str = "p") -> dict[str, Any]:
        return {
            "target_code": self._FIXED if applied else self._BUGGY,
            "patch": patch,
            "test_passed": test_passed,
            "iteration": 1 if applied else 0,
            "repair_history": (
                [{"iteration": 1, "diagnosis": "减法冒充加法", "error_category": "assertion", "patch_applied": True}]
                if applied
                else []
            ),
        }

    def test_graph_loop_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        final = self._state(applied=True, test_passed=True)
        monkeypatch.setattr(probes_mod, "invoke_workflow", lambda *a, **kw: (final, 2.0))
        outcome = probes_mod.probe_repair_graph_loop()
        assert outcome.status == "pass"
        assert outcome.evidence["patch_applied_rounds"] == 1
        assert outcome.evidence["stop_reason"] == "test_passed"
        assert outcome.evidence["dangerous_api_added"] == []

    def test_graph_loop_skip_when_debugger_not_entered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        final = self._state(applied=False, test_passed=True, patch="")
        monkeypatch.setattr(probes_mod, "invoke_workflow", lambda *a, **kw: (final, 0.5))
        outcome = probes_mod.probe_repair_graph_loop()
        assert outcome.status == "skip"
        assert "非功能故障" in outcome.detail

    def test_graph_loop_fail_when_patched_but_not_passing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        final = self._state(applied=True, test_passed=False)
        monkeypatch.setattr(probes_mod, "invoke_workflow", lambda *a, **kw: (final, 2.0))
        assert probes_mod.probe_repair_graph_loop().status == "fail"

    def test_graph_loop_error_on_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*a: Any, **kw: Any) -> Any:
            raise RuntimeError("graph crash")

        monkeypatch.setattr(probes_mod, "invoke_workflow", _boom)
        assert probes_mod.probe_repair_graph_loop().status == "error"


# ─── 6. safety / observability / analysis 探针（真实调用，零 LLM）──────────
class TestSafetyProbes:
    def test_dangerous_api_guard_real(self) -> None:
        assert probes_mod.probe_safety_dangerous_api_guard().status == "pass"

    def test_dangerous_api_guard_negative_control(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """守卫被绕过（mock 放行）时探针必须 fail，而不是静默通过。"""
        import src.tools.patch_applier as applier_mod

        monkeypatch.setattr(applier_mod, "safe_apply_patch", lambda code, patch: (patch, True))
        outcome = probes_mod.probe_safety_dangerous_api_guard()
        assert outcome.status == "fail"

    def test_naming_contract_guard_real(self) -> None:
        assert probes_mod.probe_safety_naming_contract_guard().status == "pass"

    def test_test_hacking_detection_real(self) -> None:
        assert probes_mod.probe_safety_test_hacking_detection().status == "pass"

    def test_deterministic_repair_real(self) -> None:
        assert probes_mod.probe_safety_deterministic_repair().status == "pass"

    def test_patch_rollback_real(self) -> None:
        assert probes_mod.probe_safety_patch_rollback().status == "pass"


class TestObservabilityAnalysisProbes:
    def test_trace_redaction_real(self) -> None:
        assert probes_mod.probe_observability_trace_redaction().status == "pass"

    def test_event_bus_real(self) -> None:
        assert probes_mod.probe_observability_event_bus().status == "pass"

    def test_fl_spectral_real(self) -> None:
        outcome = probes_mod.probe_analysis_fl_spectral_topk()
        assert outcome.status == "pass"
        assert outcome.evidence["top"][0]["line"] == outcome.evidence["buggy_line"]

    def test_fault_localizer_real(self) -> None:
        outcome = probes_mod.probe_analysis_fault_localizer_gold()
        assert outcome.status == "pass"
        assert outcome.evidence["hit"]["localization_hit_function"] is True

    def test_multi_candidate_real(self) -> None:
        outcome = probes_mod.probe_analysis_multi_candidate()
        assert outcome.status == "pass"
        assert outcome.evidence["best_index"] == 1


# ─── 7. 辅助函数 ────────────────────────────────────────────────────────────
class TestHelpers:
    def test_json_objects_parses_concatenated_documents(self) -> None:
        text = '{"a": 1}\n\n{\n  "b": 2\n}\n'
        assert probes_mod._json_objects(text) == [{"a": 1}, {"b": 2}]

    def test_json_objects_rejects_invalid(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            probes_mod._json_objects("not json")

    def test_tail_compacts_and_truncates(self) -> None:
        assert probes_mod._tail("a\n b\tc", limit=5) == "a b c"
        assert len(probes_mod._tail("x" * 500, limit=20)) <= 20

    def test_module_reexports_probes(self) -> None:
        module = importlib.import_module("scripts.tools.e2e_probes_workflow")
        assert hasattr(module, "PROBES")
        assert module.__all__ == ["PROBES"]
