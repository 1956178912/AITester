# ULT Mut@k 补测脚本的回归测试（2026-10-14）
#
# 覆盖 experiments/emse_ult_mutk.py 的纯函数纪律：
#   - measure_task 的保守跳过分支（无 fixed/无模块/空测试 → skipped，不进分母）；
#   - _aggregate 的池化口径（killed/total 合计 + 均值 + 跳过统计）；
#   - 口径常量（max_mutants 截断面 / timeout）与 ult_bridge_plan §4.3 裁定一致。

from __future__ import annotations

from experiments.emse_ult_mutk import (
    MAX_MUTANTS,
    TIMEOUT_SECONDS,
    _aggregate,
    measure_task,
)


def _row(**overrides):
    row = {
        "task_id": "ult__demo",
        "task_metadata": {"fixed": "def f(x):\n    return x\n", "function_name": "f"},
        "generated_test": "",
    }
    row.update(overrides)
    return row


def test_measure_task_missing_fixed_skips() -> None:
    """无 fixed 材料 → 保守 skipped（不进 Mut@k 分母）。"""
    r = measure_task(_row(task_metadata={"function_name": "f"}), "def test_x(): pass")
    assert r["skipped"] is True
    assert r["skip_reason"] == "no_fixed_or_module"


def test_measure_task_empty_test_skips() -> None:
    """生成测试为空 → 保守 skipped。"""
    r = measure_task(_row(), "   ")
    assert r["skipped"] is True
    assert r["skip_reason"] == "empty_test"


def test_aggregate_pools_killed_over_total_and_means() -> None:
    """池化口径：killed/total 合计（非均值平均），任务级均值并列。"""
    results = [
        {"task_id": "a", "skipped": False, "mutation_score": 1.0, "mutants_killed": 10, "mutants_total": 10},
        {"task_id": "b", "skipped": False, "mutation_score": 0.5, "mutants_killed": 5, "mutants_total": 10},
        {"task_id": "c", "skipped": True, "skip_reason": "empty_test"},
    ]
    agg = _aggregate(results)
    assert agg["n_tasks"] == 3
    assert agg["n_measured"] == 2
    assert agg["n_skipped"] == 1
    assert agg["mutants_killed"] == 15
    assert agg["mutants_total"] == 20
    assert agg["pooled_mutation_score"] == 0.75  # 15/20（合计口径）
    assert agg["mean_mutation_score"] == 0.75  # (1.0+0.5)/2


def test_aggregate_empty_is_none_not_zero() -> None:
    """无可测任务 → None（不得假报 0.0）。"""
    agg = _aggregate([{"task_id": "a", "skipped": True, "skip_reason": "x"}])
    assert agg["pooled_mutation_score"] is None
    assert agg["mean_mutation_score"] is None
    assert agg["n_measured"] == 0


def test_caliber_constants_match_ult_bridge_plan() -> None:
    """口径常量与 docs/design/ult_bridge_plan.md §4.3 裁定一致（timeout=killed）。"""
    assert MAX_MUTANTS == 10  # 确定性截断面（与自研 AST 变异体口径一致）
    assert TIMEOUT_SECONDS == 120  # ULT 官方 Cosmic-Ray 口径
