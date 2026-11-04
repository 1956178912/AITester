"""LLM JSON Output 配置（2026-10-14，DeepSeek 官方文档）行为锁定测试。

覆盖：
1. LLM_JSON_MODE 开关三态（默认 on / off / 兼容值）；
2. json_mode 透传（_call_llm_with_cache → _call_llm）；
3. response_format 绑定（json_mode=True 且开关非 off 时请求携带
   {"type":"json_object"}；False / 开关 off 时不携带——历史口径）；
4. finish_reason 异常守卫（length / insufficient_system_resource →
   可恢复失败重试，不把残缺内容交给下游解析）；
5. 缓存键隔离（json_mode=True 与历史非 JSON 口径不共享缓存条目）。

背景：EMSE 批次日志中 Planner/Debugger JSON 解析失败（M10 6 次/75 任务）
按 DeepSeek 官方 JSON Output 指南配置 response_format；开关默认 on，
LLM_JSON_MODE=off 供旧批次复现（请求体逐字节同历史）。
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import base_agent
from src.agents.base_agent import BaseAgent
from src.agents.llm_client import json_output_mode_enabled


@pytest.fixture(autouse=True)
def _clear_llm_lru():
    """每个测试前后清空文件缓存进程内 LRU（与 test_llm_file_cache 同款）。"""
    base_agent.clear_llm_lru_cache()
    yield
    base_agent.clear_llm_lru_cache()


def _make_agent() -> BaseAgent:
    return BaseAgent(system_prompt="json mode test system prompt")


def _fake_response(content: str = '{"ok": 1}', finish_reason: str = "stop") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {"finish_reason": finish_reason}
    resp.usage_metadata = None
    return resp


class TestJsonOutputModeSwitch:
    """LLM_JSON_MODE 开关三态。"""

    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("LLM_JSON_MODE", raising=False)
        assert json_output_mode_enabled() is True

    @pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "disabled"])
    def test_off_variants(self, monkeypatch, value):
        monkeypatch.setenv("LLM_JSON_MODE", value)
        assert json_output_mode_enabled() is False

    @pytest.mark.parametrize("value", ["on", "1", "true", "enabled", ""])
    def test_on_variants(self, monkeypatch, value):
        monkeypatch.setenv("LLM_JSON_MODE", value)
        assert json_output_mode_enabled() is True


class TestJsonModeThreading:
    """json_mode 从 _call_llm_with_cache 透传到 _call_llm（缓存关路径）。"""

    def test_json_mode_forwarded(self):
        agent = _make_agent()
        mock_llm = MagicMock(return_value='{"ok": 1}')
        with patch.object(agent, "_call_llm", mock_llm):
            agent._call_llm_with_cache("hello", json_mode=True)
        assert mock_llm.call_args.kwargs.get("json_mode") is True

    def test_json_mode_absent_when_false(self):
        """json_mode=False（默认）时调用签名与历史逐字节一致（不多传参数）。"""
        agent = _make_agent()
        mock_llm = MagicMock(return_value="plain")
        with patch.object(agent, "_call_llm", mock_llm):
            agent._call_llm_with_cache("hello")
        assert "json_mode" not in mock_llm.call_args.kwargs


class TestResponseFormatBinding:
    """response_format 绑定（真实 _call_llm 路径，mock 客户端捕获请求参数）。"""

    def _call_with_mock_client(self, monkeypatch, mock_client, **kwargs):
        monkeypatch.setattr(
            base_agent,
            "_get_all_api_configs",
            lambda: [("sk-test", "https://api.deepseek.com/v1", "deepseek-flash")],
        )
        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **kw: mock_client)
        agent = _make_agent()
        return agent._call_llm("hello", **kwargs)

    def test_json_mode_binds_response_format(self, monkeypatch):
        monkeypatch.delenv("LLM_JSON_MODE", raising=False)
        client = MagicMock()
        client.invoke.return_value = _fake_response()
        result = self._call_with_mock_client(monkeypatch, client, json_mode=True, max_retries=0)
        assert result == '{"ok": 1}'
        assert client.invoke.call_args.kwargs.get("response_format") == {"type": "json_object"}

    def test_no_json_mode_no_response_format(self, monkeypatch):
        monkeypatch.delenv("LLM_JSON_MODE", raising=False)
        client = MagicMock()
        client.invoke.return_value = _fake_response()
        self._call_with_mock_client(monkeypatch, client, max_retries=0)
        assert "response_format" not in client.invoke.call_args.kwargs

    def test_env_off_disables_binding(self, monkeypatch):
        """LLM_JSON_MODE=off：即使调用点传 json_mode=True 也走历史口径。"""
        monkeypatch.setenv("LLM_JSON_MODE", "off")
        client = MagicMock()
        client.invoke.return_value = _fake_response()
        self._call_with_mock_client(monkeypatch, client, json_mode=True, max_retries=0)
        assert "response_format" not in client.invoke.call_args.kwargs


class TestFinishReasonGuard:
    """finish_reason 异常守卫（length / insufficient_system_resource）。"""

    def _setup(self, monkeypatch, responses):
        monkeypatch.setattr(
            base_agent,
            "_get_all_api_configs",
            lambda: [("sk-test", "https://api.deepseek.com/v1", "deepseek-flash")],
        )
        client = MagicMock()
        client.invoke.side_effect = responses
        monkeypatch.setattr(base_agent, "_get_or_create_chat_client", lambda *a, **kw: client)
        # 消除指数退避等待（1s/2s/4s）
        monkeypatch.setattr(base_agent.time, "sleep", lambda s: None)
        return client

    def test_truncated_response_is_retried_then_succeeds(self, monkeypatch):
        """首次响应 finish_reason=length → 可恢复失败重试 → 第二次成功。"""
        client = self._setup(
            monkeypatch,
            [_fake_response(finish_reason="length"), _fake_response('{"ok": 1}', "stop")],
        )
        agent = _make_agent()
        result = agent._call_llm("hello", json_mode=True, max_retries=2)
        assert result == '{"ok": 1}'
        assert client.invoke.call_count == 2

    def test_insufficient_resource_retried(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            [_fake_response(finish_reason="insufficient_system_resource"), _fake_response("ok", "stop")],
        )
        agent = _make_agent()
        assert agent._call_llm("hello", max_retries=2) == "ok"
        assert client.invoke.call_count == 2

    def test_truncated_exhausted_raises(self, monkeypatch):
        """截断持续发生 → 重试耗尽后抛错（不把残缺内容交给下游）。"""
        client = self._setup(monkeypatch, [_fake_response(finish_reason="length")] * 4)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", json_mode=True, max_retries=1)
        assert client.invoke.call_count == 2  # max_retries=1 → 首发 + 1 重试

    def test_truncation_uses_the_full_ladder_when_max_retries_is_one(self, monkeypatch):
        """max_retries=1 时新口径与旧口径同为两次尝试——差别只在不能更多。"""
        client = self._setup(monkeypatch, [_fake_response(finish_reason="length")] * 5)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", max_retries=1)
        assert client.invoke.call_count == 2

    def test_truncation_is_not_retried_on_the_full_ladder(self, monkeypatch):
        """**成本锁**：`LLM_MAX_RETRIES=6`（第 11 条上调后的默认档）下，
        截断只允许一次重试 ⇒ 最坏 2 次付费，而不是 7 次买同一个残缺答案。"""
        client = self._setup(monkeypatch, [_fake_response(finish_reason="length")] * 9)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", max_retries=6)
        assert client.invoke.call_count == 2, f"截断被重试了 {client.invoke.call_count - 1} 次，成本随阶梯点火"

    def test_transient_incomplete_keeps_the_full_ladder(self, monkeypatch):
        """与截断分档：服务端资源不足属瞬态，仍走完整退避（不削既有韧性）。"""
        client = self._setup(monkeypatch, [_fake_response(finish_reason="insufficient_system_resource")] * 9)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", max_retries=3)
        assert client.invoke.call_count == 4  # 首发 + 3 次重试

    def test_class_hierarchy_keeps_existing_catches_valid(self, monkeypatch):
        """两个新异常都是 RuntimeError 子类——既有的 `except RuntimeError` 口径不变。"""
        from src.agents.llm_client import LlmIncompleteResponseError, LlmTruncatedResponseError

        assert issubclass(LlmTruncatedResponseError, RuntimeError)
        assert issubclass(LlmIncompleteResponseError, RuntimeError)
        # 分档只服务重试预算，对外仍统一抛"LLM 调用失败"（由 _call_llm 包装）
        self._setup(monkeypatch, [_fake_response(finish_reason="length")] * 2)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", max_retries=0)

    def test_single_shot_caps_the_helper_at_two_attempts(self):
        """重试器直测：single_shot 类命中时最多首发 + 1 次。"""
        from src.agents.llm_client import LlmTruncatedResponseError, _retry_with_exponential_backoff

        calls: list[int] = []

        def _boom() -> None:
            calls.append(1)
            raise LlmTruncatedResponseError("LLM 响应不完整（finish_reason=length）")

        with pytest.raises(LlmTruncatedResponseError):
            _retry_with_exponential_backoff(
                _boom,
                6,
                base_wait=0,
                retryable_exceptions=(Exception,),
                single_shot_exceptions=(LlmTruncatedResponseError,),
            )
        assert len(calls) == 2, f"实际尝试 {len(calls)} 次，成本未封顶"

    def test_same_class_without_single_shot_uses_the_full_ladder(self):
        """负对照：不登记 single_shot 时同一异常仍走完整 7 次——封顶确实是新参数造成的。"""
        from src.agents.llm_client import LlmTruncatedResponseError, _retry_with_exponential_backoff

        calls: list[int] = []

        def _boom() -> None:
            calls.append(1)
            raise LlmTruncatedResponseError("truncated")

        with pytest.raises(RuntimeError, match=r"所有重试均失败|调用失败"):
            _retry_with_exponential_backoff(_boom, 6, base_wait=0, retryable_exceptions=(Exception,))
        assert len(calls) == 7

    def test_budget_is_rechecked_before_the_single_retry(self, monkeypatch):
        """那唯一一次重试也必须在预算复查之后——省下的次数不得绕过预算闸。"""
        self._setup(monkeypatch, [_fake_response(finish_reason="length")] * 3)
        checked: list[str] = []
        real = base_agent._raise_if_budget_exceeded

        def _spy(*args, **kwargs):
            checked.append("check")
            return real(*args, **kwargs)

        monkeypatch.setattr(base_agent, "_raise_if_budget_exceeded", _spy, raising=True)
        agent = _make_agent()
        with pytest.raises(RuntimeError, match="LLM 调用失败"):
            agent._call_llm("hello", max_retries=6)
        assert checked, "重试前未复查任务级预算"


class TestCacheKeyIsolation:
    """缓存键隔离：JSON 模式与非 JSON 历史口径不共享缓存条目。"""

    def test_json_and_non_json_do_not_share_cache(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        agent = _make_agent()
        mock_llm = MagicMock(side_effect=['{"a": 1}', '{"a": 1}', "plain"])

        with patch.object(agent, "_call_llm", mock_llm):
            agent._call_llm_with_cache("same prompt", json_mode=True)
            agent._call_llm_with_cache("same prompt", json_mode=True)  # 命中（同模式）
            agent._call_llm_with_cache("same prompt")  # 新调用（非 JSON 口径）
            agent._call_llm_with_cache("same prompt")  # 命中（非 JSON 口径）

        assert mock_llm.call_count == 2  # 两种模式各一次真实调用

    def test_json_mode_cache_hit_returns_same_response(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        agent = _make_agent()
        mock_llm = MagicMock(return_value='{"b": 2}')

        with patch.object(agent, "_call_llm", mock_llm):
            first = agent._call_llm_with_cache("prompt x", json_mode=True)
            second = agent._call_llm_with_cache("prompt x", json_mode=True)

        assert first == second == '{"b": 2}'
        assert mock_llm.call_count == 1
