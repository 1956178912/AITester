"""
批量实验脚本：对 examples 目录下的所有示例文件运行 AITester 并记录结果。
支持多基线方法对比和消融实验。
"""

from __future__ import annotations

import os
import json
import time
import logging
from datetime import datetime
from typing import Any, Dict, List

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from src.tools.code_analyzer import parse_function_nodes
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD

logger = logging.getLogger(__name__)


def run_benchmark(
    examples_dir: str = "examples",
    output_dir: str = "experiments/results",
    baselines: List[str] = None,
) -> Dict[str, Any]:
    """
    批量运行基准测试，支持多基线方法对比。

    Args:
        examples_dir: 示例代码目录。
        output_dir: 结果输出目录。
        baselines: 要运行的基线方法列表，默认为 ["aitester", "direct_llm", "single_agent"]。

    Returns:
        汇总结果字典。
    """
    if baselines is None:
        baselines = ["aitester", "direct_llm", "single_agent"]

    os.makedirs(output_dir, exist_ok=True)
    all_results: Dict[str, List[Dict[str, Any]]] = {bl: [] for bl in baselines}
    total_time = 0.0

    # 遍历所有示例文件
    for filename in sorted(os.listdir(examples_dir)):
        if not filename.endswith(".py") or filename.startswith("__"):
            continue

        filepath = os.path.join(examples_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            target_code = f.read()

        # 提取所有函数名
        functions = parse_function_nodes(target_code)
        func_names = [fn["name"] for fn in functions]
        logger.info("正在处理：%s（函数：%s）", filename, func_names)

        for func_name in func_names:
            for baseline in baselines:
                start_time = time.time()

                state: AITesterState = {
                    "task_uuid": f"{filename}_{func_name}_{baseline}_{int(start_time)}",
                    "target_file": filepath,
                    "target_function": func_name,
                    "target_code": target_code,
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

                graph = build_workflow()
                final_state = graph.invoke(state)

                elapsed = time.time() - start_time
                total_time += elapsed

                all_results[baseline].append({
                    "file": filename,
                    "function": func_name,
                    "passed": final_state.get("test_passed", False),
                    "coverage": final_state.get("coverage_report"),
                    "iterations": final_state.get("iteration", 0),
                    "diagnosis": final_state.get("diagnosis"),
                    "error_category": final_state.get("error_category"),
                    "elapsed_seconds": round(elapsed, 2),
                })

                status = "✓ PASS" if final_state.get("test_passed") else "✗ FAIL"
                logger.info("  [%s] %s.%s: %s (%.1fs)", baseline, filename, func_name, status, elapsed)

    # 生成汇总统计
    summary = {
        "timestamp": datetime.now().isoformat(),
        "baselines": baselines,
        "total_files": len(list(os.listdir(examples_dir))),
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
    output_file = os.path.join(output_dir, f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("基准测试完成，结果已保存至：%s", output_file)
    logger.info("汇总：总耗时=%.1fs", total_time)
    for baseline in baselines:
        bl = summary["results"][baseline]
        logger.info("  [%s] 成功率=%.1f%%, 平均覆盖率=%.1f%%, 平均迭代=%.1f",
                     baseline, bl["success_rate"], bl["avg_coverage"], bl["avg_iterations"])

    return summary


if __name__ == "__main__":
    run_benchmark()
