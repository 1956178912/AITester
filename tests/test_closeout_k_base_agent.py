"""KB 覆盖率收口：`src/agents/base_agent.py` 的缓存分层 / 限流 / 预算 / 截断分支。

动机：base_agent 补口前 44 行未覆盖，缺口集中在**故障与降级路径**——进程内
LRU 的负缓存与淘汰、预算超限快速失败、限流（429）退避、空响应重试、缓存文件
原子写失败清理、语义缓存 upsert 失败静默、复杂度路由重排、AST 聚焦超预算保留。
这些路径"平时不走，走的时候正是线上出问题的时候"，未覆盖等于降级口径未验证。

纪律：零 LLM、零网络、零真实等待。`_call_llm` 用 fake 客户端替换（`invoke`
返回 `SimpleNamespace`）；`time.sleep` 只在限流用例里被 monkeypatch 成记录器
（同时断言"等待时长"这一语义，而非真等待）；缓存目录一律指向 `tmp_path`。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import config as config_mod
from src.agents import base_agent
from src.agents.base_agent import BaseAgent, clear_llm_lru_cache
from src.budget.cost_budget import BudgetExceededError

_CFG = [("key-1", "https://api.example.com/v1", "model-1")]


@pytest.fixture(autouse=True)
def _clean_lru() -> Any:
    """逐测试清空进程内 LRU（含负缓存），避免跨用例键复用造成假命中。"""
    clear_llm_lru_cache()
    yield
    clear_llm_lru_cache()


def _agent() -> BaseAgent:
    return BaseAgent(system_prompt="你是单元测试用智能体。")


def _fake_response(content: str = "LLM 输出", finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(content=content, response_metadata={"finish_reason": finish_reason}, usage_metadata=None)


def _patch_llm(monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace) -> dict[str, int]:
    """把 LLM 客户端整链替换为返回固定响应的 fake，返回调用计数表。"""
    calls = {"invoke": 0}

    def _invoke(messages, **kwargs):
        calls["invoke"] += 1
        return response

    client = SimpleNamespace(invoke=_invoke)
    monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: client)
    monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
    return calls


def _enable_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """打开文件缓存并指向 tmp_path（不写宿主 ~/.cache）。"""
    cache_dir = tmp_path / "llm_cache"
    monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: True)
    monkeypatch.setattr(base_agent, "_llm_cache_dir", lambda: str(cache_dir))
    return cache_dir


@pytest.mark.unit
class TestLruPrimitives:
    """进程内 LRU 的三个原语（负缓存 TTL / 容量淘汰 / token 记账）。"""

    def test_negative_cache_hit_within_ttl(self):
        key = ("/tmp/x.json", "prompt", None)
        base_agent._lru_store(key, None)
        assert base_agent._lru_check_negative(key) is True
        # 负缓存命中不改变"无正值"语义
        assert base_agent._lru_lookup(key) is None

    def test_negative_cache_expires_and_is_removed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_LRU_NEGATIVE_TTL_SECONDS", 0.0)
        key = ("/tmp/y.json", "prompt", None)
        base_agent._lru_store(key, None)
        assert base_agent._lru_check_negative(key) is False
        # 过期条目已惰性删除：再查仍是 False（而非重新命中）
        assert base_agent._lru_check_negative(key) is False

    def test_positive_store_clears_negative_and_records_tokens(self):
        key = ("/tmp/z.json", "prompt", 0.3)
        base_agent._lru_store(key, None)  # 先记负缓存
        base_agent._lru_store(key, "response", tokens=42)
        assert base_agent._lru_check_negative(key) is False
        assert base_agent._lru_lookup(key) == "response"
        assert base_agent._lru_lookup_tokens(key) == 42

    def test_positive_lru_evicts_oldest_when_over_capacity(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_LRU_MAXSIZE", 2)
        keys = [(f"/tmp/e{i}.json", f"p{i}", None) for i in range(3)]
        for i, key in enumerate(keys):
            base_agent._lru_store(key, f"v{i}")
        assert base_agent._lru_lookup(keys[0]) is None, "最久未使用条目应被淘汰"
        assert base_agent._lru_lookup(keys[2]) == "v2"
        assert base_agent._lru_lookup_tokens(keys[2]) == 0


@pytest.mark.unit
class TestBudgetAndRoutingHelpers:
    """预算异常工厂与复杂度路由重排的降级口径。"""

    def test_budget_exceeded_error_carries_stats(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.budget.cost_budget.get_budget_stats",
            lambda: {"consumed_tokens": 77, "token_limit": 3, "unit": "tokens"},
        )
        err = base_agent._budget_exceeded_error()
        assert isinstance(err, BudgetExceededError)
        assert (err.consumed, err.limit, err.unit) == (77, 3, "tokens")
        assert "LLM 预算耗尽" in str(err)

    def test_reorder_cost_weight_lookup_failure_falls_back_to_stable_order(self, monkeypatch: pytest.MonkeyPatch):
        """cost_weight 读取异常 → 全部按 1.0 处理（稳定排序保留插入序）。"""

        class _BadConfig:
            model_name = "model-1"

            @property
            def cost_weight(self):
                raise RuntimeError("配置对象损坏（模拟）")

        monkeypatch.setattr(config_mod, "LLM_CONFIGS", [_BadConfig()])
        api_groups = {
            "https://a.example.com/v1": [("k1", "model-1")],
            "https://b.example.com/v1": [("k2", "model-1")],
        }
        out = base_agent._reorder_api_groups_by_complexity(api_groups, list(_CFG), "complex")
        assert list(out) == list(api_groups)
        assert out["https://a.example.com/v1"] == [("k1", "model-1")]


@pytest.mark.unit
class TestCacheDisabledPassthrough:
    """缓存关闭时的四条透传分支（保持温度/复杂度/JSON 模式参数不丢失）。"""

    def test_complexity_and_temperature_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: False)
        agent = _agent()
        seen: dict[str, Any] = {}

        def fake_llm(user_message, max_retries=None, **kwargs):
            seen.update(kwargs)
            return "透传结果"

        monkeypatch.setattr(agent, "_call_llm", fake_llm)
        out = agent._call_llm_with_cache("问题", temperature=0.3, complexity_class="complex", json_mode=True)
        assert out == "透传结果"
        assert seen == {"temperature": 0.3, "complexity_class": "complex", "json_mode": True}

    def test_complexity_only_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: False)
        agent = _agent()
        seen: dict[str, Any] = {}

        def fake_llm(user_message, max_retries=None, **kwargs):
            seen.update(kwargs)
            return "结果"

        monkeypatch.setattr(agent, "_call_llm", fake_llm)
        assert agent._call_llm_with_cache("问题", complexity_class="simple") == "结果"
        assert seen == {"complexity_class": "simple"}

    def test_temperature_only_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: False)
        agent = _agent()
        seen: dict[str, Any] = {}

        def fake_llm(user_message, max_retries=None, **kwargs):
            seen.update(kwargs)
            return "结果"

        monkeypatch.setattr(agent, "_call_llm", fake_llm)
        assert agent._call_llm_with_cache("问题", temperature=0.9) == "结果"
        assert seen == {"temperature": 0.9}

    def test_cache_disabled_by_default_strips_json_mode_when_false(self, monkeypatch: pytest.MonkeyPatch):
        """json_mode=False 时不透传该 kwarg（请求签名与历史逐字节一致）。"""
        monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: False)
        agent = _agent()
        seen: dict[str, Any] = {}

        def fake_llm(user_message, max_retries=None, **kwargs):
            seen.update(kwargs)
            return "结果"

        monkeypatch.setattr(agent, "_call_llm", fake_llm)
        assert agent._call_llm_with_cache("问题") == "结果"
        assert seen == {}


@pytest.mark.unit
class TestRogueMonitorSidepath:
    """R16 流氓行为监控是观测旁路：上报异常不得影响 LLM 主链路。"""

    def test_monitor_failure_does_not_block_call(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "rogue_monitor_enabled", lambda: True)
        monkeypatch.setattr(base_agent, "_llm_cache_enabled", lambda: False)
        monkeypatch.setattr(
            "src.agents.rogue_monitor.get_rogue_monitor",
            lambda: (_ for _ in ()).throw(RuntimeError("监控单例损坏（模拟）")),
        )
        agent = _agent()
        monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: "主链路仍成功")
        assert agent._call_llm_with_cache("问题") == "主链路仍成功"


@pytest.mark.unit
class TestFileCachePaths:
    """文件缓存开启后的写文件 / 隔离键 / 负缓存 / 失败降级路径。"""

    def test_model_isolation_key_written_then_file_hit(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        cache_dir = _enable_cache(monkeypatch, tmp_path)
        monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", "1")
        monkeypatch.delenv("AITESTER_CACHE_NAMESPACE", raising=False)
        monkeypatch.setattr("src.agents.llm_client.get_first_valid_model_name", lambda: "model-x")
        calls = _patch_llm(monkeypatch, _fake_response("隔离缓存响应"))
        agent = _agent()

        assert agent._call_llm_with_cache("隔离键问题") == "隔离缓存响应"
        assert calls["invoke"] == 1
        expected_hash = hashlib.md5(
            f"隔离键问题\x00{agent.system_prompt}\x00mmodel-x".encode(),
        ).hexdigest()[:16]
        cache_file = Path(cache_dir) / f"{expected_hash}.json"
        assert cache_file.exists(), "M8 隔离键应参与缓存文件名哈希"
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        assert payload["response"] == "隔离缓存响应"
        assert payload["prompt"] == "隔离键问题"

        # 清空进程内 LRU 后重放：应命中隔离键文件，不再真实调用 LLM
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("隔离键问题") == "隔离缓存响应"
        assert calls["invoke"] == 1

    def test_negative_cache_hit_skips_file_read(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog):
        cache_dir = _enable_cache(monkeypatch, tmp_path)
        _patch_llm(monkeypatch, _fake_response("负缓存后仍真实调用"))
        agent = _agent()
        message = "负缓存问题"
        expected_hash = hashlib.md5(f"{message}\x00{agent.system_prompt}".encode()).hexdigest()[:16]
        cache_file = os.path.normpath(os.path.join(str(cache_dir), f"{expected_hash}.json"))
        base_agent._lru_store((cache_file, message, None), None)

        with caplog.at_level(logging.DEBUG, logger="src.agents.base_agent"):
            out = agent._call_llm_with_cache(message)
        assert out == "负缓存后仍真实调用"
        assert "负缓存命中（跳过文件重读）" in caplog.text

    def test_cache_miss_complexity_and_temperature_branches(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("未命中调用"))
        agent = _agent()
        assert agent._call_llm_with_cache("温度问题", temperature=0.4, complexity_class="simple") == "未命中调用"
        assert agent._call_llm_with_cache("复杂度问题", complexity_class="simple") == "未命中调用"
        assert calls["invoke"] == 2

    def test_atomic_write_failure_cleans_tmp_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        cache_dir = _enable_cache(monkeypatch, tmp_path)
        _patch_llm(monkeypatch, _fake_response("写失败仍返回"))
        agent = _agent()
        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("磁盘满（模拟）")))
        assert agent._call_llm_with_cache("原子写失败问题") == "写失败仍返回"
        leftover = [p.name for p in Path(cache_dir).glob("*.tmp.*")] if cache_dir.exists() else []
        assert leftover == [], f"replace 失败必须清理临时文件，残留={leftover}"

    def test_semantic_upsert_failure_is_silent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog):
        _enable_cache(monkeypatch, tmp_path)
        _patch_llm(monkeypatch, _fake_response("语义索引失败仍返回"))
        # 读路径 stats 置为 disabled（本用例只验证"写成功后 upsert 异常"的静默降级）
        monkeypatch.setattr("src.agents.semantic_cache.get_semantic_cache_stats", lambda: {"enabled": False})
        monkeypatch.setattr("src.agents.semantic_cache._semantic_cache_enabled", lambda: True)
        monkeypatch.setattr(
            "src.agents.semantic_cache.get_semantic_index",
            lambda: SimpleNamespace(upsert=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("索引损坏（模拟）"))),
        )
        agent = _agent()
        with caplog.at_level(logging.DEBUG, logger="src.agents.base_agent"):
            assert agent._call_llm_with_cache("语义 upsert 失败问题") == "语义索引失败仍返回"
        assert "语义缓存 upsert 失败" in caplog.text

    def test_cache_write_outer_failure_is_silent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog):
        """ensure_llm_cache_dir 抛错 → 整个写缓存块降级，不影响返回值。"""
        _enable_cache(monkeypatch, tmp_path)
        _patch_llm(monkeypatch, _fake_response("目录创建失败仍返回"))
        monkeypatch.setattr(
            "src.agents.llm_client.ensure_llm_cache_dir",
            lambda cache_dir: (_ for _ in ()).throw(OSError("目录不可写（模拟）")),
        )
        agent = _agent()
        with caplog.at_level(logging.DEBUG, logger="src.agents.base_agent"):
            assert agent._call_llm_with_cache("缓存目录失败问题") == "目录创建失败仍返回"
        assert "缓存写入失败" in caplog.text


@pytest.mark.unit
class TestCallLlmFaults:
    """`_call_llm` 的预算 / 路由 / 空响应 / 限流退避分支。"""

    def test_budget_exceeded_raises_before_calling(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
        monkeypatch.setattr("src.budget.cost_budget.is_budget_exceeded", lambda: True)
        monkeypatch.setattr(
            "src.budget.cost_budget.get_budget_stats",
            lambda: {"consumed_tokens": 5000, "token_limit": 1000, "unit": "tokens"},
        )
        agent = _agent()
        with pytest.raises(BudgetExceededError) as exc_info:
            agent._call_llm("问题")
        assert (exc_info.value.consumed, exc_info.value.limit) == (5000, 1000)

    def test_complexity_routing_reorders_api_groups(self, monkeypatch: pytest.MonkeyPatch):
        configs = [("k1", "https://a.example.com/v1", "model-1"), ("k2", "https://a.example.com/v1", "model-2")]
        _patch_llm(monkeypatch, _fake_response("路由后成功"))
        # 必须在 _patch_llm 之后覆盖（它会把配置链重置为单实例）
        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(configs))
        seen: dict[str, Any] = {}

        def fake_reorder(api_groups, all_configs, complexity_class):
            seen.update({"groups": api_groups, "configs": all_configs, "complexity": complexity_class})
            return api_groups

        monkeypatch.setattr(base_agent, "_reorder_api_groups_by_complexity", fake_reorder)
        agent = _agent()
        assert agent._call_llm("问题", complexity_class="complex") == "路由后成功"
        assert seen["complexity"] == "complex"
        assert seen["configs"] == configs

    def test_empty_response_exhausts_retries_and_raises(self, monkeypatch: pytest.MonkeyPatch):
        _patch_llm(monkeypatch, _fake_response(""))
        agent = _agent()
        with pytest.raises(RuntimeError) as exc_info:
            agent._call_llm("问题", max_retries=0)
        assert "已尝试所有 API" in str(exc_info.value)
        assert "LLM 返回空响应" in str(exc_info.value)

    def test_rate_limit_waits_retry_after_then_fails_over(self, monkeypatch: pytest.MonkeyPatch, caplog):
        class _RateLimitedError(RuntimeError):
            status_code = 429
            response = SimpleNamespace(headers={"retry-after": "7"})

        def _raise(messages, **kwargs):
            raise _RateLimitedError("429 Too Many Requests")

        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
        monkeypatch.setattr(
            base_agent,
            "_get_or_create_chat_client",
            lambda *a, **k: SimpleNamespace(invoke=_raise),
        )
        # 单次直调：真实 _retry_with_exponential_backoff 会把 429 异常包成
        # RuntimeError（原始 response 头信息丢失），本用例验证的是外层
        # _call_llm 的 Retry-After 解析，故绕过包装器直接抛原始异常。
        monkeypatch.setattr(base_agent, "_retry_with_exponential_backoff", lambda func, max_retries, **kw: func())
        sleeps: list[float] = []
        monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))
        agent = _agent()
        with (
            caplog.at_level(logging.WARNING, logger="src.agents.base_agent"),
            pytest.raises(RuntimeError, match="已尝试所有 API"),
        ):
            agent._call_llm("问题", max_retries=0)
        assert sleeps == [7.0], f"应按 Retry-After=7s 等待一次，实际={sleeps}"
        assert "O15 限流（429）" in caplog.text
        assert "Retry-After=7.0s" in caplog.text

    def test_rate_limit_without_retry_after_uses_floor_wait(self, monkeypatch: pytest.MonkeyPatch):
        class _RateLimitedError(RuntimeError):
            status_code = 429

        def _raise(messages, **kwargs):
            raise _RateLimitedError("429 Too Many Requests")

        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
        monkeypatch.setattr(
            base_agent,
            "_get_or_create_chat_client",
            lambda *a, **k: SimpleNamespace(invoke=_raise),
        )
        sleeps: list[float] = []
        monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))
        agent = _agent()
        with pytest.raises(RuntimeError, match="已尝试所有 API"):
            agent._call_llm("问题", max_retries=0)
        assert sleeps == [2.0], "未设 Retry-After 时应退避到基础等待 2s"

    def test_abnormal_finish_reason_retried_as_failure(self, monkeypatch: pytest.MonkeyPatch):
        """finish_reason=length（截断）属可恢复失败：不得把残缺内容交给下游。"""
        _patch_llm(monkeypatch, _fake_response("残缺内", finish_reason="length"))
        agent = _agent()
        with pytest.raises(RuntimeError) as exc_info:
            agent._call_llm("问题", max_retries=0)
        assert "finish_reason=length" in str(exc_info.value)


@pytest.mark.unit
class TestTruncateCodeFocusOverBudget:
    """AST 聚焦结果超预算但焦点已解析 → 保留聚焦+契约块，不做头尾硬截断。"""

    def test_focus_resolved_over_budget_returns_focused_code(self):
        from src.tools.code_context import extract_focused_code_detail

        body = "\n".join(f"    x{i} = {i}" for i in range(40))
        code = "import os\n\n\ndef long_fn(a):\n" + body + "\n    return a\n"
        focused, resolved = extract_focused_code_detail(code, focus_function="long_fn", max_chars=100)
        assert resolved is True
        assert len(focused) > 100, "前置条件：聚焦结果必须超预算"
        out = BaseAgent.truncate_code(code, max_chars=100, focus_function="long_fn")
        assert out == focused, "焦点已解析时返回聚焦结果本身（不追加字符级截断标记）"
        assert "[代码已截断" not in out
        assert "def long_fn(a):" in out
