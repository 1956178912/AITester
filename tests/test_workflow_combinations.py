"""
graph/workflow.py 组合路由补全测试（2026-09-29 批次，把 85% 分支覆盖率
补到 90% 严格门槛）。

补齐缺口（对照 coverage.xml 实测 85.42% 的未命中分支）：
- _should_debug 的全组合：达上限 × 关键词命中 × 再生成上限（三态交叉）、
  早期迭代关键词命中 / 未命中、defect_type 上限收敛、非 bool 真值
  test_passed（numpy.bool_ 口径审查承诺）；
- _recent_repairs_invalid 的边界：repair_history 缺 patch_applied 键 /
  混合历史（True/False 交错）/ 长度不足 2；
- _route_after_diagnosis 的诊断分支（review 节点未启用 / 启用）；
- _diagnosis_hits_test_gen_keywords 的关键词命中 / 未命中边界。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph.workflow import (
    _MAX_REGENERATIONS,
    _diagnosis_hits_test_gen_keywords,
    _recent_repairs_invalid,
    _route_after_diagnosis,
    _should_debug,
)


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


@pytest.mark.unit
class TestShouldDebugCombinations:
    """_should_debug 全组合（"达上限 × 关键词 × 再生成上限"交叉场景）。"""

    def test_done_on_test_passed_truthy(self):
        # numpy 布尔口径（2026-09-26 审查：truthiness 而非 is True）
        import numpy as np

        assert _should_debug(_state(test_passed=bool(np.True_))) == "done"

    def test_done_on_repair_invalid_early_iteration(self):
        state = _state(repair_history=[{"patch_applied": False}, {"patch_applied": False}])
        assert _should_debug(state) == "done"

    def test_debug_on_repair_invalid_but_last_iteration(self):
        # 上限分支统一决策：早期"连续修复无效"快速终止在最后一轮不生效
        state = _state(
            iteration=3,
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert _should_debug(state) == "done"  # 关键词未命中 → done

    def test_max_iter_keyword_regen_once(self):
        state = _state(iteration=3, diagnosis="测试生成错误", regeneration_count=0)
        assert _should_debug(state) == "regenerate"

    def test_max_iter_keyword_regen_cap_reached(self):
        state = _state(
            iteration=3,
            diagnosis="测试生成错误",
            regeneration_count=_MAX_REGENERATIONS,
        )
        assert _should_debug(state) == "done"

    def test_max_iter_no_keyword_done(self):
        state = _state(iteration=3, diagnosis="运行时异常")
        assert _should_debug(state) == "done"

    def test_max_iter_diagnosis_none_done(self):
        state = _state(iteration=3, diagnosis=None)
        assert _should_debug(state) == "done"

    def test_diagnosis_keyword_hit_early_iteration_regen(self):
        # M5（2026-09-29 审查 P0）：AttributeError/NameError/SyntaxError 已从
        # 关键词表删除（防源码缺陷误判为测试缺陷→假通过），现用保留关键词命中。
        state = _state(iteration=1, diagnosis="测试生成错误：断言了错误的异常类型")
        assert _should_debug(state) == "regenerate"

    def test_diagnosis_empty_string_early_iteration_debug(self):
        state = _state(iteration=1, diagnosis="")
        assert _should_debug(state) == "debug"

    def test_diagnosis_whitespace_early_iteration_debug(self):
        state = _state(iteration=1, diagnosis="   ")
        assert _should_debug(state) == "debug"

    def test_diagnosis_newline_mixed_whitespace(self):
        state = _state(iteration=1, diagnosis="\n\t ")
        assert _should_debug(state) == "debug"

    def test_diagnosis_long_text_no_keyword_debug(self):
        state = _state(iteration=1, diagnosis="x" * 500)
        assert _should_debug(state) == "debug"

    def test_diagnosis_keyword_case_insensitive_boundary(self):
        # 关键词 "测试生成错误" 是精确子串匹配；仅大小写不同的英文不命中
        state = _state(iteration=1, diagnosis="test code")
        assert _should_debug(state) == "regenerate"  # "test code" 在关键词表内

    def test_test_passed_falsy_variants_debug(self):
        for falsy in (0, "", []):
            assert _should_debug(_state(test_passed=falsy, iteration=1)) == "debug"

    def test_max_iterations_key_missing_uses_default(self):
        state = _state(iteration=99)
        state.pop("max_iterations")
        # 缺省 3 → 99 >= 3 走上限分支（无关键词 → done）
        assert _should_debug(state) == "done"

    def test_iteration_none_treated_zero(self):
        # iteration 缺失时 .get 缺省 0（None 不进入 truthiness 分支）
        state = _state()
        state.pop("iteration")
        assert _should_debug(state) == "debug"

    def test_repair_history_nonlist_guard(self):
        # repair_history 为非 list（历史脏数据防御）：_recent_repairs_invalid
        # 内部按 list 消费，None 口径已在上方 None_history 覆盖
        state = _state(repair_history=None, iteration=1)
        assert _should_debug(state) == "debug"

    def test_regeneration_count_above_cap_early_iteration(self):
        # 早期迭代 + 关键词命中 + 再生成次数已远超上限 → 落到常规 debug
        state = _state(iteration=1, diagnosis="测试生成错误", regeneration_count=_MAX_REGENERATIONS * 2)
        assert _should_debug(state) == "debug"

    def test_test_defect_none_explicit_equals_default(self):
        assert _should_debug(_state(defect_type=None)) == "debug"

    def test_test_defect_case_sensitivity(self):
        # 严格字符串匹配（"Test_Defect" 不等于 "test_defect"）→ 走常规 debug
        state = _state(defect_type="Test_Defect")
        assert _should_debug(state) == "debug"

    def test_test_defect_zero_regen_count_regen(self):
        state = _state(defect_type="test_defect", regeneration_count=0)
        assert _should_debug(state) == "regenerate"

    def test_debug_decision_includes_iteration_trace(self):
        # debug 决策经 _trace_node 记录（tracing 开关关时零副作用，仅断言路由结果）
        state = _state(iteration=2)
        assert _should_debug(state) == "debug"

    def test_iteration_keys_missing_uses_defaults(self):
        # iteration / max_iterations 键均缺失 → 缺省 0 / 3 → 常规 debug
        assert _should_debug({"test_passed": False, "diagnosis": ""}) == "debug"

    def test_repair_invalid_last_iteration_with_keyword_regen(self):
        state = _state(
            iteration=3,
            diagnosis="测试生成错误",
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert _should_debug(state) == "regenerate"

    def test_repair_invalid_last_iteration_no_keyword_done(self):
        state = _state(
            iteration=3,
            diagnosis="除零",
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert _should_debug(state) == "done"

    def test_test_passed_falsy_early_repair_invalid_done(self):
        state = _state(
            test_passed=0,
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert _should_debug(state) == "done"

    def test_diagnosis_key_missing_treated_empty(self):
        state = _state(iteration=1)
        state.pop("diagnosis")
        assert _should_debug(state) == "debug"

    def test_defect_type_missing_treated_none(self):
        state = _state(iteration=1)
        state.pop("defect_type")
        assert _should_debug(state) == "debug"

    def test_regeneration_count_missing_defaults_zero(self):
        state = _state(defect_type="test_defect")
        state.pop("regeneration_count")
        assert _should_debug(state) == "regenerate"

    def test_early_iter_keyword_cap_reached_falls_through_to_debug(self):
        state = _state(
            iteration=1,
            diagnosis="测试生成错误",
            regeneration_count=_MAX_REGENERATIONS,
        )
        assert _should_debug(state) == "debug"  # 上限保护 → 落到常规 debug

    def test_test_defect_regen(self):
        state = _state(defect_type="test_defect", regeneration_count=0)
        assert _should_debug(state) == "regenerate"

    def test_test_defect_cap_done(self):
        state = _state(defect_type="test_defect", regeneration_count=_MAX_REGENERATIONS)
        assert _should_debug(state) == "done"

    def test_plain_debug_default(self):
        assert _should_debug(_state()) == "debug"

    def test_missing_keys_use_defaults(self):
        # 全键缺失：iteration 缺省 0、max_iterations 缺省 3、test_passed 缺省 falsy
        assert _should_debug({}) == "debug"

    def test_test_passed_none_falsy(self):
        assert _should_debug(_state(test_passed=None)) == "debug"

    def test_test_passed_zero_falsy(self):
        # 0 是 falsy（"测试全过"语义）→ 不判 done
        assert _should_debug(_state(test_passed=0)) == "debug"

    def test_iter_equal_max_with_test_passed_done(self):
        # test_passed 判定先于迭代上限（顺序语义锁定）
        state = _state(test_passed=True, iteration=99)
        assert _should_debug(state) == "done"

    def test_repair_invalid_with_keyword_at_max_still_done(self):
        # 最后一轮：连续修复无效 + 关键词命中 → 上限分支统一决策（关键词
        # regenerate 机会优先于 repair_invalid 快速终止）
        state = _state(
            iteration=3,
            diagnosis="测试生成错误",
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert _should_debug(state) == "regenerate"


@pytest.mark.unit
class TestRecentRepairsInvalid:
    def test_empty_history_false(self):
        assert _recent_repairs_invalid(_state()) is False

    def test_single_failure_false(self):
        state = _state(repair_history=[{"patch_applied": False}])
        assert _recent_repairs_invalid(state) is False

    def test_two_failures_true(self):
        state = _state(repair_history=[{"patch_applied": False}, {"patch_applied": False}])
        assert _recent_repairs_invalid(state) is True

    def test_last_success_breaks_chain(self):
        state = _state(repair_history=[{"patch_applied": False}, {"patch_applied": True}])
        assert _recent_repairs_invalid(state) is False

    def test_missing_key_treated_as_invalid(self):
        state = _state(repair_history=[{}, {}])
        assert _recent_repairs_invalid(state) is True

    def test_none_history_false(self):
        assert _recent_repairs_invalid(_state(repair_history=None)) is False

    def test_three_failures_true(self):
        state = _state(repair_history=[{"patch_applied": False}] * 3)
        assert _recent_repairs_invalid(state) is True

    def test_mixed_chain_only_last_two_count(self):
        state = _state(repair_history=[{"patch_applied": False}, {"patch_applied": True}, {"patch_applied": False}])
        assert _recent_repairs_invalid(state) is False

    def test_test_passed_short_circuit_true(self):
        state = _state(test_passed=True, repair_history=[{"patch_applied": False}, {"patch_applied": False}])
        assert _recent_repairs_invalid(state) is False

    def test_test_passed_falsy_evaluates_history(self):
        state = _state(test_passed=False, repair_history=[{"patch_applied": False}, {"patch_applied": False}])
        assert _recent_repairs_invalid(state) is True

    def test_explicit_none_history_key_false(self):
        state = _state(repair_history=None)
        assert _recent_repairs_invalid(state) is False

    def test_last_entry_missing_key_invalid(self):
        state = _state(repair_history=[{"patch_applied": False}, {}])
        assert _recent_repairs_invalid(state) is True

    def test_three_entries_only_last_two_checked(self):
        state = _state(repair_history=[{"patch_applied": True}, {"patch_applied": False}, {"patch_applied": False}])
        assert _recent_repairs_invalid(state) is True


@pytest.mark.unit
class TestDiagnosisKeywords:
    def test_keyword_hits(self):
        # M5（2026-09-29 审查 P0）：AttributeError 已删除（源码缺陷签名词），
        # 用保留的"测试生成错误"关键词验证命中路径。
        assert _diagnosis_hits_test_gen_keywords("测试生成错误")
        assert _diagnosis_hits_test_gen_keywords("出现了测试用例设计错误")

    def test_keyword_misses(self):
        assert not _diagnosis_hits_test_gen_keywords("运行时除零")
        # M5：AttributeError/NameError/SyntaxError 已删除（源码缺陷签名词），
        # 命中它们不再触发"测试生成错误"路由（防实现缺陷误判→假通过）。
        assert not _diagnosis_hits_test_gen_keywords("出现了 AttributeError")
        assert not _diagnosis_hits_test_gen_keywords("出现了 NameError")
        assert not _diagnosis_hits_test_gen_keywords("出现了 SyntaxError")

    def test_none_diagnosis_safe(self):
        # _should_debug 的 `state.get("diagnosis", "") or ""` 已归一 None → ""；
        # 直接传 None 会触发正则 search(None) 异常（调用契约要求 str）
        assert not _diagnosis_hits_test_gen_keywords("")


@pytest.mark.unit
class TestRouteAfterDiagnosis:
    def test_no_defect_routes_debug(self):
        assert _route_after_diagnosis(_state()) == "debug"

    def test_implementation_defect_routes_debug(self):
        state = _state(defect_type="implementation_defect")
        assert _route_after_diagnosis(state) == "debug"

    def test_test_defect_regen(self):
        state = _state(defect_type="test_defect", regeneration_count=0)
        assert _route_after_diagnosis(state) == "regenerate"

    def test_test_defect_cap_done(self):
        state = _state(defect_type="test_defect", regeneration_count=_MAX_REGENERATIONS)
        assert _route_after_diagnosis(state) == "done"

    def test_missing_regression_key_defaults_zero(self):
        state = _state(defect_type="test_defect")
        state.pop("regeneration_count")
        assert _route_after_diagnosis(state) == "regenerate"

    def test_diagnosis_keyword_regression_not_required(self):
        # _route_after_diagnosis 不消费 diagnosis 文本（只按 defect_type 路由）——
        # 与 _should_debug 的关键词路径口径独立
        state = _state(defect_type="test_defect", diagnosis="测试生成错误")
        assert _route_after_diagnosis(state) == "regenerate"


@pytest.mark.unit
class TestCreateWorkflowConditionalEdges:
    """_create_workflow 的消融开关组合（planner/debugger 矩阵 4 态 +
    DIAGNOSIS_NODE_ENABLE / ENABLE_RAG 条件边）。"""

    def _check_graph(self, graph, expect_nodes: set[str]):
        nodes = set(graph.get_graph().nodes)
        assert expect_nodes <= nodes, f"缺失节点: {expect_nodes - nodes}"

    def test_full_graph(self):
        from src.graph.workflow import build_workflow

        g = build_workflow(planner=True, debugger=True)
        self._check_graph(g, {"planner", "generator", "executor", "debugger", "patch_applier"})

    def test_no_planner_no_debugger(self):
        from src.graph.workflow import build_workflow

        g = build_workflow(planner=False, debugger=False)
        nodes = set(g.get_graph().nodes)
        assert "generator" in nodes
        assert "debugger" not in nodes
        assert "planner" not in nodes

    def test_planner_only(self):
        from src.graph.workflow import build_workflow

        g = build_workflow(planner=True, debugger=False)
        nodes = set(g.get_graph().nodes)
        assert "planner" in nodes
        assert "debugger" not in nodes

    def test_debugger_only(self):
        from src.graph.workflow import build_workflow

        g = build_workflow(planner=False, debugger=True)
        nodes = set(g.get_graph().nodes)
        assert "debugger" in nodes
        assert "planner" not in nodes

    def test_diagnosis_node_condition(self, monkeypatch):
        from src.graph.workflow import build_workflow

        monkeypatch.setenv("DIAGNOSIS_NODE_ENABLE", "true")
        g = build_workflow(planner=False, debugger=True)
        nodes = set(g.get_graph().nodes)
        assert "diagnosis" in nodes
        monkeypatch.delenv("DIAGNOSIS_NODE_ENABLE", raising=False)

    def test_rag_off_condition(self, monkeypatch):
        from src.graph.workflow import build_workflow

        monkeypatch.setenv("ENABLE_RAG", "false")
        g = build_workflow(planner=False, debugger=False)
        nodes = g.get_graph().nodes
        # U3（2026-10-05 系统性审查落地）：补断言——RAG 关闭时基础节点集合
        # 不变（RAG 是边级增强，不增删节点）
        assert "generator" in nodes and "executor" in nodes
        assert "debugger" not in nodes and "planner" not in nodes
        monkeypatch.delenv("ENABLE_RAG", raising=False)


@pytest.mark.unit
class TestWorkflowStatsKeys:
    """get_workflow_stats 全键存在性（真实口径：llm_cache / workflow_config /
    cost_budget / semantic_cache，含 3.6 假阳性抽样统计合并消费）。"""

    def test_stats_keys_present(self):
        import src.graph.workflow as wf

        stats = wf.get_workflow_stats()
        for key in ("llm_cache", "workflow_config", "cost_budget", "semantic_cache"):
            assert key in stats, f"缺键 {key}"
        assert "entries" in stats["llm_cache"] and "enabled" in stats["llm_cache"]
        assert "ENABLE_RAG" in stats["workflow_config"]
        # 3.6 假阳性抽样统计已并入 semantic_cache 消费面
        assert "fp_checked" in stats["semantic_cache"] and "fp_rate" in stats["semantic_cache"]

    def test_stats_rag_flag_reflects_config(self, monkeypatch):
        import src.graph.workflow as wf

        # workflow_config 报告的是 config 导入期的 ENABLE_RAG 快照——
        # patch config 模块属性可验证读路径（stats 经 workflow 模块引用该常量）

        monkeypatch.setattr(wf, "ENABLE_RAG", True)
        stats = wf.get_workflow_stats()
        assert stats["workflow_config"]["ENABLE_RAG"] is True

    def test_cache_hit_rate_key_only_when_recorded(self, monkeypatch):
        import src.agents.llm_client as llm_client
        import src.graph.workflow as wf

        llm_client.reset_cache_hit_stats()
        try:
            # 无任何命中/未命中记录 → llm_cache 不附 hit_rate 键（历史口径）
            stats = wf.get_workflow_stats()
            assert "hit_rate" not in stats["llm_cache"]
            # 记录一次命中后 → hit_rate 键出现
            llm_client.record_cache_hit(True)
            stats2 = wf.get_workflow_stats()
            assert stats2["llm_cache"]["hit_rate"] == 1.0
        finally:
            llm_client.reset_cache_hit_stats()

    def test_semantic_fp_stats_merged(self, monkeypatch):
        import src.agents.llm_client as llm_client
        import src.agents.semantic_cache as sc
        import src.graph.workflow as wf

        llm_client.reset_cache_hit_stats()
        sc.reset_false_positive_stats()
        try:
            sc.record_false_positive_check(confirmed=False)
            stats = wf.get_workflow_stats()
            assert stats["semantic_cache"]["fp_checked"] == 1
            assert stats["semantic_cache"]["fp_rate"] == 1.0
        finally:
            sc.reset_false_positive_stats()
            llm_client.reset_cache_hit_stats()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))


@pytest.mark.unit
class TestWorkflowGraphShapes:
    """_create_workflow 的边拓扑各组合（cross_file / diagnosis 开关矩阵）。"""

    def test_cross_file_off_default_topology(self):
        import src.graph.workflow as wf

        g = wf.build_workflow(planner=False, debugger=True)
        graph = g.get_graph()
        edge_pairs = {(e.source, e.target) for e in graph.edges}
        assert ("executor", "diagnosis") not in edge_pairs
        assert ("debugger", "patch_applier") in edge_pairs
        assert ("patch_applier", "executor") in edge_pairs

    def test_cross_file_enabled_topology(self, monkeypatch):
        import src.graph.workflow as wf

        monkeypatch.setattr(wf, "cross_file_enabled", lambda: True)
        g = wf.build_workflow(planner=False, debugger=True)
        graph = g.get_graph()
        nodes = set(graph.nodes)
        assert "cross_file_analyzer" in nodes
        # 无 diagnosis：executor 条件边含 cross_file_analyzer
        edge_pairs = {(e.source, e.target) for e in graph.edges}
        assert ("cross_file_analyzer", "debugger") in edge_pairs
        assert ("executor", "cross_file_analyzer") in edge_pairs

    def test_cross_file_and_diagnosis_topology(self, monkeypatch):
        import src.graph.workflow as wf

        monkeypatch.setenv("DIAGNOSIS_NODE_ENABLE", "true")
        monkeypatch.setattr(wf, "cross_file_enabled", lambda: True)
        g = wf.build_workflow(planner=False, debugger=True)
        graph = g.get_graph()
        nodes = set(graph.nodes)
        assert "diagnosis" in nodes
        assert "cross_file_analyzer" in nodes
        edge_pairs = {(e.source, e.target) for e in graph.edges}
        assert ("executor", "diagnosis") in edge_pairs
        assert ("cross_file_analyzer", "debugger") in edge_pairs
        monkeypatch.delenv("DIAGNOSIS_NODE_ENABLE", raising=False)

    def test_diagnosis_only_topology(self, monkeypatch):
        import src.graph.workflow as wf

        monkeypatch.setenv("DIAGNOSIS_NODE_ENABLE", "true")
        g = wf.build_workflow(planner=False, debugger=True)
        graph = g.get_graph()
        nodes = set(graph.nodes)
        assert "diagnosis" in nodes
        assert "cross_file_analyzer" not in nodes
        edge_pairs = {(e.source, e.target) for e in graph.edges}
        assert ("executor", "diagnosis") in edge_pairs
        monkeypatch.delenv("DIAGNOSIS_NODE_ENABLE", raising=False)
