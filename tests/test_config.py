"""测试配置管理"""

import config as root_config
from src.config.config_manager import (
    count_llm_configs,
    get_all_llm_configs,
    remove_llm_config,
    validate_configs,
)


class TestConfigManager:
    """测试配置管理器"""

    def test_count_configs(self):
        """统计配置数量"""
        count = count_llm_configs()
        assert count > 0  # 应该至少有默认配置

    def test_get_all_configs(self):
        """获取所有配置"""
        configs = get_all_llm_configs()
        assert len(configs) > 0
        # 验证配置结构
        assert hasattr(configs[0], "model_name")
        assert hasattr(configs[0], "api_key")
        assert hasattr(configs[0], "base_url")

    def test_validate_configs(self):
        """验证配置"""
        result = validate_configs()
        assert isinstance(result, dict)
        assert "total_configs" in result
        assert "valid_configs" in result

    def test_remove_nonexistent_config(self):
        """移除不存在的配置返回 False"""
        result = remove_llm_config("nonexistent-model-12345")
        assert result is False

    def test_configs_have_required_fields(self):
        """验证配置包含必需字段"""
        configs = get_all_llm_configs()
        if configs:
            config = configs[0]
            assert config.model_name  # 非空
            assert config.api_key  # 非空
            assert config.base_url  # 非空


class TestRootConfigLlmLoading:
    """测试根目录 config.py 的 LLM 配置加载（容忍编号空洞）。"""

    def _fake_getenv(self, env: dict):
        """返回基于固定环境字典的 os.getenv 替身。"""

        def fake_getenv(name, default=""):
            return env.get(name, default)

        return fake_getenv

    def test_gap_tolerant_loading(self, monkeypatch):
        """LLM_2 不完整时 LLM_3 仍应被加载（回归：旧实现在首个空洞处 break）。"""
        env = {
            "LLM_1_API_KEY": "k1",
            "LLM_1_BASE_URL": "https://u1",
            "LLM_1_MODEL_NAME": "m1",
            # LLM_2 缺 model_name（空洞）
            "LLM_2_API_KEY": "k2",
            "LLM_2_BASE_URL": "https://u2",
            "LLM_3_API_KEY": "k3",
            "LLM_3_BASE_URL": "https://u3",
            "LLM_3_MODEL_NAME": "m3",
        }
        monkeypatch.setattr(root_config.os, "getenv", self._fake_getenv(env))
        configs = root_config._load_llm_configs()
        assert [c.model_name for c in configs] == ["m1", "m3"]

    def test_contiguous_loading_unchanged(self, monkeypatch):
        """连续完整配置行为与旧实现一致。"""
        env = {
            "LLM_1_API_KEY": "k1",
            "LLM_1_BASE_URL": "https://u1",
            "LLM_1_MODEL_NAME": "m1",
            "LLM_2_API_KEY": "k2",
            "LLM_2_BASE_URL": "https://u2",
            "LLM_2_MODEL_NAME": "m2",
        }
        monkeypatch.setattr(root_config.os, "getenv", self._fake_getenv(env))
        configs = root_config._load_llm_configs()
        assert [c.model_name for c in configs] == ["m1", "m2"]

    def test_no_configs_returns_empty(self, monkeypatch):
        """无任何 LLM 配置时返回空列表。"""
        monkeypatch.setattr(root_config.os, "getenv", self._fake_getenv({}))
        assert root_config._load_llm_configs() == []
