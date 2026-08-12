"""
智能体基类，封装 LLM 调用逻辑，供所有子类继承。
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

    属性:
        llm: LangChain ChatOpenAI 实例，封装 LLM 调用。
        system_prompt: 该智能体的 System Prompt 字符串。
    """

    def __init__(self, system_prompt: str) -> None:
        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=TEMPERATURE,
            openai_api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
        self.system_prompt = system_prompt

    def _call_llm(self, user_message: str, max_retries: int = 3) -> str:
        from langchain_core.messages import SystemMessage, HumanMessage
        for attempt in range(max_retries):
            try:
                response = self.llm.invoke([
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=user_message),
                ])
                text: str = response.content.strip()
                if not text:
                    raise RuntimeError("LLM 返回空响应")
                return text
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"LLM 调用失败: {e}") from e

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON 对象，使用括号平衡法。"""
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = re.sub(r"```", "", cleaned)
        start = cleaned.find("{")
        if start == -1:
            raise json.JSONDecodeError("No JSON found in response", text, 0)
        json_str = BaseAgent._find_balanced_json(cleaned, start)
        if json_str is None:
            raise json.JSONDecodeError("Could not find complete JSON", text, start)
        return json.loads(json_str.strip())

    @staticmethod
    def _find_balanced_json(text: str, start: int) -> str | None:
        """用括号平衡法找到第一个完整的 JSON 对象。"""
        depth = 0
        in_string = False
        escape = False
        i = start
        while i < len(text):
            ch = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if ch == chr(92):
                escape = True
                i += 1
                continue
            if ch == chr(34):
                in_string = not in_string
                i += 1
                continue
            if in_string:
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
            i += 1
        return text[start:] if start < len(text) else None

    @staticmethod
    def _extract_python_code(text: str) -> str:
        """从 LLM 输出中提取 Python 代码块。"""
        # Try standard markdown format: ```python ... ```
        match = re.search(r"```python\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try generic markdown format: ``` ... ```
        match = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try if it starts with "python" keyword (Agnes sometimes outputs without backticks)
        stripped = text.strip()
        if stripped.lower().startswith("python"):
            stripped = re.sub(r"^python\s*\n", "", stripped, flags=re.IGNORECASE)
            return stripped.strip()
        return text.strip()
