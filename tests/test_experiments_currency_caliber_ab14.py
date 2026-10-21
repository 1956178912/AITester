"""AB-14 回归锁：币种判定收口为单一谓词，四个站点共用（2026-10-20）。

判据链：AB-9（静默缩分母才是缺陷）→ AB-10（缺席不得报成零命中）→ AB-11（键缺席 ≠ 值为 null
≠ 读不动）→ AB-12e/AB-13（`None` 哨兵拆三态、字段名里的单位要参与判定）→ **AB-14：同一个
"这笔钱是不是美元"的判断在仓内被写了四遍且四遍互不相同（第五遍干脆没写），其中产品侧把
"币种键缺席"当成 USD**。

改前实测（`/tmp/ab14_probe.py`、`/tmp/ab14_probe2.py`，只读 + 只写 `/tmp`）：

1. `statistical_analysis.py:991` 用 `models[m].get("currency") or "USD"` 取值——键缺席、值为
   `null`、值为 `""` **三种事实一律印成 "USD"**（报告币种列里的单位是代码编的，不是登记的）。
2. 同处 `currencies` 是**大小写敏感**的集合：`USD` 与 `usd` 并存时 `len(currencies) == 2`
   ⇒ 成本整臂降为 `None`，而 `missing_models` 为空 ⇒ 报告落一行"未计价——（缺: ）"（无因）。
3. 同处币种为非字符串时：`123` 原样流进单元格（`_currency_cell` 声明返回 `str`）；
   `["USD"]` 让 `set` 推导抛 `TypeError` ⇒ 实测 CLI 退出码 1、**整份统计报告不产出**。
4. `src/budget/pricing.py:103` 用 `entry.get("currency", "USD")`——缺席默认成 USD，
   与 `null`（不计价）**在同一站点给出相反读数**；而 `spec_examples_generator.py:337` 与
   `emse_stats_report.py:576` 用 `or ""` + `.upper()`，缺席一律剔除。四站点三套口径。
5. 形状：`statistical_analysis.cost_analysis` 要 `{"models": …}` 包装体，
   `emse_stats_report.cost_effectiveness_block` 要 models 层映射；把映射直传给前者时
   `missing_models` 会列出**其实已登记**的模型名，报告据此让人去补一份本来就补好了的价目表。
6. 第五处 `analyze_t1_b2_main_batch.add_cost` 读 `input_per_mtok` / `output_per_mtok` 却
   **从不读 `currency`**，非 USD（或没登记单位）的价目被原样累加进名为 `cost_usd` 的字段——
   与 AB-13c 在 `total_usd` 上坐实的缺陷同型，只是这里连"判错了"都算不上，是**没判**。

处置口径：**判定只写一遍**（`src.budget.pricing.currency_status`），五处全部接过去；
缺席 / `null` / 空白 / 非字符串一律"币种不可判定"，不得当成任何单位；`other:X` 在带币种列的
统计报告里仍可计价但标签必须是归一化后的 `X`；返回域只增不改，键只在真发生时写入。

真批次不变量：e2 / e2_iter 两份受 `SHA256SUMS` 保护的报告只用到 `deepseek-flash`
（币种精确登记为 `USD`），本轮改动**改变 0 行**——现码复算文本由真路径锁逐行钉住。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from experiments import analyze_t1_b2_main_batch as t1b2
from experiments import emse_stats_report as rep
from experiments import spec_examples_generator as seg
from experiments import statistical_analysis as sa
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_RESULTS_DIR = _ROOT / "experiments" / "results"
_E2_BATCHES = [
    "main_batch/benchmark_synthetic_20261007_170147.json",
    "main_batch/benchmark_synthetic_20261007_161053.json",
]


@pytest.fixture(autouse=True)
def _isolate_pricing_cache():
    """价目表缓存与回退价旋钮都必须前后复位（H1/AA-8 同族：模块级状态泄漏是跨文件顺序依赖源）。"""
    pricing.reset_price_table_cache()
    yield
    pricing.reset_price_table_cache()


def _entry(currency: Any = "__omit__", **kw: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"input_per_mtok": 1.0, "output_per_mtok": 2.0}
    entry.update(kw)
    if currency != "__omit__":
        entry["currency"] = currency
    return entry


def _arm(model: str = "m", *, in_tok: int = 1_000_000, out_tok: int = 1_000_000) -> dict[str, list[dict[str, Any]]]:
    return {
        "aitester": [
            {
                "token_usage": {
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                    "llm_calls": 1,
                    "by_model": {model: in_tok + out_tok},
                }
            }
        ]
    }


def _stat_row(table: dict[str, Any], model: str = "m") -> dict[str, Any]:
    rows = sa.cost_analysis(_arm(model), table)
    return rows[0]


def _rep_block(table: dict[str, Any], model: str = "m") -> dict[str, Any]:
    return rep.cost_effectiveness_block([_row_rep(model)], price_table=table)


def _row_rep(model: str) -> dict[str, Any]:
    return {
        "detection_rate": 1.0,
        "token_usage": {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "total_tokens": 2_000_000,
            "llm_calls": 1,
            "by_model": {model: 2_000_000},
        },
    }


def _seg_cost(table: dict[str, Any], model: str = "m") -> float | None:
    return seg.estimate_cost_usd(model, {"input_tokens": 1_000_000, "output_tokens": 1_000_000}, price_table=table)


# 币种字段取值 → 归一化状态（单一谓词的值域，改前四站点给不出这张表）
STATUS_CASES: list[tuple[str, Any, str]] = [
    ("absent", "__omit__", "absent"),
    ("null", None, "null"),
    ("empty", "", "blank"),
    ("spaces", "   ", "blank"),
    ("usd", "USD", "usd"),
    ("lower", "usd", "usd"),
    ("padded", " USD ", "usd"),
    ("cny", "CNY", "other:CNY"),
    ("lower_cny_padded", " cny", "other:CNY"),
    ("int", 123, "not_string:int"),
    ("bool", True, "not_string:bool"),
    ("list", ["USD"], "not_string:list"),
    ("dict", {}, "not_string:dict"),
]


class TestCurrencyStatusDomain:
    """币种谓词的值域：六种事实必须给出六个互不相同的读数。"""

    @pytest.mark.parametrize("tag,value,expected", STATUS_CASES, ids=[c[0] for c in STATUS_CASES])
    def test_status_domain(self, tag: str, value: Any, expected: str) -> None:
        assert pricing.currency_status(_entry(value)) == expected

    @pytest.mark.parametrize("value", [None, [], "x", 5, 0], ids=["none", "list", "str", "int", "zero"])
    def test_entry_not_object_is_named_by_type(self, value: Any) -> None:
        status = pricing.currency_status(value)
        assert status == f"entry_not_object:{type(value).__name__}"

    def test_all_statuses_are_distinct(self) -> None:
        """13 个取值落在 9 个互不相同的读数上；任何两族合并都算口径塌缩。"""
        statuses = {pricing.currency_status(_entry(v)) for _, v, _ in STATUS_CASES}
        assert statuses == {
            "absent",
            "null",
            "blank",
            "usd",
            "other:CNY",
            "not_string:int",
            "not_string:bool",
            "not_string:list",
            "not_string:dict",
        }, sorted(statuses)

    def test_absent_and_null_are_different_readings(self) -> None:
        """AB-11 口径：键缺席与值为 null 不得挤进同一个桶。"""
        assert pricing.currency_status(_entry()) == "absent"
        assert pricing.currency_status(_entry(None)) == "null"

    def test_is_usd_entry_true_only_for_usd(self) -> None:
        true_cases = [v for _, v, s in STATUS_CASES if s == "usd"]
        assert [v for _, v, _ in STATUS_CASES if pricing.is_usd_entry(_entry(v))] == true_cases

    def test_reason_free_status_never_says_usd_on_absence(self) -> None:
        """缺席 / null / 空白 三种"没登记单位"的事实一律不得被读成美元。"""
        for tag in ("absent", "null", "empty", "spaces"):
            value = next(v for t, v, _ in STATUS_CASES if t == tag)
            assert pricing.currency_status(_entry(value)) != "usd"


class TestFourSitesAgree:
    """四站点共用同一判定：同一个条目在四处得到的"是不是美元"必须一致。"""

    @pytest.mark.parametrize("tag,value,expected", STATUS_CASES[:12], ids=[c[0] for c in STATUS_CASES[:12]])
    def test_pricing_site_follows_predicate(self, tag: str, value: Any, expected: str) -> None:
        assert (pricing._usd_prices(_entry(value)) is not None) == (expected == "usd")

    @pytest.mark.parametrize("tag,value,expected", STATUS_CASES[:12], ids=[c[0] for c in STATUS_CASES[:12]])
    def test_seg_site_follows_predicate(self, tag: str, value: Any, expected: str) -> None:
        got = _seg_cost({"models": {"m": _entry(value)}})
        assert (got is not None) == (expected == "usd")

    @pytest.mark.parametrize("tag,value,expected", STATUS_CASES[:12], ids=[c[0] for c in STATUS_CASES[:12]])
    def test_stats_site_follows_predicate(self, tag: str, value: Any, expected: str) -> None:
        row = _stat_row({"models": {"m": _entry(value)}})
        assert row["priced"] == (expected in ("usd", "other:CNY"))
        if expected == "usd":
            assert row["currency"] == "USD"
        elif expected == "other:CNY":
            assert row["currency"] == "CNY"
        else:
            assert row["currency"] is None

    @pytest.mark.parametrize("tag,value,expected", STATUS_CASES[:12], ids=[c[0] for c in STATUS_CASES[:12]])
    def test_report_site_follows_predicate(self, tag: str, value: Any, expected: str) -> None:
        out = _rep_block({"m": _entry(value)})
        assert out["n_priced_rows"] == (1 if expected == "usd" else 0)

    def test_four_sites_never_disagree_on_usd_verdict(self) -> None:
        for _, value, _ in STATUS_CASES:
            entry = _entry(value)
            pricing_verdict = pricing._usd_prices(entry) is not None
            seg_verdict = _seg_cost({"models": {"m": entry}}) is not None
            report_verdict = _rep_block({"m": entry})["n_priced_rows"] == 1
            assert (
                pricing_verdict
                == seg_verdict
                == report_verdict
                == (entry.get("currency") == "USD" or entry.get("currency") in ("usd", " USD "))
            ), value

    def test_seg_non_object_entry_is_none_not_crash(self) -> None:
        """条目写成列表时改前崩在 `entry.get`；现在按 `entry_not_object:list` 计不可判定。"""
        assert _seg_cost({"models": {"m": ["USD"]}}) is None


class TestPricingSiteIsNotFabricatingUsd:
    """产品侧 `src/budget/pricing.py`：币种键缺席不再被当成 USD。"""

    def test_absent_currency_yields_no_price(self) -> None:
        assert pricing._usd_prices({"input_per_mtok": 1.0, "output_per_mtok": 2.0}) is None

    def test_absent_currency_falls_back_not_price_table(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        table = tmp_path / "price_table.json"
        table.write_text(
            json.dumps({"models": {"m": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", table)
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        pricing.reset_price_table_cache()
        assert pricing.estimate_usd("m", 1_000_000, 1_000_000) == (None, "unpriced")

    def test_fallback_knob_still_wins_when_currency_undecidable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """回退价是既有设计（文档写明优先级），本轮只取消"缺席当 USD"，不动回退路径。"""
        table = tmp_path / "price_table.json"
        table.write_text(
            json.dumps({"models": {"m": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", table)
        monkeypatch.setenv("COST_USD_PER_1K", "0.002")
        pricing.reset_price_table_cache()
        usd, source = pricing.estimate_usd("m", 1_000_000, 1_000_000)
        assert (source, usd) == ("cost_usd_per_1k", 4.0)

    def test_registered_usd_entry_still_prices(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        table = tmp_path / "price_table.json"
        table.write_text(
            json.dumps({"models": {"m": {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "currency": "usd"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", table)
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        pricing.reset_price_table_cache()
        assert pricing.estimate_usd("m", 1_000_000, 1_000_000)[0] == pytest.approx(3.0)


class TestStatisticalCurrencyMechanisms:
    """统计站点：币种不可判定不得印成 USD，也不得让整份报告消失。"""

    def test_absent_currency_no_longer_prints_usd(self) -> None:
        row = _stat_row({"models": {"m": _entry()}})
        assert row["currency"] is None
        assert row["priced"] is False
        assert row["unpriced_currency_models"] == {"m": "absent"}

    def test_null_currency_is_a_separate_reading(self) -> None:
        assert _stat_row({"models": {"m": _entry(None)}})["unpriced_currency_models"] == {"m": "null"}

    def test_blank_currency_is_a_separate_reading(self) -> None:
        assert _stat_row({"models": {"m": _entry("  ")}})["unpriced_currency_models"] == {"m": "blank"}

    def test_non_string_currency_does_not_kill_the_report(self) -> None:
        """改前实测：`["USD"]` 让 cost_analysis 抛 TypeError ⇒ CLI 退出码 1、报告不产出。"""
        row = _stat_row({"models": {"m": _entry(["USD"])}})
        assert row["priced"] is False
        assert row["unpriced_currency_models"] == {"m": "not_string:list"}

    def test_int_currency_is_blocked_and_not_labeled(self) -> None:
        """值是 int 时既不能计价、更不能把 123 当成某种单位印出去。"""
        row = _stat_row({"models": {"m": _entry(123)}})
        assert row["currency"] is None
        assert row["priced"] is False
        assert row["unpriced_currency_models"] == {"m": "not_string:int"}

    def test_cny_entry_prices_with_normalized_label(self) -> None:
        row = _stat_row({"models": {"m": _entry(" cny")}})
        assert row["priced"] is True
        assert row["currency"] == "CNY"
        assert row["cost"] == pytest.approx(3.0)

    def test_mixed_case_models_price_instead_of_collapsing(self) -> None:
        """改前实测：USD + usd 两模型 ⇒ 币种集合大小 2 ⇒ 整臂成本 None 且无原因。"""
        table = {"models": {"a": _entry("USD"), "b": _entry("usd")}}
        rows = sa.cost_analysis(
            {
                "aitester": [
                    {
                        "token_usage": {
                            "input_tokens": 1_000_000,
                            "output_tokens": 1_000_000,
                            "total_tokens": 2_000_000,
                            "llm_calls": 1,
                            "by_model": {"a": 1_000_000, "b": 1_000_000},
                        }
                    }
                ]
            },
            table,
        )
        assert rows[0]["priced"] is True
        assert rows[0]["currency"] == "USD"

    def test_usd_plus_undecidable_arm_refuses_to_price_even_at_equal_prices(self) -> None:
        """混臂里一个模型登记 USD、另一个没写单位，且两者价目数字一字相同：
        `missing` 空、`labels` 只有 {USD}（大小 1）⇒ 闸门里**只有** `not currency_blocked`
        这一 term 能挡住计价。删掉它会把"没登记单位"的那半臂并进美元成本。"""
        table = {"models": {"a": _entry("USD"), "b": _entry()}}
        rows = sa.cost_analysis(
            {
                "aitester": [
                    {
                        "token_usage": {
                            "input_tokens": 1_000_000,
                            "output_tokens": 1_000_000,
                            "total_tokens": 2_000_000,
                            "llm_calls": 1,
                            "by_model": {"a": 1_000_000, "b": 1_000_000},
                        }
                    }
                ]
            },
            table,
        )
        assert rows[0]["priced"] is False and rows[0]["cost"] is None
        assert rows[0]["unpriced_currency_models"] == {"b": "absent"}

    def test_two_different_currencies_still_refuse_to_sum(self) -> None:
        table = {"models": {"a": _entry("USD"), "b": _entry("CNY")}}
        rows = sa.cost_analysis(
            {
                "aitester": [
                    {
                        "token_usage": {
                            "input_tokens": 1_000_000,
                            "output_tokens": 1_000_000,
                            "total_tokens": 2_000_000,
                            "llm_calls": 1,
                            "by_model": {"a": 1_000_000, "b": 1_000_000},
                        }
                    }
                ]
            },
            table,
        )
        assert rows[0]["priced"] is False
        assert "unpriced_currency_models" not in rows[0]

    def test_bucket_counts_partition_blocked_models(self) -> None:
        table = {"models": {"a": _entry(), "b": _entry(None), "c": _entry("  "), "d": _entry([1])}}
        rows = sa.cost_analysis(
            {
                "aitester": [
                    {
                        "token_usage": {
                            "input_tokens": 2_000_000,
                            "output_tokens": 2_000_000,
                            "total_tokens": 4_000_000,
                            "llm_calls": 1,
                            "by_model": {"a": 1_000_000, "b": 1_000_000, "c": 1_000_000, "d": 1_000_000},
                        }
                    }
                ]
            },
            table,
        )
        blocked = rows[0]["unpriced_currency_models"]
        assert sorted(blocked.values()) == ["absent", "blank", "not_string:list", "null"]
        assert len(blocked) == 4

    def test_price_missing_and_currency_missing_are_not_merged(self) -> None:
        """价格域与币种维分桶记账（AG 起 `missing_models` 只收**表内未登记**）。

        AG（2026-10-20）口径变更：表内条目的价格坏值不再冒充"未登记"，进
        `unpriced_model_reasons`；币种维仍进 `unpriced_currency_models`（状态词汇沿用
        AB-14）。三个桶互斥，完整索引是 `unpriced_model_reasons`。
        """
        table = {
            "models": {
                "priced_no_cur": _entry(),
                "no_price": {"currency": "USD", "input_per_mtok": None, "output_per_mtok": None},
            }
        }
        rows = sa.cost_analysis(
            {
                "aitester": [
                    {
                        "token_usage": {
                            "input_tokens": 1_000_000,
                            "output_tokens": 1_000_000,
                            "total_tokens": 2_000_000,
                            "llm_calls": 1,
                            "by_model": {"priced_no_cur": 1_000_000, "no_price": 1_000_000},
                        }
                    }
                ]
            },
            table,
        )
        assert rows[0]["missing_models"] == []
        assert rows[0]["unpriced_currency_models"] == {"priced_no_cur": "absent"}
        assert rows[0]["unpriced_model_reasons"] == {
            "no_price": "price_null",
            "priced_no_cur": "currency_absent",
        }

    def test_clean_path_return_domain_is_a_superset_only(self) -> None:
        """只增不改：币种可判定时不写新键（受保护文本因此逐行不变）。"""
        row = _stat_row({"models": {"m": _entry("USD")}})
        assert "unpriced_currency_models" not in row
        assert row["currency"] == "USD"


class TestPriceTableShapeDisclosure:
    """形状错传不得再被归因成"价目未登记"（AB-11 归因错位）。"""

    def test_mapping_directly_passed_is_named_as_shape(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = sa.cost_analysis(_arm("deepseek-flash"), {"deepseek-flash": _entry("USD")})
        out = capsys.readouterr().out
        assert rows[0]["priced"] is False
        assert "models_key_absent" in out
        assert '不是"价目未登记"' in out

    def test_non_object_table_is_named_by_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        sa.cost_analysis(_arm("m"), ["nope"])  # type: ignore[arg-type]
        assert "price_table_not_object:list" in capsys.readouterr().out

    def test_models_value_non_object_is_named(self, capsys: pytest.CaptureFixture[str]) -> None:
        sa.cost_analysis(_arm("m"), {"models": 5})  # type: ignore[dict-item]
        assert "models_not_object:int" in capsys.readouterr().out

    def test_models_key_absent_but_table_empty_is_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        """空对象没有形状可说——"真的没登记"仍须与"传错形状"分得开。"""
        sa.cost_analysis(_arm("m"), {"models": {}})
        assert capsys.readouterr().out == ""

    def test_clean_wrapper_is_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        sa.cost_analysis(_arm("m"), {"models": {"m": _entry("USD")}})
        assert capsys.readouterr().out == ""

    def test_shape_disclosure_does_not_change_return_domain(self) -> None:
        rows = sa.cost_analysis(_arm("m"), ["nope"])  # type: ignore[arg-type]
        assert rows[0]["cost"] is None and rows[0]["priced"] is False


class TestCostSectionRendering:
    """呈现层：单位提醒只在真出现非 USD 计价行时落字；0 机制时文本逐行不变。"""

    def test_non_usd_priced_row_triggers_unit_note(self) -> None:
        table = {"models": {"m": _entry("CNY")}}
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(_arm(), table), table))
        assert "单位提醒" in text
        assert "CNY" in text

    def test_usd_only_render_has_no_unit_note(self) -> None:
        table = {"models": {"m": _entry("USD")}}
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(_arm(), table), table))
        assert "单位提醒" not in text

    def test_blocked_currency_render_names_the_mechanism(self) -> None:
        table = {"models": {"m": _entry()}}
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(_arm(), table), table))
        assert "币种不可判定" in text and "absent" in text

    def test_hand_written_row_with_non_string_currency_renders_str_cell(self) -> None:
        rows = [
            {
                "baseline": "b",
                "n_tasks": 1,
                "input_tokens": 1,
                "output_tokens": 1,
                "by_model": {},
                "missing_models": [],
                "unattributed_tokens": 0,
                "cost": 1.0,
                "cost_per_task": 1.0,
                "currency": 123,
                "priced": True,
            }
        ]
        text = "\n".join(sa._cost_report_lines(rows, {"models": {}}))
        assert "| b | 1 | 1 | 1 | 1.0000 | 123 |" in text

    def test_no_mechanism_early_return_text_is_unchanged(self) -> None:
        """真未登记（表里没有该模型）时不得多落一行币种点名——那是另一种机制。"""
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(_arm(), {"models": {}}), {"models": {}}))
        assert "价目未登记" in text and "币种不可判定" not in text

    def test_mixed_arms_name_currency_blockage_next_to_price_gap(self) -> None:
        """一臂可计价、一臂因币种被剔 ⇒ 未计价注里要点出"缺单位"，不能只说"缺价格"。"""
        table = {"models": {"a": _entry("USD"), "b": _entry(None)}}
        data = {"aitester": _arm("a")["aitester"], "plain_llm": _arm("b")["aitester"]}
        text = "\n".join(sa._cost_report_lines(sa.cost_analysis(data, table), table))
        assert "注：1 个基线未计价——plain_llm（缺: ；币种不可判定: b（null））。" in text

    def test_zero_mechanism_render_is_line_for_line_stable(self) -> None:
        table = {"models": {"m": _entry("USD")}}
        first = sa._cost_report_lines(sa.cost_analysis(_arm(), table), table)
        second = sa._cost_report_lines(sa.cost_analysis(_arm(), table), table)
        assert first == second and len(first) == 8
        assert first[-1] == "| aitester | 1 | 1000000 | 1000000 | 3.0000 | USD |"


class TestReportSiteReasonCodes:
    """币种判定接到共享谓词后，AB-13 登记的 reason 码词汇表不得改名。"""

    REASON_CASES: ClassVar[list[tuple[str, Any, str]]] = [
        ("absent", "__omit__", "currency_absent"),
        ("null", None, "currency_absent"),
        ("blank", "   ", "currency_absent"),
        ("cny", "CNY", "currency_not_usd:CNY"),
        ("padded_cny", " cny ", "currency_not_usd:CNY"),
        ("int", 123, "currency_not_usd:not_string:int"),
        ("list", ["USD"], "currency_not_usd:not_string:list"),
    ]

    @pytest.mark.parametrize("tag,value,reason", REASON_CASES, ids=[c[0] for c in REASON_CASES])
    def test_reason_code_vocabulary_is_unchanged(self, tag: str, value: Any, reason: str) -> None:
        out = _rep_block({"m": _entry(value)})
        assert out["n_priced_rows"] == 0 and out["total_usd"] == 0.0, tag
        assert out["n_unpriceable_reasons"] == {reason: 1}, tag

    def test_usd_entry_still_leaves_no_reason_key(self) -> None:
        out = _rep_block({"m": _entry("USD")})
        assert out["n_priced_rows"] == 1 and "n_unpriceable_reasons" not in out


class TestFifthSiteIsNotCurrencyBlind:
    """第五处 `analyze_t1_b2_main_batch.add_cost` 改前**根本不判币种**（不是判得不同，是没判）。"""

    @staticmethod
    def _stats() -> dict[str, Any]:
        return {"cost_usd": None, "token_metrics": {"total_input_tokens": 1_000_000, "total_output_tokens": 1_000_000}}

    @pytest.mark.parametrize(
        "tag,value",
        [("absent", "__omit__"), ("cny", "CNY"), ("blank", ""), ("list", ["USD"])],
        ids=["absent", "cny", "blank", "list"],
    )
    def test_undecidable_or_non_usd_leaves_cost_none(self, tag: str, value: Any) -> None:
        stats = self._stats()
        t1b2.add_cost(stats, _entry(value))
        assert stats["cost_usd"] is None, tag

    def test_registered_usd_entry_prices(self) -> None:
        stats = self._stats()
        t1b2.add_cost(stats, _entry(" usd "))
        assert stats["cost_usd"] == pytest.approx(3.0)

    def test_non_object_price_entry_is_named_not_crashed(self) -> None:
        """改前 `price.get` 在这里抛 AttributeError（价目表里模型条目写成列表即可复现）。"""
        stats = self._stats()
        t1b2.add_cost(stats, ["USD"])
        assert stats["cost_usd"] is None


class TestRealBatchReadingsUnchanged:
    """真路径不变量：两份受保护报告的现码复算文本必须逐行不动（本轮改变 0 行）。"""

    def _real_rows(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not _RESULTS_DIR.is_dir():
            pytest.fail(f"缺工件：{_RESULTS_DIR} 不存在（真路径锁不许静默 skip）")
        table = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))
        data, srcs = sa.load_experiment_results_with_sources(str(_RESULTS_DIR), _E2_BATCHES, pool_seeds=True)
        assert len(srcs) == 2, srcs
        return sa.cost_analysis(data, table), table

    def test_covered_rows_and_models_floor(self) -> None:
        data, _srcs = sa.load_experiment_results_with_sources(str(_RESULTS_DIR), _E2_BATCHES, pool_seeds=True)
        total = sum(len(v) for v in data.values())
        assert total >= 500, total
        models = {
            m for rows in data.values() for r in rows for m in ((r.get("token_usage") or {}).get("by_model") or {})
        }
        assert models == {"deepseek-flash"}, models

    def test_real_arm_rows_bit_for_bit(self) -> None:
        rows, _table = self._real_rows()
        by_arm = {r["baseline"]: r for r in rows}
        assert by_arm["aitester"]["cost"] == pytest.approx(0.8273823, abs=5e-7)
        assert by_arm["aitester"]["currency"] == "USD"
        assert by_arm["aitester"]["priced"] is True
        for arm in ("plain_llm", "plain_llm_df", "single_agent"):
            assert by_arm[arm]["priced"] is False and by_arm[arm]["currency"] is None
            assert "unpriced_currency_models" not in by_arm[arm]

    def test_real_cost_cell_and_note_are_unchanged(self) -> None:
        rows, table = self._real_rows()
        text = "\n".join(sa._cost_report_lines(rows, table))
        assert "| aitester | 174 | 662361 | 523895 | 0.0048 | USD |" in text
        assert "注：1 个基线未计价——single_agent（缺: ）。" in text
        assert "单位提醒" not in text

    def test_real_price_table_currencies_unchanged(self) -> None:
        table = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))["models"]
        assert table["deepseek-flash"]["currency"] == "USD"
        assert table["qwen-long"]["currency"] == "CNY"
        assert pricing.currency_status(table["deepseek-flash"]) == "usd"
        assert pricing.currency_status(table["qwen-long"]) == "other:CNY"

    def test_protected_reports_not_rewritten(self) -> None:
        sums = _RESULTS_DIR / "main_batch" / "SHA256SUMS"
        if not sums.is_file():
            pytest.fail(f"缺工件：{sums}")
        lines = sums.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 2000, len(lines)
        for name in ("statistical_report_e2.md", "statistical_report_e2_iter.md"):
            assert (_RESULTS_DIR / "main_batch" / name).is_file(), name

    def test_no_pragma_used_to_hide_new_branches(self) -> None:
        src = (_ROOT / "src" / "budget" / "pricing.py").read_text(encoding="utf-8")
        assert "# pragma: no cover" not in src


class TestCallSitesWired:
    """接线锁：站点必须真的调用共享谓词，而不是又抄一遍判定。"""

    def test_pricing_module_exposes_the_predicate(self) -> None:
        assert callable(pricing.currency_status) and callable(pricing.is_usd_entry)

    def test_experiment_sites_import_the_predicate(self) -> None:
        """接线锁（AB-16 更新口径）：站点必须真的接共享判定，而不是又抄一遍域。

        AB-16 把条目准入（形状+币种+数字）收口到 `entry_block_reason`；
        `statistical_analysis` 的数字域走模块限定 `pricing.price_block_reason`，
        其币种读数仍经 `pricing.currency_status`（行级三态）。
        """
        expectations = {
            "experiments/statistical_analysis.py": ("price_block_reason", "currency_status"),
            "experiments/spec_examples_generator.py": ("entry_block_reason",),
            "experiments/emse_stats_report.py": ("entry_block_reason",),
            "experiments/analyze_t1_b2_main_batch.py": ("entry_block_reason",),
        }
        for rel, needles in expectations.items():
            text = (_ROOT / rel).read_text(encoding="utf-8")
            for needle in needles:
                assert needle in text, (rel, needle)

    def test_no_site_keeps_the_or_default_currency(self) -> None:
        """改前四条各自实现的兜底写法必须全部消失（否则口径又分一遍）。"""
        for rel in (
            "experiments/statistical_analysis.py",
            "experiments/spec_examples_generator.py",
            "experiments/emse_stats_report.py",
            "experiments/analyze_t1_b2_main_batch.py",
            "src/budget/pricing.py",
        ):
            text = (_ROOT / rel).read_text(encoding="utf-8")
            assert 'or "USD"' not in text and ', "USD")' not in text, rel
