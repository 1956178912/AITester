"""
TestCaseRetriever.evaluate_retrieval 单元测试（P1：RAG 检索质量指标）。

覆盖：
- 空查询列表
- Hit Rate / MRR 计算（mock collection.query）
- 无命中 / 部分命中
"""

import hashlib
from unittest.mock import patch

import pytest


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _chroma_available(),
    reason="chromadb 未安装",
)


@pytest.fixture
def retriever():
    with patch("src.rag.retriever.chromadb") as mock:
        mock.CHROMA_AVAILABLE = True
        from src.rag.retriever import TestCaseRetriever

        instance = TestCaseRetriever()
    return instance


def _case(code: str, test_code: str) -> dict:
    """构造 retrieve_test_cases 返回项（metadata 结构与 add_case 入库一致）。"""
    meta = {"code": code, "test_code": test_code, "passed": True}
    return {"test_code": test_code, "similarity": 0.9, "metadata": meta}


def _doc_id(code: str, test_code: str) -> str:
    return hashlib.md5(f"{code}|{test_code}".encode()).hexdigest()[:16]


class TestEvaluateRetrieval:
    """evaluate_retrieval 指标计算。"""

    def test_empty_queries(self, retriever):
        metrics = retriever.evaluate_retrieval([])
        assert metrics == {"num_queries": 0, "hits": 0, "hit_rate": 0.0, "mrr": 0.0}

    def test_hit_at_rank1(self, retriever):
        """期望文档排第 1 → hit_rate=1.0, mrr=1.0。"""
        code, test_code = "def a(): pass", "def test_a(): assert a()"
        with patch.object(retriever, "retrieve_test_cases", return_value=[_case(code, test_code)]):
            metrics = retriever.evaluate_retrieval([{"query": code, "expected_id": _doc_id(code, test_code)}])
        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 1.0

    def test_hit_at_rank2(self, retriever):
        """期望文档排第 2 → hit_rate=1.0, mrr=0.5。"""
        code_a, test_a = "def a(): pass", "def test_a(): pass"
        code_b, test_b = "def b(): pass", "def test_b(): assert b()"
        results = [_case(code_a, test_a), _case(code_b, test_b)]
        with patch.object(retriever, "retrieve_test_cases", return_value=results):
            metrics = retriever.evaluate_retrieval([{"query": code_b, "expected_id": _doc_id(code_b, test_b)}])
        assert metrics["hits"] == 1
        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 0.5

    def test_miss(self, retriever):
        """期望文档不在结果中 → hit_rate=0, mrr=0。"""
        code_a, test_a = "def a(): pass", "def test_a(): pass"
        other_code, other_test = "def c(): pass", "def test_c(): pass"
        with patch.object(retriever, "retrieve_test_cases", return_value=[_case(other_code, other_test)]):
            metrics = retriever.evaluate_retrieval([{"query": code_a, "expected_id": _doc_id(code_a, test_a)}])
        assert metrics["hits"] == 0
        assert metrics["hit_rate"] == 0.0
        assert metrics["mrr"] == 0.0

    def test_mixed_queries_mrr_average(self, retriever):
        """多查询 MRR 为各查询 reciprocal rank 的均值。"""
        c1, t1 = "def a(): pass", "def test_a(): pass"
        c2, t2 = "def b(): pass", "def test_b(): pass"
        c3, t3 = "def c(): pass", "def test_c(): pass"

        def fake_retrieve(query, top_k=5):
            if query == c1:  # rank 1
                return [_case(c1, t1)]
            if query == c2:  # rank 3
                return [_case(c3, t3), _case(c1, t1), _case(c2, t2)]
            return []  # c3 查询无命中（其 expected 不存在于返回）

        with patch.object(retriever, "retrieve_test_cases", side_effect=fake_retrieve):
            metrics = retriever.evaluate_retrieval(
                [
                    {"query": c1, "expected_id": _doc_id(c1, t1)},
                    {"query": c2, "expected_id": _doc_id(c2, t2)},
                    {"query": c3, "expected_id": _doc_id(c3, t3)},
                ]
            )
        # hit_rate = 2/3；mrr = (1 + 1/3 + 0) / 3
        assert metrics["num_queries"] == 3
        assert metrics["hits"] == 2
        assert metrics["hit_rate"] == round(2 / 3, 4)
        assert metrics["mrr"] == round((1 + 1 / 3) / 3, 4)
