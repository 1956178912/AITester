"""
3.4 成本感知路由单元测试（COST_AWARE 策略 + 成本告警）。

覆盖：
- RotationStrategy.COST_AWARE 枚举存在；
- APIManagerConfig.node_cost_weights / cost_alert_enabled 默认值；
- _select_node_cost_aware：成功率/成本综合评分，昂贵节点被降权；
- 故障转移到昂贵 provider 时触发成本告警 WARNING；
- cost_alert_enabled=False 时不告警；
- LLMConfig.cost_weight 字段透传（_cost_weight_for 回退链）。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from config import LLMConfig
from src.api.api_manager import (
    _COST_ALERT_THRESHOLD,
    APIHealth,
    APIManager,
    APIManagerConfig,
    RotationStrategy,
)


def _make_manager(strategy: RotationStrategy, cost_weights: dict[str, float] | None = None, alert: bool = True):
    """构造带指定策略与成本权重的 APIManager（不启动健康检查线程）。"""
    cfg = APIManagerConfig(rotation_strategy=strategy, node_cost_weights=cost_weights or {}, cost_alert_enabled=alert)
    return APIManager(config=cfg, enable_health_checker=False)


class TestCostAwareStrategy:
    """COST_AWARE 策略行为。"""

    def test_enum_exists(self):
        assert RotationStrategy.COST_AWARE.value == "cost_aware"

    def test_config_defaults(self):
        cfg = APIManagerConfig()
        assert cfg.node_cost_weights == {}
        assert cfg.cost_alert_enabled is True

    def test_cost_aware_prefers_cheap_when_equal_health(self):
        """两个节点成功率/响应时间相同，成本权重低的应被优先选中。"""
        mgr = _make_manager(RotationStrategy.COST_AWARE, cost_weights={"cheap": 1.0, "expensive": 5.0})
        # 清空 _init_clients 注册的真实节点（测试环境可能配置了 LLM_CONFIGS），
        # 只保留注入的两个受控节点
        mgr.health_nodes.clear()
        for name, cost in [("cheap", 1.0), ("expensive", 5.0)]:
            node = APIHealth(config=LLMConfig("k", "https://x", name), cost_weight=cost)
            node.mark_success(100.0)  # 两者健康状态一致
            mgr.health_nodes[name] = node
            mgr._client_cache[name] = object()
        selected = mgr.select_node()
        assert selected.config.model_name == "cheap"

    def test_cost_aware_no_healthy_returns_none(self):
        mgr = _make_manager(RotationStrategy.COST_AWARE)
        mgr.health_nodes.clear()
        # 仅一个不健康节点 → select_node 应返回 None
        node = APIHealth(config=LLMConfig("k", "https://x", "m1"))
        node.is_healthy = False
        mgr.health_nodes["m1"] = node
        assert mgr.select_node() is None


class TestCostAlert:
    """成本告警行为。"""

    def test_fallback_to_expensive_triggers_warning(self, caplog):
        """故障转移（attempt>0）落到 cost_weight >= 阈值的昂贵节点时记 WARNING。"""
        mgr = _make_manager(RotationStrategy.COST_AWARE, cost_weights={"expensive": _COST_ALERT_THRESHOLD})
        node = APIHealth(config=LLMConfig("k", "https://x", "expensive"), cost_weight=_COST_ALERT_THRESHOLD)
        mgr.health_nodes["expensive"] = node

        # 直接驱动 _try_call_node（attempt=1 模拟故障转移成功），mock 客户端
        mgr._client_cache["expensive"] = _mock_client()
        with caplog.at_level(logging.WARNING):
            mgr._try_call_node(node, [], {}, "expensive", attempt=1, prev_model="cheap")
        assert any("成本告警" in rec.message for rec in caplog.records), caplog.text

    def test_no_alert_when_disabled(self, caplog):
        mgr = _make_manager(RotationStrategy.COST_AWARE, cost_weights={"expensive": _COST_ALERT_THRESHOLD}, alert=False)
        node = APIHealth(config=LLMConfig("k", "https://x", "expensive"), cost_weight=_COST_ALERT_THRESHOLD)
        mgr.health_nodes["expensive"] = node
        mgr._client_cache["expensive"] = _mock_client()
        with caplog.at_level(logging.WARNING):
            mgr._try_call_node(node, [], {}, "expensive", attempt=1, prev_model="cheap")
        assert not any("成本告警" in rec.message for rec in caplog.records)

    def test_no_alert_for_cheap_fallback(self, caplog):
        mgr = _make_manager(RotationStrategy.COST_AWARE, cost_weights={"cheap": 1.0})
        node = APIHealth(config=LLMConfig("k", "https://x", "cheap"), cost_weight=1.0)
        mgr.health_nodes["cheap"] = node
        mgr._client_cache["cheap"] = _mock_client()
        with caplog.at_level(logging.WARNING):
            mgr._try_call_node(node, [], {}, "cheap", attempt=1, prev_model="other")
        assert not any("成本告警" in rec.message for rec in caplog.records)


class TestCostWeightFallback:
    """_cost_weight_for 回退链：node_cost_weights > LLMConfig.cost_weight > 1.0。"""

    def test_explicit_config_wins(self):
        mgr = _make_manager(RotationStrategy.HEALTH_BASED, cost_weights={"m": 3.0})
        assert mgr._cost_weight_for("m") == 3.0

    def test_llmconfig_field_fallback(self):
        mgr = _make_manager(RotationStrategy.HEALTH_BASED)
        mgr.health_nodes["m"] = APIHealth(config=LLMConfig("k", "https://x", "m", cost_weight=2.5))
        assert mgr._cost_weight_for("m") == 2.5

    def test_default_one_when_absent(self):
        mgr = _make_manager(RotationStrategy.HEALTH_BASED)
        assert mgr._cost_weight_for("unknown-model") == 1.0


def _mock_client():
    """构造一个 mock OpenAI 客户端（_try_call_node 只调用 chat.completions.create）。"""
    client = MagicMock()
    # 返回一个带 choices 的响应对象
    resp = MagicMock()
    resp.choices = [MagicMock()]
    client.chat.completions.create.return_value = resp
    return client
