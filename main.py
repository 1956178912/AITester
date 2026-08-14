"""
AITester CLI 入口模块：提供命令行接口，调用 LangGraph 工作流完成测试生成与修复。

使用方式：
    python main.py run examples/calculator.py --func divide
    python main.py list-examples
"""

from __future__ import annotations

import logging
import os
import sys
import click
from typing import Optional

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD

# 配置模块级日志：INFO 级别输出到控制台，DEBUG 级别输出到 aitester.log 文件
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("aitester.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """AITester - 多智能体自动化测试与自修复系统"""
    pass


@cli.command()
@click.argument("target_file", type=click.Path(exists=True))
@click.option("--func", "-f", default=None, help="指定被测函数名，不指定则测试全部函数")
@click.option("--max-iterations", default=MAX_ITERATIONS, help=f"最大修复迭代次数，默认 {MAX_ITERATIONS}")
@click.option("--coverage-threshold", default=COVERAGE_THRESHOLD, help=f"覆盖率阈值百分比，默认 {COVERAGE_THRESHOLD}")
def run(target_file: str, func: Optional[str], max_iterations: int, coverage_threshold: float) -> None:
    """
    运行单个测试任务。

    TARGET_FILE: 被测 Python 文件路径（必须存在）。

    流程：
    1. 读取目标代码
    2. 初始化工作流状态
    3. 运行多智能体工作流（Planner → Generator → Executor → Debugger → PatchApplier）
    4. 输出执行结果摘要
    """
    logger.info("开始测试任务：file=%s, func=%s", target_file, func)

    # 读取被测代码文件内容
    with open(target_file, "r", encoding="utf-8") as f:
        target_code = f.read()

    # 初始化工作流状态：所有字段均为 None，由工作流逐步填充
    state: AITesterState = {
        # 任务唯一标识，便于日志追踪
        "task_uuid": f"{os.path.basename(target_file)}_{func or 'all'}_{int(__import__('time').time())}",
        "target_file": target_file,
        "target_function": func,
        "module_name": os.path.splitext(os.path.basename(target_file))[0],
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
        "max_iterations": max_iterations,
        "repair_history": [],
    }

    # 构建并运行 LangGraph 工作流
    graph = build_workflow()
    final_state = graph.invoke(state)

    # 输出结果摘要到控制台
    click.echo(f"\n{'='*50}")
    click.echo(f"任务完成：{target_file}")
    if func:
        click.echo(f"被测函数：{func}")
    click.echo(f"测试通过：{final_state.get('test_passed', 'N/A')}")
    if final_state.get("coverage_report"):
        click.echo(f"覆盖率：{final_state['coverage_report']:.1f}%")
    click.echo(f"修复迭代：{final_state.get('iteration', 0)}/{max_iterations}")
    click.echo(f"{'='*50}")

    # 根据测试结果输出不同提示
    if final_state.get("test_passed"):
        click.echo("\n✓ 测试全部通过！")
    else:
        click.echo("\n✗ 测试未通过，已达到最大迭代次数。")
        if final_state.get("diagnosis"):
            click.echo(f"\n根因诊断：{final_state['diagnosis']}")
        if final_state.get("error_category"):
            click.echo(f"错误类型：{final_state['error_category']}")

    logger.info("任务完成，结果已输出到控制台和 aitester.log")


@cli.command()
def list_examples() -> None:
    """列出 examples 目录下的所有示例 Python 文件，供用户选择测试对象。"""
    examples_dir = os.path.join(os.path.dirname(__file__), "examples")
    if os.path.exists(examples_dir):
        for f in sorted(os.listdir(examples_dir)):
            if f.endswith(".py"):
                click.echo(f"  {f}")
    else:
        click.echo("examples 目录不存在")


if __name__ == "__main__":
    cli()
