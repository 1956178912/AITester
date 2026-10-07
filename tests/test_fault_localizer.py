"""修复引擎第一阶段（2026-10-07 范式转向）FaultLocalizer 行为锁。

锁定四组行为：
1. LLM 定位输出解析（容错 markdown 围栏 / 必填字段缺失降级）；
2. gold 变更函数提取（diff 行 → AST 所属函数，嵌套取最内层）；
3. 函数级命中判定（归一叶子名比较）；
4. prompt 段落渲染与开关缺省口径。

修复引擎批次 II（2026-10-07）增补：
5. Top-3 候选排序 schema（{"candidates": [...]} 新格式 + 旧单对象
   向后兼容 + 候选截断/无效降级）；
6. 元素级排序指标 localization_rank_metrics（Hit@3 / MRR 数学、
   单候选退化、None 不可测口径）。
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
    localization_rank_metrics,
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


class TestRankedCandidatesSchema:
    """批次 II：Top-3 候选排序 schema（新格式解析 + 旧格式向后兼容）。"""

    def test_parse_candidates_format(self) -> None:
        agent = FaultLocalizerAgent()
        raw = (
            '{"candidates": ['
            '{"function_name": "add", "line_start": 2, "line_end": 2, "confidence": 0.9,'
            ' "expected_logic": "返回 a+b", "reasoning": "r1"},'
            '{"function_name": "helper", "line_start": 5, "line_end": 5, "confidence": 0.3, "reasoning": "r2"}'
            "]}"
        )
        loc = agent._parse_localization(raw)
        assert loc is not None
        assert loc["function_name"] == "add"  # 顶层 = 首位候选（向后兼容）
        assert [c["function_name"] for c in loc["candidates"]] == ["add", "helper"]
        assert loc["candidates"][0]["expected_logic"] == "返回 a+b"
        assert loc["candidates"][1]["expected_logic"] == ""  # 缺省空串不丢候选

    def test_parse_single_object_backward_compat(self) -> None:
        """旧 schema（批次 I 单对象）→ candidates 单元素列表。"""
        agent = FaultLocalizerAgent()
        loc = agent._parse_localization('{"function_name": "add", "line_start": 2, "line_end": 2, "confidence": 0.9}')
        assert loc is not None
        assert len(loc["candidates"]) == 1
        assert loc["candidates"][0]["function_name"] == "add"
        # 顶层字段与首位候选同构（prompt 段落/既有指标只读顶层）
        for key in ("function_name", "line_start", "line_end", "confidence"):
            assert loc[key] == loc["candidates"][0][key]

    def test_parse_candidates_truncated_to_three(self) -> None:
        agent = FaultLocalizerAgent()
        cands = ",".join(f'{{"function_name": "f{i}", "line_start": 1, "line_end": 1}}' for i in range(5))
        loc = agent._parse_localization('{"candidates": [' + cands + "]}")
        assert loc is not None
        assert len(loc["candidates"]) == 3

    def test_parse_candidates_all_invalid_returns_none(self) -> None:
        agent = FaultLocalizerAgent()
        assert agent._parse_localization('{"candidates": [{"line_start": 2}, "junk"]}') is None

    def test_parse_candidates_empty_list_falls_back_to_top_level(self) -> None:
        """candidates 为空列表时按旧单对象口径解析顶层字段。"""
        agent = FaultLocalizerAgent()
        loc = agent._parse_localization('{"candidates": [], "function_name": "add", "line_start": 2, "line_end": 2}')
        assert loc is not None and loc["function_name"] == "add"

    def test_expected_logic_capped(self) -> None:
        agent = FaultLocalizerAgent()
        raw = '{"function_name": "f", "expected_logic": "' + "x" * 500 + '"}'
        loc = agent._parse_localization(raw)
        assert loc is not None and len(loc["expected_logic"]) == 200


class TestLocalizationRankMetrics:
    """批次 II：元素级 Top-3 命中与 MRR（RGFL 排序评测口径）。"""

    @staticmethod
    def _loc(*names: str) -> dict:
        return {
            "function_name": names[0],
            "candidates": [{"function_name": n, "line_start": 1, "line_end": 1} for n in names],
        }

    def test_hit_at_3_and_mrr_second_rank(self) -> None:
        m = localization_rank_metrics(self._loc("helper", "add", "other"), {"add"})
        assert m == {"localization_hit_function_at_3": True, "localization_mrr": 0.5}

    def test_first_rank_full_credit(self) -> None:
        m = localization_rank_metrics(self._loc("add", "helper"), {"add"})
        assert m is not None
        assert m["localization_mrr"] == 1.0

    def test_third_rank_mrr(self) -> None:
        m = localization_rank_metrics(self._loc("a", "b", "add"), {"add"})
        assert m is not None
        assert m["localization_hit_function_at_3"] is True
        assert abs(m["localization_mrr"] - 1 / 3) < 1e-9

    def test_beyond_rank_three_no_credit(self) -> None:
        m = localization_rank_metrics(self._loc("a", "b", "c", "add"), {"add"})
        assert m == {"localization_hit_function_at_3": False, "localization_mrr": 0.0}

    def test_fallback_single_candidate_legacy_schema(self) -> None:
        """批次 I 旧 schema（无 candidates）退化为单候选：at_3 = hit@1。"""
        hit = localization_rank_metrics({"function_name": "add"}, {"add"})
        assert hit == {"localization_hit_function_at_3": True, "localization_mrr": 1.0}
        miss = localization_rank_metrics({"function_name": "helper"}, {"add"})
        assert miss == {"localization_hit_function_at_3": False, "localization_mrr": 0.0}

    def test_duplicate_candidates_deduped(self) -> None:
        m = localization_rank_metrics(self._loc("add", "add", "helper"), {"add"})
        assert m is not None and m["localization_mrr"] == 1.0

    def test_qualified_leaf_normalization(self) -> None:
        m = localization_rank_metrics(self._loc("mod.ClassA.helper", "mod.add"), {"add"})
        assert m is not None
        assert m["localization_hit_function_at_3"] is True
        assert m["localization_mrr"] == 0.5

    def test_none_cases(self) -> None:
        assert localization_rank_metrics(None, {"add"}) is None
        assert localization_rank_metrics(self._loc("add"), set()) is None
        assert localization_rank_metrics({"candidates": [{"line_start": 1}]}, {"add"}) is None


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
