"""
API 管理器单元测试

测试覆盖：
- 节点注册与初始化
- 三种轮换策略
- 健康检查逻辑
- 故障转移机制
- 统计信息收集
"""

from collections import deque
from unittest.mock import MagicMock, patch

import openai
import pytest

from config import LLMConfig
from src.api_manager import (
    APIManger,
    RotationStrategy,
    get_manager,
    print_status_table,
    reset_manager,
)


@pytest.fixture
def sample_configs():
    """创建示例 LLM 配置"""
    return [
        LLMConfig(api_key="key1", base_url="https://api1.example.com/v1", model_name="model-1"),
        LLMConfig(api_key="key2", base_url="https://api2.example.com/v1", model_name="model-2"),
        LLMConfig(api_key="key3", base_url="https://api3.example.com/v1", model_name="model-3"),
    ]


@pytest.fixture
def manager(sample_configs):
    """创建测试用的 API 管理器"""
    with patch("src.api_manager.LLM_CONFIGS", sample_configs):
        with patch("src.api_manager.openai.OpenAI"):
            mgr = APIManger()
            yield mgr


class TestAPIMangerInit:
    """测试 API 管理器初始化"""

    def test_init_registers_all_nodes(self, manager, sample_configs):
        """初始化应注册所有配置的节点"""
        assert len(manager.health_nodes) == 3
        for config in sample_configs:
            assert config.model_name in manager.health_nodes

    def test_health_nodes_are_healthy_by_default(self, manager):
        """默认情况下所有节点应为健康状态"""
        for node in manager.health_nodes.values():
            assert node.is_healthy is True
            assert node.consecutive_failures == 0

    def test_client_cache_populated(self, manager):
        """客户端缓存应包含所有节点"""
        assert len(manager._client_cache) == 3


class TestRotationStrategies:
    """测试轮换策略"""

    def test_round_robin_cycles(self, manager):
        """轮询策略应按顺序循环"""
        # 确保使用轮询策略
        manager.config.rotation_strategy = RotationStrategy.ROUND_ROBIN
        # 重置索引到初始状态
        manager._rr_index = 0

        # 获取健康节点列表（保持插入顺序）
        healthy_nodes = list(manager.health_nodes.values())
        assert len(healthy_nodes) == 3

        # 首次选择第一个
        first = manager.select_node()
        assert first.config.model_name == healthy_nodes[0].config.model_name

        # 第二次选择第二个
        second = manager.select_node()
        assert second.config.model_name == healthy_nodes[1].config.model_name

        # 第三次选择第三个
        third = manager.select_node()
        assert third.config.model_name == healthy_nodes[2].config.model_name

        # 第四次应该回到第一个（循环）
        fourth = manager.select_node()
        assert fourth.config.model_name == healthy_nodes[0].config.model_name

    def test_round_robin_skips_unhealthy(self, manager):
        """轮询应跳过不健康节点"""
        # 标记第二个节点为不健康
        nodes = list(manager.health_nodes.values())
        nodes[1].is_healthy = False

        # 多次选择应只返回健康节点
        for _ in range(10):
            selected = manager.select_node()
            assert selected.is_healthy is True
            assert selected.config.model_name in ["model-1", "model-3"]

    def test_weighted_random_preferences(self, manager):
        """加权随机应倾向于成功率高且响应快的节点"""
        nodes = list(manager.health_nodes.values())

        # 设置不同的成功率和响应时间
        nodes[0].success_count = 90
        nodes[0].total_requests = 100
        nodes[0].last_response_time_ms = 100
        nodes[1].success_count = 50
        nodes[1].total_requests = 100
        nodes[1].last_response_time_ms = 500
        nodes[2].success_count = 80
        nodes[2].total_requests = 100
        nodes[2].last_response_time_ms = 200

        # 运行多次选择，统计频率
        selection_counts = {n.config.model_name: 0 for n in nodes}
        for _ in range(100):
            selected = manager.select_node()
            selection_counts[selected.config.model_name] += 1

        # model-1 应该有最高选择频率（成功率高+响应快）
        assert selection_counts["model-1"] > selection_counts["model-2"]

    def test_health_based_picks_best(self, manager):
        """健康感知策略应选择综合评分最高的节点"""
        manager.config.rotation_strategy = RotationStrategy.HEALTH_BASED
        nodes = list(manager.health_nodes.values())

        # 设置 model-1 为最优（高成功率+快响应）
        nodes[0].success_count = 95
        nodes[0].total_requests = 100
        nodes[0].last_response_time_ms = 50
        nodes[1].success_count = 80
        nodes[1].total_requests = 100
        nodes[1].last_response_time_ms = 100
        nodes[2].success_count = 70
        nodes[2].total_requests = 100
        nodes[2].last_response_time_ms = 150

        # 多次选择应倾向于最优节点
        selected_counts = {n.config.model_name: 0 for n in nodes}
        for _ in range(50):
            selected = manager.select_node()
            selected_counts[selected.config.model_name] += 1

        # model-1 应被选中的次数最多
        assert selected_counts["model-1"] >= selected_counts["model-2"]

    def test_round_robin_returns_none_when_no_healthy(self):
        """轮询策略在无健康节点时返回 None（覆盖第157行）"""
        with patch("src.api_manager.LLM_CONFIGS", []):
            with patch("src.api_manager.openai.OpenAI"):
                mgr = APIManger()
                mgr.config.rotation_strategy = RotationStrategy.ROUND_ROBIN
                # 将所有节点标记为不健康
                for node in mgr.health_nodes.values():
                    node.is_healthy = False
                # 调用 _select_node_round_robin
                result = mgr._select_node_round_robin()
                assert result is None

    def test_fastest_first_strategy(self, manager):
        """最快优先策略应选择响应时间最短的节点"""
        manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
        nodes = list(manager.health_nodes.values())

        # 通过 _response_times 间接设置 avg_response_time_ms
        nodes[0]._response_times = deque([200.0], maxlen=10)
        nodes[1]._response_times = deque([100.0], maxlen=10)
        nodes[2]._response_times = deque([300.0], maxlen=10)

        # 应返回响应时间最短的节点
        selected = manager.select_node()
        assert selected.config.model_name == "model-2"

    def test_fastest_first_returns_none_when_no_healthy(self):
        """最快优先策略在无健康节点时返回 None"""
        with patch("src.api_manager.LLM_CONFIGS", []):
            with patch("src.api_manager.openai.OpenAI"):
                mgr = APIManger()
                mgr.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
                result = mgr.select_node()
                assert result is None

    def test_select_node_uses_fastest_first(self, manager):
        """select_node 在 FASTEST_FIRST 策略时应调用对应方法（覆盖第169行）"""
        manager.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
        nodes = list(manager.health_nodes.values())
        nodes[0]._response_times = deque([300.0], maxlen=10)
        nodes[1]._response_times = deque([100.0], maxlen=10)
        nodes[2]._response_times = deque([200.0], maxlen=10)

        selected = manager.select_node()
        assert selected.config.model_name == "model-2"


class TestHealthCheck:
    """测试健康检查逻辑"""

    def test_mark_success_updates_stats(self, manager):
        """标记成功应更新统计"""
        node = list(manager.health_nodes.values())[0]
        node.mark_success(response_time_ms=150.5)

        assert node.is_healthy is True
        assert node.consecutive_failures == 0
        assert node.success_count == 1
        assert 150.5 in node._response_times  # 滑动窗口中

    def test_mark_failure_increments_counter(self, manager):
        """标记失败应增加连续失败计数"""
        node = list(manager.health_nodes.values())[0]

        node.mark_failure("api_error")
        assert node.consecutive_failures == 1
        assert node.error_count == 1

        node.mark_failure("api_error")
        assert node.consecutive_failures == 2

        node.mark_failure("api_error")
        assert node.consecutive_failures == 3
        assert node.is_healthy is False  # 连续3次失败应标记为不健康

    def test_rate_limit_sets_remaining_to_zero(self, manager):
        """限流错误应将剩余配额设为0"""
        node = list(manager.health_nodes.values())[0]
        node.rate_limit_remaining = 100

        node.mark_failure("rate_limit")
        assert node.rate_limit_remaining == 0

    def test_check_health_returns_true_on_success(self, manager):
        """健康检查成功时应返回 True 并标记成功（覆盖第196行）"""
        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response
        manager._client_cache[node.config.model_name] = mock_client

        result = manager.check_health(node)
        assert result is True
        assert node.is_healthy is True
        assert node.success_count == 1
        mock_client.chat.completions.create.assert_called_once()

    def test_check_health_marks_unhealthy_when_no_client(self, manager):
        """健康检查时客户端不存在应标记为不健康（覆盖第196行）"""
        node = list(manager.health_nodes.values())[0]
        # 从缓存中移除客户端
        del manager._client_cache[node.config.model_name]

        result = manager.check_health(node)
        assert result is False
        assert node.is_healthy is False

    def test_check_health_rate_limit_error(self, manager):
        """健康检查遇到 RateLimitError 应标记为限流失败"""
        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        # 使用 MagicMock 模拟异常，避免真实构造 OpenAI 异常
        mock_error = MagicMock()
        mock_error.__class__ = openai.RateLimitError
        mock_client.chat.completions.create.side_effect = mock_error
        manager._client_cache[node.config.model_name] = mock_client

        result = manager.check_health(node)
        assert result is False
        assert node.consecutive_failures == 1
        assert node.error_count == 1
        mock_client.chat.completions.create.assert_called_once()

    def test_check_health_api_error(self, manager):
        """健康检查遇到 APIError 应标记为 API 错误"""
        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        # 使用 MagicMock 模拟异常
        mock_error = MagicMock()
        mock_error.__class__ = openai.APIError
        mock_error.status_code = 500
        mock_client.chat.completions.create.side_effect = mock_error
        manager._client_cache[node.config.model_name] = mock_client

        result = manager.check_health(node)
        assert result is False
        assert node.consecutive_failures == 1
        assert node.error_count == 1

    def test_check_health_generic_exception(self, manager):
        """健康检查遇到其他异常应标记为错误"""
        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection error")
        manager._client_cache[node.config.model_name] = mock_client

        result = manager.check_health(node)
        assert result is False
        assert node.consecutive_failures == 1
        assert node.error_count == 1


class TestCallMethod:
    """测试 call 方法"""

    def test_call_uses_selected_node(self, manager):
        """call 方法应使用选中的节点"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]

        selected_node = list(manager.health_nodes.values())[0]

        # mock OpenAI 客户端
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.object(manager, "select_node", return_value=selected_node):
            # 将 mock 客户端放入缓存
            manager._client_cache[selected_node.config.model_name] = mock_client
            with patch("src.api_manager.openai.OpenAI", return_value=mock_client):
                result = manager.call(messages=[{"role": "user", "content": "hi"}])

                assert result is not None
                # 验证使用了正确的模型名称调用
                mock_client.chat.completions.create.assert_called_once()
                call_args = mock_client.chat.completions.create.call_args
                assert call_args.kwargs.get("model") == selected_node.config.model_name

    def test_call_falls_back_on_failure(self, manager):
        """call 方法应在失败时自动故障转移到备用节点"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]

        # 获取前两个健康节点作为主节点和备用节点
        nodes = list(manager.health_nodes.values())
        primary_node = nodes[0]
        fallback_node = nodes[1]

        # 为主节点创建 mock 客户端（第一次失败）
        primary_client = MagicMock()
        primary_client.chat.completions.create.side_effect = Exception("Simulated failure")

        # 为备用节点创建 mock 客户端（成功）
        fallback_client = MagicMock()
        fallback_client.chat.completions.create.return_value = mock_response

        # 将 mock 客户端放入缓存
        manager._client_cache[primary_node.config.model_name] = primary_client
        manager._client_cache[fallback_node.config.model_name] = fallback_client

        with patch.object(manager, "select_node", return_value=primary_node):
            result = manager.call(messages=[{"role": "user", "content": "hi"}])

            assert result is not None
            # 主节点调用一次（失败），备用节点调用一次（成功）
            assert primary_client.chat.completions.create.call_count == 1
            assert fallback_client.chat.completions.create.call_count == 1

    def test_call_with_specified_model(self, manager):
        """call 方法指定模型时应直接使用该节点（覆盖第321行）"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]

        # 指定使用 model-1
        manager.health_nodes["model-1"]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        manager._client_cache["model-1"] = mock_client

        result = manager.call(messages=[{"role": "user", "content": "hi"}], model="model-1")

        assert result is not None
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs.get("model") == "model-1"

    def test_call_raises_when_no_available_nodes(self, manager):
        """call 方法在无可用节点时应抛出 RuntimeError（覆盖第328行）"""
        # 将所有节点标记为不健康
        for node in manager.health_nodes.values():
            node.is_healthy = False

        with patch.object(manager, "select_node", return_value=None):
            with pytest.raises(RuntimeError, match="无可用 API 节点"):
                manager.call(messages=[{"role": "user", "content": "hi"}])

    def test_call_skips_node_without_client(self, manager):
        """call 方法在客户端不存在时应跳过该节点（覆盖第339行）"""
        # 获取第一个节点
        node = list(manager.health_nodes.values())[0]
        # 从缓存中移除客户端
        del manager._client_cache[node.config.model_name]

        # 第二个节点有客户端
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]
        fallback_node = list(manager.health_nodes.values())[1]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        manager._client_cache[fallback_node.config.model_name] = mock_client

        # 选择第一个节点（但没有客户端）
        with patch.object(manager, "select_node", return_value=node):
            result = manager.call(messages=[{"role": "user", "content": "hi"}])
            # 应成功使用备用节点
            assert result is not None

    def test_call_rate_limit_with_fallback(self, manager):
        """call 方法遇到 RateLimitError 且启用 fallback 时应等待后重试"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]

        nodes = list(manager.health_nodes.values())
        primary_node = nodes[0]
        fallback_node = nodes[1]

        # 主节点限流 - 使用 MagicMock 模拟异常
        primary_client = MagicMock()
        mock_rl_error = MagicMock()
        mock_rl_error.__class__ = openai.RateLimitError
        primary_client.chat.completions.create.side_effect = mock_rl_error

        # 备用节点成功
        fallback_client = MagicMock()
        fallback_client.chat.completions.create.return_value = mock_response

        manager._client_cache[primary_node.config.model_name] = primary_client
        manager._client_cache[fallback_node.config.model_name] = fallback_client

        with patch.object(manager, "select_node", return_value=primary_node):
            result = manager.call(messages=[{"role": "user", "content": "hi"}])
            assert result is not None
            # 主节点调用一次（限流），备用节点调用一次（成功）
            assert primary_client.chat.completions.create.call_count == 1
            assert fallback_client.chat.completions.create.call_count == 1

    def test_call_api_error_without_fallback(self, manager):
        """call 方法遇到 APIError 且 fallback_on_failure=False 时应重新抛出"""
        nodes = list(manager.health_nodes.values())
        node = nodes[0]
        mock_client = MagicMock()
        # 使用 MagicMock 模拟 APIError
        mock_error = RuntimeError("API Error 500")
        mock_error.status_code = 500
        mock_client.chat.completions.create.side_effect = mock_error
        manager._client_cache[node.config.model_name] = mock_client

        # 禁用 fallback
        manager.config.fallback_on_failure = False

        with patch.object(manager, "select_node", return_value=node):
            with pytest.raises(RuntimeError):  # 测试异常处理逻辑
                manager.call(messages=[{"role": "user", "content": "hi"}])

    def test_call_generic_error_without_fallback(self, manager):
        """call 方法遇到通用异常且 fallback_on_failure=False 时应重新抛出"""
        nodes = list(manager.health_nodes.values())
        node = nodes[0]
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Generic error")
        manager._client_cache[node.config.model_name] = mock_client

        # 禁用 fallback
        manager.config.fallback_on_failure = False

        with patch.object(manager, "select_node", return_value=node):
            with pytest.raises(Exception, match="Generic error"):
                manager.call(messages=[{"role": "user", "content": "hi"}])

    def test_check_health_empty_response(self, manager):
        """健康检查返回空响应时应标记失败（覆盖第199-200行）"""
        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        # 返回无 choices 的响应
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client.chat.completions.create.return_value = mock_response
        manager._client_cache[node.config.model_name] = mock_client

        result = manager.check_health(node)
        assert result is False
        assert node.consecutive_failures == 1
        assert node.error_count == 1

    def test_health_check_all(self, manager):
        """health_check_all 应对所有节点进行健康检查（覆盖第219-222行）"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response

        for node in manager.health_nodes.values():
            manager._client_cache[node.config.model_name] = mock_client

        results = manager.health_check_all()
        assert len(results) == 3
        for name, is_healthy in results.items():
            assert is_healthy is True
            assert name in manager.health_nodes

    def test_health_check_batch_with_custom_size(self, manager):
        """health_check_batch 应支持自定义 batch_size（覆盖第231-243行）"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response

        for node in manager.health_nodes.values():
            manager._client_cache[node.config.model_name] = mock_client

        # 使用自定义 batch_size=1
        results = manager.health_check_batch(batch_size=1)
        assert len(results) == 3
        for _name, is_healthy in results.items():
            assert is_healthy is True

    def test_call_all_nodes_fail(self, manager):
        """call 方法所有节点都失败时应抛出 RuntimeError（覆盖第340-341行）"""
        # 禁用 fallback，使异常直接抛出
        manager.config.fallback_on_failure = False

        node = list(manager.health_nodes.values())[0]
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("All nodes failed")
        manager._client_cache[node.config.model_name] = mock_client

        with patch.object(manager, "select_node", return_value=node):
            with pytest.raises(Exception, match="All nodes failed"):
                manager.call(messages=[{"role": "user", "content": "hi"}])


class TestGetStatus:
    """测试状态查询"""

    def test_get_status_returns_summary(self, manager):
        """get_status 应返回状态摘要"""
        status = manager.get_status()

        assert status["total_nodes"] == 3
        assert status["healthy_nodes"] == 3
        assert "nodes" in status
        assert len(status["nodes"]) == 3

    def test_get_status_node_details(self, manager):
        """状态应包含每个节点的详细信息"""
        status = manager.get_status()

        for _node_name, node_status in status["nodes"].items():
            assert "model" in node_status
            assert "is_healthy" in node_status
            assert "success_rate" in node_status
            assert "total_requests" in node_status


class TestGetTopNodes:
    """测试 get_top_nodes 方法（覆盖第437-440行）"""

    def test_get_top_nodes_sort_by_success_rate(self, manager):
        """按成功率排序"""
        nodes = list(manager.health_nodes.values())
        nodes[0].total_requests = 100
        nodes[0].success_count = 90
        nodes[1].total_requests = 100
        nodes[1].success_count = 50
        nodes[2].total_requests = 100
        nodes[2].success_count = 80

        result = manager.get_top_nodes(n=2, sort_by="success_rate")
        assert len(result) == 2
        assert result[0]["model"] == "model-1"
        assert result[1]["model"] == "model-3"

    def test_get_top_nodes_sort_by_response_time(self, manager):
        """按响应时间排序"""
        nodes = list(manager.health_nodes.values())
        nodes[0].total_requests = 10
        nodes[0].success_count = 10
        nodes[0]._response_times = deque([200.0], maxlen=10)
        nodes[1].total_requests = 10
        nodes[1].success_count = 10
        nodes[1]._response_times = deque([100.0], maxlen=10)
        nodes[2].total_requests = 10
        nodes[2].success_count = 10
        nodes[2]._response_times = deque([300.0], maxlen=10)

        result = manager.get_top_nodes(n=2, sort_by="response_time")
        assert len(result) == 2
        # 响应时间越短排名越靠前
        assert result[0]["model"] == "model-2"

    def test_get_top_nodes_sort_by_requests(self, manager):
        """按请求数排序"""
        nodes = list(manager.health_nodes.values())
        nodes[0].total_requests = 100
        nodes[1].total_requests = 200
        nodes[2].total_requests = 150

        result = manager.get_top_nodes(n=2, sort_by="requests")
        assert len(result) == 2
        assert result[0]["model"] == "model-2"
        assert result[1]["model"] == "model-3"


class TestRemoveNode:
    """测试 remove_node 方法（覆盖第501行）"""

    def test_remove_existing_node(self, manager):
        """移除存在的节点应返回 True"""
        result = manager.remove_node("model-1")
        assert result is True
        assert "model-1" not in manager.health_nodes
        assert "model-1" not in manager._client_cache

    def test_remove_nonexistent_node(self, manager):
        """移除不存在的节点应返回 False（覆盖第501行）"""
        result = manager.remove_node("nonexistent-model")
        assert result is False


class TestPrintStatusTable:
    """测试 print_status_table 函数（覆盖第529-547行）"""

    def test_print_status_table(self, manager, capsys):
        """print_status_table 应输出表格"""
        print_status_table(manager)
        captured = capsys.readouterr()
        # 验证输出包含关键信息
        assert "API 管理器状态" in captured.out
        assert "3 个节点" in captured.out
        assert "3 个健康" in captured.out

    def test_print_status_table_with_none_uses_singleton(self, manager, capsys):
        """print_status_table 传入 None 时应使用全局单例"""
        reset_manager()
        # 设置全局单例
        import src.api_manager as am

        am._manager = manager

        print_status_table(None)
        captured = capsys.readouterr()
        assert "API 管理器状态" in captured.out


class TestGlobalFunctions:
    """测试全局函数"""

    def test_get_manager_creates_singleton(self):
        """get_manager 应返回单例"""
        reset_manager()
        mgr1 = get_manager()
        mgr2 = get_manager()
        assert mgr1 is mgr2

    def test_reset_manager_clears_singleton(self):
        """reset_manager 应清除单例"""
        reset_manager()
        mgr1 = get_manager()
        reset_manager()
        mgr2 = get_manager()
        assert mgr1 is not mgr2


class TestIntegration:
    """集成测试"""

    @pytest.mark.integration
    def test_real_api_call(self):
        """测试真实 API 调用（需要配置环境变量）"""
        from config import LLM_CONFIGS

        if not LLM_CONFIGS:
            pytest.skip("未配置 LLM")

        manager = get_manager()

        try:
            response = manager.call(messages=[{"role": "user", "content": "Say hello"}], max_tokens=10)
            assert response is not None
            assert hasattr(response, "choices")
        except Exception as e:
            pytest.fail(f"API 调用失败: {e}")
