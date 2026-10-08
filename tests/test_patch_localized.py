"""R4 局部编辑通道（src/tools/patch_localized.py）单元测试。

覆盖：开关缺省 / prompt 段渲染各态 / 局部化合规校验各态（锚点落在候选内 /
候选外 / 找不到 / 模块级定位 / 无定位）。均为纯静态纯函数，零 LLM、零网络。
"""

from __future__ import annotations

from src.tools.patch_localized import (
    build_localized_edit_section,
    localized_edit_enabled,
    validate_edit_localization,
)

# add 在 L1-L2，sub 在 L5-L6
CODE = """def add(a, b):
    return a - b


def sub(a, b):
    return a + b
"""


def _loc(fn: str = "add", ls: int = 1, le: int = 2, candidates=None) -> dict:
    base = {
        "function_name": fn,
        "line_start": ls,
        "line_end": le,
        "confidence": 0.9,
        "expected_logic": "return a + b",
        "reasoning": "符号写反",
    }
    if candidates is not None:
        base["candidates"] = candidates
    return base


# ─── 开关缺省 ────────────────────────────────────────────────────────────────


def test_localized_edit_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LOCALIZED_EDIT_ENABLE", raising=False)
    assert localized_edit_enabled() is False


def test_localized_edit_enabled_true(monkeypatch) -> None:
    monkeypatch.setenv("LOCALIZED_EDIT_ENABLE", "true")
    assert localized_edit_enabled() is True


# ─── prompt 段渲染 ───────────────────────────────────────────────────────────


def test_build_section_none() -> None:
    assert build_localized_edit_section(None) == ""


def test_build_section_valid_single_candidate() -> None:
    section = build_localized_edit_section(_loc("add", 1, 2))
    assert "add" in section
    assert "L1-L2" in section
    assert "edit_intents" in section


def test_build_section_multi_candidate() -> None:
    candidates = [
        {
            "function_name": "add",
            "line_start": 1,
            "line_end": 2,
            "confidence": 0.9,
            "expected_logic": "",
            "reasoning": "",
        },
        {
            "function_name": "sub",
            "line_start": 5,
            "line_end": 6,
            "confidence": 0.4,
            "expected_logic": "",
            "reasoning": "",
        },
    ]
    section = build_localized_edit_section(_loc("add", 1, 2, candidates=candidates))
    assert "候选函数" in section
    assert "`sub`" in section


def test_build_section_module_level_returns_empty() -> None:
    assert build_localized_edit_section(_loc("<module>", 0, 0)) == ""


# ─── 局部化合规校验 ──────────────────────────────────────────────────────────


def test_validate_no_loc_unconstrained() -> None:
    out = validate_edit_localization(CODE, [{"old_str": "return a - b", "new_str": "return a + b"}], None)
    assert out["constrained"] is False
    assert out["localized_count"] == out["total"] == 1


def test_validate_module_level_unconstrained() -> None:
    out = validate_edit_localization(
        CODE, [{"old_str": "return a - b", "new_str": "return a + b"}], _loc("<module>", 0, 0)
    )
    assert out["constrained"] is False


def test_validate_anchor_inside_candidate() -> None:
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a - b", "new_str": "return a + b"}],
        _loc("add", 1, 2),
    )
    assert out["constrained"] is True
    assert out["localized_count"] == 1
    assert out["localized_ratio"] == 1.0
    assert out["violations"] == []


def test_validate_anchor_outside_candidate() -> None:
    # 锚点在 sub 函数体内（L6），但定位候选是 add（L1-L2）
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a + b", "new_str": "return a - b"}],
        _loc("add", 1, 2),
    )
    assert out["constrained"] is True
    assert out["localized_count"] == 0
    assert out["violations"] == ["intent_1_outside_candidates:L6"]


def test_validate_anchor_not_found() -> None:
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return 999", "new_str": "return 0"}],
        _loc("add", 1, 2),
    )
    assert out["violations"] == ["intent_1_anchor_not_found"]


def test_validate_mixed_ratio() -> None:
    intents = [
        {"old_str": "return a - b", "new_str": "return a + b"},  # add 内
        {"old_str": "return a + b", "new_str": "return a - b"},  # sub 内（候选外）
    ]
    out = validate_edit_localization(CODE, intents, _loc("add", 1, 2))
    assert out["localized_count"] == 1
    assert out["total"] == 2
    assert out["localized_ratio"] == 0.5


def test_validate_top3_candidate_matches_second() -> None:
    # 锚点在 sub 内，候选 Top-2 含 sub → 视为 localized
    candidates = [
        {
            "function_name": "add",
            "line_start": 1,
            "line_end": 2,
            "confidence": 0.9,
            "expected_logic": "",
            "reasoning": "",
        },
        {
            "function_name": "sub",
            "line_start": 5,
            "line_end": 6,
            "confidence": 0.4,
            "expected_logic": "",
            "reasoning": "",
        },
    ]
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a + b", "new_str": "return a - b"}],
        _loc("add", 1, 2, candidates=candidates),
    )
    assert out["localized_count"] == 1
