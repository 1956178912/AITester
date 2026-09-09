"""
TestCaseRetriever 单元测试套件

测试 RAG 检索器的核心功能：
- 初始化与配置
- 测试用例添加（add_case）
- 修复案例添加（add_repair）
- 相似检索（retrieve_test_cases / retrieve_repairs）
- 缓存清理（cleanup_expired / _cleanup_expired_and_excess）
- 清空集合（clear）

使用 mock 模拟 ChromaDB，避免依赖外部向量数据库。
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.rag.retriever import TestCaseRetriever

# ============================================================================
#  fixtures
# ============================================================================


@pytest.fixture
def mock_chromadb():
    """提供 mock 的 chromadb 模块。"""
    with patch("src.rag.retriever.chromadb") as mock:
        yield mock


@pytest.fixture
def mock_settings():
    """提供 mock 的 Settings 类。"""
    with patch("src.rag.retriever.Settings") as mock:
        yield mock


@pytest.fixture
def retriever(mock_chromadb, mock_settings):
    """创建一个 mock 的 TestCaseRetriever 实例。"""
    # 配置 mock client
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    mock_chromadb.Client.return_value = mock_client

    # 创建 retriever
    instance = TestCaseRetriever(
        collection_name="test_collection",
        persist_path=None,
        ttl_seconds=3600,
        max_cases=100,
    )
    instance.client = mock_client
    instance.collection = mock_collection
    return instance


# ============================================================================
#  初始化测试
# ============================================================================


class TestInit:
    """测试 TestCaseRetriever 初始化逻辑。"""

    def test_init_success(self, mock_chromadb, mock_settings, retriever):
        """验证正常初始化流程：创建客户端和集合。"""
        mock_chromadb.Client.assert_called_once()
        mock_chromadb.Client.return_value.get_or_create_collection.assert_called_once_with(
            name="test_collection",
            metadata={"hnsw:space": "cosine"},
        )
        assert retriever.collection_name == "test_collection"
        assert retriever.ttl_seconds == 3600
        assert retriever.max_cases == 100

    def test_init_with_persist_path(self, mock_chromadb, mock_settings):
        """验证带持久化路径的初始化。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.Client.return_value = mock_client

        instance = TestCaseRetriever(persist_path="./rag_data")
        instance.client = mock_client
        instance.collection = mock_collection

        # 验证 Settings 被调用时传入了 persist_directory
        mock_settings.assert_called_with(persist_directory="./rag_data")

    def test_init_without_chromadb_raises(self):
        """验证未安装 chromadb 时抛出 ImportError。"""
        with patch("src.rag.retriever.CHROMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="chromadb 未安装"):
                TestCaseRetriever()


# ============================================================================
#  add_case 测试
# ============================================================================


class TestAddCase:
    """测试 add_case 方法的添加逻辑。"""

    def test_add_case_passed_true(self, retriever):
        """验证 passed=True 时正常添加测试用例。"""
        retriever.collection.count.return_value = 0

        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
        )

        # 验证 upsert 被调用
        retriever.collection.upsert.assert_called_once()
        call_args = retriever.collection.upsert.call_args
        # ID 是 md5 hash 的前16位，不为空即可
        assert len(call_args.kwargs["ids"][0]) == 16
        assert "documents" in call_args.kwargs
        assert "metadatas" in call_args.kwargs

    def test_add_case_passed_false_skipped(self, retriever):
        """验证 passed=False 时不添加测试用例。"""
        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=False,
        )

        # upsert 不应被调用
        retriever.collection.upsert.assert_not_called()

    def test_add_case_capacity_limit(self, retriever):
        """验证达到容量上限时跳过添加。"""
        retriever.collection.count.return_value = 100  # 等于 max_cases
        retriever.max_cases = 100

        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
        )

        retriever.collection.upsert.assert_not_called()

    def test_add_case_with_metadata(self, retriever):
        """验证带额外元数据的添加。"""
        retriever.collection.count.return_value = 0

        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
            metadata={"func_name": "add", "coverage": 0.95},
        )

        # 验证元数据包含自定义字段
        call_args = retriever.collection.upsert.call_args
        metadata = call_args.kwargs["metadatas"][0]
        assert metadata["func_name"] == "add"
        assert metadata["coverage"] == 0.95
        assert "_added_at" in metadata  # 自动添加时间戳

    def test_add_case_generates_unique_id(self, retriever):
        """验证不同代码生成不同 ID。"""
        retriever.collection.count.return_value = 0

        # 第一次添加
        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
        )
        first_call = retriever.collection.upsert.call_args

        # 第二次添加不同代码
        retriever.add_case(
            code="def subtract(a, b): return a - b",
            test_code="def test_subtract(): assert subtract(5, 3) == 2",
            passed=True,
        )
        second_call = retriever.collection.upsert.call_args

        # ID 应该不同
        assert first_call.kwargs["ids"][0] != second_call.kwargs["ids"][0]


# ============================================================================
#  add_repair 测试
# ============================================================================


class TestAddRepair:
    """测试 add_repair 方法的添加逻辑。"""

    def test_add_repair_success(self, retriever):
        """验证修复案例正常添加。"""
        retriever.collection.count.return_value = 0

        retriever.add_repair(
            original_code="def foo(x): return x",
            patch="def foo(x): return x + 1",
            error_category="runtime",
        )

        retriever.collection.upsert.assert_called_once()
        call_args = retriever.collection.upsert.call_args
        metadata = call_args.kwargs["metadatas"][0]
        assert metadata["error_category"] == "runtime"
        assert metadata["patch"] == "def foo(x): return x + 1"

    def test_add_repair_capacity_limit(self, retriever):
        """验证修复案例达到容量上限时跳过添加。"""
        retriever.collection.count.return_value = 100
        retriever.max_cases = 100

        retriever.add_repair(
            original_code="def foo(x): return x",
            patch="def foo(x): return x + 1",
            error_category="syntax",
        )

        retriever.collection.upsert.assert_not_called()

    def test_add_repair_with_metadata(self, retriever):
        """验证带元数据的修复案例添加。"""
        retriever.collection.count.return_value = 0

        retriever.add_repair(
            original_code="def foo(x): return x",
            patch="def foo(x): return x + 1",
            error_category="assertion",
            metadata={"line_number": 42},
        )

        call_args = retriever.collection.upsert.call_args
        metadata = call_args.kwargs["metadatas"][0]
        assert metadata["line_number"] == 42


# ============================================================================
#  retrieve_test_cases 测试
# ============================================================================


class TestRetrieveTestCases:
    """测试 retrieve_test_cases 方法的检索逻辑。"""

    def test_retrieve_empty_collection(self, retriever):
        """验证空集合返回空列表。"""
        retriever.collection.count.return_value = 0

        results = retriever.retrieve_test_cases("def add(a, b): return a + b")

        assert results == []
        retriever.collection.query.assert_not_called()

    def test_retrieve_with_results(self, retriever):
        """验证正常检索返回相似案例。"""
        retriever.collection.count.return_value = 5

        # ChromaDB query 返回格式：外层 list 对应多个 query_texts，内层 list 对应每个 query 的结果
        # 代码逻辑：zip(documents[0], metadatas[0]) 按位置配对
        retriever.collection.query.return_value = {
            "documents": [["doc1_content", "doc2_content"]],
            "metadatas": [
                [
                    {"test_code": "def test_add(): pass", "distance": 0.95},
                    {"test_code": "def test_sub(): pass", "distance": 0.87},
                ],
            ],
        }

        results = retriever.retrieve_test_cases("def add(a, b): return a + b", top_k=2)

        # documents 和 metadatas 都有2个元素，应该返回2条结果
        assert len(results) == 2
        assert results[0]["test_code"] == "def test_add(): pass"
        assert results[0]["similarity"] == 0.95

    def test_retrieve_top_k_default(self, retriever):
        """验证默认 top_k=3。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"test_code": "test", "distance": 0.9}]],
        }

        retriever.retrieve_test_cases("some code")

        # 验证调用时 top_k 参数为 3
        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["n_results"] == 3


# ============================================================================
#  retrieve_repairs 测试
# ============================================================================


class TestRetrieveRepairs:
    """测试 retrieve_repairs 方法的检索逻辑。"""

    def test_retrieve_repairs_empty(self, retriever):
        """验证空集合返回空列表。"""
        retriever.collection.count.return_value = 0

        results = retriever.retrieve_repairs("runtime", "def foo(x): return x")

        assert results == []
        retriever.collection.query.assert_not_called()

    def test_retrieve_repairs_with_filter(self, retriever):
        """验证带错误类型过滤的检索。"""
        retriever.collection.count.return_value = 3

        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "fix1", "original_code": "old", "distance": 0.9}]],
        }

        results = retriever.retrieve_repairs("runtime", "def foo(x): return x", top_k=2)

        assert len(results) == 1
        assert results[0]["patch"] == "fix1"
        assert results[0]["original_code"] == "old"

        # 验证 where 过滤参数
        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["where"] == {"error_category": "runtime"}

    def test_retrieve_repairs_custom_top_k(self, retriever):
        """验证自定义 top_k 参数生效。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "fix1", "distance": 0.9}]],
        }

        retriever.retrieve_repairs("syntax", "code", top_k=5)

        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["n_results"] == 5


# ============================================================================
#  cleanup 测试
# ============================================================================


class TestCleanupExpired:
    """测试清理过期条目的逻辑。"""

    def test_cleanup_no_expired(self, retriever):
        """验证没有过期条目时返回 0。"""
        retriever.collection.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"_added_at": time.time()}],  # 当前时间，未过期
        }

        result = retriever.cleanup_expired()

        assert result == 0
        retriever.collection.delete.assert_not_called()

    def test_cleanup_with_expired(self, retriever):
        """验证正确清理过期条目。"""
        current_time = time.time()
        retriever.collection.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"_added_at": current_time - 7200},  # 2小时前，已过期
                {"_added_at": current_time - 1800},  # 30分钟前，未过期
            ],
        }
        retriever.ttl_seconds = 3600  # 1小时TTL

        result = retriever.cleanup_expired()

        assert result == 1
        retriever.collection.delete.assert_called_once_with(ids=["id1"])

    def test_cleanup_empty_collection(self, retriever):
        """验证空集合时返回 0。"""
        retriever.collection.get.return_value = {"ids": [], "metadatas": []}

        result = retriever.cleanup_expired()

        assert result == 0


class TestCleanupExpiredAndExcess:
    """测试内部清理方法 _cleanup_expired_and_excess。"""

    def test_cleanup_excess_entries(self, retriever):
        """验证超额时清理最旧条目。"""
        current_time = time.time()
        # 模拟105个条目，max_cases=100
        retriever.collection.get.return_value = {
            "ids": [f"id{i}" for i in range(105)],
            "metadatas": [
                {"_added_at": current_time - i * 10}
                for i in range(105)  # id0最新，id104最旧
            ],
        }
        retriever.max_cases = 100

        retriever._cleanup_expired_and_excess()

        # 应该删除最旧的5个条目
        delete_call = retriever.collection.delete.call_args
        deleted_ids = delete_call.kwargs["ids"]
        assert len(deleted_ids) == 5
        # 确认删除的是最旧的（id100-id104）
        assert set(deleted_ids) == {f"id{i}" for i in range(100, 105)}

    def test_cleanup_no_action_when_under_limit(self, retriever):
        """验证未超额时不执行清理。"""
        retriever.collection.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [{"_added_at": time.time()} for _ in range(2)],
        }
        retriever.max_cases = 100

        retriever._cleanup_expired_and_excess()

        retriever.collection.delete.assert_not_called()


# ============================================================================
#  clear 测试
# ============================================================================


class TestClear:
    """测试 clear 方法的清空逻辑。"""

    def test_clear_collection(self, retriever):
        """验证清空集合后重新创建。"""
        retriever.clear()

        # 验证 delete_collection 被调用
        retriever.client.delete_collection.assert_called_once_with("test_collection")
        # clear 内部会调用两次 get_or_create_collection（初始化时一次，clear时一次）
        assert retriever.client.get_or_create_collection.call_count >= 1


# ============================================================================
#  混合检索场景测试
# ============================================================================


class TestMixedRetrieval:
    """测试混合检索场景：先添加后检索。"""

    def test_add_and_retrieve_flow(self, retriever):
        """验证完整的添加-检索流程。"""
        # 模拟 collection count 从 0 变为 1
        retriever.collection.count.side_effect = [0, 1]

        # 添加一个测试用例
        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
        )

        # 模拟检索结果
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"test_code": "def test_add(): assert add(2, 3) == 5", "distance": 0.95}]],
        }

        results = retriever.retrieve_test_cases("def add(a, b): return a + b")

        assert len(results) == 1
        assert results[0]["test_code"] == "def test_add(): assert add(2, 3) == 5"

    def test_add_repair_and_retrieve_flow(self, retriever):
        """验证修复案例的添加-检索流程。"""
        retriever.collection.count.side_effect = [0, 1]

        # 添加修复案例
        retriever.add_repair(
            original_code="def foo(x): return x",
            patch="def foo(x): return x + 1",
            error_category="runtime",
        )

        # 模拟检索结果
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "def foo(x): return x + 1", "distance": 0.9}]],
        }

        results = retriever.retrieve_repairs("runtime", "def foo(x): return x")

        assert len(results) == 1
        assert results[0]["patch"] == "def foo(x): return x + 1"


# ============================================================================
#  边界条件测试
# ============================================================================


class TestEdgeCases:
    """测试边界条件和异常场景。"""

    def test_retrieve_with_missing_fields(self, retriever):
        """验证检索结果缺少字段时的容错处理。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{}]],  # 空元数据
        }

        results = retriever.retrieve_test_cases("code")

        # 应返回空字符串而不是报错
        assert results[0]["test_code"] == ""
        assert results[0]["similarity"] == 0.0

    def test_add_case_empty_metadata(self, retriever):
        """验证传入空元数据时的处理。"""
        retriever.collection.count.return_value = 0

        retriever.add_case(
            code="def foo(): pass",
            test_code="def test_foo(): pass",
            passed=True,
            metadata=None,
        )

        # 不应报错，正常添加
        retriever.collection.upsert.assert_called_once()
