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
        """A09 身份键（含模型/端点/有效温度等）写入文件并在清 LRU 后仍可命中。

        历史测试锁定的是 M8 的"仅 model 名"隔离公式；A09 后缓存键升级为
        规范化有效请求身份（`_effective_request_identity`），模型隔离是其中
        一个身份材料。本用例改为用生产 helper 复算期望路径，并断言 payload
        记录了 request_identity（模型 = 被 patch 的请求链首选 model-1）。
        """
        _enable_cache(monkeypatch, tmp_path)
        monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", "1")
        monkeypatch.delenv("AITESTER_CACHE_NAMESPACE", raising=False)
        monkeypatch.setattr("src.agents.llm_client.get_first_valid_model_name", lambda: "model-x")
        calls = _patch_llm(monkeypatch, _fake_response("隔离缓存响应"))
        agent = _agent()

        assert agent._call_llm_with_cache("隔离键问题") == "隔离缓存响应"
        assert calls["invoke"] == 1
        identity = base_agent._effective_request_identity(None, False, system_prompt=agent.system_prompt)
        # A09：隔离开启时身份含真实请求链首选模型（_patch_llm 的 model-1）
        assert identity["model"] == "model-1"
        cache_file = Path(base_agent._exact_cache_file(identity, "隔离键问题", agent.system_prompt))
        assert cache_file.exists(), "A09 有效请求身份应参与缓存文件名哈希"
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        assert payload["response"] == "隔离缓存响应"
        assert payload["prompt"] == "隔离键问题"
        assert payload["request_identity"] == identity, "payload 必须记录写入时的有效请求身份"

        # 清空进程内 LRU 后重放：应命中身份键文件，不再真实调用 LLM
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("隔离键问题") == "隔离缓存响应"
        assert calls["invoke"] == 1

    def test_negative_cache_hit_skips_file_read(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog):
        _enable_cache(monkeypatch, tmp_path)
        _patch_llm(monkeypatch, _fake_response("负缓存后仍真实调用"))
        agent = _agent()
        message = "负缓存问题"
        identity = base_agent._effective_request_identity(None, False, system_prompt=agent.system_prompt)
        cache_file = os.path.normpath(base_agent._exact_cache_file(identity, message, agent.system_prompt))
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


@pytest.mark.unit
class TestLruAuxiliaryStructureBounds:
    """A23（2026-10-18 第三方审查 P2）：`_lru_tokens` 必须与 `_lru_cache` 同步
    淘汰 / 清空，且受 `_LRU_MAXSIZE` 约束（历史实现 tokens 字典永久增长）。

    M7 验收脚本的等价锁定：`_LRU_MAXSIZE=2` 连续写 3 条后
    `(len(_lru_cache), len(_lru_tokens)) == (2, 2)`（修复前 `2 3`），
    `_lru_clear()` 后 `(0, 0)`（修复前 `0 3`）。
    """

    def test_m7_tokens_evicted_with_cache_and_cleared(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(base_agent, "_LRU_MAXSIZE", 2)
        keys = [(f"file{i}", f"prompt{i}", None) for i in range(3)]
        for i, key in enumerate(keys):
            base_agent._lru_store(key, "response", i + 1)
        # 容量约束：token 字典与正缓存同容量（2 条），不是 3 条
        assert len(base_agent._lru_cache) == 2
        assert len(base_agent._lru_tokens) == 2, "A23：token 记账字典必须随正缓存同步淘汰"
        assert base_agent._lru_lookup_tokens(keys[0]) == 0, "被淘汰条目的 token 记录必须同步移除"
        assert base_agent._lru_lookup_tokens(keys[2]) == 3
        base_agent._lru_clear()
        assert len(base_agent._lru_cache) == 0
        assert len(base_agent._lru_tokens) == 0, "A23：clear 必须同步清空 token 记账字典"

    def test_negative_store_drops_stale_tokens(self):
        """先正后负（文件被外部删除）序列不得残留孤儿 token 记录。"""
        key = ("/tmp/a23.json", "p", None)
        base_agent._lru_store(key, "resp", 7)
        assert base_agent._lru_lookup_tokens(key) == 7
        base_agent._lru_store(key, None)  # 条目转负缓存
        assert base_agent._lru_lookup_tokens(key) == 0


@pytest.mark.unit
class TestA09CacheIdentity:
    """A09（2026-10-18 第三方审查 P1）：精确缓存键 = 规范化有效请求身份。

    锁定：
    - 身份材料（thinking/reasoning/max_output/JSON 实际生效值/默认温度/模型/
      namespace）任一变化 → 不同缓存文件，旧响应不得命中；
    - 旧格式缓存只在"历史默认包络"下只读回退（身份充足时不误命中）。
    """

    def _call(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, message: str) -> tuple[str, int]:
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("身份测试响应"))
        agent = _agent()
        out = agent._call_llm_with_cache(message)
        return out, calls["invoke"]

    def test_thinking_mode_changes_identity_and_blocks_old_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("thinking 身份响应"))
        agent = _agent()
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)  # 默认 disabled
        assert agent._call_llm_with_cache("thinking 问题") == "thinking 身份响应"
        assert calls["invoke"] == 1

        # 切换 thinking 设置（新身份）→ 清 LRU 后同 prompt 必须重新真实调用
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("thinking 问题") == "thinking 身份响应"
        assert calls["invoke"] == 2, "A09：thinking 变化属于不同请求身份，不得命中旧身份缓存"
        # 两个身份各自一个缓存文件，且 payload 记录的身份 thinking 字段不同
        files = list(Path(tmp_path / "llm_cache").glob("*.json"))
        assert len(files) == 2
        identities = [json.loads(p.read_text(encoding="utf-8"))["request_identity"] for p in files]
        assert {json.dumps(i["thinking"], sort_keys=True) for i in identities} == {
            json.dumps({"type": "disabled"}, sort_keys=True),
            json.dumps({"type": "enabled"}, sort_keys=True),
        }

    def test_max_output_tokens_changes_identity(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("max_output 身份响应"))
        agent = _agent()
        monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
        assert agent._call_llm_with_cache("max_output 问题") == "max_output 身份响应"
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "123")
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("max_output 问题") == "max_output 身份响应"
        assert calls["invoke"] == 2, "A09：max_tokens 变化属于不同请求身份"
        identity = base_agent._effective_request_identity(None, False)
        assert identity["max_tokens"] == 123

    def test_effective_default_temperature_changes_identity(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("温度身份响应"))
        agent = _agent()
        base_identity = base_agent._effective_request_identity(None, False)
        assert base_identity["temperature"] == pytest.approx(base_agent.TEMPERATURE)
        assert agent._call_llm_with_cache("默认温度问题") == "温度身份响应"
        # 改变有效默认温度（调用方未显式传 temperature 的路径）→ 新身份
        monkeypatch.setattr(base_agent, "TEMPERATURE", 0.9)
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("默认温度问题") == "温度身份响应"
        assert calls["invoke"] == 2, "A09：有效默认温度变化也必须隔离（历史键漏此材料）"

    def test_json_effective_value_changes_identity(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("JSON 身份响应"))
        agent = _agent()
        monkeypatch.setenv("LLM_JSON_MODE", "on")
        assert agent._call_llm_with_cache("JSON 问题") == "JSON 身份响应"
        identity_on = base_agent._effective_request_identity(None, False)
        assert identity_on["json_object"] is False  # 调用点未请求 JSON
        # 调用点请求 json_mode=True 且开关 on → 实际绑定 response_format → 新身份
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("JSON 问题", json_mode=True) == "JSON 身份响应"
        assert calls["invoke"] == 2, "A09：JSON 模式实际生效值不同不得共享缓存"
        identity_json = base_agent._effective_request_identity(None, True)
        assert identity_json["json_object"] is True

    @pytest.mark.parametrize(
        ("env_key", "env_value"),
        [
            ("LLM_REASONING_EFFORT", "high"),
            ("AITESTER_CACHE_NAMESPACE", "seed7"),
        ],
    )
    def test_identity_matrix_env_materials_isolate(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        env_key: str,
        env_value: str,
    ):
        """身份矩阵：reasoning_effort / namespace 变化同样必须隔离缓存。"""
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("矩阵身份响应"))
        agent = _agent()
        monkeypatch.delenv(env_key, raising=False)
        assert agent._call_llm_with_cache("身份矩阵问题") == "矩阵身份响应"
        monkeypatch.setenv(env_key, env_value)
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("身份矩阵问题") == "矩阵身份响应"
        assert calls["invoke"] == 2, f"A09：{env_key} 变化属于不同请求身份，不得命中旧缓存"
        assert len(list(Path(tmp_path / "llm_cache").glob("*.json"))) == 2

    def test_legacy_cache_read_only_fallback_in_default_envelope(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """历史默认包络下，旧格式（无 request_identity）缓存仍可只读命中。"""
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("不应真实调用"))
        agent = _agent()
        legacy_file = base_agent._legacy_cache_file("旧缓存问题", agent.system_prompt, None, False)
        Path(legacy_file).parent.mkdir(parents=True, exist_ok=True)
        Path(legacy_file).write_text(
            json.dumps(
                {
                    "prompt": "旧缓存问题",
                    "system": agent.system_prompt,
                    "response": "旧缓存响应",
                    "tokens": 42,
                }
            ),
            encoding="utf-8",
        )
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("旧缓存问题") == "旧缓存响应"
        assert calls["invoke"] == 0, "默认包络下旧格式缓存应只读回退命中"
        # 不把旧文件回写成新格式（只读兼容）
        legacy_payload = json.loads(Path(legacy_file).read_text(encoding="utf-8"))
        assert "request_identity" not in legacy_payload

    def test_legacy_cache_not_hit_when_identity_sufficient(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """身份充足（thinking 非默认）时旧文件不误命中——M6 类"不串味"要求。"""
        _enable_cache(monkeypatch, tmp_path)
        calls = _patch_llm(monkeypatch, _fake_response("新身份真实响应"))
        agent = _agent()
        legacy_file = base_agent._legacy_cache_file("身份充足问题", agent.system_prompt, None, False)
        Path(legacy_file).parent.mkdir(parents=True, exist_ok=True)
        Path(legacy_file).write_text(
            json.dumps(
                {"prompt": "身份充足问题", "system": agent.system_prompt, "response": "旧身份响应", "tokens": 1}
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        clear_llm_lru_cache()
        assert agent._call_llm_with_cache("身份充足问题") == "新身份真实响应"
        assert calls["invoke"] == 1, "A09：身份充足时旧格式缓存不得被当作命中"


@pytest.mark.unit
class TestA11UsageAccounting:
    """A11（2026-10-18 第三方审查 P1）：响应 usage 先记账再做可用性判定。

    M9 验收的 Mock 条件：第一次 usage 非零且 finish_reason=length、第二次
    正常 → 累计消耗必须包含两次（修复前只记第二次）。
    """

    def test_abnormal_finish_usage_recorded_then_retry_accumulates(self, monkeypatch: pytest.MonkeyPatch):
        from src.budget.token_usage import get_usage, reset

        reset()
        responses = [
            SimpleNamespace(
                content="被截断的残缺内容",
                response_metadata={"finish_reason": "length"},
                usage_metadata={"input_tokens": 10, "output_tokens": 5},
            ),
            SimpleNamespace(
                content="正常响应",
                response_metadata={"finish_reason": "stop"},
                usage_metadata={"input_tokens": 4, "output_tokens": 3},
            ),
        ]
        calls = {"invoke": 0}

        def _invoke(messages, **kwargs):
            calls["invoke"] += 1
            return responses[min(calls["invoke"] - 1, 1)]

        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: SimpleNamespace(invoke=_invoke))
        monkeypatch.setattr("time.sleep", lambda s: None)
        agent = _agent()
        assert agent._call_llm("问题", max_retries=1) == "正常响应"
        assert calls["invoke"] == 2
        usage = get_usage()
        assert usage.total_tokens == 22, "首次 finish_reason=length 响应的 usage 必须先入账（10+5）+（4+3）"
        assert usage.llm_calls == 2

    def test_empty_response_usage_recorded(self, monkeypatch: pytest.MonkeyPatch):
        """空响应同样先把 usage 入账，再抛错（触发重试/故障转移）。"""
        from src.budget.token_usage import get_usage, reset

        reset()
        empty = SimpleNamespace(
            content="   ",
            response_metadata={"finish_reason": "stop"},
            usage_metadata={"input_tokens": 6, "output_tokens": 1},
        )
        _patch_llm(monkeypatch, empty)
        monkeypatch.setattr("time.sleep", lambda s: None)
        agent = _agent()
        with pytest.raises(RuntimeError):
            agent._call_llm("空响应问题", max_retries=0)
        assert get_usage().total_tokens == 7, "空响应的已发生消耗不得漏记"

    def test_budget_rechecked_before_retry(self, monkeypatch: pytest.MonkeyPatch):
        """A11：重试前复查预算——首次响应记账后预算超限 → 不再重试/故障转移。"""
        from src.budget.cost_budget import BudgetExceededError
        from src.budget.token_usage import reset

        reset()
        exceeded = {"flag": False}
        calls = {"invoke": 0}

        def _invoke(messages, **kwargs):
            calls["invoke"] += 1
            # 首次响应已返回（usage 已记账）；模拟记账后预算超限
            exceeded["flag"] = True
            return SimpleNamespace(
                content="残缺内容",
                response_metadata={"finish_reason": "length"},
                usage_metadata={"input_tokens": 100, "output_tokens": 100},
            )

        monkeypatch.setattr("src.budget.cost_budget.is_budget_exceeded", lambda: exceeded["flag"])
        monkeypatch.setattr(
            "src.budget.cost_budget.get_budget_stats",
            lambda: {"consumed_tokens": 999, "token_limit": 1, "unit": "tokens"},
        )
        monkeypatch.setattr(base_agent, "_get_all_api_configs", lambda: list(_CFG))
        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **k: SimpleNamespace(invoke=_invoke))
        agent = _agent()
        with pytest.raises(BudgetExceededError):
            agent._call_llm("预算问题", max_retries=3)
        assert calls["invoke"] == 1, "预算超限后不得继续重试（pre_retry_check 先于退避等待）"


@pytest.mark.unit
class TestA09LegacyCompatibilityPolicy:
    """A09 旧缓存兼容策略（docstring 声明的边界）用测试锁定：

    - 历史默认包络 → 旧文件可读；
    - 身份充足（thinking/reasoning/max_output/JSON/namespace/routing 任一
      非默认）→ 不回退旧文件（旧文件不误命中）。
    """

    def test_default_envelope_is_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
        monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
        monkeypatch.delenv("AITESTER_CACHE_NAMESPACE", raising=False)
        identity = base_agent._effective_request_identity(None, False)
        assert base_agent._legacy_cache_identity_compatible(identity) is True

    def test_thinking_enabled_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        assert (
            base_agent._legacy_cache_identity_compatible(base_agent._effective_request_identity(None, False)) is False
        )

    def test_reasoning_effort_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LLM_REASONING_EFFORT", "high")
        assert (
            base_agent._legacy_cache_identity_compatible(base_agent._effective_request_identity(None, False)) is False
        )

    def test_max_output_tokens_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "256")
        assert (
            base_agent._legacy_cache_identity_compatible(base_agent._effective_request_identity(None, False)) is False
        )

    def test_json_mode_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LLM_JSON_MODE", "on")
        assert base_agent._legacy_cache_identity_compatible(base_agent._effective_request_identity(None, True)) is False

    def test_namespace_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "seed42")
        assert (
            base_agent._legacy_cache_identity_compatible(base_agent._effective_request_identity(None, False)) is False
        )

    def test_complexity_routing_is_not_legacy_compatible(self, monkeypatch: pytest.MonkeyPatch):
        identity = base_agent._effective_request_identity(None, False, "complex")
        assert identity["routing"] == "complex"
        assert base_agent._legacy_cache_identity_compatible(identity) is False
