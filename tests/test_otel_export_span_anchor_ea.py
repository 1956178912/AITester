"""EA 轮（2026-10-27）：OTel 导出 span 区间锚点（记录时刻是结束，起点由时长反推）。

缺陷：TraceSession 的 node / task_end 记录都在操作**完成时**追加
（``record_node`` / ``record_task_end`` 里 ``ts = time.time()``，duration 由
``t0`` 起算），所以 ``ts`` 是结束时刻；导出器却把 ``ts`` 原样写进
``start_time_unix_nano``，时长向未来延伸。真实会话实测：planner span 结束比
导出时刻晚 99ms、task_end span 晚 419ms，整任务区间落在未来，父子的区间
不闭合（Jaeger / Tempo 会把这些 span 画在时间轴的未来段）。

锁定口径：
1. task_start 的 ts 是**起点**（会话构造时取），不进位移；
2. node / task_end 的 ts 是结束时刻，duration 可用时 ``start = ts - duration``，
   区间闭在 ``start + duration == ts``；
3. duration 不可用（缺失 / 负 / 非有限 / 非数值）时不位移，ts 原值保留
   （值域披露沿用 AQ / DZ 的机制名）；
4. ts 不可用（缺失 / 负 / 非有限 / 越界）时起点回落 0，同样不位移——
   0 是既有哨兵，不叠加新机制名；
5. duration > ts（记录自相矛盾）时区间裁到 ``[0, ts]``，结束时刻为准，
   披露 ``span_interval_clamped``；
6. 真实会话：每个 span 的区间闭合在自身记录的 ts 上，且不晚于导出时刻。
"""

from __future__ import annotations

import json
import time

import pytest

from src.observability.otel_export import export_trace_jsonl
from src.observability.trace import TraceSession

TRACE_RUN = "a" * 32
ROOT_SPAN = "b" * 16


def _write_trace(tmp_path, records: list[dict]) -> str:
    path = tmp_path / "task.trace.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return str(path)


def _base(node: dict | None = None, task_end: dict | None = None) -> list[dict]:
    return [
        {"event": "task_start", "task": "t1", "ts": 100.0, "run_id": TRACE_RUN, "span_id": ROOT_SPAN},
        node if node is not None else {"event": "node", "node": "planner", "task": "t1", "ts": 100.5},
        task_end
        if task_end is not None
        else {"event": "task_end", "task": "t1", "ts": 100.5, "run_id": TRACE_RUN, "span_id": "c" * 16},
    ]


def _span(spans: list[dict], name: str) -> dict:
    return next(s for s in spans if s["name"] == name)


def _reasons(span: dict) -> list[str]:
    value = span["attributes"].get("aitester.export_value_reasons")
    return [] if value is None else value.split(",")


def test_node_span_ends_at_record_timestamp(tmp_path):
    node = {"event": "node", "node": "planner", "task": "t1", "ts": 100.5, "duration_ms": 250}
    planner = _span(export_trace_jsonl(_write_trace(tmp_path, _base(node=node))), "planner")
    assert planner["start_time_unix_nano"] == 100_250_000_000
    assert planner["duration_unix_nano"] == 250_000_000
    assert planner["start_time_unix_nano"] + planner["duration_unix_nano"] == 100_500_000_000
    assert _reasons(planner) == []


def test_task_end_span_covers_task_interval(tmp_path):
    task_end = {
        "event": "task_end",
        "task": "t1",
        "ts": 100.5,
        "run_id": TRACE_RUN,
        "span_id": "c" * 16,
        "duration_s": 0.5,
    }
    end = _span(export_trace_jsonl(_write_trace(tmp_path, _base(task_end=task_end))), "task_task_end")
    assert end["start_time_unix_nano"] == 100_000_000_000
    assert end["duration_unix_nano"] == 500_000_000
    assert end["start_time_unix_nano"] + end["duration_unix_nano"] == 100_500_000_000
    assert _reasons(end) == []


def test_task_start_timestamp_is_a_start_and_is_not_shifted(tmp_path):
    records = _base()
    records[0]["duration_s"] = 2.5
    start = _span(export_trace_jsonl(_write_trace(tmp_path, records)), "task_task_start")
    assert start["start_time_unix_nano"] == 100_000_000_000
    assert start["duration_unix_nano"] == 2_500_000_000
    assert _reasons(start) == []


def test_node_without_duration_is_not_shifted(tmp_path):
    node = {"event": "node", "node": "planner", "task": "t1", "ts": 100.5}
    planner = _span(export_trace_jsonl(_write_trace(tmp_path, _base(node=node))), "planner")
    assert planner["start_time_unix_nano"] == 100_500_000_000
    assert planner["duration_unix_nano"] == 0
    assert _reasons(planner) == []


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (float("nan"), "duration_ms_not_finite"),
        (-250, "duration_ms_negative"),
        (True, "duration_ms_not_number:bool"),
        ("250", "duration_ms_not_number:str"),
    ],
)
def test_unusable_duration_keeps_record_timestamp_as_start(tmp_path, value, reason):
    node = {"event": "node", "node": "planner", "task": "t1", "ts": 100.5, "duration_ms": value}
    planner = _span(export_trace_jsonl(_write_trace(tmp_path, _base(node=node))), "planner")
    assert planner["start_time_unix_nano"] == 100_500_000_000
    assert planner["duration_unix_nano"] == 0
    assert _reasons(planner) == [reason]


@pytest.mark.parametrize("ts", [None, -1.0, float("inf"), "100.5"])
def test_unusable_timestamp_falls_back_to_zero_without_shift(tmp_path, ts):
    node = {"event": "node", "node": "planner", "task": "t1", "ts": ts, "duration_ms": 250}
    planner = _span(export_trace_jsonl(_write_trace(tmp_path, _base(node=node))), "planner")
    assert planner["start_time_unix_nano"] == 0
    assert planner["duration_unix_nano"] == 250_000_000
    assert "span_interval_clamped" not in _reasons(planner)


def test_duration_longer_than_timestamp_is_clamped_to_the_end(tmp_path):
    node = {"event": "node", "node": "planner", "task": "t1", "ts": 1.0, "duration_ms": 2000}
    planner = _span(export_trace_jsonl(_write_trace(tmp_path, _base(node=node))), "planner")
    assert planner["start_time_unix_nano"] == 0
    assert planner["duration_unix_nano"] == 1_000_000_000
    assert planner["start_time_unix_nano"] + planner["duration_unix_nano"] == 1_000_000_000
    assert _reasons(planner) == ["span_interval_clamped"]


def test_real_session_spans_close_on_their_record_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
    session = TraceSession("anchor_probe")
    t0 = time.time()
    time.sleep(0.05)
    session.record_node("planner", duration_ms=(time.time() - t0) * 1000, decision="plan_complete")
    session.record_task_end(passed=True)

    with open(session._file_path, encoding="utf-8") as f:
        records = {r["event"]: r for r in (json.loads(line) for line in f)}

    spans = {s["name"]: s for s in export_trace_jsonl(session._file_path)}
    planner = spans["planner"]
    task_end = spans["task_task_end"]
    root = spans["task_task_start"]

    assert planner["start_time_unix_nano"] + planner["duration_unix_nano"] == int(records["node"]["ts"] * 1e9)
    assert task_end["start_time_unix_nano"] + task_end["duration_unix_nano"] == int(records["task_end"]["ts"] * 1e9)
    assert task_end["start_time_unix_nano"] + task_end["duration_unix_nano"] <= int(time.time() * 1e9)
    assert planner["start_time_unix_nano"] >= root["start_time_unix_nano"]
    assert (
        planner["start_time_unix_nano"] + planner["duration_unix_nano"]
        <= task_end["start_time_unix_nano"] + task_end["duration_unix_nano"]
    )
