#!/usr/bin/python3
"""F2 论文数据底稿：新批全口径聚合（血统去重，观测不到不计 0 分母）。

输出 experiments/results/RESULTS_DATA_PACK_20261111.json
口径：
- 来源白名单：只扫描 SOURCE_ROOTS 内登记的正式批次目录；冒烟/临时目录
  （test_run_*_smoke）一律不入，避免其同名 cell×task_id 按「取最新行」覆盖主批。
- 血统去重：cell×task_id 取最新文件行；诊断通道（verify/retry6/probe）不入。
- swebench harness_invalid 不入判定分母（结构性，独立披露）。
- 逐指标 n_obs：只有实际观测到该字段的任务才计入均值。
"""

from __future__ import annotations

import glob
import json
from collections import defaultdict
from pathlib import Path

# 从脚本位置推导仓库根，保证 fresh clone / 任意路径下都能零 LLM 复算。
ROOT = Path(__file__).resolve().parents[2]

# 正式批次目录白名单（与稿件 Appendix B 的三个登记目录一致）。禁止改回
# experiments/results/** 全盘递归：H2 冒烟在同一 cell×task_id 上重写行，血统去重
# 会把它们当成「最新」而替换主批读数（2026-11-11 实测把 aitester/quixbugs 从
# 26/50 抬到 27/50、passed 从 711 抬到 712，BugsInPy 一格 token 被静默改写）。
# v1--v4 中间重跑目录不登记：其行在血统去重后被 v5/corrected 全部覆盖，
# 实测 6,377 行逐行零差异，登记反而扩大未来被污染的面。
SOURCE_ROOTS = (
    "experiments/results/test_run_20261106T101605Z",  # 主批 50 格
    "experiments/results/rerun_swebench_20261110",  # SWE-bench 补充
    "experiments/results/rerun_testgeneval_20261110_v5",  # TestGenEval corrected 终版
)
DIAGNOSTIC_MARKERS = ("/verify/", "/retry6/", "/probe/")

NUMERIC = {
    "coverage": "mean",
    "false_fix_rate": "mean",
    "detection_rate": "mean",
    "llm_suite_detection_rate": "mean",
    "mdr": "mean",
    "mtr": "mean",
    "repair_rate": "mean",
    "regression_rate": "mean",
    "patch_precision": "mean",
    "fl_at_k": "mean",
    "localization_mrr": "mean",
    "localization_hit_function": "mean",
    "localization_hit_function_at_3": "mean",
    "test_error_rate": "mean",
    "iterations": "mean",
    "elapsed_seconds": "mean",
}
BOOL_COUNTS = [
    "patch_correct",
    "patch_validated",
    "patch_rolled_back",
    "patch_abstained",
    "test_hacking_suspected",
    "self_repair_trap_suspected",
    "flaky_detected",
    "patch_plausible",
    "harness_invalid",
    "test_regenerated_pass_unverified",
    "source_patched_unverified",
    "red_regression_violation",
]

official_files: list[str] = []
for root in SOURCE_ROOTS:
    if not (ROOT / root).is_dir():
        raise SystemExit(f"official source root missing: {root}")
    official_files.extend(glob.glob(str(ROOT / root / "**/llm_sweep/*/INCREMENTAL_RESULTS.jsonl"), recursive=True))
official_files = sorted(f for f in official_files if not any(m in f for m in DIAGNOSTIC_MARKERS))
ignored_smoke = glob.glob(
    str(ROOT / "experiments/results/test_run_*_smoke/**/INCREMENTAL_RESULTS.jsonl"),
    recursive=True,
)
print(
    f"scanned {len(official_files)} official files from {len(SOURCE_ROOTS)} "
    f"whitelisted roots; ignored {len(ignored_smoke)} smoke result files"
)

lineage: dict[tuple, dict] = defaultdict(dict)
for f in official_files:
    cell = Path(f).parent.name
    with open(f, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    for line in lines:
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = r.get("task_id")
        if not tid:
            continue
        for arm, x in (r.get("results") or {}).items():
            if isinstance(x, dict):
                lineage[(cell, arm)][tid] = x

pack = {
    "generated_at": "2026-11-11",
    "caliber": "血统去重 cell×task_id 取最新行；观测不到不计 0 分母（逐指标 n_obs）；harness_invalid 不入判定分母",
}
cells = {}
for (cell, arm), tasks in lineage.items():
    model, ds = cell.split("__")[0], cell.split("__")[2]
    key = f"{model}__{arm}__{ds}"
    c = cells.setdefault(
        key,
        {
            "model": model,
            "dataset": ds,
            "arm": arm,
            "tasks_total": len(tasks),
            "judged": 0,
            "passed": 0,
            "failed": 0,
            "harness_invalid": 0,
            "tokens_total": 0,
            "calls_total": 0,
            "metrics": {k: {"n": 0, "sum": 0.0} for k in NUMERIC},
            "bools": {k: 0 for k in BOOL_COUNTS},
        },
    )
    for x in tasks.values():
        d = str(x.get("diagnosis") or "")
        is_harness = (
            ("harness_invalid" in d) or x.get("error_category") == "harness_invalid" or x.get("harness_invalid") is True
        )
        if is_harness:
            c["harness_invalid"] += 1
            c["tokens_total"] += (x.get("token_usage") or {}).get("total_tokens") or 0
            c["calls_total"] += (x.get("token_usage") or {}).get("llm_calls") or 0
            continue
        c["judged"] += 1
        if x.get("passed") is True:
            c["passed"] += 1
        elif x.get("passed") is False:
            c["failed"] += 1
        tu = x.get("token_usage") or {}
        c["tokens_total"] += tu.get("total_tokens") or 0
        c["calls_total"] += tu.get("llm_calls") or 0
        for k in NUMERIC:
            v = x.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                c["metrics"][k]["n"] += 1
                c["metrics"][k]["sum"] += float(v)
        for k in BOOL_COUNTS:
            if x.get(k) is True:
                c["bools"][k] += 1

for c in cells.values():
    c["first_pass_rate"] = round(c["passed"] / c["judged"], 4) if c["judged"] else None
    for st in c["metrics"].values():
        st["mean"] = round(st["sum"] / st["n"], 4) if st["n"] else None

pack["cells"] = dict(sorted(cells.items()))

# 数据集 × 臂 汇总（跨模型）
by_ds_arm = defaultdict(lambda: {"judged": 0, "passed": 0, "harness": 0, "tokens": 0})
for c in cells.values():
    k = (c["dataset"], c["arm"])
    b = by_ds_arm[k]
    b["judged"] += c["judged"]
    b["passed"] += c["passed"]
    b["harness"] += c["harness_invalid"]
    b["tokens"] += c["tokens_total"]
pack["by_dataset_arm"] = {
    f"{ds}__{arm}": {"first_pass_rate": round(v["passed"] / v["judged"], 4) if v["judged"] else None, **v}
    for (ds, arm), v in sorted(by_ds_arm.items())
}
# 模型 × 数据集 汇总（跨臂：全管aitester vs 消融均值放 md 再算）
by_model_ds = defaultdict(lambda: {"judged": 0, "passed": 0, "harness": 0, "tokens": 0})
for c in cells.values():
    k = (c["model"], c["dataset"])
    b = by_model_ds[k]
    b["judged"] += c["judged"]
    b["passed"] += c["passed"]
    b["harness"] += c["harness_invalid"]
    b["tokens"] += c["tokens_total"]
pack["by_model_dataset"] = {
    f"{m}__{ds}": {"first_pass_rate": round(v["passed"] / v["judged"], 4) if v["judged"] else None, **v}
    for (m, ds), v in sorted(by_model_ds.items())
}
out = ROOT / "experiments/results/RESULTS_DATA_PACK_20261111.json"
out.write_text(json.dumps(pack, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
print("written", out, "| cells:", len(cells))
