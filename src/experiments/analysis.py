"""
实验结果对比分析模块。

提供多基线实验结果的统计分析和可视化支持，包括：
- 成功率对比
- 覆盖率对比
- 统计显著性检验
- 生成对比报告
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def analyze_experiment_results(results: dict[str, Any]) -> dict[str, Any]:
    """分析实验结果并生成对比报告。

    Args:
        results: 实验结果字典，包含各基线的统计信息。
            格式: {
                "baseline_name": {
                    "passed_count": int,
                    "total_count": int,
                    "success_rate": float,
                    "avg_coverage": float,
                    "avg_iterations": float,
                }
            }

    Returns:
        分析结果字典，包含对比统计和显著性检验结果。

    Raises:
        ValueError: 当输入数据格式无效时抛出。
    """
    if not results:
        raise ValueError("实验结果不能为空")

    analysis = {
        "baselines": list(results.keys()),
        "comparison": {},
        "rankings": {},
    }

    # 计算各基线统计
    success_rates = []
    coverages = []

    for name, data in results.items():
        rate = data.get("success_rate", 0)
        coverage = data.get("avg_coverage", 0)
        success_rates.append(rate)
        coverages.append(coverage)

        analysis["comparison"][name] = {
            "success_rate": round(rate, 2),
            "coverage": round(coverage, 2),
            "iterations": round(data.get("avg_iterations", 0), 2),
        }

    # 生成排名
    analysis["rankings"] = {
        "success_rate": _rank_by_metric(success_rates, results),
        "coverage": _rank_by_metric(coverages, results),
    }

    # 简化显著性检验（实际项目中可使用 scipy）
    analysis["significance"] = {
        "method": "t-test (requires scipy)",
        "note": "Install scipy for full statistical analysis",
    }

    return analysis


def _rank_by_metric(values: list[float], results: dict[str, Any]) -> list[dict[str, Any]]:
    """按指标值排序并返回排名列表。

    Args:
        values: 指标值列表。
        results: 原始实验结果字典。

    Returns:
        按值降序排列的排名列表。
    """
    paired = list(zip(values, results.keys(), strict=True))
    paired.sort(reverse=True)

    return [
        {"rank": i + 1, "baseline": name, "value": round(value, 2)}
        for i, (value, name) in enumerate(paired)
    ]


def generate_comparison_report(analysis: dict[str, Any], output_path: str | None = None) -> str:
    """生成 Markdown 格式的对比报告。

    Args:
        analysis: analyze_experiment_results 返回的分析结果。
        output_path: 可选的输出文件路径。

    Returns:
        Markdown 格式的報告文本。
    """
    lines = [
        "# Experiment Comparison Report",
        "",
        f"## Baselines: {', '.join(analysis['baselines'])}",
        "",
        "## Success Rate Ranking",
        "",
        "| Rank | Baseline | Success Rate (%) |",
        "|---|---|---|",
    ]

    for rank_info in analysis["rankings"]["success_rate"]:
        lines.append(
            f"| {rank_info['rank']} | {rank_info['baseline']} | {rank_info['value']} |"
        )

    lines += [
        "",
        "## Coverage Ranking",
        "",
        "| Rank | Baseline | Avg Coverage (%) |",
        "|---|---|---|",
    ]

    for rank_info in analysis["rankings"]["coverage"]:
        lines.append(
            f"| {rank_info['rank']} | {rank_info['baseline']} | {rank_info['value']} |"
        )

    lines += [
        "",
        "## Detailed Comparison",
        "",
        "| Baseline | Success Rate | Coverage | Iterations |",
        "|---|---|---|---|",
    ]

    for name, data in analysis["comparison"].items():
        lines.append(
            f"| {name} | {data['success_rate']}% | {data['coverage']}% | {data['iterations']} |"
        )

    report = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("报告已保存至: %s", output_path)

    return report


def load_and_analyze(result_file: str) -> dict[str, Any]:
    """从 JSON 文件加载实验结果并进行分析。

    Args:
        result_file: 实验结果 JSON 文件路径。

    Returns:
        分析结果字典。
    """
    with open(result_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return analyze_experiment_results(data)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python src/experiments/analysis.py <result_file.json>")
        sys.exit(1)

    result_file = sys.argv[1]
    analysis = load_and_analyze(result_file)
    report = generate_comparison_report(analysis)
    print(report)
