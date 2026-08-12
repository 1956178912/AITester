"""
单元测试：测试错误分类器 ErrorClassifier 和策略函数。
覆盖所有五种错误类型及策略生成。
"""

import pytest
from src.agents.error_classifier import ErrorClassifier, ErrorCategory, get_fix_strategy


class TestErrorClassifier:
    """测试错误分类器的规则匹配逻辑。"""

    def setup_method(self):
        """为每个测试方法创建分类器实例。"""
        self.classifier = ErrorClassifier()

    def test_syntax_error_classification(self):
        """验证 ImportError 被正确分类为 SYNTAX。"""
        output = "ImportError: cannot import name 'foo' from 'bar'"
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
        # 同时包含两类错误时，优先匹配到先检查的类别
        output = "SyntaxError: invalid syntax\nZeroDivisionError: ..."
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX


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
