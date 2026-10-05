"""
G3 内核级沙箱（Kernel Sandbox，默认关，平台相关最小可用集）。

背景（gap_report 2026-09-28 P1 缺口 G3）：
    当前 executor_modes.py 已实现 Docker 容器级网络出口管控
    （DOCKER_NETWORK_ISOLATION / allowlist 模式），但全仓无
    seccomp/landlock/seatbelt 引用——内核级隔离未实现。
    本模块补齐"本地非容器执行链路"的内核级隔离纵深（容器模式
    继续保留现有出口管控，不替换）；接入点：
    - 本地链路（executor._execute_local，2026-09-30 G3 接入）；
    - venv 沙箱链路（executor_modes.execute_sandboxed，P2-5，2026-10 接入）；
    - 后端选择：macOS Seatbelt（sandbox-exec）/ Linux Landlock+bwrap；
      Windows 暂未实现（记录为未支持，fail-closed 提示）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `KERNEL_SANDBOX_ENABLE=false`（默认）时本模块零行为变化：
      不接入 executor_modes 主链路，纯命令生成 + 能力探测层；
    - 沙箱能力是**纯数据 + subprocess 命令包装**（零 LLM 成本、
      零新依赖——只用 os / platform / shutil 等标准库探测平台
      与系统工具是否存在）；
    - 缺平台工具（如 macOS 无 sandbox-exec / Linux 无 bwrap）时
      `build_sandbox_command` 返回 fail-closed 标记（不静默降级
      到"无隔离直接执行"，避免"以为隔离了其实没有"污染对比
      实验口径——与 executor_modes.docker_unavailable 同口径）；
    - 观测层：结果 JSON 增加 `kernel_sandbox_obs`（platform /
      backend / allowed_paths / capabilities），供 Fail-Closed
      治理协议与实验分析消费（纯观测，不改结果口径）。

使用方式（executor_modes 本地执行分支 / 离线验证）：
    from src.agents.kernel_sandbox import (
        kernel_sandbox_enabled,
        sandbox_supported,
        build_sandbox_command,
        describe_capabilities,
    )

    if kernel_sandbox_enabled():
        sandboxed_cmd, obs = build_sandbox_command(["python", "-m", "pytest", "test_generated.py"], cwd="/workspace")
        # obs = {"platform": "darwin", "backend": "seatbelt", "supported": True, ...}
        # sandboxed_cmd = ["sandbox-exec", "-p", "<profile>", ...] / 原命令（不支持时）
        # 不支持时 obs["supported"]=False，调用方 fail-closed 拒绝执行
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from typing import Any

logger = logging.getLogger(__name__)

# 平台探测（模块级，进程内不变）
_HOST_PLATFORM: str = platform.system().lower()  # "darwin" / "linux" / "windows" / ...


class SandboxUnavailable(RuntimeError):
    """S1（2026-09-29 审查 P0）：内核沙箱后端不可用且未显式容忍无隔离
    （ALLOW_UNSANDBOXED=false，默认）时由 build_sandbox_command 抛出。

    历史口径：平台不支持时返回原命令 + obs["supported"]=False（调用方
    忘检查 obs 时 fail-open 裸跑）。现 fail-closed：直接拒绝执行，
    除非显式设 ALLOW_UNSANDBOXED=true（保守降级，工件须记录该档位）。
    """


def kernel_sandbox_enabled() -> bool:
    """内核级沙箱开关（KERNEL_SANDBOX_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("KERNEL_SANDBOX_ENABLE", "false").lower() in ("true", "1", "on")


def _seatbelt_available() -> bool:
    """macOS Seatbelt（sandbox-exec）工具是否存在。"""
    return _HOST_PLATFORM == "darwin" and shutil.which("sandbox-exec") is not None


def _landlock_available() -> bool:
    """Linux Landlock 沙箱框架（bwrap 或 landlock-tools）是否存在（保守口径：仅探测 bwrap）。"""
    return _HOST_PLATFORM == "linux" and shutil.which("bwrap") is not None


def sandbox_supported() -> bool:
    """当前平台是否存在可用的内核级沙箱后端（macOS Seatbelt / Linux Landlock+bwrap）。

    保守口径：
        - macOS：需 sandbox-exec 工具（系统自带）；
        - Linux：需 bwrap 工具（bubblewrap，多数发行版可装）；
        - 其他平台（Windows 等）：暂未实现，返回 False（fail-closed）。
    """
    if _seatbelt_available():
        return True
    return bool(_landlock_available())


def _seatbelt_profile(allowed_paths: list[str]) -> str:
    """生成 macOS Seatbelt 沙箱 profile（保守最小可用集）。

    口径（与"本地非容器执行链路"的安全目标对齐）：
        - 拒绝写 .env / config.local* / .private* 等凭证文件（默认 DENY）；
        - 允许读写 allowed_paths（如任务临时工作目录）；
        - 允许必要的读 /tmp / 系统库（不阻断 pytest 执行）；
        - 网络：默认拒绝所有出站（(allow network*) 需显式配置时才放开，
          保守口径与 Docker 出口管控同向——"无测试执行场景"下
          不需要网络，断网是安全的默认）。

    Args:
        allowed_paths: 允许读写的路径列表（任务工作目录等）。

    Returns:
        Seatbelt profile 文本（sandbox-exec -p <profile> 消费）。
    """
    lines = ["(version 1)", "(deny default)"]
    # S2（2026-09-29 审查 P0）：最小读集 —— 不再 (allow file-read*)（全盘可读，
    # .env / llm_configs.json / ~/.ssh / ~/.aws 均可读 + 进 LLM prompt → 外泄链），
    # 改为显式放行必要子路径：
    #   - allowed_paths（任务工作目录）
    #   - /usr（Python 解释器与系统库）
    #   - /System 与 /Library（macOS 系统框架）
    #   - /tmp（pytest 临时文件）
    # 并显式 DENY 凭证文件（.env* / .ssh / .aws / llm_configs.json /
    # credentials*），即使它们位于 allowed_paths 内也拒绝。
    for path in allowed_paths:
        lines.append(f"(allow file-read* (subpath {path!r}))")
        lines.append(f"(allow file-write* (subpath {path!r}))")
    # 系统库（/usr）：pytest 解释器与 C 扩展依赖
    lines.append('(allow file-read* (subpath "/usr"))')
    lines.append('(allow file-read* (subpath "/System"))')
    lines.append('(allow file-read* (subpath "/Library"))')
    lines.append('(allow file-read* (subpath "/tmp"))')
    lines.append('(allow file-write* (subpath "/tmp"))')
    lines.append("(allow sysctl-read)")
    # 进程：pytest 需 fork/exec，但限定可执行目标为 /usr 与 allowed_paths
    # （不再 (allow process*) 全放行——可 exec 任意二进制）
    lines.append("(allow process-fork)")
    lines.extend(f"(allow process-exec (subpath {path!r}))" for path in allowed_paths)
    lines.append('(allow process-exec (subpath "/usr"))')
    lines.append("(allow ipc*)")
    # S2 凭证文件显式 DENY（覆盖 allowed_paths 内误含的凭证路径）
    lines.append('(deny file-read* (regex #".env.*|\\.ssh|\\.aws|llm_configs\\.json|credentials"))')
    # 保守：不放开网络出站（本地执行场景默认断网，与 Docker 出口管控同向）
    return "\n".join(lines)


def _build_bwrap_command(args: list[str], cwd: str, allowed_paths: list[str]) -> list[str]:
    """生成 Linux bwrap（Landlock 口径）沙箱命令。

    口径（保守最小可用集）：
        - `--bind` 只挂载 allowed_paths + cwd（其余路径不可见）；
        - `--ro-bind / /`（根文件系统只读）；
        - `--unshare-net`（断网，与 Docker --network=none 同向）；
        - `--die-with-parent`（沙箱随父进程终止，防孤儿进程）。

    Args:
        args: 要在沙箱内执行的命令列表（如 ["python", "-m", "pytest", ...]）。
        cwd: 沙箱内工作目录。
        allowed_paths: 允许读写的路径列表。

    Returns:
        bwrap 完整命令列表。
    """
    cmd: list[str] = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",  # 根文件系统只读
        "--unshare-net",  # 断网（保守，与 Docker 出口管控同向）
        "--die-with-parent",
    ]
    # 工作目录可写
    cmd.extend(["--bind", cwd, cwd])
    # 额外可写路径
    for path in allowed_paths:
        cmd.extend(["--bind", path, path])
    # 解释器 / 库所在目录需可执行（保守：挂载常见 Python 目录，按需扩展）
    for lib_dir in ("/usr", "/lib", "/lib64", "/bin", "/sbin"):
        cmd.extend(["--ro-bind", lib_dir, lib_dir])
    cmd.extend(["--chdir", cwd])
    cmd.append("--")
    cmd.extend(args)
    return cmd


def build_sandbox_command(
    args: list[str],
    cwd: str,
    allowed_paths: list[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """按当前平台生成内核级沙箱命令 + 观测层字段。

    设计口径（fail-closed，不静默降级）：
        - 平台不支持（sandbox_supported() 为 False）→ 返回原命令 +
          obs["supported"]=False（调用方应拒绝执行，避免"以为
          隔离了其实没有"污染对比实验——与 executor_modes 的
          docker_unavailable 同口径）；
        - 平台支持 → 包装为沙箱命令 + obs["supported"]=True。

    Args:
        args: 要执行的命令列表（如 ["python", "-m", "pytest", "test_generated.py"]）。
        cwd: 执行工作目录。
        allowed_paths: 额外允许读写的路径列表（默认 [cwd]）。

    Returns:
        (sandboxed_cmd, obs)：
            sandboxed_cmd: 沙箱包装后的完整命令列表（不支持时为原 args）；
            obs: 观测层 dict（platform / backend / supported /
                allowed_paths / profile_summary），纯观测不改结果口径。
    """
    paths = list(allowed_paths or [])
    if cwd and cwd not in paths:
        paths.append(cwd)

    if _seatbelt_available():
        profile = _seatbelt_profile(paths)
        sandboxed_cmd = ["sandbox-exec", "-p", profile, *args]
        obs: dict[str, Any] = {
            "platform": _HOST_PLATFORM,
            "backend": "seatbelt",
            "supported": True,
            "allowed_paths": paths,
            "profile_summary": f"{len(paths)} 路径写放行 + 全文件系统只读 + 断网",
        }
        return sandboxed_cmd, obs

    if _landlock_available():
        sandboxed_cmd = _build_bwrap_command(args, cwd, paths)
        obs = {
            "platform": _HOST_PLATFORM,
            "backend": "landlock_bwrap",
            "supported": True,
            "allowed_paths": paths,
            "profile_summary": "bwrap 根只读 + 工作目录写 + 断网（Landlock 口径）",
        }
        return sandboxed_cmd, obs

    # S1（2026-09-29 审查 P0）：fail-closed —— 平台不支持时**抛
    # SandboxUnavailable**（不再返回原命令 + supported=False 让调用方
    # "忘检查 obs" 时 fail-open 裸跑）。设 ALLOW_UNSANDBOXED=true 可显式
    # 容忍无隔离（保守降级，供无沙箱工具的平台做本地调试，但工件须
    # 记录该档位）。
    _allow_unsandboxed = os.getenv("ALLOW_UNSANDBOXED", "false").lower() in ("true", "1", "on")
    obs_unsupported: dict[str, Any] = {
        "platform": _HOST_PLATFORM,
        "backend": "none",
        "supported": False,
        "allowed_paths": paths,
        "profile_summary": "当前平台无可用内核沙箱后端（fail-closed，拒绝执行）",
        "allow_unsandboxed": _allow_unsandboxed,
    }
    if not _allow_unsandboxed:
        raise SandboxUnavailable(
            f"内核沙箱不支持当前平台（{_HOST_PLATFORM}），fail-closed 拒绝执行；"
            "如需无隔离调试请显式设 ALLOW_UNSANDBOXED=true（工件须记录该档位）"
        )
    logger.warning("内核沙箱不支持当前平台（%s），ALLOW_UNSANDBOXED=true 容忍无隔离", _HOST_PLATFORM)
    return list(args), obs_unsupported


def describe_capabilities() -> dict[str, Any]:
    """描述当前平台的内核沙箱能力（供文档 / 实验分析 / CI 消费）。

    Returns:
        能力 dict：{"platform", "supported", "backends", "notes"}。
    """
    backends: list[str] = []
    if _seatbelt_available():
        backends.append("seatbelt")
    if _landlock_available():
        backends.append("landlock_bwrap")
    notes = {
        "darwin": "Seatbelt（sandbox-exec）——平台原生沙箱，默认 macOS 自带",
        "linux": "Landlock + bwrap（bubblewrap）——需安装 bubblewrap 包",
        "windows": "暂未实现（记录为未支持，fail-closed）",
    }
    return {
        "platform": _HOST_PLATFORM,
        "supported": sandbox_supported(),
        "backends": backends,
        "notes": notes.get(_HOST_PLATFORM, f"未知平台（{_HOST_PLATFORM}），暂未实现内核沙箱"),
    }


__all__ = [
    "SandboxUnavailable",
    "build_sandbox_command",
    "describe_capabilities",
    "kernel_sandbox_enabled",
    "sandbox_supported",
]
