#!/usr/bin/env python3
"""B6（2026-10-16）：success 呈现层降级回归锁定。

锁定四组行为（对应状态登记册 §2 B6 的三个变更点）：
1. `compute_significance` 基口径 = detection_rate（M1 诚实口径，None 剔除
   不计 0；配对两侧均须可测）；旧批次缺字段时回退 passed 并在返回体标注
   basis（防静默用错口径）；
2. 三指标统计（detection/false_fix/repair）None 剔除、括号内可测 n；
3. 报告首表列序：Detection/False-Fix/Repair 在前，Success*（自指口径）后移
   且附"不得单独引用"注记；显著性章节标题带基口径标签；
4. `cohens_d` 新增 field 参数向后兼容（默认 "passed" 与历史逐位一致）。
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

vr = importlib.import_module("experiments.visualize_results")
sa = importlib.import_module("experiments.statistical_analysis")


def _row(tid: str, *, det: Any, passed: bool, ffx: Any = 0.0, rep: Any = 0.0, cov: float = 90.0) -> dict[str, Any]:
    return {
        "task_id": tid,
        "detection_rate": det,
        "false_fix_rate": ffx,
        "repair_rate": rep,
        "passed": passed,
        "coverage": cov,
    }


def _summary() -> dict[str, Any]:
    # aitester：3 可测（1 检出）+ 1 不可测；plain_llm_df：全可测
    a_rows = [
        _row("t1", det=1.0, passed=True),
        _row("t2", det=0.0, passed=False),
        _row("t3", det=0.0, passed=True),
        _row("t4", det=None, passed=False),
    ]
    b_rows = [
        _row("t1", det=1.0, passed=True),
        _row("t2", det=1.0, passed=False, ffx=1.0),
        _row("t3", det=0.0, passed=False),
        _row("t4", det=1.0, passed=True),
    ]
    return {
        "dataset": "unit",
        "results": {
            "aitester": {
                "details": a_rows,
                "success_rate": 50.0,
                "passed_count": 2,
                "failure_count": 2,
                "avg_coverage": 90.0,
                "avg_iterations": 1.0,
                "avg_elapsed_seconds": 1.0,
                "total_time": 4.0,
                "total_functions": 4,
            },
            "plain_llm_df": {
                "details": b_rows,
                "success_rate": 25.0,
                "passed_count": 1,
                "failure_count": 3,
                "avg_coverage": 90.0,
                "avg_iterations": 1.0,
                "avg_elapsed_seconds": 1.0,
                "total_time": 4.0,
                "total_functions": 4,
            },
        },
    }


@pytest.mark.unit
class TestDetectionBasis:
    def test_basis_is_detection_and_none_excluded(self) -> None:
        sig = vr.compute_significance(_summary())
        assert sig["basis"] == "detection"
        pb = sig["per_baseline"]
        # aitester：3 可测（1.0+0.0+0.0）→ 33.3，n=3；None 行不进分母（计分母会得 25）
        assert pb["aitester"]["detection"] == {"mean_pct": 33.3, "std_pct": 57.7, "n": 3}
        assert pb["aitester"]["n"] == 4
        assert pb["aitester"]["n_measurable"] == 3
        # 配对样本量 = 两侧均可测的共同任务数（t4 的 aitester 侧为 None → 排除）
        assert sig["pairwise"], sig
        assert len(sig["pairwise"]) == 1

    def test_fallback_to_passed_when_detection_absent(self, capsys: pytest.CaptureFixture[str]) -> None:
        summary = _summary()
        for bl in summary["results"]:
            for row in summary["results"][bl]["details"]:
                row["detection_rate"] = None
        sig = vr.compute_significance(summary)
        assert sig["basis"] == "passed"
        assert "回退 passed" in capsys.readouterr().out
        # passed 基口径统计：aitester 2/4 = 50.0
        assert sig["per_baseline"]["aitester"]["mean_rate"] == 50.0


@pytest.mark.unit
class TestSummaryMdLayout:
    def test_column_order_and_notes(self, tmp_path: Path) -> None:
        sig = vr.compute_significance(_summary())
        vr._charts_dir = str(tmp_path)  # type: ignore[attr-defined]
        vr.write_summary_md(_summary(), sig)
        text = (tmp_path / "summary_stats.md").read_text(encoding="utf-8")
        header = next(line for line in text.splitlines() if line.startswith("| Baseline |"))
        assert header.index("Detection Rate (n)") < header.index("Success* %")
        assert header.index("False-Fix Rate (n)") < header.index("Success* %")
        assert "不得单独引用" in text
        assert "基口径 = 检出率（detection）" in text


@pytest.mark.unit
class TestCohensDFieldCompat:
    def test_default_matches_passed_field(self) -> None:
        summary = _summary()
        a = summary["results"]["aitester"]["details"]
        b = summary["results"]["plain_llm_df"]["details"]
        assert sa.cohens_d(a, b) == sa.cohens_d(a, b, field="passed")

    def test_detection_field_uses_measurable_pairs(self) -> None:
        summary = _summary()
        a = summary["results"]["aitester"]["details"]
        b = summary["results"]["plain_llm_df"]["details"]
        d, n = sa.cohens_d(a, b, field="detection_rate")
        assert n == 3  # t4 在 aitester 侧不可测 → 不配对
        assert d != 0.0  # 检出差方向明确（a:1/3，b:2/3）
