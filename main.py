"""
AITester CLI 入口模块：提供命令行接口，调用 LangGraph 工作流完成测试生成与修复。

使用方式：
    python main.py run examples/calculator.py --func divide
    python main.py run examples/calculator.py examples/string_utils.py --parallel=2
    python main.py run examples/calculator.py --timeout=60
    python main.py run examples/calculator.py --json

新增功能（v0.7）：
    - --parallel=N：并发执行多个测试文件（默认单线程）
    - --timeout=秒：覆盖配置文件中的 EXECUTION_TIMEOUT
    - --json：输出结构化 JSON 结果

UX 优化（v0.8）：
    - 彩色输出：rich 库渲染成功/失败/警告信息
    - 进度条：tqdm 显示批量任务执行进度
    - 分组帮助：click 帮助文本按功能分组显示
    - 友好错误提示：提供解决方案建议
    - 改进日志格式：统一时间戳格式，支持 JSON 输出
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import click
from click import style
from concurrent.futures import ThreadPoolExecutor, as_completed

# 尝试导入可选依赖，提供优雅降级
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, BarColumn
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from src.graph.workflow import build_workflow
from src.graph.state import AITesterState
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD, EXECUTION_TIMEOUT

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


# ─── 彩色输出工具 ─────────────────────────────────────────────────────────────
class Colors:
    """终端颜色常量，基于 ANSI 转义序列"""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def colorize(text: str, color: str) -> str:
    """为文本添加颜色（仅在 TTY 模式下生效）"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.RESET}"


def success_msg(msg: str) -> None:
    """输出绿色成功消息"""
    click.echo(colorize(f"✓ {msg}", Colors.GREEN))


def error_msg(msg: str) -> None:
    """输出红色错误消息"""
    click.echo(colorize(f"✗ {msg}", Colors.RED), err=True)


def warning_msg(msg: str) -> None:
    """输出黄色警告消息"""
    click.echo(colorize(f"⚠ {msg}", Colors.YELLOW), err=True)


def info_msg(msg: str) -> None:
    """输出蓝色信息消息"""
    click.echo(colorize(f"ℹ {msg}", Colors.BLUE))


# ─── Rich 输出增强 ────────────────────────────────────────────────────────────
def _rich_available() -> bool:
    """检查 Rich 是否可用"""
    return RICH_AVAILABLE and Console is not None


def print_rich_table(results: List[Dict[str, Any]]) -> None:
    """使用 rich 库打印格式化表格"""
    if not _rich_available():
        return
    
    console = Console()
    table = Table(title="测试执行结果", show_header=True, header_style="bold magenta")
    
    table.add_column("状态", style="bold", width=8)
    table.add_column("文件", max_width=40)
    table.add_column("函数", max_width=20)
    table.add_column("覆盖率", justify="right", max_width=10)
    table.add_column("迭代", justify="right", max_width=8)
    
    for r in results:
        status_icon = "✓" if r.get("passed") else "✗"
        status_style = "green" if r.get("passed") else "red"
        coverage = f"{r.get('coverage', 'N/A')}%" if r.get('coverage') else "N/A"
        
        table.add_row(
            status_icon,
            os.path.basename(r.get("file", "")),
            r.get("func", "all"),
            coverage,
            str(r.get("iterations", 0)),
            style=status_style,
        )
    
    console.print(table)


def print_progress_bar(total: int, desc: str = "处理中") -> None:
    """创建进度条上下文管理器"""
    if not _rich_available():
        return
    
    console = Console()
    progress = Progress(
        SpinnerColumn(),
        TextColumn(f"[bold blue]{desc}[/bold blue]"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    )
    
    with progress:
        progress.add_task(desc, total=total)
        yield progress


# ─── CLI 分组帮助模板 ─────────────────────────────────────────────────────────
class UXGroup(click.Group):
    """自定义 CLI 组，支持分组帮助信息"""
    
    def get_help(self, ctx: click.Context) -> str:
        """重写 help 生成逻辑，添加示例命令"""
        # 获取默认 help
        help_text = super().get_help(ctx)
        
        # 添加示例命令
        examples = """
{\b 示例命令\b}
  $ python main.py run examples/calculator.py                    # 测试单个文件
  $ python main.py run examples/*.py --parallel=2                # 并发测试所有示例文件
  $ python main.py run examples/calculator.py --func divide      # 测试指定函数
  $ python main.py run examples/calculator.py --timeout=60       # 设置超时时间
  $ python main.py run examples/calculator.py --json             # 输出 JSON 格式结果
  $ python main.py list-examples                                 # 列出所有示例文件
"""
        return help_text + examples


# ─── CLI 入口 ─────────────────────────────────────────────────────────────────
@click.group(cls=UXGroup)
@click.version_option(version="0.8.0", prog_name="AITester")
def cli() -> None:
    """AITester - 多智能体自动化测试与自修复系统
    
    一个基于 LangGraph 的多智能体系统，自动为 Python 代码生成测试、诊断错误、
    并尝试修复问题，直至测试通过或达到最大迭代次数。
    """
    pass


def _run_single_task(
    target_file: str,
    func: Optional[str],
    max_iterations: int,
    timeout: int,
    output_json: bool,
) -> Dict[str, Any]:
    """
    运行单个测试任务的内部函数。

    Args:
        target_file: 被测 Python 文件路径。
        func: 指定被测函数名，None 表示测试全部函数。
        max_iterations: 最大修复迭代次数。
        timeout: 单个任务的执行超时（秒）。
        output_json: 是否输出 JSON 格式结果。

    Returns:
        任务结果字典，包含 success、file、func、passed、coverage、iterations 等字段。
    """
    logger.info("开始测试任务：file=%s, func=%s, timeout=%ds", target_file, func, timeout)

    # 读取被测代码文件内容
    with open(target_file, "r", encoding="utf-8") as f:
        target_code = f.read()

    # 初始化工作流状态
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
    }

    # 构建并运行 LangGraph 工作流
    graph = build_workflow()
    final_state = graph.invoke(state)

    # 构建结果字典
    result = {
        "success": True,
        "file": target_file,
        "func": func or "all",
        "passed": final_state.get("test_passed", False),
        "coverage": round(final_state.get("coverage_report", 0.0), 1) if final_state.get("coverage_report") else None,
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
        if final_state.get("coverage_report"):
            click.echo(f"  覆盖率：{final_state['coverage_report']:.1f}%")
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
@click.option("--coverage-threshold", default=COVERAGE_THRESHOLD, help=f"覆盖率阈值百分比（默认 {COVERAGE_THRESHOLD}%）")
@click.option("--parallel", "-p", default=1, type=int, help="并发执行的文件数量（默认 1，单线程）")
@click.option("--timeout", "-t", default=None, type=int, help=f"单个任务执行超时秒数（默认 {EXECUTION_TIMEOUT}s）")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON 格式结果（适合管道处理）")
@click.option("--verbose", "-v", is_flag=True, help="启用详细日志输出（DEBUG 级别）")
def run(
    target_files: tuple,
    func: Optional[str],
    max_iterations: int,
    coverage_threshold: float,
    parallel: int,
    timeout: Optional[int],
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
    import glob as glob_module
    expanded_files: List[str] = []
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
    results: List[Dict[str, Any]] = []
    start_time = time.time()
    
    if parallel > 1 and len(expanded_files) > 1:
        # 并发模式 - 使用进度条
        if _rich_available():
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
                            _run_single_task,
                            f, func, max_iterations, exec_timeout, json_output
                        ): f
                        for f in expanded_files
                    }
                    for future in as_completed(future_to_file):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            logger.error("任务执行异常：file=%s, error=%s", future_to_file[future], e)
                            results.append({
                                "success": False,
                                "file": future_to_file[future],
                                "func": func or "all",
                                "passed": False,
                                "error": str(e),
                            })
                        finally:
                            progress.update(task, advance=1)
        else:
            # 无 rich 时的简单进度显示
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_file = {
                    executor.submit(
                        _run_single_task,
                        f, func, max_iterations, exec_timeout, json_output
                    ): f
                    for f in expanded_files
                }
                for future in as_completed(future_to_file):
                    try:
                        result = future.result()
                        results.append(result)
                        click.echo(f"  ✓ 完成：{os.path.basename(future_to_file[future])}")
                    except Exception as e:
                        logger.error("任务执行异常：file=%s, error=%s", future_to_file[future], e)
                        results.append({
                            "success": False,
                            "file": future_to_file[future],
                            "func": func or "all",
                            "passed": False,
                            "error": str(e),
                        })
    else:
        # 单线程模式
        for target_file in expanded_files:
            result = _run_single_task(target_file, func, max_iterations, exec_timeout, json_output)
            results.append(result)

    elapsed_time = time.time() - start_time

    # 输出汇总信息（非 JSON 模式下）
    if not json_output:
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed
        
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
                coverage = f"{r.get('coverage', 'N/A')}%" if r.get('coverage') else "N/A"
                click.echo(f"  {status} {r['file']} (func={r['func']}, coverage={coverage})")
        
        # 显示执行统计
        if passed > 0:
            success_msg(f"{passed}/{total} 个测试通过")
        if failed > 0:
            warning_msg(f"{failed}/{total} 个测试失败")

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    logger.info("批量测试完成：总计=%d, 通过=%d, 失败=%d, 耗时=%.2fs", total, passed, failed, elapsed_time)


@cli.command()
def list_examples() -> None:
    """列出 examples 目录下的所有示例 Python 文件，供用户选择测试对象"""
    examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
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


if __name__ == "__main__":
    cli()
