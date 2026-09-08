"""
ErrorClassifier 单元测试

测试 error_classifier.py 中的：
- ErrorCategory 枚举
- SyntaxSubtype 枚举
- ErrorContext 数据类
- ErrorClassifier 类
- get_fix_strategy 函数
"""

import sys

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import (
    ErrorCategory,
    ErrorClassifier,
    ErrorContext,
    SyntaxSubtype,
    get_fix_strategy,
)


class TestErrorCategory:
    """测试 ErrorCategory 枚举。"""

    def test_syntax_value(self):
        """SYNTAX 类别的值。"""
        assert ErrorCategory.SYNTAX.value == "syntax"

    def test_assertion_value(self):
        """ASSERTION 类别的值。"""
        assert ErrorCategory.ASSERTION.value == "assertion"

    def test_runtime_value(self):
        """RUNTIME 类别的值。"""
        assert ErrorCategory.RUNTIME.value == "runtime"

    def test_timeout_value(self):
        """TIMEOUT 类别的值。"""
        assert ErrorCategory.TIMEOUT.value == "timeout"

    def test_unknown_value(self):
        """UNKNOWN 类别的值。"""
        assert ErrorCategory.UNKNOWN.value == "unknown"


class TestSyntaxSubtype:
    """测试 SyntaxSubtype 枚举。"""

    def test_import_error_value(self):
        """IMPORT_ERROR 子类型的值。"""
        assert SyntaxSubtype.IMPORT_ERROR.value == "import_error"

    def test_syntax_error_value(self):
        """SYNTAX_ERROR 子类型的值。"""
        assert SyntaxSubtype.SYNTAX_ERROR.value == "syntax_error"

    def test_unrecognized_value(self):
        """UNRECOGNIZED 子类型的值。"""
        assert SyntaxSubtype.UNRECOGNIZED.value == "unrecognized"


class TestErrorContext:
    """测试 ErrorContext 数据类。"""

    def test_default_values(self):
        """测试默认值。"""
        ctx = ErrorContext()
        assert ctx.filename is None
        assert ctx.line is None
        assert ctx.column is None
        assert ctx.module_name is None
        assert ctx.error_message == ""
        assert ctx.subtype is None

    def test_custom_values(self):
        """测试自定义值。"""
        ctx = ErrorContext(
            filename="test.py",
            line=42,
            column=10,
            module_name="pandas",
            error_message="No module named pandas",
            subtype=SyntaxSubtype.IMPORT_ERROR
        )
        assert ctx.filename == "test.py"
        assert ctx.line == 42
        assert ctx.module_name == "pandas"


class TestErrorClassifier:
    """测试 ErrorClassifier 分类器。"""

    def setup_method(self):
        """每个测试前创建分类器实例。"""
        self.classifier = ErrorClassifier()

    # --- classify 方法测试 ---

    def test_classify_syntax_import_error(self):
        """分类导入错误为 SYNTAX。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_classify_syntax_error(self):
        """分类语法错误为 SYNTAX。"""
        output = "SyntaxError: invalid syntax"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_classify_runtime_error(self):
        """分类运行时错误为 RUNTIME。"""
        output = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.RUNTIME

    def test_classify_zero_division(self):
        """分类除零错误为 RUNTIME。"""
        output = "ZeroDivisionError: division by zero"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.RUNTIME

    def test_classify_assertion_error(self):
        """分类断言错误为 ASSERTION。"""
        output = "AssertionError: expected 2 but got 3"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.ASSERTION

    def test_classify_timeout_error(self):
        """分类超时错误为 TIMEOUT。"""
        output = "Test ran for longer than expected"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.TIMEOUT

    def test_classify_unknown(self):
        """无法识别的错误分类为 UNKNOWN。"""
        output = "Some unknown error occurred"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.UNKNOWN

    def test_classify_with_failed_cases(self):
        """使用 failed_cases 进行分类。"""
        output = ""
        failed_cases = [{"name": "test_foo", "error": "KeyError: 'missing_key'"}]
        result = self.classifier.classify(output, failed_cases)
        assert result == ErrorCategory.RUNTIME

    def test_classify_priority_syntax_over_runtime(self):
        """语法错误优先级高于运行时错误。"""
        output = "SyntaxError: invalid syntax\nTypeError: something"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_classify_priority_runtime_over_assertion(self):
        """运行时错误优先级高于断言错误。"""
        output = "TypeError: error\nAssertionError: failed"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.RUNTIME

    # --- classify_with_context 方法测试 ---

    def test_classify_with_context_returns_tuple(self):
        """classify_with_context 返回元组。"""
        output = "ModuleNotFoundError: No module named 'test'"
        category, context = self.classifier.classify_with_context(output, [])
        assert isinstance(category, ErrorCategory)
        assert isinstance(context, ErrorContext)

    def test_classify_with_context_syntax(self):
        """语法错误的分类上下文。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR
        assert context.module_name == "pandas"

    # --- extract_error_context 方法测试 ---

    def test_extract_context_import_error(self):
        """提取导入错误的上下文。"""
        output = "ModuleNotFoundError: No module named 'numpy'"
        context = self.classifier.extract_error_context(output, [])
        assert context.module_name == "numpy"
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR

    def test_extract_context_syntax_error(self):
        """提取语法错误的上下文。"""
        output = "File \"test.py\", line 10: SyntaxError"
        context = self.classifier.extract_error_context(output, [])
        assert context.filename == "test.py"
        assert context.line == 10

    def test_extract_context_no_match(self):
        """无匹配时返回空上下文。"""
        output = "Some random error"
        context = self.classifier.extract_error_context(output, [])
        assert context.filename is None
        assert context.line is None
        assert context.subtype is None

    # --- 静态方法测试 ---

    def test_is_syntax_error_module_not_found(self):
        """检测 ModuleNotFoundError。"""
        assert ErrorClassifier._is_syntax_error("ModuleNotFoundError: No module named 'x'") is True

    def test_is_syntax_error_import_error(self):
        """检测 ImportError。"""
        assert ErrorClassifier._is_syntax_error("ImportError: cannot import name 'x'") is True

    def test_is_syntax_error_syntax_error(self):
        """检测 SyntaxError。"""
        assert ErrorClassifier._is_syntax_error("SyntaxError: invalid syntax") is True

    def test_is_syntax_error_no_match(self):
        """无语法错误时返回 False。"""
        assert ErrorClassifier._is_syntax_error("TypeError: something went wrong") is False

    def test_is_runtime_error_type_error(self):
        """检测 TypeError。"""
        assert ErrorClassifier._is_runtime_error("TypeError: invalid type") is True

    def test_is_runtime_error_value_error(self):
        """检测 ValueError。"""
        assert ErrorClassifier._is_runtime_error("ValueError: invalid value") is True

    def test_is_runtime_error_no_match(self):
        """无运行时错误时返回 False。"""
        assert ErrorClassifier._is_runtime_error("SyntaxError: invalid") is False

    def test_is_assertion_error(self):
        """检测断言错误。"""
        assert ErrorClassifier._is_assertion_error("AssertionError: expected 1") is True
        assert ErrorClassifier._is_assertion_error("assert x == y") is True

    def test_is_assertion_error_no_match(self):
        """无断言错误时返回 False。"""
        assert ErrorClassifier._is_assertion_error("TypeError: error") is False

    def test_is_timeout_error(self):
        """检测超时错误。"""
        assert ErrorClassifier._is_timeout_error("timeout exceeded") is True
        assert ErrorClassifier._is_timeout_error("TimedOut") is True

    def test_is_timeout_error_no_match(self):
        """无超时错误时返回 False。"""
        assert ErrorClassifier._is_timeout_error("RuntimeError: something") is False


class TestGetFixStrategy:
    """测试 get_fix_strategy 函数。"""

    def test_syntax_import_error_with_module(self):
        """导入错误的修复策略（含模块名）。"""
        context = ErrorContext(module_name="pandas", subtype=SyntaxSubtype.IMPORT_ERROR)
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "pandas" in strategy
        assert "requirements.txt" in strategy

    def test_syntax_import_error_without_module(self):
        """导入错误的修复策略（无模块名）。"""
        context = ErrorContext(subtype=SyntaxSubtype.IMPORT_ERROR)
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "导入错误" in strategy

    def test_syntax_error_with_location(self):
        """语法错误的修复策略（含位置）。"""
        context = ErrorContext(
            filename="test.py",
            line=10,
            column=5,
            subtype=SyntaxSubtype.SYNTAX_ERROR
        )
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "test.py" in strategy
        assert "10" in strategy
        assert "5" in strategy

    def test_runtime_error_strategy(self):
        """运行时错误的修复策略。"""
        strategy = get_fix_strategy(ErrorCategory.RUNTIME)
        assert "运行时异常" in strategy

    def test_assertion_error_strategy(self):
        """断言错误的修复策略。"""
        strategy = get_fix_strategy(ErrorCategory.ASSERTION)
        assert "断言失败" in strategy

    def test_timeout_error_strategy(self):
        """超时错误的修复策略。"""
        strategy = get_fix_strategy(ErrorCategory.TIMEOUT)
        assert "死循环" in strategy or "超时" in strategy

    def test_unknown_error_strategy(self):
        """未知错误的修复策略。"""
        strategy = get_fix_strategy(ErrorCategory.UNKNOWN)
        assert "未能自动识别" in strategy

    def test_syntax_without_context(self):
        """无上下文的语法错误策略。"""
        strategy = get_fix_strategy(ErrorCategory.SYNTAX)
        assert "语法/编译错误" in strategy
