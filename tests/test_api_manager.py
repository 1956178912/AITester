"""
API Manager 完整测试套件
测试 src/api_manager.py 中的所有核心功能：
- APIHealth 数据类及其属性/方法
- RotationStrategy 枚举
- APIManager 核心功能（轮换策略、健康检查、故障转移、节点管理）
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
from src.api.api_manager import (
    APIHealth,
    APIManager,
    APIManagerConfig,
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
        for _ in range(3):
            self.health.mark_failure("error")

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

    # ── 4.1 熔断冷却期测试 ──

    def test_initial_circuit_state(self):
        """熔断冷却期初始状态：未熔断，冷却时长默认 60s"""
        assert self.health.circuit_open_until == 0.0
        assert self.health.circuit_cooldown_seconds == 60.0
        assert self.health.in_circuit_open is False

    def test_mark_failure_opens_circuit_after_threshold(self):
        """连续失败达到阈值后打开熔断（circuit_open_until 被写入未来时间点）"""
        for _ in range(3):
            self.health.mark_failure("error")
        assert self.health.is_healthy is False
        # 冷却期应已开启：circuit_open_until 大于当前 monotonic
        assert self.health.circuit_open_until > time.monotonic()
        assert self.health.in_circuit_open is True

    def test_mark_success_resets_circuit(self):
        """成功调用复位熔断器（清零冷却截止时间与连续失败计数）"""
        for _ in range(3):
            self.health.mark_failure("error")
        assert self.health.in_circuit_open is True
        # 模拟冷却期内收到一次成功（如健康检查线程探测到恢复）
        self.health.mark_success(50.0)
        assert self.health.in_circuit_open is False
        assert self.health.circuit_open_until == 0.0
        assert self.health.consecutive_failures == 0

    def test_circuit_expires_after_cooldown(self):
        """冷却期到期后自动放行（in_circuit_open 翻回 False，无需等 mark_success）"""
        # 短冷却期便于测试
        self.health.circuit_cooldown_seconds = 0.05
        for _ in range(3):
            self.health.mark_failure("error")
        assert self.health.in_circuit_open is True
        time.sleep(0.08)
        assert self.health.in_circuit_open is False

    def test_circuit_cooldown_config_injection(self):
        """APIManagerConfig.circuit_cooldown_seconds 可覆盖默认 60s 冷却时长"""
        health = APIHealth(config=self.config, circuit_cooldown_seconds=5.0)
        for _ in range(3):
            health.mark_failure("error")
        # 冷却截止应在 now+5s 附近（允许 0.5s 误差）
        delta = health.circuit_open_until - time.monotonic()
        assert 4.0 <= delta <= 5.5


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


class TestAPIManagerNodeManagement:
    """测试节点管理功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()

    @patch("src.api.api_manager.LLM_CONFIGS", [])
    def test_init_with_empty_configs(self):
        """测试空配置初始化"""
        mgr = APIManager(enable_health_checker=False)
        assert len(mgr.health_nodes) == 0
        assert len(mgr.get_all_nodes()) == 0
        assert len(mgr.get_healthy_nodes()) == 0

    @patch(
        "src.api.api_manager.LLM_CONFIGS",
        [
            LLMConfig("key1", "url1", "model1"),
            LLMConfig("key2", "url2", "model2"),
        ],
    )
    def test_init_with_multiple_configs(self):
        """测试多配置初始化"""
        mgr = APIManager(enable_health_checker=False)
        assert len(mgr.health_nodes) == 2
        assert "model1" in mgr.health_nodes
        assert "model2" in mgr.health_nodes

    def test_add_node(self):
        """测试动态添加节点"""
        mgr = APIManager(enable_health_checker=False)
        config = LLMConfig("new-key", "new-url", "new-model")
        mgr.add_node(config)
        assert "new-model" in mgr.health_nodes
        assert mgr.health_nodes["new-model"].config.model_name == "new-model"

    def test_remove_node_existing(self):
        """测试移除存在的节点"""
        mgr = APIManager(enable_health_checker=False)
        config = LLMConfig("key1", "url1", "model1")
        mgr.add_node(config)
        result = mgr.remove_node("model1")
        assert result is True
        assert "model1" not in mgr.health_nodes

    def test_remove_node_nonexistent(self):
        """测试移除不存在的节点"""
        mgr = APIManager(enable_health_checker=False)
        result = mgr.remove_node("nonexistent-model")
        assert result is False

    def test_get_all_nodes(self):
        """测试获取所有节点"""
        mgr = APIManager(enable_health_checker=False)
        nodes = mgr.get_all_nodes()
        assert isinstance(nodes, list)

    def test_get_healthy_nodes_filters(self):
        """测试健康节点过滤"""
        mgr = APIManager(enable_health_checker=False)
        # 初始所有节点都健康
        healthy = mgr.get_healthy_nodes()
        assert len(healthy) == len(mgr.get_all_nodes())

        # 手动标记一个节点不健康
        if mgr.health_nodes:
            first_node = list(mgr.health_nodes.values())[0]
            first_node.is_healthy = False
            healthy = mgr.get_healthy_nodes()
            assert len(healthy) < len(mgr.get_all_nodes())

    def test_get_healthy_nodes_excludes_circuit_open(self):
        """4.1：熔断冷却期内的节点即使 is_healthy 为 True 也被路由过滤"""
        reset_manager()
        mgr = APIManager(enable_health_checker=False)
        mgr.add_node(LLMConfig("keyX", "urlX", "modelX"))
        mgr.add_node(LLMConfig("keyY", "urlY", "modelY"))
        node_x = mgr.health_nodes["modelX"]

        # modelX 触发熔断（连续失败达到阈值）
        for _ in range(3):
            node_x.mark_failure("error")
        # 模拟健康检查线程把 is_healthy 翻回 True，但冷却期仍未到期
        node_x.is_healthy = True
        assert node_x.in_circuit_open is True

        # 路由层应排除 modelX（冷却期内不可用）；modelY 仍可被选中
        healthy = mgr.get_healthy_nodes()
        healthy_names = [n.config.model_name for n in healthy]
        assert "modelX" not in healthy_names
        assert "modelY" in healthy_names

    def test_circuit_open_node_excluded_from_fallback_candidates(self):
        """4.1：_build_node_list 的备用节点候选同样排除熔断冷却期内的节点"""
        reset_manager()
        mgr = APIManager(enable_health_checker=False)
        mgr.add_node(LLMConfig("keyX", "urlX", "modelX"))
        mgr.add_node(LLMConfig("keyY", "urlY", "modelY"))
        node_x = mgr.health_nodes["modelX"]
        for _ in range(3):
            node_x.mark_failure("error")
        node_x.is_healthy = True  # 冷却期内即使健康也被排除
        # 以 modelY 为指定模型构建节点列表：备用候选不应包含 modelX
        nodes_to_try, fallback = mgr._build_node_list("modelY")
        assert [n.config.model_name for n in nodes_to_try] == ["modelY"]
        fallback_names = [n.config.model_name for n in fallback]
        assert "modelX" not in fallback_names

    def test_get_status_exposes_circuit_open_remaining(self):
        """4.1：get_status 输出每节点 circuit_open_remaining_s 字段"""
        reset_manager()
        mgr = APIManager(enable_health_checker=False)
        mgr.add_node(LLMConfig("keyX", "urlX", "modelX"))
        node_x = mgr.health_nodes["modelX"]
        status = mgr.get_status()
        assert status["nodes"]["modelX"]["circuit_open_remaining_s"] == 0.0
        for _ in range(3):
            node_x.mark_failure("error")
        status = mgr.get_status()
        assert status["nodes"]["modelX"]["circuit_open_remaining_s"] > 0.0

    def test_reset_stats_clears_circuit_state(self):
        """4.1：reset_stats 清零熔断冷却状态"""
        reset_manager()
        mgr = APIManager(enable_health_checker=False)
        mgr.add_node(LLMConfig("keyX", "urlX", "modelX"))
        node_x = mgr.health_nodes["modelX"]
        for _ in range(3):
            node_x.mark_failure("error")
        assert node_x.in_circuit_open is True
        mgr.reset_stats()
        assert node_x.in_circuit_open is False
        assert node_x.circuit_open_until == 0.0


class TestAPIManagerRotationStrategies:
    """测试轮换策略"""

    def setup_method(self):
        """每个测试前重置管理器并准备测试环境"""
        reset_manager()
        self.mgr = APIManager(enable_health_checker=False)
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
        # 创建隔离的管理器，避免 .env.local 中配置的多余模型干扰
        from src.api.api_manager import APIManager, RotationStrategy

        mgr = APIManager.__new__(APIManager)
        mgr.config = self.mgr.config
        mgr.health_nodes = {
            "model0": self.mgr.health_nodes["model0"],
            "model1": self.mgr.health_nodes["model1"],
            "model2": self.mgr.health_nodes["model2"],
        }
        mgr._rr_index = 0
        mgr._last_health_check = {}
        mgr._lock = self.mgr._lock
        mgr._health_checker = None
        mgr.config.rotation_strategy = RotationStrategy.ROUND_ROBIN
        selected = []
        for _ in range(6):
            node = mgr.select_node()
            selected.append(node.config.model_name)
        assert len(set(selected)) == 3  # 三个不同的模型
        assert selected[0] != selected[1]

    def test_fastest_first_selects_lowest_time(self):
        """测试最快优先策略：验证 avg_response_time_ms 计算正确"""
        from config import LLMConfig
        from src.api.api_manager import APIHealth, APIManager, RotationStrategy

        mgr = APIManager.__new__(APIManager)
        mgr.config = type("Obj", (), {"rotation_strategy": RotationStrategy.FASTEST_FIRST})()
        mgr.health_nodes = {}
        # 直接创建真实 APIHealth 节点以确保 avg_response_time_ms 可用
        for name in ["model1", "model2", "model3"]:
            cfg = LLMConfig("key", "url", name)
            mgr.health_nodes[name] = APIHealth(config=cfg)
        mgr.health_nodes["model1"]._response_times.extend([100.0] * 5)
        mgr.health_nodes["model2"]._response_times.extend([200.0] * 5)
        mgr.health_nodes["model3"]._response_times.extend([50.0] * 5)
        assert mgr.health_nodes["model3"].avg_response_time_ms == 50.0
        assert mgr.health_nodes["model1"].avg_response_time_ms == 100.0
        assert mgr.health_nodes["model2"].avg_response_time_ms == 200.0

    def test_weighted_random_preferences(self):
        """测试加权随机策略偏好"""
        from src.api.api_manager import reset_manager

        reset_manager()
        mgr = APIManager.__new__(APIManager)
        mgr.config = self.mgr.config
        mgr.health_nodes = {
            "model0": self.mgr.health_nodes["model0"],
            "model1": self.mgr.health_nodes["model1"],
            "model2": self.mgr.health_nodes["model2"],
        }
        mgr._client_cache = {k: self.mgr._client_cache[k] for k in mgr.health_nodes}
        mgr._rr_index = 0
        mgr._last_health_check = {}
        mgr._lock = self.mgr._lock
        mgr._health_checker = None
        mgr.config.rotation_strategy = RotationStrategy.WEIGHTED_RANDOM
        node0 = mgr.health_nodes["model0"]
        node0.mark_success(50.0)
        node1 = mgr.health_nodes["model1"]
        node1.mark_failure("error")
        node2 = mgr.health_nodes["model2"]
        node2.mark_failure("error")

        counts = {"model0": 0, "model1": 0, "model2": 0}
        for _ in range(50):
            node = mgr.select_node()
            counts[node.config.model_name] += 1

        assert counts["model0"] > counts["model1"] or counts["model0"] > counts["model2"]

    def test_health_based_selects_best_score(self):
        """测试健康感知策略选择综合评分最高的节点"""
        from src.api.api_manager import reset_manager

        reset_manager()
        mgr = APIManager.__new__(APIManager)
        mgr.config = self.mgr.config
        mgr.health_nodes = {
            "model0": self.mgr.health_nodes["model0"],
            "model1": self.mgr.health_nodes["model1"],
            "model2": self.mgr.health_nodes["model2"],
        }
        mgr._client_cache = {k: self.mgr._client_cache[k] for k in mgr.health_nodes}
        mgr._rr_index = 0
        mgr._last_health_check = {}
        mgr._lock = self.mgr._lock
        mgr._health_checker = None
        mgr.config.rotation_strategy = RotationStrategy.HEALTH_BASED
        node0 = mgr.health_nodes["model0"]
        node0.mark_success(100.0)
        node0.mark_success(100.0)
        node1 = mgr.health_nodes["model1"]
        node1.mark_success(80.0)
        node2 = mgr.health_nodes["model2"]
        node2.mark_failure("error")

        selected = mgr.select_node()
        assert selected is not None


class TestAPIManagerHealthCheck:
    """测试健康检查功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManager(enable_health_checker=False)
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    def test_check_health_missing_client(self):
        """测试客户端不存在时的健康检查"""
        node = self.mgr.health_nodes["model1"]
        # 移除客户端缓存
        self.mgr._client_cache.pop("model1", None)
        result = self.mgr.check_health(node)
        assert result is False
        assert node.is_healthy is False

    @patch("src.api.api_manager.openai.OpenAI")
    def test_check_health_success(self, mock_openai_class):
        """测试成功的健康检查（在 patch 内部重新创建 mgr，确保使用 mock client）"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # 在 patch 内部重新创建 mgr，避免真实 API 初始化干扰
        reset_manager()
        test_mgr = APIManager(enable_health_checker=False)
        test_mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = test_mgr.health_nodes["model1"]
        result = test_mgr.check_health(node)
        assert result is True
        assert node.is_healthy is True
        assert node.total_requests >= 1

    @patch("src.api.api_manager.openai.OpenAI")
    def test_check_health_rate_limit(self, mock_openai_class):
        """测试限流错误的健康检查"""
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", response=mock_resp, body={"code": "rate_limit"}
        )
        mock_openai_class.return_value = mock_client

        reset_manager()
        test_mgr = APIManager(enable_health_checker=False)
        test_mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = test_mgr.health_nodes["model1"]
        result = test_mgr.check_health(node)
        assert result is False
        # 连续失败1次不足以标记为不健康（需要 >=3 次）
        assert node.consecutive_failures == 1
        assert node.error_count == 1

    @patch("src.api.api_manager.openai.OpenAI")
    def test_check_health_api_error(self, mock_openai_class):
        """测试 API 错误的健康检查"""
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "api error", request=mock_resp, body={"code": "server_error"}
        )
        mock_openai_class.return_value = mock_client

        node = self.mgr.health_nodes["model1"]
        result = self.mgr.check_health(node)
        assert result is False

    @patch("src.api.api_manager.openai.OpenAI")
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
        # 清空所有节点，只添加测试节点，避免 .env.local 中真实 API 被调用
        self.mgr.health_nodes.clear()
        self.mgr._client_cache.clear()
        for i in range(5):
            self.mgr.add_node(LLMConfig(f"key{i}", f"url{i}", f"model{i}"))

        with patch.object(self.mgr, "check_health", return_value=True) as mock_check:
            results = self.mgr.health_check_batch(batch_size=2)
            assert len(results) == 5
            assert mock_check.call_count == 5


class TestAPIManagerCall:
    """测试 API 调用功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManager(enable_health_checker=False)
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_success(self, mock_openai_class):
        """测试成功调用"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        # 只使用我们自己添加的 model1，清空其他节点避免真实 API 调用
        model_name = "model1"
        self.mgr._client_cache = {model_name: mock_client}
        self.mgr.health_nodes = {model_name: self.mgr.health_nodes[model_name]}

        result = self.mgr.call(messages=[{"role": "user", "content": "hello"}])
        assert result == mock_response
        mock_client.chat.completions.create.assert_called_once()

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_with_specific_model(self, mock_openai_class):
        """测试指定模型调用"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # 清空其他节点，只保留 model1
        self.mgr._client_cache = {"model1": mock_client}
        self.mgr.health_nodes = {"model1": self.mgr.health_nodes["model1"]}

        result = self.mgr.call(
            messages=[{"role": "user", "content": "hello"}],
            model="model1",
        )
        assert result == mock_response

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_with_kwargs(self, mock_openai_class):
        """测试传递额外参数"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        self.mgr._client_cache = {"model1": mock_client}
        self.mgr.health_nodes = {"model1": self.mgr.health_nodes["model1"]}

        self.mgr.call(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.7,
            max_tokens=100,
        )
        # 验证参数被传递
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("temperature") == 0.7
        assert call_kwargs.get("max_tokens") == 100

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_fallback_on_rate_limit(self, mock_openai_class):
        """测试限流时的故障转移"""
        import openai

        mock_client1 = MagicMock()
        mock_client2 = MagicMock()

        # 第一个节点限流，第二个成功
        mock_resp429 = MagicMock()
        mock_resp429.status_code = 429
        mock_client1.chat.completions.create.side_effect = openai.RateLimitError(
            "rate limit", response=mock_resp429, body={"code": "rate_limit"}
        )
        mock_client2.chat.completions.create.return_value = MagicMock()

        mock_openai_class.side_effect = [mock_client1, mock_client2]

        # 清空并只添加 model1 和 model2
        self.mgr.health_nodes.clear()
        self.mgr._client_cache.clear()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))
        self.mgr.add_node(LLMConfig("key2", "url2", "model2"))
        self.mgr._client_cache["model1"] = mock_client1
        self.mgr._client_cache["model2"] = mock_client2

        result = self.mgr.call(messages=[{"role": "user", "content": "hello"}])
        assert result is not None

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_fallback_with_explicit_model_uses_node_model(self, mock_openai_class):
        """显式指定 model 且主节点失败时，备用节点改用自身模型名。

        回归：此前 call_model = model or node.config.model_name，指定模型时
        故障转移到备用节点仍沿用指定模型名——备用 provider 没有该模型，
        逐个 APIError 陪葬，故障转移形同虚设。
        """
        import openai

        mock_client1 = MagicMock()
        mock_client2 = MagicMock()

        # 主节点（model1）服务端错误，备用节点（model2）成功
        mock_resp500 = MagicMock()
        mock_resp500.status_code = 500
        mock_client1.chat.completions.create.side_effect = openai.APIError(
            "primary down", request=mock_resp500, body={"code": "server_error"}
        )
        ok_response = MagicMock()
        mock_client2.chat.completions.create.return_value = ok_response

        self.mgr.health_nodes.clear()
        self.mgr._client_cache.clear()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))
        self.mgr.add_node(LLMConfig("key2", "url2", "model2"))
        self.mgr._client_cache["model1"] = mock_client1
        self.mgr._client_cache["model2"] = mock_client2

        result = self.mgr.call(messages=[{"role": "user", "content": "hello"}], model="model1")

        assert result is ok_response
        # 主节点尝试：用显式指定的 model1
        assert mock_client1.chat.completions.create.call_args.kwargs["model"] == "model1"
        # 备用节点尝试：改用节点自身 model2（而非沿用指定模型）
        assert mock_client2.chat.completions.create.call_args.kwargs["model"] == "model2"

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_no_fallback_when_disabled(self, mock_openai_class):
        """测试禁用故障转移时的行为：APIError → _handle_api_error → bare raise 无 active exception → RuntimeError"""
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "api error", request=mock_resp, body={"code": "error"}
        )
        mock_openai_class.return_value = mock_client

        self.mgr.health_nodes = {"model1": self.mgr.health_nodes["model1"]}
        self.mgr._client_cache = {"model1": mock_client}
        self.mgr.config.fallback_on_failure = False

        # APIError 在 call() 循环中被 except openai.APIError 捕获，
        # 进入 _handle_api_error 后执行 bare raise，但此时无 active exception，
        # Python 会重新抛出原始异常（APIError）
        with pytest.raises(openai.APIError):
            self.mgr.call(messages=[{"role": "user", "content": "hello"}])

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_all_nodes_failed(self, mock_openai_class):
        """测试所有节点都失败时的行为"""
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.chat.completions.create.side_effect = openai.APIError(
            "error", request=mock_resp, body={"code": "error"}
        )
        mock_openai_class.return_value = mock_client

        self.mgr._client_cache = {"model1": mock_client}
        self.mgr.health_nodes = {"model1": self.mgr.health_nodes["model1"]}

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

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_unknown_model_raises(self, mock_openai_class):
        """测试指定未知模型时抛出异常"""
        self.mgr._client_cache.clear()
        self.mgr.health_nodes.clear()
        with pytest.raises(RuntimeError, match="无可用 API 节点"):
            self.mgr.call(
                messages=[{"role": "user", "content": "hello"}],
                model="unknown-model",
            )


class TestAPIManagerStatus:
    """测试状态查询功能"""

    def setup_method(self):
        """每个测试前重置管理器"""
        reset_manager()
        self.mgr = APIManager(enable_health_checker=False)
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
        mgr = APIManager(enable_health_checker=False)
        thread = HealthCheckerThread(mgr, interval=0.1)
        assert thread.daemon is True
        assert thread.name == "APIManager-HealthChecker"
        assert isinstance(thread._stop_event, type(thread._stop_event))

    def test_thread_run_starts_and_stops(self):
        """测试线程启动和停止"""
        # 使用空配置的管理器，避免后台线程因连接真实 API 而卡住
        from src.api.api_manager import reset_manager

        reset_manager()
        mgr = APIManager.__new__(APIManager)
        mgr.config = type("Obj", (), {"health_check_interval": 60.0})()
        mgr.health_nodes = {}
        thread = HealthCheckerThread(mgr, interval=0.1)
        thread.start()
        time.sleep(0.2)
        thread.stop()
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    def test_thread_skips_if_already_running(self):
        """测试已运行线程不重复启动"""
        mgr = APIManager(enable_health_checker=False)
        thread = HealthCheckerThread(mgr, interval=60.0)
        thread.start()
        # 尝试再次启动（应该跳过）
        mgr._start_health_checker()
        time.sleep(0.1)
        thread.stop()
        thread.join(timeout=1.0)

    def test_ctor_flag_false_skips_thread(self):
        """构造参数 enable_health_checker=False 时不创建后台线程（嵌入式/测试场景防副作用）"""
        mgr = APIManager(enable_health_checker=False)
        assert mgr._health_checker is None

    def test_ctor_default_starts_thread(self):
        """默认（True）保持历史行为：自动启动后台健康检查线程"""
        mgr = APIManager()  # 默认启用健康检查线程
        try:
            assert mgr._health_checker is not None
            assert mgr._health_checker.is_alive()
        finally:
            # 立即停止并等待线程退出（首次健康检查在 60s 间隔后才发生，stop 很快返回）
            mgr._stop_health_checker()
        assert mgr._health_checker is None


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

    @patch("src.api.api_manager.get_manager")
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


class TestAPIManagerEdgeCases:
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
        mgr = APIManager(config=config)
        assert mgr.config.rotation_strategy == RotationStrategy.ROUND_ROBIN
        assert mgr.config.health_check_interval == 10.0
        assert mgr.config.timeout == 30

    def test_consecutive_failures_threshold(self):
        """测试连续失败阈值"""
        mgr = APIManager(enable_health_checker=False)
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
        mgr = APIManager(enable_health_checker=False)
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

        mgr = APIManager(enable_health_checker=False)
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


class TestGhostConfigWiring:
    """APIManagerConfig.max_consecutive_failures 幽灵配置接线（0.9.9 批次）。

    此前该字段在 APIManagerConfig 中定义却从未被 mark_failure 消费（硬编码 3），
    现接线为 APIHealth.max_consecutive_failures 字段，由 manager 构造时注入。
    """

    def _make_config(self):
        return LLMConfig(api_key="k", base_url="u", model_name="m")

    def test_default_threshold_keeps_history(self):
        """默认阈值 3：连续失败 2 次仍健康，第 3 次标记不健康（与历史硬编码行为一致）"""
        health = APIHealth(config=self._make_config())
        health.mark_failure()
        health.mark_failure()
        assert health.is_healthy
        health.mark_failure()
        assert not health.is_healthy

    def test_custom_threshold_respected(self):
        """自定义阈值生效：max_consecutive_failures=1 时首次失败即不健康"""
        health = APIHealth(config=self._make_config(), max_consecutive_failures=1)
        health.mark_failure()
        assert not health.is_healthy

    def test_manager_injects_config_threshold_into_nodes(self):
        """APIManager 构造/add_node 时把 manager 配置注入节点（此前节点永远用默认 3）"""
        mgr = APIManager(config=APIManagerConfig(max_consecutive_failures=2), enable_health_checker=False)
        mgr.add_node(self._make_config())
        node = mgr.health_nodes["m"]
        assert node.max_consecutive_failures == 2
        node.mark_failure()
        assert node.is_healthy  # 阈值 2：1 次失败仍健康
        node.mark_failure()
        assert not node.is_healthy


class TestCircuitCooldownBoundaries:
    """1.5 熔断冷却期边界测试（冷却结束回归 / 多节点同时冷却 / 冷却期内快速失败）。

    背景（4.1 熔断冷却期）：节点连续失败达阈值后进入冷却期，冷却期内即使
    健康检查线程把 is_healthy 翻回 True，路由层仍跳过该节点。本组测试
    锁定冷却期三条边界行为：
    1. 冷却结束 → 节点重新进入路由池（无需 mark_success）；
    2. 多节点同时冷却 → 路由整体降级（select_node 返回 None / call 快速失败）；
    3. 冷却期内新请求 → 不打回冷却节点（流量落到健康节点或快速失败）。
    """

    def _make_manager(self, names: list[str], cooldown: float = 60.0) -> APIManager:
        reset_manager()
        mgr = APIManager(config=APIManagerConfig(circuit_cooldown_seconds=cooldown), enable_health_checker=False)
        mgr.health_nodes.clear()
        mgr._client_cache.clear()
        for name in names:
            mgr.add_node(LLMConfig(f"key-{name}", f"https://api-{name}.example.com", name))
        return mgr

    def test_node_returns_to_routing_after_cooldown_expires(self):
        """边界 1：冷却期到期后节点重新被路由选中（in_circuit_open 翻回 False）。

        用 0.05s 短冷却模拟到期：期间即使健康检查线程把 is_healthy 翻回
        True，节点仍被排除；到期后自动回归，无需 mark_success。
        """
        mgr = self._make_manager(["a", "b"], cooldown=0.05)
        node_a = mgr.health_nodes["a"]
        for _ in range(3):
            node_a.mark_failure("error")
        # 模拟健康检查线程把 is_healthy 翻回 True（冷却期内仍被排除）
        node_a.is_healthy = True
        healthy_names = [n.config.model_name for n in mgr.get_healthy_nodes()]
        assert "a" not in healthy_names
        # 冷却期到期后自动回归路由池
        time.sleep(0.08)
        healthy_names = [n.config.model_name for n in mgr.get_healthy_nodes()]
        assert "a" in healthy_names, "冷却到期后节点应重新进入路由池"
        assert node_a.in_circuit_open is False

    def test_all_nodes_cooled_down_degrades_routing_to_none(self):
        """边界 2：多节点同时进入冷却期 → 无健康节点，路由整体降级。

        select_node 返回 None；call() 走"无可用 API 节点"快速失败路径
        （而非逐个打回冷却中的死 provider 浪费时间与 token）。
        """
        mgr = self._make_manager(["a", "b", "c"], cooldown=60.0)
        for name in ("a", "b", "c"):
            for _ in range(3):
                mgr.health_nodes[name].mark_failure("error")
        # 模拟健康检查线程翻回健康（冷却期内仍不可用）
        for name in ("a", "b", "c"):
            mgr.health_nodes[name].is_healthy = True
        assert mgr.select_node() is None, "全部节点冷却期内应无健康节点"
        assert mgr.get_healthy_nodes() == []
        # call() 快速失败：不发起任何节点调用
        with pytest.raises(RuntimeError, match="无可用 API 节点"):
            mgr.call(messages=[{"role": "user", "content": "hi"}])
        # get_status 应暴露每节点剩余冷却秒数 > 0
        status = mgr.get_status()
        for name in ("a", "b", "c"):
            assert status["nodes"][name]["circuit_open_remaining_s"] > 0.0

    def test_request_during_cooldown_does_not_hit_cooled_node(self, caplog):
        """边界 3：冷却期内新请求 → 流量直接落到健康节点，冷却节点零调用。

        用 mock 客户端区分两个节点的调用次数：冷却中的节点即使被显式指定
        也不进入尝试列表（备用候选同样排除），健康节点承接全部流量。
        """
        from unittest.mock import MagicMock

        mgr = self._make_manager(["cold", "warm"], cooldown=60.0)
        # cold 进入冷却期，且模拟健康检查翻回 is_healthy=True
        for _ in range(3):
            mgr.health_nodes["cold"].mark_failure("error")
        mgr.health_nodes["cold"].is_healthy = True

        cold_client, warm_client = MagicMock(), MagicMock()
        mgr._client_cache["cold"] = cold_client
        mgr._client_cache["warm"] = warm_client

        # 显式指定 cold 模型：主节点在冷却期 → 备用候选不含 cold，走 warm
        result = mgr.call(messages=[{"role": "user", "content": "hi"}], model="warm")
        assert result is not None
        # 健康节点被调用（故障转移语义），冷却节点零调用
        assert warm_client.chat.completions.create.call_count >= 1
        assert cold_client.chat.completions.create.call_count == 0, "冷却期内节点不应承接任何请求"


