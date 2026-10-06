"""Z9（2026-10-06 审查落地）：配对二值指标的贝叶斯分析（Dirichlet 后验）。

背景（审查 R06；方法学依据 Furia/Feldt/Torkar, TSE 2019, arXiv:1811.05422
对 SE 实验中 NHST 的批评——p 值在 n=50、McNemar 不一致对仅 2/0 的样本量下
无分辨力，"p=0.4795 不显著"无法区分"真无差异"与"功效不足"）：

    配对二值结果 (a_i, b_i) 构成 2×2 列联表（沿用 mcnemar_test 口径：
    n01 = A=1 且 B=0，n10 = A=0 且 B=1）。单元格概率
    θ = (θ11, θ01, θ10, θ00) ~ Dirichlet(n11+1, n01+1, n10+1, n00+1)
    （均匀先验，无信息口径），边际差 δ = p_A − p_B = θ01 − θ10。

    - 后验均值/标准差有精确闭式（Dirichlet 线性组合矩公式）；
    - 95% 可信区间与 P(δ>0) / P(|δ| ≤ ROPE) 由固定 seed 的 Monte Carlo
      估计（random.Random.gammavariate 抽 Gamma 归一化得 Dirichlet），
      纯 stdlib、逐位可复现（与 bootstrap_paired_diff_ci 的 seed=42
      口径一致）。

与 NHST 的关系：并列呈现、不替换——run_all_statistics 的历史
McNemar / t 检验表保持不变，本模块只新增"贝叶斯配对分析"章节。

配对口径：与 statistical_analysis._pair_by_task 完全同语义
（task_id 首见去重〔调用方保证最新批次在前〕、field 值 None 跳过、
真值 → 1 / 假值 → 0），由 tests/test_z_batch.py 的等价性用例锁定，
不依赖 import（避免 statistical_analysis ↔ 本模块循环依赖）。

零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 与 bootstrap CI 同口径的默认 seed / 抽样规模（报告可复现声明依赖二者）
_BAYES_SEED = 42
_BAYES_N_DRAWS = 20000
# ROPE（Region of Practical Equivalence，实际等价区间）默认半宽：
# |δ| ≤ 5pp 视为"实践中无差异"（detection 类指标 10-20pp 才是感兴趣的
# 效应量，5pp 显著小于该量级；引用口径见模块 docstring）
_DEFAULT_ROPE = 0.05


def paired_contingency(
    results_a: list[dict],
    results_b: list[dict],
    field: str = "passed",
) -> dict[str, int]:
    """按 task_id 配对并统计 2×2 列联表计数。

    语义与 statistical_analysis._pair_by_task 一致（首见去重 / None 跳过 /
    真值→1）；返回 {"n_common", "n11", "n01", "n10", "n00"}
    （n01 = A=1 且 B=0，n10 = A=0 且 B=1，与 mcnemar_test 的命名对齐）。
    """

    def _dedup(rows: list[dict]) -> dict[str, int]:
        seen: dict[str, int] = {}
        for r in rows:
            tid = r.get("task_id")
            if not tid or tid in seen:
                continue
            val = r.get(field)
            if val is None:
                continue
            seen[tid] = 1 if val else 0
        return seen

    map_a = _dedup(results_a)
    map_b = _dedup(results_b)
    common = sorted(set(map_a) & set(map_b))
    counts = {"n_common": len(common), "n11": 0, "n01": 0, "n10": 0, "n00": 0}
    for t in common:
        a, b = map_a[t], map_b[t]
        if a == 1 and b == 1:
            counts["n11"] += 1
        elif a == 1 and b == 0:
            counts["n01"] += 1
        elif a == 0 and b == 1:
            counts["n10"] += 1
        else:
            counts["n00"] += 1
    return counts


def _percentile_linear(sorted_values: list[float], p: float) -> float:
    """线性插值百分位（与 numpy 默认 'linear' 方法同口径）。"""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = p * (len(sorted_values) - 1)
    lo = math.floor(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def bayesian_paired_analysis(
    results_a: list[dict],
    results_b: list[dict],
    field: str = "passed",
    rope: float = _DEFAULT_ROPE,
    n_draws: int = _BAYES_N_DRAWS,
    seed: int = _BAYES_SEED,
) -> dict[str, Any]:
    """配对二值指标的 Dirichlet 后验分析。

    Args:
        results_a / results_b: 两个基线的结果行列表（task_id + 二值 field）。
        field: 二值字段（"passed" / "detection_rate" / "repair_rate"），
            None 值任务跳过（与 _pair_by_task 同口径）。
        rope: 实际等价区间半宽（|δ| ≤ rope 记入 p_rope）。
        n_draws: Monte Carlo 抽样次数（<=0 时仅返回闭式矩，CI/尾部概率为 None）。
        seed: Monte Carlo 随机种子（默认与 bootstrap CI 同为 42）。

    Returns:
        {n_common, n11, n01, n10, n00, post_mean, post_sd, ci_low, ci_high,
         p_greater, p_less, p_rope, rope, note}
        —— n_common < 2 时全统计量为 None（样本不足，与 mcnemar_test
        的保守口径一致），note 说明原因。
    """
    counts = paired_contingency(results_a, results_b, field=field)
    n_common = counts["n_common"]
    base: dict[str, Any] = {**counts, "rope": rope, "note": ""}
    if n_common < 2:
        base.update(
            {
                "post_mean": None,
                "post_sd": None,
                "ci_low": None,
                "ci_high": None,
                "p_greater": None,
                "p_less": None,
                "p_rope": None,
            }
        )
        base["note"] = f"共同任务数 {n_common} < 2，样本不足（与 mcnemar_test 同口径）"
        return base

    # Dirichlet 后验参数（均匀先验 α=1）：单元格顺序 (11, 01, 10, 00)
    alpha = (
        counts["n11"] + 1,
        counts["n01"] + 1,
        counts["n10"] + 1,
        counts["n00"] + 1,
    )
    alpha0 = sum(alpha)
    # δ = θ01 − θ10 的精确后验矩（Dirichlet 线性组合）：
    # E[aᵀθ] = aᵀα/α0；Var(aᵀθ) = (α0·Σaᵢ²αᵢ − (aᵀα)²) / (α0²·(α0+1))
    a_dot_alpha = alpha[1] - alpha[2]
    sum_sq = alpha[1] + alpha[2]
    post_mean = a_dot_alpha / alpha0
    post_var = (alpha0 * sum_sq - a_dot_alpha**2) / (alpha0**2 * (alpha0 + 1))
    post_sd = math.sqrt(post_var)
    base.update({"post_mean": post_mean, "post_sd": post_sd})

    if n_draws <= 0:
        base.update({"ci_low": None, "ci_high": None, "p_greater": None, "p_less": None, "p_rope": None})
        base["note"] = "n_draws<=0：仅闭式矩（CI / 尾部概率未估计）"
        return base

    # Monte Carlo：Gamma(shape=α_i, scale=1) 归一化即 Dirichlet 样本；
    # δ = (g01 − g10) / Σg（分母约去，只需两个分子的 Gamma 变量与总和）。
    # 随机源为 random.Random(seed)——刻意非加密（与 bootstrap_paired_diff_ci
    # 同口径）：统计推断用途，可复现性（固定 seed）优先于不可预测性。
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(n_draws):
        g11 = rng.gammavariate(alpha[0], 1.0)
        g01 = rng.gammavariate(alpha[1], 1.0)
        g10 = rng.gammavariate(alpha[2], 1.0)
        g00 = rng.gammavariate(alpha[3], 1.0)
        total = g11 + g01 + g10 + g00
        deltas.append((g01 - g10) / total)
    deltas.sort()
    ci_low = _percentile_linear(deltas, 0.025)
    ci_high = _percentile_linear(deltas, 0.975)
    p_greater = sum(1 for d in deltas if d > 0) / len(deltas)
    p_less = sum(1 for d in deltas if d < 0) / len(deltas)
    p_rope = sum(1 for d in deltas if abs(d) <= rope) / len(deltas)
    base.update(
        {
            "ci_low": ci_low,
            "ci_high": ci_high,
            "p_greater": p_greater,
            "p_less": p_less,
            "p_rope": p_rope,
        }
    )
    return base


def interpret_bayes(result: dict[str, Any], rope: float | None = None) -> str:
    """贝叶斯结果的粗粒度结论标签（与 interpret_p 的 n.s./*** 风格并列）。

    - P(δ>0) ≥ 0.975 且 ROPE 外  → "bayes_pos"（方向稳健为正）
    - P(δ<0) ≥ 0.975 且 ROPE 外  → "bayes_neg"
    - P(ROPE) ≥ 0.95              → "bayes_equiv"（实践等价）
    - 其余                         → "bayes_inconclusive"（证据不足——
      恰是 n=50 主批次最常见结局，诚实标注而非强行二分）
    """
    p_greater = result.get("p_greater")
    if p_greater is None:
        return "n/a"
    _rope = rope if rope is not None else float(result.get("rope", _DEFAULT_ROPE))
    p_rope = result.get("p_rope")
    p_less = result.get("p_less", 1.0 - p_greater)
    if p_rope is not None and p_rope >= 0.95:
        return "bayes_equiv"
    if p_greater >= 0.975:
        return "bayes_pos"
    if p_less >= 0.975:
        return "bayes_neg"
    return "bayes_inconclusive"
