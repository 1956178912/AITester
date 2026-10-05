"""G18（2026-10-05 优化批次·T5）：核心纯函数的属性测试（hypothesis）。

覆盖口径（不变式而非样例）：
- determine_stop_reason 的优先级偏序：test_passed > budget_exceeded >
  regression_detected，对任意合法状态字段组合恒成立；
- _coverage_stall_detected 开关关时恒 False（默认口径零行为变化）；
- is_expression_clause 对含 CJK 字符的字符串恒 False（NL 快路径）；
- _compile_single_clause 产物要么空串、要么是可 ast.parse 的 assert 行；
- check_budget 开关关时恒放行且不累积消耗。

hypothesis 为测试链依赖（requirements.txt 已声明；缺失时整文件跳过，
与可选依赖测试同口径）。max_examples=50 控制套件耗时（全量 +~2s）。
"""

from __future__ import annotations

import ast
import os
from typing import Any
from unittest.mock import patch

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis 未安装（测试链依赖）")

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.graph.cost_budget import check_budget  # noqa: E402
from src.graph.state import AITesterState  # noqa: E402
from src.graph.workflow import (  # noqa: E402
    StopReason,
    _coverage_stall_detected,
    determine_stop_reason,
)
from src.specs.spec_ir_v2 import _compile_single_clause, is_expression_clause  # noqa: E402

# 状态字段的合法值域（与 AITesterState TypedDict 的写入方口径一致）
_state_core = st.fixed_dictionaries(
    {
        "iteration": st.integers(min_value=0, max_value=99),
        "max_iterations": st.integers(min_value=1, max_value=10),
        "regeneration_count": st.integers(min_value=0, max_value=3),
        "defect_type": st.one_of(st.none(), st.sampled_from(["test_defect", "implementation_defect"])),
        "diagnosis": st.one_of(st.none(), st.text(max_size=20)),
        "repair_history": st.lists(st.fixed_dictionaries({"patch_applied": st.booleans()}), max_size=4),
    }
)


def _merge(core: dict[str, Any], **extra: Any) -> AITesterState:
    state: AITesterState = dict(core)  # type: ignore[assignment]
    state.update(extra)  # type: ignore[typeddict-item]
    return state


@settings(max_examples=50, deadline=None)
@given(core=_state_core)
def test_stop_reason_test_passed_wins(core: dict[str, Any]) -> None:
    """test_passed 真值恒压过一切其他终止信号（收敛即终止）。"""
    state = _merge(core, test_passed=True, budget_exceeded=True, regression_detected=True)
    assert determine_stop_reason(state) is StopReason.TEST_PASSED


@settings(max_examples=50, deadline=None)
@given(core=_state_core)
def test_stop_reason_budget_beats_regression(core: dict[str, Any]) -> None:
    """test_passed 假时：预算硬闸优先于回归检测（硬上界口径）。"""
    state = _merge(core, test_passed=False, budget_exceeded=True, regression_detected=True)
    assert determine_stop_reason(state) is StopReason.BUDGET_EXCEEDED


@settings(max_examples=50, deadline=None)
@given(core=_state_core)
def test_stop_reason_regression_when_no_budget_flag(core: dict[str, Any]) -> None:
    state = _merge(core, test_passed=False, regression_detected=True)
    assert determine_stop_reason(state) is StopReason.REGRESSION_DETECTED


@settings(max_examples=50, deadline=None)
@given(
    trace=st.lists(
        st.fixed_dictionaries(
            {
                "passed": st.booleans(),
                "coverage_delta": st.one_of(st.none(), st.floats(min_value=-100.0, max_value=100.0, allow_nan=False)),
            }
        ),
        max_size=6,
    )
)
def test_coverage_stall_disabled_always_false(trace: list[dict[str, Any]]) -> None:
    """COVERAGE_STALL_DETECT_ENABLE 未启用时任意轨迹恒 False（零行为变化）。"""
    with patch.dict(os.environ):
        os.environ.pop("COVERAGE_STALL_DETECT_ENABLE", None)
        state: AITesterState = {"test_passed": False, "execution_trace": trace}  # type: ignore[typeddict-item]
        assert _coverage_stall_detected(state) is False


_CJK_CHARS = st.sampled_from(["测", "试", "生", "成", "错", "误"])


@settings(max_examples=50, deadline=None)
@given(
    prefix=st.text(max_size=8), suffix=st.text(max_size=8), cjk=_CJK_CHARS, pos=st.integers(min_value=0, max_value=8)
)
def test_is_expression_clause_rejects_cjk(prefix: str, suffix: str, cjk: str, pos: int) -> None:
    """含任意 CJK 字符的子句恒不可机器化（NL 快路径，零误报）。"""
    text = prefix[:pos] + cjk + suffix
    assert cjk in text
    assert is_expression_clause(text) is False


@settings(max_examples=50, deadline=None)
@given(
    lhs=st.sampled_from(["n", "r", "x", "value"]),
    op=st.sampled_from([">", ">=", "<", "<=", "==", "!="]),
    rhs=st.integers(min_value=-100, max_value=100),
)
def test_compile_single_clause_output_shape(lhs: str, op: str, rhs: int) -> None:
    """白名单内比较子句：产物为空串或可解析的 assert 行（不变式）。"""
    clause = f"{lhs} {op} {rhs}"
    out = _compile_single_clause(clause, "postcondition", "m", "f")
    assert out == "" or (out.startswith("assert ") and ast.parse(out) is not None)


@settings(max_examples=50, deadline=None)
@given(d1=st.integers(min_value=0, max_value=10**6), d2=st.integers(min_value=0, max_value=10**6))
def test_check_budget_disabled_always_allows(d1: int, d2: int) -> None:
    """COST_BUDGET_ENABLE 未启用时恒放行且消耗不累积（历史口径零变化）。"""
    with patch.dict(os.environ):
        os.environ.pop("COST_BUDGET_ENABLE", None)
        assert check_budget(d1) is True
        assert check_budget(d2) is True
