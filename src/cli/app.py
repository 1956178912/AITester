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

import contextlib
import glob as glob_module
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
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
from src.graph import token_usage
from src.graph.state import AITesterState
from src.graph.workflow import build_workflow, end_task_trace, start_task_trace
from src.utils.logging_utils import SensitiveFormatter, mask_sensitive_info, setup_logger_safety

# ─── 日志配置 ─────────────────────────────────────────────────────────────────
# 统一日志格式：[时间] [级别] 模块: 消息
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 每个 handler 使用 SensitiveFormatter：在格式化后的完整日志行（含 exc_info 异常
# 堆栈）上再脱敏一次，堵住 SensitiveFilter 只覆盖消息体、异常堆栈绕过的盲区
_log_formatter = SensitiveFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

# 文件 handler 在导入期立即打开 aitester.log：CWD 不可写时（只读环境/无权限目录）
# 不能因此让整个 CLI 崩溃，降级为仅控制台输出
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_formatter)
_log_handlers: list[logging.Handler] = [_console_handler]
try:
    _file_handler = logging.FileHandler("aitester.log", encoding="utf-8")
    _file_handler.setFormatter(_log_formatter)
    _log_handlers.append(_file_handler)
except OSError:
    pass

logging.basicConfig(
    level=logging.INFO,
    handlers=_log_handlers,
)

# 接入敏感信息脱敏过滤器（SensitiveFilter）：
# LLM 调用异常文本可能携带 API Key / JWT 等凭证，过滤后自动替换为占位符，
# 避免凭证泄露进 aitester.log 与控制台输出。此前该模块未被任何入口引用，
# 脱敏能力实际从未生效。
setup_logger_safety()

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _quiet_console_logs():
    """--json 模式下临时静音 stdout 控制台日志，让 stdout 只承载 JSON（便于管道/jq）。

    实现（避免全局改 handler.stream，保持对测试捕获环境友好）：
      - 仅把 stdout 控制台 handler 的 level 临时提到 CRITICAL+1（静音），
        FileHandler（aitester.log）不动，日志仍会落盘；
      - 块结束自动还原 level。
    配合 rich Progress 传 Console(stderr=True)，进度条也走 stderr，不污染 stdout。
    """
    root = logging.getLogger()
    muted: list[tuple[logging.Handler, int]] = []
    for handler in root.handlers:
        # 只静音写控制台（非文件）的 StreamHandler
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            muted.append((handler, handler.level))
            handler.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        for handler, level in muted:
            handler.setLevel(level)


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
def _make_task_error_result(file_path: str, func: str | None, error: BaseException | None) -> dict[str, Any]:
    """构建任务异常结果字典（与 _run_single_task 正常结果同构，便于汇总统计）。

    Args:
        file_path: 被测文件路径。
        func: 被测函数名（None 时记 "all"）。
        error: 触发异常的 Exception（None 时 error 字段记 "unknown error"）。

    Returns:
        标记 success/passed 为 False 的结果字典，含 error 描述（已脱敏，防 LLM 异常
        文本携带的 API Key 经 JSON/stdout 外泄——脱敏过滤器只覆盖 logging 通道）。
    """
    return {
        "success": False,
        "file": file_path,
        "func": func or "all",
        "passed": False,
        "error": mask_sensitive_info(str(error)) if error else "unknown error",
    }


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
    results.append(_make_task_error_result(file_path, func, task_error))


def _dispatch_parallel_tasks(
    expanded_files: list[str],
    func: str | None,
    max_iterations: int,
    exec_timeout: int,
    coverage_threshold: float,
    json_output: bool,
    parallel: int,
    results: list[dict[str, Any]],
    on_progress: Callable[[Future], None] | None = None,
    on_success: Callable[[str], None] | None = None,
) -> None:
    """并发派发任务并逐任务追加结果（单任务异常不中断整批）。

    rich 进度条模式与纯文本降级模式的共享派发器：两种模式唯一差异是进度反馈策略，
    由调用方经 on_progress / on_success 回调注入。任务提交、as_completed 汇总与异常
    兜底收敛到单一构造点（此前两段同构块各自维护提交+汇总循环，结果结构变化需
    同步改两处，易漂移）。

    Args:
        expanded_files: 目标文件路径列表。
        func: 被测函数名（None 表示全部函数）。
        max_iterations: 最大修复迭代次数。
        exec_timeout: 单任务执行超时（秒）。
        coverage_threshold: 覆盖率阈值（%）。
        json_output: 是否 JSON 输出模式（影响调用方决定的 on_success 行为）。
        parallel: 并发 worker 数。
        results: 结果列表，每个任务的成功/错误结果追加于此。
        on_progress: 每个任务结束（无论成败）后触发的回调，供 rich 进度条推进。
        on_success: 任务成功后触发的回调（传入文件 basename），供纯文本进度显示。
    """
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        future_to_file = {
            executor.submit(_run_single_task, f, func, max_iterations, exec_timeout, coverage_threshold, json_output): f
            for f in expanded_files
        }
        for future in as_completed(future_to_file):
            try:
                result = future.result()
                results.append(result)
                if on_success:
                    on_success(os.path.basename(future_to_file[future]))
            except Exception:
                _handle_task_exception(future, future_to_file, func, results)
            finally:
                if on_progress:
                    on_progress(future)


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
        "regeneration_count": 0,
        "repair_history": [],
        "execution_timeout": timeout,
        "coverage_threshold": coverage_threshold,
    }

    # 构建并运行 LangGraph 工作流
    graph = build_workflow()
    # 4.1 结构化追踪：任务级 JSONL 会话（AITESTER_TRACE_DIR 未设时全 no-op）
    start_task_trace(
        state["task_uuid"],
        task_meta={"file": target_file, "func": func or "all", "dataset": "cli"},
    )
    try:
        final_state = graph.invoke(state)
    finally:
        # 追踪收尾在 finally：工作流崩溃（如 recursion_limit）时仍记录 task_end
        end_task_trace(
            final_state.get("test_passed") if "final_state" in locals() else None,
            token_snapshot=token_usage.get_usage().as_dict(),
        )

    # 覆盖率达标判定：无覆盖率数据（None）时为 None（未知），否则与阈值比较
    # 注意用 is not None 判断——0.0 是合法的"覆盖率数据"，不可被 falsy 误判为缺失
    raw_coverage = final_state.get("coverage_report")
    coverage_value = round(raw_coverage, 1) if raw_coverage is not None else None
    coverage_ok: bool | None = None if coverage_value is None else coverage_value >= coverage_threshold

    # 构建结果字典
    # 1.1 状态细化：失败任务按 repair_history / rag_stats 信号补两类专属
    # 失败类别（补丁被安全守卫拒绝 / RAG 检索全空），与 benchmark 口径一致
    from src.agents.error_classifier import refine_failure_category

    error_category = refine_failure_category(
        final_state.get("error_category") or "",
        final_state.get("test_passed", False),
        repair_history=final_state.get("repair_history"),
        rag_stats=final_state.get("rag_stats"),
    )
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
        "error_category": error_category,
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

    # 超时参数校验：负数/0 会让 subprocess 立即超时，属于无效输入
    if timeout is not None and timeout < 1:
        error_msg(f"--timeout 必须 >= 1 秒（当前: {timeout}）")
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

    # --json 模式：静音 stdout 控制台日志 + rich 进度条走 stderr，让 stdout 只承载 JSON
    # （此前 json 输出与日志同走 stdout，`| jq` 解析必失败）
    _quiet_ctx = _quiet_console_logs() if json_output else contextlib.nullcontext()

    with _quiet_ctx:
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
            # 并发模式：rich 进度条与纯文本降级共用同一派发器（_dispatch_parallel_tasks），
            # 仅进度反馈策略（on_progress / on_success 回调）不同
            dispatch_kwargs = dict(
                expanded_files=expanded_files,
                func=func,
                max_iterations=max_iterations,
                exec_timeout=exec_timeout,
                coverage_threshold=coverage_threshold,
                json_output=json_output,
                parallel=parallel,
                results=results,
            )
            if _rich_available():
                from rich.console import Console
                from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

                # --json 时进度条也走 stderr，保持 stdout 纯 JSON
                console = Console(stderr=json_output)
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
                    _dispatch_parallel_tasks(
                        on_progress=lambda _f: progress.update(task, advance=1),
                        **dispatch_kwargs,
                    )
            else:
                # --json 时不往 stdout 打进度（保持纯 JSON）
                _dispatch_parallel_tasks(
                    on_success=None if json_output else (lambda name: click.echo(f"  ✓ 完成：{name}")),
                    **dispatch_kwargs,
                )
        else:
            # 单线程模式
            # 逐任务容错：单个任务异常（如读取失败、工作流崩溃）不中断整个批次，
            # 与并发分支的 _handle_task_exception 行为对齐，保证后续文件继续执行
            for target_file in expanded_files:
                try:
                    result = _run_single_task(
                        target_file, func, max_iterations, exec_timeout, coverage_threshold, json_output
                    )
                    results.append(result)
                except Exception as e:
                    logger.error("任务执行异常：file=%s, error=%s", target_file, e)
                    results.append(_make_task_error_result(target_file, func, e))

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
                    # 0.0 是合法覆盖率，用 is not None 判断缺失（falsy 会把 0% 误显示为 N/A）
                    r_cov = r.get("coverage")
                    coverage = f"{r_cov}%" if r_cov is not None else "N/A"
                    click.echo(f"  {status} {r['file']} (func={r['func']}, coverage={coverage})")

            # 显示执行统计
            if passed > 0:
                success_msg(f"{passed}/{total} 个测试通过")
            if failed > 0:
                warning_msg(f"{failed}/{total} 个测试失败")

        logger.info("批量测试完成：总计=%d, 通过=%d, 失败=%d, 耗时=%.2fs", total, passed, failed, elapsed_time)
        exit_code = 1 if failed > 0 else 0

    # 有任一任务失败（含任务崩溃产生的错误结果）时以非零码退出，
    # 让 CI/脚本能把 AITester 当门控工具用（此前无论成败都 exit 0）
    if exit_code:
        raise SystemExit(exit_code)


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
            # 此处 files 非空（上方 if files 分支保证），直接取首个文件
            click.echo(f"  python main.py run examples/{files[0]}")
        else:
            warning_msg("examples 目录下没有找到 Python 文件")
    else:
        warning_msg("examples 目录不存在")
        info_msg("提示：请创建 examples 目录并添加被测 Python 文件")


@cli.command(name="check-dataset")
@click.argument("dataset", default="examples")
@click.option("--subset", "-s", default=None, help="数据子集（如 lite/mini）")
@click.option("--limit", "-n", default=3, type=int, help="展示前 N 个任务的加载详情（默认 3）")
def check_dataset(dataset: str, subset: str | None, limit: int) -> None:
    """校验数据集加载质量（P0：SWE-bench 加载正确性排查入口）。

    加载指定数据集，逐任务检查 instance_code / test_code 完整性，
    打印前 N 个任务的加载详情与全量质量报告。

    示例：
        python main.py check-dataset swe_bench --subset lite
        python main.py check-dataset examples
    """
    from src.datasets.dataset_loader import SWEBenchDataset, load_dataset

    try:
        loader = load_dataset(dataset, subset=subset)
    except Exception as e:
        error_msg(f"数据集加载失败: {e}")
        return

    tasks = loader.tasks
    info_msg(f"数据集 {dataset}（子集: {subset or '全部'}）共加载 {len(tasks)} 个任务")

    # 逐任务打印加载详情（前 N 个，对应"手动检查 2-3 个任务"的排查方法）
    for task in tasks[:limit]:
        info_msg(f"── {task.task_id} ──")
        info_msg(f"  repo: {task.repo_name}")
        info_msg(f"  测试用例数: {task.total_test_count}（期望通过 {task.expected_pass_count}）")
        info_msg(f"  问题描述: {task.problem_statement[:80]}{'…' if len(task.problem_statement) > 80 else ''}")
        info_msg(f"  instance_code: {len(task.instance_code)} 字符")
        info_msg(f"  test_code: {len(task.test_code)} 字符")
        suggested = task.metadata.get("suggested_function")
        info_msg(f"  目标函数（从官方 patch 提取）: {suggested or '（未识别）'}")
        issues = SWEBenchDataset.validate_task(task)
        if issues:
            for issue in issues:
                warning_msg(f"  ⚠ {issue}")
        else:
            info_msg("  ✓ 加载质量健康")

    # 全量质量报告（仅 SWE-bench/Defects4J 等标准数据集有意义）
    report = {}
    if hasattr(loader, "quality_report"):
        report = loader.quality_report()
    if report:
        warning_msg(f"质量报告：{len(report)}/{len(tasks)} 个任务存在加载问题：")
        for task_id, issues in list(report.items())[:10]:
            warning_msg(f"  {task_id}: {'; '.join(issues)}")
        if len(report) > 10:
            warning_msg(f"  …（其余 {len(report) - 10} 个略）")
    else:
        info_msg(f"✓ 全量质量检查通过（{len(tasks)} 个任务无加载问题）")

    # 2.1 源码补充流程：缺失被测源码的任务单独列出 instance_id，
    # 供 export_swe_bench_source.py 批量导出 / SWE_BENCH_ENRICHMENT 补全
    if hasattr(loader, "tasks_missing_source"):
        missing_source = loader.tasks_missing_source()
        if missing_source:
            warning_msg(
                f"⚠ 缺失被测源码任务 {len(missing_source)} 个（instance_code 兜底为 issue 文本）："
            )
            for task_id in missing_source[:20]:
                warning_msg(f"  {task_id}")
            if len(missing_source) > 20:
                warning_msg(f"  …（其余 {len(missing_source) - 20} 个略）")
            warning_msg(
                "  补充方式：运行 scripts/export_swe_bench_source.py 按 base_commit 自动导出，"
                "再经 SWE_BENCH_ENRICHMENT 环境变量加载"
            )
        else:
            info_msg(f"✓ 全部 {len(tasks)} 个任务均含被测源码")
