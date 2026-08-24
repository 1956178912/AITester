"""测试异常类 — 扩展版，覆盖装饰器和工具函数"""
import pytest

from src.exceptions import (
    AITesterError,
    APIError,
    AuthenticationError,
    ConfigurationError,
    ExecutionError,
    JSONParseError,
    ParsingError,
    RateLimitError,
    SyntaxParseError,
    TimeoutError,
    retry_with_backoff,
    safe_execute,
    with_error_context,
)


class TestAITesterErrors:
    """测试基础异常类"""

    def test_base_error_message(self):
        """基础异常消息"""
        err = AITesterError("test error")
        assert str(err) == "test error"

    def test_base_error_with_context(self):
        """带上下文的异常"""
        err = AITesterError("failed", context={"key": "value"})
        assert err.context == {"key": "value"}
        assert "key=value" in str(err)

    def test_base_error_default_context(self):
        """默认上下文"""
        err = AITesterError("error")
        assert err.context == {}

    def test_is_exception_subclass(self):
        assert issubclass(AITesterError, Exception)

    def test_raises_and_catches(self):
        with pytest.raises(AITesterError) as exc_info:
            raise AITesterError("test raise")
        assert "test raise" in str(exc_info.value)

    def test_empty_context_not_none(self):
        err = AITesterError("msg")
        assert err.context is not None
        assert isinstance(err.context, dict)


class TestAPIErrors:
    """测试 API 相关异常"""

    def test_api_error_init(self):
        """API 异常初始化"""
        err = APIError("rate limited", context={"status": 429})
        assert "rate limited" in str(err)

    def test_rate_limit_error(self):
        """限流错误"""
        err = RateLimitError("too many requests")
        assert isinstance(err, APIError)

    def test_rate_limit_with_retry_after(self):
        err = RateLimitError("rate limited", retry_after=30)
        assert err.context["retry_after"] == 30

    def test_rate_limit_without_retry_after(self):
        err = RateLimitError("rate limited")
        assert "retry_after" not in err.context

    def test_auth_error(self):
        """认证错误"""
        err = AuthenticationError("invalid token")
        assert isinstance(err, APIError)


class TestParserErrors:
    """测试解析异常"""

    def test_json_parse_error(self):
        """JSON 解析错误"""
        err = JSONParseError("invalid", json_str='{"a": 1}', pos=5)
        assert isinstance(err, ParsingError)
        assert err.json_str == '{"a": 1}'
        assert err.pos == 5

    def test_json_parse_error_context(self):
        err = JSONParseError("bad", json_str="hello", pos=2)
        assert err.context["json_length"] == 5
        assert err.context["error_pos"] == 2

    def test_syntax_parse_error(self):
        """语法解析错误"""
        err = SyntaxParseError("missing colon")
        assert isinstance(err, ParsingError)

    def test_syntax_parse_error_with_fields(self):
        err = SyntaxParseError("bad", filename="test.py", lineno=10, offset=5)
        assert err.context["filename"] == "test.py"
        assert err.context["lineno"] == 10
        assert err.context["offset"] == 5

    def test_parsing_error(self):
        """通用解析错误"""
        err = ParsingError("parse failed")
        assert str(err) == "parse failed"


class TestExecutionErrors:
    """测试执行异常"""

    def test_execution_error(self):
        """执行错误"""
        err = ExecutionError("execution failed")
        assert isinstance(err, AITesterError)

    def test_timeout_error(self):
        """超时错误"""
        err = TimeoutError("timeout")
        assert isinstance(err, ExecutionError)
        assert isinstance(err, AITesterError)


class TestConfigErrors:
    """测试配置异常"""

    def test_configuration_error(self):
        """配置错误"""
        err = ConfigurationError("config missing")
        assert isinstance(err, AITesterError)


# ─── 装饰器和工具函数测试 ─────────────────────────────────────────────────────


class TestRetryWithBackoff:
    """测试带指数退避的重试装饰器"""

    def test_success_on_first_try(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_wait=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_success_after_retries(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_wait=0.01)
        def eventually_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        assert eventually_succeed() == "ok"
        assert call_count == 3

    def test_exhausts_retries_raises(self):
        @retry_with_backoff(max_retries=2, base_wait=0.01)
        def always_fail():
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            always_fail()

    def test_custom_exception_types_only(self):
        @retry_with_backoff(max_retries=2, base_wait=0.01, catch_exceptions=(ValueError,))
        def fails_with_type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            fails_with_type_error()

    def test_non_caught_exception_no_retry(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_wait=0.01, catch_exceptions=(ValueError,))
        def raises_keyerror():
            nonlocal call_count
            call_count += 1
            raise KeyError("missing")

        with pytest.raises(KeyError):
            raises_keyerror()
        assert call_count == 1


class TestWithErrorContext:
    """测试错误上下文收集装饰器"""

    def test_success_no_wrapping(self):
        @with_error_context()
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_wraps_non_aitesterror(self):
        @with_error_context()
        def throws_value_error():
            raise ValueError("original error")

        with pytest.raises(AITesterError) as exc_info:
            throws_value_error()
        assert "original error" in str(exc_info.value)
        assert exc_info.value.context["function"] == "throws_value_error"

    def test_preserves_aitesterror(self):
        @with_error_context()
        def throws_config():
            raise ConfigurationError("config issue")

        with pytest.raises(ConfigurationError):
            throws_config()

    def test_custom_context_getter(self):
        @with_error_context(context_getter=lambda: {"custom": "data"})
        def uses_context():
            raise RuntimeError("fail")

        with pytest.raises(AITesterError) as exc_info:
            uses_context()
        assert exc_info.value.context["custom"] == "data"


class TestSafeExecute:
    """测试安全执行工具函数"""

    def test_success_case(self):
        result = safe_execute(func=lambda x: x * 2, default=0, x=5)
        assert result == 10

    def test_exception_returns_default(self):
        result = safe_execute(func=lambda: 1 / 0, default=-1)
        assert result == -1

    def test_exception_with_custom_handler(self):
        logged = []
        result = safe_execute(
            func=lambda: int("not-a-number"),
            default=0,
            error_handler=lambda e: logged.append(str(e)),
        )
        assert result == 0
        assert len(logged) == 1

    def test_kwargs_passed_through(self):
        def add(a, b):
            return a + b

        assert safe_execute(func=add, default=0, a=3, b=4) == 7

    def test_empty_kwargs(self):
        def pure():
            return 42

        assert safe_execute(func=pure, default=0) == 42
