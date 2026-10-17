"""逐臂元数据抽取（零 LLM）：tokens/成本/注入与 verdict 分布/字段完整率/env_snapshot。"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

batch_path, arm_label, arm_baseline, ns, oracle_enabled, price_path, out_path = sys.argv[1:8]
data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
rd = (data.get("results") or {}).get(arm_baseline) or {}
rows = rd.get("details") or []
tm = rd.get("token_metrics") or {}
prov = data.get("provenance") or {}
try:
    price = (json.loads(Path(price_path).read_text(encoding="utf-8")).get("models") or {}).get(prov.get("model_name") or "") or {}
except (OSError, ValueError):
    price = {}
cost = None
if isinstance(price.get("input_per_mtok"), (int, float)) and isinstance(price.get("output_per_mtok"), (int, float)):
    cost = round(
        float(tm.get("total_input_tokens") or 0) / 1e6 * price["input_per_mtok"]
        + float(tm.get("total_output_tokens") or 0) / 1e6 * price["output_per_mtok"], 6
    )

required = ("spec_oracle_injected", "spec_oracle_verdict", "oracle_suite_verdict",
            "llm_suite_detection_rate", "detection_rate")
field_complete = {k: sum(1 for r in rows if k in r) for k in required}
injected_counts: dict[str, int] = {}
verdict_counts: dict[str, int] = {}
oracle_suite_counts: dict[str, int] = {}
for r in rows:
    iv = str(r.get("spec_oracle_injected"))
    injected_counts[iv] = injected_counts.get(iv, 0) + 1
    vv = str(r.get("spec_oracle_verdict"))
    verdict_counts[vv] = verdict_counts.get(vv, 0) + 1
    ov = str(r.get("oracle_suite_verdict"))
    oracle_suite_counts[ov] = oracle_suite_counts.get(ov, 0) + 1

meta = {
    "arm_label": arm_label,
    "arm_baseline": arm_baseline,
    "cache_namespace": ns,
    "spec_oracle_exec_enabled_requested": oracle_enabled,
    "batch_file": str(batch_path),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
    "provenance": {
        "git_sha": prov.get("git_sha"), "git_dirty": prov.get("git_dirty"),
        "dirty_reason": prov.get("dirty_reason"),
        "model_name": prov.get("model_name"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "temperature": prov.get("temperature"), "profile": prov.get("profile"),
        "env_snapshot_spec_oracle_exec_enable": (prov.get("env_snapshot") or {}).get("SPEC_ORACLE_EXEC_ENABLE"),
        "env_snapshot_cache_namespace": (prov.get("env_snapshot") or {}).get("AITESTER_CACHE_NAMESPACE"),
        "env_snapshot_detection_spec_mode": (prov.get("env_snapshot") or {}).get("DETECTION_SPEC_MODE"),
    },
    "field_completeness": {k: f"{v}/{len(rows)}" for k, v in field_complete.items()},
    "spec_oracle_injected_counts": injected_counts,
    "spec_oracle_verdict_counts": verdict_counts,
    "oracle_suite_verdict_counts": oracle_suite_counts,
    "llm_suite_detection": {
        "measurable": sum(1 for r in rows if r.get("llm_suite_detection_rate") is not None),
        "detected": sum(1 for r in rows if r.get("llm_suite_detection_rate") == 1.0),
    },
    "per_task_llm_suite": {
        str(r.get("task_id")): {
            "detection_rate": r.get("detection_rate"),
            "llm_suite_detection_rate": r.get("llm_suite_detection_rate"),
            "spec_oracle_injected": r.get("spec_oracle_injected"),
            "spec_oracle_verdict": r.get("spec_oracle_verdict"),
            "oracle_suite_verdict": r.get("oracle_suite_verdict"),
        }
        for r in rows
    },
}
Path(out_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{arm_label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} "
      f"injected={injected_counts} oracle_suite={oracle_suite_counts}")
