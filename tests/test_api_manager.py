"""测试 API Manager 核心功能"""
from src.api_manager import (
    APIManger,
    LLMConfig,
    get_manager,
    reset_manager,
)


class TestLLMConfig:
    """测试 LLM 配置数据类"""

    def test_create_llm_config(self):
        """创建 LLM 配置"""
        config = LLMConfig(
            api_key="test-key",
            base_url="https://api.example.com",
            model_name="test-model",
        )
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.example.com"
        assert config.model_name == "test-model"

    def test_llm_config_equality(self):
        """配置对象相等性"""
        c1 = LLMConfig("key1", "url1", "model1")
        c2 = LLMConfig("key1", "url1", "model1")
        assert c1 == c2


class TestAPIManger:
    """测试 API Manager"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()

    def test_get_default_manager(self):
        """获取默认管理器"""
        mgr = get_manager()
        assert mgr is not None
        assert isinstance(mgr, APIManger)

    def test_add_node_with_config(self):
        """添加节点（使用 LLMConfig）"""
        mgr = get_manager()
        config = LLMConfig("key1", "url1", "model1")
        mgr.add_node(config)
        nodes = mgr.get_all_nodes()
        assert len(nodes) >= 1

    def test_get_status(self):
        """获取状态"""
        mgr = get_manager()
        status = mgr.get_status()
        assert isinstance(status, dict)

    def test_reset_stats(self):
        """重置统计"""
        mgr = get_manager()
        mgr.reset_stats()
        # 不抛出异常即为成功
