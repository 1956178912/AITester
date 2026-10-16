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
import shutil
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# 超时后收口阶段等待 EOF 的宽限期（秒）：足够正常进程退出，又不至于久等
_DRAIN_GRACE_SECONDS = 5.0

# 宿主 pytest 配置键：嵌套 pytest 子进程**不得**继承。
_HOST_PYTEST_ENV_KEYS: tuple[str, ...] = ("PYTEST_PLUGINS", "PYTEST_ADDOPTS")


def nested_pytest_env(**overrides: str) -> dict[str, str]:
    """为"tmp 目录里再跑一次 pytest"的子进程构造 env（剔除宿主 pytest 配置）。

    历史口径是 ``env={**os.environ, "PYTHONPATH": tmpdir, ...}``：整体继承宿主
    环境，同时把 ``PYTHONPATH`` 覆盖成 tmpdir。这两件事叠加会**静默改写测量结果**
    ——宿主若设了 ``PYTEST_PLUGINS``（插件在宿主 sys.path 上、不在 tmpdir 上），
    嵌套 pytest 会在**收集之前**就 ImportError 退出 rc=1。

    实测复现（2026-10-16 H 轮）：宿主 ``PYTEST_PLUGINS=<不可导入模块>`` 时，
    ``detection_gates._run_test_against_code`` 把这次 rc=1 读成"测试红"，
    ``specificity_verdict`` 遂判 ``over_red``（正确结论应是 ``unavailable``——
    根本没跑起来）。即宿主的 pytest 配置能让 M1 检出裁决与 AC2 双门得出
    **与被测代码无关**的结论，且日志里看不出任何异常。

    ``PYTEST_ADDOPTS`` 同理：宿主追加的 ``-p`` / ``--cov`` 等选项会落到嵌套
    运行上，改变 rc 与输出形态。

    干净环境（两者均未设）下本函数与 ``{**os.environ, **overrides}`` 逐位等价，
    零行为变化。

    Args:
        **overrides: 需要显式设置的键（如 ``PYTHONPATH=tmpdir``），优先级最高。

    Returns:
        可直接传给 ``run_with_timeout(env=...)`` 的完整环境字典。
    """
    env = {k: v for k, v in os.environ.items() if k not in _HOST_PYTEST_ENV_KEYS}
    env.update(overrides)
    return env


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
    preexec_fn: Any = None,
    raise_on_timeout: bool = False,
    check: bool = False,
    capture_output: bool | None = None,  # 兼容裸 subprocess.run 调用位的透明参数（文件后端忽略）
) -> CompletedProcess:
    """执行子进程并在超时后**可靠**返回（整树终止 + **文件后端**收口）。

    2026-10-10 第二次加固（实跑复现后的根因修复）
    -------------------------------------------------
    首版仍用 `stdout=PIPE` + `communicate()`：即使 killpg 杀掉整个进程组，
    只要**任一孙进程在 killpg 之前已 fork 且未被同一进程组覆盖**（或
    killpg 与 fork 竞态），管道写端仍可能存活，`communicate()` 等 EOF
    **依然可能永久阻塞**——实测在 `to_base` 任务上再次挂死（外层 30s
    超时已过、子进程 88% CPU 空转、主进程 0% CPU 持有 3 个 PIPE）。

    **根因级修法：改用临时文件承接 stdout/stderr，彻底不用管道。**
    子进程写的是**普通文件**，父进程读取不依赖 EOF，因此"孙进程持有写端"
    这一阻塞条件在结构上不再存在——无论孙进程是否存活，本函数都必然返回。
    进程组终止（killpg）仍保留，用于回收资源。

    Args:
        cmd: 命令行参数序列（不经 shell）。
        timeout: 超时秒数；None 或 0 表示不设超时（仍走进程组语义）。
        cwd: 工作目录。
        env: 环境变量字典。
        text: 是否以文本模式返回输出（默认 True）。
        logger_name: 日志中标识调用方的标签。
        preexec_fn: 可选，子进程 exec 前钩子（执行器链路用于设 rlimit）。
        raise_on_timeout: 超时时是否抛 `subprocess.TimeoutExpired`（附
            `.stdout`/`.stderr` 部分输出），以兼容原有
            `except subprocess.TimeoutExpired` 分支。默认 False = 返回
            `CompletedProcess(timed_out=True)`（历史口径，现有调用方不变）。
        capture_output: 兼容裸 `subprocess.run(capture_output=True)` 调用位
            的透明参数（本实现以文件后端承接输出，无需管道；参数被忽略）。
        check: 为 True 且进程以非零码退出时抛 `CalledProcessError`
            （与 `subprocess.run(check=True)` 同语义）。

    Returns:
        `CompletedProcess`（附加 `timed_out` 标记）。**本函数保证返回**。
    """
    label = logger_name or (os.path.basename(cmd[0]) if cmd else "subprocess")
    popen_kwargs: dict[str, Any] = {}
    if preexec_fn is not None:
        # 执行器链路既需要 rlimit（S5 防 fork 炸弹/内存/fd 打满宿主），又需要
        # 本函数的整树终止（防"超时后孙进程持管道写端 → 永久阻塞"）。
        # 早期二者只能择一（裸 subprocess.run 支持 preexec_fn 但会挂死；
        # 本函数不挂死但不支持 preexec_fn），现同时提供——POSIX 上
        # start_new_session 与 preexec_fn 均为 fork 后 exec 前的钩子，可共存。
        popen_kwargs["preexec_fn"] = preexec_fn

    tmpdir = tempfile.mkdtemp(prefix="aitester_proc_")
    out_path = os.path.join(tmpdir, "stdout")
    err_path = os.path.join(tmpdir, "stderr")
    timed_out = False
    try:
        # 文件后端：不建管道 → 不存在"等 EOF"阻塞（见 docstring 根因说明）
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            proc = subprocess.Popen(
                list(cmd),
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                start_new_session=True,  # 关键：新进程组，便于整树终止
                **popen_kwargs,
            )
            try:
                # timeout=0（falsy）与 None 同义"不设超时"——历史调用点
                # （executor_repo._run / patch_rollback）以 timeout=0 表达
                # "本调用不额外设上限"；Popen.wait(0) 立即抛 TimeoutExpired
                # 会误触发整树 kill，故 0/None 归一为等待至进程自然退出。
                # 负值保守归一为 None（不臆测调用意图）。
                effective_timeout = timeout if timeout and timeout > 0 else None
                proc.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_group(proc, label=label)
                # killpg 后主进程应立即消亡；给一个很短的等待，拿不到就继续
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=_DRAIN_GRACE_SECONDS)
        out = _read_output(out_path, text=text)
        err = _read_output(err_path, text=text)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if timed_out:
        logger.warning(
            "%s：执行超时（>%ss），已终止整个进程组并返回（文件后端，不会挂死）",
            label,
            timeout,
        )
        if raise_on_timeout:
            raise subprocess.TimeoutExpired(list(cmd), timeout or 0, output=out, stderr=err)
        return CompletedProcess(proc.args, -9, out, err, timed_out=True)

    result = CompletedProcess(proc.args, proc.returncode, out, err, timed_out=False)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return result


def _read_output(path: str, *, text: bool) -> Any:
    """读取临时文件输出（文件不存在/读取失败时保守返回空串，不抛异常）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:  # pragma: no cover - 极端 IO 异常
        raw = b""
    if text:
        return raw.decode("utf-8", errors="replace")
    return raw


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
