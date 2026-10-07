"""修复引擎批次 IX（2026-10-07）：评估报告口径收口测试锁（ADR-0023）。

锁定三组行为：
1. pass@k 数学（HumanEval 无偏估计口径：n/c/k 边界、k>n 无定义、
   n-c<k 恒 1.0、多任务平均、轮次不足诚实截断）；
2. $/solved（correct=0 → None 诚实降级、正常除法、未计价 None）；
3. 污染视角聚合（五档计数、含污染 vs 干净 passed 率、None 行入
   unknown）+ run_all_statistics 三节接线存在性。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.statistical_analysis import (
    _pass_at_k_report_lines,
    _pass_at_k_value,
    contamination_view_summary,
    cost_per_solved,
    pass_at_k_summary,
)


class TestPassAtKValue:
    def test_all_success_is_one(self) -> None:
        assert _pass_at_k_value(3, 3, 1) == 1.0
        assert _pass_at_k_value(3, 3, 2) == 1.0

    def test_all_failure_is_zero(self) -> None:
        assert _pass_at_k_value(3, 0, 1) == 0.0

    def test_k_exceeds_n_undefined(self) -> None:
        assert _pass_at_k_value(2, 1, 3) is None
        assert _pass_at_k_value(0, 0, 1) is None

    def test_success_beyond_k_is_one(self) -> None:
        # n=4, c=3, k=2: 剩 1 个失败样本，抽 2 个必含成功 → 1.0
        assert _pass_at_k_value(4, 3, 2) == 1.0

    def test_one_of_two_rounds_k1(self) -> None:
        assert _pass_at_k_value(2, 1, 1) == pytest.approx(0.5)

    def test_one_of_two_rounds_k2_union(self) -> None:
        assert _pass_at_k_value(2, 1, 2) == 1.0


class TestPassAtKSummary:
    def test_multi_task_average(self) -> None:
        data = {
            "arm_a": [
                {"task_id": "t1", "patch_correct": 1},
                {"task_id": "t1", "patch_correct": 0},
                {"task_id": "t2", "patch_correct": 0},
                {"task_id": "t2", "patch_correct": 0},
            ]
        }
        s = pass_at_k_summary(data)
        assert s["arm_a"]["n_tasks"] == 2
        assert s["arm_a"]["rounds_min"] == 2
        assert s["arm_a"]["pass_at"][1] == pytest.approx(0.25)
        assert s["arm_a"]["pass_at"][2] == pytest.approx(0.5)

    def test_rounds_shortage_truncates_k(self) -> None:
        data = {
            "arm_a": [
                {"task_id": "t1", "patch_correct": 1},
                {"task_id": "t1", "patch_correct": 0},
            ]
        }
        s = pass_at_k_summary(data)
        assert 2 in s["arm_a"]["pass_at"]
        assert 3 not in s["arm_a"]["pass_at"]  # 轮次不足 k=3 诚实截断

    def test_none_rows_not_rounds(self) -> None:
        data = {"arm_a": [{"task_id": "t1", "patch_correct": None}, {"task_id": "t1", "patch_correct": 1}]}
        s = pass_at_k_summary(data)
        assert s["arm_a"]["n_tasks"] == 1
        assert s["arm_a"]["pass_at"][1] == 1.0

    def test_empty_arm(self) -> None:
        assert pass_at_k_summary({"arm_a": []})["arm_a"] == {"n_tasks": 0}

    def test_report_lines_shape(self) -> None:
        data = {"arm_a": [{"task_id": "t1", "patch_correct": 1}]}
        lines = _pass_at_k_report_lines(pass_at_k_summary(data), "patch_correct")
        assert any("pass@1" in ln for ln in lines)
        assert any("arm_a" in ln for ln in lines)


class TestCostPerSolved:
    def test_zero_solved_undefined(self) -> None:
        cost_rows = [{"baseline": "a", "cost": 1.0}]
        data = {"a": [{"patch_correct": 0}]}
        assert cost_per_solved(cost_rows, data) == {"a": None}

    def test_normal_division(self) -> None:
        cost_rows = [{"baseline": "a", "cost": 2.0}]
        data = {"a": [{"patch_correct": 1}, {"patch_correct": 1}, {"patch_correct": 0}, {"patch_correct": 1}]}
        assert cost_per_solved(cost_rows, data) == {"a": pytest.approx(2.0 / 3)}

    def test_unpriced_none(self) -> None:
        cost_rows = [{"baseline": "a", "cost": None}]
        data = {"a": [{"patch_correct": 1}]}
        assert cost_per_solved(cost_rows, data) == {"a": None}


class TestContaminationView:
    def test_counts_and_rates(self) -> None:
        data = {
            "a": [
                {"contamination_risk_level": "high", "passed": True},
                {"contamination_risk_level": "medium", "passed": True},
                {"contamination_risk_level": "low", "passed": False},
                {"contamination_risk_level": "low", "passed": True},
                {"contamination_risk_level": "not_applicable", "passed": True},
                {"passed": True},  # 缺键 → unknown
            ]
        }
        s = contamination_view_summary(data)["a"]
        assert s["counts"] == {"high": 1, "medium": 1, "low": 2, "unknown": 1, "not_applicable": 1}
        assert s["contaminated_passed_rate"] == 1.0
        assert s["clean_passed_rate"] == 0.5

    def test_empty_groups_none(self) -> None:
        s = contamination_view_summary({"a": []})["a"]
        assert s["contaminated_passed_rate"] is None
        assert s["clean_passed_rate"] is None


class TestRunAllStatisticsWiring:
    def test_sections_present_in_source(self) -> None:
        # 接线存在性锁（防节被误删）
        src = Path("experiments/statistical_analysis.py").read_text(encoding="utf-8")
        assert "## pass@k（多轮采样并集解决率" in src
        assert "## $/solved task" in src
        assert "## 污染视角（contamination_risk_level" in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
