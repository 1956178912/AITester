"""AL 批次（2026-10-06 第十三轮审查落地）测试。

锁定四组行为：
- AL1 红线勘误：预注册双语的 AK 补注行以禁止语境提及 --allow-dirty
  （与 AJ 行级守卫同口径逐行复检），勘误事实不丢失；
- AL5 定位收口：README(.en) / MODEL_CARD(.en) 标题与导语不再含
  "自修复系统/框架"主张，诚实披露行指向 repair_ceiling_report.md，
  并与 CITATION.cff 的 detection-first 口径一致；
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
    """对外门面与 repair=0 证据一致：标题去"自修复"主张 + 诚实披露行。"""

    def test_readme_title_zh(self) -> None:
        title = _first_heading(README_ZH)
        assert "自修复" not in title
        assert "检出优先" in title and "修复评估" in title

    def test_readme_title_en(self) -> None:
        title = _first_heading(README_EN)
        assert "Self-Repair" not in title and "self-repair" not in title
        assert "Detection-First" in title

    def test_readme_honest_disclosure(self) -> None:
        zh_head = _head(README_ZH, 18)
        en_head = _head(README_EN, 22)
        assert "诚实披露" in zh_head and "repair_ceiling_report.md" in zh_head
        assert "Honest disclosure" in en_head and "repair_ceiling_report.md" in en_head
        assert "repair = 0.0%" in zh_head and "repair = 0.0%" in en_head

    def test_model_card_overview(self) -> None:
        zh_head = _head(MODEL_CARD_ZH, 16)
        en_head = _head(MODEL_CARD_EN, 18)
        assert "自修复研究系统" not in zh_head
        assert "修复评估研究系统" in zh_head and "检出优先" in zh_head
        assert "self-repair research" not in en_head
        assert "repair-evaluation" in en_head

    def test_citation_alignment(self) -> None:
        title_line = next(line for line in _read(CITATION).splitlines() if line.startswith("title:"))
        assert "Detection-first" in title_line
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
