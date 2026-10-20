"""覆盖率补口：`executor_runtime.py` 的探测失败与观测边界（2026-10-19）。

目标：模块可导入性探测的三条失败通道（进程内 find_spec 异常、子进程
非零退出 / 无输出 / 输出不可解析）、能力检查在"不需要覆盖率插件"时的
最小依赖集、解释器定位的非字符串 token / PATH 解析，以及临时文件清理
失败不抛出。全部为纯本地/替身路径，不启动真实子进程。
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from src.agents import executor_runtime as rt
from src.utils.process_utils import CompletedProcess


def _completed(returncode: int = 0, *, stdout: str = "", stderr: str = "") -> CompletedProcess:
    return CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr)


class TestToStr:
    def test_bytes_are_decoded(self) -> None:
        assert rt._to_str(b"abc") == "abc"

    def test_none_is_empty(self) -> None:
        assert rt._to_str(None) == ""


class TestObservedFailThenPass:
    def test_non_dict_entries_are_skipped(self) -> None:
        """记录序列混入非 dict（旧工件/损坏数据）时保守跳过，不臆测。"""
        assert rt.observed_fail_then_pass([None, {"passed": True}]) is False

    def test_failure_then_pass_is_detected(self) -> None:
        assert rt.observed_fail_then_pass([{"passed": False}, {"passed": True}]) is True


class TestProbeModulesInProcess:
    def test_find_spec_exception_marks_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(_name: str) -> None:
            raise ImportError("boom")

        monkeypatch.setattr(importlib.util, "find_spec", _raise)
        assert rt._probe_modules_in_process(("x",)) == {"x": False}


class TestProbeModulesSubprocess:
    def test_nonzero_exit_reports_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rt.subprocess, "run", lambda *_a, **_k: _completed(1, stderr="boom"))
        modules, error = rt._probe_modules_subprocess(sys.executable, ("pytest",))
        assert modules is None
        assert error == "exit 1: boom"

    def test_empty_stdout_reports_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rt.subprocess, "run", lambda *_a, **_k: _completed(0, stdout=""))
        modules, error = rt._probe_modules_subprocess(sys.executable, ("pytest",))
        assert modules is None
        assert error == "probe 无输出"

    def test_unparseable_stdout_reports_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rt.subprocess, "run", lambda *_a, **_k: _completed(0, stdout="not-json"))
        modules, error = rt._probe_modules_subprocess(sys.executable, ("pytest",))
        assert modules is None
        assert error is not None and error.startswith("probe 输出不可解析")

    def test_non_dict_stdout_reports_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rt.subprocess, "run", lambda *_a, **_k: _completed(0, stdout="[1]"))
        modules, error = rt._probe_modules_subprocess(sys.executable, ("pytest",))
        assert modules is None
        assert error == "probe 输出结构非法"

    def test_valid_payload_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rt.subprocess, "run", lambda *_a, **_k: _completed(0, stdout='{"pytest": true}'))
        assert rt._probe_modules_subprocess(sys.executable, ("pytest",)) == ({"pytest": True}, None)


class TestExecutionCapability:
    def test_without_coverage_requires_only_pytest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rt.clear_execution_capability_cache()
        monkeypatch.setattr(rt, "_probe_interpreter_modules", lambda *_a, **_k: ({"pytest": True}, None))
        try:
            capability = rt.check_execution_capability(
                interpreter=sys.executable,
                require_coverage=False,
                require_timeout_plugin=False,
            )
        finally:
            rt.clear_execution_capability_cache()
        assert capability["required_modules"] == ["pytest"]
        assert capability["available"] is True
        assert capability["probe"] == "in_process"


class TestCommandPythonInterpreter:
    def test_non_string_token_skipped_and_relative_python_resolved(self) -> None:
        resolved = shutil.which("python3")
        if resolved is None:
            pytest.skip("python3 不在 PATH，无法覆盖相对路径解析分支")
        assert rt._command_python_interpreter([123, "python3"]) == resolved


class TestCleanupTempFile:
    def test_unlink_oserror_is_logged_not_raised(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        target.write_text("x", encoding="utf-8")

        def _raise(_path: str) -> None:
            raise OSError("boom")

        monkeypatch.setattr(rt.os, "unlink", _raise)
        rt.cleanup_temp_file(str(target))
        # 清理失败必须静默降级：不抛出且不误删（os.unlink 已被替换为抛错）
        assert target.exists()
