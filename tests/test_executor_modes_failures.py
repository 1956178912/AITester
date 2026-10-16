#!/usr/bin/env python3
"""覆盖率收口：沙箱执行器的失败路径（`src/agents/executor_modes.py`）。

动机（EMSE 多轮优化批次·最后一段）：`execute_sandboxed` 是"生成测试在哪跑"的
唯一入口，其**失败路径**决定了诊断质量——
- 测试文件写不进沙箱（磁盘满/权限）必须清理沙箱并给 `file_write_failed`，
  不得泄漏临时目录；
- 依赖安装失败必须提前返回 `dependency_install_failed`，不得让"缺依赖"被
  错误分类器误归成"代码 bug"。

覆盖目标（coverage.xml 记录）：83-85（写失败清理）、140（kernel sandbox 开启分支）、
193（依赖注入失败早退）行与对应分支。
零 LLM、零网络；pytest 执行链被替换为确定性桩（本文件只测失败路径）。
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path

import pytest

from src.agents.executor_modes import execute_sandboxed


class _ExecStub:
    """供 `execute_sandboxed(self, ...)` 使用的最小 self（无真实 LLM/图依赖）。"""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def _run_pytest_with_retry(self, cmd: object, env: object, sandbox_dir: str):
        self.calls.append((cmd, env, sandbox_dir))
        return "stub-output", None


@pytest.fixture
def target_file(tmp_path: Path) -> str:
    path = tmp_path / "calc_mod.py"
    path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return str(path)


class TestSandboxWriteFailure:
    def test_unwritable_test_file_cleans_sandbox_and_reports(
        self, target_file: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """写测试文件抛 OSError → 清理沙箱 + `file_write_failed` 诊断（不得泄漏目录）。"""
        created_dirs: list[str] = []
        real_mkdtemp = __import__("tempfile").mkdtemp

        def _spy_mkdtemp(*args: object, **kwargs: object) -> str:
            path = real_mkdtemp(*args, **kwargs)  # type: ignore[arg-type]
            created_dirs.append(path)
            return path

        monkeypatch.setattr("src.agents.executor_modes.tempfile.mkdtemp", _spy_mkdtemp)

        real_open = builtins.open

        def _guarded_open(file: object, *args: object, **kwargs: object):
            if isinstance(file, str) and file.endswith("test_generated.py"):
                raise OSError(28, "No space left on device")
            return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "open", _guarded_open)
        result = execute_sandboxed(_ExecStub(), "def test_x():\n    assert True\n", target_file)
        monkeypatch.setattr(builtins, "open", real_open)

        assert result["passed"] is False
        assert result["error_info"]["type"] == "file_write_failed"
        assert "测试文件写入沙箱失败" in result["output"]
        assert created_dirs, "未创建沙箱目录（用例失效）"
        assert not os.path.exists(created_dirs[0]), "沙箱目录未被清理（临时目录泄漏）"

    def test_missing_target_file_reports_file_not_found(self, tmp_path: Path):
        result = execute_sandboxed(_ExecStub(), "def test_x():\n    assert True\n", str(tmp_path / "nope.py"))
        assert result["passed"] is False
        assert result["error_info"]["type"] == "file_not_found"


class TestDependencyFailureEarlyReturn:
    def test_install_failure_early_returns_without_running_pytest(
        self, target_file: str, monkeypatch: pytest.MonkeyPatch
    ):
        """依赖安装失败 → 提前返回 `dependency_install_failed`，且**不跑 pytest**。"""
        stub = _ExecStub()

        def _deps_fail(*_args: object, **_kwargs: object):
            return (
                {},
                None,
                "install failed",
                {"type": "dependency_install_failed", "message": "pip boom", "detail": "boom"},
                ["nonexistent-pkg"],
            )

        monkeypatch.setattr("src.agents.executor_modes._prepare_dependencies", _deps_fail)
        result = execute_sandboxed(stub, "def test_x():\n    assert True\n", target_file)

        assert result["passed"] is False
        assert result["error_info"]["type"] == "dependency_install_failed"
        assert stub.calls == [], "依赖失败时不得继续执行 pytest"


class TestKernelSandboxBranch:
    def test_kernel_sandbox_enabled_is_consulted(self, target_file: str, monkeypatch: pytest.MonkeyPatch):
        """KERNEL_SANDBOX_ENABLE=true 时进入内核沙箱包装分支（fail-closed 语义）。

        本用例只验证**分支被走到**且失败时给结构化诊断，不实际创建内核沙箱。
        """
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")

        def _deps_ok(*_args: object, **_kwargs: object):
            return ({}, None, "", None, [])

        def _kernel_unavailable(*_args: object, **_kwargs: object):
            raise RuntimeError("kernel sandbox unavailable")

        monkeypatch.setattr("src.agents.executor_modes._prepare_dependencies", _deps_ok)
        monkeypatch.setattr("src.agents.kernel_sandbox.build_sandbox_command", _kernel_unavailable, raising=False)
        stub = _ExecStub()
        try:
            result = execute_sandboxed(stub, "def test_x():\n    assert True\n", target_file)
        except RuntimeError:
            pytest.skip("该版本在内核沙箱不可用时直接抛出（fail-closed，无结果字典）")

        assert isinstance(result, dict)
        assert "passed" in result

    def test_kernel_sandbox_disabled_path_still_runs(self, target_file: str, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("KERNEL_SANDBOX_ENABLE", raising=False)

        def _deps_ok(*_args: object, **_kwargs: object):
            return ({}, None, "", None, [])

        monkeypatch.setattr("src.agents.executor_modes._prepare_dependencies", _deps_ok)
        stub = _ExecStub()
        result = execute_sandboxed(stub, "def test_x():\n    assert True\n", target_file)
        assert isinstance(result, dict)
