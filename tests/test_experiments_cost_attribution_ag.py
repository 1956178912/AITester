"""AG 轮（2026-10-20）：成本未计价归因收口为单一机制索引。

处置 AE 评审 §5.2（候选 C）。改前 `statistical_analysis.cost_analysis` 的两个桶
把三类事实混在一起：

- `price_null` / `price_not_finite:inf` / `price_negative` / `price_not_a_number:*`
  与"表里没登记这个模型"同进 `missing_models`——报告据此让人去登记一个**已经登记**
  的模型；
- 非对象条目与**空条目**落进名为 `unpriced_currency_models` 的桶（空条目读成
  `absent`）——照桶名去补 `currency`，补完仍是 `entry_empty`；
- 跨币种 / 跨价目组合算不出成本的行没有任何归因，只剩 `（缺: ）`。

本轮口径（全部零 LLM）：

- `pricing.model_entry_reason(models, model)` 是"模型在表内"的唯一读数：键缺席 →
  `model_unregistered`，其余交 `entry_block_reason`；`entry_block_reason` 新增
  `allow_non_usd`（成本表按登记币种原样计价，币种**不可判定**仍阻断）。
- `unpriced_model_reasons` 是完整机制索引；`missing_models`（未登记）与
  `unpriced_currency_models`（币种维，状态词汇沿用 AB-14）是互斥视图；
  `unpriced_row_reason` 承担行级 `mixed_*`。
- 报告早退分支按实际机制给标题与修复建议；纯未登记 / 无 token 观测时旧文本逐行不变。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import run_b8_injection as b8
from experiments import statistical_analysis as sa
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_RESULTS_DIR = _ROOT / "experiments" / "results"
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_E2_BATCHES = [
    "main_batch/benchmark_synthetic_20261007_170147.json",
    "main_batch/benchmark_synthetic_20261007_161053.json",
]
_INF = float("inf")
_NAN = float("nan")


@pytest.fixture(autouse=True)
def _isolate_pricing_cache():
    """模块级缓存前后复位（AA-8 同族：跨文件顺序依赖源）。"""
    pricing.reset_price_table_cache()
    yield
    pricing.reset_price_table_cache()


def _entry(currency: Any = "USD", *, inp: Any = 1.0, out: Any = 1.0) -> dict[str, Any]:
    entry: dict[str, Any] = {"input_per_mtok": inp, "output_per_mtok": out}
    if currency != "__omit__":
        entry["currency"] = currency
    return entry


def _arm(*models: str) -> dict[str, list[dict[str, Any]]]:
    """每模型 1M 输入 + 1M 输出；三元组与 by_model 求和逐行自洽（AM 口径）。

    旧夹具把 by_model 写成每模型 1M、total 固定 2M：单模型时求和 1M≠2M，
    AM 起会被判 `by_model_sum_mismatch`（矛盾数据本就不得计价）——夹具修正
    为按模型数等比放大，测的仍是币种/价目机制而非行级读取。
    """
    per_model = 2_000_000
    n = len(models)
    return {
        "aitester": [
            {
                "token_usage": {
                    "input_tokens": 1_000_000 * n,
                    "output_tokens": 1_000_000 * n,
                    "total_tokens": per_model * n,
                    "llm_calls": n,
                    "by_model": {m: per_model for m in models},
                }
            }
        ]
    }


def _row(models: dict[str, Any], used: tuple[str, ...] = ("m",)) -> dict[str, Any]:
    return sa.cost_analysis(_arm(*used), {"models": models})[0]


def _report(rows: list[dict[str, Any]], table: dict[str, Any]) -> str:
    return "\n".join(sa._cost_report_lines(rows, {"models": table}))


class TestSharedModelEntryReason:
    """缺席分支只写一遍：run_b8 与 cost_analysis 同一个读数。"""

    def test_absent_model_is_the_only_unregistered_reading(self) -> None:
        assert pricing.model_entry_reason({}, "m") == "model_unregistered"
        assert pricing.model_entry_reason({"m": None}, "m") == "entry_not_object:NoneType"
        assert pricing.model_entry_reason({"m": {}}, "m") == "entry_empty"

    def test_default_stays_usd_only(self) -> None:
        """默认口径不得因新增参数而放宽——其余六个消费点仍只收明确 USD。"""
        assert pricing.entry_block_reason(_entry("CNY")) == "currency_not_usd:CNY"
        assert pricing.entry_block_reason(_entry("USD")) is None

    def test_allow_non_usd_prices_in_its_own_unit(self) -> None:
        assert pricing.entry_block_reason(_entry("CNY"), allow_non_usd=True) is None
        assert pricing.entry_block_reason(_entry(" cny "), allow_non_usd=True) is None

    def test_allow_non_usd_still_blocks_undecidable_currency(self) -> None:
        """非 USD 放行 ≠ 没有单位也放行：不可判定仍阻断（没有单位就没有金额）。"""
        for entry in (_entry("__omit__"), _entry(None), _entry("   "), _entry(123)):
            assert pricing.entry_block_reason(entry, allow_non_usd=True) is not None

    def test_allow_non_usd_does_not_swallow_price_domain(self) -> None:
        assert pricing.entry_block_reason(_entry("CNY", inp=-1.0), allow_non_usd=True) == "price_negative"
        assert pricing.entry_block_reason(_entry("CNY", inp=_INF), allow_non_usd=True) == "price_not_finite:inf"
        # 默认口径下币种维优先：先回答"这不是美元金额"
        assert pricing.entry_block_reason(_entry("CNY", inp=-1.0)) == "currency_not_usd:CNY"

    def test_run_b8_delegates_to_shared_predicate(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            ({}, "m"),
            ({"m": None}, "m"),
            ({"m": {}}, "m"),
            ({"m": _entry("CNY")}, "m"),
            ({"m": _entry("__omit__")}, "m"),
            ({"m": _entry("USD", inp=_NAN)}, "m"),
            ({"m": _entry("USD")}, "m"),
        ]
        for table, model in cases:
            assert b8._price_entry_reason(table, model) == pricing.model_entry_reason(table, model)

    def test_single_definition_in_repo(self) -> None:
        src = (_ROOT / "src/budget/pricing.py").read_text(encoding="utf-8")
        b8_src = (_ROOT / "experiments/run_b8_injection.py").read_text(encoding="utf-8")
        assert "def model_entry_reason(" in src
        assert "def model_entry_reason(" not in b8_src
        assert "entry_block_reason(table[model])" not in b8_src


class TestCostAnalysisMechanismIndex:
    """三个披露桶互斥，完整索引是 `unpriced_model_reasons`。"""

    def test_unregistered_goes_to_missing_only(self) -> None:
        row = _row({})
        assert row["missing_models"] == ["m"]
        assert row["unpriced_model_reasons"] == {"m": "model_unregistered"}
        assert "unpriced_currency_models" not in row

    @pytest.mark.parametrize(
        ("inp", "code"),
        [
            (None, "price_null"),
            (_INF, "price_not_finite:inf"),
            (_NAN, "price_not_finite:nan"),
            (-1.0, "price_negative"),
            (True, "price_not_a_number:bool"),
            ("1.0", "price_not_a_number:str"),
        ],
        ids=["null", "inf", "nan", "negative", "bool", "str"],
    )
    def test_price_domain_never_masquerades_as_unregistered(self, inp: Any, code: str) -> None:
        row = _row({"m": _entry("USD", inp=inp)})
        assert row["missing_models"] == []
        assert row["unpriced_model_reasons"] == {"m": code}
        assert "unpriced_currency_models" not in row
        assert row["priced"] is False

    @pytest.mark.parametrize(
        ("entry", "code"),
        [
            ("oops", "entry_not_object:str"),
            (None, "entry_not_object:NoneType"),
            (7, "entry_not_object:int"),
            ({}, "entry_empty"),
        ],
        ids=["str", "null", "int", "empty"],
    )
    def test_shape_is_never_filed_under_currency(self, entry: Any, code: str) -> None:
        """改前非对象条目落进 `unpriced_currency_models`，空条目还读成 `absent`。"""
        row = _row({"m": entry})
        assert row["missing_models"] == []
        assert row["unpriced_model_reasons"] == {"m": code}
        assert "unpriced_currency_models" not in row

    @pytest.mark.parametrize(
        ("currency", "status", "code"),
        [
            ("__omit__", "absent", "currency_absent"),
            (None, "null", "currency_absent"),
            ("   ", "blank", "currency_absent"),
            (["USD"], "not_string:list", "currency_not_usd:not_string:list"),
            (123, "not_string:int", "currency_not_usd:not_string:int"),
        ],
        ids=["absent", "null", "blank", "list", "int"],
    )
    def test_currency_dimension_keeps_its_bucket(self, currency: Any, status: str, code: str) -> None:
        row = _row({"m": _entry(currency)})
        assert row["missing_models"] == []
        assert row["unpriced_currency_models"] == {"m": status}
        assert row["unpriced_model_reasons"] == {"m": code}

    def test_currency_is_the_first_blocking_dimension(self) -> None:
        """价格也坏、单位也没写 → 报币种维（补价格不会让该条目变绿）。"""
        row = _row({"m": _entry("__omit__", inp=None)})
        assert row["unpriced_model_reasons"] == {"m": "currency_absent"}
        assert row["unpriced_currency_models"] == {"m": "absent"}
        assert row["missing_models"] == []

    def test_registered_non_usd_entry_still_prices(self) -> None:
        row = _row({"m": _entry("CNY")})
        assert row["priced"] is True
        assert row["currency"] == "CNY"
        assert "unpriced_model_reasons" not in row
        assert "unpriced_currency_models" not in row

    def test_registered_non_usd_with_bad_price_reports_price_domain(self) -> None:
        row = _row({"m": _entry("CNY", inp=-1.0)})
        assert row["priced"] is False
        assert row["unpriced_model_reasons"] == {"m": "price_negative"}
        assert "unpriced_currency_models" not in row

    def test_three_buckets_partition_the_index(self) -> None:
        table = {
            "absent_model": None,  # 未实际使用，仅保证表里有别的键
            "price_null": _entry("USD", inp=None),
            "shape": "oops",
            "empty": {},
            "no_currency": _entry("__omit__"),
            "good": _entry("USD"),
        }
        row = _row(table, used=("gone", "price_null", "shape", "empty", "no_currency", "good"))
        reasons = row["unpriced_model_reasons"]
        missing = set(row["missing_models"])
        currency = set(row["unpriced_currency_models"])
        others = set(reasons) - missing - currency
        assert missing == {"gone"}
        assert currency == {"no_currency"}
        assert others == {"price_null", "shape", "empty"}
        assert missing | currency | others == set(reasons)
        assert not (missing & currency) and not (missing & others) and not (currency & others)

    def test_clean_path_adds_no_keys(self) -> None:
        row = _row({"m": _entry("USD")})
        assert row["priced"] is True
        for key in ("unpriced_model_reasons", "unpriced_currency_models", "unpriced_row_reason"):
            assert key not in row

    def test_no_token_attribution_stays_key_free(self) -> None:
        """无 by_model 的臂不是"某个模型读不出"，不得凭空造机制。"""
        usage = {"total_tokens": 10, "input_tokens": 4, "output_tokens": 6}
        rows = sa.cost_analysis({"a": [{"token_usage": usage}]}, {"models": {}})
        assert rows[0]["cost"] is None
        assert rows[0]["unattributed_tokens"] == 10
        assert rows[0]["missing_models"] == []
        assert "unpriced_model_reasons" not in rows[0]
        assert "unpriced_row_reason" not in rows[0]


class TestRowLevelReasons:
    """条目都可用却算不出成本：成因在行级，不得只剩 `（缺: ）`。"""

    def test_mixed_currencies_named(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("CNY")}
        row = _row(table, used=("a", "b"))
        assert row["priced"] is False
        assert row["unpriced_row_reason"] == "mixed_currencies:CNY/USD"
        assert "unpriced_model_reasons" not in row

    def test_mixed_price_pairs_named(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("USD", inp=2.0, out=2.0)}
        row = _row(table, used=("a", "b"))
        assert row["priced"] is False
        assert row["unpriced_row_reason"] == "mixed_price_pairs"

    def test_mixed_currencies_labels_sorted_and_joined(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("CNY"), "c": _entry("EUR")}
        row = _row(table, used=("a", "b", "c"))
        assert row["unpriced_row_reason"] == "mixed_currencies:CNY/EUR/USD"

    def test_equal_prices_same_currency_still_prices(self) -> None:
        table = {"a": _entry("usd"), "b": _entry("USD")}
        row = _row(table, used=("a", "b"))
        assert row["priced"] is True
        assert row["currency"] == "USD"
        assert "unpriced_row_reason" not in row


class TestRenderingByMechanism:
    """早退分支与逐行注：建议必须对得上机制。"""

    def test_pure_unregistered_early_return_text_is_unchanged(self) -> None:
        text = _report(sa.cost_analysis(_arm("m"), {"models": {}}), {})
        assert "**价目未登记**" in text
        assert "补齐方式：在 experiments/price_table.json 对应模型条目填入" in text
        assert "未计价机制" not in text and "成本不可计算" not in text

    def test_no_observation_early_return_text_is_unchanged(self) -> None:
        # AM：真零行（三元组全 0）仍是"无 token 观测"；部分三元组是读不动，
        # 由 tests/test_cost_aggregate_token_reading_am.py 锁定。
        usage = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        rows = sa.cost_analysis({"a": [{"token_usage": usage}]}, {"models": {}})
        text = "\n".join(sa._cost_report_lines(rows, {"models": {}}))
        assert "**价目未登记**" in text
        assert "（无 token 观测）" in text
        assert "补齐方式：在 experiments/price_table.json 对应模型条目填入" in text

    def test_price_domain_early_return_advises_price_fields(self) -> None:
        table = {"m": _entry("USD", inp=None)}
        text = _report(sa.cost_analysis(_arm("m"), {"models": table}), table)
        assert "**成本不可计算**" in text
        assert "m（price_null）" in text
        assert "价格域：`price_null` 补" in text
        assert "补齐方式（仅针对未登记模型）" not in text
        assert "币种不可判定" not in text

    def test_shape_early_return_advises_shape_not_price(self) -> None:
        table = {"m": "oops"}
        text = _report(sa.cost_analysis(_arm("m"), {"models": table}), table)
        assert "m（entry_not_object:str）" in text
        assert "条目形状：非对象条目改为对象" in text
        assert "价格域：" not in text
        assert "补齐方式（仅针对未登记模型）" not in text

    def test_currency_early_return_does_not_teach_price_fill(self) -> None:
        table = {"m": _entry("__omit__")}
        text = _report(sa.cost_analysis(_arm("m"), {"models": table}), table)
        assert "**成本不可计算**" in text
        assert "币种不可判定" in text and "absent" in text
        assert "补齐价目表的 `currency` 字段才可计价" in text
        assert "补齐方式（仅针对未登记模型）" not in text
        assert "**价目未登记**" not in text

    def test_mixed_row_early_return_names_row_level(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("CNY")}
        text = _report(sa.cost_analysis(_arm("a", "b"), {"models": table}), table)
        assert "（行级）：mixed_currencies:CNY/USD" in text
        assert "行级混算" in text
        assert "价格域：" not in text and "条目形状：" not in text

    def test_partial_note_renders_other_mechanism(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("USD", inp=None)}
        data = {"good": _arm("a")["aitester"], "bad": _arm("b")["aitester"]}
        text = _report(sa.cost_analysis(data, {"models": table}), table)
        assert "注：1 个基线未计价——bad（缺: ；未计价机制: b（price_null））。" in text

    def test_partial_note_renders_row_level(self) -> None:
        table = {"a": _entry("USD"), "b": _entry("CNY")}
        data = {"good": _arm("a")["aitester"], "mix": _arm("a", "b")["aitester"]}
        text = _report(sa.cost_analysis(data, {"models": table}), table)
        assert "注：1 个基线未计价——mix（缺: ；行级: mixed_currencies:CNY/USD）。" in text

    def test_partial_note_currency_only_text_is_unchanged(self) -> None:
        table = {"a": _entry("USD"), "b": _entry(None)}
        data = {"good": _arm("a")["aitester"], "bad": _arm("b")["aitester"]}
        text = _report(sa.cost_analysis(data, {"models": table}), table)
        assert "注：1 个基线未计价——bad（缺: ；币种不可判定: b（null））。" in text

    def test_partial_note_no_attribution_text_is_unchanged(self) -> None:
        priced_row = {
            "baseline": "good",
            "n_tasks": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "by_model": {"a": 2},
            "missing_models": [],
            "unattributed_tokens": 0,
            "cost": 1.0,
            "cost_per_task": 1.0,
            "currency": "USD",
            "priced": True,
            "token_accounting_ok": True,
        }
        unpriced_row = {
            "baseline": "empty",
            "n_tasks": 1,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
            "missing_models": [],
            "unattributed_tokens": 0,
            "cost": None,
            "cost_per_task": None,
            "currency": None,
            "priced": False,
            "token_accounting_ok": True,
        }
        text = "\n".join(sa._cost_report_lines([priced_row, unpriced_row], {"models": {}}))
        assert "注：1 个基线未计价——empty（缺: ）。" in text


class TestRealBatchInvariants:
    """真批次读数与归因面逐位不变（本轮只扩合成路径的披露）。"""

    def _real_rows(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not _RESULTS_DIR.is_dir():
            pytest.fail(f"缺工件：{_RESULTS_DIR} 不存在（真路径锁不许静默 skip）")
        table = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))
        data, srcs = sa.load_experiment_results_with_sources(str(_RESULTS_DIR), _E2_BATCHES, pool_seeds=True)
        assert len(srcs) == 2, srcs
        return sa.cost_analysis(data, table), table

    def test_real_rows_gain_no_attribution_keys(self) -> None:
        rows, _table = self._real_rows()
        by_arm = {r["baseline"]: r for r in rows}
        assert by_arm["aitester"]["priced"] is True
        for arm in ("plain_llm", "plain_llm_df", "single_agent"):
            assert by_arm[arm]["priced"] is False
            for key in ("unpriced_model_reasons", "unpriced_currency_models", "unpriced_row_reason"):
                assert key not in by_arm[arm], (arm, key)

    def test_real_cost_cell_and_note_unchanged(self) -> None:
        rows, table = self._real_rows()
        text = "\n".join(sa._cost_report_lines(rows, table))
        assert "| aitester | 174 | 662361 | 523895 | 0.0048 | USD |" in text
        assert "注：1 个基线未计价——single_agent（缺: ）。" in text

    def test_real_models_floor(self) -> None:
        data, _srcs = sa.load_experiment_results_with_sources(str(_RESULTS_DIR), _E2_BATCHES, pool_seeds=True)
        models = {
            m for rows in data.values() for r in rows for m in ((r.get("token_usage") or {}).get("by_model") or {})
        }
        assert models == {"deepseek-flash"}, models
