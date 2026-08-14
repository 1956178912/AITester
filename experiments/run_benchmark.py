"""
批量实验脚本：对数据集运行 AITester 及多基线对比，记录完整结果。

支持的基线方法：
    - aitester     : 完整多智能体系统（Planner+Generator+Executor+Debugger）
    - plain_llm    : 纯 LLM 基线（无 Planner、无修复循环，仅一次调用）
    - single_agent : 单智能体基线（所有功能合并为一个 LLM 调用）

支持的数据集（通过 dataset 参数指定）：
    - examples     : 内置示例数据集（InMemoryDataset，无需下载）
    - swe_bench    : SWE-bench 数据集（需提前下载到 ~/.cache/aitester/swe_bench/）
    - defects4j_py : Defects4J-Python 数据集（需提前下载）
    - synthetic    : 合成数据集（本地生成，支持自定义规模，无需外部下载）

使用方式：
    # 仅运行内置示例数据集
    python experiments/run_benchmark.py --dataset examples --baselines aitester plain_llm single_agent

    # 运行 SWE-bench lite 子集
    python experiments/run_benchmark.py --dataset swe_bench --subset lite --baselines aitester

    # 保存结果到指定目录
    python experiments/run_benchmark.py --output-dir ./my_results --verbose
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import tempfile
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from src.dataset_loader import (
    BaseDatasetLoader,
    BenchmarkTask,
    InMemoryDataset,
    load_dataset,
)
from src.tools.code_analyzer import parse_function_nodes
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD, ENABLE_PLANNER, ENABLE_DEBUGGER

logger = logging.getLogger(__name__)


# ─── 基线方法实现 ─────────────────────────────────────────────────────────────


def run_aitester_baseline(
    state: AITesterState,
) -> Dict[str, Any]:
    """
    完整 AITester 基线：Planner → Generator → Executor → (Debugger → PatchApplier) × N。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典，包含 test_passed, coverage_report 等字段。
    """
    graph = build_workflow()
    return graph.invoke(state)


def run_plain_llm_baseline(
    state: AITesterState,
) -> Dict[str, Any]:
    """
    纯 LLM 基线（Baseline B）：不启用 Planner，不进行修复循环。
    Generator 直接基于目标代码生成测试，Executor 执行一次，无 Debugger。

    模拟"无规划、无自修复"的简单 LLM 调用场景。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典。
    """
    # 临时关闭 Planner 和 Debugger，重新加载 workflow 模块获取新图
    # 注意：通过全局变量修改后 reload 是关键，否则已有的 graph 实例不会变化
    import importlib
    import src.graph.workflow as wf_module
    global ENABLE_PLANNER, ENABLE_DEBUGGER
    old_planner, old_debugger = ENABLE_PLANNER, ENABLE_DEBUGGER
    try:
        ENABLE_PLANNER = False
        ENABLE_DEBUGGER = False
        importlib.reload(wf_module)
        graph = wf_module.build_workflow()
        return graph.invoke(state)
    finally:
        ENABLE_PLANNER, ENABLE_DEBUGGER = old_planner, old_debugger
        importlib.reload(wf_module)  # 恢复模块，避免影响后续测试


def run_single_agent_baseline(
    state: AITesterState,
) -> Dict[str, Any]:
    """
    单智能体基线（Baseline C）：将 Planner + Generator + Debugger 功能合并为一次 LLM 调用。
    无工作流，只有一个大 Prompt 让 LLM 直接输出测试代码，并允许一轮修复。

    模拟"单一 LLM 调用"的对比实验场景。

    Args:
        state: 初始工作流状态。

    Returns:
        最终状态字典（test_passed, coverage_report 等）。
    """
    from src.agents.generator import GeneratorAgent
    from src.agents.executor import ExecutorAgent

    agent = GeneratorAgent()
    executor = ExecutorAgent(timeout=int(os.getenv("EXECUTION_TIMEOUT", "30")))

    # 单次 LLM 调用：要求直接生成测试并自行判断是否需要修复
    query = (
        f"你是一个软件测试专家。请分析以下代码并直接生成完整的 pytest 测试代码。\n\n"
        f"目标代码：\n```python\n{state['target_code']}\n```\n\n"
        f"要求：\n"
        f"1. 找出代码中可能存在的 bug，编写能捕获这些 bug 的测试用例\n"
        f"2. 同时生成一个简化版的修复补丁（如果需要）\n"
        f"3. 只输出 pytest 测试代码（用 ```python 包裹），不要输出其他内容"
    )

    test_code = agent._extract_python_code(agent._call_llm(query))
    state["generated_test"] = test_code

    # 执行测试
    result = executor.execute(
        test_code=test_code,
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )

    state["test_passed"] = result["passed"]
    state["test_output"] = result["output"]
    state["coverage_report"] = result["coverage"]
    state["failed_cases"] = result["failed_cases"]
    state["iteration"] = 0

    # 若测试失败，尝试一轮 LLM 修复（单智能体只能修复一次）
    if not result["passed"] and result["failed_cases"]:
        fix_query = (
            f"测试失败了，请修复目标代码中的 bug。只输出修复后的完整代码（```python 包裹）。\n\n"
            f"原始代码：\n```python\n{state['target_code']}\n```\n\n"
            f"测试输出：\n{result['output'][:1000]}"
        )
        fix_raw = agent._call_llm(fix_query)
        fix_code = agent._extract_python_code(fix_raw)
        if fix_code:
            from src.tools.patch_applier import apply_patch_to_code
            new_code, applied = apply_patch_to_code(state["target_code"], fix_code)
            if applied:
                state["target_code"] = new_code
                # 写回文件并重试
                with open(state["target_file"], "w", encoding="utf-8") as f:
                    f.write(new_code)
                retry_result = executor.execute(
                    test_code=test_code,
                    target_file=state["target_file"],
                    target_function=state.get("target_function"),
                )
                state["test_passed"] = retry_result["passed"]
                state["test_output"] = retry_result["output"]
                state["coverage_report"] = retry_result["coverage"]
                state["failed_cases"] = retry_result["failed_cases"]
                state["iteration"] = 1

    return state


# 基线方法注册表
BASELINE_REGISTRY: Dict[str, callable] = {
    "aitester": run_aitester_baseline,
    "plain_llm": run_plain_llm_baseline,
    "single_agent": run_single_agent_baseline,
}


# ─── 单任务运行函数 ────────────────────────────────────────────────────────────


def run_single_task(
    task: BenchmarkTask,
    baselines: List[str],
    output_dir: str,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    对单个 BenchmarkTask 运行所有指定的基线方法，返回汇总结果。

    Args:
        task: 基准测试任务。
        baselines: 要运行的基线方法列表。
        output_dir: 结果输出目录。
        verbose: 是否输出详细日志。

    Returns:
        包含各基线结果的字典。
    """
    # 创建临时目录存放任务相关文件（避免修改原始文件）
    tmp_dir = tempfile.mkdtemp(prefix=f"aitester_{task.task_id}_")
    try:
        # 写入 instance_code 到临时文件
        # 从 repo_name 推导模块文件名（如 "examples/calculator" → "calculator.py"）
        module_name = task.repo_name.split("/")[-1] if "/" in task.repo_name else task.task_id.split("__")[-1]
        instance_file = os.path.join(tmp_dir, f"{module_name}.py")
        with open(instance_file, "w", encoding="utf-8") as f:
            f.write(task.instance_code)

        # 初始化工作流状态
        state: AITesterState = {
            "task_uuid": f"{task.task_id}_{{baseline}}",
            "target_file": instance_file,
            "target_function": None,
            "module_name": module_name,
            "target_code": task.instance_code,
            "test_plan": None,
            "generated_test": None,
            "test_passed": None,
            "test_output": None,
            "coverage_report": None,
            "failed_cases": None,
            "diagnosis": None,
            "error_category": None,
            "patch": None,
            "iteration": 0,
            "max_iterations": MAX_ITERATIONS,
            "repair_history": [],
        }

        results: Dict[str, Dict[str, Any]] = {}
        for baseline in baselines:
            start_time = time.time()
            state["task_uuid"] = f"{task.task_id}_{baseline}_{int(start_time)}"

            if verbose:
                logger.info("  [%s] 运行 %s ...", baseline, task.task_id)

            try:
                final_state = BASELINE_REGISTRY[baseline](state)
                elapsed = time.time() - start_time

                results[baseline] = {
                    "task_id": task.task_id,
                    "repo": task.repo_name,
                    "passed": final_state.get("test_passed", False),
                    "coverage": final_state.get("coverage_report") or 0.0,
                    "iterations": final_state.get("iteration", 0),
                    "diagnosis": final_state.get("diagnosis", ""),
                    "error_category": final_state.get("error_category", ""),
                    "elapsed_seconds": round(elapsed, 2),
                    "task_metadata": task.metadata,
                }

                status = "✓ PASS" if final_state.get("test_passed") else "✗ FAIL"
                logger.info(
                    "    [%s] %s: %s (%.1fs, coverage=%.1f%%)",
                    baseline, task.task_id, status, elapsed,
                    final_state.get("coverage_report", 0.0),
                )
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("    [%s] %s 执行失败: %s", baseline, task.task_id, e)
                results[baseline] = {
                    "task_id": task.task_id,
                    "repo": task.repo_name,
                    "passed": False,
                    "coverage": 0.0,
                    "iterations": 0,
                    "diagnosis": f"执行异常: {e}",
                    "error_category": "error",
                    "elapsed_seconds": round(elapsed, 2),
                    "task_metadata": task.metadata,
                }

        return results

    finally:
        # 清理临时目录，确保不留下被测代码副本（可能含 API Key 敏感信息）
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── 主基准测试函数 ────────────────────────────────────────────────────────────


def run_benchmark(
    dataset_name: str = "examples",
    subset: Optional[str] = None,
    baselines: Optional[List[str]] = None,
    output_dir: str = "experiments/results",
    verbose: bool = False,
    task_limit: Optional[int] = None,
    task_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    批量运行基准测试，支持多基线方法对比和消融实验。

    Args:
        dataset_name: 数据集名称（"examples"/"swe_bench"/"defects4j_py"）。
        subset: 数据子集（如 "lite"/"mini"/"full"）。
        baselines: 要运行的基线方法列表，默认为 ["aitester"]。
        output_dir: 结果输出目录。
        verbose: 是否输出详细日志。
        task_limit: 限制运行任务数量（用于快速验证，None 表示全部）。
        task_count: 合成数据集任务数量（--dataset synthetic 时有效，默认 60）。

    Returns:
        汇总结果字典，包含各基线的统计指标和详细结果。
    """
    # 默认基线
    if baselines is None:
        baselines = ["aitester"]

    # 验证基线名称
    unknown = [b for b in baselines if b not in BASELINE_REGISTRY]
    if unknown:
        raise ValueError(f"不支持的基线方法: {unknown}，支持: {list(BASELINE_REGISTRY.keys())}")

    # 加载数据集
    logger.info("加载数据集: %s (subset=%s)", dataset_name, subset)
    
    # synthetic 数据集：本地生成，支持自定义规模
    if dataset_name in ("synthetic", "synth"):
        tc = task_count or 60
        logger.info("生成合成数据集：%d 个任务", tc)
        from src.synthetic_dataset import SyntheticDataset
        dataset = SyntheticDataset(task_count=tc, seed=42)
    else:
        try:
            dataset = load_dataset(dataset_name, subset=subset)
        except Exception as e:
            logger.error("数据集加载失败: %s", e)
            raise

    if dataset.size == 0:
        logger.warning("数据集为空，尝试使用内置示例数据集")
        dataset = InMemoryDataset.create_with_samples()

    # 任务限制
    tasks = dataset.tasks[:task_limit] if task_limit else dataset.tasks
    logger.info("待运行任务数: %d，基线: %s", len(tasks), baselines)

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    all_results: Dict[str, List[Dict[str, Any]]] = {bl: [] for bl in baselines}
    total_time = 0.0

    for i, task in enumerate(tasks, start=1):
        logger.info("[%d/%d] 处理任务: %s", i, len(tasks), task.task_id)
        task_results = run_single_task(task, baselines, output_dir, verbose=verbose)

        for baseline, result in task_results.items():
            all_results[baseline].append(result)

        # 打印当前进度
        elapsed_this = sum(r["elapsed_seconds"] for r in task_results.values())
        total_time += elapsed_this
        logger.info("  本轮耗时: %.1fs（累计 %.1fs）", elapsed_this, total_time)

    # 生成汇总统计
    summary = {
        "timestamp": datetime.now().isoformat(),
        "dataset": dataset_name,
        "subset": subset,
        "total_tasks": len(tasks),
        "baselines": baselines,
        "enable_planner": ENABLE_PLANNER,
        "enable_debugger": ENABLE_DEBUGGER,
        "enable_rag": False,  # RAG 在此处不启用（实验可复现性）
        "results": {},
    }

    for baseline in baselines:
        bl_results = all_results[baseline]
        passed = sum(1 for r in bl_results if r["passed"])
        total = len(bl_results)
        avg_coverage = sum(r.get("coverage", 0) for r in bl_results) / total if total > 0 else 0
        avg_iterations = sum(r["iterations"] for r in bl_results) / total if total > 0 else 0
        avg_time = sum(r["elapsed_seconds"] for r in bl_results) / total if total > 0 else 0

        summary["results"][baseline] = {
            "total_functions": total,
            "passed_count": passed,
            "failure_count": total - passed,
            "success_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "avg_coverage": round(avg_coverage, 1),
            "avg_iterations": round(avg_iterations, 2),
            "avg_elapsed_seconds": round(avg_time, 2),
            "total_time": round(sum(r["elapsed_seconds"] for r in bl_results), 2),
            "details": bl_results,
        }

    # 保存结果
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(
        output_dir,
        f"benchmark_{dataset_name}_{timestamp_str}.json",
    )
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("基准测试完成，结果已保存至: %s", output_file)
    logger.info("汇总：总耗时=%.1fs", total_time)
    for baseline in baselines:
        bl = summary["results"][baseline]
        logger.info(
            "  [%s] 成功率=%.1f%%, 平均覆盖率=%.1f%%, 平均迭代=%.1f",
            baseline, bl["success_rate"], bl["avg_coverage"], bl["avg_iterations"],
        )

    return summary


if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--dataset", "-d", default="examples", help="数据集名称 (examples/swe_bench/defects4j_py)")
    @click.option("--subset", "-s", default=None, help="数据子集 (lite/mini/full)")
    @click.option("--baselines", "-b", default="aitester,plain_llm,single_agent",
                  help="基线方法列表（逗号分隔），默认: aitester,plain_llm,single_agent")
    @click.option("--output-dir", "-o", default="experiments/results", help="结果输出目录")
    @click.option("--verbose", "-v", is_flag=True, help="详细日志输出")
    @click.option("--task-count", "-c", default=None, type=int,
                  help="合成数据集任务数量（--dataset synthetic 时有效，默认 60）")
    @click.option("--task-limit", "-n", default=None, type=int, help="限制运行任务数量（快速验证）")
    def cli(dataset, subset, baselines, output_dir, verbose, task_limit, task_count):
        """AITester 基准测试工具"""
        bl_list = [b.strip() for b in baselines.split(",") if b.strip()]
        summary = run_benchmark(
            dataset_name=dataset,
            subset=subset,
            baselines=bl_list,
            output_dir=output_dir,
            verbose=verbose,
            task_limit=task_limit,
            task_count=task_count,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    cli()
