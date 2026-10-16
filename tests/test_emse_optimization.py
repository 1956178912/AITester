"""EMSE 投稿优化分析工具（experiments/emse_optimization.py）回归测试。

覆盖（全部纯 stdlib / 零 LLM / 零网络 / 零子进程）：
- McNemar 精确 p 与连续性校正 χ²：对照 statistical_report 已定案值
  （12:80→48.79、37:3→27.23、113:0→111.01、2:3→1.0、8:5→0.5811、
  4:8→0.3877）——统计原语与项目口径逐位对齐；
- paired_contrast 的 δ 方向约定（X vs Y → δ=X−Y）与共同可测子集口径；
- MDE / 所需配对数 / 功效的正态近似公式（手算对照）；
- 贝叶斯因子：对称性、极端值方向、Judjeys 标签判读；
- false_fix 双口径聚合（边际/条件分母）；
- Pearson/Spearman（含 ties 的平均秩）；
- swebench 事实提取与过红抽样确定性（固定 seed）。
"""

from __future__ import annotations

import json
import math

import pytest

from experiments.emse_optimization import (
    ab_pair_analysis,
    bayes_factor_discordant,
    build_false_fix_matrix,
    classify_failure_signature,
    false_fix_caliber,
    mcnemar_chi2_cc,
    mcnemar_exact_p,
    mde_paired_pp,
    mutation_correlation,
    over_red_cases,
    over_red_failure_modes,
    paired_contrast,
    pearson,
    power_at_delta,
    required_pairs,
    spearman,
    swebench_infra_facts,
)

# ─── McNemar 统计原语（对照项目已定案值） ─────────────────────────────────


class TestMcNemarPrimitives:
    @pytest.mark.parametrize(
        ("b", "c", "expected_p"),
        [
            (2, 3, 1.0),  # spec_replace B vs A（spec 报告 p=1.0000）
            (8, 5, 0.5811),  # spec_replace C vs A（spec 报告 p=0.5811）
            (4, 8, 0.3877),  # spec_replace C vs B（spec 报告 p=0.3877）
            (0, 0, 1.0),  # 无不一致对
        ],
    )
    def test_exact_p_matches_project_values(self, b, c, expected_p):
        assert mcnemar_exact_p(b, c) == pytest.approx(expected_p, abs=1e-4)

    def test_exact_p_strong_effect(self):
        # 113:0（主批次 df vs llm）——双尾精确 p = 2×0.5^113 ≈ 1.93e-34。
        # 回归纪律：容差必须为相对容差；绝对容差会把更极端配置纳入双尾，
        # 把 p 虚抬到 ~1e-12 量级（本断言即该缺陷的守卫）。
        p = mcnemar_exact_p(113, 0)
        assert p == pytest.approx(2.0 * 0.5**113, rel=1e-6)
        assert p < 1e-30

    @pytest.mark.parametrize(
        ("b", "c", "expected_chi2"),
        [
            (12, 80, 48.79),  # 主批次 aitester vs df（statistical_report 定案）
            (37, 3, 27.23),  # 主批次 aitester vs llm
            (113, 0, 111.01),  # 主批次 df vs llm
            (2, 3, 0.0),  # |b−c|=1 时连续性校正归零
        ],
    )
    def test_chi2_cc_matches_project_values(self, b, c, expected_chi2):
        assert mcnemar_chi2_cc(b, c) == pytest.approx(expected_chi2, abs=0.01)


# ─── paired_contrast：方向约定与共同可测子集 ──────────────────────────────


def _row(task_id: str, det: float | None) -> dict:
    return {"task_id": task_id, "detection_rate": det}


class TestPairedContrast:
    def test_delta_direction_is_first_minus_second(self):
        """X vs Y 的 δ 必须为 X−Y（标签方向），防止报告级符号翻转。"""
        rows_x = [_row("t1", 1.0), _row("t2", 0.0), _row("t3", 1.0)]
        rows_y = [_row("t1", 0.0), _row("t2", 0.0), _row("t3", 1.0)]
        c = paired_contrast(rows_x, rows_y)
        assert c["only_first"] == 1  # t1：仅 X 检出
        assert c["only_second"] == 0
        assert c["both"] == 1
        assert c["n_pairs"] == 3
        assert c["delta_pp"] == pytest.approx(100.0 / 3, abs=0.01)

    def test_common_measurable_subset_only(self):
        """任一侧 None 的任务不进分母（共同可测子集口径）。"""
        rows_x = [_row("t1", 1.0), _row("t2", None)]
        rows_y = [_row("t1", 1.0), _row("t2", 0.0)]
        c = paired_contrast(rows_x, rows_y)
        assert c["n_pairs"] == 1
        assert c["both"] == 1
        assert c["delta_pp"] == 0.0

    def test_unpaired_task_excluded(self):
        rows_x = [_row("t1", 1.0), _row("tX", 1.0)]
        rows_y = [_row("t1", 0.0)]
        c = paired_contrast(rows_x, rows_y)
        assert c["n_pairs"] == 1


# ─── 功效分析原语 ─────────────────────────────────────────────────────────


class TestPowerAnalysis:
    def test_mde_matches_hand_computation(self):
        """n=35、ψ=5/35：MDE = 2.8016×sqrt(0.142857/140) ≈ 8.95pp。"""
        mde = mde_paired_pp(35, 5 / 35)
        expected = 100.0 * (1.959964 + 0.841621) * math.sqrt((5 / 35) / (4 * 35))
        assert mde == pytest.approx(expected, abs=0.01)

    def test_required_pairs_for_8pp(self):
        """观测 ψ=5/35 下 80% 功效检出 8pp 需 44 对（向上取整）。"""
        n = required_pairs(8.0, 5 / 35)
        assert n == 44

    def test_power_at_delta(self):
        """n=35、ψ=5/35 时对 8pp 的功效 ≈0.707。"""
        p = power_at_delta(8.0, 35, 5 / 35)
        assert p == pytest.approx(0.7068, abs=0.001)

    def test_more_pairs_increases_power(self):
        p35 = power_at_delta(8.0, 35, 5 / 35)
        p87 = power_at_delta(8.0, 87, 5 / 35)
        assert p87 > p35 > 0.5

    def test_degenerate_inputs_return_none(self):
        assert mde_paired_pp(0, 0.5) is None
        assert mde_paired_pp(35, 0.0) is None
        assert required_pairs(0.0, 0.5) is None
        assert power_at_delta(-1.0, 35, 0.5) is None


# ─── 贝叶斯因子 ───────────────────────────────────────────────────────────


class TestBayesFactor:
    def test_matches_project_recompute(self):
        """(2,3)→0.375；(8,5)→0.3076；(4,8)→0.4443（emse_optimization 实算值）。"""
        assert bayes_factor_discordant(2, 3)["bf10_jeffreys"] == pytest.approx(0.375, abs=0.001)
        assert bayes_factor_discordant(8, 5)["bf10_jeffreys"] == pytest.approx(0.3076, abs=0.001)
        assert bayes_factor_discordant(4, 8)["bf10_jeffreys"] == pytest.approx(0.4443, abs=0.001)

    def test_symmetry_in_discordant_swap(self):
        """BF 在 (b,c) 互换下不变（先验与 H0 均对称）。"""
        assert bayes_factor_discordant(2, 3)["bf10_jeffreys"] == pytest.approx(
            bayes_factor_discordant(3, 2)["bf10_jeffreys"], abs=1e-9
        )

    def test_balanced_data_favors_null(self):
        """b=c 时 BF10<1 且随 n 增大而下降——点零假设的 Occam 因子行为
        （50:50 → BF10≈0.0796；数值积分对照验证，见测试开发记录）。"""
        bf = bayes_factor_discordant(50, 50)["bf10_jeffreys"]
        assert bf == pytest.approx(0.0796, abs=0.001)

    def test_strong_evidence_direction(self):
        """极端不一致（20:2）→ BF10≈853.6>3 支持 H1。"""
        res = bayes_factor_discordant(20, 2)
        assert res["bf10_jeffreys"] == pytest.approx(853.6, rel=0.01)
        assert res["bf10_jeffreys"] > 3.0
        assert "H1" in res["verdict"]

    def test_null_support_verdict(self):
        res = bayes_factor_discordant(8, 5)
        assert res["bf10_jeffreys"] < 1 / 3
        assert "H0" in res["verdict"]

    def test_no_discordant_pairs(self):
        res = bayes_factor_discordant(0, 0)
        assert res["bf10_jeffreys"] is None
        assert "不可判定" in res["verdict"]


# ─── false_fix 双口径 ─────────────────────────────────────────────────────


def _ff_row(passed: bool | None, ff: float | None) -> dict:
    return {"passed": passed, "false_fix_rate": ff}


class TestFalseFixCaliber:
    def test_marginal_and_conditional(self):
        rows = [
            _ff_row(True, 1.0),  # passed ∧ ff=1
            _ff_row(True, 0.0),  # passed ∧ gold 通过
            _ff_row(False, 0.0),  # 未声称成功
            _ff_row(None, None),  # 不可测
        ]
        out = false_fix_caliber(rows)
        assert out["n_rows"] == 4
        assert out["n_passed"] == 2
        assert out["n_measurable"] == 3
        assert out["n_ff1"] == 1
        assert out["marginal_pct"] == pytest.approx(100.0 / 3, abs=0.01)  # 1/3
        assert out["n_passed_measurable"] == 2
        assert out["conditional_pct"] == pytest.approx(50.0, abs=0.01)  # 1/2

    def test_all_passed_are_false_fixes(self):
        """原始口径极端情形：全部 passed 行 ff=1 → 条件口径 100%。"""
        rows = [_ff_row(True, 1.0)] * 5 + [_ff_row(False, 0.0)] * 5
        out = false_fix_caliber(rows)
        assert out["conditional_pct"] == 100.0
        assert out["marginal_pct"] == 50.0

    def test_empty_population(self):
        out = false_fix_caliber([])
        assert out["n_measurable"] == 0
        assert out["marginal_pct"] is None
        assert out["conditional_pct"] is None

    def test_matrix_against_main_batch_artifacts(self):
        """口径矩阵对主批次工件的定案值（R-P0-2 aitester：59.58%/100%）。"""
        matrix = build_false_fix_matrix()
        pop = matrix["populations"]["RP02_aitester"]
        assert pop["n_rows"] == 261
        assert pop["n_passed"] == 143
        assert pop["n_measurable"] == 240
        assert pop["n_ff1"] == 143
        assert pop["marginal_pct"] == pytest.approx(59.58, abs=0.01)
        assert pop["conditional_pct"] == 100.0

    def test_matrix_recomputes_live_when_artifacts_present(self):
        """2026-10-15 修复回归：自动复算分支必须真的触发。

        缺陷史：`_load_main_batch_rows()` 曾以 `timestamp > "2026-10-02"` 整批
        跳过，而 R-P0-2 三种子批次的 timestamp 是 2026-10-06 → 复算分支永不触发，
        矩阵长期返回硬编码 `source="10-13_caliber_fallback"`（数值相同故无人察觉）。
        """
        from experiments.emse_optimization import MAIN_BATCH_DIR

        if not sorted(MAIN_BATCH_DIR.glob("benchmark_synthetic_20261006_1*.json")):
            pytest.skip("R-P0-2 三种子批次工件不在工作树")
        pop = build_false_fix_matrix()["populations"]["RP02_aitester"]
        assert pop["source"] == "main_batch_artifact", pop
        assert pop["n_measurable"] == 240
        # 21 行 M10 第 0 轮死亡（false_fix_rate=None）不得进入 false-fix 分母
        assert pop["n_passed_but_unmeasurable"] == 21

    def test_denominator_is_metric_measurability_not_passed_measurability(self):
        """分母必须是"被度量指标本身可测"的行（修复后的显式口径）。

        构造 passed 可测但 false_fix 不可测的行：它必须**不进**边际分母。
        """
        rows = [
            _ff_row(True, 1.0),
            _ff_row(False, 0.0),
            _ff_row(False, None),  # passed 可测（False），但 false_fix 不可测 → 不进分母
        ]
        out = false_fix_caliber(rows)
        assert out["n_measurable"] == 2  # 不是 3
        assert out["n_passed_but_unmeasurable"] == 1
        assert out["marginal_pct"] == pytest.approx(50.0)

    def test_adr0027_corrected_population_present(self):
        """ADR-0027 修正口径引用值在场（同一矩阵的第二个总体）。"""
        adr = build_false_fix_matrix()["populations"]["ADR0027_corrected"]
        assert adr["conditional_pct"] == 87.16
        assert (adr["n_ff1"], adr["n_measurable"]) == (380, 436)


# ─── 相关性与抽样 ─────────────────────────────────────────────────────────


class TestCorrelation:
    def test_pearson_perfect(self):
        assert pearson([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]) == pytest.approx(1.0)

    def test_pearson_negative(self):
        r = pearson([1.0, 2.0, 3.0, 4.0], [8.0, 6.0, 4.0, 2.0])
        assert r == pytest.approx(-1.0)

    def test_spearman_monotone_nonlinear(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [1.0, 4.0, 9.0, 16.0, 25.0]  # 单调非线性
        assert spearman(xs, ys) == pytest.approx(1.0)

    def test_spearman_ties_average_rank(self):
        xs = [1.0, 2.0, 2.0, 3.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        assert spearman(xs, ys) == pytest.approx(0.9487, abs=0.001)

    def test_degenerate_returns_none(self):
        assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
        assert spearman([1.0, 2.0], [1.0, 2.0]) is None

    def test_mutation_correlation_structure(self):
        rows = [
            {"detection_rate": 1.0, "mutation_score": 0.9, "mutants_total": 5},
            {"detection_rate": 0.0, "mutation_score": 0.8, "mutants_total": 4},
            {"detection_rate": 1.0, "mutation_score": 0.95, "mutants_total": 6},
            {"detection_rate": 0.0, "mutation_score": 0.7, "mutants_total": 3},
        ]
        out = mutation_correlation(rows)
        assert out["n_det_measurable"] == 4
        assert out["detection_rate_pct"] == 50.0
        assert out["mutation_score"]["n_pairs"] == 4
        assert out["mutation_score"]["mean_when_detection_1"] == pytest.approx(0.925, abs=1e-3)
        assert out["mutants_total_distribution"]["n"] == 4
        assert out["mutants_total_distribution"]["max"] == 6

    def test_mutation_correlation_computes_real_coefficients(self):
        """EMSE 批次修复锁定：docstring 声称的 Pearson/Spearman 必须真算。

        回归背景：修复前函数体只返回 n_pairs 与 mean_when_detection_1，
        论文若据此声称"已交叉验证"即为不实陈述。
        """
        rows = [
            {"detection_rate": 1.0, "mutation_score": 0.9, "mutants_total": 5},
            {"detection_rate": 0.0, "mutation_score": 0.8, "mutants_total": 4},
            {"detection_rate": 1.0, "mutation_score": 0.95, "mutants_total": 6},
            {"detection_rate": 0.0, "mutation_score": 0.7, "mutants_total": 3},
        ]
        ms = mutation_correlation(rows)["mutation_score"]
        # 检出组 MS 均值 0.925 > 未检出组 0.75 → 正相关，且系数非 None
        assert ms["pearson"] is not None
        assert ms["spearman"] is not None
        assert ms["pearson"] > 0
        assert ms["mean_when_detection_0"] == pytest.approx(0.75, abs=1e-3)
        assert ms["mean_delta_det1_minus_det0"] == pytest.approx(0.175, abs=1e-3)
        assert "convergent-validity" in ms["interpretation_caveat"]

    def test_mutation_correlation_negative_direction_is_surfaced(self):
        """分层方向为负时必须如实呈现（不得被弱正号掩盖）。"""
        rows = [
            {"detection_rate": 1.0, "mutation_score": 0.5, "mutants_total": 5},
            {"detection_rate": 0.0, "mutation_score": 0.9, "mutants_total": 4},
            {"detection_rate": 1.0, "mutation_score": 0.55, "mutants_total": 6},
            {"detection_rate": 0.0, "mutation_score": 0.95, "mutants_total": 3},
        ]
        ms = mutation_correlation(rows)["mutation_score"]
        assert ms["mean_delta_det1_minus_det0"] < 0
        assert ms["pearson"] is not None and ms["pearson"] < 0

    def test_mutation_correlation_degenerate_spearman_reason(self):
        """退化路径给明确 reason，不臆造系数。"""
        rows = [
            {"detection_rate": 1.0, "mutation_score": 0.9, "mutants_total": 5},
            {"detection_rate": 0.0, "mutation_score": 0.8, "mutants_total": 4},
        ]
        ms = mutation_correlation(rows)["mutation_score"]
        assert ms["spearman"] is None
        assert ms["spearman_reason"] == "n_pairs_lt_3"


# ─── A/B 配对分析（--ab-pair 入口，D1 QuixBugs 复算用） ────────────────────


class TestAbPairAnalysis:
    def _write_batch(self, tmp_path, name: str, rows: list[dict]) -> str:
        path = tmp_path / name
        path.write_text(json.dumps({"results": {"arm": {"details": rows}}}), encoding="utf-8")
        return str(path)

    def test_ab_pair_direction_and_marginals(self, tmp_path):
        """δ=第一臂−第二臂；边际率分子分母透明化。"""
        rows_first = [{"task_id": f"t{i}", "detection_rate": 1.0 if i < 3 else 0.0} for i in range(10)]
        rows_second = [{"task_id": f"t{i}", "detection_rate": 1.0 if i < 5 else 0.0} for i in range(10)]
        fa = self._write_batch(tmp_path, "a.json", rows_first)
        fb = self._write_batch(tmp_path, "b.json", rows_second)
        out = ab_pair_analysis(fa, fb, "arm", "arm")
        assert out["n_pairs"] == 10
        assert out["only_first"] == 0  # 第一臂 3 个命中全部被第二臂覆盖
        assert out["only_second"] == 2
        assert out["delta_pp"] == -20.0  # 第一臂 − 第二臂
        assert out["marginal_first"]["rate_pct"] == 30.0
        assert out["marginal_second"]["rate_pct"] == 50.0
        assert out["mde_pp_80power"] is not None
        assert out["bayes"]["bf10_jeffreys"] is not None

    def test_ab_pair_missing_arm(self, tmp_path):
        fa = self._write_batch(tmp_path, "a.json", [{"task_id": "t1", "detection_rate": 1.0}])
        fb = self._write_batch(tmp_path, "b.json", [{"task_id": "t1", "detection_rate": 1.0}])
        out = ab_pair_analysis(fa, fb, "arm", "nonexistent_arm")
        assert out["n_pairs"] == 0
        assert out["delta_pp"] is None


class TestSamplingAndFacts:
    def test_over_red_cases_deterministic(self):
        """固定 seed 确定性 + 同 task 三种子行不串行（来源批次随案例保留）。"""
        rows: list[tuple[str, dict]] = []
        for seed_file in ("b1.json", "b2.json", "b3.json"):
            rows.extend(
                (
                    seed_file,
                    {
                        "task_id": f"t{i}",
                        "detection_first_status": "red_not_repaired",
                        "detection_rate": 0.0,
                        "generated_test": "x" * 100,
                    },
                )
                for i in range(8)
            )
        rows.append(
            ("b1.json", {"task_id": "tz", "detection_first_status": "all_green_unverified", "detection_rate": 0.0})
        )
        a = over_red_cases(rows, k=5, seed=42)
        b = over_red_cases(rows, k=5, seed=42)
        assert len(a) == 5
        assert [(c["task_id"], c["source_file"]) for c in a] == [(c["task_id"], c["source_file"]) for c in b]
        assert all(c["detection_first_status"] == "red_not_repaired" for c in a)
        assert all(c["source_file"] in ("b1.json", "b2.json", "b3.json") for c in a)
        assert all(c["test_head"] for c in a)

    def test_over_red_cases_empty(self):
        assert over_red_cases([], k=5) == []

    def test_over_red_failure_modes_material_missing(self):
        """fixed 材料缺失的行记 material_missing（不误报为通过/失败）。"""
        rows = [("b1.json", {"task_id": "t0", "detection_first_status": "red_not_repaired", "detection_rate": 0.0})]
        cases = [{"task_id": "t0", "source_file": "b1.json"}]
        out = over_red_failure_modes(cases, rows)
        assert out[0]["status"] == "material_missing"
        assert out[0]["source_file"] == "b1.json"

    def test_over_red_failure_modes_reruns_on_fixed(self, tmp_path):
        """有材料时在 fixed 上真实复跑（零 LLM，子进程 pytest）并记录 rc/模式。"""
        fixed = "def add(a, b):\n    return a + b\n"
        test = "from task_m import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        rows = [
            (
                "b1.json",
                {
                    "task_id": "synthetic__task_m",
                    "detection_first_status": "red_not_repaired",
                    "detection_rate": 0.0,
                    "generated_test": test,
                    "task_metadata": {"fixed": fixed},
                },
            )
        ]
        cases = [{"task_id": "synthetic__task_m", "source_file": "b1.json"}]
        out = over_red_failure_modes(cases, rows)
        assert out[0]["status"] == "ok"
        assert out[0]["passes_on_fixed"] is True
        assert out[0]["failure_mode"] == "P4_passes_on_fixed"

    def test_classify_failure_signature_rules(self):
        """模式判据：P3（属性耦合）> P2（过度规格）> P1（契约倒置）优先序。"""
        assert (
            classify_failure_signature("AttributeError: module 'x' has no attribute 'y'")
            == "P3_implementation_coupling"
        )
        assert classify_failure_signature("ValueError: invalid literal for int()") == "P2_over_specification"
        assert classify_failure_signature("AssertionError: assert 10 == 0") == "P1_bug_coupled_expectation"
        assert classify_failure_signature("something else entirely") == "P0_unclassified"

    def test_swebench_facts_from_real_artifact(self):
        """真实工件在场时校验结构化事实（缺工件则跳过——CI 精简环境）。"""
        from experiments.emse_optimization import SWEBENCH_SUMMARY

        if not SWEBENCH_SUMMARY.is_file():
            pytest.skip("swebench_20_summary.json 不在工作树")
        facts = swebench_infra_facts()
        assert facts["available"] is True
        assert facts["total_tasks_attempted"] == 20
        assert facts["tasks_completed"] == 7
        assert facts["tasks_failed"] == 3
        assert facts["tasks_timeout"] == 10
        assert "429" in facts["notes"]
        assert "基础设施故障" in facts["corrected_statement"]
        # EMSE 批次（2026-10-15 一致性修复）：限流信号计数必须覆盖全部结构化
        # 文本源，且 breakdown 之和与总数对账（旧实现只数 notes+run_notes=2，
        # 与"7/7 完成者均因 429 失败"的散文叙述不一致）。
        assert facts["rate_limit_signals"] >= 2, facts["rate_limit_signal_breakdown"]
        breakdown = facts["rate_limit_signal_breakdown"]
        # 真实工件（swebench_20_summary.json）：notes/run_notes/issues 各含 1 次
        # "429" 字面量，去重并集总数 = 2（notes 与 run_notes 文本不同、issues 文本
        # 亦不同）；issues 中"限流/429"条目共 3 条（含 404 端点错配条目不计）。
        # 关键回归点：总数不得退回旧口径（旧实现只数 notes+run_notes 且当 notes
        # 非空时完全忽略 issues）。
        assert facts["rate_limit_signals"] == 2, breakdown
        assert breakdown["issues"] == 1, breakdown
        assert breakdown["issues_rate_limit_entries"] >= 2, breakdown
        assert facts["rate_limit_signals"] >= max(breakdown[k] for k in ("run_notes", "notes", "issues")), breakdown

    def test_swebench_facts_missing_file(self, tmp_path):
        facts = swebench_infra_facts(tmp_path / "nope.json")
        assert facts["available"] is False
