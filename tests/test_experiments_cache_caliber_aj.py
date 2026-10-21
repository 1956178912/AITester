"""AJ 回归锁：缓存命中是第三种记账状态——不是记账断裂，也不是免费（2026-10-21）。

判据链：AB-11（键缺席 ≠ 值为 null）→ AB-16（什么算一个价格数字）→ AH（不完整的和
不是金额）→ AI（什么算一个 token 计数）→ **AJ：缓存命中如何参与记账**。

改前实测：`cache_hits` / `cache_avoided_tokens` 由生产者写入，但成本读端从未消费——
- S11 把"真实 token 为 0"一律读成记账断裂：quixbugs df 48/50 行、ult df 20/20 行、
  examples df 1/2 行由缓存服务，却整臂渲染 `NOT_COMPUTABLE`（成本列无数字）；
- 成本汇总与报告把缓存行读成"零 / 未计价"，纯缓存臂落一行无因的 `（缺: ）`。

处置：缓存口径单点读取（`src.budget.token_usage.cache_caliber` / `cache_totals`）——
1. 合法正向缓存证据（hits > 0 或 avoided > 0）同样算"有记账"，S11 不再误判；
2. 值域坏（负数 / 字符串 / bool / nan / inf / 半套 schema）不构成证据、不给部分和，
   机制名沿用 `token_not_count:<field>:<T>` / `token_not_finite` / `token_negative` /
   `token_field_absent`；
3. 披露键只在行内真带缓存字段时写入——主批次 / E6 / E4 的旧 schema（两个键都缺席）
   返回域与报告文本逐字不变，受保护工件不重写；
4. 真实 API 消耗仍记 0（这是正确读数），但 0 ≠ 免费：避免的 token 与命中次数
   必须与成本同读；纯缓存臂成本仍不可定价，行级原因改记 `cache_hit_no_api_spend`。

真批次读数（实测，锁定）：examples df 命中 2 / 避免 3387 tokens；quixbugs df
命中 64 / 避免 123644（48 行真实 token 为 0）；ult df 命中 39 / 避免 89249
（20/20 行真实 token 为 0，真实花费 0.0）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as report
from experiments import statistical_analysis as sa
from src.budget import token_usage as tu

_ROOT = Path(__file__).resolve().parents[1]
_OMIT = "__omit__"

_EXAMPLES = _ROOT / "experiments/results/benchmark_examples_20261012_160629.json"
_QUIXBUGS = _ROOT / "experiments/results/emse_d1_quixbugs_ab_20261013/benchmark_quixbugs_20261013_155145.json"
_ULT = _ROOT / "experiments/results/emse_ult_dfsmoke_20261017/benchmark_ult_20261017_100932.json"
_MAIN = _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json"
_EXT_ARCHIVE = _ROOT / "experiments/results/emse_stats_extensions_20261016/STATS_EXTENSIONS.json"

_PRICES: dict[str, Any] = {
    "models": {
        "m1": {
            "input_per_mtok": 1.0,
            "output_per_mtok": 2.0,
            "currency": "USD",
            "source": "test",
            "as_of": "2026-10-21",
        }
    }
}

# 改前 S11 的原文（cache-free 臂必须逐字不变——受保护报告文本一字不动）
_LEGACY_S11_REASON = (
    "2/2 行（100.0%）的 token_usage 为 0 或缺失（阈值 ≥50%）——token 记账断裂"
    "（实测形态：generated_test 非空而 llm_calls/token 全为 0），成本结论不可计算："
    "先修记账再重跑，不得在缺失记账上出 $/task 数字"
)


def _cache(hits: Any = 0, avoided: Any = 0) -> dict[str, Any]:
    return {"cache_hits": hits, "cache_avoided_tokens": avoided}


def _usage(
    total: Any = 100,
    *,
    inp: Any = 60,
    out: Any = 40,
    cache: Any = _OMIT,
    by_model: Any = _OMIT,
) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "total_tokens": total,
        "input_tokens": inp,
        "output_tokens": out,
        "llm_calls": 1,
    }
    if by_model != _OMIT:
        usage["by_model"] = by_model
    if cache != _OMIT:
        usage.update(cache)
    return usage


def _cache_only(hits: int = 1, avoided: int = 1748) -> dict[str, Any]:
    """纯缓存行：真实 token 全 0、无 by_model，命中证据非零。"""
    return _usage(0, inp=0, out=0, cache=_cache(hits, avoided), by_model={})


def _row(usage: Any = _OMIT, *, task_id: str = "t", detection: Any = 1.0) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id, "detection_rate": detection}
    if usage != _OMIT:
        row["token_usage"] = usage
    return row


def _rows_from(path: Path) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {arm: list(block["details"]) for arm, block in data["results"].items()}


def _batch(total_tasks: int, *rows: dict[str, Any], arm: str = "aitester") -> dict[str, Any]:
    return {"total_tasks": total_tasks, "results": {arm: {"details": list(rows)}}}


def _world(monkeypatch: pytest.MonkeyPatch, batch: dict[str, Any]) -> None:
    def fake_load(rel: str) -> Any:
        if rel == ext.PRICE_TABLE:
            return {"models": {"m1": _PRICES["models"]["m1"]}}
        return batch

    monkeypatch.setattr(ext, "_load", fake_load)


# ─── 1. 共享谓词（从 ext 迁到生产者模块）────────────────────────────────────


class TestSharedCountPredicate:
    @pytest.mark.parametrize("value", [0, 1, 100, 2**53])
    def test_non_negative_ints_are_counts(self, value: int) -> None:
        assert tu.count_reason(value, "cache_hits") is None

    @pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
    def test_bool_is_not_a_count(self, value: bool) -> None:
        assert tu.count_reason(value, "cache_hits") == "token_not_count:cache_hits:bool"

    def test_negative_is_named(self) -> None:
        assert tu.count_reason(-1, "cache_avoided_tokens") == "token_negative:cache_avoided_tokens"

    @pytest.mark.parametrize("value", [1.5, 100.0], ids=["fraction", "integral-float"])
    def test_float_is_not_a_count(self, value: float) -> None:
        assert tu.count_reason(value, "cache_hits") == "token_not_count:cache_hits:float"

    @pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan], ids=["inf", "-inf", "nan"])
    def test_non_finite_is_named_separately(self, value: float) -> None:
        assert tu.count_reason(value, "cache_hits") == "token_not_finite:cache_hits"

    @pytest.mark.parametrize(
        ("value", "type_name"),
        [("2", "str"), (None, "NoneType"), ([], "list"), ({}, "dict")],
    )
    def test_non_numeric_is_named(self, value: Any, type_name: str) -> None:
        assert tu.count_reason(value, "cache_hits") == f"token_not_count:cache_hits:{type_name}"

    def test_ext_alias_is_the_shared_implementation(self) -> None:
        """ext 的 AI 轮谓词只是别名——仓内只剩一份实现。"""
        assert ext.token_count_reason is tu.count_reason


# ─── 2. 行级缓存口径 ───────────────────────────────────────────────────────


class TestRowCacheCaliber:
    def test_absent_schema_is_not_zero_hits(self) -> None:
        cal = tu.cache_caliber(_usage(by_model={"m1": 100}))
        assert cal == {
            "present": False,
            "complete": False,
            "hits": 0,
            "avoided": 0,
            "evidence": False,
            "reasons": [],
            "missing": [],
        }

    def test_zero_hits_is_a_measured_zero(self) -> None:
        cal = tu.cache_caliber(_usage(cache=_cache(0, 0), by_model={"m1": 100}))
        assert cal["present"] is True
        assert cal["complete"] is True
        assert cal["evidence"] is False
        assert (cal["hits"], cal["avoided"]) == (0, 0)

    def test_hits_only_is_evidence(self) -> None:
        cal = tu.cache_caliber(_usage(0, inp=0, out=0, cache=_cache(1, 0), by_model={}))
        assert cal["evidence"] is True
        assert cal["complete"] is True
        assert (cal["hits"], cal["avoided"]) == (1, 0)

    def test_avoided_only_is_evidence(self) -> None:
        cal = tu.cache_caliber(_usage(0, inp=0, out=0, cache=_cache(0, 3387), by_model={}))
        assert cal["evidence"] is True
        assert (cal["hits"], cal["avoided"]) == (0, 3387)

    @pytest.mark.parametrize(
        ("bad", "code"),
        [
            (-1, "token_negative:cache_hits"),
            ("2", "token_not_count:cache_hits:str"),
            (True, "token_not_count:cache_hits:bool"),
            (math.nan, "token_not_finite:cache_hits"),
        ],
    )
    def test_invalid_hits_are_named_and_not_evidence(self, bad: Any, code: str) -> None:
        cal = tu.cache_caliber(_usage(0, inp=0, out=0, cache=_cache(bad, 100), by_model={}))
        assert cal["reasons"] == [code]
        assert cal["complete"] is False
        assert cal["evidence"] is True  # avoided 100 仍是合法正向证据
        assert cal["hits"] == 0

    def test_invalid_avoided_is_named_and_not_evidence(self) -> None:
        cal = tu.cache_caliber(_usage(0, inp=0, out=0, cache=_cache(0, -5), by_model={}))
        assert cal["reasons"] == ["token_negative:cache_avoided_tokens"]
        assert cal["evidence"] is False

    def test_half_schema_is_named(self) -> None:
        cal = tu.cache_caliber(_usage(0, inp=0, out=0, cache={"cache_hits": 2}, by_model={}))
        assert cal["missing"] == ["token_field_absent:cache_avoided_tokens"]
        assert cal["complete"] is False
        assert cal["evidence"] is True
        assert cal["hits"] == 2


# ─── 3. 臂级缓存汇总 ───────────────────────────────────────────────────────


class TestArmCacheTotals:
    def test_no_cache_schema_is_inert(self) -> None:
        totals = tu.cache_totals([_usage(), _usage()])
        assert totals["present"] is False
        assert totals["complete"] is False
        assert totals["hits"] is None and totals["avoided"] is None
        assert totals["n_rows_with_fields"] == 0

    def test_empty_arm(self) -> None:
        totals = tu.cache_totals([])
        assert totals["present"] is False
        assert totals["n_rows"] == 0
        assert totals["hits"] is None

    def test_all_zero_is_complete_measured_zero(self) -> None:
        totals = tu.cache_totals([_usage(cache=_cache(0, 0)), _usage(cache=_cache(0, 0))])
        assert totals["present"] is True
        assert totals["complete"] is True
        assert (totals["hits"], totals["avoided"]) == (0, 0)
        assert totals["n_hit_rows"] == 0
        assert totals["n_rows_with_fields"] == 2

    def test_sums_and_hit_rows(self) -> None:
        totals = tu.cache_totals(
            [
                _cache_only(1, 1748),
                _usage(cache=_cache(1, 1639), by_model={"m1": 100}),  # 真实调用 + 命中
                _usage(cache=_cache(0, 0)),
            ]
        )
        assert (totals["hits"], totals["avoided"]) == (2, 3387)
        assert totals["n_hit_rows"] == 2
        assert totals["n_rows_with_fields"] == 3
        assert totals["complete"] is True

    def test_partial_values_void_the_sum_not_fold(self) -> None:
        totals = tu.cache_totals([_cache_only(1, 1748), _usage(cache=_cache("2", 0))])
        assert totals["complete"] is False
        assert totals["hits"] is None and totals["avoided"] is None
        assert totals["reasons"] == {"token_not_count:cache_hits:str": 1}
        assert totals["n_hit_rows"] == 1  # 合法证据仍可数，但不参与金额

    def test_half_schema_counts_as_missing(self) -> None:
        totals = tu.cache_totals([_usage(cache={"cache_hits": 1})])
        assert totals["missing"] == {"token_field_absent:cache_avoided_tokens": 1}
        assert totals["complete"] is False
        assert totals["hits"] is None

    def test_non_object_usage_is_counted_but_does_not_void(self) -> None:
        totals = tu.cache_totals([None, "abc", _cache_only(1, 10)])
        assert totals["n_rows"] == 3
        assert totals["n_rows_with_fields"] == 1
        assert totals["complete"] is True
        assert (totals["hits"], totals["avoided"]) == (1, 10)


# ─── 4. S11 记账健全性：缓存不再是"断裂" ───────────────────────────────────


class TestS11CacheEvidence:
    def test_cache_only_arm_is_computable(self) -> None:
        rows = [_row(_cache_only(), task_id=f"t{i}") for i in range(3)]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is True
        assert sanity["n_without_accounting"] == 0
        assert sanity["n_cache_hit_rows"] == 3
        assert sanity["reason"] == ""

    def test_real_quixbugs_shape_48_of_50_no_longer_broken(self) -> None:
        """改前 48/50 无记账（96%）→ NOT_COMPUTABLE；48 行缓存命中后 50/50 有记账。"""
        rows = [_row(_cache_only()) for _ in range(48)] + [_row(_usage(by_model={"m1": 100})) for _ in range(2)]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["n_without_accounting"] == 0
        assert sanity["computable"] is True
        assert sanity["n_cache_hit_rows"] == 48

    def test_cache_fields_absent_keeps_legacy_return_domain_and_reason(self) -> None:
        rows = [_row(_usage(0, inp=0, out=0, by_model={})), _row(_usage(0, inp=0, out=0, by_model={}))]
        sanity = sa.token_accounting_sanity(rows)
        assert set(sanity) == {"n_rows", "n_without_accounting", "zero_share", "computable", "reason"}
        assert sanity["reason"] == _LEGACY_S11_REASON

    def test_invalid_cache_does_not_rescue(self) -> None:
        rows = [_row(_usage(0, inp=0, out=0, cache=_cache(-1, 0), by_model={})) for _ in range(2)]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is False
        assert sanity["n_cache_hit_rows"] == 0
        assert "缓存命中已为" not in sanity["reason"]

    def test_zero_hits_does_not_rescue(self) -> None:
        rows = [_row(_usage(0, inp=0, out=0, cache=_cache(0, 0), by_model={})) for _ in range(2)]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is False
        assert sanity["n_cache_hit_rows"] == 0

    def test_still_broken_arm_names_cache_rescued_rows(self) -> None:
        """60% 行无记账 + 40% 缓存行 → 仍判断裂，但原因必须说明缓存已救回几行。"""
        rows = [_row(_cache_only()) for _ in range(2)] + [_row(_usage(0, inp=0, out=0, by_model={})) for _ in range(3)]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is False
        assert "3/5 行（60.0%）" in sanity["reason"]
        assert "缓存命中已为 2 行提供记账" in sanity["reason"]

    def test_empty_arm_has_no_cache_key(self) -> None:
        sanity = sa.token_accounting_sanity([])
        assert sanity["computable"] is True
        assert "n_cache_hit_rows" not in sanity


# ─── 5. cost_analysis：披露键只在缓存字段在场时写入 ────────────────────────


_LEGACY_COST_KEYS = {
    "baseline",
    "n_tasks",
    "input_tokens",
    "output_tokens",
    "by_model",
    "missing_models",
    "unattributed_tokens",
    "cost",
    "cost_per_task",
    "currency",
    "priced",
    "token_accounting_ok",
    "token_accounting_reason",
    "token_zero_rows",
}


class TestCostAnalysisCache:
    def test_old_schema_return_domain_is_unchanged(self) -> None:
        rows = [_row(_usage(by_model={"m1": 100}))]
        out = sa.cost_analysis({"aitester": rows}, _PRICES)[0]
        assert set(out) == _LEGACY_COST_KEYS
        assert out["cost_per_task"] == pytest.approx(60 / 1_000_000 * 1.0 + 40 / 1_000_000 * 2.0)

    def test_cache_schema_adds_exactly_four_keys(self) -> None:
        rows = [_row(_usage(100, cache=_cache(1, 1748), by_model={"m1": 100}))]
        out = sa.cost_analysis({"aitester": rows}, _PRICES)[0]
        assert set(out) == _LEGACY_COST_KEYS | {
            "cache_hits",
            "cache_avoided_tokens",
            "cache_rows",
            "cache_hit_rows",
        }
        assert (out["cache_hits"], out["cache_avoided_tokens"]) == (1, 1748)
        assert (out["cache_rows"], out["cache_hit_rows"]) == (1, 1)
        assert out["priced"] is True

    def test_pure_cache_arm_is_unpriced_with_cause(self) -> None:
        rows = [_row(_cache_only(1, 1748)), _row(_cache_only(1, 1639))]
        out = sa.cost_analysis({"plain_llm_df": rows}, _PRICES)[0]
        assert out["priced"] is False
        assert out["cost"] is None and out["cost_per_task"] is None
        assert out["unpriced_row_reason"] == "cache_hit_no_api_spend"
        assert out["token_accounting_ok"] is True
        assert (out["cache_hits"], out["cache_avoided_tokens"]) == (2, 3387)

    def test_mixed_arm_prices_real_spend_only(self) -> None:
        rows = [
            _row(_cache_only(1, 1748)),
            _row(_usage(1_000_000, inp=1_000_000, out=0, cache=_cache(0, 0), by_model={"m1": 1_000_000})),
        ]
        out = sa.cost_analysis({"plain_llm_df": rows}, _PRICES)[0]
        assert out["priced"] is True
        assert out["cost_per_task"] == pytest.approx(0.5)  # 真实 1M input / 2 任务
        assert out.get("unpriced_row_reason") is None
        assert (out["cache_hits"], out["cache_avoided_tokens"]) == (1, 1748)

    def test_incomplete_cache_voids_amounts_and_names_mechanism(self) -> None:
        rows = [_row(_usage(100, cache=_cache("2", 0), by_model={"m1": 100}))]
        out = sa.cost_analysis({"aitester": rows}, _PRICES)[0]
        assert out["cache_hits"] is None and out["cache_avoided_tokens"] is None
        assert out["cache_reading_reasons"] == {"token_not_count:cache_hits:str": 1}

    def test_zero_cache_without_tokens_is_not_blamed_on_cache(self) -> None:
        rows = [_row(_usage(0, inp=0, out=0, cache=_cache(0, 0), by_model={}))]
        out = sa.cost_analysis({"plain_llm": rows}, _PRICES)[0]
        assert out.get("unpriced_row_reason") is None  # 无命中证据，不得声称"缓存服务"
        assert out["cache_hits"] == 0


# ─── 6. 报告呈现（statistical_analysis）────────────────────────────────────


class TestCostReportCache:
    def test_cache_free_arm_renders_no_cache_section(self) -> None:
        cost_rows = sa.cost_analysis({"aitester": [_row(_usage(1_000_000, by_model={"m1": 1_000_000}))]}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES, det_rates={"aitester": 50.0}))
        assert "缓存口径" not in text
        assert sa._cache_caliber_lines(cost_rows) == []

    def test_cache_arm_renders_hits_and_avoided(self) -> None:
        cost_rows = sa.cost_analysis({"plain_llm_df": [_row(_cache_only(2, 3387))]}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES))
        assert "**缓存口径（AJ）**" in text
        assert "命中 2 次、避免 3387 tokens" in text
        assert "0 不等于免费" in text
        assert "cache_hit_no_api_spend" in text
        assert "缓存命中：该臂真实 API 消耗为 0（由缓存服务），不是记账缺失" in text

    def test_cache_arm_no_longer_not_computable(self) -> None:
        rows = [_row(_cache_only(), task_id=f"t{i}") for i in range(3)]
        cost_rows = sa.cost_analysis({"plain_llm_df": rows}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES))
        assert "NOT_COMPUTABLE" not in text
        assert "命中 3 次、避免 5244 tokens" in text
        assert "cache_hit_no_api_spend" in text

    def test_incomplete_cache_is_disclosed_not_zeroed(self) -> None:
        rows = [_row(_usage(100, cache=_cache(-1, 0), by_model={"m1": 100}))]
        cost_rows = sa.cost_analysis({"aitester": rows}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES))
        assert "缓存读数不可用（token_negative:cache_hits←1 行）" in text
        assert "命中/避免 token 无读数（不是 0）" in text

    def test_unpriced_reason_includes_cache_reading_problem(self) -> None:
        rows = [_row(_usage(100, cache=_cache("2", 0), by_model={"m1": 100}))]
        out = sa.cost_analysis({"aitester": rows}, _PRICES)[0]
        assert "缓存读数: token_not_count:cache_hits:str←1 行" in sa._unpriced_row_reason(out)


# ─── 7. 报告呈现（emse_stats_report）──────────────────────────────────────


class TestEmseReportCache:
    def test_cost_block_old_schema_domain_unchanged(self) -> None:
        block = report.cost_block([_row(_usage(100))])
        assert set(block) == {
            "n_rows",
            "n_tokens_positive",
            "token_accounting",
            "median_tokens",
            "q1_tokens",
            "q3_tokens",
            "iqr_tokens",
            "mean_tokens",
        }
        assert set(block["token_accounting"]) == {
            "n_rows",
            "n_without_accounting",
            "zero_share",
            "computable",
            "reason",
        }

    def test_cost_block_cache_arm_discloses(self) -> None:
        rows = [_row(_cache_only()), _row(_usage(1668, cache=_cache(0, 0), by_model={"m1": 1668}))]
        block = report.cost_block(rows)
        assert (block["cache_hits"], block["cache_avoided_tokens"]) == (1, 1748)
        assert (block["n_cache_rows"], block["n_cache_hit_rows"]) == (2, 1)
        assert block["token_accounting"]["n_cache_hit_rows"] == 1

    def test_cost_block_pure_cache_arm_is_computable_with_no_median(self) -> None:
        block = report.cost_block([_row(_cache_only()), _row(_cache_only(2, 10))])
        assert block["token_accounting"]["computable"] is True
        assert block["n_tokens_positive"] == 0
        assert block["median_tokens"] is None
        assert block["n_cache_hit_rows"] == 2

    def test_cost_eff_old_schema_domain_unchanged(self) -> None:
        eff = report.cost_effectiveness_block([_row(_usage(100, by_model={"m1": 100}))], _PRICES["models"])
        assert set(eff) == {
            "total_tokens",
            "n_rows_with_tokens_positive",
            "n_priced_rows",
            "n_unpriceable_rows",
            "total_usd",
            "n_detections",
            "n_detection_measurable",
            "usd_per_detection",
            "tokens_per_detection",
        }

    def test_cost_eff_cache_arm_discloses(self) -> None:
        eff = report.cost_effectiveness_block([_row(_cache_only(1, 1748))], _PRICES["models"])
        assert (eff["cache_hits"], eff["cache_avoided_tokens"]) == (1, 1748)
        assert eff["n_cache_hit_rows"] == 1
        assert eff["n_rows_with_tokens_positive"] == 0
        assert eff["total_usd"] == 0.0  # 真实花费确实是 0——但缓存披露在旁边
        assert eff["total_tokens"] == 0.0

    def test_render_cache_free_section_has_no_cache_lines(self) -> None:
        arms = {
            "aitester": {
                "cost": report.cost_block([_row(_usage(100))]),
                "cost_eff": report.cost_effectiveness_block([_row(_usage(100))], _PRICES["models"]),
            }
        }
        text = "\n".join(report._render_cost_section(arms))
        assert "缓存口径" not in text
        assert report._render_cache_lines(arms) == []

    def test_render_cache_arm_marks_rows_and_adds_note(self) -> None:
        rows = [_row(_cache_only()), _row(_usage(1668, cache=_cache(0, 0), by_model={"m1": 1668}))]
        arms = {
            "plain_llm_df": {
                "cost": report.cost_block(rows),
                "cost_eff": report.cost_effectiveness_block(rows, _PRICES["models"]),
            }
        }
        text = "\n".join(report._render_cost_section(arms))
        assert "1 行缓存命中记账" in text
        assert "命中 1 次、避免 1748 tokens" in text
        assert "0 是真的 0，但不是免费" in text

    def test_render_not_computable_reason_mentions_cache_clause(self) -> None:
        rows = [_row(_cache_only())] + [_row(_usage(0, inp=0, out=0, by_model={})) for _ in range(3)]
        arms = {
            "plain_llm_df": {
                "cost": report.cost_block(rows),
                "cost_eff": report.cost_effectiveness_block(rows, _PRICES["models"]),
            }
        }
        text = "\n".join(report._render_cost_section(arms))
        assert "NOT_COMPUTABLE" in text
        assert "缓存命中已为 1 行提供记账" in text


# ─── 8. emse_stats_extensions：note 披露与受保护工件不变 ───────────────────


class TestExtensionsCacheNote:
    def test_old_schema_batch_has_no_cache_in_reading_or_note(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(1, _row(_usage(100, by_model={"m1": 100}))))
        reading = ext._read_tokens(["b.json"], "aitester")
        assert reading["cache"]["present"] is False
        tpt, usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert tpt == 100.0
        assert usd == pytest.approx(0.00014)
        assert "缓存" not in note

    def test_cache_batch_note_discloses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(1, _row(_cache_only(1, 1748))))
        tpt, usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert tpt == 0.0
        assert usd == 0.0
        assert "缓存口径：命中 1 次、避免 1748 tokens（1/1 行带缓存字段" in note
        assert "真实 API 消耗不含避免 token" in note

    def test_invalid_cache_note_names_mechanism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(1, _row(_usage(100, cache=_cache(-2, 0), by_model={"m1": 100}))))
        _tpt, _usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert "缓存读数不可用（token_negative:cache_hits←1 行）" in note
        assert "命中/避免 token 无读数（不是 0）" in note

    def test_archived_report_only_differs_in_registered_round_deltas(self) -> None:
        """归档案不重写：当前生成与 20261016 的差异只允许 AK note 与 AZ 两个定义字段。"""
        archived = json.loads(_EXT_ARCHIVE.read_text(encoding="utf-8"))
        fresh = ext.build_report()

        def _strip_round_deltas(report: dict) -> dict:
            out = json.loads(json.dumps(report))
            for arm in out["arms"].values():
                arm.pop("usd_note", None)
            for cmp in out["comparisons"].values():
                cmp.pop("cohens_g", None)
                cmp.pop("mcnemar_exact_p", None)
            return out

        assert _strip_round_deltas(fresh) == _strip_round_deltas(archived)
        # AZ（2026-10-21）：归档保留历史 2g / 旧精确尾；当前生成按标准定义。
        assert archived["comparisons"]["rp02_aitester_vs_df"]["cohens_g"] == pytest.approx(0.7391304347826086)
        assert fresh["comparisons"]["rp02_aitester_vs_df"]["cohens_g"] == pytest.approx(0.3695652173913043)
        assert archived["comparisons"]["rp02_df_vs_plain_llm"]["mcnemar_exact_p"] == pytest.approx(1.93144963207924e-12)
        assert fresh["comparisons"]["rp02_df_vs_plain_llm"]["mcnemar_exact_p"] == pytest.approx(1.925929944387236e-34)
        old_note = archived["arms"]["rp02_plain_llm_df"]["usd_note"]
        new_note = fresh["arms"]["rp02_plain_llm_df"]["usd_note"]
        assert new_note.startswith(old_note)
        assert "35/261 行 token 全 0" in new_note
        assert "已记录下界" in new_note
        for arm in ("rp02_aitester", "rp02_plain_llm"):
            assert fresh["arms"][arm]["usd_note"] == archived["arms"][arm]["usd_note"]


# ─── 9. 真实工件：三个曾被误判 NOT_COMPUTABLE 的臂 ─────────────────────────


class TestRealCacheArms:
    def test_examples_df(self) -> None:
        rows = _rows_from(_EXAMPLES)["plain_llm_df"]
        assert sa.token_accounting_sanity(rows)["computable"] is True
        out = sa.cost_analysis({"plain_llm_df": rows}, json.loads((_ROOT / ext.PRICE_TABLE).read_text()))
        assert (out[0]["cache_hits"], out[0]["cache_avoided_tokens"]) == (2, 3387)
        assert out[0]["cache_hit_rows"] == 2
        assert out[0].get("unpriced_row_reason") is None

    def test_quixbugs_df(self) -> None:
        rows = _rows_from(_QUIXBUGS)["plain_llm_df"]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is True
        assert sanity["n_cache_hit_rows"] == 50
        assert sanity["n_without_accounting"] == 0
        out = sa.cost_analysis({"plain_llm_df": rows}, json.loads((_ROOT / ext.PRICE_TABLE).read_text()))
        assert (out[0]["cache_hits"], out[0]["cache_avoided_tokens"]) == (64, 123644)
        assert out[0]["priced"] is True  # 2 行真实调用可计价

    def test_ult_df_pure_cache(self) -> None:
        rows = _rows_from(_ULT)["plain_llm_df"]
        sanity = sa.token_accounting_sanity(rows)
        assert (sanity["computable"], sanity["n_cache_hit_rows"]) == (True, 20)
        out = sa.cost_analysis({"plain_llm_df": rows}, json.loads((_ROOT / ext.PRICE_TABLE).read_text()))
        assert out[0]["unpriced_row_reason"] == "cache_hit_no_api_spend"
        assert (out[0]["cache_hits"], out[0]["cache_avoided_tokens"]) == (39, 89249)
        assert out[0]["token_accounting_ok"] is True

    def test_main_batch_domain_reflects_partial_accounting(self) -> None:
        """单文件主批：全记账臂返回域不变；df 臂新增 AK 下界键（8 行有产出零记账）。"""
        arms = _rows_from(_MAIN)
        price = json.loads((_ROOT / ext.PRICE_TABLE).read_text())
        for out in sa.cost_analysis(arms, price):
            expected = set(_LEGACY_COST_KEYS)
            expected_sanity = {
                "n_rows",
                "n_without_accounting",
                "zero_share",
                "computable",
                "reason",
            }
            if out["baseline"] == "plain_llm_df":
                expected |= {"token_zero_output_rows", "cost_caliber"}
                expected_sanity |= {"n_zero_output_rows"}
                assert out["cost_caliber"] == "recorded_lower_bound"
                assert out["token_zero_output_rows"] == 8
            assert set(out) == expected
            assert set(sa.token_accounting_sanity(arms[out["baseline"]])) == expected_sanity
