"""
统计显著性检验模块（规范实现）

提供基于 task_id 配对的配对 t 检验、Cohen's d 效应量计算等统计分析功能，
并生成 Markdown 报告。

历史说明：本文件此前与 run_statistical_test.py 各有一份近似重复实现，
且本文件的旧版 paired_t_test/cohens_d 按位置（min_len 截断）配对——
当两个基线的结果顺序不一致时会把不同任务错误地配成一对，t 值与 p 值失真。
现统一为按 task_id 配对（同一任务在两个基线下各跑一次，这才是"配对"的语义），
run_statistical_test.py 退化为薄壳入口（逻辑全部收敛到本模块）。

用法：
    python experiments/statistical_analysis.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import scipy.stats as stats

# 与 run_benchmark.py 一致的路径引导：本文件既可被作为包导入（experiments.statistical_analysis），
# 也可直接以脚本方式运行（python experiments/statistical_analysis.py）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 参与对比的基线（AITester 完整管线 + 两个简化基线）
_BASELINES = ("aitester", "plain_llm", "single_agent")


def load_experiment_results(results_dir: str) -> dict[str, list[dict]]:
    """
    加载实验结果数据

    Args:
        results_dir: 实验结果目录路径

    Returns:
        按基线分组的实验结果字典
    """
    results = {baseline: [] for baseline in _BASELINES}
    results_path = Path(results_dir)

    # 递归查找所有 benchmark JSON 文件
    for json_file in results_path.glob("**/benchmark_*.json"):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                dataset = data.get("dataset", "")
                if dataset != "synthetic":
                    continue

                for baseline, baseline_data in data.get("results", {}).items():
                    if baseline in results:
                        details = baseline_data.get("details", [])
                        results[baseline].extend(details)
        except Exception as e:
            print(f"警告：加载 {json_file} 失败: {e}")

    return results


def _pair_by_task(
    results_a: list[dict],
    results_b: list[dict],
) -> tuple[list[int], list[int], list[str]]:
    """
    按 task_id 将两个基线的结果配成同一任务的观测对。

    返回配对后的通过率列表（0/1）与共同任务 ID 列表（按 task_id 排序，
    保证两次运行配对顺序一致）。位置配对（min_len 截断）在两个基线结果
    顺序不一致时会错配任务，故废弃。

    Args:
        results_a: 基线 A（通常为 AITester）结果列表。
        results_b: 基线 B 结果列表。

    Returns:
        (pass_a, pass_b, common_task_ids)
    """
    pass_a = {r.get("task_id"): (1 if r.get("passed") else 0) for r in results_a if r.get("task_id")}
    pass_b = {r.get("task_id"): (1 if r.get("passed") else 0) for r in results_b if r.get("task_id")}

    common_tasks = sorted(set(pass_a) & set(pass_b))
    paired_a = [pass_a[t] for t in common_tasks]
    paired_b = [pass_b[t] for t in common_tasks]
    return paired_a, paired_b, common_tasks


def paired_t_test(
    aitester_results: list[dict], baseline_results: list[dict], baseline_name: str
) -> tuple[float, float, int]:
    """
    配对 t 检验（按 task_id 配对）

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表
        baseline_name: 基线名称（仅用于语义说明，不影响计算）

    Returns:
        (t_statistic, p_value, n_pairs)；共同任务数 < 3 时返回 (nan, nan, 0)
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)

    if n_pairs < 3:
        return float("nan"), float("nan"), n_pairs

    t_stat, p_value = stats.ttest_rel(paired_a, paired_b)
    return float(t_stat), float(p_value), n_pairs


def cohens_d(
    aitester_results: list[dict],
    baseline_results: list[dict],
) -> tuple[float, int]:
    """
    计算配对版 Cohen's d 效应量（差值均值 / 差值标准差）

    配对设计的效应量应基于配对差值（而非两独立样本的合并标准差），
    与 paired_t_test 使用同一套 task_id 配对。

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表

    Returns:
        (d, n_pairs)；共同任务数 < 2 时返回 (nan, 0)
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)

    if n_pairs < 2:
        return float("nan"), n_pairs

    differences = [a - b for a, b in zip(paired_a, paired_b, strict=True)]
    mean_diff = float(np.mean(differences))
    std_diff = float(np.std(differences, ddof=1))

    if std_diff == 0:
        return 0.0, n_pairs

    return mean_diff / std_diff, n_pairs


def interpret_p(p: float) -> str:
    """根据 p 值返回显著性标记（p 为 nan 时返回 n.s.）。"""
    if p != p:  # NaN 判断（n < 3 时无法计算）
        return "n.s."
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


def interpret_d(d: float) -> str:
    """根据 Cohen's d 返回效应量描述。"""
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


def run_all_statistics(results_dir: str, output_file: str | None = None) -> list[dict]:
    """
    运行所有统计检验并生成报告

    Args:
        results_dir: 实验结果目录
        output_file: Markdown 报告输出路径（None 时仅打印控制台，不落盘）

    Returns:
        比较结果列表，每项含 comparison / n_pairs / t_stat / p_value / sig / cohens_d / effect
    """
    print("=" * 70)
    print("统计显著性检验报告")
    print("=" * 70)

    # 加载数据
    data = load_experiment_results(results_dir)

    # 计算基本统计量
    stats_summary: dict[str, dict[str, float]] = {}
    for baseline in _BASELINES:
        if data[baseline]:
            passed = sum(1 for r in data[baseline] if r.get("passed"))
            total = len(data[baseline])
            rate = passed / total * 100 if total > 0 else 0
            stats_summary[baseline] = {"n": total, "passed": passed, "rate": rate}
            print(f"\n{baseline}: {passed}/{total} 通过 ({rate:.1f}%)")
        else:
            stats_summary[baseline] = {"n": 0, "passed": 0, "rate": 0}
            print(f"\n{baseline}: 无数据")

    # 配对 t 检验 + Cohen's d
    print("\n" + "=" * 70)
    print("配对t检验结果（按 task_id 配对）")
    print("=" * 70)

    comparisons: list[dict] = []
    for baseline in ("plain_llm", "single_agent"):
        if stats_summary[baseline]["n"] == 0:
            continue

        t_stat, p_value, n_pairs = paired_t_test(data["aitester"], data[baseline], baseline)
        d, _ = cohens_d(data["aitester"], data[baseline])
        sig = interpret_p(p_value)

        comparisons.append(
            {
                "comparison": f"AITester vs {baseline}",
                "n_pairs": n_pairs,
                "t_stat": t_stat,
                "p_value": p_value,
                "sig": sig,
                "cohens_d": d,
                "effect": interpret_d(d),
            }
        )

        # nan 值（共同任务 < 3）无法格式化，单独处理
        if t_stat != t_stat:
            print(f"\nAITester vs {baseline}: 共同任务数 {n_pairs} < 3，无法计算配对 t 检验")
            continue

        print(f"\nAITester vs {baseline}:")
        print(f"  配对数: {n_pairs}")
        print(f"  t统计量: {t_stat:.4f}")
        print(f"  p值: {p_value:.4f} ({sig})")
        print(f"  Cohen's d: {d:.4f} ({interpret_d(d)})")

    if output_file:
        # 生成 Markdown 报告
        report_lines = [
            "# 统计显著性检验报告",
            "",
            "## 数据概览",
            "",
            "| Baseline | 任务数 | 通过数 | 通过率 |",
            "|----------|--------|--------|--------|",
        ]

        for baseline in _BASELINES:
            s = stats_summary[baseline]
            report_lines.append(f"| {baseline} | {s['n']} | {s['passed']} | {s['rate']:.1f}% |")

        report_lines += [
            "",
            "## 配对t检验结果",
            "",
            "| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |",
            "|------|--------|---------|-----|--------|-----------|--------|",
        ]

        for comp in comparisons:
            t_disp = "n/a" if comp["t_stat"] != comp["t_stat"] else f"{comp['t_stat']:.4f}"
            p_disp = "n/a" if comp["p_value"] != comp["p_value"] else f"{comp['p_value']:.4f}"
            d_disp = "n/a" if comp["cohens_d"] != comp["cohens_d"] else f"{comp['cohens_d']:.4f}"
            report_lines.append(
                f"| {comp['comparison']} | {comp['n_pairs']} | {t_disp} | {p_disp} | "
                f"{comp['sig']} | {d_disp} | {comp['effect']} |"
            )

        report_lines += [
            "",
            "## 显著性标记说明",
            "",
            "- `***` p < 0.001",
            "- `**` p < 0.01",
            "- `*` p < 0.05",
            "- `n.s.` p ≥ 0.05 (不显著)",
            "",
            "## 效应量解释",
            "",
            "- `negligible`: |d| < 0.2",
            "- `small`: 0.2 ≤ |d| < 0.5",
            "- `medium`: 0.5 ≤ |d| < 0.8",
            "- `large`: |d| ≥ 0.8",
            "",
            "---",
            f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")

        print(f"\n{'=' * 70}")
        print(f"报告已保存至: {output_file}")
        print(f"{'=' * 70}")

    return comparisons


if __name__ == "__main__":
    run_all_statistics("experiments/results", "experiments/statistical_report.md")
