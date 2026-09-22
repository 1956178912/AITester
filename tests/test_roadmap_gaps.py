"""
路线图剩余缺口落地单元测试（2.3 / 3.1 / 3.3）。

覆盖：
- 2.3 复现测试专项生成（GeneratorAgent.generate_repro_test / _build_repro_prompt / 开关）
- 3.1 双向代码-测试诊断（DebuggerAgent._run_review_diagnosis / debug 分支修复 / 开关）
- 3.3 轻量奖励预测器（predict_candidate_rewards / _coverage_trend / 开关）
- 3.3 动态 temperature 接线（_dynamic_temperature_from_suggestion / BaseAgent 透传）
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.debugger import DebuggerAgent, _bidirectional_diagnosis_enabled
from src.agents.generator import GeneratorAgent, _repro_test_enabled
from src.tools import multi_candidate as mc

_GOOD_ORIGINAL = """\
def add(a, b):
    return a + b


def mul(a, b):
    return a * b
"""


# ─── 2.3 复现测试专项生成 ──────────────────────────────────────────────────


class TestReproTestGeneration:
    """2.3 复现测试专项生成能力。"""

    def test_repro_test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("REPRO_TEST_ENABLE", raising=False)
        assert _repro_test_enabled() is False

    def test_repro_test_enabled(self, monkeypatch):
        monkeypatch.setenv("REPRO_TEST_ENABLE", "true")
        assert _repro_test_enabled() is True

    def test_generate_repro_test_extracts_code(self):
        agent = GeneratorAgent()
        with patch.object(agent, "_call_llm_with_cache", return_value="```python\ndef test_bug(): pass\n```"):
            code = agent.generate_repro_test(
                defect_description="add 把加号写成了减号",
                target_code="def add(a, b): return a - b",
                module_name="calc",
            )
        assert "def test_bug" in code

    def test_generate_repro_test_fixes_import_module(self):
        agent = GeneratorAgent()
        with patch.object(
            agent,
            "_call_llm_with_cache",
            return_value="```python\nfrom calcx import add\ndef test_bug(): pass\n```",
        ):
            code = agent.generate_repro_test(
                defect_description="add 返回值错误",
                target_code="def add(a, b): return a + b",
                module_name="calc",
            )
        # 相似模块名笔误（calcx → calc）被修正
        assert "from calc import add" in code

    def test_build_repro_prompt_contains_defect_and_cross_file(self):
        agent = GeneratorAgent()
        prompt = agent._build_repro_prompt(
            defect_description="跨模块调用顺序错误",
            target_code="def f(): pass",
            module_name="main",
            cross_file_modules=["util", "config"],
        )
        assert "跨模块调用顺序错误" in prompt
        assert "from main import" in prompt
        assert "util" in prompt
        assert "跨文件上下文" in prompt
        assert "先失败" in prompt or "应失败" in prompt

    def test_build_repro_prompt_no_cross_file(self):
        agent = GeneratorAgent()
        prompt = agent._build_repro_prompt(
            defect_description="除零",
            target_code="def div(a, b): return a / b",
            module_name="calc",
            cross_file_modules=None,
        )
        assert "除零" in prompt
        assert "跨文件上下文" not in prompt


# ─── 3.1 双向代码-测试诊断（BiVCoder 式）──────────────────────────────────


class TestBidirectionalDiagnosis:
    """3.1 双向代码-测试诊断机制。"""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BIDIRECTIONAL_DIAGNOSIS_ENABLE", raising=False)
        assert _bidirectional_diagnosis_enabled() is False

    def test_enabled(self, monkeypatch):
        monkeypatch.setenv("BIDIRECTIONAL_DIAGNOSIS_ENABLE", "true")
        assert _bidirectional_diagnosis_enabled() is True

    def test_debug_disabled_returns_implementation_defect(self):
        """默认关闭时，defect_type 恒为 implementation_defect（保持历史口径）。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "加法用错运算符",
                "error_category": "assertion",
                "fix_strategy": "改回加号",
                "patch": "```python\ndef add(a, b): return a + b\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError",
                failed_cases=[{"name": "test_add", "error": "expected 5"}],
            )
        assert result["defect_type"] == "implementation_defect"

    def test_debug_test_defect_branches_to_regenerate(self):
        """Review Agent 判定为测试缺陷时，不生成补丁，返回 test_defect 信号。"""
        agent = DebuggerAgent()
        with (
            patch("src.agents.debugger._bidirectional_diagnosis_enabled", return_value=True),
            patch.object(
                agent, "_run_review_diagnosis", return_value={"defect_type": "test_defect", "reason": "预期值写错"}
            ),
        ):
            result = agent.debug(
                target_code="def add(a, b): return a + b",
                test_output="AssertionError: expected 4, got 5",
                failed_cases=[{"name": "test_add", "error": "expected 4, got 5"}],
            )
        assert result["defect_type"] == "test_defect"
        assert result["patch"] == ""
        assert "重新生成测试" in result["fix_strategy"]

    def test_debug_implementation_defect_proceeds(self):
        """Review Agent 判定为实现缺陷时，正常生成补丁。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "运算符错误",
                "error_category": "assertion",
                "fix_strategy": "改回加号",
                "patch": "```python\ndef add(a, b): return a + b\n```",
            }
        )
        with (
            patch("src.agents.debugger._bidirectional_diagnosis_enabled", return_value=True),
            patch.object(
                agent,
                "_run_review_diagnosis",
                return_value={"defect_type": "implementation_defect", "reason": "代码逻辑错误"},
            ),
            patch.object(agent, "_call_llm", return_value=mock_response),
        ):
            result = agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError",
                failed_cases=[{"name": "test_add", "error": "expected 5"}],
            )
        assert result["defect_type"] == "implementation_defect"
        assert "a + b" in result["patch"]

    def test_run_review_diagnosis_parses_test_defect(self):
        agent = DebuggerAgent()
        with patch.object(
            agent,
            "_call_llm_with_cache",
            return_value=json.dumps({"defect_type": "test_defect", "reason": "断言了错误行为"}),
        ):
            review = agent._run_review_diagnosis(
                target_code="def f(): pass",
                test_output="AssertionError",
                failed_cases=[{"name": "t", "error": "x"}],
                error_category="assertion",
            )
        assert review == {"defect_type": "test_defect", "reason": "断言了错误行为"}

    def test_run_review_diagnosis_fallback_on_invalid(self):
        """非法 defect_type 值保守归为实现缺陷（保持历史默认行为）。"""
        agent = DebuggerAgent()
        with patch.object(
            agent,
            "_call_llm_with_cache",
            return_value=json.dumps({"defect_type": "weird_value", "reason": "?"}),
        ):
            review = agent._run_review_diagnosis(
                target_code="def f(): pass",
                test_output="x",
                failed_cases=[{"name": "t", "error": "x"}],
                error_category="assertion",
            )
        assert review["defect_type"] == "implementation_defect"


# ─── 3.3 轻量奖励预测器 ────────────────────────────────────────────────────


class TestRewardPredictor:
    """3.3 轻量奖励预测器。"""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("REWARD_PREDICTOR_ENABLE", raising=False)
        assert mc.reward_predictor_enabled() is False

    def test_enabled(self, monkeypatch):
        monkeypatch.setenv("REWARD_PREDICTOR_ENABLE", "true")
        assert mc.reward_predictor_enabled() is True

    def test_coverage_trend_declining(self):
        trace = [
            {"coverage_delta": -2.0},
            {"coverage_delta": -1.0},
        ]
        assert mc._coverage_trend(trace) == "declining"

    def test_coverage_trend_stagnant(self):
        trace = [
            {"coverage_delta": 0.1},
            {"coverage_delta": -0.2},
        ]
        assert mc._coverage_trend(trace) == "stagnant"

    def test_coverage_trend_unknown(self):
        assert mc._coverage_trend(None) == "unknown"
        assert mc._coverage_trend([{"coverage_delta": 1.0}]) == "unknown"

    def _static_candidates(self, new_code_a: str, new_code_b: str) -> list[mc.CandidateResult]:
        """构造两个静态通过的候选（index 0 小改动、index 1 大改动）。"""
        return [
            mc.CandidateResult(index=0, patch="", new_code=new_code_a, static_passed=True, credit_score=0.8),
            mc.CandidateResult(index=1, patch="", new_code=new_code_b, static_passed=True, credit_score=0.2),
        ]

    def test_predict_rewards_stagnant_inverts(self):
        """停滞趋势下，更大改动的候选（低基础信用）预测奖励更高。"""
        original = "def f(x):\n    return x + 1\n" * 10
        small = "def f(x):\n    return x + 1\n" * 10
        big = "def f(x):\n    return x * 2 + 1\n" * 10
        candidates = self._static_candidates(small, big)
        pred = mc.predict_candidate_rewards(
            original,
            candidates,
            execution_trace=[{"coverage_delta": 0.1}, {"coverage_delta": -0.2}],
        )
        assert pred["trend"] == "stagnant"
        by_index = {c["index"]: c["predicted_reward"] for c in pred["candidates"]}
        # 停滞：反转信用，大改动候选（index=1）预测奖励应更高
        assert by_index[1] > by_index[0]

    def test_predict_rewards_declining_keeps_minimal(self):
        """连降趋势下，最小改动候选（高基础信用）预测奖励更高。"""
        original = "def f(x):\n    return x + 1\n" * 10
        small = "def f(x):\n    return x + 1\n" * 10
        big = "def f(x):\n    return x * 2 + 1\n" * 10
        candidates = self._static_candidates(small, big)
        pred = mc.predict_candidate_rewards(
            original,
            candidates,
            execution_trace=[{"coverage_delta": -2.0}, {"coverage_delta": -1.0}],
        )
        assert pred["trend"] == "declining"
        by_index = {c["index"]: c["predicted_reward"] for c in pred["candidates"]}
        assert by_index[0] > by_index[1]


# ─── 3.3 动态 temperature 接线 ──────────────────────────────────────────────


class TestDynamicTemperature:
    """3.3 执行反馈驱动的动态 temperature。"""

    def test_lower_temperature_halves(self):
        from config import TEMPERATURE
        from src.graph.nodes import _dynamic_temperature_from_suggestion

        lowered = _dynamic_temperature_from_suggestion("lower_temperature")
        assert lowered == round(max(0.0, TEMPERATURE * 0.5), 3)

    def test_other_suggestion_no_override(self):
        from src.graph.nodes import _dynamic_temperature_from_suggestion

        assert _dynamic_temperature_from_suggestion("switch_repair_view") is None
        assert _dynamic_temperature_from_suggestion(None) is None

    def test_call_llm_with_cache_forwards_temperature(self):
        """BaseAgent._call_llm_with_cache 把 temperature 透传给 _call_llm。"""
        from src.agents.base_agent import BaseAgent

        agent = BaseAgent(system_prompt="test")
        with patch.object(agent, "_call_llm", return_value="ok") as mock_call:
            agent._call_llm_with_cache("hello", temperature=0.1)
        # 温度作为关键字透传（None 时也透传 None，保持签名稳定）
        assert mock_call.call_args.kwargs.get("temperature") == 0.1

    def test_call_llm_with_cache_temperature_in_key(self, monkeypatch, tmp_path):
        """缓存开启时非默认温度纳入缓存键，避免与默认温度互相误命中。"""
        from src.agents import base_agent as ba

        agent = ba.BaseAgent.__new__(ba.BaseAgent)
        agent.system_prompt = "sys"
        # 强制开启文件缓存（测试环境默认关闭），覆盖缓存键含温度 + 透传两条分支
        monkeypatch.setattr(ba, "_llm_cache_enabled", lambda: True)
        monkeypatch.setattr(ba, "_llm_cache_dir", lambda: str(tmp_path))
        with patch.object(agent, "_call_llm", return_value="ok") as mock_call:
            result = agent._call_llm_with_cache("hello", temperature=0.1)
        assert result == "ok"
        assert mock_call.call_args.kwargs.get("temperature") == 0.1


# ─── 3.1 双向诊断工作流路由（防死循环）──────────────────────────────────────


class TestBidirectionalWorkflowRouting:
    """3.1 双向诊断在 _should_debug 中的分支路由。"""

    def test_test_defect_routes_regenerate(self):
        from src.graph.workflow import _should_debug

        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "defect_type": "test_defect",
            "regeneration_count": 0,
        }
        assert _should_debug(state) == "regenerate"

    def test_test_defect_capped_returns_done(self):
        """重新生成上限已满且仍判定为测试缺陷 → done（防 generator↔executor 死循环）。"""
        from src.graph.workflow import _MAX_REGENERATIONS, _should_debug

        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "defect_type": "test_defect",
            "regeneration_count": _MAX_REGENERATIONS,
        }
        assert _should_debug(state) == "done"
