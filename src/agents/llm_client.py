"""
LLM 客户端管理与调用工具模块。

封装与 LLM 交互的底层能力：
- ChatOpenAI / zai SDK 客户端实例缓存（连接池跨调用复用）
- 指数退避重试、敏感信息脱敏、token 使用统计
- LLM 配置获取（线程局部覆盖 + 全局回退）与 zai 兼容性检测
- LLM 文件缓存开关与目录解析

从 base_agent.py 拆分而来（代码可维护性优化）：BaseAgent 类保留在原模块，
通过 `from .llm_client import ...` 复用本模块工具函数，两者职责分离：
本模块专注「与外部 LLM 服务通信」，BaseAgent 专注「智能体通用行为封装」。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI

from config import LLM_CONFIGS, LLM_TIMEOUT, TEMPERATURE
from src.utils.env_utils import env_flag_opt_out

logger = logging.getLogger(__name__)

# 线程局部存储：用于在并发场景下为每个线程覆盖默认 LLM 配置
_thread_local = threading.local()

# ─── 魔数常量（统一管理，便于后续调整和注释来源）──────────────────────────
# zai SDK（智谱 BigModel）速率限制等待基准秒数：zai 限流比普通 API 更严格
_ZAI_RATE_LIMIT_WAIT_BASE_SECONDS = 5
# zai SDK 单次请求最大 token 数：glm-4.7-flash 模型上限
_ZAI_MAX_TOKENS = 4096
# 通用 LLM 调用单次最大重试次数（指数退避：1s, 2s, 4s）
_DEFAULT_LLM_MAX_RETRIES = 3


class LLMEmptyResponseError(RuntimeError):
    """LLM 返回空响应（content 与 reasoning_content 均为空）。

    确定性失败（同一 prompt / 参数下必然复现），不应按可重试的瞬态故障
    做指数退避——zai 路径 (Exception,) 兜底此前会把空响应误判为可重试，
    浪费 5+10+20=35s 墙钟才最终抛出。现作为模块级哨兵异常，zai 路径
    传入 non_retryable_exceptions=(LLMEmptyResponseError,) 立即抛出，
    交由调用方（base_agent._call_llm）按既有"空响应触发重试"语义处理
    （base_agent 的 OpenAI 路径本就对空响应 raise RuntimeError 触发同 API
    内的有限重试 + 跨模型故障转移，本异常仅消除 zai SDK 直连路径的
    无效指数退避，不改变跨模型切换行为）。
    """


# ─── LLM 客户端复用缓存（性能优化）────────────────────────────────────────────
# _call_llm 此前每次调用都新建 ChatOpenAI 实例，其底层 httpx 连接池随实例
# 创建/销毁，无法复用 TCP/TLS 连接；改为按 (model, temperature, api_key,
# base_url) 缓存实例，进程内复用连接，降低每次 LLM 调用的构建与握手开销。
# ChatOpenAI 内部客户端线程安全，可被并发任务（--parallel）共享。
# 缓存上限：配置组合数远小于 16，超出时按 FIFO 淘汰（防止 key 轮换场景膨胀）
_MAX_CACHED_LLM_CLIENTS = 16
# AD1：缓存键含 extra_body JSON（思考控制/输出上限参与键）
_llm_client_cache: dict[tuple[str, float, str, str, str], ChatOpenAI] = {}
# 缓存锁：get→构造→evict→insert 整段需原子，否则并发同 key miss 会各建一份
# 客户端（双份 httpx 连接池），且双线程同时触发 FIFO evict 时互相淘汰新插入
# 的实例（thrashing）。采用双检锁：无锁快路径命中直接返回，miss 时加锁再查
_llm_client_cache_lock = threading.Lock()


def json_output_mode_enabled() -> bool:
    """JSON Output 开关（DeepSeek `response_format={"type":"json_object"}`）。

    背景（2026-10-14，按 DeepSeek 官方文档 JSON Output 指南配置；触发：
    EMSE 批次日志中 Planner/Debugger 的 JSON 解析失败——`M10：LLM 未输出
    logic_analysis` 6 次/75 任务、`llm_json_parse_failed` 严格重试路径
    多次触发）：官方文档明确 JSON Output 保证响应为**合法 JSON 字符串**，
    并要求（a）提示中必须指示输出 JSON（各调用点提示均已含 "JSON" 与
    格式示例——已逐一核查）、（b）合理设置 max_tokens 防截断（本开关不
    改 max_tokens；截断由 finish_reason=length 守卫显式暴露并可重试）。

    环境变量（登记 docs/env_budget.yaml）：
    - LLM_JSON_MODE："on"（**默认**，减少结构化输出解析失败；对齐 AD1
      LLM_THINKING_MODE 的"行为默认值"先例）/ "off"（历史口径——不附加
      response_format，请求逐字节同历史批次，供旧批次复现/回归对照）。

    **作用面**：仅"期待结构化 JSON 的调用点"显式传 json_mode=True 时生效
    （Planner 测试计划 / Debugger 补丁与批评者/缺陷分类），代码生成类
    调用（Generator 测试、重采样补丁）不受影响——避免把代码输出强制成
    JSON。zai 兼容路径不支持该参数（保守忽略）。

    Returns:
        True = 对显式 json_mode 调用绑定 response_format；False = 历史口径。
    """
    raw = (os.getenv("LLM_JSON_MODE", "on") or "").strip().lower()
    return raw not in ("off", "0", "false", "disabled")


# finish_reason 异常值（DeepSeek 官方文档 Chat Completions）：length =
# 达到 max_tokens 截断；insufficient_system_resource = 推理资源不足中断。
# 两者均为"响应不完整"→ 按可恢复失败重试（而非把残缺内容交给下游解析）。
_ABNORMAL_FINISH_REASONS: frozenset[str] = frozenset({"length", "insufficient_system_resource"})


def _openai_extra_body() -> dict[str, Any]:
    """构建 OpenAI 兼容路径的额外请求体（AD1，2026-10-06 输出成本控制）。

    背景（实测证据）：R-P0-2 生死实验 aitester 臂输出 5.23M tokens、
    单任务最高 84k 输出，而实际工件（测试 + 补丁）仅 ~1-2k token——
    90%+ 输出为 deepseek V4 系（V4.1 Flash）**默认开启的思维链**
    （官方文档：thinking 默认 enabled；未设 max_tokens 时思考模式默认
    上限 64K；reasoning_tokens 计入 completion 输出计费）。zai 路径
    此前已硬编码 thinking disabled（跨服务商先例），本函数把同口径
    带到 OpenAI 兼容路径。

    环境变量（三者均登记 docs/env_budget.yaml）：
    - LLM_THINKING_MODE："disabled"（**默认**，对齐 zai 先例的成本保护）
      / "enabled"（质量敏感实验显式开启；R-P0-2 历史口径即默认开启）；
    - LLM_REASONING_EFFORT："none" / "low" / "high" / "max"（默认不发；
      none 亦关闭思考，low 为质量/成本折中）；
    - LLM_MAX_OUTPUT_TOKENS：输出硬上限 1..393216（默认不发——思考
      关闭后 V4 非思考默认 8K 已够；设小值可进一步截断长响应）。

    Returns:
        传给 ChatOpenAI extra_body 的字典（空字典 = 不附加任何额外字段）。
    """
    body: dict[str, Any] = {}
    mode = (os.getenv("LLM_THINKING_MODE", "disabled") or "").strip().lower()
    if mode in ("disabled", "enabled"):
        body["thinking"] = {"type": mode}
    effort = (os.getenv("LLM_REASONING_EFFORT", "") or "").strip().lower()
    if effort in ("none", "low", "high", "max"):
        body["reasoning_effort"] = effort
    mt_raw = (os.getenv("LLM_MAX_OUTPUT_TOKENS", "") or "").strip()
    if mt_raw:
        try:
            mt = int(mt_raw)
            if 1 <= mt <= 393216:
                body["max_tokens"] = mt
            else:
                logger.warning("LLM_MAX_OUTPUT_TOKENS=%s 越界（1..393216），忽略", mt_raw)
        except ValueError:
            logger.warning("LLM_MAX_OUTPUT_TOKENS=%s 非整数，忽略", mt_raw)
    return body


def _get_or_create_chat_client(model_name: str, temperature: float, api_key: str, base_url: str) -> ChatOpenAI:
    """获取（或创建）缓存的 ChatOpenAI 客户端实例。

    以 (model_name, temperature, api_key, base_url, extra_body) 为缓存键，
    相同组合复用同一实例，避免每次 LLM 调用重复构建 OpenAI SDK 客户端与
    HTTP 连接池；extra_body（AD1 思考控制/输出上限）参与键——进程内
    变更环境变量后能取到新配置的客户端（测试与多配置口径）。

    Args:
        model_name: 模型名称。
        temperature: 采样温度（与 config.TEMPERATURE 保持一致）。
        api_key: API 密钥。
        base_url: 服务 Base URL。

    Returns:
        ChatOpenAI 实例（缓存命中或新建）。
    """
    _extra_body = _openai_extra_body()
    key = (model_name, temperature, api_key, base_url, json.dumps(_extra_body, sort_keys=True))
    client = _llm_client_cache.get(key)
    if client is not None:
        return client
    with _llm_client_cache_lock:
        # 加锁后二次检查：并发窗口内其他线程可能已构造完同一 key
        client = _llm_client_cache.get(key)
        if client is not None:
            return client
        # langchain-openai 的 ChatOpenAI 接受 openai_api_key（与 OpenAI SDK 的
        # api_key 等价）；mypy 按严格 API 签名校验会报 call-arg，显式忽略。
        # extra_body 承载 DeepSeek V4 thinking 控制 / 输出上限（AD1）——
        # LangChain 透传给底层 OpenAI 兼容端点，空字典时透传 {} 等价无附加。
        client = ChatOpenAI(  # type: ignore[call-arg]
            model=model_name,
            temperature=temperature,
            openai_api_key=api_key,
            base_url=base_url,
            extra_body=_extra_body,
        )
        # 达到上限时淘汰最早插入的条目（dict 保持插入序，FIFO）
        if len(_llm_client_cache) >= _MAX_CACHED_LLM_CLIENTS:
            _llm_client_cache.pop(next(iter(_llm_client_cache)))
        _llm_client_cache[key] = client
    return client


# ─── zai SDK 客户端复用缓存（性能优化，与上方 ChatOpenAI 缓存同理）────────────
# ZhipuAiClient 继承自 OpenAI SDK 基类，底层共享一个线程安全的 httpx.Client
# （连接池可跨调用复用）；按 (api_key, base_url) 缓存实例，避免每次调用重建。
# model 是请求参数而非客户端属性，故不进缓存键。
_MAX_CACHED_ZAI_CLIENTS = 16
_zai_client_cache: dict[tuple[str, str], Any] = {}
# 线程锁：与上方 ChatOpenAI 缓存同款 DCL，防止并发首调时重复构造客户端
_zai_client_cache_lock = threading.Lock()


def _get_or_create_zai_client(api_key: str, base_url: str) -> Any:
    """获取（或创建）缓存的 zai SDK 客户端实例。

    以 (api_key, base_url) 为缓存键，相同组合复用同一实例，
    避免每次 zai 路径 LLM 调用都重建 ZhipuAiClient 与底层 httpx 连接池。
    双重检查锁保护，多线程并发首调时只构造一次。

    Args:
        api_key: API 密钥。
        base_url: 服务 Base URL。

    Returns:
        ZhipuAiClient 实例（缓存命中或新建）。

    Raises:
        ImportError: zai SDK 未安装时抛出（保持原 _call_zai 的延迟导入语义）。
    """
    # 延迟导入：避免未安装 zai SDK 时影响主程序启动
    from zai import ZhipuAiClient

    key = (api_key, base_url)
    # 第一次检查：无锁快速路径
    client = _zai_client_cache.get(key)
    if client is not None:
        return client
    with _zai_client_cache_lock:
        # 加锁后二次检查：并发窗口内其他线程可能已构造完同一 key
        client = _zai_client_cache.get(key)
        if client is not None:
            return client
        client = ZhipuAiClient(
            api_key=api_key,
            base_url=base_url,
        )
        # 达到上限时淘汰最早插入的条目（dict 保持插入序，FIFO）
        if len(_zai_client_cache) >= _MAX_CACHED_ZAI_CLIENTS:
            _zai_client_cache.pop(next(iter(_zai_client_cache)))
        _zai_client_cache[key] = client
    return client


def _retry_with_exponential_backoff(
    func: Callable[..., Any],
    max_retries: int,
    base_wait: int = 1,
    retryable_exceptions: tuple[type[Exception], ...] = (),
    non_retryable_exceptions: tuple[type[Exception], ...] = (),
    pre_retry_check: Callable[[], None] | None = None,
) -> Any:
    """带指数退避的重试通用工具函数。

    对给定函数执行带重试的调用，失败时按 2^attempt 秒指数退避等待后重试。
    可用于 _call_zai 和 _call_llm 中的重试逻辑，避免代码重复。

    Args:
        func: 要执行的函数（无参数或仅接受内部参数）。
        max_retries: 最大重试次数（不含首次尝试）。
        base_wait: 基础等待秒数（首次重试等待 base_wait，后续翻倍）。
        retryable_exceptions: 可重试的异常类型元组，为空则捕获所有异常。
        non_retryable_exceptions: 不可重试的异常类型元组（优先级高于
            retryable_exceptions）——命中即立即抛出，不重试。用于把
            "确定性失败"（如 LLM 空响应、客户端参数错误）与"瞬态失败"
            （限流 / 网络抖动 / 服务端 5xx）区分开，避免对必然失败的操作
            做无意义的指数退避（zai 路径 (Exception,) 兜底会误把空响应
            也按可重试处理，浪费 5+10+20=35s 墙钟才最终抛出）。
        pre_retry_check: A11（2026-10-18 第三方审查 P1）新增的可选回调——
            每次**实际重试前**调用（已判定可重试、退避等待之前）。调用方
            用它复查任务级预算（`is_budget_exceeded`）：上一响应即使被判
            "不可用"（finish_reason 异常 / 空响应），其 usage 也已记账
            （A11 同批修复），故重试前必须复查预算，超限即抛
            BudgetExceededError 快速失败，不再空烧 token。回调抛出的异常
            **直接向上传播**（不参与本函数的重试判定）。

    Returns:
        函数执行的返回值。

    Raises:
        RuntimeError: 所有重试均失败时抛出，携带最后一次异常信息。
        原始异常: 命中 non_retryable_exceptions 时立即抛出，不重试。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):  # attempt 0 是首次尝试
        try:
            return func()
        except Exception as e:
            # 非 retryable 异常立即抛出
            if retryable_exceptions and not isinstance(e, retryable_exceptions):
                raise
            # 不可重试的确定性失败立即抛出（优先级高于 retryable 兜底，
            # 否则 (Exception,) 兜底会把 non_retryable 也误判为可重试）
            if non_retryable_exceptions and isinstance(e, non_retryable_exceptions):
                raise
            last_error = e
            if attempt < max_retries:
                # A11：重试前复查预算（回调异常直接传播，不进重试计数）
                if pre_retry_check is not None:
                    pre_retry_check()
                # 指数退避：base_wait * 2^attempt（默认 1s → 1,2,4；zai base=5 → 5,10,20）
                # 此前误写为 base_wait**attempt：base_wait=1 时退化为固定 1s，zai 时膨胀为 5,25,125
                wait_time = base_wait * (2**attempt)
                logger.warning(
                    "调用失败 (attempt %d/%d): %s，等待 %.0fs",
                    attempt + 1,
                    max_retries + 1,
                    _redact_log_text(str(e)),
                    wait_time,
                )
                # 0.7 债务项 2.2 配套：重试等待计入全局墙钟预算由调用方
                # （_call_llm）判定；本函数保持无状态，仅负责退避语义
                time.sleep(wait_time)
            else:
                break
    raise RuntimeError(f"调用失败，已重试 {max_retries} 次: {last_error}") from last_error


def _redact_log_text(text: str) -> str:
    """对 LLM 调用路径的日志文本做敏感信息脱敏（P2-8）。

    SDK 异常消息可能携带请求头（含 Authorization: Bearer <api_key>）或
    带 key 的 URL 片段；此前这些文本直接拼进日志，handler 级脱敏过滤器
    只在 CLI 入口挂载，experiments 等非 CLI 入口下不生效。这里在
    LLM 调用的日志调用处直接脱敏，确保任何日志输出路径都不泄露凭证。

    实现统一委托给 logging_utils.redact_text（单一脱敏实现，
    与 api_manager._redact 同源，消除双套复制漂移风险）：
    logging_utils 是纯标准库模块（re 正则替换），顶层导入无循环依赖。

    Args:
        text: 待脱敏的日志文本（通常为异常字符串）。

    Returns:
        脱敏后的文本；脱敏器与兜底器均不可用时原样返回（不阻断主流程）。
    """
    from src.utils.logging_utils import redact_text

    return redact_text(text)


def _record_response_usage(usage: Any, model_name: str) -> bool:
    """将 LLM 响应的 token 使用量记入线程局部统计（容错：缺失字段记 0）。

    兼容两种响应结构：
    - LangChain usage_metadata 字典：input_tokens / output_tokens
    - OpenAI/zai usage 对象：prompt_tokens / completion_tokens

    5.4 改进：记账同时走任务级预算守卫（cost_budget.record_usage_and_check）——
    开关 COST_BUDGET_ENABLE=true 时消耗超限的调用使守卫返回 False（调用方
    据此在**下一次** LLM 调用前停止；本调用已发生，无法撤销）。

    Args:
        usage: 响应的 usage 字段（dict 或对象），可为 None。
        model_name: 模型名（用于 by_model 分桶）。

    Returns:
        True = 预算内（或预算开关关闭，历史口径）；False = 已超限。

    AT（2026-10-21）：不再 `int(... or 0)` 归一。缺席 / null 保持历史 0；bool /
    小数 / 数字字符串 / 负数 / 非有限原值交写入口 `count_reason` 判定。拒绝时
    调用已发生（`llm_calls` +1）但 token 不计入；**存在有效预算**（env 开关或
    实例级 cap，N02 起口径统一）时锁存 `budget.exceeded` 并抛不可重试的
    `BudgetAccountingError`；无有效预算则披露后继续（历史"静默忽略"只保留给
    真正无约束的记账异常）。
    """
    if not usage:
        return True
    # N02：预算异常类型需在 except 分支可见（延迟导入，保持模块加载零依赖）
    from src.budget.cost_budget import BudgetExceededError

    try:
        from src.budget.token_usage import record_usage

        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        else:
            input_tokens = getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "completion_tokens", 0)
        if input_tokens is None:
            input_tokens = 0
        if output_tokens is None:
            output_tokens = 0
        reasons = record_usage(input_tokens, output_tokens, model=model_name)
        if reasons:
            # N02（2026-10-22 第三方复审 P1）：拒绝分支必须与"有效预算"同口径。
            # 历史实现只查 COST_BUDGET_ENABLE，导致 set_task_token_cap() 注入的
            # 实例级 cap（AM1：cap 自足生效，无需 env 开关）被绕过——坏 usage
            # 既不累计也不锁死，重试/故障转移继续付费。
            # 现：存在有效预算 → 锁存 exceeded（后续前置守卫/重试复查必停）+
            # 抛不可重试的 BudgetAccountingError；无有效预算 → 保持历史披露口径。
            from src.budget.cost_budget import BudgetAccountingError, budget_effective, mark_budget_exceeded

            if budget_effective():
                mark_budget_exceeded("token 写入被拒绝: " + ",".join(reasons))
                raise BudgetAccountingError(reasons)
            return True
        # 5.4 预算守卫（默认关：未启用时 check_budget 恒 True，零行为变化）。
        # D1（N-5，2026-10-17）：USD 生产记账接线——N-4 实测此路径只传 token、
        # consumed_delta_usd 恒 0 → COST_BUDGET_USD 永不触发（纸面开关）。
        # 现预算启用时按价目表（experiments/price_table.json，回退
        # COST_USD_PER_1K）计算本次调用 USD 增量并交给 record_usage_and_check：
        # token 与 USD 两通道在同一 `budget.exceeded` 标志上触发停止通道
        # （后续 LLM 调用在 BaseAgent._call_llm 前置守卫抛 BudgetExceededError）。
        # 价目不可用 → 不编造价格：note_usd_pricing_unavailable 记事件+一次性
        # WARNING（可区分"USD 未触发"与"根本没计价"）。
        from src.budget.cost_budget import _budget_enabled, note_usd_pricing_unavailable, record_usage_and_check

        usd_cost = 0.0
        if _budget_enabled():
            from src.budget.pricing import estimate_usd

            estimated_usd, pricing_source = estimate_usd(model_name, input_tokens, output_tokens)
            if estimated_usd is None:
                note_usd_pricing_unavailable(model_name)
            else:
                usd_cost = float(estimated_usd)
                logger.debug(
                    "D1 USD 记账：model=%s tokens=%d/%d usd=%.8f source=%s",
                    model_name,
                    input_tokens,
                    output_tokens,
                    usd_cost,
                    pricing_source,
                )
        return record_usage_and_check(input_tokens, output_tokens, usd_cost=usd_cost)
    except BudgetExceededError:
        # N02（2026-10-22 第三方复审 P1）：预算类异常是**控制流信号**，绝不能被
        # 下方 O14 的 fail-closed 包装吞掉或降级成普通 RuntimeError——否则：
        # ① env 关闭但实例 cap 生效时会被 `return True` 静默放行（分支 B）；
        # ② env 开启时被包装为可重试 RuntimeError，重试器会再次发起请求。
        raise
    except Exception as e:  # O14（2026-09-29 审查 P0）：记账异常 fail-closed。
        # 历史口径：except Exception: return True（统计失败不影响主流程）——
        # 缺陷：记账层任何异常（含磁盘满 / import 失败）都会静默把
        # check_budget 短路为"预算内"，使 COST_BUDGET_ENABLE 守卫可永久
        # 失效且无告警。现改为 fail-closed：COST_BUDGET_ENABLE=true 时记账
        # 异常直接上抛（让调用方感知守卫不可用），默认关时保持历史
        # "静默忽略"口径（零行为变化）。
        from src.budget.cost_budget import _budget_enabled as _cb_enabled

        if _cb_enabled():
            logger.exception("O14 预算记账异常（fail-closed）: %s", e)  # noqa: TRY401 — %s 仅取 str 摘要（traceback 由 exception 自带）
            raise RuntimeError(f"预算记账异常（fail-closed）: {e}") from e
        logger.debug("token 统计记录失败（忽略）: %s", e)
        return True


def _budget_exceeded_error() -> Exception:
    """A11（2026-10-18 第三方审查 P1）：任务级预算超限异常工厂（单一实现）。

    历史实现只存在于 `base_agent._budget_exceeded_error()`（惰性构造避免模块
    加载期依赖 cost_budget）；A11 后 llm_client 的 zai 路径也要在**重试前**
    复查预算并抛同一异常，故工厂上移到本模块、base_agent 委托调用——两条
    调用路径共用一份单位口径（D1：USD 取 consumed_usd/usd_limit，否则
    token 口径），异常消息不会把 token 数当美元展示。

    Returns:
        BudgetExceededError 实例（延迟构造：cost_budget 仍只在调用期导入）。
    """
    from src.budget.cost_budget import BudgetExceededError, get_budget_stats

    stats = get_budget_stats()
    unit = str(stats.get("unit", "none"))
    if unit == "usd":
        return BudgetExceededError(
            consumed=float(stats.get("consumed_usd", 0.0)),
            limit=float(stats.get("usd_limit", 0.0)),
            unit="usd",
        )
    return BudgetExceededError(
        consumed=int(stats.get("consumed_tokens", 0)),
        limit=int(stats.get("token_limit", 0)),
        unit=unit,
    )


def _raise_if_budget_exceeded() -> None:
    """A11：重试前预算复查回调（超限即抛，供 `_retry_with_exponential_backoff`）。

    背景：A11 后"收到响应立即记账"——即使是 finish_reason 异常 / 空响应，
    其已发生的 token 消耗也已入账。此时继续在同一 API 内指数退避重试或
    跨模型故障转移，可能在预算已耗尽后继续烧 token；故每次**实际重试前**
    复查任务级预算（COST_BUDGET_ENABLE 默认 false 时 `is_budget_exceeded()`
    恒 False，零行为变化）。
    """
    from src.budget.cost_budget import is_budget_exceeded

    if is_budget_exceeded():
        raise _budget_exceeded_error()


# 智谱系域名判定（bigmodel.cn / zhipuai）
# 2026-09-26 优化：模块级预编译 alternation 正则（此前每次 _is_zai_compatible
# 调用都重建 list + `any` 子串扫描；--parallel 多任务热路径上 LLM 路由决策
# 每次调用 2 次）。一次 O(n) 扫描，模块加载期预编译一次，调用零分配。
# bigmodel.cn 为真实域名：. 必须字面匹配（转义为 \.），否则 bigmodelXcn
# 等 URL 会误命中；zhipuai 为纯子串特征（无元字符，保持原扫描口径）。
_ZAI_DOMAIN_RE = re.compile(r"bigmodel\.cn|zhipuai")


def _is_zai_compatible(base_url: str) -> bool:
    """判断是否为 zai SDK 兼容的 API（如 BigModel 智谱）。

    OpenAI 兼容接口返回 401 但 zai SDK 可用的服务商需走特殊路径。
    检测逻辑：检查 base_url 中是否包含智谱域名的特征字符串。

    Args:
        base_url: 模型服务的 Base URL（如 "https://open.bigmodel.cn/api/..."）。

    Returns:
        True 表示需使用 zai SDK 路径；False 使用标准 LangChain ChatOpenAI。
    """
    # 预编译 alternation 正则（模块加载期编译一次）；子串命中口径与历史
    # `any(d in base_url for d in ("bigmodel.cn", "zhipuai"))` 等价
    # （"bigmodel.cn" 中 "." 字面匹配，与 in 子串扫描一致）
    return bool(_ZAI_DOMAIN_RE.search(base_url))


def _call_zai(
    api_key: str,
    base_url: str,
    model_name: str,
    system_prompt: str,
    user_message: str,
    max_retries: int = _DEFAULT_LLM_MAX_RETRIES,
    temperature: float = TEMPERATURE,
) -> str:
    """使用 zai SDK 调用 LLM（用于 BigModel 等非 OpenAI 兼容接口）。

    F09（2026-10-19 第三方审查 P1）修复：zai 路径此前**不发送** temperature，
    而缓存身份（base_agent._effective_request_identity）按"实际生效采样温度"
    记录显式覆盖值 / config.TEMPERATURE——请求身份与真实请求不一致（同一
    prompt 在改变温度后仍可能命中旧缓存）。现 `temperature` 参与
    ``create(temperature=...)``，调用方（base_agent._call_llm）传入
    ``eff_temperature``，两条调用路径（OpenAI 兼容 / zai）对温度口径一致。
    zai SDK（zai-sdk>=0.2.0）的 ``chat.completions.create`` 支持
    ``temperature: Optional[float]`` 命名参数（静态核对 0.2.3 签名）。

    实现带指数退避的重试策略：
    - 所有可重试异常统一按 base_wait=5s 指数退避：等待 5 * 2^attempt 秒（5s, 10s, 20s ...）。
      因 _ZAI_RETRYABLE_EXCEPTIONS 含 Exception（兜底捕获全部异常），zai 限流（APIReachLimitError）
      与普通 API 错误（APIStatusError）不做区分，一律使用 5s 基准（zai 限速严格，取较长基准）。
    - 空响应（LLMEmptyResponseError）为确定性失败，**不参与**上述指数退避——
      通过 non_retryable_exceptions 立即向上抛出（5+10+20=35s 墙钟浪费消除），
      交由调用方（base_agent._call_llm）按既有"空响应触发同 API 内有限重试
      + 跨模型故障转移"语义处理。

    Args:
        api_key: API Key 凭证字符串。
        base_url: API Base URL。
        model_name: 模型名称（如 "glm-4.7-flash"）。
        system_prompt: System Prompt，定义模型角色和行为约束。
        user_message: 用户消息内容。
        max_retries: 最大重试次数，默认 3 次。
        temperature: 采样温度（F09：实际发送给 SDK 的 create(temperature=...)，
            默认 config.TEMPERATURE；生产调用点传 base_agent 的 eff_temperature）。

    Returns:
        LLM 返回的文本内容（已 strip 空白）。

    Raises:
        RuntimeError: 所有重试均失败时抛出，携带最后一次异常信息。
    """
    # 延迟导入：避免未安装 zai SDK 时影响主程序启动
    # （APIReachLimitError / APIStatusError 均为 Exception 子类，
    #  重试元组直接以 Exception 兜底，无需逐个列举——子类在 except 中
    #  被基类覆盖，列举属死代码）
    from zai.core._errors import APIReachLimitError, APIStatusError  # noqa: F401

    # A11：预算超限异常（重试前复查预算抛出）需原样向上传播，不包装成
    # "zai API 调用失败"（避免被上层误判为 API 故障继续故障转移）
    from src.budget.cost_budget import BudgetExceededError

    # 复用缓存的智谱 AI 客户端（连接池跨调用复用）
    client = _get_or_create_zai_client(api_key, base_url)

    # 定义 zai SDK 特有的可重试异常类型：限流（APIReachLimitError）/
    # 服务端错误（APIStatusError）均按 Exception 兜底捕获，不做区分，
    # 统一走指数退避（zai 限速严格，取较长基准 5s）
    _ZAI_RETRYABLE_EXCEPTIONS = (Exception,)

    def _do_zai_call() -> str:
        """执行单次 zai API 调用（内部辅助函数）。

        F09：temperature 必须与 OpenAI 兼容路径同口径实际发出——缓存身份
        （base_agent._effective_request_identity）按实际生效温度分区，若此处
        静默丢弃温度，身份记录将与真实请求不一致。
        """
        kwargs: dict[str, Any] = {"thinking": {"type": "disabled"}}
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=_ZAI_MAX_TOKENS,
            temperature=temperature,
            timeout=LLM_TIMEOUT,
            **kwargs,
        )
        # A11（2026-10-18 第三方审查 P1）：收到响应**立即**记账，再做可用性
        # 判定。历史实现先判空响应、后 `_record_response_usage`——带 usage 的
        # 空响应/截断响应抛错后 usage 漏记，且重试/故障转移继续烧 token 时
        # 消耗统计系统性偏低。记账早于任何 raise 后，无论本次响应最终是否
        # 可用，其已发生的 token 消耗都入账（与 OpenAI 路径同序）。
        _record_response_usage(getattr(response, "usage", None), model_name)
        msg = response.choices[0].message
        # 优先取 content（普通响应），回退到 reasoning_content（深度思考内容）
        text = (msg.content or msg.reasoning_content or "").strip()
        if not text:
            # 空响应是确定性失败（同 prompt 必然复现），不属于可重试的
            # 瞬态故障——抛模块级哨兵 LLMEmptyResponseError，由
            # _call_zai 的 non_retryable_exceptions 立即向上抛出，
            # 避免 (Exception,) 兜底误判为空响应可重试而做无效指数退避。
            raise LLMEmptyResponseError("LLM 返回空响应")
        logger.info("zai API 调用成功 (model=%s)", model_name)
        return text

    try:
        # 使用通用重试工具函数，zai 限流时使用更长的等待基准（5秒）。
        # non_retryable_exceptions 把"空响应"（LLMEmptyResponseError）排除在
        # 指数退避之外：该错误是确定性失败，重试必然复现，立即抛出交
        # 调用方（base_agent._call_llm）按既有"空响应触发同 API 内有限
        # 重试 + 跨模型故障转移"语义处理，不再浪费 5+10+20=35s 墙钟。
        # A11：pre_retry_check 在每次重试前复查任务级预算（上一响应即使被判
        # 不可用，其 usage 也已记账；超限则快速失败而非继续重试烧 token）。
        return _retry_with_exponential_backoff(
            func=_do_zai_call,
            max_retries=max_retries,
            base_wait=_ZAI_RATE_LIMIT_WAIT_BASE_SECONDS,  # zai 限流基准 5 秒
            retryable_exceptions=_ZAI_RETRYABLE_EXCEPTIONS,
            non_retryable_exceptions=(LLMEmptyResponseError, BudgetExceededError),
            pre_retry_check=_raise_if_budget_exceeded,
        )
    except BudgetExceededError:
        # A11：预算超限是控制流信号（不属 API 故障），不得被包装成普通
        # RuntimeError 后交给上层故障转移继续尝试其他模型（那样会绕过预算闸）。
        raise
    except Exception as e:
        # 重新抛出带有明确上下文的异常（异常文本可能含请求头凭证，先脱敏）
        raise RuntimeError(f"zai API 调用失败: {_redact_log_text(str(e))}") from e


def _thread_local_api_override() -> tuple[str, str, str] | None:
    """A10（2026-10-18 第三方审查 P1）：读取线程局部指定的 LLM 配置三元组。

    线程局部存储由 `experiments/run_benchmark.py::_set_thread_api` 在任务
    分配时写入（api_key / base_url / model_name），用于 `--parallel` 下每个
    任务线程使用自己的端点。历史缺陷：生产请求链 `_call_llm` 读
    `_get_all_api_configs()`——后者只枚举全局 `LLM_CONFIGS`，线程局部指定
    配置从未进入真实请求链（任务被"分配"给 B，实际仍按全局首配置 A 请求），
    而缓存/来源标签却经 `get_first_valid_model_name()` 取到了 B。

    回退口径与 `_get_llm_config` 逐字节一致：未显式覆盖的字段对称回退
    `LLM_CONFIGS[0]`；`api_key` 为空（无覆盖）时返回 None。

    Returns:
        (api_key, base_url, model_name)；无线程局部覆盖时 None。
    """
    api_key = getattr(_thread_local, "api_key", "")
    if not api_key:
        return None
    model = getattr(_thread_local, "model_name", "") or (LLM_CONFIGS[0].model_name if LLM_CONFIGS else "")
    base_url = getattr(_thread_local, "base_url", "") or (LLM_CONFIGS[0].base_url if LLM_CONFIGS else "")
    return (api_key, base_url, model)


def _get_llm_config() -> tuple[str, str, str]:
    """获取当前线程使用的 LLM 配置，优先返回线程局部覆盖值。

    线程局部覆盖用于并发场景下不同线程使用不同的 API Key/模型。
    若未设置线程局部值，则回退到配置文件中的第一个 LLM_CONFIGS。

    Returns:
        (api_key, base_url, model_name) 三元组；配置缺失时返回空字符串。
    """
    # 优先使用线程局部覆盖的配置（由测试或并发场景设置）
    override = _thread_local_api_override()
    if override is not None:
        return override
    # 回退到全局配置（按优先级取第一个有效配置）
    if LLM_CONFIGS:
        cfg = LLM_CONFIGS[0]
        return cfg.api_key, cfg.base_url, cfg.model_name
    # 无任何配置时返回空串（调用方应捕获并抛出 RuntimeError）
    return "", "", ""


def get_first_valid_model_name() -> str | None:
    """M8（2026-09-29 审查 P0）：返回当前线程/全局 LLM 配置链中第一个有效的
    model_name，供缓存隔离键使用。

    行为：
    - 线程局部覆盖值存在（_thread_local.model_name 非空）→ 直接返回；
    - 否则回退到 LLM_CONFIGS[0].model_name（若 LLM_CONFIGS 非空）；
    - 无任何配置时返回 None（调用方跳过隔离键材料，保持历史行为）。

    用于 AITESTER_CACHE_ISOLATE_MODEL=1 时把"当前模型命名空间"加入
    缓存键，消除跨模型缓存串味（见 base_agent._call_llm_with_cache 的
    M8 隔离逻辑）。

    A10（2026-10-18 第三方审查 P1）：本函数只返回"首个有效模型名"标签，
    真实请求链的配置优先级由 `_get_all_api_configs()` 统一（线程局部 >
    全局；标签与真实首请求一致，见该函数 docstring）。
    """
    if getattr(_thread_local, "model_name", ""):
        return _thread_local.model_name
    if LLM_CONFIGS:
        return LLM_CONFIGS[0].model_name
    return None


def _get_all_api_configs() -> list[tuple[str, str, str]]:
    """获取所有可用的 API 配置列表（按优先级排列）。

    用于 _call_llm 的 API 自动切换逻辑：当主 API 失败时依次尝试备用 API。

    A10（2026-10-18 第三方审查 P1）修复：**线程局部指定的配置优先**。
    历史实现只枚举全局 `LLM_CONFIGS`——`run_benchmark._set_thread_api` 为
    任务写入的线程局部端点从未进入生产请求链（真实请求仍从全局首配置
    开始），而缓存标签却取线程局部模型名，导致"分配与实际/标签脱节"。
    现口径：
    1. 线程局部完整三元组存在（api_key/base_url/model_name，缺失字段按
       `_get_llm_config` 同款回退）→ 作为**首个**请求配置；
    2. 全局 `LLM_CONFIGS` 其余配置原序跟在后面——线程局部端点失败时仍按
       既定全局链故障转移（行为不倒退）；
    3. 线程局部配置与全局某项完全相同时不重复（避免同一端点试两遍）；
    4. 无线程局部覆盖 / 覆盖不完整（缺 api_key/base_url/model）→ 返回全局
       链（历史口径，绝不注入半截配置遮蔽可用全局端点）。

    2026-10-19 复核残留补修（A10）：历史实现当 override **恰为全局列表已有
    项**时直接 `return global_configs`，正常轮询（全局 [A, B]、任务分配 B）
    下分配被静默丢弃。现统一为"override 居首 + 全局其余原序去重"——两条
    分支同一语义，正常轮询形状与"override 在全局之外"形状不再分叉。

    Returns:
        列表，每项为 (api_key, base_url, model_name)，仅包含已配置的项。
        若 LLM_CONFIGS 为空且无线程局部覆盖则返回空列表。
    """
    global_configs = [(c.api_key, c.base_url, c.model_name) for c in LLM_CONFIGS]
    override = _thread_local_api_override()
    # 仅完整三元组才进入请求链（半截配置请求必然失败，不应排在可用全局端点前）
    if override is None or not all(override):
        return global_configs
    # 首请求 = 显式分配；全局其余配置按原序跟随（故障转移行为不倒退），
    # 完全相同的三元组只保留一次。
    return [override, *(cfg for cfg in global_configs if cfg != override)]


# ─── A10：实际请求身份记录（provenance / 缓存标签）────────────────────────────
# 背景（2026-10-18 第三方审查 P1）：缓存/provenance 标签必须描述**真实发出
# 的请求**，而不是"本来想发的请求"。多端点故障转移场景下首选端点 B 失败、
# 备用端点 A 成功时，缓存条目的"请求身份"是 B（查找键），而"响应来源"是 A
# （真实消耗与输出所属端点）。本组函数记录本线程最近一次成功返回的真实配置，
# 供 base_agent 写入缓存 payload（response_identity）与日志；api_key 只留
# 内存线程局部（绝不进入缓存文件/工件）。
def _record_actual_request_config(api_key: str, base_url: str, model_name: str) -> None:
    """记录本线程最近一次真实发出并成功返回的 LLM 请求配置（内存 only）。"""
    _thread_local.last_request_config = (api_key, base_url, model_name)


def get_last_request_config() -> tuple[str, str, str] | None:
    """读取本线程最近一次成功请求的 (api_key, base_url, model_name)。

    Returns:
        三元组；本线程尚无成功请求记录时 None（调用方按未知来源处理）。
    """
    return getattr(_thread_local, "last_request_config", None)


def clear_last_request_config() -> None:
    """清除本线程的"最近成功请求"记录（每次 _call_llm 调用前调用，防陈旧）。"""
    with contextlib.suppress(AttributeError):
        delattr(_thread_local, "last_request_config")


# ─── A09：规范化的"有效请求身份"（缓存键材料 / 语义索引分区）──────────────────
# 2026-10-18 第三方审查 P1：精确缓存键与语义缓存都必须以**实际生效的请求身份**
# 隔离——同一 prompt 在"有效默认温度 / thinking / reasoning_effort / max_tokens /
# JSON 输出模式实际生效值 / 模型与端点 / 实验 namespace"任一不同时，响应不可
# 互换，不得命中彼此缓存。这里把身份规范化为可 JSON 序列化的 dict，并提供
# 稳定材料（供精确键哈希）与短指纹（供语义索引分区过滤，避免长串散列成本）。
def request_identity_material(identity: dict[str, Any] | None) -> str:
    """把请求身份 dict 规范化为稳定排序的 JSON 材料（确定性哈希输入）。

    规范化口径（同一身份必然产出逐字节相同材料）：
    - `sort_keys=True`：dict 键序不影响身份；
    - `separators=(",", ":")`：紧凑分隔符，无空白抖动；
    - `ensure_ascii=False`：中文模型名/路径按原字符参与哈希（UTF-8 编码）；
    - `default=str`：异常类型（如未来加入的枚举）降级为字符串而非抛错。

    Args:
        identity: `base_agent._effective_request_identity()` 产出的身份 dict。

    Returns:
        规范化 JSON 字符串；identity 为 None/空时返回空串（无身份材料）。
    """
    if not identity:
        return ""
    return json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def request_identity_fingerprint(identity: dict[str, Any] | None) -> str:
    """请求身份的短指纹（md5 前 16 位十六进制），供语义索引分区过滤。

    与 `request_identity_material()` 同源（同一规范化 JSON），故精确缓存键与
    语义缓存分区使用同一身份定义，不会出现"精确层隔离、语义层串味"的口径分裂。

    Args:
        identity: 请求身份 dict。

    Returns:
        16 位十六进制指纹；identity 为空时返回空串（调用方按"无身份"处理）。
    """
    material = request_identity_material(identity)
    if not material:
        return ""
    return hashlib.md5(material.encode("utf-8")).hexdigest()[:16]


# ─── LLM 文件缓存开关（省 token）────────────────────────────────────────────
# 默认启用；设环境变量 AITESTER_LLM_CACHE=0 可关闭（测试环境用于隔离，避免 flaky）。
# 缓存目录可用 AITESTER_LLM_CACHE_DIR 覆盖（便于测试指向临时目录）。
# 开关与目录均在每次调用时读取，便于测试用 monkeypatch.setenv 动态切换。
# 2026-10-05 审查修复（运行时缓存迁出源码树）：默认目录从 src/cache/ 改为
# 用户缓存目录（XDG_CACHE_HOME 或 ~/.cache/aitester/llm）——此前运行时
# 缓存写进源码树（src/cache/*.json，gitignore 挡 git 但污染源码树、且
# 打包/分发口径含混）。历史 src/cache/ 的既有缓存不自动迁移（迁移涉及
# 2200+ 文件的 rename，收益一次性），需要保留历史命中时显式设：
#   AITESTER_LLM_CACHE_DIR=<repo>/src/cache
_LLM_CACHE_DIR_DEFAULT = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")),
    "aitester",
    "llm",
)

# 18. 缓存安全（改进清单 P1）：缓存文件内容含完整 prompt + LLM 响应（可能夹带
# 敏感代码片段）。默认目录创建为 0o700、缓存文件写为 0o600，确保仅当前用户
# 可读（本地可信域仍不进 git，权限收缩是纵深防御）；测试经
# AITESTER_LLM_CACHE_DIR 指向临时目录时权限同样生效，不影响隔离。
_LLM_CACHE_DIR_MODE = 0o700
_LLM_CACHE_FILE_MODE = 0o600

# 19. 缓存创建者归属（外部数据支撑：Clinejection 事件——恶意 issue 标题经
# prompt injection 污染构建缓存后跨工作流向 4000 名开发者推送恶意版本；
# KeyPooling 研究——API 网关共享凭据可致全局缓存共享）。"本地可信域"假设
# 在共享 CI / 多用户机器上不成立：缓存文件头部写入创建者 uid，读侧校验
# 归属，非本用户创建的条目一律不命中（防跨用户缓存投毒），并记录告警。
# 历史无 creator 字段的文件按"同 uid 兼容"处理（不破坏既有 2200+ 缓存文件）；
# uid 不可得（Windows 等）时不写校验（降级为历史口径，权限位 0600 仍生效）。
_CREDENTIAL_CREATOR_FIELD = "creator_uid"
# 创建者标签可经环境变量显式指定（多用户共享缓存目录 / CI 场景覆盖默认 uid）
_CACHE_CREATOR_ENV = "AITESTER_CACHE_CREATOR"


def _cache_creator_uid() -> int | None:
    """当前用户 uid（POSIX）；不可得时 None（读侧跳过归属校验）。"""
    try:
        return os.getuid()
    except (AttributeError, OSError):
        return None


def _cache_creator_label() -> str:
    """缓存条目创建者标识（写入文件头部的 creator_uid 字段）。

    优先取 AITESTER_CACHE_CREATOR 显式覆盖（共享 CI / 多租户部署可为不同
    身份注入独立标签实现逻辑隔离）；否则取当前 uid；uid 不可得时返回
    空串（读侧跳过校验，历史口径）。
    """
    override = os.environ.get(_CACHE_CREATOR_ENV, "").strip()
    if override:
        return override
    uid = _cache_creator_uid()
    return str(uid) if uid is not None else ""


def cache_creator_ok(stored_uid: Any) -> bool:
    """读侧创建者归属校验（19. 防跨用户缓存投毒，Clinejection 教训）。

    规则（与写侧 _cache_creator_label 同源，避免键派生漂移）：
    - 当前创建者标签为空（uid 不可得且未显式覆盖）→ 恒 True（跳过校验，
      历史口径）；
    - 条目无 creator_uid 字段（历史文件）或值为空串 → True（兼容）；
    - 条目 creator_uid 与当前标签一致 → True；不一致 → False（不命中，
      该条目疑似被其他用户/CI 步骤写入，按投毒面处理）。

    供 base_agent 文件命中校验与测试直接消费（纯函数，零副作用）。
    """
    expected = _cache_creator_label()
    if not expected:
        return True
    if stored_uid is None or stored_uid == "":
        return True
    return str(stored_uid) == expected


def ensure_llm_cache_dir(cache_dir: str | None = None) -> str:
    """创建 LLM 缓存目录（0o700 权限）并返回其路径。

    权限口径（18. 缓存安全）：目录以 0o700 创建；已存在时不强制收敛权限——
    历史目录可能经其他工具/用户建在共享位置（强制 chmod 在 NFS/挂载卷上
    可能失败或误伤共享语义，且读侧 LRU / 负缓存不受影响）；新建目录才是
    敏感暴露面的新增点，此处保证"新增即收敛"。

    Args:
        cache_dir: 目标目录；None 时读 _llm_cache_dir()。

    Returns:
        缓存目录路径（保证目录已存在）。
    """
    target = cache_dir or _llm_cache_dir()
    if not os.path.isdir(target):
        os.makedirs(target, exist_ok=True)
        with contextlib.suppress(OSError):
            # 权限收敛失败（如 Windows / 挂载卷不支持）不阻断主流程
            os.chmod(target, _LLM_CACHE_DIR_MODE)
    return target


def secure_cache_file(tmp_path: str) -> None:
    """缓存临时文件写盘后收敛权限到 0o600（os.replace 前调用）。

    失败不阻断（非 POSIX 文件系统）；调用方在原子替换前调用，使最终
    缓存文件权限为 0o600（0o600 的临时文件经 os.replace 后权限保留）。
    """
    with contextlib.suppress(OSError):
        os.chmod(tmp_path, _LLM_CACHE_FILE_MODE)


def _llm_cache_ttl_days() -> int:
    """缓存过期清理 TTL（天）：AITESTER_LLM_CACHE_TTL_DAYS，默认 7。

    负数 / 0 表示不启用过期清理（历史口径）；正数 = 保留最近 N 天的
    缓存条目。读环境变量便于测试动态切换。
    """
    try:
        days = int(os.environ.get("AITESTER_LLM_CACHE_TTL_DAYS", "7"))
    except ValueError:
        days = 7
    return days


def cleanup_expired_cache_files(max_age_days: int | None = None) -> int:
    """清理过期的 LLM 缓存文件（18. 缓存过期清理机制）。

    按 mtime 删除早于 TTL 的 `*.json` 缓存文件（含 cross_file 修复计划
    缓存——同目录同口径），避免缓存目录长期积累敏感数据（完整 prompt +
    响应可能夹带代码片段）。默认 TTL = AITESTER_LLM_CACHE_TTL_DAYS（7 天）；
    max_age_days<=0 或 None 且 TTL<=0 时跳过（历史口径）。

    Args:
        max_age_days: 显式 TTL 覆盖（天）；None 时读环境变量。

    Returns:
        实际删除的文件数（扫描失败 / 过期清理未启用时返回 0，不抛异常——
        清理是卫生性操作，不得阻断 LLM 调用主流程）。
    """
    import time

    days = _llm_cache_ttl_days() if max_age_days is None else int(max_age_days)
    if days <= 0:
        return 0
    try:
        cache_dir = _llm_cache_dir()
        if not os.path.isdir(cache_dir):
            return 0
        cutoff = time.time() - days * 86400
        removed = 0
        for name in os.listdir(cache_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(cache_dir, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.unlink(path)
                    removed += 1
            except OSError:
                continue  # 并发删除 / 权限问题不阻断
        return removed
    except OSError:
        return 0


# ─── 15. 多进程缓存协调（改进清单 P2）：进程内 LLM 文件缓存命中率观测 ─────
# 多进程（--parallel / multiprocessing）下每个 worker 进程独立持有进程内
# LRU / 负缓存，跨进程命中只能靠文件（事实来源）。"负缓存 TTL 30s 内同键
# 跳过文件重读"的保守退化会在高频重复任务（benchmark 相同函数）造成少量
# 重复 LLM 调用。本观测层记录每个进程视角的文件缓存命中率，供
# get_workflow_stats 报告；命中率低于阈值时，运维侧可据此切换到"主进程
# 预热缓存 + 共享目录"或单进程顺序模式（见 performance_guide §多进程缓存）。
_LLM_CACHE_HIT_STATS: dict[str, int] = {"file_hits": 0, "file_misses": 0}
_LLM_CACHE_HIT_STATS_LOCK = threading.Lock()


def record_cache_hit(hit: bool) -> None:
    """记录一次 LLM 文件缓存命中/未命中（15. 多进程缓存协调观测层）。

    线程安全（--parallel 多任务并发调用）；命中率 = file_hits /
    (file_hits + file_misses)，供 get_workflow_stats 与性能基准消费。

    Args:
        hit: True = 文件缓存命中（含 LRU/语义缓存快路径），False = 未命中
            （发生了一次真实 LLM 调用）。
    """
    with _LLM_CACHE_HIT_STATS_LOCK:
        if hit:
            _LLM_CACHE_HIT_STATS["file_hits"] += 1
        else:
            _LLM_CACHE_HIT_STATS["file_misses"] += 1


def get_cache_hit_rate() -> float | None:
    """返回本进程视角的 LLM 文件缓存命中率（0.0-1.0）；无任何记录时 None。

    多进程模式下每进程各自返回本地命中率（跨进程需聚合各 worker 的
    返回值，见 performance_guide）；命中率 < 阈值（如 0.5）时建议切换为
    "主进程预热缓存 + 共享目录"或单进程顺序执行（避免重复 LLM 调用）。
    """
    with _LLM_CACHE_HIT_STATS_LOCK:
        hits = _LLM_CACHE_HIT_STATS["file_hits"]
        misses = _LLM_CACHE_HIT_STATS["file_misses"]
        total = hits + misses
        return (hits / total) if total else None


def reset_cache_hit_stats() -> None:
    """清零进程内 LLM 文件缓存命中/未命中计数（15. 多进程缓存协调观测层）。

    供测试 / 每个 benchmark 批次边界调用（命中率口径按批次独立，不跨批次
    累计）；生产代码通常无需调用（批次边界由 run_benchmark 隐式重置）。
    """
    with _LLM_CACHE_HIT_STATS_LOCK:
        _LLM_CACHE_HIT_STATS["file_hits"] = 0
        _LLM_CACHE_HIT_STATS["file_misses"] = 0


def _llm_cache_enabled() -> bool:
    """是否启用 LLM 文件缓存（默认启用，设 AITESTER_LLM_CACHE=0 关闭）。

    2026-09-28 性能优化：开关值进程内记忆（首次调用读取环境变量，之后复用
    记忆值——热路径每次 LLM 调用都读本开关 + _llm_cache_dir）。语义保持
    "开关在进程运行中生效"的保守口径不变：环境变量变更由
    clear_llm_cache_option_memory()（base_agent.clear_llm_lru_cache 一并触发）
    显式清除记忆后重新读取（测试环境经 conftest 在 env 切换时调用）。
    """
    global _llm_cache_option_memory
    if _llm_cache_option_memory is not None:
        return _llm_cache_option_memory
    _llm_cache_option_memory = env_flag_opt_out("AITESTER_LLM_CACHE")
    return _llm_cache_option_memory


_llm_cache_option_memory: bool | None = None


def clear_llm_cache_option_memory() -> None:
    """清除 LLM 缓存开关/目录记忆（环境变量 AITESTER_LLM_CACHE /
    AITESTER_LLM_CACHE_DIR 被外部（测试 monkeypatch.setenv）修改后调用，
    恢复"每次调用读环境变量"的历史口径。"""
    global _llm_cache_option_memory, _llm_cache_dir_memory
    _llm_cache_option_memory = None
    _llm_cache_dir_memory = None


_llm_cache_dir_memory: str | None = None


def _llm_cache_dir() -> str:
    """返回 LLM 缓存目录（支持环境变量覆盖，便于测试隔离到临时目录）。

    2026-09-28 性能优化：目录值进程内记忆（首次读环境变量，之后复用）；
    环境变量被外部修改时经 clear_llm_cache_option_memory() 显式清除记忆
    （base_agent.clear_llm_lru_cache 同步触发，保持测试隔离口径不变）。
    """
    global _llm_cache_dir_memory
    if _llm_cache_dir_memory is None:
        _llm_cache_dir_memory = os.environ.get("AITESTER_LLM_CACHE_DIR", _LLM_CACHE_DIR_DEFAULT)
    return _llm_cache_dir_memory
