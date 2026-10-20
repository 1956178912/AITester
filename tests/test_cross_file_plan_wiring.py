"""D3b Step A 跨文件修复计划接线回归锁（2026-10-18 第三轮独立评审落地；零 LLM）。

锁五类行为（设计依据 docs/design/cross_file_plan_wiring_prereg.md §3 Step A、
§3.5 Step B 前置件核查）：
1. **双开关默认关**：BUILD/CONSUME 读取器默认 false（OFF/OFF = 历史行为）；
2. **构建侧**：BUILD 开 + 跨文件任务 → `_debugger_node` 调
   `build_cross_file_repair_plan_cached` 且 update 写 `cross_file_plan`；
   BUILD 关 → 不写键（键集合同构，analyzer 的 None 占位不被覆盖）；
3. **消费侧**：CONSUME 开 + plan 在场 → `_resolve_target_module` 取
   `target_modules[0]`；CONSUME 关 → 即使 plan 在场也走依赖边末元素
   （历史口径），实现"构建不消费"的 A1 臂语义；
4. **单文件零变化**：无 cross_file_deps 时任何开关组合下 target_module
   恒为 state["module_name"]；
5. **Step B 未接线（反面锁定）**：apply 入参与写盘面只含入口模块，
   `per_module_patches` 零消费者（详见 `TestStepBNotWired` 文档串）。
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
class TestStepBNotWired:
    """Step B（多模块协同修复）**未接线**的反面锁定（AA 轮 2026-10-19，零 LLM）。

    这三条锁的是**现状能力边界**而非期望行为：analyzer 的 `source_files` 与
    patch_applier 的 `original_files`/`patches` 都只含入口模块，即使同目录伴生
    模块已在磁盘上（benchmark 层 `_write_cross_file_modules` 会物化）、即使
    plan 携带多模块 `per_module_patches` 且 CONSUME 开。因此今天不存在
    "多文件写盘"能力，`apply_multi_file_patch` 的多模块拓扑序只是单元素退化。

    Step B 实装时本组用例必红——那是**预期信号**：必须同步改写
    `docs/design/cross_file_plan_wiring_prereg.md` §3.5 与登记册 §4 的
    "Step B 未接线"披露行，不得只把断言改成新行为放行。
    """

    _ENTRY_SRC = "from module_c import helper\n\n\ndef f():\n    return helper()\n"
    _SIBLING_SRC = "def helper():\n    return 42\n"

    @staticmethod
    def _workspace(tmp_path: Any) -> tuple[Any, Any]:
        """入口模块 + 同目录伴生模块（真实跨文件工作区，与 benchmark 层物化同形）。"""
        sibling = tmp_path / "module_c.py"
        sibling.write_text(TestStepBNotWired._SIBLING_SRC, encoding="utf-8")
        entry = tmp_path / "module_a.py"
        entry.write_text(TestStepBNotWired._ENTRY_SRC, encoding="utf-8")
        return entry, sibling

    def test_analyzer_source_files_excludes_sibling_module_on_disk(self, tmp_path: Any) -> None:
        """前置件 (a)：伴生模块源码从未载入 —— `source_files` 恒为 entry 单键。"""
        from src.graph import nodes

        entry, sibling = self._workspace(tmp_path)
        spy = MagicMock(return_value=[])
        state = _state(target_file=str(entry), module_name="module_a", target_code=self._ENTRY_SRC)
        with (
            patch.object(nodes, "_trace_node"),
            patch.object(nodes, "analyze_multi_entry_deps", spy),
        ):
            nodes._cross_file_analyzer_node(state)  # type: ignore[arg-type]
        entry_modules, source_files = spy.call_args.args
        assert entry_modules == ["module_a"]
        assert set(source_files) == {"module_a"}
        assert sibling.exists()  # 源码在磁盘上可得，但节点不读（一期口径）

    def test_patch_applier_builds_entry_only_original_files_and_patches(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """前置件 (b)：plan 的 `per_module_patches` 无消费者——apply 入参恒为 entry 单键。"""
        from src.graph import nodes
        from src.tools import cross_file as cf

        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        monkeypatch.setenv("CROSS_FILE_PLAN_CONSUME_ENABLE", "true")
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        entry, sibling = self._workspace(tmp_path)
        patched = "from module_c import helper\n\n\ndef f():\n    return helper() + 1\n"
        recorder = MagicMock(return_value=({entry.stem: patched}, True))
        monkeypatch.setattr(cf, "apply_multi_file_patch", recorder)
        state = _state(
            target_file=str(entry),
            module_name="module_a",
            target_code=self._ENTRY_SRC,
            patch=patched,
            repair_history=[],
            iteration=0,
            cross_file_plan={
                "target_modules": ["module_a", "module_c"],
                "per_module_patches": {"module_a": patched, "module_c": self._SIBLING_SRC},
            },
        )
        with patch.object(nodes, "_trace_node"):
            update = nodes._patch_applier_node(state)  # type: ignore[arg-type]

        original_files, patches = recorder.call_args.args[:2]
        assert set(original_files) == {"module_a"}  # 非 entry 模块原文不进 apply
        assert set(patches) == {"module_a"}  # per_module_patches 未被消费
        assert update["target_code"] == patched
        assert update["repair_history"][-1]["patch_applied"] is True
        # 非入口模块在磁盘上原封不动：写盘面只有 state["target_file"]
        assert sibling.read_text(encoding="utf-8") == self._SIBLING_SRC

    def test_state_has_no_multi_module_write_back_channel(self) -> None:
        """前置件 (c)：state 里没有承载"其他模块新代码 + 每模块快照"的通道键。

        多文件写盘/整体回滚要落地，必须先有跨模块新代码与逐模块快照的落态位置；
        现仅 `cross_file_contexts`（聚焦摘录，非整模块原文）与单文件
        `_last_patch_snapshot`。此锁防止把"摘录字段"误当成源码通道接进 Step B。
        """
        from src.graph.state import AITesterState

        declared = set(AITesterState.__annotations__)
        assert "cross_file_contexts" in declared and "_last_patch_snapshot" in declared
        for absent in ("cross_file_source_files", "cross_file_new_files", "cross_file_snapshots"):
            assert absent not in declared


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
