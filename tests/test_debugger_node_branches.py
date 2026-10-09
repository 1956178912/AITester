"""src/graph/debugger.py 节点分支补齐测试（S7 拆分后覆盖率 44% → 补齐）。

S7 拆分（2026-10-08 R3）把 _diagnosis_node / _debugger_node 从 nodes.py 拆到
src/graph/debugger.py，但拆分后该模块的实验性开关分支（FL_spectral / gold
injection / fault_localizer / deterministic_repair / expert_pool / strategy_bank
/ risk_approval / failure_frequency）默认关，从未被任何测试直接覆盖（既有
test_debugger*.py 全部指向 src/agents/debugger.py 的 DebuggerAgent）。

本文件针对这 9 个未覆盖分支做纯 mock 补齐（零 LLM / 零网络 / 零子进程），
以 patch 开关函数 + mock Agent 的方式锁定各分支的观测写入口径。

mock 约定（与 test_nodes_callbacks.py 同源）：
- 节点内 `_get_or_create_debugger_agent()` 经 patch("src.graph.debugger.
  _get_or_create_debugger_agent") 替换为 MagicMock；
- 函数内延迟 import 的开关（fault_localizer / strategy_bank / risk_approval /
  fl_spectral / deterministic_repair）在**源模块** patch（import 发生时取真实值）。
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from src.budget.cost_budget import BudgetExceededError
from src.graph.debugger import (
    _build_failure_frequency_section,
    _debugger_node,
    _diagnosis_node,
    _resolve_target_module,
)


def _base_state(**overrides: object) -> dict:
    """构造最小 _debugger_node 状态（含 failed_cases 以触发定位分支）。"""
    state: dict = {
        "target_code": "def foo(x):\n    return x * 2\n",
        "target_file": "foo.py",
        "module_name": "foo",
        "test_output": "AssertionError: assert 4 == 0",
        "generated_test": "def test_foo():\n    assert foo(2) == 0\n",
        "failed_cases": [{"case": "test_foo", "error": "assert 4 == 0"}],
        "iteration": 0,
        "error_category": "logic_error",
        "task_uuid": "task-1",
        "repair_history": [],
    }
    state.update(overrides)
    return state


def _agent_result(**overrides: object) -> dict:
    """单 Agent 修复路径（agent.debug）的默认返回。"""
    result: dict = {
        "root_cause": "边界未处理",
        "error_category": "logic_error",
        "fix_strategy": "补边界检查",
        "patch": "def foo(x):\n    if x < 0: return 0\n    return x * 2\n",
    }
    result.update(overrides)
    return result


def _mock_debugger_agent(result: dict | None = None) -> MagicMock:
    """构造 _get_or_create_debugger_agent 返回的 mock agent。"""
    agent = MagicMock()
    agent.debug.return_value = result if result is not None else _agent_result()
    return agent


def _run_debugger(state: dict, agent: MagicMock | None = None, **patches: object) -> dict:
    """在统一 mock 骨架下运行 _debugger_node，屏蔽 fault_localizer 默认分支。

    patches 的键为 patch 目标（源模块限定名），值为该目标的 return_value
    （统一口径：开关函数返回 bool、定位/合成函数返回 dict、Agent 类返回
    MagicMock 实例）。
    """
    mock_agent = agent if agent is not None else _mock_debugger_agent()
    with ExitStack() as stack:
        stack.enter_context(patch("src.graph.debugger._get_or_create_debugger_agent", return_value=mock_agent))
        # 默认屏蔽 fault_localizer（其默认 true，会实例化真实 FaultLocalizerAgent；
        # 需要测试 fault_localizer 的用例会显式覆盖此 patch）
        stack.enter_context(patch("src.agents.fault_localizer.fault_localizer_enabled", return_value=False))
        for target, value in patches.items():
            stack.enter_context(patch(target, return_value=value))
        return _debugger_node(state)


# ═══ 1. _build_failure_frequency_section（FAILURE_FREQUENCY_ENABLE）═══════════


class TestBuildFailureFrequencySection:
    def test_disabled_returns_empty(self):
        with patch("src.graph.debugger._failure_frequency_enabled", return_value=False):
            assert _build_failure_frequency_section(_base_state()) == ""

    def test_signal_none_returns_empty(self):
        state = _base_state(repair_history=[{"error_category": "logic_error"}] * 3)
        with (
            patch("src.graph.debugger._failure_frequency_enabled", return_value=True),
            patch("src.tools.failure_frequency.detect_high_frequency_failure", return_value=None),
        ):
            assert _build_failure_frequency_section(state) == ""

    def test_empty_hint_returns_empty(self):
        with (
            patch("src.graph.debugger._failure_frequency_enabled", return_value=True),
            patch(
                "src.tools.failure_frequency.detect_high_frequency_failure",
                return_value={"category": "logic_error", "count": 3, "threshold": 2},
            ),
            patch("src.tools.failure_frequency.get_escalated_strategy_hint", return_value=""),
        ):
            assert _build_failure_frequency_section(_base_state()) == ""

    def test_high_frequency_injects_hint(self):
        hint = "优先启用 oracle_enhancer 强化修复"
        with (
            patch("src.graph.debugger._failure_frequency_enabled", return_value=True),
            patch(
                "src.tools.failure_frequency.detect_high_frequency_failure",
                return_value={"category": "logic_error", "count": 3, "threshold": 2},
            ),
            patch("src.tools.failure_frequency.get_escalated_strategy_hint", return_value=hint),
        ):
            assert _build_failure_frequency_section(_base_state()) == hint


# ═══ 2. _diagnosis_node（DIAGNOSIS_NODE_ENABLE 工作流级诊断点）═══════════════


class TestDiagnosisNode:
    def test_writes_defect_type_and_reason(self):
        mock_agent = MagicMock()
        mock_agent._run_review_diagnosis.return_value = {
            "defect_type": "test_defect",
            "reason": "断言期望值与实现语义不符",
        }
        state = _base_state()
        with patch("src.graph.debugger._get_or_create_debugger_agent", return_value=mock_agent):
            result = _diagnosis_node(state)
        assert result["defect_type"] == "test_defect"
        assert result["review_reason"] == "断言期望值与实现语义不符"
        assert result["diagnosis_source"] == "diagnosis_node"

    def test_missing_defect_type_defaults_to_implementation(self):
        mock_agent = MagicMock()
        mock_agent._run_review_diagnosis.return_value = {"reason": ""}
        with patch("src.graph.debugger._get_or_create_debugger_agent", return_value=mock_agent):
            result = _diagnosis_node(_base_state())
        assert result["defect_type"] == "implementation_defect"


# ═══ 3. FL_spectral 定位先验注入（FL_SPECTRAL_ENABLE）═════════════════════════


class TestFlSpectralSection:
    def test_focus_renders_section_and_writes_state(self):
        focus = {"top_k": [{"line": 5, "score": 0.9}]}
        section = "FL 谱系定位先验：第 5 行可疑"
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.debugger._fl_spectral_enabled": True,
                "src.agents.fl_spectral.measure_fl_spectral_focus": focus,
                "src.agents.fl_spectral.build_fl_spectral_prompt_section": section,
            },
        )
        assert result["fl_spectral_focus"] == focus

    def test_focus_none_skips_section(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.debugger._fl_spectral_enabled": True,
                "src.agents.fl_spectral.measure_fl_spectral_focus": None,
            },
        )
        assert result["fl_spectral_focus"] is None


# ═══ 4. gold injection 反事实臂（FL_GOLD_INJECTION_ENABLE）════════════════════


class TestGoldInjectionLocalization:
    def test_gold_injection_constructs_loc(self):
        loc = {
            "function_name": "foo",
            "line_start": 1,
            "line_end": 2,
            "confidence": 1.0,
            "reasoning": "反事实臂",
            "candidates": [{"function_name": "foo"}],
        }
        state = _base_state(gold_fixed_code="def foo(x):\n    return x * 2\n")
        result = _run_debugger(
            state,
            **{
                "src.agents.fault_localizer.gold_injection_enabled": True,
                "src.agents.fault_localizer.build_gold_injection_localization": loc,
            },
        )
        assert result["llm_localization"] == loc


# ═══ 5. fault_localizer 分支（FAULT_LOCALIZER_ENABLE，默认 true）══════════════


class TestFaultLocalizerBranch:
    def test_localize_success_writes_loc(self):
        loc = {
            "function_name": "foo",
            "line_start": 1,
            "line_end": 2,
            "confidence": 0.9,
            "candidates": [{"function_name": "foo"}],
        }
        mock_fl_agent = MagicMock()
        mock_fl_agent.localize.return_value = loc
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.agents.fault_localizer.fault_localizer_enabled": True,
                "src.agents.fault_localizer.FaultLocalizerAgent": mock_fl_agent,
            },
        )
        assert result["llm_localization"] == loc

    def test_localize_exception_degrades_to_none(self):
        mock_fl_agent = MagicMock()
        mock_fl_agent.localize.side_effect = RuntimeError("LLM 定位失败")
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.agents.fault_localizer.fault_localizer_enabled": True,
                "src.agents.fault_localizer.FaultLocalizerAgent": mock_fl_agent,
            },
        )
        # 异常被捕获（347-349），llm_localization 保守降级 None，不阻断主流程
        assert result["llm_localization"] is None
        assert result["patch"]


# ═══ 6. 确定性优先修复（DETERMINISTIC_REPAIR_FIRST_ENABLE）════════════════════


class TestDeterministicRepairFirst:
    def test_patch_produced_skips_llm(self):
        det_result = {
            "root_cause": "缺 import",
            "error_category": "logic_error",
            "fix_strategy": "import",
            "patch": "def foo(x):\n    return x * 2\n",
        }
        agent = _mock_debugger_agent()
        state = _base_state()
        result = _run_debugger(
            state,
            agent,
            **{
                "src.graph.debugger.deterministic_repair_first_enabled": True,
                "src.tools.deterministic_repair.attempt_deterministic_repair": {
                    "attempted": True,
                    "method": "import",
                    "reason": "缺 import 推断命中",
                    "patch_code": "def foo(x):\n    return x * 2\n",
                },
                "src.tools.deterministic_repair.build_deterministic_debug_result": det_result,
            },
        )
        # 确定性命中 → 跳过本轮 LLM 修复调用
        agent.debug.assert_not_called()
        assert result["deterministic_repair_status"]["patch_produced"] is True
        assert result["deterministic_repair_status"]["method"] == "import"
        assert result["patch"] == det_result["patch"]

    def test_no_patch_falls_through_to_llm(self):
        agent = _mock_debugger_agent()
        state = _base_state()
        result = _run_debugger(
            state,
            agent,
            **{
                "src.graph.debugger.deterministic_repair_first_enabled": True,
                "src.tools.deterministic_repair.attempt_deterministic_repair": {
                    "attempted": True,
                    "method": None,
                    "reason": "未命中",
                    "patch_code": "",
                },
            },
        )
        agent.debug.assert_called_once()
        assert result["deterministic_repair_status"]["patch_produced"] is False
        assert result["patch"]  # 回落 LLM 路径产出补丁


# ═══ 7. 专家池分支（EXPERT_POOL_ENABLE）═══════════════════════════════════════


class TestExpertPoolBranch:
    def test_single_winner_replaces_empty_patch(self):
        agent = _mock_debugger_agent(_agent_result(patch=""))
        mock_pool = MagicMock()
        mock_pool.generate_parallel.return_value = [{"dimension": "logic"}]
        mock_pool.cross_validate.return_value = [
            {
                "patch": "def foo(x):\n    if x < 0: return 0\n    return x * 2\n",
                "dimension": "logic",
                "agreed_dimensions": ["logic"],
                "verified_count": 1,
            }
        ]
        state = _base_state()
        result = _run_debugger(
            state,
            agent,
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": mock_pool,
                "src.tools.strategy_bank.strategy_bank_enabled": False,
            },
        )
        meta = result["expert_pool_meta"]
        assert meta is not None
        assert meta["expert_pool_winner"] is True
        assert meta["verified_count"] == 1
        assert meta["winner_dimension"] == "logic"
        assert result["patch"]

    def test_multi_candidate_synthesizes(self):
        mock_pool = MagicMock()
        mock_pool.generate_parallel.return_value = [{"dimension": "logic"}, {"dimension": "edge"}]
        mock_pool.cross_validate.return_value = [
            {"patch": "p1", "dimension": "logic", "agreed_dimensions": [], "new_code": "def f():\n    pass\n"},
            {"patch": "p2", "dimension": "edge", "agreed_dimensions": [], "new_code": "def g():\n    pass\n"},
        ]
        state = _base_state()
        result = _run_debugger(
            state,
            _mock_debugger_agent(_agent_result(patch="")),
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": mock_pool,
                "src.tools.strategy_bank.strategy_bank_enabled": False,
                "src.tools.multi_candidate.synthesize_candidates": ("merged_code", ["logic", "edge"]),
            },
        )
        meta = result["expert_pool_meta"]
        assert meta is not None
        assert meta.get("synthesized") is True
        assert result["patch"] == "merged_code"


# ═══ 8. 策略银行独立路径（STRATEGY_BANK_ENABLE，专家池关）═════════════════════


class TestStrategyBankIndependentPath:
    def test_independent_path_records_hint(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.debugger.expert_pool_enabled": False,
                "src.tools.strategy_bank.strategy_bank_enabled": True,
                "src.tools.strategy_bank.select_strategy": {"prompt_hint": "优先边界检查"},
            },
        )
        assert result["strategy_bank_hint"] == "优先边界检查"

    def test_no_prompt_hint_leaves_none(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.debugger.expert_pool_enabled": False,
                "src.tools.strategy_bank.strategy_bank_enabled": True,
                "src.tools.strategy_bank.select_strategy": {"prompt_hint": ""},
            },
        )
        assert result["strategy_bank_hint"] is None


# ═══ 9. 风险分级人工回路（RISK_APPROVAL_ENABLE）═══════════════════════════════


class TestRiskApprovalBranch:
    def test_no_pause_returns_normally(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": False,
                    "risk_level": "low",
                    "risk_score": 10,
                },
            },
        )
        assert result["patch"]

    def test_pause_requested_approved(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": True,
                    "risk_level": "high",
                    "risk_score": 90,
                },
                "langgraph.types.interrupt": "approve",
            },
        )
        assert result["risk_approval_decision"]["approved"] is True
        assert result["risk_approval_decision"]["risk_level"] == "high"
        assert result["patch"]  # 放行本轮补丁

    def test_pause_requested_rejected_discards_patch(self):
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": True,
                    "risk_level": "high",
                    "risk_score": 90,
                },
                "langgraph.types.interrupt": "reject",
            },
        )
        assert result["risk_approval_decision"]["approved"] is False
        assert result["patch"] == ""  # 拒绝后丢弃高风险补丁

    def test_pause_interrupt_none_no_checkpointer(self):
        # interrupt 返回 None（无 checkpointer）→ 暂停未生效，继续工作流补丁保留
        state = _base_state()
        result = _run_debugger(
            state,
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": True,
                    "risk_level": "high",
                    "risk_score": 90,
                },
                "langgraph.types.interrupt": None,
            },
        )
        assert result["patch"]  # 无 checkpointer 继续工作流


# ═══ 10. _resolve_target_module 跨文件 target_module 解析 ══════════════════════


class TestResolveTargetModule:
    def test_cross_file_plan_target_modules_first(self):
        state = _base_state(
            cross_file_deps=[{"target_module": "module_b"}],
            cross_file_plan={"target_modules": ["module_c"]},
        )
        assert _resolve_target_module(state) == "module_c"

    def test_cross_file_deps_fallback_last_module(self):
        state = _base_state(
            cross_file_deps=[
                {"target_module": "module_b"},
                {"target_module": "module_c"},
            ]
        )
        assert _resolve_target_module(state) == "module_c"

    def test_single_file_returns_module_name(self):
        assert _resolve_target_module(_base_state()) == "foo"


# ═══ 11. _debugger_node 异常降级分支（BudgetExceededError / JSONDecodeError）══


class TestDebuggerExceptionBranch:
    def test_budget_exceeded_marks_category(self):
        agent = _mock_debugger_agent()
        agent.debug.side_effect = BudgetExceededError(100, 100, "tokens")
        result = _run_debugger(_base_state(), agent)
        assert result["error_category"] == "budget_exceeded"
        assert result["budget_exceeded"] is True

    def test_json_decode_error_marks_unknown(self):
        agent = _mock_debugger_agent()
        agent.debug.side_effect = json.JSONDecodeError("bad json", "doc", 0)
        result = _run_debugger(_base_state(), agent)
        assert result["error_category"] == "unknown"
        assert result["patch"] == ""


# ═══ 12. 专家池辩论收敛（EXPERT_POOL_DEBATE_ENABLE）═══════════════════════════


class TestExpertPoolDebate:
    def test_debate_revises_top_k(self):
        mock_pool = MagicMock()
        mock_pool.generate_parallel.return_value = [{"dimension": "logic"}]
        mock_pool.cross_validate.return_value = [
            {"patch": "p1", "dimension": "logic", "agreed_dimensions": [], "verified_count": 1}
        ]
        mock_pool.debate_round.return_value = [
            {"patch": "revised", "dimension": "logic", "agreed_dimensions": [], "debate_revise": True}
        ]
        result = _run_debugger(
            _base_state(),
            _mock_debugger_agent(_agent_result(patch="")),
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": mock_pool,
                "src.graph.expert_pool.expert_pool_debate_enabled": True,
                "src.tools.strategy_bank.strategy_bank_enabled": False,
            },
        )
        assert result["expert_pool_meta"]["debate_revise"] is True


# ═══ 13. 专家池内策略银行协同 + 结果积累（STRATEGY_BANK_ENABLE）══════════════


class TestExpertPoolStrategyBank:
    def test_expert_pool_strategy_bank_hint_and_outcome(self):
        mock_pool = MagicMock()
        mock_pool.generate_parallel.return_value = [{"dimension": "logic"}]
        mock_pool.cross_validate.return_value = [
            {"patch": "p1", "dimension": "logic", "agreed_dimensions": [], "verified_count": 1}
        ]
        result = _run_debugger(
            _base_state(),
            _mock_debugger_agent(_agent_result(patch="")),
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": mock_pool,
                "src.tools.strategy_bank.strategy_bank_enabled": True,
                "src.tools.strategy_bank.select_strategy": {
                    "prompt_hint": "优先边界检查",
                    "strategy": "boundary_check",
                },
            },
        )
        assert result["strategy_bank_hint"] == "优先边界检查"
        assert result["expert_pool_meta"]["expert_pool_winner"] is True


# ═══ 14. 多解合成的 static_validate 回退（候选无 new_code）════════════════════


class TestExpertPoolSynthesizeStaticValidate:
    def test_synthesize_static_validate_fallback(self):
        mock_pool = MagicMock()
        mock_pool.generate_parallel.return_value = [{"dimension": "logic"}, {"dimension": "edge"}]
        # 候选无 new_code → 触发 static_validate 应用补丁得到 applied 代码
        mock_pool.cross_validate.return_value = [
            {"patch": "p1", "dimension": "logic", "agreed_dimensions": []},
            {"patch": "p2", "dimension": "edge", "agreed_dimensions": []},
        ]
        result = _run_debugger(
            _base_state(),
            _mock_debugger_agent(_agent_result(patch="")),
            **{
                "src.graph.debugger.expert_pool_enabled": True,
                "src.graph.expert_pool.ExpertPoolAgent": mock_pool,
                "src.tools.strategy_bank.strategy_bank_enabled": False,
                "src.tools.multi_candidate.static_validate_patch": (True, "", "applied_code"),
                "src.tools.multi_candidate.synthesize_candidates": ("merged", ["logic", "edge"]),
            },
        )
        assert result["expert_pool_meta"]["synthesized"] is True


# ═══ 15. 风险分级预算比例计算（token / usd 双分支）════════════════════════════


class TestRiskApprovalBudgetRatio:
    def test_token_budget_ratio_computed(self):
        result = _run_debugger(
            _base_state(),
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": False,
                    "risk_level": "low",
                },
                "src.budget.cost_budget.get_budget_stats": {
                    "token_limit": 1000,
                    "consumed_tokens": 500,
                    "usd_limit": 0,
                    "consumed_usd": 0,
                },
            },
        )
        assert result["patch"]

    def test_usd_budget_ratio_computed(self):
        result = _run_debugger(
            _base_state(),
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": False,
                    "risk_level": "low",
                },
                "src.budget.cost_budget.get_budget_stats": {
                    "token_limit": 0,
                    "consumed_tokens": 0,
                    "usd_limit": 100.0,
                    "consumed_usd": 50.0,
                },
            },
        )
        assert result["patch"]

    def test_budget_stats_exception_degrades(self):
        # get_budget_stats 返回 None → .get 抛 AttributeError → except pass
        # （预算比例取不到时保守降级，不阻断修复主流程）
        result = _run_debugger(
            _base_state(),
            **{
                "src.graph.risk_approval.risk_approval_enabled": True,
                "src.graph.risk_approval.build_risk_summary": {
                    "pause_requested": False,
                    "risk_level": "low",
                },
                "src.budget.cost_budget.get_budget_stats": None,
            },
        )
        assert result["patch"]
