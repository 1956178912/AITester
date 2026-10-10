"""AK 批次（2026-10-06 第十二轮审查落地）测试。

锁定四组行为：
- AK2 价目表：已登记模型可核验（数值/币种/官方源 URL/生效日期格式），
  无官方源模型维持 null（诚实条款——价格不编造）；
- AK3/AK4 守卫接线：ci.yml / Makefile 含三个新门禁步骤；
  入库守卫 MANIFEST 覆盖的工件存在于工作区；
- AK1 修复上限归因：repair_ceiling_report.md 落盘且含漏斗/双界章节，
  pooled 报告含 AK 勘误节且不再含已被更正的 git_dirty=False 表述；
- build_funnel / sensitivity_bounds 的结构不变式（hypothesis 属性）：
  漏斗层单调不增、桶计数守恒；双界 best ≥ worst 恒成立。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from experiments.repair_ceiling_analysis import build_funnel, sensitivity_bounds

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRICE_TABLE = PROJECT_ROOT / "experiments" / "price_table.json"
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"
MAIN_BATCH = PROJECT_ROOT / "experiments" / "results" / "main_batch"
POOLED_REPORT = MAIN_BATCH / "statistical_report_3seed_pooled.md"
CEILING_REPORT = MAIN_BATCH / "repair_ceiling_report.md"


def _load_price_table() -> dict:
    return json.loads(PRICE_TABLE.read_text(encoding="utf-8"))


def _artifacts_manifest() -> tuple[str, ...]:
    """加载入库守卫的 MANIFEST 常量（importlib，零子进程）。"""
    spec = importlib.util.spec_from_file_location(
        "check_artifacts_tracked", PROJECT_ROOT / "scripts" / "gates" / "check_artifacts_tracked.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.MANIFEST)


class TestAK2PriceTable:
    def test_official_entries_verifiable(self):
        """已登记模型：数值非负、币种合法、source 为官方页、as_of 日期格式。"""
        models = _load_price_table()["models"]
        registered = {name for name, entry in models.items() if entry["input_per_mtok"] is not None}
        assert registered == {"deepseek-flash", "qwen-long"}
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for name in registered:
            entry = models[name]
            assert entry["input_per_mtok"] >= 0, name
            assert entry["output_per_mtok"] >= 0, name
            assert entry["currency"] in ("USD", "CNY"), name
            assert entry["source"].startswith("https://"), name
            assert date_re.match(entry["as_of"]), name

    def test_unverifiable_model_stays_null(self):
        """无公开官方价目页的模型（agnes-3.0-flash）维持 null——价格不编造。"""
        entry = _load_price_table()["models"]["agnes-3.0-flash"]
        assert entry["input_per_mtok"] is None
        assert entry["output_per_mtok"] is None

    def test_cost_analysis_priced_and_unpriced_paths(self):
        """价目齐全 → 按官方价折算；价目缺失 → priced=False 不编造。"""
        from experiments.statistical_analysis import cost_analysis

        rows = [
            {
                "token_usage": {
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "by_model": {"deepseek-flash": 2_000_000},
                }
            }
        ]
        priced = cost_analysis({"aitester": rows}, _load_price_table())[0]
        assert priced["priced"] is True
        assert priced["cost"] == pytest.approx(0.3 + 1.2)
        unpriced = cost_analysis({"aitester": rows}, {"models": {}})[0]
        assert unpriced["priced"] is False and unpriced["cost"] is None


class TestAK3AK4GuardWiring:
    def test_ci_wires_new_guards(self):
        ci = CI_YML.read_text(encoding="utf-8")
        for script in (
            "check_tool_versions.py",
            "check_state_contract.py",
            "check_artifacts_tracked.py",
        ):
            assert script in ci, f"ci.yml 缺 {script} 步骤"

    def test_makefile_gates_include_new_guards(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        gates_line = next(line for line in makefile.splitlines() if line.startswith("gates:"))
        assert "state-contract" in gates_line and "tool-versions" in gates_line

    def test_artifacts_manifest_covers_evidence_chain(self):
        """MANIFEST 覆盖"报告 → 证据工件"最小集且路径真实存在。"""
        entries = _artifacts_manifest()
        assert len(entries) >= 11
        for must in (
            "statistical_report_3seed_pooled.md",
            "repair_ceiling_report.md",
            "docs/preregistration.md",
        ):
            assert any(must in e for e in entries), must
        for rel in entries:
            assert (PROJECT_ROOT / rel).exists(), rel


class TestAK1Reports:
    def test_repair_ceiling_report_sections(self):
        text = CEILING_REPORT.read_text(encoding="utf-8")
        assert "# R-P0-2 修复上限归因分析（AK1" in text
        assert "## 1. 修复通道漏斗" in text
        assert "## 3. 21 行 detection=None 敏感性双界" in text
        assert "patch_correct=1（gold 裁决） | 0 " in text
        # 双界三情形成对出现（worst/best 均在）
        assert text.count("worst(None→0)") == 2 and text.count("best(None→1)") == 2

    def test_pooled_report_erratum_corrects_provenance(self):
        text = POOLED_REPORT.read_text(encoding="utf-8")
        assert "## AK 勘误与敏感性双界" in text
        # 被更正的错误表述不得以"实验口径"原始行形式残留（勘误节的引用式复述除外）
        assert "- 工作树：干净 @ b533cff" not in text
        assert "git_dirty: true" in text
        # 双界结论句（两定性结论均保持）
        assert "双界下两条定性结论均保持" in text


class TestAK1Invariants:
    def test_funnel_layers_monotone_on_real_rows(self):
        """漏斗层单调不增（correct ≤ plausible ≤ patch ≤ loop ≤ total）。"""
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, _ = load_experiment_results_with_sources(
            str(MAIN_BATCH),
            [
                "benchmark_synthetic_20261006_140906.json",
                "benchmark_synthetic_20261006_151907.json",
                "benchmark_synthetic_20261006_164357.json",
            ],
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        funnel = build_funnel(results["aitester"])
        assert funnel["patch_correct"] <= funnel["patch_plausible"] <= funnel["patch_produced"]
        assert funnel["repair_loop_entered"] <= funnel["total"]
        assert sum(funnel["by_status"].values()) == funnel["total"]


hypothesis = pytest.importorskip("hypothesis", reason="hypothesis 未安装（测试链依赖）")

from hypothesis import strategies as st  # noqa: E402


def _rows_from_flags(flags_a: list[int | None], flags_b: list[int]) -> dict[str, list[dict]]:
    """按 0/1/None 旗标构造两臂行集（task_id 对齐，供 mcnemar 配对）。"""
    rows_a = [{"task_id": f"t{i}", "detection_rate": v} for i, v in enumerate(flags_a)]
    rows_b = [{"task_id": f"t{i}", "detection_rate": v} for i, v in enumerate(flags_b)]
    return {"aitester": rows_a, "plain_llm": rows_b, "plain_llm_df": rows_b}


@st.composite
def _paired_flag_lists(draw: st.DrawFn) -> tuple[list[int | None], list[int]]:
    """等长两臂旗标（先抽共同长度，避免 assume 高过滤率触发健康检查）。"""
    n = draw(st.integers(min_value=2, max_value=25))
    flags_a = draw(st.lists(st.one_of(st.none(), st.integers(0, 1)), min_size=n, max_size=n))
    flags_b = draw(st.lists(st.integers(0, 1), min_size=n, max_size=n))
    return flags_a, flags_b


@st.composite
def _funnel_field_lists(
    draw: st.DrawFn,
) -> tuple[list[str | None], list[str | None], list[int], list[int]]:
    """漏斗四字段的等长列表（共同长度先抽）。"""
    n = draw(st.integers(min_value=0, max_value=25))
    statuses = draw(
        st.lists(
            st.sampled_from(["red_then_green", "red_not_repaired", "all_green_unverified", None]),
            min_size=n,
            max_size=n,
        )
    )
    patches = draw(st.lists(st.one_of(st.none(), st.just("x")), min_size=n, max_size=n))
    plausibles = draw(st.lists(st.integers(0, 1), min_size=n, max_size=n))
    corrects = draw(st.lists(st.integers(0, 1), min_size=n, max_size=n))
    return statuses, patches, plausibles, corrects


@hypothesis.given(flag_lists=_paired_flag_lists())
@hypothesis.settings(max_examples=50, deadline=None)
def test_sensitivity_bounds_ordering_property(
    flag_lists: tuple[list[int | None], list[int]],
) -> None:
    """属性：None 填充双界恒有序 worst ≤ base ≤ best（按阳性计数口径）。"""
    flags_a, flags_b = flag_lists
    bounds = sensitivity_bounds(_rows_from_flags(flags_a, flags_b))
    for entry in bounds:
        rows = {r["scenario"]: r for r in entry["rows"]}
        assert rows["worst(None→0)"]["sum_a"] <= rows["base"]["sum_a"] <= rows["best(None→1)"]["sum_a"]
        assert rows["worst(None→0)"]["risk_diff"] <= rows["best(None→1)"]["risk_diff"]


@hypothesis.given(fields=_funnel_field_lists())
@hypothesis.settings(max_examples=50, deadline=None)
def test_funnel_conservation_property(
    fields: tuple[list[str | None], list[str | None], list[int], list[int]],
) -> None:
    """属性（结构不变式）：桶计数守恒，且各漏斗层只统计修复循环行。

    注：层间单调（correct ≤ plausible ≤ produced）是**数据健全性**属性
    （依赖行级 correct ⊆ plausible 语义成立），非任意输入下的结构保证——
    该断言放在 TestAK1Invariants 的真实数据测试中。
    """
    statuses, patches, plausibles, corrects = fields
    rows = [
        {
            "detection_first_status": s,
            "patch": p,
            "patch_plausible": pl,
            "patch_correct": co,
        }
        for s, p, pl, co in zip(statuses, patches, plausibles, corrects, strict=True)
    ]
    funnel = build_funnel(rows)
    assert sum(funnel["by_status"].values()) == len(rows)
    assert funnel["repair_loop_entered"] <= len(rows)
    for layer in ("patch_produced", "patch_plausible", "patch_correct"):
        assert funnel[layer] <= funnel["repair_loop_entered"], layer
