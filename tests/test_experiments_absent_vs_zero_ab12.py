"""AB-12b 回归锁：站点 a 的三件登记机制——缺席不得降成空对象 / FAIL / 无痕摘除（2026-10-20）。

AB-9 普查登记、AB-11 计数纠偏后确认仍 0 件处置的三件（`experiments/analyze_t1_b2_main_batch.py`）：

① `arm_stats` / `per_task_detection` / 逐 seed 循环里的 `(x or {})` 链——把"results 键缺席 /
  值为 null / 类型不对 / 臂键缺席 / details 缺席或 null"全部塌成同一个空对象，报告只剩
  `rows: 0`（与"真的产出 0 行"同形）；而 `nb.get("results", {}).get(arm)` 在键存在但值为
  null 时直接 `AttributeError`（静默点与崩溃点分岔）。
② `GATES.json` 缺席/读不动/`all_pass` 键缺席/值非布尔，与"值确实是 false"共用一个 `False`，
  报告只会说 `FAIL`——缺席被渲染成未通过。
③ 原批次循环的宽 `except Exception: continue` 把一份坏文件（和一对种子）无痕摘掉。

处置口径（同 AB-9/AB-10/AB-11）：**披露键只在真的发生缺席时写入**——无缺席输入（含已归档
T1/B2 批）的载荷、README 生成段、BASELINE 片段逐字节不变，入库工件一份都不重写
（见 `TestRealPathInvariants`，其中包含"已归档目录确有 7 份未采用候选，但那是有记录的过滤、
不是缺席，故不写进载荷"这条边界锁）。

判据 = **删掉对应守卫必然转红**（变异验证逐处打印变红用例名，sha256 断言字节还原）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import experiments.analyze_t1_b2_main_batch as t1
from experiments.analyze_t1_b2_main_batch import (
    ARMS,
    SEEDS,
    _fingerprint_pinned,
    _missing_side_reason,
    _nested_absence,
    _value_or_absent,
    arm_absence_reason,
    build_report,
    read_gates_artifact,
    render_baseline_fragment,
    render_readme,
)
from tests._corpus_guard import require_history

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "experiments/results/t_round_b2_main_batch_20261018"
_ORIG = _ROOT / "experiments/results/main_batch"
_REPORT = _OUT / "ANALYSIS_REPORT.json"
_README = _OUT / "README.md"
_FRAGMENT = _OUT / "BASELINE_FRAGMENT.yaml"
_PRICE = {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "currency": "USD"}
_GATES_FAIL_ROW = "| §1.1 硬门槛（干净树/指纹/行数/exit） | `FAIL` |"
_GATES_PASS_ROW = "| §1.1 硬门槛（干净树/指纹/行数/exit） | `PASS` |"


def _require(path: Path) -> Path:
    """入库工件必须在场——缺席是环境事实，用 fail 说明"本锁未执行"，不用 skip 蒙数。"""
    if not path.exists():
        pytest.skip(
            f"入库工件缺失，本锁未执行：{path}（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前：语料前提缺失改具名 skip，重跑落盘后自动恢复判定）"
        )
    return path


@pytest.fixture
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """假输入用例不跑 `git show`：profile 预设漂移固定成"无法核验"（其自身另有 AB-11 锁）。"""

    def _fake(*a: Any, **k: Any) -> dict[str, Any]:
        return {"available": False, "reason": "测试内不跑 git"}

    monkeypatch.setattr(t1, "_profile_drift", _fake)


# ───────────────────────── ① 臂在场性的返回域 ─────────────────────────


def _row(task_id: str, detection: float | None) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "detection_rate": detection,
        "repair_rate": None,
        "false_fix_rate": None,
        "coverage": 0.5,
        "iterations": 1,
        "stop_reason": "done",
    }


def _arm_obj(*, rows: int = 2, with_details: bool = True) -> dict[str, Any]:
    arm: dict[str, Any] = {
        "token_metrics": {
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "total_tokens": 1500,
            "total_llm_calls": 3,
        }
    }
    if with_details:
        arm["details"] = [_row(f"t{i}", 1.0 if i % 2 == 0 else None) for i in range(rows)]
    return arm


def _batch_obj(seed: int, arms: Any, *, provenance: bool = True) -> dict[str, Any]:
    batch: dict[str, Any] = {"seed": seed, "total_tasks": 87, "results": arms}
    if provenance:
        batch["provenance"] = {
            "git_dirty": False,
            "git_sha": f"sha{seed}",
            "model_fingerprint": {"pinned": True},
            "profile": "logic",
            "env_snapshot": {"AITESTER_PROFILE": "logic"},
            "harness": {"version": "v1"},
        }
    return batch


def _full_arms() -> dict[str, Any]:
    return {arm: _arm_obj() for arm in ARMS}


ABSENCE_SHAPES: list[tuple[str, Any, str]] = [
    ("batch 非对象", [], "batch_not_object(list)"),
    ("results 键缺席", {}, "results_key_absent"),
    ("results 值为 null", {"results": None}, "results_value_null"),
    ("results 非对象", {"results": []}, "results_not_object(list)"),
    ("臂键缺席", {"results": {}}, "arm_key_absent"),
    ("臂值为 null", {"results": {"aitester": None}}, "arm_value_null"),
    ("臂非对象", {"results": {"aitester": []}}, "arm_not_object(list)"),
    ("details 键缺席", {"results": {"aitester": {}}}, "details_key_absent"),
    ("details 值为 null", {"results": {"aitester": {"details": None}}}, "details_value_null"),
    ("details 非列表", {"results": {"aitester": {"details": {}}}}, "details_not_object(dict)"),
]


@pytest.mark.unit
class TestArmPresenceReturnDomain:
    @pytest.mark.parametrize(("label", "batch", "expected"), ABSENCE_SHAPES, ids=[s[0] for s in ABSENCE_SHAPES])
    def test_each_absence_shape_keeps_its_own_mechanism(self, label: str, batch: Any, expected: str) -> None:
        assert arm_absence_reason(batch, "aitester") == expected, label

    def test_mechanisms_are_pairwise_distinct(self) -> None:
        """十种失败机制若塌成同一个名字，披露就只剩一种读数（AB-11 判据）。"""
        names = [expected for _, _, expected in ABSENCE_SHAPES]
        assert len(set(names)) == len(names)

    def test_readable_arm_is_none(self) -> None:
        assert arm_absence_reason(_batch_obj(42, _full_arms()), "aitester") is None

    def test_empty_details_is_a_real_reading_not_an_absence(self) -> None:
        """`details: []` 是"这批真的产出了 0 行"，不是缺席——不得混进披露桶。"""
        assert arm_absence_reason({"results": {"aitester": {"details": []}}}, "aitester") is None

    def test_per_task_detection_returns_empty_only_for_absent_arm(self) -> None:
        assert t1.per_task_detection({"results": None}, "aitester") == {}
        assert set(t1.per_task_detection(_batch_obj(42, _full_arms()), "aitester")) == {"t0", "t1"}


# ───────────────────────── ② GATES.json 的三态读数 ─────────────────────────

GATES_SHAPES: list[tuple[str, Any, str, str]] = [
    ("键缺席", {}, "UNVERIFIABLE", "GATES.json 无 all_pass 键（键缺席不等于未通过）"),
    ("值为 null", {"all_pass": None}, "UNVERIFIABLE", "GATES.json 的 all_pass 非布尔（NoneType）"),
    ("值为字符串", {"all_pass": "true"}, "UNVERIFIABLE", "GATES.json 的 all_pass 非布尔（str）"),
    ("顶层非对象", [], "UNVERIFIABLE", "GATES.json 顶层非对象（list）"),
]


@pytest.mark.unit
class TestGatesTriState:
    @pytest.mark.parametrize(("label", "payload", "state", "reason"), GATES_SHAPES, ids=[s[0] for s in GATES_SHAPES])
    def test_absence_shapes_are_unverifiable(
        self, tmp_path: Path, label: str, payload: Any, state: str, reason: str
    ) -> None:
        p = tmp_path / "GATES.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        obj, got_state, got_reason = read_gates_artifact(p)
        assert (obj is None, got_state, got_reason) == (True, state, reason), label

    def test_missing_file_is_unverifiable(self, tmp_path: Path) -> None:
        obj, state, reason = read_gates_artifact(tmp_path / "GATES.json")
        assert (obj, state, reason) == (None, "UNVERIFIABLE", "GATES.json 文件缺席")

    def test_unreadable_file_is_unverifiable_not_fail(self, tmp_path: Path) -> None:
        p = tmp_path / "GATES.json"
        p.write_text("{半写的 json", encoding="utf-8")
        obj, state, reason = read_gates_artifact(p)
        assert obj is None and state == "UNVERIFIABLE"
        assert reason.startswith("GATES.json 读不动（") and reason.endswith("）")

    def test_only_a_real_false_is_fail(self, tmp_path: Path) -> None:
        p = tmp_path / "GATES.json"
        p.write_text(json.dumps({"all_pass": False}), encoding="utf-8")
        obj, state, reason = read_gates_artifact(p)
        assert (obj, state, reason) == ({"all_pass": False}, "FAIL", "")

    def test_true_is_pass(self, tmp_path: Path) -> None:
        p = tmp_path / "GATES.json"
        p.write_text(json.dumps({"all_pass": True}), encoding="utf-8")
        assert read_gates_artifact(p)[1] == "PASS"

    def test_unverifiable_reasons_are_pairwise_distinct(self, tmp_path: Path) -> None:
        shapes: list[Any] = [None, "corrupt", [], {}, {"all_pass": None}, {"all_pass": "true"}]
        reasons: list[str] = []
        for i, payload in enumerate(shapes):
            p = tmp_path / f"g{i}_GATES.json"
            if payload is None:
                reasons.append(read_gates_artifact(p)[2])
                continue
            p.write_text("{坏 json" if payload == "corrupt" else json.dumps(payload), encoding="utf-8")
            reasons.append(read_gates_artifact(p)[2])
        assert len(set(reasons)) == len(reasons), reasons


# ───────────────────────── 假环境搭建 ─────────────────────────


def _dump(payload: Any) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)


def _env(tmp_path: Path, *, new: dict[int, Any], orig: dict[str, Any], gates: Any = "__omit__") -> tuple[Path, Path]:
    """造一个只含协议种子的假 out_dir / orig_dir（不碰任何入库工件）。"""
    out = tmp_path / "out"
    out.mkdir()
    for seed, payload in new.items():
        d = out / f"seed{seed}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"benchmark_{seed}.json").write_text(_dump(payload), encoding="utf-8")
    if gates != "__omit__":
        (out / "GATES.json").write_text(_dump(gates), encoding="utf-8")
    orig_dir = tmp_path / "orig"
    orig_dir.mkdir()
    for name, payload in orig.items():
        (orig_dir / name).write_text(_dump(payload), encoding="utf-8")
    return out, orig_dir


def _complete_new() -> dict[int, Any]:
    return {seed: _batch_obj(seed, _full_arms()) for seed in SEEDS}


def _complete_orig() -> dict[str, Any]:
    return {f"benchmark_synthetic_{seed}.json": _batch_obj(seed, _full_arms()) for seed in SEEDS}


@pytest.mark.unit
class TestBuildReportDisclosures:
    def test_no_absence_writes_no_disclosure_keys(self, tmp_path: Path, no_git: None) -> None:
        """无缺席 ⇒ 载荷不含任何披露键（入库工件逐字节不变的前提）。"""
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert "availability" not in report
        assert "gates_state" not in report["verdict"]
        assert "skipped_seeds" not in report["provenance_drift"]
        assert render_readme(report).count("缺席与无法核验披露") == 0
        assert _GATES_PASS_ROW in render_readme(report)

    def test_missing_gates_is_unverifiable_and_never_renders_fail(self, tmp_path: Path, no_git: None) -> None:
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=_complete_orig())
        report = build_report(out, orig_dir, _PRICE)
        v = report["verdict"]
        assert v["verdict"] == "gates_unverifiable_grade"
        assert v["gates_all_pass"] is False
        assert v["gates_state"] == "UNVERIFIABLE"
        assert v["gates_state_reason"] == "GATES.json 文件缺席"
        assert report["availability"]["gates"] == "GATES.json 文件缺席"
        readme = render_readme(report)
        assert _GATES_FAIL_ROW not in readme
        assert "**无法核验**：GATES.json 文件缺席" in readme
        assert "## 0.1 缺席与无法核验披露" in readme
        frag = render_baseline_fragment(report)
        assert 'gates_state: "UNVERIFIABLE: GATES.json 文件缺席"' in frag

    def test_all_pass_key_absent_reason_differs_from_real_false(self, tmp_path: Path, no_git: None) -> None:
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=_complete_orig(), gates="{}")
        report = build_report(out, orig_dir, _PRICE)
        assert "无 all_pass 键" in report["verdict"]["gates_state_reason"]
        assert report["verdict"]["verdict"] == "gates_unverifiable_grade"

    def test_real_false_still_fails_without_unverifiable_keys(self, tmp_path: Path, no_git: None) -> None:
        """`all_pass=false` 是真实读数：走原 FAIL 口径，不得借用无法核验的三态壳。"""
        out, orig_dir = _env(
            tmp_path, new=_complete_new(), orig=_complete_orig(), gates=json.dumps({"all_pass": False})
        )
        report = build_report(out, orig_dir, _PRICE)
        assert report["verdict"]["verdict"] == "not_reproducible_grade"
        assert "gates_state" not in report["verdict"]
        assert "availability" not in report
        assert _GATES_FAIL_ROW in render_readme(report)

    def test_null_results_does_not_crash_but_names_mechanism(self, tmp_path: Path, no_git: None) -> None:
        """历史形态 `nb.get("results", {}).get(arm)` 在此处抛 AttributeError（键缺席才走默认值）。"""
        new = _complete_new()
        new[43] = _batch_obj(43, None)
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        arms = report["availability"]["arms"]
        assert arms["new.seed43.aitester"] == "results_value_null"
        assert "original.seed42.aitester" not in arms, "可读的臂不得被记成缺席"
        assert report["per_seed"]["43"]["new"] == {}

    def test_missing_seed_batch_is_named_and_downgrades_verdict(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        del new[44]
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        missing = report["availability"]["new_batches"]
        assert [m["seed"] for m in missing] == [44]
        assert missing[0]["mechanism"] == "seed44/ 下无 benchmark_*.json"
        assert report["verdict"]["verdict"] == "batch_absent_grade"
        assert "seed44" in report["verdict"]["rationale"]
        assert "- 协议批次缺席：seed44 — seed44/ 下无 benchmark_*.json" in render_readme(report)
        skipped = report["provenance_drift"]["skipped_seeds"]
        assert [s["seed"] for s in skipped] == [44]
        assert "批次本身缺席" in skipped[0]["mechanism"]

    def test_corrupt_new_batch_names_file_and_exception(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        new[42] = "{半写"
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        mechanism = report["availability"]["new_batches"][0]["mechanism"]
        assert mechanism.startswith("benchmark_42.json 读不动（")
        assert "JSONDecodeError" in mechanism

    def test_non_object_new_batch_names_its_type(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        new[42] = []
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert report["availability"]["new_batches"][0]["mechanism"] == "benchmark_42.json 顶层非对象（list）"
        assert report["availability"]["arms"]["new.seed42.aitester"] == "results_key_absent"

    def test_corrupt_original_file_is_named_not_silently_dropped(self, tmp_path: Path, no_git: None) -> None:
        """站点 a ③：宽 `except Exception: continue` 的历史形态——坏文件无痕摘掉。"""
        orig = _complete_orig()
        orig["benchmark_synthetic_broken.json"] = "{坏"
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=orig, gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        ob = report["availability"]["original_batches"]
        assert ob["scanned_files"] == 4
        assert ob["unreadable"] == [
            {"file": "benchmark_synthetic_broken.json", "mechanism": "读不动（JSONDecodeError）"}
        ]
        assert ob["missing_seeds"] == []
        readme = render_readme(report)
        assert "  - `benchmark_synthetic_broken.json`：读不动（JSONDecodeError）" in readme

    def test_missing_original_pair_is_disclosed(self, tmp_path: Path, no_git: None) -> None:
        orig = _complete_orig()
        del orig["benchmark_synthetic_43.json"]
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=orig, gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert report["availability"]["original_batches"]["missing_seeds"] == [43]

    def test_excluded_only_candidates_do_not_touch_payload(self, tmp_path: Path, no_git: None) -> None:
        """边界锁：`total_tasks≠87`/同 seed 第二份候选是**有记录的过滤**，不是缺席——
        写进载荷会让重算结果与受 SHA256SUMS 保护的入库工件不再逐字节相同。"""
        orig = _complete_orig()
        orig["benchmark_synthetic_partial.json"] = {"seed": 42, "total_tasks": 5, "results": {}}
        orig["benchmark_synthetic_second.json"] = _batch_obj(42, _full_arms())
        out, orig_dir = _env(tmp_path, new=_complete_new(), orig=orig, gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert "availability" not in report, "未采用候选不得写进载荷（已归档目录里就有 7 份）"
        assert "original_batches" not in (report.get("availability") or {})

    def test_arm_absence_shrinks_the_denominator_only_after_saying_so(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        arm = new[43]["results"]["plain_llm_df"]
        del arm["details"]
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        entry = report["per_seed"]["43"]
        assert set(entry["new"]) == {"aitester", "plain_llm"}
        assert entry["same_seed_ordering_ok"] is None
        assert report["availability"]["arms"]["new.seed43.plain_llm_df"] == "details_key_absent"
        assert "- 臂缺席 `new.seed43.plain_llm_df`：details_key_absent" in render_readme(report)

    def test_pooled_denominator_reports_which_seeds_were_counted(self, tmp_path: Path, no_git: None) -> None:
        """缺席臂的 seed 不进池化分母——但这条只能靠披露成立，否则读作"零命中"。"""
        new = _complete_new()
        new[44]["results"]["plain_llm"] = None
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert report["pooled"]["plain_llm"]["measurable"] == 2, "缺席 seed 不得进分母（每 seed 1 行可测）"
        assert report["availability"]["arms"]["new.seed44.plain_llm"] == "arm_value_null"


# ───────────────────────── provenance 侧的缺席读数 ─────────────────────────


@pytest.mark.unit
class TestProvenanceAbsence:
    def test_env_snapshot_key_absent_is_not_read_as_no_drift(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        del new[42]["provenance"]["env_snapshot"]
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        entry = report["provenance_drift"]["env_snapshot_diff"]["42"]
        assert entry == {"unverifiable": "新侧 env_snapshot_key_absent"}, "读不到不得落 `{}`（=无漂移）"

    def test_harness_value_null_names_its_own_mechanism(self, tmp_path: Path, no_git: None) -> None:
        new = _complete_new()
        new[42]["provenance"]["harness"] = None
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        assert report["provenance_drift"]["harness_diff"]["42"] == {"unverifiable": "新侧 harness_value_null"}

    def test_both_sides_absent_marks_flags_unverifiable(self, tmp_path: Path, no_git: None) -> None:
        new = {seed: _batch_obj(seed, _full_arms(), provenance=False) for seed in SEEDS}
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        drift = report["provenance_drift"]
        assert [s["seed"] for s in drift["skipped_seeds"]] == list(SEEDS)
        assert "provenance_key_absent" in drift["skipped_seeds"][0]["mechanism"]
        assert "unverifiable" in drift["provenance_flags"]
        readme = render_readme(report)
        assert "新批 git_dirty=None" not in readme
        assert "provenance flags：**无法核验**" in readme
        assert "- provenance 漂移缺席 seed42：" in readme

    def test_flags_seed_is_named_only_when_a_seed_was_skipped(self, tmp_path: Path, no_git: None) -> None:
        """`provenance_flags` 取最后一个未跳过 seed（不是三 seed 汇总）——只在有跳过时披露。"""
        new = _complete_new()
        del new[43]["provenance"]
        out, orig_dir = _env(tmp_path, new=new, orig=_complete_orig(), gates=json.dumps({"all_pass": True}))
        report = build_report(out, orig_dir, _PRICE)
        drift = report["provenance_drift"]
        assert drift["provenance_flags_seed"] == 44
        assert [s["seed"] for s in drift["skipped_seeds"]] == [43]
        assert drift["provenance_flags"]["new_git_sha"] == "sha44"
        assert "上行 flags 取的是**最后一个未跳过 seed（44）**" in render_readme(report)

    @pytest.mark.parametrize(
        ("provenance", "expected"),
        [
            ({}, "model_fingerprint_key_absent"),
            ({"model_fingerprint": None}, "model_fingerprint_value_null"),
            ({"model_fingerprint": []}, "model_fingerprint_not_object(list)"),
            ({"model_fingerprint": {}}, "pinned_key_absent"),
            ({"model_fingerprint": {"pinned": None}}, None),
            ({"model_fingerprint": {"pinned": False}}, False),
        ],
    )
    def test_fingerprint_pinned_keeps_its_own_reading(self, provenance: dict[str, Any], expected: Any) -> None:
        """四种"读不到"与两种真实读数不得共用一个假值。"""
        got = _fingerprint_pinned(provenance)
        assert got == expected and type(got) is type(expected)

    def test_value_or_absent_distinguishes_absent_from_null(self) -> None:
        assert _value_or_absent({"git_dirty": None}, "git_dirty") is None
        assert _value_or_absent({}, "git_dirty") == "git_dirty_key_absent"
        assert _value_or_absent({"git_dirty": False}, "git_dirty") is False

    def test_nested_absence_empty_object_is_readable(self) -> None:
        assert _nested_absence({"env_snapshot": {}}, "env_snapshot") is None
        assert _nested_absence({"env_snapshot": []}, "env_snapshot") == "env_snapshot_not_object(list)"
        assert _missing_side_reason({}, "provenance") == "批次本身缺席"
        assert _missing_side_reason({"provenance": {}}, "provenance") == "provenance_empty_object"


# ───────────────────────── 真路径不变性（入库工件绝不重写） ─────────────────────────


def _real_price() -> dict[str, Any]:
    table = json.loads(_require(_ROOT / "experiments/price_table.json").read_text(encoding="utf-8"))
    return table.get("models", {}).get("deepseek-flash", {})


@pytest.fixture
def repo_cwd(monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """真路径复算必须在仓库根用**相对路径**跑：`out_dir`/`orig_dir` 会原样写进载荷，
    入库工件记的是相对路径，绝对路径会让逐字节比较虚假转红（也保证 `git show` 命中仓库）。"""
    monkeypatch.chdir(_ROOT)
    return _OUT.relative_to(_ROOT), _ORIG.relative_to(_ROOT)


@pytest.mark.unit
class TestRealPathInvariants:
    def test_committed_analysis_report_reproduces_byte_identically(self, repo_cwd: tuple[Path, Path]) -> None:
        """改动后重算 ⇒ 与入库 ANALYSIS_REPORT.json 逐字节相同（披露键在真输入上全部不写）。"""
        # BZ 轮：报告内嵌 profile 预设漂移，对账输入是两个历史切点 rev 的
        # `git show <rev>:config.py`——shallow clone（fetch-depth=1）里必败，
        # 重算结果与入库快照的差异是环境事实而不是被测行为 ⇒ require_history
        # 显式 skip 并点名缺哪个 rev（tests/_corpus_guard.py）。
        require_history(t1.PROFILE_DRIFT_OLD_REV, t1.PROFILE_DRIFT_NEW_REV)
        out, orig_dir = repo_cwd
        report = build_report(_require(out), _require(orig_dir), _real_price())
        fresh = json.dumps(report, ensure_ascii=False, indent=2)
        assert fresh == _require(_REPORT).read_text(encoding="utf-8")

    def test_generated_readme_is_exact_prefix_of_archived(self, repo_cwd: tuple[Path, Path]) -> None:
        """生成段逐字节相同；入库 README 尾部的手工块由 X 轮保留机制原样带出（其头部差异登记在
        评审文档，非本轮改动引入）。"""
        # BZ 轮：同 test_committed_analysis_report_reproduces_byte_identically——
        # README 生成段同样内嵌历史切点对账，shallow clone 下显式 skip。
        require_history(t1.PROFILE_DRIFT_OLD_REV, t1.PROFILE_DRIFT_NEW_REV)
        out, orig_dir = repo_cwd
        report = build_report(_require(out), _require(orig_dir), _real_price())
        assert _require(_README).read_text(encoding="utf-8").startswith(render_readme(report))

    def test_committed_baseline_fragment_reproduces_byte_identically(self, repo_cwd: tuple[Path, Path]) -> None:
        out, orig_dir = repo_cwd
        report = build_report(_require(out), _require(orig_dir), _real_price())
        assert render_baseline_fragment(report) == _require(_FRAGMENT).read_text(encoding="utf-8")

    def test_committed_payload_carries_no_disclosure_keys(self) -> None:
        committed = json.loads(_require(_REPORT).read_text(encoding="utf-8"))
        assert "availability" not in committed
        assert "gates_state" not in committed["verdict"]
        assert "skipped_seeds" not in committed["provenance_drift"]

    def test_archived_orig_dir_multiple_candidates_is_registered_not_disclosed(
        self, repo_cwd: tuple[Path, Path]
    ) -> None:
        """实测登记（2026-10-23 provider 清理后重算）：原批目录 glob 命中 7 份，其中 4 份未被采用
        （4 份同 seed 的第二/第三份候选；3 份 total_tasks≠87 的部分批已随清理删除），
        0 份读不动、0 个配对缺席——所以载荷里没有 availability。
        "同 seed 多份候选首份胜出且未记录文件名"是**站点 a ④ 本轮新登记、仍未处置**的一件。"""
        out, orig_dir = repo_cwd
        report = build_report(_require(out), _require(orig_dir), _real_price())
        files = sorted(_require(orig_dir).glob("benchmark_synthetic_*.json"))
        assert len(files) == 7
        assert "availability" not in report
        adopted: set[int] = set()
        wrong_size = duplicates = unreadable = 0
        for p in files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # 分类计数器本身要能跑完：坏文件计数即可
                unreadable += 1
                continue
            if not isinstance(d, dict) or d.get("seed") not in SEEDS:
                continue
            if d.get("total_tasks") != 87:
                wrong_size += 1
            elif d["seed"] in adopted:
                duplicates += 1
            else:
                adopted.add(d["seed"])
        assert unreadable == 0 and sorted(adopted) == list(SEEDS)
        assert wrong_size == 0 and duplicates == 4, (wrong_size, duplicates)
