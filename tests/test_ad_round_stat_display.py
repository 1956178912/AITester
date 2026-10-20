#!/usr/bin/env python3
"""AD 轮（2026-10-20）回归锁：统计量渲染的量级保持 + 正态尾部补集模式消除。

背景（AC 轮登记的两项 + 数值精度普查结论）：

1. **AD-1（p 值显示精度）**：`_fmt_stat_num` 的 `{:.4f}` 把 |v| < 5e-5 的
   非零值一律印成 "0.0000"——量级信息被静默销毁。AC-1 的教训正是如此：
   p=5.890715e-26（χ²=111.01 的精确值）与下溢的 p=0.0 在报告里同形
   （都显示 "0.0000 (***)"），读者无法从账面区分"精确算出的极小值"与
   "精度丢失"。现非零小量级改科学计数法渲染；精确 0.0 仍渲染 "0.0000"
   （零是合法统计值）。
2. **AD-2（正态尾部补集模式）**：`emse_testlevel_detection.py` 的
   `1.0 - _normal_cdf(z)` 与 AC-1 的 `1 - chi2.cdf` 同型——z ≳ 8.2 时
   `1.0 - cdf` 因浮点精度静默变 0.0。改 erfc 直接算尾部。该字段
   `round(..., 4)` 显示，可显示区间内读数逐位相同；改动消除模式本身。

普查结论（同族其余点位判定）：pass@k 的 `1.0 - prod`（下溢时真值即 1.0
到机器精度，渲染不变）、Wilson 的 `p*(1-p)`（乘积非补集）、Cohen's κ 的
`(po-pe)/(1-pe)`（pe≥1 已有守卫）、BF10 的 `exp(log 差)`（下溢到 0.0 是
"支持 H0"的 intended 语义）、`inv_cdf(1-alpha/2)`（alpha 常量不接近 1）、
协议 0/1 值的浮点相等比较（生产者只写字面量 1.0/0.0/None，全仓一致习语）、
两遍法方差（数值稳定）——均判定良性/一致，不动作。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from experiments.emse_testlevel_detection import _normal_sf, wilcoxon_signed_rank
from experiments.statistical_analysis import _fmt_stat_num, mcnemar_test

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_MAIN_BATCH = PROJECT_ROOT / "experiments" / "results" / "main_batch"
_MAIN_FILES = (
    "benchmark_synthetic_20261006_164357.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_140906.json",
)
_MAIN_READY = all((_MAIN_BATCH / f).exists() for f in _MAIN_FILES)
_ready_main = pytest.mark.skipif(not _MAIN_READY, reason="三种子主批原始批次工件不在工作树")


class TestStatNumMagnitudePreserved:
    """AD-1：非零小量级必须保留量级（旧 {:.4f} 一律印 0.0000）。"""

    def test_tiny_p_renders_scientific(self) -> None:
        # AC-1 的精确值：旧渲染 "0.0000"，与下溢的 0.0 同形
        assert _fmt_stat_num(5.890715e-26) == "5.89e-26"
        assert _fmt_stat_num(1.767215e-25) == "1.77e-25"

    def test_moderate_tiny_p_renders_scientific(self) -> None:
        # 1.8e-07 量级：旧渲染同样是 "0.0000"（量级全丢）
        assert _fmt_stat_num(1.81101728724542e-07) == "1.81e-07"
        assert _fmt_stat_num(2.843839e-12) == "2.84e-12"

    def test_exact_zero_stays_fixed_point(self) -> None:
        """精确 0.0 是合法统计值（χ²=0 / 无不一致对）——不改渲染。

        -0.0 与 0.0 相等故同走定点分支，符号由 `{:.4f}` 保留（既有行为）。
        """
        assert _fmt_stat_num(0.0) == "0.0000"
        assert _fmt_stat_num(-0.0) == "-0.0000"

    def test_negative_tiny_renders_scientific(self) -> None:
        assert _fmt_stat_num(-3.2e-05) == "-3.20e-05"

    def test_normal_range_unchanged(self) -> None:
        assert _fmt_stat_num(0.1234) == "0.1234"
        assert _fmt_stat_num(1.0) == "1.0000"
        assert _fmt_stat_num(-0.5) == "-0.5000"
        assert _fmt_stat_num(111.00885) == "111.0088"  # 或 111.0089（十进制舍入），非科学计数法
        assert "e" not in _fmt_stat_num(111.00885)

    def test_nan_inf_unchanged(self) -> None:
        assert _fmt_stat_num(float("nan")) == "n/a"
        assert _fmt_stat_num(float("inf")) == "+inf"
        assert _fmt_stat_num(float("-inf")) == "-inf"

    def test_boundary_values(self) -> None:
        """阈值 |v| < 1e-4：阈值上沿用定点、下方用科学计数法（边界不含糊）。"""
        assert "e" not in _fmt_stat_num(1e-4)
        assert "e" in _fmt_stat_num(9.99e-05)

    @_ready_main
    def test_report_cell_shows_magnitude_for_main_batch(self) -> None:
        """端到端：主批 plain-df 比较经生产路径渲染出量级（AC-1 可见性闭合）。"""
        rows: dict[str, list[dict]] = {}
        for arm in ("aitester", "plain_llm", "plain_llm_df"):
            all_rows: list[dict] = []
            for name in _MAIN_FILES:
                data = json.loads((_MAIN_BATCH / name).read_text(encoding="utf-8"))
                seed = (data.get("provenance") or {}).get("seed")
                prefix = f"s{seed}__" if seed is not None else ""
                all_rows.extend(
                    {**r, "task_id": f"{prefix}{r.get('task_id', '')}"}
                    for r in data.get("results", {}).get(arm, {}).get("details", [])
                )
            latest: dict[str, dict] = {}
            for r in all_rows:
                tid = r.get("task_id")
                if tid and tid not in latest:
                    latest[tid] = r
            rows[arm] = list(latest.values())
        _chi2, p, _nd, _n = mcnemar_test(rows["plain_llm_df"], rows["plain_llm"], field="detection_rate")
        cell = _fmt_stat_num(p)
        assert p == pytest.approx(5.890715e-26, rel=1e-5, abs=0.0)
        assert cell == "5.89e-26"  # 旧实现为 "0.0000"（此断言在旧渲染下转红）


class TestNormalTailSurvival:
    """AD-2：正态尾部用 erfc 生存函数，不用 1−cdf 补集。"""

    def test_matches_scipy_sf(self) -> None:
        from scipy.stats import norm

        for z in (0.0, 0.5, 1.0, 1.96, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0):
            assert _normal_sf(z) == pytest.approx(float(norm.sf(z)), rel=1e-12, abs=0.0), z

    def test_no_underflow_where_complement_would(self) -> None:
        """z=10：1−cdf 恒 0.0（旧模式），erfc 尾部精确（旧调用点转红）。"""
        legacy = 1.0 - (0.5 * (1.0 + math.erf(10.0 / math.sqrt(2.0))))
        assert legacy == 0.0  # 坐实旧模式在此下溢
        assert _normal_sf(10.0) == pytest.approx(7.619853024160525e-24, rel=1e-6, abs=0.0)
        assert _normal_sf(10.0) > 0.0

    def test_wilcoxon_p_normal_approx_unchanged_in_display_range(self) -> None:
        """可显示区间内 p_normal_approx 读数逐位不变（改动只消除模式）。"""
        out = wilcoxon_signed_rank([1.0, 2.0, 3.0, 4.0, 5.0])
        assert out["p_exact"] == 0.0625
        # 旧公式复算对照：2·(1−cdf(z)) 与本轮 erfc 式在 4dp 显示域内一致
        n = out["n_nonzero"]
        w = out["w_plus"]
        mean = n * (n + 1) / 4.0
        var = n * (n + 1) * (2 * n + 1) / 24.0
        z = (abs(w - mean) - 0.5) / math.sqrt(var)
        legacy = round(min(2.0 * (1.0 - (0.5 * (1.0 + math.erf(max(z, 0.0) / math.sqrt(2.0))))), 1.0), 4)
        assert out["p_normal_approx"] == legacy
