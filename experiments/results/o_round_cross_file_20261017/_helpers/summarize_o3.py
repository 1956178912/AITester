#!/usr/bin/env python3
"""O-3 证据汇总：把真实 LLM 运行/零 LLM 预检/回归测试结果收敛为可审计 JSON。

输入（均在本工件目录）：
- preflight_zero_llm.json（机制/装配/孤儿构建器零 LLM 预检）
- run_run1_summary.json + run_artifacts/run1/（**完整图路由**真实 LLM 批）
- run_run2_component_summary.json（组件级真实 LLM 多文件计划/回滚）
- analyzer_trace_after_fix.json（观测性修复后 trace，零 LLM 重放）
- logs/run2_component.log（回滚原因原始行）

输出：O3_EVIDENCE.json（路由链/落态/补丁/回滚/成本/缺陷/工件 sha256）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ARTIFACT_DIR = Path(sys.argv[1]).resolve()
ROOT = ARTIFACT_DIR.parent.parent.parent


def _load(name: str) -> dict[str, object]:
    path = ARTIFACT_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _price() -> dict[str, object]:
    p = ROOT / "experiments" / "price_table.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return dict(data.get("models", {}).get("deepseek-flash", {}))
    except (OSError, ValueError):
        return {}


def _cost(usage: dict[str, object], price: dict[str, object]) -> float | None:
    """按价目表估算 USD（缺价目返回 None，不编造价目）。"""
    try:
        pin = float(price["input_per_mtok"])  # type: ignore[arg-type]
        pout = float(price["output_per_mtok"])  # type: ignore[arg-type]
        tin = float(usage.get("input_tokens") or 0)
        tout = float(usage.get("output_tokens") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    return round(tin / 1e6 * pin + tout / 1e6 * pout, 6)


def main() -> int:
    preflight = _load("preflight_zero_llm.json")
    run1 = _load("run_run1_summary.json")
    run2 = _load("run_run2_component_summary.json")
    trace_after_fix = _load("analyzer_trace_after_fix.json")

    run1_batch = json.loads(Path(str(run1.get("batch", {}).get("batch_path", ""))).read_text(encoding="utf-8")) if run1.get("batch") else {}
    run1_arm = (run1_batch.get("results") or {}).get("aitester", {})
    run1_row = (run1_arm.get("details") or [{}])[0]
    run1_tokens = run1_arm.get("token_metrics") or {}
    raw_path = ARTIFACT_DIR / "run_artifacts" / "run1" / "raw" / "synthetic__o3_target" / "aitester.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.is_file() else {}
    trace_files = sorted((ARTIFACT_DIR / "traces" / "run1").glob("*.trace.jsonl"))
    trace_records: list[dict[str, object]] = []
    for path in trace_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace_records.append(json.loads(line))
    run1_route_chain = [
        {"node": r.get("node"), "decision": r.get("decision"), "output": r.get("output")}
        for r in trace_records
        if r.get("event") == "node"
    ]
    # 旧代码（修复前）trace 中的 analyzer 记录 = D3c 缺陷直接证据
    run1_analyzer = [r for r in trace_records if r.get("node") == "cross_file_analyzer"]

    run2_tokens = run2.get("llm_usage") or {}
    total_calls = int(run1_tokens.get("total_llm_calls") or 0) + int(run2_tokens.get("llm_calls") or 0)
    total_in = int(run1_tokens.get("total_input_tokens") or 0) + int(run2_tokens.get("input_tokens") or 0)
    total_out = int(run1_tokens.get("total_output_tokens") or 0) + int(run2_tokens.get("output_tokens") or 0)
    usage_total = {"input_tokens": total_in, "output_tokens": total_out}
    price = _price()
    run2_log_lines = (ARTIFACT_DIR / "logs" / "run2_component.log").read_text(encoding="utf-8").splitlines()
    rollback_reason = [line for line in run2_log_lines if "整体回滚" in line or "漏掉原代码函数" in line]

    artifact_list = sorted(
        p
        for p in ARTIFACT_DIR.rglob("*")
        if p.is_file() and p.name not in {"SHA256SUMS"} and not p.name.endswith(".pyc")
    )
    evidence: dict[str, object] = {
        "task": "O-3 跨文件修复路径真 LLM 强制端到端",
        "date": "2026-10-18",
        "head_git_sha": run1_batch.get("provenance", {}).get("git_sha")
        or (run1.get("batch", {}).get("provenance") or {}).get("git_sha"),
        "git_dirty": run1_batch.get("provenance", {}).get("git_dirty"),
        "scenario": {
            "kind": "custom synthetic cross-file (2 modules)",
            "target_module": "o3_target",
            "caller_module": "o3_caller",
            "deterministic_failure": "add docstring 声明 sum、实现为 a-b → 按意图生成的测试首轮必失败（gold 测试自检：buggy fail / fixed pass）",
            "preset_cross_file_deps": preflight.get("graph_assembly") is not None,
            "preflight_scenario_determinism": preflight.get("scenario_determinism"),
        },
        "route_evidence_run1_graph": {
            "run_tag": "run1",
            "batch_path": run1.get("batch", {}).get("batch_path"),
            "batch_sha256": run1.get("batch", {}).get("batch_sha256"),
            "trace_files": [str(p) for p in trace_files],
            "trace_sha256": {str(p.relative_to(ARTIFACT_DIR)): _sha(p) for p in trace_files},
            "route_chain": run1_route_chain,
            "analyzer_entered": bool(run1_analyzer),
            "analyzer_record_pre_fix": run1_analyzer[0] if run1_analyzer else None,
            "node_event_counts": run1.get("trace", {}).get("node_event_counts"),
            "llm_calls": run1_tokens.get("total_llm_calls"),
            "tokens": run1_tokens,
            "wall_seconds": run1.get("wall_seconds"),
        },
        "state_and_row_audit_run1": {
            "row_audit": run1.get("batch", {}).get("row_audit"),
            "row_keys": run1.get("batch", {}).get("row_keys"),
            "raw_artifact": str(raw_path),
            "raw_keys": sorted(raw),
            "raw_patch": (raw.get("patch") or "")[:600],
            "raw_test_passed": raw.get("test_passed"),
            "raw_cross_file_deps": raw.get("cross_file_deps"),
            "generated_test_len": len(raw.get("generated_test") or ""),
            "patch_applied": (run1_row.get("repair_history") or [{}])[-1].get("patch_applied"),
            "patch_evidence_level": run1_row.get("patch_evidence_level"),
            "source_patched_unverified": run1_row.get("source_patched_unverified"),
            "patch_rollback_verdict": run1_row.get("patch_rollback_verdict"),
            "cross_file_enabled": run1_row.get("cross_file_enabled"),
            "cross_file_deps_row": run1_row.get("cross_file_deps"),
            "cross_file_plan_present": run1_row.get("cross_file_plan_present"),
        },
        "multi_file_component_run2": {
            "run_tag": "run2_component_multifile",
            "plan_per_module_patches": run2.get("plan", {}).get("per_module_patches"),
            "plan_patch_lens": run2.get("plan", {}).get("per_module_patch_lens"),
            "multi_file_apply_applied": run2.get("multi_file_apply", {}).get("applied"),
            "tests_after_apply": run2.get("tests_after_apply"),
            "rollback_reason_lines": rollback_reason,
            "llm_calls": run2_tokens.get("llm_calls"),
            "tokens": run2_tokens,
            "wall_seconds": run2.get("wall_seconds"),
            "disclosure": run2.get("disclosure"),
        },
        "analyzer_observability_fix": {
            "pre_fix_trace_decision": (run1_analyzer[0].get("decision") if run1_analyzer else None),
            "pre_fix_trace_output": (run1_analyzer[0].get("output") if run1_analyzer else None),
            "post_fix_trace": trace_after_fix.get("analyzer_records"),
            "post_fix_decision": trace_after_fix.get("decision"),
            "post_fix_dep_edges": trace_after_fix.get("dep_edges"),
            "fix_location": "src/graph/nodes.py::_cross_file_analyzer_node（trace 观测口径）",
            "routing_unchanged": True,
        },
        "defects": [
            {
                "id": "D3a",
                "status": "verified-mechanism",
                "summary": (
                    "N-4 D3 的'analyzer 从未进入'根因=场景频率：L3 真实批次任务首轮即绿 → "
                    "executor 从不 fail → 路由从不进入修复分支（非装配缺陷）。O-3 构造确定性首轮失败后，"
                    "analyzer 在真实图中被真实进入（Run #1 trace）。"
                ),
            },
            {
                "id": "D3b",
                "status": "open-need-lead-approval",
                "summary": (
                    "cross_file_plan 恒 None 占位；集中式多文件计划构建器 "
                    "cross_file.build_cross_file_repair_plan 在 src/graph 内零调用点（预检 AST 扫描），"
                    "图内 patch_applier 多文件分支只能拿到入口模块补丁（二期未接线）。"
                    "Run #2 组件级证明：真实 LLM 可产出双模块计划，apply_multi_file_patch 在补丁合法时可双文件落盘"
                    "（零 LLM stub 预检成功）；本次真实补丁因 o3_caller 补丁是'漏掉 add_twice 的整文件重写'"
                    "被 apply 层保守拒绝→**整体回滚**（安全语义正确）。修复=图接线（改 LLM 调用/路由），需 Lead 批准。"
                ),
                "evidence": {
                    "preflight_graph_call_sites": preflight.get("orphan_plan_builder", {}).get("graph_call_sites"),
                    "run2_rollback_reason": rollback_reason,
                },
            },
            {
                "id": "D3c",
                "status": "fixed",
                "summary": (
                    "_cross_file_analyzer_node 的 trace decision/dep_edges 只统计 AST 边，预置 dep_chain 边"
                    "被下游保留却在 trace 中标 single_file_fallback/dep_edges=0（审计误判）。"
                    "已修为 ast_dep_edges/preset_dep_edges 分列 + decision 反映有效边；路由/落态零变化，"
                    "回归测试 11 例（tests/test_o_round_cross_file_analyzer.py）。"
                ),
                "fix_location": "src/graph/nodes.py::_cross_file_analyzer_node",
                "tests": "tests/test_o_round_cross_file_analyzer.py（11 例）",
            },
        ],
        "llm_cost": {
            "total_calls": total_calls,
            "run1_calls": run1_tokens.get("total_llm_calls"),
            "run2_calls": run2_tokens.get("llm_calls"),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "price_model": "deepseek-flash",
            "price_table": str(ROOT / "experiments" / "price_table.json"),
            "estimated_usd_upper_bound": _cost(usage_total, price),
            "budget_usd": 0.1,
            "runs": 2,
            "runs_note": "Run1=完整图路由（真实 LLM 3 调用）；Run2=组件级多文件计划（真实 LLM 2 调用）；其后仅零 LLM 重放/汇总",
        },
        "artifacts": {
            str(p.relative_to(ARTIFACT_DIR)): _sha(p) for p in artifact_list
        },
    }
    out_path = ARTIFACT_DIR / "O3_EVIDENCE.json"
    out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "out": str(out_path),
                "analyzer_entered": evidence["route_evidence_run1_graph"]["analyzer_entered"],
                "route_chain_len": len(run1_route_chain),
                "llm_calls": total_calls,
                "estimated_usd": evidence["llm_cost"]["estimated_usd_upper_bound"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
