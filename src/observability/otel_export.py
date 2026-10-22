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
        gen_ai.usage.input_tokens / output_tokens / total_tokens
        （取自 record.token_usage）
        aitester.decision / aitester.strategy / aitester.budget_remaining
    - 数值导出值域（AQ，2026-10-21）：token 三个计数复用
      :func:`src.budget.token_usage.count_reason`（非负整数；bool / 小数 /
      非有限 / 字符串都不是计数），时间戳与 duration 只接受有限非负数，
      budget_remaining / iteration 同域。不可读的值不导出原值，机制名按处理
      顺序以逗号拼进 aitester.export_value_reasons；非有限时间戳回落到既有
      的 0 哨兵（不中止整文件导出）。干净记录（真实 trace 的全部数值字段）
      导出结果逐字不变。
    - 标识与字符串属性值域（AR，2026-10-21）：trace_id 规范化到 32 位小写
      hex、span_id 到 16 位（短 hex 左补零，大小写归一）；一个文件一个
      trace_id（首个可规范化 run_id，缺失时按路径确定性派生），缺失 /
      非法标识不再用随机 uuid，重复导出逐字稳定；同一 trace 内 span_id
      冲突改派生 id 并披露。node 名称 / decision / decision_reason /
      strategy_selected / stop_reason / task 只导出字符串，非字符串不导出
      原值并披露。标识、名称与字符串族机制名按处理顺序排在数值族之前。
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

import hashlib
import json
import logging
import math
from typing import Any

from src.budget.token_usage import count_reason, token_write_rejection_reasons

logger = logging.getLogger(__name__)

_TOKEN_ATTRIBUTES = (
    ("input_tokens", "gen_ai.usage.input_tokens"),
    ("output_tokens", "gen_ai.usage.output_tokens"),
    ("total_tokens", "gen_ai.usage.total_tokens"),
)
_STRING_ATTRIBUTES = (
    ("decision", "aitester.decision"),
    ("decision_reason", "aitester.decision_reason"),
    ("strategy_selected", "aitester.strategy"),
    ("stop_reason", "aitester.stop_reason"),
)
_VALUE_REASONS_ATTRIBUTE = "aitester.export_value_reasons"
_TRACE_ID_HEX = 32
_SPAN_ID_HEX = 16
_HEX_DIGITS = frozenset("0123456789abcdef")


def _token_attributes(token_usage: Any) -> tuple[dict[str, int], list[str]]:
    """token 三元组的可导出属性与机制名：逐个字段判定，坏值不导出原值。

    AT（2026-10-21）：`token_write_reasons` 非空 ⇒ 该快照的 token 只是已收下
    部分的和，整组不导出，机制名以 `token_write_rejected:` 前缀披露。
    """
    if token_usage is None:
        return {}, []
    if not isinstance(token_usage, dict):
        return {}, [f"token_usage_not_object:{type(token_usage).__name__}"]
    markers = token_write_rejection_reasons(token_usage)
    if markers:
        return {}, markers
    attributes: dict[str, int] = {}
    reasons: list[str] = []
    for field, attribute in _TOKEN_ATTRIBUTES:
        if field not in token_usage:
            continue
        reason = count_reason(token_usage[field], field)
        if reason is not None:
            reasons.append(reason)
            continue
        attributes[attribute] = token_usage[field]
    return attributes, reasons


def _timestamp_ns(value: Any, scale: float, field: str) -> tuple[int, list[str]]:
    """毫秒/秒 → 纳秒：只接受有限非负数，其余回落 0 并给出机制名（不抛异常）。"""
    if value is None:
        return 0, []
    if isinstance(value, bool):
        return 0, [f"{field}_not_number:bool"]
    if not isinstance(value, (int, float)):
        return 0, [f"{field}_not_number:{type(value).__name__}"]
    if isinstance(value, float) and not math.isfinite(value):
        return 0, [f"{field}_not_finite"]
    if value < 0:
        return 0, [f"{field}_negative"]
    try:
        scaled = float(value) * scale
    except OverflowError:
        return 0, [f"{field}_out_of_range"]
    if not math.isfinite(scaled):
        return 0, [f"{field}_out_of_range"]
    return int(scaled), []


def _numeric_attribute(value: Any, field: str) -> tuple[int | float | None, str | None]:
    """有限非负 int/float 才可作为数值属性导出；bool 不认（int 的子类）。"""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"{field}_not_number:bool"
    if not isinstance(value, (int, float)):
        return None, f"{field}_not_number:{type(value).__name__}"
    if isinstance(value, float) and not math.isfinite(value):
        return None, f"{field}_not_finite"
    if value < 0:
        return None, f"{field}_negative"
    return value, None


def _canonical_identifier(value: Any, width: int, field: str) -> tuple[str | None, str | None]:
    """OTel 标识：width 位小写 hex；短 hex 左补零，非法 / 非字符串不可导出。"""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{field}_not_string:{type(value).__name__}"
    lowered = value.lower()
    if not lowered or len(lowered) > width or any(ch not in _HEX_DIGITS for ch in lowered):
        return None, f"{field}_invalid_format"
    canonical = lowered.zfill(width)
    if canonical == "0" * width:
        return None, f"{field}_invalid_format"
    return canonical, None


def _derived_span_id(trace_id: str, index: int, attempt: int = 0) -> str:
    while True:
        digest = hashlib.sha256(f"aitester-span:{trace_id}:{index}:{attempt}".encode()).hexdigest()
        derived = digest[:_SPAN_ID_HEX]
        if derived != "0" * _SPAN_ID_HEX:
            return derived
        attempt += 1


def _file_trace_id(records: list[dict[str, Any]], path: str) -> str:
    """一个 trace 文件一个 trace id：首个可规范化 run_id，缺失时按路径确定性派生。"""
    first_text: str | None = None
    for record in records:
        value = record.get("run_id")
        if value is None:
            continue
        canonical, _ = _canonical_identifier(value, _TRACE_ID_HEX, "run_id")
        if canonical is not None:
            return canonical
        if first_text is None and isinstance(value, str) and value:
            first_text = value
    seed = first_text if first_text is not None else f"path:{path}"
    return hashlib.sha256(f"aitester-trace:{seed}".encode()).hexdigest()[:_TRACE_ID_HEX]


def _span_name(record: dict[str, Any], event: str) -> tuple[str, str | None]:
    if event != "node":
        return f"task_{event}", None
    node = record.get("node")
    if node is None:
        return "node", None
    if not isinstance(node, str):
        return "node", f"node_not_string:{type(node).__name__}"
    if not node:
        return "node", "node_empty"
    return node, None


def _ensure_unique_span(span: dict[str, Any], trace_id: str, index: int, seen: set[str]) -> dict[str, Any]:
    """同一 trace 内 span_id 冲突时改派生 id，并把冲突计入披露。"""
    if span["span_id"] not in seen:
        seen.add(span["span_id"])
        return span
    attempt = 0
    while True:
        candidate = _derived_span_id(trace_id, index, attempt)
        if candidate not in seen:
            break
        attempt += 1
    span["span_id"] = candidate
    existing = span["attributes"].get(_VALUE_REASONS_ATTRIBUTE)
    span["attributes"][_VALUE_REASONS_ATTRIBUTE] = f"{existing},span_id_duplicate" if existing else "span_id_duplicate"
    seen.add(candidate)
    return span


def _record_to_span(
    record: dict[str, Any], root_span_id: str | None, trace_id: str, index: int = 0
) -> dict[str, Any] | None:
    """把单条 JSONL 记录映射为 OTel span（task_start/task_end → root，node → 子 span）。"""
    event = record.get("event")
    if event not in ("node", "task_start", "task_end"):
        return None

    reasons: list[str] = []
    run_value = record.get("run_id")
    if run_value is not None:
        run_canonical, run_reason = _canonical_identifier(run_value, _TRACE_ID_HEX, "run_id")
        if run_reason is not None:
            reasons.append(run_reason)
        elif run_canonical != trace_id:
            reasons.append("run_id_mismatch")
    span_canonical, span_reason = _canonical_identifier(record.get("span_id"), _SPAN_ID_HEX, "span_id")
    if span_reason is not None:
        reasons.append(span_reason)
    span_id = span_canonical if span_canonical is not None else _derived_span_id(trace_id, index)
    if event == "task_start":
        parent_id: str | None = None
    else:
        parent_id = root_span_id  # type: ignore[assignment]
    name, name_reason = _span_name(record, event)
    if name_reason is not None:
        reasons.append(name_reason)

    ts = record.get("ts")
    start_ns, ts_reasons = _timestamp_ns(ts, 1e9, "ts")
    reasons.extend(ts_reasons)
    duration_ms = record.get("duration_ms")
    duration_ns, duration_reasons = _timestamp_ns(duration_ms, 1e6, "duration_ms")
    reasons.extend(duration_reasons)

    attributes: dict[str, Any] = {
        "gen_ai.system": "aitester",
        "gen_ai.operation.name": name,
    }
    # GenAI token 用量语义约定（gen_ai.usage.*）：值域收口，坏值不原样流出
    token_attributes, token_reasons = _token_attributes(record.get("token_usage"))
    attributes.update(token_attributes)
    reasons.extend(token_reasons)
    # AITester 专有属性（aitester.* 前缀，非 GenAI 标准，Jaeger 自定义 tag 可查）
    for src_key, dst_key in _STRING_ATTRIBUTES:
        value = record.get(src_key)
        if value is None:
            continue
        if not isinstance(value, str):
            reasons.append(f"{src_key}_not_string:{type(value).__name__}")
            continue
        attributes[dst_key] = value
    budget_remaining, budget_reason = _numeric_attribute(record.get("budget_remaining"), "budget_remaining")
    if budget_reason is not None:
        reasons.append(budget_reason)
    elif budget_remaining is not None:
        attributes["aitester.budget_remaining"] = budget_remaining
    iteration = record.get("iteration")
    if iteration is not None:
        iteration_reason = count_reason(iteration, "iteration")
        if iteration_reason is not None:
            reasons.append(iteration_reason)
        else:
            attributes["aitester.iteration"] = iteration
    task = record.get("task")
    if task is not None:
        if isinstance(task, str):
            attributes["aitester.task_id"] = task
        else:
            reasons.append(f"task_not_string:{type(task).__name__}")
    if reasons:
        attributes[_VALUE_REASONS_ATTRIBUTE] = ",".join(reasons)

    return {
        "trace_id": trace_id,
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
    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # 损坏行跳过（不阻断整文件导出，与 trace.py 的 JSONL 追加式口径一致）
            logger.warning("OTel 导出：跳过第 %d 行（JSON 损坏）", lineno)
            continue
        # N10（2026-10-22 第三方复审 P2）：JSON 合法 ≠ 记录是对象。`null` /
        # `[]` / `0` / `false` / 字符串都能被 json.loads 接受，随后
        # `_file_trace_id` 对 None 调 `.get` 抛 AttributeError，整文件导出崩溃。
        # 现按行隔离：非对象记录跳过并披露行号与类型，其余记录照常导出。
        if not isinstance(record, dict):
            logger.warning(
                "OTel 导出：跳过第 %d 行（记录不是 JSON 对象，实为 %s）",
                lineno,
                type(record).__name__,
            )
            continue
        records.append(record)

    # 一个文件一个 trace：所有 span 共用同一 trace_id（含 task_start/task_end）
    trace_id = _file_trace_id(records, path)

    # 找 task_start span（Jaeger 渲染根）；缺失时合成
    root_span_id: str | None = None
    spans: list[dict[str, Any]] = []
    seen_span_ids: set[str] = set()
    for index, record in enumerate(records):
        if record.get("event") == "task_start":
            span = _record_to_span(record, None, trace_id, index)
            if span:
                span = _ensure_unique_span(span, trace_id, index, seen_span_ids)
                root_span_id = span["span_id"]  # type: ignore[assignment]
                spans.append(span)
    if root_span_id is None:
        synthetic_id = _derived_span_id(trace_id, -1)
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
        seen_span_ids.add(synthetic_id)
        spans.append(synthetic)

    # node / task_end 子 span（按记录顺序，parent = root）
    for index, record in enumerate(records):
        if record.get("event") == "task_start":
            continue  # 已处理
        span = _record_to_span(record, root_span_id, trace_id, index)
        if span:
            spans.append(_ensure_unique_span(span, trace_id, index, seen_span_ids))

    return spans


__all__ = ["export_trace_jsonl"]
