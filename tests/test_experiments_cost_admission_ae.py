"""AE 轮回归锁：run_b8 聚合器的**价目条目级准入**接共享谓词（2026-10-20）。

判据链：AB-13（能不能计价）→ AB-14（是不是美元）→ AB-15（拒绝的呈现与归因）→
AB-16（条目级准入域 `entry_block_reason` 一处写一遍）→ AB-17（表级读侧准入
`load_table_models`）→ **AE：聚合脚本 `experiments/run_b8_injection.py::aggregate`
不再自持 `isinstance(..., (int, float))` 数字门，条目级准入接 `src.budget.pricing.entry_block_reason`。**

改前后果（前置普查 `/tmp/ae_work/AE_PRECHECK_REPORT.md` §A，只读 + 只写 tmp 实测）：
`bool`（`int` 子类）/ `nan` / `inf` / 负价都被该式收下计价——`nan`/`inf` 还会经
`_write_json`（`json.dumps` 默认 `allow_nan=True`）写进 `REPORT.json`，产出非 RFC-8259 的
裸 `NaN`/`Infinity`；`currency=CNY` 被当 USD 记进 `cost_usd_standard_price`；字符串价与
批次 `provenance.model_name` 未登记**静默**退回内置 deepseek-flash 标准价，报告与 README
里与"真表读数"同形、无任何机制披露。真实批次 0 命中（两份聚合工件均真表 USD），
故本轮目标是"未来误配不再静默"，不纠历史读数。

修复口径：
- 条目级：`model not in table` → `model_unregistered`（"没登记"与"登记了但读不出"是两种
  事实，不共用码）；否则 `entry_block_reason(entry)`（形状 / 空条目 / 币种 / 数字域）；
- 接受路径 `price_meta` 键集与改前**逐字节相同**（真表读数须与受保护 `REPORT.json` 的
  `price` 逐字段相等 ⇒ 真工件逐字节不变的前提）；
- 拒绝路径：内置 deepseek-flash 标准价（0.3 / 1.2）兜底 + `logger.warning` 点名 model 与
  机制码 + `price_meta.model` / `price_meta.entry_reason`（**不写** input/output 数字键
  ⇒ 拒绝的价与 nan/inf 不进入工件）；
- 表级失败（缺表 / 坏表）行为一律不变（只有 `table_reason`，不写 `entry_reason`）；
- README 只在表级或条目级不可用时追加一行"价目不可用"披露（真表输出空串）。

所有工件都在 `tmp_path` 上生成；受保护目录
`experiments/results/s_round_b8_injection_20261018/` **只读**（真工件回归在副本上跑，
一份真实工件都不改写）。缺工件即 `pytest.fail`，不 skip。
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest

from experiments import run_b8_injection as b8
from src.budget import pricing

_ROOT = Path(__file__).resolve().parents[1]
_PRICE_TABLE = _ROOT / "experiments" / "price_table.json"
_B8_RESULTS_DIR = _ROOT / "experiments" / "results" / "s_round_b8_injection_20261018"

_MODEL = "deepseek-flash"
_IN_TOKENS = 1000
_OUT_TOKENS = 500
#: 内置兜底价（`run_b8_injection.DEFAULT_PRICE_USD_{IN,OUT}_PER_MTOK` = 0.3 / 1.2）下的
#: 逐臂成本：1000 in × 0.3/M + 500 out × 1.2/M = 0.0003 + 0.0006（6 位四舍五入）
_EXPECTED_BUILTIN_ARM_COST = 0.0009
_EXPECTED_BUILTIN_TOTAL_COST = 0.0018
#: 受保护 `experiments/results/s_round_b8_injection_20261018/REPORT.json` 的真表读数
_PROTECTED_ARM_COSTS = {"on": 0.046531, "off": 0.060761}
_PROTECTED_TOTAL_COST = 0.107292


def _models(entry: Any) -> dict[str, Any]:
    """单模型价目条的 `models` 层（批次 provenance 的 model_name 恒为 deepseek-flash）。"""
    return {_MODEL: entry}


def _usd_entry(**overrides: Any) -> dict[str, Any]:
    entry = {"input_per_mtok": 0.5, "output_per_mtok": 2.0, "currency": "USD"}
    entry.update(overrides)
    return entry


# 条目变体矩阵：case → (`models` 层, 期望 `price.entry_reason`)
_PRICE_CASES: dict[str, tuple[dict[str, Any], str]] = {
    "currency_absent": (_models({"input_per_mtok": 0.5, "output_per_mtok": 2.0}), "currency_absent"),
    "currency_not_usd": (_models(_usd_entry(currency="CNY")), "currency_not_usd:CNY"),
    "currency_null": (_models(_usd_entry(currency=None)), "currency_absent"),
    "currency_blank": (_models(_usd_entry(currency="   ")), "currency_absent"),
    "price_null": (_models(_usd_entry(input_per_mtok=None)), "price_null"),
    "price_bool": (_models(_usd_entry(input_per_mtok=True)), "price_not_a_number:bool"),
    "price_str": (_models(_usd_entry(input_per_mtok="0.5")), "price_not_a_number:str"),
    "price_nan": (_models(_usd_entry(input_per_mtok=float("nan"))), "price_not_finite:nan"),
    "price_inf": (_models(_usd_entry(output_per_mtok=float("inf"))), "price_not_finite:inf"),
    "price_negative": (_models(_usd_entry(input_per_mtok=-0.5)), "price_negative"),
    "entry_empty": (_models({}), "entry_empty"),
    "entry_not_object": (_models([0.5, 2.0]), "entry_not_object:list"),
    # 表里登记了别的模型：键缺席 ≠ 值读不出（AB-11 判据，不共用码）
    "model_unregistered": ({"other-model": _usd_entry()}, "model_unregistered"),
}


def _minimal_arm_batch(arm: str, model_name: str = _MODEL) -> dict[str, Any]:
    """最小批次 JSON（结构与 run_benchmark 产出一致，只留聚合必需字段）。"""
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
                "token_metrics": {"total_input_tokens": _IN_TOKENS, "total_output_tokens": _OUT_TOKENS},
            }
        },
        "provenance": {"model_name": model_name, "env_snapshot": {}},
    }


def _make_out_root(base: Path, model_name: str = _MODEL) -> Path:
    """构造两臂工件 + PREREG（聚合前置条件），返回 out 根。"""
    out = base / "out"
    for arm in ("on", "off"):
        d = out / f"arm_{arm}"
        d.mkdir(parents=True)
        (d / "benchmark_min.json").write_text(json.dumps(_minimal_arm_batch(arm, model_name)), encoding="utf-8")
    (out / "PREREG.md").write_text("# PREREG\n", encoding="utf-8")
    return out


def _write_price_table(base: Path, models: dict[str, Any]) -> Path:
    """落盘合成价目表（nan/inf 用例按 JSON 默认 `allow_nan=True` 构造坏输入）。"""
    base.mkdir(parents=True, exist_ok=True)
    p = base / "price.json"
    p.write_text(json.dumps({"models": models}), encoding="utf-8")
    return p


def _aggregate(base: Path, price: str | None, model_name: str = "deepseek-flash") -> tuple[Path, dict[str, Any]]:
    """跑生产 `aggregate()`（零 LLM），返回 (out 根, REPORT.json 解析结果)。"""
    out = _make_out_root(base, model_name)
    rc = b8.aggregate(argparse.Namespace(out=str(out), price_table=price))
    assert rc == 0
    report = json.loads((out / "REPORT.json").read_text(encoding="utf-8"))
    return out, report


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return " | ".join(record.getMessage() for record in caplog.records)


# ─── 1. 条目变体矩阵：拒绝 → 内置价兜底 + 机制码点名（改前全部静默或错收） ─────


class TestEntryRejectionMatrix:
    @pytest.mark.parametrize("case", sorted(_PRICE_CASES))
    def test_rejected_entry_falls_back_to_builtin_price_and_names_the_reason(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, case: str
    ) -> None:
        models, expected = _PRICE_CASES[case]
        price_path = _write_price_table(tmp_path, models)
        with caplog.at_level(logging.WARNING, logger=b8.logger.name):
            out, report = _aggregate(tmp_path, str(price_path))

        price = report["price"]
        assert price["entry_reason"] == expected
        assert price["source"] == "builtin deepseek-flash standard price"
        assert price["model"] == _MODEL
        # 拒绝路径的 price 键集精确：内置来源 + as_of + model + entry_reason（多一键少一键都算口径变化）
        assert set(price) == {"source", "as_of", "model", "entry_reason"}
        # 表级成功（只是条目不合格）⇒ 不得写 table_reason；拒绝的价不得写进数字键
        assert "table_reason" not in price
        assert "input_per_mtok" not in price and "output_per_mtok" not in price
        # 成本按内置 0.3 / 1.2 计算（拒绝的价不参与任何金额）
        assert report["arms"]["on"]["cost_usd_standard_price"] == _EXPECTED_BUILTIN_ARM_COST
        assert report["arms"]["off"]["cost_usd_standard_price"] == _EXPECTED_BUILTIN_ARM_COST
        assert report["verdict"]["cost_total_usd"] == _EXPECTED_BUILTIN_TOTAL_COST
        # 机制披露：logger 同时点名 model 与机制码（改前无任何披露）
        messages = _messages(caplog)
        assert _MODEL in messages and expected in messages, messages

        if expected.startswith("price_not_finite"):
            # nan/inf 不得进入工件：RFC-8259 严格 JSON（无裸 NaN/Infinity）
            text = (out / "REPORT.json").read_text(encoding="utf-8")
            assert "NaN" not in text and "Infinity" not in text
            assert json.loads(text)["price"]["entry_reason"] == expected


# ─── 2. 反例（必须转绿）：合法条目不被误拒（不是"一律拒"） ────────────────────


class TestAcceptedEntries:
    def test_valid_usd_custom_entry_is_accepted_with_its_own_price(self, tmp_path: Path) -> None:
        price_path = _write_price_table(
            tmp_path, _models(_usd_entry(source="https://example.test/pricing", as_of="2026-10-20"))
        )
        _, report = _aggregate(tmp_path, str(price_path))
        assert report["price"] == {
            "source": "https://example.test/pricing",
            "currency": "USD",
            "as_of": "2026-10-20",
            "model": _MODEL,
            "input_per_mtok": 0.5,
            "output_per_mtok": 2.0,
        }
        assert "entry_reason" not in report["price"]
        # 1000 in × 0.5/M + 500 out × 2.0/M = 0.0005 + 0.001
        assert report["arms"]["on"]["cost_usd_standard_price"] == 0.0015
        assert report["verdict"]["cost_total_usd"] == 0.003

    def test_zero_price_entry_is_accepted_not_falsy_rejected(self, tmp_path: Path) -> None:
        """0.0 是**合法**登记价（真零 ≠ 拒绝），改前改后都不得被 falsy 判断误拒。"""
        price_path = _write_price_table(tmp_path, _models(_usd_entry(input_per_mtok=0.0, output_per_mtok=0.0)))
        _, report = _aggregate(tmp_path, str(price_path))
        assert "entry_reason" not in report["price"]
        assert (report["price"]["input_per_mtok"], report["price"]["output_per_mtok"]) == (0.0, 0.0)
        assert report["arms"]["on"]["cost_usd_standard_price"] == 0.0
        assert report["verdict"]["cost_total_usd"] == 0.0


# ─── 3. 真表 + 真 provenance：受保护读数逐位不变（真工件逐字节不变的前提） ─────


class TestRealArtifactsUnchanged:
    def test_real_table_reaggregation_matches_protected_readings(self, tmp_path: Path) -> None:
        """把受保护目录**整目录副本**复制到 tmp_path 重聚合真表：
        `price` / `cost_total_usd` / 两臂 `cost_usd_standard_price` 与受保护 REPORT.json
        逐位相等，且成本可按登记价从两臂 token 逐位复算；`README.md` / `ISOLATION.json`
        重生成后与受保护文件**逐字节相同**（真工件逐字节不变的前提；真实目录一份未改写）。"""
        if not (_B8_RESULTS_DIR / "REPORT.json").is_file():
            pytest.skip(
                f"受保护聚合工件缺失（本测试不做 skip）：{_B8_RESULTS_DIR}（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前：语料前提缺失改具名 skip，重跑落盘后自动恢复判定）"
            )
        out = tmp_path / "out"
        shutil.copytree(_B8_RESULTS_DIR, out)

        rc = b8.aggregate(argparse.Namespace(out=str(out), price_table=str(_PRICE_TABLE)))
        assert rc == 0
        report = json.loads((out / "REPORT.json").read_text(encoding="utf-8"))
        protected = json.loads((_B8_RESULTS_DIR / "REPORT.json").read_text(encoding="utf-8"))

        assert report["price"] == protected["price"]
        assert "entry_reason" not in report["price"] and "table_reason" not in report["price"]
        assert report["verdict"]["cost_total_usd"] == protected["verdict"]["cost_total_usd"]
        assert report["verdict"]["cost_total_usd"] == _PROTECTED_TOTAL_COST
        price = protected["price"]
        for arm in ("on", "off"):
            got = report["arms"][arm]["cost_usd_standard_price"]
            assert got == protected["arms"][arm]["cost_usd_standard_price"]
            assert got == _PROTECTED_ARM_COSTS[arm]
            token_metrics = report["arms"][arm]["token_metrics"]
            expected = round(
                token_metrics["total_input_tokens"] / 1e6 * price["input_per_mtok"]
                + token_metrics["total_output_tokens"] / 1e6 * price["output_per_mtok"],
                6,
            )
            assert got == expected
        # 真表路径渲染输出逐字节不变（README 含 §4 成本行；ISOLATION 含两臂快照）
        for name in ("README.md", "ISOLATION.json"):
            assert (out / name).read_bytes() == (_B8_RESULTS_DIR / name).read_bytes(), name


# ─── 4. 表级失败不回归：只有 table_reason，不写 entry_reason ───────────────────


class TestTableLevelFailureUnchanged:
    @pytest.mark.parametrize(
        ("case", "content", "expected"),
        [
            ("missing", None, "price_table_file_missing"),
            ("broken_models", '{"models": [1]}', "models_not_object:list"),
        ],
    )
    def test_table_level_failure_writes_table_reason_only(
        self, tmp_path: Path, case: str, content: str | None, expected: str
    ) -> None:
        path = tmp_path / f"{case}.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        _, report = _aggregate(tmp_path, str(path))
        price = report["price"]
        assert price["table_reason"] == expected
        assert "entry_reason" not in price
        assert "input_per_mtok" not in price and "output_per_mtok" not in price
        # 表级失败照旧兜底内置价（AB-17 行为不回归）
        assert report["arms"]["on"]["cost_usd_standard_price"] == _EXPECTED_BUILTIN_ARM_COST
        assert report["verdict"]["cost_total_usd"] == _EXPECTED_BUILTIN_TOTAL_COST


# ─── 5. README 披露：拒绝/表级不可用才有"价目不可用"行（真表为空串） ──────────


class TestReadmePriceDisclosure:
    def test_rejection_paths_disclose_mechanism_and_builtin_ceiling(self, tmp_path: Path) -> None:
        # ① 条目级拒绝（CNY 被当 USD 计价是改前错收 → 现拒绝并点名）
        cny_path = _write_price_table(tmp_path / "entry", _models(_usd_entry(currency="CNY")))
        entry_out, entry_report = _aggregate(tmp_path / "entry", str(cny_path))
        entry_readme = (entry_out / "README.md").read_text(encoding="utf-8")
        assert entry_report["price"]["entry_reason"] == "currency_not_usd:CNY"
        assert "价目不可用" in entry_readme
        assert "`currency_not_usd:CNY`" in entry_readme
        assert "标准价上界" in entry_readme
        assert "不是该模型/价目表登记价" in entry_readme
        # 披露行在 §4 成本合计段之后、§5 之前
        assert entry_readme.index("价目不可用") > entry_readme.index("成本合计 ≈")
        assert entry_readme.index("价目不可用") < entry_readme.index("## 5. 配对")

        # ② 表级失败（缺表）：同一行披露表级机制码
        table_out, table_report = _aggregate(tmp_path / "table", str(tmp_path / "table" / "nope.json"))
        table_readme = (table_out / "README.md").read_text(encoding="utf-8")
        assert table_report["price"]["table_reason"] == "price_table_file_missing"
        assert "价目不可用" in table_readme
        assert "`price_table_file_missing`" in table_readme
        assert "标准价上界" in table_readme

    def test_real_table_path_readme_has_no_disclosure(self, tmp_path: Path) -> None:
        """真表路径输出空串 ⇒ 既有真工件 README 逐字节不变（不加行、不改行）。"""
        out, report = _aggregate(tmp_path, str(_PRICE_TABLE))
        readme = (out / "README.md").read_text(encoding="utf-8")
        assert "entry_reason" not in report["price"] and "table_reason" not in report["price"]
        assert "价目不可用" not in readme


# ─── 6. 词汇判据：未登记与"登记了但读不出"不共用码（AB-11 判据） ──────────────


class TestEntryReasonVocabulary:
    def test_unregistered_is_distinct_from_unreadable_entry(self) -> None:
        assert b8._price_entry_reason({}, _MODEL) == "model_unregistered"
        assert b8._price_entry_reason({_MODEL: None}, _MODEL) == "entry_not_object:NoneType"
        assert b8._price_entry_reason({"other-model": _usd_entry()}, _MODEL) == "model_unregistered"
        assert b8._price_entry_reason(_models(_usd_entry()), _MODEL) is None
        # 同一张坏条目在共享谓词下的读数（不接受路径 = None 才计价）
        assert pricing.entry_block_reason(_usd_entry(currency="USD")) is None
