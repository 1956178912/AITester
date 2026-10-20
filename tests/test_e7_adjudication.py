"""E7 人工裁决执行面回归锁（AA 轮 2026-10-19，零 LLM）。

锁的是**执行面的判别力**，不是裁决结果——本批 E7 仍未执行：

1. 量表与口径与协议/工作表逐字一致（五选一 + "不可判"）；bootstrap 口径与
   `statistical_analysis` 等值；
2. 统计量按手算复核（Cohen's κ = 0.25 的可算样例、p_e=1 的无定义分支、N=0）；
3. 结构性错误必须**报错**而不是静默降级（两表候选集不一致不得取交集、
   越界标签、删行、改 task_id）；
4. 工件面：三份路径的空白录入表已备料且**判定列全空**，仓内不存在
   `E7_KAPPA.json`（协议 §0"不存在任何 Kappa 工件"的机读版）。

第 4 条同样属于"预期会红"的反面锁定：E7 真正执行并产出 κ 工件时，必须连同
`docs/HUMAN_ADJUDICATION_PROTOCOL.md` §0 的状态声明一起改写。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import e7_adjudication as e7  # noqa: E402

MAIN_BATCH = ROOT / "experiments" / "results" / "main_batch"
WORKSHEETS = {
    "n8": MAIN_BATCH / "e7_review_worksheet.md",
    "n41": MAIN_BATCH / "e7_review_worksheet_n41.md",
    "n72": MAIN_BATCH / "e7_review_worksheet_n72.md",
}
# 手算样例：6 行，A=B 3 行 → p_o=0.5；两侧边际均为 2/2/2 → p_e=12/36=1/3
# → κ=(0.5−1/3)/(1−1/3)=0.25（Landis & Koch 带：Fair）
_LAB_A = ["equivalent", "equivalent", "test_only", "test_only", "wrong_location", "wrong_location"]
_LAB_B = ["equivalent", "test_only", "test_only", "wrong_location", "wrong_location", "equivalent"]


def _rows(labels: list[str], rater: str, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "candidate_no": str(c["candidate_no"]),
            "task_id": str(c["task_id"]),
            "stratum": str(c["stratum"]),
            "judgment": lab,
            "reason": "",
            "finished_at_utc": "2026-10-19T00:00:00Z",
            "rater": rater,
        }
        for c, lab in zip(candidates, labels, strict=True)
    ]


def _write_sheet(path: Path, rows: list[dict[str, str]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(e7.SHEET_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _two_sheets(tmp_path: Path, candidates: list[dict[str, Any]]) -> tuple[Path, Path]:
    return (
        _write_sheet(tmp_path / "A.csv", _rows(_LAB_A, "A", candidates[:6])),
        _write_sheet(tmp_path / "B.csv", _rows(_LAB_B, "B", candidates[:6])),
    )


@pytest.fixture(scope="module")
def candidates_n8() -> list[dict[str, Any]]:
    return e7.parse_worksheet(WORKSHEETS["n8"].read_text(encoding="utf-8"))


@pytest.mark.unit
class TestScaleAndCaliber:
    def test_rubric_matches_worksheet_header_verbatim(self) -> None:
        """量表与工作表表头逐字同序（协议 §3 的"预注册固定"落到代码常量）。"""
        text = WORKSHEETS["n41"].read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("- 判定口径（预注册 E7 五选一）："))
        assert tuple(x.strip() for x in line.split("：", 1)[1].split("/")) == e7.RUBRIC

    def test_unjudgeable_aliases_and_valid_labels(self) -> None:
        assert (*e7.RUBRIC, e7.UNJUDGEABLE, e7.UNJUDGEABLE_ZH) == e7.VALID_LABELS
        assert e7.is_unjudgeable("unjudgeable") is True
        assert e7.is_unjudgeable("不可判") is True
        assert e7.is_unjudgeable("equivalent") is False

    def test_bootstrap_caliber_equals_statistical_analysis(self) -> None:
        """协议 §6 要求与主统计脚本同口径（10000 次、seed=42）。"""
        from experiments import statistical_analysis as sa

        assert e7.BOOTSTRAP_N_RESAMPLES == sa._BOOTSTRAP_N_RESAMPLES
        assert e7.BOOTSTRAP_SEED == sa._BOOTSTRAP_SEED


@pytest.mark.unit
class TestWorksheetParsing:
    def test_three_paths_candidate_counts(self) -> None:
        for tag, expected in (("n8", 8), ("n41", 41), ("n72", 72)):
            parsed = e7.parse_worksheet(WORKSHEETS[tag].read_text(encoding="utf-8"))
            assert len(parsed) == expected
            assert [c["candidate_no"] for c in parsed] == list(range(1, expected + 1))
            assert {c["stratum"] for c in parsed} == {"sbfl"}

    def test_n8_is_head_prefix_of_n72(self) -> None:
        """三路径全序嵌套（协议 §2.1 复算验证第 2 条）在录入面同样成立。"""
        small = e7.parse_worksheet(WORKSHEETS["n8"].read_text(encoding="utf-8"))
        full = e7.parse_worksheet(WORKSHEETS["n72"].read_text(encoding="utf-8"))
        assert [c["task_id"] for c in small] == [c["task_id"] for c in full[:8]]

    def test_parsing_does_not_touch_the_worksheet(self, tmp_path: Path) -> None:
        """协议 §4 第 2 条：工作表是备料工件，生成录入表只读。"""
        src = tmp_path / "ws.md"
        src.write_text(WORKSHEETS["n8"].read_text(encoding="utf-8"), encoding="utf-8")
        before = hashlib.sha256(src.read_bytes()).hexdigest()
        cands = e7.parse_worksheet(src.read_text(encoding="utf-8"))
        (tmp_path / "entry.csv").write_text(e7.render_entry_sheet(cands, "A"), encoding="utf-8")
        assert hashlib.sha256(src.read_bytes()).hexdigest() == before

    def test_duplicate_candidate_number_raises(self) -> None:
        with pytest.raises(ValueError, match="候选号重复"):
            e7.parse_worksheet("## 候选 1：t_x\n\n## 候选 1：t_y\n")

    def test_headingless_worksheet_raises(self) -> None:
        with pytest.raises(ValueError, match="未解析到任何候选节"):
            e7.parse_worksheet("# 只有标题\n")


@pytest.mark.unit
class TestTemplateAndValidation:
    def test_template_shape(self, candidates_n8: list[dict[str, Any]]) -> None:
        text = e7.render_entry_sheet(candidates_n8, "A")
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == 8
        assert list(rows[0]) == list(e7.SHEET_COLUMNS)
        assert all(r["judgment"] == "" and r["rater"] == "A" for r in rows)
        assert all(r["task_id"].startswith("s4") and r["stratum"] == "sbfl" for r in rows)

    def test_blank_template_is_incomplete_by_default(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = _rows([""] * 8, "A", candidates_n8)
        assert len(e7.validate_entry_rows(rows)) == 8
        assert e7.validate_entry_rows(rows, require_complete=False) == []

    def test_out_of_rubric_label_is_rejected(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = _rows(["plausible", *_LAB_A[:5], "incomplete", "test_only"], "A", candidates_n8)
        errors = e7.validate_entry_rows(rows)
        assert len(errors) == 1 and "越界量表" in errors[0]

    def test_deleted_row_is_reported_not_tolerated(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = _rows(_LAB_A, "A", candidates_n8[:6]) + _rows(["test_only"], "A", candidates_n8[7:])
        errors = e7.validate_entry_rows(rows, candidates_n8)
        assert any("缺候选行" in e and "7" in e for e in errors)

    def test_tampered_task_id_is_rejected(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = _rows([*_LAB_A, "incomplete", "test_only"], "A", candidates_n8)
        rows[0]["task_id"] = "renamed_task"
        assert any("task_id 被改写" in e for e in e7.validate_entry_rows(rows, candidates_n8))

    def test_duplicate_and_non_integer_candidate_no(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = _rows(_LAB_A, "A", candidates_n8[:6])
        rows.append(dict(rows[0]))
        rows.append({**rows[0], "candidate_no": "x"})
        errors = e7.validate_entry_rows(rows)
        assert any("重复" in e for e in errors) and any("非整数" in e for e in errors)

    def test_non_positive_candidate_no_rejected(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows = [{**_rows(_LAB_A, "A", candidates_n8[:6])[0], "candidate_no": "0"}]
        assert any("正整数" in e for e in e7.validate_entry_rows(rows))

    def test_candidate_outside_sampling_frame_rejected(self, candidates_n8: list[dict[str, Any]]) -> None:
        """录入表里冒出抽样清单之外的候选号（手动加行）→ 结构性错误。"""
        rows = _rows(["equivalent"], "A", [candidates_n8[0]])
        rows.append({**rows[0], "candidate_no": "99"})
        errors = e7.validate_entry_rows(rows, candidates_n8)
        assert any("不在抽样清单" in e for e in errors)

    def test_header_mismatch_is_structural_error(self, tmp_path: Path, candidates_n8: list[dict[str, Any]]) -> None:
        path = tmp_path / "bad.csv"
        path.write_text("candidate_no,task_id,judgment\n1,t,equivalent\n", encoding="utf-8")
        with pytest.raises(ValueError, match="表头不符"):
            e7.load_entry_sheet(path)

    def test_empty_file_and_no_rows_are_errors(self, tmp_path: Path) -> None:
        (tmp_path / "empty.csv").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="录入表为空"):
            e7.load_entry_sheet(tmp_path / "empty.csv")
        (tmp_path / "header_only.csv").write_text(",".join(e7.SHEET_COLUMNS) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="无候选行"):
            e7.load_entry_sheet(tmp_path / "header_only.csv")


@pytest.mark.unit
class TestStatistics:
    def test_kappa_matches_hand_computation(self) -> None:
        out = e7.cohen_kappa(list(zip(_LAB_A, _LAB_B, strict=True)))
        assert out["n"] == 6
        assert out["p_o"] == pytest.approx(0.5)
        assert out["p_e"] == pytest.approx(1 / 3)
        assert out["kappa"] == pytest.approx(0.25)
        assert out["confusion_matrix"]["equivalent"]["test_only"] == 1
        assert out["marginal_a"]["incomplete"] == 0

    def test_perfect_agreement_kappa_is_one(self) -> None:
        out = e7.cohen_kappa(list(zip(_LAB_A, _LAB_A, strict=True)))
        assert out["p_o"] == pytest.approx(1.0) and out["kappa"] == pytest.approx(1.0)

    def test_single_category_is_undefined_not_one(self) -> None:
        """p_e=1（全体同类）→ κ 无定义；协议 §6 第 2 条要求显式披露而非报满分。"""
        pairs = [("test_only", "test_only")] * 5
        out = e7.cohen_kappa(pairs)
        assert out["p_e"] == pytest.approx(1.0) and out["kappa"] is None
        assert "undefined" in e7.interpret_kappa(out["kappa"])

    def test_empty_pairs_returns_none_without_division(self) -> None:
        out = e7.cohen_kappa([])
        assert out == {"n": 0, "p_o": None, "p_e": None, "kappa": None, "categories": list(e7.RUBRIC)}

    def test_bootstrap_ci_is_reproducible_and_brackets_point_estimate(self) -> None:
        pairs = list(zip(_LAB_A, _LAB_B, strict=True))
        one = e7.bootstrap_kappa_ci(pairs, n_resamples=500, seed=42)
        two = e7.bootstrap_kappa_ci(pairs, n_resamples=500, seed=42)
        assert one == two
        assert one["valid_replicates"] == 500 and one["degenerate_replicates"] == 0
        lo, hi = one["ci95"]
        assert lo <= 0.25 <= hi
        # 口径入档（协议 §6：CI 与重采样脚本同批入库）；N=6 的重采样空间极小，
        # 不同 seed 可能撞出同一对分位点，故**不**断言"换 seed 必不同"。
        assert one["n_resamples"] == 500 and one["seed"] == 42

    def test_bootstrap_handles_empty_and_degenerate(self) -> None:
        assert e7.bootstrap_kappa_ci([])["ci95"] is None
        degenerate = e7.bootstrap_kappa_ci([("test_only", "test_only")] * 4, n_resamples=50, seed=42)
        assert degenerate["ci95"] is None and degenerate["valid_replicates"] == 0
        assert degenerate["degenerate_replicates"] == 50

    @pytest.mark.parametrize(
        ("kappa", "band"),
        [
            (-0.1, "Poor"),
            (0.0, "Poor"),
            (0.2, "Slight"),
            (0.4, "Fair"),
            (0.6, "Moderate"),
            (0.8, "Substantial"),
            (0.95, "Almost perfect"),
        ],
    )
    def test_external_interpretation_bands(self, kappa: float, band: str) -> None:
        assert e7.interpret_kappa(kappa) == band


@pytest.mark.unit
class TestAlignment:
    def test_row_order_does_not_matter_but_candidate_set_must_match(
        self, tmp_path: Path, candidates_n8: list[dict[str, Any]]
    ) -> None:
        """对齐按 candidate_no；候选集不一致属结构性错误——取交集会把"漏做 3 行"
        洗成一次合法的 N 缩小。"""
        rows_a = _rows([*_LAB_A, "incomplete", "test_only"], "A", candidates_n8)
        rows_b = list(reversed(_rows([*_LAB_B, "incomplete", "test_only"], "B", candidates_n8)))
        pairs, excluded = e7.align_pairs(rows_a, rows_b)
        assert [p[0] for p in pairs] == [*_LAB_A, "incomplete", "test_only"]
        assert excluded == []
        with pytest.raises(ValueError, match="候选集不一致"):
            e7.align_pairs(rows_a, rows_b[:5])

    def test_unjudgeable_rows_leave_denominator_but_stay_registered(
        self, tmp_path: Path, candidates_n8: list[dict[str, Any]]
    ) -> None:
        labels_b = [*_LAB_B, "不可判", "unjudgeable"]
        rows_a = _rows([*_LAB_A, "incomplete", "test_only"], "A", candidates_n8)
        rows_b = _rows(labels_b, "B", candidates_n8)
        pairs, excluded = e7.align_pairs(rows_a, rows_b)
        assert len(pairs) == 6 and len(excluded) == 2
        assert {e["candidate_no"] for e in excluded} == {7, 8}
        assert {e["reason"] for e in excluded} == {"unjudgeable"}

    def test_blank_judgment_is_registered_as_blank(self, candidates_n8: list[dict[str, Any]]) -> None:
        rows_a = _rows([*_LAB_A, "", ""], "A", candidates_n8)
        rows_b = _rows([*_LAB_B, "", ""], "B", candidates_n8)
        pairs, excluded = e7.align_pairs(rows_a, rows_b)
        assert len(pairs) == 6
        assert {e["reason"] for e in excluded} == {"blank"}


@pytest.mark.unit
class TestMergeAndReport:
    def test_merge_reports_primary_and_disagreements(self, tmp_path: Path, candidates_n8: list[dict[str, Any]]) -> None:
        a, b = _two_sheets(tmp_path, candidates_n8)
        report = e7.merge_sheets(a, b, n_resamples=200, seed=42)
        assert report["primary_pair"] == ["A", "B"]
        assert report["kappa"] == pytest.approx(0.25)
        assert report["n_scored"] == 6 and report["n_rows"] == 6
        assert [d["candidate_no"] for d in report["disagreement_rows"]] == [2, 4, 6]
        assert report["interpretation_band_external"] == "Fair"

    def test_merge_refuses_unvalidated_sheets(self, tmp_path: Path, candidates_n8: list[dict[str, Any]]) -> None:
        a, _ = _two_sheets(tmp_path, candidates_n8)
        rows = _rows(["plausible"] * 6, "B", candidates_n8[:6])
        bad = _write_sheet(tmp_path / "B_bad.csv", rows)
        with pytest.raises(ValueError, match="未通过校验"):
            e7.merge_sheets(a, bad)

    def test_third_rater_is_secondary_only(self, tmp_path: Path, candidates_n8: list[dict[str, Any]]) -> None:
        a, b = _two_sheets(tmp_path, candidates_n8)
        c = _write_sheet(tmp_path / "C.csv", _rows(_LAB_A, "C", candidates_n8[:6]))
        report = e7.merge_sheets(a, b, c, n_resamples=200, seed=42)
        assert report["kappa"] == pytest.approx(0.25)
        assert report["secondary_pairwise"]["A_C"] == pytest.approx(1.0)
        assert "主口径仍是 A vs B" in report["secondary_pairwise"]["note"]

    def test_report_markdown_carries_no_recomputed_numbers(
        self, tmp_path: Path, candidates_n8: list[dict[str, Any]]
    ) -> None:
        a, b = _two_sheets(tmp_path, candidates_n8)
        report = e7.merge_sheets(a, b, n_resamples=200, seed=42)
        md = e7.render_report_md(report)
        assert f"**{report['kappa']}**" in md
        lo, hi = report["bootstrap"]["ci95"]
        assert f"[{lo:.6f}, {hi:.6f}]" in md
        assert "不**回答 equivalent 占比" in md
        assert "| 2 | s42__synthetic__task_0013 | equivalent | test_only |" in md
        # 逐字锁死计数行：任何"顺手算个百分比/占比"的再计算都会改变整行文本。
        assert "- 分歧行：3（协议 §5：仅这些行进入对表讨论）" in md
        assert "- 不进分母的行：0（不可判 / 未填；属材料缺口，须登记）" in md

    def test_unjudgeable_rows_are_material_gaps_not_disagreements(
        self, tmp_path: Path, candidates_n8: list[dict[str, Any]]
    ) -> None:
        """一侧"不可判"× 另一侧有效判定属**材料缺口**，不是评分者分歧——
        协议 §5 的对表讨论只处理后者；混为一谈会把缺口洗成"有争议的行"。"""
        a = _write_sheet(tmp_path / "A.csv", _rows([*_LAB_A, "incomplete", "test_only"], "A", candidates_n8))
        b = _write_sheet(tmp_path / "B.csv", _rows([*_LAB_B, "不可判", "unjudgeable"], "B", candidates_n8))
        report = e7.merge_sheets(a, b, n_resamples=100, seed=42)
        assert [d["candidate_no"] for d in report["disagreement_rows"]] == [2, 4, 6]
        assert {e["candidate_no"] for e in report["excluded_rows"]} == {7, 8}

    def test_all_unjudgeable_merge_reports_gap_not_kappa(
        self, tmp_path: Path, candidates_n8: list[dict[str, Any]]
    ) -> None:
        """极端但真实：两侧全部"不可判"→ κ 无定义、分母 0、报告说明空矩阵成因。"""
        a = _write_sheet(tmp_path / "A.csv", _rows(["不可判"] * 8, "A", candidates_n8))
        b = _write_sheet(tmp_path / "B.csv", _rows(["unjudgeable"] * 8, "B", candidates_n8))
        report = e7.merge_sheets(a, b, n_resamples=50, seed=42)
        assert report["kappa"] is None and report["n_scored"] == 0 and report["n_rows"] == 8
        md = e7.render_report_md(report)
        assert "混淆矩阵为空、κ 无定义" in md
        assert "不可用（无有效重采样）" in md

    def test_json_is_stable_and_sorted(self, tmp_path: Path, candidates_n8: list[dict[str, Any]]) -> None:
        a, b = _two_sheets(tmp_path, candidates_n8)
        report = e7.merge_sheets(a, b, n_resamples=100, seed=42)
        dump = json.dumps(report, ensure_ascii=False, sort_keys=True)
        assert dump == json.dumps(json.loads(dump), ensure_ascii=False, sort_keys=True)


@pytest.mark.unit
class TestCli:
    def test_template_then_validate_then_merge_exit_codes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry = tmp_path / "entry.csv"
        monkeypatch.setattr(
            sys, "argv", ["x", "template", "--worksheet", str(WORKSHEETS["n8"]), "--rater", "A", "--output", str(entry)]
        )
        assert e7.main() == 0 and entry.exists()
        monkeypatch.setattr(sys, "argv", ["x", "validate", "--sheet", str(entry)])
        assert e7.main() == 1  # 全空 → 未完成
        monkeypatch.setattr(sys, "argv", ["x", "validate", "--sheet", str(entry), "--allow-incomplete"])
        assert e7.main() == 0

    def test_template_and_merge_default_to_stdout(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        candidates_n8: list[dict[str, Any]],
    ) -> None:
        """默认 `-` 只写 stdout，不落盘（备料与合并都可先看数再决定归档位置）。"""
        monkeypatch.setattr(sys, "argv", ["x", "template", "--worksheet", str(WORKSHEETS["n8"]), "--rater", "A"])
        assert e7.main() == 0
        assert capsys.readouterr().out.splitlines()[0] == ",".join(e7.SHEET_COLUMNS)
        a, b = _two_sheets(tmp_path, candidates_n8)
        monkeypatch.setattr(
            sys, "argv", ["x", "merge", "--sheet-a", str(a), "--sheet-b", str(b), "--n-resamples", "50"]
        )
        assert e7.main() == 0
        out = capsys.readouterr().out
        assert '"kappa"' in out and "Cohen" in out
        assert list(tmp_path.rglob("E7_KAPPA.json")) == []

    def test_validate_with_worksheet_cross_checks_frame(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates_n8: list[dict[str, Any]]
    ) -> None:
        path = _write_sheet(tmp_path / "A.csv", _rows(_LAB_A, "A", candidates_n8[:6]))
        monkeypatch.setattr(
            sys,
            "argv",
            ["x", "validate", "--sheet", str(path), "--worksheet", str(WORKSHEETS["n8"]), "--allow-incomplete"],
        )
        assert e7.main() == 1  # 只做了 6/8 行：进度检查也须报告缺行

    def test_merge_writes_artifacts_to_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates_n8: list[dict[str, Any]]
    ) -> None:
        a, b = _two_sheets(tmp_path, candidates_n8)
        out = tmp_path / "artifacts"
        monkeypatch.setattr(
            sys,
            "argv",
            ["x", "merge", "--sheet-a", str(a), "--sheet-b", str(b), "--output-dir", str(out), "--n-resamples", "100"],
        )
        assert e7.main() == 0
        payload = json.loads((out / "E7_KAPPA.json").read_text(encoding="utf-8"))
        assert payload["kappa"] == pytest.approx(0.25)
        assert "Cohen" in (out / "E7_KAPPA.md").read_text(encoding="utf-8")


@pytest.mark.unit
class TestArtifactSurface:
    """备料齐备 + "尚无裁决结果"的机读锁定（协议 §0/§7 步骤 0-2 的可核验形式）。"""

    @pytest.mark.parametrize("tag", ["n8", "n41", "n72"])
    @pytest.mark.parametrize("rater", ["A", "B"])
    def test_blank_entry_templates_exist_with_expected_rows(self, tag: str, rater: str) -> None:
        expected = {"n8": 8, "n41": 41, "n72": 72}[tag]
        path = MAIN_BATCH / f"e7_entry_rater{rater}_{tag}.csv"
        rows = e7.load_entry_sheet(path)
        assert len(rows) == expected
        assert all(r["rater"] == rater for r in rows)
        # E7 仍未执行：判定列必须全空（非空即意味着有人已经填进备料工件）
        assert all((r["judgment"] or "").strip() == "" for r in rows)
        assert all((r["finished_at_utc"] or "").strip() == "" for r in rows)

    def test_no_kappa_artifact_exists_yet(self) -> None:
        found = sorted(p.name for p in (ROOT / "experiments" / "results").rglob("E7_KAPPA.json"))
        assert found == [], f"E7 若已执行，须同步改写 HUMAN_ADJUDICATION_PROTOCOL.md §0 状态声明：{found}"

    def test_protocol_still_declares_e7_not_executed(self) -> None:
        text = (ROOT / "docs" / "HUMAN_ADJUDICATION_PROTOCOL.md").read_text(encoding="utf-8")
        assert "## 0. 状态声明：E7 尚未执行，且不存在任何 Kappa 工件" in text
