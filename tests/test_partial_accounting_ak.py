"""AK 回归锁：少数无记账行不是免费，也不是精确值（2026-10-21）。

判据链：S11（≥50% 断裂 → NOT_COMPUTABLE）→ AJ（缓存命中是第三种记账状态）
→ **AK：0 < 无记账行 < 50% 时成本仍可算，但它只是已记录花费的下界**。

改前实测（主批 plain_llm_df，三种子合并 261 行）：
- 35/261 行 token_usage 三元组全 0、llm_calls=0，但 generated_test 非空
  （其中 3 行 detection_rate=1.0）；
- S11 判 `computable=True`（13.4% < 50%），成本表把 `$/task=0.004543…`
  当精确值渲染，读者无从知道 35 行以 0 进入分子、却仍占任务分母；
- ext 报告 §4.1 仍显示 "226 行计价 / 0 行不可计价"，35 行在计价健全性里消失。

处置（行级数学口径不动，AE2 锁定）：
1. `token_accounting_sanity` 增 `n_zero_output_rows`（仅 >0 时）：无记账且
   generated_test 非空的子集——"有产出、无花费记录"；
2. `cost_analysis` 在成本可算且 0 < 无记账行时写
   `cost_caliber="recorded_lower_bound"`，并带 `token_zero_output_rows`；
3. 成本表 / $/solved / ext note / 报告 §4 / §4.1 声明"已记录下界、不是免费"；
4. 全记账臂与旧批次返回域、报告文本逐字不变；≥50% 断裂仍 NOT_COMPUTABLE。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as rep
from experiments import statistical_analysis as sa

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_BATCH_FILES = [
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_140906.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_151907.json",
    _ROOT / "experiments/results/main_batch/benchmark_synthetic_20261006_164357.json",
]

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

_LEGACY_SANITY_KEYS = {
    "n_rows",
    "n_without_accounting",
    "zero_share",
    "computable",
    "reason",
}


def _usage(total: Any = 1_000_000, *, inp: Any = 1_000_000, out: Any = 0) -> dict[str, Any]:
    return {
        "total_tokens": total,
        "input_tokens": inp,
        "output_tokens": out,
        "llm_calls": 1,
        "by_model": {"m1": total},
    }


def _zero_usage() -> dict[str, Any]:
    """实测形态：三元组与 llm_calls 全 0、by_model 空。"""
    return {
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
        "by_model": {},
    }


def _cache_only() -> dict[str, Any]:
    """AJ 口径：真实 0 由缓存命中解释，不是无记账。"""
    usage = _zero_usage()
    usage.update({"cache_hits": 1, "cache_avoided_tokens": 1748})
    return usage


def _row(
    usage: dict[str, Any] | None = None,
    *,
    task_id: str = "t",
    generated_test: str | None = None,
    detection: float = 0.0,
) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id, "detection_rate": detection}
    if usage is not None:
        row["token_usage"] = usage
    if generated_test is not None:
        row["generated_test"] = generated_test
    return row


def _partial_rows() -> list[dict[str, Any]]:
    """2 行有记账 + 1 行有产出零记账（1/3 < 50%）。"""
    return [
        _row(_usage(), task_id="t1", detection=1.0),
        _row(_usage(), task_id="t2"),
        _row(_zero_usage(), task_id="t3", generated_test="def test_x():\n    assert True\n", detection=1.0),
    ]


def _main_batch_rows() -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in _MAIN_BATCH_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for arm, block in data["results"].items():
            merged.setdefault(arm, []).extend(block["details"])
    return merged


# ─── 1. S11 子集计数 ───────────────────────────────────────────────────────


class TestSanityOutputSubset:
    def test_zero_rows_with_output_are_counted(self) -> None:
        rows = _partial_rows()
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["computable"] is True
        assert sanity["n_without_accounting"] == 1
        assert sanity["n_zero_output_rows"] == 1

    def test_zero_row_without_output_adds_no_key(self) -> None:
        rows = [_row(_usage()), _row(_usage()), _row(_zero_usage())]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["n_without_accounting"] == 1
        assert "n_zero_output_rows" not in sanity

    def test_full_accounting_domain_is_legacy(self) -> None:
        sanity = sa.token_accounting_sanity([_row(_usage()), _row(_usage())])
        assert set(sanity) == _LEGACY_SANITY_KEYS

    def test_cache_evidence_rows_are_not_zero_output_rows(self) -> None:
        rows = [_row(_usage()), _row(_usage()), _row(_cache_only(), generated_test="def test_y(): pass\n")]
        sanity = sa.token_accounting_sanity(rows)
        assert sanity["n_without_accounting"] == 0
        assert "n_zero_output_rows" not in sanity


# ─── 2. cost_analysis：下界键只在部分记账可算时出现 ─────────────────────────


class TestCostCaliber:
    def test_partial_arm_gets_lower_bound_caliber(self) -> None:
        out = sa.cost_analysis({"a": _partial_rows()}, _PRICES)[0]
        assert out["token_accounting_ok"] is True
        assert out["token_zero_rows"] == 1
        assert out["token_zero_output_rows"] == 1
        assert out["cost_caliber"] == "recorded_lower_bound"
        assert out["cost"] == pytest.approx(2.0)
        # 分母仍是全部任务（AE2 口径）：不是 cost / 2 个"有记账行"
        assert out["cost_per_task"] == pytest.approx(2.0 / 3)

    def test_full_accounting_domain_is_legacy(self) -> None:
        out = sa.cost_analysis({"a": [_row(_usage()), _row(_usage())]}, _PRICES)[0]
        assert set(out) == _LEGACY_COST_KEYS
        assert out["cost_per_task"] == pytest.approx(1.0)

    def test_half_missing_stays_not_computable_without_caliber(self) -> None:
        rows = [_row(_usage()), _row(_zero_usage(), generated_test="x")]
        out = sa.cost_analysis({"a": rows}, _PRICES)[0]
        assert out["token_accounting_ok"] is False
        assert out["token_zero_rows"] == 1
        assert out["token_zero_output_rows"] == 1
        assert "cost_caliber" not in out
        # 行级数学口径不变：数字仍可在 JSON 里复算，呈现层负责拦截
        assert out["cost_per_task"] == pytest.approx(1.0 / 2)

    def test_zero_row_without_output_still_gets_caliber(self) -> None:
        """无产出的空行同样可能漏记花费——下界不依赖产出证据，产出只用于解释。"""
        rows = [_row(_usage()), _row(_usage()), _row(_zero_usage())]
        out = sa.cost_analysis({"a": rows}, _PRICES)[0]
        assert out["cost_caliber"] == "recorded_lower_bound"
        assert "token_zero_output_rows" not in out


# ─── 3. statistical_analysis 报告呈现 ──────────────────────────────────────


class TestCostReportLines:
    def test_partial_arm_renders_lower_bound_note(self) -> None:
        cost_rows = sa.cost_analysis({"a": _partial_rows()}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES, det_rates={"a": 50.0}))
        assert "成本口径下界（AK）" in text
        assert "1/3 行无 token 记账" in text
        assert "generated_test 非空" in text
        assert "已记录花费的下界" in text
        assert "不是免费" in text
        # 表格仍给数字（未达 50% 断裂阈值），下界由注说明
        assert "NOT_COMPUTABLE" not in text

    def test_full_accounting_renders_no_ak_note(self) -> None:
        cost_rows = sa.cost_analysis({"a": [_row(_usage()), _row(_usage())]}, _PRICES)
        text = "\n".join(sa._cost_report_lines(cost_rows, _PRICES))
        assert "（AK）" not in text
        assert "已记录花费的下界" not in text


# ─── 4. report §4 / §4.1 呈现 ─────────────────────────────────────────────


class TestReportSections:
    def test_token_distribution_cell_names_output_subset(self) -> None:
        rows = _partial_rows()
        cost = rep.cost_block(rows)
        assert cost["token_accounting"]["n_zero_output_rows"] == 1
        text = "\n".join(rep._render_cost_section({"a": {"cost": cost}}))
        assert "其中 1 行 generated_test 非空、有产出无花费记录" in text

    def test_cost_effectiveness_counts_zero_rows(self) -> None:
        rows = [*_partial_rows(), _row(_zero_usage(), task_id="t4")]
        eff = rep.cost_effectiveness_block(rows, _PRICES["models"])
        assert eff["n_zero_token_rows"] == 2
        assert eff["n_zero_token_output_rows"] == 1
        assert eff["total_tokens"] == pytest.approx(2_000_000)
        assert eff["n_detection_measurable"] == 4

    def test_full_accounting_keys_absent(self) -> None:
        eff = rep.cost_effectiveness_block([_row(_usage())], _PRICES["models"])
        assert "n_zero_token_rows" not in eff
        assert "n_zero_token_output_rows" not in eff

    def test_section_41_renders_lower_bound_note(self) -> None:
        rows = _partial_rows()
        cost = rep.cost_block(rows)
        eff = rep.cost_effectiveness_block(rows, _PRICES["models"])
        text = "\n".join(rep._render_cost_section({"a": {"cost": cost, "cost_eff": eff}}))
        assert "零 token 行的成本口径（AK）" in text
        assert "1/3 行 token 全 0" in text
        assert "已记录花费的下界" in text
        assert "不是免费" in text

    def test_section_41_full_accounting_has_no_note(self) -> None:
        rows = [_row(_usage())]
        cost = rep.cost_block(rows)
        eff = rep.cost_effectiveness_block(rows, _PRICES["models"])
        text = "\n".join(rep._render_cost_section({"a": {"cost": cost, "cost_eff": eff}}))
        assert "（AK）" not in text


# ─── 5. ext：tokens/task 与 $/task 的 note ─────────────────────────────────


def _world(monkeypatch: pytest.MonkeyPatch, batch: dict[str, Any]) -> None:
    def fake_load(rel: str) -> Any:
        if rel == ext.PRICE_TABLE:
            return _PRICES
        return batch

    monkeypatch.setattr(ext, "_load", fake_load)


def _batch(total_tasks: int, *rows: dict[str, Any]) -> dict[str, Any]:
    return {"total_tasks": total_tasks, "results": {"aitester": {"details": list(rows)}}}


class TestExtensionsNote:
    def test_partial_arm_note_states_lower_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(3, *_partial_rows()))
        tpt, usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert tpt == pytest.approx(2_000_000 / 3)
        assert usd is not None
        assert "1/3 行 token 全 0" in note
        assert "其中 1 行 generated_test 非空" in note
        assert "已记录下界" in note
        assert "不是免费" in note

    def test_full_accounting_note_is_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(2, _row(_usage()), _row(_usage())))
        _tpt, _usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert note == "价目加权（in:out=2000000:0）；未计价模型：无"
        assert "已记录下界" not in note

    def test_cache_only_zero_rows_are_not_lower_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, _batch(2, _row(_usage()), _row(_cache_only(), generated_test="x")))
        _tpt, _usd, note = ext._cost_per_task(["b.json"], "aitester")
        assert "行 token 全 0" not in note
        assert "已记录下界" not in note
        assert "缓存口径" in note


# ─── 6. 真实主批读数（锁定口径，不改写工件）─────────────────────────────────


class TestRealMainBatch:
    def test_plain_llm_df_is_partial_not_free(self) -> None:
        arms = _main_batch_rows()
        rows = arms["plain_llm_df"]
        sanity = sa.token_accounting_sanity(rows)
        assert (sanity["computable"], sanity["n_without_accounting"]) == (True, 35)
        assert sanity["n_zero_output_rows"] == 35

        price = json.loads((_ROOT / ext.PRICE_TABLE).read_text(encoding="utf-8"))
        by_arm = {r["baseline"]: r for r in sa.cost_analysis(arms, price)}
        assert by_arm["plain_llm_df"]["cost_caliber"] == "recorded_lower_bound"
        assert by_arm["plain_llm_df"]["cost_per_task"] == pytest.approx(1.1857833 / 261)
        for arm in ("aitester", "plain_llm"):
            assert by_arm[arm]["token_zero_rows"] == 0
            assert "cost_caliber" not in by_arm[arm]

    def test_main_batch_ext_notes_keep_exact_arms(self) -> None:
        files = [str(p.relative_to(_ROOT)) for p in _MAIN_BATCH_FILES]
        for arm in ("aitester", "plain_llm"):
            _tpt, _usd, note = ext._cost_per_task(files, arm)
            assert "已记录下界" not in note
        _tpt, _usd, note = ext._cost_per_task(files, "plain_llm_df")
        assert "35/261 行 token 全 0" in note
        assert "35 行 generated_test 非空" in note
        assert "已记录下界" in note

    def test_report_41_sees_35_zero_rows(self) -> None:
        arms = _main_batch_rows()
        eff = rep.cost_effectiveness_block(arms["plain_llm_df"])
        assert (eff["n_zero_token_rows"], eff["n_zero_token_output_rows"]) == (35, 35)
        assert eff["n_priced_rows"] == 226
