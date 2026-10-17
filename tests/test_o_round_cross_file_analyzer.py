#!/usr/bin/env python3
"""O-3 跨文件修复路径：analyzer 观测性修复 + 多文件组件契约回归（零 LLM / 零网络）。

背景（O-3，2026-10-18）：N-4 的 D3 登记"cross_file_analyzer 在真实批次从未进入"。
O-3 用确定性首轮失败场景强制图路由进入后实测发现并修复一个**观测性缺陷**：

- `_cross_file_analyzer_node` 的 trace `dep_edges`/decision 只统计 **AST 推导边**，
  而 benchmark 层预置依赖边（`state["cross_file_deps"]`，由 `_write_cross_file_state`
  按 dep_chain 注入）在下游实际被保留——真实跨文件任务（被调方视角 AST 0 边 +
  预置边非空）在 trace 里被误标为 `single_file_fallback`/`dep_edges=0`，审计侧
  会误判"analyzer 没找到依赖"。修复：trace 分列 `ast_dep_edges` /
  `preset_dep_edges`，decision 反映**有效依赖边**（纯观测，路由/落态零变化）。

另锁定同批实测确认的**二期缺口**（不修，测试防止静默变化）：
- `cross_file.build_cross_file_repair_plan`（协调器-提议者多模块补丁计划）组件可跑，
  但 `src/graph/` 内**零调用点** → 图通路 `cross_file_plan` 恒 None 占位，
  多文件补丁分支实际只会拿到入口模块补丁（详见 O-3 报告缺陷 D3b）。

全部测试零 LLM / 零网络 / 确定性。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from src.graph.state import create_initial_state

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ─── 场景常量（与 experiments/results/o_round_cross_file_20261017/_helpers 同构）──
TARGET_MODULE = "o3_target"
CALLER_MODULE = "o3_caller"
TARGET_CODE = '"""O-3 场景：被调方。"""\n\n\ndef add(a, b):\n    """Return the sum of a and b."""\n    return a - b\n'
CALLER_CODE = '"""O-3 场景：调用方。"""\n\nfrom o3_target import add\n\n\ndef add_twice(a, b):\n    return add(a, b) + add(a, b)\n'
FIXED_TARGET_CODE = (
    '"""O-3 场景：被调方（gold）。"""\n\n\ndef add(a, b):\n    """Return the sum of a and b."""\n    return a + b\n'
)
GOLD_TEST = "from o3_target import add\n\n\ndef test_add_positive():\n    assert add(2, 3) == 5\n"
PRESET_DEPS: list[dict[str, Any]] = [
    {
        "source_module": CALLER_MODULE,
        "target_module": TARGET_MODULE,
        "symbol": "",
        "call_line": 0,
        "source": "benchmark_preset",
        "context": f"dep_chain[0]: {CALLER_MODULE} -> {TARGET_MODULE}",
    }
]


def _state(tmp_path: Path, *, target_code: str = TARGET_CODE) -> dict[str, Any]:
    target_file = tmp_path / f"{TARGET_MODULE}.py"
    target_file.write_text(target_code, encoding="utf-8")
    state = create_initial_state(
        "o3_test",
        str(target_file),
        target_code,
        2,
        module_name=TARGET_MODULE,
        target_function="add",
    )
    return dict(state)


def _capture_trace(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import src.graph.nodes as nodes_mod

    captured: list[dict[str, Any]] = []

    def _fake_trace(node: str, **kwargs: Any) -> None:
        captured.append({"node": node, **kwargs})

    monkeypatch.setattr(nodes_mod, "_trace_node", _fake_trace)
    return captured


# ─── 1. analyzer 观测性修复回归 ─────────────────────────────────────────────
class TestCrossFileAnalyzerObservability:
    def test_preset_only_deps_not_mislabelled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """回归（O-3 实测缺陷）：AST 0 边 + 预置边非空 → trace 必须 deps_found。

        修复前：decision=single_file_fallback、dep_edges=0（误导审计）。
        """
        from src.graph.nodes import _cross_file_analyzer_node

        trace = _capture_trace(monkeypatch)
        state = _state(tmp_path)
        state["cross_file_deps"] = list(PRESET_DEPS)
        update = _cross_file_analyzer_node(state)  # type: ignore[arg-type]

        assert update["cross_file_deps"] == PRESET_DEPS  # 预置边被保留
        assert update["cross_file_plan"] is None
        analyzer = [item for item in trace if item["node"] == "cross_file_analyzer"]
        assert len(analyzer) == 1
        record = analyzer[0]
        assert record["decision"] == "deps_found", "预置边非空不得标 single_file_fallback"
        assert record["output_summary"]["ast_dep_edges"] == 0
        assert record["output_summary"]["preset_dep_edges"] == 1
        assert record["output_summary"]["dep_edges"] == 1

    def test_ast_deps_take_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """自 import（AST 可推导）时：AST 边优先，预置边被 AST 结果覆盖（历史口径）。"""
        from src.graph.nodes import _cross_file_analyzer_node

        trace = _capture_trace(monkeypatch)
        self_import_code = f"import {TARGET_MODULE}\n\n\ndef f():\n    return {TARGET_MODULE}.add(1, 2)\n"
        state = _state(tmp_path, target_code=self_import_code)
        state["cross_file_deps"] = list(PRESET_DEPS)
        update = _cross_file_analyzer_node(state)  # type: ignore[arg-type]

        deps = update["cross_file_deps"]
        assert len(deps) == 1
        assert deps[0]["source"] == "ast_derived"
        record = next(item for item in trace if item["node"] == "cross_file_analyzer")
        assert record["output_summary"]["ast_dep_edges"] == 1
        assert record["output_summary"]["preset_dep_edges"] == 1
        assert record["decision"] == "deps_found"

    def test_no_deps_single_file_fallback_unchanged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """单文件常态（无 AST / 无预置边）→ 历史降级口径逐字不变。"""
        from src.graph.nodes import _cross_file_analyzer_node

        trace = _capture_trace(monkeypatch)
        state = _state(tmp_path, target_code="def add(a, b):\n    return a + b\n")
        update = _cross_file_analyzer_node(state)  # type: ignore[arg-type]

        assert update["cross_file_deps"] == []
        assert update["cross_file_plan"] is None
        record = next(item for item in trace if item["node"] == "cross_file_analyzer")
        assert record["decision"] == "single_file_fallback"
        assert record["output_summary"]["dep_edges"] == 0

    def test_cross_file_plan_placeholder_locked(self, tmp_path: Path) -> None:
        """锁定二期缺口：cross_file_plan 恒 None（非缺陷静默，见 D3b 登记）。"""
        from src.graph.nodes import _cross_file_analyzer_node

        state = _state(tmp_path)
        state["cross_file_deps"] = list(PRESET_DEPS)
        assert _cross_file_analyzer_node(state)["cross_file_plan"] is None  # type: ignore[arg-type]


# ─── 2. 图装配：CROSS_FILE_ENABLE 注册 analyzer 与路由边 ───────────────────
class TestWorkflowAssembly:
    def _snapshot(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[set[str], set[str]]:
        from src.graph.workflow import build_workflow

        monkeypatch.delenv("AITESTER_LLM_CACHE", raising=False)
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        graph = build_workflow(planner=True, debugger=True)
        inspect = graph._graph.get_graph()
        nodes = {name for name in inspect.nodes if not name.startswith("__")}
        edges = {f"{edge.source}->{edge.target}" for edge in inspect.edges}
        return nodes, edges

    def test_enabled_registers_analyzer_and_route(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "true")
        nodes, edges = self._snapshot(tmp_path, monkeypatch)
        assert "cross_file_analyzer" in nodes
        assert "executor->cross_file_analyzer" in edges
        assert "cross_file_analyzer->debugger" in edges

    def test_disabled_omits_analyzer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CROSS_FILE_ENABLE", "false")
        nodes, edges = self._snapshot(tmp_path, monkeypatch)
        assert "cross_file_analyzer" not in nodes
        assert "executor->cross_file_analyzer" not in edges


# ─── 3. 多文件补丁组件契约（图外组件；D3b 的"机制可跑但未接线"证据基础）───
class TestMultiFilePatchComponent:
    def test_applies_two_module_patches(self) -> None:
        from src.tools.cross_file import apply_multi_file_patch

        original = {TARGET_MODULE: TARGET_CODE, CALLER_MODULE: CALLER_CODE}
        patches = {
            TARGET_MODULE: FIXED_TARGET_CODE,
            CALLER_MODULE: CALLER_CODE + "\n# fixed caller\n",
        }
        new_files, applied = apply_multi_file_patch(original, patches, entry_module=TARGET_MODULE)
        assert applied is True
        assert new_files[TARGET_MODULE] == FIXED_TARGET_CODE
        assert "# fixed caller" in new_files[CALLER_MODULE]

    def test_failure_rolls_back_all_modules(self) -> None:
        """任一模块补丁非法 → 整体回滚（返回原始映射 + applied=False）。"""
        from src.tools.cross_file import apply_multi_file_patch

        original = {TARGET_MODULE: TARGET_CODE, CALLER_MODULE: CALLER_CODE}
        patches = {
            TARGET_MODULE: FIXED_TARGET_CODE,
            CALLER_MODULE: "def broken(:\n",  # 非法补丁
        }
        new_files, applied = apply_multi_file_patch(original, patches, entry_module=TARGET_MODULE)
        assert applied is False
        assert new_files == original


# ─── 4. 孤儿计划构建器（D3b：组件可跑、图内零调用点）──────────────────────
class TestOrphanPlanBuilder:
    class _StubDebugger:
        def debug(self, target_code: str, **kwargs: Any) -> dict[str, Any]:
            module = str(kwargs.get("target_module") or "")
            patch = FIXED_TARGET_CODE if module == TARGET_MODULE else CALLER_CODE + "\n"
            return {"patch": patch}

    def test_plan_builder_generates_multi_module_patches(self) -> None:
        from src.tools.cross_file import CrossFileDependency, build_cross_file_repair_plan

        deps = [
            CrossFileDependency(
                source_module=d["source_module"],
                target_module=d["target_module"],
                symbol=d["symbol"],
                call_line=d["call_line"],
                context=d["context"],
            )
            for d in PRESET_DEPS
        ]
        plan = build_cross_file_repair_plan(
            deps,
            self._StubDebugger(),
            TARGET_CODE,
            "AssertionError",
            [],
            focus_function="add",
            target_module=TARGET_MODULE,
            source_files={TARGET_MODULE: TARGET_CODE, CALLER_MODULE: CALLER_CODE},
        )
        assert set(plan.per_module_patches) == {TARGET_MODULE, CALLER_MODULE}
        assert plan.estimated_token_cost >= 0

    def test_graph_never_calls_plan_builder(self) -> None:
        """锁定 D3b：src/graph/ 对 build_cross_file_repair_plan 零调用点。

        若未来把计划构建器接入图（需 Lead 批准的多文件修复方案），本测试
        会红——届时同步更新 O-3 报告与相关测试，而不是静默改变行为。
        """
        call_sites: list[str] = []
        for path in (_REPO_ROOT / "src" / "graph").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "build_cross_file_repair_plan":
                    call_sites.append(f"{path.relative_to(_REPO_ROOT)}:{node.lineno}")
        assert call_sites == [], f"图内出现计划构建器调用点（需更新 D3b 结论）: {call_sites}"


# ─── 5. 场景确定性（首轮必失败的场景构造自检）─────────────────────────────
class TestScenarioDeterminism:
    def test_gold_test_fails_on_buggy_passes_on_fixed(self, tmp_path: Path) -> None:
        from src.agents.executor import ExecutorAgent

        target = tmp_path / f"{TARGET_MODULE}.py"
        target.write_text(TARGET_CODE, encoding="utf-8")
        executor = ExecutorAgent(timeout=60)
        buggy = executor.execute(GOLD_TEST, str(target))
        fixed_dir = tmp_path / "fixed"
        fixed_dir.mkdir()
        fixed_target = fixed_dir / f"{TARGET_MODULE}.py"
        fixed_target.write_text(FIXED_TARGET_CODE, encoding="utf-8")
        fixed = executor.execute(GOLD_TEST, str(fixed_target))
        assert buggy["passed"] is False
        assert buggy["failed_cases"]
        assert fixed["passed"] is True
