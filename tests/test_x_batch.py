"""X 批次（2026-10-05 第七轮审查落地）回归测试。

覆盖：
- X1/P0-4a：LLM 缓存实验命名空间（AITESTER_CACHE_NAMESPACE，多 seed 独立性）
- X1/P0-3：plain_llm_df 归因基线（线程级检出优先覆盖 + allow_regeneration
  拓扑 + _route_no_debugger 路由包装 + 注册表）
- X2/P0-4b：统计管线 M1 schema 完备性过滤（--allow-schema-mixed 历史口径）
- C5/P1-4b：repo 级链路危险 API 守卫（"+" 行提取 + 拒绝应用）
- X3/P0-5：env 开关预算守卫（登记表一致性）
- X4/P2：py.typed 类型标记随包分发

全部用例零 LLM / 零网络 / 零子进程 / 零真实 git 仓库（守卫在任何
git 操作前返回；env 预算脚本经 importlib 进程内加载，与 W2 ratchet
测试同模式）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ENV_BUDGET_SCRIPT = PROJECT_ROOT / "scripts" / "check_env_budget.py"


def _load_env_budget_module():
    """进程内加载 env 预算脚本为模块（免子进程，直接断言返回码 int）。"""
    spec = importlib.util.spec_from_file_location("aitester_env_budget", _ENV_BUDGET_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ═══ X1/P0-4a：缓存实验命名空间 ═══════════════════════════════════════════


class TestX1CacheNamespace(unittest.TestCase):
    """缓存键加入 AITESTER_CACHE_NAMESPACE：不同命名空间不共享缓存条目。

    背景（审查 P0-4a）：缓存键不含 seed 且 seed 不传 API——多 seed 复跑
    在缓存开启时是同一响应的确定性重放，统计独立性失效。修复后命名
    空间参与哈希；默认空 = 键与历史逐字节一致。
    """

    def test_different_namespace_misses_cache(self):
        """同 prompt 在两个命名空间下各自真实调用；同命名空间命中缓存。"""
        from src.agents.base_agent import BaseAgent

        with tempfile.TemporaryDirectory() as cache_dir:
            os.environ["AITESTER_LLM_CACHE"] = "1"
            os.environ["AITESTER_LLM_CACHE_DIR"] = cache_dir
            os.environ.pop("AITESTER_CACHE_NAMESPACE", None)
            try:
                with (
                    patch.object(BaseAgent, "__init__", lambda self, sp: None),
                    patch.object(
                        BaseAgent,
                        "_call_llm",
                        side_effect=lambda *a, **k: "resp",
                    ) as mock_call,
                ):
                    agent = BaseAgent.__new__(BaseAgent)
                    agent.system_prompt = "sys"

                    os.environ["AITESTER_CACHE_NAMESPACE"] = "seed1"
                    agent._call_llm_with_cache("prompt-x")
                    os.environ["AITESTER_CACHE_NAMESPACE"] = "seed2"
                    agent._call_llm_with_cache("prompt-x")
                    # 两个命名空间互不可见 → 两次真实调用
                    self.assertEqual(mock_call.call_count, 2)

                    # 同命名空间第二次 → 命中缓存，不再调用
                    os.environ["AITESTER_CACHE_NAMESPACE"] = "seed1"
                    agent._call_llm_with_cache("prompt-x")
                    self.assertEqual(mock_call.call_count, 2)
            finally:
                os.environ.pop("AITESTER_CACHE_NAMESPACE", None)
                os.environ["AITESTER_LLM_CACHE"] = "0"

    def test_no_namespace_single_entry(self):
        """默认（未设命名空间）时同 prompt 只产出一个缓存条目（历史口径）。"""
        from src.agents.base_agent import BaseAgent

        with tempfile.TemporaryDirectory() as cache_dir:
            os.environ["AITESTER_LLM_CACHE"] = "1"
            os.environ["AITESTER_LLM_CACHE_DIR"] = cache_dir
            os.environ.pop("AITESTER_CACHE_NAMESPACE", None)
            try:
                with (
                    patch.object(BaseAgent, "__init__", lambda self, sp: None),
                    patch.object(BaseAgent, "_call_llm", return_value="r"),
                ):
                    agent = BaseAgent.__new__(BaseAgent)
                    agent.system_prompt = "sys"
                    agent._call_llm_with_cache("p1")
                    agent._call_llm_with_cache("p1")
                    files = [f for f in os.listdir(cache_dir) if f.endswith(".json")]
                    self.assertEqual(len(files), 1)
            finally:
                os.environ["AITESTER_LLM_CACHE"] = "0"


# ═══ X1/P0-3：plain_llm_df 归因基线 ════════════════════════════════════════


class TestX1DetectionFirstThreadOverride(unittest.TestCase):
    """config.set_detection_first_thread_override：线程级覆盖 > env。"""

    def test_override_beats_env(self):
        import config

        old = os.environ.get("DETECTION_FIRST_ENABLE")
        os.environ["DETECTION_FIRST_ENABLE"] = "false"
        config.set_detection_first_thread_override(True)
        try:
            self.assertTrue(config.detection_first_enabled())
        finally:
            config.set_detection_first_thread_override(None)
            if old is None:
                os.environ.pop("DETECTION_FIRST_ENABLE", None)
            else:
                os.environ["DETECTION_FIRST_ENABLE"] = old

    def test_none_falls_back_to_env(self):
        import config

        old = os.environ.get("DETECTION_FIRST_ENABLE")
        os.environ["DETECTION_FIRST_ENABLE"] = "true"
        config.set_detection_first_thread_override(None)
        try:
            self.assertTrue(config.detection_first_enabled())
        finally:
            if old is None:
                os.environ.pop("DETECTION_FIRST_ENABLE", None)
            else:
                os.environ["DETECTION_FIRST_ENABLE"] = old

    def test_override_cleared_in_finally_pattern(self):
        """模拟 plain_llm_df 基线的 set/finally-clear 用法：清除后回落 env。"""
        import config

        old = os.environ.get("DETECTION_FIRST_ENABLE")
        os.environ["DETECTION_FIRST_ENABLE"] = "false"
        config.set_detection_first_thread_override(True)
        try:
            pass
        finally:
            config.set_detection_first_thread_override(None)
        try:
            self.assertFalse(config.detection_first_enabled())
        finally:
            if old is None:
                os.environ.pop("DETECTION_FIRST_ENABLE", None)
            else:
                os.environ["DETECTION_FIRST_ENABLE"] = old


class TestX1RouteNoDebugger(unittest.TestCase):
    """_route_no_debugger：debug→done 映射 + 检出优先分支透传。"""

    @staticmethod
    def _green_state() -> dict:
        # 首轮全绿 + 已执行 + 未曾红 + 再生成预算未用尽
        return {
            "test_passed": True,
            "iteration": 0,
            "detection_first_red_seen": False,
            "regeneration_count": 0,
            "execution_trace": [{"passed": True}],
            "repair_history": [],
            "max_iterations": 3,
        }

    def test_all_green_with_override_routes_regenerate(self):
        import config
        from src.graph.workflow import _route_no_debugger

        old = os.environ.get("DETECTION_FIRST_ENABLE")
        os.environ["DETECTION_FIRST_ENABLE"] = "false"  # env 关——覆盖必须独立生效
        config.set_detection_first_thread_override(True)
        try:
            self.assertEqual(_route_no_debugger(self._green_state()), "regenerate")
        finally:
            config.set_detection_first_thread_override(None)
            if old is None:
                os.environ.pop("DETECTION_FIRST_ENABLE", None)
            else:
                os.environ["DETECTION_FIRST_ENABLE"] = old

    def test_failing_test_maps_debug_to_done(self):
        """测试失败（无 Debugger 可修）→ done：失败即潜在检出，交 M1 裁决。"""
        from src.graph.workflow import _route_no_debugger

        state = {
            "test_passed": False,
            "iteration": 0,
            "regeneration_count": 0,
            "repair_history": [],
            "max_iterations": 3,
        }
        self.assertEqual(_route_no_debugger(state), "done")

    def test_all_green_without_override_routes_done(self):
        """检出优先未启用（env 关 + 无覆盖）→ 全绿即 done（plain_llm 历史口径）。"""
        import config
        from src.graph.workflow import _route_no_debugger

        old = os.environ.get("DETECTION_FIRST_ENABLE")
        os.environ["DETECTION_FIRST_ENABLE"] = "false"
        config.set_detection_first_thread_override(None)
        try:
            self.assertEqual(_route_no_debugger(self._green_state()), "done")
        finally:
            if old is None:
                os.environ.pop("DETECTION_FIRST_ENABLE", None)
            else:
                os.environ["DETECTION_FIRST_ENABLE"] = old


class TestX1PlainLlmDfBaseline(unittest.TestCase):
    def test_registry_contains_attribution_baseline(self):
        """plain_llm_df 注册且不在默认三基线里（历史批次可比性保持）。"""
        from experiments.run_benchmark import BASELINE_REGISTRY

        self.assertIn("plain_llm_df", BASELINE_REGISTRY)
        self.assertTrue(callable(BASELINE_REGISTRY["plain_llm_df"]))
        self.assertNotIn("plain_llm_df", ["aitester", "plain_llm", "single_agent"])

    def test_build_workflow_allow_regeneration_topology(self):
        """allow_regeneration=True 时 executor 不再固定接 END（可再生成）。"""
        from src.graph.workflow import _create_workflow

        wf = _create_workflow(planner=False, debugger=False, allow_regeneration=True)
        self.assertNotIn(("executor", "__end__"), wf.edges)
        # 默认口径：固定 END 边（历史拓扑不变）
        wf_legacy = _create_workflow(planner=False, debugger=False)
        self.assertIn(("executor", "__end__"), wf_legacy.edges)


# ═══ X2/P0-4b：统计管线 M1 schema 过滤 ═════════════════════════════════════


def _write_batch(path: Path, with_m1: bool) -> None:
    row: dict = {"task_id": "synthetic__task_0001", "passed": True}
    if with_m1:
        row["detection_rate"] = 0.0
    data = {
        "dataset": "synthetic",
        "results": {"aitester": {"details": [row]}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")


class TestX2SchemaFilter(unittest.TestCase):
    def test_incomplete_batch_excluded_by_default(self):
        """缺 detection_rate 的批次默认剔除（不入审计清单）。"""
        from experiments.statistical_analysis import load_experiment_results_with_sources

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _write_batch(d / "benchmark_synthetic_20261005_010101.json", with_m1=True)
            _write_batch(d / "benchmark_synthetic_20261005_010202.json", with_m1=False)
            results, included = load_experiment_results_with_sources(td, None)
            self.assertEqual(len(included), 1)
            self.assertEqual(len(results.get("aitester", [])), 1)

    def test_allow_schema_mixed_restores_legacy(self):
        """allow_schema_mixed=True 恢复历史混批口径（两批都纳入）。"""
        from experiments.statistical_analysis import load_experiment_results_with_sources

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _write_batch(d / "benchmark_synthetic_20261005_010101.json", with_m1=True)
            _write_batch(d / "benchmark_synthetic_20261005_010202.json", with_m1=False)
            results, included = load_experiment_results_with_sources(td, None, allow_schema_mixed=True)
            self.assertEqual(len(included), 2)
            self.assertEqual(len(results.get("aitester", [])), 2)

    def test_main_batch_smoke_batches_filtered(self):
        """入库 main_batch：2 个 n=5 冒烟批次被剔除，仅主批次（n=50）纳入。"""
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results_dir = PROJECT_ROOT / "experiments" / "results"
        if not (results_dir / "main_batch").exists():
            self.skipTest("main_batch 工件不在库（精简 clone）")
        whitelist = [
            "main_batch/benchmark_synthetic_20261001_112528.json",
            "main_batch/benchmark_synthetic_20261001_112801.json",
            "main_batch/benchmark_synthetic_20261001_121523.json",
        ]
        results, included = load_experiment_results_with_sources(str(results_dir), whitelist)
        self.assertEqual(len(included), 1)
        self.assertEqual(len(results.get("aitester", [])), 50)


# ═══ C5/P1-4b：repo 链路危险 API 守卫 ══════════════════════════════════════


class TestC5RepoDangerousGuard(unittest.TestCase):
    @staticmethod
    def _executor():
        from src.agents.executor_repo import RepoExecutor

        return RepoExecutor(timeout=1, setup_timeout=1)

    def test_dangerous_added_line_collected(self):
        """'+' 行的 os.system（含 from-import 别名）被收集。"""
        patch_text = "@@ -1,1 +1,2 @@\n import math\n+from os import system as s\n+s('rm -rf /tmp/x')\n"
        found = self._executor()._llm_patch_dangerous_calls(patch_text)
        self.assertIn("os.system", found)

    def test_context_lines_ignored(self):
        """上下文行/删除行（非 '+' 前缀）不参与收集。"""
        patch_text = "@@ -1,2 +1,2 @@\n-os.system('old')\n import math\n"
        found = self._executor()._llm_patch_dangerous_calls(patch_text)
        self.assertEqual(found, set())

    def test_apply_rejected_before_git(self):
        """危险补丁在任何 git/写盘操作前被拒（无 git 仓库目录也返回 False）。"""
        ex = self._executor()
        patch_text = "@@ -1,1 +1,2 @@\n import math\n+import subprocess\n+subprocess.run(['ls'])\n"
        with tempfile.TemporaryDirectory() as repo_dir:
            self.assertFalse(ex._apply_llm_patch(repo_dir, patch_text))

    def test_apply_rejected_open_credentials(self):
        """凭证文件读取（新增行 open('.env')）同样拒绝。"""
        ex = self._executor()
        patch_text = "@@ -1,1 +1,2 @@\n import math\n+f = open('.env')\n"
        with tempfile.TemporaryDirectory() as repo_dir:
            self.assertFalse(ex._apply_llm_patch(repo_dir, patch_text))


# ═══ X3/P0-5：env 开关预算守卫 ═════════════════════════════════════════════


class TestX3EnvBudget(unittest.TestCase):
    def test_check_mode_passes_on_registered_table(self):
        """CI 口径：登记表 ⊇ 当前扫描面（--check 返回 0，不写回）。"""
        module = _load_env_budget_module()
        old_argv = sys.argv
        sys.argv = ["check_env_budget.py", "--check"]
        try:
            rc = module.main()
        finally:
            sys.argv = old_argv
        self.assertEqual(rc, 0)

    def test_scan_finds_known_switches(self):
        """扫描器提取已知开关（静态口径抽检）。"""
        module = _load_env_budget_module()
        names = module.scan_env_names()
        for known in ("AITESTER_LLM_CACHE", "DETECTION_FIRST_ENABLE", "ENABLE_PLANNER"):
            self.assertIn(known, names)


# ═══ X4/P2：py.typed ═══════════════════════════════════════════════════════


class TestX4PyTyped(unittest.TestCase):
    def test_py_typed_marker_and_package_data(self):
        """PEP 561 标记存在且 package-data 声明（wheel 随包分发）。"""
        self.assertTrue((PROJECT_ROOT / "src" / "py.typed").is_file())
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.setuptools.package-data]", pyproject)
        self.assertIn('src = ["py.typed"]', pyproject)


if __name__ == "__main__":
    unittest.main()
