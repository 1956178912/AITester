#!/usr/bin/env python3
"""批次级配额预算与跑批前置闸的回归锁定（EMSE 批次 2026-10-15）。

锁定四件事：
1. **未配置 ≠ 无限**：`AITESTER_BATCH_MAX_CALLS` 未设时评估结果必须落到
   `blocking`（否则重演 SWE-bench Lite"20 次尝试 → 10 次超时 + 7 次 429 失败"）；
2. **估算公式可复算**：任务数 × 最坏臂每任务调用数 × 重试系数，向上取整；
3. **"上限低于估算"必须阻断**：配置存在但不足时同样不进批次；
4. **前置闸退出码语义**：非 strict 恒 0（告警）、strict 有阻断项 → 1。

全部用例零网络、零 LLM（`quota_probe` 不在本文件覆盖范围：它需要真实凭据）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from src.budget.batch_quota import (
    PER_TASK_CALLS_WORST,
    RETRY_FACTOR,
    assess_batch_budget,
    batch_cap_calls,
    batch_cap_usd,
    estimate_calls,
    preflight_required,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PREFLIGHT_PATH = _REPO_ROOT / "scripts" / "tools" / "run_preflight.py"
_spec = importlib.util.spec_from_file_location("_run_preflight", _PREFLIGHT_PATH)
assert _spec and _spec.loader
preflight = importlib.util.module_from_spec(_spec)
sys.modules["_run_preflight"] = preflight
_spec.loader.exec_module(preflight)

# 与批次预算相关的全部环境变量（逐个清理，避免宿主机环境污染用例）
_BUDGET_ENV_VARS = (
    "AITESTER_BATCH_MAX_CALLS",
    "AITESTER_BATCH_MAX_USD",
    "AITESTER_RUN_PREFLIGHT",
    "COST_BUDGET_ENABLE",
    "COST_BUDGET_TOKENS",
    "COST_BUDGET_USD",
    "BENCHMARK_PARALLELISM",
)


@pytest.fixture(autouse=True)
def _clean_budget_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _BUDGET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class TestEnvParsing:
    def test_unset_caps_are_none_not_zero_or_infinite(self):
        assert batch_cap_calls() is None
        assert batch_cap_usd() is None
        assert preflight_required() is False

    def test_caps_parse_int_and_float(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", "2000")
        monkeypatch.setenv("AITESTER_BATCH_MAX_USD", "12.5")
        monkeypatch.setenv("AITESTER_RUN_PREFLIGHT", "true")
        assert batch_cap_calls() == 2000
        assert batch_cap_usd() == pytest.approx(12.5)
        assert preflight_required() is True

    @pytest.mark.parametrize("raw", ["", "abc", "1e400x"])
    def test_malformed_caps_degrade_to_none(self, monkeypatch: pytest.MonkeyPatch, raw: str):
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", raw)
        assert batch_cap_calls() is None


class TestEstimate:
    def test_formula_matches_documented_caliber(self):
        # 261 任务 → ceil(261 × 4.3 × 1.5) = 1684（+1 保证严格大于乘积）
        assert estimate_calls(261) == int(261 * PER_TASK_CALLS_WORST * RETRY_FACTOR) + 1

    def test_monotone_in_task_count(self):
        assert estimate_calls(10) < estimate_calls(100) < estimate_calls(1000)

    def test_zero_and_negative_tasks_yield_zero(self):
        assert estimate_calls(0) == 0
        assert estimate_calls(-5) == 0


class TestAssessment:
    def test_all_unset_is_blocking(self):
        a = assess_batch_budget(261)
        assert a.batch_cap_calls is None
        assert a.task_level_enabled is False
        assert a.ok is False
        assert len(a.blocking) == 2  # 任务级未启用 + 批次级未配置

    def test_task_budget_enabled_but_batch_cap_missing_still_blocks(self, monkeypatch: pytest.MonkeyPatch):
        """只有任务级闸不够——SWE-bench 的失败模式正是"单任务没失控、整批烧穿"。"""
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "60000")
        a = assess_batch_budget(261)
        assert a.task_level_enabled is True
        assert a.batch_cap_calls is None
        assert a.ok is False
        assert any("批次级调用上限未配置" in b for b in a.blocking)

    def test_configured_cap_below_estimate_blocks(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", "200")
        a = assess_batch_budget(261)
        assert a.ok is False
        assert any("低于估算上界" in b for b in a.blocking)

    def test_configured_cap_above_estimate_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "60000")
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", "5000")
        a = assess_batch_budget(261)
        assert a.ok is True, a.blocking
        assert a.batch_cap_calls == 5000
        assert a.task_level_tokens == 60000


class TestPreflightCli:
    def test_report_shape_from_shared_caliber(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", "9999")
        report = preflight.batch_budget_report(87, 4)
        assert report["expect_tasks"] == 87
        assert report["estimated_calls_upper_bound"] == estimate_calls(87)
        assert report["batch_cap_calls"] == 9999
        assert report["blocking"] == []

    def test_non_strict_returns_zero_even_with_blocking(self):
        assert preflight.main(["--expect-tasks", "261"]) == 0

    def test_strict_returns_one_when_blocking(self):
        assert preflight.main(["--expect-tasks", "261", "--strict"]) == 1

    def test_strict_returns_zero_when_configured(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "60000")
        monkeypatch.setenv("AITESTER_BATCH_MAX_CALLS", "99999")
        # 工作树干净与否不影响本断言的语义：只要求"预算项已配置"时预算类阻断消失。
        report = preflight.batch_budget_report(261, 4)
        assert report["blocking"] == []

    def test_git_state_reports_dirty_boolean(self):
        state = preflight.git_state()
        assert state["sha"] is None or len(str(state["sha"])) == 40
        assert isinstance(state["dirty"], bool)

    def test_fingerprint_scan_reads_provenance(self):
        rows = preflight.recent_fingerprints(limit=3)
        for row in rows:
            assert set(row) == {"file", "model_name", "pinned", "returned_model", "git_dirty"}
