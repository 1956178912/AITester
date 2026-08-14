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


_thread_local = threading.local()


def _get_llm_config() -> tuple[str, str]:
    """获取当前线程使用的 LLM 配置，优先返回线程局部覆盖值。"""
    if hasattr(_thread_local, "api_key") and _thread_local.api_key:
        return _thread_local.api_key, _thread_local.base_url
    if LLM_CONFIGS:
        cfg = LLM_CONFIGS[0]
        return cfg.api_key, cfg.base_url
    return "", ""


def _get_all_api_configs() -> list[tuple[str, str, str]]:
    """获取所有可用的 API 配置列表（按优先级排列）。
    
    Returns:
        列表，每项为 (api_key, base_url, model_name)，仅包含已配置的项。
    """
    return [(c.api_key, c.base_url, c.model_name) for c in LLM_CONFIGS]


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端
    - 带重试的 LLM 调用（指数退避 + API 自动切换）
    - JSON 输出提取（处理 LLM 可能输出的 markdown 包裹）
    - Python 代码块提取

    属性:
        llm: LangChain ChatOpenAI 实例，封装 LLM 调用。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        # 使用默认 LLM 配置初始化 LLM 客户端
        api_key, base_url = _get_llm_config()
        model_name = LLM_CONFIGS[0].model_name if LLM_CONFIGS else "gpt-4o-mini"
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=TEMPERATURE,
            openai_api_key=api_key,
            base_url=base_url,
        )
        # 每个智能体携带自己的 System Prompt，定义其角色和行为约束
        self.system_prompt = system_prompt

    def _call_llm(self, user_message: str, max_retries: int = 3) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。
        若所有重试均失败，自动切换到备用 API 继续尝试。

        Args:
            user_message: 用户消息内容。
            max_retries: 单次 API 的最大重试次数，默认 3 次。

        Returns:
            LLM 返回的文本字符串。

        Raises:
            RuntimeError: 所有 API 和重试均失败时抛出。
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        all_configs = _get_all_api_configs()
        if not all_configs:
            raise RuntimeError("未配置任何 LLM API")

        last_error: Exception | None = None
        primary_key = all_configs[0][0] if all_configs else ""

        # 依次尝试每个 API 配置
        for api_key, base_url, model_name in all_configs:
            llm = ChatOpenAI(
                model=model_name,
                temperature=TEMPERATURE,
                openai_api_key=api_key,
                base_url=base_url,
            )
            
            for attempt in range(max_retries):
                try:
                    response = llm.invoke([
                        SystemMessage(content=self.system_prompt),
                        HumanMessage(content=user_message),
                    ])
                    text = response.content.strip()
                    if not text:
                        raise RuntimeError("LLM 返回空响应")
                    if attempt > 0 or api_key != primary_key:
                        logger.info(
                            "API 调用成功 (api=%s, attempt=%d)",
                            base_url.split("/")[2] if "/" in base_url else base_url,
                            attempt,
                        )
                    return text
                except Exception as e:
                    last_error = e
                    # 指数退避
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(
                            "API %s 调用失败 (attempt %d/%d): %s，等待 %ds",
                            base_url,
                            attempt + 1,
                            max_retries,
                            e,
                            wait_time,
                        )
                        time.sleep(wait_time)
                        continue
                    # 当前 API 所有重试耗尽，尝试下一个 API
                    logger.warning("API %s 所有重试失败，切换到备用 API", base_url)
                    break
            else:
                # 未通过 break 退出内层循环（即成功），继续外层循环到下一个 API
                continue
            # break 触发了，继续外层循环尝试下一个 API
            continue
        
        raise RuntimeError(f"LLM 调用失败，已尝试所有 API: {last_error}") from last_error

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """
        从 LLM 输出中提取 JSON 对象。
        LLM 有时会在 JSON 前后添加 markdown 代码块标记（```json ... ```），
        此方法会先清理这些标记，再用括号平衡法找到完整的 JSON 对象。
        若解析失败，尝试用正则提取候选 JSON 作为降级方案。

        Args:
            text: LLM 返回的原始文本。

        Returns:
            解析后的字典对象。

        Raises:
            json.JSONDecodeError: 无法找到有效 JSON 时抛出。
        """
        # 移除 markdown 代码块标记（如 ```json 或 ```）
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = re.sub(r"```", "", cleaned)
        # 找到第一个左花括号的位置
        start = cleaned.find("{")
        if start == -1:
            raise json.JSONDecodeError("No JSON found in response", text, 0)
        # 用括号平衡法提取完整 JSON
        json_str = BaseAgent._find_balanced_json(cleaned, start)
        if json_str is not None:
            try:
                return json.loads(json_str.strip())
            except json.JSONDecodeError:
                pass
        # 降级：用正则匹配候选 JSON 对象（从后往前找第一个合法 JSON）
        for m in reversed(list(re.finditer(r"\{[^{}]*\}", cleaned))):
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
        raise json.JSONDecodeError("Could not find complete JSON", text, start)

    @staticmethod
    def _find_balanced_json(text: str, start: int) -> str | None:
        """
        使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象。

        原理：遇到 '{' 深度+1，遇到 '}' 深度-1；
        当深度归零时，说明找到了匹配的右花括号，即一个完整 JSON 对象。
        注意：字符串内的 '{' 和 '}' 不计入深度（通过 in_string 标志位处理）。

        Args:
            text: 待搜索的文本。
            start: 起始搜索位置（应为 '{' 的位置）。

        Returns:
            完整的 JSON 字符串，未找到时返回 None。
        """
        depth = 0          # 当前括号深度
        in_string = False  # 是否处于 JSON 字符串内部
        escape = False     # 是否处于转义状态（处理 \" 等）
        i = start
        while i < len(text):
            ch = text[i]
            # 处理转义字符：\\ 或 \" 不改变 in_string 状态
            if escape:
                escape = False
                i += 1
                continue
            # 遇到反斜杠，下一个字符被转义
            if ch == chr(92):  # chr(92) = '\\'
                escape = True
                i += 1
                continue
            # 遇到引号，切换字符串状态
            if ch == chr(34):  # chr(34) = '"'
                in_string = not in_string
                i += 1
                continue
            # 在字符串内部时跳过所有字符
            if in_string:
                i += 1
                continue
            # 在字符串外部时处理括号
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                # 深度归零，找到匹配的右花括号
                if depth == 0:
                    return text[start:i + 1]
            i += 1
        # 未找到完整 JSON，返回剩余部分（可能不完整）
        return text[start:] if start < len(text) else None

    @staticmethod
    def _extract_python_code(text: str) -> str:
        """
        从 LLM 输出中提取 Python 代码块。
        支持三种格式：```python ... ```、``` ... ```、python: ...

        Args:
            text: LLM 返回的包含代码的文本。

        Returns:
            提取出的 Python 代码字符串。
        """
        # 尝试标准 markdown 格式：```python ... ```
        match = re.search(r"```python\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试通用 markdown 格式：``` ... ```
        match = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试 "python" 前缀格式（某些模型输出不带反引号）
        stripped = text.strip()
        if stripped.lower().startswith("python"):
            stripped = re.sub(r"^python\s*\n", "", stripped, flags=re.IGNORECASE)
            return stripped.strip()
        # 返回原始文本（无标记时直接返回）
        return text.strip()
