"""
AITester CLI 入口：使用 click 提供命令行接口。
"""

from __future__ import annotations

import os
import sys
import click
from typing import Optional

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD


@click.group()
def cli() -> None:
    """AITester - 多智能体自动化测试与自修复系统"""
    pass


@cli.command()
@click.argument("target_file", type=click.Path(exists=True))
@click.option("--func", "-f", default=None, help="指定被测函数名")
@click.option("--max-iterations", default=MAX_ITERATIONS, help="最大修复迭代次数")
@click.option("--coverage-threshold", default=COVERAGE_THRESHOLD, help="覆盖率阈值")
def run(target_file: str, func: Optional[str], max_iterations: int, coverage_threshold: float) -> None:
    """
    运行单个测试任务。

    TARGET_FILE: 被测 Python 文件路径。
    """
    # 读取目标代码
    with open(target_file, "r", encoding="utf-8") as f:
        target_code = f.read()

    # 初始化状态
    state: AITesterState = {
        "task_uuid": "local_run",
        "target_file": target_file,
        "target_function": func,
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
        "max_iterations": max_iterations,
        "repair_history": [],
    }

    # 构建并运行工作流
    graph = build_workflow()
    final_state = graph.invoke(state)

    # 输出结果
    click.echo(f"\n{'='*50}")
    click.echo(f"任务完成：{target_file}")
    if func:
        click.echo(f"被测函数：{func}")
    click.echo(f"测试通过：{final_state.get('test_passed', 'N/A')}")
    if final_state.get("coverage_report"):
        click.echo(f"覆盖率：{final_state['coverage_report']:.1f}%")
    click.echo(f"修复迭代：{final_state.get('iteration', 0)}/{max_iterations}")
    click.echo(f"{'='*50}")

    if final_state.get("test_passed"):
        click.echo("\n✓ 测试全部通过！")
    else:
        click.echo("\n✗ 测试未通过，已达到最大迭代次数。")
        if final_state.get("diagnosis"):
            click.echo(f"\n根因诊断：{final_state['diagnosis']}")


@cli.command()
def list_examples() -> None:
    """列出 examples 目录下的示例文件"""
    examples_dir = os.path.join(os.path.dirname(__file__), "examples")
    if os.path.exists(examples_dir):
        for f in sorted(os.listdir(examples_dir)):
            if f.endswith(".py"):
                click.echo(f"  {f}")
    else:
        click.echo("examples 目录不存在")


if __name__ == "__main__":
    cli()
