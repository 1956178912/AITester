"""Y 批次（2026-10-05 X 批次冒烟验证后的补遗）回归测试。

覆盖：
- Y1：检出优先终态标注三值推导（_derive_detection_first_status）——
  X 批次真实冒烟发现"全绿→再生成→变红→终止"轨迹下
  all_green_unverified 残留为终值与 red_seen=True 矛盾；
- Y1：结果行 regeneration_count 透出（成功/失败两分支键集合同构）；
- Y2：agent_telemetry MAST 分类法对齐（映射表 + 报告字段 + 渲染列）。

全部用例零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══ Y1：检出优先终态标注三值推导 ══════════════════════════════════════════


class TestY1DetectionFirstStatusDerivation(unittest.TestCase):
    def test_four_cells(self):
        """(passed, red_seen) 四象限：三值 + 不写。"""
        from src.graph.nodes import _derive_detection_first_status as f

        self.assertEqual(f(True, True), "red_then_green")
        self.assertEqual(f(True, False), "all_green_unverified")
        # Y1 新增：检出成功但未修复（plain_llm_df 正常终态 / 修复失败终态）
        self.assertEqual(f(False, True), "red_not_repaired")
        # 无检出无修复的失败：不写（保留上一轮值）
        self.assertIsNone(f(False, False))
        # red_seen=None 按 falsy 处理（协议开启但首轮即失败且无粘性信号）
        self.assertIsNone(f(False, None))

    def test_smoke_trace_scenario(self):
        """冒烟实测轨迹逐轮推导：exec1 全绿 → exec2 变红。

        轨迹（trace: PASS→regenerate→FAIL→done）此前终值残留
        all_green_unverified；三值推导后 exec2 覆盖为 red_not_repaired。
        """
        from src.graph.nodes import _derive_detection_first_status as f

        # exec1：iteration==0 全绿，red_seen 尚为 False/None
        red_seen_after_exec1 = False  # (not passed) or sticky → False
        status_exec1 = f(True, red_seen_after_exec1)
        self.assertEqual(status_exec1, "all_green_unverified")  # 触发再生成

        # exec2（再生成后）：失败（红），粘性 red_seen=True
        red_seen_after_exec2 = True
        status_exec2 = f(False, red_seen_after_exec2)
        self.assertEqual(status_exec2, "red_not_repaired")  # Y1：覆盖残留值


# ═══ Y1：结果行 regeneration_count 透出 ════════════════════════════════════


def _make_task():
    from src.datasets.dataset_loader import BenchmarkTask

    return BenchmarkTask(
        task_id="synthetic__task_0001",
        repo_name="synthetic",
        problem_statement="测试任务",
        instance_code="def f(x):\n    return x\n",
        test_code="def test_f():\n    assert f(1) == 1\n",
        expected_pass_count=1,
        total_test_count=1,
        metadata={},
    )


class TestY1ResultRowRegenerationCount(unittest.TestCase):
    def test_success_branch_carries_count(self):
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True, "regeneration_count": 1},
        )
        self.assertEqual(row.get("regeneration_count"), 1)
        # 检出优先字段仍在（键集合同构）
        self.assertIn("detection_first_red_seen", row)
        self.assertIn("detection_first_status", row)

    def test_failure_branch_placeholder_keeps_key_isomorphism(self):
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(_make_task(), 0.5, diagnosis="异常", error_category="error")
        self.assertIsNone(row.get("regeneration_count"))
        self.assertIn("regeneration_count", row)

    def test_protocol_off_state_keeps_none(self):
        """协议关（state 无 regeneration_count 键）→ None 占位。"""
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True},
        )
        self.assertIsNone(row.get("regeneration_count"))


# ═══ Y2：MAST 分类法对齐 ═══════════════════════════════════════════════════


class TestY2MastAlignment(unittest.TestCase):
    def test_mapping_known_and_none(self):
        """映射表：已知类命中 + 无对应显式 None（诚实口径）。"""
        # 全部本地模式都在映射表里（值可为 None）
        from src.observability.agent_telemetry import (
            _FAILURE_PATTERN_NAMES,
            _PATTERN_TO_MAST,
            mast_class_of,
            mast_top_category_of,
        )

        self.assertEqual(set(_PATTERN_TO_MAST), set(_FAILURE_PATTERN_NAMES))
        # 抽检映射
        self.assertEqual(mast_class_of("llm_json_parse_failure_loop"), "Incapability of valid output format")
        self.assertEqual(mast_class_of("cross_file_topology_mismatch"), "Task allocation and coordination mismatch")
        # 无对应：资源治理 / 本地伞形
        self.assertIsNone(mast_class_of("budget_early_stop"))
        self.assertIsNone(mast_class_of("known_error_category_hit"))
        # 大类解析
        self.assertEqual(mast_top_category_of("Instruction violations"), "Task Verification & Alignment")
        self.assertEqual(mast_top_category_of("Information exchange failure"), "Inter-agent Misalignment")
        self.assertEqual(mast_top_category_of("Task allocation and coordination mismatch"), "Specification & Design")
        self.assertIsNone(mast_top_category_of(None))
        self.assertIsNone(mast_top_category_of("不存在的类"))

    def test_report_carries_mast_fields(self):
        """报告 patterns 每项带 mast_class / mast_category。"""
        from src.observability.agent_telemetry import match_failure_patterns

        records = [
            {"task": "t1", "error_category": "execution_trace_missing"},
            {"task": "t2", "error_category": "llm_json_parse_failed", "decision": "debug"},
            {"task": "t3", "error_category": "budget_exceeded"},
        ]
        report = match_failure_patterns(records)
        for info in report["patterns"].values():
            self.assertIn("mast_class", info)
            self.assertIn("mast_category", info)
        # 抽检：execution_trace_missing → Information exchange failure
        etm = report["patterns"]["execution_trace_missing"]
        self.assertEqual(etm["count"], 1)
        self.assertEqual(etm["mast_class"], "Information exchange failure")
        self.assertEqual(etm["mast_category"], "Inter-agent Misalignment")
        # 无对应：budget_early_stop 命中但 MAST 字段为 None
        bes = report["patterns"]["budget_early_stop"]
        self.assertEqual(bes["count"], 1)
        self.assertIsNone(bes["mast_class"])

    def test_render_includes_mast_columns(self):
        """Markdown 渲染含 MAST 类 / 大类两列。"""
        from src.observability.agent_telemetry import match_failure_patterns, render_telemetry_report

        report = match_failure_patterns([{"task": "t1", "error_category": "execution_trace_missing"}])
        md = render_telemetry_report(report)
        self.assertIn("| 失败模式 | 命中次数 | MAST 类 | MAST 大类 |", md)
        self.assertIn("Information exchange failure", md)
        # 无对应类渲染为占位符（不硬凑）
        self.assertIn("budget_early_stop | 0 | — | — |", md)


if __name__ == "__main__":
    unittest.main()
