#!/usr/bin/env python3
"""Z 轮（2026-10-19 第三方全量静态审查）统计口径回归锁。

对应审查报告 F01（P1，BH q 公式）、F02（P1，配对分母）、F20（P2，匹配口径）
及 q 值涟漪。本文件锁定四组行为（**旧实现在每组都会转红**）：

1. **F01 标准 BH**：`bh_fdr_correct` 必须是
   q_(i) = min(1, min_{j≥i} m·p_(j)/j)。报告 §B 三组可手算反例在旧实现
   （无拒绝 q=原 p；有拒绝按最大被拒绝 p×名次回填）下分别为
   ``[0.01, 0.02, 1]`` / ``[0.03, 0.20, 0.30]`` / ``[0.0067, 0.0133, 0.02]``，
   本文件断言旧值必然失败。
2. **F01 主批 q 真值**：三种子主批 detection 三比较的原始 p 由三批原始
   JSON **独立重建**（不 import 项目加载器 / 不 import mcnemar_test，只用
   stdlib + erfc 手写 2×2 连续性校正），标准 BH q 锁定为
   ``1.767215e-25 / 4.265758e-12 / 1.811017e-7``；并锁定 pooled 报告、
   EVALUATION_SCOPE 的引用值已同步。
3. **F02 配对分母**：`sensitivity_bounds` 的 base 行分子/分母必须同源
   （`_pair_by_task` 配对列表）。最小反例：A 臂某任务 None、B 臂该任务阳性，
   旧实现把 B 的该阳性计入分子 → base diff=-0.5，新实现 = 0.0；真实主批
   aitester vs plain_llm_df base 锁定 n=240、A/B 阳性 38/106、
   risk_diff=-0.283333（旧整臂分子 -0.329167），worst/best 填充后 n=261、
   -0.302682 / -0.222222。
4. **E6/A1 家族 q 涟漪 + F20 匹配口径**：E6 control + A1 消融三对比
   （m=3 家族）原始 p ``[0.4795, 3.814e-5, 0.0133]`` → 标准 q
   ``[0.4795, 1.144e-4, 1.999e-2]``，BASELINE.yaml 已同步；F20 的
   strict/loose 匹配计数（29/25/0 与 62/55/0，互补 38/215=17.67% 与
   38/185=20.54%）由原始 JSON 独立复算锁定。

真实工件缺失时相关用例 `pytest.skip`（精简 CI 环境）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from experiments.repair_ceiling_analysis import sensitivity_bounds
from experiments.statistical_analysis import bh_fdr_correct

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_MAIN_BATCH = PROJECT_ROOT / "experiments" / "results" / "main_batch"
_MAIN_FILES = (
    "benchmark_synthetic_20261006_140906.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_164357.json",
)
_E6_DIR = PROJECT_ROOT / "experiments" / "results" / "e6_a1_batches"
_E6_CONTROL = _E6_DIR / "e6_control_seed42" / "benchmark_synthetic_20261009_181758.json"
_A1_STRIP = _E6_DIR / "a1_strip_seed42" / "benchmark_synthetic_20261009_180655.json"
_POOLED_REPORT = _MAIN_BATCH / "statistical_report_3seed_pooled.md"
_CEILING_REPORT = _MAIN_BATCH / "repair_ceiling_report.md"
_BASELINE = PROJECT_ROOT / "BASELINE.yaml"
_EVAL_SCOPE = PROJECT_ROOT / "docs" / "EVALUATION_SCOPE.md"

_MAIN_READY = all((_MAIN_BATCH / f).exists() for f in _MAIN_FILES)
_E6_READY = _E6_CONTROL.exists() and _A1_STRIP.exists()
_ready_main = pytest.mark.skipif(not _MAIN_READY, reason="三种子主批原始批次工件不在工作树")
_ready_e6 = pytest.mark.skipif(not _E6_READY, reason="E6/A1 归档批次工件不在工作树")


# ─── 独立统计工具（不 import 项目统计实现，保证"真值"独立可复算） ─────────


def _chi2_sf_df1(chi2: float) -> float:
    """df=1 卡方生存函数：P(X > x) = erfc(sqrt(x/2))（纯 math，无 scipy）。"""
    return math.erfc(math.sqrt(chi2 / 2.0))


def _mcnemar_from_flags(a: dict, b: dict) -> tuple[int, int, int, float, float]:
    """独立 2×2 McNemar（连续性校正）：返回 (n_common, n01, n10, chi2, p)。

    a/b 为 {task_key: detection_rate}；None 不进入分母（M1 口径），
    只用双方均可测（0/1）的共同任务。
    """
    keys = [k for k in a.keys() & b.keys() if a[k] in (0, 1) and b[k] in (0, 1)]
    n01 = sum(1 for k in keys if a[k] == 1 and b[k] == 0)
    n10 = sum(1 for k in keys if a[k] == 0 and b[k] == 1)
    if n01 + n10 == 0:
        return len(keys), n01, n10, 0.0, 1.0
    chi2 = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
    return len(keys), n01, n10, chi2, _chi2_sf_df1(chi2)


def _load_arm_rows(paths: tuple[Path, ...]) -> dict[str, dict]:
    """从原始批次 JSON 逐行重建 {arm: {(seed, task_id): 完整行}}。

    与项目加载器同构的种子分层键（(seed, task_id)，等价于加载器加
    ``s<seed>__`` 前缀），但**不复用项目代码**——独立的真值来源。
    """
    arms: dict[str, dict] = {}
    for path in paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        seed = obj["seed"]
        for arm, block in obj["results"].items():
            target = arms.setdefault(arm, {})
            for row in block.get("details", []):
                # 注入种子便于后续按 (pattern, difficulty, seed) 复算匹配键
                target[(seed, row.get("task_id"))] = {**row, "_seed": seed}
    return arms


def _load_arm_flags(paths: tuple[Path, ...], field: str = "detection_rate") -> dict[str, dict]:
    """同 `_load_arm_rows`，但只取单字段（供 McNemar 独立复算）。"""
    return {arm: {key: row.get(field) for key, row in rows.items()} for arm, rows in _load_arm_rows(paths).items()}


def _standard_bh(p_values: list[float], alpha: float = 0.05) -> tuple[list[float], list[bool]]:
    """独立标准 BH 实现（测试内对照真值，与被测实现相互独立）。"""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [float("nan")] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, m * p_values[i] / rank)
        q[i] = min(1.0, running)
    reject_rank = 0
    for rank in range(1, m + 1):
        if p_values[order[rank - 1]] <= rank / m * alpha:
            reject_rank = rank
    rejected = [False] * m
    for rank in range(1, reject_rank + 1):
        rejected[order[rank - 1]] = True
    return q, rejected


# ─── F01：标准 BH 反例与不变量 ────────────────────────────────────────────


class TestBHStandardCounterexamples:
    """审查报告 §B 三组可手算反例（旧实现全部转红）。"""

    def test_counterexample_1_mixed_rejections(self):
        """[0.01, 0.02, 0.20] → 标准 q=[0.03, 0.03, 0.20]（旧：[0.01, 0.02, 1]）。"""
        q_values, rejected = bh_fdr_correct([0.01, 0.02, 0.20])
        assert q_values == pytest.approx([0.03, 0.03, 0.20], rel=1e-12)
        assert rejected == [True, True, False]

    def test_counterexample_2_q_independent_of_rejection(self):
        """[0.03, 0.20, 0.30] → 标准 q=[0.09, 0.30, 0.30]，全不拒绝。

        旧实现给 [0.03, 0.20, 0.30] 且 rejected 全 False，首项 q<alpha——
        "q 与拒绝标记矛盾"的原始反例；标准 q 只由 p 排序位置决定。
        """
        q_values, rejected = bh_fdr_correct([0.03, 0.20, 0.30])
        assert q_values == pytest.approx([0.09, 0.30, 0.30], rel=1e-12)
        assert rejected == [False, False, False]
        # 标准 BH 下"拒绝 ⇔ q ≤ alpha"必须一致（旧实现此处冲突）
        assert [qi <= 0.05 for qi in q_values] == rejected

    def test_counterexample_3_all_rejections(self):
        """[0.001, 0.005, 0.02] → 标准 q=[0.003, 0.0075, 0.02]（旧：[0.0067, 0.0133, 0.02]）。"""
        q_values, rejected = bh_fdr_correct([0.001, 0.005, 0.02])
        assert q_values == pytest.approx([0.003, 0.0075, 0.02], rel=1e-12)
        assert rejected == [True, True, True]

    def test_q_values_do_not_depend_on_alpha(self):
        """q 只由 p 决定：alpha 变化只应改变 rejected，不改变 q。"""
        p_values = [0.01, 0.02, 0.20]
        q_a, rejected_a = bh_fdr_correct(p_values, alpha=0.05)
        q_b, rejected_b = bh_fdr_correct(p_values, alpha=0.10)
        assert q_a == pytest.approx(q_b, rel=1e-12)
        # alpha 提高后拒绝集单调扩大（标准 step-up 性质）
        assert all(ra is False or rb is True for ra, rb in zip(rejected_a, rejected_b, strict=True))

    def test_monotone_bounded_and_nan_preserved(self):
        """标准 BH 不变量：q ≥ p、q ≤ 1；nan 项 q=nan 且不参与排序。"""
        p_values = [0.5, 0.001, float("nan"), 0.02]
        q_values, rejected = bh_fdr_correct(p_values)
        assert math.isnan(q_values[2])
        valid = [i for i in range(len(p_values)) if i != 2]
        for i in valid:
            assert p_values[i] <= q_values[i] + 1e-12, (p_values[i], q_values[i])
            assert q_values[i] <= 1.0
        assert rejected[2] is False
        # 与独立实现交叉验证（nan 跳过后的同序结果）
        q_ref, rej_ref = _standard_bh([p_values[i] for i in valid])
        assert [q_values[i] for i in valid] == pytest.approx(q_ref, rel=1e-12)
        assert [rejected[i] for i in valid] == rej_ref


# ─── F01：主批 detection 三比较 p/q 真值（从原始 JSON 独立重建） ──────────


@_ready_main
class TestMainBatchQTruth:
    """主批三比较：p 由原始 JSON 独立重建，q 与独立标准 BH 交叉验证。"""

    _COMPARISONS = (
        ("plain_llm_df", "plain_llm"),
        ("aitester", "plain_llm_df"),
        ("aitester", "plain_llm"),
    )
    # 审查报告 §B 引用的三种子主批 p 值（独立重建验证）
    _EXPECTED_P = (5.890715e-26, 2.843839e-12, 1.811017e-07)
    # 标准 BH q 真值（独立复算验证）
    _EXPECTED_Q = (1.767215e-25, 4.265758e-12, 1.811017e-07)
    _EXPECTED_CELLS = ((113, 0), (12, 80), (37, 3))
    _EXPECTED_N = (261, 240, 240)

    def _flags(self) -> dict[str, dict]:
        return _load_arm_flags(tuple(_MAIN_BATCH / f for f in _MAIN_FILES))

    def test_rebuild_p_from_raw_json(self):
        arms = self._flags()
        for (arm_a, arm_b), cells, expected_p, expected_n in zip(
            self._COMPARISONS, self._EXPECTED_CELLS, self._EXPECTED_P, self._EXPECTED_N, strict=True
        ):
            n_common, n01, n10, _chi2, p_value = _mcnemar_from_flags(arms[arm_a], arms[arm_b])
            assert (n01, n10) == cells, (arm_a, arm_b)
            assert n_common == expected_n, (arm_a, arm_b)
            assert p_value == pytest.approx(expected_p, rel=1e-5), (arm_a, arm_b, p_value)

    def test_standard_bh_q_truth(self):
        arms = self._flags()
        p_values = [_mcnemar_from_flags(arms[arm_a], arms[arm_b])[4] for arm_a, arm_b in self._COMPARISONS]
        q_values, rejected = bh_fdr_correct(p_values)
        assert q_values == pytest.approx(list(self._EXPECTED_Q), rel=1e-12)
        assert rejected == [True, True, True]
        # 与独立实现交叉验证（拒绝集合与 q 均一致）
        q_ref, rejected_ref = _standard_bh(p_values)
        assert q_values == pytest.approx(q_ref, rel=1e-12)
        assert rejected == rejected_ref

    def test_pooled_report_quotes_recomputed_q(self):
        """pooled 报告主表 q 列已更新，且保留日期化勘误（不静默改历史）。"""
        text = _POOLED_REPORT.read_text(encoding="utf-8")
        assert "1.8e-25" in text  # df–plain 标准 q（旧 6.0e-08）
        assert "4.3e-12" in text  # aitester–df 标准 q（旧 1.2e-07）
        assert "2026-10-19 勘误" in text
        for token in ("plain_llm_df vs plain_llm", "aitester vs plain_llm_df", "aitester vs plain_llm"):
            assert token in text
        # 勘误节必须同时记录旧值（历史可审计）
        assert "6.0e-08" in text and "1.2e-07" in text


# ─── F02：sensitivity_bounds 配对分子 ─────────────────────────────────────


class TestSensitivityBoundsPairedNumerator:
    """base 行分子/分母必须取自同一共同配对总体（旧实现整臂分子 → 转红）。"""

    @staticmethod
    def _rows(flags_a: list[int | None], flags_b: list[int]) -> dict[str, list[dict]]:
        rows_a = [{"task_id": f"t{i}", "detection_rate": v} for i, v in enumerate(flags_a)]
        rows_b = [{"task_id": f"t{i}", "detection_rate": v} for i, v in enumerate(flags_b)]
        return {"aitester": rows_a, "plain_llm": rows_b, "plain_llm_df": rows_b}

    def test_minimal_counterexample_none_row_on_baseline_positive(self):
        """A=t3 None、B=t3 阳性：旧实现 base diff=-0.5，新实现 0.0。

        旧实现：n_common=2（t1/t2），sum_a=整臂 1、sum_b=整臂 2 → (1−2)/2=−0.5；
        正确配对：共同集内两臂阳性各 1 → (1−1)/2=0.0。
        """
        bounds = sensitivity_bounds(self._rows([1, 0, None], [1, 0, 1]))
        entry = next(e for e in bounds if "plain_llm_df" in e["comparison"])
        scenarios = {row["scenario"]: row for row in entry["rows"]}
        base = scenarios["base"]
        assert base["n_common"] == 2
        assert (base["sum_a"], base["sum_b"]) == (1, 1)  # 配对分子，而非 (1, 2)
        assert base["risk_diff"] == pytest.approx(0.0)
        assert scenarios["worst(None→0)"]["risk_diff"] == pytest.approx(-1.0 / 3.0)
        assert scenarios["best(None→1)"]["risk_diff"] == pytest.approx(0.0)
        # 双界不变式（风险差口径 worst ≤ best）
        assert scenarios["worst(None→0)"]["risk_diff"] <= scenarios["best(None→1)"]["risk_diff"]

    def test_risk_diff_always_equals_paired_sums_over_n(self):
        """结构不变式：任意情形 risk_diff == (sum_a − sum_b)/n_common（同源）。"""
        bounds = sensitivity_bounds(self._rows([1, None, 0, 1, None], [0, 1, 1, 0, 1]))
        for entry in bounds:
            for row in entry["rows"]:
                expected = (row["sum_a"] - row["sum_b"]) / row["n_common"]
                assert row["risk_diff"] == pytest.approx(expected)
                assert 0 <= row["sum_a"] <= row["n_common"]
                assert 0 <= row["sum_b"] <= row["n_common"]

    def test_real_main_batch_base_rows_paired(self):
        """真实主批：base 分子=配对阳性（不是整臂阳性）。"""
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, _ = load_experiment_results_with_sources(
            str(_MAIN_BATCH), list(_MAIN_FILES), allow_schema_mixed=False, pool_seeds=True
        )
        bounds = sensitivity_bounds(results)
        by_comp = {entry["comparison"]: {row["scenario"]: row for row in entry["rows"]} for entry in bounds}
        df_entry = by_comp["aitester vs plain_llm_df"]
        base = df_entry["base"]
        assert base["n_common"] == 240
        assert (base["sum_a"], base["sum_b"]) == (38, 106)  # 旧整臂分子是 (38, 117)
        assert base["risk_diff"] == pytest.approx(-68 / 240)  # -0.283333...，旧 -0.329167
        worst = df_entry["worst(None→0)"]
        best = df_entry["best(None→1)"]
        assert (worst["n_common"], worst["sum_a"], worst["sum_b"]) == (261, 38, 117)
        assert worst["risk_diff"] == pytest.approx(-79 / 261)  # -0.302682
        assert (best["n_common"], best["sum_a"], best["sum_b"]) == (261, 59, 117)
        assert best["risk_diff"] == pytest.approx(-58 / 261)  # -0.222222

        plain_entry = by_comp["aitester vs plain_llm"]
        assert plain_entry["base"]["risk_diff"] == pytest.approx(34 / 240)  # +0.141667
        assert plain_entry["worst(None→0)"]["risk_diff"] == pytest.approx(34 / 261)  # +0.130268
        assert plain_entry["best(None→1)"]["risk_diff"] == pytest.approx(55 / 261)  # +0.210728
        # 双界不变式在真实数据上成立
        for entry in bounds:
            scenarios = {row["scenario"]: row for row in entry["rows"]}
            assert scenarios["worst(None→0)"]["risk_diff"] <= scenarios["best(None→1)"]["risk_diff"]


# ─── F02：repair_ceiling_report.md 已重生成且含日期化勘误 ─────────────────


@_ready_main
class TestRepairCeilingReportConsistency:
    def test_report_has_20261019_erratum_and_paired_base_row(self):
        assert _CEILING_REPORT.exists(), _CEILING_REPORT
        text = _CEILING_REPORT.read_text(encoding="utf-8")
        assert "2026-10-19 勘误" in text
        assert "−0.283333" in text
        # base 行 B 阳性 = 配对共同集 106（旧整臂 117 只允许出现在 worst 行）
        base_line = next(
            line for line in text.splitlines() if line.startswith("| aitester vs plain_llm_df") and "| base |" in line
        )
        assert "| 240 | 38 | 106 | -0.283 |" in base_line
        # 报告结构与漏斗章节不得回退
        assert "## 1. 修复通道漏斗" in text
        assert "## 3. 21 行 detection=None 敏感性双界" in text
        assert text.count("worst(None→0)") == 2
        assert text.count("best(None→1)") == 2


# ─── E6/A1 家族 q 涟漪 + BASELINE.yaml 同步 ───────────────────────────────


@_ready_e6
class TestE6A1FamilyQRipple:
    """E6 control + A1 消融 = 同一 m=3 BH 家族；BASELINE 已按标准 BH 重算。"""

    def _p_values(self) -> tuple[float, float, float]:
        e6_arms = _load_arm_flags((_E6_CONTROL,))
        strip_arms = _load_arm_flags((_A1_STRIP,))
        p_a1 = _mcnemar_from_flags(e6_arms["aitester"], strip_arms["aitester"])[4]
        p_e6_df = _mcnemar_from_flags(e6_arms["aitester"], e6_arms["plain_llm_df"])[4]
        p_e6_pl = _mcnemar_from_flags(e6_arms["aitester"], e6_arms["plain_llm"])[4]
        return p_a1, p_e6_df, p_e6_pl

    def test_rebuild_family_p_and_standard_q(self):
        p_a1, p_e6_df, p_e6_pl = self._p_values()
        assert p_a1 == pytest.approx(4.795001221869535e-01, rel=1e-6)  # A1 消融
        assert p_e6_df == pytest.approx(3.8144777827131046e-05, rel=1e-6)  # E6 vs plain_llm_df
        assert p_e6_pl == pytest.approx(1.3328328780817557e-02, rel=1e-6)  # E6 vs plain_llm
        q_values, rejected = bh_fdr_correct([p_a1, p_e6_df, p_e6_pl])
        # 标准 BH q：A1=0.4795、E6-df=1.144343e-4、E6-pl=1.999249e-2
        assert q_values == pytest.approx(
            [4.795001221869535e-01, 1.1443433348139314e-04, 1.9992493171226335e-02], rel=1e-6
        )
        assert rejected == [False, True, True]
        q_ref, _ = _standard_bh([p_a1, p_e6_df, p_e6_pl])
        assert q_values == pytest.approx(q_ref, rel=1e-12)

    def test_baseline_yaml_quotes_recomputed_q_with_erratum(self):
        text = _BASELINE.read_text(encoding="utf-8")
        assert "a1_bh_fdr_q: 0.4795" in text
        assert "e6_df_bh_fdr_q: 1.144e-4" in text
        assert "2026-10-19 勘误（Z 轮第三方审查 F01）" in text
        # 旧非标准 q 不再作为统计字段值出现
        assert "a1_bh_fdr_q: 1.0000" not in text
        assert "e6_df_bh_fdr_q: 0.0067" not in text


# ─── F20：严格/宽松匹配口径与文档一致性 ──────────────────────────────────


@_ready_main
class TestF20MatchCaliber:
    """strict=pattern×difficulty×seed、loose=pattern；两组是不同总体、非互补对照。"""

    @staticmethod
    def _pattern(r: dict) -> str | None:
        return (r.get("task_metadata") or {}).get("pattern_name")

    @staticmethod
    def _difficulty(r: dict) -> int | None:
        return (r.get("task_metadata") or {}).get("difficulty")

    def _treat_rows(self) -> list[dict]:
        arms = _load_arm_rows(tuple(_MAIN_BATCH / f for f in _MAIN_FILES))
        return list(arms["aitester"].values())

    def _ref_success(self) -> tuple[set, set]:
        arms = _load_arm_rows(tuple(_MAIN_BATCH / f for f in _MAIN_FILES))
        strict_keys: set = set()
        loose_patterns: set = set()
        for (seed, _task_id), row in arms["plain_llm_df"].items():
            if row.get("passed") is not True:
                continue
            strict_keys.add((self._pattern(row), self._difficulty(row), seed))
            loose_patterns.add(self._pattern(row))
        return strict_keys, loose_patterns

    @staticmethod
    def _summarize(rows: list[dict]) -> tuple[int, int, int]:
        measurable = [r for r in rows if r.get("detection_rate") is not None]
        detected = sum(1 for r in measurable if r.get("detection_rate") == 1.0)
        return len(rows), len(measurable), detected

    def test_strict_and_loose_counts_from_raw_json(self):
        rows = self._treat_rows()
        strict_keys, loose_patterns = self._ref_success()
        strict = [r for r in rows if (self._pattern(r), self._difficulty(r), r["_seed"]) in strict_keys]
        loose = [r for r in rows if self._pattern(r) in loose_patterns]
        assert self._summarize(strict) == (29, 25, 0)  # 严格键 29 行 / 25 可测 / 0 检出
        assert self._summarize(loose) == (62, 55, 0)  # 宽松键 62 行 / 55 可测 / 0 检出
        # 互补集：strict 的互补是 232 行/215 可测（38/215=17.67%）；loose 的
        # 互补是 199 行/185 可测（38/185=20.54%）——两者行数不同，非互补对照。
        strict_comp = [r for r in rows if (self._pattern(r), self._difficulty(r), r["_seed"]) not in strict_keys]
        loose_comp = [r for r in rows if self._pattern(r) not in loose_patterns]
        assert self._summarize(strict_comp) == (232, 215, 38)
        assert self._summarize(loose_comp) == (199, 185, 38)
        strict_comp_ratio = 38 / 215
        loose_comp_ratio = 38 / 185
        assert strict_comp_ratio == pytest.approx(0.176744, rel=1e-4)
        assert loose_comp_ratio == pytest.approx(0.205405, rel=1e-4)

    def test_evaluation_scope_strict_loose_and_reference_q(self):
        """EVALUATION_SCOPE 已写全三字段键、明确非互补，且引用标准 q。"""
        text = _EVAL_SCOPE.read_text(encoding="utf-8")
        assert "pattern×difficulty×seed" in text
        assert "38/215=17.67%" in text
        assert "38/185=20.54%" in text
        assert "不是互补对照" in text
        assert "BH-FDR q=1.767e-25" in text  # C1a
        assert "BH-FDR q=4.266e-12" in text  # C3
        assert "已清空（零豁免）" in text  # F17 引用核验状态
