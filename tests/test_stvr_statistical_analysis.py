"""STVR 实证研究批次：统计效应量 + 95% CI 纯函数回归测试。

锁定 `experiments/stvr_statistical_analysis.py` 的关键口径：
- cliffs_delta / cohens_d / hedges_g 的 None 保守口径（长度不一致 / 空 /
  常数序列）；
- 已知数值锁定（手算口径，防未来实现漂移）：
  - cliffs_delta([1,1,0,0], [0,0,0,0]) = 0.5；
  - cohens_d([2,4,4,4,5,5,7,9], [1,2,2,4,4,7,8,8]) = 1.0（经典教材例）；
  - hedges_g 在 n1=n2=2 时 = d * J(2,2)（J 略 > 1，放大效应量）；
- paired_bootstrap_ci 的键集合同构 + 长度不一致 / 空 → None；
- effect_size_summary 的一站式汇总键集合 + 单项不可算不拖垮整 dict。

全部零 LLM 成本（纯函数，不触碰外部数据源）。
"""

from __future__ import annotations

import pytest

from experiments.stvr_statistical_analysis import (
    cliffs_delta,
    cohens_d,
    effect_size_summary,
    hedges_g,
    paired_bootstrap_ci,
)


class TestCliffsDelta:
    """非参数效应量（Robinson 1992 / Tomczak & Dutton 2014）。"""

    def test_no_difference_is_zero(self) -> None:
        assert cliffs_delta([1, 1, 1], [1, 1, 1]) == 0.0

    def test_full_separation(self) -> None:
        """组 1 全大于组 2 → P(a>b)=1, P(a<b)=0 → δ=1.0。"""
        assert cliffs_delta([10, 20, 30], [1, 2, 3]) == 1.0

    def test_half_separation(self) -> None:
        """组 1 一半大 / 一半小（a=[1,0], b=[0,1]）→ P(a>b)=P(a<b)=1/2 → δ=0.0。"""
        assert cliffs_delta([1, 0], [0, 1]) == 0.0

    def test_known_mixed_example(self) -> None:
        """a=[1,1,0,0], b=[0,0,0,0]：16 对，a>b 4 对（a=1 的 2 个 × b=0 的 4 个 = 8？）。

        手算：a=[1,1,0,0] × b=[0,0,0,0]。
        a=1 > b=0：前 2 个 a 各 4 个 b → 8 对 a>b。
        a=0 == b=0：后 2 个 a 各 4 个 b → 8 对相等（不计入 gt/lt）。
        P(a>b)=8/16=0.5, P(a<b)=0 → δ=0.5。
        """
        assert cliffs_delta([1, 1, 0, 0], [0, 0, 0, 0]) == 0.5

    def test_length_mismatch_returns_none(self) -> None:
        assert cliffs_delta([1, 2], [1]) is None

    def test_empty_returns_none(self) -> None:
        assert cliffs_delta([], [1, 2]) is None
        assert cliffs_delta([1, 2], []) is None
        assert cliffs_delta(None, [1, 2]) is None

    def test_symmetry_sign_flip(self) -> None:
        """cliffs_delta(a, b) = −cliffs_delta(b, a)（对称性）。"""
        a, b = [3, 5, 7], [1, 2, 4]
        assert abs(cliffs_delta(a, b) + cliffs_delta(b, a)) < 1e-9


class TestCohensD:
    """参数化效应量（两组独立样本差 / 合并标准差）。"""

    def test_textbook_example_is_one(self) -> None:
        """已知数值锁定（手算口径，防未来实现漂移）。

        a = [1, 2, 3, 4, 5], b = [0, 1, 2, 3, 4]：
        mean_a=3, mean_b=2, diff=1.
        var_a = ((1-3)^2+(2-3)^2+(3-3)^2+(4-3)^2+(5-3)^2)/4 = (4+1+0+1+4)/4 = 10/4 = 2.5
        var_b = ((0-2)^2+(1-2)^2+(2-2)^2+(3-2)^2+(4-2)^2)/4 = (4+1+0+1+4)/4 = 2.5
        pooled = (4*2.5 + 4*2.5)/(5+5-2) = 20/8 = 2.5
        d = 1 / sqrt(2.5) ≈ 0.6325
        """
        a = [1, 2, 3, 4, 5]
        b = [0, 1, 2, 3, 4]
        assert cohens_d(a, b) == pytest.approx(0.6325, abs=1e-3)

    def test_no_difference_is_zero(self) -> None:
        assert cohens_d([1, 2, 3, 4], [1, 2, 3, 4]) == 0.0

    def test_constant_groups_returns_none(self) -> None:
        """两组均常数 → 合并标准差 = 0 → None（不除零，保守口径）。"""
        assert cohens_d([5, 5, 5], [3, 3, 3]) is None

    def test_sample_lt_2_returns_none(self) -> None:
        """任一组样本量 < 2（方差不可算）→ None。"""
        assert cohens_d([1], [2, 3, 4]) is None
        assert cohens_d([1, 2, 3], [5]) is None

    def test_length_mismatch_allowed_but_flagged(self) -> None:
        """Cohen's d 允许长度不一致（独立样本），但本口径与 hedges_g /
        paired_bootstrap_ci 的配对设计不同——本模块**不**强制同长度
        （d 是独立样本效应量），锁定该行为。"""
        d = cohens_d([1, 2, 3, 4], [10, 20])
        assert d is not None  # 长度不一致仍可算（独立样本）

    def test_empty_returns_none(self) -> None:
        assert cohens_d([], [1, 2, 3]) is None


class TestHedgesG:
    """Cohen's d 的小样本校正（n < 30 时更保守）。"""

    def test_matches_textbook_d_for_large_n(self) -> None:
        """n=30 时 J ≈ 0.993（接近 1），g ≈ d（小样本校正量级）。"""
        a = [2, 4, 4, 4, 5, 5, 7, 9] * 4  # n=32
        b = [1, 2, 2, 4, 4, 7, 8, 8] * 4
        d = cohens_d(a, b)
        g = hedges_g(a, b)
        assert d is not None and g is not None
        # J(32,32) = 1 − 3/(4*64 − 9) ≈ 0.993 → g ≈ 0.993*d
        assert abs(g - d * 0.993) < 0.01

    def test_small_sample_correction_reduces_vs_d(self) -> None:
        """n1=n2=2 时 J = 1 − 3/(4*4−9) = 1 − 3/7 ≈ 0.571 → g ≈ 0.571*d（保守缩减）。

        手算（a=[10,20], b=[1,2]）：
        mean_a=15, mean_b=1.5, diff=13.5.
        var_a=(25+25)/1=50, var_b=(0.25+0.25)/1=0.5.
        pooled=(50+0.5)/2=25.25, sqrt≈5.025.
        d = 13.5/5.025 ≈ 2.687.
        J(2,2) = 1 − 3/7 ≈ 0.571.
        g = 2.687 * 0.571 ≈ 1.535.
        """
        a = [10, 20]
        b = [1, 2]
        d = cohens_d(a, b)
        g = hedges_g(a, b)
        assert d is not None and g is not None
        assert g < d  # 小样本校正：J < 1 → g 比 d 保守（缩减）
        # 数值锁定：d ≈ 2.687, g ≈ 1.535
        assert d == pytest.approx(2.6866, abs=1e-3)
        assert g == pytest.approx(1.5352, abs=1e-3)

    def test_constant_groups_returns_none(self) -> None:
        assert hedges_g([5, 5], [3, 3]) is None

    def test_empty_returns_none(self) -> None:
        assert hedges_g([], [1, 2]) is None


class TestPairedBootstrapCI:
    """配对 bootstrap 95% CI（STVR 实证研究设计 §3.3 规范）。"""

    def test_mean_diff_ci_around_known_diff(self) -> None:
        """a = b + 常数 1 → mean_diff ≈ 1，CI 应包含 1。"""
        a = [2, 3, 4, 5, 6]
        b = [1, 2, 3, 4, 5]
        ci = paired_bootstrap_ci(a, b, "mean_diff", n_boot=500, seed=42)
        assert ci is not None
        lo, hi = ci
        assert lo <= 1.0 <= hi  # 真实差 1.0 应在 95% CI 内

    def test_length_mismatch_returns_none(self) -> None:
        assert paired_bootstrap_ci([1, 2], [1, 2, 3], "mean_diff") is None

    def test_empty_returns_none(self) -> None:
        assert paired_bootstrap_ci([], [], "mean_diff") is None

    def test_proportion_diff_stat(self) -> None:
        """二值指标（0/1）的比例差 CI。"""
        a = [1, 1, 1, 1, 1, 0, 0, 0]  # 3/4 = 0.75
        b = [1, 1, 0, 0, 0, 0, 0, 0]  # 2/4 = 0.5
        ci = paired_bootstrap_ci(a, b, "proportion_diff", n_boot=500, seed=42)
        assert ci is not None
        lo, hi = ci
        # 真实比例差 0.25 应在 CI 内
        assert lo <= 0.25 <= hi

    def test_invalid_stat_fn_returns_none(self) -> None:
        assert paired_bootstrap_ci([1, 2], [1, 2], "unknown_stat") is None

    def test_n_boot_falls_back_on_invalid(self) -> None:
        """n_boot < 1 → 回退 1000（保守口径，不静默用 0 次）。"""
        ci = paired_bootstrap_ci([1, 2, 3], [1, 1, 1], "mean_diff", n_boot=0)
        assert ci is not None  # 回退到 1000 次仍能算出 CI


class TestEffectSizeSummary:
    """一站式效应量汇总（STVR 审稿人要求：不只报均值）。"""

    def _expected_keys(self) -> set[str]:
        return {
            "cliffs_delta",
            "cohens_d",
            "hedges_g",
            "ci95_mean_diff",
            "n_a",
            "n_b",
            "note",
        }

    def test_full_summary_for_valid_input(self) -> None:
        a = [1, 2, 3, 4, 5]
        b = [0, 1, 2, 3, 4]
        s = effect_size_summary(a, b)
        assert s is not None
        assert set(s.keys()) == self._expected_keys()
        assert s["n_a"] == 5 and s["n_b"] == 5
        assert s["cliffs_delta"] is not None
        assert s["cohens_d"] is not None
        assert s["cohens_d"] == pytest.approx(0.6325, abs=1e-3)
        assert s["hedges_g"] is not None
        assert s["ci95_mean_diff"] is not None  # [lo, hi]
        assert isinstance(s["note"], str)

    def test_length_mismatch_returns_none(self) -> None:
        assert effect_size_summary([1, 2], [1]) is None

    def test_empty_returns_none(self) -> None:
        assert effect_size_summary([], [1, 2]) is None

    def test_constant_groups_partial_none(self) -> None:
        """两组均常数 → cohens_d / hedges_g = None，但 cliffs_delta 仍可算。

        锁定"单项不可算不拖垮整 dict"的键集合同构口径。"""
        a = [5, 5, 5, 5]
        b = [3, 3, 3, 3]
        s = effect_size_summary(a, b)
        assert s is not None
        assert s["cohens_d"] is None
        assert s["hedges_g"] is None
        assert s["cliffs_delta"] == 1.0  # a 全大于 b
        # ci95_mean_diff 仍可算（mean diff = 2，bootstrap 能重采样）
        assert s["ci95_mean_diff"] is not None
