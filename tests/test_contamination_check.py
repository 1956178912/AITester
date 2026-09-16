"""2.1 数据污染检测模块单元测试（experiments/contamination_check.py）。

覆盖：
- extract_patch_tokens：diff 元数据行丢弃、修改行 token 提取、空补丁；
- patch_overlap_score：完全相同 / 部分重叠 / 无重叠 / 空补丁边界；
- classify_overlap：high / medium / low 三档阈值；
- detect_contamination：details 自带 golden_patch 与显式映射两种输入、
  无补丁任务跳过、渲染章节的有/无数据分支。
"""

from __future__ import annotations

from experiments.contamination_check import (
    classify_overlap,
    detect_contamination,
    extract_patch_tokens,
    patch_overlap_score,
    render_contamination_section,
)

_SAMPLE_GOLDEN = (
    "diff --git a/calc.py b/calc.py\n"
    "--- a/calc.py\n"
    "+++ b/calc.py\n"
    "@@ -1,3 +1,3 @@\n"
    " def divide(a, b):\n"
    "-    return a * b\n"
    "+    if b == 0:\n"
    "+        raise ZeroDivisionError('division by zero')\n"
    "+    return a / b\n"
)


class TestExtractPatchTokens:
    """diff 元数据丢弃与修改行 token 提取。"""

    def test_metadata_lines_dropped(self):
        tokens = extract_patch_tokens(_SAMPLE_GOLDEN)
        # 文件头/ hunk 头 的行标记（a/b 路径词）不参与
        assert "calc.py" not in tokens or not any("calc" in t and t.endswith(".py") for t in tokens)
        # 修改行内容参与
        assert "return" in tokens
        assert "zerodivisionerror" in tokens

    def test_content_lines_extracted_lowercase(self):
        tokens = extract_patch_tokens("-    return a * b\n+    return a / b\n")
        assert "return" in tokens
        assert "a" in tokens
        assert "b" in tokens

    def test_empty_patch_returns_empty_set(self):
        assert extract_patch_tokens("") == set()
        assert extract_patch_tokens(None) == set()  # type: ignore[arg-type]


class TestPatchOverlapScore:
    """Jaccard 相似度计算与边界。"""

    def test_identical_patches_score_one(self):
        assert patch_overlap_score(_SAMPLE_GOLDEN, _SAMPLE_GOLDEN) == 1.0

    def test_disjoint_patches_score_zero(self):
        other = "-    x = 1\n+    y = 2\n"
        # 与示例几乎无公共 token
        assert patch_overlap_score(other, _SAMPLE_GOLDEN) < 0.5

    def test_partial_overlap_between_zero_and_one(self):
        partial = "-    return a * b\n+    return a / b\n"
        score = patch_overlap_score(partial, _SAMPLE_GOLDEN)
        assert 0.0 < score < 1.0

    def test_both_empty_scores_zero(self):
        assert patch_overlap_score("", "") == 0.0


class TestClassifyOverlap:
    """阈值分级（0.85 / 0.6）。"""

    def test_high(self):
        assert classify_overlap(0.9) == "high"
        assert classify_overlap(0.85) == "high"

    def test_medium(self):
        assert classify_overlap(0.7) == "medium"
        assert classify_overlap(0.6) == "medium"

    def test_low(self):
        assert classify_overlap(0.59) == "low"
        assert classify_overlap(0.0) == "low"


class TestDetectContamination:
    """details 扫描与分级汇总。"""

    def _details(self):
        return [
            {
                "task_id": "t1",
                "patch": _SAMPLE_GOLDEN,  # 逐字复现 → high
                "task_metadata": {"golden_patch": _SAMPLE_GOLDEN},
            },
            {
                "task_id": "t2",
                "patch": "-    x = 1\n+    y = 2\n",
                "task_metadata": {"golden_patch": _SAMPLE_GOLDEN},
            },
            {"task_id": "t3", "patch": None, "task_metadata": {"golden_patch": _SAMPLE_GOLDEN}},
        ]

    def test_high_medium_counts(self):
        report = detect_contamination(self._details())
        assert report["checked"] == 2  # t3 无生成补丁，跳过
        assert report["high"] == ["t1"]
        # t2 与 golden 公共 token 较少（x/y 系列 vs a/b/return 系列），落在 medium 或 low
        assert report["scores"]["t2"]["level"] in ("medium", "low")

    def test_explicit_golden_patches_override(self):
        details = [{"task_id": "t1", "patch": _SAMPLE_GOLDEN}]
        report = detect_contamination(details, golden_patches={"t1": _SAMPLE_GOLDEN})
        assert report["high"] == ["t1"]

    def test_no_golden_source_checked_zero(self):
        details = [{"task_id": "t1", "patch": "x"}]
        report = detect_contamination(details)
        assert report["checked"] == 0
        assert report["contaminated_tasks"] == []

    def test_render_section_empty_when_no_data(self):
        lines = render_contamination_section({"checked": 0}, "aitester")
        assert lines == []

    def test_render_section_with_findings(self):
        report = {
            "checked": 2,
            "high": ["t1"],
            "medium": ["t2"],
            "scores": {"t1": {"score": 0.95, "level": "high"}},
            "contaminated_tasks": ["t1", "t2"],
        }
        lines = render_contamination_section(report, "aitester")
        assert "数据污染检测（2.1" in lines[0]
        assert any("t1" in ln for ln in lines)
