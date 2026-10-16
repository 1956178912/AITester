"""批后离线 MDO 计算（政策无关变异判别力度量）。

**为什么是"批后离线"而不是跑批内联**（2026-10-11 设计修正）

把 MDO 挂在 `ENABLE_MUTATION_SCORING` 下内联计算时，实测一次 20 任务 × 2 臂
的跑批在**批后阶段**再多花 >15 分钟且未收敛（每个变异体要跑行为探针 + 测试，
共 2 次子进程执行）。而 MDO 依赖的输入（`generated_test`）**已经在结果行里**，
gold 材料可从数据集重取——因此把它做成**离线批后步骤**：
① 不拖慢跑批、不影响 LLM 阶段的可复现性；
② 池规模/超时可独立调参，无需重跑 LLM；
③ 同一批次可用不同池规模重复计算，做敏感性分析。

用法：
    .venv/bin/python -m experiments.mdo_posthoc \
        experiments/results/<批>/benchmark_*.json \
        --dataset quixbugs --max-mutants 120 --timeout 30 \
        --out experiments/results/<批>/mdo_report.md

产出：`mdo_report.md`（人读）+ `<batch>.mdo.json`（机读，逐行 MDO 字段）。
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.utils.atomic_io import atomic_write_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger(__name__)


def _load_tasks(dataset: str, data_dir: str | None) -> dict[str, Any]:
    """加载数据集任务（task_id → BenchmarkTask），供提取 gold 材料。"""
    from src.datasets.dataset_loader import load_dataset

    loader = load_dataset(dataset, data_dir=data_dir)
    return {t.task_id: t for t in loader.tasks}


def _mdo_for_row(row: dict[str, Any], tasks: dict[str, Any], generator: Any, timeout: int) -> dict[str, Any]:
    """对单行计算 MDO（基准 = gold 修复后代码；缺材料一律 fail-closed）。"""
    from experiments._m1_metrics import _extract_gold_material, _gold_fixed_code
    from src.measurement.mdo import compute_mdo

    task_id = str(row.get("task_id") or "")
    task = tasks.get(task_id)
    test_code = row.get("generated_test")
    out: dict[str, Any] = {
        "mdo_available": None,
        "mtr": None,
        "mdr": None,
        "mdo_crash_rate": None,
        "mdo_pool_size": None,
        "mdo_pool_floor_ok": None,
        "mdo_not_available_reason": None,
    }
    if task is None or not test_code:
        out["mdo_not_available_reason"] = "no_task_or_test"
        return out
    base_code = _gold_fixed_code(task)
    if not base_code.strip():
        out["mdo_not_available_reason"] = "no_gold_fixed_material"
        return out
    mat = _extract_gold_material(task)
    if mat is None:
        out["mdo_not_available_reason"] = "no_gold_material"
        return out
    try:
        pool = generator.generate(base_code)
        res = compute_mdo(
            base_code=base_code,
            test_code=str(test_code),
            module_name=str(mat[0]),
            mutants=pool,
            timeout_seconds=timeout,
        )
    except Exception:
        logger.warning("MDO 计算异常（task=%s）", task_id, exc_info=True)
        out["mdo_not_available_reason"] = "exception"
        return out
    payload = res.as_dict()
    out["mdo_available"] = payload["mdo_available"]
    out["mtr"] = payload["mtr"]
    out["mdr"] = payload["mdr"]
    out["mdo_crash_rate"] = payload["crash_rate"]
    out["mdo_pool_size"] = payload["mdo_pool_size"]
    out["mdo_pool_floor_ok"] = payload["mdo_pool_floor_ok"]
    out["mdo_not_available_reason"] = payload["mdo_not_available_reason"]
    return out


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按臂汇总 MDO（None 不计入分母——与项目 M1 口径一致）。"""
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_arm.setdefault(str(r.get("_arm") or "?"), []).append(r)
    summary: dict[str, Any] = {}
    for arm, rs in sorted(by_arm.items()):
        meas = [r for r in rs if r.get("mdo_available") is True]
        reasons: dict[str, int] = {}
        for r in rs:
            if r.get("mdo_available") is not True:
                key = str(r.get("mdo_not_available_reason") or "unknown")
                reasons[key] = reasons.get(key, 0) + 1
        entry: dict[str, Any] = {
            "n_rows": len(rs),
            "n_measurable": len(meas),
            "n_not_measurable": len(rs) - len(meas),
            "not_measurable_reasons": reasons,
        }
        for field in ("mtr", "mdr", "mdo_crash_rate", "mdo_pool_size"):
            vals = [r[field] for r in meas if r.get(field) is not None]
            entry[f"{field}_mean"] = round(statistics.mean(vals), 4) if vals else None
            entry[f"{field}_median"] = round(statistics.median(vals), 4) if vals else None
        entry["n_pool_floor_ok"] = sum(1 for r in meas if r.get("mdo_pool_floor_ok") is True)
        # 判别力缺口：触发到了但判不出的比例（1 - MDR/MTR）
        gaps = [1 - (r["mdr"] / r["mtr"]) for r in meas if r.get("mtr") and r.get("mdr") is not None and r["mtr"] > 0]
        entry["oracle_gap_mean"] = round(statistics.mean(gaps), 4) if gaps else None
        summary[arm] = entry
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="批后离线 MDO 计算（零 LLM）")
    ap.add_argument("batch", help="批次 JSON 路径（benchmark_*.json）")
    ap.add_argument("--dataset", default="quixbugs", help="数据集名（用于重取 gold 材料）")
    ap.add_argument("--data-dir", default=None, help="数据集目录（默认读环境变量/缓存）")
    ap.add_argument("--max-mutants", type=int, default=120, help="每任务变异体池上限")
    ap.add_argument("--timeout", type=int, default=30, help="单次子进程超时（秒）")
    ap.add_argument("--out", default=None, help="报告输出路径（默认与批次同目录）")
    ap.add_argument("--workers", type=int, default=8, help="并行度（每行内部为子进程，主进程几乎不占 CPU）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    batch_path = Path(args.batch)
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    results = batch.get("results") or {}
    if not results:
        print("批次无 results 段", file=sys.stderr)
        return 2

    logger.info("加载数据集 %s 的任务（提取 gold 材料）", args.dataset)
    tasks = _load_tasks(args.dataset, args.data_dir)
    logger.info("任务数 = %d", len(tasks))

    from experiments.mutation_testing import ExtendedMutationGenerator

    generator = ExtendedMutationGenerator(max_per_task=args.max_mutants)

    # 并行度说明：每行的计算是"多次子进程执行"（行为探针 + 测试），
    # 主进程几乎不占 CPU，因此线程池即可获得近线性加速。默认 8 路。
    jobs: list[tuple[str, dict[str, Any]]] = []
    for arm, payload in sorted(results.items()):
        details = payload.get("details") or []
        logger.info("臂 %s：%d 行", arm, len(details))
        jobs.extend((arm, r) for r in details if isinstance(r, dict))
    logger.info("待计算 %d 行（并行度 %d）", len(jobs), args.workers)

    def _one(job: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        arm, r = job
        mdo = _mdo_for_row(r, tasks, generator, args.timeout)
        return {
            "_arm": arm,
            "task_id": r.get("task_id"),
            "detection_rate": r.get("detection_rate"),
            "repair_rate": r.get("repair_rate"),
            "patch_plausible": r.get("patch_plausible"),
            "passed": r.get("passed"),
            "coverage": r.get("coverage"),
            "stop_reason": r.get("stop_reason"),
            **mdo,
        }

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows_out: list[dict[str, Any]] = list(pool.map(_one, jobs))

    summary = _summarize(rows_out)
    out_json = batch_path.with_suffix(".mdo.json")
    atomic_write_json(out_json, {"batch": str(batch_path), "summary": summary, "rows": rows_out}, indent=2, mode=0o644)

    lines: list[str] = []
    lines.append("# 批后 MDO 报告（政策无关变异判别力度量）\n")
    lines.append(f"- 批次：`{batch_path}`")
    lines.append(f"- 数据集：`{args.dataset}`（任务数 {len(tasks)}）")
    lines.append(f"- 池上限：{args.max_mutants}；单步超时：{args.timeout}s；生成器：ExtendedMutationGenerator")
    lines.append(
        "- 口径：基准 = **gold 修复后代码**；不可测一律 None（不计入分母）；`mdr` 判据 = 行为偏差 ∧ 断言失败\n"
    )
    lines.append("## 按臂汇总\n")
    lines.append(
        "| 臂 | 行数 | 可测 | 不可测 | MTR 均值 | **MDR 均值** | CRASH 均值 | 池中位 | 达池下限 | **oracle 缺口** |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for arm, e in summary.items():
        lines.append(
            f"| `{arm}` | {e['n_rows']} | {e['n_measurable']} | {e['n_not_measurable']} | "
            f"{e['mtr_mean']} | **{e['mdr_mean']}** | {e['mdo_crash_rate_mean']} | {e['mdo_pool_size_median']} | "
            f"{e['n_pool_floor_ok']} | {e['oracle_gap_mean']} |"
        )
    lines.append("\n> **oracle 缺口** = `1 − MDR/MTR`：测试**触发到了**行为偏差却**判不出来**的比例。")
    lines.append("> 该值越高说明瓶颈在断言（oracle）而非触发——与 arXiv:2609.09315 的诊断同构。\n")
    lines.append("## 不可测原因分布\n")
    for arm, e in summary.items():
        lines.append(f"- `{arm}`：{e['not_measurable_reasons']}")
    out_md = Path(args.out) if args.out else batch_path.with_suffix(".mdo.md")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    logger.info("机读结果 → %s", out_json)
    logger.info("人读报告 → %s", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
