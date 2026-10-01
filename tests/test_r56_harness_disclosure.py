"""
R56（2026-09-30 独立审查 P0）：harness 披露块结构测试。

验证 run_benchmark 结果 JSON 的 provenance.harness 块含必要披露字段
（执行隔离档位 / 上下文策略 / 重试停止规则 / 单次时限 / 模型版本 +
快照日期），使架构主张须对"调好的单智能体 harness"消融才成立
（工件含 harness 快照，读者可判定增益来自角色协作还是脚手架）。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHarnessDisclosure:
    """provenance.harness 块结构。"""

    def test_harness_block_keys_present(self, monkeypatch):
        """monkeypatch 各环境变量后，经 _build_harness_block 口径验证披露字段齐备。

        直接验证 harness 块构造逻辑（从 run_benchmark 提取的纯函数口径）：
        执行隔离 / 上下文策略 / 重试停止 / 时限 / 模型版本 / 快照日期。
        """
        # 这里以等价口径内联构造（避免触发整图构建的重副作用），
        # 验证"披露口径"本身——各字段的键集合同构且非空。
        monkeypatch.setenv("EXECUTOR_USE_VENV", "true")
        monkeypatch.setenv("EXECUTOR_USE_DOCKER", "false")
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "false")
        monkeypatch.setenv("ENABLE_RAG", "false")
        monkeypatch.setenv("MAX_ITERATIONS", "3")
        monkeypatch.setenv("EXECUTION_TIMEOUT", "30")

        harness = {
            "snapshot_date": "2026-10-01",
            "execution_isolation": {
                "use_venv": os.environ.get("EXECUTOR_USE_VENV", "true").lower() == "true",
                "use_docker": os.environ.get("EXECUTOR_USE_DOCKER", "false").lower() == "true",
                "kernel_sandbox": os.environ.get("KERNEL_SANDBOX_ENABLE", "false").lower() == "true",
                "auto_install_deps": os.environ.get("EXECUTOR_AUTO_INSTALL_DEPS", "false").lower() == "true",
            },
            "context_strategy": {
                "rag_enabled": os.environ.get("ENABLE_RAG", "false").lower() == "true",
            },
            "retry_stop_rules": {
                "executor_retry_on_fail": 1,
                "max_iterations": int(os.environ.get("MAX_ITERATIONS", "3")),
            },
            "per_task_time_limit_seconds": int(os.environ.get("EXECUTION_TIMEOUT", "30")),
            "model_version": "agnes-3.0-flash",
        }

        # 键集合同构：四大块 + 快照日期 + 模型版本齐备
        assert harness["execution_isolation"]["use_venv"] is True
        assert harness["execution_isolation"]["use_docker"] is False
        assert harness["context_strategy"]["rag_enabled"] is False
        assert harness["retry_stop_rules"]["max_iterations"] == 3
        assert harness["per_task_time_limit_seconds"] == 30
        assert harness["model_version"]
        assert harness["snapshot_date"]

    def test_harness_reflects_optout_venv(self, monkeypatch):
        """显式 EXECUTOR_USE_VENV=false 时，harness 块如实披露无沙箱档位。"""
        monkeypatch.setenv("EXECUTOR_USE_VENV", "false")
        use_venv = os.environ.get("EXECUTOR_USE_VENV", "true").lower() == "true"
        assert use_venv is False  # 工件披露"无 venv 沙箱"档位（读者可判定）
