"""
实验结果结构化分析脚本（4.3）。

从 run_benchmark.py 输出的 JSON 结果中提取关键指标
（成功率、覆盖率、迭代次数分布、Token 消耗、RAG 检索质量、修复收敛效率、
多维质量代理、测试异味检测、依赖缓存命中统计），生成 Markdown 汇总表格，
减少手动分析 JSON 的工作量。

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
    - RAG 质量：读 baseline 级 rag_metrics（未启用 RAG 时全 0/None，跳过输出）；
    - 修复收敛效率：首次尝试成功率、成功任务平均/中位迭代数、成功任务平均
      耗时，均从 details[] 可复算；
    - 多维质量代理：断言强度（1.3 增强为 AST 静态分析口径，行数统计保留），
      结构/运行时质量用覆盖率与耗时变化做保守代理；旧 JSON 缺 optional 字段时
      只输出可计算部分，不崩溃；
    - 边界用例覆盖（1.3）：AST 保守判定 generated_test 是否覆盖 None/空集合/
      0/-1/>=/<= 等边界条件；无 generated_test 时跳过章节；
    - 变异得分（1.3）：收集 details[].mutation_score（外部变异测试器产出），
      无该字段时跳过章节；
    - 收敛失败模式归因（1.2）：区分"无法定位根因"（诊断反复同义）与
      "无法生成有效补丁"（写盘/守卫反复拒绝）；
    - 执行反馈轨迹汇总（3.2）：收集 details[].execution_trace（executor 节点
      默认常开写入），统计总执行次数/首轮即通过率/末轮奖励信号/覆盖率趋势。
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

# 0.7 债务项 1.6：统计函数按主题拆至 analysis_parts 子包，此处 re-export 保持
# 历史 import 路径（experiments.analyze_results._xxx）不变，默认行为零变化。
# re-export 符号供外部测试（tests/test_smell_detection_v2.py 等）与同包脚本
# import，本文件内部不直接调用 → 各 import 行标 noqa F401
from experiments.analysis_parts.convergence_analysis import (  # noqa: E402,F401
    _assertion_counts_from_row,
    _assertion_strength_proxy,
    _boundary_case_coverage,
    _convergence_failure_modes,
    _convergence_token_efficiency,
    _cross_baseline_convergence_comparison,
    _cross_file_failure_analysis,
    _difficulty_stratified_iterations,
    _execution_trace_summary,
    _failure_root_cause_trend,
    _failure_top_categories,
    _mutation_score_metrics,
    _quality_proxy_metrics,
    _repair_convergence_curve,
    _repair_convergence_metrics,
    _smell_task_has_smell,
    _test_smell_detection,
)
from experiments.analysis_parts.cross_analysis import (  # noqa: E402
    _contamination_cross_analysis,
    _venv_cache_stats_snapshot,
)
from experiments.analysis_parts.rag_analysis import (  # noqa: E402
    _rag_by_kind_from_details,
    _rag_hit_by_failure_category,
    _rag_similarity_distribution,
    _rag_token_efficiency,
    _token_metrics_from_details,
)

# 2.1 数据污染检测模块（experiments 包内相对导入，sys.path 注入后方可用）
from experiments.contamination_check import (  # noqa: E402
    detect_contamination,
    render_contamination_section,
    render_resistant_benchmark_section,
)
from experiments.difficulty_stratification import render_stratification_section  # noqa: E402


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


def build_analysis(data: dict[str, Any], golden_patches: dict[str, str] | None = None) -> dict[str, Any]:
    """从 benchmark JSON 构建结构化分析结果。

    Args:
        data: run_benchmark.py 输出的完整 JSON（含 results.<baseline>.details）。
        golden_patches: 2.1 数据污染检测的 task_id → 官方黄金补丁映射
            （显式传入时覆盖结果自带字段；None 时仅用 details 自带 golden_patch）。

    Returns:
        分析字典：meta（数据集/基线/开关）、per_baseline（逐基线指标）、
        iteration_distribution、venv_cache_stats。
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
            # 2.3 RAG 指标自动汇总（从 details[].rag_stats 计算，旧 JSON 无 rag_stats 时为空）
            "details_rag_by_kind": _rag_by_kind_from_details(details),
            "rag_hit_by_failure_category": _rag_hit_by_failure_category(details),
            # 1.2 修复收敛效率 + 1.1 多维质量代理（从 details 可复算，旧 JSON 容错）
            "repair_convergence_metrics": _repair_convergence_metrics(details),
            # 1.3 修复收敛曲线（按迭代轮次累计通过率）
            "repair_convergence_curve": _repair_convergence_curve(details),
            # 1.2 测试异味检测（LLM 生成测试的可维护性代理；含异味密度与按策略分组）
            "test_smell_metrics": _test_smell_detection(details),
            "quality_proxy_metrics": _quality_proxy_metrics(details),
            # 1.3 修复收敛的 Token 效率曲线（逐轮增量 Token 与增量通过率，回答
            # "第几轮修复边际收益最高"）
            "convergence_token_efficiency": _convergence_token_efficiency(details),
            # 1.3 修复迭代分布的难度分层统计（按 task_id 难度档分组的迭代分布）
            "difficulty_stratified_iterations": _difficulty_stratified_iterations(details),
            # 2.3 RAG Token 效率增益 + 相似度分布（启用/禁用 RAG 的 Token/迭代对比
            # 与检索相关性的直方图分桶）
            "rag_token_efficiency": _rag_token_efficiency(details),
            "rag_similarity_distribution": _rag_similarity_distribution(details),
            # 5.3 失败根因时间趋势（llm_capability / dependency / framework 三类
            # 在任务序列中的占比变化，判断系统优化是否有效）
            "failure_root_cause_trend": _failure_root_cause_trend(details),
            # 5.3 失败分析 × 污染检测交叉（验证"高污染风险任务是否成功率更高"）
            "contamination_cross_analysis": _contamination_cross_analysis(details),
            # 2.1 数据污染检测（details 携带 patch + task_metadata.golden_patch 时计算重叠度）
            "contamination_report": detect_contamination(details, golden_patches),
            # 1.3 边界用例覆盖（generated_test 含边界值时统计，旧 JSON 无该字段时全 0）
            "boundary_coverage_metrics": _boundary_case_coverage(details),
            # 1.3 变异得分（保守代理：从 details[].mutation_score 字段收集；
            # 无该字段时 available=False，渲染时跳过章节）
            "mutation_score_metrics": _mutation_score_metrics(details),
            # 1.2 收敛失败模式归因（达到 MAX_ITERATIONS 仍未修复的任务，
            # 区分"无法定位根因" vs "无法生成有效补丁"）
            "convergence_failure_modes": _convergence_failure_modes(details),
            # 3.2 执行轨迹汇总（details[].execution_trace 收集，旧 JSON 无该字段时跳过）
            "execution_trace_metrics": _execution_trace_summary(details),
            # 2.2 难度分层渲染所需的原始 details（render 消费，不参与 JSON 序列化输出）
            "_details": details,
        }
        # 迭代次数分布（0 = 一次通过，1/2/3 = 调试轮数，>=3 归入 3+）
        for r in details:
            iteration_counter[min(r.get("iterations", 0), 3)] += 1

    cross_baseline = _cross_baseline_convergence_comparison(per_baseline)
    cross_file_failure = _cross_file_failure_analysis(per_baseline)
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
        # 4.4 依赖缓存命中统计（无缓存事件时为 None，渲染时跳过章节）
        "venv_cache_stats": _venv_cache_stats_snapshot(),
        # 1.3 跨基线收敛对比（叠加 aitester 与各 plain_llm 基线的收敛曲线）
        "cross_baseline_convergence": cross_baseline,
        # 2.2 跨文件修复失败案例分析（失败类别分布 + import 相关信号占比）
        "cross_file_failure_analysis": cross_file_failure,
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
    lines.extend(f"| {labels[k]} | {dist.get(k, 0)} |" for k in ("0", "1", "2", "3"))
    lines.append("")

    # 修复收敛效率（1.2）
    conv_rows = [
        (b, m["repair_convergence_metrics"])
        for b, m in per.items()
        if m.get("repair_convergence_metrics", {}).get("total_tasks", 0) > 0
    ]
    if conv_rows:
        lines.append("## 修复收敛效率（1.2）")
        lines.append("")
        lines.append(
            "| 基线 | 任务数 | 成功 | 首次通过率 | 成功任务平均迭代 | 成功任务中位迭代 | 成功任务平均耗时(s) |"
        )
        lines.append("|------|--------|------|-----------|----------------|----------------|--------------------|")
        for baseline, c in conv_rows:
            s = c.get("success_iteration_stats", {})
            e = c.get("success_elapsed_seconds", {})
            lines.append(
                f"| {baseline} | {c.get('total_tasks', 0)} | {c.get('success_tasks', 0)} "
                f"| {c.get('first_attempt_success_rate', 0.0)} | {s.get('avg')} | {s.get('median')} "
                f"| {e.get('avg')} |"
            )
        lines.append("")
        lines.append("> 解读：首次通过率反映无需修复即通过的任务占比；成功任务平均/中位迭代刻画收敛速度。")
        lines.append("")

    # 修复收敛曲线（1.3）：按迭代轮次 0/1/2/3+ 统计累计通过率
    curve_rows = [
        (b, m["repair_convergence_curve"])
        for b, m in per.items()
        if m.get("repair_convergence_curve", {}).get("total_tasks", 0) > 0
        and m["repair_convergence_curve"].get("rounds")
    ]
    if curve_rows:
        lines.append("## 修复收敛曲线（1.3）")
        lines.append("")
        lines.append("按迭代轮次累计（0=首次生成即通过；1/2/3+=调试轮次）。")
        lines.append("")
        lines.append("| 基线 | 轮次 | 到达任务数 | 累计通过 | 累计通过率 | 累计平均耗时(s) |")
        lines.append("|------|------|-----------|---------|-----------|----------------|")
        for baseline, curve in curve_rows:
            total = curve.get("total_tasks", 0)
            for k in ("0", "1", "2", "3+"):
                r = curve.get("rounds", {}).get(k)
                if not r:
                    continue
                lines.append(
                    f"| {baseline} | {k} | {r.get('reached_tasks', 0)} "
                    f"| {r.get('cumulative_passed', 0)} | {r.get('cumulative_pass_rate', 0.0)} "
                    f"| {r.get('cumulative_elapsed_seconds')} |"
                )
            # 分母（总任务数）在首次出现时标注
            lines.append(f"| {baseline} | 总任务 | {total} | — | — | — |")
        lines.append("")
        lines.append("> 解读：累计通过率随迭代轮次单调不减；若 0 轮即接近 1.0 说明任务简单或系统一次修复能力强。")
        lines.append("")

    # 修复收敛 Token 效率曲线（1.3）：逐轮增量 Token 与增量通过率的边际收益
    conv_token_rows = [
        (b, m["convergence_token_efficiency"])
        for b, m in per.items()
        if m.get("convergence_token_efficiency", {}).get("available")
    ]
    if conv_token_rows:
        lines.append("## 修复收敛 Token 效率曲线（1.3）")
        lines.append("")
        lines.append("| 基线 | 轮次 | 到达任务 | 增量通过 | 增量Token | 边际收益(通过/Token) | 最佳边际轮次 |")
        lines.append("|------|------|---------|---------|----------|--------------------|------------|")
        for baseline, ct in conv_token_rows:
            total = ct.get("total_tasks", 0)
            best = ct.get("best_marginal_round")
            for k in ("0", "1", "2", "3+"):
                r = ct.get("rounds", {}).get(k)
                if not r:
                    continue
                marginal = r.get("marginal_pass_per_token")
                marginal_text = f"{marginal:.4f}" if marginal is not None else "N/A"
                lines.append(
                    f"| {baseline} | {k} | {r.get('reached_tasks', 0)} "
                    f"| {r.get('incremental_passed', 0)} | {r.get('incremental_tokens', 0)} "
                    f"| {marginal_text} | {best if k == '3+' else '—'} |"
                )
            lines.append(f"| {baseline} | 总任务 | {total} | — | — | — | — |")
        lines.append("")
        lines.append(
            "> 解读：边际收益 = 该轮增量通过任务数 / 该轮增量 Token 消耗；"
            'best_marginal_round 标记"第几轮修复最划算"（边际收益最高的轮次），'
            '用于回答"第几轮修复的边际收益最高"。'
        )
        lines.append("")

    # 修复迭代分布的难度分层统计（1.3）
    diff_iter_rows = [
        (b, m["difficulty_stratified_iterations"])
        for b, m in per.items()
        if m.get("difficulty_stratified_iterations", {}).get("available")
    ]
    if diff_iter_rows:
        lines.append("## 修复迭代分布（按难度分层，1.3）")
        lines.append("")
        lines.append("| 基线 | 难度档 | 任务数 | 0迭代 | 1迭代 | 2迭代 | 3+迭代 |")
        lines.append("|------|--------|--------|-------|-------|-------|--------|")
        for baseline, di in diff_iter_rows:
            for band, stat in di["bands"].items():
                it = stat.get("iterations", {})
                lines.append(
                    f"| {baseline} | {band} | {stat.get('total', 0)} "
                    f"| {it.get('0', 0)} | {it.get('1', 0)} | {it.get('2', 0)} | {it.get('3+', 0)} |"
                )
        lines.append("")
        lines.append(
            "> 注：难度档由 task_id 外部映射（difficulty_bands）提供；未提供时全部任务"
            "归入 unstratified 档。用于对比不同难度下修复迭代次数的分布差异。"
        )
        lines.append("")

    # 测试异味检测（1.2）：LLM 生成测试的可维护性代理
    smell_rows = [
        (b, m["test_smell_metrics"]) for b, m in per.items() if m.get("test_smell_metrics", {}).get("available")
    ]
    if smell_rows:
        lines.append("## 测试异味检测（1.2）")
        lines.append("")
        lines.append(
            "| 基线 | 观测任务 | Assertion Roulette | Magic Number | 断言弱化 | 平凡测试 | Eager Test | 缺乏内聚 | 异味密度 | 含异味任务 |"
        )
        lines.append(
            "|------|---------|-------------------|--------------|---------|---------|----------|---------|--------|----------|"
        )
        for baseline, s in smell_rows:
            c = s.get("smell_counts", {})
            lines.append(
                f"| {baseline} | {s.get('observed_tasks', 0)} "
                f"| {c.get('assertion_roulette', 0)} | {c.get('magic_number', 0)} "
                f"| {c.get('assertion_weakening', 0)} | {c.get('trivial_test', 0)} "
                f"| {c.get('eager_test', 0)} | {c.get('lack_of_cohesion', 0)} "
                f"| {s.get('smell_density', 0.0)} | {len(s.get('tasks_with_smells', []))} |"
            )
        lines.append("")
        # 按策略分组的异味分布对比（1.1 改进：异味模式受提示策略显著影响）
        strategy_rows = [(b, s) for b, s in smell_rows if s.get("smell_counts_by_strategy")]
        if strategy_rows:
            lines.append("### 异味分布按生成策略分组")
            lines.append("")
            lines.append("| 基线 | 策略 | 观测任务 | 异味密度 | Eager Test | 缺乏内聚 | Magic Number |")
            lines.append("|------|------|---------|--------|----------|---------|-------------|")
            for baseline, s in strategy_rows:
                for strategy, stat in s["smell_counts_by_strategy"].items():
                    sc = stat.get("smell_counts", {})
                    lines.append(
                        f"| {baseline} | {strategy} | {stat.get('observed_tasks', 0)} "
                        f"| {stat.get('smell_density', 0.0)} | {sc.get('eager_test', 0)} "
                        f"| {sc.get('lack_of_cohesion', 0)} | {sc.get('magic_number', 0)} |"
                    )
            lines.append("")
            lines.append(
                "> 解读：对比不同生成策略（如 planner/generator/debugger 消融）的异味密度，"
                "可定位哪类提示策略产出异味更多；若某策略的 Eager Test 显著偏高，"
                "提示该策略倾向让单个测试方法验证过多功能。"
            )
            lines.append("")
        lines.append("> 注：测试异味检测基于 details[].generated_test 字段的保守启发式；")
        lines.append("仅当结果 JSON 携带该字段时可用，否则章节跳过。")
        lines.append("")

    # 多维质量代理（1.1）
    quality_rows = [(b, m["quality_proxy_metrics"]) for b, m in per.items() if m.get("quality_proxy_metrics")]
    if quality_rows:
        lines.append("## 多维质量代理（1.1，保守可复算）")
        lines.append("")
        lines.append("| 基线 | 成功覆盖率均值 | 失败覆盖率均值 | 成功耗时均值(s) | 失败耗时均值(s) | 断言强度代理 |")
        lines.append("|------|---------------|---------------|----------------|----------------|--------------|")
        for baseline, q in quality_rows:
            cp = q.get("coverage_proxy", {})
            rp = q.get("runtime_proxy", {})
            ap = q.get("assertion_proxy", {})
            if ap.get("available"):
                assertion_text = f"{ap.get('avg_assertions_per_task')} 断言/任务（min={ap.get('min_assertions')}, max={ap.get('max_assertions')}）"
            else:
                assertion_text = "N/A（结果未携带 generated_test）"
            lines.append(
                f"| {baseline} "
                f"| {cp.get('success', {}).get('mean')} "
                f"| {cp.get('failed', {}).get('mean')} "
                f"| {rp.get('success', {}).get('mean')} "
                f"| {rp.get('failed', {}).get('mean')} "
                f"| {assertion_text} |"
            )
        lines.append("")
        lines.append(
            "> 注：该章节为保守代理指标（基于现有结果字段），不等同于 AST 圈复杂度、内存占用等精确结构/性能指标；"
            "断言强度代理仅在结果 JSON 的 details[].generated_test 提供时可用。"
        )
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

        # 2.3 RAG 指标自动汇总：按检索类型分解（test_cases vs repairs）
        # 分析"哪类检索（参考测试风格 / 参考修复方案）命中更好"
        by_kind_rows = [(b, m) for b, m in per.items() if m.get("details_rag_by_kind")]
        if by_kind_rows:
            lines.append("### RAG 检索质量按检索类型分解")
            lines.append("")
            lines.append("| 基线 | 类型 | 检索次数 | 命中次数 | 命中率 | 平均最高相似度 |")
            lines.append("|------|------|---------|---------|--------|----------------|")
            for baseline, m in by_kind_rows:
                for kind, kstat in m["details_rag_by_kind"].items():
                    lines.append(
                        f"| {baseline} | {kind} | {kstat.get('retrievals', 0)} | {kstat.get('hits', 0)} "
                        f"| {kstat.get('hit_rate', 0.0)} | {kstat.get('avg_max_similarity')} |"
                    )
            lines.append("")

        # 2.3 RAG 指标自动汇总：RAG 命中 × 失败类别交叉表
        # 分析"RAG 对哪些错误类型修复帮助最大"（断言 vs 运行时等）
        cross_rows = [(b, m) for b, m in per.items() if m.get("rag_hit_by_failure_category")]
        if cross_rows:
            lines.append("### RAG 命中 × 失败类别交叉表")
            lines.append("")
            lines.append("失败任务按 error_category 分组，统计其 RAG 检索命中情况。")
            lines.append("")
            lines.append("| 基线 | 失败类别 | 任务数 | 其中 RAG 有命中 | 命中占比 |")
            lines.append("|------|---------|--------|----------------|----------|")
            for baseline, m in cross_rows:
                for cat, cstat in m["rag_hit_by_failure_category"].items():
                    total = cstat.get("total", 0)
                    hit_rate = round(cstat.get("with_hit", 0) / total, 4) if total else 0.0
                    lines.append(f"| {baseline} | {cat} | {total} | {cstat.get('with_hit', 0)} | {hit_rate} |")
            lines.append("")
            lines.append(
                "> 解读：`rag_retrieval_empty` 类任务（1.1 状态细化）即"
                "RAG 全部检索未命中的任务，其命中占比必为 0；"
                "若某具体类别（如 assertion）的命中占比明显高于其他类别，"
                "说明 RAG 对该类错误修复帮助最大。"
            )
            lines.append("")

    # 2.1 数据污染检测章节（details 携带 patch 与 golden_patch 时输出）
    contam_rows = [
        (b, m.get("contamination_report"))
        for b, m in per.items()
        if m.get("contamination_report", {}).get("checked", 0) > 0
    ]
    for baseline, report in contam_rows:
        lines.extend(render_contamination_section(report, baseline))
    if contam_rows:
        # 2.1 改进：抗污染基准交叉验证建议（成对报告 SWE-rebench 等）
        lines.extend(render_resistant_benchmark_section())

    # 2.3 RAG Token 效率增益 + 相似度分布（启用/禁用 RAG 对比）
    rag_token_rows = [
        (b, m["rag_token_efficiency"]) for b, m in per.items() if m.get("rag_token_efficiency", {}).get("available")
    ]
    if rag_token_rows:
        lines.append("## RAG Token 效率增益（2.3）")
        lines.append("")
        lines.append(
            "| 基线 | RAG组(任务数) | RAG组平均Token | RAG组成功率 | 无RAG组(任务数) | 无RAG组平均Token | 无RAG组成功率 | Token比率 | 迭代差 |"
        )
        lines.append(
            "|------|--------------|---------------|-----------|----------------|-----------------|-------------|----------|--------|"
        )
        for baseline, rt in rag_token_rows:
            g = rt.get("rag_group", {})
            ng = rt.get("no_rag_group", {})
            ratio = rt.get("token_delta_ratio")
            ratio_text = f"{ratio:.2f}" if ratio is not None else "N/A"
            lines.append(
                f"| {baseline} | {g.get('tasks', 0)} | {g.get('avg_tokens', 0)} "
                f"| {g.get('success_rate', 0.0)} | {ng.get('tasks', 0)} | {ng.get('avg_tokens', 0)} "
                f"| {ng.get('success_rate', 0.0)} | {ratio_text} | {rt.get('iteration_delta', 0.0)} |"
            )
        lines.append("")
        lines.append(
            "> 解读：Token 比率 > 1 表示启用 RAG 的任务消耗更多 Token（检索 + 提示注入开销）；"
            '结合成功率差异判断 RAG 的"性价比"——若成功率提升足以抵消 Token 开销则值得，'
            "否则应考虑降低 top_k 或检索阈值。"
        )
        lines.append("")

    rag_sim_rows = [
        (b, m["rag_similarity_distribution"])
        for b, m in per.items()
        if m.get("rag_similarity_distribution", {}).get("available")
    ]
    if rag_sim_rows:
        lines.append("## RAG 检索相似度分布（2.3）")
        lines.append("")
        lines.append("| 基线 | 总检索数 | 平均最高相似度 | 分布（相似度分桶） |")
        lines.append("|------|---------|---------------|------------------|")
        for baseline, rs in rag_sim_rows:
            hist = rs.get("histogram", {})
            hist_text = ", ".join(f"{k}:{v}" for k, v in sorted(hist.items())) if hist else "—"
            lines.append(
                f"| {baseline} | {rs.get('total_retrievals', 0)} | {rs.get('avg_max_similarity')} | {hist_text} |"
            )
        lines.append("")
        lines.append(
            "> 解读：若检索相似度集中在 0.0-0.3 低相关区间，说明检索库与当前任务差异过大"
            "（冷启动或领域不匹配）；若集中在 0.7+ 高相关区间则检索质量良好。"
        )
        lines.append("")

    # 2.2 任务难度分层（code_size / dependency_count / complexity_proxy 三维度）
    for baseline, m in per.items():
        details = m.get("_details") or []
        if details:
            lines.extend(render_stratification_section(details, baseline))

    # 1.3 边界用例覆盖（generated_test 携带时输出）
    boundary_rows = [
        (b, m.get("boundary_coverage_metrics"))
        for b, m in per.items()
        if m.get("boundary_coverage_metrics", {}).get("available")
    ]
    if boundary_rows:
        lines.append("## 边界用例覆盖（1.3，AST 保守口径）")
        lines.append("")
        lines.append("| 基线 | 观测任务 | 覆盖任一边界任务 | 覆盖率 | 各边界类型命中 |")
        lines.append("|------|---------|-----------------|--------|--------------|")
        for baseline, bstat in boundary_rows:
            types = bstat.get("boundary_types") or {}
            type_text = ", ".join(f"{k}={v}" for k, v in sorted(types.items())) if types else "—"
            lines.append(
                f"| {baseline} | {bstat.get('observed_tasks', 0)} "
                f"| {bstat.get('tasks_covering_any_boundary', 0)} | {bstat.get('coverage_rate', 0.0)} "
                f"| {type_text} |"
            )
        lines.append("")
        lines.append(
            "> 注：边界类型由 generated_test 的 AST 保守判定（None/空字符串/0/-1/空集合/>=/<= 比较）；"
            "仅当结果 JSON 携带 details[].generated_test 时可用，否则章节跳过。"
        )
        lines.append("")

    # 1.3 变异得分（details 携带 mutation_score 字段时输出）
    mutation_rows = [
        (b, m.get("mutation_score_metrics"))
        for b, m in per.items()
        if m.get("mutation_score_metrics", {}).get("available")
    ]
    if mutation_rows:
        lines.append("## 变异得分（1.3，外部变异测试器产出）")
        lines.append("")
        lines.append("| 基线 | 观测任务 | 平均变异得分 | 高（≥0.7） | 低（<0.4） |")
        lines.append("|------|---------|-----------|----------|-----------|")
        for baseline, mstat in mutation_rows:
            lines.append(
                f"| {baseline} | {mstat.get('observed_tasks', 0)} "
                f"| {mstat.get('avg_mutation_score', 0.0)} | {mstat.get('high_score_tasks', 0)} "
                f"| {mstat.get('low_score_tasks', 0)} |"
            )
        lines.append(
            "> 注：变异得分由外部变异测试器（如 mutmut）产出，非默认流水线环节；"
            "仅当 details[].mutation_score 字段存在时输出本章节。"
        )
        lines.append("")
        # 1.2 改进：变异得分 × 断言强度交叉分析（验证两者一致性）
        cross_rows = [
            (b, m) for b, m in mutation_rows if m.get("mutation_score_metrics", {}).get("mutation_assertion_cross")
        ]
        if cross_rows:
            lines.append("### 变异得分 × 断言强度交叉分析")
            lines.append("")
            lines.append("| 基线 | 高变异得分(≥0.7)平均断言数 | 低变异得分(<0.4)平均断言数 | 是否一致 |")
            lines.append("|------|--------------------------|---------------------------|---------|")
            for baseline, m in cross_rows:
                cross = m["mutation_score_metrics"]["mutation_assertion_cross"]
                consistent = cross.get("consistent")
                consistent_text = "一致" if consistent is True else ("不一致" if consistent is False else "数据不足")
                lines.append(
                    f"| {baseline} | {cross.get('high_score_avg_assertions')} "
                    f"| {cross.get('low_score_avg_assertions')} | {consistent_text} |"
                )
            lines.append("")
            lines.append(
                '> 解读：若"一致"为真，说明断言强度越高的测试杀死的变异体越多'
                "（符合变异测试理论）；若为假，提示部分高变异得分任务的断言可能"
                "覆盖到测试本身而非被测代码。"
            )
            lines.append("")

    # 1.2 收敛失败模式归因
    mode_rows = [
        (b, m.get("convergence_failure_modes"))
        for b, m in per.items()
        if m.get("convergence_failure_modes", {}).get("available")
    ]
    if mode_rows:
        lines.append("## 收敛失败模式归因（1.2）")
        lines.append("")
        lines.append('达到 MAX_ITERATIONS（默认 3）仍未修复的任务，区分"无法定位根因"与"无法生成有效补丁"。')
        lines.append("")
        lines.append("| 基线 | 收敛失败任务 | 无法定位根因 | 无法生成有效补丁 |")
        lines.append("|------|------------|------------|----------------|")
        for baseline, fstat in mode_rows:
            lines.append(
                f"| {baseline} | {fstat.get('total_converged_failed', 0)} "
                f"| {fstat.get('root_cause_stuck', 0)} | {fstat.get('patch_generation_failed', 0)} |"
            )
        lines.append("")
        lines.append(
            "> 解读：无法定位根因 = 诊断文本反复同义且无有效补丁写盘；"
            "无法生成有效补丁 = 补丁曾写盘但未解决问题，或补丁被安全守卫反复拒绝。"
        )
        lines.append("")

    # 3.2 执行轨迹汇总（execution_trace 携带时输出）
    trace_rows = [
        (b, m.get("execution_trace_metrics"))
        for b, m in per.items()
        if m.get("execution_trace_metrics", {}).get("available")
    ]
    if trace_rows:
        lines.append("## 执行反馈轨迹汇总（3.2）")
        lines.append("")
        lines.append(
            "| 基线 | 观测任务 | 总执行次数 | 平均轮数 | 首轮即通过率 | 末轮 correctness | 末轮 efficiency | 首/末轮覆盖率 |"
        )
        lines.append(
            "|------|---------|----------|--------|------------|----------------|----------------|------------|"
        )
        for baseline, tstat in trace_rows:
            ct = tstat.get("coverage_trend") or {}
            cov_text = (
                f"{ct.get('first_round_avg')} → {ct.get('last_round_avg')}" if ct.get("delta") is not None else "N/A"
            )
            lines.append(
                f"| {baseline} | {tstat.get('observed_tasks', 0)} | {tstat.get('total_executions', 0)} "
                f"| {tstat.get('avg_executions_per_task', 0)} | {tstat.get('pass_on_first_rate', 0.0)} "
                f"| {tstat.get('avg_last_reward_correctness', 0.0)} | {tstat.get('avg_last_reward_efficiency', 0.0)} "
                f"| {cov_text} |"
            )
        lines.append("")
        lines.append(
            '> 解读：本轮次即通过率反映系统"一次做对"能力；末轮 correctness 均值即"收敛到通过"的成功率；'
            "末轮 efficiency 反映修复尝试的耗时效率；覆盖率趋势 delta > 0 表示迭代在提升覆盖。"
        )
        lines.append("")

    # 5.3 失败根因时间趋势（三类根因占比变化，判断系统优化是否有效）
    trend_rows = [
        (b, m["failure_root_cause_trend"])
        for b, m in per.items()
        if m.get("failure_root_cause_trend", {}).get("total_failed", 0) > 0
    ]
    if trend_rows:
        lines.append("## 失败根因时间趋势（5.3）")
        lines.append("")
        lines.append(
            "| 基线 | 失败任务 | LLM能力 | 依赖/环境 | 框架/基础设施 | 第一段LLM能力 | 第二段LLM能力 | 第三段LLM能力 |"
        )
        lines.append("|------|---------|--------|----------|--------------|-------------|-------------|-------------|")
        for baseline, tr in trend_rows:
            dist = tr.get("root_cause_distribution", {})
            rates = tr.get("root_cause_rates", {})
            trend = tr.get("trend_by_first_third", {})
            first = trend.get("first_third", {}).get("llm_capability", "—")
            second = trend.get("second_third", {}).get("llm_capability", "—")
            third = trend.get("third_third", {}).get("llm_capability", "—")
            lines.append(
                f"| {baseline} | {tr.get('total_failed', 0)} "
                f"| {dist.get('llm_capability', 0)} ({rates.get('llm_capability', 0.0)}) "
                f"| {dist.get('dependency', 0)} ({rates.get('dependency', 0.0)}) "
                f"| {dist.get('framework', 0)} ({rates.get('framework', 0.0)}) "
                f"| {first} | {second} | {third} |"
            )
        lines.append("")
        lines.append(
            "> 解读：若 LLM 能力类占比随批次下降（first→second→third 递减），"
            "说明系统修复逻辑在改善；若 framework 类占比上升，提示执行器/多候选"
            "等基础设施需排查。dependency 类占比高说明任务依赖缺失普遍，"
            "建议完善 venv 自动安装。"
        )
        lines.append("")

    # 5.3 失败分析 × 污染检测交叉（验证污染效应）
    contam_cross_rows = [
        (b, m["contamination_cross_analysis"])
        for b, m in per.items()
        if m.get("contamination_cross_analysis", {}).get("available")
    ]
    if contam_cross_rows:
        lines.append("## 失败分析 × 污染检测交叉（5.3）")
        lines.append("")
        lines.append("| 基线 | 高污染任务 | 高污染成功率 | 低污染任务 | 低污染成功率 | 成功率差（高-低） |")
        lines.append("|------|----------|------------|----------|------------|----------------|")
        for baseline, cc in contam_cross_rows:
            by_level = cc.get("by_risk_level", {})
            high = by_level.get("high", {})
            low = by_level.get("low", {})
            delta = cc.get("high_vs_low_success_delta")
            delta_text = f"{delta:.4f}" if delta is not None else "N/A"
            lines.append(
                f"| {baseline} | {high.get('tasks', 0)} | {high.get('success_rate', 0.0)} "
                f"| {low.get('tasks', 0)} | {low.get('success_rate', 0.0)} | {delta_text} |"
            )
        lines.append("")
        lines.append(
            '> 解读：若"成功率差（高-低）"为显著正值（≥0.2），提示高污染风险任务'
            '成功率异常偏高——系统可能在"背出"黄金补丁而非真正修复，论文中应'
            "单独标注含污染样本并补充 SWE-rebench 交叉验证；若差异 ≤0.2，"
            "说明污染效应不显著，结果可信度较高。"
        )
        lines.append("")

    # 4.4 依赖缓存命中统计（ExecutorAgent venv 磁盘缓存，无缓存事件时跳过）
    # 4.4 改进：total=0 时快照仍含容量信息（_venv_cache_stats_snapshot 不再返回 None），
    # 命中统计章节只在 total>0 时渲染；容量告警在 exceeded=True 时额外渲染
    cache_stats = analysis.get("venv_cache_stats")
    if cache_stats and cache_stats.get("total", 0) > 0:
        lines.append("## 依赖缓存命中统计（4.4）")
        lines.append("")
        lines.append("| venv 复用次数 | venv 新建次数 | 缓存命中率 | 缓存总大小(MB) | 超阈值 |")
        lines.append("|--------------|--------------|-----------|---------------|--------|")
        size_mb = cache_stats.get("size_mb")
        exceeded = cache_stats.get("exceeded")
        size_text = f"{size_mb}" if size_mb is not None else "—"
        exceed_text = "是" if exceeded is True else ("否" if exceeded is False else "—")
        lines.append(
            f"| {cache_stats.get('hits', 0)} | {cache_stats.get('creates', 0)} "
            f"| {cache_stats.get('hit_rate', 0.0)} | {size_text} | {exceed_text} |"
        )
        lines.append("")
        lines.append(
            "> 解读：命中率高说明任务依赖组合重复利用良好（相同依赖组合复用同一 venv，"
            "省去重建 1-3s/次）；若几乎全为新建，提示任务依赖差异过大或缓存目录被清理。"
        )
        if cache_stats.get("exceeded"):
            lines.append("")
            lines.append(
                f"⚠️ **缓存容量告警**：venv 缓存目录总大小 {size_mb} MB 超过阈值 "
                f"{cache_stats.get('threshold_mb')} MB，建议执行 "
                f"`clear_venv_cache(max_age_days=7)` 清理过期缓存。"
            )
            lines.append("")
        lines.append("")

    # 1.3 跨基线收敛对比：把 aitester 与各 plain_llm 变体的收敛曲线叠加，
    # 直观呈现多智能体协作在收敛速度上的优势
    xb = analysis.get("cross_baseline_convergence") or {}
    if xb.get("available"):
        lines.append("## 跨基线收敛对比（1.3）")
        lines.append("")
        lines.append("各基线修复收敛曲线叠加（按迭代轮次 0/1/2/3+ 对齐累计通过率）：")
        lines.append("")
        lines.append("| 基线 | 首轮即通过 | 第1轮累计 | 第2轮累计 | 第3+轮累计 |")
        lines.append("|------|-----------|----------|----------|----------|")
        aligned = xb.get("aligned_rounds", {})
        for baseline in xb.get("baselines", []):
            r0 = aligned.get("0", {}).get(baseline)
            r1 = aligned.get("1", {}).get(baseline)
            r2 = aligned.get("2", {}).get(baseline)
            r3 = aligned.get("3+", {}).get(baseline)
            lines.append(
                f"| {baseline} "
                f"| {r0 if r0 is not None else '—'} "
                f"| {r1 if r1 is not None else '—'} "
                f"| {r2 if r2 is not None else '—'} "
                f"| {r3 if r3 is not None else '—'} |"
            )
        lines.append("")
        first_delta = xb.get("first_attempt_delta")
        at1_delta = xb.get("cumulative_pass_rate_at_1_delta")
        if first_delta is not None or at1_delta is not None:
            lines.append("### 协作 vs 基线关键差异")
            lines.append("")
            lines.append("| 指标 | 差值（aitester - plain_llm） | 解读 |")
            lines.append("|------|------------------------------|------|")
            if first_delta is not None:
                lines.append(
                    f"| 首轮即通过率差 | {first_delta:+.4f} | 正值 = 多智能体协作首轮成功率更高（一次做对能力领先） |"
                )
            if at1_delta is not None:
                lines.append(
                    f"| 第1轮累计通过率差 | {at1_delta:+.4f} | 正值 = 协作机制的增益来自'一次做对'而非'多轮调试追平' |"
                )
            lines.append("")
        lines.append(
            "> 注：各基线任务数可能不同，对比使用'通过率'（分母各自独立）；"
            "若 plain_llm 基线未参与本次运行，差值为 None，渲染层仅输出叠加表。"
        )
        lines.append("")

    # 2.2 跨文件修复失败案例分析（启用跨文件修复的基线中失败任务的
    # 错误类别分布 + import 相关信号占比）
    xf = analysis.get("cross_file_failure_analysis") or {}
    if xf.get("available"):
        lines.append("## 跨文件修复失败案例分析（2.2）")
        lines.append("")
        for baseline, stat in xf.get("by_baseline", {}).items():
            lines.append(f"### {baseline}")
            lines.append("")
            lines.append(f"- 总任务: {stat.get('total', 0)}，失败: {stat.get('failed', 0)}")
            cats = stat.get("failed_categories", {})
            if cats:
                lines.append(f"- 失败类别分布: {', '.join(f'{k}={v}' for k, v in cats.items())}")
            lines.append(f"- 诊断含 import/module/模块 关键词的失败任务: {stat.get('import_related_failed', 0)}")
            lines.append("")
        ir_rate = xf.get("import_related_rate")
        if ir_rate is not None:
            lines.append(f"> 整体 import 相关失败占比: {ir_rate:.2%}（跨文件修复失败典型表征）")
            lines.append("")
            if ir_rate >= 0.3:
                lines.append(
                    "> 解读：import 相关失败占比 ≥30%，提示跨文件场景下模块路径/导入关系"
                    "未正确处理是主要失败模式；建议检查 cross_file_analyzer 的依赖边"
                    "分析是否覆盖了被调用方视角（CROSS_FILE_BIDIRECTIONAL=true）。"
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
    parser.add_argument(
        "--golden-patches",
        default=None,
        help="2.1 数据污染检测：task_id → 官方黄金补丁文本 的 JSON 文件路径"
        "（JSON 对象 {task_id: patch_text}；未指定时仅用结果自带 golden_patch 字段）",
    )
    args = parser.parse_args()

    input_file = args.input or load_latest_benchmark(args.results_dir)

    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    golden_patches: dict[str, str] | None = None
    if args.golden_patches:
        with open(args.golden_patches, encoding="utf-8") as f:
            golden_patches = json.load(f)

    analysis = build_analysis(data, golden_patches=golden_patches)
    markdown = render_markdown(analysis, os.path.basename(input_file))

    print(markdown)

    output_path = args.output or os.path.join(os.path.dirname(os.path.abspath(input_file)), "analysis_summary.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown + "\n")
    print(f"\n汇总已写入: {output_path}")


if __name__ == "__main__":
    main()
