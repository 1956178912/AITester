"""
1. 错误分类器置信度分层单元测试（改进清单 P1）。

验证：
- L1 规则命中（具体特征）→ 高置信（0.9）；
- L1 弱命中（仅通用格式）→ 中置信（0.5）+ 触发兜底标记；
- L1 未命中（UNKNOWN）→ 低置信（0.2）+ 兜底策略；
- enable_fallback=False 时分类结果与历史 17 类口径逐样本等价；
- L2 概率化/ML 层协议预留（_default_probabilistic_classifier 恒 None）；
- 模块级 classify_with_confidence 与实例方法口径一致。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import (
    ClassificationResult,
    ErrorCategory,
    ErrorClassifier,
    _default_probabilistic_classifier,
    classify_with_confidence,
)


def _clf() -> ErrorClassifier:
    return ErrorClassifier()


class TestConfidenceScoring:
    """L1 规则层置信度打分。"""

    def test_concrete_syntax_high_confidence(self):
        out = "ERRORS\nE   SyntaxError: invalid syntax\n    file.py:42:10: SyntaxError"
        res = _clf().classify_with_confidence(out, enable_fallback=False)
        assert res.category == ErrorCategory.SYNTAX
        assert res.confidence == 0.9
        assert res.confidence_basis == "regex_hit"
        assert not res.fallback_used

    def test_weak_syntax_low_confidence_triggers_fallback(self):
        """仅 E 前缀 / 冒号格式命中、无具体异常关键词 → 弱命中 + 兜底。

        启用兜底时类别收敛为兜底类别（UNKNOWN → generic_analysis），
        兜底标记仍保留弱命中口径信息（confidence=0.5 / regex_weak）。
        """
        out = "ERRORS\nE   module.py:10:5: some vague error"
        res = _clf().classify_with_confidence(out, enable_fallback=True)
        assert res.category == ErrorCategory.UNKNOWN  # 弱命中 SYNTAX → 收敛到兜底类别
        assert res.confidence == 0.5
        assert res.confidence_basis == "fallback_unknown"  # 兜底口径（弱命中已收敛）
        assert res.fallback_used is True
        assert res.fallback_category == ErrorCategory.UNKNOWN

    def test_weak_syntax_no_fallback_keeps_syntax(self):
        """不启用兜底时弱命中 SYNTAX 保留 SYNTAX 类别（历史 17 类口径等价）。"""
        out = "ERRORS\nE   module.py:10:5: some vague error"
        res = _clf().classify_with_confidence(out, enable_fallback=False)
        assert res.category == ErrorCategory.SYNTAX
        assert res.confidence == 0.5
        assert res.confidence_basis == "regex_weak"
        assert not res.fallback_used

    def test_unknown_low_confidence_triggers_fallback(self):
        out = "something unrecognizable with no error markers"
        res = _clf().classify_with_confidence(out, enable_fallback=True)
        assert res.category == ErrorCategory.UNKNOWN
        assert res.confidence == 0.2
        assert res.confidence_basis == "fallback_unknown"
        assert res.fallback_used is True

    def test_import_error_high_when_module_extractable(self):
        out = "ModuleNotFoundError: No module named 'pandas'"
        res = _clf().classify_with_confidence(out, enable_fallback=False)
        assert res.category == ErrorCategory.IMPORT_ERROR
        assert res.confidence == 0.9

    def test_import_error_weak_when_no_module_name(self):
        out = "ImportError: cannot import"
        res = _clf().classify_with_confidence(out, enable_fallback=False)
        assert res.category == ErrorCategory.IMPORT_ERROR
        assert res.confidence == 0.5

    def test_runtime_high_confidence(self):
        out = "ZeroDivisionError: division by zero"
        res = _clf().classify_with_confidence(out)
        assert res.category == ErrorCategory.RUNTIME
        assert res.confidence == 0.9

    def test_llm_format_error_high(self):
        out = "Error: empty response"
        res = _clf().classify_with_confidence(out)
        assert res.category == ErrorCategory.LLM_FORMAT_ERROR
        assert res.confidence == 0.9

    def test_assertion_high(self):
        out = "AssertionError: assert 5 == 6"
        res = _clf().classify_with_confidence(out)
        assert res.category == ErrorCategory.ASSERTION
        assert res.confidence == 0.9

    def test_timeout_high(self):
        out = "Test ran for longer than 30s, timeout"
        res = _clf().classify_with_confidence(out)
        assert res.category == ErrorCategory.TIMEOUT
        assert res.confidence == 0.9


class TestEquivalenceWithLegacy:
    """enable_fallback=False 时分类结果与历史 17 类口径逐样本等价。"""

    def test_equivalent_to_classify(self):
        samples = [
            "ModuleNotFoundError: No module named 'numpy'",
            "SyntaxError: invalid syntax",
            "TypeError: unsupported operand",
            "IndexError: list index out of range",
            "ZeroDivisionError: division by zero",
            "AssertionError: assert x == y",
            "Test ran for longer than 30s",
            "unrecognizable text with no markers",
            "JSONDecodeError: Expecting value",
        ]
        for out in samples:
            legacy = _clf().classify(out, [])
            confident = _clf().classify_with_confidence(out, enable_fallback=False)
            assert confident.category == legacy, f"分类漂移：{out!r}"

    def test_enable_fallback_does_not_override_high_confidence(self):
        """高置信样本启用兜底也不改变类别（兜底仅作用于低置信）。"""
        out = "ZeroDivisionError: division by zero"
        res = _clf().classify_with_confidence(out, enable_fallback=True)
        assert res.category == ErrorCategory.RUNTIME
        assert res.confidence == 0.9
        assert not res.fallback_used


class TestL2ProtocolReservation:
    """L2 概率化/ML 层协议预留（当前恒 None）。"""

    def test_default_classifier_is_none(self):
        assert _default_probabilistic_classifier() is None

    def test_l2_classifier_can_refine_low_confidence(self):
        """提供 L2 分类器时，低置信样本可用 L2 精判（协议行为验证）。"""

        class _StubL2:
            def predict(self, combined_text, target_module):
                return ErrorCategory.RUNTIME, 0.8

        res = _clf().classify_with_confidence(
            "unrecognizable text with no markers",
            enable_fallback=True,
            classifier=_StubL2(),
        )
        # L2 高置信 → 覆盖 L1 的 UNKNOWN
        assert res.category == ErrorCategory.RUNTIME
        assert res.confidence == 0.8
        assert res.confidence_basis == "l2_probabilistic"

    def test_l2_low_confidence_falls_back_to_fallback(self):
        """L2 置信度 ≤ 门槛（0.5）时维持 L1 兜底口径（弱命中 L2 不覆盖）。"""

        class _StubL2Low:
            def predict(self, combined_text, target_module):
                return ErrorCategory.RUNTIME, 0.5

        res = _clf().classify_with_confidence(
            "unrecognizable text with no markers",
            enable_fallback=True,
            classifier=_StubL2Low(),
        )
        # L2 置信度 0.5 ≤ 门槛 → 不覆盖 L1，维持 L1 兜底口径
        assert res.fallback_used is True
        assert res.fallback_category == ErrorCategory.UNKNOWN
        assert res.category == ErrorCategory.UNKNOWN


class TestModuleLevelFunction:
    """模块级 classify_with_confidence 与实例方法口径一致。"""

    def test_module_level_matches_instance(self):
        out = "ModuleNotFoundError: No module named 'pandas'"
        instance_res = _clf().classify_with_confidence(out, enable_fallback=False)
        module_res = classify_with_confidence(out, enable_fallback=False)
        assert module_res.category == instance_res.category
        assert module_res.confidence == instance_res.confidence
        assert isinstance(module_res, ClassificationResult)

    def test_module_level_with_failed_cases(self):
        out = "FAILED tests/test_x.py::test_a"
        failed = [{"name": "test_a", "error": "ZeroDivisionError: division by zero"}]
        res = classify_with_confidence(out, failed_cases=failed)
        assert res.category == ErrorCategory.RUNTIME


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
