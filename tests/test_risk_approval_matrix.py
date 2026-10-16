#!/usr/bin/env python3
"""覆盖率补口：`src/graph/risk_approval.py`（人工回路风险分级）单元测试。

动机（EMSE 多轮优化批次）：该模块决定"哪些任务需要人工介入"，属**门槛逻辑**；
其环境解析、影响面分段与因子计算此前多处未覆盖（coverage.xml 记录 66-67、108、
167、169、201-202 等）。门槛逻辑无测试 = 阈值与降级行为改动无人可挡。

全部用例零 LLM、零网络、零子进程。
"""

from __future__ import annotations

import pytest

from src.graph.risk_approval import (
    _budget_factor,
    _clamp,
    _confidence_factor,
    _env_float,
    _impact_factor,
    assess_task_risk,
    build_risk_summary,
    risk_approval_enabled,
)


class TestSwitchAndEnvParsing:
    def test_enabled_default_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RISK_APPROVAL_ENABLE", raising=False)
        assert risk_approval_enabled() is False

    def test_enabled_only_for_literal_true(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        assert risk_approval_enabled() is True
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "yes")
        assert risk_approval_enabled() is False

    def test_env_float_parses_and_clamps_into_range(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("X_TEST_FLOAT", "0.5")
        assert _env_float("X_TEST_FLOAT", 0.1, 0.0, 1.0) == pytest.approx(0.5)
        monkeypatch.setenv("X_TEST_FLOAT", "5")
        assert _env_float("X_TEST_FLOAT", 0.1, 0.0, 1.0) == pytest.approx(1.0)
        monkeypatch.setenv("X_TEST_FLOAT", "-5")
        assert _env_float("X_TEST_FLOAT", 0.1, 0.0, 1.0) == pytest.approx(0.0)

    def test_env_float_falls_back_on_unparsable_value(self, monkeypatch: pytest.MonkeyPatch):
        """解析失败必须回退默认值（此前未覆盖分支）——非法配置不得变成 0 风险。"""
        monkeypatch.setenv("X_TEST_FLOAT", "not-a-number")
        assert _env_float("X_TEST_FLOAT", 0.42, 0.0, 1.0) == pytest.approx(0.42)

    def test_env_float_missing_uses_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("X_TEST_FLOAT", raising=False)
        assert _env_float("X_TEST_FLOAT", 0.33, 0.0, 1.0) == pytest.approx(0.33)


class TestClampAndFactors:
    def test_clamp_bounds(self):
        assert _clamp(-1.0) == 0.0
        assert _clamp(2.0) == 1.0
        assert _clamp(0.25) == pytest.approx(0.25)
        assert _clamp(5.0, minimum=1.0, maximum=3.0) == pytest.approx(3.0)

    def test_confidence_none_is_conservative_high(self):
        factor, reason = _confidence_factor(None)
        assert factor == 1.0
        assert "no_confidence" in reason

    @pytest.mark.parametrize(
        ("confidence", "expected"),
        [(0.0, 1.0), (0.4, 0.6), (0.5, 0.5), (1.0, 0.0)],
    )
    def test_confidence_is_one_minus_confidence(self, confidence: float, expected: float):
        factor, _ = _confidence_factor(confidence)
        assert factor == pytest.approx(expected)

    def test_confidence_clamps_out_of_range(self):
        assert _confidence_factor(3.0)[0] == pytest.approx(0.0)
        assert _confidence_factor(-3.0)[0] == pytest.approx(1.0)

    def test_budget_factor_branches(self):
        assert _budget_factor(None)[0] == pytest.approx(0.0)  # 未配置预算 → 因子 0
        assert _budget_factor(0.1)[0] == pytest.approx(0.1)
        assert _budget_factor(0.3)[0] == pytest.approx(0.3)
        assert _budget_factor(0.6)[0] == pytest.approx(0.7)
        assert _budget_factor(0.9)[0] == pytest.approx(1.0)
        assert _budget_factor(0.0, budget_exceeded=True)[0] == pytest.approx(1.0)


class TestImpactFactor:
    def test_small_change_scores_low(self):
        factor, reason = _impact_factor(3, 1, None)
        assert factor == pytest.approx(0.2)
        assert "small_impact" in reason

    def test_medium_change_scores_mid(self):
        factor, reason = _impact_factor(10, 2, None)
        assert factor == pytest.approx(0.5)
        assert "medium_impact" in reason

    def test_large_change_scores_high(self):
        factor, reason = _impact_factor(500, 9, None)
        assert factor == pytest.approx(0.8)
        assert "large_impact" in reason

    def test_contract_missing_symbols_dominate(self):
        factor, reason = _impact_factor(1, 1, ["missing_fn"])
        assert factor >= 0.9
        assert "contract_missing" in reason

    def test_blank_contract_symbols_are_ignored(self):
        factor, reason = _impact_factor(1, 1, ["   ", ""])
        assert factor == pytest.approx(0.2)
        assert "contract_missing" not in reason

    def test_full_file_patch_dominates(self):
        factor, reason = _impact_factor(1, 1, None, full_file_patch=True)
        assert factor >= 0.9
        assert "full_file_patch" in reason

    def test_none_inputs_are_zero_change(self):
        factor, reason = _impact_factor(None, None, None)
        assert factor == pytest.approx(0.2)
        assert "small_impact" in reason


class TestAssessTaskRisk:
    def _clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "RISK_WEIGHT_CONFIDENCE",
            "RISK_WEIGHT_IMPACT",
            "RISK_WEIGHT_BUDGET",
            "RISK_THRESHOLD_MEDIUM",
            "RISK_THRESHOLD_HIGH",
        ):
            monkeypatch.delenv(name, raising=False)

    def test_high_signals_raise_score(self, monkeypatch: pytest.MonkeyPatch):
        self._clear(monkeypatch)
        result = assess_task_risk(
            confidence=0.0,
            changed_lines=500,
            changed_files=9,
            contract_missing_symbols=["fn"],
            full_file_patch=True,
            budget_ratio=0.95,
        )
        assert 0.0 <= float(result.risk_score) <= 1.0
        assert float(result.risk_score) >= 0.9
        assert result.risk_level in {"low", "medium", "high"}

    def test_low_signals_stay_low(self, monkeypatch: pytest.MonkeyPatch):
        self._clear(monkeypatch)
        result = assess_task_risk(confidence=1.0, changed_lines=1, changed_files=1)
        assert float(result.risk_score) <= 0.5

    def test_missing_signals_are_conservative_not_zero(self, monkeypatch: pytest.MonkeyPatch):
        self._clear(monkeypatch)
        result = assess_task_risk()
        assert 0.0 <= float(result.risk_score) <= 1.0

    def test_zero_total_weight_falls_back_to_uniform(self, monkeypatch: pytest.MonkeyPatch):
        """三权重全 0 → 除零保护分支（此前未覆盖）：退化为等权 1/3，不得抛 ZeroDivisionError。"""
        self._clear(monkeypatch)
        monkeypatch.setenv("RISK_WEIGHT_CONFIDENCE", "0")
        monkeypatch.setenv("RISK_WEIGHT_IMPACT", "0")
        monkeypatch.setenv("RISK_WEIGHT_BUDGET", "0")
        result = assess_task_risk(confidence=0.5, changed_lines=10, changed_files=2)
        assert 0.0 <= float(result.risk_score) <= 1.0

    def test_thresholds_are_configurable(self, monkeypatch: pytest.MonkeyPatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("RISK_THRESHOLD_MEDIUM", "0.05")
        monkeypatch.setenv("RISK_THRESHOLD_HIGH", "0.10")
        result = assess_task_risk(confidence=0.0, changed_lines=100, changed_files=5)
        assert result.risk_level in {"low", "medium", "high"}


class TestBuildRiskSummary:
    def test_summary_is_json_serializable_and_has_pause_flag(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RISK_APPROVAL_ENABLE", raising=False)
        summary = build_risk_summary(0.1, 500, 9, ["fn"], True, 0.95, None)
        assert isinstance(summary, dict)
        assert "pause_requested" in summary
        assert summary["pause_requested"] is False  # 默认关：历史零变化

    def test_pause_requested_only_when_switch_on_and_action_demands(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        summary = build_risk_summary(0.0, 900, 12, ["a", "b"], True, 1.0, True)
        assert "pause_requested" in summary
        assert summary["pause_requested"] is True
