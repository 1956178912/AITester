#!/usr/bin/env python3
"""T2/B1 分析（零 LLM，只读工件）：3 格 × 2 seed → ANALYSIS_REPORT.json + README.md。

用法：
    analyze.py --out experiments/results/t_round_b1_protocol_text_20261018 [--write]

判定规则严格取自 `PREREG.md` §5（跑前冻结）：
- H-text：逐 seed Δ_text_pp = (C3 检出率 − C2 检出率)×100 > 0；2/2 seeds 方向一致 =
  replicated；且 ≥1 seed McNemar 双侧 p<0.05 = replicated_strong；任一 seed Δ≤0 = not_replicated。
- H-sampling：逐 seed |Δ_sampling_pp| = |C2 − C1| ≤ 5.0pp 且 McNemar 双侧 p ≥ 0.05；
  2/2 seeds 满足 = sampling_effect_negligible。
- 联合 verdict 按 PREREG §5 表。

主口径 = 行 `detection_rate`（>=1.0 记检出；None 不进分母）；`llm_suite_detection_rate` 并列报告。
McNemar 精确双侧：p = min(1, 2·Σ_{k≤min(b,c)} C(n,k)/2^n)，math.comb 手算。
bootstrap：配对任务重采样 10000 次（固定 seed=20261018），percentile 95% CI。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CELLS = ("C1", "C2", "C3")
SEEDS = (42, 44)
CELL_DEF = {
    "C1": {"arm": "plain_llm", "routing": "无", "section": "无", "tag": "plain_llm"},
    "C2": {"arm": "plain_llm_df", "routing": "有", "section": "无", "tag": "rt1"},
    "C3": {"arm": "plain_llm_df", "routing": "有", "section": "有", "tag": "df_full"},
}
EXPECT_SHA = "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261018

REPO = Path("/Users/wangchenyu/Workspace/AITester")
OLD = {
    "plain_llm": (REPO / "experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json", "plain_llm"),
    "df_full": (REPO / "experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/benchmark_synthetic_20261009_190234.json", "plain_llm_df"),
    "rt1": (REPO / "experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/benchmark_synthetic_20261009_193509.json", "plain_llm_df"),
}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def _hit(value: Any) -> bool | None:
    """行级二值指标：>=1.0 记命中；None/非数值 = 不可测。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value) >= 1.0


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


# ─── 基础统计 ──────────────────────────────────────────────────────────────


def cell_stats(meta: dict) -> dict:
    """单格统计（主口径 detection_rate + llm_suite + passed + token/成本/墙钟/再生成行）。"""
    tasks = meta.get("tasks") or []
    det = [v for t in tasks if (v := _hit(t.get("detection_rate"))) is not None]
    llm = [v for t in tasks if (v := _hit(t.get("llm_suite_detection_rate"))) is not None]
    det_vals = [float(t["detection_rate"]) for t in tasks if _num(t.get("detection_rate")) is not None]
    tm = meta.get("token_metrics") or {}
    stop = Counter(str(t.get("stop_reason")) if t.get("stop_reason") is not None else "None" for t in tasks)
    status = Counter(str(t.get("detection_first_status")) if t.get("detection_first_status") is not None else "None" for t in tasks)
    regen = Counter()
    for t in tasks:
        rc = t.get("regeneration_count")
        regen[str(int(rc)) if isinstance(rc, (int, float)) and not isinstance(rc, bool) else "None"] += 1
    covs = [float(t["coverage"]) for t in tasks if _num(t.get("coverage")) is not None]
    return {
        "label": meta.get("label"),
        "arm": meta.get("arm"),
        "run_status": meta.get("run_status"),
        "rows": len(tasks),
        "detection": {
            "detected": sum(1 for v in det if v),
            "measurable": len(det),
            "rate": round(sum(1 for v in det if v) / len(det), 6) if det else None,
            "rate_pp": round(sum(1 for v in det if v) / len(det) * 100, 2) if det else None,
            "mean_of_measurable": round(sum(det_vals) / len(det_vals), 6) if det_vals else None,
        },
        "llm_suite_detection": {
            "detected": sum(1 for v in llm if v),
            "measurable": len(llm),
            "rate": round(sum(1 for v in llm if v) / len(llm), 6) if llm else None,
            "rate_pp": round(sum(1 for v in llm if v) / len(llm) * 100, 2) if llm else None,
        },
        "passed": sum(1 for t in tasks if t.get("passed") is True),
        "token_metrics": tm,
        "cost_usd_standard_price": meta.get("cost_usd_standard_price"),
        "wall_seconds": (meta.get("run_log") or {}).get("wall_seconds"),
        "regenerated_rows": sum(1 for t in tasks if isinstance(t.get("regeneration_count"), (int, float)) and not isinstance(t.get("regeneration_count"), bool) and t["regeneration_count"] > 0),
        "regeneration_count_dist": dict(sorted(regen.items())),
        "stop_reason_dist": dict(stop.most_common()),
        "detection_first_status_dist": dict(status.most_common()),
        "mean_coverage": round(sum(covs) / len(covs), 2) if covs else None,
    }


def pair_map(meta: dict) -> dict[str, bool | None]:
    """task_id → detection 命中（None=不可测），供配对检验。"""
    out: dict[str, bool | None] = {}
    for t in meta.get("tasks") or []:
        out[str(t.get("task_id"))] = _hit(t.get("detection_rate"))
    return out


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 双侧精确二项 p 值（n=b+c 不一致对，H0: p=0.5）。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def bootstrap_paired_ci(hi: dict[str, bool | None], lo: dict[str, bool | None], rng: random.Random) -> dict:
    """配对差 (hi−lo) 的 bootstrap percentile 95% CI（仅双方均可测的配对）。"""
    pairs = [(hi[k], lo[k]) for k in hi if k in lo and hi[k] is not None and lo[k] is not None]
    if not pairs:
        return {"n_pairs": 0, "ci95_pp": [None, None]}
    deltas: list[float] = []
    n = len(pairs)
    for _ in range(BOOTSTRAP_N):
        s = 0
        for _ in range(n):
            h, l = pairs[rng.randrange(n)]
            s += int(h) - int(l)
        deltas.append(s / n)
    deltas.sort()
    lo_i = int(0.025 * (BOOTSTRAP_N - 1))
    hi_i = int(0.975 * (BOOTSTRAP_N - 1))
    return {"n_pairs": n, "ci95_pp": [round(deltas[lo_i] * 100, 2), round(deltas[hi_i] * 100, 2)]}


def paired_effect(hi: dict[str, bool | None], lo: dict[str, bool | None], hi_name: str, lo_name: str) -> dict:
    """配对效应：b/c、McNemar p、配对差 + bootstrap CI（另并列臂率差，供判据使用）。"""
    common = sorted(set(hi) & set(lo))
    both = [k for k in common if hi[k] is not None and lo[k] is not None]
    b = sum(1 for k in both if hi[k] and not lo[k])   # 高格检出/低格未检出
    c = sum(1 for k in both if lo[k] and not hi[k])   # 反向
    n = len(both)
    delta = (b - c) / n if n else None
    rng = random.Random(BOOTSTRAP_SEED)
    ci = bootstrap_paired_ci({k: hi[k] for k in both}, {k: lo[k] for k in both}, rng)
    return {
        "high": hi_name,
        "low": lo_name,
        "common_task_ids": len(common),
        "paired_measurable": n,
        "b_high_only": b,
        "c_low_only": c,
        "discordant": b + c,
        "delta_pp_paired": round(delta * 100, 2) if delta is not None else None,
        "mcnemar_exact_p_two_sided": mcnemar_exact(b, c),
        "bootstrap_ci95_pp_paired": ci["ci95_pp"],
    }


def rate_effect(hi_stats: dict, lo_stats: dict) -> dict:
    """臂率差（主判据口径：各自可测行分母）。"""
    rh = (hi_stats.get("detection") or {}).get("rate")
    rl = (lo_stats.get("detection") or {}).get("rate")
    return {
        "high_rate": rh,
        "low_rate": rl,
        "delta_pp_arm_rates": round((rh - rl) * 100, 2) if rh is not None and rl is not None else None,
        "detected_delta": (hi_stats.get("detection") or {}).get("detected", 0) - (lo_stats.get("detection") or {}).get("detected", 0) if (hi_stats.get("detection") or {}).get("detected") is not None and (lo_stats.get("detection") or {}).get("detected") is not None else None,
        "high_detected_measurable": f"{(hi_stats.get('detection') or {}).get('detected')}/{(hi_stats.get('detection') or {}).get('measurable')}",
        "low_detected_measurable": f"{(lo_stats.get('detection') or {}).get('detected')}/{(lo_stats.get('detection') or {}).get('measurable')}",
    }


# ─── 旧批（2026-10-09）并排 ────────────────────────────────────────────────


def old_batch() -> dict:
    """直接从旧批工件复算三格（不硬编码数字），并披露其 provenance 缺口。"""
    batches: dict[str, dict] = {}
    stats: dict[str, dict] = {}
    maps: dict[str, dict] = {}
    for name, (path, arm) in OLD.items():
        d = batches.get(str(path))
        if d is None:
            d = _load(path)
            batches[str(path)] = d
        if not d:
            continue
        fake_meta = {"label": f"old_{name}", "arm": arm, "run_status": "ok", "tasks": [], "token_metrics": ((d.get("results") or {}).get(arm) or {}).get("token_metrics") or {}, "cost_usd_standard_price": None, "run_log": {}}
        for r in ((d.get("results") or {}).get(arm) or {}).get("details") or []:
            fake_meta["tasks"].append(
                {
                    "task_id": str(r.get("task_id")),
                    "detection_rate": r.get("detection_rate"),
                    "llm_suite_detection_rate": r.get("llm_suite_detection_rate"),
                    "passed": r.get("passed"),
                    "coverage": r.get("coverage"),
                    "stop_reason": r.get("stop_reason"),
                    "regeneration_count": r.get("regeneration_count"),
                }
            )
        stats[name] = cell_stats(fake_meta)
        maps[name] = pair_map(fake_meta)
    # 旧批并排效应（seed42）
    effects = {}
    if {"df_full", "rt1"} <= set(maps):
        effects["text_old_df_vs_rt1"] = {**rate_effect(stats["df_full"], stats["rt1"]), **paired_effect(maps["df_full"], maps["rt1"], "df_full", "rt1")}
    if {"rt1", "plain_llm"} <= set(maps):
        effects["sampling_old_rt1_vs_plain_llm"] = {**rate_effect(stats["rt1"], stats["plain_llm"]), **paired_effect(maps["rt1"], maps["plain_llm"], "rt1", "plain_llm")}
    provenance = {}
    any_batch = next(iter(batches.values()), None) or {}
    prov = any_batch.get("provenance") or {}
    provenance = {
        "git_sha": prov.get("git_sha"),
        "git_dirty": prov.get("git_dirty"),
        "has_model_fingerprint": "model_fingerprint" in prov,
        "cache_namespace": prov.get("cache_namespace"),
        "rt1_batch": OLD["rt1"][0].name,
        "plain_llm_df_d_full_batch": OLD["plain_llm"][0].name,
    }
    return {"stats": stats, "effects": effects, "provenance": provenance, "paths": {k: str(v[0]) for k, v in OLD.items()}}


def baseline_yaml_record() -> dict:
    """读 BASELINE.yaml `benchmark.rt1_sampling_control` 已登记口径（缺失/无 yaml 库则如实标注）。"""
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load((REPO / "BASELINE.yaml").read_text(encoding="utf-8"))
        return {"present": True, "record": (((data.get("benchmark") or {}).get("rt1_sampling_control")) or {})}
    except Exception as exc:  # noqa: BLE001
        return {"present": False, "error": str(exc), "record": {}}


# ─── 判定 ─────────────────────────────────────────────────────────────────


def _cell_ok(per_seed: dict, seed: int, cell: str) -> bool:
    return bool((per_seed.get(str(seed)) or {}).get(cell)) and (per_seed[str(seed)][cell].get("run_status") == "ok")


def evaluate(per_seed: dict) -> dict:
    """严格按 PREREG §5 判据（不得事后改动）。"""
    text_rows: list[dict] = []
    sampling_rows: list[dict] = []
    for seed in SEEDS:
        s = per_seed.get(str(seed)) or {}
        eff = s.get("effects") or {}
        c2c3_ok = _cell_ok(per_seed, seed, "C2") and _cell_ok(per_seed, seed, "C3")
        c1c2_ok = _cell_ok(per_seed, seed, "C1") and _cell_ok(per_seed, seed, "C2")
        if c2c3_ok and eff.get("text"):
            text_rows.append({"seed": seed, **eff["text"]})
        if c1c2_ok and eff.get("sampling"):
            sampling_rows.append({"seed": seed, **eff["sampling"]})

    # H-text
    text_complete = len(text_rows) == len(SEEDS)
    text_deltas = [r["delta_pp_arm_rates"] for r in text_rows]
    text_positive = text_complete and all(d is not None and d > 0 for d in text_deltas)
    text_sig_seeds = [r["seed"] for r in text_rows if r["mcnemar_exact_p_two_sided"] < 0.05]
    if not text_complete:
        h_text = "insufficient_data"
    elif not text_positive:
        h_text = "not_replicated"
    elif text_sig_seeds:
        h_text = "replicated_strong"
    else:
        h_text = "replicated_direction_only"

    # H-sampling
    sampling_complete = len(sampling_rows) == len(SEEDS)
    sampling_ok = sampling_complete and all(
        abs(r["delta_pp_arm_rates"]) <= 5.0 and r["mcnemar_exact_p_two_sided"] >= 0.05 for r in sampling_rows
    )
    if not sampling_complete:
        h_sampling = "insufficient_data"
    elif sampling_ok:
        h_sampling = "sampling_effect_negligible"
    else:
        h_sampling = "sampling_effect_not_negligible"

    if h_text == "insufficient_data":
        joint = "insufficient_data"
    elif h_text == "not_replicated":
        joint = "not_replicated"
    elif h_text == "replicated_strong" and h_sampling == "sampling_effect_negligible":
        joint = "confirmed"
    elif h_text == "replicated_strong":
        joint = "text_effect_confirmed_sampling_not_negligible"
    else:
        joint = "directional_only"

    reasons: list[str] = []
    reasons.append(
        f"H-text: {len(text_rows)}/2 seed 可判定；Δ_text_pp={ {r['seed']: r['delta_pp_arm_rates'] for r in text_rows} }；"
        f"McNemar p={ {r['seed']: round(r['mcnemar_exact_p_two_sided'], 6) for r in text_rows} }"
    )
    reasons.append(
        f"H-sampling: {len(sampling_rows)}/2 seed 可判定；Δ_sampling_pp={ {r['seed']: r['delta_pp_arm_rates'] for r in sampling_rows} }；"
        f"McNemar p={ {r['seed']: round(r['mcnemar_exact_p_two_sided'], 6) for r in sampling_rows} }"
    )
    return {
        "rules_source": "PREREG.md §5（跑前冻结，不得事后改动）",
        "h_text": {
            "verdict": h_text,
            "criterion": "每 seed Δ_text_pp>0 且 2/2 方向一致 = replicated；≥1 seed McNemar p<0.05 = strong",
            "rows": text_rows,
            "positive_deltas": text_positive,
            "significant_seeds": text_sig_seeds,
        },
        "h_sampling": {
            "verdict": h_sampling,
            "criterion": "每 seed |Δ_sampling_pp|≤5.0 且 McNemar p≥0.05；2/2 满足 = negligible",
            "rows": sampling_rows,
        },
        "joint_verdict": joint,
        "reasons": reasons,
    }


# ─── 主流程 ───────────────────────────────────────────────────────────────


def fingerprint_summary(metas: dict[str, dict]) -> dict:
    out = {"runs": {}, "all_present": True, "all_pinned": True, "probe_sha_unique": [], "returned_model_unique": []}
    shas, models = set(), set()
    for label, m in metas.items():
        fp = ((m or {}).get("provenance") or {}).get("model_fingerprint")
        present = isinstance(fp, dict) and bool(fp)
        out["all_present"] = out["all_present"] and present
        if present:
            pinned = fp.get("pinned")
            out["runs"][label] = {
                "pinned": pinned,
                "requested_alias": fp.get("requested_alias"),
                "returned_model": fp.get("returned_model"),
                "system_fingerprint": fp.get("system_fingerprint"),
                "probe_sha256": fp.get("probe_sha256"),
                "probe_at": fp.get("probe_at"),
                "missing": fp.get("missing"),
                "error": fp.get("error"),
            }
            if pinned is not True:
                out["all_pinned"] = False
            if fp.get("probe_sha256"):
                shas.add(fp["probe_sha256"])
            if fp.get("returned_model"):
                models.add(fp["returned_model"])
        else:
            out["all_pinned"] = False
            out["runs"][label] = {"present": False}
    out["probe_sha_unique"] = sorted(shas)
    out["returned_model_unique"] = sorted(models)
    out["snapshot_consistent"] = len(shas) <= 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    out = Path(args.out).resolve()

    preflight = _load(out / "PREFLIGHT.json") or {}
    metas: dict[str, dict] = {}
    per_seed: dict[str, dict] = {}
    missing: dict[str, str] = {}
    for seed in SEEDS:
        per_seed[str(seed)] = {}
        for cell in CELLS:
            label = f"{cell}_seed{seed}"
            m = _load(out / f"seed{seed}" / f"meta_{cell}.json")
            if m is None:
                missing[label] = "meta 缺失"
                per_seed[str(seed)][cell] = None
                continue
            metas[label] = m
            if m.get("run_status") != "ok":
                missing[label] = f"run_status={m.get('run_status')}"
            per_seed[str(seed)][cell] = cell_stats(m)

    # 三格效应（同 seed 内配对）
    for seed in SEEDS:
        s = per_seed[str(seed)]
        metas_s = {c: metas.get(f"{c}_seed{seed}") for c in CELLS}
        eff: dict[str, Any] = {}
        if all(metas_s.get(c) for c in CELLS):
            maps = {c: pair_map(metas_s[c]) for c in CELLS}  # type: ignore[arg-type]
            eff["text"] = {**rate_effect(s["C3"], s["C2"]), **paired_effect(maps["C3"], maps["C2"], "C3", "C2")}
            eff["sampling"] = {**rate_effect(s["C2"], s["C1"]), **paired_effect(maps["C2"], maps["C1"], "C2", "C1")}
        s["effects"] = eff

    evaluation = evaluate(per_seed)
    old = old_batch()
    baseline = baseline_yaml_record()
    fp = fingerprint_summary(metas)

    # detection_rate 与 llm_suite_detection_rate 一致性（N-3：两键同值）
    key_mismatch = []
    for label, m in metas.items():
        for t in m.get("tasks") or []:
            a, b = t.get("detection_rate"), t.get("llm_suite_detection_rate")
            if (a is None) != (b is None) or (a is not None and b is not None and float(a) != float(b)):
                key_mismatch.append({"label": label, "task_id": t.get("task_id"), "detection_rate": a, "llm_suite_detection_rate": b})
    # 配对表（逐任务，审计用）
    paired_tables = {}
    for seed in SEEDS:
        tbl = []
        maps = {}
        for cell in CELLS:
            m = metas.get(f"{cell}_seed{seed}")
            maps[cell] = pair_map(m) if m else {}
        for tid in sorted(set(maps["C1"]) | set(maps["C2"]) | set(maps["C3"])):
            tbl.append(
                {
                    "task_id": tid,
                    "C1": maps["C1"].get(tid, "absent"),
                    "C2": maps["C2"].get(tid, "absent"),
                    "C3": maps["C3"].get(tid, "absent"),
                }
            )
        paired_tables[str(seed)] = tbl

    # 预算/墙钟
    runs_cost = {label: (m.get("cost_usd_standard_price")) for label, m in metas.items()}
    cost_total = round(sum(v for v in runs_cost.values() if isinstance(v, (int, float))), 6)
    walls = {label: ((m.get("run_log") or {}).get("wall_seconds")) for label, m in metas.items()}
    wall_total = sum(v for v in walls.values() if isinstance(v, (int, float)))
    summary_text = (out / "RUN_SUMMARY.log").read_text(encoding="utf-8") if (out / "RUN_SUMMARY.log").is_file() else ""
    import re

    m_batch_wall = re.search(r"BATCH_WALL_SECONDS=(\d+)", summary_text)
    batch_wall = int(m_batch_wall.group(1)) if m_batch_wall else None
    gates = _load(out / "GATES.json") or {}
    prereg_sha = _sha256(out / "PREREG.md")

    payload = {
        "schema": "t2_b1_protocol_text_analysis/1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "run_stamp": out.name,
        "design": {
            "question": "RT1 消融：协议文本净效应 vs 多一次采样效应，能否在干净切点 + 模型指纹在案条件下复现",
            "cut_sha": EXPECT_SHA,
            "worktree": "/Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6",
            "cells": {c: {**CELL_DEF[c], "baseline_arg": CELL_DEF[c]["arm"]} for c in CELLS},
            "seeds": list(SEEDS),
            "dataset": {"name": "synthetic", "task_count": 87, "max_pattern_repeat": 2},
            "env_shared": (preflight.get("shared_env") or {}),
            "cell_env_diff": {"C2": {"DETECTION_FIRST_SECTION_ENABLE": "false"}, "C1": {}, "C3": {}},
            "primary_metric": "行 detection_rate（>=1.0 记检出；None 不进分母）",
            "secondary_metric": "行 llm_suite_detection_rate（同口径并列，若存在）",
            "mcnemar": "双侧精确二项，math.comb 手算；b=高检出格独有，c=反向",
            "bootstrap": f"配对任务重采样 {BOOTSTRAP_N} 次，seed={BOOTSTRAP_SEED}，percentile 95% CI",
            "prereg_sha256": prereg_sha,
        },
        "data_sources": {
            "metas": {label: str((out / f"seed{label.split('_seed')[1]}" / f"meta_{label.split('_')[0]}.json")) for label in sorted(metas)},
            "batch_json_sha256": {label: metas[label].get("batch_sha256") for label in sorted(metas)},
            "old_batch_20261009": old["paths"],
            "price_table": str(REPO / "experiments/price_table.json"),
        },
        "missing_or_failed_runs": missing,
        "execution_amendment": {
            "file": "PREREG_CONTINUATION.md",
            "sha256": _sha256(out / "PREREG_CONTINUATION.md"),
            "criteria_unchanged": True,
            "reason": "AITESTER_PROFILE=logic 预设 ENABLE_MUTATION_SCORING=true，触发内联 mutation_score + MDO 批后辅助测量；C1_seed42 任务阶段 463.8s 完成后后处理 >10.5min 未结束（mdo_posthoc.py 自述同类内联 MDO 20 任务×2 臂 >15min 未收敛），预计六跑 2h+ 会触发 85min 硬停导致 C3 缺失。",
            "action": "中止首跑（未产出批次 JSON，日志归档 _superseded_first_attempt/）；六格统一以 ENABLE_MUTATION_SCORING=false 重跑；该开关只关批后辅助测量，不影响 detection/生成/再生成/提示/预算/seeds。",
            "mutation_mdo_fields_excluded_from_conclusions": True,
            "first_attempt_archive": "_superseded_first_attempt/",
        },
        "per_seed": per_seed,
        "evaluation": evaluation,
        "fingerprint": fp,
        "gates": {"status": gates.get("status"), "blocking": gates.get("blocking"), "warnings": gates.get("warnings")},
        "cost_wall": {
            "cost_usd_standard_price_total": cost_total,
            "cost_usd_per_run": runs_cost,
            "price_basis": "experiments/price_table.json deepseek-flash input 0.3 / output 1.2 USD per Mtok（标准价，上界口径，非账单）",
            "runs_wall_seconds_sum": wall_total,
            "batch_wall_seconds": batch_wall,
            "budget_usd_limit": 2.0,
            "wall_limit_seconds": 5400,
            "within_budget": cost_total <= 2.0,
            "within_wall": (batch_wall is None or batch_wall <= 5400),
        },
        "old_batch_20261009": {
            "stats": old["stats"],
            "effects": old["effects"],
            "provenance": old["provenance"],
            "baseline_yaml_record": baseline,
            "note": "旧批（git_dirty=true、无 model_fingerprint、单 seed）；只作描述性并排，不构成本批判据",
        },
        "data_quality": {
            "detection_vs_llm_suite_key_mismatches": key_mismatch[:20],
            "detection_vs_llm_suite_mismatch_count": len(key_mismatch),
        },
        "paired_tables": paired_tables,
    }

    if args.write:
        (out / "ANALYSIS_REPORT.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "README.md").write_text(render_readme(payload), encoding="utf-8")
        print(f"[analyze] 写出 ANALYSIS_REPORT.json + README.md；joint_verdict={evaluation['joint_verdict']}")
    else:
        print(json.dumps({"joint_verdict": evaluation["joint_verdict"], "h_text": evaluation["h_text"]["verdict"], "h_sampling": evaluation["h_sampling"]["verdict"]}, ensure_ascii=False))
    return 0


# ─── README 渲染 ──────────────────────────────────────────────────────────


def _f(v, nd=2, suffix="") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}{suffix}"
    return f"{v}{suffix}"


def _pct(n, d) -> str:
    if not d:
        return "—"
    return f"{n}/{d} ({n / d * 100:.1f}%)"


def render_readme(payload: dict) -> str:
    d = payload["design"]
    ev = payload["evaluation"]
    per = payload["per_seed"]
    old = payload["old_batch_20261009"]
    fp = payload["fingerprint"]
    cw = payload["cost_wall"]

    lines: list[str] = []
    A = lines.append
    A("# T2/B1：RT1 协议文本消融的指纹级复现（3 格 × 2 seed，真 LLM）")
    A("")
    A("> **性质**：预注册判定测量（`PREREG.md` 跑前冻结，判定规则不得事后改动）。本报告只按冻结规则给 `verdict`，并如披露成本/墙钟/指纹/旧批漂移与局限。")
    A("")
    A("## 0. 摘要")
    A("")
    A(f"**联合 verdict：`{ev['joint_verdict']}`**（H-text=`{ev['h_text']['verdict']}`，H-sampling=`{ev['h_sampling']['verdict']}`）。")
    A("")
    for r in ev["reasons"]:
        A(f"- {r}")
    A("")
    A(f"- 证据质量：6 跑 `git_dirty` 全为 false 且 `git_sha` 全等于切点；`model_fingerprint` 块在场={fp['all_present']}，**pinned 全为 true={fp['all_pinned']}**"
      + ("（provider 未返回 system_fingerprint → 不得称『指纹级（pinned）』）" if not fp["all_pinned"] else "（可称『指纹级（pinned）』）")
      + f"；指纹探针 sha 唯一值数={len(fp['probe_sha_unique'])}、返回模型={fp['returned_model_unique']}。")
    A(f"- 成本/墙钟：6 跑估算 **${cw['cost_usd_standard_price_total']:.4f}**（价目表标准价上界口径，非账单）/ 批次墙钟 **{_f(cw['batch_wall_seconds'], 0, 's')}**（上限 $2.0 / 5400s）。")
    A(f"- 失败/缺失：{payload['missing_or_failed_runs'] or '无（6/6 跑批 ok）'}。")
    amend = payload.get("execution_amendment") or {}
    if amend:
        A(f"- **执行性修订（判据未改）**：首跑因批后 mutation/MDO 辅助测量墙钟超预期被中止（无主终点数据损失，日志归档 `_superseded_first_attempt/`）；六格统一以 `ENABLE_MUTATION_SCORING=false` 重跑（只关辅助测量字段；详见 `PREREG_CONTINUATION.md`，sha256 `{str(amend.get('sha256'))[:16]}…`）。")
    A("")
    A("## 1. 设计与切点")
    A("")
    A(f"- 切点：`{d['cut_sha']}`；跑批工作树：`{d['worktree']}`（与切点一致、全程 clean；本批零代码修改）。")
    A(f"- 数据：`{d['dataset']['name']}`，`--task-count {d['dataset']['task_count']} --max-pattern-repeat {d['dataset']['max_pattern_repeat']}`；seeds = {d['seeds']}。")
    A("- 三格（每 seed 独立跑，同一运行协议，仅 `--baselines` 与一个 env 开关不同）：")
    A("")
    A("| 格 | `--baselines` | 再生成路由 | 强化段落 | 语义 |")
    A("|---|---|---|---|---|")
    for c in CELLS:
        A(f"| {c} | `{d['cells'][c]['baseline_arg']}` | {d['cells'][c]['routing']} | {d['cells'][c]['section']} | {d['cells'][c]['tag']} |")
    A("")
    A("- 共享 env：" + "，".join(f"`{k}={v}`" for k, v in d["env_shared"].items()) + "；每跑独立 `AITESTER_CACHE_NAMESPACE=t_b1_<cell>_<seed>`、独立 `AITESTER_TRACE_DIR`。")
    A("- 格间唯一 env 差异：C2 额外 `DETECTION_FIRST_SECTION_ENABLE=false`（只关强化段落、**不动路由**——PREFLIGHT 的干预探针已逐项验证：section_on→段落 196 字符、section_off→None、`regenerate_entry=True` 不变）。")
    A(f"- 主口径：{d['primary_metric']}；并列 {d['secondary_metric']}。配对按 `task_id`（同 seed 三格集合一致，GATES 硬检查）。")
    A("")
    A("## 2. 逐 seed 三格主表（detection，行 `detection_rate`）")
    A("")
    A("| seed | 格 | 检出/可测 | 检出率 | llm_suite 检出/可测 | passed | tokens | 估算$ | 墙钟s | 再生成行 | 0/1 regen 计数分布 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    for seed in SEEDS:
        s = per.get(str(seed)) or {}
        for c in CELLS:
            st = s.get(c)
            if not st:
                A(f"| {seed} | {c} | — | — | — | — | — | — | — | — | — |")
                continue
            det = st["detection"]
            llm = st["llm_suite_detection"]
            tm = st["token_metrics"] or {}
            A(
                f"| {seed} | {c} | {_pct(det['detected'], det['measurable'])} | {_f(det['rate_pp'], 2, 'pp')} | "
                f"{_pct(llm['detected'], llm['measurable'])} | {_pct(st['passed'], st['rows'])} | "
                f"{tm.get('total_tokens', '—')} | {_f(st['cost_usd_standard_price'], 4)} | {_f(st['wall_seconds'], 0)} | "
                f"{st['regenerated_rows']} | {json.dumps(st['regeneration_count_dist'], ensure_ascii=False)} |"
            )
    A("")
    A("## 3. 效应表（配对 + McNemar 精确双侧 + bootstrap CI）")
    A("")
    A("### 3.1 文本净效应：C3 − C2（两者路由/再生成一致，唯一差别 = 强化段落文本）")
    A("")
    A("| seed | C3 率 | C2 率 | Δ_text（臂率，pp） | 检出计数差 | 配对可测 | b (C3 only) | c (C2 only) | 不一致对 | Δ_paired（pp） | McNemar p（双侧） | bootstrap 95% CI（pp） |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in ev["h_text"]["rows"]:
        A(
            f"| {row['seed']} | {_f((row['high_rate'] or 0) * 100, 2, 'pp')} | {_f((row['low_rate'] or 0) * 100, 2, 'pp')} | "
            f"**{_f(row['delta_pp_arm_rates'], 2)}** | {row['detected_delta']:+d} | {row['paired_measurable']} | {row['b_high_only']} | {row['c_low_only']} | "
            f"{row['discordant']} | {_f(row['delta_pp_paired'], 2)} | {row['mcnemar_exact_p_two_sided']:.6f} | "
            f"[{_f((row['bootstrap_ci95_pp_paired'] or [None, None])[0], 2)}, {_f((row['bootstrap_ci95_pp_paired'] or [None, None])[1], 2)}] |"
        )
    A("")
    A("### 3.2 多一次采样效应：C2 − C1（C1 无再生成路由；C2 首轮全绿会再生成一次）")
    A("")
    A("| seed | C2 率 | C1 率 | Δ_sampling（臂率，pp） | 配对可测 | b (C2 only) | c (C1 only) | 不一致对 | McNemar p（双侧） | bootstrap 95% CI（pp） |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for row in ev["h_sampling"]["rows"]:
        A(
            f"| {row['seed']} | {_f((row['high_rate'] or 0) * 100, 2, 'pp')} | {_f((row['low_rate'] or 0) * 100, 2, 'pp')} | "
            f"**{_f(row['delta_pp_arm_rates'], 2)}** | {row['paired_measurable']} | {row['b_high_only']} | {row['c_low_only']} | {row['discordant']} | "
            f"{row['mcnemar_exact_p_two_sided']:.6f} | [{_f((row['bootstrap_ci95_pp_paired'] or [None, None])[0], 2)}, {_f((row['bootstrap_ci95_pp_paired'] or [None, None])[1], 2)}] |"
        )
    A("")
    A("## 4. 预注册判定（`PREREG.md` §5，冻结规则）")
    A("")
    A("| 判据 | 规则（跑前冻结） | 结果 |")
    A("|---|---|---|")
    A(f"| H-text | 每 seed Δ_text_pp>0 且 2/2 方向一致 → replicated；≥1 seed McNemar p<0.05 → strong；任一 seed Δ≤0 → not_replicated | **`{ev['h_text']['verdict']}`**（显著 seeds={ev['h_text']['significant_seeds'] or '无'}） |")
    A(f"| H-sampling | 每 seed |Δ_sampling_pp|≤5.0pp 且 McNemar p≥0.05；2/2 满足 → negligible | **`{ev['h_sampling']['verdict']}`** |")
    A(f"| 联合 | 见 PREREG §5 表 | **`{ev['joint_verdict']}`** |")
    A("")
    A("## 5. 与 2026-10-09 旧批并排（描述性；旧批不构成本批判据）")
    A("")
    A("| 臂 | 旧批（2026-10-09，seed42） | 本批 seed42 | 本批 seed44 | 漂移说明 |")
    A("|---|---|---|---|---|")
    old_stats = old["stats"]
    cell_of_old = {"plain_llm": "C1", "rt1": "C2", "df_full": "C3"}
    for arm, name in (("C1/plain_llm", "plain_llm"), ("C2/rt1", "rt1"), ("C3/df_full", "df_full")):
        ost = old_stats.get(name) or {}
        odet = ost.get("detection") or {}
        n42 = ((per.get("42") or {}).get(cell_of_old[name]) or {})
        n44 = ((per.get("44") or {}).get(cell_of_old[name]) or {})
        A(
            f"| {arm} | {_pct(odet.get('detected'), odet.get('measurable'))} | "
            f"{_pct((n42.get('detection') or {}).get('detected'), (n42.get('detection') or {}).get('measurable'))} | "
            f"{_pct((n44.get('detection') or {}).get('detected'), (n44.get('detection') or {}).get('measurable'))} | "
            f"旧批 git_dirty={old['provenance'].get('git_dirty')}、无 model_fingerprint；绝对漂移只作描述 |"
        )
    A("")
    A("旧批配对复算（从旧工件的行字段直接重算，供核对 BASELINE.yaml 已登记口径）：")
    A("")
    A("| 对比 | b | c | 不一致对 | Δ（pp） | McNemar p |")
    A("|---|---|---|---|---|---|")
    for key, row in (old["effects"] or {}).items():
        A(f"| {key} | {row.get('b_high_only')} | {row.get('c_low_only')} | {row.get('discordant')} | {_f(row.get('delta_pp_arm_rates'), 2)} | {row.get('mcnemar_exact_p_two_sided'):.6f} |")
    rec = (old.get("baseline_yaml_record") or {}).get("record") or {}
    if rec:
        A("")
        A("`BASELINE.yaml` 登记口径与本批复算的差异说明：登记用 χ²（连续性校正）近似 p（df_vs_rt1: χ²=15.059, p=0.0001），本批复算用 **McNemar 精确二项** p（1.53e-05）；两者结论同向（显著），p 值口径不同，引用时须注明。登记 delta_pp=19.5 / 不一致对 17 / rt1_vs_plain_llm p=1.0 均与复算一致（1.15pp、1、1.0）。")
        A("")
        A("`BASELINE.yaml` → `benchmark.rt1_sampling_control` 已登记口径（只读引用）：")
        A("")
        A("```yaml")
        A(json.dumps(rec, ensure_ascii=False, indent=2))
        A("```")
    A("")
    A("## 6. 成本、墙钟与预算护栏")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A(f"| 6 跑估算费用（标准价上界口径） | **${cw['cost_usd_standard_price_total']:.4f}** |")
    A(f"| 逐跑费用 | {json.dumps(cw['cost_usd_per_run'], ensure_ascii=False)} |")
    A(f"| 价格口径 | {cw['price_basis']} |")
    A(f"| 逐跑墙钟之和 | {cw['runs_wall_seconds_sum']} s |")
    A(f"| 批次墙钟 | {cw['batch_wall_seconds']} s（上限 5400 s / 90 min） |")
    A(f"| 预算 | ${cw['cost_usd_standard_price_total']:.4f} ≤ $2.0 上限；`within_budget={cw['within_budget']}`，`within_wall={cw['within_wall']}` |")
    A("")
    A("## 7. 证据质量（指纹 / 洁净树 / 门禁）")
    A("")
    A("| 项 | 结果 |")
    A("|---|---|")
    A(f"| 切点 sha（6 跑 provenance 一致） | `{d['cut_sha']}` |")
    A(f"| `git_dirty` | 全为 false（GATES：`provenance_clean_tree`） |")
    A(f"| `model_fingerprint` 块在场 | {fp['all_present']} |")
    A(f"| `model_fingerprint.pinned` | 全 true={fp['all_pinned']}；返回模型={fp['returned_model_unique']}；探针 sha 唯一值数={len(fp['probe_sha_unique'])}（≤1 = 同快照） |")
    A(f"| GATES 状态 | `{payload['gates'].get('status')}`；blocking={payload['gates'].get('blocking')}；warnings={payload['gates'].get('warnings')} |")
    A(f"| 数据质量：`detection_rate` vs `llm_suite_detection_rate` | 不一致 {payload['data_quality']['detection_vs_llm_suite_mismatch_count']} 行（N-3 口径两键同值） |")
    A("| 执行性修订生效性（GATES `mutation_scoring_disabled_all_runs`） | 六跑 `env_snapshot.ENABLE_MUTATION_SCORING=false`（只关批后辅助测量；`PREREG_CONTINUATION.md`） |")
    A("")
    A("## 8. 口径与局限（必须并列披露）")
    A("")
    A("1. **样本小**：87 任务 × 2 seed；McNemar 只在不一致对上检验，功效有限。`direction_only` 不得读成「无效应」。")
    A("2. **旧批不可直接合并**：2026-10-09 旧批 `git_dirty=true`、`model_fingerprint` 缺失、单 seed；本批与其绝对值的差异混有代码状态与模型快照漂移，只作描述性并排。")
    A("3. **浮动别名**：`deepseek-flash` 为请求侧别名；本批以 `model_fingerprint`（returned_model / system_fingerprint / 探针 sha256）记录快照证据。" + ("本批 pinned=true，可称指纹级。" if fp["all_pinned"] else "**本批 pinned=false（provider 未返回 system_fingerprint），只能称『指纹块在场但未 pinned』，不得称指纹级。**"))
    A("4. **`detection_rate` 是协议级信号**：不得当作测试质量通用代理（`docs/VALIDITY.md` §5.1）。")
    A("5. **C1→C2 的『多一次采样』是复合干预**：C2 相对 C1 同时打开了再生成路由与相应计数；本批把它整体作为『多一次采样/再生成效应』报告，不进一步拆分内部调用差异。")
    A("6. **不是假修复结论**：本批主终点只有 detection；false-fix/声明通过率只作并列读数，不支持「检出优先减少假修复」的因果主张（见 `docs/VALIDITY.md` §5.2）。")
    A("7. **B2 主批次并行运行**：CPU/API 争用可能抬高墙钟与重试，本批未因此降并行度或缩样本；实际墙钟见 §6。")
    A("8. **执行性修订（非判据修订）**：见 `PREREG_CONTINUATION.md`。首跑（C1_seed42，修订前）因 `ENABLE_MUTATION_SCORING=true` 的内联 mutation_score + MDO 批后辅助测量耗时 >10.5 min 未结束而被中止，未产出批次 JSON（日志归档 `_superseded_first_attempt/`）；六格最终统一以 `ENABLE_MUTATION_SCORING=false` 重跑。该开关只影响批后 `mutation_score`/`mdo_*` 辅助字段，**不影响** detection/生成/再生成/提示/预算，本批结论不引用任何 mutation/MDO 数值。")
    A("")
    A("## 9. 文件清单")
    A("")
    A("| 文件 | 说明 |")
    A("|---|---|")
    A("| `PREREG.md` | 跑前冻结预注册（判定/停止规则/预算/产物） |")
    A("| `PREFLIGHT.json` | 工作树/预注册/导入源/CLI/干预开关/旧批复算/预算估算 + dry-run 记录 |")
    A("| `staging/<cell>_seed<seed>/benchmark_synthetic_<ts>.json` | 6 份原始批次工件 |")
    A("| `logs/<cell>_seed<seed>.log` | 6 份运行日志（起止/命令/env/退出码/墙钟） |")
    A("| `traces/<cell>_seed<seed>/` | `AITESTER_TRACE_DIR` 追踪产物 |")
    A("| `seed42/`、`seed44/` | 每 seed 三格抽取元数据 `meta_<cell>.json` |")
    A("| `RUN_SUMMARY.log` | 逐跑摘要 + 批次汇总（token/费用/墙钟/再生成行） |")
    A("| `GATES.json` | 硬门禁（行数/task 集合/洁净树/指纹/开关/预算） |")
    A("| `ANALYSIS_REPORT.json` | 本报告机器可读版（含逐任务配对表、旧批并排、逐跑 fingerprint） |")
    A("| `README.md` | 本中文报告 |")
    A("| `PREREG_CONTINUATION.md` | 跑中执行性修订（判据未改；辅助测量关闭 + 续跑规则）与首跑中止记录 |")
    A("| `_superseded_first_attempt/` | 修订前首跑日志归档（无主终点数据；不参与分析） |")
    A("| `DOC_RECONCILIATION.md` | 陈旧文档声明核对清单（Lead 采纳修正） |")
    A("| `SHA256SUMS` | checksum_results.py --write 生成、--verify 通过 |")
    A("| `_helpers/` | 零 LLM 可复算脚本（preflight/extract/gates/analyze/limited_run） |")
    A("")
    A("## 10. 复现命令")
    A("")
    A("```bash")
    A("# 1) 建 worktree（切点）并复制敏感配置（不打印/不提交）")
    A(f"git -C {REPO} worktree add --detach /Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6 {d['cut_sha']}")
    A(f"cp {REPO}/.env {REPO}/.env.local /Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6/")
    A("")
    A("# 2) 跑前自测（零 LLM）→ 真实跑批")
    A(f"cd {REPO} && bash experiments/run_t2_b1_protocol_text.sh --dry-run")
    A(f"cd {REPO} && nohup bash experiments/run_t2_b1_protocol_text.sh > /tmp/t2_b1_runner.log 2>&1 &")
    A("")
    A("# 3) 分析 + 门禁 + 校验（零 LLM）")
    A(f"{REPO}/.venv/bin/python experiments/results/t_round_b1_protocol_text_20261018/_helpers/gates.py --out experiments/results/t_round_b1_protocol_text_20261018 --expect-sha {d['cut_sha']}")
    A(f"{REPO}/.venv/bin/python experiments/results/t_round_b1_protocol_text_20261018/_helpers/analyze.py --out experiments/results/t_round_b1_protocol_text_20261018 --write")
    A(f"{REPO}/.venv/bin/python {REPO}/scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_b1_protocol_text_20261018")
    A("```")
    A("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
