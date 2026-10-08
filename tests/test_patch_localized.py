"""R4 局部编辑通道（src/tools/patch_localized.py）单元测试。

覆盖：开关缺省 / prompt 段渲染各态 / 行级局部化合规校验（缺陷行窗口 +
函数级回退 + 模块级放行 + 窗口参数 + mode 字段）。均为纯静态纯函数，
零 LLM、零网络。
"""

from __future__ import annotations

from src.tools.patch_localized import (
    build_localized_edit_section,
    localized_edit_enabled,
    validate_edit_localization,
)

# add 在 L1-L2（缺陷行 L2 = return a - b），sub 在 L5-L6（return a + b 在 L6）
CODE = """def add(a, b):
    return a - b


def sub(a, b):
    return a + b
"""


def _loc(fn: str = "add", ls: int = 2, le: int = 2, candidates=None) -> dict:
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
    section = build_localized_edit_section(_loc("add", 2, 2))
    assert "add" in section
    assert "L2-L2" in section
    assert "edit_intents" in section


def test_build_section_multi_candidate() -> None:
    candidates = [
        {
            "function_name": "add",
            "line_start": 2,
            "line_end": 2,
            "confidence": 0.9,
            "expected_logic": "",
            "reasoning": "",
        },
        {
            "function_name": "sub",
            "line_start": 6,
            "line_end": 6,
            "confidence": 0.4,
            "expected_logic": "",
            "reasoning": "",
        },
    ]
    section = build_localized_edit_section(_loc("add", 2, 2, candidates=candidates))
    assert "候选函数" in section
    assert "`sub`" in section


def test_build_section_module_level_returns_empty() -> None:
    assert build_localized_edit_section(_loc("<module>", 0, 0)) == ""


# ─── 行级合规校验 ────────────────────────────────────────────────────────────


def test_validate_no_loc_unconstrained() -> None:
    out = validate_edit_localization(CODE, [{"old_str": "return a - b", "new_str": "return a + b"}], None)
    assert out["constrained"] is False
    assert out["mode"] == "none"
    assert out["localized_count"] == out["total"] == 1


def test_validate_module_level_unconstrained() -> None:
    out = validate_edit_localization(
        CODE, [{"old_str": "return a - b", "new_str": "return a + b"}], _loc("<module>", 0, 0)
    )
    assert out["constrained"] is False
    assert out["mode"] == "none"


def test_validate_anchor_inside_window() -> None:
    # 缺陷行 L2，默认窗口 ±3 = [1,5]，锚点 "return a - b" 在 L2 → localized
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a - b", "new_str": "return a + b"}],
        _loc("add", 2, 2),
    )
    assert out["mode"] == "line"
    assert out["localized_count"] == 1
    assert out["localized_ratio"] == 1.0
    assert out["violations"] == []
    assert out["window"] == 3


def test_validate_anchor_outside_window() -> None:
    # 锚点 "return a + b" 在 L6，缺陷行 L2 窗口 [1,5] → outside
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a + b", "new_str": "return a - b"}],
        _loc("add", 2, 2),
    )
    assert out["mode"] == "line"
    assert out["localized_count"] == 0
    assert out["violations"] == ["intent_1_outside_window:L6"]


def test_validate_anchor_not_found() -> None:
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return 999", "new_str": "return 0"}],
        _loc("add", 2, 2),
    )
    assert out["violations"] == ["intent_1_anchor_not_found"]


def test_validate_window_zero_strict() -> None:
    # window=0：锚点必须精确落在缺陷行 [2,2]；"def add(a, b):" 在 L1 → outside
    out = validate_edit_localization(
        CODE,
        [{"old_str": "def add(a, b):", "new_str": "def add(a, b):"}],
        _loc("add", 2, 2),
        window=0,
    )
    assert out["window"] == 0
    assert out["localized_count"] == 0
    assert out["violations"] == ["intent_1_outside_window:L1"]


def test_validate_mixed_ratio() -> None:
    intents = [
        {"old_str": "return a - b", "new_str": "return a + b"},  # L2（缺陷行内）
        {"old_str": "return a + b", "new_str": "return a - b"},  # L6（缺陷行外）
    ]
    out = validate_edit_localization(CODE, intents, _loc("add", 2, 2))
    assert out["localized_count"] == 1
    assert out["total"] == 2
    assert out["localized_ratio"] == 0.5


def test_validate_top3_candidate_matches_second() -> None:
    # 锚点在 L6，候选 Top-2 含 sub（缺陷行 L6）→ localized
    candidates = [
        {
            "function_name": "add",
            "line_start": 2,
            "line_end": 2,
            "confidence": 0.9,
            "expected_logic": "",
            "reasoning": "",
        },
        {
            "function_name": "sub",
            "line_start": 6,
            "line_end": 6,
            "confidence": 0.4,
            "expected_logic": "",
            "reasoning": "",
        },
    ]
    out = validate_edit_localization(
        CODE,
        [{"old_str": "return a + b", "new_str": "return a - b"}],
        _loc("add", 2, 2, candidates=candidates),
    )
    assert out["localized_count"] == 1


def test_validate_function_level_fallback() -> None:
    # 候选缺 line_start/line_end → 回退函数级（AST 函数定义范围）
    loc = {"function_name": "add", "confidence": 0.9}
    out = validate_edit_localization(CODE, [{"old_str": "return a - b", "new_str": "return a + b"}], loc)
    assert out["mode"] == "function"
    # 锚点 L2 在 add 函数定义 [1,2] 内 → localized
    assert out["localized_count"] == 1
