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
    """日志过滤器，对格式化后的最终日志文本自动脱敏。

    使用方式（挂到 handler 才能覆盖子 logger 传播的消息）：
        for handler in logging.getLogger().handlers:
            handler.addFilter(SensitiveFilter())
    或直接调用 setup_logger_safety() 自动挂到目标 logger 与其 handler。

    注意：logger 级过滤器只对直接记录在该 logger 上的消息生效，
    经 propagate 到达的消息只有 handler 级过滤器会拦截。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，对最终日志文本脱敏。

        脱敏作用于格式化后的完整消息（record.getMessage()）：
        密钥常被拆分存放在 msg 与 args 中（如 logger.info("sk-%s 失效", key)），
        逐字段 mask 无法命中；先格式化再整体脱敏可覆盖所有组合。

        Args:
            record: 日志记录对象。

        Returns:
            True（始终允许日志通过，仅改写内容）。
        """
        try:
            message = record.getMessage()
        except Exception:
            return True  # 格式化失败时不阻断日志输出
        record.msg = mask_sensitive_info(message)
        record.args = None  # 防止 emit 时二次格式化
        return True


def setup_logger_safety(logger_name: str | None = None) -> None:
    """为指定 logger（或根 logger）及其 handler 添加敏感信息脱敏过滤器。

    应在应用启动（且 root logger 配置好 handler）后调用。

    注意：logger 级过滤器只对"直接在该 logger 上记录"的消息生效，
    子 logger 传播（propagate）上来的记录不经过 logger 级过滤器——
    全链路脱敏必须把过滤器挂到 handler 上（handler.handle 会逐条过滤）。
    本函数同时挂 logger 与已有 handler 两处，确保覆盖：
        - logging.info(...) 直接记录到目标 logger 的消息
        - 各模块 logger 传播到目标 logger 的消息（经 handler 过滤）

    Args:
        logger_name: 目标 logger 名称，None 表示配置根 logger。
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    filt = SensitiveFilter()
    # logger 级：拦截直接在该 logger 上记录的消息
    if not any(isinstance(f, SensitiveFilter) for f in logger.filters):
        logger.addFilter(filt)
    # handler 级：拦截经传播到达的消息（同一实例复用，脱敏幂等）
    for handler in logger.handlers:
        if not any(isinstance(f, SensitiveFilter) for f in handler.filters):
            handler.addFilter(filt)
    # 注意：必须用模块 logger 记录，不能调用模块级 logging.info()——
    # Python 3.14 中 root 无 handler 时模块级 logging.info() 会隐式触发
    # basicConfig()（附加裸 StreamHandler），导致后续业务侧 basicConfig
    # （自定义格式/FileHandler）全部失效
    logging.getLogger(__name__).info("已为 logger '%s' 添加敏感信息脱敏过滤器", logger_name or "root")


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
