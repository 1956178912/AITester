"""AN 批次测试（2026-10-07 第十四轮审查落地）。

覆盖五项（对应第十四轮系统性审查报告 N1/N2/N4/N5/N6 自主执行项）：
- AN1：TestGenEval L2 候补评估登记——CC BY-NC 4.0 许可结论
  （GitHub API `spdx_id=NOASSERTION` + LICENSE 原文核实）在
  real_benchmark_upgrade.md 与 DATA_CARD 双语锁定（许可结论改动必须
  显式改本测试，防静默漂移——AJ 批 QuixBugs 溯源守卫同口径）；
- AN2：测试套件可靠性聚合（mutation_reliability_summary）——可测行
  均值、None 不进分母（保守不误报 0）、杀灭/变异体合计、全不可测
  诚实披露；报告章节含"呈现性增补"声明；
- AN4：属性模板路线预注册草案骨架存在性 + 触发条件/红线/草案阈值锁定
  （E1 失败出口占位，激活前零实验）；
- AN5：$/detection 推导（cost_per_detection 除零/缺数 None 安全；
  _cost_report_lines 追加"成本/检出"列；det_rates=None 时与 AE2
  历史格式逐位一致——向后兼容锁）；
- AN6：工件卫生为运行时动作（tmp_trace 经 make clean-traces 清理），
  无代码产物，不设测试。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

from pathlib import Path

from experiments.statistical_analysis import (
    _cost_report_lines,
    _mutation_report_lines,
    cost_per_detection,
    mutation_reliability_summary,
)

_ROOT = Path(__file__).resolve().parents[1]

_PRICES = {
    "models": {
        "m1": {
            "input_per_mtok": 1.0,
            "output_per_mtok": 2.0,
            "currency": "USD",
            "source": "test",
            "as_of": "2026-10-07",
        }
    }
}


def _make_row(input_tokens: int, output_tokens: int, model: str | None = "m1") -> dict:
    """构造最小 token_usage 结果行（与 AE 批 _make_row 同构）。"""
    total = input_tokens + output_tokens
    tu: dict = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total}
    if model is not None:
        tu["by_model"] = {model: total}
    return {"task_id": "t", "token_usage": tu}


# ─── AN5：$/detection 推导 ───────────────────────────────────────────────────


class TestCostPerDetection:
    """cost_per_detection：除零 / 缺数诚实降级 None。"""

    def test_normal_math(self) -> None:
        """$/detection = $/task ÷ (检出率/100)：2.0 ÷ 50% = 4.0。"""
        assert cost_per_detection(2.0, 50.0) == 4.0

    def test_low_rate_scales_up(self) -> None:
        """低检出率放大单位成本：0.5 ÷ 2% = 25.0。"""
        assert cost_per_detection(0.5, 2.0) == 25.0

    def test_zero_detection_returns_none(self) -> None:
        """检出率 0% 语义上是 ∞——不得显示为有限数字。"""
        assert cost_per_detection(2.0, 0.0) is None

    def test_none_inputs_return_none(self) -> None:
        """未计价 / 无可测行 → None（诚实降级为 —）。"""
        assert cost_per_detection(None, 50.0) is None
        assert cost_per_detection(2.0, None) is None

    def test_negative_rate_defensive(self) -> None:
        """负检出率为非法口径（防御性返回 None，不抛异常）。"""
        assert cost_per_detection(2.0, -1.0) is None


class TestCostReportAn5Column:
    """_cost_report_lines：AN5 可选"成本/检出"列 + 向后兼容锁。"""

    def test_extended_table_with_column(self) -> None:
        """提供 det_rates → 表头含"成本/检出"列，数值正确。"""
        rows = [
            {
                "baseline": "a",
                "n_tasks": 1,
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "by_model": {"m1": 2_000_000},
                "missing_models": [],
                "unattributed_tokens": 0,
                "cost": 3.0,
                "cost_per_task": 3.0,
                "currency": "USD",
                "priced": True,
            }
        ]
        text = "\n".join(_cost_report_lines(rows, _PRICES, det_rates={"a": 50.0}))
        assert "成本/检出" in text
        assert "| a | 1 | 1000000 | 1000000 | 3.0000 | 6.0000 | USD |" in text
        assert "AN5" in text  # 口径说明含批次标记

    def test_zero_detection_shows_dash(self) -> None:
        """检出率 0% 的基线该列为 —（∞ 语义）。"""
        rows = [
            {
                "baseline": "b",
                "n_tasks": 2,
                "input_tokens": 2_000_000,
                "output_tokens": 0,
                "by_model": {"m1": 2_000_000},
                "missing_models": [],
                "unattributed_tokens": 0,
                "cost": 2.0,
                "cost_per_task": 1.0,
                "currency": "USD",
                "priced": True,
            }
        ]
        text = "\n".join(_cost_report_lines(rows, _PRICES, det_rates={"b": 0.0}))
        assert "| b | 2 | 2000000 | 0 | 1.0000 | — | USD |" in text

    def test_legacy_format_unchanged_when_det_rates_none(self) -> None:
        """det_rates=None（缺省）→ 与 AE2 历史格式逐位一致（向后兼容锁）。"""
        from experiments.statistical_analysis import cost_analysis

        results = {"a": [_make_row(1_000_000, 1_000_000, "m1")]}
        text = "\n".join(_cost_report_lines(cost_analysis(results, _PRICES), _PRICES))
        assert "| a | 1 | 1000000 | 1000000 | 3.0000 | USD |" in text
        assert "成本/检出" not in text  # 历史口径不出现新列


# ─── AN2：测试套件可靠性聚合 ─────────────────────────────────────────────────


class TestMutationReliabilitySummary:
    """mutation_reliability_summary：可测行均值 + None 不进分母。"""

    def test_aggregation_math(self) -> None:
        """均值只取非 None 行；杀灭/变异体全行合计。"""
        data = {
            "a": [
                {"mutation_detection_rate": 0.5, "mutants_killed": 3, "mutants_total": 4},
                {"mutation_detection_rate": 1.0, "mutants_killed": 2, "mutants_total": 2},
                {"mutation_detection_rate": None, "mutants_killed": 0, "mutants_total": 0},
            ]
        }
        s = mutation_reliability_summary(data)["a"]
        assert s["n_total"] == 3
        assert s["n_measurable"] == 2
        assert s["mean_pct"] == 75.0  # (0.5 + 1.0) / 2 * 100
        assert s["mutants_killed"] == 5
        assert s["mutants_total"] == 6

    def test_all_unmeasurable_honest(self) -> None:
        """全不可测 → mean_pct=None；报告行含诚实披露而非 0。"""
        data = {"a": [{"mutation_detection_rate": None, "mutants_killed": 0, "mutants_total": 0}]}
        s = mutation_reliability_summary(data)["a"]
        assert s["mean_pct"] is None
        lines = _mutation_report_lines(mutation_reliability_summary(data))
        assert "不可测" in "\n".join(lines)

    def test_report_lines_presentational_marker(self) -> None:
        """报告章节含 AN2 标记 + 呈现性增补声明 + 主终点不变声明。"""
        lines = _mutation_report_lines(mutation_reliability_summary({"a": []}))
        text = "\n".join(lines)
        assert "AN2" in text
        assert "呈现性增补" in text
        assert "主终点" in text

    def test_missing_row_keys_tolerated(self) -> None:
        """行缺字段（历史批次 schema）按 0/None 容错，不抛异常。"""
        s = mutation_reliability_summary({"a": [{"task_id": "t"}]})["a"]
        assert s["n_total"] == 1
        assert s["n_measurable"] == 0
        assert s["mean_pct"] is None


# ─── AN1：TestGenEval L2 候补登记锁定 ────────────────────────────────────────


class TestN1TestGenEvalRegistration:
    """许可结论（CC BY-NC 4.0，spdx_id=NOASSERTION）改动必须显式改本测试。"""

    def test_design_doc_registration(self) -> None:
        """real_benchmark_upgrade.md：TestGenEval 候补块 + 许可结论 + 溯源字段。"""
        text = (_ROOT / "docs" / "design" / "real_benchmark_upgrade.md").read_text(encoding="utf-8")
        assert "TestGenEval" in text
        assert "facebookresearch/testgeneval" in text
        assert "2410.00752" in text
        assert "CC BY-NC 4.0" in text
        assert "spdx_id=NOASSERTION" in text
        assert "2026-10-07" in text  # LICENSE 原文核实日期

    def test_data_card_bilingual_registration(self) -> None:
        """DATA_CARD 双语均登记 TestGenEval 许可结论；QuixBugs MIT 登记不受影响。"""
        for name in ("DATA_CARD.md", "DATA_CARD.en.md"):
            text = (_ROOT / "docs" / name).read_text(encoding="utf-8")
            assert "TestGenEval" in text, name
            assert "CC BY-NC 4.0" in text, name
            assert "NOASSERTION" in text, name
            assert "2026-10-07" in text, name
            # AH1 既有登记不被本批稀释
            assert "spdx_id=MIT" in text, name

    def test_bilingual_dates_synced(self) -> None:
        """DATA_CARD 中英文"最后更新"日期一致（check_bilingual_docs fail 项）。"""
        import re

        date_re = re.compile(r"(最后更新|Last updated)[:：]?\s*(\d{4}-\d{2}-\d{2})")
        zh = date_re.search((_ROOT / "docs" / "DATA_CARD.md").read_text(encoding="utf-8"))
        en = date_re.search((_ROOT / "docs" / "DATA_CARD.en.md").read_text(encoding="utf-8"))
        # R2（2026-10-08）R20 叙事对齐：DATA_CARD §1/§4 更新（QuixBugs 定位降格
        # 声明 + 状态列），"最后更新"随批升级；锁语义不变（zh == en 同步）。
        assert zh and en and zh.group(2) == en.group(2) == "2026-10-08"


# ─── AN2/AN5：预注册呈现性增补声明锁定 ───────────────────────────────────────


class TestPreregPresentationNote:
    """预注册 E3 节的呈现性增补声明（效力：主终点/阈值/停止规则不变）。"""

    def test_bilingual_note_exists(self) -> None:
        zh = (_ROOT / "docs" / "preregistration.md").read_text(encoding="utf-8")
        en = (_ROOT / "docs" / "preregistration.en.md").read_text(encoding="utf-8")
        assert "AN2/AN5" in zh and "呈现性增补" in zh
        assert "AN2/AN5" in en and "presentation-only" in en
        assert "主终点、判定阈值与停止规则不变" in zh
        assert "primary" in en and "unchanged" in en

    def test_report_assembly_wired(self) -> None:
        """报告组装包含新章节标题（静态守卫：防后续重构静默丢节）。"""
        src = (_ROOT / "experiments" / "statistical_analysis.py").read_text(encoding="utf-8")
        assert "测试套件可靠性（mutation_detection_rate 按臂聚合——AN2 呈现性增补）" in src
        assert "成本/检出" in src


# ─── AN4：属性模板路线骨架锁定 ────────────────────────────────────────────────


class TestN4PropertyRouteSkeleton:
    """E1 失败出口占位：存在、未激活、触发条件与红线字面绑定。"""

    def _text(self) -> str:
        return (_ROOT / "docs" / "design" / "property_template_route_skeleton.md").read_text(encoding="utf-8")

    def test_exists_and_inactive(self) -> None:
        """骨架存在且显式标注未激活（激活前零实验承诺）。"""
        text = self._text()
        assert "占位骨架，未激活" in text
        assert "激活前不得执行任何" in text

    def test_trigger_bound_to_e1(self) -> None:
        """触发条件字面绑定 prereg E1 判定（<0.2 / 灰区 <0.3）。"""
        text = self._text()
        assert "0.2" in text and "0.3" in text
        assert "spec_compile_rate" in text

    def test_narrative_redline(self) -> None:
        """红线锁定：路线激活即放弃逻辑驱动主张，不得复活规约驱动表述。"""
        text = self._text()
        assert "不得" in text and "复活" in text

    def test_draft_thresholds_concrete(self) -> None:
        """草案默认阈值具体化（编译率 0.5/0.3 双 gate + 检出 +5pp）——无占位符。"""
        text = self._text()
        assert "≥ 0.5" in text
        assert "< 0.3" in text
        assert "+5pp" in text

    def test_hypothesis_dependency_referenced(self) -> None:
        """骨架引用既有 hypothesis 资产（G18/T5），不得凭空造依赖。"""
        assert "hypothesis" in self._text()
