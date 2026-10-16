#!/usr/bin/env python3
"""覆盖率补口 + 语义锁定：仓库级测试节点运行器与 setup 失败传播。

动机（EMSE 多轮优化批次·仓库级验证）：`_run_test_nodes` 是 F2P/P2P 判定的执行
内核，其返回值直接决定 `passed`。它的退出码分派（0/1/4/5/124/其它）与
**PYTHONPATH 注入策略随 venv 模式切换**是两处易错点：

1. venv 模式下**不得**注入 PYTHONPATH（editable 安装已把本 commit 源码写进 venv；
   注入会把宿主/其它 commit 路径混进搜索序，破坏跨 commit 隔离）；
2. 全局模式下必须把仓库根（src 布局则 `<repo>/src` 排最前）注入，否则跨 commit
   会 `import` 到"最近一次 pip install -e"的错误版本。

本文件用 monkeypatch 替换**该模块内的** `_run`（不是真实 subprocess），
对退出码分派做确定性覆盖；零 LLM、零网络、毫秒级。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import src.agents.executor_repo as repo_mod
from src.agents.executor_repo import RepoExecutor


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["pytest"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """替换模块内 `_run`，记录 (cmd, env) 并返回可编程的退出码序列。"""
    state: dict[str, object] = {"calls": [], "results": []}

    def _fake_run(cmd, cwd, timeout, env=None):
        state["calls"].append({"cmd": list(cmd), "cwd": cwd, "env": dict(env or {})})
        results = state["results"]
        assert isinstance(results, list)
        return results.pop(0) if results else _proc(0)

    monkeypatch.setattr(repo_mod, "_run", _fake_run, raising=True)
    return state


class TestRunTestNodesDispatch:
    def test_empty_nodes_short_circuits(self, tmp_path: Path):
        executor = RepoExecutor()
        assert executor._run_test_nodes(str(tmp_path), []) == {
            "expected": 0,
            "passed": 0,
            "failed_cases": [],
        }

    def test_exit_zero_counts_as_passed(self, tmp_path: Path, recorder: dict[str, object]):
        recorder["results"] = [_proc(0, "1 passed")]
        result = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::test_ok"])
        assert result["passed"] == 1 and result["failed_cases"] == []

    def test_exit_one_records_failure_with_tail(self, tmp_path: Path, recorder: dict[str, object]):
        recorder["results"] = [_proc(1, "E   assert 1 == 2", "")]
        result = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::test_bad"])
        assert result["passed"] == 0
        assert len(result["failed_cases"]) == 1
        assert "assert 1 == 2" in result["failed_cases"][0]["error"]

    def test_exit_four_is_node_parse_failure(self, tmp_path: Path, recorder: dict[str, object]):
        recorder["results"] = [_proc(4, "ERROR: not found")]
        result = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::nope"])
        assert "节点解析失败 (exit 4)" in result["failed_cases"][0]["error"]

    def test_exit_five_is_no_tests_collected(self, tmp_path: Path, recorder: dict[str, object]):
        recorder["results"] = [_proc(5)]
        result = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py"])
        assert result["failed_cases"][0]["error"] == "无测试可收集 (exit 5)"

    def test_exit_124_is_timeout_and_loop_continues(self, tmp_path: Path, recorder: dict[str, object]):
        """超时哨兵（124）按失败记录并继续下一节点——不得让整个验证任务崩掉。"""
        recorder["results"] = [_proc(124, "", "killed"), _proc(0, "ok")]
        result = RepoExecutor(timeout=7)._run_test_nodes(
            str(tmp_path), ["tests/test_a.py::slow", "tests/test_b.py::fast"]
        )
        assert "节点执行超时（>7s）" in result["failed_cases"][0]["error"]
        assert result["passed"] == 1, "超时后必须继续跑后续节点"
        assert result["expected"] == 2

    def test_other_exit_codes_are_failures(self, tmp_path: Path, recorder: dict[str, object]):
        recorder["results"] = [_proc(3, "internal error")]
        result = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::x"])
        assert len(result["failed_cases"]) == 1
        assert "internal error" in result["failed_cases"][0]["error"]


class TestPythonPathStrategy:
    """PYTHONPATH 注入策略随模式切换（跨 commit 隔离的关键）。"""

    def _env_of_first_call(self, recorder: dict[str, object]) -> dict[str, str]:
        calls = recorder["calls"]
        assert isinstance(calls, list) and calls
        return calls[0]["env"]  # type: ignore[return-value]

    def test_global_mode_injects_repo_root(self, tmp_path: Path, recorder: dict[str, object]):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        recorder["results"] = [_proc(0)]
        RepoExecutor(use_venv=False)._run_test_nodes(str(repo_dir), ["tests/test_a.py::t"])
        pythonpath = self._env_of_first_call(recorder)["PYTHONPATH"]
        assert str(repo_dir) in pythonpath.split(os.pathsep)

    def test_global_mode_puts_src_layout_first(self, tmp_path: Path, recorder: dict[str, object]):
        """src 布局仓库：`<repo>/src` 必须排在最前，压过全局 editable 安装。"""
        repo_dir = tmp_path / "repo"
        (repo_dir / "src").mkdir(parents=True)
        recorder["results"] = [_proc(0)]
        RepoExecutor(use_venv=False)._run_test_nodes(str(repo_dir), ["tests/test_a.py::t"])
        entries = self._env_of_first_call(recorder)["PYTHONPATH"].split(os.pathsep)
        assert entries[0] == str(repo_dir / "src"), entries

    def test_venv_mode_does_not_inject_repo_root(self, tmp_path: Path, recorder: dict[str, object]):
        """venv 模式：editable 安装负责导入解析，注入仓库路径会破坏隔离。"""
        repo_dir = tmp_path / "envs" / "abc" / "repo"
        repo_dir.mkdir(parents=True)
        recorder["results"] = [_proc(0)]
        RepoExecutor(use_venv=True)._run_test_nodes(str(repo_dir), ["tests/test_a.py::t"])
        pythonpath = self._env_of_first_call(recorder).get("PYTHONPATH", "")
        assert str(repo_dir) not in pythonpath.split(os.pathsep)

    def test_existing_pythonpath_entries_are_preserved(
        self, tmp_path: Path, recorder: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        # scrub_os_environ 会裁剪环境变量，故直接断言"注入项与既有项合并"的口径：
        # 通过给模块级 scrub 打桩返回带既有 PYTHONPATH 的映射来构造。
        monkeypatch.setattr(
            repo_mod,
            "scrub_os_environ",
            lambda: {"PYTHONPATH": "/opt/preexisting", "PATH": "/usr/bin"},
            raising=True,
        )
        recorder["results"] = [_proc(0)]
        RepoExecutor(use_venv=False)._run_test_nodes(str(repo_dir), ["tests/test_a.py::t"])
        entries = self._env_of_first_call(recorder)["PYTHONPATH"].split(os.pathsep)
        assert "/opt/preexisting" in entries
        assert str(repo_dir) in entries


class TestVerifySetupFailurePropagation:
    def test_setup_error_short_circuits_verify(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """环境准备失败 → verify 必须直接返回结构化诊断（不跑测试、不抛异常）。"""
        executor = RepoExecutor()
        monkeypatch.setattr(
            RepoExecutor,
            "setup",
            lambda self, repo_url, base_commit: {
                "workdir": str(tmp_path / "repo"),
                "cached": False,
                "error": "simulated clone failure",
            },
            raising=True,
        )
        result = executor.verify(
            repo_url="file:///nonexistent",
            base_commit="0" * 40,
            llm_patch="",
            test_patch="",
            fail_to_pass=["tests/test_a.py::t"],
            pass_to_pass=[],
        )
        assert result["passed"] is False
        assert result["error_info"]["type"] == "repo_env_setup_failed"
        assert "simulated clone failure" in result["error_info"]["message"]
        assert result["repo_env"]["error"] == "simulated clone failure"
