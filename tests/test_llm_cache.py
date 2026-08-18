"""
单元测试：测试 LLM 缓存模块 llm_cache。

覆盖范围：
    - _compute_cache_key：无 extra / 有 extra / extra 为空字符串
    - _increment_hit / _increment_miss / _increment_eviction
    - cached_llm_call 装饰器：首次调用、缓存命中、cache_clear、cache_info
    - get_cached_response：始终返回 None，且调用 _increment_miss
    - set_cached_response：pass 语句（验证不报错）
    - clear_cache：日志输出
    - reset_cache_stats：重置全局 _thread_stats
"""

from unittest.mock import MagicMock, patch

import pytest

from src.graph.llm_cache import (
    _MAX_CACHE_SIZE,
    _compute_cache_key,
    _increment_eviction,
    _increment_hit,
    _increment_miss,
    cached_llm_call,
    clear_cache,
    get_cache_stats,
    get_cached_response,
    reset_cache_stats,
    set_cached_response,
)

# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stats():
    """每个测试前后重置缓存统计，防止测试间污染。"""
    reset_cache_stats()
    yield
    reset_cache_stats()


# ─── Test_compute_cache_key ──────────────────────────────────────────────────


class TestComputeCacheKey:
    """测试 _compute_cache_key 函数。"""

    def test_basic_key_without_extra(self):
        """不带 extra 时，缓存键由 prompt + system_prompt 拼接后哈希得到。"""
        key = _compute_cache_key("hello", "world")
        # SHA-256 输出固定为 64 字符十六进制
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_with_extra(self):
        """带 extra 时，key_material 会追加 extra 字段并重新哈希。"""
        key_no_extra = _compute_cache_key("prompt", "system")
        key_with_extra = _compute_cache_key("prompt", "system", extra="gpt-4")
        assert key_no_extra != key_with_extra

    def test_key_with_empty_extra(self):
        """extra 为空字符串时视为 falsy，不追加到 key_material。"""
        key_none = _compute_cache_key("prompt", "system", extra=None)
        key_empty = _compute_cache_key("prompt", "system", extra="")
        assert key_none == key_empty

    def test_deterministic(self):
        """相同参数应产生相同缓存键。"""
        key1 = _compute_cache_key("foo", "bar", extra="v1")
        key2 = _compute_cache_key("foo", "bar", extra="v1")
        assert key1 == key2

    def test_different_prompt_different_key(self):
        """不同 prompt 应产生不同缓存键。"""
        key1 = _compute_cache_key("hello world", "sys1")
        key2 = _compute_cache_key("hello there", "sys1")
        assert key1 != key2


# ─── Test_increment_hit / miss / eviction ─────────────────────────────────────


class TestIncrementStats:
    """测试 _increment_hit / _increment_miss / _increment_eviction。"""

    def test_increment_hit(self):
        """_increment_hit 应使 hits 计数加 1。"""
        _increment_hit()
        stats = get_cache_stats()
        assert stats["hits"] == 1

    def test_increment_hit_multiple_times(self):
        """多次调用 _increment_hit 应累加。"""
        _increment_hit()
        _increment_hit()
        _increment_hit()
        stats = get_cache_stats()
        assert stats["hits"] == 3

    def test_increment_miss(self):
        """_increment_miss 应使 misses 计数加 1。"""
        _increment_miss()
        stats = get_cache_stats()
        assert stats["misses"] == 1

    def test_increment_eviction(self):
        """_increment_eviction 应使 evictions 计数加 1。"""
        _increment_eviction()
        stats = get_cache_stats()
        assert stats["evictions"] == 1

    def test_increments_do_not_interfere(self):
        """三个计数器应相互独立。"""
        _increment_hit()
        _increment_miss()
        _increment_eviction()
        stats = get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["evictions"] == 1
        assert sum(stats.values()) == 3


# ─── Test_cached_llm_call ─────────────────────────────────────────────────────


class TestCachedLlmCall:
    """测试 cached_llm_call 装饰器。"""

    def test_first_call_executes_function(self):
        """首次调用应执行原函数并返回结果。"""
        mock_func = MagicMock(return_value="response_1")
        wrapped = cached_llm_call(mock_func)
        result = wrapped("hello")
        assert result == "response_1"
        mock_func.assert_called_once_with("hello")

    def test_second_call_returns_cached_result(self):
        """相同输入第二次调用应返回缓存结果，不重复调用原函数。"""
        mock_func = MagicMock(return_value="response_1")
        wrapped = cached_llm_call(mock_func)

        result1 = wrapped("hello")
        result2 = wrapped("hello")

        assert result1 == result2 == "response_1"
        assert mock_func.call_count == 1  # 仅首次调用

    def test_different_inputs_call_function_twice(self):
        """不同输入应分别调用原函数。"""
        mock_func = MagicMock(return_value="result")
        wrapped = cached_llm_call(mock_func)

        wrapped("input_a")
        wrapped("input_b")

        assert mock_func.call_count == 2

    def test_cache_clear_cleared(self):
        """调用 cache_clear 后缓存应被清空，再次调用触发原函数。"""
        mock_func = MagicMock(return_value="result")
        wrapped = cached_llm_call(mock_func)

        wrapped("input_a")
        assert mock_func.call_count == 1

        wrapped.cache_clear()
        wrapped("input_a")
        assert mock_func.call_count == 2

    def test_cache_info_returns_info(self):
        """cache_info 应返回 LRU 缓存信息字符串。"""
        mock_func = MagicMock(return_value="ok")
        wrapped = cached_llm_call(mock_func)

        info_before = wrapped.cache_info()
        # cache_info 返回一个具名元组（或类似对象），带有 hits/misses/maxsize 属性
        assert hasattr(info_before, "hits")
        assert hasattr(info_before, "misses")
        assert hasattr(info_before, "maxsize")
        assert info_before.maxsize == _MAX_CACHE_SIZE

        wrapped("a")
        wrapped("a")  # 命中
        info_after = wrapped.cache_info()
        # 至少有一次命中
        assert info_after.hits >= 1
        assert info_after.misses >= 1

    def test_wrapper_has_cache_clear_and_cache_info_attrs(self):
        """包装函数应暴露 cache_clear 和 cache_info 属性。"""
        mock_func = MagicMock(return_value="ok")
        wrapped = cached_llm_call(mock_func)

        assert callable(wrapped.cache_clear)
        assert callable(wrapped.cache_info)

    def test_max_cache_size_limit(self):
        """验证装饰器使用 _MAX_CACHE_SIZE 作为 maxsize。"""
        mock_func = MagicMock(return_value="ok")
        wrapped = cached_llm_call(mock_func)

        info = wrapped.cache_info()
        assert info.maxsize == _MAX_CACHE_SIZE


# ─── Test_get_cached_response ─────────────────────────────────────────────────


class TestGetCachedResponse:
    """测试 get_cached_response 函数。"""

    def test_returns_none(self):
        """get_cached_response 应始终返回 None。"""
        result = get_cached_response("prompt", "system")
        assert result is None

    def test_calls_increment_miss(self):
        """get_cached_response 应调用 _increment_miss。"""
        with patch("src.graph.llm_cache._increment_miss") as mock_miss:
            get_cached_response("prompt", "system")
            mock_miss.assert_called_once()

    def test_with_extra_param(self):
        """传入 extra 参数不应改变返回结果。"""
        result = get_cached_response("prompt", "system", extra="gpt-4")
        assert result is None


# ─── Test_set_cached_response ─────────────────────────────────────────────────


class TestSetCachedResponse:
    """测试 set_cached_response 函数（pass 语句覆盖）。"""

    def test_pass_no_error(self):
        """set_cached_response 的 pass 语句应正常返回，不报错。"""
        # 应正常执行，无异常
        result = set_cached_response("prompt", "system", "response", extra="v1")
        assert result is None

    def test_accepts_all_params(self):
        """函数应接受所有参数而不报错。"""
        set_cached_response("p", "s", "r")
        set_cached_response("p", "s", "r", extra=None)
        set_cached_response("p", "s", "r", extra="extra")


# ─── Test_clear_cache ─────────────────────────────────────────────────────────


class TestClearCache:
    """测试 clear_cache 函数。"""

    @patch("src.graph.llm_cache.logger")
    def test_logs_info(self, mock_logger):
        """clear_cache 应记录 info 日志。"""
        clear_cache()
        mock_logger.info.assert_called_once_with("LLM 缓存已清空")

    def test_returns_none(self):
        """clear_cache 应返回 None。"""
        result = clear_cache()
        assert result is None


# ─── Test_reset_cache_stats ───────────────────────────────────────────────────


class TestResetCacheStats:
    """测试 reset_cache_stats 函数。"""

    @patch("src.graph.llm_cache.logger")
    def test_logs_info(self, mock_logger):
        """reset_cache_stats 应记录 info 日志。"""
        reset_cache_stats()
        mock_logger.info.assert_called_once_with("缓存统计已重置")

    def test_resets_counters(self):
        """reset_cache_stats 应将所有计数器重置为零。"""
        _increment_hit()
        _increment_miss()
        _increment_eviction()
        assert get_cache_stats()["hits"] == 1

        reset_cache_stats()
        stats = get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["evictions"] == 0

    def test_creates_new_local(self):
        """reset_cache_stats 应创建新的 threading.local 实例。"""
        import threading

        from src.graph.llm_cache import _thread_stats as before

        reset_cache_stats()

        from src.graph.llm_cache import _thread_stats as after

        assert before is not after
        assert isinstance(after, threading.local)
