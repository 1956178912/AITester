"""AB-12e 回归锁：价目表读取点的返回域与 `None` 哨兵三态（2026-10-20）。

站点是 `experiments/spec_examples_generator.py` 的 `load_price_table` 与 `estimate_cost_usd`
（AB-9 登记：`docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md` §4 行 97 / 104）。
本轮前置实测（`/tmp/ab12e_price_probe.py`）坐实两件事：

1. `load_price_table` 只拦 `OSError` / `JSONDecodeError`，六种合法非对象顶层
   （list / str / int / float / bool / `null`）**原样返回**，崩溃落在调用方
   `estimate_cost_usd` 的 `table.get("models")`（`AttributeError`）；而
   `oracle_examples_replay.py:1030` 把这条读取放在**整轮付费 LLM 重放之后**——钱花完才炸。
   文档串却写着"缺失/非法 → 空 dict"：**声明与返回域不一致**。
2. `price_table=None` 兼作"未提供"哨兵，而 `None` 恰是 `json.loads` 的合法返回：
   实测显式传 `None` 时函数**回头重读盘上的真表**给出 `0.0027`——"这里没有价目表"
   被读成"按另一份文件的价目计费"（AB-11 的键缺失≠值为 null 同一族，方向相反）。

处置口径：**盘上真表读数一字不变**（顶层是 dict、3 个模型 ⇒ 0.0027 前后同值），只把
"原样返回 + 下游崩"改成"空表 + `logger.warning` 点名"，把 `None` 从双重身份里拆出来
（省略＝去读盘，显式 `None`＝声明无表 ⇒ 成本 `None`，且不读盘）。成本一律是 `None`
（"无法估算"），不是 `0`（"没有花钱"）——这两件事在报告里长得一样，含义相反。

判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名，sha256 断言字节还原）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from experiments import spec_examples_generator as gen

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_USAGE = {"input_tokens": 5_000, "output_tokens": 1_000}
_MODEL = "deepseek-flash"

# 六种"合法但非对象"的顶层（AB-9 的返回域口径：json.loads 能给出的全部六种里去掉 dict）
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


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return " | ".join(r.getMessage() for r in caplog.records)


# ─── 1. 非对象顶层：空表 + 留痕，下游不得崩 ─────────────────────────────────────
class TestNonObjectTopLevel:
    @pytest.mark.parametrize(("name", "text", "shape"), _NON_OBJECT_TEXTS)
    def test_returns_empty_dict_and_names_the_shape(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str, text: str, shape: str
    ) -> None:
        p = _write(tmp_path, text, name=f"{name}.json")
        with caplog.at_level(logging.WARNING):
            got = gen.load_price_table(p)
        assert got == {}, f"{shape} 顶层必须落空表，实际返回 {got!r}"
        assert f"price_table_not_object:{shape}" in _messages(caplog), _messages(caplog)

    @pytest.mark.parametrize(("name", "text", "shape"), _NON_OBJECT_TEXTS)
    def test_downstream_does_not_crash_after_a_paid_replay(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str, text: str, shape: str
    ) -> None:
        """改造前这条是 `AttributeError: 'list' object has no attribute 'get'`，且发生在付费重放之后。"""
        p = _write(tmp_path, text, name=f"{name}.json")
        with caplog.at_level(logging.WARNING):
            cost = gen.estimate_cost_usd(_MODEL, _USAGE, gen.load_price_table(p))
        assert cost is None, f"{shape} 顶层不得给出任何金额，实际 {cost!r}"

    def test_none_cost_is_worded_as_not_zero(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """ "无法估算"与"没有花钱"在报告里都写作一个数，留痕必须把两者分开。"""
        p = _write(tmp_path, "42")
        with caplog.at_level(logging.WARNING):
            gen.load_price_table(p)
        assert "成本估算为 None（不是 0）" in _messages(caplog), _messages(caplog)

    def test_a_dict_table_is_returned_untouched_and_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        payload = {"models": {"m": {"currency": "USD", "input_per_mtok": 0.3, "output_per_mtok": 1.2}}}
        p = _write(tmp_path, json.dumps(payload))
        with caplog.at_level(logging.WARNING):
            got = gen.load_price_table(p)
        assert got == payload, "合法对象表必须原样交出去，本轮只改非对象那一侧"
        assert caplog.records == [], f"合法输入不得留下任何痕迹：{_messages(caplog)}"

    def test_missing_file_is_disclosed_as_absent_not_as_shape(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """两条降级机制不得并写：文件缺席 ≠ 顶层非对象（AB-10 同一判据；AB-17 换成共享机制码）。"""
        with caplog.at_level(logging.WARNING):
            got = gen.load_price_table(tmp_path / "nope.json")
        assert got == {}
        msg = _messages(caplog)
        assert "price_table_file_missing" in msg, msg
        assert "price_table_not_object" not in msg, msg

    def test_broken_syntax_is_disclosed_as_invalid_json(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        p = _write(tmp_path, "{truncated")
        with caplog.at_level(logging.WARNING):
            got = gen.load_price_table(p)
        assert got == {}
        msg = _messages(caplog)
        assert "price_table_json_invalid:JSONDecodeError" in msg, msg


# ─── 2. 哨兵三态：省略 / 显式 None / 非对象 ─────────────────────────────────────
class TestSentinelSeparation:
    def test_omitted_still_reads_the_disk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def spy() -> dict[str, Any]:
            calls.append(1)
            return {"models": {_MODEL: {"currency": "USD", "input_per_mtok": 0.3, "output_per_mtok": 1.2}}}

        monkeypatch.setattr(gen, "load_price_table", spy)
        assert gen.estimate_cost_usd(_MODEL, _USAGE) is not None
        assert calls == [1], "省略形参仍须走「读盘」这条既有通道"

    def test_explicit_none_declares_no_table_and_never_touches_disk(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """改造前：显式 `None` 回头读盘并给出金额 ⇒ 坏输入被哨兵吞掉。"""
        calls: list[int] = []

        def spy() -> dict[str, Any]:
            calls.append(1)
            return {"models": {_MODEL: {"currency": "USD", "input_per_mtok": 0.3, "output_per_mtok": 1.2}}}

        monkeypatch.setattr(gen, "load_price_table", spy)
        with caplog.at_level(logging.WARNING):
            cost = gen.estimate_cost_usd(_MODEL, _USAGE, None)
        assert cost is None, f"显式声明无价目表却给出了金额：{cost!r}"
        assert calls == [], "显式 None 不得再触发读盘"
        msg = _messages(caplog)
        assert "不回头读盘" in msg, msg
        assert "键缺失" in msg and "值为 null" in msg, "调用方混同要说得出是哪两种混在一起"

    def test_non_object_passed_directly_is_counted_not_crashed(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            cost = gen.estimate_cost_usd(_MODEL, _USAGE, ["not", "a", "table"])  # type: ignore[arg-type]
        assert cost is None
        assert "非对象价目表（list）" in _messages(caplog), _messages(caplog)

    def test_empty_table_is_a_legitimate_none_and_stays_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """价目表在、模型未登记 ⇒ None 是既有诚实条款，不是本轮新增的降级，不得多留一条痕。"""
        p = _write(tmp_path, '{"models": {}}')
        with caplog.at_level(logging.WARNING):
            assert gen.estimate_cost_usd(_MODEL, _USAGE, gen.load_price_table(p)) is None
        assert caplog.records == [], _messages(caplog)

    def test_no_disk_read_happens_inside_the_empty_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`{}` 走的是显式表通道——若被改回 `is not None` 判断，这里会重新读盘。"""
        calls: list[int] = []

        def spy() -> dict[str, Any]:
            calls.append(1)
            return {"models": {_MODEL: {"currency": "USD", "input_per_mtok": 0.3, "output_per_mtok": 1.2}}}

        monkeypatch.setattr(gen, "load_price_table", spy)
        assert gen.estimate_cost_usd(_MODEL, _USAGE, {}) is None
        assert calls == []


# ─── 3. 盘上真表：读数一字不变 ─────────────────────────────────────────────────
class TestRealPriceTableUnchanged:
    def test_repo_table_is_an_object_and_loads_silently(self, caplog: pytest.LogCaptureFixture) -> None:
        assert _PRICE_TABLE.exists(), f"价目表不在库内：{_PRICE_TABLE}"
        raw = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))
        assert isinstance(raw, dict) and isinstance(raw.get("models"), dict) and len(raw["models"]) >= 1
        with caplog.at_level(logging.WARNING):
            loaded = gen.load_price_table(_PRICE_TABLE)
        assert loaded == raw, "真表必须逐字段交出去"
        assert caplog.records == [], f"真表上不得新产生留痕：{_messages(caplog)}"

    def test_estimated_cost_matches_the_explicit_table_path(self, caplog: pytest.LogCaptureFixture) -> None:
        """省略形参与显式传真表必须同值——这条是"本轮没改动计费口径"的读数锁。"""
        with caplog.at_level(logging.WARNING):
            by_default = gen.estimate_cost_usd(_MODEL, _USAGE)
            by_explicit = gen.estimate_cost_usd(_MODEL, _USAGE, gen.load_price_table(_PRICE_TABLE))
        assert by_default == by_explicit is not None, (by_default, by_explicit)
        assert caplog.records == [], _messages(caplog)

    def test_all_priced_models_survive_the_round(self) -> None:
        """每个登记模型都按既有诚实条款计价或明确不计价，不因本轮改造改变归属。"""
        table = gen.load_price_table(_PRICE_TABLE)
        for model, entry in table["models"].items():
            cost = gen.estimate_cost_usd(model, _USAGE, table)
            if str(entry.get("currency") or "").upper() == "USD" and None not in (
                entry.get("input_per_mtok"),
                entry.get("output_per_mtok"),
            ):
                assert isinstance(cost, float) and cost > 0, (model, cost)
            else:
                assert cost is None, (model, cost)

    def test_unknown_model_is_none_without_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            assert gen.estimate_cost_usd("no-such-model", _USAGE, gen.load_price_table(_PRICE_TABLE)) is None
        assert caplog.records == [], _messages(caplog)

    def test_default_argument_binding_is_still_the_repo_table(self) -> None:
        """AB-9 自捕获：默认参数在定义时绑定，改 `gen._PRICE_TABLE_PATH` 不生效——锁住这个事实。"""
        import inspect

        sig = inspect.signature(gen.load_price_table)
        assert sig.parameters["path"].default == _PRICE_TABLE, "默认路径在定义期绑定，桩替换模块变量不影响读取"
