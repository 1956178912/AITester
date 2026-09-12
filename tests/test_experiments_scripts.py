"""experiments/ 与 scripts/ 修复回归（0.9.9 批次）。

覆盖：
- visualize_results.load_latest_result 仅识别 benchmark_* 前缀
  （此前纯文件名倒序会误选 swebench_20_summary.json / performance_benchmark.json 等非 benchmark 文件）
- run_standardized_experiments.run_experiment 三个返回分支均带 description 键
  （此前 main() 写汇总报告时无条件读 r['description']，每次运行必 KeyError）
- run_benchmark 并行度经 config.BENCHMARK_PARALLELISM 容错解析
  （此前 int(os.getenv(...)) 直读，坏值在 import 阶段 ValueError 崩溃）
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script_module(module_name: str, filename: str):
    """以 importlib 加载 scripts/ 目录下的脚本（scripts 非包，无 __init__.py）。"""
    path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestVisualizeLoadLatestResult:
    """load_latest_result 仅识别 benchmark_* 前缀文件"""

    @pytest.fixture()
    def module(self):
        # matplotlib/pandas/scipy 重依赖，惰性导入一次即可
        from experiments import visualize_results

        return visualize_results

    def test_prefers_latest_benchmark_file(self, module, tmp_path):
        """混有汇总/基线文件时，仍应选中最新的 benchmark_* 文件（修复前会误选 swebench_20_summary.json）"""
        (tmp_path / "swebench_20_summary.json").write_text(json.dumps({}), encoding="utf-8")
        (tmp_path / "performance_benchmark.json").write_text(json.dumps({}), encoding="utf-8")
        (tmp_path / "synthetic_plain_llm_20260817.json").write_text(json.dumps({}), encoding="utf-8")
        (tmp_path / "benchmark_examples_20260813_100000.json").write_text(json.dumps({}), encoding="utf-8")
        (tmp_path / "benchmark_examples_20260814_100000.json").write_text(json.dumps({}), encoding="utf-8")

        picked = module.load_latest_result(str(tmp_path))
        assert picked.endswith("benchmark_examples_20260814_100000.json")

    def test_fallback_when_no_benchmark_files(self, module, tmp_path):
        """无 benchmark_* 文件时回退全量倒序（保持旧行为兜底，不崩溃）"""
        (tmp_path / "swebench_20_summary.json").write_text(json.dumps({}), encoding="utf-8")
        (tmp_path / "other.json").write_text(json.dumps({}), encoding="utf-8")

        picked = module.load_latest_result(str(tmp_path))
        assert picked.endswith("swebench_20_summary.json")

    def test_empty_dir_raises(self, module, tmp_path):
        with pytest.raises(FileNotFoundError):
            module.load_latest_result(str(tmp_path))


class TestVisualizeSummaryMdTable:
    """write_summary_md 的基线汇总表头与数据列对齐（8 列回归护栏）"""

    @pytest.fixture()
    def module(self):
        from experiments import visualize_results

        return visualize_results

    def test_header_single_row_with_8_columns(self, module, tmp_path, monkeypatch):
        """表头只有一行，且 8 列与 8 个分隔符段一一对应。

        回归：此前表头被拆成 5 列 + 3 列两行，与 8 列的数据行错位。
        """
        monkeypatch.setattr(module, "_charts_dir", str(tmp_path))
        module.write_summary_md({"dataset": "d", "results": {}}, {"n_tasks": 0, "per_baseline": {}, "pairwise": []})

        content = (tmp_path / "summary_stats.md").read_text(encoding="utf-8")
        lines = content.splitlines()
        headers = [line for line in lines if line.startswith("| Baseline")]
        assert len(headers) == 1
        assert headers[0] == (
            "| Baseline | Tasks | Passed | Success Rate | Avg Coverage | Avg Iterations | Mean Rate | Std |"
        )
        # 表头下一行必须是 8 段分隔符
        idx = lines.index(headers[0])
        assert len(lines[idx + 1].strip().split("|")) == 10  # 8 段 + 首尾空段
        assert lines[idx + 1].count("-") >= 8 * 3

    def test_data_row_column_count_matches_header(self, module, tmp_path, monkeypatch):
        """有基线数据时，数据行同样是 8 列（与表头对齐）。"""
        monkeypatch.setattr(module, "_charts_dir", str(tmp_path))
        summary = {
            "dataset": "d",
            "results": {
                "aitester": {"passed_count": 3, "success_rate": 60.0, "avg_coverage": 70.0, "avg_iterations": 2.0}
            },
        }
        sig_result = {
            "n_tasks": 5,
            "per_baseline": {"aitester": {"n": 5, "mean_rate": 0.6, "std_rate": 0.1}},
            "pairwise": [],
        }
        module.write_summary_md(summary, sig_result)

        content = (tmp_path / "summary_stats.md").read_text(encoding="utf-8")
        data_row = [
            line for line in content.splitlines() if line.startswith("| aitester")
        ]  # 数据行以基线名 aitester 开头
        assert data_row, "数据行 8 列与表头对齐"
        assert len(data_row[0].strip().split("|")) == 10


class TestRunStandardizedExperimentReturnKeys:
    """run_experiment 三个返回分支均携带 description 键（KeyError 回归护栏）"""

    @pytest.fixture()
    def module(self):
        # 每次加载新模块副本，避免跨测试残留
        return _load_script_module(f"run_std_{id(object())}", "run_standardized_experiments.py")

    def _first_experiment(self, module):
        return module.EXPERIMENTS[0]

    def test_success_branch_has_description(self, module, monkeypatch):
        exp = self._first_experiment(module)
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "stdout-text"
        fake.stderr = "stderr-text"
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: fake)

        result = module.run_experiment(exp)
        assert result["status"] == "success"
        # 回归护栏：main() 写汇总报告时无条件读 r['description']，缺键即必崩
        assert result["description"] == exp["description"]

    def test_failed_branch_has_description(self, module, monkeypatch):
        exp = self._first_experiment(module)
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        fake.stderr = "boom"
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: fake)

        result = module.run_experiment(exp)
        assert result["status"] == "failed"
        assert "description" in result

    def test_timeout_branch_has_description(self, module, monkeypatch):
        exp = self._first_experiment(module)
        monkeypatch.setattr(
            module.subprocess,
            "run",
            lambda *a, **k: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd="python run_benchmark.py", timeout=3600)
            ),
        )

        result = module.run_experiment(exp)
        assert result["status"] == "timeout"
        assert result["description"] == exp["description"]

    def test_error_branch_has_description(self, module, monkeypatch):
        exp = self._first_experiment(module)
        monkeypatch.setattr(
            module.subprocess,
            "run",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
        )

        result = module.run_experiment(exp)
        assert result["status"] == "error"
        assert "description" in result


class TestRunBenchmarkParallelismViaConfig:
    """run_benchmark 并行度经 config.BENCHMARK_PARALLELISM（源码级回归护栏）"""

    def test_no_raw_env_read_of_benchmark_parallelism(self):
        """此前 int(os.getenv("BENCHMARK_PARALLELISM","0")) 直读，坏值 import 即崩"""
        source = (REPO_ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")
        assert 'os.getenv("BENCHMARK_PARALLELISM"' not in source
        assert "from config import" in source and "BENCHMARK_PARALLELISM" in source


class TestAnalyzeResultsScript:
    """4.3 analyze_results.py：benchmark JSON → Markdown 汇总的纯函数测试
    （build_analysis / render_markdown 不碰文件系统，直接喂 dict 断言）"""

    @pytest.fixture()
    def module(self):
        # experiments 为包（有 __init__.py），直接导入
        from experiments import analyze_results

        return analyze_results

    def _sample_data(self) -> dict:
        """构造最小合法 benchmark JSON（含 token_metrics/rag_metrics 新字段）"""
        return {
            "timestamp": "2026-09-14T10:00:00",
            "dataset": "synthetic",
            "total_tasks": 3,
            "enable_planner": True,
            "enable_debugger": True,
            "enable_rag": True,
            "results": {
                "aitester": {
                    "total_functions": 3,
                    "passed_count": 2,
                    "success_rate": 66.7,
                    "avg_coverage": 55.0,
                    "avg_iterations": 1.0,
                    "avg_elapsed_seconds": 10.0,
                    "total_time": 30.0,
                    "token_metrics": {
                        "total_input_tokens": 1000,
                        "total_output_tokens": 500,
                        "total_tokens": 1500,
                        "total_llm_calls": 9,
                        "avg_tokens_per_task": 500.0,
                    },
                    "rag_metrics": {
                        "retrievals": 3,
                        "hits": 2,
                        "hit_rate": 0.6667,
                        "avg_max_similarity": 0.8,
                    },
                    "details": [
                        {"task_id": "t1", "passed": True, "iterations": 0, "coverage": 80.0},
                        {"task_id": "t2", "passed": True, "iterations": 1, "coverage": 60.0},
                        {
                            "task_id": "t3",
                            "passed": False,
                            "iterations": 2,
                            "error_category": "index_error",
                            "coverage": 0.0,
                        },
                    ],
                },
                "plain_llm": {
                    "total_functions": 3,
                    "passed_count": 1,
                    "success_rate": 33.3,
                    "avg_coverage": 20.0,
                    "avg_iterations": 0.0,
                    "avg_elapsed_seconds": 5.0,
                    "total_time": 15.0,
                    "token_metrics": {
                        "total_input_tokens": 300,
                        "total_output_tokens": 100,
                        "total_tokens": 400,
                        "total_llm_calls": 3,
                        "avg_tokens_per_task": 133.33,
                    },
                    "rag_metrics": None,
                    "details": [
                        {"task_id": "t1", "passed": True, "iterations": 0, "coverage": 80.0},
                        {"task_id": "t2", "passed": False, "iterations": 0, "error_category": "llm_format_error"},
                        {"task_id": "t3", "passed": False, "iterations": 0, "error_category": "llm_format_error"},
                    ],
                },
            },
        }

    def test_build_analysis_core_fields(self, module):
        """build_analysis 提取核心指标与按基线的失败原因分布（1.2 细化类别可单独计数）"""
        analysis = module.build_analysis(self._sample_data())
        assert analysis["meta"]["dataset"] == "synthetic"
        assert analysis["meta"]["baselines"] == ["aitester", "plain_llm"]
        assert analysis["per_baseline"]["aitester"]["success_rate"] == 66.7
        assert analysis["per_baseline"]["aitester"]["failure_category_distribution"] == {"index_error": 1}
        assert analysis["per_baseline"]["plain_llm"]["failure_category_distribution"] == {"llm_format_error": 2}
        # 迭代分布：aitester(0,1,2) + plain_llm(0,0,0) → 0×4, 1×1, 2×1, 3×0
        assert analysis["iteration_distribution"] == {"0": 4, "1": 1, "2": 1, "3": 0}

    def test_build_analysis_legacy_json_without_token_metrics(self, module):
        """旧 JSON 无 token_metrics/rag_metrics 字段时，从 details 兜底累加 + 容忍缺键"""
        data = self._sample_data()
        del data["results"]["aitester"]["token_metrics"]
        del data["results"]["aitester"]["rag_metrics"]
        data["results"]["aitester"]["details"][0]["token_usage"] = {
            "input_tokens": 100,
            "output_tokens": 50,
            "llm_calls": 3,
        }
        analysis = module.build_analysis(data)
        tm = analysis["per_baseline"]["aitester"]["token_metrics"]
        assert tm["total_tokens"] == 150
        assert tm["total_llm_calls"] == 3
        # 无 failure_category_distribution 键时从 details 兜底统计
        assert analysis["per_baseline"]["aitester"]["failure_category_distribution"] == {"index_error": 1}
        # 无 rag_metrics 键时保持 None（旧 JSON 容忍）
        assert analysis["per_baseline"]["aitester"]["rag_metrics"] is None

    def test_render_markdown_contains_fairness_table(self, module):
        """2.2 公平性对照：Markdown 必含 Token 效率对比表与按基线的失败原因分布"""
        analysis = module.build_analysis(self._sample_data())
        md = module.render_markdown(analysis, "benchmark_x.json")
        assert "Token 效率对比" in md
        assert "| aitester | 1500 | 1000 | 500 | 9 | 500.0 |" in md
        assert "失败原因分布（按基线）" in md
        assert "### plain_llm" in md
        assert "| llm_format_error | 2 |" in md
        # RAG 质量表仅在 retrievals>0 时输出
        assert "RAG 检索质量" in md
        assert "| aitester | 3 | 2 | 0.6667 | 0.8 |" in md

    def test_render_markdown_no_rag_section_when_disabled(self, module):
        """未启用 RAG（rag_metrics 全 None）时不输出 RAG 章节（避免空表误导）"""
        data = self._sample_data()
        data["results"]["aitester"]["rag_metrics"] = None
        analysis = module.build_analysis(data)
        md = module.render_markdown(analysis, "benchmark_x.json")
        assert "RAG 检索质量" not in md

    def test_rag_by_kind_breakdown(self, module):
        """2.3 自动汇总：按检索类型（test_cases/repairs）分解命中率与相似度"""
        data = self._sample_data()
        data["results"]["aitester"]["details"] = [
            {
                "task_id": "t1",
                "passed": True,
                "iterations": 0,
                "error_category": "",
                "rag_stats": [
                    {"kind": "test_cases", "results": 3, "max_similarity": 0.81},
                    {"kind": "repairs", "results": 0, "max_similarity": None},
                ],
            },
            {
                "task_id": "t2",
                "passed": False,
                "iterations": 2,
                "error_category": "assertion",
                "rag_stats": [
                    {"kind": "test_cases", "results": 0},
                    {"kind": "repairs", "results": 1, "max_similarity": 0.42},
                ],
            },
        ]
        analysis = module.build_analysis(data)
        by_kind = analysis["per_baseline"]["aitester"]["details_rag_by_kind"]
        assert by_kind["test_cases"]["retrievals"] == 2
        assert by_kind["test_cases"]["hits"] == 1
        assert by_kind["test_cases"]["hit_rate"] == 0.5
        assert by_kind["test_cases"]["avg_max_similarity"] == 0.81
        assert by_kind["repairs"]["hits"] == 1
        assert by_kind["repairs"]["avg_max_similarity"] == 0.42

    def test_rag_by_kind_empty_when_no_stats(self, module):
        """旧 JSON 无 rag_stats 字段时，按类型分解为空（渲染时跳过小节）"""
        analysis = module.build_analysis(self._sample_data())
        assert analysis["per_baseline"]["aitester"]["details_rag_by_kind"] == {}

    def test_rag_hit_by_failure_category_cross(self, module):
        """2.3 自动汇总：失败类别 × RAG 命中交叉表（1.1 细化类别单独成组）"""
        data = self._sample_data()
        data["results"]["aitester"]["details"] = [
            {
                "task_id": "t1",
                "passed": True,
                "rag_stats": [{"kind": "test_cases", "results": 3}],
            },
            {
                "task_id": "t2",
                "passed": False,
                "error_category": "rag_retrieval_empty",
                "rag_stats": [{"kind": "test_cases", "results": 0}],
            },
            {
                "task_id": "t3",
                "passed": False,
                "error_category": "patch_validation_failed",
                "rag_stats": [{"kind": "repairs", "results": 1}],
            },
            {
                "task_id": "t4",
                "passed": False,
                "error_category": "assertion",
                "rag_stats": [{"kind": "test_cases", "results": 2}],
            },
        ]
        analysis = module.build_analysis(data)
        cross = analysis["per_baseline"]["aitester"]["rag_hit_by_failure_category"]
        assert cross == {
            "rag_retrieval_empty": {"total": 1, "with_hit": 0},
            "patch_validation_failed": {"total": 1, "with_hit": 1},
            "assertion": {"total": 1, "with_hit": 1},
        }
        # 渲染含交叉表与解读注记
        md = module.render_markdown(analysis, "benchmark_x.json")
        assert "RAG 命中 × 失败类别交叉表" in md
        assert "| aitester | rag_retrieval_empty | 1 | 0 | 0.0 |" in md

    def test_rag_cross_empty_when_no_failures(self, module):
        """无失败任务时交叉表为空（成功任务不计入 RAG 命中分析）"""
        data = self._sample_data()
        data["results"]["aitester"]["details"] = [
            {"task_id": "t1", "passed": True, "rag_stats": [{"kind": "test_cases", "results": 3}]}
        ]
        analysis = module.build_analysis(data)
        assert analysis["per_baseline"]["aitester"]["rag_hit_by_failure_category"] == {}

    def test_load_latest_benchmark_prefers_benchmark_prefix(self, module, tmp_path):
        """与 visualize_results 同口径：仅识别 benchmark_* 前缀（避免误选汇总文件）"""
        (tmp_path / "swebench_20_summary.json").write_text("{}", encoding="utf-8")
        (tmp_path / "benchmark_a_20260101.json").write_text("{}", encoding="utf-8")
        (tmp_path / "benchmark_b_20260901.json").write_text("{}", encoding="utf-8")
        picked = module.load_latest_benchmark(str(tmp_path))
        assert picked.endswith("benchmark_b_20260901.json")
