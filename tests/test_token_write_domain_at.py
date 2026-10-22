"""AT 轮（2026-10-21）：token 写入口的值域契约与拒绝披露。

缺陷族（前置测量，2026-10-21）：
    AI–AP 轮把 token 计数的**读端**值域收口了，但**写入口**仍无约束：

    - `record_usage(True, 5)` 把 bool 当 1 收下；`10.7` 让总量变成小数；
      `-5` / `nan` / `inf` 直接毒化累计器；`"100"` 抛 TypeError 且整次调用丢失；
    - `record_cache_hit_usage` 同样收下 bool / 小数 / 负数 / nan，
      `"9"` 在命中计数已 +1 后抛错（半截写入）；
    - `_record_response_usage` 用 `int(... or 0)` 静默归一：小数截断、数字字符串
      收下、bool→1；`"abc"` / `nan` 的 ValueError 被宽 except 吞掉（预算关时
      整次调用连 `llm_calls` 都不记）；
    - 缓存命中路径用 `int(... or 0)` 读文件 `tokens`：合法 JSON 里的坏记账值
      会让整次缓存命中退化成真实 LLM 调用（为记账字段付一次调用费）。

处置：
    - 两个写入口共享 `count_reason`；坏值**整次拒绝**（不给部分和），事件计数
      （`llm_calls` / `cache_hits`）仍 +1；拒绝机制写进 `token_write_reasons` /
      `cache_write_reasons`（只在真发生时落盘，干净 schema 逐字不变）；
    - `_record_response_usage` 不再 `int()` 归一：缺席 / null 按历史 0，其余原值
      交写入口判定；拒绝时预算开关开启则 fail-closed（O14 口径），关闭则披露后
      继续；
    - 缓存 `tokens` 原值传给写入口（不再 int 归一），坏值仍返回缓存响应；
      本次真实调用若发生写拒绝，缓存 `tokens` 记 null（未知），命中侧披露；
    - 读端（行级 / 报告级 / OTel 导出）把写拒绝标记读成不可读，部分和不得冒充
      全额。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.budget import token_usage as tu

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]
_CLEAN_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "llm_calls",
    "cache_hits",
    "cache_avoided_tokens",
    "by_model",
}
_BAD_VALUES = [
    (True, "token_not_count:input_tokens:bool"),
    (10.7, "token_not_count:input_tokens:float"),
    ("100", "token_not_count:input_tokens:str"),
    (-5, "token_negative:input_tokens"),
    (float("nan"), "token_not_finite:input_tokens"),
    (float("inf"), "token_not_finite:input_tokens"),
]


def _reason(value: object, field: str) -> str:
    code = tu.count_reason(value, field)
    assert code is not None
    return code


class TestRecordUsageWriteDomain:
    """真实调用写入口：坏值整次拒绝，事件计数保留。"""

    def setup_method(self):
        tu.reset()

    def test_valid_pair_accumulates_and_returns_no_reason(self):
        assert tu.record_usage(100, 50, model="m1") == []
        assert tu.record_usage(30, 10, model="m1") == []
        usage = tu.get_usage()
        assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (130, 60, 190)
        assert usage.llm_calls == 2
        assert usage.by_model == {"m1": 190}
        assert usage.token_write_reasons == {}

    @pytest.mark.parametrize(("value", "code"), _BAD_VALUES)
    def test_bad_input_rejects_whole_write_but_counts_call(self, value, code):
        assert tu.record_usage(value, 5) == [code]
        usage = tu.get_usage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0  # 合法字段也不给部分和
        assert usage.total_tokens == 0
        assert usage.llm_calls == 1  # 调用确实发生过
        assert usage.by_model == {}
        assert usage.token_write_reasons == {code: 1}

    def test_bad_output_rejects_whole_write(self):
        code = _reason("bad", "output_tokens")
        assert tu.record_usage(5, "bad") == [code]
        usage = tu.get_usage()
        assert usage.input_tokens == 0
        assert usage.total_tokens == 0
        assert usage.token_write_reasons == {code: 1}

    def test_both_bad_fields_record_both_mechanisms(self):
        got = tu.record_usage(True, "5")
        assert got == [
            "token_not_count:input_tokens:bool",
            "token_not_count:output_tokens:str",
        ]
        usage = tu.get_usage()
        assert usage.llm_calls == 1
        assert usage.token_write_reasons == {
            "token_not_count:input_tokens:bool": 1,
            "token_not_count:output_tokens:str": 1,
        }

    def test_rejections_accumulate_counts(self):
        code = _reason(-1, "input_tokens")
        tu.record_usage(-1, 5)
        tu.record_usage(-1, 5)
        assert tu.get_usage().token_write_reasons == {code: 2}
        assert tu.get_usage().llm_calls == 2

    def test_non_string_model_skips_attribution_not_counts(self):
        assert tu.record_usage(5, 5, model=123) == []  # type: ignore[arg-type]
        usage = tu.get_usage()
        assert usage.total_tokens == 10
        assert usage.by_model == {}

    def test_empty_and_valid_model_buckets(self):
        tu.record_usage(5, 5, model="")
        tu.record_usage(5, 5, model="m")
        assert tu.get_usage().by_model == {"m": 10}

    def test_clean_as_dict_schema_is_byte_identical(self):
        tu.record_usage(10, 5, model="m")
        assert set(tu.get_usage().as_dict()) == _CLEAN_USAGE_KEYS

    def test_rejected_as_dict_discloses_reasons_and_stays_json_safe(self):
        code = _reason(True, "input_tokens")
        tu.record_usage(True, 5)
        d = tu.get_usage().as_dict()
        assert d["token_write_reasons"] == {code: 1}
        assert json.loads(json.dumps(d))["token_write_reasons"] == {code: 1}
        assert d["total_tokens"] == 0

    def test_merge_aggregates_write_reasons(self):
        a = tu.TokenUsage(token_write_reasons={"token_negative:input_tokens": 1})
        b = tu.TokenUsage(
            token_write_reasons={
                "token_negative:input_tokens": 2,
                "token_not_count:output_tokens:str": 1,
            }
        )
        a.merge(b)
        assert a.token_write_reasons == {
            "token_negative:input_tokens": 3,
            "token_not_count:output_tokens:str": 1,
        }


class TestRecordCacheHitWriteDomain:
    """缓存命中写入口：命中计数保留，坏 avoided 不污染口径。"""

    def setup_method(self):
        tu.reset()

    def test_valid_avoided_accounts_independently(self):
        assert tu.record_cache_hit_usage(150) == []
        usage = tu.get_usage()
        assert usage.cache_hits == 1
        assert usage.cache_avoided_tokens == 150
        assert usage.total_tokens == 0
        assert usage.cache_write_reasons == {}

    def test_valid_zero_is_not_a_rejection(self):
        assert tu.record_cache_hit_usage(0) == []
        assert tu.get_usage().cache_avoided_tokens == 0
        assert tu.get_usage().cache_write_reasons == {}

    @pytest.mark.parametrize(
        ("value", "code"),
        [
            (True, "token_not_count:cache_avoided_tokens:bool"),
            (1.5, "token_not_count:cache_avoided_tokens:float"),
            ("9", "token_not_count:cache_avoided_tokens:str"),
            (-7, "token_negative:cache_avoided_tokens"),
            (float("nan"), "token_not_finite:cache_avoided_tokens"),
            (None, "token_not_count:cache_avoided_tokens:NoneType"),
        ],
    )
    def test_bad_avoided_counts_hit_only(self, value, code):
        assert tu.record_cache_hit_usage(value) == [code]
        usage = tu.get_usage()
        assert usage.cache_hits == 1
        assert usage.cache_avoided_tokens == 0
        assert usage.cache_write_reasons == {code: 1}

    def test_clean_as_dict_has_no_marker(self):
        tu.record_cache_hit_usage(42)
        assert set(tu.get_usage().as_dict()) == _CLEAN_USAGE_KEYS

    def test_rejected_as_dict_discloses_cache_reasons(self):
        code = _reason(None, "cache_avoided_tokens")
        tu.record_cache_hit_usage(None)
        d = tu.get_usage().as_dict()
        assert d["cache_write_reasons"] == {code: 1}
        assert json.loads(json.dumps(d))["cache_write_reasons"] == {code: 1}

    def test_merge_aggregates_cache_write_reasons(self):
        a = tu.TokenUsage(cache_write_reasons={"token_negative:cache_avoided_tokens": 2})
        b = tu.TokenUsage(cache_write_reasons={"token_negative:cache_avoided_tokens": 1})
        a.merge(b)
        assert a.cache_write_reasons == {"token_negative:cache_avoided_tokens": 3}


class TestWriteRejectionCount:
    """缓存 `tokens: null` 的判据：调用前后的写拒绝次数，真实与缓存两类都算。"""

    def setup_method(self):
        tu.reset()

    def test_counts_token_and_cache_rejections(self):
        assert tu.write_rejection_count() == 0
        tu.record_usage(True, 5)
        assert tu.write_rejection_count() == 1
        tu.record_cache_hit_usage("9")
        assert tu.write_rejection_count() == 2

    def test_accepted_writes_do_not_increase(self):
        assert tu.record_usage(10, 5) == []
        assert tu.record_cache_hit_usage(7) == []
        assert tu.write_rejection_count() == 0


class TestResponseUsageNormalization:
    """`_record_response_usage` 不再 int 归一：坏值披露而不是静默改写。"""

    def setup_method(self):
        tu.reset()
        # BR 轮（N02）：拒绝分支在有效预算下会锁存 budget.exceeded——这是生产
        # 语义（下一次调用必须快速失败），但会跨用例泄漏。每个用例前后都重置
        # 线程局部预算，保证断言只观察本用例的锁存状态。
        from src.budget.cost_budget import reset_budget

        reset_budget()

    def teardown_method(self):
        from src.budget.cost_budget import reset_budget

        reset_budget()

    @staticmethod
    def _record(usage: object, model: str = "m"):
        from src.agents import llm_client

        return llm_client._record_response_usage(usage, model)

    def test_clean_dict_accepted(self):
        assert self._record({"input_tokens": 10, "output_tokens": 5}) is True
        usage = tu.get_usage()
        assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (10, 5, 15)
        assert usage.token_write_reasons == {}

    def test_none_fields_keep_historical_zero(self):
        assert self._record({"input_tokens": None, "output_tokens": 5}) is True
        usage = tu.get_usage()
        assert (usage.input_tokens, usage.output_tokens) == (0, 5)

        tu.reset()
        assert self._record({"input_tokens": 5, "output_tokens": None}) is True
        usage = tu.get_usage()
        assert (usage.input_tokens, usage.output_tokens) == (5, 0)

    @pytest.mark.parametrize(("value", "code"), _BAD_VALUES)
    def test_bad_dict_values_rejected_without_exception(self, value, code):
        assert self._record({"input_tokens": value, "output_tokens": 5}) is True
        usage = tu.get_usage()
        assert usage.total_tokens == 0
        assert usage.llm_calls == 1  # 历史 "abc"/nan 连调用都丢
        assert usage.token_write_reasons == {code: 1}

    def test_non_numeric_string_no_longer_swallowed(self):
        code = _reason("abc", "input_tokens")
        assert self._record({"input_tokens": "abc", "output_tokens": 5}) is True
        assert tu.get_usage().token_write_reasons == {code: 1}
        assert tu.get_usage().llm_calls == 1

    def test_object_attributes_validated_not_truncated(self):
        from types import SimpleNamespace

        assert self._record(SimpleNamespace(prompt_tokens=12, completion_tokens=6)) is True
        assert tu.get_usage().total_tokens == 18

        tu.reset()
        assert self._record(SimpleNamespace(prompt_tokens=10.7, completion_tokens=6)) is True
        assert tu.get_usage().total_tokens == 0
        assert tu.get_usage().token_write_reasons

    def test_budget_enabled_rejects_fail_closed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("src.budget.cost_budget._budget_enabled", lambda: True)
        with pytest.raises(RuntimeError, match="fail-closed"):
            self._record({"input_tokens": True, "output_tokens": 5})
        usage = tu.get_usage()
        assert usage.llm_calls == 1
        assert usage.token_write_reasons

    def test_budget_disabled_discloses_and_continues(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("src.budget.cost_budget._budget_enabled", lambda: False)
        assert self._record({"input_tokens": True, "output_tokens": 5}) is True
        assert tu.get_usage().token_write_reasons


class TestWriteMarkerReadSide:
    """读端：写拒绝标记让该行 token / 缓存读数不可读，而不是折成小一号的和。"""

    MARKER = "token_not_count:input_tokens:bool"
    CACHE_MARKER = "token_not_count:cache_avoided_tokens:NoneType"

    @staticmethod
    def _row(**extra: object) -> dict[str, object]:
        return {
            "token_usage": {
                "total_tokens": 15,
                "input_tokens": 10,
                "output_tokens": 5,
                "llm_calls": 2,
                **extra,
            }
        }

    def test_clean_row_reading_unchanged(self):
        row = self._row()
        assert tu.row_token_counts(row) == ((15, 10, 5), [])
        assert tu.row_token_reading(row)["counts"] == (15, 10, 5)
        assert tu.row_total_token_reading(row)["total"] == 15

    def test_row_token_counts_rejects_marked_row(self):
        counts, reasons = tu.row_token_counts(self._row(token_write_reasons={self.MARKER: 1}))
        assert counts is None
        assert reasons == [f"token_write_rejected:{self.MARKER}"]

    def test_marked_zero_row_is_not_read_as_zero(self):
        row = {
            "token_usage": {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "token_write_reasons": {self.MARKER: 1},
            }
        }
        reading = tu.row_token_reading(row)
        assert reading["counts"] is None
        assert f"token_write_rejected:{self.MARKER}" in reading["reasons"]

    def test_row_total_rejects_present_valid_total(self):
        reading = tu.row_total_token_reading(self._row(token_write_reasons={self.MARKER: 1}))
        assert reading["total"] is None
        assert reading["reasons"] == [f"token_write_rejected:{self.MARKER}"]

    def test_aggregate_totals_rejects_marked_row(self):
        agg = tu.aggregate_row_token_totals([self._row(token_write_reasons={self.MARKER: 1})])
        assert agg["total_tokens"] is None
        assert agg["n_unreadable_rows"] == 1
        assert agg["reading_reasons"] == {f"token_write_rejected:{self.MARKER}": 1}

    def test_aggregate_usage_rejects_tokens_keeps_calls(self):
        agg = tu.aggregate_row_token_usage([self._row(token_write_reasons={self.MARKER: 1})])
        assert agg["total_tokens"] is None
        assert agg["input_tokens"] is None
        assert agg["output_tokens"] is None
        assert agg["llm_calls"] == 2  # 独立事实：调用确实发生过
        assert agg["reading_reasons"] == {f"token_write_rejected:{self.MARKER}": 1}

    def test_cache_caliber_marks_incomplete(self):
        usage = {
            "cache_hits": 1,
            "cache_avoided_tokens": 0,
            "cache_write_reasons": {self.CACHE_MARKER: 1},
        }
        cal = tu.cache_caliber(usage)
        assert cal["present"] is True
        assert cal["complete"] is False
        assert cal["reasons"] == [f"cache_write_rejected:{self.CACHE_MARKER}"]
        assert cal["hits"] == 1
        assert cal["avoided"] == 0

    def test_cache_totals_returns_none_for_marked_row(self):
        usage = {
            "cache_hits": 1,
            "cache_avoided_tokens": 0,
            "cache_write_reasons": {self.CACHE_MARKER: 1},
        }
        totals = tu.cache_totals([usage])
        assert totals["complete"] is False
        assert totals["hits"] is None
        assert totals["avoided"] is None
        assert totals["reasons"] == {f"cache_write_rejected:{self.CACHE_MARKER}": 1}

    def test_cache_marker_alone_marks_present(self):
        cal = tu.cache_caliber({"cache_write_reasons": {self.CACHE_MARKER: 1}})
        assert cal["present"] is True
        assert cal["complete"] is False

    def test_malformed_markers_disclosed_not_ignored(self):
        assert tu.row_token_counts(
            {"token_usage": {"total_tokens": 1, "input_tokens": 1, "output_tokens": 0, "token_write_reasons": ["x"]}}
        )[1] == ["token_write_reasons_not_object:list"]
        assert tu.cache_caliber({"cache_hits": 1, "cache_avoided_tokens": 1, "cache_write_reasons": {1: 1}})[
            "reasons"
        ] == ["cache_write_reasons_key_not_str:int"]
        assert tu.cache_caliber({"cache_hits": 1, "cache_avoided_tokens": 1, "cache_write_reasons": {"x": 0}})[
            "reasons"
        ] == ["cache_write_reasons_count_invalid:x"]

    def test_aggregate_usage_cache_marker_blocks_avoided(self):
        usage = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_hits": 1,
            "cache_avoided_tokens": 0,
            "cache_write_reasons": {self.CACHE_MARKER: 1},
        }
        agg = tu.aggregate_row_token_usage([{"token_usage": usage}])
        assert agg["total_tokens"] == 0
        assert agg["cache"]["avoided"] is None
        assert agg["cache"]["reasons"] == {f"cache_write_rejected:{self.CACHE_MARKER}": 1}


class TestOtelExportWriteMarker:
    """OTel 导出：写拒绝的 token 快照不得把部分和当全额导出。"""

    def test_marked_snapshot_exports_no_token_attributes(self):
        from src.observability.otel_export import _token_attributes

        marker = "token_not_count:input_tokens:bool"
        attrs, reasons = _token_attributes(
            {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "token_write_reasons": {marker: 1},
            }
        )
        assert attrs == {}
        assert reasons == [f"token_write_rejected:{marker}"]

    def test_clean_snapshot_unchanged(self):
        from src.observability.otel_export import _token_attributes

        attrs, reasons = _token_attributes({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        assert attrs == {
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 5,
            "gen_ai.usage.total_tokens": 15,
        }
        assert reasons == []


class TestCachePathRawTokens:
    """缓存 tokens 字段不再 int 归一：坏记账值不得毁掉一次有效缓存命中。"""

    @pytest.fixture
    def cache_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        cache_dir = tmp_path / "cache_enabled"
        cache_dir.mkdir()
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))
        from src.agents.llm_client import clear_llm_cache_option_memory

        clear_llm_cache_option_memory()
        yield cache_dir
        clear_llm_cache_option_memory()

    @staticmethod
    def _make_agent():
        from src.agents.base_agent import BaseAgent

        with (
            patch("src.agents.llm_client.ChatOpenAI") as mock_cls,
            patch("src.agents.base_agent._get_llm_config") as mock_get,
        ):
            mock_get.return_value = ("k", "u", "m")
            mock_cls.return_value = MagicMock()
            return BaseAgent("sys prompt")

    @staticmethod
    def _only_cache_file(cache_dir: Path) -> Path:
        files = list(cache_dir.glob("*.json"))
        assert len(files) == 1
        return files[0]

    @staticmethod
    def _clear_lru() -> None:
        from src.agents.base_agent import clear_llm_lru_cache

        clear_llm_lru_cache()

    def test_valid_tokens_roundtrip_unchanged(self, cache_env):
        from src.graph.token_usage import get_usage

        tu.reset()
        agent = self._make_agent()
        agent._call_llm = MagicMock(side_effect=lambda *a, **k: (tu.record_usage(100, 50), "resp")[1])
        assert agent._call_llm_with_cache("hello") == "resp"
        assert json.loads(self._only_cache_file(cache_env).read_text(encoding="utf-8"))["tokens"] == 150

        self._clear_lru()
        tu.reset()
        assert agent._call_llm_with_cache("hello") == "resp"
        assert agent._call_llm.call_count == 1
        usage = get_usage()
        assert usage.cache_hits == 1
        assert usage.cache_avoided_tokens == 150
        assert usage.cache_write_reasons == {}

    @pytest.mark.parametrize("bad", ["abc", True, 1.5, -7, None])
    def test_bad_file_tokens_still_serves_cache_and_discloses(self, cache_env, bad):
        tu.reset()
        agent = self._make_agent()
        agent._call_llm = MagicMock(return_value="resp")
        assert agent._call_llm_with_cache("hello") == "resp"
        cache_file = self._only_cache_file(cache_env)
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        payload["tokens"] = bad
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        self._clear_lru()
        tu.reset()
        assert agent._call_llm_with_cache("hello") == "resp"
        assert agent._call_llm.call_count == 1  # 不再因记账字段重调 LLM
        usage = tu.get_usage()
        assert usage.cache_hits == 1
        assert usage.cache_avoided_tokens == 0
        assert usage.cache_write_reasons

    def test_rejected_write_during_call_makes_cache_tokens_unknown(self, cache_env):
        tu.reset()
        agent = self._make_agent()

        def _call_with_bad_usage(*_args, **_kwargs):
            tu.record_usage("abc", 5)
            return "resp"

        agent._call_llm = MagicMock(side_effect=_call_with_bad_usage)
        assert agent._call_llm_with_cache("hello") == "resp"
        assert json.loads(self._only_cache_file(cache_env).read_text(encoding="utf-8"))["tokens"] is None

        self._clear_lru()
        tu.reset()
        assert agent._call_llm_with_cache("hello") == "resp"
        assert agent._call_llm.call_count == 1
        assert tu.get_usage().cache_hits == 1
        assert tu.get_usage().cache_avoided_tokens == 0
        assert tu.get_usage().cache_write_reasons


class TestRealCorpusHasNoWriteMarkers:
    """真批次 783 行：新披露键在既有工件中缺席，干净读数不变。"""

    def test_main_batch_rows_have_no_write_markers(self):
        checked_rows = 0
        for path in _MAIN_BATCH_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            for block in data["results"].values():
                for row in block["details"]:
                    usage = row.get("token_usage") or {}
                    assert "token_write_reasons" not in usage
                    assert "cache_write_reasons" not in usage
                    checked_rows += 1
        assert checked_rows == 783

    def test_main_batch_aggregate_has_no_disclosure_keys(self):
        from experiments import run_benchmark as rb

        for path in _MAIN_BATCH_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            for block in data["results"].values():
                got = rb._aggregate_token_metrics(block["details"])
                assert "n_token_unreadable_rows" not in got
                assert "cache_reading_reasons" not in got
