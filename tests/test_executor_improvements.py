"""
测试 ExecutorAgent 的模块导入路径自动修复功能。

覆盖场景：
    - 模块名与文件名匹配：正确添加 sys.path
    - 模块名与文件名不匹配：替换导入语句
    - 无导入语句：返回原代码
    - 多个导入语句混合处理
    - 包导入处理
    - 相对导入处理
"""

from src.agents.executor import ExecutorAgent


class TestExtractModuleNameFromFile:
    """测试 _extract_module_name_from_file 静态方法。"""

    def test_simple_filename(self):
        """简单文件名：calculator.py → calculator"""
        result = ExecutorAgent._extract_module_name_from_file("examples/calculator.py")
        assert result == "calculator"

    def test_nested_path(self):
        """嵌套路径：src/utils/helper.py → helper"""
        result = ExecutorAgent._extract_module_name_from_file("src/utils/helper.py")
        assert result == "helper"

    def test_with_directory(self):
        """带目录路径：/abs/path/module.py → module"""
        result = ExecutorAgent._extract_module_name_from_file("/abs/path/my_module.py")
        assert result == "my_module"

    def test_no_extension(self):
        """无扩展名：module → module"""
        result = ExecutorAgent._extract_module_name_from_file("module")
        assert result == "module"


class TestAutoFixImports:
    """测试 _auto_fix_imports 静态方法。"""

    def test_no_imports(self):
        """无导入语句时返回原代码。"""
        test_code = """
def test_add():
    assert 1 + 1 == 2
"""
        result = ExecutorAgent._auto_fix_imports(test_code, "examples/calculator.py", "/project")
        assert result == test_code

    def test_matching_module_name(self, tmp_path):
        """模块名与文件名匹配：添加对应目录到 sys.path。"""
        # 创建临时文件
        target_file = tmp_path / "calculator.py"
        target_file.write_text("def add(a, b): return a + b\n")

        test_code = """
from calculator import add

def test_add():
    assert add(1, 2) == 3
"""
        result = ExecutorAgent._auto_fix_imports(test_code, str(target_file), str(tmp_path))
        # 模块存在时保留原始导入（因为模块已在搜索路径中）
        assert "from calculator import add" in result

    def test_mismatched_module_name(self, tmp_path):
        """模块名与文件名不匹配：替换导入语句。"""
        # 创建临时文件 buggy_library.py
        target_file = tmp_path / "buggy_library.py"
        target_file.write_text("def binary_search(arr, target): return 0\n")

        # 测试代码错误地使用了 utility_lib
        test_code = """
from utility_lib import binary_search

def test_search():
    assert binary_search([1, 2, 3], 2) == 1
"""
        result = ExecutorAgent._auto_fix_imports(test_code, str(target_file), str(tmp_path))
        # 应该替换导入语句
        assert "from buggy_library import binary_search" in result
        assert "from utility_lib import binary_search" not in result

    def test_multiple_imports_with_mismatch(self, tmp_path):
        """多个导入语句，部分不匹配。"""
        # 创建临时文件
        target_file = tmp_path / "string_utils.py"
        target_file.write_text("def is_palindrome(s): return s == s[::-1]\n")

        test_code = """
from wrong_module_name import is_palindrome
import os

def test_palindrome():
    assert is_palindrome("abcba")
"""
        result = ExecutorAgent._auto_fix_imports(test_code, str(target_file), str(tmp_path))
        # 应该替换错误的模块名
        assert "from string_utils import is_palindrome" in result
        assert "from wrong_module_name import is_palindrome" not in result
        # 注意：标准库导入（如 os）会被正确保留在标准库集合中
        # 但实现可能不会显式保留所有非模块导入
        assert "def test_palindrome" in result  # 确保函数定义保留

    def test_package_import(self, tmp_path):
        """包导入处理：package.module → package.module。"""
        # 创建包结构
        pkg_dir = tmp_path / "mypkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "utils.py").write_text("def helper(): pass\n")

        test_code = """
from mypkg.utils import helper

def test_helper():
    assert helper() is None
"""
        result = ExecutorAgent._auto_fix_imports(test_code, str(pkg_dir / "utils.py"), str(tmp_path))
        # 包导入应该能正常处理，保留原始导入或正确替换
        assert "from mypkg.utils import helper" in result or "from utils import helper" in result

    def test_relative_import(self, tmp_path):
        """相对导入处理。"""
        target_file = tmp_path / "module.py"
        target_file.write_text("def func(): pass\n")

        test_code = """
from .module import func

def test_func():
    assert func() is None
"""
        result = ExecutorAgent._auto_fix_imports(test_code, str(target_file), str(tmp_path))
        # 相对导入保持不变
        assert "from .module import func" in result


class TestEndToEndExecution:
    """端到端测试：验证实际执行效果。"""

    def test_execute_with_mismatched_import(self, tmp_path):
        """测试执行器能正确处理模块名不匹配的情况。"""
        # 创建被测文件
        target_file = tmp_path / "calc.py"
        target_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""")

        # 创建测试代码，使用错误的模块名
        test_code = """
from calculator import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
"""
        # 执行测试
        executor = ExecutorAgent(timeout=10)
        result = executor.execute(test_code, str(target_file))

        # 验证结果
        assert result["passed"], f"测试应该通过，输出: {result['output']}"
        assert result["coverage"] > 0

    def test_execute_with_correct_import(self, tmp_path):
        """测试执行器在模块名正确时也能正常工作。"""
        # 创建被测文件
        target_file = tmp_path / "math_ops.py"
        target_file.write_text("""
def multiply(a, b):
    return a * b
""")

        # 创建测试代码，使用正确的模块名
        test_code = """
from math_ops import multiply

def test_multiply():
    assert multiply(3, 4) == 12
"""
        # 执行测试
        executor = ExecutorAgent(timeout=10)
        result = executor.execute(test_code, str(target_file))

        # 验证结果
        assert result["passed"], f"测试应该通过，输出: {result['output']}"
        assert result["coverage"] > 0
