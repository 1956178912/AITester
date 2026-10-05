"""P2-2 专家池维度条件化回归测试（2026-10 批次）：
experiments/expert_pool._dimensions_for_category / generate_parallel 的
error_category 参数接入。

锁定口径：
1. EXPERT_POOL_CATEGORY_CONDITIONED 默认关 → _dimensions_for_category 恒
   返回原序 _EXPERT_DIMENSIONS（零行为变化）；
2. ON + error_category 命中映射表 → 命中维度排前，其余按原序补位
   （expert_count 不变，只重排序不增删）；
3. ON + 未知/空类别 → 回退原序（保守）；
4. expert_count > 维度表长度时循环复用补位口径与历史一致。
"""

from __future__ import annotations

from src.graph.expert_pool import (
    _EXPERT_DIMENSIONS,
    _dimensions_for_category,
    _take_n,
)


def test_default_off_returns_fixed_order(monkeypatch):
    monkeypatch.delenv("EXPERT_POOL_CATEGORY_CONDITIONED", raising=False)
    assert _dimensions_for_category("type_error", 3) == list(_EXPERT_DIMENSIONS)
    # 开关 OFF 时即使类别命中也不重排（零行为变化）
    assert _dimensions_for_category("index_error", 3) == list(_EXPERT_DIMENSIONS)


def test_on_with_category_reorders_priority_first(monkeypatch):
    monkeypatch.setenv("EXPERT_POOL_CATEGORY_CONDITIONED", "true")
    # type_error → type_safety 排前
    dims = _dimensions_for_category("type_error", 3)
    assert dims[0] == "type_safety"
    assert dims == ["type_safety", "boundary_handling", "dead_code_and_logic"]
    # index_error → boundary_handling 排前
    assert _dimensions_for_category("index_error", 3)[0] == "boundary_handling"
    # assertion → dead_code_and_logic 排前
    assert _dimensions_for_category("assertion", 3)[0] == "dead_code_and_logic"
    # 集合不变（只重排不增删）
    assert set(dims) == set(_EXPERT_DIMENSIONS)


def test_on_unknown_category_falls_back(monkeypatch):
    monkeypatch.setenv("EXPERT_POOL_CATEGORY_CONDITIONED", "true")
    assert _dimensions_for_category("some_future_category", 3) == list(_EXPERT_DIMENSIONS)
    assert _dimensions_for_category(None, 3) == list(_EXPERT_DIMENSIONS)
    assert _dimensions_for_category("", 3) == list(_EXPERT_DIMENSIONS)


def test_take_n_cycles_when_count_exceeds_dimensions():
    base = list(_EXPERT_DIMENSIONS)
    out = _take_n(base, 5)
    assert len(out) == 5
    # 前 3 个原序，第 4/5 个循环复用
    assert out[:3] == base
    assert out[3] == base[0]
    assert out[4] == base[1]


def test_take_n_empty_and_zero():
    assert _take_n(list(_EXPERT_DIMENSIONS), 0) == []
    assert _take_n([], 3) == []
