"""workflow.py 内部分支补测（2026-10-02 审查：分支覆盖门禁回绿）。

背景：`graph/workflow.py` 是 `scripts/check_branch_coverage.py` 的
90% 严格门槛核心模块，StopReason / M12 checkpointer / M4 递归限制
包装等本批次改动落地后分支覆盖跌至 82%，CI 门禁变红。本文件针对
coverage.xml 中剩余 missing branches 逐一补测：

  1. `_route_after_diagnosis` 的两个 M4 收敛 done 分支（test_passed /
     iteration 达上限）；
  2. `build_workflow` 缓存卫生钩子（缓存开 + 清理数 >0 / 清理异常）；
  3. M12 RISK_APPROVAL checkpointer 注入路径；
  4. `_RecursionLimitedGraph` invoke / ainvoke 的显式 config 分支与
     thread_id 注入分支；
  5. `_file_cache_entry_count` 记忆复用快路径（mtime 未变免重扫）。
"""

from __future__ import annotations

import asyncio

import pytest

from src.graph.workflow import _route_after_diagnosis, build_workflow


def _state(**overrides) -> dict:
    base = {
        "test_passed": False,
        "iteration": 0,
        "max_iterations": 3,
        "diagnosis": "",
        "defect_type": None,
        "regeneration_count": 0,
        "repair_history": [],
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


@pytest.mark.unit
class TestRouteAfterDiagnosisConvergence:
    """M4 收敛保护：test_passed / 迭代达上限两个 done 分支。"""

    def test_test_passed_routes_done(self):
        assert _route_after_diagnosis(_state(test_passed=True)) == "done"

    def test_iteration_at_max_routes_done(self):
        assert _route_after_diagnosis(_state(iteration=3, max_iterations=3)) == "done"

    def test_iteration_over_max_routes_done(self):
        assert _route_after_diagnosis(_state(iteration=5, max_iterations=3)) == "done"

    def test_iteration_missing_defaults_zero_routes_debug(self):
        # iteration 缺省 0 < max 缺省 3 → 不收敛，走 debug
        state = _state()
        state.pop("iteration")
        assert _route_after_diagnosis(state) == "debug"

    def test_stop_reason_written_on_convergence(self):
        state = _state(test_passed=True)
        _route_after_diagnosis(state)
        assert state.get("stop_reason") == "test_passed"


@pytest.mark.unit
class TestBuildWorkflowCacheHygiene:
    """build_workflow 缓存卫生钩子（18. LLM 缓存过期清理）分支。"""

    def test_cache_enabled_cleanup_runs(self, monkeypatch):
        """缓存开 + 清理返回 >0 → 走 logger.info 分支且不阻断构建。"""
        import src.agents.llm_client as lc
        import src.graph.workflow as wf

        monkeypatch.setattr(wf, "_llm_cache_enabled", lambda: True)
        monkeypatch.setattr(lc, "ensure_llm_cache_dir", lambda: None)
        monkeypatch.setattr(lc, "cleanup_expired_cache_files", lambda: 3)
        g = build_workflow()
        assert g is not None

    def test_cache_enabled_zero_removed_skips_log(self, monkeypatch):
        """清理返回 0 → 不进 if removed 分支。"""
        import src.agents.llm_client as lc
        import src.graph.workflow as wf

        monkeypatch.setattr(wf, "_llm_cache_enabled", lambda: True)
        monkeypatch.setattr(lc, "ensure_llm_cache_dir", lambda: None)
        monkeypatch.setattr(lc, "cleanup_expired_cache_files", lambda: 0)
        assert build_workflow() is not None

    def test_cleanup_exception_does_not_block(self, monkeypatch):
        """清理抛异常 → except 分支吞掉，工作流照常构建。"""
        import src.agents.llm_client as lc
        import src.graph.workflow as wf

        def _boom():
            raise OSError("磁盘只读")

        monkeypatch.setattr(wf, "_llm_cache_enabled", lambda: True)
        monkeypatch.setattr(lc, "ensure_llm_cache_dir", lambda: None)
        monkeypatch.setattr(lc, "cleanup_expired_cache_files", _boom)
        assert build_workflow() is not None

    def test_cache_disabled_skips_block(self, monkeypatch):
        """缓存关（默认）→ 整个 try 块内 if 不命中（历史口径）。"""
        import src.graph.workflow as wf

        monkeypatch.setattr(wf, "_llm_cache_enabled", lambda: False)
        assert build_workflow() is not None


@pytest.mark.unit
class TestRiskApprovalCheckpointer:
    """M12：RISK_APPROVAL_ENABLE=true 注入 MemorySaver checkpointer。"""

    def test_enabled_injects_checkpointer(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        g = build_workflow()
        assert getattr(g, "_has_checkpointer", False) is True, "M12 应注入 checkpointer"
        # thread_id 缺省 "default"（_build_config 语义）
        assert g._build_config()["configurable"]["thread_id"] == "default"
        assert g._build_config("task-1")["configurable"]["thread_id"] == "task-1"

    def test_disabled_no_checkpointer(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        assert getattr(g, "_has_checkpointer", False) is False
        assert "configurable" not in g._build_config()


@pytest.mark.unit
class TestRecursionLimitedGraphInvoke:
    """M4 包装：invoke / ainvoke 的显式 config 分支与 thread_id 注入。"""

    def test_invoke_with_explicit_config_passthrough(self, monkeypatch):
        """调用方显式传 config → 原样透传（不覆盖）。"""
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        seen = {}

        class _FakeGraph:
            def invoke(self, *args, **kwargs):
                seen.update(kwargs)
                return "ok"

        g._graph = _FakeGraph()
        cfg = {"recursion_limit": 42}
        assert g.invoke({"x": 1}, config=cfg) == "ok"
        assert seen["config"] is cfg

    def test_invoke_without_config_injects(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        seen = {}

        class _FakeGraph:
            def invoke(self, *args, **kwargs):
                seen.update(kwargs)
                return "ok"

        g._graph = _FakeGraph()
        assert g.invoke({"x": 1}, thread_id="t-9") == "ok"
        # E1/E2 实测：4×MAX+8 与 8×MAX+8 均触顶（2/12 与 16/174）→ 16×MAX+8
        assert seen["config"]["recursion_limit"] == 16 * 3 + 8
        # 无 checkpointer 时 configurable 不注入
        assert "configurable" not in seen["config"]

    def test_invoke_getattr_delegates(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        # __getattr__ 透传：底层 CompiledStateGraph 有 get_graph 等方法
        assert hasattr(g, "get_graph")

    def test_ainvoke_with_explicit_config_passthrough(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        seen = {}

        class _FakeGraph:
            async def ainvoke(self, *args, **kwargs):
                seen.update(kwargs)
                return "aok"

        g._graph = _FakeGraph()
        cfg = {"recursion_limit": 7}
        assert asyncio.run(g.ainvoke({"x": 1}, config=cfg)) == "aok"
        assert seen["config"] is cfg

    def test_ainvoke_without_config_injects(self, monkeypatch):
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "false")
        g = build_workflow()
        seen = {}

        class _FakeGraph:
            async def ainvoke(self, *args, **kwargs):
                seen.update(kwargs)
                return "aok"

        g._graph = _FakeGraph()
        assert asyncio.run(g.ainvoke({"x": 1})) == "aok"
        # E1/E2 实测：4×MAX+8 与 8×MAX+8 均触顶（2/12 与 16/174）→ 16×MAX+8
        assert seen["config"]["recursion_limit"] == 16 * 3 + 8

    def test_ainvoke_thread_id_injected_when_checkpointer(self, monkeypatch):
        """checkpointer 开时 ainvoke 注入 configurable.thread_id（默认 default）。"""
        monkeypatch.setenv("RISK_APPROVAL_ENABLE", "true")
        g = build_workflow()
        seen = {}

        class _FakeGraph:
            async def ainvoke(self, *args, **kwargs):
                seen.update(kwargs)
                return "aok"

        g._graph = _FakeGraph()
        asyncio.run(g.ainvoke({"x": 1}))
        assert seen["config"]["configurable"]["thread_id"] == "default"


@pytest.mark.unit
class TestFileCacheCountMemoryFastPath:
    """_file_cache_entry_count 记忆复用快路径（mtime 未变免 glob 重扫）。"""

    def test_same_dir_same_mtime_reuses_memory(self, monkeypatch, tmp_path):
        import src.graph.workflow as wf

        cache_dir = tmp_path / "cache_fast"
        cache_dir.mkdir()
        (cache_dir / "a.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))
        monkeypatch.setattr(wf, "_FILE_CACHE_COUNT_MEMORY", None)
        from src.agents.llm_client import clear_llm_cache_option_memory

        clear_llm_cache_option_memory()

        # 首次统计（建立记忆）
        assert wf._file_cache_entry_count() == 1
        remembered = wf._FILE_CACHE_COUNT_MEMORY
        assert remembered is not None
        # 人为把记忆的 mtime 回写为当前目录 stat mtime（保证相等），
        # 并把计数改为哨兵值——若走快路径，返回哨兵（不重扫）；
        # 若重扫，返回真实条目数 1。快路径语义由此可判。
        import os

        current_mtime = os.stat(cache_dir).st_mtime
        monkeypatch.setattr(wf, "_FILE_CACHE_COUNT_MEMORY", (remembered[0], 99, current_mtime))
        assert wf._file_cache_entry_count() == 99, "mtime 未变应复用记忆（免 glob 重扫）"
