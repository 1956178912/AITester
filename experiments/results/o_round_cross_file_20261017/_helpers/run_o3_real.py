#!/usr/bin/env python3
"""O-3 Run #1：run_benchmark 真实 LLM 跨文件单任务（预置失败场景，完整图路由）。

用法：
    .venv/bin/python \
        experiments/results/o_round_cross_file_20261017/_helpers/run_o3_real.py \
        <root> <artifact_dir> <run_tag>

关键设计（必须在 import config 之前设置 env）：
- `CROSS_FILE_ENABLE=true`：注册 cross_file_analyzer 节点；
- `ENABLE_PLANNER=false`：真实 LLM 调用 = generator 1 + debugger 1（控预算）；
- `ENABLE_DEBUGGER=true`：executor 失败后进入修复路由；
- `MAX_ITERATIONS=2`：首轮修复后复跑（第二轮到顶即收敛）；
- `AITESTER_LLM_CACHE=0`：强制真实调用，无缓存重放；
- `AITESTER_PROFILE` 清空：fast 默认档（无 logic 档额外门/注入，控变量）。

场景：`_helpers/o3_scenario.py`（缺陷代码 docstring=sum/实现=减法 →
按意图生成的测试首轮必失败 → 强制进入 cross_file_analyzer → debugger →
patch_applier 多文件分支 → 复跑）。

产物：run_benchmark 批次 JSON（含结果行审计字段）、traces/*.trace.jsonl、
raw/ 状态产物；本脚本另写 `run_<tag>_summary.json` 并打印结构化 marker。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
ARTIFACT_DIR = Path(sys.argv[2]).resolve()
RUN_TAG = sys.argv[3] if len(sys.argv) > 3 else "run1"
sys.path.insert(0, str(ROOT))

# ── env 必须在 import config / run_benchmark 之前设置 ──────────────────────
os.environ["AITESTER_PROFILE"] = "logic"  # FL_spectral/specificity gate 等生产链路（补丁证据门需要 sbfl/gold 证据）
os.environ.update(
    {
        "CROSS_FILE_ENABLE": "true",
        "ENABLE_PLANNER": "false",
        "ENABLE_DEBUGGER": "true",
        "MAX_ITERATIONS": "2",
        "AITESTER_LLM_CACHE": "0",
        "AITESTER_CACHE_NAMESPACE": f"o3_cross_file_{RUN_TAG}",
        "AITESTER_TRACE_DIR": str(ARTIFACT_DIR / "traces" / RUN_TAG),
        "LLM_THINKING_MODE": "disabled",
        "TEMPERATURE": "0.0",
        "BENCHMARK_PARALLELISM": "1",
        "ENABLE_MUTATION_SCORING": "false",
        "MUTATION_ADVISOR_ENABLE": "false",
        "BRANCH_COVERAGE_INJECT_ENABLE": "false",
        "FL_SPECTRAL_TOP_K": "5",
    }
)
(ARTIFACT_DIR / "traces" / RUN_TAG).mkdir(parents=True, exist_ok=True)

import experiments.run_benchmark as rb  # noqa: E402

HELPER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPER_DIR))
import o3_scenario  # noqa: E402


def _summarize_batch(batch_path: Path) -> dict[str, object]:
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    arm = batch.get("results", {}).get("aitester", {})
    rows = arm.get("details") or []
    row = rows[0] if rows else {}
    row_keys = sorted(row)
    audit = {
        key: row.get(key)
        for key in (
            "cross_file_enabled",
            "cross_file_deps",
            "cross_file_plan_present",
            "repair_history",
            "patch_plausible",
            "passed",
            "iterations",
            "stop_reason",
            "error_category",
            "detection_rate",
            "repair_rate",
        )
    }
    return {
        "batch_path": str(batch_path),
        "batch_sha256": __import__("hashlib").sha256(batch_path.read_bytes()).hexdigest(),
        "provenance": {
            key: batch.get("provenance", {}).get(key)
            for key in ("git_sha", "git_dirty", "model_name", "seed", "temperature", "profile")
        },
        "arm_summary": {
            key: arm.get(key)
            for key in ("total_functions", "passed_count", "success_rate", "avg_iterations", "total_time")
        },
        "row_count": len(rows),
        "row_audit": audit,
        "row_keys": row_keys,
        "tokens": arm.get("token_metrics"),
    }


def _all_node_records(files: list[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") == "node":
                records.append(record)
    return records


def _summarize_traces(trace_dir: Path) -> dict[str, object]:
    files = sorted(trace_dir.glob("*.trace.jsonl"))
    node_counter: dict[str, int] = {}
    analyzer_records: list[dict[str, object]] = []
    patch_records: list[dict[str, object]] = []
    route_records: list[dict[str, object]] = []
    events = 0
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            events += 1
            if record.get("event") != "node":
                continue
            node = str(record.get("node") or "")
            node_counter[node] = node_counter.get(node, 0) + 1
            if node == "cross_file_analyzer":
                analyzer_records.append(record)
            if node == "patch_applier":
                patch_records.append(record)
            if node == "_should_debug":
                route_records.append(record)
    route_chain = [
        {"node": str(r.get("node")), "decision": r.get("decision"), "output": r.get("output")}
        for r in sorted(
            (rec for rec in _all_node_records(files)),
            key=lambda rec: float(rec.get("ts") or 0),
        )
    ]
    return {
        "trace_files": [str(p) for p in files],
        "trace_file_count": len(files),
        "route_chain": route_chain,
        "analyzer_records": analyzer_records,
        "event_count": events,
        "node_event_counts": dict(sorted(node_counter.items())),
        "analyzer_entered": bool(analyzer_records),
        "patch_applier_records": patch_records,
        "route_records": route_records,
    }


_O3_FAILING_TEST = (
    "from o3_target import add\n\n\n"
    "def test_add_contract_sum() -> None:\n"
    "    assert add(2, 3) == 5\n\n\n"
    "def test_add_contract_zero() -> None:\n"
    "    assert add(0, 5) == 5\n"
)


def _install_dry_run_stubs() -> None:
    """零 LLM dry-run：桩 generator（返回按意图断言测试）+ 桩 debugger（返回正确补丁）。

    仅用于正式真 LLM 运行前的装配/路由自检（`O3_DRY_RUN_STUB_LLM=1`），
    不参与任何正式证据；桩口径与真实 LLM 观察到的行为同构（N-1 repair
    探针实证：planner=false 时 generator 会按 docstring 意图写断言）。
    """
    import src.graph.debugger as debugger_mod
    import src.graph.nodes as nodes_mod

    class _StubGeneratorAgent:
        def generate(self, *args: object, **kwargs: object) -> str:
            return _O3_FAILING_TEST

    class _StubDebuggerAgent:
        def debug(self, **kwargs: object) -> dict[str, object]:
            return {
                "root_cause": "add 的 docstring 声明求和，实现为减法",
                "error_category": "assertion",
                "fix_strategy": "修正算术运算符",
                "patch": o3_scenario.FIXED_TARGET_CODE,
                "defect_type": "code_defect",
                "review_reason": "",
            }

    nodes_mod.get_or_create_agent = lambda cls: _StubGeneratorAgent()  # type: ignore[assignment]
    debugger_mod._get_or_create_debugger_agent = lambda: _StubDebuggerAgent()  # type: ignore[assignment]


def main() -> int:
    if os.environ.get("O3_DRY_RUN_STUB_LLM") == "1":
        _install_dry_run_stubs()
    dataset = o3_scenario.build_dataset()
    # 注入 dataset 加载点（不改 run_benchmark 源码；场景构造在实验层）
    rb.load_dataset = lambda dataset_name, subset=None: dataset  # type: ignore[assignment]

    summarize_only = os.environ.get("O3_SUMMARIZE_ONLY") == "1"
    if summarize_only:
        summary: dict[str, object] = {"summarize_only": True}
        elapsed = 0.0
    else:
        started = time.time()
        summary = rb.run_benchmark(
            dataset_name="o3_cross_file",
            baselines=["aitester"],
            output_dir=str(ARTIFACT_DIR / "run_artifacts" / RUN_TAG),
            task_count=1,
            parallel=1,
            seed=42,
            deterministic=True,
            save_state=True,
        )
        elapsed = time.time() - started

    batch_files = sorted((ARTIFACT_DIR / "run_artifacts" / RUN_TAG).glob("benchmark_o3_cross_file_*.json"))
    if not batch_files:
        print(json.dumps({"status": "error", "detail": "run_benchmark 未产出批次 JSON"}, ensure_ascii=False))
        return 1
    batch_path = batch_files[-1]
    batch_summary = _summarize_batch(batch_path)
    trace_summary = _summarize_traces(ARTIFACT_DIR / "traces" / RUN_TAG)

    result: dict[str, object] = {
        "run_tag": RUN_TAG,
        "wall_seconds": round(elapsed, 2),
        "batch": batch_summary,
        "trace": trace_summary,
        "run_benchmark_return_top_keys": sorted(summary) if isinstance(summary, dict) else None,
    }
    summary_path = ARTIFACT_DIR / f"run_{RUN_TAG}_summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "O3_MARKER="
        + json.dumps(
            {
                "status": "ok",
                "summary_path": str(summary_path),
                "wall_seconds": result["wall_seconds"],
                "analyzer_entered": trace_summary["analyzer_entered"],
                "node_event_counts": trace_summary["node_event_counts"],
                "row_audit": batch_summary["row_audit"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
