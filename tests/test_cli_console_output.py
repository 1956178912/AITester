"""测试 src/cli/app.py 的 _run_single_task 非 JSON 控制台输出路径与 rich 并发进度分支。

此前 cli/app.py 覆盖率 77%，缺失主要集中在：
- _run_single_task 非 JSON 控制台摘要（任务成功/失败 + 诊断 + 建议操作）
- _dispatch_concurrent 的 rich 进度条分支（rich 可用时渲染 Progress）

本文件通过 mock build_workflow / graph.invoke 隔离 LLM 调用，纯验证 CLI 输出行为。
"""

import json
from unittest.mock import MagicMock

from click.testing import CliRunner

from src.cli import app as cli_app


class _FakeFinalState:
    """模拟 graph.invoke 返回的 final_state（dict-like 接口）。"""

    def __init__(self, test_passed: bool, coverage=None, diagnosis=None, error_category=None, iteration=1):
        self._data = {
            "test_passed": test_passed,
            "coverage_report": coverage,
            "diagnosis": diagnosis,
            "error_category": error_category,
            "iteration": iteration,
        }

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        return self._data[key]


class TestRunSingleTaskConsoleOutput:
    """_run_single_task 非 JSON 模式：控制台摘要、成功/失败分支、诊断与建议。"""

    def _make_file(self, tmp_path) -> str:
        p = tmp_path / "calc.py"
        p.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return str(p)

    def _patch_workflow(self, monkeypatch, final_state: _FakeFinalState) -> list:
        """mock build_workflow 返回的 graph，记录 invoke 调用。"""
        invoke_calls = []
        graph = MagicMock()
        graph.invoke.side_effect = lambda state: (invoke_calls.append(state), final_state)[1]
        monkeypatch.setattr(cli_app, "build_workflow", lambda: graph)
        # mock token_usage / trace 避免真实副作用
        monkeypatch.setattr(cli_app.token_usage, "get_usage", lambda: MagicMock(as_dict=lambda: {}))
        monkeypatch.setattr(cli_app, "start_task_trace", lambda *a, **k: None)
        monkeypatch.setattr(cli_app, "end_task_trace", lambda *a, **k: None)
        return invoke_calls

    def test_passed_task_console_summary(self, tmp_path, monkeypatch):
        """测试通过 + 覆盖率达标 → 控制台输出 '✓ 达标' 与 '测试全部通过'。"""
        path = self._make_file(tmp_path)
        fs = _FakeFinalState(test_passed=True, coverage=95.0, iteration=2)
        self._patch_workflow(monkeypatch, fs)

        r = CliRunner().invoke(cli_app.cli, ["run", path, "--max-iterations=3"])
        assert r.exit_code == 0
        assert "任务完成" in r.output
        assert "测试通过：True" in r.output
        assert "✓ 达标" in r.output
        assert "修复迭代：2/3" in r.output
        assert "测试全部通过" in r.output

    def test_failed_task_with_diagnosis_console(self, tmp_path, monkeypatch):
        """测试失败 + 有诊断 + 有错误类型 → 输出根因诊断、错误类型与建议操作。"""
        path = self._make_file(tmp_path)
        fs = _FakeFinalState(
            test_passed=False,
            coverage=40.0,
            diagnosis="除零错误：divide 未处理 b=0",
            error_category="runtime",
            iteration=3,
        )
        self._patch_workflow(monkeypatch, fs)

        r = CliRunner().invoke(cli_app.cli, ["run", path, "--max-iterations=3"])
        assert r.exit_code == 1, "失败任务应 exit 1"
        assert "测试未通过" in r.output
        assert "✗ 未达标" in r.output
        assert "根因诊断：除零错误" in r.output
        assert "错误类型：runtime" in r.output
        assert "建议操作" in r.output

    def test_failed_task_without_coverage(self, tmp_path, monkeypatch):
        """覆盖率数据缺失（None）→ 摘要不输出覆盖率行（'N/A' 逻辑由 coverage is None 控制）。"""
        path = self._make_file(tmp_path)
        fs = _FakeFinalState(test_passed=False, coverage=None, iteration=1)
        self._patch_workflow(monkeypatch, fs)

        r = CliRunner().invoke(cli_app.cli, ["run", path])
        assert r.exit_code == 1
        # 覆盖率缺失时摘要不含 '覆盖率：' 行
        assert "覆盖率：" not in r.output
        assert "修复迭代：1" in r.output

    def test_json_output_is_pure_json(self, tmp_path, monkeypatch):
        """--json 模式 stdout 只含 JSON（可被 json.loads 解析）。"""
        path = self._make_file(tmp_path)
        fs = _FakeFinalState(test_passed=True, coverage=88.0, iteration=1)
        self._patch_workflow(monkeypatch, fs)

        r = CliRunner().invoke(cli_app.cli, ["run", path, "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["passed"] is True
        assert data["file"] == path

    def test_func_shown_in_summary(self, tmp_path, monkeypatch):
        """指定 --func 时摘要输出 '被测函数：divide'。"""
        path = self._make_file(tmp_path)
        fs = _FakeFinalState(test_passed=True, iteration=1)
        self._patch_workflow(monkeypatch, fs)

        r = CliRunner().invoke(cli_app.cli, ["run", path, "--func", "add"])
        assert "被测函数：add" in r.output


class TestDispatchConcurrentRichBranch:
    """_dispatch_concurrent 的 rich 进度条分支（rich 可用时走 Progress 渲染）。"""

    def test_rich_progress_path_invokes_dispatch(self, tmp_path, monkeypatch):
        """rich 可用 → 走 Progress 分支，任务仍经 _dispatch_parallel_tasks 完成。"""
        p = tmp_path / "m.py"
        p.write_text("def f():\n    return 1\n", encoding="utf-8")
        dispatched = []
        results = [{"success": True, "file": str(p), "func": "all", "passed": True}]

        def fake_dispatch(**kwargs):
            dispatched.append(kwargs)
            assert kwargs["results"] is results

        # rich 可用（真实环境）+ 拦截最底层派发器验证调用链
        monkeypatch.setattr(cli_app, "_dispatch_parallel_tasks", fake_dispatch)
        # 直接调用 _dispatch_concurrent，验证 rich 分支走通（rich 实际可用）
        cli_app._dispatch_concurrent(
            [str(p)],
            func=None,
            max_iterations=1,
            exec_timeout=10,
            coverage_threshold=80.0,
            json_output=False,
            parallel=2,
            results=results,
        )
        assert len(dispatched) == 1
        assert dispatched[0]["parallel"] == 2

    def test_text_fallback_path_with_rich_unavailable(self, tmp_path, monkeypatch):
        """rich 不可用 → 降级纯文本路径，on_success 回调被设置。"""
        p = tmp_path / "m.py"
        p.write_text("def f():\n    return 1\n", encoding="utf-8")
        dispatched = []

        def fake_dispatch(**kwargs):
            dispatched.append(kwargs)

        monkeypatch.setattr(cli_app, "_dispatch_parallel_tasks", fake_dispatch)
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)
        results = []
        cli_app._dispatch_concurrent(
            [str(p)],
            func=None,
            max_iterations=1,
            exec_timeout=10,
            coverage_threshold=80.0,
            json_output=False,
            parallel=2,
            results=results,
        )
        assert len(dispatched) == 1
        # 非 JSON 模式下纯文本降级应注入 on_success 回调（非 None）
        assert dispatched[0].get("on_success") is not None

    def test_text_fallback_json_mode_silent(self, tmp_path, monkeypatch):
        """rich 不可用 + --json → on_success 为 None（保持 stdout 纯 JSON）。"""
        p = tmp_path / "m.py"
        p.write_text("def f():\n    return 1\n", encoding="utf-8")
        dispatched = []

        def fake_dispatch(**kwargs):
            dispatched.append(kwargs)

        monkeypatch.setattr(cli_app, "_dispatch_parallel_tasks", fake_dispatch)
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)
        cli_app._dispatch_concurrent(
            [str(p)],
            func=None,
            max_iterations=1,
            exec_timeout=10,
            coverage_threshold=80.0,
            json_output=True,
            parallel=2,
            results=[],
        )
        assert dispatched[0].get("on_success") is None
