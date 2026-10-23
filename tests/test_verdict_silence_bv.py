"""BV 轮（2026-10-23）：批次 VIII / XIV 两份判定核的「沉默」从未披露 —— 收口锁。

缺陷形态（零 LLM；普查工具 `scripts/tools/bv_verdict_silence_census.py`）：
两组判定键自写入起在报告面**零读者**（BU 普查 11 键池里的两项），而两者的
「没看」与「看过且干净」在结果行里同形：

- `test_hacking_suspected` / `test_hacking_signals`（批次 VIII，ADR-0022）：判定核在
  无原码 / 无补丁 / 原码解析失败 / 补丁解析失败时返回 `suspected=False, signals=[]`；
  归档 5935 行里 20 行 `suspected=True`（12 硬编码输入分支 + 8 新增吞异常）从未出现在
  任何报告面，其余 5915 行的「不怀疑」分不清是判干净还是没看。
- `fl_constraint_verdict` / `_hit_rank` / `_changed_functions`（批次 XIV，ADR-0028）：
  六种早退成因共用一个 `not_evaluable`（归档 4442/5935 = 74.8%），报告面连这个标签都不读；
  已求值的 1493 行是 hit 1487 / miss 6（hit 比 99.60%）——一条几乎不区分的「约束门」。

修复口径：**写侧只补求值状态 / 早退成因（增量，判定值语义零变化），读侧只补分档与对账**。
不动判定核的判定方向、不回填任何历史行的值、不进入任何判定。

锁的形状（沿用 BQ/BT/BU 纪律）：全归档读数（11197 / 5935 / 20 / 4442 / 1487 / 6 …）是
**实测读数**，登记在手册并附复现命令，不在这里锁死（新批次一旦落盘就会漂移）。本文件锁的是：
①状态/成因词表与判定核同源、②七个早退分支的成因归属、③写侧三键与单次计算、
④分档恒等式与推断口径、⑤报告面逐格与四条脚注、⑥四份具名冻结批次的逐档读数。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_results as ar_mod
import experiments.run_benchmark as rb_mod
from experiments._verdict_silence import (
    FL_BASIS_INFERRED,
    FL_BASIS_NOT_APPLICABLE,
    FL_BASIS_RECORDED,
    FL_BASIS_UNRECORDED_VERDICT,
    FL_CHANGED_KEY,
    FL_HIT_RANK_KEY,
    FL_INFERRED_NO_CHANGED_FUNCTIONS,
    FL_INFERRED_NO_LOCALIZATION,
    FL_INFERRED_NO_PATCH,
    FL_INFERRED_UNATTRIBUTED,
    FL_INFERRED_VOCAB,
    FL_REASON_ERROR,
    FL_REASON_KEY,
    FL_REASON_NO_CANDIDATES,
    FL_REASON_NO_CHANGED_FUNCTIONS,
    FL_REASON_NO_LOCALIZATION,
    FL_REASON_NO_ORIGINAL_CODE,
    FL_REASON_NO_PATCH,
    FL_REASON_NO_STATE,
    FL_REASON_OK,
    FL_REASON_VOCAB,
    FL_VERDICT_KEY,
    HACK_SIGNALS_KEY,
    HACK_SIGNAL_NAMES,
    HACK_STATUS_DETECTOR_ERROR,
    HACK_STATUS_EMPTY_ORIGINAL,
    HACK_STATUS_EMPTY_PATCH,
    HACK_STATUS_KEY,
    HACK_STATUS_OK,
    HACK_STATUS_PARSE_ERROR_ORIGINAL,
    HACK_STATUS_PARSE_ERROR_PATCHED,
    HACK_STATUS_UNRECORDED,
    HACK_STATUS_VOCAB,
    HACK_SUSPECTED_KEY,
    fl_changed_functions,
    fl_evaluated,
    fl_reason,
    fl_reason_mismatch,
    fl_verdict,
    hack_evaluated,
    hack_signals,
    hack_status,
    infer_fl_reason,
)
from experiments.statistical_analysis import detector_silence_stats
from src.tools.patch_test_hacking import (
    detect_test_hacking,
    hacking_evaluation_status_names,
    hacking_signal_names,
)

ROOT = Path(__file__).resolve().parents[1]

#: 具名冻结批次：逐档读数由 `scripts/tools/bv_verdict_silence_census.py --segment c` 复核。
#: 四份覆盖四种形态：全 legacy 未记录（pre-VIII）、单臂大批、quixbugs 推断含「无定位」、
#: 含 miss 的小批。锁的是"分档在这个批次上读作什么"，不是"归档一共多少行"。
PINNED_BATCHES: dict[str, dict[str, int]] = {
    "experiments/results/main_batch/benchmark_synthetic_20261007_185941.json": {
        "n_rows": 261,
        "hack_verdict_recorded": 0,
        "hack_status_unrecorded": 0,
        "hack_evaluated": 0,
        "hack_suspected": 0,
        "fl_hit": 0,
        "fl_miss": 0,
        "fl_not_evaluable": 0,
        "fl_reason_inferred": 0,
        "fl_changed_0": 0,
    },
    "experiments/results/t_round_b2_main_batch_20261018/seed44/benchmark_synthetic_20261018_120845.json": {
        "n_rows": 261,
        "hack_verdict_recorded": 261,
        "hack_status_unrecorded": 261,
        "hack_evaluated": 0,
        "hack_suspected": 1,
        "fl_hit": 14,
        "fl_miss": 0,
        "fl_not_evaluable": 247,
        "fl_reason_inferred": 247,
        "fl_changed_0": 247,
    },
    "experiments/results/spec_ab_quixbugs_20261012/replace/benchmark_quixbugs_20261012_190733.json": {
        "n_rows": 50,
        "hack_verdict_recorded": 50,
        "hack_status_unrecorded": 50,
        "hack_evaluated": 0,
        "hack_suspected": 1,
        "fl_hit": 33,
        "fl_miss": 0,
        "fl_not_evaluable": 17,
        "fl_reason_inferred": 17,
        "fl_changed_0": 17,
    },
    "experiments/results/t_round_a19_default_gate_20261018/arm_on/benchmark_synthetic_20261018_092238.json": {
        "n_rows": 10,
        "hack_verdict_recorded": 10,
        "hack_status_unrecorded": 10,
        "hack_evaluated": 0,
        "hack_suspected": 0,
        "fl_hit": 8,
        "fl_miss": 1,
        "fl_not_evaluable": 1,
        "fl_reason_inferred": 1,
        "fl_changed_0": 1,
    },
}

#: 冻结批次的推断成因分布（与上面的逐档读数分开列：两个维度都要能钉住）。
PINNED_INFERRED: dict[str, dict[str, int]] = {
    "experiments/results/main_batch/benchmark_synthetic_20261007_185941.json": {},
    "experiments/results/t_round_b2_main_batch_20261018/seed44/benchmark_synthetic_20261018_120845.json": {
        FL_INFERRED_NO_PATCH: 247
    },
    "experiments/results/spec_ab_quixbugs_20261012/replace/benchmark_quixbugs_20261012_190733.json": {
        FL_INFERRED_NO_LOCALIZATION: 15,
        FL_INFERRED_NO_PATCH: 2,
    },
    "experiments/results/t_round_a19_default_gate_20261018/arm_on/benchmark_synthetic_20261018_092238.json": {
        FL_INFERRED_NO_CHANGED_FUNCTIONS: 1
    },
}


# ═══ 夹具 ═══════════════════════════════════════════════════════════════════════


def _hack_row(
    task_id: str = "t",
    *,
    status: str | None = HACK_STATUS_OK,
    suspected: bool = False,
    signals: tuple[str, ...] = (),
    include_verdict: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id, "passed": True}
    if include_verdict:
        row[HACK_SUSPECTED_KEY] = suspected
        row[HACK_SIGNALS_KEY] = list(signals)
    if status is not None:
        row[HACK_STATUS_KEY] = status
    return row


def _fl_row(
    task_id: str = "t",
    *,
    verdict: str = "not_evaluable",
    reason: str | None = None,
    changed: tuple[str, ...] = (),
    hit_rank: int | None = None,
    patch: str | None = "--- patch ---",
    localization: bool = True,
    include_verdict: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id, "passed": True}
    if include_verdict:
        row[FL_VERDICT_KEY] = verdict
        row[FL_HIT_RANK_KEY] = hit_rank
        row[FL_CHANGED_KEY] = list(changed)
    if patch is not None:
        row["patch"] = patch
    if localization:
        row["llm_localization"] = {"candidates": [{"function_name": "f"}]}
    if reason is not None:
        row[FL_REASON_KEY] = reason
    return row


class _Task:
    """最小任务桩：判定核只读 `instance_code`。"""

    def __init__(self, code: str, task_id: str = "t") -> None:
        self.instance_code = code
        self.task_id = task_id


_ORIG = "def f(x):\n    return x\n"
_PATCHED_HARDCODED = "def f(x):\n    if x == 3:\n        return 99\n    return x\n"
_PATCHED_CLEAN = "def f(x):\n    return x + 1\n"


# ═══ 1. 词表与判定核同源 ═══════════════════════════════════════════════════════


class TestStatusVocab:
    def test_read_side_vocab_matches_detector_vocab(self) -> None:
        assert hacking_evaluation_status_names() == HACK_STATUS_VOCAB

    def test_signal_vocab_matches_detector_vocab(self) -> None:
        assert hacking_signal_names() == HACK_SIGNAL_NAMES

    def test_ok_is_the_only_evaluated_member(self) -> None:
        assert [s for s in HACK_STATUS_VOCAB if s == HACK_STATUS_OK] == [HACK_STATUS_OK]
        assert HACK_STATUS_DETECTOR_ERROR not in HACK_STATUS_VOCAB
        assert HACK_STATUS_UNRECORDED not in HACK_STATUS_VOCAB

    def test_verdict_vocab_is_the_documented_three(self) -> None:
        assert FL_REASON_VOCAB[0] == FL_REASON_OK
        assert FL_REASON_NO_STATE in FL_REASON_VOCAB
        assert FL_REASON_NO_CANDIDATES in FL_REASON_VOCAB
        assert FL_REASON_ERROR in FL_REASON_VOCAB
        assert len(set(FL_REASON_VOCAB)) == len(FL_REASON_VOCAB)

    def test_recorded_vocabulary_literals_are_a_wire_contract(self) -> None:
        """成因名会落进结果行 JSON（`fl_constraint_reason`）：改名等于改工件契约。

        这条钉的是**字符串本身**，不是常量身份——V04 变异（把
        `no_candidates` 改成 `no_candidate`）只有字面量锁能杀：模块内所有
        比较都走常量，改名在代码面上自洽，但历史新批次行会读不出来。
        """
        assert FL_REASON_VOCAB == (
            "ok",
            "no_state",
            "no_patch",
            "no_localization",
            "no_original_code",
            "no_changed_functions",
            "no_candidates",
            "error",
        )
        assert FL_INFERRED_VOCAB == (
            "inferred_no_patch",
            "inferred_no_localization",
            "inferred_no_changed_functions",
            "inferred_unattributed",
        )

    def test_inferred_vocab_is_a_lower_bound_of_recorded_causes(self) -> None:
        # 推断只能看到三支 + 无法归因；「无原码 / 无候选 / 异常」不在推断词表里。
        assert FL_INFERRED_UNATTRIBUTED in FL_INFERRED_VOCAB
        assert set(FL_INFERRED_VOCAB).isdisjoint(FL_REASON_VOCAB)


# ═══ 2. 判定核状态（写侧最小单元） ═════════════════════════════════════════════


class TestDetectorStatus:
    @pytest.mark.parametrize(
        ("orig", "patched", "expected"),
        [
            ("", _PATCHED_CLEAN, HACK_STATUS_EMPTY_ORIGINAL),
            ("   ", _PATCHED_CLEAN, HACK_STATUS_EMPTY_ORIGINAL),
            (_ORIG, "", HACK_STATUS_EMPTY_PATCH),
            ("def f(:\n", _PATCHED_CLEAN, HACK_STATUS_PARSE_ERROR_ORIGINAL),
            (_ORIG, "def f(:\n", HACK_STATUS_PARSE_ERROR_PATCHED),
        ],
    )
    def test_every_silent_cause_gets_its_own_status(self, orig: str, patched: str, expected: str) -> None:
        out = detect_test_hacking(orig, patched)
        assert out["status"] == expected
        assert out["suspected"] is False
        assert out["signals"] == []

    def test_clean_patch_is_ok_not_silent(self) -> None:
        out = detect_test_hacking(_ORIG, _PATCHED_CLEAN)
        assert out == {"suspected": False, "signals": [], "status": HACK_STATUS_OK}

    def test_hit_keeps_status_ok_and_signal_names(self) -> None:
        out = detect_test_hacking(_ORIG, _PATCHED_HARDCODED)
        assert out["status"] == HACK_STATUS_OK
        assert out["suspected"] is True
        assert out["signals"] == ["hardcoded_input_branch"]

    def test_status_is_always_in_vocabulary(self) -> None:
        cases = [
            ("", ""),
            ("", _PATCHED_CLEAN),
            (_ORIG, ""),
            ("def f(:\n", _PATCHED_CLEAN),
            (_ORIG, "def f(:\n"),
            (_ORIG, _PATCHED_CLEAN),
            (_ORIG, _PATCHED_HARDCODED),
        ]
        assert {detect_test_hacking(o, p)["status"] for o, p in cases} == set(HACK_STATUS_VOCAB)

    def test_suspected_only_true_when_ok(self) -> None:
        for orig, patched in [("", _PATCHED_CLEAN), (_ORIG, ""), ("def f(:\n", _PATCHED_CLEAN), (_ORIG, "def f(:\n")]:
            out = detect_test_hacking(orig, patched)
            assert out["suspected"] is False, (orig, patched)


# ═══ 3. 写侧接线：结果行三键、单次计算、七种成因 ═══════════════════════════════


class TestHackResultWiring:
    def test_no_state_is_empty_patch(self) -> None:
        assert rb_mod._test_hacking_result(_Task(_ORIG), None)["status"] == HACK_STATUS_EMPTY_PATCH

    def test_blank_patch_is_empty_patch(self) -> None:
        out = rb_mod._test_hacking_result(_Task(_ORIG), {"patch": "   "})
        assert out["status"] == HACK_STATUS_EMPTY_PATCH

    def test_missing_instance_code_is_empty_original(self) -> None:
        out = rb_mod._test_hacking_result(_Task(""), {"patch": _PATCHED_CLEAN})
        assert out["status"] == HACK_STATUS_EMPTY_ORIGINAL

    def test_ok_path_passes_detector_status_through(self) -> None:
        out = rb_mod._test_hacking_result(_Task(_ORIG), {"patch": _PATCHED_HARDCODED})
        assert out["status"] == HACK_STATUS_OK and out["suspected"] is True

    def test_call_site_exception_is_detector_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import experiments._m1_metrics as m1

        def _boom(_orig: str, _patch: str) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(m1, "_target_code_after_patch", _boom)
        out = rb_mod._test_hacking_result(_Task(_ORIG), {"patch": _PATCHED_CLEAN})
        assert out == {"suspected": False, "signals": [], "status": HACK_STATUS_DETECTOR_ERROR}

    def test_row_assembly_writes_the_three_keys_and_calls_once(self) -> None:
        tree = ast.parse(Path(rb_mod.__file__).read_text(encoding="utf-8"))
        target = next(
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_build_task_result"
        )
        calls = [
            node
            for node in ast.walk(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_test_hacking_result"
        ]
        assert len(calls) == 1, "判定核必须单次计算（此前结果行两键各调一次 = AST 差集跑两遍）"
        keys = {
            node.value for node in ast.walk(target) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert {HACK_SUSPECTED_KEY, HACK_SIGNALS_KEY, HACK_STATUS_KEY} <= keys
        # 键在还不够：三键必须各自取判定核的对应字段（十字串接会让 status 落成信号列表）。
        source = Path(rb_mod.__file__).read_text(encoding="utf-8")
        assert f'"{HACK_SUSPECTED_KEY}": _hack["suspected"],' in source
        assert f'"{HACK_SIGNALS_KEY}": _hack["signals"],' in source
        assert f'"{HACK_STATUS_KEY}": _hack["status"],' in source

    def test_failure_branch_declares_empty_patch(self) -> None:
        source = Path(rb_mod.__file__).read_text(encoding="utf-8")
        assert f'"{HACK_STATUS_KEY}": "{HACK_STATUS_EMPTY_PATCH}"' in source
        assert f'"{FL_REASON_KEY}": FL_REASON_NO_STATE' in source


class TestFlReasonWiring:
    def test_no_state(self) -> None:
        assert rb_mod._fl_constraint_result(_Task(_ORIG), None)["reason"] == FL_REASON_NO_STATE

    def test_no_patch(self) -> None:
        assert (
            rb_mod._fl_constraint_result(_Task(_ORIG), {"llm_localization": {"candidates": []}})["reason"]
            == FL_REASON_NO_PATCH
        )

    def test_no_localization(self) -> None:
        out = rb_mod._fl_constraint_result(_Task(_ORIG), {"patch": _PATCHED_CLEAN})
        assert out["reason"] == FL_REASON_NO_LOCALIZATION

    def test_no_original_code(self) -> None:
        state = {"patch": _PATCHED_CLEAN, "llm_localization": {"candidates": [{"function_name": "f"}]}}
        assert rb_mod._fl_constraint_result(_Task(""), state)["reason"] == FL_REASON_NO_ORIGINAL_CODE

    def test_no_changed_functions(self) -> None:
        state = {"patch": "", "llm_localization": {"candidates": [{"function_name": "f"}]}}
        state["patch"] = "   \n"
        assert rb_mod._fl_constraint_result(_Task(_ORIG), state)["reason"] == FL_REASON_NO_PATCH

    def test_no_changed_functions_when_patch_changes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.agents.fault_localizer as fl_mod

        monkeypatch.setattr(fl_mod, "patch_changed_functions", lambda *_a, **_k: set())
        state = {"patch": _PATCHED_CLEAN, "llm_localization": {"candidates": [{"function_name": "f"}]}}
        out = rb_mod._fl_constraint_result(_Task(_ORIG), state)
        assert out["reason"] == FL_REASON_NO_CHANGED_FUNCTIONS
        assert out["verdict"] == "not_evaluable" and out["changed_functions"] == []

    def test_no_candidates(self) -> None:
        state = {"patch": _PATCHED_CLEAN, "llm_localization": {"candidates": [{"function_name": ""}]}}
        out = rb_mod._fl_constraint_result(_Task(_ORIG), state)
        assert out["reason"] == FL_REASON_NO_CANDIDATES
        assert out["verdict"] == "not_evaluable"

    def test_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import experiments._m1_metrics as m1

        def _boom(*_a: Any, **_k: Any) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(m1, "_target_code_after_patch", _boom)
        state = {"patch": _PATCHED_CLEAN, "llm_localization": {"candidates": [{"function_name": "f"}]}}
        assert rb_mod._fl_constraint_result(_Task(_ORIG), state)["reason"] == FL_REASON_ERROR

    def test_ok_path_keeps_hit_verdict_and_rank(self) -> None:
        state = {"patch": _PATCHED_HARDCODED, "llm_localization": {"candidates": [{"function_name": "f"}]}}
        out = rb_mod._fl_constraint_result(_Task(_ORIG), state)
        assert out["verdict"] == "hit" and out["hit_rank"] == 1 and out["reason"] == FL_REASON_OK

    def test_miss_verdict_semantics_unchanged(self) -> None:
        loc = {"candidates": [{"function_name": "other"}]}
        state = {"patch": _PATCHED_HARDCODED, "llm_localization": loc}
        out = rb_mod._fl_constraint_result(_Task(_ORIG), state)
        assert out["verdict"] == "miss" and out["hit_rank"] is None and out["reason"] == FL_REASON_OK

    def test_every_reason_is_in_vocabulary(self) -> None:
        states = [
            None,
            {"llm_localization": {"candidates": [{"function_name": "f"}]}},
            {"patch": _PATCHED_CLEAN},
            {"patch": _PATCHED_CLEAN, "llm_localization": {"candidates": [{"function_name": ""}]}},
            {"patch": _PATCHED_HARDCODED, "llm_localization": {"candidates": [{"function_name": "f"}]}},
        ]
        reasons = {rb_mod._fl_constraint_result(_Task(_ORIG), s)["reason"] for s in states}
        assert reasons <= set(FL_REASON_VOCAB)
        assert FL_REASON_OK in reasons


# ═══ 4. 读侧分类器 ═════════════════════════════════════════════════════════════


class TestHackClassifier:
    def test_no_verdict_key(self) -> None:
        assert hack_status({"task_id": "t"}) == "no_verdict"

    def test_verdict_without_status_is_unrecorded_not_ok(self) -> None:
        assert hack_status(_hack_row(status=None)) == HACK_STATUS_UNRECORDED
        assert hack_evaluated(_hack_row(status=None)) is False

    def test_ok_is_evaluated(self) -> None:
        assert hack_evaluated(_hack_row(status=HACK_STATUS_OK)) is True

    def test_silent_statuses_are_not_evaluated(self) -> None:
        for status in (HACK_STATUS_EMPTY_ORIGINAL, HACK_STATUS_EMPTY_PATCH, HACK_STATUS_DETECTOR_ERROR):
            assert hack_evaluated(_hack_row(status=status)) is False, status

    def test_out_of_vocabulary_status_is_prefixed(self) -> None:
        assert hack_status(_hack_row(status="weird")) == "other:weird"

    def test_signals_drop_non_strings(self) -> None:
        row = _hack_row(signals=())
        row[HACK_SIGNALS_KEY] = ["assert_weakened", 3, None]
        assert hack_signals(row) == ["assert_weakened"]
        row[HACK_SIGNALS_KEY] = "assert_weakened"
        assert hack_signals(row) == []


class TestFlClassifier:
    def test_no_verdict_key(self) -> None:
        assert fl_verdict({"task_id": "t"}) == "no_verdict"

    def test_null_verdict_reads_as_not_evaluable(self) -> None:
        """失败分支显式写 `None`：语义是「无终局状态 ⇒ 不可评估」，不是"判定值缺失"。"""
        row = _fl_row("a", verdict="not_evaluable", reason=FL_REASON_NO_STATE)
        row[FL_VERDICT_KEY] = None
        assert fl_verdict(row) == "not_evaluable"
        assert fl_reason(row) == (FL_REASON_NO_STATE, FL_BASIS_RECORDED)
        assert fl_evaluated(row) is False
        legacy = _fl_row("b", verdict="not_evaluable", patch=None)
        legacy[FL_VERDICT_KEY] = None
        assert fl_reason(legacy) == (FL_INFERRED_NO_PATCH, FL_BASIS_INFERRED)

    def test_out_of_vocabulary_verdict_is_prefixed(self) -> None:
        assert fl_verdict(_fl_row(verdict="maybe")) == "other:maybe"

    @pytest.mark.parametrize(
        ("patch", "localization", "changed", "expected"),
        [
            (None, True, (), FL_INFERRED_NO_PATCH),
            ("  ", True, (), FL_INFERRED_NO_PATCH),
            ("--- p ---", False, (), FL_INFERRED_NO_LOCALIZATION),
            ("--- p ---", True, (), FL_INFERRED_NO_CHANGED_FUNCTIONS),
            ("--- p ---", True, ("f",), FL_INFERRED_UNATTRIBUTED),
        ],
    )
    def test_inference_covers_three_causes_plus_unattributed(
        self, patch: str | None, localization: bool, changed: tuple[str, ...], expected: str
    ) -> None:
        row = _fl_row(verdict="not_evaluable", patch=patch, localization=localization, changed=changed)
        assert infer_fl_reason(row) == expected

    def test_recorded_reason_wins_over_inference(self) -> None:
        row = _fl_row(verdict="not_evaluable", reason=FL_REASON_NO_ORIGINAL_CODE)
        assert fl_reason(row) == (FL_REASON_NO_ORIGINAL_CODE, FL_BASIS_RECORDED)

    def test_legacy_row_without_reason_is_inferred_not_recorded(self) -> None:
        row = _fl_row(verdict="not_evaluable")
        reason, basis = fl_reason(row)
        assert basis == FL_BASIS_INFERRED
        assert reason in FL_INFERRED_VOCAB

    def test_hit_needs_no_cause_key(self) -> None:
        assert fl_reason(_fl_row(verdict="hit", changed=("f",), hit_rank=1)) == (
            FL_REASON_OK,
            FL_BASIS_NOT_APPLICABLE,
        )

    def test_missing_verdict_key_has_its_own_basis(self) -> None:
        assert fl_reason({"task_id": "t"})[1] == FL_BASIS_UNRECORDED_VERDICT

    def test_evaluated_only_for_hit_and_miss_with_ok_cause(self) -> None:
        assert fl_evaluated(_fl_row(verdict="hit", changed=("f",), hit_rank=1)) is True
        assert fl_evaluated(_fl_row(verdict="not_evaluable")) is False
        # 判定 hit 却落了早退成因 = 写侧矛盾，读侧不认这是"求值过"
        assert fl_evaluated(_fl_row(verdict="hit", reason=FL_REASON_NO_PATCH)) is False

    def test_reason_mismatch_is_named(self) -> None:
        assert fl_reason_mismatch(_fl_row(verdict="hit", reason=FL_REASON_NO_PATCH)) is True
        assert fl_reason_mismatch(_fl_row(verdict="not_evaluable", reason=FL_REASON_OK)) is True
        assert fl_reason_mismatch(_fl_row(verdict="hit", reason=FL_REASON_OK)) is False
        assert fl_reason_mismatch(_fl_row(verdict="not_evaluable", reason=FL_REASON_NO_PATCH)) is False

    def test_changed_functions_drop_non_strings(self) -> None:
        row = _fl_row(verdict="hit", changed=())
        row[FL_CHANGED_KEY] = ["f", 7]
        assert fl_changed_functions(row) == ["f"]
        row[FL_CHANGED_KEY] = "f"
        assert fl_changed_functions(row) == []


# ═══ 5. 统计与恒等式 ═══════════════════════════════════════════════════════════


class TestStats:
    def test_empty_rows_yield_zeros_not_missing_keys(self) -> None:
        out = detector_silence_stats([])
        assert out["n_rows"] == 0
        assert out["hack"]["n_evaluated"] == 0
        assert out["fl"]["hit_ratio"] is None and out["fl"]["n_not_evaluable"] == 0

    def test_hack_partition_identity_on_mixed_rows(self) -> None:
        rows = [
            _hack_row("a", status=HACK_STATUS_OK, suspected=True, signals=("assert_weakened",)),
            _hack_row("b", status=HACK_STATUS_EMPTY_PATCH),
            _hack_row("c", status=None),
            _hack_row("d", status=HACK_STATUS_DETECTOR_ERROR),
            _hack_row("e", include_verdict=False),
        ]
        hack = detector_silence_stats(rows)["hack"]
        assert hack["n_evaluated"] == 1 and hack["n_silent"] == 2
        assert hack["n_status_unrecorded"] == 1 and hack["n_not_recorded"] == 1
        # 四档求和 = 行数：恒等式在测试侧断言（函数内不设恒真标记，见 BV §6①）
        assert hack["n_evaluated"] + hack["n_silent"] + hack["n_status_unrecorded"] + hack["n_not_recorded"] == len(
            rows
        )

    def test_hack_suspected_counts_and_samples(self) -> None:
        rows = [_hack_row(f"t{i}", status=HACK_STATUS_OK, suspected=True) for i in range(25)]
        hack = detector_silence_stats(rows)["hack"]
        assert hack["n_suspected"] == 25
        assert len(hack["suspected_samples"]) == 20  # 封顶单点在返回处

    def test_suspected_without_evaluation_only_counts_recorded_contradictions(self) -> None:
        legacy = _hack_row("legacy", status=None, suspected=True)
        recorded = _hack_row("recorded", status=HACK_STATUS_EMPTY_PATCH, suspected=True)
        hack = detector_silence_stats([legacy, recorded])["hack"]
        assert hack["n_suspected_without_evaluation"] == 1  # 只有 recorded 那行

    def test_unknown_signal_names_are_listed(self) -> None:
        rows = [_hack_row("a", suspected=True, signals=("assert_weakened", "new_signal"))]
        hack = detector_silence_stats(rows)["hack"]
        assert hack["unknown_signals"] == ["new_signal"]
        assert hack["signals"] == {"assert_weakened": 1, "new_signal": 1}

    def test_fl_identity_holds_with_recorded_and_inferred(self) -> None:
        rows = [
            _fl_row("a", verdict="not_evaluable", reason=FL_REASON_NO_PATCH),
            _fl_row("b", verdict="not_evaluable"),
            _fl_row("c", verdict="hit", changed=("f",), hit_rank=1),
            {"task_id": "d"},
        ]
        fl = detector_silence_stats(rows)["fl"]
        assert fl["n_not_evaluable"] == 2
        assert sum(fl["reason_recorded"].values()) == 1
        assert sum(fl["reason_inferred"].values()) == 1
        assert fl["n_not_evaluable"] == sum(fl["reason_recorded"].values()) + sum(fl["reason_inferred"].values())
        assert fl["n_not_recorded"] == 1

    def test_hit_ratio_excludes_not_evaluable(self) -> None:
        rows = [
            _fl_row("a", verdict="hit", changed=("f",), hit_rank=1),
            _fl_row("b", verdict="hit", changed=("f",), hit_rank=2),
            _fl_row("c", verdict="miss", changed=("f",)),
            _fl_row("d", verdict="not_evaluable"),
        ]
        fl = detector_silence_stats(rows)["fl"]
        assert fl["n_evaluated"] == 3 and fl["n_not_evaluable"] == 1
        assert fl["hit_ratio"] == pytest.approx(2 / 3, abs=0.0)

    def test_changed_len_buckets(self) -> None:
        rows = [
            _fl_row("a", verdict="hit", changed=(), hit_rank=1),
            _fl_row("b", verdict="hit", changed=("f",), hit_rank=1),
            _fl_row("c", verdict="hit", changed=("f", "g"), hit_rank=1),
            _fl_row("d", verdict="hit", changed=("f", "g", "h"), hit_rank=1),
            _fl_row("e", verdict="not_evaluable"),
        ]
        fl = detector_silence_stats(rows)["fl"]
        assert fl["changed_len"] == {"1": 1, "2": 1, "3+": 1, "0": 2}
        assert fl["hit_rank"] == {"rank_1": 4}

    def test_reason_mismatch_is_counted(self) -> None:
        rows = [_fl_row("a", verdict="hit", reason=FL_REASON_NO_PATCH)]
        assert detector_silence_stats(rows)["fl"]["n_reason_mismatch"] == 1

    def test_out_of_vocabulary_verdicts_are_listed(self) -> None:
        rows = [_fl_row("a", verdict="maybe")]
        fl = detector_silence_stats(rows)["fl"]
        assert fl["other_values"] == ["other:maybe"]
        assert fl["n_verdict_recorded"] == 0

    def test_basis_counts_split_recorded_from_inferred(self) -> None:
        rows = [
            _fl_row("a", verdict="not_evaluable", reason=FL_REASON_NO_LOCALIZATION),
            _fl_row("b", verdict="not_evaluable"),
            _fl_row("c", verdict="hit", changed=("f",), hit_rank=1),
            {"task_id": "d"},
        ]
        basis = detector_silence_stats(rows)["fl"]["basis"]
        assert basis == {
            FL_BASIS_RECORDED: 1,
            FL_BASIS_INFERRED: 1,
            FL_BASIS_NOT_APPLICABLE: 1,
            FL_BASIS_UNRECORDED_VERDICT: 1,
        }

    def test_legacy_arm_reports_zero_evaluated_not_zero_suspected(self) -> None:
        """全 legacy 臂：`已求值` = 0、`状态未记录` = 行数——不得读作「都判干净」。"""
        rows = [_hack_row("a", status=None), _hack_row("b", status=None)]
        hack = detector_silence_stats(rows)["hack"]
        assert hack["n_evaluated"] == 0 and hack["n_status_unrecorded"] == 2
        assert hack["n_suspected"] == 0


# ═══ 6. 报告面 ═════════════════════════════════════════════════════════════════


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
        """四行同时携带两组键：已求值 / 记录成因的没看 / 状态未记录的 True / 键全缺。"""
        rows: list[dict] = []
        # t1：hack 已求值且干净；FL hit（rank 1、变更 1 个函数）
        rows.append(
            {
                **_hack_row("t1", status=HACK_STATUS_OK),
                **_fl_row("t1", verdict="hit", changed=("f",), hit_rank=1, reason=FL_REASON_OK),
            }
        )
        # t2：hack 没看（无补丁）；FL not_evaluable 且成因已记录（no_patch）
        rows.append(
            {
                **_hack_row("t2", status=HACK_STATUS_EMPTY_PATCH),
                **_fl_row("t2", verdict="not_evaluable", reason=FL_REASON_NO_PATCH, patch=None),
            }
        )
        # t3：hack 有判定但状态未记录、判 True；FL not_evaluable 无成因键（推断 = 变更集合为空）
        rows.append(
            {
                **_hack_row("t3", status=None, suspected=True, signals=("assert_weakened",)),
                **_fl_row("t3", verdict="not_evaluable"),
            }
        )
        rows.append({"task_id": "t4"})
        return rows

    def _md(self) -> str:
        return ar_mod.render_markdown(self._analysis(self._fixture_rows()), "demo.json")

    def test_build_analysis_exposes_the_new_key(self) -> None:
        per = self._analysis(self._fixture_rows())["per_baseline"]["aitester"]
        assert per["detector_silence"]["hack"]["n_suspected"] == 1
        assert per["detector_silence"]["fl"]["n_hit"] == 1

    def test_new_key_moves_no_existing_judgment_value(self) -> None:
        with_keys = self._analysis(self._fixture_rows())["per_baseline"]["aitester"]
        stripped = [
            {
                k: v
                for k, v in row.items()
                if k
                not in (
                    HACK_SUSPECTED_KEY,
                    HACK_SIGNALS_KEY,
                    HACK_STATUS_KEY,
                    FL_VERDICT_KEY,
                    FL_HIT_RANK_KEY,
                    FL_CHANGED_KEY,
                    FL_REASON_KEY,
                )
            }
            for row in self._fixture_rows()
        ]
        base = self._analysis(stripped)["per_baseline"]["aitester"]
        for key in ("total_functions", "passed_count", "success_rate", "avg_coverage"):
            assert with_keys[key] == base[key], key

    def test_hack_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 4 | 3 | 2 | 1 | 1 | 1 | 1 | 1 |" in md
        assert "| **合计** | 4 | 3 | 2 | 1 | 1 | 1 | 1 | 1 |" in md

    def test_fl_table_shows_all_cells(self) -> None:
        md = self._md()
        assert "| aitester | 3 | 1 | 0 | 2 | 1 | 100.0% | 1 | 1 | 0 | 2/1/0/0 |" in md
        assert "| **合计** | 3 | 1 | 0 | 2 | 1 | 100.0% | 1 | 1 | 0 | 2/1/0/0 |" in md

    def test_both_tables_have_consistent_cell_counts(self) -> None:
        md = self._md()
        lines = md.splitlines()
        heading = "## 批次 VIII/XIV 判定核的沉默分档（BV：`test_hacking_*` / `fl_constraint_*` 的读侧）"
        tables: list[list[str]] = [[]]
        for line in lines[lines.index(heading) + 1 :]:
            if line.startswith("## "):
                break  # 本节结束：后面章节的表格不属于本节
            if line.startswith("|"):
                tables[-1].append(line)
            elif tables[-1]:
                tables.append([])
        tables = [t for t in tables if t]
        assert [[len(ln.split("|")) - 2 for ln in t] for t in tables] == [[9, 9, 9, 9], [11, 11, 11, 11]], tables

    def test_suspected_note_names_the_rows(self) -> None:
        md = self._md()
        assert "**test-hacking 判定为 True 的行 = 1**" in md
        assert "t3" in md
        assert "不是「作弊已被确认」" in md

    def test_silent_note_appears_only_when_rows_were_not_evaluated(self) -> None:
        md = self._md()
        assert "**`没看` = 1 行**" in md
        clean = [_hack_row("t1", status=HACK_STATUS_OK), {"task_id": "t2"}]
        md2 = ar_mod.render_markdown(self._analysis(clean), "demo.json")
        assert "**`没看` = " not in md2

    def test_suspected_note_is_absent_when_nothing_fired(self) -> None:
        rows = [_hack_row("t1", status=HACK_STATUS_OK), {"task_id": "t2"}]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "**test-hacking 判定为 True 的行 = " not in md

    def test_silent_arm_note_names_arms_without_any_verdict(self) -> None:
        md = ar_mod.render_markdown(self._analysis([{"task_id": "t1"}, {"task_id": "t2"}]), "demo.json")
        assert "个臂的结果行没有 `test_hacking_*` 判定键" in md
        assert "`aitester`" in md
        assert "批次早于批次 VIII 观测层" in md

    def test_hit_ratio_note_says_the_registered_cause_does_not_explain_it(self) -> None:
        one_func = [_fl_row("a", verdict="hit", changed=("f",), hit_rank=1)]
        md = ar_mod.render_markdown(self._analysis(one_func), "demo.json")
        assert "**ADR-0028 登记的整文件重写成因不足以解释这个比值**" in md

    def test_hit_ratio_note_says_the_registered_cause_applies_when_3plus_dominates(self) -> None:
        rows = [_fl_row(f"t{i}", verdict="hit", changed=("a", "b", "c"), hit_rank=1) for i in range(4)]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "与 ADR-0028 登记的「整文件重写" in md
        assert "不足以解释这个比值" not in md

    def test_fl_reason_columns_are_not_symmetric(self) -> None:
        """记录成因与推断成因两列必须各取各的数（夹具里 1:1 会让列互换活下来）。"""
        rows = [
            _fl_row("a", verdict="not_evaluable", reason=FL_REASON_NO_PATCH, patch=None),
            _fl_row("b", verdict="not_evaluable", reason=FL_REASON_NO_LOCALIZATION, localization=False),
            _fl_row("c", verdict="not_evaluable"),
        ]
        md = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "| aitester | 3 | 0 | 0 | 3 | 0 | — | 2 | 1 | 0 | 3/0/0/0 |" in md

    def test_footnotes_keep_all_calibers(self) -> None:
        md = self._md()
        assert "`hack 有判定` = 行内有 `test_hacking_suspected` 键" in md
        assert "**不得读作 ok**" in md
        assert "`成因推断（下界）`" in md
        assert "**推断是下界，不等于全集**" in md
        assert "`not_evaluable` 不进分母" in md

    def test_mismatch_note_appears_only_when_it_exists(self) -> None:
        md = self._md()
        assert "成因键与判定值自相矛盾" not in md
        rows = [_fl_row("a", verdict="hit", reason=FL_REASON_NO_PATCH)]
        md2 = ar_mod.render_markdown(self._analysis(rows), "demo.json")
        assert "成因键与判定值自相矛盾 = 1 行" in md2

    def test_section_absent_when_no_rows(self) -> None:
        md = ar_mod.render_markdown(self._analysis([]), "demo.json")
        assert "## 批次 VIII/XIV 判定核的沉默分档" not in md


# ═══ 7. 批次摘要接线（run_main_batch） ═════════════════════════════════════════


class TestSummaryLine:
    @staticmethod
    def _write_batch(tmp_path: Path, rows: list[dict]) -> Path:
        payload = {
            "dataset": "demo",
            "results": {
                "aitester": {
                    "details": rows,
                    "success_rate": 100.0,
                    "effective_total": len(rows),
                    "harness_invalid_count": 0,
                }
            },
        }
        path = tmp_path / "benchmark_demo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_summary_prints_both_families(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import experiments.run_main_batch as main_mod

        rows = [
            {
                **_hack_row("t1", status=HACK_STATUS_OK),
                **_fl_row("t1", verdict="hit", changed=("f",), hit_rank=1, reason=FL_REASON_OK),
            },
            {
                **_hack_row("t2", status=HACK_STATUS_EMPTY_PATCH),
                **_fl_row("t2", verdict="not_evaluable", reason=FL_REASON_NO_PATCH, patch=None),
            },
        ]
        main_mod._print_r4_summary(self._write_batch(tmp_path, rows))
        out = capsys.readouterr().out
        assert "BV 判定核沉默: hack 已求值 1/2" in out
        assert "没看 1" in out and "判 True 0" in out
        assert "FL 已求值 1（hit 1/miss 0，hit 比 100.0%）" in out
        assert "not_evaluable 1（成因已记录 1）" in out

    def test_summary_does_not_render_a_clean_reading_for_legacy_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import experiments.run_main_batch as main_mod

        rows = [_hack_row("t1", status=None)]
        main_mod._print_r4_summary(self._write_batch(tmp_path, rows))
        out = capsys.readouterr().out
        assert "已求值 0/1" in out
        assert "状态未记录 1" in out


# ═══ 8. 具名冻结批次 ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel", sorted(PINNED_BATCHES))
def test_pinned_batch_reads_as_registered(rel: str) -> None:
    path = ROOT / rel
    assert path.exists(), rel
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        r
        for blk in (doc.get("results") or {}).values()
        for r in (blk or {}).get("details") or []
        if isinstance(r, dict)
    ]
    out = detector_silence_stats(rows)
    hack, fl = out["hack"], out["fl"]
    got = {
        "n_rows": out["n_rows"],
        "hack_verdict_recorded": hack["n_verdict_recorded"],
        "hack_status_unrecorded": hack["n_status_unrecorded"],
        "hack_evaluated": hack["n_evaluated"],
        "hack_suspected": hack["n_suspected"],
        "fl_hit": fl["n_hit"],
        "fl_miss": fl["n_miss"],
        "fl_not_evaluable": fl["n_not_evaluable"],
        "fl_reason_inferred": sum(fl["reason_inferred"].values()),
        "fl_changed_0": fl["changed_len"].get("0", 0),
    }
    assert got == PINNED_BATCHES[rel], rel
    assert fl["reason_inferred"] == PINNED_INFERRED[rel], rel
