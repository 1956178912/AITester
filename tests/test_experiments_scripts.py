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
