"""
实验结果结构化分析脚本（4.3）。

从 run_benchmark.py 输出的 JSON 结果中提取关键指标
（成功率、覆盖率、迭代次数分布、Token 消耗、RAG 检索质量），
生成 Markdown 汇总表格，减少手动分析 JSON 的工作量。

使用方式：
    python experiments/analyze_results.py --results-dir experiments/results
    python experiments/analyze_results.py --input experiments/results/benchmark_xxx.json

输出：
    - 终端打印 Markdown 汇总表格（可直接贴报告）
    - experiments/results/analysis_summary.md（与输入文件同目录的汇总文件）

指标口径说明：
    - 成功率/覆盖率/迭代/耗时：直接读 baseline 级聚合字段（success_rate /
      avg_coverage / avg_iterations / avg_elapsed_seconds）；
    - Token 效率：优先读 baseline 级 token_metrics（run_benchmark 09-13 轮次
      起输出）；旧 JSON 无该字段时从 details[].token_usage 逐任务累加兜底；
    - 迭代分布：从 details[].iterations 统计 0/1/2/3+ 的分布（反映"一次
      修复成功率 vs 需多轮调试"）；
    - 失败原因分布：从 details[].error_category 统计（配合 1.2 错误分类
      细化，LLM_FORMAT_ERROR / INDEX_ERROR 从此可单独计数）；
    - RAG 质量：读 baseline 级 rag_metrics（未启用 RAG 时全 0/None，跳过输出）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def load_latest_benchmark(results_dir: str = "experiments/results") -> str:
    """找到结果目录下最新的 benchmark JSON 文件（文件名倒序）。

    与 visualize_results.load_latest_result 同口径：仅识别 benchmark_* 前缀
    （避免误选 swebench_20_summary.json / performance_benchmark.json 等汇总文件）。
    """
    all_json = [f for f in os.listdir(results_dir) if f.endswith(".json")]
    benchmark_files = [f for f in all_json if f.startswith("benchmark_")]
    if not benchmark_files:
        benchmark_files = all_json
    if not benchmark_files:
        raise FileNotFoundError(f"结果目录 {results_dir} 下没有 JSON 文件")
    return os.path.join(results_dir, sorted(benchmark_files, reverse=True)[0])


def _token_metrics_from_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    """旧版 JSON（无 baseline 级 token_metrics）兜底：从逐任务 token_usage 累加。"""
    total_input = sum((r.get("token_usage") or {}).get("input_tokens", 0) for r in details)
    total_output = sum((r.get("token_usage") or {}).get("output_tokens", 0) for r in details)
    total_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in details)
    total = len(details)
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_llm_calls": total_calls,
        "avg_tokens_per_task": round((total_input + total_output) / total, 2) if total > 0 else 0,
    }


def build_analysis(data: dict[str, Any]) -> dict[str, Any]:
    """从 benchmark JSON 构建结构化分析结果。

    Args:
        data: run_benchmark.py 输出的完整 JSON（含 results.<baseline>.details）。

    Returns:
        分析字典：meta（数据集/基线/开关）、per_baseline（逐基线指标）、
        iteration_distribution、failure_category_distribution。
    """
    results = data.get("results", {})
    baselines = list(results.keys())

    per_baseline: dict[str, dict[str, Any]] = {}
    iteration_counter: Counter = Counter()

    for baseline in baselines:
        bl = results[baseline]
        details = bl.get("details", [])
        # Token 指标：优先 baseline 级 token_metrics，旧 JSON 无该键时逐任务累加兜底
        token_metrics = bl.get("token_metrics")
        if token_metrics is None:
            token_metrics = _token_metrics_from_details(details)
        # RAG 质量：旧 JSON 无该键时为 None（渲染时跳过 RAG 章节）
        rag_metrics = bl.get("rag_metrics")
        # 失败原因分布：优先 baseline 级聚合（run_benchmark 09-14 轮次起输出），
        # 旧 JSON 无该键时从 details[].error_category 兜底统计
        failure_dist = bl.get("failure_category_distribution")
        if failure_dist is None:
            counter: Counter = Counter()
            for r in details:
                if not r.get("passed") and r.get("error_category"):
                    counter[r["error_category"]] += 1
            failure_dist = dict(counter.most_common())
        per_baseline[baseline] = {
            "total_functions": bl.get("total_functions", len(details)),
            "passed_count": bl.get("passed_count", 0),
            "success_rate": bl.get("success_rate", 0.0),
            "avg_coverage": bl.get("avg_coverage", 0.0),
            "avg_iterations": bl.get("avg_iterations", 0.0),
            "avg_elapsed_seconds": bl.get("avg_elapsed_seconds", 0.0),
            "total_time": bl.get("total_time", 0.0),
            "token_metrics": token_metrics,
            "rag_metrics": rag_metrics,
            "failure_category_distribution": failure_dist,
        }
        # 迭代次数分布（0 = 一次通过，1/2/3 = 调试轮数，>=3 归入 3+）
        for r in details:
            iteration_counter[min(r.get("iterations", 0), 3)] += 1

    return {
        "meta": {
            "dataset": data.get("dataset"),
            "timestamp": data.get("timestamp"),
            "baselines": baselines,
            "enable_planner": data.get("enable_planner"),
            "enable_debugger": data.get("enable_debugger"),
            "enable_rag": data.get("enable_rag"),
            "total_tasks": data.get("total_tasks"),
        },
        "per_baseline": per_baseline,
        "iteration_distribution": {str(k): iteration_counter.get(k, 0) for k in range(4)},
    }


def render_markdown(analysis: dict[str, Any], source_file: str) -> str:
    """把分析结果渲染为 Markdown 汇总表格（可直接贴实验报告）。"""
    meta = analysis["meta"]
    per = analysis["per_baseline"]
    lines: list[str] = []
    lines.append("# 实验结果汇总")
    lines.append("")
    lines.append(f"- 数据集: {meta.get('dataset')}")
    lines.append(f"- 结果文件: `{source_file}`")
    lines.append(f"- 任务数: {meta.get('total_tasks')}")
    lines.append(
        f"- 消融开关: planner={meta.get('enable_planner')} debugger={meta.get('enable_debugger')}"
        f" rag={meta.get('enable_rag')}"
    )
    lines.append("")

    # 核心指标对比表
    lines.append("## 核心指标对比")
    lines.append("")
    lines.append("| 基线 | 成功率 | 平均覆盖率 | 平均迭代 | 平均耗时(s) | 总耗时(s) |")
    lines.append("|------|--------|-----------|---------|------------|-----------|")
    for baseline, m in per.items():
        lines.append(
            f"| {baseline} | {m['success_rate']}% | {m['avg_coverage']}% "
            f"| {m['avg_iterations']} | {m['avg_elapsed_seconds']} | {m['total_time']} |"
        )
    lines.append("")

    # Token 效率对比（2.2 公平性：效果-效率二维对照，不只看成功率）
    lines.append("## Token 效率对比")
    lines.append("")
    lines.append("| 基线 | 总Token | 输入 | 输出 | LLM调用次数 | 平均每任务Token |")
    lines.append("|------|---------|------|------|------------|----------------|")
    for baseline, m in per.items():
        t = m["token_metrics"]
        lines.append(
            f"| {baseline} | {t.get('total_tokens', 0)} | {t.get('total_input_tokens', 0)} "
            f"| {t.get('total_output_tokens', 0)} | {t.get('total_llm_calls', 0)} "
            f"| {t.get('avg_tokens_per_task', 0)} |"
        )
    lines.append("")

    # 迭代次数分布
    dist = analysis["iteration_distribution"]
    lines.append("## 迭代次数分布（全基线合计）")
    lines.append("")
    lines.append("| 迭代轮数 | 任务数 |")
    lines.append("|---------|--------|")
    labels = {"0": "0（一次通过）", "1": "1", "2": "2", "3": "3+"}
    for k in ("0", "1", "2", "3"):
        lines.append(f"| {labels[k]} | {dist.get(k, 0)} |")
    lines.append("")

    # 失败原因分布（按基线输出；1.2 细化后 LLM_FORMAT_ERROR / INDEX_ERROR 可单独计数）
    fail_rows = [
        (b, m["failure_category_distribution"]) for b, m in per.items() if m.get("failure_category_distribution")
    ]
    if fail_rows:
        lines.append("## 失败原因分布（按基线）")
        lines.append("")
        for baseline, dist in fail_rows:
            lines.append(f"### {baseline}")
            lines.append("")
            lines.append("| 错误类别 | 次数 |")
            lines.append("|---------|------|")
            for cat, cnt in dist.items():
                lines.append(f"| {cat} | {cnt} |")
            lines.append("")

    # RAG 检索质量（仅当有 rag_metrics 且启用 RAG 时输出）
    rag_rows = [
        (b, m["rag_metrics"])
        for b, m in per.items()
        if m.get("rag_metrics") and m["rag_metrics"].get("retrievals", 0) > 0
    ]
    if rag_rows:
        lines.append("## RAG 检索质量")
        lines.append("")
        lines.append("| 基线 | 检索次数 | 命中次数 | 命中率 | 平均最高相似度 |")
        lines.append("|------|---------|---------|--------|----------------|")
        for baseline, rag in rag_rows:
            lines.append(
                f"| {baseline} | {rag.get('retrievals', 0)} | {rag.get('hits', 0)} "
                f"| {rag.get('hit_rate', 0.0)} | {rag.get('avg_max_similarity')} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="AITester 实验结果结构化分析（4.3）")
    parser.add_argument("--results-dir", default="experiments/results", help="结果目录（自动找最新 benchmark JSON）")
    parser.add_argument("--input", default=None, help="直接指定单个 benchmark JSON 文件（优先于 --results-dir）")
    parser.add_argument(
        "--output", default=None, help="Markdown 汇总输出路径（默认 <输入文件同目录>/analysis_summary.md）"
    )
    args = parser.parse_args()

    if args.input:
        input_file = args.input
    else:
        input_file = load_latest_benchmark(args.results_dir)

    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    analysis = build_analysis(data)
    markdown = render_markdown(analysis, os.path.basename(input_file))

    print(markdown)

    output_path = args.output or os.path.join(os.path.dirname(os.path.abspath(input_file)), "analysis_summary.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown + "\n")
    print(f"\n汇总已写入: {output_path}")


if __name__ == "__main__":
    main()
