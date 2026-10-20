"""AB-15 回归锁：成本拒绝的呈现与归因（2026-10-20）。

判据链：AB-9（静默缩分母才是缺陷）→ AB-10（缺席不得报成零命中）→ AB-11（键缺席 ≠ 值为
null ≠ 读不动）→ AB-12e/AB-13（`None` 哨兵三态、字段名里的单位参与判定）→ AB-14（判定只
写一遍）→ **AB-15：被拒绝的金额不得披着金额的形状出现；"为什么没有金额"必须与判定同源**。

AB-14 分册 §5 第 1 条登记了 `oracle_examples_replay.render_readme` 把 `None` 印成
`**$None**`、把 `0.0` 印成 `**$0.0**`——"无法估算"与"确实没花钱"只差一个词，却共用同一个
美元前缀，且没有一行说清是哪条机制。前置探针（`/tmp/ab15_probe*.py`，零 LLM、只读）把这
一族展开成四组站点：

a. `emse_stats_extensions._cost_per_task` 读价目却从不看币种（AB-13c/AB-14c 同型的第六处），
   且 `render_markdown` 对 `None` 直接 `:.4f` 崩、对部分和照原样印成全额；
b. `analyze_t1_b2_main_batch.add_cost` 的门在逐 seed 层写对了 `None`，聚合 `cost += … or 0.0`
   又把它折回 `$0.0`；价目数字域（`None` / `bool` / 非数值 / 负数）四件事共用一个假值；
c. `oracle_examples_replay.generation_summary` 算不出钱时只带 `None`，渲染侧连机制名都没有；
d. `spec_examples_generator.estimate_cost_usd` 的拒绝路径只有 `None`，机制名在仓内抄了三套
   （`currency_absent` / `currency_blocked` / 无名）。

处置口径：**拒绝就是没有金额**（不给 `$` 前缀、不折 `0.0`、不拿部分和冒充全额）；机制名
只在 `src.budget.pricing.currency_block_reason` 写一遍；披露键只在真拒绝时写入，故真批次
（全 USD）的载荷与受保护工件逐字节不变。

真批次不变量（复算见 `docs/reviews/COST_REJECTION_RENDERING_AB15_2026-10-20.md`）：
`analyze_t1_b2_main_batch` 的三臂池化成本 `1.447277 / 0.260967 / 0.541408`、总成本
`2.249652`；`emse_stats_extensions` 的 $/task `0.025885 / 0.003359 / 0.004543`；
P-1 归档 README 的 `$0.006195` 未被改写。
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from experiments import analyze_t1_b2_main_batch as t1
from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as rep
from experiments import oracle_examples_replay as oe
from experiments import spec_examples_generator as seg
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_OUT_DIR = _ROOT / "experiments" / "results" / "t_round_b2_main_batch_20261018"
_ORIG_DIR = _ROOT / "experiments" / "results" / "main_batch"
_REAL_PRICE: dict[str, Any] = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))["models"]["deepseek-flash"]

_USAGE = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
_MIN_REPORT = {
    "inputs": [],
    "command": [],
    "anchor_table": {},
    "ab": {},
    "regressions": [],
    "limitations": [],
}


@pytest.fixture(autouse=True)
def _isolate_pricing_cache():
    """价目表进程内缓存前后复位（AA-8 同族：模块级状态泄漏会制造跨文件顺序依赖）。"""
    pricing.reset_price_table_cache()
    yield
    pricing.reset_price_table_cache()


def _entry(currency: Any = "__omit__", **over: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"input_per_mtok": 1.0, "output_per_mtok": 2.0}
    entry.update(over)
    if currency != "__omit__":
        entry["currency"] = currency
    return entry


def _generation(model: str = "deepseek-flash", **over: Any) -> dict[str, Any]:
    gen = {
        "task_id": "t1",
        "status": "ok",
        "model": model,
        "usage": dict(_USAGE),
        "examples": [{"code": "assert x"}],
    }
    gen.update(over)
    return gen


def _report(estimated_cost_usd: Any, reason: str | None = None) -> dict[str, Any]:
    generation = {
        "n_tasks": 1,
        "status_counts": {"ok": 1},
        "n_tasks_with_examples": 1,
        "n_examples_total": 1,
        "llm_calls": 1,
        "cache_hits": 0,
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "estimated_cost_usd": estimated_cost_usd,
        "model": "deepseek-flash",
    }
    if reason is not None:
        generation["cost_unpriced_reason"] = reason
    return {**_MIN_REPORT, "generation": generation}


def _cost_line(report: dict[str, Any]) -> str:
    return next(line for line in oe.render_readme(report).splitlines() if "估算成本" in line)


def _stats() -> dict[str, Any]:
    return {
        "cost_usd": None,
        "token_metrics": {"total_input_tokens": 1_000_000, "total_output_tokens": 1_000_000},
    }


def _fake_price(monkeypatch: pytest.MonkeyPatch, models: dict[str, Any]) -> None:
    """把 `_cost_per_task` 读到的价目表换成合成表，批次文件仍走真实 `_load`。"""
    real_load = ext._load

    def fake_load(rel: str) -> Any:
        if rel == ext.PRICE_TABLE:
            return {"models": models}
        return real_load(rel)

    monkeypatch.setattr(ext, "_load", fake_load)


@pytest.fixture(scope="module")
def real_b2_report() -> dict[str, Any]:
    return t1.build_report(_OUT_DIR, _ORIG_DIR, _REAL_PRICE)


@pytest.fixture(scope="module")
def cny_b2_report() -> dict[str, Any]:
    return t1.build_report(_OUT_DIR, _ORIG_DIR, {**copy.deepcopy(_REAL_PRICE), "currency": "CNY"})


@pytest.fixture(scope="module")
def nocurrency_b2_report() -> dict[str, Any]:
    return t1.build_report(_OUT_DIR, _ORIG_DIR, {key: value for key, value in _REAL_PRICE.items() if key != "currency"})


# ─── 1. 机制名词汇表只写一遍 ────────────────────────────────────────────────


class TestCurrencyBlockReasonVocabulary:
    def test_usd_has_no_block_reason(self) -> None:
        assert pricing.currency_block_reason("usd") is None

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            ("absent", "currency_absent"),
            ("null", "currency_absent"),
            ("blank", "currency_absent"),
            ("other:CNY", "currency_not_usd:CNY"),
            ("other:cny", "currency_not_usd:cny"),
            ("not_string:int", "currency_not_usd:not_string:int"),
            ("not_string:bool", "currency_not_usd:not_string:bool"),
            ("entry_not_object:dict", "currency_unreachable:dict"),
            ("future_status", "currency_unreachable:future_status"),
        ],
    )
    def test_each_status_has_a_named_reason(self, status: str, reason: str) -> None:
        assert pricing.currency_block_reason(status) == reason

    def test_reason_is_none_exactly_for_usd(self) -> None:
        entries = [
            _entry("USD"),
            _entry(" usd "),
            _entry("CNY"),
            _entry(None),
            _entry("   "),
            _entry(123),
            _entry(["USD"]),
            _entry(),
            _entry(new_field=1),
            5,
            None,
        ]
        for entry in entries:
            status = pricing.currency_status(entry)
            assert (pricing.currency_block_reason(status) is None) is (status == "usd")

    def test_undetermined_statuses_are_exactly_the_three_written_forms(self) -> None:
        assert frozenset({"absent", "null", "blank"}) == pricing.CURRENCY_UNDETERMINED_STATUSES

    def test_status_keeps_absent_null_blank_distinct_while_reason_merges_them(self) -> None:
        """归因词表按"该不该补单位"合并，事实读数仍逐族可分（AB-11 的观测面保留在状态里）。"""
        entries = [_entry(), _entry(None), _entry("   ")]
        statuses = [pricing.currency_status(entry) for entry in entries]
        assert statuses == ["absent", "null", "blank"]
        assert {pricing.currency_block_reason(status) for status in statuses} == {"currency_absent"}

    def test_entry_not_object_is_not_merged_with_not_string(self) -> None:
        """条目不是对象（币种这一维读不到）与币种值不是字符串是两种事实（AB-11）。"""
        assert pricing.currency_block_reason(pricing.currency_status(5)) == "currency_unreachable:int"
        assert pricing.currency_block_reason(pricing.currency_status(_entry(5))) == ("currency_not_usd:not_string:int")

    def test_reason_vocabulary_is_exported(self) -> None:
        assert "currency_block_reason" in pricing.__all__
        assert "CURRENCY_UNDETERMINED_STATUSES" in pricing.__all__


# ─── 2. spec 生成器：判定与归因同源 ─────────────────────────────────────────


class TestSpecGeneratorAdmission:
    @pytest.mark.parametrize(
        ("table", "model", "reason"),
        [
            (None, "m", "price_table_null"),
            ([], "m", "price_table_not_object:list"),
            ({"models": {}}, "m", "model_unregistered"),
            # AB-16 改名：非对象条目是**形状**事实，与 report 既有读数统一为 entry_not_object。
            ({"models": {"m": 5}}, "m", "entry_not_object:int"),
            ({"models": {"m": []}}, "m", "entry_not_object:list"),
            ({"models": {"m": {}}}, "m", "entry_empty"),
            ({"models": {"m": _entry()}}, "m", "currency_absent"),
            ({"models": {"m": _entry("CNY")}}, "m", "currency_not_usd:CNY"),
            ({"models": {"m": _entry(None)}}, "m", "currency_absent"),
            ({"models": {"m": _entry(123)}}, "m", "currency_not_usd:not_string:int"),
            ({"models": {"m": _entry("USD", output_per_mtok=None)}}, "m", "price_null"),
            ({"models": {"m": _entry("USD")}}, "m", None),
        ],
    )
    def test_admission_reason(self, table: Any, model: str, reason: str | None) -> None:
        _, got = seg._price_admission(model, table)
        assert got == reason

    @pytest.mark.parametrize(
        ("table", "model"),
        [
            (None, "m"),
            ([], "m"),
            ({"models": {}}, "m"),
            ({"models": {"m": 5}}, "m"),
            ({"models": {"m": {}}}, "m"),
            ({"models": {"m": _entry()}}, "m"),
            ({"models": {"m": _entry("CNY")}}, "m"),
            ({"models": {"m": _entry(123)}}, "m"),
            ({"models": {"m": _entry("USD", input_per_mtok=None)}}, "m"),
            ({"models": {"m": _entry("USD")}}, "m"),
        ],
    )
    def test_estimate_and_reason_cannot_disagree(self, table: Any, model: str) -> None:
        """同一个 `_price_admission` 决定"算不算得出钱"与"为什么算不出钱"，不可能分叉。"""
        reason = seg.price_block_reason_for(model, table)
        cost = seg.estimate_cost_usd(model, _USAGE, table)
        assert (cost is None) is (reason is not None)

    def test_valid_usd_entry_still_prices(self) -> None:
        assert seg.price_block_reason_for("m", {"models": {"m": _entry("USD")}}) is None
        assert seg.estimate_cost_usd("m", _USAGE, {"models": {"m": _entry("USD")}}) == 3.0

    def test_explicit_none_does_not_reach_for_the_disk_table(self) -> None:
        assert seg.price_block_reason_for("deepseek-flash", None) == "price_table_null"

    def test_omitted_argument_reads_the_disk_table(self) -> None:
        assert seg.price_block_reason_for("deepseek-flash") is None
        assert seg.price_block_reason_for("no-such-model") == "model_unregistered"

    def test_falsy_non_object_models_now_named_and_empty_object_stays_silent(self) -> None:
        """AB-17：键在值非对象（真假一律）点名 `models_not_object:<T>`——`[]` / `None` 不再被
        `or {}` 折进"未登记"桶；`{}` 是"空对象没有形状可说"（已注册口径），保持静默。"""
        assert seg.price_block_reason_for("m", {"models": []}) == "models_not_object:list"
        assert seg.price_block_reason_for("m", {"models": None}) == "models_not_object:NoneType"
        assert seg.estimate_cost_usd("m", _USAGE, {"models": []}) is None
        assert seg.price_block_reason_for("m", {}) == "model_unregistered"
        assert seg.estimate_cost_usd("m", _USAGE, {}) is None

    def test_registered_boundary_truthy_non_object_models_now_named(self) -> None:
        """AB-15 登记的"真值非对象仍在 `models.get` 上崩"边界在 AB-16 收编为点名
        （`models_not_object:<类型名>`）——崩溃通道消失，形状错传有了可读归因。"""
        assert seg.price_block_reason_for("m", {"models": "abc"}) == "models_not_object:str"
        assert seg.price_block_reason_for("m", {"models": 5}) == "models_not_object:int"
        assert seg.estimate_cost_usd("m", _USAGE, {"models": "abc"}) is None


# ─── 3. oracle 渲染：`$None` 不再出现 ──────────────────────────────────────


class TestOracleCostRendering:
    def test_priced_generation_has_no_reason_key(self) -> None:
        summary = oe.generation_summary([_generation()], {"models": {"deepseek-flash": _entry("USD")}})
        assert summary["estimated_cost_usd"] == 3.0
        assert "cost_unpriced_reason" not in summary

    def test_cny_generation_carries_the_mechanism(self) -> None:
        summary = oe.generation_summary([_generation()], {"models": {"deepseek-flash": _entry("CNY")}})
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "currency_not_usd:CNY"

    def test_unregistered_model_carries_the_mechanism(self) -> None:
        summary = oe.generation_summary([_generation("unknown-model")], {"models": {}})
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "model_unregistered"

    def test_none_cost_never_renders_a_dollar_sign(self) -> None:
        line = _cost_line(_report(None, "currency_not_usd:CNY"))
        assert "无法估算（currency_not_usd:CNY）" in line
        assert "$None" not in line

    def test_missing_reason_is_named_as_unrecorded_not_guessed(self) -> None:
        line = _cost_line(_report(None))
        assert "无法估算（机制未记录）" in line

    def test_zero_is_still_a_real_amount(self) -> None:
        """`0.0` 是"确实没花钱"的真实读数，与"无法估算"必须不同形。"""
        line = _cost_line(_report(0.0))
        assert "$0.0" in line
        assert "无法估算" not in line

    def test_priced_cost_keeps_the_historical_shape(self) -> None:
        line = _cost_line(_report(0.006195))
        assert "$0.006195" in line
        assert "无法估算" not in line


# ─── 4. T1/B2 分析：拒绝不得被折成 0.0 ──────────────────────────────────────


class TestAnalyzeBatchCostGate:
    @pytest.mark.parametrize(
        ("p_in", "p_out", "reason"),
        [
            (None, 2.0, "price_null"),
            (1.0, None, "price_null"),
            (True, 2.0, "price_not_a_number:bool"),
            ("1.0", 2.0, "price_not_a_number:str"),
            (1.0, [2.0], "price_not_a_number:list"),
            (-1.0, 2.0, "price_negative"),
            (1.0, -2.0, "price_negative"),
            (0.0, 0.0, None),
            (1.0, 2.0, None),
        ],
    )
    def test_price_number_domain_is_named(self, p_in: Any, p_out: Any, reason: str | None) -> None:
        # AB-16：词汇搬进共享事实源 `src.budget.pricing.price_block_reason`（逐码不变）。
        assert pricing.price_block_reason(p_in, p_out) == reason

    def test_bool_and_str_together_name_both_types(self) -> None:
        assert pricing.price_block_reason(True, "2.0") == "price_not_a_number:bool/str"

    @pytest.mark.parametrize(
        ("price", "reason"),
        [
            (_entry(), "currency_absent"),
            (_entry(None), "currency_absent"),
            (_entry("   "), "currency_absent"),
            (_entry("CNY"), "currency_not_usd:CNY"),
            (_entry(123), "currency_not_usd:not_string:int"),
            (_entry("USD", input_per_mtok=None), "price_null"),
            (_entry("USD", input_per_mtok=True), "price_not_a_number:bool"),
            (_entry("USD", input_per_mtok=-1.0), "price_negative"),
        ],
    )
    def test_rejected_price_leaves_cost_none_with_a_reason(self, price: dict[str, Any], reason: str) -> None:
        stats = _stats()
        t1.add_cost(stats, price)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == reason

    def test_usd_price_still_prices_and_leaves_no_reason_key(self) -> None:
        stats = _stats()
        t1.add_cost(stats, _entry("USD"))
        assert stats["cost_usd"] == 3.0
        assert "cost_unpriced_reason" not in stats

    def test_zero_priced_amount_is_not_a_rejection(self) -> None:
        stats = {"cost_usd": None, "token_metrics": {"total_input_tokens": 0, "total_output_tokens": 0}}
        t1.add_cost(stats, _entry("USD"))
        assert stats["cost_usd"] == 0.0
        assert "cost_unpriced_reason" not in stats


class TestReasonCountRendering:
    def test_flat_counts_render_one_dimension(self) -> None:
        assert t1._format_reason_counts({"price_null": 2}) == "price_null×2"

    def test_counts_are_sorted_for_comparability(self) -> None:
        assert t1._format_reason_counts({"b": 1, "a": 2}) == "a×2；b×1"

    def test_nested_arm_counts_are_flattened(self) -> None:
        shown = t1._format_reason_counts({"aitester": {"currency_absent": 3}, "plain_llm": {"price_null": 1}})
        assert shown == "aitester: currency_absent×3；plain_llm: price_null×1"
        assert "{" not in shown and "'" not in shown

    def test_none_cost_without_reasons_is_named_not_guessed(self) -> None:
        assert t1._usd_text(None) == "—（无法估算：机制未记录）"

    def test_none_cost_with_flat_reasons(self) -> None:
        assert t1._usd_text(None, {"currency_absent": 3}) == "—（无法估算：currency_absent×3）"

    def test_none_cost_with_nested_reasons(self) -> None:
        shown = t1._usd_text(None, {"aitester": {"currency_not_usd:CNY": 3}})
        assert shown == "—（无法估算：aitester: currency_not_usd:CNY×3）"

    def test_zero_amount_keeps_the_dollar_shape(self) -> None:
        assert t1._usd_text(0.0) == "$0.0"

    def test_priced_amount_keeps_the_prefix_contract(self) -> None:
        assert t1._usd_text(1.5) == "$1.5"
        assert t1._usd_text(1.5, prefix="") == "1.5"


class TestAnalyzeBatchEndToEnd:
    def test_real_pooled_costs_are_bit_identical(self, real_b2_report: dict[str, Any]) -> None:
        assert {arm: blk["cost_usd"] for arm, blk in real_b2_report["pooled"].items()} == {
            "aitester": 1.447277,
            "plain_llm": 0.260967,
            "plain_llm_df": 0.541408,
        }
        assert real_b2_report["cost"]["actual_est_usd"] == 2.249652

    def test_real_per_seed_costs_are_bit_identical(self, real_b2_report: dict[str, Any]) -> None:
        got = {
            seed: {arm: st["cost_usd"] for arm, st in entry["new"].items()}
            for seed, entry in real_b2_report["per_seed"].items()
        }
        assert got == {
            "42": {"aitester": 0.484178, "plain_llm": 0.087678, "plain_llm_df": 0.186006},
            "43": {"aitester": 0.477407, "plain_llm": 0.08561, "plain_llm_df": 0.175248},
            "44": {"aitester": 0.485692, "plain_llm": 0.087679, "plain_llm_df": 0.180154},
        }

    def test_real_batch_gains_no_disclosure_keys(self, real_b2_report: dict[str, Any]) -> None:
        assert "unpriced_arms" not in real_b2_report["cost"]
        for arm, blk in real_b2_report["pooled"].items():
            assert "n_seeds_unpriced" not in blk, arm
            assert "unpriced_reasons" not in blk, arm

    def test_cny_batch_refuses_to_render_a_total(self, cny_b2_report: dict[str, Any]) -> None:
        assert cny_b2_report["cost"]["actual_est_usd"] is None
        assert cny_b2_report["cost"]["unpriced_arms"] == {
            arm: {"currency_not_usd:CNY": 3} for arm in ("aitester", "plain_llm", "plain_llm_df")
        }

    def test_cny_batch_pooled_cost_is_none_not_a_partial_sum(self, cny_b2_report: dict[str, Any]) -> None:
        for arm, blk in cny_b2_report["pooled"].items():
            assert blk["cost_usd"] is None, arm
            assert blk["n_seeds_unpriced"] == 3, arm
            assert blk["unpriced_reasons"] == {"currency_not_usd:CNY": 3}, arm

    def test_cny_batch_per_seed_cost_is_none(self, cny_b2_report: dict[str, Any]) -> None:
        for entry in cny_b2_report["per_seed"].values():
            assert {st["cost_usd"] for st in entry["new"].values()} == {None}

    def test_missing_currency_names_the_mechanism(self, nocurrency_b2_report: dict[str, Any]) -> None:
        assert nocurrency_b2_report["cost"]["actual_est_usd"] is None
        assert nocurrency_b2_report["cost"]["unpriced_arms"] == {
            arm: {"currency_absent": 3} for arm in ("aitester", "plain_llm", "plain_llm_df")
        }

    def test_cny_render_has_no_python_dict_repr(self, cny_b2_report: dict[str, Any]) -> None:
        text = t1.render_readme(cny_b2_report)
        assert "×{" not in text
        assert "aitester: currency_not_usd:CNY×3" in text

    def test_cny_render_never_prints_dollar_none(self, cny_b2_report: dict[str, Any]) -> None:
        text = t1.render_readme(cny_b2_report)
        assert "$None" not in text
        assert "实测估算成本=**—（无法估算：" in text

    def test_cny_render_per_arm_cell_names_the_mechanism(self, cny_b2_report: dict[str, Any]) -> None:
        text = t1.render_readme(cny_b2_report)
        assert "—（无法估算：currency_not_usd:CNY×3）" in text

    def test_real_render_keeps_the_dollar_total(self, real_b2_report: dict[str, Any]) -> None:
        text = t1.render_readme(real_b2_report)
        assert "实测估算成本=**$2.249652**" in text
        assert "无法估算" not in text


# ─── 5. emse_stats_extensions：第六处币种盲点与渲染 ─────────────────────────


class TestEmseExtensionsCostPerTask:
    def test_real_readings_are_bit_identical(self) -> None:
        got = {
            arm: ext._cost_per_task(ext.MAIN_BATCH_FILES, arm)[1] for arm in ("aitester", "plain_llm", "plain_llm_df")
        }
        assert got == {
            "aitester": 0.025884977011494247,
            "plain_llm": 0.003358973563218391,
            "plain_llm_df": 0.004543231034482759,
        }

    def test_cny_price_is_no_longer_summed_as_usd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": _entry("CNY", input_per_mtok=0.3, output_per_mtok=1.2)})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "currency_not_usd:CNY←deepseek-flash" in note

    def test_missing_currency_is_no_longer_summed_as_usd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": _entry(input_per_mtok=0.3, output_per_mtok=1.2)})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "currency_absent←deepseek-flash" in note

    def test_bool_price_is_rejected_not_multiplied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": _entry("USD", input_per_mtok=True, output_per_mtok=1.2)})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "price_not_a_number:bool←deepseek-flash" in note

    def test_non_object_entry_is_named_not_crashed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": 5})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        # AB-16 改名：非对象条目按形状事实点名（原 currency_unreachable:int）。
        assert "entry_not_object:int←deepseek-flash" in note

    def test_unregistered_model_remains_a_partial_sum_with_a_note(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ "价目没登记"是既有口径（只计 token、$ 少算并在 note 点名），不是本轮的"拒绝"。"""
        _fake_price(monkeypatch, {})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd == 0.0
        assert "未计价模型：['deepseek-flash']" in note

    def test_render_never_formats_none_as_a_float(self) -> None:
        report = {
            "caliber": "x",
            "bootstrap": {"n": 1, "seed": 42},
            "arms": {
                "a": {
                    "tokens_per_task": 100.0,
                    "tokens_per_task_bootstrap95": [90.0, 110.0],
                    "usd_per_task": None,
                    "usd_note": "计价被拒：currency_not_usd:CNY←m",
                }
            },
            "comparisons": {},
        }
        text = ext.render_markdown(report)
        assert "—（无金额）" in text
        assert "currency_not_usd:CNY←m" in text
        assert "$None" not in text

    def test_render_zero_is_still_a_dollar_amount(self) -> None:
        report = {
            "caliber": "x",
            "bootstrap": {"n": 1, "seed": 42},
            "arms": {
                "a": {
                    "tokens_per_task": 100.0,
                    "tokens_per_task_bootstrap95": [90.0, 110.0],
                    "usd_per_task": 0.0,
                    "usd_note": "x",
                }
            },
            "comparisons": {},
        }
        assert "$0.0000" in ext.render_markdown(report)

    def test_site_uses_the_shared_vocabulary(self) -> None:
        """AB-16：ext 的条目准入（币种+数字）整体收口到共享 `entry_block_reason`。"""
        source = inspect.getsource(ext)
        assert "entry_block_reason" in source


# ─── 6. emse_stats_report：机制名与 AB-14 判定同源 ─────────────────────────


def _row(model: str) -> dict[str, Any]:
    return {
        "detection_rate": 1.0,
        "token_usage": {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "total_tokens": 2_000_000,
            "by_model": {model: 2_000_000},
        },
    }


class TestEmseReportReasonConsolidation:
    def test_cny_reason_is_the_shared_code(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry("CNY")})
        assert out["n_unpriceable_reasons"] == {"currency_not_usd:CNY": 1}
        assert out["total_usd"] == 0.0

    @pytest.mark.parametrize("currency", [None, "   "])
    def test_undetermined_written_forms_are_currency_absent(self, currency: Any) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry(currency)})
        assert out["n_unpriceable_reasons"] == {"currency_absent": 1}

    def test_non_string_currency_keeps_its_type(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry(["USD"])})
        assert out["n_unpriceable_reasons"] == {"currency_not_usd:not_string:list": 1}

    def test_non_object_entry_is_a_shape_reason_not_a_currency_reason(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": 5})
        assert out["n_unpriceable_reasons"] == {"entry_not_object:int": 1}

    def test_valid_usd_entry_leaves_no_reason_key(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry("USD")})
        assert "n_unpriceable_reasons" not in out
        assert out["n_priced_rows"] == 1

    def test_site_imports_the_shared_vocabulary(self) -> None:
        """AB-16：report 的条目准入整体收口到共享 `entry_block_reason`。"""
        source = inspect.getsource(rep)
        assert "entry_block_reason" in source


# ─── 7. 接线与工件不变量 ────────────────────────────────────────────────────


class TestWiringAndArtifacts:
    def test_spec_generator_uses_the_shared_currency_vocabulary(self) -> None:
        source = inspect.getsource(seg)
        assert "currency_block_reason" in source
        assert "def price_block_reason_for" in source

    def test_oracle_attaches_reason_only_on_rejection(self) -> None:
        source = inspect.getsource(oe.generation_summary)
        assert "if cost is None:" in source
        assert "cost_unpriced_reason" in source

    def test_oracle_render_branches_on_none(self) -> None:
        source = inspect.getsource(oe.render_readme)
        assert "if est_cost is None:" in source
        assert "无法估算" in source

    def test_analyze_batch_uses_the_single_renderer_for_both_cost_rows_and_total(self) -> None:
        source = inspect.getsource(t1.render_readme)
        assert source.count("_usd_text(") >= 4  # 3 行成本节 + 逐臂表 1 行

    def test_p1_archived_readme_was_not_rewritten(self) -> None:
        """AB-15 只改渲染器；归档 README 是更早的富文本版本（251 行），本轮不重生成。"""
        path = _ROOT / "experiments" / "results" / "p_round_oracle_examples_20261018" / "README.md"
        text = path.read_text(encoding="utf-8")
        assert "估算成本 **$0.006195**" in text
        assert len(text.splitlines()) > 200
