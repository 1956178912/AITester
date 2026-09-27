"""
error_classifier 组合路由补全测试（2026-09-29 批次，把 88% 分支覆盖率
补到 90% 严格门槛）。

补齐缺口（对照 coverage.xml 实测 88.46% 的未命中分支）：
- refine_failure_category 的边界组合：patch_syntax_invalid 标志与
  error_category 同值/异值交叉、multi_candidate 候选数 0 / 静态通过 >0
  交叉、None test_passed 直通；
- classify_llm_response 的正常/截断/空响应三分支边界；
- get_recommended_fix_strategy 全类别查表（含带上下文的 IMPORT/SYNTAX
  细化与不带上下文的缺省兜底）；
- classify 与 classify_with_confidence 的 L2 分类器注入 + 兜底交叉
  （低置信 × L2 精判越限 / 未越限 / 兜底触发三态）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import (
    ErrorCategory,
    ErrorClassifier,
    ErrorContext,
    ProbabilisticClassifier,
    classify_with_confidence,
    get_fix_strategy,
    get_recommended_fix_strategy,
    refine_failure_category,
    refine_final_error_category,
)

_clf = ErrorClassifier()


class TestRefineEdgeCombinations:
    """refine_failure_category 交叉场景（组合路由分支补全）。"""

    def test_patch_syntax_invalid_flag_with_other_category(self):
        """标志位 True + 类别非 patch_syntax_invalid → 收敛到 patch_syntax_invalid。"""
        result = refine_failure_category(
            "syntax",
            False,
            execution_trace=[{"iter": 1}],
            patch_syntax_invalid=True,
        )
        assert result == "patch_syntax_invalid"

    def test_patch_syntax_invalid_category_value_only(self):
        """类别值本身命中（标志位缺省）→ 同样收敛。"""
        result = refine_failure_category(
            "patch_syntax_invalid",
            False,
            execution_trace=[{"iter": 1}],
        )
        assert result == "patch_syntax_invalid"

    def test_multi_candidate_zero_candidates_passthrough(self):
        """candidates=0（多候选未启用）→ 不走全拒绝分支，原样返回。"""
        mcs = {"candidates": 0, "static_passed": 0}
        result = refine_failure_category("runtime", False, execution_trace=[{"iter": 1}], multi_candidate_stats=mcs)
        assert result == "runtime"

    def test_multi_candidate_partial_pass_keeps(self):
        """static_passed>0 → 部分候选存活，不命中全拒绝。"""
        mcs = {"candidates": 4, "static_passed": 2}
        result = refine_failure_category("assertion", False, execution_trace=[{"iter": 1}], multi_candidate_stats=mcs)
        assert result == "assertion"

    def test_multi_candidate_stats_missing_keys(self):
        """缺键（get() 缺省 0）→ 全拒绝判定不成立，原样返回。"""
        result = refine_failure_category("runtime", False, execution_trace=[{"iter": 1}], multi_candidate_stats={})
        assert result == "runtime"

    def test_none_test_passed_passthrough(self):
        assert refine_failure_category("timeout", None, repair_history=[{"patch_applied": False}]) == "timeout"

    def test_true_test_passed_passthrough(self):
        assert refine_failure_category("unknown", True, rag_stats=[{"results": 0}]) == "unknown"

    def test_rag_partial_results_keeps_category(self):
        """rag_stats 部分命中（results>0 存在）→ 非"全空"，保留原类别。"""
        result = refine_failure_category(
            "index_error",
            False,
            rag_stats=[{"results": 0}, {"results": 3}],
            execution_trace=[{"iter": 1}],
        )
        assert result == "index_error"

    def test_rag_empty_list_not_retrieval_empty(self):
        """rag_stats=[]（未启用 RAG）→ 不命中全空分支。"""
        result = refine_failure_category("runtime", False, rag_stats=[], execution_trace=[{"iter": 1}])
        assert result == "runtime"

    def test_repair_history_missing_key_not_rejected(self):
        """键缺失（get() 缺省）→ 不视为拒绝。"""
        result = refine_failure_category("runtime", False, repair_history=[{}, {"patch_applied": True}])
        assert result == "execution_trace_missing"  # 无 execution_trace 兜底命中


class TestRefineFinalStateWiring:
    def test_full_state_with_flag(self):
        state = {
            "error_category": "syntax",
            "test_passed": False,
            "execution_trace": [{"iter": 1}],
            "patch_syntax_invalid_flag": True,
        }
        assert refine_final_error_category(state) == "patch_syntax_invalid"

    def test_empty_state_defaults(self):
        """全键缺失：error_category 缺省 ""、test_passed 缺省 False、
        execution_trace None → 收敛到 execution_trace_missing。"""
        assert refine_final_error_category({}) == "execution_trace_missing"

    def test_successful_state_passthrough(self):
        state = {"error_category": "unknown", "test_passed": True}
        assert refine_final_error_category(state) == "unknown"


class TestClassifyLlmResponseBranches:
    def test_empty_response(self):
        assert ErrorClassifier.classify_llm_response("") == ErrorCategory.LLM_EMPTY_RESPONSE
        assert ErrorClassifier.classify_llm_response("   \n\t") == ErrorCategory.LLM_EMPTY_RESPONSE

    def test_json_parse_failed_markdown_wrapped(self):
        # 非空但无法提取 JSON → JSON 解析失败
        assert ErrorClassifier.classify_llm_response("```json\n{broken") == ErrorCategory.LLM_JSON_PARSE_FAILED

    def test_valid_json_returns_format_category(self):
        # 提取成功（非空 dict）→ 保留 LLM_FORMAT_ERROR 大类语义
        assert ErrorClassifier.classify_llm_response('{"result": 1}') == ErrorCategory.LLM_FORMAT_ERROR

    def test_empty_dict_is_parse_failed(self):
        assert ErrorClassifier.classify_llm_response("{}") == ErrorCategory.LLM_JSON_PARSE_FAILED


class TestGetRecommendedStrategyAllCategories:
    def test_all_categories_have_strategy_record(self):
        for cat in ErrorCategory:
            record = get_recommended_fix_strategy(cat)
            assert record["category"] == cat.value
            assert record["strategy"]
            assert record["description"]
            assert record["repair_action"] in {"llm_resample", "repair_code", "repair_test", "investigate_infra", "no_action"}

    def test_unknown_category_fallback_tag(self):
        # 未知类别（构造一个不在映射表的哨兵）→ 通用兜底标签
        record = get_recommended_fix_strategy(ErrorCategory.UNKNOWN)
        assert record["strategy"] == "generic_analysis"

    def test_context_aware_strategy_text(self):
        ctx = ErrorContext(module_name="pandas", filename="calc.py", line=7, subtype=None)
        text = get_fix_strategy(ErrorCategory.IMPORT_ERROR, context=ctx)
        assert "pandas" in text
        # SYNTAX 无子类型（subtype=None）→ 走完整文件重写兜底策略（不含定位
        # 信息）；定位细化仅在 SYNTAX_ERROR 子类型时生效（_syntax_strategy）
        text2 = get_fix_strategy(ErrorCategory.SYNTAX, context=ctx)
        assert "完整文件" in text2 or "import" in text2
        # SYNTAX_ERROR 子类型 → 带定位的细化策略
        from src.agents.error_classifier import SyntaxSubtype

        ctx2 = ErrorContext(filename="calc.py", line=7, column=3, subtype=SyntaxSubtype.SYNTAX_ERROR)
        text3 = get_fix_strategy(ErrorCategory.SYNTAX, context=ctx2)
        assert "calc.py" in text3 and "7" in text3

    def test_no_context_strategy_text(self):
        text = get_fix_strategy(ErrorCategory.IMPORT_ERROR, context=None)
        assert "ImportError" in text or "导入" in text


class TestL2ClassifierInjection:
    """L2 概率分类器注入 + 低置信兜底交叉（三态：L2 越限 / L2 未越限 / 兜底）。"""

    def _make_l2(self, cat: ErrorCategory, conf: float) -> ProbabilisticClassifier:
        class _L2:
            def predict(self, combined_text, target_module):
                return cat, conf

        return _L2()

    def test_l2_refines_low_confidence_when_above_threshold(self):
        result = classify_with_confidence("mystery gibberish", classifier=self._make_l2(ErrorCategory.RUNTIME, 0.8))
        assert result.category == ErrorCategory.RUNTIME
        assert result.confidence_basis == "l2_probabilistic"

    def test_l2_below_threshold_keeps_fallback(self):
        result = classify_with_confidence("mystery gibberish", classifier=self._make_l2(ErrorCategory.RUNTIME, 0.3))
        assert result.confidence_basis == "fallback_unknown"
        assert result.category == ErrorCategory.UNKNOWN
        assert result.fallback_used is True

    def test_high_confidence_skips_l2(self):
        called = []

        class _L2:
            def predict(self, combined_text, target_module):
                called.append(1)
                return ErrorCategory.RUNTIME, 0.9

        out = "ZeroDivisionError: division by zero"
        result = classify_with_confidence(out, classifier=_L2())
        assert result.category == ErrorCategory.RUNTIME
        assert called == []  # 高置信样本不路由 L2（零 LLM 成本口径）

    def test_l2_applied_to_weak_syntax(self):
        """弱命中 SYNTAX（confidence=0.5 低置信）+ L2 越限 → L2 精判取代兜底。"""
        out = "calc.py:12:13: error"  # 仅通用格式命中，无具体语法关键词
        result = classify_with_confidence(out, classifier=self._make_l2(ErrorCategory.INDEX_ERROR, 0.85))
        assert result.category == ErrorCategory.INDEX_ERROR
        assert result.confidence_basis == "l2_probabilistic"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
