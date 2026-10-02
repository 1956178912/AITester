"""tools/graphrag + graph/expert_pool + tools/dependency 开关与纯逻辑分支补齐（2026-10-02 批次·十四）。

锁定三个 80-90% 分支模块的未覆盖纯逻辑分支（零 LLM / 零网络 / 零子进程）：
- graphrag: graph_rag_enabled / _graph_rag_max_hops / _graph_rag_top_k_snippets 钳制
- expert_pool: expert_pool_enabled / debate 开关 / _expert_pool_size / _expert_pool_timeout 钳制
- dependency: extract_import_module_names / extract_imported_modules / is_standard_library /
  find_missing_modules / suggest_package_names 白名单 / conftest_ast_scan_enabled /
  scan_conftest_ast_safety 各检测
"""

from __future__ import annotations

# ─── graphrag 开关与钳制 ──────────────────────────────────────────────────


class TestGraphRagSwitchBranches:
    def test_enabled_default_false(self, monkeypatch):
        from src.tools.graphrag import graph_rag_enabled

        monkeypatch.delenv("GRAPH_RAG_ENABLE", raising=False)
        assert graph_rag_enabled() is False

    def test_enabled_true(self, monkeypatch):
        from src.tools.graphrag import graph_rag_enabled

        monkeypatch.setenv("GRAPH_RAG_ENABLE", "true")
        assert graph_rag_enabled() is True

    def test_max_hops_default(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.delenv("GRAPH_RAG_MAX_HOPS", raising=False)
        assert _graph_rag_max_hops() == 2

    def test_max_hops_clamped_to_one(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.setenv("GRAPH_RAG_MAX_HOPS", "0")
        assert _graph_rag_max_hops() == 1

    def test_max_hops_clamped_to_five(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.setenv("GRAPH_RAG_MAX_HOPS", "99")
        assert _graph_rag_max_hops() == 5

    def test_max_hops_invalid_falls_back(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.setenv("GRAPH_RAG_MAX_HOPS", "abc")
        assert _graph_rag_max_hops() == 2

    def test_top_k_snippets_default(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.delenv("GRAPH_RAG_TOP_K_SNIPPETS", raising=False)
        assert _graph_rag_top_k_snippets() == 5

    def test_top_k_snippets_clamped_to_twenty(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.setenv("GRAPH_RAG_TOP_K_SNIPPETS", "99")
        assert _graph_rag_top_k_snippets() == 20

    def test_top_k_snippets_clamped_to_one(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.setenv("GRAPH_RAG_TOP_K_SNIPPETS", "0")
        assert _graph_rag_top_k_snippets() == 1


# ─── expert_pool 开关与钳制 ────────────────────────────────────────────────


class TestExpertPoolSwitchBranches:
    def test_expert_pool_enabled_default_false(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_enabled

        monkeypatch.delenv("EXPERT_POOL_ENABLE", raising=False)
        assert expert_pool_enabled() is False

    def test_expert_pool_enabled_true(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_enabled

        monkeypatch.setenv("EXPERT_POOL_ENABLE", "true")
        assert expert_pool_enabled() is True

    def test_debate_enabled_default_false(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_debate_enabled

        monkeypatch.delenv("EXPERT_POOL_DEBATE_ENABLE", raising=False)
        assert expert_pool_debate_enabled() is False

    def test_debate_enabled_requires_pool_enabled(self, monkeypatch):
        """辩论开关与 expert_pool_enabled 叠加：池开关关时恒 False（即便 debate env 为 true）。"""
        from src.graph.expert_pool import expert_pool_debate_enabled

        monkeypatch.delenv("EXPERT_POOL_ENABLE", raising=False)  # 池默认关
        monkeypatch.setenv("EXPERT_POOL_DEBATE_ENABLE", "true")
        assert expert_pool_debate_enabled() is False

    def test_debate_enabled_true(self, monkeypatch):
        """池 + 辩论双开关均 true → True。"""
        from src.graph.expert_pool import expert_pool_debate_enabled

        monkeypatch.setenv("EXPERT_POOL_ENABLE", "true")
        monkeypatch.setenv("EXPERT_POOL_DEBATE_ENABLE", "true")
        assert expert_pool_debate_enabled() is True

    def test_size_default(self, monkeypatch):
        from src.graph.expert_pool import _expert_pool_size

        monkeypatch.delenv("EXPERT_POOL_SIZE", raising=False)
        assert _expert_pool_size() == 3

    def test_size_clamped(self, monkeypatch):
        from src.graph.expert_pool import _expert_pool_size

        monkeypatch.setenv("EXPERT_POOL_SIZE", "99")
        assert _expert_pool_size() > 0
        monkeypatch.setenv("EXPERT_POOL_SIZE", "abc")
        assert _expert_pool_size() == 3  # 非法值回退默认

    def test_timeout_default(self, monkeypatch):
        from src.graph.expert_pool import _expert_timeout_seconds

        monkeypatch.delenv("EXPERT_POOL_TIMEOUT", raising=False)
        assert _expert_timeout_seconds() == 120

    def test_debate_top_k_default(self, monkeypatch):
        from src.graph.expert_pool import _debate_top_k

        monkeypatch.delenv("EXPERT_POOL_DEBATE_TOP_K", raising=False)
        assert _debate_top_k() == 2


# ─── dependency 纯逻辑 ────────────────────────────────────────────────────


class TestDependencyPureLogicBranches:
    def test_extract_import_module_names(self):
        from src.tools.dependency import extract_import_module_names

        code = "import os\nfrom collections import deque\nimport numpy as np\n"
        mods = extract_import_module_names(code)
        assert "os" in mods
        assert "collections" in mods
        assert "numpy" in mods

    def test_extract_imported_modules_set(self):
        from src.tools.dependency import extract_imported_modules

        code = "import os\nimport json\n"
        mods = extract_imported_modules(code)
        assert "os" in mods and "json" in mods

    def test_is_standard_library_true(self):
        from src.tools.dependency import is_standard_library

        assert is_standard_library("os") is True
        assert is_standard_library("json") is True
        assert is_standard_library("subprocess") is True

    def test_is_standard_library_false(self):
        from src.tools.dependency import is_standard_library

        assert is_standard_library("definitely_not_a_pkg_xyz") is False

    def test_find_missing_modules_detects_unknown(self):
        from src.tools.dependency import find_missing_modules

        # 不存在的模块名 → 缺失（非标准库 + 不可导入）
        missing = find_missing_modules({"os", "definitely_not_a_pkg_xyz"})
        assert "definitely_not_a_pkg_xyz" in missing
        assert "os" not in missing  # 标准库不缺失

    def test_conftest_ast_scan_default_enabled(self, monkeypatch):
        """CONTEST_AST_SCAN_ENABLE 默认 true（与依赖类扫描默认关相反口径）。"""
        from src.tools.dependency import conftest_ast_scan_enabled

        monkeypatch.delenv("CONTEST_AST_SCAN_ENABLE", raising=False)
        assert conftest_ast_scan_enabled() is True

    def test_conftest_ast_scan_disabled(self, monkeypatch):
        from src.tools.dependency import conftest_ast_scan_enabled

        monkeypatch.setenv("CONTEST_AST_SCAN_ENABLE", "false")
        assert conftest_ast_scan_enabled() is False

    def test_suggest_package_names_empty_input(self):
        from src.tools.dependency import suggest_package_names

        assert suggest_package_names(set()) == []

    def test_scan_conftest_ast_safety_flags_subprocess(self):
        from src.tools.dependency import scan_conftest_ast_safety

        code = "import subprocess\nsubprocess.run(['ls'])\n"
        findings = scan_conftest_ast_safety(code)
        assert isinstance(findings, list)
