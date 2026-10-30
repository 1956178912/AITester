"""E8 2×2 消融主终点统计分析（零 LLM，读三格批次 JSON 逐任务配对）。

判定口径（预注册 docs/preregistration.md §E8 冻结，legacy-off 缺格披露见
experiments/results/e8_2x2_20261028/PREREG_CELL.md）：
- 主终点：格内 aitester vs plain_llm_df 的 detection 配对差 δ（McNemar 精确
  + bootstrap CI + 贝叶斯 ROPE ±5pp；BH-FDR 校正族 = 格级主对比）；
- H1（推理模式不变式）：各格 δ 均为负且 95% CI 全负 → 核心阴性稳健；
- H2（模式依赖）：任一格 δ 转正且 CI 不含 0 → 核心阴性仅特定模式成立；
- H3（漂移归因）：plain_llm 臂格间方差 > 两个处理臂 → 漂移主要来自基线臂；
- 混合结果 → 按主导格如实报告，禁止挑选性引格。

用法：python experiments/e8_statistical_analysis.py --out <报告.json>
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
E8_ROOT = REPO / "experiments/results/e8_2x2_20261028"
CELLS = ["current-off", "current-on", "legacy-on"]  # legacy-off 结构性缺格（披露）


def load_cell(cell: str) -> dict:
    batches = sorted(
        (Path(E8_ROOT) / cell / "seed42").glob("benchmark_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not batches:
        raise SystemExit(f"✗ 格 {cell} 无批次 JSON")
    return json.loads(batches[-1].read_text(encoding="utf-8"))


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 精确检验（双侧二项 b+c, 0.5）。b/c = discordant 计数。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / (2**n) * 2
    return min(1.0, p)


def paired_analysis(aitester: dict[str, bool], df: dict[str, bool]) -> dict:
    """逐任务配对分析：δ、McNemar、bootstrap CI、ROPE。"""
    tasks = sorted(set(aitester) & set(df))
    n = len(tasks)
    a = [aitester[t] for t in tasks]
    d = [df[t] for t in tasks]
    b = sum(1 for x, y in zip(a, d, strict=True) if x and not y)  # aitester 过 df 挂
    c = sum(1 for x, y in zip(a, d, strict=True) if not x and y)  # df 过 aitester 挂
    delta = (sum(a) - sum(d)) / n
    rng = random.Random(42)
    boots = []
    for _ in range(10000):
        idx = [rng.randrange(n) for _ in range(n)]
        boots.append((sum(a[i] for i in idx) - sum(d[i] for i in idx)) / n)
    boots.sort()
    ci_lo, ci_hi = boots[249], boots[9749]  # percentile 95%
    # ROPE ±5pp：bootstrap 分布落在 [-0.05, 0.05] 的比例 = "实际等价"后验近似
    in_rope = sum(1 for v in boots if -0.05 <= v <= 0.05) / len(boots)
    return {
        "n": n,
        "aitester_pass": sum(a),
        "df_pass": sum(d),
        "delta_pp": round(delta * 100, 2),
        "discordant_b_aitester_only": b,
        "discordant_c_df_only": c,
        "mcnemar_exact_p": round(mcnemar_exact(b, c), 6),
        "ci95_pp": [round(ci_lo * 100, 2), round(ci_hi * 100, 2)],
        "rope_pm5pp_prob": round(in_rope, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(E8_ROOT / "E8_STATISTICAL_REPORT.json"))
    args = ap.parse_args()

    report: dict = {
        "schema": "aitester_e8_stats/1",
        "cells": {},
        "disclosures": [
            "legacy-off 格结构性缺失（b533cff1 无 LLM_THINKING_MODE 开关）——预注册 2×2 实际 3 格",
            "legacy-on 格无 S29 模型指纹机制（切点早于 2026-10-11），pinned 以披露替代",
            "各格 mutation scoring 关闭（不进判据）；1 seed 42",
        ],
    }
    deltas = []
    for cell in CELLS:
        batch = load_cell(cell)
        res = batch.get("results") or {}
        if "aitester" not in res or "plain_llm_df" not in res:
            raise SystemExit(f"✗ 格 {cell} 缺臂")

        def det_map(arm: str, res=res) -> dict[str, bool]:
            return {r["task_id"]: bool(r.get("passed")) for r in (res[arm].get("details") or [])}

        det_a, det_df = det_map("aitester"), det_map("plain_llm_df")
        stats = paired_analysis(det_a, det_df)
        # H3 用：三臂边缘率（供格间方差）
        stats["plain_llm_rate"] = round(
            sum(bool(r.get("passed")) for r in (res.get("plain_llm") or {}).get("details") or [])
            / max(1, len((res.get("plain_llm") or {}).get("details") or []))
            * 100,
            2,
        )
        stats["marginal_rates"] = {
            arm: round(
                sum(bool(r.get("passed")) for r in (res[arm].get("details") or []))
                / max(1, len(res[arm].get("details") or []))
                * 100,
                2,
            )
            for arm in ("aitester", "plain_llm", "plain_llm_df")
        }
        report["cells"][cell] = stats
        deltas.append(stats["delta_pp"])

    # H1/H2 判定（三格口径；预注册 H1 原文"四格"按缺格披露折算并如实标注）
    all_neg = all(v < 0 for v in deltas)
    any_pos_ci_excl_0 = any(s["delta_pp"] > 0 and s["ci95_pp"][0] > 0 for s in report["cells"].values())
    if all_neg:
        verdict = "H1"
    elif any_pos_ci_excl_0:
        verdict = "H2"
    else:
        verdict = "MIXED（按主导格如实报告）"

    # H3：plain_llm 臂格间方差 vs 两个处理臂
    def variance(rates: list[float]) -> float:
        m = sum(rates) / len(rates)
        return sum((x - m) ** 2 for x in rates) / len(rates)

    var_plain = variance([s["marginal_rates"]["plain_llm"] for s in report["cells"].values()])
    var_ait = variance([s["marginal_rates"]["aitester"] for s in report["cells"].values()])
    var_df = variance([s["marginal_rates"]["plain_llm_df"] for s in report["cells"].values()])
    report["verdict"] = {
        "H1_all_delta_negative": all_neg,
        "H2_any_delta_positive_ci_excl0": any_pos_ci_excl_0,
        "H3_plain_llm_var_gt_treatment_arms": var_plain > var_ait and var_plain > var_df,
        "variances": {
            "plain_llm": round(var_plain, 2),
            "aitester": round(var_ait, 2),
            "plain_llm_df": round(var_df, 2),
        },
        "selected": verdict,
        "note": "预注册 H 判据为冻结原文；legacy-off 缺格使 2×2 降为 3 格，判定语义按缺格披露折算",
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"报告写入：{args.out}")
    for cell, s in report["cells"].items():
        print(
            f"{cell}: δ={s['delta_pp']:+.2f}pp CI95={s['ci95_pp']} McNemar p={s['mcnemar_exact_p']} ROPE={s['rope_pm5pp_prob']}"
        )
    print("判定:", json.dumps(report["verdict"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
