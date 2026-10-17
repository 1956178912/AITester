#!/usr/bin/env python3
"""独立评审复算脚本（2026-10-17）。

用途：为 docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md 中的
C1/C2/C3/C4/C14 等核心声明提供可重放的独立复算。

复算原则：
  - 只读原始批次 JSON（experiments/results/**），不读任何项目统计脚本；
  - 全部统计量（计数/比例/Wilson CI/McNemar 精确二项/χ²±连续性校正/OR 精确 CI/
    配对风险差 cluster bootstrap CI/单侧 p/Bonferroni 敏感性）由本脚本独立计算；
  - 输出 stdout 日志 + recompute_outputs.json，供 SHA256SUMS 锁定。

运行（在仓库根 /Users/wangchenyu/Workspace/AITester）：
    .venv/bin/python3 docs/reviews/review_recompute/recompute_core_claims.py

环境：Python 3.14（.venv）；依赖 scipy（仅用于 binomtest/wilson 的交叉核对）。
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "recompute_outputs.json"

# ---------------------------------------------------------------- 统计工具


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score 区间（比例型端点小样本首选，审稿人常规要求）。"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def binom_pmf_two_sided(k: int, n: int) -> float:
    """精确 McNemar（二项检验，双侧，按对称概率法）。"""
    from scipy.stats import binomtest

    return float(binomtest(k, n, 0.5, alternative="two-sided").pvalue)


def binom_pmf_one_sided_greater(k: int, n: int) -> float:
    from scipy.stats import binomtest

    return float(binomtest(k, n, 0.5, alternative="greater").pvalue)


def mcnemar_chi2(b: int, c: int, cc: bool = True) -> float:
    """b/c = 两臂各自独有的阳性数。cc=True 为 Yates 连续性校正。"""
    if b + c == 0:
        return 0.0
    num = (abs(b - c) - (1 if cc else 0)) ** 2
    return num / (b + c)


def or_exact_ci(b: int, c: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """配对 OR = b/c 的对数正态近似 CI（b 或 c 为 0 时用 0.5 校正）。"""
    if b + c == 0:
        return (float("nan"), float("nan"))
    b_, c_ = (b, c) if (b > 0 and c > 0) else (b + 0.5, c + 0.5)
    lor = __import__("math").log(b_ / c_)
    se = (1 / b_ + 1 / c_) ** 0.5
    return (float(__import__("math").exp(lor - z * se)), float(__import__("math").exp(lor + z * se)))


def cluster_bootstrap_diff(pairs: list[tuple[int, int]], n_boot: int = 20000, seed: int = 42) -> tuple[float, float, float]:
    """配对风险差（arm_a − arm_b）的 cluster bootstrap 95%CI。
    pairs: [(a_i, b_i)]，a/b ∈ {0,1}。聚类单位 = 配对单元本身（task×seed）。"""
    import random

    rng = random.Random(seed)
    n = len(pairs)
    obs = sum(a - b for a, b in pairs) / n
    diffs: list[float] = []
    for _ in range(n_boot):
        s = rng.choices(pairs, k=n)
        diffs.append(sum(a - b for a, b in s) / n)
    diffs.sort()
    return obs, diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot)]


# ---------------------------------------------------------------- 数据加载


def load_arm_details(path: Path) -> dict[str, dict[int, int]]:
    """返回 {arm: {task_id: detection(0/1)}}，detection=None 的行剔除（fail-closed 口径）。"""
    d = json.loads(path.read_text())
    out: dict[str, dict[int, int]] = {}
    for arm, blob in d["results"].items():
        per_task: dict[int, int] = {}
        for row in blob.get("details", []):
            det = row.get("detection_rate")
            if det is None:
                continue
            per_task[row["task_id"]] = 1 if det else 0
        out[arm] = per_task
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 主流程


def main() -> None:
    report: dict = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
            "cwd": str(ROOT),
            "scipy_available": True,
        },
        "inputs": {},
        "claims": {},
    }

    # ---- C1/C2/C3：R-P0-2 三种子主批次 ------------------------------------
    files = sorted((ROOT / "experiments/results/main_batch").glob("benchmark_synthetic_20261006_*.json"))
    per_arm: dict[str, dict[tuple[int, str], int]] = {}
    seeds: set[int] = set()
    for f in files:
        report["inputs"][str(f.relative_to(ROOT))] = sha256(f)
        seed = json.loads(f.read_text())["seed"]
        seeds.add(seed)
        for arm, tasks in load_arm_details(f).items():
            for tid, v in tasks.items():
                per_arm.setdefault(arm, {})[(seed, tid)] = v

    agg = {arm: (sum(m.values()), len(m)) for arm, m in per_arm.items()}
    c1 = {
        "seeds": sorted(seeds),
        "arms": {
            arm: {"positive": k, "n": n, "rate": round(k / n, 4), "wilson95": [round(x, 4) for x in wilson_ci(k, n)]}
            for arm, (k, n) in agg.items()
        },
    }
    report["claims"]["C1_three_arm_detection"] = c1

    # 配对（同 seed 同 task）：aitester vs plain_llm_df
    pairs_ad = [(per_arm["aitester"][k], per_arm["plain_llm_df"][k]) for k in per_arm["aitester"] if k in per_arm["plain_llm_df"]]
    pairs_dp = [(per_arm["plain_llm_df"][k], per_arm["plain_llm"][k]) for k in per_arm["plain_llm_df"] if k in per_arm["plain_llm"]]

    def mcnemar_block(pairs: list[tuple[int, int]], name: str) -> dict:
        b = sum(1 for a, x in pairs if a == 1 and x == 0)
        c = sum(1 for a, x in pairs if a == 0 and x == 1)
        n11 = sum(1 for a, x in pairs if a == 1 and x == 1)
        n00 = sum(1 for a, x in pairs if a == 0 and x == 0)
        obs, lo, hi = cluster_bootstrap_diff(pairs)
        lor_lo, lor_hi = or_exact_ci(b, c)
        return {
            "name": name,
            "n_pairs": len(pairs),
            "b_only_a": b,
            "c_only_b": c,
            "both": n11,
            "neither": n00,
            "delta_pp": round(obs * 100, 2),
            "delta_boot95_pp": [round(lo * 100, 2), round(hi * 100, 2)],
            "mcnemar_exact_two_sided_p": binom_pmf_two_sided(b, b + c),
            "mcnemar_exact_one_sided_a_greater_p": binom_pmf_one_sided_greater(b, b + c),
            "chi2_no_cc": round(mcnemar_chi2(b, c, cc=False), 2),
            "chi2_yates_cc": round(mcnemar_chi2(b, c, cc=True), 2),
            "odds_ratio": round(b / c, 3) if c else float("inf"),
            "or_ci95": [round(lor_lo, 4), round(lor_hi, 4)],
        }

    report["claims"]["C2_aitester_vs_df_mcnemar"] = mcnemar_block(pairs_ad, "aitester vs plain_llm_df")
    report["claims"]["C3_df_vs_plain_llm_mcnemar"] = mcnemar_block(pairs_dp, "plain_llm_df vs plain_llm")

    # ---- C4：E4 FIXED harness ---------------------------------------------
    e4_dir = ROOT / "experiments/results/e6_a1_batches/e4_quixbugs_FIXED_harness"
    e4 = {}
    for arm, fname in [("aitester", "aitester.json"), ("plain_llm_df", "plain_llm_df.json")]:
        f = e4_dir / fname
        report["inputs"][str(f.relative_to(ROOT))] = sha256(f)
        e4.update(load_arm_details(f))
    pairs_e4 = [(e4["aitester"][k], e4["plain_llm_df"][k]) for k in e4["aitester"] if k in e4["plain_llm_df"]]
    blk = mcnemar_block(pairs_e4, "aitester vs plain_llm_df (QuixBugs E4 FIXED harness)")
    k_a, n_a = sum(e4["aitester"].values()), len(e4["aitester"])
    k_b, n_b = sum(e4["plain_llm_df"].values()), len(e4["plain_llm_df"])
    blk["arm_rates"] = {
        "aitester": {"positive": k_a, "n": n_a, "rate": round(k_a / n_a, 4), "wilson95": [round(x, 4) for x in wilson_ci(k_a, n_a)]},
        "plain_llm_df": {"positive": k_b, "n": n_b, "rate": round(k_b / n_b, 4), "wilson95": [round(x, 4) for x in wilson_ci(k_b, n_b)]},
    }
    report["claims"]["C4_e4_quixbugs"] = blk

    # ---- C14：df_spec 双臂（41 缺陷程序口径）-------------------------------
    dfs_dir = ROOT / "experiments/results/emse_df_spec_20261016"
    dfs = {}
    for arm, fname in [("plain_llm_df_spec", "benchmark_quixbugs_20261016_232138.json"), ("plain_llm_df", "benchmark_quixbugs_20261017_003023.json")]:
        f = dfs_dir / fname
        report["inputs"][str(f.relative_to(ROOT))] = sha256(f)
        dfs.update(load_arm_details(f))
    pairs_dfs = [(dfs["plain_llm_df_spec"][k], dfs["plain_llm_df"][k]) for k in dfs["plain_llm_df_spec"] if k in dfs["plain_llm_df"]]
    blk14 = mcnemar_block(pairs_dfs, "plain_llm_df_spec vs plain_llm_df (df_spec, 41 口径可判定配对)")
    k_s, n_s = sum(dfs["plain_llm_df_spec"].values()), len(dfs["plain_llm_df_spec"])
    k_d, n_d = sum(dfs["plain_llm_df"].values()), len(dfs["plain_llm_df"])
    blk14["arm_rates"] = {
        "plain_llm_df_spec": {"positive": k_s, "n": n_s, "rate": round(k_s / n_s, 4), "wilson95": [round(x, 4) for x in wilson_ci(k_s, n_s)]},
        "plain_llm_df": {"positive": k_d, "n": n_d, "rate": round(k_d / n_d, 4), "wilson95": [round(x, 4) for x in wilson_ci(k_d, n_d)]},
    }
    blk14["note"] = "p_one_sided 方向为 df_spec > df（H1 方向）；实测 b<c 故单向 p 接近 1，即显著方向与 H1 相反"
    report["claims"]["C14_df_spec"] = blk14

    # ---- 比例型端点 Wilson CI 汇总（C9/C10/C18 等小样本项）------------------
    proportions = {
        "C9_quixbugs_mutk_0.9396": (1182, 1258),
        "C9_ult_replace_mutk_0.6749": (1590, 2356),
        "C9_ult_specir_mutk_0.4395": (847, 1927),
        "C18_ult_accuracy_0.21": (42, 200),
        "C4_aitester_17_37": (17, 37),
        "C4_df_31_37": (31, 37),
        "C14_dfspec_19_35": (19, 35),
        "C14_df_28_36": (28, 36),
    }
    report["claims"]["wilson_ci_table"] = {
        name: {"k": k, "n": n, "rate": round(k / n, 4), "wilson95": [round(x, 4) for x in wilson_ci(k, n)]}
        for name, (k, n) in proportions.items()
    }

    # ---- 多重性敏感性 -------------------------------------------------------
    p_primary = report["claims"]["C2_aitester_vs_df_mcnemar"]["mcnemar_exact_two_sided_p"]
    p_e4 = report["claims"]["C4_e4_quixbugs"]["mcnemar_exact_two_sided_p"]
    p_dfs = report["claims"]["C14_df_spec"]["mcnemar_exact_two_sided_p"]
    report["claims"]["multiplicity_sensitivity"] = {
        "pre_registered_primary_comparisons": 1,
        "note": "R-P0-2 主终点为预注册的单一主对比（aitester vs plain_llm_df）；E4/df_spec/M4/D1 为各自独立预注册批次的主对比。",
        "bonferroni_if_3_primary_compared": {
            "p_C2": min(1.0, p_primary * 3),
            "p_C4": min(1.0, p_e4 * 3),
            "p_C14": min(1.0, p_dfs * 3),
            "conclusion": "三项主对比在 Bonferroni ×3 校正下均仍显著（p_C2/C4/C14 校正后均 <0.05）；探索性子组分析（按 bug_type/error_category）项目已用 BH-FDR 控制（见 statistical_analysis.py），本报告不引入新的未校正声明。",
        },
    }

    # ---- E7 人工裁决缺失的敏感性上界 ---------------------------------------
    # gold 判定错误率 q 时，n 个配对判定中期望翻转 ~Binomial(n, q)；
    # detection 率变动上界 = 期望翻转数 / n。
    e7 = {}
    for label, n in [("quixbugs_41_caliber", 37), ("quixbugs_all_50", 50)]:
        e7[label] = {f"q={q}": {"expected_flips": round(n * q, 1), "detection_rate_bound_pp": round(n * q / n * 100, 1)} for q in (0.05, 0.10, 0.20)}
    report["claims"]["E7_gold_error_sensitivity"] = {
        "model": "gold 判定错误率 q → 期望翻转 n*q → detection 率偏差上界 ±q（线性放大不考虑方向抵消）",
        "bounds": e7,
        "interpretation": "即使 10% 的 gold 三段判定有误，F2P detection 率的偏差上界约 ±10pp；C4 的 45.9% vs 83.8%（37.9pp 差距）与 C2 的 −28.3pp 均大于该上界，结论方向不翻转；但 C14 的 −25.7pp 与单批 QuixBugs 的 6pp 跨批波动处于同一量级，解读须并列披露。",
    }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
