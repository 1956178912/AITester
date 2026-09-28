"""批次6 并行专家 Agent 池 + 交叉验证边 单元测试。

覆盖：
- expert_pool_enabled 默认关
- expert_pool_enabled 开关开启
- _expert_pool_size 边界钳制
- _normalize_patch_for_voting 正常/失败
- _patches_agree 一致/子串/不一致
- ExpertPoolAgent.cross_validate 投票排序 + 误报过滤
- ExpertPoolAgent.cross_validate 全专家失败 → 空列表
- ExpertPoolAgent.generate_parallel mock DebuggerAgent 成功
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch


def test_expert_pool_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXPERT_POOL_ENABLE", None)
        from src.graph.expert_pool import expert_pool_enabled

        assert expert_pool_enabled() is False


def test_expert_pool_switch_on() -> None:
    with patch.dict(os.environ, {"EXPERT_POOL_ENABLE": "true"}):
        from src.graph.expert_pool import expert_pool_enabled

        assert expert_pool_enabled() is True


def test_expert_pool_size_clamped() -> None:
    from src.graph.expert_pool import _expert_pool_size

    with patch.dict(os.environ, {"EXPERT_POOL_SIZE": "100"}):
        assert _expert_pool_size() == 7  # 上限 7
    with patch.dict(os.environ, {"EXPERT_POOL_SIZE": "0"}):
        assert _expert_pool_size() == 1  # 下限 1
    with patch.dict(os.environ, {"EXPERT_POOL_SIZE": "5"}):
        assert _expert_pool_size() == 5
    with patch.dict(os.environ, {"EXPERT_POOL_SIZE": "not_a_num"}):
        assert _expert_pool_size() == 3  # 缺省 3


def test_normalize_patch_for_voting_valid_python() -> None:
    from src.graph.expert_pool import _normalize_patch_for_voting

    patch_text = "```python\ndef add(a, b):\n    return a + b\n```"
    normalized = _normalize_patch_for_voting(patch_text)
    # 归一化后应含 "FunctionDef" / "Add" 等 AST 节点（而非原始缩进文本）
    assert "FunctionDef" in normalized or "add" in normalized
    # 两个语义等价但缩进不同的补丁应归一化相同
    p1 = _normalize_patch_for_voting("def add(a, b):\n    return a + b")
    p2 = _normalize_patch_for_voting("def add(a, b):\n    return a+b\n")
    assert p1 == p2  # AST 级归一化消除空格差异


def test_normalize_patch_for_voting_invalid_python() -> None:
    """归一化失败（非 Python）→ 保守用原文参与投票。"""
    from src.graph.expert_pool import _normalize_patch_for_voting

    bad = "not a python code {{{"
    assert _normalize_patch_for_voting(bad) == bad


def test_patches_agree_identical() -> None:
    from src.graph.expert_pool import _patches_agree

    assert _patches_agree("abc", "abc") is True
    assert _patches_agree("", "abc") is False


def test_patches_agree_substring() -> None:
    from src.graph.expert_pool import _patches_agree

    longer = "x = 1\ny = 2\nz = 3\nw = 4\nv = 5"
    shorter = "x = 1\ny = 2"
    assert _patches_agree(shorter, longer) is True
    assert _patches_agree(longer, shorter) is True


def test_patches_agree_different() -> None:
    from src.graph.expert_pool import _patches_agree

    assert _patches_agree("x=1", "y=2") is False


def _make_candidates(
    patches: list[str], dimensions: list[str] | None = None, failed: list[bool] | None = None
) -> list[dict[str, Any]]:
    if dimensions is None:
        dimensions = [f"dim_{i}" for i in range(len(patches))]
    if failed is None:
        failed = [False] * len(patches)
    return [
        {"dimension": dimensions[i], "patch": patches[i], "confidence": 0.8, "expert_failed": failed[i]}
        for i in range(len(patches))
    ]


def test_cross_validate_all_agree_sorted_by_confidence() -> None:
    """所有候选 patch 完全一致 → 被验证数相同，按置信度排序。"""
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    candidates = _make_candidates(
        ["def f():\n    return 1", "def f():\n    return 1", "def f():\n    return 1"],
        dimensions=["a", "b", "c"],
    )
    # 把第三个的置信度调低
    candidates[2]["confidence"] = 0.3
    verified = pool.cross_validate(candidates, min_agreement=2)
    assert len(verified) == 3
    # 前两个（置信度 0.8）排在第三个（0.3）之前
    assert verified[0]["dimension"] in ("a", "b")
    assert verified[-1]["dimension"] == "c"


def test_cross_validate_filters_low_agreement() -> None:
    """min_agreement=3 时，只被 2 个同意的候选被过滤。"""
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    # 前两个一致，第三个不同
    candidates = _make_candidates(
        ["def f():\n    return 1", "def f():\n    return 1", "def g():\n    return 2"],
        dimensions=["a", "b", "c"],
    )
    verified = pool.cross_validate(candidates, min_agreement=3)
    # 前两个被 2 个同意（a, b 互投 + 自身 = 2），第三个被 1 个同意（仅自身）
    # min_agreement=3 → 前两个（verified_count=2）也被过滤
    assert all(c["verified_count"] >= 3 for c in verified)


def test_cross_validate_all_failed_returns_empty() -> None:
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    candidates = _make_candidates(["", ""], dimensions=["a", "b"], failed=[True, True])
    verified = pool.cross_validate(candidates, min_agreement=2)
    assert verified == []


def test_generate_parallel_mocks_debugger_success() -> None:
    """generate_parallel 经 mock 的 DebuggerAgent.debug 产出候选。"""
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    pool.expert_count = 2

    fake_result = {"patch": "def f():\n    return 1", "root_cause": "x", "error_category": "assertion"}
    with patch("src.agents.debugger.DebuggerAgent") as debugger_cls:
        debugger_cls.return_value.debug.return_value = fake_result
        candidates = pool.generate_parallel(
            target_code="def f(): return 0",
            test_output="AssertionError",
            failed_cases=[{"name": "test_f", "error": "assert 0 == 1"}],
        )
    assert len(candidates) == 2
    for c in candidates:
        assert c["patch"] == "def f():\n    return 1"
        assert c["expert_failed"] is False
        assert c["confidence"] == 0.5


def test_generate_parallel_mocks_debugger_failure_degrades() -> None:
    """DebuggerAgent.debug 抛异常 → 专家保守降级（expert_failed=True, patch 空）。"""
    from src.graph.expert_pool import ExpertPoolAgent

    pool = ExpertPoolAgent()
    pool.expert_count = 2
    with patch("src.agents.debugger.DebuggerAgent") as debugger_cls:
        debugger_cls.return_value.debug.side_effect = RuntimeError("LLM down")
        candidates = pool.generate_parallel(
            target_code="def f(): return 0",
            test_output="AssertionError",
            failed_cases=[],
        )
    assert len(candidates) == 2
    for c in candidates:
        assert c["expert_failed"] is True
        assert c["patch"] == ""
