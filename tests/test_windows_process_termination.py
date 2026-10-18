"""A12／P1（2026-10-18 第三方评审）：Windows 子进程整树回收分支 —— 回归锁。

缺陷（评审 G/A12、M5）
----------------------
``src/utils/process_utils.py::_terminate_process_group`` 直接调用
``os.getpgid`` / ``os.killpg``；Windows 没有这两个 API → 超时路径抛
``AttributeError`` 逃逸，**绕过 kill/wait**（调用方拿不到超时状态，进程树
可能残留）。``orphan_guard`` 内嵌看门狗脚本里的 ``os.killpg`` 同样没有平台
分支（父进程死亡路径会崩溃、命令进程组无人回收）。

修复
----
- ``_is_windows()``（**可注入**平台判定，单测 monkeypatch 模拟）分派
  ``_terminate_process_group_windows``：``taskkill /T /F /PID <pid>`` 整树回收
  → 失败/不可用时 ``process.kill()`` 兜底 → **有界等待直接子进程**（必要时补
  kill）；POSIX 两段式 killpg 路径逐字不变。
- ``_ORPHAN_GUARD_HELPERS`` 内嵌脚本按 ``os.name == "nt"`` 分流：Windows 用
  ``taskkill /T /F`` + ``child.kill()`` 兜底 + ``child.wait``；POSIX 保持
  ``os.killpg(os.getpgid(child.pid), SIGKILL)``。

本机 macOS 无法实跑 Windows，按评审 M5 口径全部用 Mock / 进程内语义模拟：
不启动、不终止真实 Windows 进程；POSIX 行为另用真实隔离子进程回归。
"""

from __future__ import annotations

import os
import subprocess
import sys
import types
from unittest.mock import Mock, patch

import pytest

import src.utils.process_utils as process_utils
from src.utils.process_utils import (
    _ORPHAN_GUARD_HELPERS,
    _ORPHAN_GUARD_SCRIPT,
    _is_windows,
    _run_taskkill,
    _terminate_process_group,
    _terminate_process_group_windows,
)

# ───────────────────────── 1) 平台判定与分支选择（M5 口径） ─────────────────────────


@pytest.mark.unit
class TestPlatformDispatch:
    def test_is_windows_matches_os_name(self) -> None:
        assert _is_windows() is (os.name == "nt")

    def test_m5_windows_branch_terminates_via_taskkill_on_mock_process(self) -> None:
        """评审 M5 脚本语义：模拟 Windows 下传入 Mock 进程，必须进入回收分支且不抛错。"""
        process = Mock(pid=123456)
        with (
            patch.object(process_utils, "_is_windows", return_value=True),
            patch.object(
                process_utils,
                "_run_taskkill",
                return_value=subprocess.CompletedProcess([], 0),
            ) as taskkill,
        ):
            _terminate_process_group(process, label="audit")  # 修复前：AttributeError
        assert taskkill.call_args_list[0].args == (123456,)
        assert process.kill.called is False, "taskkill 成功时不应再 kill() 直接子进程"
        assert process.wait.called, "直接子进程必须被有界等待/收尸"

    def test_windows_branch_never_touches_posix_process_group_apis(self) -> None:
        """Windows 分支不得调用 os.getpgid / os.killpg（历史 AttributeError 根因）。"""

        def _posix_api_must_not_be_called(*_args: object, **_kwargs: object) -> int:
            raise AssertionError("Windows 分支调用了 POSIX 进程组 API（A12 回归）")

        process = Mock(pid=654321)
        with (
            patch.object(process_utils, "_is_windows", return_value=True),
            patch.object(process_utils, "_run_taskkill", return_value=subprocess.CompletedProcess([], 0)),
            patch.object(process_utils.os, "getpgid", _posix_api_must_not_be_called),
            patch.object(process_utils.os, "killpg", _posix_api_must_not_be_called),
        ):
            _terminate_process_group(process, label="audit")
        assert process.wait.called

    def test_posix_branch_unchanged_when_is_windows_false(self) -> None:
        """POSIX 路径保持两段式 killpg（SIGTERM → SIGKILL）语义不变。"""
        process = Mock(pid=321)
        with (
            patch.object(process_utils, "_is_windows", return_value=False),
            patch.object(process_utils.os, "getpgid", return_value=456) as getpgid,
            patch.object(process_utils.os, "killpg") as killpg,
        ):
            _terminate_process_group(process, label="audit", grace_seconds=0)
        getpgid.assert_called_once_with(321)
        signals = [call.args[1] for call in killpg.call_args_list]
        assert signals == [process_utils.signal.SIGTERM, process_utils.signal.SIGKILL]
        assert all(call.args[0] == 456 for call in killpg.call_args_list)


# ───────────────────────── 2) Windows 回收分支细节 ─────────────────────────


class _FakeProc:
    """最小 Popen 替身：记录 wait/kill 调用，按脚本返回 poll 结果。"""

    def __init__(self, *, wait_outcomes: list[object], poll_outcomes: list[object]) -> None:
        self.pid = 4242
        self.wait_calls: list[float | None] = []
        self.kill_calls = 0
        self._wait_outcomes = list(wait_outcomes)
        self._poll_outcomes = list(poll_outcomes)

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        outcome = self._wait_outcomes.pop(0) if self._wait_outcomes else 0
        if isinstance(outcome, BaseException):
            raise outcome
        return 0

    def poll(self) -> int | None:
        return self._poll_outcomes.pop(0) if self._poll_outcomes else 0

    def kill(self) -> None:
        self.kill_calls += 1


@pytest.mark.unit
class TestWindowsTerminationBranch:
    def test_taskkill_nonzero_returncode_falls_back_to_kill(self) -> None:
        process = Mock(pid=111)
        with patch.object(process_utils, "_run_taskkill", return_value=subprocess.CompletedProcess([], 128)):
            _terminate_process_group_windows(process, label="audit")
        assert process.kill.called, "taskkill 返回非 0 时必须 kill() 兜底直接子进程"
        assert process.wait.called

    def test_taskkill_unavailable_falls_back_to_kill(self) -> None:
        process = Mock(pid=112)
        with patch.object(process_utils, "_run_taskkill", return_value=None):
            _terminate_process_group_windows(process, label="audit")
        assert process.kill.called, "taskkill 不可用时必须 kill() 兜底直接子进程"
        assert process.wait.called

    def test_no_valid_pid_falls_back_to_kill(self) -> None:
        process = Mock(pid=None)
        _terminate_process_group_windows(process, label="audit")
        assert process.kill.called
        assert process.wait.called

    def test_stubborn_child_is_killed_and_reaped_after_first_wait_timeout(self) -> None:
        """第一轮 wait 超时 → poll 仍存活 → 补 kill() → 再次 wait（直接子进程必被收尸）。"""
        process = _FakeProc(
            wait_outcomes=[subprocess.TimeoutExpired("audit", 5.0), 0],
            poll_outcomes=[None, 0],
        )
        with patch.object(process_utils, "_run_taskkill", return_value=subprocess.CompletedProcess([], 0)):
            _terminate_process_group_windows(process, label="audit")
        assert process.kill_calls == 1, "首轮 wait 超时且进程仍存活时未补 kill()"
        assert len(process.wait_calls) == 2, "kill() 后未再次等待直接子进程（可能留僵尸）"

    def test_function_returns_when_child_never_reports_exit(self) -> None:
        """子进程始终不退出：函数仍必须**返回**（不挂死，残余风险交由上层观测）。"""
        process = _FakeProc(
            wait_outcomes=[
                subprocess.TimeoutExpired("audit", 5.0),
                subprocess.TimeoutExpired("audit", 5.0),
            ],
            poll_outcomes=[None, None],
        )
        with patch.object(process_utils, "_run_taskkill", return_value=None):
            _terminate_process_group_windows(process, label="audit")
        assert process.kill_calls == 2  # 兜底 kill + 二轮仍存活补 kill
        assert len(process.wait_calls) == 2

    def test_run_taskkill_uses_expected_command(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(process_utils.subprocess, "run", return_value=completed) as run:
            assert _run_taskkill(9876) is completed
        argv = run.call_args.args[0]
        assert argv == ["taskkill", "/T", "/F", "/PID", "9876"]

    def test_run_taskkill_returns_none_when_binary_missing(self) -> None:
        with patch.object(process_utils.subprocess, "run", side_effect=FileNotFoundError("taskkill")):
            assert _run_taskkill(9876) is None

    def test_run_taskkill_returns_none_on_timeout(self) -> None:
        with patch.object(
            process_utils.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("taskkill", 10),
        ):
            assert _run_taskkill(9876) is None


# ───────────────────────── 3) orphan_guard 内嵌脚本平台分支 ─────────────────────────


def _load_guard_helpers() -> dict[str, object]:
    """进程内 exec 看门狗脚本的 helper 段（不启动真实进程，M5 同口径）。"""
    namespace: dict[str, object] = {}
    exec(compile(_ORPHAN_GUARD_HELPERS, "<orphan_guard_helpers>", "exec"), namespace)
    return namespace


def _guard_fake_subprocess(run: Mock) -> types.SimpleNamespace:
    """看门狗脚本里的 subprocess 替身（保留异常类型供 except 分支解析）。"""
    return types.SimpleNamespace(
        run=run,
        SubprocessError=subprocess.SubprocessError,
        TimeoutExpired=subprocess.TimeoutExpired,
    )


@pytest.mark.unit
class TestOrphanGuardScriptPlatformBranch:
    def test_script_contains_both_platform_branches(self) -> None:
        assert "_IS_WINDOWS = os.name ==" in _ORPHAN_GUARD_HELPERS
        assert "taskkill" in _ORPHAN_GUARD_HELPERS
        assert "os.killpg" in _ORPHAN_GUARD_HELPERS  # POSIX 语义保留
        assert _ORPHAN_GUARD_SCRIPT.startswith(_ORPHAN_GUARD_HELPERS)

    def test_windows_branch_uses_taskkill_and_waits(self) -> None:
        namespace = _load_guard_helpers()
        namespace["_IS_WINDOWS"] = True
        run = Mock(return_value=subprocess.CompletedProcess([], 0))
        namespace["subprocess"] = _guard_fake_subprocess(run)
        child = Mock(pid=4321)
        namespace["_kill_child_group"](child)  # type: ignore[operator]
        argv = run.call_args.args[0]
        assert argv == ["taskkill", "/T", "/F", "/PID", "4321"]
        assert child.wait.called, "Windows 分支必须等待直接子进程"
        assert child.kill.called is False

    def test_windows_branch_falls_back_to_child_kill(self) -> None:
        namespace = _load_guard_helpers()
        namespace["_IS_WINDOWS"] = True
        run = Mock(side_effect=FileNotFoundError("taskkill"))
        namespace["subprocess"] = _guard_fake_subprocess(run)
        child = Mock(pid=4322)
        child.wait.side_effect = [subprocess.TimeoutExpired("child", 2.0), 0]
        namespace["_kill_child_group"](child)  # type: ignore[operator]
        assert child.kill.called, "taskkill 不可用时看门狗必须回退 child.kill()"

    def test_posix_branch_still_kills_isolated_process_group(self) -> None:
        """POSIX 语义回归：脚本 helper 仍以 killpg 回收隔离进程组。"""
        if os.name == "nt":  # pragma: no cover - 本仓开发/CI 为 POSIX
            pytest.skip("POSIX 分支验证需 POSIX 宿主")
        namespace = _load_guard_helpers()
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
        )
        try:
            namespace["_kill_child_group"](child)  # type: ignore[operator]
            assert child.wait(timeout=10) == -9, "脚本 helper 未以 SIGKILL 回收隔离进程组"
        finally:
            if child.poll() is None:  # pragma: no cover - 防御断言失败时残留
                child.kill()
                child.wait(timeout=10)
