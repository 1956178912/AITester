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
from config import LLM_CONFIGS, TEMPERATURE

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

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            # glm-4.7-flash 默认开启深度思考，关闭以获取普通响应
            # thinking.disabled 可避免返回过长的推理链，节省 token 并加快响应
            kwargs: dict[str, Any] = {"thinking": {"type": "disabled"}}
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=_ZAI_MAX_TOKENS,
                **kwargs,
            )
            msg = response.choices[0].message
            # 优先取 content（普通响应），回退到 reasoning_content（深度思考内容）
            # 两者均为空说明模型异常返回，抛出明确错误以便重试
            text = (msg.content or msg.reasoning_content or "").strip()
            if not text:
                raise RuntimeError("LLM 返回空响应")
            logger.info("zai API 调用成功 (model=%s, attempt=%d)", model_name, attempt)
            return text

        except APIReachLimitError as e:
            # 速率限制：等比增长等待时间，基准 5 秒（zai 限流比普通 API 更严格）
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt * _ZAI_RATE_LIMIT_WAIT_BASE_SECONDS
                logger.warning("zai API 限流 (attempt %d/%d): %s，等待 %ds",
                               attempt + 1, max_retries, e, wait_time)
                time.sleep(wait_time)
                continue
            raise

        except APIStatusError as e:
            # API 状态错误（4xx/5xx）：指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning("zai API 错误 (attempt %d/%d): %s，等待 %ds",
                               attempt + 1, max_retries, e, wait_time)
                time.sleep(wait_time)
                continue
            raise

        except Exception as e:
            # 其他未知异常（网络断开、解析错误等）：统一指数退避
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning("zai API 调用失败 (attempt %d/%d): %s，等待 %ds",
                               attempt + 1, max_retries, e, wait_time)
                time.sleep(wait_time)
                continue
            raise

    # 所有重试耗尽，抛出最终错误（chain from last_error 保留异常链）
    raise RuntimeError(f"zai API 调用失败: {last_error}") from last_error


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

        # 依次尝试每个 API 配置（自动故障转移：主 API 失败 → 备用 API）
        for api_key, base_url, model_name in all_configs:
            # 判断当前 API 是否为 zai SDK 兼容接口，分流至不同调用路径
            is_zai = _is_zai_compatible(base_url)

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
                    ])
                    text = response.content.strip()
                    # 空响应视为失败，触发当前 API 的异常捕获并尝试下一个 API
                    if not text:
                        raise RuntimeError("LLM 返回空响应")

                # 打印成功日志（仅在有重试可能时打印，避免单次调用产生过多日志）
                if max_retries > 1:
                    # 从 base_url 提取主机名作为 API 标识（如 "open.bigmodel.cn"）
                    api_id = base_url.split("/")[2] if "/" in base_url else base_url
                    logger.info("API 调用成功 (api=%s, model=%s)", api_id, model_name)
                return text

            except Exception as e:
                # 记录当前 API 失败原因，继续尝试下一个 API（不立即抛出）
                last_error = e
                logger.warning("API %s (%s) 调用失败: %s", base_url, model_name, e)
                # 当前 API 所有重试耗尽，尝试下一个 API（for 循环自动 continue）
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
