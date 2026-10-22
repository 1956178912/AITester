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

N-2 接线修复（2026-10-17）：执行器沙箱放行面
------------------------------------------------
e2e 探针实测：`KERNEL_SANDBOX_ENABLE=true` 时执行器 100% 失败（`sandbox-exec:
execvp() of '.../.venv/bin/python' failed: Operation not permitted`），因为接线
只放行任务目录，未放行**解释器自身**（venv/bin/python 的字面路径、framework
Python.app、venv 根/pyvenv.cfg、stdlib）与 pytest 临时目录。本模块补三件事：

- `build_sandbox_command(..., cwd_rw=, exec_paths=, read_paths=, write_paths=)`：
  放行面细分（读写/只读/仅执行，SBPL 规则按文件 literal / 目录 subpath 生成）；
- `interpreter_sandbox_allowances(python_executable)`：解释器执行所需最小
  exec/read 路径集（venv 根只读、framework 安装根、argv[0] 字面+realpath）；
- `sandbox_launch_failure(output)`：沙箱启动失败识别（沙箱配置/exec 被拒 →
  调用方应记 `kernel_sandbox_unavailable`，不得误报为 test_failure）。
仍禁止写仓库根（executor 传 `cwd_rw=False`，cwd 仅只读）与读凭证文件
（profile 的 `.env*`/`.ssh`/`.aws`/`llm_configs.json` DENY 正则保留）。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from typing import Any

from src.utils.env_utils import env_flag

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
    return env_flag("KERNEL_SANDBOX_ENABLE")


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


def _sbpl_quote(path: str) -> str:
    """SBPL 字符串字面量（**双引号**；反斜杠/双引号经 JSON 转义）。

    M 轮 N-2 e2e 探针实测缺陷（2026-10-17）：历史上用 Python `repr()`
    （`f"(subpath {path!r})"`）把路径写成**单引号**字符串，而 Seatbelt
    profile 语言只接受双引号字符串——`sandbox-exec` 直接以 rc=65 拒绝
    整个 profile（stderr：`unexpected symbol argument ... (subpath '/tmp')`），
    `KERNEL_SANDBOX_ENABLE=true` 的所有执行链路 100% 失效且错误只出现在
    pytest 输出里（表现为测试失败而非沙箱不可用）。JSON 转义与 SBPL 双引号
    字符串的 `\\` / `\"` 转义兼容；非 ASCII 路径保持原字符（ensure_ascii=False）。

    Args:
        path: 文件系统路径。

    Returns:
        SBPL 字符串字面量（含两端双引号）。
    """
    import json

    return json.dumps(str(path), ensure_ascii=False)


def _dedupe_paths(*groups: list[str] | None) -> list[str]:
    """合并多组路径并去重（保持首次出现顺序；空/None 组忽略）。

    Args:
        *groups: 任意数量的路径列表（可为 None）。

    Returns:
        去重后的路径列表（顺序稳定，便于 obs/测试断言可复现）。
    """
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for path in group or []:
            if not path:
                continue
            normalized = os.path.normpath(str(path))
            if normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
    return out


def _realpath_variants(path: str) -> list[str]:
    """返回路径的"字面形式 + realpath 形式"（去重、稳定顺序）。

    macOS/Linux 系统路径常含符号链接（`/tmp → /private/tmp`、`/var →
    /private/var`、`/Users` 无）；SBPL 的 subpath/literal 匹配按**真实路径**
    生效，只用字面形式会漏掉整棵子树（实测：TMPDIR `/var/folders/...` 的
    scandir 被拒 → pytest rootdir 扫描失败）。故所有放行路径同时生成
    字面与 realpath 两种规则（幂等去重，不扩大面——二者指向同一目标）。

    Args:
        path: 原始路径。

    Returns:
        去重后的路径变体列表（[原路径] 或 [原路径, realpath]）。
    """
    variants: list[str] = []
    for candidate in (str(path),):
        if candidate and candidate not in variants:
            variants.append(candidate)
    try:
        real = os.path.realpath(str(path))
    except OSError:  # pragma: no cover - 极端文件系统异常
        real = str(path)
    if real and real not in variants:
        variants.append(real)
    return variants


def _sbpl_scope_rules(action: str, paths: list[str] | None) -> list[str]:
    """为一组路径生成 SBPL 放行规则（文件用 literal、目录用 subpath）。

    N-2（2026-10-17）：执行器接线需要**细粒度放行面**——解释器 argv[0] 是
    **文件**路径（`.../.venv/bin/python`），SBPL `subpath` 只对目录有意义；
    framework 安装根/TMPDIR 是目录。故文件路径生成 `(literal ...)`（精确
    匹配该文件），目录路径生成 `(subpath ...)`（覆盖整棵子树）。

    Args:
        action: SBPL 动作（如 "file-read*"、"file-write*"、"process-exec"）。
        paths: 路径列表（可为 None）。

    Returns:
        SBPL 规则行列表；paths 为空时返回 []。
    """
    rules: list[str] = []
    for path in _dedupe_paths(paths):
        for variant in _realpath_variants(path):
            quoted = _sbpl_quote(variant)
            rules.append(f"(allow {action} (literal {quoted}))")
            try:
                is_dir = os.path.isdir(variant)
            except OSError:  # pragma: no cover - 极端文件系统异常
                is_dir = False
            if is_dir:
                rules.append(f"(allow {action} (subpath {quoted}))")
    return rules


def _seatbelt_profile(
    allowed_paths: list[str],
    *,
    exec_paths: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
) -> str:
    """生成 macOS Seatbelt 沙箱 profile（保守最小可用集）。

    口径（与"本地非容器执行链路"的安全目标对齐）：
        - 拒绝写 .env / config.local* / .private* 等凭证文件（默认 DENY）；
        - 允许读写 allowed_paths（如任务临时工作目录）；
        - 允许必要的读 /tmp / 系统库（不阻断 pytest 执行）；
        - 网络：默认拒绝所有出站（(allow network*) 需显式配置时才放开，
          保守口径与 Docker 出口管控同向——"无测试执行场景"下
          不需要网络，断网是安全的默认）。

    N-2（2026-10-17）细粒度放行面：`exec_paths`（仅执行，如解释器二进制/
    framework Python.app）、`read_paths`（只读，如 venv 根/pyvenv.cfg/stdlib/
    项目根）、`write_paths`（读写，如 pytest 临时目录 TMPDIR）。三者与
    allowed_paths（历史：读写+执行）叠加，互不隐含。

    Args:
        allowed_paths: 允许读写+执行的路径列表（任务工作目录等）。
        exec_paths: 仅允许执行的路径（文件用 literal、目录用 subpath）。
        read_paths: 只读放行的路径。
        write_paths: 读写放行的路径（不含执行）。

    Returns:
        Seatbelt profile 文本（sandbox-exec -p <profile> 消费）。
    """
    lines = ["(version 1)", "(deny default)"]
    # 根目录解析（2026-10-17 N-2 实测）：`deny default` 下执行任何二进制前
    # dyld/路径解析需要根目录与祖先目录的元数据；缺这两条时沙箱进程直接
    # SIGABRT（rc=-6，无任何错误输出），比缺具体路径更难诊断。
    # 只放行 metadata（stat）与根目录本身，不放开全盘内容读取。
    lines.append('(allow file-read* (literal "/"))')
    lines.append('(allow file-read-metadata (subpath "/"))')
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
        for variant in _realpath_variants(path):
            quoted = _sbpl_quote(variant)
            lines.append(f"(allow file-read* (subpath {quoted}))")
            lines.append(f"(allow file-write* (subpath {quoted}))")
    lines.extend(_sbpl_scope_rules("file-read*", read_paths))
    lines.extend(_sbpl_scope_rules("file-write*", write_paths))
    # 系统库（/usr）：pytest 解释器与 C 扩展依赖
    lines.append('(allow file-read* (subpath "/usr"))')
    lines.append('(allow file-read* (subpath "/System"))')
    lines.append('(allow file-read* (subpath "/Library"))')
    lines.append('(allow file-read* (subpath "/tmp"))')
    lines.append('(allow file-write* (subpath "/tmp"))')
    # macOS /tmp 是 /private/tmp 的符号链接：SBPL 按真实路径匹配，须同时放行
    lines.append('(allow file-read* (subpath "/private/tmp"))')
    lines.append('(allow file-write* (subpath "/private/tmp"))')
    # 标准设备节点（deny default 下极小放行）：pytest 捕获层需打开 /dev/null；
    # Python 启动/hash seed 需读 /dev/urandom；/dev/zero 供子进程常规使用。
    lines.append('(allow file-read* (literal "/dev/null"))')
    lines.append('(allow file-write* (literal "/dev/null"))')
    lines.append('(allow file-read* (literal "/dev/zero"))')
    lines.append('(allow file-read* (literal "/dev/urandom"))')
    lines.append('(allow file-read* (literal "/dev/random"))')
    lines.append("(allow sysctl-read)")
    # 进程：pytest 需 fork/exec，但限定可执行目标为 /usr 与 allowed_paths
    # （不再 (allow process*) 全放行——可 exec 任意二进制）
    lines.append("(allow process-fork)")
    lines.extend(
        f"(allow process-exec (subpath {_sbpl_quote(variant)}))"
        for path in allowed_paths
        for variant in _realpath_variants(path)
    )
    lines.extend(_sbpl_scope_rules("process-exec", exec_paths))
    lines.append('(allow process-exec (subpath "/usr"))')
    lines.append("(allow ipc*)")
    # S2 凭证文件显式 DENY（覆盖 allowed_paths 内误含的凭证路径）。
    # N-2（2026-10-17）**正则修正**：历史 `.env.*` 会把 `.venv/` 整棵虚拟环境树
    # 也 DENY（".venv" 含子串 ".env"）→ 沙箱内 Python 读 pyvenv.cfg/site-packages
    # 直接 PermissionError（venv 链路 100% 不可用；此前被 SBPL 语法错误掩盖）。
    # 现按"路径分量"匹配：`.env`/`.env.local` 等命中，`.venv` 不命中。
    lines.append(
        '(deny file-read* (regex #"(^|/)\\.env($|[./])|(^|/)\\.ssh($|/)|(^|/)\\.aws($|/)|'
        'llm_configs\\.json|credentials"))'
    )
    # 保守：不放开网络出站（本地执行场景默认断网，与 Docker 出口管控同向）
    return "\n".join(lines)


def _build_bwrap_command(
    args: list[str],
    cwd: str,
    allowed_paths: list[str],
    *,
    exec_paths: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
) -> list[str]:
    """生成 Linux bwrap（Landlock 口径）沙箱命令。

    口径（保守最小可用集）：
        - `--bind` 只挂载 allowed_paths + cwd + write_paths（其余路径不可见）；
        - `--ro-bind / /`（根文件系统只读）；
        - `--unshare-net`（断网，与 Docker --network=none 同向）；
        - `--die-with-parent`（沙箱随父进程终止，防孤儿进程）。

    N-2（2026-10-17）：`exec_paths` / `read_paths` 以只读方式挂载（解释器
    二进制/framework/venv 根必须可见才可执行），`write_paths` 以可写方式挂载
    （pytest 临时目录）。文件路径同样可 `--ro-bind`（bwrap 支持单文件绑定）。

    Args:
        args: 要在沙箱内执行的命令列表（如 ["python", "-m", "pytest", ...]）。
        cwd: 沙箱内工作目录。
        allowed_paths: 允许读写的路径列表。
        exec_paths: 仅需可见/可执行的路径（只读挂载）。
        read_paths: 只读挂载路径。
        write_paths: 可写挂载路径。

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
    for path in _dedupe_paths(allowed_paths, write_paths):
        cmd.extend(["--bind", path, path])
    # 只读可见/可执行路径（解释器、framework、venv 根、stdlib、项目根等）
    for path in _dedupe_paths(exec_paths, read_paths):
        cmd.extend(["--ro-bind", path, path])
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
    *,
    cwd_rw: bool = True,
    exec_paths: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """按当前平台生成内核沙箱命令 + 观测层字段。

    设计口径（fail-closed，不静默降级）：
        - 平台不支持（sandbox_supported() 为 False）→ 返回原命令 +
          obs["supported"]=False（调用方应拒绝执行，避免"以为
          隔离了其实没有"污染对比实验——与 executor_modes 的
          docker_unavailable 同口径）；
        - 平台支持 → 包装为沙箱命令 + obs["supported"]=True。

    N-2（2026-10-17）执行器接线：新增细粒度放行面（全部可选、默认行为不变）：
        - `cwd_rw=False`：cwd 只**只读**放行（不再自动进入可写 allowed_paths）
          ——执行器沙箱必须阻止写仓库根，但 pytest 需要读项目根配置；
        - `exec_paths`：仅执行放行（解释器 argv[0] 字面路径、realpath、
          framework Python.app 等；文件 literal / 目录 subpath）；
        - `read_paths`：只读放行（venv 根/pyvenv.cfg、framework 安装根、项目根）；
        - `write_paths`：读写放行（pytest 临时目录 TMPDIR、coverage 数据目录）。

    Args:
        args: 要执行的命令列表（如 ["python", "-m", "pytest", "test_generated.py"]）。
        cwd: 执行工作目录。
        allowed_paths: 额外允许读写的路径列表（默认 [cwd]）。
        cwd_rw: cwd 是否进入可写 allowed_paths（默认 True 保持历史行为；
            False 时 cwd 仅进 read_paths，防写仓库根）。
        exec_paths: 仅执行放行的路径列表（文件/目录均可）。
        read_paths: 只读放行的路径列表。
        write_paths: 读写放行的路径列表（不隐含执行）。

    Returns:
        (sandboxed_cmd, obs)：
            sandboxed_cmd: 沙箱包装后的完整命令列表（不支持时为原 args）；
            obs: 观测层 dict（platform / backend / supported /
                allowed_paths / exec_paths / read_paths / write_paths /
                profile_summary），纯观测不改结果口径。
    """
    paths = _dedupe_paths(allowed_paths)
    # cwd 语义：cwd_rw=True（历史）→ 可写 allowed_paths；False → 只读 read_paths
    read_all = _dedupe_paths(read_paths)
    write_all = _dedupe_paths(write_paths)
    exec_all = _dedupe_paths(exec_paths)
    if cwd:
        if cwd_rw:
            if cwd not in paths:
                paths.append(cwd)
        elif cwd not in read_all:
            read_all.append(cwd)

    if _seatbelt_available():
        profile = _seatbelt_profile(paths, exec_paths=exec_all, read_paths=read_all, write_paths=write_all)
        sandboxed_cmd = ["sandbox-exec", "-p", profile, *args]
        obs: dict[str, Any] = {
            "platform": _HOST_PLATFORM,
            "backend": "seatbelt",
            "supported": True,
            "allowed_paths": paths,
            "exec_paths": exec_all,
            "read_paths": read_all,
            "write_paths": write_all,
            "cwd_rw": bool(cwd_rw),
            "profile_summary": (
                f"{len(paths)} 路径写放行 + {len(read_all)} 只读 + {len(exec_all)} 仅执行 + 全文件系统只读 + 断网"
            ),
        }
        return sandboxed_cmd, obs

    if _landlock_available():
        sandboxed_cmd = _build_bwrap_command(
            args,
            cwd,
            paths,
            exec_paths=exec_all,
            read_paths=read_all,
            write_paths=write_all,
        )
        obs = {
            "platform": _HOST_PLATFORM,
            "backend": "landlock_bwrap",
            "supported": True,
            "allowed_paths": paths,
            "exec_paths": exec_all,
            "read_paths": read_all,
            "write_paths": write_all,
            "cwd_rw": bool(cwd_rw),
            "profile_summary": "bwrap 根只读 + 工作目录写 + 断网（Landlock 口径）",
        }
        return sandboxed_cmd, obs

    # S1（2026-09-29 审查 P0）：fail-closed —— 平台不支持时**抛
    # SandboxUnavailable**（不再返回原命令 + supported=False 让调用方
    # "忘检查 obs" 时 fail-open 裸跑）。设 ALLOW_UNSANDBOXED=true 可显式
    # 容忍无隔离（保守降级，供无沙箱工具的平台做本地调试，但工件须
    # 记录该档位）。
    _allow_unsandboxed = env_flag("ALLOW_UNSANDBOXED")
    obs_unsupported: dict[str, Any] = {
        "platform": _HOST_PLATFORM,
        "backend": "none",
        "supported": False,
        "allowed_paths": paths,
        "exec_paths": exec_all,
        "read_paths": read_all,
        "write_paths": write_all,
        "cwd_rw": bool(cwd_rw),
        "profile_summary": "当前平台无可用内核沙箱后端（fail-closed，拒绝执行）",
        "allow_unsandboxed": _allow_unsandboxed,
    }
    if not _allow_unsandboxed:
        # F12（2026-10-22 第三方复审）：不再把 ALLOW_UNSANDBOXED 宣传成"恢复本地
        # 执行"的开关——ExecutorAgent 只认 obs["supported"]，设了该开关仍拒绝
        # （同批已把 .env.example 与执行器提示改为补齐后端 / 走 Docker）。
        raise SandboxUnavailable(
            f"内核沙箱不支持当前平台（{_HOST_PLATFORM}），fail-closed 拒绝执行；"
            "请安装 bubblewrap / 启用 macOS Seatbelt，或改用 EXECUTOR_USE_DOCKER=true"
        )
    logger.warning("内核沙箱不支持当前平台（%s），ALLOW_UNSANDBOXED=true 容忍无隔离", _HOST_PLATFORM)
    return list(args), obs_unsupported


def interpreter_sandbox_allowances(python_executable: str | None = None) -> dict[str, list[str]]:
    """计算"在沙箱内运行该解释器"所需的最小放行路径集（exec/read 分离）。

    N-2（2026-10-17）执行器沙箱接线修复的核心数据：解释器启动到 pytest
    运行需要的不只是任务目录——`sys.executable`（venv 内是符号链接/包装器）
    的字面路径必须可执行、其 realpath（framework `Python.app`）必须可执行、
    venv 根的 `pyvenv.cfg` 与 site-packages、framework 安装根的 stdlib 必须
    可读。此前接线只放行任务目录 → `sandbox-exec: execvp() of
    '.../.venv/bin/python' failed: Operation not permitted`。

    口径（只读 + 仅执行，不扩大可写面）：
        - exec_paths：解释器 argv[0] 字面文件、realpath 文件、两者所在目录、
          framework/系统安装根（含 `Resources/Python.app`）；
        - read_paths：venv 根（存在 pyvenv.cfg 时）、安装根、解释器目录；
        - write_paths：空（临时目录由调用方按需加入，不在此处扩张可写面）。

    Args:
        python_executable: 解释器路径；None 时用当前 `sys.executable`。

    Returns:
        {"exec_paths": [...], "read_paths": [...], "write_paths": []}。
    """
    exe = str(python_executable or sys.executable)
    try:
        real = os.path.realpath(exe)
    except OSError:  # pragma: no cover - 极端文件系统异常
        real = exe
    exe_dir = os.path.dirname(os.path.abspath(exe))
    real_dir = os.path.dirname(os.path.abspath(real))
    # venv 根：exe 所在目录的父目录含 pyvenv.cfg（venv/bin/python 布局）
    venv_candidate = os.path.dirname(exe_dir)
    venv_root = venv_candidate if os.path.isfile(os.path.join(venv_candidate, "pyvenv.cfg")) else None
    # 安装根：realpath 的父目录的父目录（framework: .../Versions/3.14；系统: /usr）
    install_root = os.path.dirname(real_dir)
    exec_paths = _dedupe_paths([exe, real], [exe_dir, real_dir, install_root])
    read_paths = _dedupe_paths([venv_root] if venv_root else None, [install_root, exe_dir, real_dir])
    return {"exec_paths": exec_paths, "read_paths": read_paths, "write_paths": []}


#: 沙箱启动/配置失败特征（输出行前缀/子串；命中即应归为 kernel_sandbox_unavailable）。
_SANDBOX_LAUNCH_FAILURE_MARKERS: tuple[str, ...] = (
    "sandbox-exec: ",
    "bwrap: ",
    "execvp() of",
    "failed: Operation not permitted",
    "kernel sandbox",
)


def sandbox_launch_failure(output: str) -> str | None:
    """从子进程输出识别"沙箱启动/配置失败"（区别于被测测试真实失败）。

    N-2（2026-10-17）：沙箱 profile 语法错误（rc=65）/ 解释器 exec 被拒
    （rc=71）/ bwrap 配置失败等，此前会被 `build_error_info` 统一记为
    `test_failure`，把"沙箱配置故障"误报成"测试失败"，污染测量归因与修复
    循环（Debugger 会去修代码，而不是发现沙箱不可用）。命中特征时调用方应
    把 `error_info.type` 覆盖为显式 `kernel_sandbox_unavailable`（不新增
    ErrorCategory 枚举值，保持 BASELINE error_categories=18 口径不变）。

    Args:
        output: 子进程合并输出（stdout+stderr）。

    Returns:
        命中的首行诊断（截断 300 字符）；未命中返回 None。
    """
    text = str(output or "")
    if not text:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in _SANDBOX_LAUNCH_FAILURE_MARKERS):
            return stripped[:300]
    return None


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
    "interpreter_sandbox_allowances",
    "kernel_sandbox_enabled",
    "sandbox_launch_failure",
    "sandbox_supported",
]
