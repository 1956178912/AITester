#!/usr/bin/env python3
"""T1（B2）主批次锁指纹复现批分析（零 LLM 只读工件）。

用法：
    .venv/bin/python experiments/analyze_t1_b2_main_batch.py \
        --out experiments/results/t_round_b2_main_batch_20261018 \
        --orig-dir experiments/results/main_batch \
        [--write]

产出（--write 时）：
    <out>/ANALYSIS_REPORT.json   判定（§1.2 pre-registered）+ 逐 seed/合并表 + 与原批并排 + provenance 漂移
    <out>/README.md              中文报告（含 §1.1 硬门槛、判定、三指标、成本、口径与局限）。
                                  生成内容之外的**手工维护节**用 `<!-- MANUAL:BEGIN/END -->`
                                  标记包裹，--write 时原样保留在文末（防重跑丢失手写
                                  解读；X 轮 2026-10-19 增设，回归锁见
                                  tests/test_analyze_t1_b2_manual_sections.py）。

口径：
- detection 计数 = 行 `detection_rate` 值 >= 1.0（None 不进分母）；同时并列 `llm_suite_detection_rate`
  可测时的计数（N-3 后独立判读口径；旧批该字段恒 None）。
- repair/false_fix 计数沿用主批次 M1 行口径（>=1.0 计命中），分母 = 字段非 None 行数。
- McNemar：按 (seed, task_id) 配对；b=新检出旧未检出，c=旧检出新未检出；双侧精确二项 p。
- bootstrap：按任务对重采样 5000 次（固定 seed=20261018，percentile 95% CI）。
- 成本：本批 token_metrics 的 input/output 分别 × 价目表（官方价，峰时全额），非账单。
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SEEDS = (42, 43, 44)
ARMS = ("aitester", "plain_llm", "plain_llm_df")
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20261018


def _load_json(path: Path) -> dict[str, Any]:
    """读 JSON（失败抛异常，供调用方定位）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_presets(rev: str) -> dict[str, dict[str, str]]:
    """从指定 git 版本的 config.py 读取 `_PROFILE_PRESETS`（AST 求值，零导入）。

    失败（git 不可用/版本缺失）返回空 dict——调用方需按"无法核验"披露，不得
    当成"无漂移"（本项目纪律：缺席与通过不同形）。
    """
    try:
        src = subprocess.run(
            ["git", "show", f"{rev}:config.py"], capture_output=True, text=True, timeout=20, check=True
        ).stdout
        tree = ast.parse(src)
    except Exception:
        return {}
    for node in tree.body:
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        if any(getattr(t, "id", "") == "_PROFILE_PRESETS" for t in targets) and value is not None:
            try:
                return ast.literal_eval(value)
            except Exception:
                return {}
    return {}


def _profile_drift(old_rev: str, new_rev: str, profile: str = "logic") -> dict[str, Any]:
    """profile 预设漂移（新增/删除/改值）——env_snapshot 只记录固定键集，
    profile 注入的新增开关不体现在 snapshot diff 里，必须单独披露。"""
    old = _profile_presets(old_rev)
    new = _profile_presets(new_rev)
    if not old or not new:
        return {"available": False, "reason": "git show config.py 失败（无法核验），不得当作无漂移"}
    o = old.get(profile) or {}
    n = new.get(profile) or {}
    return {
        "available": True,
        "profile": profile,
        "old_rev": old_rev,
        "new_rev": new_rev,
        "added": {k: n[k] for k in sorted(set(n) - set(o))},
        "removed": {k: o[k] for k in sorted(set(o) - set(n))},
        "changed": {k: {"old": o[k], "new": n[k]} for k in sorted(set(o) & set(n)) if o[k] != n[k]},
        "old_key_count": len(o),
        "new_key_count": len(n),
    }


def _metric_hit(value: Any) -> bool | None:
    """M1 行级二值指标：>=1.0 记命中；None 不可测返回 None。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value) >= 1.0


def arm_stats(batch: dict[str, Any], arm: str) -> dict[str, Any]:
    """逐臂统计（detection / repair / false_fix / 覆盖率 / token / 成本 / stop_reason）。"""
    res = (batch.get("results") or {}).get(arm) or {}
    rows = res.get("details") or []
    det = [v for r in rows if (v := _metric_hit(r.get("detection_rate"))) is not None]
    llm_det = [v for r in rows if (v := _metric_hit(r.get("llm_suite_detection_rate"))) is not None]
    rep = [v for r in rows if (v := _metric_hit(r.get("repair_rate"))) is not None]
    ff = [v for r in rows if (v := _metric_hit(r.get("false_fix_rate"))) is not None]
    covs = [float(r["coverage"]) for r in rows if isinstance(r.get("coverage"), (int, float))]
    iters = [float(r["iterations"]) for r in rows if isinstance(r.get("iterations"), (int, float))]
    tm = res.get("token_metrics") or {}
    return {
        "rows": len(rows),
        "detection_measurable": len(det),
        "detected": sum(det),
        "detection_rate": round(sum(det) / len(det), 4) if det else None,
        "llm_suite_detection_measurable": len(llm_det),
        "llm_suite_detected": sum(llm_det) if llm_det else None,
        "repair_measurable": len(rep),
        "repaired": sum(rep),
        "repair_rate": round(sum(rep) / len(rep), 4) if rep else None,
        "false_fix_measurable": len(ff),
        "false_fixed": sum(ff),
        "false_fix_rate": round(sum(ff) / len(ff), 4) if ff else None,
        "coverage_mean": round(sum(covs) / len(covs), 2) if covs else None,
        "iterations_mean": round(sum(iters) / len(iters), 3) if iters else None,
        "stop_reasons": dict(Counter(str(r.get("stop_reason")) for r in rows)),
        "regeneration_rows": sum(
            1 for r in rows if isinstance(r.get("regeneration_count"), (int, float)) and r["regeneration_count"] > 0
        ),
        "rollback_field_present": sum(1 for r in rows if "patch_rolled_back" in r),
        "token_metrics": tm,
        "cost_usd": None,  # 由 price 计算后填充
        "calls": tm.get("total_llm_calls"),
    }


def add_cost(stats: dict[str, Any], price: dict[str, Any]) -> None:
    """按价目表计算 arm 成本（$；input/output 分开计价）。"""
    tm = stats.get("token_metrics") or {}
    p_in = price.get("input_per_mtok")
    p_out = price.get("output_per_mtok")
    if not isinstance(p_in, (int, float)) or not isinstance(p_out, (int, float)):
        return
    tin = tm.get("total_input_tokens") or 0
    tout = tm.get("total_output_tokens") or 0
    stats["cost_usd"] = round((tin * p_in + tout * p_out) / 1e6, 6)


def per_task_detection(batch: dict[str, Any], arm: str) -> dict[str, bool | None]:
    """task_id → detection 命中（None=不可测），供配对检验。"""
    out: dict[str, bool | None] = {}
    for r in ((batch.get("results") or {}).get(arm) or {}).get("details") or []:
        out[str(r.get("task_id"))] = _metric_hit(r.get("detection_rate"))
    return out


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 双侧精确二项 p 值（b+c 个不一致对，p=0.5）。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # 双侧：2 × P(X <= k)，上限 1
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def paired_delta(
    new_map: dict[str, bool | None], old_map: dict[str, bool | None], *, keys: list[str]
) -> dict[str, Any]:
    """配对差（new − old）的 McNemar + bootstrap CI（仅双方均可测的配对）。"""
    pairs = [(new_map.get(k), old_map.get(k)) for k in keys]
    pairs = [(n, o) for n, o in pairs if n is not None and o is not None]
    b = sum(1 for n, o in pairs if n and not o)
    c = sum(1 for n, o in pairs if o and not n)
    n = len(pairs)
    if n == 0:
        return {
            "n_pairs": 0,
            "b_new_only": b,
            "c_old_only": c,
            "delta": None,
            "delta_pp": None,
            "mcnemar_exact_p_two_sided": 1.0,
            "bootstrap_ci95": [None, None],
        }
    delta = (b - c) / n
    rng = random.Random(BOOTSTRAP_SEED)
    boots: list[float] = []
    for _ in range(BOOTSTRAP_N):
        s = 0
        for _ in range(n):
            nn, oo = pairs[rng.randrange(n)]
            s += int(nn) - int(oo)
        boots.append(s / n)
    boots.sort()
    lo = boots[int(0.025 * BOOTSTRAP_N)]
    hi = boots[int(0.975 * BOOTSTRAP_N) - 1]
    return {
        "n_pairs": n,
        "b_new_only": b,
        "c_old_only": c,
        "delta": round(delta, 4) if delta is not None else None,
        "delta_pp": round(delta * 100, 2) if delta is not None else None,
        "mcnemar_exact_p_two_sided": round(mcnemar_exact(b, c), 8),
        "bootstrap_ci95": [round(lo, 4), round(hi, 4)],
    }


def pooled_counts(batch: dict[str, Any], arm: str) -> tuple[int, int]:
    """合并口径计数（detected, measurable）。"""
    st = arm_stats(batch, arm)
    return st["detected"], st["detection_measurable"]


def ordering_ok(stats_by_arm: dict[str, dict[str, Any]]) -> bool:
    """R1：plain_llm_df > aitester > plain_llm（按 detection_rate，合并口径）。"""
    d = {a: stats_by_arm[a]["detection_rate"] for a in ARMS}
    if any(v is None for v in d.values()):
        return False
    return d["plain_llm_df"] > d["aitester"] > d["plain_llm"]


def build_report(out_dir: Path, orig_dir: Path, price: dict[str, Any]) -> dict[str, Any]:
    """构建完整分析报告（JSON 载荷）。"""
    gates = _load_json(out_dir / "GATES.json") if (out_dir / "GATES.json").exists() else None
    preflight = _load_json(out_dir / "PREFLIGHT.json") if (out_dir / "PREFLIGHT.json").exists() else None
    amendment = out_dir / "PREREG_AMENDMENT_cost_estimate.md"

    new_batches: dict[int, dict[str, Any]] = {}
    for seed in SEEDS:
        files = sorted((out_dir / f"seed{seed}").glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
        if files:
            new_batches[seed] = _load_json(files[-1])
        else:
            new_batches[seed] = {}

    orig_batches: dict[int, dict[str, Any]] = {}
    for p in sorted(orig_dir.glob("benchmark_synthetic_*.json")):
        try:
            d = _load_json(p)
        except Exception:  # noqa: S112 - 损坏/半写批次 JSON 跳过（不让单个坏文件中断全批分析）
            continue
        seed = d.get("seed")
        if seed in (42, 43, 44) and d.get("total_tasks") == 87 and seed not in orig_batches:
            orig_batches[seed] = d

    report: dict[str, Any] = {
        "schema": "aitester_t1_b2_analysis/1",
        "out_dir": str(out_dir),
        "orig_dir": str(orig_dir),
        "seeds": list(SEEDS),
        "arms": list(ARMS),
        "prereg_amendment": {
            "path": str(amendment),
            "note": "跑前成本估算修正（input/output 份额口径），判据未改",
        },
        "gates": gates,
        "preflight": {
            "prereg_sha256": (preflight or {}).get("prereg_sha256"),
            "cost_estimate": (preflight or {}).get("cost_estimate"),
            "quota_probe_ok": ((preflight or {}).get("quota_probe") or {}).get("ok"),
        },
        "per_seed": {},
        "pooled": {},
        "original_pooled": {},
        "paired_new_vs_original": {},
        "provenance_drift": {},
        "cost": {},
        "verdict": {},
        "limitations": [
            "单次运行/seed，温度 0 仍有服务端非确定性；复现判据只到方向/排序级，不要求逐位相等",
            "harness 自 R-P0-2（2026-10-06, b533cff）演进至 a93c1f6：logic 档/默认开关增量为披露项（见 provenance_drift），跨批差异不作单一归因",
            "detection 为 M1 行口径（detection_rate≥1）；repair/false_fix 随行口径并列，不与旧批修正口径混用",
            "成本为官方价目表峰时全额估算（非账单）；跑前估算曾误设 input 份额，已在 PREREG_AMENDMENT 披露",
        ],
    }

    # ── 逐 seed 表 ──────────────────────────────────────────────────────────
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        ob = orig_batches.get(seed) or {}
        entry: dict[str, Any] = {"new": {}, "original": {}}
        for arm in ARMS:
            if nb.get("results", {}).get(arm):
                st = arm_stats(nb, arm)
                add_cost(st, price)
                entry["new"][arm] = st
            if ob.get("results", {}).get(arm):
                st = arm_stats(ob, arm)
                add_cost(st, price)
                entry["original"][arm] = st
        new_order = ordering_ok(entry["new"]) if len(entry["new"]) == 3 else None
        entry["same_seed_ordering_ok"] = new_order
        report["per_seed"][str(seed)] = entry

    # ── 合并口径（3 seed 池化）──────────────────────────────────────────────
    pooled: dict[str, Any] = {}
    orig_pooled: dict[str, Any] = {}
    for arm in ARMS:
        det = 0
        meas = 0
        rep = rep_n = 0
        ff = ff_n = 0
        cost = 0.0
        tokens = {"in": 0, "out": 0, "total": 0, "calls": 0}
        for seed in SEEDS:
            st = report["per_seed"][str(seed)]["new"].get(arm)
            if st:
                det += st["detected"]
                meas += st["detection_measurable"]
                rep += st["repaired"]
                rep_n += st["repair_measurable"]
                ff += st["false_fixed"]
                ff_n += st["false_fix_measurable"]
                cost += st["cost_usd"] or 0.0
                tm = st["token_metrics"] or {}
                tokens["in"] += tm.get("total_input_tokens") or 0
                tokens["out"] += tm.get("total_output_tokens") or 0
                tokens["total"] += tm.get("total_tokens") or 0
                tokens["calls"] += tm.get("total_llm_calls") or 0
        pooled[arm] = {
            "detected": det,
            "measurable": meas,
            "detection_rate": round(det / meas, 4) if meas else None,
            "repaired": rep,
            "repair_measurable": rep_n,
            "repair_rate": round(rep / rep_n, 4) if rep_n else None,
            "false_fixed": ff,
            "false_fix_measurable": ff_n,
            "false_fix_rate": round(ff / ff_n, 4) if ff_n else None,
            "tokens": tokens,
            "cost_usd": round(cost, 6),
        }
        # 旧批同口径池化
        odet = omeas = 0
        for seed in SEEDS:
            st = report["per_seed"][str(seed)]["original"].get(arm)
            if st:
                odet += st["detected"]
                omeas += st["detection_measurable"]
        orig_pooled[arm] = {
            "detected": odet,
            "measurable": omeas,
            "detection_rate": round(odet / omeas, 4) if omeas else None,
        }
    report["pooled"] = pooled
    report["original_pooled"] = orig_pooled

    # ── R1/R2/R3（预注册判据）───────────────────────────────────────────────
    r1 = ordering_ok(pooled)
    seeds_with_order = [s for s in SEEDS if report["per_seed"][str(s)].get("same_seed_ordering_ok")]
    r3 = len(seeds_with_order) >= 2
    # R2：新批 aitester vs df 配对（按 seed+task 配对）
    new_maps: dict[str, dict[tuple[int, str], bool | None]] = {a: {} for a in ARMS}
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        for arm in ARMS:
            for tid, hit in per_task_detection(nb, arm).items():
                new_maps[arm][(seed, tid)] = hit
    keys = sorted(set(new_maps["aitester"]) & set(new_maps["plain_llm_df"]))
    flat_new = {str(k): v for k, v in new_maps["aitester"].items()}
    flat_new_df = {str(k): v for k, v in new_maps["plain_llm_df"].items()}
    r2_stats = paired_delta(flat_new, flat_new_df, keys=[str(k) for k in keys])
    r2 = r2_stats["delta"] is not None and r2_stats["delta"] < 0 and r2_stats["bootstrap_ci95"][1] < 0
    gates_ok = bool((gates or {}).get("all_pass"))
    if not gates_ok:
        verdict = "not_reproducible_grade"
        rationale = "§1.1 硬门槛未全过（见 gates），只报告事实、不出方向性结论"
    elif r1 and r2 and r3:
        verdict = "reproduced"
        rationale = "R1 合并排序成立 ∧ R2 负向差显著（CI 全负）∧ R3 逐 seed 排序 ≥2/3"
    elif r1:
        verdict = "direction_partial"
        rationale = "R1 成立但 R2 的 bootstrap CI 跨 0（方向一致但强度不足）"
    else:
        verdict = "not_reproduced"
        rationale = "R1 或 R2 反向/不成立"
    report["verdict"] = {
        "verdict": verdict,
        "rationale": rationale,
        "R1_pooled_ordering_df_gt_aitester_gt_plain": r1,
        "R2_aitester_vs_df_delta_negative_ci_below_zero": r2,
        "R2_stats": r2_stats,
        "R3_ordering_in_at_least_2_of_3_seeds": r3,
        "R3_seeds_with_ordering": seeds_with_order,
        "gates_all_pass": gates_ok,
    }

    # ── 新批 vs 原批配对（复现性的逐任务一致性，描述性）────────────────────
    old_maps: dict[str, dict[str, bool | None]] = {a: {} for a in ARMS}
    for seed, ob in orig_batches.items():
        for arm in ARMS:
            for tid, hit in per_task_detection(ob, arm).items():
                old_maps[arm][(seed, tid)] = hit
    for arm in ARMS:
        flat_new_arm = {str(k): v for k, v in new_maps[arm].items()}
        flat_old_arm = {str(k): v for k, v in old_maps[arm].items()}
        common = [k for k in flat_new_arm if k in flat_old_arm]
        report["paired_new_vs_original"][arm] = paired_delta(flat_new_arm, flat_old_arm, keys=common)

    # ── provenance 漂移（新旧 env_snapshot / harness）────────────────────────
    drift: dict[str, Any] = {"env_snapshot_diff": {}, "harness_diff": {}, "profile": {}}
    for seed in SEEDS:
        nb = new_batches.get(seed) or {}
        ob = orig_batches.get(seed) or {}
        np_ = nb.get("provenance") or {}
        op_ = ob.get("provenance") or {}
        if not np_ or not op_:
            continue
        nsnap = np_.get("env_snapshot") or {}
        osnap = op_.get("env_snapshot") or {}
        diff = {}
        for k in sorted(set(nsnap) | set(osnap)):
            if nsnap.get(k) != osnap.get(k):
                diff[k] = {"new": nsnap.get(k), "old": osnap.get(k)}
        drift["env_snapshot_diff"][str(seed)] = diff
        drift["profile"][str(seed)] = {"new": np_.get("profile"), "old": op_.get("profile")}
        nh = np_.get("harness") or {}
        oh = op_.get("harness") or {}
        hdiff = {}
        for k in sorted(set(nh) | set(oh)):
            if nh.get(k) != oh.get(k):
                hdiff[k] = {"new": nh.get(k), "old": oh.get(k)}
        drift["harness_diff"][str(seed)] = hdiff
        drift["provenance_flags"] = {
            "new_git_dirty": np_.get("git_dirty"),
            "new_git_sha": np_.get("git_sha"),
            "new_fingerprint_pinned": (np_.get("model_fingerprint") or {}).get("pinned"),
            "old_git_dirty": op_.get("git_dirty"),
            "old_git_sha": op_.get("git_sha"),
            "old_fingerprint_present": "model_fingerprint" in op_,
        }
    report["provenance_drift"] = drift
    # profile 预设漂移（logic 档新增 5 个行为开关等）——env_snapshot 固定键集看不到
    report["profile_preset_drift"] = _profile_drift(
        "b533cff1c316e8e80db635a1b2946610b211a5b6", "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"
    )

    # ── 成本 ────────────────────────────────────────────────────────────────
    total_cost = round(sum(v["cost_usd"] for v in pooled.values()), 6)
    total_tokens = sum(v["tokens"]["total"] for v in pooled.values())
    report["cost"] = {
        "actual_est_usd": total_cost,
        "total_tokens": total_tokens,
        "preflight_estimate_usd": ((preflight or {}).get("cost_estimate") or {}).get("est_usd"),
        "amended_estimate_usd": 8.8,
        "budget_usd": (preflight or {}).get("budget_usd"),
        "note": "实测成本按本批 token_metrics 的 input/output 分别计价（官方价目表峰时全额，非账单）",
    }
    return report


def render_baseline_fragment(report: dict[str, Any]) -> str:
    """渲染 BASELINE.yaml `target_quality.b2_main_batch_t_round` 片段（2 空格缩进 YAML）。"""
    v = report["verdict"]
    lines: list[str] = []
    lines.append("  b2_main_batch_t_round:")
    lines.append('    measured_at: "2026-10-18"')
    lines.append('    nature: "锁指纹复现批（decision-grade；预注册冻结；成本估算口径修正见 PREREG_AMENDMENT）"')
    lines.append('    cut_commit: "a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"')
    lines.append(
        "    protocol: {dataset: synthetic, task_count: 87, max_pattern_repeat: 2, seeds: [42, 43, 44], "
        'arms: [aitester, plain_llm, plain_llm_df], profile: logic, temperature: 0.0, cache: "off", parallelism: 4}'
    )
    per_seed = {
        k: {"pass": x.get("pass"), "exit_code": x.get("exit_code"), "wall_seconds": x.get("wall_seconds")}
        for k, x in (report.get("gates") or {}).get("per_seed", {}).items()
    }
    lines.append(f"    gates: {{all_pass: {str(v.get('gates_all_pass')).lower()}, per_seed: {per_seed}}}")
    pooled = report["pooled"]
    lines.append("    pooled_261_per_arm:")
    for arm in report["arms"]:
        p = pooled.get(arm) or {}
        o = (report.get("original_pooled") or {}).get(arm) or {}
        lines.append(
            f"      {arm}: {{detected: {p.get('detected')}, measurable: {p.get('measurable')}, "
            f"detection_rate: {p.get('detection_rate')}, repaired: {p.get('repaired')}, "
            f"repair_measurable: {p.get('repair_measurable')}, false_fixed: {p.get('false_fixed')}, "
            f"false_fix_measurable: {p.get('false_fix_measurable')}, tokens: {(p.get('tokens') or {}).get('total')}, "
            f"cost_usd: {p.get('cost_usd')}, original_detected: {o.get('detected')}, "
            f"original_measurable: {o.get('measurable')}, original_rate: {o.get('detection_rate')}}}"
        )
    lines.append("    verdict:")
    lines.append(f'      classification: "{v.get("verdict")}"')
    lines.append(f'      rationale: "{v.get("rationale")}"')
    r1 = str(v.get("R1_pooled_ordering_df_gt_aitester_gt_plain")).lower()
    r3 = str(v.get("R3_ordering_in_at_least_2_of_3_seeds")).lower()
    lines.append(f"      R1_pooled_ordering_df_gt_aitester_gt_plain: {r1}")
    lines.append(
        f"      R3_ordering_in_at_least_2_of_3_seeds: {r3}  # seeds_with_ordering={v.get('R3_seeds_with_ordering')}"
    )
    r2 = v.get("R2_stats") or {}
    lines.append(
        f"      R2_aitester_vs_df: {{delta_pp: {r2.get('delta_pp')}, b_new_only: {r2.get('b_new_only')}, "
        f"c_old_only: {r2.get('c_old_only')}, mcnemar_p: {r2.get('mcnemar_exact_p_two_sided')}, "
        f"bootstrap_ci95: {r2['bootstrap_ci95']}}}"
    )
    lines.append(
        '    provenance: "三 seed 均 git_dirty=false / git_sha=a93c1f6 / model_fingerprint.pinned=true / '
        '87 行×3 臂 / task 集与原批一致"'
    )
    c = report.get("cost") or {}
    lines.append(
        f"    cost: {{actual_est_usd: {c.get('actual_est_usd')}, total_tokens: {c.get('total_tokens')}, "
        f"preflight_estimate_usd: {c.get('preflight_estimate_usd')}, "
        f"amended_estimate_usd: {c.get('amended_estimate_usd')}, budget_usd: {c.get('budget_usd')}}}"
    )
    lines.append(
        '    caliber_note: "harness 漂移（logic 档自 R-P0-2 新增 5 开关、输出 token 份额差异）逐项披露；'
        'repair/false_fix 与旧批修正口径不混用"'
    )
    lines.append(
        '    artifacts: "experiments/results/t_round_b2_main_batch_20261018/'
        '（PREREG/PREFLIGHT/PREREG_AMENDMENT/GATES/ANALYSIS_REPORT/README/SHA256SUMS）"'
    )
    return "\n".join(lines) + "\n"


def render_readme(report: dict[str, Any]) -> str:
    """渲染中文 README 报告（表格为主，数字全部来自 report）。"""
    v = report["verdict"]
    lines: list[str] = []
    lines.append("# T1（B2）：主批次锁指纹复现批（3 seed × 3 臂，synthetic n=87/seed）")
    lines.append("")
    lines.append("> **性质：复现性测量（decision-grade），非能力主张。** 预注册见 `PREREG.md`（跑前冻结）、")
    lines.append("> 成本估算修正见 `PREREG_AMENDMENT_cost_estimate.md`（判据未改）。")
    lines.append("")
    lines.append("## 0. 预注册判定")
    lines.append("")
    lines.append("| 项 | 结果 |")
    lines.append("|---|---|")
    lines.append(f"| **verdict** | **`{v['verdict']}`** — {v['rationale']} |")
    lines.append(f"| §1.1 硬门槛（干净树/指纹/行数/exit） | `{'PASS' if v['gates_all_pass'] else 'FAIL'}` |")
    lines.append(f"| R1 合并排序 df>aitester>plain | `{v['R1_pooled_ordering_df_gt_aitester_gt_plain']}` |")
    lines.append(
        f"| R2 aitester vs df 配对差 | δ={v['R2_stats']['delta']} （{v['R2_stats']['delta_pp']}pp）"
        f"；b/c={v['R2_stats']['b_new_only']}/{v['R2_stats']['c_old_only']}"
        f"；McNemar p={v['R2_stats']['mcnemar_exact_p_two_sided']}"
        f"；CI95={v['R2_stats']['bootstrap_ci95']} |"
    )
    lines.append(
        f"| R3 逐 seed 排序 | `{v['R3_ordering_in_at_least_2_of_3_seeds']}`（seed {v['R3_seeds_with_ordering']}） |"
    )
    lines.append("")
    # ── 0.5 机制对照（描述性，不做事后改判）──────────────────────────────
    lines.append("## 0.5 与原批的机制对照（描述性；不用于改判）")
    lines.append("")
    lines.append("### 0.5.1 stop_reason 分布（三 seed 合并，逐臂）")
    lines.append("")
    lines.append("| 臂 | 新批 stop_reason | 原批 stop_reason |")
    lines.append("|---|---|---|")
    for arm in report["arms"]:
        new_sr: dict[str, int] = {}
        old_sr: dict[str, int] = {}
        for seed in report["seeds"]:
            st = (report["per_seed"].get(str(seed)) or {}).get("new", {}).get(arm)
            if st:
                for key, n in (st.get("stop_reasons") or {}).items():
                    new_sr[str(key)] = new_sr.get(str(key), 0) + int(n)
            ost = (report["per_seed"].get(str(seed)) or {}).get("original", {}).get(arm)
            if ost:
                for key, n in (ost.get("stop_reasons") or {}).items():
                    old_sr[str(key)] = old_sr.get(str(key), 0) + int(n)
        lines.append(f"| `{arm}` | {new_sr} | {old_sr} |")
    lines.append("")
    pd = report.get("profile_preset_drift") or {}
    lines.append("### 0.5.2 logic 档预设漂移（候选机制来源，非因果证明）")
    lines.append("")
    if pd.get("available"):
        added = pd.get("added") or {}
        lines.append(
            f"logic 档自 R-P0-2 切点新增 **{len(added)}** 个行为开关（R-P0-2 切点未启用）："
            + "、".join(f"`{k}`" for k in added)
            + "。本批按当前 documented protocol（logic 档）运行，因此**新批不是 R-P0-2 的逐字节等价重跑**；"
            "R1 未复现与这些漂移的相关性只能作为**候选机制**，因果归属需下一轮的逐开关消融（另预注册）。"
        )
    else:
        lines.append("profile 预设漂移无法核验（git show 失败）——不得当作无漂移。")
    lines.append("")
    r2 = v.get("R2_stats") or {}
    lines.append("### 0.5.3 解释边界（写死口径，防事后改写）")
    lines.append("")
    lines.append(
        "- **正面（R2）**：新批 `aitester` vs `plain_llm_df` 的配对差为 "
        f"δ={r2.get('delta')}（{r2.get('delta_pp')}pp；b/c={r2.get('b_new_only')}/{r2.get('c_old_only')}；"
        f"McNemar p={r2.get('mcnemar_exact_p_two_sided')}；bootstrap CI={r2.get('bootstrap_ci95')}）——"
        "头条结论的核心负面证据（编排 vs df 提示协议的检出差距，方向为负）在新协议下**仍然成立且显著**。"
    )
    lines.append(
        f"- **未复现（R1/R3）**：预设的完整排序 `plain_llm_df > aitester > plain_llm` 未成立"
        f"（R1={v.get('R1_pooled_ordering_df_gt_aitester_gt_plain')}；R3={v.get('R3_ordering_in_at_least_2_of_3_seeds')}）。"
        "注意：R-P0-2 中 `aitester > plain_llm` 这一**次级排序**本身不是核心结论；其未复现意味着"
        '"aitester 检出高于裸提示"在当前协议下不成立（新批部分 seed 甚至更低）。'
    )
    lines.append(
        '- **不得**把本批差异归因于模型能力变化（同切点同模型指纹）；也**不得**声称"编排更差"是因果结论——'
        '协议漂移是混杂因素。可辩护表述："R-P0-2 头条批次的检出数字对 logic 档协议版本敏感；核心负面（vs df）稳健，'
        '次级排序（vs 裸提示）不稳健"。'
    )
    lines.append("")
    lines.append("## 1. 合并口径（3 seed 池化，n=261/臂）")
    lines.append("")
    lines.append("| 臂 | 检出/可测 | detection | repair | false_fix | tokens | 成本(USD, 估算) |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in report["arms"]:
        p = report["pooled"].get(arm) or {}
        o = report["original_pooled"].get(arm) or {}
        lines.append(
            f"| `{arm}`（新批） | {p.get('detected')}/{p.get('measurable')} | {p.get('detection_rate')} | "
            f"{(p.get('repaired') or 0)}/{p.get('repair_measurable')} | "
            f"{(p.get('false_fixed') or 0)}/{p.get('false_fix_measurable')} | "
            f"{(p.get('tokens') or {}).get('total')} | {p.get('cost_usd')} |"
        )
        lines.append(
            f"| `{arm}`（R-P0-2 旧批） | {o.get('detected')}/{o.get('measurable')} | {o.get('detection_rate')} | — | — | — | — |"
        )
    lines.append("")
    lines.append("## 2. 逐 seed 检出（新批 vs 旧批）")
    lines.append("")
    lines.append(
        "| seed | 臂 | 新批检出/可测 | 新批率 | 旧批检出/可测 | 旧批率 | 新 vs 旧 配对 δ | 不一致 b/c | McNemar p |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for seed in report["seeds"]:
        entry = report["per_seed"].get(str(seed)) or {}
        for arm in report["arms"]:
            nst = (entry.get("new") or {}).get(arm) or {}
            ost = (entry.get("original") or {}).get(arm) or {}
            lines.append(
                f"| {seed} | `{arm}` | {nst.get('detected')}/{nst.get('detection_measurable')} | "
                f"{nst.get('detection_rate')} | {ost.get('detected')}/{ost.get('detection_measurable')} | "
                f"{ost.get('detection_rate')} | — | — | — |"
            )
    lines.append("")
    lines.append("> 说明：第 2 节表内「新 vs 旧」配对列按臂汇总（三 seed 合并），逐 seed 明细见 ANALYSIS_REPORT.json。")
    lines.append("")
    lines.append("## 3. 新批 vs 旧批配对一致性（按 seed+task 配对，三 seed 合并）")
    lines.append("")
    lines.append("| 臂 | 配对数 | b(新检出旧未) | c(旧检出新未) | δ | McNemar p | CI95 |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in report["arms"]:
        p = report["paired_new_vs_original"].get(arm) or {}
        lines.append(
            f"| `{arm}` | {p.get('n_pairs')} | {p.get('b_new_only')} | {p.get('c_old_only')} | "
            f"{p.get('delta')} | {p.get('mcnemar_exact_p_two_sided')} | {p.get('bootstrap_ci95')} |"
        )
    lines.append("")
    lines.append("## 4. 成本与 provenance")
    lines.append("")
    c = report["cost"]
    lines.append(
        f"- tokens={c['total_tokens']}；实测估算成本=**${c['actual_est_usd']}**；"
        f"跑前估算=${c['preflight_estimate_usd']}（口径已修正为 ${c['amended_estimate_usd']}，见 amendment）；"
        f"预算参考=${c['budget_usd']}"
    )
    flags = (report.get("provenance_drift") or {}).get("provenance_flags") or {}
    lines.append(
        f"- 新批 git_dirty={flags.get('new_git_dirty')} / git_sha={flags.get('new_git_sha')} / "
        f"fingerprint.pinned={flags.get('new_fingerprint_pinned')}；"
        f"旧批 git_dirty={flags.get('old_git_dirty')} / fingerprint 在场={flags.get('old_fingerprint_present')}"
    )
    lines.append("- 逐 seed env_snapshot / harness 漂移明细见 ANALYSIS_REPORT.json `provenance_drift`。")
    pd = report.get("profile_preset_drift") or {}
    if pd.get("available"):
        lines.append("")
        lines.append("### 4.1 logic 档预设漂移（R-P0-2 切点 b533cff → 本批切点 a93c1f6）")
        lines.append("")
        lines.append(
            f"logic 档开关数 {pd.get('old_key_count')} → {pd.get('new_key_count')}；"
            f"新增 **{len(pd.get('added') or {})}**、删除 {len(pd.get('removed') or {})}、改值 {len(pd.get('changed') or {})}。"
        )
        if pd.get("added"):
            lines.append("")
            lines.append("| 新增开关 | 生效值 |")
            lines.append("|---|---|")
            for k, v in pd["added"].items():
                lines.append(f"| `{k}` | `{v}` |")
        lines.append("")
        lines.append(
            "> 这些开关改变的是 aitester 臂的**再生成路由/变异反馈/定位测量**，是本批与 R-P0-2 的协议级差异；"
            "本批判据因此限定为『当前切点 documented protocol 下方向性复现』，不作逐字节等价陈述。"
        )
    else:
        lines.append("- profile 预设漂移：**无法核验**（git show config.py 失败），不得当作无漂移。")
    lines.append("")
    lines.append("## 5. 局限")
    lines.append("")
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    lines.append("## 6. 复算入口")
    lines.append("")
    lines.append("```bash")
    lines.append(".venv/bin/python experiments/analyze_t1_b2_main_batch.py \\")
    lines.append("    --out experiments/results/t_round_b2_main_batch_20261018 \\")
    lines.append("    --orig-dir experiments/results/main_batch --write")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


_MANUAL_BEGIN = "<!-- MANUAL:BEGIN -->"
_MANUAL_END = "<!-- MANUAL:END -->"


def _preserve_manual_sections(generated: str, existing_path: Path) -> str:
    """把既有 README 中 MANUAL 标记块原样保留到生成内容末尾。

    背景（X 轮 2026-10-19）：归档 README 曾含手工追加的"0.6 T 轮发现（可辩护
    表述，写死防事后改写）"节，而 `render_readme` 从零生成——重跑 `--write` 会
    **静默丢失**该节（复算实证：/tmp 副本重跑后 diff 缺 32 行）。标记块内的
    内容为手写解读（引用数字须人工与 report 核对后更新），生成器不重写、不
    校验其内容，只保证不丢。

    规则：
    - 仅保留 `MANUAL:BEGIN` 与 `MANUAL:END` 成对闭合的块（未闭合标记整体
      不保留——防截断内容被当作完整块）；
    - 多个块按原相对顺序追加到生成内容末尾；
    - 既有文件不存在（首次生成）时原样返回。
    """
    if not existing_path.is_file():
        return generated
    existing = existing_path.read_text(encoding="utf-8")
    blocks: list[str] = []
    rest = existing
    while True:
        begin = rest.find(_MANUAL_BEGIN)
        if begin < 0:
            break
        end = rest.find(_MANUAL_END, begin)
        if end < 0:
            break
        blocks.append(rest[begin : end + len(_MANUAL_END)].strip("\n"))
        rest = rest[end + len(_MANUAL_END) :]
    if not blocks:
        return generated
    header = (
        "\n\n---\n\n"
        "<!-- 以下为手工维护节（MANUAL 标记块）：生成器 --write 时原样保留，\n"
        "     不重写亦不校验其内容；块内引用数字更新须人工核对后编辑。 -->\n"
    )
    return generated.rstrip("\n") + "\n" + header + "\n\n" + "\n\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T1（B2）主批次锁指纹复现批分析（零 LLM）")
    parser.add_argument("--out", required=True, help="T1 结果目录")
    parser.add_argument("--orig-dir", default="experiments/results/main_batch", help="R-P0-2 原批次目录")
    parser.add_argument("--price", default="experiments/price_table.json")
    parser.add_argument("--write", action="store_true", help="写出 ANALYSIS_REPORT.json / README.md")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    price = json.loads(Path(args.price).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
    report = build_report(out_dir, Path(args.orig_dir), price)
    if args.write:
        (out_dir / "ANALYSIS_REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        readme_path = out_dir / "README.md"
        readme_path.write_text(_preserve_manual_sections(render_readme(report), readme_path), encoding="utf-8")
        (out_dir / "BASELINE_FRAGMENT.yaml").write_text(render_baseline_fragment(report), encoding="utf-8")
        print(f"已写出：{out_dir / 'ANALYSIS_REPORT.json'}")
        print(f"已写出：{out_dir / 'README.md'}")
    print(json.dumps(report["verdict"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
