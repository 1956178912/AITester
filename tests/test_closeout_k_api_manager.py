"""KB 覆盖率收口：`src/api/api_manager.py` 的路由 / 熔断 / 健康检查 / 关闭分支。

动机：api_manager 补口前 29 行未覆盖，全部是"出问题时才走"的路径——熔断冷却
期内健康检查短路、批量检查的停止信号、复杂度路由命中/未命中、单节点空节点
早退、全部候选不可用抛错、后台线程关闭超时告警。这些分支决定故障转移在极端
状态下是否仍按设计收敛，未覆盖即未经演练。

纪律：零真实 LLM / 零网络 / 零后台线程。管理器用 `__new__` 隔离构造（不启动
健康检查线程、不读宿主 .env 模型池）；节点用真实 `APIHealth` + `mark_success`
填充滑动窗口；时间语义只读 `time.monotonic()` 的相对偏移，不 sleep。
"""

from __future__ import annotations

import logging
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from config import LLMConfig
from src.api.api_health import APIHealth, APIManagerConfig
from src.api.api_manager import APIManager, reset_manager

_CFG = LLMConfig("test-key", "https://api.example.com/v1", "model-a")


def _isolated_mgr() -> APIManager:
    """隔离构造 APIManager：不启动后台线程、不初始化真实节点池。"""
    reset_manager()
    mgr = APIManager.__new__(APIManager)
    mgr.config = APIManagerConfig()
    mgr.health_nodes = {}
    mgr._rr_index = 0
    mgr._client_cache = {}
    mgr._lock = threading.Lock()
    mgr._health_checker = None
    return mgr


def _node(name: str, response_time_ms: float = 100.0) -> APIHealth:
    """构造健康节点（mark_success 填充滑动窗口，success_rate=1.0）。"""
    cfg = LLMConfig(f"key-{name}", f"https://{name}.example.com/v1", name)
    node = APIHealth(config=cfg)
    node.mark_success(response_time_ms)
    return node


def _add(mgr: APIManager, *nodes: APIHealth) -> None:
    for node in nodes:
        mgr.health_nodes[node.config.model_name] = node


@pytest.mark.unit
class TestStrategyBranches:
    """各轮换策略的排序分支（fastest_first 此前只有 early-return 被覆盖）。"""

    def test_fastest_first_sorts_by_avg_response_time(self):
        mgr = _isolated_mgr()
        slow = _node("model-a", 500.0)
        fast = _node("model-b", 20.0)
        mid = _node("model-c", 120.0)
        _add(mgr, slow, fast, mid)
        assert mgr._select_node_fastest_first() is fast
        # 排序发生在 get_healthy_nodes 返回的快照列表上（不改变节点池顺序）
        times = [n.avg_response_time_ms for n in (slow, fast, mid)]
        assert times == [500.0, 20.0, 120.0]


@pytest.mark.unit
class TestHealthCheckBranches:
    """健康检查的熔断短路与批量停止信号。"""

    def test_check_health_short_circuits_in_circuit_open(self, caplog: pytest.LogCaptureFixture):
        mgr = _isolated_mgr()
        node = _node("model-a")
        node.circuit_open_until = time.monotonic() + 600.0
        with caplog.at_level(logging.DEBUG, logger="src.api.api_manager"):
            assert mgr.check_health(node) is False
        assert "健康检查跳过（熔断冷却期内，等待半开窗口）" in caplog.text
        # 冷却期内不得发探测请求（客户端缓存未被消费/填充）
        assert mgr._client_cache == {}

    def test_health_check_batch_breaks_on_stop_event(self, monkeypatch: pytest.MonkeyPatch):
        mgr = _isolated_mgr()
        _add(mgr, _node("model-a"), _node("model-b"))
        stop_event = threading.Event()
        stop_event.set()
        mgr._health_checker = SimpleNamespace(  # type: ignore[assignment]
            stop_event=stop_event,
            stop=lambda: None,
            join=lambda timeout=None: None,
        )
        called: list[str] = []

        def _boom(node: APIHealth) -> bool:
            called.append(node.config.model_name)
            return True

        monkeypatch.setattr(mgr, "check_health", _boom)
        assert mgr.health_check_batch(batch_size=1) == {}
        assert called == [], "停止信号已置位时不得再对节点发起真实探测"


@pytest.mark.unit
class TestComplexityRouting:
    """P0 1.2 复杂度感知路由：命中 / 回落 / 排序口径。"""

    def test_build_node_list_complexity_hit_returns_fallback_pool(self):
        mgr = _isolated_mgr()
        cheap = _node("model-cheap", 50.0)
        expensive = _node("model-expensive", 50.0)
        _add(mgr, cheap, expensive)
        mgr.config.node_cost_weights = {"model-cheap": 0.5, "model-expensive": 3.0}
        nodes_to_try, fallback = mgr._build_node_list(None, complexity_class="complex")
        assert [n.config.model_name for n in nodes_to_try] == ["model-expensive"]
        # 命中复杂度路由时必须保留全池备用候选（否则熔断后无故障转移出口）
        assert [n.config.model_name for n in fallback] == ["model-cheap"]

    def test_build_node_list_complexity_miss_falls_back_to_history(self, monkeypatch: pytest.MonkeyPatch):
        mgr = _isolated_mgr()
        monkeypatch.setattr(mgr, "_select_node_by_complexity", lambda complexity_class: None)
        captured: dict[str, Any] = {}

        def _fake_fallback(model: str | None):
            captured["model"] = model
            return [object()], [object()]

        monkeypatch.setattr(mgr, "_fallback_default_nodes", _fake_fallback)
        nodes_to_try, fallback = mgr._build_node_list(None, complexity_class="complex")
        assert captured == {"model": None}
        assert len(nodes_to_try) == 1
        assert len(fallback) == 1

    def test_select_node_by_complexity_no_candidates_returns_none(self):
        mgr = _isolated_mgr()
        node = _node("model-a")
        node.circuit_open_until = time.monotonic() + 600.0
        _add(mgr, node)
        assert mgr._select_node_by_complexity("complex") is None

    def test_select_node_by_complexity_single_candidate_returns_it(self):
        mgr = _isolated_mgr()
        only = _node("model-only")
        _add(mgr, only)
        assert mgr._select_node_by_complexity("complex") is only

    @pytest.mark.parametrize(
        ("complexity_class", "expected"),
        [
            ("complex", "model-expensive"),
            ("simple", "model-cheap"),
            ("medium", "model-normal"),
        ],
    )
    def test_select_node_by_complexity_sorts_by_cost_weight(self, complexity_class: str, expected: str):
        mgr = _isolated_mgr()
        _add(mgr, _node("model-cheap", 50.0), _node("model-expensive", 50.0), _node("model-normal", 50.0))
        mgr.config.node_cost_weights = {"model-cheap": 0.5, "model-expensive": 3.0, "model-normal": 1.0}
        selected = mgr._select_node_by_complexity(complexity_class)
        assert selected is not None
        assert selected.config.model_name == expected


@pytest.mark.unit
class TestCallAndShutdown:
    """call() 全候选不可用抛错 + 后台健康检查线程关闭。"""

    def test_call_raises_when_no_nodes_available(self, monkeypatch: pytest.MonkeyPatch):
        mgr = _isolated_mgr()
        monkeypatch.setattr(mgr, "_build_node_list", lambda model, complexity_class=None: ([], []))
        with pytest.raises(RuntimeError, match="所有 API 节点不可用"):
            mgr.call(messages=[{"role": "user", "content": "hi"}])

    def test_stop_health_checker_no_checker_is_noop(self):
        mgr = _isolated_mgr()
        mgr._stop_health_checker()  # checker=None 时直接返回，不抛异常
        assert mgr._health_checker is None

    def test_stop_health_checker_alive_logs_warning(self, caplog: pytest.LogCaptureFixture):
        mgr = _isolated_mgr()
        mgr._health_checker = SimpleNamespace(  # type: ignore[assignment]
            stop=lambda: None,
            join=lambda timeout=None: None,
            is_alive=lambda: True,
        )
        with caplog.at_level(logging.WARNING, logger="src.api.api_manager"):
            mgr._stop_health_checker()
        assert "健康检查线程未在 5.0s 内退出，交由进程退出清理" in caplog.text
        # join 超时后不得清空引用（口径：残留线程会在批次边界自然退出）
        assert mgr._health_checker is not None
