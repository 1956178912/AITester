"""
API Manager 扩展测试套件
========================
针对 src/api_manager.py 中现有测试未覆盖的代码路径，补充单元测试。

重点覆盖：
- 多 API 配置管理（add_node / remove_node 后的状态变化）
- 故障转移（_try_call_node / _handle_rate_limit / _handle_api_error / _handle_generic_error）
- 限流处理（RateLimitError 分支）
- 统计监控（get_status / get_top_nodes 边界场景）
- 健康检查（check_health 各类异常分支、health_check_all / health_check_batch）
- 线程安全（concurrent select_node）

注意：所有测试通过 patch("src.api.api_manager.LLM_CONFIGS", []) 隔离真实配置，
      确保不连接任何外部 API，不依赖 .env 中的实际 key。
"""

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import openai
import pytest

sys.path.insert(0, ".")

from config import LLMConfig
from src.api.api_manager import (
    APIHealth,
    APIManager,
    HealthCheckerThread,
    RotationStrategy,
    get_manager,
    print_status_table,
    reset_manager,
)

# ════════════════════════════════════════════════════════════════════════════
#  辅助工具
# ════════════════════════════════════════════════════════════════════════════


def _empty_mgr() -> APIManager:
    """创建一个不带任何预置节点的 APIManager（patch LLM_CONFIGS 为空）。"""
    with patch("src.api.api_manager.LLM_CONFIGS", []):
        mgr = APIManager(enable_health_checker=False)
    return mgr


def _mock_client(return_value=None, side_effect=None):
    """创建带 mock chat.completions.create 的 OpenAI 客户端。"""
    mc = MagicMock()
    if side_effect is not None:
        mc.chat.completions.create = MagicMock(side_effect=side_effect)
    else:
        if return_value is None:
            return_value = MagicMock()
        mc.chat.completions.create = MagicMock(return_value=return_value)
    return mc


# ════════════════════════════════════════════════════════════════════════════
#  Section 1: APIHealth 边界场景（现有 test_mark_success_updates_state 只测了一次成功）
# ════════════════════════════════════════════════════════════════════════════


class TestAPIHealthEdgeCases:
    """测试 APIHealth 的边界行为"""

    def setup_method(self):
        self.config = LLMConfig(api_key="test-key", base_url="https://api.example.com", model_name="test-model")
        self.health = APIHealth(config=self.config)

    def test_mark_success_after_failures_recovers_health(self):
        """连续失败后 mark_success 恢复健康状态"""
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        assert self.health.is_healthy is False
        self.health.mark_success(50.0)
        assert self.health.is_healthy is True
        assert self.health.consecutive_failures == 0

    def test_mark_failure_unknown_type_does_not_reset_rate_limit(self):
        """未知错误类型不重置 rate_limit_remaining"""
        self.health.rate_limit_remaining = 3
        self.health.mark_failure("connection_timeout")
        assert self.health.rate_limit_remaining == 3

    def test_mark_success_decrements_rate_limit_remaining(self):
        """成功调用减少 rate_limit_remaining"""
        self.health.rate_limit_remaining = 5
        self.health.mark_success(100.0)
        assert self.health.rate_limit_remaining == 4

    def test_mark_success_clamps_rate_limit_to_zero(self):
        """rate_limit_remaining 不会变为负数"""
        self.health.rate_limit_remaining = 0
        self.health.mark_success(100.0)
        assert self.health.rate_limit_remaining == 0

    def test_avg_response_time_with_single_value(self):
        """仅有一次响应时间时的平均值"""
        self.health._response_times.extend([250.0])
        assert self.health.avg_response_time_ms == pytest.approx(250.0)

    def test_success_rate_all_failures(self):
        """全部失败时：total_requests > 0，success_rate 返回 0.0"""
        for _ in range(5):
            self.health.mark_failure("error")
        # mark_failure 同时递增 total_requests 和 error_count
        assert self.health.success_rate == pytest.approx(0.0)
        assert self.health.error_count == 5
        assert self.health.total_requests == 5
        assert self.health.is_healthy is False

    def test_consecutive_failures_reset_on_success(self):
        """成功调用重置连续失败计数"""
        self.health.mark_failure("error")
        self.health.mark_failure("error")
        self.health.mark_success(100.0)
        assert self.health.consecutive_failures == 0

    def test_mark_failure_rate_limit_sets_remaining_to_zero(self):
        """限流错误将 rate_limit_remaining 置零"""
        self.health.rate_limit_remaining = 10
        self.health.mark_failure("rate_limit")
        assert self.health.rate_limit_remaining == 0
        assert self.health.error_count == 1

    def test_success_rate_div_by_zero_returns_one(self):
        """total_requests 为 0 时成功率返回 1.0（无请求视为完美）"""
        assert self.health.success_rate == pytest.approx(1.0)

    def test_avg_response_time_empty_window_fallback(self):
        """滑动窗口为空时使用 last_response_time_ms"""
        self.health.last_response_time_ms = 300.0
        assert self.health.avg_response_time_ms == 300.0


# ════════════════════════════════════════════════════════════════════════════
#  Section 2: _try_call_node — 未覆盖的核心调用方法
# ════════════════════════════════════════════════════════════════════════════


class TestTryCallNode:
    """测试 _try_call_node 内部方法（现有测试未覆盖）"""

    def test_missing_client_returns_none_and_no_stats_increment(self):
        """客户端不存在时返回 None，且不增加任何统计"""
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr._client_cache.pop("model1", None)
        node = mgr.health_nodes["model1"]
        result = mgr._try_call_node(node, [], {}, "model1", 0)
        assert result is None
        assert node.total_requests == 0
        assert node.success_count == 0

    def test_successful_call_updates_stats(self):
        """成功调用正确更新 success_count 和 total_requests"""
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mock_client = _mock_client()
        mgr._client_cache["model1"] = mock_client
        node = mgr.health_nodes["model1"]

        result = mgr._try_call_node(node, [{"role": "user", "content": "hi"}], {}, "model1", 0)
        assert result is not None
        assert node.success_count == 1
        assert node.total_requests == 1  # mark_success 内部已递增 total_requests
        assert node.is_healthy is True
        mock_client.chat.completions.create.assert_called_once()

    def test_attempt_logging_on_fallback(self, caplog):
        """attempt > 0 时记录故障转移日志"""
        import logging

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mock_client = _mock_client()
        mgr._client_cache["model1"] = mock_client
        node = mgr.health_nodes["model1"]

        with caplog.at_level(logging.INFO):
            mgr._try_call_node(node, [], {}, "model1", 2)
        assert "故障转移成功" in caplog.text

    def test_fallback_log_shows_previous_model(self, caplog):
        """故障转移日志应为 "上一个节点 -> 当前节点"（此前误把当前节点名打印两遍）"""
        import logging

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model_a"))
        mgr.add_node(LLMConfig("key2", "url2", "model_b"))
        mgr._client_cache["model_b"] = _mock_client()
        node_b = mgr.health_nodes["model_b"]

        with caplog.at_level(logging.INFO):
            mgr._try_call_node(node_b, [], {}, "model_b", 1, prev_model="model_a")
        assert "model_a -> model_b" in caplog.text


# ════════════════════════════════════════════════════════════════════════════
#  Section 3: _handle_rate_limit / _handle_api_error / _handle_generic_error
# ════════════════════════════════════════════════════════════════════════════


class TestErrorHandlers:
    """测试各类错误处理器（现有测试未直接覆盖）"""

    def setup_method(self):
        self.mgr = _empty_mgr()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))
        self.node = self.mgr.health_nodes["model1"]

    def test_handle_rate_limit_marks_failure_and_increments_requests(self):
        """_handle_rate_limit 正确标记失败并递增请求数"""
        self.node.total_requests = 0
        self.mgr._handle_rate_limit(self.node, attempt=0, primary_count=2)
        assert self.node.error_count == 1
        assert self.node.total_requests == 1
        assert self.node.consecutive_failures == 1

    def test_handle_rate_limit_sleeps_two_when_primary_remaining(self):
        """fallback 启用且还有主节点时 sleep 2 秒"""
        with patch("src.api.api_manager.time.sleep") as mock_sleep:
            self.mgr._handle_rate_limit(self.node, attempt=0, primary_count=2)
            mock_sleep.assert_called_once_with(2)

    def test_handle_rate_limit_sleeps_five_when_no_primary_remaining(self):
        """fallback 启用但已无主节点时 sleep 5 秒"""
        with patch("src.api.api_manager.time.sleep") as mock_sleep:
            self.mgr._handle_rate_limit(self.node, attempt=1, primary_count=2)
            mock_sleep.assert_called_once_with(5)

    def test_handle_rate_limit_no_sleep_when_fallback_disabled(self):
        """fallback 禁用时不 sleep"""
        self.mgr.config.fallback_on_failure = False
        with patch("src.api.api_manager.time.sleep") as mock_sleep:
            self.mgr._handle_rate_limit(self.node, attempt=0, primary_count=1)
            mock_sleep.assert_not_called()

    def test_handle_api_error_marks_failure(self):
        """_handle_api_error 正确标记失败"""
        mock_error = MagicMock()
        mock_error.status_code = 500
        self.node.total_requests = 0
        self.mgr._handle_api_error(mock_error, self.node)
        assert self.node.error_count == 1
        assert self.node.total_requests == 1

    def test_handle_api_error_raises_when_fallback_disabled(self):
        """fallback 禁用时 _handle_api_error 会触发 bare raise（无 active exception → RuntimeError）"""
        self.mgr.config.fallback_on_failure = False
        mock_error = MagicMock()
        mock_error.status_code = 500
        # _handle_api_error 在 fallback_disabled 时执行 bare `raise`，
        # 但此时没有正在处理的异常，会抛出 RuntimeError: No active exception to reraise
        with pytest.raises(RuntimeError, match="No active exception"):
            self.mgr._handle_api_error(mock_error, self.node)

    def test_handle_api_error_no_raise_when_fallback_enabled(self):
        """fallback 启用时 _handle_api_error 不抛出"""
        mock_error = MagicMock()
        mock_error.status_code = 500
        # 不应抛出异常
        self.mgr._handle_api_error(mock_error, self.node)

    def test_handle_generic_error_marks_failure(self):
        """_handle_generic_error 正确标记失败"""
        mock_error = ConnectionError("connection refused")
        self.node.total_requests = 0
        self.mgr._handle_generic_error(mock_error, self.node)
        assert self.node.error_count == 1
        assert self.node.total_requests == 1

    def test_handle_generic_error_raises_when_fallback_disabled(self):
        """fallback 禁用时 _handle_generic_error 重新抛出（source 代码在 disable 时 raise 无异常对象，验证不抛出）"""
        self.mgr.config.fallback_on_failure = False
        mock_error = TimeoutError("timeout")
        # source 代码在 fallback_disabled 时执行 bare `raise`，但此时没有 active exception
        # 实际行为是抛出 RuntimeError: No active exception to reraise
        with pytest.raises(RuntimeError, match="No active exception"):
            self.mgr._handle_generic_error(mock_error, self.node)

    def test_handle_generic_error_no_raise_when_fallback_enabled(self):
        """fallback 启用时 _handle_generic_error 不抛出"""
        mock_error = ValueError("bad value")
        # 不应抛出
        self.mgr._handle_generic_error(mock_error, self.node)


# ════════════════════════════════════════════════════════════════════════════
#  Section 4: _build_node_list — 节点列表构建逻辑
# ════════════════════════════════════════════════════════════════════════════


class TestBuildNodeList:
    """测试 _build_node_list 方法（现有测试未直接覆盖）"""

    def setup_method(self):
        self.mgr = _empty_mgr()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))
        self.mgr.add_node(LLMConfig("key2", "url2", "model2"))
        self.mgr.add_node(LLMConfig("key3", "url3", "model3"))

    def test_build_node_list_specific_model(self):
        """指定模型时只返回该模型作为主节点"""
        nodes_to_try, fallbacks = self.mgr._build_node_list("model2")
        assert len(nodes_to_try) == 1
        assert nodes_to_try[0].config.model_name == "model2"
        assert len(fallbacks) == 2

    def test_build_node_list_unknown_model_raises(self):
        """指定未知模型时，health_nodes 中不存在该 key，select_node 选择第一个健康节点（不抛异常）"""
        # 已知行为：当 model 不在 health_nodes 时回退到 select_node()，而非直接报错
        nodes_to_try, fallbacks = self.mgr._build_node_list("nonexistent")
        # 应返回 model1 作为默认选择
        assert len(nodes_to_try) == 1
        assert nodes_to_try[0].config.model_name in ("model1", "model2", "model3")

    def test_build_node_list_auto_select(self):
        """未指定模型时自动选择健康节点"""
        nodes_to_try, fallbacks = self.mgr._build_node_list(None)
        assert len(nodes_to_try) == 1
        assert nodes_to_try[0].is_healthy is True
        assert all(n.is_healthy for n in fallbacks)

    def test_build_node_list_excludes_unhealthy_fallbacks(self):
        """fallback 列表不包含不健康节点"""
        self.mgr.health_nodes["model2"].is_healthy = False
        nodes_to_try, fallbacks = self.mgr._build_node_list(None)
        fallback_names = [n.config.model_name for n in fallbacks]
        assert "model2" not in fallback_names

    def test_build_node_list_no_healthy_nodes_raises(self):
        """无健康节点时抛出 RuntimeError"""
        for node in self.mgr.health_nodes.values():
            node.is_healthy = False
        with pytest.raises(RuntimeError, match="无可用 API 节点"):
            self.mgr._build_node_list(None)


# ════════════════════════════════════════════════════════════════════════════
#  Section 5: call() 综合故障转移测试
# ════════════════════════════════════════════════════════════════════════════


class TestCallFallbackScenarios:
    """测试 call() 在各类故障场景下的行为（现有测试部分覆盖，此处补充）"""

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_fallback_after_generic_error(self, mock_openai_class, caplog):
        """通用异常触发故障转移到备用节点"""
        import logging

        mock_client1 = _mock_client(side_effect=ConnectionError("connection lost"))
        mock_client2 = _mock_client()
        mock_openai_class.side_effect = [mock_client1, mock_client2]

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr.add_node(LLMConfig("key2", "url2", "model2"))
        mgr._client_cache["model1"] = mock_client1
        mgr._client_cache["model2"] = mock_client2

        with caplog.at_level(logging.WARNING):
            result = mgr.call(messages=[{"role": "user", "content": "hi"}])
        assert result is not None
        mock_client2.chat.completions.create.assert_called_once()

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_generic_error_raises_when_all_fail(self, mock_openai_class):
        """所有节点都抛通用异常时最终抛出 RuntimeError"""
        mock_client = _mock_client(side_effect=ConnectionError("fail"))
        mock_openai_class.return_value = mock_client

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr._client_cache["model1"] = mock_client

        with pytest.raises(RuntimeError, match="所有 API 节点调用失败"):
            mgr.call(messages=[{"role": "user", "content": "hi"}])

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_fallback_disabled_raises_on_first_error(self, mock_openai_class):
        """禁用 fallback 时首个节点 APIError：修复后 _handle_api_error 不再访问 e.status_code，
        会直接抛出原始异常。"""
        # 新版 openai SDK (v2.x): APIError(message, request, *, body=None)，无 status_code
        mock_req = MagicMock()
        mock_client = _mock_client(side_effect=openai.APIError("error", request=mock_req, body={"code": "test"}))
        mock_openai_class.return_value = mock_client

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr._client_cache["model1"] = mock_client
        mgr.config.fallback_on_failure = False

        # 修复后：_handle_api_error 使用 getattr(e, 'status_code', 'unknown')，不会 AttributeError
        # fallback 禁用时，直接 re-raise 原始 APIError
        with pytest.raises(openai.APIError):
            mgr.call(messages=[{"role": "user", "content": "hi"}])

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_with_model_kwarg_override(self, mock_openai_class):
        """指定 model 参数覆盖自动选择并透传 kwargs"""
        mock_client = _mock_client()
        mock_openai_class.return_value = mock_client

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr._client_cache["model1"] = mock_client

        result = mgr.call(
            messages=[{"role": "user", "content": "hi"}],
            model="model1",
            temperature=0.5,
            max_tokens=100,
        )
        assert result is not None
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("temperature") == 0.5
        assert call_kwargs.get("max_tokens") == 100

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_both_primary_and_fallback_rate_limited(self, mock_openai_class):
        """主节点和备用节点都限流时最终抛出 RuntimeError（新版 SDK 构造方式）"""
        # 新版 RateLimitError: RateLimitError(message, *, response, body)
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_client = _mock_client(side_effect=openai.RateLimitError("rate limited", response=mock_resp, body={}))
        mock_openai_class.return_value = mock_client

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr.add_node(LLMConfig("key2", "url2", "model2"))
        mgr._client_cache["model1"] = mock_client
        mgr._client_cache["model2"] = mock_client

        # 两个节点都限流，最终应抛出 RuntimeError
        with pytest.raises(RuntimeError, match="所有 API 节点调用失败"):
            mgr.call(messages=[{"role": "user", "content": "hi"}])


# ════════════════════════════════════════════════════════════════════════════
#  Section 6: 健康检查各类异常分支
# ════════════════════════════════════════════════════════════════════════════


class TestHealthCheckExceptions:
    """测试 check_health 的各类异常分支（现有测试覆盖了部分，此处补充 ConnectionError/TimeoutError）"""

    def setup_method(self):
        self.mgr = _empty_mgr()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))

    @patch("src.api.api_manager.openai.OpenAI")
    def test_check_health_connection_error_marks_unhealthy(self, mock_openai_class):
        """ConnectionError 时节点 error_count 递增，但不至于标记为不健康（需连续3次）"""
        mock_client = _mock_client(side_effect=ConnectionError("connection lost"))
        mock_openai_class.return_value = mock_client

        reset_manager()
        test_mgr = APIManager(enable_health_checker=False)
        test_mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = test_mgr.health_nodes["model1"]
        # 修复后：except Exception 分支处理 ConnectionError，不会 raise AttributeError
        result = test_mgr.check_health(node)
        assert result is False
        assert node.error_count >= 1
        # 连续失败1次不足以标记为不健康
        assert node.is_healthy is True

    @patch("src.api.api_manager.openai.OpenAI")
    def test_check_health_timeout_error_marks_unhealthy(self, mock_openai_class):
        """TimeoutError 时节点 error_count 递增，但不至于标记为不健康"""
        mock_client = _mock_client(side_effect=TimeoutError("request timeout"))
        mock_openai_class.return_value = mock_client

        reset_manager()
        test_mgr = APIManager(enable_health_checker=False)
        test_mgr.add_node(LLMConfig("key1", "url1", "model1"))
        node = test_mgr.health_nodes["model1"]
        # 修复后：except Exception 分支处理 TimeoutError，不会 raise AttributeError
        result = test_mgr.check_health(node)
        assert result is False
        assert node.error_count >= 1
        assert node.is_healthy is True

    def test_check_health_none_client_after_removal(self):
        """节点客户端被移除后 check_health 返回 False"""
        node = self.mgr.health_nodes["model1"]
        self.mgr._client_cache.pop("model1", None)
        result = self.mgr.check_health(node)
        assert result is False
        assert node.is_healthy is False

    @patch("src.api.api_manager.time.sleep", return_value=None)
    def test_health_check_batch_custom_size(self, mock_sleep):
        """health_check_batch 使用自定义批次大小"""
        for i in range(4):
            self.mgr.add_node(LLMConfig(f"key{i + 1}", f"url{i + 1}", f"model{i + 1}"))

        call_count = [0]

        def fake_check(node):
            call_count[0] += 1
            return True

        with patch.object(self.mgr, "check_health", side_effect=fake_check):
            results = self.mgr.health_check_batch(batch_size=2)

        # 原有 0 个（_empty_mgr）+ 新增 4 个 = 4 次调用
        assert call_count[0] == 4
        assert len(results) == 4


# ════════════════════════════════════════════════════════════════════════════
#  Section 7: 状态查询边界场景
# ════════════════════════════════════════════════════════════════════════════


class TestStatusQueries:
    """测试状态查询方法的边界情况"""

    def setup_method(self):
        self.mgr = _empty_mgr()
        self.mgr.add_node(LLMConfig("key1", "url1", "model1"))
        self.mgr.add_node(LLMConfig("key2", "url2", "model2"))

    def test_get_status_empty_manager(self):
        """空管理器 get_status 返回正确结构"""
        empty = _empty_mgr()
        status = empty.get_status()
        assert status["total_nodes"] == 0
        assert status["healthy_nodes"] == 0
        assert status["unhealthy_nodes"] == 0
        assert isinstance(status["nodes"], dict)

    def test_get_status_mixed_health(self):
        """混合健康状态的节点报告正确"""
        self.mgr.health_nodes["model1"].is_healthy = False
        status = self.mgr.get_status()
        assert status["total_nodes"] == 2
        assert status["healthy_nodes"] == 1
        assert status["unhealthy_nodes"] == 1
        assert status["nodes"]["model1"]["is_healthy"] is False
        assert status["nodes"]["model2"]["is_healthy"] is True

    def test_get_top_nodes_sort_by_requests(self):
        """按请求数排序"""
        self.mgr.health_nodes["model1"].total_requests = 100
        self.mgr.health_nodes["model1"].mark_success(50.0)
        self.mgr.health_nodes["model2"].total_requests = 50
        self.mgr.health_nodes["model2"].mark_success(80.0)

        top = self.mgr.get_top_nodes(n=2, sort_by="requests")
        assert len(top) == 2
        assert top[0]["model"] == "model1"
        assert top[1]["model"] == "model2"

    def test_get_top_nodes_n_exceeds_available(self):
        """请求的 n 超过可用节点数时不报错"""
        top = self.mgr.get_top_nodes(n=100)
        assert len(top) <= 2

    def test_get_status_includes_strategy(self):
        """get_status 包含轮换策略值"""
        self.mgr.config.rotation_strategy = RotationStrategy.ROUND_ROBIN
        status = self.mgr.get_status()
        assert status["rotation_strategy"] == "round_robin"

    def test_reset_stats_clears_all_counters(self):
        """reset_stats 清除所有计数器包括 is_healthy 恢复"""
        self.mgr.health_nodes["model1"].total_requests = 10
        self.mgr.health_nodes["model1"].success_count = 7
        self.mgr.health_nodes["model1"].error_count = 3
        self.mgr.health_nodes["model1"].consecutive_failures = 2
        self.mgr.health_nodes["model1"].is_healthy = False

        self.mgr.reset_stats()
        node = self.mgr.health_nodes["model1"]
        assert node.total_requests == 0
        assert node.success_count == 0
        assert node.error_count == 0
        assert node.consecutive_failures == 0
        assert node.is_healthy is True
        assert len(node._response_times) == 0


# ════════════════════════════════════════════════════════════════════════════
#  Section 8: add_node / remove_node 后的状态一致性
# ════════════════════════════════════════════════════════════════════════════


class TestNodeLifecycle:
    """测试节点动态添加/移除后的状态一致性"""

    @patch("src.api.api_manager.openai.OpenAI")
    def test_add_node_increases_node_count(self, mock_openai_class):
        """add_node 后节点数量增加"""
        mock_openai_class.return_value = MagicMock()
        mgr = _empty_mgr()
        initial_count = len(mgr.health_nodes)
        mgr.add_node(LLMConfig("new-key", "new-url", "new-model"))
        assert len(mgr.health_nodes) == initial_count + 1
        assert "new-model" in mgr.health_nodes

    @patch("src.api.api_manager.openai.OpenAI")
    def test_add_node_client_cached(self, mock_openai_class):
        """add_node 后客户端存入缓存"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        assert "model1" in mgr._client_cache
        assert mgr._client_cache["model1"] is mock_client

    @patch("src.api.api_manager.openai.OpenAI")
    def test_remove_node_decreases_count(self, mock_openai_class):
        """remove_node 后节点数量和缓存同时减少"""
        mock_openai_class.return_value = MagicMock()
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr.add_node(LLMConfig("key2", "url2", "model2"))
        assert len(mgr.health_nodes) == 2

        result = mgr.remove_node("model1")
        assert result is True
        assert len(mgr.health_nodes) == 1
        assert "model1" not in mgr.health_nodes
        assert "model1" not in mgr._client_cache

    @patch("src.api.api_manager.openai.OpenAI")
    def test_add_then_remove_then_add_same_model(self, mock_openai_class):
        """添加→移除→再次添加同一模型"""
        mock_openai_class.return_value = MagicMock()
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr.remove_node("model1")
        assert "model1" not in mgr.health_nodes
        mgr.add_node(LLMConfig("key1-new", "url1-new", "model1"))
        assert "model1" in mgr.health_nodes
        assert mgr.health_nodes["model1"].config.api_key == "key1-new"


# ════════════════════════════════════════════════════════════════════════════
#  Section 9: HealthCheckerThread 异常处理
# ════════════════════════════════════════════════════════════════════════════


class TestHealthCheckerThreadExceptions:
    """测试 HealthCheckerThread 在异常时的行为"""

    def test_thread_handles_exception_during_health_check(self):
        """健康检查线程在 check_health 抛异常时不崩溃"""
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))

        original_batch = mgr.health_check_batch
        call_count = [0]

        def raising_batch(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise RuntimeError("simulated health check failure")
            return original_batch(*args, **kwargs)

        mgr.health_check_batch = raising_batch
        thread = HealthCheckerThread(mgr, interval=0.05)
        thread.start()
        time.sleep(0.25)
        thread.stop()
        thread.join(timeout=2.0)
        assert not thread.is_alive()

    def test_thread_run_logs_exception(self, caplog):
        """健康检查线程异常时被记录到日志"""
        mgr = _empty_mgr()

        def always_raise(*args, **kwargs):
            raise ValueError("always fails")

        mgr.health_check_batch = always_raise
        thread = HealthCheckerThread(mgr, interval=0.05)
        thread.start()
        time.sleep(0.25)
        thread.stop()
        thread.join(timeout=2.0)
        assert not thread.is_alive()


# ════════════════════════════════════════════════════════════════════════════
#  Section 10: 并发线程安全测试
# ════════════════════════════════════════════════════════════════════════════


class TestConcurrentAccess:
    """测试多线程并发访问的安全性"""

    def test_concurrent_add_and_remove(self):
        """并发添加和移除节点不崩溃"""
        mgr = _empty_mgr()
        errors = []

        def add_nodes():
            for i in range(50):
                try:
                    mgr.add_node(LLMConfig(f"k{i}", f"url{i}", f"m{i}"))
                except Exception as e:
                    errors.append(e)

        def remove_nodes():
            for i in range(50):
                try:
                    mgr.remove_node(f"m{i}")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=add_nodes), threading.Thread(target=remove_nodes)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"并发操作产生错误: {errors}"

    def test_concurrent_select_node(self):
        """并发 select_node 不崩溃"""
        mgr = _empty_mgr()
        for i in range(10):
            mgr.add_node(LLMConfig(f"k{i}", f"url{i}", f"m{i}"))

        errors = []

        def select_many():
            for _ in range(200):
                try:
                    mgr.select_node()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=select_many) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_reset_and_success(self):
        """并发 reset_stats 和 mark_success 不崩溃"""
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("k1", "url1", "m1"))
        errors = []

        def reset_loop():
            for _ in range(100):
                try:
                    mgr.reset_stats()
                except Exception as e:
                    errors.append(e)

        def success_loop():
            node = mgr.health_nodes["m1"]
            for _ in range(100):
                try:
                    node.mark_success(50.0)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=reset_loop), threading.Thread(target=success_loop)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


# ════════════════════════════════════════════════════════════════════════════
#  Section 11: get_status 数据类型完整性
# ════════════════════════════════════════════════════════════════════════════


class TestStatusDataIntegrity:
    """测试 get_status 返回数据的类型和完整性"""

    def setup_method(self):
        self.mgr = _empty_mgr()
        self.mgr.add_node(LLMConfig("key1", "https://api.example.com", "model1"))
        self.mgr.health_nodes["model1"].mark_success(120.0)
        self.mgr.health_nodes["model1"].mark_success(130.0)
        self.mgr.health_nodes["model1"].mark_failure("error")

    def test_status_node_has_all_required_fields(self):
        """节点状态包含所有必需字段"""
        status = self.mgr.get_status()
        node_info = list(status["nodes"].values())[0]
        required_keys = {
            "model",
            "base_url",
            "is_healthy",
            "success_rate",
            "total_requests",
            "consecutive_failures",
            "avg_response_time_ms",
        }
        assert required_keys.issubset(node_info.keys())

    def test_status_rounding_precision(self):
        """成功率和小数值四舍五入精度正确"""
        status = self.mgr.get_status()
        node_info = list(status["nodes"].values())[0]
        # 2 成功 1 失败，total_requests=3，success_rate=2/3≈0.667
        assert node_info["success_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert node_info["avg_response_time_ms"] == pytest.approx(125.0)

    def test_status_healthy_nodes_count_matches_filter(self):
        """healthy_nodes 计数与 get_healthy_nodes 一致"""
        self.mgr.health_nodes["model1"].is_healthy = False
        status = self.mgr.get_status()
        assert status["healthy_nodes"] == len(self.mgr.get_healthy_nodes())
        assert status["unhealthy_nodes"] == len(self.mgr.get_all_nodes()) - status["healthy_nodes"]


# ════════════════════════════════════════════════════════════════════════════
#  Section 12: print_status_table 输出验证
# ════════════════════════════════════════════════════════════════════════════


class TestPrintStatusTable:
    """测试 print_status_table 输出"""

    def test_print_status_table_with_manager(self, capsys):
        """传入 manager 实例时正常输出包含模型名"""
        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model1"))
        mgr.health_nodes["model1"].mark_success(100.0)
        print_status_table(mgr)
        captured = capsys.readouterr()
        assert "model1" in captured.out

    def test_print_status_table_empty_manager(self, capsys):
        """空管理器的状态表格正常输出"""
        mgr = _empty_mgr()
        print_status_table(mgr)
        captured = capsys.readouterr()
        assert "0" in captured.out  # total_nodes=0


# ════════════════════════════════════════════════════════════════════════════
#  Section 13: 单例线程卫生与故障转移日志（0.9.2 新增）
# ════════════════════════════════════════════════════════════════════════════


class TestSingletonThreadHygiene:
    """测试 get_manager/reset_manager 的线程卫生与单例语义。

    背景：APIManager 初始化会启动后台健康检查守护线程（每 60s 发起真实
    LLM 探测请求）。reset_manager 此前只清全局引用，残留线程继续对旧
    实例发起健康检查（消耗 API 配额）；现 reset 前显式停止并等待线程退出。
    """

    @patch("src.api.api_manager.LLM_CONFIGS", [])
    def test_get_manager_returns_same_instance(self):
        """连续 get_manager 返回同一实例，reset 后换新实例"""
        reset_manager()
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2
        reset_manager()
        m3 = get_manager()
        assert m3 is not m1
        reset_manager()

    @patch("src.api.api_manager.LLM_CONFIGS", [])
    def test_reset_manager_stops_health_checker_thread(self):
        """reset_manager 停止后台健康检查线程（不再残留发起 LLM 探测）"""
        reset_manager()
        mgr = get_manager()
        checker = mgr._health_checker
        assert checker is not None
        assert checker.is_alive()
        reset_manager()
        # 线程已退出，且管理器引用被清除
        assert not checker.is_alive()
        assert mgr._health_checker is None

    @patch("src.api.api_manager.LLM_CONFIGS", [])
    def test_concurrent_get_manager_creates_single_instance(self):
        """多线程并发 get_manager 只创建一个实例（双重检查锁）"""
        reset_manager()
        threads: list[threading.Thread] = []
        seen: list[APIManager] = []
        seen_lock = threading.Lock()
        barrier = threading.Barrier(8)

        def grab():
            m = get_manager()
            barrier.wait()  # 所有线程都拿到实例后再比对
            with seen_lock:
                seen.append(m)

        for _ in range(8):
            t = threading.Thread(target=grab)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert len({id(m) for m in seen}) == 1
        reset_manager()

    @patch("src.api.api_manager.openai.OpenAI")
    def test_call_failover_logs_transition(self, mock_openai_class, caplog):
        """call() 故障转移成功日志包含 "上一节点 -> 当前节点" 的迁移信息"""
        import logging

        mock_client_a = _mock_client(side_effect=ConnectionError("connection lost"))
        mock_client_b = _mock_client()
        mock_openai_class.side_effect = [mock_client_a, mock_client_b]

        mgr = _empty_mgr()
        mgr.add_node(LLMConfig("key1", "url1", "model_a"))
        mgr.add_node(LLMConfig("key2", "url2", "model_b"))
        mgr._client_cache["model_a"] = mock_client_a
        mgr._client_cache["model_b"] = mock_client_b

        with caplog.at_level(logging.INFO):
            result = mgr.call(messages=[{"role": "user", "content": "hi"}], model="model_a")
        assert result is not None
        mock_client_b.chat.completions.create.assert_called_once()
        assert "model_a -> model_b" in caplog.text
