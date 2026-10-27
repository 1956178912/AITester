"""编排自动搜索（bandit）测试——P1-A 落地（spec-p1a-bandit §9 的 7 组用例）。

覆盖（全部桩评估器，零 LLM / 零网络 / 零子进程）：
1. 信用分配正确性（构造轨迹：成功/失败/不可测三分支 + 机制归因映射）；
2. 预算封顶（eval / token 双顶，先到即停）；
3. 确定性（同 seed 双跑逐位一致；不同 seed 序列有异）；
4. 默认关零行为变化（主开关未设 → 公共入口拒绝且 env 快照不变）；
5. 臂空间约束与键名（16 臂唯一 id / 依赖 / SPEC 链一体 / 键名 ⊆ 已知集合）；
6. UCB1 数学性质（round-robin 初始化 / 恒优臂收敛 / 不可测臂排除）；
7. memoize（同 (arm, cell) 至多评估一次）+ 信用不耦合不变量。

沙箱纪律：--basetemp 用全新目录名；勿跑全量套件。
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from src.graph.orchestration_search import (
    ARM_REGISTRY,
    KNOWN_ARM_ENV_KEYS,
    ArmSpec,
    ArmSpecError,
    Cell,
    CellResult,
    OrchestrationSearch,
    SearchBudget,
    SearchDisabledError,
    apply_arm_env,
    assert_no_credit_coupling,
    attribute_mechanisms,
    establish_clean_baseline,
    get_arm,
    hindsight_credits,
    restore_env_snapshot,
    select_champion,
)

# ─── 公共脚手架 ──────────────────────────────────────────────────────────────


@pytest.fixture
def search_on(monkeypatch):
    """开启主开关（调用期读 env，monkeypatch 动态切换）。"""
    monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", "true")


@pytest.fixture
def search_off(monkeypatch):
    """确保主开关未设置（默认关口径）。"""
    monkeypatch.delenv("ORCHESTRATION_SEARCH_ENABLE", raising=False)


def _make_cells(n: int, task_prefix: str = "synthetic__t", seed: int = 42) -> list[Cell]:
    """构造 n 个 cell（task=None——桩评估器不触达任务对象）。"""
    return [Cell(task_id=f"{task_prefix}{i:04d}", seed=seed, task=None) for i in range(n)]


class StubEvaluator:
    """固定奖励表桩评估器（确定性；记录每次调用供 memoize/序列断言）。"""

    def __init__(
        self,
        rewards: dict[str, float | None] | None = None,
        tokens: dict[str, int] | None = None,
        default_reward: float | None = 0.0,
    ) -> None:
        self._rewards = rewards or {}
        self._tokens = tokens or {}
        self._default_reward = default_reward
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, arm: ArmSpec, cell: Cell) -> CellResult:
        self.calls.append((arm.arm_id, cell.task_id, cell.seed))
        return CellResult(
            arm_id=arm.arm_id,
            task_id=cell.task_id,
            seed=cell.seed,
            detection=self._rewards.get(arm.arm_id, self._default_reward),
            total_tokens=self._tokens.get(arm.arm_id, 1000),
            llm_calls=2,
            duration_s=1.5,
            trace_records=[],
        )


def _executor_event(iteration: int, decision: str, coverage: float | None = None) -> dict[str, Any]:
    """构造 executor trace 事件（实测 schema 子集）。"""
    output: dict[str, Any] = {"passed": decision == "PASS", "failed_cases": 0 if decision == "PASS" else 1}
    if coverage is not None:
        output["coverage"] = coverage
    return {"event": "node", "node": "executor", "decision": decision, "iteration": iteration, "output": output}


def _should_debug_event(reason: str) -> dict[str, Any]:
    """构造 _should_debug trace 事件。"""
    return {"event": "node", "node": "_should_debug", "decision": "regenerate", "output": {"reason": reason}}


def _patch_applier_event(decision: str) -> dict[str, Any]:
    """构造 patch_applier trace 事件。"""
    return {
        "event": "node",
        "node": "patch_applier",
        "decision": decision,
        "output": {"patch_applied": decision == "written"},
    }


def _generator_event(decision: str) -> dict[str, Any]:
    """构造 generator trace 事件。"""
    return {"event": "node", "node": "generator", "decision": decision, "output": {"generated_test_len": 900}}


# ─── 1. 信用分配正确性 ───────────────────────────────────────────────────────


class TestHindsightCredit:
    """规格 §9.1：信用分配正确性（构造轨迹 + 三分支 + 机制归因）。"""

    def test_success_branch_signals(self):
        """detection=1：S1 红证人 +0.4、S2 覆盖递增 +0.2、S3 补丁落地 +0.2、S4 被拒 −0.1。"""
        records = [
            _executor_event(0, "FAIL", coverage=50.0),  # S1: +0.4
            _patch_applier_event("written"),  # S3: +0.2
            _executor_event(1, "FAIL", coverage=70.0),  # S2: +0.2（70 > 50）
            _patch_applier_event("rejected"),  # S4: −0.1
        ]
        credits = hindsight_credits(records, 1.0)
        assert credits == pytest.approx([0.4, 0.2, 0.2, -0.1])

    def test_failure_branch_hindsight(self):
        """detection=0：推进步骤按 γ 保留正信用；负向信号不二次惩罚。"""
        records = [
            _executor_event(0, "FAIL", coverage=50.0),  # S1: 0.4 × γ
            _patch_applier_event("rejected"),  # S4: 0（失败不罚）
        ]
        credits = hindsight_credits(records, 0.0, gamma=0.5)
        assert credits == pytest.approx([0.2, 0.0])

    def test_none_detection_all_zero(self):
        """detection=None（不可测）：全部信用 0.0（不误报）。"""
        records = [_executor_event(0, "FAIL", coverage=50.0), _patch_applier_event("written")]
        assert hindsight_credits(records, None) == [0.0, 0.0]

    def test_regen_and_mutation_and_gate_signals(self):
        """S5 再生成 / S6 变异注入 / S7 门①命中在成功分支的信用。"""
        records = [
            _should_debug_event("specificity_gate_over_red"),  # S7: +0.1
            _generator_event("regenerated"),  # S5: +0.1
            {"event": "node", "node": "mutation_advisor", "decision": "injected", "output": {}},  # S6: +0.1
        ]
        credits = hindsight_credits(records, 1.0)
        assert credits == pytest.approx([0.1, 0.1, 0.1])

    def test_gamma_default_from_config(self, monkeypatch):
        """gamma=None 时读 config 常量（调用期读取，可 monkeypatch 覆盖）。"""
        import config as _config

        monkeypatch.setattr(_config, "ORCHESTRATION_SEARCH_HINDSIGHT_GAMMA", 0.25)
        records = [_executor_event(0, "FAIL")]
        assert hindsight_credits(records, 0.0) == pytest.approx([0.4 * 0.25])

    def test_red_erasure_scenario_step_level(self):
        """抹红场景（red_then_green ∧ detection=0）：步骤级公式仍给红证人/补丁
        步骤 hindsight 信用（已知局限——终局抹红由 final_state 旗标在报告层陈述）。"""
        records = [
            _executor_event(0, "FAIL"),  # 红证人
            _patch_applier_event("written"),  # 补丁落地（后续测试被再生成抹红）
            _generator_event("regenerated"),
        ]
        credits = hindsight_credits(records, 0.0, gamma=0.5)
        assert credits == pytest.approx([0.2, 0.1, 0.05])

    def test_attribute_mechanisms_mapping(self):
        """reason→mechanism 映射（仅聚合非零信用事件——零信用路由决策的效果
        由被触发的动作事件 S5 承载，规格 §3.4 语义）。"""
        arm = get_arm("df_incumbent")
        records = [
            _executor_event(0, "FAIL"),  # detection_first（臂开）: +0.4
            _should_debug_event("specificity_gate_over_red"),  # specificity_gate: +0.1
            _should_debug_event("detection_first_all_green"),  # 零信用（未命中信号）→ 跳过
            _should_debug_event("test_gen_diagnosis"),  # 零信用 → 跳过
            _should_debug_event("review_test_defect"),  # 零信用 → 跳过
            _patch_applier_event("written"),  # debugger: +0.2
            {
                "event": "node",
                "node": "mutation_advisor",
                "decision": "injected",
                "output": {},
            },  # mutation_advisor: +0.1
        ]
        credits = hindsight_credits(records, 1.0)
        totals = attribute_mechanisms(records, arm, credits)
        assert totals == {
            "detection_first": pytest.approx(0.4),
            "specificity_gate": pytest.approx(0.1),
            "debugger": pytest.approx(0.2),
            "mutation_advisor": pytest.approx(0.1),
        }

    def test_attribute_mechanisms_base_without_detection_first(self):
        """未开检出优先的臂：红证人归 generator_base（非 detection_first）。"""
        arm = get_arm("plain_llm_floor")
        records = [_executor_event(0, "FAIL")]
        credits = hindsight_credits(records, 1.0)
        totals = attribute_mechanisms(records, arm, credits)
        assert totals == {"generator_base": pytest.approx(0.4)}


# ─── 2. 预算封顶 ─────────────────────────────────────────────────────────────


class TestBudgetCap:
    """规格 §9.2：eval / token 双顶，先到即停。"""

    def test_token_cap_stops_first(self, search_on):
        """高 token 桩：在 max_total_tokens 处停（stop_reason=max_tokens）。"""
        arms = ARM_REGISTRY
        cells = _make_cells(36)
        stub = StubEvaluator(tokens={arm.arm_id: 10_000 for arm in arms})  # 16 臂 × 1 万 = 16 万/轮
        budget = SearchBudget(max_evals=240, max_total_tokens=50_000)
        search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=42, evaluator=stub)
        report = search.run()
        assert report["budget"]["stop_reason"] == "max_tokens"
        assert report["budget"]["tokens_used"] >= 50_000
        assert report["budget"]["evals_used"] < 240

    def test_eval_cap_stops_first(self, search_on):
        """低 token 桩：在 max_evals 处停（stop_reason=max_evals）。"""
        arms = ARM_REGISTRY
        cells = _make_cells(36)
        stub = StubEvaluator(tokens={arm.arm_id: 10 for arm in arms})
        budget = SearchBudget(max_evals=20, max_total_tokens=1_500_000)
        search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=42, evaluator=stub)
        report = search.run()
        assert report["budget"]["stop_reason"] == "max_evals"
        assert report["budget"]["evals_used"] == 20

    def test_all_arms_excluded_records_reason(self, search_on):
        """全部臂退出（cell 耗尽）时 stop_reason=all_arms_excluded（非预算触顶）。"""
        arms = ARM_REGISTRY
        cells = _make_cells(2)  # 每臂最多 2 次新鲜评估
        stub = StubEvaluator()
        budget = SearchBudget(max_evals=240, max_total_tokens=1_500_000)
        search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=42, evaluator=stub)
        report = search.run()
        assert report["budget"]["stop_reason"] == "all_arms_excluded"
        assert all(stats["excluded_reason"] == "cells_exhausted" for stats in report["arm_stats"].values())


# ─── 3. 确定性 ───────────────────────────────────────────────────────────────


class TestDeterminism:
    """规格 §9.3：同 seed 双跑逐位一致（ts 除外）；不同 seed 序列有异。"""

    def _run_once(self, seed: int) -> dict:
        arms = ARM_REGISTRY
        cells = _make_cells(36)
        rewards = {arm.arm_id: (1.0 if i % 3 == 0 else 0.0) for i, arm in enumerate(arms)}
        stub = StubEvaluator(rewards=rewards, tokens={arm.arm_id: 100 * (i + 1) for i, arm in enumerate(arms)})
        budget = SearchBudget(max_evals=60, max_total_tokens=1_500_000)
        search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=seed, evaluator=stub)
        return search.run()

    def test_same_seed_identical(self, search_on):
        """同 seed 双跑：拉取序列、逐臂统计、champion 逐位一致。"""
        report_a = self._run_once(42)
        report_b = self._run_once(42)
        assert report_a["pull_sequence"] == report_b["pull_sequence"]
        assert report_a["arm_stats"] == report_b["arm_stats"]
        assert report_a["champion"] == report_b["champion"]
        assert report_a["rows"] == report_b["rows"]

    def test_different_seed_call_sequence_differs(self, search_on):
        """不同 seed 的 evaluator 调用序列不同（36 cell 洗牌随 seed 变化）。"""
        arms = ARM_REGISTRY
        cells = _make_cells(36)
        stub_a = StubEvaluator()
        stub_b = StubEvaluator()
        for stub, seed in ((stub_a, 42), (stub_b, 43)):
            budget = SearchBudget(max_evals=48, max_total_tokens=1_500_000)
            search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=seed, evaluator=stub)
            search.run()
        assert stub_a.calls != stub_b.calls


# ─── 4. 默认关零行为变化 ─────────────────────────────────────────────────────


class TestDefaultOff:
    """规格 §9.4：主开关未设 → 公共入口拒绝执行且 env 零变化。"""

    def test_public_entries_reject_when_disabled(self, search_off):
        """四个公共入口全部抛 SearchDisabledError。"""
        with pytest.raises(SearchDisabledError):
            OrchestrationSearch(
                arms=ARM_REGISTRY,
                cells=_make_cells(2),
                budget=SearchBudget(max_evals=4, max_total_tokens=1000),
                evaluator=StubEvaluator(),
            )
        with pytest.raises(SearchDisabledError):
            apply_arm_env(get_arm("df_incumbent"))
        with pytest.raises(SearchDisabledError):
            establish_clean_baseline()
        from src.graph.orchestration_search import run_arm_cell

        with pytest.raises(SearchDisabledError):
            run_arm_cell(get_arm("df_incumbent"), Cell(task_id="t", seed=1, task=None))

    def test_env_untouched_when_disabled(self, search_off):
        """拒绝路径不触碰 os.environ（快照逐位相等）。"""
        before = dict(os.environ)
        with pytest.raises(SearchDisabledError):
            apply_arm_env(get_arm("df_incumbent"))
        with pytest.raises(SearchDisabledError):
            establish_clean_baseline()
        assert dict(os.environ) == before

    def test_apply_arm_env_restores_exactly(self, search_on, monkeypatch):
        """开启后 apply_arm_env 退出时 env 逐键恢复（含"原未设置"键的清除）。"""
        monkeypatch.setenv("DETECTION_FIRST_ENABLE", "false")  # ambient 有值
        monkeypatch.delenv("MUTATION_ADVISOR_ENABLE", raising=False)  # ambient 未设置
        arm = get_arm("df_incumbent")  # 设置 5 个键（含 MUTATION_ADVISOR 之外的键）
        before = dict(os.environ)
        with apply_arm_env(arm):
            assert os.environ["DETECTION_FIRST_ENABLE"] == "true"
            assert os.environ["DETECTION_SPECIFICITY_GATE_ENABLE"] == "true"
        after = dict(os.environ)
        assert after == before

    def test_nested_apply_arm_env_rejected(self, search_on):
        """嵌套 apply_arm_env 直接抛错（进程全局 env 的串行前提被破坏 = 调用方 Bug）。"""
        arm = get_arm("df_incumbent")
        # 外层进入后 active=True；内层 CM __enter__ 检测到嵌套即抛（调用期已过主开关校验）
        with apply_arm_env(arm), pytest.raises(ArmSpecError, match="嵌套"), apply_arm_env(arm):
            pass

    def test_clean_baseline_and_restore(self, search_on, monkeypatch):
        """干净基线把 10 个已知臂键压 false；restore 恢复原快照。"""
        monkeypatch.setenv("FL_SPECTRAL_ENABLE", "true")  # ambient 干扰项
        monkeypatch.delenv("ROUTE_STRUCTURED_ENABLE", raising=False)
        snapshot = establish_clean_baseline()
        assert all(os.environ.get(k) == "false" for k in KNOWN_ARM_ENV_KEYS)
        restore_env_snapshot(snapshot)
        assert os.environ.get("FL_SPECTRAL_ENABLE") == "true"
        assert os.environ.get("ROUTE_STRUCTURED_ENABLE") is None


# ─── 5. 臂空间约束与键名 ─────────────────────────────────────────────────────


class TestArmRegistry:
    """规格 §9.5：16 臂唯一 id / 依赖约束 / SPEC 链一体 / 键名 ⊆ 已知集合。"""

    def test_registry_shape(self):
        """16 臂、id 唯一、全键名合法、取值合法。"""
        assert len(ARM_REGISTRY) == 16
        ids = [arm.arm_id for arm in ARM_REGISTRY]
        assert len(set(ids)) == 16
        for arm in ARM_REGISTRY:
            for key, value in arm.env.items():
                assert key in KNOWN_ARM_ENV_KEYS, f"{arm.arm_id} 含未知键 {key}"
                assert value in ("true", "false"), f"{arm.arm_id} 的 {key} 取值非法：{value}"

    def test_dependency_constraints_hold(self):
        """登记表内 mutation_advisor / fl_spectral 仅在 debugger 臂出现。"""
        for arm in ARM_REGISTRY:
            for dep in ("MUTATION_ADVISOR_ENABLE", "FL_SPECTRAL_ENABLE"):
                if arm.env.get(dep) == "true":
                    assert arm.debugger, f"{arm.arm_id} 开 {dep} 但 debugger=False"

    def test_spec_chain_atomic(self):
        """SPEC 链三开关在登记表中按生效值同进同退（缺省键在干净基线下为 false）。"""
        for arm in ARM_REGISTRY:
            states = {
                arm.env.get(k, "false") for k in ("SPEC_IR_ENABLE", "SPEC_IR_DSL_ENABLE", "SPEC_ORACLE_EXEC_ENABLE")
            }
            assert len(states) == 1, f"{arm.arm_id} 拆开 SPEC 链"

    def test_allow_regeneration_resolution(self):
        """再生路由解析：df_incumbent/gates_only_noregen=True；plain_llm_floor/全拓扑=False。"""
        assert get_arm("df_incumbent").resolved_allow_regeneration is True
        assert get_arm("plain_llm_floor").resolved_allow_regeneration is False
        assert get_arm("gates_only_noregen").resolved_allow_regeneration is True  # 显式保留
        assert get_arm("full_df_gates").resolved_allow_regeneration is False

    def test_invalid_specs_rejected(self):
        """非法臂定义全部抛 ArmSpecError（键名/取值/链拆开/依赖/再生矛盾）。"""
        with pytest.raises(ArmSpecError, match="未知 env 键"):
            ArmSpec(arm_id="bad_key", planner=False, debugger=False, env={"NOT_A_SWITCH": "true"})
        with pytest.raises(ArmSpecError, match="取值"):
            ArmSpec(arm_id="bad_value", planner=False, debugger=False, env={"DETECTION_FIRST_ENABLE": "yes"})
        with pytest.raises(ArmSpecError, match="SPEC 链"):
            ArmSpec(
                arm_id="split_chain",
                planner=True,
                debugger=True,
                env={"SPEC_IR_ENABLE": "true", "SPEC_IR_DSL_ENABLE": "false"},
            )
        with pytest.raises(ArmSpecError, match="debugger=False"):
            ArmSpec(arm_id="mut_no_debugger", planner=False, debugger=False, env={"MUTATION_ADVISOR_ENABLE": "true"})
        with pytest.raises(ArmSpecError, match="矛盾"):
            ArmSpec(arm_id="regen_with_debugger", planner=True, debugger=True, allow_regeneration=True)
        with pytest.raises(ArmSpecError, match="非法"):
            ArmSpec(arm_id="", planner=True, debugger=True)

    def test_get_arm_unknown(self):
        """未知臂 id 抛 ArmSpecError。"""
        with pytest.raises(ArmSpecError, match="未知臂 id"):
            get_arm("nonexistent_arm")


# ─── 6. UCB1 数学性质 ────────────────────────────────────────────────────────


class TestUCB1Properties:
    """规格 §9.6：round-robin 初始化 / 恒优臂收敛 / 不可测臂排除。"""

    def test_round_robin_initialization(self, search_on):
        """前 |A| 次拉取每臂恰一次（按登记序）。"""
        arms = ARM_REGISTRY
        stub = StubEvaluator()
        budget = SearchBudget(max_evals=16, max_total_tokens=1_500_000)
        search = OrchestrationSearch(
            arms=arms, cells=_make_cells(36), budget=budget, ucb_c=1.0, seed=42, evaluator=stub
        )
        report = search.run()
        assert report["pull_sequence"] == [arm.arm_id for arm in arms]

    def test_constant_best_arm_converges(self, search_on):
        """恒优臂（detection 恒 1）被选为 champion 且可测次数显著高于其余臂。

        注意：获胜臂是 df_no_gates 而非 incumbent 自身——champion 规则要求
        **严格优于 incumbent"（打平即阴性），这是"自动发现优于手工设计"
        命题的科学口径。
        """
        arms = ARM_REGISTRY
        rewards = {arm.arm_id: (1.0 if arm.arm_id == "df_no_gates" else 0.0) for arm in arms}
        stub = StubEvaluator(rewards=rewards)
        budget = SearchBudget(max_evals=200, max_total_tokens=1_500_000)
        search = OrchestrationSearch(
            arms=arms, cells=_make_cells(36), budget=budget, ucb_c=1.0, seed=42, evaluator=stub
        )
        report = search.run()
        assert report["champion"] == "df_no_gates"
        best_n = report["arm_stats"]["df_no_gates"]["n_measurable"]
        others_n = [s["n_measurable"] for aid, s in report["arm_stats"].items() if aid != "df_no_gates"]
        assert best_n > max(others_n)

    def test_unmeasurable_arm_excluded(self, search_on):
        """全 None 臂在超过 max_unmeasurable 后被排除（excluded_structurally）。"""
        arms = ARM_REGISTRY
        rewards = {arm.arm_id: (None if arm.arm_id == "plain_llm_floor" else 0.0) for arm in arms}
        stub = StubEvaluator(rewards=rewards)
        budget = SearchBudget(max_evals=240, max_total_tokens=1_500_000)
        search = OrchestrationSearch(
            arms=arms, cells=_make_cells(36), budget=budget, ucb_c=1.0, seed=42, evaluator=stub, max_unmeasurable=2
        )
        report = search.run()
        floor_stats = report["arm_stats"]["plain_llm_floor"]
        assert floor_stats["excluded_reason"] == "unmeasurable_exceeded"
        assert floor_stats["n_measurable"] == 0
        assert floor_stats["unmeasurable"] == 3  # 第 3 次（> 2）触发排除


# ─── 7. memoize + 信用不耦合 ─────────────────────────────────────────────────


class TestMemoizeAndInvariants:
    """规格 §9.7：同 (arm, cell) 至多评估一次；信用函数不进主循环。"""

    def test_no_duplicate_cell_evaluation(self, search_on):
        """evaluator 对同 (arm, task, seed) 至多调用一次（零重复 LLM 成本）。"""
        arms = ARM_REGISTRY
        cells = _make_cells(6)  # 每臂最多 6 次新鲜评估
        stub = StubEvaluator()
        budget = SearchBudget(max_evals=240, max_total_tokens=1_500_000)
        search = OrchestrationSearch(arms=arms, cells=cells, budget=budget, ucb_c=1.0, seed=42, evaluator=stub)
        report = search.run()
        keys = [(arm_id, task_id, seed) for arm_id, task_id, seed in stub.calls]
        assert len(keys) == len(set(keys)), "同 (arm, cell) 被重复评估"
        assert len(keys) <= len(arms) * len(cells)
        # cell 耗尽停止：总评估 = 16 臂 × 6 cell
        assert report["budget"]["stop_reason"] == "all_arms_excluded"
        assert len(keys) == len(arms) * len(cells)

    def test_credit_functions_not_coupled_to_search_loop(self):
        """不变量：OrchestrationSearch 源码不引用 hindsight 信用符号（防 reward hacking）。"""
        assert_no_credit_coupling()

    def test_champion_constraints_unit(self):
        """champion 选拔单元测试：token 超 2×  incumbent 的臂即使 detection 高也落选。"""
        arm_stats = {
            "df_incumbent": {"n_measurable": 10, "mean_detection": 0.45, "mean_tokens": 4000.0, "mean_false_fix": 0.0},
            "expensive_best": {
                "n_measurable": 10,
                "mean_detection": 0.90,
                "mean_tokens": 20000.0,
                "mean_false_fix": 0.0,
            },
            "cheap_good": {"n_measurable": 10, "mean_detection": 0.55, "mean_tokens": 6000.0, "mean_false_fix": 0.1},
            "thin_evidence": {"n_measurable": 2, "mean_detection": 0.99, "mean_tokens": 100.0, "mean_false_fix": 0.0},
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion == "cheap_good"  # expensive_best 超 token 约束；thin_evidence 证据不足
        assert "cheap_good" in reason

    def test_champion_false_fix_guard(self):
        """假修复守卫：false_fix > 0.5 的臂落选（防"刷 passed"配置）。"""
        arm_stats = {
            "df_incumbent": {"n_measurable": 10, "mean_detection": 0.45, "mean_tokens": 4000.0, "mean_false_fix": 0.0},
            "hacky": {"n_measurable": 10, "mean_detection": 0.80, "mean_tokens": 4000.0, "mean_false_fix": 0.9},
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "阴性" in reason

    def test_champion_none_when_incumbent_unavailable(self):
        """incumbent 不可用 → 无从比较（None + 原因）。"""
        arm_stats = {
            "df_incumbent": {"n_measurable": 1, "mean_detection": 0.0, "mean_tokens": 0.0, "mean_false_fix": 0.0}
        }
        champion, reason = select_champion(arm_stats, min_evals=5)
        assert champion is None
        assert "incumbent" in reason
