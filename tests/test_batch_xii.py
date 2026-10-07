"""修复引擎批次 XII（2026-10-07）：交互中心失败归因测试锁（ADR-0026）。

锁定三组行为：
1. interaction_attribution 映射（交互边 × 故障侧——编排上界归
   harness 侧、规约失效归 model 侧、验证门拦截归 harness 侧）；
2. annotate_final_state 向后兼容（增补 edge/fault_side 键，既有
   bucket/stop_reason/detail 三键语义零变化）；
3. summarize_batch / render_markdown 的交互视角聚合与渲染。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability.failure_taxonomy import (
    FAULT_SIDES,
    INTERACTION_EDGES,
    FailureBucket,
    annotate_final_state,
    interaction_attribution,
    render_markdown,
    summarize_batch,
)


class TestInteractionAttribution:
    def test_recursion_limit_is_harness_side(self) -> None:
        r = interaction_attribution({"test_passed": False, "stop_reason": "recursion_limit"})
        assert r == {"edge": "harness", "fault_side": "harness_side"}

    def test_budget_exceeded_is_harness_side(self) -> None:
        r = interaction_attribution({"test_passed": False, "budget_exceeded": True})
        assert r == {"edge": "harness", "fault_side": "harness_side"}

    def test_spec_failure_is_model_side(self) -> None:
        r = interaction_attribution({"test_passed": False, "stop_reason": "test_gen_diagnosis"})
        assert r == {"edge": "planner_to_generator", "fault_side": "model_side"}

    def test_generation_failure_is_model_side(self) -> None:
        r = interaction_attribution({"test_passed": False, "stop_reason": "max_iterations"})
        assert r == {"edge": "debugger_to_executor", "fault_side": "model_side"}

    def test_regression_gate_is_harness_side(self) -> None:
        # 验证门拦截 ≠ 补丁质量差：门组件属 harness
        r = interaction_attribution({"test_passed": False, "regression_detected": True})
        assert r == {"edge": "debugger_to_executor", "fault_side": "harness_side"}

    def test_completed_task_no_attribution_claim(self) -> None:
        r = interaction_attribution({"test_passed": True, "stop_reason": "test_passed"})
        assert r["fault_side"] == "uncategorized"

    def test_missing_stop_reason_uncategorized(self) -> None:
        r = interaction_attribution({"test_passed": False})
        assert r == {"edge": "uncategorized", "fault_side": "uncategorized"}

    def test_domain_values_contract(self) -> None:
        # 取值域锁（防漂移）
        assert set(FAULT_SIDES) == {"model_side", "harness_side", "environment", "grader", "uncategorized"}
        assert "debugger_to_executor" in INTERACTION_EDGES


class TestAnnotateBackwardCompat:
    def test_legacy_keys_unchanged(self) -> None:
        a = annotate_final_state({"test_passed": False, "stop_reason": "max_iterations"})
        assert a["bucket"] == FailureBucket.GENERATION_CAPABILITY_FAILURE
        assert a["stop_reason"] == "max_iterations"
        assert "detail" in a

    def test_new_keys_present_all_branches(self) -> None:
        for state in (
            {"test_passed": True},
            {"test_passed": False, "budget_exceeded": True},
            {"test_passed": False, "regression_detected": True},
            {"test_passed": False, "stop_reason": "unknown"},
            {"test_passed": False},
        ):
            a = annotate_final_state(state)
            assert "edge" in a and "fault_side" in a
            assert a["edge"] in INTERACTION_EDGES
            assert a["fault_side"] in FAULT_SIDES


class TestSummarizeAndRender:
    def test_fault_side_aggregation(self) -> None:
        states = [
            {"test_passed": False, "stop_reason": "max_iterations"},
            {"test_passed": False, "stop_reason": "recursion_limit"},
            {"test_passed": True},
        ]
        s = summarize_batch(states)
        assert s["total"] == 3
        assert s["fault_side_counts"]["model_side"] == 1
        assert s["fault_side_counts"]["harness_side"] == 1
        assert s["fault_side_counts"]["uncategorized"] == 1  # 收敛行
        assert s["edge_counts"]["debugger_to_executor"] == 1
        assert s["edge_counts"]["harness"] == 2

    def test_empty_batch_zeroes(self) -> None:
        s = summarize_batch([])
        assert s["total"] == 0
        assert all(v == 0 for v in s["fault_side_counts"].values())

    def test_render_includes_attribution_table(self) -> None:
        s = summarize_batch([{"test_passed": False, "stop_reason": "max_iterations"}])
        md = render_markdown(s)
        assert "交互中心归因" in md
        assert "model_side" in md
        assert "debugger_to_executor" in md
        assert "prompt/后训练/生成质量" in md


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
