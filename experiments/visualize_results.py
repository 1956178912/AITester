"""
实验结果可视化脚本：读取 benchmark JSON 结果，生成对比图表与统计显著性检验。
输出：
  - experiments/results/charts/baseline_comparison.png（柱状图对比）
  - experiments/results/charts/statistical_significance.png（统计检验结果）
  - experiments/results/charts/results_table.csv（详细数据表格）
  - experiments/results/charts/summary_stats.md（Markdown 汇总报告）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")  # 无 GUI 环境下的后端
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats as scipy_stats

# 中文字体支持
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "SimHei", "DejaVu Sans"]
# axes.unicode_minus=False 解决负号显示为方块的问题
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10
plt.rcParams["figure.dpi"] = 150
# bbox="tight" 裁剪图表边缘空白，避免保存时截断坐标轴标签
plt.rcParams["savefig.bbox"] = "tight"

RESULTS_DIR = "experiments/results"
CHARTS_DIR = os.path.join(RESULTS_DIR, "charts")
_charts_dir = CHARTS_DIR  # 由 main() 动态设置


def load_latest_result(results_dir: str = RESULTS_DIR) -> str:
    """找到最新的 benchmark JSON 结果文件。"""
    files = sorted(
        [f for f in os.listdir(results_dir) if f.endswith(".json")],
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"结果目录 {results_dir} 下没有找到 JSON 文件")
    return os.path.join(results_dir, files[0])


# ─── 统计检验辅助函数 ────────────────────────────────────────────────────────────


def _interpret_p(p: float) -> str:
    """根据 p 值返回显著性标记。"""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


def _interpret_d(d: float) -> str:
    """根据 Cohen's d 返回效应量描述。"""
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


def compute_significance(summary: dict[str, Any]) -> dict[str, Any]:
    """
    对所有基线两两配对，进行统计显著性检验。

    使用每任务的通过率（0/1）作为样本，计算配对 t 检验和 Mann-Whitney U 检验，
    同时给出 Cohen's d 效应量，以量化提升幅度。

    Args:
        summary: benchmark 汇总结果字典。

    Returns:
        {
            "pairwise": [(bl_a, bl_b, t_stat, p_val, u_stat, mw_p, d, sig), ...],
            "per_baseline": {bl: {"mean_rate", "std_rate", "n"}}
        }
    """
    baselines = list(summary["results"].keys())
    details_map = {bl: summary["results"][bl]["details"] for bl in baselines}

    # 收集所有任务的 task_id，用于配对比较（同一任务在不同基线上的表现对比）
    all_task_ids: set[str] = set()
    for bl_details in details_map.values():
        all_task_ids.update(r["task_id"] for r in bl_details)
    all_task_ids = sorted(all_task_ids)

    # 构建每基线按 task_id 索引的通过率表（1.0=通过，0.0=失败）
    rate_by_task: dict[str, dict[str, float]] = {}
    for bl in baselines:
        rate_by_task[bl] = {r["task_id"]: (1.0 if r["passed"] else 0.0) for r in details_map[bl]}

    # 各基线汇总统计
    per_baseline: dict[str, dict[str, float]] = {}
    for bl in baselines:
        rates = [v for v in rate_by_task[bl].values()]
        n = len(rates)
        mean_r = sum(rates) / n if n else 0.0
        std_r = (sum((r - mean_r) ** 2 for r in rates) / (n - 1)) ** 0.5 if n > 1 else 0.0
        per_baseline[bl] = {
            "mean_rate": round(mean_r * 100, 1),
            "std_rate": round(std_r * 100, 1),
            "n": n,
        }

    # 两两配对检验：以第一个基线（通常 aitester）为参照，与其他基线逐一比较
    pairwise = []
    if len(baselines) >= 2:
        ref = baselines[0]  # 以 aitester 为主基线，对比其他方法的相对提升
        ref_rates = [rate_by_task[ref].get(tid, 0.0) for tid in all_task_ids]

        for bl in baselines[1:]:
            cmp_rates = [rate_by_task[bl].get(tid, 0.0) for tid in all_task_ids]
            n_pairs = len(ref_rates)

            # 配对 t 检验
            t_stat, p_val = scipy_stats.ttest_rel(ref_rates, cmp_rates, nan_policy="omit")
            # Mann-Whitney U 检验（非参数）
            u_stat, mw_p = scipy_stats.mannwhitneyu(ref_rates, cmp_rates, alternative="two-sided")
            # Cohen's d（配对差值的标准化均值）
            diffs = [r - c for r, c in zip(ref_rates, cmp_rates, strict=False)]
            mean_diff = sum(diffs) / n_pairs if n_pairs else 0.0
            std_diff = (sum((d - mean_diff) ** 2 for d in diffs) / (n_pairs - 1)) ** 0.5 if n_pairs > 1 else 1.0
            d = mean_diff / std_diff if std_diff > 0 else 0.0

            sig = _interpret_p(p_val)
            pairwise.append(
                (
                    ref,
                    bl,
                    round(t_stat, 3),
                    round(p_val, 4),
                    round(u_stat, 1),
                    round(mw_p, 4),
                    round(d, 3),
                    sig,
                    _interpret_d(d),
                )
            )

    return {"pairwise": pairwise, "per_baseline": per_baseline, "n_tasks": len(all_task_ids)}


# ─── 图表绘制 ────────────────────────────────────────────────────────────────────


def plot_baseline_comparison(summary: dict[str, Any]) -> None:
    """绘制三个并排柱状图：成功率、平均覆盖率、平均迭代次数，便于直观对比基线优劣。"""
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
    for bar, val in zip(bars1, success_rates, strict=False):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{val:.1f}", ha="center", va="bottom", fontsize=9
        )

    # 平均覆盖率柱状图
    bars2 = axes[1].bar([xi + width for xi in x], coverages, width, color="#55A868")
    axes[1].set_title("平均覆盖率 (%)", fontsize=12)
    axes[1].set_xticks([xi + width for xi in x])
    axes[1].set_xticklabels(baselines, rotation=15, ha="right")
    axes[1].set_ylim(0, 100)
    for bar, val in zip(bars2, coverages, strict=False):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{val:.1f}", ha="center", va="bottom", fontsize=9
        )

    # 平均迭代次数柱状图
    bars3 = axes[2].bar([xi + width * 2 for xi in x], iterations, width, color="#C44E52")
    axes[2].set_title("平均修复迭代", fontsize=12)
    axes[2].set_xticks([xi + width * 2 for xi in x])
    axes[2].set_xticklabels(baselines, rotation=15, ha="right")
    for bar, val in zip(bars3, iterations, strict=False):
        axes[2].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    plt.tight_layout()
    plt.savefig(os.path.join(_charts_dir, "baseline_comparison.png"), dpi=150)
    plt.close()
    print("图表已保存: baseline_comparison.png")


def plot_statistical_significance(sig_result: dict[str, Any]) -> None:
    """
    绘制统计检验结果：p 值热力图 + Cohen's d 效应量柱状图。
    仅在有至少 2 个基线时生成。
    """
    pairwise = sig_result.get("pairwise", [])
    if not pairwise:
        print("基线数不足，跳过统计检验图")
        return

    baselines = ["aitester"] + [p[1] for p in pairwise]
    p_values = [[None for _ in baselines] for _ in baselines]
    cohens_d = [[None for _ in baselines] for _ in baselines]

    for p in pairwise:
        bl_a, bl_b, _, _, _, _, d, sig, _ = p
        idx_a, idx_b = baselines.index(bl_a), baselines.index(bl_b)
        p_values[idx_a][idx_b] = sig
        p_values[idx_b][idx_a] = sig
        cohens_d[idx_a][idx_b] = round(d, 2)
        cohens_d[idx_b][idx_a] = round(-d, 2)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # p 值热力图
    im1 = ax1.imshow(
        [[1 if s in ("***", "**", "*") else 0.3 for s in row] for row in p_values],
        cmap="RdYlGn_r",
        vmin=0,
        vmax=1,
        aspect="auto",
    )
    ax1.set_xticks(range(len(baselines)))
    ax1.set_yticks(range(len(baselines)))
    ax1.set_xticklabels(baselines, rotation=45, ha="right")
    ax1.set_yticklabels(baselines)
    for i in range(len(baselines)):
        for j in range(len(baselines)):
            ax1.text(
                j,
                i,
                p_values[i][j],
                ha="center",
                va="center",
                color="white" if p_values[i][j] in ("***", "**", "*") else "black",
                fontsize=11,
            )
    ax1.set_title("配对 t 检验 p 值（*** p<0.001, ** p<0.01, * p<0.05）", fontsize=11)
    fig.colorbar(im1, ax=ax1, shrink=0.8)

    # Cohen's d 效应量柱状图
    d_vals = [p[6] for p in pairwise]  # Cohen's d
    labels = [f"{p[0]} vs {p[1]}" for p in pairwise]
    colors = ["#55A868" if d >= 0 else "#C44E52" for d in d_vals]
    bars = ax2.barh(labels, d_vals, color=colors)
    ax2.axvline(x=0, color="black", linewidth=0.8)
    ax2.set_title("Cohen's d 效应量（右侧=aitester 优势）", fontsize=11)
    ax2.set_xlabel("Cohen's d")
    for bar, d in zip(bars, d_vals, strict=False):
        ax2.text(
            bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2, f"{d:.2f}", ha="left", va="center", fontsize=9
        )
    plt.tight_layout()
    plt.savefig(os.path.join(_charts_dir, "statistical_significance.png"), dpi=150)
    plt.close()
    print("图表已保存: statistical_significance.png")


def plot_detail_table(summary: dict[str, Any]) -> None:
    """生成详细结果表格（CSV 格式），便于论文引用。"""
    rows = []
    for bl, data in summary["results"].items():
        rows.append(
            {
                "baseline": bl,
                "total_functions": data["total_functions"],
                "passed": data["passed_count"],
                "failed": data["failure_count"],
                "success_rate_pct": data["success_rate"],
                "avg_coverage_pct": data["avg_coverage"],
                "avg_iterations": data["avg_iterations"],
                "avg_time_s": data["avg_elapsed_seconds"],
                "total_time_s": data["total_time"],
            }
        )

    df = pd.DataFrame(rows)
    csv_path = os.path.join(_charts_dir, "results_table.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print("结果表格已保存: results_table.csv")
    print(df.to_string(index=False))


def write_summary_md(summary: dict[str, Any], sig_result: dict[str, Any]) -> None:
    """生成 Markdown 格式的汇总报告，便于论文引用。"""
    lines = [
        "# Benchmark Results Summary",
        "",
        f"**数据集**: {summary.get('dataset', 'unknown')}  |  **子集**: {summary.get('subset', 'N/A')}  |  **任务数**: {sig_result.get('n_tasks', 'N/A')}",
        "",
        "## 各基线汇总统计",
        "",
        "| Baseline | Tasks | Passed | Success Rate (%) | Avg Coverage (%) | Avg Iterations | Mean Rate (%) | Std (%) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for bl, stats in sig_result.get("per_baseline", {}).items():
        bl_data = summary["results"].get(bl, {})
        lines.append(
            f"| {bl} | {stats['n']} | {bl_data.get('passed_count', '-')} "
            f"| {bl_data.get('success_rate', '-')} | {bl_data.get('avg_coverage', '-')} "
            f"| {bl_data.get('avg_iterations', '-')} | {stats['mean_rate']} | {stats['std_rate']} |"
        )

    lines += [
        "",
        "## 统计显著性检验（配对 t 检验 + Mann-Whitney U）",
        "",
        "| Pair | t-stat | p-value | Sig. | Cohen's d | Effect |",
        "|---|---|---|---|---|---|",
    ]
    for p in sig_result.get("pairwise", []):
        bl_a, bl_b, t_stat, p_val, _, mw_p, d, sig, effect = p
        lines.append(f"| {bl_a} vs {bl_b} | {t_stat} | {p_val} ({mw_p}) | {sig} | {d} | {effect} |")

    md_path = os.path.join(_charts_dir, "summary_stats.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("汇总报告已保存: summary_stats.md")


def main() -> None:
    """主入口：加载最新结果并生成所有可视化输出。"""
    results_dir = RESULTS_DIR
    if len(sys.argv) > 1 and sys.argv[1] in ("--results-dir", "-r"):
        results_dir = sys.argv[2] if len(sys.argv) > 2 else RESULTS_DIR
    global _charts_dir
    _charts_dir = os.path.join(results_dir, "charts")
    os.makedirs(_charts_dir, exist_ok=True)

    result_file = load_latest_result(results_dir)
    print(f"加载结果: {result_file}")

    with open(result_file, encoding="utf-8") as f:
        summary = json.load(f)

    plot_baseline_comparison(summary)
    plot_detail_table(summary)

    # 统计显著性检验
    sig_result = compute_significance(summary)
    plot_statistical_significance(sig_result)
    write_summary_md(summary, sig_result)

    print(f"\n✅ 可视化完成，图表保存在: {_charts_dir}")


if __name__ == "__main__":
    main()
