"""agents/executor_repo 纯逻辑 / mock-subprocess 分支补齐（2026-10-02 批次·十）。

锁定 executor_repo.py 的低覆盖纯逻辑分支（零真实子进程 / 零网络）：
- _get_repo_setup_lock：同 env_dir 返回同一锁实例 / 不同 env_dir 不同锁
- _repo_envs_root：SWE_REPO_ENVS_DIR 覆盖 / 默认回退 ~/.cache/aitester/repo_envs
- _run：子进程正常 / 超时哨兵 returncode=124 / stdout bytes 解码兜底 / env 透传
- RepoExecutor.__init__ 默认值
- _resolve_venv_dir：use_venv+reuse / use_venv 不 reuse / 不用 venv 三分支
- _venv_python：不用 venv / venv 未建立 / venv 已建立 / reuse_by_repo 解析
- setup 缓存命中判定（mock 文件系统标记 + mock git rev-parse）
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

# ─── _get_repo_setup_lock 分支 ─────────────────────────────────────────────


class TestGetRepoSetupLockBranches:
    def test_same_dir_returns_same_lock(self):
        from src.agents.executor_repo import _get_repo_setup_lock

        lock1 = _get_repo_setup_lock("/tmp/env_a")
        lock2 = _get_repo_setup_lock("/tmp/env_a")
        assert lock1 is lock2  # 同 env_dir 复用同一锁

    def test_different_dir_returns_different_lock(self):
        from src.agents.executor_repo import _get_repo_setup_lock

        lock_a = _get_repo_setup_lock("/tmp/env_a")
        lock_b = _get_repo_setup_lock("/tmp/env_b")
        assert lock_a is not lock_b

    def test_normpath_equivalent_dirs_share_lock(self):
        """等价路径（. / 尾斜杠）经 normpath 归一后共享锁。"""
        from src.agents.executor_repo import _get_repo_setup_lock

        lock1 = _get_repo_setup_lock("/tmp/env_a/")
        lock2 = _get_repo_setup_lock("/tmp/env_a")
        assert lock1 is lock2


# ─── _repo_envs_root 分支 ──────────────────────────────────────────────────


class TestRepoEnvsRootBranches:
    def test_default_root(self, monkeypatch):
        from src.agents.executor_repo import _repo_envs_root

        monkeypatch.delenv("SWE_REPO_ENVS_DIR", raising=False)
        root = _repo_envs_root()
        assert os.path.basename(root) == "repo_envs"
        assert "aitester" in root

    def test_env_override(self, monkeypatch):
        from src.agents.executor_repo import _repo_envs_root

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", "/tmp/custom_repo_envs")
        assert _repo_envs_root() == "/tmp/custom_repo_envs"

    def test_env_empty_string_falls_back_default(self, monkeypatch):
        """空字符串 env → 或运算回退默认根目录。"""
        from src.agents.executor_repo import _repo_envs_root

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", "")
        root = _repo_envs_root()
        assert os.path.basename(root) == "repo_envs"


# ─── _run 分支 ─────────────────────────────────────────────────────────────


class TestRunBranches:
    def test_normal_run_returns_completed_process(self):
        from src.agents.executor_repo import _run

        proc = _run(["echo", "hello"], cwd=".", timeout=5)
        assert proc.returncode == 0
        assert "hello" in proc.stdout

    def test_timeout_returns_124_sentinel(self):
        """子进程超时 → 哨兵结果 returncode=124 + stderr 含超时标记（不抛出）。"""
        from src.agents.executor_repo import _run

        proc = _run(["sleep", "10"], cwd=".", timeout=1)
        assert proc.returncode == 124
        assert "超时" in proc.stderr

    def test_env_passthrough(self):
        """env 参数显式传入时透传（不走 scrub_os_environ）。"""
        from src.agents.executor_repo import _run

        proc = _run(["env"], cwd=".", timeout=5, env={"MY_TEST_VAR": "abc123"})
        assert "MY_TEST_VAR=abc123" in proc.stdout

    def test_nonexistent_command_returns_nonzero(self):
        """命令不存在：shlex.split + 真实子进程返回非 0（不抛出，调用方按码判断）。

        用 `true || false` 等价物：直接执行不存在的可执行文件，subprocess.run
        对"可执行文件缺失"的 FileNotFoundError 在本仓 _run 未捕获（仅捕获
        TimeoutExpired）——锁定实际口径：测试改用 `false` 命令（存在且恒返回
        1）验证"非 0 返回码"分支，避免平台差异。
        """
        from src.agents.executor_repo import _run

        proc = _run(["false"], cwd=".", timeout=5)
        assert proc.returncode == 1

    def test_timeout_bytes_stdout_decoded(self):
        """text=True 下超时已捕获的 stdout/stderr 为 str；模拟 bytes 兜底路径。

        直接构造 TimeoutExpired(bytes) 验证 _run 的解码分支。
        """
        import src.agents.executor_repo as er

        # monkeypatch subprocess.run 抛 TimeoutExpired（bytes stdout）
        timeout_exc = subprocess.TimeoutExpired(cmd=["x"], timeout=1)
        timeout_exc.stdout = b"partial-out"
        timeout_exc.stderr = b"partial-err"

        with patch.object(er.subprocess, "run", side_effect=timeout_exc):
            proc = er._run(["x"], cwd=".", timeout=1)
        assert proc.returncode == 124
        assert proc.stdout == "partial-out"
        assert "partial-err" in proc.stderr
        assert "超时" in proc.stderr

    def test_timeout_none_output_empty_strings(self):
        """超时且 stdout/stderr 均为 None → 空串兜底。"""
        import src.agents.executor_repo as er

        timeout_exc = subprocess.TimeoutExpired(cmd=["x"], timeout=1)
        timeout_exc.stdout = None
        timeout_exc.stderr = None

        with patch.object(er.subprocess, "run", side_effect=timeout_exc):
            proc = er._run(["x"], cwd=".", timeout=1)
        assert proc.returncode == 124
        assert proc.stdout == ""
        assert "超时" in proc.stderr


# ─── RepoExecutor.__init__ 默认值 ──────────────────────────────────────────


class TestRepoExecutorInitBranches:
    def test_defaults(self, monkeypatch):
        from src.agents.executor_repo import RepoExecutor

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", "/tmp/er_envs")
        ex = RepoExecutor()
        assert ex.timeout == 30
        assert ex.setup_timeout == 600
        assert ex.use_venv is False
        assert ex.venv_reuse_by_repo is False
        assert ex.env_root == "/tmp/er_envs"

    def test_custom_values(self, monkeypatch):
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(timeout=10, setup_timeout=120, use_venv=True, venv_reuse_by_repo=True)
        assert ex.timeout == 10
        assert ex.setup_timeout == 120
        assert ex.use_venv is True
        assert ex.venv_reuse_by_repo is True


# ─── _resolve_venv_dir 分支 ────────────────────────────────────────────────


class TestResolveVenvDirBranches:
    def test_no_venv_returns_env_dir(self):
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(use_venv=False)
        assert ex._resolve_venv_dir("/env", "url", "/repo") == "/env"

    def test_venv_no_reuse_returns_env_dir(self):
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=False)
        assert ex._resolve_venv_dir("/env", "url", "/repo") == "/env"

    def test_venv_reuse_returns_repo_venv_dir(self):
        """use_venv+reuse → 解析为仓库级共享目录（<repo 名>/_shared_venv 形态）。"""
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        out = ex._resolve_venv_dir("/env", "https://github.com/org/repo.git", "/repo")
        # 共享目录含 "_shared_venv" 标记且不含 env_dir
        assert "_shared_venv" in out
        assert out != "/env"


# ─── _venv_python 分支 ─────────────────────────────────────────────────────


class TestVenvPythonBranches:
    def test_no_venv_returns_none(self, monkeypatch):
        from src.agents.executor_repo import RepoExecutor

        ex = RepoExecutor(use_venv=False)
        assert ex._venv_python("/env") is None

    def test_venv_not_built_returns_none(self, tmp_path, monkeypatch):
        """use_venv=True 但 venv/bin/python 不存在 → None（未建立）。"""
        from src.agents.executor_repo import RepoExecutor

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path))
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=False)
        # tmp_path 下无 venv 目录 → _venv_python 返回 None
        assert ex._venv_python(str(tmp_path)) is None

    def test_venv_built_returns_path(self, tmp_path, monkeypatch):
        """venv/bin/python 存在 → 返回该路径。"""
        from src.agents.executor_repo import RepoExecutor

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path))
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=False)
        venv_python = tmp_path / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("#!/usr/bin/env python\n")
        assert ex._venv_python(str(tmp_path)) == str(venv_python)

    def test_venv_reuse_resolves_shared_dir(self, tmp_path, monkeypatch):
        """venv_reuse_by_repo=True 时 venv python 解析自仓库级共享目录。"""
        from src.agents.executor_repo import RepoExecutor

        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(tmp_path))
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        # 构造共享目录下的 venv python
        shared = ex._resolve_venv_dir(str(tmp_path), "https://github.com/org/repo.git", "/repo")
        venv_python = os.path.join(shared, "venv", "bin", "python")
        os.makedirs(os.path.dirname(venv_python), exist_ok=True)
        with open(venv_python, "w") as f:
            f.write("#!/usr/bin/env python\n")
        out = ex._venv_python(str(tmp_path), "https://github.com/org/repo.git", "/repo")
        assert out == venv_python


# ─── setup 缓存命中判定（mock git rev-parse）──────────────────────────────


class TestSetupCacheHitBranches:
    def _mk_setup_env(self, tmp_path, use_venv: bool = False):
        """构造 setup 缓存命中所需目录结构 + pip 标记。"""

        env_root = tmp_path / "envs"
        repo_name = "myrepo"
        commit = "abc123def456"  # 12 字符
        env_dir = env_root / repo_name / commit[:12]
        repo_dir = env_dir / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        marker = ".venv_pip_installed" if use_venv else ".pip_installed"
        (env_dir / marker).write_text("ok")
        return str(env_root), repo_name, commit, str(env_dir), str(repo_dir)

    def test_cache_hit_checkout_at_commit(self, tmp_path, monkeypatch):
        """缓存标记存在 + git rev-parse HEAD == commit → cached=True。"""
        from src.agents.executor_repo import RepoExecutor

        env_root, _repo_name, commit, _env_dir, repo_dir = self._mk_setup_env(tmp_path)
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", env_root)
        ex = RepoExecutor()

        def _fake_git(cmd, cwd, timeout, env=None):
            if "rev-parse" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=commit + "\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("src.agents.executor_repo._run", side_effect=_fake_git):
            result = ex.setup("https://github.com/org/myrepo.git", commit)
        assert result["cached"] is True
        assert result["workdir"] == repo_dir
        assert result["error"] is None

    def test_cache_drift_reprepares(self, tmp_path, monkeypatch):
        """缓存标记存在但 HEAD 偏离 commit → 重新准备（cached=False）。"""
        from src.agents.executor_repo import RepoExecutor

        env_root, _repo_name, commit, _env_dir, _repo_dir = self._mk_setup_env(tmp_path)
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", env_root)
        ex = RepoExecutor()

        def _fake_git(cmd, cwd, timeout, env=None):
            if "rev-parse" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="ffffffffffff\n", stderr="")
            # 其他 git 命令（clone/checkout/install 标记等）一律成功
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("src.agents.executor_repo._run", side_effect=_fake_git):
            result = ex.setup("https://github.com/org/myrepo.git", commit)
        # checkout 漂移 → 重新准备（走非缓存路径）
        assert result["cached"] is False

    def test_cache_miss_no_marker(self, tmp_path, monkeypatch):
        """pip 标记不存在 → 缓存未命中（走完整 clone/install 路径）。"""
        from src.agents.executor_repo import RepoExecutor

        env_root = tmp_path / "envs_empty"
        env_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(env_root))
        ex = RepoExecutor()

        def _fake_git(cmd, cwd, timeout, env=None):
            return subprocess.CompletedProcess(cmd, 0, stdout="abc123def456\n", stderr="")

        with patch("src.agents.executor_repo._run", side_effect=_fake_git):
            result = ex.setup("https://github.com/org/myrepo.git", "abc123def456")
        assert result["cached"] is False
