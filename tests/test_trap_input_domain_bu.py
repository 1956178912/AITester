"""BU 轮（2026-10-22）：Self-Repair Trap 判定核的输入可达域从未披露 —— 收口锁。

缺陷形态（零 LLM；普查工具 `scripts/tools/bu_writeonly_key_census.py`）：
`self_repair_trap_suspected` / `self_repair_trap_signals` 自批次 XIV（ADR-0028）写入结果行，
`src/` + `experiments/` + `scripts/` 全树只有写入点、零读者（BU 普查：13 个只写不读键之一）。
归档 11197 行里 5935 行带判定，**恒为 False、信号恒为空**；同进程把判定核重跑在归档历史上
与行内值按值对照 = 0 例不一致（写入端不撒谎）。但「恒不怀疑」里混着三种事实：输入点数 <2
（3200 行）、历史键值为 `null`（12 行）、输入够且判干净（2723 行）。三个信号各自的门槛
更从未被量过：`assert_count_declining` 需 ≥3 个可解析点、`mutation_score_declining` 需 ≥2 个
非 `None` 分数，两者在本语料的输入域都是**空集**；另有 531 行确有 2 点连续下降的证据，
因点数低于门槛而进不了判据。

修复口径：**只补读侧分档与对账，判定值与方向一处不动**——不改 `detect_self_repair_trap`、
不改写入端、不回填任何历史行的值。

锁的形状（沿用 BQ/BT 纪律）：全归档读数（11197 / 5935 / 531 …）是**实测读数**，登记在手册并
附复现命令，不在这里锁死（新批次一旦落盘就会漂移）。本文件锁的是：①分档恒等式与可达域定义、
②三份具名冻结批次的逐档读数、③阈值常量与判定核字面量的 AST 同源锁、④报告面逐格与脚注、
⑤写入端仍然透出判定核的值。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
from experiments._trap_input_domain import (
    BUCKET_BELOW_FLOOR,
    BUCKET_FLOOR_REACHED,
    BUCKET_MALFORMED,
    BUCKET_NOT_RECORDED,
    GLOBAL_MIN_POINTS,
    SIGNAL_MIN_POINTS,
    TRAP_HISTORY_KEY,
    TRAP_SIGNALS_KEY,
    TRAP_VERDICT_KEY,
    assert_counts,
    input_bucket,
    mutation_scores,
    signal_domains,
    two_point_decline_outside_domain,
)
from experiments.statistical_analysis import (
    self_repair_trap_domain_stats,
    self_repair_trap_domain_summary,
)
from src.tools.self_repair_trap import detect_self_repair_trap

ROOT = Path(__file__).resolve().parents[1]

#: 具名冻结批次（BU 手册 §3 的复现项；三份都在版本控制里的历史批次，不会因新跑批漂移）
PINNED_BATCHES = {
    "experiments/results/e6_a1_batches/e6_phase2_matched_coldcache/benchmark_synthetic_20261009_191716.json": {
        "n_rows": 174,
        "n_with_verdict": 174,
        "not_recorded": 0,
        "history_malformed": 12,
        "below_min_floor": 81,
        "min_floor_reached": 81,
        "declining": 0,
        "collapse": 81,
        "score": 0,
        "n_decline2_outside_domain": 18,
        "n_verdict_true": 0,
        "n_signals_nonempty": 0,
        "n_suspected_mismatch": 0,
        "n_signals_mismatch": 0,
        "n_unmeasurable": 0,
    },
    "experiments/results/t_round_b2_main_batch_20261018/seed42/benchmark_synthetic_20261018_100552.json": {
        "n_rows": 261,
        "n_with_verdict": 261,
        "not_recorded": 0,
        "history_malformed": 0,
        "below_min_floor": 97,
        "min_floor_reached": 164,
        "declining": 0,
        "collapse": 164,
        "score": 0,
        "n_decline2_outside_domain": 35,
        "n_verdict_true": 0,
        "n_signals_nonempty": 0,
        "n_suspected_mismatch": 0,
        "n_signals_mismatch": 0,
        "n_unmeasurable": 0,
    },
    "experiments/results/emse_ult_df200_20261017/benchmark_ult_20261017_110803.json": {
        "n_rows": 200,
        "n_with_verdict": 200,
        "not_recorded": 0,
        "history_malformed": 0,
        "below_min_floor": 5,
        "min_floor_reached": 195,
        "declining": 0,
        "collapse": 195,
        "score": 0,
        "n_decline2_outside_domain": 37,
        "n_verdict_true": 0,
        "n_signals_nonempty": 0,
        "n_suspected_mismatch": 0,
        "n_signals_mismatch": 0,
        "n_unmeasurable": 0,
    },
}


def _snap(assert_count: Any = 3, parse_ok: bool = True, score: Any = None, regeneration: int = 0) -> dict:
    return {
        "regeneration": regeneration,
        "assert_count": assert_count,
        "test_count": 1,
        "parse_ok": parse_ok,
        "mutation_score": score,
    }


def _row(task_id: str, history: Any, suspected: bool = False, signals: Any = None, **extra) -> dict:
    row = {
        "task_id": task_id,
        "passed": True,
        TRAP_VERDICT_KEY: suspected,
        TRAP_SIGNALS_KEY: [] if signals is None else signals,
        TRAP_HISTORY_KEY: history,
    }
    row.update(extra)
    return row


def _judge_gates() -> dict[str, tuple[str, int]]:
    """从判定核源码取真实门槛：信号名 → (`len()` 的变量名, 字面量阈值)。"""
    tree = ast.parse((ROOT / "src" / "tools" / "self_repair_trap.py").read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "detect_self_repair_trap"),
        None,
    )
    assert fn is not None, "判定核函数名变更需同步本锁"
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def enclosing_if(node: ast.AST) -> ast.If | None:
        cur = parents.get(node)
        while cur is not None and not isinstance(cur, ast.If):
            cur = parents.get(cur)
        return cur

    out: dict[str, tuple[str, int]] = {}
    for node in ast.walk(fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "signals"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        name = node.args[0].value
        guard = enclosing_if(node)
        assert guard is not None, name
        gates = [
            cmp
            for cmp in ast.walk(guard.test)
            if isinstance(cmp, ast.Compare)
            and isinstance(cmp.ops[0], ast.GtE)
            and isinstance(cmp.left, ast.Call)
            and isinstance(cmp.left.func, ast.Name)
            and cmp.left.func.id == "len"
            and len(cmp.comparators) == 1
            and isinstance(cmp.comparators[0], ast.Constant)
            and isinstance(cmp.comparators[0].value, int)
        ]
        assert len(gates) == 1, (name, len(gates))
        arg = gates[0].left.args[0]
        out[name] = (arg.id if isinstance(arg, ast.Name) else "", int(gates[0].comparators[0].value))
    return out


class TestInputBucket:
    """四档分档：只回答「输入够不够被判定核看」，不回答「判出什么」。"""

    def test_row_without_verdict_key_is_not_recorded(self) -> None:
        assert input_bucket({"task_id": "t"}) == BUCKET_NOT_RECORDED

    def test_verdict_false_is_still_a_recorded_verdict(self) -> None:
        # 归档里 5935 行全是 False——False 是「有记录」，缺键才是「未记录」
        assert input_bucket({TRAP_VERDICT_KEY: False}) == BUCKET_MALFORMED

    @pytest.mark.parametrize("history", [None, {}, "history", 0, 3])
    def test_history_not_a_list_is_malformed(self, history: Any) -> None:
        assert input_bucket(_row("t", history)) == BUCKET_MALFORMED

    @pytest.mark.parametrize("history", [[], [_snap()], [None, None][:1]])
    def test_below_two_points_is_below_floor(self, history: list) -> None:
        assert input_bucket(_row("t", history)) == BUCKET_BELOW_FLOOR

    @pytest.mark.parametrize("n", [2, 3, 5])
    def test_at_or_above_floor_is_floor_reached(self, n: int) -> None:
        assert input_bucket(_row("t", [_snap() for _ in range(n)])) == BUCKET_FLOOR_REACHED

    def test_bucket_count_is_steady_with_history_content(self) -> None:
        # 点数分档按快照**条数**，非 dict 元素不进快照但也不改变档（可达域另有其档）
        assert input_bucket(_row("t", [{"parse_ok": False}, {"parse_ok": False}])) == BUCKET_FLOOR_REACHED

    def test_global_floor_is_the_min_of_signal_thresholds(self) -> None:
        assert min(SIGNAL_MIN_POINTS.values()) == GLOBAL_MIN_POINTS

    def test_every_row_lands_in_exactly_one_bucket(self) -> None:
        rows = [
            {"task_id": "r0"},
            _row("r1", None),
            _row("r2", [_snap()]),
            _row("r3", [_snap(), _snap()]),
        ]
        out = self_repair_trap_domain_stats(rows)
        assert (
            out["not_recorded"] + out["history_malformed"] + out["below_min_floor"] + out["min_floor_reached"]
            == out["n_rows"]
            == 4
        )


class TestJudgeParity:
    """读侧的取数口径必须与判定核一致——否则可达域是在说另一件事。"""

    def test_last_unparsable_snapshot_yields_no_counts(self) -> None:
        # 判定核：末快照不可解析 ⇒ 不冒充断言退化
        assert assert_counts([_snap(9), _snap(4, parse_ok=False)]) == []

    def test_unparsable_middle_snapshot_is_skipped_in_counts(self) -> None:
        assert assert_counts([_snap(9), _snap(0, parse_ok=False), _snap(7)]) == [9, 7]

    def test_missing_assert_count_reads_as_zero(self) -> None:
        assert assert_counts([{"parse_ok": True}, {"parse_ok": True, "assert_count": None}]) == [0, 0]

    def test_non_numeric_assert_count_raises_instead_of_folding_clean(self) -> None:
        # 沉默兜底就是本轮要收的口：读不懂必须炸出来，不能折成「判干净」
        with pytest.raises(ValueError):
            assert_counts([_snap("abc"), _snap(1)])

    def test_bool_mutation_score_is_not_a_score(self) -> None:
        # bool 是 int 的子类；判定核用 `not isinstance(..., bool)` 排除，读侧同口径
        assert mutation_scores([_snap(score=True), _snap(score=False)]) == []

    def test_numeric_string_score_is_excluded(self) -> None:
        assert mutation_scores([_snap(score="0.5"), _snap(score=0.5)]) == [0.5]

    def test_scores_ignore_parse_ok(self) -> None:
        assert mutation_scores([_snap(score=0.2, parse_ok=False), _snap(score=0.1)]) == [0.2, 0.1]

    @pytest.mark.parametrize(
        "history",
        [
            [_snap(5)],
            [_snap(5), _snap(3)],
            [_snap(5), _snap(4), _snap(2)],
            [_snap(5), _snap(0)],
            [_snap(5, score=0.9), _snap(4, score=0.1)],
            [_snap(5), _snap(4, parse_ok=False)],
            [_snap(1, score=0.5), _snap(1, score=0.5)],
        ],
    )
    def test_judge_firing_implies_domain_membership(self, history: list) -> None:
        """判定核真开出某信号 ⇒ 该行必在该信号的可达域内（必要条件锁死）。"""
        verdict = detect_self_repair_trap(history)
        domains = signal_domains(history)
        for signal in verdict["signals"]:
            assert domains[signal] is True, (signal, history)
        if not verdict["suspected"]:
            return
        assert any(domains.values()), history


class TestSignalDomains:
    def test_single_point_history_is_in_no_domain(self) -> None:
        assert signal_domains([_snap(5)]) == dict.fromkeys(SIGNAL_MIN_POINTS, False)

    def test_two_parsed_points_enter_only_collapse(self) -> None:
        dom = signal_domains([_snap(5), _snap(3)])
        assert dom == {
            "assert_count_declining": False,
            "assertion_collapse": True,
            "mutation_score_declining": False,
        }

    def test_three_parsed_points_enter_declining_and_collapse(self) -> None:
        dom = signal_domains([_snap(5), _snap(4), _snap(3)])
        assert dom["assert_count_declining"] is True and dom["assertion_collapse"] is True

    def test_two_numeric_scores_enter_score_domain(self) -> None:
        assert signal_domains([_snap(score=0.8), _snap(score=0.2)])["mutation_score_declining"] is True

    def test_one_none_score_blocks_the_score_domain(self) -> None:
        assert signal_domains([_snap(score=0.8), _snap(score=None)])["mutation_score_declining"] is False

    def test_unparsable_last_point_blocks_both_assert_domains(self) -> None:
        dom = signal_domains([_snap(5), _snap(4), _snap(3, parse_ok=False)])
        assert dom["assert_count_declining"] is False and dom["assertion_collapse"] is False

    def test_domains_cover_exactly_the_judge_signals(self) -> None:
        assert set(SIGNAL_MIN_POINTS) == {"assert_count_declining", "assertion_collapse", "mutation_score_declining"}
        assert set(signal_domains([_snap(5), _snap(4)])) == set(SIGNAL_MIN_POINTS)


class TestTwoPointDeclineOutsideDomain:
    def test_decline_at_two_points_is_evidence_outside_the_gate(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(10), _snap(8)])) is True

    def test_increase_at_two_points_is_not_evidence(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(8), _snap(10)])) is False

    def test_equal_counts_are_not_a_decline(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(8), _snap(8)])) is False

    def test_three_point_decline_is_inside_the_gate_not_outside(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(10), _snap(8), _snap(6)])) is False

    def test_one_point_row_is_outside_scope_of_this_measure(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(10)])) is False

    def test_malformed_history_is_outside_scope(self) -> None:
        assert two_point_decline_outside_domain(_row("t", None)) is False

    def test_unparsable_last_point_is_not_counted_as_evidence(self) -> None:
        assert two_point_decline_outside_domain(_row("t", [_snap(10), _snap(8, parse_ok=False)])) is False


class TestDomainStats:
    def test_empty_arm_returns_zero_counts(self) -> None:
        out = self_repair_trap_domain_stats([])
        assert out["n_rows"] == 0
        assert out["n_with_verdict"] == 0
        assert out["signal_domain"] == dict.fromkeys(SIGNAL_MIN_POINTS, 0)
        assert out["reconciled"] is True

    def test_missing_arm_key_is_zero_counts_not_absent(self) -> None:
        assert self_repair_trap_domain_summary({"plain_llm": []})["plain_llm"]["n_rows"] == 0

    def test_arms_are_sorted(self) -> None:
        out = self_repair_trap_domain_summary({"z": [_row("a", [_snap()])], "a": [_row("b", [_snap()])]})
        assert list(out) == ["a", "z"]

    def test_mixed_fixture_bucket_and_domain_counts(self) -> None:
        rows = [
            _row("t1", [_snap(10), _snap(8)]),
            _row("t2", [_snap(5)]),
            _row("t3", None),
            {"task_id": "t4"},
        ]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_rows"] == 4 and out["n_with_verdict"] == 3
        assert out["not_recorded"] == 1 and out["history_malformed"] == 1
        assert out["below_min_floor"] == 1 and out["min_floor_reached"] == 1
        assert out["signal_domain"] == {
            "assert_count_declining": 0,
            "assertion_collapse": 1,
            "mutation_score_declining": 0,
        }
        assert out["n_decline2_outside_domain"] == 1
        assert out["mismatches"] == []  # 明细只点漂移行，干净行不许进

    def test_true_verdict_and_nonempty_signals_are_counted(self) -> None:
        rows = [_row("t", [_snap(5), _snap(0), _snap(0)], suspected=True, signals=["assertion_collapse"])]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_verdict_true"] == 1 and out["n_signals_nonempty"] == 1
        assert out["n_suspected_mismatch"] == 0 and out["reconciled"] is True

    def test_row_claiming_a_verdict_the_judge_did_not_make_is_a_mismatch(self) -> None:
        rows = [_row("t", [_snap(9), _snap(8)], suspected=True, signals=["assertion_collapse"])]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_suspected_mismatch"] == 1
        assert out["mismatches"] == ["t"]
        assert out["reconciled"] is True  # 对账跑通了，只是结论不一致

    def test_signals_only_drift_is_counted_separately(self) -> None:
        # 判定核在这份历史上真开火（declining），归档值同为 True 但信号名不同 ⇒ 只计信号漂移
        rows = [_row("t", [_snap(9), _snap(8), _snap(7)], suspected=True, signals=["assertion_collapse"])]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_suspected_mismatch"] == 0 and out["n_signals_mismatch"] == 1
        assert out["mismatches"] == ["t"]

    def test_mismatch_detail_is_capped_but_the_count_is_not(self) -> None:
        rows = [_row(f"t{i}", [_snap(9), _snap(8)], suspected=True) for i in range(25)]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_suspected_mismatch"] == 25 and len(out["mismatches"]) == 20

    def test_judge_exception_is_never_folded_into_consistent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_history):
            raise RuntimeError("判定核炸了")

        monkeypatch.setattr("src.tools.self_repair_trap.detect_self_repair_trap", _boom)
        out = self_repair_trap_domain_stats([_row("t", [_snap(5), _snap(4)])])
        assert out["n_rerun_error"] == 1 and out["reconciled"] is False

    def test_judge_unavailable_is_never_folded_into_consistent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "src.tools.self_repair_trap", None)
        rows = [_row("t", [_snap(5), _snap(4)]), _row("u", [_snap(5)])]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_rerun_error"] == out["n_with_verdict"] == 2
        assert out["reconciled"] is False

    def test_unreadable_snapshot_is_its_own_column(self) -> None:
        rows = [_row("t", [_snap("abc"), _snap(4)]), _row("u", [_snap(5), _snap(4)])]
        out = self_repair_trap_domain_stats(rows)
        assert out["n_unmeasurable"] == 1
        assert out["n_rerun_error"] == 1  # 判定核同一条 int() 路径，同样抛错
        assert sum(out["signal_domain"].values()) == 1  # 读不懂的行不占任何可达域
        assert out["reconciled"] is False
        assert out["below_min_floor"] + out["min_floor_reached"] == 2  # 档位仍由点数决定

    def test_non_dict_rows_are_dropped_before_bucketing(self) -> None:
        out = self_repair_trap_domain_stats([None, "x", _row("t", [_snap()])])  # type: ignore[list-item]
        assert out["n_rows"] == 1


class TestThresholdSourceLock:
    """阈值常量与判定核字面量同源；读侧不许重打一遍数字。"""

    def test_signal_min_points_equals_the_judge_literals(self) -> None:
        gates = _judge_gates()
        assert {name: thr for name, (recv, thr) in gates.items()} == SIGNAL_MIN_POINTS

    def test_judge_measures_the_sequences_the_read_side_documents(self) -> None:
        gates = _judge_gates()
        assert gates["assert_count_declining"][0] == "counts"
        assert gates["assertion_collapse"][0] == "counts"
        assert gates["mutation_score_declining"][0] == "scores"

    def test_read_side_reads_the_shared_constant_not_retyped_literals(self) -> None:
        tree = ast.parse((ROOT / "experiments" / "_trap_input_domain.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "signal_domains")
        gates = [node for node in ast.walk(fn) if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.GtE)]
        assert len(gates) == len(SIGNAL_MIN_POINTS)
        for node in gates:
            right = node.comparators[0]
            assert isinstance(right, ast.Subscript), ast.unparse(node)
            assert isinstance(right.value, ast.Name) and right.value.id == "SIGNAL_MIN_POINTS"

    def test_decline_gate_also_reads_the_shared_constant(self) -> None:
        tree = ast.parse((ROOT / "experiments" / "_trap_input_domain.py").read_text(encoding="utf-8"))
        fn = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "two_point_decline_outside_domain"
        )
        subs = {
            node.value.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
        }
        assert "SIGNAL_MIN_POINTS" in subs
        # 下界必须是字面量 2 的显式检查（否则 counts 短于 2 会 IndexError）
        assert any(isinstance(node, ast.Constant) and node.value == 2 for node in ast.walk(fn)), (
            "缺少 len(counts) >= 2 的下界"
        )

    def test_write_side_still_publishs_the_judges_verdict(self) -> None:
        """BU 只加读侧：结果行仍逐字透出判定核的 suspected / signals。"""
        tree = ast.parse((ROOT / "experiments" / "run_benchmark.py").read_text(encoding="utf-8"))
        pairs: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                if isinstance(key, ast.Constant) and key.value in (TRAP_VERDICT_KEY, TRAP_SIGNALS_KEY):
                    pairs[key.value] = ast.unparse(value)
        # ast.unparse 出单引号（源码写的是双引号），比较按 unparse 形态
        assert pairs[TRAP_VERDICT_KEY] == "_trap['suspected']"
        assert pairs[TRAP_SIGNALS_KEY] == "_trap['signals']"


class TestReportSurface:
    @staticmethod
    def _analysis(rows: list[dict]) -> dict[str, Any]:
        return ar_mod.build_analysis(
            {
                "dataset": "demo",
                "results": {
                    "aitester": {
                        "details": rows,
                        "total_functions": len(rows),
                        "passed_count": sum(1 for r in rows if r.get("passed")),
                        "success_rate": 100.0,
                        "avg_coverage": 0.3,
                        "avg_iterations": 1.5,
                        "avg_elapsed_seconds": 1.5,
                        "total_time": 3.0,
                    }
                },
            }
        )

    @staticmethod
    def _fixture_rows() -> list[dict]:
        return [
            {
                "task_id": "t1",
                "passed": True,
                TRAP_VERDICT_KEY: False,
                TRAP_SIGNALS_KEY: [],
                TRAP_HISTORY_KEY: [_snap(10), _snap(8)],
            },
            {
                "task_id": "t2",
                "passed": True,
                TRAP_VERDICT_KEY: False,
                TRAP_SIGNALS_KEY: [],
                TRAP_HISTORY_KEY: [_snap(5)],
            },
            {"task_id": "t3", "passed": True, TRAP_VERDICT_KEY: False, TRAP_SIGNALS_KEY: [], TRAP_HISTORY_KEY: None},
            {"task_id": "t4", "passed": True},
        ]

    def test_build_analysis_exposes_the_new_key(self) -> None:
        per = self._analysis(self._fixture_rows())["per_baseline"]["aitester"]
        assert per["self_repair_trap_domain"]["n_with_verdict"] == 3

    def test_new_key_moves_no_existing_judgment_value(self) -> None:
        with_trap = self._analysis(self._fixture_rows())["per_baseline"]["aitester"]
        without = [
            {k: v for k, v in r.items() if k not in (TRAP_VERDICT_KEY, TRAP_SIGNALS_KEY, TRAP_HISTORY_KEY)}
            for r in self._fixture_rows()
        ]
        base = self._analysis(without)["per_baseline"]["aitester"]
        for key in ("total_functions", "passed_count", "success_rate", "avg_coverage"):
            assert with_trap[key] == base[key], key

    def test_table_shows_all_cells_of_the_pinned_fixture(self) -> None:
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        assert "| aitester | 4 | 3 | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0/0 |" in md
        assert "| **合计** | 4 | 3 | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0/0 |" in md

    def test_table_carries_the_mismatch_cells_in_both_rows(self) -> None:
        """不一致列两行都得真取数：归档行与判定核重跑不符时必须露出，不许恒显 0/0。"""
        rows = [_row("t", [_snap(9), _snap(8)], suspected=True, signals=["assertion_collapse"])]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "| aitester | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 1 | 1 | 1/1 |" in md
        assert "| **合计** | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 1 | 1 | 1/1 |" in md

    def test_bu_table_rows_share_one_cell_count(self) -> None:
        """表头 / 分隔 / 数据行的列数必须一致——少一列表头不该通过任何门禁。"""
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        lines = md.splitlines()
        heading = "## Self-Repair Trap 判定核的输入可达域（BU：`self_repair_trap_*` 的读侧）"
        table: list[str] = []
        for ln in lines[lines.index(heading) + 1 :]:
            if ln.startswith("|"):
                table.append(ln)
            elif table:
                break
        assert [len(ln.split("|")) - 2 for ln in table] == [13, 13, 13, 13], table

    def test_empty_domain_note_appears_only_when_declining_domain_is_zero(self) -> None:
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        assert "**`assert_count_declining` 的输入域在本语料是空集**" in md
        three_points = [
            *self._fixture_rows(),
            {
                "task_id": "t5",
                "passed": True,
                TRAP_VERDICT_KEY: False,
                TRAP_SIGNALS_KEY: [],
                TRAP_HISTORY_KEY: [_snap(10), _snap(8), _snap(6)],
            },
        ]
        md2 = ar_mod.render_markdown(self._analysis(three_points), "demo.json")
        assert "**`assert_count_declining` 的输入域在本语料是空集**" not in md2
        assert "| 1 | 2 |" in md2  # declining 可达 = 1、collapse 可达 = 2

    def test_arm_without_any_verdict_key_is_named_not_dropped(self) -> None:
        rows = [{"task_id": "t1", "passed": True}, {"task_id": "t2", "passed": False}]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "个臂的结果行两个键都没落盘" in md
        assert "`aitester`" in md
        assert "不是「都判过且不怀疑」" in md

    def test_section_absent_when_no_rows_at_all(self) -> None:
        md = ar_mod.render_markdown(self._analysis([]), "demo.json")
        assert "## Self-Repair Trap 判定核的输入可达域" not in md

    def test_footnotes_keep_both_calibers(self) -> None:
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        assert "`未记录` = 行内没有 `self_repair_trap_suspected` 键" in md
        assert "判定核走「结构异常 ⇒ 不怀疑」分支" in md
        assert "回答的是**输入够不够**，不是判没判出来" in md
        assert "证据存在、判据看不见" in md

    def test_rerun_error_is_printed_only_when_it_exists(self) -> None:
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        assert "对账异常（同进程重跑判定核抛错）" not in md

    def test_rerun_error_note_names_the_count_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_history):
            raise RuntimeError("判定核炸了")

        monkeypatch.setattr("src.tools.self_repair_trap.detect_self_repair_trap", _boom)
        md = ar_mod.render_markdown(self._analysis([_row("t", [_snap(5), _snap(4)])]), "demo.json")
        assert "对账异常（同进程重跑判定核抛错）= 1 行，单列不折成「一致」" in md

    def test_silent_arm_note_absent_when_every_row_has_a_verdict(self) -> None:
        rows = [_row("t", [_snap(5), _snap(4)]), _row("u", [_snap(3)])]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "个臂的结果行两个键都没落盘" not in md

    def test_footnote_thresholds_read_the_shared_constant(self) -> None:
        """门槛只有一处事实源：报告面脚注与空集点名必须跟着常量走，不许重打字面量。"""
        original = dict(ar_mod.SIGNAL_MIN_POINTS)
        try:
            ar_mod.SIGNAL_MIN_POINTS.update(
                {"assert_count_declining": 4, "assertion_collapse": 5, "mutation_score_declining": 6}
            )
            md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
            assert "`declining 可达` 需 ≥4 个可解析点" in md
            assert "`collapse 可达` 需 ≥5 个可解析点" in md
            assert "`score 可达` 需 ≥6 个非 `None` 变异分数" in md
            assert "没有任何一行给出 ≥4 个可解析断言计数" in md
        finally:
            ar_mod.SIGNAL_MIN_POINTS.clear()
            ar_mod.SIGNAL_MIN_POINTS.update(original)

    def test_existing_sections_render_unchanged(self) -> None:
        md = ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")
        assert "## 验收 oracle 来源与可见性（BT：`oracle_type` / `test_visible_to_system` 的读侧）" in md


class TestPinnedBatches:
    """三份具名冻结批次的逐档读数（BU 手册 §3 复现项）。"""

    @pytest.mark.parametrize("rel", sorted(PINNED_BATCHES))
    def test_pinned_batch_readings(self, rel: str) -> None:
        path = ROOT / rel
        if not path.exists():
            pytest.skip(f"批次工件不在本地：{rel}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            r
            for blk in (doc.get("results") or {}).values()
            for r in (blk or {}).get("details") or []
            if isinstance(r, dict)
        ]
        out = self_repair_trap_domain_stats(rows)
        want = PINNED_BATCHES[rel]
        got = {
            "n_rows": out["n_rows"],
            "n_with_verdict": out["n_with_verdict"],
            "not_recorded": out["not_recorded"],
            "history_malformed": out["history_malformed"],
            "below_min_floor": out["below_min_floor"],
            "min_floor_reached": out["min_floor_reached"],
            "declining": out["signal_domain"]["assert_count_declining"],
            "collapse": out["signal_domain"]["assertion_collapse"],
            "score": out["signal_domain"]["mutation_score_declining"],
            "n_decline2_outside_domain": out["n_decline2_outside_domain"],
            "n_verdict_true": out["n_verdict_true"],
            "n_signals_nonempty": out["n_signals_nonempty"],
            "n_suspected_mismatch": out["n_suspected_mismatch"],
            "n_signals_mismatch": out["n_signals_mismatch"],
            "n_unmeasurable": out["n_unmeasurable"],
        }
        assert got == want, rel
        assert (
            out["not_recorded"] + out["history_malformed"] + out["below_min_floor"] + out["min_floor_reached"]
            == out["n_rows"]
        ), rel
        assert out["reconciled"] is True, rel

    def test_the_twelve_malformed_rows_are_all_in_one_named_batch(self) -> None:
        pytest.skip(
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
        """归档里「历史键在但值为 null」只此一档 12 行——点名，不并档。"""
        total = 0
        hits: list[str] = []
        for path in sorted((ROOT / "experiments" / "results").rglob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
                continue
            rows = [
                r for blk in doc["results"].values() for r in (blk or {}).get("details") or [] if isinstance(r, dict)
            ]
            n = self_repair_trap_domain_stats(rows)["history_malformed"]
            if n:
                hits.append(str(path.relative_to(ROOT)))
                total += n
        assert (total, hits) == (12, list(PINNED_BATCHES)[:1]), hits


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
