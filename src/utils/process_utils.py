"""子进程执行辅助：带**超时后可靠终止**的 `subprocess.run` 替代实现。

背景（2026-10-09 审查报告 §11.1b 结果十二：QuixBugs 批后挂死）
------------------------------------------------------------------
`subprocess.run(..., timeout=N)` 的标准库实现在超时后的行为**不足以保证返回**：

1. 它只 `kill()` **直接子进程**（`Popen.kill`），**不 kill 孙进程**——被测测试
   代码若自行 fork/生成子进程（pytest 插件、multiprocessing、被测代码内的
   `subprocess`），孙进程会**继承并继续持有 stdout/stderr 管道写端**；
2. 之后 `communicate()` 仍需读到 **EOF** 才返回，而 EOF 要等**所有**持有写端的
   进程退出——孙进程不死则**永久阻塞**。

实测证据（可复现）：`--dataset quixbugs` 跑满 50 任务后，主线程卡死在
`selectors.select → subprocess._communicate`，`%CPU 0.0`，**30+ 分钟不返回**，
批次 JSON 从未写出（`sample` 栈 1780/1780 命中同一调用链，落点
`src/tools/branch_coverage_inject.py:161`）。`EXECUTION_TIMEOUT`（30s）与
O3 超时（60s）只覆盖**单个子进程执行**，不覆盖"超时后无法回收"这一场景。

本模块的 `run_with_timeout` 三处加固：
- `start_new_session=True` → 子进程成为**新进程组组长**，可用
  `killpg` 一次终止整棵进程树（含孙进程）；
- 超时后 `killpg(SIGKILL)` 再**有限次尝试** `communicate(timeout=...)` 收口；
- 仍收不回时**放弃读取并返回**（标记 `timed_out=True`），**保证函数一定返回**
  —— 宁可丢一次测量结果，不可让整个批次挂死。

调用方按 `CompletedProcess.returncode` 与 `timed_out` 判定；返回值形状与
`subprocess.run` 兼容（`returncode` / `stdout` / `stderr` / `args`）。
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# 超时后收口阶段等待 EOF 的宽限期（秒）：足够正常进程退出，又不至于久等
_DRAIN_GRACE_SECONDS = 5.0


class CompletedProcess(subprocess.CompletedProcess[str]):
    """`subprocess.CompletedProcess` 的扩展：附加 `timed_out` 标记。

    继承以便调用方按原类型注解消费（`returncode` / `stdout` / `stderr`）。
    """

    def __init__(self, *args: Any, timed_out: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.timed_out = timed_out


def run_with_timeout(
    cmd: Sequence[str],
    *,
    timeout: float | None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    text: bool = True,
    logger_name: str = "",
) -> CompletedProcess:
    """执行子进程并在超时后**可靠**返回（kill 整个进程组 + 有界收口）。

    Args:
        cmd: 命令行参数序列（不经 shell）。
        timeout: 超时秒数；None 表示不设超时（仍走进程组语义）。
        cwd: 工作目录。
        env: 环境变量字典。
        text: 是否以文本模式捕获输出（默认 True）。
        logger_name: 日志中标识调用方的标签（便于定位是哪个测量层超时）。

    Returns:
        `CompletedProcess`：`returncode` 为 `-9`（被 SIGKILL）时表示超时终止；
        `timed_out=True` 明确标记超时。**本函数保证返回**（不会因孙进程持有
        管道而永久阻塞）。
    """
    label = logger_name or (os.path.basename(cmd[0]) if cmd else "subprocess")
    proc = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        start_new_session=True,  # 关键：新进程组，便于整树终止
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return CompletedProcess(proc.args, proc.returncode, out, err, timed_out=False)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc, label=label)
        # 有界收口：killpg 后进程树通常立即消亡，EOF 随之到达；
        # 仍收不回则放弃（不阻塞），返回空输出 + timed_out 标记。
        try:
            out, err = proc.communicate(timeout=_DRAIN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning(
                "%s：超时后进程组仍持有管道（%.0fs 宽限内未收口），放弃读取并返回（避免批次挂死）",
                label,
                _DRAIN_GRACE_SECONDS,
            )
            out, err = "", ""
            _close_quietly(proc)
        return CompletedProcess(proc.args, proc.returncode, out, err, timed_out=True)


def _terminate_process_group(proc: subprocess.Popen[str], *, label: str) -> None:
    """终止子进程**及其整个进程组**（含孙进程），失败时回退到 kill()。"""
    killed_group = False
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        killed_group = True
    except (ProcessLookupError, PermissionError, OSError) as e:
        logger.debug("%s：killpg 失败（%s），回退 kill()", label, e)
    if not killed_group:
        with contextlib.suppress(OSError):  # pragma: no cover - 进程已消亡
            proc.kill()


def _close_quietly(proc: subprocess.Popen[str]) -> None:
    """尽力关闭管道，避免 fd 泄漏（进程仍存活时 close 可能抛错，忽略）。"""
    for stream in (proc.stdout, proc.stderr, proc.stdin):
        if stream is not None:
            with contextlib.suppress(OSError):  # pragma: no cover - 已被回收
                stream.close()
