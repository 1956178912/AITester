"""DY 轮锁：追踪会话构造/收尾的失败态与耗时字段。

两个面同属「宣称与现实一致」：
- ``TraceSession.__init__`` 的 docstring 承诺「目录创建失败降级为 no-op（不阻断
  主流程）」，实际 ``os.makedirs`` 未设防——AITESTER_TRACE_DIR 指向普通文件之下时
  构造抛 NotADirectoryError，CLI 把每个任务改写成「崩溃」；
- 纯内存模式（默认）的 ``task_end`` 缺 ``duration_s``，而文件追踪模式有——诊断
  快照的耗时字段不该取决于是否开文件追踪。
"""

from __future__ import annotations

import json
import logging

import pytest

from src.graph import tracing
from src.observability import trace as trace_mod
from src.observability.trace import (
    TraceSession,
    dump_recent_to,
    reset_memory_buffer,
    reset_trace_file_locks,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.delenv("AITESTER_TRACE_DIR", raising=False)
    monkeypatch.delenv("TRACE_MEMORY_BUFFER_ENABLE", raising=False)
    reset_memory_buffer()
    reset_trace_file_locks()
    assert trace_mod._memory_buffer_enabled(), "本组锁要求内存缓冲启用（默认 true）"
    yield
    reset_memory_buffer()
    reset_trace_file_locks()
    tracing._trace_local.session = None


def _uncreatable_dir(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("regular file, not a directory", encoding="utf-8")
    return blocker / "trace"


class TestUncreatableTraceDir:
    def test_constructor_degrades_to_memory_only(self, tmp_path, caplog):
        target = _uncreatable_dir(tmp_path)
        with caplog.at_level(logging.WARNING):
            session = TraceSession("dy_task", trace_directory=str(target))
        assert session._file_path is None, "目录不可建时不得留下文件路径"
        assert session.records[0]["event"] == "task_start", "降级后仍须累积内存快照"
        assert "降级" in caplog.text, "降级必须留 warning，不得静默"

    def test_end_event_keeps_result_and_duration(self, tmp_path):
        session = TraceSession("dy_task", trace_directory=str(_uncreatable_dir(tmp_path)))
        session.record_task_end(True, token_usage={"total_tokens": 7})
        end = session.records[-1]
        assert end["event"] == "task_end"
        assert end["passed"] is True
        assert end["token_usage"] == {"total_tokens": 7}
        assert isinstance(end["duration_s"], float), "降级路径的 task_end 也要带耗时"

    def test_start_task_trace_survives_and_dump_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AITESTER_TRACE_DIR", str(_uncreatable_dir(tmp_path)))
        tracing.start_task_trace("dy_mem", task_meta={"file": "x.py"})
        assert tracing._trace_local.session is not None, "构造失败不得丢弃会话"
        tracing.end_task_trace(False)
        assert tracing._trace_local.session is None

        dump_path = dump_recent_to(str(tmp_path / "dump"))
        assert dump_path is not None, "降级后 --dump-trace-on-failure 仍必须可用"
        with open(dump_path, encoding="utf-8") as f:
            tasks = {json.loads(line)["task"] for line in f}
        assert tasks == {"dy_mem"}


class TestMemoryOnlyDuration:
    def test_memory_only_session_records_duration(self):
        session = TraceSession("dy_plain")
        assert session._file_path is None
        session.record_task_end(True)
        end = session.records[-1]
        assert isinstance(end["duration_s"], float), "默认内存模式的 task_end 也要带耗时"
