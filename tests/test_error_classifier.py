"""
ErrorClassifier 单元测试

测试 error_classifier.py 中的：
- ErrorCategory 枚举
- SyntaxSubtype 枚举
- ErrorContext 数据类
- ErrorClassifier 类
- get_fix_strategy 函数
"""

import os
import sys

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

    # P2 细化新增类别
    def test_import_error_value(self):
        """IMPORT_ERROR 类别的值。"""
        assert ErrorCategory.IMPORT_ERROR.value == "import_error"

    def test_type_error_value(self):
        """TYPE_ERROR 类别的值。"""
        assert ErrorCategory.TYPE_ERROR.value == "type_error"

    def test_logic_error_value(self):
        """LOGIC_ERROR 类别的值。"""
        assert ErrorCategory.LOGIC_ERROR.value == "logic_error"


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
            subtype=SyntaxSubtype.IMPORT_ERROR,
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

    def test_classify_import_error(self):
        """P2 细化：导入错误独立为 IMPORT_ERROR（不再归 SYNTAX）。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.IMPORT_ERROR

    def test_classify_syntax_error(self):
        """分类语法错误为 SYNTAX。"""
        output = "SyntaxError: invalid syntax"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.SYNTAX

    def test_classify_type_error(self):
        """P2 细化：类型错误独立为 TYPE_ERROR（不再归 RUNTIME）。"""
        output = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.TYPE_ERROR

    def test_classify_runtime_error(self):
        """分类非类型的运行时错误为 RUNTIME。"""
        output = "IndexError: list index out of range"
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

    def test_classify_priority_type_error_over_assertion(self):
        """P2 细化：类型错误优先级高于断言错误。"""
        output = "TypeError: error\nAssertionError: failed"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.TYPE_ERROR

    def test_classify_priority_import_over_syntax(self):
        """P2 细化：导入错误优先于语法错误。"""
        output = "ModuleNotFoundError: No module named 'x'\nSyntaxError: bad"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.IMPORT_ERROR

    def test_classify_logic_error(self):
        """P2 细化：断言失败且失败栈未触及被测模块 → LOGIC_ERROR。"""
        # target_module=calculator；失败栈只出现在测试文件（test_calc.py）
        output = 'File "test_calc.py", line 5, in test_add\n    assert add(1, 2) == 3\nAssertionError: assert 4 == 3'
        result = self.classifier.classify(output, [], target_module="calculator")
        assert result == ErrorCategory.LOGIC_ERROR

    def test_classify_assertion_when_target_in_stack(self):
        """P2 细化：断言失败但失败栈触及被测模块 → 仍为 ASSERTION（代码 bug）。"""
        output = (
            'File "calculator.py", line 12, in add\n'
            "    return a + b\n"
            'File "test_calc.py", line 5, in test_add\n'
            "AssertionError: assert 4 == 3"
        )
        result = self.classifier.classify(output, [], target_module="calculator")
        assert result == ErrorCategory.ASSERTION

    def test_classify_assertion_without_module_hint(self):
        """P2 细化：未提供 target_module 时保守归 ASSERTION。"""
        output = "AssertionError: expected 2 but got 3"
        result = self.classifier.classify(output, [])
        assert result == ErrorCategory.ASSERTION

    # --- classify_with_context 方法测试 ---

    def test_classify_with_context_returns_tuple(self):
        """classify_with_context 返回元组。"""
        output = "ModuleNotFoundError: No module named 'test'"
        category, context = self.classifier.classify_with_context(output, [])
        assert isinstance(category, ErrorCategory)
        assert isinstance(context, ErrorContext)

    def test_classify_with_context_import(self):
        """P2 细化：导入错误的分类上下文（类别升级为 IMPORT_ERROR）。"""
        output = "ModuleNotFoundError: No module named 'pandas'"
        category, context = self.classifier.classify_with_context(output, [])
        assert category == ErrorCategory.IMPORT_ERROR
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
        output = 'File "test.py", line 10: SyntaxError'
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
        context = ErrorContext(filename="test.py", line=10, column=5, subtype=SyntaxSubtype.SYNTAX_ERROR)
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

    # ── P2 细化新增类别的修复策略 ──

    def test_import_error_strategy_with_module(self):
        """IMPORT_ERROR 独立策略（含模块名，指向安装依赖）。"""
        context = ErrorContext(module_name="pandas")
        strategy = get_fix_strategy(ErrorCategory.IMPORT_ERROR, context)
        assert "pandas" in strategy
        assert "安装" in strategy or "pip" in strategy

    def test_import_error_strategy_without_module(self):
        """IMPORT_ERROR 独立策略（无模块名）。"""
        strategy = get_fix_strategy(ErrorCategory.IMPORT_ERROR)
        assert "导入错误" in strategy

    def test_type_error_strategy(self):
        """TYPE_ERROR 独立策略（类型核对，禁止吞异常）。"""
        strategy = get_fix_strategy(ErrorCategory.TYPE_ERROR)
        assert "TypeError" in strategy
        assert "类型" in strategy

    def test_logic_error_strategy(self):
        """LOGIC_ERROR 独立策略（优先修测试预期值）。"""
        strategy = get_fix_strategy(ErrorCategory.LOGIC_ERROR)
        assert "测试" in strategy
        assert "预期值" in strategy
