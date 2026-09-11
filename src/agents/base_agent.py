"""
智能体基类模块：封装 LLM 调用逻辑，为所有子类提供统一的接口。

所有智能体（Planner、Generator、Debugger）均继承此类，
共享 LLM 调用、JSON 解析、代码提取等通用能力。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any

from langchain_openai import ChatOpenAI

from config import LLM_CONFIGS, LLM_TIMEOUT, TEMPERATURE
from src.utils.helpers import extract_code_block, extract_json_object

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
# ───────────────────────────────────────────────────────────────────────────
# Token 优化常量
# 单条代码输入最大字符数：超长代码截断，避免 token 浪费
_CODE_MAX_CHARS = 3000
# 代码截断提示信息
_CODE_TRUNCATED_MSG = "\n\n[代码已截断，仅显示前 {max} 字符]"

# ─── LLM 客户端复用缓存（性能优化）────────────────────────────────────────────
# _call_llm 此前每次调用都新建 ChatOpenAI 实例，其底层 httpx 连接池随实例
# 创建/销毁，无法复用 TCP/TLS 连接；改为按 (model, temperature, api_key,
# base_url) 缓存实例，进程内复用连接，降低每次 LLM 调用的构建与握手开销。
# ChatOpenAI 内部客户端线程安全，可被并发任务（--parallel）共享。
# 缓存上限：配置组合数远小于 16，超出时按 FIFO 淘汰（防止 key 轮换场景膨胀）
_MAX_CACHED_LLM_CLIENTS = 16
_llm_client_cache: dict[tuple[str, float, str, str], ChatOpenAI] = {}
# 缓存锁：get→构造→evict→insert 整段需原子，否则并发同 key miss 会各建一份
# 客户端（双份 httpx 连接池），且双线程同时触发 FIFO evict 时互相淘汰新插入
# 的实例（thrashing）。采用双检锁：无锁快路径命中直接返回，miss 时加锁再查
_llm_client_cache_lock = threading.Lock()


def _get_or_create_chat_client(model_name: str, temperature: float, api_key: str, base_url: str) -> ChatOpenAI:
    """获取（或创建）缓存的 ChatOpenAI 客户端实例。

    以 (model_name, temperature, api_key, base_url) 为缓存键，相同组合复用
    同一实例，避免每次 LLM 调用重复构建 OpenAI SDK 客户端与 HTTP 连接池。

    Args:
        model_name: 模型名称。
        temperature: 采样温度（与 config.TEMPERATURE 保持一致）。
        api_key: API 密钥。
        base_url: 服务 Base URL。

    Returns:
        ChatOpenAI 实例（缓存命中或新建）。
    """
    key = (model_name, temperature, api_key, base_url)
    client = _llm_client_cache.get(key)
    if client is not None:
        return client
    with _llm_client_cache_lock:
        # 加锁后二次检查：并发窗口内其他线程可能已构造完同一 key
        client = _llm_client_cache.get(key)
        if client is not None:
            return client
        client = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=api_key,
            base_url=base_url,
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
    func,
    max_retries: int,
    base_wait: int = 1,
    retryable_exceptions: tuple = (),
) -> Any:
    """带指数退避的重试通用工具函数。

    对给定函数执行带重试的调用，失败时按 2^attempt 秒指数退避等待后重试。
    可用于 _call_zai 和 _call_llm 中的重试逻辑，避免代码重复。

    Args:
        func: 要执行的函数（无参数或仅接受内部参数）。
        max_retries: 最大重试次数（不含首次尝试）。
        base_wait: 基础等待秒数（首次重试等待 base_wait，后续翻倍）。
        retryable_exceptions: 可重试的异常类型元组，为空则捕获所有异常。

    Returns:
        函数执行的返回值。

    Raises:
        RuntimeError: 所有重试均失败时抛出，携带最后一次异常信息。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):  # attempt 0 是首次尝试
        try:
            return func()
        except Exception as e:
            # 非 retryable 异常立即抛出
            if retryable_exceptions and not isinstance(e, retryable_exceptions):
                raise
            last_error = e
            if attempt < max_retries:
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
                time.sleep(wait_time)
            else:
                break
    raise RuntimeError(f"调用失败，已重试 {max_retries} 次: {last_error}") from last_error


def _redact_log_text(text: str) -> str:
    """对 LLM 调用路径的日志文本做敏感信息脱敏（P2-8）。

    SDK 异常消息可能携带请求头（含 Authorization: Bearer <api_key>）或
    带 key 的 URL 片段；此前这些文本直接拼进日志，handler 级脱敏过滤器
    只在 CLI 入口挂载，experiments 等非 CLI 入口下不生效。这里在
    base_agent 的日志调用处直接脱敏，确保任何日志输出路径都不泄露凭证。

    Args:
        text: 待脱敏的日志文本（通常为异常字符串）。

    Returns:
        脱敏后的文本；脱敏器不可用时原样返回（不阻断主流程）。
    """
    try:
        from src.utils.logging_utils import mask_sensitive_info

        return mask_sensitive_info(text)
    except Exception:
        return text


def _record_response_usage(usage: Any, model_name: str) -> None:
    """将 LLM 响应的 token 使用量记入线程局部统计（容错：缺失字段记 0）。

    兼容两种响应结构：
    - LangChain usage_metadata 字典：input_tokens / output_tokens
    - OpenAI/zai usage 对象：prompt_tokens / completion_tokens

    Args:
        usage: 响应的 usage 字段（dict 或对象），可为 None。
        model_name: 模型名（用于 by_model 分桶）。
    """
    if not usage:
        return
    try:
        from src.graph.token_usage import record_usage

        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        else:
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        record_usage(input_tokens, output_tokens, model=model_name)
    except Exception as e:  # 统计失败不影响主流程
        logger.debug("token 统计记录失败（忽略）: %s", e)


def _is_zai_compatible(base_url: str) -> bool:
    """判断是否为 zai SDK 兼容的 API（如 BigModel 智谱）。

    OpenAI 兼容接口返回 401 但 zai SDK 可用的服务商需走特殊路径。
    检测逻辑：检查 base_url 中是否包含智谱域名的特征字符串。

    Args:
        base_url: 模型服务的 Base URL（如 "https://open.bigmodel.cn/api/..."）。

    Returns:
        True 表示需使用 zai SDK 路径；False 使用标准 LangChain ChatOpenAI。
    """
    # 智谱系域名关键字列表（bigmodel.cn 和 zhipuai.cn 均覆盖）
    zai_domains = ["bigmodel.cn", "zhipuai"]
    return any(d in base_url for d in zai_domains)


def _call_zai(
    api_key: str,
    base_url: str,
    model_name: str,
    system_prompt: str,
    user_message: str,
    max_retries: int = _DEFAULT_LLM_MAX_RETRIES,
) -> str:
    """使用 zai SDK 调用 LLM（用于 BigModel 等非 OpenAI 兼容接口）。

    实现带指数退避的重试策略：
    - 所有可重试异常统一按 base_wait=5s 指数退避：等待 5 * 2^attempt 秒（5s, 10s, 20s ...）。
      因 _ZAI_RETRYABLE_EXCEPTIONS 含 Exception（兜底捕获全部异常），zai 限流（APIReachLimitError）
      与普通 API 错误（APIStatusError）不做区分，一律使用 5s 基准（zai 限速严格，取较长基准）。

    Args:
        api_key: API Key 凭证字符串。
        base_url: API Base URL。
        model_name: 模型名称（如 "glm-4.7-flash"）。
        system_prompt: System Prompt，定义模型角色和行为约束。
        user_message: 用户消息内容。
        max_retries: 最大重试次数，默认 3 次。

    Returns:
        LLM 返回的文本内容（已 strip 空白）。

    Raises:
        RuntimeError: 所有重试均失败时抛出，携带最后一次异常信息。
    """
    # 延迟导入：避免未安装 zai SDK 时影响主程序启动
    from zai.core._errors import APIReachLimitError, APIStatusError

    # 复用缓存的智谱 AI 客户端（连接池跨调用复用）
    client = _get_or_create_zai_client(api_key, base_url)

    # 定义 zai SDK 特有的可重试异常类型
    _ZAI_RETRYABLE_EXCEPTIONS = (APIReachLimitError, APIStatusError, Exception)

    def _do_zai_call() -> str:
        """执行单次 zai API 调用（内部辅助函数）。"""
        kwargs: dict[str, Any] = {"thinking": {"type": "disabled"}}
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=_ZAI_MAX_TOKENS,
            timeout=LLM_TIMEOUT,
            **kwargs,
        )
        msg = response.choices[0].message
        # 优先取 content（普通响应），回退到 reasoning_content（深度思考内容）
        text = (msg.content or msg.reasoning_content or "").strip()
        if not text:
            raise RuntimeError("LLM 返回空响应")
        # token 消耗统计（zai 路径响应携带 OpenAI 风格的 usage 字段，可能缺失）
        _record_response_usage(getattr(response, "usage", None), model_name)
        logger.info("zai API 调用成功 (model=%s)", model_name)
        return text

    try:
        # 使用通用重试工具函数，zai 限流时使用更长的等待基准（5秒）
        return _retry_with_exponential_backoff(
            func=_do_zai_call,
            max_retries=max_retries,
            base_wait=_ZAI_RATE_LIMIT_WAIT_BASE_SECONDS,  # zai 限流基准 5 秒
            retryable_exceptions=_ZAI_RETRYABLE_EXCEPTIONS,
        )
    except Exception as e:
        # 重新抛出带有明确上下文的异常（异常文本可能含请求头凭证，先脱敏）
        raise RuntimeError(f"zai API 调用失败: {_redact_log_text(str(e))}") from e


def _get_llm_config() -> tuple[str, str, str]:
    """获取当前线程使用的 LLM 配置，优先返回线程局部覆盖值。

    线程局部覆盖用于并发场景下不同线程使用不同的 API Key/模型。
    若未设置线程局部值，则回退到配置文件中的第一个 LLM_CONFIGS。

    Returns:
        (api_key, base_url, model_name) 三元组；配置缺失时返回空字符串。
    """
    # 优先使用线程局部覆盖的配置（由测试或并发场景设置）
    if hasattr(_thread_local, "api_key") and _thread_local.api_key:
        # 未显式覆盖的字段对称回退全局配置：只设 api_key 不设 base_url 时
        # 此前裸取 _thread_local.base_url 会 AttributeError
        model = getattr(_thread_local, "model_name", LLM_CONFIGS[0].model_name if LLM_CONFIGS else "")
        base_url = getattr(_thread_local, "base_url", "") or (LLM_CONFIGS[0].base_url if LLM_CONFIGS else "")
        return _thread_local.api_key, base_url, model
    # 回退到全局配置（按优先级取第一个有效配置）
    if LLM_CONFIGS:
        cfg = LLM_CONFIGS[0]
        return cfg.api_key, cfg.base_url, cfg.model_name
    # 无任何配置时返回空串（调用方应捕获并抛出 RuntimeError）
    return "", "", ""


def _get_all_api_configs() -> list[tuple[str, str, str]]:
    """获取所有可用的 API 配置列表（按优先级排列）。

    用于 _call_llm 的 API 自动切换逻辑：当主 API 失败时依次尝试备用 API。

    Returns:
        列表，每项为 (api_key, base_url, model_name)，仅包含已配置的项。
        若 LLM_CONFIGS 为空则返回空列表。
    """
    return [(c.api_key, c.base_url, c.model_name) for c in LLM_CONFIGS]


# ─── LLM 文件缓存开关（省 token）────────────────────────────────────────────
# 默认启用；设环境变量 AITESTER_LLM_CACHE=0 可关闭（测试环境用于隔离，避免 flaky）。
# 缓存目录默认 src/cache/，可用 AITESTER_LLM_CACHE_DIR 覆盖（便于测试指向临时目录）。
# 开关与目录均在每次调用时读取，便于测试用 monkeypatch.setenv 动态切换。
_LLM_CACHE_DIR_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "cache"))


def _llm_cache_enabled() -> bool:
    """是否启用 LLM 文件缓存（默认启用，设 AITESTER_LLM_CACHE=0 关闭）。"""
    return os.environ.get("AITESTER_LLM_CACHE", "1") != "0"


def _llm_cache_dir() -> str:
    """返回 LLM 缓存目录（支持环境变量覆盖，便于测试隔离到临时目录）。"""
    return os.environ.get("AITESTER_LLM_CACHE_DIR", _LLM_CACHE_DIR_DEFAULT)


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端（复用连接池缓存）
    - 带重试的 LLM 调用（指数退避 + API 自动切换，支持 zai SDK）
    - JSON 输出提取（处理 LLM 可能输出的 markdown 包裹）
    - Python 代码块提取

    属性:
        llm: LangChain ChatOpenAI 实例（来自模块级缓存，连接池跨实例/跨调用复用）。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        # 从配置获取默认 LLM 参数（api_key / base_url / model_name）
        api_key, base_url, model_name = _get_llm_config()
        # 复用缓存的 LangChain 客户端（连接池跨实例复用）：
        # 此前每个 BaseAgent 实例都新建一个 ChatOpenAI，而生产调用全部走
        # _call_llm 的缓存客户端，self.llm 实际只是"占位"属性——每个智能体
        # 实例化都白白多建一个 httpx 连接池；现改为与 _call_llm 共享同一缓存
        self.llm = _get_or_create_chat_client(model_name, TEMPERATURE, api_key, base_url)
        # 每个智能体携带自己的 System Prompt，定义其角色和行为约束
        self.system_prompt = system_prompt

    def _call_llm_with_cache(self, user_message: str, max_retries: int = _DEFAULT_LLM_MAX_RETRIES) -> str:
        """
        带缓存的 LLM 调用方法。

        首次调用时执行完整的 LLM 请求并缓存结果，
        后续相同输入直接返回缓存响应，节省 token 和延迟。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数。

        Returns:
            LLM 返回的文本字符串（来自缓存或实时调用）。
        """
        # 缓存开关关闭时直接透传（测试环境默认关闭，避免缓存文件污染与 flaky）
        if not _llm_cache_enabled():
            return self._call_llm(user_message, max_retries)

        # 生成缓存键（基于 user_message + system_prompt）
        # 使用 hashlib.md5 替代 hash()，确保跨会话稳定命中（hash() 在 Python 3.3+ 默认随机化）
        # 说明：键不含 model，缓存的是"成功的 LLM 输出文本"；配额故障转移/模型切换后，
        # 命中旧结果仍有效（都是该 prompt 的合理回答），且不再消耗 token。
        cache_key = f"{user_message}:{self.system_prompt}"
        cache_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]  # 取前16位十六进制，固定长度
        cache_file = os.path.join(_llm_cache_dir(), f"{cache_hash}.json")
        cache_file = os.path.normpath(cache_file)

        # 读缓存：校验 prompt 与 system 完全一致才命中（防 md5 前16位碰撞误命中）
        try:
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if cached_data.get("prompt") == user_message and cached_data.get("system") == self.system_prompt:
                        logger.info("LLM 缓存命中 (省 1 次调用): %s", cache_key[:50])
                        return cached_data["response"]
        except Exception as e:
            logger.debug("缓存读取失败: %s", e)

        # 未命中，执行实际调用（仅在成功时写缓存；失败如 403 额度用尽则不缓存）
        response = self._call_llm(user_message, max_retries)

        # 写入缓存
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "prompt": user_message,
                        "system": self.system_prompt,
                        "response": response,
                        "timestamp": time.time(),
                    },
                    f,
                    ensure_ascii=False,
                )
            logger.info("LLM 缓存已写入: %s", cache_key[:50])
        except Exception as e:
            logger.debug("缓存写入失败: %s", e)

        return response

    def _call_llm(self, user_message: str, max_retries: int = _DEFAULT_LLM_MAX_RETRIES) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。
        若所有重试均失败，自动切换到备用 API 继续尝试。
        支持 OpenAI 兼容接口和 zai SDK（BigModel）两种调用路径。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数，默认 3 次。

        Returns:
            LLM 返回的文本字符串。

        Raises:
            RuntimeError: 所有 API 和重试均失败时抛出。
        """
        # 延迟导入：避免循环导入（base_agent 被 planner/generator/debugger 导入）
        from langchain_core.messages import HumanMessage, SystemMessage

        # 获取所有已配置的 API，未配置时直接报错不进入重试循环
        all_configs = _get_all_api_configs()
        if not all_configs:
            raise RuntimeError("未配置任何 LLM API")

        # 记录最后一次异常，用于最终报错信息
        last_error: Exception | None = None

        # 按 base_url 分组配置，支持同一 API 内切换模型
        # 结构：{base_url: [(api_key, model_name), ...]}
        api_groups: dict[str, list[tuple[str, str]]] = {}
        for api_key, base_url, model_name in all_configs:
            if base_url not in api_groups:
                api_groups[base_url] = []
            api_groups[base_url].append((api_key, model_name))

        # 依次尝试每个 API 组（自动故障转移：主 API 失败 → 备用 API）
        # 同一 API 内也尝试不同模型（额度用完时自动切换）
        for base_url, models in api_groups.items():
            # 判断当前 API 是否为 zai SDK 兼容接口，分流至不同调用路径
            is_zai = _is_zai_compatible(base_url)

            for api_key, model_name in models:
                try:
                    if is_zai:
                        # BigModel 等非 OpenAI 兼容接口：使用 zai SDK 专属调用
                        text = _call_zai(api_key, base_url, model_name, self.system_prompt, user_message, max_retries)
                    else:
                        # OpenAI 兼容接口：复用缓存的 ChatOpenAI 客户端（连接池跨调用复用）
                        llm = _get_or_create_chat_client(model_name, TEMPERATURE, api_key, base_url)
                        response = llm.invoke(
                            [
                                SystemMessage(content=self.system_prompt),
                                HumanMessage(content=user_message),
                            ],
                            timeout=LLM_TIMEOUT,
                        )
                        text = response.content.strip()
                        # 空响应视为失败，触发当前 API 的异常捕获并尝试下一个 API
                        if not text:
                            raise RuntimeError("LLM 返回空响应")
                        # token 消耗统计（LangChain 响应的 usage_metadata，可能缺失）
                        _record_response_usage(getattr(response, "usage_metadata", None), model_name)

                    # 打印成功日志
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                    return text

                except Exception as e:
                    # 记录当前模型失败原因，继续尝试同 API 的下一个模型
                    # 异常文本可能携带请求头/URL 中的 API Key（部分 SDK 会把
                    # Authorization 头打进报错信息），统一走脱敏后再落日志（P2-8）
                    last_error = e
                    logger.warning("模型 %s 调用失败: %s，尝试同 API 的其他模型", model_name, _redact_log_text(str(e)))
                    continue

            # 当前 API 的所有模型都失败，记录并尝试下一个 API
            api_id = base_url.split("/")[2] if "/" in base_url else base_url
            logger.warning("API %s 所有模型均失败，尝试备用 API", api_id)
            continue

        # 所有 API 均失败，抛出包含最后一次异常信息的 RuntimeError
        raise RuntimeError(f"LLM 调用失败，已尝试所有 API: {_redact_log_text(str(last_error))}") from last_error

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """
        从 LLM 输出中提取 JSON 对象（委托给公共工具函数）。

        Args:
            text: LLM 返回的原始文本。

        Returns:
            解析后的字典对象。

        Raises:
            json.JSONDecodeError: 无法找到有效 JSON 时抛出。
        """
        return extract_json_object(text)

    @staticmethod
    def _find_balanced_json(text: str, start: int) -> str | None:
        """
        使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象（委托给公共工具函数）。

        Args:
            text: 待搜索的文本。
            start: 起始搜索位置（应为 '{' 的位置）。

        Returns:
            完整的 JSON 字符串，未找到匹配时返回 None。
        """
        from src.utils.helpers import _find_balanced_json as _helpers_find_balanced_json

        return _helpers_find_balanced_json(text, start)

    @staticmethod
    def _extract_python_code(text: str) -> str:
        """
        从 LLM 输出中提取 Python 代码块（委托给公共工具函数）。

        Args:
            text: LLM 返回的包含代码的文本。

        Returns:
            提取出的 Python 代码字符串（无 markdown 包裹）。
        """
        return extract_code_block(text, language="python")

    @staticmethod
    def truncate_code(
        code: str,
        max_chars: int = _CODE_MAX_CHARS,
        focus_function: str | None = None,
    ) -> str:
        """截断超长代码，避免 LLM token 浪费。

        截取策略（P0 优化，解决 SWE-bench 大文件上下文丢失问题）：
        1. 代码在预算内 → 原样返回；
        2. 否则先做基于 AST 的智能截取（保留 import + 目标函数及其
           直接依赖的辅助函数，超长函数体首尾截断），优先于"头尾各半"
           硬截断——硬截断对数百行源文件会让 LLM 看不到目标函数；
        3. AST 截取仍超预算（或源码无法解析、无函数体）→ 回退字符级
           头尾截断兜底。

        Args:
            code: 原始代码字符串。
            max_chars: 最大允许字符数，默认 3000。
            focus_function: 焦点函数名（如 "divide"）。提供时按函数维度
                截取上下文；None 时保留全部顶层函数再按预算裁剪。

        Returns:
            截断后的代码字符串。
        """
        if len(code) <= max_chars:
            return code

        # 第一层：AST 智能截取（惰性导入，避免 tools 模块的循环依赖）
        from src.tools.code_context import extract_focused_code

        focused = extract_focused_code(code, focus_function=focus_function, max_chars=max_chars)
        if len(focused) <= max_chars:
            logger.info(
                "代码已按 AST 智能截取：%d → %d 字符（focus=%s）", len(code), len(focused), focus_function or "*"
            )
            return focused

        # 第二层：字符级头尾截断兜底（保留 import 头 + 尾部，中间省略）
        head_len = max_chars // 2
        tail_len = max_chars - head_len - len(_CODE_TRUNCATED_MSG.format(max=max_chars))
        head = code[:head_len]
        tail = code[-tail_len:] if tail_len > 0 else ""
        truncated = head + _CODE_TRUNCATED_MSG.format(max=max_chars) + tail
        logger.info("代码已字符级截断：%d → %d 字符", len(code), len(truncated))
        return truncated
