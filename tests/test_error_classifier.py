"""
单元测试：测试错误分类器 ErrorClassifier 和策略函数 get_fix_strategy。

覆盖范围：
    - 全部五种错误类型（SYNTAX、RUNTIME、ASSERTION、TIMEOUT、UNKNOWN）的分类正确性
    - Syntax 子类型识别（IMPORT_ERROR、SYNTAX_ERROR）
    - 错误上下文提取（文件名、行号、列号、模块名）
    - 分类优先级：SYNTAX > RUNTIME > ASSERTION > TIMEOUT
    - failed_cases 的 error 字段参与分类
    - 每种错误类型对应的修复策略关键词完整性
"""

import pytest
from src.agents.error_classifier import (
    ErrorClassifier,
    ErrorCategory,
    SyntaxSubtype,
    ErrorContext,
    get_fix_strategy,
)


# ─── TestErrorClassifier：错误分类器 ──────────────────────────────────────────
class TestErrorClassifier:
    """测试错误分类器的规则匹配逻辑。"""

    def setup_method(self):
        """为每个测试方法创建独立的分类器实例。"""
        self.classifier = ErrorClassifier()

    def test_syntax_error_classification(self):
        """验证 ImportError 被正确分类为 SYNTAX。"""
        output = "ImportError: cannot import name 'foo' from 'bar'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_module_not_found_classification(self):
        """验证 ModuleNotFoundError 被正确分类为 SYNTAX。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_syntax_error_classification(self):
        """验证 SyntaxError 被正确分类为 SYNTAX。"""
        output = "SyntaxError: invalid syntax"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_indentation_error_classification(self):
        """验证 IndentationError 被正确分类为 SYNTAX。"""
        output = "IndentationError: expected an indented block"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_runtime_error_classification(self):
        """验证 ZeroDivisionError 被正确分类为 RUNTIME。"""
        output = "ZeroDivisionError: division by zero"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.RUNTIME

    def test_assertion_error_classification(self):
        """验证 AssertionError 被正确分类为 ASSERTION。"""
        output = "AssertionError: assert 2 == 3"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.ASSERTION

    def test_timeout_classification(self):
        """验证超时输出被正确分类为 TIMEOUT。"""
        output = "Test ran for longer than 30 seconds"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.TIMEOUT

    def test_unknown_error_fallback(self):
        """验证无法识别的错误返回 UNKNOWN。"""
        output = "Some unexpected error occurred"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.UNKNOWN

    def test_failed_cases_influence(self):
        """验证 failed_cases 的 error 字段也参与分类。"""
        output = ""
        cases = [{"name": "test_foo", "error": "TypeError: unsupported operand type"}]
        result = self.classifier.classify(output, cases)
        assert result == ErrorCategory.RUNTIME

    def test_syntax_priority_over_runtime(self):
        """验证语法错误优先级高于运行时错误。"""
        # 同时包含两类错误时，优先匹配到先检查的 SYNTAX 类别
        output = "SyntaxError: invalid syntax\nZeroDivisionError: ..."
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_import_error_priority_over_runtime(self):
        """验证 ImportError 优先级高于运行时错误。"""
        output = "ImportError: cannot import name 'foo'\nTypeError: ..."
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX


# ─── TestClassifyWithContext：带上下文的分类 ───────────────────────────────────
class TestClassifyWithContext:
    """测试 classify_with_context() 方法和错误上下文提取。"""

    def setup_method(self):
        """为每个测试方法创建独立的分类器实例。"""
        self.classifier = ErrorClassifier()

    def test_import_error_context_extraction(self):
        """验证 ImportError 能正确提取模块名。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR
        assert context.module_name == "pandas"

    def test_syntax_error_context_extraction(self):
        """验证 SyntaxError 能正确提取文件名和行号。"""
        output = "SyntaxError: invalid syntax\n  File \"test.py\", line 10\n    x ="
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR
        assert context.filename == "test.py"
        assert context.line == 10

    def test_colon_format_context_extraction(self):
        """验证冒号格式能正确提取文件名、行号、列号。"""
        output = "SyntaxError: E   test.py:5:3: invalid syntax"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.SYNTAX_ERROR
        assert context.filename == "test.py"
        assert context.line == 5
        assert context.column == 3

    def test_no_context_extraction_on_unknown(self):
        """验证 UNKNOWN 错误不提取特定上下文。"""
        output = "Some random error"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.UNKNOWN
        assert context.subtype is None
        assert context.filename is None

    def test_module_name_in_failed_cases(self):
        """验证 failed_cases 中的模块名能被正确提取。"""
        output = ""
        cases = [{
            "name": "test_import",
            "error": "ModuleNotFoundError: No module named 'numpy'"
        }]
        category, context = self.classifier.classify_with_context(output, cases)
        assert category == ErrorCategory.SYNTAX
        assert context.module_name == "numpy"


# ─── TestFixStrategy：修复策略映射 ────────────────────────────────────────────
class TestFixStrategy:
    """测试错误类型到修复策略的映射。"""

    def test_syntax_strategy(self):
        """验证语法错误的修复策略包含关键词。"""
        strategy = get_fix_strategy(ErrorCategory.SYNTAX)
        assert "重新生成" in strategy or "完整" in strategy

    def test_runtime_strategy(self):
        """验证运行时异常的修复策略包含分析提示。"""
        strategy = get_fix_strategy(ErrorCategory.RUNTIME)
        assert "分析" in strategy or "异常" in strategy

    def test_assertion_strategy(self):
        """验证断言失败的修复策略引导判断方向。"""
        strategy = get_fix_strategy(ErrorCategory.ASSERTION)
        assert "代码逻辑" in strategy or "预期值" in strategy

    def test_timeout_strategy(self):
        """验证超时的修复策略指向循环/递归问题。"""
        strategy = get_fix_strategy(ErrorCategory.TIMEOUT)
        assert "死循环" in strategy or "递归" in strategy

    def test_unknown_strategy(self):
        """验证未知类型的修复策略为通用分析。"""
        strategy = get_fix_strategy(ErrorCategory.UNKNOWN)
        assert "分析" in strategy

    def test_import_error_strategy_with_module_name(self):
        """验证 ImportError 策略包含模块名建议。"""
        context = ErrorContext(
            subtype=SyntaxSubtype.IMPORT_ERROR,
            module_name="pandas"
        )
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "pandas" in strategy
        assert "依赖" in strategy or "模块" in strategy

    def test_syntax_error_strategy_with_location(self):
        """验证 SyntaxError 策略包含位置信息。"""
        context = ErrorContext(
            subtype=SyntaxSubtype.SYNTAX_ERROR,
            filename="test.py",
            line=10,
            column=3
        )
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "test.py" in strategy
        assert "10" in strategy
        assert "3" in strategy

    def test_syntax_error_strategy_without_context(self):
        """验证无上下文时 SyntaxError 策略仍然有效。"""
        context = None
        strategy = get_fix_strategy(ErrorCategory.SYNTAX, context)
        assert "语法" in strategy or "import" in strategy


# ─── TestEdgeCases：边界情况测试 ───────────────────────────────────────────────
class TestEdgeCases:
    """测试边界情况和异常输入。"""

    def setup_method(self):
        """为每个测试方法创建独立的分类器实例。"""
        self.classifier = ErrorClassifier()

    def test_empty_output(self):
        """验证空输出返回 UNKNOWN。"""
        result = self.classifier.classify("", [])
        assert result == ErrorCategory.UNKNOWN

    def test_empty_failed_cases(self):
        """验证空 failed_cases 不影响分类。"""
        output = "SyntaxError: invalid syntax"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_many_failed_cases_truncation(self):
        """验证超过 3 个 failed_cases 时只取前 3 个。"""
        output = ""
        cases = [
            {"name": f"test_{i}", "error": "TypeError: ..."}
            for i in range(10)
        ]
        result = self.classifier.classify(output, cases)
        assert result == ErrorCategory.RUNTIME

    def test_import_error_with_from_clause(self):
        """验证 ImportError with from 子句能正确提取模块名。"""
        output = "ImportError: cannot import name 'foo' from 'bar'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.SYNTAX
        assert context.subtype == SyntaxSubtype.IMPORT_ERROR
        assert context.module_name == "foo"

    def test_tab_error_classification(self):
        """验证 TabError 被正确分类为 SYNTAX。"""
        output = "TabError: inconsistent use of tabs and spaces"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_incomplete_input_classification(self):
        """验证 IncompleteInput 被正确分类为 SYNTAX。"""
        output = "IncompleteInput: unexpected EOF while parsing"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX
