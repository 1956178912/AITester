"""embedding_utils 后端加载/嵌入分支补齐（2026-10-08，73% → 90%+）。

补齐 test_embedding_utils.py 未覆盖的 _load_backend / _embed_with_backend 后端分支：
codebert（transformers）/ sentence-transformers / chromadb 三后端的加载、嵌入、
ImportError 降级、异常降级（全部 mock 后端模块，零真实模型加载 / 零网络）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.utils.embedding_utils as eu


@pytest.fixture(autouse=True)
def _reset_backend_cache(monkeypatch):
    """每个测试前重置模块级后端缓存，避免跨测试复用污染。"""
    monkeypatch.setattr(eu, "_backend_initialized", False)
    monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": None})
    yield
    monkeypatch.setattr(eu, "_backend_initialized", False)
    monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": None})


# ═══ 1. _load_backend 后端加载分支 ════════════════════════════════════════════


class TestLoadBackendBranches:
    def test_codebert_import_error_falls_back(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        # transformers 未安装 → ImportError → 降级 (None, None)
        with patch.dict("sys.modules", {"transformers": None}):
            name, instance = eu._load_backend()
        assert name is None and instance is None

    def test_codebert_load_success(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_transformers = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        mock_transformers.AutoModel.from_pretrained.return_value = mock_model
        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            name, instance = eu._load_backend()
        assert name == "codebert"
        assert instance["tokenizer"] is mock_tokenizer
        assert instance["model"] is mock_model

    def test_codebert_load_exception_falls_back(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "codebert")
        mock_transformers = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained.side_effect = RuntimeError("hf down")
        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            name, instance = eu._load_backend()
        assert name is None and instance is None

    def test_sentence_transformers_import_error_falls_back(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "sentence_transformers")
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            name, instance = eu._load_backend()
        assert name is None and instance is None

    def test_chromadb_load_success(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "chromadb")
        mock_embed_fn = MagicMock()
        with patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction", return_value=mock_embed_fn):
            name, instance = eu._load_backend()
        assert name == "chromadb"
        assert instance is mock_embed_fn

    def test_auto_no_backend_returns_none(self, monkeypatch):
        # auto 模式：三个后端都不可用 → (None, None)
        monkeypatch.setenv("EMBEDDING_BACKEND", "auto")
        with (
            patch.dict("sys.modules", {"transformers": None, "sentence_transformers": None}),
            patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction", side_effect=ImportError),
        ):
            name, instance = eu._load_backend()
        assert name is None and instance is None

    def test_backend_cache_hit(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_initialized", True)
        monkeypatch.setattr(eu, "_backend_cache", {"instance": "mock", "name": "codebert"})
        name, instance = eu._load_backend()
        assert name == "codebert"
        assert instance == "mock"

    def test_sentence_transformers_load_success(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "sentence_transformers")
        mock_st = MagicMock()
        mock_instance = MagicMock()
        mock_st.SentenceTransformer.return_value = mock_instance
        with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
            name, instance = eu._load_backend()
        assert name == "sentence_transformers"
        assert instance is mock_instance

    def test_chromadb_failure_falls_back(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "chromadb")
        with patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction", side_effect=RuntimeError("boom")):
            name, instance = eu._load_backend()
        assert name is None and instance is None


# ═══ 2. _embed_with_backend 嵌入分支 ══════════════════════════════════════════


class TestEmbedWithBackendBranches:
    def test_none_instance_returns_none(self):
        assert eu._embed_with_backend(None, "hello") is None

    def test_sentence_transformers_embed(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "sentence_transformers"})
        mock_instance = MagicMock()
        mock_instance.encode.return_value = [1.0, 0.5]
        assert eu._embed_with_backend(mock_instance, "hello") == [1.0, 0.5]

    def test_chromadb_embed(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "chromadb"})
        mock_instance = MagicMock()
        mock_instance.return_value = [[0.1, 0.2]]
        assert eu._embed_with_backend(mock_instance, "hello") == [0.1, 0.2]

    def test_chromadb_empty_vecs_returns_none(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "chromadb"})
        mock_instance = MagicMock()
        mock_instance.return_value = []  # 空结果 → None
        assert eu._embed_with_backend(mock_instance, "hello") is None

    def test_embed_exception_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "sentence_transformers"})
        mock_instance = MagicMock()
        mock_instance.encode.side_effect = RuntimeError("boom")
        assert eu._embed_with_backend(mock_instance, "hello") is None

    def test_unknown_backend_returns_none(self, monkeypatch):
        # backend name 不在 codebert/sentence_transformers/chromadb → return None
        monkeypatch.setattr(eu, "_backend_cache", {"instance": MagicMock(), "name": "bogus"})
        assert eu._embed_with_backend(MagicMock(), "hello") is None

    def test_codebert_embed(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "codebert"})
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": 1, "attention_mask": 1}
        mock_model = MagicMock()
        mock_vec = MagicMock()
        mock_vec.norm.return_value = 1.0
        mock_vec.tolist.return_value = [0.1, 0.2]
        mock_vec.__truediv__.return_value = mock_vec  # _vec / (...) 返回自身
        mock_model.return_value.last_hidden_state = MagicMock()
        mock_model.return_value.last_hidden_state.__getitem__.return_value = mock_vec
        instance = {"tokenizer": mock_tokenizer, "model": mock_model}
        with patch.dict("sys.modules", {"torch": MagicMock()}):
            result = eu._embed_with_backend(instance, "hello")
        assert result == [0.1, 0.2]

    def test_codebert_torch_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(eu, "_backend_cache", {"instance": None, "name": "codebert"})
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": 1}
        instance = {"tokenizer": mock_tokenizer, "model": MagicMock()}
        # torch 缺失（sys.modules 里 None）→ ImportError → return None
        with patch.dict("sys.modules", {"torch": None}):
            result = eu._embed_with_backend(instance, "hello")
        assert result is None


# ═══ 4. embed_text / backend_name 主链路 ═══════════════════════════════════════


class TestEmbedTextMainPath:
    def test_embed_text_loads_backend(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "chromadb")
        mock_instance = MagicMock()
        mock_instance.return_value = [[0.1, 0.2]]
        with patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction", return_value=mock_instance):
            result = eu.embed_text("hello")
        assert result == [0.1, 0.2]

    def test_backend_name_none(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_BACKEND", "none")
        assert eu.backend_name() is None

    def test_embed_text_backend_unavailable_returns_none(self, monkeypatch):
        # 后端全部不可用 → _load_backend 返回 (None, None) → instance None → None
        monkeypatch.setenv("EMBEDDING_BACKEND", "auto")
        with (
            patch.dict("sys.modules", {"transformers": None, "sentence_transformers": None}),
            patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction", side_effect=ImportError),
        ):
            result = eu.embed_text("hello")
        assert result is None


# ═══ 3. cosine_similarity 纯 Python 回退零向量分支 ═════════════════════════════


class TestCosineSimilarityPurePythonZeroVector:
    def test_pure_python_zero_vector_returns_zero(self, monkeypatch):
        # numpy 缺失 → 纯 Python 回退；零向量 → 0.0
        monkeypatch.setitem(__import__("sys").modules, "numpy", None)
        assert eu.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert eu.cosine_similarity([1.0, 1.0], [0.0, 0.0]) == 0.0
