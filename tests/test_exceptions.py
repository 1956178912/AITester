"""
单元测试：测试统一异常处理模块。

覆盖范围：
    - AITesterError 及其子类的实例化和消息
    - retry_with_backoff 装饰器的重试逻辑
    - with_error_context 装饰器的上下文收集
    - safe_execute 函数的异常捕获
"""

import pytest

from src.exceptions import (
    AITesterError,
    APIError,
    AuthenticationError,
    ConfigurationError,
    ExecutionError,
    JSONParseError,
    RateLimitError,
    SyntaxParseError,
    TimeoutError,
    retry_with_backoff,
    safe_execute,
    with_error_context,
)


# ─── TestAITesterError：基础异常类 ───────────────────────────────────────────
class TestAITesterError:
    """测试基础异常类 AITesterError。"""

    def test_base_exception_without_context(self):
        """测试不带上下文的异常消息。"""
        error = AITesterError("简单错误消息")
        assert str(error) == "简单错误消息"
        assert error.message == "简单错误消息"
        assert error.context == {}

    def test_base_exception_with_context(self):
        """测试带上下文的异常消息。"""
        context = {"key1": "value1", "key2": 42}
        error = AITesterError("带上下文的错误", context=context)
        expected = "带上下文的错误 [key1=value1, key2=42]"
        assert str(error) == expected
        assert error.context == context

    def test_subclass_inheritance(self):
        """测试子类继承关系。"""
        error = ConfigurationError("配置错误")
        assert isinstance(error, AITesterError)
        assert isinstance(error, ConfigurationError)

        error = TimeoutError("超时错误")
        assert isinstance(error, ExecutionError)
        assert isinstance(error, AITesterError)


# ─── TestSpecificExceptions：具体异常类型 ─────────────────────────────────────
class TestSpecificExceptions:
    """测试具体的异常类型。"""

    def test_json_parse_error(self):
        """测试 JSONParseError 的初始化。"""
        error = JSONParseError("Invalid JSON", '{"a": 1', 5)
        assert error.message == "Invalid JSON"
        assert error.json_str == '{"a": 1'
        assert error.pos == 5
        assert "json_length" in error.context
        assert "error_pos" in error.context

    def test_syntax_parse_error(self):
        """测试 SyntaxParseError 的初始化。"""
        error = SyntaxParseError("unexpected EOF", "test.py", 10, 5)
        assert error.message == "unexpected EOF"
        assert error.context["filename"] == "test.py"
        assert error.context["lineno"] == 10
        assert error.context["offset"] == 5

    def test_rate_limit_error(self):
        """测试 RateLimitError 的初始化。"""
        error = RateLimitError("Rate limited", retry_after=60)
        assert error.message == "Rate limited"
        assert error.context["retry_after"] == 60

    def test_authentication_error(self):
        """测试 AuthenticationError 的初始化。"""
        error = AuthenticationError("Invalid API key")
        assert error.message == "Invalid API key"
        assert isinstance(error, APIError)


# ─── TestRetryWithBackoff：重试装饰器 ─────────────────────────────────────────
class TestRetryWithBackoff:
    """测试 retry_with_backoff 装饰器。"""

    def test_success_on_first_attempt(self):
        """测试首次调用成功的情况。"""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_wait=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_failure_then_success(self):
        """测试失败后重试成功的情况。"""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_wait=0.01)
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("临时错误")
            return "success"

        result = failing_then_success()
        assert result == "success"
        assert call_count == 3

    def test_exhaust_retries_raises(self):
        """测试重试耗尽后抛出异常。"""
        call_count = 0

        @retry_with_backoff(max_retries=2, base_wait=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("永久错误")

        with pytest.raises(ValueError, match="永久错误"):
            always_fails()
        assert call_count == 3  # 1次初始 + 2次重试

    def test_specific_exception_only(self):
        """测试只捕获指定异常类型。"""
        call_count = 0

        @retry_with_backoff(max_retries=2, base_wait=0.01, catch_exceptions=(ValueError,))
        def mixed_failures():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("可重试")
            raise TypeError("不可重试")

        with pytest.raises(TypeError):
            mixed_failures()

    def test_custom_logger_name(self):
        """测试自定义日志记录器名称。"""

        @retry_with_backoff(max_retries=1, base_wait=0.01, logger_name="test_logger")
        def func_with_logger():
            raise ValueError("测试")

        with pytest.raises(ValueError):
            func_with_logger()


# ─── TestWithErrorContext：错误上下文装饰器 ────────────────────────────────────
class TestWithErrorContext:
    """测试 with_error_context 装饰器。"""

    def test_context_collection(self):
        """测试自动收集函数参数上下文。"""

        @with_error_context()
        def func_with_args(a: int, b: str) -> str:
            raise ValueError("测试错误")

        with pytest.raises(AITesterError) as exc_info:
            func_with_args(1, "test")

        context = exc_info.value.context
        assert context["function"] == "func_with_args"
        assert context["args_count"] == 2
        assert context["kwargs_count"] == 0

    def test_custom_context_getter(self):
        """测试自定义上下文获取函数。"""

        @with_error_context(context_getter=lambda: {"custom": "value"})
        def func_with_custom_context():
            raise RuntimeError("测试")

        with pytest.raises(AITesterError) as exc_info:
            func_with_custom_context()

        context = exc_info.value.context
        assert context["custom"] == "value"


# ─── TestSafeExecute：安全执行函数 ────────────────────────────────────────────
class TestSafeExecute:
    """测试 safe_execute 函数。"""

    def test_successful_execution(self):
        """测试成功执行的情况。"""

        def good_func(x: int) -> int:
            return x * 2

        result = safe_execute(good_func, default=-1, x=5)
        assert result == 10

    def test_exception_returns_default(self):
        """测试异常时返回默认值。"""

        def bad_func(x: int) -> int:
            raise ValueError("错误")

        result = safe_execute(bad_func, default=-1, x=5)
        assert result == -1

    def test_custom_exception_type(self):
        """测试自定义异常类型捕获。"""

        def raises_value_error(x: int) -> int:
            raise ValueError("值错误")

        def raises_type_error(x: int) -> int:
            raise TypeError("类型错误")

        # 只捕获 ValueError，不捕获 TypeError
        # 对于 ValueError，应该返回默认值
        result = safe_execute(raises_value_error, default=-1, catch_exceptions=(ValueError,), x=5)
        assert result == -1

        # 对于 TypeError，应该抛出异常
        with pytest.raises(TypeError):
            safe_execute(raises_type_error, default=-1, catch_exceptions=(ValueError,), x=5)

    def test_error_handler_callback(self):
        """测试错误处理回调。"""
        errors_caught = []

        def error_handler(e: Exception) -> None:
            errors_caught.append(str(e))

        def bad_func() -> str:
            raise ValueError("测试错误")

        result = safe_execute(
            bad_func,
            default="fallback",
            error_handler=error_handler,
        )
        assert result == "fallback"
        assert len(errors_caught) == 1
        assert "测试错误" in errors_caught[0]
