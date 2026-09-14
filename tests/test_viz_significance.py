"""
visualize_results 统计显著性收敛测试（2026-09-15 深度重构批次）。

锁定行为：
- 配对原语复用 experiments.statistical_analysis._pair_by_task（按 task_id 配对）
- Cohen's d 复用 statistical_analysis.cohens_d（同一配对口径）
- 样本 < 3 时 t/U 检验记 NaN（图表占位），n_pairs < 2 时 Cohen's d 记 NaN
- 旧实现按"全部 task_id 0.0 填充"的口径已被废弃——缺失 task_id 的任务
  在统计检验中不计入样本（与 statistical_analysis 规范一致）
"""

from __future__ import annotations

import math

import pytest


@pytest.fixture
def viz():
    """加载 visualize_results（依赖 matplotlib，缺失时跳过）。"""
    pytest.importorskip("matplotlib", reason="matplotlib 未安装（experiments.visualize_results 依赖）")
    from experiments import visualize_results

    return visualize_results


def _make_summary(rate_map: dict[str, dict[str, int]]) -> dict:
    """构造 compute_significance 的输入（baseline → {task_id: passed}）。"""
    results = {}
    for baseline, tasks in rate_map.items():
        details = [{"task_id": tid, "passed": bool(passed)} for tid, passed in tasks.items()]
        results[baseline] = {"details": details}
    return {"results": results}


class TestSignificanceConvergence:
    """统计检验收敛到 statistical_analysis 单一规范实现的行为锁定。"""

    def test_pairs_by_task_id_not_by_full_universe(self, viz) -> None:
        """缺失 task_id 的任务不计入样本（旧"0.0 填充全任务集"口径已废弃）。"""
        summary = _make_summary(
            {
                "aitester": {"t1": 1, "t2": 1, "t3": 0},
                "plain_llm": {"t1": 1, "t2": 0, "t4": 1},  # t4 仅 plain_llm 有
            }
        )
        sig = viz.compute_significance(summary)
        # t1/t2 共同（t3 仅 aitester，t4 仅 plain_llm → 不计入）
        (pair,) = sig["pairwise"]
        _ref, _cmp_bl, t_stat, p_val, u_stat, mw_p, d, _sig_mark, _effect = pair
        assert _ref == "aitester"
        assert _cmp_bl == "plain_llm"
        assert sig["n_tasks"] == 4  # 全集仍为 4 个 task_id（n_tasks 字段保留旧语义）
        # 配对样本 2 个 → t/U 记 NaN（< 3）
        assert math.isnan(t_stat) and math.isnan(p_val)
        assert math.isnan(u_stat) and math.isnan(mw_p)
        # Cohen's d：n_pairs=2 可计算（差异 t1 相同、t2 不同）
        assert isinstance(d, float)

    def test_sufficient_samples_compute_real_values(self, viz) -> None:
        """样本 ≥ 3 且差异有方差时 t/U/d 均为有限数值。"""
        a = {"t1": 1, "t2": 1, "t3": 1, "t4": 0, "t5": 1, "t6": 0}
        b = {"t1": 0, "t2": 0, "t3": 1, "t4": 0, "t5": 0, "t6": 0}
        sig = viz.compute_significance(_make_summary({"aitester": a, "plain_llm": b}))["pairwise"]
        (_ref, _cmp_bl, t_stat, p_val, u_stat, mw_p, d, _sig_mark, _effect) = sig[0]
        assert math.isfinite(t_stat)
        assert math.isfinite(p_val)
        assert math.isfinite(u_stat)
        assert math.isfinite(mw_p)
        assert math.isfinite(d)

    def test_constant_groups_produce_nan_placeholder(self, viz) -> None:
        """恒定组（全 1 vs 全 0）配对 t 检验 t=inf → NaN 占位（与 analysis.py 守卫口径一致）。"""
        a = {f"t{i}": 1 for i in range(6)}
        b = {f"t{i}": 0 for i in range(6)}
        sig = viz.compute_significance(_make_summary({"aitester": a, "plain_llm": b}))["pairwise"]
        (_r, _c, t_stat, p_val, u_stat, mw_p, d, sig_mark, _eff) = sig[0]
        assert math.isnan(t_stat)
        assert math.isnan(p_val)
        assert math.isnan(u_stat)
        assert math.isnan(mw_p)
        assert math.isnan(d)
        assert sig_mark == "n.s."

    def test_reuses_statistical_analysis_primitives(self, viz) -> None:
        """配对原语/效应量/标记解释引用 statistical_analysis（单一规范实现）。"""
        from experiments import statistical_analysis

        # 四个函数均指向 statistical_analysis 模块的实现（非本地副本）
        assert viz._pair_by_task is statistical_analysis._pair_by_task
        assert viz.cohens_d is statistical_analysis.cohens_d
        assert viz.interpret_p is statistical_analysis.interpret_p
        assert viz.interpret_d is statistical_analysis.interpret_d

    def test_single_baseline_no_pairwise(self, viz) -> None:
        """单基线时 pairwise 为空（行为不变）。"""
        sig = viz.compute_significance(_make_summary({"aitester": {"t1": 1}}))
        assert sig["pairwise"] == []
        assert sig["n_tasks"] == 1

    def test_per_baseline_summary_fields(self, viz) -> None:
        """per_baseline 字段口径不变（mean_rate / std_rate / n）。"""
        sig = viz.compute_significance(_make_summary({"aitester": {"t1": 1, "t2": 0}}))
        pb = sig["per_baseline"]["aitester"]
        assert pb["mean_rate"] == 50.0
        assert pb["std_rate"] == pytest.approx(70.7, abs=0.1)  # 样本 std
        assert pb["n"] == 2
