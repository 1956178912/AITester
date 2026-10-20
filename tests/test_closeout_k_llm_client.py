"""KB 覆盖率收口：`src/agents/llm_client.py` 的客户端缓存 / 记账 / TTL 分支。

动机：llm_client 补口前 23 行未覆盖，缺口是**并发窗口与故障降级**——客户端
缓存双重检查锁的第二查（并发首调时复用他人已建实例）、token 记账异常的
fail-closed 口径、缓存创建者 uid 不可得、TTL 参数坏值、过期清理的 OSError
降级。这些分支在单线程测试里"几乎不可达"，但生产 --parallel 下正是常态；
未覆盖即双重检查锁的复用语义与预算守卫的 fail-closed 语义未经验证。

纪律：零真实网络（客户端缓存用"竞态模拟 dict"，构造路径不会真正建 SDK 客户端）；
零真实等待；缓存目录指向 tmp_path。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from config import LLMConfig
from src.agents import llm_client

# conftest 的 _isolate_llm_cache 会在每个测试内用 unittest.mock.patch 把
# llm_client.get_first_valid_model_name 换成 return_value=None 的 MagicMock
# （防跨模型缓存污染）。本文件要验证该函数本体，故在**模块导入期**
# （autouse fixture 尚未生效）捕获真实函数引用。
_REAL_GET_FIRST_VALID_MODEL_NAME = llm_client.get_first_valid_model_name


class _RacyCache(dict):
    """模拟并发窗口：第一次 get 未命中，第二次 get（锁内二次检查）命中。"""

    def __init__(self, cached: Any) -> None:
        super().__init__()
        self.cached = cached
        self.get_calls = 0

    def get(self, key, default=None):  # type: ignore[override]
        self.get_calls += 1
        return None if self.get_calls == 1 else self.cached


@pytest.mark.unit
class TestClientCacheDoubleCheck:
    """客户端缓存双重检查锁的"锁内二次命中"分支（并发首调复用）。"""

    def test_chat_client_second_check_returns_cached_instance(self, monkeypatch: pytest.MonkeyPatch):
        sentinel = object()
        racy = _RacyCache(sentinel)
        monkeypatch.setattr(llm_client, "_llm_client_cache", racy)
        out = llm_client._get_or_create_chat_client("model-x", 0.2, "key", "https://api.example.com/v1")
        assert out is sentinel
        assert racy.get_calls == 2, "应走无锁快路径 + 锁内二次检查两次 get"

    def test_zai_client_second_check_returns_cached_instance(self, monkeypatch: pytest.MonkeyPatch):
        sentinel = object()
        racy = _RacyCache(sentinel)
        monkeypatch.setattr(llm_client, "_zai_client_cache", racy)
        out = llm_client._get_or_create_zai_client("key", "https://open.bigmodel.cn/api/paas/v4")
        assert out is sentinel
        assert racy.get_calls == 2


@pytest.mark.unit
class TestRecordResponseUsageFailClosed:
    """O14：记账异常在 COST_BUDGET_ENABLE 开启时 fail-closed，关闭时静默忽略。"""

    @staticmethod
    def _break_record_usage(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.budget.token_usage.record_usage",
            lambda *a, **k: (_ for _ in ()).throw(OSError("磁盘满（模拟）")),
        )

    def test_budget_enabled_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch):
        self._break_record_usage(monkeypatch)
        monkeypatch.setattr("src.budget.cost_budget._budget_enabled", lambda: True)
        with pytest.raises(RuntimeError, match="预算记账异常（fail-closed）"):
            llm_client._record_response_usage({"input_tokens": 3, "output_tokens": 4}, "model-x")

    def test_budget_disabled_returns_true(self, monkeypatch: pytest.MonkeyPatch):
        self._break_record_usage(monkeypatch)
        monkeypatch.setattr("src.budget.cost_budget._budget_enabled", lambda: False)
        assert llm_client._record_response_usage({"input_tokens": 3, "output_tokens": 4}, "model-x") is True


@pytest.mark.unit
class TestZaiTemperaturePassthrough:
    """F09（2026-10-19 第三方审查 P1）：zai 请求必须实际携带 temperature。

    历史缺陷：`_call_zai` 签名与 SDK create 均无 temperature，而缓存身份
    （`base_agent._effective_request_identity`）记录"实际生效采样温度"——
    请求身份与实际请求分叉，改温度可能命中旧缓存。本类锁定调用级参数。
    """

    @staticmethod
    def _fake_response() -> Any:
        message = MagicMock()
        message.content = "ok"
        message.reasoning_content = None
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        response.usage = None
        return response

    def test_create_receives_temperature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        create = MagicMock(return_value=self._fake_response())
        client = MagicMock()
        client.chat.completions.create = create
        monkeypatch.setattr(llm_client, "_get_or_create_zai_client", lambda *a, **k: client)

        out = llm_client._call_zai(
            "k",
            "https://open.bigmodel.cn/api/paas/v4",
            "glm-4.7-flash",
            "sys",
            "hi",
            max_retries=0,
            temperature=0.37,
        )
        assert out == "ok"
        assert create.call_args.kwargs["temperature"] == pytest.approx(0.37)

    def test_temperature_param_defaults_to_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        create = MagicMock(return_value=self._fake_response())
        client = MagicMock()
        client.chat.completions.create = create
        monkeypatch.setattr(llm_client, "_get_or_create_zai_client", lambda *a, **k: client)

        llm_client._call_zai("k", "https://open.bigmodel.cn/api", "m", "s", "u", max_retries=0)
        assert create.call_args.kwargs["temperature"] == pytest.approx(llm_client.TEMPERATURE)


@pytest.mark.unit
class TestFirstValidModelName:
    """M8 缓存隔离键材料：线程局部 > 全局配置链 > None。"""

    def test_thread_local_model_name_takes_priority(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(llm_client._thread_local, "model_name", "thread-model", raising=False)
        monkeypatch.setattr(llm_client, "LLM_CONFIGS", [LLMConfig("k", "https://a/v1", "global-model")])
        assert _REAL_GET_FIRST_VALID_MODEL_NAME() == "thread-model"

    def test_global_first_config_used_when_no_thread_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delattr(llm_client._thread_local, "model_name", raising=False)
        monkeypatch.setattr(llm_client, "LLM_CONFIGS", [LLMConfig("k", "https://a/v1", "global-model")])
        assert _REAL_GET_FIRST_VALID_MODEL_NAME() == "global-model"

    def test_returns_none_without_any_config(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delattr(llm_client._thread_local, "model_name", raising=False)
        monkeypatch.setattr(llm_client, "LLM_CONFIGS", [])
        assert _REAL_GET_FIRST_VALID_MODEL_NAME() is None


@pytest.mark.unit
class TestCacheCreatorUid:
    """缓存创建者归属：uid 不可得时降级（读侧跳过校验）。"""

    def test_uid_unavailable_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "getuid", lambda: (_ for _ in ()).throw(OSError("无 uid（模拟）")))
        assert llm_client._cache_creator_uid() is None

    def test_empty_expected_label_accepts_any_stored_uid(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(llm_client, "_cache_creator_label", lambda: "")
        assert llm_client.cache_creator_ok("other-user") is True
        assert llm_client.cache_creator_ok(None) is True


@pytest.mark.unit
class TestCacheTtlAndCleanup:
    """TTL 参数坏值与过期清理的 OSError 降级。"""

    def test_ttl_invalid_env_falls_back_to_7_days(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AITESTER_LLM_CACHE_TTL_DAYS", "七天")
        assert llm_client._llm_cache_ttl_days() == 7

    def test_cleanup_skips_file_with_unreadable_mtime(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        cache_dir = tmp_path / "llm_cache"
        cache_dir.mkdir()
        (cache_dir / "a.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(llm_client, "_llm_cache_dir", lambda: str(cache_dir))
        monkeypatch.setattr(os.path, "getmtime", lambda path: (_ for _ in ()).throw(OSError("stat 失败（模拟）")))
        assert llm_client.cleanup_expired_cache_files(max_age_days=1) == 0
        assert (cache_dir / "a.json").exists(), "stat 失败的条目不得被误删"

    def test_cleanup_outer_oserror_returns_zero(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            llm_client,
            "_llm_cache_dir",
            lambda: (_ for _ in ()).throw(OSError("缓存目录不可读（模拟）")),
        )
        assert llm_client.cleanup_expired_cache_files(max_age_days=1) == 0
