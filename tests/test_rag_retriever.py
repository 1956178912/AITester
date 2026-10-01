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


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


# 与 test_rag_metrics.py 保持一致：未安装 chromadb 时整套用例跳过（skipif），
# 避免精简环境/CI 因缺可选依赖而误报 32 条 ERROR。
pytestmark = pytest.mark.skipif(
    not _chroma_available(),
    reason="chromadb 未安装",
)

# ============================================================================
#  fixtures
# ============================================================================


@pytest.fixture
def mock_chromadb():
    """提供 mock 的 chromadb 模块。"""
    with patch("src.rag.retriever.chromadb") as mock:
        yield mock


@pytest.fixture
def retriever(mock_chromadb):
    """创建一个 mock 的 TestCaseRetriever 实例。"""
    # 配置 mock client（chromadb 1.x 现代 API：Ephemeral/PersistentClient）
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    mock_chromadb.EphemeralClient.return_value = mock_client
    mock_chromadb.PersistentClient.return_value = mock_client

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

    def test_init_success(self, mock_chromadb, retriever):
        """验证正常初始化流程：EphemeralClient（内存模式）+ 余弦空间集合。"""
        mock_chromadb.EphemeralClient.assert_called_once()
        mock_chromadb.EphemeralClient.return_value.get_or_create_collection.assert_called_once_with(
            name="test_collection",
            metadata={"hnsw:space": "cosine"},
        )
        # 关闭后台遥测（避免上报）
        mock_chromadb.Settings.assert_called_once_with(anonymized_telemetry=False)
        assert retriever.collection_name == "test_collection"
        assert retriever.ttl_seconds == 3600
        assert retriever.max_cases == 100

    def test_init_with_persist_path(self, mock_chromadb):
        """验证带持久化路径的初始化走 PersistentClient。"""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client

        instance = TestCaseRetriever(persist_path="./rag_data")
        instance.client = mock_client
        instance.collection = mock_collection

        # 验证 PersistentClient 被调用时传入了 path
        mock_chromadb.PersistentClient.assert_called_once()
        assert mock_chromadb.PersistentClient.call_args.kwargs["path"] == "./rag_data"

    def test_init_without_chromadb_raises(self):
        """验证未安装 chromadb 时抛出 ImportError。"""
        with patch("src.rag.retriever.CHROMA_AVAILABLE", False), pytest.raises(ImportError, match="chromadb 未安装"):
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
        """验证正常检索返回相似案例，similarity 由余弦距离换算（1 - distance）。"""
        retriever.collection.count.return_value = 5

        # ChromaDB query 返回格式：外层 list 对应多个 query_texts，内层 list 对应每个 query 的结果
        # distances 与 documents 按位置一一对应；旧代码误从 metadatas 里取 distance（恒 0.0）
        retriever.collection.query.return_value = {
            "documents": [["doc1_content", "doc2_content"]],
            "metadatas": [
                [
                    {"test_code": "def test_add(): pass"},
                    {"test_code": "def test_sub(): pass"},
                ],
            ],
            "distances": [[0.05, 0.13]],
        }

        results = retriever.retrieve_test_cases("def add(a, b): return a + b", top_k=2)

        # documents 和 metadatas 都有2个元素，应该返回2条结果
        assert len(results) == 2
        assert results[0]["test_code"] == "def test_add(): pass"
        assert results[0]["similarity"] == 0.95
        assert results[1]["similarity"] == 0.87

        # 必须请求 distances 字段（否则无法换算相似度）
        call_args = retriever.collection.query.call_args
        assert "distances" in call_args.kwargs["include"]

    def test_retrieve_top_k_default(self, retriever):
        """验证默认 top_k=3。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"test_code": "test"}]],
            "distances": [[0.1]],
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
            "metadatas": [[{"patch": "fix1", "original_code": "old"}]],
            "distances": [[0.1]],
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
            "metadatas": [[{"patch": "fix1"}]],
            "distances": [[0.1]],
        }

        retriever.retrieve_repairs("syntax", "code", top_k=5)

        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["n_results"] == 5

    def test_retrieve_repairs_normalizes_invalid_error_category(self, retriever):
        """S4 安全（2026-09-29）：非枚举形态的 error_category 归一为 "unknown"，
        保证 Chroma where 子句稳定（含特殊操作符语法的值归一，避免解析异常
        或误匹配）。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "fix1"}]],
            "distances": [[0.1]],
        }

        # 含 where 子句特殊操作符语法的值 → 归一为 "unknown"
        retriever.retrieve_repairs("foo$ne:bar", "code")
        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["where"] == {"error_category": "unknown"}

    def test_retrieve_repairs_none_error_category_normalized(self, retriever):
        """S4 安全：None / 空值归一为 "unknown"（where 子句恒有确定值）。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "fix1"}]],
            "distances": [[0.1]],
        }

        retriever.retrieve_repairs(None, "code")
        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["where"] == {"error_category": "unknown"}

    def test_retrieve_repairs_enum_style_category_preserved(self, retriever):
        """S4 安全：纯枚举形态（字母数字/下划线/短横线）原样保留。"""
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "fix1"}]],
            "distances": [[0.1]],
        }

        retriever.retrieve_repairs("patch-syntax-invalid", "code")
        call_args = retriever.collection.query.call_args
        assert call_args.kwargs["where"] == {"error_category": "patch-syntax-invalid"}


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
        retriever.collection.count.return_value = 105  # 超额 → 节流检查须读到真实数字
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
        retriever.collection.count.return_value = 2
        retriever.max_cases = 100

        retriever._cleanup_expired_and_excess()

        retriever.collection.delete.assert_not_called()

    def test_cleanup_throttled_when_under_capacity(self, retriever):
        """节流：容量未满时，距上次清理不足 60s 应跳过全表扫描。"""
        retriever.collection.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"_added_at": time.time()}],
        }
        retriever.max_cases = 100
        retriever.collection.count.return_value = 1  # 未满

        # 首次调用（_last_cleanup_at == 0）必须执行
        retriever._cleanup_expired_and_excess()
        assert retriever.collection.get.call_count == 1
        assert retriever._last_cleanup_at != 0.0

        # 紧接着再调用（同一秒内，容量未满）应跳过
        retriever._cleanup_expired_and_excess()
        assert retriever.collection.get.call_count == 1  # 未再扫描

    def test_cleanup_runs_when_at_capacity(self, retriever):
        """容量满时即使刚清理过也必须再次扫描（驱逐语义）。"""
        retriever.collection.get.return_value = {
            "ids": [f"id{i}" for i in range(100)],
            "metadatas": [{"_added_at": time.time()} for _ in range(100)],
        }
        retriever.max_cases = 100
        retriever.collection.count.return_value = 100  # 已满

        retriever._cleanup_expired_and_excess()
        assert retriever.collection.get.call_count == 1

        # 容量满 → 立即再调也应重新扫描
        retriever._cleanup_expired_and_excess()
        assert retriever.collection.get.call_count == 2


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
        # count 调用顺序：_cleanup 节流检查(0) → add_case 容量检查(1) → retrieve 空集检查(1)
        retriever.collection.count.side_effect = [0, 1, 1]

        # 添加一个测试用例
        retriever.add_case(
            code="def add(a, b): return a + b",
            test_code="def test_add(): assert add(2, 3) == 5",
            passed=True,
        )

        # 模拟检索结果
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"test_code": "def test_add(): assert add(2, 3) == 5"}]],
            "distances": [[0.05]],
        }

        results = retriever.retrieve_test_cases("def add(a, b): return a + b")

        assert len(results) == 1
        assert results[0]["test_code"] == "def test_add(): assert add(2, 3) == 5"

    def test_add_repair_and_retrieve_flow(self, retriever):
        """验证修复案例的添加-检索流程。"""
        # count 调用顺序：_cleanup 节流检查(0) → add_repair 容量检查(1) → retrieve 空集检查(1)
        retriever.collection.count.side_effect = [0, 1, 1]

        # 添加修复案例
        retriever.add_repair(
            original_code="def foo(x): return x",
            patch="def foo(x): return x + 1",
            error_category="runtime",
        )

        # 模拟检索结果
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "def foo(x): return x + 1"}]],
            "distances": [[0.1]],
        }

        results = retriever.retrieve_repairs("runtime", "def foo(x): return x")

        assert len(results) == 1
        assert results[0]["patch"] == "def foo(x): return x + 1"


# ============================================================================
#  边界条件测试
# ============================================================================


class TestConcurrentUpsertGuard:
    """0.7 P1-2.1 并发护栏：写锁只在 upsert 段持有（清理/容量检查移锁外）。

    护栏目标（与 0.6 venv 双锁护栏同口径）：
    - upsert 在写锁内串行化（保证 HNSW 集合的并发写安全）；
    - 清理 + 容量检查在锁外（不再让全表清理阻塞并行 worker 的入库排队）；
    - 并发 N 个 worker 各自 add_case 时，upsert 调用次数 = N（无丢失、无重入）。
    """

    def test_concurrent_upsert_serialized(self, retriever):
        """并发入库时 upsert 次数 = worker 数，且**同一时刻至多一个**在临界区内。

        O35（2026-09-30 审查 F）修复：本用例此前给 fake_upsert 自己套了一把
        `upsert_lock` 再自增计数——串行性由测试自带的锁保证，与被测对象
        `TestCaseRetriever._write_lock` 无关，把 _write_lock 删掉断言照样过
        （用例对被测行为不可证伪）。现改为**不引入任何外部锁**，直接度量
        临界区并发度：进入时 +1、退出时 -1、期间 sleep 让出调度窗口，
        记录观测到的最大并发数；真正的串行化只能来自被测代码的写锁。
        """
        import threading

        upsert_count = {"n": 0}
        max_concurrent = {"cur": 0, "peak": 0}
        stat_lock = threading.Lock()  # 仅保护统计量读改写（不是串行化手段）

        def fake_upsert(**kwargs):
            with stat_lock:
                upsert_count["n"] += 1
                max_concurrent["cur"] += 1
                max_concurrent["peak"] = max(max_concurrent["peak"], max_concurrent["cur"])
            # 让出调度窗口：无写锁时 8 个线程会在此重叠 → peak > 1
            time.sleep(0.01)
            with stat_lock:
                max_concurrent["cur"] -= 1

        retriever.collection.upsert.side_effect = fake_upsert
        retriever.collection.count.return_value = 0  # 容量未满，全部通过
        retriever.max_cases = 1000

        workers = 8
        threads = []
        for i in range(workers):
            t = threading.Thread(
                target=retriever.add_case,
                kwargs={
                    "code": f"def f_{i}(): return {i}",
                    "test_code": f"def test_f_{i}(): assert f_{i}() == {i}",
                    "passed": True,
                },
            )
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 8 个 worker 各入库一次 → upsert 恰好 8 次（无丢失、无重入）
        assert upsert_count["n"] == workers
        # 关键断言：被测写锁必须把临界区串行化（否则 8 线程必然重叠）
        assert max_concurrent["peak"] == 1, f"upsert 临界区并发度 = {max_concurrent['peak']}（写锁失效）"

    def test_cleanup_not_blocked_by_upsert_lock(self, retriever):
        """清理（写锁外）不被 upsert 写锁阻塞——在写锁**被持有时**测清理耗时。

        实现口径（0.7 P1-2.1）：_upsert 只把 `collection.upsert` 放进写锁，
        清理 / 容量检查在锁外执行。

        O35（2026-09-30 审查 F）修复：本用例此前先在**主线程同步**跑完
        add_case（写锁早已释放），再在无竞争状态下测一次清理耗时并断言
        `elapsed < 1.0`——注释自承"若被阻塞 0.2s+ 仍 <1s"，即阈值比最坏
        情况还宽，锁是否真的在锁外对结果毫无影响（不可证伪）。
        现改为：后台线程持写锁期间（upsert 内 sleep 600ms），主线程发起
        清理并断言 < 300ms——若清理在锁内，必然被阻塞约 600ms 而失败。
        """
        import threading

        upsert_started = threading.Event()

        # fake upsert：在写锁内驻留 600ms，模拟嵌入推理 + HNSW 写入耗时
        def slow_upsert(**kwargs):
            upsert_started.set()
            time.sleep(0.6)

        retriever.collection.upsert.side_effect = slow_upsert
        retriever.collection.count.return_value = 0
        retriever.max_cases = 1000

        # 后台线程：阻塞在写锁内的 upsert
        writer = threading.Thread(
            target=retriever.add_case,
            kwargs={
                "code": "def main(): return 1",
                "test_code": "def test_main(): assert main() == 1",
                "passed": True,
            },
        )
        writer.start()
        try:
            # 确认写锁已被该线程持有（slow_upsert 已进入）
            assert upsert_started.wait(timeout=5.0), "upsert 未进入写锁（测试前提不成立）"

            # 关键断言：写锁被持有时清理仍应立即返回（阈值 300ms < 600ms 驻留）
            t0 = time.time()
            retriever._cleanup_expired_and_excess()
            elapsed = time.time() - t0
            assert elapsed < 0.3, f"清理被写锁阻塞 {elapsed:.3f}s（应在锁外执行）"
        finally:
            writer.join(timeout=5.0)
        assert not writer.is_alive()

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
        # distances 缺失时宽松回退 0.0，相似度记为 1.0（不影响排序，仅数值失真）
        assert results[0]["similarity"] == 1.0

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
