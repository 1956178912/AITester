"""批次7 GraphRAG 结构图索引 + 混合检索 单元测试。

覆盖：
- graph_rag_enabled 默认关 / 开启
- GraphRAGIndex.build_from_cross_file_deps 构建 + 边去重
- GraphRAGIndex.n_hop_subgraph N 跳邻域（1 跳 / 2 跳）
- GraphRAGIndex.find_symbol_anchor 符号锚点查找
- GraphRAGIndex.find_text_snippets 文本片段定位
- hybrid_retrieve 全视角（subgraph + snippets + anchors）
- hybrid_retrieve 空索引降级（空结果）
- build_graphrag_prompt_section 渲染 + 空结果 → 空串
"""

from __future__ import annotations

import os
from unittest.mock import patch


def test_graph_rag_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GRAPH_RAG_ENABLE", None)
        from src.tools.graphrag import graph_rag_enabled

        assert graph_rag_enabled() is False


def test_graph_rag_switch_on() -> None:
    with patch.dict(os.environ, {"GRAPH_RAG_ENABLE": "true"}):
        from src.tools.graphrag import graph_rag_enabled

        assert graph_rag_enabled() is True


def _sample_deps() -> list[dict]:
    """构造 sample 跨文件依赖边（A → B, B → C, A → C，含重复边去重场景）。"""
    return [
        {"source_module": "a", "target_module": "b", "symbol": "helper", "call_line": 10, "context": "x = helper()"},
        {"source_module": "b", "target_module": "c", "symbol": "util", "call_line": 20, "context": "y = util()"},
        {"source_module": "a", "target_module": "c", "symbol": "util", "call_line": 30, "context": "z = util()"},
        # 重复边（a → b helper，call_line 更大 → 应被去重保留最小 call_line=10）
        {"source_module": "a", "target_module": "b", "symbol": "helper", "call_line": 99, "context": "dup"},
    ]


def test_build_from_cross_file_deps_dedup() -> None:
    """重复边去重：同 (source, target, symbol) 只保留最小 call_line。"""
    from src.tools.graphrag import GraphRAGIndex

    index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps())
    # a → b helper 去重后只保留一条边详情（call_line=10）
    detail = index._edge_details.get(("a", "b", "helper"))
    assert detail is not None
    assert detail["call_line"] == 10
    assert detail["context"] == "x = helper()"  # 非重复边的 context


def test_n_hop_subgraph_1_hop() -> None:
    from src.tools.graphrag import GraphRAGIndex

    index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps())
    subgraph = index.n_hop_subgraph("a", hops=1)
    # 1 跳：a → b (helper), a → c (util), c → a 入边（无），b → a 入边（无）
    # 出边：(a→b, helper), (a→c, util)；入边：b 的入边（a→b helper 已含），c 的入边（a→c util 已含）
    edge_pairs = set((e["source_module"], e["target_module"], e["symbol"]) for e in subgraph)
    assert ("a", "b", "helper") in edge_pairs
    assert ("a", "c", "util") in edge_pairs


def test_n_hop_subgraph_2_hops() -> None:
    from src.tools.graphrag import GraphRAGIndex

    index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps())
    subgraph = index.n_hop_subgraph("a", hops=2)
    # 2 跳：第一跳 a → {b, c}；第二跳 b → {c (util)}, c → {}
    # 出边含 (b→c, util)（入边含 (c→b, util) 的入边视角）
    edge_pairs = set((e["source_module"], e["target_module"], e["symbol"]) for e in subgraph)
    assert ("b", "c", "util") in edge_pairs


def test_find_symbol_anchor() -> None:
    from src.tools.graphrag import GraphRAGIndex

    index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps())
    anchors = index.find_symbol_anchor("helper")
    # helper 出现在 (b, helper) 锚点
    assert ("b", "helper") in anchors
    anchors_util = index.find_symbol_anchor("util")
    assert ("c", "util") in anchors_util
    # 不存在的符号 → 空
    assert index.find_symbol_anchor("nonexistent") == []


def test_find_text_snippets() -> None:
    from src.tools.graphrag import GraphRAGIndex

    index = GraphRAGIndex.build_from_cross_file_deps(
        _sample_deps(),
        module_sources={
            "a": "import b\n\ndef run():\n    x = b.helper()\n    return x\n",
            "c": "def util(v):\n    return v * 2\n",
        },
    )
    snippets = index.find_text_snippets("helper", top_k=3)
    # "helper" 出现在 module "a" 的第 3 行（x = b.helper()）
    assert len(snippets) >= 1
    assert "a" in snippets[0]
    # 空模块源 → 无片段
    empty_index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps(), module_sources={})
    assert empty_index.find_text_snippets("helper") == []


def test_hybrid_retrieve_full() -> None:
    """全视角混合检索：subgraph + snippets + anchors。"""
    from src.tools.graphrag import GraphRAGIndex, hybrid_retrieve

    index = GraphRAGIndex.build_from_cross_file_deps(
        _sample_deps(),
        module_sources={
            "a": "import b\n\ndef run():\n    x = b.helper()\n    return x\n",
            "c": "def util(v):\n    return v * 2\n",
        },
    )
    result = hybrid_retrieve(
        index,
        center_module="a",
        center_symbol="helper",
        query_text="helper",
        hops=2,
        top_k_snippets=3,
    )
    assert result["center_module"] == "a"
    assert result["center_symbol"] == "helper"
    assert result["hops_used"] == 2
    # 子图非空（a → b, a → c）
    assert len(result["subgraph"]) >= 2
    # 文本片段非空（helper 在 module a）
    assert len(result["text_snippets"]) >= 1
    # 符号锚点非空（helper 在 module b）
    assert len(result["anchor_symbols"]) >= 1


def test_hybrid_retrieve_empty_index_degrades() -> None:
    """空索引 → 混合检索全视角空（保守降级，不阻断修复）。"""
    from src.tools.graphrag import GraphRAGIndex, hybrid_retrieve

    index = GraphRAGIndex()
    result = hybrid_retrieve(index, center_symbol="nonexistent", query_text="nope")
    assert result["subgraph"] == []
    assert result["text_snippets"] == []
    assert result["anchor_symbols"] == []


def test_hybrid_retrieve_center_symbol_resolves_module() -> None:
    """center_symbol 指定时经 find_symbol_anchor 定位模块。"""
    from src.tools.graphrag import GraphRAGIndex, hybrid_retrieve

    index = GraphRAGIndex.build_from_cross_file_deps(_sample_deps())
    result = hybrid_retrieve(index, center_symbol="helper", hops=1)
    # helper 锚点在 module b → center_module 应解析为 "b"
    assert result["center_module"] == "b"
    # 子图非空（b → c, c 入边）
    assert len(result["subgraph"]) >= 1


def test_build_graphrag_prompt_section_empty() -> None:
    from src.tools.graphrag import build_graphrag_prompt_section

    assert build_graphrag_prompt_section({}) == ""
    assert build_graphrag_prompt_section(None) == ""
    assert build_graphrag_prompt_section({"subgraph": [], "text_snippets": [], "anchor_symbols": []}) == ""


def test_build_graphrag_prompt_section_with_data() -> None:
    from src.tools.graphrag import GraphRAGIndex, build_graphrag_prompt_section, hybrid_retrieve

    index = GraphRAGIndex.build_from_cross_file_deps(
        _sample_deps(),
        module_sources={
            "a": "import b\n\ndef run():\n    x = b.helper()\n    return x\n",
        },
    )
    result = hybrid_retrieve(index, center_module="a", center_symbol="helper", query_text="helper", hops=1)
    section = build_graphrag_prompt_section(result)
    assert "依赖子图" in section
    assert "相关片段" in section
    assert "符号锚点" in section
    assert "a.helper" in section or "b.helper" in section


class TestGraphRAGMoreBranches:
    """build_from_call_graph / 非法依赖跳过 / 片段截断（2026-10-08 补齐 86% → 100%）。"""

    def test_build_skips_invalid_deps(self):
        from src.tools.graphrag import GraphRAGIndex

        deps = [
            "not-a-dict",  # 非 dict 跳过
            {"source_module": "a"},  # 缺 target/symbol 跳过
            {"source_module": "a", "target_module": "b"},  # 缺 symbol 跳过
        ]
        index = GraphRAGIndex.build_from_cross_file_deps(deps)
        assert index._symbols == set()

    def test_build_from_call_graph_cross_module(self):
        from src.tools.graphrag import GraphRAGIndex

        call_edges = [("caller_fn", "callee_fn")]
        module_sources = {
            "mod_a": "function caller_fn() {}",
            "mod_b": "function callee_fn() {}",
        }
        index = GraphRAGIndex.build_from_call_graph(call_edges, module_sources)
        assert ("mod_b", "callee_fn") in index._symbols

    def test_build_from_call_graph_same_module_skipped(self):
        from src.tools.graphrag import GraphRAGIndex

        # 同模块内调用 → 跳过（图索引只关心跨模块边）
        call_edges = [("fn_a", "fn_b")]
        module_sources = {"mod": "function fn_a() {}\nfunction fn_b() {}"}
        index = GraphRAGIndex.build_from_call_graph(call_edges, module_sources)
        assert index._symbols == set()

    def test_find_text_snippets_capped(self):
        from src.tools.graphrag import GraphRAGIndex

        index = GraphRAGIndex()
        index._module_sources = {"mod": "hello\nhello\nhello\nhello\n"}
        snippets = index.find_text_snippets("hello", top_k=2)
        assert len(snippets) == 2

    def test_max_hops_invalid_falls_back(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_max_hops

        monkeypatch.setenv("GRAPH_RAG_MAX_HOPS", "abc")
        assert _graph_rag_max_hops() == 2

    def test_top_k_snippets_invalid_falls_back(self, monkeypatch):
        from src.tools.graphrag import _graph_rag_top_k_snippets

        monkeypatch.setenv("GRAPH_RAG_TOP_K_SNIPPETS", "abc")
        assert _graph_rag_top_k_snippets() == 5
