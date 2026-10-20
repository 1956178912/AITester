"""
实验结果可视化脚本：读取 benchmark JSON 结果，生成对比图表与统计显著性检验。
输出：
  - experiments/results/charts/baseline_comparison.png（柱状图对比）
  - experiments/results/charts/statistical_significance.png（统计检验结果）
  - experiments/results/charts/results_table.csv（详细数据表格）
  - experiments/results/charts/summary_stats.md（Markdown 汇总报告）

B6（2026-10-16）呈现口径：基口径 = detection_rate（M1 诚实口径，None 剔除；
旧批次缺字段时回退 passed 并显式标注）；success（自指通过率）保留但标注
"不得单独引用"——须与检出/假修复/修复三指标并列（状态登记册 §5）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

# F06（2026-10-19 审查执行前提）：以 `python experiments/visualize_results.py`
# 直接运行（reproduce.sh Step 6 口径）时 sys.path[0] 是 experiments/ 目录、仓库
# 根不在其中，`from experiments.statistical_analysis import ...` 会
# ModuleNotFoundError——Step 6 出图此前从未能按脚本内命令直接跑通。此处显式
# 注入仓库根（与 analyze_results.py / run_benchmark.py 同口径），保证
# reproduce.sh Step 6 调用真实可用。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # 无 GUI 环境下的后端
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as scipy_stats  # noqa: E402

from experiments.statistical_analysis import (  # noqa: E402
    _pair_by_task,
    cohens_d,
    interpret_d,
    interpret_p,
)

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


def load_latest_result(
    results_dir: str = RESULTS_DIR,
    dataset: str | None = None,
    result_path: str | None = None,
) -> str:
    """定位要可视化的 benchmark 结果文件（F06：显式来源，不静默猜测）。

    仅识别 benchmark 运行产物（``benchmark_<dataset>_<YYYYMMDD_HHMMSS>.json``，
    与 run_benchmark 的命名口径一致）；results 目录下还混有汇总/基线/性能类
    JSON（如 swebench_20_summary.json、performance_benchmark.json、
    synthetic_plain_llm_*.json），纯文件名倒序会误选这些文件。

    F06（2026-10-19 第三方全量静态审查，P1）：旧实现只按**完整文件名**倒序
    取第一项——同目录混存多数据集产物时字典序会压过时间戳（例如旧的
    ``benchmark_ult_*`` 压过较新的 ``benchmark_synthetic_*``），导致出图基于
    错误数据集。现按以下优先级确定来源，且无匹配时**显式报错**：

    1. ``result_path`` 显式给定：直接使用（存在性 fail-closed 校验）；
    2. ``dataset`` 显式给定：只匹配 ``benchmark_{dataset}_`` 前缀，取最新；
    3. 两者都未给：仅在 ``benchmark_*`` 中取最新（**不**回退到全量 JSON）。

    Args:
        results_dir: 结果目录（默认 ``experiments/results``）。
        dataset: 数据集名（``synthetic`` / ``swe_bench`` / ``examples`` 等），
            用于前缀过滤；None 表示不过滤数据集。
        result_path: 显式结果 JSON 路径，优先级最高。

    Returns:
        选中结果 JSON 的路径。

    Raises:
        FileNotFoundError: 显式路径不存在，或目录下没有匹配的 benchmark 结果
            （不静默回退，避免把汇总/基线文件当成本次产物出图）。
    """
    if result_path:
        if not os.path.isfile(result_path):
            raise FileNotFoundError(f"显式指定的结果文件不存在: {result_path}")
        return result_path

    all_json = [f for f in os.listdir(results_dir) if f.endswith(".json")]
    benchmark_files = [f for f in all_json if f.startswith("benchmark_")]
    if dataset:
        prefix = f"benchmark_{dataset}_"
        benchmark_files = [f for f in benchmark_files if f.startswith(prefix)]
        if not benchmark_files:
            raise FileNotFoundError(
                f"结果目录 {results_dir} 下没有数据集 '{dataset}' 的 benchmark 结果"
                f"（期望前缀 {prefix}*.json）；请检查 --dataset 或显式指定 --result"
            )
    if not benchmark_files:
        raise FileNotFoundError(
            f"结果目录 {results_dir} 下没有 benchmark_* 结果文件（不回退为全量 JSON 猜测；请用 --result 显式指定）"
        )
    return os.path.join(results_dir, sorted(benchmark_files, reverse=True)[0])


# ─── 统计检验（收敛至 statistical_analysis.py 单一规范实现）─────────────────────
# 配对原语 _pair_by_task / Cohen's d / 显著性标记解释统一复用 experiments.statistical_analysis，
# 本文件仅保留 scipy 原生调用（ttest_rel / mannwhitneyu）——非参数 U 检验是本脚本图表
# 专用指标，规范模块未覆盖，故保留 scipy 直接调用（口径仍与配对原语一致）。


def _metric_stats(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """M1 诚实口径的逐基线统计：None 剔除（不计 0），返回百分比均值/标准差与可测 n。

    与 `_pair_by_task` 的 field 口径一致（B6/2026-10-16：呈现层不得把
    不可测（None）静默计 0）。`passed` 为布尔字段——bool 是 int 子类，
    同一函数可复用。
    """
    vals = [float(r[field]) for r in rows if isinstance(r.get(field), (int, float))]
    n = len(vals)
    if n == 0:
        return {"mean_pct": None, "std_pct": None, "n": 0}
    mean = sum(vals) / n
    std = (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"mean_pct": round(mean * 100, 1), "std_pct": round(std * 100, 1), "n": n}


def compute_significance(summary: dict[str, Any]) -> dict[str, Any]:
    """对所有基线两两配对做显著性检验（B6/2026-10-16：口径从 passed 改为检出优先）。

    基口径 = **detection_rate**（M1 诚实口径：None 剔除、不计 0；配对要求
    两侧任务均可测）——与项目呈现纪律"success（自指通过率）不得单独引用、
    必须与检出/修复/假修复三指标并列"（状态登记册 §5）一致。全部任务均
    不可测（旧批次缺该字段）时回退 passed 口径并在返回体显式标注 basis
    （防静默用错口径）。同时给出各基线三指标 + passed 的完整可测统计。

    Args:
        summary: benchmark 汇总结果字典。

    Returns:
        {
            "basis": "detection" | "passed",
            "pairwise": [(bl_a, bl_b, t_stat, p_val, u_stat, mw_p, d, sig, effect), ...],
            "per_baseline": {bl: {"mean_rate", "std_rate", "n", "n_measurable",
                                  "detection": {...}, "false_fix": {...},
                                  "repair": {...}, "passed": {...}}},
            "n_tasks": 总任务数
        }
    """
    baselines = list(summary["results"].keys())
    details_map = {bl: summary["results"][bl]["details"] for bl in baselines}

    # 口径裁决：任基线存在可测 detection_rate → 检出主口径；否则回退自指口径
    det_measurable_total = sum(
        1 for bl in baselines for r in details_map[bl] if isinstance(r.get("detection_rate"), (int, float))
    )
    if det_measurable_total > 0:
        basis = "detection"
    else:
        basis = "passed"
        print("⚠️  全部任务 detection_rate 不可测（旧批次缺该字段），显著性检验回退 passed 自指口径")
    # 行字段名（明细行字段 vs 展示口径名不同：detection_rate / passed）
    pair_field = "detection_rate" if basis == "detection" else "passed"

    # 收集所有任务的 task_id，用于配对比较（同一任务在不同基线上的表现对比）
    all_task_ids: set[str] = set()
    for bl_details in details_map.values():
        all_task_ids.update(r["task_id"] for r in bl_details)
    all_task_ids = sorted(all_task_ids)

    # 各基线可测统计（三指标 + passed 全量；None 剔除）
    per_baseline: dict[str, dict[str, Any]] = {}
    for bl in baselines:
        rows = details_map[bl]
        det = _metric_stats(rows, "detection_rate")
        passed_stats = _metric_stats(rows, "passed")
        per_baseline[bl] = {
            "mean_rate": det["mean_pct"] if basis == "detection" else passed_stats["mean_pct"],
            "std_rate": det["std_pct"] if basis == "detection" else passed_stats["std_pct"],
            "n": len(rows),
            "n_measurable": det["n"] if basis == "detection" else passed_stats["n"],
            "detection": det,
            "false_fix": _metric_stats(rows, "false_fix_rate"),
            "repair": _metric_stats(rows, "repair_rate"),
            "passed": passed_stats,
        }

    # 两两配对检验：以第一个基线（通常 aitester）为参照，与其他基线逐一比较
    # 配对原语复用 statistical_analysis._pair_by_task（按 task_id 配对，与规范模块一致；
    # B6：field=基口径——detection 主口径 / passed 回退，两侧同口径出数）
    pairwise = []
    if len(baselines) >= 2:
        ref = baselines[0]  # 以 aitester 为主基线，对比其他方法的相对提升
        ref_details = details_map[ref]

        for bl in baselines[1:]:
            cmp_details = details_map[bl]

            # 按 task_id 配对（与 statistical_analysis.paired_t_test 同一原语）
            paired_a, paired_b, _common = _pair_by_task(ref_details, cmp_details, field=pair_field)
            n_pairs = len(paired_a)

            # 配对 t 检验（双尾）
            t_stat, p_val = scipy_stats.ttest_rel(paired_a, paired_b) if n_pairs >= 3 else (float("nan"), float("nan"))
            # Mann-Whitney U 检验（非参数，双尾；样本不足时记 NaN 与旧图表占位口径一致）
            u_stat, mw_p = (
                scipy_stats.mannwhitneyu(paired_a, paired_b, alternative="two-sided")
                if n_pairs >= 3
                else (float("nan"), float("nan"))
            )
            # Cohen's d 复用 statistical_analysis.cohens_d（同一配对原语与字段口径，
            # B6：field=pair_field 与 t 检验保持同口径；n<2 返回 NaN）
            d, _d_n = cohens_d(ref_details, cmp_details, field=pair_field)

            # NaN/Inf 守卫（与 src/experiments/analysis.py 同口径）：
            # 两组通过率完全恒定（全 1 / 全 0 / 配对差值无方差）时 scipy 返回 inf/NaN，
            # 图表占位与 JSON 序列化（round(float(inf)) 产生 Infinity 非标准 token）均需有限值，
            # 该对比记 NaN 占位而非崩溃
            if not (math.isfinite(t_stat) and math.isfinite(p_val) and math.isfinite(d)):
                t_stat = p_val = u_stat = mw_p = float("nan")
                d = float("nan")

            sig = interpret_p(p_val)
            pairwise.append(
                (
                    ref,
                    bl,
                    round(float(t_stat), 3) if n_pairs >= 3 else float("nan"),
                    round(float(p_val), 4) if n_pairs >= 3 else float("nan"),
                    round(float(u_stat), 1) if n_pairs >= 3 else float("nan"),
                    round(float(mw_p), 4) if n_pairs >= 3 else float("nan"),
                    round(float(d), 3),
                    sig,
                    interpret_d(d),
                )
            )

    return {"basis": basis, "pairwise": pairwise, "per_baseline": per_baseline, "n_tasks": len(all_task_ids)}


# ─── 图表绘制 ────────────────────────────────────────────────────────────────────


def plot_baseline_comparison(summary: dict[str, Any]) -> None:
    """四联柱状图（B6/2026-10-16 口径重排）：检出率 / 假修复率 / 成功率* / 覆盖率。

    呈现纪律对齐（状态登记册 §5）：detection 与 false_fix 为 M1 诚实口径
    （None 剔除，无值画 "—" 并标注可测 n），成功率保留但显式标注**自指
    口径（passed 派生，不得单独引用）**；平均修复迭代不再入主图（辅助量）。
    """
    baselines = list(summary["results"].keys())
    details_map = {bl: summary["results"][bl]["details"] for bl in baselines}
    det = {bl: _metric_stats(details_map[bl], "detection_rate") for bl in baselines}
    ffx = {bl: _metric_stats(details_map[bl], "false_fix_rate") for bl in baselines}
    success_rates = [summary["results"][bl]["success_rate"] for bl in baselines]
    coverages = [summary["results"][bl]["avg_coverage"] for bl in baselines]

    x = list(range(len(baselines)))
    _fig, axes = plt.subplots(1, 4, figsize=(20, 5))

    def _panel(
        ax: Any,
        values: list[float | None],
        ns: list[int | None],
        title: str,
        color: str,
    ) -> None:
        bars = ax.bar(x, [v if v is not None else 0.0 for v in values], color=color)
        ax.set_title(title, fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(baselines, rotation=15, ha="right")
        ax.set_ylim(0, 100)
        for bar, val, n in zip(bars, values, ns, strict=False):
            if val is None:
                label = "—（不可测）"
            elif n is not None and n > 0:
                label = f"{val:.1f}\n(n={n})"
            else:
                label = f"{val:.1f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                (bar.get_height() if val is not None else 0.0) + 1,
                label,
                ha="center",
                va="bottom",
                fontsize=8,
            )

    _panel(
        axes[0], [det[bl]["mean_pct"] for bl in baselines], [det[bl]["n"] for bl in baselines], "检出率 (%)", "#4C72B0"
    )
    _panel(
        axes[1],
        [ffx[bl]["mean_pct"] for bl in baselines],
        [ffx[bl]["n"] for bl in baselines],
        "假修复率 (%)（M1 口径）",
        "#C44E52",
    )
    _panel(axes[2], list(success_rates), [None] * len(baselines), "测试成功率* (%)（自指口径）", "#8172B2")
    _panel(axes[3], list(coverages), [None] * len(baselines), "平均覆盖率 (%)", "#55A868")

    _fig.text(
        0.5,
        -0.06,
        "* 自指通过率（passed 派生）：不得单独引用——须与检出/假修复/修复三指标并列（状态登记册 §5；B6/2026-10-16）",
        ha="center",
        fontsize=9,
    )

    plt.tight_layout()
    plt.savefig(os.path.join(_charts_dir, "baseline_comparison.png"), dpi=150)
    plt.close()
    print("图表已保存: baseline_comparison.png")


def plot_statistical_significance(sig_result: dict[str, Any]) -> None:
    """
    绘制统计检验结果：p 值热力图 + Cohen's d 效应量柱状图。
    仅在有至少 2 个基线时生成。标题显式标注基口径（B6/2026-10-16）。
    """
    pairwise = sig_result.get("pairwise", [])
    if not pairwise:
        print("基线数不足，跳过统计检验图")
        return

    basis = sig_result.get("basis", "detection")

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
            # 2026-09-26 round9（P2 健壮性）：对角线/无对比对象格为 None
            # （i==j 或该基线对未做检验），ax1.text 传 None 会被 matplotlib
            # 静默渲染为 "None" 文本，改为 "—" 占位（无对比数据语义）
            cell = p_values[i][j]
            ax1.text(
                j,
                i,
                "—" if cell is None else cell,
                ha="center",
                va="center",
                color="white" if cell in ("***", "**", "*") else "black",
                fontsize=11,
            )
    ax1.set_title(f"配对 t 检验 p 值（基口径={basis}；*** p<0.001, ** p<0.01, * p<0.05）", fontsize=11)
    fig.colorbar(im1, ax=ax1, shrink=0.8)

    # Cohen's d 效应量柱状图
    d_vals = [p[6] for p in pairwise]  # Cohen's d
    labels = [f"{p[0]} vs {p[1]}" for p in pairwise]
    colors = ["#55A868" if d >= 0 else "#C44E52" for d in d_vals]
    bars = ax2.barh(labels, d_vals, color=colors)
    ax2.axvline(x=0, color="black", linewidth=0.8)
    ax2.set_title(f"Cohen's d 效应量（基口径={basis}；右侧=参照基线优势）", fontsize=11)
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
    """生成详细结果表格（CSV 格式，B6/2026-10-16：三指标列前置、自指口径列后移）。

    列序纪律：detection / false_fix / repair（M1 诚实口径，含可测 n）在前，
    success（自指）/ passed 原始计数随后——与"success 不得单独引用"的
    呈现声明一致。
    """
    rows = []
    for bl, data in summary["results"].items():
        details = data["details"]
        det = _metric_stats(details, "detection_rate")
        ffx = _metric_stats(details, "false_fix_rate")
        rep = _metric_stats(details, "repair_rate")
        rows.append(
            {
                "baseline": bl,
                "total_functions": data["total_functions"],
                "detection_rate_pct": det["mean_pct"],
                "detection_n_measurable": det["n"],
                "false_fix_rate_pct": ffx["mean_pct"],
                "false_fix_n_measurable": ffx["n"],
                "repair_rate_pct": rep["mean_pct"],
                "repair_n_measurable": rep["n"],
                "success_rate_pct": data["success_rate"],
                "passed": data["passed_count"],
                "failed": data["failure_count"],
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
    """生成 Markdown 格式的汇总报告，便于论文引用（B6/2026-10-16：三指标列前置）。"""
    basis = sig_result.get("basis", "detection")
    basis_label = "检出率（detection）" if basis == "detection" else "自指通过率（passed，回退口径）"

    def _cell(m: dict[str, Any]) -> str:
        return "—" if m.get("mean_pct") is None else f"{m['mean_pct']} ({m['n']})"

    lines = [
        "# Benchmark Results Summary",
        "",
        f"**数据集**: {summary.get('dataset', 'unknown')}",
        f"**子集**: {summary.get('subset', 'N/A')}  |  **任务数**: {sig_result.get('n_tasks', 'N/A')}",
        f"**显著性基口径**: {basis_label}（B6/2026-10-16）",
        "",
        "## 各基线汇总统计",
        "",
        "> 三指标 = 检出率 / 假修复率 / 修复率（M1 诚实口径：括号内为可测 n，None 剔除不计 0）；",
        "> Success* 为自指通过率（passed 派生，**不得单独引用**——须与三指标并列）。",
        "",
        "| Baseline | Tasks | Detection Rate (n) | False-Fix Rate (n) | Repair Rate (n) | Success* % | Coverage % | Mean Rate | Std |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for bl, stats in sig_result.get("per_baseline", {}).items():
        bl_data = summary["results"].get(bl, {})
        lines.append(
            f"| {bl} | {stats['n']} | {_cell(stats.get('detection', {}))} "
            f"| {_cell(stats.get('false_fix', {}))} | {_cell(stats.get('repair', {}))} "
            f"| {bl_data.get('success_rate', '-')} | {bl_data.get('avg_coverage', '-')} "
            f"| {stats['mean_rate']} | {stats['std_rate']} |"
        )

    lines += [
        "",
        f"## 统计显著性检验（配对 t 检验 + Mann-Whitney U；基口径 = {basis_label}）",
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
    """主入口：加载指定/最新结果并生成所有可视化输出。

    F06（2026-10-19 第三方审查，P1）：新增 ``--result``（显式产物路径，最高
    优先级）与 ``--dataset``（只认 ``benchmark_{dataset}_`` 前缀）——复现脚本
    Step6 传 ``--dataset "$DATASET"``，保证出图来源 = 本次运行的数据集，不再
    依赖目录内文件名倒序猜测（旧行为会让 benchmark_ult_* 压过 synthetic）。
    """
    parser = argparse.ArgumentParser(description="AITester 实验结果可视化（F06 显式来源）")
    parser.add_argument("--results-dir", "-r", default=RESULTS_DIR, help="结果目录（默认 experiments/results）")
    parser.add_argument("--result", default=None, help="显式指定 benchmark 结果 JSON 路径（优先于 --dataset）")
    parser.add_argument(
        "--dataset", default=None, help="只使用 benchmark_<dataset>_ 前缀的结果（如 synthetic / swe_bench）"
    )
    args = parser.parse_args()

    results_dir = args.results_dir
    global _charts_dir
    _charts_dir = os.path.join(results_dir, "charts")
    os.makedirs(_charts_dir, exist_ok=True)

    result_file = load_latest_result(results_dir, dataset=args.dataset, result_path=args.result)
    print(f"加载结果: {result_file}")
    if args.dataset:
        print(f"数据集过滤: --dataset {args.dataset}（仅 benchmark_{args.dataset}_ 前缀）")

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
