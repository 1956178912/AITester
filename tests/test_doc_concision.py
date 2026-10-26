"""DD 轮（2026-10-26）文档重写：门面与 docs 核心的行数上限（简洁度棘轮）。

锁语义：每份重写文档不得超过上限。上限是棘轮，只降不升——升上限必须在本
文件里显式改数字，等于把「文档又变长了」变成一次需要解释的 diff。
冻结的研究证据与归档快照不在本集合：篇幅由内容决定，不参与简洁度判据。
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LINE_LIMITS: dict[str, int] = {
    "README.md": 160,
    "README.en.md": 160,
    "CHANGELOG.md": 160,
    "CHANGELOG.en.md": 160,
    "QUICKSTART.md": 100,
    "QUICKSTART.en.md": 100,
    "CONTRIBUTING.md": 80,
    "CONTRIBUTING.en.md": 80,
    "MODEL_CARD.md": 90,
    "MODEL_CARD.en.md": 90,
    "REPLICATION.md": 100,
    "REPLICATION.en.md": 100,
    "SECURITY.md": 50,
    "SECURITY.en.md": 50,
    "docs/INDEX.md": 100,
    "docs/INDEX.en.md": 100,
    "docs/api_reference.md": 350,
    "docs/api_reference.en.md": 350,
    "docs/usage_examples.md": 200,
    "docs/usage_examples.en.md": 200,
    "docs/performance_guide.md": 220,
    "docs/performance_guide.en.md": 220,
    "docs/troubleshooting.md": 110,
    "docs/troubleshooting.en.md": 110,
    "docs/threat_model.md": 90,
    "docs/threat_model.en.md": 90,
    "docs/COST_MODEL.md": 100,
    "docs/COST_MODEL.en.md": 100,
}


def test_limits_cover_exactly_the_rewrite_set() -> None:
    assert len(LINE_LIMITS) == 28


@pytest.mark.parametrize(("rel", "limit"), sorted(LINE_LIMITS.items()))
def test_rewritten_doc_within_line_ceiling(rel: str, limit: int) -> None:
    path = PROJECT_ROOT / rel
    assert path.is_file(), f"{rel} 缺失（fail-closed）"
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= limit, f"{rel} 现有 {lines} 行，超过上限 {limit}"
