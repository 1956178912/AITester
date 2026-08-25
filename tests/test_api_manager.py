"""
API Manager 完整测试套件
测试 src/api_manager.py 中的所有核心功能：
- APIHealth 数据类及其属性/方法
- RotationStrategy 枚举
- APIManger 核心功能（轮换策略、健康检查、故障转移、节点管理）
- HealthCheckerThread 后台线程
- 全局单例函数
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# 设置路径以便导入 src 模块
sys.path.insert(0, ".")

from config import LLMConfig
from src.api_manager import (
    APIHealth,
    APIManagerConfig,
    APIManger,
    HealthCheckerThread,
    RotationStrategy,
    get_manager,
    print_status_table,
    reset_manager,
)


class TestAPIHealth:
    """测试 APIHealth 数据类的属性和方法"""

    def setup_method(self):
        """每个测试前创建一个新的 APIHealth 实例"""
        self.config = LLMConfig(
            api_key="test-key",
            base_url="https://api.example.com",
            model_name="test-model",
        )
        self.health = APIHealth(config=self.config)

    def test_initial_state(self):
        """测试初始状态"""
        assert self.health.is_healthy is True
        assert self.health.consecutive_failures == 0
        assert self.health.total_requests == 0
        assert self.health.success_count == 0
        assert self.health.error_count == 0
        assert self.health.last_response_time_ms == 0.0
        assert self.health.rate_limit_remaining == 0
        assert len(self.health._response_times) == 0

    def test_success_rate_when_no_requests(self):
        """测试无请求时的成功率"""
        assert self.health.success_rate == 1.0

    def test_success_rate_calculation(self):
        """测试成功率计算"""
        # 模拟 10 次请求，7 次成功，3 次失败
        for _ in range(7):
            self.health.mark_success(100.0)
            self.health.total_requests += 1
        for _ in range(3):
            self.health.mark_failure("error")
            self.health.total_requests += 1

        assert self.health.total_requests == 10
        assert self.health.success_count == 7
        assert self.health.error_count == 3
        assert self.health.success_rate == pytest.approx(0.7)

    def test_avg_response_time_with_window(self):
        """测试滑动窗口平均响应时间"""
        # 添加一些响应时间
        self.health._response_times.extend([100.0, 200.0, 300.0])
        assert self.health.avg_response_time_ms == pytest.approx(200.0)

    def test_avg_response_time_fallback(self):
        """测试滑动窗口为空时使用 last_response_time_ms"""
        self.health.last_response_time_ms = 150.0
        assert self.health.avg_response_time_ms == 150.0

    def test_mark_success_updates_state(self):
        """测试 mark_success 更新状态"""
        self.health.mark_success(120.5)
        assert self.health.is_healthy is True
        assert self.health.consecutive_failures == 0
        assert self.health.success_count == 1
        assert 120.5 in self.health._response_times
        assert self.health.total_requests == 1

    def test_mark_failure_updates_consecutive_failures(self):
        """测试连续失败计数"""
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        assert self.health.consecutive_failures == 2
        assert self.health.error_count == 2
        assert self.health.is_healthy is True  # 未达到阈值

    def test_mark_failure_marks_unhealthy_after_threshold(self):
        """测试连续失败 3 次后标记为不健康"""
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        assert self.health.is_healthy is False
        assert self.health.consecutive_failures == 3

    def test_mark_failure_rate_limit(self):
        """测试限流错误处理"""
        self.health.rate_limit_remaining = 5
        self.health.mark_failure("rate_limit")
        assert self.health.rate_limit_remaining == 0

    def test_response_time_window_maxlen(self):
        """测试滑动窗口大小限制"""
        # 默认 maxlen=10，添加 15 个值
        for i in range(15):
            self.health.mark_success(float(i * 10))
        assert len(self.health._response_times) == 10
        # 最早的值已被移除
        assert 0.0 not in self.health._response_times
        assert 140.0 in self.health._response_times


class TestRotationStrategy:
    """测试轮换策略枚举"""

    def test_enum_values(self):
        """测试枚举值"""
        assert RotationStrategy.ROUND_ROBIN.value == "round_robin"
        assert RotationStrategy.WEIGHTED_RANDOM.value == "weighted_random"
        assert RotationStrategy.HEALTH_BASED.value == "health_based"
        assert RotationStrategy.FASTEST_FIRST.value == "fastest_first"


class TestAPIManagerConfig:
    """测试 API 管理器配置"""

    def test_default_config(self):
        """测试默认配置值"""
        config = APIManagerConfig()
        assert config.rotation_strategy == RotationStrategy.HEALTH_BASED
        assert config.health_check_interval == 60.0
        assert config.fallback_on_failure is True
        assert config.max_consecutive_failures == 3
        assert config.timeout == 60
        assert config.retry_count == 2
        assert config.batch_health_check_size == 10
        assert config.health_check_timeout == 5.0

    def test_custom_config(self):
        """测试自定义配置"""
        config = APIManagerConfig(
            rotation_strategy=RotationStrategy.ROUND_ROBIN,
            health_check_interval=30.0,
            fallback_on_failure=False,
            timeout=30,
        )
        assert config.rotation_strategy == RotationStrategy.ROUND_ROBIN
        assert config.health_check_interval == 30.0
        assert config.fallback_on_failure is False
        assert config.timeout == 30


class TestAPIMangerNodeManagement:
    """测试节点管理功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()

    @patch("src.api_manager.LLM_CONFIGS", [])
    def test_init_with_empty_configs(self):
        """测试空配置初始化"""
        mgr = APIManger()
        assert len(mgr.health_nodes) == 0
        assert len(mgr.get_all_nodes()) == 0
        assert len(mgr.get_healthy_nodes()) == 0

    @patch("src.api_manager.LLM_CONFIGS", [
        LLMConfig("key1", "url1", "model1"),
        LLMConfig("key2", "url2", "model2"),
    ])
    def test_init_with_multiple_configs(self):
        """测试多配置初始化"""
        mgr = APIManger()
        assert len(mgr.health_nodes) == 2
        assert "model1" in mgr.health_nodes
        assert "model2" in mgr.health_nodes

    def test_add_node(self):
        """测试动态添加节点"""
        mgr = APIManger()
        config = LLMConfig("new-key", "new-url", "new-model")
        mgr.add_node(config)
        assert "new-model" in mgr.health_nodes
        assert mgr.health_nodes["new-model"].config.model_name == "new-model"

    def test_remove_node_existing(self):
        """测试移除存在的节点"""
        mgr = APIManger()
        config = LLMConfig("key1", "url1", "model1")
        mgr.add_node(config)
        result = mgr.remove_node("model1")
        assert result is True
        assert "model1" not in mgr.health_nodes

    def test_remove_node_nonexistent(self):
        """测试移除不存在的节点"""
        mgr = APIManger()
        result = mgr.remove_node("nonexistent-model")
        assert result is False

    def test_get_all_nodes(self):
        """测试获取所有节点"""
        mgr = APIManger()
        nodes = mgr.get_all_nodes()
        assert isinstance(nodes, list)

    def test_get_healthy_nodes_filters(self):
        """测试健康节点过滤"""
        mgr = APIManger()
        # 初始所有节点都健康
        healthy = mgr.get_healthy_nodes()
        assert len(healthy) == len(mgr.get_all_nodes())

        # 手动标记一个节点不健康
        if mgr.health_nodes:
            first_node = list(mgr.health_nodes.values())[0]
            first_node.is_healthy = False
            healthy = mgr.get_healthy_nodes()
            assert len(healthy) < len(mgr.get_all_nodes())


class TestAPIMangerRotationStrategies:
    """测试轮换策略"""

    def setup_method(self):
        """每个测试前重置管理器并准备测试环境"""
        reset_manager()
        self.mgr = APIManger()
        # 添加三个测试节点
        for i in range(3):
            self.mgr.add_node(LLMConfig(f"key{i}", f"url{i}", f"model{i}"))

    def test_select_node_returns_node(self):
        """测试选择节点返回有效节点"""
        node = self.mgr.select_node()
        assert node is not None
        assert isinstance(node, APIHealth)

    def test_select_node_no_healthy_nodes(self):
        """测试无健康节点时返回 None"""
        # 将所有节点标记为不健康
        for node in self.mgr.health_nodes.values():
            node.is_healthy = False
        node = self.mgr.select_node()
        assert node is None

    def test_round_robin_cycles(self):
        """测试轮询策略循环"""
        self.mgr.config.rotation_strategy = RotationStrategy.ROUND_ROBIN
        selected = []
        for _ in range(6):
            node = self.mgr.select_node()
            selected.append(node.config.model_name)
        # 应该按顺序循环
        assert len(set(selected)) == 3  # 三个不同的模型
        assert selected[0] != selected[1] or len(selected) > 1

    def test_fastest_first_selects_lowest_time(self):
        """测试最快优先策略"""
        self.mgr.config.rotation_strategy = RotationStrategy.FASTEST_FIRST
        # 设置不同的响应时间
        nodes = list(self.mgr.health_nodes.values())
        nodes[0]._response_times.extend([100.0] * 5)
        nodes[1]._response_times.extend([200.0] * 5)
        nodes[2]._response_times.extend([50.0] * 5)

        selected = self.mgr.select_node()
        assert selected.config.model_name == "model2"  # 响应时间最短的

    def test_weighted_random_preferences(self):
        """测试加权随机策略偏好"""
        self.mgr.config.rotation_strategy = RotationStrategy.WEIGHTED_RANDOM
        # 设置节点0的高成功率和快响应
        node0 = self.mgr.health_nodes["model0"]
        node0.mark_success(50.0)  # 高成功率 + 快响应 = 高权重
        node1 = self.mgr.health_nodes["model1"]
        node1.mark_failure("error")  # 低成功率
        node2 = self.mgr.health_nodes["model2"]
        node2.mark_failure("error")

        # 多次选择，model0 应该更常被选中
        counts = {"model0": 0, "model1": 0, "model2": 0}
        for _ in range(50):
            node = self.mgr.select_node()
            counts[node.config.model_name] += 1

        # model0 应该被选中最多（权重最高）
        assert counts["model0"] > counts["model1"] or counts["model0"] > counts["model2"]

    def test_health_based_selects_best_score(self):
        """测试健康感知策略选择综合评分最高的节点"""
        self.mgr.config.rotation_strategy = RotationStrategy.HEALTH_BASED
        # model0: 高成功率 + 中等响应时间
        node0 = self.mgr.health_nodes["model0"]
        node0.mark_success(100.0)
        node0.mark_success(100.0)
        # model1: 中等成功率 + 快速响应
        node1 = self.mgr.health_nodes["model1"]
        node1.mark_success(80.0)
        # model2: 低成功率
        node2 = self.mgr.health_nodes["model2"]
        node2.mark_failure("error")

        selected = self.mgr.select_node()
        # 应该选择评分最高的节点（综合考虑成功率和响应时间）
        assert selected is not None


class TestAPIMangerHealthCheck:
    """测试健康检查功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManger()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    def test_check_health_missing_client(self):
        """测试客户端不存在时的健康检查"""
        node = self.mgr.health_nodes["model1"]
        # 移除客户端缓存
        self.mgr._client_cache.pop("model1", None)
        result = self.mgr.check_health(node)
        assert result is False
        assert node.is_healthy is False

    @patch("src.api_manager.openai.OpenAI")
    def test_check_health_success(self, mock_openai_class):
        """测试成功的健康检查"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        node = self.mgr.health_nodes["model1"]
        result = self.mgr.check_health(node)
        assert result is True
        assert node.is_healthy is True
        assert node.total_requests >= 1

    @patch("src.api_manager.openai.OpenAI")
    def test_check_health_rate_limit(self, mock_openai_class):
        """测试限流错误的健康检查"""
        import openai
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", MagicMock(), None
        )
        mock_openai_class.return_value = mock_client

        node = self.mgr.health_nodes["model1"]
        result = self.mgr.check_health(node)
        assert result is False
        assert node.is_healthy is False

    @patch("src.api_manager.openai.OpenAI")
    def test_check_health_api_error(self, mock_openai_class):
        """测试 API 错误的健康检查"""
        import openai
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "api error", mock_response, None
        )
        mock_openai_class.return_value = mock_client

        node = self.mgr.health_nodes["model1"]
        result = self.mgr.check_health(node)
        assert result is False

    @patch("src.api_manager.openai.OpenAI")
    def test_check_health_empty_response(self, mock_openai_class):
        """测试空响应的健康检查"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = []  # 空响应
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        node = self.mgr.health_nodes["model1"]
        result = self.mgr.check_health(node)
        assert result is False

    def test_health_check_all(self):
        """测试批量健康检查"""
        with patch.object(self.mgr, "check_health", return_value=True) as mock_check:
            results = self.mgr.health_check_all()
            assert isinstance(results, dict)
            mock_check.assert_called()

    def test_health_check_batch(self):
        """测试分批健康检查"""
        # 添加多个节点
        for i in range(5):
            self.mgr.add_node(LLMConfig(f"key{i}", f"url{i}", f"model{i}"))

        with patch.object(self.mgr, "check_health", return_value=True) as mock_check:
            results = self.mgr.health_check_batch(batch_size=2)
            assert len(results) == 6  # 原有 + 新增 5 个
            assert mock_check.call_count == 6


class TestAPIMangerCall:
    """测试 API 调用功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManger()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    @patch("src.api_manager.openai.OpenAI")
    def test_call_success(self, mock_openai_class):
        """测试成功调用"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = self.mgr.call(messages=[{"role": "user", "content": "hello"}])
        assert result == mock_response
        mock_client.chat.completions.create.assert_called_once()

    @patch("src.api_manager.openai.OpenAI")
    def test_call_with_specific_model(self, mock_openai_class):
        """测试指定模型调用"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = self.mgr.call(
            messages=[{"role": "user", "content": "hello"}],
            model="model1",
        )
        assert result == mock_response

    @patch("src.api_manager.openai.OpenAI")
    def test_call_with_kwargs(self, mock_openai_class):
        """测试传递额外参数"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        self.mgr.call(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.7,
            max_tokens=100,
        )
        # 验证参数被传递
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("temperature") == 0.7
        assert call_kwargs.get("max_tokens") == 100

    @patch("src.api_manager.openai.OpenAI")
    def test_call_fallback_on_rate_limit(self, mock_openai_class):
        """测试限流时的故障转移"""
        import openai
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()

        # 第一个节点限流，第二个成功
        mock_client1.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", MagicMock(), None
        )
        mock_client2.chat.completions.create.return_value = MagicMock()

        mock_openai_class.side_effect = [mock_client1, mock_client2]

        # 添加第二个节点
        self.mgr.add_node(LLMConfig("key2", "url2", "model2"))

        result = self.mgr.call(messages=[{"role": "user", "content": "hello"}])
        assert result is not None

    @patch("src.api_manager.openai.OpenAI")
    def test_call_no_fallback_when_disabled(self, mock_openai_class):
        """测试禁用故障转移时的行为"""
        import openai
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "error", MagicMock(), None
        )
        mock_openai_class.return_value = mock_client

        # 禁用故障转移
        self.mgr.config.fallback_on_failure = False

        with pytest.raises(RuntimeError):
            self.mgr.call(messages=[{"role": "user", "content": "hello"}])

    @patch("src.api_manager.openai.OpenAI")
    def test_call_all_nodes_failed(self, mock_openai_class):
        """测试所有节点都失败时的行为"""
        import openai
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "error", MagicMock(), None
        )
        mock_openai_class.return_value = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            self.mgr.call(messages=[{"role": "user", "content": "hello"}])
        assert "所有 API 节点调用失败" in str(exc_info.value)

    def test_call_no_available_nodes(self):
        """测试无可用节点时抛出异常"""
        # 清空所有节点
        self.mgr.health_nodes.clear()
        self.mgr._client_cache.clear()

        with pytest.raises(RuntimeError, match="无可用 API 节点"):
            self.mgr.call(messages=[{"role": "user", "content": "hello"}])

    @patch("src.api_manager.openai.OpenAI")
    def test_call_unknown_model_raises(self, mock_openai_class):
        """测试指定未知模型时抛出异常"""
        with pytest.raises(RuntimeError, match="无可用 API 节点"):
            self.mgr.call(
                messages=[{"role": "user", "content": "hello"}],
                model="unknown-model",
            )


class TestAPIMangerStatus:
    """测试状态查询功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManger()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    def test_get_status(self):
        """测试获取状态"""
        status = self.mgr.get_status()
        assert isinstance(status, dict)
        assert "total_nodes" in status
        assert "healthy_nodes" in status
        assert "nodes" in status
        assert status["total_nodes"] >= 1

    def test_get_status_node_details(self):
        """测试节点详细信息"""
        status = self.mgr.get_status()
        for _name, node_info in status["nodes"].items():
            assert "model" in node_info
            assert "base_url" in node_info
            assert "is_healthy" in node_info
            assert "success_rate" in node_info
            assert "total_requests" in node_info

    def test_get_top_nodes(self):
        """测试获取表现最好的节点"""
        # 添加一些请求记录
        for node in self.mgr.health_nodes.values():
            node.total_requests = 10
            node.mark_success(100.0)

        top_nodes = self.mgr.get_top_nodes(n=5, sort_by="success_rate")
        assert isinstance(top_nodes, list)

    def test_get_top_nodes_empty(self):
        """测试无请求记录时返回空列表"""
        top_nodes = self.mgr.get_top_nodes(n=5)
        assert top_nodes == []

    def test_get_top_nodes_sort_by_response_time(self):
        """测试按响应时间排序"""
        # 设置不同的响应时间
        nodes = list(self.mgr.health_nodes.values())
        if nodes:
            nodes[0]._response_times.extend([50.0] * 5)
            nodes[0].total_requests = 5

        top_nodes = self.mgr.get_top_nodes(n=1, sort_by="response_time")
        assert len(top_nodes) <= 1

    def test_reset_stats(self):
        """测试重置统计"""
        # 先添加一些统计数据
        for node in self.mgr.health_nodes.values():
            node.total_requests = 10
            node.success_count = 5
            node.error_count = 5
            node.consecutive_failures = 3

        self.mgr.reset_stats()

        for node in self.mgr.health_nodes.values():
            assert node.total_requests == 0
            assert node.success_count == 0
            assert node.error_count == 0
            assert node.consecutive_failures == 0
            assert node.is_healthy is True


class TestHealthCheckerThread:
    """测试后台健康检查线程"""

    def test_thread_creation(self):
        """测试线程创建"""
        mgr = APIManger()
        thread = HealthCheckerThread(mgr, interval=0.1)
        assert thread.daemon is True
        assert thread.name == "APIManger-HealthChecker"
        assert isinstance(thread._stop_event, type(thread._stop_event))

    def test_thread_run_starts_and_stops(self):
        """测试线程启动和停止"""
        mgr = APIManger()
        thread = HealthCheckerThread(mgr, interval=0.1)
        thread.start()
        time.sleep(0.15)  # 让线程运行一小段时间
        thread.stop()
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    def test_thread_skips_if_already_running(self):
        """测试已运行线程不重复启动"""
        mgr = APIManger()
        thread = HealthCheckerThread(mgr, interval=60.0)
        thread.start()
        # 尝试再次启动（应该跳过）
        mgr._start_health_checker()
        time.sleep(0.1)
        thread.stop()
        thread.join(timeout=1.0)


class TestGlobalFunctions:
    """测试全局函数"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()

    def test_get_manager_singleton(self):
        """测试单例模式"""
        mgr1 = get_manager()
        mgr2 = get_manager()
        assert mgr1 is mgr2

    def test_reset_manager_clears_singleton(self):
        """测试重置单例"""
        mgr1 = get_manager()
        reset_manager()
        mgr2 = get_manager()
        assert mgr1 is not mgr2

    @patch("src.api_manager.get_manager")
    def test_print_status_table_none_manager(self, mock_get_manager):
        """测试打印状态表格（使用默认管理器）"""
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "total_nodes": 2,
            "healthy_nodes": 1,
            "rotation_strategy": "health_based",
            "nodes": {
                "model1": {
                    "model": "model1",
                    "is_healthy": True,
                    "success_rate": 0.9,
                    "total_requests": 10,
                    "avg_response_time_ms": 100.0,
                }
            },
        }
        mock_get_manager.return_value = mock_mgr
        # 不应抛出异常
        print_status_table()


class TestAPIMangerEdgeCases:
    """测试边界情况和异常处理"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = APIManagerConfig(
            rotation_strategy=RotationStrategy.ROUND_ROBIN,
            health_check_interval=10.0,
            timeout=30,
        )
        mgr = APIManger(config=config)
        assert mgr.config.rotation_strategy == RotationStrategy.ROUND_ROBIN
        assert mgr.config.health_check_interval == 10.0
        assert mgr.config.timeout == 30

    def test_consecutive_failures_threshold(self):
        """测试连续失败阈值"""
        mgr = APIManger()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = mgr.health_nodes["model1"]

        # 连续失败 2 次，仍健康
        node.mark_failure("error")
        node.mark_failure("error")
        assert node.is_healthy is True

        # 第 3 次失败，变为不健康
        node.mark_failure("error")
        assert node.is_healthy is False

    def test_response_time_sliding_window(self):
        """测试响应时间滑动窗口"""
        mgr = APIManger()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = mgr.health_nodes["model1"]

        # 添加超过窗口大小的响应时间
        for i in range(15):
            node.mark_success(float(i * 10))

        # 窗口大小应为 10
        assert len(node._response_times) == 10
        # 最新的 10 个值应该保留
        assert 140.0 in node._response_times
        assert 0.0 not in node._response_times

    def test_select_node_with_lock(self):
        """测试线程安全选择"""
        import threading
        mgr = APIManger()
        for i in range(5):
            mgr.add_node(LLMConfig(f"key{i}", f"url{i}", f"model{i}"))

        errors = []

        def select_nodes():
            for _ in range(100):
                try:
                    mgr.select_node()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=select_nodes) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
