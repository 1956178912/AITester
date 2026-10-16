"""测试 src/agents/planner.py（此前 42% 覆盖：plan() 主流程与 LogicAnalysisResult 未触达）

通过 mock _call_llm_with_cache 覆盖 plan() 的三条路径（正常 / 缺 logic_analysis 兜底 /
target_function 聚焦），以及 LogicAnalysisResult 的构造与序列化。
不触网、不调用真实 LLM。
"""

import json
from unittest.mock import patch

from src.agents.planner import LogicAnalysisResult, PlannerAgent

# 一段合法的最小 LLM 响应（plan() 期望的结构）
_FULL_RESPONSE = {
    "function_name": "add",
    "description": "两整数相加",
    "logic_analysis": {
        "input_domain": "整数 a, b",
        "output_domain": "整数和",
        "preconditions": ["a, b 为整数"],
        "postconditions": ["result == a + b"],
        "edge_cases": ["a=0", "b=0"],
    },
    "test_cases": [{"name": "t1", "input": {"a": 1, "b": 2}, "expected": 3}],
}

_CODE = "def add(a, b):\n    return a + b\n"


class TestLogicAnalysisResult:
    """LogicAnalysisResult 构造与序列化"""

    def test_init_and_to_dict(self):
        r = LogicAnalysisResult(
            input_domain="int a,b",
            output_domain="int",
            preconditions=["a,b 整数"],
            postconditions=["r == a+b"],
            edge_cases=["a=0"],
        )
        d = r.to_dict()
        assert d == {
            "input_domain": "int a,b",
            "output_domain": "int",
            "preconditions": ["a,b 整数"],
            "postconditions": ["r == a+b"],
            "edge_cases": ["a=0"],
        }
        # 字段引用一致
        assert d["edge_cases"] == r.edge_cases


class TestPlannerPlan:
    """PlannerAgent.plan() 三条路径"""

    def _planner(self):
        return PlannerAgent()

    def test_plan_full_logic_analysis(self):
        """LLM 输出了 logic_analysis → 原样保留"""
        p = self._planner()
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_FULL_RESPONSE)) as m:
            result = p.plan(_CODE, target_function="add")
        assert result["logic_analysis"]["input_domain"] == "整数 a, b"
        assert result["function_name"] == "add"
        assert m.call_count == 1

    def test_plan_missing_logic_analysis_filled(self):
        """LLM 跳过思维链 → 填充空逻辑分析，避免下游崩溃"""
        p = self._planner()
        resp = {
            "function_name": "add",
            "description": "x",
            "test_cases": [],
        }
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(resp)):
            result = p.plan(_CODE)
        la = result["logic_analysis"]
        assert la["input_domain"] == ""
        assert la["preconditions"] == []
        assert la["edge_cases"] == []

    def test_plan_leaf_fallback_marks_m10_misattribution(self):
        """ADR-0032 写侧：叶子回退导致的 M10 降级必须带 `m10_leaf_fallback=True`。

        此前该标记**只有写侧没有读侧，且写侧本身也没有测试**——ADR-0032 声称的
        "分离提取器误诊 vs LLM 真未输出"因此既不可机读也无回归护栏。
        构造：外层 JSON 残缺（括号平衡法失败）→ extract_json_object 走叶子降级档
        返回最内层片段 `{"k": 42}` 并置哨兵；该片段无 logic_analysis → 命中 M10
        兜底分支，两个标记同时落下。
        """
        from src.utils.helpers import was_leaf_fallback_used

        p = self._planner()
        with patch.object(p, "_call_llm_with_cache", return_value='xx {"outer": stuff, {"k": 42}'):
            result = p.plan(_CODE)
        assert was_leaf_fallback_used() is True, "前提失效：叶子降级档未命中"
        assert result["logic_degraded"] is True
        assert result["m10_leaf_fallback"] is True

    def test_plan_genuine_m10_omits_leaf_fallback_marker(self):
        """反向锁：LLM 真未输出 logic_analysis（JSON 本身完好）→ 不带叶子回退标记。

        两个标记的组合才是 ADR-0032 的可分离性口径：
        (degraded=True, leaf=True) = 提取器误诊；(degraded=True, leaf=False) = 真 M10。
        """
        p = self._planner()
        resp = {"function_name": "add", "description": "x", "test_cases": []}
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(resp)):
            result = p.plan(_CODE)
        assert result["logic_degraded"] is True
        assert result.get("m10_leaf_fallback") is not True

    def test_plan_full_response_has_no_degradation_markers(self):
        """完整输出路径：logic_analysis 在场 → 显式 logic_degraded=False 且无叶子标记。"""
        p = self._planner()
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_FULL_RESPONSE)):
            result = p.plan(_CODE)
        assert result["logic_degraded"] is False
        assert "m10_leaf_fallback" not in result

    def test_plan_target_function_appended_to_query(self):
        """target_function 应进入发给 LLM 的查询文本"""
        p = self._planner()
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_FULL_RESPONSE)) as m:
            p.plan(_CODE, target_function="add")
        query = m.call_args.args[0]
        assert "add" in query
        assert "只针对以下函数" in query

    def test_plan_invalid_json_raises(self):
        """LLM 返回非 JSON → _extract_json 抛 JSONDecodeError（非文档误标的 RuntimeError）"""
        import json

        import pytest

        p = self._planner()
        with patch.object(p, "_call_llm_with_cache", return_value="这不是 JSON"), pytest.raises(json.JSONDecodeError):
            p.plan(_CODE)
