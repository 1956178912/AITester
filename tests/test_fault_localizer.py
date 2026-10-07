"""修复引擎第一阶段（2026-10-07 范式转向）FaultLocalizer 行为锁。

锁定四组行为：
1. LLM 定位输出解析（容错 markdown 围栏 / 必填字段缺失降级）；
2. gold 变更函数提取（diff 行 → AST 所属函数，嵌套取最内层）；
3. 函数级命中判定（归一叶子名比较）；
4. prompt 段落渲染与开关缺省口径。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.fault_localizer import (
    FaultLocalizerAgent,
    build_localization_prompt_section,
    fault_localizer_enabled,
    gold_changed_functions,
    localization_hit,
)

BUGGY = (
    "def add(a, b):\n"  # L1
    "    return a - b\n"  # L2（缺陷行）\n"
    "\n"
    "def helper(x):\n"  # L4
    "    return x * 2\n"  # L5
)
FIXED = "def add(a, b):\n    return a + b\n\ndef helper(x):\n    return x * 2\n"


class TestParseLocalization:
    def test_parse_ok(self) -> None:
        agent = FaultLocalizerAgent()
        raw = '{"function_name": "add", "line_start": 2, "line_end": 2, "confidence": 0.9, "reasoning": "减号误用"}'
        loc = agent._parse_localization(raw)
        assert loc is not None
        assert loc["function_name"] == "add"
        assert loc["line_start"] == 2
        assert 0.0 <= loc["confidence"] <= 1.0

    def test_parse_tolerates_markdown_fence(self) -> None:
        agent = FaultLocalizerAgent()
        raw = '```json\n{"function_name": "add", "line_start": 2, "line_end": 2, "confidence": 0.5}\n```'
        loc = agent._parse_localization(raw)
        assert loc is not None and loc["function_name"] == "add"

    def test_parse_missing_function_returns_none(self) -> None:
        agent = FaultLocalizerAgent()
        assert agent._parse_localization('{"line_start": 2}') is None
        assert agent._parse_localization("not json at all") is None

    def test_parse_line_bounds_normalized(self) -> None:
        agent = FaultLocalizerAgent()
        loc = agent._parse_localization('{"function_name": "f", "line_start": 5, "line_end": 2, "confidence": 2.0}')
        assert loc is not None
        assert loc["line_start"] == 5 and loc["line_end"] >= 5
        assert loc["confidence"] == 1.0


class TestGoldChangedFunctions:
    def test_single_function_diff(self) -> None:
        gold = gold_changed_functions(BUGGY, FIXED)
        assert gold == {"add"}

    def test_module_level_change(self) -> None:
        buggy = "X = 1\n"
        fixed = "X = 2\n"
        assert gold_changed_functions(buggy, fixed) == {"<module>"}

    def test_identical_code_returns_empty(self) -> None:
        assert gold_changed_functions(BUGGY, BUGGY) == set()

    def test_empty_inputs_return_empty(self) -> None:
        assert gold_changed_functions("", FIXED) == set()


class TestLocalizationHit:
    def test_hit(self) -> None:
        loc = {"function_name": "add"}
        assert localization_hit(loc, {"add"}) == {"localization_hit_function": True}

    def test_miss(self) -> None:
        loc = {"function_name": "helper"}
        assert localization_hit(loc, {"add"}) == {"localization_hit_function": False}

    def test_qualified_name_leaf_match(self) -> None:
        loc = {"function_name": "mod.ClassA.method_x"}
        assert localization_hit(loc, {"ClassA.method_x"})["localization_hit_function"] is True

    def test_none_loc_returns_none(self) -> None:
        assert localization_hit(None, {"add"}) is None


class TestPromptSectionAndSwitch:
    def test_section_render(self) -> None:
        section = build_localization_prompt_section(
            {"function_name": "add", "confidence": 0.9, "line_start": 2, "line_end": 2, "reasoning": "x"}
        )
        assert "add" in section and "0.90" in section

    def test_section_none_is_empty(self) -> None:
        assert build_localization_prompt_section(None) == ""

    def test_switch_default_on(self, monkeypatch) -> None:
        monkeypatch.delenv("FAULT_LOCALIZER_ENABLE", raising=False)
        assert fault_localizer_enabled() is True

    def test_switch_explicit_off(self, monkeypatch) -> None:
        monkeypatch.setenv("FAULT_LOCALIZER_ENABLE", "false")
        assert fault_localizer_enabled() is False
