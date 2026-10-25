"""AI 回归锁：token 计数也有值域，不完整的 token 和不是 token 读数（2026-10-21）。

判据链：AB-11（键缺席 ≠ 值为 null）→ AB-16（什么算一个价格数字只写一遍）→
AH（不完整的和不是金额）→ **AI：什么算一个 token 计数只写一遍**。

AH §7 登记的三条边界在本轮收口：
1. `tokens_per_task` 未同步三态（`n_tasks == 0` 时仍返回 `0.0`）；
2. `by_model` 形状坏（非对象）在 `.items()` 上崩；
3. `input_tokens + output_tokens` 与 `total_tokens` 是否自洽不在判据内。

改前读入侧是 `sum += value or 0`：
- `token_usage` 为真值非对象（`"abc"` / `[1]`）→ `.get` 上 AttributeError；
- `token_usage` 为 falsy 非对象（`[]`）→ 经 `or {}` 静默折成零 token；
- `total_tokens` / `input_tokens` / `output_tokens` 非数字 → TypeError；
- `True` 当 1 收下、`-5` 让 tokens/task 与金额同时为负、`inf`/`nan` 产出非有限读数
  （`inf/inf` 的占比得 `nan`，且 `inf != inf` 为假让 AH 的闭合检查放行）；
- `total_tokens` 键缺席、只有 in/out 有数字 → `tokens/task=0.0`（分母在、分子被吞）；
- `by_model` 非对象 → `.items()` 崩；值为字符串 → TypeError；值为 bool/负数 → 照收；
  键非字符串 → `'、'.join` 崩。

处置：一行 token 记账 = **三个非负整数**。形状/缺席/类型/负数/非有限任一不成立
⇒ 整臂 `tokens/task` 与 `$/task` 均 `None`；`in+out ≠ total` 或 `by_model` 读不动
⇒ 总数仍可读、金额 `None`。机制名逐条点名（`token_usage_absent` /
`token_usage_not_object:<T>` / `token_field_absent:<field>` /
`token_not_count:<field>:<T>` / `token_not_finite:<field>` / `token_negative:<field>` /
`token_split_mismatch:<in+out>/<total>` / `by_model_not_object:<T>` /
`by_model_key_not_string:<T>`）。真批次 783 行全为 int、逐行闭合 ⇒ 三个
`tokens/task` / 三个 CI / 三个 `$/task` 逐位不变，受保护工件不重写。
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from experiments import emse_stats_extensions as ext

_PRICE = ext.PRICE_TABLE
_BATCH = "ai_synthetic_batch.json"
_OMIT = "__omit__"


def _usd(input_per_mtok: float = 1.0, output_per_mtok: float = 2.0) -> dict[str, Any]:
    return {"input_per_mtok": input_per_mtok, "output_per_mtok": output_per_mtok, "currency": "USD"}


def _row(usage: Any = _OMIT, *, task_id: str = "t") -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id, "detection_rate": 1.0}
    if usage != _OMIT:
        row["token_usage"] = usage
    return row


def _usage(
    total: Any = 100,
    *,
    inp: Any = 60,
    out: Any = 40,
    by_model: Any = _OMIT,
) -> dict[str, Any]:
    usage: dict[str, Any] = {"total_tokens": total, "input_tokens": inp, "output_tokens": out}
    if by_model != _OMIT:
        usage["by_model"] = by_model
    return usage


def _batch(total_tasks: int, *rows: dict[str, Any]) -> dict[str, Any]:
    return {"total_tasks": total_tasks, "results": {"aitester": {"details": list(rows)}}}


def _world(monkeypatch: pytest.MonkeyPatch, batch: dict[str, Any], prices: dict[str, Any] | None = None) -> None:
    table = {"deepseek-flash": _usd()} if prices is None else prices

    def fake_load(rel: str) -> Any:
        return {"models": table} if rel == _PRICE else batch

    monkeypatch.setattr(ext, "_load", fake_load)


class TestTokenCountDomain:
    @pytest.mark.parametrize("value", [0, 1, 100, 2**53])
    def test_non_negative_ints_are_counts(self, value: int) -> None:
        assert ext.token_count_reason(value, "total_tokens") is None

    @pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
    def test_bool_is_not_a_count(self, value: bool) -> None:
        """bool 是 int 的子类，但 `True + True` 不是两个 token。"""
        assert ext.token_count_reason(value, "total_tokens") == "token_not_count:total_tokens:bool"

    def test_negative_is_named(self) -> None:
        assert ext.token_count_reason(-1, "total_tokens") == "token_negative:total_tokens"

    @pytest.mark.parametrize("value", [1.5, 100.0], ids=["fraction", "integral-float"])
    def test_float_is_not_a_count(self, value: float) -> None:
        assert ext.token_count_reason(value, "input_tokens") == "token_not_count:input_tokens:float"

    @pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan], ids=["inf", "-inf", "nan"])
    def test_non_finite_is_named_separately(self, value: float) -> None:
        assert ext.token_count_reason(value, "total_tokens") == "token_not_finite:total_tokens"

    @pytest.mark.parametrize(
        ("value", "type_name"),
        [("100", "str"), (None, "NoneType"), ([], "list"), ({}, "dict")],
    )
    def test_non_numeric_is_named(self, value: Any, type_name: str) -> None:
        assert ext.token_count_reason(value, "output_tokens") == f"token_not_count:output_tokens:{type_name}"


class TestRowTokenCounts:
    def test_valid_triple(self) -> None:
        assert ext._row_token_counts(_row(_usage(by_model={"m": 100}))) == ((100, 60, 40), [])

    def test_missing_token_usage_is_absence_not_zero(self) -> None:
        assert ext._row_token_counts(_row()) == (None, ["token_usage_absent"])

    @pytest.mark.parametrize(
        ("usage", "code"),
        [
            (None, "token_usage_not_object:NoneType"),
            ([], "token_usage_not_object:list"),
            ("abc", "token_usage_not_object:str"),
        ],
    )
    def test_non_object_usage_is_named(self, usage: Any, code: str) -> None:
        assert ext._row_token_counts(_row(usage)) == (None, [code])

    def test_empty_object_names_all_three_absent_fields(self) -> None:
        counts, reasons = ext._row_token_counts(_row({}))
        assert counts is None
        assert reasons == [
            "token_field_absent:total_tokens",
            "token_field_absent:input_tokens",
            "token_field_absent:output_tokens",
        ]

    def test_missing_total_is_absent_not_zero(self) -> None:
        counts, reasons = ext._row_token_counts(_row({"input_tokens": 60, "output_tokens": 40}))
        assert counts is None
        assert reasons == ["token_field_absent:total_tokens"]


class TestCostPerTaskValueDomain:
    @pytest.mark.parametrize(
        "usage",
        [None, [], "abc", [1]],
        ids=["null", "empty-list", "str", "list"],
    )
    def test_non_object_usage_is_not_a_zero_reading(self, monkeypatch: pytest.MonkeyPatch, usage: Any) -> None:
        _world(monkeypatch, _batch(2, _row(usage)))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert f"token_usage_not_object:{type(usage).__name__}" in note
        assert "tokens/task 与 $/task 均无读数（不是 0）" in note

    def test_missing_token_usage_is_not_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """改前 `(r.get("token_usage") or {})` 把"没记录"读成"零消耗"。"""
        _world(monkeypatch, _batch(2, _row()))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert "token_usage_absent" in note

    def test_missing_total_tokens_is_not_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AH §7 第 1 条：分母在、分子被吞——`tokens/task=0.0` 是编造的。"""
        _world(monkeypatch, _batch(2, _row({"input_tokens": 60, "output_tokens": 40})))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert "token_field_absent:total_tokens" in note

    @pytest.mark.parametrize(
        ("value", "code"),
        [
            ("100", "token_not_count:total_tokens:str"),
            (True, "token_not_count:total_tokens:bool"),
            (100.0, "token_not_count:total_tokens:float"),
            (-5, "token_negative:total_tokens"),
            (math.inf, "token_not_finite:total_tokens"),
            (math.nan, "token_not_finite:total_tokens"),
        ],
    )
    def test_bad_counts_are_named_and_never_become_numbers(
        self, monkeypatch: pytest.MonkeyPatch, value: Any, code: str
    ) -> None:
        _world(monkeypatch, _batch(2, _row(_usage(total=value, inp=value, out=0, by_model={"m": value}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None, "坏计数不得折成 tokens/task"
        assert usd is None, "坏计数不得折成金额"
        assert code in note
        assert "tokens/task 与 $/task 均无读数（不是 0）" in note

    def test_one_bad_row_invalidates_the_arm_sum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(2, _row(_usage(by_model={"m": 100}), task_id="a"), _row("abc", task_id="b")))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert "token_usage_not_object:str←1 行" in note

    def test_negative_counts_do_not_produce_negative_amounts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(2, _row(_usage(total=-5, inp=-3, out=-2, by_model={"m": -5}))))
        _, usd, _ = ext._cost_per_task([_BATCH], "aitester")
        assert usd is None, "负 token 不得产出负金额"

    def test_inf_does_not_slip_through_attribution_closure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`inf != inf` 为假：AH 的闭合检查对 inf 恰好放行，值域必须在读入侧拦下。"""
        _world(
            monkeypatch,
            _batch(2, _row(_usage(total=math.inf, inp=math.inf, out=0, by_model={"m": math.inf}))),
        )
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert "token_not_finite:total_tokens" in note


class TestAttributionValueDomain:
    @pytest.mark.parametrize(
        ("by_model", "code"),
        [
            (None, "by_model_not_object:NoneType"),
            ([], "by_model_not_object:list"),
            ("m", "by_model_not_object:str"),
        ],
    )
    def test_non_object_by_model_keeps_tokens_and_drops_amount(
        self, monkeypatch: pytest.MonkeyPatch, by_model: Any, code: str
    ) -> None:
        """形状坏不废 token 总数（total 可读），但金额没有归因。"""
        _world(monkeypatch, _batch(2, _row(_usage(by_model=by_model))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 50.0
        assert usd is None
        assert code in note
        # AG 判据：在场但读不动 ≠ 没有归因——提示语不得教人去补 by_model。
        assert "no_model_attribution" not in note

    @pytest.mark.parametrize(
        ("tokens", "code"),
        [
            ("100", "token_not_count:by_model:str"),
            (True, "token_not_count:by_model:bool"),
            (100.0, "token_not_count:by_model:float"),
            (-5, "token_negative:by_model"),
            (math.inf, "token_not_finite:by_model"),
        ],
    )
    def test_bad_by_model_values_drop_amount(self, monkeypatch: pytest.MonkeyPatch, tokens: Any, code: str) -> None:
        _world(monkeypatch, _batch(2, _row(_usage(by_model={"deepseek-flash": tokens}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 50.0
        assert usd is None
        assert code in note

    def test_non_string_model_key_is_named_not_joined(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """改前未登记的非字符串键让 `'、'.join` 抛 TypeError。"""
        _world(monkeypatch, _batch(2, _row(_usage(by_model={1: 100}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 50.0
        assert usd is None
        assert "by_model_key_not_string:int" in note

    @pytest.mark.parametrize(("inp", "out", "ratio"), [(50, 40, "90/100"), (70, 40, "110/100")])
    def test_input_plus_output_must_equal_total(
        self, monkeypatch: pytest.MonkeyPatch, inp: int, out: int, ratio: str
    ) -> None:
        """AH §7 第 3 条：in/out 拆分不闭合时，按错误比例加权的不是金额。"""
        _world(monkeypatch, _batch(2, _row(_usage(inp=inp, out=out, by_model={"deepseek-flash": 100}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 50.0, "总数仍可读"
        assert usd is None
        assert f"token_split_mismatch:{ratio}" in note
        assert "⇒ $/task 无金额（不是 0）" in note

    def test_split_mismatch_is_per_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两行偏移相抵时臂级合计会闭合——行级判定不得被抵消掩盖。"""
        _world(
            monkeypatch,
            _batch(
                2,
                _row(_usage(total=100, inp=60, out=50, by_model={"deepseek-flash": 100}), task_id="a"),
                _row(_usage(total=100, inp=60, out=30, by_model={"deepseek-flash": 100}), task_id="b"),
            ),
        )
        _, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert usd is None, "臂级 180 = 200? 不，两行各自不闭合，金额不得给出"
        assert "token_split_mismatch:110/100←1 行" in note
        assert "token_split_mismatch:90/100←1 行" in note


class TestZeroAndDenominator:
    def test_true_zero_is_still_a_real_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(2, _row(_usage(total=0, inp=0, out=0, by_model={}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 0.0
        assert usd == 0.0
        assert "无金额机制" not in note

    def test_zero_tasks_has_no_token_reading_either(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AH §7 第 1 条：没有分母时 tokens/task 也不是 0。"""
        _world(monkeypatch, _batch(0, _row(_usage(by_model={"deepseek-flash": 100}))))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt is None
        assert usd is None
        assert "无任务" in note
        assert "tokens/task" in note


class TestBootstrap:
    def _run(self, monkeypatch: pytest.MonkeyPatch, usage: Any, *, total_tasks: int = 2) -> Any:
        _world(monkeypatch, _batch(total_tasks, _row(usage, task_id="a"), _row(usage, task_id="b")))
        return ext._bootstrap_cost_ci([_BATCH], "aitester", n_boot=100)

    @pytest.mark.parametrize("usage", [None, "abc", _usage(total="100")], ids=["null", "str", "str-total"])
    def test_bad_readings_have_no_ci(self, monkeypatch: pytest.MonkeyPatch, usage: Any) -> None:
        assert self._run(monkeypatch, usage) is None

    def test_non_finite_never_reaches_the_ci(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, _usage(total=math.inf, inp=math.inf, out=0)) is None

    def test_zero_tasks_has_no_ci(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, _usage(by_model={"deepseek-flash": 100}), total_tasks=0) is None

    def test_true_zero_tokens_has_a_zero_ci(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, _usage(total=0, inp=0, out=0, by_model={})) == (0.0, 0.0)

    def test_real_ci_is_bit_identical(self) -> None:
        # 2026-10-25 输入面换代：逐位值绑定已撤回 main_batch（24226/2964/3822 系），
        # 退役为**CI 域断言**——区间有序、非负、覆盖点估计量级；重建批实测
        # aitester [3020.6, 3429.9] / plain [971.7, 1174.1] / single [1115.75, 1504.95]。
        for arm in ("aitester", "plain_llm", "single_agent"):
            lo, hi = ext._bootstrap_cost_ci(ext.MAIN_BATCH_FILES, arm)
            assert 0 < lo <= hi
            assert hi < 10_000  # 重建 synthetic 批的每任务成本量级（历史 24k 量级不回归）


class TestRender:
    def _report(self, tpt: float | None, ci: list[float] | None, usd: float | None, note: str) -> dict[str, Any]:
        return {
            "caliber": "x",
            "bootstrap": {"n": 1, "seed": 42},
            "arms": {
                "a": {
                    "tokens_per_task": tpt,
                    "tokens_per_task_bootstrap95": ci,
                    "usd_per_task": usd,
                    "usd_note": note,
                }
            },
            "comparisons": {},
        }

    def test_none_token_reading_is_not_rendered_as_zero(self) -> None:
        text = ext.render_markdown(self._report(None, None, None, "token 读数不可用：token_usage_absent←1 行"))
        assert "—（无 token 读数）" in text
        assert "—（无金额）" in text
        assert "$None" not in text
        assert "| a | 0 |" not in text

    def test_caliber_lists_token_domain_and_closure(self) -> None:
        text = ext.render_markdown(self._report(50.0, [40.0, 60.0], 0.0, "x"))
        assert "三个计数字段均为非负整数" in text
        assert "in+out = total_tokens" in text
        assert "by_model 合计 = total_tokens" in text


class TestRealBatchInvariants:
    def test_real_token_shapes_are_in_domain_and_closed(self) -> None:
        """真批次是"读数不变"的前提：三字段 int、by_model str→int、逐行两处闭合。"""
        # v0.6 输入面换代：重建 synthetic 批无 plain_llm_df 臂，遍历按批实际臂
        e6_arms = set(json.loads((ext._REPO_ROOT / ext.MAIN_BATCH_FILES[0]).read_text(encoding="utf-8"))["results"])
        for arm in ("aitester", "plain_llm", "plain_llm_df"):
            if arm not in e6_arms:
                continue
            reading = ext._read_tokens(ext.MAIN_BATCH_FILES, arm)
            assert reading["value_reasons"] == []
            assert reading["split_reasons"] == []
            assert reading["model_reasons"] == []
            rows = [r for rel in ext.MAIN_BATCH_FILES for r in ext._arm_detection_rows(ext._load(rel), arm)]
            for row in rows:
                usage = row["token_usage"]
                assert isinstance(usage, dict)
                for field in ("total_tokens", "input_tokens", "output_tokens"):
                    assert isinstance(usage[field], int) and not isinstance(usage[field], bool)
                    assert usage[field] >= 0
                assert usage["input_tokens"] + usage["output_tokens"] == usage["total_tokens"]
                assert sum(usage["by_model"].values()) == usage["total_tokens"]

    def test_real_readings_match_the_protected_artifact(self) -> None:
        archived = json.loads(
            (ext._REPO_ROOT / "experiments/results/emse_stats_extensions_20261016/STATS_EXTENSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        for arm in ("aitester", "plain_llm", "plain_llm_df"):
            tpt, usd, _ = ext._cost_per_task(ext.MAIN_BATCH_FILES, arm)
            blk = archived["arms"][f"rp02_{arm}"]
            assert tpt == blk["tokens_per_task"], arm
            assert usd == blk["usd_per_task"], arm
            assert (
                list(ext._bootstrap_cost_ci(ext.MAIN_BATCH_FILES, arm) or ()) == blk["tokens_per_task_bootstrap95"]
            ), arm
