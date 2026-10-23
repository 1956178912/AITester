"""BQ（2026-10-22）：报告读侧把四个 status 通道当作不存在 —— 收口锁。

缺陷族（BH→BP 系列第 9 面，"写了没人读"）。改前实测（零 LLM，
`scripts/tools/bq_check_leg_probe.py` A/B 段，全部只读）：

1. **报告面零行读者**。BM 轮给 `contract_status` 接的是**生产侧透传**
   （`_build_risk_summary_for_result` 的 `contract_status=final_state.get(...)`）；
   BN 轮把四个 status 通道（contract / static / safety / oracle）写进结果行
   两分支与 raw 白名单。但 `experiments/` + `scripts/` 184 个 .py 里，从
   **details 行**读这四个键的消费者 = **0**（`build_analysis` 的 30 个指标
   助手无一读、`run_main_batch` 摘要块不列、`statistical_analysis` 不读）。
   对照组：`contract_missing_symbols` 有 1 个真实行读者
   （`scripts/tools/refresh_patch_field.py:201`，`row.get(...) or []`）。
2. **后果**：归档与新批次里"这条腿跑过且干净（ok）"与"崩了（error）/
   按设计没跑（disabled）/ 材料缺失（unavailable）/ 没记录（null / absent）"
   在所有报告面同形——BG→BN 七轮的披露链在实验侧断在最后一步。
3. **归档读数**（1702 个 JSON，可解析 1594）：四键出现 = **0**
   （BN 之后没有批次跑过）；`contract_missing_symbols` 8865 处是 BL 之前
   的历史行（8853 None + 12 非平凡）。

修复口径：**只补读侧披露，判定值与方向一处不动**。`_check_leg_measurability`
按七档计数（ok / disabled / unavailable / error / null / absent / other），
每通道满足 `Σ分档 == n_rows`；报告章节与批次摘要行只让分档可见——四个键
不进入任何判定，既不被翻成通过也不被翻成拒绝。归档"0 出现"是**实测读数**
（写进手册），不是锁：真批次一旦落盘，恒等式锁仍然成立，"0 出现"要按新
读数重新登记，故本文件只锁恒等式与披露形状，不锁"归档必须为 0"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
from experiments.analysis_parts.check_leg_analysis import (
    CHECK_LEG_CHANNELS,
    CHECK_LEG_LABELS,
    _check_leg_measurability,
)
from experiments.run_main_batch import _print_r4_summary

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
ARCHIVE_FILES = 8

_ABSENT = object()
VOCAB = ("ok", "disabled", "unavailable", "error")

#: build_analysis 的 per_baseline 既有键集（棘轮：只允许多出 check_leg_measurability 一个新键）
_EXPECTED_PER_BASELINE_KEYS = {
    "total_functions",
    "passed_count",
    "success_rate",
    "avg_coverage",
    "avg_iterations",
    "avg_elapsed_seconds",
    "total_time",
    "token_metrics",
    "rag_metrics",
    "failure_category_distribution",
    "details_rag_by_kind",
    "rag_hit_by_failure_category",
    "repair_convergence_metrics",
    "repair_convergence_curve",
    "test_smell_metrics",
    "quality_proxy_metrics",
    "convergence_token_efficiency",
    "difficulty_stratified_iterations",
    "rag_token_efficiency",
    "rag_similarity_distribution",
    "failure_root_cause_trend",
    "contamination_cross_analysis",
    "contamination_report",
    "boundary_coverage_metrics",
    "mutation_score_metrics",
    "fl_at_k_metrics",
    "m1_metrics",
    "convergence_failure_modes",
    "execution_trace_metrics",
    "_details",
}


def _row(**legs: Any) -> dict[str, Any]:
    """构造结果行；不传的键即"键缺席"（BN 之前的历史批次形状）。"""
    return {"task_id": "t", "passed": True, **legs}


def _all(grade: Any) -> dict[str, Any]:
    return {channel: grade for channel in CHECK_LEG_CHANNELS}


def _md(arms: dict[str, list[dict[str, Any]]]) -> str:
    results = {name: {"details": rows, "success_rate": 0.0} for name, rows in arms.items()}
    return ar_mod.render_markdown(ar_mod.build_analysis({"dataset": "demo", "results": results}), "demo.json")


def _batch(tmp_path: Path, details: list[dict[str, Any]]) -> Path:
    p = tmp_path / "batch.json"
    p.write_text(json.dumps({"results": {"b": {"details": details}}}), encoding="utf-8")
    return p


# ─── 一、七档各就各位：词表四值 + null / absent / other ──────────────────


class TestGradesCountEveryShape:
    @pytest.mark.parametrize("grade", VOCAB)
    def test_vocabulary_value_lands_in_its_own_grade(self, grade: str) -> None:
        result = _check_leg_measurability([_row(**_all(grade))])
        for channel in CHECK_LEG_CHANNELS:
            counts = result["channels"][channel]
            assert counts[grade] == 1
            assert sum(counts[g] for g in (*VOCAB, "null", "absent", "other")) == 1

    def test_null_is_not_absent_and_not_ok(self) -> None:
        result = _check_leg_measurability([_row(**_all(None))])
        for channel in CHECK_LEG_CHANNELS:
            counts = result["channels"][channel]
            assert counts["null"] == 1
            assert counts["absent"] == 0
            assert counts["ok"] == 0

    def test_key_absent_is_not_null(self) -> None:
        result = _check_leg_measurability([_row()])
        for channel in CHECK_LEG_CHANNELS:
            counts = result["channels"][channel]
            assert counts["absent"] == 1
            assert counts["null"] == 0

    @pytest.mark.parametrize("value", ["OK", 1, [], {}, True, "ok "])
    def test_off_vocabulary_value_gets_its_own_grade_with_details(self, value: Any) -> None:
        """词表外真值自成一档并带明细：防 "OK"/1 被静默算进 ok。"""
        result = _check_leg_measurability([_row(**_all(value))])
        for channel in CHECK_LEG_CHANNELS:
            counts = result["channels"][channel]
            assert counts["other"] == 1
            assert counts["other_values"] == [value]
            assert counts["ok"] == 0

    def test_off_vocabulary_details_deduplicate_per_channel(self) -> None:
        result = _check_leg_measurability([_row(static_check_status="OK"), _row(static_check_status="OK")])
        assert result["channels"]["static_check_status"]["other"] == 2
        assert result["channels"]["static_check_status"]["other_values"] == ["OK"]

    def test_mixed_row_counts_each_channel_independently(self) -> None:
        result = _check_leg_measurability(
            [_row(contract_status="ok", static_check_status="error", safety_check_status="disabled")]
        )
        assert result["channels"]["contract_status"]["ok"] == 1
        assert result["channels"]["static_check_status"]["error"] == 1
        assert result["channels"]["safety_check_status"]["disabled"] == 1
        # 没写键的通道记缺席，不记 null
        assert result["channels"]["oracle_check_status"]["absent"] == 1


# ─── 二、恒等式：分档合计 = 行数；记录行数；不可测行数 ────────────────────


_CORPUS: list[list[dict[str, Any]]] = [
    [],
    [_row()],
    [_row(**_all("ok"))],
    [_row(**_all(None))],
    [_row(contract_status="error"), _row(), _row(static_check_status="unavailable")],
    [_row(**_all("ok")), _row(**_all("disabled")), _row(**_all("error")), _row(**_all(None)), _row()],
    [_row(contract_status="ok", static_check_status="OK", safety_check_status=None)],
    [_row(**_all("ok"))] * 7,
]


class TestIdentitiesHold:
    @pytest.mark.parametrize("details", _CORPUS)
    def test_channel_grades_sum_to_n_rows(self, details: list[dict[str, Any]]) -> None:
        result = _check_leg_measurability(details)
        for channel in CHECK_LEG_CHANNELS:
            counts = result["channels"][channel]
            total = sum(counts[g] for g in (*VOCAB, "null", "absent", "other"))
            assert total == result["n_rows"] == len(details), (channel, counts)

    @pytest.mark.parametrize("details", _CORPUS)
    def test_recorded_rows_excludes_all_absent_rows(self, details: list[dict[str, Any]]) -> None:
        result = _check_leg_measurability(details)
        all_absent = sum(1 for row in details if not any(c in row for c in CHECK_LEG_CHANNELS))
        assert result["recorded_rows"] == len(details) - all_absent

    @pytest.mark.parametrize("details", _CORPUS)
    def test_unmeasurable_rows_never_exceed_recorded(self, details: list[dict[str, Any]]) -> None:
        result = _check_leg_measurability(details)
        assert 0 <= result["rows_any_unmeasurable"] <= result["recorded_rows"]

    def test_available_matches_recorded_rows(self) -> None:
        assert _check_leg_measurability([_row()])["available"] is False
        assert _check_leg_measurability([_row(contract_status=None)])["available"] is True
        assert _check_leg_measurability([])["available"] is False


class TestRowsAnyUnmeasurable:
    def test_counts_row_once_when_several_legs_fail(self) -> None:
        details = [_row(contract_status="error", static_check_status="unavailable")]
        assert _check_leg_measurability(details)["rows_any_unmeasurable"] == 1

    def test_disabled_is_not_unmeasurable(self) -> None:
        assert _check_leg_measurability([_row(**_all("disabled"))])["rows_any_unmeasurable"] == 0

    def test_null_and_absent_are_not_unmeasurable(self) -> None:
        assert _check_leg_measurability([_row(**_all(None)), _row()])["rows_any_unmeasurable"] == 0

    def test_ok_is_not_unmeasurable(self) -> None:
        assert _check_leg_measurability([_row(**_all("ok"))])["rows_any_unmeasurable"] == 0


class TestReasonTwoGrades:
    def test_no_rows(self) -> None:
        result = _check_leg_measurability([])
        assert result["reason"] == "no_rows"
        assert result["available"] is False

    def test_rows_but_nothing_recorded(self) -> None:
        result = _check_leg_measurability([_row(), _row()])
        assert result["reason"] == "no_channel_recorded"
        assert result["available"] is False

    def test_recorded_rows_have_no_reason(self) -> None:
        assert _check_leg_measurability([_row(**_all("ok"))])["reason"] is None


# ─── 三、判定不动：既有键集只多一个新键，既有章节一行不改 ──────────────────


class TestJudgmentValuesDidNotMove:
    """build_analysis 的既有输出一个键不动：新读者走平行键。"""

    def _analysis(self) -> dict[str, Any]:
        details = [
            {
                "task_id": "t1",
                "passed": True,
                "iterations": 1,
                "coverage": 0.5,
                "elapsed_seconds": 1.0,
                "detection_rate": 1.0,
                "repair_rate": 1.0,
                "false_fix_rate": 0.0,
                "contract_status": "ok",
                "static_check_status": "error",
                "safety_check_status": "ok",
                "oracle_check_status": None,
            },
            {
                "task_id": "t2",
                "passed": False,
                "iterations": 2,
                "coverage": 0.1,
                "elapsed_seconds": 2.0,
                "detection_rate": None,
                "repair_rate": None,
                "false_fix_rate": None,
            },
        ]
        data = {
            "dataset": "demo",
            "results": {
                "aitester": {
                    "details": details,
                    "total_functions": 2,
                    "passed_count": 1,
                    "success_rate": 50.0,
                    "avg_coverage": 0.3,
                    "avg_iterations": 1.5,
                    "avg_elapsed_seconds": 1.5,
                    "total_time": 3.0,
                }
            },
        }
        return ar_mod.build_analysis(data)

    def test_per_baseline_key_set_is_ratcheted_by_registered_keys(self) -> None:
        keys = set(self._analysis()["per_baseline"]["aitester"])
        # BQ 断言的形态是"恰好 +1 键"；BT 轮（2026-10-22）再 +1：
        # `oracle_provenance`（验收 oracle 来源与可见性的读侧对账）；
        # BU 轮（2026-10-22）再 +1：`self_repair_trap_domain`
        # （Self-Repair Trap 判定核输入可达域的读侧分档）。
        # BV 轮（2026-10-23）再 +1：`detector_silence`（批次 VIII/XIV
        # 两份判定核的沉默分档读侧）。键集棘轮只增不删，新增键必须在此
        # 显式登记（不放行任意新键）。
        assert keys == _EXPECTED_PER_BASELINE_KEYS | {
            "check_leg_measurability",
            "oracle_provenance",
            "self_repair_trap_domain",
            "detector_silence",
        }

    def test_existing_values_unchanged_by_the_new_key(self) -> None:
        per = self._analysis()["per_baseline"]["aitester"]
        assert per["total_functions"] == 2
        assert per["passed_count"] == 1
        assert per["success_rate"] == 50.0
        assert per["avg_coverage"] == 0.3
        assert per["avg_iterations"] == 1.5
        # M1 既有口径：None 行不计分母（1/2 可测），与新键无关
        assert per["m1_metrics"]["available"] is True
        assert per["m1_metrics"]["total_tasks"] == 2
        assert per["m1_metrics"]["metrics"]["detection_rate"] == {"observed": 1, "mean": 1.0}
        assert per["m1_metrics"]["metrics"]["test_error_rate"] == {"observed": 0, "mean": None}
        assert per["contamination_cross_analysis"]["n_details"] == 2

    def test_existing_sections_render_unchanged(self) -> None:
        md = ar_mod.render_markdown(self._analysis(), "demo.json")
        assert "## M1 指标汇总（R2，None 不计入分母）" in md
        assert "## 失败分析 × 污染检测交叉（5.3）" in md
        # BP 轮的披露文案仍在（BQ 不覆盖前轮章节）
        assert "本节未列出 1 个基线" in md
        assert "原因 no_level_recorded" in md


# ─── 四、报告章节：分档可见、沉默臂点名、无常驻全零表 ────────────────────


class TestSectionDiscloses:
    def test_table_counts_each_grade_per_channel(self) -> None:
        details = [
            _row(contract_status="ok", static_check_status="ok", safety_check_status="ok", oracle_check_status="ok"),
            _row(
                contract_status="error",
                static_check_status=None,
                safety_check_status="disabled",
                oracle_check_status="unavailable",
            ),
            _row(contract_status="ok", static_check_status="OK", safety_check_status="ok", oracle_check_status="ok"),
        ]
        md = _md({"aitester": details})
        assert "## 检查腿可测量性（BQ：结果行四通道的读侧）" in md
        assert "| aitester | 命名契约腿 | 2 | 1 | 0 | 0 | 0 | 3 |" in md
        assert "| aitester | 静态检查腿 | 1 | 0 | 0 | 1 | 0 | 3 |" in md
        assert "| aitester | 安全预检腿 | 2 | 0 | 1 | 0 | 0 | 3 |" in md
        assert "| aitester | oracle 腿 | 2 | 1 | 0 | 0 | 0 | 3 |" in md
        assert "至少一条检查腿没测成的行合计 **1**" in md

    def test_off_vocabulary_values_are_named_not_silently_ok(self) -> None:
        md = _md(
            {
                "aitester": [
                    _row(
                        contract_status="ok",
                        static_check_status="OK",
                        safety_check_status="ok",
                        oracle_check_status="ok",
                    )
                ]
            }
        )
        assert "词表外取值（不进 ok 也不进任何否定档）" in md
        assert "`static_check_status` 出现词表外取值 ['OK'] ×1" in md

    def test_clean_batch_does_not_print_the_off_vocabulary_line(self) -> None:
        md = _md({"aitester": [_row(**_all("ok"))]})
        assert "词表外取值" not in md

    def test_silent_arm_is_named_instead_of_dropped(self) -> None:
        md = _md({"记录过": [_row(**_all("ok"))], "全没记录": [_row(), _row(), _row()]})
        assert "## 检查腿可测量性（BQ：结果行四通道的读侧）" in md
        assert "本节未列出 1 个基线" in md
        assert "`全没记录`（3 行四通道全部未记录，原因 no_channel_recorded）" in md
        assert "**不是「四腿都干净」，也不是「没有任务」**" in md

    def test_zero_row_arm_is_not_reported_as_unrecorded(self) -> None:
        """「没有行」与「有行但全没记录」是两件事：前者不进「未列出」。"""
        md = _md({"有记录": [_row(**_all("ok"))], "空臂": [], "全没记录": [_row()]})
        # 只取 BQ 章节的「未列出」行（BP 5.3 章节的同款句式按 contamination 口径渲染）
        line = next(ln for ln in md.splitlines() if ln.startswith("> 本节未列出") and "四通道全部未记录" in ln)
        assert "本节未列出 1 个基线" in line
        assert "`空臂`" not in line
        assert "`全没记录`" in line

    def test_section_survives_when_no_arm_is_recorded(self) -> None:
        """全部臂都未记录时本节仍要出现：改前它随 filter 一起消失。"""
        md = _md({"全没记录": [_row(), _row()], "空臂": []})
        assert "## 检查腿可测量性（BQ：结果行四通道的读侧）" in md
        assert "| 基线 | 通道 | ok |" not in md
        assert "> 本节未列出 1 个基线：`全没记录`（2 行四通道全部未记录，原因 no_channel_recorded）。" in md

    def test_no_rows_at_all_leaves_the_section_out(self) -> None:
        assert "## 检查腿可测量性" not in _md({"空": []})

    def test_mixed_arm_keeps_absent_column(self) -> None:
        md = _md({"混合": [_row(**_all("ok")), _row()]})
        assert "| 混合 | 命名契约腿 | 1 | 0 | 0 | 0 | 1 | 2 |" in md

    def test_caliber_note_states_keys_enter_no_judgment(self) -> None:
        md = _md({"a": [_row(**_all("ok"))], "b": [_row()]})
        assert "**四个键不进入任何判定**" in md
        assert "不把没测翻成通过，也不翻成拒绝" in md
        assert "`ok` 才是「检查完成且零疑点」" in md


# ─── 五、批次摘要行：与 R4/N1 同块同风格 ────────────────────────────────


class TestBatchSummaryLineDiscloses:
    def test_recorded_batch_prints_grade_counts(self, tmp_path: Path, capsys) -> None:
        details = [
            {
                "detection_rate": 1.0,
                "repair_rate": 1.0,
                "false_fix_rate": 0.0,
                "contract_status": "ok",
                "static_check_status": "ok",
                "safety_check_status": "ok",
                "oracle_check_status": "ok",
            },
            {
                "detection_rate": 1.0,
                "repair_rate": 1.0,
                "false_fix_rate": 0.0,
                "contract_status": "error",
                "static_check_status": None,
                "safety_check_status": "disabled",
            },
        ]
        _print_r4_summary(_batch(tmp_path, details))
        out = capsys.readouterr().out
        assert "BQ 检查腿（记录 2/2 行，任一腿没测成 1 行）" in out
        assert "命名契约腿 ok=1 没测成=1 没跑=0 未记录=0" in out
        assert "静态检查腿 ok=1 没测成=0 没跑=0 未记录=1" in out
        assert "安全预检腿 ok=1 没测成=0 没跑=1 未记录=0" in out
        assert "oracle 腿 ok=1 没测成=0 没跑=0 未记录=1" in out
        # 同块既有口径一行不动（BM 轮锁不破）
        assert "R4 regression_rate=不可测（无可测行）（可测 0/2）" in out

    def test_unrecorded_batch_says_unrecorded_not_zero(self, tmp_path: Path, capsys) -> None:
        """归档形状（四键缺席）：明写"未记录"，不打印会被读成"干净"的 0。"""
        details = [{"detection_rate": 1.0, "repair_rate": 1.0, "false_fix_rate": 0.0}]
        _print_r4_summary(_batch(tmp_path, details))
        out = capsys.readouterr().out
        assert "BQ 检查腿: 未记录（早于 BN 轮落盘，不可读作「干净」）" in out
        assert "BQ 检查腿（记录" not in out


# ─── 六、锚点在源码里（防披露被整段删掉）────────────────────────────────


class TestDisclosureAnchorsInSource:
    def test_helper_counts_all_seven_grades(self) -> None:
        src = (ROOT / "experiments/analysis_parts/check_leg_analysis.py").read_text(encoding="utf-8")
        assert "if channel not in row:" in src
        assert 'counts["absent"] += 1' in src
        assert 'counts["null"] += 1' in src
        assert 'result["reason"] = "no_rows"' in src
        assert '"no_channel_recorded"' in src
        assert "rows_any_unmeasurable" in src

    def test_build_analysis_wires_the_helper(self) -> None:
        src = (ROOT / "experiments/analyze_results.py").read_text(encoding="utf-8")
        assert '"_check_leg_measurability(details)' in src or "_check_leg_measurability(details)" in src
        assert '"check_leg_measurability": _check_leg_measurability(details)' in src
        assert "silent_leg_arms" in src
        assert "检查腿可测量性（BQ：结果行四通道的读侧）" in src

    def test_batch_summary_wires_the_helper(self) -> None:
        src = (ROOT / "experiments/run_main_batch.py").read_text(encoding="utf-8")
        assert "_check_leg_measurability(det)" in src
        assert "BQ 检查腿: 未记录（早于 BN 轮落盘，不可读作「干净」）" in src

    def test_channel_tuple_matches_result_row_keys(self) -> None:
        """四通道顺序与 run_benchmark 结果行一致；键名漂移会被本锁抓住。"""
        src = (ROOT / "experiments/run_benchmark.py").read_text(encoding="utf-8")
        for channel in CHECK_LEG_CHANNELS:
            assert f'"{channel}": final_state.get(' in src
        assert set(CHECK_LEG_LABELS) == set(CHECK_LEG_CHANNELS)


# ─── 七、真归档恒等式复算（有界样本；不锁"0 出现"）────────────────────


def test_archive_identities_hold_on_bounded_sample() -> None:
    """归档 1702 份 JSON 现读四键 0 出现（手册 §3 实测）；本锁只钉恒等式——
    真批次一旦落盘， identities 仍须成立，"0 出现"按新读数重新登记。"""
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
            leg = _check_leg_measurability(details)
            for channel in CHECK_LEG_CHANNELS:
                counts = leg["channels"][channel]
                total = sum(counts[g] for g in (*VOCAB, "null", "absent", "other"))
                assert total == leg["n_rows"] == len(details), (path, arm, channel)
            all_absent = sum(1 for row in details if not any(c in row for c in CHECK_LEG_CHANNELS))
            assert leg["recorded_rows"] == len(details) - all_absent, (path, arm)
            assert leg["available"] == (leg["recorded_rows"] > 0)
            assert 0 <= leg["rows_any_unmeasurable"] <= leg["recorded_rows"]
            checked += 1
    assert checked, f"前 {ARCHIVE_FILES} 份批次文件里没有任何可比对的臂"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
