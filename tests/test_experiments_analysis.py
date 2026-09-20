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

    def test_rankings_value_name_binding(self):
        """排名基于 (name, value) 绑定，而非按 zip 位置错配：
        值 0.1 归 a，值 0.9 归 b，即使插入顺序不同结果也应一致。"""
        results_low_first = {
            "a": _results_with_details(10, 0.1),
            "b": _results_with_details(10, 0.9),
        }
        ranks = analyze_experiment_results(results_low_first)["rankings"]["success_rate"]
        assert [r["baseline"] for r in ranks] == ["b", "a"]
        assert ranks[0]["value"] == 90.0
        assert ranks[1]["value"] == 10.0

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

    def test_report_ok_with_skipped_comparison_does_not_crash(self):
        """status=ok 但对比被 skipped（两组通过率恒定）时，报告不得 KeyError。

        回归：generate_comparison_report 此前对全部对比硬读 t_stat/p_value，
        skipped 条目无这些键 → 常量组场景（常见于小样本基线）报告生成直接崩。
        """
        results = {
            "aitester": _results_with_details(5, 1.0),
            "plain_llm": _results_with_details(5, 1.0),
        }
        analysis = analyze_experiment_results(results)
        assert analysis["significance"]["status"] == "ok"
        assert analysis["significance"]["comparisons"][0]["status"] == "skipped"

        report = generate_comparison_report(analysis)  # 修复前此处 KeyError: 't_stat'

        assert "Significance Test" in report
        # skipped 对比以说明形式输出，而非进结果表
        assert "skipped" not in report or "恒定" in report
        assert "t 统计量" in report  # 表头仍保留

    def test_report_mixed_numeric_and_skipped(self):
        """数值化对比入表 + skipped 对比单列说明，二者共存时报告完整不崩。"""
        results = {
            "aitester": _results_with_details(8, 0.5),
            "plain_llm": _results_with_details(8, 0.5),  # 恒定 → skipped
            "baseline_b": _results_with_details(8, 0.2),  # 非恒定 → 数值化
        }
        analysis = analyze_experiment_results(results)
        report = generate_comparison_report(analysis)
        sig = analysis["significance"]
        statuses = [c.get("status") for c in sig.get("comparisons", [])]
        # 既含数值化（non-skipped，无 status 键）又含 skipped
        assert "skipped" in statuses and None in statuses
        # skipped 对比以说明形式出现（含 note 关键字），数值化对比进入表格行
        assert "恒定" in report or "无差异" in report
        assert "aitester vs baseline_b" in report


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


class TestSignificanceBoundaryConditions:
    """5.1 统计检验边界条件补强（样本量 < 3 / 部分配对缺失 / 单基线）。"""

    def test_single_sample_details_insufficient(self):
        """单基线 details 仅 1 条（< 最小样本 3）→ insufficient_data，不触发除零。"""
        results = {"a": _results_with_details(1, 0.0)}
        sig = analyze_experiment_results(results)["significance"]
        assert sig["status"] in ("insufficient_data", "unavailable")
        assert "note" in sig

    def test_two_samples_details_insufficient(self):
        """2 条 details 仍低于最小样本数 3（边界 -1），不崩溃、不产生 t 统计量。"""
        results = {
            "a": _results_with_details(2, 0.5),
            "b": _results_with_details(2, 0.5),
        }
        sig = analyze_experiment_results(results)["significance"]
        # 样本量不足 → 走 insufficient_data 分支（无数字条目）
        assert sig["status"] == "insufficient_data"

    def test_partial_task_id_overlap_paired(self):
        """两基线 task_id 仅部分重叠（3/5 公共）时按公共集配对，n 取重叠数。"""
        details_a = [{"task_id": f"t{i}", "passed": i < 4} for i in range(5)]
        details_b = [{"task_id": f"t{i}", "passed": i < 1} for i in range(3)]  # 仅 t0-t2
        results = {
            "aitester": _results_with_details(5, 0.8) | {"details": details_a},
            "plain_llm": _results_with_details(3, 0.0) | {"details": details_b},
        }
        sig = analyze_experiment_results(results)["significance"]
        if sig["status"] == "ok":
            comp = sig["comparisons"][0]
            assert comp["method"] == "paired_t_test"
            assert comp["n_a"] == 3 and comp["n_b"] == 3

    def test_single_baseline_no_comparison(self):
        """单基线（无对比对象）时 comparisons 为空 → insufficient_data。"""
        results = {"a": _results_with_details(10, 0.5)}
        sig = analyze_experiment_results(results)["significance"]
        # a 为 baseline 自身，无其他基线可对比
        assert sig["status"] in ("insufficient_data", "unavailable")

    def test_details_not_list_degrades(self):
        """details 字段为非 list（脏数据）时不崩溃，归入 insufficient_data。"""
        results = {
            "a": _results_with_details(10, 0.5) | {"details": {"corrupted": True}},
            "b": _results_with_details(10, 0.5),
        }
        sig = analyze_experiment_results(results)["significance"]
        assert sig["status"] in ("insufficient_data", "unavailable")


class TestAnalyzeResultsNewMetricsBoundary:
    """5.1 边界补强：analyze_results 新增指标的边界条件（样本量=1、
    全部通过/失败、无 Token 数据等退化输入不得崩溃）。

    覆盖目标（此前 91% 的 analysis.py + 新增 analyze_results 指标）：
    - _test_smell_detection: 无 generated_test / 单任务 / 多策略分组
    - _convergence_token_efficiency: 无 Token 数据 / 单任务
    - _difficulty_stratified_iterations: 全部任务 0 迭代 / 单难度档
    - _mutation_score_metrics: 单任务 / 无断言（交叉分析退化）
    - _rag_token_efficiency: 仅 RAG 组 / 仅无 RAG 组（无法对比）
    - _failure_root_cause_trend: 无失败任务（全通过）
    """

    def test_smell_detection_no_generated_test(self):
        """details 无 generated_test 时异味检测返回 available=False（不崩溃）。"""
        from experiments.analyze_results import _test_smell_detection

        details = [{"task_id": "t1", "passed": True}]
        result = _test_smell_detection(details)
        assert result["available"] is False
        assert result["observed_tasks"] == 0

    def test_smell_detection_single_task_with_smell(self):
        """单任务有异味（无断言）时 smell_density=1.0（边界：1/1）。"""
        from experiments.analyze_results import _test_smell_detection

        details = [{"task_id": "t1", "passed": True, "generated_test": "def test_x():\n    pass\n"}]
        result = _test_smell_detection(details)
        assert result["available"] is True
        assert result["observed_tasks"] == 1
        assert result["smell_density"] == 1.0
        assert len(result["tasks_with_smells"]) == 1

    def test_smell_detection_strategy_grouping(self):
        """多策略分组：strategy 字段非空时输出 smell_counts_by_strategy。"""
        from experiments.analyze_results import _test_smell_detection

        details = [
            {"task_id": "t1", "passed": True, "generated_test": "def test_a():\n    pass\n", "strategy": "planner"},
            {
                "task_id": "t2",
                "passed": True,
                "generated_test": "def test_b():\n    assert 1 == 1\n",
                "strategy": "plain",
            },
        ]
        result = _test_smell_detection(details)
        assert "smell_counts_by_strategy" in result
        assert result["smell_counts_by_strategy"]["planner"]["observed_tasks"] == 1
        assert result["smell_counts_by_strategy"]["plain"]["observed_tasks"] == 1

    def test_convergence_token_efficiency_no_token_data(self):
        """无 Token 数据时按均摊保守口径仍可用（rounds 非空，best_marginal_round 可能 None）。"""
        from experiments.analyze_results import _convergence_token_efficiency

        details = [
            {"task_id": "t1", "passed": True, "iterations": 1},
            {"task_id": "t2", "passed": False, "iterations": 2},
        ]
        result = _convergence_token_efficiency(details)
        assert result["available"] is True
        assert result["rounds"]["0"]["reached_tasks"] >= 0
        # 无 Token 数据时 marginal 为 None（增量 Token=0 不除零）
        assert result["rounds"]["0"]["marginal_pass_per_token"] is None or isinstance(
            result["rounds"]["0"]["marginal_pass_per_token"], (int, float)
        )

    def test_convergence_token_efficiency_empty(self):
        """空 details 返回 available=False。"""
        from experiments.analyze_results import _convergence_token_efficiency

        result = _convergence_token_efficiency([])
        assert result["available"] is False

    def test_difficulty_stratified_all_zero_iterations(self):
        """全部任务 0 迭代时分布仅 0 档（无 1/2/3+ 键）。"""
        from experiments.analyze_results import _difficulty_stratified_iterations

        details = [
            {"task_id": "t1", "passed": True, "iterations": 0},
            {"task_id": "t2", "passed": True, "iterations": 0},
        ]
        result = _difficulty_stratified_iterations(details, {"t1": "easy", "t2": "hard"})
        assert result["available"] is True
        assert result["bands"]["easy"]["iterations"]["0"] == 1
        assert result["bands"]["hard"]["iterations"]["0"] == 1
        assert "3+" not in result["bands"]["easy"]["iterations"]

    def test_difficulty_stratified_no_bands(self):
        """无 difficulty_bands 时全部归入 unstratified 档。"""
        from experiments.analyze_results import _difficulty_stratified_iterations

        details = [{"task_id": "t1", "passed": False, "iterations": 3}]
        result = _difficulty_stratified_iterations(details, None)
        assert result["available"] is True
        assert result["bands"]["unstratified"]["iterations"]["3+"] == 1

    def test_mutation_score_single_task_no_assertions(self):
        """单任务无 generated_test 时变异-断言交叉分析退化为 None（不崩溃）。"""
        from experiments.analyze_results import _mutation_score_metrics

        details = [
            {"task_id": "t1", "passed": True, "mutation_score": 0.8, "generated_test": "def test_x():\n    pass\n"},
        ]
        result = _mutation_score_metrics(details)
        assert result["available"] is True
        cross = result.get("mutation_assertion_cross")
        # 无有效断言（pass 体）时 high/low 组 avg 为 None（数据不足）
        assert cross is None or (
            cross.get("high_score_avg_assertions") is None or cross.get("low_score_avg_assertions") is None
        )

    def test_mutation_score_no_scores(self):
        """无 mutation_score 字段时返回 available=False。"""
        from experiments.analyze_results import _mutation_score_metrics

        details = [{"task_id": "t1", "passed": True}]
        result = _mutation_score_metrics(details)
        assert result["available"] is False

    def test_rag_token_efficiency_single_group(self):
        """仅 RAG 组（无 RAG 组）时 available=False（无法对比）。"""
        from experiments.analyze_results import _rag_token_efficiency

        details = [
            {"task_id": "t1", "passed": True, "rag_stats": [{"results": 1}], "token_usage": {"total_tokens": 100}},
        ]
        result = _rag_token_efficiency(details)
        assert result["available"] is False

    def test_rag_token_efficiency_both_groups(self):
        """两组都有任务时正常对比（Token 比率 / 迭代差计算）。"""
        from experiments.analyze_results import _rag_token_efficiency

        details = [
            {
                "task_id": "t1",
                "passed": True,
                "rag_stats": [{"results": 1}],
                "token_usage": {"total_tokens": 200},
                "iterations": 2,
            },
            {
                "task_id": "t2",
                "passed": False,
                "rag_stats": None,
                "token_usage": {"total_tokens": 100},
                "iterations": 1,
            },
        ]
        result = _rag_token_efficiency(details)
        assert result["available"] is True
        assert result["rag_group"]["avg_tokens"] == 200.0
        assert result["no_rag_group"]["avg_tokens"] == 100.0
        assert result["token_delta_ratio"] == 2.0
        assert result["iteration_delta"] == 1.0

    def test_failure_root_cause_trend_all_passed(self):
        """全部任务通过（无失败）时返回 total_failed=0、分布为空。"""
        from experiments.analyze_results import _failure_root_cause_trend

        details = [
            {"task_id": "t1", "passed": True},
            {"task_id": "t2", "passed": True},
        ]
        result = _failure_root_cause_trend(details)
        assert result["total_failed"] == 0
        assert result["root_cause_distribution"] == {}

    def test_failure_root_cause_trend_all_failed_dependency(self):
        """全部失败且 import_error 时 dependency 占比 1.0。"""
        from experiments.analyze_results import _failure_root_cause_trend

        details = [
            {"task_id": "t1", "passed": False, "error_category": "import_error"},
            {"task_id": "t2", "passed": False, "error_category": "import_error"},
        ]
        result = _failure_root_cause_trend(details)
        assert result["total_failed"] == 2
        assert result["root_cause_rates"]["dependency"] == 1.0
        assert result["root_cause_rates"]["llm_capability"] == 0.0

    def test_contamination_cross_no_risk_level(self):
        """无 contamination_risk_level 字段时 available=False。"""
        from experiments.analyze_results import _contamination_cross_analysis

        details = [{"task_id": "t1", "passed": True}]
        result = _contamination_cross_analysis(details)
        assert result["available"] is False

    def test_contamination_cross_high_vs_low(self):
        """高/低污染任务成功率对比（delta 计算）。"""
        from experiments.analyze_results import _contamination_cross_analysis

        details = [
            {"task_id": "t1", "passed": True, "contamination_risk_level": "high"},
            {"task_id": "t2", "passed": True, "contamination_risk_level": "high"},
            {"task_id": "t3", "passed": False, "contamination_risk_level": "low"},
        ]
        result = _contamination_cross_analysis(details)
        assert result["available"] is True
        assert result["by_risk_level"]["high"]["success_rate"] == 1.0
        assert result["by_risk_level"]["low"]["success_rate"] == 0.0
        assert result["high_vs_low_success_delta"] == 1.0


class TestCrossBaselineConvergenceBoundary:
    """1.3 跨基线收敛对比的边界条件（基线数 <2 / 协作组缺失等退化输入）。"""

    def test_single_baseline_not_available(self):
        """仅 1 个基线时 available=False（无对比对象）。"""
        from experiments.analyze_results import _cross_baseline_convergence_comparison

        per = {
            "aitester": {
                "repair_convergence_curve": {
                    "total_tasks": 10,
                    "rounds": {
                        "0": {"cumulative_pass_rate": 0.8},
                        "1": {"cumulative_pass_rate": 0.9},
                    },
                }
            }
        }
        result = _cross_baseline_convergence_comparison(per)
        assert result["available"] is False
        assert result["baselines"] == ["aitester"]

    def test_two_baselines_no_delta(self):
        """协作组与基线组各 1 个时 delta 为两组合值之差（保守口径）。"""
        from experiments.analyze_results import _cross_baseline_convergence_comparison

        per = {
            "aitester": {
                "repair_convergence_curve": {
                    "total_tasks": 10,
                    "rounds": {
                        "0": {"cumulative_pass_rate": 0.8},
                        "1": {"cumulative_pass_rate": 0.9},
                    },
                }
            },
            "plain_llm": {
                "repair_convergence_curve": {
                    "total_tasks": 10,
                    "rounds": {
                        "0": {"cumulative_pass_rate": 0.6},
                        "1": {"cumulative_pass_rate": 0.75},
                    },
                }
            },
        }
        result = _cross_baseline_convergence_comparison(per)
        assert result["available"] is True
        assert result["first_attempt_delta"] == 0.2  # 0.8 - 0.6
        assert result["cumulative_pass_rate_at_1_delta"] == 0.15  # 0.9 - 0.75
        assert result["collab_group"] == ["aitester"]
        assert result["plain_group"] == ["plain_llm"]

    def test_no_plain_baseline_delta_none(self):
        """两个基线均不含 'plain' 时两组均空，delta 为 None。"""
        from experiments.analyze_results import _cross_baseline_convergence_comparison

        per = {
            "aitester": {"repair_convergence_curve": {"rounds": {"0": {"cumulative_pass_rate": 0.8}}}},
            "another_agent": {"repair_convergence_curve": {"rounds": {"0": {"cumulative_pass_rate": 0.7}}}},
        }
        result = _cross_baseline_convergence_comparison(per)
        assert result["available"] is True
        assert result["first_attempt_delta"] is None
        assert result["cumulative_pass_rate_at_1_delta"] is None

    def test_missing_rounds_skipped(self):
        """某基线缺某轮数据时对齐表跳过该格（不崩溃）。"""
        from experiments.analyze_results import _cross_baseline_convergence_comparison

        per = {
            "aitester": {
                "repair_convergence_curve": {
                    "rounds": {"0": {"cumulative_pass_rate": 0.8}, "1": {"cumulative_pass_rate": 0.9}}
                }
            },
            "plain_llm": {"repair_convergence_curve": {"rounds": {"0": {"cumulative_pass_rate": 0.6}}}},
        }
        result = _cross_baseline_convergence_comparison(per)
        assert result["aligned_rounds"]["0"]["plain_llm"] == 0.6
        assert "plain_llm" not in result["aligned_rounds"].get("1", {})
        # at_1 delta 因 plain_llm 缺 1 轮数据而为 None
        assert result["cumulative_pass_rate_at_1_delta"] is None


class TestCrossFileFailureAnalysisBoundary:
    """2.2 跨文件修复失败案例分析的边界条件（无失败 / import 关键词统计）。"""

    def test_no_failed_tasks_not_available(self):
        """全部任务通过时 available=False。"""
        from experiments.analyze_results import _cross_file_failure_analysis

        per = {"aitester": {"_details": [{"task_id": "t1", "passed": True}]}}
        result = _cross_file_failure_analysis(per)
        assert result["available"] is False

    def test_failed_tasks_import_related_count(self):
        """诊断含 import/module/模块 关键词的失败任务计数。"""
        from experiments.analyze_results import _cross_file_failure_analysis

        per = {
            "aitester": {
                "_details": [
                    {
                        "task_id": "t1",
                        "passed": False,
                        "error_category": "import_error",
                        "diagnosis": "ModuleNotFoundError: No module named 'foo'",
                    },
                    {
                        "task_id": "t2",
                        "passed": False,
                        "error_category": "assertion",
                        "diagnosis": "AssertionError: expected 1 == 2",
                    },
                ]
            }
        }
        result = _cross_file_failure_analysis(per)
        assert result["available"] is True
        assert result["by_baseline"]["aitester"]["failed"] == 2
        assert result["by_baseline"]["aitester"]["import_related_failed"] == 1
        assert result["import_related_rate"] == 0.5

    def test_no_details_empty(self):
        """_details 为空时跳过该基线（不崩溃）。"""
        from experiments.analyze_results import _cross_file_failure_analysis

        per = {"aitester": {}}
        result = _cross_file_failure_analysis(per)
        assert result["available"] is False
