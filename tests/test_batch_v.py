"""修复引擎批次 V（2026-10-07，ADR-0020）：弃权门观测层行为锁。

锁定三组行为：
1. 求值核 evaluate_patch_abstention（五信号命中/组合/None 保守）；
2. cpr_idr_report 弃权视角数学（would-be abstention 拦截面/压制数/精确率）；
3. run_benchmark 接线存在性（结果行双分支键集合同构）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.cpr_idr_report import _analyze
from src.tools.patch_abstain import evaluate_patch_abstention, patch_abstain_signal_names


class TestEvaluatePatchAbstention:
    def test_none_record_conservative(self) -> None:
        assert evaluate_patch_abstention(None) == {"abstain": False, "signals": []}

    def test_empty_record_no_signals(self) -> None:
        assert evaluate_patch_abstention({}) == {"abstain": False, "signals": []}

    def test_each_signal_fires(self) -> None:
        cases = [
            ({"test_regenerated_pass_unverified": True}, "test_regenerated_pass_unverified"),
            ({"detection_first_status": "all_green_unverified"}, "detection_first_status"),
            ({"specificity_gate_verdict": "over_red"}, "specificity_gate_verdict"),
            ({"patch_evidence_level": "none"}, "patch_evidence_level"),
            ({"source_patched_unverified": True}, "source_patched_unverified"),
        ]
        for record, expected_signal in cases:
            result = evaluate_patch_abstention(record)
            assert result["abstain"] is True, record
            assert result["signals"] == [expected_signal]

    def test_multiple_signals_collected(self) -> None:
        result = evaluate_patch_abstention({"patch_evidence_level": "none", "source_patched_unverified": True})
        assert result["abstain"] is True
        assert set(result["signals"]) == {"patch_evidence_level", "source_patched_unverified"}

    def test_trusted_values_do_not_fire(self) -> None:
        """各键的可信取值（specific_red / sbfl / False / red_then_green）不触发。"""
        record = {
            "test_regenerated_pass_unverified": False,
            "detection_first_status": "red_then_green",
            "specificity_gate_verdict": "specific_red",
            "patch_evidence_level": "sbfl",
            "source_patched_unverified": False,
        }
        assert evaluate_patch_abstention(record) == {"abstain": False, "signals": []}

    def test_signal_names_catalogue(self) -> None:
        assert set(patch_abstain_signal_names()) == {
            "test_regenerated_pass_unverified",
            "detection_first_status",
            "specificity_gate_verdict",
            "patch_evidence_level",
            "source_patched_unverified",
        }


class TestCprIdrAbstentionView:
    def test_abstention_math(self) -> None:
        rows = [
            # passed + 弃权信号 + 裁决失败 → 压制且计入精确率分子
            ("b.json", {"passed": True, "patch_plausible": 1, "patch_correct": 0, "patch_evidence_level": "none"}),
            # passed + 无信号 → 不压制
            ("b.json", {"passed": True, "patch_plausible": 1, "patch_correct": 0, "patch_evidence_level": "sbfl"}),
            # 非 passed 行的 plausible 命中仍计入拦截面
            ("b.json", {"passed": False, "patch_plausible": 1, "patch_correct": 0, "source_patched_unverified": True}),
        ]
        stats = _analyze(rows)
        assert stats["plausible_total"] == 3
        assert stats["abstain_plausible_hits"] == 2
        assert abs(stats["abstain_plausible_rate"] - 2 / 3) < 1e-9
        assert stats["passed_total"] == 2
        assert stats["passed_abstained"] == 1
        assert stats["passed_abstained_incorrect"] == 1
        assert stats["abstain_precision"] == 1.0

    def test_precision_none_when_no_suppression(self) -> None:
        rows = [("b.json", {"passed": True, "patch_plausible": 1, "patch_correct": 0, "patch_evidence_level": "sbfl"})]
        stats = _analyze(rows)
        assert stats["passed_abstained"] == 0
        assert stats["abstain_precision"] is None  # 无压制 → 未定义（诚实）

    def test_false_fix_rate_also_counts_as_incorrect(self) -> None:
        """patch_correct 缺失但 false_fix_rate=1.0 的行同样计入精确率分子。"""
        rows = [
            (
                "b.json",
                {
                    "passed": True,
                    "patch_plausible": 1,
                    "false_fix_rate": 1.0,
                    "detection_first_status": "all_green_unverified",
                },
            )
        ]
        stats = _analyze(rows)
        assert stats["passed_abstained"] == 1
        assert stats["passed_abstained_incorrect"] == 1


class TestRunBenchmarkWiring:
    def test_result_row_keys_wired_both_branches(self) -> None:
        """接线存在性锁：成功/失败两分支均透出弃权键（键集合同构）。

        成功分支表达式含 evaluate_patch_abstention(final_state)（仅成功
        分支有 final_state 求值）；失败分支占位 False/[]（字面量唯一）。
        """
        import inspect

        import experiments.run_benchmark as rb

        src_text = inspect.getsource(rb._build_task_result)
        assert '"patch_abstained": evaluate_patch_abstention(final_state)["abstain"]' in src_text
        assert '"patch_abstain_signals": evaluate_patch_abstention(final_state)["signals"]' in src_text
        assert '"patch_abstained": False' in src_text
        assert '"patch_abstain_signals": []' in src_text
        assert src_text.count('"patch_abstained"') == 2  # 恰好两分支各一处
