#!/usr/bin/env python3
"""Z8（2026-10-06 审查落地）：配对比例检验的功效分析（实验设计前置工具）。

背景（审查 R06）：
    主批次 n=50、detection McNemar 不一致对仅 2/0——检验完全无分辨力。
    在规划下一轮实验（真实基准 / 生死实验）前，需要回答两个问题：
    ① 想以 80% 功效检出 10pp 的 detection 差异，需要多少任务？
    ② 维持当前 n=50，能以 80% 功效检出的最小差异是多少？
    本脚本用配对比例的正态近似给出闭式答案，避免"跑完实验才发现
    样本量注定不显著"的浪费。

公式（配对二值，Rosner《Fundamentals of Biostatistics》配对比例检验）：
    δ = p_a − p_b
    σ_d² = p_a + p_b − δ² − 2·p11      （p11 = 双方均为 1 的联合概率）
    n_required = (z_{1−α/2} + z_{power})² · σ_d² / δ²
    power(n, δ) = Φ(δ·√n/σ_d − z_{1−α/2}) + Φ(−δ·√n/σ_d − z_{1−α/2})

    p11 可由历史批次的不一致对结构估计：p11 ≈ min(p_a, p_b) − c，
    其中 c 为"A=1 且 B=0"型不一致率（A=系统，B=基线）。

用法：
    python3 scripts/tools/power_analysis.py                 # 默认：主批次口径速览
    python3 scripts/tools/power_analysis.py --n 100 --p-base 0.02 --p11 0.01
    python3 scripts/tools/power_analysis.py --self-check    # 往返一致性自检

零 LLM / 零网络 / 零子进程；纯 stdlib（statistics.NormalDist）。
"""

from __future__ import annotations

import argparse
import math
import sys
from statistics import NormalDist

# 标准正态分布句柄（NormalDist() 即 N(0,1)）
_NORM = NormalDist()


def _var_paired_diff(p_a: float, p_b: float, p11: float) -> float:
    """配对差 δ = p_a − p_b 的单任务方差 σ_d²（见模块 docstring 公式）。"""
    delta = p_a - p_b
    return p_a + p_b - delta * delta - 2.0 * p11


def _validate_p11(p_a: float, p_b: float, p11: float) -> None:
    """p11 合法性（联合概率必须落在 Fréchet 界内：max(0, p_a+p_b−1) ≤ p11 ≤ min(p_a,p_b)）。"""
    lower = max(0.0, p_a + p_b - 1.0)
    upper = min(p_a, p_b)
    if not (lower - 1e-12 <= p11 <= upper + 1e-12):
        raise ValueError(
            f"p11={p11} 超出联合概率合法区间 [{lower:.4f}, {upper:.4f}]"
            f"（p_a={p_a}, p_b={p_b}）——请从历史批次不一致对结构重新估计"
        )


def power_paired(
    n: int,
    p_a: float,
    p_b: float,
    p11: float,
    alpha: float = 0.05,
) -> float:
    """给定样本量 n 与真实 (p_a, p_b, p11)，双侧水平 α 下的检验功效。"""
    _validate_p11(p_a, p_b, p11)
    delta = p_a - p_b
    var = _var_paired_diff(p_a, p_b, p11)
    if n <= 0 or var <= 0 or delta == 0:
        return alpha  # 无差异时"功效"退化为弃真率水平（仅当 δ>0 才有意义）
    z_crit = _NORM.inv_cdf(1.0 - alpha / 2.0)
    z_effect = delta * math.sqrt(n) / math.sqrt(var)
    return _NORM.cdf(z_effect - z_crit) + _NORM.cdf(-z_effect - z_crit)


def required_n_paired(
    p_a: float,
    p_b: float,
    p11: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """以指定功效检出 δ = p_a − p_b 所需的配对任务数（正态近似，向上取整）。"""
    _validate_p11(p_a, p_b, p11)
    delta = p_a - p_b
    if abs(delta) < 1e-12:
        raise ValueError("p_a == p_b（δ=0）：任何样本量都无法检出零差异")
    var = _var_paired_diff(p_a, p_b, p11)
    if var <= 0:
        raise ValueError("σ_d² ≤ 0：给定 (p_a, p_b, p11) 组合退化，请检查 p11 估计")
    z_crit = _NORM.inv_cdf(1.0 - alpha / 2.0)
    z_power = _NORM.inv_cdf(power)
    n0 = math.ceil((z_crit + z_power) ** 2 * var / (delta * delta))
    # 闭式 n 忽略双侧功效公式的第二项 Φ(−z−z_c)（微小但非零），可能使
    # 实际功效略低于目标——自增直到达标，保证 required_n 的"达到目标
    # 功效"承诺（与 detectable_delta_paired 的往返一致性由测试锁定）
    for _ in range(10000):
        if power_paired(n0, p_a, p_b, p11, alpha) >= power:
            break
        n0 += 1
    return n0


def detectable_delta_paired(
    n: int,
    p_b: float,
    p11: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """样本量 n 下以指定功效可检出的最小 δ（二分求解）。

    注意 σ_d² 依赖 p_a = p_b + δ（δ 越大方差越大），故无闭式解；二分
    区间上界取 p11 的 Fréchet 可行域内最大 δ（p_a + p_b − 1 ≤ p11 要求
    δ ≤ 1 − 2·p_b + p11——在 δ = 1 − p_b 极端点 p11 被"挤"成 p_b，评估
    退化无意义），若上端功效仍不足则返回 float('nan')。
    """
    # δ→0 处 p11 可行性（p11 ≤ min(p_a,p_b)=p_b）
    _validate_p11(p_b, p_b, p11)
    lo = 1e-9
    hi = min(1.0 - p_b, 1.0 - 2.0 * p_b + p11)
    if hi <= lo:
        raise ValueError(f"p11={p11} 在 p_b={p_b} 下无可行 δ 区间（p11 过小）——请从历史批次不一致对结构重新估计 p11")
    # 上端功效仍不足：该 n 连可行域内最大差异都检不出（样本量极小）
    if power_paired(n, p_b + hi, p_b, p11, alpha) < power:
        return float("nan")
    for _ in range(200):  # 二分至机器精度量级
        mid = (lo + hi) / 2.0
        if power_paired(n, p_b + mid, p_b, p11, alpha) >= power:
            hi = mid
        else:
            lo = mid
    return hi


def _self_check() -> int:
    """往返一致性自检：required_n 反解回 detectable_delta 应≈原 δ。"""
    cases = [
        # (p_a, p_b, p11)——覆盖低基线（detection 2% 量级）与中等基线
        (0.12, 0.02, 0.01),
        (0.22, 0.02, 0.01),
        (0.32, 0.02, 0.015),
        (0.75, 0.52, 0.45),
        (0.90, 0.50, 0.48),
    ]
    for p_a, p_b, p11 in cases:
        n = required_n_paired(p_a, p_b, p11)
        delta_back = detectable_delta_paired(n, p_b, p11)
        recovered = p_b + delta_back
        # detectable_delta 返回的是"恰好达到目标功效"的 δ，应 ≤ 原 δ
        # 且相差不超过一个样本步进对应的 δ 变化（容差 15%）
        if not (p_b < recovered <= p_a * 1.15 + 1e-9):
            print(
                f"自检失败：δ={p_a - p_b:.4f} 需要 n={n}，"
                f"但 n 反解可检出 δ={delta_back:.4f}（复原 p_a={recovered:.4f}）"
            )
            return 1
        print(f"自检通过：δ={p_a - p_b:.2f} → n={n} → 反解 δ={delta_back:.4f} ≤ 原 δ ✓")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="配对比例检验（McNemar 口径）的功效分析（纯离线，纯 stdlib）")
    parser.add_argument("--n", type=int, default=50, help="现有/规划的任务数（默认 50，主批次口径）")
    parser.add_argument("--p-base", type=float, default=0.02, help="基线比例 p_b（默认 0.02，主批次 detection 量级）")
    parser.add_argument(
        "--p11",
        type=float,
        default=0.01,
        help="双方均为 1 的联合概率（默认 0.01，低基线场景的保守估计）",
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="双侧检验水平（默认 0.05）")
    parser.add_argument("--power", type=float, default=0.8, help="目标功效（默认 0.8）")
    parser.add_argument("--self-check", action="store_true", help="运行往返一致性自检（CI 可选）")
    args = parser.parse_args()

    if args.self_check:
        return _self_check()

    print("=" * 70)
    print("配对比例功效分析（Z8：实验设计前置——先算样本量，再跑实验）")
    print("=" * 70)
    print(
        f"口径：n={args.n}，基线 p_b={args.p_base:.2%}，p11={args.p11:.2%}，"
        f"α={args.alpha}（双侧），目标功效={args.power:.0%}"
    )
    print()

    # ① 当前 n 可检出的最小差异
    delta_min = detectable_delta_paired(args.n, args.p_base, args.p11, args.alpha, args.power)
    if math.isnan(delta_min):
        print(f"① n={args.n} 下连 δ=1−p_b 的极端差异都无法以 {args.power:.0%} 功效检出——样本量过小")
    else:
        print(
            f"① n={args.n} 可检出的最小差异：δ ≈ {delta_min:.2%}"
            f"（即系统需达 p_a ≈ {args.p_base + delta_min:.2%} 才能被判定显著）"
        )

    # ② 常见目标差异所需的样本量
    print(f"② 以 {args.power:.0%} 功效检出各目标差异所需任务数：")
    print("   目标 δ    所需 n（配对）   对应 p_a")
    for delta_target in (0.05, 0.10, 0.20, 0.30):
        p_a = args.p_base + delta_target
        if p_a > 1.0:
            continue
        try:
            n_req = required_n_paired(p_a, args.p_base, args.p11, args.alpha, args.power)
            print(f"   {delta_target:>6.0%}     {n_req:>8d}        {p_a:.0%}")
        except ValueError as exc:
            print(f"   {delta_target:>6.0%}     不适用（{exc}）")

    print()
    print("提示：p11 请用历史批次列联表估计（min(p_a,p_b) − c，c = A=1且B=0 型")
    print("不一致率）；p11 越大（两系统结果越同向）所需样本量越大。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
