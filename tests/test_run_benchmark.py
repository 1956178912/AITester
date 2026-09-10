"""experiments/run_benchmark.py 回归测试。

覆盖 0.9.8 去重重构：
- _build_task_result：成功/失败两类结果字典结构一致（单一构造点，防字段漂移）；
- run_single_task：基线成功/异常路径统一经 _build_task_result 汇总（重构回归）。
"""

from typing import Any

import experiments.run_benchmark as rb
from experiments.run_benchmark import _build_task_result
from src.datasets.dataset_loader import BenchmarkTask


def _make_task() -> BenchmarkTask:
    """构造一个最小可运行的基准测试任务（无需真实数据集）。"""
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


class TestBuildTaskResult:
    """_build_task_result 单一构造点测试。"""

    def test_success_shape(self):
        """成功路径：字段取自 final_state，与旧三分支成功实现一致。"""
        task = _make_task()
        state = {
            "test_passed": True,
            "coverage_report": 88.5,
            "iteration": 2,
            "diagnosis": "ok",
            "error_category": "",
            "rag_stats": [{"kind": "test_cases", "results": 3}],
        }
        result = _build_task_result(task, 1.234, final_state=state)
        assert result["task_id"] == "repo__repo-1"
        assert result["repo"] == "repo/repo"
        assert result["passed"] is True
        assert result["coverage"] == 88.5
        assert result["iterations"] == 2
        assert result["diagnosis"] == "ok"
        assert result["error_category"] == ""
        assert result["rag_stats"] == state["rag_stats"]
        assert result["elapsed_seconds"] == 1.23
        assert result["task_metadata"] == task.metadata
        # token_usage 为线程局部统计（测试中默认 0），键必须存在
        assert "token_usage" in result

    def test_failure_shape(self):
        """失败路径：无 final_state 时占位值，diagnosis/error_category 用传入值。"""
        task = _make_task()
        result = _build_task_result(task, 0.5, diagnosis="执行异常: boom", error_category="error")
        assert result["passed"] is False
        assert result["coverage"] == 0.0
        assert result["iterations"] == 0
        assert result["diagnosis"] == "执行异常: boom"
        assert result["error_category"] == "error"
        assert result["rag_stats"] is None
        assert result["elapsed_seconds"] == 0.5

    def test_success_and_failure_same_keys(self):
        """字段口径回归护栏：成功/失败两类结果键集合必须完全一致。"""
        task = _make_task()
        success = _build_task_result(task, 1.0, final_state={})
        failure = _build_task_result(task, 1.0)
        assert set(success.keys()) == set(failure.keys())


class TestRunSingleTask:
    """run_single_task 去重重构后的路径回归（mock 基线注册表，不触发 LLM 调用）。"""

    def test_success_and_exception_paths(self, tmp_path, monkeypatch):
        task = _make_task()
        calls: list[dict[str, Any]] = []

        def fake_baseline(state: dict[str, Any]) -> dict[str, Any]:
            calls.append(state)
            return {
                "test_passed": True,
                "coverage_report": 50.0,
                "iteration": 1,
                "diagnosis": None,
                "error_category": None,
                "rag_stats": None,
            }

        def raising_baseline(state: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

        monkeypatch.setitem(rb.BASELINE_REGISTRY, "ok", fake_baseline)
        monkeypatch.setitem(rb.BASELINE_REGISTRY, "boom", raising_baseline)

        results = rb.run_single_task(task, ["ok", "boom"], str(tmp_path))

        ok = results["ok"]
        assert ok["passed"] is True
        assert ok["coverage"] == 50.0
        assert ok["iterations"] == 1

        boom = results["boom"]
        assert boom["passed"] is False
        assert boom["error_category"] == "error"
        assert "执行异常: boom" in boom["diagnosis"]
        # 成功基线被调用一次，异常基线调用后抛出（无重试）
        assert len(calls) == 1
