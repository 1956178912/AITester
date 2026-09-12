"""
BaseAgent 扩展单元测试：覆盖 _call_zai、_get_llm_config 线程局部、
_get_all_api_configs、_call_llm_with_cache、_call_llm 等未覆盖路径，
将覆盖率从 62% 提升至 ≥80%。
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.base_agent import (
    _DEFAULT_LLM_MAX_RETRIES,
    BaseAgent,
    _call_zai,
    _get_all_api_configs,
    _get_llm_config,
)
from src.agents.llm_client import (
    _get_or_create_zai_client,
    _llm_client_cache,
    _thread_local,
    _zai_client_cache,
)


@pytest.fixture(autouse=True)
def _clear_llm_client_cache():
    """每个测试前后清空 LLM 客户端复用缓存（ChatOpenAI 与 zai 两套）。

    各测试独立 patch 客户端构造，若缓存残留前一个测试的 mock 实例，
    _call_llm / _call_zai 会复用旧 mock 导致断言错乱。
    """
    _llm_client_cache.clear()
    _zai_client_cache.clear()
    yield
    _llm_client_cache.clear()
    _zai_client_cache.clear()


# ─── TestCallZai ──────────────────────────────────────────────────────────────


class TestCallZai:
    """测试 zai SDK 调用路径 (_call_zai)。"""

    @patch("src.agents.llm_client._retry_with_exponential_backoff")
    def test_call_zai_success(self, mock_retry):
        """zai 调用成功时返回 LLM 文本。"""
        mock_retry.return_value = "zai response text"
        result = _call_zai(
            api_key="test_key",
            base_url="https://open.bigmodel.cn/api/llm/chat",
            model_name="glm-4.7-flash",
            system_prompt="You are helpful.",
            user_message="Hello",
        )
        assert result == "zai response text"
        mock_retry.assert_called_once()

    @patch("src.agents.llm_client._retry_with_exponential_backoff")
    def test_call_zai_raises_on_failure(self, mock_retry):
        """zai 调用全部失败时抛出 RuntimeError。"""
        mock_retry.side_effect = RuntimeError("zai error")
        with pytest.raises(RuntimeError, match="zai API 调用失败"):
            _call_zai(
                api_key="key",
                base_url="https://open.bigmodel.cn/api",
                model_name="glm-4.7-flash",
                system_prompt="sys",
                user_message="usr",
            )

    @patch("src.agents.llm_client._retry_with_exponential_backoff")
    def test_call_zai_passes_correct_args(self, mock_retry):
        """验证传递给重试函数的参数正确（包含 base_wait=5）。"""
        mock_retry.return_value = "ok"
        _call_zai(
            api_key="k",
            base_url="https://open.bigmodel.cn/api",
            model_name="m",
            system_prompt="s",
            user_message="u",
            max_retries=2,
        )
        call_kwargs = mock_retry.call_args
        assert call_kwargs.kwargs["base_wait"] == 5
        assert call_kwargs.kwargs["max_retries"] == 2


# ─── TestZaiClientReuse ──────────────────────────────────────────────────────
class TestZaiClientReuse:
    """测试 zai SDK 客户端复用缓存（_get_or_create_zai_client）。

    zai 是延迟导入（from zai import ZhipuAiClient），测试通过向 sys.modules
    注入假 zai 模块来追踪构造次数，不依赖真实 zai SDK。
    """

    @pytest.fixture
    def fake_zai(self, monkeypatch):
        """注入假的 zai / zai.core / zai.core._errors 模块，返回 (假模块, 构造记录)。"""
        import types

        fake_module = types.ModuleType("zai")
        fake_core = types.ModuleType("zai.core")
        fake_errors = types.ModuleType("zai.core._errors")

        class APIReachLimitError(Exception):
            """假 zai 限流异常（用于 _call_zai 导入路径）。"""

        class APIStatusError(Exception):
            """假 zai 状态异常（用于 _call_zai 导入路径）。"""

        fake_errors.APIReachLimitError = APIReachLimitError
        fake_errors.APIStatusError = APIStatusError
        fake_core._errors = fake_errors
        fake_module.core = fake_core

        constructed: list = []

        # 预配置 LLM 响应：所有 fake 客户端的 create() 直接返回该响应
        response = MagicMock(name="zai_response")
        message = MagicMock(name="zai_message")
        message.content = "zai ok"
        response.choices = [MagicMock(message=message)]

        def _fake_zhipu_ai_client(api_key=None, base_url=None, **kwargs):
            mock_client = MagicMock(name=f"zai_client_{api_key}_{base_url}")
            mock_client.chat.completions.create.return_value = response
            constructed.append(mock_client)
            return mock_client

        fake_module.ZhipuAiClient = _fake_zhipu_ai_client
        monkeypatch.setitem(sys.modules, "zai", fake_module)
        monkeypatch.setitem(sys.modules, "zai.core", fake_core)
        monkeypatch.setitem(sys.modules, "zai.core._errors", fake_errors)
        return fake_module, constructed

    def test_same_config_reuses_client(self, fake_zai):
        """相同 (api_key, base_url) 返回同一实例，只构造一次。"""
        _, constructed = fake_zai
        c1 = _get_or_create_zai_client("key-1", "https://open.bigmodel.cn/api/paas/v4/")
        c2 = _get_or_create_zai_client("key-1", "https://open.bigmodel.cn/api/paas/v4/")

        assert c1 is c2
        assert len(constructed) == 1

    def test_different_config_creates_new_client(self, fake_zai):
        """不同 api_key 构建新实例。"""
        _, constructed = fake_zai
        c1 = _get_or_create_zai_client("key-1", "https://open.bigmodel.cn/api/paas/v4/")
        c2 = _get_or_create_zai_client("key-2", "https://open.bigmodel.cn/api/paas/v4/")

        assert c1 is not c2
        assert len(constructed) == 2

    def test_fifo_eviction_at_capacity(self, fake_zai, monkeypatch):
        """缓存达到上限时按 FIFO 淘汰最早条目。"""
        import src.agents.llm_client as ba

        fake_module, _ = fake_zai
        monkeypatch.setattr(ba, "_MAX_CACHED_ZAI_CLIENTS", 2)

        _get_or_create_zai_client("k1", "u")
        _get_or_create_zai_client("k2", "u")
        _get_or_create_zai_client("k3", "u")

        assert len(_zai_client_cache) == 2
        assert ("k1", "u") not in _zai_client_cache  # 最早插入的 k1 被淘汰
        assert ("k3", "u") in _zai_client_cache

    def test_call_zai_reuses_client_across_calls(self, fake_zai):
        """_call_zai 连续两次调用复用同一客户端。"""
        fake_module, constructed = fake_zai

        result1 = _call_zai(
            api_key="key-1",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            model_name="glm-4.7-flash",
            system_prompt="sys",
            user_message="hello",
        )
        result2 = _call_zai(
            api_key="key-1",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            model_name="glm-4.7-flash",
            system_prompt="sys",
            user_message="hello",
        )

        assert result1 == "zai ok"
        assert result2 == "zai ok"
        assert len(constructed) == 1  # 两次调用只构造 1 个客户端


# ─── TestGetLlmConfigThreadLocal ──────────────────────────────────────────────


class TestGetLlmConfigThreadLocal:
    """测试 _get_llm_config 的线程局部覆盖分支。"""

    def teardown_method(self, method):
        """每个测试后清理线程局部存储。"""
        for attr in ("api_key", "base_url", "model_name"):
            if hasattr(_thread_local, attr):
                delattr(_thread_local, attr)

    @patch("src.agents.llm_client.LLM_CONFIGS", new=[])
    def test_thread_local_api_key_takes_precedence(self):
        """线程局部 api_key 存在时优先使用它。"""
        _thread_local.api_key = "thread_key"
        _thread_local.base_url = "https://thread.url"
        api_key, base_url, model_name = _get_llm_config()
        assert api_key == "thread_key"
        assert base_url == "https://thread.url"
        assert model_name == ""

    @patch("src.agents.llm_client.LLM_CONFIGS")
    def test_thread_local_model_fallback_to_config(self, mock_configs):
        """线程局部未设置 model_name 时回退到 LLM_CONFIGS[0]。"""
        mock_cfg = MagicMock()
        mock_cfg.model_name = "fallback-model"
        mock_configs.__iter__ = MagicMock(return_value=iter([mock_cfg]))
        mock_configs.__len__ = MagicMock(return_value=1)
        mock_configs.__getitem__ = MagicMock(return_value=mock_cfg)

        _thread_local.api_key = "tk"
        _thread_local.base_url = "turl"
        api_key, base_url, model_name = _get_llm_config()
        assert model_name == "fallback-model"

    @patch("src.agents.llm_client.LLM_CONFIGS", new=[])
    def test_thread_local_empty_api_key_falls_through(self):
        """线程局部 api_key 为空时回退到全局配置。"""
        _thread_local.api_key = ""
        _thread_local.base_url = "ignored"
        with patch("src.agents.llm_client.LLM_CONFIGS", new=[]):
            api_key, base_url, model_name = _get_llm_config()
        assert api_key == ""


# ─── TestGetAllApiConfigs ─────────────────────────────────────────────────────


class TestGetAllApiConfigs:
    """测试 _get_all_api_configs。"""

    @patch("src.agents.llm_client.LLM_CONFIGS")
    def test_returns_tuple_list(self, mock_configs):
        """返回所有配置的 (api_key, base_url, model_name) 三元组列表。"""
        cfg1 = MagicMock()
        cfg1.api_key = "key1"
        cfg1.base_url = "https://api1.com"
        cfg1.model_name = "model1"
        cfg2 = MagicMock()
        cfg2.api_key = "key2"
        cfg2.base_url = "https://api2.com"
        cfg2.model_name = "model2"
        mock_configs.__iter__ = MagicMock(return_value=iter([cfg1, cfg2]))
        mock_configs.__len__ = MagicMock(return_value=2)

        result = _get_all_api_configs()
        assert len(result) == 2
        assert result[0] == ("key1", "https://api1.com", "model1")
        assert result[1] == ("key2", "https://api2.com", "model2")

    @patch("src.agents.llm_client.LLM_CONFIGS", new=[])
    def test_empty_configs_returns_empty_list(self):
        """无配置时返回空列表。"""
        assert _get_all_api_configs() == []


# ─── TestCallLlmWithCache ─────────────────────────────────────────────────────
#
# 背景：本组 6 个测试曾以"局部 import os/json 无法 patch"为由 skip
# （旧实现的方法内局部 import）。源码重构为模块级 import 后（base_agent
# 顶部 import os/json/hashlib），缓存开关与目录均可经环境变量 patch：
# - AITESTER_LLM_CACHE=1 开启缓存（conftest autouse fixture 默认置 0，测试内显式覆盖）
# - AITESTER_LLM_CACHE_DIR 指向临时目录（conftest 已做测试隔离）
# 缓存键算法（与 base_agent._call_llm_with_cache 保持一致）：
#   md5(f"{user_message}:{system_prompt}").hexdigest()[:16] + ".json"


def _cache_file_for(user_message: str, system_prompt: str, cache_dir) -> Path:
    """计算给定消息对应的缓存文件路径（与 base_agent 实现同步，用于测试预置/断言）。"""
    digest = hashlib.md5(f"{user_message}:{system_prompt}".encode()).hexdigest()[:16]
    return Path(cache_dir) / f"{digest}.json"


class TestCallLlmWithCache:
    """测试 _call_llm_with_cache 缓存读写路径。"""

    def _make_agent(self):
        """创建一个 mock llm 的 BaseAgent 实例。"""
        with (
            patch("src.agents.llm_client.ChatOpenAI") as mock_cls,
            patch("src.agents.base_agent._get_llm_config") as mock_get,
        ):
            mock_get.return_value = ("k", "u", "m")
            mock_llm = MagicMock()
            mock_cls.return_value = mock_llm
            return BaseAgent("sys prompt")

    @pytest.fixture
    def cache_env(self, monkeypatch, tmp_path):
        """开启 LLM 文件缓存并把缓存目录指向临时目录（覆盖 conftest 的默认关闭）。"""
        cache_dir = tmp_path / "cache_enabled"
        cache_dir.mkdir()
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))
        return cache_dir

    def test_cache_miss_calls_llm(self, cache_env):
        """缓存未命中时调用 _call_llm 并将结果写入缓存文件。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="llm response")
        result = agent._call_llm_with_cache("hello")
        assert result == "llm response"
        agent._call_llm.assert_called_once_with("hello", _DEFAULT_LLM_MAX_RETRIES)
        # 缓存文件已写入且内容完整
        cache_file = _cache_file_for("hello", "sys prompt", cache_env)
        assert cache_file.exists()
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data["prompt"] == "hello"
        assert data["system"] == "sys prompt"
        assert data["response"] == "llm response"

    def test_cache_hit_returns_cached_response(self, cache_env):
        """缓存命中时直接返回缓存的 response，不再发起 LLM 调用。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="live response")
        first = agent._call_llm_with_cache("hello")
        assert first == "live response"
        agent._call_llm.reset_mock()
        # 相同输入第二次调用：命中缓存，_call_llm 不再被调用
        second = agent._call_llm_with_cache("hello")
        assert second == "live response"
        agent._call_llm.assert_not_called()

    def test_cache_hit_different_prompt_calls_llm(self, cache_env):
        """缓存条目的 prompt 与当前请求不一致时（碰撞/脏数据），应落回实时调用。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="live response")
        # 预置一条 prompt 不匹配的缓存条目（模拟哈希碰撞或历史脏数据）
        cache_file = _cache_file_for("hello", "sys prompt", cache_env)
        cache_file.write_text(
            json.dumps({"prompt": "stale", "system": "sys prompt", "response": "stale response"}),
            encoding="utf-8",
        )
        result = agent._call_llm_with_cache("hello")
        assert result == "live response"
        agent._call_llm.assert_called_once()
        # 旧条目被有效结果覆盖
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data["prompt"] == "hello"
        assert data["response"] == "live response"

    def test_cache_read_exception_logs_and_continues(self, cache_env):
        """缓存文件损坏（非法 JSON）时读取异常被吞掉，仍正常走 LLM 调用。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="live response")
        cache_file = _cache_file_for("hello", "sys prompt", cache_env)
        cache_file.write_text("{ not valid json", encoding="utf-8")
        result = agent._call_llm_with_cache("hello")
        assert result == "live response"
        agent._call_llm.assert_called_once()
        # 损坏文件被有效内容覆盖
        json.loads(cache_file.read_text(encoding="utf-8"))

    def test_cache_write_after_llm_call(self, cache_env):
        """LLM 调用成功后写入缓存文件（含 timestamp 字段，目录中仅此一个文件）。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="resp A")
        agent._call_llm_with_cache("msg A")
        cache_file = _cache_file_for("msg A", "sys prompt", cache_env)
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert {"prompt", "system", "response", "timestamp"} <= set(data)
        assert data["response"] == "resp A"
        # 缓存目录中恰好一个文件（无冗余写入）
        assert list(cache_env.iterdir()) == [cache_file]

    def test_cache_write_exception_logs_and_returns(self, cache_env):
        """缓存写入失败（如只读文件系统）时异常被吞掉，正常返回 LLM 结果。"""
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="live response")
        with patch("os.makedirs", side_effect=OSError("read-only filesystem")):
            result = agent._call_llm_with_cache("hello")
        assert result == "live response"
        agent._call_llm.assert_called_once()

    def test_cache_method_exists_and_has_correct_signature(self):
        """验证 _call_llm_with_cache 方法存在且具有正确的签名。"""
        import inspect

        agent = self._make_agent()
        sig = inspect.signature(agent._call_llm_with_cache)
        params = list(sig.parameters.keys())
        assert "user_message" in params
        assert "max_retries" in params
        # 验证方法存在且可调用
        assert callable(agent._call_llm_with_cache)


# ─── TestCallLlm ──────────────────────────────────────────────────────────────


class TestCallLlm:
    """测试 _call_llm 的 OpenAI 兼容路径。"""

    def _make_agent(self):
        """创建 mock llm 的 BaseAgent 实例。"""
        with (
            patch("src.agents.llm_client.ChatOpenAI") as mock_cls,
            patch("src.agents.base_agent._get_llm_config") as mock_get,
        ):
            mock_get.return_value = ("k", "u", "m")
            mock_llm = MagicMock()
            mock_cls.return_value = mock_llm
            return BaseAgent("sys prompt")

    @patch("src.agents.base_agent._get_all_api_configs")
    def test_raises_when_no_configs(self, mock_get_configs):
        """无 API 配置时抛出 RuntimeError。"""
        mock_get_configs.return_value = []
        agent = self._make_agent()
        with pytest.raises(RuntimeError, match="未配置任何 LLM API"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.llm_client.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_success_on_first_api(self, mock_get_configs, mock_chat_openai, mock_is_zai):
        """第一个 API 成功时直接返回文本。"""
        mock_get_configs.return_value = [("key1", "https://api.openai.com/v1", "gpt-4")]
        mock_is_zai.return_value = False
        mock_response = MagicMock()
        mock_response.content = "  hello world  "
        mock_chat_openai.return_value.invoke.return_value = mock_response
        agent = self._make_agent()
        result = agent._call_llm("hello")
        assert result == "hello world"

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.llm_client.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_falls_back_to_second_api_on_failure(self, mock_get_configs, mock_chat_openai, mock_is_zai):
        """第一个 API 失败时自动切换到备用 API。"""
        mock_get_configs.return_value = [
            ("key1", "https://api.fail.com/v1", "gpt-4"),
            ("key2", "https://api.ok.com/v1", "gpt-3.5"),
        ]
        mock_is_zai.return_value = False

        call_count = [0]

        def make_mock_response(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("connection refused")
            mock_resp = MagicMock()
            mock_resp.content = "recovered"
            return mock_resp

        mock_chat_openai.return_value.invoke.side_effect = make_mock_response

        agent = self._make_agent()
        result = agent._call_llm("hello")
        assert result == "recovered"
        assert mock_chat_openai.return_value.invoke.call_count == 2

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.llm_client.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_raises_when_all_apis_fail(self, mock_get_configs, mock_chat_openai, mock_is_zai):
        """所有 API 均失败时抛出 RuntimeError。"""
        mock_get_configs.return_value = [
            ("key1", "https://api1.com/v1", "m1"),
            ("key2", "https://api2.com/v1", "m2"),
        ]
        mock_is_zai.return_value = False
        mock_instance = MagicMock()
        mock_instance.invoke.side_effect = RuntimeError("all fail")
        mock_chat_openai.return_value = mock_instance

        agent = self._make_agent()
        with pytest.raises(RuntimeError, match="已尝试所有 API"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.llm_client.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_empty_response_triggers_retry(self, mock_get_configs, mock_chat_openai, mock_is_zai):
        """LLM 返回空响应时视为失败，尝试下一个模型/API。"""
        mock_get_configs.return_value = [
            ("key1", "https://api1.com/v1", "m1"),
        ]
        mock_is_zai.return_value = False
        mock_instance = MagicMock()
        mock_empty_response = MagicMock()
        mock_empty_response.content = "   "
        mock_instance.invoke.return_value = mock_empty_response
        mock_chat_openai.return_value = mock_instance

        agent = self._make_agent()
        with pytest.raises(RuntimeError, match="已尝试所有 API"):
            agent._call_llm("hello")

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.base_agent._call_zai")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_zai_path_called_for_zai_url(self, mock_get_configs, mock_call_zai, mock_is_zai):
        """zai 兼容 URL 走 _call_zai 路径。"""
        mock_get_configs.return_value = [("zai_key", "https://open.bigmodel.cn/api", "glm-4")]
        mock_is_zai.return_value = True
        mock_call_zai.return_value = "zai reply"
        agent = self._make_agent()
        result = agent._call_llm("hello")
        assert result == "zai reply"
        mock_call_zai.assert_called_once()

    @patch("src.agents.base_agent._is_zai_compatible")
    @patch("src.agents.llm_client.ChatOpenAI")
    @patch("src.agents.base_agent._get_all_api_configs")
    def test_same_api_multiple_models_fallback(self, mock_get_configs, mock_chat_openai, mock_is_zai):
        """同一 API 有多个模型时，失败后尝试同 API 的下一个模型。"""
        mock_get_configs.return_value = [
            ("key1", "https://api1.com/v1", "m1"),
            ("key1", "https://api1.com/v1", "m2"),
        ]
        mock_is_zai.return_value = False
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("m1 failed")
            mock_resp = MagicMock()
            mock_resp.content = "m2 succeeded"
            return mock_resp

        mock_instance = MagicMock()
        mock_instance.invoke.side_effect = side_effect
        mock_chat_openai.return_value = mock_instance

        agent = self._make_agent()
        result = agent._call_llm("hello")
        assert result == "m2 succeeded"


# ─── TestExtractJsonEdgeCases ─────────────────────────────────────────────────


class TestExtractJsonEdgeCases:
    """测试 _extract_json 的边缘情况和降级路径。"""

    def test_json_with_surrounding_text_and_markdown(self):
        """文本中嵌有 markdown 包裹的 JSON。"""
        text = 'Here\'s the result:\n```json\n{"answer": 42}\n```\nHope this helps!'
        result = BaseAgent._extract_json(text)
        assert result == {"answer": 42}

    def test_fallback_to_regex_on_invalid_balanced(self):
        """平衡法提取后 JSON 格式不合法时，降级到正则匹配。"""
        text = '{"a": } not valid'
        with pytest.raises(json.JSONDecodeError):
            BaseAgent._extract_json(text)

    def test_regex_fallback_find_Leaf_json(self):
        """正则降级：从文本中提取最内层合法 JSON。"""
        text = 'Some text {"valid": true} more text'
        result = BaseAgent._extract_json(text)
        assert result == {"valid": True}

    def test_no_curly_braces_raises(self):
        """文本中无 '{' 时抛出明确的 JSONDecodeError。"""
        with pytest.raises(json.JSONDecodeError, match="No JSON found"):
            BaseAgent._extract_json("just plain text")

    def test_extract_json_with_array_value(self):
        """提取含数组值的 JSON。"""
        text = '{"items": [1, 2, 3], "name": "test"}'
        result = BaseAgent._extract_json(text)
        assert result["items"] == [1, 2, 3]
        assert result["name"] == "test"


# ─── TestFindBalancedJsonEdgeCases ────────────────────────────────────────────


class TestFindBalancedJsonEdgeCases:
    """测试 _find_balanced_json 的边缘情况。"""

    def test_start_at_negative(self):
        """start 为负数时返回 None。"""
        assert BaseAgent._find_balanced_json("{}", -1) is None

    def test_start_at_exact_length(self):
        """start 等于文本长度时返回 None。"""
        assert BaseAgent._find_balanced_json("{}", 2) is None

    def test_escaped_brace_in_string(self):
        """字符串内的花括号不计入深度。"""
        text = '{"key": "value \\"with braces {in}\\""}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == text

    def test_multiple_json_objects_returns_first(self):
        """文本中有多个 JSON 对象时返回第一个完整的。"""
        text = '{"a": 1} some text {"b": 2}'
        result = BaseAgent._find_balanced_json(text, 0)
        assert result == '{"a": 1}'

    def test_empty_text(self):
        """空文本返回 None。"""
        assert BaseAgent._find_balanced_json("", 0) is None


# ─── TestExtractPythonCodeEdgeCases ───────────────────────────────────────────


class TestExtractPythonCodeEdgeCases:
    """测试 _extract_python_code 的边缘情况。"""

    def test_generic_fence_without_language(self):
        """纯 ``` 包裹（无语言标记）也能提取。"""
        text = "```\ndef foo(): pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def foo():" in result

    def test_python_prefix_with_uppercase(self):
        """PYTHON: 大写前缀也能识别。"""
        text = "PYTHON:\ndef hello(): pass"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result

    def test_python_prefix_with_extra_whitespace(self):
        """python: 前缀后有多个空格或换行也能识别。"""
        text = "python  \n\ndef hello(): pass"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result

    def test_plain_code_stripped(self):
        """无标记时返回 strip 后的原文。"""
        text = "  def hello():\n    pass  "
        result = BaseAgent._extract_python_code(text)
        assert result == "def hello():\n    pass"

    def test_python_fence_takes_precedence_over_generic(self):
        """同时存在 python 和通用 fence 时优先取 python 块。"""
        text = "```\nvar x = 1;\n```\n```python\ndef hello(): pass\n```"
        result = BaseAgent._extract_python_code(text)
        assert "def hello():" in result
        assert "var x = 1;" not in result


# ─── TestTruncateCodeEdgeCases ────────────────────────────────────────────────


class TestTruncateCodeEdgeCases:
    """测试 truncate_code 的边缘情况。"""

    def test_exact_max_chars_not_truncated(self):
        """代码长度正好等于 max_chars 时不被截断。"""
        code = "x" * 100
        result = BaseAgent.truncate_code(code, max_chars=100)
        assert result == code

    def test_one_char_over_truncated(self):
        """代码超出一字符时触发截断。"""
        code = "x" * 101
        result = BaseAgent.truncate_code(code, max_chars=100)
        assert len(result) <= 100
        assert "[代码已截断" in result

    def test_truncated_msg_includes_max_value(self):
        """截断提示中包含 max_chars 值。"""
        code = "x" * 200
        result = BaseAgent.truncate_code(code, max_chars=50)
        assert "50" in result

    def test_tail_len_zero_when_max_is_small(self):
        """max_chars 很小时尾部可能为空，但不报错。"""
        code = "x" * 1000
        result = BaseAgent.truncate_code(code, max_chars=10)
        assert "[代码已截断" in result
        assert len(result) < len(code)


# ─── TestGetLlmConfigIntegration ──────────────────────────────────────────────


class TestGetLlmConfigIntegration:
    """集成测试：验证 _get_llm_config 在有配置时的完整路径。"""

    @patch("src.agents.llm_client.LLM_CONFIGS")
    def test_returns_config_values(self, mock_configs):
        """有配置时返回正确的 api_key、base_url、model_name。"""
        mock_cfg = MagicMock()
        mock_cfg.api_key = "real_key"
        mock_cfg.base_url = "https://api.example.com/v1"
        mock_cfg.model_name = "example-model"
        mock_configs.__iter__ = MagicMock(return_value=iter([mock_cfg]))
        mock_configs.__len__ = MagicMock(return_value=1)
        mock_configs.__getitem__ = MagicMock(return_value=mock_cfg)

        api_key, base_url, model_name = _get_llm_config()
        assert api_key == "real_key"
        assert base_url == "https://api.example.com/v1"
        assert model_name == "example-model"
