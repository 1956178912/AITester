"""
统计显著性检验模块

提供配对 t 检验、Cohen's d 效应量计算等统计分析功能。
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

    for json_file in results_path.glob("**/benchmark_*.json"):
        try:
            with open(json_file) as f:
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
) -> tuple[float, float]:
    """
    配对 t 检验

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表
        baseline_name: 基线名称

    Returns:
        (t_statistic, p_value)
    """
    # 提取成功率
    aitester_pass = [1 if r.get("passed") else 0 for r in aitester_results]
    baseline_pass = [1 if r.get("passed") else 0 for r in baseline_results]

    # 取较小长度进行配对
    min_len = min(len(aitester_pass), len(baseline_pass))
    aitester_pass = aitester_pass[:min_len]
    baseline_pass = baseline_pass[:min_len]

    if min_len < 3:
        return (float("nan"), float("nan"))

    # 配对 t 检验
    [a - b for a, b in zip(aitester_pass, baseline_pass, strict=False)]
    t_stat, p_value = stats.ttest_rel(aitester_pass, baseline_pass)

    print(f"\n配对 t 检验：AITester vs {baseline_name}")
    print(f"  样本数：{min_len}")
    print(f"  t 统计量：{t_stat:.4f}")
    print(f"  p 值：{p_value:.4f}")
    print(f"  显著性：{'***' if p_value < 0.001 else '**' if p_value < 0.01 else '*' if p_value < 0.05 else 'n.s.'}")

    return t_stat, p_value


def cohens_d(aitester_results: list[dict], baseline_results: list[dict]) -> float:
    """
    计算 Cohen's d 效应量

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表

    Returns:
        Cohen's d 值
    """
    # 提取成功率
    aitester_pass = [1 if r.get("passed") else 0 for r in aitester_results]
    baseline_pass = [1 if r.get("passed") else 0 for r in baseline_results]

    # 取较小长度
    min_len = min(len(aitester_pass), len(baseline_pass))
    aitester_pass = aitester_pass[:min_len]
    baseline_pass = baseline_pass[:min_len]

    if min_len < 2:
        return float("nan")

    # 计算合并标准差
    pooled_std = np.sqrt(
        ((min_len - 1) * np.std(aitester_pass, ddof=1) ** 2 + (min_len - 1) * np.std(baseline_pass, ddof=1) ** 2)
        / (2 * min_len - 2)
    )

    if pooled_std == 0:
        return 0.0

    # Cohen's d
    mean_diff = np.mean(aitester_pass) - np.mean(baseline_pass)
    d = mean_diff / pooled_std

    # 效应量解释
    if abs(d) < 0.2:
        effect = "negligible"
    elif abs(d) < 0.5:
        effect = "small"
    elif abs(d) < 0.8:
        effect = "medium"
    else:
        effect = "large"

    print("\nCohen's d 效应量：AITester vs baseline")
    print(f"  d = {d:.4f} ({effect})")

    return d


def run_all_statistics(results_dir: str):
    """
    运行所有统计检验

    Args:
        results_dir: 实验结果目录路径
    """
    print("=" * 60)
    print("统计显著性检验报告")
    print("=" * 60)

    # 加载数据
    data = load_experiment_results(results_dir)

    # 统计样本数
    print("\n数据概览：")
    print(f"  AITester: {len(data['aitester'])} 个任务")
    print(f"  plain_llm: {len(data['plain_llm'])} 个任务")
    print(f"  single_agent: {len(data['single_agent'])} 个任务")

    # 计算基本统计量
    for baseline in ["aitester", "plain_llm", "single_agent"]:
        if data[baseline]:
            passed = sum(1 for r in data[baseline] if r.get("passed"))
            total = len(data[baseline])
            rate = passed / total * 100 if total > 0 else 0
            print(f"  {baseline}: {passed}/{total} 通过 ({rate:.1f}%)")

    # 配对 t 检验
    print("\n" + "=" * 60)
    print("配对 t 检验结果")
    print("=" * 60)

    if data["plain_llm"]:
        paired_t_test(data["aitester"], data["plain_llm"], "plain_llm")

    if data["single_agent"]:
        paired_t_test(data["aitester"], data["single_agent"], "single_agent")

    # Cohen's d 效应量
    print("\n" + "=" * 60)
    print("Cohen's d 效应量")
    print("=" * 60)

    if data["plain_llm"]:
        cohens_d(data["aitester"], data["plain_llm"])

    if data["single_agent"]:
        cohens_d(data["aitester"], data["single_agent"])

    print("\n" + "=" * 60)
    print("检验完成")
    print("=" * 60)


if __name__ == "__main__":
    results_dir = "experiments/results"
    run_all_statistics(results_dir)
