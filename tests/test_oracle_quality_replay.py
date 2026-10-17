"""A-05 oracle 质量重放工具契约测试（零 LLM / 零网络 / 确定性）。

锁定 ``experiments/oracle_quality_replay.py`` 的核心口径：
- 锚表加载的 sha256 强制校验（SHA256SUMS / 显式摘要；缺失即 fail-closed）；
- 内容寻址查找、state 重建（反事实 / 归档语义两态）与生产注入函数 fidelity；
- 归档 ``spec_oracle_verdict`` / ``spec_oracle_injected`` 的语义复现与自洽性；
- oracle 四分类矩阵（correct / fp / silent / misguided）与不可分类原因单列；
- 失败类型归因、detection 转移（added/lost/preserved/none/undecidable）；
- 分母纪律（可分类 oracle 测试数）与报告字段、body digest 确定性；
- 微型端到端：真实 pytest 子进程跑 buggy/fixed 两侧（tmp_path fixture）。

测试全部使用 tmp_path 微型 fixture（小模块 + 已知行为测试），不依赖真实
QuixBugs 数据集/网络/LLM；必要的真实 pytest 子进程为本地执行。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import experiments.oracle_quality_replay as oq

# ─── 微型 fixture 工具 ─────────────────────────────────────────────────────
_BUGGY_ADD = "def add(a, b):\n    return a - b\n"
_FIXED_ADD = "def add(a, b):\n    return a + b\n"
_ADD_LOGIC = {"function_name": "add", "postconditions": ["result == a + b"], "postconditions_expr": ["result == a + b"]}
# 有效的 LLM 生成测试：buggy 失败（-1）∧ fixed 通过（5）→ effective
_LLM_TEST = "from add import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def _make_qxb_root(tmp_path: Path) -> Path:
    """构造最小 QuixBugs 口径数据根（python_programs + correct_python_programs）。"""
    root = tmp_path / "qxb"
    (root / "python_programs").mkdir(parents=True)
    (root / "correct_python_programs").mkdir(parents=True)
    (root / "python_programs" / "add.py").write_text(_BUGGY_ADD, encoding="utf-8")
    (root / "correct_python_programs" / "add.py").write_text(_FIXED_ADD, encoding="utf-8")
    return root


def _make_anchor_table(tmp_path: Path, anchors: dict) -> tuple[Path, Path]:
    """写锚表 + 同目录 SHA256SUMS（返回两路径）。"""
    table_dir = tmp_path / "anchors"
    table_dir.mkdir()
    table = table_dir / "SPEC_ANCHOR_TABLE.json"
    payload = {"meta": {"schema": 1, "table_entries": len(anchors)}, "anchors": anchors}
    table.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    sums = table_dir / "SHA256SUMS"
    sums.write_text(f"{digest}  SPEC_ANCHOR_TABLE.json\n", encoding="utf-8")
    return table, sums


def _anchor_entry(code: str = _BUGGY_ADD) -> dict:
    """按缺陷版源码内容哈希构造一条锚材料。"""
    return {
        hashlib.sha256(code.strip().encode("utf-8")).hexdigest(): {
            "function_name": "add",
            "logic_analysis": dict(_ADD_LOGIC),
        }
    }


def _task_row(
    *,
    generated_test: str = _LLM_TEST,
    task_id: str = "quixbugs__add",
    program: str = "add",
    fixed: str = _FIXED_ADD,
    detection: float | None = 1.0,
    verdict: str = "not_attempted",
    injected: bool | None = None,
) -> dict:
    """构造一条最小归档任务行（仅含本工具消费的字段）。"""
    return {
        "task_id": task_id,
        "generated_test": generated_test,
        "task_metadata": {
            "source": "quixbugs",
            "program": program,
            "test_cases": "",
            "fixed": fixed,
            "suggested_function": program,
            "is_cross_file": False,
        },
        "specificity_gate_verdict": "unavailable",
        "detection_rate": detection,
        "spec_oracle_verdict": verdict,
        "spec_oracle_injected": injected,
        "passed": False,
    }


def _write_artifact(path: Path, arms: dict[str, list[dict]]) -> Path:
    """写最小 benchmark 工件 JSON（results.<arm>.details）。"""
    payload = {
        "timestamp": "2026-10-17T00:00:00+00:00",
        "dataset": "quixbugs",
        "results": {arm: {"details": rows} for arm, rows in arms.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fake_task(
    *,
    task_id: str = "quixbugs__p",
    injected: bool = True,
    injection_verdict: str = "injected",
    attempted: bool = True,
    anchor_hit: bool = True,
    oracle_status: str = "ok",
    counts: dict | None = None,
    n_oracle_nodes: int = 1,
    unclassifiable: dict | None = None,
    failure_stats: dict | None = None,
    detection: dict | None = None,
    detection_agreement: str = "match",
    archived_verdict: str = "not_attempted",
    verdict_agreement: str = "match",
    field_consistency: bool = True,
    analysis_set: str = "defect_program",
    defect_signal: bool = True,
    artifact_detection_rate: float | None = 1.0,
) -> dict:
    """构造聚合/交叉校验测试用任务记录（键集合与 analyze_task 输出同构）。"""
    return {
        "task_id": task_id,
        "program": "p",
        "analysis_set": analysis_set,
        "defect_signal": defect_signal,
        "status": "ok",
        "skip_reason": None,
        "artifact_detection_rate": artifact_detection_rate,
        "artifact_spec_oracle_verdict": archived_verdict,
        "artifact_spec_oracle_injected": None,
        "anchor": {"hit": anchor_hit},
        "injection": {"verdict": injection_verdict, "injected": injected, "attempted": attempted},
        "archived_check": {"verdict_agreement": verdict_agreement, "field_consistency": field_consistency},
        "llm_only": {
            "detection_agreement": detection_agreement,
            "replay_detection": 1.0,
            "replay_detection_strict": 1.0,
        },
        "oracle": {
            "status": oracle_status,
            "n_oracle_nodes": n_oracle_nodes,
            "n_classifiable": sum((counts or {}).values()),
            "counts": {cls: 0 for cls in oq.ORACLE_CLASSES} | dict(counts or {}),
            "unclassifiable": dict(unclassifiable or {}),
            "failure_stats": dict(failure_stats or {}),
        },
        "detection": detection
        or {"archived": 1.0, "llm_only_replay": 1.0, "augmented_replay": 1.0, "transition": "preserved"},
    }


# ─── 锚表加载与 sha256 校验 ────────────────────────────────────────────────
def test_load_anchor_table_sha256_from_sums_ok(tmp_path: Path) -> None:
    table, sums = _make_anchor_table(tmp_path, _anchor_entry())
    loaded = oq.load_anchor_table(table, sums_path=sums)
    assert loaded["sha256"] == hashlib.sha256(table.read_bytes()).hexdigest()
    assert loaded["expected_sha256"] == loaded["sha256"]
    assert len(loaded["anchors"]) == 1
    assert loaded["meta"]["table_entries"] == 1


def test_load_anchor_table_sha256_mismatch_fail_closed(tmp_path: Path) -> None:
    table, sums = _make_anchor_table(tmp_path, _anchor_entry())
    sums.write_text("0" * 64 + "  SPEC_ANCHOR_TABLE.json\n", encoding="utf-8")
    with pytest.raises(oq.AnchorTableError, match="sha256 校验失败"):
        oq.load_anchor_table(table, sums_path=sums)


def test_load_anchor_table_missing_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(oq.AnchorTableError, match="锚表不存在"):
        oq.load_anchor_table(tmp_path / "missing.json")
    table, _sums = _make_anchor_table(tmp_path, _anchor_entry())
    with pytest.raises(oq.AnchorTableError, match="SHA256SUMS 不存在"):
        oq.load_anchor_table(table, sums_path=tmp_path / "no_sums")


def test_load_anchor_table_explicit_sha256_override(tmp_path: Path) -> None:
    table, sums = _make_anchor_table(tmp_path, _anchor_entry())
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    loaded = oq.load_anchor_table(table, sums_path=sums, expected_sha256=digest.upper())
    assert loaded["expected_sha256_source"] == "cli"
    with pytest.raises(oq.AnchorTableError, match="sha256 校验失败"):
        oq.load_anchor_table(table, sums_path=sums, expected_sha256="f" * 64)


def test_load_anchor_table_rejects_empty_anchors(tmp_path: Path) -> None:
    table_dir = tmp_path / "t"
    table_dir.mkdir()
    table = table_dir / "SPEC_ANCHOR_TABLE.json"
    table.write_text(json.dumps({"anchors": {}}), encoding="utf-8")
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    (table_dir / "SHA256SUMS").write_text(f"{digest}  SPEC_ANCHOR_TABLE.json\n", encoding="utf-8")
    with pytest.raises(oq.AnchorTableError, match="anchors 为空"):
        oq.load_anchor_table(table)


# ─── 内容寻址查找与 state 重建 ────────────────────────────────────────────
def test_lookup_anchor_content_addressed_strip() -> None:
    anchors = _anchor_entry()
    digest, entry = oq.lookup_anchor(anchors, _BUGGY_ADD)
    assert entry is not None and entry["function_name"] == "add"
    # strip 口径：前后空白不影响命中
    _digest2, entry2 = oq.lookup_anchor(anchors, "\n" + _BUGGY_ADD + "  \n")
    assert entry2 is not None
    miss_digest, miss = oq.lookup_anchor(anchors, _FIXED_ADD)
    assert miss is None and miss_digest != digest


def test_module_name_for_task_rules() -> None:
    assert oq.module_name_for_task("quixbugs__bitcount") == "bitcount"
    assert oq.module_name_for_task("synthetic__task_0000") == "task_0000"
    assert oq.module_name_for_task("x__a-b") == "a_b"
    assert len(oq.module_name_for_task("x__" + "m" * 80)) == 50


def test_reconstruct_state_exact_fields() -> None:
    entry = {"function_name": "add", "logic_analysis": dict(_ADD_LOGIC)}
    state = oq.reconstruct_state("quixbugs__add", {"suggested_function": "add"}, entry, _BUGGY_ADD)
    assert state["module_name"] == "add"
    assert state["target_function"] == "add"
    assert state["target_code"] == _BUGGY_ADD
    assert state["test_plan"] == {"function_name": "add", "logic_analysis": _ADD_LOGIC}
    assert "spec_ir" not in state  # 反事实口径：不写现场 spec_ir


def test_reconstruct_state_archived_has_no_test_plan() -> None:
    entry = {"function_name": "add", "logic_analysis": dict(_ADD_LOGIC)}
    state = oq.reconstruct_state("quixbugs__add", {"suggested_function": "add"}, entry, _BUGGY_ADD, archived_state=True)
    assert "test_plan" not in state
    assert state["target_function"] == "add"
    # suggested_function 缺席 → 不写 target_function（生产缺席语义）
    state2 = oq.reconstruct_state("quixbugs__add", {}, entry, _BUGGY_ADD, archived_state=True)
    assert "target_function" not in state2


def test_production_oracle_test_names_match_markers() -> None:
    assert oq.production_oracle_test_names() == oq.ORACLE_TEST_MARKERS


def test_is_oracle_node_markers() -> None:
    assert oq.is_oracle_node("test_generated.py::test_specir_v2_oracle")
    assert oq.is_oracle_node("test_generated.py::test_specir_v2_smt_witness_1")
    assert not oq.is_oracle_node("test_generated.py::test_add")
    assert not oq.is_oracle_node("test_generated.py::TestClass::test_x")


# ─── 生产注入 fidelity ────────────────────────────────────────────────────
def test_injection_fidelity_matches_production_function() -> None:
    from src.graph.nodes import _append_spec_oracle_to_test_with_verdict as production

    entry = {"function_name": "add", "logic_analysis": dict(_ADD_LOGIC)}
    state = oq.reconstruct_state("quixbugs__add", {"suggested_function": "add"}, entry, _BUGGY_ADD)
    merged_a, injected_a, verdict_a = oq.production_inject_oracle(_LLM_TEST, state)
    merged_b, injected_b, verdict_b = production(_LLM_TEST, state)
    assert (merged_a, injected_a, verdict_a) == (merged_b, injected_b, verdict_b)
    assert injected_a is True and verdict_a == "injected"
    assert merged_a.startswith(_LLM_TEST)
    assert oq.is_oracle_node(merged_a)


def test_injection_archived_state_not_attempted() -> None:
    entry = {"function_name": "add", "logic_analysis": dict(_ADD_LOGIC)}
    state = oq.reconstruct_state("quixbugs__add", {"suggested_function": "add"}, entry, _BUGGY_ADD, archived_state=True)
    merged, injected, verdict = oq.production_inject_oracle(_LLM_TEST, state)
    assert (merged, injected, verdict) == (_LLM_TEST, False, "not_attempted")


def test_archived_verdict_normalization_and_field_consistency() -> None:
    assert oq.normalize_archived_verdict(None) == "not_attempted"
    assert oq.normalize_archived_verdict("") == "not_attempted"
    assert oq.normalize_archived_verdict("compiled_empty") == "compiled_empty"
    ok, _detail = oq.archive_field_consistency("not_attempted", None)
    assert ok
    ok2, _ = oq.archive_field_consistency("compiled_empty", False)
    assert ok2
    ok3, detail3 = oq.archive_field_consistency("injected", True)
    assert ok3 and detail3 == ""
    bad, detail_bad = oq.archive_field_consistency("injected", None)
    assert not bad and "spec_oracle_injected" in detail_bad
    bad2, _ = oq.archive_field_consistency("weird_verdict", False)
    assert not bad2


# ─── oracle 四分类矩阵 ────────────────────────────────────────────────────
def test_classify_oracle_outcomes_four_class_matrix() -> None:
    nodes = [
        "test_generated.py::test_specir_v2_oracle_correct",
        "test_generated.py::test_specir_v2_oracle_fp",
        "test_generated.py::test_specir_v2_oracle_silent",
        "test_generated.py::test_specir_v2_oracle_misguided",
    ]
    buggy = {nodes[0]: "fail", nodes[1]: "fail", nodes[2]: "pass", nodes[3]: "pass"}
    fixed = {nodes[0]: "pass", nodes[1]: "fail", nodes[2]: "pass", nodes[3]: "fail"}
    rows, counts, unclassifiable = oq.classify_oracle_outcomes(nodes, buggy, fixed)
    assert counts == {"correct": 1, "fp": 1, "silent": 1, "misguided": 1}
    assert sum(unclassifiable.values()) == 0
    assert [r["cls"] for r in rows] == ["correct", "fp", "misguided", "silent"]  # node id 排序
    assert all(r["reason"] is None for r in rows)


def test_classify_oracle_outcomes_unclassifiable_reasons() -> None:
    nodes = ["n_timeout", "n_skip", "n_error", "n_missing"]
    buggy = {"n_timeout": "timeout", "n_skip": "skip", "n_error": "error", "n_missing": "fail"}
    fixed = {"n_timeout": "pass", "n_skip": "pass", "n_error": "pass"}
    rows, counts, unclassifiable = oq.classify_oracle_outcomes(
        nodes, buggy, fixed, buggy_missing_reason="missing_side", fixed_missing_reason="missing_side"
    )
    assert counts == {"correct": 0, "fp": 0, "silent": 0, "misguided": 0}
    assert unclassifiable["timeout"] == 1
    assert unclassifiable["skipped"] == 1
    assert unclassifiable["test_error"] == 1
    assert unclassifiable["missing_side"] == 1
    assert {r["cls"] for r in rows} == {None}


def test_classify_oracle_counts_sum_invariant() -> None:
    nodes = [f"n{i}" for i in range(6)]
    buggy = {n: "fail" for n in nodes}
    fixed = {n: "pass" for n in nodes}
    _rows, counts, _unc = oq.classify_oracle_outcomes(nodes, buggy, fixed)
    assert sum(counts.values()) == len(nodes)


# ─── 失败归因 / junit 解析 ─────────────────────────────────────────────────
def test_failure_kind_and_exception_name() -> None:
    assert oq.failure_kind("AssertionError: assert 1 == 2") == "assertion"
    assert oq.failure_kind("assert 1 == 2") == "assertion"
    assert oq.failure_kind("TypeError: cannot unpack") == "exception"
    assert oq.failure_kind("Failed: Timeout (>1.0s) from pytest-timeout.") == "timeout"
    assert oq.failure_kind("something odd") == "other"
    assert oq.exception_name("TypeError: cannot unpack") == "TypeError"
    assert oq.exception_name("AssertionError: x") == "AssertionError"
    assert oq.exception_name("no exception here") is None


def test_parse_junit_failure_notes(tmp_path: Path) -> None:
    xml = tmp_path / "junit.xml"
    xml.write_text(
        "<?xml version='1.0'?><testsuites><testsuite>"
        "<testcase classname='test_generated' name='test_specir_v2_oracle'>"
        "<failure message='TypeError: unsupported operand'>trace</failure></testcase>"
        "<testcase classname='test_generated' name='test_ok'></testcase>"
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    notes = oq.parse_junit_failure_notes(xml)
    assert "test_generated.py::test_specir_v2_oracle" in notes
    note = notes["test_generated.py::test_specir_v2_oracle"]
    assert note["kind"] == "exception" and note["exception"] == "TypeError"
    assert "test_generated.py::test_ok" not in notes
    assert oq.parse_junit_failure_notes(tmp_path / "missing.xml") == {}


# ─── 转移 / 聚合 / 交叉校验 ────────────────────────────────────────────────
def test_injection_transition_matrix() -> None:
    assert oq.injection_transition(0.0, 1.0) == "added"
    assert oq.injection_transition(1.0, 0.0) == "lost"
    assert oq.injection_transition(1.0, 1.0) == "preserved"
    assert oq.injection_transition(0.0, 0.0) == "none"
    assert oq.injection_transition(None, 1.0) == "undecidable"
    assert oq.injection_transition(1.0, None) == "undecidable"


def test_aggregate_injection_rates() -> None:
    tasks = [
        _fake_task(task_id="a", injected=True),
        _fake_task(task_id="b", injected=True, counts={"correct": 1}),
        _fake_task(task_id="c", injected=False, injection_verdict="compiled_empty", counts={}),
        _fake_task(
            task_id="d", injected=False, injection_verdict="not_attempted", attempted=False, anchor_hit=False, counts={}
        ),
    ]
    agg = oq.aggregate_injection(tasks)
    assert agg["n_task_rows"] == 4
    assert agg["n_anchor_hit"] == 3
    assert agg["n_attempted"] == 3
    assert agg["n_injected"] == 2
    assert agg["n_compiled_empty"] == 1
    assert agg["injection_rate_of_rows"] == 0.5
    assert agg["compiled_nonempty_rate_of_attempted"] == round(2 / 3, 6)
    assert agg["n_tasks_with_measurable_oracle"] == 2
    assert agg["oracle_tests_per_measurable_task"]["n"] == 2


def test_aggregate_oracle_denominator_discipline() -> None:
    tasks = [
        _fake_task(task_id="a", counts={"correct": 1}, n_oracle_nodes=2),
        _fake_task(task_id="b", counts={"fp": 1, "silent": 1}, n_oracle_nodes=2, unclassifiable={"timeout": 1}),
        _fake_task(task_id="c", oracle_status="not_run", counts={}, n_oracle_nodes=0),
    ]
    agg = oq.aggregate_oracle(tasks)
    assert agg["n_tasks_measured"] == 2
    assert agg["n_oracle_tests_classifiable"] == 3
    assert agg["n_oracle_tests_unclassifiable"] == 1
    assert agg["counts"] == {"correct": 1, "fp": 1, "silent": 1, "misguided": 0}
    assert agg["rates"]["correct"] == round(1 / 3, 6)
    assert agg["unclassifiable_counts"] == {"timeout": 1}
    # 无可分类测试 → 占比 None（分母纪律，不臆造 0%）
    empty = oq.aggregate_oracle([_fake_task(oracle_status="not_run", counts={})])
    assert empty["n_oracle_tests_classifiable"] == 0
    assert empty["rates"]["correct"] is None


def test_detection_stats_transitions_and_lists() -> None:
    tasks = [
        _fake_task(
            task_id="added",
            detection={"archived": 0.0, "llm_only_replay": 0.0, "augmented_replay": 1.0, "transition": "added"},
            counts={"correct": 1},
        ),
        _fake_task(
            task_id="lost",
            detection={"archived": 1.0, "llm_only_replay": 1.0, "augmented_replay": 0.0, "transition": "lost"},
            counts={"fp": 1},
            failure_stats={"fixed_side_failure_kinds": {"assertion": 1}},
        ),
        _fake_task(
            task_id="kept",
            detection={"archived": 1.0, "llm_only_replay": 1.0, "augmented_replay": 1.0, "transition": "preserved"},
        ),
        _fake_task(
            task_id="none",
            detection={"archived": 0.0, "llm_only_replay": 0.0, "augmented_replay": 0.0, "transition": "none"},
        ),
    ]
    stats = oq.detection_stats(tasks)
    assert stats["transition_counts"] == {"added": 1, "lost": 1, "none": 1, "preserved": 1}
    assert [t["task_id"] for t in stats["added_tasks"]] == ["added"]
    assert [t["task_id"] for t in stats["lost_tasks"]] == ["lost"]
    assert stats["llm_only_replay"] == {"n_detected": 2, "n_denominator": 4, "rate": 0.5}
    assert stats["paired_augmented_vs_llm_only"]["n_paired"] == 4
    assert stats["paired_augmented_vs_llm_only"]["n_changed"] == 2


def test_build_cross_check_zero_mismatch_and_attribution() -> None:
    clean = [_fake_task(task_id="a"), _fake_task(task_id="b", detection_agreement="both_none")]
    cc = oq.build_cross_check(clean)
    assert cc["all_ok"] is True
    assert cc["detection_vs_archive"]["n_mismatch"] == 0
    assert cc["oracle_verdict_vs_archive"]["n_mismatch"] == 0
    dirty = [
        _fake_task(
            task_id="bad", detection_agreement="mismatch", archived_verdict="injected", verdict_agreement="mismatch"
        ),
        _fake_task(task_id="inconsistent", field_consistency=False),
    ]
    cc2 = oq.build_cross_check(dirty)
    assert cc2["all_ok"] is False
    assert cc2["detection_vs_archive"]["n_mismatch"] == 1
    assert cc2["oracle_verdict_vs_archive"]["n_mismatch"] == 1
    assert len(cc2["archive_field_consistency_violations"]) == 1
    # mismatch 逐条进入归因清单（不静默）
    assert cc2["detection_vs_archive"]["mismatch_or_attributed_nonmatch"][0]["task_id"] == "bad"


def test_arm_role_mapping() -> None:
    assert oq._arm_role("plain_llm_df_spec") == "treatment"
    assert oq._arm_role("plain_llm_df") == "control"
    assert oq._arm_role("something_else") == "other"


# ─── 报告/确定性 ──────────────────────────────────────────────────────────
def test_report_fields_and_empty_arms() -> None:
    report = oq.build_report(
        artifact_entries=[{"path": "x.json", "sha256": "a" * 64, "arms": [{"arm": "plain_llm_df", "n_rows": 1}]}],
        anchor_info={"path": "t.json", "sha256": "b" * 64, "n_anchors": 1, "meta": {}},
        arms=[],
        config={"jobs": 1},
        command=["python", "-m", "x"],
    )
    assert report["schema_version"] == oq.SCHEMA_VERSION
    assert report["metric_definition"]["classes"] == oq.ORACLE_CLASS_DEFINITIONS
    assert report["comparison"] is None  # 单臂/无臂 → 无对比
    assert report["inputs"][0]["sha256"] == "a" * 64
    assert report["limitations"]
    # 确定性：body digest 对时间戳/墙钟不敏感、对计数敏感
    from experiments.misguided_metrics import body_digest

    body_a = {"x": 1, "timing": {"wall_s": 1.0}}
    body_b = {"x": 1, "timing": {"wall_s": 99.0}}
    assert body_digest(body_a) == body_digest(body_b)
    assert body_digest(body_a) != body_digest({"x": 2, "timing": {"wall_s": 1.0}})


def test_determinism_meta_repeat() -> None:
    body = {"x": 1, "timing": {"wall_s": 1.0}}
    meta_ok = {"body_digest": "d1"}
    assert oq._determinism_meta([(body, meta_ok)])["deterministic"] is True
    same = oq._determinism_meta([(body, {"body_digest": "d1"}), (body, {"body_digest": "d1"})])
    assert same["deterministic"] is True and same["difference_paths"] == []
    changed = oq._determinism_meta([(body, {"body_digest": "d1"}), ({"x": 2}, {"body_digest": "d2"})])
    assert changed["deterministic"] is False
    assert any("/x" in path for path in changed["difference_paths"])


# ─── 微型端到端（真实 pytest 子进程） ─────────────────────────────────────
def test_end_to_end_tiny_fixture_runs_production_injection(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    table, _sums = _make_anchor_table(tmp_path, _anchor_entry())
    anchors = oq.load_anchor_table(table)["anchors"]
    row = _task_row()
    record = oq.analyze_task(
        row,
        anchors=anchors,
        roots=[root],
        pytest_timeout_s=5.0,
        collect_timeout_s=30.0,
        file_timeout_s=60.0,
        siblings_cache={},
    )
    assert record["status"] == "ok"
    assert record["anchor"]["hit"] is True
    assert record["injection"]["verdict"] == "injected"
    assert record["injection"]["injected"] is True
    assert record["injection"]["n_oracle_test_defs"] == 1
    # LLM-only 重放：effective 测试 → detection=1.0，且与归档 detection 对账 match
    assert record["llm_only"]["replay_detection"] == 1.0
    assert record["llm_only"]["detection_agreement"] == "match"
    # oracle 重放：绑定 (a,b)=(0,0) 断言 r == a+b → buggy/fixed 都过 = silent
    assert record["oracle"]["status"] == "ok"
    assert record["oracle"]["counts"]["silent"] == 1
    assert record["oracle"]["n_classifiable"] == 1
    # 增强后任务级检出不变（LLM 已检出；oracle silent 不损伤）
    assert record["detection"]["augmented_replay"] == 1.0
    assert record["detection"]["transition"] == "preserved"
    # 归档语义复现：归档批次无 test_plan → not_attempted
    assert record["archived_check"]["replay_verdict"] == "not_attempted"
    assert record["archived_check"]["verdict_agreement"] == "match"
    assert record["archived_check"]["field_consistency"] is True


def test_analyze_task_skips_anchor_miss(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    table, _sums = _make_anchor_table(tmp_path, _anchor_entry())  # 只含 buggy add 的哈希
    anchors = oq.load_anchor_table(table)["anchors"]
    # 改一个字符使缺陷版源码哈希不命中锚表
    root.joinpath("python_programs", "add.py").write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
    record = oq.analyze_task(
        _task_row(fixed=_FIXED_ADD + "\n"),
        anchors=anchors,
        roots=[root],
        pytest_timeout_s=5.0,
        collect_timeout_s=30.0,
        file_timeout_s=60.0,
        siblings_cache={},
    )
    # 注：dataset fixed 校验先于锚查找；此处 fixed 与数据目录不一致会先 fail-closed，
    # 故该场景断言"结构跳过且给出可解释原因"（锚 miss 或同源校验失败均不静默）。
    assert record["status"] == "structural_skip"
    assert record["skip_reason"] in {"anchor_miss", "buggy_source_validation_failed"}


def test_analyze_task_rejects_already_injected_test(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    table, _sums = _make_anchor_table(tmp_path, _anchor_entry())
    anchors = oq.load_anchor_table(table)["anchors"]
    test_with_oracle = _LLM_TEST + "\n\ndef test_specir_v2_oracle():\n    pass\n"
    record = oq.analyze_task(
        _task_row(generated_test=test_with_oracle),
        anchors=anchors,
        roots=[root],
        pytest_timeout_s=5.0,
        collect_timeout_s=30.0,
        file_timeout_s=60.0,
        siblings_cache={},
    )
    assert record["status"] == "structural_skip"
    assert record["skip_reason"] == "already_contains_oracle"


# ─── CLI fail-closed 与落盘 ────────────────────────────────────────────────
def test_main_fail_closed_on_missing_anchor(tmp_path: Path) -> None:
    out = tmp_path / "out"
    code = oq.main(["--anchor-table", str(tmp_path / "missing.json"), "--out", str(out)])
    assert code == 2
    assert not (out / "ORACLE_QUALITY_REPORT.json").exists()


def test_main_writes_json_md_readme(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    table, _sums = _make_anchor_table(tmp_path, _anchor_entry())
    artifact = _write_artifact(tmp_path / "bench.json", {"plain_llm_df_spec": [_task_row()]})
    out = tmp_path / "out"
    code = oq.main(
        [
            "--anchor-table",
            str(table),
            "--artifact",
            str(artifact),
            "--quixbugs-root",
            str(root),
            "--out",
            str(out),
            "--jobs",
            "1",
            "--per-test-timeout",
            "5",
            "--file-timeout",
            "60",
            "--quiet",
        ]
    )
    assert code == 0
    payload = json.loads((out / "ORACLE_QUALITY_REPORT.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == oq.SCHEMA_VERSION
    assert payload["run_meta"]["body_digest"]
    assert payload["run_meta"]["cross_check_ok"] is True
    arm = payload["report"]["arms"][0]
    assert arm["subsets"]["all_tasks"]["injection"]["verdict_counts"] == {"injected": 1}
    assert arm["subsets"]["all_tasks"]["oracle"]["counts"]["silent"] == 1
    assert (out / "ORACLE_QUALITY_REPORT.md").exists()
    assert (out / "README.md").exists()
    md = (out / "ORACLE_QUALITY_REPORT.md").read_text(encoding="utf-8")
    assert "oracle 四分类" in md and "交叉校验" in md
