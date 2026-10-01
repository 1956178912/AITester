"""
graph/tracing.py 核心路由模块分支覆盖补齐（P0-1，2026-10-02 审查）。

补齐 start_task_trace / end_task_trace / _trace_node 的组合路由分支：
- start_task_trace: 文件追踪开/关 × 内存缓冲开/关 的四象限；
- end_task_trace: session=None 早退 + session 存在时入缓冲；
- _trace_node: session=None no-op + session 存在时全参数 / 部分参数透传。
"""

from __future__ import annotations

import src.graph.tracing as tracing_mod
from src.graph.tracing import (
    _trace_node,
    end_task_trace,
    start_task_trace,
)


class TestStartTaskTraceBranches:
    """start_task_trace 的四象限路由分支。"""

    def test_both_disabled_sets_none(self, monkeypatch):
        """文件追踪 + 内存缓冲双关：线程局部置 None（历史零开销口径）。"""
        monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        # 先用 session 存在的路径建好线程局部属性，再验证双关时被置 None
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        start_task_trace("warmup")
        end_task_trace(None)
        # 回到双关
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        tracing_mod._trace_local.session = "sentinel"
        start_task_trace("t1")
        assert tracing_mod._trace_local.session is None

    def test_file_on_buffer_off(self, monkeypatch, tmp_path):
        """仅文件追踪开：建 session（写盘口径）。"""
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        start_task_trace("t2", task_meta={"k": "v"})
        session = tracing_mod._trace_local.session
        assert session is not None
        assert session.task_id == "t2"
        # 收尾清除，避免污染后续用例
        end_task_trace(True)
        assert tracing_mod._trace_local.session is None

    def test_file_off_buffer_on(self, monkeypatch):
        """仅内存缓冲开（O35 修复后）：也建 session（内存累积供失败诊断）。"""
        monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        start_task_trace("t3")
        session = tracing_mod._trace_local.session
        assert session is not None
        assert session.task_id == "t3"
        end_task_trace(None)
        assert tracing_mod._trace_local.session is None

    def test_both_on(self, monkeypatch, tmp_path):
        """文件追踪 + 内存缓冲双开：建 session 且收尾入缓冲。"""
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        start_task_trace("t4")
        session = tracing_mod._trace_local.session
        assert session is not None
        end_task_trace(True, token_snapshot={"total_tokens": 3})
        assert tracing_mod._trace_local.session is None
        from src.observability import trace as trace_mod

        with trace_mod._memory_ring_lock:
            ring = list(trace_mod._memory_ring)
        assert ring and ring[-1]["task"] == "t4"


class TestEndTaskTraceBranches:
    """end_task_trace 的 session=None 早退分支。"""

    def test_early_return_when_session_none(self, monkeypatch):
        """线程局部无 session（双关或未 start）：早退不报错。"""
        monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        monkeypatch.setattr(tracing_mod._trace_local, "session", None)
        end_task_trace(True, token_snapshot={"total_tokens": 1})  # no-op
        # 未入缓冲
        from src.observability import trace as trace_mod

        with trace_mod._memory_ring_lock:
            ring = list(trace_mod._memory_ring)
        assert not any(r.get("task") == "nonexistent" for r in ring)


class TestTraceNodeBranches:
    """_trace_node 的 session=None / session 存在 + 参数子集分支。"""

    def test_noop_when_session_none(self, monkeypatch):
        """双关 + 未 start：_trace_node no-op（零 I/O、零对象分配）。"""
        monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        monkeypatch.setattr(tracing_mod._trace_local, "session", None)
        _trace_node("planner")  # 全默认参数 no-op
        assert tracing_mod._trace_local.session is None

    def test_full_params_when_session_exists(self, monkeypatch, tmp_path):
        """session 存在 + 全参数透传给 record_node。"""
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        start_task_trace("t5")
        session = tracing_mod._trace_local.session
        _trace_node(
            "executor",
            output_summary={"passed": False},
            decision="FAIL",
            duration_ms=12.5,
            iteration=2,
            input_summary={"n": 1},
            token_usage={"total_tokens": 9},
            decision_reason="assert",
            strategy_selected="single",
            budget_remaining=100,
        )
        node_events = [r for r in session.records if r.get("event") == "node"]
        assert node_events, "节点事件应已累积"
        ev = node_events[-1]
        assert ev["node"] == "executor"
        assert ev["decision"] == "FAIL"
        assert ev["duration_ms"] == 12.5
        # output_summary 经 _summarize 后键名为 "output"
        assert ev.get("output") == {"passed": False}
        assert ev["iteration"] == 2
        assert ev.get("input") == {"n": 1}
        assert ev.get("token_usage") == {"total_tokens": 9}
        assert ev.get("decision_reason") == "assert"
        assert ev.get("strategy_selected") == "single"
        assert ev.get("budget_remaining") == 100
        end_task_trace(False)

    def test_partial_params_when_session_exists(self, monkeypatch, tmp_path):
        """session 存在 + 仅 decision（其余 None）：缺省参数不写记录。"""
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        start_task_trace("t6")
        session = tracing_mod._trace_local.session
        _trace_node("planner", decision="plan_complete")
        node_events = [r for r in session.records if r.get("event") == "node"]
        ev = node_events[-1]
        assert ev["decision"] == "plan_complete"
        # 缺省参数不应以 None 键写入记录
        assert "duration_ms" not in ev or ev["duration_ms"] is None
        end_task_trace(True)
