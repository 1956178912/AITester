"""R-3 回归测试：`run_benchmark.py` 后处理墙钟 hook（Q-3 模块接入，纯观测）。

覆盖（零网络/零 LLM；全部用 fake 任务/结果 + monkeypatch 后处理函数，不真正跑批）：
1. `_run_postprocess_stage`：单阶段计时、多 callable 顺序、异常时仍记录 wall
   且原异常上抛、后续 callable 不执行；
2. `_run_baseline_postprocess_with_wall`：mutation 关闭零行为（不调用/不建 map/
   不产生阶段键）、启用时三调用顺序/入参/日志与历史内联块等价、每基线样本粒度、
   mutation/MDO 异常路径（先记录 wall、再原异常上抛）；
3. `_postprocess_wall_summary_fields` / `_attach_postprocess_wall_to_summary`：
   summary 字段形状、granularity、"字段总在"（mutation 关闭 → 空映射）、阈值
   告警触发与 logger.warning、既有 summary 键零变化、JSON 可序列化；
4. 默认零行为变化证据：callable 调用序列/入参快照、bl_results 对象不被替换、
   summary 仅新增两键。
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

import experiments.run_benchmark as rb


def _fake_tasks(count: int = 2) -> list[Any]:
    """最小 fake 任务（hook 仅访问 task_id；不依赖 BenchmarkTask 重字段）。"""
    return [SimpleNamespace(task_id=f"task_{idx}") for idx in range(count)]


def _fake_results(count: int = 2) -> list[dict[str, Any]]:
    return [{"task_id": f"task_{idx}", "passed": True} for idx in range(count)]


@pytest.fixture
def postprocess_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any, Any, Any]]:
    """把三个后处理计算函数替换为记录调用（顺序 + 入参快照），返回调用日志。"""
    calls: list[tuple[str, Any, Any, Any]] = []

    def _scores(bl_results: Any, task_map: Any, max_mutants: Any) -> None:
        calls.append(("scores", bl_results, dict(task_map), max_mutants))

    def _detection(bl_results: Any, task_map: Any, max_mutants: Any, seed: Any) -> None:
        calls.append(("detection", bl_results, dict(task_map), (max_mutants, seed)))

    def _mdo(bl_results: Any, task_map: Any) -> None:
        calls.append(("mdo", bl_results, dict(task_map), None))

    monkeypatch.setattr(rb, "_compute_mutation_scores_for_baseline", _scores)
    monkeypatch.setattr(rb, "_compute_mutation_detection_for_baseline", _detection)
    monkeypatch.setattr(rb, "_compute_mdo_for_baseline", _mdo)
    return calls


# ─────────────────────────── 1. _run_postprocess_stage ───────────────────────────


class TestRunPostprocessStage:
    def test_single_call_recorded(self) -> None:
        durations: dict[str, list[float]] = {}
        calls: list[int] = []
        rb._run_postprocess_stage(durations, "mutation", lambda: calls.append(1))
        assert calls == [1]
        assert list(durations) == ["mutation"]
        assert len(durations["mutation"]) == 1
        assert isinstance(durations["mutation"][0], float)
        assert durations["mutation"][0] >= 0.0

    def test_multiple_callables_in_order(self) -> None:
        durations: dict[str, list[float]] = {}
        order: list[str] = []
        rb._run_postprocess_stage(
            durations,
            "mutation",
            lambda: order.append("scores"),
            lambda: order.append("detection"),
        )
        assert order == ["scores", "detection"]
        assert len(durations["mutation"]) == 1

    def test_stages_are_separate(self) -> None:
        durations: dict[str, list[float]] = {}
        rb._run_postprocess_stage(durations, "mutation", lambda: None)
        rb._run_postprocess_stage(durations, "mdo", lambda: None)
        assert set(durations) == {"mutation", "mdo"}
        assert len(durations["mutation"]) == 1
        assert len(durations["mdo"]) == 1

    def test_appends_across_baselines(self) -> None:
        durations: dict[str, list[float]] = {}
        rb._run_postprocess_stage(durations, "mutation", lambda: None)
        rb._run_postprocess_stage(durations, "mutation", lambda: None)
        assert len(durations["mutation"]) == 2

    def test_exception_still_records_and_reraises(self) -> None:
        durations: dict[str, list[float]] = {}
        later: list[str] = []

        def _boom() -> None:
            raise RuntimeError("mutation boom")

        with pytest.raises(RuntimeError, match="mutation boom"):
            rb._run_postprocess_stage(durations, "mutation", _boom, lambda: later.append("x"))
        assert later == []  # 异常后后续 callable 不执行
        assert len(durations["mutation"]) == 1  # 异常路径仍记录 wall 样本


# ─────────────────────────── 2. 单基线后处理 hook ───────────────────────────


class TestBaselinePostprocessHook:
    def test_disabled_zero_behavior(self, postprocess_calls: list[Any]) -> None:
        durations: dict[str, list[float]] = {}
        results = _fake_results()
        # 用无 task_id 属性的对象证明 disabled 分支不构建 task_map（不访问任务）
        rb._run_baseline_postprocess_with_wall(
            results,
            [object(), object()],
            durations,
            mutation_enabled=False,
            mutation_max_mutants=10,
            seed=42,
        )
        assert postprocess_calls == []
        assert durations == {}
        assert results == _fake_results()

    def test_enabled_call_sequence_and_args(self, postprocess_calls: list[Any]) -> None:
        durations: dict[str, list[float]] = {}
        results = _fake_results()
        tasks = _fake_tasks()
        rb._run_baseline_postprocess_with_wall(
            results,
            tasks,
            durations,
            mutation_enabled=True,
            mutation_max_mutants=7,
            seed=42,
        )
        assert [call[0] for call in postprocess_calls] == ["scores", "detection", "mdo"]
        # bl_results 同一对象透传（不复制/不替换）
        assert all(call[1] is results for call in postprocess_calls)
        assert postprocess_calls[0][3] == 7
        assert postprocess_calls[1][3] == (7, 42)
        assert postprocess_calls[2][3] is None
        assert set(durations) == {"mutation", "mdo"}
        assert len(durations["mutation"]) == 1
        assert len(durations["mdo"]) == 1

    def test_task_map_contains_task_ids(self, postprocess_calls: list[Any]) -> None:
        rb._run_baseline_postprocess_with_wall(
            _fake_results(),
            _fake_tasks(3),
            {},
            mutation_enabled=True,
            mutation_max_mutants=5,
            seed=1,
        )
        assert set(postprocess_calls[0][2]) == {"task_0", "task_1", "task_2"}

    def test_per_baseline_granularity(self, postprocess_calls: list[Any]) -> None:
        """两基线各跑一次 hook → 每阶段 2 个样本（粒度 per_baseline）。"""
        durations: dict[str, list[float]] = {}
        for _ in range(2):
            rb._run_baseline_postprocess_with_wall(
                _fake_results(),
                _fake_tasks(),
                durations,
                mutation_enabled=True,
                mutation_max_mutants=5,
                seed=1,
            )
        assert len(durations["mutation"]) == 2
        assert len(durations["mdo"]) == 2
        fields, _ = rb._postprocess_wall_summary_fields(durations)
        assert fields["postprocess_wall"]["mutation"]["n_tasks"] == 2

    def test_mutation_exception_records_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("scores boom")

        monkeypatch.setattr(rb, "_compute_mutation_scores_for_baseline", _boom)
        durations: dict[str, list[float]] = {}
        with pytest.raises(RuntimeError, match="scores boom"):
            rb._run_baseline_postprocess_with_wall(
                _fake_results(),
                _fake_tasks(),
                durations,
                mutation_enabled=True,
                mutation_max_mutants=5,
                seed=1,
            )
        assert len(durations["mutation"]) == 1  # 异常路径仍写样本
        assert "mdo" not in durations  # MDO 未执行 → 不产生空阶段键

    def test_mdo_exception_records_and_reraises(
        self, postprocess_calls: list[Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: Any, **kwargs: Any) -> None:
            raise ValueError("mdo boom")

        monkeypatch.setattr(rb, "_compute_mdo_for_baseline", _boom)
        durations: dict[str, list[float]] = {}
        with pytest.raises(ValueError, match="mdo boom"):
            rb._run_baseline_postprocess_with_wall(
                _fake_results(),
                _fake_tasks(),
                durations,
                mutation_enabled=True,
                mutation_max_mutants=5,
                seed=1,
            )
        assert len(durations["mutation"]) == 1
        assert len(durations["mdo"]) == 1  # MDO 异常路径仍记录样本

    def test_enabled_logs_same_message(self, postprocess_calls: list[Any], caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=rb.logger.name):
            rb._run_baseline_postprocess_with_wall(
                _fake_results(),
                _fake_tasks(),
                {},
                mutation_enabled=True,
                mutation_max_mutants=10,
                seed=42,
            )
        assert any("启用变异得分评估（1.2）" in record.message for record in caplog.records)


# ─────────────────────────── 3. summary 字段 / 告警 / 落盘形状 ───────────────────────────


class TestSummaryFields:
    def test_empty_durations_field_present(self) -> None:
        fields, warnings = rb._postprocess_wall_summary_fields({})
        assert fields["postprocess_wall"] == {}
        assert fields["postprocess_wall_granularity"] == "per_baseline"
        assert warnings == []

    def test_shape_after_samples(self) -> None:
        fields, warnings = rb._postprocess_wall_summary_fields({"mutation": [1.0, 2.0], "mdo": [0.5]})
        wall = fields["postprocess_wall"]
        assert set(wall) == {"mutation", "mdo"}
        assert set(wall["mutation"]) == {
            "wall_s",
            "n_tasks",
            "mean_s",
            "p50_s",
            "p95_s",
            "max_s",
            "timed_out_tasks",
        }
        assert wall["mutation"]["n_tasks"] == 2
        assert wall["mdo"]["n_tasks"] == 1
        assert warnings == []

    def test_json_serializable(self) -> None:
        fields, _ = rb._postprocess_wall_summary_fields({"mdo": [1.5, 2.5]})
        payload = json.dumps({"summary": fields}, ensure_ascii=False)
        loaded = json.loads(payload)
        assert loaded["summary"]["postprocess_wall_granularity"] == "per_baseline"
        assert loaded["summary"]["postprocess_wall"]["mdo"]["n_tasks"] == 2

    def test_warning_threshold_triggers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITESTER_POSTPROCESS_WARN_S", "1")
        fields, warnings = rb._postprocess_wall_summary_fields({"mutation": [5.0, 5.0]})
        assert len(warnings) == 1
        assert "mutation" in warnings[0]
        assert fields["postprocess_wall"]["mutation"]["wall_s"] == 10.0

    def test_warning_threshold_not_triggered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITESTER_POSTPROCESS_WARN_S", "600")
        _, warnings = rb._postprocess_wall_summary_fields({"mutation": [0.1, 0.2]})
        assert warnings == []


class TestAttachToSummary:
    def test_only_adds_two_keys(self) -> None:
        summary: dict[str, Any] = {"results": {}, "total_tasks": 3, "seed": 42}
        rb._attach_postprocess_wall_to_summary(summary, {"mdo": [0.5]})
        assert set(summary) == {"results", "total_tasks", "seed", "postprocess_wall", "postprocess_wall_granularity"}
        assert summary["total_tasks"] == 3
        assert summary["postprocess_wall"]["mdo"]["n_tasks"] == 1

    def test_empty_durations_field_present(self) -> None:
        summary: dict[str, Any] = {}
        rb._attach_postprocess_wall_to_summary(summary, {})
        assert summary["postprocess_wall"] == {}
        assert summary["postprocess_wall_granularity"] == "per_baseline"

    def test_warning_logged(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("AITESTER_POSTPROCESS_WARN_S", "1")
        summary: dict[str, Any] = {}
        with caplog.at_level(logging.WARNING, logger=rb.logger.name):
            rb._attach_postprocess_wall_to_summary(summary, {"mdo": [700.0]})
        assert any("mdo" in record.message and "墙钟" in record.message for record in caplog.records)


# ─────────────────────────── 4. 默认零行为变化证据 ───────────────────────────


class TestZeroBehaviorRegression:
    def test_legacy_inline_sequence_equivalence(self, postprocess_calls: list[Any]) -> None:
        """hook 启用路径的调用序列与历史内联块逐项等价（顺序 + 入参）。

        历史内联块（R-3 前）：
            _compute_mutation_scores_for_baseline(bl_results, task_map, MUTATION_MAX_MUTANTS)
            _compute_mutation_detection_for_baseline(bl_results, task_map, MUTATION_MAX_MUTANTS, seed=seed)
            _compute_mdo_for_baseline(bl_results, task_map)
        """
        results = _fake_results()
        tasks = _fake_tasks()
        rb._run_baseline_postprocess_with_wall(
            results,
            tasks,
            {},
            mutation_enabled=True,
            mutation_max_mutants=rb.MUTATION_MAX_MUTANTS,
            seed=7,
        )
        expected_task_map = {task.task_id: task for task in tasks}
        assert [call[0] for call in postprocess_calls] == ["scores", "detection", "mdo"]
        assert postprocess_calls[0][1] is results
        assert postprocess_calls[0][2] == expected_task_map
        assert postprocess_calls[0][3] == rb.MUTATION_MAX_MUTANTS
        assert postprocess_calls[1][3] == (rb.MUTATION_MAX_MUTANTS, 7)
        assert postprocess_calls[2][1] is results
        assert postprocess_calls[2][2] == expected_task_map

    def test_disabled_does_not_mutate_results(self, postprocess_calls: list[Any]) -> None:
        results = _fake_results()
        snapshot = [dict(row) for row in results]
        rb._run_baseline_postprocess_with_wall(
            results,
            _fake_tasks(),
            {},
            mutation_enabled=False,
            mutation_max_mutants=10,
            seed=1,
        )
        assert results == snapshot

    def test_summary_payload_roundtrip(self) -> None:
        summary: dict[str, Any] = {"results": {"aitester": {"success_rate": 50.0}}, "seed": 42}
        rb._attach_postprocess_wall_to_summary(summary, {"mutation": [0.2], "mdo": [0.1]})
        rt = json.loads(json.dumps(summary, ensure_ascii=False))
        assert rt["results"]["aitester"]["success_rate"] == 50.0  # 旧字段原样
        assert rt["postprocess_wall_granularity"] == "per_baseline"
        assert rt["postprocess_wall"]["mutation"]["n_tasks"] == 1
