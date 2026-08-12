"""
批量实验脚本：对 examples 目录下的所有示例文件运行 AITester 并记录结果。
"""

from __future__ import annotations

import click
import os
import json
import time
from datetime import datetime
from typing import Any, Dict, List

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from src.tools.code_analyzer import parse_function_nodes
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD


def run_benchmark(examples_dir: str = "examples", output_dir: str = "experiments/results") -> Dict[str, Any]:
    """
    批量运行基准测试。

    Args:
        examples_dir: 示例代码目录。
        output_dir: 结果输出目录。

    Returns:
        汇总结果字典。
    """
    os.makedirs(output_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []
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

        click.echo(f"\n正在处理：{filename}（函数：{func_names}）")

        for func_name in func_names:
            start_time = time.time()

            state: AITesterState = {
                "task_uuid": f"{filename}_{func_name}_{int(start_time)}",
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
                "patch": None,
                "iteration": 0,
                "max_iterations": MAX_ITERATIONS,
                "repair_history": [],
            }

            graph = build_workflow()
            final_state = graph.invoke(state)

            elapsed = time.time() - start_time
            total_time += elapsed

            results.append({
                "file": filename,
                "function": func_name,
                "passed": final_state.get("test_passed", False),
                "coverage": final_state.get("coverage_report"),
                "iterations": final_state.get("iteration", 0),
                "diagnosis": final_state.get("diagnosis"),
                "elapsed_seconds": round(elapsed, 2),
            })

            status = "✓ PASS" if final_state.get("test_passed") else "✗ FAIL"
            click.echo(f"  {func_name}: {status} ({elapsed:.1f}s)")

    # 保存汇总结果
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_files": len(results),
        "passed_count": sum(1 for r in results if r["passed"]),
        "failed_count": sum(1 for r in results if not r["passed"]),
        "avg_coverage": sum(r.get("coverage", 0) for r in results) / len(results) if results else 0,
        "total_time": round(total_time, 2),
        "results": results,
    }

    output_file = os.path.join(output_dir, f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    click.echo(f"\n基准测试完成，结果已保存至：{output_file}")
    click.echo(f"  总计：{summary['total_files']} 个函数")
    click.echo(f"  通过：{summary['passed_count']}  |  失败：{summary['failed_count']}")
    click.echo(f"  平均覆盖率：{summary['avg_coverage']:.1f}%")
    click.echo(f"  总耗时：{summary['total_time']:.1f}s")

    return summary


if __name__ == "__main__":

    run_benchmark()
