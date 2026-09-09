"""
AITester CLI 应用：click 命令组、任务执行与结果输出。

使用方式（经由根目录 main.py 薄入口或直接导入）：
    python main.py run examples/calculator.py --func divide
    python main.py run examples/calculator.py examples/string_utils.py --parallel=2
    python main.py run examples/calculator.py --timeout=60
    python main.py run examples/calculator.py --json
    python main.py list-examples

命令行为说明：
    - --parallel=N：并发执行多个测试文件（默认单线程）
    - --timeout=秒：覆盖配置文件中的 EXECUTION_TIMEOUT
    - --json：输出结构化 JSON 结果
    - rich 可用时渲染表格与进度条，缺失时降级为纯文本输出
"""

from __future__ import annotations

import glob as glob_module
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import click

from config import COVERAGE_THRESHOLD, EXECUTION_TIMEOUT, MAX_ITERATIONS
from src import __version__
from src.cli.output import (
    Colors,
    _rich_available,
    colorize,
    error_msg,
    info_msg,
    print_rich_table,
    success_msg,
    warning_msg,
)
from src.graph.state import AITesterState
from src.graph.workflow import build_workflow

# ─── 日志配置 ─────────────────────────────────────────────────────────────────
# 统一日志格式：[时间] [级别] 模块: 消息
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("aitester.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ─── CLI 分组帮助模板 ─────────────────────────────────────────────────────────
class UXGroup(click.Group):
    """自定义 CLI 组，支持分组帮助信息"""

    def get_help(self, ctx: click.Context) -> str:
        """重写 help 生成逻辑，添加示例命令"""
        # 获取默认 help
        help_text = super().get_help(ctx)

        # 添加示例命令（使用 rich 语法）
        examples = """
[bold]示例命令[/bold]
  $ python main.py run examples/calculator.py                    # 测试单个文件
  $ python main.py run examples/*.py --parallel=2                # 并发测试所有示例文件
  $ python main.py run examples/calculator.py --func divide      # 测试指定函数
  $ python main.py run examples/calculator.py --timeout=60       # 设置超时时间
  $ python main.py run examples/calculator.py --json             # 输出 JSON 格式结果
  $ python main.py list-examples                                 # 列出所有示例文件
"""
        return help_text + examples


@click.group(cls=UXGroup)
@click.version_option(version=__version__, prog_name="AITester")
def cli() -> None:
    """AITester - 多智能体自动化测试与自修复系统

    一个基于 LangGraph 的多智能体系统，自动为 Python 代码生成测试、诊断错误、
    并尝试修复问题，直至测试通过或达到最大迭代次数。
    """
    pass


# ─── 任务执行 ─────────────────────────────────────────────────────────────────
def _handle_task_exception(future, future_to_file: dict, func: str | None, results: list) -> None:
    """
    统一处理并行任务执行中的异常，记录日志并追加错误结果。

    Args:
        future: concurrent.futures.Future 对象。
        future_to_file: future -> 文件路径的映射字典。
        func: 被测函数名（用于结果字典）。
        results: 结果列表，异常结果将被追加到此列表。
    """
    file_path = future_to_file[future]
    task_error = future.exception()  # 只调用一次，避免重复取异常
    logger.error("任务执行异常：file=%s, error=%s", file_path, task_error)
    results.append(
        {
            "success": False,
            "file": file_path,
            "func": func or "all",
            "passed": False,
            "error": str(task_error) if task_error else "unknown error",
        }
    )


def _run_single_task(
    target_file: str,
    func: str | None,
    max_iterations: int,
    timeout: int,
    coverage_threshold: float,
    output_json: bool,
) -> dict[str, Any]:
    """
    运行单个测试任务的内部函数。

    Args:
        target_file: 被测 Python 文件路径。
        func: 指定被测函数名，None 表示测试全部函数。
        max_iterations: 最大修复迭代次数。
        timeout: 单个任务的执行超时（秒），经 state 贯通到 Executor。
        coverage_threshold: 覆盖率达标阈值（%），用于结果判定与摘要输出。
        output_json: 是否输出 JSON 格式结果。

    Returns:
        任务结果字典，包含 success、file、func、passed、coverage、coverage_ok、iterations 等字段。
    """
    logger.info("开始测试任务：file=%s, func=%s, timeout=%ds", target_file, func, timeout)

    # 读取被测代码文件内容
    with open(target_file, encoding="utf-8") as f:
        target_code = f.read()

    # 初始化工作流状态
    # execution_timeout / coverage_threshold 经 state 贯通到下游节点（此前两个 CLI 选项均未生效）
    state: AITesterState = {
        "task_uuid": f"{os.path.basename(target_file)}_{func or 'all'}_{int(time.time())}",
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
        "execution_timeout": timeout,
        "coverage_threshold": coverage_threshold,
    }

    # 构建并运行 LangGraph 工作流
    graph = build_workflow()
    final_state = graph.invoke(state)

    # 覆盖率达标判定：无覆盖率数据时为 None（未知），否则与阈值比较
    coverage_value = round(final_state.get("coverage_report", 0.0), 1) if final_state.get("coverage_report") else None
    coverage_ok: bool | None = None if coverage_value is None else coverage_value >= coverage_threshold

    # 构建结果字典
    result = {
        "success": True,
        "file": target_file,
        "func": func or "all",
        "passed": final_state.get("test_passed", False),
        "coverage": coverage_value,
        "coverage_threshold": coverage_threshold,
        "coverage_ok": coverage_ok,
        "iterations": final_state.get("iteration", 0),
        "max_iterations": max_iterations,
        "diagnosis": final_state.get("diagnosis"),
        "error_category": final_state.get("error_category"),
    }

    # 输出结果
    if output_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 输出结果摘要到控制台
        separator = "=" * 50
        click.echo(f"\n{separator}")
        click.echo(f"{Colors.BOLD}任务完成：{target_file}{Colors.RESET}")
        if func:
            click.echo(f"  被测函数：{func}")
        click.echo(f"  测试通过：{final_state.get('test_passed', 'N/A')}")
        if coverage_value is not None:
            threshold_mark = "✓ 达标" if coverage_ok else "✗ 未达标"
            click.echo(f"  覆盖率：{coverage_value:.1f}%（阈值 {coverage_threshold:.1f}% {threshold_mark}）")
        click.echo(f"  修复迭代：{final_state.get('iteration', 0)}/{max_iterations}")
        click.echo(f"{separator}")

        # 根据测试结果输出不同提示
        if final_state.get("test_passed"):
            success_msg("测试全部通过！")
        else:
            error_msg("测试未通过，已达到最大迭代次数。")
            if final_state.get("diagnosis"):
                click.echo(f"\n  根因诊断：{final_state['diagnosis']}")
            if final_state.get("error_category"):
                click.echo(f"  错误类型：{final_state['error_category']}")
            # 提供解决方案建议
            click.echo("\n" + colorize("💡 建议操作：", Colors.CYAN))
            click.echo("  1. 检查被测代码是否存在逻辑错误")
            click.echo("  2. 手动运行被测函数进行调试")
            click.echo("  3. 增加 --max-iterations 参数允许更多修复尝试")
            click.echo("  4. 使用 --verbose 查看详细日志")

    logger.info("任务完成：file=%s, passed=%s", target_file, result["passed"])
    return result


@cli.command()
@click.argument("target_files", type=click.Path(exists=True), nargs=-1)
@click.option("--func", "-f", default=None, help="指定被测函数名，不指定则测试全部函数")
@click.option("--max-iterations", default=MAX_ITERATIONS, help=f"最大修复迭代次数（默认 {MAX_ITERATIONS}）")
@click.option(
    "--coverage-threshold", default=COVERAGE_THRESHOLD, help=f"覆盖率阈值百分比（默认 {COVERAGE_THRESHOLD}%）"
)
@click.option("--parallel", "-p", default=1, type=int, help="并发执行的文件数量（默认 1，单线程）")
@click.option("--timeout", "-t", default=None, type=int, help=f"单个任务执行超时秒数（默认 {EXECUTION_TIMEOUT}s）")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON 格式结果（适合管道处理）")
@click.option("--verbose", "-v", is_flag=True, help="启用详细日志输出（DEBUG 级别）")
def run(
    target_files: tuple,
    func: str | None,
    max_iterations: int,
    coverage_threshold: float,
    parallel: int,
    timeout: int | None,
    json_output: bool,
    verbose: bool,
) -> None:
    """运行测试任务（支持单文件或多个文件）

    TARGET_FILES: 一个或多个被测 Python 文件路径（必须存在）

    示例：
        python main.py run examples/calculator.py
        python main.py run examples/calculator.py examples/string_utils.py
        python main.py run examples/*.py --parallel=2
        python main.py run examples/calculator.py --timeout=60
        python main.py run examples/calculator.py --json

    流程：
        1. 读取目标代码
        2. 初始化工作流状态
        3. 运行多智能体工作流（Planner → Generator → Executor → Debugger → PatchApplier）
        4. 输出执行结果摘要或 JSON
    """
    # 验证参数
    if parallel < 1:
        error_msg("--parallel 必须大于 0")
        raise SystemExit(1)

    if max_iterations < 1:
        error_msg("--max-iterations 必须大于 0")
        raise SystemExit(1)

    if coverage_threshold < 0 or coverage_threshold > 100:
        error_msg(f"--coverage-threshold 必须在 0-100 范围内（当前: {coverage_threshold}%）")
        raise SystemExit(1)

    # 设置详细日志级别
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        info_msg("已启用详细日志模式")

    # 使用命令行指定的 timeout，否则使用配置默认值
    exec_timeout = timeout if timeout is not None else EXECUTION_TIMEOUT

    # 支持 glob 模式展开（如 examples/*.py）
    expanded_files: list[str] = []
    for pattern in target_files:
        matched = glob_module.glob(pattern)
        if matched:
            expanded_files.extend(sorted(matched))
        elif os.path.exists(pattern):
            expanded_files.append(pattern)
        else:
            warning_msg(f"文件不存在：{pattern}")

    if not expanded_files:
        error_msg("没有有效的目标文件，请检查文件路径是否正确")
        info_msg("提示：使用 'python main.py list-examples' 查看可用示例文件")
        raise SystemExit(1)

    logger.info("开始批量测试任务：files=%s, parallel=%d, timeout=%ds", expanded_files, parallel, exec_timeout)

    # 显示任务信息
    if not json_output:
        click.echo(f"\n{Colors.BOLD}开始执行测试任务{Colors.RESET}")
        click.echo(f"  目标文件：{len(expanded_files)} 个")
        click.echo(f"  并发数：{parallel}")
        click.echo(f"  超时：{exec_timeout}s")
        click.echo(f"  最大迭代：{max_iterations}")
        click.echo("")

    # 并发执行
    results: list[dict[str, Any]] = []
    start_time = time.time()

    if parallel > 1 and len(expanded_files) > 1:
        # 并发模式 - 使用进度条
        if _rich_available():
            from rich.console import Console
            from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

            console = Console()
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]执行测试任务[/bold blue]"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            )
            with progress:
                task = progress.add_task("运行中...", total=len(expanded_files))
                with ThreadPoolExecutor(max_workers=parallel) as executor:
                    future_to_file = {
                        executor.submit(
                            _run_single_task, f, func, max_iterations, exec_timeout, coverage_threshold, json_output
                        ): f
                        for f in expanded_files
                    }
                    for future in as_completed(future_to_file):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception:
                            _handle_task_exception(future, future_to_file, func, results)
                        finally:
                            progress.update(task, advance=1)
        else:
            # 无 rich 时的简单进度显示
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_file = {
                    executor.submit(
                        _run_single_task, f, func, max_iterations, exec_timeout, coverage_threshold, json_output
                    ): f
                    for f in expanded_files
                }
                for future in as_completed(future_to_file):
                    try:
                        result = future.result()
                        results.append(result)
                        click.echo(f"  ✓ 完成：{os.path.basename(future_to_file[future])}")
                    except Exception:
                        _handle_task_exception(future, future_to_file, func, results)
    else:
        # 单线程模式
        for target_file in expanded_files:
            result = _run_single_task(target_file, func, max_iterations, exec_timeout, coverage_threshold, json_output)
            results.append(result)

    elapsed_time = time.time() - start_time

    # 汇总统计（单一计算点，供非 JSON 摘要输出与日志复用）
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed

    # 输出汇总信息（非 JSON 模式下）
    if not json_output:
        separator = "=" * 50
        click.echo(f"\n{separator}")
        click.echo(f"{Colors.BOLD}批量测试完成{Colors.RESET}")
        click.echo(f"  总计：{total} 个文件")
        click.echo(f"  通过：{colorize(str(passed), Colors.GREEN)}")
        if failed > 0:
            click.echo(f"  失败：{colorize(str(failed), Colors.RED)}")
        click.echo(f"  耗时：{elapsed_time:.2f}s")
        click.echo(f"{separator}")

        # 打印结果表格
        if _rich_available():
            print_rich_table(results)
        else:
            for r in results:
                status = colorize("✓", Colors.GREEN) if r.get("passed") else colorize("✗", Colors.RED)
                coverage = f"{r.get('coverage', 'N/A')}%" if r.get("coverage") else "N/A"
                click.echo(f"  {status} {r['file']} (func={r['func']}, coverage={coverage})")

        # 显示执行统计
        if passed > 0:
            success_msg(f"{passed}/{total} 个测试通过")
        if failed > 0:
            warning_msg(f"{failed}/{total} 个测试失败")

    logger.info("批量测试完成：总计=%d, 通过=%d, 失败=%d, 耗时=%.2fs", total, passed, failed, elapsed_time)


@cli.command()
def list_examples() -> None:
    """列出 examples 目录下的所有示例 Python 文件，供用户选择测试对象"""
    # 项目根目录 = src/cli/ 的上两级（原 main.py 在根目录时 __file__ 即根目录）
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    examples_dir = os.path.join(project_root, "examples")
    if os.path.exists(examples_dir):
        files = sorted([f for f in os.listdir(examples_dir) if f.endswith(".py")])
        if files:
            click.echo(f"\n{Colors.BOLD}可用示例文件（共 {len(files)} 个）{Colors.RESET}\n")
            for f in files:
                click.echo(f"  {Colors.CYAN}•{Colors.RESET} {f}")
            click.echo(f"\n{Colors.BOLD}使用示例：{Colors.RESET}")
            click.echo(f"  python main.py run examples/{files[0] if files else 'example.py'}")
        else:
            warning_msg("examples 目录下没有找到 Python 文件")
    else:
        warning_msg("examples 目录不存在")
        info_msg("提示：请创建 examples 目录并添加被测 Python 文件")
