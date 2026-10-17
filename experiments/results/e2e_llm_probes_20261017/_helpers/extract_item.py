"""逐项证据抽取：批次 JSON 指标/字段 → item_meta.json；日志关键词 + trace 节点计数。

只读取工件，零网络/零 LLM；输出为可审计 JSON（数字均来自工件，不手写）。
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

item_dir, log_path, out_meta, price_path, start_epoch, end_epoch = sys.argv[1:7]
item = Path(item_dir)
log = Path(log_path)

price = {}
try:
    price = (json.loads(Path(price_path).read_text(encoding="utf-8")).get("models") or {}).get("deepseek-flash") or {}
except (OSError, ValueError):
    pass

batches = sorted(glob.glob(str(item / "benchmark_*.json")))
meta: dict = {
    "item": item.name,
    "item_dir": str(item),
    "log": str(log),
    "start_epoch": int(start_epoch),
    "end_epoch": int(end_epoch),
    "wall_seconds": int(end_epoch) - int(start_epoch),
    "batch_files": [],
}

# ── 批次工件（可能 0 个 = 失败/未产出）──
details_all: list[dict] = []
token_totals = {"total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0, "total_llm_calls": 0,
                "total_cache_hits": 0, "total_cache_avoided_tokens": 0}
for bp in batches:
    try:
        data = json.loads(Path(bp).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    sha = hashlib.sha256(Path(bp).read_bytes()).hexdigest()
    results = data.get("results") or {}
    arms = {}
    for arm, rd in results.items():
        if not isinstance(rd, dict):
            continue
        tm = rd.get("token_metrics") or {}
        for k in token_totals:
            token_totals[k] += int(tm.get(k) or 0)
        det = rd.get("details") or []
        details_all.extend(det)
        arms[arm] = {
            "rows": len(det),
            "token_metrics": tm,
            "agg_rag_metrics": rd.get("rag_metrics"),
        }
    meta["batch_files"].append({"path": str(bp), "sha256": sha, "dataset": data.get("dataset"),
                                "total_tasks": data.get("total_tasks"), "provenance": data.get("provenance"),
                                "arms": arms})

in_tok = token_totals["total_input_tokens"]
out_tok = token_totals["total_output_tokens"]
cost = None
if isinstance(price.get("input_per_mtok"), (int, float)) and isinstance(price.get("output_per_mtok"), (int, float)):
    cost = round(in_tok / 1e6 * price["input_per_mtok"] + out_tok / 1e6 * price["output_per_mtok"], 6)
meta["tokens"] = token_totals
meta["cost_usd_standard_price"] = cost

# ── 逐任务字段观测（关键 state 字段是否恒 None/路径是否进入）──
def _is_none(v):
    return v is None or v == "" or v == [] or v == {}

rows_obs = []
for r in details_all:
    rh = r.get("repair_history")
    et = r.get("execution_trace")
    rows_obs.append({
        "task_id": r.get("task_id"),
        "passed": r.get("passed"),
        "iterations": r.get("iterations"),
        "detection_rate": r.get("detection_rate"),
        "repair_rate": r.get("repair_rate"),
        "false_fix_rate": r.get("false_fix_rate"),
        "test_error_rate": r.get("test_error_rate"),
        "stop_reason": r.get("stop_reason"),
        "error_category": r.get("error_category"),
        "token_budget_capped": r.get("token_budget_capped"),
        "diagnosis_present": not _is_none(r.get("diagnosis")),
        "patch_present": not _is_none(r.get("patch")),
        "repair_history_len": len(rh) if isinstance(rh, list) else None,
        "execution_trace_len": len(et) if isinstance(et, list) else None,
        "spec_compile_rate": r.get("spec_compile_rate"),
        "spec_oracle_injected": r.get("spec_oracle_injected"),
        "spec_oracle_verdict": r.get("spec_oracle_verdict"),
        "spec_expr_coverage": r.get("spec_expr_coverage"),
        "spec_replace_applied": r.get("spec_replace_applied"),
        "specificity_gate_verdict": r.get("specificity_gate_verdict"),
        "detection_first_status": r.get("detection_first_status"),
        "rag_stats": r.get("rag_stats"),
        "cross_file_deps": r.get("cross_file_deps"),
        "task_metadata_keys": sorted((r.get("task_metadata") or {}).keys())[:40],
        "task_metadata_difficulty": (r.get("task_metadata") or {}).get("difficulty"),
        "task_metadata_is_cross_file": (r.get("task_metadata") or {}).get("is_cross_file"),
        "patched_files": len(re.findall(r"^--- ", str(r.get("patch") or ""), flags=re.MULTILINE)) or None,
        "harness_invalid": r.get("harness_invalid"),
    })
meta["rows"] = rows_obs
meta["field_none_counts"] = {
    key: sum(1 for row in rows_obs if _is_none(row.get(key)))
    for key in (
        "detection_rate", "repair_rate", "false_fix_rate", "stop_reason", "diagnosis_present",
        "patch_present", "spec_compile_rate", "spec_oracle_injected", "spec_oracle_verdict",
        "spec_expr_coverage", "rag_stats", "cross_file_deps", "task_metadata_difficulty",
    )
}

# ── 日志关键词命中（观察 vs 期望的原始证据；只记命中行行号与截断文本）──
log_text = ""
try:
    log_text = log.read_text(encoding="utf-8", errors="replace")
except OSError:
    pass
keywords = [
    "venv", "aitester_sandbox", "sandbox-exec", "Seatbelt", "内核沙箱", "沙箱",
    "rag", "RAG", "检索", "chroma", "Chroma",
    "预算", "超限", "budget", "BudgetExceeded", "cost_budget",
    "cross_file", "跨文件", "多文件",
    "降级", "未支持", "not supported", "不可用",
    "trace", "生成计划", "planner", "debugger", "补丁", "repair",
]
log_hits = {}
for kw in keywords:
    hits = [ln.rstrip() for ln in log_text.splitlines() if kw in ln]
    if hits:
        log_hits[kw] = {"count": len(hits), "examples": [h[:220] for h in hits[:3]]}
meta["log_keyword_hits"] = log_hits
meta["log_warnings_errors"] = [
    ln.rstrip()[:260] for ln in log_text.splitlines()
    if re.search(r"⚠️|WARNING|ERROR|Traceback|超时|失败", ln) and len(ln.strip()) > 0
][:40]

# ── trace 节点事件计数（证明节点真的进入：planner/generator/executor/debugger/…）──
node_counts: dict[str, int] = {}
event_counts: dict[str, int] = {}
trace_files = sorted(glob.glob(str(item / "traces" / "*.jsonl")))
for tf in trace_files:
    try:
        for line in Path(tf).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            n = ev.get("node")
            if n:
                node_counts[str(n)] = node_counts.get(str(n), 0) + 1
            e = ev.get("event")
            if e:
                event_counts[str(e)] = event_counts.get(str(e), 0) + 1
    except OSError:
        continue
meta["trace"] = {"files": len(trace_files), "node_event_counts": node_counts, "event_counts": event_counts}

# ── venv 缓存目录时间窗证据（venv 执行器路径是否真的创建/复用 venv）──
venv_root = Path(os.path.expanduser("~")) / ".cache" / "aitester" / "venvs"
venv_touched = []
if venv_root.is_dir():
    for p in sorted(venv_root.iterdir()):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if int(start_epoch) - 5 <= mt <= int(end_epoch) + 5:
            venv_touched.append({"name": p.name, "mtime": mt})
meta["venv_cache_touched_in_window"] = venv_touched[:20]

Path(out_meta).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[extract] {item.name}: batches={len(batches)} rows={len(rows_obs)} wall={meta['wall_seconds']}s "
      f"tokens={token_totals['total_tokens']} cost=${cost} trace_files={len(trace_files)} "
      f"venv_touched={len(venv_touched)}")
