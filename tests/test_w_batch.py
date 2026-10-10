"""W 批次（2026-10-05 审查优化落地）回归测试。

覆盖：
- W1 文档漂移守卫（模板数 50 与 BASELINE.yaml 一致 / README 无指向已删文件的断链）
- W3 检出优先协议（DETECTION_FIRST_ENABLE，默认关；ADR-0015）
- W6 single_agent 基线健全性修复（模块名注入 / 轨迹补记 / 变异反馈死代码修复）
- W2 覆盖率渐进 ratchet（scripts/gates/coverage_ratchet.py，进程内 importlib 加载）
- W4 QuixBugs / BugsInPy 真实基准加载器

全部用例零 LLM / 零网络 / 零子进程（mock 或本地 fixture）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_RATCHET_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "coverage_ratchet.py"


def _load_ratchet_module():
    """进程内加载 ratchet 脚本为模块（免子进程，断言可直接读返回码 int）。"""
    spec = importlib.util.spec_from_file_location("aitester_coverage_ratchet", _RATCHET_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ═══ W1：文档漂移守卫 ═════════════════════════════════════════════════════════


class TestW1DocDrift(unittest.TestCase):
    def test_synthetic_template_count_matches_baseline(self):
        """唯一缺陷 pattern 总数与 BASELINE.yaml synthetic_templates 一致。

        探查口径：8 个 pattern 池（含跨文件池）按 name 字段去重合计；
        该数字被 BASELINE.yaml / README / verify_synthetic_templates.py
        三处引用，漂移即口径断裂。
        """
        from src.datasets.synthetic_dataset import (
            BUG_PATTERNS,
            BUG_PATTERNS_LEVEL2,
            BUG_PATTERNS_LEVEL4,
            BUG_PATTERNS_LEVEL25,
            BUG_PATTERNS_LEVEL25HARD,
            BUG_PATTERNS_LEVEL45,
            CROSS_FILE_DEEP_PATTERNS,
            CROSS_FILE_PATTERNS,
        )

        pools = [
            BUG_PATTERNS,
            BUG_PATTERNS_LEVEL2,
            BUG_PATTERNS_LEVEL25,
            BUG_PATTERNS_LEVEL25HARD,
            BUG_PATTERNS_LEVEL4,
            BUG_PATTERNS_LEVEL45,
            CROSS_FILE_PATTERNS,
            CROSS_FILE_DEEP_PATTERNS,
        ]
        unique_names = {t["name"] for p in pools for t in p}
        baseline_text = (PROJECT_ROOT / "BASELINE.yaml").read_text(encoding="utf-8")
        m = re.search(r"^synthetic_templates:\s*(\d+)", baseline_text, re.M)
        assert m is not None, "BASELINE.yaml 缺 synthetic_templates 键"
        self.assertEqual(len(unique_names), int(m.group(1)), "模板唯一 pattern 数与 BASELINE.yaml 漂移")

    def test_readme_no_dangling_round7_link(self):
        """README 双语不再引用已删除的 docs/review_2026-09-26_round7.md。"""
        for readme in ("README.md", "README.en.md"):
            content = (PROJECT_ROOT / readme).read_text(encoding="utf-8")
            self.assertNotIn("docs/review_2026-09-26_round7.md", content, f"{readme} 仍含 round7 断链")


# ═══ W3：检出优先协议 ═════════════════════════════════════════════════════════


class TestW3DetectionFirst(unittest.TestCase):
    def test_default_off(self):
        """DETECTION_FIRST_ENABLE 默认 false（ADR-0003 默认行为不变）。"""
        import config

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DETECTION_FIRST_ENABLE", None)
            self.assertFalse(config.detection_first_enabled())

    def test_regenerate_entry_matrix(self):
        """_detection_first_regenerate_entry 仅在"开关开 + 全绿 + iteration 0"命中。"""
        from src.graph import nodes

        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "true"}):
            self.assertTrue(nodes._detection_first_regenerate_entry({"test_passed": True, "iteration": 0}))
            self.assertFalse(nodes._detection_first_regenerate_entry({"test_passed": None, "iteration": 0}))
            self.assertFalse(nodes._detection_first_regenerate_entry({"test_passed": False, "iteration": 0}))
            self.assertFalse(nodes._detection_first_regenerate_entry({"test_passed": True, "iteration": 1}))
        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "false"}):
            self.assertFalse(nodes._detection_first_regenerate_entry({"test_passed": True, "iteration": 0}))

    def test_section_content(self):
        from src.graph import nodes

        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "true"}):
            section = nodes._detection_first_section({"test_passed": True, "iteration": 0})
            self.assertIsNotNone(section)
            assert section is not None
            self.assertIn("先红后绿", section)
            self.assertIn("禁止放松", section)
            self.assertIn("禁止重新实现被测函数", section)
        self.assertIsNone(nodes._detection_first_section({"test_passed": None, "iteration": 0}))

    def test_state_declares_new_keys(self):
        from src.graph.state import AITesterState, create_initial_state

        self.assertIn("detection_first_red_seen", AITesterState.__annotations__)
        self.assertIn("detection_first_status", AITesterState.__annotations__)
        state = create_initial_state(
            task_uuid="t", target_file="m.py", target_code="def f():\n    pass\n", max_iterations=3
        )
        self.assertIsNone(state["detection_first_red_seen"])
        self.assertIsNone(state["detection_first_status"])

    def test_should_debug_routes(self):
        """开关开：首轮全绿 + 预算未用 → regenerate；预算用尽 / 开关关 → done。"""
        from src.graph.state import create_initial_state
        from src.graph.workflow import _should_debug

        def _state(regeneration_count: int = 0) -> dict:
            state = create_initial_state(
                task_uuid="t", target_file="m.py", target_code="def f():\n    pass\n", max_iterations=3
            )
            state["test_passed"] = True
            state["iteration"] = 0
            state["execution_trace"] = [{"iteration": 0, "passed": True, "coverage": 90.0}]
            state["regeneration_count"] = regeneration_count
            return state

        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "true"}):
            self.assertEqual(_should_debug(_state(0)), "regenerate")
            self.assertEqual(_should_debug(_state(1)), "done")
        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "false"}):
            self.assertEqual(_should_debug(_state(0)), "done")

    def test_executor_node_writes_observables(self):
        """开关开：失败轮写 red_seen=True；通过轮写终态标注；开关关不写任何键。"""
        from src.graph import nodes
        from src.graph.state import create_initial_state

        class _FakeExec:
            def __init__(self, passed: bool) -> None:
                self._passed = passed

            def execute(self, **_kwargs: object) -> dict:
                return {
                    "passed": self._passed,
                    "output": "",
                    "coverage": 80.0,
                    "failed_cases": [] if self._passed else ["test_x"],
                }

        def _run(passed: bool, extra_state: dict | None = None) -> dict:
            state = create_initial_state(
                task_uuid="t", target_file="m.py", target_code="def f():\n    pass\n", max_iterations=3
            )
            state["generated_test"] = "def test_f():\n    assert True\n"
            if extra_state:
                state.update(extra_state)
            fake = _FakeExec(passed)
            with patch.object(nodes, "_get_or_create_executor_agent", return_value=fake):
                return nodes._executor_node(state)

        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "true"}):
            # Y1（2026-10-05 三值修订）：失败轮且曾红（本轮红或粘性红）→
            # 写 red_not_repaired（此前不写，残留中间值与 red_seen=True 矛盾——
            # X 批次冒烟 trace: PASS→regenerate→FAIL→done 实证）
            update = _run(passed=False)
            self.assertIs(update["detection_first_red_seen"], True)
            self.assertEqual(update["detection_first_status"], "red_not_repaired")

            # Y1 补例：失败但从未红（iteration>0 修复回归，无 iteration==0 红灯）
            # → 不写终态（无语义可标注，保留上一轮值）
            update = _run(passed=False, extra_state={"iteration": 1})
            self.assertNotIn("detection_first_status", update)

            update = _run(passed=True)
            self.assertIs(update["detection_first_red_seen"], False)
            self.assertEqual(update["detection_first_status"], "all_green_unverified")

            update = _run(passed=True, extra_state={"detection_first_red_seen": True})
            self.assertEqual(update["detection_first_status"], "red_then_green")

        with patch.dict(os.environ, {"DETECTION_FIRST_ENABLE": "false"}):
            update = _run(passed=True)
            self.assertNotIn("detection_first_red_seen", update)
            self.assertNotIn("detection_first_status", update)


# ═══ W6：single_agent 基线健全性修复 ══════════════════════════════════════════


class _FakeGenerator:
    """捕获 query 的 GeneratorAgent 替身（模块名注入断言的数据源）。

    返回体同时含同名函数 f（供 apply_patch_to_code 命中替换，触发修复轮
    写盘 + 重试路径）与占位测试函数。
    """

    last_query: str = ""

    def _call_llm(self, query: str) -> str:
        _FakeGenerator.last_query = query
        return "def f():\n    return 1\n\ndef test_placeholder():\n    assert True\n"

    @staticmethod
    def _extract_python_code(raw: str) -> str:
        return raw


class _FakeExecutor:
    def __init__(self, results: list[dict]) -> None:
        self._results = list(results)

    def execute(self, **_kwargs: object) -> dict:
        return self._results.pop(0)


def _green() -> dict:
    return {"passed": True, "output": "1 passed", "coverage": 90.0, "failed_cases": []}


def _red() -> dict:
    return {"passed": False, "output": "1 failed", "coverage": 50.0, "failed_cases": ["test_x"]}


def _base_state(tmp_file: Path) -> dict:
    from src.graph.state import create_initial_state

    tmp_file.write_text("def f():\n    return 1\n", encoding="utf-8")
    return dict(
        create_initial_state(
            task_uuid="t",
            max_iterations=3,
            target_file=str(tmp_file),
            target_code="def f():\n    return 1\n",
            module_name="mymod",
        )
    )


class TestW6SingleAgentBaseline(unittest.TestCase):
    def setUp(self) -> None:
        _FakeGenerator.last_query = ""

    def _run(self, state: dict, exec_results: list[dict]) -> dict:
        import experiments.run_benchmark as rb

        with (
            patch("src.agents.generator.GeneratorAgent", _FakeGenerator),
            patch("src.agents.executor.ExecutorAgent", lambda **_k: _FakeExecutor(exec_results)),
        ):
            return rb.run_single_agent_baseline(state)

    def test_prompt_contains_module_name_and_no_contradiction(self):
        with tempfile.TemporaryDirectory() as td:
            state = _base_state(Path(td) / "mymod.py")
            self._run(state, [_green()])
            q = _FakeGenerator.last_query
            self.assertIn("mymod", q, "prompt 必须注入真实模块名（W6 根因：50/50 猜错模块名）")
            self.assertIn("from mymod import", q)
            # W6：移除"同时生成修复补丁"的自相矛盾要求（诱导双代码块输出）
            self.assertNotIn("同时生成一个简化版的修复补丁", q)

    def test_module_name_fallback_to_file_stem(self):
        with tempfile.TemporaryDirectory() as td:
            from src.graph.state import create_initial_state

            f = Path(td) / "fallbackmod.py"
            f.write_text("def f():\n    return 1\n", encoding="utf-8")
            state = create_initial_state(
                task_uuid="t",
                max_iterations=3,
                target_file=str(f),
                target_code="def f():\n    return 1\n",
                module_name=None,
            )
            self._run(state, [_green()])
            self.assertIn("fallbackmod", _FakeGenerator.last_query)

    def test_mutation_feedback_entered_prompt_before_call(self):
        """W6 死代码修复：变异反馈必须在 LLM 调用前拼入（此前拼在调用后永不生效）。"""
        with tempfile.TemporaryDirectory() as td:
            state = _base_state(Path(td) / "mymod.py")
            state["mutation_feedback"] = {"survived_mutants": ["operator_flip@line3"]}
            self._run(state, [_green()])
            self.assertIn("operator_flip@line3", _FakeGenerator.last_query)

    def test_execution_trace_recorded_green(self):
        """W6：绕过工作流的基线也必须补记 execution_trace（此前恒空 →
        error_category 100% 误报 execution_trace_missing）。"""
        with tempfile.TemporaryDirectory() as td:
            state = _base_state(Path(td) / "mymod.py")
            final = self._run(state, [_green()])
            self.assertEqual(len(final["execution_trace"]), 1)
            record = final["execution_trace"][0]
            self.assertTrue(record["passed"])
            self.assertEqual(record["coverage"], 90.0)

    def test_execution_trace_recorded_after_retry(self):
        """修复轮重试同样补记第二条轨迹。"""
        with tempfile.TemporaryDirectory() as td:
            state = _base_state(Path(td) / "mymod.py")
            # 第一次红 → 触发修复轮；修复返回原代码（可通过安全守卫）→ 重试绿
            final = self._run(state, [_red(), _green()])
            self.assertEqual(final["iteration"], 1)
            self.assertEqual(len(final["execution_trace"]), 2)
            self.assertFalse(final["execution_trace"][0]["passed"])
            self.assertTrue(final["execution_trace"][1]["passed"])


# ═══ W2：覆盖率渐进 ratchet（进程内加载，免子进程）════════════════════════════


def _write_cov_xml(path: Path, line_pct: float, branch_pct: float) -> None:
    lv, lc = 1000, int(1000 * line_pct / 100)
    bv, bc = 100, int(100 * branch_pct / 100)
    path.write_text(
        f'<coverage lines-valid="{lv}" lines-covered="{lc}" branches-valid="{bv}" '
        f'branches-covered="{bc}" line-rate="{line_pct / 100}" branch-rate="{branch_pct / 100}"/>',
        encoding="utf-8",
    )


class TestW2CoverageRatchet(unittest.TestCase):
    def test_regression_blocks_and_check_does_not_write(self):
        mod = _load_ratchet_module()
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "coverage.xml"
            state = Path(td) / "state.yaml"
            _write_cov_xml(xml, line_pct=90.0, branch_pct=40.0)
            original = "line_total: 95.00\nbranch_total: 30.00\n"
            state.write_text(original, encoding="utf-8")
            argv = ["ratchet", "--check", "--coverage-xml", str(xml), "--state", str(state)]
            with patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 1, "实测低于水位（回退）必须返回 1")
            self.assertEqual(state.read_text(encoding="utf-8"), original, "--check 模式不得写状态文件")

    def test_local_mode_bumps_floor_and_settles(self):
        mod = _load_ratchet_module()
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "coverage.xml"
            state = Path(td) / "state.yaml"
            _write_cov_xml(xml, line_pct=90.0, branch_pct=40.0)
            state.write_text("line_total: 80.00\nbranch_total: 30.00\n", encoding="utf-8")
            with patch.object(
                sys, "argv", ["ratchet", "--coverage-xml", str(xml), "--state", str(state), "--bump", "0.5"]
            ):
                rc = mod.main()
            self.assertEqual(rc, 0)
            text = state.read_text(encoding="utf-8")
            self.assertIn("line_total: 90.0", text, "余量 ≥ 步长时上调到实测")
            self.assertIn("branch_total: 40.0", text, "余量 10pp ≥ 0.5 步长时上调到实测")
            # 再次运行：水位已贴实测，无步长余量 → 不再改写（水位稳定，只升不降）
            with patch.object(
                sys, "argv", ["ratchet", "--coverage-xml", str(xml), "--state", str(state), "--bump", "0.5"]
            ):
                rc2 = mod.main()
            self.assertEqual(rc2, 0)
            self.assertIn("line_total: 90.0", state.read_text(encoding="utf-8"))


# ═══ W4：QuixBugs / BugsInPy 加载器 ══════════════════════════════════════════


class TestW4RealBugsLoaders(unittest.TestCase):
    def test_quixbugs_degrades_without_data(self):
        from src.datasets import load_dataset

        with tempfile.TemporaryDirectory() as td:
            ds = load_dataset("quixbugs", data_dir=td)
            self.assertEqual(ds.size, 0, "目录缺失时空数据集优雅降级，不抛异常")

    def test_quixbugs_loads_fixture(self):
        from src.datasets import QuixBugsDataset

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(f"{td}/python_programs")
            os.makedirs(f"{td}/correct_python_programs")
            os.makedirs(f"{td}/python_testcases")
            Path(f"{td}/python_programs/buggyprog.py").write_text("def alg(a):\n    return 0\n", encoding="utf-8")
            Path(f"{td}/correct_python_programs/buggyprog.py").write_text(
                "def alg(a):\n    return 1\n", encoding="utf-8"
            )
            Path(f"{td}/python_testcases/buggyprog_test.py").write_text(
                "def test_alg():\n    from buggyprog import alg\n    assert alg(1) == 1\n", encoding="utf-8"
            )
            ds = QuixBugsDataset(data_dir=td)
            self.assertEqual(ds.size, 1)
            task = ds.tasks[0]
            self.assertEqual(task.task_id, "quixbugs__buggyprog")
            self.assertEqual(task.metadata["suggested_function"], "alg")
            self.assertTrue(task.metadata["fixed"].strip(), "gold 修复版必须可用（M1 F2P 判据）")
            self.assertTrue(task.metadata["test_cases"].strip(), "gold 测试必须可用（M1 detection）")

    def test_bugsinpy_manifest_and_m1_compat(self):
        from experiments._m1_metrics import _extract_gold_material
        from src.datasets import BugsInPyDataset

        with tempfile.TemporaryDirectory() as td:
            rows = [
                {
                    "project": "pandas",
                    "bug_id": "1-00001",
                    "file_path": "pandas/core/frame.py",
                    "buggy_code": "def f(x):\n    return x\n",
                    "fixed_code": "def f(x):\n    return x + 1\n",
                    "test_code": "def test_f():\n    from frame import f\n    assert f(1) == 2\n",
                },
                {"project": "bad", "bug_id": "x", "buggy_code": ""},  # 无效行：跳过
            ]
            Path(f"{td}/bugs_in_py_manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            ds = BugsInPyDataset(data_dir=td)
            self.assertEqual(ds.size, 1)
            task = ds.tasks[0]
            material = _extract_gold_material(task)
            self.assertIsNotNone(material, "M1 gold 材料必须开箱可用")
            assert material is not None
            module_name, gold_tests, gold_fixed = material
            self.assertEqual(module_name, "pandas_1_00001_frame")  # 中划线归一为下划线（M1 单点派生）
            self.assertIn("def test_f", gold_tests)
            self.assertIn("return x + 1", gold_fixed)

    def test_registered_in_factory(self):
        from src.datasets.dataset_loader import get_available_datasets, load_dataset

        avail = get_available_datasets()
        for name in ("quixbugs", "quix_bugs", "bugsinpy", "bugs_in_py"):
            self.assertIn(name, avail)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_dataset("bugs_in_py", data_dir=td).size, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
