"""DD 轮（2026-10-26）：docs 顶层文档必须在 INDEX 中可达。

判据：docs/*.md（非 .en.md、非 INDEX.md）每份都能在 docs/INDEX.md 里以
`](<文件名>` 链到；英文孪生同理在 docs/INDEX.en.md。
只查 docs 顶层：子目录（adr/design/emse/reviews/security）由 INDEX 的目录
链接统一进入，不做逐文件展开。
"""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_zh_docs_are_indexed() -> None:
    index = (DOCS / "INDEX.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in sorted(DOCS.glob("*.md"))
        if not path.name.endswith(".en.md") and path.name != "INDEX.md" and f"]({path.name}" not in index
    ]
    assert missing == []


def test_en_docs_are_indexed() -> None:
    index = (DOCS / "INDEX.en.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in sorted(DOCS.glob("*.en.md"))
        if path.name != "INDEX.en.md" and f"]({path.name}" not in index
    ]
    assert missing == []
