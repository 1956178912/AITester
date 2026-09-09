"""
AITester CLI 入口模块（薄封装）。

命令行实现位于 src/cli/ 子包（src/cli/app.py + src/cli/output.py）。
本文件仅保留顶层入口，使以下用法继续可用：
    python main.py run examples/calculator.py --func divide
    python main.py run examples/*.py --parallel=2
    python main.py list-examples
    setup.py 控制台脚本 aite
"""

from src.cli.app import cli

__all__ = ["cli"]

if __name__ == "__main__":
    cli()
