"""终端输出工具：ANSI 彩色消息 + Rich 增强表格（Rich 缺失时优雅降级）。"""

from __future__ import annotations

import os
import sys
from typing import Any

import click

# 尝试导入可选依赖，提供优雅降级
# 注：进度条组件（rich.progress）由 app.py 在并发分支内自行延迟导入，此处不再转导
# 运行期符号统一为 _console（Any 类型），mypy 不报 Cannot assign to a type
# （与 src/graph/rag.py 的可选导入模式一致）
Console: Any = None
try:
    from rich.console import Console as _Console

    Console = _Console
    _console: Any = _Console
    RICH_AVAILABLE = True
except ImportError:
    # rich 未安装：保持预声明的 None（mypy 按运行期值处理），调用方先查 RICH_AVAILABLE
    _console = None
    RICH_AVAILABLE = False


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


def print_rich_table(results: list[dict[str, Any]]) -> None:
    """使用 rich 库打印格式化表格"""
    if not _rich_available():
        return

    # Table 仅在 RICH_AVAILABLE=True 时导入（见模块顶部分支），此处延迟使用
    from rich.table import Table

    console = _console()
    table = Table(title="测试执行结果", show_header=True, header_style="bold magenta")

    table.add_column("状态", style="bold", width=8)
    table.add_column("文件", max_width=40)
    table.add_column("函数", max_width=20)
    table.add_column("覆盖率", justify="right", max_width=10)
    table.add_column("迭代", justify="right", max_width=8)

    for r in results:
        status_icon = "✓" if r.get("passed") else "✗"
        status_style = "green" if r.get("passed") else "red"
        # 0.0 是合法覆盖率，用 is not None 判断缺失（falsy 会把 0% 误显示为 N/A）
        r_cov = r.get("coverage")
        coverage = f"{r_cov}%" if r_cov is not None else "N/A"

        table.add_row(
            status_icon,
            os.path.basename(r.get("file", "")),
            r.get("func", "all"),
            coverage,
            str(r.get("iterations", 0)),
            style=status_style,
        )

    console.print(table)
