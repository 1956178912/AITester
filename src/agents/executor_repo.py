"""
仓库级执行器（RepoExecutor）：在真实仓库环境中验证 SWE-bench 类任务的
gold test_patch 验证口径（FAIL_TO_PASS / PASS_TO_PASS）。

背景：
    SWE-bench 的官方验证口径是"把 gold test_patch 应用到 base_commit 检出后
    的仓库，跑 FAIL_TO_PASS（修复前失败、修复后通过）与 PASS_TO_PASS
    （前后都通过）"。单临时文件 executor 装不下仓库级代码（模块名断裂、
    依赖未安装、多源文件补丁），故本模块独立承载仓库级执行，不改动
    ExecutorAgent 的任何既有路径（合成数据集 / examples 口径零变化）。

职责边界（默认全部关闭，opt-in）：
    - 仅服务 source==swe_bench 且携带 FAIL_TO_PASS 的任务（由 run_benchmark
      按 task.metadata 路由，REPO_LEVEL_EXECUTION=true 时启用）；
    - 环境 setup（clone + checkout + pip install -e）按 (repo, commit) 缓存，
      同仓库多任务复用（SWE-bench lite 500 任务多为 6-8 个仓库）；
    - 验证流程内 LLM 补丁写入经 git checkout -- . / git clean 恢复，无论验证
      成功与否，验证结束后仓库环境恢复为"仅应用 test_patch"的干净基线。

Returns:
    与 ExecutorAgent.execute 同构的结果字典，额外携带：
    - repo_env (dict): 仓库环境路径 / 缓存状态 / pip install 是否成功
    - fail_to_pass (dict): {"expected": 总数, "passed": 通过数}
    - pass_to_pass (dict): 同上（expected 为 0 时 passed 为 0，不影响判定）

判定口径（与 SWE-bench 官方一致）：
    passed = fail_to_pass 全部通过 且 pass_to_pass 无回归。
    FAIL_TO_PASS 在"基线（未打修复补丁）"上跑，用于确认测试基线确实失败
    （基线全通过 → 任务数据有问题，记 base_not_failing 诊断）；
    打 LLM 补丁后重跑，FAIL_TO_PASS 全过 + PASS_TO_PASS 无回归 → passed。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any

from src.utils.credential_scrub import scrub_os_environ
from src.utils.env_utils import env_flag, env_flag_opt_out, env_float
from src.utils.pytest_output import run_has_effective_pass

logger = logging.getLogger(__name__)

# 仓库环境缓存根目录（与 venv 缓存同口径 ~/.cache/aitester/）：
# 按 repo_name/commit[:12] 分目录，(repo, commit) 相同的环境跨任务/跨运行复用。
_DEFAULT_REPO_ENVS_DIR = os.path.join(os.path.expanduser("~"), ".cache", "aitester", "repo_envs")

# 2026-09-26 round9 P1：共享 venv 创建/重指向目录锁注册表。
# setup() 中 _create_venv / _venv_pip_install（editable 重指向）操作的是
# 仓库级共享目录（<repo>/_shared_venv），--parallel 下多任务同仓库并发
# setup 时 pip 写 venv 内 site-packages / .pth 文件互相踩（半成品 venv）。
# 锁粒度为 (repo_name, commit[:12]) 维度——与 setup 的 env_dir 路径一致，
# 不同仓库/不同 commit 互不阻塞，同仓库同 commit 的并发 setup 串行化。
_repo_setup_locks: dict[str, threading.Lock] = {}
_repo_setup_locks_guard = threading.Lock()


def _get_repo_setup_lock(env_dir: str) -> threading.Lock:
    """获取指定仓库环境目录的 setup 锁（per-env_dir，不同目录互不阻塞）。"""
    key = os.path.normpath(env_dir)
    with _repo_setup_locks_guard:
        lock = _repo_setup_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _repo_setup_locks[key] = lock
        return lock


def _repo_envs_root() -> str:
    """仓库环境缓存根目录（SWE_REPO_ENVS_DIR 可覆盖，测试指向临时目录）。"""
    return os.getenv("SWE_REPO_ENVS_DIR") or _DEFAULT_REPO_ENVS_DIR


# F10（2026-10-19 Z 轮审查 P1）：共享 venv 的 editable 源码绑定标记文件名。
# 共享 venv（use_venv=True + venv_reuse_by_repo=True）跨 commit 复用同一个
# venv，而 `pip install -e` 把"最近一次安装时 repo_dir"的绝对路径写进
# site-packages（.pth / __editable__ finder）——per-commit 缓存命中直接
# return 会让 venv 继续指向上一个 commit 的源码目录（A→B→A 回 A 时
# `import <repo_pkg>` 解析到 B，测试在错误源码上裁决）。故在 venv 目录下
# 用该 marker 记录"当前 editable 绑定的 commit"，缓存命中时校验并在仓库级
# 锁内按需重指向。只对共享 venv 生效（per-commit venv / 全局模式零变化）。
_VENV_EDITABLE_COMMIT_MARKER = ".venv_editable_commit"

# F11（2026-10-19 Z 轮审查 P1）：官方 SWE-bench harness 接口假设。
# 官方 `swebench.harness.run_evaluation` CLI 使用命名参数，不接受历史实现
# 的位置参数；predictions schema 为 {instance_id, model_name_or_path,
# model_patch}。本仓**未锁定**官方包版本、真实包验收仍未执行（见
# `_run_official_swebench_harness` docstring）——以下常量按官方 main 分支
# 接口静态核对，可由调用方经函数参数或覆写模块常量调整；刻意不新增环境
# 变量（ADR-0003 env 预算门禁，experiments/ 侧也不登记）。
_OFFICIAL_HARNESS_DATASET = "SWE-bench/SWE-bench_Lite"
_OFFICIAL_HARNESS_SPLIT = "test"
#: 单 instance 求值无需并发；固定 1 避免官方 runner 起多 worker 抢 Docker 资源。
_OFFICIAL_HARNESS_MAX_WORKERS = 1
#: 官方 runner（含 Docker 构建）远慢于单次 pytest，超时下限 300s。
_OFFICIAL_HARNESS_TIMEOUT_FLOOR = 300


def _run(cmd: list[str], cwd: str, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """统一子进程执行：超时/异常不抛出，由调用方按 returncode 判断。

    超时经 returncode=124（Linux timeout 命令口径）返回而非抛出
    subprocess.TimeoutExpired——SWE-bench 仓库中单节点 pytest 跑满 timeout
    很常见，此前该异常穿透 verify() 的 try/finally 使整个验证任务崩溃
    而非记录该 node 失败；统一在此收敛后，所有调用方按 returncode 判断
    即可（124 一律视为失败，调用方无需感知区别）。

    2026-10-11 全面优化批次：run_with_timeout 接线（孤儿风险消除）——
    本 helper 是所有仓库级子进程（git clone / pip install / pytest 验证 /
    swebench runner）的唯一收敛点；孙进程持管道写端时裸 subprocess.run
    的 communicate 可能永久阻塞（2026-10-09 批后挂死事故同构风险面）。
    run_with_timeout 以文件后端 + 进程组 kill 保证必然返回；超时归一为
    returncode=124 哨兵（与历史 TimeoutExpired 分支逐字一致：stdout/stderr
    取已捕获部分、stderr 追加超时前缀）。
    """
    from src.utils.process_utils import run_with_timeout

    proc = run_with_timeout(
        cmd,
        cwd=cwd,
        timeout=timeout,
        env=env if env is not None else scrub_os_environ(),
        text=True,
    )
    if proc.timed_out:
        # 超时：构造哨兵结果（与历史 TimeoutExpired 分支口径逐字一致）
        stdout_part = proc.stdout or ""
        stderr_part = proc.stderr or ""
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=stdout_part,
            stderr=f"命令执行超时（>{timeout}s）\n{stderr_part[:300]}",
        )
    return proc


class RepoExecutor:
    """仓库级执行器：setup 一次（缓存复用），验证按 (LLM 补丁, test_patch) 走。

    属性:
        timeout: 单次 pytest 运行超时秒数（沿用 config.EXECUTION_TIMEOUT 口径）。
        setup_timeout: clone / pip install 子进程超时秒数（仓库级安装远慢于单任务）。
        env_root: 仓库环境缓存根目录（默认 ~/.cache/aitester/repo_envs/）。
    """

    def __init__(
        self,
        timeout: int = 30,
        setup_timeout: int = 600,
        use_venv: bool = False,
        venv_reuse_by_repo: bool = False,
    ) -> None:
        self.timeout = timeout
        self.setup_timeout = setup_timeout
        self.env_root = _repo_envs_root()
        # venv 隔离（opt-in，默认关保持与已缓存 repo_envs 的兼容）：
        # 每个 (repo, commit) 环境旁建独立 venv，pip install -e 装入 venv
        # （而非全局 sys.executable），pytest 用 venv 的 python 运行。
        # 共享全局 python 会让"最近一次 pip install -e"的 commit 源码
        # 污染其它 commit 的 `import <repo_pkg>`（跨 commit 版本不一致 →
        # AttributeError/ImportError，与 LLM 补丁无关）。
        self.use_venv = use_venv
        # P0 4.3 venv 按仓库复用：同一 repo 的多个 commit 共享一个 venv
        # （键：repo 名 + 依赖指纹），仅当依赖列表（requirements/setup.py/
        # pyproject.toml 的 hash）变更时重建。大幅减少 venv 重建开销
        # （SWE-bench 同一 repo 通常 10-20 个 commit，逐个建 venv 耗时
        # 10-20 倍）。与 use_venv 正交：use_venv=False 时本参数无效果。
        self.venv_reuse_by_repo = venv_reuse_by_repo

    # P0 4.3 venv 目录解析（按仓库共享 or 按 commit 独立）
    def _resolve_venv_dir(self, env_dir: str, repo_url: str, repo_dir: str) -> str:
        """返回该环境使用的 venv 目录路径。

        venv_reuse_by_repo=True → 仓库级共享目录（<repo>/_shared_venv）；
        False → 传统 per-commit 目录（<env_dir>）。
        """
        if self.use_venv and self.venv_reuse_by_repo:
            return self._repo_venv_dir(repo_url, repo_dir)
        return env_dir

    def _venv_python(self, env_dir: str, repo_url: str = "", repo_dir: str = "") -> str | None:
        """该环境的 venv python 路径（use_venv=True 且 venv 已建立时）。

        P0 4.3：venv_reuse_by_repo=True 时解析为仓库级共享目录。
        """
        if not self.use_venv:
            return None
        actual_venv_dir = self._resolve_venv_dir(env_dir, repo_url, repo_dir)
        vpy = os.path.join(actual_venv_dir, "venv", "bin", "python")
        return vpy if os.path.isfile(vpy) else None

    # ── 环境 setup（clone + checkout + pip install -e，缓存复用）────────────────

    def setup(self, repo_url: str, base_commit: str) -> dict[str, Any]:
        """准备 (repo_url, base_commit) 的仓库环境，返回环境信息与错误诊断。

        命中缓存（目录存在 + 已 checkout 到目标 commit + pip install 标记存在）
        时直接复用，跳过 clone/install。

        Returns:
            {"workdir": str, "cached": bool, "error": str | None}
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        # 去 .git 后缀（"sqlfluff/sqlfluff.git" → "sqlfluff"）
        repo_name = repo_name.removesuffix(".git")
        env_dir = os.path.join(self.env_root, repo_name, base_commit[:12])
        repo_dir = os.path.join(env_dir, "repo")

        env_error: str | None = None
        cached = False

        # 缓存命中条件随 use_venv 切换：venv 模式看 .venv_pip_installed，
        # 全局模式看 .pip_installed（与既有缓存环境兼容）
        _pip_marker = ".venv_pip_installed" if self.use_venv else ".pip_installed"
        if os.path.isfile(os.path.join(env_dir, _pip_marker)) and os.path.isdir(repo_dir):
            # 缓存命中：确认 checkout 仍在目标 commit
            # Z3（2026-10-06 审查修复）：前缀（commit[:12]）比较改全等——
            # 12 位前缀碰撞概率虽低，但碰撞时会把"同仓库不同 commit"的
            # 缓存环境误判命中（错 commit 环境 + 错误基线代码）。全等的
            # 退化方向是安全的：短 sha 入参时永不命中缓存（重建），性能
            # 损失而非正确性损失（SWE-bench 数据源均为 40 位完整 sha）。
            head = _run(["git", "rev-parse", "HEAD"], repo_dir, 30)
            if head.returncode == 0 and head.stdout.strip() == base_commit:
                cached = True
                logger.info("仓库环境命中缓存: %s", env_dir)
            else:
                logger.warning("仓库环境缓存 checkout 漂移，重新准备: %s", env_dir)

        if not cached:
            # 2026-09-26 round9 P1：per-env_dir 锁保护 clone/checkout/venv/pip 序列。
            # 旧实现无锁，--parallel 下多任务同 (repo, commit) 并发 setup 时：
            # - 同时 shutil.rmtree(repo_dir) 互相删除对方刚 clone 的仓库；
            # - 并发 python -m venv --clear 写同一 venv 目录（半成品）；
            # - pip install -e 写 site-packages / .pth 互相踩。
            # 锁粒度为 env_dir（= <repo>/<commit[:12]>），不同仓库/不同
            # commit 互不阻塞。持锁时间 = clone + venv + pip（分钟级），
            # 但仅同 (repo, commit) 的并发 setup 会被串行化（与单任务
            # 串行等价）；SWE-bench 同仓库多 commit 场景下锁粒度到
            # commit 级，不损失跨 commit 的并行度。
            lock = _get_repo_setup_lock(env_dir)
            with lock:
                # 锁内重检缓存：持锁前可能已被其他线程完成 setup
                # （Z3：同全等比较口径，见上方首次检查处注释）
                if os.path.isfile(os.path.join(env_dir, _pip_marker)) and os.path.isdir(repo_dir):
                    head = _run(["git", "rev-parse", "HEAD"], repo_dir, 30)
                    if head.returncode == 0 and head.stdout.strip() == base_commit:
                        cached = True
                        logger.info("仓库环境命中缓存（锁内复检）: %s", env_dir)
                if not cached:
                    os.makedirs(env_dir, exist_ok=True)
                    # 清掉旧 repo 目录（部分失败残留）
                    if os.path.isdir(repo_dir):
                        shutil.rmtree(repo_dir, ignore_errors=True)

                    env_error = self._clone_and_checkout(repo_url, base_commit, repo_dir)
                    if env_error:
                        return {"workdir": repo_dir, "cached": False, "error": env_error}

                    if self.use_venv:
                        if self.venv_reuse_by_repo:
                            # P0 4.3：按仓库复用 venv（依赖指纹键），跨 commit 共享。
                            # F10（2026-10-19 Z 轮审查 P1）：创建/复用/editable 重指向
                            # 全部收进 _setup_shared_venv——内部持**仓库级 venv 锁**
                            # （键 = 共享 venv 目录），与缓存命中分支的"检查+重指向"
                            # 共用同一锁域，避免 A/B commit 并发交错后 venv 指错源码。
                            env_error = self._setup_shared_venv(repo_url, repo_dir, base_commit)
                        else:
                            # 传统模式：每个 (repo, commit) 独立 venv
                            # venv 隔离：建独立 venv，pip install -e 装入 venv
                            env_error = self._create_venv(env_dir)
                            if env_error:
                                logger.warning("venv 创建失败，退回全局 python: %s", env_error)
                                env_error = self._pip_install_editable(repo_dir)
                                if env_error:
                                    logger.warning("仓库 pip install -e 失败（记录但不阻断验证）: %s", env_error)
                                else:
                                    with open(os.path.join(env_dir, ".pip_installed"), "w", encoding="utf-8") as f:
                                        f.write(base_commit)
                            else:
                                env_error = self._venv_pip_install(repo_dir, env_dir)
                                if env_error:
                                    logger.warning("venv pip install -e 失败（记录但不阻断验证）: %s", env_error)
                                else:
                                    with open(os.path.join(env_dir, ".venv_pip_installed"), "w", encoding="utf-8") as f:
                                        f.write(base_commit)
                    else:
                        env_error = self._pip_install_editable(repo_dir)
                        if env_error:
                            logger.warning("仓库 pip install -e 失败（记录但不阻断验证）: %s", env_error)
                        else:
                            with open(os.path.join(env_dir, ".pip_installed"), "w", encoding="utf-8") as f:
                                f.write(base_commit)

        # F10（2026-10-19 Z 轮审查 P1）：共享 venv 下缓存命中 ≠ 源码绑定正确。
        # per-commit 缓存只证明"该 commit 的 repo 目录 + 环境标记在"，而 venv 的
        # editable 安装是**跨 commit 共享的可变状态**（可能仍指向上一个 commit）。
        # 命中时读 venv 绑定 marker 与目标 base_commit 比较：不一致 → 在仓库级
        # venv 锁内重跑 pip install -e 重指向并更新 marker；一致 → 跳过（性能不变）。
        # 非共享 venv / 全局模式：_ensure_shared_venv_editable_binding 立即返回 None，
        # 行为零变化。
        if cached:
            _bind_err = self._ensure_shared_venv_editable_binding(repo_url, repo_dir, base_commit)
            if _bind_err is not None:
                logger.warning(
                    "共享 venv editable 绑定校验失败（venv 可能仍指旧 commit 源码）: %s",
                    _bind_err,
                )
                env_error = _bind_err

        return {"workdir": repo_dir, "cached": cached, "error": env_error}

    def _create_venv(self, env_dir: str) -> str | None:
        """在该环境旁创建独立 venv（复用已有）。失败返回错误文本，成功 None。"""
        vpy = os.path.join(env_dir, "venv", "bin", "python")
        if os.path.isfile(vpy):
            return None
        res = _run(
            [sys.executable, "-m", "venv", "--clear", os.path.join(env_dir, "venv")], env_dir, self.setup_timeout
        )
        if res.returncode != 0:
            return f"venv 创建失败: {res.stderr.strip()[:200]}"
        if not os.path.isfile(vpy):
            return f"venv 创建后无 python: {vpy}"
        return None

    # ── P0 4.3：venv 按仓库复用（跨 commit 共享）────────────────────────────

    def _repo_venv_dir(self, repo_url: str, repo_dir: str) -> str:
        """计算仓库级 venv 目录（P0 4.3：同一 repo 多 commit 共享一个 venv）。

        目录布局：<env_root>/<repo_name>/_shared_venv/
        与 per-commit 的 <env_root>/<repo>/<commit>/venv/ 区分：

        - 共享 venv **只装依赖**（依赖指纹 requirements/pyproject/setup 的
          SHA256 只决定是否需要重装依赖）；
        - editable 绑定的源码目录是**跨 commit 共享的可变状态**：``pip install
          -e`` 写入的是「最近一次安装时的 repo_dir」绝对路径（.pth /
          __editable__ finder），**不会**随 checkout 自动跟随（F10／2026-10-19
          Z 轮审查前的"自动跟随"表述是错误前提，A→B→A 会导入 B 的源码）；
        - 现行口径：venv 目录下的 ``.venv_editable_commit`` marker 记录当前绑定
          commit；setup 缓存命中 / verify 时在**仓库级 venv 锁内**校验，仅当
          marker ≠ 目标 base_commit 才重跑一次 ``pip install -e .`` 重指向并
          刷新 marker；同 commit 命中零额外安装（性能不变）。

        Args:
            repo_url: 仓库 URL（取 repo 名做键）。
            repo_dir: 当前 checkout 的源码目录（editable install 目标）。

        Returns:
            共享 venv 目录路径。
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_name = repo_name.removesuffix(".git")
        return os.path.join(self.env_root, repo_name, "_shared_venv")

    # ── F10（2026-10-19 Z 轮审查）：共享 venv 的 editable 源码绑定 ─────────────

    def _shared_venv_reuse_enabled(self) -> bool:
        """是否启用"按仓库共享 venv"模式（use_venv 与 venv_reuse_by_repo 同时开）。"""
        return self.use_venv and self.venv_reuse_by_repo

    @staticmethod
    def _venv_editable_marker(venv_dir: str) -> str:
        """共享 venv 的 editable 绑定 marker 路径（<venv_dir>/.venv_editable_commit）。"""
        return os.path.join(venv_dir, _VENV_EDITABLE_COMMIT_MARKER)

    def _read_venv_editable_commit(self, venv_dir: str) -> str | None:
        """读取共享 venv 当前 editable 绑定的 commit（读不到 → None）。

        None 表示"绑定未知"（旧版缓存无 marker / 读取失败），按保守方向
        处理：视为需要重指向，而不是假定已绑定目标 commit。
        """
        try:
            with open(self._venv_editable_marker(venv_dir), encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def _write_venv_editable_commit(self, venv_dir: str, base_commit: str) -> None:
        """记录共享 venv 当前 editable 绑定的 commit（写失败仅告警，不阻断）。

        写失败的方向是安全的：marker 缺失/过期只意味着下次缓存命中会多跑
        一次重指向（幂等），不会把"未验证的绑定"冒充为"已验证"。
        """
        try:
            with open(self._venv_editable_marker(venv_dir), "w", encoding="utf-8") as f:
                f.write(base_commit)
        except OSError as e:
            logger.warning("共享 venv editable 绑定标记写入失败（下次命中将重新校验）: %s", e)

    def _repoint_shared_venv_locked(self, venv_dir: str, repo_dir: str, base_commit: str) -> str | None:
        """**已持 venv 锁**时校验并刷新 editable 源码绑定（幂等）。

        Returns:
            None = 绑定已正确（本次无需重指向）或重指向成功；
            错误文本 = 重指向失败（调用方按 fail-closed 处理，不得在错误
            源码上裁决）。
        """
        bound = self._read_venv_editable_commit(venv_dir)
        if bound == base_commit:
            # 常见路径：同 commit 缓存命中 → 零额外安装开销（不跑 pip）。
            logger.debug("共享 venv editable 已绑定目标 commit，跳过重指向: %s", venv_dir)
            return None
        logger.info(
            "共享 venv editable 绑定与目标 commit 不一致（%s → %s），重指向源码: %s",
            (bound or "<未记录>")[:12],
            base_commit[:12],
            venv_dir,
        )
        # venv 目录缺失（如历史 venv 创建失败后回退全局 editable，但本 commit
        # 已在缓存）时不能调用 pip（子进程 python 不存在）；按绑定失败返回。
        vpy = os.path.join(venv_dir, "venv", "bin", "python")
        if not os.path.isfile(vpy):
            return f"共享 venv 不可用（缺少 python: {vpy}），无法重指向 editable 源码"
        try:
            err = self._venv_pip_install(repo_dir, venv_dir)
        except OSError as e:  # pragma: no cover - 防御子进程启动失败（如 python 不可执行）
            return f"共享 venv editable 重指向异常: {e}"
        if err:
            logger.warning("共享 venv editable 重指向失败（venv 仍指旧 commit 源码）: %s", err)
            return err
        self._write_venv_editable_commit(venv_dir, base_commit)
        return None

    def _ensure_shared_venv_editable_binding(self, repo_url: str, repo_dir: str, base_commit: str) -> str | None:
        """共享 venv 缓存命中路径：在仓库级 venv 锁内校验+（按需）重指向。

        锁键 = 共享 venv 目录（`_get_repo_setup_lock`），确保"读 marker → 比较
        → 重指向 → 写 marker"整段不与其它 commit 的同类操作交错。非共享
        venv / 全局模式直接返回 None（既有行为零变化）。
        """
        if not self._shared_venv_reuse_enabled():
            return None
        venv_dir = self._repo_venv_dir(repo_url, repo_dir)
        with _get_repo_setup_lock(venv_dir):
            return self._repoint_shared_venv_locked(venv_dir, repo_dir, base_commit)

    def _setup_shared_venv(self, repo_url: str, repo_dir: str, base_commit: str) -> str | None:
        """P0 4.3 共享 venv 分支：创建/复用 venv、按需安装、绑定 editable 源码。

        F10（2026-10-19 Z 轮审查）：整段包在仓库级 venv 锁内——共享 venv 是
        跨 commit 的可变状态，"创建/依赖安装/editable 重指向/绑定 marker 写入"
        的检查+变更必须在同一锁域内，否则两个 commit 并发 setup 时可能交错成
        "A 检查后 B 重指向、A 又不刷新"的错误绑定。
        """
        venv_dir = self._repo_venv_dir(repo_url, repo_dir)
        with _get_repo_setup_lock(venv_dir):
            return self._setup_shared_venv_locked(repo_dir, base_commit, venv_dir)

    def _setup_shared_venv_locked(self, repo_dir: str, base_commit: str, venv_dir: str) -> str | None:
        """`_setup_shared_venv` 的持锁主体（调用方必须已持 venv 锁）。"""
        env_dir = os.path.dirname(repo_dir)  # repo_dir = <env_dir>/repo
        env_error: str | None = self._create_venv(venv_dir)
        if env_error:
            logger.warning("venv 创建失败，退回全局 python: %s", env_error)
            env_error = self._pip_install_editable(repo_dir)
            if env_error:
                logger.warning("仓库 pip install -e 失败（记录但不阻断验证）: %s", env_error)
            else:
                # 2026-09-26 全面审查（P1 缓存一致性）：venv 创建失败回退到全局
                # pip install 后，缓存检查标记须与 use_venv 模式对齐——use_venv=True
                # 时 setup() 入口读 .venv_pip_installed，此处若写 .pip_installed 则
                # 下次 setup() 永远缓存 miss，每次重新 git clone + pip install。
                _marker = ".venv_pip_installed" if self.use_venv else ".pip_installed"
                with open(os.path.join(env_dir, _marker), "w", encoding="utf-8") as f:
                    f.write(base_commit)
            return env_error

        # 检测依赖指纹：同一指纹复用已有 venv（不重新装依赖）
        dep_fingerprint = self._dep_fingerprint(repo_dir)
        marker = os.path.join(venv_dir, ".venv_dep_fingerprint")
        need_install = True
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as f:
                existing_fp = f.read().strip()
            if existing_fp == dep_fingerprint:
                # 依赖未变 → 复用 venv，不重新装依赖。
                # 但必须刷新 editable 源码指向：pip install -e 写入的是绝对路径
                # （.pth / __editable__ finder），跨 commit 时旧 venv 的 editable
                # 安装仍指向上一个 commit 的 repo 目录——与本 commit 不一致时会让
                # `import <repo_pkg>` 解析到错误版本（正是 4.3 要消除的跨 commit
                # 污染）。因此指纹命中时重跑一次轻量 `pip install -e .`（依赖已装、
                # 仅重指向源码，秒级），不装依赖本身。
                logger.info(
                    "P0 4.3 venv 复用命中（依赖指纹未变，仅重指向 editable 源码）: %s（commit %s）",
                    venv_dir,
                    base_commit[:12],
                )
                _repoint_err = self._venv_pip_install(repo_dir, venv_dir)
                if _repoint_err:
                    # 重指向失败（pip 网络异常等）：editable 仍指旧 commit 源码，
                    # 测试会在旧版本上裁决——保留诊断但不清除环境标记（venv 本身
                    # 可用，走保守路径），由 verify 阶段绑定复检 fail-closed 兜底。
                    logger.warning(
                        "P0 4.3 editable 重指向失败（venv 仍指旧 commit 源码）: %s",
                        _repoint_err,
                    )
                else:
                    # F10：安装成功才更新绑定 marker（失败时保留旧值以反映真实绑定）
                    self._write_venv_editable_commit(venv_dir, base_commit)
                # O35（P2 性能）：指纹命中分支已做过一次 `pip install -e .`
                # （上方 repoint），need_install 置 False 避免再跑一次同样的安装。
                need_install = False
        if need_install:
            env_error = self._venv_pip_install(repo_dir, venv_dir)
            if env_error:
                logger.warning("venv pip install -e 失败（记录但不阻断验证）: %s", env_error)
            else:
                with open(marker, "w", encoding="utf-8") as f:
                    f.write(dep_fingerprint)
                # F10：首次（或依赖变更后）安装成功 → 记录 editable 绑定
                self._write_venv_editable_commit(venv_dir, base_commit)
        # 写环境标记（venv 模式下，即使复用也标记该 commit 已就绪）
        with open(os.path.join(env_dir, ".venv_pip_installed"), "w", encoding="utf-8") as f:
            f.write(base_commit)
        return env_error

    def _dep_fingerprint(self, repo_dir: str) -> str:
        """计算仓库依赖指纹（P0 4.3：依赖列表变更检测）。

        指纹 = sha256(requirements*.txt + pyproject.toml + setup.py + setup.cfg
        的内容拼接)。任一依赖文件变更 → 指纹变 → 需重新 pip install -e；
        仅源码变更（无依赖文件改动）→ 指纹不变 → 复用 venv 跳过重装。

        Args:
            repo_dir: 仓库源码目录（已 checkout 到目标 commit）。

        Returns:
            依赖指纹（64 位 hex 字符串）。
        """
        import hashlib

        content_parts: list[bytes] = []
        # requirements*.txt（requirements.txt / requirements-dev.txt / 等）
        if os.path.isdir(repo_dir):
            for fname in sorted(os.listdir(repo_dir)):
                if fname.startswith("requirements") and fname.endswith(".txt"):
                    fpath = os.path.join(repo_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "rb") as f:
                            content_parts.append(f.read())
        # pyproject.toml / setup.py / setup.cfg
        for fname in ("pyproject.toml", "setup.py", "setup.cfg"):
            fpath = os.path.join(repo_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    content_parts.append(f.read())
        if not content_parts:
            # 无依赖声明文件 → 指纹为 "no-deps"（首次装完即复用）
            return "no-deps"
        h = hashlib.sha256()
        for part in content_parts:
            h.update(part)
        return h.hexdigest()

    def _venv_pip_install(self, repo_dir: str, env_dir: str) -> str | None:
        """在 venv 内 pip install -e .（依赖装进 venv，不污染全局）。"""
        if not (
            os.path.isfile(os.path.join(repo_dir, "setup.py"))
            or os.path.isfile(os.path.join(repo_dir, "pyproject.toml"))
        ):
            return None
        vpy = os.path.join(env_dir, "venv", "bin", "python")
        res = _run(
            [vpy, "-m", "pip", "install", "-e", ".", "--quiet", "--no-warn-script-location"],
            repo_dir,
            self.setup_timeout,
        )
        if res.returncode != 0:
            return f"venv pip install -e 失败: {res.stderr.strip()[:300]}"
        return None

    def _clone_and_checkout(self, repo_url: str, base_commit: str, repo_dir: str) -> str | None:
        """git clone + checkout base_commit。失败返回错误文本，成功 None。"""
        if shutil.which("git") is None:
            return "git 不可用，无法准备仓库环境"
        clone = _run(
            ["git", "clone", "--no-checkout", "--filter=blob:none", repo_url, repo_dir],
            os.path.dirname(repo_dir) or ".",
            self.setup_timeout,
        )
        if clone.returncode != 0:
            # 部分克隆失败（网络/缓存目录残留）时重试一次全量 clone
            shutil.rmtree(repo_dir, ignore_errors=True)
            os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
            clone = _run(["git", "clone", repo_url, repo_dir], os.path.dirname(repo_dir), self.setup_timeout)
            if clone.returncode != 0:
                return f"git clone 失败: {clone.stderr.strip()[:300]}"
        co = _run(["git", "checkout", base_commit], repo_dir, self.setup_timeout)
        if co.returncode != 0:
            return f"git checkout {base_commit[:12]} 失败: {co.stderr.strip()[:300]}"
        logger.info("仓库环境准备完成: %s @ %s", repo_url, base_commit[:12])
        return None

    def _pip_install_editable(self, repo_dir: str) -> str | None:
        """pip install -e .（仓库 pyproject/setup.py 声明的依赖）。

        按用户确认的口径：仅装仓库自身依赖，不扫描 test_patch 的新增 import。
        无 setup.py/pyproject.toml 的仓库跳过（不视为错误）。
        """
        if not (
            os.path.isfile(os.path.join(repo_dir, "setup.py"))
            or os.path.isfile(os.path.join(repo_dir, "pyproject.toml"))
        ):
            return None
        res = _run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet", "--no-warn-script-location"],
            repo_dir,
            self.setup_timeout,
        )
        if res.returncode != 0:
            return f"pip install -e 失败: {res.stderr.strip()[:300]}"
        return None

    # ── gold test_patch 验证 ──────────────────────────────────────────────────

    def verify(
        self,
        repo_url: str,
        base_commit: str,
        test_patch: str,
        llm_patch: str,
        fail_to_pass: list[str],
        pass_to_pass: list[str] | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """SWE-bench 官方口径验证：test_patch 前后对比 + LLM 补丁修复判定。

        流程（在 setup 的仓库环境中）：
        1. 恢复干净工作区（git checkout -- . / clean -fd），丢弃上一轮 llm_patch 残留；
        2. 应用 test_patch（git apply）→ 跑 FAIL_TO_PASS 基线（应失败，记录失败数）；
        3. test_patch 全程留在工作区（不 stash，避免带走 untracked 新建测试文件）
           → 再应用 llm_patch（git apply，失败时降级为逐文件写入）
           → 重跑 FAIL_TO_PASS + PASS_TO_PASS；
        4. 判定：FAIL_TO_PASS 全过 且 PASS_TO_PASS 无回归 → passed；
        5. 无论结果，git checkout -- . / clean -fd 清除 llm_patch 修改
           + 重建 test_patch 基线（下一轮迭代/下一基线复用）。

        Args:
            repo_url: 仓库 URL（定位缓存环境）。
            base_commit: 基础 commit（定位缓存环境）。
            test_patch: gold test_patch（unified diff 文本）。
            llm_patch: LLM 生成的修复（完整文件代码或 unified diff）。
            fail_to_pass: FAIL_TO_PASS 测试节点列表（如 "test_foo.py::test_bar"）。
            pass_to_pass: PASS_TO_PASS 测试节点列表（可为空）。
            instance_id: 官方数据集真实 instance_id（F11／2026-10-19 Z 轮：
                官方 swebench harness 的 predictions 必须携带真实 instance_id；
                缺失时官方路径降级自建口径——绝不伪造）。

        Returns:
            与 ExecutorAgent.execute 同构 + repo_env / fail_to_pass / pass_to_pass 字段。
        """
        pass_to_pass = pass_to_pass or []
        env = self.setup(repo_url, base_commit)
        repo_dir = env["workdir"]
        base_result: dict[str, Any] = {
            "passed": False,
            "output": "",
            "coverage": 0.0,
            "failed_cases": [],
        }
        if env["error"] and not os.path.isdir(repo_dir):
            base_result["error_info"] = {"type": "repo_env_setup_failed", "message": env["error"]}
            base_result["repo_env"] = env
            return base_result

        # O35（2026-09-30 全面审查 P1）：verify() 与 setup() 共用同一工作区，
        # 但此前**不持锁**——setup() 明确为 (repo, commit) 目录加 per-env 锁
        # （L202 起的注释即写明"--parallel 下多任务同 (repo, commit) 并发"），
        # 而 verify() 在锁外做 `git checkout -- .` / `git clean -fdx` / 应用补丁 /
        # 跑测试。两线程同 (repo, commit) 并发 verify 时，一方的 checkout/clean
        # 会把另一方刚 apply 的 llm_patch / test_patch 抹掉，F2P/P2P 裁决
        # 静默失真（无任何报错）。现用**同一把 per-env_dir 锁**串行化。
        # 锁在 setup() 返回后获取（setup 内部的同名锁已释放，无死锁；
        # 本锁为非重入 Lock，故 verify 体内不得再进 setup()）。
        # 获取点紧贴 try——下方**所有**路径（官方 harness 提前 return / 临时
        # 文件写盘失败 / 正常收尾 / 任意异常）统一由 finally 释放，无泄漏。
        _repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        _verify_env_dir = os.path.join(self.env_root, _repo_name, base_commit[:12])
        _verify_lock = _get_repo_setup_lock(_verify_env_dir)
        # F10（2026-10-19 Z 轮审查 P1）：共享 venv 模式下，venv 的 editable 绑定是
        # **跨 commit 共享的可变状态**——只在 setup 缓存命中时校验还不够：setup
        # 返回到本函数真正跑测试之间，另一 commit 的 setup/verify 可能把 venv
        # 重指向别处。故在 per-env 锁之外再持**仓库级 venv 锁**直到验证结束
        # （锁序 env→venv，与 setup 内部一致，无死锁），并在锁内复检绑定：
        # 无法绑定目标 commit 时 fail-closed（不产出错源裁决）。
        _shared_venv_dir: str | None = None
        _verify_venv_lock: threading.Lock | None = None
        if self._shared_venv_reuse_enabled():
            _shared_venv_dir = self._repo_venv_dir(repo_url, repo_dir)
            _verify_venv_lock = _get_repo_setup_lock(_shared_venv_dir)
        _verify_lock.acquire()
        if _verify_venv_lock is not None:
            _verify_venv_lock.acquire()
        try:
            if _shared_venv_dir is not None:
                _bind_err = self._repoint_shared_venv_locked(_shared_venv_dir, repo_dir, base_commit)
                if _bind_err is not None:
                    logger.warning(
                        "F10 共享 venv 绑定复核失败，拒绝在未知/错误源码上裁决: %s",
                        _bind_err,
                    )
                    base_result["error_info"] = {
                        "type": "repo_venv_rebind_failed",
                        "message": (f"共享 venv editable 无法绑定目标 commit {base_commit[:12]}: {_bind_err}"),
                    }
                    base_result["repo_env"] = env
                    return base_result
            # M3（2026-09-29 审查 P0）：官方 swebench 包路径（SWE_USE_OFFICIAL_HARNESS=true
            # 时启用，默认 false 保持历史自建 harness 口径）。启用时先尝试
            # `python -m swebench.harness.run_evaluation`，成功则以官方结果为准；
            # 官方包未安装 / 执行失败时降级历史自建口径（零行为变化）。
            if self._official_harness_enabled():
                # 官方 harness 自行 clone/执行，不经过 _run_test_nodes，故对其
                # 前置一次 conftest 扫描。用本地缓存克隆（同 repo_url + 同
                # base_commit → conftest 内容一致）作代理面：命中即不调用官方
                # harness，全部节点记失败（passed=False，不会假过）。
                _refuse = self._scan_repo_conftests(repo_dir) if os.path.isdir(repo_dir) else []
                if _refuse:
                    _detail = "; ".join(f"{rel}: {','.join(feats)}" for rel, feats in _refuse[:5])[:300]
                    logger.warning(
                        "S6 conftest 守卫：%d 个 conftest.py 命中硬拒特征，拒绝调用官方 swebench harness（%s）",
                        len(_refuse),
                        _detail,
                    )
                    base_result["output"] = f"[S6 conftest 守卫拒绝执行] {_detail}"
                    base_result["failed_cases"] = [
                        {"name": node, "error": f"S6 conftest 危险调用守卫拒绝执行: {_detail}"}
                        for node in [*fail_to_pass, *pass_to_pass]
                    ]
                    base_result["repo_env"] = env
                    return base_result
                _official_result = self._run_official_swebench_harness(
                    repo_url=repo_url,
                    base_commit=base_commit,
                    test_patch=test_patch,
                    llm_patch=llm_patch,
                    fail_to_pass=fail_to_pass,
                    pass_to_pass=pass_to_pass,
                    instance_id=instance_id,
                )
                if _official_result is not None:
                    base_result.update(_official_result)
                    base_result["repo_env"] = env
                    base_result["harness_source"] = "official_swebench"
                    return base_result
                # 官方路径降级：记日志后继续自建口径
                logger.info("M3 官方 swebench harness 降级（未安装/执行失败），回退自建 harness 口径")

            # 临时文件名按 (pid, thread) 双键隔离——2026-09-26 全面审查 P1 并发安全：
            # 此前仅 os.getpid()，--parallel 下多线程同仓库 verify 并发时同一 pid
            # 的多个线程命中同一临时文件（一个线程正在 git apply 的补丁文件被
            # 另一个线程覆盖/删除 → 半成品读入）。pid+thread ident 双键在
            # ThreadPoolExecutor 复用线程场景下仍唯一（ident 在 thread.join() 前
            # 不复用，且 os.getpid() 恒为当前进程，组合键进程内唯一）。
            test_file = os.path.join(
                tempfile.gettempdir(),
                f"aitester_repo_test_{base_commit[:8]}_{os.getpid()}_{threading.get_ident()}.patch",
            )
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_patch)

            # 内层 try：主验证体；finally 只负责临时补丁文件清理。
            # 外层 finally（本 try 的配对）负责释放 _verify_lock。
            try:
                # 1. 恢复干净基线（丢弃 llm_patch 残留与 test_patch 残留，从 HEAD 起）
                _run(["git", "checkout", "--", "."], repo_dir, 60)
                _run(["git", "clean", "-fd", "-x"], repo_dir, 120)

                # 2. 应用 test_patch（基线 FAIL_TO_PASS 验证：确认缺陷可复现）。
                # 空 test_patch（任务无 gold 测试）跳过 apply 与 --check，直接进
                # FAIL_TO_PASS 基线实测（正常函数在基线就过 → base_not_failing）。
                # 非空 test_patch：损坏文本经 git apply --check 拦截 → 显式诊断；
                # 合法补丁走 _apply_patch_robust（含 Apple Git new-file bug 兜底）。
                if test_patch and test_patch.strip():
                    pre_apply = _run(["git", "apply", "--check", test_file], repo_dir, 60)
                    if pre_apply.returncode != 0:
                        base_result["error_info"] = {
                            "type": "test_patch_apply_failed",
                            "message": pre_apply.stderr.strip()[:500]
                            or "test_patch 无法应用（git apply --check 拒绝）",
                        }
                        base_result["repo_env"] = env
                        return base_result
                    self._apply_patch_robust(repo_dir, test_file)
                baseline_failures = self._run_fail_to_pass(repo_dir, fail_to_pass, repo_url=repo_url)
                # 基线全过 = 任务数据有问题（缺陷已修）或 test_patch 未覆盖缺陷，如实记录
                base_not_failing = len(baseline_failures["failed_cases"]) == 0
                # F05（2026-10-22 第三方复审 P1）：PASS_TO_PASS 必须在**应用
                # llm_patch 之前**测基线。历史实现只在补丁后测一次，却把它当
                # "基线通过率"喂 M3 门禁——补丁本身打坏 P2P（基线 2/2、补丁后
                # 1/2）时被误判 harness_invalid 剔除，等于把有效回归洗成环境噪声。
                p2p_baseline = (
                    self._run_pass_to_pass(repo_dir, pass_to_pass, repo_url=repo_url)
                    if pass_to_pass
                    else {"expected": 0, "passed": 0, "failed_cases": []}
                )

                # 3. 应用 llm_patch 后重跑。test_patch 全程留在工作区（不 stash，
                # 避免带走 untracked 新建测试文件）；llm_patch 经
                # _apply_patch_robust → git apply（含 --check 预检 + new-file
                # 兜底回填），失败不阻断，FAIL_TO_PASS 实测裁决。
                llm_applied = self._apply_llm_patch(repo_dir, llm_patch)
                after = self._run_fail_to_pass(repo_dir, fail_to_pass, repo_url=repo_url)
                p2p = (
                    self._run_pass_to_pass(repo_dir, pass_to_pass, repo_url=repo_url)
                    if pass_to_pass
                    else {"expected": 0, "passed": 0, "failed_cases": []}
                )

                f2p_all = len(fail_to_pass) > 0 and len(after["failed_cases"]) == 0
                p2p_no_regression = p2p["expected"] == 0 or len(p2p["failed_cases"]) == 0
                passed = f2p_all and p2p_no_regression and not base_not_failing

                # 4. 恢复"仅 test_patch"基线（下一轮迭代/下一基线复用该环境）。
                # checkout -- . 清除 llm_patch 对已跟踪文件的修改；clean -fdx
                # 清除全部 untracked（含 test_patch 新建测试文件 + llm_patch
                # 副产物）；_apply_patch_robust 重建 test_patch 基线（new-file
                # 兜底回填每轮生效）。空 test_patch 时跳过重建。
                _run(["git", "checkout", "--", "."], repo_dir, 60)
                _run(["git", "clean", "-fdx"], repo_dir, 120)
                if test_patch and test_patch.strip():
                    self._apply_patch_robust(repo_dir, test_file)

                output = f"[FAIL_TO_PASS baseline] {baseline_failures['expected'] - len(baseline_failures['failed_cases'])}/{baseline_failures['expected']} passed\n"
                output += f"[FAIL_TO_PASS after-llm-patch] {after['expected'] - len(after['failed_cases'])}/{after['expected']} passed\n"
                output += f"[PASS_TO_PASS baseline] {p2p_baseline['passed']}/{p2p_baseline['expected']} passed\n"
                output += f"[PASS_TO_PASS after-llm-patch] {p2p['passed']}/{p2p['expected']} passed"
                if not llm_applied:
                    output += "\n[llm_patch_apply_failed] 补丁未成功应用（判定按 FAIL_TO_PASS 实测）"
                base_result["passed"] = passed
                base_result["output"] = output
                base_result["failed_cases"] = after["failed_cases"]
                base_result["repo_env"] = dict(env.items())
                base_result["fail_to_pass"] = {
                    "expected": after["expected"],
                    "passed": after["expected"] - len(after["failed_cases"]),
                    "baseline_passed": baseline_failures["expected"] - len(baseline_failures["failed_cases"]),
                }
                base_result["pass_to_pass"] = {"expected": p2p["expected"], "passed": p2p["passed"]}
                base_result["pass_to_pass_baseline"] = {
                    "expected": p2p_baseline["expected"],
                    "passed": p2p_baseline["passed"],
                }
                base_result["llm_patch_applied"] = llm_applied
                # M3（2026-09-29 审查 P0）：基线 PASS_TO_PASS 硬前置门禁。
                # 历史口径：P2P 通过率无检查，基线环境本身损坏（如 click 版本
                # 不兼容导致 P2P 4/131）时实验照常产出"结果"，但这些结果
                # 既不能证明系统好也不能证明系统差——harness 无效。
                # 现加硬门禁：P2P 期望数 > 0 且通过率 < P2P_GATE_THRESHOLD
                # （默认 0.95，环境变量 P2P_GATE_THRESHOLD 可调）时，
                # 标记 harness_invalid=True 并将 passed 强制置 False
                # （结果行带 error_info type=harness_invalid，调用方应剔除）。
                # 默认 0.95 与 M3 审查建议"基线 P2P≥95%"一致；
                # P2P_GATE_ENABLE=false（默认 true）可关闭门禁恢复历史口径。
                _p2p_gate_enabled = env_flag_opt_out("P2P_GATE_ENABLE")
                # J-1d（2026-10-17）：原裸 float(os.getenv(...)) 遇坏值抛 ValueError，会把
                # 判分路径整体打断；阈值定义域即 [0,1]，越界属配置错误而非意图。口径与
                # 姊妹门禁 config.SWE_BENCH_P2P_GATE_THRESHOLD（_parse_float_env 同范围）对齐。
                _p2p_gate_threshold = env_float("P2P_GATE_THRESHOLD", 0.95, lo=0.0, hi=1.0)
                _harness_invalid = False
                if _p2p_gate_enabled and p2p_baseline["expected"] > 0:
                    # F05：门禁只看**补丁前**基线；补丁后的 P2P 失败已计入
                    # passed（回归），不得再被改写成 harness_invalid。
                    _p2p_baseline_rate = p2p_baseline["passed"] / p2p_baseline["expected"]
                    base_result["p2p_baseline_rate"] = round(_p2p_baseline_rate, 4)
                    if _p2p_baseline_rate < _p2p_gate_threshold:
                        _harness_invalid = True
                        base_result["passed"] = False
                        base_result["error_info"] = {
                            "type": "harness_invalid",
                            "message": (
                                f"M3 基线 P2P 门禁：P2P 通过率 {_p2p_baseline_rate:.2%} "
                                f"低于阈值 {_p2p_gate_threshold:.2%}（期望 {p2p_baseline['expected']}，"
                                f"通过 {p2p_baseline['passed']}），harness 环境本身损坏，"
                                "实验结果不可信（应剔除本任务）"
                            ),
                        }
                        logger.warning(
                            "M3 基线 P2P 门禁未通过：P2P %d/%d（%.2f%% < %.2f%%），harness_invalid=True",
                            p2p_baseline["passed"],
                            p2p_baseline["expected"],
                            _p2p_baseline_rate * 100,
                            _p2p_gate_threshold * 100,
                        )
                # J-4（2026-10-17）：此前 harness_invalid 由两条腿分别写
                # （拦截分支写 True、`else` 分支写 False），而**门禁开启且基线
                # 健康**这条腿无人写 → 结果字典缺键。该字典整体落进
                # `final_state["repo_verification"]`（run_benchmark L2325），
                # 官方 harness 分支又恒带 `harness_invalid: False`——同一字段
                # 在不同健康路径里时有时无：按 `["harness_invalid"]` 取值即
                # KeyError，按 `.get()` 取则 None 与 False 混用。现改由唯一
                # 事实源 `_harness_invalid` 单点落键（此前它被赋值两次却从未
                # 被读过，正是"本该单点落键"的残留证据），四条腿返回形状同构。
                base_result["harness_invalid"] = _harness_invalid
                if base_not_failing:
                    base_result["error_info"] = {
                        "type": "base_not_failing",
                        "message": "FAIL_TO_PASS 在基线（未打修复补丁）上全部通过：缺陷不可复现或任务数据异常",
                    }
                return base_result
            finally:
                if os.path.isfile(test_file):
                    os.remove(test_file)
        finally:
            # O35：与 acquire() 配对（覆盖官方 harness 提前 return / 临时文件
            # 写盘失败 / 正常收尾 / 任意异常——非重入 Lock，单点释放）
            # F10：共享 venv 锁按逆序单点释放（先 venv 后 env）。
            if _verify_venv_lock is not None:
                _verify_venv_lock.release()
            _verify_lock.release()

    def _run_fail_to_pass(self, repo_dir: str, fail_to_pass: list[str], repo_url: str = "") -> dict[str, Any]:
        """运行 FAIL_TO_PASS 测试节点，返回 expected 总数与 failed_cases 列表。"""
        return self._run_test_nodes(repo_dir, fail_to_pass, repo_url=repo_url)

    def _run_pass_to_pass(self, repo_dir: str, pass_to_pass: list[str], repo_url: str = "") -> dict[str, Any]:
        """运行 PASS_TO_PASS 回归测试节点。"""
        return self._run_test_nodes(repo_dir, pass_to_pass, repo_url=repo_url)

    #: S6 conftest 扫描的单文件体积上限：超过即不解析，按"未审查"fail-closed
    #: （2 MiB 远大于任何真实 conftest.py，仅用于阻断异常大文件拖慢验证）。
    _CONFTEST_SCAN_MAX_BYTES = 2 * 1024 * 1024

    #: os.walk 时跳过的目录：版本库/虚拟环境/依赖缓存里不会有被测仓库的
    #: conftest.py（且数量巨大），跳过既省时也避免把旁 venv 的文件当仓库代码。
    _CONFTEST_SCAN_SKIP_DIRS = frozenset({".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".tox"})

    @classmethod
    def _scan_repo_conftests(cls, repo_dir: str) -> list[tuple[str, list[str]]]:
        """扫描仓库工作树内全部 conftest.py，返回**硬拒**命中（空 = 可执行）。

        裁决口径（依据见 ``src/tools/dependency.py`` 的
        :data:`_CONTEST_HARD_REFUSE` 实测注释）：

        - Tier 1 特征命中 → 硬拒；
        - 文件读不懂（解析失败 / OSError / 超体积）→ 硬拒。扫描用宿主解释器的
          AST，被测仓库跑在旁 venv 的另一解释器上，宿主读不懂 ≠ 不会执行，
          故按 G 轮 fail-closed 决策拒绝；
        - Tier 2 特征命中（subprocess / socket / urllib / shutil.rmtree 等真实
          测试基建常用能力）→ 仅 WARNING 留审计线索，不阻断。

        Returns:
            ``[(相对路径, 命中特征列表)]``，仅含硬拒项。日志与返回值都只含
            **路径与特征名**，不回显文件内容（第三方 conftest 可能含凭证）。
        """
        from src.tools.dependency import _CONTEST_HARD_REFUSE, conftest_ast_scan_enabled, scan_conftest_ast_safety

        if not conftest_ast_scan_enabled():
            return []
        refused: list[tuple[str, list[str]]] = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in cls._CONFTEST_SCAN_SKIP_DIRS]
            if "conftest.py" not in files:
                continue
            path = os.path.join(root, "conftest.py")
            rel = os.path.relpath(path, repo_dir)
            try:
                if os.path.getsize(path) > cls._CONFTEST_SCAN_MAX_BYTES:
                    refused.append((rel, ["<oversize>"]))
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    code = f.read()
            except OSError as e:
                logger.warning("S6 conftest 扫描读取失败 %s（按未审查 fail-closed）: %s", rel, e)
                refused.append((rel, ["<unreadable>"]))
                continue
            findings, parsed = scan_conftest_ast_safety(code)
            if not parsed:
                logger.warning("S6 conftest 扫描无法解析 %s（按未审查 fail-closed）", rel)
                refused.append((rel, ["<unparseable>"]))
                continue
            hard = sorted(set(findings) & _CONTEST_HARD_REFUSE)
            if hard:
                refused.append((rel, hard))
            elif findings:
                logger.warning("S6 conftest Tier 2 告警（不阻断）：%s 命中 %s", rel, sorted(findings))
        return refused

    def _run_test_nodes(self, repo_dir: str, test_nodes: list[str], repo_url: str = "") -> dict[str, Any]:
        """对仓库目录运行指定 pytest 节点，解析 failed_cases。

        节点名即 pytest -k 无法精确表达（:: 语法），逐个节点经
        `pytest <node>` 单独运行（SWE-bench 官方 harness 同口径），
        失败用例记录为 {"name": node, "error": tail}。

        cwd 用绝对路径传入（而非依赖 cwd 参数）：git apply / pytest 等
        子进程均以 subprocess.run(cwd=...) 显式定位，避免父进程 CWD 干扰。

        P0 4.3：repo_url 传入后 _venv_python 解析仓库级共享 venv 目录。
        """
        if not test_nodes:
            return {"expected": 0, "passed": 0, "failed_cases": []}
        # S6/M11（2026-09-29 审查 P0 声明，2026-10-16 G 轮接线）：conftest.py
        # 危险调用扫描。pytest 在**收集阶段**就 import 并执行仓库自带
        # conftest.py——早于任何测试断言，是 repo 级链路在宿主上执行第三方代码
        # 的最早入口。此前 scan_conftest_ast_safety 无任何生产调用点（守卫形同
        # 不存在），现于唯一的 pytest 咽喉点前置裁决：Tier 1 命中或文件"读不懂"
        # 一律不执行 pytest（fail-closed），全部节点记失败并标注守卫拒绝，故
        # 既不会假过（F2P/P2P 全 0），也能在批次日志里区分"守卫拒绝"与"用例失败"。
        refuse = self._scan_repo_conftests(repo_dir)
        if refuse:
            detail = "; ".join(f"{rel}: {','.join(feats)}" for rel, feats in refuse[:5])[:300]
            logger.warning(
                "S6 conftest 守卫：%d 个 conftest.py 命中硬拒特征，拒绝在该仓库执行 pytest（%s）",
                len(refuse),
                detail,
            )
            return {
                "expected": len(test_nodes),
                "passed": 0,
                "failed_cases": [
                    {"name": node, "error": f"S6 conftest 危险调用守卫拒绝执行 pytest: {detail}"} for node in test_nodes
                ],
            }
        env = scrub_os_environ()
        # 被测仓库根目录入 PYTHONPATH：gold test_patch 的测试文件通常
        # `from <repo_pkg> import ...`，仓库根须可导入。
        #
        # PYTHONPATH 前缀策略随模式切换：
        # - venv 模式（use_venv=True）：`pip install -e` 已把本 commit 源码
        #   的 editable 安装写进 venv 自身 site-packages，venv 的
        #   `import <repo_pkg>` 天然解析到本 commit——**不注入 PYTHONPATH**
        #   （实测：venv python 下带 PYTHONPATH 注入会 ImportError，不带则
        #   正常通过 editable 安装导入；注入还会把宿主/其它 commit 路径混入
        #   搜索序，破坏隔离）。
        # - 全局模式（use_venv=False）：各 repo_env 共享同一全局 python，
        #   全局 site-packages 的 editable 安装指向"最近一次 pip install -e"
        #   的 commit 源码 → 跨 commit 任务 `import <repo_pkg>` 解析到错误
        #   版本（AttributeError / ImportError，与 LLM 补丁无关）。src 布局
        #   仓库的包在 <repo>/src 而非仓库根，故把 src 目录（若存在）排最前，
        #   让当前 commit 源码优先于全局 editable 安装。
        if self.use_venv:
            _path_dirs: list[str] = []
        else:
            _path_dirs = [repo_dir]
            if os.path.isdir(os.path.join(repo_dir, "src")):
                _path_dirs.insert(0, os.path.join(repo_dir, "src"))
        env["PYTHONPATH"] = os.pathsep.join(
            _path_dirs + [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
        )
        failed_cases: list[dict[str, Any]] = []
        passed_count = 0
        # O 轮（2026-10-18）确定性修复：禁止子 pytest 写 __pycache__。
        # 根因（O-4 在 CI/探针复现）：baseline 与 llm_patch 两阶段在 1s 内写入
        # **同尺寸**源码时，CPython 缓存的 pyc 头 (源 mtime 整秒, size) 不变 →
        # 第二轮复用 baseline 字节码 → "补丁明明应用成功却仍失败"的随机假红
        # （本地 executor-repo-verify 6/15 复现；CI 侧曾用 sitecustomize 规避）。
        # 在唯一 pytest 咽喉点写 PYTHONDONTWRITEBYTECODE + -B 双保险（env 可
        # 传播到 pytest 子进程），彻底消除 mtime 粒度竞态。
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # venv 隔离：pytest 用该环境旁 venv 的 python（依赖/版本与全局解耦）
        env_dir = os.path.dirname(repo_dir)  # repo_dir = <env_dir>/repo
        _py = self._venv_python(env_dir, repo_url=repo_url, repo_dir=repo_dir) or sys.executable
        if self.use_venv:
            # venv 的 sys.executable 即该环境 python；把其 bin 目录加入 PATH，
            # 子进程内再调 python/pip 时也指向 venv（避免落回宿主 python）
            _venv_bin = os.path.dirname(_py)
            _existing_path = env.get("PATH") or ""
            env["PATH"] = _venv_bin + os.pathsep + _existing_path if _existing_path else _venv_bin
        for node in test_nodes:
            res = _run(
                [_py, "-B", "-m", "pytest", "-p", "no:cacheprovider", node, "--tb=short", "-q"],
                repo_dir,
                self.timeout,
                env,
            )
            if res.returncode in (0, 1):
                _node_output = res.stdout + res.stderr
                if res.returncode == 0 and run_has_effective_pass(0, _node_output):
                    passed_count += 1
                elif res.returncode == 0:
                    # BE（2026-10-21）：rc==0 但无有效通过（全 skip / xfail /
                    # deselect）→ 记失败。F2P/P2P 判定消费 failed_cases
                    # （f2p_all / p2p_no_regression 看"无失败用例"），若放行
                    # 会把"没跑起来"读成"补丁正确"。
                    failed_cases.append(
                        {
                            "name": node,
                            "error": f"无有效通过（rc=0，摘要无 passed / 全 skip）: {_node_output.strip()[-400:]}",
                        }
                    )
                else:
                    failed_cases.append({"name": node, "error": _node_output.strip()[-400:]})
            elif res.returncode == 4:
                # 节点解析失败（测试不存在 / 收集错误）：按失败记录
                failed_cases.append(
                    {"name": node, "error": f"节点解析失败 (exit 4): {(res.stdout + res.stderr).strip()[:300]}"}
                )
            elif res.returncode == 5:
                # 无测试收集（仓库该 commit 下无 pytest 测试）：按失败记录
                failed_cases.append({"name": node, "error": "无测试可收集 (exit 5)"})
            elif res.returncode == 124:
                # 节点执行超时（_run 收敛后的哨兵退出码，GNU timeout 口径）：
                # 按失败记录并继续下一节点（此前 TimeoutExpired 穿透 verify()
                # 使整个验证任务崩溃，2026-09-26 全面审查 P1 鲁棒性修复）
                failed_cases.append(
                    {"name": node, "error": f"节点执行超时（>{self.timeout}s）: {res.stderr.strip()[:200]}"}
                )
            else:
                failed_cases.append({"name": node, "error": (res.stdout + res.stderr).strip()[-400:]})
        return {"expected": len(test_nodes), "passed": passed_count, "failed_cases": failed_cases}

    # M2（2026-09-29 审查 P0）：测试文件保护——LLM 补丁触碰测试目录 / 测试
    # 文件即拒绝应用（防改 gold 测试让 F2P 假过）。_apply_llm_patch 在
    # test_patch 之后应用，无路径过滤时 LLM 可改写 gold 测试文件。
    # O35（2026-09-30 全面审查 P2）：补两个漏检形态——
    #   - 裸 `test.py`（`test_[^/]*\.py` 要求 test 后有下划线，命中不了）；
    #   - `*_tests/` 目录（`tests?/` 只覆盖 test/、tests/、testing/）。
    # 二者都是真实仓库里常见的 gold 测试落点，漏检即绕过 M2 守卫。
    _TEST_PATH_RE = re.compile(
        r"(^|/)(tests?|testing)/|(^|/)[^/]*_tests?/|(^|/)test_[^/]*\.py$|(^|/)test\.py$"
        r"|(^|/)[^/]+_test\.py$|(^|/)conftest\.py$",
        re.IGNORECASE,
    )

    # M3（2026-09-29 审查 P0）官方 swebench 包开关（SWE_USE_OFFICIAL_HARNESS=true
    # 时启用，默认 false 保持历史自建 harness 口径）。启用时 verify() 在
    # 自建路径之外先尝试 `python -m swebench.harness.run_evaluation`
    # （pip install swebench），成功则以官方结果为准；失败/未安装时降级
    # 历史自建口径（零行为变化）。
    @staticmethod
    def _official_harness_enabled() -> bool:
        return env_flag("SWE_USE_OFFICIAL_HARNESS")

    @staticmethod
    def _official_run_id(base_commit: str) -> str:
        """官方 runner 的 run_id：安全字符集 + pid/线程唯一（并发互不覆盖报告）。"""
        commit_part = re.sub(r"[^A-Za-z0-9_.-]", "", base_commit)[:8] or "unknown"
        return f"aitester-{commit_part}-{os.getpid()}-{threading.get_ident()}"

    @staticmethod
    def _official_report_candidate(payload: Any, instance_id: str, depth: int = 0) -> dict[str, Any] | None:
        """在官方报告 JSON 中定位 instance_id 对应的 per-instance 报告。

        官方报告形状随版本略有差异，兼容两种已核对形态：
        - 聚合报告 dict：``{instance_id: {"resolved": bool, "tests_status": {...}}}``；
        - per-instance 报告：``{"instance_id": ..., "resolved": ..., "tests_status": ...}``
          （官方 run 目录按 run/model/instance 分层，文件内自带 instance_id）。
        递归（限深）扫描嵌套 dict，命中即返回；找不到返回 None。
        """
        if depth > 6 or not isinstance(payload, dict):
            return None
        # 形态 1：聚合报告以 instance_id 为键
        candidate = payload.get(instance_id)
        if isinstance(candidate, dict) and ("resolved" in candidate or "tests_status" in candidate):
            return candidate
        # 形态 2：per-instance 报告带 instance_id 字段
        if payload.get("instance_id") == instance_id and ("resolved" in payload or "tests_status" in payload):
            return payload
        # 形态 3：嵌套容器（run/model 目录层、{"results": {...}} 等）→ 递归
        for value in payload.values():
            found = RepoExecutor._official_report_candidate(value, instance_id, depth + 1)
            if found is not None:
                return found
        return None

    @classmethod
    def _find_official_instance_report(cls, report_dir: str, instance_id: str) -> dict[str, Any] | None:
        """递归扫描 report_dir 下 *.json，返回 instance_id 匹配的 per-instance 报告。"""
        for root, _dirs, files in os.walk(report_dir):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(root, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        payload = json.load(f)
                except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.info("M3 官方 swebench 报告文件跳过（%s）: %s", path, e)
                    continue
                found = cls._official_report_candidate(payload, instance_id)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _official_report_to_result(
        report: dict[str, Any], fail_to_pass: list[str], pass_to_pass: list[str]
    ) -> dict[str, Any] | None:
        """校验官方 per-instance report schema 并换算为自建口径同构结果。

        官方 schema（已静态核对官方接口）::

            {"resolved": bool,
             "tests_status": {"FAIL_TO_PASS": {"success": [...], "failure": [...]},
                              "PASS_TO_PASS": {"success": [...], "failure": [...]}}}

        口径：passed = resolved；passed 计数分别取两组 success 列表长度。
        schema 不符 / resolved=True 但 success 数不足 expected（报告与任务
        错配）→ 返回 None，调用方降级自建 harness——**绝不假过**。
        """
        resolved = report.get("resolved")
        if not isinstance(resolved, bool):
            logger.info("M3 官方 swebench 报告 schema 不符（resolved=%r 非 bool），降级自建口径", resolved)
            return None
        tests_status = report.get("tests_status")
        if not isinstance(tests_status, dict):
            logger.info("M3 官方 swebench 报告 schema 不符（tests_status 缺失/非 dict），降级自建口径")
            return None
        groups: dict[str, list[Any]] = {}
        for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            group = tests_status.get(key)
            # 官方每组为 {"success": [...], "failure": [...]}；success 必须是列表
            if not isinstance(group, dict) or not isinstance(group.get("success"), list):
                logger.info(
                    "M3 官方 swebench 报告 schema 不符（tests_status.%s.success 缺失/非 list），降级自建口径",
                    key,
                )
                return None
            groups[key] = group["success"]
        f2p_passed = len(groups["FAIL_TO_PASS"])
        p2p_passed = len(groups["PASS_TO_PASS"])
        # 一致性：resolved=True 但 success 数不足 expected → schema/报告错配，降级
        if resolved and (f2p_passed < len(fail_to_pass) or p2p_passed < len(pass_to_pass)):
            logger.info(
                "M3 官方 swebench 报告与任务不匹配（resolved=True 但 success f2p=%d/%d p2p=%d/%d），降级自建口径",
                f2p_passed,
                len(fail_to_pass),
                p2p_passed,
                len(pass_to_pass),
            )
            return None
        return {
            "passed": resolved,
            "fail_to_pass": {"expected": len(fail_to_pass), "passed": f2p_passed},
            "pass_to_pass": {"expected": len(pass_to_pass), "passed": p2p_passed},
            "harness_invalid": False,
        }

    def _run_official_swebench_harness(
        self,
        repo_url: str,
        base_commit: str,
        test_patch: str,
        llm_patch: str,
        fail_to_pass: list[str],
        pass_to_pass: list[str],
        instance_id: str | None = None,
        dataset_name: str | None = None,
    ) -> dict[str, Any] | None:
        """M3：官方 swebench 包验证路径（官方 CLI + 官方报告 schema）。

        2026-10-19 Z 轮审查（F11）重写：历史实现把位置参数喂给官方 CLI、用
        ``patch`` 字段、伪造 ``instance_id`` 并读取旁置 ``_report.json``——与
        官方接口全链不符，真实包下必然参数错误或解析不到。现行口径：

        1. 预测 JSON 为官方 predictions 列表：``[{instance_id, model_name_or_path,
           model_patch}]``；**只传 LLM 补丁**（test_patch 是评测侧 gold 测试，
           官方 harness 会按数据集自行应用，故不作为 model_patch）。
        2. 命名参数调用官方 CLI：``--dataset_name`` / ``--split`` /
           ``--predictions_path`` / ``--max_workers`` / ``--run_id`` /
           ``--report_dir``；run_id 形如 ``aitester-<sha8>-<pid>-<thread>``，
           report_dir 为临时目录（读取后随 TemporaryDirectory 清理）。
        3. 报告解析：递归扫描 report_dir 下 ``*.json``，定位 instance_id 匹配的
           per-instance report，读 ``resolved`` 与
           ``tests_status.FAIL_TO_PASS.success`` / ``PASS_TO_PASS.success``。
        4. 任一环不符（无 instance_id / 无报告 / schema 不符 / rc!=0）→
           ``logger.info`` + 返回 None 降级自建 harness——**绝不把缺失当通过**。

        已知边界（如实披露）：本仓**未锁定官方 swebench 包版本**，且**真实包
        验收仍未执行**（无网络/无 Docker 的静态审查环境）。数据集名默认假设
        ``SWE-bench/SWE-bench_Lite``，可由调用方经 ``dataset_name`` 参数或
        覆写模块常量 ``_OFFICIAL_HARNESS_DATASET`` 调整（刻意不新增环境变量，
        避免 ADR-0003 env 预算门禁）。官方接口若再变更，本路径是"尽力而为的
        降级支路"：失败即回退自建口径，不会假过。

        Args:
            repo_url: 仓库 URL（仅用于日志/接口兼容；官方 runner 从数据集读取
                仓库信息）。
            base_commit: 基础 commit（用于生成 run_id；官方 runner 从数据集读取
                base commit）。
            test_patch: gold test_patch（**不传给官方 runner**——由官方 harness
                按数据集自行应用；保留参数仅为调用点接口稳定）。
            llm_patch: LLM 生成的修复（unified diff），作为 predictions 的
                ``model_patch``。
            fail_to_pass: FAIL_TO_PASS 测试节点列表（用于 expected 计数）。
            pass_to_pass: PASS_TO_PASS 测试节点列表（用于 expected 计数）。
            instance_id: 官方数据集中的真实 instance_id（如
                ``django__django-12345``）。缺失/空 → 日志后返回 None（无法
                构造合法 predictions，降级自建口径）。
            dataset_name: 官方数据集名；``None``（默认）= 取模块常量
                :data:`_OFFICIAL_HARNESS_DATASET`（运行期读取，测试/调用方可经
                monkeypatch 覆写常量，或直接传参覆盖）。

        Returns:
            与 verify() 自建口径同构的结果 dict（passed / fail_to_pass /
            pass_to_pass / harness_invalid / output），或 None（降级自建口径）。
        """
        if not instance_id:
            logger.info(
                "M3 官方 swebench harness 缺少真实 instance_id（repo=%s commit=%s），降级自建口径",
                repo_url,
                base_commit[:12],
            )
            return None
        # 运行期解析默认值（而非函数默认参数在 def 期绑定）——docstring 承诺的
        # "覆写模块常量"才真正生效。
        resolved_dataset = dataset_name or _OFFICIAL_HARNESS_DATASET

        run_id = self._official_run_id(base_commit)
        try:
            with tempfile.TemporaryDirectory(prefix="aitester_swebench_") as work_dir:
                pred_file = os.path.join(work_dir, "predictions.json")
                report_dir = os.path.join(work_dir, "report")
                os.makedirs(report_dir, exist_ok=True)
                predictions = [
                    {
                        "instance_id": instance_id,
                        "model_name_or_path": "aitester",
                        "model_patch": llm_patch or "",
                    }
                ]
                with open(pred_file, "w", encoding="utf-8") as f:
                    json.dump(predictions, f, ensure_ascii=False, indent=2, allow_nan=False)

                # 2026-10-11 全面优化批次：经 _run 收敛点走 run_with_timeout
                # （孤儿风险消除；超时归一为 returncode=124 哨兵 → 下方按
                # rc!=0 降级自建口径）。
                res = _run(
                    [
                        sys.executable,
                        "-m",
                        "swebench.harness.run_evaluation",
                        "--dataset_name",
                        resolved_dataset,
                        "--split",
                        _OFFICIAL_HARNESS_SPLIT,
                        "--predictions_path",
                        pred_file,
                        "--max_workers",
                        str(_OFFICIAL_HARNESS_MAX_WORKERS),
                        "--run_id",
                        run_id,
                        "--report_dir",
                        report_dir,
                    ],
                    work_dir,
                    max(self.timeout, _OFFICIAL_HARNESS_TIMEOUT_FLOOR),
                )
                if res.returncode != 0:
                    logger.info(
                        "M3 官方 swebench runner 退出码 %d（降级自建口径）: %s",
                        res.returncode,
                        (res.stderr or res.stdout).strip()[:300],
                    )
                    return None

                report = self._find_official_instance_report(report_dir, instance_id)
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError) as e:
            # OSError 覆盖 swebench 包未安装（python -m 找不到模块时由解释器
            # 以 rc!=0 返回，本分支兜底子进程启动级异常）；JSON 解析异常 →
            # 降级。TemporaryDirectory 退出时自动清理 predictions/report。
            logger.info("M3 官方 swebench 路径异常（降级自建口径）: %s", e)
            return None

        if report is None:
            logger.info(
                "M3 官方 swebench 报告缺失或无法定位 instance %s（report_dir 已扫描，降级自建口径）",
                instance_id,
            )
            return None
        result = self._official_report_to_result(report, fail_to_pass, pass_to_pass)
        if result is None:
            return None
        result["output"] = (
            f"[M3 官方 swebench harness] resolved={result['passed']} "
            f"f2p={result['fail_to_pass']['passed']}/{result['fail_to_pass']['expected']} "
            f"p2p={result['pass_to_pass']['passed']}/{result['pass_to_pass']['expected']} "
            f"instance={instance_id} run_id={run_id}"
        )
        return result

    @classmethod
    def _split_diff_hunks(cls, patch_text: str) -> list[tuple[list[str], list[str], list[str]]]:
        """把 unified diff 按 hunk 切成 ``(after 行, before 行, 新增行)`` 三元组。

        三者都剥掉前缀字符并**保留原缩进**：
        - after = 上下文行（" "）+ 新增行（"+"）≈ 打补丁后的 hunk 切片；
        - before = 上下文行（" "）+ 删除行（"-"）≈ 打补丁前的 hunk 切片；
        - added = 仅新增行（"+"）。

        保留上下文行是 G 轮实效化的关键：只看 "+" 行会把 hunk 的结构信息
        （外层 ``def``/``class``、多行表达式的开括号、``from os import system
        as s`` 这类别名声明）全部丢掉，拼接结果既解析不了、也解析不出别名。

        文件头（``diff --git`` / ``index`` / ``--- `` / ``+++ ``）出现在首个
        ``@@`` 之前，故按"未进入 hunk"跳过；``\\ No newline at end of file``
        标记跳过；hunk 内遇到非法前缀行（如下一份文件的 ``diff --git``）即
        收尾当前 hunk。LLM 输出常把空上下文行的 " " 前缀丢掉，此处按上下文
        行处理（空行不影响危险调用判定，但影响缩进结构）。
        """
        hunks: list[tuple[list[str], list[str], list[str]]] = []
        after: list[str] = []
        before: list[str] = []
        added: list[str] = []
        in_hunk = False

        def _flush() -> None:
            if after or before or added:
                hunks.append((after.copy(), before.copy(), added.copy()))
            after.clear()
            before.clear()
            added.clear()

        for line in patch_text.splitlines():
            if line.startswith("@@"):
                if in_hunk:
                    _flush()
                in_hunk = True
                continue
            if not in_hunk:
                continue
            if line.startswith("\\"):
                continue
            if line.startswith("+"):
                after.append(line[1:])
                added.append(line[1:])
            elif line.startswith("-"):
                before.append(line[1:])
            elif line.startswith(" ") or not line.strip():
                body = line[1:] if line.startswith(" ") else ""
                after.append(body)
                before.append(body)
            else:
                _flush()
                in_hunk = False
        if in_hunk:
            _flush()
        return hunks

    @classmethod
    def _llm_patch_dangerous_calls(cls, patch_text: str) -> tuple[set[str], int]:
        """C5：扫描 unified diff 各 hunk，收集**补丁新引入**的危险调用特征。

        逐 hunk 三口径合并（G 轮实效化）：
        1. after 切片扫描 − before 切片扫描 = 差集，即"新引入"（与本地链路
           ``patch_applier.dangerous_api_added`` 的 before/after 差集同口径，
           上下文行里既有的危险调用不误判为新增）；
        2. ∪ 仅 "+" 行的扫描结果——集合差有**遮蔽盲区**：上下文里既有同名
           特征（如既有 os.system 调用）会把新增的同特征调用一并减掉；
           "+"-only 只可能命中真正新增的行，无遮蔽，故取并集；
        3. 扫描本身走 :func:`collect_dangerous_calls_in_fragment`（三级降级
           解析：整段 dedent → ``if True:`` 套件 → 逐行累积），并把无法解析
           的残行数如实上报。

        Returns:
            ``(命中的危险特征集, 无法解析的残行数)``。两者任一非零，调用方都
            必须拒绝应用补丁（fail-closed）：残行数 > 0 意味着该 hunk 未被
            完整静态审查，此时空特征集只表示"读不懂"而非"安全"。
        """
        from src.tools.patch_applier import collect_dangerous_calls_in_fragment

        found: set[str] = set()
        residue = 0
        for after_lines, before_lines, added_lines in cls._split_diff_hunks(patch_text):
            after_found, after_residue = collect_dangerous_calls_in_fragment(after_lines)
            residue += after_residue
            before_found, _ = collect_dangerous_calls_in_fragment(before_lines)
            found |= after_found - before_found
            plus_found, _ = collect_dangerous_calls_in_fragment(added_lines)
            found |= plus_found
        return found, residue

    @classmethod
    def _patch_touches_test_files(cls, patch_text: str) -> str | None:
        """解析 unified diff 目标路径，命中测试文件即返回路径（否则 None）。"""
        for m in re.finditer(
            r"^\+\+\+ [^/]*(\S+)|^--- [^/]*(\S+)|^diff --git a/(\S+) b/(\S+)", patch_text, re.MULTILINE
        ):
            paths = [p for p in m.groups() if p]
            for p in paths:
                if p in ("/dev/null", "/dev/zero"):
                    continue
                # 统一 b/<p> / a/<p> 前缀
                norm = p[2:] if p[:2] in ("a/", "b/") else p
                if cls._TEST_PATH_RE.search(norm):
                    return norm
        return None

    @staticmethod
    def _looks_like_unified_diff(patch_text: str) -> bool:
        """N08（2026-10-22 第三方复审 P2）：识别 unified diff 的三种合法开头。

        历史判据只认 "diff --git" 或 "@@"，于是标准单文件 diff
        （``--- a/pkg.py`` / ``+++ b/pkg.py`` / ``@@``）被当成"完整源码"拒绝，
        合法修复被记 llm_patch_applied=False，实际验证的是未修复版本。

        判据要求 ``--- `` 与 ``+++ `` **相邻成对**出现（标准 diff 文件头），
        避免把 Python 注释 / docstring 里的单行误判为补丁。
        """
        text = (patch_text or "").lstrip()
        if text.startswith(("diff --git", "@@")):
            return True
        lines = text.splitlines()
        for i in range(min(len(lines) - 1, 4)):
            if lines[i].startswith("--- ") and lines[i + 1].startswith("+++ "):
                return True
        return False

    @staticmethod
    def _normalize_unified_headers(patch_text: str) -> str:
        """给 ``---`` / ``+++`` 文件头的裸路径补 ``a/`` / ``b/`` 前缀。

        git apply 默认 ``-p1``：``--- src/pkg.py`` 会被剥掉首段路径后找不到
        文件，补丁必然被拒。difflib 回退产出的正是这种裸路径（N08 同根因），
        因此识别放宽后**必须同时规范化路径**才算闭环。

        - 已带 a/ b/ 前缀的行原样保留（逐字不变，避免二次加前缀）；
        - ``/dev/null``（新增/删除文件）不加前缀；
        - 只改文件头两行，hunk 正文（可能以 --- 开头的内容行）不动。
        """
        lines = (patch_text or "").splitlines()
        out: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            # 只把**相邻成对**的 ---/+++ 当文件头（标准 unified diff 文件头）。
            # 逐行匹配会把 hunk 内以 "--- " 开头的删除行误当文件头改写。
            if line.startswith("--- ") and nxt.startswith("+++ "):
                out.append(RepoExecutor._prefix_header_path(line, "a/"))
                out.append(RepoExecutor._prefix_header_path(nxt, "b/"))
                i += 2
                continue
            out.append(line)
            i += 1
        return "\n".join(out) + ("\n" if patch_text.endswith("\n") else "")

    @staticmethod
    def _prefix_header_path(line: str, prefix: str) -> str:
        """给单行文件头补前缀；已带前缀 / /dev/null 原样返回。"""
        marker, _, path = line.partition(" ")
        path = path.strip()
        if not path or path in ("/dev/null", "/dev/zero") or path.startswith(("a/", "b/")):
            return line
        return f"{marker} {prefix}{path}"

    def _apply_llm_patch(self, repo_dir: str, llm_patch: str) -> bool:
        """把 LLM 补丁应用到仓库工作区。

        LLM 补丁两种形态（与 patch_applier 同口径）：
        1. unified diff（含 "diff --git" / "--- " / "+++" 行）→
           _apply_patch_robust（git apply + new-file 兜底回填）；
        2. 非 unified diff（LLM 重写目标模块的完整文件代码）→ 无法映射到
           仓库内真实路径（LLM 写的是 sqlfluff_XXXX.py 而非仓库真实文件），
           此时保守返回 False（验证按基线 FAIL_TO_PASS 实测，不误判通过）。
        返回是否成功应用（失败不阻断，验证按 FAIL_TO_PASS 实测判定）。
        """
        if not llm_patch or not llm_patch.strip():
            return False
        stripped = llm_patch.lstrip()
        # LLM 补丁 unified diff 判定（N08）："diff --git"（git diff 输出）、
        # 以 hunk 头 "@@" 开头（纯 unified diff，无文件头），或标准文件头
        # "--- <path>" + "+++ <path>" 成对开头（git diff --no-index / difflib
        # 的常规产物）。完整文件代码（Python 源码）不以这些开头，落入 else
        # 分支保守处理。
        if not self._looks_like_unified_diff(stripped):
            # 完整文件代码形态：LLM 写的是"任务模块名.py"（如 sqlfluff_4764.py），
            # 与仓库内真实文件路径（src/sqlfluff/cli/commands.py）对不上，
            # 无法直接应用 → 保守 False（FAIL_TO_PASS 实测裁决，不误判）
            logger.info("LLM 补丁为非 unified diff 形态（完整文件代码），仓库级无法映射路径，按无补丁实测")
            return False
        # N08：裸路径（无 a/ b/ 前缀）在 git apply -p1 下必然找不到文件。
        # 识别放宽后同步规范化文件头，否则"识别通过但应用仍被拒"，等于没修。
        llm_patch = self._normalize_unified_headers(llm_patch)
        # M2（2026-09-29 审查 P0）：测试文件保护。解析 unified diff 的所有
        # 目标路径（`+++ b/<p>` / `--- a/<p>` / `diff --git a/<p> b/<p>`），
        # 若命中测试目录（tests/ / testing/ / test_*.py / *_test.py / conftest.py）
        # 即拒绝应用——LLM 改 gold 测试让 F2P"全过"是典型假修复通道
        # （_apply_llm_patch 在 test_patch 之后应用，无路径过滤时可改写
        # gold 测试文件）。保守拒绝，FAIL_TO_PASS 实测裁决。
        touched_test_file = self._patch_touches_test_files(llm_patch)
        if touched_test_file:
            logger.info(
                "M2 测试文件保护：LLM 补丁触碰测试文件 %s，拒绝应用（防改 gold 测试让 F2P 假过）",
                touched_test_file,
            )
            return False
        # C5（2026-10-05 系统审查 P0·X 批次落地；2026-10-16 G 轮实效化）：
        # 危险 API 静态守卫。背景：本地链路（patch_applier.safe_apply_patch）
        # 有 AST 级危险调用差集守卫（os.system / subprocess / eval / 网络外连
        # / 凭证读取 / 动态构造绕过，C4 起含 from-import 别名图），但 repo 级
        # 链路的 unified diff 此前**直接 git apply 后在宿主/venv 裸跑**——同一
        # 守卫口径的缺口。X 批次从补丁 "+" 行（新增代码，新增即"新引入"，
        # 无需与原代码做差集）提取伪模块跑同一收集器，命中即拒绝应用（与 M2
        # 测试文件保护同口径：FAIL_TO_PASS 实测裁决，不误判通过）。
        #
        # G 轮实测缺陷（已修）：X 批次把 "+" 行原样拼接后交给
        # _collect_dangerous_calls，而该函数语法失败返回空集。最常见的补丁形态
        # 是"往既有函数体里插一行"——外层 def/class 是上下文行（不参与拼接），
        # "+" 行以缩进开头，拼接后必抛 IndentationError → 空集 → 守卫放行，
        # 即 X 批次的 C5 对主流形态**全盲**。现改为逐 hunk 重建 after/before
        # 切片（保留上下文行，结构完整可解析）跑三级降级扫描，取差集 ∪ "+"-only
        # （差集有"既有同名特征遮蔽新增"的盲区，故并集）；并按 G 轮 fail-closed
        # 决策：残行数 > 0（hunk 未被完整静态审查）同样拒绝应用——"读不懂"
        # 不等于"安全"。日志只记特征名与残行数，不回显补丁内容（补丁可能含
        # 凭证/PII）。
        _dangerous, _unparsed = self._llm_patch_dangerous_calls(llm_patch)
        if _dangerous:
            logger.warning(
                "C5 危险 API 守卫：LLM 补丁新增行命中危险调用 %s，拒绝应用（FAIL_TO_PASS 按无补丁实测）",
                sorted(_dangerous),
            )
            return False
        if _unparsed:
            logger.warning(
                "C5 危险 API 守卫：LLM 补丁新增行有 %d 行无法静态解析，按 fail-closed 拒绝应用"
                "（FAIL_TO_PASS 按无补丁实测）",
                _unparsed,
            )
            return False
        # 临时补丁文件按 (pid, thread) 隔离——2026-09-26 全面审查 P1 并发安全：
        # --parallel 下多线程共享同一进程（同 pid、同 tempfile.gettempdir()），
        # 固定文件名（或仅 pid 后缀）会让一个线程的 finally: os.remove 删掉
        # 另一个线程正在 git apply 的补丁文件。pid+thread ident 双键在
        # ThreadPoolExecutor 场景下保证每线程独立文件，跨进程由 pid 隔离。
        patch_file = os.path.join(
            tempfile.gettempdir(),
            f"aitester_llm_unified_{os.getpid()}_{threading.get_ident()}.patch",
        )
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(llm_patch)
        try:
            res = _run(["git", "apply", "--check", patch_file], repo_dir, 60)
            if res.returncode != 0:
                logger.info(
                    "LLM 补丁 --check 拒绝（上下文与当前源码不一致），按无补丁实测: %s",
                    res.stderr.strip()[:200],
                )
                return False
            self._apply_patch_robust(repo_dir, patch_file)
            return True
        finally:
            os.remove(patch_file)

    # ── unified diff 解析（new-file 手动写入兜底）──────────────────────────

    @staticmethod
    def parse_new_file_bodies(patch_text: str) -> dict[str, str]:
        """解析 unified diff，提取所有 new-file（--- /dev/null）目标文件的内容。

        仅处理 new-file hunk（`--- /dev/null` → `+++ b/<path>`）：把该 section
        内全部 `+` 行拼接为目标文件完整内容（new-file 的每行均为 `+` 前缀，
        无 context 行，拼接结果即文件全文）。**修改已有文件**的 section
        （`--- a/<path>`，非 /dev/null）明确排除——其 `+` 行只是被改的行，
        缺 context 行，拼接结果不是完整文件，回填会破坏目标文件。

        Returns:
            {目标文件相对路径: 文件内容}；无 new-file section 时返回空 dict。
        """
        result: dict[str, str] = {}
        current_file: str | None = None
        current_is_new: bool = False
        lines: list[str] = []

        def _flush() -> None:
            nonlocal current_file, current_is_new, lines
            if current_file is not None and current_is_new:
                result[current_file] = "\n".join(lines) + ("\n" if lines else "")
            current_file = None
            current_is_new = False
            lines = []

        for raw in patch_text.splitlines():
            if raw.startswith("diff --git "):
                _flush()
                continue
            if raw.startswith(("new file mode", "index ")):
                continue
            if raw.startswith("--- "):
                # 当前 section 的源端：/dev/null 即 new-file，其余是修改
                current_is_new = "/dev/null" in raw
                current_file = None  # 源端行重置目标端（等待 +++ 行设定路径）
                continue
            if raw.startswith("+++ "):
                # 目标端路径（b/ 前缀为 git 惯例，无前缀为裸路径）。
                # new-file section 的 +++ 行必须沿用紧邻的 --- /dev/null
                # 标记；修改 section 的 +++ 行 current_is_new 已为 False。
                # 路径重置 current_file/lines（上一 section 由 _flush 收尾，
                # 此处仅设定本 section 目标，不重复 flush）。
                path = raw[4:]
                path = path.removeprefix("b/")
                current_file = path
                lines = []
                continue
            if current_file is not None and current_is_new and raw.startswith("+"):
                lines.append(raw[1:])
                # new-file section 无 context/- 行；修改 section 整体跳过
                # （不写 result）
        _flush()
        return result

    def _apply_patch_robust(self, repo_dir: str, patch_file: str) -> None:
        """git apply + new-file 空产出兜底（manual write 回填）。

        先 git apply（修改已有文件场景正常工作），再检测 new-file 目标：
        若文件为空或不存在，用 parse_new_file_bodies 提取的内容手动写入。
        兜底确保即使 git apply 的 new-file 路径损坏，测试文件仍有内容。
        注意：git apply rc!=0 也执行兜底解析——合法补丁的 --check 通过即
        意味着 hunk 可解析（_apply_patch_robust 的调用方已用 --check 预判，
        本函数直接应用 + 兜底，不再重复 check）。
        """
        res = _run(["git", "apply", "--whitespace=nowarn", patch_file], repo_dir, 60)
        if res.returncode != 0:
            logger.warning("git apply 失败 (rc=%d): %s", res.returncode, res.stderr.strip()[:200])
        # 兜底：new-file hunk 可能因 Apple Git 2.54 bug 产出空文件
        with open(patch_file, encoding="utf-8") as f:
            patch_text = f.read()
        new_files = self.parse_new_file_bodies(patch_text)
        for rel_path, content in new_files.items():
            # S6（2026-09-29 审查 P0 + 2026-10-02 修复）：补丁路径越界写防护。
            # rel_path 取自补丁 `+++ b/<path>`（LLM / 上游数据可控），
            # 绝对路径或 `../` 序列可使 os.path.join 逃出 repo_dir
            # （如 `+++ b/../../.ssh/authorized_keys`）。realpath 归一化后
            # 必须仍位于 repo_dir 内，否则拒绝该 hunk 的兜底写入
            # （git apply 自身的路径校验不受影响，本防护仅约束手动回填）。
            if os.path.isabs(rel_path):
                logger.warning("拒绝越界补丁路径（绝对路径）: %r", rel_path)
                continue
            target = os.path.realpath(os.path.join(repo_dir, rel_path))
            repo_root = os.path.realpath(repo_dir)
            if not (target == repo_root or target.startswith(repo_root.rstrip(os.sep) + os.sep)):
                logger.warning("拒绝越界补丁路径: %r（解析为 %s，超出仓库根）", rel_path, target)
                continue
            existing = ""
            if os.path.isfile(target):
                with open(target, encoding="utf-8") as f:
                    existing = f.read()
            if existing != content:
                os.makedirs(os.path.dirname(target) or repo_dir, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("new-file 兜底写入: %s (%d chars)", rel_path, len(content))
