"""AE 批次测试（2026-10-06 第十一轮审查落地）。

覆盖四项（对应第十一轮系统性审查报告 N4/N8/AE3/N9 自主执行项）：
- AE1：预注册文档双语配对存在性 + 预注册判定阈值锁定
  （E1 spec_compile_rate ≥0.3 保留 / <0.2 放弃 / 灰区一次迭代；
  E2 双门通道归零与收敛终点——阈值改动必须显式改本测试，防静默漂移）；
- AE2：$/task 成本口径——价目表 schema、cost_analysis 计价数学、
  价目缺失 None 安全（不编造价格）、报告章节行；
- AE3：Makefile clean-traces 目标存在性（静态守卫）。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程。
论文骨架（.private/paper/OUTLINE.md）为本地私有工件（gitignore 全覆盖），
按隐私隔离约定不入库、不加测试依赖。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import ClassVar

import pytest

from experiments.statistical_analysis import (
    _cost_report_lines,
    cost_analysis,
    load_price_table,
    run_all_statistics,
)

_ROOT = Path(__file__).resolve().parents[1]


# ─── AE1：预注册文档锁定 ─────────────────────────────────────────────────────


class TestPreregistrationDoc:
    """E1/E2 跑前落盘的预注册工件（效力见 docs/preregistration.md 头部声明）。"""

    def test_bilingual_pair_exists(self) -> None:
        """双语配对存在且非空（docs/ 门禁要求 .md ↔ .en.md 成对）。"""
        zh = _ROOT / "docs" / "preregistration.md"
        en = _ROOT / "docs" / "preregistration.en.md"
        assert zh.exists() and zh.stat().st_size > 1000
        assert en.exists() and en.stat().st_size > 1000

    def test_last_updated_lines_synced(self) -> None:
        """中英文版"最后更新"日期一致（check_bilingual_docs 的 fail 项）。"""
        zh = (_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
        en = (_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
        zh_date = next(line for line in zh.splitlines() if "最后更新" in line)
        en_date = next(line for line in en.splitlines() if "Last updated" in line)
        # AN2/AN5（2026-10-07）呈现性增补入 E3 节——日期随批升级
        assert "2026-10-07" in zh_date
        assert "2026-10-07" in en_date

    def test_e1_thresholds_locked(self) -> None:
        """E1 预注册判定阈值三段齐备：≥0.3 保留 / <0.2 放弃 / 灰区一次迭代。"""
        zh = (_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
        en = (_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
        for text in (zh, en):
            assert "spec_compile_rate" in text
            assert "0.3" in text and "0.2" in text

    def test_e2_endpoints_locked(self) -> None:
        """E2 主终点锁定：过红/抹红通道归零 + aitester vs df 收敛判定。"""
        zh = (_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
        en = (_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
        for zh_frag, en_frag in (("过红", "over-red"), ("抹红", "erase-red")):
            assert zh_frag in zh
            assert en_frag in en
        for text in (zh, en):
            assert "plain_llm_df" in text
            assert "95% CI" in text

    def test_execution_log_table_pending(self) -> None:
        """执行记录表状态锁：E1/E2+E3/E4 均已执行（判定回填）。

        2026-10-09：E4 由「待执行」推进为「已执行」（aitester 单臂首跑，
        detection 0/41 主终点失败；见 preregistration E4 行与
        「E4 数据集口径增补」）。本断言原为"E4 行仍在且未被删除"的非退化
        守卫，故锚定 **行存在 + 状态 ∈ {待执行, 已执行}**，而非冻结某一个
        状态字面量（同 test_am_batch E6 口径先例：守卫不应成为状态冻结点）。
        """
        zh = (_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
        # E1 于 2026-10-07 执行：spec_compile_rate=0.367 ≥ 0.3 → 保留
        # E2+E3 于 2026-10-07 执行：通道降幅 67%/85.7% 过停止线 → 恰好一次
        # 迭代分支；H2c 显著为负 → 结论升级
        # （合法状态演进，AO 改 cap 同步 test_am 先例：锁随执行记录推进）
        assert "| E1 | 已执行" in zh
        assert "0.367" in zh
        assert "experiments/results/ab1_validation_e1/" in zh
        assert "| E2+E3 | 已执行" in zh
        assert "−0.3673" in zh
        assert "| E4 |" in zh
        assert ("E4 | 待执行" in zh) or ("E4 | **已执行" in zh)


# ─── AE2：$/task 成本口径 ────────────────────────────────────────────────────


def _make_row(input_tokens: int, output_tokens: int, model: str | None = "deepseek-flash") -> dict:
    """构造最小 token_usage 结果行（与 run_benchmark 行字段同构）。"""
    total = input_tokens + output_tokens
    tu: dict = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total}
    if model is not None:
        tu["by_model"] = {model: total}
    return {"task_id": "t", "token_usage": tu}


class TestPriceTable:
    """价目表加载与 schema（诚实条款：null = 不计价，不编造）。"""

    def test_repo_price_table_schema(self) -> None:
        """入库价目表：models 为 dict，数值字段 null 或非负数，币种为字符串。"""
        table = load_price_table(_ROOT / "experiments" / "price_table.json")
        models = table["models"]
        assert isinstance(models, dict) and len(models) >= 1
        for name, entry in models.items():
            assert isinstance(name, str) and isinstance(entry, dict)
            for key in ("input_per_mtok", "output_per_mtok"):
                value = entry[key]
                assert value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0)
            assert isinstance(entry.get("currency", "USD"), str)

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """文件缺失 → 空表（不抛异常，成本节按未登记口径）。"""
        assert load_price_table(tmp_path / "nope.json") == {"models": {}}

    def test_none_path_returns_empty(self) -> None:
        """None 路径 → 空表。"""
        assert load_price_table(None) == {"models": {}}


class TestCostAnalysis:
    """cost_analysis 计价数学与 None 安全。"""

    _PRICES: ClassVar[dict] = {
        "models": {
            "m1": {
                "input_per_mtok": 1.0,
                "output_per_mtok": 2.0,
                "currency": "USD",
                "source": "test",
                "as_of": "2026-10-06",
            },
        }
    }

    def test_priced_math_exact(self) -> None:
        """计价数学：Σin×单价_in + Σout×单价_out，$/task = 成本/任务数。

        2 任务：in=2,000,000 out=1,000,000 → 成本 = 2×1 + 1×2 = 4.0 →
        $/task = 2.0。
        """
        results = {
            "a": [
                _make_row(1_500_000, 600_000, "m1"),
                _make_row(500_000, 400_000, "m1"),
            ]
        }
        rows = cost_analysis(results, self._PRICES)
        assert len(rows) == 1
        r = rows[0]
        assert r["n_tasks"] == 2
        assert r["input_tokens"] == 2_000_000
        assert r["output_tokens"] == 1_000_000
        assert r["priced"] is True
        assert r["cost"] == pytest.approx(4.0)
        assert r["cost_per_task"] == pytest.approx(2.0)
        assert r["currency"] == "USD"

    def test_missing_price_is_none(self) -> None:
        """价目未登记 → cost=None / priced=False / missing_models 列出（不编造）。"""
        results = {"a": [_make_row(1000, 2000, "unknown-model")]}
        rows = cost_analysis(results, self._PRICES)
        r = rows[0]
        assert r["priced"] is False
        assert r["cost"] is None
        assert r["cost_per_task"] is None
        assert r["missing_models"] == ["unknown-model"]

    def test_missing_token_usage_counts_zero(self) -> None:
        """无 token_usage 的行计 0 token 但仍进任务数分母。"""
        results = {"a": [_make_row(1_000_000, 0, "m1"), {"task_id": "t2"}]}
        rows = cost_analysis(results, self._PRICES)
        r = rows[0]
        assert r["n_tasks"] == 2
        assert r["input_tokens"] == 1_000_000
        assert r["cost_per_task"] == pytest.approx(1.0 / 2)

    def test_unattributed_tokens_disclosed(self) -> None:
        """有总 token 但缺 by_model 的行 → unattributed_tokens 披露、不计成本。"""
        results = {"a": [_make_row(1_000_000, 1_000_000, model=None)]}
        rows = cost_analysis(results, self._PRICES)
        r = rows[0]
        assert r["input_tokens"] == 1_000_000
        assert r["unattributed_tokens"] == 2_000_000
        assert r["priced"] is False

    def test_mixed_price_models_degrade_to_none(self) -> None:
        """多模型异价 → in/out 无法按模型拆分归属，成本诚实降级 None。"""
        prices = {
            "models": {
                "m1": dict(self._PRICES["models"]["m1"]),
                "m2": {
                    "input_per_mtok": 3.0,
                    "output_per_mtok": 4.0,
                    "currency": "USD",
                    "source": "test",
                    "as_of": "2026-10-06",
                },
            }
        }
        results = {"a": [_make_row(1_000_000, 0, "m1"), _make_row(0, 1_000_000, "m2")]}
        r = cost_analysis(results, prices)[0]
        assert r["priced"] is False
        assert r["missing_models"] == []


class TestCostReportLines:
    """报告成本章节行（齐备 → 表格；缺失 → 诚实提示）。"""

    def test_unpriced_note_lists_models(self) -> None:
        """价目缺失 → "价目未登记" + 待计价模型清单。"""
        rows = cost_analysis({"a": [_make_row(100, 100, "m-x")]}, {"models": {}})
        text = "\n".join(_cost_report_lines(rows, {"models": {}}))
        assert "价目未登记" in text
        assert "m-x" in text

    def test_priced_table_rows(self) -> None:
        """价目齐全 → Markdown 表含 $/task 数字。"""
        rows = cost_analysis({"a": [_make_row(1_000_000, 1_000_000, "m1")]}, TestCostAnalysis._PRICES)
        text = "\n".join(_cost_report_lines(rows, TestCostAnalysis._PRICES))
        assert "| a | 1 | 1000000 | 1000000 | 3.0000 | USD |" in text

    def test_partial_priced_note(self) -> None:
        """部分基线未计价 → 表格 + 尾注。"""
        results = {
            "a": [_make_row(1_000_000, 0, "m1")],
            "b": [_make_row(0, 1_000_000, "m-unknown")],
        }
        text = "\n".join(_cost_report_lines(cost_analysis(results, TestCostAnalysis._PRICES), TestCostAnalysis._PRICES))
        assert "| a | 1 | 1000000 | 0 | 1.0000 | USD |" in text
        assert "1 个基线未计价" in text
        assert "m-unknown" in text


class TestWiring:
    """接线守卫：run_all_statistics 接受 price_table（向后兼容默认 None）。"""

    def test_run_all_statistics_signature(self) -> None:
        params = inspect.signature(run_all_statistics).parameters
        assert "price_table" in params
        assert params["price_table"].default is None

    def test_price_table_json_valid(self) -> None:
        """入库价目表 JSON 可解析（防手改破坏 schema）。"""
        data = json.loads((_ROOT / "experiments" / "price_table.json").read_text(encoding="utf-8"))
        assert isinstance(data.get("models"), dict)


# ─── AE3：Makefile clean-traces 目标 ─────────────────────────────────────────


class TestMakefileCleanTraces:
    """tmp_trace 残留治理入口（静态守卫）。"""

    def test_target_and_phony_declared(self) -> None:
        makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "clean-traces:" in makefile
        phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))
        assert "clean-traces" in phony

    def test_target_removes_tmp_trace_only(self) -> None:
        """目标体只清理 tmp_trace/（防 clean 目标误伤其他路径）。"""
        makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
        target_body = makefile.split("clean-traces:", 1)[1]
        recipe = target_body.split("\n")[1]  # 紧随其后的第一条 recipe 行
        assert "rm -rf tmp_trace" in recipe
