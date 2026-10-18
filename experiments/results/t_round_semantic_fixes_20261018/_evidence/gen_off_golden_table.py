#!/usr/bin/env python3
"""T4（T 轮 2026-10-18）：A-19 抢占优先级修复的**改动前**黄金行为表生成器。

用途：在修改 `src/graph/workflow.py::_should_debug` **之前**跑一次，把默认关
（COVERAGE_STALL_DETECT_ENABLE=false）路径下 `_should_debug` 的
(decision, state["stop_reason"], _trace_node 调用序列, 日志文案) 冻结为 JSON；
随后修复落地，测试用同一张表逐行比对 → 作为"默认关路径行为零变化"的
**改前证据**（表由改动前实现生成，不是事后自证）。

零 LLM、零网络、零子进程：只调用纯路由函数（_should_debug 不做 IO）。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.graph import workflow as wf  # noqa: E402
from src.graph.state import create_initial_state  # noqa: E402

OUT = Path(__file__).resolve().parent / "off_golden_table_before.json"

# 确定性基线开关（测试侧用同一组值 monkeypatch，保证表与断言同口径）
BASE_ENV = {
    "COVERAGE_STALL_DETECT_ENABLE": "false",
    "COVERAGE_STALL_ROUNDS": "2",
    "COVERAGE_STALL_EPS": "0.5",
    "DETECTION_FIRST_ENABLE": "false",
    "DETECTION_SPECIFICITY_GATE_ENABLE": "false",
    "ROUTE_STRUCTURED_ENABLE": "false",
}

_STALL_TRACE = [
    {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
    {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
    {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
]
_GROW_TRACE = [
    {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
    {"iteration": 1, "passed": False, "coverage": 30.0, "coverage_delta": 30.0},
]
_INVALID_REPAIRS = [{"patch_applied": False}, {"patch_applied": False}]
_KEYWORD_DIAGNOSIS = "测试生成错误：期望的异常类型不匹配（test code 断言错误）"

# 每行：(name, state_overrides, row_env_overrides)
_ROWS = [
    ("plain_debug", {"iteration": 1, "max_iterations": 3}, {}),
    ("test_passed", {"test_passed": True, "iteration": 2, "execution_trace": _STALL_TRACE}, {}),
    ("budget_exceeded", {"budget_exceeded": True, "iteration": 1}, {}),
    ("regression_detected", {"regression_detected": True, "iteration": 1}, {}),
    ("test_defect_regen", {"defect_type": "test_defect", "regeneration_count": 0, "iteration": 1}, {}),
    (
        "test_defect_cap",
        {"defect_type": "test_defect", "regeneration_count": 2, "iteration": 1},
        {},
    ),
    ("repair_invalid", {"iteration": 1, "max_iterations": 3, "repair_history": _INVALID_REPAIRS}, {}),
    ("repair_invalid_at_max", {"iteration": 3, "max_iterations": 3, "repair_history": _INVALID_REPAIRS}, {}),
    (
        "max_iteration_keyword",
        {"iteration": 3, "max_iterations": 3, "diagnosis": _KEYWORD_DIAGNOSIS, "regeneration_count": 0},
        {},
    ),
    ("max_iteration", {"iteration": 3, "max_iterations": 3}, {}),
    (
        "keyword_early",
        {"iteration": 1, "max_iterations": 3, "diagnosis": _KEYWORD_DIAGNOSIS, "regeneration_count": 0},
        {},
    ),
    (
        "keyword_early_regen_capped",
        {"iteration": 1, "max_iterations": 3, "diagnosis": _KEYWORD_DIAGNOSIS, "regeneration_count": 2},
        {},
    ),
    # 停滞 trace 在 OFF 下必须完全不改变历史路由（关键零变化行）
    ("stalled_trace_off_plain", {"iteration": 2, "max_iterations": 3, "execution_trace": _STALL_TRACE}, {}),
    (
        "stalled_trace_off_repair_invalid",
        {"iteration": 2, "max_iterations": 3, "execution_trace": _STALL_TRACE, "repair_history": _INVALID_REPAIRS},
        {},
    ),
    (
        "stalled_trace_off_at_max",
        {"iteration": 3, "max_iterations": 3, "execution_trace": _STALL_TRACE},
        {},
    ),
    (
        "growing_trace_plain",
        {"iteration": 1, "max_iterations": 3, "execution_trace": _GROW_TRACE},
        {},
    ),
    # 检出优先 / 特异性门：显式打开后作为历史分支基线（OFF 口径无关停滞）
    (
        "detection_first_all_green",
        {"test_passed": True, "iteration": 0, "regeneration_count": 0, "execution_trace": _STALL_TRACE},
        {"DETECTION_FIRST_ENABLE": "true"},
    ),
    (
        "specificity_gate_over_red",
        {"iteration": 0, "specificity_gate_verdict": "over_red", "regeneration_count": 0},
        {"DETECTION_SPECIFICITY_GATE_ENABLE": "true"},
    ),
]


class _TraceRecorder:
    def __init__(self) -> None:
        self.calls: list[list] = []

    def __call__(self, *args, **kwargs):
        self.calls.append([list(args), _jsonable(kwargs)])


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _base_state() -> dict:
    return create_initial_state(
        task_uuid="t4_golden_table",
        target_file="/tmp/t4_golden_module.py",
        target_function="f",
        module_name="t4_golden_module",
        target_code="def f():\n    return 1\n",
        max_iterations=3,
    )


def _run_row(name: str, overrides: dict, row_env: dict) -> dict:
    import os

    saved = {k: os.environ.get(k) for k in BASE_ENV}
    for k, v in BASE_ENV.items():
        os.environ[k] = v
    os.environ.update(row_env)
    try:
        state = _base_state()
        state.update(overrides)
        before = dict(state)
        recorder = _TraceRecorder()
        original_trace = wf._trace_node
        wf._trace_node = recorder
        log_records: list[dict] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(
                    {
                        "logger": record.name,
                        "level": record.levelname,
                        "message": record.getMessage(),
                    }
                )

        handler = _Capture()
        target_logger = logging.getLogger("src.graph.workflow")
        old_level = target_logger.level
        target_logger.addHandler(handler)
        target_logger.setLevel(logging.INFO)
        try:
            decision = wf._should_debug(state)
        finally:
            target_logger.removeHandler(handler)
            target_logger.setLevel(old_level)
            wf._trace_node = original_trace
        mutated = sorted(k for k in before if before.get(k) != state.get(k))
        return {
            "name": name,
            "env": row_env,
            "state": _jsonable(overrides),
            "decision": decision,
            "stop_reason": state.get("stop_reason"),
            "mutated_keys": mutated,
            "trace_calls": recorder.calls,
            "logs": [rec for rec in log_records if rec["logger"] == "src.graph.workflow"],
        }
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    rows = [_run_row(*row) for row in _ROWS]
    payload = {
        "generated_from": "src/graph/workflow.py::_should_debug（改动前实现）",
        "note": "默认关（COVERAGE_STALL_DETECT_ENABLE=false）路径黄金行为表；T 轮修复后测试逐行比对",
        "base_env": BASE_ENV,
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
