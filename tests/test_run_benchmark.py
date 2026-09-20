"""experiments/run_benchmark.py 回归测试。

覆盖 0.1 去重重构 + 1.2 变异得分接线：
- _build_task_result：成功/失败两类结果字典结构一致（单一构造点，防字段漂移）；
- run_single_task：基线成功/异常路径统一经 _build_task_result 汇总（重构回归）；
- _compute_mutation_scores_for_baseline：1.2 变异得分逐任务写回 details[].mutation_score
  （开关启用时计算，generated_test/instance_code 缺失时写 None 保持键集合同构）。
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
            "generated_test": "def test_f():\n    assert f() == 1\n",
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
        # 1.2 变异得分：generated_test 写进结果行（成功分支），供 compute_mutation_score 消费
        assert result["generated_test"] == state["generated_test"]
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
        success = _build_task_result(task, 1.0, final_state={"patch": "+x", "generated_test": "def t(): pass"})
        failure = _build_task_result(task, 1.0)
        assert set(success.keys()) == set(failure.keys())
        assert "patch" in success, "结果行必须携带 patch 字段（2.1 污染检测输入）"
        assert success["patch"] == "+x"
        assert failure["patch"] is None
        # 1.2 变异得分：generated_test 成功分支取 final_state 值，失败分支 None 兜底
        assert success["generated_test"] == "def t(): pass"
        assert failure["generated_test"] is None


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


class TestComputeMutationScoresForBaseline:
    """1.2 变异得分接线：_compute_mutation_scores_for_baseline 逐任务写回 mutation_score。"""

    def _make_task(self, instance_code: str = "def f():\n    return 1\n") -> BenchmarkTask:
        return BenchmarkTask(
            task_id="repo__repo-1",
            repo_name="repo/repo",
            problem_statement="fix a bug",
            instance_code=instance_code,
            test_code="def test_f():\n    assert f() == 1\n",
            expected_pass_count=0,
            total_test_count=1,
            metadata={"source": "test"},
        )

    def test_missing_generated_test_writes_none(self, monkeypatch):
        """generated_test 缺失（旧 JSON 兼容 / 失败分支）→ mutation_score=None，不崩溃。"""
        task = self._make_task()
        task_map = {task.task_id: task}
        bl_results = [
            {"task_id": task.task_id, "repo": task.repo_name, "passed": True, "generated_test": None},
            {"task_id": task.task_id, "repo": task.repo_name, "passed": False, "generated_test": None},
        ]
        # mock compute_mutation_score 确认"未被调用"（缺失即跳过）
        from experiments import mutation_testing

        calls: list[dict] = []
        monkeypatch.setattr(
            mutation_testing,
            "compute_mutation_score",
            lambda **kw: calls.append(kw) or {"available": True, "mutation_score": 0.5},
        )
        rb._compute_mutation_scores_for_baseline(bl_results, task_map, max_mutants=5)
        assert all(r["mutation_score"] is None for r in bl_results), "缺失 generated_test 应写 None"
        assert calls == [], "缺失 generated_test 不应调用 compute_mutation_score"

    def test_with_generated_test_calls_compute(self, monkeypatch):
        """generated_test 存在 → 调用 compute_mutation_score，写回 mutation_score。"""
        task = self._make_task(instance_code="def check(x):\n    if x == 5:\n        return True\n    return False\n")
        task_map = {task.task_id: task}
        bl_results = [
            {
                "task_id": task.task_id,
                "repo": task.repo_name,
                "passed": True,
                "generated_test": "def test_check():\n    assert check(5) is True\n",
            },
        ]
        captured: list[dict] = []

        def fake_compute(**kw):
            captured.append(kw)
            return {
                "available": True,
                "mutation_score": 0.75,
                "mutants_killed": 3,
                "mutants_total": 4,
                "elapsed_seconds": 1.2,
            }

        from experiments import mutation_testing

        monkeypatch.setattr(mutation_testing, "compute_mutation_score", fake_compute)
        rb._compute_mutation_scores_for_baseline(bl_results, task_map, max_mutants=5)
        assert bl_results[0]["mutation_score"] == 0.75, "应写回 compute 产出的 mutation_score"
        assert len(captured) == 1, "应调用一次 compute_mutation_score"
        assert captured[0]["max_mutants"] == 5
        assert captured[0]["source_code"] == task.instance_code
        assert captured[0]["test_code"] == bl_results[0]["generated_test"]

    def test_unknown_task_id_writes_none(self, monkeypatch):
        """task_id 不在 dataset_tasks 映射中（task 缺失）→ mutation_score=None。"""
        bl_results = [{"task_id": "ghost__task", "repo": "x/y", "passed": True, "generated_test": "def t(): pass"}]
        rb._compute_mutation_scores_for_baseline(bl_results, {}, max_mutants=5)
        assert bl_results[0]["mutation_score"] is None

    def test_empty_instance_code_writes_none(self, monkeypatch):
        """task.instance_code 为空 → mutation_score=None（无源码可变异）。"""
        task = self._make_task(instance_code="")
        task_map = {task.task_id: task}
        bl_results = [
            {"task_id": task.task_id, "repo": task.repo_name, "passed": True, "generated_test": "def t(): pass"}
        ]
        from experiments import mutation_testing

        calls: list[dict] = []
        monkeypatch.setattr(
            mutation_testing,
            "compute_mutation_score",
            lambda **kw: calls.append(kw) or {"available": True, "mutation_score": 0.5},
        )
        rb._compute_mutation_scores_for_baseline(bl_results, task_map, max_mutants=5)
        assert bl_results[0]["mutation_score"] is None
        assert calls == [], "空 instance_code 不应调用 compute_mutation_score"
