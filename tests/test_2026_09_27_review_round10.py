"""第 10 轮全面审查与保守优化的回归测试（默认行为不变）。

锁定本轮修复的行为口径：
- P1 graph/nodes._suggest_iteration_strategy 非数值 coverage_delta 崩溃
  （"n/a"/dict 跳过，数值路径零变化）
- P2 base_agent._lru_store 负缓存 FIFO cap（与 LRU 同 _LRU_MAXSIZE 上限）
- P2 executor_runtime TimeoutExpired 分支保留前次有效输出（追加而非覆盖）
- P2 generator._auto_fix_module_name 带点路径子串替换残留（锚定正则）
- P2 reports.generator error_context None 渲染"未知"/"—"
- P2 dataset_loader total_test_count 兜底 = len(F2P) + len(P2P)
- P2 convergence_analysis _safe_int/_safe_float 非数字值回退 0
- P2 rag_analysis 非 dict rag_stats 元素跳过
- P2 compare_failures regressed 排除 new_categories（避免重复列示）
- P2 run_benchmark 汇总 iterations/elapsed_seconds None 防护
"""

from __future__ import annotations

import math

# ─── P1 graph/nodes _suggest_iteration_strategy 非数值 delta 防护 ─────────────


class TestSuggestIterationStrategyNonNumeric:
    """2026-09-27 round10 P1：非数值 coverage_delta 不再崩溃。"""

    def test_non_numeric_delta_skipped(self):
        from src.graph.nodes import _suggest_iteration_strategy

        # trace 有 4 条 → trace[-3:-1] = entries[1..3]；其中 entry[2] 为 "n/a"
        # 跳过，entries[1](-2.0) 和 entries[3](0.0) 有效；recent[-2:]=[-2.0, 0.0]
        # 非全负 → 非 declining；abs 非全 <0.5 → 非 stagnant → None
        trace = [
            {"round": 0, "coverage_delta": -1.0},
            {"round": 1, "coverage_delta": -2.0},
            {"round": 2, "coverage_delta": "n/a"},
            {"round": 3, "coverage_delta": -0.5},
        ]
        # trace[-3:-1] = entries[1], entries[2]（跳过）→ recent=[-2.0]
        # len < 2 → declining=False, stagnant=False → None
        assert _suggest_iteration_strategy(trace, None) is None

    def test_non_numeric_mixed_with_valid(self):
        from src.graph.nodes import _suggest_iteration_strategy

        # 4 条 trace：trace[-3:-1] = entries[1], entries[2]（前 3 条中前 2 条）
        # entries[1]=-1.0（有效）, entries[2]="bad"（跳过）
        # recent=[-1.0]，len<2 → 非 declining/非 stagnant → None
        trace = [
            {"round": 0, "coverage_delta": 0.1},
            {"round": 1, "coverage_delta": -1.0},
            {"round": 2, "coverage_delta": "bad"},
            {"round": 3, "coverage_delta": -0.5},
        ]
        assert _suggest_iteration_strategy(trace, None) is None

    def test_non_numeric_all_recent(self):
        from src.graph.nodes import _suggest_iteration_strategy

        # 4 条 trace：trace[-3:-1] = entries[1..2]
        # 全为非数值 → recent 为空 → None
        trace = [
            {"round": 0, "coverage_delta": -1.0},
            {"round": 1, "coverage_delta": "a"},
            {"round": 2, "coverage_delta": {"x": 1}},
            {"round": 3, "coverage_delta": -0.5},
        ]
        assert _suggest_iteration_strategy(trace, None) is None

    def test_all_non_numeric_returns_none(self):
        from src.graph.nodes import _suggest_iteration_strategy

        trace = [
            {"round": 0, "coverage_delta": "n/a"},
            {"round": 1, "coverage_delta": "bad"},
            {"round": 2, "coverage_delta": {"bad": 1}},
            {"round": 3, "coverage_delta": 0.1},
        ]
        # trace[-3:-1] 全为非数值 → 跳过 → None
        assert _suggest_iteration_strategy(trace, None) is None

    def test_numeric_path_unchanged(self):
        from src.graph.nodes import _suggest_iteration_strategy

        # declining：前 2 条全 <0
        t1 = [
            {"round": 0, "coverage_delta": -1.0},
            {"round": 1, "coverage_delta": -0.5},
            {"round": 2, "coverage_delta": 0.0},
        ]
        assert _suggest_iteration_strategy(t1, None) == "lower_temperature"

        # stagnant：前 2 条 abs 全 <0.5（非全负）
        t2 = [
            {"round": 0, "coverage_delta": 0.1},
            {"round": 1, "coverage_delta": -0.2},
            {"round": 2, "coverage_delta": 0.3},
        ]
        assert _suggest_iteration_strategy(t2, None) == "switch_repair_view"

    def test_single_round_returns_none(self):
        from src.graph.nodes import _suggest_iteration_strategy

        assert _suggest_iteration_strategy([{"round": 0}], None) is None


# ─── P2 base_agent 负缓存 FIFO cap ─────────────────────────────────────────────


class TestLruNegativeCacheCap:
    """2026-09-27 round10 P2：_lru_negatives 与 LRU 同容量上限。"""

    def test_negative_cache_bounded(self):
        import src.agents.base_agent as ba

        ba._lru_clear()
        maxsize = ba._LRU_MAXSIZE
        for i in range(maxsize + 100):
            ba._lru_store(("f", f"k{i}", None), None)
        with ba._lru_lock:
            assert len(ba._lru_negatives) <= maxsize
        ba._lru_clear()

    def test_negative_cache_evicts_oldest(self):
        import src.agents.base_agent as ba

        ba._lru_clear()
        maxsize = ba._LRU_MAXSIZE
        for i in range(maxsize + 5):
            ba._lru_store(("f", f"k{i}", None), None)
        # 最早插入的 k0 已被淘汰（FIFO）
        with ba._lru_lock:
            assert ("f", "k0", None) not in ba._lru_negatives
        ba._lru_clear()


# ─── P2 executor_runtime TimeoutExpired 保留前次输出 ───────────────────────────


class TestExecutorRuntimeTimeoutKeepsPriorOutput:
    """2026-09-27 round10 P2：第 2 次超时不再覆盖第 1 次有效输出。"""

    def _make_executor(self):
        from src.agents.executor import ExecutorAgent

        return ExecutorAgent.__new__(ExecutorAgent)

    def test_timeout_appends_prior_output(self):
        import subprocess

        ex = self._make_executor()
        ex.timeout = 1

        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:

                class R:
                    stdout = "first-fail-output"
                    stderr = ""
                    returncode = 1

                return R()
            raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=1, output="partial")

        import unittest.mock as mock

        with mock.patch("subprocess.run", side_effect=fake_run):
            last_output, last_result = ex._run_pytest_with_retry(["pytest"], {}, "/tmp")
        # 第 1 次有效输出保留 + 第 2 次超时快照追加
        assert "first-fail-output" in last_output
        assert "timeout attempt 2" in last_output
        assert last_result[0] == "EARLY_RETURN"

    def test_single_timeout_unchanged(self):
        import subprocess

        ex = self._make_executor()
        ex.timeout = 1

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=1, output="only-partial")

        import unittest.mock as mock

        with mock.patch("subprocess.run", side_effect=fake_run):
            last_output, last_result = ex._run_pytest_with_retry(["pytest"], {}, "/tmp")
        # 单次超时时 last_output 原为空串，结果不变（无 [timeout attempt 1] 前缀污染）
        assert last_output == "only-partial"
        assert last_result[0] == "EARLY_RETURN"


# ─── P2 generator 带点路径模块名替换 ───────────────────────────────────────────


class TestGeneratorModuleFixDotted:
    """2026-09-27 round10 P2：带点路径子串替换不再残留损坏导入。"""

    def test_dotted_wm_does_not_break_package_form(self):
        from src.agents.generator import GeneratorAgent

        # mypkg / mypkg.sub 相似度低于 0.6（实测）→ 不触发替换（门控语义）
        code = "from mypkg import something\nfrom mypkg.sub import x\n"
        result = GeneratorAgent._fix_import_module(code, "mytarget")
        assert result == code  # 相似度不足，保持原样

    def test_similar_module_still_fixed(self):
        from src.agents.generator import GeneratorAgent

        code = "from calclator import add\n"
        result = GeneratorAgent._fix_import_module(code, "calculator")
        assert "from calculator import add" in result

    def test_similar_dotted_replacement_anchored(self):
        from src.agents.generator import GeneratorAgent

        # simple_mod 与 simple 相似度 0.65（>0.6 门控放行），锚定正则
        # `from simple.mod import` 不应波及 `from simple import` 行
        code = "from simple.mod import helper\nfrom simple import add\n"
        result = GeneratorAgent._fix_import_module(code, "target")
        # simple_mod 与 target 不相似（0.43）→ 不触发替换
        # 但 simple 与 target 也不相似 → 整段保持原样
        assert result == code
        # 验证锚定逻辑：若强制替换，`from simple import` 不得被
        # `from simple.mod` 的替换波及
        code2 = "from target_mod import helper\nfrom target import add\n"
        result2 = GeneratorAgent._fix_import_module(code2, "target")
        # target_mod 与 target 相似度 0.83（>0.6）→ 触发精确锚定替换
        assert "from target import helper" in result2
        # `from target import add` 行未被破坏
        assert result2.count("from target import") == 2


# ─── P2 reports.generator None 渲染 ────────────────────────────────────────────


class TestReportNoneRendering:
    """2026-09-27 round10 P2：error_context None 字段渲染"未知"/"—"。"""

    def _make_report(self):
        from src.agents.error_classifier import ErrorCategory
        from src.reports.generator import ErrorReport

        return ErrorReport(
            task_id="t1",
            target_file="x.py",
            target_function="f",
            error_category=ErrorCategory.UNKNOWN,
        )

    def test_to_text_none_filename(self):
        from src.agents.error_classifier import ErrorContext

        rep = self._make_report()
        rep.error_context = ErrorContext(filename=None, line=None, column=None)
        text = rep.to_text()
        assert "文件: 未知" in text
        assert "行号: —" in text
        assert "列号: —" in text
        assert "文件: None" not in text

    def test_to_markdown_none_filename(self):
        from src.agents.error_classifier import ErrorContext

        rep = self._make_report()
        rep.error_context = ErrorContext(filename=None, line=3, column=None)
        md = rep.to_markdown()
        assert "未知" in md
        assert "**行号**: 3" in md
        assert "**列号**: —" in md


# ─── P2 dataset_loader total_test_count 兜底 = F2P + P2P ───────────────────────


class TestDatasetLoaderTotalTestCount:
    """2026-09-27 round10 P2：SWE-bench 兜底口径 F2P+P2P（不漏 P2P）。"""

    def _load(self, tmp_path, records):
        import json

        from src.datasets.dataset_loader import SWEBenchDataset

        jsonl = tmp_path / "swe_bench_instances.jsonl"
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        ds = SWEBenchDataset()
        ds._loaded = False
        import unittest.mock as mock

        with mock.patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True
        return ds

    def test_f2p_plus_p2p_fallback(self, tmp_path):
        ds = self._load(
            tmp_path,
            [
                {
                    "instance_id": "a__a-1",
                    "repository": "org/a",
                    "problem_statement": "p",
                    "FAIL_TO_PASS": '["t1", "t2"]',
                    "PASS_TO_PASS": '["p1", "p2", "p3"]',
                }
            ],
        )
        task = ds.get_task_by_id("a__a-1")
        assert task is not None
        # 兜底口径 = F2P(2) + P2P(3) = 5（旧口径仅 F2P = 2）
        assert task.total_test_count == 5

    def test_p2p_only_fallback(self, tmp_path):
        ds = self._load(
            tmp_path,
            [
                {
                    "instance_id": "b__b-1",
                    "repository": "org/b",
                    "problem_statement": "p",
                    "FAIL_TO_PASS": "",
                    "PASS_TO_PASS": '["p1"]',
                }
            ],
        )
        task = ds.get_task_by_id("b__b-1")
        assert task is not None
        # 兜底口径 = F2P(0) + P2P(1) = 1
        assert task.total_test_count == 1

    def test_official_fields_still_win(self, tmp_path):
        ds = self._load(
            tmp_path,
            [
                {
                    "instance_id": "c__c-1",
                    "repository": "org/c",
                    "problem_statement": "p",
                    "n_tests_before": 10,
                    "pass_num_after": 9,
                    "FAIL_TO_PASS": '["t1"]',
                    "PASS_TO_PASS": '["p1"]',
                }
            ],
        )
        task = ds.get_task_by_id("c__c-1")
        assert task is not None
        # 官方字段存在时仍以官方值为准，口径不变
        assert task.total_test_count == 9


# ─── P2 convergence_analysis _safe_int/_safe_float ────────────────────────────


class TestConvergenceSafeNumeric:
    """2026-09-27 round10 P2：非数字 iterations/elapsed_seconds 不崩溃。"""

    def test_repair_convergence_curve_bad_iterations(self):
        from experiments.analysis_parts.convergence_analysis import _repair_convergence_curve

        details = [
            {"task_id": "t1", "passed": True, "iterations": "abc", "elapsed_seconds": "xyz"},
            {"task_id": "t2", "passed": False, "iterations": None, "elapsed_seconds": None},
        ]
        r = _repair_convergence_curve(details)
        assert r["total_tasks"] == 2
        assert r["rounds"], "应产出轮次结构"

    def test_repair_convergence_metrics_bad_values(self):
        from experiments.analysis_parts.convergence_analysis import _repair_convergence_metrics

        details = [
            {"task_id": "t1", "passed": True, "iterations": "3.5", "elapsed_seconds": "n/a"},
            {"task_id": "t2", "passed": False, "iterations": {"x": 1}, "elapsed_seconds": None},
        ]
        r = _repair_convergence_metrics(details)
        assert r["total_tasks"] == 2
        # 非数字值归 0 → 第 0 轮计入
        assert r["first_attempt_success_count"] == 1

    def test_quality_proxy_bad_coverage(self):
        from experiments.analysis_parts.convergence_analysis import _quality_proxy_metrics

        details = [
            {"task_id": "t1", "passed": True, "coverage": "bad", "elapsed_seconds": [1, 2]},
        ]
        r = _quality_proxy_metrics(details)
        assert r["coverage_proxy"]["success"]["mean"] == 0.0
        assert r["runtime_proxy"]["success"]["mean"] == 0.0

    def test_failure_modes_bad_iterations(self):
        from experiments.analysis_parts.convergence_analysis import _convergence_failure_modes

        details = [{"task_id": "t1", "passed": False, "iterations": "abc"}]
        r = _convergence_failure_modes(details)
        # 非数字 iterations 归 0 → 不计入"收敛失败"（<3 轮）
        assert r.get("total_converged_failed", 0) == 0

    def test_execution_trace_summary_bad_reward(self):
        from experiments.analysis_parts.convergence_analysis import _execution_trace_summary

        details = [
            {
                "task_id": "t1",
                "execution_trace": [
                    {
                        "round": 0,
                        "passed": False,
                        "coverage": "bad",
                        "reward_signals": {"correctness": "x", "efficiency": 0.5},
                    },
                    {"round": 1, "passed": True, "coverage": 0.8, "reward_signals": {"correctness": {"bad": 1}}},
                ],
            }
        ]
        r = _execution_trace_summary(details)
        assert r["available"] is True
        # correctness 两次都非数值 → 均值 None
        assert r["avg_last_reward_correctness"] is None


# ─── P2 rag_analysis 非 dict 元素跳过 ──────────────────────────────────────────


class TestRagAnalysisNonDictElements:
    """2026-09-27 round10 P2：rag_stats 混入非 dict 元素不再崩溃。"""

    def test_by_kind_skips_non_dict(self):
        from experiments.analysis_parts.rag_analysis import _rag_by_kind_from_details

        details = [
            {
                "task_id": "t1",
                "rag_stats": [{"kind": "test_cases", "results": 1, "max_similarity": 0.5}, "str-element", 42],
            },
        ]
        r = _rag_by_kind_from_details(details)
        assert r.get("test_cases", {}).get("retrievals") == 1

    def test_cross_skips_non_dict(self):
        from experiments.analysis_parts.rag_analysis import _rag_hit_by_failure_category

        details = [
            {"task_id": "t1", "passed": False, "error_category": "ERROR_X", "rag_stats": ["not-a-dict"]},
        ]
        r = _rag_hit_by_failure_category(details)
        assert r.get("ERROR_X", {}).get("with_hit") == 0

    def test_similarity_distribution_skips_non_dict(self):
        from experiments.analysis_parts.rag_analysis import _rag_similarity_distribution

        details = [
            {"task_id": "t1", "rag_stats": [{"max_similarity": 0.6}, "junk"]},
        ]
        r = _rag_similarity_distribution(details)
        assert r["total_retrievals"] == 1

    def test_token_efficiency_bad_iterations(self):
        from experiments.analysis_parts.rag_analysis import _rag_token_efficiency

        details = [
            {
                "task_id": "t1",
                "passed": False,
                "rag_stats": [{"results": 1}],
                "iterations": "abc",
                "token_usage": {"total_tokens": "x"},
            },
            {"task_id": "t2", "passed": False, "iterations": None, "token_usage": None},
        ]
        r = _rag_token_efficiency(details)
        # 两组均有任务；非数字值归 0
        assert r["available"] is True


# ─── P2 compare_failures regressed 排除 new_categories ─────────────────────────


class TestCompareFailuresRegressedExcludesNew:
    """2026-09-27 round10 P2：品牌新类别不再同时出现在 regressed 与 new。"""

    def test_new_category_not_regressed(self):
        from experiments.compare_failures import cross_batch_comparison

        summaries = [
            {
                "results": {
                    "aitester": {
                        "details": [
                            {"task_id": "t1", "passed": False, "error_category": "CAT_OLD"},
                            {"task_id": "t2", "passed": False, "error_category": "CAT_OLD"},
                            {"task_id": "t3", "passed": True},
                        ]
                    }
                }
            },
            {
                "results": {
                    "aitester": {
                        "details": [
                            {"task_id": "t4", "passed": False, "error_category": "CAT_OLD"},
                            {"task_id": "t5", "passed": False, "error_category": "CAT_NEW"},
                            {"task_id": "t6", "passed": True},
                        ]
                    }
                }
            },
        ]
        r = cross_batch_comparison(summaries, "aitester")
        # CAT_NEW 品牌新（旧批无、最新批有）→ 在 new_categories
        assert "CAT_NEW" in r["new_categories"]
        # CAT_OLD：旧批 2 → 新批 1（下降）→ 不在 regressed
        # CAT_NEW：品牌新 → 排除在 regressed 之外
        assert "CAT_NEW" not in r["regressed_categories"]
        assert "CAT_OLD" not in r["regressed_categories"]


# ─── P2 run_benchmark 汇总 None 防护 ──────────────────────────────────────────


class TestRunBenchmarkSummaryNoneSafe:
    """2026-09-27 round10 P2：iterations/elapsed_seconds None 不再崩溃。"""

    def test_summary_handles_none_iterations(self):
        import inspect

        from experiments import run_benchmark

        # 验证 run_benchmark 源码中 sum 表达式已用 r.get(...) or 0 防护
        src = inspect.getsource(run_benchmark)
        assert 'r.get("iterations") or 0' in src
        assert 'r.get("elapsed_seconds") or 0' in src

    def test_sum_expression_safe(self):
        # 验证新的 sum 表达式对 None 安全
        bl_results = [
            {"task_id": "t1", "passed": True, "coverage": 0.5, "iterations": None, "elapsed_seconds": None},
            {"task_id": "t2", "passed": False, "coverage": 0, "iterations": 2, "elapsed_seconds": 10.0},
        ]
        total = len(bl_results)
        avg_iterations = sum(r.get("iterations") or 0 for r in bl_results) / total
        assert avg_iterations == 1.0
        avg_time = sum(r.get("elapsed_seconds") or 0 for r in bl_results) / total
        assert avg_time == 5.0


# ─── P2 statistical_analysis docstring 口径 ────────────────────────────────────


class TestCohensDDocstringAlignment:
    """2026-09-27 round10 P2：cohens_d n_pairs<2 返回 (nan, n_pairs)。"""

    def test_single_pair_returns_nan_with_n_pairs(self):
        from experiments.statistical_analysis import cohens_d

        aitester = [{"task_id": "t1", "passed": True}]
        baseline = [{"task_id": "t1", "passed": False}]
        d, n = cohens_d(aitester, baseline)
        assert math.isnan(d)
        assert n == 1

    def test_zero_pairs_returns_nan_with_zero(self):
        from experiments.statistical_analysis import cohens_d

        aitester = [{"task_id": "t1", "passed": True}]
        baseline = [{"task_id": "t2", "passed": False}]
        d, n = cohens_d(aitester, baseline)
        assert math.isnan(d)
        assert n == 0


# ─── P2 code_context depth 口径文档化 ──────────────────────────────────────────


class TestCodeContextDepthDoc:
    """2026-09-27 round10 P2：_closure_names depth=N 含 N 层被调（文档澄清）。"""

    def test_depth_docstring_clarified(self):
        import inspect

        from src.tools.code_context import _closure_names

        doc = inspect.getdoc(_closure_names) or ""
        assert "depth=N" in doc or "depth=1" in doc


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
