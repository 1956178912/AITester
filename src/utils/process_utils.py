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

M-3 加固（2026-10-17）：**父进程死亡缺口** —— 孤儿 pytest 根因修复
----------------------------------------------------------------
L 轮正式批实测 1 例 M1 判分孤儿（PID 57034，ppid=1，~98% CPU，age 9m42s）；
现场残留证据（`experiments/results/orphan_repro_20261017/evidence_l_batch_leftovers.log`）
显示 M1 判分 tmpdir 与 `run_with_timeout` 文件后端 tmpdir **同秒出生且都未被
finally 清理** ⇒ 调用进程在超时分支**之前**被外部异常杀死。`start_new_session=True`
让子进程自成会话（为整树 killpg 服务）的代价是：**调用方进程被外部杀死时
（SIGKILL / harness 超时 / CI 取消），子进程不会被连带回收**——macOS 无
`PR_SET_PDEATHSIG` 等价物，子进程被 init/launchd 收养后继续空转。

两层修复：

1. **超时路径两段式终止**（`_terminate_process_group`）：先 `killpg(SIGTERM)`
   给组内进程自清理机会（`_TERMINATE_GRACE_SECONDS`，可经 `terminate_grace=`
   覆盖），宽限后**总是**再 `killpg(SIGKILL)` 清扫（含"组长已退出、组内仍有
   成员"的场景）——整树终止语义不变，只是多了优雅阶段。
2. **父死亡看门狗**（`orphan_guard=True`，默认关、按调用点启用）：
   `run_with_timeout` 先起一个监督进程（也在新会话），由它再起真正的命令
   （同一进程组）；监督进程每 0.1s 检查 `os.getppid() != 原始父 PID`，
   一旦父进程消亡立即 `killpg(SIGKILL)` 回收命令进程组并以 143 退出。
   这样"调用方被外部 SIGKILL"时孙进程不会成为孤儿；超时路径仍由
   `killpg` 整组回收（监督进程与命令同组，一并终止）。

已知边界（残余风险，见复现 S4）：命令**自身**再 `start_new_session=True`
的子进程仍会逃逸出看门狗可触达的进程组（任何进程组信号都到不了），
需要调用点自行避免该形态；`orphan_guard` 与 `preexec_fn` 不能同用（看门狗
无法转发任意 Python 钩子），同时给出会 fail-closed 抛 `ValueError`。

A08 / A12 加固（2026-10-18 第三方评审）
----------------------------------------
- **A08（P0，凭证边界）**：新增 ``untrusted_exec_env()`` 作为"执行不可信
  代码"的**统一最小环境构造器**（最小白名单 + 嵌套 pytest 运行期必需键 +
  显式 overrides）；``nested_pytest_env`` 委托它。M1 判分 / MDO / P2P 等
  旁路执行面不再把宿主 ``LLM_*_API_KEY`` / ``OPENAI_API_KEY`` / ``AWS_*`` 等
  凭证继承进执行 LLM 生成代码的子进程。
- **A12（P1，Windows 回收）**：``_terminate_process_group`` 增加
  ``_is_windows()``（可注入）平台分支——Windows 用 ``taskkill /T /F``
  整树回收 + ``process.kill()`` 兜底 + 有界等待直接子进程；看门狗内嵌脚本
  同步平台分支。POSIX 行为（两段式 killpg）逐字不变。
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# 超时后收口阶段等待 EOF 的宽限期（秒）：足够正常进程退出，又不至于久等
_DRAIN_GRACE_SECONDS = 5.0

# 超时后先 SIGTERM、再 SIGKILL 之间的宽限期（秒）：足够可响应进程自清理
# （pytest 落盘 / 临时目录 / 子进程回收），又不至于显著拉长超时路径。
# 调用点可经 run_with_timeout(terminate_grace=...) 覆盖（0–10s 归一）。
_TERMINATE_GRACE_SECONDS = 0.5

# 父死亡看门狗脚本（`orphan_guard=True` 时以 `python -c <脚本> <父PID> <cmd...>`
# 启动）。只用标准库：它运行在 tmpdir / 干净 PYTHONPATH 下，不得 import 项目模块。
# 协议：argv[1]=调用方 PID，argv[2:]=真实命令；命令与看门狗同进程组（新会话由
# run_with_timeout 的 start_new_session 建立），因此超时 killpg 可一次回收两者；
# 看门狗唯一职责是**父进程死亡时立即回收命令进程组**（与"超时"互补的两条路径）。
#
# A12（2026-10-18 第三方评审 P1）平台分支：Windows 无 ``os.getpgid`` /
# ``os.killpg``，历史脚本在父进程死亡路径上会 AttributeError 逃逸（看门狗
# 崩溃 → 命令进程树没人回收）。现按 ``os.name == "nt"`` 分流：POSIX 保持
# killpg 整组终止；Windows 用 ``taskkill /T /F /PID`` 整树回收，失败回退
# ``child.kill()`` 并**等待直接子进程**，保证命令进程至少被回收/收尸。
# 单测可 exec ``_ORPHAN_GUARD_HELPERS`` 后改写 ``_IS_WINDOWS`` 全局模拟
# Windows 分支（不启动/终止真实进程）。
_ORPHAN_GUARD_HELPERS = r"""
import os
import signal
import subprocess
import sys
import time

_POLL_INTERVAL_S = 0.1
# 平台判定常量：Windows 无 os.getpgid/killpg。单测在 exec 本段后可改写该
# 全局（进程内模拟），不依赖真实 Windows 宿主。
_IS_WINDOWS = os.name == "nt"


def _kill_child_group(child):
    # 回收命令进程树：POSIX killpg 整组；Windows taskkill /T /F。
    if _IS_WINDOWS:
        _kill_child_group_windows(child)
        return
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
    except OSError:
        try:
            child.kill()
        except OSError:
            pass


def _kill_child_group_windows(child):
    # Windows：taskkill /T /F 终止整棵进程树；不可用/失败回退 kill()。
    # 无论走哪条分支都等待直接子进程（有界），避免看门狗先退出留下未收尸子进程。
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(child.pid)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        child.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except OSError:
            pass
        try:
            child.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
"""

_ORPHAN_GUARD_SCRIPT = (
    _ORPHAN_GUARD_HELPERS
    + r"""
if len(sys.argv) < 3:
    sys.exit(2)
_parent_pid = int(sys.argv[1])
_cmd = sys.argv[2:]

# 竞态兜底：调用方可能在监督进程 exec 前就已死亡（此时 getppid 已不是原始父 PID）
if os.getppid() != _parent_pid:
    sys.exit(143)

child = subprocess.Popen(_cmd)
while True:
    returncode = child.poll()
    if returncode is not None:
        sys.exit(returncode if returncode >= 0 else 128 - returncode)
    if os.getppid() != _parent_pid:
        # 调用方已死：命令进程组（含孙进程）立即回收，然后自己退出成"已回收"
        _kill_child_group(child)
        try:
            child.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        sys.exit(143)
    time.sleep(_POLL_INTERVAL_S)
"""
)

# 宿主 pytest 配置键：嵌套 pytest 子进程**不得**继承。
_HOST_PYTEST_ENV_KEYS: tuple[str, ...] = ("PYTEST_PLUGINS", "PYTEST_ADDOPTS")

# ─── 不可信代码执行环境（A08，2026-10-18 第三方评审 P0）─────────────────────
#
# 背景：``nested_pytest_env`` 历史实现只剔除上面两个宿主 pytest 配置键，其余
# 宿主环境原样进入"执行 LLM 生成测试 / 补丁 / 探针"的子进程。评分（M1）、
# MDO、P2P 回归等**旁路执行面**因此绕过主 Executor 既有的凭证脱敏
# （``credential_scrub.scrub_os_environ`` / venv / Docker 链路），宿主若配置了
# ``LLM_*_API_KEY`` / ``OPENAI_API_KEY`` / ``AWS_*`` / ``MYSQL_PASSWORD`` /
# ``SSH_AUTH_SOCK`` 等，生成代码可读取并外传——威胁模型（docs/threat_model.md）
# 承诺的"不可信代码只得最小环境"在这些入口失效。
#
# 修复口径（A08 验收）：**统一最小白名单**（复用 ``credential_scrub.build_minimal_env``
# 的"默认拒绝"实现，避免两套名单漂移）+ 下面这组"嵌套 pytest 运行期必需、
# 且不承载凭证"的键 + 显式 overrides。白名单外的键（含全部凭证 / 宿主 pytest
# 配置 / 覆盖率注入 / 档位开关）一律不进入子进程——新增凭证变量无需改名单。
#
# 注意：``build_minimal_env()`` 是无条件白名单（不读
# ``CREDENTIAL_SCRUB_WHITELIST_ENABLE`` 开关）——不可信评分子进程始终最小化，
# 宿主不能用该开关把凭证重新放回判分子进程。
#
# 不继承 ``PYTHONWARNINGS`` / ``COVERAGE_*`` / ``TZ`` 等宿主运行期变量是**有意**
# 的：它们能改变 pytest 退出码/输出口径（测量伪影），不属于"被测代码必需"。
_UNTRUSTED_EXEC_PRESERVE_KEYS: frozenset[str] = frozenset(
    {
        # 测量确定性 / 解释器行为（非凭证；部分站点显式传 0 或 1，其余沿用宿主）
        "PYTHONDONTWRITEBYTECODE",  # 判分 tmpdir 不落 .pyc（与 -B 同义）
        "PYTHONHASHSEED",  # 固定哈希随机化 → 跨运行可复现
        "PYTHONUTF8",  # 跨平台文本编码口径
        "COLUMNS",  # pytest 输出宽度（部分站点显式覆盖 200）
        # ── Windows 平台必需：缺失时 Python/subprocess 启动、临时目录、
        # 动态库解析可能异常（本机 macOS 无法实跑，按 CPython/Windows 通用
        # 约定补齐；均为 OS 非敏感变量）──
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
)


def untrusted_exec_env(**overrides: str) -> dict[str, str]:
    """构造"执行不可信代码"的最小环境（A08/P0 统一构造器）。

    用于所有会执行 **LLM 生成测试 / 补丁 / 行为探针** 的子进程入口
    （M1 判分、MDO、P2P 回归、门/重放等委托原语，以及嵌套 pytest 站点）：

    1. 以 ``credential_scrub.build_minimal_env()`` 的**最小白名单**为基底
       （PATH / HOME / TMP* / LANG / PYTHONPATH / SSL 证书等非敏感基础键，
       默认拒绝其余一切键——凭证、宿主 pytest 配置、覆盖率注入、档位开关
       都不会进入不可信子进程）；
    2. 叠加 ``_UNTRUSTED_EXEC_PRESERVE_KEYS``（嵌套 pytest 运行期确定性 +
       Windows 平台必需键，仅在宿主实际设置时保留）；
    3. 显式 ``overrides`` 最后覆盖（调用点声明"本子进程确实需要"的键，如
       ``PYTHONPATH=tmpdir`` / ``PYTHONDONTWRITEBYTECODE=1``）。overrides 是
       可信调用点的显式声明，**不会被凭证规则再次剔除**。

    与历史 ``{**os.environ, **overrides}`` 的差异：非白名单宿主键不再继承。
    这既是安全边界，也消除"宿主运行期变量静默改写测量口径"的同类伪影
    （例如宿主 ``PYTHONWARNINGS=error`` / ``COVERAGE_*`` 不应影响判分）。

    Args:
        **overrides: 需要显式设置的键（优先级最高，值按原样写入）。

    Returns:
        可直接传给 ``run_with_timeout(env=...)`` 的最小环境字典。
    """
    # 函数内延迟导入：process_utils 位于依赖链底层（explore/measurement 都
    # import 它），避免模块加载期把 config 侧依赖带进所有调用方。
    from src.utils.credential_scrub import build_minimal_env

    env: dict[str, str] = build_minimal_env()
    for key in _UNTRUSTED_EXEC_PRESERVE_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    # 防御性二次剔除：即使未来最小白名单被扩大，也绝不把宿主 pytest 配置
    # 带进嵌套运行（H 轮实测：不可导入的 PYTEST_PLUGINS → rc=1 被读成"测试红"）。
    for key in _HOST_PYTEST_ENV_KEYS:
        env.pop(key, None)
    env.update(overrides)
    return env


def nested_pytest_env(**overrides: str) -> dict[str, str]:
    """为"tmp 目录里再跑一次 pytest"构造 env（``untrusted_exec_env`` 兼容别名）。

    历史（H 轮 2026-10-16）：本函数只剔除宿主 ``PYTEST_PLUGINS`` /
    ``PYTEST_ADDOPTS``，其余环境整体继承。宿主若设了 ``PYTEST_PLUGINS``
    （插件在宿主 sys.path 上、不在 tmpdir 上），嵌套 pytest 会在**收集之前**
    就 ImportError 退出 rc=1；``detection_gates`` 把 rc=1 读成"测试红"，
    ``specificity_verdict`` 遂判 ``over_red``（正确结论应是 ``unavailable``）。

    A08（2026-10-18 第三方评审 P0，凭证边界）：单纯剔除两个 pytest 键**不是**
    安全边界——M1/MDO/P2P 等评分旁路会把宿主凭证继承进执行 LLM 生成代码的
    子进程。现委托 ``untrusted_exec_env``：最小白名单 + pytest 运行期键 +
    overrides，凭证与宿主 pytest 配置都不再进入嵌套运行。

    语义变化（有意，安全默认）：
    - 宿主 pytest 配置（``PYTEST_PLUGINS`` / ``PYTEST_ADDOPTS``）仍剔除；
    - 宿主凭证（``LLM_*_API_KEY`` / ``OPENAI_API_KEY`` / ``AWS_*`` /
      ``MYSQL_PASSWORD`` 等）与其余非白名单键不再继承；
    - 嵌套 pytest 必需项（PATH / HOME / TMPDIR / PYTHONPATH /
      PYTHONDONTWRITEBYTECODE / PYTHONHASHSEED / LANG / SSL 证书等）保留；
    - 显式 overrides（如 ``PYTHONPATH=tmpdir``）优先级最高。

    Args:
        **overrides: 需要显式设置的键（如 ``PYTHONPATH=tmpdir``），优先级最高。

    Returns:
        可直接传给 ``run_with_timeout(env=...)`` 的最小环境字典。
    """
    return untrusted_exec_env(**overrides)


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
    terminate_grace: float | None = None,
    orphan_guard: bool = False,
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

    2026-10-17 M-3 加固（父进程死亡缺口，孤儿 pytest 根因）
    ------------------------------------------------------
    见模块 docstring。两点：① 超时路径先 `SIGTERM` 宽限再 `SIGKILL` 清扫
    （`terminate_grace` 可配）；② `orphan_guard=True` 时先起父死亡看门狗
    （监督进程 + 真实命令同进程组），调用方被外部 SIGKILL 时由看门狗回收
    命令进程组，不再产生 ppid=1 的孤儿。默认关（按调用点启用，避免给所有
    调用面增加一层进程与启动开销）；与 `preexec_fn` 同用会 fail-closed 抛
    `ValueError`。

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
        terminate_grace: 超时后 SIGTERM 与 SIGKILL 之间的宽限秒数；
            None = 模块默认 `_TERMINATE_GRACE_SECONDS`（0.5s），负值归 0，
            上限 10s（防误配置挂死）。
        orphan_guard: 是否启用父死亡看门狗（`python -c` 监督进程）。
            启用后 `CompletedProcess.args` 仍为**原命令**；`returncode` 为
            原命令退出码（原命令被信号杀死时归一为 128+n）。与
            `preexec_fn` 不能同用。

    Returns:
        `CompletedProcess`（附加 `timed_out` 标记）。**本函数保证返回**。

    Raises:
        ValueError: `orphan_guard=True` 且同时给了 `preexec_fn`（fail-closed）。
    """
    if orphan_guard and preexec_fn is not None:
        raise ValueError("orphan_guard 与 preexec_fn 不能同时使用（看门狗无法转发 preexec_fn 钩子）")
    label = logger_name or (os.path.basename(cmd[0]) if cmd else "subprocess")
    popen_kwargs: dict[str, Any] = {}
    if preexec_fn is not None:
        # 执行器链路既需要 rlimit（S5 防 fork 炸弹/内存/fd 打满宿主），又需要
        # 本函数的整树终止（防"超时后孙进程持管道写端 → 永久阻塞"）。
        # 早期二者只能择一（裸 subprocess.run 支持 preexec_fn 但会挂死；
        # 本函数不挂死但不支持 preexec_fn），现同时提供——POSIX 上
        # start_new_session 与 preexec_fn 均为 fork 后 exec 前的钩子，可共存。
        popen_kwargs["preexec_fn"] = preexec_fn

    launch_cmd: list[str] = list(cmd)
    if orphan_guard:
        # 监督进程与真实命令同进程组（新会话由下方 start_new_session 建立）：
        # 超时 killpg 一次回收两者；调用方死亡时由监督进程 killpg 回收。
        launch_cmd = [sys.executable, "-c", _ORPHAN_GUARD_SCRIPT, str(os.getpid()), *launch_cmd]

    tmpdir = tempfile.mkdtemp(prefix="aitester_proc_")
    out_path = os.path.join(tmpdir, "stdout")
    err_path = os.path.join(tmpdir, "stderr")
    timed_out = False
    try:
        # 文件后端：不建管道 → 不存在"等 EOF"阻塞（见 docstring 根因说明）
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            proc = subprocess.Popen(
                launch_cmd,
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
                _terminate_process_group(proc, label=label, grace_seconds=terminate_grace)
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
        return CompletedProcess(list(cmd), -9, out, err, timed_out=True)

    result = CompletedProcess(list(cmd), proc.returncode, out, err, timed_out=False)
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


def _resolve_terminate_grace(grace_seconds: float | None) -> float:
    """归一 SIGTERM→SIGKILL 宽限秒数（None→默认；负值→0；上限 10 防误配置）。

    Args:
        grace_seconds: 调用点显式宽限（None = 用模块默认 `_TERMINATE_GRACE_SECONDS`）。

    Returns:
        落在 ``[0.0, 10.0]`` 的宽限秒数；无法解析时回落默认值。
    """
    raw: Any = _TERMINATE_GRACE_SECONDS if grace_seconds is None else grace_seconds
    try:
        value = float(raw)
    except (TypeError, ValueError):  # pragma: no cover - 防御非数值注入
        return _TERMINATE_GRACE_SECONDS
    return min(max(value, 0.0), 10.0)


def _is_windows() -> bool:
    """平台判定：当前是否 Windows（**可注入**：单测 monkeypatch 本函数模拟）。

    单独抽成函数而不是模块级常量，原因：本机（macOS）无法实跑 Windows 分支，
    A12/M5 验收要求用 Mock 单测覆盖 Windows 回收语义（``monkeypatch.setattr``
    到本函数即可让 ``_terminate_process_group`` 进入 Windows 分支）。
    """
    return os.name == "nt"


# taskkill /T /F 单次调用上限（秒）与直接子进程收尸等待上限（秒）。
# 有界：即使 taskkill 挂死也不让超时回收路径无限等待（本模块核心契约是
# "一定返回"）。taskkill 本身很短命，10s 已是极端宽限。
_WINDOWS_TASKKILL_TIMEOUT_SECONDS = 10.0
_WINDOWS_REAP_TIMEOUT_SECONDS = 5.0


def _run_taskkill(pid: int) -> subprocess.CompletedProcess[str] | None:
    """Windows：``taskkill /T /F /PID <pid>`` 终止整棵进程树。

    返回 ``CompletedProcess``；taskkill 不可用（不在 PATH）或调用异常时返回
    ``None``，由调用方回退 ``process.kill()``（只保证直接子进程被终止）。
    不经 shell（列表参数），pid 为整数，无注入面。
    """
    try:
        return subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=_WINDOWS_TASKKILL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover - 平台相关
        logger.debug("taskkill 不可用或调用失败（pid=%s）：%s", pid, e)
        return None


def _wait_and_reap(proc: subprocess.Popen[str], *, label: str) -> None:
    """有界等待直接子进程退出；仍存活则 ``kill()`` 后再次等待（收尸）。

    无论 ``wait`` 是否超时都不向上抛异常——超时回收路径的本职是"尽量回收 +
    一定返回"；僵尸残留由调用方/巡检层观测。
    """
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=_WINDOWS_REAP_TIMEOUT_SECONDS)
    if proc.poll() is not None:
        return
    logger.debug("%s：直接子进程仍在运行，kill() 兜底", label)
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=_WINDOWS_REAP_TIMEOUT_SECONDS)


def _terminate_process_group_windows(proc: subprocess.Popen[str], *, label: str) -> None:
    """Windows 进程树回收分支（A12/P1）：taskkill /T /F → kill() 兜底 → 等待。

    Windows 没有 ``os.getpgid`` / ``os.killpg``（历史实现在超时路径上抛
    ``AttributeError``，绕过 kill/wait，子进程树可能残留）。本分支：

    1. ``taskkill /T /F /PID <pid>`` 终止**整棵树**（含孙进程）；
    2. taskkill 不存在 / 返回非 0 / 抛错 → ``process.kill()`` 终止直接子进程；
    3. 无论哪条路径都**有界等待直接子进程**（必要时再补一次 kill）——保证
       直接子进程被回收，不把 "taskkill 失败" 升级成"直接子进程失控"。
    """
    pid = getattr(proc, "pid", None)
    taskkill_ok = False
    # bool 是 int 子类：显式排除，避免 True 被当成 pid=1
    if isinstance(pid, int) and not isinstance(pid, bool):
        completed = _run_taskkill(pid)
        taskkill_ok = completed is not None and getattr(completed, "returncode", 1) == 0
        if not taskkill_ok:
            logger.debug("%s：taskkill 未成功（pid=%s），回退 kill()", label, pid)
    else:  # pragma: no cover - 防御非常规 Popen 替身
        logger.debug("%s：无有效 pid（%r），直接 kill() 兜底", label, pid)
    if not taskkill_ok:
        with contextlib.suppress(OSError):
            proc.kill()
    _wait_and_reap(proc, label=label)


def _terminate_process_group(
    proc: subprocess.Popen[str],
    *,
    label: str,
    grace_seconds: float | None = None,
) -> None:
    """终止子进程**及其整个进程组**（含孙进程）：SIGTERM 宽限 → SIGKILL 清扫。

    M-3（2026-10-17）：历史上直接 `killpg(SIGKILL)`——子进程（如 pytest）
    没有机会清理自己的临时文件/子进程；但超时是"父进程仍存活"的路径，
    宽限只影响清理质量、不改变整树终止语义：

    1. 先 `killpg(SIGTERM)`（可响应进程自清理，如 pytest 落盘/临时目录）；
    2. 最多等待 `grace` 秒（组长退出即提前结束等待）；
    3. **总是**再 `killpg(SIGKILL)` 清扫——包括"组长已退出但组内仍有成员"
       的形态（组号在组内仍有成员时仍有效）。
    4. 任何 `getpgid`/`killpg` 失败（进程已消亡/无权限）都回退 `proc.kill()`。

    A12（2026-10-18 第三方评审 P1，Windows）：Windows 无 `os.getpgid` /
    `os.killpg`，历史实现直接 AttributeError 逃逸、绕过 kill/wait。现按
    `_is_windows()` 分派到 `_terminate_process_group_windows`（taskkill /T /F
    整树回收 + `process.kill()` 兜底 + 有界等待直接子进程）；POSIX 路径逐字
    不变（仍为新会话进程组 + 两段式 killpg）。

    注意：本函数只覆盖"**调用方存活**时的超时回收"；调用方被外部 SIGKILL
    的路径由 `run_with_timeout(orphan_guard=True)` 的看门狗负责（见模块 docstring）。

    Args:
        proc: 已超时的直接子进程（POSIX 上同时是进程组组长）。
        label: 日志标签。
        grace_seconds: SIGTERM 后宽限秒数（None = 模块默认 0.5s）。
    """
    grace = _resolve_terminate_grace(grace_seconds)
    if _is_windows():
        # Windows：无进程组 API，走 taskkill 整树 + kill() 兜底分支。
        _terminate_process_group_windows(proc, label=label)
        return
    try:
        pgid: int | None = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError) as e:  # pragma: no cover - 进程已消亡竞态
        logger.debug("%s：getpgid 失败（%s），回退 kill()", label, e)
        pgid = None
    if pgid is None:  # pragma: no cover - 进程已消亡竞态
        with contextlib.suppress(OSError):
            proc.kill()
        return

    # 阶段 1：SIGTERM 给组内进程自清理机会
    sent_term = False
    try:
        os.killpg(pgid, signal.SIGTERM)
        sent_term = True
    except (ProcessLookupError, PermissionError, OSError) as e:  # pragma: no cover - 组已消亡竞态
        logger.debug("%s：killpg(SIGTERM) 失败（%s），转入 SIGKILL 兜底", label, e)
    if sent_term and grace > 0:
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.02)

    # 阶段 2：SIGKILL 兜底清扫（整树终止语义不变；组长已退出也补刀组内残留成员）
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError) as e:
        logger.debug("%s：killpg(SIGKILL) 失败（%s），回退 kill()", label, e)
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
