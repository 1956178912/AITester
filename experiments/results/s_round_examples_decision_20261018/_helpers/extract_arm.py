"""逐臂元数据抽取（零 LLM）：tokens/成本/墙钟/行字段/注入与 verdict/示例来源与计数/字段完整性。"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

batch_path, label, cli, env_examples, ns, start_epoch, start_iso, out_meta, trace_dir, log_path, price_path = sys.argv[1:12]
batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
arm = (batch.get("results") or {}).get("aitester") or {}
rows = arm.get("details") or []
prov = batch.get("provenance") or {}
snap = prov.get("env_snapshot") or {}
tm = arm.get("token_metrics") or batch.get("token_metrics") or {}

price = json.loads(Path(price_path).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in, p_out = price.get("input_per_mtok"), price.get("output_per_mtok")
cost = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    cost = round((tm.get("total_input_tokens", 0) * p_in + tm.get("total_output_tokens", 0) * p_out) / 1e6, 6)

wall = exit_code = end_iso = None
log_text = Path(log_path).read_text(encoding="utf-8", errors="replace") if Path(log_path).exists() else ""
m = re.search(r"END_ISO_UTC=(\S+) END_EPOCH=(\d+) EXIT_CODE=(-?\d+) WALL_SECONDS=(\d+)", log_text)
if m:
    end_iso, _e, exit_code, wall = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

REQ_KEYS = [
    "task_id", "passed", "coverage", "iterations", "stop_reason",
    "spec_oracle_injected", "spec_oracle_verdict", "oracle_suite_verdict",
    "llm_suite_detection_rate", "detection_rate", "repair_rate", "false_fix_rate",
    "spec_oracle_examples_source", "spec_oracle_examples_count",
]
field_present = {k: sum(1 for r in rows if k in r) for k in REQ_KEYS}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


tasks = []
stop_reasons = Counter()
oracle_suite = Counter()
oracle_verdict = Counter()
examples_source = Counter()
examples_counts = []
for r in rows:
    sr = r.get("stop_reason")
    stop_reasons[str(sr) if sr else "None"] += 1
    osv = r.get("oracle_suite_verdict")
    oracle_suite[str(osv) if osv is not None else "None"] += 1
    ov = r.get("spec_oracle_verdict")
    oracle_verdict[str(ov) if ov is not None else "None"] += 1
    es = r.get("spec_oracle_examples_source")
    examples_source[str(es) if es is not None else "None"] += 1
    ec = _int(r.get("spec_oracle_examples_count"))
    if ec is not None:
        examples_counts.append(ec)
    tasks.append({
        "task_id": r.get("task_id"),
        "passed": bool(r.get("passed")),
        "iterations": int(r.get("iterations") or 0),
        "coverage": _num(r.get("coverage")),
        "detection_rate": _num(r.get("detection_rate")),
        "llm_suite_detection_rate": _num(r.get("llm_suite_detection_rate")),
        "repair_rate": _num(r.get("repair_rate")),
        "false_fix_rate": _num(r.get("false_fix_rate")),
        "stop_reason": sr,
        "spec_oracle_injected": r.get("spec_oracle_injected"),
        "spec_oracle_verdict": ov,
        "oracle_suite_verdict": osv,
        "spec_oracle_examples_source": es,
        "spec_oracle_examples_count": ec,
        "elapsed_seconds": _num(r.get("elapsed_seconds")),
        "token_usage": r.get("token_usage") or {},
    })

# trace：planner 事件中的 examples 证据（若 Q-1 在 trace 中记录）与 stop/reason 计数
trace_events = Counter()
if Path(trace_dir).is_dir():
    for f in sorted(Path(trace_dir).glob("*.trace.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") == "node":
                trace_events[f"{rec.get('node')}:{rec.get('decision')}"] += 1

det_vals = [t["llm_suite_detection_rate"] for t in tasks if t["llm_suite_detection_rate"] is not None]
if not det_vals:
    det_vals = [t["detection_rate"] for t in tasks if t["detection_rate"] is not None]

payload = {
    "arm_label": label,
    "cli": cli,
    "env_expected_SPEC_ORACLE_EXAMPLES_ENABLE": env_examples,
    "cache_namespace": ns,
    "batch_path": str(Path(batch_path).resolve()),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "task_ids": [t["task_id"] for t in tasks],
    "tasks": tasks,
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
    "wall_seconds": wall,
    "start_epoch": int(start_epoch),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "exit_code": exit_code,
    "log_path": str(Path(log_path).resolve()),
    "trace_dir": str(Path(trace_dir).resolve()),
    "provenance": {
        "git_sha": prov.get("git_sha"),
        "git_dirty": prov.get("git_dirty"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "env_snapshot_SPEC_ORACLE_EXEC_ENABLE": snap.get("SPEC_ORACLE_EXEC_ENABLE"),
        "env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE": snap.get("SPEC_ORACLE_EXAMPLES_ENABLE"),
        "env_snapshot_DETECTION_SPEC_MODE": snap.get("DETECTION_SPEC_MODE"),
    },
    "stop_reason_counts": dict(stop_reasons),
    "oracle_suite_verdict_counts": dict(oracle_suite),
    "oracle_verdict_counts": dict(oracle_verdict),
    "examples_source_counts": dict(examples_source),
    "examples_count_stats": {
        "n_rows_with_count": len(examples_counts),
        "mean": round(sum(examples_counts) / len(examples_counts), 4) if examples_counts else None,
        "max": max(examples_counts) if examples_counts else None,
        "total": sum(examples_counts),
    },
    "field_present_counts": field_present,
    "trace_events": dict(trace_events),
    "detection_aggregate": {
        "measurable": len(det_vals),
        "detected": sum(1 for v in det_vals if float(v) >= 1.0),
        "rate": round(sum(1 for v in det_vals if float(v) >= 1.0) / len(det_vals), 4) if det_vals else None,
    },
}
Path(out_meta).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} wall={wall}s "
      f"injected={dict((k, v) for k, v in Counter(str(t['spec_oracle_injected']) for t in tasks).items())} "
      f"oracle_suite={dict(oracle_suite)} examples_source={dict(examples_source)}")
