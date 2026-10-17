"""两臂核验：provenance/env_snapshot、字段完整率、LLM-suite 一致性、注入/verdict 分布。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

out, root, arm_baseline, git_head = sys.argv[1:5]
out = Path(out)
meta_a = json.loads((out / "arm_control.meta.json").read_text(encoding="utf-8"))
meta_b = json.loads((out / "arm_oracle.meta.json").read_text(encoding="utf-8"))
issues: list[str] = []
warnings: list[str] = []

# provenance
for meta, expected_oracle in ((meta_a, None), (meta_b, "true")):
    prov = meta.get("provenance") or {}
    fp = prov.get("model_fingerprint") or {}
    label = meta["arm_label"]
    if prov.get("git_dirty") is True:
        issues.append(f"{label}: provenance.git_dirty=true")
    if str(prov.get("git_sha")) != git_head:
        issues.append(f"{label}: git_sha={prov.get('git_sha')} ≠ 切点 {git_head}")
    if fp.get("pinned") is not True:
        warnings.append(f"{label}: 模型指纹 pinned≠true（{fp.get('pinned')}）")
    snap = prov.get("env_snapshot_spec_oracle_exec_enable")
    if expected_oracle is not None and str(snap).lower() != expected_oracle:
        issues.append(f"{label}: env_snapshot.SPEC_ORACLE_EXEC_ENABLE={snap!r}，期望 {expected_oracle!r}")
    if expected_oracle is None and snap not in (None, "", "false", "False"):
        issues.append(f"{label}: control 臂 env_snapshot.SPEC_ORACLE_EXEC_ENABLE={snap!r}，期望未设")
    if prov.get("env_snapshot_detection_spec_mode") not in (None, ""):
        issues.append(f"{label}: 不应设置 DETECTION_SPEC_MODE，实际 {prov.get('env_snapshot_detection_spec_mode')!r}")

# 字段完整率
for meta in (meta_a, meta_b):
    rows = meta["rows"]
    bad = {k: v for k, v in (meta.get("field_completeness") or {}).items() if v != f"{rows}/{rows}"}
    if bad:
        issues.append(f"{meta['arm_label']}: 行字段不完整 {bad}")

# LLM-suite 一致性（逐任务）
per_a = meta_a.get("per_task_llm_suite") or {}
per_b = meta_b.get("per_task_llm_suite") or {}
common = sorted(set(per_a) & set(per_b))
mismatch = []
for tid in common:
    a = per_a[tid].get("llm_suite_detection_rate")
    b = per_b[tid].get("llm_suite_detection_rate")
    if a != b:
        mismatch.append({"task_id": tid, "control": a, "oracle": b})
only_a = sorted(set(per_a) - set(per_b))
only_b = sorted(set(per_b) - set(per_a))

def _detection(meta):
    m = meta.get("llm_suite_detection") or {}
    return {"measurable": m.get("measurable"), "detected": m.get("detected"),
            "rate": round(m["detected"] / m["measurable"], 4) if m.get("measurable") else None}

comparison = {
    "arm_baseline": arm_baseline,
    "git_head": git_head,
    "control": {
        "rows": meta_a["rows"], "tokens": meta_a.get("token_metrics"),
        "cost_usd_standard_price": meta_a.get("cost_usd_standard_price"),
        "llm_suite_detection": _detection(meta_a),
        "spec_oracle_injected_counts": meta_a.get("spec_oracle_injected_counts"),
        "spec_oracle_verdict_counts": meta_a.get("spec_oracle_verdict_counts"),
        "oracle_suite_verdict_counts": meta_a.get("oracle_suite_verdict_counts"),
        "batch_sha256": meta_a.get("batch_sha256"),
        "env_snapshot_spec_oracle_exec_enable": (meta_a.get("provenance") or {}).get("env_snapshot_spec_oracle_exec_enable"),
    },
    "oracle": {
        "rows": meta_b["rows"], "tokens": meta_b.get("token_metrics"),
        "cost_usd_standard_price": meta_b.get("cost_usd_standard_price"),
        "llm_suite_detection": _detection(meta_b),
        "spec_oracle_injected_counts": meta_b.get("spec_oracle_injected_counts"),
        "spec_oracle_verdict_counts": meta_b.get("spec_oracle_verdict_counts"),
        "oracle_suite_verdict_counts": meta_b.get("oracle_suite_verdict_counts"),
        "batch_sha256": meta_b.get("batch_sha256"),
        "env_snapshot_spec_oracle_exec_enable": (meta_b.get("provenance") or {}).get("env_snapshot_spec_oracle_exec_enable"),
    },
    "llm_suite_consistency": {
        "common_tasks": len(common), "mismatch_count": len(mismatch), "mismatches": mismatch,
        "only_in_control": only_a, "only_in_oracle": only_b,
    },
    "issues": issues,
    "warnings": warnings,
}
(out / "ARM_COMPARISON.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "control": comparison["control"]["llm_suite_detection"],
    "oracle": comparison["oracle"]["llm_suite_detection"],
    "consistency": comparison["llm_suite_consistency"],
    "control_injected": comparison["control"]["spec_oracle_injected_counts"],
    "oracle_injected": comparison["oracle"]["spec_oracle_injected_counts"],
    "oracle_verdict": comparison["oracle"]["spec_oracle_verdict_counts"],
    "oracle_suite": comparison["oracle"]["oracle_suite_verdict_counts"],
    "issues": issues, "warnings": warnings,
}, ensure_ascii=False, indent=2))
raise SystemExit(0 if not issues else 1)