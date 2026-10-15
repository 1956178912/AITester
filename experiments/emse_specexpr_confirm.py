"""M4：SpecExpr 确认性实验分析脚本（零 LLM，纯 stdlib）。

背景（预注册 61a7e04，EMSE 批次四）：
    synthetic seed45/46 × 87 任务 × 2 臂（replace 纯 NL vs
    replace+SpecExpr）的 SpecExpr 确认性实验。本脚本做零 LLM 复算：
    - 种子内配对 + 池化计数（**跨种子 task_id 错配防护**——两种子
      task_id 相同但任务内容不同，错配会产生虚假配对）；
    - 统计量与项目定案值对齐（pilot b=7/c=1/n=50 → δ=12pp、p=0.0703）；
    - 预注册判定规则（confirmed / trend / not_confirmed / indeterminate）；
    - 不对称应用审计（forward/reverse 双向分解——reverse 违反材料包含律）；
    - 回退子集敏感性（仅双 applied 子集的 McNemar）；
    - 机制统计（fallback_rate / spec_expr_coverage / detection_marginal，
      None 处理）；
    - provenance 校验（replace 臂 SPEC_IR_ENABLE 必须 None）与工件缺失
      的可读诊断。

零 LLM 纪律：只消费已归档 JSON 工件（results.aitester.details +
provenance.env_snapshot），不触发任何 LLM 调用。
"""

from __future__ import annotations

import json
import math
import sys
from math import comb
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ─── 预注册常量（与 61a7e04 同族） ───
CONFIRM_P = 0.05
CONFIRM_DELTA_PP = 8.0
TREND_P = 0.10

# 批次工件子目录（batch_dir 下：sNN_replace / sNN_specir）
_REPLACE_SUFFIX = "_replace"
_SPECIR_SUFFIX = "_specir"


class MissingArtifactError(Exception):
    """批次工件缺失或结构不完整（含目录路径的可读诊断）。"""


# ─── McNemar 统计原语 ───────────────────────────────────────────────────
def _mcnemar_exact_p(b_pos: int, b_neg: int) -> float:
    """McNemar 精确双侧 p（二项检验，n=b_pos+b_neg, p0=0.5）。"""
    n = b_pos + b_neg
    if n == 0:
        return 1.0
    k = min(b_pos, b_neg)
    one_sided = sum(comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(2.0 * one_sided, 1.0)


def _bf10_jeffreys(b_pos: int, b_neg: int) -> dict[str, Any]:
    """McNemar 二项模型 BF10（Jeffreys 先验 Beta(0.5,0.5)）+ 判读。"""
    n = b_pos + b_neg
    if n == 0:
        return {"bf10_jeffreys": None, "verdict": "不可判定（无不一致对）"}
    from math import lgamma

    def _log_beta(x: float, y: float) -> float:
        return lgamma(x) + lgamma(y) - lgamma(x + y)

    log_p_h1 = math.log(comb(n, b_pos)) + _log_beta(b_pos + 0.5, b_neg + 0.5) - _log_beta(0.5, 0.5)
    log_p_h0 = math.log(comb(n, b_pos)) + n * math.log(0.5)
    bf = math.exp(log_p_h1 - log_p_h0)
    if bf >= 10:
        verdict = "强支持 H1"
    elif bf >= 3:
        verdict = "中等支持 H1"
    elif bf <= 0.1:
        verdict = "强支持 H0"
    elif bf <= 1 / 3:
        verdict = "支持 H0"
    else:
        verdict = "证据不足"
    return {"bf10_jeffreys": round(bf, 4), "verdict": verdict}


def contrast_from_counts(counts: dict[str, int]) -> dict[str, Any]:
    """从四种计数（only_first/only_second/both/neither）算统计量。

    δ = (only_first − only_second) / n_pairs × 100；
    无不一致对 → MDE / 所需配对数 = None（设计无鉴别力，保守口径）。
    """
    only_first = counts.get("only_first", 0)
    only_second = counts.get("only_second", 0)
    both = counts.get("both", 0)
    neither = counts.get("neither", 0)
    n_pairs = only_first + only_second + both + neither
    discordant = only_first + only_second
    delta_pp = (only_first - only_second) / n_pairs * 100 if n_pairs else 0.0
    p_exact = _mcnemar_exact_p(only_first, only_second)
    bf10 = _bf10_jeffreys(only_first, only_second)
    # MDE / 所需配对数（正态近似，与 emse_optimization 同族）
    mde_pp: float | None = None
    required_pairs: int | None = None
    if discordant > 0:
        psi = discordant / n_pairs
        z_a, z_b = 1.959964, 0.841621
        mde_pp = 100.0 * (z_a + z_b) * math.sqrt(psi / (4 * n_pairs))
        required_pairs = math.ceil(((z_a + z_b) ** 2) * psi / (4 * ((8.0 / 100) ** 2)))
    return {
        "n_pairs": n_pairs,
        "delta_pp": round(delta_pp, 2),
        "p_exact": round(p_exact, 4),
        "discordant": discordant,
        "bf10": bf10,
        "mde_pp": round(mde_pp, 2) if mde_pp is not None else None,
        "required_pairs_for_8pp": required_pairs,
        # 别名键（build_analysis 的 primary_pooled 消费）：
        "only_specir": only_first,
        "only_replace": only_second,
    }


# ─── 预注册判定 ─────────────────────────────────────────────────────────
def verdict(contrast: dict[str, Any]) -> str:
    """预注册判定（与 61a7e04 同族）：
    - p<0.05 ∧ δ≥8pp = confirmed；
    - p<0.05 ∧ 0<δ<8pp = not_confirmed（**显著但效应量不足**——统计
      显著不等于效应量达标，预注册要求 δ≥8pp 才算 confirmed，δ 不达
      即便 p 小也判 not_confirmed，防小样本 p 值过拟合）；
    - 0.05≤p<0.10 ∧ δ>0 = trend；
    - 其余（δ≤0 / p≥0.10）= not_confirmed；
    - 统计量缺失 = indeterminate。
    """
    p = contrast.get("p_exact")
    delta = contrast.get("delta_pp")
    if p is None or delta is None:
        return "indeterminate"
    if p < CONFIRM_P:
        # p 显著但效应量未达 CONFIRM_DELTA_PP → 预注册判 not_confirmed
        return "confirmed" if delta >= CONFIRM_DELTA_PP else "not_confirmed"
    if p < TREND_P and delta > 0:
        return "trend"
    return "not_confirmed"


# ─── 池化纪律：跨种子错配防护 ──────────────────────────────────────────
def pooled_counts(seeds: list[dict[str, int]]) -> dict[str, int]:
    """池化 = 各种子分量分量和（**绝不做跨种子配对**——两种子 task_id
    相同但任务内容不同，错配会产生虚假配对；只合计计数值）。"""
    out = {"only_first": 0, "only_second": 0, "both": 0, "neither": 0}
    for c in seeds:
        for k in out:
            out[k] += c.get(k, 0)
    out["n_pairs"] = out["only_first"] + out["only_second"] + out["both"] + out["neither"]
    out["discordant"] = out["only_first"] + out["only_second"]
    return out


# ─── 机制统计与审计 ────────────────────────────────────────────────────
def mechanism_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """机制统计（None 处理：不可测行不进分子分母，保守口径）。"""
    n_rows = len(rows)
    applied_counter: dict[str, int] = {}
    for r in rows:
        a = r.get("spec_replace_applied")
        if a:
            applied_counter[a] = applied_counter.get(a, 0) + 1
    fallback_rate = None
    if n_rows:
        fb = applied_counter.get("attempted_fallback", 0)
        fallback_rate = round(fb / n_rows, 4)
    cov_vals = [r.get("spec_expr_coverage") for r in rows if r.get("spec_expr_coverage") is not None]
    compile_vals = [r.get("spec_compile_rate") for r in rows if r.get("spec_compile_rate") is not None]
    det_vals = [r.get("detection_rate") for r in rows if r.get("detection_rate") is not None]
    return {
        "n_rows": n_rows,
        "spec_replace_applied": applied_counter,
        "fallback_rate": fallback_rate,
        "spec_expr_coverage_mean": round(sum(cov_vals) / len(cov_vals), 4) if cov_vals else None,
        "spec_expr_coverage_n": len(cov_vals),
        "spec_compile_rate_mean": round(sum(compile_vals) / len(compile_vals), 4) if compile_vals else None,
        "detection_available": len(det_vals),
        "detection_positive": sum(1 for d in det_vals if d == 1.0),
        "detection_marginal": round(sum(1 for d in det_vals if d == 1.0) / len(det_vals), 4) if det_vals else None,
    }


def asymmetry_audit(replace_rows: list[dict], specir_rows: list[dict]) -> dict[str, Any]:
    """不对称应用审计（同 task 两臂 spec_replace_applied 不一致）。

    双向分解：
    - forward = replace applied ∧ specir fallback（replace 有材料 specir 没应用）；
    - reverse = replace fallback ∧ specir applied（**违反材料包含律**——
      SpecExpr 材料 ⊇ NL，specir 应用时 replace 必应用；reverse 案例须
      单独计数并在报告中披露根因）。
    """
    replace_map = {r.get("task_id"): r.get("spec_replace_applied") for r in replace_rows}
    specir_map = {r.get("task_id"): r.get("spec_replace_applied") for r in specir_rows}
    common = set(replace_map) & set(specir_map)
    asymmetric: list[str] = []
    forward = 0
    reverse = 0
    for tid in sorted(common):
        r_app, s_app = replace_map[tid], specir_map[tid]
        if r_app != s_app:
            asymmetric.append(tid)
            if r_app == "attempted_replaced" and s_app == "attempted_fallback":
                forward += 1
            elif r_app == "attempted_fallback" and s_app == "attempted_replaced":
                reverse += 1
    return {
        "n_compared": len(common),
        "n_asymmetric": len(asymmetric),
        "asymmetric_task_ids": asymmetric,
        "n_forward_replace_applied_specir_fallback": forward,
        "n_reverse_replace_fallback_specir_applied": reverse,
    }


def applied_subset_contrast(replace_rows: list[dict], specir_rows: list[dict]) -> dict[str, Any]:
    """回退子集敏感性：仅双 applied（spec_replace_applied=attempted_replaced
    且 detection 非 None）的任务子集做 McNemar。"""
    replace_applied = {
        r.get("task_id"): r.get("detection_rate")
        for r in replace_rows
        if r.get("spec_replace_applied") == "attempted_replaced" and r.get("detection_rate") is not None
    }
    specir_applied = {
        r.get("task_id"): r.get("detection_rate")
        for r in specir_rows
        if r.get("spec_replace_applied") == "attempted_replaced" and r.get("detection_rate") is not None
    }
    common = set(replace_applied) & set(specir_applied)
    only_first = only_second = both = neither = 0
    for tid in common:
        r1 = 1 if replace_applied[tid] == 1.0 else 0
        s1 = 1 if specir_applied[tid] == 1.0 else 0
        # specir vs replace（第一臂=specir）
        if s1 and not r1:
            only_first += 1
        elif r1 and not s1:
            only_second += 1
        elif s1 and r1:
            both += 1
        else:
            neither += 1
    n = len(common)
    delta_pp = (only_first - only_second) / n * 100 if n else 0.0
    p_exact = _mcnemar_exact_p(only_first, only_second)
    return {
        "n_pairs": n,
        "only_first": only_first,
        "only_second": only_second,
        "both": both,
        "neither": neither,
        "delta_pp": round(delta_pp, 2),
        "p_exact": round(p_exact, 4),
    }


# ─── 工件加载 ───────────────────────────────────────────────────────────
def _load_batch(batch_dir: Path, suffix: str, seed: int) -> tuple[list[dict], dict[str, Any]]:
    """加载 sNN_replace / sNN_specir 子目录的批次 JSON（details + provenance）。"""
    sub = batch_dir / f"s{seed}{suffix}"
    json_files = sorted(sub.glob("*.json")) if sub.is_dir() else []
    if not json_files:
        raise MissingArtifactError(f"批次工件缺失: {sub}（无 JSON 文件）")
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    details = (data.get("results") or {}).get("aitester", {}).get("details", [])
    if not isinstance(details, list):
        raise MissingArtifactError(f"工件 details 非 list: {json_files[0]}")
    provenance = data.get("provenance") or {}
    return details, provenance


def _verify_provenance(provenance_replace: dict, provenance_specir: dict, seed: int) -> bool:
    """provenance 校验：replace 臂 SPEC_IR_ENABLE 必须 None / 未开启；
    specir 臂必须 true；两臂同 seed + 同 fingerprint。"""
    env_r = provenance_replace.get("env_snapshot") or {}
    env_s = provenance_specir.get("env_snapshot") or {}
    # replace 臂 SPEC_IR 必须关闭
    if (env_r.get("SPEC_IR_ENABLE") or "").lower() in ("true", "1", "on"):
        return False
    # specir 臂 SPEC_IR 必须开启
    if (env_s.get("SPEC_IR_ENABLE") or "").lower() not in ("true", "1", "on"):
        return False
    # 同 seed
    if provenance_replace.get("seed") != seed or provenance_specir.get("seed") != seed:
        return False
    # 同 model fingerprint
    fp_r = (provenance_replace.get("model_fingerprint") or {}).get("system_fingerprint")
    fp_s = (provenance_specir.get("model_fingerprint") or {}).get("system_fingerprint")
    return not (fp_r and fp_s and fp_r != fp_s)


def _seed_contrast(replace_rows: list[dict], specir_rows: list[dict]) -> dict[str, Any]:
    """单种子内配对（specir vs replace，标准口径：双 detection 非 None）。"""
    replace_map = {r.get("task_id"): r.get("detection_rate") for r in replace_rows}
    specir_map = {r.get("task_id"): r.get("detection_rate") for r in specir_rows}
    common = set(replace_map) & set(specir_map)
    only_first = only_second = both = neither = 0
    for tid in common:
        r_det, s_det = replace_map[tid], specir_map[tid]
        if r_det is None or s_det is None:
            continue
        r1 = 1 if r_det == 1.0 else 0
        s1 = 1 if s_det == 1.0 else 0
        if s1 and not r1:
            only_first += 1
        elif r1 and not s1:
            only_second += 1
        elif s1 and r1:
            both += 1
        else:
            neither += 1
    return {
        "only_first": only_first,
        "only_second": only_second,
        "both": both,
        "neither": neither,
        "n_pairs": only_first + only_second + both + neither,
    }


# ─── 主分析 ─────────────────────────────────────────────────────────────
def build_analysis(batch_dir: Path | str) -> dict[str, Any]:
    """读 2 种子 × 2 臂工件，做种子内配对 + 池化 + provenance 校验。

    返回 {primary_pooled, per_seed, provenance_ok, asymmetry_total,
    design_sensitivity, verdict}。
    """
    batch_dir = Path(batch_dir)
    seeds: list[dict[str, Any]] = []
    all_replace_rows: list[dict] = []
    all_specir_rows: list[dict] = []
    provenance_ok = True

    for seed in (45, 46):
        replace_rows, prov_r = _load_batch(batch_dir, _REPLACE_SUFFIX, seed)
        specir_rows, prov_s = _load_batch(batch_dir, _SPECIR_SUFFIX, seed)
        all_replace_rows.extend(replace_rows)
        all_specir_rows.extend(specir_rows)
        if not _verify_provenance(prov_r, prov_s, seed):
            provenance_ok = False
        sc = _seed_contrast(replace_rows, specir_rows)
        seeds.append({"seed": seed, "contrast": sc, "rows_replace": replace_rows, "rows_specir": specir_rows})

    pooled = pooled_counts([s["contrast"] for s in seeds])
    pooled_contrast = contrast_from_counts(pooled)
    audit_all = asymmetry_audit(all_replace_rows, all_specir_rows)
    design_sensitivity = mechanism_stats(all_specir_rows)
    # 设计敏感性补充：replace 边际（基线天花板核对）
    replace_mech = mechanism_stats(all_replace_rows)
    design_sensitivity["replace_marginal"] = replace_mech["detection_marginal"]
    design_sensitivity["specir_marginal"] = design_sensitivity["detection_marginal"]

    return {
        "primary_pooled": {
            **pooled,
            "only_specir": pooled["only_first"],
            "only_replace": pooled["only_second"],
            "delta_pp": pooled_contrast["delta_pp"],
            "p_exact": pooled_contrast["p_exact"],
            "bf10": pooled_contrast["bf10"],
        },
        "per_seed": [
            {
                "seed": s["seed"],
                "contrast": s["contrast"],
                "seed_p": round(_mcnemar_exact_p(s["contrast"]["only_first"], s["contrast"]["only_second"]), 4),
            }
            for s in seeds
        ],
        "provenance_ok": provenance_ok,
        "asymmetry_total": audit_all["n_asymmetric"],
        "asymmetry_detail": audit_all,
        "design_sensitivity": design_sensitivity,
        "verdict": verdict(pooled_contrast),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI：`--batch-dir <dir>` 读 2 种子 × 2 臂工件，输出分析 JSON。"""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--batch-dir",
        default="experiments/results/emse_specexpr_synth_20261014",
        help="批次工件根目录（含 s45_replace 等子目录）",
    )
    ap.add_argument("--out", default=None, help="结果落盘路径（JSON）")
    args = ap.parse_args(argv)

    analysis = build_analysis(Path(args.batch_dir))
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[emse_specexpr_confirm] 结果已落盘 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
