"""
智能体基类模块：封装 LLM 调用逻辑，为所有子类提供统一的接口。

所有智能体（Planner、Generator、Debugger）均继承此类，
共享 LLM 调用、JSON 解析、代码提取等通用能力。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
)


class BaseAgent:
    """
    所有智能体的公共基类。

    封装了与 LLM 交互的底层逻辑，包括：
    - 初始化 LangChain ChatOpenAI 客户端
    - 带重试的 LLM 调用（指数退避）
    - JSON 输出提取（处理 LLM 可能输出的 markdown 包裹）
    - Python 代码块提取

    属性:
        llm: LangChain ChatOpenAI 实例，封装 LLM 调用。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        # 使用配置文件中的参数初始化 LLM 客户端
        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=TEMPERATURE,
            openai_api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
        # 每个智能体携带自己的 System Prompt，定义其角色和行为约束
        self.system_prompt = system_prompt

    def _call_llm(self, user_message: str, max_retries: int = 3) -> str:
        """
        调用 LLM 并返回文本响应。
        失败时进行最多 max_retries 次重试，采用指数退避策略（1s, 2s, 4s）。

        Args:
            user_message: 用户消息内容。
            max_retries: 最大重试次数，默认 3 次。

        Returns:
            LLM 返回的文本字符串。

        Raises:
            RuntimeError: 所有重试均失败时抛出。
        """
        # 延迟导入，避免循环依赖
        from langchain_core.messages import SystemMessage, HumanMessage

        for attempt in range(max_retries):
            try:
                # 构造包含 System Prompt 和用户消息的消息列表
                response = self.llm.invoke([
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=user_message),
                ])
                # 清理响应文本：去除首尾空白
                text: str = response.content.strip()
                # 空响应视为错误
                if not text:
                    raise RuntimeError("LLM 返回空响应")
                return text
            except Exception as e:
                # 仍有重试机会时，等待后继续（指数退避：2^attempt 秒）
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 第0次等1s，第1次等2s，第2次等4s
                    time.sleep(wait_time)
                    continue
                # 所有重试耗尽，抛出最终异常
                raise RuntimeError(f"LLM 调用失败: {e}") from e

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """
        从 LLM 输出中提取 JSON 对象。
        LLM 有时会在 JSON 前后添加 markdown 代码块标记（```json ... ```），
        此方法会先清理这些标记，再用括号平衡法找到完整的 JSON 对象。

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
        if json_str is None:
            raise json.JSONDecodeError("Could not find complete JSON", text, start)
        # 解析 JSON 字符串为字典
        return json.loads(json_str.strip())

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
            if ch == chr(92):  # chr(92) = '\'
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
        match = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试 "python" 前缀格式（某些模型输出不带反引号）
        stripped = text.strip()
        if stripped.lower().startswith("python"):
            stripped = re.sub(r"^python\s*\n", "", stripped, flags=re.IGNORECASE)
            return stripped.strip()
        # 返回原始文本（无标记时直接返回）
        return text.strip()
