"""emse_stats_extensions 纯函数单测（第十九轮评审 A-15，2026-10-16）。

锁定口径：Wilson 区间 / Cohen's g / OR+Haldane 修正 / McNemar 精确 p /
种子化 bootstrap 确定性。期望值为**独立手算**（不调用被测函数生成），
防"自己验证自己"。
"""

from __future__ import annotations

import math

import pytest

from experiments.emse_stats_extensions import (
    Z95,
    binom_exact_two_sided,
    cohens_g,
    odds_ratio_ci,
    paired_bootstrap_diff_ci,
    wilson_ci,
)


@pytest.mark.unit
class TestWilsonCi:
    """Wilson score 区间（手算期望值）。"""

    def test_known_values_rp02_aitester(self):
        # 38/240 手算：center=0.163712, half=0.046146 → (0.117566, 0.209858)
        lo, hi = wilson_ci(38, 240)
        assert lo == pytest.approx(0.1176, abs=1e-4)
        assert hi == pytest.approx(0.2099, abs=1e-4)

    def test_known_values_rp02_df(self):
        # 117/261 手算：center=0.449078, half=0.059890 → (0.389188, 0.508968)
        lo, hi = wilson_ci(117, 261)
        assert lo == pytest.approx(0.3892, abs=1e-4)
        assert hi == pytest.approx(0.5089, abs=1e-4)

    def test_zero_successes_upper_bound(self):
        # 0/10 手算上界 ≈ 0.2776（Wilson 不会给出 0 上界——与 naive 近似关键差异）
        lo, hi = wilson_ci(0, 10)
        assert lo == 0.0
        assert hi == pytest.approx(0.2776, abs=1e-4)

    def test_all_successes(self):
        lo, hi = wilson_ci(10, 10)
        assert hi == 1.0
        assert lo == pytest.approx(0.7224, abs=1e-4)

    def test_n_zero_fail_closed(self):
        assert wilson_ci(0, 0) == (0.0, 0.0)

    def test_bounds_within_unit_interval(self):
        for k, n in [(1, 3), (5, 7), (50, 100), (999, 1000)]:
            lo, hi = wilson_ci(k, n)
            assert 0.0 <= lo <= hi <= 1.0


@pytest.mark.unit
class TestEffectSizes:
    """Cohen's g / OR / 精确 p。"""

    def test_cohens_g_known(self):
        # 12/80：|12-80|/92 = 0.73913
        assert cohens_g(12, 80) == pytest.approx(0.7391, abs=1e-4)

    def test_cohens_g_zero_discordant(self):
        assert cohens_g(0, 0) == 0.0

    def test_cohens_g_one_sided(self):
        assert cohens_g(5, 0) == 1.0

    def test_odds_ratio_known(self):
        # b=12.5, c=80.5（Haldane +0.5）：OR=0.15528, CI≈(0.0856, 0.2818)
        pt, lo, hi = odds_ratio_ci(12, 80)
        assert pt == pytest.approx(0.1553, abs=1e-4)
        assert lo == pytest.approx(0.0856, abs=1e-4)
        assert hi == pytest.approx(0.2818, abs=1e-4)

    def test_odds_ratio_zero_cell_no_crash(self):
        # n01=0：修正后 CI 上界极大（正确行为，防除零）
        pt, _lo, hi = odds_ratio_ci(113, 0)
        assert math.isfinite(pt) and math.isfinite(hi)
        assert hi > 100

    def test_binom_exact_two_sided_known(self):
        # 0/14 双尾精确 p = 2 × 0.5^14 = 0.000122
        assert binom_exact_two_sided(0, 14) == pytest.approx(2 * 0.5**14, rel=1e-6)

    def test_binom_exact_extreme(self):
        # 7/14：双尾 p = 1（完全无方向）
        assert binom_exact_two_sided(7, 14) == pytest.approx(1.0)


@pytest.mark.unit
class TestPairedBootstrap:
    """种子化配对 bootstrap：确定性 + 区间合理性。"""

    def test_deterministic_same_seed(self):
        pairs = [(1.0, 0.0)] * 12 + [(0.0, 1.0)] * 80 + [(0.0, 0.0)] * 100
        a = paired_bootstrap_diff_ci(pairs, n_boot=200, seed=42)
        b = paired_bootstrap_diff_ci(pairs, n_boot=200, seed=42)
        assert a == b  # 同种子逐位一致（可复现性纪律）

    def test_different_seed_can_differ(self):
        # 不同种子通常给出不同 CI；但小样本 + 高度倾斜数据下百分比位可能
        # 偶然重合（choices 实现尤然）——故断言"多个种子中至少一次不同"
        # 而非"必然不同"（后者是把随机性质当确定性性质的错误假设）。
        pairs = [(1.0, 0.0)] * 12 + [(0.0, 1.0)] * 80
        results = {paired_bootstrap_diff_ci(pairs, n_boot=200, seed=s) for s in (42, 43, 44, 45, 46)}
        assert len(results) > 1

    def test_direction_and_containment(self):
        # a 系统性低于 b：CI 应全负且包含点差
        pairs = [(0.0, 1.0)] * 30 + [(0.0, 0.0)] * 70
        lo, hi = paired_bootstrap_diff_ci(pairs, n_boot=2000, seed=42)
        assert hi < 0.0
        assert lo <= -0.3 <= hi

    def test_empty_pairs_fail_closed(self):
        assert paired_bootstrap_diff_ci([], n_boot=10, seed=42) == (0.0, 0.0)


@pytest.mark.unit
class TestConstants:
    def test_z95_precision(self):
        # 精确分位数（防手抄 1.96 常数漂移）
        assert abs(Z95 - 1.959964) < 1e-6
