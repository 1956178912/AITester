#!/usr/bin/env python3
"""O-3 零 LLM 预检：跨文件机制可运行性 + 图装配 + 孤儿计划构建器取证。

用法（必须在真实 LLM 运行前跑）：
    CROSS_FILE_ENABLE=true .venv/bin/python \
        experiments/results/o_round_cross_file_20261017/_helpers/preflight_zero_llm.py \
        <root> <artifact_dir>

取证项（全部零 LLM / 零网络）：
1. **图装配**：CROSS_FILE_ENABLE=false vs true 的节点/边差集——
   true 档必须注册 cross_file_analyzer 且存在 executor→cross_file_analyzer、
   cross_file_analyzer→debugger 路由边；
2. **analyzer 节点直接调用**：预置 dep_chain 的 state 经
   `_cross_file_analyzer_node` 后 cross_file_deps 保留（非空）、
   cross_file_plan 为 None（当前占位实现，见缺陷 D3b）；
3. **孤儿计划构建器**（缺陷 D3b 取证）：`cross_file.build_cross_file_repair_plan`
   可产出**多模块补丁计划**（stub debugger 零 LLM），
   `apply_multi_file_patch` 可真实应用两个模块补丁——但 `src/graph/` 内
   **零调用点**（AST 静态扫描），即图通路从未生成多文件计划；
4. **场景确定性**：gold 契约测试在缺陷代码上必失败、在 fixed 上必通过
   （真实 ExecutorAgent 沙箱执行）。
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
ARTIFACT_DIR = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))

# env 必须在 import config 之前设置
os.environ["CROSS_FILE_ENABLE"] = "true"
os.environ["ENABLE_PLANNER"] = "false"
os.environ["ENABLE_DEBUGGER"] = "true"
os.environ["AITESTER_LLM_CACHE"] = "0"
os.environ.setdefault("AITESTER_TRACE_DIR", str(ARTIFACT_DIR / "traces" / "preflight"))

from src.graph.state import create_initial_state  # noqa: E402
from src.graph.workflow import build_workflow  # noqa: E402

SCENARIO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCENARIO_DIR))
import o3_scenario  # noqa: E402


def _graph_snapshot() -> dict[str, object]:
    graph = build_workflow()
    inspect = graph._graph.get_graph()
    return {
        "nodes": sorted(n for n in inspect.nodes if not n.startswith("__")),
        "edges": sorted(f"{e.source}->{e.target}" for e in inspect.edges),
    }


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, object] = {}

    # ── 1. 图装配差集（CROSS_FILE_ENABLE 在 build_workflow 时经 env_flag 读取，
    #       逐次切换 env 即可，无需 reload 模块）────────────────────────────
    os.environ["CROSS_FILE_ENABLE"] = "false"
    off_snapshot = _graph_snapshot()
    os.environ["CROSS_FILE_ENABLE"] = "true"
    on_snapshot = _graph_snapshot()

    off_nodes = set(off_snapshot["nodes"])  # type: ignore[arg-type]
    on_nodes = set(on_snapshot["nodes"])  # type: ignore[arg-type]
    added_nodes = sorted(on_nodes - off_nodes)
    on_edges = set(on_snapshot["edges"])  # type: ignore[arg-type]
    evidence["graph_assembly"] = {
        "off_nodes": sorted(off_nodes),
        "on_nodes": sorted(on_nodes),
        "added_nodes": added_nodes,
        "analyzer_route_edges_present": {
            "executor->cross_file_analyzer": "executor->cross_file_analyzer" in on_edges,
            "cross_file_analyzer->debugger": "cross_file_analyzer->debugger" in on_edges,
        },
        "on_edges": sorted(on_edges),
    }

    # ── 2. analyzer 节点直接调用（预置 dep_chain）────────────────────────
    from src.graph.nodes import _cross_file_analyzer_node

    tmpdir = Path(tempfile.mkdtemp(prefix="aitester_o3_preflight_"))
    target_file = tmpdir / f"{o3_scenario.TARGET_MODULE}.py"
    target_file.write_text(o3_scenario.TARGET_CODE, encoding="utf-8")
    (tmpdir / f"{o3_scenario.CALLER_MODULE}.py").write_text(o3_scenario.CALLER_CODE, encoding="utf-8")
    state = create_initial_state(
        "o3_preflight",
        str(target_file),
        o3_scenario.TARGET_CODE,
        2,
        module_name=o3_scenario.TARGET_MODULE,
        target_function="add",
    )
    state["cross_file_deps"] = list(o3_scenario.DEP_EDGES)
    update = _cross_file_analyzer_node(state)  # type: ignore[arg-type]
    evidence["analyzer_node"] = {
        "update_keys": sorted(update),
        "cross_file_deps": update.get("cross_file_deps"),
        "cross_file_plan": update.get("cross_file_plan"),
        "cross_file_contexts": update.get("cross_file_contexts"),
        "deps_source": [d.get("source") for d in (update.get("cross_file_deps") or [])],
    }

    # ── 3. 孤儿计划构建器：组件可跑但图内零调用点 ─────────────────────────
    from src.tools.cross_file import (
        CrossFileDependency,
        apply_multi_file_patch,
        build_cross_file_repair_plan,
    )

    class _StubDebugger:
        """零 LLM 提议者 stub：对目标模块返回 add→sum 补丁；对调用方返回注释补丁。"""

        def debug(self, target_code: str, **kwargs: object) -> dict[str, object]:
            module = str(kwargs.get("target_module") or "")
            if module == o3_scenario.TARGET_MODULE:
                return {"patch": o3_scenario.FIXED_TARGET_CODE}
            return {"patch": o3_scenario.CALLER_CODE + "\n# touched by O-3 stub\n"}

    deps = [
        CrossFileDependency(
            source_module=d["source_module"],
            target_module=d["target_module"],
            symbol=d.get("symbol", ""),
            call_line=int(d.get("call_line", 0)),
            context=d.get("context", ""),
        )
        for d in o3_scenario.DEP_EDGES
    ]
    source_files = {
        o3_scenario.TARGET_MODULE: o3_scenario.TARGET_CODE,
        o3_scenario.CALLER_MODULE: o3_scenario.CALLER_CODE,
    }
    plan = build_cross_file_repair_plan(
        deps,
        _StubDebugger(),
        o3_scenario.TARGET_CODE,
        "AssertionError: assert 3 == -1",
        [],
        focus_function="add",
        target_module=o3_scenario.TARGET_MODULE,
        source_files=source_files,
    )
    original_files = {
        o3_scenario.TARGET_MODULE: o3_scenario.TARGET_CODE,
        o3_scenario.CALLER_MODULE: o3_scenario.CALLER_CODE,
    }
    new_files, applied = apply_multi_file_patch(
        original_files, plan.per_module_patches, o3_scenario.TARGET_MODULE, deps=deps
    )
    # AST 静态扫描：src/graph/ 是否调用 build_cross_file_repair_plan（期望 0）
    call_sites: list[str] = []
    for path in (ROOT / "src" / "graph").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                if name == "build_cross_file_repair_plan":
                    call_sites.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    evidence["orphan_plan_builder"] = {
        "plan_target_modules": plan.target_modules,
        "plan_per_module_patches": sorted(plan.per_module_patches),
        "plan_estimated_token_cost": plan.estimated_token_cost,
        "multi_file_apply_applied": bool(applied),
        "target_fixed_in_new_files": new_files[o3_scenario.TARGET_MODULE] == o3_scenario.FIXED_TARGET_CODE,
        "caller_touched_in_new_files": "O-3 stub" in new_files[o3_scenario.CALLER_MODULE],
        "graph_call_sites": call_sites,
        "graph_call_sites_count": len(call_sites),
    }

    # ── 4. 场景确定性：gold 契约测试在缺陷/fixed 上的执行结果 ─────────────
    from src.agents.executor import ExecutorAgent

    executor = ExecutorAgent(timeout=60)
    buggy = executor.execute(o3_scenario.GOLD_TEST, str(target_file))
    fixed_file = tmpdir / "fixed_target.py"
    fixed_file.write_text(o3_scenario.FIXED_TARGET_CODE, encoding="utf-8")
    # fixed 模块名需与测试 import 一致：写为 o3_target.py 的临时副本
    fixed_dir = Path(tempfile.mkdtemp(prefix="aitester_o3_preflight_fixed_"))
    fixed_module = fixed_dir / f"{o3_scenario.TARGET_MODULE}.py"
    fixed_module.write_text(o3_scenario.FIXED_TARGET_CODE, encoding="utf-8")
    fixed = executor.execute(o3_scenario.GOLD_TEST, str(fixed_module))
    evidence["scenario_determinism"] = {
        "gold_test_on_buggy_passed": buggy.get("passed"),
        "gold_test_on_buggy_failed_cases": len(buggy.get("failed_cases") or []),
        "gold_test_on_fixed_passed": fixed.get("passed"),
        "note": "缺陷代码（docstring=sum / 实现=减法）上按意图断言必失败 → 图路由必进入修复分支",
    }

    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)
    shutil.rmtree(fixed_dir, ignore_errors=True)

    out_path = ARTIFACT_DIR / "preflight_zero_llm.json"
    out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "out": str(out_path), "evidence": evidence}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
