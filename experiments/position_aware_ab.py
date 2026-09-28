"""
position_aware_focus A/B 对比实验脚本（评估 2026-09-25 §3.3 剩余工作）。

用途：
    跑 position_aware_focus（位置感知迭代修复）ON/OFF 对比，
    分析"先定位后补丁"策略对修复成功率 / 修复轮次 / 定位正确率
    的影响，为论文提供实验数据。

设计口径（保守、零 LLM 成本）：
    - ON 组：`POSITION_AWARE_REPAIR_ENABLE=true`（先定位后补丁，
      traceback 行号 + AST 定位"包围异常行的最短区间函数"）；
    - OFF 组：`POSITION_AWARE_REPAIR_ENABLE=false`（历史全文件修复口径）；
    - 指标：成功率 delta + 平均迭代 delta + 定位正确率
      （state["position_aware_focus"]["function_name"] 命中
      gold suggested_function 的比例，仅 ON 组有意义）；
    - 输出 Markdown 汇总（供论文引用）+ JSON 原始数据。

使用方式：
    python experiments/position_aware_ab.py --dataset examples --task-count 20
    python experiments/position_aware_ab.py --dataset synthetic --task-count 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run_one_arm(
    dataset_name: str,
    task_limit: int | None,
    task_count: int | None,
    subset: str | None,
    output_dir: str,
    position_aware_on: bool,
) -> dict[str, Any]:
    """跑一组（位置感知 ON 或 OFF）benchmark，返回汇总 dict。

    Args:
        dataset_name: 数据集名。
        task_limit: 任务数上限。
        task_count: 合成数据集任务数。
        subset: 数据子集。
        output_dir: 结果输出目录。
        position_aware_on: 是否启用位置感知修复。

    Returns:
        benchmark 汇总 dict。
    """
    from experiments.run_benchmark import run_benchmark

    prev = os.environ.get("POSITION_AWARE_REPAIR_ENABLE")
    try:
        os.environ["POSITION_AWARE_REPAIR_ENABLE"] = "true" if position_aware_on else "false"
        summary = run_benchmark(
            dataset_name=dataset_name,
            subset=subset,
            baselines=["aitester"],
            output_dir=output_dir,
            verbose=False,
            task_limit=task_limit,
            task_count=task_count,
            parallel=None,
            seed=42,
            enable_rag=False,
            save_state=True,  # 需 save_state 才能拿到 position_aware_focus 状态
            enable_mutation_scoring=False,
            difficulty="mixed",
        )
    finally:
        if prev is not None:
            os.environ["POSITION_AWARE_REPAIR_ENABLE"] = prev
        else:
            os.environ.pop("POSITION_AWARE_REPAIR_ENABLE", None)
    return summary


def _success_rate(summary: dict[str, Any]) -> float:
    """aitester 基线成功率。"""
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        total = bl.get("total_functions", 0)
        passed = bl.get("passed_count", 0)
        return round(passed / total * 100, 2) if total > 0 else 0.0
    return 0.0


def _avg_iterations(summary: dict[str, Any]) -> float:
    """aitester 基线平均迭代次数。"""
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        return float(bl.get("avg_iterations") or 0.0)
    return 0.0


def _locate_accuracy(output_dir: str, summary: dict[str, Any]) -> float:
    """定位正确率：position_aware_focus.function_name 命中 gold suggested_function 的比例。

    仅 ON 组有意义（OFF 组 position_aware_focus 恒 focused=False，正确率 0.0）。
    通过 save_state 落盘的 raw/<task_id>/aitester.json 读取。
    """
    raw_dir = os.path.join(output_dir, "raw")
    if not os.path.isdir(raw_dir):
        return 0.0
    # 逐 task 读取：details 是 aiterster 基线结果列表（每项含 task_id）；
    # 兼容 details 缺失 / 非 list 两种旧 JSON 形态（保守 0.0 不崩溃）。
    details = summary.get("results", {}).get("aitester", {}).get("details")
    if not isinstance(details, list):
        return 0.0
    total = 0
    hit = 0
    for row in details:
        if not isinstance(row, dict):
            continue
        task_id = row.get("task_id")
        if not task_id:
            continue
        task_dir = os.path.join(raw_dir, task_id)
        if not os.path.isdir(task_dir):
            continue
        state_file = os.path.join(task_dir, "aitester.json")
        if not os.path.exists(state_file):
            continue
        try:
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        focus = state.get("position_aware_focus") or {}
        if not focus.get("focused"):
            continue
        total += 1
        gold = (state.get("task_metadata") or {}).get("suggested_function")
        located = focus.get("function_name")
        if gold and located and located == gold:
            hit += 1
    return round(hit / total * 100, 2) if total > 0 else 0.0


def _render_markdown(
    on_summary: dict[str, Any], off_summary: dict[str, Any], on_dir: str, off_dir: str, output_dir: str
) -> str:
    """渲染位置感知 A/B 对比 Markdown。"""
    on_rate = _success_rate(on_summary)
    off_rate = _success_rate(off_summary)
    on_iter = _avg_iterations(on_summary)
    off_iter = _avg_iterations(off_summary)
    on_locate = _locate_accuracy(on_dir, on_summary)
    off_locate = _locate_accuracy(off_dir, off_summary)
    rate_delta = round(on_rate - off_rate, 2)
    iter_delta = round(on_iter - off_iter, 2)

    lines = [
        "# position_aware_focus A/B 对比汇总",
        "",
        f"- 数据集: {on_summary.get('dataset', '?')} (subset={on_summary.get('subset', 'None')})",
        f"- ON 组（位置感知启用）成功率: {on_rate}%",
        f"- OFF 组（位置感知关闭）成功率: {off_rate}%",
        f"- 成功率 delta (ON - OFF): {rate_delta:+.2f}pp",
        f"- 平均迭代 ON: {on_iter:.2f} / OFF: {off_iter:.2f}（delta {iter_delta:+.2f}）",
        f"- 定位正确率（ON 组 focused 命中 gold function）: {on_locate}%",
        f"- 定位正确率（OFF 组，恒 0）: {off_locate}%",
        "",
        "## 解读",
        "",
    ]
    if rate_delta > 0:
        lines.append(f"- 位置感知修复带来 {rate_delta:+.2f}pp 成功率提升。")
    elif rate_delta < 0:
        lines.append(f"- 位置感知修复导致 {abs(rate_delta):.2f}pp 成功率下降（需排查定位误判）。")
    else:
        lines.append("- 位置感知修复未改变成功率（样本量小时结论保守解读）。")
    if iter_delta < 0:
        lines.append(f"- 平均迭代下降 {abs(iter_delta):.2f}（定位正确时减少无效修复轮次）。")
    elif iter_delta > 0:
        lines.append(f"- 平均迭代上升 {iter_delta:.2f}（定位引入额外定位开销或误判）。")

    md_path = os.path.join(output_dir, "position_aware_ab_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json_path = os.path.join(output_dir, "position_aware_ab_raw.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "on": {"success_rate": on_rate, "avg_iterations": on_iter, "locate_accuracy_pct": on_locate},
                "off": {"success_rate": off_rate, "avg_iterations": off_iter, "locate_accuracy_pct": off_locate},
                "rate_delta_pp": rate_delta,
                "iter_delta": iter_delta,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[A/B] 汇总已写入: {md_path}")
    print(f"[A/B] 原始数据: {json_path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="position_aware_focus A/B 对比实验")
    parser.add_argument("--dataset", default="examples", help="数据集名称（默认 examples）")
    parser.add_argument("--subset", default=None, help="数据子集")
    parser.add_argument("--task-limit", type=int, default=None, help="每组任务数上限")
    parser.add_argument("--task-count", type=int, default=None, help="合成数据集任务数")
    parser.add_argument(
        "--output-dir", default=os.path.join(PROJECT_ROOT, "experiments", "results"), help="结果输出目录"
    )
    args = parser.parse_args()

    on_dir = os.path.join(args.output_dir, "position_aware_on")
    off_dir = os.path.join(args.output_dir, "position_aware_off")
    os.makedirs(on_dir, exist_ok=True)
    os.makedirs(off_dir, exist_ok=True)

    print("[A/B] 跑 OFF 组（位置感知关闭，历史全文件修复口径）...")
    off_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=off_dir,
        position_aware_on=False,
    )

    print("[A/B] 跑 ON 组（位置感知启用）...")
    on_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=on_dir,
        position_aware_on=True,
    )

    _render_markdown(on_summary, off_summary, on_dir, off_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
