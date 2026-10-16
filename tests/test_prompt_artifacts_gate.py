#!/usr/bin/env python3
"""Instruction artifact 抽取器与哈希锁门禁的回归测试（零 LLM、零网络）。

锁定三件事：
1. **抽取保真**：`collect_artifacts()` 对每个登记 artifact 给出非空文本与稳定
   sha256（同进程两次调用逐位一致）——这是"逐字抽取"的可验证前提；
2. **文本来源正确**：模板常量与内联段落的抽取结果必须与源码中的实际字符串一致
   （内联段落走 AST 字面量，不依赖运行期 state）；
3. **门禁真的会红**：篡改清单哈希 / 伪造幽灵条目 / 清单缺失（strict）都必须失败，
   否则哈希锁只是装饰。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GATE_PATH = _REPO_ROOT / "scripts" / "gates" / "check_prompt_artifacts.py"
_spec = importlib.util.spec_from_file_location("_prompt_gate", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["_prompt_gate"] = gate
_spec.loader.exec_module(gate)

from experiments.prompt_artifacts import (  # noqa: E402
    _ARTIFACT_SPECS,
    _load_inline_literal,
    build_markdown,
    collect_artifacts,
)

_MANIFEST_GLOB = "experiments/results/prompt_artifacts_*/PROMPT_ARTIFACTS.json"
_HAS_MANIFEST = bool(sorted(_REPO_ROOT.glob(_MANIFEST_GLOB)))


class TestCollector:
    def test_all_registered_artifacts_are_extracted(self):
        rows = collect_artifacts()
        assert len(rows) == len(_ARTIFACT_SPECS)
        assert {r["id"] for r in rows} == {s["id"] for s in _ARTIFACT_SPECS}

    def test_every_artifact_has_text_and_hash(self):
        for row in collect_artifacts():
            assert row["text"].strip(), f"{row['id']} 文本为空"
            assert len(row["sha256"]) == 64
            assert row["chars"] == len(row["text"])

    def test_extraction_is_deterministic(self):
        first = {r["id"]: r["sha256"] for r in collect_artifacts()}
        second = {r["id"]: r["sha256"] for r in collect_artifacts()}
        assert first == second

    def test_template_artifact_matches_source_constant(self):
        """模板类 artifact 必须与 `templates.py` 的常量逐字一致。"""
        from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT, GENERATOR_SYSTEM_PROMPT

        rows = {r["id"]: r for r in collect_artifacts()}
        assert rows["generator_system_prompt"]["text"] == GENERATOR_SYSTEM_PROMPT
        assert rows["debugger_system_prompt"]["text"] == DEBUGGER_SYSTEM_PROMPT

    def test_inline_artifacts_are_extracted_from_ast_literals(self):
        """内联段落用 AST 字面量抽取，不依赖运行期 state（无需构造工作流状态）。"""
        detection = _load_inline_literal("src.graph.nodes", "_detection_first_section")
        over_red = _load_inline_literal("src.graph.nodes", "_over_red_section")
        assert "检出优先" in detection and "先红后绿" in detection
        assert "过红" in over_red and "特异" in over_red

    def test_injection_calibers_are_recorded(self):
        """每个 artifact 必须记录注入口径（env + 默认值 + 关闭时行为）。"""
        for row in collect_artifacts():
            assert "mode" in row["injection"]
            assert row["on_disabled"], row["id"]
            if row["injection"]["mode"] != "always":
                assert row["injection"]["env"], row["id"]
                assert row["injection"]["default"] in {"true", "false"}, row["id"]

    def test_markdown_contains_full_text_and_hashes(self):
        rows = collect_artifacts()
        md = build_markdown(rows, json_name="PROMPT_ARTIFACTS.json")
        for row in rows:
            assert row["id"] in md
            assert row["sha256"][:12] in md
        assert "```text" in md


class TestGate:
    def _write_manifest(self, tmp_path: Path, rows: list[dict]) -> Path:
        payload = {"generated_by": "test", "count": len(rows), "artifacts": rows}
        path = tmp_path / "PROMPT_ARTIFACTS.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_missing_manifest_skips_by_default(self, tmp_path: Path, capsys):
        code = gate.main(["--manifest", str(tmp_path / "absent.json")])
        assert code == 0
        assert "SKIP" in capsys.readouterr().out

    def test_missing_manifest_fails_in_strict(self, tmp_path: Path):
        assert gate.main(["--manifest", str(tmp_path / "absent.json"), "--strict"]) == 1

    def test_matching_manifest_passes(self, tmp_path: Path):
        rows = collect_artifacts()
        # 用实时抽取结果构造"最新清单"，必须通过
        manifest = self._write_manifest(tmp_path, rows)
        assert gate.main(["--manifest", str(manifest)]) == 0

    def test_stale_hash_fails(self, tmp_path: Path):
        rows = collect_artifacts()
        rows[0] = {**rows[0], "sha256": "0" * 64}
        manifest = self._write_manifest(tmp_path, rows)
        assert gate.main(["--manifest", str(manifest)]) == 1

    def test_ghost_entry_fails(self, tmp_path: Path):
        rows = [*collect_artifacts(), {"id": "ghost_artifact", "sha256": "a" * 64, "chars": 1}]
        manifest = self._write_manifest(tmp_path, rows)
        assert gate.main(["--manifest", str(manifest)]) == 1

    def test_corrupt_manifest_fails(self, tmp_path: Path):
        path = tmp_path / "PROMPT_ARTIFACTS.json"
        path.write_text("{not json", encoding="utf-8")
        assert gate.main(["--manifest", str(path)]) == 1

    @pytest.mark.skipif(not _HAS_MANIFEST, reason="清单工件未生成（派生物不入 git）")
    def test_repo_manifest_is_current(self):
        """仓库现状自检：已生成的清单必须与当前源码一致。"""
        assert gate.main([]) == 0


class TestPromptCard:
    """Prompt Card 派生件：结构完整、与门禁同口径、幂等。"""

    def test_card_contains_core_artifact_full_text(self):
        rows = collect_artifacts()
        from experiments.prompt_artifacts import build_prompt_card

        card = build_prompt_card(rows, generated_at="2026-10-15")
        core = next(r for r in rows if r["id"] == "detection_first_section")
        assert core["text"].rstrip() in card, "核心 artifact 全文必须在卡内逐字出现"
        assert core["sha256"] in card

    def test_card_lists_every_artifact_hash(self):
        from experiments.prompt_artifacts import build_prompt_card

        rows = collect_artifacts()
        card = build_prompt_card(rows, generated_at="2026-10-15")
        for row in rows:
            assert row["sha256"] in card, row["id"]
            assert row["id"] in card

    def test_card_call_site_count_matches_json_contract_gate(self):
        """卡内调用点数必须等于 JSON 契约门禁的权威计数（口径 A=7）。"""
        import importlib.util

        from experiments.prompt_artifacts import _call_sites, build_prompt_card

        spec = importlib.util.spec_from_file_location(
            "_json_gate", _REPO_ROOT / "scripts" / "gates" / "check_json_contract_sites.py"
        )
        assert spec and spec.loader
        gate_mod = importlib.util.module_from_spec(spec)
        sys.modules["_json_gate"] = gate_mod
        spec.loader.exec_module(gate_mod)

        sites = _call_sites()
        total = sum(len(v) for v in sites.values())
        assert total == gate_mod.EXPECTED_SITES, f"卡内调用点 {total} ≠ 门禁权威值 {gate_mod.EXPECTED_SITES}"
        card = build_prompt_card(collect_artifacts(), generated_at="2026-10-15")
        # 卡内两处声明：§0 概述与 §3 合计——都必须是权威值
        assert f"**{gate_mod.EXPECTED_SITES} 个 JSON 契约调用点**" in card
        assert f"合计 **{gate_mod.EXPECTED_SITES}** 处" in card

    def test_card_declares_boundaries_and_pending_confirmation(self):
        from experiments.prompt_artifacts import build_prompt_card

        card = build_prompt_card(collect_artifacts(), generated_at="2026-10-15")
        assert "请勿手工编辑" in card
        assert "SPEC_EXPR_GRAMMAR_SECTION" in card, "必须显式声明未纳入的动态文法段"
        assert "- [ ] 确认" in card, "必须保留待作者确认清单"

    def test_card_generation_is_idempotent(self):
        from experiments.prompt_artifacts import build_prompt_card

        rows = collect_artifacts()
        first = build_prompt_card(rows, generated_at="2026-10-15")
        second = build_prompt_card(rows, generated_at="2026-10-15")
        assert first == second

    def test_call_sites_line_numbers_are_numerically_sorted(self):
        from experiments.prompt_artifacts import _call_sites

        for path, linenos in _call_sites().items():
            numbers = [int(n) for n in linenos]
            assert numbers == sorted(numbers), (path, linenos)

    @pytest.mark.skipif(not _HAS_MANIFEST, reason="清单工件未生成")
    def test_repo_card_is_current(self):
        """仓库现状自检：已生成的卡必须与当前源码抽取结果一致。"""
        from experiments.prompt_artifacts import build_prompt_card, collect_artifacts

        card_path = sorted(_REPO_ROOT.glob("experiments/results/prompt_artifacts_*/PROMPT_CARD.md"))[-1]
        rows = collect_artifacts()
        expected = build_prompt_card(rows, generated_at="2026-10-15")
        actual = card_path.read_text(encoding="utf-8")
        # 生成日期由运行日决定，比较时剔除该行（其余必须逐字一致）
        strip = lambda text: "\n".join(  # noqa: E731
            line for line in text.splitlines() if "自动生成（" not in line
        )
        assert strip(actual) == strip(expected), "Prompt Card 与源码抽取结果不一致，请重跑 make prompt-artifacts"
