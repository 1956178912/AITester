"""
增强测试：测试 ErrorClassifier 的错误上下文提取和改进。

覆盖范围：
    - 语法错误检测和上下文提取
    - 错误上下文提取（文件名、行号、模块名）
    - 改进的修复策略
"""

import pytest
from src.agents.error_classifier import (
    ErrorClassifier,
    ErrorCategory,
    SyntaxSubtype,
    ErrorContext,
    get_fix_strategy,
)


# ─── TestSyntaxErrorDetection：语法错误检测 ───────────────────────────────────
class TestSyntaxErrorDetection:
    """测试语法错误的识别和分类。"""

    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_syntax_error_with_traceback(self):
        """测试带 traceback 的语法错误分类。"""
        output = """
SyntaxError: invalid syntax
  File "test.py", line 10
    x =
         ^
"""
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.SYNTAX

    def test_syntax_error_with_colon_format(self):
        """测试冒号格式的语法错误。"""
        output = "E   test.py:5:3: invalid syntax"
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.SYNTAX

    def test_multiple_syntax_errors(self):
        """测试多个语法错误的分类。"""
        output = """
SyntaxError: unexpected indent
  File "a.py", line 5

SyntaxError: EOF while parsing
  File "b.py", line 20
"""
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.SYNTAX

    def test_syntax_error_in_test_file(self):
        """测试文件中语法错误的分类。"""
        output = """
============================= test session ==============================
FAILED test_example.py::test_something - SyntaxError: E   test_example.py:10:5: invalid syntax
"""
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.SYNTAX


# ─── TestErrorContextExtraction：错误上下文提取 ───────────────────────────────
class TestErrorContextExtraction:
    """测试错误上下文的提取功能。"""

    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_traceback_context_extraction(self):
        """测试从 traceback 提取文件名和行号。"""
        output = '''
Traceback (most recent call last):
  File "test_runner.py", line 42, in run_test
    result = test_func()
  File "test_example.py", line 10, in test_function
    x =
         ^
SyntaxError: invalid syntax
'''
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR
        assert context.filename == "test_example.py"
        assert context.line == 10

    def test_colon_format_context_extraction(self):
        """测试冒号格式的文件:行:列提取。"""
        output = "SyntaxError: E   module.py:15:8: missing closing parenthesis"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR
        assert context.filename == "module.py"
        assert context.line == 15
        assert context.column == 8

    def test_module_not_found_context(self):
        """测试 ModuleNotFoundError 的模块名提取。"""
        output = "ModuleNotFoundError: No module named 'requests'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR
        assert context.module_name == "requests"

    def test_import_error_from_clause(self):
        """测试 ImportError with from 子句的模块名提取。"""
        output = "ImportError: cannot import name 'foo' from 'bar'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR
        assert context.module_name == "foo"

    def test_failed_cases_context_extraction(self):
        """测试从 failed_cases 提取上下文。"""
        output = ""
        cases = [
            {
                "name": "test_import",
                "error": "ModuleNotFoundError: No module named 'numpy'"
            }
        ]
        category, context = self.classifier.classify_with_context(output, cases)
        assert category == ErrorCategory.SYNTAX
        assert context.module_name == "numpy"

    def test_no_context_on_runtime_error(self):
        """测试运行时错误不提取特定上下文。"""
        output = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.RUNTIME
        assert context.subtype is None

    def test_no_context_on_assertion_error(self):
        """测试断言错误不提取特定上下文。"""
        output = "AssertionError: expected 5, got 3"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.ASSERTION
        assert context.subtype is None


# ─── TestImprovedFixStrategy：改进的修复策略 ─────────────────────────────────
class TestImprovedFixStrategy:
    """测试改进的修复策略。"""

    def test_syntax_strategy_with_location(self):
        """测试带位置信息的语法错误修复策略。"""
        context = ErrorContext(
            subtype=SyntaxSubtype.SYNTAX_ERROR,
            filename="calculator.py",
            line=25,
            column=10,
            error_message="SyntaxError: invalid syntax"
        )
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "calculator.py" in strategy
        assert "25" in strategy
        assert "10" in strategy

    def test_import_strategy_with_module(self):
        """测试导入错误的修复策略。"""
        context = ErrorContext(
            subtype=SyntaxSubtype.IMPORT_ERROR,
            module_name="pandas",
            error_message="ModuleNotFoundError: No module named 'pandas'"
        )
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "pandas" in strategy

    def test_unknown_strategy_still_works(self):
        """测试未知类型的修复策略仍有效。"""
        strategy = get_fix_strategy(ErrorCategory.UNKNOWN)
        assert "分析" in strategy


# ─── TestPriorityRules：优先级规则测试 ────────────────────────────────────────
class TestPriorityRules:
    """测试错误分类的优先级规则。"""

    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_syntax_priority_over_all(self):
        """语法错误优先级最高。"""
        output = "SyntaxError: invalid syntax\nZeroDivisionError: division by zero"
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.SYNTAX

    def test_runtime_priority_over_assertion(self):
        """运行时错误优先级高于断言错误。"""
        output = "TypeError: argument of type 'NoneType' is not iterable\nAssertionError: fail"
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.RUNTIME

    def test_assertion_priority_over_timeout(self):
        """断言错误优先级高于超时。"""
        output = "AssertionError: 1 != 2\ntimeout exceeded"
        category = self.classifier.classify(output, [])
        assert category == ErrorCategory.ASSERTION


# ─── TestBoundaryConditions：边界条件测试 ─────────────────────────────────────
class TestBoundaryConditions:
    """测试边界条件和异常情况。"""

    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_multiline_traceback(self):
        """测试多行 traceback 的正确处理。"""
        output = """
Traceback (most recent call last):
  File "runner.py", line 10, in <module>
    test_func()
  File "test_module.py", line 25, in test_function
    result = calculate(1, 0)
  File "calculator.py", line 8, in calculate
    return a / b
ZeroDivisionError: division by zero
"""
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.RUNTIME
        # 应提取到最近的文件位置
        assert context.filename == "calculator.py"
        assert context.line == 8

    def test_empty_error_message(self):
        """测试空错误消息的处理。"""
        category, context = self.classifier.classify_with_context("", [])
        assert category == ErrorCategory.UNKNOWN
        assert context.error_message == ""

    def test_very_long_error_message(self):
        """测试超长错误消息的截断。"""
        long_error = "Error: " + "x" * 1000
        category, context = self.classifier.classify_with_context(long_error, [])
        assert len(context.error_message) <= 500  # 应被截断

    def test_special_characters_in_filename(self):
        """测试文件名中的特殊字符。"""
        output = 'File "test_file(1).py", line 5'
        category, context = self.classifier.classify_with_context(output, [])
        # 应能处理特殊字符
        assert category == ErrorCategory.UNKNOWN  # 无法匹配已知模式
