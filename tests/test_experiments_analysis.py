"""测试 src/experiments/analysis.py（此前 0% 覆盖）

覆盖：
- analyze_experiment_results 的排名/对比/异常分支
- _compute_significance 三种状态（ok / insufficient_data / unavailable）
- 配对 t 检验（task_id 配对）与 Welch 双样本回退
- generate_comparison_report 的 Markdown 输出与落盘
- load_and_analyze 的 JSON 加载
"""

import json

import pytest

from src.experiments import analysis as analysis_module
from src.experiments.analysis import (
    analyze_experiment_results,
    generate_comparison_report,
    load_and_analyze,
)


def _results_with_details(n: int, passed_frac: float, baseline: str = "aitester") -> dict:
    """构造带 per-task details 的结果字典（前 passed_frac 比例的任务通过）。"""
    details = [{"task_id": f"t{i}", "passed": i < int(n * passed_frac)} for i in range(n)]
    passed = sum(1 for d in details if d["passed"])
    return {
        "passed_count": passed,
        "total_count": n,
        "success_rate": passed / n * 100,
        "avg_coverage": 80.0,
        "avg_iterations": 2.0,
        "details": details,
    }


class TestAnalyzeExperimentResults:
    """analyze_experiment_results 基本行为"""

    def test_empty_results_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            analyze_experiment_results({})

    def test_rankings_descending(self):
        results = {
            "a": _results_with_details(10, 0.5),
            "b": _results_with_details(10, 0.9),
        }
        analysis = analyze_experiment_results(results)
        ranks = analysis["rankings"]["success_rate"]
        assert ranks[0]["baseline"] == "b"
        assert ranks[0]["rank"] == 1
        assert ranks[1]["baseline"] == "a"

    def test_comparison_fields(self):
        analysis = analyze_experiment_results({"a": _results_with_details(10, 0.5)})
        assert analysis["baselines"] == ["a"]
        assert analysis["comparison"]["a"]["success_rate"] == 50.0

    def test_significance_insufficient_data_without_details(self):
        """只有聚合统计量（无 details）时如实标注 insufficient_data，不假装检验"""
        results = {"a": {"passed_count": 3, "total_count": 10, "success_rate": 30.0}}
        analysis = analyze_experiment_results(results)
        assert analysis["significance"]["status"] in ("insufficient_data", "unavailable")

    def test_significance_ok_paired(self):
        """两基线都带 task_id details 时走配对 t 检验。

        通过率取 5/6 vs 1/6（差值序列含 0 和 1），避免全同/全异二值分布
        触发 scipy 矩计算精度告警（退化数据）。
        """
        results = {
            "aitester": _results_with_details(6, 5 / 6),
            "plain_llm": _results_with_details(6, 1 / 6),
        }
        analysis = analyze_experiment_results(results)
        sig = analysis["significance"]
        assert sig["status"] == "ok"
        comp = sig["comparisons"][0]
        assert comp["method"] == "paired_t_test"
        assert comp["comparison"] == "aitester vs plain_llm"
        assert comp["n_a"] == 6 and comp["n_b"] == 6

    def test_significance_fallback_welch(self):
        """details 无 task_id 时退化为 Welch 双样本检验"""
        details_a = [{"task_id": None, "passed": i < 5} for i in range(10)]
        details_b = [{"task_id": None, "passed": i < 2} for i in range(10)]
        results = {
            "aitester": _results_with_details(10, 0.5) | {"details": details_a},
            "plain_llm": _results_with_details(10, 0.2) | {"details": details_b},
        }
        sig = analyze_experiment_results(results)["significance"]
        assert sig["status"] == "ok"
        assert sig["comparisons"][0]["method"] == "welch_t_test"

    def test_significance_scipy_unavailable(self, monkeypatch):
        """scipy 缺失时返回 unavailable 而非崩溃"""
        monkeypatch.setattr(analysis_module, "_SCIPY_AVAILABLE", False)
        monkeypatch.setattr(analysis_module, "scipy_stats", None)
        sig = analyze_experiment_results(
            {"aitester": _results_with_details(6, 1.0), "plain_llm": _results_with_details(6, 0.0)}
        )["significance"]
        assert sig["status"] == "unavailable"

    def test_significance_constant_groups_marked_skipped(self):
        """两组通过率恒定（配对全 1 vs 全 1）时 t 检验返回 NaN，记 skipped 而非数字条目。

        回归：此前 NaN 会经 round(float(nan)) 写入结果 JSON——非标准 JSON token，
        严格解析器（如 JS JSON.parse）报错。
        """
        results = {
            "aitester": _results_with_details(5, 1.0),
            "plain_llm": _results_with_details(5, 1.0),
        }
        analysis = analyze_experiment_results(results)
        sig = analysis["significance"]
        assert sig["status"] == "ok"
        comp = sig["comparisons"][0]
        assert comp["status"] == "skipped"
        assert "note" in comp
        # 整体结果 JSON 严格可解析：不得含非标准 NaN token
        assert "NaN" not in json.dumps(analysis)

    def test_significance_constant_groups_welch_marked_skipped(self):
        """无 task_id 退化 Welch 分支：两组全 0 vs 全 1（std 均为 0）同样记 skipped。"""
        details_a = [{"task_id": None, "passed": False} for _ in range(5)]
        details_b = [{"task_id": None, "passed": True} for _ in range(5)]
        results = {
            "aitester": _results_with_details(5, 0.0) | {"details": details_a},
            "plain_llm": _results_with_details(5, 1.0) | {"details": details_b},
        }
        sig = analyze_experiment_results(results)["significance"]
        assert sig["status"] == "ok"
        comp = sig["comparisons"][0]
        assert comp["method"] == "welch_t_test"
        assert comp["status"] == "skipped"
        assert "NaN" not in json.dumps(sig)


class TestGenerateComparisonReport:
    """generate_comparison_report 输出"""

    def test_report_contains_rankings_and_significance(self, tmp_path):
        results = {
            "aitester": _results_with_details(8, 0.9),
            "plain_llm": _results_with_details(8, 0.3),
        }
        analysis = analyze_experiment_results(results)
        out = tmp_path / "report.md"
        report = generate_comparison_report(analysis, str(out))

        assert "Success Rate Ranking" in report
        assert "Coverage Ranking" in report
        assert "Significance Test" in report
        assert out.read_text(encoding="utf-8") == report

    def test_report_insufficient_data_noted(self):
        results = {"a": {"passed_count": 0, "total_count": 0}}
        analysis = analyze_experiment_results(results)
        report = generate_comparison_report(analysis)
        assert "Significance Test" in report
        # 非 ok 状态时输出说明而非结果表
        assert "说明" in report


class TestLoadAndAnalyze:
    """load_and_analyze JSON 加载"""

    def test_load_json_file(self, tmp_path):
        results = {"a": _results_with_details(4, 0.5)}
        file = tmp_path / "results.json"
        file.write_text(json.dumps(results), encoding="utf-8")

        analysis = load_and_analyze(str(file))
        assert analysis["baselines"] == ["a"]

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_and_analyze(str(tmp_path / "nope.json"))
