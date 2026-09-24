"""
src.graph.tracing 直接单元测试（线程局部会话管理）。

test_trace_observability.py 已覆盖 workflow 接线的启用/禁用行为，
本文件补 graph.tracing 自身的两条不变式：
- start_task_trace 后 _trace_local.session 挂载，end_task_trace 后清空；
- 未 start 直接 end_task_trace / _trace_node 安全 no-op（无会话时不抛异常）。
"""

from __future__ import annotations

import pytest


@pytest.fixture
def cleanup_env(monkeypatch):
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    import src.graph.tracing as tracing
    import src.observability.trace as trace_mod

    trace_mod.reset_trace_file_locks()
    # 清掉可能残留的线程局部 session
    if hasattr(tracing._trace_local, "session"):
        tracing._trace_local.session = None
    yield
    trace_mod.reset_trace_file_locks()
    if hasattr(tracing._trace_local, "session"):
        tracing._trace_local.session = None


class TestGraphTracingThreadLocal:
    def test_end_without_start_is_noop(self, cleanup_env) -> None:
        """未 start_task_trace 直接 end_task_trace：安全返回，不抛异常。"""
        import src.graph.tracing as tracing
        from src.graph.tracing import end_task_trace

        end_task_trace(True, token_snapshot={"total_tokens": 1})
        # 仍无会话
        assert getattr(tracing._trace_local, "session", None) is None

    def test_trace_node_without_session_is_noop(self, cleanup_env) -> None:
        """无会话时 _trace_node 安全 no-op。"""
        from src.graph.tracing import _trace_node

        _trace_node("planner", output_summary={"x": 1}, decision="y", duration_ms=1.0, iteration=0)

    def test_start_creates_and_end_clears_session(self, cleanup_env, tmp_path, monkeypatch) -> None:
        """start 挂载 TraceSession 到线程局部，end 写 task_end 后清空。"""
        import src.graph.tracing as tracing

        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        tracing.start_task_trace("t_local", task_meta={"a": 1})
        assert isinstance(getattr(tracing._trace_local, "session", None), object)
        session = tracing._trace_local.session
        assert session.task_id == "t_local"

        tracing.end_task_trace(True, token_snapshot={"total_tokens": 3})
        # end 后线程局部必须清空（防止下一任务串扰）
        assert tracing._trace_local.session is None

        # 且 JSONL 写入了 task_start + task_end 两条
        import json

        lines = [json.loads(l) for l in open(tmp_path / "t_local.trace.jsonl", encoding="utf-8")]
        assert [r["event"] for r in lines] == ["task_start", "task_end"]
        assert lines[1]["token_usage"]["total_tokens"] == 3
