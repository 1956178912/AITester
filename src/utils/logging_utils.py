"""
日志脱敏工具模块。

提供统一的敏感信息脱敏功能，防止 API Key、密码等敏感信息泄露到日志中。
所有 logger 调用应通过此模块的脱敏函数处理后再输出。
"""

from __future__ import annotations

import logging
import re
from typing import Any

# 敏感信息模式匹配规则
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API Key 模式（如 sk-xxx, LLM_xxx_API_KEY=xxx）
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})"), "<REDACTED_API_KEY>"),
    # Base64 编码的密钥
    (re.compile(r'(?:key|token|secret|password)=(.{8,})(?:\s|$|")'), r"key=<REDACTED>"),
    # JWT Token
    (re.compile(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"), "<REDACTED_JWT>"),
]


def mask_sensitive_info(text: str) -> str:
    """对文本中的敏感信息进行脱敏处理。

    将所有匹配的敏感信息替换为占位符，防止日志泄露。

    Args:
        text: 原始文本字符串。

    Returns:
        脱敏后的文本字符串。
    """
    if not text:
        return text or ""

    result = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


class SensitiveFilter(logging.Filter):
    """日志过滤器，自动对敏感信息进行脱敏。

    使用方法：
        logger.addFilter(SensitiveFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，对消息中的敏感信息进行脱敏。

        Args:
            record: 日志记录对象。

        Returns:
            True（始终允许日志通过）。
        """
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_info(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_sensitive_info(str(v)) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_sensitive_info(str(arg)) if isinstance(arg, str) else arg for arg in record.args
                )
        return True


def setup_logger_safety(logger_name: str | None = None) -> None:
    """为指定 logger（或根 logger）添加敏感信息过滤器。

    应在应用启动时调用，确保所有日志输出自动脱敏。

    Args:
        logger_name: 目标 logger 名称，None 表示配置根 logger。
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    # 检查是否已添加过滤器
    if not any(isinstance(f, SensitiveFilter) for f in logger.filters):
        logger.addFilter(SensitiveFilter())
        logging.info("已为 logger '%s' 添加敏感信息脱敏过滤器", logger_name or "root")


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """对字典中的所有字符串值进行脱敏。

    Args:
        data: 原始字典。

    Returns:
        脱敏后的新字典。
    """
    return {k: mask_sensitive_info(str(v)) if isinstance(v, str) else v for k, v in data.items()}


# 模块加载时自动配置根 logger
setup_logger_safety()
