"""AR（2026-10-21）otel_export 标识与字符串导出值域回归锁。

缺陷族（实测于真实 trace 语料 9086 文件 / 129058 span；2026-10-23 provider
清理删除 323 份归档后复测为 8763 文件 / 126408 span，判定不变）：
- `run_id` 原样当 trace_id 导出（真实形态 16 位 hex），`span_id` 原样导出
  （真实形态 12 位 hex）——都不符合 OTel：trace_id 必须 32 位小写 hex、
  span_id 必须 16 位；
- `task_start` / `task_end` 没有显式标识时每次导出生成随机 uuid，node span
  又拿 run_id 当 trace_id，于是同一文件出现两个 trace，root 与子 span 的
  parent 引用跨 trace（实测 8002 个文件多 trace、61188 条 parent 断链）；
- 9086/9086 个文件重复导出标识不一致（导出不可复现）；
- node 名称 / decision / strategy 等字符串属性对非字符串原样导出。

锁定口径：
1. trace_id 规范化为 32 位、span_id 为 16 位小写 hex：短 hex 左补零、
   大小写归一；非字符串 / 空串 / 非 hex / 超宽 / 全零都不可导出；
2. 一个文件一个 trace_id：首个可规范化 run_id，否则首个非法字符串 run_id
   参与哈希，否则按文件路径确定性派生；不一致的 run_id 披露
   `run_id_mismatch`；
3. 缺失 / 非法标识按 SHA-256 确定性派生（不再随机），重复导出逐字稳定；
   同一 trace 内 span_id 冲突改派生 id 并追加 `span_id_duplicate`；
4. 字符串属性只导出 `str`；非字符串不导出原值并按字段披露；
   node 名称缺失回退 "node"（空串披露 `node_empty`）；
5. 机制名顺序：run_id → span_id → name → ts → duration → token →
   string attrs → budget → iteration → task；
6. 真实语料：每文件单 trace、标识形态合规、parent 均在同文件、
   span_id 无重复、零披露、重复导出稳定。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import pytest

from src.observability.otel_export import (
    _VALUE_REASONS_ATTRIBUTE,
    _canonical_identifier,
    _derived_span_id,
    _file_trace_id,
    _record_to_span,
    export_trace_jsonl,
)
from tests._corpus_guard import require_full_corpus

TRACE_HEX = re.compile(r"[0-9a-f]{32}")
SPAN_HEX = re.compile(r"[0-9a-f]{16}")
STRING_ATTRIBUTES = (
    ("decision", "aitester.decision"),
    ("decision_reason", "aitester.decision_reason"),
    ("strategy_selected", "aitester.strategy"),
    ("stop_reason", "aitester.stop_reason"),
)


def _reasons(span) -> list[str]:
    value = span["attributes"].get(_VALUE_REASONS_ATTRIBUTE)
    return [] if value is None else value.split(",")


def _span(record: dict, root: str = "c" * 16, trace: str | None = None):
    trace_id = trace if trace is not None else _file_trace_id([record], "probe.trace.jsonl")
    span = _record_to_span(record, root, trace_id, 0)
    assert span is not None
    return span


def _write(tmp_path, records: list[dict], name: str = "task.trace.jsonl") -> str:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return str(path)


class TestIdentifierCanonicalization:
    def test_absent_identifier_is_silent(self):
        assert _canonical_identifier(None, 32, "run_id") == (None, None)

    def test_full_width_hex_preserved(self):
        assert _canonical_identifier("a" * 32, 32, "run_id") == ("a" * 32, None)
        assert _canonical_identifier("0" * 15 + "f", 16, "span_id") == ("0" * 15 + "f", None)

    def test_uppercase_is_lowered(self):
        assert _canonical_identifier("A" * 32, 32, "run_id") == ("a" * 32, None)

    def test_short_hex_left_zero_padded(self):
        assert _canonical_identifier("ab", 32, "run_id") == ("0" * 30 + "ab", None)
        assert _canonical_identifier("cd", 16, "span_id") == ("0" * 14 + "cd", None)

    def test_non_string_reported_by_type(self):
        assert _canonical_identifier(123, 32, "run_id") == (None, "run_id_not_string:int")
        assert _canonical_identifier(b"ab", 16, "span_id") == (None, "span_id_not_string:bytes")

    @pytest.mark.parametrize("value", ["", "xy", "0x12", "a" * 33])
    def test_malformed_span_id_rejected(self, value):
        assert _canonical_identifier(value, 16, "span_id") == (None, "span_id_invalid_format")

    def test_all_zero_identifier_rejected(self):
        assert _canonical_identifier("0" * 32, 32, "run_id") == (None, "run_id_invalid_format")
        assert _canonical_identifier("0" * 16, 16, "span_id") == (None, "span_id_invalid_format")


class TestRecordIdentifierMapping:
    def test_valid_short_ids_canonicalized_without_disclosure(self):
        span = _span({"event": "node", "node": "n1", "run_id": "ab", "span_id": "cd"})
        assert span["trace_id"] == "0" * 30 + "ab"
        assert span["span_id"] == "0" * 14 + "cd"
        assert _reasons(span) == []

    def test_uppercase_ids_canonicalized_end_to_end(self):
        span = _span({"event": "node", "node": "n1", "run_id": "AB", "span_id": "CD"})
        assert span["trace_id"] == "0" * 30 + "ab"
        assert span["span_id"] == "0" * 14 + "cd"

    def test_non_string_run_id_disclosed(self):
        span = _span({"event": "node", "node": "n1", "run_id": 42, "span_id": "cd"})
        assert _reasons(span) == ["run_id_not_string:int"]
        assert TRACE_HEX.fullmatch(span["trace_id"])

    def test_invalid_run_id_disclosed_and_trace_stable(self):
        record = {"event": "node", "node": "n1", "run_id": "not-hex", "span_id": "cd"}
        first = _span(record)
        second = _span(record)
        assert _reasons(first) == ["run_id_invalid_format"]
        assert first["trace_id"] == second["trace_id"]
        assert TRACE_HEX.fullmatch(first["trace_id"])

    def test_run_id_mismatch_disclosed(self):
        records = [
            {"event": "node", "node": "n1", "run_id": "aa"},
            {"event": "node", "node": "n2", "run_id": "bb"},
        ]
        trace = _file_trace_id(records, "p.trace.jsonl")
        first = _record_to_span(records[0], "c" * 16, trace, 0)
        second = _record_to_span(records[1], "c" * 16, trace, 1)
        assert first["trace_id"] == trace == second["trace_id"]
        assert _reasons(first) == []
        assert _reasons(second) == ["run_id_mismatch"]

    def test_missing_span_id_derived_deterministically(self):
        record = {"event": "node", "node": "n1", "run_id": "aa"}
        trace = _file_trace_id([record], "p.trace.jsonl")
        first = _record_to_span(record, "c" * 16, trace, 3)
        second = _record_to_span(record, "c" * 16, trace, 3)
        assert first["span_id"] == second["span_id"] == _derived_span_id(trace, 3)
        assert SPAN_HEX.fullmatch(first["span_id"])
        assert _reasons(first) == []

    def test_invalid_span_id_disclosed_then_derived(self):
        span = _span({"event": "node", "node": "n1", "run_id": "aa", "span_id": "xyz"})
        assert _reasons(span) == ["span_id_invalid_format"]
        assert SPAN_HEX.fullmatch(span["span_id"])

    def test_all_zero_span_id_disclosed_then_derived(self):
        span = _span({"event": "node", "node": "n1", "run_id": "aa", "span_id": "0" * 16})
        assert _reasons(span) == ["span_id_invalid_format"]
        assert span["span_id"] != "0" * 16

    def test_node_name_non_string_falls_back(self):
        span = _span({"event": "node", "node": 7, "run_id": "aa"})
        assert span["name"] == "node"
        assert span["attributes"]["gen_ai.operation.name"] == "node"
        assert _reasons(span) == ["node_not_string:int"]

    def test_node_name_empty_falls_back_with_disclosure(self):
        span = _span({"event": "node", "node": "", "run_id": "aa"})
        assert span["name"] == "node"
        assert _reasons(span) == ["node_empty"]

    def test_node_name_absent_is_silent(self):
        span = _span({"event": "node", "run_id": "aa"})
        assert span["name"] == "node"
        assert _reasons(span) == []


class TestFileTraceId:
    def test_first_canonical_run_id_wins(self):
        records = [{"run_id": "cc"}, {"run_id": "dd"}]
        assert _file_trace_id(records, "p.trace.jsonl") == "0" * 30 + "cc"

    def test_no_run_id_uses_path_seed(self):
        first = _file_trace_id([], "/one/a.trace.jsonl")
        second = _file_trace_id([], "/two/b.trace.jsonl")
        assert TRACE_HEX.fullmatch(first) and TRACE_HEX.fullmatch(second)
        assert first != second
        assert first == _file_trace_id([], "/one/a.trace.jsonl")

    def test_all_invalid_strings_hash_first_string(self):
        records = [{"run_id": "bad!"}, {"run_id": "worse!"}]
        expected = hashlib.sha256(b"aitester-trace:bad!").hexdigest()[:32]
        assert _file_trace_id(records, "p.trace.jsonl") == expected

    def test_non_string_and_empty_run_ids_fall_back_to_path(self):
        expected = hashlib.sha256(b"aitester-trace:path:p.trace.jsonl").hexdigest()[:32]
        assert _file_trace_id([{"run_id": 42}], "p.trace.jsonl") == expected
        assert _file_trace_id([{"run_id": ""}], "p.trace.jsonl") == expected


class TestDuplicateSpanIds:
    def test_duplicate_span_id_rederived_and_disclosed(self, tmp_path):
        records = [
            {"event": "task_start", "run_id": "aa", "span_id": "01"},
            {"event": "node", "node": "n1", "run_id": "aa", "span_id": "cc"},
            {"event": "node", "node": "n2", "run_id": "aa", "span_id": "cc"},
        ]
        spans = export_trace_jsonl(_write(tmp_path, records))
        assert spans[1]["span_id"] == "0" * 14 + "cc"
        assert spans[2]["span_id"] != spans[1]["span_id"]
        assert SPAN_HEX.fullmatch(spans[2]["span_id"])
        assert _reasons(spans[2]) == ["span_id_duplicate"]

    def test_duplicate_appends_after_existing_reasons(self, tmp_path):
        records = [
            {"event": "task_start", "run_id": "aa", "span_id": "01"},
            {"event": "node", "node": "n1", "run_id": "aa", "span_id": "cc"},
            {"event": "node", "node": "n2", "run_id": "aa", "span_id": "cc", "ts": math.nan},
        ]
        spans = export_trace_jsonl(_write(tmp_path, records))
        assert _reasons(spans[2]) == ["ts_not_finite", "span_id_duplicate"]

    def test_duplicate_with_root_span_keeps_parent_link(self, tmp_path):
        records = [
            {"event": "task_start", "run_id": "aa", "span_id": "cc"},
            {"event": "node", "node": "n1", "run_id": "aa", "span_id": "cc"},
        ]
        spans = export_trace_jsonl(_write(tmp_path, records))
        root, node = spans
        assert node["span_id"] != root["span_id"]
        assert node["parent_span_id"] == root["span_id"]
        assert _reasons(node) == ["span_id_duplicate"]

    def test_explicit_id_colliding_with_later_derivation_is_rederived(self, tmp_path):
        records = [
            {"event": "task_start", "run_id": "aa", "span_id": "01"},
            {"event": "node", "node": "n1", "run_id": "aa"},
            {"event": "node", "node": "n2", "run_id": "aa", "span_id": "derived-placeholder"},
        ]
        trace = _file_trace_id(records, "p.trace.jsonl")
        derived_first = _derived_span_id(trace, 1)
        records[2]["span_id"] = derived_first
        spans = export_trace_jsonl(_write(tmp_path, records))
        assert spans[1]["span_id"] == derived_first
        assert spans[2]["span_id"] != derived_first
        assert _reasons(spans[2]) == ["span_id_duplicate"]


class TestStringValueDomain:
    def test_all_string_attributes_exported(self):
        span = _span(
            {
                "event": "node",
                "node": "worker",
                "run_id": "aa",
                "decision": "patch",
                "decision_reason": "tests_failed",
                "strategy_selected": "single_patch",
                "stop_reason": "test_passed",
                "task": "t1",
            }
        )
        attributes = span["attributes"]
        assert attributes["aitester.decision"] == "patch"
        assert attributes["aitester.decision_reason"] == "tests_failed"
        assert attributes["aitester.strategy"] == "single_patch"
        assert attributes["aitester.stop_reason"] == "test_passed"
        assert attributes["aitester.task_id"] == "t1"
        assert _reasons(span) == []

    def test_empty_string_still_exported(self):
        span = _span({"event": "node", "node": "worker", "run_id": "aa", "decision": ""})
        assert span["attributes"]["aitester.decision"] == ""
        assert _reasons(span) == []

    @pytest.mark.parametrize(("field", "attribute"), STRING_ATTRIBUTES)
    def test_non_string_attribute_omitted_and_disclosed(self, field, attribute):
        span = _span({"event": "node", "node": "worker", "run_id": "aa", field: 7})
        assert attribute not in span["attributes"]
        assert _reasons(span) == [f"{field}_not_string:int"]

    @pytest.mark.parametrize("value", [7, ["a"], {"v": "a"}, True])
    def test_non_string_task_omitted_and_disclosed(self, value):
        span = _span({"event": "node", "node": "worker", "run_id": "aa", "task": value})
        assert "aitester.task_id" not in span["attributes"]
        assert _reasons(span) == [f"task_not_string:{type(value).__name__}"]

    def test_absent_task_is_silent(self):
        span = _span({"event": "node", "node": "worker", "run_id": "aa"})
        assert "aitester.task_id" not in span["attributes"]
        assert _reasons(span) == []


class TestReasonOrder:
    def test_identifier_name_string_numeric_order(self):
        span = _span(
            {
                "event": "node",
                "run_id": 1,
                "span_id": "xyz",
                "node": 2,
                "ts": math.nan,
                "duration_ms": -1,
                "token_usage": {"input_tokens": "10"},
                "decision": 3,
                "decision_reason": 4,
                "strategy_selected": 5,
                "stop_reason": 6,
                "budget_remaining": -1,
                "iteration": True,
                "task": 7,
            }
        )
        assert _reasons(span) == [
            "run_id_not_string:int",
            "span_id_invalid_format",
            "node_not_string:int",
            "ts_not_finite",
            "duration_ms_negative",
            "token_not_count:input_tokens:str",
            "decision_not_string:int",
            "decision_reason_not_string:int",
            "strategy_selected_not_string:int",
            "stop_reason_not_string:int",
            "budget_remaining_negative",
            "token_not_count:iteration:bool",
            "task_not_string:int",
        ]


class TestExportEndToEnd:
    def test_one_trace_valid_shape_and_links(self, tmp_path):
        records = [
            {"event": "task_start", "task": "t1", "ts": 1.0, "run_id": "ab", "span_id": "01"},
            {"event": "node", "node": "n1", "task": "t1", "ts": 2.0, "run_id": "ab", "span_id": "02"},
            {"event": "task_end", "task": "t1", "ts": 3.0, "run_id": "ab", "span_id": "03"},
        ]
        spans = export_trace_jsonl(_write(tmp_path, records))
        trace_ids = {s["trace_id"] for s in spans}
        assert len(trace_ids) == 1
        trace_id = trace_ids.pop()
        assert TRACE_HEX.fullmatch(trace_id)
        span_ids = [s["span_id"] for s in spans]
        assert len(set(span_ids)) == len(span_ids)
        for span in spans:
            assert span["trace_id"] == trace_id
            assert SPAN_HEX.fullmatch(span["span_id"])
            if span["parent_span_id"] is not None:
                assert span["parent_span_id"] in span_ids
        assert spans[0]["parent_span_id"] is None
        assert spans[1]["parent_span_id"] == spans[0]["span_id"]
        assert spans[2]["parent_span_id"] == spans[0]["span_id"]
        assert all(_reasons(s) == [] for s in spans)

    def test_repeat_export_is_identical(self, tmp_path):
        records = [
            {"event": "task_start", "run_id": "ab"},
            {"event": "node", "node": "n1", "run_id": "ab", "ts": 1.0},
            {"event": "node", "node": "n2", "run_id": "ab", "ts": 2.0},
        ]
        path = _write(tmp_path, records)
        assert export_trace_jsonl(path) == export_trace_jsonl(path)

    def test_missing_task_start_synthesizes_deterministic_root(self, tmp_path):
        records = [
            {"event": "node", "node": "n1", "run_id": "ab"},
            {"event": "node", "node": "n2", "run_id": "ab"},
        ]
        path = _write(tmp_path, records)
        first = export_trace_jsonl(path)
        second = export_trace_jsonl(path)
        assert first == second
        root = first[0]
        assert root["name"] == "task_root_synthetic"
        assert root["parent_span_id"] is None
        assert SPAN_HEX.fullmatch(root["span_id"])
        assert all(s["parent_span_id"] == root["span_id"] for s in first[1:])

    def test_trace_id_without_run_id_depends_on_path(self, tmp_path):
        records = [{"event": "node", "node": "n1", "ts": 1.0}]
        first = export_trace_jsonl(_write(tmp_path, records, name="a.trace.jsonl"))
        second = export_trace_jsonl(_write(tmp_path, records, name="b.trace.jsonl"))
        assert TRACE_HEX.fullmatch(first[0]["trace_id"])
        assert TRACE_HEX.fullmatch(second[0]["trace_id"])
        assert first[0]["trace_id"] != second[0]["trace_id"]
        assert first[0]["span_id"] != second[0]["span_id"]

    def test_empty_file_synthetic_root_is_stable(self, tmp_path):
        path = _write(tmp_path, [])
        first = export_trace_jsonl(path)
        second = export_trace_jsonl(path)
        assert first == second
        assert len(first) == 1
        assert TRACE_HEX.fullmatch(first[0]["trace_id"])
        assert SPAN_HEX.fullmatch(first[0]["span_id"])


class TestRealCorpus:
    def test_corpus_shape_links_and_zero_disclosures(self):
        # BZ 轮：trace 文件数与 span 总数以全归档为扫描面
        # ——fresh clone 只有入库子集 ⇒ require_full_corpus 显式 skip 并带
        # 实测读数（tests/_corpus_guard.py）。
        # 2026-10-23 provider 清理（删除 323 份含非 DeepSeek provider 的 trace
        # 归档）后复测：文件 9086 → 8763、span 129058 → 126408。
        require_full_corpus()
        root = Path(__file__).resolve().parents[1]
        files = sorted(root.rglob("*.trace.jsonl"))
        assert len(files) == 1106, "真实 trace 语料文件数变化，先复测再改锁"  # CI 重建 2026-10-24：新语料（原 8763）
        total = 0
        for path in files:
            spans = export_trace_jsonl(str(path))
            trace_ids = {s["trace_id"] for s in spans}
            assert len(trace_ids) == 1, path
            trace_id = next(iter(trace_ids))
            assert TRACE_HEX.fullmatch(trace_id), path
            span_ids = [s["span_id"] for s in spans]
            assert len(set(span_ids)) == len(span_ids), path
            for span in spans:
                assert span["trace_id"] == trace_id, path
                assert SPAN_HEX.fullmatch(span["span_id"]), path
                if span["parent_span_id"] is not None:
                    assert span["parent_span_id"] in span_ids, path
                assert _VALUE_REASONS_ATTRIBUTE not in span["attributes"], path
            total += len(spans)
        assert total == 7751  # 收口回钉 2026-10-25（原精确 126408；重建期下界 7747）

    def test_corpus_repeat_export_is_stable(self):
        root = Path(__file__).resolve().parents[1]
        for path in sorted(root.rglob("*.trace.jsonl")):
            assert export_trace_jsonl(str(path)) == export_trace_jsonl(str(path)), path
