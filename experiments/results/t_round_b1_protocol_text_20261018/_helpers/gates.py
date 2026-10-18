#!/usr/bin/env python3
"""T2/B1 硬门禁（零 LLM）：6 份逐跑元数据 + PREFLIGHT → GATES.json。

用法：gates.py --out <OUT> --expect-sha <SHA>
退出码：0 = 无阻断项（可带 warning）；1 = 存在阻断项。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CELLS = ("C1", "C2", "C3")
SEEDS = (42, 44)
TAGS = {"C1": "plain_llm", "C2": "rt1", "C3": "df_full"}
EXPECTED_ENV = {
    "AITESTER_PROFILE": "logic",
    "LLM_THINKING_MODE": "disabled",
    "BENCHMARK_PARALLELISM": "4",
    "AITESTER_LLM_CACHE": "0",
    "COST_BUDGET_ENABLE": "true",
    "COST_BUDGET_TOKENS": "200000",
    "COST_BUDGET_USD": "1.0",
    "AITESTER_BATCH_MAX_CALLS": "4000",
    "AITESTER_BATCH_MAX_USD": "2.0",
}


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-sha", required=True)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    expect = args.expect_sha

    checks: list[dict] = []

    def chk(cid: str, ok: bool, detail, *, blocking: bool = True) -> None:
        checks.append({"id": cid, "ok": bool(ok), "detail": detail, "blocking": bool(blocking and not ok)})

    preflight = _load(out / "PREFLIGHT.json") or {}
    metas: dict[str, dict | None] = {}
    for seed in SEEDS:
        for cell in CELLS:
            metas[f"{cell}_seed{seed}"] = _load(out / f"seed{seed}" / f"meta_{cell}.json")

    # 1) 六份元数据与跑批状态
    chk("six_meta_present", all(v is not None for v in metas.values()), {k: v is not None for k, v in metas.items()})
    statuses = {k: (v or {}).get("run_status") for k, v in metas.items()}
    chk("all_runs_ok", all(s == "ok" for s in statuses.values()), statuses)

    # 2) 行数 / task_id 唯一
    rows_ok = {}
    for k, v in metas.items():
        if not v:
            rows_ok[k] = {"rows": None}
            continue
        tids = v.get("task_ids") or []
        rows_ok[k] = {"rows": len(tids), "unique": len(set(tids))}
    chk("rows_87_and_unique", all(x.get("rows") == 87 and x.get("unique") == 87 for x in rows_ok.values()), rows_ok)

    # 3) 同 seed 三格 task_id 集合一致
    set_ok = {}
    for seed in SEEDS:
        sets = []
        for cell in CELLS:
            m = metas[f"{cell}_seed{seed}"]
            sets.append(set((m or {}).get("task_ids") or []))
        set_ok[str(seed)] = {"equal": sets[0] == sets[1] == sets[2], "sizes": [len(s) for s in sets]}
    chk("task_sets_identical_within_seed", all(v["equal"] for v in set_ok.values()), set_ok)

    # 4) provenance：干净树 + 切点
    prov = {k: ((v or {}).get("provenance") or {}) for k, v in metas.items()}
    git_ok = {k: {"git_sha": p.get("git_sha"), "git_dirty": p.get("git_dirty")} for k, p in prov.items()}
    chk("provenance_sha_matches_cut", all(p.get("git_sha") == expect for p in prov.values()), git_ok)
    chk("provenance_clean_tree", all(p.get("git_dirty") is False for p in prov.values()), git_ok)

    # 5) 模型指纹块在场（pinned=false 只记 warning：provider 可能不返回 system_fingerprint）
    fp = {k: p.get("model_fingerprint") for k, p in prov.items()}
    fp_present = {k: isinstance(v, dict) and len(v) > 0 for k, v in fp.items()}
    chk("model_fingerprint_present", all(fp_present.values()), fp_present)
    pinned = {k: (v or {}).get("pinned") for k, v in fp.items()}
    if pinned and all(v is True for v in pinned.values()):
        chk("model_fingerprint_pinned", True, pinned, blocking=False)
    else:
        chk("model_fingerprint_pinned", False, {"pinned": pinned, "missing": {k: (v or {}).get("missing") for k, v in fp.items()}}, blocking=False)

    # 6) 干预开关生效性（从工件 env_snapshot 逐位证明）
    env_ok = {}
    for seed in SEEDS:
        for cell in CELLS:
            key = f"{cell}_seed{seed}"
            v = metas[key] or {}
            snap = ((v.get("provenance") or {}).get("env_snapshot_subset") or {})
            ns = ((v.get("provenance") or {}).get("cache_namespace"))
            env_ok[key] = {
                "DETECTION_FIRST_SECTION_ENABLE": snap.get("DETECTION_FIRST_SECTION_ENABLE"),
                "cache_namespace": ns,
                "expected_namespace": f"t_b1_{cell}_{seed}",
                "cache_enabled": (v.get("provenance") or {}).get("cache_enabled"),
                "temperature": (v.get("provenance") or {}).get("temperature"),
            }
    section_ok = all(
        (
            (env_ok[f"C2_seed{s}"]["DETECTION_FIRST_SECTION_ENABLE"] == "false")
            and (env_ok[f"C1_seed{s}"]["DETECTION_FIRST_SECTION_ENABLE"] != "false")
            and (env_ok[f"C3_seed{s}"]["DETECTION_FIRST_SECTION_ENABLE"] != "false")
        )
        for s in SEEDS
    )
    chk("intervention_section_switch_in_artifact", section_ok, env_ok)
    ns_ok = all(v["cache_namespace"] == v["expected_namespace"] for v in env_ok.values())
    chk("cache_namespaces_isolated", ns_ok, {k: {"actual": v["cache_namespace"], "expected": v["expected_namespace"]} for k, v in env_ok.items()})
    cache_off = all(v["cache_enabled"] is False for v in env_ok.values())
    chk("cache_disabled", cache_off, {k: v["cache_enabled"] for k, v in env_ok.items()}, blocking=False)
    temp_ok = all(v["temperature"] == 0.0 for v in env_ok.values())
    chk("temperature_zero", temp_ok, {k: v["temperature"] for k, v in env_ok.items()})
    # PREREG_CONTINUATION.md 执行性修订：六跑均以 ENABLE_MUTATION_SCORING=false 跑（只关批后辅助测量）
    mut_vals = {k: (((metas[k] or {}).get("provenance") or {}).get("env_snapshot_subset") or {}).get("ENABLE_MUTATION_SCORING") for k in metas}
    chk("mutation_scoring_disabled_all_runs", all(v == "false" for v in mut_vals.values()), mut_vals)

    # 7) 预算 / 墙钟
    costs = {k: (v or {}).get("cost_usd_standard_price") for k, v in metas.items()}
    cost_total = round(sum(c for c in costs.values() if isinstance(c, (int, float))), 6)
    walls = {k: ((v or {}).get("run_log") or {}).get("wall_seconds") for k, v in metas.items()}
    wall_total = sum(w for w in walls.values() if isinstance(w, (int, float)))
    chk("cost_total_under_budget_2usd", cost_total <= 2.0, {"cost_total_usd": cost_total, "per_run": costs})
    chk("wall_total_under_90min", wall_total <= 5400, {"wall_total_seconds": wall_total, "per_run": walls})

    # 8) 预注册 sha 与 dry-run 一致
    prereg_now = None
    prereg_path = out / "PREREG.md"
    if prereg_path.is_file():
        import hashlib

        prereg_now = hashlib.sha256(prereg_path.read_bytes()).hexdigest()
    prereg_ok = bool(preflight.get("prereg", {}).get("sha256")) and prereg_now == preflight["prereg"]["sha256"]
    chk("prereg_hash_unchanged", prereg_ok, {"preflight": preflight.get("prereg", {}).get("sha256"), "now": prereg_now})

    # 9) 旧批基线可复算（并排对照取证基础；非阻断）
    old = preflight.get("old_baseline_20261009") or {}
    old_expected = {"plain_llm": 9, "rt1": 10, "df_full": 27}
    old_ok = all((old.get(n) or {}).get("detected") == old_expected[n] for n in old_expected)
    chk("old_baseline_recomputable", old_ok, {n: (old.get(n) or {}).get("detected") for n in old_expected}, blocking=False)

    blocking = [c["id"] for c in checks if c["blocking"]]
    warnings = [c["id"] for c in checks if not c["ok"] and not c["blocking"]]
    status = "fail" if blocking else ("pass_with_warnings" if warnings else "pass")
    payload = {
        "schema": "t2_b1_protocol_text_gates/1",
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "status": status,
        "blocking": blocking,
        "warnings": warnings,
        "checks": checks,
        "evidence_quality": {
            "clean_tree_and_cut_sha": all(p.get("git_dirty") is False and p.get("git_sha") == expect for p in prov.values()),
            "model_fingerprint_present": all(fp_present.values()),
            "model_fingerprint_pinned_all": bool(pinned) and all(v is True for v in pinned.values()),
            "note": "pinned=false 表示 provider 未返回 system_fingerprint：指纹块在场但未锁定模型快照，不得称『指纹级（pinned）』",
            "execution_amendment": "PREREG_CONTINUATION.md：判据未改；首跑因批后 mutation/MDO 辅助测量墙钟超预期被中止（日志见 _superseded_first_attempt/，无主终点数据损失），六格以 ENABLE_MUTATION_SCORING=false 统一重跑",
        },
    }
    (out / "GATES.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gates] status={status} blocking={blocking} warnings={warnings}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
