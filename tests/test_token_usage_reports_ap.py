"""AP（2026-10-21）：报告侧 token 总量消费者——不可读不折 0、坏值不当数字。

覆盖五个此前各自把“读不动”折回 0、或把在场坏值直接当数字的消费者：

- ``experiments/analyze_t1_b2_main_batch.py`` 逐 seed 池化与两处渲染；
- ``experiments/run_b8_injection.py`` README 冒烟合计、主批合计与表格单元；
- ``experiments/rag_ab_experiment.py`` 单行解析与 A/B 统计检验；
- ``experiments/analysis_parts/rag_analysis.py`` RAG 两组 token 均值；
- ``experiments/analyze_results.py`` Token 效率表与 RAG Token 效率节。

锁的口径：

- 共享 :func:`token_metric_reading` / :func:`sum_token_metric_values` 是聚合
  ``token_metrics`` 的唯一读数：整键 ``None`` / 字段缺席按历史 0；字段在场
  ``None`` 是上游拒绝（不可读，不折 0）；``"100"`` / bool / 小数 / 负数 /
  nan 不是计数；多份聚合任一不可读 ⇒ 不给部分和；
- 单行总量沿用 AO 的 :func:`row_total_token_reading`（rag_ab 解析、
  rag_analysis 分组）；
- 不可读在报告里落“不可读”并点名机制；干净真批次输出逐字不变。
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from experiments import analyze_results as ar
from experiments import analyze_t1_b2_main_batch as tb
from experiments import rag_ab_experiment as ra
from experiments import run_b8_injection as b8
from experiments.analysis_parts import rag_analysis as rag
from src.budget import token_usage as tu

_ROOT = Path(__file__).resolve().parents[1]
_T1B2_DIR = _ROOT / "experiments/results/t_round_b2_main_batch_20261018"
_B8_DIR = _ROOT / "experiments/results/s_round_b8_injection_20261018"
_RAG_SYNTHETIC_DIR = _ROOT / "experiments/results/rag_ab_synthetic"
_RAG_LVL_DIR = _ROOT / "experiments/results/rag_lvl25h_n40"
_MAIN_BATCH = _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json"


def _rag_details(directory: Path, sub: str) -> list[dict[str, Any]]:
    path = sorted((directory / sub).glob("*.json"))[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    return next(iter(data["results"].values()))["details"]


def _record(task_id: str, usage: Any, *, passed: bool = True) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "passed": passed,
        "iterations": 0,
        "elapsed_seconds": 1.0,
        "error_category": "",
        "token_usage": usage,
    }


class TestTokenMetricReading:
    """单份聚合 ``token_metrics`` 的字段读数。"""

    def test_absent_metrics_is_historical_zero(self) -> None:
        reading = tu.token_metric_reading(None, "total_tokens")
        assert reading == {"absent": True, "value": 0, "reasons": []}

    def test_absent_field_is_historical_zero(self) -> None:
        reading = tu.token_metric_reading({"total_input_tokens": 5}, "total_tokens")
        assert reading == {"absent": True, "value": 0, "reasons": []}

    def test_present_zero_is_readable(self) -> None:
        reading = tu.token_metric_reading({"total_tokens": 0}, "total_tokens")
        assert reading["value"] == 0
        assert reading["absent"] is False
        assert reading["reasons"] == []

    def test_present_none_is_upstream_refusal(self) -> None:
        reading = tu.token_metric_reading({"total_tokens": None}, "total_tokens")
        assert reading["value"] is None
        assert reading["reasons"] == ["token_metric_unreadable:total_tokens"]

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            ("100", "token_not_count:total_tokens:str"),
            (True, "token_not_count:total_tokens:bool"),
            (10.7, "token_not_count:total_tokens:float"),
            (-5, "token_negative:total_tokens"),
            (float("nan"), "token_not_finite:total_tokens"),
            (float("inf"), "token_not_finite:total_tokens"),
        ],
        ids=["str", "bool", "float", "negative", "nan", "inf"],
    )
    def test_bad_count_is_unreadable(self, value: Any, reason: str) -> None:
        reading = tu.token_metric_reading({"total_tokens": value}, "total_tokens")
        assert reading["value"] is None
        assert reading["reasons"] == [reason]

    @pytest.mark.parametrize("metrics", [[], "oops", 3], ids=["list", "str", "int"])
    def test_non_object_metrics_is_unreadable(self, metrics: Any) -> None:
        reading = tu.token_metric_reading(metrics, "total_tokens")
        assert reading["value"] is None
        assert reading["reasons"] == [f"token_metrics_not_object:{type(metrics).__name__}"]

    def test_allow_float_accepts_finite_non_negative(self) -> None:
        assert (
            tu.token_metric_reading({"avg_tokens_per_task": 12}, "avg_tokens_per_task", allow_float=True)["value"] == 12
        )
        assert (
            tu.token_metric_reading({"avg_tokens_per_task": 12.5}, "avg_tokens_per_task", allow_float=True)["value"]
            == 12.5
        )

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (True, "token_not_number:avg_tokens_per_task:bool"),
            ("12", "token_not_number:avg_tokens_per_task:str"),
            (float("nan"), "token_not_finite:avg_tokens_per_task"),
            (float("inf"), "token_not_finite:avg_tokens_per_task"),
            (-0.5, "token_negative:avg_tokens_per_task"),
        ],
        ids=["bool", "str", "nan", "inf", "negative"],
    )
    def test_allow_float_rejects_bad_numbers(self, value: Any, reason: str) -> None:
        reading = tu.token_metric_reading({"avg_tokens_per_task": value}, "avg_tokens_per_task", allow_float=True)
        assert reading["value"] is None
        assert reading["reasons"] == [reason]

    def test_allow_float_present_none(self) -> None:
        reading = tu.token_metric_reading({"avg_tokens_per_task": None}, "avg_tokens_per_task", allow_float=True)
        assert reading["value"] is None
        assert reading["reasons"] == ["token_metric_unreadable:avg_tokens_per_task"]


class TestSumTokenMetricValues:
    """多份聚合求和的“任一不可读即拒绝部分和”。"""

    def test_clean_sum_keeps_absent_as_zero(self) -> None:
        result = tu.sum_token_metric_values([{"total_tokens": 100}, None, {"total_tokens": 200}, {}], "total_tokens")
        assert result == {
            "value": 300,
            "n_readable": 2,
            "n_absent": 2,
            "n_unreadable": 0,
            "reasons": {},
        }

    def test_any_unreadable_blocks_partial_sum(self) -> None:
        result = tu.sum_token_metric_values([{"total_tokens": 100}, {"total_tokens": "100"}, None], "total_tokens")
        assert result["value"] is None
        assert result["n_readable"] == 1
        assert result["n_absent"] == 1
        assert result["n_unreadable"] == 1
        assert result["reasons"] == {"token_not_count:total_tokens:str": 1}

    def test_non_object_source_is_unreadable(self) -> None:
        result = tu.sum_token_metric_values([{"total_tokens": 100}, []], "total_tokens")
        assert result["value"] is None
        assert result["reasons"] == {"token_metrics_not_object:list": 1}

    def test_empty_sources_is_zero(self) -> None:
        assert tu.sum_token_metric_values([], "total_tokens") == {
            "value": 0,
            "n_readable": 0,
            "n_absent": 0,
            "n_unreadable": 0,
            "reasons": {},
        }

    def test_reason_counts_accumulate_per_row(self) -> None:
        result = tu.sum_token_metric_values([{"total_tokens": True}, {"total_tokens": False}], "total_tokens")
        assert result["value"] is None
        assert result["reasons"] == {"token_not_count:total_tokens:bool": 2}


class TestT1B2PooledTokens:
    """t1/b2 分析：逐 seed 池化与渲染。"""

    @staticmethod
    def _report() -> dict[str, Any]:
        return json.loads((_T1B2_DIR / "ANALYSIS_REPORT.json").read_text(encoding="utf-8"))

    def test_tokens_text_renders_refusal(self) -> None:
        assert tb._tokens_text(None) == "不可读"
        assert tb._tokens_text(0) == "0"
        assert tb._tokens_text(2629059) == "2629059"

    def test_real_batch_pooled_tokens_recompute(self) -> None:
        report = self._report()
        expected = {
            "aitester": {"in": 1897326, "out": 731733, "total": 2629059, "calls": 983},
            "plain_llm": {"in": 123394, "out": 186624, "total": 310018, "calls": 271},
            "plain_llm_df": {"in": 257038, "out": 386914, "total": 643952, "calls": 508},
        }
        keys = {
            "in": "total_input_tokens",
            "out": "total_output_tokens",
            "total": "total_tokens",
            "calls": "total_llm_calls",
        }
        for arm, wanted in expected.items():
            sources = [report["per_seed"][seed]["new"][arm]["token_metrics"] for seed in ("42", "43", "44")]
            got = {name: tu.sum_token_metric_values(sources, key)["value"] for name, key in keys.items()}
            assert got == wanted, arm
            assert report["pooled"][arm]["tokens"] == wanted, arm
        assert sum(wanted["total"] for wanted in expected.values()) == report["cost"]["total_tokens"] == 3583029
        assert "token_reading_reasons" not in report["pooled"]["aitester"]

    def test_pooled_source_uses_shared_sum(self) -> None:
        src = inspect.getsource(tb.build_report)
        assert "sum_token_metric_values(token_metric_sources" in src
        assert 'token_metric_sources.append(st.get("token_metrics"))' in src
        assert 'tokens: dict[str, Any] = {name: reading["value"] for name, reading in token_readings.items()}' in src
        assert "total_tokens = None if any(total is None for total in token_totals) else sum(token_totals)" in src

    def test_clean_readme_rendering_unchanged(self) -> None:
        md = tb.render_readme(self._report())
        assert "| `aitester`（新批） | 8/261 | 0.0307 | 22/261 | 200/261 | 2629059 | 1.447277 |" in md
        assert "- tokens=3583029；" in md
        assert "不可读" not in md

    def test_clean_baseline_fragment_unchanged(self) -> None:
        generated = tb.render_baseline_fragment(self._report())
        stored = (_T1B2_DIR / "BASELINE_FRAGMENT.yaml").read_text(encoding="utf-8")
        assert generated == stored

    def test_unreadable_pooled_token_renders_refusal(self) -> None:
        report = copy.deepcopy(self._report())
        report["pooled"]["aitester"]["tokens"]["total"] = None
        report["pooled"]["aitester"]["token_reading_reasons"] = {"token_metric_unreadable:total_tokens": 1}
        report["cost"]["total_tokens"] = None
        report["cost"]["token_unreadable_arms"] = {"aitester": {"token_metric_unreadable:total_tokens": 1}}
        md = tb.render_readme(report)
        assert "| `aitester`（新批） | 8/261 | 0.0307 | 22/261 | 200/261 | 不可读 | 1.447277 |" in md
        assert "- tokens=不可读；" in md
        fragment = tb.render_baseline_fragment(report)
        assert "tokens: 不可读, cost_usd" in fragment
        assert "total_tokens: 不可读, preflight_estimate_usd" in fragment


class TestB8Readme:
    """B8 README：冒烟合计、主批合计与表格单元。"""

    @staticmethod
    def _report() -> dict[str, Any]:
        return json.loads((_B8_DIR / "REPORT.json").read_text(encoding="utf-8"))

    def test_token_metric_text_clean_and_bad(self) -> None:
        assert b8._token_metric_text({"total_tokens": 83246}, "total_tokens") == "83246"
        assert b8._token_metric_text({"total_tokens": None}, "total_tokens") == "不可读"
        assert b8._token_metric_text({"total_tokens": "83246"}, "total_tokens") == "不可读"
        assert b8._token_metric_text(None, "total_tokens") == "0"

    def test_clean_readme_reproducible(self, tmp_path: Path) -> None:
        report = self._report()
        b8._write_readme(tmp_path, report)
        generated = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert generated == (_B8_DIR / "README.md").read_text(encoding="utf-8")
        assert "| tokens / LLM calls | 83246 / 58 | 113638 / 82 |" in generated
        assert "**64415 tokens ≈ $0.033032**" in generated
        assert "主批 196884 tokens" in generated
        assert "token 读数不可用" not in generated

    def test_unreadable_main_total_renders_refusal(self, tmp_path: Path) -> None:
        report = copy.deepcopy(self._report())
        report["arms"]["on"]["token_metrics"]["total_tokens"] = None
        report["harness_smoke"][0]["token_metrics"]["total_tokens"] = "14395"
        b8._write_readme(tmp_path, report)
        generated = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "| tokens / LLM calls | 不可读 / 58 | 113638 / 82 |" in generated
        assert "**不可读 tokens ≈ $0.033032**" in generated
        assert "主批 不可读 tokens" in generated
        assert "token_metric_unreadable:total_tokens×1" in generated
        assert "token_not_count:total_tokens:str×1" in generated

    def test_readme_source_uses_shared_readers(self) -> None:
        src = inspect.getsource(b8._write_readme)
        assert "sum_token_metric_values(" in src
        assert "token_metric_reading(" in src
        assert 'int((row.get("token_metrics") or {}).get("total_tokens") or 0)' not in src


class TestRagAbParse:
    """rag_ab 单行解析：总量走 AO 共享读数。"""

    def test_absent_usage_is_historical_zero(self) -> None:
        parsed = ra._parse_task_record({"task_id": "T"})
        assert parsed["tokens_total"] == 0
        assert "token_reading_reasons" not in parsed

    def test_total_only_and_inout_only(self) -> None:
        assert ra._parse_task_record(_record("T", {"total_tokens": 200}))["tokens_total"] == 200
        assert ra._parse_task_record(_record("T", {"input_tokens": 10, "output_tokens": 5}))["tokens_total"] == 15

    @pytest.mark.parametrize(
        ("usage", "reason"),
        [
            ({"total_tokens": None}, "token_not_count:total_tokens:NoneType"),
            ({"total_tokens": "100"}, "token_not_count:total_tokens:str"),
            ({"total_tokens": True}, "token_not_count:total_tokens:bool"),
            ({"total_tokens": -5}, "token_negative:total_tokens"),
            ({"total_tokens": float("nan")}, "token_not_finite:total_tokens"),
            ("oops", "token_usage_not_object:str"),
        ],
        ids=["null", "str", "bool", "negative", "nan", "non-object"],
    )
    def test_bad_total_is_unreadable(self, usage: Any, reason: str) -> None:
        parsed = ra._parse_task_record(_record("T", usage))
        assert parsed["tokens_total"] is None
        assert parsed["token_reading_reasons"] == [reason]


class TestRagAbCompare:
    """rag_ab A/B 统计：不可读不参与检验，也不报“无显著差异”。"""

    @staticmethod
    def _pair(on_usage: Any, off_usage: Any, *, on_passed: bool = True, off_passed: bool = True) -> dict[str, Any]:
        return ra.compare_ab(
            [
                ra._parse_task_record(_record("T1", on_usage, passed=on_passed)),
                ra._parse_task_record(_record("T2", {"total_tokens": 300})),
            ],
            [
                ra._parse_task_record(_record("T1", off_usage, passed=off_passed)),
                ra._parse_task_record(_record("T2", {"total_tokens": 240})),
            ],
        )

    def test_clean_comparison_unchanged(self) -> None:
        report = ra.compare_ab(
            [
                ra._parse_task_record(_record("a", {"total_tokens": 100})),
                ra._parse_task_record(_record("b", {"total_tokens": 200})),
            ],
            [
                ra._parse_task_record(_record("a", {"total_tokens": 50})),
                ra._parse_task_record(_record("b", {"total_tokens": 60})),
            ],
        )
        assert report["rag_on"]["avg_tokens"] == 150.0
        assert report["rag_off"]["avg_tokens"] == 55.0
        assert report["token_saving"]["delta_avg"] == -95.0
        assert list(report["token_saving"]) == [
            "delta_avg",
            "delta_pct",
            "t_stat",
            "p_value_welch",
            "u_stat",
            "p_value_mann_whitney",
            "cohens_d",
        ]

    def test_unreadable_record_blocks_statistics(self) -> None:
        report = self._pair({"total_tokens": 100}, {"total_tokens": None})
        assert report["rag_on"]["avg_tokens"] is None
        assert report["rag_off"]["avg_tokens"] is None
        for key in (
            "delta_avg",
            "delta_pct",
            "t_stat",
            "p_value_welch",
            "u_stat",
            "p_value_mann_whitney",
            "cohens_d",
        ):
            assert report["token_saving"][key] is None, key
        assert report["token_saving"]["n_token_unreadable_records"] == 1
        assert report["token_saving"]["token_reading_reasons"] == {"token_not_count:total_tokens:NoneType": 1}
        assert "不可判定" in report["interpretation"]["token"]
        assert "无显著差异" not in report["interpretation"]["token"]

    def test_bool_token_not_counted_as_one(self) -> None:
        report = self._pair({"total_tokens": 100}, {"total_tokens": True})
        assert report["token_saving"]["delta_avg"] is None
        assert report["token_saving"]["token_reading_reasons"] == {"token_not_count:total_tokens:bool": 1}

    def test_negative_token_not_averaged(self) -> None:
        report = self._pair({"total_tokens": 100}, {"total_tokens": -100})
        assert report["rag_off"]["avg_tokens"] is None
        assert report["token_saving"]["token_reading_reasons"] == {"token_negative:total_tokens": 1}

    def test_real_synthetic_batch_clean_values(self) -> None:
        on = ra._load_results(sorted((_RAG_SYNTHETIC_DIR / "rag_on").glob("*.json"))[-1])
        off = ra._load_results(sorted((_RAG_SYNTHETIC_DIR / "rag_off").glob("*.json"))[-1])
        assert len(on) == len(off) == 20
        assert all(record["tokens_total"] is not None for record in on + off)
        report = ra.compare_ab(on, off)
        assert report["rag_on"]["avg_tokens"] == 4345.6
        assert report["rag_off"]["avg_tokens"] == 3088.3
        assert report["token_saving"]["delta_avg"] == -1257.3
        assert "n_token_unreadable_records" not in report["token_saving"]

    def test_compare_source_gates_before_scipy(self) -> None:
        src = inspect.getsource(ra.compare_ab)
        assert "tokens_available" in src
        assert "token_unreadable" in src
        assert "if tokens_available:" in src


class TestRagTokenEfficiency:
    """RAG 两组 token 均值：组内坏值不再静默解析 / 折 0。"""

    @staticmethod
    def _details(rag_usage: Any, no_rag_usage: Any) -> list[dict[str, Any]]:
        return [
            {"task_id": "t1", "passed": True, "rag_stats": [{"results": 1}], "token_usage": rag_usage},
            {"task_id": "t2", "passed": False, "rag_stats": [], "token_usage": no_rag_usage},
        ]

    def test_clean_groups_unchanged(self) -> None:
        result = rag._rag_token_efficiency(self._details({"total_tokens": 200}, {"total_tokens": 100}))
        assert result["rag_group"] == {
            "tasks": 1,
            "avg_tokens": 200.0,
            "avg_iterations": 0.0,
            "success_rate": 1.0,
        }
        assert result["no_rag_group"] == {
            "tasks": 1,
            "avg_tokens": 100.0,
            "avg_iterations": 0.0,
            "success_rate": 0.0,
        }
        assert result["token_delta_ratio"] == 2.0

    @pytest.mark.parametrize(
        ("usage", "reason"),
        [
            ({"total_tokens": "100"}, "token_not_count:total_tokens:str"),
            ({"total_tokens": True}, "token_not_count:total_tokens:bool"),
            ({"total_tokens": -100}, "token_negative:total_tokens"),
            ({"total_tokens": float("nan")}, "token_not_finite:total_tokens"),
            ("oops", "token_usage_not_object:str"),
        ],
        ids=["str", "bool", "negative", "nan", "non-object"],
    )
    def test_bad_group_value_is_unreadable(self, usage: Any, reason: str) -> None:
        result = rag._rag_token_efficiency(self._details(usage, {"total_tokens": 100}))
        assert result["rag_group"]["avg_tokens"] is None
        assert result["rag_group"]["n_token_unreadable_rows"] == 1
        assert result["rag_group"]["token_reading_reasons"] == {reason: 1}
        assert result["token_delta_ratio"] is None

    def test_absent_usage_keeps_historical_zero(self) -> None:
        result = rag._rag_token_efficiency(self._details(None, None))
        assert result["rag_group"]["avg_tokens"] == 0.0
        assert result["no_rag_group"]["avg_tokens"] == 0.0
        assert "n_token_unreadable_rows" not in result["rag_group"]
        assert result["token_delta_ratio"] is None

    def test_zero_denominator_still_none(self) -> None:
        result = rag._rag_token_efficiency(self._details({"total_tokens": 200}, {"total_tokens": 0}))
        assert result["token_delta_ratio"] is None

    def test_real_batch_mixed_groups_clean_values(self) -> None:
        details = _rag_details(_RAG_LVL_DIR, "rag_on") + _rag_details(_RAG_LVL_DIR, "rag_off")
        result = rag._rag_token_efficiency(details)
        assert result["rag_group"]["avg_tokens"] == 4197.38
        assert result["no_rag_group"]["avg_tokens"] == 1558.28
        assert result["token_delta_ratio"] == 2.6936
        assert "n_token_unreadable_rows" not in result["rag_group"]

    def test_group_stats_no_longer_uses_safe_float(self) -> None:
        src = inspect.getsource(rag._rag_token_efficiency)
        assert "row_total_token_reading(" in src
        assert "_safe_float((r.get(" not in src


class TestAnalyzeResultsTables:
    """analyze_results 的 Token 效率表与 RAG Token 效率节。"""

    @staticmethod
    def _analysis() -> dict[str, Any]:
        data = json.loads(_MAIN_BATCH.read_text(encoding="utf-8"))
        return ar.build_analysis(data)

    def _render(self, analysis: dict[str, Any]) -> str:
        return ar.render_markdown(analysis, "benchmark.json")

    def test_real_batch_token_table_unchanged(self) -> None:
        md = self._render(self._analysis())
        section = md.split("## Token 效率对比", 1)[1].split("##", 1)[0]
        assert "| aitester | 2544615 | 565287 | 1979328 | 396 | 29248.45 |" in section
        assert "| plain_llm | 284317 | 46496 | 237821 | 96 | 3268.01 |" in section
        assert "不可读" not in section

    def test_none_metric_renders_refusal_and_note(self) -> None:
        analysis = self._analysis()
        analysis["per_baseline"]["aitester"]["token_metrics"] = {"total_tokens": None}
        section = self._render(analysis).split("## Token 效率对比", 1)[1].split("##", 1)[0]
        assert "| aitester | 不可读 | 0 | 0 | 0 | 0 |" in section
        assert "Token 读数不可判定" in section
        assert "`total_tokens` 不可读（token_metric_unreadable:total_tokens）" in section

    def test_non_object_metrics_renders_refusal(self) -> None:
        analysis = self._analysis()
        analysis["per_baseline"]["aitester"]["token_metrics"] = "oops"
        section = self._render(analysis).split("## Token 效率对比", 1)[1].split("##", 1)[0]
        assert "| aitester | 不可读 | 不可读 | 不可读 | 不可读 | 不可读 |" in section
        assert "token_metrics_not_object:str" in section

    def test_bad_avg_float_is_unreadable(self) -> None:
        analysis = self._analysis()
        analysis["per_baseline"]["aitester"]["token_metrics"] = {
            "total_tokens": 100,
            "avg_tokens_per_task": True,
        }
        section = self._render(analysis).split("## Token 效率对比", 1)[1].split("##", 1)[0]
        assert "| aitester | 100 | 0 | 0 | 0 | 不可读 |" in section
        assert "token_not_number:avg_tokens_per_task:bool" in section

    def test_rag_section_clean_render_unchanged(self) -> None:
        details = [
            {"task_id": "t1", "passed": True, "rag_stats": [{"results": 1}], "token_usage": {"total_tokens": 200}},
            {"task_id": "t2", "passed": False, "rag_stats": [], "token_usage": {"total_tokens": 100}},
        ]
        md = self._render(ar.build_analysis({"results": {"aitester": {"details": details}}}))
        section = md.split("## RAG Token 效率增益（2.3）", 1)[1].split("##", 1)[0]
        assert "| aitester | 1 | 200.0 | 1.0 | 1 | 100.0 | 0.0 | 2.00 | 0.0 |" in section
        assert "不可读" not in section

    def test_rag_section_unreadable_group_renders_refusal(self) -> None:
        details = [
            {"task_id": "t1", "passed": True, "rag_stats": [{"results": 1}], "token_usage": {"total_tokens": 100}},
            {"task_id": "t2", "passed": False, "rag_stats": [], "token_usage": {"total_tokens": None}},
        ]
        md = self._render(ar.build_analysis({"results": {"aitester": {"details": details}}}))
        section = md.split("## RAG Token 效率增益（2.3）", 1)[1].split("##", 1)[0]
        assert "| aitester | 1 | 100.0 | 1.0 | 1 | 不可读 | 0.0 | N/A | 0.0 |" in section
        assert "无RAG组 的 `avg_tokens` 不可读" in section
        assert "token_not_count:total_tokens:NoneType" in section

    def test_rag_section_unreadable_rag_group_renders_refusal(self) -> None:
        details = [
            {"task_id": "t1", "passed": True, "rag_stats": [{"results": 1}], "token_usage": {"total_tokens": None}},
            {"task_id": "t2", "passed": False, "rag_stats": [], "token_usage": {"total_tokens": 100}},
        ]
        md = self._render(ar.build_analysis({"results": {"aitester": {"details": details}}}))
        section = md.split("## RAG Token 效率增益（2.3）", 1)[1].split("##", 1)[0]
        assert "| aitester | 1 | 不可读 | 1.0 | 1 | 100.0 | 0.0 | N/A | 0.0 |" in section
        assert "RAG组 的 `avg_tokens` 不可读" in section

    def test_token_table_source_uses_shared_metric_reading(self) -> None:
        src = inspect.getsource(ar.render_markdown)
        assert 'token_metric_reading(t, "total_tokens")' in src
        assert "allow_float=True" in src
        assert "t.get('total_tokens', 0)" not in src
