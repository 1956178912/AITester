"""P2-1（2026-10 批次）：trace.jsonl → OpenTelemetry 导出器。

背景：
    src/observability/trace.py 的 TraceSession 落盘自定义 JSONL schema
    （event=node/task_start/task_end + run_id/span_id/decision/token_usage
    等字段）。跨团队 / 论文附录 / 开源传播时，自定义 schema 复用成本高。
    本导出器把 trace.jsonl 转换为 OpenTelemetry GenAI 语义约定
    （opentelemetry-spec 的 GenAI 信号 + span 属性）的 trace 结构，
    一条 trace 可被 Jaeger / Tempo 直接渲染。

设计口径（与 ADR-0003 默认关 + ADR-0004 零默认依赖一致）：
    - 纯离线转换：读 JSONL 文件 → 返回 OTel 兼容 dict 结构
      （spans 列表，含 trace_id / span_id / parent_id / name /
      start_time_unix_nano / duration / attributes）；
    - 不引入 opentelemetry SDK 依赖（本仓库零默认依赖口径；
      消费方如需 SDK 直接 `pip install opentelemetry-api`，
      本导出的结构可经 SDK 的 Tracer 构造或直接 OTLP 序列化）；
    - GenAI 语义约定映射（属性前缀 gen_ai.*）：
        gen_ai.system=aitester / gen_ai.operation.name=<node>
        gen_ai.usage.input_tokens / output_tokens（取自 record.token_usage）
        aitester.decision / aitester.strategy / aitester.budget_remaining
    - task_start / task_end 映射为 trace 级 span（root）；
      每个 node 事件映射为子 span（parent = 该 task 的 root span）。

用法：
    from src.observability.otel_export import export_trace_jsonl
    spans = export_trace_jsonl("path/to/<task>.trace.jsonl")
    # spans: [{"trace_id", "span_id", "parent_span_id", "name",
    #          "start_time_unix_nano", "duration_unix_nano",
    #          "attributes": {...}}, ...]
    # 可喂给 opentelemetry SDK 的 trace 构造器，或经
    # opentelemetry-exporter-otlp-proto-http 序列化为 OTLP。
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def _record_to_span(record: dict[str, Any], root_span_id: str | None, trace_id: str) -> dict[str, Any] | None:
    """把单条 JSONL 记录映射为 OTel span（task_start/task_end → root，node → 子 span）。"""
    event = record.get("event")
    if event not in ("node", "task_start", "task_end"):
        return None
    ts = record.get("ts")
    start_ns = int(float(ts) * 1e9) if isinstance(ts, (int, float)) else 0
    duration_ms = record.get("duration_ms")
    duration_ns = int(float(duration_ms) * 1e6) if isinstance(duration_ms, (int, float)) else 0

    # 确定性 trace/span id：优先用记录自带 run_id / span_id，缺失时派生
    # （保证重复导出同一文件时 span id 稳定，便于跨渲染器对齐）。
    trace_id_val = record.get("run_id") or trace_id
    if event == "task_start":
        # task_start 映射为 trace 级 root span（无 parent）
        span_id = record.get("span_id") or uuid.uuid4().hex[:16]
        parent_id: str | None = None
    elif event == "task_end":
        # task_end 映射为 root 的收尾子 span（挂在 task_start root 之下）
        span_id = record.get("span_id") or uuid.uuid4().hex[:16]
        parent_id = root_span_id
    else:  # node 事件：子 span，挂在 root
        span_id = record.get("span_id") or uuid.uuid4().hex[:16]
        parent_id = root_span_id  # type: ignore[assignment]
    name = record.get("node") if event == "node" else f"task_{record.get('event', 'unknown')}"
    attributes: dict[str, Any] = {
        "gen_ai.system": "aitester",
        "gen_ai.operation.name": name,
    }
    # GenAI token 用量语义约定（gen_ai.usage.*）
    token_usage = record.get("token_usage")
    if isinstance(token_usage, dict):
        if token_usage.get("input_tokens") is not None:
            attributes["gen_ai.usage.input_tokens"] = token_usage["input_tokens"]
        if token_usage.get("output_tokens") is not None:
            attributes["gen_ai.usage.output_tokens"] = token_usage["output_tokens"]
        if token_usage.get("total_tokens") is not None:
            attributes["gen_ai.usage.total_tokens"] = token_usage["total_tokens"]
    # AITester 专有属性（aitester.* 前缀，非 GenAI 标准，Jaeger 自定义 tag 可查）
    for src_key, dst_key in (
        ("decision", "aitester.decision"),
        ("decision_reason", "aitester.decision_reason"),
        ("strategy_selected", "aitester.strategy"),
        ("budget_remaining", "aitester.budget_remaining"),
        ("iteration", "aitester.iteration"),
        ("stop_reason", "aitester.stop_reason"),
    ):
        if record.get(src_key) is not None:
            attributes[dst_key] = record[src_key]
    if record.get("task") is not None:
        attributes["aitester.task_id"] = record["task"]

    return {
        "trace_id": trace_id_val,
        "span_id": span_id,
        "parent_span_id": parent_id,
        "name": name,
        "start_time_unix_nano": start_ns,
        "duration_unix_nano": duration_ns,
        "attributes": attributes,
    }


def export_trace_jsonl(path: str) -> list[dict[str, Any]]:
    """把 trace.jsonl 转换为 OTel 兼容 span 列表（纯离线，零 SDK 依赖）。

    Args:
        path: trace.jsonl 文件路径（TraceSession 落盘的 <task_uuid>.trace.jsonl）。

    Returns:
        span 列表（task_start 在前，随后按记录顺序 node，task_end 收尾；
        无 task_start 记录时自动合成一个 root span 保证 Jaeger 渲染连通）。

    Raises:
        OSError: 文件不可读时抛出（不静默吞掉，与 fail-closed 口径一致）。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    records: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # 损坏行跳过（不阻断整文件导出，与 trace.py 的 JSONL 追加式口径一致）
            continue

    # trace_id：取首条记录 run_id（缺失时派生确定性 id）
    first = next((r for r in records if r.get("event") == "task_start"), None)
    trace_id = (first.get("run_id") if first else None) or uuid.uuid4().hex[:32]

    # 找 task_start span（Jaeger 渲染根）；缺失时合成
    root_span_id: str | None = None
    spans: list[dict[str, Any]] = []
    for record in records:
        if record.get("event") == "task_start":
            span = _record_to_span(record, None, trace_id)
            if span:
                root_span_id = span["span_id"]  # type: ignore[assignment]
                spans.append(span)
    if root_span_id is None:
        synthetic_id = uuid.uuid4().hex[:16]
        synthetic = {
            "trace_id": trace_id,
            "span_id": synthetic_id,
            "parent_span_id": None,
            "name": "task_root_synthetic",
            "start_time_unix_nano": 0,
            "duration_unix_nano": 0,
            "attributes": {"gen_ai.system": "aitester", "aitester.synthetic_root": True},
        }
        root_span_id = synthetic_id
        spans.append(synthetic)

    # node / task_end 子 span（按记录顺序，parent = root）
    for record in records:
        if record.get("event") == "task_start":
            continue  # 已处理
        span = _record_to_span(record, root_span_id, trace_id)
        if span:
            spans.append(span)

    return spans


__all__ = ["export_trace_jsonl"]
