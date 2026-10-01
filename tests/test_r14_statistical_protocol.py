"""
R14（2026-09-30 独立审查 P0）：统计协议改造测试。

覆盖：
- mcnemar_test 二值配对检验（不一致对 / 全一致 / 样本不足）
- two_proportion_binomtest 二项检验
- bh_fdr_correct 多重比较校正（BH 保守口径）

Arcuri & Briand（ICSE 2011）：二值配对数据应用 McNemar 而非 t 检验；
多组对比须做 FDR 校正。本测试锁死统计口径，防"二值数据用 t 检验"的
历史缺陷回归。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.statistical_analysis import (
    bh_fdr_correct,
    mcnemar_test,
    two_proportion_binomtest,
)


class TestMcNemar:
    def test_mcnemar_incongruent_pairs(self):
        """A 全过 B 全败（6 共同任务）→ n01=6, n10=0，显著。

        连续性校正 (|6-0|-1)^2/6 = 25/6 ≈ 4.17 → p < 0.05（显著差异）。
        注：n01+n10 较小时校正过度保守（n01=3 时 p≈0.248），故样本量取 6。
        """
        A = [{"task_id": f"t{i}", "passed": True} for i in range(6)]
        B = [{"task_id": f"t{i}", "passed": False} for i in range(6)]
        chi2, p, n_conc, n_common = mcnemar_test(A, B)
        assert n_common == 6
        assert n_conc == 6  # 6 个不一致对（A 通过 B 失败）
        assert p < 0.05  # 显著差异
        assert chi2 > 0

    def test_mcnemar_all_match(self):
        """两组逐任务完全一致 → n_conc=0, p=1.0（无差异，保守）。"""
        A = [{"task_id": "t1", "passed": True}, {"task_id": "t2", "passed": False}]
        B = [{"task_id": "t1", "passed": True}, {"task_id": "t2", "passed": False}]
        chi2, p, n_conc, _ = mcnemar_test(A, B)
        assert n_conc == 0
        assert p == 1.0
        assert chi2 == 0.0

    def test_mcnemar_insufficient_sample(self):
        """共同任务 < 2 → nan（样本不足，与 paired_t_test 同口径）。"""
        A = [{"task_id": "t1", "passed": True}]
        B = [{"task_id": "t1", "passed": False}]
        chi2, p, _, n_common = mcnemar_test(A, B)
        assert math.isnan(p)
        assert math.isnan(chi2)
        assert n_common == 1

    def test_mcnemar_symmetric_incongruent(self):
        """对称不一致（n01=2, n10=2）→ chi2 小，不显著。"""
        A = [
            {"task_id": "t1", "passed": True},
            {"task_id": "t2", "passed": True},
            {"task_id": "t3", "passed": False},
            {"task_id": "t4", "passed": False},
        ]
        B = [
            {"task_id": "t1", "passed": False},
            {"task_id": "t2", "passed": False},
            {"task_id": "t3", "passed": True},
            {"task_id": "t4", "passed": True},
        ]
        _chi2, p, n_conc, _ = mcnemar_test(A, B)
        assert n_conc == 4
        # 对称不一致（2 vs 2）→ chi2 较小（|2-2|-1=1, 1^2/4=0.25），p 较大
        assert p > 0.05


class TestBinomTest:
    def test_binom_all_pass_significant(self):
        """全通过（10/10）vs 0.5 → p < 0.05（系统性通过）。"""
        A = [{"passed": True} for _ in range(10)]
        B = [{"passed": False} for _ in range(10)]
        p_a, p_b = two_proportion_binomtest(A, B)
        assert p_a < 0.05
        assert p_b < 0.05  # 0/10 全失败也显著偏离 0.5

    def test_binom_mixed_not_significant(self):
        """5/10 混合 → p ≈ 1.0（与抛硬币无差异）。"""
        A = [{"passed": i % 2 == 0} for i in range(10)]
        p_a, _ = two_proportion_binomtest(A, [])
        assert p_a > 0.5

    def test_binom_empty_nan(self):
        """空列表 → nan（无观测）。"""
        p_a, p_b = two_proportion_binomtest([], [])
        assert math.isnan(p_a)
        assert math.isnan(p_b)


class TestBH_FDR:
    def test_fdr_rejects_significant(self):
        """p=[0.01, 0.5, 0.5] → 第一组拒绝（q≤0.05），其余不拒绝。"""
        q_values, rejected = bh_fdr_correct([0.01, 0.5, 0.5])
        assert rejected == [True, False, False]
        assert q_values[0] <= 0.05

    def test_fdr_no_rejection(self):
        """全部 p 不显著 → 无拒绝，q 保守。"""
        _, rejected = bh_fdr_correct([0.3, 0.4, 0.5])
        assert all(r is False for r in rejected)

    def test_fdr_all_nan(self):
        """全 nan → q 全 nan，rejected 全 False。"""
        q_values, rejected = bh_fdr_correct([float("nan")] * 3)
        assert all(math.isnan(q) for q in q_values)
        assert all(r is False for r in rejected)

    def test_fdr_empty(self):
        """空列表 → 空结果。"""
        q_values, rejected = bh_fdr_correct([])
        assert q_values == []
        assert rejected == []

    def test_fdr_multiple_rejections(self):
        """p=[0.01, 0.02, 0.5, 0.5] → 前两组拒绝（BH 单调性）。"""
        _, rejected = bh_fdr_correct([0.01, 0.02, 0.5, 0.5])
        assert rejected == [True, True, False, False]
