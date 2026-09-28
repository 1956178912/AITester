"""P0 测试预言增强（OracleEnhancer）单元测试。

覆盖：
- 开关默认关（ORACLE_ENHANCE_ENABLE 未设 → oracle_enhance_enabled() False）
- 开关开启（monkeypatch 环境变量）
- enhance() 空 test_cases 保守降级
- enhance() LLM 成功时按 case_name 对齐回写 oracle 字段
- enhance() LLM 失败（RuntimeError）保守降级
- enhance() LLM 输出非列表保守降级
- _apply_oracles 对齐缺失时跳过
- oracle_confidence 越界钳制
- _planner_node 集成：ORACLE_ENHANCE_ENABLE=true 时写入 oracle_enhanced 字段
- _planner_node 默认关时 update dict 不含 oracle_enhanced 键（历史口径不变）
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch


def test_oracle_enhance_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ORACLE_ENHANCE_ENABLE", None)
        from src.agents.oracle_enhancer import oracle_enhance_enabled

        assert oracle_enhance_enabled() is False


def test_oracle_enhance_switch_on() -> None:
    with patch.dict(os.environ, {"ORACLE_ENHANCE_ENABLE": "true"}):
        from src.agents.oracle_enhancer import oracle_enhance_enabled

        assert oracle_enhance_enabled() is True


def test_enhance_empty_test_cases_degrades() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    agent = MagicMock(spec=OracleEnhancerAgent)
    plan: dict[str, Any] = {"test_cases": [], "logic_analysis": {}}
    OracleEnhancerAgent.enhance(agent, plan)
    assert plan["oracle_enhanced"] is False
    assert agent._call_llm_with_cache.call_count == 0


def _make_agent_stub(oracle_json: str) -> MagicMock:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    agent = MagicMock(spec=OracleEnhancerAgent)
    agent._call_llm_with_cache.return_value = oracle_json

    def _fake_extract(raw: str) -> Any:
        return json.loads(raw)

    agent._extract_json.side_effect = _fake_extract
    return agent


def test_enhance_success_aligns_oracles() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    oracle_response = json.dumps(
        [
            {
                "case_name": "test_add",
                "oracle": "assert add(1, 2) == 3",
                "oracle_source": "postcondition",
                "oracle_confidence": 0.9,
            },
            {
                "case_name": "test_divide_zero",
                "oracle": "pytest.raises(ZeroDivisionError)",
                "oracle_source": "edge_case",
                "oracle_confidence": 0.7,
            },
        ]
    )
    agent = _make_agent_stub(oracle_response)
    plan: dict[str, Any] = {
        "test_cases": [
            {"case_name": "test_add", "input_args": {"a": 1, "b": 2}},
            {"case_name": "test_divide_zero", "input_args": {"a": 1, "b": 0}},
            {"case_name": "test_missing_oracle", "input_args": {}},
        ],
        "logic_analysis": {"postconditions": ["result == a + b"]},
    }
    result = OracleEnhancerAgent.enhance(agent, plan)
    assert result["oracle_enhanced"] is True
    tc0 = result["test_cases"][0]
    assert tc0["oracle"] == "assert add(1, 2) == 3"
    assert tc0["oracle_source"] == "postcondition"
    assert tc0["oracle_confidence"] == 0.9
    tc2 = result["test_cases"][2]
    assert "oracle" not in tc2  # 对齐缺失：保守跳过


def test_enhance_llm_failure_degrades() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    agent = MagicMock(spec=OracleEnhancerAgent)
    agent._call_llm_with_cache.side_effect = RuntimeError("LLM down")
    plan: dict[str, Any] = {
        "test_cases": [{"case_name": "test_add"}],
        "logic_analysis": {"postconditions": []},
    }
    result = OracleEnhancerAgent.enhance(agent, plan)
    assert result["oracle_enhanced"] is False
    assert "oracle" not in result["test_cases"][0]


def test_enhance_non_list_output_degrades() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    agent = _make_agent_stub(json.dumps({"unexpected": "object"}))
    plan: dict[str, Any] = {"test_cases": [{"case_name": "test_add"}], "logic_analysis": {}}
    result = OracleEnhancerAgent.enhance(agent, plan)
    assert result["oracle_enhanced"] is False


def test_apply_oracles_clamps_confidence() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    cases: list[dict[str, Any]] = [
        {"case_name": "a"},
        {"case_name": "b"},
        {"case_name": "c"},
        {"case_name": "d"},
    ]
    oracles = [
        {"case_name": "a", "oracle": "assert x", "oracle_confidence": 5.0},
        {"case_name": "b", "oracle": "assert y", "oracle_confidence": -1.0},
        {"case_name": "c", "oracle": "assert z", "oracle_confidence": "bad"},
        {"case_name": "d", "oracle": "assert w"},
    ]
    OracleEnhancerAgent._apply_oracles(cases, oracles)
    assert cases[0]["oracle_confidence"] == 1.0
    assert cases[1]["oracle_confidence"] == 0.0
    assert cases[2]["oracle_confidence"] == 0.0
    assert cases[3]["oracle_confidence"] == 0.0


def test_planner_node_writes_oracle_enhanced_when_enabled() -> None:
    with patch.dict(os.environ, {"ORACLE_ENHANCE_ENABLE": "true"}):
        from src.graph import nodes as nodes_mod

        fake_plan = {
            "function_name": "add",
            "logic_analysis": {"postconditions": []},
            "test_cases": [{"case_name": "test_add"}],
        }

        def _fake_enhance(agent, plan):
            plan["oracle_enhanced"] = True
            return plan

        with (
            patch.object(nodes_mod, "PlannerAgent") as planner_cls,
            patch("src.agents.oracle_enhancer.OracleEnhancerAgent.enhance", _fake_enhance),
        ):
            planner_cls.return_value.plan.return_value = dict(fake_plan)
            state: dict[str, Any] = {"target_code": "def add(a,b): return a+b", "target_function": "add"}
            update = nodes_mod._planner_node(state)
            assert "test_plan" in update
            assert update["oracle_enhanced"] is True


def test_planner_node_no_oracle_key_when_disabled() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ORACLE_ENHANCE_ENABLE", None)
        from src.graph import nodes as nodes_mod

        fake_plan = {
            "function_name": "add",
            "logic_analysis": {"postconditions": []},
            "test_cases": [{"case_name": "test_add"}],
        }
        with patch.object(nodes_mod, "PlannerAgent") as planner_cls:
            planner_cls.return_value.plan.return_value = dict(fake_plan)
            state: dict[str, Any] = {"target_code": "def add(a,b): return a+b", "target_function": "add"}
            update = nodes_mod._planner_node(state)
            assert "test_plan" in update
            assert "oracle_enhanced" not in update  # 历史口径不变


def test_enhance_with_oracles_wrapper_object() -> None:
    from src.agents.oracle_enhancer import OracleEnhancerAgent

    agent = _make_agent_stub(
        json.dumps({"oracles": [{"case_name": "test_x", "oracle": "assert 1", "oracle_confidence": 0.5}]})
    )
    plan: dict[str, Any] = {"test_cases": [{"case_name": "test_x"}], "logic_analysis": {}}
    result = OracleEnhancerAgent.enhance(agent, plan)
    assert result["oracle_enhanced"] is True
    assert result["test_cases"][0]["oracle"] == "assert 1"
