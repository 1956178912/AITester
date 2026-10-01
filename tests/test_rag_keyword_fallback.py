"""RAG 关键词兜底层分支补测（2026-10-02 审查：分支覆盖门禁回绿）。

背景：`src/graph/rag.py` 的 20 号"关键词兜底检索"层（LeanKG 回退链
最底层，RAG_KEYWORD_FALLBACK_ENABLE 默认关）落地时零测试覆盖——
coverage.xml 显示 `_iter_candidate_docs` / `keyword_fallback_search` /
`retriever_or_keyword_fallback` / `_tokenize` 合计约 38 个分支未覆盖，
是总分支覆盖 77% 门槛的决定性缺口之一。本文件逐一补测全分支矩阵，
候选文档源经 `sources=` 注入（零目录扫描依赖），CI 稳定。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import src.graph.rag as rag
from src.graph.rag import (
    _iter_candidate_docs,
    _keyword_fallback_enabled,
    _keyword_fallback_max_results,
    _tokenize,
    keyword_fallback_result_count,
    keyword_fallback_search,
    keyword_similarity,
    retriever_or_keyword_fallback,
)


@pytest.mark.unit
class TestSwitches:
    """关键词兜底开关与上限解析。"""

    def test_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("RAG_KEYWORD_FALLBACK_ENABLE", raising=False)
        assert _keyword_fallback_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on"])
    def test_enabled_truthy(self, monkeypatch, value):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", value)
        assert _keyword_fallback_enabled() is True

    def test_max_results_default_clamp(self, monkeypatch):
        monkeypatch.delenv("RAG_KEYWORD_FALLBACK_MAX_RESULTS", raising=False)
        assert _keyword_fallback_max_results() == 5
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_MAX_RESULTS", "9999")
        assert _keyword_fallback_max_results() == 100  # 上限钳制
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_MAX_RESULTS", "0")
        assert _keyword_fallback_max_results() == 1  # 下限钳制
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_MAX_RESULTS", "abc")
        assert _keyword_fallback_max_results() == 5  # 非法回退


@pytest.mark.unit
class TestTokenize:
    r"""_tokenize 轻量分词（英文 \w+ + 中文单字）。"""

    def test_english_lowercased(self):
        assert _tokenize("Hello World") == {"hello", "world"}

    def test_digits_and_underscore_kept(self):
        assert _tokenize("a_1 b2") == {"a_1", "b2"}

    def test_chinese_chars_split(self):
        assert _tokenize("边界条件") == {"边", "界", "条", "件"}

    def test_mixed_language(self):
        toks = _tokenize("test边界")
        assert "test" in toks
        assert "边" in toks

    def test_empty(self):
        assert _tokenize("") == set()

    def test_punctuation_only(self):
        assert _tokenize("!!!???...") == set()


@pytest.mark.unit
class TestKeywordSimilarity:
    """keyword_similarity 归一化重叠打分。"""

    def test_full_overlap_is_one(self):
        assert keyword_similarity("a b c", "prefix a b c suffix") == 1.0

    def test_partial_overlap(self):
        # query 4 tokens，命中 2 → 0.5
        assert keyword_similarity("a b c d", "a b x y") == 0.5

    def test_zero_overlap(self):
        assert keyword_similarity("x y", "z w") == 0.0

    def test_empty_query_zero(self):
        assert keyword_similarity("", "anything") == 0.0

    def test_empty_doc_zero(self):
        assert keyword_similarity("a b", "") == 0.0

    def test_whitespace_query_zero(self):
        assert keyword_similarity("   ", "a b") == 0.0


@pytest.mark.unit
class TestIterCandidateDocs:
    """_iter_candidate_docs 材料源枚举（cache + rag_data，含损坏文件跳过）。"""

    def test_cache_dir_env_used(self, monkeypatch, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "a.json").write_text(json.dumps({"prompt": "fix the bug", "response": "patch text"}), encoding="utf-8")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", "")
        docs = _iter_candidate_docs()
        assert docs, "cache 材料应被枚举"
        assert docs[0][0] == "cache"
        assert "fix the bug" in docs[0][2]

    def test_corrupt_json_skipped(self, monkeypatch, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "bad.json").write_text("{not json", encoding="utf-8")
        (cache / "ok.json").write_text(json.dumps({"prompt": "p", "response": "r"}), encoding="utf-8")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", "")
        docs = _iter_candidate_docs()
        assert len(docs) == 1, "损坏 JSON 应静默跳过"
        assert docs[0][1] == "ok.json"

    def test_empty_prompt_response_skipped(self, monkeypatch, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "empty.json").write_text(json.dumps({"prompt": "", "response": ""}), encoding="utf-8")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", "")
        assert _iter_candidate_docs() == []

    def test_rag_data_source_included(self, monkeypatch, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache))
        rag_dir = tmp_path / "rag"
        rag_dir.mkdir()
        (rag_dir / "case1.json").write_text(json.dumps([{"code": "def f(): pass"}]), encoding="utf-8")
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", str(rag_dir))
        docs = _iter_candidate_docs()
        assert any(d[0] == "rag_data" for d in docs), "rag_data 材料应被枚举"

    def test_missing_dirs_return_empty(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "nope"))
        monkeypatch.setattr(rag, "RAG_PERSIST_PATH", str(tmp_path / "nope2"))
        assert _iter_candidate_docs() == []


@pytest.mark.unit
class TestKeywordFallbackSearch:
    """keyword_fallback_search 全分支（开关 / 空查询 / 排序 / 限流 / 观测层）。"""

    def _sources(self):
        return [
            ("cache", "doc1.json", "fix divide by zero error boundary"),
            ("cache", "doc2.json", "unrelated cooking recipe text"),
            ("rag_data", "case1.json", "divide zero boundary condition fix"),
        ]

    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.delenv("RAG_KEYWORD_FALLBACK_ENABLE", raising=False)
        assert keyword_fallback_search("divide zero") == []

    def test_empty_query_returns_empty(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        assert keyword_fallback_search("") == []
        assert keyword_fallback_search("   ") == []

    def test_zero_similarity_excluded(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        out = keyword_fallback_search("quantum entanglement", sources=self._sources())
        assert out == [], "零重叠条目不应返回"

    def test_sorted_by_similarity_desc(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        out = keyword_fallback_search("divide zero boundary fix", sources=self._sources())
        assert out
        sims = [d["similarity"] for d in out]
        assert sims == sorted(sims, reverse=True), f"未按相似度降序: {sims}"
        # 命中最多的 doc 应在首位（doc1 与 case1 均命中多数 token）
        assert out[0]["similarity"] > 0

    def test_max_results_limits_output(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        out = keyword_fallback_search("divide zero boundary fix", max_results=1, sources=self._sources())
        assert len(out) == 1

    def test_result_shape_and_text_truncation(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        long_text = "divide " + "x" * 5000
        out = keyword_fallback_search("divide", sources=[("cache", "big.json", long_text)])
        assert out[0]["source"] == "cache"
        assert out[0]["doc_id"] == "big.json"
        assert len(out[0]["text"]) == 1200, "text 应截断到 1200 字符"
        assert isinstance(out[0]["similarity"], float)

    def test_observation_layer_updated(self, monkeypatch):
        monkeypatch.setenv("RAG_KEYWORD_FALLBACK_ENABLE", "true")
        keyword_fallback_search("divide zero", sources=self._sources())
        assert keyword_fallback_result_count() > 0
        # 清空后（无调用）返回 0 的分支由 test_result_count_zero 覆盖

    def test_result_count_zero_without_calls(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_last_results", [])
        assert keyword_fallback_result_count() == 0

    def test_result_count_none_safe(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_last_results", None)
        assert keyword_fallback_result_count() == 0


@pytest.mark.unit
class TestRetrieverOrKeywordFallback:
    """retriever_or_keyword_fallback 向量 → 关键词双层回退矩阵。"""

    def _kwargs(self, **overrides):
        base = {
            "op_name": "retrieve_test_cases",
            "action": MagicMock(),
            "enabled": True,
            "module_available": True,
            "retriever_cls": object,
            "get_retriever": MagicMock(return_value=MagicMock()),
            "keyword_query": "divide zero",
        }
        base.update(overrides)
        return base

    def test_vector_success(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        kw = self._kwargs()
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert vector is True and fallback is False
        kw["action"].assert_called_once()

    def test_vector_disabled_falls_to_keyword(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        monkeypatch.setattr(rag, "keyword_fallback_search", lambda q: [{"doc_id": "x", "similarity": 0.5}])
        kw = self._kwargs(enabled=False, action=MagicMock())
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert vector is False and fallback is True
        kw["action"].assert_not_called()

    def test_vector_none_retriever_falls_to_keyword(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        monkeypatch.setattr(rag, "keyword_fallback_search", lambda q: [{"doc_id": "y"}])
        kw = self._kwargs(get_retriever=MagicMock(return_value=None), action=MagicMock())
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, True)

    def test_vector_exception_falls_to_keyword(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        monkeypatch.setattr(rag, "keyword_fallback_search", lambda q: [{"doc_id": "z"}])
        action = MagicMock(side_effect=RuntimeError("向量库超时"))
        kw = self._kwargs(action=action)
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, True)

    def test_fallback_disabled_returns_false(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: False)
        kw = self._kwargs(enabled=False, action=MagicMock())
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, False)

    def test_empty_query_skips_keyword(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        search = MagicMock()
        monkeypatch.setattr(rag, "keyword_fallback_search", search)
        kw = self._kwargs(enabled=False, keyword_query="")
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, False)
        search.assert_not_called()

    def test_keyword_zero_results_returns_false(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: True)
        monkeypatch.setattr(rag, "keyword_fallback_search", lambda q: [])
        kw = self._kwargs(enabled=False)
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, False)

    def test_module_unavailable_path(self, monkeypatch):
        monkeypatch.setattr(rag, "_keyword_fallback_enabled", lambda: False)
        kw = self._kwargs(module_available=False, retriever_cls=None, action=MagicMock())
        vector, fallback = retriever_or_keyword_fallback(**kw)
        assert (vector, fallback) == (False, False)
        kw["action"].assert_not_called()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
