#!/usr/bin/env python3
"""
统计显著性检验分析脚本（兼容入口）

本文件此前的独立实现（配对 t 检验 + Cohen's d + Markdown 报告）已收敛到
statistical_analysis.py——两份实现逻辑重复，且旧版 statistical_analysis.py
按位置配对（结果顺序不一致时错配任务），规范实现统一为按 task_id 配对。

保留本入口仅为兼容既有调用习惯（论文提交包、复现脚本）：
    python experiments/run_statistical_test.py
等价于：
    python experiments/statistical_analysis.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.statistical_analysis import run_all_statistics  # noqa: E402

if __name__ == "__main__":
    run_all_statistics("experiments/results", "experiments/statistical_report.md")
