"""AO（2026-10-21）：报告级 token 汇总读端——读不动不是 0。

覆盖三个此前各自持有 `int(... or 0)` / `_safe_float(... or 0)` 的报告消费者：
- experiments/model_gradient.py 档位 token 合计；
- experiments/compare_failures.py 翻转任务 token 单元格与两侧合计；
- experiments/analysis_parts/convergence_analysis.py 逐轮 Token 效率曲线。

锁的口径：
- 共享 :func:`row_total_token_reading` / :func:`aggregate_row_token_totals`
  是唯一总量读数；`total_tokens` 在场合法即可读（旧 JSON total-only 不回归），
  `total_tokens` 缺席而 in/out 齐全时读 in+out，坏值 / 非对象 / 部分正和不可读；
- 不可读 → 总量 None（不给部分和）、报告显示“不可读”并点名机制；
- 整键缺席 / null 保留历史 0；`total_tokens` 与 in+out 矛盾仍可读但披露；
- 真批次（main_batch 三份）零不可读行，新总量与旧循环逐臂一致。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from experiments import compare_failures as cf
from experiments import model_gradient as mg
from experiments.analysis_parts.convergence_analysis import _convergence_token_efficiency
from src.budget import token_usage as tu

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]


def _row(usage: Any) -> dict[str, Any]:
    return {"task_id": "T", "passed": False, "iterations": 0, "token_usage": usage}


def _detail(usage: Any, iterations: int = 0, passed: bool = False) -> dict[str, Any]:
    return {"task_id": "T", "passed": passed, "iterations": iterations, "token_usage": usage}


def _table_row(report: str, task_id: str) -> str:
    return next(line for line in report.splitlines() if line.startswith(f"| {task_id} "))


def _total_line(report: str) -> str:
    return next(line for line in report.splitlines() if line.startswith("**翻转任务 token 对比**"))


class TestSharedTotalReading:
    """共享总量读数：只回答 total 是否可读，值域与成本三元组同源。"""

    def test_total_only_is_readable(self) -> None:
        reading = tu.row_total_token_reading(_row({"total_tokens": 200}))
        assert reading["total"] == 200
        assert reading["absent"] is False
        assert reading["reasons"] == []

    def test_inout_only_sums(self) -> None:
        reading = tu.row_total_token_reading(_row({"input_tokens": 10, "output_tokens": 5}))
        assert reading["total"] == 15
        assert reading["reasons"] == []

    def test_absent_and_null_are_historical_zero(self) -> None:
        absent = tu.row_total_token_reading({"task_id": "T"})
        null = tu.row_total_token_reading(_row(None))
        assert absent == {"absent": True, "total": 0, "reasons": [], "contradiction": False}
        assert null["absent"] is True and null["total"] == 0

    @pytest.mark.parametrize(
        "value",
        [True, 10.7, "100", -5, float("nan"), float("inf")],
        ids=["bool", "float", "str", "negative", "nan", "inf"],
    )
    def test_present_bad_total_is_unreadable(self, value: Any) -> None:
        reading = tu.row_total_token_reading(_row({"total_tokens": value}))
        assert reading["total"] is None
        assert reading["reasons"]

    @pytest.mark.parametrize("usage", [[], "oops", 3], ids=["list", "str", "int"])
    def test_non_object_usage_is_unreadable(self, usage: Any) -> None:
        reading = tu.row_total_token_reading(_row(usage))
        assert reading["total"] is None
        assert reading["reasons"][0].startswith("token_usage_not_object:")

    def test_zero_partial_is_historical_zero_row(self) -> None:
        assert tu.row_total_token_reading(_row({"input_tokens": 0}))["total"] == 0
        assert tu.row_total_token_reading(_row({}))["total"] == 0

    def test_positive_partial_without_total_is_unreadable(self) -> None:
        reading = tu.row_total_token_reading(_row({"input_tokens": 10}))
        assert reading["total"] is None
        assert "token_field_absent:total_tokens" in reading["reasons"]
        assert "token_field_absent:output_tokens" in reading["reasons"]

    def test_bad_field_without_total_names_the_field(self) -> None:
        reading = tu.row_total_token_reading(_row({"input_tokens": True, "output_tokens": 5}))
        assert reading["total"] is None
        assert reading["reasons"] == [
            "token_field_absent:total_tokens",
            "token_not_count:input_tokens:bool",
        ]

    def test_contradiction_keeps_total_readable(self) -> None:
        reading = tu.row_total_token_reading(_row({"total_tokens": 100, "input_tokens": 7, "output_tokens": 8}))
        assert reading["total"] == 100
        assert reading["contradiction"] is True
        assert reading["reasons"] == []

    def test_aggregate_clean_mixed_matches_old_sum(self) -> None:
        rows = [
            {"task_id": "A"},
            _row({"total_tokens": 100, "input_tokens": 40, "output_tokens": 60}),
            _row({"total_tokens": 200}),
            _row({"input_tokens": 10, "output_tokens": 5}),
        ]
        agg = tu.aggregate_row_token_totals(rows)
        assert agg["total_tokens"] == 315
        assert agg["n_absent_rows"] == 1
        assert agg["n_unreadable_rows"] == 0

    def test_aggregate_any_unreadable_blocks_partial_sum(self) -> None:
        rows = [_row({"total_tokens": 100}), _row({"total_tokens": "100"})]
        agg = tu.aggregate_row_token_totals(rows)
        assert agg["total_tokens"] is None
        assert agg["n_unreadable_rows"] == 1
        assert agg["reading_reasons"] == {"token_not_count:total_tokens:str": 1}

    def test_aggregate_contradiction_disclosed_but_summed(self) -> None:
        agg = tu.aggregate_row_token_totals([_row({"total_tokens": 100, "input_tokens": 7, "output_tokens": 8})])
        assert agg["total_tokens"] == 100
        assert agg["n_contradiction_rows"] == 1


class TestModelGradientTokenMetrics:
    """档位汇总：共享总量读数 + markdown 不可读披露。"""

    def test_clean_rows_use_shared_total(self) -> None:
        metrics = mg._tier_token_metrics([_detail({"total_tokens": 100}), _detail({"total_tokens": 200})])
        assert metrics["total_tokens"] == 300
        assert metrics["n_token_unreadable_rows"] == 0

    def test_unreadable_row_blocks_total(self) -> None:
        metrics = mg._tier_token_metrics([_detail({"total_tokens": 100}), _detail({"total_tokens": float("nan")})])
        assert metrics["total_tokens"] is None
        assert metrics["n_token_unreadable_rows"] == 1
        assert metrics["token_reading_reasons"] == {"token_not_finite:total_tokens": 1}

    def test_markdown_renders_unreadable_and_disclosure(self) -> None:
        metrics = {
            "tier": "tierA",
            "first_success_rate": 0.5,
            "avg_iterations": 1.5,
            "llm_applied_ratio": None,
            "total_tokens": None,
            "note": "本次新跑",
            "n_token_unreadable_rows": 2,
            "token_reading_reasons": {"token_not_count:total_tokens:str": 2},
        }
        md = mg._render_markdown("20261021_120000", 1, "synthetic", "level3", [metrics])
        row = next(line for line in md.splitlines() if line.startswith("| tierA "))
        assert "| 不可读 |" in row
        assert row.count("|") == 7
        assert "token 读数披露" in md
        assert "token_not_count:total_tokens:str×2" in md

    def test_markdown_clean_output_unchanged(self) -> None:
        metrics = {
            "tier": "tierA",
            "first_success_rate": 0.5,
            "avg_iterations": 1.5,
            "llm_applied_ratio": None,
            "total_tokens": 300,
            "note": "本次新跑",
        }
        md = mg._render_markdown("20261021_120000", 1, "synthetic", "level3", [metrics])
        assert "| tierA | 50.00% | 1.50 | N/A | 300 | 本次新跑 |" in md
        assert "token 读数披露" not in md

    def test_markdown_split_mismatch_disclosed(self) -> None:
        metrics = {
            "tier": "tierA",
            "first_success_rate": 0.5,
            "avg_iterations": 1.5,
            "llm_applied_ratio": None,
            "total_tokens": 100,
            "note": "",
            "n_token_split_mismatch_rows": 1,
        }
        md = mg._render_markdown("20261021_120000", 1, "synthetic", "level3", [metrics])
        assert "| 100 |" in md
        assert "1 行 total_tokens 与 in+out 不一致" in md

    def test_main_no_longer_sums_locally(self) -> None:
        src = inspect.getsource(mg.main)
        assert "total_tokens += int(" not in src
        assert "_tier_token_metrics(" in src


class TestCompareFailuresReport:
    """翻转任务报告：单行坏值不再炸整份报告，合计不给部分和。"""

    @staticmethod
    def _report(full_usage: Any, base_usage: Any = None) -> str:
        if base_usage is None:
            base_usage = {"total_tokens": 50}
        inverted = [
            {"task_id": "T1", "full": _row(full_usage), "base": _row(base_usage)},
        ]
        return cf.build_report(inverted, "aitester", "plain_llm", None)

    def test_clean_totals_unchanged(self) -> None:
        report = self._report({"total_tokens": 100, "input_tokens": 40, "output_tokens": 60})
        assert "aitester 合计 100，plain_llm 合计 50（完整系统多消耗 50，性价比倒挂需关注）" in report

    def test_non_object_row_does_not_crash(self) -> None:
        report = self._report("oops")
        assert "| 不可读 |" in _table_row(report, "T1")
        assert "aitester 合计 不可读（1 行无法读取）" in _total_line(report)
        assert "不作性价比倒挂判断" in _total_line(report)
        assert "aitester 1 行（token_usage_not_object:str×1）" in report

    def test_str_total_not_summed(self) -> None:
        report = self._report({"total_tokens": "100"})
        assert "| 不可读 |" in _table_row(report, "T1")
        assert "合计 100" not in _total_line(report)

    def test_absent_keeps_question_mark_and_historical_zero(self) -> None:
        report = self._report(None)
        assert "| ? |" in _table_row(report, "T1")
        assert "aitester 合计 0，plain_llm 合计 50" in _total_line(report)

    def test_inout_only_cell_and_total(self) -> None:
        report = self._report({"input_tokens": 10, "output_tokens": 5})
        assert "| 15 |" in _table_row(report, "T1")
        assert "aitester 合计 15" in _total_line(report)

    def test_total_only_cell(self) -> None:
        report = self._report({"total_tokens": 200})
        assert "| 200 |" in _table_row(report, "T1")
        assert "aitester 合计 200" in _total_line(report)

    def test_split_mismatch_disclosed_but_summed(self) -> None:
        report = self._report({"total_tokens": 100, "input_tokens": 7, "output_tokens": 8})
        assert "aitester 合计 100（其中 1 行 total 与 in+out 不一致）" in _total_line(report)
        assert "完整系统多消耗 50" in report

    def test_clean_report_has_no_disclosure(self) -> None:
        report = self._report({"total_tokens": 100})
        assert "Token 读数机制" not in report


class TestConvergenceTokenCurve:
    """逐轮 Token 曲线：坏值不再折成 0 / nan，整条曲线标注不可读。"""

    def test_total_only_amortized_unchanged(self) -> None:
        result = _convergence_token_efficiency([_detail({"total_tokens": 200}, iterations=2, passed=True)])
        assert result["available"] is True
        assert abs(result["rounds"]["2"]["incremental_tokens"] - 200 / 3) < 0.01

    def test_absent_is_historical_zero_and_available(self) -> None:
        result = _convergence_token_efficiency([_detail(None, iterations=1, passed=True)])
        assert result["available"] is True
        assert result["n_token_unreadable_rows"] == 0
        assert result["rounds"]["0"]["incremental_tokens"] == 0

    @pytest.mark.parametrize(
        "usage",
        [
            "oops",
            {"total_tokens": "100"},
            {"total_tokens": -100},
            {"total_tokens": float("nan")},
            {"input_tokens": 10},
        ],
        ids=["non-object", "str-total", "negative", "nan", "partial-positive"],
    )
    def test_bad_total_makes_curve_unavailable(self, usage: Any) -> None:
        result = _convergence_token_efficiency([_detail(usage, iterations=1, passed=True)])
        assert result["available"] is False
        assert result["rounds"] == {}
        assert result["n_token_unreadable_rows"] == 1
        assert result["token_reading_reasons"]

    def test_inout_only_is_readable(self) -> None:
        result = _convergence_token_efficiency(
            [_detail({"input_tokens": 10, "output_tokens": 5}, iterations=0, passed=True)]
        )
        assert result["available"] is True
        assert result["rounds"]["0"]["incremental_tokens"] == 15

    @pytest.mark.parametrize(
        "iterations",
        [
            [{"tokens": "100"}],
            [{"tokens": True}],
            [{"tokens": -50}],
            [{"tokens": float("nan")}],
            ["oops"],
            [{}],
        ],
        ids=["str", "bool", "negative", "nan", "non-dict", "missing-tokens"],
    )
    def test_bad_per_round_tokens_make_curve_unavailable(self, iterations: list[Any]) -> None:
        result = _convergence_token_efficiency(
            [_detail({"total_tokens": 100, "iterations": iterations}, iterations=0, passed=True)]
        )
        assert result["available"] is False
        assert result["n_token_unreadable_rows"] == 1
        assert result["token_reading_reasons"]

    def test_iterations_not_list_unavailable(self) -> None:
        result = _convergence_token_efficiency(
            [_detail({"total_tokens": 100, "iterations": {"0": 100}}, iterations=0, passed=True)]
        )
        assert result["available"] is False
        assert result["token_reading_reasons"] == {"token_usage_iterations_not_list:dict": 1}

    def test_clean_per_round_detail_unchanged(self) -> None:
        details = [
            _detail(
                {"total_tokens": 300, "iterations": [{"tokens": 100}, {"tokens": 100}, {"tokens": 100}]},
                iterations=2,
                passed=True,
            ),
            _detail({"total_tokens": 100, "iterations": [{"tokens": 100}]}, iterations=0, passed=False),
        ]
        result = _convergence_token_efficiency(details)
        assert result["available"] is True
        assert result["rounds"]["0"]["incremental_tokens"] == 100
        assert result["rounds"]["1"]["incremental_tokens"] == 0
        assert result["rounds"]["2"]["incremental_tokens"] == 100

    def test_one_bad_row_blocks_partial_curve(self) -> None:
        details = [
            _detail({"total_tokens": 100}, iterations=0, passed=True),
            _detail({"total_tokens": "100"}, iterations=0, passed=True),
        ]
        result = _convergence_token_efficiency(details)
        assert result["available"] is False
        assert result["rounds"] == {}
        assert result["n_token_unreadable_rows"] == 1

    def test_main_batches_have_no_unreadable_rows(self) -> None:
        checked_arms = 0
        for path in _MAIN_BATCH_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            for arm, block in data["results"].items():
                rows = [r for r in block.get("details", []) if isinstance(r, dict)]
                if not rows:
                    continue
                checked_arms += 1
                agg = tu.aggregate_row_token_totals(rows)
                reference = sum(
                    r["token_usage"]["total_tokens"]
                    for r in rows
                    if isinstance(r.get("token_usage"), dict) and "total_tokens" in r["token_usage"]
                )
                assert agg["n_unreadable_rows"] == 0, f"{path.name}:{arm}"
                assert agg["total_tokens"] == reference, f"{path.name}:{arm}"
                curve = _convergence_token_efficiency(rows)
                assert curve["available"] is True, f"{path.name}:{arm}"
                assert curve["n_token_unreadable_rows"] == 0, f"{path.name}:{arm}"
        assert checked_arms > 0

    def test_compare_report_no_local_total_sum(self) -> None:
        src = inspect.getsource(cf.build_report)
        assert 'get("total_tokens", 0)' not in src
        assert "aggregate_row_token_totals" in src
