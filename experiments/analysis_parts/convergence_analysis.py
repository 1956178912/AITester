"""修复收敛 / 质量代理 / 测试异味 / 跨基线对比主题函数（从 analyze_results.py 拆分，0.7 债务项 1.6）。

所有函数均为纯函数，只消费 details[] 与 per_baseline 字典；
模块级依赖：ast（AST 静态分析）、Counter（分布统计）、_assertion_strength_proxy / _assertion_counts_from_row / _smell_task_has_smell（组内共享，同文件内直接引用）。
"""

from __future__ import annotations

import ast
from collections import Counter
from typing import Any


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
            node
            for node in _ast_smell.walk(tree)
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
        stat["smell_density"] = (
            round(stat["tasks_with_smells"] / stat["observed_tasks"], 4) if stat["observed_tasks"] else 0.0
        )
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
    baselines_with_curve = [bl for bl, m in per_baseline.items() if m.get("repair_convergence_curve", {}).get("rounds")]
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
        "second_third": failed_rows[third : 2 * third],
        "third_third": failed_rows[2 * third :],
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
        high_ms = [asserts for ms, asserts in cross_tasks if ms >= 0.7 and asserts is not None]
        low_ms = [asserts for ms, asserts in cross_tasks if ms < 0.4 and asserts is not None]
        result["mutation_assertion_cross"] = {
            "high_score_avg_assertions": round(sum(high_ms) / len(high_ms), 2) if high_ms else None,
            "low_score_avg_assertions": round(sum(low_ms) / len(low_ms), 2) if low_ms else None,
            "consistent": (
                (high_ms and low_ms) and round(sum(high_ms) / len(high_ms), 2) > round(sum(low_ms) / len(low_ms), 2)
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
    converged_failed = [r for r in details if not r.get("passed") and int(r.get("iterations", 0) or 0) >= 3]
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
                elif (isinstance(v, int) and v in (0, -1, 1, 10**6)) or (
                    isinstance(v, float) and v in (-0.1, 0.0, 1.0)
                ):
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
