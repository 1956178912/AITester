"""P1 执行感知可观测性升级（TraceSession 结构化决策路径 + 分层缓存统计）单元测试。

覆盖：
- TraceSession.record_node 新增字段（input_summary / token_usage / decision_reason /
  strategy_selected / budget_remaining）按需写入 JSONL（缺省不写）
- _trace_node 透传新字段
- record_node 全默认参数时 record 与历史口径逐字节一致（仅 event/task/node/ts）
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import patch


def _make_session(tmp: str) -> Any:
    from src.observability.trace import TraceSession

    return TraceSession("task_x", trace_directory=tmp)


def test_record_node_all_fields_written() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session = _make_session(tmp)
        session.record_node(
            node="debugger",
            output_summary={"error_category": "assertion"},
            decision="debug",
            duration_ms=12.3,
            iteration=1,
            input_summary={"target_code_len": 500},
            token_usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "llm_calls": 1},
            decision_reason="error_category=assertion, iteration=1 < max → debug",
            strategy_selected="multi_candidate",
            budget_remaining=450,
        )
        # 从 JSONL 文件读取记录
        trace_file = os.path.join(tmp, "task_x.trace.jsonl")
        with open(trace_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        # 找 debugger 节点记录（task_start 是第一条）
        node_records = [r for r in lines if r.get("node") == "debugger"]
        assert len(node_records) == 1
        rec = node_records[0]
        assert rec["output"] == {"error_category": "assertion"}
        assert rec["decision"] == "debug"
        assert rec["duration_ms"] == 12.3
        assert rec["iteration"] == 1
        assert rec["input"] == {"target_code_len": 500}
        assert rec["token_usage"]["total_tokens"] == 150
        assert rec["decision_reason"] == "error_category=assertion, iteration=1 < max → debug"
        assert rec["strategy_selected"] == "multi_candidate"
        assert rec["budget_remaining"] == 450


def test_record_node_default_params_no_new_fields() -> None:
    """全默认参数（仅 node 必填）→ record 不含 P1 新字段（历史口径不变）。"""
    with tempfile.TemporaryDirectory() as tmp:
        session = _make_session(tmp)
        session.record_node(node="planner")
        trace_file = os.path.join(tmp, "task_x.trace.jsonl")
        with open(trace_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        node_records = [r for r in lines if r.get("node") == "planner"]
        assert len(node_records) == 1
        rec = node_records[0]
        # 历史字段
        assert rec["event"] == "node"
        assert rec["task"] == "task_x"
        assert rec["node"] == "planner"
        assert "ts" in rec
        # P1 新字段缺省不写入
        assert "input" not in rec
        assert "token_usage" not in rec
        assert "decision_reason" not in rec
        assert "strategy_selected" not in rec
        assert "budget_remaining" not in rec
        assert "output" not in rec
        assert "decision" not in rec


def test_trace_node_passes_new_fields() -> None:
    """_trace_node 透传 P1 新字段到 TraceSession.record_node。"""
    from src.graph import tracing as tracing_mod

    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"AITESTER_TRACE_DIR": tmp}):
            tracing_mod.start_task_trace("task_y")
            tracing_mod._trace_node(
                node="executor",
                output_summary={"passed": False},
                decision="FAIL",
                duration_ms=5.0,
                iteration=0,
                input_summary={"test_code_len": 200},
                token_usage={"total_tokens": 80, "llm_calls": 2},
                decision_reason="test_failed",
                strategy_selected="single_patch",
                budget_remaining=920,
            )
            tracing_mod.end_task_trace(passed=False)
        # 读 JSONL 验证字段透传
        trace_file = os.path.join(tmp, "task_y.trace.jsonl")
        with open(trace_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        node_records = [r for r in lines if r.get("node") == "executor"]
        assert len(node_records) == 1
        rec = node_records[0]
        assert rec["input"] == {"test_code_len": 200}
        assert rec["token_usage"]["llm_calls"] == 2
        assert rec["decision_reason"] == "test_failed"
        assert rec["strategy_selected"] == "single_patch"
        assert rec["budget_remaining"] == 920


def test_trace_node_no_session_no_op() -> None:
    """_trace_node 在无会话时 no-op（历史行为）。"""
    from src.graph import tracing as tracing_mod

    # 确保无会话（trace 未启用且线程局部 session=None）
    tracing_mod._trace_local.session = None
    tracing_mod._trace_node(
        node="test",
        input_summary={"x": 1},
        token_usage={"y": 2},
        decision_reason="z",
        strategy_selected="w",
        budget_remaining=0,
    )
    # U3（2026-10-05 系统性审查落地）：补断言——调用后仍无会话
    assert tracing_mod._trace_local.session is None
