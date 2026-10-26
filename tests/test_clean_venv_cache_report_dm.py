"""DM 轮：clean-venv-cache 的报告必须与真实磁盘结果一致。

修复前实测（2026-10-26，macOS，非 root）：
1. 缓存目录只读（0o500）时 ``clear_venv_cache()`` 仍返回 ``removed=["locked_venv"]``，
   CLI 打印「✓ 已删除 1 个 venv（释放 0.0 MB）：locked_venv」且 rc=0——目录原封不动。
   根因是 ``shutil.rmtree(full, ignore_errors=True)`` 永不抛出，后面的
   ``except OSError`` 是死分支；旧测试用 MagicMock 让 rmtree 主动 raise，锁住的是
   错误契约（mock 形态掩盖了真实行为）。
2. ``--list-only --max-age-days 30`` / ``--max-size-mb 0`` 仍列出全部条目：过滤条件
   被静默忽略，预览名单与实际删除名单不一致。

本文件用真实权限失败（不 mock rmtree）与真实 mtime/大小构造断言。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

import src.tools.dependency as dep
from src.cli import app as cli_app


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    path = tmp_path / "venvs"
    path.mkdir()
    monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(path))
    return path


def _make_venv(cache: Path, name: str, payload: bytes = b"x") -> Path:
    venv = cache / name
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_bytes(payload)
    return venv


def _age(path: Path, days: float) -> None:
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def _invoke(*args: str):
    return CliRunner().invoke(cli_app.cli, ["clean-venv-cache", *args])


class TestDeletionFailureIsReported:
    """删除失败不得被计为已删除。"""

    def test_real_rmtree_failure_not_counted_as_removed(self, cache_dir):
        _make_venv(cache_dir, "locked_venv", b"x" * 4096)
        os.chmod(cache_dir, 0o500)
        try:
            result = dep.clear_venv_cache()
            assert result["removed"] == []
            assert result["failed"] == ["locked_venv"]
            assert result["freed_mb"] == 0.0
            assert (cache_dir / "locked_venv").is_dir(), "目录仍在就说明删除失败"
        finally:
            os.chmod(cache_dir, 0o700)

    def test_cli_reports_failure_and_exits_nonzero(self, cache_dir):
        _make_venv(cache_dir, "locked_venv", b"x" * 4096)
        os.chmod(cache_dir, 0o500)
        try:
            r = _invoke()
        finally:
            os.chmod(cache_dir, 0o700)
        assert r.exit_code == 1, r.output
        assert "已删除" not in r.output
        assert "没有符合条件" not in r.output
        assert "删除失败" in r.output and "locked_venv" in r.output

    def test_partial_failure_separates_removed_from_failed(self, cache_dir):
        _make_venv(cache_dir, "ok_venv", b"x" * (1024 * 1024))
        stuck = _make_venv(cache_dir, "stuck_venv", b"x" * 1024)
        inner = stuck / "lib"
        inner.mkdir()
        (inner / "payload.bin").write_bytes(b"y")
        os.chmod(inner, 0o500)
        try:
            result = dep.clear_venv_cache()
        finally:
            os.chmod(inner, 0o700)
        assert result["removed"] == ["ok_venv"]
        assert result["failed"] == ["stuck_venv"]
        assert result["kept"] == []
        assert 0.9 < result["freed_mb"] < 1.2, "只应计入真正删掉的目录大小"

    def test_cli_success_still_reports_removed(self, cache_dir):
        _make_venv(cache_dir, "venv_a", b"x" * (1024 * 1024))
        r = _invoke()
        assert r.exit_code == 0, r.output
        assert "已删除 1 个 venv" in r.output
        assert not (cache_dir / "venv_a").exists()


class TestListOnlyRespectsFilters:
    """--list-only 的预览名单必须与实删名单同源。"""

    def test_preview_matches_actual_removal_by_age(self, cache_dir):
        _age(_make_venv(cache_dir, "old_venv"), 10)
        _make_venv(cache_dir, "fresh_venv")
        preview = dep.preview_venv_cache_cleanup(max_age_days=7)
        flags = {e["name"]: e["would_remove"] for e in preview}
        assert flags == {"old_venv": True, "fresh_venv": False}
        assert (cache_dir / "old_venv").is_dir(), "预览不得删除"
        result = dep.clear_venv_cache(max_age_days=7)
        assert result["removed"] == [e["name"] for e in preview if e["would_remove"]]
        assert result["kept"] == [e["name"] for e in preview if not e["would_remove"]]

    def test_preview_matches_actual_removal_by_size(self, cache_dir):
        _make_venv(cache_dir, "big_venv", b"x" * (2 * 1024 * 1024))
        _make_venv(cache_dir, "small_venv", b"x")
        preview = dep.preview_venv_cache_cleanup(max_size_mb=1)
        flags = {e["name"]: e["would_remove"] for e in preview}
        assert flags == {"big_venv": True, "small_venv": False}
        assert (cache_dir / "big_venv").is_dir(), "预览不得删除"

    def test_cli_list_only_respects_age_filter(self, cache_dir):
        _age(_make_venv(cache_dir, "old_venv"), 10)
        _make_venv(cache_dir, "fresh_venv")
        r = _invoke("--list-only", "--max-age-days", "7")
        assert r.exit_code == 0, r.output
        assert "[将删除] old_venv" in r.output, r.output
        assert "[保留] fresh_venv" in r.output, r.output
        assert (cache_dir / "old_venv").is_dir() and (cache_dir / "fresh_venv").is_dir()

    def test_cli_list_only_without_filters_keeps_plain_listing(self, cache_dir):
        _make_venv(cache_dir, "venv_a")
        _make_venv(cache_dir, "venv_b")
        r = _invoke("--list-only")
        assert r.exit_code == 0, r.output
        assert "venv 缓存共 2 项" in r.output
        assert "将删除" not in r.output
