"""
5.2 新增错误分类类别单元测试。

覆盖：
- refine_failure_category 的 EXECUTION_TRACE_MISSING（执行轨迹丢失）；
- refine_failure_category 的 MULTI_CANDIDATE_ALL_REJECTED（多候选全拒绝）；
- 优先级判定（patch_rejected > rag_empty > trace_missing > multi_rejected）；
- refine_final_error_category 从 final_state 接线；
- get_fix_strategy 对两个新类别的策略描述。
"""

from __future__ import annotations

from src.agents.error_classifier import (
    ErrorCategory,
    get_fix_strategy,
    refine_failure_category,
    refine_final_error_category,
)


class TestExecutionTraceMissing:
    """执行轨迹丢失（EXECUTION_TRACE_MISSING）。"""

    def test_failed_task_without_trace_returns_execution_trace_missing(self):
        # 任务失败 + 无 patch_rejected + 无 rag_empty + execution_trace 为空
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[],  # 空轨迹
        )
        assert result == ErrorCategory.EXECUTION_TRACE_MISSING.value

    def test_failed_task_with_trace_passes_through(self):
        # 有 execution_trace（至少 1 条）时不判定 trace_missing，原样返回
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[{"iteration": 0, "passed": False}],
        )
        assert result == "assertion"

    def test_none_trace_returns_execution_trace_missing(self):
        # execution_trace 为 None（未写入）也视为"丢失"
        result = refine_failure_category(
            "unknown",
            test_passed=False,
            execution_trace=None,
        )
        assert result == ErrorCategory.EXECUTION_TRACE_MISSING.value

    def test_passed_task_not_refined(self):
        # 成功任务原样返回（不做细化）
        result = refine_failure_category("assertion", test_passed=True, execution_trace=[])
        assert result == "assertion"


class TestMultiCandidateAllRejected:
    """多候选全拒绝（MULTI_CANDIDATE_ALL_REJECTED）。"""

    def test_all_candidates_rejected_returns_multi_rejected(self):
        # 多候选 stats：3 个候选，0 个通过静态筛选
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[{"iteration": 0, "passed": False}],  # 有轨迹（避免先命中 trace_missing）
            multi_candidate_stats={"candidates": 3, "static_passed": 0},
        )
        assert result == ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED.value

    def test_some_candidates_passed_returns_original(self):
        # 有候选通过静态筛选时不判定"全拒绝"
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[{"iteration": 0, "passed": False}],
            multi_candidate_stats={"candidates": 3, "static_passed": 2},
        )
        assert result == "assertion"

    def test_no_multi_stats_returns_original(self):
        # 未启用多候选（stats 为 None）时原样返回
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[{"iteration": 0, "passed": False}],
            multi_candidate_stats=None,
        )
        assert result == "assertion"


class TestRefinePriority:
    """判定优先级：patch_rejected > rag_empty > trace_missing > multi_rejected。"""

    def test_patch_rejected_wins_over_trace_missing(self):
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            repair_history=[{"patch_applied": False}],
            execution_trace=[],  # 同时满足 trace_missing，但 patch_rejected 优先级更高
        )
        assert result == ErrorCategory.PATCH_VALIDATION_FAILED.value

    def test_rag_empty_wins_over_trace_missing(self):
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            rag_stats=[{"results": 0}, {"results": 0}],
            execution_trace=[],  # rag_empty 优先级高于 trace_missing
        )
        assert result == ErrorCategory.RAG_RETRIEVAL_EMPTY.value

    def test_trace_missing_wins_over_multi_rejected(self):
        result = refine_failure_category(
            "assertion",
            test_passed=False,
            execution_trace=[],  # trace_missing（优先级高于 multi_rejected）
            multi_candidate_stats={"candidates": 3, "static_passed": 0},
        )
        assert result == ErrorCategory.EXECUTION_TRACE_MISSING.value


class TestRefineFinalErrorCategory:
    """从 final_state 接线（refine_final_error_category）。"""

    def test_extracts_all_state_fields(self):
        final_state = {
            "error_category": "assertion",
            "test_passed": False,
            "execution_trace": [],
        }
        result = refine_final_error_category(final_state)
        assert result == ErrorCategory.EXECUTION_TRACE_MISSING.value

    def test_multi_rejected_from_state(self):
        final_state = {
            "error_category": "assertion",
            "test_passed": False,
            "execution_trace": [{"iteration": 0, "passed": False}],
            "multi_candidate_stats": {"candidates": 3, "static_passed": 0},
        }
        result = refine_final_error_category(final_state)
        assert result == ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED.value

    def test_passed_state_returns_original(self):
        final_state = {"error_category": "assertion", "test_passed": True}
        result = refine_final_error_category(final_state)
        assert result == "assertion"


class TestNewCategoryFixStrategy:
    """新类别的修复策略描述（get_fix_strategy）。"""

    def test_execution_trace_missing_strategy(self):
        strategy = get_fix_strategy(ErrorCategory.EXECUTION_TRACE_MISSING)
        assert "execution_trace" in strategy.lower() or "轨迹" in strategy
        assert len(strategy) > 10  # 非空策略描述

    def test_multi_candidate_all_rejected_strategy(self):
        strategy = get_fix_strategy(ErrorCategory.MULTI_CANDIDATE_ALL_REJECTED)
        assert "多候选" in strategy or "候选" in strategy
        assert "静态筛选" in strategy or "回退" in strategy

    def test_strategy_for_other_categories_still_works(self):
        # 回归：原有类别策略不受新类别影响
        strategy = get_fix_strategy(ErrorCategory.ASSERTION)
        assert len(strategy) > 0
