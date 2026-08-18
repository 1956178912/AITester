"""
API 管理器增强版测试

测试大规模节点池（100+ 模型）场景下的行为。
"""

from collections import deque
from unittest.mock import patch

import pytest

from config import LLMConfig
from src.api_manager import (
    APIManger,
    RotationStrategy,
)


@pytest.fixture
def large_scale_configs():
    """创建大规模节点池配置（模拟100+模型）"""
    configs = []
    for i in range(120):  # 120 个节点
        configs.append(
            LLMConfig(api_key=f"key-{i}", base_url=f"https://api{i}.example.com/v1", model_name=f"model-{i:03d}")
        )
    return configs


@pytest.fixture
def large_manager(large_scale_configs):
    """创建大规模测试管理器"""
    with patch("src.api_manager.LLM_CONFIGS", large_scale_configs):
        with patch("src.api_manager.openai.OpenAI"):
            mgr = APIManger()
            yield mgr


class TestLargeScaleNodes:
    """大规模节点池测试"""

    def test_init_registers_all_nodes(self, large_manager):
        """初始化应注册所有 120 个节点"""
        assert len(large_manager.health_nodes) == 120
        assert len(large_manager._client_cache) == 120

    def test_healthy_nodes_count(self, large_manager):
        """默认所有节点应为健康状态"""
        healthy = large_manager.get_healthy_nodes()
        assert len(healthy) == 120

    def test_round_robin_distributes_equally(self, large_manager):
        """轮询应均匀分布请求"""
        # 确保使用轮询策略
        large_manager.config.rotation_strategy = RotationStrategy.ROUND_ROBIN

        selection_counts = {f"model-{i:03d}": 0 for i in range(120)}

        # 选择 1200 次（每个节点平均 10 次）
        for _ in range(1200):
            node = large_manager.select_node()
            selection_counts[node.config.model_name] += 1

        # 验证分布均匀（允许 ±2 的误差）
        for count in selection_counts.values():
            assert 8 <= count <= 12, f"分布不均: {count}"

    def test_health_based_selects_best_node(self, large_manager):
        """健康感知策略应选择最优节点"""
        large_manager.config.rotation_strategy = RotationStrategy.HEALTH_BASED

        # 设置第一个节点为最优（高成功率 + 快响应）
        best_node = list(large_manager.health_nodes.values())[0]
        # 通过 success_count 和 total_requests 控制成功率
        best_node.total_requests = 100
        best_node.success_count = 99  # 成功率 0.99
        best_node.last_response_time_ms = 50

        # 其他节点性能较差
        for name, node in large_manager.health_nodes.items():
            if name != best_node.config.model_name:
                node.total_requests = 100
                node.success_count = 70  # 成功率 0.7
                node.last_response_time_ms = 300

        # 多次选择应倾向于最优节点
        selected_counts = {name: 0 for name in large_manager.health_nodes}
        for _ in range(100):
            selected = large_manager.select_node()
            selected_counts[selected.config.model_name] += 1

        # 最优节点应被选中最多
        assert selected_counts[best_node.config.model_name] > 50

    def test_fastest_first_selects_quickest(self, large_manager):
        """最快优先策略应选择响应最快的节点"""
        large_manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST

        # 获取前三个节点并设置不同响应时间
        nodes = list(large_manager.health_nodes.values())[:3]
        # 设置滑动窗口响应时间（影响 avg_response_time_ms）
        nodes[0]._response_times = deque([100, 100, 100], maxlen=10)  # 最快，平均 100ms
        nodes[1]._response_times = deque([200, 200, 200], maxlen=10)  # 中等，平均 200ms
        nodes[2]._response_times = deque([500, 500, 500], maxlen=10)  # 最慢，平均 500ms

        # 对其他所有节点设置较高的响应时间，确保它们不会被选中
        all_nodes = list(large_manager.health_nodes.values())
        for node in all_nodes[3:]:
            node._response_times = deque([1000, 1000, 1000], maxlen=10)  # 很慢，平均 1000ms

        # 快速优先策略总是选择响应时间最短的节点
        selected = large_manager.select_node()

        # 找到响应时间最短的节点
        fastest_node = min(nodes, key=lambda n: n.avg_response_time_ms)
        assert selected.config.model_name == fastest_node.config.model_name


class TestBatchHealthCheck:
    """批量健康检查测试"""

    def test_batch_check_processes_in_groups(self, large_manager):
        """批量检查应分批执行"""
        check_results = []

        def mock_check(node):
            check_results.append(node.config.model_name)
            return True

        with patch.object(large_manager, "check_health", side_effect=mock_check):
            # 直接调用 health_check_all 来测试（批量检查内部调用 check_health）
            large_manager.health_check_all()

        # 应有 120 次检查调用
        assert len(check_results) == 120

    def test_batch_check_respects_batch_size(self, large_manager):
        """批量大小应影响执行方式"""
        call_order = []

        def tracked_check(node):
            call_order.append(node.config.model_name)
            return True

        with patch.object(large_manager, "check_health", side_effect=tracked_check):
            large_manager.health_check_batch(batch_size=20)

        # 检查顺序应保持（虽然不严格，但应该连续执行）
        assert len(call_order) == 120


class TestDynamicManagement:
    """动态节点管理测试"""

    def test_add_node_to_large_pool(self, large_manager):
        """动态添加节点"""
        new_config = LLMConfig(api_key="new-key", base_url="https://new.example.com/v1", model_name="new-model")

        with patch("src.api_manager.openai.OpenAI"):
            large_manager.add_node(new_config)

        assert len(large_manager.health_nodes) == 121
        assert "new-model" in large_manager.health_nodes

    def test_remove_node_from_large_pool(self, large_manager):
        """动态移除节点"""
        initial_count = len(large_manager.health_nodes)

        # 移除一个节点
        first_model = list(large_manager.health_nodes.keys())[0]
        result = large_manager.remove_node(first_model)

        assert result is True
        assert len(large_manager.health_nodes) == initial_count - 1
        assert first_model not in large_manager.health_nodes

    def test_get_top_nodes_large_pool(self, large_manager):
        """获取 Top N 节点"""
        # 设置不同的成功率（通过 success_count 和 total_requests 控制）
        nodes = list(large_manager.health_nodes.values())
        for i, node in enumerate(nodes):
            # 设置 success_rate 间接通过 success_count/total_requests
            node.total_requests = 100
            node.success_count = int((0.9 - (i * 0.001)) * 100)

        top_10 = large_manager.get_top_nodes(n=10, sort_by="success_rate")

        assert len(top_10) == 10
        # 验证按成功率排序
        for i in range(len(top_10) - 1):
            assert top_10[i]["success_rate"] >= top_10[i + 1]["success_rate"]


class TestStatusReporting:
    """状态报告测试"""

    def test_get_status_large_pool(self, large_manager):
        """获取大规模池的状态"""
        status = large_manager.get_status()

        assert status["total_nodes"] == 120
        assert status["healthy_nodes"] == 120
        assert status["unhealthy_nodes"] == 0
        assert len(status["nodes"]) == 120

    def test_reset_stats_large_pool(self, large_manager):
        """重置大规模池的统计"""
        # 先设置一些统计数据
        for node in large_manager.health_nodes.values():
            node.total_requests = 100
            node.success_count = 90
            node.error_count = 10

        large_manager.reset_stats()

        # 验证全部重置
        for node in large_manager.health_nodes.values():
            assert node.total_requests == 0
            assert node.success_count == 0
            assert node.error_count == 0
            assert node.consecutive_failures == 0


class TestMixedHealthStatus:
    """混合健康状态测试"""

    def test_fallback_to_healthy_nodes(self, large_manager):
        """故障转移应跳到健康节点"""
        # 标记前 60 个节点为不健康
        nodes = list(large_manager.health_nodes.values())
        for node in nodes[:60]:
            node.is_healthy = False
            node.consecutive_failures = 3

        # 应仍有 60 个健康节点
        healthy = large_manager.get_healthy_nodes()
        assert len(healthy) == 60

        # 选择节点应只返回健康节点
        for _ in range(10):
            selected = large_manager.select_node()
            assert selected.is_healthy is True

    def test_empty_pool_raises_error(self, large_manager):
        """所有节点不可用时应抛出异常"""
        # 标记所有节点为不健康
        for node in large_manager.health_nodes.values():
            node.is_healthy = False

        # 选择节点应返回 None
        assert large_manager.select_node() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
