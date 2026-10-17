#!/usr/bin/env python3
"""O-3 修复后零 LLM 取证：`_cross_file_analyzer_node` trace 决策/字段（观测性修复验证）。

Run #1 真实图跑在**修复前**完成（trace 见 traces/run1/：decision=single_file_fallback
+ dep_edges=0，正是 D3c 缺陷证据）。本脚本零 LLM 重放同一 state 形状
（AST 0 边 + benchmark 预置 dep_chain 边），在**修复后**代码上采集 trace，
证明 decision=deps_found、ast/preset 分列——观测性修复生效，路由/落态未变。

产物：`trace_after_fix/<task>.trace.jsonl` + `analyzer_trace_after_fix.json`。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
ARTIFACT_DIR = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))

HELPER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPER_DIR))
import o3_scenario  # noqa: E402

os.environ["AITESTER_TRACE_DIR"] = str(ARTIFACT_DIR / "trace_after_fix")
os.environ.setdefault("AITESTER_LLM_CACHE", "0")

from src.graph.nodes import _cross_file_analyzer_node  # noqa: E402
from src.graph.state import create_initial_state  # noqa: E402
from src.graph.tracing import end_task_trace, start_task_trace  # noqa: E402


def main() -> int:
    trace_dir = ARTIFACT_DIR / "trace_after_fix"
    trace_dir.mkdir(parents=True, exist_ok=True)
    for stale in trace_dir.glob("*.trace.jsonl"):
        stale.unlink()

    workdir = Path(tempfile.mkdtemp(prefix="aitester_o3_after_fix_"))
    target_file = workdir / f"{o3_scenario.TARGET_MODULE}.py"
    target_file.write_text(o3_scenario.TARGET_CODE, encoding="utf-8")
    state = create_initial_state(
        "o3_after_fix",
        str(target_file),
        o3_scenario.TARGET_CODE,
        2,
        module_name=o3_scenario.TARGET_MODULE,
        target_function="add",
    )
    state["cross_file_deps"] = list(o3_scenario.DEP_EDGES)
    start_task_trace("o3_after_fix", {"module_name": o3_scenario.TARGET_MODULE})
    try:
        update = _cross_file_analyzer_node(state)  # type: ignore[arg-type]
    finally:
        end_task_trace(True)

    trace_files = sorted(trace_dir.glob("*.trace.jsonl"))
    records: list[dict[str, object]] = []
    for path in trace_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    analyzer_records = [r for r in records if r.get("node") == "cross_file_analyzer"]
    evidence = {
        "update_cross_file_deps": update.get("cross_file_deps"),
        "update_cross_file_plan": update.get("cross_file_plan"),
        "trace_files": [str(p) for p in trace_files],
        "analyzer_records": analyzer_records,
        "decision": analyzer_records[0].get("decision") if analyzer_records else None,
        "dep_edges": (analyzer_records[0].get("output") or {}).get("dep_edges") if analyzer_records else None,
        "note": (
            "零 LLM 重放（与 Run #1 相同 state 形状）；Run #1 真实图跑发生在修复前，"
            "trace 中 decision=single_file_fallback/dep_edges=0 即 D3c 缺陷证据。"
        ),
    }
    out_path = ARTIFACT_DIR / "analyzer_trace_after_fix.json"
    out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(workdir, ignore_errors=True)
    print(json.dumps({"status": "ok", "out": str(out_path), "decision": evidence["decision"], "dep_edges": evidence["dep_edges"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
