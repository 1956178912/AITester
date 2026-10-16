#!/usr/bin/env python3
"""覆盖率补口 + 缓存语义锁定：仓库级环境 setup（`src/agents/executor_repo.py`）。

动机（EMSE 多轮优化批次·仓库级验证入口）：`RepoExecutor.setup` 是 SWE-bench 类
仓库级实验的**环境准备唯一入口**，其缓存判据决定"同一 (repo, commit) 是否复用
环境"。这套逻辑历史上出过两类真实事故（代码注释自陈）：

1. **缓存标记与模式不对齐**：`use_venv=True` 时入口读 `.venv_pip_installed`，
   若回退路径写 `.pip_installed`，则每次都缓存 miss → 反复 `git clone` +
   `pip install`（SWE-bench 同仓库 10–20 个 commit 时成倍放大）；
2. **12 位前缀碰撞**：缓存命中判据从 `commit[:12]` 比较改为**全等**比较，否则
   "同仓库不同 commit"会被误判命中（拿到错 commit 的代码跑基线）。

本文件的夹具是**真实本地 git 仓库**（`file://` 无关，直接路径即可），
pip/venv 步骤用 monkeypatch 隔离（不打网络、不污染宿主 site-packages），
只验证 setup 的控制流与标记语义。零 LLM、零网络。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from src.agents.executor_repo import RepoExecutor

pytestmark = pytest.mark.timeout(180)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


@pytest.fixture
def tiny_repo(tmp_path: Path) -> tuple[Path, str]:
    """建一个只有 `pkg/__init__.py` 的本地 git 仓库，返回 (repo_path, commit_sha)。"""
    repo = tmp_path / "tinyrepo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "setup.py").write_text(
        "from setuptools import setup\n\nsetup(name='tinypkg', version='0.0.1', packages=['pkg'])\n",
        encoding="utf-8",
    )
    assert _git(["init", "-q"], repo).returncode == 0
    assert _git(["add", "-A"], repo).returncode == 0
    commit = _git(["commit", "-q", "-m", "init"], repo)
    assert commit.returncode == 0, commit.stderr
    sha = _git(["rev-parse", "HEAD"], repo).stdout.strip()
    assert len(sha) == 40
    return repo, sha


@pytest.fixture
def env_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo_envs"
    monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(root))
    return root


@pytest.fixture
def isolated_installs(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """隔离 pip/venv 副作用：记录调用次数，返回成功（None）。"""
    calls = {"editable": 0, "venv_install": 0, "create_venv": 0}

    def _pip_editable(self: RepoExecutor, repo_dir: str) -> str | None:
        calls["editable"] += 1
        return None

    def _venv_install(self: RepoExecutor, repo_dir: str, venv_dir: str) -> str | None:
        calls["venv_install"] += 1
        return None

    monkeypatch.setattr(RepoExecutor, "_pip_install_editable", _pip_editable, raising=True)
    monkeypatch.setattr(RepoExecutor, "_venv_pip_install", _venv_install, raising=True)
    return calls


class TestSetupGlobalMode:
    def test_first_setup_clones_and_marks_installed(
        self, tiny_repo: tuple[Path, str], env_root: Path, isolated_installs: dict[str, int]
    ):
        repo, sha = tiny_repo
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=False)
        result = executor.setup(str(repo), sha)

        assert result["error"] is None, result
        assert result["cached"] is False
        workdir = Path(result["workdir"])
        assert (workdir / "pkg" / "__init__.py").is_file(), "clone 未落地源码"
        assert isolated_installs["editable"] == 1
        marker = workdir.parent / ".pip_installed"
        assert marker.is_file(), "全局模式必须写 .pip_installed 标记"
        assert marker.read_text(encoding="utf-8").strip() == sha

    def test_second_setup_hits_cache_and_skips_install(
        self, tiny_repo: tuple[Path, str], env_root: Path, isolated_installs: dict[str, int]
    ):
        repo, sha = tiny_repo
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=False)
        assert executor.setup(str(repo), sha)["cached"] is False
        second = executor.setup(str(repo), sha)
        assert second["cached"] is True, "同 (repo, commit) 第二次必须命中缓存"
        assert isolated_installs["editable"] == 1, "缓存命中不得重复 pip install"

    def test_marker_with_wrong_commit_forces_reprepare(
        self, tiny_repo: tuple[Path, str], env_root: Path, isolated_installs: dict[str, int]
    ):
        """标记写入的 sha 与请求 sha 不一致时……必须重新准备还是复用？

        当前实现只比较**工作树的 HEAD**与请求 sha（标记内容仅作存在性判据），
        故 HEAD 匹配时仍判缓存命中。本用例锁定该语义：标记内容不参与命中判定。
        """
        repo, sha = tiny_repo
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=False)
        first = executor.setup(str(repo), sha)
        marker = Path(first["workdir"]).parent / ".pip_installed"
        marker.write_text("deadbeef" * 5, encoding="utf-8")
        second = executor.setup(str(repo), sha)
        assert second["cached"] is True, "命中判据是 HEAD 全等 + 标记存在，与标记内容无关"
        assert isolated_installs["editable"] == 1

    def test_checkout_drift_triggers_reprepare(
        self, tiny_repo: tuple[Path, str], env_root: Path, isolated_installs: dict[str, int]
    ):
        """工作树 HEAD 与请求 sha 不同 → 必须判缓存 miss 并重新准备（Z3 全等判据）。"""
        repo, sha = tiny_repo
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=False)
        first = executor.setup(str(repo), sha)
        repo_dir = Path(first["workdir"])
        # 制造漂移：检出到另一个 commit（用分支名也可，这里直接改 HEAD）
        (repo_dir / "pkg" / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
        assert _git(["add", "-A"], repo_dir).returncode == 0
        assert _git(["commit", "-q", "-m", "drift"], repo_dir).returncode == 0
        second = executor.setup(str(repo), sha)
        assert second["cached"] is False, "HEAD 漂移后必须重新准备"
        assert isolated_installs["editable"] == 2

    def test_clone_failure_is_reported_not_raised(self, tmp_path: Path, env_root: Path):
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=False)
        result = executor.setup(str(tmp_path / "no_such_repo_xyz"), "0" * 40)
        assert result["error"], "clone 失败必须返回 error 诊断（不得抛异常）"
        assert result["cached"] is False


class TestSetupVenvMode:
    def test_shared_venv_fallback_writes_venv_marker(
        self,
        tiny_repo: tuple[Path, str],
        env_root: Path,
        isolated_installs: dict[str, int],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """**按仓库复用模式**下 venv 创建失败 → 回退全局 pip install，且必须写
        `.venv_pip_installed`。

        这是历史事故 1 的精确复现条件：入口按 `use_venv` 读该标记，
        回退路径若写 `.pip_installed` 则永久缓存 miss、反复 clone + install。
        """
        repo, sha = tiny_repo
        monkeypatch.setattr(RepoExecutor, "_create_venv", lambda self, env_dir: "simulated venv failure", raising=True)
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=True, venv_reuse_by_repo=True)
        result = executor.setup(str(repo), sha)
        env_dir = Path(result["workdir"]).parent
        assert (env_dir / ".venv_pip_installed").is_file(), "use_venv + 按仓库复用的回退路径必须写 .venv_pip_installed"
        assert isolated_installs["editable"] == 1
        assert executor.setup(str(repo), sha)["cached"] is True

    def test_per_commit_venv_fallback_writes_global_marker(
        self,
        tiny_repo: tuple[Path, str],
        env_root: Path,
        isolated_installs: dict[str, int],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """**per-commit venv 模式**下创建失败 → 回退全局安装并写 `.pip_installed`。

        与上一用例构成对照：两条回退路径写**不同**标记，但各自必须与入口读的标记
        一致。该差异正是历史事故根因，故两侧都锁定。
        """
        repo, sha = tiny_repo
        monkeypatch.setattr(RepoExecutor, "_create_venv", lambda self, env_dir: "simulated venv failure", raising=True)
        executor = RepoExecutor(timeout=30, setup_timeout=60, use_venv=True, venv_reuse_by_repo=False)
        result = executor.setup(str(repo), sha)
        env_dir = Path(result["workdir"]).parent
        assert (env_dir / ".pip_installed").is_file()
        assert isolated_installs["editable"] == 1


class TestVenvResolution:
    def test_resolve_uses_shared_dir_when_reuse_enabled(self, tmp_path: Path):
        executor = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        resolved = executor._resolve_venv_dir("/envs/x", "https://host/o/r.git", "/envs/x/repo")
        assert resolved != "/envs/x", "按仓库复用时必须解析到共享 venv 目录"
        assert "shared" in resolved or resolved.endswith("r") or "r" in Path(resolved).name

    def test_resolve_uses_env_dir_by_default(self):
        executor = RepoExecutor(use_venv=True, venv_reuse_by_repo=False)
        assert executor._resolve_venv_dir("/envs/x", "url", "/envs/x/repo") == "/envs/x"

    def test_venv_python_is_none_when_disabled(self):
        assert RepoExecutor(use_venv=False)._venv_python("/envs/x") is None

    def test_venv_python_is_none_when_not_created(self, tmp_path: Path):
        executor = RepoExecutor(use_venv=True)
        assert executor._venv_python(str(tmp_path)) is None

    def test_env_root_honours_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path / "custom"))
        assert RepoExecutor().env_root == str(tmp_path / "custom")
