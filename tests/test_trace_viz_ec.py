"""EC（2026-10-27）：trace 可视化 / 回放的读侧词汇必须与写侧一致。

写侧（TraceSession）只写三类事件：task_start / node / task_end；任务结果
字段是 passed（True / False / None 三态），节点 token 快照是 token_usage
（total_tokens）。读侧 trace_viz 此前按另一套词汇读（node_end /
test_passed / token_delta），实测 100 份真实轨迹 100% 渲染成
「无节点记录 + FAIL」。以下用例全部用写侧真实产出构造轨迹。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.observability.trace import TraceSession
from src.utils.trace_viz import replay_trace, trace_to_html

# 徽章断言只认徽章的完整标记——`<code>PASS</code>` 决策 chip 也含 >PASS< 子串。
_PASS_BADGE = '<span class="badge pass">PASS</span>'
_FAIL_BADGE = '<span class="badge fail">FAIL</span>'
_CRASH_BADGE = '<span class="badge fail">CRASH</span>'


def _render(tmp_path: Path, path: str) -> tuple[int, str]:
    out = tmp_path / "out.html"
    n = trace_to_html([path], str(out))
    return n, out.read_text(encoding="utf-8")


def _green_session(tmp_path: Path) -> TraceSession:
    session = TraceSession("green", str(tmp_path))
    session.record_node("planner", decision="plan_complete", duration_ms=12.5)
    session.record_node("executor", decision="PASS", duration_ms=800.0)
    session.record_task_end(passed=True)
    assert session._file_path is not None
    return session


class TestWriterVocabularyRendering:
    def test_green_writer_trace_renders_pass_badge(self, tmp_path: Path):
        session = _green_session(tmp_path)
        n, html = _render(tmp_path, session._file_path)
        assert n == 1
        assert _PASS_BADGE in html
        assert _FAIL_BADGE not in html
        assert _CRASH_BADGE not in html

    def test_writer_node_events_render_as_timeline_chips(self, tmp_path: Path):
        session = _green_session(tmp_path)
        _, html = _render(tmp_path, session._file_path)
        assert "无节点记录" not in html
        assert "<b>planner</b>" in html
        assert "<b>executor</b>" in html
        assert "800.0ms" in html
        assert "节点数: 2" in html

    def test_summary_node_total_counts_node_events_only(self, tmp_path: Path):
        session = _green_session(tmp_path)
        _, html = _render(tmp_path, session._file_path)
        assert "<b>节点记录</b>: 2" in html

    def test_node_token_usage_renders_total_tokens(self, tmp_path: Path):
        session = TraceSession("tok", str(tmp_path))
        session.record_node(
            "planner",
            token_usage={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
        )
        session.record_task_end(passed=True)
        _, html = _render(tmp_path, session._file_path)
        assert "140 tok" in html


class TestVerdictVocabulary:
    def test_failed_writer_trace_renders_fail_badge(self, tmp_path: Path):
        session = TraceSession("failed", str(tmp_path))
        session.record_node("executor", decision="FAIL")
        session.record_task_end(passed=False)
        _, html = _render(tmp_path, session._file_path)
        assert _FAIL_BADGE in html
        assert _PASS_BADGE not in html

    def test_crashed_writer_trace_renders_crash_badge(self, tmp_path: Path):
        """写侧 passed=None 是「任务中途崩溃」，不得折叠成 PASS/FAIL。"""
        session = TraceSession("crashed", str(tmp_path))
        session.record_node("executor", decision="PASS")
        session.record_task_end(passed=None)
        _, html = _render(tmp_path, session._file_path)
        assert _CRASH_BADGE in html
        assert _PASS_BADGE not in html
        assert _FAIL_BADGE not in html

    def test_trace_without_task_end_is_crash_not_fail(self, tmp_path: Path):
        session = TraceSession("truncated", str(tmp_path))
        session.record_node("planner", decision="plan_complete")
        _, html = _render(tmp_path, session._file_path)
        assert _CRASH_BADGE in html
        assert _FAIL_BADGE not in html

    def test_foreign_node_end_event_is_not_a_node_chip(self, tmp_path: Path):
        """读侧只认写侧的 node 事件——外来词汇不得冒充节点记录。"""
        path = tmp_path / "legacy.trace.jsonl"
        path.write_text(
            json.dumps({"event": "node_end", "node": "planner", "ts": 1.0})
            + "\n"
            + json.dumps({"event": "task_end", "passed": True, "ts": 2.0})
            + "\n",
            encoding="utf-8",
        )
        _, html = _render(tmp_path, str(path))
        assert "无节点记录" in html
        assert "节点数: 0" in html
        assert _PASS_BADGE in html


class TestReplayVocabulary:
    def test_replay_state_tracks_writer_passed_field(self, tmp_path: Path):
        session = TraceSession("replay", str(tmp_path))
        session.record_node("executor", decision="FAIL", iteration=2)
        session.record_task_end(passed=False)
        steps = replay_trace(str(session._file_path))
        assert len(steps) == 3
        assert steps[-1]["state_snapshot"]["test_passed"] is False
        assert steps[-1]["state_snapshot"]["iteration"] == 2


class TestRenderContracts:
    def test_missing_file_still_renders_empty_html(self, tmp_path: Path):
        out = tmp_path / "out.html"
        assert trace_to_html([str(tmp_path / "missing.jsonl")], str(out)) == 0
        assert out.exists()

    def test_corrupt_lines_are_skipped_and_verdict_still_rendered(self, tmp_path: Path):
        path = tmp_path / "bad.trace.jsonl"
        path.write_text(
            json.dumps({"event": "task_start", "ts": 1.0})
            + "\n"
            + "corrupt {{{{ not json\n"
            + json.dumps({"event": "task_end", "passed": False, "ts": 2.0})
            + "\n",
            encoding="utf-8",
        )
        n, html = _render(tmp_path, str(path))
        assert n == 1
        assert _FAIL_BADGE in html

    def test_multiple_writer_traces_are_counted(self, tmp_path: Path):
        a = _green_session(tmp_path)
        b = TraceSession("second", str(tmp_path))
        b.record_task_end(passed=False)
        out = tmp_path / "out.html"
        assert trace_to_html([a._file_path, b._file_path], str(out)) == 2
        html = out.read_text(encoding="utf-8")
        assert _PASS_BADGE in html
        assert _FAIL_BADGE in html
