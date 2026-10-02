"""agents/base_agent 纯逻辑函数分支补齐（2026-10-02 批次·九）。

锁定 base_agent.py 的低覆盖纯逻辑分支（零 LLM / 零网络 / 零 subprocess）：
- _is_rate_limit_error：429 / rate limit / too many requests 关键词 /
  RateLimit 异常类名 / http_response.status_code 多路径判定
- _extract_retry_after_seconds：http_response.headers / response.headers
  两种异常形态 + 非法数值降级 None + 无响应 None
- _reorder_api_groups_by_complexity：simple/complex/medium 三档排序 +
  空组兜底 1.0 + 单实例无效果（保持历史行为）

LLM 调用（_call_llm / _call_llm_with_cache 的文件缓存路径）已有
test_base_agent_extended.py 锁定，本文件仅补纯逻辑入口。
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── _is_rate_limit_error 分支 ──────────────────────────────────────────────


class TestIsRateLimitErrorBranches:
    def _judge(self, e: BaseException) -> bool:
        from src.agents.base_agent import _is_rate_limit_error

        return _is_rate_limit_error(e)

    def test_msg_contains_429(self):
        assert self._judge(RuntimeError("HTTP 429 Too Many Requests")) is True

    def test_msg_contains_rate_limit(self):
        assert self._judge(RuntimeError("API rate limit exceeded")) is True

    def test_msg_contains_too_many_requests(self):
        assert self._judge(RuntimeError("429 too many requests")) is True

    def test_type_name_contains_ratelimit(self):
        """openai.RateLimitError 类名（含 RateLimit）匹配。"""

        class _RateLimitError(Exception):
            pass

        assert self._judge(_RateLimitError()) is True  # 类型名含 RateLimit

    def test_type_name_contains_rate_limit_snake(self):
        """SDK 变体类名 RateLimitError2 / rate_limit 变体。"""

        class _RateLimit(Exception):
            pass

        # 类名 RateLimit 不含 "RateLimit"? 实际含；再用 rate_limit 关键词兜底
        assert self._judge(_RateLimit("rate_limit retry")) is True

    def test_status_code_attr_429(self):
        """httpx.HTTPStatusError 的 status_code 属性路径（非关键词命中）。"""

        class _HttpStatusError(Exception):
            def __init__(self):
                super().__init__("server error")  # 消息无 429 关键词
                self.status_code = 429

        assert self._judge(_HttpStatusError()) is True

    def test_generic_exception_returns_false(self):
        assert self._judge(RuntimeError("普通业务错误")) is False

    def test_non_rate_status_code_returns_false(self):
        class _HttpStatusError(Exception):
            def __init__(self):
                super().__init__("server error")
                self.status_code = 500

        assert self._judge(_HttpStatusError()) is False


# ─── _extract_retry_after_seconds 分支 ───────────────────────────────────────


class TestExtractRetryAfterSecondsBranches:
    def _extract(self, e: BaseException) -> float | None:
        from src.agents.base_agent import _extract_retry_after_seconds

        return _extract_retry_after_seconds(e)

    def test_http_response_dict_header_valid(self):
        """http_response.headers（dict）携带有效 retry-after → float。"""
        exc = MagicMock()
        exc.http_response = MagicMock()
        exc.http_response.headers = {"retry-after": "42"}
        exc.response = None
        assert self._extract(exc) == 42.0

    def test_response_dict_header_valid(self):
        """response.headers（dict，SDK 变体）→ float。"""
        exc = MagicMock()
        exc.http_response = None
        exc.response = MagicMock()
        exc.response.headers = {"retry-after": "5.5"}
        assert self._extract(exc) == 5.5

    def test_invalid_header_value_returns_none(self):
        """retry-after 非数字（如 HTTP-date 格式）→ 降级 None（保守）。"""
        exc = MagicMock()
        exc.http_response = MagicMock()
        exc.http_response.headers = {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
        exc.response = None
        assert self._extract(exc) is None

    def test_no_response_returns_none(self):
        """无 http_response / response 属性 → None。"""
        exc = RuntimeError("plain")
        assert self._extract(exc) is None

    def test_headers_non_dict_returns_none(self):
        """headers 非 dict（如 httpx.Headers 对象无 .get）→ 降级 None。"""
        exc = MagicMock()
        exc.http_response = MagicMock()
        exc.http_response.headers = object()  # 非 dict，isinstance 失败
        exc.response = None
        assert self._extract(exc) is None

    def test_header_empty_string_returns_none(self):
        """空串 retry-after → 不命中 if _ra 分支 → None。"""
        exc = MagicMock()
        exc.http_response = MagicMock()
        exc.http_response.headers = {"retry-after": ""}
        exc.response = None
        assert self._extract(exc) is None


# ─── _reorder_api_groups_by_complexity 分支 ──────────────────────────────────


class TestReorderApiGroupsBranches:
    def _reorder(self, complexity: str):
        from src.agents.base_agent import _reorder_api_groups_by_complexity

        api_groups = {
            "url_expensive": [("key1", "expensive_model")],
            "url_cheap": [("key2", "cheap_model")],
            "url_empty": [],  # 空组兜底 1.0
        }
        # 构造 cost_weight 查找表（monkeypatch config.LLM_CONFIGS）
        # 直接通过 LLM_CONFIGS 注入
        import config

        saved = config.LLM_CONFIGS
        from config import LLMConfig

        config.LLM_CONFIGS = [
            LLMConfig("key1", "url_expensive", "expensive_model", cost_weight=3.0),
            LLMConfig("key2", "url_cheap", "cheap_model", cost_weight=0.5),
        ]
        try:
            return _reorder_api_groups_by_complexity(api_groups, [], complexity)
        finally:
            config.LLM_CONFIGS = saved

    def test_complex_puts_expensive_first(self):
        """complex 档：高 cost_weight 端点在前（expensive 3.0 > cheap 0.5）。"""
        out = self._reorder("complex")
        keys = list(out.keys())
        assert keys[0] == "url_expensive"
        assert keys[-1] in ("url_cheap", "url_empty")  # cheap 或 empty(1.0) 靠后

    def test_simple_puts_cheap_first(self):
        """simple 档：低 cost_weight 端点在前（cheap 0.5 最前）。"""
        out = self._reorder("simple")
        keys = list(out.keys())
        assert keys[0] == "url_cheap"

    def test_medium_sorts_by_distance_from_1(self):
        """medium 档：按 |cost-1.0| 排序（empty 1.0 距离 0 最前，cheap 0.5 距离 0.5，expensive 3.0 距离 2.0）。"""
        out = self._reorder("medium")
        keys = list(out.keys())
        # empty 组 cost 兜底 1.0 → 距离 0 → 最前
        assert keys[0] == "url_empty"
        # expensive(3.0) 距离 2.0 > cheap(0.5) 距离 0.5 → expensive 最后
        assert keys[-1] == "url_expensive"

    def test_unknown_class_treated_as_medium(self):
        """未知 complexity_class 按 medium 口径（|cost-1| 排序）。"""
        out_unknown = self._reorder("unknown_class")
        out_medium = self._reorder("medium")
        assert list(out_unknown.keys()) == list(out_medium.keys())

    def test_single_instance_no_effect(self):
        """单实例（仅 1 个非空组）排序无效果（历史行为不变）。"""
        from src.agents.base_agent import _reorder_api_groups_by_complexity

        api_groups = {"url_only": [("k", "only_model")]}
        import config

        saved = config.LLM_CONFIGS
        config.LLM_CONFIGS = [config.LLMConfig("k", "url_only", "only_model", cost_weight=2.0)]
        try:
            out = _reorder_api_groups_by_complexity(api_groups, [], "complex")
            assert list(out.keys()) == ["url_only"]
        finally:
            config.LLM_CONFIGS = saved

    def test_empty_group_cost_weight_fallback_1(self):
        """空组（无模型）cost_weight 兜底 1.0（_bw 口径）。"""
        from src.agents.base_agent import _reorder_api_groups_by_complexity

        api_groups = {"url_empty": [], "url_cheap": [("k", "cheap_model")]}
        import config

        saved = config.LLM_CONFIGS
        config.LLM_CONFIGS = [config.LLMConfig("k", "url_cheap", "cheap_model", cost_weight=0.5)]
        try:
            # simple 档：cheap(0.5) < empty(1.0 兜底) → cheap 最前
            out = _reorder_api_groups_by_complexity(api_groups, [], "simple")
            assert next(iter(out.keys())) == "url_cheap"
        finally:
            config.LLM_CONFIGS = saved

    def test_reorder_does_not_mutate_input(self):
        """原 api_groups 字典不被修改（返回新字典）。"""
        from src.agents.base_agent import _reorder_api_groups_by_complexity

        api_groups = {"u1": [("k1", "m1")], "u2": [("k2", "m2")]}
        original_keys = list(api_groups.keys())
        import config

        saved = config.LLM_CONFIGS
        config.LLM_CONFIGS = []
        try:
            _reorder_api_groups_by_complexity(api_groups, [], "complex")
        finally:
            config.LLM_CONFIGS = saved
        assert list(api_groups.keys()) == original_keys  # 原字典顺序/内容不变
