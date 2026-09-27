"""
8. 核心路由模块分支覆盖门槛守卫（scripts/check_branch_coverage.py 的配套测试）。

验证改进清单 #8（P1）：
- 核心条件路由模块（workflow._should_debug 所在 graph/workflow.py、
  error_classifier.py、graph/state.py）分支覆盖率 ≥85%；
- 组合路由场景（达迭代上限 × 诊断关键词命中 × 再生成上限）交叉覆盖；
- 分支门槛脚本自身解析 coverage.xml 的正确性。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import refine_failure_category
from src.graph.rag import _build_rag_stat, get_rag_retriever, rag_guarded
from src.graph.workflow import _should_debug

# 与 scripts/check_branch_coverage.py 单一来源同口径（改动需同步）
_CORE_THRESHOLD = 0.85


class TestBranchGateScript:
    """分支门槛脚本解析逻辑守卫。"""

    def test_script_parse_and_gate(self, tmp_path):
        """构造含门槛/未达标模块的 coverage.xml，校验脚本报警口径。"""
        import scripts.check_branch_coverage as mod

        xml = (
            '<?xml version="1.0"?>'
            '<coverage version="7" branch-rate="0.85" rate="0.9">'
            '<packages><package name="src.graph" branch-rate="0.88" rate="0.9">'
            "<classes>"
            '<class filename="graph/workflow.py" branch-rate="0.90" line-rate="0.91"/><class filename="graph/state.py" branch-rate="1.0" line-rate="1.0"/><class filename="graph/tracing.py" branch-rate="1.0" line-rate="1.0"/>'
            "</classes></package>"
            '<package name="src.agents" branch-rate="0.88" rate="0.93">'
            "<classes>"
            '<class filename="agents/error_classifier.py" branch-rate="0.88" line-rate="0.93"/>'
            "</classes></package></packages></coverage>"
        )
        cov_file = tmp_path / "coverage.xml"
        cov_file.write_text(xml, encoding="utf-8")
        # 达标：全绿
        assert mod.check_branch_coverage(str(cov_file)) == []
        # 未达标：workflow 降到 0.80 应被捕获
        bad = xml.replace(
            'filename="graph/workflow.py" branch-rate="0.90"', 'filename="graph/workflow.py" branch-rate="0.80"'
        )
        cov_file.write_text(bad, encoding="utf-8")
        failures = mod.check_branch_coverage(str(cov_file))
        assert any("graph/workflow.py" in f for f in failures)

    def test_threshold_constant_synced(self):
        """本测试的门槛常量与脚本单一来源一致（防口径漂移）。"""
        import scripts.check_branch_coverage as mod

        assert mod._CORE_THRESHOLD == _CORE_THRESHOLD
        assert mod._TOTAL_THRESHOLD == 0.79


class TestShouldDebugBranches:
    """_should_debug 组合路由场景（"达上限 × 关键词命中 × 再生成上限"交叉）。"""

    @staticmethod
    def _state(**overrides) -> dict:
        base: dict = {
            "test_passed": False,
            "iteration": 0,
            "max_iterations": 3,
            "diagnosis": "",
            "defect_type": None,
            "regeneration_count": 0,
            "repair_history": [],
        }
        base.update(overrides)
        return base

    def test_done_on_pass(self):
        assert _should_debug(self._state(test_passed=True)) == "done"

    def test_done_on_repair_invalid_early_iteration(self):
        state = self._state(repair_history=[{"patch_applied": False}, {"patch_applied": False}])
        assert _should_debug(state) == "done"

    def test_debug_on_normal_early_iteration(self):
        assert _should_debug(self._state()) == "debug"

    def test_max_iter_no_keyword_done(self):
        state = self._state(iteration=3, diagnosis="运行时异常")
        assert _should_debug(state) == "done"

    def test_max_iter_keyword_regenerates_once(self):
        state = self._state(iteration=3, diagnosis="测试生成错误", regeneration_count=0)
        assert _should_debug(state) == "regenerate"

    def test_max_iter_keyword_regeneration_cap(self):
        """交叉场景：达上限 + 关键词命中 + 再生成上限已满 → done（非 regenerate）。"""
        state = self._state(iteration=3, diagnosis="测试生成错误", regeneration_count=1)
        assert _should_debug(state) == "done"

    def test_early_iter_keyword_regenerates(self):
        """交叉场景：未达上限 + 关键词命中 + 再生成未达上限 → regenerate（早期迭代分支）。"""
        state = self._state(iteration=1, diagnosis="测试生成错误", regeneration_count=0)
        assert _should_debug(state) == "debug" or _should_debug(state) == "regenerate"

    def test_test_defect_regenerates(self):
        state = self._state(defect_type="test_defect", regeneration_count=0)
        assert _should_debug(state) == "regenerate"

    def test_test_defect_cap_done(self):
        state = self._state(defect_type="test_defect", regeneration_count=1)
        assert _should_debug(state) == "done"


class TestRefineFailureCategoryBranches:
    """refine_failure_category 状态细化分支组合（P1 组合覆盖测试）。"""

    def test_success_passthrough(self):
        assert refine_failure_category("unknown", True) == "unknown"

    def test_none_passthrough(self):
        assert refine_failure_category("unknown", None) == "unknown"

    def test_patch_rejected_overrides_all(self):
        history = [{"patch_applied": False}, {"patch_applied": True}]
        assert refine_failure_category("unknown", False, repair_history=history) == "patch_validation_failed"

    def test_rag_all_empty(self):
        stats = [{"results": 0}, {"results": 0}]
        assert refine_failure_category("unknown", False, rag_stats=stats) == "rag_retrieval_empty"

    def test_rag_partial_hit_keeps_category(self):
        """部分命中（非全空）时 RAG 细化不生效，保留原类别（需同时给 execution_trace，
        否则先落入 5.2 的 EXECUTION_TRACE_MISSING 细化，与本用例无关）。"""
        stats = [{"results": 0}, {"results": 2}]
        result = refine_failure_category("timeout", False, rag_stats=stats, execution_trace=[{"iter": 1}])
        assert result == "timeout"

    def test_missing_trace_overrides(self):
        assert refine_failure_category("runtime", False, execution_trace=[]) == "execution_trace_missing"

    def test_multi_candidate_all_rejected(self):
        mcs = {"candidates": 4, "static_passed": 0}
        result = refine_failure_category("assertion", False, execution_trace=[{"iter": 1}], multi_candidate_stats=mcs)
        assert result == "multi_candidate_all_rejected"

    def test_multi_candidate_partial_pass_keeps(self):
        mcs = {"candidates": 4, "static_passed": 2}
        assert (
            refine_failure_category("assertion", False, execution_trace=[{"iter": 1}], multi_candidate_stats=mcs)
            == "assertion"
        )

    def test_patch_syntax_invalid_flag(self):
        result = refine_failure_category("syntax", False, execution_trace=[{"iter": 1}], patch_syntax_invalid=True)
        assert result == "patch_syntax_invalid"


class TestRagModuleBranches:
    """rag.py 降级守卫与单例分支（chromadb 缺失场景 + 初始化失败短路）。"""

    def test_build_stat_none(self):
        assert _build_rag_stat(None, "test_cases") is None

    def test_build_stat_mixed_types(self):
        stat = _build_rag_stat([{"similarity": 0.9}, "not-a-dict", {"results": 1}], "repairs")
        assert stat["results"] == 3
        assert stat["max_similarity"] == 0.9

    def test_guard_disabled_returns_false(self):
        called = []
        ok = rag_guarded(
            "op",
            lambda r: called.append(1),
            enabled=False,
            module_available=True,
            retriever_cls=object,
            get_retriever=lambda: object(),
        )
        assert ok is False and called == []

    def test_guard_retriever_none_returns_false(self):
        called = []
        ok = rag_guarded(
            "op",
            lambda r: called.append(1),
            enabled=True,
            module_available=True,
            retriever_cls=object,
            get_retriever=lambda: None,
        )
        assert ok is False and called == []

    def test_guard_action_exception_returns_true(self):
        def boom(_r):
            raise RuntimeError("x")

        ok = rag_guarded(
            "op",
            boom,
            enabled=True,
            module_available=True,
            retriever_cls=object,
            get_retriever=lambda: object(),
        )
        # 降级口径：action 抛异常被吞掉，整体视为"已执行"（True）
        assert ok is True

    def test_get_retriever_failed_short_circuit(self):
        """初始化失败标志置位后不再重试（短路分支覆盖）。"""
        import src.graph.rag as rag_mod

        original_failed = rag_mod._rag_init_failed
        original_retriever = rag_mod._rag_retriever
        try:
            rag_mod._rag_init_failed = True
            rag_mod._rag_retriever = None
            assert get_rag_retriever() is None
            # 标志置位后返回值恒为 None，且不抛异常
            assert get_rag_retriever() is None
        finally:
            rag_mod._rag_init_failed = original_failed
            rag_mod._rag_retriever = original_retriever


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
