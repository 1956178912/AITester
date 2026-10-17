"""N-3（A-05 后续修复）契约测试：spec_anchor→oracle 接线 + 独立判读 + 重放模式。

覆盖三块：
1. **接线修复**（`src/graph/nodes.py`）：规约材料四源优先级（spec_ir →
   test_plan.logic_analysis → spec_anchor.logic_analysis / human_spec）、
   人类 docstring 锚不强行编译、逐类可审计 verdict、开关关闭零行为差异；
2. **独立判读**（`experiments/_m1_metrics.py`）：LLM-suite / oracle-suite 分开
   执行（pytest -k 子集）、结果行两键语义、fail-closed/超时单列、无 oracle 时
   命令逐位不变且零额外子进程；
3. **独立判读重放**（`experiments/oracle_quality_replay.py --independent-judging`）：
   anchor-only state 重建、M-2 基线加载与逐任务对账、有限运行语义、README。

零 LLM / 零网络；仅 1 例真实 pytest 子进程（本地执行，<3s）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import experiments._m1_metrics as m1
import experiments.oracle_quality_replay as oq
import experiments.run_benchmark as rb
from src.datasets.dataset_loader import BenchmarkTask

# ─── 微型 fixture ──────────────────────────────────────────────────────────
_BUGGY_CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"
_FIXED_CODE = "def add(a: int, b: int) -> int:\n    return a + b + 1\n"
_GOLD_TEST = "from add_off_by_one import add\n\n\ndef test_gold():\n    assert add(1, 2) == 4\n"
_LLM_TEST = "from add_off_by_one import add\n\n\ndef test_f2p():\n    assert add(1, 2) == 4\n"

# 可编译规约材料（逻辑分析原始 dict 形态；parse_logic_analysis 可解析）
_LOGIC_COMPILABLE: dict[str, Any] = {
    "function_name": "add",
    "postconditions_expr": ["result == a + b"],
}
_LOGIC_UNPARSEABLE: dict[str, Any] = {"not_a_logic_field": ["x"]}
_HUMAN_SPEC = "Add two integers\n\nInput:\n    a: int\n    b: int\n\nOutput:\n    a + b"
_TARGET_CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"


def _synthetic_task() -> BenchmarkTask:
    """最小 F2P 可判定 synthetic 任务（gold test_cases / fixed 齐备）。"""
    return BenchmarkTask(
        task_id="probe__add_off_by_one",
        repo_name="synthetic/_probe",
        problem_statement="off-by-one",
        instance_code=_BUGGY_CODE,
        test_code=_GOLD_TEST,
        expected_pass_count=1,
        total_test_count=1,
        metadata={
            "source": "synthetic",
            "test_cases": _GOLD_TEST,
            "fixed": _FIXED_CODE,
            "is_cross_file": False,
        },
    )


def _state_with_generated(generated: str) -> dict[str, Any]:
    return {"generated_test": generated, "test_passed": True, "regeneration_count": 0}


def _oracle_block(assert_value: int) -> str:
    """构造注入块（与 compile_spec_oracle 产物同形，含固定测试名）。"""
    return (
        "\n\n\n# SpecIR v2 确定性 oracle（compile_readiness=1.00）\n"
        "from add_off_by_one import add\n\n"
        "def test_specir_v2_oracle():\n"
        f"    assert add(1, 2) == {assert_value}\n"
    )


def _state_with_anchor(
    *,
    anchor: dict[str, Any] | None = None,
    target_function: str | None = "add",
    module_name: str | None = "mod_add",
    target_code: str = _TARGET_CODE,
) -> Any:
    state: dict[str, Any] = {"target_code": target_code, "module_name": module_name}
    if target_function is not None:
        state["target_function"] = target_function
    if anchor is not None:
        state["spec_anchor"] = anchor
    return state


def _fake_run_factory(*, buggy: tuple[Any, ...] | None, fixed: tuple[Any, ...] | None):
    """构造 _run_pytest_in_tmp 替身：按 target_code 返回 buggy/fixed 侧结果。

    O-1 起 ``_suite_run_verdict`` 会解析 pytest 摘要行区分 pass/skip/unavailable；
    替身输出为空时补一个最小摘要（与真实 pytest 输出同形），避免把"无摘要"的
    合成结果误当成 unavailable。
    """

    def _with_summary(run: tuple[Any, ...] | None) -> tuple[Any, ...] | None:
        if run is None:
            return None
        rc, out, err = run
        if not str(out).strip() and rc in (0, 1):
            out = "1 passed in 0.01s" if rc == 0 else "1 failed in 0.01s"
        return (rc, out, err)

    calls: list[dict[str, Any]] = []

    def fake(test_code: str, target_code: str, module_name: str, **kwargs: Any) -> tuple[Any, ...] | None:
        calls.append({"test_code": test_code, "target_code": target_code, "module_name": module_name, **kwargs})
        if str(target_code).strip() == _FIXED_CODE.strip():
            return _with_summary(fixed)
        return _with_summary(buggy)

    return fake, calls


# ═══ 1. 接线修复：材料优先级 / verdict / 零差异 ═════════════════════════════
class TestSpecAnchorWiring:
    """_resolve_spec_oracle_material + 生产注入函数的材料优先级。"""

    def test_priority_spec_ir_first(self) -> None:
        from src.graph.nodes import _resolve_spec_oracle_material

        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": _LOGIC_UNPARSEABLE})
        state["spec_ir"] = {"function_name": "add", "postconditions_expr": ["result == a + b"]}
        state["test_plan"] = {"logic_analysis": _LOGIC_UNPARSEABLE}
        material, source, verdict = _resolve_spec_oracle_material(state)
        assert material is not None and source == "spec_ir"
        assert verdict == "not_attempted"

    def test_priority_test_plan_second(self) -> None:
        from src.graph.nodes import _resolve_spec_oracle_material

        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": _LOGIC_UNPARSEABLE})
        state["test_plan"] = {"logic_analysis": dict(_LOGIC_COMPILABLE)}
        material, source, _verdict = _resolve_spec_oracle_material(state)
        assert material is not None and source == "test_plan.logic_analysis"

    def test_priority_spec_anchor_logic_analysis_third(self) -> None:
        """生产 df_spec/union 臂形态：只有 spec_anchor（无 test_plan/spec_ir）。"""
        from src.graph.nodes import _resolve_spec_oracle_material

        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": dict(_LOGIC_COMPILABLE)})
        material, source, _verdict = _resolve_spec_oracle_material(state)
        assert material is not None
        assert source == "spec_anchor.logic_analysis"

    def test_human_spec_only_not_forced_to_compile(self) -> None:
        """doc/augment 臂形态：仅 human_spec → 不强行编译，记可审计原因。"""
        from src.graph.nodes import (
            _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY,
            _resolve_spec_oracle_material,
        )

        state = _state_with_anchor(anchor={"function_name": "add", "human_spec": _HUMAN_SPEC})
        material, source, verdict = _resolve_spec_oracle_material(state)
        assert material is None
        assert source == "spec_anchor.human_spec"
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY

    def test_anchor_unparseable_reason(self) -> None:
        from src.graph.nodes import (
            _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_ANCHOR_UNPARSEABLE,
            _resolve_spec_oracle_material,
        )

        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": _LOGIC_UNPARSEABLE})
        material, _source, verdict = _resolve_spec_oracle_material(state)
        assert material is None
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_ANCHOR_UNPARSEABLE

    def test_no_material_reason(self) -> None:
        from src.graph.nodes import _resolve_spec_oracle_material

        material, source, verdict = _resolve_spec_oracle_material(_state_with_anchor())
        assert material is None and source == ""
        assert verdict == "not_attempted"

    def test_missing_target_reason(self) -> None:
        """有材料但既无 target_function 也无 material.function_name → missing_target。"""
        from src.graph.nodes import (
            _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_MISSING_TARGET,
            _resolve_spec_oracle_material,
        )

        spec = {"function_name": "add", "postconditions_expr": ["result == a + b"]}
        state = _state_with_anchor(target_function=None)
        state["spec_ir"] = spec
        state["spec_ir"].pop("function_name")
        state["spec_ir"]["postconditions"] = ["r == a + b"]
        state["module_name"] = "mod_add"
        _material, _source, _verdict = _resolve_spec_oracle_material(state)
        # 材料可解析但无函数名：注入函数返回 missing_target
        from src.graph.nodes import _append_spec_oracle_to_test_with_verdict

        merged, injected, verdict = _append_spec_oracle_to_test_with_verdict(_LLM_TEST, state)
        assert merged == _LLM_TEST and injected is False
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_MISSING_TARGET

    def test_production_injection_uses_anchor_only_state(self) -> None:
        """N-3 核心：anchor-only state（生产 df_spec 臂形态）现在能注入。"""
        from src.graph.nodes import _append_spec_oracle_to_test_with_verdict

        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": dict(_LOGIC_COMPILABLE)})
        merged, injected, verdict = _append_spec_oracle_to_test_with_verdict(_LLM_TEST, state)
        assert injected is True and verdict == "injected"
        assert merged.startswith(_LLM_TEST)
        assert "test_specir_v2_oracle" in merged

    def test_human_spec_production_injection_not_attempted(self) -> None:
        from src.graph.nodes import (
            _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY,
            _append_spec_oracle_to_test_with_verdict,
        )

        state = _state_with_anchor(anchor={"function_name": "add", "human_spec": _HUMAN_SPEC})
        merged, injected, verdict = _append_spec_oracle_to_test_with_verdict(_LLM_TEST, state)
        assert (merged, injected) == (_LLM_TEST, False)
        assert verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED_HUMAN_SPEC_ONLY

    def test_switch_off_anchor_state_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开关关闭：即便锚材料齐备也逐字节不变、injected=None（零差异证据）。"""
        from src.graph.nodes import _spec_oracle_injection_verdict

        monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
        state = _state_with_anchor(anchor={"function_name": "add", "logic_analysis": dict(_LOGIC_COMPILABLE)})
        merged, injected, verdict = _spec_oracle_injection_verdict(_LLM_TEST, state)  # type: ignore[arg-type]
        assert merged == _LLM_TEST
        assert injected is None
        assert verdict == "not_attempted"

    def test_verdict_domain_backward_compatible(self) -> None:
        from src.graph.nodes import _SPEC_ORACLE_VERDICT_DOMAIN

        legacy = {
            "not_attempted",
            "compiled_empty",
            "injected",
            "injected_and_passed",
            "injected_and_failed",
        }
        assert legacy <= set(_SPEC_ORACLE_VERDICT_DOMAIN)
        assert {
            "not_attempted_missing_target",
            "not_attempted_human_spec_only",
            "not_attempted_anchor_unparseable",
        } <= set(_SPEC_ORACLE_VERDICT_DOMAIN)
        assert len(_SPEC_ORACLE_VERDICT_DOMAIN) == len(set(_SPEC_ORACLE_VERDICT_DOMAIN))

    def test_historical_test_plan_injection_text_unchanged(self) -> None:
        """test_plan 材料路径（历史口径）产物与直接调用编译器逐字节一致。"""
        from src.graph.nodes import _append_spec_oracle_to_test_with_verdict
        from src.specs import compile_spec_oracle, parse_logic_analysis

        logic = {"function_name": "add", "postconditions_expr": ["result == a + b"]}
        state: Any = {
            "target_code": _TARGET_CODE,
            "module_name": "mod_add",
            "target_function": "add",
            "test_plan": {"logic_analysis": dict(logic)},
        }
        merged, injected, _verdict = _append_spec_oracle_to_test_with_verdict(_LLM_TEST, state)
        assert injected is True
        expected_code = compile_spec_oracle(
            parse_logic_analysis(dict(logic)), "mod_add", "add", signature_params=["a", "b"]
        )
        assert merged == f"{_LLM_TEST}\n\n\n{expected_code}"


# ═══ 2. 独立判读：m1_metrics ════════════════════════════════════════════════
class TestM1IndependentJudging:
    """_m1_metrics LLM-suite / oracle-suite 分离执行与字段语义。"""

    def test_oracle_names_match_production_constants(self) -> None:
        from src.graph.nodes import _SPEC_ORACLE_TEST_NAMES

        assert tuple(_SPEC_ORACLE_TEST_NAMES) == m1._ORACLE_SUITE_TEST_NAMES

    def test_has_oracle_suite_markers(self) -> None:
        assert m1.has_oracle_suite(_LLM_TEST + _oracle_block(4)) is True
        assert m1.has_oracle_suite(_LLM_TEST) is False
        assert m1.has_oracle_suite("") is False

    def test_llm_filter_none_without_markers(self) -> None:
        assert m1.llm_suite_keyword_filter(_LLM_TEST) is None
        assert m1.suite_filters(_LLM_TEST) == (None, None)

    def test_suite_filters_with_markers(self) -> None:
        llm_filter, oracle_filter = m1.suite_filters(_LLM_TEST + _oracle_block(4))
        assert llm_filter == m1._LLM_SUITE_KEYWORD_FILTER
        assert oracle_filter == m1._ORACLE_SUITE_KEYWORD_FILTER
        assert "not test_specir_v2_oracle" in str(llm_filter)
        assert "test_specir_v2_smt_witness" in str(oracle_filter)

    def test_run_pytest_no_filter_command_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 keyword_filter 时命令与历史逐位一致（零差异证据）。"""
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="test_x.py::test_a\n", stderr="", timed_out=False)

        monkeypatch.setattr("src.utils.process_utils.run_with_timeout", fake_run)
        result = m1._run_pytest_in_tmp("def test_a():\n    assert True\n", "x = 1\n", "mod_x", timeout=10)
        assert result is not None and result[0] == 0
        pytest_cmds = [cmd for cmd in captured if "-m" in cmd and "pytest" in cmd]
        assert len(pytest_cmds) == 1
        cmd = pytest_cmds[0]
        assert "-k" not in cmd
        # 历史命令骨架锁定（除解释器/测试路径外逐项一致）
        assert cmd[1:7] == ["-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
        assert cmd[-1].endswith("test_mod_x.py")

    def test_run_pytest_adds_k_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="", stderr="", timed_out=False)

        monkeypatch.setattr("src.utils.process_utils.run_with_timeout", fake_run)
        m1._run_pytest_in_tmp(
            "def test_a():\n    assert True\n",
            "x = 1\n",
            "mod_x",
            timeout=10,
            keyword_filter=m1._ORACLE_SUITE_KEYWORD_FILTER,
        )
        pytest_cmds = [cmd for cmd in captured if "-m" in cmd and "pytest" in cmd]
        assert len(pytest_cmds) == 1
        cmd = pytest_cmds[0]
        index = cmd.index("-k")
        assert cmd[index + 1] == m1._ORACLE_SUITE_KEYWORD_FILTER

    def test_detection_rate_switch_off_uses_legacy_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 oracle 测试：detection 走与历史相同的两次运行且不带 -k。"""
        fake, calls = _fake_run_factory(buggy=(1, "", ""), fixed=(0, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        detection = m1._compute_detection_rate(_synthetic_task(), _state_with_generated(_LLM_TEST))
        assert detection == 1.0
        assert len(calls) == 2
        assert all(c["keyword_filter"] is None for c in calls)

    def test_detection_rate_with_oracle_uses_llm_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, calls = _fake_run_factory(buggy=(1, "", ""), fixed=(0, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = _LLM_TEST + _oracle_block(4)
        detection = m1._compute_detection_rate(_synthetic_task(), _state_with_generated(generated))
        assert detection == 1.0
        assert len(calls) == 2
        assert all(c["keyword_filter"] == m1._LLM_SUITE_KEYWORD_FILTER for c in calls)

    def test_detection_rate_ignores_oracle_fixed_failure(self) -> None:
        """核心语义（真实子进程）：oracle 在 fixed 上失败不得改写 LLM-suite 检出。"""
        generated = _LLM_TEST + _oracle_block(3)  # oracle 断言 buggy 行为 → fixed 失败
        detection = m1._compute_detection_rate(_synthetic_task(), _state_with_generated(generated))
        verdict = m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(generated))
        assert detection == 1.0, "LLM 测试是合法 F2P → detection 必须为 1.0（不被 oracle 失败改写）"
        assert verdict == "misguided"

    @pytest.mark.parametrize(
        ("buggy_rc", "fixed_rc", "expected"),
        [
            (1, 0, "correct"),
            (1, 1, "fp"),
            (0, 0, "silent"),
            (0, 1, "misguided"),
        ],
    )
    def test_oracle_suite_verdict_matrix(
        self, monkeypatch: pytest.MonkeyPatch, buggy_rc: int, fixed_rc: int, expected: str
    ) -> None:
        fake, calls = _fake_run_factory(buggy=(buggy_rc, "", ""), fixed=(fixed_rc, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = _LLM_TEST + _oracle_block(4)
        verdict = m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(generated))
        assert verdict == expected
        assert len(calls) == 2
        assert all(c["keyword_filter"] == m1._ORACLE_SUITE_KEYWORD_FILTER for c in calls)

    def test_oracle_suite_unavailable_without_markers_no_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail_if_called(*args, **kwargs):
            raise AssertionError("无 oracle 标记时不得启动 oracle-suite 子进程")

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fail_if_called)
        assert m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(_LLM_TEST)) == "unavailable"

    def test_oracle_suite_unavailable_without_gold_material(self) -> None:
        swe_task = BenchmarkTask(
            task_id="swe__probe",
            repo_name="swe/probe",
            problem_statement="x",
            instance_code=_BUGGY_CODE,
            test_code="",
            expected_pass_count=0,
            total_test_count=0,
            metadata={"source": "swe_bench"},
        )
        generated = _LLM_TEST + _oracle_block(4)
        assert m1._compute_oracle_suite_verdict(swe_task, _state_with_generated(generated)) == "unavailable"

    def test_oracle_suite_unavailable_on_timeout_or_collection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        generated = _LLM_TEST + _oracle_block(4)
        # 超时 → None
        fake, _calls = _fake_run_factory(buggy=None, fixed=(0, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        assert m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(generated)) == "unavailable"
        # 收集错误（rc=2）→ unavailable（不得误判为 fail/fp）
        fake2, _ = _fake_run_factory(buggy=(2, "errors during collection", ""), fixed=(2, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake2)
        assert m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(generated)) == "unavailable"

    def test_test_error_rate_uses_llm_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, calls = _fake_run_factory(buggy=(0, "", ""), fixed=(0, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = _LLM_TEST + _oracle_block(4)
        assert m1._compute_test_error_rate(_synthetic_task(), _state_with_generated(generated)) == 0.0
        assert calls[0]["keyword_filter"] == m1._LLM_SUITE_KEYWORD_FILTER

    def test_build_m1_task_metrics_new_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _calls = _fake_run_factory(buggy=(1, "", ""), fixed=(0, "", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        metrics = m1.build_m1_task_metrics(_synthetic_task(), _state_with_generated(_LLM_TEST))
        assert metrics["detection_rate"] == metrics["llm_suite_detection_rate"] == 1.0
        assert metrics["oracle_suite_verdict"] == "unavailable"
        assert set(m1.ORACLE_SUITE_VERDICTS) >= {metrics["oracle_suite_verdict"]}
        # final_state 缺失 → 新键默认值（键集合同构）
        metrics_none = m1.build_m1_task_metrics(_synthetic_task(), None)
        assert metrics_none["llm_suite_detection_rate"] is None
        assert metrics_none["oracle_suite_verdict"] == "unavailable"

    def test_switch_off_zero_extra_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """默认开关关闭（无 oracle 测试）：oracle 判定零子进程、命令零过滤。"""
        calls: list[dict[str, Any]] = []

        def fake_run(test_code, target_code, module_name, **kwargs):
            calls.append(kwargs)
            return (1, "", "") if target_code == _BUGGY_CODE else (0, "", "")

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake_run)
        detection = m1._compute_detection_rate(_synthetic_task(), _state_with_generated(_LLM_TEST))
        oracle = m1._compute_oracle_suite_verdict(_synthetic_task(), _state_with_generated(_LLM_TEST))
        assert detection == 1.0 and oracle == "unavailable"
        assert len(calls) == 2, "只应有历史两段执行（buggy/fixed），oracle 判定不新增子进程"
        assert all(kwargs.get("keyword_filter") is None for kwargs in calls)


# ═══ 3. run_benchmark 结果行字段 ═══════════════════════════════════════════
class TestRunBenchmarkFields:
    """_build_task_result 成功/失败分支的独立判读字段（键集合同构）。"""

    def test_success_row_has_independent_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rb, "_compute_detection_rate", lambda task, state: 1.0)
        monkeypatch.setattr(rb, "_compute_oracle_suite_verdict", lambda task, state: "correct")
        row = rb._build_task_result(_synthetic_task(), 1.0, final_state=_state_with_generated(_LLM_TEST))
        assert row["detection_rate"] == 1.0
        assert row["llm_suite_detection_rate"] == 1.0
        assert row["oracle_suite_verdict"] == "correct"

    def test_failure_row_has_independent_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = rb._build_task_result(_synthetic_task(), 1.0, diagnosis="boom", error_category="error")
        assert row["detection_rate"] is None
        assert row["llm_suite_detection_rate"] is None
        assert row["oracle_suite_verdict"] == "unavailable"

    def test_success_failure_same_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rb, "_compute_detection_rate", lambda task, state: 0.0)
        monkeypatch.setattr(rb, "_compute_oracle_suite_verdict", lambda task, state: "silent")
        success = rb._build_task_result(_synthetic_task(), 1.0, final_state=_state_with_generated(_LLM_TEST))
        failure = rb._build_task_result(_synthetic_task(), 1.0)
        assert set(success.keys()) == set(failure.keys())
        for key in ("llm_suite_detection_rate", "oracle_suite_verdict"):
            assert key in success and key in failure


# ═══ 4. 独立判读重放模式 ═══════════════════════════════════════════════════
class TestIndependentReplay:
    """oracle_quality_replay --independent-judging 的 state/对账/聚合/CLI。"""

    def test_reconstruct_state_anchor_only_fields(self) -> None:
        anchor = {"function_name": "add", "logic_analysis": dict(_LOGIC_COMPILABLE)}
        state = oq.reconstruct_state_anchor_only("quixbugs__add", {"suggested_function": "add"}, anchor, _BUGGY_CODE)
        assert state["module_name"] == "add"
        assert state["target_function"] == "add"
        assert state["target_code"] == _BUGGY_CODE
        assert state["spec_anchor"] == anchor
        assert "test_plan" not in state and "spec_ir" not in state

    def test_anchor_only_state_injects_via_production(self) -> None:
        """重放模式的 state（anchor-only）经生产注入口应注入（接线修复证据）。"""
        anchor = {"function_name": "add", "logic_analysis": dict(_LOGIC_COMPILABLE)}
        state = oq.reconstruct_state_anchor_only("quixbugs__add", {"suggested_function": "add"}, anchor, _BUGGY_CODE)
        merged, injected, verdict = oq.production_inject_oracle(_LLM_TEST, state)
        assert injected is True and verdict == "injected"
        assert oq.is_oracle_node(merged)

    def test_load_m2_report_fail_closed(self, tmp_path: Path) -> None:
        with pytest.raises(oq.OracleQualityError, match="M-2 基线报告不存在"):
            oq.load_m2_report(tmp_path / "missing.json")
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(oq.OracleQualityError, match="无法解析"):
            oq.load_m2_report(bad)
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"report": {"arms": []}}), encoding="utf-8")
        with pytest.raises(oq.OracleQualityError, match="结构不合法"):
            oq.load_m2_report(empty)

    def _write_m2_and_index(self, tmp_path: Path) -> dict[str, Any]:
        payload = {
            "schema_version": "oracle_quality_metric/1",
            "report": {
                "arms": [
                    {
                        "arm": "plain_llm_df_spec",
                        "tasks": [
                            {
                                "task_id": "quixbugs__add",
                                "status": "ok",
                                "injection": {"verdict": "injected"},
                                "llm_only": {"replay_detection": 1.0},
                                "oracle": {"status": "ok", "counts": {"correct": 1}},
                            }
                        ],
                        "subsets": {
                            "defect_programs": {
                                "detection": {"llm_only_replay": {"n_detected": 1, "n_denominator": 1, "rate": 1.0}},
                                "oracle": {"counts": {"correct": 1}},
                                "injection": {},
                            }
                        },
                    }
                ]
            },
            "run_meta": {"body_digest": "digest-x"},
        }
        path = tmp_path / "m2.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return oq.load_m2_report(path)

    def test_load_m2_report_ok_and_index(self, tmp_path: Path) -> None:
        m2 = self._write_m2_and_index(tmp_path)
        assert m2["body_digest"] == "digest-x"
        arm_index = m2["arm_index"]["plain_llm_df_spec"]
        assert arm_index["tasks"]["quixbugs__add"]["llm_only_replay_detection"] == 1.0
        assert arm_index["tasks"]["quixbugs__add"]["oracle_class"] == "correct"
        assert arm_index["aggregate"]["llm_only_replay_40"]["n_detected"] == 1

    def _fake_task(self, **overrides: Any) -> dict[str, Any]:
        task: dict[str, Any] = {
            "task_id": "quixbugs__add",
            "analysis_set": "defect_program",
            "defect_signal": True,
            "status": "ok",
            "injection": {"verdict": "injected", "injected": True},
            "independent": {
                "status": "ok",
                "llm_suite_detection": 1.0,
                "oracle_suite_verdict": "correct",
                "skip_reason": None,
            },
        }
        task.update(overrides)
        return task

    def test_cross_check_zero_mismatch(self) -> None:
        m2_arm = {
            "tasks": {
                "quixbugs__add": {
                    "llm_only_replay_detection": 1.0,
                    "oracle_class": "correct",
                    "injection_verdict": "injected",
                }
            }
        }
        cross = oq.build_independent_cross_check([self._fake_task()], m2_arm)
        assert cross["all_ok"] is True
        assert cross["detection_vs_m2"]["agreement_counts"]["match"] == 1
        assert cross["oracle_class_vs_m2"]["agreement_counts"]["match"] == 1
        assert cross["injection_vs_m2"]["agreement_counts"]["same_verdict"] == 1

    def test_cross_check_mismatch_attribution(self) -> None:
        m2_arm = {
            "tasks": {
                "quixbugs__add": {
                    "llm_only_replay_detection": 0.0,
                    "oracle_class": "fp",
                    "injection_verdict": "injected",
                }
            }
        }
        cross = oq.build_independent_cross_check([self._fake_task()], m2_arm)
        assert cross["all_ok"] is False
        assert cross["detection_vs_m2"]["n_mismatch"] == 1
        assert cross["detection_vs_m2"]["mismatches"][0]["task_id"] == "quixbugs__add"
        assert cross["oracle_class_vs_m2"]["agreement_counts"]["mismatch"] == 1

    def test_cross_check_missing_m2_task_is_not_ok(self) -> None:
        cross = oq.build_independent_cross_check([self._fake_task(task_id="missing")], {"tasks": {}})
        assert cross["all_ok"] is False
        assert cross["detection_vs_m2"]["agreement_counts"]["m2_task_missing"] == 1

    def test_aggregate_independent_rates(self) -> None:
        tasks = [self._fake_task(), self._fake_task(status="structural_skip", independent={"status": "not_run"})]
        m2_arm = {
            "tasks": {},
            "aggregate": {"llm_only_replay_40": {"n_detected": 1, "n_denominator": 1}},
        }
        aggregate = oq.aggregate_independent(tasks, m2_arm)
        subset = aggregate["subsets"]["defect_programs"]
        assert subset["n_tasks"] == 2
        assert subset["n_tasks_judged"] == 1
        assert subset["llm_suite_detection"] == {"n_detected": 1, "n_denominator": 1, "rate": 1.0}
        assert subset["oracle_suite_counts"]["correct"] == 1
        assert aggregate["m2_rates_match"] is True
        assert aggregate["all_ok"] is False  # 缺 M-2 任务 → cross-check 失败

    def test_aggregate_independent_limited_semantics(self) -> None:
        tasks = [self._fake_task()]
        m2_arm = {
            "tasks": {
                "quixbugs__add": {
                    "llm_only_replay_detection": 1.0,
                    "oracle_class": "correct",
                    "injection_verdict": "injected",
                }
            },
            "aggregate": {"llm_only_replay_40": {"n_detected": 40, "n_denominator": 40}},
        }
        aggregate = oq.aggregate_independent(tasks, m2_arm, limited=True)
        assert aggregate["measurement_limited"] is True
        assert aggregate["m2_rates_match"] is False
        # 截断运行不要求 40 口径计数一致（只要求逐任务 0 mismatch）
        assert aggregate["all_ok"] is True

    def test_judge_task_independent_not_injected(self) -> None:
        record = oq.judge_task_independent(
            task_id="quixbugs__add",
            task_metadata={"source": "quixbugs"},
            buggy_code=_BUGGY_CODE,
            fixed_code=_FIXED_CODE,
            generated_test=_LLM_TEST,
            merged_test=_LLM_TEST,
            injected=False,
            injection_verdict="not_attempted_human_spec_only",
        )
        # 未注入：LLM-suite 照常判读（材料缺 test_cases → None），oracle 不可判
        assert record["status"] == "ok"
        assert record["skip_reason"] == "not_injected"
        assert record["llm_suite_detection"] is None
        assert record["oracle_suite_verdict"] == "unavailable"

    def test_judge_task_independent_uses_production_functions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(oq, "m1_llm_suite_detection", lambda task, state: 1.0)
        monkeypatch.setattr(oq, "m1_oracle_suite_verdict", lambda task, state: "fp")
        merged = _LLM_TEST + _oracle_block(4)
        record = oq.judge_task_independent(
            task_id="quixbugs__add",
            task_metadata={"source": "quixbugs", "test_cases": _GOLD_TEST, "fixed": _FIXED_CODE},
            buggy_code=_BUGGY_CODE,
            fixed_code=_FIXED_CODE,
            generated_test=_LLM_TEST,
            merged_test=merged,
            injected=True,
            injection_verdict="injected",
        )
        assert record["status"] == "ok"
        assert record["llm_suite_detection"] == 1.0
        assert record["oracle_suite_verdict"] == "fp"
        assert record["merged_has_oracle_markers"] is True

    def test_independent_checks_all_ok_summary(self) -> None:
        good = {
            "arm": "a",
            "independent_judging": {
                "all_ok": True,
                "m2_rates_match": True,
                "cross_check_vs_m2": {"detection_vs_m2": {"n_mismatch": 0}},
            },
        }
        ok, failures = oq.independent_checks_all_ok([good])
        assert ok is True and failures == []
        bad = {
            "arm": "b",
            "independent_judging": {
                "all_ok": False,
                "m2_rates_match": False,
                "cross_check_vs_m2": {"detection_vs_m2": {"n_mismatch": 2}},
            },
        }
        ok2, failures2 = oq.independent_checks_all_ok([bad])
        assert ok2 is False and failures2 and "mismatch=2" in failures2[0]

    def test_render_independent_readme_sections(self) -> None:
        report = {
            "inputs": [{"path": "x.json", "sha256": "a" * 64}],
            "anchor_table": {"path": "t.json", "sha256": "b" * 64},
            "independent_judging": {"m2_baseline": {"path": "m2.json", "sha256": "c" * 64}},
            "arms": [
                {
                    "arm": "plain_llm_df_spec",
                    "subsets": {"all_tasks": {"injection": {"n_anchor_hit": 50, "n_injected": 38}}},
                    "independent_judging": {
                        "subsets": {
                            "defect_programs": {
                                "llm_suite_detection": {"n_detected": 20, "n_denominator": 40, "rate": 0.5},
                                "oracle_suite_counts": {
                                    "correct": 0,
                                    "fp": 29,
                                    "silent": 9,
                                    "misguided": 0,
                                    "unavailable": 0,
                                },
                            }
                        },
                        "m2_baseline_40caliber": {"n_detected": 20, "n_denominator": 40, "rate": 0.5},
                        "m2_rates_match": True,
                        "cross_check_vs_m2": {
                            "detection_vs_m2": {"n_mismatch": 0},
                            "oracle_class_vs_m2": {"agreement_counts": {"match": 38}},
                            "injection_vs_m2": {"agreement_counts": {"same_verdict": 49}},
                        },
                        "measurement_limited": False,
                    },
                }
            ],
            "command": ["python", "-m", "experiments.oracle_quality_replay", "--independent-judging"],
            "limitations": ["限制一"],
        }
        run_meta = {
            "body_digest": "d" * 64,
            "tool_wall_s": 12.3,
            "m1_per_test_timeout_s": 1,
            "determinism": {"repeat": 1, "deterministic": True, "body_digests": ["d" * 64]},
        }
        readme = oq.render_independent_readme(report, run_meta)
        assert "独立判读零 LLM 重放验证" in readme
        assert "M-2 40 口径基线" in readme
        assert "50.00%" in readme
        assert "oracle-suite 四分类" in readme
        assert "限制一" in readme
        assert "M1_PER_TEST_TIMEOUT=1" in readme

    def test_main_independent_fail_closed_missing_m2(self, tmp_path: Path) -> None:
        code = oq.main(
            [
                "--independent-judging",
                "--m2-report",
                str(tmp_path / "missing_m2.json"),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        assert code == 2
        assert not (tmp_path / "out" / "ORACLE_INDEPENDENT_JUDGING_REPORT.json").exists()
