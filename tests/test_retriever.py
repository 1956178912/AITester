"""
单元测试：测试 RAG 检索器 TestCaseRetriever。

覆盖范围：
    - chromadb 未安装时抛出 ImportError
    - add_case 只入库 passed=True 的案例
    - retrieve 方法在 collection 为空时返回空列表
    - clear 方法重建集合
"""

from unittest.mock import MagicMock, patch

import pytest

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

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_capacity_limit_skips_insert(self, mock_chromadb):
        """达到容量上限时应跳过添加并记录警告。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1000  # 达到上限
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(max_cases=1000)
        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=True,
        )
        mock_collection.upsert.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_repair_capacity_limit_skips_insert(self, mock_chromadb):
        """add_repair 达到容量上限时应跳过添加。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1000
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(max_cases=1000)
        retriever.add_repair(
            original_code="def buggy(): pass",
            patch="def fixed(): pass",
            error_category="syntax",
        )
        mock_collection.upsert.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_test_cases_with_results(self, mock_chromadb):
        """retrieve_test_cases 返回检索结果。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["def foo(): pass"]],
            "metadatas": [[{"test_code": "def test_foo(): pass", "distance": 0.9}]],
        }
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        result = retriever.retrieve_test_cases("def foo(): pass", top_k=3)
        assert len(result) == 1
        assert result[0]["test_code"] == "def test_foo(): pass"
        assert result[0]["similarity"] == 0.9

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_repairs_with_results(self, mock_chromadb):
        """retrieve_repairs 返回检索结果。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["error: runtime\ndef buggy()"]],
            "metadatas": [[{"patch": "def fixed()", "distance": 0.85}]],
        }
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        result = retriever.retrieve_repairs("runtime", "def foo(): pass")
        assert len(result) == 1
        assert result[0]["patch"] == "def fixed()"
        assert result[0]["similarity"] == 0.85

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_cleanup_expired_removes_old_entries(self, mock_chromadb):
        """cleanup_expired 应清理过期条目。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"_added_at": 0},  # 过期（假设 ttl=3600）
                {"_added_at": 9999999999},  # 未过期
            ],
        }
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(ttl_seconds=3600)
        count = retriever.cleanup_expired()
        assert count == 1
        mock_collection.delete.assert_called_once_with(ids=["id1"])

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_cleanup_expired_no_expired_entries(self, mock_chromadb):
        """cleanup_expired 无过期条目时返回 0。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": [], "metadatas": []}
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(ttl_seconds=3600)
        count = retriever.cleanup_expired()
        assert count == 0
        mock_collection.delete.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_with_metadata(self, mock_chromadb):
        """add_case 应正确传递元数据。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever()
        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=True,
            metadata={"function": "foo", "line": 10},
        )
        call_args = mock_collection.upsert.call_args
        meta = call_args[1]["metadatas"][0]
        assert meta["function"] == "foo"
        assert meta["line"] == 10
        assert "_added_at" in meta

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_cleanup_expired_and_excess_skips_empty(self, mock_chromadb):
        """_cleanup_expired_and_excess 无条目时不应报错。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": [], "metadatas": []}
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(ttl_seconds=3600)
        retriever._cleanup_expired_and_excess()
        mock_collection.delete.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_cleanup_expired_and_excess_removes_overcapacity(self, mock_chromadb):
        """_cleanup_expired_and_excess 移除超额条目。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        # 模拟 5 个条目，max_cases=3
        mock_collection.get.return_value = {
            "ids": ["id1", "id2", "id3", "id4", "id5"],
            "metadatas": [
                {"_added_at": 100},
                {"_added_at": 200},
                {"_added_at": 300},
                {"_added_at": 400},
                {"_added_at": 500},
            ],
        }
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        retriever = TestCaseRetriever(ttl_seconds=99999, max_cases=3)
        retriever._cleanup_expired_and_excess()
        # 应删除 2 个最旧的条目
        assert mock_collection.delete.call_count == 1
