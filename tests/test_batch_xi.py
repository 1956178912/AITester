"""修复引擎批次 XI（2026-10-07）：oracle 上下文消融档测试锁（ADR-0025）。

锁定三组行为：
1. oracle_context_tier：默认 full、minimal 档、非法值回退 full；
2. _generator_node 四段剥离契约（minimal 时分支覆盖/边界锚点/蜕变/
   差分全不构造——源码级接线锁）；
3. 历史口径零变化（默认 full 时四段构造条件与原逻辑一致）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.logic_spec import oracle_context_minimal, oracle_context_tier


class TestOracleContextTier:
    def test_default_full(self, monkeypatch) -> None:
        monkeypatch.delenv("ORACLE_CONTEXT_TIER", raising=False)
        assert oracle_context_tier() == "full"
        assert oracle_context_minimal() is False

    def test_minimal_tier(self, monkeypatch) -> None:
        monkeypatch.setenv("ORACLE_CONTEXT_TIER", "minimal")
        assert oracle_context_tier() == "minimal"
        assert oracle_context_minimal() is True

    def test_invalid_value_falls_back_to_full(self, monkeypatch) -> None:
        monkeypatch.setenv("ORACLE_CONTEXT_TIER", "turbo")
        assert oracle_context_tier() == "full"
        assert oracle_context_minimal() is False

    def test_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("ORACLE_CONTEXT_TIER", "  MINIMAL  ")
        assert oracle_context_tier() == "minimal"


class TestGeneratorNodeWiringContract:
    """源码级接线锁：minimal 守卫覆盖四个增强段构造条件。"""

    SRC = Path("src/graph/nodes.py").read_text(encoding="utf-8")

    def test_tier_gate_imported(self) -> None:
        assert "oracle_context_minimal as _oracle_ctx_minimal" in self.SRC

    def test_all_four_sections_gated(self) -> None:
        # 四段的构造条件均带 not _ctx_minimal 前缀
        assert "if not _ctx_minimal and _branch_coverage_inject_enabled()" in self.SRC
        assert "if not _ctx_minimal and _boundary_triplets_enabled()" in self.SRC
        assert "if not _ctx_minimal and _mr_enabled() and _fn_name:" in self.SRC
        assert "if not _ctx_minimal and _diff_enabled() and _fn_name:" in self.SRC

    def test_section_variables_default_none(self) -> None:
        # 四段变量保持 None 缺省（minimal 时不注入的结构保证）
        assert "_bc_section: str | None = None" in self.SRC
        assert "_bt_section: str | None = None" in self.SRC
        assert "_mr_section: str | None = None" in self.SRC
        assert "_diff_section: str | None = None" in self.SRC


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
