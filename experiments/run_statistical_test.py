#!/usr/bin/env python3
"""
统计显著性检验分析脚本
基于实验结果数据运行配对t检验和Cohen's d效应量计算
"""

import json
from pathlib import Path

import numpy as np
import scipy.stats as stats


def load_experiment_results(results_dir: str) -> dict[str, list[dict]]:
    """
    加载实验结果数据

    Args:
        results_dir: 实验结果目录路径

    Returns:
        按基线分组的实验结果字典
    """
    results = {"aitester": [], "plain_llm": [], "single_agent": []}
    results_path = Path(results_dir)

    # 递归查找所有benchmark JSON文件
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


def paired_t_test(
    aitester_results: list[dict], baseline_results: list[dict], baseline_name: str
) -> tuple[float, float, int]:
    """
    配对t检验

    Args:
        aitester_results: AITester结果列表
        baseline_results: 基线结果列表
        baseline_name: 基线名称

    Returns:
        (t_statistic, p_value, n_pairs)
    """
    # 提取通过率
    [1 if r.get("passed") else 0 for r in aitester_results]
    [1 if r.get("passed") else 0 for r in baseline_results]

    # 按task_id配对
    aitester_by_task = {r["task_id"]: (1 if r.get("passed") else 0) for r in aitester_results}
    baseline_by_task = {r["task_id"]: (1 if r.get("passed") else 0) for r in baseline_results}

    # 找到共同的任务
    common_tasks = set(aitester_by_task.keys()) & set(baseline_by_task.keys())

    if len(common_tasks) < 3:
        return (float("nan"), float("nan"), 0)

    # 按相同顺序排列
    sorted_tasks = sorted(common_tasks)
    paired_aitester = [aitester_by_task[t] for t in sorted_tasks]
    paired_baseline = [baseline_by_task[t] for t in sorted_tasks]

    n_pairs = len(paired_aitester)

    # 配对t检验
    t_stat, p_value = stats.ttest_rel(paired_aitester, paired_baseline)

    return t_stat, p_value, n_pairs


def cohens_d(aitester_results: list[dict], baseline_results: list[dict], n_pairs: int) -> float:
    """
    计算Cohen's d效应量

    Args:
        aitester_results: AITester结果列表
        baseline_results: 基线结果列表
        n_pairs: 配对数量

    Returns:
        Cohen's d值
    """
    if n_pairs < 2:
        return float("nan")

    # 按task_id配对
    aitester_by_task = {r["task_id"]: (1 if r.get("passed") else 0) for r in aitester_results}
    baseline_by_task = {r["task_id"]: (1 if r.get("passed") else 0) for r in baseline_results}

    # 找到共同的任务
    common_tasks = set(aitester_by_task.keys()) & set(baseline_by_task.keys())
    sorted_tasks = sorted(common_tasks)[:n_pairs]

    paired_aitester = [aitester_by_task[t] for t in sorted_tasks]
    paired_baseline = [baseline_by_task[t] for t in sorted_tasks]

    # 计算差值
    differences = [a - b for a, b in zip(paired_aitester, paired_baseline, strict=False)]

    # Cohen's d = mean_diff / std_diff
    mean_diff = np.mean(differences)
    std_diff = np.std(differences, ddof=1)

    if std_diff == 0:
        return 0.0

    d = mean_diff / std_diff
    return d


def interpret_p(p: float) -> str:
    """根据p值返回显著性标记"""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


def interpret_d(d: float) -> str:
    """根据Cohen's d返回效应量描述"""
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


def run_all_statistics(results_dir: str, output_file: str):
    """
    运行所有统计检验并生成报告

    Args:
        results_dir: 实验结果目录
        output_file: 输出报告文件路径
    """
    print("=" * 70)
    print("统计显著性检验报告")
    print("=" * 70)

    # 加载数据
    data = load_experiment_results(results_dir)

    # 计算基本统计量
    stats_summary = {}
    for baseline in ["aitester", "plain_llm", "single_agent"]:
        if data[baseline]:
            passed = sum(1 for r in data[baseline] if r.get("passed"))
            total = len(data[baseline])
            rate = passed / total * 100 if total > 0 else 0
            stats_summary[baseline] = {"n": total, "passed": passed, "rate": rate}
            print(f"\n{baseline}: {passed}/{total} 通过 ({rate:.1f}%)")
        else:
            stats_summary[baseline] = {"n": 0, "passed": 0, "rate": 0}

    # 配对t检验
    print("\n" + "=" * 70)
    print("配对t检验结果")
    print("=" * 70)

    comparisons = []

    # AITester vs plain_llm
    if stats_summary["plain_llm"]["n"] > 0:
        t_stat, p_value, n_pairs = paired_t_test(data["aitester"], data["plain_llm"], "plain_llm")
        d = cohens_d(data["aitester"], data["plain_llm"], n_pairs)
        sig = interpret_p(p_value)
        comparisons.append(
            {
                "comparison": "AITester vs plain_llm",
                "n_pairs": n_pairs,
                "t_stat": t_stat,
                "p_value": p_value,
                "sig": sig,
                "cohens_d": d,
                "effect": interpret_d(d),
            }
        )
        print("\nAITester vs plain_llm:")
        print(f"  配对数: {n_pairs}")
        print(f"  t统计量: {t_stat:.4f}")
        print(f"  p值: {p_value:.4f} ({sig})")
        print(f"  Cohen's d: {d:.4f} ({interpret_d(d)})")

    # AITester vs single_agent
    if stats_summary["single_agent"]["n"] > 0:
        t_stat, p_value, n_pairs = paired_t_test(data["aitester"], data["single_agent"], "single_agent")
        d = cohens_d(data["aitester"], data["single_agent"], n_pairs)
        sig = interpret_p(p_value)
        comparisons.append(
            {
                "comparison": "AITester vs single_agent",
                "n_pairs": n_pairs,
                "t_stat": t_stat,
                "p_value": p_value,
                "sig": sig,
                "cohens_d": d,
                "effect": interpret_d(d),
            }
        )
        print("\nAITester vs single_agent:")
        print(f"  配对数: {n_pairs}")
        print(f"  t统计量: {t_stat:.4f}")
        print(f"  p值: {p_value:.4f} ({sig})")
        print(f"  Cohen's d: {d:.4f} ({interpret_d(d)})")

    # 生成Markdown报告
    report_lines = [
        "# 统计显著性检验报告",
        "",
        "## 数据概览",
        "",
        "| Baseline | 任务数 | 通过数 | 通过率 |",
        "|----------|--------|--------|--------|",
    ]

    for baseline in ["aitester", "plain_llm", "single_agent"]:
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
        report_lines.append(
            f"| {comp['comparison']} | {comp['n_pairs']} | "
            f"{comp['t_stat']:.4f} | {comp['p_value']:.4f} | "
            f"{comp['sig']} | {comp['cohens_d']:.4f} | {comp['effect']} |"
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
        f"*报告生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    # 写入报告
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"\n{'=' * 70}")
    print(f"报告已保存至: {output_file}")
    print(f"{'=' * 70}")

    return comparisons


if __name__ == "__main__":
    results_dir = "experiments/results"
    output_file = "experiments/statistical_report.md"

    run_all_statistics(results_dir, output_file)
