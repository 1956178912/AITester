"""tools/dependency 纯静态 import 提取 / 白名单 / 缺失判定分支补齐（2026-10-02 批次·五）。

锁定 dependency.py 零 LLM / 零网络 / 零 venv 的纯逻辑分支：
- extract_import_module_names / extract_imported_modules（import 形式捕获）
- is_standard_library（stdlib 清单判定）
- find_missing_modules（stdlib / 本地文件 / 缺失 三类判定）
- suggest_package_names（映射 + 白名单守卫）
"""

from __future__ import annotations


class TestExtractImportedModulesBranches:
    def test_import_clause_multiple(self):
        from src.tools.dependency import extract_imported_modules

        out = extract_imported_modules("import numpy, scipy\n")
        assert "numpy" in out
        assert "scipy" in out

    def test_from_import(self):
        from src.tools.dependency import extract_imported_modules

        out = extract_imported_modules("from collections import OrderedDict\n")
        assert "collections" in out

    def test_import_as_alias(self):
        from src.tools.dependency import extract_imported_modules

        out = extract_imported_modules("import numpy as np\n")
        assert "numpy" in out

    def test_submodule_maps_to_top_level(self):
        from src.tools.dependency import extract_imported_modules

        out = extract_imported_modules("from os.path import join\n")
        # 顶层模块名（取点分首段）
        assert "os" in out

    def test_no_imports_empty(self):
        from src.tools.dependency import extract_imported_modules

        assert extract_imported_modules("x = 1\n") == set()


class TestIsStandardLibraryBranches:
    def test_stdlib_module(self):
        from src.tools.dependency import is_standard_library

        assert is_standard_library("os") is True
        assert is_standard_library("sys") is True

    def test_non_stdlib_module(self):
        from src.tools.dependency import is_standard_library

        assert is_standard_library("numpy") is False
        assert is_standard_library("totally_not_a_module") is False


class TestFindMissingModulesBranches:
    def test_stdlib_not_missing(self):
        from src.tools.dependency import find_missing_modules

        out = find_missing_modules({"os", "sys"})
        assert "os" not in out
        assert "sys" not in out

    def test_local_file_not_missing(self, tmp_path):
        from src.tools.dependency import find_missing_modules

        # 本地文件 module_name 与文件名匹配 → 视为本地可用
        local_file = tmp_path / "local_mod.py"
        local_file.write_text("x = 1\n")
        out = find_missing_modules({"local_mod"}, extra_search_files=[str(local_file)])
        assert "local_mod" not in out

    def test_unknown_module_missing(self):
        from src.tools.dependency import find_missing_modules

        out = find_missing_modules({"definitely_missing_module_xyz"})
        assert "definitely_missing_module_xyz" in out

    def test_empty_input_returns_empty(self):
        from src.tools.dependency import find_missing_modules

        assert find_missing_modules(set()) == set()


class TestSuggestPackageNamesBranches:
    def test_default_now_enforces_builtin_whitelist(self, monkeypatch):
        """C-08（2026-10-09 审查修订）：白名单默认开——未设置环境变量时
        走内置 `_PIP_PACKAGE_WHITELIST`（~40 常见包）过滤，未知包名被拒。"""
        from src.tools.dependency import suggest_package_names

        monkeypatch.delenv("PIP_PACKAGE_WHITELIST_ENABLE", raising=False)
        monkeypatch.delenv("PIP_PACKAGE_WHITELIST", raising=False)
        out = suggest_package_names({"numpy", "totally_hallucinated_pkg"})
        assert "numpy" in out
        assert "totally_hallucinated_pkg" not in out

    def test_default_off_preserves_legacy_passthrough(self, monkeypatch):
        """显式 PIP_PACKAGE_WHITELIST_ENABLE=false 退回历史口径（调试场景）。"""
        from src.tools.dependency import suggest_package_names

        monkeypatch.setenv("PIP_PACKAGE_WHITELIST_ENABLE", "false")
        monkeypatch.delenv("PIP_PACKAGE_WHITELIST", raising=False)
        out = suggest_package_names({"PIL", "totally_hallucinated_pkg"})
        # PIL → pillow 映射；未知名默认放行（历史行为）
        assert "pillow" in out
        assert "totally_hallucinated_pkg" in out

    def test_stdlib_excluded(self, monkeypatch):
        from src.tools.dependency import suggest_package_names

        monkeypatch.delenv("PIP_PACKAGE_WHITELIST_ENABLE", raising=False)
        out = suggest_package_names({"os", "numpy"})
        # os 是 stdlib → 排除（白名单开与关口径一致）
        assert "os" not in out
        assert "numpy" in out

    def test_whitelist_filters_unknown(self, monkeypatch):
        from src.tools.dependency import suggest_package_names

        monkeypatch.setenv("PIP_PACKAGE_WHITELIST_ENABLE", "true")
        monkeypatch.setenv("PIP_PACKAGE_WHITELIST", "numpy,pandas")
        out = suggest_package_names({"numpy", "some_unknown_pkg"})
        assert "numpy" in out
        assert "some_unknown_pkg" not in out

    def test_whitelist_rejects_all_unknown(self, monkeypatch):
        from src.tools.dependency import suggest_package_names

        monkeypatch.setenv("PIP_PACKAGE_WHITELIST_ENABLE", "true")
        monkeypatch.setenv("PIP_PACKAGE_WHITELIST", "numpy")
        out = suggest_package_names({"some_unknown_pkg"})
        assert out == []
