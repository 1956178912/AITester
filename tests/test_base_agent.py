"""
BaseAgent 单元测试

测试 base_agent.py 中的：
- _retry_with_exponential_backoff
- _is_zai_compatible
- _get_llm_config
- _get_or_create_chat_client（客户端复用缓存）
- BaseAgent 静态方法 (_extract_json, _find_balanced_json, _extract_python_code, truncate_code)
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# 设置路径以便导入 src 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.base_agent import (
    BaseAgent,
    _get_llm_config,
    _get_or_create_chat_client,
    _is_zai_compatible,
    _llm_client_cache,
    _retry_with_exponential_backoff,
)


class TestRetryWithExponentialBackoff:
    """测试带指数退避的重试机制。"""

    def test_success_on_first_try(self):
        """首次调用成功时直接返回结果。"""
        mock_func = MagicMock(return_value="success")
        result = _retry_with_exponential_backoff(mock_func, max_retries=3)
        assert result == "success"
        mock_func.assert_called_once()

    def test_success_after_retries(self):
        """重试后成功时返回结果。"""
        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("temporary error")
            return "success"

        result = _retry_with_exponential_backoff(flaky_func, max_retries=3, base_wait=0.01)
        assert result == "success"
        assert call_count[0] == 3

    def test_raises_after_all_retries(self):
        """所有重试失败时抛出 RuntimeError。"""

        def always_fails():
            raise ValueError("persistent error")

        with pytest.raises(RuntimeError, match="已重试 2 次"):
            _retry_with_exponential_backoff(always_fails, max_retries=2, base_wait=0.01)

    def test_non_retryable_exception(self):
        """非 retryable 异常立即抛出，不重试。"""

        def raises_type_error():
            raise TypeError("type error")

        with pytest.raises(TypeError):
            _retry_with_exponential_backoff(raises_type_error, max_retries=3, retryable_exceptions=(ValueError,))

    def test_retryable_exception_caught(self):
        """retryable 异常会被捕获并重试。"""
        call_count = [0]

        def raises_value_error():
            call_count[0] += 1
            raise ValueError("value error")

        with pytest.raises(RuntimeError):
            _retry_with_exponential_backoff(
                raises_value_error, max_retries=2, retryable_exceptions=(ValueError,), base_wait=0.01
            )
        assert call_count[0] == 3  # 首次 + 2 次重试


class TestIsZaiCompatible:
    """测试 zai SDK 兼容性检测。"""

    def test_bigmodel_domain(self):
        """智谱域名应返回 True。"""
        assert _is_zai_compatible("https://open.bigmodel.cn/api/llm/chat") is True

    def test_zhipuai_domain(self):
        """zhipuai 域名应返回 True。"""
        assert _is_zai_compatible("https://open.zhipuai.cn/api") is True

    def test_openai_domain(self):
        """OpenAI 域名应返回 False。"""
        assert _is_zai_compatible("https://api.openai.com/v1") is False

    def test_empty_url(self):
        """空 URL 应返回 False。"""
        assert _is_zai_compatible("") is False

    def test_none_domain(self):
        """None 域名应返回 False。"""
        assert _is_zai_compatible("https://example.com") is False


class TestGetLlmConfig:
    """测试 LLM 配置获取。"""

    @patch("src.agents.base_agent.LLM_CONFIGS", new=[])
    def test_empty_configs(self):
        """无配置时返回空字符串。"""
        api_key, base_url, model_name = _get_llm_config()
        assert api_key == ""
        assert base_url == ""
        assert model_name == ""

    @patch("src.agents.base_agent.LLM_CONFIGS")
    def test_returns_first_config(self, mock_configs):
        """返回第一个有效配置。"""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "test_key"
        mock_cfg.base_url = "https://api.test.com"
        mock_cfg.model_name = "test-model"
        mock_configs.__iter__ = MagicMock(return_value=iter([mock_cfg]))
        mock_configs.__len__ = MagicMock(return_value=1)
        mock_configs.__getitem__ = MagicMock(return_value=mock_cfg)

        api_key, base_url, model_name = _get_llm_config()
        assert api_key == "test_key"
        assert base_url == "https://api.test.com"
        assert model_name == "test-model"


class TestExtractJson:
    """测试 JSON 提取功能。"""

    def test_extract_simple_json(self):
        """提取简单 JSON。"""
        text = '{"key": "value"}'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_with_markdown(self):
        """提取带 markdown 包裹的 JSON。"""
        text = '```json\n{"key": "value"}\n```'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_with_text_around(self):
        """提取嵌入在文本中的 JSON。"""
        text = 'Here is the result:\n{"answer": 42}\nDone.'
        result = BaseAgent._extract_json(text)
        assert result == {"answer": 42}

    def test_extract_nested_json(self):
        """提取嵌套 JSON。"""
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = BaseAgent._extract_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_raises_when_no_json(self):
        """无 JSON 时抛出异常。"""
        with pytest.raises(json.JSONDecodeError):
            BaseAgent._extract_json("no json here")

    def test_raises_when_invalid_json(self):
        """无效 JSON 时抛出异常。"""
        with pytest.raises(json.JSONDecodeError):
            BaseAgent._extract_json("{invalid json}")

    def test_extract_json_with_escaped_quotes(self):
        """提取含转义引号的 JSON。"""
        text = '{"message": "He said \\"hello\\""}'
        result = BaseAgent._extract_json(text)
        assert result["message"] == 'He said "hello"'


class TestFindBalancedJson:
    """测试括号平衡法提取 JSON。"""

    def test_balanced_json(self):
        """正常匹配的 JSON。"""
        text = '{"a": 1, "b": 2}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_unbalanced_json(self):
        """未闭合的 JSON 返回剩余部分。"""
        text = '{"a": 1,'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_nested_json(self):
        """嵌套 JSON。"""
        text = '{"a": {"b": {"c": 1}}}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_json_with_strings(self):
        """含字符串的 JSON。"""
        text = '{"msg": "hello {world}"}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_out_of_bounds_start(self):
        """起始位置越界返回 None。"""
        result = BaseAgent._find_balanced_json("{}", 5)
        assert result is None


class TestExtractPythonCode:
    """测试 Python 代码提取功能。"""

    def test_extract_python_fenced(self):
        """提取 ```python 标记的代码块。"""
        text = "```python\ndef hello():\n    pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result

    def test_extract_generic_fenced(self):
        """提取通用 ``` 标记的代码块。"""
        text = "```\ndef hello():\n    pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result

    def test_extract_python_prefix(self):
        """提取 python: 前缀的代码。"""
        text = "python:\ndef hello():\n    pass"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result

    def test_extract_plain_code(self):
        """无标记时直接返回代码。"""
        text = "def hello():\n    pass"
        result = BaseAgent._extract_python_code(text)
        assert result == text.strip()

    def test_prefer_python_fence(self):
        """优先匹配 python 标记。"""
        text = "```javascript\nvar x = 1;\n```\n```python\ndef hello(): pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result


class TestTruncateCode:
    """测试代码截断功能。"""

    def test_short_code_not_truncated(self):
        """短代码不被截断。"""
        code = "def hello():\n    pass"
        result = BaseAgent.truncate_code(code)
        assert result == code

    def test_long_code_truncated(self):
        """长代码被截断。"""
        code = "x = " * 2000 + "\ndef hello():\n    pass"
        result = BaseAgent.truncate_code(code, max_chars=100)
        assert len(result) <= 100
        assert "[代码已截断" in result

    def test_truncate_with_custom_max(self):
        """自定义最大字符数。"""
        code = "a" * 500
        result = BaseAgent.truncate_code(code, max_chars=100)
        assert len(result) <= 100


class TestBaseAgentInit:
    """测试 BaseAgent 初始化。"""

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._get_llm_config")
    def test_init_sets_llm(self, mock_get_config, mock_chat_openai):
        """验证初始化时设置 llm 和 system_prompt。"""
        mock_get_config.return_value = ("key", "url", "model")
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        agent = BaseAgent("test prompt")

        assert agent.system_prompt == "test prompt"
        assert agent.llm == mock_llm
        mock_chat_openai.assert_called_once()


class TestChatClientReuse:
    """测试 _get_or_create_chat_client 客户端复用缓存（性能优化）。"""

    @pytest.fixture(autouse=True)
    def _clear_client_cache(self):
        """每个测试前清空客户端缓存，避免相互干扰。"""
        _llm_client_cache.clear()
        yield
        _llm_client_cache.clear()

    @patch("src.agents.base_agent.ChatOpenAI")
    def test_same_config_reuses_client(self, mock_chat_openai):
        """相同配置返回同一实例，ChatOpenAI 只构建一次。"""
        c1 = _get_or_create_chat_client("model-a", 0.0, "key-1", "https://test.example.com/v1")
        c2 = _get_or_create_chat_client("model-a", 0.0, "key-1", "https://test.example.com/v1")

        assert c1 is c2
        mock_chat_openai.assert_called_once()

    @patch("src.agents.base_agent.ChatOpenAI")
    def test_different_config_creates_new_client(self, mock_chat_openai):
        """不同模型（缓存键不同）构建新实例。"""
        client_a, client_b = MagicMock(name="client_a"), MagicMock(name="client_b")
        mock_chat_openai.side_effect = [client_a, client_b]

        c1 = _get_or_create_chat_client("model-a", 0.0, "key-1", "https://test.example.com/v1")
        c2 = _get_or_create_chat_client("model-b", 0.0, "key-1", "https://test.example.com/v1")

        assert c1 is client_a
        assert c2 is client_b
        assert mock_chat_openai.call_count == 2

    @patch("src.agents.base_agent.ChatOpenAI")
    def test_fifo_eviction_at_capacity(self, mock_chat_openai, monkeypatch):
        """缓存达到上限时按 FIFO 淘汰最早条目。"""
        import src.agents.base_agent as ba

        monkeypatch.setattr(ba, "_MAX_CACHED_LLM_CLIENTS", 2)

        k1 = ("m1", 0.0, "k", "https://a.example.com")
        k2 = ("m2", 0.0, "k", "https://a.example.com")
        k3 = ("m3", 0.0, "k", "https://a.example.com")
        _get_or_create_chat_client(*k1)
        _get_or_create_chat_client(*k2)
        _get_or_create_chat_client(*k3)

        assert len(_llm_client_cache) == 2
        assert k1 not in _llm_client_cache  # 最早插入的 m1 被淘汰
        assert k3 in _llm_client_cache

    @patch("src.agents.base_agent._get_all_api_configs")
    @patch("src.agents.base_agent._get_llm_config")
    @patch("src.agents.base_agent.ChatOpenAI")
    def test_call_llm_reuses_client_across_calls(self, mock_chat_openai, mock_get_config, mock_all_configs):
        """_call_llm 连续两次调用复用同一客户端（连接池跨调用复用）。"""
        mock_get_config.return_value = ("init-key", "init-url", "init-model")
        mock_all_configs.return_value = [("key-1", "https://test.example.com/v1", "model-a")]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="  ok  ")
        mock_chat_openai.return_value = mock_llm

        agent = BaseAgent("system prompt")
        # 初始化已构建 1 个客户端（init-key 组合），_call_llm 走 key-1 组合
        result1 = agent._call_llm("hello")
        calls_after_first = mock_chat_openai.call_count
        result2 = agent._call_llm("hello")

        assert result1 == "ok"
        assert result2 == "ok"
        assert calls_after_first == mock_chat_openai.call_count  # 第二次调用未新建客户端
        assert mock_llm.invoke.call_count == 2
