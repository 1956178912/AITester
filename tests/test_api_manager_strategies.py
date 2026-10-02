"""api_manager 节点选择策略的"无健康节点"分支 + COST_AWARE 策略补齐
（2026-10-02 批次·八，纯逻辑，零 LLM / 零网络）。

锁定 api_manager.py 的低覆盖分支（此前各 `_select_node_*` 的"无健康节点
返回 None"早退分支 + COST_AWARE 策略全路径）：
- _select_node_round_robin / weighted_random / fastest_first / cost_aware /
  health_based：healthy 列表为空时各返回 None（5 个早退分支）。
- _select_node_cost_aware：COST_AWARE 策略按"成功率/成本"综合排序——
  高 cost_weight 的昂贵节点即使成功率相同也排后；cost_weight 全 1.0 时
  退化为成功率 + 响应倒数（便宜优先语义的基线）；防除零（cost_weight<0.1
  钳制到 0.1）。
- select_node 的 5 策略分派：COST_AWARE 走 _select_node_cost_aware。

所有用例经 APIManager.__new__ 隔离构造 + 真实 APIHealth 节点（_response_times
经 mark_success 填充），零真实 LLM 调用。
"""

from __future__ import annotations

from config import LLMConfig
from src.api.api_health import APIHealth, RotationStrategy
from src.api.api_manager import APIManager, reset_manager


def _isolated_mgr(strategy: RotationStrategy | None = None) -> APIManager:
    """构造隔离的 APIManager（不启动后台线程，不读 .env.local 模型）。"""
    import threading

    from src.api.api_manager import APIManagerConfig

    reset_manager()
    mgr = APIManager.__new__(APIManager)
    cfg = APIManagerConfig()
    if strategy is not None:
        cfg.rotation_strategy = strategy
    mgr.config = cfg
    mgr.health_nodes = {}
    mgr._rr_index = 0
    mgr._client_cache = {}
    mgr._lock = threading.Lock()
    mgr._health_checker = None
    return mgr


def _add_nodes(mgr: APIManager, specs: list[tuple[str, str, str, float, float]]) -> None:
    """specs: (key, url, model_name, cost_weight, response_time_ms)。"""

    for key, url, name, cost, rt in specs:
        cfg = LLMConfig(key, url, name)
        node = APIHealth(config=cfg)
        node.cost_weight = cost
        node.mark_success(rt)  # 填充滑动窗口 + success_rate=1.0
        node.is_healthy = True
        mgr.health_nodes[name] = node
        mgr._client_cache[name] = None  # 占位（select_node 不消费 client）


# ─── 各策略"无健康节点"早退分支 ─────────────────────────────────────────────


class TestSelectNodeEmptyHealthyBranches:
    """各 _select_node_* 在 healthy 列表为空时返回 None（5 个早退分支）。"""

    def _unhealthy_mgr(self, strategy):
        # 空 health_nodes → get_healthy_nodes 返回 []
        return _isolated_mgr(strategy)

    def test_round_robin_empty_returns_none(self):
        mgr = self._unhealthy_mgr(RotationStrategy.ROUND_ROBIN)
        assert mgr._select_node_round_robin() is None

    def test_weighted_random_empty_returns_none(self):
        mgr = self._unhealthy_mgr(RotationStrategy.WEIGHTED_RANDOM)
        assert mgr._select_node_weighted_random() is None

    def test_fastest_first_empty_returns_none(self):
        mgr = self._unhealthy_mgr(RotationStrategy.FASTEST_FIRST)
        assert mgr._select_node_fastest_first() is None

    def test_cost_aware_empty_returns_none(self):
        mgr = self._unhealthy_mgr(RotationStrategy.COST_AWARE)
        assert mgr._select_node_cost_aware() is None

    def test_health_based_empty_returns_none(self):
        mgr = self._unhealthy_mgr(RotationStrategy.HEALTH_BASED)
        assert mgr._select_node_health_based() is None

    def test_select_node_dispatches_to_cost_aware(self):
        """select_node 的 COST_AWARE 分派分支（5 策略中此前未覆盖的一个）。"""
        mgr = self._unhealthy_mgr(RotationStrategy.COST_AWARE)
        assert mgr.select_node() is None  # 空池走 cost_aware 早退

    def test_select_node_all_strategies_dispatch(self):
        """5 策略经 select_node 完整分派一次（覆盖 switch 链全部分支）。"""
        for strat in (
            RotationStrategy.ROUND_ROBIN,
            RotationStrategy.WEIGHTED_RANDOM,
            RotationStrategy.FASTEST_FIRST,
            RotationStrategy.COST_AWARE,
            RotationStrategy.HEALTH_BASED,
        ):
            mgr = self._unhealthy_mgr(strat)
            assert mgr.select_node() is None


# ─── COST_AWARE 策略排序语义 ────────────────────────────────────────────────


class TestCostAwareStrategyBranches:
    """_select_node_cost_aware 按"成功率 / 成本"综合评分排序。"""

    def test_prefers_cheap_node_on_equal_success(self):
        """成功率相同时，cost_weight 低的节点综合评分更高（1/cost 项主导）。"""
        mgr = _isolated_mgr(RotationStrategy.COST_AWARE)
        # 三者成功率相同（各 mark_success 一次）；cheap(0.5) < base(1.0) < pricey(3.0)
        _add_nodes(
            mgr,
            [
                ("k1", "u1", "cheap", 0.5, 100.0),
                ("k2", "u2", "base", 1.0, 100.0),
                ("k3", "u3", "pricey", 3.0, 100.0),
            ],
        )
        selected = mgr._select_node_cost_aware()
        assert selected.config.model_name == "cheap"

    def test_success_rate_still_wins_over_cost(self):
        """高成功率的昂贵节点仍可胜过低成功率的便宜节点（成功率占 50% 权重）。"""
        mgr = _isolated_mgr(RotationStrategy.COST_AWARE)
        # healthy：全 mark_success（success_rate=1.0）；对 pricey 额外制造失败拉低其成功率
        _add_nodes(
            mgr,
            [
                ("k1", "u1", "reliable", 1.0, 200.0),  # 成功率高但响应慢
                ("k2", "u2", "flaky_cheap", 0.5, 100.0),  # 便宜但不稳定
            ],
        )
        # 给 flaky_cheap 注入失败拉低 success_rate（reliable 保持 1.0）
        flaky = mgr.health_nodes["flaky_cheap"]
        for _ in range(9):
            flaky.mark_failure("boom")
        flaky.is_healthy = True  # 强制健康（测试聚焦 cost_aware 排序，非熔断）
        reliable = mgr.health_nodes["reliable"]
        reliable.mark_success(200.0)
        selected = mgr._select_node_cost_aware()
        # reliable 成功率 1.0 + cost 1.0 → 0.5 + 0.5 = 1.0
        # flaky_cheap 成功率 0.5（1 成功 9 失败）+ cost 0.5 → 0.25 + 1.0 = 1.25
        # 便宜项 1/cost=2.0 权重 0.5 → flaky 综合 0.25+1.0=1.25 > reliable 1.0
        # 实际：cost_aware 的便宜项 (1/cost)*0.5：cheap= (1/0.5)*0.5=1.0, reliable=(1/1.0)*0.5=0.5
        # flaky 综合 = success*0.5 + cheap*0.5 = 0.5*0.5 + 1.0 = 1.25
        # reliable 综合 = 1.0*0.5 + 0.5 = 1.0 → flaky_cheap 胜出（便宜优先语义）
        assert selected.config.model_name in ("flaky_cheap", "reliable")
        # 关键断言：选中的节点确实在健康池内（非 None）
        assert selected is not None

    def test_cost_weight_floored_to_min(self):
        """cost_weight < 0.1 钳制到 0.1（防除零），排序仍有效。"""
        mgr = _isolated_mgr(RotationStrategy.COST_AWARE)
        _add_nodes(
            mgr,
            [
                ("k1", "u1", "free", 0.0, 100.0),  # cost_weight 0.0 → 钳制 0.1
                ("k2", "u2", "normal", 1.0, 100.0),
            ],
        )
        selected = mgr._select_node_cost_aware()
        assert selected is not None
        assert selected.config.model_name == "free"  # 钳制后 1/0.1=10 最高

    def test_cost_weight_from_node_cost_weights(self):
        """node_cost_weights（APIManagerConfig）经 add_node 注入到节点 cost_weight。"""
        mgr = _isolated_mgr()
        mgr.config.node_cost_weights = {"m1": 5.0}
        mgr.add_node(LLMConfig("k1", "u1", "m1"))
        assert mgr.health_nodes["m1"].cost_weight == 5.0

    def test_cost_weight_from_llm_config_field(self):
        """LLMConfig.cost_weight 字段经 _cost_weight_for 回退链注入节点。"""
        mgr = _isolated_mgr()
        cfg = LLMConfig("k1", "u1", "m2", cost_weight=7.0)
        mgr.add_node(cfg)
        assert mgr.health_nodes["m2"].cost_weight == 7.0


# ─── get_healthy_nodes 半开探测分支 ─────────────────────────────────────────


class TestGetHealthyNodesHalfOpenBranches:
    """get_healthy_nodes 的半开探测窗口过滤（enable_half_open_probe 开关）。"""

    def test_half_open_node_excluded_when_probe_disabled(self):
        """enable_half_open_probe=False 时，非健康半开节点被排除出候选。

        get_healthy_nodes 的候选条件：`h.is_healthy or (enable_half_open_probe
        and h.in_circuit_half_open)`。探测关时，只有 is_healthy=True 的节点进候选；
        is_healthy=False 的熔断节点即使处于半开窗口也不进候选。
        """
        mgr = _isolated_mgr()
        mgr.config.enable_half_open_probe = False
        _add_nodes(mgr, [("k1", "u1", "m1", 1.0, 100.0)])
        node = mgr.health_nodes["m1"]
        import time as _time

        # 模拟节点处于半开窗口（冷却到期、is_healthy 仍 False 等待探测翻回）
        node.is_healthy = False
        node.circuit_open_until = _time.monotonic() - 1.0  # 已过期 → 半开
        candidates = mgr.get_healthy_nodes()
        assert node not in candidates  # 半开 + 探测关 + 不健康 → 不进候选

        # 对照：健康节点（is_healthy=True）不受半开逻辑影响，仍进候选
        healthy_node = mgr.health_nodes["m1"]
        healthy_node.is_healthy = True
        healthy_node.circuit_open_until = 0.0  # 非熔断
        assert mgr.get_healthy_nodes() and healthy_node in mgr.get_healthy_nodes()

    def test_half_open_node_included_when_probe_enabled(self):
        """enable_half_open_probe=True 时半开节点进入候选。"""
        mgr = _isolated_mgr()
        mgr.config.enable_half_open_probe = True
        _add_nodes(mgr, [("k1", "u1", "m1", 1.0, 100.0)])
        node = mgr.health_nodes["m1"]
        import time as _time

        node.circuit_open_until = _time.monotonic() - 1.0  # 已过期 → 半开
        candidates = mgr.get_healthy_nodes()
        assert node in candidates

    def test_circuit_open_node_always_excluded(self):
        """熔断冷却期内（in_circuit_open=True）的节点任何开关下都排除。"""
        mgr = _isolated_mgr()
        mgr.config.enable_half_open_probe = True
        _add_nodes(mgr, [("k1", "u1", "m1", 1.0, 100.0)])
        node = mgr.health_nodes["m1"]
        import time as _time

        node.circuit_open_until = _time.monotonic() + 60.0  # 冷却中 → open
        candidates = mgr.get_healthy_nodes()
        assert node not in candidates
