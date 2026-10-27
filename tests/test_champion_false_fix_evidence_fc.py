"""FC 轮锁：champion 守卫不得把「假修复率无观测」读作 0（给无证据的臂发通行证）。

缺陷（2026-10-27 审查，ADR-0036 判据 A 的"测量纪律"面）：
    `select_champion` 的防"刷 passed"约束原式为
        `false_fix_ok = float(stats.get("mean_false_fix", 0.0)) <= max_false_fix`
    而 `mean_false_fix` 由 `_mean(arm_false_fix[arm])` 计算——**零样本时
    `_mean([])` 返回 0.0**。于是「一条假修复率观测都没有」的臂
    （`n_false_fix == 0`）拿到 `mean_false_fix = 0.0`，**空洞通过**该守卫
    并被选为 champion：守卫在关键处从未真正判读。

    「没测」被读成了「测得 0」。真值语义在
    `experiments/_m1_metrics.py::_compute_false_fix_rate`：`repair_rate` 为
    None（无 gold 材料 / gold 套件全 skip / rc==5 / 执行超时）时
    `false_fix_rate` 恒为 None；`detection_rate` 由**另一条**路径独立计算
    （跑的是生成测试，不是 gold 套件）——因此"检出率可测、假修复率不可测"
    是真实可达的组合，不是理论构造。

判据三层（先红后绿）：
    1. 单元层：候选臂 detection 严格优于 incumbent 但 `n_false_fix == 0`
       ⇒ 不得被选为 champion，原因须点名该臂与"无观测"；
    2. 端到端层：真实 `OrchestrationSearch` + 真实报告装配，桩化单 cell
       评估 ⇒ 报告 `champion` 为 None，`arm_stats[*].n_false_fix` 披露 0；
    3. 读者层：报告须披露假修复率**观测数**；Markdown 表格在零观测时显示
       "不可测"而不是 0.0000（否则缺证据仍会被读成"无假修复"）。
    反向对照：有观测且不超限的臂仍可当 champion（守卫不得变成永假）。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.graph.orchestration_search import (
    ArmSpec,
    Cell,
    CellResult,
    OrchestrationSearch,
    SearchBudget,
    select_champion,
)


def _stats(**overrides: Any) -> dict[str, Any]:
    """一份臂统计的完整骨架（缺省 = 有观测、假修复率 0）。"""
    base: dict[str, Any] = {
        "n_measurable": 10,
        "unmeasurable": 0,
        "excluded_reason": None,
        "mean_detection": 0.45,
        "se_detection": 0.1,
        "mean_tokens": 4000.0,
        "mean_duration_s": 1.5,
        "n_false_fix": 10,
        "mean_false_fix": 0.0,
        "repair_any": False,
    }
    base.update(overrides)
    return base


class TestChampionFalseFixEvidence:
    def test_arm_without_false_fix_observation_is_not_champion(self) -> None:
        """核心判据：检出率更优但假修复率零观测 ⇒ 不得当 champion。"""
        arm_stats = {
            "df_incumbent": _stats(),
            "no_evidence": _stats(mean_detection=0.90, n_false_fix=0),
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "no_evidence" in reason
        assert "无观测" in reason

    def test_zero_sample_is_not_read_as_measured_zero(self) -> None:
        """「没测」不得被读成「测得 0」：显式 mean_false_fix=0.0 同样不得放行。"""
        arm_stats = {
            "df_incumbent": _stats(),
            "trap": _stats(mean_detection=0.90, n_false_fix=0, mean_false_fix=0.0),
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "trap" in reason

    def test_missing_key_is_treated_as_no_observation(self) -> None:
        """老调用方漏带 `n_false_fix` ⇒ 按无观测处理（fail-closed），不按 0 放行。"""
        arm_stats = {
            "df_incumbent": _stats(),
            "legacy_shape": {"n_measurable": 10, "mean_detection": 0.90, "mean_tokens": 4000.0, "mean_false_fix": 0.0},
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "legacy_shape" in reason

    def test_measured_arm_still_wins(self) -> None:
        """反向对照：有观测且不超限的臂仍可当 champion（守卫不得变成永假）。"""
        arm_stats = {
            "df_incumbent": _stats(),
            "measured": _stats(mean_detection=0.90, n_false_fix=10, mean_false_fix=0.1),
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion == "measured"
        assert "measured" in reason

    def test_observed_but_over_limit_still_rejected(self) -> None:
        """反向对照：有观测但超 0.5 上限 ⇒ 仍落选（修复不得放宽原约束）。"""
        arm_stats = {
            "df_incumbent": _stats(),
            "hacky": _stats(mean_detection=0.90, n_false_fix=10, mean_false_fix=0.9),
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "hacky" in reason
        assert "mean_false_fix" in reason


def _run_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    false_fix_rate: float | None,
    max_evals: int = 12,
) -> dict[str, Any]:
    """真实 `OrchestrationSearch` + 真实报告装配（只桩掉单 cell 评估）。"""
    monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", "true")
    arms = [
        ArmSpec(arm_id="df_incumbent", planner=False, debugger=False),
        ArmSpec(arm_id="cand", planner=True, debugger=True),
    ]
    cells = [Cell(task_id=f"t{i:02d}", seed=42, task=None) for i in range(6)]

    def _evaluator(arm: Any, cell: Cell) -> CellResult:
        return CellResult(
            arm_id=arm.arm_id,
            task_id=cell.task_id,
            seed=cell.seed,
            detection=0.45 if arm.arm_id == "df_incumbent" else 1.0,
            false_fix_rate=false_fix_rate,
            total_tokens=10,
        )

    search = OrchestrationSearch(
        arms=arms,
        cells=cells,
        budget=SearchBudget(max_evals=max_evals, max_total_tokens=10**9),
        seed=7,
        evaluator=_evaluator,
        min_evals_per_arm=2,
    )
    return search.run()


class TestSearchReportDisclosesFalseFixEvidence:
    def test_report_does_not_crown_arm_without_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端：假修复率全不可测的臂即使检出率更优也不得被选为 champion。"""
        report = _run_search(monkeypatch, false_fix_rate=None)
        assert report["champion"] is None
        assert "无观测" in report["champion_reason"]
        assert all(stats["n_false_fix"] == 0 for stats in report["arm_stats"].values())

    def test_report_crowns_arm_when_evidence_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """反向对照：假修复率有观测且不超限 ⇒ 冠军照常产生（守卫不空转）。"""
        report = _run_search(monkeypatch, false_fix_rate=0.1)
        assert report["champion"] == "cand"
        assert all(stats["n_false_fix"] > 0 for stats in report["arm_stats"].values())

    def test_sample_count_matches_observations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """披露的观测数必须等于实际观测数（不是常数、不是 0/1 兜底）。"""
        report = _run_search(monkeypatch, false_fix_rate=0.25)
        for stats in report["arm_stats"].values():
            assert stats["n_false_fix"] == stats["n_measurable"]
            assert stats["mean_false_fix"] == pytest.approx(0.25)


class TestMarkdownRendererDisclosesUnmeasurable:
    @staticmethod
    def _render(arm_stats: dict[str, dict[str, Any]]) -> str:
        from experiments.run_orchestration_search import _render_attribution_md

        report: dict[str, Any] = {
            "config": {"n_arms": len(arm_stats), "ucb_c": 1.0, "seed": 0, "max_unmeasurable": 5, "n_cells": 1},
            "budget": {
                "max_evals": 10,
                "max_total_tokens": 100,
                "evals_used": 1,
                "tokens_used": 10,
                "stop_reason": "max_evals",
            },
            "coverage": {"cells_observed": 1},
            "arm_stats": arm_stats,
            "champion": None,
            "champion_reason": "（测试构造）",
        }
        meta = {"cache_namespace": "seed42", "run_id": "fc-test-run", "task_count": 1, "seeds": [42]}
        return _render_attribution_md(report, {}, meta)

    def test_zero_observation_renders_as_unmeasurable(self) -> None:
        """零观测时表格须写"不可测"，不得写 0.0000（缺证据≠无假修复）。"""
        md = self._render({"cand": _stats(n_false_fix=0)})
        # 断言精确到表格单元（表头本身含"n不可测"列名，不能用全文包含判定）
        assert "| 0 | 不可测 |" in md
        assert "| 0 | 0.0000 |" not in md

    def test_observed_value_is_rendered(self) -> None:
        """有观测时照常渲染数值（披露不是把列抹掉）。"""
        md = self._render({"cand": _stats(n_false_fix=3, mean_false_fix=0.125)})
        assert "| 3 | 0.1250 |" in md
        assert "| 3 | 不可测 |" not in md
