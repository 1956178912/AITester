"""修复引擎批次 XVI（2026-10-10，ADR-0020 修订）：验证层观测行为锁。

锁定两组行为：
1. 求值核 evaluate_patch_validation（三档验证证据命中/优先级/None 保守）；
2. filtered_success 组合判定（passed ∧ ¬abstain ∧ validated）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.patch_validate import (
    evaluate_patch_validation,
    filtered_success,
    patch_validate_verdict_names,
)


class TestEvaluatePatchValidation:
    def test_none_record_conservative(self) -> None:
        assert evaluate_patch_validation(None) == {
            "validated": False,
            "verdict": "not_applicable",
            "signals": [],
        }

    def test_empty_record_unvalidated(self) -> None:
        assert evaluate_patch_validation({}) == {
            "validated": False,
            "verdict": "unvalidated",
            "signals": [],
        }

    def test_gold_verdict_strongest(self) -> None:
        """repo_verification.passed=True 命中 gold 档（最强证据）。"""
        result = evaluate_patch_validation({"repo_verification": {"passed": True}})
        assert result == {"validated": True, "verdict": "gold", "signals": ["gold"]}

    def test_deterministic_verdict(self) -> None:
        """确定性修复引擎产出命中 deterministic 档（ADR-0019）。"""
        result = evaluate_patch_validation({"deterministic_repair_status": {"patch_produced": True}})
        assert result == {"validated": True, "verdict": "deterministic", "signals": ["deterministic"]}

    def test_evidence_verdict(self) -> None:
        """确定性证据门放行（gold/sbfl）命中 evidence 档。"""
        for level in ("gold", "sbfl"):
            result = evaluate_patch_validation({"patch_evidence_level": level})
            assert result == {"validated": True, "verdict": "evidence", "signals": ["evidence"]}, level

    def test_gold_priority_over_evidence(self) -> None:
        """gold 档优先于 evidence 档（取最高命中等级）。"""
        record = {
            "repo_verification": {"passed": True},
            "patch_evidence_level": "sbfl",
        }
        result = evaluate_patch_validation(record)
        assert result["verdict"] == "gold"

    def test_keyword_evidence_not_validated(self) -> None:
        """keyword/none 证据等级不构成独立验证证据。"""
        for level in ("keyword", "none"):
            result = evaluate_patch_validation({"patch_evidence_level": level})
            assert result["validated"] is False, level
            assert result["verdict"] == "unvalidated", level

    def test_repo_verification_not_passed_not_validated(self) -> None:
        """repo_verification.passed=False 或缺失 passed 键不命中 gold。"""
        assert evaluate_patch_validation({"repo_verification": {"passed": False}})["verdict"] == "unvalidated"
        assert evaluate_patch_validation({"repo_verification": {}})["verdict"] == "unvalidated"

    def test_deterministic_not_produced_not_validated(self) -> None:
        assert (
            evaluate_patch_validation({"deterministic_repair_status": {"patch_produced": False}})["verdict"]
            == "unvalidated"
        )

    def test_verdict_names_catalogue(self) -> None:
        assert set(patch_validate_verdict_names()) == {
            "gold",
            "deterministic",
            "evidence",
            "unvalidated",
            "not_applicable",
        }


class TestFilteredSuccess:
    def test_all_three_conditions(self) -> None:
        """passed ∧ ¬abstain ∧ validated 才计 filtered success。"""
        assert filtered_success({"passed": True, "patch_abstained": False, "patch_validated": True}) is True

    def test_failed_not_filtered(self) -> None:
        assert filtered_success({"passed": False, "patch_abstained": False, "patch_validated": True}) is False

    def test_abstained_not_filtered(self) -> None:
        assert filtered_success({"passed": True, "patch_abstained": True, "patch_validated": True}) is False

    def test_unvalidated_not_filtered(self) -> None:
        assert filtered_success({"passed": True, "patch_abstained": False, "patch_validated": False}) is False

    def test_missing_keys_conservative(self) -> None:
        """缺键保守：不当作 filtered success（与求值核保守口径一致）。"""
        assert filtered_success({"passed": True}) is False
