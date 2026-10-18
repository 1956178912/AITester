#!/usr/bin/env python3
"""逐跑元数据抽取（零 LLM）：批次 JSON + 运行日志 → `seed<NN>/meta_<cell>.json`。

用法：
    extract_arm.py <batch_json> <label> <cell> <seed> <arm> <out_meta> <log_path> <trace_dir> <price_table> <batch_dir>

若 batch_json 为 "-" 或不存在（跑失败）：写 run_status=failed 的元数据（不伪造任何指标）。

meta 字段：
- run_status / rows / task_ids；逐任务行（detection_rate、llm_suite_detection_rate、passed、
  regeneration_count、stop_reason、token）；token_metrics；cost_usd_standard_price；
- provenance 摘要（git_sha、git_dirty、model_fingerprint 全块、关键 env_snapshot 子集、harness 子集）；
- 日志起止（START/END ISO+epoch、EXIT_CODE、WALL_SECONDS）。
stdout 打印一行机器可读摘要 `EXTRACT_OK ...`。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

(
    batch_path_s,
    label,
    cell,
    seed_s,
    arm,
    out_meta_s,
    log_path_s,
    trace_dir_s,
    price_path_s,
    batch_dir_s,
) = sys.argv[1:11]

batch_path = Path(batch_path_s)
out_meta = Path(out_meta_s)
log_path = Path(log_path_s)
trace_dir = Path(trace_dir_s)
batch_dir = Path(batch_dir_s)

ENV_KEYS = [
    "AITESTER_PROFILE",
    "TEMPERATURE",
    "LLM_THINKING_MODE",
    "BENCHMARK_PARALLELISM",
    "AITESTER_LLM_CACHE",
    "AITESTER_CACHE_NAMESPACE",
    "COST_BUDGET_ENABLE",
    "COST_BUDGET_TOKENS",
    "COST_BUDGET_USD",
    "AITESTER_BATCH_MAX_CALLS",
    "AITESTER_BATCH_MAX_USD",
    "DETECTION_FIRST_ENABLE",
    "DETECTION_FIRST_SECTION_ENABLE",
    "ENABLE_MUTATION_SCORING",
    "MAX_ITERATIONS",
    "MAX_REGENERATIONS",
    "EXECUTION_TIMEOUT",
    "LLM_TIMEOUT",
]
TASK_KEYS = [
    "detection_rate",
    "llm_suite_detection_rate",
    "passed",
    "coverage",
    "iterations",
    "stop_reason",
    "regeneration_count",
    "elapsed_seconds",
    "detection_first_status",
    "detection_first_red_seen",
    "error_category",
    "harness_invalid",
]


def _load_price() -> tuple[float | None, float | None]:
    try:
        price = json.loads(Path(price_path_s).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
        p_in = price.get("input_per_mtok")
        p_out = price.get("output_per_mtok")
        if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
            return float(p_in), float(p_out)
    except Exception:
        pass
    return None, None


def _parse_log() -> dict:
    out = {
        "log_path": str(log_path.resolve()) if log_path.exists() else str(log_path),
        "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.exists() else None,
        "start_iso_utc": None,
        "start_epoch": None,
        "end_iso_utc": None,
        "end_epoch": None,
        "exit_code": None,
        "wall_seconds": None,
    }
    if not log_path.exists():
        return out
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"START_ISO_UTC=(\S+) START_EPOCH=(\d+)", text)
    if m:
        out["start_iso_utc"], out["start_epoch"] = m.group(1), int(m.group(2))
    m = re.search(r"END_ISO_UTC=(\S+) END_EPOCH=(\d+) EXIT_CODE=(-?\d+) WALL_SECONDS=(\d+)", text)
    if m:
        out["end_iso_utc"] = m.group(1)
        out["end_epoch"] = int(m.group(2))
        out["exit_code"] = int(m.group(3))
        out["wall_seconds"] = int(m.group(4))
    return out


def _task_rows(rows: list[dict]) -> list[dict]:
    tasks: list[dict] = []
    for r in rows:
        tu = r.get("token_usage") or {}
        tasks.append(
            {
                "task_id": r.get("task_id"),
                **{k: r.get(k) for k in TASK_KEYS},
                "total_tokens": tu.get("total_tokens"),
                "llm_calls": tu.get("llm_calls"),
            }
        )
    return tasks


def main() -> int:
    seed = int(seed_s)
    price_in, price_out = _load_price()
    meta: dict = {
        "label": label,
        "cell": cell,
        "seed": seed,
        "arm": arm,
        "batch_dir": str(batch_dir.resolve()),
        "batch_path": None,
        "batch_sha256": None,
        "run_status": "failed",
        "rows": 0,
        "task_ids": [],
        "tasks": [],
        "token_metrics": {},
        "cost_usd_standard_price": None,
        "cost_price_basis": {
            "model": "deepseek-flash",
            "input_per_mtok": price_in,
            "output_per_mtok": price_out,
            "source": str(Path(price_path_s).resolve()) if Path(price_path_s).exists() else None,
        },
        "provenance": {},
        "run_log": _parse_log(),
        "trace_dir": str(trace_dir.resolve()) if trace_dir.exists() else str(trace_dir),
        "trace_files": len(list(trace_dir.glob("*.trace.jsonl"))) if trace_dir.is_dir() else 0,
        "failure_note": None,
    }

    if batch_path_s == "-" or not batch_path.exists():
        meta["failure_note"] = "批次 JSON 不存在（跑失败或超时）"
        out_meta.parent.mkdir(parents=True, exist_ok=True)
        out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EXTRACT_FAIL label={label} reason=no_batch_json")
        return 0

    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        meta["failure_note"] = f"批次 JSON 解析失败: {exc}"
        out_meta.parent.mkdir(parents=True, exist_ok=True)
        out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EXTRACT_FAIL label={label} reason=json_parse")
        return 0

    res = (batch.get("results") or {}).get(arm) or {}
    rows = res.get("details") or []
    tm = res.get("token_metrics") or {}
    prov = batch.get("provenance") or {}
    snap = prov.get("env_snapshot") or {}
    harness = prov.get("harness") or {}

    in_tok = tm.get("total_input_tokens")
    out_tok = tm.get("total_output_tokens")
    cost = None
    if price_in is not None and price_out is not None and isinstance(in_tok, (int, float)) and isinstance(out_tok, (int, float)):
        cost = round((in_tok * price_in + out_tok * price_out) / 1e6, 6)

    rows_status_ok = len(rows) == 87 and len({str(r.get("task_id")) for r in rows}) == 87
    meta.update(
        {
            "run_status": "ok" if rows_status_ok else ("anomaly_rows" if rows else "failed"),
            "batch_path": str(batch_path.resolve()),
            "batch_sha256": hashlib.sha256(batch_path.read_bytes()).hexdigest(),
            "batch_timestamp": batch.get("timestamp"),
            "n_tasks_requested": batch.get("total_tasks"),
            "rows": len(rows),
            "task_ids": [str(r.get("task_id")) for r in rows],
            "tasks": _task_rows(rows),
            "token_metrics": {
                "total_input_tokens": in_tok,
                "total_output_tokens": out_tok,
                "total_tokens": tm.get("total_tokens"),
                "avg_tokens_per_task": tm.get("avg_tokens_per_task"),
                "total_llm_calls": tm.get("total_llm_calls"),
            },
            "cost_usd_standard_price": cost,
            "provenance": {
                "git_sha": prov.get("git_sha"),
                "git_dirty": prov.get("git_dirty"),
                "dirty_reason": prov.get("dirty_reason"),
                "model_name": prov.get("model_name"),
                "model_fingerprint": prov.get("model_fingerprint"),
                "temperature": prov.get("temperature"),
                "max_iterations": prov.get("max_iterations"),
                "seed": prov.get("seed"),
                "profile": prov.get("profile"),
                "cache_enabled": prov.get("cache_enabled"),
                "cache_namespace": prov.get("cache_namespace"),
                "env_snapshot_subset": {k: snap.get(k) for k in ENV_KEYS},
                "harness": {
                    "snapshot_date": harness.get("snapshot_date"),
                    "model_version": harness.get("model_version"),
                    "retry_stop_rules": harness.get("retry_stop_rules"),
                    "per_task_time_limit_seconds": harness.get("per_task_time_limit_seconds"),
                },
                "valid_apis_redacted": prov.get("valid_apis"),
            },
            "summary": {
                "detected": sum(1 for r in rows if isinstance(r.get("detection_rate"), (int, float)) and not isinstance(r.get("detection_rate"), bool) and float(r["detection_rate"]) >= 1.0),
                "measurable": sum(1 for r in rows if isinstance(r.get("detection_rate"), (int, float)) and not isinstance(r.get("detection_rate"), bool)),
                "passed": sum(1 for r in rows if r.get("passed") is True),
                "regenerated_rows": sum(1 for r in rows if isinstance(r.get("regeneration_count"), (int, float)) and r.get("regeneration_count") > 0),
            },
        }
    )
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    s = meta["summary"]
    print(
        f"EXTRACT_OK label={label} rows={meta['rows']} det={s['detected']}/{s['measurable']} "
        f"cost_usd={cost} wall={meta['run_log']['wall_seconds']} exit={meta['run_log']['exit_code']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
