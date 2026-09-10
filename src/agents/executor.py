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
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 预编译正则表达式（避免重复编译开销）─────────────────────────────────────
# 匹配 "from module_name import ..." 语句
_RE_FROM_IMPORT = re.compile(r"from\s+([\w.]+)\s+import")
# 匹配 "import module_name" 语句
_RE_IMPORT = re.compile(r"^import\s+([\w.]+)")
# 提取模块名（无扩展名）
_RE_MODULE_NAME = re.compile(r"([^/\\]+)\.py$")
# 匹配 pytest-cov 输出的 TOTAL 行中的覆盖率百分比
_RE_COVERAGE_TOTAL = re.compile(r"TOTAL\s+.+?(\d+)%")
# 匹配 pytest 输出中 "FAILED test_file.py::test_func" 行（提取失败用例名）
# 预编译到模块级：_parse_failed_cases 每次执行测试都要调用，
# 避免每次重新编译正则
_RE_FAILED_CASE = re.compile(r"FAILED\s+(.+?\.py::\S+)")
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
    测试执行器：在本地或隔离沙箱中运行 pytest 测试。
    注意：use_docker 参数目前保留用于未来扩展，实际执行始终在本地进行。

    隔离执行（P1 依赖隔离优化）：
    - use_venv=True：在临时沙箱目录 + 缓存 venv 中执行，PYTHONPATH 仅指向
      沙箱目录，被测代码的 import 不污染系统环境，任务间依赖互不冲突。
    - auto_install_deps=True：执行前检测缺失的第三方依赖，自动在 venv 内
      pip install（仅影响 venv，不安装到系统环境）。

    属性:
        timeout: 单次测试最大运行时间（秒），可通过 EXECUTION_TIMEOUT 环境变量配置。
        use_docker: 是否使用 Docker 隔离执行（当前未启用，保留接口）。
        use_venv: 是否使用 venv 沙箱隔离执行（默认 False，保持原有行为）。
        auto_install_deps: 是否自动安装缺失依赖（需 use_venv 生效）。
        dep_install_timeout: 依赖安装子进程超时秒数。
    """

    def __init__(
        self,
        timeout: int = 30,
        use_docker: bool = False,
        use_venv: bool = False,
        auto_install_deps: bool = False,
        dep_install_timeout: int = 120,
    ) -> None:
        # timeout 从参数传入，默认 30 秒
        self.timeout = timeout
        self.use_docker = use_docker
        self.use_venv = use_venv
        self.auto_install_deps = auto_install_deps
        self.dep_install_timeout = dep_install_timeout

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
        # 隔离沙箱路径：venv + 临时目录执行，避免依赖冲突与环境污染（P1 优化）
        if self.use_venv:
            return self._execute_sandboxed(test_code, target_file, target_function)

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

    def _execute_sandboxed(
        self,
        test_code: str,
        target_file: str,
        target_function: str | None = None,
    ) -> dict[str, Any]:
        """在隔离沙箱中执行测试：临时目录 + 缓存 venv + 依赖自动安装。

        流程：
        1. 创建临时沙箱目录，拷入被测模块文件（按 target_file 的模块名）；
        2. 写入自动修复导入后的测试文件；
        3. 检测被测代码 + 测试代码缺失的第三方依赖：
           - auto_install_deps=True → 在 venv 内 pip install（仅影响 venv）；
           - auto_install_deps=False → 记录缺失清单到 error_info，照常执行
             （失败将由错误分类器归为 import_error，便于区分代码 bug 与环境问题）；
        4. 用 venv 解释器（或系统解释器）在沙箱目录运行 pytest，
           PYTHONPATH 仅指向沙箱目录，实现任务间依赖隔离；
        5. 清理沙箱目录（venv 保留缓存，相同依赖组合的任务复用）。

        Returns:
            与 execute() 相同结构的结果字典。
        """
        from src.tools.dependency import (
            create_venv,
            extract_imported_modules,
            find_missing_modules,
            install_packages,
            suggest_package_names,
            venv_cache_dir,
        )

        sandbox_dir = tempfile.mkdtemp(prefix="aitester_sandbox_")
        # 被测模块名：取 target_file 基名（与 _extract_module_name_from_file 语义一致）
        module_name = self._extract_module_name_from_file(target_file)
        module_file = os.path.join(sandbox_dir, f"{module_name}.py")
        try:
            with open(target_file, encoding="utf-8") as f:
                target_source = f.read()
            with open(module_file, "w", encoding="utf-8") as f:
                f.write(target_source)
        except OSError as e:
            self._cleanup_sandbox(sandbox_dir)
            return {
                "passed": False,
                "output": f"读取被测文件失败: {e}",
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": {"type": "file_not_found", "message": str(e), "file_path": target_file},
            }

        # 测试文件写入沙箱（导入修复以沙箱为搜索根，模块名与文件名天然对齐）
        fixed_test_code = self._auto_fix_imports(test_code, module_file, sandbox_dir)
        test_file = os.path.join(sandbox_dir, "test_generated.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(fixed_test_code)

        # ── 依赖检测与安装 ──────────────────────────────────────────────────
        required_modules = extract_imported_modules(target_source + "\n" + fixed_test_code)
        missing_modules = find_missing_modules(required_modules, extra_search_files=[module_file])
        missing_packages = suggest_package_names(missing_modules)

        env = os.environ.copy()
        # 模块搜索路径仅指向沙箱目录（追加原 PYTHONPATH 保留 pytest 等测试工具）
        env["PYTHONPATH"] = sandbox_dir + os.pathsep + env.get("PYTHONPATH", "")
        python_path = sys.executable
        dep_install_note = ""
        sandbox_error_info: dict[str, Any] | None = None

        if missing_packages and self.use_venv:
            # 创建/复用缓存 venv（相同依赖组合共享，省 1-3s 重建开销）
            venv_dir = venv_cache_dir(missing_packages)
            try:
                python_path = create_venv(venv_dir, timeout=self.dep_install_timeout)
                if self.auto_install_deps:
                    ok, summary = install_packages(python_path, missing_packages, timeout=self.dep_install_timeout)
                    dep_install_note = f"依赖安装{'成功' if ok else '失败'}: {summary}"
                    if not ok:
                        sandbox_error_info = {
                            "type": "dependency_install_failed",
                            "message": f"缺失依赖安装失败: {missing_packages}",
                            "detail": summary,
                        }
            except RuntimeError as e:
                sandbox_error_info = {"type": "dependency_install_failed", "message": str(e), "detail": str(e)}

        if missing_packages and not self.use_venv:
            # 非 venv 模式但检测到缺失依赖：仅记录提示（由分类器区分代码 bug 与环境问题）
            dep_install_note = f"检测到缺失依赖（未安装，ENV_AUTO_INSTALL 关闭）: {missing_packages}"

        # 依赖安装失败/venv 创建失败：测试结果将不可信（缺失依赖仍在），
        # 直接提前返回，让 Debugger 拿到准确的 dependency_install_failed 诊断
        if sandbox_error_info:
            self._cleanup_sandbox(sandbox_dir)
            return {
                "passed": False,
                "output": dep_install_note or "依赖处理失败",
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": sandbox_error_info,
            }

        try:
            cmd = [
                python_path,
                "-m",
                "pytest",
                test_file,
                "-v",
                "--tb=short",
                f"--cov={sandbox_dir}",
                "--cov-report=term",
            ]
            if target_function:
                cmd.extend(["-k", target_function])

            output, last_result = self._run_pytest_with_retry(cmd, env, sandbox_dir)
            if isinstance(last_result, tuple) and last_result[0] == "EARLY_RETURN":
                result = {
                    "passed": False,
                    "output": output,
                    "coverage": 0.0,
                    "failed_cases": [],
                    "error_info": last_result[1],
                }
            else:
                coverage = self._parse_coverage(output)
                failed_cases = self._parse_failed_cases(output)
                passed = last_result is not None and last_result.returncode == 0
                result = {
                    "passed": passed,
                    "output": output,
                    "coverage": coverage,
                    "failed_cases": failed_cases,
                }
                if last_result is not None and last_result.returncode != 0:
                    result["error_info"] = self._build_error_info(last_result, output)
                    result["error_info"]["missing_dependencies"] = sorted(missing_modules)

            # 依赖检测结论写入 error_info / output，供 Debugger 与实验分析使用
            if dep_install_note:
                result["dep_note"] = dep_install_note
            if sandbox_error_info and not result.get("passed"):
                # 安装失败优先于测试失败报告（测试失败只是安装失败的表象）
                result["error_info"] = sandbox_error_info
            return result
        finally:
            # 清理临时沙箱（venv 缓存在 ~/.cache/aitester/venvs/，跨任务保留）
            self._cleanup_sandbox(sandbox_dir)

    @staticmethod
    def _cleanup_sandbox(sandbox_dir: str) -> None:
        """清理沙箱临时目录，失败仅记录警告（venv 缓存目录不受影响）。"""
        try:
            if os.path.isdir(sandbox_dir):
                import shutil

                shutil.rmtree(sandbox_dir, ignore_errors=True)
                logger.debug("已清理沙箱目录: %s", sandbox_dir)
        except OSError as e:
            logger.warning("清理沙箱目录失败: %s", e)

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
                # TimeoutExpired 携带超时前已累积的部分 stdout/stderr（text 模式下为 str，
                # 未产生时可能为 None）。合并进 last_output，让下游 Debugger 能拿到现场
                # 快照而非空白文本（此前超时分支丢失了部分输出）。
                partial_output = (e.output or "") + (e.stderr or "")
                last_output = partial_output
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
        """生成 sys.path 修改代码（import sys 只出现一次，避免原实现的重复导入）。"""
        inserts = "\n".join(f"sys.path.insert(0, {repr(d)})" for d in sorted(module_dirs))
        return f"import sys\n{inserts}"

    @staticmethod
    def _is_similar_module_name(imported_module: str, actual_module_name: str) -> bool:
        """判断导入名是否为被测模块名的"笔误"变体（大小写/缩写/近形名）。

        仅对相似名称做替换，避免把 numpy、requests 等第三方库导入
        错误地改写为被测模块名（原实现对所有未解析导入无差别替换）。

        Args:
            imported_module: 测试代码中的导入模块名。
            actual_module_name: 被测文件实际模块名。

        Returns:
            True 表示应替换为目标模块名。
        """
        a = imported_module.lower()
        b = actual_module_name.lower()
        if a == b:
            return True
        # 相似度阈值 0.6：覆盖常见笔误（如 calc vs calculator），
        # 同时排除无关名称（如 numpy vs calculator 相似度仅约 0.13）
        return SequenceMatcher(None, a, b).ratio() >= 0.6

    @staticmethod
    def _apply_import_replacements(
        test_code: str, imports: list[str], actual_module_name: str, needs_replacement: bool
    ) -> str:
        """对测试代码应用导入替换，返回修改后的代码。

        仅替换与被测模块名相似的导入（_is_similar_module_name 门控），
        并按模块名精确锚定正则，避免原实现"一条正则改写全部 import"
        导致的第三方库导入被误替换问题。
        """
        fixed_code = test_code
        if needs_replacement and imports:
            replaced_any = False
            for imported_module in imports:
                if imported_module == actual_module_name:
                    continue
                if not ExecutorAgent._is_similar_module_name(imported_module, actual_module_name):
                    # 无关模块（如第三方库）保持原样，不改写
                    continue
                # 按模块名锚定，仅替换该模块的导入语句
                from_pattern = re.compile(rf"^from\s+{re.escape(imported_module)}\s+import", re.MULTILINE)
                fixed_code = from_pattern.sub(f"from {actual_module_name} import", fixed_code)
                import_pattern = re.compile(rf"^import\s+{re.escape(imported_module)}\s*$", re.MULTILINE)
                fixed_code = import_pattern.sub(f"import {actual_module_name}", fixed_code)
                replaced_any = True
                logger.info("模块名不匹配，已将导入 '%s' 替换为 '%s'", imported_module, actual_module_name)
            if not replaced_any:
                logger.debug("无需替换：未发现与目标模块相似的错误导入名")
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
        # 使用模块级预编译正则（_RE_FAILED_CASE）
        for i, line in enumerate(lines):
            m = _RE_FAILED_CASE.search(line)
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
