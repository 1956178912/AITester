"""AN 轮：token_usage 聚合读取器收口（写盘 token_metrics / 可信报告 / 旧批次兜底）。

缺陷族（2026-10-21 前置测量实测）：
    `run_benchmark._aggregate_token_metrics`、`trusted_verification.arm_trusted_metrics`、
    `rag_analysis._token_metrics_from_details` 都用
    `(r.get("token_usage") or {}).get(..., 0)` 自行求和：
    - 非对象真值行（`token_usage="100"`）AttributeError；
    - bool / 小数 / 字符串 / 负数 / nan 静默入总量（True→1、-3 命中率 -300%）；
    - 行内 `total_tokens` 与 in+out 矛盾时，写盘侧取 in+out、可信报告取 total_tokens
      ——同一事实两个读数；
    - 缓存 / 调用坏值被读成 0，部分和冒充全额。

处置：
    - AM 的单行策略迁入生产者模块 `src.budget.token_usage.row_token_reading`
      （成本表 `_row_cost_tokens` 成为其别名，判定只写一遍）；
    - 新增 `aggregate_row_token_usage`：整键缺席 / null 按历史 0；在场坏值让
      对应总量为 None（不给部分和）；拆分矛盾只披露（token 总量仍可读，与 AM 的
      金额级阻断区分）；缓存半套 / 坏值让缓存读数为 None + 机制索引；
    - 三个消费者共用该读取器，披露键只在真发生时写入。

真批次证据：main_batch 三文件 783 行 / 9 臂全部 int 自洽、缓存 schema 缺席
⇒ 复算与已落 `token_metrics` 逐键一致，返回域逐键不变。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from experiments import run_benchmark as rb
from experiments import statistical_analysis as sa
from experiments import trusted_verification as tv
from experiments.analysis_parts.rag_analysis import _token_metrics_from_details
from src.budget import token_usage as tu

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]
_DISCLOSURE_KEYS = (
    "n_token_unreadable_rows",
    "token_reading_reasons",
    "n_token_split_mismatch_rows",
    "cache_reading_reasons",
)


def _rows(*usages: Any) -> list[dict[str, Any]]:
    return [{"token_usage": usage} for usage in usages]


def _two_clean_rows() -> list[dict[str, Any]]:
    return [
        {
            "token_usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "llm_calls": 2,
                "cache_hits": 1,
                "cache_avoided_tokens": 30,
            }
        },
        {
            "token_usage": {
                "input_tokens": 200,
                "output_tokens": 100,
                "llm_calls": 3,
                "cache_hits": 0,
                "cache_avoided_tokens": 0,
            }
        },
    ]


class TestRowTokenReadingShared:
    """AN：行级读数是共享的（成本表不得再持有第二份策略）。"""

    def test_cost_table_delegates_to_producer_reader(self) -> None:
        assert sa._row_cost_tokens is tu.row_token_reading

    def test_absent_key_is_historical_zero(self) -> None:
        reading = tu.row_token_reading({"passed": True})
        assert reading == {"absent": True, "usage": None, "counts": (0, 0, 0), "reasons": []}

    def test_null_usage_is_historical_zero(self) -> None:
        reading = tu.row_token_reading({"token_usage": None})
        assert reading["absent"] is True
        assert reading["counts"] == (0, 0, 0)

    def test_all_zero_and_all_missing_partial_are_zero_rows(self) -> None:
        assert tu.row_token_reading({"token_usage": {}})["counts"] == (0, 0, 0)
        assert tu.row_token_reading({"token_usage": {"input_tokens": 0}})["counts"] == (0, 0, 0)

    def test_total_absent_with_both_parts_is_readable(self) -> None:
        reading = tu.row_token_reading({"token_usage": {"input_tokens": 10, "output_tokens": 5}})
        assert reading["counts"] == (15, 10, 5)

    def test_present_bad_value_is_unreadable_with_reason(self) -> None:
        reading = tu.row_token_reading({"token_usage": {"total_tokens": 15, "input_tokens": "10", "output_tokens": 5}})
        assert reading["counts"] is None
        assert reading["reasons"] == ["token_not_count:input_tokens:str"]


class TestAggregateRowTokenUsage:
    """AN：多行聚合的量级与阻断范围。"""

    def test_absent_rows_are_historical_zero(self) -> None:
        agg = tu.aggregate_row_token_usage([{"passed": True}])
        assert (agg["input_tokens"], agg["output_tokens"], agg["total_tokens"]) == (0, 0, 0)
        assert agg["llm_calls"] == 0
        assert agg["n_absent_rows"] == 1
        assert agg["n_unreadable_rows"] == 0
        assert agg["cache"]["present"] is False

    def test_non_object_usage_does_not_crash_and_blocks_totals(self) -> None:
        agg = tu.aggregate_row_token_usage([{"token_usage": "100"}])
        assert agg["input_tokens"] is None
        assert agg["output_tokens"] is None
        assert agg["total_tokens"] is None
        assert agg["llm_calls"] is None
        assert agg["n_unreadable_rows"] == 1
        assert agg["reading_reasons"] == {"token_usage_not_object:str": 1}
        assert agg["cache"]["present"] is True
        assert agg["cache"]["hits"] is None
        assert agg["cache"]["reasons"] == {"token_usage_not_object:str": 1}

    @pytest.mark.parametrize(
        ("value", "code"),
        [
            (True, "token_not_count:input_tokens:bool"),
            (1.5, "token_not_count:input_tokens:float"),
            ("100", "token_not_count:input_tokens:str"),
            (-5, "token_negative:input_tokens"),
            (float("nan"), "token_not_finite:input_tokens"),
        ],
    )
    def test_bad_triple_value_blocks_totals(self, value: Any, code: str) -> None:
        agg = tu.aggregate_row_token_usage(_rows({"total_tokens": 10, "input_tokens": value, "output_tokens": 5}))
        assert agg["input_tokens"] is None
        assert agg["total_tokens"] is None
        assert agg["reading_reasons"] == {code: 1}

    def test_partial_positive_is_unreadable(self) -> None:
        agg = tu.aggregate_row_token_usage(_rows({"total_tokens": 105, "input_tokens": 100}))
        assert agg["total_tokens"] is None
        assert "token_field_absent:output_tokens" in agg["reading_reasons"]

    def test_all_zero_partial_row_does_not_poison_valid_rows(self) -> None:
        agg = tu.aggregate_row_token_usage(
            _rows({"input_tokens": 0}, {"total_tokens": 110, "input_tokens": 100, "output_tokens": 10})
        )
        assert (agg["input_tokens"], agg["output_tokens"], agg["total_tokens"]) == (100, 10, 110)

    def test_total_absent_with_both_parts_contributes(self) -> None:
        agg = tu.aggregate_row_token_usage(_rows({"input_tokens": 100, "output_tokens": 10}))
        assert agg["total_tokens"] == 110

    def test_split_mismatch_is_disclosed_but_totals_stay_readable(self) -> None:
        agg = tu.aggregate_row_token_usage(_rows({"total_tokens": 999, "input_tokens": 100, "output_tokens": 10}))
        assert (agg["input_tokens"], agg["output_tokens"], agg["total_tokens"]) == (100, 10, 999)
        assert agg["n_contradiction_rows"] == 1
        assert agg["contradiction_reasons"] == {"token_split_mismatch": 1}
        assert agg["n_unreadable_rows"] == 0

    def test_bad_llm_calls_blocks_calls_only(self) -> None:
        agg = tu.aggregate_row_token_usage(
            _rows({"total_tokens": 110, "input_tokens": 100, "output_tokens": 10, "llm_calls": -3})
        )
        assert agg["total_tokens"] == 110
        assert agg["llm_calls"] is None
        assert agg["n_unreadable_rows"] == 1
        assert agg["reading_reasons"] == {"token_negative:llm_calls": 1}

    def test_bad_cache_blocks_cache_only(self) -> None:
        agg = tu.aggregate_row_token_usage(
            _rows(
                {
                    "total_tokens": 110,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "llm_calls": 1,
                    "cache_hits": "2",
                    "cache_avoided_tokens": 0,
                }
            )
        )
        assert agg["total_tokens"] == 110
        assert agg["cache"]["present"] is True
        assert agg["cache"]["complete"] is False
        assert agg["cache"]["hits"] is None
        assert agg["cache"]["avoided"] is None
        assert agg["cache"]["reasons"] == {"token_not_count:cache_hits:str": 1}

    def test_cache_schema_half_present_across_rows_is_incomplete(self) -> None:
        agg = tu.aggregate_row_token_usage(
            _rows(
                {"total_tokens": 110, "input_tokens": 100, "output_tokens": 10, "cache_hits": 1},
                {"total_tokens": 110, "input_tokens": 100, "output_tokens": 10},
            )
        )
        assert agg["cache"]["present"] is True
        assert agg["cache"]["complete"] is False
        assert agg["cache"]["hits"] is None

    def test_cache_absent_in_all_rows_keeps_absent_schema(self) -> None:
        agg = tu.aggregate_row_token_usage(_rows({"total_tokens": 110, "input_tokens": 100, "output_tokens": 10}))
        assert agg["cache"]["present"] is False
        assert agg["cache"]["reasons"] == {}
        assert agg["cache"]["missing"] == {}

    def test_present_non_object_marks_cache_unreadable(self) -> None:
        agg = tu.aggregate_row_token_usage([{"token_usage": 100}])
        assert agg["cache"]["present"] is True
        assert agg["cache"]["complete"] is False
        assert agg["cache"]["hits"] is None
        assert agg["cache"]["reasons"] == {"token_usage_not_object:int": 1}


class TestRunBenchmarkTokenMetrics:
    """AN：写盘 `token_metrics` 的读数与披露面。"""

    def test_clean_rows_reading_unchanged(self) -> None:
        got = rb._aggregate_token_metrics(_two_clean_rows())
        assert got["total_input_tokens"] == 300
        assert got["total_output_tokens"] == 150
        assert got["total_tokens"] == 450
        assert got["total_llm_calls"] == 5
        assert got["total_cache_hits"] == 1
        assert got["total_cache_avoided_tokens"] == 30
        assert got["cache_hit_rate_pct"] == round(1 / 6 * 100, 2)
        assert got["uncached_theoretical_tokens"] == 480
        assert got["avg_tokens_per_task"] == 225.0
        assert got["output_share_pct"] == 33.33
        assert got["avg_output_per_task"] == 75.0
        assert got["avg_output_per_call"] == 30.0
        assert all(key not in got for key in _DISCLOSURE_KEYS)

    def test_non_object_usage_is_none_not_attribute_error(self) -> None:
        got = rb._aggregate_token_metrics([{"token_usage": "100"}])
        assert got["total_input_tokens"] is None
        assert got["total_output_tokens"] is None
        assert got["total_tokens"] is None
        assert got["total_llm_calls"] is None
        assert got["total_cache_hits"] is None
        assert got["cache_hit_rate_pct"] is None
        assert got["uncached_theoretical_tokens"] is None
        assert got["avg_tokens_per_task"] is None
        assert got["n_token_unreadable_rows"] == 1
        assert got["token_reading_reasons"] == {"token_usage_not_object:str": 1}
        assert got["cache_reading_reasons"] == {"token_usage_not_object:str": 1}

    def test_bad_triple_value_blocks_token_numbers_only(self) -> None:
        got = rb._aggregate_token_metrics(_rows({"total_tokens": 11, "input_tokens": True, "output_tokens": 10}))
        assert got["total_input_tokens"] is None
        assert got["total_tokens"] is None
        assert got["avg_tokens_per_task"] is None
        assert got["output_share_pct"] is None
        assert got["avg_output_per_task"] is None
        assert got["avg_output_per_call"] is None
        # 调用 / 缓存是独立事实：本行两者都缺席 → 历史 0
        assert got["total_llm_calls"] == 0
        assert got["total_cache_hits"] == 0
        assert got["cache_hit_rate_pct"] == 0.0
        assert got["token_reading_reasons"] == {"token_not_count:input_tokens:bool": 1}

    def test_split_mismatch_disclosed_with_recorded_total(self) -> None:
        got = rb._aggregate_token_metrics(_rows({"total_tokens": 999, "input_tokens": 100, "output_tokens": 10}))
        assert got["total_input_tokens"] == 100
        assert got["total_output_tokens"] == 10
        assert got["total_tokens"] == 999
        assert got["avg_tokens_per_task"] == 999.0
        assert got["n_token_split_mismatch_rows"] == 1
        assert "n_token_unreadable_rows" not in got

    def test_bad_cache_blocks_cache_numbers_not_tokens(self) -> None:
        got = rb._aggregate_token_metrics(
            _rows(
                {
                    "total_tokens": 110,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "llm_calls": 3,
                    "cache_hits": -1,
                    "cache_avoided_tokens": 0,
                }
            )
        )
        assert got["total_tokens"] == 110
        assert got["total_llm_calls"] == 3
        assert got["total_cache_hits"] is None
        assert got["total_cache_avoided_tokens"] is None
        assert got["cache_hit_rate_pct"] is None
        assert got["uncached_theoretical_tokens"] is None
        assert got["cache_reading_reasons"] == {"token_negative:cache_hits": 1}

    def test_old_schema_rows_without_cache_keep_zero_reading(self) -> None:
        got = rb._aggregate_token_metrics(
            _rows({"total_tokens": 110, "input_tokens": 100, "output_tokens": 10, "llm_calls": 2})
        )
        assert got["total_cache_hits"] == 0
        assert got["total_cache_avoided_tokens"] == 0
        assert got["cache_hit_rate_pct"] == 0.0
        assert got["uncached_theoretical_tokens"] == 110
        assert "cache_reading_reasons" not in got

    def test_real_main_batch_matches_persisted_token_metrics(self) -> None:
        checked_rows = 0
        checked_arms = 0
        for path in _MAIN_BATCH_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            for arm, block in data["results"].items():
                stored = block["token_metrics"]
                details = block["details"]
                got = rb._aggregate_token_metrics(details)
                assert {key: got[key] for key in stored} == stored, arm
                assert all(key not in got for key in _DISCLOSURE_KEYS), arm
                checked_rows += len(details)
                checked_arms += 1
        assert checked_rows == 783
        assert checked_arms == 9


class TestTrustedVerificationMetrics:
    """AN：可信报告不得折叠坏值，也不得隐藏命中率分母。"""

    def test_clean_rows_reading_unchanged(self) -> None:
        m = tv.arm_trusted_metrics(_two_clean_rows())
        assert m["cache_hits"] == 1
        assert m["cache_avoided_tokens"] == 30
        assert m["cache_hit_rate_pct"] == round(1 / 6 * 100, 2)
        assert m["uncached_theoretical_tokens"] == 480
        assert m["llm_calls"] == 5

    def test_non_object_usage_returns_none_not_crash(self) -> None:
        m = tv.arm_trusted_metrics([{"token_usage": "100"}])
        assert m["cache_hits"] is None
        assert m["cache_avoided_tokens"] is None
        assert m["cache_hit_rate_pct"] is None
        assert m["uncached_theoretical_tokens"] is None
        assert m["llm_calls"] is None
        assert m["n_token_unreadable_rows"] == 1
        assert m["token_reading_reasons"] == {"token_usage_not_object:str": 1}

    def test_split_mismatch_uses_recorded_total(self) -> None:
        m = tv.arm_trusted_metrics(_rows({"total_tokens": 999, "input_tokens": 100, "output_tokens": 10}))
        assert m["uncached_theoretical_tokens"] == 999
        assert m["n_token_split_mismatch_rows"] == 1

    def test_bad_cache_blocks_cache_numbers_only(self) -> None:
        m = tv.arm_trusted_metrics(
            _rows(
                {
                    "total_tokens": 110,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "llm_calls": 3,
                    "cache_hits": True,
                    "cache_avoided_tokens": 0,
                }
            )
        )
        assert m["cache_hits"] is None
        assert m["cache_hit_rate_pct"] is None
        assert m["uncached_theoretical_tokens"] is None
        assert m["llm_calls"] == 3

    def test_cli_prints_real_call_denominator(self, tmp_path: Path, capsys, monkeypatch) -> None:
        batch = {
            "results": {
                "arm": {
                    "details": [
                        {
                            "token_usage": {
                                "total_tokens": 100,
                                "input_tokens": 60,
                                "output_tokens": 40,
                                "llm_calls": 4,
                                "cache_hits": 1,
                                "cache_avoided_tokens": 30,
                            }
                        }
                    ]
                }
            }
        }
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(batch), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["trusted_verification", "--batch", str(path)])
        tv.main()
        out = capsys.readouterr().out
        assert "命中 1 / 真实调用 4" in out


class TestRagAnalysisFallback:
    """AN：旧批次兜底的逐任务累加同样走共享读取器。"""

    def test_clean_rows_five_key_contract(self) -> None:
        got = _token_metrics_from_details(_two_clean_rows())
        assert got["total_input_tokens"] == 300
        assert got["total_output_tokens"] == 150
        assert got["total_tokens"] == 450
        assert got["total_llm_calls"] == 5
        assert got["avg_tokens_per_task"] == 225.0
        assert all(key not in got for key in _DISCLOSURE_KEYS)

    def test_unreadable_returns_none_with_disclosure(self) -> None:
        got = _token_metrics_from_details([{"token_usage": "100"}])
        assert got["total_input_tokens"] is None
        assert got["total_tokens"] is None
        assert got["total_llm_calls"] is None
        assert got["avg_tokens_per_task"] is None
        assert got["n_token_unreadable_rows"] == 1
        assert got["token_reading_reasons"] == {"token_usage_not_object:str": 1}

    def test_split_mismatch_disclosed_total_still_recorded(self) -> None:
        got = _token_metrics_from_details(
            [{"token_usage": {"total_tokens": 999, "input_tokens": 100, "output_tokens": 10}}]
        )
        assert got["total_tokens"] == 999
        assert got["n_token_split_mismatch_rows"] == 1

    def test_absent_rows_historical_zero(self) -> None:
        got = _token_metrics_from_details([{"passed": True}])
        assert got["total_tokens"] == 0
        assert got["avg_tokens_per_task"] == 0
        assert all(key not in got for key in _DISCLOSURE_KEYS)
