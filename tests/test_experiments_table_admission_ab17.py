"""AB-17 回归锁：价目表**表级读侧准入**收口到共享事实源（2026-10-20）。

判据链：AB-11（键缺席 ≠ 值为 null ≠ 读不动）→ AB-12e/AB-13（`None` 哨兵三态、机制逐一点名）
→ AB-14/AB-15（币种判定只写一遍）→ AB-16（条目级形状/数字域收口 `entry_block_reason`）→
**AB-17：文件 → `models` 层的判定收口到 `src.budget.pricing` 的四个共享助手**
（`table_read_reason` / `load_table_json` / `models_layer` / `load_table_models`）。

改前七处读点各写一套文件/形状判定：同一份坏表在 spec 读出"读不动 / 顶层是 X"，在 report
读出另一套中文短语，在 statistical 又一套，在 ext 上是七处里唯一连空表降级都没有的**直接崩**，
在 run_b8 被 `is_file()` 前置守卫静默吞掉退回内置价——同一种坏，七种读法。机制词汇表
（一处写一遍）：`price_table_file_missing` / `price_table_json_invalid:<T>`（含
`UnicodeDecodeError`，属 `ValueError`）/ `price_table_file_unreadable:<T>` /
`price_table_not_object:<T>` / `models_key_absent`（顶层非空对象缺键）/
`models_not_object:<T>`（键在值非对象，真假一律）；`{}` / `{"models": {}}` 静默
（"空对象没有形状可说"，沿用 statistical AB-14 已注册口径——"真的没登记"与"传错形状"仍分得开）；
`model_unregistered` 只留给**真的键缺席**，值 `null` → `entry_not_object:NoneType`
（经 `entry_block_reason`，AB-11 判据）。

两处记录在案的读法差异（设计如此，不是同源破坏）：① spec 的加载器对 `models` 层 pass-through
——文件级失败在加载器点名，`models` 层形状"谁做的判定谁点名"（消费点 `_price_admission` 读出
同一个码）；② ext 的 `_load` 自持 `is_file()` 前置守卫（既有读取器语义）——目录被它的读取器读成
"缺失"（`price_table_file_missing`），其余六个读点经 `load_table_json` 读成
`price_table_file_unreadable:IsADirectoryError`。

真工件不变量：七处读点在真表上读出**同一份** models 映射；run_b8 的 `table_reason` 披露键
只在表真不可用时写入——真表聚合的 `price` 元数据与受保护目录既有 `REPORT.json` 的 `price`
逐字段相等（故真批次工件逐字节不变的前提成立；聚合一律在 tmp 副本上跑，绝不改写真实目录）。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from experiments import analyze_t1_b2_main_batch as t1
from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as rep
from experiments import run_b8_injection as b8
from experiments import spec_examples_generator as seg
from experiments import statistical_analysis as sa
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_B8_RESULTS_DIR = _ROOT / "experiments" / "results" / "s_round_b8_injection_20261018"

_SITE_FILES = {
    "pricing": _ROOT / "src" / "budget" / "pricing.py",
    "spec": _ROOT / "experiments" / "spec_examples_generator.py",
    "report": _ROOT / "experiments" / "emse_stats_report.py",
    "ext": _ROOT / "experiments" / "emse_stats_extensions.py",
    "statistical": _ROOT / "experiments" / "statistical_analysis.py",
    "analyze": _ROOT / "experiments" / "analyze_t1_b2_main_batch.py",
    "run_b8": _ROOT / "experiments" / "run_b8_injection.py",
}

# 表级机制矩阵：case 名 → 期望机制码（文件内容由 `_materialize` 按 case 名落盘）
_CASES: dict[str, str] = {
    "missing": "price_table_file_missing",
    "syntax": "price_table_json_invalid:JSONDecodeError",
    "binary": "price_table_json_invalid:UnicodeDecodeError",
    "dir": "price_table_file_unreadable:IsADirectoryError",
    "top_list": "price_table_not_object:list",
    "top_null": "price_table_not_object:NoneType",
    "no_models": "models_key_absent",
    "models_list": "models_not_object:list",
    "models_null": "models_not_object:NoneType",
}


def _materialize(tmp_path: Path, case: str) -> Path:
    p = tmp_path / f"{case}.json"
    if case == "missing":
        return p
    if case == "dir":
        p.mkdir()
        return p
    if case == "binary":
        p.write_bytes(b"\xff\xfe{\x00")
        return p
    content = {
        "syntax": "{truncated",
        "top_list": "[1]",
        "top_null": "null",
        "no_models": '{"prices": 1}',
        "models_list": '{"models": [1]}',
        "models_null": '{"models": null}',
    }[case]
    p.write_text(content, encoding="utf-8")
    return p


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return " | ".join(r.getMessage() for r in caplog.records)


def _stub_price_models(monkeypatch: pytest.MonkeyPatch, models: dict[str, Any]) -> None:
    real_load = ext._load

    def fake_load(rel: str) -> Any:
        if rel == ext.PRICE_TABLE:
            return {"models": models}
        return real_load(rel)

    monkeypatch.setattr(ext, "_load", fake_load)


# ─── 1. 一处写一遍：四个助手只在 pricing 定义，七个读点全部接线 ────────────────


class TestVocabularyIsWrittenOnce:
    def _sources(self) -> dict[str, str]:
        return {name: path.read_text(encoding="utf-8") for name, path in _SITE_FILES.items()}

    def test_helpers_are_defined_exactly_once(self) -> None:
        src = self._sources()
        for helper in ("table_read_reason", "load_table_json", "models_layer", "load_table_models"):
            assert sum(s.count(f"def {helper}(") for s in src.values()) == 1, helper
            assert f"def {helper}(" in src["pricing"], helper

    def test_no_site_redefines_a_local_shaping_predicate(self) -> None:
        """改前七处各写一套；中途的 `_price_shape_reason` 草名不得复活。"""
        src = self._sources()
        for name, text in src.items():
            if name == "pricing":
                continue
            for helper in ("table_read_reason", "load_table_json", "models_layer", "load_table_models"):
                assert f"def {helper}(" not in text, f"{name} 重复定义 {helper}"
            assert "_price_shape_reason" not in text, name

    def test_sites_wire_the_shared_helpers(self) -> None:
        src = self._sources()
        assert "from src.budget.pricing import entry_block_reason, load_table_json, models_layer" in src["spec"]
        assert "from src.budget.pricing import entry_block_reason, load_table_json, models_layer" in src["report"]
        assert "from src.budget.pricing import entry_block_reason, models_layer, table_read_reason" in src["ext"]
        assert "from src.budget.pricing import entry_block_reason, load_table_json, models_layer" in src["analyze"]
        assert "from src.budget.pricing import load_table_models" in src["run_b8"]
        assert "pricing.load_table_json(" in src["statistical"]
        assert "pricing.models_layer(" in src["statistical"]


# ─── 2. 行为矩阵：同一份坏表，六个读点读出同一个名字 ──────────────────────────


class TestOneNameAcrossReadSites:
    @pytest.mark.parametrize("case", sorted(_CASES))
    def test_same_bad_table_same_code_everywhere(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
        case: str,
    ) -> None:
        expected = _CASES[case]
        p = _materialize(tmp_path, case)
        got: dict[str, Any] = {}

        # 1. pricing（共享助手本体）
        got["pricing"] = pricing.load_table_models(p)

        # 2. spec：文件级判定在加载器点名；`models` 层形状**不在加载器判定**（pass-through，
        #    "谁做的判定谁点名"——消费时经 `_price_admission` 读出同一个码）
        with caplog.at_level(logging.WARNING):
            loaded = seg.load_price_table(p)
        if case in ("no_models", "models_list", "models_null"):
            assert loaded == json.loads(p.read_text(encoding="utf-8")), "models 层形状原样交出"
            assert caplog.records == [], _messages(caplog)
            assert seg.price_block_reason_for("m", loaded) == expected
        else:
            assert loaded == {}
            assert expected in _messages(caplog), _messages(caplog)
        got["spec"] = expected

        # 3. report：stderr 点名 + 空表
        assert rep._load_price_table(p) == {}
        assert expected in capsys.readouterr().err

        # 4. statistical：stdout 点名 + 包装体空表
        assert sa.load_price_table(str(p)) == {"models": {}}
        assert expected in capsys.readouterr().out

        # 5. ext：读取失败 → (None, 机制名)，不再崩（`_load` 自持 `is_file()` 前置守卫，
        #    目录被它的读取器读成"缺失"——机制词汇同源，读取器差异如实记录）
        monkeypatch.setattr(ext, "PRICE_TABLE", str(p))
        got["ext"] = ext._load_price_models()

        # 6. analyze：表级失败 → (None, 机制名)
        got["analyze"] = t1._load_price_entry(p)

        assert got["pricing"] == ({}, expected)
        assert got["ext"] == (None, "price_table_file_missing" if case == "dir" else expected)
        assert got["analyze"] == (None, expected)
        assert got["spec"] == expected

    def test_pricing_cached_wrapper_names_the_same_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`pricing.load_price_table()`（缓存包装）与其余读点同源：同一套机制码。"""
        for case in ("missing", "models_list"):
            p = _materialize(tmp_path, case)
            monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", p)
            pricing.reset_price_table_cache()
            try:
                with caplog.at_level(logging.WARNING):
                    assert pricing.load_price_table() == {}
                assert _CASES[case] in _messages(caplog), _messages(caplog)
            finally:
                pricing.reset_price_table_cache()


# ─── 3. 空对象静默 doctrine：`{}` 与 `{"models": {}}` 在任何读点都不留痕 ──────


class TestEmptyObjectSilenceDoctrine:
    @pytest.mark.parametrize(("case", "content"), [("empty_obj", "{}"), ("models_empty", '{"models": {}}')])
    def test_empty_table_is_silent_everywhere(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
        case: str,
        content: str,
    ) -> None:
        p = tmp_path / f"{case}.json"
        p.write_text(content, encoding="utf-8")

        assert pricing.load_table_models(p) == ({}, None)

        with caplog.at_level(logging.WARNING):
            got_spec = seg.load_price_table(p)
        # spec 返回域：`{}` 与 `{"models": {}}` 均为合法对象表 ⇒ 原样交出、零留痕
        assert got_spec == json.loads(content)
        assert caplog.records == [], _messages(caplog)
        assert seg.price_block_reason_for("m", got_spec) == "model_unregistered"

        assert rep._load_price_table(p) == {}
        assert capsys.readouterr().err == ""
        assert sa.load_price_table(str(p)) == {"models": {}}
        assert capsys.readouterr().out == ""
        monkeypatch.setattr(ext, "PRICE_TABLE", str(p))
        assert ext._load_price_models() == ({}, None)
        assert t1._load_price_entry(p) == (None, "model_unregistered")

    def test_real_table_is_silent_at_the_same_sites(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))
        with caplog.at_level(logging.WARNING):
            assert seg.load_price_table(_PRICE_TABLE) == raw
        assert caplog.records == [], _messages(caplog)
        assert rep._load_price_table(_PRICE_TABLE) == raw["models"]
        assert capsys.readouterr().err == ""
        assert sa.load_price_table(str(_PRICE_TABLE)) == {"models": raw["models"]}
        assert capsys.readouterr().out == ""
        monkeypatch.setattr(ext, "PRICE_TABLE", str(_PRICE_TABLE))
        _, reason = ext._load_price_models()
        assert reason is None


# ─── 4. 检索层：键缺席（未登记）与值 null（形状）不再共用一个码 ──────────────


class TestAbsentKeyIsNotTheSameAsNullValue:
    def test_spec_null_entry_reads_entry_not_object(self) -> None:
        assert seg.price_block_reason_for("m", {"models": {"m": None}}) == "entry_not_object:NoneType"
        assert seg.price_block_reason_for("m", {"models": {}}) == "model_unregistered"
        assert seg.estimate_cost_usd("m", {"input_tokens": 0, "output_tokens": 0}, {"models": {"m": None}}) is None

    def test_report_null_entry_reads_entry_not_object(self) -> None:
        row = {
            "detection_rate": 1.0,
            "token_usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "by_model": {"m": 15},
            },
        }
        out_null = rep.cost_effectiveness_block([row], price_table={"m": None})
        assert out_null["n_unpriceable_reasons"] == {"entry_not_object:NoneType": 1}
        out_absent = rep.cost_effectiveness_block([row], price_table={})
        assert out_absent["n_unpriceable_reasons"] == {"model_unregistered": 1}

    def test_ext_null_entry_is_rejected_not_unregistered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_price_models(monkeypatch, {"deepseek-flash": None})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is None and "entry_not_object:NoneType" in note
        _stub_price_models(monkeypatch, {})
        _, usd, note = ext._cost_per_task(ext.MAIN_BATCH_FILES, "aitester")
        assert usd is not None and "未计价模型：['deepseek-flash']" in note, note

    def test_analyze_null_entry_is_named_by_entry_predicate(self, tmp_path: Path) -> None:
        p = tmp_path / "t.json"
        p.write_text(json.dumps({"models": {"deepseek-flash": None}}), encoding="utf-8")
        entry, reason = t1._load_price_entry(p)
        assert (entry, reason) == (None, None), "表级成功、条目为 null：机制名归 add_cost 的条目谓词"
        stats: dict[str, Any] = {"token_metrics": {"total_input_tokens": 0, "total_output_tokens": 0}}
        t1.add_cost(stats, entry, reason)
        assert stats["cost_unpriced_reason"] == "entry_not_object:NoneType"
        absent = tmp_path / "absent.json"
        absent.write_text(json.dumps({"models": {}}), encoding="utf-8")
        assert t1._load_price_entry(absent) == (None, "model_unregistered")


# ─── 5. run_b8：`table_reason` 只在表真不可用时写入；真表元数据与受保护报告相等 ──


def _minimal_arm_batch(arm: str) -> dict[str, Any]:
    return {
        "results": {
            arm: {
                "details": [
                    {
                        "task_id": "t1",
                        "stop_reason": "coverage_stall",
                        "iterations": 3,
                        "coverage": 0.0,
                        "passed": False,
                    }
                ],
                "token_metrics": {"total_input_tokens": 1000, "total_output_tokens": 500},
            }
        },
        "provenance": {"model_name": "deepseek-flash", "env_snapshot": {}},
    }


def _make_out_root(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    for arm in ("on", "off"):
        d = out / f"arm_{arm}"
        d.mkdir(parents=True)
        (d / "benchmark_min.json").write_text(json.dumps(_minimal_arm_batch(arm)), encoding="utf-8")
    (out / "PREREG.md").write_text("# PREREG\n", encoding="utf-8")
    return out


def _aggregate(tmp_path: Path, price: str | None) -> dict[str, Any]:
    out = _make_out_root(tmp_path)
    rc = b8.aggregate(argparse.Namespace(out=str(out), price_table=price))
    assert rc == 0
    return json.loads((out / "REPORT.json").read_text(encoding="utf-8"))


class TestRunB8PriceDisclosure:
    def test_real_price_table_matches_the_protected_report(self, tmp_path: Path) -> None:
        report = _aggregate(tmp_path, str(_PRICE_TABLE))
        protected = json.loads((_B8_RESULTS_DIR / "REPORT.json").read_text(encoding="utf-8"))
        assert report["price"] == protected["price"]
        assert "table_reason" not in report["price"]

    def test_missing_price_table_discloses_mechanism_and_falls_back(self, tmp_path: Path) -> None:
        report = _aggregate(tmp_path, str(tmp_path / "nope.json"))
        assert report["price"]["source"] == "builtin deepseek-flash standard price"
        assert report["price"]["table_reason"] == "price_table_file_missing"

    def test_shape_broken_price_table_discloses_its_code(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.json"
        p.write_text('{"models": [1]}', encoding="utf-8")
        report = _aggregate(tmp_path, str(p))
        assert report["price"]["table_reason"] == "models_not_object:list"

    def test_empty_object_price_table_is_silent(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.json"
        p.write_text("{}", encoding="utf-8")
        report = _aggregate(tmp_path, str(p))
        assert report["price"] == {"source": "builtin deepseek-flash standard price", "as_of": "2026-10-06"}

    def test_valid_entry_price_is_taken(self, tmp_path: Path) -> None:
        p = tmp_path / "custom.json"
        p.write_text(
            json.dumps({"models": {"deepseek-flash": {"input_per_mtok": 0.5, "output_per_mtok": 2.0}}}),
            encoding="utf-8",
        )
        report = _aggregate(tmp_path, str(p))
        assert report["price"]["model"] == "deepseek-flash"
        assert (report["price"]["input_per_mtok"], report["price"]["output_per_mtok"]) == (0.5, 2.0)


# ─── 6. 真表：七个读点读出同一份 models 映射 ─────────────────────────────────


class TestSevenReadersOneRealTable:
    def test_all_readers_yield_the_same_real_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = json.loads(_PRICE_TABLE.read_text(encoding="utf-8"))
        models_expected = raw["models"]
        monkeypatch.setattr(ext, "PRICE_TABLE", str(_PRICE_TABLE))

        assert pricing.load_table_models(_PRICE_TABLE) == (models_expected, None)
        monkeypatch.setattr(pricing, "_PRICE_TABLE_PATH", _PRICE_TABLE)
        pricing.reset_price_table_cache()
        try:
            assert pricing.load_price_table() == models_expected
        finally:
            pricing.reset_price_table_cache()
        assert seg.load_price_table(_PRICE_TABLE) == raw
        assert rep._load_price_table(_PRICE_TABLE) == models_expected
        assert sa.load_price_table(str(_PRICE_TABLE)) == {"models": models_expected}
        entry, reason = t1._load_price_entry(_PRICE_TABLE)
        assert reason is None and entry == models_expected["deepseek-flash"]
        assert ext._load_price_models() == (models_expected, None)
        b8_table, b8_reason = b8.load_table_models(_PRICE_TABLE)
        assert b8_reason is None and b8_table == models_expected
