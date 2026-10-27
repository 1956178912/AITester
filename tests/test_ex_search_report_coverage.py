"""EX 轮：搜索报告的「设计集分母」与「观测覆盖」不得混为一谈。

缺陷：`build_search_report` 把 rows 里 distinct (task, seed) 写进
`config.n_cells`，而归因报告 MD 把该字段标注为「设计集」。预算/排除让搜索
提前停止时，同一行会自相矛盾（「12 任务 × 3 种子 = 16 cell」），且设计集的
真实分母在工件中不可恢复。

锁口径：
- `config.n_cells` = 设计集唯一 cell 数（与预算无关）；
- `coverage.cells_observed` = 本次实际触达的 distinct cell 数；
- 归因 MD 同时披露两者（分母可见，截断不隐藏）。
"""

from __future__ import annotations

import pytest

from experiments.run_orchestration_search import _render_attribution_md
from src.graph.orchestration_search import (
    ARM_REGISTRY,
    Cell,
    CellResult,
    OrchestrationSearch,
    SearchBudget,
)


@pytest.fixture(autouse=True)
def _search_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启主开关（构造期读 env）。"""
    monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", "true")


class _StubEvaluator:
    """确定性桩评估器：零 LLM、固定奖励与 token。"""

    def __call__(self, arm, cell: Cell) -> CellResult:
        return CellResult(
            arm_id=arm.arm_id,
            task_id=cell.task_id,
            seed=cell.seed,
            detection=0.0,
            total_tokens=1000,
            llm_calls=2,
            duration_s=0.1,
            trace_records=[],
        )


def _make_cells(n: int) -> list[Cell]:
    """n 个唯一 (task, seed=42) cell（task=None——桩评估器不触达任务对象）。"""
    return [Cell(task_id=f"synthetic__t{i:04d}", seed=42, task=None) for i in range(n)]


def _run(cells: list[Cell], *, max_evals: int) -> dict:
    search = OrchestrationSearch(
        arms=ARM_REGISTRY,
        cells=cells,
        budget=SearchBudget(max_evals=max_evals, max_total_tokens=10**9),
        ucb_c=1.0,
        seed=42,
        evaluator=_StubEvaluator(),
    )
    return search.run()


def _md(report: dict) -> str:
    return _render_attribution_md(
        report,
        {},
        {
            "run_id": "ex-probe",
            "task_count": 12,
            "seeds": "42,43,44",
            "cache_namespace": "orch_search_s42",
        },
    )


def test_design_set_size_survives_a_truncated_search() -> None:
    """预算截断时：config.n_cells 仍是设计集 36，覆盖另行披露为 16。"""
    report = _run(_make_cells(36), max_evals=16)

    assert report["budget"]["evals_used"] == 16
    assert report["config"]["n_cells"] == 36
    assert report["coverage"]["cells_observed"] == 16


def test_full_coverage_equals_design_set() -> None:
    """负向对照：全部 cell 都被触达时，覆盖数 = 设计集数。"""
    report = _run(_make_cells(2), max_evals=240)

    assert report["budget"]["stop_reason"] == "all_arms_excluded"
    assert report["config"]["n_cells"] == 2
    assert report["coverage"]["cells_observed"] == 2


def test_duplicate_cells_count_once_in_design_set() -> None:
    """重复 (task, seed) 不放大分母：设计集按唯一 cell 计。"""
    base = _make_cells(2)
    report = _run([base[0], base[0], base[1]], max_evals=16)

    assert report["config"]["n_cells"] == 2
    assert report["coverage"]["cells_observed"] == 2


def test_attribution_md_reports_design_set_and_coverage() -> None:
    """归因 MD 的「设计集」行不再被观测数篡改，并新增覆盖行。"""
    md = _md(_run(_make_cells(36), max_evals=16))

    assert "设计集：synthetic 12 任务 × 种子 42,43,44 = 36 cell" in md
    assert "覆盖：16 / 36 cell（44.4%）" in md
    assert "= 16 cell" not in md


def test_attribution_md_full_coverage_is_hundred_percent() -> None:
    """全量触达时覆盖行显示 100.0%。"""
    md = _md(_run(_make_cells(2), max_evals=240))

    assert "覆盖：2 / 2 cell（100.0%）" in md
