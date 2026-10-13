"""STVR 实证研究批次：统计效应量 + 置信区间纯函数模块（零 LLM 成本）。

背景：
    STVR（Software: Testing, Verification & Reliability）投稿导向的实证
    研究设计要求**不只报均值**——每项对比指标必须带**效应量 + 95% CI**
    （`docs/design/stvr_empirical_study_design.md` §3.3）。本模块提供
    三个核心效应量度量 + 一个配对 CI 工具，全部为**纯函数**（不触碰
    外部数据源 / 不发网络 / 不耗 LLM 配额），供 `experiments/
    stvr_ablation_study.py` 实跑批次的分析侧消费：

    - `cliffs_delta(a, b)`：非参数效应量（Robinson 1992；Tomczak &
      Dutton 2014 推荐），对二值 / 有序指标（detection_rate /
      repair_rate）最稳健，STVR 审稿人最常要求；
    - `cohens_d(a, b)`：参数化效应量（两组独立样本差 / 合并标准差），
      对连续指标（mutation_score / token / elapsed）适用；
    - `hedges_g(a, b)`：Cohen's d 的小样本校正（g = d * J(n1, n2)），
      样本量 < 30 时比 Cohen's d 更保守（STVR 场景 n 常偏小）；
    - `paired_bootstrap_ci(a, b, n_boot=1000, seed=42)`：配对 bootstrap
      95% CI（对均值差 / 比例差 / Cliff's delta 等均可用，STVR 规范）。

设计约束（与 STVR 实证研究设计 §3.3 锁死）：
    - 样本长度必须一致（配对设计）——`cliffs_delta` / `cohens_d` /
      `hedges_g` 均假设 a、b 同长度（任务级配对）；
    - 长度不一致 / 空样本 / 常数序列（方差 = 0）→ 保守返回
      `None`（与 `_m1_metrics` 的 None 保守口径一致），**不**静默
      回退到非配对口径（审稿人可归因性要求）；
    - `paired_bootstrap_ci` 默认 `n_boot=1000` + `seed=42`（跨运行
      可复现），`n_boot` 非法值回退 1000；
    - 所有函数纯函数，零 LLM 成本，可被单测锁定。
"""

from __future__ import annotations

import random
import statistics
from typing import Any


def _as_list(x: Any) -> list[float] | None:
    """把输入转成 float 列表；None / 空 / 非数值 → None（保守口径）。"""
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        try:
            return [float(v) for v in x]
        except (TypeError, ValueError):
            return None
    return None


def cliffs_delta(a: list[float] | tuple[float, ...] | None,
                 b: list[float] | tuple[float, ...] | None) -> float | None:
    """计算 Cliff's delta（非参数效应量，Robinson 1992 / Tomczak & Dutton 2014）。

    定义（配对 / 独立样本通用）：
        δ = [P(a > b) − P(a < b)]

    其中 P 为所有 (a_i, b_j) 对中的比例。|δ| 的解释：
        < 0.148 小 / 0.148–0.27 中等 / 0.27–0.33 大（Tomczak & Dutton 2014）。

    Args:
        a: 组 1 的观测值列表（如 RAG-on 臂的 detection_rate 数组）。
        b: 组 2 的观测值列表（如 RAG-off 臂的 detection_rate 数组）。

    Returns:
        - a / b 为 None / 空 / 长度不一致 → None（保守口径）；
        - 否则 → δ ∈ [−1.0, 1.0]（保留 4 位小数）。
    """
    la, lb = _as_list(a), _as_list(b)
    if not la or not lb or len(la) != len(lb):
        return None
    if not la:  # 已判空，此处为 mypy 友好
        return None
    gt, lt = 0, 0
    n = len(la) * len(lb)
    for x in la:
        for y in lb:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    return round((gt - lt) / n, 4)


def cohens_d(a: list[float] | tuple[float, ...] | None,
             b: list[float] | tuple[float, ...] | None) -> float | None:
    """计算 Cohen's d（参数化效应量，两组独立样本）。

    定义：
        d = (mean_a − mean_b) / s_pooled
        s_pooled = sqrt(((n_a−1)*var_a + (n_b−1)*var_b) / (n_a+n_b−2))

    Args:
        a: 组 1 的观测值列表。
        b: 组 2 的观测值列表。

    Returns:
        - a / b 为 None / 空 / 任一组样本量 < 2（方差不可算）→ None；
        - 合并标准差 = 0（两组均常数）→ None（保守口径，不除零）；
        - 否则 → d（保留 4 位小数；正 = 组 1 更大）。
    """
    la, lb = _as_list(a), _as_list(b)
    if not la or not lb or len(la) < 2 or len(lb) < 2:
        return None
    na, nb = len(la), len(lb)
    var_a, var_b = statistics.variance(la), statistics.variance(lb)
    pooled = ((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2)
    if pooled <= 0:
        return None  # 两组均常数 → 合并标准差 0，不除零
    return round((statistics.mean(la) - statistics.mean(lb)) / (pooled ** 0.5), 4)


def hedges_g(a: list[float] | tuple[float, ...] | None,
             b: list[float] | tuple[float, ...] | None) -> float | None:
    """计算 Hedges' g（Cohen's d 的小样本校正，n < 30 时更保守）。

    定义：
        g = d * J(n_a, n_b)
        J(n1, n2) = 1 − 3 / (4*(n1+n2) − 9)  （Hedges & Olkin 1985）

    J < 1 恒成立（n1+n2 > 3 时），故 g < d——Hedges' g 是**保守校正**
    （小样本下 Cohen's d 常高估真实效应量，J 因子将其缩减）。n 越大，
    J 越接近 1（g ≈ d）；n 越小，J 越小（g 越低于 d，校正越强）。

    Args:
        a / b: 同 `cohens_d`。

    Returns:
        - 同 `cohens_d` 的 None 条件；
        - 否则 → g（保留 4 位小数；正 = 组 1 更大；g ≤ d 恒成立）。
    """
    d = cohens_d(a, b)
    if d is None:
        return None
    la, lb = _as_list(a), _as_list(b)
    assert la is not None and lb is not None
    n1, n2 = len(la), len(lb)
    denom = 4 * (n1 + n2) - 9
    if denom <= 0:
        return None  # 极端小样本（n1+n2 < 3），保守 None
    j = 1.0 - 3.0 / denom
    return round(d * j, 4)


def paired_bootstrap_ci(
    a: list[float] | tuple[float, ...] | None,
    b: list[float] | tuple[float, ...] | None,
    stat_fn: str = "mean_diff",
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float] | None:
    """配对 bootstrap 95% CI（STVR 实证研究设计 §3.3 规范）。

    对配对观测 (a_i, b_i) 做 bootstrap 重采样（按 i 同时重采样 a_i / b_i，
    保留配对结构），计算 stat_fn 的分布，取 2.5 / 97.5 分位数。

    Args:
        a / b: 同长度配对观测列表（长度不一致 / 空 → None）。
        stat_fn: 统计量名（"mean_diff" / "proportion_diff" / "cliffs_delta"）：
            - mean_diff: mean(a) − mean(b)（连续指标，如 mutation_score）；
            - proportion_diff: 比例差（二值指标，如 detection_rate 0/1）；
            - cliffs_delta: 配对版 Cliff's delta（有序 / 二值指标）。
        n_boot: bootstrap 重采样次数（默认 1000；非法值回退 1000）。
        seed: 随机种子（默认 42，跨运行可复现）。

    Returns:
        - a / b 长度不一致 / 空 → None；
        - 否则 → (lo, hi) 95% CI（保留 4 位小数；lo ≤ hi）。
    """
    la, lb = _as_list(a), _as_list(b)
    if not la or not lb or len(la) != len(lb):
        return None
    if n_boot < 1:
        n_boot = 1000
    n = len(la)
    rng = random.Random(seed)
    if stat_fn == "mean_diff":
        def _stat(s: list[float], t: list[float]) -> float:
            return statistics.mean(s) - statistics.mean(t)
    elif stat_fn == "proportion_diff":
        def _stat(s: list[float], t: list[float]) -> float:
            return (sum(1 for x in s if x >= 0.5) / len(s)) - (sum(1 for x in t if x >= 0.5) / len(t))
    elif stat_fn == "cliffs_delta":
        def _stat(s: list[float], t: list[float]) -> float:
            d = cliffs_delta(s, t)
            return d if d is not None else 0.0
    else:
        return None  # 未知统计量 → 保守 None

    ests: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        sa = [la[i] for i in idx]
        sb = [lb[i] for i in idx]
        ests.append(_stat(sa, sb))
    ests.sort()
    lo = ests[int(0.025 * n_boot)]
    hi = ests[int(0.975 * n_boot)]
    if lo > hi:  # 极端分布（全同值）下 int 截断可能 lo>hi，钳制
        lo, hi = hi, lo
    return (round(lo, 4), round(hi, 4))


def effect_size_summary(
    a: list[float] | tuple[float, ...] | None,
    b: list[float] | tuple[float, ...] | None,
) -> dict[str, Any] | None:
    """一站式效应量汇总（STVR 审稿人要求：不只报均值，报效应量 + CI）。

    返回键集合同构 dict（a / b 长度不一致 / 空 → 返回 None；否则各字段
    独立计算，缺失项为 None，**不**因单项不可算而整 dict 为 None）：

        - "cliffs_delta": float | None
        - "cohens_d": float | None
        - "hedges_g": float | None
        - "ci95_mean_diff": [lo, hi] | None（bootstrap 1000 次，seed=42）
        - "n_a": int, "n_b": int（样本量，审稿人常追问）
        - "note": str（口径说明，如"配对设计，bootstrap CI"）

    用途：`experiments/stvr_ablation_study.py` 实跑批次的分析侧，对每对
    消融臂（如 both_on vs both_off）调用本函数，把结果写进论文
    Results 章节（STVR §5 写作结构 §5 锁死）。
    """
    la, lb = _as_list(a), _as_list(b)
    if not la or not lb or len(la) != len(lb):
        return None
    return {
        "cliffs_delta": cliffs_delta(la, lb),
        "cohens_d": cohens_d(la, lb),
        "hedges_g": hedges_g(la, lb),
        "ci95_mean_diff": list(paired_bootstrap_ci(la, lb, "mean_diff")) if paired_bootstrap_ci(la, lb, "mean_diff") else None,
        "n_a": len(la),
        "n_b": len(lb),
        "note": "paired design; bootstrap 95% CI (n_boot=1000, seed=42)",
    }
