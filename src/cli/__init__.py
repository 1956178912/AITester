"""
CLI 子包：click 命令组、任务执行与终端输出。

导入本包即完成日志配置（StreamHandler + FileHandler）并暴露 click 命令组 ``cli``。
根目录的 main.py 仅作为薄入口复用本包，保持 `python main.py ...` 与
setup.py 控制台脚本 `aitester=main:cli` 两种入口行为不变。
"""

from src.cli.app import cli

__all__ = ["cli"]
