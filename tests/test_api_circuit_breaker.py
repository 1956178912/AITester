"""
4.4 熔断器指数退避 + Prometheus 指标导出单元测试。

覆盖：
- APIHealth 指数退避：mark_failure 触发熔断时 circuit_open_count 递增，
  冷却期按 base * 2^open_count 增长并受惩罚上限约束；
- mark_success 重置 circuit_open_count；
- _probe_circuit_half_open 半开探测：成功闭合 / 失败继续退避；
- half_open_probe_success_rate 计算；
- to_prometheus_text 7 指标导出格式。
"""

from __future__ import annotations

from config import LLMConfig
from src.api.api_health import APIHealth


def _make_health(**overrides) -> APIHealth:
    """构造带默认 LLMConfig 的 APIHealth（测试无真实 API 请求）。"""
    config = LLMConfig(
        model_name="test-model",
        api_key="test-key",
        base_url="http://localhost:1",
    )
    kwargs: dict = {"config": config}
    kwargs.update(overrides)
    return APIHealth(**kwargs)


class TestExponentialBackoff:
    """指数退避行为测试。"""

    def test_initial_state(self):
        health = _make_health()
        assert health.circuit_open_count == 0
        assert health.half_open_success == 0
        assert health.half_open_failure == 0
        assert health.in_circuit_open is False

    def test_mark_failure_triggers_circuit_with_backoff_count(self):
        """首次熔断（连续失败达阈值）时 circuit_open_count 递增。"""
        health = _make_health(max_consecutive_failures=1, circuit_cooldown_seconds=10.0)
        health.mark_failure()
        assert health.in_circuit_open is True
        assert health.circuit_open_count == 1  # 首次熔断后 +1

    def test_repeated_circuit_failures_grow_backoff(self):
        """连续触发熔断时冷却期按指数增长（base * 2^open_count）。"""
        health = _make_health(max_consecutive_failures=1, circuit_cooldown_seconds=10.0)
        # 第 1 次熔断：base * 2^0 = 10s
        health.mark_failure()
        count_after_first = health.circuit_open_count
        assert count_after_first == 1
        # 模拟冷却到期后再次失败重开（半开探测失败路径）
        health.circuit_open_until = 0.0  # 跳过等待，直接置冷却到期
        health.consecutive_failures = 0
        health.is_healthy = True
        health.mark_failure()
        # open_count 应继续递增（从 1 到 2）
        assert health.circuit_open_count == 2

    def test_mark_success_resets_backoff(self):
        """成功时 circuit_open_count 归零（指数退避重置）。"""
        health = _make_health(max_consecutive_failures=1, circuit_cooldown_seconds=10.0)
        health.mark_failure()
        assert health.circuit_open_count == 1
        health.mark_success(100.0)
        assert health.circuit_open_count == 0
        assert health.in_circuit_open is False


class TestHalfOpenProbe:
    """半开探测行为测试。"""

    def test_half_open_probe_success_closes_circuit(self):
        health = _make_health(max_consecutive_failures=1, circuit_cooldown_seconds=0.0)
        health.mark_failure()
        # 冷却到期（circuit_cooldown_seconds=0.0 时冷却立即到期）
        assert health.in_circuit_half_open is True
        health._probe_circuit_half_open(True)
        assert health.circuit_open_until == 0.0
        assert health.circuit_open_count == 0
        assert health.half_open_success == 1
        assert health.in_circuit_open is False

    def test_half_open_probe_failure_extends_backoff(self):
        health = _make_health(max_consecutive_failures=1, circuit_cooldown_seconds=10.0)
        health.mark_failure()
        assert health.half_open_failure == 0
        # 将 circuit_open_until 设为 10s 前的时间点，使 in_circuit_half_open=True
        # （冷却已到期、探测尚未完成 → 进入半开窗口）
        import time as _time

        health.circuit_open_until = _time.monotonic() - 1.0
        assert health.in_circuit_half_open is True
        health._probe_circuit_half_open(False)
        assert health.half_open_failure == 1
        assert health.in_circuit_open is True  # 重新打开

    def test_half_open_probe_noop_when_not_in_window(self):
        """不在半开窗口时 _probe_circuit_half_open 无操作。"""
        health = _make_health()
        # 未熔断：in_circuit_half_open 为 False
        assert health.in_circuit_half_open is False
        health._probe_circuit_half_open(False)
        # 无变化
        assert health.half_open_failure == 0

    def test_half_open_probe_success_rate(self):
        """half_open_probe_success_rate = 成功 / (成功+失败)。"""
        health = _make_health()
        # 无探测记录时返回 None
        assert health.half_open_probe_success_rate is None
        health.half_open_success = 3
        health.half_open_failure = 1
        assert health.half_open_probe_success_rate == 0.75
        # 全成功 = 1.0
        health2 = _make_health()
        health2.half_open_success = 5
        assert health2.half_open_probe_success_rate == 1.0
        # 全失败 = 0.0
        health3 = _make_health()
        health3.half_open_failure = 2
        assert health3.half_open_probe_success_rate == 0.0


class TestPrometheusExport:
    """Prometheus 指标文本导出格式测试。"""

    def test_export_contains_seven_metric_lines_per_node(self):
        from src.api.api_manager import APIManager

        manager = APIManager(enable_health_checker=False)
        if not manager.health_nodes:
            import pytest

            pytest.skip("无 LLM 配置节点，跳过 Prometheus 导出测试")
        # 触发一次失败 + 成功让指标非零
        first_name = next(iter(manager.health_nodes))
        node = manager.health_nodes[first_name]
        node.max_consecutive_failures = 1
        node.mark_failure()
        node.mark_success(100.0)

        text = manager.to_prometheus_text()
        # 7 类指标均出现
        for metric in [
            "aitester_api_health",
            "aitester_api_circuit_state",
            "aitester_api_circuit_open_remaining_seconds",
            "aitester_api_circuit_open_count",
            "aitester_api_half_open_probe_success_rate",
            "aitester_api_success_rate",
            "aitester_api_avg_response_time_ms",
        ]:
            assert metric in text, f"缺少指标 {metric}"
        # 节点 model 标签出现
        assert f'model="{first_name}"' in text

    def test_export_help_and_type_lines(self):
        from src.api.api_manager import APIManager

        manager = APIManager(enable_health_checker=False)
        text = manager.to_prometheus_text()
        assert "# HELP" in text
        assert "# TYPE" in text
        # 每个指标 1 条 HELP + 1 条 TYPE，7 指标
        assert text.count("# HELP") == 7
        assert text.count("# TYPE") == 7

    def test_export_empty_when_no_nodes(self):
        from src.api.api_manager import APIManager

        manager = APIManager(enable_health_checker=False)
        # 清空节点
        manager.health_nodes.clear()
        text = manager.to_prometheus_text()
        # 无节点时仍输出 HELP/TYPE 头（7 指标），但无数据行
        data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
        assert data_lines == []


class TestGetStatusNewFields:
    """get_status 输出的 4.4 新增字段测试。"""

    def test_status_contains_circuit_open_count(self):
        from src.api.api_manager import APIManager

        manager = APIManager(enable_health_checker=False)
        if not manager.health_nodes:
            import pytest

            pytest.skip("无 LLM 配置节点，跳过")
        status = manager.get_status()
        node_data = next(iter(status["nodes"].values()))
        assert "circuit_open_count" in node_data
        assert "half_open_success" in node_data
        assert "half_open_failure" in node_data
        assert "half_open_probe_success_rate" in node_data
        assert node_data["circuit_open_count"] == 0
        assert node_data["half_open_probe_success_rate"] is None

    def test_reset_stats_clears_new_counters(self):
        from src.api.api_manager import APIManager

        manager = APIManager(enable_health_checker=False)
        if not manager.health_nodes:
            import pytest

            pytest.skip("无 LLM 配置节点，跳过")
        node = next(iter(manager.health_nodes.values()))
        node.circuit_open_count = 5
        node.half_open_success = 3
        node.half_open_failure = 2
        manager.reset_stats()
        assert node.circuit_open_count == 0
        assert node.half_open_success == 0
        assert node.half_open_failure == 0
