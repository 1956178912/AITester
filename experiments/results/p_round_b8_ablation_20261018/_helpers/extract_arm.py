"""逐臂元数据抽取（零 LLM）：tokens/成本/墙钟/逐任务字段/stop_reason/stall 计数/trace 证据。"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

batch_path, label, cli_flag, stall_env, ns, start_epoch, start_iso, out_meta, trace_dir, log_path, price_path = sys.argv[1:12]
batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
arm = (batch.get("results") or {}).get("aitester") or {}
rows = arm.get("details") or []
prov = batch.get("provenance") or {}
snap = prov.get("env_snapshot") or {}
tm = arm.get("token_metrics") or batch.get("token_metrics") or {}

price = json.loads(Path(price_path).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in = price.get("input_per_mtok")
p_out = price.get("output_per_mtok")
cost = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    cost = round((tm.get("total_input_tokens", 0) * p_in + tm.get("total_output_tokens", 0) * p_out) / 1e6, 6)

wall = None
exit_code = None
end_iso = None
log_text = Path(log_path).read_text(encoding="utf-8", errors="replace") if Path(log_path).exists() else ""
m = re.search(r"END_ISO_UTC=(\S+) END_EPOCH=(\d+) EXIT_CODE=(-?\d+) WALL_SECONDS=(\d+)", log_text)
if m:
    end_iso, _end_epoch, exit_code, wall = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

REQ_KEYS = ["task_id", "passed", "coverage", "iterations", "stop_reason", "detection_rate", "repair_rate", "false_fix_rate"]
field_present = {k: sum(1 for r in rows if k in r) for k in REQ_KEYS}

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

tasks = []
stop_reasons = Counter()
stall_label = 0
for r in rows:
    sr = r.get("stop_reason")
    stop_reasons[str(sr) if sr else "None"] += 1
    if sr == "coverage_stall":
        stall_label += 1
    meta_tm = r.get("task_metadata") or {}
    tasks.append({
        "task_id": r.get("task_id"),
        "difficulty": meta_tm.get("difficulty"),
        "bug_type": meta_tm.get("bug_type"),
        "is_cross_file": meta_tm.get("is_cross_file"),
        "passed": bool(r.get("passed")),
        "iterations": int(r.get("iterations") or 0),
        "coverage": _num(r.get("coverage")),
        "detection_rate": _num(r.get("detection_rate")),
        "repair_rate": _num(r.get("repair_rate")),
        "false_fix_rate": _num(r.get("false_fix_rate")),
        "stop_reason": sr,
        "elapsed_seconds": _num(r.get("elapsed_seconds")),
        "execution_trace_len": len(r.get("execution_trace") or []),
        "token_usage": r.get("token_usage") or {},
    })

trace_reason_counts = Counter()
trace_node_decisions = Counter()
if Path(trace_dir).is_dir():
    for f in sorted(Path(trace_dir).glob("*.trace.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") != "node":
                continue
            node = rec.get("node")
            dec = rec.get("decision")
            if node in ("_should_debug", "_route_after_diagnosis"):
                trace_node_decisions[f"{node}:{dec}"] += 1
            out = rec.get("output")
            reason = out.get("reason") if isinstance(out, dict) else None
            if reason:
                trace_reason_counts[str(reason)] += 1

det_vals = [t["detection_rate"] for t in tasks if t["detection_rate"] is not None]
payload = {
    "arm_label": label,
    "cli_flag": cli_flag,
    "env_expected_COVERAGE_STALL_DETECT_ENABLE": stall_env,
    "cache_namespace": ns,
    "batch_path": str(Path(batch_path).resolve()),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "task_ids": [t["task_id"] for t in tasks],
    "tasks": tasks,
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
    "price_table": {"model": "deepseek-flash", "input_per_mtok": p_in, "output_per_mtok": p_out},
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
        "env_snapshot_COVERAGE_STALL_DETECT_ENABLE": snap.get("COVERAGE_STALL_DETECT_ENABLE"),
        "env_snapshot_DETECTION_SPEC_MODE": snap.get("DETECTION_SPEC_MODE"),
    },
    "stop_reason_counts": dict(stop_reasons),
    "coverage_stall_label_count": stall_label,
    "trace_reason_counts": dict(trace_reason_counts),
    "trace_node_decisions": dict(trace_node_decisions),
    "field_present_counts": field_present,
    "detection_aggregate": {
        "measurable": len(det_vals),
        "detected": sum(1 for v in det_vals if float(v) >= 1.0),
        "rate": round(sum(1 for v in det_vals if float(v) >= 1.0) / len(det_vals), 4) if det_vals else None,
    },
}
Path(out_meta).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} "
      f"wall={wall}s stop_reasons={dict(stop_reasons)} coverage_stall={stall_label}")
