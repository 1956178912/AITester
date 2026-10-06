"""
R2（2026-10-05 审查：统计协议完整性）测试。

覆盖：
- 报告落盘：McNemar / BH-FDR / Bootstrap 95% CI / Cliff's δ / 数据来源
  五个章节写入 statistical_report.md（R14 的 McNemar 与 BH-FDR 此前仅
  打印控制台——"算而未报"，报告读者只能看到口径错误的 t 检验表）；
- bootstrap_paired_diff_ci 手算值断言（已知小样本 + 固定 seed=42，
  结果逐位可复现）；
- --batches 白名单过滤（白名单外文件与非 synthetic 文件既不进入统计、
  也不进入"数据来源"审计清单；未提供 --batches 时 glob 行为不变）；
- cliffs_delta 边界（全正差值 +1 / 全负差值 −1 / 正负平衡 0）；
- analyze_results 的 M1 指标聚合（detection/repair/false_fix/test_error_rate，
  None 不计入分母——"不可测"不是 0 分）。

默认行为不变原则：既有"配对t检验结果"表保持原样（回归断言锁定）。
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.analyze_results import _m1_metrics_aggregate, build_analysis, render_markdown
from experiments.statistical_analysis import (
    bootstrap_paired_diff_ci,
    cliffs_delta,
    interpret_cliffs_delta,
    load_experiment_results_with_sources,
    run_all_statistics,
)
from experiments.statistical_analysis import (
    main as stat_main,
)


def _write_batch(
    root: Path,
    name: str,
    *,
    dataset: str = "synthetic",
    aitester_passed: list[bool],
    plain_llm_passed: list[bool],
    single_agent_passed: list[bool] | None = None,
) -> str:
    """写一个 benchmark_*.json 批次文件（task_id 对齐 t0..tn-1），返回文件名。

    X2（2026-10-05 P0-4b）起：行携带非 None 的 detection_rate（镜像
    passed 值）——统计加载默认剔除"M1 指标未计算"的批次，fixture 不带
    该字段会被新口径过滤，报告为空。
    """

    def _rows_x2(passed: list[bool]) -> list[dict]:
        return [{"task_id": f"t{i}", "passed": p, "detection_rate": 1.0 if p else 0.0} for i, p in enumerate(passed)]

    results: dict[str, dict] = {
        "aitester": {"details": _rows_x2(aitester_passed)},
        "plain_llm": {"details": _rows_x2(plain_llm_passed)},
    }
    if single_agent_passed is not None:
        results["single_agent"] = {"details": _rows_x2(single_agent_passed)}
    (root / name).write_text(json.dumps({"dataset": dataset, "results": results}), encoding="utf-8")
    return name


def _rows(passed: list[bool], offset: int = 0) -> list[dict]:
    """构造结果行列表（task_id 带偏移，供两组部分重叠场景）。"""
    return [{"task_id": f"t{i + offset}", "passed": p} for i, p in enumerate(passed)]


class TestReportSectionsOnDisk:
    """R2：McNemar / BH-FDR / bootstrap / Cliff's δ / 数据来源 章节落盘。"""

    def test_mcnemar_and_fdr_sections_written(self, tmp_path):
        """AITester 6/8 通过 vs plain_llm 0/8：McNemar n01=6, n10=0 →
        chi2=(6−1)²/6=4.1667，p=0.0412（*）；单对比 BH-FDR q=p 且拒绝 H0。"""
        _write_batch(
            tmp_path,
            "benchmark_r2a.json",
            aitester_passed=[True] * 6 + [False] * 2,
            plain_llm_passed=[False] * 8,
        )
        report = tmp_path / "statistical_report.md"
        run_all_statistics(str(tmp_path), str(report))
        text = report.read_text(encoding="utf-8")

        # 默认行为不变：历史 t 检验表原样保留
        assert "## 配对t检验结果" in text
        assert "| AITester vs plain_llm | 8 |" in text

        # McNemar 章节落盘（手算：n01=6, n10=0, chi2=4.1667, p=0.0412 → *）
        assert "## McNemar 配对检验（passed，自指指标——仅作诊断参考）" in text  # 2026-10-05 P0 口径
        assert "| AITester vs plain_llm | 8 | 6 | 4.1667 | 0.0412 | * |" in text

        # BH-FDR 章节落盘（单对比：q = 原始 p，拒绝 H0）
        assert "## 多重比较校正（BH-FDR）" in text
        assert "| AITester vs plain_llm | 0.0412 | 0.0412 | 是 |" in text

        # Bootstrap 章节落盘（差值均值 6/8=0.7500；CI 值为数值格式即可——
        # 边界桶的精确值由 TestBootstrapCI 的宽裕手算用例单独锁定）
        assert "## Bootstrap 95% 置信区间" in text
        assert re.search(r"\| AITester vs plain_llm \| 8 \| 0\.7500 \| [\d.]+ \| [\d.]+ \| 10000 \| 42 \|", text)

        # Cliff's δ 与数据来源章节
        assert "## 效应量对比（Cohen's d 与 Cliff's δ）" in text
        assert "## 数据来源" in text
        assert "- `benchmark_r2a.json`" in text

    def test_comparisons_dict_carries_r2_fields(self, tmp_path):
        """返回的 comparisons 列表携带 R2 字段（供实验分析/下游消费）。"""
        _write_batch(
            tmp_path,
            "benchmark_r2b.json",
            aitester_passed=[True] * 4 + [False] * 2,
            plain_llm_passed=[False] * 6,
        )
        comps = run_all_statistics(str(tmp_path), None)
        assert comps, "应至少产生一条对比"
        for comp in comps:
            for key in (
                "cliffs_delta",
                "cliffs_effect",
                "bootstrap_mean_diff",
                "bootstrap_ci_low",
                "bootstrap_ci_high",
                "bootstrap_n_resamples",
                "bootstrap_seed",
                "mcnemar_chi2",
                "mcnemar_p",
                "fdr_adjusted_p",
            ):
                assert key in comp


class TestBootstrapCI:
    """R2：配对差值均值的百分位法 bootstrap 95% CI（手算值断言）。"""

    def test_hand_computed_small_sample(self):
        """差值序列 [1,0,0,0,0]：bootstrap 重采样均值 = k/5，k ~ Binomial(5, 0.2)。

        手算（10000 次重采样）：
        - 2.5% 分位落在 k=0 桶（P(k=0)=0.328，累计质量远盖过 2.5%）→ 0.0；
        - 97.5% 分位落在 k=3 桶（累计至 k=2 为 0.942、至 k=3 为 0.993，
          两侧余量 ≥ 1.7 个百分点，远大于万分位采样噪声）→ 3/5 = 0.6；
        - 差值均值点估计 = 1/5 = 0.2。
        """
        A = _rows([True, False, False, False, False])
        B = _rows([False] * 5)
        mean, ci_low, ci_high, n_pairs = bootstrap_paired_diff_ci(A, B)
        assert n_pairs == 5
        assert mean == 0.2
        assert ci_low == 0.0
        assert ci_high == 0.6

    def test_degenerate_constant_diff(self):
        """全同差值（恒 +1 / 恒 −1）→ 每次重采样均值不变，CI 退化为点。"""
        assert bootstrap_paired_diff_ci(_rows([True] * 6), _rows([False] * 6)) == (1.0, 1.0, 1.0, 6)
        assert bootstrap_paired_diff_ci(_rows([False] * 6), _rows([True] * 6)) == (-1.0, -1.0, -1.0, 6)

    def test_fixed_seed_bitwise_reproducible(self):
        """同参数两次调用结果逐位一致（random.Random(seed) 独立实例，
        不受全局随机状态影响——报告可审计）。"""
        A = _rows([False] * 10)
        B = _rows([True, False] * 5)
        first = bootstrap_paired_diff_ci(A, B, n_resamples=500, seed=7)
        second = bootstrap_paired_diff_ci(A, B, n_resamples=500, seed=7)
        assert first == second
        # 点估计为负方向（AITester 全败、基线半过 → 差值均值 −0.5）
        assert first[0] == -0.5
        assert first[1] <= first[0] <= first[2]

    def test_insufficient_pairs_nan(self):
        """共同任务 < 2 → 全 nan（与 paired_t_test / cohens_d 同口径）。"""
        mean, ci_low, ci_high, n_pairs = bootstrap_paired_diff_ci(
            [{"task_id": "t1", "passed": True}], [{"task_id": "t1", "passed": False}]
        )
        assert n_pairs == 1
        assert all(math.isnan(v) for v in (mean, ci_low, ci_high))


class TestBatchesWhitelist:
    """R2：--batches 批次白名单过滤与"数据来源"审计清单。"""

    @staticmethod
    def _make_three_batches(tmp_path: Path) -> None:
        """w1/w2 为 synthetic，w3 为非 synthetic（examples）——w1 与 w2 的
        aitester 通过情况相反，便于断言"混入与否"。"""
        _write_batch(tmp_path, "benchmark_w1.json", aitester_passed=[True] * 5, plain_llm_passed=[False] * 5)
        _write_batch(tmp_path, "benchmark_w2.json", aitester_passed=[False] * 5, plain_llm_passed=[True] * 5)
        _write_batch(
            tmp_path,
            "benchmark_w3.json",
            dataset="examples",
            aitester_passed=[True] * 5,
            plain_llm_passed=[True] * 5,
        )

    def test_load_with_sources_whitelist_filters(self, tmp_path):
        """白名单只纳入指定文件；sources 返回实际加载（synthetic）的清单。"""
        self._make_three_batches(tmp_path)
        results, sources = load_experiment_results_with_sources(
            str(tmp_path), ["benchmark_w2.json", "benchmark_w3.json"]
        )
        # w3 为非 synthetic：即使被白名单指定也不纳入（_load_batch_file 过滤）
        assert sources == ["benchmark_w2.json"]
        # 仅 w2 数据进入：aitester 5 行全为失败（w1 的全通过数据被排除）
        assert len(results["aitester"]) == 5
        assert all(not r["passed"] for r in results["aitester"])

    def test_cli_batches_whitelist(self, tmp_path, monkeypatch):
        """--batches 白名单：报告只统计白名单内 synthetic 文件，
        数据来源清单与数据概览一致（审计口径）。"""
        self._make_three_batches(tmp_path)
        report = tmp_path / "report.md"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "statistical_analysis.py",
                "--results-dir",
                str(tmp_path),
                "--output",
                str(report),
                "--batches",
                "benchmark_w1.json,benchmark_w3.json",
            ],
        )
        stat_main()
        text = report.read_text(encoding="utf-8")
        # 白名单内且 synthetic 的 w1 纳入
        assert "- `benchmark_w1.json`" in text
        # 非 synthetic 的 w3 被过滤（不进统计也不进审计清单）
        assert "benchmark_w3.json" not in text
        # 白名单外的 w2 完全排除（glob 模式下会混入并稀释/翻转结论）
        assert "benchmark_w2.json" not in text
        # 数据概览：aitester 仅 w1 的 5 个任务（全通过）
        assert "| aitester | 5 | 5 | 100.0% |" in text

    def test_cli_without_batches_keeps_glob_behavior(self, tmp_path, monkeypatch):
        """未提供 --batches：递归 glob 全目录（历史行为），审计清单列出
        全部 synthetic 批次（w3 仍被 dataset 过滤）。"""
        self._make_three_batches(tmp_path)
        report = tmp_path / "report.md"
        monkeypatch.setattr(
            sys,
            "argv",
            ["statistical_analysis.py", "--results-dir", str(tmp_path), "--output", str(report)],
        )
        stat_main()
        text = report.read_text(encoding="utf-8")
        assert "- `benchmark_w1.json`" in text
        assert "- `benchmark_w2.json`" in text
        assert "benchmark_w3.json" not in text
        # glob 混批次：w1 + w2 共 10 个任务、5 个通过（历史口径不变）
        assert "| aitester | 10 | 5 | 50.0% |" in text


class TestCliffsDelta:
    """R2：配对差值符号版 Cliff's delta（非参数效应量）边界。"""

    def test_all_positive_diffs(self):
        """全正差值（AITester 全过、基线全败）→ δ = +1.0（large）。"""
        delta, n_pairs = cliffs_delta(_rows([True] * 6), _rows([False] * 6))
        assert delta == 1.0
        assert n_pairs == 6
        assert interpret_cliffs_delta(delta) == "large"

    def test_all_negative_diffs(self):
        """全负差值（AITester 全败、基线全过）→ δ = −1.0。"""
        delta, _ = cliffs_delta(_rows([False] * 6), _rows([True] * 6))
        assert delta == -1.0

    def test_zero_symmetric(self):
        """正负个数相等（2 正 2 负）→ δ = 0.0（negligible）。"""
        delta, n_pairs = cliffs_delta(_rows([True, True, False, False]), _rows([False, False, True, True]))
        assert delta == 0.0
        assert n_pairs == 4

    def test_zero_identical_groups(self):
        """两组逐任务结果完全一致（差值全 0）→ δ = 0.0。"""
        delta, _ = cliffs_delta(_rows([True, False, True, False]), _rows([True, False, True, False]))
        assert delta == 0.0

    def test_partial_overlap(self):
        """部分 task_id 重叠（3/5 公共）时按公共集计算：公共对差值
        [1, 1, -1] → δ = (2−1)/3。"""
        delta, n_pairs = cliffs_delta(_rows([True, True, False, True, False]), _rows([False, False, True]))
        assert n_pairs == 3
        assert delta == pytest.approx(1 / 3)

    def test_insufficient_pairs_nan(self):
        """共同任务 < 2 → (nan, 1)（与 cohens_d 同口径）。"""
        delta, n_pairs = cliffs_delta([{"task_id": "t1", "passed": True}], [{"task_id": "t1", "passed": False}])
        assert math.isnan(delta)
        assert n_pairs == 1
        assert interpret_cliffs_delta(delta) == "unknown"


class TestM1Aggregation:
    """R2：analyze_results 的 M1 指标聚合（None 不计入分母）。"""

    def test_none_excluded_from_denominator(self):
        """None 行不计入任何指标的 observed/均值：detection 可测 2 个
        （均值 (1.0+0.5)/2=0.75），repair 仅 1 个可测（均值 1.0）。"""
        details = [
            {
                "task_id": "t1",
                "passed": True,
                "detection_rate": 1.0,
                "repair_rate": 1.0,
                "false_fix_rate": 0.0,
                "test_error_rate": 0.0,
            },
            {
                "task_id": "t2",
                "passed": False,
                "detection_rate": 0.5,
                "repair_rate": None,
                "false_fix_rate": None,
                "test_error_rate": None,
            },
            {"task_id": "t3", "passed": True},  # 全字段缺失（旧 JSON 行）
        ]
        m1 = _m1_metrics_aggregate(details)
        assert m1["available"] is True
        assert m1["total_tasks"] == 3
        assert m1["metrics"]["detection_rate"] == {"observed": 2, "mean": 0.75}
        assert m1["metrics"]["repair_rate"] == {"observed": 1, "mean": 1.0}
        assert m1["metrics"]["false_fix_rate"] == {"observed": 1, "mean": 0.0}
        assert m1["metrics"]["test_error_rate"] == {"observed": 1, "mean": 0.0}

    def test_all_none_not_available(self):
        """无可测任务（全 None / 无字段）→ available=False（渲染层跳过章节）。"""
        m1 = _m1_metrics_aggregate([{"task_id": "t1", "passed": True, "detection_rate": None}])
        assert m1["available"] is False
        assert m1["metrics"]["detection_rate"]["mean"] is None

    def test_render_section_with_and_without_m1_fields(self):
        """携带 M1 字段时渲染"## M1 指标汇总"章节；旧 JSON（无字段）时
        章节缺席——历史输出结构零变化（只追加，不改写）。"""
        details_with_m1 = [
            {
                "task_id": f"t{i}",
                "passed": i < 2,
                "detection_rate": 1.0 if i < 2 else None,
                "repair_rate": None,
                "false_fix_rate": 0.0,
                "test_error_rate": None,
            }
            for i in range(4)
        ]
        details_without_m1 = [{"task_id": f"t{i}", "passed": i < 2} for i in range(4)]

        def _render(details: list[dict]) -> str:
            data = {"dataset": "synthetic", "results": {"aitester": {"details": details}}}
            return render_markdown(build_analysis(data), "benchmark_x.json")

        text_with = _render(details_with_m1)
        assert "## M1 指标汇总（R2，None 不计入分母）" in text_with
        assert "| aitester | 2/4 | 1.0（n=2） | — | 0.0（n=4） | — |" in text_with

        text_without = _render(details_without_m1)
        assert "## M1 指标汇总" not in text_without
        # 核心指标对比表（历史章节）不受影响
        assert "## 核心指标对比" in text_without
