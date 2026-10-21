"""AS（2026-10-21）：TraceSession 生产端标识契约。

背景：AR 轮在导出端补上了 trace_id/span_id 的规范化与派生，但生产端仍写
16 位 `run_id`、12 位 `span_id`，task_start/task_end 完全不带标识，注释承诺
的 parent 字段从未出现。导出端的补零/派生只能掩盖上游缺陷。

本文件锁定：
- 一次会话一个 32 位小写 hex run_id（OTel trace_id 宽度）；
- task_start 是 root（16 位 span_id、无 parent），node/task_end 是它的子 span；
- 每个 node/task_end 的 span_id 唯一且 parent_span_id 指向 root；
- 内存模式（未启用文件追踪）同样产出 root 与完整父子链；
- 生产端 trace 直接导出为单 trace、零披露、两次导出逐字稳定。
"""

from __future__ import annotations

import json
import re

import pytest

from src.observability import trace as trace_mod
from src.observability.otel_export import export_trace_jsonl
from src.observability.trace import (
    TraceSession,
    dump_recent_to,
    memory_buffer_snapshot,
    reset_memory_buffer,
    reset_trace_file_locks,
)

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID = re.compile(r"^[0-9a-f]{16}$")


@pytest.fixture(autouse=True)
def _isolated_trace(monkeypatch):
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    reset_trace_file_locks()
    reset_memory_buffer()
    yield
    reset_trace_file_locks()
    reset_memory_buffer()


def _jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _start_and_children(tmp_path, task: str = "task_as"):
    session = TraceSession(task, trace_directory=str(tmp_path))
    session.record_node("planner")
    session.record_node("executor")
    session.record_task_end(True)
    return _jsonl(tmp_path / f"{task}.trace.jsonl")


def test_task_start_carries_otel_width_identifiers(tmp_path):
    records = _start_and_children(tmp_path)
    start = records[0]
    assert start["event"] == "task_start"
    assert TRACE_ID.fullmatch(start["run_id"]), start["run_id"]
    assert SPAN_ID.fullmatch(start["span_id"]), start["span_id"]
    assert "parent_span_id" not in start


def test_children_share_run_and_point_to_root(tmp_path):
    start, planner, executor, end = _start_and_children(tmp_path)
    assert {start["run_id"], planner["run_id"], executor["run_id"], end["run_id"]} == {start["run_id"]}
    span_ids = [start["span_id"], planner["span_id"], executor["span_id"], end["span_id"]]
    assert len(set(span_ids)) == 4
    for child in (planner, executor, end):
        assert SPAN_ID.fullmatch(child["span_id"]), child["span_id"]
        assert child["parent_span_id"] == start["span_id"]


def test_many_nodes_get_unique_span_ids_under_one_root(tmp_path):
    session = TraceSession("many", trace_directory=str(tmp_path))
    for index in range(32):
        session.record_node(f"n{index}")
    records = _jsonl(tmp_path / "many.trace.jsonl")
    root, *nodes = records
    assert len({node["span_id"] for node in nodes}) == 32
    assert {node["parent_span_id"] for node in nodes} == {root["span_id"]}
    assert root["span_id"] not in {node["span_id"] for node in nodes}


def test_sessions_do_not_share_run_or_root(tmp_path):
    first = _start_and_children(tmp_path, "first")[0]
    second = _start_and_children(tmp_path, "second")[0]
    assert first["run_id"] != second["run_id"]
    assert first["span_id"] != second["span_id"]


def test_memory_only_session_has_root_and_children():
    session = TraceSession("memory_only")
    assert session._enabled is False
    session.record_node("planner")
    session.record_task_end(True)

    assert [record["event"] for record in session.records] == ["task_start", "node", "task_end"]
    root, node, end = session.records
    assert TRACE_ID.fullmatch(root["run_id"])
    assert SPAN_ID.fullmatch(root["span_id"])
    assert "parent_span_id" not in root
    for child in (node, end):
        assert child["run_id"] == root["run_id"]
        assert SPAN_ID.fullmatch(child["span_id"])
        assert child["parent_span_id"] == root["span_id"]
    assert len({root["span_id"], node["span_id"], end["span_id"]}) == 3


def test_task_end_without_result_still_carries_identity(tmp_path):
    session = TraceSession("crash", trace_directory=str(tmp_path))
    session.record_task_end(None)
    root, end = _jsonl(tmp_path / "crash.trace.jsonl")
    assert end["passed"] is None
    assert end["run_id"] == root["run_id"]
    assert SPAN_ID.fullmatch(end["span_id"])
    assert end["parent_span_id"] == root["span_id"]


def test_dump_recent_to_preserves_identifier_chain(tmp_path):
    session = TraceSession("memory_dump")
    session.record_node("planner")
    session.record_task_end(True)
    memory_buffer_snapshot(session.task_id, session.records)

    path = dump_recent_to(str(tmp_path))
    assert path is not None
    records = _jsonl(path)
    root = next(record for record in records if record["event"] == "task_start")
    children = [record for record in records if record.get("event") in ("node", "task_end")]
    assert [record["parent_span_id"] for record in children] == [root["span_id"]] * len(children)
    assert all(record["run_id"] == root["run_id"] for record in children)


def test_identifier_exemption_is_shape_exact():
    upper = "0123456789ABCDEF0123456789ABCDEF"
    too_long = "0" * 33
    redacted = trace_mod._redact_record({"run_id": upper, "note": too_long})
    assert redacted["run_id"] == upper
    assert redacted["note"] == "<REDACTED_KEY>"


def test_identifier_fields_survive_redaction_but_ordinary_hex_does_not():
    run_id = "0123456789abcdef0123456789abcdef"
    span_id = "0123456789abcdef"
    redacted = trace_mod._redact_record(
        {
            "event": "node",
            "run_id": run_id,
            "span_id": span_id,
            "parent_span_id": span_id,
            "note": run_id,
        }
    )
    assert redacted["run_id"] == run_id
    assert redacted["span_id"] == span_id
    assert redacted["parent_span_id"] == span_id
    assert redacted["note"] == "<REDACTED_KEY>"


def test_export_of_producer_trace_is_one_clean_trace(tmp_path):
    _start_and_children(tmp_path)
    path = tmp_path / "task_as.trace.jsonl"
    spans = export_trace_jsonl(str(path))
    raw = _jsonl(path)
    root = raw[0]

    assert [span["name"] for span in spans] == [
        "task_task_start",
        "planner",
        "executor",
        "task_task_end",
    ]
    assert {span["trace_id"] for span in spans} == {root["run_id"]}
    assert all(TRACE_ID.fullmatch(span["trace_id"]) for span in spans)
    assert all(SPAN_ID.fullmatch(span["span_id"]) for span in spans)
    assert [span["span_id"] for span in spans] == [root["span_id"], *(record["span_id"] for record in raw[1:])]
    assert [span["parent_span_id"] for span in spans[1:]] == [record["parent_span_id"] for record in raw[1:]]
    assert all(span["parent_span_id"] == root["span_id"] for span in spans[1:])
    assert all("aitester.synthetic_root" not in span["attributes"] for span in spans)
    assert all("aitester.export_value_reasons" not in span["attributes"] for span in spans)
    assert export_trace_jsonl(str(path)) == spans
