"""P-2（A-19 wiring 修复，2026-10-18）：覆盖率停滞检测短路消费回归测试。

背景（本批修复的缺陷）：修复前 `_coverage_stall_detected` 只被
`determine_stop_reason` 调用，`_should_debug` / `_route_after_diagnosis`
**不消费**该判定（无短路段），且 `determine_stop_reason` 的停滞分支位于
MAX_ITERATIONS 之后 → COVERAGE_STALL 标签在自然终止时被遮蔽、提前停止
从不发生（"纸面功能"）。本文件锁定修复后的短路语义与 OFF 零行为变化。

测试口径：
- ON（COVERAGE_STALL_DETECT_ENABLE=true）：停滞状态在进入 debugger 前
  短路为 "done"，`state["stop_reason"]="coverage_stall"`；
- OFF（false）：逐位保持历史行为（"debug" / max_iterations / repair_invalid 等）；
- 优先级：test_passed/budget/regression/test_defect-regen-cap 不被抢占；
  stall 分支移到 MAX_ITERATIONS 之前（ON 时自然终止标签为 coverage_stall）；
- 全部为纯函数/图装配零 LLM 测试。
"""

from __future__ import annotations

import pytest

from src.graph.state import create_initial_state
from src.graph.workflow import (
    _MAX_REGENERATIONS,
    StopReason,
    _coverage_stall_detected,
    _route_after_diagnosis,
    _should_debug,
    build_workflow,
    determine_stop_reason,
    effective_stop_reason,
)

ON_ENV = "COVERAGE_STALL_DETECT_ENABLE"


def _state(**overrides):
    """构造最小 AITesterState（max_iterations=3；可覆盖任意键）。"""
    state = create_initial_state(
        task_uuid="test_stall_task",
        target_file="/tmp/test_stall_module.py",
        target_function="f",
        module_name="test_stall_module",
        target_code="def f():\n    return 1\n",
        max_iterations=3,
    )
    state.update(overrides)
    return state


def _stalled_trace(rounds: int = 2, delta: float = 0.0):
    """构造最近 K 轮"失败且覆盖率 delta≈0"的 execution_trace。"""
    return [{"passed": False, "coverage_delta": delta} for _ in range(rounds)]


@pytest.fixture()
def stall_on(monkeypatch):
    monkeypatch.setenv(ON_ENV, "true")
    return True


@pytest.fixture()
def stall_off(monkeypatch):
    monkeypatch.setenv(ON_ENV, "false")
    return False


# ── 1) ON：_should_debug 短路为 done + 标签 ─────────────────────────────────
class TestShouldDebugShortCircuit:
    def test_stalled_on_short_circuits_to_done(self, stall_on):
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False)
        assert _coverage_stall_detected(state) is True
        assert _should_debug(state) == "done"
        assert state["stop_reason"] == StopReason.COVERAGE_STALL.value

    def test_stalled_on_at_iteration_one_with_enough_trace(self, stall_on):
        # 迭代计数与 trace 轮数独立：只要有 K 轮停滞且未通过，即短路
        state = _state(iteration=1, execution_trace=_stalled_trace(2), test_passed=False)
        assert _should_debug(state) == "done"
        assert state["stop_reason"] == StopReason.COVERAGE_STALL.value

    def test_off_returns_debug_zero_behavior(self, stall_off):
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False)
        assert _coverage_stall_detected(state) is False
        assert _should_debug(state) == "debug"
        assert state.get("stop_reason") is None  # 历史：路由 debug 不写标签

    def test_not_stalled_on_returns_debug(self, stall_on):
        # 覆盖率仍有显著变化（|delta| >= eps）→ 不判停滞 → 继续修复
        state = _state(iteration=2, execution_trace=_stalled_trace(2, delta=5.0), test_passed=False)
        assert _should_debug(state) == "debug"

    def test_insufficient_rounds_on_returns_debug(self, stall_on):
        state = _state(iteration=1, execution_trace=_stalled_trace(1), test_passed=False)
        assert _should_debug(state) == "debug"

    def test_passed_round_blocks_stall(self, stall_on):
        trace = [{"passed": False, "coverage_delta": 0.0}, {"passed": True, "coverage_delta": 0.0}]
        state = _state(iteration=2, execution_trace=trace, test_passed=False)
        assert _should_debug(state) == "debug"

    def test_test_passed_priority_not_preempted(self, stall_on):
        # test_passed=True 分支在短路段之前：即使停滞也不改写 test_passed 语义
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=True)
        assert _should_debug(state) == "done"
        assert state["stop_reason"] == StopReason.TEST_PASSED.value

    def test_negative_control_deleted_short_circuit_is_old_behavior(self, monkeypatch):
        # 删短路负控：停滞判定 True 但开关派生判定 False（模拟未接线）→ 仍 debug
        monkeypatch.setenv(ON_ENV, "true")
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False)
        monkeypatch.setattr("src.graph.workflow._coverage_stall_enabled", lambda: False)
        assert _should_debug(state) == "debug"
        assert state.get("stop_reason") is None

    def test_negative_control_detector_false_keeps_debug(self, monkeypatch):
        # 开关 ON 但未停滞（检测器 False）→ 不得提前停止
        monkeypatch.setenv(ON_ENV, "true")
        state = _state(iteration=2, execution_trace=_stalled_trace(2, delta=9.0), test_passed=False)
        assert _should_debug(state) == "debug"


# ── 2) 标签优先级（determine_stop_reason） ──────────────────────────────────
class TestStopReasonPriority:
    def test_stalled_on_iter_below_max_labels_coverage_stall(self, stall_on):
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False)
        assert determine_stop_reason(state) is StopReason.COVERAGE_STALL

    def test_at_max_stalled_on_labels_coverage_stall(self, stall_on):
        # 修复点：停滞分支移至 MAX_ITERATIONS 之前 → ON 时自然终止标签不再被遮蔽
        state = _state(iteration=3, execution_trace=_stalled_trace(2), test_passed=False)
        assert determine_stop_reason(state) is StopReason.COVERAGE_STALL
        assert _should_debug(state) == "done"
        assert state["stop_reason"] == StopReason.COVERAGE_STALL.value
        assert effective_stop_reason(state) == StopReason.COVERAGE_STALL.value

    def test_at_max_stalled_off_labels_max_iterations(self, stall_off):
        state = _state(iteration=3, execution_trace=_stalled_trace(2), test_passed=False)
        assert determine_stop_reason(state) is StopReason.MAX_ITERATIONS
        assert _should_debug(state) == "done"
        assert state["stop_reason"] == StopReason.MAX_ITERATIONS.value

    def test_budget_exceeded_not_preempted(self, stall_on):
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False, budget_exceeded=True)
        assert determine_stop_reason(state) is StopReason.BUDGET_EXCEEDED

    def test_regression_detected_not_preempted(self, stall_on):
        state = _state(iteration=2, execution_trace=_stalled_trace(2), test_passed=False, regression_detected=True)
        assert determine_stop_reason(state) is StopReason.REGRESSION_DETECTED

    def test_test_defect_regen_cap_not_preempted(self, stall_on):
        state = _state(
            iteration=2,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            defect_type="test_defect",
            regeneration_count=_MAX_REGENERATIONS,
        )
        assert determine_stop_reason(state) is StopReason.TEST_DEFECT_REGEN_CAP

    def test_stall_before_repair_invalid_when_on(self, stall_on):
        # 修复后顺序：stall(5) 在 repair_invalid(7) 之前
        state = _state(
            iteration=2,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert determine_stop_reason(state) is StopReason.COVERAGE_STALL

    def test_repair_invalid_unchanged_when_off(self, stall_off):
        state = _state(
            iteration=2,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert determine_stop_reason(state) is StopReason.REPAIR_INVALID

    def test_stall_before_keyword_early_when_on(self, stall_on):
        state = _state(
            iteration=2,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            diagnosis="测试生成错误：期望的异常类型不匹配（test code 断言错误）",
        )
        assert determine_stop_reason(state) is StopReason.COVERAGE_STALL

    def test_keyword_early_unchanged_when_off(self, stall_off):
        state = _state(
            iteration=2,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            diagnosis="测试生成错误：期望的异常类型不匹配（test code 断言错误）",
        )
        assert determine_stop_reason(state) is StopReason.TEST_GEN_KEYWORD_EARLY


# ── 3) 诊断路由对称短路 ─────────────────────────────────────────────────────
class TestRouteAfterDiagnosisShortCircuit:
    def test_stalled_on_routes_done(self, stall_on):
        state = _state(
            iteration=1,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            defect_type="implementation_defect",
        )
        assert _route_after_diagnosis(state) == "done"
        assert state["stop_reason"] == StopReason.COVERAGE_STALL.value

    def test_stalled_off_routes_debug(self, stall_off):
        state = _state(
            iteration=1,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            defect_type="implementation_defect",
        )
        assert _route_after_diagnosis(state) == "debug"
        assert state.get("stop_reason") is None

    def test_test_defect_regenerate_not_preempted(self, stall_on):
        # test_defect + 未达再生成上限 → regenerate（优先于停滞短路）
        state = _state(
            iteration=1,
            execution_trace=_stalled_trace(2),
            test_passed=False,
            defect_type="test_defect",
            regeneration_count=0,
        )
        assert _route_after_diagnosis(state) == "regenerate"

    def test_at_max_passed_done_keeps_passed_label(self, stall_on):
        state = _state(
            iteration=3,
            execution_trace=_stalled_trace(2),
            test_passed=True,
            defect_type="implementation_defect",
        )
        assert _route_after_diagnosis(state) == "done"
        assert state["stop_reason"] == StopReason.TEST_PASSED.value


# ── 4) 图装配 smoke（ON/OFF 均可编译，路由函数已注册） ─────────────────────
class TestGraphAssembly:
    @pytest.mark.parametrize("value", ["true", "false"])
    def test_build_workflow_compiles_both_arms(self, monkeypatch, value):
        monkeypatch.setenv(ON_ENV, value)
        graph = build_workflow()
        assert hasattr(graph, "invoke")

    def test_short_circuit_functions_exist(self):
        # 回归锁：短路消费点必须存在于两个路由函数中（本修复的核心契约）
        import inspect

        from src.graph import workflow as wf

        src = inspect.getsource(wf._should_debug)
        assert "_coverage_stall_enabled() and _coverage_stall_detected(state)" in src
        src2 = inspect.getsource(wf._route_after_diagnosis)
        assert "_coverage_stall_enabled() and _coverage_stall_detected(state)" in src2
