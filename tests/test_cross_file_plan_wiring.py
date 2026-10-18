"""D3b Step A 跨文件修复计划接线回归锁（2026-10-18 第三轮独立评审落地；零 LLM）。

锁四类行为（设计依据 docs/design/cross_file_plan_wiring_prereg.md §3 Step A）：
1. **双开关默认关**：BUILD/CONSUME 读取器默认 false（OFF/OFF = 历史行为）；
2. **构建侧**：BUILD 开 + 跨文件任务 → `_debugger_node` 调
   `build_cross_file_repair_plan_cached` 且 update 写 `cross_file_plan`；
   BUILD 关 → 不写键（键集合同构，analyzer 的 None 占位不被覆盖）；
3. **消费侧**：CONSUME 开 + plan 在场 → `_resolve_target_module` 取
   `target_modules[0]`；CONSUME 关 → 即使 plan 在场也走依赖边末元素
   （历史口径），实现"构建不消费"的 A1 臂语义；
4. **单文件零变化**：无 cross_file_deps 时任何开关组合下 target_module
   恒为 state["module_name"]。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.graph import debugger as debugger_module
from src.graph.debugger import _debugger_node, _resolve_target_module
from src.tools.cross_file import (
    CrossFileRepairPlan,
    cross_file_plan_build_enabled,
    cross_file_plan_consume_enabled,
)

_DEP_EDGE: dict[str, Any] = {
    "source_module": "module_a",
    "target_module": "module_c",
    "symbol": "helper",
    "call_line": 3,
    "context": "helper()",
    "source": "ast_derived",
}


def _state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "target_file": "examples/calculator.py",
        "module_name": "synthetic__task__test",
        "target_code": "def f():\n    return 1\n",
        "iteration": 1,
        "cross_file_deps": [_DEP_EDGE],
        "error_category": "test_failure",
    }
    state.update(extra)
    return state


@pytest.mark.unit
class TestSwitchDefaults:
    """双开关默认关（OFF/OFF = 历史行为）。"""

    def test_both_switches_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CROSS_FILE_PLAN_BUILD_ENABLE", raising=False)
        monkeypatch.delenv("CROSS_FILE_PLAN_CONSUME_ENABLE", raising=False)
        assert cross_file_plan_build_enabled() is False
        assert cross_file_plan_consume_enabled() is False

    def test_switches_read_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", "true")
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "1")
        assert cross_file_plan_build_enabled() is True
        assert cross_file_plan_consume_enabled() is True


@pytest.mark.unit
class TestResolveTargetModuleGating:
    """消费门控：CONSUME 关时 plan 在场也不消费（A1 语义）。"""

    def test_consume_off_ignores_plan_in_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "false")
        state = _state(cross_file_plan={"target_modules": ["module_c"]})
        # 历史口径：plan 不被消费 → 依赖边末元素
        assert _resolve_target_module(state) == "module_c"  # 末元素恰好也是 module_c

    def test_consume_off_ignores_plan_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "false")
        state = _state()
        # 无 plan 在 state、又传了 plan 参数 → 仍走依赖边末元素（不消费参数）
        assert _resolve_target_module(state, plan={"target_modules": ["module_x"]}) == "module_c"

    def test_consume_off_falls_back_to_deps_tail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "false")
        deps = [_DEP_EDGE, {**_DEP_EDGE, "target_module": "module_z"}]
        state = _state(cross_file_deps=deps)
        assert _resolve_target_module(state) == "module_z"

    def test_consume_on_uses_plan_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "true")
        state = _state(cross_file_plan={"target_modules": ["module_head", "module_tail"]})
        assert _resolve_target_module(state) == "module_head"

    def test_consume_on_prefers_plan_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "true")
        state = _state(cross_file_plan={"target_modules": ["from_state"]})
        assert _resolve_target_module(state, plan={"target_modules": ["from_param"]}) == "from_param"

    def test_consume_on_without_plan_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "true")
        state = _state(cross_file_plan=None)
        assert _resolve_target_module(state) == "module_c"

    def test_single_file_unchanged_under_all_switches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _state(cross_file_deps=[], cross_file_plan={"target_modules": ["module_c"]})
        for build, consume in (("false", "false"), ("true", "true")):
            monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", build)
            monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", consume)
            assert _resolve_target_module(state) == "synthetic__task__test"


@pytest.mark.unit
class TestDebuggerNodeBuildWiring:
    """节点侧：BUILD 开 → 构建并落键；BUILD 关 → 不写键。"""

    def _run_node(
        self, state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        agent = MagicMock()
        agent.debug.return_value = {
            "root_cause": "rc",
            "patch": "def f():\n    return 2\n",
            "error_category": "test_failure",
        }
        plan = CrossFileRepairPlan(
            plan_id="cf_2m_test",
            target_modules=["module_a", "module_c"],
            per_module_patches={"module_a": "x"},
            dependency_edges=[],
            estimated_token_cost=10,
        )
        with (
            patch.object(debugger_module, "_get_or_create_debugger_agent", return_value=agent),
            patch.object(debugger_module, "_trace_node"),
            patch.object(debugger_module, "publish_debugger_diagnosed"),
            patch("src.tools.cross_file.build_cross_file_repair_plan_cached", return_value=plan) as builder,
            patch("src.tools.cross_file.cross_file_enabled", return_value=True),
        ):
            update = _debugger_node(state)  # type: ignore[arg-type]
        return update, {"builder": builder, "agent": agent}

    def test_build_off_writes_no_plan_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", "false")
        update, mocks = self._run_node(_state(), monkeypatch)
        assert "cross_file_plan" not in update
        mocks["builder"].assert_not_called()

    def test_build_on_writes_plan_and_consumes_when_consume_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", "true")
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "true")
        update, mocks = self._run_node(_state(), monkeypatch)
        mocks["builder"].assert_called_once()
        assert update["cross_file_plan"]["target_modules"] == ["module_a", "module_c"]
        # 消费开：agent.debug 的 target_module = plan 首元素
        assert mocks["agent"].debug.call_args.kwargs["target_module"] == "module_a"

    def test_build_on_consume_off_uses_deps_tail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", "true")
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "false")
        update, mocks = self._run_node(_state(), monkeypatch)
        mocks["builder"].assert_called_once()
        assert update["cross_file_plan"]["target_modules"] == ["module_a", "module_c"]
        # 构建不消费：target_module 走依赖边末元素（A1 臂 = 白烧调用无路由变化）
        assert mocks["agent"].debug.call_args.kwargs["target_module"] == "module_c"

    def test_build_failure_degrades_to_no_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_PLAN_BUILD_ENABLE", "true")
        agent = MagicMock()
        agent.debug.return_value = {"root_cause": "rc", "patch": "p", "error_category": "test_failure"}
        with (
            patch.object(debugger_module, "_get_or_create_debugger_agent", return_value=agent),
            patch.object(debugger_module, "_trace_node"),
            patch.object(debugger_module, "publish_debugger_diagnosed"),
            patch("src.tools.cross_file.build_cross_file_repair_plan_cached", side_effect=RuntimeError("boom")),
            patch("src.tools.cross_file.cross_file_enabled", return_value=True),
        ):
            update = _debugger_node(_state())  # type: ignore[arg-type]
        assert "cross_file_plan" not in update  # 失败降级，不阻断修复主流程
        assert update["patch"] == "p"
