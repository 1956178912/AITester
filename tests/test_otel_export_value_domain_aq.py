"""AQ（2026-10-21）otel_export 数值导出值域回归锁。

缺陷族：`_record_to_span` 在导出边界对数值不做值域判定——
- token 三元组把 bool / 字符串 / 小数 / 负数 / NaN / Inf / 容器原样写进
  `gen_ai.usage.*`（GenAI 语义约定要求整数；NaN/Inf 不是合法 OTLP JSON 数值）；
- `ts` / `duration_ms` 为非有限 float 时 `int()` 抛异常，**整文件导出中止**，
  而损坏 JSONL 行却是跳过的——同类坏数据两种命运；
- 非对象 `token_usage` 静默降级为"没有 token 属性"，读不动与缺席不可区分；
- `budget_remaining` / `iteration` 同样不设防。

锁定口径：
1. token 计数复用 `src.budget.token_usage.count_reason`（非负整数；bool 不认）；
2. 时间戳 / duration / budget_remaining 只接受有限非负数，坏值回落既有 0 哨兵
   并披露（不再抛异常）；iteration 是计数，同 `count_reason`；
3. 坏值不导出原值，机制名按处理顺序（ts → duration → token → budget →
   iteration）逗号拼进 `aitester.export_value_reasons`；
4. `token_usage` 缺席 / null 是历史缺席（无属性、无披露），非对象才是读不动；
5. 干净记录逐字不变（真实 trace 全量 129058 span 零披露、token 属性全 int）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.observability.otel_export import (
    _VALUE_REASONS_ATTRIBUTE,
    _numeric_attribute,
    _record_to_span,
    _timestamp_ns,
    _token_attributes,
    export_trace_jsonl,
)
from tests._corpus_guard import require_full_corpus

TRACE = "t" * 32
BASE = {"event": "node", "node": "n1", "ts": 1.5, "duration_ms": 2.0, "span_id": "b" * 16}
TOKEN_KEYS = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens",
)


def _span(**overrides):
    record = dict(BASE)
    record.update(overrides)
    span = _record_to_span(record, "root", TRACE)
    assert span is not None
    return span


def _reasons(span) -> list[str]:
    value = span["attributes"].get(_VALUE_REASONS_ATTRIBUTE)
    return [] if value is None else value.split(",")


class TestTokenValueDomain:
    def test_clean_triple_exported(self):
        span = _span(token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30})
        assert span["attributes"]["gen_ai.usage.input_tokens"] == 10
        assert span["attributes"]["gen_ai.usage.output_tokens"] == 20
        assert span["attributes"]["gen_ai.usage.total_tokens"] == 30
        assert _reasons(span) == []

    def test_absent_token_usage_is_historical_absence(self):
        span = _span()
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _VALUE_REASONS_ATTRIBUTE not in span["attributes"]

    def test_null_token_usage_is_historical_absence(self):
        span = _span(token_usage=None)
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _VALUE_REASONS_ATTRIBUTE not in span["attributes"]

    def test_partial_dict_exports_present_fields_only(self):
        span = _span(token_usage={"input_tokens": 10})
        assert span["attributes"]["gen_ai.usage.input_tokens"] == 10
        assert "gen_ai.usage.output_tokens" not in span["attributes"]
        assert "gen_ai.usage.total_tokens" not in span["attributes"]
        assert _reasons(span) == []

    def test_present_none_field_is_unreadable(self):
        span = _span(token_usage={"input_tokens": None, "output_tokens": 20, "total_tokens": 30})
        assert "gen_ai.usage.input_tokens" not in span["attributes"]
        assert span["attributes"]["gen_ai.usage.output_tokens"] == 20
        assert _reasons(span) == ["token_not_count:input_tokens:NoneType"]

    def test_bool_is_not_a_count(self):
        span = _span(token_usage={"input_tokens": True, "output_tokens": False, "total_tokens": True})
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _reasons(span) == [
            "token_not_count:input_tokens:bool",
            "token_not_count:output_tokens:bool",
            "token_not_count:total_tokens:bool",
        ]

    def test_string_count_rejected(self):
        span = _span(token_usage={"input_tokens": "10", "output_tokens": "20", "total_tokens": "30"})
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _reasons(span) == [
            "token_not_count:input_tokens:str",
            "token_not_count:output_tokens:str",
            "token_not_count:total_tokens:str",
        ]

    def test_finite_float_rejected(self):
        span = _span(token_usage={"input_tokens": 10.0, "output_tokens": 20.5, "total_tokens": 30.0})
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _reasons(span) == [
            "token_not_count:input_tokens:float",
            "token_not_count:output_tokens:float",
            "token_not_count:total_tokens:float",
        ]

    def test_negative_rejected(self):
        span = _span(token_usage={"input_tokens": -1, "output_tokens": 20, "total_tokens": -19})
        assert "gen_ai.usage.input_tokens" not in span["attributes"]
        assert span["attributes"]["gen_ai.usage.output_tokens"] == 20
        assert "gen_ai.usage.total_tokens" not in span["attributes"]
        assert _reasons(span) == ["token_negative:input_tokens", "token_negative:total_tokens"]

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_rejected(self, value):
        span = _span(token_usage={"input_tokens": value, "output_tokens": 20, "total_tokens": 30})
        assert "gen_ai.usage.input_tokens" not in span["attributes"]
        assert _reasons(span) == ["token_not_finite:input_tokens"]

    @pytest.mark.parametrize("value", [[1], {"a": 1}, (1, 2)])
    def test_container_rejected(self, value):
        span = _span(token_usage={"input_tokens": value, "output_tokens": 20, "total_tokens": 30})
        assert "gen_ai.usage.input_tokens" not in span["attributes"]
        assert _reasons(span) == [f"token_not_count:input_tokens:{type(value).__name__}"]

    @pytest.mark.parametrize("value", ["not-a-dict", [1, 2], 7, True])
    def test_non_object_token_usage_is_disclosed(self, value):
        span = _span(token_usage=value)
        assert all(key not in span["attributes"] for key in TOKEN_KEYS)
        assert _reasons(span) == [f"token_usage_not_object:{type(value).__name__}"]

    def test_bad_field_does_not_poison_siblings(self):
        span = _span(token_usage={"input_tokens": 10, "output_tokens": -1, "total_tokens": 30})
        assert span["attributes"]["gen_ai.usage.input_tokens"] == 10
        assert span["attributes"]["gen_ai.usage.total_tokens"] == 30
        assert "gen_ai.usage.output_tokens" not in span["attributes"]
        assert _reasons(span) == ["token_negative:output_tokens"]


class TestTimestampValueDomain:
    def test_float_ts_and_duration_conversion(self):
        span = _span(ts=1.5, duration_ms=2.0)
        assert span["start_time_unix_nano"] == 1_500_000_000
        assert span["duration_unix_nano"] == 2_000_000
        assert _reasons(span) == []

    def test_int_ts_and_duration_conversion(self):
        span = _span(ts=1, duration_ms=2)
        assert span["start_time_unix_nano"] == 1_000_000_000
        assert span["duration_unix_nano"] == 2_000_000
        assert _reasons(span) == []

    def test_absent_ts_and_duration_are_zero_without_reason(self):
        span = _span(ts=None, duration_ms=None)
        assert span["start_time_unix_nano"] == 0
        assert span["duration_unix_nano"] == 0
        assert _reasons(span) == []

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_ts_falls_back_to_zero(self, value):
        span = _span(ts=value)
        assert span["start_time_unix_nano"] == 0
        assert _reasons(span) == ["ts_not_finite"]

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_duration_falls_back_to_zero(self, value):
        span = _span(duration_ms=value)
        assert span["duration_unix_nano"] == 0
        assert _reasons(span) == ["duration_ms_not_finite"]

    def test_negative_ts_and_duration_rejected(self):
        span = _span(ts=-1.0, duration_ms=-2.0)
        assert span["start_time_unix_nano"] == 0
        assert span["duration_unix_nano"] == 0
        assert _reasons(span) == ["ts_negative", "duration_ms_negative"]

    def test_bool_ts_and_duration_rejected(self):
        span = _span(ts=True, duration_ms=False)
        assert span["start_time_unix_nano"] == 0
        assert span["duration_unix_nano"] == 0
        assert _reasons(span) == ["ts_not_number:bool", "duration_ms_not_number:bool"]

    @pytest.mark.parametrize("value", ["1.5", [1.5], {"v": 1.5}])
    def test_non_number_ts_reported_by_type(self, value):
        span = _span(ts=value)
        assert span["start_time_unix_nano"] == 0
        assert _reasons(span) == [f"ts_not_number:{type(value).__name__}"]

    def test_out_of_range_ts_does_not_overflow(self):
        span = _span(ts=1e308)
        assert span["start_time_unix_nano"] == 0
        assert _reasons(span) == ["ts_out_of_range"]

    def test_huge_int_ts_does_not_overflow(self):
        span = _span(ts=10**400)
        assert span["start_time_unix_nano"] == 0
        assert _reasons(span) == ["ts_out_of_range"]

    def test_nan_timestamp_does_not_abort_export(self, tmp_path):
        path = tmp_path / "nan.trace.jsonl"
        path.write_text(
            json.dumps({"event": "task_start", "ts": math.nan, "run_id": "a" * 32, "span_id": "a" * 16})
            + "\n"
            + json.dumps({"event": "node", "node": "n1", "ts": math.inf, "duration_ms": math.nan})
            + "\n",
            encoding="utf-8",
        )
        spans = export_trace_jsonl(str(path))
        assert [s["name"] for s in spans] == ["task_task_start", "n1"]
        assert spans[0]["start_time_unix_nano"] == 0
        assert spans[1]["start_time_unix_nano"] == 0
        assert spans[1]["duration_unix_nano"] == 0
        assert _reasons(spans[1]) == ["ts_not_finite", "duration_ms_not_finite"]


class TestNumericCustomAttributes:
    def test_budget_remaining_int_and_float_exported(self):
        assert _span(budget_remaining=999)["attributes"]["aitester.budget_remaining"] == 999
        assert _span(budget_remaining=12.5)["attributes"]["aitester.budget_remaining"] == 12.5

    def test_zero_budget_remaining_exported(self):
        span = _span(budget_remaining=0)
        assert span["attributes"]["aitester.budget_remaining"] == 0
        assert _reasons(span) == []

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (True, "budget_remaining_not_number:bool"),
            ("999", "budget_remaining_not_number:str"),
            (-1, "budget_remaining_negative"),
            (math.nan, "budget_remaining_not_finite"),
            (math.inf, "budget_remaining_not_finite"),
        ],
    )
    def test_bad_budget_remaining_omitted_and_disclosed(self, value, reason):
        span = _span(budget_remaining=value)
        assert "aitester.budget_remaining" not in span["attributes"]
        assert _reasons(span) == [reason]

    def test_iteration_count_exported(self):
        span = _span(iteration=3)
        assert span["attributes"]["aitester.iteration"] == 3
        assert _reasons(span) == []

    def test_zero_iteration_exported(self):
        assert _span(iteration=0)["attributes"]["aitester.iteration"] == 0

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            (True, "token_not_count:iteration:bool"),
            (3.0, "token_not_count:iteration:float"),
            ("3", "token_not_count:iteration:str"),
            (-1, "token_negative:iteration"),
        ],
    )
    def test_bad_iteration_omitted_and_disclosed(self, value, reason):
        span = _span(iteration=value)
        assert "aitester.iteration" not in span["attributes"]
        assert _reasons(span) == [reason]

    def test_absent_numeric_attributes_have_no_reason(self):
        span = _span()
        assert "aitester.budget_remaining" not in span["attributes"]
        assert "aitester.iteration" not in span["attributes"]
        assert _VALUE_REASONS_ATTRIBUTE not in span["attributes"]


class TestReasonAggregation:
    def test_reason_order_follows_processing_order(self):
        span = _span(
            ts=math.nan,
            duration_ms=-1,
            token_usage={"input_tokens": "10", "output_tokens": 20, "total_tokens": 30},
            budget_remaining=-1,
            iteration=True,
        )
        assert _reasons(span) == [
            "ts_not_finite",
            "duration_ms_negative",
            "token_not_count:input_tokens:str",
            "budget_remaining_negative",
            "token_not_count:iteration:bool",
        ]

    def test_clean_record_has_no_reason_attribute(self):
        span = _span(
            token_usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            budget_remaining=10,
            iteration=1,
        )
        assert _VALUE_REASONS_ATTRIBUTE not in span["attributes"]

    def test_reasons_attribute_is_a_string(self):
        span = _span(ts=math.nan)
        assert isinstance(span["attributes"][_VALUE_REASONS_ATTRIBUTE], str)


class TestHelperUnits:
    def test_token_attributes_helper_shape(self):
        attrs, reasons = _token_attributes({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
        assert attrs == {
            "gen_ai.usage.input_tokens": 1,
            "gen_ai.usage.output_tokens": 2,
            "gen_ai.usage.total_tokens": 3,
        }
        assert reasons == []

    def test_timestamp_helper_scales(self):
        assert _timestamp_ns(2.0, 1e9, "ts") == (2_000_000_000, [])
        assert _timestamp_ns(2.0, 1e6, "duration_ms") == (2_000_000, [])

    def test_numeric_attribute_helper_shape(self):
        assert _numeric_attribute(5, "f") == (5, None)
        assert _numeric_attribute(None, "f") == (None, None)
        assert _numeric_attribute(math.nan, "f") == (None, "f_not_finite")


class TestExportEndToEnd:
    def test_bad_values_are_json_serializable_without_nan(self, tmp_path):
        path = tmp_path / "bad.trace.jsonl"
        path.write_text(
            json.dumps(
                {
                    "event": "task_end",
                    "ts": math.nan,
                    "duration_ms": math.inf,
                    "run_id": "a" * 32,
                    "span_id": "a" * 16,
                    "token_usage": {"input_tokens": math.nan, "output_tokens": "20", "total_tokens": True},
                    "budget_remaining": math.inf,
                    "iteration": "1",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        spans = export_trace_jsonl(str(path))
        # allow_nan=False：NaN/Inf 若泄漏会直接抛 ValueError
        payload = json.dumps(spans, allow_nan=False)
        assert "export_value_reasons" in payload

    def test_clean_export_has_no_disclosure_attribute(self, tmp_path):
        path = tmp_path / "clean.trace.jsonl"
        records = [
            {"event": "task_start", "ts": 1.0, "run_id": "a" * 32, "span_id": "a" * 16},
            {"event": "node", "node": "n1", "ts": 2.0, "duration_ms": 3.0, "iteration": 1},
            {
                "event": "task_end",
                "ts": 3.0,
                "run_id": "a" * 32,
                "span_id": "b" * 16,
                "token_usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            },
        ]
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        spans = export_trace_jsonl(str(path))
        assert all(_VALUE_REASONS_ATTRIBUTE not in s["attributes"] for s in spans)

    def test_real_traces_have_zero_disclosures_and_clean_types(self):
        # BZ 轮：spans 总数（129058）与零披露结论以全归档 trace 语料为扫描面
        # ——fresh clone 只有入库子集 ⇒ require_full_corpus 显式 skip 并带
        # 实测读数（tests/_corpus_guard.py）。
        require_full_corpus()
        root = Path(__file__).resolve().parents[1]
        files = sorted(root.rglob("*.trace.jsonl"))
        assert files, "真实 trace 语料缺失"
        spans = 0
        token_attrs = 0
        for path in files:
            for span in export_trace_jsonl(str(path)):
                spans += 1
                attrs = span["attributes"]
                assert _VALUE_REASONS_ATTRIBUTE not in attrs, path
                for key in TOKEN_KEYS:
                    if key in attrs:
                        token_attrs += 1
                        assert type(attrs[key]) is int, (path, key)
                        assert attrs[key] >= 0, (path, key)
                assert type(span["start_time_unix_nano"]) is int, path
                assert span["start_time_unix_nano"] >= 0, path
                assert type(span["duration_unix_nano"]) is int, path
                assert span["duration_unix_nano"] >= 0, path
        assert spans == 129058
        assert token_attrs == 27135

    def test_real_token_attributes_match_raw_task_end_records(self):
        # BZ 轮：checked 下界（27000）以全归档 trace 语料为扫描面——同
        # test_real_traces_have_zero_disclosures_and_clean_types 的显式 skip 口径。
        require_full_corpus()
        root = Path(__file__).resolve().parents[1]
        checked = 0
        for path in sorted(root.rglob("*.trace.jsonl")):
            raw_tokens = {}
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and isinstance(record.get("token_usage"), dict):
                    raw_tokens = record["token_usage"]
            if not raw_tokens:
                continue
            end_span = next((s for s in export_trace_jsonl(str(path)) if s["name"] == "task_task_end"), None)
            assert end_span is not None, path
            for field, key in zip(("input_tokens", "output_tokens", "total_tokens"), TOKEN_KEYS, strict=True):
                if field in raw_tokens:
                    assert end_span["attributes"][key] == raw_tokens[field], (path, field)
                    checked += 1
        assert checked >= 27000
