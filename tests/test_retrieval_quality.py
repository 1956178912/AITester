"""Retrieval quality (Recall@k) observation — STVR empirical-study batch.

Locks the conservative-None caliber of ``compute_recall_at_k`` and the
key-set-isomorphism of the augmented rag_stat dict:

- empty / None refs → None (unmeasurable, NOT 0.0);
- default-disabled switch → None (historical caliber zero change);
- enabled + enough refs → |relevant in top-k| / k;
- insufficient refs (len < k) → None (denominator-shrink guard);
- the augmented stat dict always carries ``recall_at_k`` /
  ``retrieval_relevance`` / ``retrieval_relevant_count`` keys
  (None / 0 placeholders when disabled or unmeasurable), so downstream
  consumers (experiments/analysis_parts/rag_analysis.py) see a stable
  key set and historical JSONs (without these keys) degrade gracefully.
"""

from __future__ import annotations

import pytest

from src.measurement.retrieval_quality import (
    _recall_enabled,
    _recall_k,
    _relevant_threshold,
    compute_recall_at_k,
    rag_stat_with_recall,
    retrieval_relevance,
)


def _refs(similarities: list[float]) -> list[dict]:
    """Build a refs list shaped like TestCaseRetriever output (sorted desc)."""
    return [{"similarity": s, "test_code": f"t{i}", "metadata": {}} for i, s in enumerate(similarities)]


class TestComputeRecallAtK:
    """Core 3-state + guard calibers (zero LLM cost)."""

    def test_none_refs_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """refs=None (RAG not enabled / no history) → None, not 0.0."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        assert compute_recall_at_k(None, k=3, threshold=0.7) is None

    def test_empty_refs_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        assert compute_recall_at_k([], k=3, threshold=0.7) is None

    def test_disabled_switch_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default (RAG_RETRIEVAL_RECALL_ENABLE unset/false) → None even with refs."""
        monkeypatch.delenv("RAG_RETRIEVAL_RECALL_ENABLE", raising=False)
        refs = _refs([0.9, 0.85, 0.8, 0.75])
        assert compute_recall_at_k(refs, k=3, threshold=0.7) is None

    def test_enabled_all_relevant_is_1_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.95, 0.9, 0.85, 0.8])  # all >= 0.7
        assert compute_recall_at_k(refs, k=3, threshold=0.7) == 1.0

    def test_enabled_half_relevant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """top-3 = [0.9, 0.5, 0.4] with threshold 0.7 → 1/3 relevant."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.9, 0.5, 0.4, 0.3])
        assert compute_recall_at_k(refs, k=3, threshold=0.7) == pytest.approx(1 / 3, abs=1e-4)

    def test_enabled_none_relevant_is_0_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """top-k all below threshold → 0.0 (retrieved but all low-relevance)."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.5, 0.4, 0.3, 0.2])
        assert compute_recall_at_k(refs, k=3, threshold=0.7) == 0.0

    def test_insufficient_refs_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """len(refs) < k → None (cannot measure recall on a partial top-k)."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.9, 0.8])  # only 2, k=3
        assert compute_recall_at_k(refs, k=3, threshold=0.7) is None

    def test_explicit_k_and_threshold_override_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit k/threshold args take precedence over env vars."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.9, 0.8, 0.7, 0.6, 0.5])
        # k=5, threshold=0.6 → 4 of top-5 relevant (0.9, 0.8, 0.7, 0.6) → 0.8
        assert compute_recall_at_k(refs, k=5, threshold=0.6) == pytest.approx(0.8, abs=1e-4)

    def test_non_dict_ref_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-dict elements in refs are skipped (robust against mock shapes)."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs: list = [{"similarity": 0.9}, "str-not-dict", 42, {"similarity": 0.5}, {"similarity": 0.8}]
        # k=3 → top-3 = [0.9, "str", 42] → only 1 relevant (0.9) → 1/3
        assert compute_recall_at_k(refs, k=3, threshold=0.7) == pytest.approx(1 / 3, abs=1e-4)


class TestRetrievalRelevance:
    """retrieval_relevance() returns a stable key-set dict (None placeholders)."""

    def test_none_refs_stable_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        out = retrieval_relevance(None)
        assert out is not None
        assert set(out.keys()) == {"retrieval_relevance", "retrieval_relevant_count", "retrieval_total_refs"}
        assert out["retrieval_relevance"] is None
        assert out["retrieval_relevant_count"] == 0
        assert out["retrieval_total_refs"] == 0

    def test_disabled_stable_keys_with_zero_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAG_RETRIEVAL_RECALL_ENABLE", raising=False)
        out = retrieval_relevance(_refs([0.9, 0.8, 0.7]))
        assert out is not None
        assert out["retrieval_relevance"] is None  # disabled → not measured
        assert out["retrieval_total_refs"] == 3  # count still reported (observed refs)

    def test_enabled_populates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        out = retrieval_relevance(_refs([0.9, 0.8, 0.7, 0.6]))
        assert out is not None
        assert out["retrieval_relevance"] == 1.0  # 3/3 relevant
        assert out["retrieval_total_refs"] == 4


class TestRagStatWithRecall:
    """Key-set-isomorphism: augmented stat dict always carries the new keys."""

    def test_disabled_keys_present_with_none_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RAG_RETRIEVAL_RECALL_ENABLE off → keys present, None/0 placeholders."""
        monkeypatch.delenv("RAG_RETRIEVAL_RECALL_ENABLE", raising=False)
        stat = rag_stat_with_recall(_refs([0.9, 0.8]), "test_cases")
        assert stat is not None
        assert "recall_at_k" in stat
        assert "retrieval_relevance" in stat
        assert "retrieval_relevant_count" in stat
        assert stat["recall_at_k"] is None
        assert stat["retrieval_relevance"] is None
        assert stat["retrieval_relevant_count"] == 0
        # historical fields preserved
        assert stat["kind"] == "test_cases"
        assert stat["results"] == 2

    def test_enabled_populates_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        stat = rag_stat_with_recall(_refs([0.9, 0.8, 0.7]), "test_cases")
        assert stat is not None
        assert stat["recall_at_k"] == 1.0
        assert stat["retrieval_relevance"] == 1.0
        assert stat["retrieval_relevant_count"] == 3

    def test_none_refs_returns_none_stat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """refs=None → whole stat is None (no rag happened, downstream skips)."""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        assert rag_stat_with_recall(None, "test_cases") is None


class TestEnvReaders:
    """Env-var default & parse calibers."""

    def test_default_k_is_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAG_RECALL_K", raising=False)
        assert _recall_k() == 3

    def test_invalid_k_falls_back_to_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for bad in ["abc", "0", "-1", "999", ""]:
            monkeypatch.setenv("RAG_RECALL_K", bad)
            assert _recall_k() == 3

    def test_valid_k_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RECALL_K", "5")
        assert _recall_k() == 5

    def test_default_threshold_is_0_7(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAG_RECALL_RELEVANT_THRESHOLD", raising=False)
        assert _relevant_threshold() == 0.7

    def test_threshold_clamped_to_unit_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RECALL_RELEVANT_THRESHOLD", "5")
        assert _relevant_threshold() == 1.0
        monkeypatch.setenv("RAG_RECALL_RELEVANT_THRESHOLD", "-3")
        assert _relevant_threshold() == 0.0

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAG_RETRIEVAL_RECALL_ENABLE", raising=False)
        assert _recall_enabled() is False
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        assert _recall_enabled() is True


class TestA22RelevantCountDirect:
    """A22（2026-10-18 第三方审查 P2）：一次解析有效 k、直接返回整数相关数。

    历史缺陷：`retrieval_relevance()` 先用内部默认 k 算比例，再
    `effective_k = k if (k and len(refs) >= k) else len(refs)` 反推——
    k=None 且 len(refs) > 默认 k 时分母误用 len(refs)，相关数被放大
    （top-3 内 2 个相关、refs 共 4 条 → round(2/3*4)=3）。
    """

    def test_k_none_uses_default_k_not_refs_len(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        monkeypatch.setenv("RAG_RECALL_K", "3")
        # top-3 = [0.9, 0.8, 0.5] → 2 相关；第 4 条 0.95 不在 top-k 内
        refs = _refs([0.9, 0.8, 0.5, 0.95])
        out = retrieval_relevance(refs)
        assert out is not None
        assert out["retrieval_relevant_count"] == 2, "k=None 时必须按默认 k=3 直接计数（不得用 len(refs) 反推放大）"
        assert out["retrieval_relevance"] == pytest.approx(round(2 / 3, 4))
        assert out["retrieval_relevant_count"] <= _recall_k()

    def test_explicit_k_resolved_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.9, 0.8, 0.75, 0.7, 0.65])
        out = retrieval_relevance(refs, k=5, threshold=0.7)
        assert out is not None
        assert out["retrieval_relevant_count"] == 4, "0.9/0.8/0.75/0.7 共 4 个相关"
        assert out["retrieval_relevance"] == pytest.approx(0.8)

    def test_count_consistent_with_recall_and_never_exceeds_k(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.9, 0.8, 0.7, 0.9, 0.9, 0.9])
        out = retrieval_relevance(refs, k=3, threshold=0.7)
        assert out is not None
        # 直接由比例派生关系：recall = count/k（整数计数为事实源）
        assert out["retrieval_relevance"] == pytest.approx(round(out["retrieval_relevant_count"] / 3, 4))
        assert 0 <= out["retrieval_relevant_count"] <= 3

    def test_unmeasurable_cases_return_zero_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        # refs 不足 k：不可测量（None）+ 计数 0
        out = retrieval_relevance(_refs([0.9, 0.8]), k=3)
        assert out is not None
        assert out["retrieval_relevance"] is None
        assert out["retrieval_relevant_count"] == 0
        # 开关关：同样 None + 0
        monkeypatch.delenv("RAG_RETRIEVAL_RECALL_ENABLE", raising=False)
        out2 = retrieval_relevance(_refs([0.9, 0.8, 0.7]))
        assert out2 is not None
        assert out2["retrieval_relevance"] is None
        assert out2["retrieval_relevant_count"] == 0

    def test_compute_recall_matches_evaluate_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """比例与整数计数同源：compute_recall_at_k 与 retrieval_relevance 自洽。"""
        monkeypatch.setenv("RAG_RETRIEVAL_RECALL_ENABLE", "true")
        refs = _refs([0.95, 0.4, 0.9, 0.85, 0.2])
        recall = compute_recall_at_k(refs)
        out = retrieval_relevance(refs)
        assert recall == pytest.approx(round(2 / 3, 4))  # top-3: 0.95 相关 / 0.4 不相关 / 0.9 相关
        assert out is not None
        assert out["retrieval_relevance"] == recall
        assert out["retrieval_relevant_count"] == 2
