"""
测试执行器智能体，在隔离环境中运行测试并捕获结果。
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict
import sys


class ExecutorAgent:
    """
    测试执行器：在本地或 Docker 容器中运行 pytest 测试。

    属性:
        timeout: 单次测试最大运行时间（秒）。
        use_docker: 是否使用 Docker 隔离执行。
    """

    def __init__(self, timeout: int = 30, use_docker: bool = False) -> None:
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
            subprocess.TimeoutExpired: 测试超时。
        """
        import tempfile

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.dirname(os.path.abspath(target_file))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            test_file = f.name

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = target_dir + os.pathsep + env.get("PYTHONPATH", "")

            # 使用当前 Python 解释器路径，避免依赖系统 python 命令
            python_path = sys.executable
            cmd = [
                python_path, "-m", "pytest",
                test_file,
                "-v",
                "--tb=short",
            ]
            if target_function:
                cmd.append(f"-k {target_function}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=project_root,
                env=env,
            )

            output = result.stdout + result.stderr
            passed = result.returncode == 0

            coverage = self._parse_coverage(output)
            failed_cases = self._parse_failed_cases(output)

            return {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }
        finally:
            os.unlink(test_file)

    @staticmethod
    def _parse_coverage(output: str) -> float:
        """
        从 pytest-cov 输出中解析覆盖率百分比。

        Args:
            output: pytest 输出文本。

        Returns:
            覆盖率百分比（0-100）。
        """
        for line in output.splitlines():
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

        Args:
            output: pytest 输出文本。

        Returns:
            失败用例列表，每个元素为 {"name": str, "error": str}。
        """
        failed = []
        lines = output.splitlines()
        pattern = re.compile(r"FAILED\s+(.+?\.py::\S+)")
        i = 0
        while i < len(lines):
            line = lines[i]
            m = pattern.search(line)
            if m:
                case_name = m.group(1).strip()
                error_lines = []
                j = i + 1
                while j < len(lines):
                    l = lines[j]
                    if "FAILED" in l and ".py::" in l:
                        break
                    if "======" in l and "short" in l:
                        break
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
