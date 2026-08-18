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
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 预编译正则表达式（避免重复编译开销）─────────────────────────────────────
# 匹配 "from module_name import ..." 语句
_RE_FROM_IMPORT = re.compile(r"from\s+([\w.]+)\s+import")
# 匹配 "import module_name" 语句
_RE_IMPORT = re.compile(r"^import\s+([\w.]+)")
# 替换 from old_module import ... 为 from new_module import ...
_RE_FROM_REPLACE = re.compile(r"from\s+([\w.]+)\s+import")
# 替换 import old_module 为 import new_module
_RE_IMPORT_REPLACE = re.compile(r"^import\s+([\w.]+)\s*$", re.MULTILINE)
# 提取模块名（无扩展名）
_RE_MODULE_NAME = re.compile(r"([^/\\]+)\.py$")
# ───────────────────────────────────────────────────────────────────────────


# ─── 标准库模块集合（预定义，避免重复创建）────────────────────────────────────
_STANDARD_LIBRARIES = frozenset(
    {
        "os",
        "sys",
        "re",
        "math",
        "json",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "pathlib",
        "typing",
        "abc",
        "copy",
        "unittest",
        "pytest",
        "tempfile",
        "subprocess",
        "logging",
        "argparse",
        "dataclasses",
        "enum",
        "io",
        "string",
        "textwrap",
        "struct",
        "codecs",
        "unicodedata",
        "difflib",
        "pprint",
        "reprlib",
        "numbers",
        "cmath",
        "decimal",
        "fractions",
        "random",
        "statistics",
        "array",
        "bisect",
        "heapq",
        "queue",
        "types",
        "contextlib",
        "operator",
        "pickle",
        "shelve",
        "dbm",
        "sqlite3",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
        "zipimport",
        "concurrent",
        "multiprocessing",
        "threading",
        "signal",
        "mmap",
        "ctypes",
        "select",
        "socket",
        "ssl",
        "urllib",
        "http",
        "email",
        "html",
        "xml",
        "ipaddress",
        "webbrowser",
        "cgi",
        "cgitb",
        "wsgiref",
        "venv",
        "shutil",
        "diskcache",
        "glob",
        "fnmatch",
        "stat",
        "filecmp",
        "secrets",
    }
)


class ExecutorAgent:
    """
    测试执行器：在本地或 Docker 容器中运行 pytest 测试。
    注意：use_docker 参数目前保留用于未来扩展，实际执行始终在本地进行。

    属性:
        timeout: 单次测试最大运行时间（秒），可通过 EXECUTION_TIMEOUT 环境变量配置。
        use_docker: 是否使用 Docker 隔离执行（当前未启用，保留接口）。
    """

    def __init__(self, timeout: int = 30, use_docker: bool = False) -> None:
        # timeout 从参数传入，默认 30 秒
        self.timeout = timeout
        self.use_docker = use_docker

    def execute(
        self,
        test_code: str,
        target_file: str,
        target_function: str | None = None,
    ) -> dict[str, Any]:
        """
        执行 pytest 测试并返回结果。
        失败时自动重试一次（防止偶发性环境干扰导致误判），最多尝试 2 次。

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
            - error_info (dict): 错误详情（可选）。
        """
        # 获取项目根目录（本文件在 src/agents/ 下，根目录为其上两级）
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 被测代码所在目录，用于设置 PYTHONPATH（使 pytest 能找到被测模块）
        target_dir = os.path.dirname(os.path.abspath(target_file))

        # P0 改进：自动检测并修复模块导入路径
        # 分析测试代码中的 import 语句，动态添加 sys.path
        fixed_test_code = self._auto_fix_imports(test_code, target_file, project_root)
        if fixed_test_code != test_code:
            logger.info("已自动修复模块导入路径")

        # 将测试代码写入临时文件，便于 pytest 执行
        # delete=False：py.test 需要文件存在于磁盘，不能是内存对象
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(fixed_test_code)
            test_file = f.name

        try:
            # 复制当前环境变量，并追加被测代码目录到 PYTHONPATH
            # 这样 pytest 在执行测试时能 import 被测模块
            env = os.environ.copy()
            env["PYTHONPATH"] = target_dir + os.pathsep + env.get("PYTHONPATH", "")

            python_path = sys.executable  # 使用当前 Python 解释器
            # 构建 pytest 命令
            cmd = [
                python_path,
                "-m",
                "pytest",
                test_file,
                "-v",  # 详细输出（显示每个用例的 PASS/FAIL）
                "--tb=short",  # 缩短 traceback（只显示关键错误位置）
                f"--cov={target_dir}",  # 只收集目标目录的覆盖率
                "--cov-report=term",  # 终端输出覆盖率报告
            ]
            if target_function:
                # 若指定了目标函数，用 -k 过滤只运行匹配的测试
                cmd.extend(["-k", target_function])

            # 带重试的执行逻辑：最多尝试 2 次
            last_output = ""
            last_result = None
            max_attempts = 2
            for attempt in range(max_attempts):
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
                except subprocess.TimeoutExpired as e:
                    # 超时时不重试：超时意味着被测代码有死循环，重试也不会改善
                    error_msg = f"测试执行超时（>{self.timeout}s）"
                    logger.error("测试执行超时（>%ds）: %s", self.timeout, e)
                    # 返回包含详细错误信息的字典
                    return {
                        "passed": False,
                        "output": error_msg,
                        "coverage": 0.0,
                        "failed_cases": [],
                        "error_info": {
                            "type": "timeout",
                            "message": error_msg,
                            "timeout_seconds": self.timeout,
                            "command": " ".join(cmd[:5]) if len(cmd) > 5 else " ".join(cmd),
                        },
                    }
                except FileNotFoundError as e:
                    # Python 解释器或 pytest 未找到
                    error_msg = "执行环境错误（找不到 pytest 或 Python 解释器）"
                    logger.error("执行环境错误（找不到 pytest）: %s", e)
                    return {
                        "passed": False,
                        "output": error_msg,
                        "coverage": 0.0,
                        "failed_cases": [],
                        "error_info": {
                            "type": "file_not_found",
                            "message": error_msg,
                            "detail": str(e),
                        },
                    }
                except PermissionError as e:
                    # 权限不足，无法执行文件
                    error_msg = "权限不足，无法执行测试文件"
                    logger.error("权限错误: %s", e)
                    return {
                        "passed": False,
                        "output": error_msg,
                        "coverage": 0.0,
                        "failed_cases": [],
                        "error_info": {
                            "type": "permission_error",
                            "message": error_msg,
                            "file_path": str(e.filename) if hasattr(e, "filename") else "",
                        },
                    }
                except Exception as e:
                    # 其他未知异常（网络、子进程启动失败等）
                    error_msg = f"测试执行异常: {type(e).__name__}: {e}"
                    logger.error("测试执行异常: %s", e)
                    last_output = error_msg
                    last_result = None
                    break

            output = last_output
            # 通过 returncode == 0 判断是否全部测试通过
            passed = last_result is not None and last_result.returncode == 0

            # 解析覆盖率和失败用例
            coverage = self._parse_coverage(output)
            failed_cases = self._parse_failed_cases(output)

            # 构建返回结果，包含详细的错误信息（如果有）
            result_dict = {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }

            # 如果有错误信息，添加到结果中
            if last_result and last_result.returncode != 0:
                result_dict["error_info"] = {
                    "type": "test_failure",
                    "returncode": last_result.returncode,
                    "has_syntax_error": "SyntaxError" in output or "ImportError" in output,
                    "has_runtime_error": any(e in output for e in ["TypeError", "ValueError", "ZeroDivisionError"]),
                }

            return result_dict
        finally:
            # 清理临时文件，避免磁盘垃圾堆积
            try:
                if os.path.exists(test_file):
                    os.unlink(test_file)
                    logger.debug("已清理临时测试文件: %s", test_file)
            except OSError as e:
                # 文件清理失败不影响测试结果，仅记录警告
                logger.warning("清理临时文件失败: %s", e)

    @staticmethod
    def _extract_module_name_from_file(target_file: str) -> str:
        """
        从文件路径提取模块名（不含扩展名）。

        Args:
            target_file: 被测代码文件路径。

        Returns:
            模块名称（如 'calculator' 从 'examples/calculator.py'）。
        """
        # 使用预编译的正则表达式提取模块名
        match = _RE_MODULE_NAME.search(target_file)
        if match:
            return match.group(1)
        # 备用方案：使用 os.path.splitext
        return os.path.splitext(os.path.basename(target_file))[0]

    @staticmethod
    @lru_cache(maxsize=256)
    def _cached_search_module_path(module_name: str, root_path_str: str, max_depth: int) -> tuple:
        """
        缓存版本的模块路径搜索（优化高频调用场景）。

        使用 LRU 缓存避免重复搜索相同模块，显著提升性能。

        Args:
            module_name: 模块名称（不含 .py 后缀）。
            root_path_str: 项目根目录路径（字符串形式，用于缓存键）。
            max_depth: 最大搜索深度，默认 3 层。

        Returns:
            匹配的目录路径元组（去重）。
        """
        root_path = Path(root_path_str)
        matched_dirs = set()

        # 策略 1：直接匹配文件名
        py_file = root_path / f"{module_name}.py"
        if py_file.exists():
            matched_dirs.add(str(py_file.parent))
            return tuple(matched_dirs)

        # 策略 2：检查常见子目录
        common_dirs = ["src", "lib", "tests", "."]
        for common_dir in common_dirs:
            candidate = root_path / common_dir / f"{module_name}.py"
            if candidate.exists():
                matched_dirs.add(str(candidate.parent))
                return tuple(matched_dirs)

        # 策略 3：深度限制的 rglob 搜索
        for found_file in root_path.rglob(f"{module_name}.py"):
            rel_parts = found_file.relative_to(root_path).parts
            if len(rel_parts) <= max_depth:
                matched_dirs.add(str(found_file.parent))
                break

        # 策略 4：查找包目录
        pkg_dir = root_path / module_name
        if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
            matched_dirs.add(str(pkg_dir))

        return tuple(matched_dirs)

    @staticmethod
    def _auto_fix_imports(test_code: str, target_file: str, project_root: str) -> str:
        """
        自动修复模块导入路径（优化版）

        分析测试代码中的 import 语句，动态添加 sys.path，解决 ModuleNotFoundError。
        支持两种场景：
        1. 模块名与文件名匹配：添加对应的目录到 sys.path
        2. 模块名与文件名不匹配：替换导入语句中的模块名为实际文件名

        Args:
            test_code: 原始测试代码。
            target_file: 被测代码文件路径。
            project_root: 项目根目录。

        Returns:
            修复后的测试代码（如无需修改则返回原代码）。
        """
        # 提取所有 import 语句（排除标准库和相对导入）
        imports = []

        # 使用预编译的正则表达式进行匹配
        for line in test_code.split("\n"):
            line = line.strip()
            match1 = _RE_FROM_IMPORT.match(line)
            match2 = _RE_IMPORT.match(line)
            if match1:
                module_name = match1.group(1)
                # 只记录非标准库且非相对导入的模块
                top_level = module_name.split(".")[0]
                if not module_name.startswith(".") and top_level not in _STANDARD_LIBRARIES:
                    imports.append(module_name)
            elif match2:
                module_name = match2.group(1)
                # 只记录非标准库且非相对导入的模块
                top_level = module_name.split(".")[0]
                if not module_name.startswith(".") and top_level not in _STANDARD_LIBRARIES:
                    imports.append(module_name)

        if not imports:
            return test_code

        # 获取被测文件的实际模块名
        actual_module_name = ExecutorAgent._extract_module_name_from_file(target_file)
        module_dirs = set()
        needs_replacement = False

        # 限制 rglob 搜索深度，避免大型项目遍历过慢（默认最多 3 层）
        _MAX_SEARCH_DEPTH = 3

        for module_name in imports:
            # 使用缓存的搜索函数（优化高频调用场景）
            found_dirs = ExecutorAgent._cached_search_module_path(module_name, project_root, _MAX_SEARCH_DEPTH)

            if found_dirs:
                # 模块存在，添加其目录到 sys.path
                module_dirs.update(found_dirs)
            else:
                # 模块不存在，检查是否需要替换为实际模块名
                if module_name != actual_module_name:
                    needs_replacement = True
                    # 添加被测文件所在目录，以便导入实际模块
                    target_dir = os.path.dirname(os.path.abspath(target_file))
                    module_dirs.add(target_dir)

        if not module_dirs and not needs_replacement:
            return test_code

        # 生成 sys.path 修改代码
        sys_path_code = "\n".join([f"import sys\nsys.path.insert(0, {repr(d)})" for d in sorted(module_dirs)])

        fixed_code = test_code

        # 如果需要替换模块名，执行导入语句替换
        if needs_replacement:
            # 替换 from module_name import ... 为 from actual_module_name import ...
            # 只替换测试代码中引用的模块名，不影响标准库
            for imported_module in imports:
                if imported_module != actual_module_name:
                    # 使用预编译的正则表达式进行替换
                    fixed_code = _RE_FROM_REPLACE.sub(rf"from {actual_module_name} import", fixed_code)
                    # 替换 import imported_module（仅匹配独立的 import 语句）
                    fixed_code = _RE_IMPORT_REPLACE.sub(f"import {actual_module_name}", fixed_code)
            if imports:
                logger.info(f"模块名不匹配，已将导入从 '{imports[0]}' 替换为 '{actual_module_name}'")

        # 在测试代码开头插入路径修复
        if sys_path_code:
            fixed_code = f"""{sys_path_code}

{fixed_code}
"""

        return fixed_code

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
    def _parse_failed_cases(output: str) -> list[dict[str, str]]:
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
                after_match = line[m.end() :].strip()
                if after_match:
                    error_lines.append(after_match)
                j = i + 1
                while j < len(lines):
                    l = lines[j]
                    if "FAILED" in l and ".py::" in l:
                        break  # 遇到下一个失败用例
                    if "======" in l and "short" in l:
                        break  # 遇到分隔线
                    if l.strip() and not l.startswith("WARNING"):
                        error_lines.append(l)
                    j += 1
                if error_lines:
                    failed.append(
                        {
                            "name": case_name,
                            "error": "\n".join(error_lines),
                        }
                    )
                i = j
            else:
                i += 1
        return failed
