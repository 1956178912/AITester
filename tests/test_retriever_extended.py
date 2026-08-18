"""
补充测试：retriever.py 边缘情况和未覆盖路径测试。

覆盖范围：
    - _cleanup_expired_and_excess：TTL 过期清理、容量超限清理
    - cleanup_expired：手动清理过期条目并返回数量
    - add_case/add_repair 容量上限警告
    - retrieve_repairs 返回实际结果
    - 带 persist_path 的初始化
    - 元数据传递
"""

from unittest.mock import MagicMock, patch


class TestCleanupExpiredAndExcess:
    """测试 _cleanup_expired_and_excess 内部清理逻辑。"""

    @patch("builtins.__import__")
    def test_no_entries_returns_early(self, mock_import):
        """collection 为空时直接返回。"""
        # 阻止 time 模块被导入，让内部 import time 走正常路径
        # 但我们需要 mock time.time，所以用更直接的方式：
        # 直接 mock retriever 内部的 time 属性
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_collection.get.return_value = {"ids": []}
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600
        retriever.max_cases = 1000

        # 直接替换 time 模块引用
        import time as real_time

        with patch.object(real_time, "time", return_value=1000.0):
            retriever._cleanup_expired_and_excess()

        mock_collection.delete.assert_not_called()

    @patch("builtins.__import__")
    def test_expired_entries_are_deleted(self, mock_import):
        """TTL 过期的条目应被删除。"""
        import time as real_time

        from src.rag.retriever import TestCaseRetriever

        current = 1000.0

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["doc1"],
            "metadatas": [{"_added_at": current - 5000, "code": "x=1"}],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600

        with patch.object(real_time, "time", return_value=current):
            retriever._cleanup_expired_and_excess()

        mock_collection.delete.assert_called_once_with(ids=["doc1"])

    @patch("builtins.__import__")
    def test_valid_entries_not_deleted(self, mock_import):
        """未过期的条目不应被删除。"""
        import time as real_time

        from src.rag.retriever import TestCaseRetriever

        current = 1000.0

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["doc1"],
            "metadatas": [{"_added_at": current - 100, "code": "x=1"}],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600

        with patch.object(real_time, "time", return_value=current):
            retriever._cleanup_expired_and_excess()

        mock_collection.delete.assert_not_called()

    @patch("builtins.__import__")
    def test_excess_entries_trimmed_keeps_newest(self, mock_import):
        """超过 max_cases 时删除最旧的条目，保留最新的。"""
        import time as real_time

        from src.rag.retriever import TestCaseRetriever

        current = 1000.0

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.get.return_value = {
            "ids": ["doc1", "doc2", "doc3"],
            "metadatas": [
                {"_added_at": current - 10},
                {"_added_at": current - 100},
                {"_added_at": current - 500},
            ],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever(max_cases=2)
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600

        with patch.object(real_time, "time", return_value=current):
            retriever._cleanup_expired_and_excess()

        delete_call = mock_collection.delete.call_args
        assert "doc3" in delete_call[1]["ids"]


class TestCleanupExpiredPublic:
    """测试 cleanup_expired 公共方法。"""

    @patch("builtins.__import__")
    def test_cleanup_returns_count(self, mock_import):
        """cleanup_expired 返回清理的过期条目数。"""
        import time as real_time

        from src.rag.retriever import TestCaseRetriever

        current = 1000.0

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["old1", "old2", "new1"],
            "metadatas": [
                {"_added_at": current - 5000},
                {"_added_at": current - 6000},
                {"_added_at": current - 100},
            ],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600

        with patch.object(real_time, "time", return_value=current):
            count = retriever.cleanup_expired()

        assert count == 2
        deleted_ids = mock_collection.delete.call_args[1]["ids"]
        assert "old1" in deleted_ids
        assert "old2" in deleted_ids

    @patch("builtins.__import__")
    def test_cleanup_no_expired_returns_zero(self, mock_import):
        """无过期条目时返回 0。"""
        import time as real_time

        from src.rag.retriever import TestCaseRetriever

        current = 1000.0

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["recent"],
            "metadatas": [{"_added_at": current - 10}],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection
        retriever.ttl_seconds = 3600

        with patch.object(real_time, "time", return_value=current):
            assert retriever.cleanup_expired() == 0


class TestCapacityLimits:
    """测试缓存容量上限行为。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_skips_when_at_capacity(self, mock_chromadb):
        """达到 max_cases 时 add_case 跳过不入库。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5  # 已达上限
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever(max_cases=5)
        retriever.client = mock_client
        retriever.collection = mock_collection

        retriever.add_case(code="x=1", test_code="def test_x(): pass", passed=True)
        mock_collection.upsert.assert_not_called()

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_repair_skips_when_at_capacity(self, mock_chromadb):
        """达到 max_cases 时 add_repair 跳过不入库。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever(max_cases=3)
        retriever.client = mock_client
        retriever.collection = mock_collection

        retriever.add_repair(original_code="buggy", patch="fixed", error_category="runtime")
        mock_collection.upsert.assert_not_called()


class TestRetrieveRepairsResult:
    """测试 retrieve_repairs 返回实际结构化结果。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_repairs_returns_structured_data(self, mock_chromadb):
        """retrieve_repairs 返回包含 patch 和 similarity 的字典列表。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["error_category: runtime\ndef buggy(): pass\ndef fixed(): pass"]],
            "metadatas": [
                [
                    {
                        "error_category": "runtime",
                        "original_code": "def buggy(): pass",
                        "patch": "def fixed(): pass",
                        "distance": 0.15,
                    }
                ]
            ],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection

        results = retriever.retrieve_repairs("runtime", "def buggy(): pass")
        assert len(results) == 1
        assert results[0]["patch"] == "def fixed(): pass"
        assert results[0]["original_code"] == "def buggy(): pass"
        assert abs(results[0]["similarity"] - 0.15) < 0.01


class TestInitWithPersistPath:
    """测试带 persist_path 的初始化。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_init_with_persist_path(self, mock_chromadb):
        """指定 persist_path 时 Settings 包含 persist_directory。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client
        mock_settings = MagicMock()

        with patch("src.rag.retriever.Settings", mock_settings):
            retriever = TestCaseRetriever(persist_path="/tmp/rag_test")

        mock_settings.assert_called_once_with(persist_directory="/tmp/rag_test")
        assert retriever.persist_path == "/tmp/rag_test"

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_init_without_persist_path_uses_default(self, mock_chromadb):
        """不指定 persist_path 时使用默认 Settings（内存模式）。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client
        mock_settings = MagicMock()

        with patch("src.rag.retriever.Settings", mock_settings):
            retriever = TestCaseRetriever()

        mock_settings.assert_called_once_with()
        assert retriever.persist_path is None


class TestAddCaseMetadata:
    """测试 add_case 元数据传递。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_case_stores_custom_metadata(self, mock_chromadb):
        """add_case 将自定义 metadata 存入集合。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection

        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=True,
            metadata={"function_name": "foo", "complexity": "low"},
        )
        call_kwargs = mock_collection.upsert.call_args[1]
        meta = call_kwargs["metadatas"][0]
        assert meta["function_name"] == "foo"
        assert meta["complexity"] == "low"
        assert "_added_at" in meta
        assert meta["passed"] is True


class TestAddRepairMetadata:
    """测试 add_repair 元数据传递。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_add_repair_stores_custom_metadata(self, mock_chromadb):
        """add_repair 将自定义 metadata 存入集合。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection

        retriever.add_repair(
            original_code="def buggy(): return 1/0",
            patch="def fixed(): return 0",
            error_category="runtime",
            metadata={"line_number": 42, "file": "main.py"},
        )
        call_kwargs = mock_collection.upsert.call_args[1]
        meta = call_kwargs["metadatas"][0]
        assert meta["error_category"] == "runtime"
        assert meta["line_number"] == 42
        assert meta["file"] == "main.py"


class TestRetrieveTestCasesResult:
    """测试 retrieve_test_cases 返回结构化结果。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_retrieve_test_cases_with_results(self, mock_chromadb):
        """retrieve_test_cases 在 collection 非空时返回相似案例。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["def target_code:\ndef foo(): pass\ndef test_code:\ndef test_foo(): pass"]],
            "metadatas": [[{"test_code": "def test_foo(): pass", "distance": 0.2}]],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection

        results = retriever.retrieve_test_cases("def foo(): pass")
        assert len(results) == 1
        assert results[0]["test_code"] == "def test_foo(): pass"
        assert abs(results[0]["similarity"] - 0.2) < 0.01


class TestClearPreservesState:
    """测试 clear 后检索器仍可正常使用。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_clear_recreates_collection(self, mock_chromadb):
        """clear 应删除旧集合并重建新集合。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_old_col = MagicMock()
        mock_new_col = MagicMock()
        mock_new_col.count.return_value = 0
        mock_client.delete_collection.return_value = None
        mock_client.get_or_create_collection.side_effect = [mock_old_col, mock_new_col]

        retriever = TestCaseRetriever(collection_name="test_col")
        retriever.client = mock_client
        retriever.collection = mock_old_col

        retriever.clear()
        # clear 后 collection 应该是新的
        assert retriever.collection is mock_new_col
        mock_client.delete_collection.assert_called_once_with("test_col")

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_clear_then_add_case(self, mock_chromadb):
        """clear 后仍可继续添加案例。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_old_col = MagicMock()
        mock_new_col = MagicMock()
        mock_new_col.count.return_value = 0
        mock_client.delete_collection.return_value = None
        mock_client.get_or_create_collection.side_effect = [mock_old_col, mock_new_col]

        retriever = TestCaseRetriever(collection_name="test_col")
        retriever.client = mock_client
        retriever.collection = mock_old_col

        retriever.clear()
        assert retriever.collection is mock_new_col

        # 使用新 collection 添加
        retriever.add_case(code="x=1", test_code="def test_x(): pass", passed=True)
        mock_new_col.upsert.assert_called_once()


class TestRetrieveTestCasesTopK:
    """测试 retrieve_test_cases 的 top_k 参数。"""

    @patch("src.rag.retriever.CHROMA_AVAILABLE", True)
    @patch("src.rag.retriever.chromadb")
    def test_top_k_respected(self, mock_chromadb):
        """top_k 参数正确传递给 query。"""
        from src.rag.retriever import TestCaseRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"test_code": "test1", "distance": 0.1}]],
        }
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = TestCaseRetriever()
        retriever.client = mock_client
        retriever.collection = mock_collection

        retriever.retrieve_test_cases("target", top_k=5)
        mock_collection.query.assert_called_once()
        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["n_results"] == 5
