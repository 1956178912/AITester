"""修复引擎批次 XIII（2026-10-07）：修正口径重估收口测试锁（ADR-0027）。

锁定四组行为：
1. correct_row 行级修正四态（correct/wrong_patch/不可测三键 None/
   无补丁保留原值）——原行不被修改（纯函数）；
2. analyze_arm 汇总数学（代际 repair、修正 false_fix、CPR/IDR/弃权
   经 _analyze 喂修正行、bug_type 分层 2×2）；
3. fl_hit_value 抽出后的 cf_upper_bound 回归（批次 X 既有锁）；
4. 报告关键行（CPR 首次可定义 / 弃权精确率非平凡 / 解混杂解读）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.cf_upper_bound import fl_hit_value
from experiments.corrected_metrics import _batch_label, analyze_arm, build_report, correct_row

GOOD = "def add(a, b):\n    return a + b\n"
BAD = "def add(a, b):\n    return a - b\n"


def _row(
    task_id: str,
    patch: str,
    *,
    passed: bool = False,
    correct: int = 0,
    ff: float | None = 1.0,
    plausible: int = 1,
    bug: str = "assertion",
    fl=None,
) -> dict:
    row = {
        "task_id": f"synthetic__{task_id}",
        "patch": patch,
        "passed": passed,
        "patch_correct": correct,
        "false_fix_rate": ff,
        "patch_plausible": plausible,
        "task_metadata": {
            "source": "synthetic",
            "bug_type": bug,
            "test_cases": f"from {task_id} import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            "fixed": "",
        },
    }
    if fl is not None:
        row["localization_hit_function"] = fl
    return row


class TestCorrectRow:
    def test_correct_patch(self) -> None:
        original = _row("m1", "python\n" + GOOD, correct=0, ff=1.0)
        c = correct_row(original, timeout=60)
        assert c["corrected_verdict"] == "correct"
        assert (c["patch_correct"], c["repair_rate"], c["false_fix_rate"]) == (1, 1.0, 0.0)
        # 纯函数：原行不受污染
        assert original["patch_correct"] == 0

    def test_wrong_patch_passed_false_fix_one(self) -> None:
        c = correct_row(_row("m2", BAD, passed=True), timeout=60)
        assert c["corrected_verdict"] == "wrong_patch"
        assert c["false_fix_rate"] == 1.0  # passed ∧ 修正 correct=0

    def test_wrong_patch_failed_false_fix_zero(self) -> None:
        c = correct_row(_row("m3", BAD, passed=False), timeout=60)
        assert c["false_fix_rate"] == 0.0

    def test_unreplayable_keys_become_none(self) -> None:
        # diff 形态不可重放：受染的 0/1.0 改 None（不可测诚实降级）
        c = correct_row(_row("m4", "diff --git a/m.py b/m.py\n"), timeout=60)
        assert c["corrected_verdict"] == "not_replayable_diff"
        assert c["patch_correct"] is None
        assert c["repair_rate"] is None
        assert c["false_fix_rate"] is None

    def test_no_patch_keeps_original(self) -> None:
        # 无补丁行原指标语义正确（repair=0 非伪影），键值保留
        c = correct_row(_row("m5", "", correct=0, ff=1.0), timeout=60)
        assert c["corrected_verdict"] == "no_patch"
        assert c["patch_correct"] == 0
        assert c["false_fix_rate"] == 1.0


class TestAnalyzeArm:
    def _make_dir(self, tmp_path: Path) -> Path:
        # 3 correct + 1 wrong(passed) + 1 no_patch(passed) —— 分层两 bug_type
        details = [_row(f"ok_{i}", "python\n" + GOOD, passed=True, fl=True, bug="assertion") for i in range(3)] + [
            _row("bad", BAD, passed=True, fl=True, bug="runtime"),
            _row("np", "", passed=True, correct=0, ff=1.0, bug="assertion"),
        ]
        batch = {"results": {"aitester": {"details": details}}}
        p = tmp_path / "benchmark_synthetic_test.json"
        p.write_text(json.dumps(batch), encoding="utf-8")
        return tmp_path

    def test_generation_math(self, tmp_path) -> None:
        a = analyze_arm(self._make_dir(tmp_path), "aitester", timeout=60)
        assert a["verdict_dist"]["correct"] == 3
        assert a["verdict_dist"]["wrong_patch"] == 1
        assert a["verdict_dist"]["no_patch"] == 1
        g = a["generations"]["早期批次"]
        assert g["replayable"] == 4
        assert g["correct"] == 3
        assert g["repair_rate"] == 0.75

    def test_corrected_false_fix(self, tmp_path) -> None:
        a = analyze_arm(self._make_dir(tmp_path), "aitester", timeout=60)
        # passed 可测 5 行（4 修正 + 1 no_patch）；false_fix = bad（wrong∧passed）
        # + no_patch（无补丁通过 = 假成功，历史口径语义正确保留）共 2 行
        assert a["false_fix"]["passed_measurable"] == 5
        assert a["false_fix"]["passed_false_fix"] == 2
        assert a["false_fix"]["rate"] == 0.4

    def test_cpr_now_defined_and_abstention_nontrivial(self, tmp_path) -> None:
        a = analyze_arm(self._make_dir(tmp_path), "aitester", timeout=60)
        cpr = a["cpr_view"]
        # correct=3（3 修正行；no_patch 行 patch_correct=0 不进 CPR 分母）
        assert cpr["correct_total"] == 3
        assert cpr["cpr"] is not None
        # 弃权精确率有真实分母（passed 压制行存在时）
        if cpr["passed_abstained"]:
            assert cpr["abstain_precision"] is not None

    def test_bug_type_stratification(self, tmp_path) -> None:
        a = analyze_arm(self._make_dir(tmp_path), "aitester", timeout=60)
        s = a["cf_strata"]
        assert s["assertion"] == {"hit": 3, "hit_correct": 3, "miss": 0, "miss_correct": 0}
        assert s["runtime"] == {"hit": 1, "hit_correct": 0, "miss": 0, "miss_correct": 0}

    def test_batch_label_mapping(self) -> None:
        assert _batch_label("benchmark_synthetic_20261006_140906.json") == "R-P0-2（10-06 三种子）"
        assert _batch_label("benchmark_synthetic_20261007_161053.json") == "E1/E2 logic 档（10-07）"
        assert _batch_label("benchmark_synthetic_20260818_112443.json") == "早期批次"


class TestReportAndContracts:
    def test_report_key_lines(self, tmp_path) -> None:
        self._make_dir(tmp_path) if hasattr(self, "_make_dir") else None
        # 复用 AnalyzeArm 的构造
        details = [_row("ok", "python\n" + GOOD, passed=True, fl=True, bug="assertion")]
        batch = {"results": {"aitester": {"details": details}}}
        (tmp_path / "benchmark_synthetic_r.json").write_text(json.dumps(batch), encoding="utf-8")
        report = build_report(tmp_path, "aitester", timeout=60)
        assert "修正 repair_rate" in report
        assert "CPR（正确补丁保留率，correct>0 后首次可定义）" in report
        assert "弃权精确率（修正，非平凡）" in report
        assert "建议非预注册" in report
        assert "解混杂检验" in report

    def test_cli_writes_report(self, tmp_path) -> None:
        from experiments.corrected_metrics import main as cm_main

        batch = {"results": {"aitester": {"details": [_row("cli", "python\n" + GOOD, fl=True)]}}}
        (tmp_path / "benchmark_synthetic_cli.json").write_text(json.dumps(batch), encoding="utf-8")
        out = tmp_path / "cm.md"
        rc = cm_main([str(tmp_path), "--arm", "aitester", "--out", str(out)])
        assert rc == 0
        assert "ADR-0027" in out.read_text(encoding="utf-8")

    def test_fl_hit_value_contract(self) -> None:
        assert fl_hit_value({"localization_hit_function": True}) == (True, "localization_hit_function")
        assert fl_hit_value({"fl_at_k": {"fl_at_1": 0.0}}) == (False, "fl_at_1_spectral")
        assert fl_hit_value({}) == (None, "none")
        # 函数级优先于谱系回退
        assert fl_hit_value({"localization_hit_function": False, "fl_at_k": {"fl_at_1": 1.0}}) == (
            False,
            "localization_hit_function",
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
