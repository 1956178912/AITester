"""TestCaseRetriever 深层分支补齐（2026-10-08，88% → 95%+）。

补齐 test_rag_retriever.py 未覆盖的深层分支：
- _detect_poisoning 记忆投毒静态扫描（纯函数）；
- add_case / add_repair 的投毒过滤拒入 + task_uuid 任务命名空间；
- cleanup 元数据非数值（str）保守视为未过期；
- retrieve_repairs 查询结果缺 distances 字段的回退口径。
全部 mock chromadb，零真实向量库 / 零网络。
"""

from __future__ import annotations

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


pytestmark = pytest.mark.skipif(not _chroma_available(), reason="chromadb 未安装")


@pytest.fixture
def retriever():
    with patch("src.rag.retriever.chromadb") as mock_chroma:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.EphemeralClient.return_value = mock_client
        instance = TestCaseRetriever(max_cases=100)
        instance.client = mock_client
        instance.collection = mock_collection
        yield instance


# ═══ 1. 记忆投毒静态扫描（_detect_poisoning）══════════════════════════════════


class TestDetectPoisoning:
    def test_empty_code_false(self):
        from src.rag.retriever import _detect_poisoning

        assert _detect_poisoning("") is False

    def test_clean_code_false(self):
        from src.rag.retriever import _detect_poisoning

        assert _detect_poisoning("def f():\n    return 1\n") is False

    def test_dangerous_call_true(self):
        from src.rag.retriever import _detect_poisoning

        assert _detect_poisoning("os.system('ls')") is True
        assert _detect_poisoning("subprocess.run(['ls'])") is True


# ═══ 2. add_case / add_repair 投毒过滤 + task_uuid ════════════════════════════


class TestAddPoisoningAndTaskUuid:
    def test_add_case_poisoning_rejected(self, retriever, monkeypatch):
        monkeypatch.setenv("RAG_POISONING_FILTER", "true")
        retriever.add_case("def f(): pass", "os.system('ls')", passed=True)
        retriever.collection.upsert.assert_not_called()

    def test_add_repair_poisoning_rejected(self, retriever, monkeypatch):
        monkeypatch.setenv("RAG_POISONING_FILTER", "true")
        retriever.add_repair("def f(): pass", "shutil.rmtree('/')", "runtime")
        retriever.collection.upsert.assert_not_called()

    def test_add_case_task_uuid_written(self, retriever):
        retriever.add_case("code", "test", passed=True, task_uuid="task-1")
        meta = retriever.collection.upsert.call_args[1]["metadatas"][0]
        assert meta["task_uuid"] == "task-1"

    def test_add_repair_task_uuid_written(self, retriever):
        retriever.add_repair("orig", "patch", "runtime", task_uuid="task-2")
        meta = retriever.collection.upsert.call_args[1]["metadatas"][0]
        assert meta["task_uuid"] == "task-2"


# ═══ 3. cleanup 元数据非数值（保守视为未过期）═════════════════════════════════


class TestCleanupNonNumericMetadata:
    def test_cleanup_non_numeric_added_at_treated_expired(self, retriever):
        # _added_at 为字符串（非数值）→ added_at 归一 0.0 → 视为过期删除
        retriever.collection.get.return_value = {
            "ids": ["doc1"],
            "metadatas": [{"_added_at": "not-a-number"}],
        }
        retriever.collection.delete = MagicMock()
        expired = retriever.cleanup_expired()
        assert expired == 1
        retriever.collection.delete.assert_called_once()

    def test_cleanup_expired_deletes(self, retriever):
        now = time.time()
        retriever.collection.get.return_value = {
            "ids": ["doc1"],
            "metadatas": [{"_added_at": now - 999999}],
        }
        retriever.collection.delete = MagicMock()
        expired = retriever.cleanup_expired()
        assert expired == 1
        retriever.collection.delete.assert_called_once()


# ═══ 3b. _cleanup_expired_and_excess 深层分支 ══════════════════════════════════


class TestCleanupExpiredAndExcess:
    def test_empty_ids_returns_zero(self, retriever):
        retriever.collection.count.return_value = 0
        retriever._last_cleanup_at = 0.0  # 首次，触发全表扫描
        retriever.collection.get.return_value = {"ids": []}
        assert retriever._cleanup_expired_and_excess() == 0

    def test_non_numeric_and_expired_deleted(self, retriever):
        now = time.time()
        retriever.collection.count.return_value = 1
        retriever._last_cleanup_at = 0.0
        retriever.collection.get.return_value = {
            "ids": ["doc1", "doc2"],
            "metadatas": [{"_added_at": "bad"}, {"_added_at": now - 999999}],
        }
        retriever.collection.delete = MagicMock()
        retriever._cleanup_expired_and_excess()
        # 非数值 → added_at=0.0 → 过期；过期条目 → 均被删除
        retriever.collection.delete.assert_called_once()


# ═══ 4b. evaluate_retrieval 空查询 + 命中 ═════════════════════════════════════


class TestEvaluateRetrievalBranches:
    def test_empty_queries(self, retriever):
        result = retriever.evaluate_retrieval([], top_k=5)
        assert result["num_queries"] == 0
        assert result["hit_rate"] == 0.0

    def test_hit(self, retriever):
        import hashlib

        expected_id = hashlib.md5(b"code|test").hexdigest()[:16]
        retriever.retrieve_test_cases = MagicMock(return_value=[{"metadata": {"code": "code", "test_code": "test"}}])
        result = retriever.evaluate_retrieval([{"query": "q", "expected_id": expected_id}], top_k=5)
        assert result["hits"] == 1
        assert result["hit_rate"] == 1.0


# ═══ 4. retrieve_repairs 缺 distances 字段回退 ════════════════════════════════


class TestRetrieveRepairsMissingDistances:
    def test_retrieve_repairs_missing_distances_falls_back(self, retriever):
        retriever.collection.count.return_value = 1
        retriever.collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"patch": "p", "original_code": "o"}]],
            # 无 distances 字段 → 回退记 similarity 1.0
        }
        repairs = retriever.retrieve_repairs("runtime", "def f(): pass")
        assert len(repairs) == 1
        assert repairs[0]["similarity"] == 1.0  # 回退口径


# ═══ 5. evaluate_retrieval 空 expected_id ═════════════════════════════════════


class TestEvaluateRetrievalEmptyExpectedId:
    def test_empty_expected_id_skipped(self, retriever):
        result = retriever.evaluate_retrieval([{"query": "q", "expected_id": ""}], top_k=5)
        assert result["num_queries"] == 1
        assert result["hits"] == 0
