"""experiments/run_benchmark.py 回归测试。

覆盖 0.1 去重重构 + 1.2 变异得分接线：
- _build_task_result：成功/失败两类结果字典结构一致（单一构造点，防字段漂移）；
- run_single_task：基线成功/异常路径统一经 _build_task_result 汇总（重构回归）；
- _compute_mutation_scores_for_baseline：1.2 变异得分逐任务写回 details[].mutation_score
  （开关启用时计算，generated_test/instance_code 缺失时写 None 保持键集合同构）。
"""

import json
import os
from typing import Any

import pytest

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
        # 1.3 命名契约符号守卫 / 2.2 重采样：成功分支取 final_state 值，
        # 失败分支 None 兜底（键集合同构）
        assert success["contract_missing_symbols"] is None
        assert failure["contract_missing_symbols"] is None
        assert success["patch_resample_stats"] is None
        assert failure["patch_resample_stats"] is None
        # 五、多维度污染检测：contamination_risk_level 字段必须存在；
        # 无 golden_patches 材料时返回 "not_applicable"（N7，2026-10-05
        # 复审：检测不适用与"检测过且无重叠证据"的 "low" 区分）
        assert success["contamination_risk_level"] == "not_applicable"
        assert failure["contamination_risk_level"] == "not_applicable"


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


class TestSlidingWindow:
    """0.7 债务项 2.5：滑窗提交，保持在途 future ≤ max_inflight。"""

    def _make_tasks(self, n: int) -> list[BenchmarkTask]:
        """构造 n 个 task_id 互不相同的任务。"""
        tasks = []
        for i in range(n):
            task = _make_task()
            task.task_id = f"repo__repo-{i}"
            tasks.append(task)
        return tasks

    def test_all_tasks_processed(self, tmp_path, monkeypatch):
        """滑窗派发：所有任务都被处理且结果经回调收集，不丢任务。"""
        import concurrent.futures

        tasks = self._make_tasks(20)
        collected: list[str] = []

        def fake_run_task(args):
            task, *_ = args
            return task, {"ok": {"passed": True, "elapsed_seconds": 0.001}}

        monkeypatch.setattr(rb, "_run_task_with_progress", fake_run_task)

        def on_task_done(task, task_results):
            collected.append(task.task_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            rb._run_tasks_sliding_window(
                executor, tasks, ["ok"], str(tmp_path), False, False, max_inflight=4, on_task_done=on_task_done
            )

        assert len(collected) == 20
        assert set(collected) == {t.task_id for t in tasks}

    def test_exception_task_isolated(self, tmp_path, monkeypatch):
        """滑窗派发：任务异常时回调收到空结果，其余任务不受影响。"""
        import concurrent.futures

        tasks = self._make_tasks(5)
        collected: dict[str, dict] = {}

        def fake_run_task(args):
            task, *_ = args
            if task.task_id == "repo__repo-3":
                raise RuntimeError("boom")
            return task, {"ok": {"passed": True, "elapsed_seconds": 0.001}}

        monkeypatch.setattr(rb, "_run_task_with_progress", fake_run_task)

        def on_task_done(task, task_results):
            collected[task.task_id] = task_results

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            rb._run_tasks_sliding_window(
                executor, tasks, ["ok"], str(tmp_path), False, False, max_inflight=3, on_task_done=on_task_done
            )

        assert len(collected) == 5  # 所有任务（含异常）都回调
        assert collected["repo__repo-3"] == {}  # 异常任务收到空结果
        assert collected["repo__repo-1"] != {}  # 正常任务结果保留


class TestDumpStateArtifactsObservationKeys:
    """H 轮（2026-10-16）：环节级工件白名单必须包含"只写不读"的观测信号。

    缺陷形态（与本白名单前两次扩容同构）：节点把信号写进 state，但白名单没登记
    → LangGraph 状态在 run 结束后被丢弃 → 下游分析永远读到 None → 指标失真，
    而节点注释承诺的用途（G2 风险分级 / 确定性套件入库）静默落空。
    """

    _OBSERVATION_KEYS = ("testless_validation", "deterministic_guard_report", "m10_leaf_fallback")

    def _dump(self, tmp_path, state: dict[str, Any]) -> dict[str, Any]:
        task = _make_task()
        rb._dump_state_artifacts(str(tmp_path), task, "aitester", state)
        artifact = tmp_path / "raw" / task.task_id / "aitester.json"
        return json.loads(artifact.read_text(encoding="utf-8"))

    def test_observation_signals_are_persisted(self, tmp_path) -> None:
        state = {
            "testless_validation": {"passed": False, "failed_layers": ["mypy"], "layers": {"mypy": {"passed": False}}},
            "deterministic_guard_report": {
                "filename": "m",
                "findings": [{"rule": "random_usage", "detail": "random.random()", "line": 3}],
                "is_deterministic": False,
            },
        }
        data = self._dump(tmp_path, state)
        assert data["testless_validation"] == state["testless_validation"]
        assert data["deterministic_guard_report"] == state["deterministic_guard_report"]

    def test_absent_signals_dump_as_null_not_missing_key(self, tmp_path) -> None:
        """默认档（两开关关）键必须**在场且为 null**——键集合同构，下游无需 hasattr 式防御。"""
        data = self._dump(tmp_path, {})
        for key in self._OBSERVATION_KEYS:
            assert key in data, f"工件缺键 {key}（白名单未登记 → 信号写进 state 即被丢弃）"
            assert data[key] is None

    def test_key_set_is_stable(self, tmp_path) -> None:
        """工件键集合钉死（新增/删除键必须显式改本用例，防字段静默漂移）。"""
        expected = {
            "task_id",
            "baseline",
            "test_plan",
            "generated_test",
            "diagnosis",
            "error_category",
            "patch",
            "test_passed",
            "iterations",
            "coverage",
            "rag_stats",
            "position_aware_focus",
            "repo_verification",
            "cross_file_deps",
            "testless_validation",
            "deterministic_guard_report",
            "m10_leaf_fallback",
            "task_metadata",
        }
        assert set(self._dump(tmp_path, {})) == expected


class TestFailureAttributionWiring:
    """I1（2026-10-16）：终局失效归因必须真的落进批次工件，且口径可复算。

    缺陷形态：`observability.failure_taxonomy` 自 U11（2026-10-05）落地以来
    **零生产调用点**——五桶分类与批次 XII 的 edge × fault_side 增补维度只在
    单测里被断言，批次工件/报表一处不落。G3 修好了写侧→读侧的键路径
    （logic_degraded 抬顶层），但整条归因链的末端仍不产出任何工件，
    "失败发生在哪个环节"因此无法从批次结果复算。
    """

    _NEW_KEYS = (
        "failure_bucket",
        "failure_bucket_detail",
        "attribution_edge",
        "attribution_fault_side",
        "m10_leaf_fallback",
    )

    def test_no_final_state_yields_none_not_uncategorized(self) -> None:
        """无工作流终局（运行异常/限流）→ 四键全 None，**不**冒充兜底桶。

        折进 uncategorized 会让桶分布的分母失去意义："归因未接线"与
        "状态信息不足"同形。改由 _aggregate_failure_buckets 单列计数。
        """
        got = rb._failure_attribution_for_result(None)
        assert set(got) == set(self._NEW_KEYS) - {"m10_leaf_fallback"}
        assert all(v is None for v in got.values()), got

    def test_state_view_rebuild_is_load_bearing(self) -> None:
        """状态视图重建不是装饰：直喂 final_state 会把失败任务全部落兜底桶。

        O35：stop_reason 由条件边函数原地写入，LangGraph 不回写 → 直读恒空。
        不经 effective_stop_reason 兜底，"迭代耗尽"这类**最常见的**生成能力
        失效会被误判成 UNCATEGORIZED——把"归因没接对"伪装成"系统失效无法分类"。
        """
        from src.observability.failure_taxonomy import annotate_final_state

        state = {"test_passed": False, "iteration": 5, "max_iterations": 5}
        assert annotate_final_state(state)["bucket"].value == "uncategorized", "前提失效：直喂已能分类"
        got = rb._failure_attribution_for_result(state)
        assert got["failure_bucket"] == "generation_capability_failure"
        assert got["attribution_fault_side"] == "model_side"
        assert got["attribution_edge"] == "debugger_to_executor"

    def test_converged_row_is_task_completed(self) -> None:
        """收敛优先于一切：即使迭代数达上限，test_passed=True 恒归 task_completed。"""
        got = rb._failure_attribution_for_result(
            {"test_passed": True, "iteration": 9, "max_iterations": 5, "budget_exceeded": True}
        )
        assert got["failure_bucket"] == "task_completed"
        assert got["attribution_fault_side"] == "uncategorized", "收敛行不得冒充归因结论"

    def test_verification_failure_beats_stop_reason(self) -> None:
        got = rb._failure_attribution_for_result(
            {"test_passed": False, "regression_detected": True, "iteration": 5, "max_iterations": 5}
        )
        assert got["failure_bucket"] == "verification_failure"
        assert got["attribution_fault_side"] == "harness_side"

    def test_row_carries_new_keys(self) -> None:
        """结果行五键落盘（含 I2 的 m10_leaf_fallback 顶层标记）。"""
        task = _make_task()
        state = {"test_passed": False, "iteration": 5, "max_iterations": 5, "m10_leaf_fallback": True}
        row = _build_task_result(task, 1.0, final_state=state)
        assert row["failure_bucket"] == "generation_capability_failure"
        assert row["attribution_fault_side"] == "model_side"
        assert row["m10_leaf_fallback"] is True
        assert isinstance(row["failure_bucket_detail"], str) and row["failure_bucket_detail"]

    def test_success_and_failure_rows_share_new_keys(self) -> None:
        """键集合同构：失败分支五键必须在场且为 None（下游无需 hasattr 式防御）。"""
        task = _make_task()
        success = _build_task_result(task, 1.0, final_state={"test_passed": True})
        failure = _build_task_result(task, 1.0)
        assert set(success) == set(failure)
        for key in self._NEW_KEYS:
            assert key in success, f"结果行缺键 {key}"
            assert failure[key] is None, f"失败分支 {key} 应为 None 占位"

    def test_row_is_json_serializable(self) -> None:
        """桶值必须是 str 而非 StrEnum 实例（跨语言消费方/严格 JSON 校验器口径）。"""
        row = _build_task_result(_make_task(), 1.0, final_state={"test_passed": True})
        for key in ("failure_bucket", "attribution_edge", "attribution_fault_side"):
            assert type(row[key]) is str, (key, type(row[key]))
        assert json.loads(json.dumps({k: row[k] for k in self._NEW_KEYS}))


class TestFailureBucketAggregation:
    """I1：臂级桶分布聚合的分母口径（唯一容易读错的地方，必须钉死）。"""

    def _rows(self) -> list[dict[str, Any]]:
        task = _make_task()
        return [
            _build_task_result(task, 1.0, final_state={"test_passed": True}),
            _build_task_result(task, 1.0, final_state={"test_passed": False, "iteration": 5, "max_iterations": 5}),
            _build_task_result(task, 1.0, final_state={"test_passed": False, "budget_exceeded": True}),
            _build_task_result(task, 1.0, final_state={"test_passed": False, "logic_degraded": True}),
            _build_task_result(task, 1.0, diagnosis="执行异常: boom", error_category="error"),  # 无终局状态
        ]

    def test_denominator_excludes_rows_without_final_state(self) -> None:
        agg = rb._aggregate_failure_buckets(self._rows())
        assert agg["total_rows"] == 5
        assert agg["unclassified_rows"] == 1
        assert agg["total"] == 4, "分布分母只算有终局状态的行"
        assert sum(agg["counts"].values()) == agg["total"]
        assert agg["counts"]["uncategorized"] == 0, "异常行不得被折进兜底桶"

    def test_shares_sum_to_one_over_classified(self) -> None:
        agg = rb._aggregate_failure_buckets(self._rows())
        assert abs(sum(agg["shares"].values()) - 1.0) < 1e-6
        assert agg["counts"]["task_completed"] == 1
        assert agg["counts"]["generation_capability_failure"] == 1
        assert agg["counts"]["verification_failure"] == 1
        # I3：stop_reason 为 unknown 时 logic_degraded 弱信号可达 → 规约层失效
        assert agg["counts"]["specification_failure"] == 1

    def test_all_buckets_edges_sides_present_even_at_zero(self) -> None:
        """键集合全域在场（0 桶也列出）：分布口径跨批次可比。"""
        from src.observability.failure_taxonomy import FAULT_SIDES, INTERACTION_EDGES, FailureBucket

        agg = rb._aggregate_failure_buckets([_build_task_result(_make_task(), 1.0, final_state={"test_passed": True})])
        assert set(agg["counts"]) == {b.value for b in FailureBucket}
        assert set(agg["fault_side_counts"]) == set(FAULT_SIDES)
        assert set(agg["edge_counts"]) == set(INTERACTION_EDGES)

    def test_empty_batch_is_safe(self) -> None:
        agg = rb._aggregate_failure_buckets([])
        assert agg["total"] == 0 and agg["total_rows"] == 0 and agg["unclassified_rows"] == 0
        assert all(v == 0.0 for v in agg["shares"].values())

    def test_output_feeds_render_markdown_with_denominator_disclosure(self) -> None:
        """聚合输出可直接喂报告层；分母披露行必须出现（否则报表把批次规模读小）。"""
        from src.observability.failure_taxonomy import render_markdown

        md = render_markdown(rb._aggregate_failure_buckets(self._rows()), title="臂级失效分布")
        assert "## 臂级失效分布" in md
        assert "总计：4 个任务" in md
        assert "另有 1 个任务无工作流终局状态" in md
        assert "批次共 5 行" in md


class TestModuleLevelAggregators:
    """J-1b（2026-10-17）：三个原 `run_benchmark()` 嵌套聚合器的口径锁定。

    外提前它们只能靠端到端跑批间接覆盖；现在逐口径钉死——分母、零除守卫、
    剔除规则都是报表读者最容易误读的地方。
    """

    def test_they_are_module_level_not_closures(self) -> None:
        """重构目的本身：qualname 必须无 `<locals>`，否则单测再度够不着。"""
        for fn in (
            rb._aggregate_rag_metrics,
            rb._aggregate_token_metrics,
            rb._aggregate_failure_categories,
        ):
            assert "<locals>" not in fn.__qualname__, f"{fn.__name__} 仍是嵌套函数：{fn.__qualname__}"

    def test_rag_hit_rate_denominator_is_retrievals(self) -> None:
        """hit_rate 分母 = 检索次数（不是任务数）；results==0 记未命中。"""
        got = rb._aggregate_rag_metrics(
            [
                {"rag_stats": [{"results": 2, "max_similarity": 0.9}, {"results": 0, "max_similarity": None}]},
                {"rag_stats": [{"results": 1, "max_similarity": 0.7}]},
                {"no_rag_stats_here": True},
            ]
        )
        assert got["retrievals"] == 3
        assert got["hits"] == 2
        assert got["hit_rate"] == 0.6667

    def test_rag_similarity_avg_skips_none_but_counts_them_as_retrievals(self) -> None:
        """max_similarity 缺失不入均值分母，但仍是 1 次检索（两个分母不得混用）。"""
        got = rb._aggregate_rag_metrics([{"rag_stats": [{"results": 1, "max_similarity": None}] * 2}])
        assert got == {"retrievals": 2, "hits": 2, "hit_rate": 1.0, "avg_max_similarity": None}

    def test_rag_empty_batch_shape_is_zero_not_crash(self) -> None:
        assert rb._aggregate_rag_metrics([]) == {
            "retrievals": 0,
            "hits": 0,
            "hit_rate": 0.0,
            "avg_max_similarity": None,
        }

    def test_token_cache_hit_rate_denominator_includes_real_calls(self) -> None:
        """cache_hit_rate = 命中 /(命中 + 真实调用)；写成 命中/调用 会把命中率虚高。"""
        got = rb._aggregate_token_metrics(self._two_rows())
        assert got["total_cache_hits"] == 1 and got["total_llm_calls"] == 5
        assert got["cache_hit_rate_pct"] == round(1 / 6 * 100, 2)

    def test_token_uncached_theoretical_restores_cache_savings(self) -> None:
        """无缓存理论成本必须含避免 token，否则跨批缓存命中率漂移会伪装成成本下降。"""
        got = rb._aggregate_token_metrics(self._two_rows())
        assert got["total_tokens"] == 450
        assert got["uncached_theoretical_tokens"] == 480
        assert got["output_share_pct"] == 33.33
        assert (got["avg_tokens_per_task"], got["avg_output_per_task"]) == (225.0, 75.0)

    def test_token_per_task_and_per_call_use_different_denominators(self) -> None:
        """per_task 分母 = 行数，per_call 分母 = 调用数（两者混用即成本口径错报）。"""
        got = rb._aggregate_token_metrics(self._two_rows())
        assert got["avg_output_per_call"] == 30.0
        assert got["avg_output_per_task"] == 75.0

    def test_token_missing_usage_row_is_zero_safe(self) -> None:
        """历史落盘行可无 token_usage；None 视为 0 且零除分支不得抛。"""
        got = rb._aggregate_token_metrics([{"passed": True}])
        assert got["total_tokens"] == 0
        assert got["cache_hit_rate_pct"] == 0.0
        assert got["avg_tokens_per_task"] == 0
        assert got["output_share_pct"] == 0.0
        assert got["avg_output_per_call"] == 0

    def test_failure_categories_excludes_passed_and_uncategorized(self) -> None:
        """只统计失败且有 error_category 的行；成功行的类别残留不得计入。"""
        got = rb._aggregate_failure_categories(
            [
                {"passed": False, "error_category": "timeout"},
                {"passed": False, "error_category": "timeout"},
                {"passed": True, "error_category": "timeout"},
                {"passed": False},
            ]
        )
        assert got == {"timeout": 2}

    def test_failure_categories_sorted_desc_and_ties_keep_row_order(self) -> None:
        """按计数降序；同数以行序稳定排列（否则跨批表格顺序随机、diff 无意义）。"""
        got = rb._aggregate_failure_categories(
            [
                {"passed": False, "error_category": "beta"},
                {"passed": False, "error_category": "alpha"},
                {"passed": False, "error_category": "gamma"},
                {"passed": False, "error_category": "gamma"},
            ]
        )
        assert list(got) == ["gamma", "beta", "alpha"]

    @staticmethod
    def _two_rows() -> list[dict[str, Any]]:
        return [
            {
                "token_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "llm_calls": 2,
                    "cache_hits": 1,
                    "cache_avoided_tokens": 30,
                }
            },
            {
                "token_usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "llm_calls": 3,
                    "cache_hits": 0,
                    "cache_avoided_tokens": 0,
                }
            },
        ]


class TestStagnationArm:
    """A-19（2026-10-17）：覆盖率停滞检测消融臂的 CLI→env 映射。

    为什么单独测：`workflow` 每次判定都现读 `COVERAGE_STALL_DETECT_ENABLE`
    （`_coverage_stall_enabled` → `env_flag`），CLI 写 env 即全链路生效；
    若映射写反，消融臂的"开"与"关"在工件 provenance 里看不出差别，
    整批对照会在无告警的情况下变成同一臂重复跑两次。
    """

    def test_no_arm_selected_returns_none_and_leaves_env_untouched(self, monkeypatch) -> None:
        """两臂都未指定：返回 None=沿用配置默认，且不得写入该 env 键。"""
        monkeypatch.delenv("COVERAGE_STALL_DETECT_ENABLE", raising=False)
        assert rb._apply_stagnation_arm() is None
        assert "COVERAGE_STALL_DETECT_ENABLE" not in os.environ

    def test_enable_arm_writes_true(self, monkeypatch) -> None:
        monkeypatch.delenv("COVERAGE_STALL_DETECT_ENABLE", raising=False)
        assert rb._apply_stagnation_arm(enable=True) == "true"
        assert os.environ["COVERAGE_STALL_DETECT_ENABLE"] == "true"

    def test_disable_arm_writes_false_overriding_profile_preset(self, monkeypatch) -> None:
        """对照臂必须能覆盖环境里既有值（否则"锁定不提前停"口径不成立）。"""
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        assert rb._apply_stagnation_arm(disable=True) == "false"
        assert os.environ["COVERAGE_STALL_DETECT_ENABLE"] == "false"

    def test_both_arms_raise_and_do_not_touch_env(self, monkeypatch) -> None:
        """互斥臂 fail fast：静默取一会让工件臂标签与命令意图不一致。"""
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "keep-me")
        with pytest.raises(ValueError, match="互斥"):
            rb._apply_stagnation_arm(enable=True, disable=True)
        assert os.environ["COVERAGE_STALL_DETECT_ENABLE"] == "keep-me"

    def test_value_is_read_back_by_env_flag(self, monkeypatch) -> None:
        """落盘值必须被生产读侧 `env_flag` 判为预期的开/关（端到端语义锁）。"""
        from src.utils.env_utils import env_flag

        monkeypatch.delenv("COVERAGE_STALL_DETECT_ENABLE", raising=False)
        rb._apply_stagnation_arm(enable=True)
        assert env_flag("COVERAGE_STALL_DETECT_ENABLE") is True
        rb._apply_stagnation_arm(disable=True)
        assert env_flag("COVERAGE_STALL_DETECT_ENABLE") is False
