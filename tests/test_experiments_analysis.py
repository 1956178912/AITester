"""
测试实验结果分析模块。
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.experiments.analysis import (
    analyze_experiment_results,
    generate_comparison_report,
    load_and_analyze,
)


class TestAnalyzeExperimentResults:
    """测试 analyze_experiment_results 函数。"""

    def test_empty_results_raises(self):
        """空结果应抛出 ValueError。"""
        with pytest.raises(ValueError, match="实验结果不能为空"):
            analyze_experiment_results({})

    def test_single_baseline(self):
        """单基线分析应正常返回。"""
        results = {
            "baseline_a": {
                "passed_count": 8,
                "total_count": 10,
                "success_rate": 80.0,
                "avg_coverage": 75.5,
                "avg_iterations": 2.3,
            }
        }
        analysis = analyze_experiment_results(results)
        assert "baseline_a" in analysis["comparison"]
        assert analysis["comparison"]["baseline_a"]["success_rate"] == 80.0
        assert len(analysis["rankings"]["success_rate"]) == 1

    def test_multiple_baselines(self):
        """多基线分析应正确排序。"""
        results = {
            "baseline_a": {"success_rate": 90.0, "avg_coverage": 80.0, "avg_iterations": 2.0},
            "baseline_b": {"success_rate": 85.0, "avg_coverage": 75.0, "avg_iterations": 2.5},
            "baseline_c": {"success_rate": 95.0, "avg_coverage": 85.0, "avg_iterations": 1.8},
        }
        analysis = analyze_experiment_results(results)

        # 验证排名正确
        assert analysis["rankings"]["success_rate"][0]["baseline"] == "baseline_c"
        assert analysis["rankings"]["success_rate"][0]["value"] == 95.0
        assert analysis["rankings"]["coverage"][0]["baseline"] == "baseline_c"

    def test_analysis_contains_required_fields(self):
        """分析结果应包含必要字段。"""
        results = {"test": {"success_rate": 50.0, "avg_coverage": 60.0, "avg_iterations": 3.0}}
        analysis = analyze_experiment_results(results)

        assert "baselines" in analysis
        assert "comparison" in analysis
        assert "rankings" in analysis
        assert "significance" in analysis


class TestGenerateComparisonReport:
    """测试报告生成功能。"""

    def test_basic_report_generation(self):
        """基本报告生成。"""
        analysis = {
            "baselines": ["a", "b"],
            "comparison": {
                "a": {"success_rate": 80.0, "coverage": 70.0, "iterations": 2.0},
                "b": {"success_rate": 90.0, "coverage": 85.0, "iterations": 1.5},
            },
            "rankings": {
                "success_rate": [
                    {"rank": 1, "baseline": "b", "value": 90.0},
                    {"rank": 2, "baseline": "a", "value": 80.0},
                ],
                "coverage": [
                    {"rank": 1, "baseline": "b", "value": 85.0},
                    {"rank": 2, "baseline": "a", "value": 70.0},
                ],
            },
        }

        report = generate_comparison_report(analysis)
        assert "# Experiment Comparison Report" in report
        assert "Success Rate Ranking" in report
        assert "Coverage Ranking" in report
        assert "baseline_b" in report or "b" in report

    def test_report_to_file(self):
        """报告可写入文件。"""
        analysis = {
            "baselines": ["test"],
            "comparison": {"test": {"success_rate": 100.0, "coverage": 90.0, "iterations": 1.0}},
            "rankings": {
                "success_rate": [{"rank": 1, "baseline": "test", "value": 100.0}],
                "coverage": [{"rank": 1, "baseline": "test", "value": 90.0}],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_comparison_report(analysis, str(output_path))
            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert "Experiment Comparison Report" in content


class TestLoadAndAnalyze:
    """测试从文件加载结果。"""

    def test_load_and_analyze(self):
        """从 JSON 文件加载并分析。"""
        results = {
            "baseline_x": {"success_rate": 75.0, "avg_coverage": 65.0, "avg_iterations": 2.0},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(results, f)
            f.flush()

            analysis = load_and_analyze(f.name)
            assert "baseline_x" in analysis["comparison"]
            assert analysis["comparison"]["baseline_x"]["success_rate"] == 75.0
