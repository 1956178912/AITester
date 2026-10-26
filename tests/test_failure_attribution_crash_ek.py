"""EK 轮：已知崩溃原因必须落进归因列。

缺陷族：EJ 轮把 `GraphRecursionError` 折成结果行 `stop_reason="recursion_limit"`
后，`_build_task_result` 的失败分支仍把归因四键（failure_bucket /
failure_bucket_detail / attribution_edge / attribution_fault_side）硬编码为
None——同一行出现「终止原因已知、归因未知」的自相矛盾，且批次聚合仍把这类
确定性 harness 崩溃计入 `unclassified_rows`，ADR-0026 的 harness 归因在
生产工件里依旧不可读。

修法口径：
1. `_failure_attribution_for_result(final_state, stop_reason)`：final_state
   为 None 但 stop_reason 已知时，按已知原因重建状态视图交给分类法；
2. final_state 存在时仍以 `effective_stop_reason` 为准（行参数被忽略）；
3. 无 final_state 且无已知原因（普通异常 / 限流耗尽）仍四键 None，
   继续单列 `unclassified_rows`——那才是「根本没有终局状态」。
"""

from langgraph.errors import GraphRecursionError

import experiments.run_benchmark as rb
from experiments.run_benchmark import (
    _aggregate_failure_buckets,
    _build_task_result,
    _failure_attribution_for_result,
)
from src.datasets.dataset_loader import BenchmarkTask
from src.observability.failure_taxonomy import render_markdown


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


_EMPTY_ATTRIBUTION = {
    "failure_bucket": None,
    "failure_bucket_detail": None,
    "attribution_edge": None,
    "attribution_fault_side": None,
}


class TestAttributionForKnownCrash:
    def test_known_crash_reason_is_classified(self) -> None:
        attr = _failure_attribution_for_result(None, "recursion_limit")

        assert attr["failure_bucket"] == "generation_capability_failure"
        assert attr["attribution_edge"] == "harness"
        assert attr["attribution_fault_side"] == "harness_side"
        assert "状态信息不足" not in (attr["failure_bucket_detail"] or "")

    def test_unknown_crash_stays_unclassified(self) -> None:
        assert _failure_attribution_for_result(None) == _EMPTY_ATTRIBUTION

    def test_row_with_known_crash_reason_carries_attribution(self) -> None:
        row = _build_task_result(
            _make_task(),
            0.1,
            diagnosis="执行异常: Recursion limit of 56 reached",
            error_category="error",
            stop_reason="recursion_limit",
        )

        assert row["stop_reason"] == "recursion_limit"
        assert row["failure_bucket"] == "generation_capability_failure"
        assert row["attribution_edge"] == "harness"
        assert row["attribution_fault_side"] == "harness_side"
        assert "状态信息不足" not in row["failure_bucket_detail"]

    def test_row_without_reason_keeps_none(self) -> None:
        row = _build_task_result(_make_task(), 0.1, diagnosis="执行异常: boom", error_category="error")

        assert row["stop_reason"] is None
        for key, value in _EMPTY_ATTRIBUTION.items():
            assert row[key] == value


class TestAggregationDenominator:
    def test_known_crash_counts_into_distribution(self) -> None:
        known = _build_task_result(
            _make_task(), 0.1, diagnosis="boom", error_category="error", stop_reason="recursion_limit"
        )
        unknown = _build_task_result(_make_task(), 0.1, diagnosis="boom", error_category="error")

        summary = _aggregate_failure_buckets([known, unknown])

        assert summary["counts"]["generation_capability_failure"] == 1
        assert summary["unclassified_rows"] == 1
        assert summary["total"] == 1
        assert summary["total_rows"] == 2
        assert summary["shares"]["generation_capability_failure"] == 1.0
        assert summary["fault_side_counts"]["harness_side"] == 1
        assert summary["edge_counts"]["harness"] == 1
        markdown = render_markdown(summary)
        assert "另有 1 个任务无工作流终局状态" in markdown
        assert "批次共 2 行" in markdown


class TestRunSingleTaskWiring:
    def test_recursion_crash_row_is_attributed_end_to_end(self, tmp_path, monkeypatch) -> None:
        def raising(state: dict) -> dict:
            raise GraphRecursionError("Recursion limit of 56 reached")

        monkeypatch.setitem(rb.BASELINE_REGISTRY, "recursion", raising)
        row = rb.run_single_task(_make_task(), ["recursion"], str(tmp_path))["recursion"]

        assert row["stop_reason"] == "recursion_limit"
        assert row["failure_bucket"] == "generation_capability_failure"
        assert row["attribution_edge"] == "harness"
        assert row["attribution_fault_side"] == "harness_side"

    def test_plain_exception_row_stays_unclassified(self, tmp_path, monkeypatch) -> None:
        def raising(state: dict) -> dict:
            raise RuntimeError("boom")

        monkeypatch.setitem(rb.BASELINE_REGISTRY, "boom", raising)
        row = rb.run_single_task(_make_task(), ["boom"], str(tmp_path))["boom"]

        assert row["stop_reason"] is None
        for key, value in _EMPTY_ATTRIBUTION.items():
            assert row[key] == value
