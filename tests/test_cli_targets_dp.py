"""DP 轮（2026-10-26）`run` 的目标文件面：目录目标与重复目标。

修复前实测：
- ``python main.py run <目录> --json`` 退出 1，输出 ``"success": false`` 与
  ``[Errno 21] Is a directory``——把用法错误伪装成「任务失败」，与 DK 轮
  「无有效目标 ⇒ rc=2」的口径矛盾；
- ``_expand_target_files(("examples/*.py", "examples/calculator.py"))`` 返回 7 项，
  ``calculator.py`` 出现两次；重复目标会重复进入工作流、重复消耗 LLM；
- 显式目录 ``examples`` 被 ``glob.glob`` 原样命中并直接收下，目录与普通文件
  在展开阶段没有被区分。

本轮口径：显式目录 / 非普通文件与「通配符只匹配到目录」按用法错误 rc=2 拒绝且
不启动任何任务；glob 命中的目录静默过滤；同一文件（绝对路径口径）只跑一次。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeFinalState:
    def __init__(self, test_passed: bool, coverage: float | None = 100.0, iteration: int = 1):
        self._data = {
            "test_passed": test_passed,
            "coverage_report": coverage,
            "diagnosis": None,
            "error_category": None,
            "iteration": iteration,
        }

    def get(self, key, default=None):
        return self._data.get(key, default)


def _patch_workflow(monkeypatch, calls: list[str]) -> None:
    graph = MagicMock()

    def _invoke(state):
        calls.append(state["target_file"])
        return _FakeFinalState(True)

    graph.invoke.side_effect = _invoke
    monkeypatch.setattr(cli_app, "build_workflow", lambda: graph)
    monkeypatch.setattr(cli_app.token_usage, "get_usage", lambda: MagicMock(as_dict=lambda: {}))
    monkeypatch.setattr(cli_app, "start_task_trace", lambda *a, **k: None)
    monkeypatch.setattr(cli_app, "end_task_trace", lambda *a, **k: None)


def _write(path: Path, name: str) -> str:
    target = path / name
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    return str(target)


def _invoke(args: list[str]):
    return CliRunner().invoke(cli_app.cli, args)


def _text(result) -> str:
    return result.output + getattr(result, "stderr", "")


class TestDirectoryTargetsRejected:
    def test_explicit_directory_is_usage_error(self, monkeypatch, tmp_path):
        calls: list[str] = []
        _patch_workflow(monkeypatch, calls)
        r = _invoke(["run", str(tmp_path)])
        assert r.exit_code == 2, _text(r)
        assert "目标不是普通文件" in _text(r)
        assert calls == [], "用法错误必须在启动任何任务之前拒绝"
        assert "开始执行测试任务" not in r.output

    def test_directory_aborts_whole_batch_before_running_files(self, monkeypatch, tmp_path):
        calls: list[str] = []
        _patch_workflow(monkeypatch, calls)
        target = _write(tmp_path, "ok.py")
        r = _invoke(["run", str(tmp_path), target])
        assert r.exit_code == 2, _text(r)
        assert calls == []

    def test_glob_matching_only_directories_is_usage_error(self, tmp_path, capsys):
        (tmp_path / "sub").mkdir()
        with pytest.raises(SystemExit) as exc_info:
            cli_app._expand_target_files((str(tmp_path / "*"),))
        assert exc_info.value.code == 2
        assert "模式只匹配到目录或非普通文件" in capsys.readouterr().err

    def test_glob_skips_directories_but_keeps_files(self, tmp_path):
        (tmp_path / "sub").mkdir()
        target = _write(tmp_path, "a.py")
        assert cli_app._expand_target_files((str(tmp_path / "*"),)) == [target]


class TestDuplicateTargets:
    def test_duplicate_explicit_target_runs_once(self, monkeypatch, tmp_path):
        calls: list[str] = []
        _patch_workflow(monkeypatch, calls)
        target = _write(tmp_path, "a.py")
        r = _invoke(["run", target, target])
        assert r.exit_code == 0, _text(r)
        assert calls == [target]
        assert "总计：1 个文件" in r.output

    def test_glob_and_explicit_overlap_deduplicates(self, tmp_path):
        first = _write(tmp_path, "a.py")
        second = _write(tmp_path, "b.py")
        assert sorted(cli_app._expand_target_files((str(tmp_path / "*.py"), first))) == sorted([first, second])

    def test_repeated_target_among_several_runs_once(self, monkeypatch, tmp_path):
        calls: list[str] = []
        _patch_workflow(monkeypatch, calls)
        first = _write(tmp_path, "a.py")
        second = _write(tmp_path, "b.py")
        r = _invoke(["run", first, second, first])
        assert r.exit_code == 0, _text(r)
        assert sorted(calls) == sorted([first, second])
        assert "总计：2 个文件" in r.output

    def test_same_file_via_relative_and_absolute_runs_once(self, monkeypatch, tmp_path):
        calls: list[str] = []
        _patch_workflow(monkeypatch, calls)
        target = _write(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        r = _invoke(["run", "a.py", target])
        assert r.exit_code == 0, _text(r)
        assert len(calls) == 1, calls


class TestDocumentedTargetSemantics:
    def test_run_help_states_file_only_and_dedup(self):
        out = _invoke(["run", "--help"]).output
        assert "普通文件" in out
        assert "只跑一次" in out

    def test_api_reference_zh_documents_target_semantics(self):
        text = (PROJECT_ROOT / "docs/api_reference.md").read_text(encoding="utf-8")
        assert "普通文件" in text
        assert "只跑一次" in text

    def test_api_reference_en_documents_target_semantics(self):
        text = (PROJECT_ROOT / "docs/api_reference.en.md").read_text(encoding="utf-8")
        assert "regular files" in text
        assert "run once" in text
