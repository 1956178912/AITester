"""H1 载荷等价实验的统计分析（预注册 §3/§4 的机器实现）。

输入：``experiments/results/e3_h1_payload/<arm>/benchmark_*.json``（每臂取最新一份）。
输出：``H1_STATISTICAL_REPORT.json`` + ``H1_STATISTICAL_REPORT.md``。

口径（逐条对应预注册，不得在取数后改）：

- 主终点 δ = ``detection_rate(①df_parity) − detection_rate(③full)``，逐 task 配对；
  ``detection_rate`` 为 ``None`` 的行从配对分母剔除，并**并列报告剔除数**
  （§3.1：禁止把 None 记为 0）。
- S1 McNemar 精确检验：主判定用**单侧**（H1 方向），并列双尾。
- S3 贝叶斯 ROPE ±5pp（复用 ``experiments/bayesian_paired.py``）。
- S2 BH-FDR：对预注册对比统一校正；本次结构水平未跑，实际对比数为 1。
- §3.4 assay-sensitivity：②与 REF（gold 口径 75.6%，工件已清除）差 > 10pp
  ⇒ 标注"assay sensitivity 未建立"，结论降级为不可判定。
- §3.2 判定：δ ≥ +20pp ∧ p_BH < 0.05 ⇒ H1 成立；δ ≤ +5pp ∧ P(|δ|≤5pp) ≥ 0.90
  ⇒ H1 否证；其余 indeterminate。

用法::

    .venv/bin/python experiments/h1_payload_analysis.py
    .venv/bin/python experiments/h1_payload_analysis.py --root experiments/results/e3_h1_smoke
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:  # 允许以 `python experiments/xxx.py` 直接运行
    sys.path.insert(0, str(REPO))

from experiments.bayesian_paired import bayesian_paired_analysis  # noqa: E402
from experiments.e8_statistical_analysis import paired_analysis  # noqa: E402

DEFAULT_ROOT = REPO / "experiments/results/e3_h1_payload"

ARM_PRIMARY = "p_df_parity__o_logic"  # ①
ARM_MONO = "p_df_parity__o_mono"  # ②
ARM_FULL = "p_full__o_logic"  # ③
REF_DETECTION_PCT = 75.6  # 预注册 §3.4 固定值（gold 口径 31/41）
REF_NOTE = "REF 工件已清除（sha256 d23402fb…），仅存记录值 31/41 = 75.6%"


def load_arm(root: Path, arm: str) -> dict[str, Any]:
    """取该臂最新一份批次 JSON（按 mtime）。"""
    batches = sorted((root / arm).glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
    if not batches:
        raise SystemExit(f"✗ 臂 {arm} 无批次 JSON：{root / arm}")
    return json.loads(batches[-1].read_text(encoding="utf-8"))


def detection_map(batch: dict[str, Any], baseline: str = "aitester") -> tuple[dict[str, bool], int]:
    """逐任务检出布尔 + 不可测（None）行数。

    ``detection_rate`` 为 0/1/None：None 表示超时或无 gold 材料，按 §3.1
    从配对分母剔除（**不得**记 0）。

    ``baseline``：①③是 aitester 臂；②是单体流水线，基线名为 ``plain_llm_df``
    （预注册 §2.1）。取不到指定基线时**报错**而不是静默返回空表——空表会把
    操纵检查算成 0% 检出（2026-10-31 首跑实测踩过）。
    """
    res = batch.get("results") or {}
    if baseline not in res:
        available = sorted(k for k in res if isinstance(res[k], dict))
        raise KeyError(f"臂内无基线 {baseline!r}（现有 {available}）")
    details = res[baseline].get("details") or []
    out: dict[str, bool] = {}
    none_rows = 0
    for row in details:
        value = row.get("detection_rate")
        if value is None:
            none_rows += 1
            continue
        out[row["task_id"]] = bool(value)
    return out, none_rows


def one_sided_mcnemar(b: int, c: int) -> float:
    """单侧精确 McNemar（H1 方向：δ > 0，即 ① 检出更多）。

    返回 P(X ≥ max(b, c)) under X ~ Binom(b + c, 0.5)；b == c 时返回 1.0。
    """
    n = b + c
    if n == 0 or b == c:
        return 1.0
    k = max(b, c)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2**n)
    return min(1.0, tail)


def bh_fdr(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg 校正（保序）。"""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [1.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        value = min(prev, p_values[idx] * m / rank)
        adjusted[idx] = value
        prev = value
    return adjusted


def verdict(delta_pp: float, p_bh: float, p_rope: float | None) -> str:
    """预注册 §3.2 判定表（不得改阈值）。"""
    if delta_pp >= 20.0 and p_bh < 0.05:
        return "H1 成立"
    if delta_pp <= 5.0 and p_rope is not None and p_rope >= 0.90:
        return "H1 否证"
    return "indeterminate"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    root = Path(args.root)

    arm_primary = load_arm(root, ARM_PRIMARY)
    arm_full = load_arm(root, ARM_FULL)

    det_primary, none_primary = detection_map(arm_primary)
    det_full, none_full = detection_map(arm_full)

    stats = paired_analysis(det_primary, det_full)
    # 单侧 McNemar：b = ①检出且③未检出，c = ③检出且①未检出（同 task 配对）
    common = sorted(set(det_primary) & set(det_full))
    b = sum(1 for t in common if det_primary[t] and not det_full[t])
    c = sum(1 for t in common if det_full[t] and not det_primary[t])
    p_one = one_sided_mcnemar(b, c)
    p_values = [p_one]
    p_bh = bh_fdr(p_values)[0]

    bayes = bayesian_paired_analysis(
        [{"task_id": t, "passed": det_primary[t]} for t in common],
        [{"task_id": t, "passed": det_full[t]} for t in common],
        field="passed",
        rope=0.05,
    )

    # §3.4 assay-sensitivity：② 与 REF 的差
    manipulation: dict[str, Any] = {"available": False, "reason": REF_NOTE}
    try:
        arm_mono = load_arm(root, ARM_MONO)
    except SystemExit:
        arm_mono = None
    if arm_mono is not None:
        det_mono, none_mono = detection_map(arm_mono, baseline="plain_llm_df")
        rate = 100.0 * sum(det_mono.values()) / max(1, len(det_mono))
        diff = rate - REF_DETECTION_PCT
        manipulation = {
            "available": True,
            "arm_detection_pct": round(rate, 2),
            "ref_detection_pct": REF_DETECTION_PCT,
            "diff_pp": round(diff, 2),
            "assay_sensitivity_established": abs(diff) <= 10.0,
            "none_rows": none_mono,
        }

    verdict_text = verdict(stats["delta_pp"], p_bh, bayes.get("p_rope"))
    downgraded = False
    if manipulation.get("available") and not manipulation["assay_sensitivity_established"]:
        downgraded = True
        verdict_text = "不可判定（assay sensitivity 未建立）"

    report = {
        "schema": "aitester_h1_payload_stats/1",
        "root": str(root),
        "arms": {"primary": ARM_PRIMARY, "mono": ARM_MONO, "full": ARM_FULL},
        "primary": {
            **stats,
            "b_primary_only": b,
            "c_full_only": c,
            "p_one_sided": round(p_one, 6),
            "p_bh": round(p_bh, 6),
            "n_pairs": len(common),
        },
        "bayes": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in bayes.items()},
        "excluded_none_rows": {"primary": none_primary, "full": none_full},
        "manipulation_check": manipulation,
        "verdict": verdict_text,
        "downgraded": downgraded,
        "disclosures": [
            "detection_rate=None 的行已从配对分母剔除（预注册 §3.1），不计 0",
            REF_NOTE,
            "structure 水平未跑（预注册 §2.7 预算保护），BH 校正实际只含 1 个对比",
            "spec_oracle_injected 在 H1 阶段尚不可得（C3 未打开，预注册 §3.3）",
        ],
    }

    out_json = Path(args.out) if args.out else root / "H1_STATISTICAL_REPORT.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# H1 载荷等价实验——统计报告",
        "",
        f"- 臂：①`{ARM_PRIMARY}` vs ③`{ARM_FULL}`；配对任务 **{len(common)}**",
        f"- 剔除的不可测行：①{none_primary} / ③{none_full}（None 不计 0）",
        f"- **δ = {stats['delta_pp']:+.2f}pp**，95% CI {stats['ci95_pp']}",
        f"- McNemar：单侧 p={p_one:.4f} / 双尾 p={stats['mcnemar_exact_p']:.4f}（b={b}, c={c}）；p_BH={p_bh:.4f}",
        f"- ROPE ±5pp：P(|δ|≤5pp)={bayes.get('p_rope')}；P(δ>20pp)={bayes.get('p_greater')}",
        f"- 操纵检查：{json.dumps(manipulation, ensure_ascii=False)}",
        f"- **判定：{verdict_text}**",
        "",
        "## 披露",
        "",
    ]
    lines += [f"- {item}" for item in report["disclosures"]]
    out_md = out_json.with_suffix(".md")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n报告 → {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
