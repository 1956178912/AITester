"""第 9 轮全面审查与保守优化的回归测试（默认行为不变）。

锁定本轮修复的行为口径：
- P1 变异测试模块名对齐（_infer_imported_module_name + _run_mutant_tests）
- P2 统计口径（cohens_d 零方差、t 检验 isfinite 守卫、interpret_d inf/nan）
- P2 收敛 Token 均摊（无逐轮明细时 total 只计入最终轮一次，无负增量）
- P2 死代码清理（compare_failures all_categories、_remove_not_op）
- P2 健壮性（contamination task_id 去重、iterations null 防护、
  mutation_score float 防护、visualize None 对角线）
- P2 口径文档化（statistical_analysis synthetic 过滤注释）
"""

from __future__ import annotations

import math

# ─── P1 变异测试模块名对齐 ──────────────────────────────────────────────────


class TestMutationModuleNameAlignment:
    """2026-09-26 round9 P1：_run_mutant_tests 沙箱模块名与测试 import 名对齐。"""

    def test_infer_from_import_statement(self):
        from experiments.mutation_testing import _infer_imported_module_name

        test_code = "from mymodule import calc\n\ndef test_x():\n    assert calc() == 1\n"
        assert _infer_imported_module_name(test_code) == "mymodule"

    def test_infer_plain_import_statement(self):
        from experiments.mutation_testing import _infer_imported_module_name

        test_code = "import mymodule\n\ndef test_x():\n    assert mymodule.calc() == 1\n"
        assert _infer_imported_module_name(test_code) == "mymodule"

    def test_infer_skips_stdlib_first(self):
        from experiments.mutation_testing import _infer_imported_module_name

        test_code = "import os\nfrom mymodule import calc\n\ndef test_x():\n    assert calc() == 1\n"
        assert _infer_imported_module_name(test_code) == "mymodule"

    def test_infer_fallback_when_no_import(self):
        from experiments.mutation_testing import _infer_imported_module_name

        assert _infer_imported_module_name("") == "mutated_module"
        assert _infer_imported_module_name("def test_x():\n    pass\n") == "mutated_module"

    def test_infer_dotted_module_takes_top_level(self):
        from experiments.mutation_testing import _infer_imported_module_name

        test_code = "from mypkg.mymod import calc\n"
        assert _infer_imported_module_name(test_code) == "mypkg"

    def test_run_mutant_tests_writes_inferred_module_name(self):
        """_run_mutant_tests 缺省 module_name 时写盘为 <inferred>.py。"""
        from experiments.mutation_testing import MutationGenerator, _run_mutant_tests

        source = "def check(x):\n    return x > 3\n"
        gen = MutationGenerator()
        mutants = [m for m in gen.generate(source) if m.mutant_type == "boundary_shift"]
        assert mutants, "应生成 boundary_shift 变异体"
        mutant = mutants[0]

        test_code = "from mymod import check\n\ndef test_basic():\n    assert check(5) == True\n"
        # 弱测试不覆盖 3 边界 → 变异体存活（保守口径）
        killed = _run_mutant_tests(mutant, test_code, "", 15)
        assert killed is False, "弱测试全通过 → 变异体存活（保守口径）"

        # 强测试覆盖 3 边界 → 变异体被杀死
        strong_test = (
            "from mymod import check\n"
            "\n"
            "def test_above():\n    assert check(4) == True\n"
            "\n"
            "def test_boundary_eq():\n    assert check(3) == False\n"
            "\n"
            "def test_below():\n    assert check(0) == False\n"
        )
        killed_strong = _run_mutant_tests(mutant, strong_test, "", 15)
        assert killed_strong is True, "强测试应杀死 boundary_shift 变异体"


# ─── P2 统计口径 ────────────────────────────────────────────────────────────


class TestCohensDZeroVariance:
    """2026-09-26 round9 P2：零方差差值不再返回 0.0（与全赢事实矛盾）。"""

    def test_constant_positive_diff_returns_pos_inf(self):
        from experiments.statistical_analysis import cohens_d

        aitester = [{"task_id": f"t{i}", "passed": True} for i in range(5)]
        baseline = [{"task_id": f"t{i}", "passed": False} for i in range(5)]
        d, n = cohens_d(aitester, baseline)
        assert n == 5
        assert math.isinf(d) and d > 0, f"全赢应返回 +inf，实际 {d}"

    def test_constant_negative_diff_returns_neg_inf(self):
        from experiments.statistical_analysis import cohens_d

        aitester = [{"task_id": f"t{i}", "passed": False} for i in range(5)]
        baseline = [{"task_id": f"t{i}", "passed": True} for i in range(5)]
        d, _n = cohens_d(aitester, baseline)
        assert math.isinf(d) and d < 0, f"全输应返回 -inf，实际 {d}"

    def test_all_same_returns_zero(self):
        from experiments.statistical_analysis import cohens_d

        aitester = [{"task_id": f"t{i}", "passed": True} for i in range(5)]
        baseline = [{"task_id": f"t{i}", "passed": True} for i in range(5)]
        d, _n = cohens_d(aitester, baseline)
        assert d == 0.0, f"全同应返回 0.0，实际 {d}"


class TestInterpretDInfAndNan:
    """2026-09-26 round9 P2：interpret_d 对 inf/nan 返回正确语义。"""

    def test_inf_returns_large(self):
        from experiments.statistical_analysis import interpret_d

        assert interpret_d(float("inf")) == "large"
        assert interpret_d(float("-inf")) == "large"

    def test_nan_returns_unknown(self):
        from experiments.statistical_analysis import interpret_d

        assert interpret_d(float("nan")) == "unknown"

    def test_regular_values_unchanged(self):
        from experiments.statistical_analysis import interpret_d

        assert interpret_d(0.0) == "negligible"
        assert interpret_d(0.3) == "small"
        assert interpret_d(0.6) == "medium"
        assert interpret_d(0.9) == "large"


# ─── P2 收敛 Token 均摊 ─────────────────────────────────────────────────────


class TestConvergenceTokenEfficiencyNoNegative:
    """2026-09-26 round9 P2：无逐轮明细时 total 只计入最终轮一次，无负增量。"""

    def test_no_negative_incremental_tokens(self):
        from experiments.analysis_parts.convergence_analysis import _convergence_token_efficiency

        details = [
            {"task_id": "A", "passed": True, "iterations": 2, "token_usage": {"total_tokens": 200}},
            {"task_id": "B", "passed": False, "iterations": 0, "token_usage": {"total_tokens": 50}},
        ]
        result = _convergence_token_efficiency(details)
        for label, r in result["rounds"].items():
            assert r["incremental_tokens"] >= 0, f"{label} 轮增量 Token 为负: {r['incremental_tokens']}"

    def test_final_round_gets_full_amortized_total(self):
        from experiments.analysis_parts.convergence_analysis import _convergence_token_efficiency

        details = [
            {"task_id": "A", "passed": True, "iterations": 2, "token_usage": {"total_tokens": 200}},
        ]
        result = _convergence_token_efficiency(details)
        # k=0: A 未到达最终轮 → 0; k=1: 仍未到达 → 0; k=2: 200/3=66.67
        assert result["rounds"]["0"]["incremental_tokens"] == 0.0
        assert result["rounds"]["1"]["incremental_tokens"] == 0.0
        assert abs(result["rounds"]["2"]["incremental_tokens"] - 200 / 3) < 0.01

    def test_with_per_round_detail_unchanged(self):
        """有逐轮明细时仍按精确口径（不受新均摊逻辑影响）。

        2026-09-26 round9 P2：reached 口径为 iterations <= k（任务"到达"当轮
        即其最终轮 <= 当轮），有逐轮明细时仅当任务确实经过当轮才计入
        per_round[k].tokens。任务 iterations=2 仅在 k=2 及以后"到达"，
        k=0/1 的 reached 不含该任务 → round_tokens=0。
        """
        from experiments.analysis_parts.convergence_analysis import _convergence_token_efficiency

        details = [
            {
                "task_id": "A",
                "passed": True,
                "iterations": 2,
                "token_usage": {
                    "total_tokens": 300,
                    "iterations": [
                        {"tokens": 100},
                        {"tokens": 100},
                        {"tokens": 100},
                    ],
                },
            },
            {
                "task_id": "B",
                "passed": False,
                "iterations": 0,
                "token_usage": {
                    "total_tokens": 100,
                    "iterations": [{"tokens": 100}],
                },
            },
        ]
        result = _convergence_token_efficiency(details)
        # k=0: B 到达（iterations==0），per_round[0].tokens=100 → inc=100
        # k=1: 无任务恰好到达 k=1 → inc=0
        # k=2: A 到达（iterations==2），per_round[2].tokens=100 → inc=100
        assert result["rounds"]["0"]["incremental_tokens"] == 100.0
        assert result["rounds"]["1"]["incremental_tokens"] == 0.0
        assert result["rounds"]["2"]["incremental_tokens"] == 100.0


# ─── P2 死代码清理 ──────────────────────────────────────────────────────────


class TestDeadCodeRemoved:
    """2026-09-26 round9 P2：死代码已删除。"""

    def test_all_categories_not_in_compare_failures(self):
        import inspect

        from experiments import compare_failures

        src = inspect.getsource(compare_failures.cross_batch_comparison)
        # 死代码删除：原 all_categories 循环已删，仅保留清理注释（含 "all_categories"
        # 字样的说明注释）。检查的是"未删除"的循环体特征（for ... all_categories），
        # 而非注释文字。
        # 2026-09-26 round9 P2：原死循环 `for category in all_categories:` 已删除，
        # 注释行含 "all_categories" 属说明性文字，用 "for category in all_categories"
        # 做更精确的断言（锁定循环体已删而非注释）。
        assert "for category in all_categories" not in src, "死循环 all_categories 应已删除"

    def test_remove_not_op_not_in_mutation_testing(self):
        import inspect

        from experiments import mutation_testing

        src = inspect.getsource(mutation_testing.MutationGenerator)
        assert "_remove_not_op" not in src, "死代码 _remove_not_op 应已删除"


# ─── P2 健壮性 ──────────────────────────────────────────────────────────────


class TestContaminationTaskIdDedup:
    """2026-09-26 round9 P2：detect_contamination 按 task_id 去重。"""

    def test_duplicate_task_id_counted_once(self):
        from experiments.contamination_check import detect_contamination

        details = [
            {"task_id": "t1", "passed": True, "patch": "def a(): pass", "golden_patch": "def a(): pass"},
            {"task_id": "t1", "passed": True, "patch": "def a(): pass", "golden_patch": "def a(): pass"},
        ]
        result = detect_contamination(details)
        assert result["checked"] == 1, f"重复 task_id 应只计一次，实际 checked={result['checked']}"
        assert len(result["contaminated_tasks"]) + len(result["clean_tasks"]) == 1


class TestIterationsNullSafety:
    """2026-09-26 round9 P2：iterations=null 不再崩溃。"""

    def test_iterations_null_does_not_crash(self):
        from experiments.analyze_results import build_analysis

        data = {
            "dataset": "test",
            "results": {
                "aitester": {
                    "details": [
                        {"task_id": "t1", "passed": True, "iterations": None},
                        {"task_id": "t2", "passed": False, "iterations": 2},
                    ],
                    "total_functions": 2,
                    "passed_count": 1,
                },
            },
            "total_tasks": 2,
        }
        result = build_analysis(data)
        assert result["iteration_distribution"]["0"] == 1
        assert result["iteration_distribution"]["2"] == 1


class TestMutationScoreFloatGuard:
    """2026-09-26 round9 P2：mutation_score 非数值时 float() 不崩溃。"""

    def test_malformed_mutation_score_does_not_crash(self):
        from experiments.analysis_parts.convergence_analysis import _mutation_score_metrics

        details = [
            {"task_id": "t1", "passed": True, "mutation_score": "n/a"},
            {"task_id": "t2", "passed": True, "mutation_score": 0.8},
        ]
        result = _mutation_score_metrics(details)
        assert result["available"] is True
        assert result["observed_tasks"] == 1
        assert result["avg_mutation_score"] == 0.8


class TestVisualizeNoneDiagonal:
    """2026-09-26 round9 P2：visualize p 值热力图 None 对角线渲染为 "—"。"""

    def test_none_cell_renders_dash(self, capsys):
        import pytest

        matplotlib = pytest.importorskip("matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from experiments import visualize_results

        sig_result = {
            "pairwise": [
                ["aitester", "plain_llm", 0.05, 0.03, 1.0, 0.9, 0.5, "*", "x"],
            ],
        }
        # O35（2026-09-30 审查 F）：此前是 `try/except Exception: pass`——
        # 宽 except 把本用例要防的渲染异常一并吞掉，用例恒绿（自相矛盾）。
        # 上方已 matplotlib.use("Agg")（无显示环境也安全），故直接断言
        # 渲染不抛异常；抛出即用例失败，符合"None 对角线渲染为 —"的意图。
        try:
            # U3（2026-10-05 系统性审查落地）：补断言——渲染路径完整执行
            # （函数内部 savefig 后自关图窗，plt.get_fignums() 恒空，故以
            # "图表已保存" 提示输出作为全路径执行的观测信号）
            visualize_results.plot_statistical_significance(sig_result)
            captured = capsys.readouterr()
            assert "图表已保存: statistical_significance.png" in captured.out
        finally:
            plt.close("all")


# ─── P2 口径文档化 ──────────────────────────────────────────────────────────


class TestSyntheticFilterDocumented:
    """2026-09-26 round9 P2：synthetic 过滤有注释说明。"""

    def test_load_experiment_results_has_synthetic_comment(self):
        import inspect

        from experiments.statistical_analysis import load_experiment_results

        src = inspect.getsource(load_experiment_results)
        assert "synthetic" in src
        # 注释应说明"仅纳入 synthetic"的原因
        assert "round9" in src or "配对" in src, "应注释说明过滤原因"


class TestFailureKBNoSyntheticDefault:
    """2026-09-26 round9 P2：failure_knowledge_base 不再硬编码 synthetic。"""

    def test_no_synthetic_default_in_reproducible_steps(self):
        from experiments.analyze_failures import failure_knowledge_base

        details = [
            {
                "task_id": "t1",
                "passed": False,
                "error_category": "assertion",
                "diagnosis": "assert x == 1",
            },
        ]
        result = failure_knowledge_base(details, top_n=5)
        assert len(result) == 1
        steps = result[0]["reproducible_steps"]
        # 无 dataset 字段时不应硬编码 synthetic
        assert "synthetic" not in steps, f"不应硬编码 synthetic，实际: {steps}"
        # 应省略 --dataset 参数
        assert "--dataset" not in steps, f"无 dataset 时应省略 --dataset，实际: {steps}"

    def test_explicit_dataset_used_when_provided(self):
        from experiments.analyze_failures import failure_knowledge_base

        details = [
            {
                "task_id": "t1",
                "passed": False,
                "error_category": "assertion",
                "diagnosis": "assert x == 1",
            },
        ]
        result = failure_knowledge_base(details, top_n=5, dataset="swe_bench")
        assert "--dataset swe_bench" in result[0]["reproducible_steps"]


class TestDatasetInjectedInLoadAllResults:
    """2026-09-26 round9 P2：load_all_results 从顶层注入 dataset 字段。"""

    def test_dataset_injected_from_top_level(self, tmp_path):
        import json

        from experiments.analyze_failures import load_all_results

        bench_file = tmp_path / "benchmark_synthetic_001.json"
        bench_file.write_text(
            json.dumps(
                {
                    "dataset": "swe_bench",
                    "results": {
                        "aitester": {
                            "details": [
                                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                            ],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        tasks = load_all_results(str(tmp_path))
        assert len(tasks) == 1
        assert tasks[0]["dataset"] == "swe_bench", f"应从顶层注入 dataset，实际: {tasks[0].get('dataset')}"

    def test_no_dataset_key_when_absent(self, tmp_path):
        import json

        from experiments.analyze_failures import load_all_results

        bench_file = tmp_path / "benchmark_x.json"
        bench_file.write_text(
            json.dumps(
                {
                    "results": {
                        "aitester": {
                            "details": [
                                {"task_id": "t1", "passed": False, "error_category": "assertion"},
                            ],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        tasks = load_all_results(str(tmp_path))
        assert len(tasks) == 1
        assert "dataset" not in tasks[0], "无顶层 dataset 时不应注入"
