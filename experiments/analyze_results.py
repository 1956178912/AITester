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
      默认常开写入），统计总执行次数/首轮即通过率/末轮奖励信号/覆盖率趋势；
    - M1 指标汇总（R2，2026-10-05 审查）：收集 details[].detection_rate /
      repair_rate / false_fix_rate / test_error_rate（run_benchmark._m1_metrics
      的逐任务产物，可能为 None 表示不可测），None 不计入分母——各指标
      输出可测任务数与非 None 均值；旧 JSON 无该字段时章节自动跳过。
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
from experiments._patch_acceptance import (  # noqa: E402
    CORRECT_GOLD_INCORRECT,
    CORRECT_NO_GOLD,
    abstain_signal_names,
)
from experiments._trap_input_domain import SIGNAL_MIN_POINTS  # noqa: E402
from experiments.analysis_parts.check_leg_analysis import (  # noqa: E402
    CHECK_LEG_CHANNELS,
    CHECK_LEG_LABELS,
    _check_leg_measurability,
)
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
    _fl_at_k_metrics,
    _m1_metrics_aggregate,
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
from experiments.statistical_analysis import (  # noqa: E402
    detector_silence_stats as _detector_silence,
)
from experiments.statistical_analysis import (  # noqa: E402
    oracle_provenance_stats as _oracle_provenance,
)
from experiments.statistical_analysis import (  # noqa: E402
    patch_acceptance_stats as _patch_acceptance,
)
from experiments.statistical_analysis import (  # noqa: E402
    residual_keys_stats as _residual_keys,
)
from experiments.statistical_analysis import (  # noqa: E402
    self_repair_trap_domain_stats as _trap_domain,
)
from src.budget.token_usage import token_metric_reading  # noqa: E402


def load_latest_benchmark(results_dir: str = "experiments/results") -> str:
    """找到结果目录下最新的 benchmark JSON 文件（文件名倒序）。

    与 visualize_results.load_latest_result 同口径：仅识别 benchmark_* 前缀，
    无匹配时显式报错。

    AA-2（2026-10-19，承接第四轮审查 F06 同类残留）：旧实现只在 docstring 上声称
    同口径，实际在无 `benchmark_*` 文件时回退到目录内全部 JSON。结果目录混有
    `performance_benchmark.json`、`swebench_20_summary.json` 等汇总/性能产物，
    回退会把这些文件当成分析对象、静默读错分母，故改为 fail-closed。
    """
    all_json = sorted(f for f in os.listdir(results_dir) if f.endswith(".json"))
    benchmark_files = [f for f in all_json if f.startswith("benchmark_")]
    if not benchmark_files:
        raise FileNotFoundError(
            f"结果目录 {results_dir} 下没有 benchmark_*.json"
            f"（目录内共 {len(all_json)} 个 JSON，均非 benchmark 运行产物）；"
            "请用 --input 显式指定要分析的结果文件"
        )
    return os.path.join(results_dir, benchmark_files[-1])


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
            # BQ 轮（2026-10-22）：四个 status 通道的报告面读侧。BN/BL 把四键
            # 写进结果行两分支与 raw 白名单，但报告面零读者——归档与新批次里
            # "这条腿跑过且干净（ok）"与"崩了 / 按设计没跑 / 没记录"在所有
            # 报告面同形。本助手只加分档计数与恒等式，判定值与判定方向一处
            # 不动（四键不进入任何判定，既不被翻成通过也不被翻成拒绝）。
            "check_leg_measurability": _check_leg_measurability(details),
            # BT 轮（2026-10-22）：验收 oracle 来源与可见性的读侧对账。
            # 两键自 R52 起只写不读，且仓库级验收被标成 generated_test + 可见；
            # 本键只统计，不进入任何判定。
            "oracle_provenance": _oracle_provenance(details),
            # BU 轮（2026-10-22）：Self-Repair Trap 判定核输入可达域的读侧。
            # 两键自批次 XIV（ADR-0028）起只写不读，归档 5935 行恒判"不怀疑"；
            # 本键只分档与对账，判定值与判定方向一处不动。
            "self_repair_trap_domain": _trap_domain(details),
            # BV 轮（2026-10-23）：批次 VIII / XIV 两份判定核的沉默分档读侧。
            # 两组键（test_hacking_* / fl_constraint_*）自写入起报告面零读者，
            # 且「没看」与「看过且干净」在结果行里同形；本键只分档与对账，
            # 判定值与判定方向一处不动。
            "detector_silence": _detector_silence(details),
            # BW 轮（2026-10-23）：补丁接收链的覆盖率/分母读侧。
            # `patch_precision`（预注册 E3 指标）、`patch_plausible_evidence`、
            # `patch_plausible_invariant_violation`、`patch_abstain_signals` 自写入起
            # 报告面零读者；`patch_validated` 只有测试读者。本键只分档与对账，
            # 判定值与判定方向一处不动。
            "patch_acceptance": _patch_acceptance(details),
            # BX 轮（2026-10-23）：写而不读键池最后两键的读侧。
            # `risk_summary`（8,864 行全 `enabled=False` 占位）与 `mdo_crash_rate`
            # （五层输入域、分母=全池 n）自写入起报告面零读者；本键只分档与对账，
            # 判定值与判定方向一处不动。
            "residual_keys": _residual_keys(details),
            # 2.1 数据污染检测（details 携带 patch + task_metadata.golden_patch 时计算重叠度）
            "contamination_report": detect_contamination(details, golden_patches),
            # 1.3 边界用例覆盖（generated_test 含边界值时统计，旧 JSON 无该字段时全 0）
            "boundary_coverage_metrics": _boundary_case_coverage(details),
            # 1.3 变异得分（保守代理：从 details[].mutation_score 字段收集；
            # 无该字段时 available=False，渲染时跳过章节）
            "mutation_score_metrics": _mutation_score_metrics(details),
            # B-02（2026-10-04 系统审查 P1）：故障定位质量 FL@1/3/5 汇总
            # （从 details[].fl_at_k 收集，run_benchmark._fl_at_k 的产物；
            # 旧 JSON 无该字段时 available=False，渲染时跳过章节）
            "fl_at_k_metrics": _fl_at_k_metrics(details),
            # R2（2026-10-05 审查）：M1 指标汇总（detection/repair/false_fix/
            # test_error_rate，None 不计入分母；旧 JSON 无该字段时
            # available=False，渲染时跳过章节）
            "m1_metrics": _m1_metrics_aggregate(details),
            # 1.2 收敛失败模式归因（达到 MAX_ITERATIONS 仍未修复的任务，
            # 区分"无法定位根因" vs "无法生成有效补丁"）
            "convergence_failure_modes": _convergence_failure_modes(details),
            # 3.2 执行轨迹汇总（details[].execution_trace 收集，旧 JSON 无该字段时跳过）
            "execution_trace_metrics": _execution_trace_summary(details),
            # 2.2 难度分层渲染所需的原始 details（render 消费，不参与 JSON 序列化输出）
            "_details": details,
        }
        # 迭代次数分布（0 = 一次通过，1/2/3 = 调试轮数，>=3 归入 3+）
        # 2026-09-26 round9（P2 健壮性）：旧 JSON / 失败行 iterations 可能为
        # null（JSON None），min(None, 3) 抛 TypeError 使整份 build_analysis
        # 崩溃。归一为 int or 0，与 convergence_analysis L359 的
        # int(r.get("iterations", 0) or 0) 同口径。
        for r in details:
            iteration_counter[min(int(r.get("iterations") or 0), 3)] += 1

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


def _ratio_text(numerator: int, denominator: int) -> str:
    """比例文本；分母为 0 时 `—`（不是 0%，也不是 100%）。"""
    return f"{numerator / denominator:.1%}" if denominator else "—"


def _ratio_text2(numerator: int, denominator: int) -> str:
    """两位小数比例文本（BX：crash 率在千分之几量级，一位小数会失真）。"""
    return f"{numerator / denominator:.2%}" if denominator else "—"


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
    # AP（2026-10-21）：聚合 token_metrics 的字段走共享读数——此前
    # `t.get(..., 0)` 把在场 None 印成字面量 `None`（与缺席 0 同形），
    # 非对象 / 坏值要么崩要么冒充数字。不可读落"不可读"，干净读数逐字不变。
    token_notes: list[str] = []
    for baseline, m in per.items():
        t = m["token_metrics"]
        readings = {
            "total_tokens": token_metric_reading(t, "total_tokens"),
            "total_input_tokens": token_metric_reading(t, "total_input_tokens"),
            "total_output_tokens": token_metric_reading(t, "total_output_tokens"),
            "total_llm_calls": token_metric_reading(t, "total_llm_calls"),
            "avg_tokens_per_task": token_metric_reading(t, "avg_tokens_per_task", allow_float=True),
        }
        unreadable_fields = [key for key, reading in readings.items() if reading["value"] is None]
        if unreadable_fields:
            codes = sorted(
                {code for reading in readings.values() if reading["value"] is None for code in reading["reasons"]}
            )
            token_notes.append(
                f"{baseline} 的 {'、'.join(f'`{key}`' for key in unreadable_fields)} 不可读（{'；'.join(codes)}）"
            )
        cells = ["不可读" if reading["value"] is None else reading["value"] for reading in readings.values()]
        lines.append(f"| {baseline} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} |")
    lines.append("")
    lines.extend(f"> Token 读数不可判定：{note}" for note in token_notes)
    if token_notes:
        lines.append(">")
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
    # AO（2026-10-21）：行读数不可用导致整条曲线不可读时点名披露
    # （读不动不是 0；不能让该基线的曲线静默消失）。
    conv_token_blocked = [
        (b, m["convergence_token_efficiency"])
        for b, m in per.items()
        if not m.get("convergence_token_efficiency", {}).get("available")
        and m.get("convergence_token_efficiency", {}).get("n_token_unreadable_rows", 0) > 0
    ]
    if conv_token_rows or conv_token_blocked:
        lines.append("## 修复收敛 Token 效率曲线（1.3）")
        lines.append("")
        if conv_token_rows:
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
        for baseline, ct in conv_token_blocked:
            reasons = "、".join(f"{code}×{count}" for code, count in ct.get("token_reading_reasons", {}).items())
            lines.append(
                f"> - `{baseline}` Token 曲线不可读：{ct.get('n_token_unreadable_rows')} 行读数不可用（{reasons}）。"
            )
        if conv_token_blocked:
            lines.append("")
        if conv_token_rows:
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
        rag_token_notes: list[str] = []
        for baseline, rt in rag_token_rows:
            g = rt.get("rag_group", {})
            ng = rt.get("no_rag_group", {})
            ratio = rt.get("token_delta_ratio")
            ratio_text = f"{ratio:.2f}" if ratio is not None else "N/A"
            # AP：组均值不可读时不得借用 `.get(..., 0)` 印 0（"没有 token"与
            # "读不出 token"必须分形）。
            rag_avg = "不可读" if g.get("avg_tokens") is None else g.get("avg_tokens", 0)
            no_rag_avg = "不可读" if ng.get("avg_tokens") is None else ng.get("avg_tokens", 0)
            for side_key, group in (("RAG组", g), ("无RAG组", ng)):
                if group.get("avg_tokens") is None:
                    reasons = "；".join(group.get("token_reading_reasons", {}))
                    rag_token_notes.append(
                        f"{baseline} {side_key} 的 `avg_tokens` 不可读"
                        f"（{group.get('n_token_unreadable_rows', 0)} 行不可读：{reasons or '机制未记录'}）"
                    )
            lines.append(
                f"| {baseline} | {g.get('tasks', 0)} | {rag_avg} "
                f"| {g.get('success_rate', 0.0)} | {ng.get('tasks', 0)} | {no_rag_avg} "
                f"| {ng.get('success_rate', 0.0)} | {ratio_text} | {rt.get('iteration_delta', 0.0)} |"
            )
        lines.append("")
        lines.extend(f"> Token 读数不可判定：{note}" for note in rag_token_notes)
        if rag_token_notes:
            lines.append(">")
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
            # 2026-09-26 round9（P2 口径修复）：details 行不再携带 instance_code
            # （run_benchmark L359 只写 generated_test，无 instance_code 字段），
            # 旧调用仅传 details → code_size 全部落 "small"、dependency_count
            # 全部落 "low"（退化单档，分层失去区分度）。现从 details 自带字段
            # 构造 instance_codes/test_codes 映射：
            #   - instance_codes: 用 task_metadata.instance_code（若有）兜底，
            #     否则该行 code_size 退化 small（与旧行为一致，不引入新崩溃）；
            #   - test_codes: 直接读 details[].generated_test（code_size 的兜底源）。
            # 两个映射均为 task_id → 源码字符串，供 stratify_by_dimension 消费。
            instance_codes_map: dict[str, str] = {}
            test_codes_map: dict[str, str] = {}
            for r in details:
                tid = str(r.get("task_id", ""))
                task_meta = r.get("task_metadata") or {}
                ic = task_meta.get("instance_code")
                if isinstance(ic, str) and ic:
                    instance_codes_map[tid] = ic
                gt = r.get("generated_test")
                if isinstance(gt, str) and gt:
                    test_codes_map[tid] = gt
            lines.extend(
                render_stratification_section(
                    details,
                    baseline,
                    instance_codes=instance_codes_map or None,
                    test_codes=test_codes_map or None,
                )
            )

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

    # B-02（2026-10-04 系统审查 P1）：故障定位质量 FL@1/3/5（details[].fl_at_k
    # 携带时输出；旧 JSON 无该字段时章节自动跳过，历史口径零变化）
    fl_rows = [
        (b, m.get("fl_at_k_metrics")) for b, m in per.items() if (m.get("fl_at_k_metrics") or {}).get("available")
    ]
    if fl_rows:
        lines.append("## 故障定位质量（B-02，Ochiai FL@1/3/5）")
        lines.append("")
        lines.append("| 基线 | 观测任务/总数 | FL@1 命中率 | FL@3 命中率 | FL@5 命中率 |")
        lines.append("|------|--------------|-----------|-----------|-----------|")
        for baseline, fl in fl_rows:
            lines.append(
                f"| {baseline} | {fl.get('observed_tasks', 0)}/{fl.get('total_tasks', 0)} "
                f"| {fl.get('fl_at_1_rate')} | {fl.get('fl_at_3_rate')} | {fl.get('fl_at_5_rate')} |"
            )
        lines.append(
            "> 注：FL@k = Ochiai 谱系 Top-k 可疑行覆盖真实缺陷行（gold diff）的比例；"
            "仅当 details[].fl_at_k 字段存在（FL_SPECTRAL_ENABLE 且 gold 材料可解）时输出本章节。"
        )
        lines.append("")

    # R2（2026-10-05 审查：统计协议完整性）：M1 指标汇总（None 剔除口径，
    # 任一基线有可测任务时输出；旧 JSON 无该字段时章节自动跳过，历史输出零变化）
    m1_rows = [(b, m.get("m1_metrics")) for b, m in per.items() if (m.get("m1_metrics") or {}).get("available")]
    if m1_rows:
        lines.append("## M1 指标汇总（R2，None 不计入分母）")
        lines.append("")
        lines.append(
            "| 基线 | 可测任务/总数 | detection_rate 均值 | repair_rate 均值 | false_fix_rate 均值 | test_error_rate 均值 |"
        )
        lines.append(
            "|------|--------------|--------------------|----------------|-------------------|-------------------|"
        )

        def _m1_cell(m1: dict[str, Any], name: str) -> str:
            # 单指标单元格："mean（n=observed）"；无可测任务时输出 "—"
            stat = (m1.get("metrics") or {}).get(name) or {}
            if not stat.get("observed"):
                return "—"
            return f"{stat.get('mean')}（n={stat.get('observed')}）"

        for baseline, m1 in m1_rows:
            total = m1.get("total_tasks", 0)
            # 可测任务数四指标可能不同（逐字段各自剔除 None），取 detection_rate
            # 的可测数作主列口径，其余指标均值旁以 n= 标注
            det = (m1.get("metrics") or {}).get("detection_rate", {})
            observed_disp = f"{det.get('observed', 0)}/{total}"
            lines.append(
                f"| {baseline} | {observed_disp} "
                f"| {_m1_cell(m1, 'detection_rate')} | {_m1_cell(m1, 'repair_rate')} "
                f"| {_m1_cell(m1, 'false_fix_rate')} | {_m1_cell(m1, 'test_error_rate')} |"
            )
        lines.append("")
        lines.append(
            "> 注：M1 指标（detection/repair/false_fix/test_error_rate）为 oracle 材料"
            "可测任务的逐任务 0/1 值均值；None（不可测：oracle 缺失 / 坏测试剔除等）"
            "不计入分母，各列 n 为该指标的可测任务数——与 run_main_batch 的 R4 批次"
            "摘要同口径。旧结果 JSON 无这些字段时本章节自动跳过。"
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
    contam_cross = {b: m.get("contamination_cross_analysis", {}) for b, m in per.items()}
    contam_cross_rows = [(b, cc) for b, cc in contam_cross.items() if cc.get("available")]
    # BP 轮：改前 available=False 的臂被 filter 直接丢掉 ⇒ 整节从报告里消失，
    # 「这批 30 行全都没记录级别」与「这一节没跑」同形。现在按名留下。
    silent_cross_arms = [
        (b, cc) for b, cc in contam_cross.items() if cc and not cc.get("available") and cc.get("n_details")
    ]
    if contam_cross_rows or silent_cross_arms:
        lines.append("## 失败分析 × 污染检测交叉（5.3）")
        lines.append("")
    if contam_cross_rows:
        lines.append(
            "| 基线 | 高污染任务 | 高污染成功率 | 低污染任务 | 低污染成功率 | 成功率差（高-低） | 未入对照任务 |"
        )
        lines.append("|------|----------|------------|----------|------------|----------------|------------|")
        delta_computable = False
        for baseline, cc in contam_cross_rows:
            by_level = cc.get("by_risk_level", {})
            high = by_level.get("high", {})
            low = by_level.get("low", {})
            delta = cc.get("high_vs_low_success_delta")
            if delta is not None:
                delta_computable = True
                delta_text = f"{delta:.4f}"
            else:
                # BP 轮：改前两档不齐时返回的是「键不存在」，渲染出的 N/A 与「检测整腿没跑」
                # 同形，读者无从知道缺的是哪一档。判定不变（仍不是数值），只点名缺失档。
                missing_buckets = "、".join(cc.get("delta_missing_buckets") or [])
                delta_text = f"N/A（{missing_buckets} 档无行）" if missing_buckets else "N/A"
            excluded = sum(int(s.get("tasks", 0)) for lv, s in by_level.items() if lv not in ("high", "low"))
            # BP 轮：改前 `if not level: continue` 丢掉的未记录行既不在桶里也不在本列，
            # 表内合计小于行数却无人点名；它们同样"未入对照"，现在计入本列。
            excluded += int(cc.get("unobserved_total", 0))
            lines.append(
                f"| {baseline} | {high.get('tasks', 0)} | {high.get('success_rate', 0.0)} "
                f"| {low.get('tasks', 0)} | {low.get('success_rate', 0.0)} | {delta_text} | {excluded} |"
            )
        lines.append("")
        lines.append(
            '> 解读：若"成功率差（高-低）"为显著正值（≥0.2），提示高污染风险任务'
            '成功率异常偏高——系统可能在"背出"黄金补丁而非真正修复，论文中应'
            "单独标注含污染样本并补充 SWE-rebench 交叉验证；若差异 ≤0.2，"
            "说明污染效应不显著，结果可信度较高。"
        )
        lines.append("")
        if not delta_computable:
            # ≥0.2 / ≤0.2 判据需要一个算得出的差；全表 N/A 时它既不被满足也不被否证，
            # 不能顺着上面那句读成「差异 ≤0.2 ⇒ 结果可信度较高」。
            lines.append(
                "> 本表全部臂的「成功率差（高-低）」都是 N/A：没有一个臂同时具备 high 档与 low"
                " 档的行。上面那句 ≥0.2 / ≤0.2 判据在这批数据上无从应用——读不出「污染效应显著」，"
                "也读不出「污染效应不显著、结果可信度较高」。（BP 轮）"
            )
            lines.append("")
        lines.append(
            "> 「未入对照任务」= medium/unknown/not_applicable 三档合计，再加行内未记录该字段的行数"
            "（BM 轮，2026-10-22 起显式列示，此前这些行在本表里完全不可见；BP 轮把改前被 "
            "`if not level: continue` 静默丢弃的未记录行也计入本列）。unknown 表示这条检测腿没测成"
            "（补丁非文本、依赖导入失败等），not_applicable 表示无黄金补丁材料，未记录表示这一行根本没有"
            "该字段——改前脚注把「未记录」也写成 unknown，本表实际并不这样计。批次 IX 的按臂聚合表仍按历史"
            "口径把未记录行并计进 unknown，两表 unknown 之差即未记录行数；三者都不进入高/低污染对照，"
            "既不算污染证据也不算干净证据。"
        )
        lines.append("")
    if silent_cross_arms:
        detail = "；".join(
            f"`{b}`（{int(cc.get('n_details', 0))} 行全部未记录，原因 {cc.get('reason') or '未记录'}）"
            for b, cc in silent_cross_arms
        )
        lines.append(f"> 本节未列出 {len(silent_cross_arms)} 个基线：{detail}。")
        lines.append(
            "> 「未列出」= 这些臂的 details 里没有任何一行记录过 contamination_risk_level，"
            "**不是「检测干净」，也不是「没有任务」**——上表只对有记录的臂给出对照。（BP 轮）"
        )
        lines.append("")

    # BQ 轮（2026-10-22）：四个 status 通道的报告面读侧披露。改前报告面对这
    # 四个键零读者——BN/BL 落盘的字节没有任何消费面看，"这条腿跑过且干净
    # （ok）"与"崩了（error）/ 按设计没跑（disabled）/ 没记录（null/absent）"
    # 在所有报告面同形。本节只让分档可见：四键不进入任何判定，既不被翻成
    # 通过也不被翻成拒绝。
    leg_map = {b: m.get("check_leg_measurability", {}) for b, m in per.items()}
    leg_rows = [(b, lg) for b, lg in leg_map.items() if lg.get("available")]
    # 全行四键缺席的臂（BN 之前的历史批次）按名留下：改前的对应形态是整节
    # 不渲染（读者无从知道"没读过"与"没有数据"的差别）；全零表更坏——会被
    # 读成"四腿都干净"（BP 轮同款判据）。
    silent_leg_arms = [(b, lg) for b, lg in leg_map.items() if lg and not lg.get("available") and lg.get("n_rows")]
    if leg_rows or silent_leg_arms:
        lines.append("## 检查腿可测量性（BQ：结果行四通道的读侧）")
        lines.append("")
    if leg_rows:
        lines.append(
            "| 基线 | 通道 | ok | 没测成(error/unavailable) | 按设计没跑(disabled) | 未记录(值为 null) | 未记录(键缺席) | 行数 |"
        )
        lines.append(
            "|------|------|----|--------------------------|---------------------|------------------|----------------|------|"
        )
        for baseline, lg in leg_rows:
            for channel in CHECK_LEG_CHANNELS:
                ch = lg["channels"].get(channel, {})
                lines.append(
                    f"| {baseline} | {CHECK_LEG_LABELS[channel]} | {ch.get('ok', 0)} "
                    f"| {ch.get('error', 0) + ch.get('unavailable', 0)} | {ch.get('disabled', 0)} "
                    f"| {ch.get('null', 0)} | {ch.get('absent', 0)} | {lg.get('n_rows', 0)} |"
                )
        lines.append("")
        unm_total = sum(int(lg.get("rows_any_unmeasurable", 0)) for _, lg in leg_rows)
        lines.append(f"> 上表各臂至少一条检查腿没测成的行合计 **{unm_total}**（error/unavailable 两档）。")
        # 词表外取值单列点名：防 "OK"/1 这类值被静默算进 ok（BP 轮词表外判据的同族）
        other_notes = [
            f"`{b}` 臂 `{channel}` 出现词表外取值 {ch['other_values']} ×{ch['other']}"
            for b, lg in leg_rows
            for channel in CHECK_LEG_CHANNELS
            for ch in [lg["channels"].get(channel, {})]
            if ch.get("other")
        ]
        if other_notes:
            lines.append("")
            lines.append(f"> 词表外取值（不进 ok 也不进任何否定档）：{'；'.join(other_notes)}。")
        lines.append("")
        lines.append(
            "> 口径：四值词汇（ok / disabled / unavailable / error）来自 `src/utils/check_status.py`"
            " 单一事实源；`ok` 才是「检查完成且零疑点」；`没测成` = error/unavailable；"
            "`按设计没跑` = disabled；`未记录(值为 null)` = 该任务该腿没记录（失败分支占位或腿未跑）；"
            "`未记录(键缺席)` = 批次早于 BN 轮（2026-10-22）落盘。**四个键不进入任何判定**——"
            "本节只让「没测 / 没记录」在报告面可见，不把没测翻成通过，也不翻成拒绝；"
            "行级读数以原始工件（raw/ 白名单）为准。"
        )
        lines.append("")
    if silent_leg_arms:
        detail = "；".join(
            f"`{b}`（{int(lg.get('n_rows', 0))} 行四通道全部未记录，原因 {lg.get('reason') or '未记录'}）"
            for b, lg in silent_leg_arms
        )
        lines.append(f"> 本节未列出 {len(silent_leg_arms)} 个基线：{detail}。")
        lines.append(
            "> 「未列出」= 这些臂的结果行里四个键一个都没落盘（批次早于 BN 轮 2026-10-22），"
            "**不是「四腿都干净」，也不是「没有任务」**——上表只对有记录的臂给分档。（BQ 轮）"
        )
        lines.append("")

    # BT 轮（2026-10-22）：验收 oracle 来源与可见性的报告面读侧。改前两键
    # 自 R52 起只写不读，仓库级验收还被标成 generated_test + 可见；本节只统计
    # 与对账，不进入任何判定（不改 passed / repair / 分母）。
    prov = {b: m.get("oracle_provenance", {}) for b, m in per.items()}
    prov_rows = [(b, pv) for b, pv in prov.items() if pv.get("n_rows")]
    if prov_rows:
        lines.append("## 验收 oracle 来源与可见性（BT：`oracle_type` / `test_visible_to_system` 的读侧）")
        lines.append("")
        lines.append(
            "| 基线 | 生成测试（可见） | 增强测试（可见） | gold F2P（不可见） | 未记录 | 词表外 | 行数 | repo 行 | repo 缺声明 | repo 声明一致 | repo 不一致 |"
        )
        lines.append(
            "|------|------------------|------------------|--------------------|--------|--------|------|---------|-------------|----------------|-------------|"
        )
        for baseline, pv in prov_rows:
            by = pv.get("by_type", {})
            lines.append(
                f"| {baseline} | {by.get('generated_test', 0)} | {by.get('enhanced_generated_test', 0)} "
                f"| {by.get('gold_fail_to_pass', 0)} | {by.get('not_recorded', 0)} | {by.get('other', 0)} "
                f"| {pv.get('n_rows', 0)} | {pv.get('repo_rows', 0)} | {pv.get('repo_rows_unrecorded', 0)} "
                f"| {pv.get('repo_rows_consistent', 0)} | {pv.get('n_violations', 0)} |"
            )
        lines.append("")
        bad = [(b, pv) for b, pv in prov_rows if pv.get("n_violations")]
        if bad:
            detail = "；".join(
                f"`{b}` {pv['n_violations']} 行（样例 task_id: {', '.join(pv.get('violations', [])[:5]) or '—'}）"
                for b, pv in bad
            )
            lines.append(f"> **不一致（repo 行必须 gold + 不可见）**：{detail}。")
            lines.append("")
        other_notes = [f"`{b}` 出现词表外取值 {pv['other_values']}" for b, pv in prov_rows if pv.get("other_values")]
        if other_notes:
            lines.append(f"> 词表外取值（单列，不并入任何档）：{'；'.join(other_notes)}。")
            lines.append("")
        lines.append(
            "> 口径：`generated_test` / `enhanced_generated_test` 为本地生成测试验收（测试对系统可见）；"
            "`gold_fail_to_pass` 为仓库级验收（gold FAIL_TO_PASS/PASS_TO_PASS，测试**对系统不可见**）；"
            "`未记录` = 该行没有这两个键（批次早于 R52，**不等于**「生成测试验收」）。"
            "repo 行（有 `repo_verification`）必须同时满足 `gold_fail_to_pass` 与 `False`，否则计入「不一致」。"
        )
        lines.append(
            "> `repo 缺声明` = 有仓库级验收但**两个键都未记录**（早于 R52 的历史批次）——"
            "缺键读作未记录，**不计入不一致**；只记录了一个键属不完整声明，仍计入不一致。"
        )
        lines.append("")

    # BU 轮（2026-10-22）：Self-Repair Trap 判定核输入可达域的报告面读侧。改前
    # `self_repair_trap_suspected` / `_signals` 自批次 XIV（ADR-0028）起只写不读，
    # 归档 5935 行恒判"不怀疑"——输入不足、形状不符与"判干净"三种事实在报告面
    # 同形，且三个信号各自的最少点数门槛从不披露。本节只分档与对账，
    # 不改判定核、不改任何行的值与方向。
    trap = {b: m.get("self_repair_trap_domain", {}) for b, m in per.items()}
    trap_rows = [(b, t) for b, t in trap.items() if t.get("n_rows")]
    if trap_rows:
        lines.append("## Self-Repair Trap 判定核的输入可达域（BU：`self_repair_trap_*` 的读侧）")
        lines.append("")
        lines.append(
            "| 基线 | 行数 | 有判定 | 未记录 | 历史 null | <2 点 | ≥2 点 | declining 可达 | collapse 可达 | score 可达 | 域外下降 | 开火 | 不一致（判定/信号） |"
        )
        lines.append(
            "|------|------|--------|--------|-----------|-------|-------|----------------|-------------|------------|----------|------|--------------------|"
        )
        totals = Counter()
        for baseline, t in trap_rows:
            dom = t.get("signal_domain", {})
            totals.update(
                {
                    "n_rows": t.get("n_rows", 0),
                    "n_with_verdict": t.get("n_with_verdict", 0),
                    "not_recorded": t.get("not_recorded", 0),
                    "history_malformed": t.get("history_malformed", 0),
                    "below_min_floor": t.get("below_min_floor", 0),
                    "min_floor_reached": t.get("min_floor_reached", 0),
                    "assert_count_declining": dom.get("assert_count_declining", 0),
                    "assertion_collapse": dom.get("assertion_collapse", 0),
                    "mutation_score_declining": dom.get("mutation_score_declining", 0),
                    "n_decline2_outside_domain": t.get("n_decline2_outside_domain", 0),
                    "n_verdict_true": t.get("n_verdict_true", 0),
                    "n_suspected_mismatch": t.get("n_suspected_mismatch", 0),
                    "n_signals_mismatch": t.get("n_signals_mismatch", 0),
                    "n_rerun_error": t.get("n_rerun_error", 0),
                }
            )
            lines.append(
                f"| {baseline} | {t.get('n_rows', 0)} | {t.get('n_with_verdict', 0)} "
                f"| {t.get('not_recorded', 0)} | {t.get('history_malformed', 0)} "
                f"| {t.get('below_min_floor', 0)} | {t.get('min_floor_reached', 0)} "
                f"| {dom.get('assert_count_declining', 0)} | {dom.get('assertion_collapse', 0)} "
                f"| {dom.get('mutation_score_declining', 0)} | {t.get('n_decline2_outside_domain', 0)} "
                f"| {t.get('n_verdict_true', 0)} "
                f"| {t.get('n_suspected_mismatch', 0)}/{t.get('n_signals_mismatch', 0)} |"
            )
        lines.append(
            f"| **合计** | {totals['n_rows']} | {totals['n_with_verdict']} | {totals['not_recorded']} "
            f"| {totals['history_malformed']} | {totals['below_min_floor']} | {totals['min_floor_reached']} "
            f"| {totals['assert_count_declining']} | {totals['assertion_collapse']} "
            f"| {totals['mutation_score_declining']} | {totals['n_decline2_outside_domain']} "
            f"| {totals['n_verdict_true']} | {totals['n_suspected_mismatch']}/{totals['n_signals_mismatch']} |"
        )
        lines.append("")
        silent_arms = [b for b, t in trap_rows if not t.get("n_with_verdict")]
        if silent_arms:
            lines.append(
                f"> 本节 {len(silent_arms)} 个臂的结果行两个键都没落盘："
                f"{'、'.join(f'`{b}`' for b in silent_arms)}——**不是「都判过且不怀疑」**，"
                "是批次早于 ADR-0028 观测层（`未记录` 一档）。"
            )
            lines.append("")
        if not totals["assert_count_declining"]:
            lines.append(
                f"> **`assert_count_declining` 的输入域在本语料是空集**：{totals['n_with_verdict']} 行里"
                f"没有任何一行给出 ≥{SIGNAL_MIN_POINTS['assert_count_declining']} 个可解析断言计数"
                "（归档历史最长 2 点）——该信号「从未开火」与「从未被给过判定机会」在判定值上同形。"
            )
            lines.append("")
        if totals["n_rerun_error"]:
            lines.append(f"> 对账异常（同进程重跑判定核抛错）= {totals['n_rerun_error']} 行，单列不折成「一致」。")
            lines.append("")
        lines.append(
            "> 口径：`未记录` = 行内没有 `self_repair_trap_suspected` 键（批次早于 ADR-0028），"
            "**不等于**「这条腿干净」；`历史 null` = 键在但 `oracle_quality_history` 不是列表，"
            "判定核走「结构异常 ⇒ 不怀疑」分支；`<2 点` / `≥2 点` = 历史快照点数。"
        )
        lines.append(
            "> 三个「可达」列回答的是**输入够不够**，不是判没判出来："
            f"`declining 可达` 需 ≥{SIGNAL_MIN_POINTS['assert_count_declining']} 个可解析点、"
            f"`collapse 可达` 需 ≥{SIGNAL_MIN_POINTS['assertion_collapse']} 个可解析点、"
            f"`score 可达` 需 ≥{SIGNAL_MIN_POINTS['mutation_score_declining']} 个非 `None` 变异分数。"
            "`域外下降` = 历史确有连续下降但点数低于 declining 门槛（证据存在、判据看不见）。"
            "`不一致` = 同进程把判定核重跑在归档历史上与行内已写值按值对照的差异行数（不改写任何值）。"
        )
        lines.append("")

    # BV 轮（2026-10-23）：批次 VIII / XIV 两份判定核的沉默分档报告面读侧。改前
    # `test_hacking_*`（批次 VIII，ADR-0022）与 `fl_constraint_*`（批次 XIV，
    # ADR-0028）只写不读，而两者的「没看」与「看过且干净」在结果行里同形：
    # 判定核在无原码 / 无补丁 / 解析失败时返回 suspected=False + signals=[]，
    # 约束门的六种早退共用一个 not_evaluable。本节只分档与对账，判定值与
    # 判定方向一处不动（两组键不进入任何判定）。
    silence = {b: m.get("detector_silence", {}) for b, m in per.items()}
    silence_rows = [(b, s) for b, s in silence.items() if s.get("n_rows")]
    if silence_rows:
        lines.append("## 批次 VIII/XIV 判定核的沉默分档（BV：`test_hacking_*` / `fl_constraint_*` 的读侧）")
        lines.append("")
        lines.append(
            "| 基线 | 行数 | hack 有判定 | 状态已记录 | 已求值（ok） | 没看 | 状态未记录 | 判 True | 信号非空 |"
        )
        lines.append(
            "|------|------|-------------|-------------|---------------|------|-------------|---------|----------|"
        )
        hack_totals = Counter()
        for baseline, s in silence_rows:
            h = s.get("hack", {})
            hack_totals.update(
                {
                    "n_rows": s.get("n_rows", 0),
                    "n_verdict_recorded": h.get("n_verdict_recorded", 0),
                    "n_status_recorded": h.get("n_status_recorded", 0),
                    "n_evaluated": h.get("n_evaluated", 0),
                    "n_silent": h.get("n_silent", 0),
                    "n_status_unrecorded": h.get("n_status_unrecorded", 0),
                    "n_suspected": h.get("n_suspected", 0),
                    "n_signal_nonempty": h.get("n_signal_nonempty", 0),
                }
            )
            lines.append(
                f"| {baseline} | {s.get('n_rows', 0)} | {h.get('n_verdict_recorded', 0)} "
                f"| {h.get('n_status_recorded', 0)} | {h.get('n_evaluated', 0)} | {h.get('n_silent', 0)} "
                f"| {h.get('n_status_unrecorded', 0)} | {h.get('n_suspected', 0)} | {h.get('n_signal_nonempty', 0)} |"
            )
        lines.append(
            f"| **合计** | {hack_totals['n_rows']} | {hack_totals['n_verdict_recorded']} "
            f"| {hack_totals['n_status_recorded']} | {hack_totals['n_evaluated']} | {hack_totals['n_silent']} "
            f"| {hack_totals['n_status_unrecorded']} | {hack_totals['n_suspected']} "
            f"| {hack_totals['n_signal_nonempty']} |"
        )
        lines.append("")
        lines.append(
            "| 基线 | FL 有判定 | hit | miss | not_evaluable | 已求值 | hit 比 | 成因已记录 | 成因推断（下界） | 成因不一致 | 变更函数 0/1/2/3+ |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        fl_totals = Counter()
        for baseline, s in silence_rows:
            f = s.get("fl", {})
            changed = f.get("changed_len", {})
            fl_totals.update(
                {
                    "n_verdict_recorded": f.get("n_verdict_recorded", 0),
                    "n_hit": f.get("n_hit", 0),
                    "n_miss": f.get("n_miss", 0),
                    "n_not_evaluable": f.get("n_not_evaluable", 0),
                    "n_evaluated": f.get("n_evaluated", 0),
                    "n_recorded": sum(f.get("reason_recorded", {}).values()),
                    "n_inferred": sum(f.get("reason_inferred", {}).values()),
                    "n_reason_mismatch": f.get("n_reason_mismatch", 0),
                    "changed_0": changed.get("0", 0),
                    "changed_1": changed.get("1", 0),
                    "changed_2": changed.get("2", 0),
                    "changed_3": changed.get("3+", 0),
                }
            )
            ratio = f.get("hit_ratio")
            lines.append(
                f"| {baseline} | {f.get('n_verdict_recorded', 0)} | {f.get('n_hit', 0)} | {f.get('n_miss', 0)} "
                f"| {f.get('n_not_evaluable', 0)} | {f.get('n_evaluated', 0)} "
                f"| {f'{ratio:.1%}' if ratio is not None else '—'} "
                f"| {sum(f.get('reason_recorded', {}).values())} | {sum(f.get('reason_inferred', {}).values())} "
                f"| {f.get('n_reason_mismatch', 0)} "
                f"| {changed.get('0', 0)}/{changed.get('1', 0)}/{changed.get('2', 0)}/{changed.get('3+', 0)} |"
            )
        total_ratio = (fl_totals["n_hit"] / fl_totals["n_evaluated"]) if fl_totals["n_evaluated"] else None
        lines.append(
            f"| **合计** | {fl_totals['n_verdict_recorded']} | {fl_totals['n_hit']} | {fl_totals['n_miss']} "
            f"| {fl_totals['n_not_evaluable']} | {fl_totals['n_evaluated']} "
            f"| {f'{total_ratio:.1%}' if total_ratio is not None else '—'} "
            f"| {fl_totals['n_recorded']} | {fl_totals['n_inferred']} | {fl_totals['n_reason_mismatch']} "
            f"| {fl_totals['changed_0']}/{fl_totals['changed_1']}/{fl_totals['changed_2']}/{fl_totals['changed_3']} |"
        )
        lines.append("")
        silent_arms = [b for b, s in silence_rows if not s.get("hack", {}).get("n_verdict_recorded")]
        if silent_arms:
            lines.append(
                f"> {len(silent_arms)} 个臂的结果行没有 `test_hacking_*` 判定键："
                f"{'、'.join(f'`{b}`' for b in silent_arms)}——**不是「都判过且干净」**，"
                "是批次早于批次 VIII 观测层（`hack 有判定` = 0）。"
            )
            lines.append("")
        if hack_totals["n_suspected"]:
            samples = []
            for _, s in silence_rows:
                samples.extend(s.get("hack", {}).get("suspected_samples", []))
            lines.append(
                f"> **test-hacking 判定为 True 的行 = {hack_totals['n_suspected']}**"
                f"（样例 task_id: {', '.join(samples[:10]) or '—'}）——这批行此前在任何报告面都不出现。"
                "判定值为 True 只说明**补丁里出现了三类结构信号之一**（硬编码输入分支 / 断言弱化 / "
                "新增吞异常），它不进入 passed，也不是「作弊已被确认」。"
            )
            lines.append("")
        if hack_totals["n_silent"]:
            lines.append(
                f"> **`没看` = {hack_totals['n_silent']} 行**：判定核在这批行上根本没跑"
                "（无原码 / 无补丁 / 两侧之一解析失败）——它们的 `suspected=False` 与"
                "「三信号都跑过且零命中」在判定值上同形，`没看` 一列就是这两者的分界。"
            )
            lines.append("")
        if total_ratio is not None and fl_totals["n_evaluated"] and total_ratio >= 0.99:
            share3 = fl_totals["changed_3"] / fl_totals["n_evaluated"]
            if share3 > 0.5:
                reading = (
                    f"其中变更函数 3+ 档占 {share3:.1%}——与 ADR-0028 登记的「整文件重写 ⇒ 变更集合 ≈ 全文件函数 ⇒ "
                    "近乎恒 hit」一致，此时 hit 比几乎不含定位质量信息。"
                )
            else:
                reading = (
                    f"变更函数 3+ 档只占 {share3:.1%}，**ADR-0028 登记的整文件重写成因不足以解释这个比值**——"
                    f"高 hit 比的直接含义是「补丁改的函数几乎总落在 Top-k 候选里」，而 miss 仅 "
                    f"{fl_totals['n_miss']} 行 ⇒ 该门在本语料几乎不区分。"
                )
            lines.append(
                f"> **约束门的判别力读数**：已求值 {fl_totals['n_evaluated']} 行里 hit {fl_totals['n_hit']} / "
                f"miss {fl_totals['n_miss']}（hit 比 {total_ratio:.1%}）。{reading}"
                "hit 比不得读作「定位质量好」。"
            )
            lines.append("")
        if fl_totals["n_reason_mismatch"]:
            lines.append(
                f"> 成因键与判定值自相矛盾 = {fl_totals['n_reason_mismatch']} 行（写侧缺陷信号，单列不修正）。"
            )
            lines.append("")
        lines.append(
            "> 口径：`hack 有判定` = 行内有 `test_hacking_suspected` 键（批次早于 VIII 则缺席，**不等于**"
            "「判过且干净」）；`状态已记录` = 有 `test_hacking_status`（BV 起落盘）；`状态未记录` = "
            "有判定但状态键缺席（早于 BV）——**不得读作 ok**；`没看` = 状态词表里 `ok` 之外的任何一档"
            "（无原码 / 无补丁 / 原码解析失败 / 补丁解析失败 / 调用点异常）。"
        )
        lines.append(
            "> FL 侧：`not_evaluable` 的成因分两列——`成因已记录` 来自 `fl_constraint_reason`（BV 起落盘），"
            "`成因推断（下界）` 是按行内材料（`patch` / `llm_localization` / "
            "`fl_constraint_changed_functions`）反推的历史行，只能看到「无补丁 / 无定位 / 变更集合为空」"
            "三支，「无原码 / 无候选 / 异常」落 `inferred_unattributed`——**推断是下界，不等于全集**。"
            "`hit 比` 的分母是 `已求值`（hit + miss），`not_evaluable` 不进分母；"
            "判定值为 `null`（失败分支的显式占位）按 `not_evaluable` 读，成因取 `no_state`。"
        )
        lines.append("")

    # BW 轮（2026-10-23）：补丁接收链的覆盖率/分母报告面读侧。改前
    # `patch_precision`（预注册 E3）、`patch_plausible_evidence` /
    # `patch_plausible_invariant_violation`（P0-2）、`patch_abstain_signals`
    # 自写入起报告面零读者，`patch_validated` 只有测试读者。判定值本身忠实，
    # 没有读者的是它们的分母与输入可达域。本节只分档与对账，判定值与方向
    # 一处不动。
    acceptance = {b: m.get("patch_acceptance", {}) for b, m in per.items()}
    acceptance_rows = [(b, s) for b, s in acceptance.items() if s.get("n_rows")]
    if acceptance_rows:
        lines.append("## 补丁接收链的覆盖率与分母（BW：`patch_precision` / 证据 / 弃权 / 验证的读侧）")
        lines.append("")
        lines.append(
            "| 基线 | 行数 | 接收链已记录 | plausible | correct | 交 | 接受集判错 | 排除集判对 | 接受集无 gold | 精确率 | 并集精确率 | gold 精确率 | 覆盖率 | 选择性风险 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        acc_totals = Counter()
        for baseline, s in acceptance_rows:
            a = s.get("acceptance", {})
            n_rec = a.get("n_recorded", 0)
            n_p = a.get("n_plausible", 0)
            n_c = a.get("n_correct", 0)
            n_pc = a.get("n_plausible_correct", 0)
            n_ic = a.get("n_implausible_correct", 0)
            acc_totals.update(
                {
                    "n_rows": s.get("n_rows", 0),
                    "n_recorded": n_rec,
                    "n_plausible": n_p,
                    "n_correct": n_c,
                    "n_plausible_correct": n_pc,
                    "n_plausible_incorrect": a.get("n_plausible_incorrect", 0),
                    "n_implausible_correct": n_ic,
                    "n_implausible_incorrect": a.get("n_implausible_incorrect", 0),
                    "n_plausible_no_gold": a.get("n_plausible_no_gold", 0),
                    "n_plausible_gold": a.get("n_plausible_gold", 0),
                    "n_gold_correct": a.get("n_gold_correct", 0),
                    "n_gold_incorrect": a.get("n_gold_incorrect", 0),
                    "n_status_gold_incorrect": a.get("correct_status", {}).get(CORRECT_GOLD_INCORRECT, 0),
                    "n_status_no_gold": a.get("correct_status", {}).get(CORRECT_NO_GOLD, 0),
                }
            )
            lines.append(
                f"| {baseline} | {s.get('n_rows', 0)} | {n_rec} | {n_p} | {n_c} | {n_pc} "
                f"| {a.get('n_plausible_incorrect', 0)} | {n_ic} | {a.get('n_plausible_no_gold', 0)} "
                f"| {_ratio_text(n_pc, n_p)} | {_ratio_text(n_c, n_p + n_ic)} "
                f"| {_ratio_text(a.get('n_gold_correct', 0), a.get('n_plausible_gold', 0))} "
                f"| {_ratio_text(n_p, n_rec)} "
                f"| {_ratio_text(a.get('n_plausible_incorrect', 0), n_p)} |"
            )
        lines.append(
            f"| **合计** | {acc_totals['n_rows']} | {acc_totals['n_recorded']} | {acc_totals['n_plausible']} "
            f"| {acc_totals['n_correct']} | {acc_totals['n_plausible_correct']} "
            f"| {acc_totals['n_plausible_incorrect']} | {acc_totals['n_implausible_correct']} "
            f"| {acc_totals['n_plausible_no_gold']} "
            f"| {_ratio_text(acc_totals['n_plausible_correct'], acc_totals['n_plausible'])} "
            f"| {_ratio_text(acc_totals['n_correct'], acc_totals['n_plausible'] + acc_totals['n_implausible_correct'])} "
            f"| {_ratio_text(acc_totals['n_gold_correct'], acc_totals['n_plausible_gold'])} "
            f"| {_ratio_text(acc_totals['n_plausible'], acc_totals['n_recorded'])} "
            f"| {_ratio_text(acc_totals['n_plausible_incorrect'], acc_totals['n_plausible'])} |"
        )
        lines.append("")
        lines.append(
            "> 三个精确率是三个分母，不是三个估计：`精确率` = 交 / plausible（存储的 `patch_precision` 口径）；"
            "`并集精确率` = correct / (plausible ∪ correct)——"
            f"{acc_totals['n_implausible_correct']} 行 `correct=1 ∧ plausible=0` 让两集合不是包含关系；"
            "`gold 精确率` 在接收集里剔除 "
            f"{acc_totals['n_plausible_no_gold']} 行「无 gold 材料」（`repair_rate` 缺席或 `None`），"
            "是预注册 E3 的可比口径。`覆盖率` = plausible / 接收链已记录；"
            "`选择性风险` = 接受集判错 / plausible（同一分母，二者互补）。"
            "`patch_precision=None` 当且仅当 `plausible=0`（无分母），**不得读作 0，也不得读作「无 gold」**。"
        )
        lines.append(
            f"> `correct=0` 分两档：gold 判错 {acc_totals['n_status_gold_incorrect']} 行 / 无 gold 材料 "
            f"{acc_totals['n_status_no_gold']} 行——"
            "后者是写侧在无 gold 时的保守取值，**不是判错**。`correct=1 ∧ plausible=0` 的 "
            f"{acc_totals['n_implausible_correct']} 行是接收门与 gold 判定的方向分歧，单列不修正。"
        )
        inv = Counter()
        for _, s in acceptance_rows:
            inv.update(s.get("acceptance", {}).get("invariant", {}))
        lines.append(
            f"> `patch_plausible_invariant_violation` 的读侧：按行内材料复算违反不变量 "
            f"{inv['violation']} 行，其中布尔键为真 {inv['flag_true']} 行、**键缺席 "
            f"{inv['flag_missing']} 行**；键未落盘的历史行另有 {inv['flag_unrecorded']} 行。"
            "缺席不得读作「未违反」——该布尔键不能当完整性信号用。"
        )
        lines.append(
            f"> 键组早于落盘的臂：接收链未记录 {acc_totals['n_rows'] - acc_totals['n_recorded']} 行"
            "（早于 R53），**不等于**「plausible=0」；弃权/证据/验证三组各自的未记录数见下表。"
        )
        lines.append(
            "> 工件注记（ADR-0021）：早于 2026-10-07 的归档行里 `patch` 文本可能仍带 "
            "`python\\n`/围栏前缀，`patch_present` 与证据档在个别行上会低估；本表按归档原值读，"
            "修正口径以 `make repair-replay` 的回放为准（本轮**未重跑**回放，不改写任何行）。"
        )
        lines.append("")
        lines.append(
            "| 基线 | 证据已记录 | applied | applied_then_rejected | rejected | no_patch | no_state | 其它 | 未记录 | 隐含 plausible | plausible 无证据 | 不一致 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        ev_totals = Counter()
        for baseline, s in acceptance_rows:
            ev = s.get("evidence", {})
            basis = ev.get("basis", {})
            ev_totals.update(
                {
                    "n_recorded": ev.get("n_recorded", 0),
                    "applied": basis.get("applied", 0),
                    "applied_then_rejected": basis.get("applied_then_rejected", 0),
                    "rejected": basis.get("rejected", 0),
                    "no_patch": basis.get("no_patch", 0),
                    "no_state": basis.get("no_state", 0),
                    "n_other": ev.get("n_other", 0),
                    "n_unrecorded": ev.get("n_unrecorded", 0),
                    "n_implied_plausible": ev.get("n_implied_plausible", 0),
                    "n_plausible_without_evidence": ev.get("n_plausible_without_evidence", 0),
                    "n_mismatch": ev.get("n_mismatch", 0),
                }
            )
            lines.append(
                f"| {baseline} | {ev.get('n_recorded', 0)} | {basis.get('applied', 0)} "
                f"| {basis.get('applied_then_rejected', 0)} | {basis.get('rejected', 0)} "
                f"| {basis.get('no_patch', 0)} | {basis.get('no_state', 0)} | {ev.get('n_other', 0)} "
                f"| {ev.get('n_unrecorded', 0)} | {ev.get('n_implied_plausible', 0)} "
                f"| {ev.get('n_plausible_without_evidence', 0)} | {ev.get('n_mismatch', 0)} |"
            )
        lines.append(
            f"| **合计** | {ev_totals['n_recorded']} | {ev_totals['applied']} "
            f"| {ev_totals['applied_then_rejected']} | {ev_totals['rejected']} "
            f"| {ev_totals['no_patch']} | {ev_totals['no_state']} | {ev_totals['n_other']} "
            f"| {ev_totals['n_unrecorded']} | {ev_totals['n_implied_plausible']} "
            f"| {ev_totals['n_plausible_without_evidence']} | {ev_totals['n_mismatch']} |"
        )
        lines.append("")
        lines.append(
            f"> 证据档与 `plausible` 的恒等：`applied` / `applied_then_rejected` ⇔ `plausible=1`，"
            f"不一致 {ev_totals['n_mismatch']} 行。`未记录` = 键缺席（早于 P0-2），"
            "**不等于「没有证据」**；后者看 `no_patch` / `no_state` / `rejected`。"
            f"`plausible=1` 却缺席证据键的 {ev_totals['n_plausible_without_evidence']} 行是历史行，"
            "其接受资格没有可复核依据。"
        )
        lines.append("")
        lines.append(
            "| 基线 | 弃权已记录 | abstained | 可抑制 | 无可抑制对象 | 抑制 passed | 抑制 gold 判错 | 抑制精确率 | 信号非空 | ≥2 信号 | 无效信号 | 判定不一致 | 信号不一致 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        ab_totals = Counter()
        sig_counts = Counter()
        sig_domain = {name: Counter() for name in abstain_signal_names()}
        for baseline, s in acceptance_rows:
            ab = s.get("abstain", {})
            sp = ab.get("suppressed_precision", {})
            ab_totals.update(
                {
                    "n_recorded": ab.get("n_recorded", 0),
                    "n_abstained": ab.get("n_abstained", 0),
                    "n_actionable": ab.get("n_actionable", 0),
                    "n_no_effect": ab.get("n_no_effect", 0),
                    "n_suppressed": ab.get("n_suppressed", 0),
                    "suppressed_denominator": sp.get("denominator", 0),
                    "suppressed_numerator": sp.get("numerator", 0),
                    "n_signal_nonempty": ab.get("n_signal_nonempty", 0),
                    "n_multi_signal": ab.get("n_multi_signal", 0),
                    "n_unknown_signals": ab.get("n_unknown_signals", 0),
                    "n_abstain_mismatch": ab.get("n_abstain_mismatch", 0),
                    "n_signal_mismatch": ab.get("n_signal_mismatch", 0),
                }
            )
            sig_counts.update(ab.get("signals", {}))
            for name, counts in ab.get("signal_domain", {}).items():
                sig_domain.setdefault(name, Counter()).update(counts)
            lines.append(
                f"| {baseline} | {ab.get('n_recorded', 0)} | {ab.get('n_abstained', 0)} "
                f"| {ab.get('n_actionable', 0)} | {ab.get('n_no_effect', 0)} "
                f"| {ab.get('n_suppressed', 0)} | {sp.get('numerator', 0)} "
                f"| {_ratio_text(sp.get('numerator', 0), sp.get('denominator', 0))} "
                f"| {ab.get('n_signal_nonempty', 0)} | {ab.get('n_multi_signal', 0)} "
                f"| {ab.get('n_unknown_signals', 0)} | {ab.get('n_abstain_mismatch', 0)} "
                f"| {ab.get('n_signal_mismatch', 0)} |"
            )
        lines.append(
            f"| **合计** | {ab_totals['n_recorded']} | {ab_totals['n_abstained']} "
            f"| {ab_totals['n_actionable']} | {ab_totals['n_no_effect']} "
            f"| {ab_totals['n_suppressed']} | {ab_totals['suppressed_numerator']} "
            f"| {_ratio_text(ab_totals['suppressed_numerator'], ab_totals['suppressed_denominator'])} "
            f"| {ab_totals['n_signal_nonempty']} | {ab_totals['n_multi_signal']} "
            f"| {ab_totals['n_unknown_signals']} | {ab_totals['n_abstain_mismatch']} "
            f"| {ab_totals['n_signal_mismatch']} |"
        )
        lines.append("")
        lines.append(
            f"> 弃权的分母有两层：`abstained` {ab_totals['n_abstained']} 行里 "
            f"{ab_totals['n_no_effect']} 行是「失败且无补丁」——**没有可抑制对象**，"
            f"与真正的抑制同记 `True`；`可抑制` = {ab_totals['n_actionable']} 行。"
            f"`抑制精确率` = 被抑制的 passed 中 gold 判错 / 有 gold 裁决的被抑制行"
            f"（{ab_totals['suppressed_numerator']}/{ab_totals['suppressed_denominator']}）；"
            f"分母含全部被抑制行时为 {_ratio_text(ab_totals['suppressed_numerator'], ab_totals['n_suppressed'])}"
            "——两个数都要报，后者把 18 行无 gold 材料记为「非错误」。"
        )
        lines.append(
            "> 信号计数（可多选）："
            + "、".join(f"`{name}` {sig_counts.get(name, 0)}" for name in sig_domain)
            + f"；{ab_totals['n_multi_signal']} 行同时 ≥2 个信号，未知信号名 "
            f"{ab_totals['n_unknown_signals']} 个。信号域（已记录行的键状态）："
            + "；".join(
                f"`{name}` 记录 {counter.get('recorded', 0)}/null {counter.get('null', 0)}"
                f"/缺席 {counter.get('missing', 0)}"
                for name, counter in sig_domain.items()
            )
            + "。"
        )
        lines.append("")
        lines.append(
            "| 基线 | 验证已记录 | validated | unvalidated | 无输入 | 未验证且无输入 | passed | 抑制中 passed | 未抑制 passed | filtered success | filtered/passed | filtered/(passed∧¬abstain) | 判定不一致 | 验证不一致 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        va_totals = Counter()
        verdict_counts: Counter[str] = Counter()
        input_counts: Counter[str] = Counter()
        level_counts: Counter[str] = Counter()
        for baseline, s in acceptance_rows:
            va = s.get("validate", {})
            va_totals.update(
                {
                    "n_recorded": va.get("n_recorded", 0),
                    "n_validated": va.get("n_validated", 0),
                    "n_unvalidated": va.get("n_unvalidated", 0),
                    "n_no_input": va.get("n_no_input", 0),
                    "n_unvalidated_without_input": va.get("n_unvalidated_without_input", 0),
                    "n_passed": va.get("n_passed", 0),
                    "n_passed_abstained": va.get("n_passed_abstained", 0),
                    "n_passed_not_abstained": va.get("n_passed_not_abstained", 0),
                    "n_filtered_success": va.get("n_filtered_success", 0),
                    "n_verdict_mismatch": va.get("n_verdict_mismatch", 0),
                    "n_validated_mismatch": va.get("n_validated_mismatch", 0),
                }
            )
            verdict_counts.update(va.get("verdict", {}))
            input_counts.update(va.get("input_counts", {}))
            level_counts.update(va.get("evidence_level_values", {}))
            lines.append(
                f"| {baseline} | {va.get('n_recorded', 0)} | {va.get('n_validated', 0)} "
                f"| {va.get('n_unvalidated', 0)} | {va.get('n_no_input', 0)} "
                f"| {va.get('n_unvalidated_without_input', 0)} | {va.get('n_passed', 0)} "
                f"| {va.get('n_passed_abstained', 0)} | {va.get('n_passed_not_abstained', 0)} "
                f"| {va.get('n_filtered_success', 0)} "
                f"| {_ratio_text(va.get('n_filtered_success', 0), va.get('n_passed', 0))} "
                f"| {_ratio_text(va.get('n_filtered_success', 0), va.get('n_passed_not_abstained', 0))} "
                f"| {va.get('n_verdict_mismatch', 0)} | {va.get('n_validated_mismatch', 0)} |"
            )
        lines.append(
            f"| **合计** | {va_totals['n_recorded']} | {va_totals['n_validated']} "
            f"| {va_totals['n_unvalidated']} | {va_totals['n_no_input']} "
            f"| {va_totals['n_unvalidated_without_input']} | {va_totals['n_passed']} "
            f"| {va_totals['n_passed_abstained']} | {va_totals['n_passed_not_abstained']} "
            f"| {va_totals['n_filtered_success']} "
            f"| {_ratio_text(va_totals['n_filtered_success'], va_totals['n_passed'])} "
            f"| {_ratio_text(va_totals['n_filtered_success'], va_totals['n_passed_not_abstained'])} "
            f"| {va_totals['n_verdict_mismatch']} | {va_totals['n_validated_mismatch']} |"
        )
        lines.append("")
        lines.append(
            f"> 验证表的分母是 `patch_validated` **已记录**的 {va_totals['n_recorded']} 行"
            f"（早于批次 XVI 的 {acc_totals['n_rows'] - va_totals['n_recorded']} 行不在表内，"
            "不得读作「未验证」）。`unvalidated` ≠ 「验证过且失败」：其中 "
            f"{va_totals['n_unvalidated_without_input']} 行**根本没有可用的验证输入**。"
            f"`filtered success` = passed ∧ ¬abstained ∧ validated；两个分母分别回答"
            "「验证门在全部 passed 上保留了多少」与「在未被弃权的 passed 上保留了多少」。"
        )
        lines.append(
            "> 输入可达域："
            + "、".join(
                f"`{name}` {input_counts.get(name, 0)} 行"
                for name in ("repo_verification", "deterministic_repair_status", "patch_evidence_level")
            )
            + "——两个最强输入在整个归档里**可达域为空**，`validated=True` 全部来自最弱的证据档。"
            "`patch_evidence_level` 取值："
            + "、".join(f"`{level}` {count}" for level, count in sorted(level_counts.items()))
            + "。判定词表："
            + "、".join(f"`{name}` {count}" for name, count in sorted(verdict_counts.items()))
            + "。与判定核重跑的不一致：判定 "
            f"{va_totals['n_verdict_mismatch']} 行 / validated {va_totals['n_validated_mismatch']} 行。"
        )
        lines.append(
            "> 外部口径（BW 联网核对）：覆盖率与选择性风险按 selective prediction 的"
            "风险–覆盖曲线定义（coverage = 接受数 / 可测数，selective risk = 接受中错误数 / 接受数）；"
            "覆盖率为 0 时风险是**未定义**，不得写成 0。弃权精确率按「弃权决策中确实该弃权的占比」读，"
            "分母必须随值一起报。本节的四个已记录集各自成表：接收链、证据、弃权、验证。"
        )
        lines.append("")

    # BX 轮（2026-10-23）：写而不读键池最后两键的报告面读侧。改前 `risk_summary`
    # （8,864 行全 `enabled=False` 占位）与 `mdo_crash_rate`（五层输入域、分母=
    # 全池 n）在报告面零读者：通道没开与「全部低风险」同形，「未跑 / 材料缺 /
    # 不可测 / 暂定池 / 实测」同记 None。本节只分档与对账，判定值与方向一处不动。
    residual = {b: m.get("residual_keys", {}) for b, m in per.items()}
    residual_rows = sorted(((b, s) for b, s in residual.items() if s.get("n_rows")), key=lambda t: t[0])
    if residual_rows:
        lines.append("## 写而不读键池的收口（BX：`risk_summary` 与 `mdo_crash_rate` 的读侧）")
        lines.append("")
        lines.append(
            "| 基线 | 行数 | risk 在场 | 键缺席 | enabled=True | enabled=False | 7 键形状 | 6 键形状 | 其它形状 "
            "| level 非空 | pause=False | pause 缺席 | contract_status 在场 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        risk_totals: Counter = Counter()
        risk_shapes: Counter = Counter()
        shape7 = "approval_action|enabled|factors|pause_requested|reasons|risk_level|risk_score"
        shape6 = "approval_action|enabled|factors|reasons|risk_level|risk_score"
        for baseline, s in residual_rows:
            risk = s.get("risk_summary", {})
            shapes = risk.get("schema_shapes", {})
            risk_shapes.update(shapes)
            enabled = risk.get("enabled", {})
            pause = risk.get("pause", {})
            contract = risk.get("contract_status", {})
            risk_totals.update(
                {
                    "n_rows": risk.get("n_rows", 0),
                    "n_key_present": risk.get("n_key_present", 0),
                    "n_key_absent": risk.get("n_key_absent", 0),
                    "enabled_true": enabled.get("enabled_true", 0),
                    "enabled_false": enabled.get("enabled_false", 0),
                    "shape7": shapes.get(shape7, 0),
                    "shape6": shapes.get(shape6, 0),
                    "shape_other": sum(shapes.values()) - shapes.get(shape7, 0) - shapes.get(shape6, 0),
                    "level_nonnull": risk.get("level_nonnull", 0),
                    "pause_false": pause.get("false", 0),
                    "pause_absent": pause.get("absent", 0),
                    "contract_present": contract.get("present", 0),
                }
            )
            lines.append(
                f"| {baseline} | {risk.get('n_rows', 0)} | {risk.get('n_key_present', 0)} "
                f"| {risk.get('n_key_absent', 0)} | {enabled.get('enabled_true', 0)} "
                f"| {enabled.get('enabled_false', 0)} | {shapes.get(shape7, 0)} | {shapes.get(shape6, 0)} "
                f"| {sum(shapes.values()) - shapes.get(shape7, 0) - shapes.get(shape6, 0)} "
                f"| {risk.get('level_nonnull', 0)} | {pause.get('false', 0)} | {pause.get('absent', 0)} "
                f"| {contract.get('present', 0)} |"
            )
        lines.append(
            f"| **合计** | {risk_totals['n_rows']} | {risk_totals['n_key_present']} "
            f"| {risk_totals['n_key_absent']} | {risk_totals['enabled_true']} "
            f"| {risk_totals['enabled_false']} | {risk_totals['shape7']} | {risk_totals['shape6']} "
            f"| {risk_totals['shape_other']} | {risk_totals['level_nonnull']} "
            f"| {risk_totals['pause_false']} | {risk_totals['pause_absent']} | {risk_totals['contract_present']} |"
        )
        lines.append("")
        lines.append(
            f"> `risk_summary` 的读法：`enabled=False` 是**通道关闭**的占位——全归档 "
            f"{risk_totals['enabled_false']}/{risk_totals['n_key_present']} 行关闭、"
            f"`enabled=True` {risk_totals['enabled_true']} 行；`risk_level` 非空 "
            f"{risk_totals['level_nonnull']} 行。**`level=None` 不是 `low`**，"
            "`pause_requested=False` 也不是「判定无需暂停」（通道关闭时它恒为 False）。"
            "外部口径（BX 联网核对）：NIST SP 800-30 的风险等级是半定量分箱映射出的"
            "定性/序数标签，不是概率——没有开启记录就没有可读级别。"
            f"键缺席 {risk_totals['n_key_absent']} 行（早于该键落盘）不等于低风险；"
            f"`contract_status`（BL 起才写入）在 {risk_totals['n_key_present']} 行在场记录里 "
            f"{risk_totals['contract_present']} 行出现 ⇒「缺失符号为空可不可信」在归档上无证据。"
        )
        lines.append("")
        lines.append(
            "| 基线 | 行数 | 未跑 | 材料缺 | 不可测 | 暂定池 | 实测 | 值非空 | 值=0 | 值≠0 "
            "| floor=False | 其中非暂定 | 池化 crash（反推） | 行均值 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        mdo_totals: Counter = Counter()
        reason_counts: Counter = Counter()
        weighted_sum = 0.0
        for baseline, s in residual_rows:
            mdo = s.get("mdo_crash", {})
            layers = mdo.get("layers", {})
            value = mdo.get("value", {})
            pooled = mdo.get("pooled", {})
            mdo_totals.update(
                {
                    "n_rows": mdo.get("n_rows", 0),
                    "n_key_present": mdo.get("n_key_present", 0),
                    "n_key_absent": mdo.get("n_key_absent", 0),
                    "not_run": layers.get("not_run", 0),
                    "material_absent": layers.get("material_absent", 0),
                    "not_measurable": layers.get("not_measurable", 0),
                    "provisional": layers.get("provisional_pool", 0),
                    "measured": layers.get("measured", 0),
                    "value_nonnull": mdo.get("n_value_nonnull", 0),
                    "value_null": mdo.get("n_value_null", 0),
                    "zero": mdo.get("n_zero", 0),
                    "nonzero": mdo.get("n_nonzero", 0),
                    "floor_false": mdo.get("floor_false", 0),
                    "floor_false_other": mdo.get("floor_false_other", 0),
                    "pooled_crash": pooled.get("n_crash", 0),
                    "pooled_pool": pooled.get("n_pool", 0),
                    "pooled_ambiguous": pooled.get("n_ambiguous", 0),
                    "pooled_failed": pooled.get("n_failed", 0),
                    "evaluability": mdo.get("n_evaluability_recorded", 0),
                    "raw_present": mdo.get("provisional_raw", {}).get("n_present", 0),
                    "raw_zero": mdo.get("provisional_raw", {}).get("n_zero", 0),
                    "raw_nonzero": mdo.get("provisional_raw", {}).get("n_nonzero", 0),
                    "raw_crash": mdo.get("provisional_raw", {}).get("pooled", {}).get("n_crash", 0),
                    "raw_pool": mdo.get("provisional_raw", {}).get("pooled", {}).get("n_pool", 0),
                }
            )
            reason_counts.update(mdo.get("unmeasured_reasons", {}))
            if value.get("mean") is not None:
                weighted_sum += float(value["mean"]) * int(value.get("n", 0))
            mean_text = "—" if value.get("mean") is None else f"{value['mean']:.2%}"
            lines.append(
                f"| {baseline} | {mdo.get('n_rows', 0)} | {layers.get('not_run', 0)} "
                f"| {layers.get('material_absent', 0)} | {layers.get('not_measurable', 0)} "
                f"| {layers.get('provisional_pool', 0)} | {layers.get('measured', 0)} "
                f"| {mdo.get('n_value_nonnull', 0)} | {mdo.get('n_zero', 0)} | {mdo.get('n_nonzero', 0)} "
                f"| {mdo.get('floor_false', 0)} | {mdo.get('floor_false_other', 0)} "
                f"| {_ratio_text2(pooled.get('n_crash', 0), pooled.get('n_pool', 0))} | {mean_text} |"
            )
        mean_total = weighted_sum / mdo_totals["value_nonnull"] if mdo_totals["value_nonnull"] else None
        lines.append(
            f"| **合计** | {mdo_totals['n_rows']} | {mdo_totals['not_run']} "
            f"| {mdo_totals['material_absent']} | {mdo_totals['not_measurable']} "
            f"| {mdo_totals['provisional']} | {mdo_totals['measured']} "
            f"| {mdo_totals['value_nonnull']} | {mdo_totals['zero']} | {mdo_totals['nonzero']} "
            f"| {mdo_totals['floor_false']} | {mdo_totals['floor_false_other']} "
            f"| {_ratio_text2(mdo_totals['pooled_crash'], mdo_totals['pooled_pool'])} "
            f"| {'—' if mean_total is None else f'{mean_total:.2%}'} |"
        )
        lines.append("")
        lines.append(
            f"> `mdo_crash_rate` 的五层输入域：未跑 {mdo_totals['not_run']} / 材料缺 "
            f"{mdo_totals['material_absent']}（`mdo_available` 仍为 `None`，只有 `reason` 说明写侧早退）"
            f"/ 不可测 {mdo_totals['not_measurable']} / 暂定池 {mdo_totals['provisional']} / 实测 "
            f"{mdo_totals['measured']}，合计 = 键在场 {mdo_totals['n_key_present']}"
            f"；键缺席 {mdo_totals['n_key_absent']}"
            "（早于 MDO 落盘）。未给出规范值三层的成因："
            + "、".join(f"`{reason}` {count}" for reason, count in sorted(reason_counts.items()))
            + "。"
        )
        lines.append(
            f"> `mdo_pool_floor_ok=False` 是**两义键**：{mdo_totals['floor_false']} 行 = 暂定池 "
            f"{mdo_totals['provisional']} + 不可测 {mdo_totals['floor_false_other']}；后者是 "
            "`MDOResult` 的默认值，**不是池不足**——直接按该键筛「池不足」会多算 "
            f"{mdo_totals['floor_false_other']} 行。"
        )
        lines.append(
            "> 分母口径：crash 率 = `crashed / 全池 n`（`src/measurement/mdo.py` 的 CRASH 行；"
            "含 `non_terminating` / `probe_invalid` / `no_effective_pass`），与 MTR/MDR 的"
            "**可评估**分母不同。`mdo_status` / `mdo_evaluable` / `mdo_non_terminating` / "
            "`mdo_probe_invalid` / `mdo_no_effective_pass` 在归档 "
            f"{mdo_totals['evaluability']} 行在场 ⇒ 可评估分母**无法从归档复算**；"
            "crash 率不得与 MDR 相除或相减。"
        )
        lines.append(
            f"> 值域：规范值非空 {mdo_totals['value_nonnull']} 行（`0.0` {mdo_totals['zero']} 行 = "
            f"实测零崩溃；≠0 {mdo_totals['nonzero']} 行），空 {mdo_totals['value_null']} 行 = "
            "未测或被出口拦截——**`None` 不是 0**。同一批的逐行均值 "
            f"{'—' if mean_total is None else f'{mean_total:.2%}'} 与池化 "
            f"{mdo_totals['pooled_crash']}/{mdo_totals['pooled_pool']} = "
            f"{_ratio_text2(mdo_totals['pooled_crash'], mdo_totals['pooled_pool'])} 是两个口径"
            "（前者每行等权）。暂定池 "
            f"{mdo_totals['raw_present']} 行的原始值在 `mdo_raw`（`0.0` {mdo_totals['raw_zero']} / "
            f"≠0 {mdo_totals['raw_nonzero']}，池化 {mdo_totals['raw_crash']}/{mdo_totals['raw_pool']} = "
            f"{_ratio_text2(mdo_totals['raw_crash'], mdo_totals['raw_pool'])}），**不与实测合并**。"
            "反推：规范值已四舍五入到 4 位，分子按 `round(c/n,4)==rate` 在 `0..n` 内唯一整数解重建"
            f"（歧义 {mdo_totals['pooled_ambiguous']} 行 / 失败 {mdo_totals['pooled_failed']} 行）。"
            "外部口径（BX 联网核对）：Google Play `vitals.crashrate` 以去重用户数归一化并明确"
            "禁止再聚合该计数；同一分子换分母（per-session vs per-request）会得到不同读数 ⇒ "
            "crash 率必须带分母，且两个分母的读数不得相减。"
        )
        lines.append("")

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
