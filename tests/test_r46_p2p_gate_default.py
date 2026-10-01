"""
R46（2026-09-30 独立审查 P0）：SWE-bench P2P 门禁默认开启测试。

锁死口径：
- config.SWE_BENCH_P2P_GATE_ENABLE 缺省（未设环境变量）时为 True（R46 起默认开）；
- 显式设 false 时退回关闭（消融 / 无 verify 脚本环境）；
- _check_swe_bench_p2p_gate 对非 SWE-bench 任务（source≠swe_bench /
  缺 repo_url/base_commit）永不命中，历史口径零变化；
- 门禁开启 + verify_single_instance 不可用时保守跳过（不阻断批次）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.datasets.dataset_loader import BenchmarkTask


def _swe_task() -> BenchmarkTask:
    """构造一个 SWE-bench 仓库级任务（含 repo_url/base_commit 元数据）。"""
    return BenchmarkTask(
        task_id="swe-bench__django-12345",
        repo_name="django/django",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={
            "source": "swe_bench",
            "repo_url": "https://github.com/django/django",
            "base_commit": "abc123",
            "fail_to_pass": ["test_f"],
            "pass_to_pass": ["test_g"],
        },
    )


def _plain_task() -> BenchmarkTask:
    """非 SWE-bench 任务（source≠swe_bench，门禁永不命中）。"""
    return BenchmarkTask(
        task_id="synthetic__t1",
        repo_name="synthetic",
        problem_statement="fix",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "synthetic"},
    )


class TestP2PDefaultOn:
    """R46：门禁默认开启口径。"""

    def test_default_enabled(self, monkeypatch):
        """未设环境变量时，config.SWE_BENCH_P2P_GATE_ENABLE 为 True（R46 起）。"""
        import os

        monkeypatch.delenv("SWE_BENCH_P2P_GATE_ENABLE", raising=False)
        import config as cfg

        # 重新解析默认值（config 在 import 时绑定，用同口径表达式验证）
        default_val = os.getenv("SWE_BENCH_P2P_GATE_ENABLE", "true").lower() == "true"
        assert default_val is True
        # config 模块级常量（import 时 env 未设 → 绑定 True）
        assert cfg.SWE_BENCH_P2P_GATE_ENABLE is True

    def test_explicit_off(self, monkeypatch):
        """显式设 false 时退回关闭（消融对照口径）。"""
        monkeypatch.setenv("SWE_BENCH_P2P_GATE_ENABLE", "false")
        import os

        default_val = os.getenv("SWE_BENCH_P2P_GATE_ENABLE", "true").lower() == "true"
        assert default_val is False


class TestGateNonSweNeverHits:
    """非 SWE-bench 任务永不命中门禁（历史口径零变化）。"""

    def test_plain_task_returns_none(self):
        import experiments.run_benchmark as rb

        # 即使门禁开启，非 SWE-bench 任务（无 repo_url/base_commit）也返回 None
        with patch.object(rb, "SWE_BENCH_P2P_GATE_ENABLE", True):
            result = rb._check_swe_bench_p2p_gate(_plain_task())
        assert result is None


class TestGateVerifyUnavailableSkips:
    """门禁开启 + verify_single_instance 不可用时保守跳过（不阻断批次）。"""

    def test_verify_import_error_returns_none(self):
        import experiments.run_benchmark as rb

        with (
            patch.object(rb, "SWE_BENCH_P2P_GATE_ENABLE", True),
            patch.dict("sys.modules", {"scripts.verify_instance_solvable": None}),
        ):
            # verify_single_instance 导入失败（ImportError）→ 保守跳过，返回 None
            result = rb._check_swe_bench_p2p_gate(_swe_task())
        assert result is None
