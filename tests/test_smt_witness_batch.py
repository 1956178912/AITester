"""T3b z3 SMT 见证批定向测试（≤10 例）：status 分类 / 超时计法 / 率分母 /
材料缺口剔除 / 确定性 / 关联层分桶口径。

只测 ``experiments/smt_witness_batch.py`` 的纯函数与真实 z3 求解路径，
不跑整批（整批落盘在 ``experiments/results/t_round_smt_witness_20261018/``）。
"""

from __future__ import annotations

import hashlib

import pytest

from experiments import smt_witness_batch as swb
from src.specs.spec_smt import check_postcondition_consistency, smt_available

requires_z3 = pytest.mark.skipif(not smt_available(), reason="z3-solver 未安装（pip install aitester[formal]）")


def _clause_row(status: str, *, ms: float = 1.0) -> dict[str, object]:
    return {
        "smt_status": status,
        "reached_solver": status != "error",
        "smt_solve_ms": ms,
    }


def _task_record(
    task_id: str,
    statuses: list[str],
    *,
    material_status: str = "anchor_hit",
    detection_rate: float | None = 1.0,
) -> dict[str, object]:
    clauses = [_clause_row(status) for status in statuses]
    rates = swb.compute_task_rates(clauses)  # type: ignore[arg-type]
    return {
        "task_id": task_id,
        "material_status": material_status,
        "dfspec_detection_rate": detection_rate,
        "dfspec_detection_measurable": detection_rate is not None,
        "clauses": clauses,
        **rates,
    }


class TestStatusClassification:
    def test_status_mapping_frozen_rules(self) -> None:
        # unknown：墙钟 < 0.9×timeout 保持 unknown，达到阈值才计 timeout
        assert swb.classify_result("unknown", 4600.0, 5000) == ("timeout", None, True)
        assert swb.classify_result("unknown", 100.0, 5000) == ("unknown", None, True)
        assert swb.classify_result("unknown", 4500.0, 5000)[0] == "timeout"
        assert swb.classify_result("unknown", 4499.0, 5000)[0] == "unknown"
        # sat/unsat 永不计 timeout（防"慢"被读成失败/不可满足）
        assert swb.classify_result("sat", 99999.0, 5000) == ("sat", None, True)
        assert swb.classify_result("unsat", 99999.0, 5000) == ("unsat", None, True)
        # skipped（未达求解器）→ error/not_reached，绝不计 unsat/unknown/timeout
        status, error_kind, reached = swb.classify_result("skipped", 1.0, 5000)
        assert (status, error_kind, reached) == ("error", "not_reached", False)


class TestTaskRates:
    def test_rate_denominators_frozen(self) -> None:
        rates = swb.compute_task_rates([_clause_row("sat"), _clause_row("unsat"), _clause_row("error")])
        assert rates["smt_clauses_nonempty"] == 3 and rates["smt_clauses_reached"] == 2
        assert rates["smt_witness_rate"] == round(1 / 3, 6)  # sat / 非空（不是 / reached）
        assert rates["smt_reach_rate"] == round(2 / 3, 6)
        assert rates["smt_timeout_rate"] == 0.0
        rates2 = swb.compute_task_rates([_clause_row("sat"), _clause_row("timeout", ms=5000.0), _clause_row("error")])
        assert rates2["smt_timeout_rate"] == round(1 / 2, 6)  # timeout / reached
        assert rates2["smt_timeout_share_nonempty"] == round(1 / 3, 6)  # timeout / 非空
        # 无非空子句 → 率一律 None（不是 0，避免"未测量"被读成"失败"）
        empty = swb.compute_task_rates([])
        assert empty["smt_witness_rate"] is None and empty["smt_timeout_rate"] is None


class TestMaterialSelection:
    def test_channel_selection_and_empty_filter(self) -> None:
        spec = {
            "preconditions": ["中文前置"],
            "preconditions_expr": ["x > 0"],
            "postconditions_expr": ["result == x"],
            "invariants_expr": [],
            "postconditions": ["中文后置"],
        }
        channel, clauses = swb.select_clause_material(spec)
        assert channel == "expr"
        assert [c["channel_field"] for c in clauses] == ["preconditions_expr", "postconditions_expr"]
        assert [c["kind"] for c in clauses] == ["precondition", "postcondition"]
        # 无 *_expr 字段 → NL 回退（保持 src 通道选择口径）
        channel_nl, clauses_nl = swb.select_clause_material({"preconditions": ["x > 0"], "postconditions": ["r == x"]})
        assert channel_nl == "nl"
        assert [c["channel_field"] for c in clauses_nl] == ["preconditions", "postconditions"]
        # 空串子句不进 D1（与可编译率非空口径一致）
        _, filtered = swb.select_clause_material({"preconditions_expr": ["  ", "x > 0", ""]})
        assert [c["clause"] for c in filtered] == ["x > 0"]


class TestSignatureParams:
    def test_dotted_method_name_fallback(self) -> None:
        source = "class Node:\n    def __init__(self, value=None):\n        self.value = value\n"
        params, label = swb.resolve_signature_params(source, "Node.__init__")
        assert params == ["value"] and label == "dotted_tail"
        # 未解析：函数名不存在 → (None, unresolved)，任务全子句记 error（不静默成功）
        assert swb.resolve_signature_params(source, "missing_fn") == (None, "unresolved")


class TestRealSolverPath:
    @requires_z3
    def test_sat_unsat_and_gate_rejected(self) -> None:
        sat = swb.solve_clause("x > 0", "precondition", ["x"])
        assert sat["smt_status"] == "sat" and sat["reached_solver"] is True
        unsat = swb.solve_clause("x > 0 and x < 0", "precondition", ["x"])
        assert unsat["smt_status"] == "unsat"  # 真 UNSAT：前件空洞
        # 未达求解器（白名单调用不可翻译）→ error/not_reached，绝不计 unsat/unknown
        rejected = swb.solve_clause("len(items) > 0", "precondition", ["items"])
        assert (rejected["smt_status"], rejected["error_kind"]) == ("error", "not_reached")
        assert rejected["reached_solver"] is False

    @requires_z3
    def test_result_alias_post_clause_now_reached(self) -> None:
        # T3c（2026-10-18）行为变更：spec_smt._collect_post_constraints 现做
        # token 感知的 result→r 别名归一（签名参数名不是 result 时）。
        # T3b 批工件（t_round_smt_witness_20261018/）为 **pre-fix 基线**：
        # 该批 110 条 result 别名子句被记 error/not_reached；本断言改为修复后现状。
        alias = swb.solve_clause("result == 0", "postcondition", ["arr"])
        assert (alias["smt_status"], alias["reached_solver"]) == ("sat", True)
        # 负控 1：只归一精确名字 result——其它结果别名（res）仍保守未达求解器
        other = swb.solve_clause("res == 0", "postcondition", ["arr"])
        assert (other["smt_status"], other["error_kind"]) == ("error", "not_reached")
        # 负控 2：参数名确实为 result 时不归一（历史行为）——result 是输入参数，
        # 不会换成自由结果变量 r（规格变量域仍为 result）。详见
        # tests/test_spec_smt_result_alias.py::test_param_named_result_keeps_historical_behavior
        param_named = check_postcondition_consistency({"postconditions": ["result == 0"]}, ["result"])
        assert param_named["status"] == "sat" and param_named["variables"] == ["result"]
        ok = swb.solve_clause("r == 0", "postcondition", ["arr"])
        assert ok["smt_status"] == "sat"  # r 为自由结果变量 → 后件自洽


class TestAggregationAndAssociation:
    def test_missing_material_excluded_and_association_frozen(self) -> None:
        records = [
            _task_record("a", ["sat", "sat"]),
            _task_record("b", ["sat", "error"], detection_rate=None),
            _task_record("c", [], material_status="spec_material_missing"),
        ]
        agg = swb.aggregate_records(records)  # type: ignore[arg-type]
        assert agg["tasks_total"] == 3 and agg["tasks_with_material"] == 2
        assert agg["material_gap_tasks"] == [{"task_id": "c", "material_status": "spec_material_missing"}]
        assert agg["witness_rate_mean"] == round((1.0 + 0.5) / 2, 6)  # 缺口任务不摊薄均值
        assert swb.check_recompute(records[:2], agg)["all_ok"] is True  # type: ignore[arg-type]
        # 关联层：中位数二分 + MDE 披露；退化分桶 → 无对照，不做 detection 比较
        assoc = swb.build_association(
            [
                _task_record("low", ["error", "error"], detection_rate=0.0),
                _task_record("mid", ["sat", "error"], detection_rate=1.0),
                _task_record("high", ["sat", "sat"], detection_rate=1.0),
            ]
        )  # type: ignore[arg-type]
        assert assoc["status"] == "exploratory" and assoc["mde_pp"] == swb.MDE_PP_FROZEN
        assert assoc["bucketing_rule"] == "median_split_on_smt_witness_rate"
        assert assoc["buckets"]["high"]["n_tasks"] == 2 and assoc["buckets"]["low"]["n_tasks"] == 1
        flat = swb.build_association([_task_record("x", ["sat"]), _task_record("y", ["sat"])])  # type: ignore[arg-type]
        assert flat["buckets"] == {} and "无对照" in flat["interpretation"]


class TestTaskBuildDeterminism:
    @requires_z3
    def test_full_task_build_is_deterministic_after_stripping_timings(self, tmp_path) -> None:
        program_dir = tmp_path / "quixbugs" / "python_programs"
        program_dir.mkdir(parents=True)
        source = "def add(a, b):\n    return a - b\n"
        (program_dir / "add.py").write_text(source, encoding="utf-8")
        digest = hashlib.sha256(source.strip().encode("utf-8")).hexdigest()
        anchors = {
            digest: {
                "function_name": "add",
                "logic_analysis": {
                    # 真实锚材料同时带 NL 字段（parse_logic_analysis 的"有材料"判定
                    # 只看 NL/边界/示例/函数名；仅 expr 字段会保守返回 None）
                    "preconditions": ["a 为正整数", "b 为正整数"],
                    "postconditions": ["返回 a 与 b 之和"],
                    "preconditions_expr": ["a > 0", "b > 0"],
                    "postconditions_expr": ["result == a + b"],
                },
                "source_len": len(source),
                "chosen_from": "synthetic.json",
            }
        }
        task_row = {
            "task_id": "quixbugs__add",
            "task_metadata": {"program": "add"},
            "detection_rate": 1.0,
            "specificity_gate_verdict": "specific_red",
            "spec_oracle_verdict": "not_attempted",
        }
        roots = [tmp_path / "quixbugs"]
        first = swb.build_task_record(task_row, anchors, roots, in_primary=True)
        second = swb.build_task_record(task_row, anchors, roots, in_primary=True)
        # 计时键剔除后完全一致（status/分类/计数/率/哈希）
        assert swb.canonical_dump(swb._strip_timing_keys(first)) == swb.canonical_dump(swb._strip_timing_keys(second))
        assert first["material_status"] == "anchor_hit"
        assert first["channel_used"] == "expr"
        assert first["smt_clauses_nonempty"] == 3
        # T3c 行为变更：post 子句 "result == a + b" 经别名归一为 r == a + b 后可达
        # 求解器 → sat（T3b pre-fix 基线为 error/not_reached）。本测试的确定性
        # 断言在上一行（剔计时键后两次构建逐字段一致），状态快照随行为更新。
        assert first["smt_status_counts"] == {
            "sat": 3,
            "unsat": 0,
            "unknown": 0,
            "timeout": 0,
            "error": 0,
        }
        # 锚表未命中 → spec_material_missing，任务行不产生任何子句（缺口剔除）
        missing = swb.build_task_record(task_row, {}, roots, in_primary=True)
        assert missing["material_status"] == "spec_material_missing"
        assert missing["clauses"] == [] and missing["smt_clauses_nonempty"] == 0
