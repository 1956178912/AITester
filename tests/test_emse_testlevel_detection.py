"""emse_testlevel_detection（测试级检出画像）纯函数回归测试。

覆盖（零 LLM / 零网络 / 零 pytest 子进程——只测纯函数与聚合口径）：
- node id 归一口径（去 tmpdir 绝对路径，跨运行/跨臂可比）；
- 两路解析（记录插件 JSONL / `-v` 文本）逐测试结果折叠与交叉一致性；
- 逐测试四分类 + `other`（skipped / 单侧缺失 / 收集失败）与套件级标签；
- Wilcoxon 符号秩精确零分布（对照手算闭式值）与配对统计口径；
- 单源聚合分母（f2p 率、盲测质量、f2f、单测试扛下检出的换算表）；
- 测试级配对（按 node id）与任务聚类配对（每任务一个单位）。
"""

from __future__ import annotations

import json

from experiments.emse_testlevel_detection import (
    _dist_summary,
    _fold_plugin_records,
    _merge_reconciliation,
    _norm_nodeid,
    _parse_verbose,
    _quantile,
    aggregate_source,
    classify_tests,
    suite_class,
    task_clustered_pair,
    testlevel_pair,
    wilcoxon_signed_rank,
)

# ─── node id 归一 ──────────────────────────────────────────────────────


def test_norm_nodeid_strips_tmpdir_prefix() -> None:
    raw = "/var/folders/x/T/tl_bitcount_ab/python_testcases/test_bitcount.py::test_bitcount_zero"
    assert _norm_nodeid(raw, "bitcount") == "test_bitcount.py::test_bitcount_zero"


def test_norm_nodeid_keeps_parametrized_suffix() -> None:
    raw = "/tmp/tl_x/python_testcases/test_wrap.py::test_wrap_4[1-2]"
    assert _norm_nodeid(raw, "wrap") == "test_wrap.py::test_wrap_4[1-2]"


def test_norm_nodeid_fallback_without_marker() -> None:
    """无 `test_{module}.py::` 标记时退化为 `::` 之后部分（仍任务隔离）。"""
    assert _norm_nodeid("other_dir/test_x.py::test_a", "bitcount") == "test_bitcount.py::test_a"


# ─── 两路解析 ──────────────────────────────────────────────────────────


def _write_jsonl(tmp_path, records: list[dict]) -> str:
    p = tmp_path / "outcomes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return str(p)


def test_fold_plugin_records_phases(tmp_path) -> None:
    """setup 失败→error；call 失败→fail；call 跳过→skip；teardown 失败→error。"""
    path = _write_jsonl(
        tmp_path,
        [
            {"nodeid": "test_m.py::t_pass", "when": "setup", "outcome": "passed"},
            {"nodeid": "test_m.py::t_pass", "when": "call", "outcome": "passed"},
            {"nodeid": "test_m.py::t_pass", "when": "teardown", "outcome": "passed"},
            {"nodeid": "test_m.py::t_fail", "when": "setup", "outcome": "passed"},
            {"nodeid": "test_m.py::t_fail", "when": "call", "outcome": "failed"},
            {"nodeid": "test_m.py::t_err", "when": "setup", "outcome": "failed"},
            {"nodeid": "test_m.py::t_skip", "when": "setup", "outcome": "skipped"},
            {"nodeid": "test_m.py::t_skip", "when": "call", "outcome": "skipped"},
            {"nodeid": "test_m.py::t_td", "when": "setup", "outcome": "passed"},
            {"nodeid": "test_m.py::t_td", "when": "call", "outcome": "passed"},
            {"nodeid": "test_m.py::t_td", "when": "teardown", "outcome": "failed"},
        ],
    )
    from pathlib import Path

    out = _fold_plugin_records(Path(path), "m")
    assert out == {
        "test_m.py::t_pass": "pass",
        "test_m.py::t_fail": "fail",
        "test_m.py::t_err": "error",
        "test_m.py::t_skip": "skip",
        "test_m.py::t_td": "error",
    }


def test_verbose_parse_ignores_summary_lines() -> None:
    """`-v` 正文行（node 在前）被解析；`-rA` 摘要行（outcome 在前）被忽略。"""
    stdout = (
        "collecting ... collected 2 items\n"
        "/tmp/tl_m/python_testcases/test_m.py::t_a PASSED [ 50%]\n"
        "/tmp/tl_m/python_testcases/test_m.py::t_b[2] FAILED [100%]\n"
        "=========================== short test summary info ============================\n"
        "PASSED /tmp/tl_m/python_testcases/test_m.py::t_a\n"
        "FAILED /tmp/tl_m/python_testcases/test_m.py::t_b[2]\n"
    )
    assert _parse_verbose(stdout, "m") == {"test_m.py::t_a": "pass", "test_m.py::t_b[2]": "fail"}


def test_two_parsers_agree_on_same_run() -> None:
    """同一运行的两路解析必须一致（不一致会被 run_side 记入 parse_mismatch）。"""
    stdout = (
        "/tmp/tl_m/python_testcases/test_m.py::t_a PASSED [ 50%]\n"
        "/tmp/tl_m/python_testcases/test_m.py::t_b FAILED [100%]\n"
    )
    plugin = {
        "test_m.py::t_a": "pass",
        "test_m.py::t_b": "fail",
    }
    assert _parse_verbose(stdout, "m") == plugin


# ─── 逐测试分类 ────────────────────────────────────────────────────────


def _side(outcomes: dict[str, str], *, timed_out: bool = False) -> dict:
    return {"outcomes": outcomes, "timed_out": timed_out}


def test_classify_tests_four_classes() -> None:
    buggy = _side({"test_m.py::a": "fail", "test_m.py::b": "pass", "test_m.py::c": "fail", "test_m.py::d": "pass"})
    fixed = _side({"test_m.py::a": "pass", "test_m.py::b": "pass", "test_m.py::c": "fail", "test_m.py::d": "fail"})
    rows, counts = classify_tests("m", buggy, fixed)
    cls = {r["node"]: r["cls"] for r in rows}
    assert cls == {
        "test_m.py::a": "f2p",
        "test_m.py::b": "p2p",
        "test_m.py::c": "f2f",
        "test_m.py::d": "p2f",
    }
    assert counts == {"f2p": 1, "p2p": 1, "f2f": 1, "p2f": 1, "other": 0}


def test_classify_tests_other_cases() -> None:
    """skipped 与单侧缺失 → other（不进四分类分母）。"""
    buggy = _side({"test_m.py::a": "pass", "test_m.py::b": "fail", "test_m.py::skip": "skip"})
    fixed = _side({"test_m.py::a": "pass", "test_m.py::skip": "pass", "test_m.py::only_fixed": "pass"})
    rows, counts = classify_tests("m", buggy, fixed)
    cls = {r["node"]: r["cls"] for r in rows}
    assert cls["test_m.py::skip"] == "other"
    assert cls["test_m.py::only_fixed"] == "other"
    # b 只在 buggy 侧出现 → other
    assert cls["test_m.py::b"] == "other"
    assert counts == {"f2p": 0, "p2p": 1, "f2f": 0, "p2f": 0, "other": 3}


def test_classify_tests_unusable_side_is_all_other() -> None:
    """任一侧无逐测试数据（收集错误/超时）→ 全部 other，四分类计数为 0。"""
    buggy = _side({"test_m.py::a": "fail"})
    fixed = _side({}, timed_out=True)
    rows, counts = classify_tests("m", buggy, fixed)
    assert counts == {"f2p": 0, "p2p": 0, "f2f": 0, "p2f": 0, "other": 1}
    assert rows[0]["fixed"] == "unavailable"


def test_suite_class_labels() -> None:
    clean = {"f2p": 1, "p2p": 5, "f2f": 0, "p2f": 0, "other": 0}
    rows = [{"node": "n", "buggy": "fail", "fixed": "pass", "cls": "f2p"}]
    ok = {"outcomes": {"n": "fail"}, "timed_out": False}
    ok2 = {"outcomes": {"n": "pass"}, "timed_out": False}
    to = {"outcomes": {}, "timed_out": True}
    assert suite_class(clean, ok, ok2, rows) == "detecting_clean"
    assert suite_class({"f2p": 1, "p2p": 0, "f2f": 1, "p2f": 0, "other": 0}, ok, ok, rows) == "detecting_invalid"
    assert suite_class({"f2p": 0, "p2p": 3, "f2f": 0, "p2f": 0, "other": 0}, ok2, ok2, rows) == "blind_clean"
    assert suite_class({"f2p": 0, "p2p": 0, "f2f": 2, "p2f": 0, "other": 0}, ok, ok, rows) == "invalid_only"
    assert suite_class(clean, to, ok2, rows) == "timeout"
    assert suite_class({k: 0 for k in ("f2p", "p2p", "f2f", "p2f", "other")}, ok, ok2, []) == "no_pertest_data"


# ─── 统计原语 ──────────────────────────────────────────────────────────


def test_wilcoxon_exact_all_positive_small_n() -> None:
    """n=5 全正差（秩 1..5，W+=15 最大）→ 双侧精确 p = 2/2^5 = 0.0625。"""
    out = wilcoxon_signed_rank([1.0, 2.0, 3.0, 4.0, 5.0])
    assert out["n_nonzero"] == 5
    assert out["w_plus"] == 15.0
    assert out["p_exact"] == 0.0625


def test_wilcoxon_exact_symmetric_is_one() -> None:
    """对称差（+x/−x）→ W+ 居中，双侧 p=1.0。"""
    out = wilcoxon_signed_rank([1.0, -1.0, 2.0, -2.0])
    assert out["p_exact"] == 1.0


def test_wilcoxon_zero_diffs_dropped() -> None:
    out = wilcoxon_signed_rank([0.0, 0.0])
    assert out["n_nonzero"] == 0 and out["p_exact"] is None
    mixed = wilcoxon_signed_rank([0.0, 1.0, 2.0, 3.0])
    assert mixed["n_nonzero"] == 3 and mixed["n_zero_diff"] == 1


def test_quantile_and_dist_summary() -> None:
    assert _quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert _quantile([], 0.5) is None
    s = _dist_summary([0.0, 0.5, 1.0])
    assert s["n"] == 3 and s["mean"] == 0.5 and s["median"] == 0.5 and s["min"] == 0.0 and s["max"] == 1.0


# ─── 聚合口径（分母显式）──────────────────────────────────────────────


def _mk_task(
    task_id: str,
    counts: dict[str, int],
    *,
    archived_det: float | None,
    reproduced: float | None = None,
    buggy_rc: int | None = 1,
    fixed_rc: int | None = 0,
) -> dict:
    n_class = counts["f2p"] + counts["p2p"] + counts["f2f"] + counts["p2f"]
    return {
        "set": "s",
        "arm_letter": "",
        "task_id": task_id,
        "module": task_id.rsplit("__", maxsplit=1)[-1],
        "archived_detection_rate": archived_det,
        "archived_stop_reason": "test_passed",
        "n_generated_test_chars": 100,
        "n_ast_test_defs": n_class + counts["other"],
        "material_ok": True,
        "material_mismatch": {"archived_fixed_vs_dataset_fixed": False, "archived_gold_tests_vs_dataset": False},
        "needs_quixbugs_support": False,
        "suite_class": "detecting_clean" if counts["f2p"] else "blind_clean",
        "counts": counts,
        "n_classifiable": n_class,
        "n_union": n_class + counts["other"],
        "n_only_buggy": 0,
        "n_only_fixed": 0,
        "tests": [],
        "buggy": {
            "rc": buggy_rc,
            "timed_out": buggy_rc is None,
            "wall_s": 0.5,
            "parser": "plugin+verbose",
            "n_nodeids_plugin": n_class,
            "n_nodeids_verbose": n_class,
            "parse_agree_n": n_class,
            "parse_mismatch": [],
            "exec_error_heuristic": False,
            "stdout_sha256": "x",
            "stdout_tail": "",
        },
        "fixed": {
            "rc": fixed_rc,
            "timed_out": fixed_rc is None,
            "wall_s": 0.5,
            "parser": "plugin+verbose",
            "n_nodeids_plugin": n_class,
            "n_nodeids_verbose": n_class,
            "parse_agree_n": n_class,
            "parse_mismatch": [],
            "exec_error_heuristic": False,
            "stdout_sha256": "y",
            "stdout_tail": "",
        },
        "task_level_reproduced": reproduced if reproduced is not None else archived_det,
        "f2p_call_phase": counts["f2p"],
        "f2p_setup_teardown_error": 0,
    }


def _mk_run(tasks: list[dict]) -> dict:
    return {
        "source": {
            "label": "s",
            "kind": "batch5",
            "arm_letter": "",
            "cache_namespace": "",
            "path": "p.json",
            "sha256": "z",
        },
        "n_rows": len(tasks),
        "skipped_no_gold": [],
        "wall_s": 1.0,
        "tasks": tasks,
    }


def test_aggregate_source_denominators_and_conversion() -> None:
    """f2p 率分母 = 两侧都出现的可分类测试；单测试扛下的检出按 f2p=1 计数。"""
    t1 = _mk_task("quixbugs__a", {"f2p": 1, "p2p": 9, "f2f": 0, "p2f": 0, "other": 0}, archived_det=1.0)
    t2 = _mk_task("quixbugs__b", {"f2p": 3, "p2p": 5, "f2f": 2, "p2f": 0, "other": 1}, archived_det=1.0)
    t3 = _mk_task("quixbugs__c", {"f2p": 0, "p2p": 4, "f2f": 0, "p2f": 0, "other": 0}, archived_det=0.0, buggy_rc=0)
    agg = aggregate_source(_mk_run([t1, t2, t3]))
    assert agg["class_totals"] == {"f2p": 4, "p2p": 18, "f2f": 2, "p2f": 0, "other": 1}
    assert agg["n_classifiable_total"] == 24
    assert agg["n_union_total"] == 25
    assert agg["pooled_f2p_rate"] == round(4 / 24, 4)
    assert agg["pooled_f2p_rate_union_denom"] == round(4 / 25, 4)
    assert agg["blind_mass"]["p2p_over_p2p_plus_f2p"] == round(18 / 22, 4)
    assert agg["invalid_mass"]["f2f"] == 2
    assert agg["invalid_mass"]["n_suites_with_f2f"] == 1
    assert agg["invalid_mass"]["n_suites_green_on_fixed_rc0"] == 3
    assert agg["detection_conversion"]["n_archived_detection_1"] == 2
    assert agg["detection_conversion"]["f2p_count_distribution"] == {"0": 0, "1": 1, "2": 0, "3+": 1}
    assert agg["detection_conversion"]["n_single_test_carried"] == 1
    assert agg["per_task_f2p_fraction"]["n"] == 3
    assert agg["task_level_reconciliation"]["n_disagree"] == 0
    assert agg["parser_crosscheck"]["n_mismatches"] == 0
    assert agg["n_no_pertest_data"] == 0


# ─── 配对（测试级 + 任务聚类）──────────────────────────────────────────


def _suite(task_id: str, node_classes: dict[str, str], det: float | None = 1.0) -> dict:
    counts = {"f2p": 0, "p2p": 0, "f2f": 0, "p2f": 0, "other": 0}
    tests = []
    for node, cls in node_classes.items():
        counts[cls] += 1
        tests.append(
            {
                "node": node,
                "buggy": "fail" if cls in ("f2p", "f2f") else "pass",
                "fixed": "fail" if cls in ("f2f", "p2f") else "pass",
                "cls": cls,
            }
        )
    n_class = sum(v for k, v in counts.items() if k != "other")
    return {
        "task_id": task_id,
        "suite_class": "detecting_clean" if counts["f2p"] else "blind_clean",
        "counts": counts,
        "n_classifiable": n_class,
        "n_union": len(tests),
        "n_only_buggy": 0,
        "n_only_fixed": 0,
        "tests": tests,
        "archived_detection_rate": det,
        "task_level_reproduced": det,
        "f2p_call_phase": counts["f2p"],
        "f2p_setup_teardown_error": 0,
        "buggy": {
            "rc": 1,
            "timed_out": False,
            "parser": "plugin+verbose",
            "parse_agree_n": len(tests),
            "parse_mismatch": [],
            "exec_error_heuristic": False,
            "stdout_sha256": "b",
        },
        "fixed": {
            "rc": 0,
            "timed_out": False,
            "parser": "plugin+verbose",
            "parse_agree_n": len(tests),
            "parse_mismatch": [],
            "exec_error_heuristic": False,
            "stdout_sha256": "f",
        },
    }


def test_testlevel_pair_counts_shared_and_arm_specific() -> None:
    """共享 node id 才进配对分母；独有 node id 单列；other 丢弃并计数。"""
    x = _mk_run([_suite("quixbugs__a", {"test_a.py::t1": "f2p", "test_a.py::t2": "p2p", "test_a.py::xonly": "f2p"})])
    y = _mk_run([_suite("quixbugs__a", {"test_a.py::t1": "p2p", "test_a.py::t2": "p2p", "test_a.py::yonly": "f2p"})])
    out = testlevel_pair(x, y, "X", "Y")
    assert out["n_test_nodeids_shared"] == 2
    assert out["n_nodeids_x_only"] == 1 and out["n_nodeids_y_only"] == 1
    assert out["n_pairs_testlevel"] == 2
    assert out["b_pos_x_only_f2p"] == 1 and out["b_neg_y_only_f2p"] == 0
    assert out["delta_pp"] == 50.0
    assert out["ratio"] == "1:0"


def test_testlevel_pair_drops_other_nodes() -> None:
    x = _mk_run([_suite("quixbugs__a", {"test_a.py::t1": "f2p", "test_a.py::t2": "other"})])
    y = _mk_run([_suite("quixbugs__a", {"test_a.py::t1": "p2p", "test_a.py::t2": "p2p"})])
    out = testlevel_pair(x, y, "X", "Y")
    assert out["n_shared_dropped_other"] == 1
    assert out["n_pairs_testlevel"] == 1


def test_task_clustered_pair_direction_and_ties() -> None:
    """任务聚类：X 更多的任务数 / Y 更多的任务数 / 并列，且符号检验 = McNemar 精确。"""
    x = _mk_run(
        [
            _suite("quixbugs__a", {"test_a.py::t1": "f2p", "test_a.py::t2": "f2p", "test_a.py::t3": "p2p"}),
            _suite("quixbugs__b", {"test_b.py::t1": "p2p"}),
            _suite("quixbugs__c", {"test_c.py::t1": "p2p"}),
        ]
    )
    y = _mk_run(
        [
            _suite("quixbugs__a", {"test_a.py::t1": "p2p", "test_a.py::t2": "p2p", "test_a.py::t3": "p2p"}),
            _suite("quixbugs__b", {"test_b.py::t1": "f2p"}),
            _suite("quixbugs__c", {"test_c.py::t1": "p2p"}),
        ]
    )
    out = task_clustered_pair(x, y, "X", "Y")
    assert out["n_tasks"] == 3
    assert out["sum_f2p_x"] == 2 and out["sum_f2p_y"] == 1
    assert out["n_tasks_more_f2p_x"] == 1
    assert out["n_tasks_more_f2p_y"] == 1
    assert out["n_tasks_tied"] == 1
    assert out["sign_test_mcnemar_exact_p"] == 1.0
    assert out["mean_delta_f2p_count"] is not None


def test_merge_reconciliation_counts() -> None:
    tasks = [
        {"archived_detection_rate": 1.0, "task_level_reproduced": 1.0},
        {"archived_detection_rate": 0.0, "task_level_reproduced": None},
    ]
    assert _merge_reconciliation(tasks) == {"1.0->1.0": 1, "0.0->None": 1}


# ─── 替代口径敏感性 / 独立复核解析 / 复用加载 ──────────────────────────


def test_pytest_summary_regex_parsing() -> None:
    """独立复核读取的是 pytest 自身汇总行（不依赖本脚本解析器）。"""
    from experiments.emse_testlevel_detection import _PYTEST_SUMMARY_RE

    def counts(line: str) -> dict[str, int]:
        return {m.group(2): int(m.group(1)) for m in _PYTEST_SUMMARY_RE.finditer(line)}

    assert counts("===== 37 failed, 9 passed in 0.08s =====") == {"failed": 37, "passed": 9}
    assert counts("46 passed in 0.07s") == {"passed": 46}
    assert counts("2 failed, 1 error, 5 passed in 0.1s") == {"failed": 2, "error": 1, "passed": 5}


def test_mcnemar_from_maps_standard_caliber_skips_none() -> None:
    """标准口径：任一侧 None 的任务退出配对分母（与既有 _effective_pair 同规则）。"""
    from experiments.emse_testlevel_detection import _mcnemar_from_maps

    x = {"t1": 1.0, "t2": 0.0, "t3": None, "t4": 1.0}
    y = {"t1": 0.0, "t2": 1.0, "t3": 1.0, "t4": 1.0}
    out = _mcnemar_from_maps(x, y, "X", "Y")
    assert out["n_pairs"] == 3  # t3 被剔除
    assert out["b_pos_x_only"] == 1 and out["b_neg_y_only"] == 1
    assert out["ratio"] == "1:1"
    assert out["p_value"] == 1.0


def test_hang_sensitivity_flips_and_contrast() -> None:
    """替代口径：buggy 侧挂死 ∧ fixed 侧 rc=0 → 记检出；只影响敏感性表，不影响主口径。"""
    from experiments.emse_testlevel_detection import hang_sensitivity

    def mk(tid: str, *, buggy_to: bool, fixed_rc: int, repro: float | None) -> dict:
        t = _mk_task(tid, {"f2p": 0, "p2p": 2, "f2f": 0, "p2f": 0, "other": 0}, archived_det=None, reproduced=None)
        t["buggy"]["timed_out"] = buggy_to
        t["buggy"]["rc"] = None if buggy_to else 1
        t["fixed"]["timed_out"] = False
        t["fixed"]["rc"] = fixed_rc
        t["task_level_reproduced"] = repro
        return t

    run_a = _mk_run([mk("quixbugs__a", buggy_to=True, fixed_rc=0, repro=None)])
    run_a["source"]["label"], run_a["source"]["arm_letter"] = "A", "A"
    run_b = _mk_run([mk("quixbugs__a", buggy_to=False, fixed_rc=0, repro=0.0)])
    run_b["source"]["label"], run_b["source"]["arm_letter"] = "B", "B"
    out = hang_sensitivity([run_a, run_b])
    assert out["flip_task_ids_per_source"] == {"A": ["quixbugs__a"], "B": []}
    assert out["n_flip_tasks_per_source"] == {"A": 1, "B": 0}
    assert len(out["contrasts"]) == 1
    assert out["contrasts"][0]["ratio"] == "1:0"
    assert out["contrasts"][0]["n_pairs"] == 1
    # 主口径（task_level_reproduced）不被改写
    assert run_a["tasks"][0]["task_level_reproduced"] is None


def test_load_reused_report_rebuilds_runs(tmp_path) -> None:
    """--reuse-json：从既有工件重建 runs（measured 字段原样复用）。"""
    from experiments.emse_testlevel_detection import load_reused_report

    task = _mk_task("quixbugs__a", {"f2p": 1, "p2p": 1, "f2f": 0, "p2f": 0, "other": 0}, archived_det=1.0)
    task["set"] = "quixbugs50_batch5"
    prev = {
        "meta": {"wall_clock_total_s": 12.5, "cmdline": "python ... --jobs 1", "n_pytest_runs": 410},
        "tasks": [task],
        "aggregates": {"per_source": [{"label": "quixbugs50_batch5", "n_rows_in_artifact": 50, "wall_s": 12.5}]},
        "handcheck": [{"set": "quixbugs50_batch5", "task_id": "quixbugs__a", "buggy_stdout": "B", "fixed_stdout": "F"}],
    }
    path = tmp_path / "prev.json"
    path.write_text(json.dumps(prev), encoding="utf-8")
    sources = [
        {
            "label": "quixbugs50_batch5",
            "kind": "batch5",
            "arm_letter": "",
            "cache_namespace": "",
            "path": tmp_path / "bench.json",
            "sha256": "x",
        }
    ]
    out = load_reused_report(path, sources, {"excluded_task_ids": ["quixbugs__z"]})
    assert out["wall_clock_total_s"] == 12.5
    assert len(out["runs"]) == 1
    assert out["runs"][0]["n_rows"] == 50
    assert out["runs"][0]["skipped_no_gold"] == ["quixbugs__z"]
    assert out["runs"][0]["handcheck_raw"][("quixbugs50_batch5", "quixbugs__a")]["buggy_stdout"] == "B"
