#!/usr/bin/env python3
"""O 轮：RepoExecutor 嵌套 pytest 的"同秒同尺寸源码 → stale pyc 假红"根修回归。

背景（O-4 在 CI 探针里复现，O 轮根修）：
`executor-repo-verify` 的 baseline 与 llm_patch 两阶段常在 1s 内写入**同尺寸**
源码；CPython pyc 头只校验 (源 mtime 整秒, size)，于是第二轮 pytest 复用
baseline 字节码 → "补丁已应用却仍失败"的随机假红（本地 executor-repo-verify
6/15 复现）。O-4 曾用 CI/Makefile 侧 sitecustomize 规避；本轮在唯一 pytest
咽喉点（`RepoExecutor._run_test_nodes`）写 `PYTHONDONTWRITEBYTECODE=1` + `-B`
双保险（env 可传播到 pytest 子进程），从根上消除竞态。

本文件锁定：
1) 传参契约（`-B` + env 双保险不得回退）；
2) 行为证据（两阶段同秒同尺寸改写后，第二轮读到新源码；repo 内不产生 __pycache__）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.agents import executor_repo as er


@pytest.fixture()
def repo_dir(tmp_path: Path) -> Path:
    """最小可 pytest 仓库：mod.py + test_mod.py（无第三方依赖）。"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "test_mod.py").write_text(
        "import mod\n\n\ndef test_value():\n    assert mod.VALUE == 1\n",
        encoding="utf-8",
    )
    return root


def _make_executor(monkeypatch) -> er.RepoExecutor:
    executor = er.RepoExecutor(use_venv=False, timeout=60, setup_timeout=60)
    monkeypatch.setattr(executor, "_venv_python", lambda *a, **k: sys.executable)
    return executor


class TestBytecodeContract:
    def test_run_test_nodes_passes_dash_b_and_env(self, monkeypatch, repo_dir):
        captured: dict = {}

        class _Ok:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, cwd, timeout, env=None):
            captured["cmd"] = list(cmd)
            captured["env"] = dict(env or {})
            return _Ok()

        monkeypatch.setattr(er, "_run", fake_run)
        executor = _make_executor(monkeypatch)
        executor._run_test_nodes(str(repo_dir), ["test_mod.py::test_value"])
        assert "-B" in captured["cmd"], "pytest 调用未带 -B（stale pyc 竞态会回归）"
        assert captured["env"].get("PYTHONDONTWRITEBYTECODE") == "1"

    def test_does_not_write_bytecode_into_repo(self, monkeypatch, repo_dir):
        """真实跑子进程：repo 内不得出现 __pycache__（否则同秒同尺寸改写会撞 stale pyc）。"""
        executor = _make_executor(monkeypatch)
        result = executor._run_test_nodes(str(repo_dir), ["test_mod.py::test_value"])
        assert result["passed"] or result.get("failed_cases") == []
        pycache_dirs = list(repo_dir.rglob("__pycache__"))
        pycs = list(repo_dir.rglob("*.pyc"))
        assert pycache_dirs == [] and pycs == [], f"repo 内写入了字节码缓存：{pycache_dirs + pycs}"


class TestSameSecondRewrite:
    def test_same_second_same_size_rewrite_sees_new_source(self, monkeypatch, repo_dir):
        """baseline 与 patch 两阶段同秒同尺寸：第二轮必须读到新源码（根因行为回归）。"""
        executor = _make_executor(monkeypatch)
        first = executor._run_test_nodes(str(repo_dir), ["test_mod.py::test_value"])
        assert first["passed"], f"baseline 阶段应通过：{first}"

        # 同尺寸改写（VALUE = 1 -> VALUE = 2），并把 mtime 固定回 baseline 阶段同一秒
        mod = repo_dir / "mod.py"
        baseline_stat = mod.stat()
        mod.write_text("VALUE = 2\n", encoding="utf-8")
        os.utime(mod, ns=(baseline_stat.st_atime_ns, baseline_stat.st_mtime_ns))
        (repo_dir / "test_mod.py").write_text(
            "import mod\n\n\ndef test_value():\n    assert mod.VALUE == 2\n",
            encoding="utf-8",
        )
        second = executor._run_test_nodes(str(repo_dir), ["test_mod.py::test_value"])
        assert second["passed"], "同秒同尺寸改写后第二轮仍失败——stale pyc 假红回归（检查 -B/PYTHONDONTWRITEBYTECODE）"
