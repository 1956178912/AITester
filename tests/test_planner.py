"""
单元测试：测试 PlannerAgent。

覆盖范围：
    - LogicAnalysisResult.to_dict()：序列化结果正确性
    - plan() 正常 JSON 返回、logic_analysis 缺失时填充空值
"""

import json
from unittest.mock import patch

import pytest

from src.agents.planner import LogicAnalysisResult, PlannerAgent


# ─── TestLogicAnalysisResult：逻辑分析结果序列化 ───────────────────────────────
class TestLogicAnalysisResult:
    """测试 LogicAnalysisResult 的 to_dict 方法。"""

    def test_to_dict_all_fields(self):
        """所有字段正确序列化到字典。"""
        result = LogicAnalysisResult(
            input_domain="正整数列表",
            output_domain="排序后的列表",
            preconditions=["输入非空"],
            postconditions=["输出有序"],
            edge_cases=["空列表", "单元素"],
        )
        d = result.to_dict()
        assert d["input_domain"] == "正整数列表"
        assert d["output_domain"] == "排序后的列表"
        assert d["preconditions"] == ["输入非空"]
        assert d["postconditions"] == ["输出有序"]
        assert d["edge_cases"] == ["空列表", "单元素"]

    def test_to_dict_empty_lists(self):
        """空前置/后置/边界条件列表也能正确序列化。"""
        result = LogicAnalysisResult(
            input_domain="",
            output_domain="",
            preconditions=[],
            postconditions=[],
            edge_cases=[],
        )
        d = result.to_dict()
        assert d["preconditions"] == []
        assert d["postconditions"] == []
        assert d["edge_cases"] == []


# ─── TestPlannerAgent：规划师智能体 ────────────────────────────────────────────
class TestPlannerAgent:
    """测试 PlannerAgent.plan() 方法。"""

    def _make_agent(self):
        """工厂方法：创建 PlannerAgent 实例。"""
        return PlannerAgent()

    @patch.object(PlannerAgent, "_call_llm")
    @patch.object(PlannerAgent, "_extract_json")
    def test_plan_normal_json(self, mock_extract, mock_llm):
        """正常 JSON 响应时 plan() 返回完整计划字典。"""
        mock_llm.return_value = '{"function_name": "foo", "logic_analysis": {"input_domain": "int", "output_domain": "bool", "preconditions": [], "postconditions": [], "edge_cases": []}, "test_cases": [{"name": "test_foo"}]}'
        mock_extract.return_value = json.loads(mock_llm.return_value)
        agent = self._make_agent()
        result = agent.plan("def foo(x): return x > 0", "foo")
        assert result["function_name"] == "foo"
        assert len(result["test_cases"]) == 1
        assert "logic_analysis" in result

    @patch.object(PlannerAgent, "_call_llm")
    @patch.object(PlannerAgent, "_extract_json")
    def test_plan_missing_logic_analysis_filled(self, mock_extract, mock_llm):
        """logic_analysis 缺失时自动填充空值。"""
        mock_llm.return_value = '{"function_name": "bar", "test_cases": []}'
        mock_extract.return_value = {"function_name": "bar", "test_cases": []}
        agent = self._make_agent()
        result = agent.plan("def bar(x): return x", "bar")
        assert "logic_analysis" in result
        assert result["logic_analysis"]["input_domain"] == ""
        assert result["logic_analysis"]["preconditions"] == []
        assert result["logic_analysis"]["edge_cases"] == []

    @patch.object(PlannerAgent, "_call_llm")
    @patch.object(PlannerAgent, "_extract_json")
    def test_plan_none_logic_analysis_filled(self, mock_extract, mock_llm):
        """logic_analysis 为 None 时自动填充空值。"""
        mock_llm.return_value = '{"function_name": "baz", "logic_analysis": None, "test_cases": []}'
        mock_extract.return_value = {"function_name": "baz", "logic_analysis": None, "test_cases": []}
        agent = self._make_agent()
        result = agent.plan("def baz(): pass", "baz")
        assert result["logic_analysis"]["input_domain"] == ""
        assert isinstance(result["logic_analysis"]["postconditions"], list)

    def test_plan_llm_failure_raises(self):
        """LLM 调用失败时抛出异常。"""
        agent = self._make_agent()
        with patch.object(agent, "_call_llm", side_effect=RuntimeError("API 错误")):
            with pytest.raises(RuntimeError, match="API 错误"):
                agent.plan("def foo(): pass")
