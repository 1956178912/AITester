#!/usr/bin/env python3
"""N-3 小规模真 LLM 冒烟（≤3 次调用；验证性，不作证据）。

目的（任务书 N-3 §4）：用 **df_spec 臂 + SPEC_ORACLE_EXEC_ENABLE=true** 跑
1 个 QuixBugs 任务，验证：
    ① 注入发生（oracle_suite_verdict 非 unavailable / spec_oracle_verdict 非 not_attempted）；
    ② LLM-suite detection 不被 oracle 失败改写（与 legacy 混判口径对比）；
    ③ 结果行/trace 字段齐全。

实现说明：直接调用生产 df_spec 臂入口 ``run_plain_llm_df_spec_baseline``
（与 run_benchmark/run_main_batch 的该臂执行路径同一函数），再经生产
``_build_task_result`` 组装结果行 —— 等价于"df_spec 臂跑 1 个任务"，
但可精确选择任务、限制调用量并保证不落盘正式批次工件。

运行（由外层 shell 提供 env：AITESTER_PROFILE=logic / TEMPERATURE=0.0 /
LLM_THINKING_MODE=disabled / SPEC_ORACLE_EXEC_ENABLE=true /
AITESTER_CACHE_NAMESPACE=n3_smoke_20261017 / AITESTER_BATCH_MAX_CALLS=3 /
COST_BUDGET_ENABLE=true / COST_BUDGET_USD=0.01 / M1_PER_TEST_TIMEOUT=1）：

    .venv/bin/python experiments/results/emse_oracle_independent_judging_20261017/smoke/smoke_run.py \
        --task-id quixbugs__find_in_sorted --out <本目录>/smoke

输出：SMOKE_REPORT.json（环境白名单/task/墙钟/token/检查项/关键字段）、
      ROW.json（完整结果行）、smoke.log（stdout）。
**不写任何 API key / 不打印敏感配置。**
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 敏感 env 白名单外一律不落盘（防 key 泄漏）；本脚本不打印任何 LLM_* 值。
_ENV_WHITELIST = (
    "AITESTER_PROFILE",
    "TEMPERATURE",
    "LLM_THINKING_MODE",
    "SPEC_ORACLE_EXEC_ENABLE",
    "M1_PER_TEST_TIMEOUT",
    "AITESTER_CACHE_NAMESPACE",
    "BENCHMARK_PARALLELISM",
    "AITESTER_BATCH_MAX_CALLS",
    "COST_BUDGET_ENABLE",
    "COST_BUDGET_USD",
)


def _env_snapshot() -> dict[str, str]:
    return {key: os.environ.get(key, "") for key in _ENV_WHITELIST}


def _model_name() -> str:
    """模型名（非敏感；不落盘/不打印 API key 与 base_url）。"""
    try:
        import config

        configs = list(getattr(config, "LLM_CONFIGS", []))
        return str(configs[0].model_name) if configs else "unknown"
    except Exception:
        return "unknown"


def _find_task(task_id: str) -> Any:
    from src.datasets import load_dataset

    dataset = load_dataset("quixbugs")
    tasks = {task.task_id: task for task in dataset.tasks}
    if task_id not in tasks:
        raise SystemExit(f"数据集无该任务: {task_id}")
    return tasks[task_id]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N-3 真 LLM 冒烟（df_spec 臂单任务）")
    parser.add_argument("--task-id", default="quixbugs__find_in_sorted")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 先 import config（触发 .env/.env.local 加载），再读项目模块
    import config  # noqa: F401  (副作用：加载 LLM 配置)
    import experiments._m1_metrics as m1
    import experiments.run_benchmark as rb
    from src.graph.state import create_initial_state

    task = _find_task(args.task_id)
    module_name = str(task.task_id).split("__")[-1].replace("-", "_")[:50]
    suggested = task.metadata.get("suggested_function")
    tmpdir = Path(tempfile.mkdtemp(prefix=f"n3_smoke_{module_name}_"))
    instance_file = tmpdir / f"{module_name}.py"
    instance_file.write_text(task.instance_code, encoding="utf-8")

    state = create_initial_state(
        str(task.task_id),
        str(instance_file),
        task.instance_code,
        3,  # max_iterations（冒烟用最小修复预算，与 df 臂口径一致）
        module_name=module_name,
        target_function=suggested,
        problem_statement=getattr(task, "problem_statement", None),
    )
    state["gold_fixed_code"] = m1._gold_fixed_code(task)

    print(f"[smoke] task={task.task_id} module={module_name} suggested={suggested}", flush=True)
    t0 = time.time()
    final_state = rb.run_plain_llm_df_spec_baseline(state)
    wall_s = round(time.time() - t0, 3)
    print(f"[smoke] baseline done wall={wall_s}s", flush=True)

    row = rb._build_task_result(task, wall_s, final_state=final_state)
    generated_test = str(final_state.get("generated_test") or "")
    anchor = final_state.get("spec_anchor") or {}
    merge_verdict = final_state.get("spec_oracle_verdict")
    injection_ok = bool(final_state.get("spec_oracle_injected")) and merge_verdict in {
        "injected",
        "injected_and_passed",
        "injected_and_failed",
    }

    # ② 独立性对比：同一 generated_test 在 legacy 混判口径（不 -k 过滤）下的
    # detection —— 若 oracle 在 fixed 侧失败，legacy 会低于 LLM-suite 值。
    from experiments._m1_metrics import _compute_detection_rate

    llm_suite_detection = row.get("llm_suite_detection_rate")
    legacy_mixed_detection: float | None
    saved_filter = m1.llm_suite_keyword_filter
    try:
        m1.llm_suite_keyword_filter = lambda _generated: None  # type: ignore[assignment]
        legacy_mixed_detection = _compute_detection_rate(task, {"generated_test": generated_test})
    finally:
        m1.llm_suite_keyword_filter = saved_filter  # type: ignore[assignment]

    execution_trace = final_state.get("execution_trace") or []
    oracle_verdict = row.get("oracle_suite_verdict")
    checks = {
        "injection_occurred": injection_ok,
        "generated_test_contains_oracle": "test_specir_v2_oracle" in generated_test,
        "spec_anchor_present": bool(anchor),
        "spec_anchor_has_logic_analysis": isinstance(anchor.get("logic_analysis"), dict),
        "row_fields_present": all(
            key in row for key in ("detection_rate", "llm_suite_detection_rate", "oracle_suite_verdict", "spec_oracle_verdict")
        ),
        "oracle_suite_verdict_measurable": oracle_verdict in {"correct", "fp", "silent", "misguided"},
        "llm_suite_not_rewritten_by_oracle": (
            legacy_mixed_detection is None
            or llm_suite_detection is None
            or float(llm_suite_detection) >= float(legacy_mixed_detection)
        ),
        "trace_present": bool(execution_trace),
        "pdf_generated_test_present": bool(generated_test.strip()),
    }
    report = {
        "kind": "n3_real_llm_smoke",
        "evidence_status": "验证性冒烟，不作证据（≤3 次真实 LLM 调用）",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "task_id": task.task_id,
        "module_name": module_name,
        "model_name": _model_name(),
        "env_snapshot": _env_snapshot(),
        "wall_s": wall_s,
        "row": {
            "detection_rate": row.get("detection_rate"),
            "llm_suite_detection_rate": llm_suite_detection,
            "oracle_suite_verdict": oracle_verdict,
            "spec_oracle_injected": row.get("spec_oracle_injected"),
            "spec_oracle_verdict": row.get("spec_oracle_verdict"),
            "passed": row.get("passed"),
            "iterations": row.get("iterations"),
            "token_usage": row.get("token_usage"),
            "spec_replace_applied": row.get("spec_replace_applied"),
        },
        "independence_probe": {
            "llm_suite_detection": llm_suite_detection,
            "legacy_mixed_detection": legacy_mixed_detection,
            "oracle_suite_verdict": oracle_verdict,
            "note": (
                "legacy_mixed_detection = oracle 与 LLM 同文件混判（修复前口径）；"
                "llm_suite_detection = 独立判读 LLM-suite。oracle 在 fixed 侧失败时前者会被抹低。"
            ),
        },
        "anchor": {
            "function_name": anchor.get("function_name"),
            "has_human_spec": isinstance(anchor.get("human_spec"), str),
            "has_logic_analysis": isinstance(anchor.get("logic_analysis"), dict),
        },
        "execution_trace_entries": len(execution_trace) if isinstance(execution_trace, list) else 0,
        "checks": checks,
        "all_checks_pass": all(bool(value) for value in checks.values()),
        "limitations": [
            "单任务、单次运行；模型输出随机性与单任务代表性限制结论强度（验证性，不作证据）",
            "df_spec 臂入口直接调用（等价 run_benchmark 该臂路径），未落盘正式批次工件",
            "调用上限由外层 env AITESTER_BATCH_MAX_CALLS=3 硬约束；token 用量见 row.token_usage",
        ],
    }
    (out_dir / "ROW.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "SMOKE_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"checks": checks, "all_checks_pass": report["all_checks_pass"]}, ensure_ascii=False, indent=2))
    print(f"[smoke] report: {out_dir / 'SMOKE_REPORT.json'}", flush=True)
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0 if report["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
