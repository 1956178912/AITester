"""
src/tools/dependency.py 单元测试（P1：依赖检测与隔离执行）。

覆盖：
- extract_imported_modules 的两种 import 语句与相对导入排除
- find_missing_modules 的 stdlib/已安装/项目内/缺失判定
- suggest_package_names 的模块名→包名映射
- create_venv / install_packages / venv_cache_dir（mock subprocess）
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.dependency import (
    create_venv,
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
