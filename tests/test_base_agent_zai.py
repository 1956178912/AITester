"""
补充测试：BaseAgent 的 zai SDK 调用路径和 LLM 调用重试/故障转移逻辑。

覆盖范围（任务 t1）：
    - _call_zai：成功响应、空响应重试、速率限制重试、状态错误重试、通用异常重试
    - _get_llm_config：线程局部配置覆盖、model_name 未设置时回退全局默认
    - BaseAgent._call_llm：OpenAI 兼容路径成功、zai 兼容路径成功、API 故障转移、空响应处理
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCallZai:
    """测试 _call_zai 函数（zai SDK 调用路径）。"""

    @patch("zai.ZhipuAiClient")
    def test_success_returns_content(self, mock_client_cls):
        """zai SDK 调用成功时返回消息内容。"""
        from src.agents.base_agent import _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello world"
        mock_msg.reasoning_content = None
        mock_response.choices = [MagicMock(message=mock_msg)]
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        result = _call_zai("key", "https://open.bigmodel.cn/api", "glm-4.7-flash", "sys", "user")
        assert result == "Hello world"
        mock_client_cls.assert_called_once_with(api_key="key", base_url="https://open.bigmodel.cn/api")
        mock_client_cls.return_value.chat.completions.create.assert_called_once()

    @patch("zai.ZhipuAiClient")
    def test_fallback_to_reasoning_content(self, mock_client_cls):
        """content 为空时使用 reasoning_content。"""
        from src.agents.base_agent import _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.reasoning_content = "reasoning text"
        mock_response.choices = [MagicMock(message=mock_msg)]
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        result = _call_zai("key", "https://open.bigmodel.cn/api", "glm-4.7-flash", "sys", "user")
        assert result == "reasoning text"

    @patch("zai.ZhipuAiClient")
    def test_empty_response_raises_runtime_error(self, mock_client_cls):
        """content 和 reasoning_content 均为空时抛出 RuntimeError。"""
        from src.agents.base_agent import _DEFAULT_LLM_MAX_RETRIES, _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.reasoning_content = None
        mock_response.choices = [MagicMock(message=mock_msg)]
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        with pytest.raises(RuntimeError, match="zai API 调用失败"):
            _call_zai(
                "key", "https://open.bigmodel.cn/api", "model", "sys", "user", max_retries=_DEFAULT_LLM_MAX_RETRIES
            )
        # 应尝试 1 + max_retries 次（首次 + 重试）
        assert mock_client_cls.return_value.chat.completions.create.call_count == _DEFAULT_LLM_MAX_RETRIES + 1

    @patch("src.agents.base_agent.time.sleep")
    @patch("zai.ZhipuAiClient")
    def test_rate_limit_retries_then_succeeds(self, mock_client_cls, mock_sleep):
        """速率限制时指数退避重试，最终成功。"""
        from zai.core._errors import APIReachLimitError

        from src.agents.base_agent import _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "OK"
        mock_msg.reasoning_content = None
        mock_response.choices = [MagicMock(message=mock_msg)]

        # 前两次限流，第三次成功
        mock_client_cls.return_value.chat.completions.create.side_effect = [
            APIReachLimitError("rate limited", response=MagicMock()),
            APIReachLimitError("rate limited", response=MagicMock()),
            mock_response,
        ]

        result = _call_zai("key", "https://open.bigmodel.cn/api", "model", "sys", "user", max_retries=3)
        assert result == "OK"
        assert mock_client_cls.return_value.chat.completions.create.call_count == 3
        # 验证等待时间：指数退避 base_wait=5，attempt=0 时 5^0=1s，attempt=1 时 5^1=5s
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 5

    @patch("src.agents.base_agent.time.sleep")
    @patch("zai.ZhipuAiClient")
    def test_status_error_retries_then_succeeds(self, mock_client_cls, mock_sleep):
        """API 状态错误时指数退避重试（1s, 2s），最终成功。"""
        from zai.core._errors import APIStatusError

        from src.agents.base_agent import _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "OK"
        mock_msg.reasoning_content = None
        mock_response.choices = [MagicMock(message=mock_msg)]

        mock_client_cls.return_value.chat.completions.create.side_effect = [
            APIStatusError("bad request", response=MagicMock()),
            mock_response,
        ]

        result = _call_zai("key", "https://open.bigmodel.cn/api", "model", "sys", "user", max_retries=2)
        assert result == "OK"
        # 使用指数退避（base_wait=1），第一次等 1s
        assert mock_sleep.call_args_list[0][0][0] == 1

    @patch("src.agents.base_agent.time.sleep")
    @patch("zai.ZhipuAiClient")
    def test_generic_exception_retries_then_fails(self, mock_client_cls, mock_sleep):
        """通用异常重试耗尽后抛出 RuntimeError。"""
        from src.agents.base_agent import _DEFAULT_LLM_MAX_RETRIES, _call_zai

        mock_client_cls.return_value.chat.completions.create.side_effect = ValueError("network error")

        with pytest.raises(RuntimeError, match="zai API 调用失败"):
            _call_zai("key", "https://open.bigmodel.cn/api", "model", "sys", "user")
        # 应尝试 1 + max_retries 次
        assert mock_client_cls.return_value.chat.completions.create.call_count == _DEFAULT_LLM_MAX_RETRIES + 1

    @patch("zai.ZhipuAiClient")
    def test_kwargs_passes_thinking_disabled(self, mock_client_cls):
        """确认 thinking.disabled 参数正确传递。"""
        from src.agents.base_agent import _call_zai

        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "OK"
        mock_msg.reasoning_content = None
        mock_response.choices = [MagicMock(message=mock_msg)]
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        _call_zai("key", "https://open.bigmodel.cn/api", "model", "sys", "user")

        call_kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert call_kwargs["thinking"] == {"type": "disabled"}
        assert call_kwargs["max_tokens"] == 4096


class TestGetLlmConfigThreadLocal:
    """测试 _get_llm_config 的线程局部覆盖。"""

    @patch("src.agents.base_agent.LLM_CONFIGS")
    def test_thread_local_overrides_global(self, mock_configs):
        """线程局部设置覆盖全局配置。"""
        from src.agents.base_agent import _get_llm_config, _thread_local

        mock_configs.__len__ = MagicMock(return_value=1)
        mock_cfg = MagicMock()
        mock_cfg.api_key = "global-key"
        mock_cfg.base_url = "https://global.api"
        mock_cfg.model_name = "global-model"
        mock_configs.__getitem__ = MagicMock(return_value=mock_cfg)
        mock_configs.__iter__ = MagicMock(side_effect=iter([mock_cfg]))

        # 设置线程局部覆盖
        _thread_local.api_key = "thread-key"
        _thread_local.base_url = "https://thread.api"
        # 不设置 model_name，应回退到全局默认
        try:
            key, url, model = _get_llm_config()
            assert key == "thread-key"
            assert url == "https://thread.api"
            assert model == "global-model"
        finally:
            delattr(_thread_local, "api_key")
            delattr(_thread_local, "base_url")

    @patch("src.agents.base_agent.LLM_CONFIGS")
    def test_thread_local_with_explicit_model(self, mock_configs):
        """线程局部同时设置 model_name 时优先使用。"""
        from src.agents.base_agent import _get_llm_config, _thread_local

        mock_configs.__len__ = MagicMock(return_value=1)
        mock_cfg = MagicMock()
        mock_cfg.model_name = "global-model"
        mock_configs.__getitem__ = MagicMock(return_value=mock_cfg)

        _thread_local.api_key = "tk"
        _thread_local.base_url = "bu"
        _thread_local.model_name = "thread-model"
        try:
            key, url, model = _get_llm_config()
            assert model == "thread-model"
        finally:
            delattr(_thread_local, "api_key")
            delattr(_thread_local, "base_url")
            delattr(_thread_local, "model_name")


class TestCallLlm:
    """测试 BaseAgent._call_llm 方法（OpenAI 兼容路径 + zai 故障转移）。"""

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_openai_path_success(self, mock_get_configs, mock_llm_cls):
        """OpenAI 兼容接口调用成功。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [("key", "https://api.openai.com", "gpt-4")]
        mock_llm_instance = MagicMock()
        mock_llm_cls.return_value = mock_llm_instance

        mock_response = MagicMock()
        mock_response.content = "success"
        mock_llm_instance.invoke.return_value = mock_response

        agent = BaseAgent(system_prompt="test")
        result = agent._call_llm("hello")
        assert result == "success"
        mock_llm_instance.invoke.assert_called_once()

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_openai_empty_response_raises(self, mock_get_configs, mock_llm_cls):
        """OpenAI 返回空响应时抛出 RuntimeError。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [("key", "https://api.openai.com", "gpt-4")]
        mock_llm_instance = MagicMock()
        mock_llm_cls.return_value = mock_llm_instance
        mock_response = MagicMock()
        mock_response.content = ""
        mock_llm_instance.invoke.return_value = mock_response

        agent = BaseAgent(system_prompt="test")
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent._is_zai_compatible", return_value=True)
    @patch("src.agents.base_agent._call_zai")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_zai_path_used_for_bigmodel(self, mock_get_configs, mock_call_zai, mock_is_zai):
        """BigModel URL 走 zai SDK 路径。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [("key", "https://open.bigmodel.cn/api", "glm-4.7-flash")]
        mock_call_zai.return_value = "zai response"

        agent = BaseAgent(system_prompt="test")
        result = agent._call_llm("hello")
        assert result == "zai response"
        mock_call_zai.assert_called_once()

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_fallback_to_next_api_on_failure(self, mock_get_configs, mock_is_zai, mock_llm_cls):
        """主 API 失败时自动切换到备用 API。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [
            ("key1", "https://api.openai.com", "gpt-4"),
            ("key2", "https://api.backup.com", "gpt-3.5"),
        ]

        # 第一个 API 抛异常，第二个成功
        mock_llm_instance_fail = MagicMock()
        mock_llm_instance_fail.invoke.side_effect = RuntimeError("api down")
        mock_llm_cls.side_effect = [mock_llm_instance_fail, MagicMock()]

        mock_llm_instance_ok = mock_llm_cls.return_value
        mock_response = MagicMock()
        mock_response.content = "backup ok"
        mock_llm_instance_ok.invoke.return_value = mock_response

        agent = BaseAgent(system_prompt="test")
        result = agent._call_llm("hello")
        assert result == "backup ok"
        assert mock_llm_cls.call_count == 2

    @patch("src.agents.base_agent._get_all_api_configs")
    def test_no_configs_raises(self, mock_get_configs):
        """无 API 配置时抛出 RuntimeError。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = []
        agent = BaseAgent(system_prompt="test")
        with pytest.raises(RuntimeError, match="未配置任何 LLM API"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_all_apis_fail_raises(self, mock_get_configs, mock_llm_cls):
        """所有 API 均失败时抛出 RuntimeError。"""
        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [
            ("key1", "https://api1.com", "model1"),
            ("key2", "https://api2.com", "model2"),
        ]
        mock_instance = MagicMock()
        mock_instance.invoke.side_effect = RuntimeError("both down")
        mock_llm_cls.return_value = mock_instance

        agent = BaseAgent(system_prompt="test")
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_api_id_extracted_from_url(self, mock_get_configs, mock_llm_cls):
        """成功调用时日志中包含 API 主机名。"""
        import logging

        from src.agents.base_agent import BaseAgent

        mock_get_configs.return_value = [("key", "https://open.bigmodel.cn/api/v1", "model")]
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_instance.invoke.return_value = mock_response

        agent = BaseAgent(system_prompt="test")
        with patch.object(logging.getLogger("src.agents.base_agent"), "info") as mock_info:
            agent._call_llm("hello")
            # 成功日志应包含主机名
            called_args = [call[0][1] for call in mock_info.call_args_list]
            assert any("open.bigmodel.cn" in str(a) for a in called_args)
