"""BP（2026-10-22）：统计对照面把「这一行没记录污染级别」折成沉默 —— 收口锁。

缺陷族（BH→BP 系列第 8 面）。同一批 `details` 行、同一个"行内没有
`contamination_risk_level`"的事实，在两个消费者手里去向不同（改前实测，零 LLM）：

1. `analysis_parts/cross_analysis._contamination_cross_analysis` 用一条
   `if not level: continue`——缺席行**不进任何桶也不计数**。归档 320 个臂上
   2093 行 key_absent（value_null / 空串 0 行），读者只看到 `by_risk_level`
   合计比行数少，或整节 `available=False` 从报告里消失；"这批 30 行全都没记录"
   与"根本没有行"同形，后者又与"这一节没跑"同形。
2. `statistical_analysis.contamination_view_summary` 用 `row.get(...) or "unknown"`
   ——缺席行**并进 unknown**，与"检测腿跑了但判不了"同计数。
3. 渲染层 5.3 表按第 ①种口径算「未入对照任务」列（三档合计），脚注却按第 ②种
   口径解释它（"未记录表示 unknown"）——两表之差正好是被丢掉的缺席行数，无处对账。
4. `high_vs_low_success_delta`：docstring 声明 `float | None`，代码两档不齐时是
   「键不存在」；归档 198 个 available 臂里 **0 个**有该键（157 个 high、low 双缺，
   41 个缺 high）⇒ 高 vs 低对照从未产出一个数，而 5.3 的解读句写着
   "若差异 ≤0.2，说明污染效应不显著，结果可信度较高"，N/A 被顺着读成有利判定。

修复口径：**只把沉默换成分档披露，判定值与方向一个都不动**。本轮用"逐字重写改前
算法再对比"锁住这一点（`_pre_bp_cross` / `_pre_bp_view`）；披露走平行键
（`n_details` / `unobserved` / `unobserved_total` / `reason` /
`delta_missing_buckets` / `unknown_of_which_absent`），因此两消费者可对账：
`view.counts["unknown"] == 真 unknown 行数 + cross.unobserved_total`。

空白串（`" "`）不算缺席：它在两侧都是真值，改前本函数也把它记作观测到并自成一档；
把它划进缺席会让恒等式在多出一个空格字符时失效——故只把精确空串记作 `value_blank`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
from experiments.analysis_parts.cross_analysis import _contamination_cross_analysis
from experiments.statistical_analysis import _contamination_view_report_lines, contamination_view_summary

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
UNOBSERVED_KEYS = ("key_absent", "value_null", "value_blank", "other_falsy")
# 真归档不变量复算只取排序后前 8 份批次文件（口径写进断言消息，不宣称覆盖全库）
ARCHIVE_FILES = 8

_ABSENT = object()


def _row(level: Any = _ABSENT, *, passed: bool = True) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": "t", "passed": passed}
    if level is not _ABSENT:
        row["contamination_risk_level"] = level
    return row


def _md(arms: dict[str, list[dict[str, Any]]]) -> str:
    results = {name: {"details": rows, "success_rate": 0.0} for name, rows in arms.items()}
    return ar_mod.render_markdown(ar_mod.build_analysis({"dataset": "demo", "results": results}), "demo.json")


def _pre_bp_cross(details: list[dict[str, Any]]) -> dict[str, Any]:
    """改前 `_contamination_cross_analysis` 逐字重写：用于证明桶数值与判定逐位不变。"""
    observed = 0
    by_level: dict[str, dict[str, Any]] = {}
    for row in details:
        level = row.get("contamination_risk_level")
        if not level:
            continue
        observed += 1
        stat = by_level.setdefault(str(level), {"tasks": 0, "passed": 0})
        stat["tasks"] += 1
        if row.get("passed"):
            stat["passed"] += 1
    if observed == 0:
        return {"available": False, "by_risk_level": {}}
    result: dict[str, Any] = {"available": True, "by_risk_level": {}}
    for level, stat in by_level.items():
        total = stat["tasks"]
        result["by_risk_level"][level] = {
            "tasks": total,
            "passed": stat["passed"],
            "success_rate": round(stat["passed"] / total, 4) if total else 0.0,
        }
    high_rate = result["by_risk_level"].get("high", {}).get("success_rate")
    low_rate = result["by_risk_level"].get("low", {}).get("success_rate")
    if high_rate is not None and low_rate is not None:
        result["high_vs_low_success_delta"] = round(high_rate - low_rate, 4)
    return result


def _pre_bp_view(data: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """批次 IX 改前 `contamination_view_summary` 逐字重写（无 unknown_of_which_absent）。"""
    summary: dict[str, dict[str, Any]] = {}
    for baseline in sorted(data):
        counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0, "not_applicable": 0}
        cont_pass = cont_n = clean_pass = clean_n = 0
        for row in data[baseline] or []:
            level = row.get("contamination_risk_level") or "unknown"
            counts[level] = counts.get(level, 0) + 1
            if level in ("high", "medium"):
                cont_n += 1
                cont_pass += 1 if row.get("passed") else 0
            elif level == "low":
                clean_n += 1
                clean_pass += 1 if row.get("passed") else 0
        summary[baseline] = {
            "counts": counts,
            "contaminated_passed_rate": round(cont_pass / cont_n, 4) if cont_n else None,
            "clean_passed_rate": round(clean_pass / clean_n, 4) if clean_n else None,
        }
    return summary


_CORPUS: list[list[dict[str, Any]]] = [
    [],
    [_row()],
    [_row("high"), _row("high", passed=False), _row("low", passed=False)],
    [_row("low"), _row(), _row(None), _row(""), _row(0), _row(False)],
    [_row("unknown"), _row("not_applicable"), _row("medium"), _row()],
    [_row(" "), _row("  "), _row("off_vocab")],
    [_row(), _row(), _row()],
]


# ─── 一、缺席的四种形状各有一档，不再混作"没这回事" ────────────────────────


class TestAbsentShapesGetTheirOwnGrades:
    @pytest.mark.parametrize(
        ("row", "grade"),
        [
            (_row(), "key_absent"),
            (_row(None), "value_null"),
            (_row(""), "value_blank"),
            (_row(0), "other_falsy"),
            (_row(False), "other_falsy"),
            (_row([]), "other_falsy"),
        ],
    )
    def test_single_absent_row_lands_in_its_own_grade(self, row: dict[str, Any], grade: str) -> None:
        result = _contamination_cross_analysis([row])
        assert result["unobserved"][grade] == 1
        assert result["unobserved_total"] == 1
        assert result["n_details"] == 1
        assert result["by_risk_level"] == {}

    def test_four_grades_counted_separately(self) -> None:
        result = _contamination_cross_analysis([_row(), _row(None), _row(""), _row(0)])
        assert result["available"] is False
        assert result["reason"] == "no_level_recorded"
        assert result["unobserved"] == {k: 1 for k in UNOBSERVED_KEYS}
        assert result["unobserved_total"] == 4
        assert result["n_details"] == 4

    def test_whitespace_level_is_observed_not_absent(self) -> None:
        """批次 IX 消费侧把 " " 当真值自成一档 ⇒ 本函数不能把它划进缺席，否则恒等式失效。"""
        result = _contamination_cross_analysis([_row(" ")])
        assert result["available"] is True
        assert result["unobserved_total"] == 0
        assert result["by_risk_level"][" "] == {"tasks": 1, "passed": 1, "success_rate": 1.0}

    def test_rows_present_and_no_rows_are_two_different_reasons(self) -> None:
        assert _contamination_cross_analysis([])["reason"] == "no_rows"
        assert _contamination_cross_analysis([_row(), _row(None)])["reason"] == "no_level_recorded"

    def test_mixed_corpus_still_available_but_counts_the_absent(self) -> None:
        result = _contamination_cross_analysis([_row("low"), _row(), _row()])
        assert result["available"] is True
        assert result["unobserved"]["key_absent"] == 2
        assert result["by_risk_level"]["low"]["tasks"] == 1


# ─── 二、判定值与方向零变化（逐字对比改前算法）────────────────────────────


class TestJudgmentValuesDidNotMove:
    @pytest.mark.parametrize("details", _CORPUS)
    def test_cross_buckets_and_available_bit_identical_to_pre_bp(self, details: list[dict[str, Any]]) -> None:
        cur = _contamination_cross_analysis(details)
        old = _pre_bp_cross(details)
        assert cur["available"] is old["available"]
        assert cur["by_risk_level"] == old["by_risk_level"]
        if "high_vs_low_success_delta" in old:
            assert cur["high_vs_low_success_delta"] == old["high_vs_low_success_delta"]

    @pytest.mark.parametrize("details", _CORPUS)
    def test_view_counts_and_rates_bit_identical_to_batch_ix(self, details: list[dict[str, Any]]) -> None:
        data = {"arm": details}
        cur = contamination_view_summary(data)
        old = _pre_bp_view(data)
        assert cur["arm"]["counts"] == old["arm"]["counts"]
        assert cur["arm"]["contaminated_passed_rate"] == old["arm"]["contaminated_passed_rate"]
        assert cur["arm"]["clean_passed_rate"] == old["arm"]["clean_passed_rate"]
        assert "unknown_of_which_absent" not in old["arm"]

    @pytest.mark.parametrize("details", _CORPUS)
    def test_absent_rows_never_enter_a_compared_bucket(self, details: list[dict[str, Any]]) -> None:
        """分档不是判成某一档：未记录行既不进 high/low 对照，也不进 unknown 桶（cross 侧）。"""
        cur = _contamination_cross_analysis(details)
        assert set(cur["by_risk_level"]).isdisjoint(UNOBSERVED_KEYS)
        bucketed = sum(int(block["tasks"]) for block in cur["by_risk_level"].values())
        assert bucketed + cur["unobserved_total"] == cur["n_details"] == len(details)


# ─── 三、delta：把 None 落到位并点名缺失档 ───────────────────────────────


class TestDeltaIsAnExplicitNone:
    def test_both_buckets_missing_names_both(self) -> None:
        result = _contamination_cross_analysis([_row("medium"), _row("unknown")])
        assert result["available"] is True
        assert "high_vs_low_success_delta" in result
        assert result["high_vs_low_success_delta"] is None
        assert result["delta_missing_buckets"] == ["high", "low"]

    def test_only_high_missing_names_high(self) -> None:
        result = _contamination_cross_analysis([_row("low"), _row("low", passed=False)])
        assert result["high_vs_low_success_delta"] is None
        assert result["delta_missing_buckets"] == ["high"]

    def test_computable_delta_carries_no_missing_buckets(self) -> None:
        result = _contamination_cross_analysis([_row("high"), _row("low", passed=False)])
        assert result["high_vs_low_success_delta"] == pytest.approx(1.0)
        assert "delta_missing_buckets" not in result


# ─── 四、两消费者可对账（批次 IX 口径并计 unknown，差值即缺席行数）──────────


class TestTwoConsumersReconcile:
    @pytest.mark.parametrize("details", _CORPUS)
    def test_unknown_identity(self, details: list[dict[str, Any]]) -> None:
        cross = _contamination_cross_analysis(details)
        view = contamination_view_summary({"arm": details})["arm"]
        true_unknown = int(cross["by_risk_level"].get("unknown", {}).get("tasks", 0))
        assert int(view["counts"].get("unknown", 0)) == true_unknown + int(cross["unobserved_total"])

    @pytest.mark.parametrize("details", _CORPUS)
    def test_absent_rows_identity(self, details: list[dict[str, Any]]) -> None:
        cross = _contamination_cross_analysis(details)
        view = contamination_view_summary({"arm": details})["arm"]
        assert int(view["unknown_of_which_absent"]) == int(cross["unobserved_total"])

    def test_view_discloses_its_own_fold(self) -> None:
        view = contamination_view_summary({"arm": [_row("unknown"), _row(), _row(None)]})["arm"]
        assert view["counts"]["unknown"] == 3
        assert view["unknown_of_which_absent"] == 2


# ─── 五、渲染层 5.3：沉默的臂点名、未入对照列补齐、N/A 不再被读成有利 ──────


class TestSectionFiveThreeDiscloses:
    def test_silent_arm_is_named_instead_of_dropped(self) -> None:
        md = _md({"记录过": [_row("high"), _row("low", passed=False)], "全没记录": [_row(), _row(), _row()]})
        assert "## 失败分析 × 污染检测交叉（5.3）" in md
        assert "本节未列出 1 个基线" in md
        assert "`全没记录`（3 行全部未记录，原因 no_level_recorded）" in md
        assert "**不是「检测干净」，也不是「没有任务」**" in md

    def test_zero_row_arm_is_not_reported_as_unrecorded(self) -> None:
        md = _md({"有行": [_row("high"), _row("low")], "空臂": [], "全没记录": [_row()]})
        line = next(ln for ln in md.splitlines() if ln.startswith("> 本节未列出"))
        assert "本节未列出 1 个基线" in line
        assert "`空臂`" not in line
        assert "`全没记录`" in line

    def test_section_survives_when_no_arm_is_comparable(self) -> None:
        """全部臂都不可对照时本节仍要出现：改前它随 filter 一起消失（P14 锚点）。"""
        md = _md({"全没记录": [_row(), _row()], "空臂": []})
        assert "## 失败分析 × 污染检测交叉（5.3）" in md
        assert "| 基线 | 高污染任务 |" not in md
        assert "> 本节未列出 1 个基线：`全没记录`（2 行全部未记录，原因 no_level_recorded）。" in md

    def test_uncompared_column_includes_unrecorded_rows(self) -> None:
        details = [_row("high"), _row("low", passed=False), _row(), _row(None), _row("")]
        md = _md({"混合": details})
        assert "| 混合 | 1 | 1.0 | 1 | 0.0 | 1.0000 | 3 |" in md
        assert "再加行内未记录该字段的行数" in md

    def test_missing_bucket_named_in_the_delta_cell(self) -> None:
        md = _md({"只有低污染": [_row("low"), _row("low", passed=False)]})
        assert "| N/A（high 档无行） |" in md
        assert "| N/A（high、low 档无行） |" in _md({"只有中污染": [_row("medium")]})

    def test_all_na_table_refuses_the_favorable_reading(self) -> None:
        md = _md({"a": [_row("low")], "b": [_row("medium")]})
        assert "本表全部臂的「成功率差（高-低）」都是 N/A" in md
        assert "也读不出「污染效应不显著、结果可信度较高」" in md
        # 只要有一个臂算得出差，就不该出现这句（防把披露写成常驻文案）
        md2 = _md({"a": [_row("high"), _row("low")]})
        assert "本表全部臂的「成功率差（高-低）」都是 N/A" not in md2

    def test_bm_footnote_substring_survives_but_no_longer_calls_absent_unknown(self) -> None:
        md = _md({"a": [_row("high"), _row("low"), _row("medium"), _row("unknown"), _row("not_applicable")]})
        assert "未入对照任务」= medium/unknown/not_applicable" in md
        assert "`if not level: continue` 静默丢弃的未记录行也计入本列" in md
        assert "改前脚注把「未记录」也写成 unknown" in md

    def test_no_data_at_all_still_leaves_the_section_out(self) -> None:
        """真「没有行」不冒充「有行但没记录」：两者仍分得开，前者不渲染。"""
        assert "## 失败分析 × 污染检测交叉（5.3）" not in _md({"空": []})

    def test_view_report_lines_disclose_absent_composition(self) -> None:
        with_absent = contamination_view_summary({"a": [_row(), _row("low")]})
        lines = _contamination_view_report_lines(with_absent)
        assert any("unknown 列含 1 行「行内未记录 contamination_risk_level」" in ln for ln in lines)
        without = contamination_view_summary({"a": [_row("low")]})
        assert not any("行内未记录" in ln for ln in _contamination_view_report_lines(without))


# ─── 六、锚点在源码里（防披露被整段删掉）────────────────────────────────


class TestDisclosureAnchorsInSource:
    def test_cross_analysis_discloses_shapes(self) -> None:
        src = (ROOT / "experiments/analysis_parts/cross_analysis.py").read_text(encoding="utf-8")
        assert 'unobserved["key_absent"] += 1' in src
        assert 'if "contamination_risk_level" not in row:' in src
        assert '"reason": "no_rows" if not details else "no_level_recorded"' in src
        assert 'result["delta_missing_buckets"]' in src

    def test_view_summary_keeps_historical_counts_literal(self) -> None:
        src = (ROOT / "experiments/statistical_analysis.py").read_text(encoding="utf-8")
        assert '"unknown_of_which_absent": absent_rows' in src
        assert 'level = recorded or "unknown"' in src
        assert '"high": 0, "medium": 0, "low": 0, "unknown": 0, "not_applicable": 0' in src

    def test_renderer_adds_unobserved_to_excluded(self) -> None:
        src = (ROOT / "experiments/analyze_results.py").read_text(encoding="utf-8")
        assert 'excluded += int(cc.get("unobserved_total", 0))' in src
        assert "silent_cross_arms" in src
        assert 'cc.get("delta_missing_buckets")' in src


# ─── 七、真归档不变量复算（有界样本）──────────────────────────────────


def test_archive_invariants_hold_on_bounded_sample() -> None:
    paths = sorted(RESULTS.rglob("benchmark_*.json"))[:ARCHIVE_FILES]
    if not paths:
        pytest.skip("归档批次文件不存在")
    checked = 0
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, dict):
            continue
        for arm, block in results.items():
            if not isinstance(block, dict) or not isinstance(block.get("details"), list):
                continue
            details = block["details"]
            if not all(isinstance(row, dict) for row in details):
                continue
            cross = _contamination_cross_analysis(details)
            view = contamination_view_summary({str(arm): details})[str(arm)]
            bucketed = sum(int(blk["tasks"]) for blk in cross["by_risk_level"].values())
            assert bucketed + int(cross["unobserved_total"]) == len(details), (path, arm)
            true_unknown = int(cross["by_risk_level"].get("unknown", {}).get("tasks", 0))
            assert int(view["counts"].get("unknown", 0)) == true_unknown + int(cross["unobserved_total"]), (path, arm)
            assert int(view["unknown_of_which_absent"]) == int(cross["unobserved_total"]), (path, arm)
            checked += 1
    assert checked, f"前 {ARCHIVE_FILES} 份批次文件里没有任何可比对的臂"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
