"""P1 分层缓存统计（tiered_cache_stats）单元测试。

覆盖：
- get_workflow_stats 在任一层有命中计数时附 tiered_cache_stats 键
- 全零（无 LLM 调用）时不附 tiered_cache_stats 键（历史口径不变）
- exact_layer 命中计数与 llm_client._LLM_CACHE_HIT_STATS 同口径
- semantic_layer 命中计数与 semantic_cache.get_semantic_cache_stats 同口径
"""

from __future__ import annotations


def _reset_cache_stats() -> None:
    from src.agents.llm_client import reset_cache_hit_stats
    from src.agents.semantic_cache import reset_semantic_index

    reset_cache_hit_stats()
    reset_semantic_index()


def test_tiered_cache_stats_absent_when_no_llm_calls() -> None:
    """全零（无 LLM 调用记录）→ get_workflow_stats 不附 tiered_cache_stats 键。"""
    from src.graph.workflow import get_workflow_stats

    _reset_cache_stats()
    stats = get_workflow_stats()
    assert "tiered_cache_stats" not in stats  # 历史口径：零计数时不附带


def test_tiered_cache_stats_present_with_exact_hits() -> None:
    """精确层有命中 → tiered_cache_stats.exact_layer 反映 file_hits 计数。"""
    from src.agents.llm_client import record_cache_hit
    from src.graph.workflow import get_workflow_stats

    _reset_cache_stats()
    record_cache_hit(True)  # 1 命中
    record_cache_hit(False)  # 1 未命中
    stats = get_workflow_stats()
    assert "tiered_cache_stats" in stats
    tiered = stats["tiered_cache_stats"]
    assert tiered["exact_layer"]["hits"] == 1
    assert tiered["exact_layer"]["misses"] == 1
    assert abs(tiered["exact_layer"]["hit_rate"] - 0.5) < 1e-6


def test_tiered_cache_stats_semantic_layer_fields() -> None:
    """语义层字段完整（enabled / hits / misses / fp_* 四件套）。"""
    from src.agents.llm_client import record_cache_hit
    from src.graph.workflow import get_workflow_stats

    _reset_cache_stats()
    record_cache_hit(True)
    stats = get_workflow_stats()
    tiered = stats["tiered_cache_stats"]
    sem = tiered["semantic_layer"]
    # 语义缓存默认关（SEMANTIC_CACHE_ENABLE=false）
    assert sem["enabled"] is False
    assert set(sem.keys()) == {
        "enabled",
        "hits",
        "misses",
        "hit_rate",
        "fp_checked",
        "fp_confirmed",
        "fp_false_positive",
        "fp_rate",
    }
    # 未触发语义命中时 hits/misses 均为 0，fp_rate 为 0.0
    assert sem["hits"] == 0
    assert sem["misses"] == 0
    assert sem["hit_rate"] is None or sem["hit_rate"] == 0.0


def test_tiered_cache_stats_both_layers() -> None:
    """精确 + 语义同时有命中时，两层计数均反映。"""
    from src.agents.llm_client import record_cache_hit
    from src.agents.semantic_cache import get_semantic_index
    from src.graph.workflow import get_workflow_stats

    _reset_cache_stats()
    record_cache_hit(True)
    record_cache_hit(True)
    # 语义层：直接操作内部计数（测试场景，模拟命中）
    index = get_semantic_index()
    with index._lock:
        index._hits = 3
        index._misses = 1
    stats = get_workflow_stats()
    tiered = stats["tiered_cache_stats"]
    assert tiered["exact_layer"]["hits"] == 2
    assert tiered["semantic_layer"]["hits"] == 3
    assert tiered["semantic_layer"]["misses"] == 1
    assert abs(tiered["semantic_layer"]["hit_rate"] - 0.75) < 1e-6
