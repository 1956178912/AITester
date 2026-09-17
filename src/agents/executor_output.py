"""
执行结果解析：pytest 输出的覆盖率、失败用例提取与错误信息构建。

拆分自 executor.py（结构优化轮次）：三条执行链路（本地 / venv 沙箱 / Docker）
共用的输出解析逻辑集中于此，函数均为纯函数（_build_error_info 以 CompletedProcess
的鸭子类型对象为入参，签名与返回值不变）。
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ─── 预编译正则表达式（避免重复编译开销）─────────────────────────────────────
# 匹配 pytest-cov 输出的 TOTAL 行中的覆盖率百分比
_RE_COVERAGE_TOTAL = re.compile(r"TOTAL\s+.+?(\d+)%")
# 匹配 pytest 输出中 "FAILED test_file.py::test_func" 行（提取失败用例名）
# 预编译到模块级：parse_failed_cases 每次执行测试都要调用，
# 避免每次重新编译正则
_RE_FAILED_CASE = re.compile(r"FAILED\s+(.+?\.py::\S+)")
# ───────────────────────────────────────────────────────────────────────────


def build_error_info(last_result: subprocess.CompletedProcess[str], output: str) -> dict[str, Any]:
    """根据测试结果构建错误信息字典。"""
    return {
        "type": "test_failure",
        "returncode": last_result.returncode,
        "has_syntax_error": "SyntaxError" in output or "ImportError" in output,
        "has_runtime_error": any(e in output for e in ["TypeError", "ValueError", "ZeroDivisionError"]),
    }


def parse_coverage(output: str) -> float:
    """
    从 pytest-cov 输出中解析覆盖率百分比。
    pytest-cov 会在输出末尾打印类似 "TOTAL  xxxxx  85%" 的行。

    Args:
        output: pytest 输出文本。

    Returns:
        覆盖率百分比（0-100）。未找到覆盖率信息时返回 0.0。
    """
    lines = output.splitlines()
    # 优先只扫描 TOTAL 汇总行（pytest-cov 覆盖率结果的权威来源），
    # 避免逐行全量正则匹配的性能开销
    total_lines = [line for line in lines if line.startswith("TOTAL")]
    # 兼容旧版 pytest-cov 的小写 total 行格式
    if not total_lines:
        total_lines = [line for line in lines if line.startswith("total")]
    if not total_lines:
        total_lines = lines  # 极端兜底：保持与原行为一致的全文扫描
    for line in total_lines:
        # 匹配 "TOTAL  xxxxx  85%" 格式，捕获百分比数字
        m = _RE_COVERAGE_TOTAL.search(line)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return 0.0


def parse_failed_cases(output: str) -> list[dict[str, str]]:
    """
    从 pytest 输出中解析失败的用例列表。
    pytest 输出格式：FAILED test_file.py::test_func_name

    解析逻辑：
    1. 扫描每行，找到 "FAILED ... .py::..." 模式的行
    2. 提取失败用例名称
    3. 向后收集错误详情，直到遇到下一个 FAILED 行或分隔线（"======" + "short"）

    Args:
        output: pytest 输出文本。

    Returns:
        失败用例列表，每个元素为 {"name": str, "error": str}。
    """
    failed = []
    lines = output.splitlines()
    # 使用模块级预编译正则（_RE_FAILED_CASE）
    for i, line in enumerate(lines):
        m = _RE_FAILED_CASE.search(line)
        if m:
            case_name = m.group(1).strip()
            error_lines = _collect_error_lines(lines, i, m.end())
            if error_lines:
                failed.append({"name": case_name, "error": "\n".join(error_lines)})

    return failed


def _collect_error_lines(lines: list[str], start_idx: int, match_end: int) -> list[str]:
    """从指定位置收集错误行，直到遇到下一个 FAILED 行或分隔线。"""
    error_lines = []
    # 先提取 FAILED 行本身的错误信息（如 "- AssertionError: ..."）
    after_match = lines[start_idx][match_end:].strip()
    if after_match:
        error_lines.append(after_match)

    for j in range(start_idx + 1, len(lines)):
        line_content = lines[j]
        if "FAILED" in line_content and ".py::" in line_content:
            break  # 遇到下一个失败用例
        if "======" in line_content and "short" in line_content:
            break  # 遇到分隔线
        if line_content.strip() and not line_content.startswith("WARNING"):
            error_lines.append(line_content)

    return error_lines
