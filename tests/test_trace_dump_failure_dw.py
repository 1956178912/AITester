"""DW 轮锁：``dump_recent_to`` / ``--dump-trace-on-failure`` 的失败态。

历史行为（改前实测）：
1. ``dump_recent_to`` 的 ``os.makedirs`` 在 ``try`` 之外——目标路径的父级是普通
   文件或不可写时抛 ``NotADirectoryError`` / ``PermissionError``，与 docstring
   「创建失败返回 None」相反；
2. CLI 在任务结果构造之后才调用诊断出口，异常冒泡到任务层 → **已完成的任务**
   被 ``_append_task_error`` 改写成「任务崩溃」，主流程被诊断出口反噬；
3. 无快照可写与写盘失败都只返回 ``None``，CLI 静默，用户显式要求诊断导出却
   既拿不到文件也看不到原因；
4. 崩溃任务（graph.invoke 抛异常）走的异常分支从不尝试导出——恰在最需要诊断
   时该开关不生效。

本文件锁死修复后的契约：三态可区分（成功 / 无快照 / 写盘失败），失败只披露、
不改变任务结果，崩溃路径同样尝试导出。
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from src.observability.trace import (
    dump_recent_to,
    dump_recent_to_with_reason,
    memory_buffer_snapshot,
    reset_memory_buffer,
)


@pytest.fixture(autouse=True)
def _clean_memory_buffer():
    reset_memory_buffer()
    yield
    reset_memory_buffer()


def _block_target_dir(tmp_path) -> str:
    """把 ``tmp_path/tmp_trace`` 占为普通文件，使 makedirs 必然失败。"""
    blocked = tmp_path / "tmp_trace"
    blocked.write_text("not a directory", encoding="utf-8")
    return str(blocked / "sub")


class TestDumpRecentToFailureStates:
    def test_parent_is_file_returns_none_instead_of_raising(self, tmp_path):
        """docstring 承诺「创建失败返回 None」：父级是普通文件时不得抛异常。"""
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])

        assert dump_recent_to(_block_target_dir(tmp_path)) is None

    def test_reason_reports_write_failure_when_dir_cannot_be_created(self, tmp_path):
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])

        path, reason = dump_recent_to_with_reason(_block_target_dir(tmp_path))

        assert path is None
        assert reason is not None and "写盘失败" in reason

    def test_reason_reports_empty_buffer_without_claiming_write_failure(self, tmp_path):
        path, reason = dump_recent_to_with_reason(str(tmp_path / "tmp_trace"))

        assert path is None
        assert reason is not None and "无快照可写" in reason
        assert "写盘失败" not in reason

    def test_success_reports_path_and_no_reason(self, tmp_path):
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])

        path, reason = dump_recent_to_with_reason(str(tmp_path / "tmp_trace"))

        assert path is not None and os.path.exists(path)
        assert reason is None


class TestCliDumpFailureDisclosure:
    def test_blocked_dir_returns_reason_and_warns_on_stderr(self, tmp_path, monkeypatch, capsys):
        """写盘失败 → 返回原因、stderr 披露、stdout 不被污染（JSON 模式下）。"""
        from src.cli import app as cli_app

        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tmp_trace").write_text("not a directory", encoding="utf-8")

        path, error = cli_app._dump_trace_on_failure(output_json=True)

        assert path is None
        assert error is not None and "写盘失败" in error
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "失败追踪快照未写入" in captured.err

    def test_empty_buffer_is_disclosed_not_silent(self, tmp_path, monkeypatch, capsys):
        from src.cli import app as cli_app

        monkeypatch.chdir(tmp_path)

        path, error = cli_app._dump_trace_on_failure(output_json=False)

        assert path is None
        assert error is not None and "无快照可写" in error
        captured = capsys.readouterr()
        assert "失败追踪快照未写入" in captured.err

    def test_success_keeps_non_json_hint_on_stdout(self, tmp_path, monkeypatch, capsys):
        from src.cli import app as cli_app

        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])
        monkeypatch.chdir(tmp_path)

        path, error = cli_app._dump_trace_on_failure(output_json=False)

        assert path is not None and error is None
        captured = capsys.readouterr()
        assert "诊断追踪" in captured.out
        assert captured.err == ""


class _FakeGraph:
    def __init__(self, *, test_passed: bool = False, exc: BaseException | None = None) -> None:
        self._test_passed = test_passed
        self._exc = exc

    def invoke(self, state):
        if self._exc is not None:
            raise self._exc
        state["test_passed"] = self._test_passed
        state["iteration"] = 1
        state["diagnosis"] = None
        return state


class TestTaskResultSurvivesDumpFailure:
    def test_failed_task_keeps_result_when_dump_dir_blocked(self, tmp_path, monkeypatch):
        """诊断写盘失败不得把「任务已跑完」改写成「任务崩溃」。"""
        from src.cli import app as cli_app

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tmp_trace").write_text("not a directory", encoding="utf-8")
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])
        monkeypatch.setattr(cli_app, "build_workflow", lambda: _FakeGraph(test_passed=False))

        result = cli_app._run_single_task(
            target_file=str(target),
            func=None,
            max_iterations=1,
            timeout=30,
            coverage_threshold=80.0,
            output_json=True,
            dump_trace_on_failure=True,
        )

        assert result["success"] is True, "任务结果不得被诊断出口失败改写"
        assert result["passed"] is False
        assert "trace_dump_path" not in result
        assert "写盘失败" in result["trace_dump_error"]

    def test_crashed_task_attempts_dump_and_reports_reason(self, tmp_path, monkeypatch):
        """崩溃路径同样尝试导出：错误结果携带 trace_dump_error，JSON 单文档可解析。"""
        from src.cli import app as cli_app

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tmp_trace").write_text("not a directory", encoding="utf-8")
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])
        monkeypatch.setattr(cli_app, "_run_single_task", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

        r = CliRunner().invoke(cli_app.cli, ["run", str(target), "--json", "--dump-trace-on-failure"])

        assert r.exit_code == 1, r.output
        payload = json.loads(r.stdout)
        assert payload["error"] == "boom"
        assert payload["passed"] is False
        assert "写盘失败" in payload["trace_dump_error"]
        assert "trace_dump_path" not in payload
        assert "失败追踪快照未写入" in r.stderr
