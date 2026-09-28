"""跨文件修复（3.5 CROSS_FILE_ENABLE）A/B 对比实验脚手架。

对应 docs/design/cross_file_repair.md §"默认启用前置条件" 的 T1 / T4 验收标准：

    T1: 合成数据集跨文件任务（Level 3 双模块，--difficulty level3）
        CROSS_FILE_ENABLE=true 成功率相对 false 基线提升 ≥ +15pp（绝对值）。
    T4: 无回归——单文件任务（Level 1）开启 CROSS_FILE_ENABLE=true 后成功率
        不下降（下降 > 5pp 视为降级路径缺陷）。

设计口径（与 position_aware_ab.py 保持一致，保守、可复现）：
    - ON 组：CROSS_FILE_ENABLE=true（cross_file_analyzer 节点 + 多文件补丁分支）；
    - OFF 组：CROSS_FILE_ENABLE=false（历史单文件口径）；
    - 指标：成功率 delta + 平均迭代 delta + T1/T4 阈值判定；
    - 输出 Markdown 汇总（供论文引用）+ JSON 原始数据。

使用方式：
    python experiments/cross_file_ab.py --dataset synthetic --difficulty level3 --task-count 50
    python experiments/cross_file_ab.py --dataset synthetic --difficulty level1 --task-count 50
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

# T1 / T4 验收阈值（docs/design/cross_file_repair.md §"默认启用前置条件"）
T1_MIN_DELTA_PP = 15.0  # level3: ON 成功率 - OFF 成功率 最小提升（绝对值 pp）
T4_MAX_DROP_PP = 5.0  # level1: ON 相对 OFF 的最大允许下降（pp）


def _run_one_arm(
    dataset_name: str,
    task_limit: int | None,
    task_count: int | None,
    subset: str | None,
    difficulty: str,
    output_dir: str,
    cross_file_on: bool,
) -> dict[str, Any]:
    """跑一组（跨文件 ON 或 OFF）benchmark，返回汇总 dict。"""
    from experiments.run_benchmark import run_benchmark

    prev = os.environ.get("CROSS_FILE_ENABLE")
    try:
        os.environ["CROSS_FILE_ENABLE"] = "true" if cross_file_on else "false"
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
            save_state=True,
            enable_mutation_scoring=False,
            difficulty=difficulty,
        )
    finally:
        if prev is not None:
            os.environ["CROSS_FILE_ENABLE"] = prev
        else:
            os.environ.pop("CROSS_FILE_ENABLE", None)
    return summary


def _success_rate(summary: dict[str, Any]) -> float:
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        total = bl.get("total_functions", 0)
        passed = bl.get("passed_count", 0)
        return round(passed / total * 100, 2) if total > 0 else 0.0
    return 0.0


def _avg_iterations(summary: dict[str, Any]) -> float:
    for baseline, bl in summary.get("results", {}).items():
        if baseline != "aitester":
            continue
        return float(bl.get("avg_iterations") or 0.0)
    return 0.0


def _render_markdown(
    on_summary: dict[str, Any],
    off_summary: dict[str, Any],
    difficulty: str,
    output_dir: str,
) -> str:
    """渲染跨文件 A/B 对比 Markdown。"""
    on_rate = _success_rate(on_summary)
    off_rate = _success_rate(off_summary)
    on_iter = _avg_iterations(on_summary)
    off_iter = _avg_iterations(off_summary)
    delta_pp = round(on_rate - off_rate, 2)

    lines = [
        "# CROSS_FILE_ENABLE A/B 对比汇总",
        "",
        f"- 数据集: {on_summary.get('dataset', '?')} (difficulty={difficulty})",
        f"- ON 组（跨文件修复启用）成功率: {on_rate}%",
        f"- OFF 组（单文件历史口径）成功率: {off_rate}%",
        f"- 成功率 delta (ON - OFF): {delta_pp:+.2f}pp",
        f"- 平均迭代 ON: {on_iter:.2f} / OFF: {off_iter:.2f}",
        "",
        "## 验收判定",
        "",
    ]
    if difficulty == "level3":
        passed = delta_pp >= T1_MIN_DELTA_PP
        lines.append(
            f"- **T1（跨文件提升 ≥ +{T1_MIN_DELTA_PP:.0f}pp）**: "
            + ("✅ 通过" if passed else f"❌ 未通过（实测 {delta_pp:+.2f}pp）")
        )
    elif difficulty == "level1":
        dropped = delta_pp < -T4_MAX_DROP_PP
        lines.append(
            f"- **T4（单文件无回归，下降 ≤ {T4_MAX_DROP_PP:.0f}pp）**: "
            + ("❌ 未通过（降级路径缺陷）" if dropped else f"✅ 通过（实测 {delta_pp:+.2f}pp）")
        )
    else:
        lines.append(f"- 难度 {difficulty} 无预设验收阈值，仅记录 delta。")
    lines.append("")

    md_path = os.path.join(output_dir, "cross_file_ab_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json_path = os.path.join(output_dir, "cross_file_ab_raw.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "difficulty": difficulty,
                "on": {"success_rate": on_rate, "avg_iterations": on_iter},
                "off": {"success_rate": off_rate, "avg_iterations": off_iter},
                "delta_pp": delta_pp,
                "t1_pass": (delta_pp >= T1_MIN_DELTA_PP) if difficulty == "level3" else None,
                "t4_pass": (not (delta_pp < -T4_MAX_DROP_PP)) if difficulty == "level1" else None,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[A/B] 汇总已写入: {md_path}")
    print(f"[A/B] 原始数据: {json_path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="CROSS_FILE_ENABLE A/B 对比实验")
    parser.add_argument("--dataset", default="synthetic", help="数据集名称（默认 synthetic）")
    parser.add_argument("--subset", default=None, help="数据子集")
    parser.add_argument("--task-limit", type=int, default=None, help="每组任务数上限")
    parser.add_argument("--task-count", type=int, default=50, help="合成数据集任务数（默认 50）")
    parser.add_argument(
        "--difficulty",
        default="level3",
        choices=["level1", "level2", "level3", "level4", "mixed"],
        help="合成数据集难度层级（默认 level3 跨文件；level1 用于 T4 无回归检查）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="结果输出目录（默认按 difficulty 命名：experiments/results/cross_file_ab_<difficulty>）",
    )
    args = parser.parse_args()

    if not args.output_dir:
        args.output_dir = os.path.join(PROJECT_ROOT, "experiments", "results", f"cross_file_ab_{args.difficulty}")
    on_dir = os.path.join(args.output_dir, "cross_file_on")
    off_dir = os.path.join(args.output_dir, "cross_file_off")
    os.makedirs(on_dir, exist_ok=True)
    os.makedirs(off_dir, exist_ok=True)

    print(f"[A/B] 跑 OFF 组（跨文件关闭，difficulty={args.difficulty}）...")
    off_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        difficulty=args.difficulty,
        output_dir=off_dir,
        cross_file_on=False,
    )

    print(f"[A/B] 跑 ON 组（跨文件启用，difficulty={args.difficulty}）...")
    on_summary = _run_one_arm(
        dataset_name=args.dataset,
        task_limit=args.task_limit,
        task_count=args.task_count,
        subset=args.subset,
        difficulty=args.difficulty,
        output_dir=on_dir,
        cross_file_on=True,
    )

    _render_markdown(on_summary, off_summary, args.difficulty, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
