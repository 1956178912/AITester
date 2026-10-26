"""DS 轮：任务崩溃路径的结果面必须与成功路径同构，且人读模式必须披露原因。

修复前实测（2026-10-26，零 LLM）::

    python3 main.py run /tmp/bad_encoding.py --json
    {
      "success": false,
      "file": "/tmp/bad_encoding.py",
      "func": "all",
      "passed": false,
      "error": "'utf-8' codec can't decode byte 0xff in position 21: invalid start byte"
    }

成功路径同一份 JSON 有 14 个键（含 ``coverage`` / ``coverage_threshold`` /
``coverage_ok`` / ``iterations`` / ``max_iterations`` / ``diagnosis`` /
``error_category`` / ``event_bus`` / ``cost_budget`` / ``semantic_cache``），
崩溃行只有 5 个——``jq '.coverage_ok'`` 在崩溃任务上取不到键，而
``docs/api_reference.md`` 承诺 ``--json`` 逐任务结果「含 coverage_ok」。

人读模式更糟：崩溃任务只在表格里留一行 ``✗ … coverage=N/A 迭代 0``，原因只进
``aitester.log``；stderr 只有 ``⚠ 1/1 个测试失败``，操作者无法从终端知道为什么
失败（且「迭代 0」是缺键兜底，不代表真实迭代数）。

口径：崩溃结果与成功结果键集合逐键相同（未知判定值显式为 null），人读模式下
原因写 stderr（stdout 仍只承载表格）；``--json`` 模式下 stdout 仍只承载 JSON。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from src.cli import app as cli_app
from src.cli.output import print_rich_table


def _invoke(*args: str):
    return CliRunner().invoke(cli_app.cli, list(args))


def _ok_file(tmp_path):
    path = tmp_path / "ok.py"
    path.write_text("def f():\n    return 1\n", encoding="utf-8")
    return path


def _bad_file(tmp_path):
    path = tmp_path / "bad_encoding.py"
    path.write_bytes(b'def f():\n    return "\xff\xfe"\n')
    return path


def _graph_mock() -> MagicMock:
    graph = MagicMock()
    graph.invoke.return_value = {
        "test_passed": True,
        "coverage_report": 90.0,
        "iteration": 1,
        "diagnosis": None,
        "error_category": None,
    }
    return graph


def _success_payload(tmp_path) -> dict:
    with patch("src.cli.app.build_workflow", return_value=_graph_mock()):
        result = _invoke("run", str(_ok_file(tmp_path)), "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _error_payload(tmp_path, *extra: str) -> dict:
    result = _invoke("run", str(_bad_file(tmp_path)), "--json", *extra)
    assert result.exit_code == 1, result.output
    return json.loads(result.output)


class TestErrorJsonIsomorphic:
    def test_key_set_equals_success_path(self, tmp_path):
        success = _success_payload(tmp_path)
        error = _error_payload(tmp_path)
        assert set(error) == set(success)
        assert error["error"]

    def test_unknown_judgments_are_explicit_null(self, tmp_path):
        error = _error_payload(tmp_path)
        assert error["success"] is False
        assert error["passed"] is False
        for key in (
            "coverage",
            "coverage_ok",
            "iterations",
            "diagnosis",
            "error_category",
            "event_bus",
            "cost_budget",
            "semantic_cache",
        ):
            assert error[key] is None, key

    def test_cli_thresholds_are_carried(self, tmp_path):
        error = _error_payload(tmp_path, "--coverage-threshold", "91.5", "--max-iterations", "7")
        assert error["coverage_threshold"] == 91.5
        assert error["max_iterations"] == 7


class TestErrorBuilderContract:
    def test_defaults_for_unknown_unknowns(self):
        result = cli_app._make_task_error_result("x.py", None, None)
        assert result["file"] == "x.py"
        assert result["func"] == "all"
        assert result["error"] == "unknown error"
        assert result["coverage_threshold"] is None
        assert result["max_iterations"] is None

    def test_success_path_declares_error_key(self, tmp_path):
        success = _success_payload(tmp_path)
        assert success.get("error", "missing") is None


class TestHumanModeDisclosesCrashReason:
    def test_stderr_has_reason_and_stdout_has_summary(self, tmp_path):
        result = _invoke("run", str(_bad_file(tmp_path)))
        assert result.exit_code == 1, result.output
        assert "任务执行异常" in result.stderr
        assert "codec" in result.stderr
        assert "批量测试完成" in result.stdout
        assert "任务执行异常" not in result.stdout

    def test_append_task_error_keeps_stdout_clean(self, capsys):
        results: list[dict] = []
        cli_app._append_task_error("bad.py", None, RuntimeError("boom"), results, json_output=False)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "任务执行异常" in captured.err
        assert "boom" in captured.err
        assert results[0]["coverage_ok"] is None

    def test_parallel_dispatch_propagates_thresholds(self, monkeypatch, capsys):
        def _boom(*_args, **_kwargs):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(cli_app, "_run_single_task", _boom)
        results: list[dict] = []
        cli_app._dispatch_parallel_tasks(
            expanded_files=["a.py"],
            func=None,
            max_iterations=6,
            exec_timeout=30,
            coverage_threshold=72.5,
            json_output=False,
            parallel=1,
            results=results,
        )
        assert results[0]["coverage_threshold"] == 72.5
        assert results[0]["max_iterations"] == 6
        assert "kaboom" in capsys.readouterr().err


class TestRichTableUnknownIterations:
    def test_none_iterations_renders_na(self, capsys):
        print_rich_table([{"passed": False, "file": "a.py", "func": "all", "coverage": 0.0, "iterations": None}])
        out = capsys.readouterr().out
        assert "N/A" in out
        assert "None" not in out
