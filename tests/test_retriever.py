"""
单元测试：测试 RAG 检索器 TestCaseRetriever。

覆盖范围：
    - chromadb 未安装时抛出 ImportError
    - add_case 只入库 passed=True 的案例
    - retrieve 方法在 collection 为空时返回空列表
    - clear 方法重建集合
"""

import pytest
from unittest.mock import patch, MagicMock, call
from src.rag.retriever import TestCaseRetriever


# ─── TestTestCaseRetriever：RAG 检索器 ────────────────────────────────────────
class TestTestCaseRetriever:
    """测试 TestCaseRetriever 的核心功能。"""

    def test_raises_import_error_when_chromadb_missing(self):
        """chromadb 未安装时应抛出 ImportError。"""
        with patch("src.rag.retriever.CHROMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="chromadb"):
                TestCaseRetriever()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_skips_failed(self, mock_chromadb):
        """passed=False 的测试用例不应入库。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=False,
        )
        # upsert 不应被调用
        mock_collection.upsert.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_inserts_when_passed(self, mock_chromadb):
        """passed=True 的测试用例应被入库。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0  # 模拟空集合
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=True,
            metadata={"function": "foo"},
        )
        mock_collection.upsert.assert_called_once()
        call_args = mock_collection.upsert.call_args
        # 验证文档内容包含 code 和 test_code
        doc = call_args[1]["documents"][0]
        assert "def foo(): pass" in doc
        assert "def test_foo(): pass" in doc

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_test_cases_empty_collection(self, mock_chromadb):
        """collection 为空时应返回空列表。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        result = retriever.retrieve_test_cases("def foo(): pass")
        assert result == []

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_repairs_empty_collection(self, mock_chromadb):
        """collection 为空时 retrieve_repairs 返回空列表。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        result = retriever.retrieve_repairs("runtime", "def foo(): pass")
        assert result == []

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_clear_recreates_collection(self, mock_chromadb):
        """clear 应删除旧集合并重建新集合。"""
        mock_client = MagicMock()
        mock_old_collection = MagicMock()
        mock_new_collection = MagicMock()
        mock_client.delete_collection.return_value = None
        mock_client.get_or_create_collection.side_effect = [mock_old_collection, mock_new_collection]
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(collection_name="test_col")
        retriever.collection = mock_old_collection
        retriever.clear()
        mock_client.delete_collection.assert_called_once_with("test_col")
        mock_client.get_or_create_collection.assert_called_with(
            name="test_col",
            metadata={"hnsw:space": "cosine"},
        )

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_repair_stores_correctly(self, mock_chromadb):
        """add_repair 应将修复案例入库。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0  # 模拟空集合
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        retriever.add_repair(
            original_code="def buggy(): return 1/0",
            patch="def fixed(): return x if x != 0 else 0",
            error_category="runtime",
        )
        mock_collection.upsert.assert_called_once()
        doc = mock_collection.upsert.call_args[1]["documents"][0]
        assert "runtime" in doc
        assert "original_code" in doc
