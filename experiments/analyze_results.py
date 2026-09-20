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
import ast
import json
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 2.1 数据污染检测模块（experiments 包内相对导入，sys.path 注入后方可用）
from experiments.contamination_check import (
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


# ── 测试异味 AST 阈值（保守口径）──────────────────────────────────────────────
# 单个 test_* 函数内独立断言数 >= 4 且被测目标 >= 2 判为 Eager Test
# （一个方法验证过多功能，拆分成本高的异味）
EAGER_TEST_ASSERT_THRESHOLD = 4
# 单个 test_* 函数内断言涉及的不同被测目标（函数调用名/属性名）>= 2 才判 Eager
EAGER_TEST_TARGET_THRESHOLD = 2
# 多 test_* 函数间"目标集合两两不重叠"占比 >= 0.5 判为 Lack of Cohesion
# （实证研究中最常见的异味 41.2%，阈值取保守 0.5 避免误报）
LACK_OF_COHESION_THRESHOLD = 0.5
# 异味密度 = 单任务异味种类数 / 6（任务无异味记 0），用于质量代理的独立维度
# （1.1 改进：异味密度作为与断言行数并列的保守可复算质量信号）
SMELL_TYPE_COUNT = 6


def _smell_task_has_smell(row: dict[str, Any], test_code: str) -> set[str]:
    """计算单任务（generated_test 非空）命中的测试异味种类集合（保守启发）。

    与 _test_smell_detection 原逐行计数逻辑同口径（判定规则只实现一次，
    供异味计数与异味密度/策略分组复用，DRY）：
    - assertion_roulette / trivial_test: 无有效断言或函数体仅恒真断言；
    - magic_number: >= 3 个独立整数字面量且无命名常量赋值；
    - assertion_weakening: 与上一轮（repair_history / prev_assertion_count）
      相比断言数减少；
    - eager_test / lack_of_cohesion: AST 口径（见模块级阈值常量）。

    Args:
        row: benchmark details 行（repair_history / prev_assertion_count 等）。
        test_code: generated_test 源码（非空）。

    Returns:
        命中的异味种类集合（无异味时为空集）。
    """
    smells: set[str] = set()
    stripped = test_code.strip()
    has_assertion = "assert " in stripped or "pytest.raises" in stripped

    # 简单启发：测试函数体是否包含有效断言（assert / pytest.raises）
    if not has_assertion:
        # 区分"无断言但非平凡"（仅 Assignment/Function 调用，无有效断言语句）
        # 与"平凡测试"（函数体仅含 pass / return None / 单一 assert True）
        body_lines = [
            ln
            for ln in stripped.splitlines()
            if ln.strip() and not ln.strip().startswith(("def ", "#", "import ", "from "))
        ]
        is_trivial = len(body_lines) <= 2 and any(ln.strip() in ("pass", "return None", "") for ln in body_lines)
        smells.add("trivial_test" if is_trivial else "assertion_roulette")

    # 魔数检测：数字字面量未绑定到命名常量（保守口径：仅统计 "assert X == <int>" 中
    # 未出现在命名常量赋值语句中的数字；这里简化为：若代码中没有 "const" 类赋值
    # 但出现 >= 3 个独立整数字面量，则判定为 magic_number）
    if "==" in stripped:
        import re

        literals = set(re.findall(r"==\s*(-?\d+)\b", stripped))
        if len(literals) >= 3 and not any(
            line.strip().startswith(("CONST", "NOMINAL", "LIMIT", "THRESHOLD")) for line in stripped.splitlines()
        ):
            smells.add("magic_number")

    # 断言弱化：repair_history 中若记录了上一轮断言数且当前断言数减少，则判定
    history = row.get("repair_history") or []
    prev_assertions = row.get("prev_assertion_count")
    cur_assertions = sum(1 for line in stripped.splitlines() if line.strip().startswith("assert "))
    if prev_assertions is not None and cur_assertions < int(prev_assertions):
        smells.add("assertion_weakening")
    # 顺带把 repair_history 中记录的断言数变化做轻量检测（若字段存在）
    if history and isinstance(history, list):
        for h in history:
            if (
                isinstance(h, dict)
                and "assertion_count" in h
                and "prev_assertion_count" in h
                and int(h["assertion_count"]) < int(h["prev_assertion_count"])
            ):
                smells.add("assertion_weakening")
                break

    # 平凡测试：函数体仅含 pass / return None / 单一恒真断言（已计入上方分支）
    # 此处仅处理"有断言但恒真"的情形（如 assert True / assert 1 == 1）
    trivial_const_asserts = [
        ln
        for ln in stripped.splitlines()
        if ln.strip().startswith("assert") and ("True" in ln or "1 == 1" in ln or "0 == 0" in ln)
    ]
    body_lines = [
        ln
        for ln in stripped.splitlines()
        if ln.strip() and not ln.strip().startswith(("def ", "#", "import ", "from "))
    ]
    if has_assertion and len(body_lines) <= 2 and trivial_const_asserts:
        smells.add("trivial_test")

    # ── AST 口径异味：Eager Test + Lack of Cohesion（解析失败时跳过）──
    import ast as _ast_smell

    try:
        tree = _ast_smell.parse(stripped)
    except (SyntaxError, ValueError):
        tree = None

    if tree is not None:
        # 收集所有 test_* 函数
        test_funcs = [
            node for node in _ast_smell.walk(tree)
            if isinstance(node, _ast_smell.FunctionDef) and node.name.startswith("test_")
        ]
        # Eager Test：单个测试函数内独立断言数 >= 阈值，
        # 且断言涉及的不同"被测目标"（Call.func 名 / Attribute.attr）>= 2
        for tf in test_funcs:
            assert_nodes = [n for n in _ast_smell.walk(tf) if isinstance(n, _ast_smell.Assert)]
            if len(assert_nodes) < EAGER_TEST_ASSERT_THRESHOLD:
                continue
            targets: set = set()
            for n in _ast_smell.walk(tf):
                if isinstance(n, _ast_smell.Call) and isinstance(n.func, _ast_smell.Name):
                    targets.add(n.func.id)
                elif isinstance(n, _ast_smell.Attribute):
                    targets.add(n.attr)
            if len(targets) >= EAGER_TEST_TARGET_THRESHOLD:
                smells.add("eager_test")
                break

        # Lack of Cohesion：多个测试函数的"被测目标集合"两两不重叠占比 >= 阈值
        if len(test_funcs) >= 2:
            func_targets: list = []
            for tf in test_funcs:
                t: set = set()
                for n in _ast_smell.walk(tf):
                    if isinstance(n, _ast_smell.Call) and isinstance(n.func, _ast_smell.Name):
                        t.add(n.func.id)
                    elif isinstance(n, _ast_smell.Attribute):
                        t.add(n.attr)
                func_targets.append(t)
            non_overlap_pairs = 0
            total_pairs = 0
            for i in range(len(func_targets)):
                for j in range(i + 1, len(func_targets)):
                    total_pairs += 1
                    if not (func_targets[i] & func_targets[j]):
                        non_overlap_pairs += 1
            if total_pairs > 0 and (non_overlap_pairs / total_pairs) >= LACK_OF_COHESION_THRESHOLD:
                smells.add("lack_of_cohesion")

    return smells


def _test_smell_detection(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.2 测试异味检测：从 details[].generated_test 识别 LLM 生成测试的常见异味。

    异味清单（保守可复算，仅依赖结果 JSON 已有的 generated_test 字段）：
    - assertion_roulette: 测试函数内无 assert / pytest.raises / return 之外的断言语句；
    - magic_number: 出现未命名常量数字字面量（如 == 42 而非 NOMINAL_VALUE）；
    - assertion_weakening: 任务内 generated_test 较上一轮（repair_history 中）断言数减少；
    - trivial_test: 测试函数体仅含 pass / 单一 assert True 类恒真断言；
    - eager_test: 单个测试方法验证过多功能（AST 口径：一个 test_* 函数内
      独立断言 >= EAGER_TEST_ASSERT_THRESHOLD 且断言涉及的不同被测目标
      >= EAGER_TEST_TARGET_THRESHOLD，即"一个方法测多件事"）；
    - lack_of_cohesion: 测试文件内缺乏内聚性（AST 口径：多个 test_* 函数的
      被测目标集合两两不重叠占比 >= LACK_OF_COHESION_THRESHOLD，说明各用例
      各自为战、无共享测试主题）。

    返回：
        {"available": bool, "observed_tasks": int,
         "smell_counts": {"assertion_roulette": n, "magic_number": n,
                           "assertion_weakening": n, "trivial_test": n,
                           "eager_test": n, "lack_of_cohesion": n},
         "tasks_with_smells": [task_id...]}

    辅助函数 _smell_task_has_smell(row) 计算单任务异味集合，本函数汇总；
    异味密度（smell_density）= 有异味任务数 / 观测任务数（保守口径，
    每任务最多 1，避免单任务多异味虚增密度）；按 strategy 分组的
    smell_counts_by_strategy 支持"异味分布 × 生成策略"交叉分析。
    """
    observed = 0
    smell_counts = {
        "assertion_roulette": 0,
        "magic_number": 0,
        "assertion_weakening": 0,
        "trivial_test": 0,
        "eager_test": 0,
        "lack_of_cohesion": 0,
    }
    # 按策略分组的异味计数（details[].strategy 非空时收集）
    by_strategy: dict[str, dict[str, Any]] = {}
    tasks_with_smells: list[str] = []
    for row in details:
        test_code = row.get("generated_test")
        if not isinstance(test_code, str) or not test_code.strip():
            continue
        observed += 1
        task_id = str(row.get("task_id", f"row_{observed}"))
        smells = _smell_task_has_smell(row, test_code)
        task_has_smell = bool(smells)
        strategy = str(row.get("strategy") or "").strip()
        if strategy:
            stat = by_strategy.setdefault(
                strategy,
                {
                    "observed_tasks": 0,
                    "tasks_with_smells": 0,
                    "smell_counts": dict.fromkeys(smell_counts, 0),
                },
            )
            stat["observed_tasks"] += 1
            if smells:
                stat["tasks_with_smells"] += 1
            for name in smells:
                stat["smell_counts"][name] += 1
        for name in smells:
            smell_counts[name] += 1
        if task_has_smell:
            tasks_with_smells.append(task_id)

    if observed == 0:
        return {"available": False, "observed_tasks": 0, "smell_counts": smell_counts, "tasks_with_smells": []}
    smell_density = round(len(tasks_with_smells) / observed, 4)
    # 按策略分组的异味密度（有异味任务 / 该策略观测任务）
    for stat in by_strategy.values():
        stat["smell_density"] = round(stat["tasks_with_smells"] / stat["observed_tasks"], 4) if stat["observed_tasks"] else 0.0
    result: dict[str, Any] = {
        "available": True,
        "observed_tasks": observed,
        "smell_counts": smell_counts,
        "smell_density": smell_density,
        "tasks_with_smells": tasks_with_smells,
    }
    if by_strategy:
        result["smell_counts_by_strategy"] = by_strategy
    return result


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


def _convergence_token_efficiency(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.3 修复收敛的 Token 效率曲线：把逐轮 Token 消耗与迭代轮次结合。

    1.3 改进："第几轮修复的边际收益最高"——按迭代轮次（0/1/2/3+）分别统计：
    - 该轮"增量"Token（该轮消耗的 Token，从 details[].token_usage.iterations 逐轮累加；
      旧 JSON 无逐轮字段时回退为"整任务均摊到其经历的各轮"，保守口径）；
    - 该轮的"增量通过率"（累计通过 - 上轮累计通过）与"增量 Token 成本"，
      二者相除得到"每 Token 换来多少新通过任务"的边际收益代理；
    - 边际收益最高的轮次标签（用于回答"第几轮修复最划算"）。

    说明：
    - Token 消耗字段：details[].token_usage.total_tokens（旧 JSON 兜底累加）；
      逐轮 Token 明细（iterations[].tokens）若存在则精确到轮次，否则按
      "总 Token / 任务经历的轮次数"均摊（保守口径，避免高估单轮成本）；
    - 无 Token 数据时 available=False，渲染跳过章节。
    """
    total = len(details)
    if total == 0:
        return {"available": False, "total_tasks": 0, "rounds": {}}
    max_observed = max((int(r.get("iterations", 0) or 0) for r in details), default=-1)
    # 逐轮累计：到达任务数 / 累计通过 / 累计 Token（含本轮增量）
    rounds: dict[str, dict[str, Any]] = {}
    prev_cumulative_passed = 0
    prev_cumulative_tokens = 0.0
    for k in range(max(0, min(max_observed, 3)) + 1):
        label = str(k) if k < 3 else "3+"
        reached = [r for r in details if int(r.get("iterations", 0) or 0) <= k]
        cumulative_passed = sum(1 for r in reached if r.get("passed"))
        # 逐轮 Token：优先读 token_usage.iterations[k].tokens（精确口径），
        # 缺失时按"总 Token / 该任务经历的轮次数(=k+1)"均摊（保守口径）
        round_tokens = 0.0
        for r in reached:
            usage = r.get("token_usage") or {}
            per_round = usage.get("iterations")
            if isinstance(per_round, list) and k < len(per_round) and isinstance(per_round[k], dict):
                round_tokens += float(per_round[k].get("tokens", 0) or 0)
            else:
                round_tokens += float(usage.get("total_tokens", 0) or 0) / (k + 1)
        incremental_passed = max(0, cumulative_passed - prev_cumulative_passed)
        incremental_tokens = round_tokens - prev_cumulative_tokens
        marginal = round(incremental_passed / incremental_tokens, 6) if incremental_tokens > 0 else None
        rounds[label] = {
            "reached_tasks": len(reached),
            "cumulative_passed": cumulative_passed,
            "cumulative_tokens": round(prev_cumulative_tokens + incremental_tokens, 2),
            "incremental_passed": incremental_passed,
            "incremental_tokens": round(incremental_tokens, 2),
            "marginal_pass_per_token": marginal,
        }
        prev_cumulative_passed = cumulative_passed
        prev_cumulative_tokens += incremental_tokens
    # 边际收益最高的轮次（None 值跳过；全部 None 时为 None）
    best_round = None
    best_marginal = 0.0
    for label in ("0", "1", "2", "3+"):
        marginal = rounds.get(label, {}).get("marginal_pass_per_token")
        if marginal is not None and marginal > best_marginal:
            best_marginal = marginal
            best_round = label
    return {
        "available": True,
        "total_tasks": total,
        "rounds": rounds,
        "best_marginal_round": best_round,
    }


def _difficulty_stratified_iterations(
    details: list[dict[str, Any]],
    difficulty_bands: dict[str, int] | None = None,
) -> dict[str, Any]:
    """1.3 修复迭代分布的分层统计：按任务难度分层看迭代次数分布。

    1.3 改进：聚合迭代分布掩盖"不同难度任务收敛行为差异"。本函数把
    任务按难度分档（difficulty_bands: task_id → 难度档，外部可由
    difficulty_stratification 的 code_size/dependency_count/complexity_proxy
    分档结果传入），统计各难度档下 0/1/2/3+ 迭代的任务数分布。

    Args:
        details: benchmark details 列表。
        difficulty_bands: task_id → 难度档（如 "easy"/"medium"/"hard"）的映射；
            None 或空时全部任务归入 "unstratified" 档。

    Returns:
        {band: {"total": n, "iterations": {"0": n0, "1": n1, "2": n2, "3+": np}}}；
        无任务时返回 {"available": False, "bands": {}}。
    """
    bands = difficulty_bands or {}
    stratified: dict[str, dict[str, int]] = {}
    for row in details:
        task_id = str(row.get("task_id", ""))
        band = str(bands.get(task_id) or "unstratified")
        iters = min(int(row.get("iterations", 0) or 0), 3)
        label = str(iters) if iters < 3 else "3+"
        stat = stratified.setdefault(band, {"total": 0, "iterations": {}})
        stat["total"] += 1
        stat["iterations"][label] = stat["iterations"].get(label, 0) + 1
    if not stratified:
        return {"available": False, "bands": {}}
    return {"available": True, "bands": stratified}


def _cross_baseline_convergence_comparison(
    per_baseline: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """1.3 跨基线收敛对比：把 aitester 与各 plain_llm 变体的收敛曲线叠加。

    1.3 改进：单基线收敛曲线无法直接回答"多智能体协作在收敛速度上是否
    优于单智能体基线"。本函数收集 per_baseline 中各基线的
    repair_convergence_curve，按轮次对齐后输出叠加视图，并计算两个关键
    对比指标：
    - first_attempt_delta: 各基线"首轮即通过"任务占比的差异
      （aitester - plain_llm，正值 = 多智能体协作首轮成功率更高）；
    - cumulative_pass_rate_at_1: 第 1 轮（k=1）累计通过率的基线间差异
      （若 aitester 在该轮领先，说明协作机制的增益来自"一次做对"而非
      "多轮调试追平"）。

    对齐规则：
    - 仅纳入 per_baseline 中同时携带 repair_convergence_curve 的基线；
    - 基线数 < 2 时 available=False（无对比对象），渲染层跳过章节；
    - 各基线任务数可能不同，对比使用"通过率"（分母各自独立）而非任务数。

    Args:
        per_baseline: build_analysis 产出的 per_baseline 字典
            （{baseline: {repair_convergence_curve: {...}, ...}}）。

    Returns:
        {"available": bool,
         "baselines": [baseline...],
         "aligned_rounds": {"0": {baseline: cumulative_pass_rate}, "1": {...}, ...},
         "first_attempt_delta": float | None,
         "cumulative_pass_rate_at_1_delta": float | None}
        first_attempt_delta / cumulative_pass_rate_at_1_delta 取
        "含 'aitester' 且不含 'plain' 的基线" 与 "含 'plain' 的基线"
        两组的均值差；任一组为空时为 None。
    """
    baselines_with_curve = [
        bl for bl, m in per_baseline.items()
        if m.get("repair_convergence_curve", {}).get("rounds")
    ]
    if len(baselines_with_curve) < 2:
        return {"available": False, "baselines": baselines_with_curve}

    # 按轮次对齐累计通过率（各基线独立分母，保守口径）
    aligned: dict[str, dict[str, float]] = {}
    for bl in baselines_with_curve:
        rounds = per_baseline[bl]["repair_convergence_curve"]["rounds"]
        for k in ("0", "1", "2", "3+"):
            r = rounds.get(k)
            if not r:
                continue
            aligned.setdefault(k, {})[bl] = r.get("cumulative_pass_rate", 0.0)

    # 分组：协作组（含 aitester 且不含 plain）vs 基线组（含 plain）
    collab_group = [bl for bl in baselines_with_curve if "aitester" in bl and "plain" not in bl]
    plain_group = [bl for bl in baselines_with_curve if "plain" in bl]

    def _mean_rate(group: list[str], key: str) -> float | None:
        values = [aligned.get(key, {}).get(bl) for bl in group]
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    first_attempt_delta: float | None = None
    at1_delta: float | None = None
    if collab_group and plain_group:
        collab_first = _mean_rate(collab_group, "0")
        plain_first = _mean_rate(plain_group, "0")
        if collab_first is not None and plain_first is not None:
            first_attempt_delta = round(collab_first - plain_first, 4)
        collab_at1 = _mean_rate(collab_group, "1")
        plain_at1 = _mean_rate(plain_group, "1")
        if collab_at1 is not None and plain_at1 is not None:
            at1_delta = round(collab_at1 - plain_at1, 4)

    return {
        "available": True,
        "baselines": baselines_with_curve,
        "aligned_rounds": aligned,
        "first_attempt_delta": first_attempt_delta,
        "cumulative_pass_rate_at_1_delta": at1_delta,
        "collab_group": collab_group,
        "plain_group": plain_group,
    }


def _cross_file_failure_analysis(
    per_baseline: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """2.2 跨文件修复失败案例分析：统计启用跨文件修复的基线中失败任务的
    错误类别分布与跨文件相关信号。

    2.2 改进：跨文件修复（CROSS_FILE_ENABLE=true）在真实数据集约 40%
    任务需要多文件修改的场景下启用后，失败模式与单文件修复可能不同
    （如"依赖边分析为空但任务实际跨文件"）。本函数收集：
    - 各基线中"含 cross_file 相关信号"（details[].cross_file_deps 非空
      或 error_category 命中跨文件相关类别）的任务占比；
    - 失败任务的 error_category 分布（识别跨文件场景下的高频失败类别）；
    - 失败任务中 diagnosis 含"import" / "module" 关键词的比例
      （跨文件修复失败的典型表征：模块路径/导入关系未正确处理）。

    Args:
        per_baseline: build_analysis 产出的 per_baseline 字典。

    Returns:
        {"available": bool,
         "by_baseline": {baseline: {"total", "failed", "failed_categories": {...},
                                    "import_related_failed": int}},
         "import_related_rate": float | None}
        无失败任务时 available=False（渲染层跳过章节）。
    """
    by_baseline: dict[str, dict[str, Any]] = {}
    total_failed = 0
    import_related_failed = 0
    for bl, m in per_baseline.items():
        details = m.get("_details") or []
        if not details:
            continue
        failed_rows = [r for r in details if not r.get("passed")]
        if not failed_rows:
            continue
        cat_counter: Counter = Counter()
        import_related = 0
        for row in failed_rows:
            cat = str(row.get("error_category") or "unknown")
            cat_counter[cat] += 1
            diag = str(row.get("diagnosis") or "").lower()
            # 跨文件失败典型信号：诊断文本含 import/module/模块 关键词
            if any(kw in diag for kw in ("import", "module", "模块")):
                import_related += 1
        by_baseline[bl] = {
            "total": len(details),
            "failed": len(failed_rows),
            "failed_categories": dict(cat_counter.most_common()),
            "import_related_failed": import_related,
        }
        total_failed += len(failed_rows)
        import_related_failed += import_related
    if total_failed == 0:
        return {"available": False, "by_baseline": {}}
    return {
        "available": True,
        "by_baseline": by_baseline,
        "import_related_rate": round(import_related_failed / total_failed, 4),
    }


def _assertion_strength_proxy(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.1/1.3 断言强度：AST 静态分析 + 行数统计双口径。

    说明：benchmark 结果不会保存完整断言语义，这里基于可选字段
    generated_test（--save-state 的 details 扩展带上时可用）：
    - 行数口径（保守近似，旧 JSON 兼容）：统计 `assert ` 行数；
    - AST 口径（1.3 增强）：对 generated_test 做 ast.parse，统计
      非测试函数体中的 assert 语句总数（含 assert 后的消息分支），
      与行数口径一致时交叉验证"是否有 assert 被字符串拼接掩盖"。
    旧 JSON 无 generated_test 时返回 available=False，渲染时跳过该小节。
    """
    observed = 0
    assertion_counts: list[int] = []
    ast_assertion_counts: list[int] = []
    ast_parse_failed: list[str] = []
    for row in details:
        test_code = row.get("generated_test")
        if not isinstance(test_code, str) or not test_code.strip():
            continue
        observed += 1
        task_id = str(row.get("task_id", f"row_{observed}"))
        # 行数口径：`assert ` 开头的语句行（保守，与历史口径一致）
        assertion_counts.append(sum(1 for line in test_code.splitlines() if line.strip().startswith("assert ")))
        # AST 口径：统计所有 Assert 节点（包括嵌套在 if/for 等块内，
        # 以及带消息字符串的 assert——行数口径同样计入，二者可比对）
        try:
            tree = ast.parse(test_code)
            ast_assertion_counts.append(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.Assert)))
        except SyntaxError:
            # generated_test 语法不完整（LLM 生成损坏）时跳过 AST 口径，
            # 记录 task_id 供异味检测交叉引用
            ast_parse_failed.append(task_id)

    if not assertion_counts:
        return {"available": False, "observed_tasks": 0}
    avg = sum(assertion_counts) / len(assertion_counts)
    ast_avg = round(sum(ast_assertion_counts) / len(ast_assertion_counts), 2) if ast_assertion_counts else None
    return {
        "available": True,
        "observed_tasks": observed,
        "avg_assertions_per_task": round(avg, 2),
        "min_assertions": min(assertion_counts),
        "max_assertions": max(assertion_counts),
        "tasks_with_zero_assertions": sum(1 for value in assertion_counts if value == 0),
        # 1.3 AST 口径增强字段（旧 JSON 无 generated_test 时整个 proxy available=False，
        # 这些键不出现，渲染层不读取即兼容）
        "ast_avg_assertions": ast_avg,
        "ast_parse_failed_tasks": ast_parse_failed,
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


def _failure_root_cause_trend(details: list[dict[str, Any]]) -> dict[str, Any]:
    """5.3 失败根因时间趋势：追踪三类根因（llm_capability / dependency /
    framework）在任务序列中的占比变化。

    根因归属（保守启发，不依赖 LLM）：
    - llm_capability: LLM 能力类失败（ASSERTION/LOGIC/UNKNOWN 等，补丁应用
      成功但测试仍失败，或 LLM 格式/超时类失败）；
    - dependency: 依赖/环境类失败（IMPORT_ERROR，缺第三方依赖或模块路径
      错误，修复方向是装依赖而非改代码）；
    - framework: 框架/基础设施类失败（EXECUTION_TRACE_MISSING /
      MULTI_CANDIDATE_ALL_REJECTED / PATCH_VALIDATION_FAILED，执行器、
      多候选策略或安全守卫异常）。

    Args:
        details: benchmark details 列表（按任务顺序）。

    Returns:
        {"total_failed": 失败任务数,
         "root_cause_distribution": {llm_capability: n, dependency: n, framework: n},
         "root_cause_rates": {llm_capability: float, dependency: float, framework: float},
         "trend_by_first_third": {"first_third": {...}, "second_third": {...}, "third_third": {...}}}
        trend_by_first_third 把失败任务按顺序分三段，各段统计三类根因占比，
        用于判断"系统优化是否有效"（若 framework/dependency 占比随批次下降，
        说明基础设施与依赖处理在改善）。
    """
    failed_rows = [r for r in details if not r.get("passed")]
    total_failed = len(failed_rows)
    if total_failed == 0:
        return {"total_failed": 0, "root_cause_distribution": {}, "root_cause_rates": {}, "trend_by_first_third": {}}

    def _root_cause(row: dict[str, Any]) -> str:
        cat = str(row.get("error_category") or "unknown").lower()
        if cat in ("import_error",):
            return "dependency"
        if cat in ("execution_trace_missing", "multi_candidate_all_rejected", "patch_validation_failed"):
            return "framework"
        # 其余失败（assertion/logic/unknown/runtime/type/index/timeout 等）
        # 归为 LLM 能力类（系统修复逻辑未覆盖到，需 LLM 理解代码）
        return "llm_capability"

    dist: Counter = Counter()
    for row in failed_rows:
        dist[_root_cause(row)] += 1
    # 三类根因均给出（缺省 0），便于渲染层直接读 rates（避免 KeyError）
    rates = {k: round(dist.get(k, 0) / total_failed, 4) for k in ("llm_capability", "dependency", "framework")}
    # 时间趋势：把失败任务按顺序三等分（不足 3 段时按实际分段）
    third = max(1, total_failed // 3)
    segments = {
        "first_third": failed_rows[:third],
        "second_third": failed_rows[third:2 * third],
        "third_third": failed_rows[2 * third:],
    }
    trend: dict[str, dict[str, float]] = {}
    for seg_name, seg_rows in segments.items():
        if not seg_rows:
            continue
        seg_dist: Counter = Counter(_root_cause(r) for r in seg_rows)
        trend[seg_name] = {
            k: round(seg_dist.get(k, 0) / len(seg_rows), 4) for k in ("llm_capability", "dependency", "framework")
        }
    return {
        "total_failed": total_failed,
        "root_cause_distribution": {k: dist.get(k, 0) for k in ("llm_capability", "dependency", "framework")},
        "root_cause_rates": rates,
        "trend_by_first_third": trend,
    }


def _contamination_cross_analysis(details: list[dict[str, Any]]) -> dict[str, Any]:
    """5.3 失败分析 × 污染检测交叉：高污染风险任务是否具有更高修复成功率。

    2.1 改进联动：details[].contamination_risk_level（high/medium/low，由
    contamination_check.detect_contamination 产出）与 passed 交叉，验证
    "污染效应"是否真实存在——若 high 风险任务成功率显著高于 low 风险任务，
    提示系统确实在"背出"黄金补丁而非真正定位根因。

    Returns:
        {"available": bool,
         "by_risk_level": {"high": {tasks, passed, success_rate},
                            "medium": {...}, "low": {...}},
         "high_vs_low_success_delta": float | None}
        无 contamination_risk_level 字段时 available=False。
    """
    observed = 0
    by_level: dict[str, dict[str, Any]] = {}
    for row in details:
        level = row.get("contamination_risk_level")
        if not level:
            continue
        observed += 1
        stat = by_level.setdefault(str(level), {"tasks": 0, "passed": 0})
        stat["tasks"] += 1
        if row.get("passed"):
            stat["passed"] += 1
    if observed == 0:
        return {"available": False, "by_risk_level": {}}
    result: dict[str, Any] = {"available": True, "by_risk_level": {}}
    for level, stat in by_level.items():
        total = stat["tasks"]
        result["by_risk_level"][level] = {
            "tasks": total,
            "passed": stat["passed"],
            "success_rate": round(stat["passed"] / total, 4) if total else 0.0,
        }
    high_rate = result["by_risk_level"].get("high", {}).get("success_rate")
    low_rate = result["by_risk_level"].get("low", {}).get("success_rate")
    if high_rate is not None and low_rate is not None:
        result["high_vs_low_success_delta"] = round(high_rate - low_rate, 4)
    return result


def _rag_token_efficiency(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG Token 效率增益：对比启用/禁用 RAG 任务的 Token 消耗与迭代次数。

    2.3 改进：当前仅报告 Hit Rate/MRR，本函数从 details[].rag_enabled
    （或 rag_stats 非空推断）把任务分为"启用 RAG"与"未启用 RAG"两组，
    对比两组的平均 Token / 平均迭代 / 成功率，回答"RAG 检索是否值得其
    检索 + 提示注入的 Token 开销"。

    分组口径：
    - rag_stats 非空（任务内发生过检索）= 启用 RAG 组；
    - 其余 = 未启用 RAG 组（含 RAG 关闭时的历史任务）。
    - 两组任一为空时 available=False（无法对比）。

    Returns:
        {"available": bool, "rag_group": {tasks, avg_tokens, avg_iterations, success_rate},
         "no_rag_group": {...}, "token_delta_ratio": float,
         "iteration_delta": int}
    """
    rag_rows: list[dict[str, Any]] = []
    no_rag_rows: list[dict[str, Any]] = []
    for row in details:
        is_rag = bool(row.get("rag_stats")) or row.get("rag_enabled")
        (rag_rows if is_rag else no_rag_rows).append(row)
    if not rag_rows or not no_rag_rows:
        return {"available": False, "observed_rag_tasks": len(rag_rows), "observed_no_rag_tasks": len(no_rag_rows)}

    def _group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        avg_tokens = round(sum(float((r.get("token_usage") or {}).get("total_tokens", 0) or 0) for r in rows) / n, 2) if n else 0.0
        avg_iterations = round(sum(int(r.get("iterations", 0) or 0) for r in rows) / n, 2) if n else 0.0
        success_rate = round(sum(1 for r in rows if r.get("passed")) / n, 4) if n else 0.0
        return {"tasks": n, "avg_tokens": avg_tokens, "avg_iterations": avg_iterations, "success_rate": success_rate}

    rag_stat = _group_stats(rag_rows)
    no_rag_stat = _group_stats(no_rag_rows)
    token_delta_ratio = round(rag_stat["avg_tokens"] / no_rag_stat["avg_tokens"], 4) if no_rag_stat["avg_tokens"] else None
    iteration_delta = round(rag_stat["avg_iterations"] - no_rag_stat["avg_iterations"], 2)
    return {
        "available": True,
        "rag_group": rag_stat,
        "no_rag_group": no_rag_stat,
        "token_delta_ratio": token_delta_ratio,
        "iteration_delta": iteration_delta,
    }


def _rag_similarity_distribution(details: list[dict[str, Any]]) -> dict[str, Any]:
    """2.3 RAG 检索结果相关性分布：avg_max_similarity 的直方图分桶。

    2.3 改进：当前仅报告 Hit Rate 和 MRR，本函数把各检索记录的最高相似度
    按 0.1 步长分桶（0.0-0.1 ... 0.9-1.0），输出分布直方图，用于观察
    "检索结果是普遍低相关还是集中在高相关"，辅助判断检索库质量。

    Returns:
        {"available": bool, "histogram": {"0.0-0.1": n, ...},
         "total_retrievals": int, "avg_max_similarity": float | None}
    """
    bins = {f"{i * 0.1:.1f}-{(i + 1) * 0.1:.1f}": 0 for i in range(10)}
    total = 0
    sims: list[float] = []
    for row in details:
        for s in row.get("rag_stats") or []:
            ms = s.get("max_similarity")
            if ms is None:
                continue
            total += 1
            val = float(ms)
            sims.append(val)
            # 归一化到 0.0-1.0（相似度可能 >1，保守截断到 1.0）
            idx = min(int(val * 10), 9)
            bins[f"{idx * 0.1:.1f}-{(idx + 1) * 0.1:.1f}"] += 1
    if total == 0:
        return {"available": False, "histogram": {}, "total_retrievals": 0}
    return {
        "available": True,
        "histogram": {k: v for k, v in bins.items() if v > 0},
        "total_retrievals": total,
        "avg_max_similarity": round(sum(sims) / len(sims), 4) if sims else None,
    }


def _venv_cache_stats_snapshot() -> dict[str, Any] | None:
    """4.4 依赖缓存命中率统计：读取 ExecutorAgent venv 磁盘缓存的命中数据。

    缓存统计由 src/tools/dependency.py 维护（按依赖组合复用 venv），
    此处仅做只读快照，供分析报告输出缓存复用效率。导入失败或统计
    为空（尚无缓存事件）时返回 None，渲染时跳过章节，不崩溃。

    4.4 改进：额外附带缓存容量信息（总大小 + 是否超告警阈值），
    超限时输出清理建议（只监控不自动清理）。
    """
    try:
        from src.tools.dependency import check_venv_cache_size, get_venv_cache_stats
    except Exception:
        return None
    stats = get_venv_cache_stats()
    if stats.get("total", 0) == 0:
        # 尚无缓存事件时仍可提供容量监控（目录可能存在历史 venv）
        try:
            size = check_venv_cache_size()
            return {**size, "hits": 0, "creates": 0, "total": 0, "hit_rate": 0.0}
        except Exception:
            return None
    try:
        size = check_venv_cache_size()
        stats.update(size)
    except Exception:
        pass
    return stats


def _boundary_case_coverage(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.3 边界用例覆盖度：检测生成测试是否覆盖边界条件。

    边界条件清单（AST 保守口径，针对 generated_test 代码）：
    - 空/None 输入（None / 空字符串 / 空集合字面量）
    - 数值极值（int/float 字面量中出现 0、-1、-0.1、1.0、10**6、maxsize 量级）
    - 边界比较（测试体含 >=/<= 的数值边界比较语句）

    实现：对 generated_test 做 ast.parse，收集测试体中出现的"边界值"
    字面量与比较运算符类型，判定每个任务是否覆盖至少 1 类边界条件。
    旧 JSON 无 generated_test 时 available=False。

    Returns:
        {"available": bool, "observed_tasks": int,
         "boundary_types": {type: covered_task_count},
         "tasks_covering_any_boundary": int, "coverage_rate": float}
    """
    import ast as _ast

    observed = 0
    boundary_types: Counter = Counter()
    tasks_covering = 0
    for row in details:
        test_code = row.get("generated_test")
        if not isinstance(test_code, str) or not test_code.strip():
            continue
        observed += 1
        try:
            tree = _ast.parse(test_code)
        except SyntaxError:
            continue
        covered_types: set[str] = set()
        # 边界数值/字符串/None 字面量
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant):
                v = node.value
                if v is None:
                    covered_types.add("none")
                elif isinstance(v, str) and v == "":
                    covered_types.add("empty_string")
                elif (isinstance(v, int) and v in (0, -1, 1, 10**6)) or (isinstance(v, float) and v in (-0.1, 0.0, 1.0)):
                    covered_types.add("numeric_extreme")
            if isinstance(node, _ast.List) and not getattr(node, "elts", None):
                covered_types.add("empty_collection")
            if isinstance(node, _ast.Set) and not getattr(node, "elts", None):
                covered_types.add("empty_collection")
        # 边界比较运算符（>=/<=/==/!=）
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Compare):
                ops = {type(op).__name__ for op in node.ops}
                if "GtE" in ops or "LtE" in ops:
                    covered_types.add("comparison_boundary")
        for t in covered_types:
            boundary_types[t] += 1
        if covered_types:
            tasks_covering += 1

    if observed == 0:
        return {
            "available": False,
            "observed_tasks": 0,
            "boundary_types": {},
            "tasks_covering_any_boundary": 0,
            "coverage_rate": 0.0,
        }
    return {
        "available": True,
        "observed_tasks": observed,
        "boundary_types": dict(boundary_types),
        "tasks_covering_any_boundary": tasks_covering,
        "coverage_rate": round(tasks_covering / observed, 4),
    }


def _mutation_score_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.3 变异得分：收集 details[].mutation_score（0.0-1.0，由外部变异测试器产出）。

    说明：变异测试需执行大量扰动用例，成本高，不作为默认流水线环节；
    本函数仅做"已有 mutation_score 字段时的汇总"，无该字段时 available=False
    跳过章节，不阻断主流程。未来若接入 mutation 执行（如 mutmut），可在此
    直接消费逐任务的 mutation_score 值。

    Returns:
        {"available": bool, "observed_tasks": int, "avg_mutation_score": float,
         "high_score_tasks": int, "low_score_tasks": int}
    """
    observed = 0
    scores: list[float] = []
    for row in details:
        ms = row.get("mutation_score")
        if ms is None:
            continue
        try:
            scores.append(float(ms))
            observed += 1
        except (TypeError, ValueError):
            continue
    if observed == 0:
        return {"available": False, "observed_tasks": 0}
    avg = round(sum(scores) / len(scores), 4)
    high = sum(1 for s in scores if s >= 0.7)
    low = sum(1 for s in scores if s < 0.4)
    result = {
        "available": True,
        "observed_tasks": observed,
        "avg_mutation_score": avg,
        "high_score_tasks": high,
        "low_score_tasks": low,
    }
    # 1.2 改进：变异得分 × 断言强度交叉分析——验证"高变异得分任务是否同时
    # 具有较高 AST 断言强度"（两者应一致：断言越强，变异体越容易被杀死）
    cross_tasks = [
        (float(row.get("mutation_score")), _assertion_counts_from_row(row))
        for row in details
        if row.get("mutation_score") is not None
    ]
    if cross_tasks:
        high_ms = [
            asserts for ms, asserts in cross_tasks if ms >= 0.7 and asserts is not None
        ]
        low_ms = [asserts for ms, asserts in cross_tasks if ms < 0.4 and asserts is not None]
        result["mutation_assertion_cross"] = {
            "high_score_avg_assertions": round(sum(high_ms) / len(high_ms), 2) if high_ms else None,
            "low_score_avg_assertions": round(sum(low_ms) / len(low_ms), 2) if low_ms else None,
            "consistent": (
                (high_ms and low_ms)
                and round(sum(high_ms) / len(high_ms), 2) > round(sum(low_ms) / len(low_ms), 2)
            )
            if (high_ms or low_ms)
            else None,
        }
    return result


def _assertion_counts_from_row(row: dict[str, Any]) -> int | None:
    """单任务断言强度（AST 口径，generated_test 缺失/解析失败时返回 None）。

    供变异得分 × 断言强度交叉分析使用；与 _assertion_strength_proxy 同口径
    （AST 统计 Assert 节点数），但返回单任务值（None 表示无数据）。
    """
    test_code = row.get("generated_test")
    if not isinstance(test_code, str) or not test_code.strip():
        return None
    try:
        tree = ast.parse(test_code)
    except (SyntaxError, ValueError):
        return None
    return sum(1 for _ in ast.walk(tree) if isinstance(_, ast.Assert))


def _convergence_failure_modes(details: list[dict[str, Any]]) -> dict[str, Any]:
    """1.2 收敛失败模式归因：达到 MAX_ITERATIONS 仍未修复的任务，
    区分"无法定位根因"（诊断反复同义/空）vs "无法生成有效补丁"
    （补丁写盘成功但测试仍失败，或被守卫拒绝后反复重写同一补丁）。

    判定逻辑（保守启发，不依赖 LLM）：
    - 收集未通过任务中 iterations>=3（达到 MAX_ITERATIONS）的任务
    - 遍历 repair_history（若存在）提取各轮 patch_applied 标志与诊断文本
    - "无法生成有效补丁"：任一情形命中——
        情形A：补丁曾写盘成功（patch_applied=True）但测试仍未通过
               （定位到了根因但补丁本身不能解决问题，属补丁质量问题）
        情形B：补丁被安全守卫拒绝（patch_applied=False 且有 patch 记录）
    - "无法定位根因"：诊断文本反复同义（最近 2 轮 diagnosis 相同）且
        补丁从未写盘成功（说明 Debugger 反复给出相同结论，没有真正
        识别到问题所在）
    - 两者皆命中时归"无法生成有效补丁"（更具体，便于定位）
    """
    converged_failed = [
        r for r in details
        if not r.get("passed") and int(r.get("iterations", 0) or 0) >= 3
    ]
    root_cause_stuck = 0
    patch_stuck = 0
    tasks_stuck: list[str] = []
    for row in converged_failed:
        task_id = str(row.get("task_id", "unknown"))
        repair_history = row.get("repair_history") or []

        prev_diags: list[str] = []
        patch_ever_applied = False
        patch_ever_rejected = False
        if isinstance(repair_history, list):
            for h in repair_history:
                if not isinstance(h, dict):
                    continue
                d = str(h.get("diagnosis") or "").strip()
                if d:
                    prev_diags.append(d)
                if h.get("patch_applied"):
                    patch_ever_applied = True
                elif "patch" in h and not h.get("patch_applied", False):
                    patch_ever_rejected = True

        # 无法定位根因：诊断反复同义且从未写盘成功
        diag_stuck = False
        if len(prev_diags) >= 2 and prev_diags[-1] == prev_diags[-2]:
            diag_stuck = True
        if diag_stuck and not patch_ever_applied and not patch_ever_rejected:
            diag_stuck = True
        elif not (patch_ever_applied or patch_ever_rejected) and not prev_diags:
            # 无 repair_history 且未写盘 → 保守归无法定位根因
            diag_stuck = True

        # 无法生成有效补丁：写盘成功但未解决 或 被守卫拒绝
        patch_failed = patch_ever_applied or patch_ever_rejected

        mode = None
        if patch_failed:
            mode = "patch_generation_failed"
            patch_stuck += 1
        elif diag_stuck:
            mode = "root_cause_stuck"
            root_cause_stuck += 1

        if mode is not None:
            tasks_stuck.append(task_id)

    return {
        "total_converged_failed": len(converged_failed),
        "root_cause_stuck": root_cause_stuck,
        "patch_generation_failed": patch_stuck,
        "tasks": tasks_stuck,
        "available": len(converged_failed) > 0,
    }


def _execution_trace_summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    """3.2 执行轨迹汇总：收集 details[].execution_trace（executor 节点默认常开写入）。

    指标（保守可复算）：
    - observed_tasks: 携带非空 execution_trace 的任务数
    - total_executions: 所有任务的 executor 执行次数合计
    - avg_executions_per_task: 平均每次任务执行轮数（反映修复尝试次数）
    - pass_on_first_rate: 首轮执行即通过的任务占比
    - avg_reward_correctness: 各任务末轮 correctness 信号均值
    - avg_reward_efficiency: 各任务末轮 efficiency 信号均值
    - coverage_trend: 逐轮平均覆盖率趋势（首轮 vs 末轮，观察收敛方向）

    旧 JSON 无 execution_trace 字段时返回 available=False（渲染时跳过章节）。
    """
    observed = 0
    total_executions = 0
    pass_on_first = 0
    last_rew_correctness: list[float] = []
    last_rew_efficiency: list[float] = []
    first_covs: list[float] = []
    last_covs: list[float] = []
    for row in details:
        trace = row.get("execution_trace")
        if not isinstance(trace, list) or not trace:
            continue
        observed += 1
        total_executions += len(trace)
        # 首轮（iteration=0 或 首条记录）是否通过
        first_entry = trace[0]
        if isinstance(first_entry, dict) and first_entry.get("passed"):
            pass_on_first += 1
        # 末轮奖励信号
        last = trace[-1] if isinstance(trace[-1], dict) else {}
        rewards = last.get("reward_signals") or {}
        if isinstance(rewards, dict):
            if "correctness" in rewards:
                last_rew_correctness.append(float(rewards["correctness"]))
            if "efficiency" in rewards:
                last_rew_efficiency.append(float(rewards["efficiency"]))
        # 首末轮覆盖率
        if isinstance(first_entry, dict) and first_entry.get("coverage") is not None:
            first_covs.append(float(first_entry["coverage"]))
        if "coverage" in last:
            last_covs.append(float(last["coverage"]))
    if observed == 0:
        return {"available": False, "observed_tasks": 0}
    avg_first_cov = round(sum(first_covs) / len(first_covs), 2) if first_covs else None
    avg_last_cov = round(sum(last_covs) / len(last_covs), 2) if last_covs else None
    return {
        "available": True,
        "observed_tasks": observed,
        "total_executions": total_executions,
        "avg_executions_per_task": round(total_executions / observed, 2),
        "pass_on_first_rate": round(pass_on_first / observed, 4),
        "avg_last_reward_correctness": (
            round(sum(last_rew_correctness) / len(last_rew_correctness), 3) if last_rew_correctness else None
        ),
        "avg_last_reward_efficiency": (
            round(sum(last_rew_efficiency) / len(last_rew_efficiency), 3) if last_rew_efficiency else None
        ),
        "coverage_trend": {
            "first_round_avg": avg_first_cov,
            "last_round_avg": avg_last_cov,
            "delta": round((avg_last_cov or 0.0) - (avg_first_cov or 0.0), 2)
            if avg_first_cov is not None and avg_last_cov is not None
            else None,
        },
    }


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
            "best_marginal_round 标记\"第几轮修复最划算\"（边际收益最高的轮次），"
            "用于回答\"第几轮修复的边际收益最高\"。"
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
        lines.append("| 基线 | 观测任务 | Assertion Roulette | Magic Number | 断言弱化 | 平凡测试 | Eager Test | 缺乏内聚 | 异味密度 | 含异味任务 |")
        lines.append("|------|---------|-------------------|--------------|---------|---------|----------|---------|--------|----------|")
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
        strategy_rows = [
            (b, s)
            for b, s in smell_rows
            if s.get("smell_counts_by_strategy")
        ]
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
        (b, m["rag_token_efficiency"])
        for b, m in per.items()
        if m.get("rag_token_efficiency", {}).get("available")
    ]
    if rag_token_rows:
        lines.append("## RAG Token 效率增益（2.3）")
        lines.append("")
        lines.append("| 基线 | RAG组(任务数) | RAG组平均Token | RAG组成功率 | 无RAG组(任务数) | 无RAG组平均Token | 无RAG组成功率 | Token比率 | 迭代差 |")
        lines.append("|------|--------------|---------------|-----------|----------------|-----------------|-------------|----------|--------|")
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
            "结合成功率差异判断 RAG 的\"性价比\"——若成功率提升足以抵消 Token 开销则值得，"
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
                f"| {baseline} | {rs.get('total_retrievals', 0)} "
                f"| {rs.get('avg_max_similarity')} | {hist_text} |"
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
                "> 解读：若\"一致\"为真，说明断言强度越高的测试杀死的变异体越多"
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
        lines.append("达到 MAX_ITERATIONS（默认 3）仍未修复的任务，区分\"无法定位根因\"与\"无法生成有效补丁\"。")
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
        lines.append("| 基线 | 观测任务 | 总执行次数 | 平均轮数 | 首轮即通过率 | 末轮 correctness | 末轮 efficiency | 首/末轮覆盖率 |")
        lines.append("|------|---------|----------|--------|------------|----------------|----------------|------------|")
        for baseline, tstat in trace_rows:
            ct = tstat.get("coverage_trend") or {}
            cov_text = f"{ct.get('first_round_avg')} → {ct.get('last_round_avg')}" if ct.get("delta") is not None else "N/A"
            lines.append(
                f"| {baseline} | {tstat.get('observed_tasks', 0)} | {tstat.get('total_executions', 0)} "
                f"| {tstat.get('avg_executions_per_task', 0)} | {tstat.get('pass_on_first_rate', 0.0)} "
                f"| {tstat.get('avg_last_reward_correctness', 0.0)} | {tstat.get('avg_last_reward_efficiency', 0.0)} "
                f"| {cov_text} |"
            )
        lines.append("")
        lines.append(
            "> 解读：本轮次即通过率反映系统\"一次做对\"能力；末轮 correctness 均值即\"收敛到通过\"的成功率；"
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
        lines.append("| 基线 | 失败任务 | LLM能力 | 依赖/环境 | 框架/基础设施 | 第一段LLM能力 | 第二段LLM能力 | 第三段LLM能力 |")
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
            "> 解读：若\"成功率差（高-低）\"为显著正值（≥0.2），提示高污染风险任务"
            "成功率异常偏高——系统可能在\"背出\"黄金补丁而非真正修复，论文中应"
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
                    f"| 首轮即通过率差 | {first_delta:+.4f} "
                    f"| 正值 = 多智能体协作首轮成功率更高（一次做对能力领先） |"
                )
            if at1_delta is not None:
                lines.append(
                    f"| 第1轮累计通过率差 | {at1_delta:+.4f} "
                    f"| 正值 = 协作机制的增益来自'一次做对'而非'多轮调试追平' |"
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
