"""DZ 轮：OTel 导出的整任务时长口径（task_end.duration_s）。

背景：
    TraceSession.record_task_end 写的是 ``duration_s``（秒，round 2），而
    otel_export._record_to_span 只读 ``duration_ms``——node 事件的字段。
    于是 task_end 映射出的 root span ``duration_unix_nano`` 恒为 0，
    整任务墙钟耗时在 Jaeger/Tempo 渲染里静默消失，且不产生任何
    aitester.export_value_reasons 披露（消费方无法知道"没有时长"还是"时长为 0"）。

锁定口径：
1. task_end 的 duration_s 按秒 → 纳秒导出（12.5s → 12_500_000_000ns）；
2. duration_s 的值域与 duration_ms 同源（AQ）：非有限 / 负数 / bool /
   非数值不原样导出，回落 0 并给出 ``duration_s_*`` 机制名；
3. 两字段同时出现时 duration_s（任务级字段）优先，避免 extra 注入的
   duration_ms 改写任务级时长；
4. node 事件的 duration_ms 口径不变（既有 test_p2_1_otel_export 已锁，
   本文件不重复）。
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from src.observability.otel_export import export_trace_jsonl


def _write_trace(tmp_path: Any, records: list[dict]) -> str:
    p = tmp_path / "task.trace.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    return str(p)


def _task_end_span(records: list[dict], tmp_path: Any) -> dict:
    spans = export_trace_jsonl(_write_trace(tmp_path, records))
    return next(s for s in spans if s["name"] == "task_task_end")


def _base_records(task_end: dict) -> list[dict]:
    return [
        {"event": "task_start", "task": "t", "ts": 1000.0, "run_id": "0123456789abcdef"},
        {"event": "task_end", "task": "t", "run_id": "0123456789abcdef", **task_end},
    ]


def test_task_end_duration_s_is_exported_in_nanoseconds(tmp_path):
    span = _task_end_span(_base_records({"ts": 1012.5, "duration_s": 12.5}), tmp_path)
    assert span["duration_unix_nano"] == 12_500_000_000
    assert "aitester.export_value_reasons" not in span["attributes"]


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (math.inf, "duration_s_not_finite"),
        (math.nan, "duration_s_not_finite"),
        (-1.5, "duration_s_negative"),
        (True, "duration_s_not_number:bool"),
        ("2.5", "duration_s_not_number:str"),
    ],
)
def test_task_end_bad_duration_s_is_disclosed(tmp_path, value, reason):
    span = _task_end_span(_base_records({"ts": 1001.0, "duration_s": value}), tmp_path)
    assert span["duration_unix_nano"] == 0
    assert span["attributes"]["aitester.export_value_reasons"] == reason


def test_task_end_duration_s_wins_over_duration_ms(tmp_path):
    span = _task_end_span(_base_records({"ts": 1002.0, "duration_s": 2.0, "duration_ms": 5000}), tmp_path)
    assert span["duration_unix_nano"] == 2_000_000_000
