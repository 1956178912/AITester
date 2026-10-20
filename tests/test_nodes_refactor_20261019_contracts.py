"""重构契约：三个高复杂度节点拆分后的私有 helper 默认档行为（2026-10-19）。

本文件不重复节点级回归（`tests/test_workflow*.py` 已覆盖主链路），只锁定
**拆分边界**本身：

- 默认关闭的开关必须保持"零写入 / 零附加 LLM 调用"的历史口径；
- helper 的返回键集合固定，主节点按名消费时不会因拆分漂移；
- 未写盘 / 未启用时不得产生快照或证据门副作用。

这样任何后续"顺手改默认值"都会被直接暴露，而不是被 9300+ 例回归掩盖。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.graph import nodes


def _state(**extra: Any) -> dict[str, Any]:
    """最小可用状态（只含 helper 读取的键，避免无关字段干扰）。"""
    base: dict[str, Any] = {
        "target_code": "def f(x):\n    return x\n",
        "target_function": "f",
        "module_name": "m",
    }
    base.update(extra)
    return base


class TestGeneratorHelpers:
    def test_rag_disabled_returns_no_refs_and_no_stat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "ENABLE_RAG", False)
        refs, stat = nodes._retrieve_generator_rag_refs(_state())
        assert refs is None
        assert stat is None

    def test_minimal_tier_suppresses_all_static_sections(self) -> None:
        sections = nodes._build_generator_static_sections(_state(), ctx_minimal=True)
        assert sections == {
            "branch_coverage_section": None,
            "feedback_compression_section": None,
            "compressed_feedback": None,
            "boundary_triplets_section": None,
            "paths_section": None,
            "operation_map_section": None,
        }

    def test_minimal_tier_suppresses_oracle_sections(self) -> None:
        sections = nodes._build_generator_oracle_sections(_state(), {}, ctx_minimal=True)
        assert sections == {
            "metamorphic_section": None,
            "differential_section": None,
            "injection_findings": [],
            "injection_warning": None,
            "spec_replace_section": None,
            "spec_augment_section": None,
            "spec_replace_applied": None,
            "spec_augment_applied": None,
            "empty_plan_shortcut": False,
        }

    def test_prompt_sections_merge_both_groups(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.tools.logic_spec as logic_spec

        monkeypatch.setattr(logic_spec, "oracle_context_minimal", lambda: True)
        sections = nodes._build_generator_prompt_sections(_state(), {})
        assert len(sections) == 15
        assert all(
            sections[key] is None
            for key in (
                "branch_coverage_section",
                "boundary_triplets_section",
                "paths_section",
                "operation_map_section",
                "metamorphic_section",
                "differential_section",
                "spec_replace_section",
                "spec_augment_section",
            )
        )
        assert sections["injection_findings"] == []
        assert sections["empty_plan_shortcut"] is False

    def test_postchecks_return_fixed_keys_on_plain_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "_oracle_validate_enabled", lambda: False)
        monkeypatch.setattr(nodes, "_apply_test_suite_dedup", lambda code: (code, 0))
        monkeypatch.setattr(nodes, "_spec_oracle_injection_verdict", lambda code, _state: (code, None, "not_attempted"))
        code = "def test_f():\n    assert f(1) == 1\n"
        result = nodes._run_generator_postchecks(_state(), code)
        assert result["generated_test"] == code
        assert result["oracle_findings"] == []
        assert result["deterministic_guard_report"] is None
        assert result["tautological_count"] == 0
        assert result["o4_triggered"] is False
        assert result["spec_oracle_injected"] is None
        assert result["spec_oracle_verdict"] == "not_attempted"


class TestExecutorHelpers:
    def test_rogue_monitor_disabled_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "rogue_monitor_enabled", lambda: False)
        update: dict[str, Any] = {}
        nodes._apply_executor_rogue_monitor(update)
        assert update == {}

    def test_detection_first_disabled_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "detection_first_enabled", lambda: False)
        update: dict[str, Any] = {}
        nodes._apply_executor_detection_first(update, _state(), passed=True)
        nodes._apply_executor_ac2_gates(update, _state(), passed=False)
        assert update == {}

    def test_branch_coverage_disabled_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "_branch_coverage_inject_enabled", lambda: False)
        update: dict[str, Any] = {}
        nodes._apply_executor_branch_coverage(update, _state())
        assert update == {}

    def test_patch_rollback_noop_when_execution_passed(self) -> None:
        update: dict[str, Any] = {}
        nodes._apply_executor_patch_rollback(update, _state(), passed=True)
        assert update == {}


class TestPatchHelpers:
    def test_same_code_needs_no_safety_scan(self) -> None:
        code = "def f(x):\n    return x\n"
        state = _state(target_code=code)
        assert nodes._check_patch_safety(state, code, code, applied=True) == (True, code)
        assert "_1_3_contract_missing" not in state

    def test_evidence_gate_skipped_when_not_written(self) -> None:
        code = "def f(x):\n    return x\n"
        written, new_code, update = nodes._apply_patch_evidence_gate(_state(), code, code, False, {})
        assert (written, new_code, update) == (False, code, {})

    def test_snapshot_rollback_disabled_records_not_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(nodes, "snapshot_rollback_enabled", lambda: False)
        code = "def f(x):\n    return x\n"
        update: dict[str, Any] = {}
        effective, written = nodes._apply_snapshot_rollback(_state(), code, False, code, update)
        assert (effective, written) == (code, False)
        assert update == {"patch_rollback_verdict": "not_enabled", "patch_rolled_back": False}

    def test_single_patch_path_delegates_to_applier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = "def f(x):\n    return x\n"
        monkeypatch.setattr(nodes, "multi_candidate_available", lambda: False)

        def _apply(*, original_code: str, patch: str) -> tuple[str, bool]:
            return original_code + "\n# " + patch, True

        monkeypatch.setattr(nodes, "apply_patch_to_code", _apply)
        new_code, applied, extra = nodes._resolve_patch_application(_state(cross_file_deps=[], patch="diff"), original)
        assert (new_code, applied, extra) == (original + "\n# diff", True, {})
