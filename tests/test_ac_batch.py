"""AC 批次测试（2026-10-06 第十轮审查落地）。

覆盖三块：
- AC1（T-P0-2）prompt–DSL 契约修复：SPEC_EXPR_CONTRACT_SECTION 注入门控、
  parse→compile_readiness 契约往返锁定（修复前 spec_compile_rate 恒 0.0
  的回归防线）、表达式通道分通道计率、M10 schema 对 *_expr 字段的容忍；
- AC2（T-P0-4）检出优先双门：门开关默认关、特异性判定三值、红回归
  纯状态判定的守卫矩阵、_should_debug 过红路由分支、
  create_initial_state 原码快照；
- AC4（T-P0-5）聚类稳健统计：ICC 估计量、精确符号检验、
  template_cluster_sensitivity 输出、plain_llm_df 一等基线加载。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agents.planner import PlannerAgent
from src.prompts.templates import SPEC_EXPR_CONTRACT_SECTION
from src.specs import compile_readiness, parse_logic_analysis, spec_expr_coverage
from src.tools.detection_gates import (
    detection_specificity_gate_enabled,
    red_regression_check,
    red_regression_gate_enabled,
    specificity_verdict,
)
from src.tools.logic_spec import validate_logic_spec

# ─── AC1：契约段与注入门控 ───────────────────────────────────────────────────


def test_ac1_contract_section_content() -> None:
    """契约段必须点名三个 *_expr 字段，且示例自身可编译（自洽契约）。"""
    assert "preconditions_expr" in SPEC_EXPR_CONTRACT_SECTION
    assert "postconditions_expr" in SPEC_EXPR_CONTRACT_SECTION
    assert "invariants_expr" in SPEC_EXPR_CONTRACT_SECTION
    # 示例表达式必须能通过表达式通道判定（契约不可自相矛盾）
    from src.specs.spec_ir_v2 import _whitelist_check, is_expression_clause

    for example in ("b != 0", "result == sorted(result)"):
        assert is_expression_clause(example)
        assert not _whitelist_check(example)


def test_ac1_planner_appends_contract_section_iff_dsl_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPEC_IR_DSL_ENABLE=true 时契约段进查询；默认关时 prompt 零变化。"""
    raw_response = json.dumps(
        {
            "function_name": "divide",
            "description": "除法",
            "logic_analysis": {
                "input_domain": "数对",
                "output_domain": "商",
                "preconditions": ["b 不为零"],
                "preconditions_expr": ["b != 0"],
                "postconditions": [],
                "edge_cases": [],
            },
            "test_cases": [],
        },
        ensure_ascii=False,
    )
    captured: list[str] = []

    def fake_call(query: str, **_: Any) -> str:
        captured.append(query)
        return raw_response

    agent = PlannerAgent()
    monkeypatch.setattr(agent, "_call_llm_with_cache", fake_call)

    monkeypatch.setenv("SPEC_IR_DSL_ENABLE", "true")
    plan_on = agent.plan("def divide(a, b):\n    return a / b\n", "divide")
    assert any("preconditions_expr" in q for q in captured), "DSL 开启时契约段必须注入查询"

    captured.clear()
    monkeypatch.delenv("SPEC_IR_DSL_ENABLE", raising=False)
    agent.plan("def divide(a, b):\n    return a / b\n", "divide")
    assert not any("preconditions_expr" in q for q in captured), "默认关时 prompt 必须零变化"
    # 计划解析正常（expr 字段随 logic_analysis 透传）
    assert plan_on["logic_analysis"]["preconditions_expr"] == ["b != 0"]


def test_ac1_contract_roundtrip_compile_rate_positive() -> None:
    """契约锁定核心：按 prompt 契约格式产出的规约必须编译率 > 0。

    修复前（AB1 验证批实证）：中文 NL 子句 100% 被 _EXPR_TOKEN_RE 拒绝，
    spec_compile_rate 恒 0.0——本测试是该契约断裂的永久回归防线。
    """
    logic_analysis = {
        "input_domain": "整数对",
        "output_domain": "商",
        "preconditions": ["b 不为零", "a 为整数"],
        "preconditions_expr": ["b != 0"],
        "postconditions": ["结果为 a/b"],
        "postconditions_expr": ["abs(result * b - a) < 1e-9"],
        "edge_cases": ["b=0 抛异常"],
    }
    spec = parse_logic_analysis(logic_analysis)
    assert spec is not None
    assert spec.get("preconditions_expr") == ["b != 0"]
    assert compile_readiness(spec) == 1.0
    assert spec_expr_coverage(spec) == pytest.approx(2 / 3)


def test_ac1_compile_readiness_expr_channel_semantics() -> None:
    """表达式通道分通道计率：白名单违例剔除、混合按比例、纯 NL 维持历史 0。"""
    # 全部合法
    assert compile_readiness({"preconditions_expr": ["b != 0", "a >= 0"]}) == 1.0
    # 白名单外调用 → 不可编译
    assert compile_readiness({"preconditions_expr": ["open('/etc/passwd') is None"]}) == 0.0
    # 混合
    assert compile_readiness({"preconditions_expr": ["b != 0", "open('x') is None"]}) == 0.5
    # 中文 NL（无 expr 通道）→ 历史保守口径 0.0（契约断裂基线可复现）
    assert compile_readiness({"preconditions": ["b 不为零"], "postconditions": []}) == 0.0
    # 历史英文表达式 NL 口径不变（无 expr 键时走 NL 通道）
    assert compile_readiness({"preconditions": ["x > 0", "x 为正"]}) == 0.5
    # 空材料
    assert compile_readiness(None) == 0.0
    assert compile_readiness({}) == 0.0


def test_ac1_spec_expr_coverage_edges() -> None:
    """覆盖率边界：无材料 None / 纯 expr 1.0 / 超出封顶。"""
    assert spec_expr_coverage(None) is None
    assert spec_expr_coverage({"preconditions": ["a"], "preconditions_expr": ["a > 0", "a < 9"]}) == 1.0
    assert spec_expr_coverage({"preconditions": ["a", "b", "c"], "preconditions_expr": ["a > 0"]}) == pytest.approx(
        1 / 3
    )


def test_ac1_m10_schema_tolerates_expr_fields() -> None:
    """M10 schema 强校验对 *_expr 附加字段零 findings（不误杀契约产物）。"""
    logic_analysis = {
        "input_domain": "整数对",
        "output_domain": "商",
        "preconditions": ["b 不为零"],
        "preconditions_expr": ["b != 0"],
        "postconditions": ["结果为商"],
        "postconditions_expr": ["result >= 0"],
        "edge_cases": ["b=0 抛异常"],
    }
    assert validate_logic_spec(logic_analysis) == []


def test_ac1_parse_expr_passthrough_absent_when_missing() -> None:
    """未提供 expr 字段时 spec 不含该键（schema 向后兼容）。"""
    spec = parse_logic_analysis({"preconditions": ["x > 0"], "postconditions": []})
    assert spec is not None
    assert "preconditions_expr" not in spec
    assert "postconditions_expr" not in spec


# ─── AC2：检出优先双门 ──────────────────────────────────────────────────────


def test_ac2_gate_envs_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """双门默认关（ADR-0003：默认行为零变化）。"""
    monkeypatch.delenv("DETECTION_SPECIFICITY_GATE_ENABLE", raising=False)
    monkeypatch.delenv("RED_REGRESSION_GATE_ENABLE", raising=False)
    assert detection_specificity_gate_enabled() is False
    assert red_regression_gate_enabled() is False


def test_ac2_specificity_verdict_unavailable_without_gold() -> None:
    """无 gold 材料（真实仓库场景）→ unavailable 保守放行。"""
    assert specificity_verdict("def test_x(): pass", None, "m") == "unavailable"
    assert specificity_verdict("def test_x(): pass", "  ", "m") == "unavailable"


@pytest.mark.parametrize(
    ("runner_result", "expected"),
    [
        ({"green": True, "rc": 0, "unavailable": False}, "specific_red"),
        ({"green": False, "rc": 1, "unavailable": False}, "over_red"),
        (None, "unavailable"),
    ],
)
def test_ac2_specificity_verdict_with_runner(
    monkeypatch: pytest.MonkeyPatch, runner_result: Any, expected: str
) -> None:
    """门①三值判定：gold fixed 上绿=specific_red / 红=over_red / 不可判=unavailable。"""
    import src.tools.detection_gates as gates

    monkeypatch.setattr(gates, "_run_test_against_code", lambda *a, **k: runner_result)
    assert specificity_verdict("def test_x(): pass", "def f(): pass", "mod") == expected


def test_ac2_red_regression_check_guard_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """门②守卫矩阵：仅"曾红+换测试+未修补+门开"四条件齐备才判抹红。"""
    monkeypatch.setenv("RED_REGRESSION_GATE_ENABLE", "true")
    base = {
        "detection_first_red_seen": True,
        "red_witness_test_code": "def test_a(): assert f(1) == 2",
        "regeneration_count": 1,
        "target_code": "code-v1",
        "original_target_code": "code-v1",
    }
    witness = base["red_witness_test_code"]
    upd = red_regression_check(base, "def test_a(): pass")
    assert upd == {"red_regression_violation": True, "generated_test": witness, "test_passed": False}
    # 源码已修补 → 交 M1 事后独立裁决，门内不动
    assert red_regression_check({**base, "target_code": "code-v2"}, "def test_a(): pass") is None
    # 测试未被替换 → 无违规
    assert red_regression_check(base, witness) is None
    # 未发生再生成 → 无违规
    assert red_regression_check({**base, "regeneration_count": 0}, "def test_a(): pass") is None
    # 未曾见红 → 无违规
    assert red_regression_check({**base, "detection_first_red_seen": False}, "def test_a(): pass") is None
    # 无红证人快照 → 无违规
    assert red_regression_check({**base, "red_witness_test_code": None}, "def test_a(): pass") is None
    # 门关 → 无违规
    monkeypatch.delenv("RED_REGRESSION_GATE_ENABLE", raising=False)
    assert red_regression_check(base, "def test_a(): pass") is None


def test_ac2_create_initial_state_snapshots_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_initial_state 快照任务起始原码（红回归门对照材料）。"""
    monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
    from src.graph.state import create_initial_state

    state = create_initial_state("t", "p/task_0000.py", "print('buggy')", 3)
    assert state["original_target_code"] == "print('buggy')"
    assert state["gold_fixed_code"] is None
    assert state["red_witness_test_code"] is None
    assert state["specificity_gate_verdict"] is None
    assert state["red_regression_violation"] is None


def test_ac2_should_debug_over_red_routes_regenerate(monkeypatch: pytest.MonkeyPatch) -> None:
    """_should_debug：iteration==0 过红 → regenerate（而非进修复循环）。"""
    monkeypatch.setenv("DETECTION_SPECIFICITY_GATE_ENABLE", "true")
    from src.graph.workflow import _should_debug

    state: dict[str, Any] = {
        "test_passed": False,
        "iteration": 0,
        "max_iterations": 3,
        "regeneration_count": 0,
        "specificity_gate_verdict": "over_red",
        "repair_history": [],
        "diagnosis": "",
        "execution_trace": [{"n": 1}],
    }
    assert _should_debug(state) == "regenerate"  # type: ignore[arg-type]
    # specific_red → 常规 debug（进修复循环）
    state["specificity_gate_verdict"] = "specific_red"
    assert _should_debug(state) == "debug"  # type: ignore[arg-type]
    # 门关 → verdict 存在也不改路由（默认零变化）
    monkeypatch.delenv("DETECTION_SPECIFICITY_GATE_ENABLE", raising=False)
    state["specificity_gate_verdict"] = "over_red"
    assert _should_debug(state) == "debug"  # type: ignore[arg-type]


def test_ac2_gate_execution_rejects_unsafe_module_name() -> None:
    """门执行原语：module_name 非合法标识符（路径穿越形态）→ 委托前拒绝。

    M1 委托原语自身不校验名字（f"{name}.py" 拼临时目录路径），穿越形态
    会拼出临时目录外的路径——本层校验是门执行的安全前提（曾由本测试
    实测捕获，回归防线）。
    """
    import src.tools.detection_gates as gates

    assert gates._run_test_against_code("def test_x(): pass", "X = 1", "../../evil") is None
    assert gates._run_test_against_code("def test_x(): pass", "X = 1", "ok-module") is None
    assert gates._run_test_against_code("def test_x(): pass", "X = 1", "") is None


def test_ac2_gate_execution_real_roundtrip() -> None:
    """门执行原语真实往返（委托 M1 原语，临时目录 pytest）。"""
    import src.tools.detection_gates as gates

    # 真缺陷：buggy 版 abs 缺失——缺陷特异红测试 buggy 红 / fixed 绿
    buggy = "def dist(x, y):\n    return x - y\n"
    fixed = "def dist(x, y):\n    return abs(x - y)\n"
    red_test = "from m2 import dist\n\ndef test_neg():\n    assert dist(3, 10) == 7\n"
    assert gates._run_test_against_code(red_test, buggy, "m2")["green"] is False
    assert gates._run_test_against_code(red_test, fixed, "m2")["green"] is True
    # 恒绿测试在 buggy 上也绿（非缺陷特异）
    green_test = "from m3 import divide\n\ndef test_ok():\n    assert divide(6, 3) == 2\n"
    buggy_div = "def divide(a, b):\n    return a / b\n"
    assert gates._run_test_against_code(green_test, buggy_div, "m3")["green"] is True


# ─── AC4：聚类稳健统计 ──────────────────────────────────────────────────────


def test_ac4_icc_one_way_binary() -> None:
    """ICC 估计量：完全按簇分化 → 高；簇内随机 → 低/0；退化结构 → None。"""
    from experiments.statistical_analysis import _icc_one_way_binary

    clustered = {"t1": [1.0, 1.0, 1.0], "t2": [0.0, 0.0, 0.0], "t3": [1.0, 1.0]}
    assert _icc_one_way_binary(clustered) is not None and _icc_one_way_binary(clustered) > 0.9
    mixed = {"t1": [1.0, 0.0, 1.0, 0.0], "t2": [0.0, 1.0, 0.0, 1.0]}
    assert _icc_one_way_binary(mixed) == 0.0
    assert _icc_one_way_binary({"only": [1.0, 0.0]}) is None
    assert _icc_one_way_binary({"t1": [1.0], "t2": [1.0]}) is None


def test_ac4_exact_sign_test_p() -> None:
    """精确符号检验：22:0 极小 p；1:1 不显著；0:0 恒 1。"""
    from experiments.statistical_analysis import _exact_sign_test_p

    assert _exact_sign_test_p(22, 0) < 1e-6
    assert _exact_sign_test_p(1, 1) == 1.0
    assert _exact_sign_test_p(0, 0) == 1.0


def test_ac4_template_cluster_sensitivity_output() -> None:
    """敏感性输出：含 McNemar/校正 χ²/符号检验三要素，方向计数正确。"""
    from experiments.statistical_analysis import template_cluster_sensitivity

    def rows(dets: list[float], pat: str) -> list[dict[str, Any]]:
        return [
            {"task_id": f"{pat}_{i}", "detection_rate": v, "task_metadata": {"pattern_name": pat}}
            for i, v in enumerate(dets)
        ]

    rows_a = rows([1.0, 1.0, 0.0], "p1") + rows([0.0, 0.0], "p2")
    rows_b = rows([0.0, 0.0, 0.0], "p1") + rows([1.0, 0.0], "p2")
    md = template_cluster_sensitivity(rows_a, rows_b, "armA", "armB")
    assert "McNemar" in md and "DEFF" in md and "符号检验" in md
    # p1 模板 armA 全胜、p2 模板 armB 胜 → 1:1
    assert "armA 胜 1" in md and "armB 胜 1" in md


def test_ac4_plain_llm_df_first_class_baseline(tmp_path: Path) -> None:
    """plain_llm_df 升为统计加载一等基线（生死实验核心对比臂不再漏收）。"""
    from experiments.statistical_analysis import load_experiment_results

    batch = {
        "dataset": "synthetic",
        "provenance": {"seed": 42},
        "results": {
            "plain_llm_df": {
                "details": [
                    {"task_id": "synthetic__task_0000", "detection_rate": 1.0},
                    {"task_id": "synthetic__task_0001", "detection_rate": 0.0},
                ]
            }
        },
    }
    f = tmp_path / "benchmark_x.json"
    f.write_text(json.dumps(batch), encoding="utf-8")
    results = load_experiment_results(str(tmp_path), pool_seeds=True)
    assert len(results["plain_llm_df"]) == 2
    assert results["plain_llm_df"][0]["task_id"].startswith("s42__")
