"""EJ 轮：recursion_limit 终止原因的可观测面。

缺陷族：`StopReason.RECURSION_LIMIT` 枚举位、失效分类法的
`"recursion_limit" → harness/harness_side` 映射（ADR-0026）都在，但全链路
没有写入点——基准跑批的异常分支把结果行 `stop_reason` 硬编码为 `None`，
于是"图递归上限触顶"这一**确定性**终止原因在工件里退化成"没有终局状态"，
分类法为它准备的桶/边/侧三条映射永远不命中。

修法口径：
1. `GraphRecursionError`（LangGraph 包装器自己的硬上界）→ `recursion_limit`；
2. 普通 `RecursionError` 是节点代码缺陷，不得冒充编排上界；
3. 其余异常仍记 `None`（无终局状态，不折进 UNCATEGORIZED 桶）。
"""

from unittest.mock import MagicMock

from langgraph.errors import GraphRecursionError

import experiments.run_benchmark as rb
import src.graph.workflow as workflow
from experiments.run_benchmark import _build_task_result
from src.datasets.dataset_loader import BenchmarkTask
from src.graph.workflow import StopReason
from src.observability.failure_taxonomy import annotate_final_state


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


def _classifier():
    classifier = getattr(workflow, "stop_reason_for_exception", None)
    assert classifier is not None, "workflow 未提供异常→终止原因分类器"
    return classifier


class TestStopReasonForException:
    def test_graph_recursion_maps_to_recursion_limit(self) -> None:
        assert _classifier()(GraphRecursionError("Recursion limit of 56 reached")) is StopReason.RECURSION_LIMIT

    def test_plain_recursion_error_is_not_labeled(self) -> None:
        # Python 层递归溢出是节点代码缺陷，不是编排硬上界
        assert _classifier()(RecursionError("maximum recursion depth exceeded")) is None

    def test_other_exception_is_not_labeled(self) -> None:
        assert _classifier()(RuntimeError("boom")) is None


class TestFailureRowStopReason:
    def test_failure_row_records_known_stop_reason(self) -> None:
        row = _build_task_result(
            _make_task(),
            0.1,
            diagnosis="执行异常: Recursion limit of 56 reached",
            error_category="error",
            stop_reason="recursion_limit",
        )
        assert row["stop_reason"] == "recursion_limit"

    def test_failure_row_defaults_to_none(self) -> None:
        row = _build_task_result(_make_task(), 0.1, diagnosis="执行异常: boom", error_category="error")
        assert row["stop_reason"] is None

    def test_success_row_derives_from_final_state(self) -> None:
        # 成功分支有终局状态：以 effective_stop_reason 为准，异常侧参数不得覆盖
        row = _build_task_result(
            _make_task(),
            0.1,
            final_state={"test_passed": False, "budget_exceeded": True},
            stop_reason="recursion_limit",
        )
        assert row["stop_reason"] == "budget_exceeded"

    def test_key_sets_stay_identical(self) -> None:
        success = _build_task_result(_make_task(), 0.1, final_state={"test_passed": True})
        failure = _build_task_result(_make_task(), 0.1, stop_reason="recursion_limit")
        assert set(success) == set(failure)


class TestRunSingleTaskWiring:
    def test_recursion_crash_row_is_labeled_end_to_end(self, tmp_path, monkeypatch) -> None:
        def raising(state: dict) -> dict:
            raise GraphRecursionError("Recursion limit of 56 reached")

        monkeypatch.setitem(rb.BASELINE_REGISTRY, "recursion", raising)
        row = rb.run_single_task(_make_task(), ["recursion"], str(tmp_path))["recursion"]

        assert row["error_category"] == "error"
        assert row["stop_reason"] == "recursion_limit"
        # 口径不变：无终局状态的行仍不进桶分布分母
        assert row["failure_bucket"] is None
        # 标签落到分类法后兑现 ADR-0026 的 harness 归因承诺
        annotation = annotate_final_state({"test_passed": False, "stop_reason": row["stop_reason"]})
        assert annotation["bucket"].value == "generation_capability_failure"
        assert annotation["edge"] == "harness"
        assert annotation["fault_side"] == "harness_side"

    def test_rate_limit_retry_recursion_crash_is_labeled(self, tmp_path, monkeypatch) -> None:
        calls: list[int] = []

        def flaky(state: dict) -> dict:
            calls.append(1)
            if len(calls) == 1:
                response = MagicMock()
                response.status_code = 429
                raise rb.openai.RateLimitError("rate limited", response=response, body={})
            raise GraphRecursionError("Recursion limit of 56 reached")

        monkeypatch.setattr(rb.time, "sleep", lambda _seconds: None)
        monkeypatch.setitem(rb.BASELINE_REGISTRY, "flaky", flaky)
        row = rb.run_single_task(_make_task(), ["flaky"], str(tmp_path))["flaky"]

        assert row["error_category"] == "rate_limit"
        assert row["stop_reason"] == "recursion_limit"

    def test_plain_exception_row_stays_none(self, tmp_path, monkeypatch) -> None:
        def raising(state: dict) -> dict:
            raise RuntimeError("boom")

        monkeypatch.setitem(rb.BASELINE_REGISTRY, "boom", raising)
        row = rb.run_single_task(_make_task(), ["boom"], str(tmp_path))["boom"]

        assert row["stop_reason"] is None
