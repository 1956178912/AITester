#!/usr/bin/env python3
"""Z 轮（2026-10-19 第四轮第三方全量静态审查）执行器/数据库修复回归锁。

覆盖审查报告 F04 / F07 / F10 / F11（均 P1）：

- F04 ``executor_runtime._make_resource_preexec_fn``：契约"0=禁用"此前未兑现
  （实际 ``setrlimit(..., (0, 0))`` 把额度压到 0）。现每项 ``> 0`` 才设置，
  0 跳过；Darwin 跳过 AS 的既有兜底不得回归。
- F07 ``init_db.init_database``：conn/cursor 生命周期此前只包 commit；现覆盖
  数据库名校验、全部 SQL、commit 的整个使用区间，finally 分项关闭；连接失败
  时 conn=None 不重复关闭。
- F10 ``executor_repo`` 共享 venv：per-commit 缓存命中时 venv 的 editable
  绑定可能仍指上一个 commit（A→B→A 回 A 导入 B 源码）。现读
  ``<venv>/.venv_editable_commit`` 校验，不一致则在仓库级锁内重指向并更新
  marker；run_benchmark 构造处接线 ``SWE_REPO_VENV_REUSE_BY_REPO``（此前该
  README 承诺的开关全仓无消费点、实际不可达）。
- F11 官方 swebench harness 全链：命名参数 CLI、官方 predictions schema
  （instance_id / model_name_or_path / model_patch）、真实 instance_id 透传、
  report_dir 递归报告解析、缺 instance_id/坏 schema/非零 rc → 降级 None
  （绝不假过）。

纪律：零 LLM、零网络、零真实 git/pip/venv/swebench/mysql；全部 mock 或
tmp_path 假文件系统驱动。macOS 无法实测 Linux setrlimit 真实效果、官方
swebench 包也未安装——本文件只锁定调用契约与降级方向。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import init_db as init_db_mod
import src.agents.executor_repo as repo_mod
import src.agents.executor_runtime as er
from src.agents.executor_repo import RepoExecutor

_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40
_REPO_URL = "https://github.com/foo/bar.git"
_INSTANCE_ID = "django__django-12345"


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=returncode, stdout=stdout, stderr=stderr)


# ══════════════════════════════════════════════════════════════════════════
# F04：EXECUTOR_RLIMIT_* 的 0 = 禁用（不调用 setrlimit）
# ══════════════════════════════════════════════════════════════════════════


_RLIMIT_ENV_TO_NAME = {
    "EXECUTOR_RLIMIT_CPU": "CPU",
    "EXECUTOR_RLIMIT_AS_MB": "AS",
    "EXECUTOR_RLIMIT_NPROC": "NPROC",
    "EXECUTOR_RLIMIT_FSIZE_MB": "FSIZE",
    "EXECUTOR_RLIMIT_NOFILE": "NOFILE",
}
_ALL_RLIMIT_ENVS = (*_RLIMIT_ENV_TO_NAME, "EXECUTOR_RLIMIT_AS_FORCE")


def _call_preexec_linux(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str] | None = None
) -> list[tuple[str, tuple[int, int]]]:
    """按 Linux 口径构造 preexec 闭包并记录 setrlimit 调用（不触碰真实资源）。"""
    for name in _ALL_RLIMIT_ENVS:
        monkeypatch.delenv(name, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(er, "_IS_DARWIN", False)
    fn = er._make_resource_preexec_fn()
    assert fn is not None
    import resource

    names = {
        resource.RLIMIT_CPU: "CPU",
        resource.RLIMIT_AS: "AS",
        resource.RLIMIT_NPROC: "NPROC",
        resource.RLIMIT_FSIZE: "FSIZE",
        resource.RLIMIT_NOFILE: "NOFILE",
    }
    calls: list[tuple[str, tuple[int, int]]] = []

    def _spy(which, limits):
        calls.append((names.get(which, str(which)), limits))

    monkeypatch.setattr(resource, "setrlimit", _spy)
    fn()
    return calls


@pytest.mark.unit
class TestF04RlimitZeroDisables:
    """报告 §M7 反例：0 不得变成 (0,0)，而是跳过该 setrlimit 调用。"""

    def test_defaults_set_five_limits_with_positive_quota(self, monkeypatch: pytest.MonkeyPatch):
        calls = _call_preexec_linux(monkeypatch)
        names = [name for name, _limits in calls]
        assert names == ["CPU", "AS", "NPROC", "FSIZE", "NOFILE"]
        assert all(limits != (0, 0) for _n, limits in calls), "默认值不得写成 (0,0)"
        # 正默认值仍按历史口径换算（AS 512MB、FSIZE 100MB 等）
        by_name = dict(calls)
        assert by_name["CPU"] == (300, 300)
        assert by_name["AS"] == (512 * 1024 * 1024, 512 * 1024 * 1024)
        assert by_name["NPROC"] == (512, 512)
        assert by_name["FSIZE"] == (100 * 1024 * 1024, 100 * 1024 * 1024)
        assert by_name["NOFILE"] == (256, 256)

    @pytest.mark.parametrize("env_name,limit_name", list(_RLIMIT_ENV_TO_NAME.items()))
    def test_zero_skips_only_that_limit(self, monkeypatch: pytest.MonkeyPatch, env_name: str, limit_name: str):
        calls = _call_preexec_linux(monkeypatch, {env_name: "0"})
        names = [name for name, _limits in calls]
        assert limit_name not in names, f"{env_name}=0 应禁用 {limit_name}（而非设成 0 额度）"
        assert len(names) == 4, f"{env_name}=0 只影响该项，其余四项照常设置"
        assert all(limits != (0, 0) for _n, limits in calls)

    def test_all_zero_sets_no_limit(self, monkeypatch: pytest.MonkeyPatch):
        calls = _call_preexec_linux(monkeypatch, {name: "0" for name in _RLIMIT_ENV_TO_NAME})
        assert calls == [], "五项全 0 时不得调用任何 setrlimit"

    def test_zero_as_is_not_revived_by_force_switch(self, monkeypatch: pytest.MonkeyPatch):
        # F04 契约优先于 Darwin 的 AS_FORCE 开关：显式 AS=0 仍是"禁用"
        calls = _call_preexec_linux(monkeypatch, {"EXECUTOR_RLIMIT_AS_MB": "0", "EXECUTOR_RLIMIT_AS_FORCE": "1"})
        assert "AS" not in [name for name, _limits in calls]

    def test_positive_as_encodes_megabytes(self, monkeypatch: pytest.MonkeyPatch):
        calls = _call_preexec_linux(monkeypatch, {"EXECUTOR_RLIMIT_AS_MB": "128"})
        assert dict(calls)["AS"] == (128 * 1024 * 1024, 128 * 1024 * 1024)

    def test_darwin_still_skips_as(self, monkeypatch: pytest.MonkeyPatch):
        # 既有 S5 平台兜底不得回归：Darwin 默认跳过 AS，其余四项保留。
        for name in _ALL_RLIMIT_ENVS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(er, "_IS_DARWIN", True)
        fn = er._make_resource_preexec_fn()
        assert fn is not None
        import resource

        names = {
            resource.RLIMIT_CPU: "CPU",
            resource.RLIMIT_AS: "AS",
            resource.RLIMIT_NPROC: "NPROC",
            resource.RLIMIT_FSIZE: "FSIZE",
            resource.RLIMIT_NOFILE: "NOFILE",
        }
        called: list[str] = []
        monkeypatch.setattr(resource, "setrlimit", lambda which, _limits: called.append(names.get(which, "?")))
        fn()
        assert "AS" not in called
        assert called == ["CPU", "NPROC", "FSIZE", "NOFILE"]


# ══════════════════════════════════════════════════════════════════════════
# F07：init_database 资源生命周期覆盖整个使用区间
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestF07InitDatabaseResourceCleanup:
    """报告 §M9 反例：SQL 异常后 cursor/conn 均须 close（此前均 False）。"""

    @staticmethod
    def _connect_ok() -> tuple[Mock, Mock]:
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_sql_exception_closes_cursor_and_conn(self, monkeypatch: pytest.MonkeyPatch):
        conn, cursor = self._connect_ok()
        cursor.execute.side_effect = RuntimeError("injected SQL failure")
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        with pytest.raises(RuntimeError, match="injected SQL failure"):
            init_db_mod.init_database()
        assert cursor.close.called, "SQL 异常时 cursor 必须关闭（F07 前为泄漏）"
        assert conn.close.called, "SQL 异常时 conn 必须关闭（F07 前为泄漏）"

    def test_invalid_db_name_closes_both(self, monkeypatch: pytest.MonkeyPatch):
        conn, cursor = self._connect_ok()
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "bad; DROP TABLE x")
        with pytest.raises(ValueError, match="非法数据库名"):
            init_db_mod.init_database()
        assert cursor.close.called and conn.close.called, "库名校验抛异常也在资源生命周期内"

    def test_commit_exception_closes_both(self, monkeypatch: pytest.MonkeyPatch):
        conn, cursor = self._connect_ok()
        conn.commit.side_effect = RuntimeError("commit boom")
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        with pytest.raises(RuntimeError, match="commit boom"):
            init_db_mod.init_database()
        assert cursor.close.called and conn.close.called

    def test_cursor_creation_failure_still_closes_conn(self, monkeypatch: pytest.MonkeyPatch):
        conn = Mock()
        conn.cursor.side_effect = RuntimeError("cursor failed")
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        with pytest.raises(RuntimeError, match="cursor failed"):
            init_db_mod.init_database()
        assert conn.close.called, "cursor 获取失败时 conn 已创建，必须关闭"

    def test_connect_failure_raises_once_without_second_close_error(self, monkeypatch: pytest.MonkeyPatch):
        # 连接失败：conn 保持 None → finally 不得再 close（否则 AttributeError
        # 会顶替原始异常，形成"二次异常"）。只允许原异常向上传播一次。
        calls: list[int] = []

        def _connect(**_kw):
            calls.append(1)
            raise RuntimeError("connection refused")

        monkeypatch.setattr(init_db_mod.pymysql, "connect", _connect)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        with pytest.raises(RuntimeError) as excinfo:
            init_db_mod.init_database()
        assert excinfo.value.args == ("connection refused",), "不得抛二次异常/替换原异常"
        assert len(calls) == 1

    def test_close_failure_is_suppressed(self, monkeypatch: pytest.MonkeyPatch):
        conn, cursor = self._connect_ok()
        cursor.close.side_effect = RuntimeError("cursor close boom")
        conn.close.side_effect = RuntimeError("conn close boom")
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        assert init_db_mod.init_database() is None, "关闭动作失败不得盖过初始化成功/原异常"
        assert conn.commit.called

    def test_success_path_commit_and_closes(self, monkeypatch: pytest.MonkeyPatch):
        conn, cursor = self._connect_ok()
        monkeypatch.setattr(init_db_mod.pymysql, "connect", lambda **_kw: conn)
        monkeypatch.setattr(init_db_mod, "MYSQL_DATABASE", "audit")
        assert init_db_mod.init_database() is None
        assert conn.commit.called
        assert cursor.close.called and conn.close.called
        # CREATE DATABASE + USE + 三张建表 = 5 条 SQL
        assert cursor.execute.call_count == 5


# ══════════════════════════════════════════════════════════════════════════
# F10：共享 venv 的 editable 源码绑定（A→B→A 错 commit）
# ══════════════════════════════════════════════════════════════════════════


def _setup_shared_venv_cache_hit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    marker: str | None = _COMMIT_B,
    use_venv: bool = True,
    reuse: bool = True,
    create_venv_python: bool = True,
    commit: str = _COMMIT_A,
) -> tuple[RepoExecutor, str, str, list[list[str]]]:
    """构造共享 venv 下"目标 commit 已缓存"的现场。

    Returns:
        (executor, repo_dir, venv_dir, run_calls)。
    """
    root = tmp_path / "envs"
    monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(root))
    ex = RepoExecutor(use_venv=use_venv, venv_reuse_by_repo=reuse)
    env_dir = os.path.join(ex.env_root, "bar", commit[:12])
    repo_dir = os.path.join(env_dir, "repo")
    os.makedirs(repo_dir)
    pip_marker = ".venv_pip_installed" if use_venv else ".pip_installed"
    with open(os.path.join(env_dir, pip_marker), "w", encoding="utf-8") as f:
        f.write(commit)
    venv_dir = ex._repo_venv_dir(_REPO_URL, repo_dir)
    if create_venv_python:
        vpy = os.path.join(venv_dir, "venv", "bin", "python")
        os.makedirs(os.path.dirname(vpy))
        with open(vpy, "w", encoding="utf-8") as f:
            f.write("")
    if marker is not None:
        os.makedirs(venv_dir, exist_ok=True)
        with open(os.path.join(venv_dir, ".venv_editable_commit"), "w", encoding="utf-8") as f:
            f.write(marker)
    run_calls: list[list[str]] = []

    def _fake_run(cmd, _cwd, _timeout, env=None):
        run_calls.append(list(cmd))
        return _proc(0, stdout=commit + "\n")

    monkeypatch.setattr(repo_mod, "_run", _fake_run)
    return ex, repo_dir, venv_dir, run_calls


@pytest.mark.unit
class TestF10SharedVenvEditableBinding:
    """报告 §M8 反例：缓存命中 A、marker=B → repoint≥1 且 marker 刷新为 A。"""

    def test_cache_hit_with_stale_binding_repoints_and_updates_marker(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        ex, repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_B)
        repoints: list[tuple[str, str]] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda r, v: repoints.append((r, v)) or None)
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out["cached"] is True and out["error"] is None
        assert repoints == [(repo_dir, venv_dir)], "共享 venv 缓存命中且绑定漂移 → 必须重指向目标 commit"
        marker = os.path.join(venv_dir, ".venv_editable_commit")
        assert Path(marker).read_text(encoding="utf-8") == _COMMIT_A

    def test_cache_hit_with_matching_binding_skips_repoint(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_A)
        repoints: list[object] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda r, v: repoints.append((r, v)) or None)
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out["cached"] is True and out["error"] is None
        assert repoints == [], "同 commit 缓存命中不得重复 pip install（性能不变）"
        assert Path(os.path.join(venv_dir, ".venv_editable_commit")).read_text(encoding="utf-8") == _COMMIT_A

    def test_cache_hit_without_marker_treated_as_unknown_and_repoints(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # 旧版缓存没有 marker：保守视为"绑定未知"，必须验证性重指向一次。
        ex, _repo_dir, _venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=None)
        calls: list[object] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda r, v: calls.append((r, v)) or None)
        assert ex.setup(_REPO_URL, _COMMIT_A)["cached"] is True
        assert len(calls) == 1

    def test_a_to_b_to_a_second_hit_does_not_repoint_again(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        # 完整 A→B→A 语义：首批命中把绑定从 B 刷成 A；再回 A 命中时零安装。
        ex, _repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_B)
        repoints: list[object] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda r, v: repoints.append((r, v)) or None)
        assert ex.setup(_REPO_URL, _COMMIT_A)["cached"] is True
        assert ex.setup(_REPO_URL, _COMMIT_A)["cached"] is True
        assert len(repoints) == 1, "首次命中重指向一次后，绑定=A 的后续命中不得重复安装"
        assert Path(os.path.join(venv_dir, ".venv_editable_commit")).read_text(encoding="utf-8") == _COMMIT_A

    def test_check_and_repoint_happen_under_venv_lock(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_B)
        venv_lock = repo_mod._get_repo_setup_lock(venv_dir)  # ensure 内部取到的同一把锁
        seen: dict[str, bool] = {}

        def _record_install(_repo_dir: str, _venv_dir: str) -> None:
            seen["locked_during_install"] = venv_lock.locked()

        monkeypatch.setattr(ex, "_venv_pip_install", _record_install)
        assert ex.setup(_REPO_URL, _COMMIT_A)["cached"] is True
        assert seen["locked_during_install"] is True, "检查+重指向必须在仓库级 venv 锁内，避免跨 commit 交错"
        assert venv_lock.locked() is False, "setup 返回后锁必须释放"

    def test_repoint_failure_reports_error_and_keeps_old_binding(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_B)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: "pip 网络异常")
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out["cached"] is True
        assert out["error"] == "pip 网络异常", "重指向失败须如实返回（verify 侧据此 fail-closed）"
        assert Path(os.path.join(venv_dir, ".venv_editable_commit")).read_text(encoding="utf-8") == _COMMIT_B

    def test_missing_venv_python_is_reported_fail_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, _venv_dir, _calls = _setup_shared_venv_cache_hit(
            monkeypatch, tmp_path, marker=_COMMIT_B, create_venv_python=False
        )
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out["cached"] is True and out["error"] is not None
        assert "共享 venv 不可用" in out["error"]

    def test_non_shared_venv_cache_hit_is_unchanged(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, venv_dir, _calls = _setup_shared_venv_cache_hit(
            monkeypatch, tmp_path, marker=None, use_venv=True, reuse=False
        )
        repoints: list[object] = []
        monkeypatch.setattr(ex, "_venv_pip_install", lambda r, v: repoints.append((r, v)) or None)
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out == {
            "workdir": os.path.join(ex.env_root, "bar", _COMMIT_A[:12], "repo"),
            "cached": True,
            "error": None,
        }
        assert repoints == [], "per-commit venv 的缓存命中路径零变化（不引入 marker/重指向）"
        assert not os.path.exists(os.path.join(venv_dir, ".venv_editable_commit")), (
            "非共享模式不得写共享 marker（venv_dir 即 env_dir）"
        )

    def test_global_mode_cache_hit_is_unchanged(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, repo_dir, _venv_dir, _calls = _setup_shared_venv_cache_hit(
            monkeypatch, tmp_path, marker=None, use_venv=False, reuse=False
        )
        repoints: list[object] = []
        monkeypatch.setattr(ex, "_pip_install_editable", lambda r: repoints.append(r) or None)
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out == {"workdir": repo_dir, "cached": True, "error": None}
        assert repoints == []

    def test_not_cached_install_writes_editable_marker(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        # 首次（非缓存）共享 venv 安装成功后必须写绑定 marker，否则每次命中
        # 都会误判"绑定未知"而白跑一次 pip install。
        root = tmp_path / "envs"
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(root))
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        env_dir = os.path.join(ex.env_root, "bar", _COMMIT[:12])
        repo_dir = os.path.join(env_dir, "repo")

        def _clone(_url, _commit, _dir):
            os.makedirs(_dir, exist_ok=True)

        os.makedirs(os.path.join(ex.env_root, "bar", "_shared_venv"), exist_ok=True)
        monkeypatch.setattr(ex, "_clone_and_checkout", _clone)
        monkeypatch.setattr(ex, "_create_venv", lambda _d: None)
        monkeypatch.setattr(ex, "_venv_pip_install", lambda _r, _v: None)
        out = ex.setup(_REPO_URL, _COMMIT)
        assert out["cached"] is False and out["error"] is None
        venv_dir = ex._repo_venv_dir(_REPO_URL, repo_dir)
        assert Path(os.path.join(venv_dir, ".venv_editable_commit")).read_text(encoding="utf-8") == _COMMIT

    def test_marker_write_failure_only_warns(self, tmp_path: Path):
        # 写 marker 失败的方向是安全的（下次命中多一次重指向），不得让 setup 崩。
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("x", encoding="utf-8")
        ex._write_venv_editable_commit(str(blocker / "venv"), _COMMIT_A)  # 不抛异常
        # 写失败方向安全：marker 不可读 → 下次缓存命中保守地重新校验并重指向
        assert ex._read_venv_editable_commit(str(blocker / "venv")) is None

    def test_repoint_pip_oserror_reported_as_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        ex, _repo_dir, _venv_dir, _calls = _setup_shared_venv_cache_hit(monkeypatch, tmp_path, marker=_COMMIT_B)

        def _raise(_r, _v):
            raise OSError("python 不可执行")

        monkeypatch.setattr(ex, "_venv_pip_install", _raise)
        out = ex.setup(_REPO_URL, _COMMIT_A)
        assert out["cached"] is True and out["error"] is not None
        assert "重指向异常" in out["error"]

    def test_verify_fails_closed_when_shared_venv_rebind_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        # setup 返回到 verify 跑测试之间，绑定可能被别的 commit 改掉；锁内复核
        # 失败时必须拒绝在未知/错误源码上裁决，而不是照常跑测试。
        root = tmp_path / "envs"
        monkeypatch.setenv("SWE_REPO_ENVS_DIR", str(root))
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_repoint_shared_venv_locked", lambda *_a: "模拟重指向失败")
        out = ex.verify(_REPO_URL, _COMMIT_A, "", "", ["t.py::a"], [])
        assert out["passed"] is False
        assert out["error_info"]["type"] == "repo_venv_rebind_failed"
        assert out["repo_env"]["cached"] is True
        # 提前 return 也必须释放 per-env 锁（否则后续同 (repo, commit) 的 setup 永久阻塞）
        env_dir = os.path.join(ex.env_root, "bar", _COMMIT_A[:12])
        assert repo_mod._get_repo_setup_lock(env_dir).locked() is False


@pytest.mark.unit
class TestF10RunBenchmarkWiring:
    """README 承诺的 SWE_REPO_VENV_REUSE_BY_REPO 必须真的被消费。"""

    def test_constructor_accepts_reuse_keyword(self):
        ex = RepoExecutor(use_venv=True, venv_reuse_by_repo=True)
        assert ex.venv_reuse_by_repo is True
        assert ex._shared_venv_reuse_enabled() is True

    def test_run_benchmark_wires_reuse_env_into_constructor(self):
        # 调用点在 run_benchmark 的批次主循环深处（需完整数据集/LLM 工作流），
        # 单测直接锁源码接线字符串——这是本仓对"文档承诺开关可达"的最小
        # 可验证证据；语义本身由 test_constructor_accepts_reuse_keyword 覆盖。
        src = (Path(__file__).resolve().parents[1] / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        assert src.count("venv_reuse_by_repo=") == 1, "RepoExecutor 构造处应且仅应有一处共享 venv 开关接线"
        assert 'venv_reuse_by_repo=os.environ.get("SWE_REPO_VENV_REUSE_BY_REPO", "false").lower()' in src.replace(
            "\n", " "
        ).replace("                        ", " ")
        assert '"SWE_REPO_VENV_REUSE_BY_REPO"' in src


# ══════════════════════════════════════════════════════════════════════════
# F11：官方 swebench harness 命令/预测/报告契约
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """替换模块内唯一子进程收敛点 _run，记录调用并按脚本返回。"""
    state: dict[str, object] = {"calls": [], "results": [], "raise_on": None}

    def _fake(cmd, cwd, timeout, env=None):
        state["calls"].append({"cmd": list(cmd), "cwd": cwd, "timeout": timeout})
        if state["raise_on"] is not None:
            raise state["raise_on"]
        results = state["results"]  # type: ignore[assignment]
        res = results.pop(0) if results else _proc()  # type: ignore[union-attr]
        return res(cmd, cwd, timeout) if callable(res) else res

    monkeypatch.setattr(repo_mod, "_run", _fake)
    return state


def _official_report(
    *, resolved: bool = True, f2p_success: list[str] | None = None, p2p_success: list[str] | None = None
) -> dict[str, object]:
    return {
        "resolved": resolved,
        "patch_successfully_applied": True,
        "tests_status": {
            "FAIL_TO_PASS": {"success": list(f2p_success or []), "failure": []},
            "PASS_TO_PASS": {"success": list(p2p_success or []), "failure": []},
        },
    }


def _runner_writing_report(instance_id: str, report_obj: dict[str, object], layout: str = "per_instance"):
    """runner 替身：从命名参数取 report_dir/run_id，按官方布局落报告。"""

    def _runner(cmd: list[str], _cwd: str, _timeout: int) -> subprocess.CompletedProcess[str]:
        report_dir = Path(cmd[cmd.index("--report_dir") + 1])
        run_id = cmd[cmd.index("--run_id") + 1]
        if layout == "per_instance":
            target = report_dir / run_id / "aitester" / instance_id
            target.mkdir(parents=True, exist_ok=True)
            (target / "report.json").write_text(
                json.dumps({"instance_id": instance_id, **report_obj}), encoding="utf-8"
            )
        else:
            (report_dir / f"{run_id}.aitester.json").write_text(json.dumps({instance_id: report_obj}), encoding="utf-8")
        return _proc(0)

    return _runner


@pytest.mark.unit
class TestF11OfficialHarnessContract:
    """报告 §M10：官方 CLI 参数/预测 schema 契约（真实包未安装，只锁调用面）。"""

    def test_cli_named_arguments_and_official_predictions(
        self, fake_run: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        captured: dict[str, object] = {}

        def _runner(cmd: list[str], cwd: str, timeout: int) -> subprocess.CompletedProcess[str]:
            captured["cmd"] = list(cmd)
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            pred_path = Path(cmd[cmd.index("--predictions_path") + 1])
            captured["predictions"] = json.loads(pred_path.read_text(encoding="utf-8"))
            report_dir = Path(cmd[cmd.index("--report_dir") + 1])
            (report_dir / "report.json").write_text(
                json.dumps({_INSTANCE_ID: _official_report(f2p_success=["a", "b"], p2p_success=["c"])}),
                encoding="utf-8",
            )
            return _proc(0)

        fake_run["results"] = [_runner]  # type: ignore[index]
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        out = ex._run_official_swebench_harness(
            _REPO_URL, _COMMIT, "test-patch-text", "model-patch-text", ["a", "b"], ["c"], instance_id=_INSTANCE_ID
        )
        assert out is not None and out["passed"] is True

        cmd = captured["cmd"]
        assert isinstance(cmd, list)
        assert cmd[:3] == [sys.executable, "-m", "swebench.harness.run_evaluation"]
        assert cmd[3].startswith("--"), "官方 CLI 只接受命名参数（历史位置参数 pred_file 已废弃）"
        assert cmd[cmd.index("--dataset_name") + 1] == repo_mod._OFFICIAL_HARNESS_DATASET
        assert repo_mod._OFFICIAL_HARNESS_DATASET == "SWE-bench/SWE-bench_Lite"
        assert cmd[cmd.index("--split") + 1] == "test"
        assert cmd[cmd.index("--max_workers") + 1] == str(repo_mod._OFFICIAL_HARNESS_MAX_WORKERS)
        run_id = cmd[cmd.index("--run_id") + 1]
        assert run_id.startswith(f"aitester-{_COMMIT[:8]}-")
        assert all(ch.isalnum() or ch in "-_." for ch in run_id), "run_id 必须是安全字符集"
        assert cmd[cmd.index("--report_dir") + 1].endswith("report")
        assert captured["cwd"] == os.path.dirname(cmd[cmd.index("--predictions_path") + 1])
        assert isinstance(captured["timeout"], int) and captured["timeout"] >= 300

        # 官方 predictions schema：真实 instance_id + model_name_or_path + model_patch
        assert captured["predictions"] == [
            {"instance_id": _INSTANCE_ID, "model_name_or_path": "aitester", "model_patch": "model-patch-text"}
        ]
        pred = captured["predictions"][0]
        assert "patch" not in pred and "test_patch" not in pred, (
            "官方 harness 只读 model_patch；test_patch 由评测侧自行应用"
        )
        assert "repo" not in pred and "base_commit" not in pred, "prediction 不再塞入非官方元数据"
        assert list(tmp_path.iterdir()) == [], "临时 predictions/report 目录必须清理"

    def test_dataset_name_override(self, fake_run: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        captured: dict[str, list[str]] = {}

        def _runner(cmd: list[str], _cwd: str, _timeout: int) -> subprocess.CompletedProcess[str]:
            captured["cmd"] = list(cmd)
            report_dir = Path(cmd[cmd.index("--report_dir") + 1])
            (report_dir / "r.json").write_text(
                json.dumps({"instance_id": _INSTANCE_ID, **_official_report(f2p_success=["a"], p2p_success=[])}),
                encoding="utf-8",
            )
            return _proc(0)

        fake_run["results"] = [_runner]  # type: ignore[index]
        assert (
            RepoExecutor(timeout=5, setup_timeout=5)._run_official_swebench_harness(
                _REPO_URL,
                _COMMIT,
                "",
                "",
                ["a"],
                [],
                instance_id=_INSTANCE_ID,
                dataset_name="SWE-bench/SWE-bench_Verified",
            )
            is not None
        )
        assert captured["cmd"][captured["cmd"].index("--dataset_name") + 1] == "SWE-bench/SWE-bench_Verified"

    def test_default_dataset_reads_module_constant_at_call_time(
        self, fake_run: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # docstring 承诺"可覆写模块常量"：默认值必须运行期读取，而非 def 期绑定。
        monkeypatch.setattr(repo_mod, "_OFFICIAL_HARNESS_DATASET", "SWE-bench/SWE-bench_Verified")
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        captured: dict[str, list[str]] = {}

        def _runner(cmd: list[str], _cwd: str, _timeout: int) -> subprocess.CompletedProcess[str]:
            captured["cmd"] = list(cmd)
            report_dir = Path(cmd[cmd.index("--report_dir") + 1])
            (report_dir / "r.json").write_text(
                json.dumps({"instance_id": _INSTANCE_ID, **_official_report(f2p_success=["a"], p2p_success=[])}),
                encoding="utf-8",
            )
            return _proc(0)

        fake_run["results"] = [_runner]  # type: ignore[index]
        assert (
            RepoExecutor(timeout=5, setup_timeout=5)._run_official_swebench_harness(
                _REPO_URL, _COMMIT, "", "", ["a"], [], instance_id=_INSTANCE_ID
            )
            is not None
        )
        assert captured["cmd"][captured["cmd"].index("--dataset_name") + 1] == "SWE-bench/SWE-bench_Verified"

    def test_run_id_is_filesystem_safe(self):
        weird = RepoExecutor._official_run_id("ab/cd:ef gh")
        assert weird == f"aitester-abcdefgh-{os.getpid()}-{repo_mod.threading.get_ident()}"

    def test_run_benchmark_passes_instance_id_into_verify(self):
        # run_benchmark 的 verify 调用点在批次主循环内（需完整数据集/LLM 工作流），
        # 此处锁源码接线：真实 instance_id 必须从 task.metadata 传给 verify。
        src = (Path(__file__).resolve().parents[1] / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        assert src.count('instance_id=task.metadata.get("instance_id")') == 1
        assert "executor_repo.verify(" in src

    def test_report_locator_depth_and_non_dict_guards(self):
        deep: object = {"instance_id": _INSTANCE_ID, **_official_report(f2p_success=["a"], p2p_success=[])}
        for _ in range(7):
            deep = {"nested": deep}
        assert RepoExecutor._official_report_candidate(deep, _INSTANCE_ID) is None, "递归限深防异常深报告树"
        assert RepoExecutor._official_report_candidate("not-a-dict", _INSTANCE_ID) is None
        # 浅层嵌套仍可定位（官方 run/model 目录层）
        shallow = {"run": {"model": {"instance_id": _INSTANCE_ID, **_official_report(f2p_success=["a"])}}}
        assert RepoExecutor._official_report_candidate(shallow, _INSTANCE_ID) is not None

    def test_run_id_empty_commit_falls_back_to_unknown(self):
        assert RepoExecutor._official_run_id("").startswith("aitester-unknown-")

    def test_verify_passes_real_instance_id_to_official_harness(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_official_harness_enabled", lambda: True)
        monkeypatch.setattr(ex, "_scan_repo_conftests", lambda _d: [])
        seen: dict[str, object] = {}

        def _fake_official(**kwargs):
            seen.update(kwargs)
            return {
                "passed": True,
                "output": "official",
                "harness_invalid": False,
                "fail_to_pass": {},
                "pass_to_pass": {},
            }

        monkeypatch.setattr(ex, "_run_official_swebench_harness", _fake_official)
        out = ex.verify(_REPO_URL, _COMMIT, "tp", "lp", ["t.py::a"], [], instance_id=_INSTANCE_ID)
        assert seen["instance_id"] == _INSTANCE_ID, "F11：verify 必须把真实 instance_id 透传到官方 harness"
        assert out["harness_source"] == "official_swebench"

    def test_verify_without_instance_id_degrades_to_self_built(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_official_harness_enabled", lambda: True)
        monkeypatch.setattr(ex, "_scan_repo_conftests", lambda _d: [])
        seen: dict[str, object] = {}

        def _fake_official(**kwargs):
            seen.update(kwargs)

        monkeypatch.setattr(ex, "_run_official_swebench_harness", _fake_official)
        monkeypatch.setattr(repo_mod, "_run", lambda _c, _w, _t, env=None: _proc(0))
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: True)
        monkeypatch.setattr(ex, "_apply_llm_patch", lambda _d, _p: True)
        legs = [
            {"expected": 1, "passed": 0, "failed_cases": [{"name": "a", "error": "boom"}]},
            {"expected": 1, "passed": 1, "failed_cases": []},
        ]
        monkeypatch.setattr(ex, "_run_fail_to_pass", lambda _d, _n, repo_url="": legs.pop(0))
        monkeypatch.setattr(
            ex, "_run_pass_to_pass", lambda _d, _n, repo_url="": {"expected": 1, "passed": 1, "failed_cases": []}
        )
        out = ex.verify(
            _REPO_URL, _COMMIT, "--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-x\n+y\n", "lp", ["t.py::a"], ["t.py::b"]
        )
        assert seen["instance_id"] is None, "缺 instance_id 时不得伪造"
        assert "harness_source" not in out, "官方降级后由自建口径裁决"
        assert out["passed"] is True
