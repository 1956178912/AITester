#!/usr/bin/env python3
"""O-3 Run #2：**组件级**真实 LLM 多文件修复计划构建 + 多文件补丁应用证明。

背景（D3b）：图通路从不调用 `cross_file.build_cross_file_repair_plan`
（O-3 预检静态扫描：src/graph 零调用点）→ 图内 `cross_file_plan` 恒 None，
多文件补丁分支只拿到入口模块补丁。本脚本用**真实 LLM DebuggerAgent**
（每模块 1 次 → 共 2 次真实调用）验证该计划构建器 + `apply_multi_file_patch`
组件本身可跑，即"机制可用、缺的是图接线"。

明确披露：本运行是**组件级**（不经过 LangGraph 路由），与 Run #1（完整图
路由）互补；不作为"图已支持多文件修复"的证据。

环境：真实 LLM（AITESTER_LLM_CACHE=0 强制、thinking=disabled、temp=0）、
AITESTER_PROFILE=logic（与 Run #1 同档）；预算 2 次调用 ≤ $0.01。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
ARTIFACT_DIR = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))

os.environ["AITESTER_PROFILE"] = "logic"
os.environ.update(
    {
        "AITESTER_LLM_CACHE": "0",
        "AITESTER_CACHE_NAMESPACE": "o3_component_multifile_run2",
        "LLM_THINKING_MODE": "disabled",
        "TEMPERATURE": "0.0",
        "MAX_ITERATIONS": "2",
        "ENABLE_PLANNER": "false",
        "ENABLE_DEBUGGER": "true",
        "CROSS_FILE_ENABLE": "true",
        "MUTATION_ADVISOR_ENABLE": "false",
        "ENABLE_MUTATION_SCORING": "false",
    }
)

HELPER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPER_DIR))
import o3_scenario  # noqa: E402


def _usage() -> dict[str, object]:
    from src.budget.token_usage import get_usage

    return get_usage().as_dict()


def main() -> int:
    from src.agents.debugger import DebuggerAgent
    from src.agents.executor import ExecutorAgent
    from src.tools.cross_file import (
        CrossFileDependency,
        apply_multi_file_patch,
        build_cross_file_repair_plan,
    )

    started = time.time()
    workdir = Path(tempfile.mkdtemp(prefix="aitester_o3_component_"))
    target_path = workdir / f"{o3_scenario.TARGET_MODULE}.py"
    caller_path = workdir / f"{o3_scenario.CALLER_MODULE}.py"
    target_path.write_text(o3_scenario.TARGET_CODE, encoding="utf-8")
    caller_path.write_text(o3_scenario.CALLER_CODE, encoding="utf-8")

    # 真实失败观测（零 LLM）：gold 测试在缺陷代码上失败
    executor = ExecutorAgent(timeout=60)
    buggy_run = executor.execute(o3_scenario.GOLD_TEST, str(target_path))
    test_output = str(buggy_run.get("output") or "")
    failed_cases = buggy_run.get("failed_cases") or []
    if buggy_run.get("passed") is not False:
        print(json.dumps({"status": "error", "detail": "场景前置失败：gold 测试未在缺陷代码上失败"}))
        return 1

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
    debugger = DebuggerAgent()
    plan = build_cross_file_repair_plan(
        deps,
        debugger,
        o3_scenario.TARGET_CODE,
        test_output,
        failed_cases,
        focus_function="add",
        target_module=o3_scenario.TARGET_MODULE,
        source_files=source_files,
    )
    plan_patches = dict(plan.per_module_patches)
    original_files = {
        o3_scenario.TARGET_MODULE: o3_scenario.TARGET_CODE,
        o3_scenario.CALLER_MODULE: o3_scenario.CALLER_CODE,
    }
    new_files, applied = apply_multi_file_patch(
        original_files, plan_patches, o3_scenario.TARGET_MODULE, deps=deps
    )
    # 把应用后的多文件写回工作区，验证真实执行
    tests_after: dict[str, object] = {}
    if applied:
        target_path.write_text(new_files[o3_scenario.TARGET_MODULE], encoding="utf-8")
        caller_path.write_text(new_files[o3_scenario.CALLER_MODULE], encoding="utf-8")
        gold_after = executor.execute(o3_scenario.GOLD_TEST, str(target_path))
        tests_after["gold_on_patched_target_passed"] = gold_after.get("passed")
        caller_test = (
            f"from {o3_scenario.CALLER_MODULE} import add_twice\n\n\n"
            "def test_add_twice():\n    assert add_twice(2, 3) == 10\n"
        )
        caller_after = executor.execute(caller_test, str(caller_path))
        tests_after["caller_chain_test_passed"] = caller_after.get("passed")

    result: dict[str, object] = {
        "run_tag": "run2_component_multifile",
        "kind": "component_level_real_llm",
        "disclosure": (
            "组件级证明（DebuggerAgent × 模块数 + build_cross_file_repair_plan + "
            "apply_multi_file_patch），不经过 LangGraph 路由；图路由证据见 Run #1。"
        ),
        "wall_seconds": round(time.time() - started, 2),
        "plan": {
            "target_modules": plan.target_modules,
            "per_module_patches": sorted(plan_patches),
            "per_module_patch_lens": {name: len(text) for name, text in plan_patches.items()},
            "estimated_token_cost": plan.estimated_token_cost,
            "dependency_edges": [
                {
                    "source_module": edge.source_module,
                    "target_module": edge.target_module,
                }
                for edge in plan.dependency_edges
            ],
        },
        "multi_file_apply": {
            "applied": bool(applied),
            "target_changed": (
                new_files.get(o3_scenario.TARGET_MODULE) != original_files[o3_scenario.TARGET_MODULE]
                if applied
                else False
            ),
            "caller_changed": (
                new_files.get(o3_scenario.CALLER_MODULE) != original_files[o3_scenario.CALLER_MODULE]
                if applied
                else False
            ),
            "input_sha256_target": __import__("hashlib").sha256(
                original_files[o3_scenario.TARGET_MODULE].encode()
            ).hexdigest(),
        },
        "tests_after_apply": tests_after,
        "llm_usage": _usage(),
        "buggy_run_failed_cases": len(failed_cases),
        "scenario": "o3_target(add: docstring=sum/impl=subtract) + o3_caller(add_twice)",
    }
    out_path = ARTIFACT_DIR / "run_run2_component_summary.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("O3_COMPONENT_MARKER=" + json.dumps({"status": "ok", "summary_path": str(out_path), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
