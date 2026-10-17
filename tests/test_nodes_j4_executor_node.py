"""J-4（2026-10-17）：`_executor_node` 观测/门控分支补测。

纪律：零 LLM、零真实执行——`ExecutorAgent` 整类被 mock，沙箱不启动；
所有门（flaky / 特异性 / 红回归 / 分支覆盖率 / 探针）的产物用 monkeypatch
替换成确定性返回值。

判别性口径：每条"开关开启"都配"开关关闭"对照（开关判定写反时，开启态用例
本身发现不了）；conftest 的 `_isolate_profile_presets` 已记录本块历史上因
档位泄漏导致的覆盖率非确定（漂移行正落在特异性门内），故这里显式钉住开关。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.graph import nodes as nodes_mod

_TARGET_CODE = "def rank_items(items):\n    if len(items) > 2:\n        return sorted(items)\n    return list(items)\n"
_PASS_RESULT = {"passed": True, "output": "1 passed", "coverage": 100.0, "failed_cases": []}
_FAIL_RESULT = {
    "passed": False,
    "output": "1 failed",
    "coverage": 40.0,
    "failed_cases": [{"name": "test_rank_items"}],
}


def _state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "target_file": "/tmp/does_not_exist_j4.py",
        "module_name": "target_mod",
        "target_code": _TARGET_CODE,
        "target_function": "rank_items",
        "generated_test": "def test_rank_items():\n    assert rank_items([3,1,2]) == [1,2,3]\n",
        "iteration": 0,
        "max_iterations": 3,
    }
    state.update(extra)
    return state


def _run_executor(
    monkeypatch: pytest.MonkeyPatch, state: dict[str, Any], result: dict[str, Any] | None = None, **env: str
) -> dict[str, Any]:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    fake_agent = MagicMock()
    fake_agent.execute.return_value = dict(result or _PASS_RESULT)
    with (
        patch.object(nodes_mod, "ExecutorAgent", return_value=fake_agent),
        patch.object(nodes_mod, "_trace_node"),
        patch.object(nodes_mod, "publish_tests_executed"),
    ):
        return nodes_mod._executor_node(state)  # type: ignore[arg-type]


def rag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式关 RAG：非 RAG 用例不该被检索入库路径干扰（普通 helper，非 fixture）。"""
    monkeypatch.setattr(nodes_mod, "ENABLE_RAG", False)


@pytest.mark.unit
class TestRagIngestAndRepairGate:
    """C10 验证门：通过的补丁才进修复案例库，入库后消费暂存。"""

    def _enable_rag(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        retriever = MagicMock()
        monkeypatch.setattr(nodes_mod, "ENABLE_RAG", True)
        monkeypatch.setattr(nodes_mod, "RAG_MODULE_AVAILABLE", True)
        monkeypatch.setattr(nodes_mod, "TestCaseRetriever", object)
        monkeypatch.setattr(nodes_mod, "get_rag_retriever", lambda: retriever)
        return retriever

    def test_pass_ingests_case_and_repair_then_consumes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        retriever = self._enable_rag(monkeypatch)
        state = _state(
            last_applied_repair={"patch": "--- a\n+++ b\n", "original_code": _TARGET_CODE, "error_category": "RUNTIME"}
        )
        update = _run_executor(monkeypatch, state, _PASS_RESULT)
        assert retriever.add_case.call_count == 1
        assert retriever.add_case.call_args.kwargs["passed"] is True
        assert retriever.add_repair.call_args.kwargs["patch"] == "--- a\n+++ b\n"
        assert update["last_applied_repair"] is None  # 入库后消费，防下一轮重复入库

    def test_fail_discards_pending_repair_without_ingest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """失败轮：补丁未通过验证 → 不入库、直接丢弃暂存（防污染案例库）。"""
        retriever = self._enable_rag(monkeypatch)
        state = _state(last_applied_repair={"patch": "bad", "original_code": _TARGET_CODE})
        update = _run_executor(monkeypatch, state, _FAIL_RESULT)
        assert retriever.add_repair.call_count == 0
        assert retriever.add_case.call_count == 0
        assert update["last_applied_repair"] is None

    def test_pass_without_pending_repair_skips_add_repair(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：全过但无暂存补丁（首轮）→ 只入库用例，不入库修复案例。"""
        retriever = self._enable_rag(monkeypatch)
        _run_executor(monkeypatch, _state(), _PASS_RESULT)
        assert retriever.add_case.call_count == 1
        assert retriever.add_repair.call_count == 0


@pytest.mark.unit
class TestTraceAndStrategy:
    """3.2 轨迹：上一轮覆盖率 → coverage_delta → 迭代策略建议。"""

    def test_prev_coverage_from_history_produces_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        state = _state(
            execution_trace=[
                {"passed": False, "coverage": 60.0, "coverage_delta": -10.0, "iteration": 0},
                {"passed": False, "coverage": 50.0, "coverage_delta": -10.0, "iteration": 1},
            ]
        )
        update = _run_executor(
            monkeypatch, state, {"passed": False, "output": "x", "coverage": 40.0, "failed_cases": []}
        )
        assert len(update["execution_trace"]) == 3  # 历史 2 条 + 本轮 1 条
        # 上一轮覆盖率 50 → 本轮 40：连降两轮 → 建议降温度（prev_coverage 读取腿的证据）
        assert update["execution_trace"][-1]["coverage_delta"] == -10.0
        assert update["iteration_strategy_suggestion"] == "lower_temperature"

    def test_first_round_has_no_prev_coverage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT)
        assert len(update["execution_trace"]) == 1


@pytest.mark.unit
class TestRogueMonitorLeg:
    """R16：findings 非空才写键（默认关时零开销）。"""

    def test_findings_written_for_all_four_agents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        monitor = MagicMock()
        monitor.check.return_value = [SimpleNamespace(agent_id="X", kind="frequency", detail="z=3.1", metric=3.1)]
        monkeypatch.setattr("src.agents.rogue_monitor.get_rogue_monitor", lambda: monitor)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, ROGUE_MONITOR_ENABLE="true")
        assert len(monitor.check.call_args_list) == 4  # Planner/Generator/Executor/Debugger
        assert len(update["rogue_findings"]) == 4
        assert {f["kind"] for f in update["rogue_findings"]} == {"frequency"}

    def test_clean_monitor_writes_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        monitor = MagicMock()
        monitor.check.return_value = []
        monkeypatch.setattr("src.agents.rogue_monitor.get_rogue_monitor", lambda: monitor)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, ROGUE_MONITOR_ENABLE="true")
        assert "rogue_findings" not in update

    def test_switch_off_does_not_touch_monitor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：默认关 → 连监控实例都不取（零开销承诺）。"""
        rag_off(monkeypatch)
        get = MagicMock()
        monkeypatch.setattr("src.agents.rogue_monitor.get_rogue_monitor", get)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT)
        assert get.call_count == 0
        assert "rogue_findings" not in update


@pytest.mark.unit
class TestFlakyGateLeg:
    """R35/R31：仅失败轮重跑；flaky 轮保守记 False。"""

    def _patch_detect(self, monkeypatch: pytest.MonkeyPatch, verdict: dict[str, Any]) -> MagicMock:
        spy = MagicMock(return_value=verdict)
        monkeypatch.setattr("src.agents.flaky_gate.detect_flaky", spy)
        return spy

    def test_flaky_round_forces_fail_and_marks_unverified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        spy = self._patch_detect(monkeypatch, {"flaky": True, "pass_count": 2, "total": 3, "fail_count": 1})
        update = _run_executor(monkeypatch, _state(), _FAIL_RESULT, FLAKY_CHECK_ENABLE="true")
        assert spy.call_args.kwargs["base_result"]["passed"] is False
        assert update["test_passed"] is False and update["flaky_unverified"] is True
        assert update["flaky_pass_count"] == 2 and update["flaky_total_count"] == 3

    def test_stable_failure_keeps_result_and_marks_verified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        self._patch_detect(monkeypatch, {"flaky": False, "pass_count": 0, "total": 3, "fail_count": 3})
        update = _run_executor(monkeypatch, _state(), _FAIL_RESULT, FLAKY_CHECK_ENABLE="true")
        assert update["flaky_unverified"] is False
        assert update["test_passed"] is False

    def test_green_round_skips_flaky_rerun(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：全绿即稳定，不重跑（省 subprocess，也防把 passed 改坏）。"""
        rag_off(monkeypatch)
        spy = self._patch_detect(monkeypatch, {"flaky": True, "pass_count": 3, "total": 3, "fail_count": 0})
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, FLAKY_CHECK_ENABLE="true")
        assert spy.call_count == 0
        assert "flaky_detected" not in update
        assert update["test_passed"] is True


@pytest.mark.unit
class TestDetectionFirstAndGates:
    """W3 检出优先 + AC2 双门（特异性门 / 红回归门）。"""

    def test_first_round_red_stores_red_witness(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        update = _run_executor(monkeypatch, _state(), _FAIL_RESULT, DETECTION_FIRST_ENABLE="true")
        assert update["detection_first_red_seen"] is True
        assert update["red_witness_test_code"] == _state()["generated_test"]

    def test_over_red_verdict_suppresses_witness(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """过红（gold fixed 上也红）不是"红证人"——不能存下来当修复循环依据。"""
        rag_off(monkeypatch)
        monkeypatch.setattr("src.tools.detection_gates.specificity_verdict", lambda *a, **k: "over_red")
        update = _run_executor(
            monkeypatch,
            _state(gold_fixed_code="def rank_items(items):\n    return list(items)\n"),
            _FAIL_RESULT,
            DETECTION_FIRST_ENABLE="true",
            DETECTION_SPECIFICITY_GATE_ENABLE="true",
        )
        assert update["specificity_gate_verdict"] == "over_red"
        assert "red_witness_test_code" not in update

    def test_cross_file_metadata_is_passed_to_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """P0-1：cross_file_deps 非空 → 门收到 {"is_cross_file": True, target_module}。"""
        rag_off(monkeypatch)
        captured: dict[str, Any] = {}

        def _spy(_test, _gold, _module, task_metadata=None):
            captured["meta"] = task_metadata
            return "specific_red"

        monkeypatch.setattr("src.tools.detection_gates.specificity_verdict", _spy)
        update = _run_executor(
            monkeypatch,
            _state(cross_file_deps=[{"target_module": "helpers"}]),
            _FAIL_RESULT,
            DETECTION_FIRST_ENABLE="true",
            DETECTION_SPECIFICITY_GATE_ENABLE="true",
        )
        assert captured["meta"] == {"is_cross_file": True, "target_module": "target_mod"}
        assert update["red_witness_test_code"]

    def test_single_file_task_passes_none_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：无 cross_file_deps → task_metadata=None（委托层走单文件口径）。"""
        rag_off(monkeypatch)
        captured: dict[str, Any] = {}

        def _spy(_test, _gold, _module, task_metadata=None):
            captured["meta"] = task_metadata
            return "unavailable"

        monkeypatch.setattr("src.tools.detection_gates.specificity_verdict", _spy)
        _run_executor(
            monkeypatch, _state(), _FAIL_RESULT, DETECTION_FIRST_ENABLE="true", DETECTION_SPECIFICITY_GATE_ENABLE="true"
        )
        assert captured["meta"] is None

    def test_cross_file_metadata_without_module_name_omits_target_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """nodes.py:1601 的 False 腿：跨文件但 module_name 空 → 只带 is_cross_file。

        `target_module` 缺失时委托层无法物化伴生模块，回退单文件口径——键
        缺席本身就是要锁的口径（写 `""` 会让下游误以为拿到了模块名）。
        """
        rag_off(monkeypatch)
        captured: dict[str, Any] = {}

        def _spy(_test, _gold, _module, task_metadata=None):
            captured["meta"] = task_metadata
            return "specific_red"

        monkeypatch.setattr("src.tools.detection_gates.specificity_verdict", _spy)
        _run_executor(
            monkeypatch,
            _state(module_name="", cross_file_deps=[{"target_module": "helpers"}]),
            _FAIL_RESULT,
            DETECTION_FIRST_ENABLE="true",
            DETECTION_SPECIFICITY_GATE_ENABLE="true",
        )
        assert captured["meta"] == {"is_cross_file": True}

    def test_red_regression_gate_without_red_seen_keeps_weak_pass_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """门②恢复红证人，但本任务"从未见过红"→ 三值推导 None → 沿用弱通过标注。

        （nodes.py:1621 的 None 腿）非首轮（iteration!=0）时 red_seen 是粘性
        信号、本轮不重推，故 1566 先写 all_green_unverified；门②把 test_passed
        保守改回 False 后，若无"曾见红"证据**不得**把它改写成 red_not_repaired
        ——那是"有效检出"信号，凭空写会让评估层把一次假绿计成一次成功检出。
        与 ..._rederives_status（red_seen=True → red_not_repaired）成对，
        判别性来自 red_seen 输入而非 mock 形状。
        """
        rag_off(monkeypatch)
        monkeypatch.setattr(
            "src.tools.detection_gates.red_regression_check",
            lambda state, _test: {"test_passed": False, "red_witness_restored": True},
        )
        update = _run_executor(
            monkeypatch,
            _state(iteration=1, regeneration_count=1),
            _PASS_RESULT,
            DETECTION_FIRST_ENABLE="true",
        )
        assert update["red_witness_restored"] is True
        assert update["test_passed"] is False
        assert update["detection_first_status"] == "all_green_unverified"

    def test_red_regression_gate_restores_witness_and_rederives_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        monkeypatch.setattr(
            "src.tools.detection_gates.red_regression_check",
            lambda state, _test: {"test_passed": False, "red_witness_restored": True},
        )
        update = _run_executor(
            monkeypatch,
            _state(detection_first_red_seen=True, regeneration_count=1),
            _PASS_RESULT,
            DETECTION_FIRST_ENABLE="true",
        )
        assert update["red_witness_restored"] is True
        assert update["test_passed"] is False  # 门②把假成功改回失败
        assert update["detection_first_status"] == "red_not_repaired"

    def test_gate_off_writes_no_detection_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：默认关 → update 键集合与历史同构（零行为变化）。"""
        rag_off(monkeypatch)
        update = _run_executor(monkeypatch, _state(), _FAIL_RESULT)
        assert not {"detection_first_red_seen", "red_witness_test_code"} & set(update)


@pytest.mark.unit
class TestBranchCoverageMeasureLeg:
    """O3 测量侧：测得才写键，测不到不写（不写 None 伪装成功）。"""

    def test_measurement_written(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        payload = {"branch_coverage": 50.0, "missing_branches": [{"line": 2, "to": 3}]}
        monkeypatch.setattr("src.tools.branch_coverage_inject.measure_branch_coverage", lambda **kw: payload)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, BRANCH_COVERAGE_INJECT_ENABLE="true")
        assert update["branch_coverage"] == payload

    def test_measurement_failure_writes_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        monkeypatch.setattr("src.tools.branch_coverage_inject.measure_branch_coverage", lambda **kw: None)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, BRANCH_COVERAGE_INJECT_ENABLE="true")
        assert "branch_coverage" not in update

    def test_docker_leg_skips_measurement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """O16 缺口口径：Docker 链路不测（容器内 JSON 回传未实现），开关开着也不跑。"""
        rag_off(monkeypatch)
        spy = MagicMock()
        monkeypatch.setattr("src.tools.branch_coverage_inject.measure_branch_coverage", spy)
        monkeypatch.setattr(nodes_mod, "EXECUTOR_USE_DOCKER", True)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT, BRANCH_COVERAGE_INJECT_ENABLE="true")
        assert spy.call_count == 0
        assert "branch_coverage" not in update


@pytest.mark.unit
class TestM6RollbackLeg:
    """失败轮坏补丁回滚：磁盘恢复后 state 必须同事务跟随（C6）。"""

    def test_rollback_restores_target_code_and_clears_snapshot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)

        def _fake_rollback(state, restored_out=None):
            if restored_out is not None:
                restored_out["content"] = _TARGET_CODE
            return True

        monkeypatch.setattr(nodes_mod, "_rollback_last_patch", _fake_rollback)
        update = _run_executor(monkeypatch, _state(_last_patch_snapshot={"content": _TARGET_CODE}), _FAIL_RESULT)
        assert update["last_patch_rolled_back"] is True
        assert update["target_code"] == _TARGET_CODE
        assert update["_last_patch_snapshot"] is None and update["_last_patch_iteration"] is None

    def test_rollback_without_restored_content_leaves_target_code_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """快照恢复成功但出参未带原文（nodes.py:1661 的 False 腿）→ 不写 target_code。

        这是 `_rollback_last_patch` 的降级口径（快照存在但读不出内容）：此时
        宁可 state 仍是补丁码，也不能凭空造一个"已恢复"的 target_code 键。
        """
        rag_off(monkeypatch)
        monkeypatch.setattr(nodes_mod, "_rollback_last_patch", lambda state, restored_out=None: True)
        update = _run_executor(monkeypatch, _state(_last_patch_snapshot={"content": _TARGET_CODE}), _FAIL_RESULT)
        assert update["last_patch_rolled_back"] is True
        assert "target_code" not in update

    def test_rollback_skipped_on_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        spy = MagicMock(return_value=False)
        monkeypatch.setattr(nodes_mod, "_rollback_last_patch", spy)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT)
        assert spy.call_count == 0
        assert "last_patch_rolled_back" not in update


@pytest.mark.unit
class TestRegenerationObservation:
    """M5：再生成后全绿 ≠ 缺陷被处理。"""

    def test_regenerated_pass_is_flagged_unverified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        update = _run_executor(monkeypatch, _state(regeneration_count=1), _PASS_RESULT)
        assert update["test_regenerated_pass_unverified"] is True

    def test_first_round_pass_not_flagged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rag_off(monkeypatch)
        update = _run_executor(monkeypatch, _state(), _PASS_RESULT)
        assert "test_regenerated_pass_unverified" not in update
