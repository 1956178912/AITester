"""修复引擎批次 XIV（2026-10-07，ADR-0028）测试。

覆盖：
- XIV1：FL Top-k 约束观测门——patch_changed_functions（纯插入锚定 /
  模块级 / 嵌套最内层 / 不可解析降级 / 与 gold_changed_functions 的
  口径差异锁定）+ fl_constraint_verdict（hit_rank / miss / None 降级 /
  旧 schema 单候选退化 / 叶子名归一）+ _fl_constraint_result 结果行
  （成功实算 / 失败占位键集合同构）；
- XIV2：Self-Repair Trap 观测器——snapshot_test_quality（计数 / 不可
  解析 / 变异分透传）+ detect_self_repair_trap 三信号（declining /
  collapse / mutation 下降 + 最新快照不可解析豁免 + 稀疏缺失不进
  判定）+ state 契约（TypedDict 声明 + 工厂默认）+ 结果行透出 +
  generator 接线锁；
- XIV3：文档面——ADR-0028 建档与索引 + Frame Lifetime Trace 设计
  草案（激活门槛声明 + 未核验数字红线标记）。

不触网、不调用真实 LLM。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BUGGY = "def f(a):\n    return a + 1\n\ndef g(b):\n    return b * 2\n"
_PATCHED_INSERT = "def f(a):\n    if a is None:\n        return 0\n    return a + 1\n\ndef g(b):\n    return b * 2\n"


def _make_task():
    from src.datasets.dataset_loader import BenchmarkTask

    return BenchmarkTask(
        task_id="synthetic__task_0001",
        repo_name="synthetic",
        problem_statement="测试任务",
        instance_code=_BUGGY,
        test_code="def test_f():\n    assert f(1) == 2\n",
        expected_pass_count=1,
        total_test_count=1,
        metadata={},
    )


# ═══ XIV1：FL Top-k 约束观测门 ═══════════════════════════════════════════


class TestPatchChangedFunctions(unittest.TestCase):
    """补丁变更函数集合（约束门的补丁侧输入；insert 锚定为核心差异）。"""

    def test_replace_inside_function(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        patched = _BUGGY.replace("return a + 1", "return a + 2")
        self.assertEqual(patch_changed_functions(_BUGGY, patched), {"f"})

    def test_pure_insert_inside_function_and_gold_gap_locked(self) -> None:
        """纯插入修复归属 f；同时锁定与 gold 口径的差异（gold 为空集合）。"""
        from src.agents.fault_localizer import gold_changed_functions, patch_changed_functions

        self.assertEqual(patch_changed_functions(_BUGGY, _PATCHED_INSERT), {"f"})
        # gold 口径只计 delete/replace——纯插入是空集合（判定核差异的
        # 存在理由，回归锁）
        self.assertEqual(gold_changed_functions(_BUGGY, _PATCHED_INSERT), set())

    def test_insert_at_top_of_file_is_module_level(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        patched = "import os\n\n" + _BUGGY
        self.assertEqual(patch_changed_functions(_BUGGY, patched), {"<module>"})

    def test_module_level_change_misses_function_candidates(self) -> None:
        """<module> 级变更与函数候选不相交 → miss（ADR-0028 豁免条款依据）。"""
        from src.agents.fault_localizer import fl_constraint_verdict, patch_changed_functions

        patched = "import os\n\n" + _BUGGY
        changed = patch_changed_functions(_BUGGY, patched)
        verdict = fl_constraint_verdict({"candidates": [{"function_name": "f"}]}, changed)
        assert verdict is not None
        self.assertEqual(verdict["verdict"], "miss")

    def test_nested_function_innermost(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        buggy = "def outer():\n    def inner():\n        return 1\n    return inner()\n"
        patched = "def outer():\n    def inner():\n        return 2\n    return inner()\n"
        self.assertEqual(patch_changed_functions(buggy, patched), {"inner"})

    def test_unparseable_buggy_falls_back_to_module(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        self.assertEqual(patch_changed_functions("this is not python (", _PATCHED_INSERT), {"<module>"})

    def test_identical_texts_empty_set(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        self.assertEqual(patch_changed_functions(_BUGGY, _BUGGY), set())

    def test_empty_inputs_empty_set(self) -> None:
        from src.agents.fault_localizer import patch_changed_functions

        self.assertEqual(patch_changed_functions("", _BUGGY), set())
        self.assertEqual(patch_changed_functions(_BUGGY, "   "), set())


class TestFlConstraintVerdict(unittest.TestCase):
    """判定核：Top-3 候选与补丁变更集合求交。"""

    def test_hit_first_candidate_rank_one(self) -> None:
        from src.agents.fault_localizer import fl_constraint_verdict

        verdict = fl_constraint_verdict(
            {"candidates": [{"function_name": "f"}, {"function_name": "g"}]},
            {"f"},
        )
        assert verdict is not None
        self.assertEqual(verdict["verdict"], "hit")
        self.assertEqual(verdict["hit_rank"], 1)
        self.assertEqual(verdict["changed_functions"], ["f"])

    def test_hit_second_candidate_with_dedup(self) -> None:
        from src.agents.fault_localizer import fl_constraint_verdict

        verdict = fl_constraint_verdict(
            {"candidates": [{"function_name": "a"}, {"function_name": "a"}, {"function_name": "b"}]},
            {"b"},
        )
        assert verdict is not None
        self.assertEqual(verdict["hit_rank"], 2)

    def test_qualified_name_leaf_normalization(self) -> None:
        from src.agents.fault_localizer import fl_constraint_verdict

        verdict = fl_constraint_verdict(
            {"candidates": [{"function_name": "pkg.cls.method"}]},
            {"method"},
        )
        assert verdict is not None
        self.assertEqual(verdict["verdict"], "hit")

    def test_old_schema_single_candidate_fallback(self) -> None:
        """批次 I 旧 schema（无 candidates 键）退化为单候选。"""
        from src.agents.fault_localizer import fl_constraint_verdict

        verdict = fl_constraint_verdict({"function_name": "f", "confidence": 0.9}, {"f"})
        assert verdict is not None
        self.assertEqual(verdict["verdict"], "hit")
        self.assertEqual(verdict["hit_rank"], 1)

    def test_miss_verdict(self) -> None:
        from src.agents.fault_localizer import fl_constraint_verdict

        verdict = fl_constraint_verdict({"candidates": [{"function_name": "zzz"}]}, {"f"})
        assert verdict is not None
        self.assertEqual(verdict["verdict"], "miss")
        self.assertIsNone(verdict["hit_rank"])

    def test_none_inputs_return_none(self) -> None:
        from src.agents.fault_localizer import fl_constraint_verdict

        self.assertIsNone(fl_constraint_verdict(None, {"f"}))
        self.assertIsNone(fl_constraint_verdict({"candidates": [{"function_name": "f"}]}, set()))
        self.assertIsNone(fl_constraint_verdict({}, {"f"}))


class TestFlConstraintResultRow(unittest.TestCase):
    """结果行透出（成功实算 / 失败占位键集合同构）。"""

    def test_success_branch_hit(self) -> None:
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={
                "passed": True,
                "patch": _PATCHED_INSERT,
                "llm_localization": {"candidates": [{"function_name": "h"}, {"function_name": "f"}]},
            },
        )
        self.assertEqual(row["fl_constraint_verdict"], "hit")
        self.assertEqual(row["fl_constraint_hit_rank"], 2)
        self.assertEqual(row["fl_constraint_changed_functions"], ["f"])

    def test_success_branch_not_evaluable_without_localization(self) -> None:
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True, "patch": _PATCHED_INSERT},
        )
        self.assertEqual(row["fl_constraint_verdict"], "not_evaluable")
        self.assertIsNone(row["fl_constraint_hit_rank"])
        self.assertEqual(row["fl_constraint_changed_functions"], [])

    def test_success_branch_not_evaluable_without_patch(self) -> None:
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={
                "passed": True,
                "llm_localization": {"candidates": [{"function_name": "f"}]},
            },
        )
        self.assertEqual(row["fl_constraint_verdict"], "not_evaluable")

    def test_failure_branch_placeholder_isomorphism(self) -> None:
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(_make_task(), 0.5, diagnosis="异常", error_category="error")
        self.assertIsNone(row["fl_constraint_verdict"])
        self.assertIsNone(row["fl_constraint_hit_rank"])
        self.assertEqual(row["fl_constraint_changed_functions"], [])
        self.assertIsNone(row["oracle_quality_history"])
        self.assertFalse(row["self_repair_trap_suspected"])
        self.assertEqual(row["self_repair_trap_signals"], [])


# ═══ XIV2：Self-Repair Trap 观测器 ═══════════════════════════════════════


class TestSnapshotTestQuality(unittest.TestCase):
    """质量快照（数据面）。"""

    def test_counts_and_parse_ok(self) -> None:
        from src.tools.self_repair_trap import snapshot_test_quality

        snap = snapshot_test_quality("def test_a():\n    assert 1\n    assert 2\n", regeneration=1)
        self.assertEqual(snap["assert_count"], 2)
        self.assertEqual(snap["test_count"], 1)
        self.assertTrue(snap["parse_ok"])
        self.assertEqual(snap["regeneration"], 1)
        self.assertIsNone(snap["mutation_score"])

    def test_unparseable_records_parse_ok_false(self) -> None:
        from src.tools.self_repair_trap import snapshot_test_quality

        snap = snapshot_test_quality("def broken(:\n")
        self.assertFalse(snap["parse_ok"])
        self.assertEqual(snap["assert_count"], 0)

    def test_mutation_score_passthrough(self) -> None:
        from src.tools.self_repair_trap import snapshot_test_quality

        snap = snapshot_test_quality("def test_a():\n    assert 1\n", mutation_score=0.75)
        self.assertEqual(snap["mutation_score"], 0.75)


class TestDetectSelfRepairTrap(unittest.TestCase):
    """判定核三信号（保守口径）。"""

    def test_declining_assert_count_signal(self) -> None:
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n    assert 2\n    assert 3\n", regeneration=0),
            snapshot_test_quality("def test_a():\n    assert 1\n    assert 2\n", regeneration=1),
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=2),
        ]
        result = detect_self_repair_trap(history)
        self.assertTrue(result["suspected"])
        self.assertIn("assert_count_declining", result["signals"])

    def test_stable_assert_count_not_suspected(self) -> None:
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=0),
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=1),
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=2),
        ]
        self.assertFalse(detect_self_repair_trap(history)["suspected"])

    def test_assertion_collapse_signal(self) -> None:
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n    assert 2\n", regeneration=0),
            snapshot_test_quality("def test_a():\n    pass\n", regeneration=1),
        ]
        result = detect_self_repair_trap(history)
        self.assertTrue(result["suspected"])
        self.assertIn("assertion_collapse", result["signals"])

    def test_unparseable_latest_does_not_masquerade_as_collapse(self) -> None:
        """最新快照不可解析（语法损坏）→ 不冒充断言退化（口径红线）。"""
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=0),
            snapshot_test_quality("def broken(:\n", regeneration=1),
        ]
        result = detect_self_repair_trap(history)
        self.assertFalse(result["suspected"])
        self.assertEqual(result["signals"], [])

    def test_mutation_score_declining_signal(self) -> None:
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n", mutation_score=0.8, regeneration=0),
            snapshot_test_quality("def test_a():\n    assert 1\n", mutation_score=0.5, regeneration=1),
        ]
        result = detect_self_repair_trap(history)
        self.assertTrue(result["suspected"])
        self.assertIn("mutation_score_declining", result["signals"])

    def test_sparse_mutation_scores_ignored(self) -> None:
        """变异分稀疏缺失（<2 个非 None）不进判定（AN2 口径）。"""
        from src.tools.self_repair_trap import detect_self_repair_trap, snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n", regeneration=0),
            snapshot_test_quality("def test_a():\n    assert 1\n", mutation_score=0.5, regeneration=1),
        ]
        self.assertFalse(detect_self_repair_trap(history)["suspected"])

    def test_empty_history_not_suspected(self) -> None:
        from src.tools.self_repair_trap import detect_self_repair_trap

        self.assertFalse(detect_self_repair_trap(None)["suspected"])
        self.assertFalse(detect_self_repair_trap([])["suspected"])
        self.assertFalse(detect_self_repair_trap([{"unexpected": 1}])["suspected"])


class TestSelfRepairTrapStateContract(unittest.TestCase):
    """state 契约：TypedDict 声明 + 工厂默认 + generator 接线。"""

    def test_typeddict_field_declared(self) -> None:
        from src.graph.state import AITesterState

        self.assertIn("oracle_quality_history", AITesterState.__annotations__)

    def test_factory_default_none(self) -> None:
        from src.graph.state import create_initial_state

        state = create_initial_state("u-1", "mod.py", "x = 1\n", 3)
        self.assertIsNone(state.get("oracle_quality_history"))

    def test_generator_wiring_lock(self) -> None:
        """generator 节点接线锁：快照写入点存在（wiring 锁，配合状态契约门）。"""
        import inspect

        from src.graph import nodes

        source = inspect.getsource(nodes)
        self.assertIn("oracle_quality_history", source)
        self.assertIn("snapshot_test_quality", source)


class TestTrapResultRow(unittest.TestCase):
    """结果行透出（成功实算 / 历史透传）。"""

    def test_success_branch_carries_trap_and_history(self) -> None:
        from experiments.run_benchmark import _build_task_result
        from src.tools.self_repair_trap import snapshot_test_quality

        history = [
            snapshot_test_quality("def test_a():\n    assert 1\n    assert 2\n", regeneration=0),
            snapshot_test_quality("def test_a():\n    pass\n", regeneration=1),
        ]
        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True, "oracle_quality_history": history},
        )
        self.assertTrue(row["self_repair_trap_suspected"])
        self.assertIn("assertion_collapse", row["self_repair_trap_signals"])
        self.assertEqual(row["oracle_quality_history"], history)

    def test_success_branch_no_history_keeps_placeholder(self) -> None:
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(_make_task(), 1.0, final_state={"passed": True})
        self.assertFalse(row["self_repair_trap_suspected"])
        self.assertEqual(row["self_repair_trap_signals"], [])
        self.assertIsNone(row["oracle_quality_history"])


# ═══ XIV3：文档面 ═════════════════════════════════════════════════════════


class TestBatchXivDocs(unittest.TestCase):
    """ADR-0028 建档 + 设计草案激活门槛。"""

    def test_adr_0028_exists_and_indexed(self) -> None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        adr = os.path.join(repo_root, "docs", "adr", "0028-fl-constraint-gate-self-repair-trap.md")
        self.assertTrue(os.path.exists(adr))
        with open(adr, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("FL Top-k 约束观测门", content)
        self.assertIn("Self-Repair Trap", content)
        with open(os.path.join(repo_root, "docs", "adr", "README.md"), encoding="utf-8") as f:
            index = f.read()
        self.assertIn("[0028](0028-fl-constraint-gate-self-repair-trap.md)", index)

    def test_frame_lifetime_trace_design_gated(self) -> None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, "docs", "design", "frame_lifetime_trace.md"), encoding="utf-8") as f:
            content = f.read()
        # 激活门槛声明（未实现、未排期——ADR-0003 纪律）
        self.assertIn("未实现、未排期", content)
        # 引用纪律：未核验数字必须带红线标记（AX 批次纪律）
        self.assertIn("[未核验]", content)


if __name__ == "__main__":
    unittest.main()
