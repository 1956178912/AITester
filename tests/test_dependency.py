"""
src/tools/dependency.py 单元测试（P1：依赖检测与隔离执行）。

覆盖：
- extract_imported_modules 的两种 import 语句与相对导入排除
- find_missing_modules 的 stdlib/已安装/项目内/缺失判定
- suggest_package_names 的模块名→包名映射
- create_venv / install_packages / venv_cache_dir（mock subprocess）
- 4.4 venv 缓存监控（命中率统计 / 列表 / 清理）
"""

import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.dependency import (
    create_venv,
    extract_import_module_names,
    extract_imported_modules,
    find_missing_modules,
    install_packages,
    is_standard_library,
    suggest_package_names,
    venv_cache_dir,
)


class TestExtractImportedModules:
    """extract_imported_modules 行为。"""

    def test_plain_import(self):
        assert extract_imported_modules("import os\nimport sys\n") == {"os", "sys"}

    def test_from_import(self):
        assert extract_imported_modules("from collections import OrderedDict") == {"collections"}

    def test_dotted_top_level(self):
        assert extract_imported_modules("import numpy.core") == {"numpy"}

    def test_relative_import_skipped(self):
        assert extract_imported_modules("from . import utils\n") == set()

    def test_as_alias_ignored(self):
        # "import numpy as np" → 模块名仍是 numpy
        assert extract_imported_modules("import numpy as np") == {"numpy"}

    def test_empty(self):
        assert extract_imported_modules("") == set()

    def test_multiline_from_import(self):
        code = "from os import (\n    path,\n    sep,\n)\n"
        assert "os" in extract_imported_modules(code)

    def test_comma_import_all_modules_captured(self):
        """逗号分隔多模块导入（import numpy, scipy）须完整捕获。

        回归：旧实现的正则 ^import\\s+(\\w+\\.)? 只取首个模块名，
        scipy 会逃过缺失依赖检测，venv 里少装包导致测试 ImportError。
        """
        assert extract_imported_modules("import numpy, scipy\n") == {"numpy", "scipy"}
        assert extract_imported_modules("import numpy, scipy, os\n") == {"numpy", "scipy", "os"}


class TestExtractImportModuleNames:
    """extract_import_module_names 共享实现（executor 导入修复同源复用）。"""

    def test_plain_single(self):
        assert extract_import_module_names("import os\n") == ["os"]

    def test_comma_list(self):
        assert extract_import_module_names("import a, b.c, d\n") == ["a", "b.c", "d"]

    def test_as_alias_dropped(self):
        assert extract_import_module_names("import numpy as np") == ["numpy"]
        assert extract_import_module_names("import a.b as x, c\n") == ["a.b", "c"]

    def test_trailing_comment_stripped(self):
        assert extract_import_module_names("import os, sys  # 注释\n") == ["os", "sys"]

    def test_from_import(self):
        assert extract_import_module_names("from collections import OrderedDict") == ["collections"]

    def test_relative_imports_skipped(self):
        assert extract_import_module_names("from . import utils\nfrom ..pkg import x\n") == []

    def test_multiline_paren_from(self):
        code = "from os import (\n    path,\n    sep,\n)\n"
        assert "os" in extract_import_module_names(code)


class TestIsStandardLibrary:
    """is_standard_library 判定。"""

    def test_stdlib_modules(self):
        assert is_standard_library("os")
        assert is_standard_library("json")
        assert is_standard_library("dataclasses")

    def test_third_party_not_stdlib(self):
        assert not is_standard_library("pandas")
        assert not is_standard_library("torch")


class TestFindMissingModules:
    """find_missing_modules 判定链。"""

    def test_stdlib_never_missing(self):
        assert find_missing_modules({"os", "sys", "re"}) == set()

    def test_installed_module_not_missing(self):
        # pytest 是项目锁定依赖，测试进程中必然可导入
        assert "pytest" not in find_missing_modules({"pytest"})

    def test_project_file_module_not_missing(self):
        missing = find_missing_modules({"calculator"}, extra_search_files=["/tmp/calculator.py"])
        assert "calculator" not in missing

    def test_fake_module_missing(self):
        missing = find_missing_modules({"definitely_not_a_real_module_zzz"})
        assert "definitely_not_a_real_module_zzz" in missing

    def test_project_module_wins_over_missing(self):
        # 项目自带同名模块优先视为可用（即使 pip 也有同名包）
        missing = find_missing_modules({"logging"}, extra_search_files=["/tmp/logging.py"])
        assert "logging" not in missing


class TestSuggestPackageNames:
    """suggest_package_names 映射。"""

    def test_known_module_to_package(self):
        assert suggest_package_names({"PIL"}) == ["pillow"]
        assert suggest_package_names({"cv2"}) == ["opencv-python-headless"]
        assert suggest_package_names({"yaml"}) == ["pyyaml"]

    def test_unknown_module_identity(self):
        # 未知模块默认"模块名即包名"
        assert suggest_package_names({"somepkg"}) == ["somepkg"]

    def test_stdlib_excluded(self):
        # 标准库模块不应产生安装建议
        assert suggest_package_names({"os"}) == []

    def test_sorted_dedup(self):
        result = suggest_package_names({"zeta", "alpha"})
        assert result == ["alpha", "zeta"]


class TestVenvCacheDir:
    """venv_cache_dir 确定性。"""

    def test_same_packages_same_dir(self):
        a = venv_cache_dir(["pandas", "numpy"])
        b = venv_cache_dir(["numpy", "pandas"])
        assert a == b  # 排序后 hash 一致

    def test_different_packages_different_dir(self):
        assert venv_cache_dir(["pandas"]) != venv_cache_dir(["numpy"])

    def test_label_truncated(self):
        """目录名标签部分限长 40 字符，避免包名过长撑爆路径。"""
        d = venv_cache_dir(["a_very_long_package_name_x" * 5])
        label = os.path.basename(d).split("_", 1)[1]  # 去掉 hash 前缀
        assert len(label) <= 40


class TestCreateVenv:
    """create_venv / install_packages（mock 子进程）。"""

    @patch("src.tools.dependency.subprocess.run")
    def test_create_venv_runs_python_module(self, mock_run, tmp_path):
        mock_run.return_value = type("P", (), {"returncode": 0, "stderr": ""})
        # 预置解释器文件避免走真实创建
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        py = bin_dir / "python"
        py.write_text("")
        result = create_venv(str(tmp_path))
        assert result == str(py)
        # 复用语义：已有解释器时不应调用 subprocess
        mock_run.assert_not_called()

    @patch("src.tools.dependency.subprocess.run")
    def test_create_venv_creates_when_missing(self, mock_run, tmp_path):
        mock_run.return_value = type("P", (), {"returncode": 0, "stderr": ""})
        create_venv(str(tmp_path))
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "venv" in cmd and "--system-site-packages" in cmd

    @patch("src.tools.dependency.subprocess.run")
    def test_create_venv_failure_raises(self, mock_run, tmp_path):
        mock_run.return_value = type("P", (), {"returncode": 1, "stderr": "boom"})
        import pytest

        with pytest.raises(RuntimeError):
            create_venv(str(tmp_path))

    @patch("src.tools.dependency.subprocess.run")
    def test_install_packages_success(self, mock_run):
        mock_run.return_value = type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})
        ok, _ = install_packages("/venv/bin/python", ["pandas"])
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert "pip" in " ".join(cmd) and "pandas" in cmd

    @patch("src.tools.dependency.subprocess.run")
    def test_install_packages_no_packages_noop(self, mock_run):
        ok, out = install_packages("/venv/bin/python", [])
        assert ok is True and out == ""
        mock_run.assert_not_called()

    @patch("src.tools.dependency.subprocess.run")
    def test_install_packages_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=10)
        ok, detail = install_packages("/venv/bin/python", ["pandas"], timeout=10)
        assert ok is False
        assert "超时" in detail


class TestVenvCacheMonitoring:
    """4.4 依赖缓存监控：命中率统计 / 列表 / 清理（仅新增函数，不改 create_venv 复用行为）"""

    @pytest.fixture(autouse=True)
    def _isolate_cache_dir(self, tmp_path, monkeypatch):
        """把缓存目录指向 tmp_path，避免污染真实 ~/.cache/aitester/venvs。"""
        import src.tools.dependency as dep

        monkeypatch.setattr(dep, "_VENV_CACHE_DIR", str(tmp_path / "venvs"))
        monkeypatch.setattr(dep, "_VENV_CACHE_STATS_FILE", str(tmp_path / "venvs" / "cache_stats.json"))
        # 重置进程内统计
        with dep._venv_cache_stats_lock:
            dep._venv_cache_stats["hits"] = 0
            dep._venv_cache_stats["creates"] = 0
            dep._venv_cache_stats["last_event_at"] = None
        self.dep = dep

    def _make_venv_dir(self, name: str, size_bytes: int = 1024) -> str:
        """在缓存目录下创建一个模拟 venv（含 bin/python 文件 + 占位数据）。"""
        import os
        import src.tools.dependency as dep

        full = os.path.join(dep._VENV_CACHE_DIR, name)
        os.makedirs(os.path.join(full, "bin"), exist_ok=True)
        with open(os.path.join(full, "bin", "python"), "wb") as f:
            f.write(b"\x7fELF")
        with open(os.path.join(full, "data.bin"), "wb") as f:
            f.write(b"0" * size_bytes)
        return full

    def test_get_venv_cache_stats_initial_zero(self):
        stats = self.dep.get_venv_cache_stats()
        assert stats["total"] == 0
        assert stats["hit_rate"] == 0.0

    def test_get_venv_cache_stats_after_events(self):
        self.dep._record_venv_cache_event("hit")
        self.dep._record_venv_cache_event("hit")
        self.dep._record_venv_cache_event("create")
        stats = self.dep.get_venv_cache_stats()
        assert stats["hits"] == 2
        assert stats["creates"] == 1
        assert stats["total"] == 3
        assert stats["hit_rate"] == round(2 / 3, 4)

    def test_list_venv_cache_empty_when_no_dir(self):
        assert self.dep.list_venv_cache() == []

    def test_list_venv_cache_returns_entries(self):
        self._make_venv_dir("abc_hash_pkg", size_bytes=100)
        entries = self.dep.list_venv_cache()
        assert len(entries) == 1
        assert entries[0]["name"] == "abc_hash_pkg"
        assert entries[0]["size_mb"] >= 0.0

    def test_clear_venv_cache_all(self):
        self._make_venv_dir("old1")
        self._make_venv_dir("old2")
        result = self.dep.clear_venv_cache()
        assert sorted(result["removed"]) == ["old1", "old2"]
        assert result["kept"] == []
        assert self.dep.list_venv_cache() == []

    def test_clear_venv_cache_by_age(self):
        import os
        import src.tools.dependency as dep

        old = self._make_venv_dir("old")
        past = dep.time.time() - 10 * 86400
        os.utime(old, (past, past))
        self._make_venv_dir("fresh")

        result = self.dep.clear_venv_cache(max_age_days=7)
        assert "old" in result["removed"]
        assert "fresh" in result["kept"]

    def test_clear_venv_cache_by_size(self):
        self._make_venv_dir("big", size_bytes=10 * 1024 * 1024)
        self._make_venv_dir("small", size_bytes=100)
        result = self.dep.clear_venv_cache(max_size_mb=1)
        assert "big" in result["removed"]
        assert "small" in result["kept"]

    def test_create_venv_records_hit_on_reuse(self):
        """create_venv 复用已存在 venv 时记录 hit 事件（4.4 命中率统计）。"""
        import os
        import src.tools.dependency as dep

        full = self._make_venv_dir("hash_pkg")
        stats_before = dep.get_venv_cache_stats()["hits"]
        interpreter = dep.create_venv(full)
        assert os.path.exists(interpreter)
        stats_after = dep.get_venv_cache_stats()["hits"]
        assert stats_after == stats_before + 1
