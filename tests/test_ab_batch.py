"""AB 批次（2026-10-06 生死实验根因修复）测试。

覆盖：
- AB1：M10 强校验拒绝降级出口（LOGIC_SPEC_STRICT_FALLBACK_ENABLE，
  默认 false 保持 raise；true 时标记 logic_spec_rejected 继续）+
  logic 档预设注入（AA 教训：动态全键清理）；
- AB2：provenance profile 字段（ACTIVE_PROFILE 透出，源文本口径断言）；
- AB3：结果行 spec_compile_rate 透出（成功/失败分支键集合同构）；
- AB4：多种子统计拼接口径（pool_seeds——异种子前缀拼接不折叠、
  同种子重复跑仍折叠、无 seed 批次文件名兜底、CLI 旗标接线）。

不触网、不调用真实 LLM。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CODE = "def add(a, b):\n    return a + b\n"

# 缺 logic_analysis 的最小响应（触发 M10 缺失路径）
_NO_LOGIC_RESPONSE = {
    "function_name": "add",
    "description": "两整数相加",
    "test_cases": [{"name": "t1", "input": {"a": 1, "b": 2}, "expected": 3}],
}

# logic_analysis 存在但字段非法（input_domain 非字符串 → schema findings 路径）
_BAD_SCHEMA_RESPONSE = {
    "function_name": "add",
    "description": "x",
    "logic_analysis": {
        "input_domain": 123,
        "output_domain": "",
        "preconditions": [],
        "postconditions": [],
        "edge_cases": [],
    },
    "test_cases": [],
}


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


# ═══ AB1：M10 强校验拒绝降级出口 ═════════════════════════════════════════


class TestAB1StrictFallback:
    """M10 strict 拒绝出口：默认 raise，fallback 开启时标记降级继续。"""

    def test_strict_missing_logic_raises_by_default(self, monkeypatch):
        """strict 开 + fallback 关（默认）→ ValueError（历史口径锁定）。"""
        import pytest

        from src.agents.planner import PlannerAgent

        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "true")
        monkeypatch.delenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", raising=False)
        p = PlannerAgent()
        with (
            patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_NO_LOGIC_RESPONSE)),
            pytest.raises(ValueError, match="logic_analysis 缺失"),
        ):
            p.plan(_CODE)

    def test_strict_missing_logic_fallback_marks_and_continues(self, monkeypatch):
        """strict 开 + fallback 开 → 不抛异常，标记 logic_spec_rejected 后继续。"""
        from src.agents.planner import PlannerAgent

        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "true")
        monkeypatch.setenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", "true")
        p = PlannerAgent()
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_NO_LOGIC_RESPONSE)):
            result = p.plan(_CODE)
        # 降级标记 + 空逻辑字段已填充（degraded 路径照常走）
        assert "logic_analysis 缺失" in result["logic_spec_rejected"]
        assert result["logic_degraded"] is True
        assert result["logic_analysis"]["input_domain"] == ""
        # 计划本体不受影响（吞吐恢复的语义：任务继续）
        assert result["function_name"] == "add"
        assert len(result["test_cases"]) == 1

    def test_strict_schema_fail_raises_by_default(self, monkeypatch):
        """strict 开 + fallback 关：schema 校验失败路径 → ValueError。"""
        import pytest

        from src.agents.planner import PlannerAgent

        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "true")
        monkeypatch.delenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", raising=False)
        p = PlannerAgent()
        with (
            patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_BAD_SCHEMA_RESPONSE)),
            pytest.raises(ValueError, match="schema 校验失败"),
        ):
            p.plan(_CODE)

    def test_strict_schema_fail_fallback_marks(self, monkeypatch):
        """strict 开 + fallback 开：schema 失败路径 → 标记降级继续。"""
        from src.agents.planner import PlannerAgent

        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "true")
        monkeypatch.setenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", "true")
        p = PlannerAgent()
        with patch.object(p, "_call_llm_with_cache", return_value=json.dumps(_BAD_SCHEMA_RESPONSE)):
            result = p.plan(_CODE)
        assert "schema 校验失败" in result["logic_spec_rejected"]
        assert result["logic_degraded"] is True

    def test_fallback_env_parsing_variants(self, monkeypatch):
        """fallback 开关解析口径：true/1/on 为真，其余默认关。"""
        from src.agents import planner

        monkeypatch.delenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", raising=False)
        assert planner._logic_spec_strict_fallback_enabled() is False
        for val in ("true", "1", "on"):
            monkeypatch.setenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", val)
            assert planner._logic_spec_strict_fallback_enabled() is True
        for val in ("false", "0", "off", "yes", "tr ue", "enabled"):
            monkeypatch.setenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", val)
            assert planner._logic_spec_strict_fallback_enabled() is False

    def test_logic_profile_preset_injects_fallback(self, monkeypatch):
        """logic 档预设注入 LOGIC_SPEC_STRICT_FALLBACK_ENABLE。

        AA 批次教训：profile setdefault 注入会跨用例泄漏——快照全部
        环境键，finally 里删除一切新增键后再 reload 还原无档状态。
        """
        import importlib

        before_keys = set(os.environ.keys())
        try:
            monkeypatch.setenv("AITESTER_PROFILE", "logic")
            cfg = importlib.import_module("config")
            importlib.reload(cfg)
            assert cfg.ACTIVE_PROFILE == "logic"
            assert os.environ["LOGIC_SPEC_STRICT_FALLBACK_ENABLE"] == "true"
            assert os.environ["LOGIC_SPEC_STRICT_ENABLE"] == "true"
        finally:
            # 全键清理：删除 reload 注入的一切新增键（不限于本用例断言的键）
            for k in set(os.environ.keys()) - before_keys:
                os.environ.pop(k, None)
            cfg = importlib.import_module("config")
            importlib.reload(cfg)
            assert cfg.ACTIVE_PROFILE is None, "清理后 config 应回到无档默认态"


# ═══ AB2：provenance profile 字段 ════════════════════════════════════════


class TestAB2ProvenanceProfile:
    """provenance 显式记录生效 profile（生死实验观测缺口）。"""

    def test_active_profile_importable_by_run_benchmark(self):
        """run_benchmark 模块加载即验证 ACTIVE_PROFILE 导入契约。"""
        import config

        assert hasattr(config, "ACTIVE_PROFILE")  # None（默认档）或档名
        import experiments.run_benchmark as rb

        assert rb.ACTIVE_PROFILE is config.ACTIVE_PROFILE

    def test_provenance_source_wires_active_profile(self):
        """run_benchmark 把 ACTIVE_PROFILE 写入 provenance + 快照键含
        profile 原文与 fallback 开关（run_benchmark 主函数副作用重，按
        R56 harness 披露测试的同等源文本口径断言）。"""
        import inspect

        import experiments.run_benchmark as rb

        src = inspect.getsource(rb.run_benchmark)
        assert '"profile": ACTIVE_PROFILE' in src, "provenance 必须显式含 profile 字段"
        assert '"AITESTER_PROFILE"' in src, "快照键必须含 profile 原文"
        assert '"LOGIC_SPEC_STRICT_FALLBACK_ENABLE"' in src, "快照键必须含 M10 降级开关"


# ═══ AB3：结果行 spec_compile_rate 透出 ══════════════════════════════════


class TestAB3SpecCompileRateRow(unittest.TestCase):
    """spec_compile_rate 行级透出（成功透传 / 失败占位键集合同构）。"""

    def test_success_branch_carries_rate(self):
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True, "spec_compile_rate": 0.75},
        )
        self.assertEqual(row.get("spec_compile_rate"), 0.75)
        # 相邻观测字段仍在（键集合同构不回退）
        self.assertIn("detection_first_status", row)
        self.assertIn("regeneration_count", row)

    def test_failure_branch_placeholder_keeps_key_isomorphism(self):
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(_make_task(), 0.5, diagnosis="异常", error_category="error")
        self.assertIsNone(row.get("spec_compile_rate"))
        self.assertIn("spec_compile_rate", row)

    def test_dsl_off_state_keeps_none(self):
        """SPEC_IR_DSL_ENABLE 关（state 无键）→ None 占位（历史口径）。"""
        from experiments.run_benchmark import _build_task_result

        row = _build_task_result(
            _make_task(),
            1.0,
            final_state={"passed": True},
        )
        self.assertIsNone(row.get("spec_compile_rate"))


# ═══ AB4：多种子统计拼接口径 ═════════════════════════════════════════════


def _write_batch(path, seed: int | None, detection_by_task: dict[str, float], baseline: str = "aitester") -> None:
    """写一个最小 M1 schema 完备批次文件（detection_rate 非 None 行存在）。"""
    details = [
        {
            "task_id": tid,
            "passed": False,
            "detection_rate": det,
            "repair_rate": 0.0,
            "false_fix_rate": 0.0,
        }
        for tid, det in detection_by_task.items()
    ]
    doc = {
        "dataset": "synthetic",
        "results": {baseline: {"details": details}},
    }
    if seed is not None:
        doc["provenance"] = {"seed": seed}
    path.write_text(json.dumps(doc), encoding="utf-8")


class TestAB4PoolSeeds:
    """pool_seeds：异种子拼接不折叠、同种子重复跑仍折叠。"""

    def test_pool_seeds_prefixes_and_pools(self, tmp_path):
        """3 种子同 task_id → pool_seeds=True 按 seed 前缀分层 3 行。"""
        from experiments.statistical_analysis import load_experiment_results

        for seed in (42, 43, 44):
            _write_batch(tmp_path / f"benchmark_synthetic_20261006_1{seed}.json", seed, {"t1": 1.0})

        pooled = load_experiment_results(str(tmp_path), pool_seeds=True)
        ids = [r["task_id"] for r in pooled["aitester"]]
        assert sorted(ids) == ["s42__t1", "s43__t1", "s44__t1"], "异种子行必须按 seed 前缀分层"

    def test_pool_seeds_same_seed_rerun_still_dedups(self, tmp_path):
        """同 seed 两份批次（重跑协议）→ 前缀相同，_pair_by_task 仍折叠。"""
        from experiments.statistical_analysis import _pair_by_task, load_experiment_results

        _write_batch(tmp_path / "benchmark_synthetic_20261006_010101.json", 42, {"t1": 1.0})
        _write_batch(tmp_path / "benchmark_synthetic_20261006_020202.json", 42, {"t1": 0.0})

        pooled = load_experiment_results(str(tmp_path), pool_seeds=True)
        rows = pooled["aitester"]
        assert all(r["task_id"] == "s42__t1" for r in rows)
        # _pair_by_task 对同 id 行首见（= 最新时间戳批次）优先 → 只剩 1 对
        _a, _b, common = _pair_by_task(rows, rows)
        assert len(common) == 1

    def test_pool_seeds_missing_seed_falls_back_to_file_stem(self, tmp_path):
        """无 provenance.seed 的批次 → 文件名 stem 前缀（跨文件不折叠）。"""
        from experiments.statistical_analysis import load_experiment_results

        _write_batch(tmp_path / "benchmark_synthetic_20261006_030303.json", None, {"t1": 1.0})
        _write_batch(tmp_path / "benchmark_synthetic_20261006_040404.json", None, {"t1": 0.0})

        pooled = load_experiment_results(str(tmp_path), pool_seeds=True)
        ids = sorted(r["task_id"] for r in pooled["aitester"])
        assert ids == [
            "benchmark_synthetic_20261006_030303__t1",
            "benchmark_synthetic_20261006_040404__t1",
        ]

    def test_paired_pooled_6_vs_2_semantics(self, tmp_path):
        """端到端语义：3 种子 × 2 任务同名对 → pooled 配对数 6（默认口径 2）。"""
        from experiments.statistical_analysis import _pair_by_task, load_experiment_results

        for seed in (42, 43, 44):
            _write_batch(
                tmp_path / f"benchmark_synthetic_20261006_1{seed}.json",
                seed,
                {"t1": 1.0, "t2": 0.0},
            )
            _write_batch(
                tmp_path / f"benchmark_synthetic_20261006_1{seed}b.json",
                seed,
                {"t1": 0.0, "t2": 1.0},
                baseline="plain_llm",
            )

        default = load_experiment_results(str(tmp_path))
        _, _, common_default = _pair_by_task(default["aitester"], default["plain_llm"], field="detection_rate")
        pooled = load_experiment_results(str(tmp_path), pool_seeds=True)
        _, _, common_pooled = _pair_by_task(pooled["aitester"], pooled["plain_llm"], field="detection_rate")
        assert len(common_default) == 2, "历史口径：同 task_id 折叠后只剩单种子配对"
        assert len(common_pooled) == 6, "pool 口径：3 种子 × 2 任务全量进入配对"

    def test_cli_flag_parses(self, monkeypatch):
        """--pool-seeds CLI 旗标接线（argparse 解析 + 透传 run_all_statistics）。"""
        import experiments.statistical_analysis as sa

        captured: dict = {}

        def fake_run_all(*args, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(sys, "argv", ["statistical_analysis.py", "--pool-seeds", "--batches", "a.json"])
        monkeypatch.setattr(sa, "run_all_statistics", fake_run_all)
        sa.main()
        assert captured.get("pool_seeds") is True
        assert captured.get("batch_files") == ["a.json"]


if __name__ == "__main__":
    unittest.main()
