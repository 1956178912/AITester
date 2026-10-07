"""修复引擎批次 III（2026-10-07）：编辑意图确定性落盘 + 再生成计数补漏。

锁定四组行为：
1. 编辑意图引擎（src/tools/patch_intent.py）：意图解析校验、锚点唯一性
   拒绝、原子性回退、AST 语法门、存量语法错误豁免；
2. debugger 接线：prompt 契约注入（开关控）、意图成功替换 patch、
   拒绝回落、返回观测键；
3. AC2 过红再生成入口计数补漏（_specificity_over_red_regenerate_entry
   ——E2 16/174 触顶根因通道的上限保护恢复）；
4. 状态契约：edit_intent_status 声明 + 工厂 None（键集合同构）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph.nodes import _specificity_over_red_regenerate_entry
from src.graph.state import create_initial_state
from src.tools.patch_intent import (
    apply_edit_intents,
    edit_intent_enabled,
    parse_edit_intents,
)

CODE = "def add(a, b):\n    return a - b\n\n\ndef helper(x):\n    return x * 2\n"


class TestParseEditIntents:
    def test_valid_intents(self) -> None:
        intents = parse_edit_intents([{"old_str": "a - b", "new_str": "a + b"}])
        assert intents == [{"old_str": "a - b", "new_str": "a + b"}]

    def test_rejects_invalid_entries(self) -> None:
        raw = [
            "junk",  # 非 dict
            {"old_str": "", "new_str": "x"},  # 空 old_str
            {"old_str": "x", "new_str": "x"},  # 无变化
            {"old_str": 1, "new_str": "y"},  # 非字符串
            {"old_str": "a", "new_str": None},  # 非字符串
        ]
        assert parse_edit_intents(raw) == []

    def test_non_list_returns_empty(self) -> None:
        assert parse_edit_intents(None) == []
        assert parse_edit_intents({"old_str": "x", "new_str": "y"}) == []
        assert parse_edit_intents([]) == []


class TestApplyEditIntents:
    def test_single_edit(self) -> None:
        result = apply_edit_intents(CODE, [{"old_str": "return a - b", "new_str": "return a + b"}])
        assert result["ok"] is True
        assert "return a + b" in result["code"]
        assert result["applied"] == 1 and result["total"] == 1

    def test_multi_hunk_sequential(self) -> None:
        result = apply_edit_intents(
            CODE,
            [
                {"old_str": "return a - b", "new_str": "return a + b"},
                {"old_str": "return x * 2", "new_str": "return x * 3"},
            ],
        )
        assert result["ok"] is True
        assert "return a + b" in result["code"] and "return x * 3" in result["code"]
        assert result["applied"] == 2

    def test_anchor_not_unique_atomic_reject(self) -> None:
        """锚点出现 2 次 → 整体拒绝、原码返回（杜绝静默错应用）。"""
        dup = "X = 1\nY = 1\n"
        result = apply_edit_intents(dup, [{"old_str": "1", "new_str": "2"}])
        assert result["ok"] is False
        assert result["code"] == dup  # 原子回退
        assert any("anchor_not_unique" in d for d in result["diagnostics"])

    def test_anchor_missing_rejects(self) -> None:
        result = apply_edit_intents(CODE, [{"old_str": "not in code", "new_str": "x"}])
        assert result["ok"] is False and result["code"] == CODE

    def test_second_intent_fails_first_rolled_back(self) -> None:
        """第二条锚点失效 → 已应用的第一条一并回滚（原子性）。"""
        result = apply_edit_intents(
            CODE,
            [
                {"old_str": "return a - b", "new_str": "return a + b"},
                {"old_str": "stale anchor", "new_str": "z"},
            ],
        )
        assert result["ok"] is False
        assert "return a - b" in result["code"]  # 第一条已回滚
        assert result["applied"] == 0

    def test_result_syntax_gate_rejects(self) -> None:
        """编辑结果破坏语法 → 拒绝并回退（原码可解析场景）。"""
        result = apply_edit_intents(CODE, [{"old_str": "return a - b", "new_str": "return ((("}])
        assert result["ok"] is False
        assert result["code"] == CODE
        assert any(d.startswith("result_syntax_error") for d in result["diagnostics"])

    def test_preexisting_syntax_error_exempt(self) -> None:
        """原文本本就不可解析 → 跳过 AST 门（存量语法错误不误杀编辑）。"""
        bad = "def f(:\n    pass\n"
        result = apply_edit_intents(bad, [{"old_str": "def f(:", "new_str": "def f(x):"}])
        assert result["ok"] is True
        assert "def f(x):" in result["code"]

    def test_empty_original_code_rejects(self) -> None:
        result = apply_edit_intents("   ", [{"old_str": "a", "new_str": "b"}])
        assert result["ok"] is False
        assert any("empty_original_code" in d for d in result["diagnostics"])


class TestSwitch:
    def test_default_off(self, monkeypatch) -> None:
        monkeypatch.delenv("EDIT_INTENT_ENABLE", raising=False)
        assert edit_intent_enabled() is False

    def test_explicit_on(self, monkeypatch) -> None:
        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        assert edit_intent_enabled() is True


class TestSpecificityOverRedRegenerateEntry:
    """AC2 过红再生成入口计数补漏（E2 16/174 触顶根因通道的上限保护）。"""

    def test_over_red_first_iteration_detected(self) -> None:
        state = {"iteration": 0, "test_passed": False, "specificity_gate_verdict": "over_red"}
        assert _specificity_over_red_regenerate_entry(state) is True

    def test_specific_red_not_detected(self) -> None:
        state = {"iteration": 0, "test_passed": False, "specificity_gate_verdict": "specific_red"}
        assert _specificity_over_red_regenerate_entry(state) is False

    def test_verdict_none_not_detected(self) -> None:
        state = {"iteration": 0, "test_passed": False, "specificity_gate_verdict": None}
        assert _specificity_over_red_regenerate_entry(state) is False

    def test_later_iteration_not_detected(self) -> None:
        """over_red 分支只在首轮触发；非首轮不计数（防误伤常规修复循环）。"""
        state = {"iteration": 2, "test_passed": False, "specificity_gate_verdict": "over_red"}
        assert _specificity_over_red_regenerate_entry(state) is False

    def test_generator_increment_wiring(self) -> None:
        """计数接线存在性锁：再生成路径判定条件包含第 5 类入口。

        （inspect.getsource 文本锁沿用仓内既有守卫模式——防止该条件被
        无意删除导致上限保护再次失效。）
        """
        import inspect

        import src.graph.nodes as nodes

        src_text = inspect.getsource(nodes._generator_node)
        assert "_specificity_over_red_regenerate_entry(state)" in src_text


class TestDebuggerEditIntentWiring:
    """debug() 接线行为锁：意图成功替换 patch / 拒绝回落 / 观测键透出。"""

    def _run_debug(self, monkeypatch, response: str) -> dict:
        from unittest.mock import patch

        from src.agents.debugger import DebuggerAgent

        agent = DebuggerAgent()
        with patch.object(agent, "_call_llm", return_value=response):
            return agent.debug(
                target_code=CODE,
                test_output="AssertionError: assert -1 == 1",
                failed_cases=[{"name": "test_add", "error": "assert -1 == 1"}],
            )

    def test_intent_applied_replaces_patch(self, monkeypatch) -> None:
        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        response = (
            '{"root_cause": "减号误用", "error_category": "ASSERTION", "fix_strategy": "s", '
            '"patch": "```python\\nENTIRE FILE REWRITE\\n```", '
            '"edit_intents": [{"old_str": "return a - b", "new_str": "return a + b"}]}'
        )
        result = self._run_debug(monkeypatch, response)
        assert result["edit_intent_status"]["ok"] is True
        assert result["edit_intent_status"]["applied"] == 1
        assert "return a + b" in result["patch"]  # 最小编辑结果
        assert "ENTIRE FILE REWRITE" not in result["patch"]  # 整文件重写被替换

    def test_intent_rejected_falls_back_to_legacy_patch(self, monkeypatch) -> None:
        """锚点不唯一 → 确定性引擎拒绝 → 回落整文件补丁通道。"""
        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        response = (
            '{"root_cause": "r", "error_category": "ASSERTION", "fix_strategy": "s", '
            '"patch": "```python\\ndef add(a, b):\\n    return a + b\\n```", '
            '"edit_intents": [{"old_str": "return", "new_str": "return 1 +"}]}'
        )
        result = self._run_debug(monkeypatch, response)
        assert result["edit_intent_status"]["ok"] is False
        assert any("anchor_not_unique" in d for d in result["edit_intent_status"]["diagnostics"])
        assert "def add" in result["patch"]  # legacy 整文件补丁保留

    def test_no_intents_records_status(self, monkeypatch) -> None:
        """契约开启但响应无 edit_intents → 状态记录 no_valid，patch 走 legacy。"""
        monkeypatch.setenv("EDIT_INTENT_ENABLE", "true")
        response = (
            '{"root_cause": "r", "error_category": "ASSERTION", "fix_strategy": "s", "patch": "```python\\nkept\\n```"}'
        )
        result = self._run_debug(monkeypatch, response)
        assert result["edit_intent_status"]["diagnostics"] == ["no_valid_edit_intents_in_response"]
        assert "kept" in result["patch"]

    def test_switch_off_zero_behavior_change(self, monkeypatch) -> None:
        """开关关：无意图契约注入、无意图应用、观测键 None（历史口径）。"""
        monkeypatch.delenv("EDIT_INTENT_ENABLE", raising=False)
        response = (
            '{"root_cause": "r", "error_category": "ASSERTION", "fix_strategy": "s", '
            '"patch": "```python\\ndef add(a, b):\\n    return a - b\\n```", '
            '"edit_intents": [{"old_str": "return a - b", "new_str": "return a + b"}]}'
        )
        result = self._run_debug(monkeypatch, response)
        assert result["edit_intent_status"] is None
        # 开关关时响应中的 edit_intents 字段被忽略：patch 保持响应原样
        assert "return a - b" in result["patch"]


class TestStateContract:
    def test_state_declares_edit_intent_status(self) -> None:
        state = create_initial_state(
            task_uuid="t",
            target_file="m.py",
            target_code="x = 1\n",
            max_iterations=3,
        )
        assert state["edit_intent_status"] is None

    def test_typeddict_annotation_exists(self) -> None:
        """TypedDict 字段存在性：类字典含该注解键（运行时工厂 + 注解双口径）。"""
        from src.graph.state import AITesterState

        state = create_initial_state(
            task_uuid="t",
            target_file="m.py",
            target_code="x = 1\n",
            max_iterations=3,
        )
        assert "edit_intent_status" in state
        assert "edit_intent_status" in AITesterState.__annotations__
