"""df_spec 分析脚本契约测试（零 LLM；纯函数纪律）。

锁定 tests 对象 experiments/emse_df_spec_analysis.py 的核心口径：
- 单向精确 p 的单侧尾定义与边界；
- 有效配对子集（双方非 None）与方向计数；
- 41 缺陷程序口径切分（_test 后缀排除）；
- 预注册三态判定边界（60%/50% 线、0.05/0.10 p 界、方向条件）；
- 取值域统计（spec_replace_applied / verdict）。

背景：脚本按"有入库测试锁定契约的 emse 脚本必须入库"纪律（.gitignore
批次七/九注释）随本测试入库——否则 fresh clone 收集即 ImportError。
"""

from __future__ import annotations

import json

import pytest

from experiments.emse_df_spec_analysis import (
    CONFIRM_P,
    FAIL_LINE,
    SUCCESS_LINE,
    MissingArtifactError,
    build_analysis,
    contrast,
    decide,
    defect_program_ids,
    detection_summary,
    domain_stats,
    effective_pair,
    load_arm_rows,
    one_sided_p,
)


def _row(det=None, sra=None, verdict=None):
    return {
        "detection_rate": det,
        "spec_replace_applied": sra,
        "specificity_gate_verdict": verdict,
        "red_regression_violation": None,
    }


# ─── one_sided_p ────────────────────────────────────────────────────────
class TestOneSidedP:
    def test_perfect_seven_zero(self):
        # 7:0 全单向：P(X≥7 | n=7) = 0.5^7 = 0.0078
        assert one_sided_p(7, 0) == pytest.approx(0.0078125)

    def test_zero_seven_direction_mismatch(self):
        # 方向相反：P(X≥0) = 1.0（必然不显著）
        assert one_sided_p(0, 7) == 1.0

    def test_six_one_below_confirm(self):
        # 6:1：P(X≥6 | n=7) = (1+7)*0.5^7 = 0.0625 > 0.05（双侧 0.125）——单侧也不达 0.05
        assert one_sided_p(6, 1) == pytest.approx(0.0625)

    def test_seven_one_confirm(self):
        # 7:1：P(X≥7 | n=8) = (1+8)*0.5^8 = 0.035156
        assert one_sided_p(7, 1) == pytest.approx(0.03515625)
        assert one_sided_p(7, 1) < CONFIRM_P

    def test_no_discordant_pairs(self):
        assert one_sided_p(0, 0) == 1.0


# ─── effective_pair / detection_summary ────────────────────────────────
class TestPairing:
    def test_effective_pair_counts_and_none(self):
        a = {"t1": _row(1.0), "t2": _row(0.0), "t3": _row(1.0), "t4": _row(None)}
        b = {"t1": _row(0.0), "t2": _row(1.0), "t3": _row(1.0), "t4": _row(1.0)}
        a_pos, b_pos, n = effective_pair(a, b)
        assert (a_pos, b_pos, n) == (1, 1, 3)  # t4 双方有一侧 None → 不进配对

    def test_pair_missing_task_ignored(self):
        a = {"t1": _row(1.0), "t2": _row(1.0)}
        b = {"t1": _row(0.0)}
        assert effective_pair(a, b) == (1, 0, 1)

    def test_detection_summary_denominator(self):
        rows = {"t1": _row(1.0), "t2": _row(1.0), "t3": _row(0.0), "t4": _row(None)}
        s = detection_summary(rows)
        assert s == {"denominator_rows": 4, "measurable": 3, "positive": 2, "rate": 0.6667}

    def test_detection_summary_empty_measurable(self):
        s = detection_summary({"t1": _row(None)})
        assert s["rate"] is None


# ─── 41 口径切分 ────────────────────────────────────────────────────────
class TestDefectProgramSplit:
    def test_excludes_test_suffix(self):
        rows = {
            "quixbugs__breadth_first_search": _row(),
            "quixbugs__breadth_first_search_test": _row(),
            "quixbugs__bucketsort": _row(),
        }
        assert defect_program_ids(rows) == {"quixbugs__breadth_first_search", "quixbugs__bucketsort"}


# ─── domain_stats ───────────────────────────────────────────────────────
class TestDomainStats:
    def test_buckets_none_and_values(self):
        rows = {
            "t1": _row(sra="attempted_replaced"),
            "t2": _row(sra="attempted_fallback"),
            "t3": _row(sra=None),
            "t4": _row(sra="attempted_replaced"),
        }
        assert domain_stats(rows, "spec_replace_applied") == {
            "attempted_fallback": 1,
            "attempted_replaced": 2,
            "none": 1,
        }

    def test_subset_filter(self):
        rows = {"t1": _row(sra="attempted_replaced"), "t2": _row(sra=None)}
        assert domain_stats(rows, "spec_replace_applied", {"t1"}) == {"attempted_replaced": 1}


# ─── decide（预注册判定边界）─────────────────────────────────────────────
class TestDecide:
    def _c(self, p1, delta=8.0):
        return {"p_one_sided": p1, "delta_pp": delta}

    def test_confirmed_requires_both_conditions(self):
        d = decide(self._c(0.03), 0.65)
        assert d["verdict"] == "confirmed"
        assert d["conditions"]["absolute_line"]["met"] is True

    def test_rate_below_threshold_blocks_confirmed(self):
        # p 显著但 rate=0.55 < 0.60 → 非 confirmed（且 p<0.10 ∧ δ>0 → trend）
        d = decide(self._c(0.03), 0.55)
        assert d["verdict"] == "trend"
        assert d["conditions"]["absolute_line"]["met"] is False

    def test_trend_band(self):
        d = decide(self._c(0.07), 0.65)
        assert d["verdict"] == "trend"

    def test_not_confirmed_when_p_high(self):
        d = decide(self._c(0.20), 0.65)
        assert d["verdict"] == "not_confirmed"

    def test_not_confirmed_when_direction_negative(self):
        # p=0.07 但 δ<0（方向为负）→ 不满足 trend 方向条件
        d = decide(self._c(0.07, delta=-8.0), 0.65)
        assert d["verdict"] == "not_confirmed"

    def test_fail_line_flagged_independently(self):
        d = decide(self._c(0.5, delta=-20.0), 0.45)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is True
        assert FAIL_LINE > 0.45  # 失败线常量即预注册 50% 线

    def test_rate_none_safe(self):
        d = decide(self._c(1.0, delta=0.0), None)
        assert d["verdict"] == "not_confirmed"
        assert d["fail_line_triggered"] is None


# ─── contrast / load_arm_rows / build_analysis（端到端，临时文件）──────
class TestContrastAndLoad:
    def test_contrast_delta_and_p(self):
        a = {"t1": _row(1.0), "t2": _row(1.0), "t3": _row(0.0)}
        b = {"t1": _row(0.0), "t2": _row(1.0), "t3": _row(1.0)}
        c = contrast(a, b)
        assert c["a_only"] == 1 and c["b_only"] == 1 and c["n_pairs"] == 3
        assert c["delta_pp"] == 0.0
        assert c["p_one_sided"] == 0.75  # 1:1 → P(X≥1 | n=2) = 0.75（方向不符即不显著）

    def test_load_arm_auto_single(self, tmp_path):
        art = {
            "results": {
                "plain_llm_df_spec": {
                    "details": [
                        {"task_id": "t1", "detection_rate": 1.0, "spec_replace_applied": "attempted_replaced"},
                    ]
                }
            }
        }
        p = tmp_path / "a.json"
        p.write_text(json.dumps(art), encoding="utf-8")
        rows = load_arm_rows(p)
        assert rows["t1"]["detection_rate"] == 1.0
        assert rows["t1"]["spec_replace_applied"] == "attempted_replaced"

    def test_load_arm_ambiguous_raises(self, tmp_path):
        art = {
            "results": {
                "a": {"details": [{"task_id": "t1"}]},
                "b": {"details": [{"task_id": "t1"}]},
            }
        }
        p = tmp_path / "a.json"
        p.write_text(json.dumps(art), encoding="utf-8")
        with pytest.raises(MissingArtifactError):
            load_arm_rows(p)

    def test_load_arm_missing_file(self, tmp_path):
        with pytest.raises(MissingArtifactError):
            load_arm_rows(tmp_path / "nope.json")

    def test_load_arm_explicit_key_disambiguates(self, tmp_path):
        art = {
            "results": {
                "a": {"details": [{"task_id": "t1", "detection_rate": 1.0}]},
                "b": {"details": [{"task_id": "t1", "detection_rate": 0.0}]},
            }
        }
        p = tmp_path / "a.json"
        p.write_text(json.dumps(art), encoding="utf-8")
        rows = load_arm_rows(p, "b")
        assert rows["t1"]["detection_rate"] == 0.0

    def test_build_analysis_end_to_end(self, tmp_path):
        # 41 口径内 2 任务 + 1 个 _test；df_spec 净胜 1（1:0）
        def _art(arm, dets, sra):
            return {
                "results": {
                    arm: {
                        "details": [
                            {
                                "task_id": tid,
                                "detection_rate": det,
                                "spec_replace_applied": sra(tid),
                                "specificity_gate_verdict": None,
                            }
                            for tid, det in dets.items()
                        ]
                    }
                }
            }

        ids = ["quixbugs__a", "quixbugs__b", "quixbugs__a_test"]
        a = _art("plain_llm_df_spec", dict(zip(ids, [1.0, 1.0, None], strict=True)), lambda t: "attempted_replaced")
        b = _art("plain_llm_df", dict(zip(ids, [0.0, 1.0, None], strict=True)), lambda t: None)
        pa, pb = tmp_path / "a.json", tmp_path / "b.json"
        pa.write_text(json.dumps(a), encoding="utf-8")
        pb.write_text(json.dumps(b), encoding="utf-8")
        out = build_analysis(pa, pb, "plain_llm_df_spec", "plain_llm_df")
        assert out["df_spec"]["detection_41"]["positive"] == 2
        assert out["df"]["detection_41"]["positive"] == 1
        assert out["contrast_41"]["a_only"] == 1 and out["contrast_41"]["n_pairs"] == 2
        assert out["decision"]["conditions"]["absolute_line"]["threshold"] == SUCCESS_LINE
        assert out["audit"]["spec_replace_applied_dfspec"]["attempted_replaced"] == 3
