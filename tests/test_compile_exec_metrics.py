"""A-11 编译率 / 执行率工具契约测试（零 LLM / 零网络 / 确定性）。

锁定 ``experiments/compile_exec_metrics.py`` 的核心口径：
- compile_rate 行级判定（ast.parse 成功；空产物单列不算编译失败）；
- exec_rate 行级判定（pytest --collect-only 可收集；import/collection error 归因；
  收集超时单列）；
- 材料可重建性判定（QuixBugs 缺陷版优先/回退 fixed；synthetic 跨文件
  材料缺失 → material_incomplete 不进 exec 分母；单文件用归档 fixed）；
- 执行树物化（平铺 + python_programs 双布局 + QuixBugs 辅助材料）；
- 分母纪律（空产物 / 材料不完整 / 超时不进 exec 率分母；比率 0 分母 → None）；
- 原因分布、批次×臂表、跨 seed 合并按计数重算（不做比率平均）；
- 报告字段、body digest 确定性、CLI fail-closed。

测试全部使用 tmp_path 微型 fixture；必要的真实 pytest 子进程为本地执行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.compile_exec_metrics as ce

_BUGGY_ADD = "def add(a, b):\n    return a - b\n"
_FIXED_ADD = "def add(a, b):\n    return a + b\n"
_OK_TEST = "from add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


# ─── 微型 fixture 工具 ─────────────────────────────────────────────────────
def _make_qxb_root(tmp_path: Path) -> Path:
    """最小 QuixBugs 口径根（python_programs + correct + 辅助材料）。"""
    root = tmp_path / "qxb"
    (root / "python_programs").mkdir(parents=True)
    (root / "correct_python_programs").mkdir(parents=True)
    (root / "python_programs" / "add.py").write_text(_BUGGY_ADD, encoding="utf-8")
    (root / "correct_python_programs" / "add.py").write_text(_FIXED_ADD, encoding="utf-8")
    support = root / "python_testcases"
    support.mkdir()
    (support / "node.py").write_text("class Node:\n    pass\n", encoding="utf-8")
    (support / "load_testdata.py").write_text("def load():\n    return []\n", encoding="utf-8")
    (root / "json_testcases").mkdir()
    return root


def _quixbugs_row(generated_test: str = _OK_TEST, task_id: str = "quixbugs__add") -> dict:
    """最小 QuixBugs 归档行。"""
    return {
        "task_id": task_id,
        "generated_test": generated_test,
        "task_metadata": {
            "source": "quixbugs",
            "program": "add",
            "fixed": _FIXED_ADD,
            "suggested_function": "add",
            "is_cross_file": False,
        },
    }


def _synthetic_row(generated_test: str = "from task_0000 import f\n\n\ndef test_f():\n    assert f(1) == 1\n") -> dict:
    """最小 synthetic 单文件归档行（无缺陷版源码，只有 gold fixed）。"""
    return {
        "task_id": "synthetic__task_0000",
        "generated_test": generated_test,
        "task_metadata": {
            "source": "synthetic",
            "is_cross_file": False,
            "fixed": "def f(x):\n    return x\n",
            "suggested_function": "f",
        },
    }


def _fake_row(
    *,
    status: str = "ok",
    compile_ok: bool = True,
    empty: bool = False,
    n_test_defs: int = 1,
    material_ok: bool = True,
    material_source: str = "buggy",
    exec_ok: bool | None = True,
    exec_reason: str | None = None,
    timed_out: bool = False,
) -> dict:
    """构造 aggregate_rows 消费的行记录（键集合与 analyze_row 同构）。"""
    return {
        "task_id": "t",
        "status": status,
        "compile": {
            "status": "empty" if empty else ("ok" if compile_ok else "syntax_error"),
            "ok": compile_ok,
            "empty": empty,
            "n_test_defs": n_test_defs,
            "error": None,
        },
        "material": {
            "ok": material_ok,
            "reason": None if material_ok else "material_incomplete",
            "material_source": material_source if material_ok else None,
        },
        "exec": {
            "attempted": material_ok and not empty,
            "ok": exec_ok,
            "reason": exec_reason,
            "timed_out": timed_out,
        },
    }


def _write_artifact(path: Path, arms: dict[str, list[dict]]) -> Path:
    """写最小 benchmark 工件 JSON。"""
    payload = {
        "timestamp": "2026-10-17T00:00:00+00:00",
        "dataset": "quixbugs",
        "results": {arm: {"details": rows} for arm, rows in arms.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ─── 编译判定 ──────────────────────────────────────────────────────────────
def test_compile_generated_test_ok_counts_test_defs() -> None:
    code = "import pytest\n\n\ndef _helper():\n    return 1\n\n\ndef test_a():\n    assert _helper()\n\n\ndef test_b():\n    assert True\n"
    result = ce.compile_generated_test(code)
    assert result == {
        "status": "ok",
        "ok": True,
        "empty": False,
        "n_test_defs": 2,
        "error": None,
    }


def test_compile_generated_test_syntax_error() -> None:
    result = ce.compile_generated_test("def test_x(:\n    pass\n")
    assert result["status"] == "syntax_error"
    assert result["ok"] is False
    assert result["empty"] is False
    assert "line" in str(result["error"])


def test_compile_generated_test_empty() -> None:
    for value in (None, "", "   \n\t"):
        result = ce.compile_generated_test(value)
        assert result["status"] == "empty"
        assert result["ok"] is False and result["empty"] is True
        assert result["n_test_defs"] == 0


def test_compile_generated_test_no_test_defs_still_compiles() -> None:
    result = ce.compile_generated_test("def helper():\n    return 1\n")
    assert result["ok"] is True
    assert result["n_test_defs"] == 0


# ─── 收集结果分类（纯函数） ────────────────────────────────────────────────
def test_classify_collect_result_ok() -> None:
    result = ce.classify_collect_result(0, "test_x.py::test_a", timed_out=False, n_nodes=1)
    assert result["ok"] is True and result["reason"] is None


def test_classify_collect_result_no_tests() -> None:
    assert ce.classify_collect_result(5, "no tests ran", timed_out=False, n_nodes=0)["reason"] == "no_tests_collected"
    assert ce.classify_collect_result(0, "", timed_out=False, n_nodes=0)["reason"] == "no_tests_collected"


def test_classify_collect_result_import_error() -> None:
    output = "E   ModuleNotFoundError: No module named 'missing_mod'"
    result = ce.classify_collect_result(2, output, timed_out=False, n_nodes=0)
    assert result["ok"] is False
    assert result["reason"] == "import_error"
    assert "missing_mod" in result["detail"]


def test_classify_collect_result_syntax_error() -> None:
    output = "E   File test_x.py, line 2\nE     def test(:\nE         ^\nE   SyntaxError: invalid syntax"
    result = ce.classify_collect_result(2, output, timed_out=False, n_nodes=0)
    assert result["reason"] == "syntax_error"


def test_classify_collect_result_collect_error_generic() -> None:
    result = ce.classify_collect_result(2, "ERROR: usage error", timed_out=False, n_nodes=0)
    assert result["reason"] == "collect_error"


def test_classify_collect_result_timeout_single_listed() -> None:
    result = ce.classify_collect_result(None, "", timed_out=True, n_nodes=0)
    assert result["ok"] is None
    assert result["reason"] == "collect_timeout"


# ─── 材料可重建性判定 ──────────────────────────────────────────────────────
def test_classify_material_quixbugs_prefers_buggy(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    material = ce.classify_material(_quixbugs_row(), roots=[root])
    assert material["ok"] is True
    assert material["layout"] == "quixbugs"
    assert material["material_source"] == "buggy"
    assert material["target_code"] == _BUGGY_ADD
    assert material["module_name"] == "add"


def test_classify_material_quixbugs_falls_back_to_fixed(tmp_path: Path) -> None:
    root = tmp_path / "empty_qxb"
    (root / "python_programs").mkdir(parents=True)
    row = _quixbugs_row()
    row["task_metadata"]["fixed"] = _FIXED_ADD
    material = ce.classify_material(row, roots=[root])
    assert material["ok"] is True
    assert material["material_source"] == "fixed_gold"
    assert material["target_code"] == _FIXED_ADD


def test_classify_material_quixbugs_missing_all_is_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "empty_qxb"
    (root / "python_programs").mkdir(parents=True)
    row = _quixbugs_row()
    row["task_metadata"]["fixed"] = ""
    material = ce.classify_material(row, roots=[root])
    assert material["ok"] is False
    assert material["reason"] == "material_incomplete"


def test_classify_material_synthetic_cross_file_incomplete() -> None:
    row = {
        "task_id": "synthetic__task_0002",
        "generated_test": "from task_0002 import f\n",
        "task_metadata": {"source": "synthetic", "is_cross_file": True, "fixed": ""},
    }
    material = ce.classify_material(row, roots=[])
    assert material["ok"] is False
    assert material["reason"] == "material_incomplete"
    assert "跨文件" in material["detail"]


def test_classify_material_synthetic_single_file_uses_fixed_gold() -> None:
    material = ce.classify_material(_synthetic_row(), roots=[])
    assert material["ok"] is True
    assert material["layout"] == "flat"
    assert material["material_source"] == "fixed_gold"
    assert material["module_name"] == "task_0000"


def test_classify_material_rejects_invalid_module_name() -> None:
    row = {
        "task_id": "synthetic__bad-name!",
        "generated_test": "def test_x():\n    assert True\n",
        "task_metadata": {"source": "synthetic", "is_cross_file": False, "fixed": "def f():\n    pass\n"},
    }
    material = ce.classify_material(row, roots=[])
    assert material["ok"] is False
    assert material["reason"] == "material_incomplete"


# ─── 执行树物化 / 收集重放（真实 pytest 子进程） ───────────────────────────
def test_materialize_exec_tree_quixbugs_layout(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    material = ce.classify_material(_quixbugs_row(), roots=[root])
    version_dir = tmp_path / "version"
    pythonpath = ce.materialize_exec_tree(material, version_dir, _OK_TEST)
    assert (version_dir / "add.py").is_file()
    assert (version_dir / "python_programs" / "__init__.py").is_file()
    assert (version_dir / "python_programs" / "add.py").is_file()
    assert (version_dir / "conftest.py").is_file()
    assert (version_dir / "python_testcases" / "node.py").is_file()
    assert (version_dir / ce.TEST_FILENAME).read_text(encoding="utf-8") == _OK_TEST
    assert len(pythonpath) == 2


def test_run_collect_replay_detects_import_error(tmp_path: Path) -> None:
    material = ce.classify_material(_synthetic_row(), roots=[])
    version_dir = tmp_path / "v"
    pythonpath = ce.materialize_exec_tree(
        material,
        version_dir,
        "from definitely_missing_module import x\n\n\ndef test_x():\n    assert x\n",
    )
    result = ce.run_collect_replay(version_dir, pythonpath=pythonpath, timeout_s=30.0)
    assert result["ok"] is False
    assert result["reason"] == "import_error"
    assert result["timed_out"] is False


def test_run_collect_replay_success(tmp_path: Path) -> None:
    material = ce.classify_material(_synthetic_row(), roots=[])
    version_dir = tmp_path / "v"
    pythonpath = ce.materialize_exec_tree(material, version_dir, _synthetic_row()["generated_test"])
    result = ce.run_collect_replay(version_dir, pythonpath=pythonpath, timeout_s=30.0)
    assert result["ok"] is True
    assert result["n_collected"] >= 1
    assert result["parser"] == "collect_only_q"


def test_sanitize_collect_detail_removes_volatile_noise(tmp_path: Path) -> None:
    """pytest 摘要耗时/临时目录路径必须规范化（否则 --repeat digest 抖动）。"""
    version_dir = tmp_path / "tmpabc"
    raw_a = f"pytest rc=2: ERROR {version_dir}/test_generated.py no tests collected, 1 error in 0.23s"
    raw_b = f"pytest rc=2: ERROR {version_dir}/test_generated.py no tests collected, 1 error in 0.97s"
    clean_a = ce.sanitize_collect_detail(raw_a, version_dir)
    clean_b = ce.sanitize_collect_detail(raw_b, version_dir)
    assert clean_a == clean_b
    assert "0.23" not in clean_a and "0.97" not in clean_b
    assert str(version_dir) not in clean_a
    assert "<TMPDIR>" in clean_a and "<DURATION>" in clean_a


# ─── 聚合分母纪律 ──────────────────────────────────────────────────────────
def test_aggregate_rows_denominator_discipline() -> None:
    rows = [
        _fake_row(),  # compile ok + exec ok
        _fake_row(exec_ok=False, exec_reason="import_error"),  # compile ok + exec 失败
        _fake_row(compile_ok=False),  # 编译失败 → 进 exec 分母、计失败
        _fake_row(empty=True),  # 空产物 → 不进 compile/exec 分母
        _fake_row(material_ok=False),  # 材料不完整 → 不进 exec 分母
        _fake_row(exec_ok=None, exec_reason="collect_timeout", timed_out=True),  # 超时单列
    ]
    agg = ce.aggregate_rows(rows)
    assert agg["n_rows"] == 6
    assert agg["n_empty_generated_test"] == 1
    assert agg["n_compile_denominator"] == 5
    assert agg["n_compile_ok"] == 4
    assert agg["compile_rate"] == round(4 / 5, 6)
    assert agg["n_material_incomplete"] == 1
    assert agg["n_exec_attempted"] == 3  # 编译成功且材料完整：ok / import 失败 / 超时
    assert agg["n_exec_ok"] == 1
    assert agg["n_collect_timeout"] == 1
    assert agg["n_exec_denominator_excl_timeout"] == 2
    assert agg["exec_rate"] == round(1 / 3, 6)
    assert agg["exec_rate_excl_timeout"] == round(1 / 2, 6)
    assert agg["reason_counts"]["empty_generated_test"] == 1
    assert agg["reason_counts"]["material_incomplete"] == 1
    assert agg["reason_counts"]["compile_syntax_error"] == 1
    assert agg["reason_counts"]["import_error"] == 1
    assert agg["reason_counts"]["collect_timeout"] == 1


def test_aggregate_rows_driver_task_sensitivity() -> None:
    """QuixBugs *_test 驱动任务敏感性口径：排除后分母/比率重算。"""
    rows = [
        {**_fake_row(), "task_id": "quixbugs__gcd"},
        {**_fake_row(), "task_id": "quixbugs__gcd_test"},
        {**_fake_row(exec_ok=False, exec_reason="import_error"), "task_id": "quixbugs__foo_test"},
    ]
    agg = ce.aggregate_rows(rows)
    assert agg["n_driver_task_rows"] == 2
    # 主口径：3 行编译成功且材料完整 → exec attempted=3（1 驱动行 import 失败）→ 2/3
    assert agg["n_exec_attempted"] == 3 and agg["n_exec_ok"] == 2
    # 排除驱动任务后：1 行 → 1/1（敏感性口径不与主口径混用分母）
    assert agg["n_compile_denominator_excl_driver_tasks"] == 1
    assert agg["n_exec_attempted_excl_driver_tasks"] == 1
    assert agg["exec_rate_excl_driver_tasks"] == 1.0
    assert agg["compile_rate_excl_driver_tasks"] == 1.0


def test_aggregate_rows_zero_denominators_are_none() -> None:
    agg = ce.aggregate_rows([_fake_row(empty=True), _fake_row(empty=True)])
    assert agg["n_compile_denominator"] == 0
    assert agg["compile_rate"] is None
    assert agg["exec_rate"] is None
    assert agg["exec_rate_excl_timeout"] is None


def test_aggregate_rows_no_test_defs_counts() -> None:
    agg = ce.aggregate_rows([_fake_row(n_test_defs=0), _fake_row()])
    assert agg["n_no_test_defs"] == 1
    assert agg["n_compile_ok"] == 2


# ─── 报告 / 合并 / 确定性 ──────────────────────────────────────────────────
def test_pooled_recomputes_rates_from_counts_not_average() -> None:
    batch_results = [
        {
            "label": "b1",
            "round": "r",
            "arms": [
                {
                    "arm": "a",
                    "rows": [_fake_row(), _fake_row()],  # 2/2 ok
                }
            ],
        },
        {
            "label": "b2",
            "round": "r",
            "arms": [
                {
                    "arm": "a",
                    "rows": [_fake_row(exec_ok=False, exec_reason="import_error")] * 2,  # 0/2 ok
                }
            ],
        },
    ]
    pooled = ce._build_pooled(batch_results)
    assert len(pooled) == 1
    agg = pooled[0]["aggregate"]
    assert pooled[0]["n_batches"] == 2
    assert agg["n_exec_ok"] == 2 and agg["n_exec_attempted"] == 4
    assert agg["exec_rate"] == 0.5  # 按计数 2/4；若按比率平均会是 0.5 巧合，故再验 compile
    assert agg["compile_rate"] == 1.0


def test_report_fields_and_digest_volatile_insensitive() -> None:
    report = ce.build_report(
        inputs=[{"path": "a.json", "sha256": "a" * 64, "batch": "b", "round": "r", "arms": ["x"]}],
        batch_results=[
            {
                "label": "b",
                "round": "r",
                "artifact": "a.json",
                "sha256": "a" * 64,
                "arms": [
                    {"arm": "x", "aggregate": ce.aggregate_rows([_fake_row()]), "rows": [], "timing": {"wall_s": 1.0}}
                ],
                "timing": {"wall_s": 2.0},
            }
        ],
        pooled=[],
        config={"jobs": 1},
        command=["python", "-m", "x"],
    )
    assert report["schema_version"] == ce.SCHEMA_VERSION
    assert report["metric_definition"]["compile_rate"]
    assert report["metric_definition"]["testagent_comparability"]
    assert report["inputs"][0]["sha256"] == "a" * 64
    assert report["limitations"]
    from experiments.misguided_metrics import body_digest

    body_a = {"x": 1, "timing": {"wall_s": 1.0}}
    body_b = {"x": 1, "timing": {"wall_s": 99.0}}
    assert body_digest(body_a) == body_digest(body_b)
    assert body_digest(body_a) != body_digest({"x": 2})


def test_default_batches_cover_required_rounds() -> None:
    specs = ce.default_batches()
    rounds = {spec.round for spec in specs}
    labels = {spec.label for spec in specs}
    assert "emse_docstring_anchor_20261017" in rounds
    assert "emse_df_spec_20261016" in rounds
    assert "main_batch" in rounds
    assert {"main_batch_seed42", "main_batch_seed43", "main_batch_seed44"} <= labels
    assert len(specs) == 8


def test_parse_batch_arg_and_resolve_fail_closed(tmp_path: Path) -> None:
    spec = ce._parse_batch_arg("lbl=/tmp/x.json,rnd")
    assert (spec.label, spec.round, spec.path) == ("lbl", "rnd", Path("/tmp/x.json"))
    spec2 = ce._parse_batch_arg("lbl=/tmp/x.json")
    assert spec2.round == "lbl"
    with pytest.raises(ce.CompileExecError, match="LABEL=PATH"):
        ce._parse_batch_arg("/tmp/x.json")
    args = ce._build_arg_parser().parse_args(["--batch", "b=/no/such/file.json", "--out", str(tmp_path)])
    with pytest.raises(ce.CompileExecError, match="批次工件不存在"):
        ce._resolve_batches(args)


def test_main_fail_closed_on_missing_batch(tmp_path: Path) -> None:
    code = ce.main(["--batch", "b=/no/such/file.json", "--out", str(tmp_path / "out")])
    assert code == 2
    assert not (tmp_path / "out" / "COMPILE_EXEC_REPORT.json").exists()


# ─── 微型端到端（真实 pytest 子进程 + CLI 落盘） ───────────────────────────
def test_main_end_to_end_tiny_fixture(tmp_path: Path) -> None:
    root = _make_qxb_root(tmp_path)
    artifact = _write_artifact(
        tmp_path / "bench.json",
        {
            "plain_llm_df": [
                _quixbugs_row(_OK_TEST, "quixbugs__add"),
                _quixbugs_row("def test_bad(:\n    pass\n", "quixbugs__add"),
                {
                    "task_id": "quixbugs__add2",
                    "generated_test": _OK_TEST,
                    "task_metadata": {
                        "source": "quixbugs",
                        "program": "add2",
                        "fixed": "",
                        "suggested_function": "add2",
                        "is_cross_file": False,
                    },
                },
            ]
        },
    )
    out = tmp_path / "out"
    code = ce.main(
        [
            "--batch",
            f"tiny={artifact},tiny_round",
            "--quixbugs-root",
            str(root),
            "--out",
            str(out),
            "--jobs",
            "1",
            "--collect-timeout",
            "30",
            "--quiet",
        ]
    )
    assert code == 0
    payload = json.loads((out / "COMPILE_EXEC_REPORT.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == ce.SCHEMA_VERSION
    assert payload["run_meta"]["body_digest"]
    batch = payload["report"]["batches"][0]
    assert batch["label"] == "tiny" and batch["round"] == "tiny_round"
    agg = batch["arms"][0]["aggregate"]
    # 3 行：①可执行成功 ②编译语法错误 ③程序 add2 无源码/无 fixed → 材料不完整
    assert agg["n_rows"] == 3
    assert agg["n_compile_ok"] == 2 and agg["n_compile_denominator"] == 3
    assert agg["n_exec_attempted"] == 1 and agg["n_exec_ok"] == 1
    assert agg["reason_counts"]["compile_syntax_error"] == 1
    assert agg["reason_counts"]["material_incomplete"] == 1
    assert (out / "COMPILE_EXEC_REPORT.md").exists()
    md = (out / "COMPILE_EXEC_REPORT.md").read_text(encoding="utf-8")
    assert "compile_rate" in md and "exec_rate" in md and "TestAgent" in md
