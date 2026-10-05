"""P2-4 覆盖率停滞检测回归测试（2026-10 批次）：
workflow._coverage_stall_detected / determine_stop_reason 的 6.5 分支。

锁定口径（与 workflow.py 实现一致）：
- COVERAGE_STALL_DETECT_ENABLE 默认关时恒 False（零行为变化，
  determine_stop_reason 优先级序列与历史完全一致）；
- ON 时：最近 K 轮（COVERAGE_STALL_ROUNDS 默认 2）coverage_delta 全部
  |delta| < eps（COVERAGE_STALL_EPS 默认 0.5）且 test_passed 为假 →
  判停滞 → StopReason.COVERAGE_STALL；
- 保守降级：trace 不足 K 轮 / 任一轮 delta=None / 任一轮 passed=True
  / 非 dict 条目 → 不判停滞。
"""

from __future__ import annotations

import pytest

from src.graph.workflow import (
    StopReason,
    _coverage_stall_detected,
    determine_stop_reason,
)


def _stall_state(iteration: int = 2, deltas: tuple[float | None, ...] = (0.0, 0.2), **overrides) -> dict:
    trace = [{"iteration": i, "passed": False, "coverage": 50.0, "coverage_delta": d} for i, d in enumerate(deltas)]
    state = {"test_passed": False, "iteration": iteration, "max_iterations": 5, "execution_trace": trace}
    state.update(overrides)
    return state


# ── 默认关（零行为变化）─────────────────────────────────────────────────────


def test_stall_off_by_default(monkeypatch):
    monkeypatch.delenv("COVERAGE_STALL_DETECT_ENABLE", raising=False)
    assert _coverage_stall_detected(_stall_state()) is False


def test_stop_reason_off_unchanged_priority(monkeypatch):
    """OFF 时即使 trace 全停滞，determine_stop_reason 仍走历史 6/7 分支
    （iteration 达上限 → MAX_ITERATIONS，不得被 COVERAGE_STALL 抢占）。"""
    monkeypatch.delenv("COVERAGE_STALL_DETECT_ENABLE", raising=False)
    state = _stall_state(iteration=5, deltas=(0.0, 0.2), max_iterations=5)
    state["max_iterations"] = 5
    assert determine_stop_reason(state) == StopReason.MAX_ITERATIONS


# ── ON：判定矩阵 ────────────────────────────────────────────────────────────


@pytest.fixture
def stall_on(monkeypatch):
    monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
    return "on"


def test_stall_detected_two_zero_deltas(stall_on):
    assert _coverage_stall_detected(_stall_state(deltas=(0.0, 0.2))) is True


def test_stall_detected_small_negative_deltas(stall_on):
    # 小幅负增长（|delta| < eps）按绝对值口径也算停滞（覆盖率小幅震荡/连降
    # 均属无效迭代）
    assert _coverage_stall_detected(_stall_state(deltas=(-0.2, -0.3))) is True


def test_stall_not_detected_large_drop(stall_on):
    # delta=-1.0 属"仍在显著变化"（|delta| >= eps=0.5），不判停滞
    assert _coverage_stall_detected(_stall_state(deltas=(-1.0, -0.5))) is False


def test_stall_not_detected_when_growing(stall_on):
    assert _coverage_stall_detected(_stall_state(deltas=(3.0, 0.0))) is False


def test_stall_not_detected_when_test_passed(stall_on):
    assert _coverage_stall_detected(_stall_state(deltas=(0.0, 0.0), test_passed=True)) is False


def test_stall_not_detected_insufficient_trace(stall_on):
    # 默认 K=2，只有 1 轮 trace → 保守不判（信息不足保持 MAX_ITERATIONS 口径）
    assert _coverage_stall_detected(_stall_state(deltas=(0.0,))) is False


def test_stall_not_detected_when_delta_none(stall_on):
    # 首轮 delta=None（无上一轮）→ 保守不判
    assert _coverage_stall_detected(_stall_state(deltas=(None, 0.0))) is False


def test_stall_not_detected_when_entry_not_dict(stall_on):
    state = _stall_state(deltas=(0.0, 0.0))
    state["execution_trace"] = ["not-a-dict", {"passed": False, "coverage_delta": 0.0}]
    assert _coverage_stall_detected(state) is False


def test_stall_stop_reason_on_before_keywords(stall_on):
    state = _stall_state(deltas=(0.0, 0.2), iteration=2, max_iterations=5)
    assert determine_stop_reason(state) == StopReason.COVERAGE_STALL


def test_stall_custom_rounds_and_eps(stall_on, monkeypatch):
    monkeypatch.setenv("COVERAGE_STALL_ROUNDS", "3")
    monkeypatch.setenv("COVERAGE_STALL_EPS", "1.0")
    # 3 轮 delta < 1.0 → 停滞
    assert _coverage_stall_detected(_stall_state(deltas=(0.0, 0.9, 0.5))) is True
    # delta 0.9 < eps 1.0 但 1.0 不 < eps → 不判
    assert _coverage_stall_detected(_stall_state(deltas=(0.0, 1.0, 0.5))) is False
