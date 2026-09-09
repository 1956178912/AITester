"""
通用工具模块：提供跨模块的公共工具函数。

本模块集中管理被多个子模块重复使用的工具函数，遵循 DRY 原则：
- extract_code_block(): 从 LLM 输出中提取代码块（支持多种格式）
- extract_json(): 从文本中提取 JSON 对象（含括号平衡法）

使用示例：
    from src.utils.helpers import extract_code_block, extract_json
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 预编译正则表达式（避免重复编译开销）
# 匹配 ```python ... ``` 或 ``` ... ``` 代码块
_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*\n(.*?)\n\s*```", re.DOTALL)
# 匹配最内层无嵌套的 {...} JSON 对象
_JSON_LEAF_PATTERN = re.compile(r"\{[^{}]*\}")


def extract_code_block(text: str, language: str | None = None) -> str:
    """
    从 LLM 输出中提取代码块。

    支持三种格式（按优先级）：
    1. ```python ... ```（带语言标记的 markdown 代码块）
    2. ``` ... ```（通用 markdown 代码块）
    3. python: ... 前缀格式（某些模型输出不带反引号）
    4. 纯文本（无标记时直接返回）

    Args:
        text: LLM 返回的包含代码的原始文本。
        language: 期望的代码语言（如 "python"），None 表示不限制。

    Returns:
        提取出的代码字符串（已去除 markdown 包裹和首尾空白）。
    """
    # 尝试带语言标记的格式：```python ... ```（优先匹配）
    match = re.search(r"```python\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试通用 markdown 格式：``` ... ```
    match = _CODE_BLOCK_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    # 尝试 "python" 前缀格式（某些模型输出不带反引号，如 "python:\n..."）
    stripped = text.strip()
    if stripped.lower().startswith("python"):
        # 去除 "python" 或 "python:" 前缀及紧随的换行
        stripped = re.sub(r"^python\s*:?\s*\n?", "", stripped, flags=re.IGNORECASE)
        return stripped.strip()

    # 返回原始文本（strip 空白）
    return text.strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """
    从文本中提取 JSON 对象。

    处理流程：
    1. 移除 markdown 代码块标记（```json 或 ```）
    2. 使用括号平衡法找到完整的 JSON 对象
    3. 若失败，用正则提取候选 JSON 作为降级方案

    Args:
        text: 包含 JSON 对象的文本。

    Returns:
        解析后的字典对象。

    Raises:
        json.JSONDecodeError: 无法找到有效 JSON 时抛出。
    """
    # 移除 markdown 代码块标记
    cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
    cleaned = re.sub(r"```", "", cleaned)

    # 找到第一个 '{' 位置
    start = cleaned.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON found in response", text, 0)

    # 使用括号平衡法提取完整 JSON
    json_str = _find_balanced_json(cleaned, start)
    if json_str is not None:
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            pass  # 降级到正则方案

    # 降级方案：用正则匹配最内层无嵌套的 {...}
    for match in reversed(list(_JSON_LEAF_PATTERN.finditer(cleaned))):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue

    # 所有方案均失败
    raise json.JSONDecodeError("Could not find complete JSON", text, start)


def _find_balanced_json(text: str, start: int) -> str | None:
    """
    使用括号平衡法找到从 start 位置开始的第一个完整 JSON 对象。

    算法原理：
    - 遇到 '{' 深度+1，遇到 '}' 深度-1
    - 当深度归零时，说明找到了匹配的右花括号
    - 字符串字面量内的 '{' 和 '}' 不计入深度

    Args:
        text: 待搜索的文本。
        start: 起始搜索位置（应为 '{' 的位置）。

    Returns:
        完整的 JSON 字符串，未找到时返回 None。
    """
    depth = 0
    in_string = False
    escape = False

    if start < 0 or start >= len(text):
        return None

    i = start
    while i < len(text):
        ch = text[i]

        # 处理转义
        if escape:
            escape = False
            i += 1
            continue

        # 遇到反斜杠，标记下一个字符为转义字符
        if ch == "\\":
            escape = True
            i += 1
            continue

        # 遇到双引号，切换字符串状态
        if ch == '"':
            in_string = not in_string
            i += 1
            continue

        # 在字符串内部时跳过
        if in_string:
            i += 1
            continue

        # 处理花括号深度变化
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

        i += 1

    # JSON 对象未闭合，返回剩余部分供调用方降级处理
    return text[start:] if start < len(text) else None
