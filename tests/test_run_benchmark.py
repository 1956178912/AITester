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

    def test_thread_local_api_assignment_restored_after_task(self, tmp_path, monkeypatch):
        """W 轮连带修复：run_single_task 结束后线程局部 API 分配恢复原状。

        `_set_thread_api` 把任务分配写入当前线程 `_thread_local`；并行跑批
        下每任务重新分配、行为不变，但进程内单线程调用方（CLI/库/测试）此前
        会把最后一次分配（真实 env 凭证）永久留在主线程，污染后续
        `_get_llm_config` / `_get_all_api_configs` 与缓存身份。
        """
        from src.agents.llm_client import _thread_local

        monkeypatch.setitem(
            rb.BASELINE_REGISTRY,
            "ok",
            lambda state: {
                "test_passed": True,
                "coverage_report": 0.0,
                "iteration": 0,
                "diagnosis": None,
                "error_category": None,
                "rag_stats": None,
            },
        )
        # 进入前：线程局部无分配
        for attr in ("api_key", "base_url", "model_name"):
            monkeypatch.delattr(_thread_local, attr, raising=False)
        rb.run_single_task(_make_task(), ["ok"], str(tmp_path))
        for attr in ("api_key", "base_url", "model_name"):
            assert not hasattr(_thread_local, attr), f"任务结束后线程局部 {attr} 不得残留"

        # 进入前已有分配 → 恢复为原值（不被任务分配覆盖）
        monkeypatch.setattr(_thread_local, "api_key", "outer-key", raising=False)
        monkeypatch.setattr(_thread_local, "base_url", "https://outer.example/v1", raising=False)
        monkeypatch.setattr(_thread_local, "model_name", "outer-model", raising=False)
        rb.run_single_task(_make_task(), ["ok"], str(tmp_path))
        assert _thread_local.api_key == "outer-key"
        assert _thread_local.base_url == "https://outer.example/v1"
        assert _thread_local.model_name == "outer-model"


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
            # BN 轮（2026-10-22）：AITesterState 声明的 10 个 status/outcomes 通道
            # 归位进白名单（此前 raw 工件里 0 出现 ⇒ 归档无法复核"检查崩了"与
            # "按设计没跑"的区别）。逐键断言见 tests/test_bn_status_persistence.py。
            "contract_status",
            "static_check_status",
            "static_check_outcomes",
            "safety_check_status",
            "safety_check_outcomes",
            "oracle_check_status",
            "oracle_check_outcomes",
            "detection_first_status",
            "edit_intent_status",
            "deterministic_repair_status",
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


class TestReproProvenanceGitSha:
    """A03（2026-10-18 第三方审查 P1）：`.repro_provenance` 的 GIT_SHA 必须被消费。

    评审证据：Dockerfile.repro 用 `--build-arg GIT_SHA` 把提交 SHA 写入
    `/workspace/.repro_provenance`，而 `.dockerignore` 排除 `.git`——容器内
    `git rev-parse HEAD` 必然失败；历史实现只检查 marker **是否存在**
    （`environment.in_docker_repro`），从不读取 GIT_SHA，导致复现容器内
    `provenance.git_sha=None`，"build-arg 使提交可追溯"落空。

    修复口径（这些用例锁定）：
    - 有 git：git HEAD 为来源，marker 值同时记录并校验一致性；
    - 无 git（复现容器 / 源码包）：marker 的 GIT_SHA 作为 provenance 来源；
    - 两者都无：git_sha=None 且来源=None（如实标注不可追溯）。
    """

    _MARKER_SHA = "0123456789abcdef0123456789abcdef01234567"

    def _write_marker(self, directory, value: str | None = None) -> None:
        content = f"GIT_SHA={self._MARKER_SHA if value is None else value}\n"
        (directory / ".repro_provenance").write_text(content, encoding="utf-8")

    @staticmethod
    def _head_sha() -> str:
        import subprocess

        repo = rb.Path(rb.__file__).resolve().parent.parent
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(repo), timeout=10
        ).stdout.strip()

    def test_marker_git_sha_used_when_git_unavailable(self, tmp_path):
        """复现容器场景（无 .git）：git_sha 来自 marker，来源如实标注。"""
        self._write_marker(tmp_path)
        block = rb._resolve_git_provenance(workspace_dir=tmp_path, repo_dir=tmp_path)
        assert block["git_sha"] == self._MARKER_SHA
        assert block["git_sha_source"] == "repro_provenance"
        assert block["git_available"] is False
        assert block["in_docker_repro"] is True
        assert block["repro_provenance"]["present"] is True
        assert block["repro_provenance"]["git_sha"] == self._MARKER_SHA
        assert block["repro_provenance"]["git_sha_matches_git"] is None

    def test_git_available_and_marker_consistent(self, tmp_path):
        """有 git 且 marker 与 HEAD 一致：来源=git，一致性=True、无冲突。"""
        head = self._head_sha()
        assert head
        self._write_marker(tmp_path, value=head)
        block = rb._resolve_git_provenance(workspace_dir=tmp_path)
        assert block["git_sha"] == head
        assert block["git_sha_source"] == "git"
        assert block["git_available"] is True
        assert block["repro_provenance"]["git_sha_matches_git"] is True
        assert block["repro_provenance"]["git_sha_conflict"] is False

    def test_git_available_and_marker_mismatch_flagged(self, tmp_path):
        """有 git 但 marker SHA 不同：记住两者并标记冲突（不得静默取一个）。"""
        self._write_marker(tmp_path, value="deadbeef" * 5)
        block = rb._resolve_git_provenance(workspace_dir=tmp_path)
        assert block["git_sha"] == self._head_sha()
        assert block["git_sha_source"] == "git"
        assert block["repro_provenance"]["git_sha"] == "deadbeef" * 5
        assert block["repro_provenance"]["git_sha_matches_git"] is False
        assert block["repro_provenance"]["git_sha_conflict"] is True

    def test_unknown_marker_value_is_not_used_as_sha(self, tmp_path):
        """`ARG GIT_SHA` 缺省值 unknown 不是提交 SHA——不得写进 provenance。"""
        self._write_marker(tmp_path, value="unknown")
        block = rb._resolve_git_provenance(workspace_dir=tmp_path, repo_dir=tmp_path)
        assert block["git_sha"] is None
        assert block["git_sha_source"] is None
        assert block["in_docker_repro"] is True  # 容器标记仍在
        assert block["repro_provenance"]["git_sha"] is None

    def test_no_marker_and_no_git(self, tmp_path):
        """两者都不可用：如实标注 None，不伪造来源。"""
        block = rb._resolve_git_provenance(workspace_dir=tmp_path, repo_dir=tmp_path)
        assert block["git_sha"] is None
        assert block["git_sha_source"] is None
        assert block["in_docker_repro"] is False
        assert block["repro_provenance"]["present"] is False

    def test_environment_block_carries_source_fields(self, tmp_path):
        """environment 块含 git_sha_source / repro_provenance（结果 JSON 可审计）。"""
        self._write_marker(tmp_path)
        env = rb._build_environment_provenance(
            tmp_path, git_block=rb._resolve_git_provenance(tmp_path, repo_dir=tmp_path)
        )
        assert set(env) >= {
            "python_version",
            "platform",
            "git_sha",
            "git_sha_source",
            "in_docker_repro",
            "repro_provenance",
        }
        assert env["git_sha"] == self._MARKER_SHA
        assert env["git_sha_source"] == "repro_provenance"
        assert env["in_docker_repro"] is True
        assert env["repro_provenance"]["git_sha"] == self._MARKER_SHA

    def test_run_benchmark_wires_environment_and_provenance_blocks(self):
        """静态接线守卫：run_benchmark 必须使用统一解析结果（防回退为存在性检查）。"""
        import inspect

        source = inspect.getsource(rb.run_benchmark)
        assert "_build_environment_provenance" in source
        assert '"git_sha_source": _git_block["git_sha_source"]' in source
        assert '"repro_provenance": _git_block["repro_provenance"]' in source
        # 旧实现的两个只查存在性的表达式不得回归
        assert 'os.path.exists(os.path.join(os.getcwd(), ".repro_provenance"))' not in source


# ═══════════════════════════════════════════════════════════════════════════
#  A16 证据消费（2026-10-19 Y 轮审计补口）
# ═══════════════════════════════════════════════════════════════════════════
#
# 审计来源：`ff15a2f`→HEAD 的逐行覆盖率审计显示
# `_apply_execution_flaky_evidence` 的 flaky 分支（第 281-287 行）零执行——
# 既有测试只覆盖了"非 flaky → 写 test_passed"的快速返回路径。
#
# 为什么危险：single_agent 基线绕过工作流节点直接调 ExecutorAgent，若不消费
# 执行层的 fail→pass 证据，它会把"同测试首败次过"记成 `test_passed=True`，
# 把执行不稳定抹成成功证据——正是 A16 要消除的判分偏差。


def test_flaky_evidence_is_consumed_conservatively() -> None:
    """flaky 证据存在时：保守记 False + 写真实 pass/total 计数。"""
    state: dict[str, Any] = {}
    result = {
        "flaky_fail_then_pass": True,
        "passed": True,  # 最终一次执行通过——不得直接当成功
        "execution_attempts": [{"passed": False}, {"passed": True}, {"passed": True}],
    }
    rb._apply_execution_flaky_evidence(state, result)

    assert state["test_passed"] is False, "不稳定结果不能作为成功证据"
    assert state["flaky_detected"] is True
    assert state["flaky_unverified"] is True
    assert state["flaky_pass_count"] == 2
    assert state["flaky_total_count"] == 3


def test_flaky_evidence_filters_non_dict_attempts() -> None:
    """尝试记录里的非 dict 条目必须被过滤（不得让 len 虚高或计数崩溃）。"""
    state: dict[str, Any] = {}
    result = {
        "flaky_fail_then_pass": True,
        "passed": True,
        "execution_attempts": [{"passed": True}, "脏数据", None, {"passed": False}],
    }
    rb._apply_execution_flaky_evidence(state, result)

    assert state["flaky_pass_count"] == 1
    assert state["flaky_total_count"] == 2, "非 dict 条目不计入总数"


def test_non_flaky_path_writes_only_test_passed() -> None:
    """无 flaky 证据时只写 test_passed——其余键保持未设置（历史口径零变化）。"""
    state: dict[str, Any] = {}
    rb._apply_execution_flaky_evidence(state, {"passed": True})

    assert state == {"test_passed": True}, f"非 flaky 路径不得写入额外证据键：{state}"


# ═══════════════════════════════════════════════════════════════════════════
#  A03 复现来源解析的降级路径（2026-10-19 Y2 审计补口）
# ═══════════════════════════════════════════════════════════════════════════
#
# 审计来源：`ff15a2f`→HEAD 的逐行覆盖率审计显示，marker 读取失败、marker 行
# 格式不符、git 调用异常三条降级路径零执行。它们共同保证"溯源不可得时如实
# 记录 error / 回落 marker，而不是抛异常中断整批跑测"——若退化，一次权限
# 异常就能让整批实验在启动阶段崩溃，而既有测试全绿。


def test_marker_read_error_is_recorded_not_raised(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """marker 存在但读不出（权限/编码）→ 记录 error，不抛异常。"""
    (tmp_path / ".repro_provenance").write_text("GIT_SHA=deadbeefcafe", encoding="utf-8")

    def _boom(self: Any, *args: Any, **kwargs: Any) -> str:
        raise OSError("权限不足")

    monkeypatch.setattr("pathlib.Path.read_text", _boom)
    info = rb._read_repro_provenance_marker(tmp_path)

    assert info["present"] is True, "文件存在性判定不受读取失败影响"
    assert info["git_sha"] is None
    assert "OSError" in (info["error"] or ""), "异常类型须如实记录，供批次审计"


def test_marker_ignores_malformed_lines(tmp_path: Any) -> None:
    """marker 行格式不符（无 `=` / key 非 GIT_SHA）必须跳过，不得中断解析。"""
    (tmp_path / ".repro_provenance").write_text(
        "no-equals-here\nSOMETHING=1\n  git_sha = deadbeefcafe  \n", encoding="utf-8"
    )
    info = rb._read_repro_provenance_marker(tmp_path)

    assert info["git_sha"] == "deadbeefcafe", "前两行应被跳过，键名大小写不敏感"


def test_git_exception_degrades_to_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """git 调用异常（未安装/权限）→ git_available=False，回落 marker 作为来源。"""
    (tmp_path / ".repro_provenance").write_text("GIT_SHA=deadbeefcafe", encoding="utf-8")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("git 不可用")

    monkeypatch.setattr(rb.subprocess, "run", _boom)
    resolved = rb._resolve_git_provenance(workspace_dir=tmp_path, repo_dir=tmp_path)

    assert resolved["git_available"] is False
    assert resolved["git_sha"] == "deadbeefcafe"
    assert resolved["git_sha_source"] == "repro_provenance", "无 git 时以 marker 为来源"
    assert resolved["repro_provenance"]["git_sha_matches_git"] is None
    assert resolved["repro_provenance"]["git_sha_conflict"] is False
