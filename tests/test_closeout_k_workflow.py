"""KB 覆盖率收口：`src/graph/workflow.py` 的停滞检测 / 缓存统计 / 可观测降级分支。

动机：workflow 补口前 17 行未覆盖，且缺口全是**观测层与卫生性操作的失败降级**
（覆盖率停滞检测窗口参数坏值、目录被外部删除后的记忆失效、get_workflow_stats
三段统计读取异常、MemorySaver 缺失时跳过 checkpointer）。观测层缺陷不会让主
流程崩，但会让实验报告数字静默失真——正好是最需要锁定口径的地方。

纪律：零 LLM / 零网络 / 零真实缓存目录写入（`tmp_path`）；不构建真实工作流图
（除 MemorySaver 缺失用例必须走 build_workflow 的编译路径，该用例只建简化拓扑）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.graph import workflow as wf


@pytest.mark.unit
class TestCoverageStallParams:
    """P2-4 停滞检测的窗口/阈值参数坏值回退。"""

    def test_rounds_invalid_env_falls_back_to_two(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COVERAGE_STALL_ROUNDS", "两轮")
        assert wf._coverage_stall_rounds() == 2

    def test_eps_invalid_env_falls_back_to_half_point(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COVERAGE_STALL_EPS", "零点五")
        assert wf._coverage_stall_eps() == 0.5

    def test_detected_false_when_recent_round_passed(self, monkeypatch: pytest.MonkeyPatch):
        """最近窗口内有一轮 test_passed=True → 不判停滞（修复可能已生效）。"""
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        state = {
            "test_passed": False,
            "execution_trace": [
                {"passed": False, "coverage_delta": 0.1},
                {"passed": True, "coverage_delta": 0.1},
            ],
        }
        assert wf._coverage_stall_detected(state) is False  # type: ignore[arg-type]


@pytest.mark.unit
class TestFileCacheEntryCountMemory:
    """缓存条目数进程内记忆：目录被外部删除时记忆失效并归 0。"""

    def test_glob_oserror_degrades_to_zero(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """目录可 stat 但 glob 抛 OSError（权限/网络盘）→ 归 0 并记忆，不抛异常。"""

        class _ExplodingPath:
            def __init__(self, path: str) -> None:
                self.path = path

            def glob(self, pattern: str):
                raise OSError("目录不可读（模拟）")

        monkeypatch.setattr(wf, "_FILE_CACHE_COUNT_MEMORY", None)
        monkeypatch.setattr(wf, "Path", _ExplodingPath)
        monkeypatch.setattr(wf, "_llm_cache_dir", lambda: str(tmp_path / "unreadable"))
        assert wf._file_cache_entry_count() == 0
        assert (str(tmp_path / "unreadable"), 0, 0.0) == wf._FILE_CACHE_COUNT_MEMORY

    def test_stale_memory_with_deleted_dir_returns_zero(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        cache_dir = tmp_path / "llm_cache"
        cache_dir.mkdir()
        (cache_dir / "a.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(wf, "_llm_cache_dir", lambda: str(cache_dir))
        assert wf._file_cache_entry_count() == 1  # 首次统计建立记忆
        (cache_dir / "a.json").unlink()
        cache_dir.rmdir()
        assert wf._file_cache_entry_count() == 0, "目录消失（OSError）后不得复用旧记忆值"


@pytest.mark.unit
class TestWorkflowStatsFailureDegradation:
    """get_workflow_stats 的三段观测统计读取失败均保守跳过（不抛异常）。"""

    def test_budget_and_semantic_stats_failure_skipped(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.budget.cost_budget.get_process_budget_stats",
            lambda: (_ for _ in ()).throw(RuntimeError("预算统计损坏（模拟）")),
        )
        stats = wf.get_workflow_stats()
        assert "llm_cache" in stats
        assert "workflow_config" in stats
        assert "cost_budget" not in stats
        assert "semantic_cache" not in stats

    def test_cache_hit_rate_failure_skipped(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.agents.llm_client.get_cache_hit_rate",
            lambda: (_ for _ in ()).throw(RuntimeError("命中率统计损坏（模拟）")),
        )
        stats = wf.get_workflow_stats()
        assert "hit_rate" not in stats["llm_cache"]

    def test_tiered_cache_stats_failure_skipped(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.agents.semantic_cache.get_semantic_cache_stats",
            lambda: (_ for _ in ()).throw(RuntimeError("分层统计损坏（模拟）")),
        )
        stats = wf.get_workflow_stats()
        assert "tiered_cache_stats" not in stats


@pytest.mark.unit
class TestBuildWorkflowCheckpointerDegradation:
    """M12：RISK_APPROVAL_ENABLE 开启但 langgraph checkpoint 不可用 → 跳过注入。"""

    def test_missing_memory_saver_skips_checkpointer(self, monkeypatch: pytest.MonkeyPatch, caplog):
        import logging

        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        # sys.modules 中置 None：`from langgraph.checkpoint.memory import MemorySaver`
        # 会抛 ImportError（模拟可选依赖缺失的部署环境）
        monkeypatch.setitem(sys.modules, "langgraph.checkpoint.memory", None)
        with caplog.at_level(logging.WARNING, logger="src.graph.workflow"):
            graph = wf.build_workflow(planner=False, debugger=False)
        assert graph is not None
        assert "MemorySaver 不可用" in caplog.text
