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
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI

from config import LLM_CONFIGS, LLM_TIMEOUT

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
        # langchain-openai 的 ChatOpenAI 接受 openai_api_key（与 OpenAI SDK 的
        # api_key 等价）；mypy 按严格 API 签名校验会报 call-arg，显式忽略
        client = ChatOpenAI(  # type: ignore[call-arg]
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
    func: Callable[..., Any],
    max_retries: int,
    base_wait: int = 1,
    retryable_exceptions: tuple[type[Exception], ...] = (),
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
    """
    if not usage:
        return True
    try:
        from src.graph.token_usage import record_usage

        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        else:
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        record_usage(input_tokens, output_tokens, model=model_name)
        # 5.4 预算守卫（默认关：未启用时 check_budget 恒 True，零行为变化）
        from src.graph.cost_budget import check_budget

        return check_budget(consumed_delta_tokens=input_tokens + output_tokens)
    except Exception as e:  # 统计失败不影响主流程
        logger.debug("token 统计记录失败（忽略）: %s", e)
        return True


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
    # （APIReachLimitError / APIStatusError 均为 Exception 子类，
    #  重试元组直接以 Exception 兜底，无需逐个列举——子类在 except 中
    #  被基类覆盖，列举属死代码）
    from zai.core._errors import APIReachLimitError, APIStatusError  # noqa: F401

    # 复用缓存的智谱 AI 客户端（连接池跨调用复用）
    client = _get_or_create_zai_client(api_key, base_url)

    # 定义 zai SDK 特有的可重试异常类型：限流（APIReachLimitError）/
    # 服务端错误（APIStatusError）均按 Exception 兜底捕获，不做区分，
    # 统一走指数退避（zai 限速严格，取较长基准 5s）
    _ZAI_RETRYABLE_EXCEPTIONS = (Exception,)

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
    _llm_cache_option_memory = os.environ.get("AITESTER_LLM_CACHE", "1") != "0"
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
