"""ES 轮（2026-10-27）：双语门禁的「H2 骨架按序对齐」承诺与实现分裂。

历史实现把中英 H2 标题归一化后做**字面**比对：只有跨语言字面相同的标题才
参与顺序判定。翻译文档的标题天然不同——实测全仓 20 对配对中仅 CHANGELOG
存在 2 个跨语言相同标题，其余 19 对的结构化对照永远不会触发，"英文版缺
章节 / 章节顺序漂移"全部静默通过。

修复后改用语言无关的骨架指纹：H2 编号序列（"一、" / "1." 折算为整数）
逐位相等；H2 数相等时逐节比对 H3 小节数。两者都不读取标题文本。
"""

from __future__ import annotations

from typing import Any

import pytest

import scripts.gates.check_bilingual_docs as cbd


def _skeleton(text: str) -> list[tuple[int | None, int]]:
    return cbd._extract_h2_skeleton(text)


def test_ordinal_swap_detected_despite_translated_titles() -> None:
    """编号顺序互换（标题全译名）必须被检出——旧实现因标题不同而静默。"""
    zh = "## 一、概览\n## 二、安装\n## 三、用法\n"
    en = "## 1. Overview\n## 3. Usage\n## 2. Installation\n"
    drift = cbd._h2_structure_drift(_skeleton(zh), _skeleton(en))
    assert drift is not None
    assert "编号" in drift


def test_missing_numbered_chapter_detected_within_count_tolerance() -> None:
    """少一章但总数差 1（在 ±2 容差内）仍必须被检出。"""
    zh = "## 一、甲\n## 二、乙\n## 三、丙\n## 四、丁\n"
    en = "## 1. A\n## 2. B\n## 3. C\n"
    drift = cbd._h2_structure_drift(_skeleton(zh), _skeleton(en))
    assert drift is not None
    assert "编号" in drift


def test_translated_titles_with_matching_skeleton_pass() -> None:
    """标题全不同但骨架一致（编号 + H3 小节数）→ 不得误报。"""
    zh = "## 一、概览\n### 目标\n### 范围\n## 二、安装\n### 依赖\n"
    en = "## 1. Overview\n### Goals\n### Scope\n## 2. Install\n### Requirements\n"
    assert cbd._h2_structure_drift(_skeleton(zh), _skeleton(en)) is None


def test_subsection_skeleton_drift_detected() -> None:
    """无编号文档：同 H2 数下 H3 小节数向量不一致 → 检出骨架漂移。"""
    zh = "## 甲\n### 细节\n## 乙\n### 细节\n"
    en = "## A\n## B\n### Details\n"
    drift = cbd._h2_structure_drift(_skeleton(zh), _skeleton(en))
    assert drift is not None
    assert "H3" in drift


def test_unnumbered_count_tolerance_stays_silent() -> None:
    """无编号且 H2 数差 ≤2（文档化容差：英文可省略内部实现章节）→ 不报。"""
    zh = "## 甲\n## 乙\n## 丙\n"
    en = "## A\n## B\n"
    assert cbd._h2_structure_drift(_skeleton(zh), _skeleton(en)) is None


def test_gate_runs_structural_comparison_on_real_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """真语料上结构化对照必须真正执行到带编号的配对（分母可见）。

    旧实现在 19/20 对上等价于空转；本锁把"可比较的编号配对数量"变成
    断言——编号体系被静默移除、比对被绕过时立即转红。
    """
    real = cbd._h2_structure_drift
    comparable: list[tuple[Any, Any]] = []

    def recorder(zh: Any, en: Any) -> str | None:
        if any(o is not None for o, _ in zh) and any(o is not None for o, _ in en):
            comparable.append((zh, en))
        return real(zh, en)

    monkeypatch.setattr(cbd, "_h2_structure_drift", recorder)
    failures, warnings = cbd.check_bilingual(strict=True)
    assert failures == [], "\n".join(failures)
    assert warnings == [], "\n".join(warnings)
    # 实测当前 13 对带编号；门槛 10 防止编号体系被移除后检查退化为空转
    assert len(comparable) >= 10
