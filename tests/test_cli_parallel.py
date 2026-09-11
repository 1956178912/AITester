"""
CLI 并发派发回归测试：锁定 _dispatch_parallel_tasks 与 run 并发分支行为。

回归背景（0.9.10 批次）：
- 此前 rich 进度条模式与纯文本降级模式各维护一份"future 提交 + as_completed 汇总"
  同构代码块（约 30 行重复），合并为共享派发器 _dispatch_parallel_tasks 后，
  本文件补齐并发路径的回归护栏：
  1. 全部成功 → 结果按 as_completed 顺序入 results；
  2. 单任务异常 → _handle_task_exception 追加错误结果，整批不中断；
  3. on_success / on_progress 回调触发时机（成功 basename / 每个任务结束）；
  4. run 命令 --parallel>1 多文件在 rich 可用与不可用两条路径下的端到端行为。
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from click.testing import CliRunner

from src.cli import app as cli_app


def _make_files(tmp_path, count: int = 2) -> list[str]:
    """创建 count 个简单被测文件，返回路径列表。"""
    files = []
    for i in range(count):
        f = tmp_path / f"mod_{i}.py"
        f.write_text(f"def add_{i}(a, b):\n    return a + b\n", encoding="utf-8")
        files.append(str(f))
    return files


def _mock_task_result(file_stem: str) -> dict:
    """构造与 _run_single_task 正常返回同构的成功结果字典。"""
    return {
        "success": True,
        "file": f"/x/{file_stem}.py",
        "func": "all",
        "passed": True,
        "coverage": 90.0,
        "coverage_threshold": 80.0,
        "coverage_ok": True,
        "iterations": 1,
        "max_iterations": 3,
        "diagnosis": None,
        "error_category": None,
    }


class TestDispatchParallelTasks:
    """_dispatch_parallel_tasks 共享派发器单元测试。"""

    def test_all_success_appends_results(self, tmp_path):
        """全部成功：results 收到每个任务一个结果，数量与目标文件一致。"""
        files = _make_files(tmp_path, 3)
        results: list[dict] = []

        with patch.object(
            cli_app,
            "_run_single_task",
            side_effect=lambda target_file, *a, **kw: _mock_task_result(os.path.basename(target_file)[:-3]),
        ):
            cli_app._dispatch_parallel_tasks(
                expanded_files=files,
                func=None,
                max_iterations=3,
                exec_timeout=30,
                coverage_threshold=80.0,
                json_output=True,
                parallel=2,
                results=results,
            )

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert {r["file"] for r in results} == {f"/x/{os.path.basename(f)[:-3]}.py" for f in files}

    def test_single_task_failure_does_not_stop_batch(self, tmp_path):
        """单任务异常：错误结果经 _handle_task_exception 追加，其余任务正常完成。"""
        files = _make_files(tmp_path, 2)
        bad, good = files

        def fake_task(target_file, *args, **kwargs):
            if target_file == bad:
                raise RuntimeError("boom")
            r = _mock_task_result(os.path.basename(target_file)[:-3])
            r["file"] = target_file  # 与 _make_task_error_result 同口径（真实路径），便于按 file 汇总
            return r

        results: list[dict] = []
        with patch.object(cli_app, "_run_single_task", side_effect=fake_task):
            cli_app._dispatch_parallel_tasks(
                expanded_files=files,
                func="divide",
                max_iterations=3,
                exec_timeout=30,
                coverage_threshold=80.0,
                json_output=True,
                parallel=2,
                results=results,
            )

        assert len(results) == 2
        by_file = {r["file"]: r for r in results}
        assert by_file[bad]["success"] is False
        assert by_file[bad]["passed"] is False
        assert "boom" in by_file[bad]["error"]
        assert by_file[good]["success"] is True

    def test_on_success_receives_basename(self, tmp_path):
        """on_success 回调仅在任务成功时触发，且传入文件 basename。"""
        files = _make_files(tmp_path, 2)
        seen: list[str] = []
        results: list[dict] = []

        with patch.object(
            cli_app,
            "_run_single_task",
            side_effect=lambda target_file, *a, **kw: _mock_task_result(os.path.basename(target_file)[:-3]),
        ):
            cli_app._dispatch_parallel_tasks(
                expanded_files=files,
                func=None,
                max_iterations=3,
                exec_timeout=30,
                coverage_threshold=80.0,
                json_output=False,
                parallel=2,
                results=results,
                on_success=seen.append,
            )

        assert sorted(seen) == sorted(os.path.basename(f) for f in files)

    def test_on_progress_fires_per_task_including_failures(self, tmp_path):
        """on_progress 每个任务结束（无论成败）触发一次，共 len(files) 次。"""
        files = _make_files(tmp_path, 3)
        progress_calls = []
        results: list[dict] = []

        def fake_task(target_file, *args, **kwargs):
            if "mod_1" in target_file:
                raise RuntimeError("boom")
            return _mock_task_result(os.path.basename(target_file)[:-3])

        with patch.object(cli_app, "_run_single_task", side_effect=fake_task):
            cli_app._dispatch_parallel_tasks(
                expanded_files=files,
                func=None,
                max_iterations=3,
                exec_timeout=30,
                coverage_threshold=80.0,
                json_output=True,
                parallel=2,
                results=results,
                on_progress=lambda _f: progress_calls.append(1),
            )

        assert len(progress_calls) == 3
        assert len(results) == 3


class TestHandleTaskException:
    """_handle_task_exception 直接回归。"""

    def test_appends_error_result_with_masked_text(self):
        """异常 future 追加 success=False 结果，error 文本经脱敏。

        脱敏规则：`sk-` 后接 20+ 位字母数字才命中（logging_utils._SENSITIVE_PATTERNS），
        故用足长度的假 key 验证替换为占位符。
        """
        results: list[dict] = []
        future = MagicMock()
        future_to_file = {future: "/tmp/calc.py"}
        # sk- + 24 位字母数字，满足 {20,} 正则
        fake_key = "sk-abc123def456ghi789jkl012"
        future.exception.return_value = RuntimeError(f"{fake_key} 失效")

        cli_app._handle_task_exception(future, future_to_file, "divide", results)

        assert len(results) == 1
        r = results[0]
        assert r["success"] is False and r["passed"] is False
        assert r["file"] == "/tmp/calc.py" and r["func"] == "divide"
        assert fake_key not in r["error"]

    def test_error_result_shape_matches_success_result(self):
        """异常结果与正常结果同构：成功结果有的判定键，异常结果也都有。"""
        results: list[dict] = []
        future = MagicMock()
        future_to_file = {future: "f.py"}
        future.exception.return_value = None

        cli_app._handle_task_exception(future, future_to_file, None, results)

        r = results[0]
        # _make_task_error_result 的最小键集
        assert {"success", "file", "func", "passed", "error"} <= r.keys()
        assert r["error"] == "unknown error"
        assert r["func"] == "all"


class TestRunParallelBranches:
    """run 命令 --parallel>1 多文件端到端（mock 工作流，覆盖 rich/非rich 双路径）。"""

    def _setup_graph_mock(self) -> MagicMock:
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "test_passed": True,
            "coverage_report": 90.0,
            "iteration": 1,
            "diagnosis": None,
            "error_category": None,
        }
        return mock_graph

    def test_run_parallel_rich_available(self, tmp_path):
        """rich 可用路径：--parallel=2 走进度条分支，两文件都成功、exit 0。"""
        files = _make_files(tmp_path, 2)
        runner = CliRunner()
        with (
            patch("src.cli.app.build_workflow", return_value=self._setup_graph_mock()),
            patch.object(cli_app, "_rich_available", return_value=True),
        ):
            result = runner.invoke(cli_app.cli, ["run", files[0], files[1], "--parallel", "2", "--json"])
        assert result.exit_code == 0, result.output
        # 两个任务各输出一份 JSON 结果，均 passed
        assert result.output.count('"passed": true') == 2

    def test_run_parallel_no_rich(self, tmp_path):
        """无 rich 降级路径：--parallel=2 走纯文本分支，两文件都成功、exit 0。"""
        files = _make_files(tmp_path, 2)
        runner = CliRunner()
        with (
            patch("src.cli.app.build_workflow", return_value=self._setup_graph_mock()),
            patch.object(cli_app, "_rich_available", return_value=False),
        ):
            result = runner.invoke(cli_app.cli, ["run", files[0], files[1], "--parallel", "2", "--json"])
        assert result.exit_code == 0, result.output

    def test_run_parallel_single_file_falls_back_to_sequential(self, tmp_path):
        """--parallel>1 但仅 1 个文件：不进入并发分支，顺序执行同样成功。"""
        files = _make_files(tmp_path, 1)
        runner = CliRunner()
        with (
            patch("src.cli.app.build_workflow", return_value=self._setup_graph_mock()),
            patch.object(cli_app, "_rich_available", return_value=False),
        ):
            result = runner.invoke(cli_app.cli, ["run", files[0], "--parallel", "2", "--json"])
        assert result.exit_code == 0, result.output

    def test_run_parallel_failure_exits_nonzero(self, tmp_path):
        """并发分支下任一任务未通过 → exit 1（CI 门控语义，0.9.6 引入，并发路径回归护栏）。"""
        files = _make_files(tmp_path, 2)
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "test_passed": False,
            "coverage_report": None,
            "iteration": 3,
            "diagnosis": None,
            "error_category": None,
        }
        runner = CliRunner()
        with (
            patch("src.cli.app.build_workflow", return_value=mock_graph),
            patch.object(cli_app, "_rich_available", return_value=False),
        ):
            result = runner.invoke(cli_app.cli, ["run", files[0], files[1], "--parallel", "2", "--json"])
        assert result.exit_code == 1
