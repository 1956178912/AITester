"""AD 批次测试（2026-10-06 输出成本控制）。

背景：R-P0-2 生死实验实测 90%+ 输出 token 为 DeepSeek V4 系默认开启的
思维链（thinking 默认 enabled、思考模式 max_tokens 默认 64K、思维链按
输出计费；aitester 臂 5.23M 输出中实际工件仅 ~10%，单任务最高 84k
输出）。AD1 在 OpenAI 兼容路径接入 thinking / reasoning_effort /
max_tokens 三参数（默认关思考，对齐 zai 路径硬编码先例）。

覆盖：
- _openai_extra_body 解析矩阵（默认值 / 显式开启 / 非法值忽略 / 越界忽略）；
- 客户端缓存键含 extra_body（环境变更 → 新客户端，测试口径）；
- 客户端实例携带 extra_body（透传到底层 OpenAI 兼容端点）；
- zai 路径不受影响（保持自身硬编码 thinking disabled）。
"""

from __future__ import annotations

from typing import ClassVar

import pytest

import src.agents.llm_client as llm_client_module
from src.agents.llm_client import _get_or_create_chat_client, _openai_extra_body

_ENV_KEYS = ("LLM_THINKING_MODE", "LLM_REASONING_EFFORT", "LLM_MAX_OUTPUT_TOKENS")


@pytest.fixture(autouse=True)
def _clear_env_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例前清三环境变量 + 清空客户端缓存（隔离 FIFO 缓存与环境）。"""
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    llm_client_module._llm_client_cache.clear()
    yield
    llm_client_module._llm_client_cache.clear()


class TestOpenAIExtraBody:
    def test_default_disables_thinking(self) -> None:
        """默认（无任何 env）= thinking disabled，其余字段不发送。"""
        assert _openai_extra_body() == {"thinking": {"type": "disabled"}}

    def test_enabled_with_effort_and_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """质量敏感口径：thinking enabled + effort low + 输出上限。"""
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "4096")
        assert _openai_extra_body() == {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "low",
            "max_tokens": 4096,
        }

    @pytest.mark.parametrize("bad", ["abc", "0", "-5", "999999", "393217"])
    def test_invalid_max_tokens_ignored(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        """非法/越界 max_tokens 一律忽略（不发字段），不抛异常。"""
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", bad)
        assert "max_tokens" not in _openai_extra_body()

    @pytest.mark.parametrize("effort", ["none", "low", "high", "max"])
    def test_reasoning_effort_values(self, monkeypatch: pytest.MonkeyPatch, effort: str) -> None:
        """reasoning_effort 合法枚举透传（none 亦为官方关闭思考的口径）。"""
        monkeypatch.setenv("LLM_REASONING_EFFORT", effort)
        assert _openai_extra_body()["reasoning_effort"] == effort

    def test_invalid_effort_and_mode_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非法枚举值忽略：mode 不发 thinking、effort 不发字段。"""
        monkeypatch.setenv("LLM_THINKING_MODE", "bogus")
        monkeypatch.setenv("LLM_REASONING_EFFORT", "ultra")
        assert _openai_extra_body() == {}

    def test_effort_none_is_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """reasoning_effort=none 是官方关闭思考的合法口径（非非法值）。"""
        monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
        assert _openai_extra_body() == {
            "thinking": {"type": "disabled"},  # 默认模式仍在
            "reasoning_effort": "none",
        }


class TestClientCacheWithExtraBody:
    _KW: ClassVar[dict[str, str | float]] = {
        "model_name": "test-model",
        "temperature": 0.0,
        "api_key": "sk-test",
        "base_url": "https://api.example.com/v1",
    }

    def test_client_carries_extra_body(self) -> None:
        """客户端实例携带 extra_body（默认 disabled），透传至底层端点。"""
        client = _get_or_create_chat_client(**self._KW)
        assert getattr(client, "extra_body", None) == {"thinking": {"type": "disabled"}}

    def test_env_change_yields_new_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """缓存键含 extra_body：环境变更后取到新配置客户端（非缓存旧实例）。"""
        c1 = _get_or_create_chat_client(**self._KW)
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "2048")
        c2 = _get_or_create_chat_client(**self._KW)
        assert c1 is not c2
        assert getattr(c2, "extra_body", None)["max_tokens"] == 2048
        # 同环境再次获取命中缓存
        c3 = _get_or_create_chat_client(**self._KW)
        assert c2 is c3

    def test_same_env_hits_cache(self) -> None:
        """同配置重复获取返回缓存实例（连接池复用口径不回归）。"""
        c1 = _get_or_create_chat_client(**self._KW)
        c2 = _get_or_create_chat_client(**self._KW)
        assert c1 is c2
