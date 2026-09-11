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
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# scipy 为锁定依赖（requirements.lock），但保持宽容降级：
# 未安装时显著性检验返回 unavailable 而非崩溃
try:
    from scipy import stats as scipy_stats

    _SCIPY_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失的降级分支
    scipy_stats = None
    _SCIPY_AVAILABLE = False

# 显著性检验所需的最小样本数（与 experiments/statistical_analysis.py 保持一致）
_MIN_SAMPLES_FOR_TEST = 3


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

    # 显著性检验：此前写死 "t-test (requires scipy)" 占位文本（从未真正执行），
    # 现按 per-task details 实际计算（配对 t 检验，样本不足时如实标注）
    analysis["significance"] = _compute_significance(results)

    return analysis


def _compute_significance(results: dict[str, Any]) -> dict[str, Any]:
    """按 per-task details 计算基线间成功率的显著性检验。

    仅当各基线提供 details（含 passed 字段的逐任务结果列表）时才能做检验，
    聚合统计量（passed_count 等）不足以推断分布，此时如实返回 insufficient_data
    而不是假装执行了 t 检验。

    配对逻辑与 experiments/statistical_analysis.py 一致：
    两个基线的 details 都含 task_id 时按 task_id 配对（ttest_rel），
    否则退化为 Welch 双样本检验（ttest_ind, equal_var=False）。

    Args:
        results: analyze_experiment_results 的输入字典。

    Returns:
        显著性结果字典：status 为 ok/unavailable/insufficient_data，
        status=ok 时含 method 与 comparisons（每项 comparison/t_stat/p_value/significant）。
    """
    if not _SCIPY_AVAILABLE:
        return {"status": "unavailable", "note": "scipy 未安装，无法执行显著性检验"}

    baseline = "aitester" if "aitester" in results else next(iter(results))
    base_details = results[baseline].get("details")
    if not isinstance(base_details, list) or len(base_details) < _MIN_SAMPLES_FOR_TEST:
        return {
            "status": "insufficient_data",
            "note": f"基线 {baseline} 缺少 ≥{_MIN_SAMPLES_FOR_TEST} 条逐任务 details，无法检验",
        }

    comparisons: list[dict[str, Any]] = []
    for name, data in results.items():
        if name == baseline:
            continue
        other_details = data.get("details")
        if not isinstance(other_details, list) or len(other_details) < _MIN_SAMPLES_FOR_TEST:
            continue

        paired = _pair_passed_by_task(base_details, other_details)
        if paired is not None:
            a, b = paired
            method = "paired_t_test"
            if len(a) < _MIN_SAMPLES_FOR_TEST:
                continue
            t_stat, p_value = scipy_stats.ttest_rel(a, b)
        else:
            a = _passed_indicators(base_details)
            b = _passed_indicators(other_details)
            method = "welch_t_test"
            t_stat, p_value = scipy_stats.ttest_ind(a, b, equal_var=False)

        # NaN/Inf 守卫：两组成功率恒定（全 1 或全 0）时 scipy 返回非有限统计量
        # ——配对 t 检验全零差值给 t=nan，Welch 双样本零方差给 t=±inf。
        # round(float(nan/inf)) 会把非标准 NaN/Infinity token 写进结果 JSON，
        # 严格解析器（如 JS JSON.parse）报错；统计上该对比也无"显著性"可言，
        # 记一条 skipped 说明而非数字条目
        t_stat_f = float(t_stat)
        p_value_f = float(p_value)
        if not math.isfinite(t_stat_f) or not math.isfinite(p_value_f):
            comparisons.append(
                {
                    "comparison": f"{baseline} vs {name}",
                    "method": method,
                    "n_a": len(a),
                    "n_b": len(b),
                    "status": "skipped",
                    "note": "两组通过率恒定（无差异），t 检验不适用",
                }
            )
            continue

        comparisons.append(
            {
                "comparison": f"{baseline} vs {name}",
                "method": method,
                "n_a": len(a),
                "n_b": len(b),
                "t_stat": round(t_stat_f, 4),
                "p_value": round(p_value_f, 4),
                "significant": bool(p_value_f < 0.05),
            }
        )

    if not comparisons:
        return {"status": "insufficient_data", "note": "其他基线缺少逐任务 details，无法对比"}

    return {"status": "ok", "method": "t-test", "comparisons": comparisons}


def _passed_indicators(details: list[dict]) -> list[float]:
    """把逐任务结果转为 0/1 通过率列表。"""
    return [1.0 if r.get("passed") else 0.0 for r in details]


def _pair_passed_by_task(
    details_a: list[dict],
    details_b: list[dict],
) -> tuple[list[float], list[float]] | None:
    """两基线的 details 均含 task_id 时，返回按 task_id 配对的两组通过率列表；否则返回 None。"""
    if not all(r.get("task_id") for r in details_a) or not all(r.get("task_id") for r in details_b):
        return None
    map_a = {r["task_id"]: (1.0 if r.get("passed") else 0.0) for r in details_a}
    map_b = {r["task_id"]: (1.0 if r.get("passed") else 0.0) for r in details_b}
    common = sorted(set(map_a) & set(map_b))
    return [map_a[t] for t in common], [map_b[t] for t in common]


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

    return [{"rank": i + 1, "baseline": name, "value": round(value, 2)} for i, (value, name) in enumerate(paired)]


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
        lines.append(f"| {rank_info['rank']} | {rank_info['baseline']} | {rank_info['value']} |")

    lines += [
        "",
        "## Coverage Ranking",
        "",
        "| Rank | Baseline | Avg Coverage (%) |",
        "|---|---|---|",
    ]

    for rank_info in analysis["rankings"]["coverage"]:
        lines.append(f"| {rank_info['rank']} | {rank_info['baseline']} | {rank_info['value']} |")

    lines += [
        "",
        "## Detailed Comparison",
        "",
        "| Baseline | Success Rate | Coverage | Iterations |",
        "|---|---|---|---|",
    ]

    for name, data in analysis["comparison"].items():
        lines.append(f"| {name} | {data['success_rate']}% | {data['coverage']}% | {data['iterations']} |")

    # 显著性检验结果（仅当实际完成检验时输出，否则如实说明原因）
    sig = analysis.get("significance", {})
    sig_status = sig.get("status", "insufficient_data")
    lines += ["", "## Significance Test", "", f"- 状态: {sig_status}"]
    if sig_status == "ok":
        lines += [
            "",
            "| 对比 | 方法 | 样本量 | t 统计量 | p 值 | 显著 (p<0.05) |",
            "|---|---|---|---|---|---|",
        ]
        for comp in sig.get("comparisons", []):
            lines.append(
                f"| {comp['comparison']} | {comp['method']} | {comp['n_a']}/{comp['n_b']} "
                f"| {comp['t_stat']} | {comp['p_value']} | {'是' if comp['significant'] else '否'} |"
            )
    else:
        lines.append(f"- 说明: {sig.get('note', '数据不足，未执行检验')}")

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
    with open(result_file, encoding="utf-8") as f:
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
