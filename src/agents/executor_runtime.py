"""
测试执行器基础设施：子进程运行、超时重试与临时资源清理。

拆分自 executor.py（结构优化轮次）：ExecutorAgent 的类主体保留在
executor.py，本模块承载三条执行链路共用的底层能力——
带重试的 pytest 子进程执行（_run_pytest_with_retry）与临时文件/沙箱目录清理
（_cleanup_temp_file / _cleanup_sandbox）。
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from typing import Any

try:
    import resource  # POSIX only; Windows 下 import 失败 → 静默降级

    _RLIMIT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RLIMIT_AVAILABLE = False

logger = logging.getLogger(__name__)

# S5 平台兜底（2026-10-01 主批次实跑发现）：macOS（Darwin）上
# resource.setrlimit(RLIMIT_AS, ...) 在 preexec_fn 内调用会抛
# SubprocessError("Exception occurred in preexec_fn")——macOS 对 RLIMIT_AS
# 的限制行为与 Linux 不同（Python 3.14 解释器 + pytest + coverage 虚拟
# 地址空间轻松超过 512MB，且 setrlimit 本身在 fork 后 exec 前对 AS
# 的限制在 Darwin 上不稳定）。此前 S5 仅检查 RLIMIT_AVAILABLE（import
# resource 成功）与平台 ∈ {Linux, Darwin}，未考虑 macOS 上 AS 限制
# 会导致**所有**子进程 pytest 直接 SubprocessError 失败（主批次 0/5
# 全失败即此原因）。
# 兜底口径：Darwin 平台**跳过** RLIMIT_AS（保留 CPU / NPROC / FSIZE /
# NOFILE 四项有效防线），Linux 保持全五项；可经 EXECUTOR_RLIMIT_AS_MB
# 设为 0 在 Linux 上手动禁用 AS 限制。
_IS_DARWIN = platform.system() == "Darwin"

# AS 限制平台兜底（2026-10-01 主批次实跑发现）：macOS（Darwin）上
# **任何** resource.setrlimit(RLIMIT_AS, ...) 调用都会抛 SubprocessError
# （本机 Python 3.14 实测：fresh 进程 RLIMIT_AS 软/硬限均为无上限，
# setrlimit(AS, 2GB) / (AS, 128GB) / (AS, current+1) 均 SubprocessError——
# Darwin 对该 rlimit 的限制整体不支持）。若强行 setrlimit(AS) 会导致
# **所有**子进程 pytest 直接失败（主批次 0/5 全失败即此原因）。
# 兜底口径：Darwin 平台**默认跳过** RLIMIT_AS（保留 CPU / NPROC /
# FSIZE / NOFILE 四项有效防线），Linux 保持全五项；显式
# EXECUTOR_RLIMIT_AS_FORCE=1 可在 Darwin 上强制启用 AS（自担风险，
# 若平台不支持会重现场）。


def _make_resource_preexec_fn() -> Any | None:
    """返回 preexec_fn 闭包（在子进程 exec 前设 resource.setrlimit）。"""
    if not _RLIMIT_AVAILABLE or (platform.system() not in ("Linux", "Darwin")):
        return None
    _cpu_limit = int(os.getenv("EXECUTOR_RLIMIT_CPU", "300"))
    _as_limit_mb = int(os.getenv("EXECUTOR_RLIMIT_AS_MB", "512"))
    _nproc_limit = int(os.getenv("EXECUTOR_RLIMIT_NPROC", "512"))
    _FSIZE_limit_mb = int(os.getenv("EXECUTOR_RLIMIT_FSIZE_MB", "100"))
    _nofile_limit = int(os.getenv("EXECUTOR_RLIMIT_NOFILE", "256"))
    # Darwin 平台兜底：默认跳过 AS（setrlimit(AS) 在 macOS 上整体不支持）；
    # 显式 EXECUTOR_RLIMIT_AS_FORCE=1 时强制启用（Linux 口径不变）。
    _as_force = os.getenv("EXECUTOR_RLIMIT_AS_FORCE", "0") == "1"
    _enable_as = _as_force or not _IS_DARWIN

    def _preexec_fn() -> None:
        # CPU 时间（软限 = 300s，到时后 SIGXCPU 终止子进程）
        resource.setrlimit(resource.RLIMIT_CPU, (_cpu_limit, _cpu_limit))
        # 虚拟地址空间（Linux 全量；Darwin 默认跳过——见模块顶注：
        # setrlimit(AS) 在 macOS 上整体不支持，强设会 SubprocessError）
        if _enable_as:
            _as_bytes = _as_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (_as_bytes, _as_bytes))
        # 最大子进程数（fork 炸弹防线；非 root 时硬限生效）
        resource.setrlimit(resource.RLIMIT_NPROC, (_nproc_limit, _nproc_limit))
        # 文件大小（防 LLM 代码写满磁盘）
        _FSIZE_bytes = _FSIZE_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_bytes, _FSIZE_bytes))
        # 文件描述符上限（防无界 open）
        resource.setrlimit(resource.RLIMIT_NOFILE, (_nofile_limit, _nofile_limit))

    return _preexec_fn


def _to_str(value: str | bytes | None) -> str:
    """将 subprocess.TimeoutExpired 的 output/stderr 字段安全转为字符串。

    2026-09-26 优化：从 run_pytest_with_retry 内部闭包提升为模块级函数
    （此前每次 TimeoutExpired 都重新创建闭包对象，热路径上无谓分配）。
    本调用点恒传 text=True，运行期 output/stderr 为 str 或 None；mypy 按
    类型联合（str | bytes | None）报 "+" 运算，显式转 str 收窄
    （bytes 分支仅静态可达性兜底，运行期不会触发）。
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_pytest_with_retry(self, cmd: list[str], env: dict[str, str], project_root: str) -> tuple[str, Any]:
    """
    带重试的 pytest 执行逻辑，最多尝试 2 次。
    超时/环境问题直接返回 EARLY_RETURN 标记，其他异常仅记录日志并保留最近一次有效结果。

    由 ExecutorAgent 实例调用（self.timeout 为单次超时秒数）。

    Returns:
        (output, last_result) 元组：last_result 为 subprocess.CompletedProcess、
        ("EARLY_RETURN", error_info) / ("UNAVAILABLE", error_info) 标记元组或 None。
        2026-09-26 round9 P2：通用异常不再把 last_result 置 None（保留最近一次
        有效结果，仅追加异常现场文本）；无任何有效结果时返回 ("UNAVAILABLE", …)
        标记，下游按 EARLY_RETURN 分支处理（isinstance(last_result, tuple) 统一）。
    """
    max_attempts = 2
    last_output = ""
    # 2026-09-26 round9 P2：last_result 类型为 CompletedProcess | tuple | None——
    # ("EARLY_RETURN"/"UNAVAILABLE", error_info) 标记元组与 None（未运行）
    # 三种形态之一；mypy 需显式 Any 联合（历史调用方按 .returncode 属性访问
    # CompletedProcess，标记元组由 isinstance(last_result, tuple) 守卫分流）。
    last_result: Any = None

    for attempt in range(max_attempts):
        try:
            # S5（2026-09-29 审查 P0）：子进程资源限制（preexec_fn + rlimit）
            # —— 此前仅约束墙钟（timeout=self.timeout），无 rlimit：
            # LLM 生成代码内 fork 炸弹 / 大内存 / 无界 print 可打满宿主
            # RSS / fd / 进程表。现通过 preexec_fn 在子进程 exec 前
            # 设 resource.setrlimit（POSIX；Windows 静默跳过，历史不变）。
            _preexec = _make_resource_preexec_fn()
            _preexec_fn_arg = {"preexec_fn": _preexec} if _preexec is not None else {}
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=project_root,
                env=env,
                **_preexec_fn_arg,
                check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
            )
            last_result = result
            last_output = result.stdout + result.stderr
            if result.returncode == 0:
                break
            logger.warning("第 %d 次执行失败，尝试重试...", attempt + 1)
        except subprocess.TimeoutExpired as e:
            # 本调用点恒传 text=True，运行期 output/stderr 为 str 或 None；
            # _to_str 收窄类型联合（bytes 分支仅静态可达性兜底）。
            # 追加进 last_output（而非覆盖），让下游 Debugger 能拿到前次有效
            # 输出 + 本次超时快照，而非仅超时的部分文本。
            # 2026-09-26 round10 P2：旧实现 last_output = partial_output 直接
            # 覆盖，第 1 次执行失败（rc≠0）后第 2 次超时且部分输出为空时，
            # 下游丢失第 1 次的真实 pytest 输出（修复线索）——对齐 round9 通用
            # 异常分支的追加口径。单次超时场景 last_output 原为空串，结果不变。
            partial_output = _to_str(e.output) + _to_str(e.stderr)
            last_output = (
                f"{last_output or ''}\n[timeout attempt {attempt + 1}] {partial_output}"
                if last_output
                else partial_output
            )
            error_msg = f"测试执行超时（>{self.timeout}s）"
            logger.error("测试执行超时（>%ds）: %s", self.timeout, e)
            error_info = {
                "type": "timeout",
                "message": error_msg,
                "timeout_seconds": self.timeout,
                "command": " ".join(cmd[:5]) if len(cmd) > 5 else " ".join(cmd),
            }
            # 超时/环境错误需由调用方直接 return，这里用特殊标记
            return last_output, ("EARLY_RETURN", error_info)
        except FileNotFoundError as e:
            error_msg = "执行环境错误（找不到 pytest 或 Python 解释器）"
            logger.error("执行环境错误（找不到 pytest）: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "file_not_found",
                    "message": error_msg,
                    "detail": str(e),
                },
            )
        except PermissionError as e:
            error_msg = "权限不足，无法执行测试文件"
            logger.error("权限错误: %s", e)
            return last_output, (
                "EARLY_RETURN",
                {
                    "type": "permission_error",
                    "message": error_msg,
                    "file_path": str(e.filename) if hasattr(e, "filename") else "",
                },
            )
        except Exception as e:
            error_msg = f"测试执行异常: {type(e).__name__}: {e}"
            logger.error("测试执行异常: %s", e)
            # 2026-09-26 round9 P2：通用异常不销毁 last_result（保留最近一次
            # 有效结果），仅追加异常现场文本。旧实现在第 2 次重试抛通用异常
            # 时把第 1 次失败的 last_result 置 None → 下游判"未运行"，丢失
            # 第 1 次的真实测试输出（passed/failed_cases 全空）。保守修复：
            # 有 last_result 时仅追加文本，无时标记 "UNAVAILABLE"（与 EARLY_RETURN
            # 同走 EARLY_RETURN 分支下游不会误读 .returncode）。
            if last_result is None:
                last_result = ("UNAVAILABLE", {"type": "execution_exception", "message": error_msg})
                last_output = error_msg
            else:
                last_output = f"{last_output or ''}\n[retry {attempt + 1} exception] {error_msg}"
            break

    return last_output, last_result


def cleanup_temp_file(test_file: str) -> None:
    """清理临时测试文件，失败时仅记录警告。"""
    try:
        if os.path.exists(test_file):
            os.unlink(test_file)
            logger.debug("已清理临时测试文件: %s", test_file)
    except OSError as e:
        logger.warning("清理临时文件失败: %s", e)


def cleanup_sandbox(sandbox_dir: str) -> None:
    """清理沙箱临时目录，失败仅记录警告（venv 缓存目录不受影响）。"""
    try:
        if os.path.isdir(sandbox_dir):
            import shutil

            shutil.rmtree(sandbox_dir, ignore_errors=True)
            logger.debug("已清理沙箱目录: %s", sandbox_dir)
    except OSError as e:
        logger.warning("清理沙箱目录失败: %s", e)
