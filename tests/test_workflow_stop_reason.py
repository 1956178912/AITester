"""StopReason / determine_stop_reason 全分支覆盖测试（2026-10-02 审查）。

背景：`src/graph/workflow.py` 的 `determine_stop_reason`（O27 单点判定）
落地后无独立单测——`graph/workflow.py` 分支覆盖从 92% 跌至 74%，
`scripts/check_branch_coverage.py` 的 90% 严格门槛因此变红（CI 会拦）。
本文件对该纯函数的 11 个 StopReason 分支逐一锁定判定优先级，
不依赖 LLM / 图执行（纯数据输入 → 枚举输出），CI 可安全运行。

判定优先级（首个命中即返回，见 determine_stop_reason docstring）：
  test_passed → budget_exceeded → regression_detected
  → (test_defect & 再生成达上限) → iteration 上限 → 修复无效
  → 诊断关键词（早/晚）→ UNKNOWN
"""

from __future__ import annotations

from src.graph.workflow import (
    _MAX_REGENERATIONS,
    StopReason,
    determine_stop_reason,
)


def _base_state(**overrides) -> dict:
    """最小 state：不命中任何终止条件（应落到 UNKNOWN 或关键词分支）。"""
    state = {
        "test_passed": False,
        "iteration": 0,
        "max_iterations": 3,
        "diagnosis": "",
        "defect_type": None,
        "regeneration_count": 0,
        "repair_history": [],
        "budget_exceeded": False,
        "regression_detected": False,
    }
    state.update(overrides)
    return state


class TestDetermineStopReasonBranches:
    """determine_stop_reason 11 个枚举分支逐一覆盖。"""

    def test_test_passed_first_priority(self):
        """test_passed=True 最优先（甚至压过 budget/regression）。"""
        state = _base_state(test_passed=True, budget_exceeded=True, regression_detected=True)
        assert determine_stop_reason(state) is StopReason.TEST_PASSED

    def test_budget_exceeded_second_priority(self):
        """预算超限优先于回归检测与迭代上限。"""
        state = _base_state(budget_exceeded=True, regression_detected=True, iteration=99)
        assert determine_stop_reason(state) is StopReason.BUDGET_EXCEEDED

    def test_regression_detected_third_priority(self):
        """回归检测优先于 test_defect 上限与迭代上限。"""
        state = _base_state(
            regression_detected=True,
            defect_type="test_defect",
            regeneration_count=_MAX_REGENERATIONS,
            iteration=99,
        )
        assert determine_stop_reason(state) is StopReason.REGRESSION_DETECTED

    def test_test_defect_regen_cap(self):
        """test_defect 且再生成已达上限 → TEST_DEFECT_REGEN_CAP。"""
        state = _base_state(
            defect_type="test_defect",
            regeneration_count=_MAX_REGENERATIONS,
            iteration=0,  # 未达迭代上限（验证该分支先于迭代上限判定）
        )
        assert determine_stop_reason(state) is StopReason.TEST_DEFECT_REGEN_CAP

    def test_test_defect_below_cap_falls_through(self):
        """test_defect 但再生成未达上限 → 不命中该分支，继续向下判定。"""
        state = _base_state(
            defect_type="test_defect",
            regeneration_count=0,
            diagnosis="",  # 无关键词 → UNKNOWN
        )
        assert determine_stop_reason(state) is StopReason.UNKNOWN

    def test_max_iterations(self):
        """iteration >= max_iterations → MAX_ITERATIONS。"""
        state = _base_state(iteration=3, max_iterations=3, diagnosis="")
        assert determine_stop_reason(state) is StopReason.MAX_ITERATIONS

    def test_repair_invalid(self):
        """最近 2 次修复均未应用补丁 → REPAIR_INVALID（未达迭代上限）。"""
        state = _base_state(
            iteration=1,
            max_iterations=3,
            diagnosis="",
            repair_history=[{"patch_applied": False}, {"patch_applied": False}],
        )
        assert determine_stop_reason(state) is StopReason.REPAIR_INVALID

    def test_recent_repair_applied_falls_through(self):
        """最近修复有成功应用 → 不命中 REPAIR_INVALID，继续向下。"""
        state = _base_state(
            iteration=1,
            max_iterations=3,
            diagnosis="",
            repair_history=[{"patch_applied": False}, {"patch_applied": True}],
        )
        assert determine_stop_reason(state) is StopReason.UNKNOWN

    def test_keyword_early(self):
        """诊断关键词命中 + 早期迭代 → TEST_GEN_KEYWORD_EARLY。"""
        state = _base_state(iteration=1, max_iterations=3, diagnosis="测试生成错误")
        assert determine_stop_reason(state) is StopReason.TEST_GEN_KEYWORD_EARLY

    def test_keyword_late_branch_is_unreachable_dead_code(self):
        """锁定 TEST_GEN_KEYWORD_LATE 的可达性边界（审查发现的死分支）。

        判定顺序第 5 步（iteration >= max_iterations → MAX_ITERATIONS）
        先于第 7 步（关键词）执行；而第 7 步内层又要求 iteration < max
        才返回 EARLY、否则 LATE——但走到第 7 步时 iteration 必然 < max
        （否则已被第 5 步拦截），故 LATE 分支恒不可达。

        本用例断言当前实际语义（关键词 + 达上限 → MAX_ITERATIONS）。
        若未来调整判定优先级使 LATE 可达，本用例需同步更新——
        这正是"优先级顺序"被测试锁定的意图。
        """
        state = _base_state(iteration=0, max_iterations=0, diagnosis="测试生成错误")
        # 第 5 步先命中（0 >= 0）→ MAX_ITERATIONS，关键词分支不参与
        assert determine_stop_reason(state) is StopReason.MAX_ITERATIONS

        # 迭代未达上限 + 关键词命中 → 恒为 EARLY（LATE 不可达）
        early = _base_state(iteration=0, max_iterations=1, diagnosis="测试用例")
        assert determine_stop_reason(early) is StopReason.TEST_GEN_KEYWORD_EARLY
        # 枚举成员保留（对外契约），但当前无输入能产生该值
        assert StopReason.TEST_GEN_KEYWORD_LATE.value == "test_gen_diagnosis"

    def test_unknown_fallback(self):
        """无任何条件命中 → UNKNOWN 兜底。"""
        state = _base_state(diagnosis="普通诊断文本")
        assert determine_stop_reason(state) is StopReason.UNKNOWN

    def test_empty_state_defaults(self):
        """空 dict 输入不抛异常（所有 .get 均有默认值）。"""
        assert determine_stop_reason({}) is StopReason.UNKNOWN

    def test_none_diagnosis_and_none_repair_history(self):
        """diagnosis=None / repair_history=None 的 None 容错。"""
        state = _base_state(diagnosis=None, repair_history=None, iteration=1)
        assert determine_stop_reason(state) is StopReason.UNKNOWN


class TestStopReasonEnumIntegrity:
    """StopReason 枚举契约：值唯一 + 与路由层消费口径一致。"""

    def test_values_unique(self):
        values = [r.value for r in StopReason]
        assert len(values) == len(set(values)), f"枚举值重复: {values}"

    def test_all_values_nonempty_strings(self):
        for r in StopReason:
            assert isinstance(r.value, str) and r.value, f"{r.name} 的 value 非法"

    def test_stop_reason_written_to_state_shape(self):
        """路由层写 state["stop_reason"] 的值必须是枚举 .value（str）。"""
        state = _base_state(test_passed=True)
        reason = determine_stop_reason(state)
        assert isinstance(reason.value, str)
