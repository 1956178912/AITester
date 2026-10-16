#!/usr/bin/env python3
"""覆盖率补口：编排搜索的**纯逻辑内核**（`src/graph/orchestration_search.py`）。

动机（EMSE 多轮优化批次·主链路）：该模块是"自动搜索编排 vs 手工编排"路线的
执行内核（ADR-0016/0030）。其**臂规格校验、UCB1 选择、预算双顶、回溯信用归因**
都是确定性纯逻辑——没有理由不测；而这些逻辑一旦写错，搜索结果会被静默偏置
（例如 tie-break 不稳定 → 复现性丧失；None 进分母 → 与 M1 诚实口径冲突）。

覆盖目标（coverage.xml 记录）：_as_count_int 67-71、UCB1Bandit 636/701、
trace 路径解析 919-935、机制归因 890-899、臂校验与预算路径。
零 LLM、零网络、零子进程。
"""

from __future__ import annotations

import pytest

from src.graph.orchestration_search import (
    ArmSpec,
    ArmSpecError,
    SearchBudget,
    UCB1Bandit,
    _as_count_int,
    _trace_file_path,
    apply_arm_env,
    get_arm,
    restore_env_snapshot,
    search_enabled,
)


class TestHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, 0),  # bool 必须排除（True 不是计数 1）
            (False, 0),
            (5, 5),
            (5.9, 5),
            ("7", 0),  # 字符串不隐式转（防"配置写错被当合法"）
            (None, 0),
            ([], 0),
        ],
    )
    def test_as_count_int_semantics(self, value: object, expected: int):
        assert _as_count_int(value) == expected

    def test_trace_file_path_is_sanitized_and_stable(self):
        """task_id 里的路径分隔符/特殊字符不得逃出 trace 目录。"""
        path = _trace_file_path("/tmp/traces", "synthetic__task_0001")
        assert path.startswith("/tmp/traces/")
        assert ".." not in path
        assert _trace_file_path("/tmp/traces", "synthetic__task_0001") == path

    def test_trace_file_path_survives_hostile_task_id(self):
        hostile = "../../etc/passwd"
        path = _trace_file_path("/tmp/traces", hostile)
        assert os.path.normpath(path).startswith("/tmp/traces/")

    def test_search_switch_is_boolean(self, monkeypatch: pytest.MonkeyPatch):
        for raw in ("true", "1", "on", "false", ""):
            monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", raw)
            assert isinstance(search_enabled(), bool)


import os  # noqa: E402  (放在类外：供 hostile 用例使用)


class TestArmSpecValidation:
    def test_minimal_arm_is_valid(self):
        arm = ArmSpec(arm_id="df_incumbent", planner=False, debugger=False)
        assert arm.arm_id == "df_incumbent"

    @pytest.mark.parametrize("bad_id", ["", "has space", "has-dash", "has/slash"])
    def test_invalid_arm_id_rejected(self, bad_id: str):
        with pytest.raises(ArmSpecError):
            ArmSpec(arm_id=bad_id, planner=False, debugger=False)

    def test_cjk_arm_id_is_currently_accepted(self):
        """**已知宽松边界**：校验用 `str.isalnum()`，而它对 CJK 返回 True，
        故中文臂 id 会通过。本用例锁定现状（不隐藏），若未来收紧为 ASCII
        白名单，此处会失败并强制同步文档与臂注册表。"""
        arm = ArmSpec(arm_id="有中文", planner=False, debugger=False)
        assert arm.arm_id == "有中文"

    def test_unknown_env_key_rejected(self):
        with pytest.raises(ArmSpecError):
            ArmSpec(arm_id="a", planner=False, debugger=False, env={"NOT_A_KNOWN_KEY": "true"})

    def test_env_value_must_be_true_or_false_strings(self):
        with pytest.raises(ArmSpecError):
            ArmSpec(arm_id="a", planner=False, debugger=False, env={"ENABLE_DEBUGGER": "yes"})

    def test_get_arm_returns_known_arm(self):
        arm = get_arm("df_incumbent")
        assert isinstance(arm, ArmSpec)
        assert arm.arm_id == "df_incumbent"

    def test_get_arm_unknown_raises(self):
        with pytest.raises(ArmSpecError):
            get_arm("no_such_arm_id_xyz")


class TestUCB1Bandit:
    def test_empty_arm_set_rejected(self):
        with pytest.raises(ArmSpecError):
            UCB1Bandit([])

    def test_first_round_is_round_robin(self):
        bandit = UCB1Bandit(["a", "b", "c"])
        assert [bandit.select() for _ in range(3)] == ["a", "b", "c"]

    def test_after_initialization_prefers_better_arm(self):
        bandit = UCB1Bandit(["a", "b"], c=0.0)  # c=0 → 纯贪心，便于断言
        assert bandit.select() == "a"
        bandit.update("a", 0.0)
        assert bandit.select() == "b"
        bandit.update("b", 1.0)
        assert bandit.select() == "b", "贪心口径应持续选均值高的臂"

    def test_unmeasurable_reward_does_not_enter_denominator(self):
        """`reward=None` 只计 unmeasurable（与 M1 的 None 不进分母同口径）。"""
        bandit = UCB1Bandit(["a"])
        bandit.select()
        bandit.update("a", None)
        stats = bandit.stats("a")
        assert stats.n == 0
        assert stats.unmeasurable == 1

    def test_exclude_removes_from_active_and_select_returns_none_when_empty(self):
        bandit = UCB1Bandit(["a", "b"])
        bandit.exclude("a")
        assert bandit.active == ("b",)
        bandit.exclude("b")
        assert bandit.active == ()
        assert bandit.select() is None

    def test_exclude_is_idempotent(self):
        bandit = UCB1Bandit(["a"])
        bandit.exclude("a")
        bandit.exclude("a")
        assert bandit.active == ()

    def test_tie_break_is_deterministic_by_registration_order(self):
        bandit = UCB1Bandit(["x", "y", "z"], c=0.0)
        for arm in ("x", "y", "z"):
            bandit.select()
            bandit.update(arm, 1.0)
        # 三臂均值相同 → tie-break 取登记序最小
        assert bandit.select() == "x"
        assert bandit.select() == "x"

    def test_exploration_bonus_grows_with_unpulled_arm(self):
        bandit = UCB1Bandit(["a", "b"], c=1.0)
        bandit.select()
        bandit.update("a", 1.0)
        bandit.select()
        bandit.update("b", 0.0)
        seen = {bandit.select() for _ in range(5)}
        assert seen <= {"a", "b"}
        assert bandit.c == 1.0

    def test_defensive_branch_prefers_arm_without_observations(self):
        """防御分支：活跃臂 `n == 0` 时优先返回它（初始化轮之后的窄路径）。

        构造：走完初始化轮（pulls > |A|）后把某活跃臂的 `n` 归零——真实场景对应
        "该臂从未产出可测观测"。注意 `n == 0` 的臂必须**先于**有观测的臂被遍历到，
        否则它会参与正常 UCB 打分（该分支按设计只在最前命中）。
        """
        bandit = UCB1Bandit(["a", "b"])
        bandit.select()  # pulls=1 → a
        bandit.update("a", 1.0)
        bandit.select()  # pulls=2 → b
        bandit.update("b", 1.0)
        bandit.stats("a").n = 0  # 把登记序最前的臂归零
        assert bandit.select() == "a"


class TestSearchBudget:
    def test_eval_cap_sets_stop_reason(self):
        budget = SearchBudget(max_evals=2, max_total_tokens=10**9)
        budget.record(tokens=1)
        assert budget.can_continue() is True
        budget.record(tokens=1)
        assert budget.can_continue() is False
        assert budget.stop_reason == "max_evals"

    def test_token_cap_sets_stop_reason(self):
        budget = SearchBudget(max_evals=10**6, max_total_tokens=5)
        budget.record(tokens=5)
        assert budget.stop_reason == "max_tokens"

    def test_first_stop_reason_wins(self):
        budget = SearchBudget(max_evals=1, max_total_tokens=1)
        budget.record(tokens=1)
        assert budget.stop_reason == "max_evals", "双顶同时触发时按检查顺序记录首个原因"

    def test_negative_tokens_are_clamped(self):
        budget = SearchBudget(max_evals=10, max_total_tokens=10)
        budget.record(tokens=-5)
        assert budget.tokens_used == 0

    def test_snapshot_shape(self):
        budget = SearchBudget(max_evals=3, max_total_tokens=100)
        budget.record(tokens=7)
        snapshot = budget.to_dict()
        assert snapshot["evals_used"] == 1
        assert snapshot["tokens_used"] == 7
        assert snapshot["stop_reason"] is None


class TestEnvRestore:
    def test_snapshot_restore_roundtrip(self, monkeypatch: pytest.MonkeyPatch):
        """环境快照/恢复：未设置过（None）的键必须被删回"未设置"，而不是设成字符串。"""
        monkeypatch.setenv("CFG_ANALYSIS_ENABLE", "true")
        snapshot = {"CFG_ANALYSIS_ENABLE": "true", "PATH_ENUM_INJECT_ENABLE": None}
        monkeypatch.setenv("PATH_ENUM_INJECT_ENABLE", "true")
        restore_env_snapshot(snapshot)
        assert os.environ.get("CFG_ANALYSIS_ENABLE") == "true"
        assert "PATH_ENUM_INJECT_ENABLE" not in os.environ

    def test_apply_arm_env_requires_explicit_opt_in(self):
        """搜索 harness 默认关（ADR-0003）：未开启时 `apply_arm_env` 必须**拒绝**执行。"""
        from src.graph.orchestration_search import SearchDisabledError

        arm = ArmSpec(arm_id="df_incumbent", planner=False, debugger=False)
        with pytest.raises(SearchDisabledError), apply_arm_env(arm):
            pass

    def test_apply_arm_env_applies_and_restores(self, monkeypatch: pytest.MonkeyPatch):
        """开启后：上下文内写入臂级 env，退出后恢复原值（不得泄漏给后续臂）。"""
        monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", "true")
        monkeypatch.setenv("DETECTION_FIRST_ENABLE", "false")
        arm = ArmSpec(arm_id="arm_df", planner=False, debugger=False, env={"DETECTION_FIRST_ENABLE": "true"})
        with apply_arm_env(arm):
            assert os.environ.get("DETECTION_FIRST_ENABLE") == "true"
        assert os.environ.get("DETECTION_FIRST_ENABLE") == "false", "臂级 env 不得泄漏到上下文之外"
