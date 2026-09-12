"""
实验结果结构化分析脚本（4.3）。

从 run_benchmark.py 输出的 JSON 结果中提取关键指标
（成功率、覆盖率、迭代次数分布、Token 消耗、RAG 检索质量、修复收敛效率、
多维质量代理、测试异味检测），生成 Markdown 汇总表格，减少手动分析 JSON 的工作量。

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
    - 多维质量代理：断言强度代理用 generated_test 中 assert 行数近似
      （有代码时），结构/运行时质量用覆盖率与耗时变化做保守代理；旧 JSON
      缺 optional 字段时只输出可计算部分，不崩溃。
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


def _rag_by_kind_from_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 指标自动汇总：按检索类型（test_cases vs repairs）分解检索质量。

    从 details[].rag_stats 逐条累计（每条记录 kind / results / max_similarity），
    分析"参考测试风格"与"参考修复方案"两类检索各自的命中率与相似度水平。

    Returns:
        {"test_cases": {retrievals, hits, hit_rate, avg_max_similarity},
         "repairs": {...}}；无 rag_stats 时返回空 dict。
    """
    per_kind: dict[str, dict[str, Any]] = {}
    for r in details:
        for s in r.get("rag_stats") or []:
            kind = s.get("kind", "unknown")
            stat = per_kind.setdefault(kind, {"retrievals": 0, "hits": 0, "sims": []})
            stat["retrievals"] += 1
            if s.get("results", 0) > 0:
                stat["hits"] += 1
            if s.get("max_similarity") is not None:
                stat["sims"].append(s["max_similarity"])
    result: dict[str, Any] = {}
    for kind, stat in per_kind.items():
        sims = stat.pop("sims")
        stat["hit_rate"] = round(stat["hits"] / stat["retrievals"], 4) if stat["retrievals"] else 0.0
        stat["avg_max_similarity"] = round(sum(sims) / len(sims), 4) if sims else None
        result[kind] = stat
    return result


def _rag_hit_by_failure_category(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 指标自动汇总：RAG 命中 × 失败类别交叉表。

    仅统计失败任务（passed=False），按 error_category 分组（1.1 细化后
    rag_retrieval_empty / patch_validation_failed 单独成组），记录组内
    "至少一次 RAG 检索命中"的任务数，用于分析 RAG 对哪些错误类型修复
    帮助最大（命中占比高 = 检索增强实际发生）。

    Returns:
        {error_category: {"total": 任务数, "with_hit": RAG 有命中的任务数}}；
        无失败任务时返回空 dict。
    """
    cross: dict[str, dict[str, int]] = {}
    for r in details:
        if r.get("passed"):
            continue
        cat = r.get("error_category") or "unknown"
        stat = cross.setdefault(cat, {"total": 0, "with_hit": 0})
        stat["total"] += 1
        if any(s.get("results", 0) > 0 for s in r.get("rag_stats") or []):
            stat["with_hit"] += 1
    return cross


def _repair_convergence_curve(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.3 修复收敛曲线：按迭代轮次累计通过率与累计修复成本。

    指标含义：
    - rounds: 按迭代轮次 0/1/2/3（3 表示 3+ 合并）分别统计"本轮及之前累计通过的任务数"
      与"本轮及之前累计消耗的平均耗时"，用于观察"随迭代次数增加，通过率如何变化"。
    - cumulative_pass_rate: 各轮累计通过率（0.0-1.0）。
    - cumulative_elapsed_seconds: 各轮累计平均耗时（成功任务的 mean elapsed）。
    - total_tasks: 任务总数（分母）。

    说明：
    - 仅统计 details 中已观测的迭代轮次；
    - 未产生该轮次的任务不计入分子，但计入分母（保守口径，避免高估通过率）；
    - 无任务时返回空结构，渲染时跳过章节。
    """
    total = len(details)
    if total == 0:
        return {"total_tasks": 0, "rounds": {}}
    max_observed = max((int(r.get("iterations", 0) or 0) for r in details), default=-1)
    rounds: dict[str, dict[str, Any]] = {}
    for k in range(max(0, min(max_observed, 3)) + 1):
        label = str(k) if k < 3 else "3+"
        reached = [r for r in details if int(r.get("iterations", 0) or 0) <= k]
        passed_in_reached = sum(1 for r in reached if r.get("passed"))
        elapsed_mean = (
            round(sum(float(r.get("elapsed_seconds", 0.0) or 0.0) for r in reached) / len(reached), 2)
            if reached
            else None
        )
        rounds[label] = {
            "reached_tasks": len(reached),
            "cumulative_passed": passed_in_reached,
            "cumulative_pass_rate": round(passed_in_reached / total, 4) if total else 0.0,
            "cumulative_elapsed_seconds": elapsed_mean,
        }
    return {
        "total_tasks": total,
        "rounds": rounds,
    }


def _test_smell_detection(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.2 测试异味检测：从 details[].generated_test 识别 LLM 生成测试的常见异味。

    异味清单（保守可复算，仅依赖结果 JSON 已有的 generated_test 字段）：
    - assertion_roulette: 测试函数内无 assert / pytest.raises / return 之外的断言语句；
    - magic_number: 出现未命名常量数字字面量（如 == 42 而非 NOMINAL_VALUE）；
    - assertion_weakening: 任务内 generated_test 较上一轮（repair_history 中）断言数减少；
    - trivial_test: 测试函数体仅含 pass / 单一 assert True 类恒真断言。

    返回：
        {"available": bool, "observed_tasks": int,
         "smell_counts": {"assertion_roulette": n, "magic_number": n,
                           "assertion_weakening": n, "trivial_test": n},
         "tasks_with_smells": [task_id...]}

    说明：仅当 details 携带 generated_test 时 available=True；否则返回
    available=False（渲染时跳过章节）。
    """
    observed = 0
    smell_counts = {
        "assertion_roulette": 0,
        "magic_number": 0,
        "assertion_weakening": 0,
        "trivial_test": 0,
    }
    tasks_with_smells: list[str] = []
    for row in details:
        test_code = row.get("generated_test")
        if not isinstance(test_code, str) or not test_code.strip():
            continue
        observed += 1
        task_id = str(row.get("task_id", f"row_{observed}"))
        task_has_smell = False

        # 简单启发：测试函数体是否包含有效断言（assert / pytest.raises）
        stripped = test_code.strip()
        has_assertion = "assert " in stripped or "pytest.raises" in stripped
        if not has_assertion:
            # 区分"无断言但非平凡"（仅 Assignment/Function 调用，无有效断言语句）
            # 与"平凡测试"（函数体仅含 pass / return None / 单一 assert True）
            body_lines = [
                ln for ln in stripped.splitlines()
                if ln.strip() and not ln.strip().startswith(("def ", "#", "import ", "from "))
            ]
            is_trivial = len(body_lines) <= 2 and any(
                ln.strip() in ("pass", "return None", "") for ln in body_lines
            )
            if is_trivial:
                smell_counts["trivial_test"] += 1
                task_has_smell = True
            else:
                smell_counts["assertion_roulette"] += 1
                task_has_smell = True

        # 魔数检测：数字字面量未绑定到命名常量（保守口径：仅统计 "assert X == <int>" 中
        # 未出现在命名常量赋值语句中的数字；这里简化为：若代码中没有 "const" 类赋值
        # 但出现 >= 3 个独立整数字面量，则判定为 magic_number）
        if "==" in stripped:
            import re

            literals = set(re.findall(r"==\s*(-?\d+)\b", stripped))
            if len(literals) >= 3 and not any(
                line.strip().startswith(("CONST", "NOMINAL", "LIMIT", "THRESHOLD"))
                for line in stripped.splitlines()
            ):
                smell_counts["magic_number"] += 1
                task_has_smell = True

        # 断言弱化：repair_history 中若记录了上一轮断言数且当前断言数减少，则判定
        history = row.get("repair_history") or []
        prev_assertions = row.get("prev_assertion_count")
        cur_assertions = sum(1 for line in stripped.splitlines() if line.strip().startswith("assert "))
        if prev_assertions is not None and cur_assertions < int(prev_assertions):
            smell_counts["assertion_weakening"] += 1
            task_has_smell = True
        # 顺带把 repair_history 中记录的断言数变化做轻量检测（若字段存在）
        if history and isinstance(history, list):
            for h in history:
                if isinstance(h, dict) and "assertion_count" in h and "prev_assertion_count" in h:
                    if int(h["assertion_count"]) < int(h["prev_assertion_count"]):
                        smell_counts["assertion_weakening"] += 1
                        task_has_smell = True
                        break

        # 平凡测试：函数体仅含 pass / return None / 单一恒真断言（已计入上方分支）
        # 此处仅处理"有断言但恒真"的情形（如 assert True / assert 1 == 1）
        trivial_const_asserts = [
            ln for ln in stripped.splitlines()
            if ln.strip().startswith("assert") and ("True" in ln or "1 == 1" in ln or "0 == 0" in ln)
        ]
        body_lines = [
            ln for ln in stripped.splitlines()
            if ln.strip() and not ln.strip().startswith(("def ", "#", "import ", "from "))
        ]
        if has_assertion and len(body_lines) <= 2 and trivial_const_asserts:
            smell_counts["trivial_test"] += 1
            task_has_smell = True

        if task_has_smell:
            tasks_with_smells.append(task_id)

    if observed == 0:
        return {"available": False, "observed_tasks": 0, "smell_counts": smell_counts, "tasks_with_smells": []}
    return {
        "available": True,
        "observed_tasks": observed,
        "smell_counts": smell_counts,
        "tasks_with_smells": tasks_with_smells,
    }


def _repair_convergence_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.2 修复收敛效率：从 details[] 统计成功/失败任务的迭代与耗时结构。

    指标含义：
    - first_attempt_success_rate: iterations==0 且 passed=True 的任务占比；
    - success_iteration_stats: 成功任务的 min/avg/median/max iterations；
    - failed_iteration_stats: 失败任务的 min/avg/median/max iterations；
    - success_elapsed_seconds: 成功任务的 min/avg/median/max 耗时。

    该函数只在有 detail 时可计算；无任务时返回空结构（渲染时跳过章节）。
    """
    success_rows = [r for r in details if r.get("passed")]
    failed_rows = [r for r in details if not r.get("passed")]
    total = len(details)
    first_attempt_passed = sum(1 for r in success_rows if int(r.get("iterations", 0) or 0) == 0)

    def _stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "min": None, "avg": None, "median": None, "max": None}
        ordered = sorted(values)
        n = len(ordered)
        median = ordered[n // 2] if n % 2 == 1 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
        return {
            "count": n,
            "min": round(min(ordered), 2),
            "avg": round(sum(ordered) / n, 2),
            "median": round(median, 2),
            "max": round(max(ordered), 2),
        }

    return {
        "total_tasks": total,
        "success_tasks": len(success_rows),
        "failed_tasks": len(failed_rows),
        "first_attempt_success_rate": round(first_attempt_passed / total, 4) if total else 0.0,
        "first_attempt_success_count": first_attempt_passed,
        "success_iteration_stats": _stats([float(r.get("iterations", 0) or 0) for r in success_rows]),
        "failed_iteration_stats": _stats([float(r.get("iterations", 0) or 0) for r in failed_rows]),
        "success_elapsed_seconds": _stats([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in success_rows]),
        "failed_elapsed_seconds": _stats([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in failed_rows]),
    }


def _assertion_strength_proxy(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.1 断言强度代理：用 generated_test 中 assert 行数量做保守近似。

    说明：benchmark 结果本身不会保存完整断言语义，这里仅统计可选字段
    generated_test（若未来 --save-state 的 details 扩展带上该字段）中的
    `assert ` 行数，用于观察"修复/生成是否出现断言弱化"的趋势。旧 JSON
    无 generated_test 时返回 available=False，渲染时跳过该小节。
    """
    observed = 0
    assertion_counts: list[int] = []
    for row in details:
        test_code = row.get("generated_test")
        if not isinstance(test_code, str) or not test_code.strip():
            continue
        observed += 1
        assertion_counts.append(sum(1 for line in test_code.splitlines() if line.strip().startswith("assert ")))

    if not assertion_counts:
        return {"available": False, "observed_tasks": 0}
    avg = sum(assertion_counts) / len(assertion_counts)
    return {
        "available": True,
        "observed_tasks": observed,
        "avg_assertions_per_task": round(avg, 2),
        "min_assertions": min(assertion_counts),
        "max_assertions": max(assertion_counts),
        "tasks_with_zero_assertions": sum(1 for value in assertion_counts if value == 0),
    }


def _quality_proxy_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.1 多维质量代理：基于现有字段给出保守可复算指标。

    当前 benchmark JSON 缺少补丁前后的 AST 圈复杂度、内存占用和原始执行
    轨迹，因此这里只报告可由结果文件直接验证的代理维度：
    - coverage_proxy: 成功/失败任务的覆盖率均值与中位数；
    - runtime_proxy: 成功/失败任务的耗时均值与中位数；
    - assertion_proxy: 可选 generated_test 的 assert 行数；
    - failure_proxy: 失败任务错误类别 Top N。

    该输出明确标注为 proxy，避免被误读为精确结构质量或性能回归指标。
    """
    success_rows = [r for r in details if r.get("passed")]
    failed_rows = [r for r in details if not r.get("passed")]

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        n = len(ordered)
        median = ordered[n // 2] if n % 2 == 1 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
        return round(median, 2)

    return {
        "coverage_proxy": {
            "success": {
                "mean": _mean([float(r.get("coverage", 0.0) or 0.0) for r in success_rows]),
                "median": _median([float(r.get("coverage", 0.0) or 0.0) for r in success_rows]),
            },
            "failed": {
                "mean": _mean([float(r.get("coverage", 0.0) or 0.0) for r in failed_rows]),
                "median": _median([float(r.get("coverage", 0.0) or 0.0) for r in failed_rows]),
            },
        },
        "runtime_proxy": {
            "success": {
                "mean": _mean([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in success_rows]),
                "median": _median([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in success_rows]),
            },
            "failed": {
                "mean": _mean([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in failed_rows]),
                "median": _median([float(r.get("elapsed_seconds", 0.0) or 0.0) for r in failed_rows]),
            },
        },
        "assertion_proxy": _assertion_strength_proxy(details),
        "failure_top_categories": _failure_top_categories(failed_rows),
    }


def _failure_top_categories(details: list[dict[str, Any]], top_n: int = 5) -> dict[str, Any]:
    """从失败任务中提取 Top N 错误类别，辅助结构/逻辑质量归因。"""
    counter: Counter = Counter()
    for row in details:
        if row.get("passed"):
            continue
        counter[row.get("error_category") or "unknown"] += 1
    items = counter.most_common(top_n)
    return {
        "top_n": top_n,
        "distribution": {category: count for category, count in items},
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
            # 2.3 RAG 指标自动汇总（从 details[].rag_stats 计算，旧 JSON 无 rag_stats 时为空）
            "details_rag_by_kind": _rag_by_kind_from_details(details),
            "rag_hit_by_failure_category": _rag_hit_by_failure_category(details),
            # 1.2 修复收敛效率 + 1.1 多维质量代理（从 details 可复算，旧 JSON 容错）
            "repair_convergence_metrics": _repair_convergence_metrics(details),
            # 1.3 修复收敛曲线（按迭代轮次累计通过率）
            "repair_convergence_curve": _repair_convergence_curve(details),
            # 1.2 测试异味检测（LLM 生成测试的可维护性代理）
            "test_smell_metrics": _test_smell_detection(details),
            "quality_proxy_metrics": _quality_proxy_metrics(details),
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
        if m.get("repair_convergence_curve", {}).get("total_tasks", 0) > 0 and m["repair_convergence_curve"].get("rounds")
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

    # 测试异味检测（1.2）：LLM 生成测试的可维护性代理
    smell_rows = [
        (b, m["test_smell_metrics"])
        for b, m in per.items()
        if m.get("test_smell_metrics", {}).get("available")
    ]
    if smell_rows:
        lines.append("## 测试异味检测（1.2）")
        lines.append("")
        lines.append("| 基线 | 观测任务 | Assertion Roulette | Magic Number | 断言弱化 | 平凡测试 | 含异味任务 |")
        lines.append("|------|---------|-------------------|--------------|---------|---------|----------|")
        for baseline, s in smell_rows:
            c = s.get("smell_counts", {})
            lines.append(
                f"| {baseline} | {s.get('observed_tasks', 0)} "
                f"| {c.get('assertion_roulette', 0)} | {c.get('magic_number', 0)} "
                f"| {c.get('assertion_weakening', 0)} | {c.get('trivial_test', 0)} "
                f"| {len(s.get('tasks_with_smells', []))} |"
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
