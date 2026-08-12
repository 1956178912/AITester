"""
实验结果可视化脚本：读取 benchmark JSON 结果，生成对比图表。
输出：
- experiments/results/charts/baseline_comparison.png（柱状图对比）
- experiments/results/charts/results_table.csv（详细数据表格）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")  # 无 GUI 环境下的后端
import matplotlib.pyplot as plt
import pandas as pd

# 中文字体支持
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RESULTS_DIR = "experiments/results"
CHARTS_DIR = os.path.join(RESULTS_DIR, "charts")


def load_latest_result(results_dir: str = RESULTS_DIR) -> str:
    """
    找到最新的 benchmark JSON 结果文件。
    按文件名排序（时间戳格式），取最后一个。

    Args:
        results_dir: 结果目录路径。

    Returns:
        最新结果文件的完整路径。

    Raises:
        FileNotFoundError: 结果目录下没有 JSON 文件时抛出。
    """
    files = sorted(
        [f for f in os.listdir(results_dir) if f.endswith(".json")],
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"结果目录 {results_dir} 下没有找到 JSON 文件")
    return os.path.join(results_dir, files[0])


def plot_baseline_comparison(summary: Dict[str, Any]) -> None:
    """
    绘制各基线方法的对比柱状图（成功率、平均覆盖率、平均迭代次数）。
    三个子图并排显示，便于直观对比。

    Args:
        summary: benchmark 汇总结果字典。
    """
    baselines = list(summary["results"].keys())
    success_rates = [summary["results"][bl]["success_rate"] for bl in baselines]
    coverages = [summary["results"][bl]["avg_coverage"] for bl in baselines]
    iterations = [summary["results"][bl]["avg_iterations"] for bl in baselines]

    x = range(len(baselines))
    width = 0.25

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # 成功率柱状图
    bars1 = axes[0].bar(x, success_rates, width, color="#4C72B0")
    axes[0].set_title("测试成功率 (%)", fontsize=12)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(baselines, rotation=15, ha="right")
    axes[0].set_ylim(0, 100)
    for bar, val in zip(bars1, success_rates):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                      f"{val:.1f}", ha="center", va="bottom", fontsize=9)

    # 平均覆盖率柱状图
    bars2 = axes[1].bar([xi + width for xi in x], coverages, width, color="#55A868")
    axes[1].set_title("平均覆盖率 (%)", fontsize=12)
    axes[1].set_xticks([xi + width for xi in x])
    axes[1].set_xticklabels(baselines, rotation=15, ha="right")
    axes[1].set_ylim(0, 100)
    for bar, val in zip(bars2, coverages):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                      f"{val:.1f}", ha="center", va="bottom", fontsize=9)

    # 平均迭代次数柱状图
    bars3 = axes[2].bar([xi + width * 2 for xi in x], iterations, width, color="#C44E52")
    axes[2].set_title("平均修复迭代", fontsize=12)
    axes[2].set_xticks([xi + width * 2 for xi in x])
    axes[2].set_xticklabels(baselines, rotation=15, ha="right")
    for bar, val in zip(bars3, iterations):
        axes[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                      f"{val:.1f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, "baseline_comparison.png"), dpi=150)
    plt.close()
    print(f"图表已保存: baseline_comparison.png")


def plot_detail_table(summary: Dict[str, Any]) -> None:
    """
    生成详细结果表格（CSV 格式），便于论文引用。
    表格包含成功率、覆盖率、迭代次数、执行时间等关键指标。

    Args:
        summary: benchmark 汇总结果字典。
    """
    rows = []
    for bl, data in summary["results"].items():
        rows.append({
            "baseline": bl,
            "total_functions": data["total_functions"],
            "passed": data["passed_count"],
            "failed": data["failure_count"],
            "success_rate_pct": data["success_rate"],
            "avg_coverage_pct": data["avg_coverage"],
            "avg_iterations": data["avg_iterations"],
            "avg_time_s": data["avg_elapsed_seconds"],
            "total_time_s": data["total_time"],
        })

    df = pd.DataFrame(rows)
    csv_path = os.path.join(CHARTS_DIR, "results_table.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"结果表格已保存: results_table.csv")
    print(df.to_string(index=False))


def main() -> None:
    """主入口：加载最新结果并生成所有可视化输出。"""
    os.makedirs(CHARTS_DIR, exist_ok=True)

    result_file = load_latest_result()
    print(f"加载结果: {result_file}")

    with open(result_file, "r", encoding="utf-8") as f:
        summary = json.load(f)

    plot_baseline_comparison(summary)
    plot_detail_table(summary)

    print("\n可视化完成，图表保存在:", CHARTS_DIR)


if __name__ == "__main__":
    main()
