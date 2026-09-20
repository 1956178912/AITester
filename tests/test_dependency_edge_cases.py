"""
src/tools/dependency.py 边界分支补充测试（优化轮次：覆盖率 90% → 99%+）。

补齐 test_dependency.py 未覆盖的分支：
- is_standard_library：缺失 stdlib_module_names 回退
- _is_importable_cached：缓存命中 / find_spec 异常
- create_venv：创建超时 / Windows 解释器路径回退
- _persist_cache_stats：OSError 静默降级
- list_venv_cache：非目录项跳过 / getsize 失败 / ctime 失败
- clear_venv_cache：rmtree 失败保留 / 目录缓存不存在早退
"""

import json
import os
import shutil
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import src.tools.dependency as dep


def _WrapPath(**overrides) -> types.ModuleType:
    """构造 os.path 的包装模块：仅覆盖指定函数，其余委托原实现。

    monkeypatch.setattr(os, "path", wrapper) 后，依赖模块内所有
    os.path.xxx 调用都会经过 wrapper，测试结束自动还原。
    """
    import ntpath
    import posixpath

    real = (sys.platform.startswith("win") and ntpath) or posixpath
    wrapper = types.ModuleType("os_path_wrapper")
    for name in dir(real):
        setattr(wrapper, name, getattr(real, name))
    for key, value in overrides.items():
        if key not in ("real_getctime",):
            setattr(wrapper, key, value)
    return wrapper


class TestIsStandardLibraryFallback:
    """is_standard_library 对缺失 sys.stdlib_module_names 解释器的回退。"""

    def test_missing_stdlib_names_returns_false(self, monkeypatch):
        monkeypatch.setattr(sys, "stdlib_module_names", None, raising=False)
        monkeypatch.setattr(dep, "sys", type("S", (), {"stdlib_module_names": None})())
        # getattr(sys, "stdlib_module_names", None) 为 None → 非标准解释器口径
        assert dep.is_standard_library("os") is False


class TestImportableCache:
    """_is_importable_cached 缓存与异常分支。"""

    def test_cache_hit_skips_find_spec(self, monkeypatch):
        module = "definitely_not_a_real_module_cache"
        monkeypatch.setitem(dep._importable_cache, module, True)
        with patch("importlib.util.find_spec") as mock_find:
            assert dep._is_importable_cached(module) is True
            mock_find.assert_not_called()

    def test_find_spec_exception_counts_as_missing(self, monkeypatch):
        module = "definitely_not_a_real_module_zzz_err"
        monkeypatch.delitem(dep._importable_cache, module, raising=False)
        with patch("importlib.util.find_spec", side_effect=ValueError("namespace package")):
            assert dep._is_importable_cached(module) is False
        # 异常结果同样写入缓存（避免重复探测）
        assert dep._importable_cache[module] is False


class TestCreateVvenvEdgeCases:
    """create_venv 超时与解释器路径回退。"""

    @patch("src.tools.dependency.subprocess.run")
    def test_create_venv_timeout_raises(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="venv", timeout=5)
        with pytest.raises(RuntimeError, match="超时"):
            dep.create_venv(str(tmp_path), timeout=5)

    @patch("src.tools.dependency.subprocess.run")
    def test_create_venv_falls_back_to_windows_interpreter(self, mock_run, tmp_path, monkeypatch):
        """unix 解释器路径不存在时回退到 Scripts/python.exe。"""
        mock_run.return_value = type("P", (), {"returncode": 0, "stderr": ""})
        win_dir = tmp_path / "Scripts"
        win_dir.mkdir()
        (win_dir / "python.exe").write_text("")
        result = dep.create_venv(str(tmp_path))
        assert result == str(win_dir / "python.exe")


class TestPersistCacheStatsOSError:
    """_persist_cache_stats 落盘失败静默降级（不影响主流程）。"""

    def test_persist_oserror_swallowed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "venvs"))
        # 统计文件路径指向只读目录（POSIX）→ open 抛 PermissionError(OSError)
        ro_dir = tmp_path / "ro"
        ro_dir.mkdir()
        os.chmod(ro_dir, 0o555)
        try:
            monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(ro_dir))
            dep._venv_cache_stats["hits"] = 1
            # 不应抛出
            dep._persist_cache_stats()
        finally:
            os.chmod(ro_dir, 0o755)


class TestListVenvCacheEdgeCases:
    """list_venv_cache 的异常分支。"""

    @pytest.fixture
    def cache_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "venvs"))
        return tmp_path / "venvs"

    def test_non_dir_entries_skipped(self, cache_dir):
        cache_dir.mkdir()
        (cache_dir / "plain_file.txt").write_text("x")
        entries = dep.list_venv_cache()
        assert entries == []

    def test_getsize_failure_ignored(self, cache_dir, monkeypatch):
        """os.path.getsize 抛 OSError 的文件被跳过（size_mb 记 0）。"""
        cache_dir.mkdir()
        venv = cache_dir / "abc_hash_pkg"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")
        real_getsize = os.path.getsize

        def fake_getsize(path, *args, **kwargs):
            if str(path).endswith("python"):
                raise OSError("concurrent delete")
            return real_getsize(path)

        monkeypatch.setattr(os, "path", _WrapPath(getsize=fake_getsize))
        entries = dep.list_venv_cache()
        assert len(entries) == 1
        assert entries[0]["size_mb"] == 0.0

    def test_getctime_failure_returns_unknown(self, cache_dir, monkeypatch):
        """os.path.getctime 抛 OSError 时 created_at 记 "unknown"。"""
        cache_dir.mkdir()
        venv = cache_dir / "abc_hash_pkg"
        (venv / "bin").mkdir(parents=True)
        real_getctime = os.path.getctime

        def fake_getctime(path, *args, **kwargs):
            raise OSError("stat failed")

        monkeypatch.setattr(os, "path", _WrapPath(getctime=fake_getctime, real_getctime=real_getctime))
        entries = dep.list_venv_cache()
        assert entries[0]["created_at"] == "unknown"


class TestClearVenvCacheEdgeCases:
    """clear_venv_cache 的保留分支。"""

    @pytest.fixture
    def cache_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "venvs"))
        return tmp_path / "venvs"

    def test_missing_cache_dir_returns_empty(self, cache_dir):
        result = dep.clear_venv_cache()
        assert result == {"removed": [], "kept": [], "freed_mb": 0.0}

    def test_rmtree_failure_kept(self, cache_dir, monkeypatch):
        venv = cache_dir / "locked"
        (venv / "bin").mkdir(parents=True)
        monkeypatch.setattr(shutil, "rmtree", MagicMock(side_effect=OSError("locked")))
        result = dep.clear_venv_cache()
        assert "locked" in result["kept"]
        assert result["removed"] == []


class TestVenvCacheDirWindows:
    """venv_cache_dir 路径确定性（Windows 候选解释器）。"""

    def test_same_input_same_path(self):
        assert dep.venv_cache_dir(["x"]) == dep.venv_cache_dir(["x"])


def _write_stats_file(path: str, hits: int, creates: int) -> None:
    """辅助：写入落盘统计 JSON。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"hits": hits, "creates": creates}, f)


class TestLoadCacheStatsCorrupted:
    """_load_cache_stats 对损坏/非法 JSON 的兜底（零值）。"""

    def test_corrupted_json_returns_zero(self, tmp_path, monkeypatch):
        stats_file = tmp_path / "stats.json"
        stats_file.write_text("{not valid json")
        # 4.4 改进：_venv_cache_stats_file 动态读 _VENV_CACHE_DIR，
        # 设缓存目录为 stats_file 的父目录使路径一致
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path))
        assert dep._load_cache_stats() == {"hits": 0, "creates": 0, "last_event_at": None}

    def test_non_dict_json_returns_zero(self, tmp_path, monkeypatch):
        stats_file = tmp_path / "stats.json"
        stats_file.write_text("[1, 2, 3]")
        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path))
        assert dep._load_cache_stats() == {"hits": 0, "creates": 0, "last_event_at": None}
