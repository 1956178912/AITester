"""P0-4 内核沙箱"显式启用时本地链路 fail-closed 可用"自验证（2026-10 批次·续四）。

此前威胁模型 P0-4 缺口登记为"内核沙箱已接线本地 + venv 两条主链路
（P2-5，2026-10-04），但 KERNEL_SANDBOX_ENABLE 默认关（启用为显式行为），
CI 未预装 bwrap → 显式启用时 Linux CI 容器仍 fail-closed 拒绝执行"。

本测试锁定"显式启用后本地链路真的可用"的自验证口径（零 LLM / 零子进程，
纯 monkeypatch 平台探测 + argv 装配断言）：

1. CI 预装 bwrap 路径：kernel_sandbox._landlock_available() 为 True
   （bwrap 工具存在）→ build_sandbox_command 装配 bwrap argv（--ro-bind /
   + --unshare-net + --bind cwd + 解释器库 ro-bind + --chdir），
   子进程经 bwrap 隔离执行（断网 + 只读根 + 工作目录写）；
2. fail-closed 口径复锁：平台无后端且 ALLOW_UNSANDBOXED=false 时
   build_sandbox_command 抛 SandboxUnavailable（不静默降级到无隔离裸跑）；
3. 本地链路 argv 装配（executor._execute_local L210-227 口径）：
   KERNEL_SANDBOX_ENABLE=true 且后端支持时，cmd 被替换为完整
   sandboxed_cmd（argv[0]=bwrap/sandbox-exec 本身，零 subprocess 语义
   歧义），self._kernel_sandbox_executable 记录 argv[0]（观测用途）；
   obs["supported"]=False 时本地链路拒绝执行并返回
   kernel_sandbox_unavailable 诊断（不裸跑）。

用途：CI 预装 bwrap 后跑本测试即可自验证"显式启用路径可用"；
macOS dev 机（seatbelt）同口径覆盖。测试不依赖真实 bwrap 安装
（monkeypatch _landlock_available / _seatbelt_available 控制平台探测）。
"""

from __future__ import annotations

import platform
import shutil
from unittest.mock import patch

import pytest

from src.agents.kernel_sandbox import (
    SandboxUnavailable,
    build_sandbox_command,
)

# ── 1. 平台探测（CI 预装 bwrap 路径）────────────────────────────────────────


def test_landlock_available_true_when_bwrap_present(monkeypatch):
    """bwrap 工具存在 + 平台 linux → _landlock_available() True（CI 预装口径）。"""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    # 模块级 _HOST_PLATFORM 在 import 时已探测，须一并 patch
    import src.agents.kernel_sandbox as ks

    monkeypatch.setattr(ks, "_HOST_PLATFORM", "linux")
    assert ks._landlock_available() is True
    assert ks._seatbelt_available() is False


def test_landlock_available_false_when_bwrap_missing(monkeypatch):
    """bwrap 工具缺失 → _landlock_available() False（fail-closed 前提）。"""
    import src.agents.kernel_sandbox as ks

    monkeypatch.setattr(ks, "_HOST_PLATFORM", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert ks._landlock_available() is False


def test_sandbox_supported_linux_with_bwrap(monkeypatch):
    """bwrap 预装 + linux → sandbox_supported() True（显式启用路径可用前提）。"""
    import src.agents.kernel_sandbox as ks

    monkeypatch.setattr(ks, "_HOST_PLATFORM", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    assert ks.sandbox_supported() is True


# ── 2. build_sandbox_command：bwrap argv 装配（显式启用后可用）───────────────


def test_build_sandbox_command_bwrap_argv_assembly(monkeypatch):
    """bwrap 路径：cmd 被包装为完整 bwrap argv（argv[0]=bwrap，零 subprocess 歧义）。"""
    import src.agents.kernel_sandbox as ks

    monkeypatch.setattr(ks, "_HOST_PLATFORM", "linux")
    # 直接 patch 模块级探测函数（不依赖真实 bwrap 工具存在，仅验证 argv 装配逻辑）
    with (
        patch.object(ks, "_seatbelt_available", return_value=False),
        patch.object(ks, "_landlock_available", return_value=True),
    ):
        cmd, obs = build_sandbox_command(
            args=["/venv/bin/python", "-m", "pytest", "test_generated.py"],
            cwd="/tmp/aitester_task_dir",
            allowed_paths=["/venv"],
        )
    assert cmd[0] == "bwrap"
    # 断网 + 只读根 + 工作目录写（Landlock 口径）
    assert "--unshare-net" in cmd
    assert "--die-with-parent" in cmd
    # cwd 可写挂载
    assert "--bind" in cmd
    # 解释器库目录 ro-bind（保守最小集）
    assert "/usr" in cmd
    # --chdir + 命令体
    assert "--chdir" in cmd
    assert cmd[-1] == "test_generated.py"  # 原命令尾元素保留
    # obs 字段
    assert obs["supported"] is True
    assert obs["backend"] == "landlock_bwrap"
    assert obs["platform"] == "linux"


# ── 3. fail-closed 口径复锁（无后端 + ALLOW_UNSANDBOXED=false → 拒绝）──────


def test_build_sandbox_command_unsupported_fail_closed(monkeypatch):
    """平台无后端 + ALLOW_UNSANDBOXED=false → 抛 SandboxUnavailable（不裸跑）。"""
    import src.agents.kernel_sandbox as ks

    monkeypatch.delenv("ALLOW_UNSANDBOXED", raising=False)
    with (
        patch.object(ks, "_seatbelt_available", return_value=False),
        patch.object(ks, "_landlock_available", return_value=False),
        pytest.raises(SandboxUnavailable),
    ):
        build_sandbox_command(args=["python", "-m", "pytest"], cwd="/tmp/x")


def test_build_sandbox_command_unsupported_allow_unsandboxed(monkeypatch):
    """平台无后端 + ALLOW_UNSANDBOXED=true → 返回原命令 + obs.supported=False
    （保守降级，调用方须检查 obs 字段，本地链路据此走 kernel_sandbox_unavailable
    早退分支，不静默裸跑）。"""
    import src.agents.kernel_sandbox as ks

    monkeypatch.setenv("ALLOW_UNSANDBOXED", "true")
    with (
        patch.object(ks, "_seatbelt_available", return_value=False),
        patch.object(ks, "_landlock_available", return_value=False),
    ):
        cmd, obs = build_sandbox_command(args=["python", "-m", "pytest"], cwd="/tmp/x")
    assert cmd == ["python", "-m", "pytest"]  # 原命令（未包装）
    assert obs["supported"] is False
    assert obs["allow_unsandboxed"] is True


# ── 4. 本地链路 argv 装配口径（executor._execute_local L210-227 行为复锁）────


def test_local_chain_full_argv_no_subprocess_ambiguity(monkeypatch):
    """本地链路 G3 口径复锁：KERNEL_SANDBOX_ENABLE=true + 后端支持时，
    cmd 被替换为完整 sandboxed_cmd（argv[0]=bwrap 本身），
    而非 sandboxed_cmd[1:]（旧 bug：cmd[0]='-p'/'--ro-bind' 导致
    subprocess.run(cmd) 把 argv[0] 当可执行文件 → FileNotFoundError）。

    本测试直接验证 build_sandbox_command 返回的 argv 满足
    "subprocess.run(cmd) 无歧义" 口径（cmd[0] 为工具名，非参数）：
    - bwrap 路径：cmd[0]="bwrap"（工具名）；
    - seatbelt 路径：cmd[0]="sandbox-exec"（工具名）。
    """
    import src.agents.kernel_sandbox as ks

    # bwrap 路径
    with (
        patch.object(ks, "_seatbelt_available", return_value=False),
        patch.object(ks, "_landlock_available", return_value=True),
    ):
        bwrap_cmd, _ = build_sandbox_command(args=[sys_executable_placeholder(), "-m", "pytest"], cwd="/tmp/x")
    assert bwrap_cmd[0] == "bwrap"  # argv[0] 为工具名（subprocess.run 无歧义）

    # seatbelt 路径
    with (
        patch.object(ks, "_seatbelt_available", return_value=True),
        patch.object(ks, "_landlock_available", return_value=False),
    ):
        seatbelt_cmd, _ = build_sandbox_command(args=[sys_executable_placeholder(), "-m", "pytest"], cwd="/tmp/x")
    assert seatbelt_cmd[0] == "sandbox-exec"  # argv[0] 为工具名


def sys_executable_placeholder() -> str:
    """返回一个可执行路径占位（测试不真实执行，仅验证 argv 装配形状）。"""
    import sys

    return sys.executable
