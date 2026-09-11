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
