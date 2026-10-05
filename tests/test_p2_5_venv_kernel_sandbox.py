"""P2-5 venv 沙箱链路内核沙箱接线回归测试（2026-10 批次）。

锁定口径（与 executor_modes.execute_sandboxed 实现一致）：
1. 默认关（KERNEL_SANDBOX_ENABLE=false）：venv 沙箱链路零行为变化
   （结果 dict 无 kernel_sandbox_obs 键）；
2. 开关 ON + 平台支持（build_sandbox_command 打桩 supported=True）：
   - cmd 被替换为完整沙箱 argv（argv[0] 即 sandbox-exec/bwrap 工具自身，
     S1 修复同款的"完整 argv 传法"，无 subprocess 语义歧义）；
   - 允许路径包含 sandbox_dir 与 sys.executable（seatbelt process-exec /
     bwrap bind 口径）；
   - 结果 dict 附 kernel_sandbox_obs 观测层（纯观测，不改结果口径）；
3. 开关 ON + 平台不支持（build_sandbox_command 抛 SandboxUnavailable）：
   fail-closed 拒绝执行（error_info.type=kernel_sandbox_unavailable），
   不静默降级 venv 裸跑（与本地链路口径一致）；
4. 开关 ON + supported=False 容忍档（ALLOW_UNSANDBOXED=true，双保险分支）：
   同样拒绝执行（保守 fail-closed）。
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

import src.agents.executor_modes as em
import src.agents.kernel_sandbox as ks
from src.agents.kernel_sandbox import SandboxUnavailable

# 被测文件桩：模块名 "calc_add"，被测源码可被 auto_fix_imports 处理
_TARGET_DIR = "/tmp/aitester_p2_5_stub"
_TARGET_FILE = os.path.join(_TARGET_DIR, "calc_add.py")
_TARGET_SOURCE = "def add(a, b):\n    return a + b\n"


def _setup_target() -> None:
    os.makedirs(_TARGET_DIR, exist_ok=True)
    with open(_TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(_TARGET_SOURCE)


def _make_executor(captured: dict | None = None):
    """构造 ExecutorAgent 桩实例：真实类 + 实例属性注入，
    _run_pytest_with_retry / _cleanup_sandbox 直接命中实例属性
    （self.<attr> 优先于类属性——不污染其他用例的类属性绑定）。

    注：__init__ 回落 config 默认（EXECUTOR_USE_VENV 默认 true，R10），
    经 object.__new__ 跳过 __init__ 直接注入字段，避免 config 环境变量
    漂移（本测试只关心 execute_sandboxed 的内核沙箱接线段）。
    """
    from src.agents.executor import ExecutorAgent

    self = object.__new__(ExecutorAgent)
    self.timeout = 30
    self.use_docker = False
    self.use_venv = True
    self.auto_install_deps = False
    self.dep_install_timeout = 120
    self.docker_image = "aitester:latest"
    self._kernel_sandbox_executable = None
    self._kernel_sandbox_obs = {}
    if captured is not None:

        def _fake_run(cmd, env, project_root):
            fake_completed = MagicMock()
            fake_completed.returncode = 0
            fake_completed.stdout = "1 passed"
            fake_completed.stderr = ""
            captured["cmd"] = list(cmd)
            captured["cwd"] = project_root
            return "1 passed", fake_completed

        self._run_pytest_with_retry = lambda cmd, env, project_root: _fake_run(cmd, env, project_root)
        self._cleanup_sandbox = lambda d: None
    return self


@pytest.fixture
def captured(monkeypatch):
    """桩掉 execute_sandboxed 的非被测段（依赖准备 / 沙箱清理），
    返回捕获器 dict（cmd / cwd 由 _make_executor 注入的子进程桩填充）。

    子进程执行（self._run_pytest_with_retry）桩由 _make_executor(captured=…)
    直接注入实例属性（self.<attr> 命中，无需打桩类属性——避免污染其他用例）。
    """
    _setup_target()
    monkeypatch.setattr(
        em,
        "_prepare_dependencies",
        lambda self_, *a, **k: ({}, sys.executable, "", None, []),
    )
    monkeypatch.setattr(em, "cleanup_sandbox", lambda d: None, raising=False)
    return {"target_file": _TARGET_FILE, "cmd": None, "cwd": None}


def _run_sandboxed(captured, monkeypatch, test_code: str = "def test_x():\n    pass\n") -> dict:
    """执行 execute_sandboxed（_make_executor 注入捕获器 + 桩）。"""
    self = _make_executor(captured)
    return em.execute_sandboxed(self, test_code, captured["target_file"])


# ── 1. 默认关：零行为变化（结果 dict 无 kernel_sandbox_obs）────────────────


def test_venv_sandbox_kernel_off_by_default(captured, monkeypatch):
    monkeypatch.delenv("KERNEL_SANDBOX_ENABLE", raising=False)
    result = _run_sandboxed(captured, monkeypatch)
    assert result["passed"] is True
    # 默认关：cmd 原样（python 解释器打头），无观测层键
    assert captured["cmd"][0] == sys.executable
    assert "kernel_sandbox_obs" not in result


# ── 2. ON + 支持：完整 argv 传法 + 允许路径 + 观测层 ─────────────────────────


def test_venv_sandbox_kernel_on_supported(captured, monkeypatch):
    monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")
    fake_obs: dict = {"platform": "darwin", "backend": "seatbelt", "supported": True, "allowed_paths": []}

    def _fake_build(args, cwd, allowed_paths=None):
        fake_obs["allowed_paths"] = list(allowed_paths or [])
        fake_obs["cwd"] = cwd
        return ["sandbox-exec", "-p", "(version 1)", *args], fake_obs

    monkeypatch.setattr(ks, "build_sandbox_command", _fake_build, raising=False)

    result = _run_sandboxed(captured, monkeypatch)
    assert result["passed"] is True
    # 完整 argv 传法：cmd 被替换为沙箱命令（argv[0] = sandbox-exec）
    assert captured["cmd"][0] == "sandbox-exec"
    assert captured["cmd"][1] == "-p"
    # 允许路径口径：sandbox_dir + sys.executable
    assert sys.executable in fake_obs["allowed_paths"]
    # 观测层透传（纯观测，不改结果口径）
    assert "kernel_sandbox_obs" in result
    assert result["kernel_sandbox_obs"]["backend"] == "seatbelt"


# ── 3. ON + 平台不支持（SandboxUnavailable）：fail-closed 拒绝执行 ─────────


def test_venv_sandbox_kernel_unavailable_fail_closed(captured, monkeypatch):
    monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")

    def _raise(*a, **k):
        raise SandboxUnavailable("内核沙箱不支持当前平台（windows），fail-closed 拒绝执行")

    monkeypatch.setattr(ks, "build_sandbox_command", _raise, raising=False)

    result = _run_sandboxed(captured, monkeypatch)
    assert result["passed"] is False
    assert result["error_info"]["type"] == "kernel_sandbox_unavailable"
    # 拒绝执行：pytest 子进程未跑（cmd 未被 _run_pytest_with_retry 桩捕获）
    assert captured["cmd"] is None


# ── 4. ON + supported=False（ALLOW_UNSANDBOXED=true 容忍档）：双保险拒绝 ──────


def test_venv_sandbox_kernel_supported_false_double_safety(captured, monkeypatch):
    monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")

    def _return_unsupported(args, cwd, allowed_paths=None):
        obs = {
            "platform": "windows",
            "backend": "none",
            "supported": False,
            "allowed_paths": list(allowed_paths or []),
            "profile_summary": "当前平台无可用内核沙箱后端（fail-closed，拒绝执行）",
            "allow_unsandboxed": True,
        }
        return list(args), obs

    monkeypatch.setattr(ks, "build_sandbox_command", _return_unsupported, raising=False)

    result = _run_sandboxed(captured, monkeypatch)
    assert result["passed"] is False
    assert result["error_info"]["type"] == "kernel_sandbox_unavailable"
    assert result["kernel_sandbox_obs"]["supported"] is False
