"""AL 批次（2026-10-06 第十三轮审查落地）测试。

锁定四组行为：
- AL1 红线勘误：预注册双语的 AK 补注行以禁止语境提及 --allow-dirty
  （与 AJ 行级守卫同口径逐行复检），勘误事实不丢失；
- AL5 定位收口：README(.en) / MODEL_CARD(.en) 定位区不含"自修复系统/框架"
  主张；诚实披露小节携带修正口径与伪影定性，并与 CITATION.cff 的
  detection-first 口径一致（DD 轮改为结构判据）；
- E6/E7 预注册节（AL7/AL10）：双语存在性与关键口径（预算匹配定义 /
  执行前置旗标 / 分层键 / 判定规则 / 增补先于数据产生的时序声明）；
- E7 抽样纯函数：抽样框过滤、分层 ceil 配额、同 seed 确定性、
  fraction 边界与候选清单渲染结构。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from experiments.repair_sample_selection import (
    build_sampling_frame,
    render_markdown,
    select_stratified_sample,
    stratify,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREREG_ZH = PROJECT_ROOT / "docs" / "preregistration.md"
PREREG_EN = PROJECT_ROOT / "docs" / "preregistration.en.md"
README_ZH = PROJECT_ROOT / "README.md"
README_EN = PROJECT_ROOT / "README.en.md"
MODEL_CARD_ZH = PROJECT_ROOT / "MODEL_CARD.md"
MODEL_CARD_EN = PROJECT_ROOT / "MODEL_CARD.en.md"
CITATION = PROJECT_ROOT / "CITATION.cff"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _head(path: Path, n: int) -> str:
    return "\n".join(_read(path).splitlines()[:n])


def _first_heading(path: Path) -> str:
    for line in _read(path).splitlines():
        if line.startswith("# "):
            return line
    raise AssertionError(f"{path} 缺一级标题")


def _preamble(path: Path) -> str:
    """首个二级标题之前的定位区（门面的「名片」部分）。"""
    lines: list[str] = []
    for line in _read(path).splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines)


def _h2_section(path: Path, heading: str) -> str:
    """取某个二级标题下的正文（到下一个二级标题为止）；标题缺失即红。"""
    lines = _read(path).splitlines()
    for index, line in enumerate(lines):
        if line.strip() == heading:
            body: list[str] = []
            for follow in lines[index + 1 :]:
                if follow.startswith("## "):
                    break
                body.append(follow)
            return "\n".join(body)
    raise AssertionError(f"{path} 缺二级标题 {heading!r}")


class TestAL1ErratumContext:
    """AJ 红线守卫同口径复检（zh/en 逐行）+ 勘误事实保全。"""

    _MARKERS = ("不得", "never", "do not", "Do not", "violate", "red line")

    def test_allow_dirty_lines_all_forbidding(self) -> None:
        for path in (PREREG_ZH, PREREG_EN):
            for lineno, line in enumerate(_read(path).splitlines(), 1):
                if "--allow-dirty" in line:
                    assert any(m in line for m in self._MARKERS), (path.name, lineno)

    def test_erratum_facts_preserved(self) -> None:
        zh = _read(PREREG_ZH)
        en = _read(PREREG_EN)
        assert "AK 勘误补注" in zh and "AL1" in zh
        assert "AK erratum" in en and "AL1" in en


class TestAL5Positioning:
    """对外门面与 repair=0 证据一致（DD 轮：结构判据取代行窗口）。

    旧锁用 16/18、60/70 行窗口钉「披露留在头部」，两次因叙事增补被迫扩容。
    DD 轮把判据改成结构：定位事实在首个 H2 前的定位区，披露事实在
    `## 它不是什么（诚实披露）` / `## What It Is Not (Honest Disclosure)` 小节内。
    结构锁不随篇幅漂移，也不会把「披露被下沉到中后段」误判为通过。
    """

    def test_readme_positioning_zh(self) -> None:
        preamble = _preamble(README_ZH)
        assert "检出优先" in preamble and "修复评估" in preamble
        assert "自修复" not in preamble

    def test_readme_positioning_en(self) -> None:
        lowered = _preamble(README_EN).lower()
        assert "detection-first" in lowered and "repair-evaluation" in lowered
        assert "self-repair" not in lowered

    def test_readme_honest_disclosure_zh(self) -> None:
        section = _h2_section(README_ZH, "## 它不是什么（诚实披露）")
        assert "39.31%" in section
        assert "伪影" in section
        assert "repair_caliber_matrix.md" in section
        assert "preregistration.md" in section

    def test_readme_honest_disclosure_en(self) -> None:
        section = _h2_section(README_EN, "## What It Is Not (Honest Disclosure)")
        assert "39.31%" in section
        assert "artifact" in section
        assert "repair_caliber_matrix.md" in section
        assert "preregistration.md" in section

    def test_model_card_positioning(self) -> None:
        zh = _preamble(MODEL_CARD_ZH)
        en = _preamble(MODEL_CARD_EN).lower()
        assert "修复评估研究系统" in zh and "检出优先" in zh
        assert "自修复研究系统" not in zh
        assert "repair-evaluation" in en and "detection-first" in en
        assert "self-repair research" not in en

    def test_citation_alignment(self) -> None:
        title_line = next(line for line in _read(CITATION).splitlines() if line.startswith("title:"))
        # 锁语义=检出优先定位在场、自修复主张不在场；标题大小写不构成语义差异。
        assert "detection-first" in title_line.lower()
        assert "Self-Repair" not in title_line


class TestPreregE6E7:
    """E6（预算匹配四臂）/ E7（修复上限分层抽样）预注册节锁定。"""

    def test_e6_section_zh(self) -> None:
        text = _read(PREREG_ZH)
        assert "## E6：预算匹配四臂" in text
        assert "--per-task-token-cap" in text
        assert "26,115" in text and "4,223" in text
        assert "无迭代条款" in text

    def test_e7_section_zh(self) -> None:
        text = _read(PREREG_ZH)
        assert "## E7：修复上限分层抽样" in text
        assert "patch_evidence_level" in text
        assert "equivalent" in text and "10%" in text
        assert "repair_sample_selection.py" in text

    def test_e6_e7_sections_en(self) -> None:
        text = _read(PREREG_EN)
        assert "## E6: Budget-Matched Four Arms" in text
        assert "## E7: Repair-Ceiling Stratified Sampling" in text
        assert "--per-task-token-cap" in text

    def test_scope_amendment_precedes_data(self) -> None:
        zh = _read(PREREG_ZH)
        en = _read(PREREG_EN)
        assert "E6（预算匹配四臂）/ E7（修复上限分层抽样）" in zh
        assert "早于任何 E6/E7 数据" in zh
        assert "the amendment precedes any" in en


def _row(task_id: str, status: str | None, plausible: int, evidence: str | None, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "task_id": task_id,
        "detection_first_status": status,
        "patch_plausible": plausible,
        "patch_evidence_level": evidence,
    }
    row.update(extra)
    return row


class TestSampleFrame:
    """E7 抽样框：修复循环进入 ∧ patch_plausible==1。"""

    def test_frame_filters(self) -> None:
        rows = [
            _row("t1", "red_not_repaired", 1, "sbfl"),
            _row("t2", "red_then_green", 1, "none"),
            _row("t3", "all_green_unverified", 1, "sbfl"),
            _row("t4", "red_not_repaired", 0, "sbfl"),
            _row("t5", None, 1, "none"),
        ]
        frame = build_sampling_frame(rows)
        assert [r["task_id"] for r in frame] == ["t1", "t2"]

    def test_frame_empty(self) -> None:
        assert build_sampling_frame([]) == []


class TestStratifiedSelection:
    """分层 ceil 配额 + seed 确定性 + fraction 边界。"""

    @staticmethod
    def _strata() -> dict[str, list[dict[str, object]]]:
        rows: list[dict[str, object]] = []
        rows += [_row(f"n{i:02d}", "red_not_repaired", 1, "none") for i in range(10)]
        rows += [_row(f"s{i:02d}", "red_then_green", 1, "sbfl") for i in range(7)]
        rows += [_row(f"k{i:02d}", "red_not_repaired", 1, "keyword") for i in range(3)]
        return stratify(rows)

    def test_strata_sizes(self) -> None:
        counts = {name: len(members) for name, members in self._strata().items()}
        assert counts == {"none": 10, "sbfl": 7, "keyword": 3}

    def test_quota_ceil_per_stratum(self) -> None:
        selected = select_stratified_sample(self._strata(), 0.10, 42)
        counts = Counter(str(r["_stratum"]) for r in selected)
        assert counts == {"keyword": 1, "none": 1, "sbfl": 1}

    def test_quota_half_ceil(self) -> None:
        selected = select_stratified_sample(self._strata(), 0.5, 42)
        counts = Counter(str(r["_stratum"]) for r in selected)
        assert counts == {"none": 5, "sbfl": 4, "keyword": 2}

    def test_deterministic_same_seed(self) -> None:
        first = select_stratified_sample(self._strata(), 0.3, 42)
        second = select_stratified_sample(self._strata(), 0.3, 42)
        assert [r["task_id"] for r in first] == [r["task_id"] for r in second]

    def test_full_fraction_takes_all(self) -> None:
        selected = select_stratified_sample(self._strata(), 1.0, 42)
        assert len(selected) == 20

    def test_zero_fraction_selects_none(self) -> None:
        assert select_stratified_sample(self._strata(), 0.0, 42) == []

    def test_invalid_fraction_rejected(self) -> None:
        with pytest.raises(ValueError):
            select_stratified_sample(self._strata(), 1.5, 42)

    def test_empty_strata_ok(self) -> None:
        assert select_stratified_sample({}, 0.1, 42) == []

    def test_three_paths_nested_on_archived_frame(self) -> None:
        pytest.skip(
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
        """E7 三路径（10% / 56% / 100%）在归档抽样框上逐级嵌套且同序。

        这条性质支撑"路径 A 的裁决成果升级到 B 或全框普查时零返工"。

        **它不是 `random.sample()` 的算法保证**：同 seed 不同 k 的样本并不保证
        嵌套——在 150 组合成参数上实测 13% 集合不嵌套、33% 顺序不一致。它在
        本项目 (72 行 / seed=42 / 单层 sbfl) 下成立，属于当前备料的**有效性
        事实**。若改抽样实现或抽样框导致本测试转红，正确解读是"备料失效、
        须重新生成"，而不是"测试过时"。
        """
        from experiments.repair_sample_selection import _DEFAULT_BATCHES
        from experiments.statistical_analysis import load_experiment_results_with_sources

        results, _sources = load_experiment_results_with_sources(
            "experiments/results/main_batch",
            list(_DEFAULT_BATCHES),
            allow_schema_mixed=False,
            pool_seeds=True,
        )
        strata = stratify(build_sampling_frame(results.get("aitester") or []))

        def ids(fraction: float) -> list[str]:
            return [str(r["task_id"]) for r in select_stratified_sample(strata, fraction, 42)]

        n8, n41, n72 = ids(0.10), ids(0.56), ids(1.0)
        assert (len(n8), len(n41), len(n72)) == (8, 41, 72), "三路径样本量与备料不符"
        assert len(set(n72)) == 72, "全框普查不得出现重复行"
        assert set(n8) <= set(n41) <= set(n72), "集合嵌套破裂：升级路径会遗漏已裁决行"
        assert n72[: len(n8)] == n8, "顺序不一致：已裁决行在升级后的位置会变"


class TestRenderManifest:
    """候选清单渲染：参数披露 + 判定口径 + 待复核列。"""

    def test_manifest_structure(self) -> None:
        strata = TestStratifiedSelection._strata()
        selected = select_stratified_sample(strata, 1.0, 7)
        manifest = render_markdown(selected, {k: len(v) for k, v in strata.items()}, ["a.json"], 1.0, 7)
        assert manifest.startswith("# E7")
        assert "seed=7" in manifest and "fraction=100%" in manifest
        assert "人工判定" in manifest and "待复核" in manifest
        assert "equivalent" in manifest
