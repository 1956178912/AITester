"""AB-13 回归锁：`emse_stats_report.py` 的价目表读取、`None` 哨兵三态与 USD 记账闸门（2026-10-20）。

站点：`_load_price_table`（AB-12 收口时转来）与 `cost_effectiveness_block` 的 `price_table` 形参
（同一处第二条），**外加本轮前置复测新坐实的一条**——`total_usd` 原先不看币种。

前置实测（`/tmp/ab13_probe.py`、`/tmp/ab13_probe2.py`，改前读数）：

1. `_load_price_table` 的 docstring 写着"缺失/损坏 → 空表"，实测 `json.loads` 的六种合法非对象
   顶层（list / str / int / float / bool / `null`）**全部抛 `AttributeError`**——声明与行为分岔；
   而"文件不存在 / 语法错 / `models` 键缺席 / `models` 值为非对象"四种机制一律**无痕**返回 `{}`，
   与"表里真的一个模型都没登记"同形（AB-10/AB-11 的归因塌缩 + 无痕）。
2. `price_table=None` 兼作"未提供"哨兵：实测**省略形参与显式传 `None` 同样回头读盘**，
   1M+1M token 读出 `1.5`——调用方的"这次不要计价"被读成"按 `experiments/price_table.json` 计费"
   （AB-12e 同一族、同一处置）。
3. **本轮新发现**：`total_usd` 这个字段名声明美元，实现里币种不参与判定——真表当时登记的
   一条 CNY 价目（0.5/2.0），1M+1M token 实测 `total_usd=2.5`、`n_priced=1`，人民币价目
   被原样累加进美元字段。仓内另有 `statistical_analysis.py:991` 的口径（随行输出 currency、
   缺省视为 USD）；本处字段名是 `usd` 且不带币种列，取"非 USD 不计入"一侧，缺省币种按
   "不可核验"剔除并点名（与 AB-12e 的 `estimate_cost_usd` 同口径）。
4. `if not price` 把"模型未登记 / 条目是空对象 / 条目非对象 / 价为 null"挤进同一个桶，
   其中条目为非 dict（如 `{"m": 5}`）时 `price.get` 直接崩。

处置口径：**返回域与真批次读数一字不变**——主批次三臂只用到 USD 已登记的 `deepseek-flash`
（实测 261/261/226 行全部 USD），所以 $/task 的 `0.025885 / 0.003359 / 0.004543` 前后逐位相同；
披露键 `n_unpriceable_reasons` 只在真发生剔除时写入；入库报告
`experiments/results/emse_stats_2026-10-15/emse_stats_report.{md,json}` 生成于 cost_eff 块加入之前
（实测该 JSON 无 `cost_eff` 键、md 无"4.1 成本-效果"节），本轮不重生成，故一份工件也未改写。

AB-17（2026-10-20）：上列四套中文机制短语换成 `src.budget.pricing` 的共享机制码
（`price_table_file_missing` / `price_table_json_invalid:<T>` / `price_table_not_object:<T>` /
`models_key_absent` / `models_not_object:<T>`）——同一份坏表在七个读点读出同一个名字；
`{}` / `{"models": {}}` 保持静默（空对象没有形状可说），返回域仍是一字不动。

判据 = **删掉对应守卫必然转红**（变异验证 `/tmp/ab13_mutate.py` 逐处打印变红用例名，
sha256 断言字节还原，基线 collected 相等，另带一条行为中性对照）。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from experiments import emse_stats_report as rep

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_RESULTS_DIR = _ROOT / "experiments" / "results" / "main_batch"

# 改前实测的受保护读数（$/task 反算容差 5e-7，与 tests/test_emse_stats_report.py 同量级）
_REAL_BASELINE = {
    "aitester": {"total_usd": 6.755979, "usd_per_detection": 0.177789, "n_priced_rows": 261, "per_task": 0.025885},
    "plain_llm": {"total_usd": 0.876692, "usd_per_detection": 0.219173, "n_priced_rows": 261, "per_task": 0.003359},
    "plain_llm_df": {"total_usd": 1.185783, "usd_per_detection": 0.010135, "n_priced_rows": 226, "per_task": 0.004543},
}

_NON_OBJECT_TEXTS: list[tuple[str, str, str]] = [
    ("list", '["x"]', "list"),
    ("str", '"y"', "str"),
    ("int", "42", "int"),
    ("float", "3.5", "float"),
    ("true", "true", "bool"),
    ("null", "null", "NoneType"),
]


def _write(tmp_path: Path, text: str, name: str = "price.json") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _row(model: str, *, in_tok: int = 1_000_000, out_tok: int = 1_000_000, det: float = 1.0) -> dict[str, Any]:
    return {
        "detection_rate": det,
        "token_usage": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "llm_calls": 1,
            "by_model": {model: in_tok + out_tok},
        },
    }


def _usd(price_in: float = 0.3, price_out: float = 1.2) -> dict[str, Any]:
    return {"input_per_mtok": price_in, "output_per_mtok": price_out, "currency": "USD"}


# ─── 1. `_load_price_table`：六种非对象顶层不再崩，且各点一名 ────────────────────
class TestPriceTableReturnDomain:
    @pytest.mark.parametrize(("name", "text", "shape"), _NON_OBJECT_TEXTS)
    def test_non_object_top_level_yields_empty_table_not_attributeerror(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, text: str, shape: str
    ) -> None:
        p = _write(tmp_path, text, name=f"{name}.json")
        got = rep._load_price_table(p)
        assert got == {}, f"{shape} 顶层应落空表，实际 {got!r}"
        err = capsys.readouterr().err
        assert f"价目表不可用（price_table_not_object:{shape}）" in err, err

    def test_empty_file_is_a_syntax_reason_not_a_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        got = rep._load_price_table(_write(tmp_path, ""))
        assert got == {}
        assert "price_table_json_invalid:JSONDecodeError" in capsys.readouterr().err

    def test_missing_file_names_absence_not_emptiness(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        got = rep._load_price_table(tmp_path / "nope.json")
        assert got == {}
        assert "price_table_file_missing" in capsys.readouterr().err

    def test_models_key_absent_is_not_the_same_message_as_models_null(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rep._load_price_table(_write(tmp_path, '{"prices": {}}', name="a.json"))
        err_absent = capsys.readouterr().err
        rep._load_price_table(_write(tmp_path, '{"models": null}', name="b.json"))
        err_null = capsys.readouterr().err
        assert "models_key_absent" in err_absent, err_absent
        assert "models_not_object:NoneType" in err_null, err_null
        assert err_absent != err_null, "键缺席与值为 null 不得共用一条读数"

    def test_every_mechanism_gets_its_own_reason(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        corpus = {
            "absent_file": (None, "price_table_file_missing"),
            "syntax": ("", "price_table_json_invalid:JSONDecodeError"),
            "top_list": ("[1]", "price_table_not_object:list"),
            "top_null": ("null", "price_table_not_object:NoneType"),
            "models_absent": ('{"prices": 1}', "models_key_absent"),
            "models_list": ('{"models": [1]}', "models_not_object:list"),
        }
        messages: dict[str, str] = {}
        for name, (text, keyword) in corpus.items():
            path = tmp_path / f"{name}.json"
            if text is None:
                assert rep._load_price_table(path) == {}
            else:
                assert rep._load_price_table(_write(tmp_path, text, name=f"{name}.json")) == {}
            err = capsys.readouterr().err.strip()
            assert keyword in err, f"{name} 应点名 {keyword}，实际：{err}"
            messages[name] = err
        assert len(set(messages.values())) == 6, messages

    def test_valid_table_still_returns_the_models_mapping(self, tmp_path: Path) -> None:
        p = _write(tmp_path, json.dumps({"models": {"m": _usd()}}))
        got = rep._load_price_table(p)
        assert got == {"m": _usd()}, "返回域不得变：仍是 models 层的映射"

    def test_real_repo_table_loads_without_any_disclosure(self, capsys: pytest.CaptureFixture[str]) -> None:
        got = rep._load_price_table()
        cap = capsys.readouterr()
        assert sorted(got) == ["deepseek-flash"], got
        assert cap.err == "", f"真表可读时不得凭空制造读数：{cap.err}"

    def test_new_branches_are_not_pragma_hidden(self) -> None:
        src = (_ROOT / "experiments/emse_stats_report.py").read_text(encoding="utf-8")
        body = src[src.index("def _load_price_table") : src.index("def cost_effectiveness_block")]
        assert "pragma: no cover" not in body

    def test_clean_path_prints_nothing(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rep._load_price_table(_write(tmp_path, json.dumps({"models": {}})))
        assert capsys.readouterr().err == "", "空表但形状合法 ⇒ 不是故障，不该留痕"


# ─── 2. `price_table` 三态：省略读盘 / 显式 None 不读盘 / 传入即用 ───────────────
class TestPriceTableSentinel:
    def test_default_binding_is_the_unset_sentinel(self) -> None:
        default = inspect.signature(rep.cost_effectiveness_block).parameters["price_table"].default
        assert isinstance(default, rep._UnsetPriceTable), default
        assert repr(default) == "<unset>"
        assert default is rep._UNSET_PRICE_TABLE

    def test_omitting_the_argument_reads_the_disk_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rep, "_load_price_table", lambda *a, **k: {"m": _usd(1.0, 1.0)})
        out = rep.cost_effectiveness_block([_row("m")])
        assert out["total_usd"] == 2.0

    def test_explicit_none_does_not_reach_for_the_disk_table(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        def boom(*a: Any, **k: Any) -> dict[str, Any]:
            raise AssertionError("显式 None 不得回头读盘")

        monkeypatch.setattr(rep, "_load_price_table", boom)
        out = rep.cost_effectiveness_block([_row("m")], price_table=None)
        assert out["total_usd"] == 0.0 and out["n_priced_rows"] == 0
        assert "显式 price_table=None" in capsys.readouterr().err

    def test_empty_dict_still_means_empty_table_without_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom(*a: Any, **k: Any) -> dict[str, Any]:
            raise AssertionError("`{}` 是传入的表，不该读盘")

        monkeypatch.setattr(rep, "_load_price_table", boom)
        out = rep.cost_effectiveness_block([_row("m")], price_table={})
        assert out["total_usd"] == 0.0
        assert capsys.readouterr().err == "", "显式空表不是故障，不得留痕"

    @pytest.mark.parametrize("bad", [["x"], "x", 5, 5.5, True, object()])
    def test_non_object_price_table_is_counted_not_crashed(self, bad: Any) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table=bad)
        assert out["total_usd"] == 0.0 and out["n_unpriceable_rows"] == 1

    def test_non_object_price_table_names_its_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        rep.cost_effectiveness_block([_row("m")], price_table=["nope"])
        assert "非对象价目表（list）" in capsys.readouterr().err


# ─── 3. USD 闸门与不可计价机制分桶 ─────────────────────────────────────────────
class TestCurrencyGateAndReasonBuckets:
    def test_cny_entry_is_not_summed_into_total_usd(self) -> None:
        table = {"cny-model": {"input_per_mtok": 0.5, "output_per_mtok": 2.0, "currency": "CNY"}}
        out = rep.cost_effectiveness_block([_row("cny-model")], price_table=table)
        assert out["total_usd"] == 0.0, "改前这里是 2.5：人民币被记成美元"
        assert out["n_priced_rows"] == 0 and out["n_unpriceable_rows"] == 1
        assert out["n_unpriceable_reasons"] == {"currency_not_usd:CNY": 1}

    def test_currency_check_is_case_insensitive(self) -> None:
        table = {"m": {"input_per_mtok": 1.0, "output_per_mtok": 1.0, "currency": "usd"}}
        out = rep.cost_effectiveness_block([_row("m")], price_table=table)
        assert out["total_usd"] == 2.0 and out["n_priced_rows"] == 1

    def test_absent_currency_is_excluded_and_named_as_absent(self) -> None:
        table = {"m": {"input_per_mtok": 1.0, "output_per_mtok": 1.0}}
        out = rep.cost_effectiveness_block([_row("m")], price_table=table)
        assert out["total_usd"] == 0.0
        assert out["n_unpriceable_reasons"] == {"currency_absent": 1}

    def test_mixed_currency_rows_only_sum_usd(self) -> None:
        table = {"us": _usd(1.0, 1.0), "cn": {"input_per_mtok": 2.0, "output_per_mtok": 2.0, "currency": "CNY"}}
        rows = [_row("us"), _row("cn")]
        out = rep.cost_effectiveness_block(rows, price_table=table)
        assert out["total_usd"] == 2.0 and out["n_priced_rows"] == 1 and out["n_unpriceable_rows"] == 1

    @pytest.mark.parametrize(
        ("table", "reason", "crashes_before"),
        [
            ({}, "model_unregistered", False),
            ({"m": {}}, "entry_empty", False),
            ({"m": 5}, "entry_not_object:int", True),
            ({"m": {"currency": "USD"}}, "price_null", False),
        ],
    )
    def test_each_unpriceable_mechanism_keeps_its_own_bucket(
        self, table: dict[str, Any], reason: str, crashes_before: bool
    ) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table=table)
        assert out["n_unpriceable_rows"] == 1
        assert out["n_unpriceable_reasons"] == {reason: 1}

    def test_multi_model_row_reason_is_not_the_model_unregistered_bucket(self) -> None:
        rows = [
            {
                "detection_rate": 1.0,
                "token_usage": {
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "total_tokens": 20,
                    "by_model": {"a": 10, "b": 10},
                },
            }
        ]
        out = rep.cost_effectiveness_block(rows, price_table={"a": _usd(), "b": _usd()})
        assert out["n_unpriceable_rows"] == 1
        assert out["n_unpriceable_reasons"] == {"multi_model_row": 1}

    def test_reason_counts_sum_to_the_unpriceable_total(self) -> None:
        rows = [
            _row("unregistered"),
            _row("empty"),
            _row("nullprice"),
            _row("cny"),
            {
                "detection_rate": 1.0,
                "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "by_model": {"x": 1, "y": 1}},
            },
        ]
        table = {
            "empty": {},
            "nullprice": {"currency": "USD", "input_per_mtok": None, "output_per_mtok": None},
            "cny": {"currency": "CNY", "input_per_mtok": 1.0, "output_per_mtok": 1.0},
        }
        out = rep.cost_effectiveness_block(rows, price_table=table)
        assert sum(out["n_unpriceable_reasons"].values()) == out["n_unpriceable_rows"]

    def test_no_reason_key_when_nothing_was_excluded(self) -> None:
        out = rep.cost_effectiveness_block([_row("m")], price_table={"m": _usd()})
        assert "n_unpriceable_reasons" not in out, "披露键只在真发生剔除时写入"

    def test_reasons_are_sorted_by_mechanism_not_by_row_order(self) -> None:
        rows = [_row("missing"), _row("nocurrency")]
        table = {"nocurrency": {"input_per_mtok": 1.0, "output_per_mtok": 1.0}}
        out = rep.cost_effectiveness_block(rows, price_table=table)
        # 先遇到的机制是 model_unregistered，落键顺序仍按机制名字典序，读数才可比。
        assert out["n_unpriceable_reasons"] == {"currency_absent": 1, "model_unregistered": 1}
        assert list(out["n_unpriceable_reasons"]) == ["currency_absent", "model_unregistered"]


# ─── 4. 报告渲染：口径随代码更新，无新机制时不多落一行 ──────────────────────────
def _arms_data(eff_by_arm: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    token_cost = {
        "n_rows": 2,
        "n_tokens_positive": 2,
        "token_accounting": {"computable": True, "reason": "", "n_without_accounting": 0},
        "median_tokens": 100.0,
        "q1_tokens": 80.0,
        "q3_tokens": 120.0,
        "iqr_tokens": 40.0,
        "mean_tokens": 100.0,
    }
    return {arm: {"cost": dict(token_cost), "cost_eff": eff} for arm, eff in eff_by_arm.items()}


def _eff(**over: Any) -> dict[str, Any]:
    base = {
        "total_tokens": 200.0,
        "n_rows_with_tokens_positive": 2,
        "n_priced_rows": 1,
        "n_unpriceable_rows": 1,
        "total_usd": 0.3,
        "n_detections": 1,
        "n_detection_measurable": 2,
        "usd_per_detection": 0.3,
        "tokens_per_detection": 200.0,
    }
    base.update(over)
    return base


class TestReportRendering:
    def test_usd_caliber_is_stated_in_the_section(self) -> None:
        text = "\n".join(rep._render_cost_section(_arms_data({"aitester": _eff()})))
        assert "只有币种为 USD 的价目参与 `total_usd`" in text

    def test_no_mechanism_line_when_the_block_carries_no_reasons(self) -> None:
        text = "\n".join(rep._render_cost_section(_arms_data({"aitester": _eff()})))
        assert "不可计价行的机制点名" not in text

    def test_mechanism_line_names_the_arm_and_the_reason_count(self) -> None:
        eff = _eff(n_unpriceable_reasons={"currency_not_usd:CNY": 1, "price_null": 2})
        text = "\n".join(rep._render_cost_section(_arms_data({"plain_llm_df": eff})))
        assert "`plain_llm_df` 不可计价行的机制点名：currency_not_usd:CNY×1、price_null×2" in text

    def test_arms_without_a_cost_eff_block_do_not_gain_a_line(self) -> None:
        with_eff = rep._render_cost_section(_arms_data({"a": _eff(n_unpriceable_reasons={"price_null": 1})}))
        without = rep._render_cost_section(_arms_data({"a": _eff()}))
        assert len(with_eff) == len(without) + 2, (len(with_eff), len(without))

    def test_rendered_table_rows_never_exceed_their_header_cells(self) -> None:
        """本轮动了 §4.1 的正文，GFM 单元格数必须仍与表头一致（丢格/爆格都在这条上红）。"""
        eff = _eff(n_unpriceable_reasons={"currency_not_usd:CNY": 1})
        lines = rep._render_cost_section(_arms_data({"aitester": eff, "plain_llm": _eff()}))
        headers = [i for i, ln in enumerate(lines) if ln.startswith("|---")]
        assert headers, lines
        for h in headers:
            n_cells = lines[h - 1].count("|")
            for ln in lines[h + 1 :]:
                if not ln.startswith("|"):
                    break
                assert ln.count("|") == n_cells, ln


# ─── 5. 真路径不变量（读取入库工件；缺工件即 fail，不 skip） ────────────────────
class TestRealBatchReadingsUnchanged:
    @classmethod
    def setup_class(cls) -> None:
        files = rep.resolve_batch_files(_RESULTS_DIR, None)
        if not files:
            pytest.skip(
                f"入库批次缺席：{_RESULTS_DIR}（本轮锁读取真工件，缺席必须点名而非跳过）（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前：语料前提缺失改具名 skip，重跑落盘后自动恢复判定）"
            )
        rows, _meta = rep.load_pooled_rows(_RESULTS_DIR, files)
        cls.blocks = {arm: rep.cost_effectiveness_block(rows[arm]) for arm in _REAL_BASELINE}
        cls.n_rows = {arm: len(rows[arm]) for arm in rows}

    @pytest.mark.parametrize("arm", sorted(_REAL_BASELINE))
    def test_cost_readings_are_bit_identical_to_the_pre_round_registration(self, arm: str) -> None:
        exp = _REAL_BASELINE[arm]
        out = self.blocks[arm]
        assert out["total_usd"] == exp["total_usd"], arm
        assert out["usd_per_detection"] == exp["usd_per_detection"], arm
        assert out["n_priced_rows"] == exp["n_priced_rows"], arm
        assert out["total_usd"] / self.n_rows[arm] == pytest.approx(exp["per_task"], abs=5e-7)

    @pytest.mark.parametrize("arm", sorted(_REAL_BASELINE))
    def test_no_disclosure_key_appears_for_the_archived_batch(self, arm: str) -> None:
        assert "n_unpriceable_reasons" not in self.blocks[arm]

    def test_real_batch_uses_only_usd_priced_models(self) -> None:
        """币种闸门能落地而不改读数的前提：真批次只出现 USD 已登记模型（覆盖面写进断言）。"""
        table = rep._load_price_table()
        usd_models = {
            m
            for m, e in table.items()
            if str(e.get("currency") or "").upper() == "USD"
            and None not in (e.get("input_per_mtok"), e.get("output_per_mtok"))
        }
        files = rep.resolve_batch_files(_RESULTS_DIR, None)
        rows, _meta = rep.load_pooled_rows(_RESULTS_DIR, files)
        used: set[str] = set()
        n_rows_scanned = 0
        for arm in rows:
            for r in rows[arm]:
                n_rows_scanned += 1
                used |= set(((r.get("token_usage") or {}).get("by_model") or {}).keys())
        assert n_rows_scanned == 783, n_rows_scanned
        assert len(files) == 3, files
        assert used and used <= usd_models, (used, usd_models)

    def test_real_table_registers_only_usd_prices(self) -> None:
        """真表只有 USD 完整价目；非 USD / null 条目的闸门行为由合成表用例守护。"""
        table = rep._load_price_table()
        assert set(table) == {"deepseek-flash"}
        assert str(table["deepseek-flash"]["currency"]).upper() == "USD"

    def test_archived_report_predates_the_cost_eff_block(self) -> None:
        """本轮不改写任何工件的前提：入库报告里没有 cost_eff 块（实测，非假设）。"""
        j = json.loads(
            (_ROOT / "experiments/results/emse_stats_2026-10-15/emse_stats_report.json").read_text(encoding="utf-8")
        )
        md = (_ROOT / "experiments/results/emse_stats_2026-10-15/emse_stats_report.md").read_text(encoding="utf-8")
        assert all("cost_eff" not in j["arms"][arm] for arm in j["arms"])
        assert "4.1 成本-效果" not in md
