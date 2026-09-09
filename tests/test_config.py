"""测试配置管理"""

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
