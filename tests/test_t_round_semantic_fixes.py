"""T 轮（2026-10-18）语义修复回归：A-19 抢占优先级 + 回滚 verdict 结果行 schema。

覆盖任务：
1. **A-19 抢占优先级修复**（承接 S-2 登记缺陷）：生产默认协议
   （PATCH_EVIDENCE_GATE_ENABLE=true）下 repair-invalid 与停滞窗口同迭代收敛
   时，COVERAGE_STALL_DETECT_ENABLE=true 的停滞判定优先于 repair-invalid skip
   生效（分支归属/日志/打点如实为"停滞"）；默认关路径逐位零变化。
   零变化证据 = **改动前**由 `_should_debug` 生成并冻结的黄金行为表
   （experiments/results/t_round_semantic_fixes_20261018/_evidence/
   off_golden_table_before.json，18 行：decision / stop_reason / 变更键集合 /
   _trace_node 调用序列 / 日志文案），改动后逐行比对一致。
2. **回滚 verdict 结果行 schema**（O 轮登记）：`patch_rollback_verdict` /
   `patch_rolled_back` 进结果行（成功分支从 state 投影、失败分支
   None/False 占位），纯观测不参与路由；成功/失败分支键集合同构 + JSON 落盘。

全部用例零 LLM、零网络、零真实子进程（纯路由函数 / 结果行组装）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

import experiments.run_benchmark as rb
from experiments.run_benchmark import _build_task_result
from src.datasets.dataset_loader import BenchmarkTask
from src.graph import workflow as wf
from src.graph.state import create_initial_state

# ── 确定性基线开关（与改动前黄金表生成脚本同口径，防档位预设漂移）──────────
_BASE_ENV = {
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
_VALID_REPAIRS = [{"patch_applied": True}, {"patch_applied": True}]
_KEYWORD_DIAGNOSIS = "测试生成错误：期望的异常类型不匹配（test code 断言错误）"
_STALL_PREEMPT_LOG = "P2-4 覆盖率停滞（同迭代优先于 repair-invalid"
_STALL_TAIL_LOG = "P2-4 覆盖率停滞（连续"
_REPAIR_INVALID_LOG = "连续多次修复无效，跳过 Debugger"


def _base_state(**overrides: Any) -> dict[str, Any]:
    state = create_initial_state(
        task_uuid="t4_semantic_fixes",
        target_file="/tmp/t4_golden_module.py",
        target_function="f",
        module_name="t4_golden_module",
        target_code="def f():\n    return 1\n",
        max_iterations=3,
    )
    state.update(overrides)
    return state


def _jsonable(value: Any) -> Any:
    """与黄金表生成器同口径的 JSON 化（dict/list/标量 → 原生类型）。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


class _TraceRecorder:
    def __init__(self) -> None:
        self.calls: list[list] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append([list(args), _jsonable(kwargs)])


@pytest.fixture()
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _BASE_ENV.items():
        monkeypatch.setenv(name, value)


# ═══ 1. 默认关（OFF）零行为：改动前黄金表逐行比对 ═══════════════════════════
_OFF_GOLDEN_TABLE: list[dict[str, Any]] = [
    {
        "name": "plain_debug",
        "env": {},
        "state": {"iteration": 1, "max_iterations": 3},
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 1}}]],
        "logs": [],
    },
    {
        "name": "test_passed",
        "env": {},
        "state": {
            "test_passed": True,
            "iteration": 2,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
                {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            ],
        },
        "decision": "done",
        "stop_reason": "test_passed",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [[["_should_debug"], {"decision": "done", "output_summary": {"reason": "test_passed"}}]],
        "logs": [],
    },
    {
        "name": "budget_exceeded",
        "env": {},
        "state": {"budget_exceeded": True, "iteration": 1},
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 1}}]],
        "logs": [],
    },
    {
        "name": "regression_detected",
        "env": {},
        "state": {"regression_detected": True, "iteration": 1},
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 1}}]],
        "logs": [],
    },
    {
        "name": "test_defect_regen",
        "env": {},
        "state": {"defect_type": "test_defect", "regeneration_count": 0, "iteration": 1},
        "decision": "regenerate",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [
            [["_should_debug"], {"decision": "regenerate", "output_summary": {"reason": "review_test_defect"}}]
        ],
        "logs": [
            {
                "logger": "src.graph.workflow",
                "level": "INFO",
                "message": "双向诊断（3.1）：测试缺陷，路由回 generator 重新生成测试",
            }
        ],
    },
    {
        "name": "test_defect_cap",
        "env": {},
        "state": {"defect_type": "test_defect", "regeneration_count": 2, "iteration": 1},
        "decision": "done",
        "stop_reason": "test_defect_regeneration_cap",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [
            [
                ["_should_debug"],
                {
                    "decision": "done",
                    "output_summary": {"reason": "test_defect_regeneration_cap", "regeneration_count": 2},
                },
            ]
        ],
        "logs": [
            {"logger": "src.graph.workflow", "level": "INFO", "message": "双向诊断（3.1）：已达重新生成上限，结束流程"}
        ],
    },
    {
        "name": "repair_invalid",
        "env": {},
        "state": {
            "iteration": 1,
            "max_iterations": 3,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        },
        "decision": "done",
        "stop_reason": "skip_debugger_repair_invalid",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [
            [
                ["_should_debug"],
                {"decision": "done", "output_summary": {"reason": "skip_debugger_repair_invalid", "iteration": 1}},
            ]
        ],
        "logs": [{"logger": "src.graph.workflow", "level": "INFO", "message": "连续多次修复无效，跳过 Debugger"}],
    },
    {
        "name": "repair_invalid_at_max",
        "env": {},
        "state": {
            "iteration": 3,
            "max_iterations": 3,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        },
        "decision": "done",
        "stop_reason": "max_iterations",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [[["_should_debug"], {"decision": "done", "output_summary": {"reason": "max_iterations"}}]],
        "logs": [],
    },
    {
        "name": "max_iteration_keyword",
        "env": {},
        "state": {
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：期望的异常类型不匹配（test code 断言错误）",
            "regeneration_count": 0,
        },
        "decision": "regenerate",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [
            [
                ["_should_debug"],
                {
                    "decision": "regenerate",
                    "output_summary": {"reason": "test_gen_diagnosis", "signal": "diagnosis_keyword"},
                },
            ]
        ],
        "logs": [
            {
                "logger": "src.graph.workflow",
                "level": "INFO",
                "message": "诊断表明测试生成错误（信号=diagnosis_keyword），触发重新生成测试代码",
            }
        ],
    },
    {
        "name": "max_iteration",
        "env": {},
        "state": {"iteration": 3, "max_iterations": 3},
        "decision": "done",
        "stop_reason": "max_iterations",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [[["_should_debug"], {"decision": "done", "output_summary": {"reason": "max_iterations"}}]],
        "logs": [],
    },
    {
        "name": "keyword_early",
        "env": {},
        "state": {
            "iteration": 1,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：期望的异常类型不匹配（test code 断言错误）",
            "regeneration_count": 0,
        },
        "decision": "regenerate",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [
            [
                ["_should_debug"],
                {
                    "decision": "regenerate",
                    "output_summary": {"reason": "test_gen_diagnosis_early", "signal": "diagnosis_keyword"},
                },
            ]
        ],
        "logs": [
            {
                "logger": "src.graph.workflow",
                "level": "INFO",
                "message": "诊断表明测试生成错误（iteration < max，信号=diagnosis_keyword），触发重新生成测试代码",
            }
        ],
    },
    {
        "name": "keyword_early_regen_capped",
        "env": {},
        "state": {
            "iteration": 1,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：期望的异常类型不匹配（test code 断言错误）",
            "regeneration_count": 2,
        },
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 1}}]],
        "logs": [],
    },
    {
        "name": "stalled_trace_off_plain",
        "env": {},
        "state": {
            "iteration": 2,
            "max_iterations": 3,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
                {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            ],
        },
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 2}}]],
        "logs": [],
    },
    {
        "name": "stalled_trace_off_repair_invalid",
        "env": {},
        "state": {
            "iteration": 2,
            "max_iterations": 3,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
                {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            ],
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        },
        "decision": "done",
        "stop_reason": "skip_debugger_repair_invalid",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [
            [
                ["_should_debug"],
                {"decision": "done", "output_summary": {"reason": "skip_debugger_repair_invalid", "iteration": 2}},
            ]
        ],
        "logs": [{"logger": "src.graph.workflow", "level": "INFO", "message": "连续多次修复无效，跳过 Debugger"}],
    },
    {
        "name": "stalled_trace_off_at_max",
        "env": {},
        "state": {
            "iteration": 3,
            "max_iterations": 3,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
                {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            ],
        },
        "decision": "done",
        "stop_reason": "max_iterations",
        "mutated_keys": ["stop_reason"],
        "trace_calls": [[["_should_debug"], {"decision": "done", "output_summary": {"reason": "max_iterations"}}]],
        "logs": [],
    },
    {
        "name": "growing_trace_plain",
        "env": {},
        "state": {
            "iteration": 1,
            "max_iterations": 3,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 30.0, "coverage_delta": 30.0},
            ],
        },
        "decision": "debug",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [[["_should_debug"], {"decision": "debug", "output_summary": {"iteration": 1}}]],
        "logs": [],
    },
    {
        "name": "detection_first_all_green",
        "env": {"DETECTION_FIRST_ENABLE": "true"},
        "state": {
            "test_passed": True,
            "iteration": 0,
            "regeneration_count": 0,
            "execution_trace": [
                {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
                {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
                {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            ],
        },
        "decision": "regenerate",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [
            [["_should_debug"], {"decision": "regenerate", "output_summary": {"reason": "detection_first_all_green"}}]
        ],
        "logs": [
            {
                "logger": "src.graph.workflow",
                "level": "INFO",
                "message": "W3 检出优先：首轮全绿未检出缺陷，触发再生成更强的测试（先红后绿）",
            }
        ],
    },
    {
        "name": "specificity_gate_over_red",
        "env": {"DETECTION_SPECIFICITY_GATE_ENABLE": "true"},
        "state": {"iteration": 0, "specificity_gate_verdict": "over_red", "regeneration_count": 0},
        "decision": "regenerate",
        "stop_reason": None,
        "mutated_keys": [],
        "trace_calls": [
            [["_should_debug"], {"decision": "regenerate", "output_summary": {"reason": "specificity_gate_over_red"}}]
        ],
        "logs": [
            {
                "logger": "src.graph.workflow",
                "level": "INFO",
                "message": "AC2 特异性门：过红测试（gold fixed 上仍红），路由再生成缺陷特异测试",
            }
        ],
    },
]


class TestOffGoldenTable:
    """默认关路径零行为证据：18 行状态矩阵与**改动前**实现逐位一致。"""

    def test_golden_table_has_18_frozen_rows(self) -> None:
        # 表由改动前实现（2026-10-18 T4 开工前）冻结，行数固定防静默删行
        assert len(_OFF_GOLDEN_TABLE) == 18
        assert len({row["name"] for row in _OFF_GOLDEN_TABLE}) == 18

    def test_golden_tail_stall_row_present(self) -> None:
        # 关键零变化行：OFF 时停滞 trace 不得改变历史路由（stall 开关 OFF 时
        # _coverage_stall_detected 恒 False → 与无停滞 trace 的历史分支一致）
        rows = {row["name"]: row for row in _OFF_GOLDEN_TABLE}
        assert rows["stalled_trace_off_repair_invalid"]["decision"] == "done"
        assert rows["stalled_trace_off_repair_invalid"]["stop_reason"] == "skip_debugger_repair_invalid"
        assert rows["stalled_trace_off_repair_invalid"]["logs"] == [
            {"logger": "src.graph.workflow", "level": "INFO", "message": _REPAIR_INVALID_LOG}
        ]

    @pytest.mark.parametrize("row", _OFF_GOLDEN_TABLE, ids=[row["name"] for row in _OFF_GOLDEN_TABLE])
    def test_off_decision_trace_logs_unchanged(
        self,
        base_env: None,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        row: dict[str, Any],
    ) -> None:
        # 行级 env 覆盖（检出优先 / 特异性门等历史分支基线）
        with pytest.MonkeyPatch.context() as mp:
            for name, value in row["env"].items():
                mp.setenv(name, value)
            state = _base_state()
            state.update(row["state"])
            before = dict(state)
            recorder = _TraceRecorder()
            monkeypatch.setattr(wf, "_trace_node", recorder)
            with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
                decision = wf._should_debug(state)
        assert decision == row["decision"], f"{row['name']}：路由决策漂移"
        assert state.get("stop_reason") == row["stop_reason"], f"{row['name']}：终止标签漂移"
        mutated = sorted(k for k in before if before.get(k) != state.get(k))
        assert mutated == row["mutated_keys"], f"{row['name']}：状态变更键集合漂移"
        assert recorder.calls == row["trace_calls"], f"{row['name']}：_trace_node 调用序列漂移"
        workflow_logs = [
            {"logger": rec.name, "level": rec.levelname, "message": rec.getMessage()}
            for rec in caplog.records
            if rec.name == "src.graph.workflow"
        ]
        assert workflow_logs == row["logs"], f"{row['name']}：日志文案漂移"


# ═══ 2. A-19 抢占优先级修复（ON 语义） ══════════════════════════════════════
class TestA19PriorityPreemption:
    """S-2 登记缺陷：默认协议下 repair-invalid 与停滞窗口同迭代收敛。"""

    def _tie_state(self) -> dict[str, Any]:
        return _base_state(
            iteration=2,
            max_iterations=3,
            test_passed=False,
            execution_trace=_STALL_TRACE,
            repair_history=_INVALID_REPAIRS,
        )

    def test_on_tie_stall_preempts_repair_invalid(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        recorder = _TraceRecorder()
        monkeypatch.setattr(wf, "_trace_node", recorder)
        state = self._tie_state()
        with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
            decision = wf._should_debug(state)
        # 路由与迭代数不变（平局止于同一迭代）——修复只改"谁拥有终止决定"
        assert decision == "done"
        assert state["stop_reason"] == wf.StopReason.COVERAGE_STALL.value
        # 分支归属证据：日志为停滞文案（修复前是"连续多次修复无效"）
        messages = [rec.getMessage() for rec in caplog.records if rec.name == "src.graph.workflow"]
        assert any(_STALL_PREEMPT_LOG in m for m in messages), messages
        assert all(_REPAIR_INVALID_LOG not in m for m in messages), messages
        # 打点：preempted 键如实记录被抢占的 repair-invalid（纯观测）
        assert recorder.calls == [
            [
                ["_should_debug"],
                {
                    "decision": "done",
                    "output_summary": {
                        "reason": "coverage_stall",
                        "iteration": 2,
                        "preempted": "skip_debugger_repair_invalid",
                    },
                },
            ]
        ]

    def test_off_tie_repair_invalid_unchanged(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 默认关：同一条平局状态 → 历史 repair-invalid 分支照旧（零变化）
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "false")
        state = self._tie_state()
        with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
            decision = wf._should_debug(state)
        assert decision == "done"
        assert state["stop_reason"] == wf.StopReason.REPAIR_INVALID.value
        messages = [rec.getMessage() for rec in caplog.records if rec.name == "src.graph.workflow"]
        assert messages == [_REPAIR_INVALID_LOG]

    def test_on_tie_without_stall_keeps_repair_invalid(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # ON 但覆盖率仍在显著变化（不判停滞）→ repair-invalid 语义不得被改写
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        state = self._tie_state()
        state["execution_trace"] = _GROW_TRACE
        with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
            decision = wf._should_debug(state)
        assert decision == "done"
        assert state["stop_reason"] == wf.StopReason.REPAIR_INVALID.value
        messages = [rec.getMessage() for rec in caplog.records if rec.name == "src.graph.workflow"]
        assert messages == [_REPAIR_INVALID_LOG]

    def test_on_no_repair_invalid_still_tail_short_circuit(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 非平局路径：停滞尾部短路保持原语义（gate-off 场景的省迭代来源）
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        state = self._tie_state()
        state["repair_history"] = _VALID_REPAIRS
        with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
            decision = wf._should_debug(state)
        assert decision == "done"
        assert state["stop_reason"] == wf.StopReason.COVERAGE_STALL.value
        messages = [rec.getMessage() for rec in caplog.records if rec.name == "src.graph.workflow"]
        assert len(messages) == 1 and _STALL_TAIL_LOG in messages[0]

    def test_on_tie_route_unchanged_for_later_branches(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 范围限定/路由不变：平局状态下 repair-invalid 在历史实现中本就先返回
        # done（排在 test_defect / 关键词 regenerate 之前）→ 加停滞守卫后仍是
        # done，**唯一差异是归因**（coverage_stall vs repair_invalid），
        # 不引入/不放大任何路由变化。
        for extra in (
            {"defect_type": "test_defect", "regeneration_count": 0},
            {"diagnosis": _KEYWORD_DIAGNOSIS, "regeneration_count": 0},
        ):
            monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "false")
            off_state = self._tie_state()
            off_state.update(extra)
            assert wf._should_debug(off_state) == "done"
            assert off_state["stop_reason"] == "skip_debugger_repair_invalid"
            monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
            on_state = self._tie_state()
            on_state.update(extra)
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="src.graph.workflow"):
                assert wf._should_debug(on_state) == "done"
            assert on_state["stop_reason"] == "coverage_stall"
            messages = [rec.getMessage() for rec in caplog.records if rec.name == "src.graph.workflow"]
            assert any(_STALL_PREEMPT_LOG in m for m in messages), messages

    def test_on_stall_guard_does_not_preempt_earlier_specificity_gate(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 范围限定：守卫只作用于 repair-invalid 平局分支；排在更前的
        # specificity-gate 再生成分支照旧（不被停滞抢占）
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        monkeypatch.setenv("DETECTION_SPECIFICITY_GATE_ENABLE", "true")
        state = self._tie_state()
        state["iteration"] = 0
        state["specificity_gate_verdict"] = "over_red"
        state["regeneration_count"] = 0
        assert wf._should_debug(state) == "regenerate"

    def test_on_tie_iteration_count_unchanged_zero_savings_contract(
        self, base_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 预注册口径：本修复**不承诺**迭代节省（ON/OFF 平局同为 done，iteration
        # 计数不因优先级变化）；省迭代收益仍来自 gate-off 场景的尾部短路
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        on_state = self._tie_state()
        on_decision = wf._should_debug(on_state)
        on_iteration = on_state["iteration"]
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "false")
        off_state = self._tie_state()
        off_decision = wf._should_debug(off_state)
        off_iteration = off_state["iteration"]
        assert on_decision == off_decision == "done"
        assert on_iteration == off_iteration == 2
        # 唯一差异 = 终止归因
        assert on_state["stop_reason"] == "coverage_stall"
        assert off_state["stop_reason"] == "skip_debugger_repair_invalid"

    def test_priority_guard_scope_is_repair_invalid_only(self) -> None:
        # 结构锁（防未来重构把守卫移到"抢占一切再生"的位置）：
        # 守卫条件必须与 _repair_invalid_hit 合取，且停滞判定跨 repair-invalid 平局
        source = __import__("inspect").getsource(wf._should_debug)
        guard = "_repair_invalid_hit and _coverage_stall_enabled() and _coverage_stall_detected(state)"
        assert guard in source
        # 停滞平局守卫出现在 repair-invalid 主体之前（同一 if 链先停滞后 repair）
        assert source.index(guard) < source.index('logger.info("连续多次修复无效，跳过 Debugger")')


# ═══ 3. 回滚 verdict 结果行 schema（O 轮登记） ═══════════════════════════════
def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="repo__repo-1",
        repo_name="repo/repo",
        problem_statement="fix a bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={"source": "test"},
    )


@pytest.fixture()
def _cheap_row_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """结果行组装的重材料 helper 用零-LLM 常量替身（本组只验证键位/投影）。"""
    monkeypatch.setattr(rb, "_compute_detection_rate", lambda task, state: None)
    monkeypatch.setattr(rb, "_compute_oracle_suite_verdict", lambda task, state: "unavailable")
    monkeypatch.setattr(rb, "_compute_repair_rate", lambda task, state: None)
    monkeypatch.setattr(rb, "_compute_false_fix_rate", lambda task, state: None)
    monkeypatch.setattr(rb, "_compute_test_error_rate", lambda task, state: None)


class TestRollbackVerdictRowSchema:
    """A-03 快照/P2P 回滚观测字段进结果行（成功投影 / 失败占位，纯观测）。"""

    def test_success_row_projects_rollback_fields(self, _cheap_row_helpers: None) -> None:
        state = {
            "test_passed": False,
            "iteration": 2,
            "patch_rollback_verdict": "regression_failed",
            "patch_rolled_back": True,
        }
        row = _build_task_result(_make_task(), 1.0, final_state=state)
        assert row["patch_rollback_verdict"] == "regression_failed"
        assert row["patch_rolled_back"] is True

    def test_success_row_without_rollback_protocol_is_none(self, _cheap_row_helpers: None) -> None:
        # 无补丁/未进入修复环：state 未写这两个键 → None（"回滚协议未执行"，
        # 与 False"执行但未回滚"语义区分）
        row = _build_task_result(_make_task(), 1.0, final_state={"test_passed": False})
        assert row["patch_rollback_verdict"] is None
        assert row["patch_rolled_back"] is None

    def test_success_row_not_enabled_is_false(self, _cheap_row_helpers: None) -> None:
        # 开关默认关（PATCH_SNAPSHOT_ROLLBACK_ENABLE=false）时 _patch_applier_node
        # 写 "not_enabled"/False（纯观测，不参与路由）
        state = {"patch_rollback_verdict": "not_enabled", "patch_rolled_back": False}
        row = _build_task_result(_make_task(), 1.0, final_state=state)
        assert row["patch_rollback_verdict"] == "not_enabled"
        assert row["patch_rolled_back"] is False

    def test_failure_row_placeholder_semantics(self) -> None:
        # 失败分支无 final_state → 无回滚语义：verdict=None（不可判定）、
        # rolled_back=False（明确未发生回滚）
        row = _build_task_result(_make_task(), 0.5, diagnosis="执行异常: boom", error_category="error")
        assert row["patch_rollback_verdict"] is None
        assert row["patch_rolled_back"] is False

    def test_success_failure_rows_same_key_set(self, _cheap_row_helpers: None) -> None:
        success = _build_task_result(
            _make_task(), 1.0, final_state={"patch_rollback_verdict": "verified", "patch_rolled_back": False}
        )
        failure = _build_task_result(_make_task(), 1.0, diagnosis="boom", error_category="error")
        assert set(success) == set(failure)

    def test_row_json_persistable(self, _cheap_row_helpers: None, tmp_path) -> None:
        # 落盘验证：两键随结果行进入 JSON 工件（可序列化 + 往返保真）
        state = {"patch_rollback_verdict": "regression_failed", "patch_rolled_back": True}
        row = _build_task_result(_make_task(), 1.0, final_state=state)
        out = tmp_path / "benchmark_row.json"
        out.write_text(json.dumps({"details": [row]}, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(out.read_text(encoding="utf-8"))["details"][0]
        assert loaded["patch_rollback_verdict"] == "regression_failed"
        assert loaded["patch_rolled_back"] is True
