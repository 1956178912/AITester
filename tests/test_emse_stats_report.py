"""EMSE 统计补口工具（experiments/emse_stats_report.py）回归测试。

覆盖（全部纯 stdlib + 既有项目函数 / 零 LLM / 零网络 / 不外呼网络；
仅 `--corrected-repair` 才有本地 pytest 子进程，本文件不触发该路径）：

- 闭式 MDE 的单调性：对 n 单调递减、对目标 δ 单调递增（经 required_pairs
  往返）——"样本量越大 / 目标差异越大 ⇒ 可检出下限越宽松"的方向守卫；
- bootstrap CI 在固定 seed 下逐位可复现（同参数两次调用输出完全相同）；
- 报告与 JSON 落盘、必需列头存在、二者数字同源；
- `None` 口径：不可测行**剔除而非记 0**（分母与配对数同时收缩）；
- 批次文件缺失时**显式报错**（不静默降级为少数批次）；
- 真实工件（1.4GB 级 results 目录）在场时的回归锁定，缺席自动 skip。
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from experiments.emse_optimization import mde_paired_pp, power_at_delta, required_pairs
from experiments.emse_stats_report import (
    _ARMS,
    _RP02_DEFAULT_BATCHES,
    cost_block,
    endpoint_point,
    load_pooled_rows,
    main,
    mde_block,
    mde_sigma_closed_form_pp,
    paired_diff_ci,
    resolve_batch_files,
    sigma_d2_paired,
)
from experiments.statistical_analysis import bootstrap_paired_diff_ci

_REAL_RESULTS_DIR = Path(__file__).resolve().parents[1] / "experiments" / "results" / "main_batch"
# R-P0-2 三种子合并的定案配对结构（statistical_report_3seed_pooled.md：37/3、12/80、113/0）
_REAL_EXPECTED = {
    ("aitester", "plain_llm"): (240, 37, 3),
    ("aitester", "plain_llm_df"): (240, 12, 80),
    ("plain_llm_df", "plain_llm"): (261, 113, 0),
}


# ─── 夹具：两批次 × 三臂的小工件（字段口径与真实行同构） ───────────────────
def _row(
    task_id: str,
    detection: float | None,
    repair: float | None,
    false_fix: float | None,
    passed: bool,
    tokens: float,
) -> dict[str, Any]:
    """构造一条结果行（字段名与真实批次 JSON 的 details 行一致）。"""
    return {
        "task_id": task_id,
        "detection_rate": detection,
        "repair_rate": repair,
        "false_fix_rate": false_fix,
        "passed": passed,
        "token_usage": {
            "input_tokens": tokens / 3,
            "output_tokens": tokens / 3,
            "total_tokens": tokens,
            "llm_calls": 1,
        },
        "patch": "",
        "task_metadata": {"test_cases": ""},
    }


def _fixture_arms() -> dict[str, list[dict[str, Any]]]:
    """三臂夹具：含 None 行（task_0007）、0 token 行、passed 真/假两态。

    配对结构（detection）：ai vs llm n_common=7（任务 7 因 ai=None 退出）、
    n10/n01=2/0；ai vs df n_common=7、n10/n01=0/3；df vs llm n_common=8、n10/n01=5/0。
    """
    ai = [
        _row("task_0000", 1.0, 0.0, 1.0, True, 300.0),
        _row("task_0001", 1.0, 0.0, 1.0, True, 400.0),
        _row("task_0002", 1.0, 1.0, 0.0, True, 500.0),
        _row("task_0003", 0.0, 0.0, 0.0, True, 600.0),
        _row("task_0004", 0.0, 0.0, 1.0, False, 700.0),
        _row("task_0005", 0.0, 0.0, 0.0, False, 800.0),
        _row("task_0006", 0.0, 0.0, 0.0, False, 0.0),  # 记账为 0 → 成本口径剔除
        _row("task_0007", None, None, None, False, 900.0),  # 不可测行（M1 None 口径）
    ]
    llm = [
        _row("task_0000", 1.0, 0.0, 1.0, True, 100.0),
        _row("task_0001", 0.0, 0.0, 0.0, False, 110.0),
        _row("task_0002", 0.0, 0.0, 0.0, False, 120.0),
        _row("task_0003", 0.0, 0.0, 1.0, True, 130.0),
        _row("task_0004", 0.0, 0.0, 1.0, True, 140.0),
        _row("task_0005", 0.0, 0.0, 1.0, True, 150.0),
        _row("task_0006", 0.0, 0.0, 1.0, False, 160.0),
        _row("task_0007", 0.0, 0.0, 0.0, False, 170.0),
    ]
    df = [
        _row("task_0000", 1.0, 0.0, 0.0, True, 200.0),
        _row("task_0001", 1.0, 0.0, 0.0, True, 210.0),
        _row("task_0002", 1.0, 0.0, 1.0, False, 220.0),
        _row("task_0003", 1.0, 0.0, 1.0, False, 230.0),
        _row("task_0004", 1.0, 0.0, 1.0, False, 240.0),
        _row("task_0005", 1.0, 0.0, 1.0, False, 250.0),
        _row("task_0006", 0.0, 0.0, 0.0, False, 260.0),
        _row("task_0007", 0.0, 0.0, 0.0, False, 270.0),
    ]
    return {"aitester": ai, "plain_llm": llm, "plain_llm_df": df}


def _write_batch(dir_path: Path, name: str, seed: int, arms: dict[str, list[dict[str, Any]]]) -> Path:
    """写一份最小批次 JSON（结构与真实工件同形）。"""
    payload = {
        "timestamp": "2026-10-06T14:09:06",
        "dataset": "synthetic",
        "seed": seed,
        "provenance": {"seed": seed},
        "results": {arm: {"details": rows} for arm, rows in arms.items()},
    }
    path = dir_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    """单批次夹具目录（批次名与 R-P0-2 默认名不同 → 测试显式传 --batches）。"""
    _write_batch(tmp_path, "benchmark_synthetic_20261006_140906.json", 42, _fixture_arms())
    return tmp_path


@pytest.fixture
def fixture_rows(fixture_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """夹具池化后的行（走真实加载器：种子前缀 + None 保留）。"""
    files = resolve_batch_files(fixture_dir, "benchmark_synthetic_20261006_140906.json")
    rows, _meta = load_pooled_rows(fixture_dir, files)
    return rows


# ─── (i) 闭式 MDE 单调性：对 n 递减、对目标 δ 递增 ────────────────────────
class TestClosedFormMdeMonotonicity:
    def test_mde_decreases_with_n(self) -> None:
        """样本量增大 ⇒ MDE 严格下降（同一不一致结构 σ_d²=0.25）。"""
        sigma2 = 0.25
        mdes = [mde_sigma_closed_form_pp(n, sigma2) for n in (10, 25, 50, 100, 400, 1000)]
        assert all(mde is not None for mde in mdes)
        values = [float(mde) for mde in mdes if mde is not None]
        assert all(later < earlier for earlier, later in pairwise(values))
        # 与 sqrt(1/n) 标度一致（闭式性质，非硬编码定案值）
        assert values[0] / values[-1] == pytest.approx((1000 / 10) ** 0.5, rel=1e-9)

    def test_mde_increases_with_sigma_and_is_none_without_discordance(self) -> None:
        """不一致结构越大 ⇒ MDE 越大；无结构（σ_d²=0）/ 零 n ⇒ None（不臆造）。"""
        assert mde_sigma_closed_form_pp(100, 0.4) > mde_sigma_closed_form_pp(100, 0.1)
        assert mde_sigma_closed_form_pp(100, 0.0) is None
        assert mde_sigma_closed_form_pp(0, 0.1) is None

    def test_target_delta_monotonicity_via_required_pairs_round_trip(self) -> None:
        """目标 δ 越大 ⇒ 给定功效下所需 n 越小；反解回 MDE 随目标 δ 单调递增。

        往返一致性由项目既有 `required_pairs` / `mde_paired_pp`（ψ 口径同式）锁定：
        `mde_paired_pp(required_pairs(δ, ψ), ψ) ≲ δ`（ceil 取整 ⇒ 略小于目标 δ）。
        """
        psi = 5 / 35
        targets = (5.0, 8.0, 12.0, 20.0)
        n_required = [required_pairs(delta, psi) for delta in targets]
        assert all(n is not None for n in n_required)
        ns = [int(n) for n in n_required if n is not None]
        assert all(later < earlier for earlier, later in pairwise(ns))
        recovered = [mde_paired_pp(n, psi) for n in ns]
        assert all(mde is not None for mde in recovered)
        values = [float(mde) for mde in recovered if mde is not None]
        # 目标 δ 越大 ⇒ 同一功效水平下的 MDE 越大（单调递增）
        assert all(later > earlier for earlier, later in pairwise(values))
        for target, value in zip(targets, values, strict=True):
            # ceil 取整只会让可实现 MDE ≤ 目标 δ；n 极小时（如目标 20pp → n=8）
            # 取整造成的相对下滑最大（实测 ≈6%），故用相对容差而非绝对容差
            assert value <= target + 1e-9
            assert value >= target * 0.85
        # 功效随目标 δ 递增（同 n、同 ψ）
        powers = [power_at_delta(delta, ns[0], psi) for delta in targets]
        assert all(p is not None for p in powers)
        power_values = [float(p) for p in powers if p is not None]
        assert all(later > earlier for earlier, later in pairwise(power_values))

    def test_sigma_d2_matches_project_formula(self) -> None:
        """σ_d² 现算式 == 项目公式 p_a + p_b − δ² − 2·p11（逐位）。"""
        p_a, p_b, p11 = 0.158333, 0.016667, 0.004167
        delta = p_a - p_b
        assert sigma_d2_paired(p_a, p_b, p11) == pytest.approx(p_a + p_b - delta * delta - 2 * p11, rel=1e-15)


# ─── (ii) bootstrap CI 固定 seed 可复现 ──────────────────────────────────
class TestBootstrapDeterminism:
    def test_paired_diff_ci_identical_across_two_calls(self, fixture_rows) -> None:
        """同参数两次调用输出逐位相同（random.Random(seed) 独立实例）。"""
        first = paired_diff_ci(fixture_rows["aitester"], fixture_rows["plain_llm"], "detection_rate")
        second = paired_diff_ci(fixture_rows["aitester"], fixture_rows["plain_llm"], "detection_rate")
        assert first == second
        assert first["n_pairs"] == 7
        # 报告口径为 4 位小数（JSON 同源）
        assert first["diff_pp"] == pytest.approx(round(100.0 * 2 / 7, 4), abs=1e-9)

    def test_project_bootstrap_helper_identical_across_two_calls(self, fixture_rows) -> None:
        """底层 helper 本身的可复现性（复用即继承该性质，无需重实现）。"""
        a = [{**r, "passed": r.get("detection_rate")} for r in fixture_rows["aitester"]]
        b = [{**r, "passed": r.get("detection_rate")} for r in fixture_rows["plain_llm"]]
        first = bootstrap_paired_diff_ci(a, b, n_resamples=10000, seed=42)
        second = bootstrap_paired_diff_ci(a, b, n_resamples=10000, seed=42)
        assert first == second
        assert first[3] == 7


# ─── (iii) 报告落盘 + 必需列头 ───────────────────────────────────────────
_REQUIRED_HEADERS = (
    "## 0. 口径（caliber）",
    "派生证据",
    "n_common",
    "n10",
    "n01",
    "观测 δ(pp)",
    "MDE_σ(pp)（闭式，主口径）",
    "观测/MDE_σ",
    "## 2. 比例型端点：各臂点估计",
    "## 3. 比例型端点：配对差 95% CI",
    "配对差(pp)",
    "95% CI(pp)",
    "## 4. 成本分布",
    "中位数 tokens",
    "IQR",
    "## 6. 不可计算项与局限",
)


class TestReportArtifacts:
    def test_main_writes_report_and_json_with_required_headers(self, fixture_dir: Path, tmp_path: Path, capsys) -> None:
        out_dir = tmp_path / "out"
        rc = main(
            [
                "--results-dir",
                str(fixture_dir),
                "--out",
                str(out_dir),
                "--batches",
                "benchmark_synthetic_20261006_140906.json",
            ]
        )
        assert rc == 0
        report_path = out_dir / "emse_stats_report.md"
        json_path = out_dir / "emse_stats_report.json"
        assert report_path.is_file()
        assert json_path.is_file()

        report = report_path.read_text(encoding="utf-8")
        missing = [header for header in _REQUIRED_HEADERS if header not in report]
        assert not missing, f"报告缺少必需列头/章节：{missing}"

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["caliber"]["derived_evidence"] is True
        assert payload["caliber"]["bootstrap_seed"] == 42
        assert payload["caliber"]["bootstrap_n_resamples"] == 10000
        assert set(payload["arms"]) == set(_ARMS)
        assert len(payload["mde"]) == 3
        assert len(payload["paired_diff_ci"]) == 12  # 3 对比 × 4 端点

        # 报告与 JSON 同源：JSON 的 n_common/n10/n01 必须出现在报告表格中
        first = payload["mde"][0]
        assert first["n_common"] == 7
        assert (first["n10"], first["n01"]) == (2, 0)
        assert f"| {first['n_common']} | {first['n10']} | {first['n01']} |" in report
        # JSON 的 MDE 必须等于现算值（同源，不硬编码定案数）
        expected_mde = mde_sigma_closed_form_pp(first["n_common"], first["sigma_d2"])
        assert expected_mde is not None
        assert first["mde_sigma_closed_pp"] == pytest.approx(expected_mde, abs=1e-3)

        # 控制台摘要（紧凑口径行 + MDE 行）
        captured = capsys.readouterr().out
        assert "MDE_σ(闭式)" in captured
        assert "报告：" in captured

    def test_missing_batch_files_fail_loudly(self, tmp_path: Path, capsys) -> None:
        """批次缺失 → 退出码 2 且不落盘（不静默用少数批次出报告）。"""
        out_dir = tmp_path / "out"
        rc = main(["--results-dir", str(tmp_path), "--out", str(out_dir), "--batches", "not_there.json"])
        assert rc == 2
        assert not (out_dir / "emse_stats_report.md").exists()
        assert "口径错误" in capsys.readouterr().err

    def test_default_batches_are_rp02_three_seeds(self) -> None:
        """默认批次 = R-P0-2 三种子（口径写死在常量里，避免无参数时口径漂移）。"""
        assert len(_RP02_DEFAULT_BATCHES) == 3
        assert all("20261006" in name for name in _RP02_DEFAULT_BATCHES)
        assert resolve_batch_files(Path("/tmp"), None) == [Path("/tmp") / n for n in _RP02_DEFAULT_BATCHES]


# ─── (iv) None / 缺失值剔除而非记 0 ──────────────────────────────────────
class TestNoneExcludedNotZero:
    def test_endpoint_denominator_excludes_none(self, fixture_rows) -> None:
        """ai 臂 detection 有 3 个 1 / 4 个 0 / 1 个 None → 3/7，而非 3/8。"""
        point = endpoint_point(fixture_rows["aitester"], "detection_rate")
        assert point["numerator"] == 3
        assert point["denominator"] == 7
        assert point["rate_pct"] == pytest.approx(100.0 * 3 / 7, abs=1e-4)
        assert point["rate_pct"] != pytest.approx(100.0 * 3 / 8, abs=1e-4)

    def test_conditional_denominator_uses_passed_rows(self, fixture_rows) -> None:
        """条件口径（passed=True）分母 = passed 行 ∩ 可测行。"""
        point = endpoint_point(fixture_rows["aitester"], "false_fix_rate", restrict_passed=True)
        assert point["denominator"] == 4  # task_0000..0003（task_0007 的 None 不计）
        assert point["numerator"] == 2
        assert point["rate_pct"] == pytest.approx(50.0, abs=1e-4)

    def test_pairing_drops_none_rows(self, fixture_rows) -> None:
        """配对时 None 行退出分母：ai vs llm 为 7 对（任务 7 被剔除）。"""
        ci = paired_diff_ci(fixture_rows["aitester"], fixture_rows["plain_llm"], "detection_rate")
        assert ci["n_pairs"] == 7
        assert ci["diff_pp"] == pytest.approx(round(100.0 * 2 / 7, 4), abs=1e-9)
        # 若把 None 记 0，配对会是 8 对且差值为 (3−1)/8——断言未发生该口径漂移
        assert ci["n_pairs"] != 8
        assert ci["diff_pp"] != pytest.approx(round(100.0 * 2 / 8, 4), abs=1e-9)

    def test_paired_structure_none_excluded(self, fixture_rows) -> None:
        """MDE 块的 n_common/n10/n01 与 None 口径一致。"""
        block = mde_block(fixture_rows["aitester"], fixture_rows["plain_llm"], "detection_rate")
        assert block["n_common"] == 7
        assert (block["n10"], block["n01"], block["n11"]) == (2, 0, 1)
        assert block["sigma_d2"] is not None and block["sigma_d2"] > 0
        mde = block["mde_sigma_closed_pp"]
        assert mde is not None and mde > 0
        # 比值 = |观测 δ| / MDE（现算，非硬编码）；夹具只有 7 对，MDE > 观测 δ
        # ⇒ 比值 < 1——正是"样本量不足、该对比本就检不出"的演示
        ratio = block["ratio_delta_over_mde_sigma"]
        assert ratio is not None
        assert ratio == pytest.approx(abs(block["delta_pp"] or 0.0) / mde, abs=1e-3)
        assert 0.0 < ratio < 1.0

    def test_zero_token_rows_excluded_from_cost(self, fixture_rows) -> None:
        """token 记账为 0 的行不进成本分布（与 S11 判定同口径）。"""
        cost = cost_block(fixture_rows["aitester"])
        assert cost["n_rows"] == 8
        assert cost["n_tokens_positive"] == 7  # task_0006 的 0 token 被剔除
        assert cost["median_tokens"] is not None


# ─── 真实工件回归（缺席自动 skip；不依赖 1.4GB 目录存在） ─────────────────
@pytest.mark.skipif(
    not all((_REAL_RESULTS_DIR / name).is_file() for name in _RP02_DEFAULT_BATCHES),
    reason="R-P0-2 三种子批次工件不在场（外部数据目录），跳过真实工件回归",
)
class TestRealArtifactRegression:
    def test_pooled_pairing_matches_canonical_report(self) -> None:
        """三对比的 n_common / n10 / n01 与 canonical 三种子合并报告逐位一致。"""
        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        assert [m["seed"] for m in meta] == [42, 43, 44]
        assert all(len(rows[arm]) == 261 for arm in _ARMS)
        for (arm_a, arm_b), expected in _REAL_EXPECTED.items():
            block = mde_block(rows[arm_a], rows[arm_b], "detection_rate")
            assert (block["n_common"], block["n10"], block["n01"]) == expected

    def test_mde_positive_and_below_observed_delta(self) -> None:
        """三对比 MDE 均为正且小于观测差异（即均非"样本量注定检不出"）。"""
        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, _meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        for arm_a, arm_b in _REAL_EXPECTED:
            block = mde_block(rows[arm_a], rows[arm_b], "detection_rate")
            mde = block["mde_sigma_closed_pp"]
            assert mde is not None and mde > 0
            assert abs(block["delta_pp"] or 0.0) > mde

    def test_none_rows_excluded_in_real_data(self) -> None:
        """真实工件：aitester 的 21 行 detection=None 不进分母（261→240）。"""
        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, _meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        point = endpoint_point(rows["aitester"], "detection_rate")
        assert point["denominator"] == 240
        assert point["numerator"] == 38

    def test_false_fix_caliber_matches_rp02_canonical(self) -> None:
        """真实工件：false_fix 边际 = 143/240 = 59.58%（项目定案分母口径）。

        守卫点：若把 21 行不可测行计入分母（143/261 = 54.79%）或把 None 记 0，
        本断言失败。
        """
        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, _meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        marginal = endpoint_point(rows["aitester"], "false_fix_rate")
        conditional = endpoint_point(rows["aitester"], "false_fix_rate", restrict_passed=True)
        assert (marginal["numerator"], marginal["denominator"]) == (143, 240)
        assert marginal["rate_pct"] == pytest.approx(59.58, abs=0.01)
        assert (conditional["numerator"], conditional["denominator"]) == (143, 143)


class TestWilsonCiA07:
    """A-07（2026-10-17）：比例型端点单臂 Wilson score 95% CI。"""

    def test_known_values(self) -> None:
        """已知值锁定：38/240 与 4/261 与独立评审复算一致（防公式漂移）。"""
        from experiments.emse_stats_report import wilson_ci

        lo, hi = wilson_ci(38, 240)
        assert (round(lo, 2), round(hi, 2)) == (11.76, 20.99)
        lo2, hi2 = wilson_ci(4, 261)
        assert (round(lo2, 2), round(hi2, 2)) == (0.60, 3.87)

    def test_zero_denominator_returns_none(self) -> None:
        """n=0 → None（不可计算不记 0，与全模块纪律一致）。"""
        from experiments.emse_stats_report import wilson_ci

        assert wilson_ci(0, 0) is None

    def test_extremes_are_bounded(self) -> None:
        """0/n 与 n/n 的区间不越界 [0,100] 且包含点估计。"""
        from experiments.emse_stats_report import wilson_ci

        lo, hi = wilson_ci(0, 37)
        assert 0.0 <= lo <= hi <= 100.0 and lo == 0.0
        lo2, hi2 = wilson_ci(37, 37)
        assert 0.0 <= lo2 <= hi2 <= 100.0 and hi2 == 100.0

    def test_endpoint_point_carries_wilson(self) -> None:
        """endpoint_point 输出含 wilson95_pct 且与 wilson_ci 同源。"""
        from experiments.emse_stats_report import wilson_ci

        rows = [{"detection_rate": 1.0}, {"detection_rate": 0.0}, {"detection_rate": None}]
        point = endpoint_point(rows, "detection_rate")
        assert point["denominator"] == 2 and point["numerator"] == 1
        assert point["wilson95_pct"] == [round(x, 4) for x in wilson_ci(1, 2)]

    def test_real_data_matches_review_recompute(self) -> None:
        """真实工件：aitester detection 38/240 的 Wilson CI 与复算工件逐位一致。"""
        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, _meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        point = endpoint_point(rows["aitester"], "detection_rate")
        assert point["wilson95_pct"] == [11.7581, 20.9851]


class TestCostEffectivenessA07:
    """A-07（2026-10-17）：$/detection 成本-效果块。"""

    def test_unregistered_price_not_fabricated(self) -> None:
        """价目未登记的模型不计价（不编造价格），tokens 仍累计。"""
        from experiments.emse_stats_report import cost_effectiveness_block

        rows = [
            {
                "detection_rate": 1.0,
                "token_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "llm_calls": 1,
                    "by_model": {"mystery-model": 150},
                },
            }
        ]
        out = cost_effectiveness_block(rows, price_table={})
        assert out["n_priced_rows"] == 0 and out["n_unpriceable_rows"] == 1
        assert out["total_usd"] == 0.0
        assert out["tokens_per_detection"] == 150.0
        assert out["usd_per_detection"] is None or out["usd_per_detection"] == 0.0

    def test_single_model_priced_exactly(self) -> None:
        """单模型行按 input/output 分别计价（算术精确锁定）。"""
        from experiments.emse_stats_report import cost_effectiveness_block

        price = {"m1": {"input_per_mtok": 0.3, "output_per_mtok": 1.2}}
        rows = [
            {
                "detection_rate": 1.0,
                "token_usage": {
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "total_tokens": 2_000_000,
                    "llm_calls": 1,
                    "by_model": {"m1": 2_000_000},
                },
            },
            {
                "detection_rate": 0.0,
                "token_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                    "by_model": {},
                },
            },
        ]
        out = cost_effectiveness_block(rows, price_table=price)
        assert out["total_usd"] == pytest.approx(0.3 + 1.2, abs=1e-9)
        assert out["n_detections"] == 1
        assert out["usd_per_detection"] == pytest.approx(1.5, abs=1e-9)
        assert out["tokens_per_detection"] == pytest.approx(2_000_000.0)

    def test_zero_detection_no_division(self) -> None:
        """检出为 0 → $/detection 与 tokens/detection 均 None（不除零）。"""
        from experiments.emse_stats_report import cost_effectiveness_block

        rows = [
            {
                "detection_rate": 0.0,
                "token_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "llm_calls": 1,
                    "by_model": {"m1": 15},
                },
            }
        ]
        out = cost_effectiveness_block(rows, price_table={"m1": {"input_per_mtok": 0.3, "output_per_mtok": 1.2}})
        assert out["n_detections"] == 0
        assert out["usd_per_detection"] is None and out["tokens_per_detection"] is None

    def test_real_data_usd_per_task_matches_baseline(self) -> None:
        """真实工件：总 $ / 行数 反算的 $/task 与 BASELINE 声称逐位一致
        （aitester $0.0259 / plain_llm_df $0.0045——价格记账的端到端锁定）。"""
        from experiments.emse_stats_report import cost_effectiveness_block

        files = resolve_batch_files(_REAL_RESULTS_DIR, None)
        rows, _meta = load_pooled_rows(_REAL_RESULTS_DIR, files)
        for arm, expected in (("aitester", 0.0259), ("plain_llm_df", 0.0045)):
            out = cost_effectiveness_block(rows[arm])
            assert out["total_usd"] is not None
            per_task = out["total_usd"] / len(rows[arm])
            assert per_task == pytest.approx(expected, abs=5e-5), f"{arm}: {per_task}"
