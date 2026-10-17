"""
AITester CLI 应用：click 命令组、任务执行与结果输出。

使用方式（经由根目录 main.py 薄入口或直接导入）：
    python main.py run examples/calculator.py --func divide
    python main.py run examples/calculator.py examples/string_utils.py --parallel=2
    python main.py run examples/calculator.py --timeout=60
    python main.py run examples/calculator.py --json
    python main.py list-examples
    python main.py doctor

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
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import click

from config import COVERAGE_THRESHOLD, EXECUTION_TIMEOUT, MAX_ITERATIONS
from src import __version__
from src.budget import token_usage
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
from src.graph.event_bus import get_event_bus
from src.graph.state import create_initial_state
from src.graph.workflow import build_workflow, end_task_trace, start_task_trace
from src.utils.logging_utils import SensitiveFormatter, mask_sensitive_info, setup_logger_safety

# ─── 日志配置 ─────────────────────────────────────────────────────────────────
# 统一日志格式：[时间] [级别] 模块: 消息
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 每个 handler 使用 SensitiveFormatter：在格式化后的完整日志行（含 exc_info 异常
# 堆栈）上再脱敏一次，堵住 SensitiveFilter 只覆盖消息体、异常堆栈绕过的盲区
_log_formatter = SensitiveFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

# U8（2026-10-05 系统性审查落地）：日志初始化从"导入期副作用"改为 CLI 入口
# 惰性初始化——此前 import src.cli.app 即 basicConfig + 在 CWD 打开
# aitester.log，任何把它当库导入的代码（测试/嵌入/experiments）都被迫产生
# 日志文件、被改 root logger。现拆为 _configure_cli_logging()，仅 click 组
# cli() 回调调用（幂等哨兵防重）；模块导入零副作用。
_LOGGING_CONFIGURED = False
# U8：生效中的 handler 清单（_configure_cli_logging 执行后填充，供测试/诊断
# 观测脱敏 formatter 是否挂载；导入期为空列表 = 未初始化）。
_ACTIVE_CLI_HANDLERS: list[logging.Handler] = []


def _configure_cli_logging() -> None:
    """CLI 入口日志初始化（幂等；文件 handler 失败降级仅控制台）。"""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    _LOGGING_CONFIGURED = True
    # 文件 handler 在 CLI 启动时打开 aitester.log：CWD 不可写时（只读环境/
    # 无权限目录）不能因此让 CLI 崩溃，降级为仅控制台输出
    _console_handler = logging.StreamHandler(sys.stdout)
    _console_handler.setFormatter(_log_formatter)
    handlers: list[logging.Handler] = [_console_handler]
    try:
        _file_handler = logging.FileHandler("aitester.log", encoding="utf-8")
        _file_handler.setFormatter(_log_formatter)
        handlers.append(_file_handler)
    except OSError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
    )
    _ACTIVE_CLI_HANDLERS.clear()
    _ACTIVE_CLI_HANDLERS.extend(handlers)

    # 接入敏感信息脱敏过滤器（SensitiveFilter）：
    # LLM 调用异常文本可能携带 API Key / JWT 等凭证，过滤后自动替换为占位符，
    # 避免凭证泄露进 aitester.log 与控制台输出。
    setup_logger_safety()


logger = logging.getLogger(__name__)


def _event_bus_stats() -> dict[str, Any]:
    """1.4 事件总线观测统计（各事件发布次数 + 已订阅事件名）。"""
    return get_event_bus().stats()


@contextlib.contextmanager
def _quiet_console_logs() -> Iterator[None]:
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
  $ python main.py doctor                                        # 零 LLM 自检（环境/配置 + 功能矩阵，不消耗 API 配额）
"""
        return help_text + examples


@click.group(cls=UXGroup)
@click.version_option(version=__version__, prog_name="AITester")
def cli() -> None:
    """AITester - 检出优先的测试生成与修复评估（归因）系统

    以**检出优先协议**为主成功口径：自动为 Python 代码生成测试、诊断错误、
    尝试修复，直至测试通过或达到最大迭代次数；并如实报告 detection / repair /
    false_fix 三指标与口径（见 BASELINE.yaml）。

    注：编排层（LangGraph：Planner → Generator → Executor → Debugger →
    PatchApplier）在本系统中定位为**可消融容器**，非主断言——项目自身 n=261
    实验测得编排净贡献为负（δ≈−0.28，ADR-0016），故不再以"多智能体"为主表述
    （与 README / MODEL_CARD 对齐）。
    """
    # U8：CLI 入口惰性日志初始化（幂等；库导入不再产生 aitester.log）
    _configure_cli_logging()


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


def _handle_task_exception(
    future: Future, future_to_file: dict[Future, str], func: str | None, results: list[dict[str, Any]]
) -> None:
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
    dump_trace_on_failure: bool = False,
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
        dump_trace_on_failure: 任务失败时写内存追踪快照到 ./tmp_trace/（默认 False 零 I/O）。
    """
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        future_to_file = {
            executor.submit(
                _run_single_task,
                f,
                func,
                max_iterations,
                exec_timeout,
                coverage_threshold,
                json_output,
                dump_trace_on_failure,
            ): f
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


def _dispatch_concurrent(
    expanded_files: list[str],
    func: str | None,
    max_iterations: int,
    exec_timeout: int,
    coverage_threshold: float,
    json_output: bool,
    parallel: int,
    results: list[dict[str, Any]],
    dump_trace_on_failure: bool = False,
) -> None:
    """并发执行测试任务（rich 进度条优先，纯文本降级兜底）。

    rich 可用时渲染进度条（--json 时进度条走 stderr，保持 stdout 纯 JSON）；
    否则降级为纯文本逐任务提示（--json 时静默，避免污染 JSON 输出）。
    两种模式共享 _dispatch_parallel_tasks 派发器，仅进度反馈策略不同。

    Args:
        expanded_files: 目标文件路径列表。
        func: 被测函数名（None 表示全部函数）。
        max_iterations: 最大修复迭代次数。
        exec_timeout: 单任务执行超时（秒）。
        coverage_threshold: 覆盖率阈值（%）。
        json_output: 是否 JSON 输出模式（影响进度条输出通道与降级提示）。
        parallel: 并发 worker 数。
        results: 结果列表，每个任务的成功/错误结果追加于此。
        dump_trace_on_failure: 任务失败时写内存追踪快照到 ./tmp_trace/（默认 False 零 I/O）。
    """
    # 两种进度反馈模式（纯文本 / rich 进度条）共享 7 个公共位置参数，
    # 唯一差异是 on_progress（rich 推进度条）/ on_success（纯文本逐任务提示）
    # 回调，避免重复展开 8 个位置参数两次（此前两段同构块易漂移）。
    # 值类型与各参数签名一一对应（list[str] / str | None / int / float /
    # bool / int / list[dict[str, Any]]）；标注 dict[str, object] 仅为 mypy
    # 对 **kwargs 展开的静态校验放行（运行时值均为各参数期望类型）
    shared_kwargs: dict[str, object] = {
        "expanded_files": expanded_files,
        "func": func,
        "max_iterations": max_iterations,
        "exec_timeout": exec_timeout,
        "coverage_threshold": coverage_threshold,
        "json_output": json_output,
        "parallel": parallel,
        "results": results,
        "dump_trace_on_failure": dump_trace_on_failure,
    }
    if not _rich_available():
        # 纯文本降级：--json 时不往 stdout 打进度（保持纯 JSON）
        _dispatch_parallel_tasks(
            on_success=None if json_output else (lambda name: click.echo(f"  ✓ 完成：{name}")),
            **shared_kwargs,  # type: ignore[arg-type]
        )
        return

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
            **shared_kwargs,  # type: ignore[arg-type]
        )


def _dump_trace_on_failure(output_json: bool) -> str | None:
    """任务失败时把内存追踪快照写成临时 JSONL 供诊断（--dump-trace-on-failure）。

    仅当 CLI 显式开启 --dump-trace-on-failure 且本任务失败时触发；
    把进程级内存快照（TraceSession 累积的最近任务节点记录，默认启用、不落盘）
    经 `dump_recent_to` 写入 `./tmp_trace/<ts>_failed_trace.jsonl` 并提示路径。
    无快照可写 / 写盘失败时静默跳过（诊断出口，不影响主流程）。

    Returns:
        写盘成功时返回路径字符串（供调用方把 `trace_dump_path` 字段写进结果 dict），
        无快照可写 / 写盘失败时返回 None。
    """
    from src.observability.trace import dump_recent_to

    target_dir = os.path.join(os.getcwd(), "tmp_trace")
    path = dump_recent_to(target_dir)
    if path is None:
        return None
    logger.info("失败追踪快照已写盘: %s", path)
    if not output_json:
        click.echo(f"\n  诊断追踪：{path}（--dump-trace-on-failure）")
    return path


def _run_single_task(
    target_file: str,
    func: str | None,
    max_iterations: int,
    timeout: int,
    coverage_threshold: float,
    output_json: bool,
    dump_trace_on_failure: bool | None = None,
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
        dump_trace_on_failure: 任务失败时把内存追踪快照（--dump-trace-on-failure）
            写成临时 JSONL 供诊断；None/False 时不触发（默认行为不变，零 I/O）。

    Returns:
        任务结果字典，包含 success、file、func、passed、coverage、coverage_ok、iterations 等字段。
    """
    logger.info("开始测试任务：file=%s, func=%s, timeout=%ds", target_file, func, timeout)

    # O35（2026-09-30 全面审查 P1）：任务级统计逐任务复位（与 run_benchmark
    # 同口径）。此前 CLI 侧**从不** reset：
    #   - token_usage 是线程局部累计，--parallel 的 ThreadPoolExecutor 复用
    #     工作线程 → 第 2 个任务的 trace token_snapshot 含第 1 个任务的量，
    #     "逐任务 token 消耗"随同线程任务数递增（虚高）；
    #   - cost_budget 的 budget.exceeded 一旦置真永不复位 → 同线程后续任务
    #     所有 LLM 调用被前置守卫拦下（任务级预算退化为线程级终身封顶）。
    token_usage.reset()
    from src.budget.cost_budget import reset_budget

    reset_budget()

    # 读取被测代码文件内容
    with open(target_file, encoding="utf-8") as f:
        target_code = f.read()

    # 初始化工作流状态（唯一构造点：create_initial_state，与 benchmark 口径一致）
    # execution_timeout / coverage_threshold 经 state 贯通到下游节点（此前两个 CLI 选项均未生效）
    state = create_initial_state(
        task_uuid=f"{os.path.basename(target_file)}_{func or 'all'}_{int(time.time())}",
        target_file=target_file,
        target_function=func,
        target_code=target_code,
        max_iterations=max_iterations,
        execution_timeout=timeout,
        coverage_threshold=coverage_threshold,
    )

    # 构建并运行 LangGraph 工作流
    graph = build_workflow()
    # 4.1 结构化追踪：任务级 JSONL 会话（AITESTER_TRACE_DIR 未设时全 no-op）
    start_task_trace(
        state["task_uuid"],
        task_meta={"file": target_file, "func": func or "all", "dataset": "cli"},
    )
    # 初始化 final_state 为 None：graph.invoke 抛异常（recursion_limit 等）时，
    # finally 收尾分支走 None 路径而非依赖 locals() 检查——后者语义晦涩且
    # 任何在 invoke 前给 final_state 赋值的重构都会让该分支恒为 None 而无人察觉
    final_state: dict[str, Any] | None = None
    try:
        final_state = graph.invoke(state)
    finally:
        # 追踪收尾在 finally：工作流崩溃（如 recursion_limit）时仍记录 task_end
        end_task_trace(
            final_state.get("test_passed") if final_state is not None else None,
            token_snapshot=token_usage.get_usage().as_dict(),
        )

    # graph.invoke 是 LangGraph 同步调用，正常返回必为非 None dict；为 None 说明
    # invoke 内部状态异常（非预期），按失败结果处理而非 NPE。mypy 沿"已赋值"
    # 路径仍判 dict|None（invoke 返回 Any 但 try/finally 语义下不做收窄），显式 assert
    # 收窄，运行期异常路径已由上层 _run_single_task 的调用方捕获
    assert final_state is not None, "graph.invoke 未返回状态（非预期）"

    # 覆盖率达标判定：无覆盖率数据（None）时为 None（未知），否则与阈值比较
    # 注意用 is not None 判断——0.0 是合法的"覆盖率数据"，不可被 falsy 误判为缺失
    raw_coverage = final_state.get("coverage_report")
    coverage_value = round(raw_coverage, 1) if raw_coverage is not None else None
    coverage_ok: bool | None = None if coverage_value is None else coverage_value >= coverage_threshold

    # 构建结果字典
    # 1.1 状态细化：失败任务按 repair_history / rag_stats 信号补两类专属
    # 失败类别（补丁被安全守卫拒绝 / RAG 检索全空），与 benchmark 口径一致
    from src.agents.error_classifier import refine_final_error_category
    from src.graph.event_bus import WorkflowCompleted, publish_event

    error_category = refine_final_error_category(final_state)
    # 1.4 事件总线接线：WorkflowCompleted（工作流收尾，纯观测）
    publish_event(
        WorkflowCompleted(
            task_uuid=state.get("task_uuid", ""),
            test_passed=bool(final_state.get("test_passed")),
            iteration=int(final_state.get("iteration", 0)),
            final_error_category=error_category,
        )
    )
    # 6.1/1.4：--json 输出含 1.4 事件总线观测统计 + 5.4 预算统计
    # （纯观测字段，供管道 / 脚本消费；非 JSON 模式不展示）
    from src.agents.semantic_cache import get_semantic_cache_stats
    from src.budget.cost_budget import get_process_budget_stats

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
        # 1.4 事件总线 / 5.4 预算 / 5.1 语义缓存 观测统计
        "event_bus": _event_bus_stats(),
        "cost_budget": get_process_budget_stats(),
        "semantic_cache": get_semantic_cache_stats(),
    }

    # 可观测性批次：--dump-trace-on-failure 且本任务失败 → 把内存追踪快照
    # （TraceSession 累积的最近任务节点记录，默认启用不落盘）写成临时 JSONL
    # 供诊断；写盘成功时把路径写进 result（JSON 模式可消费），失败静默跳过。
    if dump_trace_on_failure and not result["passed"]:
        _dump_path = _dump_trace_on_failure(output_json)
        if _dump_path is not None:
            result["trace_dump_path"] = _dump_path

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
@click.option(
    "--dump-trace-on-failure",
    "dump_trace_on_failure",
    is_flag=True,
    default=False,
    help="任务失败时把内存追踪快照（最近任务节点记录，默认启用不落盘）写成 "
    "./tmp_trace/<ts>_failed_trace.jsonl 供诊断；默认关，不设置时无 I/O",
)
def run(
    target_files: tuple[str, ...],
    func: str | None,
    max_iterations: int,
    coverage_threshold: float,
    parallel: int,
    timeout: int | None,
    json_output: bool,
    verbose: bool,
    dump_trace_on_failure: bool,
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
        3. 运行可消融编排工作流（Planner → Generator → Executor → Debugger → PatchApplier）
        4. 输出执行结果摘要或 JSON
    """
    _validate_run_args(parallel, max_iterations, coverage_threshold, timeout)

    # 设置详细日志级别
    if verbose and not json_output:
        logging.getLogger().setLevel(logging.DEBUG)
        info_msg("已启用详细日志模式")
    elif verbose and json_output:
        # 2026-09-26 round10 P2：--json 静音 stdout 控制台日志（让 stdout 只
        # 承载 JSON），--verbose 把 root logger 提到 DEBUG 也无效（stdout
        # handler 被 _quiet_console_logs 提到 CRITICAL+1 拦截）——显式提示
        # 用户两 flag 组合时 verbose 不生效，避免参数语义冲突导致误判。
        # N 轮 N-1 e2e 探针（cli-run-json-single）实测修复：本提示此前经
        # info_msg 走 stdout，直接污染 `run ... --json --verbose` 的 JSON
        # 输出（`| jq` 首行解析失败），与 --quiet_console_logs 文档承诺的
        # "stdout 只承载 JSON"契约矛盾——提示改走 stderr（--json 模式下
        # stderr 才是人读通道；非 JSON 模式的 verbose 提示路径不变）。
        click.echo(
            "ℹ 提示：--json 模式下控制台日志被静音，--verbose 不生效（DEBUG 日志仅在非 JSON 模式输出）", err=True
        )

    # 使用命令行指定的 timeout，否则使用配置默认值
    exec_timeout = timeout if timeout is not None else EXECUTION_TIMEOUT

    # 支持 glob 模式展开（如 examples/*.py）
    expanded_files = _expand_target_files(target_files)

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
            _dispatch_concurrent(
                expanded_files,
                func,
                max_iterations,
                exec_timeout,
                coverage_threshold,
                json_output,
                parallel,
                results,
                dump_trace_on_failure=dump_trace_on_failure,
            )
        else:
            # 单线程模式
            # 逐任务容错：单个任务异常（如读取失败、工作流崩溃）不中断整个批次，
            # 与并发分支的 _handle_task_exception 行为对齐，保证后续文件继续执行
            for target_file in expanded_files:
                try:
                    result = _run_single_task(
                        target_file,
                        func,
                        max_iterations,
                        exec_timeout,
                        coverage_threshold,
                        json_output,
                        dump_trace_on_failure=dump_trace_on_failure,
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
            _print_run_summary(results, total, passed, failed, elapsed_time)

        logger.info("批量测试完成：总计=%d, 通过=%d, 失败=%d, 耗时=%.2fs", total, passed, failed, elapsed_time)
        exit_code = 1 if failed > 0 else 0

    # 有任一任务失败（含任务崩溃产生的错误结果）时以非零码退出，
    # 让 CI/脚本能把 AITester 当门控工具用（此前无论成败都 exit 0）
    if exit_code:
        raise SystemExit(exit_code)


def _validate_run_args(parallel: int, max_iterations: int, coverage_threshold: float, timeout: int | None) -> None:
    """校验 run 命令输入参数，非法时抛 SystemExit(1)。"""
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


def _expand_target_files(target_files: tuple[str, ...]) -> list[str]:
    """展开 glob 模式与普通路径，返回存在的文件列表（glob 匹配项按字典序稳定排序）。"""
    expanded_files: list[str] = []
    for pattern in target_files:
        matched = glob_module.glob(pattern)
        if matched:
            expanded_files.extend(sorted(matched))
        elif os.path.exists(pattern):
            expanded_files.append(pattern)
        else:
            warning_msg(f"文件不存在：{pattern}")
    return expanded_files


def _print_run_summary(
    results: list[dict[str, Any]], total: int, passed: int, failed: int, elapsed_time: float
) -> None:
    """打印批量测试完成摘要（非 JSON 模式，含结果表格与统计）。"""
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


@cli.command()
def list_examples() -> None:
    """列出 examples 目录下的所有示例 Python 文件，供用户选择测试对象"""
    # 项目根目录 = src/cli/ 的上两级（原 main.py 在根目录时 __file__ 即根目录）
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    examples_dir = os.path.join(project_root, "examples")
    if os.path.exists(examples_dir):
        # N 轮 N-1 e2e 探针（cli-list-examples）实测修复：此前把
        # `examples/__init__.py` 等下划线开头文件也列为示例，并把它当作
        # "使用示例"建议执行——用户复制首条命令得到空模块任务（无意义）。
        # 过滤下划线开头文件（包初始化/私有模块不是可运行示例）；
        # 使用示例优先建议 calculator.py（README/文档主推示例）。
        files = sorted([f for f in os.listdir(examples_dir) if f.endswith(".py") and not f.startswith("_")])
        if files:
            click.echo(f"\n{Colors.BOLD}可用示例文件（共 {len(files)} 个）{Colors.RESET}\n")
            for f in files:
                click.echo(f"  {Colors.CYAN}•{Colors.RESET} {f}")
            click.echo(f"\n{Colors.BOLD}使用示例：{Colors.RESET}")
            suggested = "calculator.py" if "calculator.py" in files else files[0]
            click.echo(f"  python main.py run examples/{suggested}")
        else:
            warning_msg("examples 目录下没有找到 Python 文件")
    else:
        warning_msg("examples 目录不存在")
        info_msg("提示：请创建 examples 目录并添加被测 Python 文件")


@cli.command(name="clean-venv-cache")
@click.option("--max-age-days", default=None, type=int, help="超过该天数的 venv 删除（None 表示不按年龄过滤）")
@click.option("--max-size-mb", default=None, type=int, help="超过该大小（MB）的 venv 删除（None 表示不按大小过滤）")
@click.option("--list-only", "-l", is_flag=True, help="仅列出缓存目录内容，不删除")
def clean_venv_cache(max_age_days: int | None, max_size_mb: int | None, list_only: bool) -> None:
    """清理 ExecutorAgent 的 venv 依赖缓存（4.4：按时间/大小清理 + 命中率统计）。

    缓存目录默认 ~/.cache/aitester/venvs/（可经 AITESTER_VENV_CACHE_DIR 环境变量覆盖）。
    两个过滤条件均缺省时清空全部缓存；--list-only 只读展示，不产生删除。

    示例：
        python main.py clean-venv-cache --list-only            # 查看现有缓存
        python main.py clean-venv-cache --max-age-days 30      # 删除 30 天前的 venv
        python main.py clean-venv-cache --max-size-mb 512      # 删除超过 512MB 的 venv
    """
    from src.tools import dependency

    if list_only:
        entries = dependency.list_venv_cache()
        if not entries:
            info_msg("venv 缓存目录为空（或尚未创建）")
        else:
            info_msg(f"venv 缓存共 {len(entries)} 项（总大小 {round(sum(e['size_mb'] for e in entries), 2)} MB）：")
            for entry in entries:
                info_msg(f"  {entry['name']}  {entry['size_mb']} MB  创建 {entry['created_at']}")
        stats = dependency.get_venv_cache_stats()
        info_msg(f"命中率统计: {stats['hits']}/{stats['total']} 次复用（hit rate {stats['hit_rate']}）")
        return

    result = dependency.clear_venv_cache(max_age_days=max_age_days, max_size_mb=max_size_mb)
    if result["removed"]:
        success_msg(
            f"已删除 {len(result['removed'])} 个 venv（释放 {result['freed_mb']} MB）：{', '.join(result['removed'])}"
        )
    else:
        info_msg("没有符合条件的 venv 需要删除")
    if result["kept"]:
        info_msg(f"保留 {len(result['kept'])} 个 venv：{', '.join(result['kept'])}")


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
    from src.datasets.dataset_loader import load_dataset

    try:
        loader = load_dataset(dataset, subset=subset)
    except Exception as e:
        error_msg(f"数据集加载失败: {e}")
        return

    tasks = loader.tasks
    info_msg(f"数据集 {dataset}（子集: {subset or '全部'}）共加载 {len(tasks)} 个任务")

    # 逐任务打印加载详情（前 N 个，对应"手动检查 2-3 个任务"的排查方法）
    _print_task_details(tasks, limit)
    # 全量质量报告（仅 SWE-bench/Defects4J 等标准数据集有意义）
    _print_quality_report(loader, tasks)
    # 2.1 源码补充流程：缺失被测源码的任务单独列出 instance_id
    _print_missing_source(loader, tasks)


def _print_task_details(tasks: list[Any], limit: int) -> None:
    """逐任务打印加载详情（前 N 个，对应"手动检查 2-3 个任务"的排查方法）。"""
    from src.datasets.dataset_loader import SWEBenchDataset

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


def _print_quality_report(loader: Any, tasks: list[Any]) -> None:
    """打印全量质量报告（仅 SWE-bench/Defects4J 等标准数据集有意义）。"""
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


def _print_missing_source(loader: Any, tasks: list[Any]) -> None:
    """列出缺失被测源码的任务（供 export_swe_bench_source.py 批量导出补全）。"""
    if hasattr(loader, "tasks_missing_source"):
        missing_source = loader.tasks_missing_source()
        if missing_source:
            warning_msg(f"⚠ 缺失被测源码任务 {len(missing_source)} 个（instance_code 兜底为 issue 文本）：")
            for task_id in missing_source[:20]:
                warning_msg(f"  {task_id}")
            if len(missing_source) > 20:
                warning_msg(f"  …（其余 {len(missing_source) - 20} 个略）")
            warning_msg(
                "  补充方式：运行 scripts/tools/export_swe_bench_source.py 按 base_commit 自动导出，"
                "再经 SWE_BENCH_ENRICHMENT 环境变量加载"
            )
        else:
            info_msg(f"✓ 全部 {len(tasks)} 个任务均含被测源码")


# ─── doctor：零 LLM 自检命令（P-3，2026-10-18）────────────────────────────────
#
# 定位：把"N 轮全功能探针矩阵（零 LLM 子集）"与"运行环境/配置就绪度"收敛为
# 一个用户可执行入口：`python main.py doctor`。
#
# 设计口径（与 O-4 CI 作业、docs/design/e2e_probe_matrix.md §5 同源）：
# - **零 LLM**：矩阵子进程强制移除 AITESTER_E2E_LLM，且不传 --include-llm；
#   真实 LLM 探针由探针框架置 skip（不消耗任何 API 配额）；环境检查纯只读
#   （不发起网络/LLM 调用、不打印任何密钥值，输出统一过脱敏层）；
# - **子进程隔离**：矩阵走 `scripts/tools/e2e_probe.py`（其内部每探针再独立
#   子进程，崩溃/挂死/污染隔离由框架保证），doctor 只负责总超时与 JSON 聚合；
# - **退出码**：矩阵 fail/error 或环境检查 fail → 1；仅 warn/skip → 0；
#   `--strict` 时 warn/skip 也返回 1（发布前/CI 严格自检用）。

_DOCTOR_SCHEMA = "aitester_doctor/1"
_DOCTOR_DEFAULT_TIMEOUT_S = 180
_DOCTOR_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DOCTOR_LLM_SCAN_LIMIT = 32
_DOCTOR_STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
_DOCTOR_STATUS_COLOR = {"pass": Colors.GREEN, "warn": Colors.YELLOW, "fail": Colors.RED}

#: 关键可选依赖（缺失 = warn，不 fail）：module 名 → (pip 安装名, 用途说明)。
_DOCTOR_OPTIONAL_DEPS: tuple[tuple[str, str, str], ...] = (
    ("z3", "z3-solver", "SMT 见证层（SPEC_SMT_ENABLE）"),
    ("coverage", "coverage", "branch 覆盖率注入/测量"),
    ("pytest", "pytest", "测试执行链路（executor）"),
    ("chromadb", "chromadb", "RAG / 语义缓存"),
    ("datasets", "datasets", "SWE-bench / ULT 数据加载"),
)


def _doctor_check(
    name: str,
    label: str,
    status: str,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一条 doctor 检查结果（统一过脱敏层，杜绝密钥进输出）。"""
    safe_status = status if status in _DOCTOR_STATUS_ICON else "warn"
    return {
        "name": name,
        "label": label,
        "status": safe_status,
        "detail": mask_sensitive_info(str(detail)),
        "evidence": evidence or {},
    }


def _doctor_check_python(version_info: tuple[int, int, int] | None = None) -> dict[str, Any]:
    """Python 版本检查（项目 requires-python >=3.12；<3.10 fail，3.10/3.11 warn）。"""
    import platform as _platform

    major, minor, micro = version_info or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    version = f"{major}.{minor}.{micro}"
    if (major, minor) >= (3, 12):
        status = "pass"
        detail = f"Python {version}（满足 requires-python >=3.12）"
    elif (major, minor) >= (3, 10):
        status = "warn"
        detail = f"Python {version} 低于项目下限 3.12（部分锁定依赖可能无 wheel；建议升级）"
    else:
        status = "fail"
        detail = f"Python {version} 不受支持（项目要求 >=3.12）"
    return _doctor_check(
        "python",
        "Python 版本",
        status,
        detail,
        {"version": version, "requires": ">=3.12", "implementation": _platform.python_implementation()},
    )


def _doctor_check_optional_deps(find_spec: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """关键可选依赖检查（缺失 = warn：只影响对应功能，不阻断零 LLM 自检）。"""
    import importlib.util as _importlib_util

    probe = find_spec or _importlib_util.find_spec
    missing: list[dict[str, str]] = []
    for module, pip_name, purpose in _DOCTOR_OPTIONAL_DEPS:
        try:
            available = probe(module) is not None
        except (ImportError, ValueError, AttributeError):
            available = False
        if not available:
            missing.append({"module": module, "install": pip_name, "purpose": purpose})
    if missing:
        missing_hint = "、".join(f"{item['module']}（pip install {item['install']}）" for item in missing)
        detail = f"缺失 {len(missing)} 项：{missing_hint}（缺失只影响对应功能，不影响零 LLM 自检；按需安装）"
        status = "warn"
    else:
        status = "pass"
        detail = f"全部 {len(_DOCTOR_OPTIONAL_DEPS)} 项可选依赖可用"
    return _doctor_check(
        "optional_dependencies",
        "可选依赖",
        status,
        detail,
        {
            "available": [m for m, _, _ in _DOCTOR_OPTIONAL_DEPS if m not in {i["module"] for i in missing}],
            "missing": missing,
        },
    )


def _doctor_check_llm_endpoints(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """LLM 端点配置存在性检查（只报数量/缺键，**绝不输出任何凭证值**）。"""
    env = os.environ if environ is None else environ
    configured = 0
    incomplete: list[int] = []
    for idx in range(1, _DOCTOR_LLM_SCAN_LIMIT + 1):
        values = [str(env.get(f"LLM_{idx}_{field}", "")).strip() for field in ("API_KEY", "BASE_URL", "MODEL_NAME")]
        if all(values):
            configured += 1
        elif any(values):
            incomplete.append(idx)
    env_local_present = os.path.isfile(os.path.join(_DOCTOR_REPO_ROOT, ".env.local"))
    parts = [f"已配置 {configured} 个 LLM 端点"]
    if incomplete:
        parts.append(f"{len(incomplete)} 个编号不完整（缺 API_KEY/BASE_URL/MODEL_NAME 之一，已跳过）")
    if not env_local_present:
        parts.append("未发现 .env.local（可复制 config.local.example 配置）")
    if configured:
        status = "pass"
    else:
        status = "warn"
        parts.append("零 LLM 自检不受影响；`python main.py run` 需要至少一个端点")
    return _doctor_check(
        "llm_endpoints",
        "LLM 端点配置",
        status,
        "；".join(parts),
        {
            "configured": configured,
            "incomplete_indices": incomplete,
            "env_local_present": env_local_present,
        },
    )


def _doctor_check_datasets(load_dataset_fn: Callable[..., Any] | None = None) -> dict[str, Any]:
    """数据集缓存可加载性检查（QuixBugs / ULT / examples；ULT 缺失属正常降级）。"""
    loader = load_dataset_fn
    if loader is None:
        from src.datasets.dataset_loader import load_dataset as _load_dataset

        loader = _load_dataset
    sizes: dict[str, int] = {}
    errors: dict[str, str] = {}
    for name in ("examples", "quixbugs", "ult"):
        try:
            dataset = loader(name)
            sizes[name] = int(getattr(dataset, "size", len(getattr(dataset, "tasks", []) or [])))
        except Exception as exc:  # 数据不可加载不阻断自检，只降级为 warn/fail 明细
            sizes[name] = 0
            errors[name] = f"{type(exc).__name__}: {str(exc)[:120]}"
    if sizes.get("examples", 0) <= 0:
        status = "fail"
    elif sizes.get("quixbugs", 0) < 41:
        status = "warn"
    else:
        status = "pass"
    parts = [
        f"examples={sizes.get('examples', 0)}",
        f"QuixBugs={sizes.get('quixbugs', 0)}",
        f"ULT={sizes.get('ult', 0) if sizes.get('ult', 0) > 0 else '未配置（正常降级）'}",
    ]
    if sizes.get("quixbugs", 0) < 41:
        parts.append("QuixBugs <41：dataset 探针将显式 skip（可克隆 QuixBugs 或设 AITESTER_QUIXBUGS_DATA）")
    if errors:
        parts.append("加载异常：" + "；".join(f"{k}（{v}）" for k, v in errors.items()))
    return _doctor_check(
        "datasets",
        "数据集缓存",
        status,
        " / ".join(parts),
        {"sizes": sizes, "errors": errors},
    )


def _doctor_check_kernel_sandbox(
    supported: bool | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """内核沙箱能力检查（supported/unsupported 明确降级，不视为失败）。"""
    if supported is None or capabilities is None:
        from src.agents.kernel_sandbox import describe_capabilities, sandbox_supported

        if supported is None:
            supported = sandbox_supported()
        if capabilities is None:
            capabilities = describe_capabilities()
    enabled_raw = os.getenv("KERNEL_SANDBOX_ENABLE", "").strip().lower()
    enabled = enabled_raw in ("1", "true", "yes", "on")
    # describe_capabilities() 返回 {"platform","supported","backends":[...],"notes"}；
    # 兼容旧 dict 形态（backend 单值）——两者都只用于展示，不影响判据。
    capabilities = capabilities or {}
    raw_backends = capabilities.get("backends")
    if isinstance(raw_backends, (list, tuple)) and raw_backends:
        backend = "、".join(str(item) for item in raw_backends)
    else:
        backend = str(capabilities.get("backend") or "none")
    platform_name = str(capabilities.get("platform") or sys.platform)
    if supported:
        status = "pass"
        detail = f"可用（backend={backend}，platform={platform_name}）；KERNEL_SANDBOX_ENABLE={str(enabled).lower()}"
    else:
        status = "warn"
        detail = (
            f"当前平台无内核沙箱后端（platform={platform_name}）：执行器按设计 fail-closed/显式 "
            f"kernel_sandbox_unavailable，不会静默裸跑；属平台能力差异"
        )
    return _doctor_check(
        "kernel_sandbox",
        "内核沙箱",
        status,
        detail,
        {"supported": bool(supported), "backend": backend, "platform": platform_name, "enabled": enabled},
    )


def _doctor_check_git(runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """工作树状态检查（HEAD sha / dirty 行数，只读；非 git 树降级 warn）。"""
    import subprocess as _subprocess

    run = runner or _subprocess.run

    def _git(*args: str) -> Any:
        return run(["git", *args], cwd=_DOCTOR_REPO_ROOT, capture_output=True, text=True, timeout=10)

    try:
        head = _git("rev-parse", "--short", "HEAD")
        dirty = _git("status", "--porcelain")
    except Exception as exc:
        return _doctor_check(
            "git",
            "工作树状态",
            "warn",
            f"git 检查不可用（{type(exc).__name__}）：非 git 工作树或未安装 git，不影响功能自检",
            {"available": False},
        )
    if getattr(head, "returncode", 1) != 0:
        stderr = (getattr(head, "stderr", "") or "").strip()[:120]
        return _doctor_check(
            "git",
            "工作树状态",
            "warn",
            f"非 git 工作树（{stderr or 'git rev-parse 失败'}），跳过 HEAD/dirty 检查",
            {"available": False},
        )
    sha = (getattr(head, "stdout", "") or "").strip()
    dirty_lines = [line for line in (getattr(dirty, "stdout", "") or "").splitlines() if line.strip()]
    status = "pass" if not dirty_lines else "warn"
    detail = f"HEAD {sha}，工作树{'干净' if not dirty_lines else f'有 {len(dirty_lines)} 项未提交改动（只读检查，不影响自检）'}"
    return _doctor_check("git", "工作树状态", status, detail, {"head": sha, "dirty_lines": len(dirty_lines)})


def _doctor_collect_checks() -> list[dict[str, Any]]:
    """执行全部环境/配置检查（单项异常降级 warn，不阻断 doctor 其余部分）。"""
    factories: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
        ("python", _doctor_check_python),
        ("optional_dependencies", _doctor_check_optional_deps),
        ("llm_endpoints", _doctor_check_llm_endpoints),
        ("datasets", _doctor_check_datasets),
        ("kernel_sandbox", _doctor_check_kernel_sandbox),
        ("git", _doctor_check_git),
    )
    checks: list[dict[str, Any]] = []
    for fallback_name, factory in factories:
        try:
            checks.append(factory())
        except Exception as exc:
            checks.append(
                _doctor_check(
                    fallback_name,
                    fallback_name,
                    "warn",
                    f"检查项异常（{type(exc).__name__}: {str(exc)[:160]}）；不影响零 LLM 自检其余部分",
                )
            )
    return checks


def _doctor_run_probe_matrix(groups: list[str], timeout_s: int) -> dict[str, Any]:
    """在隔离子进程中跑零 LLM 探针矩阵（强制零 LLM，读 JSON 汇总）。

    Returns:
        ``{"status": "ok"|"error"|"timeout", "report": <探针报告 dict>|None,
        "duration_s": float, "returncode": int|None, "detail": str, "stderr_tail": str}``。
    """
    import shutil as _shutil
    import subprocess as _subprocess
    import tempfile as _tempfile

    script = os.path.join(_DOCTOR_REPO_ROOT, "scripts", "tools", "e2e_probe.py")
    tmpdir = _tempfile.mkdtemp(prefix="aitester_doctor_")
    json_path = os.path.join(tmpdir, "e2e_probe.json")
    env = dict(os.environ)
    # 强制零 LLM：移除外部可能注入的开关（doctor 永不传 --include-llm，双保险）
    env.pop("AITESTER_E2E_LLM", None)
    env["AITESTER_LLM_CACHE"] = "0"
    cmd = [sys.executable, script, "--all", "--json-out", json_path]
    for group in groups:
        cmd.extend(["--group", group])
    started = time.perf_counter()
    try:
        try:
            proc = _subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=_DOCTOR_REPO_ROOT,
                env=env,
                check=False,
            )
        except _subprocess.TimeoutExpired as exc:
            stderr_tail = mask_sensitive_info(str(getattr(exc, "stderr", "") or "")[-400:])
            return {
                "status": "timeout",
                "report": None,
                "duration_s": round(time.perf_counter() - started, 2),
                "returncode": 124,
                "detail": f"探针矩阵执行超时（>{timeout_s}s，可用 --timeout 调大；子进程已终止）",
                "stderr_tail": stderr_tail,
            }
        duration_s = round(time.perf_counter() - started, 2)
        stderr_tail = mask_sensitive_info((proc.stderr or "")[-400:])
        report: dict[str, Any] | None = None
        if os.path.isfile(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                report = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                report = None
        if report is None:
            return {
                "status": "error",
                "report": None,
                "duration_s": duration_s,
                "returncode": proc.returncode,
                "detail": f"探针子进程未产出可解析 JSON（rc={proc.returncode}）",
                "stderr_tail": stderr_tail,
            }
        return {
            "status": "ok",
            "report": report,
            "duration_s": duration_s,
            "returncode": proc.returncode,
            "detail": "",
            "stderr_tail": stderr_tail,
        }
    except OSError as exc:
        return {
            "status": "error",
            "report": None,
            "duration_s": round(time.perf_counter() - started, 2),
            "returncode": None,
            "detail": f"无法启动探针子进程：{type(exc).__name__}: {exc}",
            "stderr_tail": "",
        }
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)


def _doctor_aggregate_probe_result(probe_result: dict[str, Any]) -> dict[str, Any]:
    """把探针子进程结果聚合为 doctor 的 matrix 段（含分组汇总/失败/跳过）。"""
    status = str(probe_result.get("status") or "error")
    matrix: dict[str, Any] = {
        "status": status,
        "duration_s": float(probe_result.get("duration_s") or 0.0),
        "returncode": probe_result.get("returncode"),
        "summary": {"pass": 0, "fail": 0, "skip": 0, "error": 0},
        "groups": {},
        "failures": [],
        "skips": [],
        "load_errors": [],
        "detail": str(probe_result.get("detail") or ""),
        "stderr_tail": str(probe_result.get("stderr_tail") or ""),
        "probe_report": None,
    }
    report = probe_result.get("report")
    if status != "ok" or not isinstance(report, dict):
        matrix["summary"] = {"pass": 0, "fail": 0, "skip": 0, "error": 1}
        return matrix
    rows = report.get("probes") or []
    summary = {"pass": 0, "fail": 0, "skip": 0, "error": 0}
    groups: dict[str, dict[str, int]] = {}
    failures: list[dict[str, Any]] = []
    skips: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_status = str(row.get("status") or "error")
        if row_status not in summary:
            row_status = "error"
        summary[row_status] += 1
        group = str(row.get("group") or "unknown")
        group_counts = groups.setdefault(group, {"pass": 0, "fail": 0, "skip": 0, "error": 0})
        group_counts[row_status] += 1
        if row_status in ("fail", "error"):
            failures.append(
                {
                    "name": str(row.get("name") or "?"),
                    "group": group,
                    "status": row_status,
                    "detail": mask_sensitive_info(str(row.get("detail") or ""))[:400],
                }
            )
        elif row_status == "skip":
            skips.append(
                {
                    "name": str(row.get("name") or "?"),
                    "detail": mask_sensitive_info(str(row.get("detail") or ""))[:300],
                    "requires_llm": bool(row.get("requires_llm")),
                }
            )
    matrix.update(
        {
            "summary": summary,
            "groups": groups,
            "failures": failures,
            "skips": skips,
            "load_errors": [mask_sensitive_info(str(item)) for item in (report.get("load_errors") or [])],
            "probe_report": report,
        }
    )
    return matrix


def _doctor_parse_groups(raw_groups: tuple[str, ...]) -> list[str]:
    """解析 --groups（支持多次传入与逗号分隔；去空/去重保序）。"""
    groups: list[str] = []
    for raw in raw_groups:
        for item in str(raw).split(","):
            group = item.strip()
            if group and group not in groups:
                groups.append(group)
    return groups


def _doctor_build_report(
    *,
    groups: list[str],
    timeout_s: int,
    strict: bool,
    checks: list[dict[str, Any]] | None = None,
    probe_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 doctor 完整报告（环境检查 + 探针矩阵聚合 + 退出码判定）。"""
    check_items = checks if checks is not None else _doctor_collect_checks()
    matrix = _doctor_aggregate_probe_result(
        probe_result if probe_result is not None else _doctor_run_probe_matrix(groups, timeout_s)
    )
    check_summary = {"pass": 0, "warn": 0, "fail": 0}
    for item in check_items:
        check_status = str(item.get("status") or "warn")
        if check_status not in check_summary:
            check_status = "warn"
        check_summary[check_status] += 1
    matrix_fail = int(matrix["summary"].get("fail", 0)) + int(matrix["summary"].get("error", 0))
    matrix_skip = int(matrix["summary"].get("skip", 0))
    fail_total = check_summary["fail"] + matrix_fail
    warn_total = check_summary["warn"]
    ok = fail_total == 0
    if fail_total > 0:
        conclusion = "fail"
    elif warn_total > 0:
        conclusion = "warn"
    else:
        conclusion = "pass"
    exit_code = 0 if ok else 1
    if strict and (warn_total > 0 or matrix_skip > 0):
        exit_code = 1
    return {
        "schema": _DOCTOR_SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cwd": os.getcwd(),
        "command": {"groups": list(groups), "timeout_s": timeout_s, "strict": bool(strict), "zero_llm": True},
        "python": {"version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"},
        "checks": check_items,
        "check_summary": check_summary,
        "matrix": matrix,
        "conclusion": conclusion,
        "ok": ok,
        "strict": bool(strict),
        "exit_code": exit_code,
    }


def _doctor_print_human(report: dict[str, Any]) -> None:
    """人类可读输出（✅/⚠️/❌ + 分组汇总 + 失败建议 + 结论）。"""
    click.echo(colorize("AITester Doctor — 零 LLM 自检", Colors.BOLD))
    click.echo(colorize("环境 / 配置：", Colors.BOLD))
    for item in report.get("checks") or []:
        status = str(item.get("status") or "warn")
        icon = _DOCTOR_STATUS_ICON.get(status, "•")
        color = _DOCTOR_STATUS_COLOR.get(status, Colors.BLUE)
        click.echo(colorize(f"  {icon} {item.get('label')}: {item.get('detail')}", color))
    click.echo(colorize("功能矩阵（零 LLM 子集；强制不设置 AITESTER_E2E_LLM，不消耗 LLM 配额）：", Colors.BOLD))
    matrix = report.get("matrix") or {}
    status = str(matrix.get("status") or "error")
    if status == "ok":
        summary = matrix.get("summary") or {}
        click.echo(
            f"  总计：✅{summary.get('pass', 0)} 通过 / ❌{summary.get('fail', 0)} 失败 / "
            f"❌{summary.get('error', 0)} 错误 / ⏭️{summary.get('skip', 0)} 跳过"
            f"（{float(matrix.get('duration_s') or 0.0):.1f}s）"
        )
        for group in sorted((matrix.get("groups") or {}).keys()):
            counts = (matrix.get("groups") or {})[group]
            click.echo(
                f"    - {group:<14s} pass={counts.get('pass', 0)} fail={counts.get('fail', 0)} "
                f"error={counts.get('error', 0)} skip={counts.get('skip', 0)}"
            )
        failures = matrix.get("failures") or []
        if failures:
            click.echo("  失败明细与建议：")
            for failure in failures[:10]:
                click.echo(
                    colorize(
                        f"    ❌ {failure.get('name')}（{failure.get('group')}，{failure.get('status')}）："
                        f"{str(failure.get('detail'))[:200]}",
                        Colors.RED,
                    )
                )
                click.echo(
                    f"       建议：单独复跑 `python scripts/tools/e2e_probe.py --name {failure.get('name')}`；"
                    "若属平台能力差异可忽略或按提示补齐依赖"
                )
        skips = matrix.get("skips") or []
        llm_skips = [item for item in skips if item.get("requires_llm")]
        other_skips = [item for item in skips if not item.get("requires_llm")]
        if llm_skips:
            click.echo(f"  ⏭️ 跳过 {len(llm_skips)} 个真实 LLM 探针（doctor 强制零 LLM；不影响自检判据）")
        if other_skips:
            names = "、".join(str(item.get("name")) for item in other_skips[:6])
            click.echo(f"  ⏭️ 环境能力差异跳过 {len(other_skips)} 个：{names}")
        load_errors = matrix.get("load_errors") or []
        if load_errors:
            click.echo(
                f"  ⚠️ 探针模块加载告警 {len(load_errors)} 条：" + "；".join(str(item)[:120] for item in load_errors[:3])
            )
    else:
        click.echo(
            colorize(
                f"  ❌ 功能矩阵执行失败（{status}）：{matrix.get('detail') or ''!s}",
                Colors.RED,
            )
        )
        if matrix.get("stderr_tail"):
            click.echo(f"     子进程 stderr（尾部）：{str(matrix.get('stderr_tail'))[:300]}")
    conclusion = str(report.get("conclusion") or "fail")
    icon = _DOCTOR_STATUS_ICON.get(conclusion, "❌")
    color = _DOCTOR_STATUS_COLOR.get(conclusion, Colors.RED)
    conclusion_text = {
        "pass": "通过（环境与零 LLM 功能矩阵均就绪）",
        "warn": "通过（存在警告项，见上）",
        "fail": "未通过（存在失败项，见上）",
    }.get(conclusion, "未通过")
    reason = ""
    if report.get("strict") and int(report.get("exit_code") or 0) != 0 and report.get("ok"):
        reason = "；--strict：warn/skip 视为不通过"
    elif report.get("strict") and int(report.get("exit_code") or 0) != 0:
        reason = "；--strict 下 warn/skip 亦算不通过"
    click.echo(colorize(f"结论：{icon} {conclusion_text}{reason}（exit={report.get('exit_code')}）", color))


@cli.command(name="doctor")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON 报告（stdout 纯 JSON，适合 CI/管道/jq）")
@click.option(
    "--groups",
    "groups",
    multiple=True,
    help="只跑指定功能组（可多次或逗号分隔，如 budget,executor；默认全部零 LLM 探针）",
)
@click.option(
    "--timeout",
    "timeout_s",
    default=_DOCTOR_DEFAULT_TIMEOUT_S,
    type=click.IntRange(min=5),
    show_default=True,
    help="探针矩阵子进程总超时（秒）",
)
@click.option("--strict", is_flag=True, help="警告/跳过也返回非零退出码（发布前严格自检）")
def doctor(json_output: bool, groups: tuple[str, ...], timeout_s: int, strict: bool) -> None:
    """零 LLM 自检：环境/配置检查 + 全功能探针矩阵（零 LLM 子集）。

    检查项：Python 版本、可选依赖（z3/coverage/pytest/chromadb/datasets）、
    LLM 端点配置存在性（只报数量/缺键，绝不输出凭证）、数据集缓存
    （QuixBugs/ULT/examples）、内核沙箱能力、git HEAD/dirty（只读）。
    随后在隔离子进程内跑 N 轮全功能探针的**零 LLM 子集**（真实 LLM 探针
    置 skip，不消耗任何 API 配额），汇总 pass/fail/skip/error。

    退出码：存在 fail/error → 1；仅 warn/skip → 0；--strict 时 warn/skip → 1。

    示例：
        python main.py doctor
        python main.py doctor --json
        python main.py doctor --groups budget,executor
        python main.py doctor --strict --timeout 240
    """
    group_list = _doctor_parse_groups(groups)
    try:
        if json_output:
            # stdout 只承载 JSON：静音 root logger 的 stdout 控制台 handler
            with _quiet_console_logs():
                report = _doctor_build_report(groups=group_list, timeout_s=timeout_s, strict=strict)
                click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            # 检查期（数据加载器等）的 INFO 日志仍落 aitester.log，但不刷屏 stdout
            with _quiet_console_logs():
                report = _doctor_build_report(groups=group_list, timeout_s=timeout_s, strict=strict)
            _doctor_print_human(report)
    except Exception as exc:  # 兜底 fail-closed：doctor 自身异常也必须非零退出且可诊断
        safe_error = mask_sensitive_info(f"{type(exc).__name__}: {exc}")
        if json_output:
            click.echo(
                json.dumps(
                    {"schema": _DOCTOR_SCHEMA, "ok": False, "error": safe_error, "exit_code": 1},
                    ensure_ascii=False,
                )
            )
        else:
            error_msg(f"doctor 执行失败：{safe_error}")
        click.get_current_context().exit(1)
        return
    click.get_current_context().exit(int(report.get("exit_code") or 0))
