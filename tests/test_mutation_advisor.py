"""M7 图内变异顾问（src/graph/mutation_advisor.py）单元测试。

背景：2026-09-29 批次新增的 opt-in 模块（MUTATION_ADVISOR_ENABLE
默认关）落地时零测试覆盖——`graph/mutation_advisor.py` 分支在
coverage.xml 中全部未覆盖。本文件覆盖：开关解析 / prompt 注入段落
渲染与截断 / _mutation_advisor_node 的三条结果路径（注入 / 无存活
变异体 / 测量异常降级），测量层 build_mutation_feedback 以 monkeypatch
替换（零 subprocess，CI 稳定）（2026-10-02 审查修复）。
"""

from __future__ import annotations

import pytest

from src.graph.mutation_advisor import (
    _mutation_advisor_node,
    build_mutation_prompt_section,
    mutation_advisor_enabled,
)


class TestSwitch:
    """MUTATION_ADVISOR_ENABLE 开关（默认 false 历史口径）。"""

    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("MUTATION_ADVISOR_ENABLE", raising=False)
        assert mutation_advisor_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("MUTATION_ADVISOR_ENABLE", value)
        assert mutation_advisor_enabled() is True

    def test_falsy_value(self, monkeypatch):
        monkeypatch.setenv("MUTATION_ADVISOR_ENABLE", "false")
        assert mutation_advisor_enabled() is False


class TestPromptSection:
    """build_mutation_prompt_section 渲染（保守口径：空输入 → 空串）。"""

    def test_none_returns_empty(self):
        assert build_mutation_prompt_section(None) == ""

    def test_no_survived_returns_empty(self):
        assert build_mutation_prompt_section({"available": True, "survived_mutants": []}) == ""
        assert build_mutation_prompt_section({"survived_mutants": None}) == ""

    def test_renders_survivors_and_score(self):
        text = build_mutation_prompt_section(
            {"available": True, "survived_mutants": ["m1: 边界缺失"], "mutation_score": 0.5}
        )
        assert "共 1 条" in text
        assert "0.5" in text
        assert "m1: 边界缺失" in text
        assert "变异测试得分" in text

    def test_capped_at_15_survivors(self):
        survived = [f"mutant-{i}" for i in range(30)]
        text = build_mutation_prompt_section({"survived_mutants": survived, "mutation_score": 0.1})
        assert "共 30 条" in text  # 总数如实
        assert "15. mutant-14" in text  # 第 15 条（索引 0..14）展示
        assert "mutant-15" not in text  # 第 16 条起截断


class TestMutationAdvisorNode:
    """_mutation_advisor_node 三条结果路径（测量层 monkeypatch）。"""

    def _state(self) -> dict:
        return {
            "target_code": "def f():\n    return 1\n",
            "generated_test": "def test_f():\n    assert f() == 1\n",
            "iteration": 1,
        }

    def test_injects_when_survivors_exist(self, monkeypatch):
        feedback = {"available": True, "survived_mutants": ["m1", "m2"], "mutation_score": 0.4}
        monkeypatch.setattr("experiments.mutation_testing.build_mutation_feedback", lambda **kw: feedback)
        update = _mutation_advisor_node(self._state())
        assert update.get("mutation_feedback") == feedback

    def test_no_update_when_all_killed(self, monkeypatch):
        feedback = {"available": True, "survived_mutants": [], "mutation_score": 1.0}
        monkeypatch.setattr("experiments.mutation_testing.build_mutation_feedback", lambda **kw: feedback)
        assert _mutation_advisor_node(self._state()) == {}

    def test_no_update_when_unavailable(self, monkeypatch):
        feedback = {"available": False, "survived_mutants": ["m1"]}
        monkeypatch.setattr("experiments.mutation_testing.build_mutation_feedback", lambda **kw: feedback)
        assert _mutation_advisor_node(self._state()) == {}

    def test_exception_degrades_to_empty(self, monkeypatch):
        def _boom(**kw):
            raise RuntimeError("subprocess 挂了")

        monkeypatch.setattr("experiments.mutation_testing.build_mutation_feedback", _boom)
        assert _mutation_advisor_node(self._state()) == {}

    def test_none_feedback_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr("experiments.mutation_testing.build_mutation_feedback", lambda **kw: None)
        assert _mutation_advisor_node(self._state()) == {}

    def test_missing_state_keys_do_not_crash(self, monkeypatch):
        """state 缺 target_code / generated_test → 空串传入，不抛异常。"""
        monkeypatch.setattr(
            "experiments.mutation_testing.build_mutation_feedback",
            lambda **kw: {"available": False, "survived_mutants": []},
        )
        assert _mutation_advisor_node({}) == {}


class TestWorkflowConditionalRegistration:
    """workflow.build_workflow 对 mutation_advisor 的条件注册（默认关）。"""

    def test_enabled_node_registered(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        with patch("src.graph.workflow.StateGraph") as mock_sg:
            mock_wf = MagicMock()
            mock_sg.return_value = mock_wf
            monkeypatch.setenv("MUTATION_ADVISOR_ENABLE", "true")
            monkeypatch.setattr("src.graph.workflow.mutation_advisor_enabled", lambda: True, raising=False)
            import src.graph.workflow as w

            w._create_workflow()
            # 注册节点名中应出现 mutation_advisor
            node_names = [c.args[0] for c in mock_wf.add_node.call_args_list]
            assert "mutation_advisor" in node_names

    def test_disabled_node_not_registered(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        with patch("src.graph.workflow.StateGraph") as mock_sg:
            mock_wf = MagicMock()
            mock_sg.return_value = mock_wf
            monkeypatch.delenv("MUTATION_ADVISOR_ENABLE", raising=False)
            import src.graph.workflow as w

            w._create_workflow()
            node_names = [c.args[0] for c in mock_wf.add_node.call_args_list]
            assert "mutation_advisor" not in node_names, "默认关时图拓扑应与历史一致"
