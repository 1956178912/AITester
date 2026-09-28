"""多解合成（PRISM 式）单元测试。

覆盖：
- 无重叠候选：直接合并，合成代码包含所有修改区域
- 有重叠候选：保守不合成（返回空串）
- 无候选：返回空串
- region_labels 正确反映各候选的修改区域
"""

from __future__ import annotations

import ast

from src.tools.multi_candidate import (
    CandidateResult,
    _extract_modified_regions,
    synthesize_candidates,
)

_ORIGINAL = """\
def add(a, b):
    return a + b


def mul(a, b):
    return a * b


def div(a, b):
    return a / b
"""


def _make_candidates(original: str, patches: list[str]) -> list[CandidateResult]:
    """辅助：从候选补丁列表构建 CandidateResult（static_passed=True 的）。"""
    results: list[CandidateResult] = []
    for i, patch in enumerate(patches):
        results.append(
            CandidateResult(
                index=i,
                patch=patch,
                new_code=patch,
                static_passed=True,
            )
        )
    return results


def test_extract_modified_regions_no_change() -> None:
    """候选与原代码完全相同 → 无修改区域。"""
    mod = _extract_modified_regions(_ORIGINAL, _ORIGINAL)
    assert mod == set()


def test_extract_modified_regions_single_func() -> None:
    """候选修改了 add 函数 → 修改区域 = {"add"}。"""
    patched = _ORIGINAL.replace("return a + b", "return a - b")
    mod = _extract_modified_regions(_ORIGINAL, patched)
    assert mod == {"add"}


def test_extract_modified_regions_multi_func() -> None:
    """候选修改了 add 和 mul → 修改区域 = {"add", "mul"}。"""
    patched = _ORIGINAL.replace("return a + b", "return a - b").replace("return a * b", "return a / b")
    mod = _extract_modified_regions(_ORIGINAL, patched)
    assert mod == {"add", "mul"}


def test_synth_no_overlap_merges_all_regions() -> None:
    """两个候选分别修改 add 和 mul（无重叠）→ 合成代码包含两个修改。"""
    cand_a = _ORIGINAL.replace("return a + b", "return a - b")  # 修改 add
    cand_b = _ORIGINAL.replace("return a * b", "return a // b")  # 修改 mul
    candidates = _make_candidates(_ORIGINAL, [cand_a, cand_b])

    synthesized, labels = synthesize_candidates(_ORIGINAL, candidates)
    assert synthesized, "无重叠候选应成功合成"
    ast.parse(synthesized)  # 语法校验
    # 合成代码应包含两个修改
    assert "return a - b" in synthesized
    assert "return a // b" in synthesized
    # region_labels 反映各候选的修改区域
    assert len(labels) == 2


def test_synth_overlap_returns_empty() -> None:
    """两个候选修改同一函数（重叠）→ 保守不合成（返回空串）。"""
    cand_a = _ORIGINAL.replace("return a + b", "return a - b")
    cand_b = _ORIGINAL.replace("return a + b", "return a + 1")  # 也修改 add
    candidates = _make_candidates(_ORIGINAL, [cand_a, cand_b])

    synthesized, _ = synthesize_candidates(_ORIGINAL, candidates)
    assert synthesized == "", "有重叠候选应保守不合成"


def test_synth_no_candidates_returns_empty() -> None:
    """无候选 → 返回空串。"""
    synthesized, labels = synthesize_candidates(_ORIGINAL, [])
    assert synthesized == ""
    assert labels == []


def test_synth_all_rejected_returns_empty() -> None:
    """所有候选 static_passed=False 且 static_ok=True → 返回空串。"""
    candidates = [
        CandidateResult(index=0, patch="bad", new_code=None, static_passed=False, static_reason="语法错误"),
        CandidateResult(index=1, patch="bad2", new_code=None, static_passed=False, static_reason="函数丢失"),
    ]
    synthesized, _ = synthesize_candidates(_ORIGINAL, candidates, static_ok=True)
    assert synthesized == ""


def test_synth_single_candidate_passthrough() -> None:
    """单候选 → 合成结果等于该候选本身（无其他候选可合并）。"""
    cand = _ORIGINAL.replace("return a + b", "return a - b")
    candidates = _make_candidates(_ORIGINAL, [cand])
    synthesized, labels = synthesize_candidates(_ORIGINAL, candidates)
    assert synthesized == cand
    assert len(labels) == 1


def test_synth_regions_disjoint_union() -> None:
    """三个候选修改三个不同函数（add/mul/div）→ 合成包含所有修改。"""
    cand_a = _ORIGINAL.replace("return a + b", "return a - b")
    cand_b = _ORIGINAL.replace("return a * b", "return a // b")
    cand_c = _ORIGINAL.replace("return a / b", "return a % b")
    candidates = _make_candidates(_ORIGINAL, [cand_a, cand_b, cand_c])

    synthesized, labels = synthesize_candidates(_ORIGINAL, candidates)
    assert synthesized, "三个无重叠候选应成功合成"
    ast.parse(synthesized)
    assert "return a - b" in synthesized
    assert "return a // b" in synthesized
    assert "return a % b" in synthesized
    assert len(labels) == 3
