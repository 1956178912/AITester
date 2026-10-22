"""BR 轮（2026-10-22 第三方集中复审）统计/账本契约：N03/N04/N05/N06/N07。

每一项都用报告给出的构造反例锁定"修复前会错、修复后不会"的行为，避免只测
正常路径（这类缺陷的共同特征正是"正常批次看不出来"）。
"""

from __future__ import annotations

import os
import sys
from typing import ClassVar
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import e7_adjudication
from experiments.emse_optimization import paired_contrast
from experiments.emse_stats_extensions import _cost_per_task, _read_tokens, binom_exact_two_sided
from experiments.statistical_analysis import cost_analysis
from scripts.tools.power_analysis import detectable_delta_paired, power_paired

_PRICE_ONE_DOLLAR = {"models": {"m": {"currency": "USD", "input_per_mtok": 1, "output_per_mtok": 1}}}


class TestE7Identity:
    """N03：按候选号合并前必须核对任务身份。"""

    _A: ClassVar[list[dict[str, str]]] = [
        {"candidate_no": "1", "task_id": "t1", "judgment": "equivalent"},
        {"candidate_no": "2", "task_id": "t2", "judgment": "test_only"},
    ]
    _B_SWAPPED: ClassVar[list[dict[str, str]]] = [
        {"candidate_no": "1", "task_id": "t2", "judgment": "equivalent"},
        {"candidate_no": "2", "task_id": "t1", "judgment": "test_only"},
    ]
    _B_CONSISTENT: ClassVar[list[dict[str, str]]] = [
        {"candidate_no": "1", "task_id": "t1", "judgment": "test_only"},
        {"candidate_no": "2", "task_id": "t2", "judgment": "equivalent"},
    ]

    def _merge(self, rows_b, **kwargs):
        with patch.object(e7_adjudication, "load_entry_sheet", side_effect=[self._A, rows_b]):
            return e7_adjudication.merge_sheets("A.csv", "B.csv", n_resamples=0, **kwargs)

    def test_swapped_identity_is_refused_before_kappa(self):
        """A/B 任务身份互换：历史实现给 κ=1.0（完全相反的判定被算成一致）。"""
        with pytest.raises(ValueError, match="身份校验失败"):
            self._merge(self._B_SWAPPED)

    def test_consistent_identity_still_computes(self):
        report = self._merge(self._B_CONSISTENT)
        assert report["n_scored"] == 2
        # 两行判定完全相反（equivalent vs test_only 互换）→ κ 应为 -1.0
        assert report["kappa"] == pytest.approx(-1.0)

    def test_missing_task_id_is_refused(self):
        rows = [dict(self._B_CONSISTENT[0], task_id=""), self._B_CONSISTENT[1]]
        with pytest.raises(ValueError, match="身份校验失败"):
            self._merge(rows)

    def test_candidates_list_binds_identity(self):
        """给出抽样清单时，表内 task_id 被改写即拒绝（validate 前置）。"""
        candidates = [{"candidate_no": 1, "task_id": "t1"}, {"candidate_no": 2, "task_id": "t2"}]
        with pytest.raises(ValueError, match="未通过校验"):
            self._merge(self._B_SWAPPED, candidates=candidates)


class TestCostAttribution:
    """N04：逐行归因闭合，未知 token 不得套其他行价格。"""

    def test_missing_attribution_blocked_with_scoped_subtotal(self):
        usage = {"total_tokens": 100, "input_tokens": 40, "output_tokens": 60}
        results = {
            "a": [
                {"token_usage": dict(usage, by_model={"m": 100})},
                {"token_usage": dict(usage)},  # 缺归因
            ]
        }
        row = cost_analysis(results, _PRICE_ONE_DOLLAR)[0]

        assert row["cost"] is None  # 全额不可计算（历史给 0.0002）
        assert row["priced"] is False
        assert row["cost_per_task"] is None
        assert row["unattributed_tokens"] == 100
        assert row["n_unattributed_rows"] == 1
        # 可归因小计保留，但范围明确标注（只有第一行 100 token）
        assert row["attributed_cost"] == pytest.approx(0.0001)
        assert row["attributed_cost_scope"] == "attributed_rows_only"

    def test_fully_attributed_arm_still_priced(self):
        usage = {"total_tokens": 100, "input_tokens": 40, "output_tokens": 60}
        results = {"a": [{"token_usage": dict(usage, by_model={"m": 100})}]}
        row = cost_analysis(results, _PRICE_ONE_DOLLAR)[0]

        assert row["priced"] is True
        assert row["cost"] == pytest.approx(0.0001)
        assert "attributed_cost" not in row  # 无缺归因时返回域不变

    def test_per_row_nonclosure_cannot_cancel_out(self, monkeypatch):
        """路径 B：两行逐行不闭合、整臂 200=200 仍必须废金额。"""
        fixture = {
            "total_tasks": 2,
            "results": {
                "a": {
                    "details": [
                        {
                            "task_id": "t1",
                            "token_usage": {
                                "total_tokens": 100,
                                "input_tokens": 40,
                                "output_tokens": 60,
                                "by_model": {"m": 200},
                            },
                        },
                        {
                            "task_id": "t2",
                            "token_usage": {
                                "total_tokens": 100,
                                "input_tokens": 40,
                                "output_tokens": 60,
                                "by_model": {"m": 0},
                            },
                        },
                    ]
                }
            },
        }
        monkeypatch.setattr("experiments.emse_stats_extensions._load", lambda _rel: fixture)
        monkeypatch.setattr(
            "experiments.emse_stats_extensions._load_price_models",
            lambda: (_PRICE_ONE_DOLLAR["models"], None),
        )

        reading = _read_tokens(["fixture.json"], "a")
        assert any(r.startswith("row_attribution_mismatch") for r in reading["model_reasons"])

        _tpt, usd, note = _cost_per_task(["fixture.json"], "a")
        assert usd is None
        assert "row_attribution_mismatch" in note


class TestPairedLatestRows:
    """N05：先选最新行，再排除 None；旧可测值不得顶替最新 None。"""

    def test_latest_none_wins_and_pairs_consistently(self):
        a = [
            {"task_id": "t1", "detection_rate": None},
            {"task_id": "t2", "detection_rate": 1},
            {"task_id": "t3", "detection_rate": 0},
            {"task_id": "t1", "detection_rate": 0},  # 旧批次
        ]
        b = [
            {"task_id": "t1", "detection_rate": 1},
            {"task_id": "t2", "detection_rate": 0},
            {"task_id": "t3", "detection_rate": 0},
        ]

        out = paired_contrast(a, b)
        assert out["n_pairs"] == 2  # 历史给 3
        assert out["delta_pp"] == pytest.approx(50.0)  # 历史给 0.0

    def test_no_duplicates_unchanged(self):
        a = [{"task_id": "t1", "detection_rate": 1}, {"task_id": "t2", "detection_rate": 0}]
        b = [{"task_id": "t1", "detection_rate": 0}, {"task_id": "t2", "detection_rate": 0}]
        out = paired_contrast(a, b)
        assert (out["n_pairs"], out["only_first"], out["delta_pp"]) == (2, 1, 50.0)


class TestBinomialTies:
    """N06：非 0.5 精确二项的并列结局必须计入。"""

    def test_tied_outcomes_are_not_dropped(self):
        assert binom_exact_two_sided(0, 4, p=0.2) == pytest.approx(1.0, abs=0.0)

    def test_non_tied_case_matches_exact_enumeration(self):
        # k=0,n=10,p=.3：单侧 .7^10=.0282475，另一尾 .009002+.001447+... → .0388396
        assert binom_exact_two_sided(0, 10, p=0.3) == pytest.approx(0.03883960329999999, abs=0.0)

    def test_half_p_integer_branch_unchanged(self):
        """McNemar 唯一生产实参 p=.5 走整数权重分支，尾部数值不得漂移。"""
        assert binom_exact_two_sided(0, 113) == pytest.approx(1.925929944387236e-34, abs=0.0)

    def test_boundary_p_values(self):
        assert binom_exact_two_sided(3, 3, p=1.0) == 1.0
        assert binom_exact_two_sided(0, 3, p=0.0) == 1.0


class TestZeroBaselineMDE:
    """N07：零基线退化端点不得把可检出差异报成 nan。"""

    def test_finite_mde_with_matching_power(self):
        mde = detectable_delta_paired(100, 0.0, 0.0)
        assert mde == mde  # 不是 nan
        assert mde == pytest.approx(0.0727764806, rel=1e-6)
        assert power_paired(100, mde, 0.0, 0.0) == pytest.approx(0.8, abs=1e-9)

    def test_power_at_small_delta_is_not_alpha(self):
        """δ=.1 的功效 .9152 与"端点 nan"并存即自相矛盾（修复前现象）。"""
        assert power_paired(100, 0.1, 0.0, 0.0) == pytest.approx(0.9151812833, rel=1e-9)

    def test_degenerate_variance_reports_zero_not_alpha(self):
        """δ≠0 且 σ²=0（p_a=1,p_b=0,p11=0）→ 0.0，不冒充弃真率。"""
        assert power_paired(100, 1.0, 0.0, 0.0) == 0.0

    def test_true_zero_power_still_nan(self):
        """样本量真不足（可行域内最大 δ 也未达 80% 功效）时保持 nan。"""
        mde = detectable_delta_paired(1, 0.3, 0.29)
        assert mde != mde  # nan：n=1 连可行域上端都只有 0.297 功效
