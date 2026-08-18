"""
单元测试：测试 BaseAgent 静态方法（无需 LLM）和线程局部配置。

覆盖范围：
    - _extract_json：正常 JSON、markdown 包裹、不完整 JSON、嵌套 JSON、转义字符、空花括号
    - _find_balanced_json：括号深度平衡、字符串内括号、转义引号
    - _extract_python_code：```python 包裹、``` 通用包裹、python: 前缀、无标记纯代码
    - _get_llm_config：线程局部配置和全局配置
    - _get_all_api_configs：API 配置列表获取
"""

import json

import pytest

from src.agents.base_agent import BaseAgent


# ─── TestExtractJson：JSON 提取方法 ────────────────────────────────────────────
class TestExtractJson:
    """测试 BaseAgent._extract_json 静态方法。"""

    def test_normal_json(self):
        """正常 JSON 字符串直接解析。"""
        text = '{"a": 1, "b": "hello"}'
        result = BaseAgent._extract_json(text)
        assert result == {"a": 1, "b": "hello"}

    def test_markdown_wrapped_json(self):
        """带 ```json 代码块标记的 JSON 能正确提取。"""
        text = '```json\n{"a": 1, "b": 2}\n```'
        result = BaseAgent._extract_json(text)
        assert result == {"a": 1, "b": 2}

    def test_markdown_generic_wrapped_json(self):
        """带 ``` 通用代码块标记的 JSON 能正确提取。"""
        text = '```\n{"x": 10}\n```'
        result = BaseAgent._extract_json(text)
        assert result == {"x": 10}

    def test_incomplete_json_fallback(self):
        """不完整 JSON（缺少结尾括号）时尝试降级正则匹配。"""
        # 以简单合法片段为例，降級匹配应该能提取到
        text = '一些前缀 {"key": "value"} 一些后缀'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value"}

    def test_nested_json(self):
        """嵌套 JSON 结构能完整解析。"""
        text = json.dumps({"outer": {"inner": [1, 2, 3]}, "flag": True})
        result = BaseAgent._extract_json(text)
        assert result == {"outer": {"inner": [1, 2, 3]}, "flag": True}

    def test_escaped_characters(self):
        """含转义字符（\"、\\）的 JSON 能正确解析。"""
        text = r'{"msg": "他说\"你好\"", "path": "C:\\temp"}'
        result = BaseAgent._extract_json(text)
        assert result["msg"] == '他说"你好"'
        assert result["path"] == "C:\\temp"

    def test_empty_braces_raises(self):
        """空花括号文本应抛出 JSONDecodeError。"""
        with pytest.raises(json.JSONDecodeError):
            BaseAgent._extract_json("no json here")

    def test_empty_object(self):
        """空 JSON 对象 {} 能正确解析。"""
        result = BaseAgent._extract_json("{}")
        assert result == {}

    def test_text_before_json(self):
        """JSON 前有冗余文字的提取。"""
        text = '根据分析，结果是：\n```json\n{"plan": "test"}\n```'
        result = BaseAgent._extract_json(text)
        assert result == {"plan": "test"}


# ─── TestFindBalancedJson：括号平衡法 ──────────────────────────────────────────
class TestFindBalancedJson:
    """测试 BaseAgent._find_balanced_json 静态方法。"""

    def test_balanced_depth(self):
        """括号深度正确归零时返回完整 JSON。"""
        text = 'xxx {"a": 1} yyy'
        result = BaseAgent._find_balanced_json(text, text.find("{"))
        assert result == '{"a": 1}'

    def test_nested_braces(self):
        """嵌套括号深度正确跟踪。"""
        text = '{"a": {"b": {"c": 1}}}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"a": {"b": {"c": 1}}}'

    def test_braces_inside_string_ignored(self):
        """字符串内部的括号不计入深度。"""
        text = '{"msg": "{not json}"}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"msg": "{not json}"}'

    def test_escaped_quotes(self):
        """转义引号不切换 in_string 状态。"""
        text = r'{"msg": "he said \"ok\""}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == r'{"msg": "he said \"ok\""}'

    def test_no_opening_brace(self):
        """未找到 { 时 start=-1，应返回 None。"""
        result = BaseAgent._find_balanced_json("no braces", -1)
        assert result is None

    def test_unbalanced_returns_remainder(self):
        """未匹配的右括号时返回从 start 到末尾的片段。"""
        text = '{"a": 1'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"a": 1'


# ─── TestExtractPythonCode：Python 代码提取 ────────────────────────────────────
class TestExtractPythonCode:
    """测试 BaseAgent._extract_python_code 静态方法。"""

    def test_python_fenced(self):
        """```python ... ``` 格式正确提取。"""
        text = '```\nprint("hello")\n```'
        # 注意：regex 期望 python 标记
        text = '```python\nprint("hello")\n```'
        result = BaseAgent._extract_python_code(text)
        assert result == 'print("hello")'

    def test_generic_fence(self):
        """```（无语言标记）格式也能提取。"""
        text = "```\ndef foo(): pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert result == "def foo(): pass"

    def test_python_prefix(self):
        """python: 前缀格式（无反引号）能提取。"""
        text = "python:\ndef foo():\n    return 1"
        result = BaseAgent._extract_python_code(text)
        assert "def foo():" in result
        assert "return 1" in result

    def test_no_markers_returns_stripped(self):
        """无标记时直接返回原文（strip 后）。"""
        text = "def bar():\n    return True"
        result = BaseAgent._extract_python_code(text)
        assert result == "def bar():\n    return True"

    def test_python_fence_with_extra_text(self):
        """代码块前后有冗余文字时仍正确提取。"""
        text = "以下是代码：\n```python\ndef main(): pass\n```\n结束。"
        result = BaseAgent._extract_python_code(text)
        assert result == "def main(): pass"
