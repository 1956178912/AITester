"""DD 轮（2026-10-26）：旧门面叙事归档完整性。

重写把 README / CHANGELOG 的历史叙事归档到 docs/history/，旧文字零丢失。
锁三件事：归档存在且达到字节下限、归档头写明「历史快照」、新 CHANGELOG 链到
全部四份归档。字节下限取重写前实测值向下取整（README 241,293 / 245,545；
CHANGELOG 1,277,257 / 1,402,435）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ARCHIVES: tuple[tuple[str, int], ...] = (
    ("docs/history/README_2026-10-26_full.md", 200_000),
    ("docs/history/README_2026-10-26_full.en.md", 200_000),
    ("docs/history/CHANGELOG_2026-10-26_full.md", 1_000_000),
    ("docs/history/CHANGELOG_2026-10-26_full.en.md", 1_100_000),
)


@pytest.mark.parametrize(("rel", "floor"), ARCHIVES)
def test_archive_meets_byte_floor(rel: str, floor: int) -> None:
    path = PROJECT_ROOT / rel
    assert path.is_file(), f"{rel} 缺失"
    assert path.stat().st_size >= floor, f"{rel} 仅 {path.stat().st_size} 字节，低于下限 {floor}"


def test_archive_headers_mark_snapshot() -> None:
    zh = (PROJECT_ROOT / ARCHIVES[0][0]).read_text(encoding="utf-8")
    en = (PROJECT_ROOT / ARCHIVES[1][0]).read_text(encoding="utf-8")
    assert "历史快照" in zh and "最后更新" in zh
    assert "historical snapshot" in en.lower()
    for rel, _ in ARCHIVES[2:]:
        assert "1.0.0" in (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def test_new_changelog_links_all_archives() -> None:
    for changelog in ("CHANGELOG.md", "CHANGELOG.en.md"):
        text = (PROJECT_ROOT / changelog).read_text(encoding="utf-8")
        for rel, _ in ARCHIVES:
            assert f"]({rel})" in text, f"{changelog} 未链接 {rel}"
