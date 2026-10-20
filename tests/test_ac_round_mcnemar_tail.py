#!/usr/bin/env python3
"""AC 轮（2026-10-20）回归锁：McNemar p 值尾部数值稳定性（生产路径）。

背景（AC 轮独立复算发现）：`mcnemar_test` 旧实现以 `1.0 - chi2.cdf(x, df=1)`
计算 p。float64 相对 1 的机器精度约 2.2e-16，故 `1.0 - cdf` 在
p ≲ 6e-17（χ² ≳ 71）时恒等于 1.0 → p 静默变为精确 0.0。主批
plain_llm_df vs plain_llm（χ²=111.00885）实测旧路径 p=0.0、BH q=0.0，
而 Z 轮勘误表（statistical_report_3seed_pooled.md）引用的精确值为
p=5.890715e-26 / q=1.767215e-25（`erfc(√(χ²/2))` 与 `chi2.sf` 逐位一致）
——即**报告数字无法从生产代码路径复现**。Z 轮测试（test_review_20261019_
stats.py）虽锁定了精确值，但走的是测试内 `erfc` 助手，生产
`mcnemar_test` 从未在该数据上被执行过（"逻辑有测试、接线无测试"同型盲区）。

本文件锁定三组行为（**旧 `1-cdf` 实现在每组都会转红**）：

1. **生产路径真值**：三种子主批 detection 三比较经生产 `mcnemar_test`
   + 生产 `bh_fdr_correct` 返回 p=(5.890715e-26, 2.843839e-12,
   1.811017e-07)、q=(1.767215e-25, 4.265758e-12, 1.811017e-07)——与
   pooled 报告勘误节引用值一致（复算链条闭合）。
2. **合成大 χ² 不下溢**：b/c=400/0（χ²≈798）→ p 必须 > 0 且 < 1e-100，
   且与 `erfc(√(χ²/2))` 精确公式相对误差 < 1e-12。
3. **既有语义不变**：全一致 → (0.0, 1.0)；n_common<2 → (nan, nan)；
   中等 χ²（27.225，p≈1.8e-07）sf 与 1-cdf 在 1e-12 相对误差内一致
   （修复不改变既有可复算值的量级）。

真实工件缺失时相关用例 `pytest.skip`（精简 CI 环境）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from experiments.statistical_analysis import bh_fdr_correct, mcnemar_test

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_MAIN_BATCH = PROJECT_ROOT / "experiments" / "results" / "main_batch"
# 文件名内嵌时间戳降序 = 最新批次在前（与 _sort_batch_files_deterministic 同口径）
_MAIN_FILES = (
    "benchmark_synthetic_20261006_164357.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_140906.json",
)
# detection 三比较（前臂 − 后臂；与 pooled 报告主表同序）
_COMPARISONS = (
    ("plain_llm_df", "plain_llm"),
    ("aitester", "plain_llm_df"),
    ("aitester", "plain_llm"),
)
_EXPECTED_P = (5.890715e-26, 2.843839e-12, 1.811017e-07)
_EXPECTED_Q = (1.767215e-25, 4.265758e-12, 1.811017e-07)
_MAIN_READY = all((_MAIN_BATCH / f).exists() for f in _MAIN_FILES)
_ready_main = pytest.mark.skipif(not _MAIN_READY, reason="三种子主批原始批次工件不在工作树")


def _load_arm(arm: str) -> list[dict]:
    """按项目口径加载单臂：种子分层前缀 + 最新批次优先去重（首见胜出）。"""
    rows: list[dict] = []
    for name in _MAIN_FILES:
        data = json.loads((_MAIN_BATCH / name).read_text(encoding="utf-8"))
        seed = (data.get("provenance") or {}).get("seed")
        prefix = f"s{seed}__" if seed is not None else ""
        rows.extend(
            {**r, "task_id": f"{prefix}{r.get('task_id', '')}"}
            for r in data.get("results", {}).get(arm, {}).get("details", [])
        )
    latest: dict[str, dict] = {}
    for r in rows:
        tid = r.get("task_id")
        if not tid or tid in latest:
            continue
        latest[tid] = r
    return list(latest.values())


def _erfc_sf(chi2_stat: float) -> float:
    """df=1 卡方生存函数精确式：P(X > x) = erfc(√(x/2))（纯 math 参考实现）。"""
    return math.erfc(math.sqrt(chi2_stat / 2.0))


class TestMcNemarTailStability:
    """p 值不得因 `1-cdf` 浮点下溢而静默变 0.0（AC-1）。"""

    def test_synthetic_huge_chi2_not_underflowed(self):
        """b/c=1000/0 → χ²≈998：p 必须保持为正的极小值（旧 1-cdf 恒 0.0）。"""
        rows_a = [{"task_id": f"t{i}", "detection_rate": 1} for i in range(1000)]
        rows_b = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(1000)]
        chi2, p, n_conc, n_common = mcnemar_test(rows_a, rows_b, field="detection_rate")
        assert n_common == 1000 and n_conc == 1000
        assert chi2 == pytest.approx((1000 - 0 - 1) ** 2 / 1000, rel=1e-12)
        assert p > 0.0, "p 不得下溢为 0.0（旧 1-cdf 实现在此转红）"
        assert p < 1e-100
        assert p == pytest.approx(_erfc_sf(chi2), rel=1e-12)

    def test_underflow_threshold_boundary(self):
        """χ² 刚过下溢阈值（~71）时 p 仍须精确（旧实现在此区间已开始丢精度）。"""
        # 构造 b=56, c=0 → χ²=(56-1)²/56=54.02（p≈2.4e-13，尚未下溢）
        rows_a = [{"task_id": f"t{i}", "detection_rate": 1} for i in range(56)]
        rows_b = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(56)]
        chi2, p, _, _ = mcnemar_test(rows_a, rows_b, field="detection_rate")
        assert p == pytest.approx(_erfc_sf(chi2), rel=1e-12)
        # 构造 b=1000, c=0 → χ²≈998（p≈1e-217，1-cdf 必下溢）
        rows_a = [{"task_id": f"t{i}", "detection_rate": 1} for i in range(1000)]
        rows_b = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(1000)]
        chi2, p, _, _ = mcnemar_test(rows_a, rows_b, field="detection_rate")
        assert p > 0.0
        assert p < 1e-100
        assert p == pytest.approx(_erfc_sf(chi2), rel=1e-12)

    def test_moderate_chi2_values_unchanged(self):
        """中等 χ²（p≈1.8e-07）：sf 与旧 1-cdf 在 1e-12 相对误差内一致。"""
        from scipy.stats import chi2 as _chi2_dist

        rows_a = [{"task_id": f"t{i}", "detection_rate": 1} for i in range(37)]
        rows_a += [{"task_id": f"t{i + 100}", "detection_rate": 0} for i in range(3)]
        rows_b = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(37)]
        rows_b += [{"task_id": f"t{i + 100}", "detection_rate": 1} for i in range(3)]
        chi2, p, _, _ = mcnemar_test(rows_a, rows_b, field="detection_rate")
        legacy = float(1.0 - _chi2_dist.cdf(chi2, df=1))
        assert p == pytest.approx(legacy, rel=1e-12)
        assert p == pytest.approx(1.81101728724542e-07, rel=1e-6)

    def test_existing_edge_semantics_preserved(self):
        """全一致 → (0.0, 1.0)；n_common<2 → (nan, nan)（既有语义不变）。"""
        same_a = [{"task_id": "t1", "passed": True}, {"task_id": "t2", "passed": False}]
        same_b = [{"task_id": "t1", "passed": True}, {"task_id": "t2", "passed": False}]
        assert mcnemar_test(same_a, same_b) == (0.0, 1.0, 0, 2)
        tiny_a = [{"task_id": "t1", "passed": True}]
        tiny_b = [{"task_id": "t1", "passed": False}]
        chi2, p, _, n_common = mcnemar_test(tiny_a, tiny_b)
        assert math.isnan(chi2) and math.isnan(p) and n_common == 1


@_ready_main
class TestMainBatchProductionPathTruth:
    """生产 mcnemar_test + bh_fdr_correct 在真实主批上的真值（闭合复算链）。"""

    def test_production_p_and_q_match_report_erratum(self):
        arms = {a: _load_arm(a) for a in ("aitester", "plain_llm", "plain_llm_df")}
        p_values = []
        for arm_a, arm_b in _COMPARISONS:
            _chi2, p, _n_conc, _n_common = mcnemar_test(arms[arm_a], arms[arm_b], field="detection_rate")
            p_values.append(p)
        # abs=0.0：pytest.approx 默认 abs=1e-12 会让"下溢的 0.0"冒充
        # 1e-25 量级的真值通过（实测陷阱），必须纯相对比较。
        # rel=1e-5：报告引用值为七位有效数字字面量（1.767215e-25 等），
        # 与全精度复算值的相对差在 1e-7 量级（Z 轮 p 值同款容差）。
        assert p_values == pytest.approx(list(_EXPECTED_P), rel=1e-5, abs=0.0)
        q_values, rejected = bh_fdr_correct(p_values)
        assert q_values == pytest.approx(list(_EXPECTED_Q), rel=1e-5, abs=0.0)
        assert rejected == [True, True, True]

    def test_production_chi2_matches_pooled_report(self):
        """χ² 列与 pooled 报告主表逐位一致（111.01 / 48.79 / 27.23）。"""
        arms = {a: _load_arm(a) for a in ("aitester", "plain_llm", "plain_llm_df")}
        got = [round(mcnemar_test(arms[a], arms[b], field="detection_rate")[0], 2) for a, b in _COMPARISONS]
        assert got == [111.01, 48.79, 27.23]
