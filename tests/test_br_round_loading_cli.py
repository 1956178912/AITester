"""BR 轮（2026-10-22 第三方集中复审）加载/CLI/隔离建议：F06/F07/F11/F12。

F06：pass@k 用裸 task_id 跨批合并，把不同题目当"同题多轮"。
F07：批次加载非原子——后一臂失败时前一臂已写入且来源不登记。
F11：`--json` 模式下异常任务既无成功行也无错误行（stdout 里整个任务消失）。
F12：恢复指引推荐 ALLOW_UNSANDBOXED，但执行器仍拒绝（照做无效）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.statistical_analysis import (
    load_experiment_results_with_sources,
    pass_at_k_summary,
)


def _batch(rows_aitester, rows_plain=None):
    return {
        "dataset": "synthetic",
        "results": {
            "aitester": {"details": rows_aitester},
            "plain_llm": {"details": rows_plain if rows_plain is not None else []},
        },
    }


def _row(task_id: str, fixed: str | None, *, correct: bool = True):
    row = {"task_id": task_id, "detection_rate": 1, "patch_correct": correct}
    if fixed is not None:
        row["task_metadata"] = {"fixed": fixed}
    return row


class TestAtomicBatchLoad:
    """F07：失败批次不得留下无来源的前臂。"""

    def test_second_arm_failure_commits_nothing(self, tmp_path: Path):
        payload = {
            "dataset": "synthetic",
            "results": {
                "aitester": {"details": [{"task_id": "t1", "detection_rate": 1}]},
                "plain_llm": None,  # 后一臂坏 → 整批失败
            },
        }
        (tmp_path / "b.json").write_text(json.dumps(payload), encoding="utf-8")

        results, sources = load_experiment_results_with_sources(str(tmp_path), ["b.json"])

        assert results.get("aitester", []) == []
        assert sources == []

    def test_non_list_details_commits_nothing(self, tmp_path: Path):
        payload = {
            "dataset": "synthetic",
            "results": {
                "aitester": {"details": [{"task_id": "t1", "detection_rate": 1}]},
                "plain_llm": {"details": {"not": "a list"}},
            },
        }
        (tmp_path / "b.json").write_text(json.dumps(payload), encoding="utf-8")

        results, sources = load_experiment_results_with_sources(str(tmp_path), ["b.json"])

        assert results.get("aitester", []) == []
        assert sources == []

    def test_healthy_batch_still_loads(self, tmp_path: Path):
        payload = _batch([{"task_id": "t1", "detection_rate": 1}])
        (tmp_path / "b.json").write_text(json.dumps(payload), encoding="utf-8")

        results, sources = load_experiment_results_with_sources(str(tmp_path), ["b.json"])

        assert len(results["aitester"]) == 1
        assert len(sources) == 1


class TestPassAtKIdentity:
    """F06：同一裸 task_id、不同程序 → 不是同题多轮。"""

    def test_same_id_different_program_not_merged(self):
        data = {
            "aitester": [
                _row("task_0000", "def f(a, b):\n    return abs(a - b)\n"),
                _row("task_0000", "def f(n):\n    return n * (n - 1)\n"),
            ]
        }
        summary = pass_at_k_summary(data)["aitester"]

        assert summary["n_tasks"] == 2  # 历史按裸 ID 合并 → 1
        assert summary["rounds_max"] == 1
        assert summary["identity_basis"] == {"content": 2}

    def test_same_program_across_batches_is_rounds(self):
        fixed = "def f(a, b):\n    return abs(a - b)\n"
        data = {
            "aitester": [
                dict(_row("s42__task_0000", fixed), _batch_tag="s42__"),
                dict(_row("s43__task_0000", fixed), _batch_tag="s43__"),
            ]
        }
        summary = pass_at_k_summary(data)["aitester"]

        assert summary["n_tasks"] == 1
        assert summary["rounds_max"] == 2
        assert summary["pass_at"][2] == pytest.approx(1.0)

    def test_missing_content_identity_scoped_to_batch(self):
        data = {
            "aitester": [
                dict(_row("task_0000", None), _batch_tag="batch_a"),
                dict(_row("task_0000", None), _batch_tag="batch_b"),
            ]
        }
        summary = pass_at_k_summary(data)["aitester"]

        assert summary["n_tasks"] == 2  # 跨批同号不再当同题
        assert summary["identity_basis"] == {"batch_scoped": 2}

    def test_loader_same_seed_cross_batch_stays_separate(self, tmp_path: Path):
        """R03（2026-10-23 全量集中复审 P1）：同 seed 异批异题不得合成同题多轮。

        真实例（报告 M07）：seed44 的 t08 gates 批次与主批同为
        synthetic__task_0016 且均无 fixed，pattern/gold 不同——旧加载层
        `_batch_tag = "s44__"` 使 batch_scoped 回退身份相同，pass@k 把两道
        题合成 pass@2。修复后 tag 恒取批次文件身份（目录/stem）。
        """
        from experiments.statistical_analysis import _load_batch_file, pass_at_k_summary

        def _batch_doc(pattern: str) -> dict:
            return {
                "dataset": "synthetic",
                "provenance": {"seed": 44},
                "results": {
                    "aitester": {
                        "details": [
                            {
                                "task_id": "synthetic__task_0016",
                                "detection_rate": 1,
                                "patch_correct": 0,
                                "task_metadata": {"pattern_name": pattern},
                            }
                        ]
                    }
                },
            }

        (tmp_path / "benchmark_a.json").write_text(json.dumps(_batch_doc("three_module_chain")), encoding="utf-8")
        (tmp_path / "benchmark_b.json").write_text(json.dumps(_batch_doc("type_mismatch")), encoding="utf-8")

        results: dict[str, list[dict]] = {"aitester": []}
        for name in ("benchmark_a.json", "benchmark_b.json"):
            assert _load_batch_file(results, tmp_path / name, pool_seeds=True) is True

        rows = results["aitester"]
        # 两行 task_id 的 seed 前缀不变（AB4 分层语义保留），tag 已按批次分开
        assert all(r["task_id"] == "s44__synthetic__task_0016" for r in rows)
        assert len({r["_batch_tag"] for r in rows}) == 2

        summary = pass_at_k_summary(results)["aitester"]
        assert summary["n_tasks"] == 2, "同 seed 跨批异题不得合成同题多轮"
        assert summary["identity_basis"] == {"batch_scoped": 2}


class TestCliJsonErrorLine:
    """F11：异常任务也必须在 JSON 流里有一行。"""

    def test_append_task_error_emits_json(self, capsys):
        from src.cli.app import _append_task_error

        results: list[dict] = []
        _append_task_error("bad.py", "f", RuntimeError("boom"), results, json_output=True)

        out = capsys.readouterr().out.strip()
        payload = json.loads(out)
        assert payload["file"] == "bad.py"
        assert payload["passed"] is False
        assert len(results) == 1

    def test_append_task_error_silent_in_text_mode(self, capsys):
        from src.cli.app import _append_task_error

        results: list[dict] = []
        _append_task_error("bad.py", "f", RuntimeError("boom"), results, json_output=False)

        assert capsys.readouterr().out == ""
        assert len(results) == 1

    def test_parallel_handler_uses_same_contract(self, capsys):
        from src.cli.app import _handle_task_exception

        future = MagicMock()
        future.exception.return_value = RuntimeError("boom")
        results: list[dict] = []
        _handle_task_exception(future, {future: "bad.py"}, None, results, json_output=True)

        assert json.loads(capsys.readouterr().out.strip())["file"] == "bad.py"


class TestReleaseGreenGate:
    """F08：发布绿门必须限定必需工作流与 SHA，且不得自我等待。"""

    def test_gate_targets_ci_workflow_by_sha(self):
        text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

        assert "actions/workflows/ci.yml/runs" in text
        assert "head_sha=${sha}" in text or "head_sha=" in text
        assert "/commits/" not in text  # 旧口径查 commit check-runs（会把自己等进去）
        assert "actions: read" in text
        # 只认 completed+success，且在途继续等待
        assert '"completed"' in text and '"success"' in text


class TestUnsandboxedGuidance:
    """F12：不得再推荐一个无效的"恢复"开关。"""

    def test_env_example_does_not_advertise_recovery(self):
        text = Path(".env.example").read_text(encoding="utf-8")
        assert "ALLOW_UNSANDBOXED=true 时容忍无隔离降级" not in text
        assert "设了也不会让任务跑起来" in text

    def test_executor_message_points_to_real_options(self):
        from src.agents import executor as executor_mod  # noqa: F401

        text = Path("src/agents/executor.py").read_text(encoding="utf-8")
        assert "如需无隔离调试请显式设 ALLOW_UNSANDBOXED" not in text
        assert "EXECUTOR_USE_DOCKER" in text
