"""failure_taxonomy 终局失效分类框架测试（U11，2026-10-05 系统性审查落地）。

锁定契约：
1. 全部 StopReason 枚举值 → 预期桶逐一映射（与 workflow.py 对齐）；
2. 优先级：test_passed=True 恒优先；预算/回归状态字段优先于查表；
3. 兜底：状态不足 → UNCATEGORIZED（可度量，不抛异常）；
4. 聚合：占比和为 1、空批安全；渲染含全部桶行；
5. 幂等：同状态重复标注结果一致。
"""

from __future__ import annotations

import pytest

from src.observability.failure_taxonomy import (
    FailureBucket,
    annotate_final_state,
    render_markdown,
    summarize_batch,
)


class TestStopReasonMapping:
    """全部 StopReason 枚举值的桶映射锁定（防 workflow 枚举扩展后漂移）。"""

    @pytest.mark.parametrize(
        ("stop_reason", "expected"),
        [
            ("test_passed", FailureBucket.TASK_COMPLETED),
            ("test_passed_converged", FailureBucket.TASK_COMPLETED),
            ("test_defect_regeneration_cap", FailureBucket.SPECIFICATION_FAILURE),
            ("test_gen_diagnosis", FailureBucket.SPECIFICATION_FAILURE),
            ("test_gen_diagnosis_early", FailureBucket.SPECIFICATION_FAILURE),
            ("max_iterations", FailureBucket.GENERATION_CAPABILITY_FAILURE),
            ("max_iterations_reached", FailureBucket.GENERATION_CAPABILITY_FAILURE),
            ("skip_debugger_repair_invalid", FailureBucket.GENERATION_CAPABILITY_FAILURE),
            ("coverage_stall", FailureBucket.GENERATION_CAPABILITY_FAILURE),
            ("recursion_limit", FailureBucket.GENERATION_CAPABILITY_FAILURE),
            ("budget_exceeded", FailureBucket.VERIFICATION_FAILURE),
            ("regression_detected", FailureBucket.VERIFICATION_FAILURE),
            ("unknown", FailureBucket.UNCATEGORIZED),
        ],
    )
    def test_each_stop_reason_maps_to_expected_bucket(self, stop_reason, expected):
        state = {"test_passed": False, "stop_reason": stop_reason}
        assert annotate_final_state(state)["bucket"] is expected

    def test_mapping_covers_all_workflow_stop_reasons(self):
        """映射表必须覆盖 workflow.StopReason 全部枚举值（新枚举值遗漏会被
        UNCATEGORIZED 兜底吞掉——本用例强制扩展时同步维护映射表）。"""
        from src.graph.workflow import StopReason
        from src.observability.failure_taxonomy import _STOP_REASON_TO_BUCKET

        missing = [reason.value for reason in StopReason if reason.value not in _STOP_REASON_TO_BUCKET]
        assert not missing, f"StopReason 新增枚举值未映射失效桶: {missing}"


class TestPriority:
    def test_passed_overrides_everything(self):
        """test_passed=True 恒为 TASK_COMPLETED（即使 stop_reason 指向失效）。"""
        state = {
            "test_passed": True,
            "stop_reason": "max_iterations",
            "budget_exceeded": True,
        }
        result = annotate_final_state(state)
        assert result["bucket"] is FailureBucket.TASK_COMPLETED
        assert result["stop_reason"] == "max_iterations"

    def test_budget_field_beats_stop_reason(self):
        """budget_exceeded 状态字段优先于 stop_reason 查表。"""
        state = {"test_passed": False, "budget_exceeded": True, "stop_reason": "max_iterations"}
        assert annotate_final_state(state)["bucket"] is FailureBucket.VERIFICATION_FAILURE

    def test_regression_field_beats_stop_reason(self):
        state = {"test_passed": False, "regression_detected": True, "stop_reason": "unknown"}
        assert annotate_final_state(state)["bucket"] is FailureBucket.VERIFICATION_FAILURE

    def test_logic_degraded_weak_signal(self):
        """stop_reason 缺失 + logic_degraded=True → 规约层失效（弱信号）。"""
        state = {"test_passed": False, "logic_degraded": True}
        result = annotate_final_state(state)
        assert result["bucket"] is FailureBucket.SPECIFICATION_FAILURE
        assert "logic_degraded" in result["detail"]

    def test_insufficient_state_falls_back(self):
        """无 stop_reason、无任何信号 → UNCATEGORIZED（兜底不抛异常）。"""
        result = annotate_final_state({})
        assert result["bucket"] is FailureBucket.UNCATEGORIZED
        assert result["stop_reason"] == ""

    def test_empty_state_dict_safe(self):
        """空 dict 与缺失键安全（run_benchmark 行可能缺字段）。"""
        for state in ({}, {"stop_reason": None}, {"test_passed": None}):
            assert "bucket" in annotate_final_state(state)


class TestUnknownStopReasonDoesNotPreemptWeakSignal:
    """I3（2026-10-16）：``stop_reason="unknown"`` 语义是**无信息**，不得抢占
    logic_degraded 弱信号。

    缺陷发现路径：I1 把 annotate_final_state 接进批次落盘时，按 G3 文档口径必须
    经 effective_stop_reason 取终止原因（O35：路由层写入被 LangGraph 丢弃，直读
    恒空）。而 effective_stop_reason 的兜底返回值是 ``"unknown"``——非空字符串，
    于是旧实现 ``if stop_reason:`` 把它当作有信息的归因证据走查表 → UNCATEGORIZED，
    **永远走不到** logic_degraded 弱信号分支：G3 抬升键路径修好了，读侧分支在
    唯一的生产路径上依然不可达。既有单测只构造"stop_reason 缺失"的输入
    （见 TestPriority.test_logic_degraded_weak_signal），因此一直是绿的。
    """

    def test_unknown_with_degraded_hits_specification_failure(self) -> None:
        result = annotate_final_state({"test_passed": False, "stop_reason": "unknown", "logic_degraded": True})
        assert result["bucket"] is FailureBucket.SPECIFICATION_FAILURE
        assert "logic_degraded" in result["detail"]

    def test_unknown_stop_reason_is_preserved_in_annotation(self) -> None:
        """改正不得丢信息：标注里仍带原始 stop_reason（unknown 而非空串）。"""
        result = annotate_final_state({"test_passed": False, "stop_reason": "unknown", "logic_degraded": True})
        assert result["stop_reason"] == "unknown"
        assert "unknown" in result["detail"]

    def test_unknown_without_degraded_still_uncategorized(self) -> None:
        """无弱信号时 unknown 仍进兜底桶（不冒充分类结论，与映射表锁定用例一致）。"""
        for state in (
            {"test_passed": False, "stop_reason": "unknown"},
            {"test_passed": False, "stop_reason": "unknown", "logic_degraded": False},
        ):
            assert annotate_final_state(state)["bucket"] is FailureBucket.UNCATEGORIZED

    def test_informative_stop_reason_still_beats_weak_signal(self) -> None:
        """有信息的 stop_reason 优先于弱信号（弱信号只补"无信息"的空档）。"""
        result = annotate_final_state({"test_passed": False, "stop_reason": "coverage_stall", "logic_degraded": True})
        assert result["bucket"] is FailureBucket.GENERATION_CAPABILITY_FAILURE

    def test_missing_stop_reason_with_degraded_unchanged(self) -> None:
        """既有行为保留：stop_reason 缺失 + 降级 → 规约层失效。"""
        result = annotate_final_state({"test_passed": False, "logic_degraded": True})
        assert result["bucket"] is FailureBucket.SPECIFICATION_FAILURE

    def test_effective_stop_reason_path_reaches_weak_signal(self) -> None:
        """端到端：经 workflow.effective_stop_reason 取终止原因（生产唯一口径）
        后，规约降级任务仍归 SPECIFICATION_FAILURE——这是 I3 真正要保住的路径。"""
        from src.graph.workflow import effective_stop_reason

        state = {"test_passed": False, "logic_degraded": True}
        assert effective_stop_reason(state) == "unknown", "前提失效：兜底不再返回 unknown"
        annotation = annotate_final_state({**state, "stop_reason": effective_stop_reason(state)})
        assert annotation["bucket"] is FailureBucket.SPECIFICATION_FAILURE


class TestSummarizeBatch:
    def test_empty_batch(self):
        summary = summarize_batch([])
        assert summary["total"] == 0
        assert sum(summary["counts"].values()) == 0
        assert all(v == 0.0 for v in summary["shares"].values())

    def test_single_bucket_full_share(self):
        states = [{"test_passed": True}] * 7
        summary = summarize_batch(states)
        assert summary["total"] == 7
        assert summary["shares"]["task_completed"] == 1.0

    def test_multi_bucket_shares_sum_to_one(self):
        states = [
            {"test_passed": True},
            {"test_passed": False, "stop_reason": "max_iterations"},
            {"test_passed": False, "stop_reason": "budget_exceeded"},
            {"test_passed": False, "stop_reason": "test_gen_diagnosis"},
            {},
        ]
        summary = summarize_batch(states)
        assert summary["total"] == 5
        assert abs(sum(summary["shares"].values()) - 1.0) < 1e-6
        assert summary["counts"]["uncategorized"] == 1


class TestRenderMarkdown:
    def test_contains_header_and_all_buckets(self):
        summary = summarize_batch([{"test_passed": True}, {}])
        md = render_markdown(summary)
        assert "## 终局失效分布" in md
        for bucket in FailureBucket:
            assert bucket.value in md
        assert "总计：2 个任务" in md

    def test_custom_title(self):
        md = render_markdown(summarize_batch([]), title="批次 X")
        assert "## 批次 X" in md

    def test_no_denominator_disclosure_when_key_absent(self):
        """I1 向后兼容：summarize_batch 的输出无 unclassified_rows 键（全量分类），
        不得渲染分母披露行——该行只对批次聚合方（run_benchmark
        ._aggregate_failure_buckets，会把无终局状态的行单列）有意义。"""
        md = render_markdown(summarize_batch([{"test_passed": True}]))
        assert "总计：1 个任务" in md
        assert "无工作流终局状态" not in md

    def test_denominator_disclosure_rendered_when_present(self):
        """分母诚实：有未分类行时必须披露，否则报表把批次规模读小。"""
        summary = summarize_batch([{"test_passed": True}, {"test_passed": True}])
        summary["total_rows"] = 5
        summary["unclassified_rows"] = 3
        md = render_markdown(summary)
        assert "总计：2 个任务" in md
        assert "另有 3 个任务无工作流终局状态" in md
        assert "批次共 5 行" in md


class TestIdempotency:
    def test_repeated_annotation_is_stable(self):
        state = {"test_passed": False, "stop_reason": "coverage_stall", "logic_degraded": True}
        first = annotate_final_state(state)
        second = annotate_final_state(state)
        assert first == second

    def test_input_not_mutated(self):
        state = {"test_passed": False, "stop_reason": "max_iterations"}
        snapshot = dict(state)
        annotate_final_state(state)
        assert state == snapshot
