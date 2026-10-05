"""P2-1 OTel 导出器回归测试（2026-10 批次）：
src/observability/otel_export.export_trace_jsonl 的 JSONL → OTel span 映射。

锁定口径（与 otel_export.py 实现一致）：
1. 文件不存在 → 抛 OSError（fail-closed，不静默吞掉）；
2. 无 task_start 记录 → 自动合成 root span（保证 Jaeger 渲染连通）；
3. 每 event 映射（task_start/task_end → root，node → 子 span parent=root）；
4. GenAI 语义属性映射（gen_ai.system / gen_ai.operation.name /
   gen_ai.usage.*）+ aitester.* 专有属性；
5. run_id/span_id 稳定（同文件重复导出 span id 一致，缺失时派生）；
6. 损坏行跳过（不阻断整文件）。
"""

from __future__ import annotations

import json

import pytest

from src.observability.otel_export import export_trace_jsonl


def _write_trace(tmp_path, records: list[dict]) -> str:
    p = tmp_path / "task.trace.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def test_export_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        export_trace_jsonl(str(tmp_path / "does_not_exist.jsonl"))


def test_export_empty_file_synthesizes_root(tmp_path):
    p = _write_trace(tmp_path, [])
    spans = export_trace_jsonl(p)
    assert len(spans) == 1
    assert spans[0]["name"] == "task_root_synthetic"
    assert spans[0]["parent_span_id"] is None
    assert spans[0]["attributes"]["gen_ai.system"] == "aitester"


def test_task_start_becomes_root_and_nodes_are_children(tmp_path):
    records = [
        {"event": "task_start", "task": "t1", "ts": 1000.0, "run_id": "r1"},
        {
            "event": "node",
            "node": "planner",
            "task": "t1",
            "ts": 1000.5,
            "run_id": "r1",
            "span_id": "s1",
            "decision": "done",
            "token_usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            "strategy_selected": "single_patch",
            "budget_remaining": 999,
            "iteration": 1,
            "duration_ms": 123.4,
        },
        {"event": "task_end", "task": "t1", "ts": 1001.0, "run_id": "r1", "stop_reason": "test_passed"},
    ]
    spans = export_trace_jsonl(_write_trace(tmp_path, records))
    by_name = {s["name"]: s for s in spans}
    # task_start 是 root（无 parent）
    assert by_name["task_task_start"]["parent_span_id"] is None
    # node 子 span 的 parent = task_start 的 span_id
    planner = by_name["planner"]
    assert planner["parent_span_id"] == by_name["task_task_start"]["span_id"]
    # GenAI 语义属性
    assert planner["attributes"]["gen_ai.system"] == "aitester"
    assert planner["attributes"]["gen_ai.operation.name"] == "planner"
    assert planner["attributes"]["gen_ai.usage.input_tokens"] == 10
    assert planner["attributes"]["gen_ai.usage.output_tokens"] == 20
    assert planner["attributes"]["gen_ai.usage.total_tokens"] == 30
    # aitester.* 专有属性
    assert planner["attributes"]["aitester.decision"] == "done"
    assert planner["attributes"]["aitester.strategy"] == "single_patch"
    assert planner["attributes"]["aitester.budget_remaining"] == 999
    assert planner["attributes"]["aitester.iteration"] == 1
    assert planner["attributes"]["aitester.task_id"] == "t1"
    # duration 转换：123.4 ms → 123400000 ns
    assert planner["duration_unix_nano"] == 123400000
    # task_end 也有 stop_reason 属性
    assert by_name["task_task_end"]["attributes"]["aitester.stop_reason"] == "test_passed"
    assert by_name["task_task_end"]["parent_span_id"] == by_name["task_task_start"]["span_id"]


def test_trace_id_from_run_id(tmp_path):
    records = [
        {"event": "task_start", "task": "t1", "ts": 1.0, "run_id": "my-run-42"},
        {"event": "node", "node": "generator", "task": "t1", "ts": 2.0, "run_id": "my-run-42"},
    ]
    spans = export_trace_jsonl(_write_trace(tmp_path, records))
    assert all(s["trace_id"] == "my-run-42" for s in spans)


def test_span_id_stable_for_same_file(tmp_path):
    records = [
        {"event": "task_start", "task": "t1", "ts": 1.0, "run_id": "r", "span_id": "root-x"},
        {"event": "node", "node": "executor", "task": "t1", "ts": 2.0, "run_id": "r", "span_id": "node-x"},
    ]
    p = _write_trace(tmp_path, records)
    first = export_trace_jsonl(p)
    second = export_trace_jsonl(p)
    assert [s["span_id"] for s in first] == [s["span_id"] for s in second]
    assert first[0]["span_id"] == "root-x"
    assert first[1]["span_id"] == "node-x"


def test_corrupt_lines_skipped(tmp_path):
    p = tmp_path / "trace.jsonl"
    p.write_text(
        json.dumps({"event": "task_start", "task": "t", "ts": 1.0})
        + "\n"
        + "NOT-JSON{{garbage\n"
        + json.dumps({"event": "node", "node": "debugger", "task": "t", "ts": 2.0})
        + "\n",
        encoding="utf-8",
    )
    spans = export_trace_jsonl(str(p))
    # 损坏行跳过：root + debugger 子 span（garbage 行不产生 span）
    names = [s["name"] for s in spans]
    assert "task_task_start" in names
    assert "debugger" in names
    assert len(spans) == 2


def test_node_without_token_usage_omits_genai_usage(tmp_path):
    records = [
        {"event": "task_start", "task": "t", "ts": 1.0, "run_id": "r"},
        {"event": "node", "node": "router", "task": "t", "ts": 2.0, "run_id": "r"},
    ]
    spans = export_trace_jsonl(_write_trace(tmp_path, records))
    router = next(s for s in spans if s["name"] == "router")
    assert "gen_ai.usage.input_tokens" not in router["attributes"]
    assert "gen_ai.usage.output_tokens" not in router["attributes"]
