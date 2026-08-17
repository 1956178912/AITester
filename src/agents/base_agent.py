"""
智能体基类模块：封装 LLM 调用逻辑，为所有子类提供统一的接口。

所有智能体（Planner、Generator、Debugger）均继承此类，
共享 LLM 调用、JSON 解析、代码提取等通用能力。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict

from langchain_openai import ChatOpenAI
import threading
from config import LLM_CONFIGS, TEMPERATURE, LLM_TIMEOUT

from src.exceptions import (
    APIError,
    RateLimitError,
    AuthenticationError,
    JSONParseError,
    AITesterError,
    retry_with_backoff,
)

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
# JSON 提取降级正则：匹配最内层无嵌套的 `{...}` 对象
_JSON_LEAF_PATTERN = r"\{[^{}]*\}"
# ───────────────────────────────────────────────────────────────────────────


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
                wait_time = base_wait ** attempt
                logger.warning("调用失败 (attempt %d/%d): %s，等待 %ds",
                               attempt + 1, max_retries + 1, e, wait_time)
                time.sleep(wait_time)
            else:
                break
    raise RuntimeError(f"调用失败，已重试 {max_retries} 次: {last_error}") from last_error


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


def _call_zai(api_key: str, base_url: str, model_name: str,
              system_prompt: str, user_message: str,
              max_retries: int = _DEFAULT_LLM_MAX_RETRIES) -> str:
    """使用 zai SDK 调用 LLM（用于 BigModel 等非 OpenAI 兼容接口）。

    实现带指数退避的重试策略：
    - APIReachLimitError（速率限制）：等待 5 * 2^attempt 秒（较长，因 zai 限速严格）
    - APIStatusError / 其他异常：等待 2^attempt 秒（1s, 2s, 4s）

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
    from zai import ZhipuAiClient
    from zai.core._errors import APIReachLimitError, APIStatusError

    # 初始化智谱 AI 客户端
    client = ZhipuAiClient(
        api_key=api_key,
        base_url=base_url,
    )

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
        # 重新抛出带有明确上下文的异常
        raise RuntimeError(f"zai API 调用失败: {e}") from e


def _get_llm_config() -> tuple[str, str, str]:
    """获取当前线程使用的 LLM 配置，优先返回线程局部覆盖值。

    线程局部覆盖用于并发场景下不同线程使用不同的 API Key/模型。
    若未设置线程局部值，则回退到配置文件中的第一个 LLM_CONFIGS。

    Returns:
        (api_key, base_url, model_name) 三元组；配置缺失时返回空字符串。
    """
    # 优先使用线程局部覆盖的配置（由测试或并发场景设置）
    if hasattr(_thread_local, "api_key") and _thread_local.api_key:
        # 若线程未显式设置 model_name，从全局配置读取默认值
        model = getattr(_thread_local, "model_name", LLM_CONFIGS[0].model_name if LLM_CONFIGS else "")
        return _thread_local.api_key, _thread_local.base_url, model
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


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端
    - 带重试的 LLM 调用（指数退避 + API 自动切换，支持 zai SDK）
    - JSON 输出提取（处理 LLM 可能输出的 markdown 包裹）
    - Python 代码块提取

    属性:
        llm: LangChain ChatOpenAI 实例，封装 LLM 调用。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        # 从配置获取默认 LLM 参数（api_key / base_url / model_name）
        api_key, base_url, model_name = _get_llm_config()
        # 初始化 LangChain 客户端，TEMPERATURE 来自 config.py 全局常量
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=TEMPERATURE,
            openai_api_key=api_key,
            base_url=base_url,
        )
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
        # 生成缓存键（基于 prompt 和 system_prompt）
        cache_key = f"{user_message}:{self.system_prompt[:100]}"  # 截取前100字符作为标识
        
        # 尝试从缓存获取
        import os
        cache_file = os.path.join(os.path.dirname(__file__), '..', 'cache', f'{hash(cache_key) % 10000}.json')
        cache_file = os.path.normpath(cache_file)
        
        try:
            if os.path.exists(cache_file):
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    if cached_data.get('prompt') == user_message and cached_data.get('system') == self.system_prompt:
                        logger.info("LLM 缓存命中: %s", cache_key[:50])
                        return cached_data['response']
        except Exception as e:
            logger.debug("缓存读取失败: %s", e)
        
        # 未命中，执行实际调用
        response = self._call_llm(user_message, max_retries)
        
        # 写入缓存
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            import json
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'prompt': user_message,
                    'system': self.system_prompt,
                    'response': response,
                    'timestamp': os.path.getmtime(cache_file) if os.path.exists(cache_file) else 0
                }, f, ensure_ascii=False)
            logger.info("LLM 缓存已更新: %s", cache_key[:50])
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
        from langchain_core.messages import SystemMessage, HumanMessage

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
                        text = _call_zai(api_key, base_url, model_name,
                                         self.system_prompt, user_message, max_retries)
                    else:
                        # OpenAI 兼容接口：使用 LangChain ChatOpenAI 统一路径
                        llm = ChatOpenAI(
                            model=model_name,
                            temperature=TEMPERATURE,
                            openai_api_key=api_key,
                            base_url=base_url,
                        )
                        response = llm.invoke([
                            SystemMessage(content=self.system_prompt),
                            HumanMessage(content=user_message),
                        ], timeout=LLM_TIMEOUT)
                        text = response.content.strip()
                        # 空响应视为失败，触发当前 API 的异常捕获并尝试下一个 API
                        if not text:
                            raise RuntimeError("LLM 返回空响应")

                    # 打印成功日志
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                    return text

                except Exception as e:
                    # 记录当前模型失败原因，继续尝试同 API 的下一个模型
                    last_error = e
                    logger.warning("模型 %s 调用失败: %s，尝试同 API 的其他模型", model_name, e)
                    continue

            # 当前 API 的所有模型都失败，记录并尝试下一个 API
            api_id = base_url.split("/")[2] if "/" in base_url else base_url
            logger.warning("API %s 所有模型均失败，尝试备用 API", api_id)
            continue

        # 所有 API 均失败，抛出包含最后一次异常信息的 RuntimeError
        raise RuntimeError(f"LLM 调用失败，已尝试所有 API: {last_error}") from last_error

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """
        从 LLM 输出中提取 JSON 对象。
        LLM 有时会在 JSON 前后添加 markdown 代码块标记（```json ... ```），
        此方法会先清理这些标记，再用括号平衡法找到完整的 JSON 对象。
        若解析失败，尝试用正则提取候选 JSON 作为降级方案。

        处理流程：
        1. 去除 markdown 代码块围栏（``` 或 ```json）
        2. 定位第一个 '{' 位置
        3. 使用括号平衡法扫描完整 JSON 对象
        4. 若平衡法失败，用正则回溯匹配最内层合法 JSON

        Args:
            text: LLM 返回的原始文本。

        Returns:
            解析后的字典对象。

        Raises:
            json.JSONDecodeError: 无法找到有效 JSON 时抛出。
        """
        # 移除 markdown 代码块标记（如 ```json\n 或 ```\n）
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = re.sub(r"```", "", cleaned)
        # 找到第一个左花括号的位置，JSON 对象必以 '{' 开始
        start = cleaned.find("{")
        if start == -1:
            # 全文无 '{'，直接抛出明确的 JSONDecodeError
            raise json.JSONDecodeError("No JSON found in response", text, 0)
        # 用括号平衡法提取从 start 开始的完整 JSON 对象
        json_str = BaseAgent._find_balanced_json(cleaned, start)
        if json_str is not None:
            try:
                return json.loads(json_str.strip())
            except json.JSONDecodeError:
                # 平衡法提取到的字符串格式仍不合法，进入降级方案
                pass
        # 降级方案：用正则匹配最内层无嵌套的 `{...}`，从后往前找第一个合法 JSON
        # 从后往前是为了优先匹配较大的候选（外层 JSON 通常包含更多字段）
        for m in reversed(list(re.finditer(_JSON_LEAF_PATTERN, cleaned))):
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
        # 所有方案均失败，抛出包含原文位置的错误
        raise json.JSONDecodeError("Could not find complete JSON", text, start)

    @staticmethod
    def _find_balanced_json(text: str, start: int) -> str | None:
        """
        使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象。

        算法原理：
        - 遇到 '{' 深度+1，遇到 '}' 深度-1
        - 当深度归零时，说明找到了匹配的右花括号，即一个完整 JSON 对象
        - 字符串字面量内的 '{' 和 '}' 不计入深度（通过 in_string 标志位处理）
        - 转义字符（\" 和 \\）需要特殊处理，避免误判

        Args:
            text: 待搜索的文本。
            start: 起始搜索位置（应为 '{' 的位置）。

        Returns:
            完整的 JSON 字符串，未找到匹配时返回 None。
        """
        depth = 0          # 当前括号深度（遇 '{' +1，遇 '}' -1）
        in_string = False  # 是否处于 JSON 字符串字面量内部
        escape = False     # 是否处于转义状态（上一个字符是反斜杠）
        # 边界检查：start 超出文本范围则直接返回 None
        if start < 0 or start >= len(text):
            return None
        i = start
        while i < len(text):
            ch = text[i]
            # 处理转义：若上一个字符是反斜杠，当前字符是转义目标，不改变状态
            if escape:
                escape = False
                i += 1
                continue
            # 遇到反斜杠，标记下一个字符为转义字符
            if ch == chr(92):  # chr(92) = '\\'
                escape = True
                i += 1
                continue
            # 遇到双引号，切换字符串状态（进入或离开字符串字面量）
            if ch == chr(34):  # chr(34) = '"'
                in_string = not in_string
                i += 1
                continue
            # 在字符串内部时，跳过所有字符（包括 '{' '}' '"' 均不计入深度）
            if in_string:
                i += 1
                continue
            # 在字符串外部时，处理花括号深度变化
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                # 深度归零表示找到匹配的右花括号，返回完整 JSON 切片
                if depth == 0:
                    return text[start:i + 1]
            i += 1
        # 遍历结束仍未归零（JSON 对象未闭合），返回剩余部分供调用方降级处理
        return text[start:] if start < len(text) else None

    @staticmethod
    def _extract_python_code(text: str) -> str:
        """
        从 LLM 输出中提取 Python 代码块。
        支持三种格式：```python ... ```、``` ... ```、python: ...

        匹配优先级：
        1. ```python ... ```（最明确，优先匹配）
        2. ``` ... ```（通用 markdown 代码块）
        3. python: ... 前缀（某些模型输出不带反引号）
        4. 以上均无则返回原始文本（strip 空白）

        Args:
            text: LLM 返回的包含代码的文本。

        Returns:
            提取出的 Python 代码字符串（无 markdown 包裹）。
        """
        # 尝试标准 markdown 格式：```python ... ```
        # re.DOTALL 使 '.' 匹配换行符，从而跨行提取代码块
        match = re.search(r"```python\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试通用 markdown 格式：``` ... ```（不限制语言标记）
        match = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试 "python" 前缀格式（某些模型输出不带反引号，如 "python:\n..."）
        stripped = text.strip()
        if stripped.lower().startswith("python"):
            # 去除 "python" 前缀及紧随的换行
            stripped = re.sub(r"^python\s*\n", "", stripped, flags=re.IGNORECASE)
            return stripped.strip()
        # 返回原始文本（无标记时直接返回，由调用方决定是否有效）
        return text.strip()
