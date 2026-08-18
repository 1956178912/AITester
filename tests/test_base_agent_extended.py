"""
补充测试：base_agent.py 未覆盖路径的 mock 测试。

覆盖范围：
    - _retry_with_exponential_backoff：成功、重试后成功、全部失败、异常过滤
    - _call_llm_with_cache：缓存命中、缓存未命中、缓存读写异常
    - _find_balanced_json 边界情况：越界、空文本、多个 JSON
    - _extract_python_code 边缘情况
    - _extract_json 边缘情况
"""

import json
from unittest.mock import patch

import pytest


class TestRetryWithExponentialBackoff:
    """测试 _retry_with_exponential_backoff 通用重试工具函数。"""

    def test_success_on_first_try(self):
        """首次调用成功，不重试。"""
        from src.agents.base_agent import _retry_with_exponential_backoff

        result = _retry_with_exponential_backoff(lambda: "ok", max_retries=3)
        assert result == "ok"

    @patch("src.agents.base_agent.time.sleep")
    def test_retry_then_succeed(self, mock_sleep):
        """前两次失败，第三次成功。"""
        from src.agents.base_agent import _retry_with_exponential_backoff

        call_count = [0]

        def side_effect():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError(f"fail{call_count[0]}")
            return "success"

        result = _retry_with_exponential_backoff(side_effect, max_retries=3, base_wait=1)
        assert result == "success"
        assert mock_sleep.call_count == 2
        # base_wait=1 时，1^attempt 始终为 1（任何次幂都是 1）
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 1

    def test_all_retries_fail_raises_runtime_error(self):
        """所有重试均失败时抛出 RuntimeError。"""
        from src.agents.base_agent import _DEFAULT_LLM_MAX_RETRIES, _retry_with_exponential_backoff

        def always_fail():
            raise ValueError("always fail")

        with pytest.raises(RuntimeError, match="已重试"):
            _retry_with_exponential_backoff(always_fail, max_retries=_DEFAULT_LLM_MAX_RETRIES)

    def test_non_retryable_exception_raises_immediately(self):
        """非 retryable 异常立即抛出，不重试。"""
        from src.agents.base_agent import _retry_with_exponential_backoff

        def raise_type_error():
            raise TypeError("unexpected")

        with pytest.raises(TypeError, match="unexpected"):
            _retry_with_exponential_backoff(
                raise_type_error,
                max_retries=3,
                retryable_exceptions=(ValueError,),
            )


class TestCallLlmWithCache:
    """测试 BaseAgent._call_llm_with_cache 缓存逻辑。"""

    @patch("src.agents.base_agent.BaseAgent._call_llm")
    def test_cache_miss_calls_llm(self, mock_call_llm):
        """缓存未命中时调用 LLM 并返回结果。"""
        from src.agents.base_agent import BaseAgent

        mock_call_llm.return_value = "llm_response"
        agent = BaseAgent(system_prompt="sys_prompt_test")

        with patch("os.path.exists", return_value=False):
            result = agent._call_llm_with_cache("hello")

        assert result == "llm_response"
        mock_call_llm.assert_called_once_with("hello", 3)

    @patch("src.agents.base_agent.BaseAgent._call_llm")
    def test_cache_hit_returns_cached_and_skips_llm(self, mock_call_llm):
        """缓存命中时直接返回缓存响应，不调用 LLM。"""
        from src.agents.base_agent import BaseAgent

        mock_call_llm.return_value = "llm_response"
        agent = BaseAgent(system_prompt="sys_prompt_test")

        cached_content = json.dumps(
            {
                "prompt": "hello",
                "system": "sys_prompt_test",
                "response": "cached_answer",
            }
        )

        class FakeFile:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return cached_content

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", return_value=FakeFile()):
                result = agent._call_llm_with_cache("hello")

        assert result == "cached_answer"
        mock_call_llm.assert_not_called()

    @patch("src.agents.base_agent.BaseAgent._call_llm")
    def test_cache_read_error_falls_through_to_llm(self, mock_call_llm):
        """缓存读取异常时降级到真实 LLM 调用。"""
        from src.agents.base_agent import BaseAgent

        mock_call_llm.return_value = "real_response"
        agent = BaseAgent(system_prompt="sys_prompt")

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=OSError("read error")):
                result = agent._call_llm_with_cache("hello")

        assert result == "real_response"
        mock_call_llm.assert_called_once()

    @patch("src.agents.base_agent.BaseAgent._call_llm")
    def test_cache_write_error_does_not_affect_result(self, mock_call_llm):
        """缓存写入异常不影响正常返回值。"""
        from src.agents.base_agent import BaseAgent

        mock_call_llm.return_value = "response"
        agent = BaseAgent(system_prompt="sys")

        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs", side_effect=OSError("disk full")):
                result = agent._call_llm_with_cache("hello")

        assert result == "response"


class TestFindBalancedJsonEdgeCases:
    """测试 _find_balanced_json 边界情况。"""

    def test_start_negative_returns_none(self):
        """start 为负数时返回 None。"""
        from src.agents.base_agent import BaseAgent

        assert BaseAgent._find_balanced_json('{"a": 1}', -1) is None

    def test_start_too_large_returns_none(self):
        """start 超出文本长度时返回 None。"""
        from src.agents.base_agent import BaseAgent

        assert BaseAgent._find_balanced_json('{"a": 1}', 100) is None

    def test_empty_text_returns_none(self):
        """空文本返回 None。"""
        from src.agents.base_agent import BaseAgent

        assert BaseAgent._find_balanced_json("", 0) is None

    def test_multiple_jsons_returns_first(self):
        """多个 JSON 对象时返回第一个完整的。"""
        from src.agents.base_agent import BaseAgent

        text = '{"a": 1} some text {"b": 2}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"a": 1}'

    def test_deeply_nested_json(self):
        """深层嵌套 JSON 正确平衡。"""
        from src.agents.base_agent import BaseAgent

        text = '{"a": {"b": {"c": [1, 2, {"d": true}]}}}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_unmatched_closing_brace_returns_remainder(self):
        """未匹配的右括号时返回从 start 到末尾的片段。"""
        from src.agents.base_agent import BaseAgent

        text = '{"a": 1'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"a": 1'


class TestExtractPythonCodeEdgeCases:
    """测试 _extract_python_code 边缘情况。"""

    def test_no_markers_returns_stripped(self):
        """无标记时返回 strip 后的原文。"""
        from src.agents.base_agent import BaseAgent

        text = "  def foo(): pass  "
        result = BaseAgent._extract_python_code(text)
        assert result == "def foo(): pass"

    def test_python_prefix_uppercase(self):
        """PYTHON: (大写) 前缀也能匹配。"""
        from src.agents.base_agent import BaseAgent

        text = "PYTHON:\nprint('hi')"
        result = BaseAgent._extract_python_code(text)
        assert "print('hi')" in result

    def test_generic_fence_extraction(self):
        """``` 无语言标记时也能提取。"""
        from src.agents.base_agent import BaseAgent

        text = "```\nresult = 1 + 2\n```"
        result = BaseAgent._extract_python_code(text)
        assert result == "result = 1 + 2"

    def test_python_fence_takes_priority_over_generic(self):
        """```python 优先于通用 ``` 匹配。"""
        from src.agents.base_agent import BaseAgent

        text = "```python\ndef a(): pass\n```\n```\ndef b(): pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def a" in result
        assert "def b" not in result


class TestExtractJsonEdgeCases:
    """测试 _extract_json 边缘情况。"""

    def test_no_braces_raises_decode_error(self):
        """文本中无 { 时抛出明确的 JSONDecodeError。"""
        from src.agents.base_agent import BaseAgent

        with pytest.raises(json.JSONDecodeError, match="No JSON found"):
            BaseAgent._extract_json("just plain text")

    def test_incomplete_json_raises_decode_error(self):
        """不完整的 JSON 对象（无闭合括号）时正则也匹配不到，抛错。"""
        from src.agents.base_agent import BaseAgent

        text = '{"key": "value"'  # 缺少右括号，正则 {_JSON_LEAF_PATTERN} 无法匹配
        with pytest.raises(json.JSONDecodeError, match="Could not find complete JSON"):
            BaseAgent._extract_json(text)

    def test_empty_object_parsed(self):
        """空对象 {} 能正确解析。"""
        from src.agents.base_agent import BaseAgent

        result = BaseAgent._extract_json("{}")
        assert result == {}

    def test_whitespace_around_json(self):
        """JSON 前后有空格或换行时仍能解析。"""
        from src.agents.base_agent import BaseAgent

        text = '  \n  {"a": 1}  \n'
        result = BaseAgent._extract_json(text)
        assert result == {"a": 1}

    def test_json_with_trailing_text(self):
        """JSON 后有冗余文字时仍能正确解析。"""
        from src.agents.base_agent import BaseAgent

        text = '{"a": 1} some trailing text'
        result = BaseAgent._extract_json(text)
        assert result == {"a": 1}
