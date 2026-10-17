#!/usr/bin/env python3
"""J-4（2026-10-17）覆盖率补口：Planner 观测层（SpecIR R7 主开关 + A-01 DSL 层）
与 R1c 规约 oracle 注入的意外异常兜底腿。

动机：`_planner_node` 尾部的 25 行观测分支**从未被执行过**（SPEC_IR_ENABLE /
SPEC_IR_DSL_ENABLE 两个科研开关默认关，既有测试只跑默认口径）。这些分支写出的
`spec_ir` / `spec_compile_rate` / `spec_expr_coverage` / `spec_reject_reasons` /
`spec_provenance` / `budget_exceeded` 正是实验行里"逻辑驱动"主张的可证伪度量——
**未被执行过意味着写侧形状从未被验证**：键名拼错、None 与缺键混淆、
"空 dict 不写入"的同构约定失效，都会静默污染已发布的实验结论而不是让测试变红。

纪律：零 LLM。PlannerAgent 用 MagicMock 顶掉（`get_or_create_agent` 单点），
`src.specs` 的解析/度量函数按需用 monkeypatch 顶掉以命中难构造的分支，
其余走真实纯函数。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.specs as specs_mod
from src.graph import nodes
from src.graph.nodes import (
    _SPEC_ORACLE_VERDICT_COMPILED_EMPTY,
    _append_spec_oracle_to_test_with_verdict,
)
from src.graph.state import create_initial_state

_TARGET_CODE = "def double(x):\n    return x * 2\n"
_LOGIC_ANALYSIS: dict[str, Any] = {
    "function_name": "double",
    "input_domain": "int",
    "preconditions": ["x > 0"],
    "postconditions": ["r == x * 2"],
    "edge_cases": ["x = 0"],
}


def _state(uuid: str = "u-j4", target_function: str | None = "double") -> dict[str, Any]:
    return create_initial_state(  # type: ignore[no-any-return]
        uuid, "target_mod.py", _TARGET_CODE, 0, module_name="target_mod", target_function=target_function
    )


def _planner_update(
    monkeypatch: pytest.MonkeyPatch,
    logic_analysis: dict[str, Any] | None = None,
    *,
    state: dict[str, Any] | None = None,
    plan_side_effect: Exception | None = None,
) -> dict[str, Any]:
    """用 mock PlannerAgent 跑一次 `_planner_node`，返回其 update dict（零 LLM）。"""
    agent = MagicMock()
    if plan_side_effect is not None:
        agent.plan.side_effect = plan_side_effect
    else:
        agent.plan.return_value = {
            "function_name": "double",
            "logic_analysis": logic_analysis if logic_analysis is not None else _LOGIC_ANALYSIS,
            "test_cases": [],
        }
    with patch.object(nodes, "get_or_create_agent", return_value=agent):
        return nodes._planner_node(state or _state())  # type: ignore[arg-type]


@pytest.mark.unit
class TestPlannerSpecIrLeg:
    """R7 主开关（432-441）：SpecIR 解析 + findings 校验写回。"""

    def test_default_off_writes_no_spec_ir_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_IR_ENABLE", raising=False)
        out = _planner_update(monkeypatch)
        assert "spec_ir" not in out, "默认关时不得新增顶层键（历史键集合零变化）"

    def test_on_with_material_produces_spec_ir_with_findings(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPEC_IR_ENABLE", "true")
        out = _planner_update(monkeypatch)
        spec = out["spec_ir"]
        assert spec is not None and spec["function_name"] == "double"
        assert isinstance(spec["findings"], list), "findings 键必须存在（可为空列表），供下游对账"

    def test_on_without_material_writes_explicit_none(self, monkeypatch: pytest.MonkeyPatch):
        # 解析返回 None 时**显式写 None**而非缺键——缺键与 None 在 JSONL 投影行里
        # 可区分，会让"开关开但无规约材料"这一档永久丢失。
        monkeypatch.setenv("SPEC_IR_ENABLE", "true")
        monkeypatch.setattr(specs_mod, "parse_logic_analysis", lambda *_a, **_kw: None)
        out = _planner_update(monkeypatch)
        assert "spec_ir" in out and out["spec_ir"] is None

    def test_boundary_triplets_are_derived_and_passed_in(self, monkeypatch: pytest.MonkeyPatch):
        # 432-437：三元组来自确定性 AST 推导（非 LLM），必须真传进解析器，
        # 否则 SpecIR 的 boundaries 恒空、"机器可执行边界锚点"形同装饰。
        seen: dict[str, Any] = {}

        def _spy(la: Any, boundary_triplets: Any = None) -> dict[str, Any]:
            seen["logic_analysis"] = la
            seen["boundary_triplets"] = boundary_triplets
            return {"schema_version": "1", "function_name": "double"}

        monkeypatch.setenv("SPEC_IR_ENABLE", "true")
        monkeypatch.setattr(specs_mod, "parse_logic_analysis", _spy)
        out = _planner_update(monkeypatch)
        assert seen["logic_analysis"] == _LOGIC_ANALYSIS
        assert isinstance(seen["boundary_triplets"], list)
        assert out["spec_ir"]["findings"], "validate_spec_ir 仍须对被替换产物出具 findings"


@pytest.mark.unit
class TestPlannerSpecIrDslLeg:
    """A-01 DSL 层（448-504）：可编译率 / 表达式覆盖率 / 拒绝原因 / 溯源。"""

    def test_default_off_writes_no_dsl_keys(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_IR_DSL_ENABLE", raising=False)
        out = _planner_update(monkeypatch)
        for key in ("spec_compile_rate", "spec_expr_coverage", "spec_reject_reasons", "spec_provenance"):
            assert key not in out

    def test_dsl_on_without_r7_falls_back_to_inline_parse(self, monkeypatch: pytest.MonkeyPatch):
        # 456-462：R7 关、DSL 开 → spec_ir 通道缺席，DSL 层必须**独立**现场解析
        # logic_analysis（否则可编译率恒 0，度量退化成开关组合的伪影）。
        monkeypatch.delenv("SPEC_IR_ENABLE", raising=False)
        monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
        out = _planner_update(monkeypatch)
        assert "spec_ir" not in out
        assert isinstance(out["spec_compile_rate"], float)
        assert isinstance(out["spec_expr_coverage"], float)
        assert out["spec_compile_rate"] > 0.0, "pre/post 子句均可编译，率不应为 0"

    def test_dsl_on_reuses_r7_spec_ir(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPEC_IR_ENABLE", "true")
        monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
        out = _planner_update(monkeypatch)
        assert out["spec_ir"] is not None
        assert isinstance(out["spec_compile_rate"], float)

    def test_empty_reject_reasons_and_provenance_are_not_written(self, monkeypatch: pytest.MonkeyPatch):
        # 499-504：刻意"空则不写"以保持跨任务行键集合可对账——写 {} 会让
        # `if "spec_reject_reasons" in row` 把"无拒绝原因"误读成"有该维度"。
        monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
        monkeypatch.setattr(specs_mod, "spec_reject_reasons", lambda *_a, **_kw: {})
        monkeypatch.setattr(specs_mod, "spec_provenance", lambda *_a, **_kw: {})
        out = _planner_update(monkeypatch)
        assert "spec_reject_reasons" not in out and "spec_provenance" not in out
        assert "spec_compile_rate" in out, "同族里只有这两项走'空则不写'口径"

    def test_non_empty_reject_reasons_and_provenance_are_written(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
        monkeypatch.setattr(specs_mod, "spec_reject_reasons", lambda *_a, **_kw: {"unknown_name": 2})
        monkeypatch.setattr(specs_mod, "spec_provenance", lambda *_a, **_kw: {"preconditions": "llm"})
        out = _planner_update(monkeypatch)
        assert out["spec_reject_reasons"] == {"unknown_name": 2}
        assert out["spec_provenance"] == {"preconditions": "llm"}

    def test_unknown_function_name_falls_back_to_sole_top_level(self, monkeypatch: pytest.MonkeyPatch):
        # 480-488：M10 降级的两种形态（state 缺 target_function / 规约里是字面量
        # "unknown"）都要让签名提取回退到 target_code 的模块唯一顶层函数名，
        # 否则自定义参数名的可编译子句被误判 unknown_name，度量成为假下界。
        monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
        seen: list[Any] = []

        def _spy(spec: Any, sig_params: Any = None) -> float:
            seen.append(sig_params)
            return 0.0

        monkeypatch.setattr(specs_mod, "compile_readiness", _spy)
        _planner_update(
            monkeypatch,
            logic_analysis={**_LOGIC_ANALYSIS, "function_name": "unknown"},
            state=_state("u-j4-unknown", target_function=None),
        )
        assert seen == [["x"]], "应解析出 double(x) 的签名参数，而非退回历史默认集 {r,x,a,b,y}"


@pytest.mark.unit
class TestPlannerBudgetMarker:
    """505-508：预算封顶标记——determine_stop_reason 的 BUDGET_EXCEEDED 唯一写入点。"""

    def test_budget_exceeded_marks_flag(self, monkeypatch: pytest.MonkeyPatch):
        from src.budget.cost_budget import BudgetExceededError

        out = _planner_update(monkeypatch, plan_side_effect=BudgetExceededError(120_000, 100_000, "tokens"))
        assert out["budget_exceeded"] is True
        assert out["test_plan"]["logic_degraded"] is True

    def test_ordinary_llm_failure_does_not_mark(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_IR_ENABLE", raising=False)
        out = _planner_update(monkeypatch, plan_side_effect=RuntimeError("LLM down"))
        assert "budget_exceeded" not in out, "非预算失败不得误标 BUDGET_EXCEEDED"
        assert out["logic_degraded"] is True


@pytest.mark.unit
class TestSpecOracleCompileExceptionLeg:
    """220-223：编译层意外异常必须归入 compiled_empty，而非崩图或误记 not_attempted。"""

    def _oracle_state(self) -> dict[str, Any]:
        state = _state("u-j4-oracle")
        state["spec_ir"] = {"schema_version": "1", "function_name": "double", "postconditions": ["r == x * 2"]}
        return state

    @pytest.mark.parametrize("exc", [SyntaxError("boom"), ValueError("boom"), TypeError("boom"), KeyError("boom")])
    def test_compile_raises_falls_back_to_compiled_empty(self, monkeypatch: pytest.MonkeyPatch, exc: Exception):
        def _raise(*_a: Any, **_kw: Any) -> str:
            raise exc

        monkeypatch.setattr(specs_mod, "compile_spec_oracle", _raise)
        merged, injected, verdict = _append_spec_oracle_to_test_with_verdict("# llm test\n", self._oracle_state())  # type: ignore[arg-type]
        assert merged == "# llm test\n", "异常腿必须原样返回，不得半截注入"
        assert injected is False
        assert verdict == _SPEC_ORACLE_VERDICT_COMPILED_EMPTY

    def test_unlisted_exception_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch):
        # 兜底捕获是**有名单**的：RuntimeError 之类真故障不得被伪装成"产物为空"，
        # 否则崩图原因永久消失在判定里。
        def _raise(*_a: Any, **_kw: Any) -> str:
            raise RuntimeError("real bug")

        monkeypatch.setattr(specs_mod, "compile_spec_oracle", _raise)
        with pytest.raises(RuntimeError):
            _append_spec_oracle_to_test_with_verdict("# llm test\n", self._oracle_state())  # type: ignore[arg-type]
