"""G3 内核级沙箱（kernel_sandbox）单元测试。

覆盖：
- kernel_sandbox_enabled 默认关 / 开启
- sandbox_supported 平台探测（缺工具 / 支持工具）
- build_sandbox_command fail-closed 口径（不支持平台返回原命令 + supported=False）
- Seatbelt profile 生成（macOS 支持时）
- bwrap 命令生成（Linux 支持时）
- describe_capabilities 输出结构
"""

from __future__ import annotations

import os
from unittest.mock import patch


def test_kernel_sandbox_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KERNEL_SANDBOX_ENABLE", None)
        from src.agents.kernel_sandbox import kernel_sandbox_enabled

        assert kernel_sandbox_enabled() is False


def test_kernel_sandbox_switch_on() -> None:
    with patch.dict(os.environ, {"KERNEL_SANDBOX_ENABLE": "true"}, clear=False):
        from src.agents.kernel_sandbox import kernel_sandbox_enabled

        assert kernel_sandbox_enabled() is True


def test_sandbox_supported_on_darwin_with_seatbelt() -> None:
    """macOS + sandbox-exec 存在 → 支持（Seatbelt 后端）。"""
    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "darwin"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=True),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=False),
    ):
        from src.agents.kernel_sandbox import sandbox_supported

        assert sandbox_supported() is True


def test_sandbox_supported_on_linux_with_bwrap() -> None:
    """Linux + bwrap 存在 → 支持（Landlock 后端）。"""
    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "linux"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=False),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=True),
    ):
        from src.agents.kernel_sandbox import sandbox_supported

        assert sandbox_supported() is True


def test_sandbox_supported_unsupported_platform() -> None:
    """Windows / 缺工具 → 不支持（fail-closed 拒绝执行）。"""
    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "windows"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=False),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=False),
    ):
        from src.agents.kernel_sandbox import sandbox_supported

        assert sandbox_supported() is False


def test_build_sandbox_command_seatbelt() -> None:
    """macOS Seatbelt 后端：命令以 sandbox-exec 开头 + profile 注入。"""
    from src.agents.kernel_sandbox import build_sandbox_command

    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "darwin"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=True),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=False),
    ):
        cmd, obs = build_sandbox_command(
            ["python", "-m", "pytest", "test_x.py"], cwd="/workspace", allowed_paths=["/data"]
        )
        assert cmd[0] == "sandbox-exec"
        assert "-p" in cmd
        assert cmd[-3:] == ["python", "-m", "pytest", "test_x.py"][-3:]
        assert obs["supported"] is True
        assert obs["backend"] == "seatbelt"
        assert "/workspace" in obs["allowed_paths"]
        assert "/data" in obs["allowed_paths"]


def test_build_sandbox_command_bwrap() -> None:
    """Linux bwrap 后端：命令以 bwrap 开头 + 断网 / 只读根。"""
    from src.agents.kernel_sandbox import build_sandbox_command

    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "linux"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=False),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=True),
    ):
        cmd, obs = build_sandbox_command(
            ["python", "-m", "pytest", "test_x.py"], cwd="/workspace", allowed_paths=["/data"]
        )
        assert cmd[0] == "bwrap"
        assert "--unshare-net" in cmd
        assert obs["supported"] is True
        assert obs["backend"] == "landlock_bwrap"


def test_build_sandbox_command_unsupported_fail_closed() -> None:
    """S1（2026-09-29 审查 P0）：不支持平台 → 抛 SandboxUnavailable（fail-closed）。

    历史口径：返回原命令 + supported=False（调用方忘检查 obs 时
    fail-open 裸跑）。现 fail-closed：直接拒绝执行，除非显式设
    ALLOW_UNSANDBOXED=true（保守降级，工件须记录该档位）。
    """
    from src.agents.kernel_sandbox import SandboxUnavailable, build_sandbox_command

    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "windows"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=False),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=False),
        patch.dict(os.environ, {"ALLOW_UNSANDBOXED": "false"}),
    ):
        try:
            build_sandbox_command(["python", "-m", "pytest", "test_x.py"], cwd="/workspace")
            raise AssertionError("Expected SandboxUnavailable to be raised")
        except SandboxUnavailable as exc:
            # U3（2026-10-05 系统性审查落地）：补断言——异常对象真实存在
            # （fail-closed 语义锁定，且 except 体不再是纯 pass）
            assert exc is not None


def test_build_sandbox_command_unsupported_allow_unsandboxed() -> None:
    """S1：ALLOW_UNSANDBOXED=true 时保守降级——返回原命令 + supported=False。"""
    from src.agents.kernel_sandbox import build_sandbox_command

    with (
        patch("src.agents.kernel_sandbox._HOST_PLATFORM", "windows"),
        patch("src.agents.kernel_sandbox._seatbelt_available", return_value=False),
        patch("src.agents.kernel_sandbox._landlock_available", return_value=False),
        patch.dict(os.environ, {"ALLOW_UNSANDBOXED": "true"}),
    ):
        cmd, obs = build_sandbox_command(["python", "-m", "pytest", "test_x.py"], cwd="/workspace")
        assert cmd == ["python", "-m", "pytest", "test_x.py"]  # 原命令（不支持时不包装）
        assert obs["supported"] is False
        assert obs["backend"] == "none"
        assert obs.get("allow_unsandboxed") is True


def test_describe_capabilities_structure() -> None:
    """describe_capabilities 返回 platform / supported / backends / notes 键。"""
    from src.agents.kernel_sandbox import describe_capabilities

    caps = describe_capabilities()
    assert "platform" in caps
    assert "supported" in caps
    assert "backends" in caps
    assert "notes" in caps
    assert isinstance(caps["backends"], list)
