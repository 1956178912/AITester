"""
单元测试：测试 BaseAgent 的辅助函数（无需真实 API）。

覆盖范围：
    - _is_zai_compatible: 判断是否为大模型兼容接口
    - _get_llm_config: 无配置时返回空串
    - _get_all_api_configs: 无配置时返回空列表
"""

import pytest
from unittest.mock import patch


class TestIsZaiCompatible:
    """测试 _is_zai_compatible 函数。"""

    def test_bigmodel_domain(self):
        """bigmodel.cn 域名应返回 True。"""
        from src.agents.base_agent import _is_zai_compatible
        assert _is_zai_compatible("https://open.bigmodel.cn/api") is True

    def test_zhipuai_domain(self):
        """zhipuai 域名应返回 True。"""
        from src.agents.base_agent import _is_zai_compatible
        assert _is_zai_compatible("https://api.zhipuai.cn") is True

    def test_openai_domain(self):
        """openai.com 域名应返回 False。"""
        from src.agents.base_agent import _is_zai_compatible
        assert _is_zai_compatible("https://api.openai.com") is False

    def test_empty_url(self):
        """空 URL 应返回 False。"""
        from src.agents.base_agent import _is_zai_compatible
        assert _is_zai_compatible("") is False

    def test_custom_domain(self):
        """自定义域名应返回 False。"""
        from src.agents.base_agent import _is_zai_compatible
        assert _is_zai_compatible("https://custom.api.com") is False


class TestGetLlmConfig:
    """测试 _get_llm_config 函数。"""

    @patch("src.agents.base_agent.LLM_CONFIGS", [])
    def test_no_configs_returns_empty(self):
        """无配置时返回空字符串。"""
        from src.agents.base_agent import _get_llm_config
        api_key, base_url, model = _get_llm_config()
        assert api_key == ""
        assert base_url == ""
        assert model == ""


class TestGetAllApiConfigs:
    """测试 _get_all_api_configs 函数。"""

    @patch("src.agents.base_agent.LLM_CONFIGS", [])
    def test_empty_configs_returns_empty_list(self):
        """无配置时返回空列表。"""
        from src.agents.base_agent import _get_all_api_configs
        result = _get_all_api_configs()
        assert result == []
