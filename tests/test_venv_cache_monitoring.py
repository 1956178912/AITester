"""
4.4 venv 缓存监控与容量告警单元测试。

覆盖：
- get_venv_cache_size_mb（目录不存在 / 存在）；
- check_venv_cache_size 容量告警（未超限 / 超限）；
- get_venv_cache_stats 命中率计算（hits/creates/total/hit_rate）；
- clear_venv_cache 全量清理与按年龄/大小过滤。
"""

from __future__ import annotations

import os

import pytest

import src.tools.dependency as dep


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """把 _VENV_CACHE_DIR 指向临时目录（隔离测试，不碰真实 ~/.cache）。"""
    cache_dir = tmp_path / "venv_cache"
    cache_dir.mkdir()
    monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(cache_dir))
    # 同步重置进程内统计（避免跨测试污染）
    monkeypatch.setattr(dep, "_venv_cache_stats", {"hits": 0, "creates": 0, "last_event_at": None})
    # 0.7 债务项 2.4：重置落盘节流状态，确保每个测试的首个事件必落盘
    # （否则节流窗口会跨测试残留，导致落盘断言被跳过）
    monkeypatch.setattr(dep, "_venv_cache_last_persist_at", None)
    # 重置落盘统计文件
    stats_file = os.path.join(str(cache_dir), "cache_stats.json")
    if os.path.exists(stats_file):
        os.unlink(stats_file)
    yield cache_dir


class TestGetVenvCacheSizeMb:
    """缓存目录大小统计。"""

    def test_nonexistent_dir_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "no_such_dir"))
        assert dep.get_venv_cache_size_mb() == 0.0

    def test_existing_dir_returns_size(self, _isolated_cache_dir):
        # 创建一个 1KB 文件
        f = _isolated_cache_dir / "f1"
        f.write_bytes(b"x" * 1024)
        size = dep.get_venv_cache_size_mb()
        assert size > 0.0
        assert size < 0.001  # 1KB 远小于 1MB


class TestCheckVenvCacheSize:
    """容量告警检查。"""

    def test_below_threshold_no_warning(self, _isolated_cache_dir):
        # 默认阈值 5120MB，小缓存不应触发告警
        result = dep.check_venv_cache_size()
        assert result["exceeded"] is False
        assert result["recommendation"] == ""
        assert result["threshold_mb"] == dep._VENV_CACHE_SIZE_WARN_MB
        assert result["size_mb"] >= 0.0

    def test_exceeds_threshold_triggers_recommendation(self, _isolated_cache_dir, monkeypatch):
        # 把阈值调到 0.001MB（1KB），放一个 2KB 文件 → 超限
        monkeypatch.setattr(dep, "_VENV_CACHE_SIZE_WARN_MB", 0.001)
        (_isolated_cache_dir / "f1").write_bytes(b"x" * 2048)
        result = dep.check_venv_cache_size()
        assert result["exceeded"] is True
        assert "clear_venv_cache" in result["recommendation"]


class TestGetVenvCacheStats:
    """命中率统计。"""

    def test_no_events_returns_zero_hit_rate(self, _isolated_cache_dir):
        stats = dep.get_venv_cache_stats()
        assert stats["hits"] == 0
        assert stats["creates"] == 0
        assert stats["total"] == 0
        assert stats["hit_rate"] == 0.0

    def test_record_hit_computes_rate(self, _isolated_cache_dir):
        # 记录 1 hit + 1 create → hit_rate = 0.5
        dep._record_venv_cache_event("hit")
        dep._record_venv_cache_event("create")
        stats = dep.get_venv_cache_stats()
        assert stats["hits"] == 1
        assert stats["creates"] == 1
        assert stats["total"] == 2
        assert stats["hit_rate"] == 0.5

    def test_persist_stats_to_disk(self, _isolated_cache_dir):
        dep._record_venv_cache_event("hit")
        # 持久化文件应存在
        stats_file = _isolated_cache_dir / "cache_stats.json"
        assert stats_file.exists()


class TestClearVenvCache:
    """缓存清理。"""

    def test_clear_all_when_no_filters(self, _isolated_cache_dir):
        for i in range(3):
            d = _isolated_cache_dir / f"venv_{i}"
            d.mkdir()
            # 每个 venv 写 1MB 文件（round(freed_mb, 2) 后 > 0）
            (d / "a.py").write_bytes(b"x" * 1024 * 1024)
        result = dep.clear_venv_cache()
        assert len(result["removed"]) == 3
        assert result["kept"] == []
        assert result["freed_mb"] > 0.0

    def test_clear_by_max_age(self, _isolated_cache_dir, monkeypatch):
        old = _isolated_cache_dir / "old"
        old.mkdir()
        new = _isolated_cache_dir / "new"
        new.mkdir()
        # 把 old 的 mtime 调到 10 天前
        import time as _time

        ten_days_ago = _time.time() - 10 * 86400
        os.utime(old, (ten_days_ago, ten_days_ago))
        result = dep.clear_venv_cache(max_age_days=7)
        assert "old" in result["removed"]
        assert "new" in result["kept"]

    def test_clear_by_max_size(self, _isolated_cache_dir):
        small = _isolated_cache_dir / "small"
        small.mkdir()
        big = _isolated_cache_dir / "big"
        big.mkdir()
        (small / "a.py").write_text("x")
        # 大目录：写 2MB
        (big / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
        result = dep.clear_venv_cache(max_size_mb=1)
        assert "big" in result["removed"]
        assert "small" in result["kept"]

    def test_clear_nonexistent_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "no_such_dir"))
        result = dep.clear_venv_cache()
        assert result["removed"] == []
        assert result["kept"] == []
        assert result["freed_mb"] == 0.0
