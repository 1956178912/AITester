"""AX（2026-10-21）：基准/全栈汇总的呈现与聚合读点——坏读数不中止汇总。

覆盖三个此前仍把聚合 ``token_metrics`` 原值直出的汇总读点：

- ``experiments/run_benchmark.py`` 跑完后的终端 token 效率行（``%d`` / ``%.2f``）：
  AN/AT 会把在场坏值写成 ``None``（上游拒绝），历史格式化在整轮跑完后抛
  ``TypeError``；
- ``experiments/run_full_stack_swe_bench_pro.py`` G8 Markdown 的“总 token”列：
  ``bl.get("token_metrics", {})`` 只兜键缺席，``null`` / 非对象 / 坏值要么崩、
  要么原样印进表格；
- ``experiments/summarize_full_stack.py`` 的逐基线 token 均值：
  ``(bl.get("token_metrics") or {}).get("total_tokens")`` 真值非对象崩、
  假值非对象改写，``float()`` 把 bool / 数字字符串 / 负数 / 非有限值收进均值。

锁的口径：

- 单份聚合 ``token_metrics`` 的唯一读数沿用 :func:`token_metric_reading`：
  整份 / 字段缺席按 AE2 历史 0，字段在场 ``None`` 是上游拒绝（不可读）；
- 呈现层不可读落“不可读”并点名机制，**不折 0、不原值直出**；一个字段坏
  不连坐同一份载荷的其它字段，一个基线坏不连坐另一个基线；
- 均值是另一历史口径：缺席块**不参与**逐基线均值（历史 ``or {}`` 行为），
  任一在场块不可读 ⇒ 该基线均值 ``None`` + 机制名，不给部分均值；
- 干净真语料逐字 / 逐位不变：64 份顶层 ``benchmark_*.json`` 的 34 个 token 块
  独立复算与聚合读数一致。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from experiments import run_benchmark as rb
from experiments import run_full_stack_swe_bench_pro as fs
from experiments import summarize_full_stack as sf
from tests._corpus_guard import require_full_corpus

_ROOT = Path(__file__).resolve().parents[1]
_RESULTS = _ROOT / "experiments/results"


def _summary(token_metrics: Any) -> dict[str, Any]:
    """最小 G8 汇总块：一个基线 + 一份聚合 token_metrics。"""
    return {
        "results": {
            "aitester": {
                "success_rate": 25.0,
                "avg_coverage": 80.0,
                "avg_iterations": 3.0,
                "token_metrics": token_metrics,
            }
        }
    }


class TestRunBenchmarkTokenEfficiencyTexts:
    """终端 token 效率行：None 是上游拒绝，不是格式化输入。"""

    def test_clean_readings_render_historical_text(self) -> None:
        log_text, progress_text, reasons = rb._token_efficiency_texts(
            {"total_tokens": 100, "avg_tokens_per_task": 12.5, "total_llm_calls": 3}
        )
        assert log_text == "总tokens=100, 平均每任务tokens=12.50, LLM调用次数=3"
        assert progress_text == "平均每任务Token: 12.5, LLM调用次数: 3"
        assert reasons == []

    def test_upstream_none_renders_unreadable_without_crash(self) -> None:
        log_text, progress_text, reasons = rb._token_efficiency_texts(
            {"total_tokens": None, "avg_tokens_per_task": None, "total_llm_calls": 1}
        )
        assert log_text == "总tokens=不可读, 平均每任务tokens=不可读, LLM调用次数=1"
        assert progress_text == "平均每任务Token: 不可读, LLM调用次数: 1"
        assert "token_metric_unreadable:total_tokens" in reasons
        assert "token_metric_unreadable:avg_tokens_per_task" in reasons
        assert "token_metric_unreadable:total_llm_calls" not in reasons

    def test_absent_metrics_is_historical_zero(self) -> None:
        log_text, progress_text, reasons = rb._token_efficiency_texts(None)
        assert log_text == "总tokens=0, 平均每任务tokens=0.00, LLM调用次数=0"
        assert progress_text == "平均每任务Token: 0, LLM调用次数: 0"
        assert reasons == []

    @pytest.mark.parametrize("bad", [True, "100", -5, 1.5, float("nan"), float("inf")])
    def test_bad_counts_are_unreadable(self, bad: Any) -> None:
        log_text, progress_text, reasons = rb._token_efficiency_texts(
            {"total_tokens": bad, "avg_tokens_per_task": 1.0, "total_llm_calls": 1}
        )
        assert "总tokens=不可读" in log_text
        assert "平均每任务tokens=1.00" in log_text
        assert "LLM调用次数=1" in log_text
        assert progress_text == "平均每任务Token: 1.0, LLM调用次数: 1"
        assert reasons

    def test_three_unreadable_fields_report_three_mechanisms(self) -> None:
        _, _, reasons = rb._token_efficiency_texts(
            {"total_tokens": None, "avg_tokens_per_task": None, "total_llm_calls": None}
        )
        assert len(reasons) == 3
        assert len(set(reasons)) == 3


class TestFullStackMarkdownTokenCell:
    """G8 Markdown 总 token 列：坏形状只废该单元。"""

    def test_clean_table_row_unchanged(self) -> None:
        lines = fs._render_baseline_table(_summary({"total_tokens": 100}))
        assert "| aitester | 25.0% | 80.0% | 3.0 | 100 |" in lines
        assert not any("不可读" in line for line in lines)

    def test_null_metrics_is_historical_zero(self) -> None:
        lines = fs._render_baseline_table(_summary(None))
        assert "| aitester | 25.0% | 80.0% | 3.0 | 0 |" in lines
        assert not any("不可读" in line for line in lines)

    @pytest.mark.parametrize("tm", [[1], 0, "", False, True, "100", {"total_tokens": [1]}])
    def test_bad_shape_or_value_renders_unreadable(self, tm: Any) -> None:
        lines = fs._render_baseline_table(_summary(tm))
        row = next(line for line in lines if line.startswith("| aitester |"))
        assert row.endswith("| 不可读 |")
        assert row.startswith("| aitester | 25.0% | 80.0% | 3.0 |")
        assert any(line.startswith("> aitester 的总 token 不可读") for line in lines)

    @pytest.mark.parametrize("value", [True, "100", -5, 1.5, float("nan"), float("inf"), None])
    def test_bad_token_value_renders_unreadable(self, value: Any) -> None:
        lines = fs._render_baseline_table(_summary({"total_tokens": value}))
        row = next(line for line in lines if line.startswith("| aitester |"))
        assert row.endswith("| 不可读 |")
        notes = [line for line in lines if line.startswith("> aitester")]
        assert notes and "total_tokens" in notes[0]

    def test_absent_field_is_historical_zero(self) -> None:
        lines = fs._render_baseline_table(_summary({"total_input_tokens": 9}))
        assert "| aitester | 25.0% | 80.0% | 3.0 | 0 |" in lines
        assert not any("不可读" in line for line in lines)


class TestSummarizeFullStackTokenAverage:
    """逐基线 token 均值：坏块让该基线不可读，但汇总继续。"""

    @staticmethod
    def _benchmark(token_metrics: Any, *, passed: int = 1, total: int = 2) -> dict[str, Any]:
        details = [{"task_id": f"t{i}", "passed": i < passed} for i in range(total)]
        return {
            "results": {
                "aitester": {
                    "details": details,
                    "token_metrics": token_metrics,
                }
            }
        }

    def test_mean_over_readable_values(self) -> None:
        agg = sf._aggregate_group(
            [
                self._benchmark({"total_tokens": 100}),
                self._benchmark({"total_tokens": 200}),
            ]
        )
        bl = agg["baselines"]["aitester"]
        assert bl["avg_total_tokens"] == 150.0
        assert "avg_total_tokens_reason" not in bl

    def test_absent_blocks_are_skipped_historically(self) -> None:
        agg = sf._aggregate_group(
            [
                self._benchmark({"total_tokens": 100}),
                self._benchmark(None),
                self._benchmark({"total_input_tokens": 5}),
            ]
        )
        bl = agg["baselines"]["aitester"]
        assert bl["avg_total_tokens"] == 100.0
        assert "avg_total_tokens_reason" not in bl

    def test_present_zero_counts_as_a_reading(self) -> None:
        agg = sf._aggregate_group(
            [
                self._benchmark({"total_tokens": 0}),
                self._benchmark({"total_tokens": 100}),
            ]
        )
        assert agg["baselines"]["aitester"]["avg_total_tokens"] == 50.0

    @pytest.mark.parametrize("tm", [["x"], "abc", True, 0, "", []])
    def test_non_object_shape_does_not_abort_other_stats(self, tm: Any) -> None:
        agg = sf._aggregate_group(
            [
                self._benchmark(tm, passed=1, total=2),
                self._benchmark({"total_tokens": 100}, passed=0, total=2),
            ]
        )
        bl = agg["baselines"]["aitester"]
        assert bl["avg_total_tokens"] is None
        assert "token_metrics_not_object" in bl["avg_total_tokens_reason"]
        assert bl["total_tasks"] == 4
        assert bl["passed_count"] == 1

    @pytest.mark.parametrize("value", [True, "100", -5, 1.5, float("nan"), float("inf"), None])
    def test_bad_value_makes_average_unreadable_without_partial_mean(self, value: Any) -> None:
        agg = sf._aggregate_group(
            [
                self._benchmark({"total_tokens": value}),
                self._benchmark({"total_tokens": 100}),
            ]
        )
        bl = agg["baselines"]["aitester"]
        assert bl["avg_total_tokens"] is None
        assert bl["avg_total_tokens_reason"]

    def test_one_bad_baseline_does_not_poison_another(self) -> None:
        summary = {
            "results": {
                "bad": {"details": [], "token_metrics": ["x"]},
                "good": {"details": [], "token_metrics": {"total_tokens": 42}},
            }
        }
        agg = sf._aggregate_group([summary])
        assert agg["baselines"]["bad"]["avg_total_tokens"] is None
        assert agg["baselines"]["good"]["avg_total_tokens"] == 42.0
        assert "avg_total_tokens_reason" not in agg["baselines"]["good"]


class TestRealCorpusCleanPath:
    """真语料独立复算：干净路径的均值逐位不变。"""

    def test_top_level_benchmark_means_reproduce(self) -> None:
        # BZ 轮：块数（34）以 results 顶层全部 benchmark_examples_*.json 为
        # 扫描面——fresh clone 只有入库子集 ⇒ require_full_corpus 显式 skip
        # 并带实测读数（tests/_corpus_guard.py）。
        require_full_corpus()
        files = sorted(_RESULTS.glob("benchmark_*.json"))
        assert files
        expected: dict[str, list[float]] = defaultdict(list)
        summaries: list[dict[str, Any]] = []
        n_blocks = 0
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            summaries.append(data)
            for baseline, bl in (data.get("results") or {}).items():
                tm = bl.get("token_metrics")
                if not isinstance(tm, dict) or "total_tokens" not in tm:
                    continue
                value = tm["total_tokens"]
                if isinstance(value, int) and not isinstance(value, bool):
                    expected[baseline].append(float(value))
                    n_blocks += 1
        assert n_blocks == 34
        agg = sf._aggregate_group(summaries)
        for baseline, values in expected.items():
            want = round(sum(values) / len(values), 3)
            assert agg["baselines"][baseline]["avg_total_tokens"] == want
            assert "avg_total_tokens_reason" not in agg["baselines"][baseline]


class TestSourceLocks:
    """源码锁：三个读点不得回退到宽松读取。"""

    def test_summarize_uses_shared_reading(self) -> None:
        import inspect

        body = inspect.getsource(sf._aggregate_group).split('"""', 2)[-1]
        assert '(bl.get("token_metrics") or {})' not in body
        assert "float(token_total)" not in body
        assert 'token_metric_reading(bl.get("token_metrics"), "total_tokens")' in body

    def test_run_benchmark_terminal_uses_shared_reading(self) -> None:
        source = (_ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8")
        assert 'tm["total_tokens"]' not in source
        assert 'tm["avg_tokens_per_task"]' not in source
        assert 'tm["total_llm_calls"]' not in source
        assert "_token_efficiency_texts(" in source

    def test_run_full_stack_table_uses_shared_reading(self) -> None:
        import inspect

        body = inspect.getsource(fs._render_baseline_table).split('"""', 2)[-1]
        assert 'bl.get("token_metrics", {})' not in body
        assert "tm.get('total_tokens')" not in body
        assert 'token_metric_reading(bl.get("token_metrics"), "total_tokens")' in body
        module = (_ROOT / "experiments/run_full_stack_swe_bench_pro.py").read_text(encoding="utf-8")
        assert "_render_baseline_table(summary)" in module
