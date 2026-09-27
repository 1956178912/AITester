"""
src.observability.trace 单元测试（4.1 结构化追踪层）。

覆盖：
- 未启用（AITESTER_TRACE_DIR 未设）时全部 no-op（不写盘、无副作用）；
- 启用时 JSONL 追加写入、事件序列（task_start/node/task_end）；
- 长文本摘要截断头尾各半；
- 敏感信息脱敏（凭证不落盘）；
- workflow 接线（start_task_trace / end_task_trace / _trace_node）。
"""

from __future__ import annotations

import json

import pytest

from src.observability import trace as trace_mod
from src.observability.trace import (
    TraceSession,
    dump_recent_to,
    memory_buffer_snapshot,
    reset_memory_buffer,
    reset_trace_file_locks,
    trace_dir,
    trace_enabled,
)


@pytest.fixture
def cleanup_env(monkeypatch):
    """隔离 AITESTER_TRACE_DIR 环境变量并清理文件锁注册表。"""
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    reset_trace_file_locks()
    yield
    reset_trace_file_locks()


def _load_jsonl(path):
    """读取 JSONL 文件为记录列表（每行一个 JSON 对象）。"""
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def _load_jsonl_content(path):
    """读取 JSONL 文件的原始文本（用于脱敏断言）。"""
    return open(path, encoding="utf-8").read()


class TestTraceSwitch:
    """追踪开关行为。"""

    def test_disabled_by_default(self, cleanup_env):
        assert trace_dir() is None
        assert trace_enabled() is False
        assert TraceSession.enabled() is False

    def test_enabled_when_env_set(self, cleanup_env, monkeypatch):
        monkeypatch.setenv("AITESTER_TRACE_DIR", "/tmp/x")
        assert trace_dir() == "/tmp/x"
        assert trace_enabled() is True

    def test_empty_env_is_disabled(self, cleanup_env, monkeypatch):
        monkeypatch.setenv("AITESTER_TRACE_DIR", "   ")
        assert trace_enabled() is False


class TestNoOpWhenDisabled:
    """未启用时所有记录方法 no-op（零 I/O）。"""

    def test_no_write_when_disabled(self, cleanup_env, tmp_path):
        TraceSession("task_a", trace_directory=str(tmp_path))
        # 显式给了目录但环境变量未设：构造器以目录为准 → 仍应启用写盘
        # （验证构造器目录参数优先于环境变量）
        files = list(tmp_path.glob("*.jsonl"))
        assert files, "显式传目录时即使环境变量未设也应启用"

    def test_noop_session_without_dir(self, cleanup_env):
        # 环境变量未设、未传目录 → 禁用，record_* 全 no-op
        session = TraceSession("task_b")
        assert not session._enabled
        # 不抛异常即可（no-op 路径）
        session.record_node("planner", decision="x")
        session.record_task_end(True, token_usage={"total_tokens": 1})

    def test_session_with_dir_writes(self, cleanup_env, tmp_path):
        session = TraceSession("task_c", trace_directory=str(tmp_path))
        assert session._enabled
        session.record_node("planner", decision="plan_complete")
        session.record_task_end(True, token_usage={"total_tokens": 42})
        lines = _load_jsonl(tmp_path / "task_c.trace.jsonl")
        assert [r["event"] for r in lines] == ["task_start", "node", "task_end"]
        assert lines[2]["token_usage"]["total_tokens"] == 42


class TestSummarize:
    """长文本摘要截断。"""

    def test_short_unchanged(self):
        assert trace_mod._summarize("hello") == "hello"

    def test_long_truncated_head_tail(self):
        text = "A" * 3000 + "B" * 3000
        result = trace_mod._summarize(text)
        assert isinstance(result, str)
        assert "truncated" in result
        assert result.startswith("AAAA")
        assert result.endswith("BBBB")
        # 截断后长度远小于原文
        assert len(result) < 3000

    def test_non_str_passthrough(self):
        assert trace_mod._summarize({"a": 1}) == {"a": 1}
        assert trace_mod._summarize(123) == 123


class TestRedaction:
    """写入文本经脱敏（凭证不落盘）。"""

    def test_credential_redacted(self, cleanup_env, tmp_path):
        session = TraceSession("task_d", trace_directory=str(tmp_path))
        # 模拟 token_usage 快照里意外带凭证（不应发生，但脱敏兜底）
        session.record_task_end(
            True,
            token_usage={"total_tokens": 1, "by_model": {"sk-ws-ABCDEFGH1234567890xy": 1}},
        )
        content = _load_jsonl_content(tmp_path / "task_d.trace.jsonl")
        assert "sk-ws-ABCDEFGH1234567890xy" not in content
        assert "<REDACTED_API_KEY>" in content


class TestWorkflowWiring:
    """workflow 的 trace 接线（start/end/_trace_node）。"""

    def test_noop_when_disabled(self, cleanup_env, monkeypatch):
        import src.graph.workflow as wf

        wf.start_task_trace("t")
        wf._trace_node("planner", decision="x")
        wf.end_task_trace(True)
        # 未启用：线程局部无 session，全部 no-op，无副作用
        assert not getattr(wf._trace_local, "session", None)

    def test_events_when_enabled(self, cleanup_env, monkeypatch, tmp_path):
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        import src.graph.workflow as wf

        wf.start_task_trace("task_e", task_meta={"baseline": "aitester"})
        wf._trace_node("executor", output_summary={"passed": False}, decision="FAIL", iteration=1)
        wf.end_task_trace(False, token_snapshot={"total_tokens": 7})
        lines = _load_jsonl(tmp_path / "task_e.trace.jsonl")
        events = [r["event"] for r in lines]
        assert events == ["task_start", "node", "task_end"]
        assert lines[1]["decision"] == "FAIL"
        assert lines[1]["iteration"] == 1
        assert lines[2]["token_usage"]["total_tokens"] == 7


class TestMemoryBuffer:
    """内存快照缓冲（默认启用、不落盘；--dump-trace-on-failure 失败诊断出口）。"""

    def test_snapshot_ring_capacity(self, monkeypatch):
        """环形缓冲默认容量 64，溢出后最早任务被覆盖。"""
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        reset_memory_buffer()
        for i in range(trace_mod._MEMORY_BUFFER_CAPACITY + 5):
            memory_buffer_snapshot(f"task_{i}", [{"event": "node", "task": f"task_{i}"}])
        with trace_mod._memory_ring_lock:
            ring = list(trace_mod._memory_ring)
        assert len(ring) == trace_mod._MEMORY_BUFFER_CAPACITY
        # 最早的任务（task_0..task_4）被覆盖
        assert ring[0]["task"] == "task_5"
        assert ring[-1]["task"] == f"task_{trace_mod._MEMORY_BUFFER_CAPACITY + 4}"

    def test_snapshot_disabled_by_env(self, monkeypatch):
        """TRACE_MEMORY_BUFFER_ENABLE=false 时缓冲不累积（零内存开销）。"""
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "false")
        reset_memory_buffer()
        memory_buffer_snapshot("task_x", [{"event": "node"}])
        with trace_mod._memory_ring_lock:
            assert trace_mod._memory_ring == []

    def test_dump_recent_to_jsonl(self, monkeypatch, tmp_path):
        """dump_recent_to 把最近任务快照写成 JSONL（显式调用才落盘）。"""
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        reset_memory_buffer()
        memory_buffer_snapshot("task_1", [{"event": "node", "node": "planner", "task": "task_1"}])
        memory_buffer_snapshot("task_2", [{"event": "node", "node": "executor", "task": "task_2"}])
        path = dump_recent_to(str(tmp_path))
        assert path is not None
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        # 各任务记录 + 任务边界 marker
        events = [rec["event"] for rec in lines]
        assert "node" in events
        assert "snapshot_task" in events
        assert any(rec.get("task") == "task_1" for rec in lines)
        assert any(rec.get("task") == "task_2" for rec in lines)

    def test_dump_empty_returns_none(self, monkeypatch, tmp_path):
        """无快照可写时返回 None（不落盘、不报错）。"""
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        reset_memory_buffer()
        assert dump_recent_to(str(tmp_path)) is None

    def test_end_task_trace_feeds_buffer(self, cleanup_env, monkeypatch, tmp_path):
        """文件追踪启用时 end_task_trace 把 session.records 快照入缓冲。"""
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(tmp_path))
        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        reset_memory_buffer()
        import src.graph.workflow as wf

        wf.start_task_trace("task_f")
        wf._trace_node("planner", decision="plan_complete")
        wf.end_task_trace(True, token_snapshot={"total_tokens": 1})
        with trace_mod._memory_ring_lock:
            ring = list(trace_mod._memory_ring)
        assert len(ring) == 1
        assert ring[0]["task"] == "task_f"
        # 快照包含节点事件与 task_end 事件（内存视角累积）
        events = [r["event"] for r in ring[0]["records"]]
        assert "node" in events
        assert "task_end" in events
