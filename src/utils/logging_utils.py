"""
日志脱敏工具模块。

提供统一的敏感信息脱敏功能，防止 API Key、密码等敏感信息泄露到日志中。
所有 logger 调用应通过此模块的脱敏函数处理后再输出。
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

# 敏感信息模式匹配规则
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API Key 模式：覆盖 sk- 前缀、带点号段、无 sk- 前缀的长十六进制/base64 密钥
    # （形如 sk-ws-xxx.yyy...、e2b08862968b... 两类此前不在此模式内）
    (re.compile(r"(sk-[A-Za-z0-9.\-_]{20,})"), "<REDACTED_API_KEY>"),
    # 长十六进制串（>=32 位，前后无字母数字/下划线粘连）
    (re.compile(r"(?<![\w-])[A-Fa-f0-9]{32,}(?!\w)"), "<REDACTED_KEY>"),
    # 长 base64 串（>=40 位，须含大小写字母或 +/_，避免误伤普通长单词）
    (re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9+/=_-]{40,}={0,2})(?![A-Za-z0-9+/_=])"), "<REDACTED_KEY>"),
    # Base64 编码的密钥
    (re.compile(r'(?:key|token|secret|password)=(.{8,})(?:\s|$|")'), r"key=<REDACTED>"),
    # JWT Token
    (re.compile(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"), "<REDACTED_JWT>"),
]

# 4.2 改进：fallback 兜底模式（"长随机串 + JWT"类凭证）——脱敏模块
# 彻底不可用（理论上不会发生：纯标准库模块）时，至少拦截最常见的
# sk-/hex/base64/JWT 四种凭证形态。与 _SENSITIVE_PATTERNS 前 4 条同
# 口径，独立成 tuple 供 fallback_mask_sensitive_info 消费（避免降级路径
# 调用 mask_sensitive_info 本身导致递归触发异常）。
# 注：_SENSITIVE_PATTERNS[0]=sk- 前缀、[1]=32+ hex、[2]=40+ base64、
# [3]=key=xxx 赋值、[4]=JWT；fallback 取 [0,1,2,4]（sk/hex/base64/JWT），
# 跳过 [3]（key=xxx 依赖上下文匹配，降级态保守起见不纳入，避免误伤）。
_FALLBACK_PATTERNS: tuple[tuple[re.Pattern, str], ...] = tuple(_SENSITIVE_PATTERNS[i] for i in (0, 1, 2, 4))

# setup_logger_safety 的"检查-追加"段锁（2026-09-26 全面审查：并发调用幂等化）
_logger_safety_lock = threading.Lock()


def fallback_mask_sensitive_info(text: str) -> str:
    """脱敏模块异常时的纯正则兜底（4.2 审计 R-1）。

    当 mask_sensitive_info 因任何原因不可用（循环导入 / 模块损坏）时，
    调用方委托本函数做"长随机串 + JWT"兜底脱敏，避免敏感文本原样落日志。

    4.2 改进：覆盖 4 类最高频凭证形态（sk- 前缀 / 32+ hex / 40+ base64 /
    JWT），补齐 R-1 审计发现的"JWT 在降级路径不拦截"缺口——JWT 是
    最常见的外泄凭证之一，降级态仍应拦截。key=xxx 赋值形态因依赖上下文
    匹配仍不纳入（避免降级态误伤普通文本）。正常路径的
    SensitiveFilter/SensitiveFormatter 仍会做二次脱敏兜底。

    Args:
        text: 原始文本。

    Returns:
        长随机串类凭证被替换为占位符后的文本；text 为空时原样返回。
    """
    if not text:
        return text or ""
    result = text
    for pattern, replacement in _FALLBACK_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


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


def redact_text(text: str) -> str:
    """对任意日志文本做脱敏的单一实现（4.1 审计：消除双套 _redact 复制）。

    历史上 `src/api/api_manager._redact` 与 `src/agents/llm_client._redact_log_text`
    各自实现了一份同构的"mask → fallback → 原样返回"三级降级逻辑（注释均声明
    "与对方同口径，委托同一实现"，但代码实际是复制而非委托——一旦模式更新
    只改一处，另一处静默漂移）。本函数是该降级链的单一实现：
    1. 首选 mask_sensitive_info（完整 5 模式）；
    2. 首选路径异常时降级 fallback_mask_sensitive_info（纯正则兜底）；
    3. 两者均不可用时原样返回（脱敏失败不应阻断主流程）。

    各调用方保留本模块内的 `_redact` 别名（历史 patch 路径 / 日志口径
    不变），实现统一收敛到本函数。

    Args:
        text: 待脱敏的日志文本（异常字符串 / base_url 等）。

    Returns:
        脱敏后的文本。
    """
    try:
        return mask_sensitive_info(text)
    except Exception:
        try:
            return fallback_mask_sensitive_info(text)
        except Exception:
            # 脱敏模块彻底不可用（理论上不会发生：纯标准库模块）时原样返回，
            # 不阻断主流程——脱敏失败不应让 LLM/API 调用本身崩溃
            return text


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


class SensitiveFormatter(logging.Formatter):
    """对格式化后的完整日志行（含 exc_info 异常堆栈）做脱敏的 Formatter。

    SensitiveFilter 只对 record.getMessage()（消息体）脱敏；当记录携带 exc_info 时，
    异常 traceback 由 Formatter.formatException 单独生成并追加在消息之后，
    会绕过 filter，导致 API Key 等凭证仍可能落进日志文件（长期留存面）。
    本 formatter 在 super().format() 得到的完整结果（消息 + 堆栈）上再跑一次
    mask_sensitive_info，堵住该盲区。挂在 handler 上即可（配合 SensitiveFilter
    双重防护，脱敏幂等）。
    """

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        try:
            return mask_sensitive_info(formatted)
        except Exception:
            # 脱敏主路径失败：先走纯正则兜底（4.2 口径），彻底不可用时才退回
            # 原始文本——此前直接返回未脱敏的完整行（含堆栈），是脱敏盲区
            try:
                return fallback_mask_sensitive_info(formatted)
            except Exception:
                return formatted


def setup_logger_safety(logger_name: str | None = None) -> None:
    """为指定 logger（或根 logger）及其 handler 添加敏感信息脱敏过滤器。

    应在应用启动（且 root logger 配置好 handler）后调用。

    注意：logger 级过滤器只对"直接在该 logger 上记录"的消息生效，
    子 logger 传播（propagate）上来的记录不经过 logger 级过滤器——
    全链路脱敏必须把过滤器挂到 handler 上（handler.handle 会逐条过滤）。
    本函数同时挂 logger 与已有 handler 两处，确保覆盖：
        - logging.info(...) 直接记录到目标 logger 的消息
        - 各模块 logger 传播到目标 logger 的消息（经 handler 过滤）

    线程安全（2026-09-26 全面审查）："检查-追加"段持锁执行——此前并发
    调用（惰性 import 路径 / 多线程入口）各自追加一个过滤器实例，
    handler.filters 无谓膨胀；锁内幂等短路，单线程行为不变。

    Args:
        logger_name: 目标 logger 名称，None 表示配置根 logger。
    """
    with _logger_safety_lock:
        logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()

        # 幂等短路：logger 与全部 handler 均已挂脱敏过滤器时直接返回。
        # setup_logger_safety 被多个模块/入口重复调用（logging_utils 模块加载、
        # cli/app.py 导入期、嵌入式调用方）时，避免过滤器实例无谓膨胀。
        # 注意：logger.handlers 为空时 all(...) 恒真，需联合 logger.filters 判断
        # （logger 级无过滤器则仍需挂，handler 循环自然 no-op）。
        logger_has_filter = any(isinstance(f, SensitiveFilter) for f in logger.filters)
        handlers_have_filters = all(
            all(isinstance(f, SensitiveFilter) for f in handler.filters) for handler in logger.handlers
        )
        if logger_has_filter and handlers_have_filters:
            return

        filt = SensitiveFilter()
        # logger 级：拦截直接在该 logger 上记录的消息
        if not logger_has_filter:
            logger.addFilter(filt)
        # handler 级：拦截经传播到达的消息（同一实例复用，脱敏幂等）
        for handler in logger.handlers:
            if not any(isinstance(f, SensitiveFilter) for f in handler.filters):
                handler.addFilter(filt)
        # 注意：必须用模块 logger 记录，不能调用模块级 logging.info()——
        # Python 3.14 中 root 无 handler 时模块级 logging.info() 会隐式触发
        # basicConfig()（附加裸 StreamHandler），导致后续业务侧 basicConfig
        # （自定义格式/FileHandler）全部失效。
        # 用 DEBUG 级别：避免每次 CLI 启动都刷一行提示（--verbose 时可见）
        logging.getLogger(__name__).debug("已为 logger '%s' 添加敏感信息脱敏过滤器", logger_name or "root")


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """对字典中的所有字符串值进行脱敏（递归处理嵌套 dict / list / tuple）。

    4.2 改进：此前仅脱敏顶层字符串值，嵌套结构（如 {"nested": {"token": "sk-..."}}）
    内的敏感字段会原样保留——trace JSONL 落盘、异常堆栈等场景常用嵌套 dict，
    漏拦即泄漏。本实现递归遍历 dict/list/tuple，对其中所有字符串值脱敏，
    非字符串值（数字/布尔/None）保持原样，返回新结构（不修改入参）。

    2026-09-26 全面审查：字符串入参不再静默返回 {}（旧 _redact_scalars_dict
    兜底把整个值丢弃——脱敏形同虚设）：str 入参直接脱敏后包成 {"value": ...}
    保持"返回 dict"的签名契约，调用方取 ["value"] 消费。

    Args:
        data: 原始字典（值可含嵌套 dict / list / tuple / 标量）。

    Returns:
        脱敏后的新字典（嵌套结构同样被递归脱敏）。
    """
    if isinstance(data, dict):
        return {k: _redact_value(v) for k, v in data.items()}
    if isinstance(data, str):
        # 字符串入参：脱敏后包成单键 dict（保持签名 dict 契约，值不丢弃）
        return {"value": mask_sensitive_info(data)}
    return {}


def _redact_value(value: Any) -> Any:
    """递归脱敏任意嵌套结构（dict / list / tuple / 标量）。"""
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_redact_value(v) for v in value]
        return items if isinstance(value, list) else tuple(items)
    if isinstance(value, str):
        return mask_sensitive_info(value)
    return value


# 模块加载时自动配置根 logger
setup_logger_safety()
