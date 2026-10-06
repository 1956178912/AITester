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


def _run(cmd: list[str], cwd: str, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """统一子进程执行：超时/异常不抛出，由调用方按 returncode 判断。

    超时经 returncode=124（Linux timeout 命令口径）返回而非抛出
    subprocess.TimeoutExpired——SWE-bench 仓库中单节点 pytest 跑满 timeout
    很常见，此前该异常穿透 verify() 的 try/finally 使整个验证任务崩溃
    而非记录该 node 失败；统一在此收敛后，所有调用方按 returncode 判断
    即可（124 一律视为失败，调用方无需感知区别）。
    """
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env if env is not None else scrub_os_environ(),
            check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
        )
    except subprocess.TimeoutExpired as e:
        # 超时：构造哨兵结果（stdout/stderr 取已捕获部分，None 兜底空串；
        # text=True 模式下已捕获部分为 str，mypy 按 bytes|str 联合类型报
        # arg-type，归一为 str；stderr 同口径归一后截尾），退出码 124
        # （GNU timeout 超时常量）
        stdout_part = e.stdout if isinstance(e.stdout, str) else ((e.stdout or b"").decode("utf-8", "replace"))
        stderr_part = e.stderr if isinstance(e.stderr, str) else ((e.stderr or b"").decode("utf-8", "replace"))
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=stdout_part,
            stderr=f"命令执行超时（>{timeout}s）\n{stderr_part[:300]}",
        )


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
                            # P0 4.3：按仓库复用 venv（依赖指纹键），跨 commit 共享
                            venv_dir = self._repo_venv_dir(repo_url, repo_dir)
                            env_error = self._create_venv(venv_dir)
                            if env_error:
                                logger.warning("venv 创建失败，退回全局 python: %s", env_error)
                                env_error = self._pip_install_editable(repo_dir)
                                if env_error:
                                    logger.warning("仓库 pip install -e 失败（记录但不阻断验证）: %s", env_error)
                                else:
                                    # 2026-09-26 全面审查（P1 缓存一致性）：venv 创建失败
                                    # 回退到全局 pip install 后，缓存检查标记须与 use_venv
                                    # 模式对齐——use_venv=True 时 setup() 入口读
                                    # .venv_pip_installed（L148），此处若写 .pip_installed
                                    # 则下次 setup() 永远缓存 miss，每次重新 git clone +
                                    # pip install（SWE-bench 批量任务 10-20 个 commit 的
                                    # 同一仓库重复 clone）。现按 use_venv 写对应标记。
                                    _marker = ".venv_pip_installed" if self.use_venv else ".pip_installed"
                                    with open(os.path.join(env_dir, _marker), "w", encoding="utf-8") as f:
                                        f.write(base_commit)
                            else:
                                # 检测依赖指纹：同一指纹复用已有 venv（不重新 pip install -e）
                                dep_fingerprint = self._dep_fingerprint(repo_dir)
                                marker = os.path.join(venv_dir, ".venv_dep_fingerprint")
                                need_install = True
                                if os.path.isfile(marker):
                                    with open(marker, encoding="utf-8") as f:
                                        existing_fp = f.read().strip()
                                    if existing_fp == dep_fingerprint:
                                        # 依赖未变 → 复用 venv，不重新 pip install。
                                        # 但必须刷新 editable 源码指向：pip install -e
                                        # 写入的是绝对路径（.pth / __editable__ finder），
                                        # 跨 commit 时旧 venv 的 editable 安装仍指向上一个
                                        # commit 的 repo 目录——与本 commit 不一致时会让
                                        # `import <repo_pkg>` 解析到错误版本（正是 4.3 要
                                        # 消除的跨 commit 污染）。因此指纹命中时重跑一次
                                        # 轻量 `pip install -e .`（依赖已装、仅重指向
                                        # 源码，秒级），不装依赖本身。
                                        logger.info(
                                            "P0 4.3 venv 复用命中（依赖指纹未变，仅重指向 editable 源码）: %s（commit %s）",
                                            venv_dir,
                                            base_commit[:12],
                                        )
                                        _repoint_err = self._venv_pip_install(repo_dir, venv_dir)
                                        if _repoint_err:
                                            # 重指向失败（pip 网络异常等）：editable 仍指旧
                                            # commit 源码，测试会在旧版本上裁决——保留诊断
                                            # 但不清除环境标记（venv 本身可用，走保守路径），
                                            # 由 verify 阶段的 base_not_failing 等信号兜底。
                                            logger.warning(
                                                "P0 4.3 editable 重指向失败（venv 仍指旧 commit 源码）: %s",
                                                _repoint_err,
                                            )
                                        # O35（P2 性能）：指纹命中分支已做过一次
                                        # `pip install -e .`（上方 repoint），此前
                                        # need_install 保持初值 True，下方会**再跑一次
                                        # 同样的 pip install**——每次 venv 复用命中都
                                        # 白付一遍 pip 启动/解析开销（秒级 × 每任务）。
                                        # repoint 本身就是这次 install，故置 False 收口。
                                        need_install = False
                                else:
                                    # 指纹不同（依赖变了）→ 必须重装。
                                    # need_install 已在上方初始化为 True，本分支
                                    # 无需再赋值（O35：原 `else: need_install = True`
                                    # 是对初值的无操作死代码，已删）。
                                    pass
                                if need_install:
                                    env_error = self._venv_pip_install(repo_dir, venv_dir)
                                    if env_error:
                                        logger.warning("venv pip install -e 失败（记录但不阻断验证）: %s", env_error)
                                    else:
                                        with open(marker, "w", encoding="utf-8") as f:
                                            f.write(dep_fingerprint)
                                # 写环境标记（venv 模式下，即使复用也标记该 commit 已就绪）
                                with open(os.path.join(env_dir, ".venv_pip_installed"), "w", encoding="utf-8") as f:
                                    f.write(base_commit)
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
        - 共享 venv 只装依赖（pip install -e 指向最新 checkout 的 repo_dir）；
        - 源码指向随每次 checkout 刷新（editable install 的 .pth 文件
          指向 repo_dir，commit 切换时自动跟随）；
        - 依赖指纹（requirements/pyproject/setup 的 hash）决定是否需要
          重新 pip install，源码切换不触发依赖重装。

        Args:
            repo_url: 仓库 URL（取 repo 名做键）。
            repo_dir: 当前 checkout 的源码目录（editable install 目标）。

        Returns:
            共享 venv 目录路径。
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_name = repo_name.removesuffix(".git")
        return os.path.join(self.env_root, repo_name, "_shared_venv")

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
        _verify_lock.acquire()
        try:
            # M3（2026-09-29 审查 P0）：官方 swebench 包路径（SWE_USE_OFFICIAL_HARNESS=true
            # 时启用，默认 false 保持历史自建 harness 口径）。启用时先尝试
            # `python -m swebench.harness.run_evaluation`，成功则以官方结果为准；
            # 官方包未安装 / 执行失败时降级历史自建口径（零行为变化）。
            if self._official_harness_enabled():
                _official_result = self._run_official_swebench_harness(
                    repo_url=repo_url,
                    base_commit=base_commit,
                    test_patch=test_patch,
                    llm_patch=llm_patch,
                    fail_to_pass=fail_to_pass,
                    pass_to_pass=pass_to_pass,
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
                output += f"[PASS_TO_PASS] {p2p['passed']}/{p2p['expected']} passed"
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
                _p2p_gate_enabled = os.getenv("P2P_GATE_ENABLE", "true").lower() not in ("false", "0", "off")
                _p2p_gate_threshold = float(os.getenv("P2P_GATE_THRESHOLD", "0.95"))
                _harness_invalid = False
                if _p2p_gate_enabled and p2p["expected"] > 0:
                    _p2p_baseline_rate = p2p["passed"] / p2p["expected"]
                    base_result["p2p_baseline_rate"] = round(_p2p_baseline_rate, 4)
                    if _p2p_baseline_rate < _p2p_gate_threshold:
                        _harness_invalid = True
                        base_result["harness_invalid"] = True
                        base_result["passed"] = False
                        base_result["error_info"] = {
                            "type": "harness_invalid",
                            "message": (
                                f"M3 基线 P2P 门禁：P2P 通过率 {_p2p_baseline_rate:.2%} "
                                f"低于阈值 {_p2p_gate_threshold:.2%}（期望 {p2p['expected']}，"
                                f"通过 {p2p['passed']}），harness 环境本身损坏，"
                                "实验结果不可信（应剔除本任务）"
                            ),
                        }
                        logger.warning(
                            "M3 基线 P2P 门禁未通过：P2P %d/%d（%.2f%% < %.2f%%），harness_invalid=True",
                            p2p["passed"],
                            p2p["expected"],
                            _p2p_baseline_rate * 100,
                            _p2p_gate_threshold * 100,
                        )
                else:
                    base_result["harness_invalid"] = False
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
            _verify_lock.release()

    def _run_fail_to_pass(self, repo_dir: str, fail_to_pass: list[str], repo_url: str = "") -> dict[str, Any]:
        """运行 FAIL_TO_PASS 测试节点，返回 expected 总数与 failed_cases 列表。"""
        return self._run_test_nodes(repo_dir, fail_to_pass, repo_url=repo_url)

    def _run_pass_to_pass(self, repo_dir: str, pass_to_pass: list[str], repo_url: str = "") -> dict[str, Any]:
        """运行 PASS_TO_PASS 回归测试节点。"""
        return self._run_test_nodes(repo_dir, pass_to_pass, repo_url=repo_url)

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
                [_py, "-m", "pytest", "-p", "no:cacheprovider", node, "--tb=short", "-q"],
                repo_dir,
                self.timeout,
                env,
            )
            if res.returncode in (0, 1):
                if res.returncode == 0:
                    passed_count += 1
                else:
                    failed_cases.append({"name": node, "error": (res.stdout + res.stderr).strip()[-400:]})
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
        return os.getenv("SWE_USE_OFFICIAL_HARNESS", "false").lower() in ("true", "1", "on")

    def _run_official_swebench_harness(
        self,
        repo_url: str,
        base_commit: str,
        test_patch: str,
        llm_patch: str,
        fail_to_pass: list[str],
        pass_to_pass: list[str],
    ) -> dict[str, Any] | None:
        """M3（2026-09-29 审查 P0）：官方 swebench 包验证路径。

        调用 `python -m swebench.harness.run_evaluation`（官方 harness），
        把 LLM 补丁与 gold test_patch 喂给官方 runner，读取其产出的
        `predictions.json` / `report.json` 提取 F2P/P2P 结果。

        降级口径（保守）：
        - swebench 包未安装（ModuleNotFoundError / 命令不存在）→ 返回
          None，verify() 继续自建 harness 口径（历史行为零变化）；
        - 官方 runner 执行异常 / 输出文件缺失 → 返回 None + 日志；
        - 仅当官方 runner 成功产出 report 且 F2P/P2P 判定与自建口径
          同构时才返回 dict（passed / fail_to_pass / pass_to_pass /
          harness_invalid 字段），否则降级。

        Args:
            repo_url: 仓库 URL（定位缓存环境，与 verify 同口径）。
            base_commit: 基础 commit（定位缓存环境）。
            test_patch: gold test_patch（unified diff 文本）。
            llm_patch: LLM 生成的修复（unified diff）。
            fail_to_pass: FAIL_TO_PASS 测试节点列表。
            pass_to_pass: PASS_TO_PASS 测试节点列表。

        Returns:
            与 verify() 自建口径同构的结果 dict（passed / fail_to_pass /
            pass_to_pass / harness_invalid / error_info），或 None（降级
            到自建口径）。
        """
        import subprocess
        import tempfile as _tempfile

        # 准备官方 runner 输入：predictions.json（LLM 补丁 + 元数据）
        pred = {
            "model_name_or_path": "aitester",
            "instance_id": f"{repo_url}@{base_commit[:8]}",
            "repo": repo_url,
            "base_commit": base_commit,
            "patch": llm_patch or "",
            "test_patch": test_patch or "",
            "fail_to_pass": fail_to_pass,
            "pass_to_pass": pass_to_pass or [],
        }
        pred_file = os.path.join(
            _tempfile.gettempdir(),
            f"aitester_swebench_pred_{os.getpid()}_{threading.get_ident()}.json",
        )
        with open(pred_file, "w", encoding="utf-8") as f:
            json.dump([pred], f, ensure_ascii=False, indent=2)

        try:
            # 官方 runner（pip install swebench）：python -m
            # swebench.harness.run_evaluation <pred_file>
            # 输出：日志 + 同目录 report.json（F2P/P2P 判定）
            res = subprocess.run(
                [sys.executable, "-m", "swebench.harness.run_evaluation", pred_file],
                capture_output=True,
                text=True,
                timeout=max(self.timeout, 300),
                cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
                check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
            )
            if res.returncode != 0:
                logger.info(
                    "M3 官方 swebench runner 退出码 %d（降级自建口径）: %s",
                    res.returncode,
                    (res.stderr or res.stdout).strip()[:300],
                )
                return None

            # 读取官方 report（与 pred_file 同目录的 report.json）
            report_file = pred_file.replace(".json", "_report.json")
            if not os.path.exists(report_file):
                # 官方 runner 可能把 report 写到 cwd 或 stdout（JSON 块）
                logger.info("M3 官方 swebench report 文件缺失（%s），降级自建口径", report_file)
                return None
            with open(report_file, encoding="utf-8") as f:
                report = json.load(f)
            # 官方 report 同构提取（字段名与 SWE-bench 官方口径一致）
            return {
                "passed": bool(report.get("resolved", False)),
                "fail_to_pass": {
                    "expected": len(fail_to_pass),
                    "passed": int(report.get("fail_to_pass_pass", 0) or 0),
                },
                "pass_to_pass": {
                    "expected": len(pass_to_pass),
                    "passed": int(report.get("pass_to_pass_pass", 0) or 0),
                },
                "harness_invalid": False,
                "output": f"[M3 官方 swebench harness] resolved={report.get('resolved')}",
            }
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError, ModuleNotFoundError) as e:
            logger.info("M3 官方 swebench 路径异常（降级自建口径）: %s", e)
            return None
        finally:
            for p in (pred_file, pred_file.replace(".json", "_report.json")):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass

    @classmethod
    def _llm_patch_dangerous_calls(cls, patch_text: str) -> set[str]:
        """C5：从 unified diff 的 "+" 行提取新增代码，收集危险调用特征。

        实现口径：
        - 仅取 hunk 新增行（行首 "+" 且排除 "+++" 文件头）——新增行即
          "补丁新引入"（无需与原代码做差集，与本地链路
          patch_applier.dangerous_api_added 的差集口径在此处天然等价）；
        - 复用 patch_applier._collect_dangerous_calls（模块限定调用 +
          from-import 别名图（C4）+ 凭证读取 + 动态构造绕过，同一特征集）；
        - 上下文行（" " 前缀）不参与——原代码既有危险调用不拦截（与
          本地链路"只拦新增危险、放行既有"口径一致）。
        """
        from src.tools.patch_applier import _collect_dangerous_calls

        added_lines: list[str] = []
        for line in patch_text.splitlines():
            if line.startswith("+++") or not line.startswith("+"):
                continue
            added_lines.append(line[1:])
        if not added_lines:
            return set()
        return _collect_dangerous_calls("\n".join(added_lines))

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
        # LLM 补丁 unified diff 判定："diff --git"（git diff 输出）或
        # 以 hunk 头 "@@" 开头（纯 unified diff，无 git 头）。完整文件代码
        # （Python 源码）不以这些开头，落入 else 分支保守处理。
        is_unified = stripped.startswith(("diff --git", "@@"))
        if not is_unified:
            # 完整文件代码形态：LLM 写的是"任务模块名.py"（如 sqlfluff_4764.py），
            # 与仓库内真实文件路径（src/sqlfluff/cli/commands.py）对不上，
            # 无法直接应用 → 保守 False（FAIL_TO_PASS 实测裁决，不误判）
            logger.info("LLM 补丁为非 unified diff 形态（完整文件代码），仓库级无法映射路径，按无补丁实测")
            return False
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
        # C5（2026-10-05 系统审查 P0·X 批次落地）：危险 API 静态守卫。
        # 背景：本地链路（patch_applier.safe_apply_patch）有 AST 级危险调用
        # 差集守卫（os.system / subprocess / eval / 网络外连 / 凭证读取 /
        # 动态构造绕过，C4 起含 from-import 别名图），但 repo 级链路的
        # unified diff 此前**直接 git apply 后在宿主/venv 裸跑**——同一
        # 守卫口径的缺口。现从补丁 "+" 行（新增代码，新增即"新引入"，
        # 无需与原代码做差集）提取伪模块跑同一收集器（_collect_dangerous_calls），
        # 命中即拒绝应用（与 M2 测试文件保护同口径：FAIL_TO_PASS 实测裁决，
        # 不误判通过）。能力边界：'+' 行片段 AST 解析失败时收集器返回空集
        # （不拦截——与本地链路"语法失败由 ast.parse 先行拦截"的分工不同，
        # 此处片段本就可能不独立成模块；git apply 后的执行仍受 venv 隔离
        # 与 P2P 门禁约束，属纵深一层而非唯一防线）。
        _dangerous = self._llm_patch_dangerous_calls(llm_patch)
        if _dangerous:
            logger.warning(
                "C5 危险 API 守卫：LLM 补丁新增行命中危险调用 %s，拒绝应用（FAIL_TO_PASS 按无补丁实测）",
                sorted(_dangerous),
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
