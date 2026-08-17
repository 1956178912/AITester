"""
统一异常处理模块：提供通用的异常类型和工具函数。

本模块定义了 AITester 项目专用的异常层次结构，并提供了统一的错误处理工具，
确保各组件能一致地处理异常情况。

异常层次：
    AITesterError (基类)
    ├── ConfigurationError: 配置相关错误
    ├── ExecutionError: 执行相关错误
    │   ├── TimeoutError: 超时错误
    │   └── PermissionError: 权限错误
    ├── ParsingError: 解析相关错误
    │   ├── JSONParseError: JSON 解析错误
    │   └── SyntaxParseError: 语法解析错误
    └── APIError: API 调用错误
        ├── RateLimitError: 速率限制错误
        └── AuthenticationError: 认证错误
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Dict, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

# 类型变量：用于泛型装饰器
F = TypeVar('F', bound=Callable[..., Any])


class AITesterError(Exception):
    """AITester 项目的基类异常。

    所有自定义异常都应继承此类，以便统一捕获和处理。
    """
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        """初始化异常。

        Args:
            message: 错误消息。
            context: 上下文信息字典（可选），包含额外的诊断信息。
        """
        self.message = message
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """返回格式化的错误消息。

        Returns:
            包含错误消息和上下文的字符串。
        """
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} [{context_str}]"
        return self.message


class ConfigurationError(AITesterError):
    """配置相关错误。

    当配置文件缺失、格式错误或必需参数未设置时抛出。
    """
    pass


class ExecutionError(AITesterError):
    """执行相关错误。

    当测试执行失败时抛出，包括超时、权限不足等。
    """
    pass


class TimeoutError(ExecutionError):
    """超时错误。

    当操作超过指定时间限制时抛出。
    """
    pass


class ParsingError(AITesterError):
    """解析相关错误。

    当解析失败时抛出，包括 JSON 解析、语法解析等。
    """
    pass


class JSONParseError(ParsingError):
    """JSON 解析错误。

    当 JSON 字符串格式不正确或无法解析时抛出。
    """
    def __init__(self, message: str, json_str: str, pos: int):
        """初始化 JSON 解析错误。

        Args:
            message: 错误消息。
            json_str: 导致错误的 JSON 字符串。
            pos: 错误发生的位置。
        """
        super().__init__(message, {"json_length": len(json_str), "error_pos": pos})
        self.json_str = json_str
        self.pos = pos


class SyntaxParseError(ParsingError):
    """语法解析错误。

    当 Python 代码语法不正确时抛出。
    """
    def __init__(self, message: str, filename: str = "", lineno: int = 0, offset: int = 0):
        """初始化语法解析错误。

        Args:
            message: 错误消息。
            filename: 文件名（可选）。
            lineno: 行号（可选）。
            offset: 列偏移（可选）。
        """
        context = {}
        if filename:
            context["filename"] = filename
        if lineno:
            context["lineno"] = lineno
        if offset:
            context["offset"] = offset
        super().__init__(message, context)


class APIError(AITesterError):
    """API 调用错误。

    当外部 API 调用失败时抛出。
    """
    pass


class RateLimitError(APIError):
    """速率限制错误。

    当 API 返回速率限制响应时抛出。
    """
    def __init__(self, message: str, retry_after: Optional[int] = None):
        """初始化速率限制错误。

        Args:
            message: 错误消息。
            retry_after: 建议的重试间隔（秒），可选。
        """
        context = {}
        if retry_after:
            context["retry_after"] = retry_after
        super().__init__(message, context)


class AuthenticationError(APIError):
    """认证错误。

    当 API 认证失败时抛出。
    """
    pass


def retry_with_backoff(
    max_retries: int = 3,
    base_wait: float = 1.0,
    exponential_base: float = 2.0,
    catch_exceptions: tuple = (Exception,),
    logger_name: Optional[str] = None,
) -> Callable[[F], F]:
    """带指数退避的重试装饰器。

    对标记的函数执行带重试的调用，失败时按指数退避策略等待后重试。

    示例:
        ```python
        @retry_with_backoff(max_retries=3, base_wait=1.0)
        def call_api():
            # API 调用逻辑
            pass
        ```

    Args:
        max_retries: 最大重试次数（不含首次尝试）。
        base_wait: 基础等待秒数（首次重试等待 base_wait 秒）。
        exponential_base: 指数基数，用于计算后续等待时间。
        catch_exceptions: 需要捕获并重试的异常类型元组。
        logger_name: 日志记录器名称，为 None 时使用调用者模块日志。

    Returns:
        装饰后的函数。
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except catch_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = base_wait * (exponential_base ** attempt)
                        log = logger_name and logging.getLogger(logger_name) or logger
                        log.warning(
                            "函数 %s 调用失败 (尝试 %d/%d): %s，等待 %.1f 秒后重试",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            e,
                            wait_time,
                        )
                        time.sleep(wait_time)
                    else:
                        break
            if last_exception:
                raise last_exception
            return None  # 理论上不会到达这里
        return wrapper  # type: ignore[return-value]
    return decorator


def with_error_context(
    context_getter: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Callable[[F], F]:
    """错误上下文收集装饰器。

    自动收集函数执行时的上下文信息，并在异常发生时附加到错误中。

    Args:
        context_getter: 返回上下文字典的函数，为 None 时自动收集参数。

    Returns:
        装饰后的函数。
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except AITesterError as e:
                # 已有上下文，直接抛出
                raise
            except Exception as e:
                # 收集上下文信息
                context: Dict[str, Any] = {}
                if context_getter:
                    try:
                        context.update(context_getter())
                    except Exception:
                        pass
                # 添加函数参数信息
                context["function"] = func.__name__
                context["args_count"] = len(args)
                context["kwargs_count"] = len(kwargs)
                # 抛出带上下文的异常
                raise AITesterError(str(e), context) from e
        return wrapper  # type: ignore[return-value]
    return decorator


def safe_execute(
    func: Callable[..., Any],
    default: Any = None,
    catch_exceptions: tuple = (Exception,),
    error_handler: Optional[Callable[[Exception], Any]] = None,
    **kwargs: Any,
) -> Any:
    """安全执行函数，捕获异常并返回默认值。

    这是一个实用函数，用于执行可能失败的操作性代码。

    示例:
        ```python
        result = safe_execute(
            func=my_function,
            default="fallback",
            arg1=value1,
            arg2=value2
        )
        ```

    Args:
        func: 要执行的函数。
        default: 发生异常时返回的默认值。
        catch_exceptions: 需要捕获的异常类型元组。
        error_handler: 异常处理回调函数（可选），接收异常对象。
        **kwargs: 传递给 func 的命名参数。

    Returns:
        函数执行结果，失败时返回 default。
    """
    try:
        return func(**kwargs)
    except catch_exceptions as e:
        if error_handler:
            error_handler(e)
        else:
            logger.error("安全执行失败: %s", e, exc_info=True)
        return default
