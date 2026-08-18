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
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.dirname(os.path.abspath(target_file))

        fixed_test_code = self._auto_fix_imports(test_code, target_file, project_root)
        if fixed_test_code != test_code:
            logger.info("已自动修复模块导入路径")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(fixed_test_code)
            test_file = f.name

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = target_dir + os.pathsep + env.get("PYTHONPATH", "")

            python_path = sys.executable
            cmd = [
                python_path,
                "-m",
                "pytest",
                test_file,
                "-v",
                "--tb=short",
                f"--cov={target_dir}",
                "--cov-report=term",
            ]
            if target_function:
                cmd.extend(["-k", target_function])

            output, last_result = self._run_pytest_with_retry(cmd, env, project_root)
            # 检查是否需要立即返回（超时/环境问题）
            if isinstance(last_result, tuple) and last_result[0] == "EARLY_RETURN":
                return {
                    "passed": False,
                    "output": output,
                    "coverage": 0.0,
                    "failed_cases": [],
                    "error_info": last_result[1],
                }

            coverage = self._parse_coverage(output)
            failed_cases = self._parse_failed_cases(output)
            passed = last_result is not None and last_result.returncode == 0

            result_dict = {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }

            if last_result and last_result.returncode != 0:
                result_dict["error_info"] = self._build_error_info(last_result, output)

            return result_dict
        finally:
            self._cleanup_temp_file(test_file)

    @staticmethod
    def _build_error_info(last_result, output: str) -> dict:
        """根据测试结果构建错误信息字典。"""
        return {
            "type": "test_failure",
            "returncode": last_result.returncode,
            "has_syntax_error": "SyntaxError" in output or "ImportError" in output,
            "has_runtime_error": any(e in output for e in ["TypeError", "ValueError", "ZeroDivisionError"]),
        }

    @staticmethod
    def _cleanup_temp_file(test_file: str) -> None:
        """清理临时测试文件，失败时仅记录警告。"""
        try:
            if os.path.exists(test_file):
                os.unlink(test_file)
                logger.debug("已清理临时测试文件: %s", test_file)
        except OSError as e:
            logger.warning("清理临时文件失败: %s", e)

    def _run_pytest_with_retry(self, cmd: list, env: dict, project_root: str) -> tuple[str, Any]:
        """
        带重试的 pytest 执行逻辑，最多尝试 2 次。
        超时/环境问题直接返回 error 字典，其他异常仅记录日志并返回空结果。

        Returns:
            (output, last_result) 元组，last_result 为 subprocess.CompletedProcess 或 None。
        """
        max_attempts = 2
        last_output = ""
        last_result = None

        for attempt in range(max_attempts):
            try:
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
                    break
                logger.warning("第 %d 次执行失败，尝试重试...", attempt + 1)
            except subprocess.TimeoutExpired as e:
                error_msg = f"测试执行超时（>{self.timeout}s）"
                logger.error("测试执行超时（>%ds）: %s", self.timeout, e)
                error_info = {
                    "type": "timeout",
                    "message": error_msg,
                    "timeout_seconds": self.timeout,
                    "command": " ".join(cmd[:5]) if len(cmd) > 5 else " ".join(cmd),
                }
                # 超时/环境错误需由调用方直接 return，这里用特殊标记
                return last_output, ("EARLY_RETURN", error_info)
            except FileNotFoundError as e:
                error_msg = "执行环境错误（找不到 pytest 或 Python 解释器）"
                logger.error("执行环境错误（找不到 pytest）: %s", e)
                return last_output, (
                    "EARLY_RETURN",
                    {
                        "type": "file_not_found",
                        "message": error_msg,
                        "detail": str(e),
                    },
                )
            except PermissionError as e:
                error_msg = "权限不足，无法执行测试文件"
                logger.error("权限错误: %s", e)
                return last_output, (
                    "EARLY_RETURN",
                    {
                        "type": "permission_error",
                        "message": error_msg,
                        "file_path": str(e.filename) if hasattr(e, "filename") else "",
                    },
                )
            except Exception as e:
                error_msg = f"测试执行异常: {type(e).__name__}: {e}"
                logger.error("测试执行异常: %s", e)
                last_output = error_msg
                last_result = None
                break

        return last_output, last_result

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
        imports = ExecutorAgent._extract_imports(test_code)
        if not imports:
            return test_code

        actual_module_name = ExecutorAgent._extract_module_name_from_file(target_file)
        module_dirs, needs_replacement = ExecutorAgent._resolve_module_paths(
            imports, actual_module_name, project_root, target_file
        )

        if not module_dirs and not needs_replacement:
            return test_code

        sys_path_code = ExecutorAgent._build_sys_path_code(module_dirs)
        fixed_code = ExecutorAgent._apply_import_replacements(test_code, imports, actual_module_name, needs_replacement)

        if sys_path_code:
            fixed_code = f"{sys_path_code}\n\n{fixed_code}\n"

        return fixed_code

    @staticmethod
    def _extract_imports(test_code: str) -> list[str]:
        """提取测试代码中的非标准库导入模块名（排除相对导入）。"""
        imports = []
        for line in test_code.split("\n"):
            line = line.strip()
            match1 = _RE_FROM_IMPORT.match(line)
            match2 = _RE_IMPORT.match(line)
            if match1 or match2:
                module_name = (match1 or match2).group(1)
                top_level = module_name.split(".")[0]
                if not module_name.startswith(".") and top_level not in _STANDARD_LIBRARIES:
                    imports.append(module_name)
        return imports

    @staticmethod
    def _resolve_module_paths(
        imports: list[str], actual_module_name: str, project_root: str, target_file: str
    ) -> tuple[set, bool]:
        """根据导入列表解析模块路径，返回 (module_dirs, needs_replacement)。"""
        module_dirs = set()
        needs_replacement = False
        _MAX_SEARCH_DEPTH = 3

        for module_name in imports:
            found_dirs = ExecutorAgent._cached_search_module_path(module_name, project_root, _MAX_SEARCH_DEPTH)
            if found_dirs:
                module_dirs.update(found_dirs)
            elif module_name != actual_module_name:
                needs_replacement = True
                target_dir = os.path.dirname(os.path.abspath(target_file))
                module_dirs.add(target_dir)

        return module_dirs, needs_replacement

    @staticmethod
    def _build_sys_path_code(module_dirs: set) -> str:
        """生成 sys.path 修改代码。"""
        return "\n".join([f"import sys\nsys.path.insert(0, {repr(d)})" for d in sorted(module_dirs)])

    @staticmethod
    def _apply_import_replacements(
        test_code: str, imports: list[str], actual_module_name: str, needs_replacement: bool
    ) -> str:
        """对测试代码应用导入替换，返回修改后的代码。"""
        fixed_code = test_code
        if needs_replacement and imports:
            for imported_module in imports:
                if imported_module != actual_module_name:
                    fixed_code = _RE_FROM_REPLACE.sub(rf"from {actual_module_name} import", fixed_code)
                    fixed_code = _RE_IMPORT_REPLACE.sub(f"import {actual_module_name}", fixed_code)
            logger.info(f"模块名不匹配，已将导入从 '{imports[0]}' 替换为 '{actual_module_name}'")
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
        pattern = re.compile(r"FAILED\s+(.+?\.py::\S+)")

        for i, line in enumerate(lines):
            m = pattern.search(line)
            if m:
                case_name = m.group(1).strip()
                error_lines = ExecutorAgent._collect_error_lines(lines, i, m.end())
                if error_lines:
                    failed.append({"name": case_name, "error": "\n".join(error_lines)})

        return failed

    @staticmethod
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
