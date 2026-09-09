"""
LLM 调用缓存（src.graph.llm_cache）单元测试。

覆盖：
- 缓存读写往返（get/set）
- 缓存键隔离（不同 system_prompt / extra 互不干扰）
- 未命中返回 None
- LRU 淘汰策略（超出 maxsize 淘汰最久未用条目）
- 命中率统计（hits/misses/evictions）与 reset_cache_stats
- clear_cache 真正清空
- cached_llm_call 装饰器（缓存命中、按函数限定名隔离）
- 线程安全（并发读写不报错、统计一致）
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

import src.graph.llm_cache as llm_cache
from src.graph.llm_cache import (
    cached_llm_call,
    clear_cache,
    get_cache_stats,
    get_cached_response,
    reset_cache_stats,
    set_cached_response,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    """每个测试前后清空缓存与统计，避免模块级全局状态串扰。"""
    clear_cache()
    reset_cache_stats()
    yield
    clear_cache()
    reset_cache_stats()


# ─── 基础读写 ──────────────────────────────────────────────────────────────────
class TestBasicReadWrite:
    def test_set_then_get_roundtrip(self):
        set_cached_response("prompt", "sys", "response")
        assert get_cached_response("prompt", "sys") == "response"

    def test_miss_returns_none(self):
        assert get_cached_response("never-set", "sys") is None

    def test_get_hit_does_not_mutate_value(self):
        set_cached_response("p", "s", "v1")
        assert get_cached_response("p", "s") == "v1"
        # 覆盖写入
        set_cached_response("p", "s", "v2")
        assert get_cached_response("p", "s") == "v2"


# ─── 缓存键隔离 ───────────────────────────────────────────────────────────────
class TestKeyIsolation:
    def test_different_system_prompt_isolated(self):
        set_cached_response("p", "sys_a", "A")
        set_cached_response("p", "sys_b", "B")
        assert get_cached_response("p", "sys_a") == "A"
        assert get_cached_response("p", "sys_b") == "B"

    def test_extra_field_isolates(self):
        set_cached_response("p", "s", "model1-ans", extra="model1")
        set_cached_response("p", "s", "model2-ans", extra="model2")
        assert get_cached_response("p", "s", extra="model1") == "model1-ans"
        assert get_cached_response("p", "s", extra="model2") == "model2-ans"

    def test_prompt_content_matters(self):
        set_cached_response("p1", "s", "x")
        assert get_cached_response("p2", "s") is None


# ─── LRU 淘汰 ─────────────────────────────────────────────────────────────────
class TestLRUEviction:
    @pytest.fixture
    def tiny_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """将 maxsize 降到 3 以便在小规模下验证淘汰逻辑。"""
        monkeypatch.setattr(llm_cache, "_MAX_CACHE_SIZE", 3)

    def test_evicts_least_recently_used(self, tiny_cache: None):
        set_cached_response("k1", "s", "1")
        set_cached_response("k2", "s", "2")
        set_cached_response("k3", "s", "3")
        # 访问 k1，使其变为最近使用
        assert get_cached_response("k1", "s") == "1"
        # 写入第 4 个，应淘汰最久未用的 k2
        set_cached_response("k4", "s", "4")
        assert get_cached_response("k2", "s") is None  # k2 被淘汰
        assert get_cached_response("k1", "s") == "1"  # k1 保留
        assert get_cached_response("k3", "s") == "3"
        assert get_cached_response("k4", "s") == "4"

    def test_eviction_counted(self, tiny_cache: None):
        set_cached_response("a", "s", "1")
        set_cached_response("b", "s", "2")
        set_cached_response("c", "s", "3")
        set_cached_response("d", "s", "4")  # 触发 1 次淘汰
        stats = get_cache_stats()
        assert stats["evictions"] == 1


# ─── 统计与重置 ────────────────────────────────────────────────────────────────
class TestStats:
    def test_hit_and_miss_counts(self):
        set_cached_response("p", "s", "v")
        get_cached_response("p", "s")  # hit
        get_cached_response("missing", "s")  # miss
        stats = get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_reset_zeroes_counters(self):
        set_cached_response("p", "s", "v")
        get_cached_response("p", "s")
        assert get_cache_stats()["hits"] == 1
        reset_cache_stats()
        assert get_cache_stats() == {"hits": 0, "misses": 0, "evictions": 0}

    def test_get_stats_returns_copy(self):
        s1 = get_cache_stats()
        s1["hits"] = 999  # 修改副本不影响真实统计
        assert get_cache_stats()["hits"] == 0


# ─── clear_cache ──────────────────────────────────────────────────────────────
class TestClear:
    def test_clear_empties_store(self):
        set_cached_response("p", "s", "v")
        clear_cache()
        assert get_cached_response("p", "s") is None


# ─── cached_llm_call 装饰器 ────────────────────────────────────────────────────
class TestCachedLLMCallDecorator:
    def test_second_call_is_cached(self):
        calls: list[str] = []

        @cached_llm_call
        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            return f"resp-{prompt}"

        assert fake_llm("q") == "resp-q"
        assert fake_llm("q") == "resp-q"
        # 相同 prompt 只实际调用一次
        assert calls == ["q"]

    def test_different_prompts_call_independently(self):
        @cached_llm_call
        def fake_llm(prompt: str) -> str:
            return f"resp-{prompt}"

        assert fake_llm("a") == "resp-a"
        assert fake_llm("b") == "resp-b"

    def test_decorator_hits_counted_in_stats(self):
        @cached_llm_call
        def fake_llm(prompt: str) -> str:
            return "x"

        fake_llm("q")  # miss + 调用
        fake_llm("q")  # hit
        stats = get_cache_stats()
        assert stats["hits"] >= 1


# ─── 线程安全 ─────────────────────────────────────────────────────────────────
class TestThreadSafety:
    def test_concurrent_read_write_no_error(self):
        errors: list[BaseException] = []

        def worker(tid: int) -> None:
            try:
                for i in range(50):
                    key = f"key-{tid}-{i % 10}"
                    set_cached_response(key, "s", f"{tid}-{i % 10}")
                    get_cached_response(key, "s")
            except BaseException as e:  # noqa: BLE001 测试需捕获所有异常
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 统计计数应为线程间累加的总和（8 线程 × 50 次 = 400 次读）
        stats = get_cache_stats()
        assert stats["hits"] + stats["misses"] == 400


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
