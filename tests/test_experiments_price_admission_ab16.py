"""AB-16 回归锁：价目条目的准入域一处写一遍（2026-10-20）。

判据链：AB-9（静默缩分母才是缺陷）→ AB-10（缺席不得报成零命中）→ AB-11（缺席的三种
形状）→ AB-12（0 实例要连覆盖面一起锁）→ AB-13（字段名里的单位参与判定）→ AB-14（币种
判定只写一遍）→ AB-15（拒绝要有拒绝的形状，归因与判定同源）→ **AB-16：什么能变成金额
只写一遍**。

改前"一张价格条目能不能进美元金额"在六处消费点各写一套域（生产 `pricing._usd_prices`、
`spec_examples_generator`、`emse_stats_report`、`emse_stats_extensions`、
`analyze_t1_b2_main_batch`、`statistical_analysis`）：`bool` 被当 1 计价、`"1.0"` 被
`float()` 收下、`-1.0` 编出负数金额、`[1.0]`/`{}` 抛 TypeError、`nan`/`inf` 乘成非有限
金额、空条目 `{}` 读出四种结论、非对象条目两套词汇（`currency_unreachable:<T>` 与
`entry_not_object:<T>`）。处置口径：数字域（真数/bool/负数/nan/inf）与条目形状域
（对象/空/币种/数字）收口到 `src.budget.pricing` 的 `price_block_reason` 与
`entry_block_reason`，六处全部接过去；真批次（全 USD、有效数字）载荷与受保护工件逐字节
不变。

真批次不变量（复算见 `docs/reviews/PRICE_ADMISSION_AB16_2026-10-20.md`）：
`analyze_t1_b2_main_batch` 三臂池化成本 `1.447277 / 0.260967 / 0.541408`、总成本
`2.249652`；`emse_stats_extensions` 三臂 $/task `0.025884977011494247 /
0.003358973563218391 / 0.004543231034482759`；P-1 归档 README 的 `$0.006195` 未被改写。
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Any

import pytest

from experiments import analyze_t1_b2_main_batch as t1
from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as rep
from experiments import oracle_examples_replay as oe
from experiments import spec_examples_generator as seg
from experiments import statistical_analysis as sa
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_OUT_DIR = _ROOT / "experiments" / "results" / "t_round_b2_main_batch_20261018"
_ORIG_DIR = _ROOT / "experiments" / "results" / "main_batch"
_REAL_PRICE: dict[str, Any] = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))["models"]["deepseek-flash"]
_REAL_MODELS: dict[str, Any] = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))["models"]

_USAGE = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
_MIN_REPORT = {
    "inputs": [],
    "command": [],
    "anchor_table": {},
    "ab": {},
    "regressions": [],
    "limitations": [],
}

_NAN = float("nan")
_INF = float("inf")


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


def _arm(model: str = "m") -> dict[str, list[dict[str, Any]]]:
    return {
        "aitester": [
            {
                "token_usage": {
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "total_tokens": 2_000_000,
                    "llm_calls": 1,
                    "by_model": {model: 2_000_000},
                }
            }
        ]
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


# ─── 1. 共享词汇表的导出面 ───────────────────────────────────────────────────


class TestSharedVocabularyExports:
    def test_both_predicates_are_public(self) -> None:
        assert callable(pricing.price_block_reason)
        assert callable(pricing.entry_block_reason)
        assert "price_block_reason" in pricing.__all__
        assert "entry_block_reason" in pricing.__all__

    def test_entry_predicate_sits_on_the_currency_chain(self) -> None:
        """条目级判定复用币种链（AB-14/15 不重复也不绕过）——币种事实源仍只有一个。"""
        src = inspect.getsource(pricing.entry_block_reason)
        assert "currency_block_reason(currency_status(" in src
        assert "price_block_reason(" in src


# ─── 2. 数字域矩阵：什么算一个价格 ───────────────────────────────────────────


class TestPriceBlockReasonMatrix:
    @pytest.mark.parametrize(
        ("p_in", "p_out", "reason"),
        [
            (None, 2.0, "price_null"),
            (1.0, None, "price_null"),
            (True, 2.0, "price_not_a_number:bool"),
            (1.0, False, "price_not_a_number:bool"),
            ("1.0", 2.0, "price_not_a_number:str"),
            ("abc", 2.0, "price_not_a_number:str"),
            ([1.0], 2.0, "price_not_a_number:list"),
            ({}, 2.0, "price_not_a_number:dict"),
            (-1.0, 2.0, "price_negative"),
            (1.0, -2.0, "price_negative"),
            (-_INF, 2.0, "price_negative"),
            (_NAN, 2.0, "price_not_finite:nan"),
            (1.0, _INF, "price_not_finite:inf"),
            (0, 0, None),
            (0.0, 2.0, None),
            (3.5, 1.2, None),
        ],
    )
    def test_each_bad_number_gets_its_own_code(self, p_in: Any, p_out: Any, reason: str | None) -> None:
        assert pricing.price_block_reason(p_in, p_out) == reason

    def test_bad_types_are_aggregated_and_sorted(self) -> None:
        assert pricing.price_block_reason(True, "2.0") == "price_not_a_number:bool/str"
        assert pricing.price_block_reason("2.0", True) == "price_not_a_number:bool/str"

    def test_both_non_finite_kinds_are_named(self) -> None:
        assert pricing.price_block_reason(_NAN, _INF) == "price_not_finite:inf/nan"

    def test_zero_is_a_real_price_not_a_rejection(self) -> None:
        """`0.0` 是"确实不花钱"的真实价目，与 `None`/坏数字必须不同形。"""
        assert pricing.price_block_reason(0.0, 0.0) is None
        assert pricing.price_block_reason(0, 0) is None

    def test_truthy_int_price_passes(self) -> None:
        assert pricing.price_block_reason(1, 2) is None


class TestPriceReasonPrecedence:
    def test_null_beats_everything(self) -> None:
        assert pricing.price_block_reason(True, None) == "price_null"
        assert pricing.price_block_reason(None, _NAN) == "price_null"

    def test_type_beats_negative_and_non_finite(self) -> None:
        assert pricing.price_block_reason(-1.0, True) == "price_not_a_number:bool"
        assert pricing.price_block_reason(_NAN, "x") == "price_not_a_number:str"

    def test_negative_beats_non_finite(self) -> None:
        assert pricing.price_block_reason(-1.0, _NAN) == "price_negative"
        assert pricing.price_block_reason(_NAN, -1.0) == "price_negative"

    def test_negative_infinity_is_still_a_negative(self) -> None:
        """AB-15b 既有读数逐码保持：`-inf` 确实小于零，仍落 `price_negative`。"""
        assert pricing.price_block_reason(-_INF, -_INF) == "price_negative"


# ─── 3. 条目形状域矩阵：什么算一张合格条目 ───────────────────────────────────


class TestEntryBlockReasonMatrix:
    @pytest.mark.parametrize(
        ("entry", "reason"),
        [
            (5, "entry_not_object:int"),
            ("x", "entry_not_object:str"),
            (["USD"], "entry_not_object:list"),
            (None, "entry_not_object:NoneType"),
            ({}, "entry_empty"),
            ({"currency": "USD"}, "price_null"),
            ({"currency": "USD", "input_per_mtok": True, "output_per_mtok": 2.0}, "price_not_a_number:bool"),
            ({"currency": "USD", "input_per_mtok": _NAN, "output_per_mtok": 2.0}, "price_not_finite:nan"),
            ({"currency": "USD", "input_per_mtok": _INF, "output_per_mtok": 2.0}, "price_not_finite:inf"),
            ({"currency": "USD", "input_per_mtok": -1.0, "output_per_mtok": 2.0}, "price_negative"),
            (_entry("CNY"), "currency_not_usd:CNY"),
            (_entry(), "currency_absent"),
            (_entry(None), "currency_absent"),
            (_entry("   "), "currency_absent"),
            (_entry(["USD"]), "currency_not_usd:not_string:list"),
            (_entry("USD"), None),
            (_entry(" usd "), None),
        ],
    )
    def test_each_shape_gets_its_own_code(self, entry: Any, reason: str | None) -> None:
        assert pricing.entry_block_reason(entry) == reason

    def test_shape_is_checked_before_currency_and_price(self) -> None:
        """非对象条目根本没有币种/价格可读——不得再翻成币种码（AB-11 归因错位）。"""
        assert pricing.entry_block_reason(7) == "entry_not_object:int"

    def test_empty_beats_missing_currency(self) -> None:
        """ "什么都没有"比"没写单位"更准确——`{}` 不落 `currency_absent`。"""
        assert pricing.entry_block_reason({}) == "entry_empty"

    def test_currency_beats_price_digits(self) -> None:
        assert pricing.entry_block_reason({"currency": "CNY", "input_per_mtok": True, "output_per_mtok": 2.0}) == (
            "currency_not_usd:CNY"
        )
        assert pricing.entry_block_reason({"input_per_mtok": True, "output_per_mtok": 2.0}) == "currency_absent"

    def test_usd_and_zero_price_is_admissible(self) -> None:
        assert pricing.entry_block_reason(_entry("USD", input_per_mtok=0.0, output_per_mtok=0.0)) is None

    def test_real_usd_entry_is_admissible(self) -> None:
        assert pricing.entry_block_reason(_REAL_PRICE) is None


# ─── 4. 生产路径：记账金额不得是非有限/编造的 ────────────────────────────────


class TestProductionPricingPath:
    @pytest.mark.parametrize(
        ("p_in", "p_out", "prices"),
        [
            (None, 2.0, None),
            (True, 2.0, None),
            ("1.0", 2.0, None),
            (-1.0, 2.0, None),
            ([1.0], 2.0, None),
            ({}, 2.0, None),
            (_NAN, 2.0, None),
            (_INF, 2.0, None),
            (0.0, 2.0, (0.0, 2.0)),
            (3.5, 1.2, (3.5, 1.2)),
        ],
    )
    def test_usd_prices_reject_bad_numbers(self, p_in: Any, p_out: Any, prices: Any) -> None:
        assert pricing._usd_prices(_entry("USD", input_per_mtok=p_in, output_per_mtok=p_out)) == prices

    def test_estimate_usd_refuses_to_account_nan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """改前 `inf` 满足 `inf < 0` 为假被收下——记账会写出 `inf` 美元。"""
        monkeypatch.delenv("COST_USD_PER_1K", raising=False)
        monkeypatch.setattr(
            pricing,
            "load_price_table",
            lambda: {"m": _entry("USD", input_per_mtok=_NAN, output_per_mtok=1.2)},
        )
        assert pricing.estimate_usd("m", 1_000_000, 1_000_000) == (None, "unpriced")
        monkeypatch.setattr(
            pricing,
            "load_price_table",
            lambda: {"m": _entry("USD", input_per_mtok=_INF, output_per_mtok=1.2)},
        )
        assert pricing.estimate_usd("m", 1_000_000, 1_000_000) == (None, "unpriced")

    def test_estimate_usd_still_prices_a_valid_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pricing, "load_price_table", lambda: {"m": _entry("USD")})
        usd, source = pricing.estimate_usd("m", 1_000_000, 1_000_000)
        assert usd == 3.0 and source == "price_table:m"

    def test_real_table_readings_unchanged(self) -> None:
        """真表逐模型读数：deepseek-flash 1.5（唯一登记条目）。"""
        assert pricing._usd_prices(_REAL_MODELS["deepseek-flash"]) == (0.3, 1.2)
        assert pricing._usd_prices(None) is None

    def test_deleted_private_helper_stays_deleted(self) -> None:
        """`_as_non_negative_float` 的域被共享谓词取代（约等于但 `inf < 0` 为假 ⇒ 收下）。"""
        assert not hasattr(pricing, "_as_non_negative_float")


# ─── 5. spec_examples_generator：容器形状与数字域 ────────────────────────────


class TestSpecGeneratorAdmission:
    @pytest.mark.parametrize(
        ("p_in", "p_out", "reason"),
        [
            (None, 2.0, "price_null"),
            (True, 2.0, "price_not_a_number:bool"),
            ("1.0", 2.0, "price_not_a_number:str"),
            (-1.0, 2.0, "price_negative"),
            ([1.0], 2.0, "price_not_a_number:list"),
            ({}, 2.0, "price_not_a_number:dict"),
            (_NAN, 2.0, "price_not_finite:nan"),
            (_INF, 2.0, "price_not_finite:inf"),
            (0.0, 2.0, None),
        ],
    )
    def test_price_block_reason_for_matches_the_shared_domain(self, p_in: Any, p_out: Any, reason: str | None) -> None:
        table = {"models": {"m": _entry("USD", input_per_mtok=p_in, output_per_mtok=p_out)}}
        assert seg.price_block_reason_for("m", table) == reason

    def test_bad_numbers_never_crash_and_never_price(self) -> None:
        """改前 `[1.0]`/`{}` 在 `float()` 上抛 TypeError——坏输入不得再炸成崩溃。"""
        for bad in ([1.0], {}, "1.0", True, -1.0, _NAN, _INF):
            table = {"models": {"m": _entry("USD", input_per_mtok=bad, output_per_mtok=2.0)}}
            assert seg.estimate_cost_usd("m", _USAGE, table) is None, bad
            assert seg.price_block_reason_for("m", table) is not None, bad

    @pytest.mark.parametrize(
        ("models", "reason"),
        [
            ("abc", "models_not_object:str"),
            (5, "models_not_object:int"),
            (["x"], "models_not_object:list"),
            ([], "models_not_object:list"),
            (None, "models_not_object:NoneType"),
            ({}, "model_unregistered"),
        ],
    )
    def test_models_container_shape_is_named_except_the_empty_boundary(self, models: Any, reason: str) -> None:
        """非对象容器（真假一律）点名 `models_not_object:<T>`（AB-17 收编假值非对象）；
        `{}` 是"空对象没有形状可说"，保持静默"未登记"口径。"""
        assert seg.price_block_reason_for("m", {"models": models}) == reason

    def test_key_absent_models_reads_as_unregistered(self) -> None:
        assert seg.price_block_reason_for("m", {}) == "model_unregistered"

    def test_non_object_table_is_named_not_crashed(self) -> None:
        assert seg.price_block_reason_for("m", ["not", "a", "table"]) == "price_table_not_object:list"

    def test_non_object_entry_is_a_shape_reason(self) -> None:
        assert seg.price_block_reason_for("m", {"models": {"m": 5}}) == "entry_not_object:int"

    def test_estimate_and_reason_cannot_disagree(self) -> None:
        """同一个 `_price_admission` 决定"算不算得出钱"与"为什么算不出钱"，不可能分叉。"""
        for table in ({"models": {"m": _entry("CNY")}}, {"models": {"m": _entry("USD", input_per_mtok=_NAN)}}):
            reason = seg.price_block_reason_for("m", table)
            cost = seg.estimate_cost_usd("m", _USAGE, table)
            assert (cost is None) is (reason is not None)

    def test_real_table_readings_unchanged(self) -> None:
        assert seg.estimate_cost_usd("deepseek-flash", _USAGE) == 1.5
        assert seg.price_block_reason_for("deepseek-flash") is None
        assert seg.price_block_reason_for("unknown-model") == "model_unregistered"


# ─── 6. emse_stats_report：坏数字剔除不崩，可达码不变 ────────────────────────


class TestEmseReportAdmission:
    @pytest.mark.parametrize(
        ("p_in", "p_out", "reason"),
        [
            (None, 2.0, "price_null"),
            (True, 2.0, "price_not_a_number:bool"),
            ("1.0", 2.0, "price_not_a_number:str"),
            ([1.0], 2.0, "price_not_a_number:list"),
            ({}, 2.0, "price_not_a_number:dict"),
            (-1.0, 2.0, "price_negative"),
            (_NAN, 2.0, "price_not_finite:nan"),
            (_INF, 2.0, "price_not_finite:inf"),
        ],
    )
    def test_bad_numbers_are_excluded_with_a_reason_not_a_crash(self, p_in: Any, p_out: Any, reason: str) -> None:
        """改前这些值或抛 TypeError、或编出负数/非有限金额累进 `total_usd`。"""
        out = rep.cost_effectiveness_block(
            [_row("m")], price_table={"m": _entry("USD", input_per_mtok=p_in, output_per_mtok=p_out)}
        )
        assert out["n_unpriceable_reasons"] == {reason: 1}
        assert out["total_usd"] == 0.0

    def test_reachable_reason_codes_unchanged(self) -> None:
        assert rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry("CNY")})["n_unpriceable_reasons"] == {
            "currency_not_usd:CNY": 1
        }
        assert rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry()})["n_unpriceable_reasons"] == {
            "currency_absent": 1
        }

    def test_entry_shapes_are_named(self) -> None:
        assert rep.cost_effectiveness_block([_row("m")], price_table={"m": 5})["n_unpriceable_reasons"] == {
            "entry_not_object:int": 1
        }
        assert rep.cost_effectiveness_block([_row("m")], price_table={"m": {}})["n_unpriceable_reasons"] == {
            "entry_empty": 1
        }

    def test_unregistered_stays_its_own_reason(self) -> None:
        assert rep.cost_effectiveness_block([_row("m")], price_table={})["n_unpriceable_reasons"] == {
            "model_unregistered": 1
        }

    def test_valid_usd_entry_prices(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _entry("USD")})
        assert out["n_priced_rows"] == 1
        assert out["total_usd"] == 3.0

    def test_real_entry_reads_unchanged(self) -> None:
        out = rep.cost_effectiveness_block([_row("deepseek-flash")], price_table=_REAL_MODELS)
        assert out["n_priced_rows"] == 1
        assert out["total_usd"] == 1.5


# ─── 7. emse_stats_extensions：空条目/null 价改归拒绝，真读数逐位不变 ────────


class TestEmseExtensionsAdmission:
    def test_real_readings_are_bit_identical(self) -> None:
        got = {
            arm: ext._cost_per_task(ext.MAIN_BATCH_FILES, arm)[1]
            for arm in (
                a
                for a in ("aitester", "plain_llm", "plain_llm_df")
                if a in json.loads((Path(ext.MAIN_BATCH_FILES[0])).read_text(encoding="utf-8"))["results"]
            )
        }
        assert got == {
            "aitester": 0.00216645,
            "plain_llm": 0.0008745149999999999,
        }  # v0.6 输入面换代实测回钉（历史 0.0259/0.0034/0.0045 随撤回退役；遍历元组按原三臂、
        # 重建 synthetic 批无 plain_llm_df 故 got 两臂）

    @pytest.mark.parametrize(
        ("p_in", "reason"),
        [
            (None, "price_null"),
            (True, "price_not_a_number:bool"),
            ("1.0", "price_not_a_number:str"),
            ([1.0], "price_not_a_number:list"),
            ({}, "price_not_a_number:dict"),
            (-1.0, "price_negative"),
            (_NAN, "price_not_finite:nan"),
            (_INF, "price_not_finite:inf"),
        ],
    )
    def test_bad_numbers_are_rejected_with_a_reason(
        self, monkeypatch: pytest.MonkeyPatch, p_in: Any, reason: str
    ) -> None:
        """改前 `str`/`list`/`dict` 价在直乘上抛 TypeError，负价照乘出负数金额。"""
        _fake_price(monkeypatch, {"deepseek-flash": _entry("USD", input_per_mtok=p_in, output_per_mtok=1.2)})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert f"计价被拒：{reason}←deepseek-flash" in note

    def test_empty_entry_and_null_price_are_rejections_not_partial_sums(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """改前 `{}`/null 价从"未计价"折成 `0.0` 部分和——拒绝必须有拒绝的形状（AB-15）。"""
        _fake_price(monkeypatch, {"deepseek-flash": {}})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "计价被拒：entry_empty←deepseek-flash" in note
        _fake_price(monkeypatch, {"deepseek-flash": {"currency": "USD"}})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "计价被拒：price_null←deepseek-flash" in note

    def test_non_object_entry_is_named_not_crashed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": 5})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "计价被拒：entry_not_object:int←deepseek-flash" in note

    def test_unregistered_model_is_no_amount_not_a_partial_sum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AB-16 当时保留"未计价模型"部分和；AH（2026-10-20）起未登记 ⇒ 无金额 + 机制名。
        "没登记"与"登记了却用不了"仍是两件事：前者记 model_unregistered、后者记计价被拒。"""
        _fake_price(monkeypatch, {})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None
        assert "未计价模型：['deepseek-flash']" in note
        assert "model_unregistered←deepseek-flash" in note
        assert "计价被拒" not in note

    def test_zero_price_is_a_real_amount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_price(monkeypatch, {"deepseek-flash": _entry("USD", input_per_mtok=0.0, output_per_mtok=0.0)})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd == 0.0
        assert "计价被拒" not in note

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


# ─── 8. analyze_t1_b2_main_batch：拒绝不折 0.0，真批次逐字节不变 ─────────────


class TestAnalyzeBatchAdmission:
    pytestmark = pytest.mark.skipif(
        not (_ROOT / "experiments/results/main_batch").is_dir(),
        reason="主批次工件已清除（2026-10-24 用户指令、DeepSeek 重跑前）：历史读数锁退役，重跑落盘后重建",
    )

    @pytest.mark.parametrize(
        ("price", "reason"),
        [
            (_entry("USD", input_per_mtok=None), "price_null"),
            (_entry("USD", input_per_mtok=True), "price_not_a_number:bool"),
            (_entry("USD", input_per_mtok="1.0"), "price_not_a_number:str"),
            (_entry("USD", input_per_mtok=[1.0]), "price_not_a_number:list"),
            (_entry("USD", input_per_mtok=-1.0), "price_negative"),
            (_entry("USD", input_per_mtok=_NAN), "price_not_finite:nan"),
            (_entry("USD", input_per_mtok=_INF), "price_not_finite:inf"),
        ],
    )
    def test_bad_numbers_leave_cost_none_with_a_reason(self, price: dict[str, Any], reason: str) -> None:
        stats = _stats()
        t1.add_cost(stats, price)
        assert stats["cost_usd"] is None
        assert stats["cost_unpriced_reason"] == reason

    def test_entry_shapes_are_named(self) -> None:
        stats = _stats()
        t1.add_cost(stats, {})
        assert stats["cost_unpriced_reason"] == "entry_empty"
        stats = _stats()
        t1.add_cost(stats, 5)  # type: ignore[arg-type]
        assert stats["cost_unpriced_reason"] == "entry_not_object:int"

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

    def test_real_pooled_costs_are_bit_identical(self, real_b2_report: dict[str, Any]) -> None:
        assert {arm: blk["cost_usd"] for arm, blk in real_b2_report["pooled"].items()} == {
            "aitester": 1.447277,
            "plain_llm": 0.260967,
            "plain_llm_df": 0.541408,
        }
        assert real_b2_report["cost"]["actual_est_usd"] == 2.249652

    def test_real_batch_gains_no_disclosure_keys(self, real_b2_report: dict[str, Any]) -> None:
        assert "unpriced_arms" not in real_b2_report["cost"]
        for entry in real_b2_report["per_seed"].values():
            for st in entry["new"].values():
                assert "cost_unpriced_reason" not in st

    def test_real_render_keeps_the_dollar_total(self, real_b2_report: dict[str, Any]) -> None:
        text = t1.render_readme(real_b2_report)
        assert "实测估算成本=**$2.249652**" in text
        assert "无法估算" not in text
        assert "$nan" not in text and "$inf" not in text

    def test_cny_batch_still_refuses_a_total(self) -> None:
        cny = t1.build_report(_OUT_DIR, _ORIG_DIR, {**_REAL_PRICE, "currency": "CNY"})
        assert cny["cost"]["actual_est_usd"] is None
        text = t1.render_readme(cny)
        assert "$None" not in text and "$nan" not in text


# ─── 9. oracle：拒绝随工件带走机制名，渲染永不出现 `$nan` ───────────────────


class TestOracleAdmission:
    def test_bad_entry_carries_the_mechanism(self) -> None:
        summary = oe.generation_summary(
            [_generation()], {"models": {"deepseek-flash": _entry("USD", input_per_mtok=_NAN)}}
        )
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "price_not_finite:nan"

    def test_empty_entry_carries_the_mechanism(self) -> None:
        summary = oe.generation_summary([_generation()], {"models": {"deepseek-flash": {}}})
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "entry_empty"

    def test_non_object_entry_carries_the_mechanism(self) -> None:
        summary = oe.generation_summary([_generation()], {"models": {"deepseek-flash": 5}})
        assert summary["estimated_cost_usd"] is None
        assert summary["cost_unpriced_reason"] == "entry_not_object:int"

    def test_valid_entry_prices_without_a_reason_key(self) -> None:
        summary = oe.generation_summary([_generation()], {"models": {"deepseek-flash": _entry("USD")}})
        assert summary["estimated_cost_usd"] == 3.0
        assert "cost_unpriced_reason" not in summary

    def test_render_never_prints_nan_or_inf(self) -> None:
        line = _cost_line(_report(None, "price_not_finite:nan"))
        assert "无法估算（price_not_finite:nan）" in line
        assert "$nan" not in line and "$inf" not in line
        assert "$None" not in line


# ─── 10. statistical_analysis：数字域收口，桶级词汇不动 ──────────────────────


class TestStatisticalAnalysisAdmission:
    @pytest.mark.parametrize(
        ("entry", "priced"),
        [
            ({"input_per_mtok": 1.0, "output_per_mtok": 2.0}, True),
            ({"input_per_mtok": 0, "output_per_mtok": 0}, True),
            ({"input_per_mtok": True, "output_per_mtok": 2.0}, False),
            ({"input_per_mtok": "1.0", "output_per_mtok": 2.0}, False),
            ({"input_per_mtok": -1.0, "output_per_mtok": 2.0}, False),
            ({"input_per_mtok": _NAN, "output_per_mtok": 2.0}, False),
            ({"input_per_mtok": _INF, "output_per_mtok": 2.0}, False),
            ({"input_per_mtok": None, "output_per_mtok": 2.0}, False),
            ({}, False),
            (None, False),
        ],
    )
    def test_model_is_priced_matrix(self, entry: Any, priced: bool) -> None:
        """唯一读数变化：`inf` 改前满足 `inf >= 0` 被收下（金额变 `inf`），现不计价。"""
        assert sa._model_is_priced(entry) is priced

    def test_real_table_entry_readings_unchanged(self) -> None:
        assert sa._model_is_priced(_REAL_MODELS["deepseek-flash"]) is True
        assert sa._model_is_priced(_REAL_MODELS.get("unknown-model")) is False

    def test_cost_analysis_bad_number_goes_to_mechanism_index_not_a_price(self) -> None:
        """AG（2026-10-20）口径变更：域坏值不再与"未登记"同桶，进机制索引。

        删掉本条会让 `price_not_finite:inf` 重新冒充 `missing_models`——报告据此
        让人去登记一个**已经登记**的模型。
        """
        rows = sa.cost_analysis(_arm("m"), {"models": {"m": _entry("USD", input_per_mtok=_INF)}})
        assert rows[0]["priced"] is False
        assert rows[0]["missing_models"] == []
        assert rows[0]["unpriced_model_reasons"] == {"m": "price_not_finite:inf"}
        assert rows[0]["cost"] is None

    def test_cost_analysis_valid_entry_still_prices(self) -> None:
        rows = sa.cost_analysis(_arm("m"), {"models": {"m": _entry("USD")}})
        assert rows[0]["priced"] is True
        assert rows[0]["cost"] == 3.0
        assert rows[0]["currency"] == "USD"


# ─── 11. 一处写一遍：定义数、站点接线、死词汇清除 ────────────────────────────


class TestOneVocabularyPerRepo:
    def _sources(self) -> dict[str, str]:
        files = {
            "pricing": _ROOT / "src" / "budget" / "pricing.py",
            "spec": _ROOT / "experiments" / "spec_examples_generator.py",
            "report": _ROOT / "experiments" / "emse_stats_report.py",
            "ext": _ROOT / "experiments" / "emse_stats_extensions.py",
            "analyze": _ROOT / "experiments" / "analyze_t1_b2_main_batch.py",
            "statistical": _ROOT / "experiments" / "statistical_analysis.py",
            "oracle": _ROOT / "experiments" / "oracle_examples_replay.py",
        }
        return {name: path.read_text(encoding="utf-8") for name, path in files.items()}

    def test_predicates_are_defined_exactly_once(self) -> None:
        """`def entry_block_reason(` 与 `def price_block_reason(` 全仓各出现一次（pricing）。"""
        src = self._sources()
        assert sum(s.count("def entry_block_reason(") for s in src.values()) == 1
        assert sum(s.count("def price_block_reason(") for s in src.values()) == 1
        assert "def entry_block_reason(" in src["pricing"]
        assert "def price_block_reason(" in src["pricing"]

    def test_sites_import_the_shared_predicate(self) -> None:
        src = self._sources()
        for name in ("spec", "report", "ext", "analyze"):
            assert "from src.budget.pricing import entry_block_reason" in src[name], name
        assert "pricing.price_block_reason" in src["statistical"]

    def test_sites_call_the_shared_predicate(self) -> None:
        src = self._sources()
        for name in ("report", "ext", "analyze"):
            assert "entry_block_reason(" in src[name].replace(
                "from src.budget.pricing import entry_block_reason", ""
            ), name

    def test_dead_local_vocabulary_is_gone(self) -> None:
        """死词汇只剩注释里的历史说明；定义与调用一律不得复活。"""
        src = self._sources()
        assert "def _price_reject_reason" not in src["analyze"]
        assert "_price_reject_reason(" not in src["analyze"]
        assert "def _as_non_negative_float" not in src["pricing"]
        assert "_as_non_negative_float(" not in src["pricing"]
        for name in ("report", "ext"):
            assert "currency_block_reason" not in src[name], name


# ─── 12. 受保护工件与归档不动 ────────────────────────────────────────────────


class TestProtectedArtifactsUnchanged:
    def test_p1_archived_readme_was_not_rewritten(self) -> None:
        path = _ROOT / "experiments" / "results" / "p_round_oracle_examples_20261018" / "README.md"
        text = path.read_text(encoding="utf-8")
        assert "估算成本 **$0.006195**" in text
        assert len(text.splitlines()) > 200

    def test_repo_price_table_is_numerically_pristine(self) -> None:
        """真表不得被本轮"修表"——仅登记 DeepSeek 官方 USD 价目，数值不变。"""
        assert _REAL_MODELS["deepseek-flash"]["currency"].upper() == "USD"
        assert math.isfinite(float(_REAL_MODELS["deepseek-flash"]["input_per_mtok"]))
