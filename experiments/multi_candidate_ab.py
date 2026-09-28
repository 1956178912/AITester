"""
多候选补丁 A/B 对比实验脚本（评估 2026-09-25 §3.4 剩余工作）。

用途：
    跑多候选补丁 ON/OFF 对比，按错误类型（断言/运行时/导入/语法/未知）
    分析哪类收益最大，为论文提供实验数据。

设计口径（保守、零 LLM 成本）：
    - 复用 run_benchmark 的既有能力：ON 组显式启用
      `ENABLE_MULTI_CANDIDATE_PATCH=true`（+ 可选执行验证
      `MULTI_CANDIDATE_EXEC_VALIDATE=true`），OFF 组保持
      `ENABLE_MULTI_CANDIDATE_PATCH=false`（历史单补丁口径）；
    - 对比指标：按基线对齐的成功率 delta + 按错误类型分桶的
      失败占比 delta（哪类错误在 ON 组占比下降最多 = 多候选收益最大）；
    - 输出 Markdown 汇总（供论文引用）+ JSON 原始数据（可复算）。

使用方式：
    # 跑一组对比（examples 数据集，ON/OFF 各 N 任务）
    python experiments/multi_candidate_ab.py --dataset examples --task-count 20 --task-limit 20
    # 指定数据集与任务数
    python experiments/multi_candidate_ab.py --dataset synthetic --task-count 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 错误类型分桶（与 summarize_full_stack 同口径）
_ERROR_BUCKETS: tuple[str, ...] = ("assertion", "runtime", "import_error", "syntax", "unknown")


def _run_one_arm(
    dataset_name: str,
    task_limit: int | None,
    task_count: int | None,
    subset: str | None,
    output_dir: str,
    multi_candidate_on: bool,
    exec_validate: bool,
) -> dict[str, Any]:
    """跑一组（多候选 ON 或 OFF）benchmark，返回汇总 dict。

    Args:
        dataset_name: 数据集名（examples / synthetic / swe_bench_pro ...）。
        task_limit: 任务数上限。
        task_count: 合成数据集任务数。
        subset: 数据子集。
        output_dir: 结果输出目录。
        multi_candidate_on: 是否启用多候选补丁。
        exec_validate: 是否启用执行验证（仅 ON 组有意义）。

    Returns:
        benchmark 汇总 dict（results / token_metrics 等）。
    """
    from experiments.run_benchmark import run_benchmark

    prev_multi = os.environ.get("ENABLE_MULTI_CANDIDATE_PATCH")
    prev_exec = os.environ.get("MULTI_CANDIDATE_EXEC_VALIDATE")
    try:
        if multi_candidate_on:
            os.environ["ENABLE_MULTI_CANDIDATE_PATCH"] = "true"
            os.environ["MULTI_CANDIDATE_EXEC_VALIDATE"] = "true" if exec_validate else "false"
        else:
            os.environ["ENABLE_MULTI_CANDIDATE_PATCH"] = "false"
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
            enable_rag=False,  # A/B 口径：关 RAG，排除检索变量
            save_state=False,
            enable_mutation_scoring=False,
            difficulty="mixed",
        )
    finally:
        if prev_multi is not None:
            os.environ["ENABLE_MULTI_CANDIDATE_PATCH"] = prev_multi
        else:
            os.environ.pop("ENABLE_MULTI_CANDIDATE_PATCH", None)
        if prev_exec is not None:
            os.environ["MULTI_CANDIDATE_EXEC_VALIDATE"] = prev_exec
        else:
            os.environ.pop("MULTI_CANDIDATE_EXEC_VALIDATE", None)
    return summary


def _bucket_error_counts(summary: dict[str, Any]) -> Counter:
    """聚合一个 benchmark 的失败错误类型分桶计数（跨基线合计，仅 aiterester）。"""
    totals: Counter = Counter()
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        for row in bl.get("details", []):
            if not row.get("passed") and row.get("error_category"):
                category = str(row["error_category"]).lower()
                bucket = category if category in _ERROR_BUCKETS else "other"
                totals[bucket] += 1
    return totals


def _success_rate(summary: dict[str, Any]) -> float:
    """aitester 基线成功率（无 aiterester 基线时返回 0.0）。"""
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        total = bl.get("total_functions", 0)
        passed = bl.get("passed_count", 0)
        return round(passed / total * 100, 2) if total > 0 else 0.0
    return 0.0


def _render_markdown(on_summary: dict[str, Any], off_summary: dict[str, Any], output_dir: str) -> str:
    """渲染多候选 A/B 对比 Markdown（按基线对齐 + 按错误类型分桶）。"""
    on_rate = _success_rate(on_summary)
    off_rate = _success_rate(off_summary)
    delta = round(on_rate - off_rate, 2)
    on_buckets = _bucket_error_counts(on_summary)
    off_buckets = _bucket_error_counts(off_summary)
    on_total = sum(on_buckets.values()) or 1
    off_total = sum(off_buckets.values()) or 1

    lines = [
        "# 多候选补丁 A/B 对比汇总",
        "",
        f"- 数据集: {on_summary.get('dataset', '?')} (subset={on_summary.get('subset', 'None')})",
        f"- ON 组（多候选启用）成功率: {on_rate}%",
        f"- OFF 组（多候选关闭）成功率: {off_rate}%",
        f"- 成功率 delta (ON - OFF): {delta:+.2f}pp",
        "",
        "## 按错误类型分桶的失败占比对比",
        "",
        "| 错误桶 | OFF 占比 | ON 占比 | 占比 delta | 解读 |",
        "|--------|---------|--------|-----------|------|",
    ]
    any_positive = delta > 0
    for bucket in (*_ERROR_BUCKETS, "other"):
        off_count = off_buckets.get(bucket, 0)
        on_count = on_buckets.get(bucket, 0)
        off_pct = off_count / off_total * 100 if off_total > 0 else 0.0
        on_pct = on_count / on_total * 100 if on_total > 0 else 0.0
        bucket_delta = on_pct - off_pct
        if bucket_delta < -5:
            interpretation = f"⬇ 该桶失败占比下降 {abs(bucket_delta):.1f}pp（多候选收益最明显）"
        elif bucket_delta > 5:
            interpretation = f"⬆ 该桶失败占比上升 {bucket_delta:.1f}pp（需排查多候选是否引入新失败）"
        else:
            interpretation = "≈ 占比基本持平"
        lines.append(
            f"| {bucket} | {off_count} ({off_pct:.1f}%) | {on_count} ({on_pct:.1f}%) | {bucket_delta:+.1f}pp | {interpretation} |"
        )
    lines.append("")
    if any_positive:
        lines.append(f"> 结论：多候选补丁在 aiterester 基线上带来 {delta:+.2f}pp 成功率提升。")
    else:
        lines.append(f"> 结论：多候选补丁未带来正向成功率提升（delta {delta:+.2f}pp），需结合样本量解读。")
    lines.append("")

    md_path = os.path.join(output_dir, "multi_candidate_ab_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json_path = os.path.join(output_dir, "multi_candidate_ab_raw.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "on": {"success_rate": on_rate, "error_buckets": dict(on_buckets)},
                "off": {"success_rate": off_rate, "error_buckets": dict(off_buckets)},
                "delta_pp": delta,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[A/B] 汇总已写入: {md_path}")
    print(f"[A/B] 原始数据: {json_path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="多候选补丁 A/B 对比实验（ON/OFF + 按错误类型分桶）")
    parser.add_argument("--dataset", default="examples", help="数据集名称（默认 examples）")
    parser.add_argument("--subset", default=None, help="数据子集")
    parser.add_argument("--task-limit", type=int, default=None, help="每组任务数上限")
    parser.add_argument("--task-count", type=int, default=None, help="合成数据集任务数")
    parser.add_argument(
        "--output-dir", default=os.path.join(PROJECT_ROOT, "experiments", "results"), help="结果输出目录"
    )
    parser.add_argument("--no-exec-validate", action="store_true", help="ON 组禁用执行验证（仅静态筛选）")
    args = parser.parse_args()

    on_dir = os.path.join(args.output_dir, "multi_candidate_on")
    off_dir = os.path.join(args.output_dir, "multi_candidate_off")
    os.makedirs(on_dir, exist_ok=True)
    os.makedirs(off_dir, exist_ok=True)

    print("[A/B] 跑 OFF 组（多候选关闭，历史单补丁口径）...")
    off_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=off_dir,
        multi_candidate_on=False,
        exec_validate=False,
    )

    print("[A/B] 跑 ON 组（多候选启用）...")
    on_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        output_dir=on_dir,
        multi_candidate_on=True,
        exec_validate=not args.no_exec_validate,
    )

    _render_markdown(on_summary, off_summary, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
