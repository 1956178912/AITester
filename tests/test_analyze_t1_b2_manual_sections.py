"""X 轮（2026-10-19）：T1（B2）README 手工节保留机制的回归锁。

背景（复算实证的隐患）：`analyze_t1_b2_main_batch.py --write` 从零重生成
README.md，而归档版含手工追加的"0.6 T 轮发现（可辩护表述，写死防事后改写）"
节——重跑即静默丢失 32 行手写解读（本轮复算在 /tmp 副本上实测）。修法：
手工节用 `<!-- MANUAL:BEGIN/END -->` 标记包裹，`_preserve_manual_sections`
在 --write 时把成对闭合的标记块原样保留到生成内容末尾。

本文件锁定四件事（全部 hermetic：直接用归档 ANALYSIS_REPORT.json 渲染，
不重跑批次分析、不依赖 git）：
1. 归档 README 经"渲染 + 保留"后，手工节完整存活（含关键表述句）；
2. 无标记的既有文件不被追加任何内容（防误伤普通工件 README）；
3. 未闭合的 MANUAL:BEGIN 不保留（防截断内容被当作完整块）；
4. 多标记块按原相对顺序全部保留。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARTIFACT_DIR = _REPO_ROOT / "experiments/results/t_round_b2_main_batch_20261018"
_SCRIPT = _REPO_ROOT / "experiments/analyze_t1_b2_main_batch.py"


def _load_analyzer():
    spec = importlib.util.spec_from_file_location("_t1b2_under_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_t1b2_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_archived_readme_manual_section_survives_regeneration() -> None:
    """归档 README 手工节在"渲染 + 保留"后完整存活（核心契约）。"""
    mod = _load_analyzer()
    report = json.loads((_ARTIFACT_DIR / "ANALYSIS_REPORT.json").read_text(encoding="utf-8"))
    generated = mod.render_readme(report)
    merged = mod._preserve_manual_sections(generated, _ARTIFACT_DIR / "README.md")
    # 手工节的关键表述逐句存活
    for phrase in [
        "0.6 T 轮发现",
        "可辩护表述，写死防事后改写",
        "not_reproduced",
        "−25.29pp",
        "thinking",
        "plain_llm",
        "11.88%",
    ]:
        assert phrase in merged, f"手工节表述丢失：{phrase}"
    # 生成内容本身仍在（保留不是替换）
    assert "预注册判定" in merged
    assert "MANUAL:BEGIN" in merged and "MANUAL:END" in merged


def test_no_manual_markers_means_no_append() -> None:
    """无标记的既有文件：原样返回，不追加任何内容。"""
    mod = _load_analyzer()
    generated = "# generated\n\nsome content\n"
    plain = tmp_with("# plain readme\n\nno markers here\n")
    assert mod._preserve_manual_sections(generated, plain) == generated


def test_unclosed_marker_not_preserved(tmp_path: Path) -> None:
    """未闭合的 MANUAL:BEGIN 不保留（截断内容不得冒充完整块）。"""
    mod = _load_analyzer()
    broken = tmp_path / "README.md"
    broken.write_text("x\n<!-- MANUAL:BEGIN -->\n## half a section\nno end marker\n", encoding="utf-8")
    generated = "# generated\n"
    assert mod._preserve_manual_sections(generated, broken) == generated


def test_missing_existing_file_returns_generated(tmp_path: Path) -> None:
    """首次生成（既有 README 不存在）时原样返回。"""
    mod = _load_analyzer()
    generated = "# generated\n"
    assert mod._preserve_manual_sections(generated, tmp_path / "nope.md") == generated


def test_multiple_blocks_preserved_in_order(tmp_path: Path) -> None:
    """多个标记块按原相对顺序全部保留。"""
    mod = _load_analyzer()
    existing = tmp_path / "README.md"
    existing.write_text(
        "head\n"
        "<!-- MANUAL:BEGIN -->\n## first block\nAAA\n<!-- MANUAL:END -->\n"
        "middle\n"
        "<!-- MANUAL:BEGIN -->\n## second block\nBBB\n<!-- MANUAL:END -->\n"
        "tail\n",
        encoding="utf-8",
    )
    merged = mod._preserve_manual_sections("# generated\n", existing)
    assert "## first block\nAAA" in merged and "## second block\nBBB" in merged
    assert merged.index("first block") < merged.index("second block")


def tmp_with(content: str) -> Path:
    """写一个临时无标记 README 并返回路径（辅助）。"""
    import tempfile

    fd, name = tempfile.mkstemp(suffix=".md")
    with open(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    return Path(name)
