"""
测试执行器模块：在隔离环境中运行 pytest 测试并捕获结果。

支持超时配置、重试机制和覆盖率报告解析。
默认在本地环境执行，Docker 模式需要额外配置。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ─── 魔数常量（统一管理，便于后续调整）─────────────────────────────────────
# pytest 执行时的默认超时秒数：单次测试最长运行时间
_DEFAULT_EXECUTION_TIMEOUT_SECONDS = 30
# pytest 重试最大次数（首次失败后额外重试 1 次，共 2 次尝试）
_MAX_EXECUTION_ATTEMPTS = 2
# 分隔线标记：用于识别 pytest --tb=short 输出中的错误详情分隔区
_TB_SEPARATOR = "======"
# ───────────────────────────────────────────────────────────────────────────


class ExecutorAgent:
    """
    测试执行器：在本地或 Docker 容器中运行 pytest 测试。
    注意：use_docker 参数目前保留用于未来扩展，实际执行始终在本地进行。

    属性:
        timeout: 单次测试最大运行时间（秒），可通过 EXECUTION_TIMEOUT 环境变量配置。
        use_docker: 是否使用 Docker 隔离执行（当前未启用，保留接口）。
    """

    def __init__(self, timeout: int = _DEFAULT_EXECUTION_TIMEOUT_SECONDS,
                 use_docker: bool = False) -> None:
        # timeout 从参数传入，默认 _DEFAULT_EXECUTION_TIMEOUT_SECONDS 秒
        self.timeout = timeout
        self.use_docker = use_docker

    def execute(
        self,
        test_code: str,
        target_file: str,
        target_function: str | None = None,
    ) -> Dict[str, Any]:
        """
        执行 pytest 测试并返回结果。
        失败时自动重试一次（防止偶发性环境干扰导致误判），最多尝试 _MAX_EXECUTION_ATTEMPTS 次。

        Args:
            test_code: pytest 测试代码字符串。
            target_file: 被测代码文件路径。
            target_function: 指定要运行的测试函数名（可选）。

        Returns:
            包含以下键的字典：
            - passed (bool): 是否全部测试通过。
            - output (str): 测试输出文本。
            - coverage (float): 代码覆盖率（如有）。
            - failed_cases (List[dict]): 失败的用例列表。

        Raises:
            subprocess.TimeoutExpired: 测试超时（此时不重试，直接返回超时标记）。
        """
        # 获取项目根目录（本文件在 src/agents/ 下，根目录为其上两级）
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 被测代码所在目录，用于设置 PYTHONPATH（使 pytest 能找到被测模块）
        target_dir = os.path.dirname(os.path.abspath(target_file))

        # 将测试代码写入临时文件，便于 pytest 执行
        # delete=False：py.test 需要文件存在于磁盘，不能是内存对象
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            test_file = f.name

        try:
            # 复制当前环境变量，并追加被测代码目录到 PYTHONPATH
            # 这样 pytest 在执行测试时能 import 被测模块
            env = os.environ.copy()
            env["PYTHONPATH"] = target_dir + os.pathsep + env.get("PYTHONPATH", "")

            python_path = sys.executable  # 使用当前 Python 解释器
            # 构建 pytest 命令
            cmd = [
                python_path, "-m", "pytest",
                test_file,
                "-v",                   # 详细输出（显示每个用例的 PASS/FAIL）
                "--tb=short",           # 缩短 traceback（只显示关键错误位置）
                f"--cov={target_dir}",  # 只收集目标目录的覆盖率
                "--cov-report=term",    # 终端输出覆盖率报告
            ]
            if target_function:
                # 若指定了目标函数，用 -k 过滤只运行匹配的测试
                cmd.append(f"-k {target_function}")

            # 带重试的执行逻辑：最多尝试 _MAX_EXECUTION_ATTEMPTS 次
            last_output = ""
            last_result = None
            for attempt in range(_MAX_EXECUTION_ATTEMPTS):
                try:
                    # 执行 pytest，捕获 stdout 和 stderr
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        cwd=project_root,
                        env=env,
                    )
                    last_result = result
                    last_output = result.stdout + result.stderr
                    if result.returncode == 0:
                        break  # 成功则提前退出，不浪费重试次数
                    logger.warning("第 %d 次执行失败，尝试重试...", attempt + 1)
                except subprocess.TimeoutExpired:
                    # 超时时不重试：超时意味着被测代码有死循环，重试也不会改善
                    last_output = f"超时（>{self.timeout}s）"
                    last_result = None
                    break

            output = last_output
            # 通过 returncode == 0 判断是否全部测试通过
            passed = last_result is not None and last_result.returncode == 0

            # 解析覆盖率和失败用例
            coverage = self._parse_coverage(output)
            failed_cases = self._parse_failed_cases(output)

            return {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }
        finally:
            # 清理临时文件，避免磁盘垃圾堆积
            os.unlink(test_file)

    @staticmethod
    def _parse_coverage(output: str) -> float:
        """
        从 pytest-cov 输出中解析覆盖率百分比。
        pytest-cov 会在输出末尾打印类似 "TOTAL  xxxxx  85%" 的行。

        Args:
            output: pytest 输出文本。

        Returns:
            覆盖率百分比（0-100）。未找到覆盖率信息时返回 0.0。
        """
        for line in output.splitlines():
            # 匹配 "TOTAL  xxxxx  85%" 格式，捕获百分比数字
            m = re.search(r"TOTAL\s+.+?(\d+)%", line)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return 0.0

    @staticmethod
    def _parse_failed_cases(output: str) -> list[Dict[str, str]]:
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
        # 匹配 "FAILED test_file.py::test_func_name" 行
        pattern = re.compile(r"FAILED\s+(.+?\.py::\S+)")
        i = 0
        while i < len(lines):
            line = lines[i]
            m = pattern.search(line)
            if m:
                case_name = m.group(1).strip()
                # 收集该用例的错误信息（直到下一个 FAILED 或分隔线）
                error_lines = []
                # 先提取 FAILED 行本身的错误信息（如 "- AssertionError: ..."）
                after_match = line[m.end():].strip()
                if after_match:
                    error_lines.append(after_match)
                j = i + 1
                while j < len(lines):
                    l = lines[j]
                    if "FAILED" in l and ".py::" in l:
                        break  # 遇到下一个失败用例
                    if _TB_SEPARATOR in l and "short" in l:
                        break  # 遇到分隔线
                    if l.strip() and not l.startswith("WARNING"):
                        error_lines.append(l)
                    j += 1
                if error_lines:
                    failed.append({
                        "name": case_name,
                        "error": "\n".join(error_lines),
                    })
                i = j
            else:
                i += 1
        return failed
