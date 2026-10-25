"""AH 回归锁：$/task 只在价目覆盖全部 token 且归因闭合时才是金额（2026-10-20）。

判据链：AB-9（静默缩分母才是缺陷）→ AB-11（键缺席 ≠ 值为 null）→ AB-14（判定只写一遍）
→ AB-15（拒绝要有拒绝的形状）→ AB-16（什么能变成金额只写一遍）→ AB-17（表级读取不崩）
→ AG（"未登记"不是"未计价"）→ **AH：不完整的和不是金额**。

改前 `_cost_per_task` 只有"被拒份额"不给金额；其余三种不完整的和照样披着金额的形状：
价目没登记全部模型 → `0.0`（note 只说"未计价模型"）；已登记 + 未登记混合 → 部分和；
`token_usage` 有 token 却无 `by_model` → `0.0` 且 note 声称"未计价模型：无"；`by_model`
合计与 `total_tokens` 不符 → 按错误的分母算出的部分和；`total_tasks=0` → `0.0`
（"无任务"）。处置：以上一律 `usd_per_task=None` 并在 note 点名机制
（`model_unregistered←…` / `no_model_attribution` /
`token_attribution_mismatch:<by_model合计>/<total_tokens>` / 无任务），与既有
`计价被拒：<code>←<模型>` 同一形状。token 总数确实为 0 时 `0.0` 仍是完整和（没有可漏计
的份额），不拒绝。

真批次不变量：三臂 `by_model` 合计与 `total_tokens` 逐位相等（delta 0），故
`0.025884977011494247 / 0.003358973563218391 / 0.004543231034482759` 一字不变；受
`SHA256SUMS` 保护的归档报告不重写。
"""

from __future__ import annotations

from typing import Any

import pytest

from experiments import emse_stats_extensions as ext
from experiments import emse_stats_report as rep

_PRICE = ext.PRICE_TABLE
_BATCH = "ah_synthetic_batch.json"


def _usd(input_per_mtok: float = 2.0, output_per_mtok: float = 8.0) -> dict[str, Any]:
    return {"input_per_mtok": input_per_mtok, "output_per_mtok": output_per_mtok, "currency": "USD"}


def _row(total_tokens: int, *, by_model: Any = "__omit__", input_tokens: int | None = None) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "input_tokens": total_tokens if input_tokens is None else input_tokens,
        "output_tokens": 0,
        "total_tokens": total_tokens,
    }
    if by_model != "__omit__":
        usage["by_model"] = by_model
    return {"token_usage": usage}


def _batch(total_tasks: int, *rows: dict[str, Any]) -> dict[str, Any]:
    return {"total_tasks": total_tasks, "results": {"aitester": {"details": list(rows)}}}


def _world(monkeypatch: pytest.MonkeyPatch, prices: dict[str, Any], batch: dict[str, Any]) -> None:
    def fake_load(rel: str) -> Any:
        return {"models": prices} if rel == _PRICE else batch

    monkeypatch.setattr(ext, "_load", fake_load)


class TestIncompleteSumsAreNotAmounts:
    def test_all_models_unregistered_returns_none_not_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(monkeypatch, {}, _batch(2, _row(100, by_model={"deepseek-flash": 100})))
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert tpt == 50.0
        assert usd is None, "未登记模型不得以 0.0 冒充金额"
        assert "model_unregistered←deepseek-flash" in note
        assert "⇒ $/task 无金额（不是 0）" in note

    def test_partial_coverage_is_not_a_partial_sum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(
            monkeypatch,
            {"deepseek-flash": _usd()},
            _batch(2, _row(100, by_model={"deepseek-flash": 60, "mystery": 40})),
        )
        _, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert usd is None, "已计价份额不得以部分和冒充全额"
        assert "model_unregistered←mystery" in note

    @pytest.mark.parametrize("by_model", ["__omit__", {}], ids=["absent", "empty"])
    def test_missing_by_model_is_named_not_zero(self, monkeypatch: pytest.MonkeyPatch, by_model: Any) -> None:
        _world(monkeypatch, {"deepseek-flash": _usd()}, _batch(2, _row(100, by_model=by_model)))
        _, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert usd is None, "有 token 却无模型归因时 0.0 是编造的金额"
        assert "no_model_attribution" in note

    @pytest.mark.parametrize(("model_total", "total"), [(90, 100), (0, 100), (100, 0)])
    def test_by_model_total_must_equal_total_tokens(
        self, monkeypatch: pytest.MonkeyPatch, model_total: int, total: int
    ) -> None:
        _world(
            monkeypatch,
            {"deepseek-flash": _usd()},
            _batch(2, _row(total, by_model={"deepseek-flash": model_total})),
        )
        _, usd, note = ext._cost_per_task([_BATCH], "aitester")
        assert usd is None, "归因不闭合时按错误分母算出的和不是金额"
        assert f"token_attribution_mismatch:{model_total}/{total}" in note

    def test_true_zero_tokens_is_a_real_zero_amount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """0 token 没有可漏计的份额：0.0 是完整和，不因 AH 口径被拒。"""
        for by_model in ("__omit__", {"deepseek-flash": 0}):
            _world(monkeypatch, {"deepseek-flash": _usd()}, _batch(2, _row(0, by_model=by_model)))
            _, usd, note = ext._cost_per_task([_BATCH], "aitester")
            assert usd == 0.0
            assert "无金额机制" not in note

    def test_zero_tasks_has_no_denominator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(
            monkeypatch,
            {"deepseek-flash": _usd()},
            _batch(0, _row(100, by_model={"deepseek-flash": 100})),
        )
        tpt, usd, note = ext._cost_per_task([_BATCH], "aitester")
        # AI（2026-10-21）按 AH §7 第 1 条把 tokens/task 一并改三态：没有分母时
        # 0.0 与金额的 0.0 同源——都是编造出来的读数。
        assert tpt is None, "没有任务分母时 tokens/task 不是 0"
        assert usd is None, "没有任务就没有每任务金额"
        assert "无任务" in note

    def test_fully_covered_batch_still_gets_an_amount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _world(
            monkeypatch,
            {"deepseek-flash": _usd()},
            _batch(2, _row(100, by_model={"deepseek-flash": 100})),
        )
        _, usd, note = ext._cost_per_task([_BATCH], "aitester")
        # share=1、tpt=50、in:out=100:0、输入单价 2 USD/Mtok ⇒ 50 × 2 / 1e6
        assert usd == pytest.approx(0.0001, abs=0.0)
        assert "无金额机制" not in note


class TestRealBatchUnchanged:
    def test_real_readings_are_bit_identical(self) -> None:
        # 2026-10-25 输入面换代：实测值回钉重建 synthetic 批（历史 0.0259/0.0034/0.0045 随撤回退役）
        got = {
            arm: ext._cost_per_task(ext.MAIN_BATCH_FILES, arm)[1] for arm in ("aitester", "plain_llm", "single_agent")
        }
        assert got == {
            "aitester": 0.00216645,
            "plain_llm": 0.0008745149999999999,
            "single_agent": 0.000997275,
        }

    def test_real_batches_have_closed_attribution(self) -> None:
        """锁住"真读数不变"的前提：三臂 by_model 合计 = total_tokens（delta 0）。"""
        # v0.6 输入面换代：按重建批实际臂遍历
        for arm in ("aitester", "plain_llm", "single_agent"):
            rows = [r for rel in ext.MAIN_BATCH_FILES for r in ext._arm_detection_rows(ext._load(rel), arm)]
            total = sum((r.get("token_usage") or {}).get("total_tokens", 0) or 0 for r in rows)
            attributed = sum(
                t or 0 for r in rows for t in ((r.get("token_usage") or {}).get("by_model") or {}).values()
            )
            assert attributed == total, arm


class TestRenderAndVocabulary:
    def _report(self, usd: float | None, note: str) -> dict[str, Any]:
        return {
            "caliber": "x",
            "bootstrap": {"n": 1, "seed": 42},
            "arms": {
                "a": {
                    "tokens_per_task": 50.0,
                    "tokens_per_task_bootstrap95": [40.0, 60.0],
                    "usd_per_task": usd,
                    "usd_note": note,
                }
            },
            "comparisons": {},
        }

    def test_none_is_rendered_as_no_amount_not_a_dollar(self) -> None:
        text = ext.render_markdown(self._report(None, "无金额机制：model_unregistered←m ⇒ $/task 无金额（不是 0）"))
        assert "—（无金额）" in text
        assert "model_unregistered←m" in text
        assert "$None" not in text

    def test_caliber_lists_the_completeness_requirement(self) -> None:
        text = ext.render_markdown(self._report(0.0, "x"))
        assert "by_model 合计 = total_tokens" in text
        assert "—（无金额）" in text

    def test_unregistered_uses_the_report_site_vocabulary(self) -> None:
        row = {
            "detection_rate": 1.0,
            "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "by_model": {"m": 15}},
        }
        out = rep.cost_effectiveness_block([row], price_table={})
        assert out["n_unpriceable_reasons"] == {"model_unregistered": 1}
