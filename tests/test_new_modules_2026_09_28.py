"""2.2 控制流图（CFG）静态分析 + 1.4 事件总线 + 6.2 trace 可视化的测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

# ── 2.2 CFG 分析 ──────────────────────────────────────────────────────────────
from src.tools.control_flow import (
    analyze_control_flow,
    build_cfg_prompt_section,
    cfg_analysis_enabled,
)


def _sample_code() -> str:
    return """
def process(items, strict=False):
    total = 0
    for i, x in enumerate(items):
        if x is None:
            continue
        if strict and x < 0:
            raise ValueError("negative")
        total += x
    return total
"""


class TestControlFlowAnalysis:
    def test_basic_branch_detection(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        assert cfg["func_name"] == "process"
        assert len(cfg["branch_conditions"]) == 2
        assert cfg["branch_conditions"][0]["expr"] == "x is None"
        assert cfg["branch_conditions"][1]["expr"] == "strict and x < 0"

    def test_loop_detection(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        assert len(cfg["loop_boundaries"]) == 1
        assert cfg["loop_boundaries"][0]["kind"] == "for"
        assert "enumerate" in cfg["loop_boundaries"][0]["iterator"]

    def test_exception_detection(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        assert len(cfg["exception_paths"]) == 1
        assert cfg["exception_paths"][0]["kind"] == "raise"
        assert "ValueError" in cfg["exception_paths"][0]["types"][0]

    def test_return_points(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        assert len(cfg["return_points"]) == 1
        assert cfg["return_points"][0]["value"] == "total"

    def test_cyclomatic_estimate(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        # 1 (base) + 2 branches + 1 loop = 4
        assert cfg["cyclomatic_estimate"] == 4

    def test_while_loop(self):
        code = """
def count(n):
    i = 0
    while i < n:
        i += 1
    return i
"""
        cfg = analyze_control_flow(code, "count")
        assert len(cfg["loop_boundaries"]) == 1
        assert cfg["loop_boundaries"][0]["kind"] == "while"

    def test_try_except(self):
        code = """
def safe_div(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return 0
"""
        cfg = analyze_control_flow(code, "safe_div")
        kinds = {e["kind"] for e in cfg["exception_paths"]}
        assert "except" in kinds
        types_found = [t for e in cfg["exception_paths"] if e["kind"] == "except" for t in e["types"]]
        assert "ZeroDivisionError" in types_found

    def test_ternary_branch(self):
        code = """
def abs_val(x):
    return x if x >= 0 else -x
"""
        cfg = analyze_control_flow(code, "abs_val")
        # 三元表达式算一个分支
        assert len(cfg["branch_conditions"]) == 1
        assert "ternary" in cfg["branch_conditions"][0]["expr"]

    def test_no_function_returns_empty(self):
        code = "x = 1\n"
        cfg = analyze_control_flow(code, "nonexistent")
        assert cfg["func_name"] == "nonexistent"
        assert cfg["branch_conditions"] == []
        assert cfg["cyclomatic_estimate"] == 1

    def test_unparseable_code(self):
        cfg = analyze_control_flow("def broken(:\n", "x")
        assert cfg["cyclomatic_estimate"] == 1
        assert cfg["branch_conditions"] == []

    def test_none_func_name_takes_first(self):
        code = """
def first():
    pass

def second():
    if True:
        pass
"""
        cfg = analyze_control_flow(code, None)
        assert cfg["func_name"] == "first"

    def test_path_hint_populated(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        assert "控制流摘要" in cfg["path_hint"]
        assert "分支" in cfg["path_hint"]

    def test_path_hint_simple_func(self):
        code = """
def simple():
    return 42
"""
        cfg = analyze_control_flow(code, "simple")
        # 有 1 个出口 → 摘要含 "出口 1 个"
        assert "出口" in cfg["path_hint"]


class TestBuildCfgPromptSection:
    def test_enabled_returns_section(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        with patch("src.tools.control_flow.cfg_analysis_enabled", return_value=True):
            section = build_cfg_prompt_section(cfg)
        assert "控制流分析" in section
        assert "process" in section

    def test_disabled_returns_empty(self):
        cfg = analyze_control_flow(_sample_code(), "process")
        with patch("src.tools.control_flow.cfg_analysis_enabled", return_value=False):
            assert build_cfg_prompt_section(cfg) == ""

    def test_none_cfg_returns_empty(self):
        with patch("src.tools.control_flow.cfg_analysis_enabled", return_value=True):
            assert build_cfg_prompt_section(None) == ""

    def test_env_switch(self):
        with patch.dict(os.environ, {"CFG_ANALYSIS_ENABLE": "false"}):
            assert not cfg_analysis_enabled()
        with patch.dict(os.environ, {"CFG_ANALYSIS_ENABLE": "true"}):
            assert cfg_analysis_enabled()
        # 默认 true
        env = {k: v for k, v in os.environ.items() if k != "CFG_ANALYSIS_ENABLE"}
        with patch.dict(env, clear=True):
            assert cfg_analysis_enabled()


# ── 1.4 事件总线 ──────────────────────────────────────────────────────────────

from src.graph.event_bus import (  # noqa: E402
    DebuggerDiagnosed,
    EventBus,
    PatchApplied,
    PlanGenerated,
    TestsExecuted,
    WorkflowCompleted,
    get_event_bus,
)


class TestEventBus:
    def test_publish_subscribe_basic(self):
        bus = EventBus()
        received: list = []
        bus.subscribe("plan_generated", lambda e: received.append(e))
        ev = PlanGenerated(task_uuid="t1", function_name="add", test_case_count=5)
        bus.publish(ev)
        assert len(received) == 1
        assert received[0].EVENT_NAME == "plan_generated"
        assert received[0].payload["function_name"] == "add"

    def test_publish_multiple_events(self):
        bus = EventBus()
        counts = {"plan": 0, "exec": 0, "debug": 0}

        def sub_plan(e):
            counts["plan"] += 1

        def sub_exec(e):
            counts["exec"] += 1

        def sub_debug(e):
            counts["debug"] += 1

        bus.subscribe("plan_generated", sub_plan)
        bus.subscribe("tests_executed", sub_exec)
        bus.subscribe("debugger_diagnosed", sub_debug)
        bus.publish(PlanGenerated(task_uuid="t1"))
        bus.publish(TestsExecuted(task_uuid="t1", passed=True))
        bus.publish(DebuggerDiagnosed(task_uuid="t1", error_category="runtime"))
        assert counts == {"plan": 1, "exec": 1, "debug": 1}

    def test_unsubscribe_isolation(self):
        bus = EventBus()
        received: list = []
        bus.subscribe("plan_generated", lambda e: received.append(e))
        bus.publish(PlanGenerated())
        # 发布未订阅的事件类型
        bus.publish(TestsExecuted())
        assert len(received) == 1  # 只有 plan 被订阅

    def test_subscriber_exception_isolation(self):
        bus = EventBus()
        received: list = []

        def bad_subscriber(e):
            raise ValueError("boom")

        def good_subscriber(e):
            received.append(e)

        bus.subscribe("plan_generated", bad_subscriber)
        bus.subscribe("plan_generated", good_subscriber)
        bus.publish(PlanGenerated())
        # 坏订阅者异常被隔离，好订阅者仍收到
        assert len(received) == 1

    def test_stats(self):
        bus = EventBus()
        bus.subscribe("plan_generated", lambda e: None)
        bus.publish(PlanGenerated())
        bus.publish(PlanGenerated())
        s = bus.stats()
        assert s["counts"]["plan_generated"] == 2
        assert "plan_generated" in s["subscribed"]

    def test_clear(self):
        bus = EventBus()
        bus.subscribe("plan_generated", lambda e: None)
        bus.publish(PlanGenerated())
        bus.clear()
        assert bus.stats() == {"counts": {}, "subscribed": []}

    def test_event_summary_json_serializable(self):
        ev = PatchApplied(task_uuid="t1", applied=True, new_code_chars=100, postprocess_labels=["imports_repaired"])
        s = ev.summary()
        json.dumps(s)  # 不抛异常
        assert s["event"] == "patch_applied"
        assert s["payload"]["postprocess_labels"] == ["imports_repaired"]

    def test_all_event_types(self):
        """五种事件类型都能构造 + 发布 + 订阅。"""
        bus = EventBus()
        events = [
            PlanGenerated(task_uuid="t"),
            TestsExecuted(task_uuid="t", passed=True, coverage=90.0),
            PatchApplied(task_uuid="t", applied=True, new_code_chars=50),
            DebuggerDiagnosed(task_uuid="t", error_category="assertion"),
            WorkflowCompleted(task_uuid="t", test_passed=True, iteration=3),
        ]
        for ev in events:
            name = ev.EVENT_NAME
            bus.subscribe(name, lambda e: None)
            bus.publish(ev)
        s = bus.stats()
        assert len(s["counts"]) == 5

    def test_process_singleton(self):
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_event_bus_disabled_env(self):
        import src.graph.event_bus as eb_module

        bus = EventBus()
        received: list = []
        bus.subscribe("plan_generated", lambda e: received.append(e))
        with patch.dict(os.environ, {"EVENT_BUS_ENABLE": "false"}):
            eb_module._bus.publish(PlanGenerated())
        # 开关关闭时 publish 为 no-op
        assert len(received) == 0

    def test_event_bus_enabled_default(self):
        import src.graph.event_bus as eb_module

        received: list = []
        eb_module._bus.subscribe("plan_generated", lambda e: received.append(e))
        eb_module._bus.publish(PlanGenerated())
        # 默认 true，发布正常
        assert len(received) == 1
        eb_module._bus.clear()


# ── 6.2 trace 可视化 + 回放 ───────────────────────────────────────────────────

from src.utils.trace_viz import replay_trace, trace_to_html  # noqa: E402


class TestTraceToHTML:
    def test_render_single_trace(self, tmp_path: Path):
        trace_file = tmp_path / "task1.trace.jsonl"
        recs = [
            {"event": "task_start", "task_uuid": "task1", "ts": "2026-09-28T10:00:00Z"},
            {
                "event": "node_end",
                "node": "planner",
                "decision": "plan_complete",
                "duration_ms": 1200,
                "token_delta": 500,
                "ts": "2026-09-28T10:00:01Z",
            },
            {
                "event": "node_end",
                "node": "executor",
                "decision": "PASS",
                "duration_ms": 800,
                "ts": "2026-09-28T10:00:05Z",
            },
            {"event": "task_end", "test_passed": True, "ts": "2026-09-28T10:00:05Z"},
        ]
        with open(trace_file, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

        out = tmp_path / "out.html"
        n = trace_to_html([str(trace_file)], str(out), title="Test")
        assert n == 1
        content = out.read_text()
        assert "Task Timeline" not in content  # 自定义标题
        assert "Test" in content
        assert "planner" in content
        assert "PASS" in content
        assert "task_start" in content

    def test_render_missing_file(self, tmp_path: Path):
        out = tmp_path / "out.html"
        n = trace_to_html([str(tmp_path / "nonexistent.jsonl")], str(out))
        assert n == 0
        # 仍写空 HTML
        assert out.exists()

    def test_render_corrupt_jsonl(self, tmp_path: Path):
        trace_file = tmp_path / "bad.trace.jsonl"
        with open(trace_file, "w") as f:
            f.write('{"event": "task_start", "ts": "2026-09-28T10:00:00Z"}\n')
            f.write("corrupt {{{{ not json\n")
            f.write('{"event": "task_end", "test_passed": false, "ts": "2026-09-28T10:00:05Z"}\n')
        out = tmp_path / "out.html"
        n = trace_to_html([str(trace_file)], str(out))
        assert n == 1  # 2 条有效记录（损坏行跳过）
        content = out.read_text()
        assert "FAIL" in content  # test_passed=false

    def test_render_multiple_traces(self, tmp_path: Path):
        traces = []
        for i in range(2):
            tf = tmp_path / f"t{i}.trace.jsonl"
            with open(tf, "w") as f:
                f.write(json.dumps({"event": "task_end", "test_passed": i == 0}) + "\n")
            traces.append(str(tf))
        out = tmp_path / "out.html"
        n = trace_to_html(traces, str(out))
        assert n == 2
        content = out.read_text()
        assert content.count("task_end") >= 2


class TestReplayTrace:
    def test_replay_basic(self, tmp_path: Path):
        trace_file = tmp_path / "task1.trace.jsonl"
        recs = [
            {"event": "task_start", "task_uuid": "t1", "ts": "2026-09-28T10:00:00Z"},
            {
                "event": "node_end",
                "node": "executor",
                "test_passed": False,
                "iteration": 1,
                "ts": "2026-09-28T10:00:01Z",
            },
            {"event": "task_end", "test_passed": True, "iteration": 2, "ts": "2026-09-28T10:00:05Z"},
        ]
        with open(trace_file, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

        steps = replay_trace(str(trace_file))
        assert len(steps) == 3
        assert steps[0]["event"] == "task_start"
        assert steps[1]["state_snapshot"]["test_passed"] is False
        assert steps[2]["state_snapshot"]["test_passed"] is True
        assert steps[2]["state_snapshot"]["iteration"] == 2

    def test_replay_missing_file(self):
        assert replay_trace("/nonexistent/path.jsonl") == []

    def test_replay_state_factory(self, tmp_path: Path):
        trace_file = tmp_path / "t.trace.jsonl"
        with open(trace_file, "w") as f:
            f.write(json.dumps({"event": "node_end", "test_passed": True}) + "\n")
        steps = replay_trace(str(trace_file), state_factory=lambda: {"initial": True})
        assert steps[0]["state_snapshot"]["initial"] is True
        assert steps[0]["state_snapshot"]["test_passed"] is True

    def test_replay_corrupt_file(self, tmp_path: Path):
        trace_file = tmp_path / "bad.trace.jsonl"
        trace_file.write_text("not json at all\n")
        assert replay_trace(str(trace_file)) == []
