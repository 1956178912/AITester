"""空计划短路行为锁（EMPTY_PLAN_SHORTCUT_ENABLE，2026-10-10 独立审查落地）。

锁定三组行为：
1. 开关默认关（不设 env）时历史口径零变化——空计划仍走 Generator LLM 调用；
2. 开关开启 + 空计划（test_cases=[]）→ 跳过 LLM 调用、generated_test 为空、
   empty_plan_shortcut=True；
3. 开关开启 + 非空计划 → 正常生成（不走短路）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph import workflow as workflow_module
from src.graph.nodes import _empty_plan_shortcut_enabled


@pytest.fixture
def _gen_env() -> None:
    """隔离环境：保存并清空 EMPTY_PLAN_SHORTCUT_ENABLE，测试后恢复。"""
    import os

    original = os.getenv("EMPTY_PLAN_SHORTCUT_ENABLE")
    os.environ.pop("EMPTY_PLAN_SHORTCUT_ENABLE", None)
    yield
    if original is None:
        os.environ.pop("EMPTY_PLAN_SHORTCUT_ENABLE", None)
    else:
        os.environ["EMPTY_PLAN_SHORTCUT_ENABLE"] = original


class TestEmptyPlanShortcut:
    def test_switch_defaults_off(self, _gen_env: None) -> None:
        assert _empty_plan_shortcut_enabled() is False

    @patch("src.graph.nodes.GeneratorAgent")
    def test_empty_plan_with_switch_on_skips_llm(self, mock_generator_class, _gen_env: None, monkeypatch) -> None:
        """开关开 + 空计划 → 跳过 LLM 调用，empty_plan_shortcut=True。"""
        monkeypatch.setenv("EMPTY_PLAN_SHORTCUT_ENABLE", "true")
        workflow_module.ENABLE_RAG = False
        workflow_module.RAG_MODULE_AVAILABLE = False

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_foo(): pass"
        mock_generator_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "module_name": "test_module",
            "test_plan": {"function_name": "foo", "test_cases": []},
        }
        result = workflow_module._generator_node(state)

        assert result["generated_test"] == ""
        assert result["empty_plan_shortcut"] is True
        # 短路关键断言：Generator LLM 调用从未发生
        mock_agent.generate.assert_not_called()

    @patch("src.graph.nodes.GeneratorAgent")
    def test_non_empty_plan_with_switch_on_generates(self, mock_generator_class, _gen_env: None, monkeypatch) -> None:
        """开关开 + 非空计划 → 正常生成（不走短路）。"""
        monkeypatch.setenv("EMPTY_PLAN_SHORTCUT_ENABLE", "true")
        workflow_module.ENABLE_RAG = False
        workflow_module.RAG_MODULE_AVAILABLE = False

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_foo(): pass"
        mock_generator_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "module_name": "test_module",
            "test_plan": {"function_name": "foo", "test_cases": [{"case_name": "x"}]},
        }
        result = workflow_module._generator_node(state)

        assert result["generated_test"] == "def test_foo(): pass"
        assert result["empty_plan_shortcut"] is False
        mock_agent.generate.assert_called_once()

    @patch("src.graph.nodes.GeneratorAgent")
    def test_empty_plan_with_switch_off_still_generates(self, mock_generator_class, _gen_env: None) -> None:
        """开关默认关 + 空计划 → 历史口径（仍走 LLM 调用，零行为变化）。"""
        workflow_module.ENABLE_RAG = False
        workflow_module.RAG_MODULE_AVAILABLE = False

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_foo(): pass"
        mock_generator_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "module_name": "test_module",
            "test_plan": {"function_name": "foo", "test_cases": []},
        }
        result = workflow_module._generator_node(state)

        assert result["empty_plan_shortcut"] is False
        mock_agent.generate.assert_called_once()
