"""graph/expert_pool + tools/graphrag env 开关 / 参数钳制 / 补丁归一化分支补齐。

锁定 2026-10-02 批次 expert_pool / graphrag 低覆盖分支（纯静态，零 LLM）：
- expert_pool 3 个开关 env 解析 + 范围钳制（top_k / size / timeout）
- _normalize_patch_for_voting AST 归一化口径
- _patches_agree 补丁一致性判定
- graphrag GRAPH_RAG_ENABLE / max_hops / top_k_snippets 钳制
"""

from __future__ import annotations

import pytest


class TestExpertPoolSwitchBranches:
    def test_expert_pool_enabled_default_false(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_enabled

        monkeypatch.delenv("EXPERT_POOL_ENABLE", raising=False)
        assert expert_pool_enabled() is False

    def test_expert_pool_enabled_true(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_enabled

        monkeypatch.setenv("EXPERT_POOL_ENABLE", "true")
        assert expert_pool_enabled() is True

    def test_debate_default_false(self, monkeypatch):
        from src.graph.expert_pool import expert_pool_debate_enabled

        monkeypatch.delenv("EXPERT_POOL_DEBATE_ENABLE", raising=False)
        assert expert_pool_debate_enabled() is False

    def test_debate_requires_pool_enabled(self, monkeypatch):
        # 辩论开关在 pool 关时恒 False
        from src.graph.expert_pool import expert_pool_debate_enabled

        monkeypatch.delenv("EXPERT_POOL_ENABLE", raising=False)
        monkeypatch.setenv("EXPERT_POOL_DEBATE_ENABLE", "true")
        assert expert_pool_debate_enabled() is False


class TestExpertPoolParamClampBranches:
    def test_debate_top_k_default(self, monkeypatch):
        from src.graph.expert_pool import _debate_top_k

        monkeypatch.delenv("EXPERT_POOL_DEBATE_TOP_K", raising=False)
        assert _debate_top_k() == 2

    @pytest.mark.parametrize("val,expected", [("1", 2), ("5", 4), ("3", 3), ("not_num", 2)])
    def test_debate_top_k_clamp(self, monkeypatch, val, expected):
        from src.graph.expert_pool import _debate_top_k

        monkeypatch.setenv("EXPERT_POOL_DEBATE_TOP_K", val)
        assert _debate_top_k() == expected

    def test_expert_pool_size_default(self, monkeypatch):
        from src.graph.expert_pool import _expert_pool_size

        monkeypatch.delenv("EXPERT_POOL_SIZE", raising=False)
        assert _expert_pool_size() == 3

    @pytest.mark.parametrize("val,expected", [("0", 1), ("8", 7), ("5", 5), ("not_num", 3)])
    def test_expert_pool_size_clamp(self, monkeypatch, val, expected):
        from src.graph.expert_pool import _expert_pool_size

        monkeypatch.setenv("EXPERT_POOL_SIZE", val)
        assert _expert_pool_size() == expected

    def test_expert_timeout_default(self, monkeypatch):
        from src.graph.expert_pool import _expert_timeout_seconds

        monkeypatch.delenv("EXPERT_POOL_TIMEOUT", raising=False)
        assert _expert_timeout_seconds() == 120

    @pytest.mark.parametrize("val,expected", [("10", 30), ("999", 600), ("300", 300), ("bad", 120)])
    def test_expert_timeout_clamp(self, monkeypatch, val, expected):
        from src.graph.expert_pool import _expert_timeout_seconds

        monkeypatch.setenv("EXPERT_POOL_TIMEOUT", val)
        assert _expert_timeout_seconds() == expected


class TestNormalizePatchForVotingBranches:
    def test_whitespace_normalization(self):
        from src.graph.expert_pool import _normalize_patch_for_voting

        out = _normalize_patch_for_voting("def f():\n    return 1\n")
        assert isinstance(out, str)

    def test_empty_patch(self):
        from src.graph.expert_pool import _normalize_patch_for_voting

        out = _normalize_patch_for_voting("")
        assert isinstance(out, str)

    def test_invalid_syntax_degrades(self):
        from src.graph.expert_pool import _normalize_patch_for_voting

        out = _normalize_patch_for_voting("def f(:\n")
        assert isinstance(out, str)


class TestPatchesAgreeBranches:
    def test_identical_patches_agree(self):
        from src.graph.expert_pool import _patches_agree

        assert _patches_agree("def f():\n    return 1\n", "def f():\n    return 1\n") is True

    def test_different_patches_disagree(self):
        from src.graph.expert_pool import _patches_agree

        assert _patches_agree("def f():\n    return 1\n", "def f():\n    return 2\n") is False


class TestGraphRagSwitchBranches:
    def test_graph_rag_enabled_default_false(self, monkeypatch):
        from src.tools.graphrag import graph_rag_enabled

        monkeypatch.delenv("GRAPH_RAG_ENABLE", raising=False)
        assert graph_rag_enabled() is False

    def test_graph_rag_enabled_true(self, monkeypatch):
        from src.tools.graphrag import graph_rag_enabled

        monkeypatch.setenv("GRAPH_RAG_ENABLE", "true")
        assert graph_rag_enabled() is True

    def test_max_hops_default(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.delenv("GRAPH_RAG_MAX_HOPS", raising=False)
        assert _graph_rag_max_hops() == 2

    @pytest.mark.parametrize("val,expected", [("0", 1), ("9", 5), ("3", 3), ("bad", 2)])
    def test_max_hops_clamp(self, monkeypatch, val, expected):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.setenv("GRAPH_RAG_MAX_HOPS", val)
        assert _graph_rag_max_hops() == expected

    def test_top_k_snippets_default(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.delenv("GRAPH_RAG_TOP_K_SNIPPETS", raising=False)
        assert _graph_rag_top_k_snippets() == 5

    @pytest.mark.parametrize("val,expected", [("0", 1), ("99", 20), ("8", 8), ("bad", 5)])
    def test_top_k_snippets_clamp(self, monkeypatch, val, expected):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.setenv("GRAPH_RAG_TOP_K_SNIPPETS", val)
        assert _graph_rag_top_k_snippets() == expected
