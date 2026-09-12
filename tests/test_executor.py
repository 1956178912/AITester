"""
ExecutorAgent 单元测试

测试 executor.py 中的：
- ExecutorAgent 类
- 导入修复功能
- 覆盖率解析
- 失败用例解析
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.executor import ExecutorAgent


class TestExecutorAgentInit:
    """测试 ExecutorAgent 初始化。"""

    def test_default_timeout(self):
        """默认超时为 30 秒。"""
        executor = ExecutorAgent()
        assert executor.timeout == 30

    def test_custom_timeout(self):
        """自定义超时时间。"""
        executor = ExecutorAgent(timeout=60)
        assert executor.timeout == 60

    def test_use_docker_default(self):
        """默认不使用 Docker。"""
        executor = ExecutorAgent()
        assert executor.use_docker is False

    def test_use_docker_enabled(self):
        """启用 Docker 模式。"""
        executor = ExecutorAgent(use_docker=True)
        assert executor.use_docker is True


class TestExtractModuleName:
    """测试模块名提取功能。"""

    def test_simple_filename(self):
        """简单文件名。"""
        result = ExecutorAgent._extract_module_name_from_file("examples/calculator.py")
        assert result == "calculator"

    def test_path_with_dirs(self):
        """带路径的文件名。"""
        result = ExecutorAgent._extract_module_name_from_file("/path/to/src/my_module.py")
        assert result == "my_module"

    def test_no_extension(self):
        """无扩展名时回退到 basename。"""
        result = ExecutorAgent._extract_module_name_from_file("examples/mymodule")
        assert result == "mymodule"


class TestExtractImports:
    """测试导入提取功能。"""

    def test_extract_from_import(self):
        """提取 from ... import 语句。"""
        code = "from calculator import add\nimport pytest"
        imports = ExecutorAgent._extract_imports(code)
        assert "calculator" in imports

    def test_extract_import(self):
        """提取 import 语句（非标准库）。"""
        # os 和 json 是标准库，会被跳过
        code = "import requests\nimport numpy"
        imports = ExecutorAgent._extract_imports(code)
        assert "requests" in imports
        assert "numpy" in imports

    def test_skip_standard_libraries(self):
        """跳过标准库导入。"""
        code = "import os\nimport sys\nimport re\nfrom calculator import add"
        imports = ExecutorAgent._extract_imports(code)
        assert "os" not in imports
        assert "sys" not in imports
        assert "re" not in imports
        assert "calculator" in imports

    def test_skip_relative_imports(self):
        """跳过相对导入。"""
        code = "from .local import something\nfrom calculator import add"
        imports = ExecutorAgent._extract_imports(code)
        assert len(imports) == 1
        assert "calculator" in imports

    def test_empty_code(self):
        """空代码无导入。"""
        imports = ExecutorAgent._extract_imports("")
        assert imports == []

    def test_comma_import_all_modules_captured(self):
        """逗号分隔多模块导入（import numpy, scipy）须完整捕获。

        回归：executor 本地复制的正则只取逗号列表首个模块，
        后续模块逃过依赖检测/导入修复链路。
        """
        code = "import numpy, scipy\n"
        imports = ExecutorAgent._extract_imports(code)
        assert "numpy" in imports
        assert "scipy" in imports

    def test_third_party_diskcache_not_treated_as_stdlib(self):
        """diskcache 是第三方包，不得被误判为标准库过滤掉。

        回归：executor 曾维护硬编码标准库 frozenset，误将 diskcache 列入，
        且清单缺 asyncio 等 stdlib；现复用 dependency.is_standard_library
        （sys.stdlib_module_names 权威清单）后须正确区分两类。
        """
        imports = ExecutorAgent._extract_imports("import diskcache\n")
        assert "diskcache" in imports

    def test_asyncio_treated_as_stdlib(self):
        """asyncio 属标准库，应被过滤（硬编码清单曾遗漏导致误判为第三方）。"""
        imports = ExecutorAgent._extract_imports("import asyncio\n")
        assert imports == []


class TestExecuteEnv:
    """execute() 非 venv 路径的环境构造（PYTHONPATH / cwd 深度）。"""

    @patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry")
    @patch("src.agents.executor.ExecutorAgent._auto_fix_imports")
    def test_project_root_is_repo_root(self, mock_fix, mock_retry, tmp_path, monkeypatch):
        """pytest 执行 cwd = 仓库根（executor.py 上溯三层），而非 src/。

        回归：此前上溯两层得到 src/，src 外的 examples/ 等目录模块
        在 rglob 搜索与 pytest 工作目录中都不可见。
        """
        monkeypatch.delenv("PYTHONPATH", raising=False)
        mock_fix.return_value = "def test_x(): pass"
        mock_retry.return_value = ("1 passed", MagicMock(returncode=0))

        target = tmp_path / "target.py"
        target.write_text("def x(): return 1\n", encoding="utf-8")

        ExecutorAgent().execute("def test_x(): pass", str(target))

        _, _, project_root = mock_retry.call_args.args
        # 测试文件位于 tests/test_executor.py → 上溯两层即仓库根
        expected_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert os.path.realpath(project_root) == os.path.realpath(expected_root)

    @patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry")
    @patch("src.agents.executor.ExecutorAgent._auto_fix_imports")
    def test_pythonpath_no_trailing_sep_when_unset(self, mock_fix, mock_retry, tmp_path, monkeypatch):
        """原 PYTHONPATH 未设置时，注入后不得产生尾随分隔符（空段等价 CWD）。"""
        monkeypatch.delenv("PYTHONPATH", raising=False)
        mock_fix.return_value = "def test_x(): pass"
        mock_retry.return_value = ("1 passed", MagicMock(returncode=0))

        target = tmp_path / "target.py"
        target.write_text("def x(): return 1\n", encoding="utf-8")

        ExecutorAgent().execute("def test_x(): pass", str(target))

        env = mock_retry.call_args.args[1]
        assert not env["PYTHONPATH"].endswith(os.pathsep)
        assert env["PYTHONPATH"] == str(tmp_path)

    @patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry")
    @patch("src.agents.executor.ExecutorAgent._auto_fix_imports")
    def test_pythonpath_appends_existing_segments(self, mock_fix, mock_retry, tmp_path, monkeypatch):
        """原 PYTHONPATH 已设置时，新目录追加在首、原段完整保留（空段仍被过滤）。"""
        monkeypatch.setenv("PYTHONPATH", "/a::/b")  # 中间空段应被过滤
        mock_fix.return_value = "def test_x(): pass"
        mock_retry.return_value = ("1 passed", MagicMock(returncode=0))

        target = tmp_path / "target.py"
        target.write_text("def x(): return 1\n", encoding="utf-8")

        ExecutorAgent().execute("def test_x(): pass", str(target))

        env = mock_retry.call_args.args[1]
        assert env["PYTHONPATH"] == os.pathsep.join([str(tmp_path), "/a", "/b"])


class TestParseCoverage:
    """测试覆盖率解析。"""

    def test_parse_coverage_percentage(self):
        """解析覆盖率百分比。"""
        output = "TOTAL                              100     150     85%"
        result = ExecutorAgent._parse_coverage(output)
        assert result == 85.0

    def test_parse_coverage_no_match(self):
        """无覆盖率信息时返回 0.0。"""
        output = "============================= tests =============================="
        result = ExecutorAgent._parse_coverage(output)
        assert result == 0.0

    def test_parse_coverage_multiple_lines(self):
        """多行输出中解析正确的覆盖率。"""
        output = """
Name    Stmts    Miss  Cover
------------------------------------
total   100      20    80%
------------------------------------
TOTAL   100      20    80%
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 80.0


class TestParseFailedCases:
    """测试失败用例解析。"""

    def test_parse_single_failure(self):
        """解析单个失败用例。"""
        output = """
FAILED test_calc.py::test_add - AssertionError: expected 2
=========================== short test summary ============================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 1
        assert "test_add" in result[0]["name"]

    def test_parse_multiple_failures(self):
        """解析多个失败用例。"""
        output = """
FAILED test_calc.py::test_add - AssertionError: first
FAILED test_calc.py::test_sub - AssertionError: second
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 2

    def test_parse_no_failures(self):
        """无失败用例时返回空列表。"""
        output = """
============================= 1 passed in 0.1s ==============================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert result == []

    def test_parse_failure_with_error_details(self):
        """解析带错误详情的失败用例。"""
        output = """
FAILED test_calc.py::test_divide - ZeroDivisionError: division by zero
    assert divide(1, 0) == 0
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 1
        assert "ZeroDivisionError" in result[0]["error"]


class TestBuildErrorInfo:
    """测试错误信息构建。"""

    def test_build_error_info_syntax(self):
        """构建含语法错误的信息。"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        output = "SyntaxError: invalid syntax"
        result = ExecutorAgent._build_error_info(mock_result, output)
        assert result["type"] == "test_failure"
        assert result["has_syntax_error"] is True

    def test_build_error_info_runtime(self):
        """构建含运行时错误的信息。"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        output = "TypeError: unsupported operand"
        result = ExecutorAgent._build_error_info(mock_result, output)
        assert result["has_runtime_error"] is True


class TestCleanupTempFile:
    """测试临时文件清理。"""

    def test_cleanup_existing_file(self, tmp_path):
        """清理存在的临时文件。"""
        test_file = tmp_path / "test_temp.py"
        test_file.write_text("print('hello')")

        ExecutorAgent._cleanup_temp_file(str(test_file))
        assert not test_file.exists()

    def test_cleanup_nonexistent_file(self):
        """清理不存在的文件不报错。"""
        ExecutorAgent._cleanup_temp_file("/nonexistent/path.py")


class TestAutoFixImports:
    """测试导入自动修复。"""

    def test_no_imports(self):
        """无导入时返回原代码。"""
        code = "def test():\n    pass"
        result = ExecutorAgent._auto_fix_imports(code, "examples/test.py", "/project")
        assert result == code

    def test_fix_import_path(self):
        """修复导入路径。"""
        code = "from calculator import add\n\ndef test_add():\n    pass"
        result = ExecutorAgent._auto_fix_imports(code, "examples/calculator.py", "/project")
        # 应该添加 sys.path 修改
        assert "sys.path" in result or result == code

    def test_third_party_import_not_replaced(self):
        """第三方库导入（如 numpy）不被改写为被测模块名。

        回归测试：原实现对所有未解析导入无差别替换，
        会把 "import numpy" 错误改写为 "import calculator"。
        """
        code = "from calculator import add\nimport numpy as np\n\ndef test_add():\n    pass"
        result = ExecutorAgent._auto_fix_imports(code, "examples/calculator.py", "/nonexistent-root")
        assert "import numpy as np" in result
        assert "import calculator\n" not in result

    def test_similar_misspelling_replaced(self):
        """与目标模块名相似的笔误导入（calculater → calculator）被替换。"""
        code = "from calculater import add\n\ndef test_add():\n    pass"
        result = ExecutorAgent._auto_fix_imports(code, "examples/calculator.py", "/nonexistent-root")
        assert "from calculator import add" in result

    def test_build_sys_path_code_single_import(self):
        """多目录注入时 import sys 只出现一次。"""
        code = ExecutorAgent._build_sys_path_code({"/dir-a", "/dir-b"})
        assert code.count("import sys") == 1
        assert "sys.path.insert(0, '/dir-a')" in code
        assert "sys.path.insert(0, '/dir-b')" in code


class TestResolveModulePaths:
    """测试模块路径解析。"""

    def test_module_found(self, tmp_path):
        """模块存在时返回路径。"""
        # 创建模拟文件
        test_file = tmp_path / "test_module.py"
        test_file.write_text("def foo(): pass")

        module_dirs, needs_replacement = ExecutorAgent._resolve_module_paths(
            ["test_module"], "test_module", str(tmp_path), str(test_file)
        )
        assert len(module_dirs) > 0

    def test_module_not_found(self):
        """模块不存在时标记需要替换。"""
        module_dirs, needs_replacement = ExecutorAgent._resolve_module_paths(
            ["nonexistent_module"], "actual_module", "/project", "/project/src/actual_module.py"
        )
        assert needs_replacement is True


class TestRunPytestWithRetry:
    """测试带重试的 pytest 执行。"""

    @patch("subprocess.run")
    def test_success_on_first_try(self, mock_run):
        """首次尝试成功。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1 passed"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = ExecutorAgent(timeout=30)
        output, result = executor._run_pytest_with_retry(["pytest"], {}, "/project")

        assert result.returncode == 0
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_timeout_returns_early(self, mock_run):
        """超时时返回 EARLY_RETURN。"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=30)

        executor = ExecutorAgent(timeout=30)
        output, result = executor._run_pytest_with_retry(["pytest"], {}, "/project")

        assert result[0] == "EARLY_RETURN"
        assert result[1]["type"] == "timeout"

    @patch("subprocess.run")
    def test_timeout_captures_partial_output(self, mock_run):
        """超时携带的部分 stdout/stderr 应合并进 output，供 Debugger 诊断现场。"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pytest", timeout=30, output="collected 3 items", stderr="some traceback line"
        )

        executor = ExecutorAgent(timeout=30)
        output, result = executor._run_pytest_with_retry(["pytest"], {}, "/project")

        assert result[0] == "EARLY_RETURN"
        assert "collected 3 items" in output
        assert "some traceback line" in output

    @patch("subprocess.run")
    def test_file_not_found_returns_early(self, mock_run):
        """找不到执行文件时返回 EARLY_RETURN。"""
        mock_run.side_effect = FileNotFoundError("pytest not found")

        executor = ExecutorAgent(timeout=30)
        output, result = executor._run_pytest_with_retry(["pytest"], {}, "/project")

        assert result[0] == "EARLY_RETURN"
        assert result[1]["type"] == "file_not_found"

    @patch("subprocess.run")
    def test_permission_error_returns_early(self, mock_run):
        """权限错误时返回 EARLY_RETURN。"""
        mock_run.side_effect = PermissionError("Permission denied")

        executor = ExecutorAgent(timeout=30)
        output, result = executor._run_pytest_with_retry(["pytest"], {}, "/project")

        assert result[0] == "EARLY_RETURN"
        assert result[1]["type"] == "permission_error"
