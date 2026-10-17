"""misguided/effective 逐测试度量工具契约测试（零 LLM / 零网络 / 确定性）。

锁定 experiments/misguided_metrics.py 的核心口径：
- 四分类矩阵（effective / misguided / both_pass / both_fail）与不可分类原因单列；
- 分母纪律（可分类 = 两侧均有 pass/fail；timeout/collect/skip 等不进分母）；
- JUnit XML 与 ``-v`` 两路解析、集合失败/导入失败归因；
- 缺陷版源码解析优先级与"与工件任务一致"的 fail-closed 校验；
- 双布局物化（平铺 + python_programs 包结构，生产/官方 import 均可解析）；
- 嵌套 pytest 环境（nested_pytest_env 剔除宿主 PYTEST_PLUGINS，H2 教训）；
- artifact 解析、臂选择、报告字段（输入 sha256/命令/分母披露/确定性声明）；
- body digest 对易变字段（时间戳/墙钟）不敏感、对计数敏感（确定性口径）。

测试全部使用 tmp_path 微型 fixture（小模块 + 已知行为测试），不依赖真实
QuixBugs 数据集/网络/LLM；必要的真实 pytest 子进程为本地执行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.misguided_metrics as metrics

# ─── 微型 fixture 工具 ─────────────────────────────────────────────────────
_BUGGY_ADD = "def add(a, b):\n    return a - b\n"
_FIXED_ADD = "def add(a, b):\n    return a + b\n"


def _make_qxb_root(tmp_path: Path) -> Path:
    """构造最小 QuixBugs 口径数据根（python_programs + correct_python_programs）。"""
    root = tmp_path / "qxb"
    (root / "python_programs").mkdir(parents=True)
    (root / "correct_python_programs").mkdir(parents=True)
    (root / "python_programs" / "add.py").write_text(_BUGGY_ADD, encoding="utf-8")
    (root / "correct_python_programs" / "add.py").write_text(_FIXED_ADD, encoding="utf-8")
    return root


def _task_row(
    program: str,
    generated_test: str,
    fixed_code: str,
    *,
    task_id: str | None = None,
    detection: float | None = None,
    verdict: str | None = None,
    passed: bool | None = False,
    suggested: str | None = None,
) -> dict:
    """构造一条最小归档任务行（仅含本工具消费的字段）。"""
    return {
        "task_id": task_id or f"quixbugs__{program}",
        "generated_test": generated_test,
        "task_metadata": {
            "source": "quixbugs",
            "program": program,
            "test_cases": "",
            "fixed": fixed_code,
            "suggested_function": suggested or program,
            "is_cross_file": False,
        },
        "specificity_gate_verdict": verdict,
        "detection_rate": detection,
        "passed": passed,
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


def _materialize_version_dir(tmp_path: Path, generated_test: str, *, program: str = "add") -> Path:
    """物化一个最小版本目录（被测模块 = 正确实现，供 run_side 契约测试用）。"""
    version_dir = tmp_path / "version"
    metrics.materialize_version(
        version_dir,
        program,
        _FIXED_ADD,
        generated_test,
        {"node.py": "class Node:\n    pass\n"},
    )
    return version_dir


def _side(**overrides) -> dict:
    """构造 run_side 形态的侧结果 dict（replay_detection 等纯函数测试用）。"""
    base = {
        "ok": True,
        "collect_ok": True,
        "collect_reason": None,
        "collect_rc": 0,
        "collect_timed_out": False,
        "collected": ["test_generated.py::test_x"],
        "n_collected": 1,
        "exec_ok": True,
        "exec_rc": 0,
        "exec_timed_out": False,
        "exec_error": False,
        "outcomes": {"test_generated.py::test_x": "pass"},
        "n_outcomes": 1,
        "missing_reason": None,
    }
    base.update(overrides)
    return base


def _fake_task(**overrides) -> dict:
    """构造聚合测试用任务记录。"""
    base = {
        "task_id": "quixbugs__p",
        "status": "ok",
        "analysis_set": "defect_program",
        "defect_signal": True,
        "n_ast_test_defs": 4,
        "n_collected": 4,
        "n_classifiable": 4,
        "counts": {"effective": 1, "misguided": 1, "both_pass": 1, "both_fail": 1},
        "unclassifiable": dict.fromkeys(metrics.UNCLASSIFIABLE_REASONS, 0),
    }
    base.update(overrides)
    return base


# ─── 四分类与分母 ──────────────────────────────────────────────────────────
class TestClassifyOutcomes:
    def test_four_class_matrix(self):
        nodes = ["t::eff", "t::mis", "t::bp", "t::bf"]
        buggy = {"t::eff": "fail", "t::mis": "pass", "t::bp": "pass", "t::bf": "fail"}
        fixed = {"t::eff": "pass", "t::mis": "fail", "t::bp": "pass", "t::bf": "fail"}
        rows, counts, unclassifiable = metrics.classify_outcomes(nodes, buggy, fixed)
        assert counts == {"effective": 1, "misguided": 1, "both_pass": 1, "both_fail": 1}
        assert sum(unclassifiable.values()) == 0
        assert [row["cls"] for row in rows] == ["both_fail", "both_pass", "effective", "misguided"]

    def test_timeout_reason_single_listed(self):
        _, counts, unclassifiable = metrics.classify_outcomes(
            ["t::a", "t::b"],
            {"t::a": "fail", "t::b": "timeout"},
            {"t::a": "pass", "t::b": "fail"},
        )
        assert counts["effective"] == 1
        assert unclassifiable["timeout"] == 1
        assert sum(counts.values()) == 1

    def test_skipped_reason_single_listed(self):
        _, counts, unclassifiable = metrics.classify_outcomes(["t::a"], {"t::a": "pass"}, {"t::a": "skip"})
        assert sum(counts.values()) == 0
        assert unclassifiable["skipped"] == 1

    def test_test_error_reason_single_listed(self):
        _, _, unclassifiable = metrics.classify_outcomes(["t::a"], {"t::a": "error"}, {"t::a": "pass"})
        assert unclassifiable["test_error"] == 1

    def test_missing_side_uses_side_reason(self):
        rows, counts, unclassifiable = metrics.classify_outcomes(
            ["t::a"],
            {"t::a": "pass"},
            {},
            fixed_missing_reason="timeout",
        )
        assert rows[0]["reason"] == "timeout"
        assert rows[0]["fixed"] == "unavailable"
        assert counts["both_pass"] == 0
        assert unclassifiable["timeout"] == 1

    def test_both_missing_is_unknown(self):
        rows, _, unclassifiable = metrics.classify_outcomes(["t::a"], {}, {})
        assert rows[0]["reason"] == "unknown"
        assert unclassifiable["unknown"] == 1

    def test_denominator_invariant(self):
        nodes = [f"t::n{i}" for i in range(7)]
        buggy = {"t::n0": "fail", "t::n1": "pass", "t::n2": "timeout", "t::n3": "skip"}
        fixed = {"t::n0": "pass", "t::n1": "fail", "t::n2": "pass", "t::n4": "pass"}
        rows, counts, unclassifiable = metrics.classify_outcomes(
            nodes, buggy, fixed, buggy_missing_reason="timeout", fixed_missing_reason="timeout"
        )
        # 行数 = 并集；可分类 + 不可分类 = 全部行（无静默丢弃）
        assert len(rows) == 7
        assert sum(counts.values()) + sum(unclassifiable.values()) == len(rows)
        assert sum(counts.values()) == 2  # effective(n0) + misguided(n1)

    def test_rows_sorted_deterministically(self):
        rows, _, _ = metrics.classify_outcomes(["t::z", "t::a", "t::m"], {"t::a": "pass"}, {"t::a": "pass"})
        assert [r["node"] for r in rows] == ["t::a", "t::m", "t::z"]


# ─── JUnit / verbose 解析 ─────────────────────────────────────────────────
_JUNIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="2" skipped="1" tests="5">
  <testcase classname="test_generated" name="test_ok" time="0.001" />
  <testcase classname="test_generated" name="test_fail" time="0.001">
    <failure message="assert 1 == 2">trace</failure>
  </testcase>
  <testcase classname="test_generated" name="test_hang" time="2.000">
    <failure message="Failed: Timeout (&gt;1.0s) from pytest-timeout.">trace</failure>
  </testcase>
  <testcase classname="test_generated" name="test_skip" time="0.000">
    <skipped type="pytest.skip" message="nope">skip</skipped>
  </testcase>
  <testcase classname="test_generated.TestK" name="test_err" time="0.001">
    <error message="boom">teardown error</error>
  </testcase>
</testsuite></testsuites>
"""


class TestParsers:
    def test_parse_junit_all_statuses(self, tmp_path: Path):
        xml = tmp_path / "junit.xml"
        xml.write_text(_JUNIT_XML, encoding="utf-8")
        parsed = metrics.parse_junit_xml(xml)
        assert parsed["parse_error"] is None
        assert parsed["n_testcases"] == 5
        assert parsed["outcomes"]["test_generated.py::test_ok"] == "pass"
        assert parsed["outcomes"]["test_generated.py::test_fail"] == "fail"
        assert parsed["outcomes"]["test_generated.py::test_hang"] == "timeout"
        assert parsed["outcomes"]["test_generated.py::test_skip"] == "skip"
        assert parsed["outcomes"]["test_generated.py::TestK::test_err"] == "error"

    def test_parse_junit_collection_failure(self, tmp_path: Path):
        xml = tmp_path / "junit.xml"
        xml.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" tests="1">
  <testcase classname="" name="test_generated" time="0.001">
    <error message="collection failure">ModuleNotFoundError: No module named 'nope'</error>
  </testcase>
</testsuite></testsuites>
""",
            encoding="utf-8",
        )
        parsed = metrics.parse_junit_xml(xml)
        assert parsed["outcomes"] == {}
        assert len(parsed["collection_failures"]) == 1
        assert parsed["collection_failures"][0]["name"] == "test_generated"

    def test_parse_junit_missing_file(self, tmp_path: Path):
        parsed = metrics.parse_junit_xml(tmp_path / "absent.xml")
        assert parsed["outcomes"] == {}
        assert parsed["parse_error"]

    def test_junit_node_key_class_and_param(self):
        assert metrics._junit_node_key("test_generated", "test_a") == "test_generated.py::test_a"
        assert metrics._junit_node_key("test_generated.TestK", "test_b[1-2]") == "test_generated.py::TestK::test_b[1-2]"
        assert metrics._junit_node_key("", "test_x") is None

    def test_parse_verbose_outcomes(self):
        out = "test_generated.py::test_ok PASSED [ 50%]\ntest_generated.py::TestK::test_bad FAILED [100%]\nnoise line\n"
        parsed = metrics.parse_verbose_outcomes(out)
        assert parsed == {
            "test_generated.py::test_ok": "pass",
            "test_generated.py::TestK::test_bad": "fail",
        }

    def test_normalize_node_list_filters_summary(self):
        out = "test_generated.py::test_a\ntest_generated.py::test_b[1]\n\n7 tests collected in 0.10s\n"
        assert metrics._normalize_node_list(out) == [
            "test_generated.py::test_a",
            "test_generated.py::test_b[1]",
        ]


# ─── 工件解析与选择 ───────────────────────────────────────────────────────
class TestArtifactIO:
    def test_load_and_select(self, tmp_path: Path):
        artifact = _write_artifact(tmp_path / "a.json", {"arm_x": [{"task_id": "t1"}]})
        data = metrics.load_artifact(artifact)
        assert metrics.list_artifact_arms(data) == ["arm_x"]
        assert metrics.select_rows(data, "arm_x")[0]["task_id"] == "t1"

    @pytest.mark.parametrize("content", ["not-json", "{}", '{"results": {}}', "[]"])
    def test_load_artifact_invalid_raises(self, tmp_path: Path, content: str):
        path = tmp_path / "bad.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(metrics.ArtifactError):
            metrics.load_artifact(path)

    def test_select_unknown_arm_raises(self, tmp_path: Path):
        data = metrics.load_artifact(_write_artifact(tmp_path / "a.json", {"arm_x": []}))
        with pytest.raises(metrics.ArtifactError):
            metrics.select_rows(data, "missing_arm")

    def test_resolve_selection_rejects_duplicate_and_unknown(self, tmp_path: Path):
        artifact = _write_artifact(tmp_path / "a.json", {"arm_x": []})
        with pytest.raises(metrics.ArtifactError):
            metrics._resolve_selection([artifact, artifact], [])
        with pytest.raises(metrics.ArtifactError):
            metrics._resolve_selection([artifact], ["nope"])

    def test_numeric_normalization(self):
        assert metrics._as_float_or_none(1.0) == 1.0
        assert metrics._as_float_or_none("0.0") == 0.0
        assert metrics._as_float_or_none(None) is None
        assert metrics._as_float_or_none("None") is None
        assert metrics._as_bool_or_none(False) is False
        assert metrics._as_bool_or_none("True") is True
        assert metrics._as_bool_or_none(None) is None


# ─── 缺陷版源码解析与校验 ─────────────────────────────────────────────────
class TestSourceResolution:
    def test_resolve_priority_first_root_wins(self, tmp_path: Path):
        r1 = tmp_path / "r1"
        r2 = tmp_path / "r2"
        for root, body in ((r1, "def add(a, b):\n    return 1\n"), (r2, "def add(a, b):\n    return 2\n")):
            (root / "python_programs").mkdir(parents=True)
            (root / "python_programs" / "add.py").write_text(body, encoding="utf-8")
        code, path = metrics.resolve_buggy_source("add", [r1, r2])
        assert "return 1" in code
        assert path == r1 / "python_programs" / "add.py"

    def test_resolve_missing_lists_checked_paths(self, tmp_path: Path):
        with pytest.raises(metrics.MaterialError) as err:
            metrics.resolve_buggy_source("ghost", [tmp_path])
        assert err.value.reason == "missing_buggy_source"
        assert "python_programs/ghost.py" in err.value.detail

    def test_validate_ok_flags(self):
        flags = metrics.validate_buggy_source(
            _BUGGY_ADD,
            "add",
            {"fixed": _FIXED_ADD, "suggested_function": "add"},
            _FIXED_ADD,
        )
        assert flags["suggested_function_found"] is True
        assert flags["fixed_material_matches_dataset"] is True

    def test_validate_suggested_function_mismatch_fail_closed(self):
        with pytest.raises(metrics.MaterialError) as err:
            metrics.validate_buggy_source(
                _BUGGY_ADD, "add", {"fixed": _FIXED_ADD, "suggested_function": "mul"}, _FIXED_ADD
            )
        assert err.value.reason == "buggy_source_validation_failed"
        assert "suggested_function" in err.value.detail

    def test_validate_fixed_material_mismatch_fail_closed(self):
        with pytest.raises(metrics.MaterialError) as err:
            metrics.validate_buggy_source(
                _BUGGY_ADD, "add", {"fixed": "def add(a, b):\n    return a * b\n"}, _FIXED_ADD
            )
        assert err.value.reason == "buggy_source_validation_failed"

    def test_validate_unparseable_buggy(self):
        with pytest.raises(metrics.MaterialError) as err:
            metrics.validate_buggy_source("def broken(:\n", "add", {}, None)
        assert err.value.reason == "buggy_source_unparseable"

    def test_dataset_fixed_source(self, tmp_path: Path):
        root = _make_qxb_root(tmp_path)
        assert metrics.dataset_fixed_source("add", [root]) == _FIXED_ADD
        assert metrics.dataset_fixed_source("ghost", [root]) is None

    def test_collect_siblings_excludes_target(self, tmp_path: Path):
        buggy = tmp_path / "python_programs"
        buggy.mkdir()
        (buggy / "add.py").write_text(_BUGGY_ADD, encoding="utf-8")
        (buggy / "node.py").write_text("class Node:\n    pass\n", encoding="utf-8")
        siblings = metrics.collect_siblings(buggy / "add.py")
        assert "node.py" in siblings
        assert "add.py" not in siblings


# ─── 物化 ────────────────────────────────────────────────────────────────
class TestMaterialize:
    def test_dual_layout_contents(self, tmp_path: Path):
        version_dir = _materialize_version_dir(tmp_path, "def test_x():\n    assert True\n")
        # 平铺口径（生产执行沙箱）
        assert (version_dir / "add.py").read_text(encoding="utf-8") == _FIXED_ADD
        # 包结构口径（QuixBugs 官方 import）
        pkg = version_dir / "python_programs"
        assert (pkg / "__init__.py").is_file()
        assert (pkg / "add.py").read_text(encoding="utf-8") == _FIXED_ADD
        # 依赖与生成测试原文
        assert (version_dir / "node.py").is_file()
        assert (version_dir / "test_generated.py").read_text(encoding="utf-8").startswith("def test_x")
        assert "pytest.use_correct" in (version_dir / "conftest.py").read_text(encoding="utf-8")


# ─── pytest 子进程执行 ────────────────────────────────────────────────────
class TestRunSide:
    def test_basic_execution(self, tmp_path: Path):
        tests = "def test_ok():\n    assert True\n\ndef test_bad():\n    assert False\n"
        side = metrics.run_side(
            version_dir=_materialize_version_dir(tmp_path, tests),
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
        )
        assert side["ok"] is True
        assert side["collect_ok"] is True
        assert side["n_collected"] == 2
        assert side["outcomes"] == {
            "test_generated.py::test_ok": "pass",
            "test_generated.py::test_bad": "fail",
        }
        assert side["exec_rc"] == 1
        assert side["exec_error"] is False
        assert side["parser"] in {"junit", "junit+verbose"}

    def test_import_error_attributed(self, tmp_path: Path):
        tests = "from nope import thing\n\ndef test_x():\n    assert True\n"
        side = metrics.run_side(
            version_dir=_materialize_version_dir(tmp_path, tests),
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
        )
        assert side["ok"] is False
        assert side["collect_ok"] is False
        assert side["collect_reason"] == "import_error"
        assert "No module named 'nope'" in side["detail"]

    def test_per_test_timeout_classified(self, tmp_path: Path):
        tests = "import time\n\ndef test_hang():\n    time.sleep(10)\n\ndef test_ok():\n    assert True\n"
        side = metrics.run_side(
            version_dir=_materialize_version_dir(tmp_path, tests),
            pytest_timeout_s=1.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
        )
        assert side["ok"] is True
        assert side["outcomes"]["test_generated.py::test_hang"] == "timeout"
        assert side["outcomes"]["test_generated.py::test_ok"] == "pass"

    def test_uses_nested_pytest_env_and_strips_host_pytest(self, tmp_path: Path, monkeypatch):
        # H2 教训：宿主 PYTEST_PLUGINS 若被继承，嵌套 pytest 会在收集前 ImportError。
        monkeypatch.setenv("PYTEST_PLUGINS", "definitely_missing_plugin_xyz")
        calls: list[dict] = []
        real_nested = metrics.nested_pytest_env

        def spy(**overrides):
            env = real_nested(**overrides)
            calls.append(env)
            return env

        monkeypatch.setattr(metrics, "nested_pytest_env", spy)
        side = metrics.run_side(
            version_dir=_materialize_version_dir(tmp_path, "def test_ok():\n    assert True\n"),
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
        )
        assert side["ok"] is True
        assert calls, "run_side 必须经 nested_pytest_env 构造子进程环境"
        assert "PYTEST_PLUGINS" not in calls[0]
        assert calls[0]["PYTHONHASHSEED"] == "0"
        assert side["collect_timed_out"] is False


# ─── 任务级复算 / 交叉校验纯函数 ──────────────────────────────────────────
class TestReplayDetection:
    @pytest.mark.parametrize(
        ("buggy_rc", "fixed_rc", "expected"),
        [(1, 0, 1.0), (0, 0, 0.0), (1, 1, 0.0), (2, 0, 0.0)],
    )
    def test_rc_rules(self, buggy_rc, fixed_rc, expected):
        buggy = _side(exec_rc=buggy_rc, exec_error=buggy_rc >= 2)
        fixed = _side(exec_rc=fixed_rc)
        assert metrics.replay_detection(buggy, fixed) == expected

    def test_none_when_collect_failed_or_timed_out(self):
        assert metrics.replay_detection(_side(collect_ok=False), _side()) is None
        assert metrics.replay_detection(_side(exec_timed_out=True), _side()) is None

    def test_strict_returns_none_on_per_test_timeout(self):
        buggy = _side(exec_rc=1, outcomes={"test_generated.py::test_x": "timeout"})
        fixed = _side()
        assert metrics.replay_detection(buggy, fixed) == 1.0
        assert metrics.replay_detection(buggy, fixed, strict=True) is None

    @pytest.mark.parametrize(
        ("a", "r", "tag"),
        [
            (1.0, 1.0, "match"),
            (0.0, 0.0, "match"),
            (None, None, "both_none"),
            (1.0, 0.0, "mismatch"),
            (None, 1.0, "artifact_none"),
            (1.0, None, "replay_none"),
        ],
    )
    def test_agreement_tags(self, a, r, tag):
        assert metrics._detection_agreement(a, r) == tag


class TestVerdictAgreement:
    @pytest.mark.parametrize(
        ("verdict", "fixed_rc", "tag"),
        [
            ("specific_red", 0, "match"),
            ("specific_red", 1, "mismatch"),
            ("over_red", 1, "match"),
            ("over_red", 0, "mismatch"),
            ("unavailable", 1, "not_applicable"),
            (None, 0, "not_applicable"),
        ],
    )
    def test_verdict_vs_fixed_side(self, verdict, fixed_rc, tag):
        fixed = _side(exec_rc=fixed_rc)
        assert metrics._verdict_agreement(verdict, fixed)[0] == tag


class TestAggregation:
    def test_aggregate_subset_rates_and_task_level(self):
        tasks = [
            _fake_task(),
            _fake_task(
                task_id="quixbugs__q",
                n_classifiable=2,
                counts={"effective": 0, "misguided": 0, "both_pass": 2, "both_fail": 0},
                unclassifiable={**dict.fromkeys(metrics.UNCLASSIFIABLE_REASONS, 0), "timeout": 3},
            ),
            _fake_task(
                task_id="quixbugs__driver_test",
                analysis_set="driver_or_unknown",
                status="structural_skip",
                n_classifiable=0,
                counts={"effective": 0, "misguided": 0, "both_pass": 0, "both_fail": 0},
            ),
        ]
        agg_all = metrics._aggregate_subset(tasks)
        assert agg_all["n_tasks"] == 3
        assert agg_all["n_tasks_ok"] == 2
        assert agg_all["n_tests_classifiable"] == 6
        assert agg_all["counts"] == {"effective": 1, "misguided": 1, "both_pass": 3, "both_fail": 1}
        assert agg_all["rates"]["misguided_share"] == round(1 / 6, 6)
        assert agg_all["unclassifiable_counts"]["timeout"] == 3
        assert agg_all["task_level"]["n_tasks_with_misguided"] == 1
        assert agg_all["task_level"]["n_tasks_with_effective"] == 1

    def test_aggregate_tasks_splits_defect_programs(self):
        tasks = [_fake_task(), _fake_task(task_id="quixbugs__z_test", analysis_set="driver_or_unknown")]
        agg = metrics.aggregate_tasks(tasks)
        assert agg["all_tasks"]["n_tasks"] == 2
        assert agg["defect_programs"]["n_tasks"] == 1
        assert agg["defect_programs_41_convention"]["n_tasks"] == 1
        assert agg["defect_programs"]["n_tests_classifiable"] == 4

    def test_aggregate_excludes_no_defect_signal_from_primary(self):
        # 41 口径包含无缺陷信号任务（如 node：buggy==fixed），主分析集必须剔除
        tasks = [
            _fake_task(task_id="quixbugs__p"),
            _fake_task(
                task_id="quixbugs__node",
                defect_signal=False,
                counts={"effective": 0, "misguided": 0, "both_pass": 10, "both_fail": 7},
                n_classifiable=17,
                n_collected=17,
            ),
        ]
        agg = metrics.aggregate_tasks(tasks)
        assert agg["defect_programs_41_convention"]["n_tasks"] == 2
        assert agg["defect_programs"]["n_tasks"] == 1
        assert agg["defect_programs"]["n_tests_classifiable"] == 4
        assert agg["all_tasks"]["counts"]["both_pass"] == 11

    def test_cross_check_collects_disagreements(self):
        tasks = [
            _fake_task(
                task_id="t1",
                detection_agreement="mismatch",
                artifact_detection_rate=1.0,
                replay_detection=0.0,
                artifact_verdict="over_red",
                verdict_agreement="match",
                artifact_passed=False,
                replay_fixed_green=False,
            ),
            _fake_task(
                task_id="t2",
                detection_agreement="match",
                artifact_detection_rate=0.0,
                replay_detection=0.0,
                artifact_verdict="specific_red",
                verdict_agreement="mismatch",
                artifact_passed=False,
                replay_fixed_green=False,
            ),
        ]
        cc = metrics.build_cross_check(tasks)
        assert cc["detection_agreement_counts"] == {"match": 1, "mismatch": 1}
        assert len(cc["detection_disagreements"]) == 1
        assert cc["detection_disagreements"][0]["task_id"] == "t1"
        assert cc["verdict_agreement_counts"] == {"match": 1, "mismatch": 1}
        assert len(cc["verdict_disagreements"]) == 1
        assert cc["artifact_passed_counts"] == {"false": 2}


# ─── 报告确定性 ──────────────────────────────────────────────────────────
class TestComparison:
    @staticmethod
    def _arm(label: str, rates: dict[str, float], n_classifiable: int) -> dict:
        return {
            "arm": label,
            "artifact": f"experiments/results/{label}.json",
            "artifact_sha256": "0" * 64,
            "aggregate": {
                "all_tasks": {"n_tests_classifiable": n_classifiable, "rates": rates, "task_level": {}},
                "defect_programs": {
                    "n_tests_classifiable": n_classifiable,
                    "rates": rates,
                    "task_level": {
                        "n_tasks_with_effective": 1,
                        "n_tasks_with_misguided": 1,
                        "per_task_misguided_fraction": {},
                    },
                },
                "defect_programs_41_convention": {"n_tests_classifiable": n_classifiable, "rates": rates},
            },
        }

    def test_single_arm_returns_none(self):
        rates = {"effective_share": 0.5, "misguided_share": 0.1, "both_pass_share": 0.3, "both_fail_share": 0.1}
        assert metrics.build_comparison([self._arm("a", rates, 10)]) is None

    def test_three_arms_pairwise(self):
        rates_a = {
            "effective_share": 0.5,
            "misguided_share": 0.10,
            "both_pass_share": 0.30,
            "both_fail_share": 0.10,
        }
        rates_b = {
            "effective_share": 0.4,
            "misguided_share": 0.01,
            "both_pass_share": 0.50,
            "both_fail_share": 0.09,
        }
        rates_c = {
            "effective_share": 0.2,
            "misguided_share": 0.02,
            "both_pass_share": 0.60,
            "both_fail_share": 0.18,
        }
        comparison = metrics.build_comparison(
            [self._arm("df", rates_a, 10), self._arm("doc", rates_b, 20), self._arm("union", rates_c, 30)]
        )
        assert comparison is not None
        assert [a["label"] for a in comparison["arms"]] == ["df", "doc", "union"]
        assert len(comparison["pairs"]) == 3
        pair = comparison["pairs"][0]
        assert pair["arm_a"]["label"] == "df" and pair["arm_b"]["label"] == "doc"
        assert pair["per_test_defect_programs"]["misguided"]["delta_pp_b_minus_a"] == pytest.approx(-9.0)
        assert pair["per_test_defect_programs"]["effective"]["delta_pp_b_minus_a"] == pytest.approx(-10.0)
        third = comparison["pairs"][2]
        assert third["arm_a"]["label"] == "doc" and third["arm_b"]["label"] == "union"
        assert third["per_test_all_tasks"]["n_tests_classifiable"] == {"arm_a": 20, "arm_b": 30}


class TestReportDeterminism:
    def test_body_digest_ignores_volatile_fields(self):
        body_a = {"arms": [{"counts": {"effective": 1}}], "config": {"jobs": 2}}
        body_b = json.loads(json.dumps(body_a))
        body_a["config"]["generated_at"] = "2026-10-17T00:00:00+00:00"
        body_a["arms"][0]["timing"] = {"wall_s": 1.0}
        body_a["config"]["started_at"] = "x"
        assert metrics.body_digest(body_a) == metrics.body_digest(body_b)

    def test_body_digest_changes_on_counts(self):
        body_a = {"arms": [{"counts": {"effective": 1}}]}
        body_b = {"arms": [{"counts": {"effective": 2}}]}
        assert metrics.body_digest(body_a) != metrics.body_digest(body_b)

    def test_strip_volatile_nested(self):
        stripped = metrics.strip_volatile(
            {"a": {"wall_s": 1, "timing": {"x": 2}, "keep": 3}, "list": [{"elapsed_s": 1, "ok": True}]}
        )
        assert stripped == {"a": {"keep": 3}, "list": [{"ok": True}]}

    def test_diff_paths_locates_count_change(self):
        diffs = metrics._diff_paths(
            {"arms": [{"counts": {"effective": 1}}]},
            {"arms": [{"counts": {"effective": 2}}]},
        )
        assert any("effective" in d for d in diffs)

    def test_determinism_meta_single(self):
        body, meta = {"x": 1}, {"body_digest": "d1"}
        out = metrics._determinism_meta([(body, meta)])
        assert out["repeat"] == 1
        assert out["deterministic"] is True

    def test_determinism_meta_detects_drift(self):
        b1, m1 = {"arms": [{"counts": {"effective": 1}}]}, {"body_digest": "d1"}
        b2, m2 = {"arms": [{"counts": {"effective": 2}}]}, {"body_digest": "d2"}
        out = metrics._determinism_meta([(b1, m1), (b2, m2)])
        assert out["deterministic"] is False
        assert out["difference_paths"]


# ─── 任务分析：结构跳过不静默 ────────────────────────────────────────────
class TestAnalyzeTaskSkips:
    def test_missing_buggy_source_is_structural_skip(self, tmp_path: Path):
        row = _task_row("add", "def test_x():\n    assert True\n", _FIXED_ADD)
        task = metrics.analyze_task(
            row,
            roots=[tmp_path],
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
            siblings_cache={},
        )
        assert task["status"] == "structural_skip"
        assert task["skip_reason"] == "missing_buggy_source"
        assert "python_programs/add.py" in task["skip_detail"]

    def test_empty_generated_test_is_structural_skip(self, tmp_path: Path):
        root = _make_qxb_root(tmp_path)
        row = _task_row("add", "   \n", _FIXED_ADD)
        task = metrics.analyze_task(
            row,
            roots=[root],
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
            siblings_cache={},
        )
        assert task["status"] == "structural_skip"
        assert task["skip_reason"] == "empty_generated_test"

    def test_structural_skip_reconciles_artifact_detection(self, tmp_path: Path):
        # 生成测试语法错误 → 结构跳过；归档 detection=0.0 时必须记 replay_none 而非 both_none
        row = _task_row("add", "def broken(:\n    pass\n", _FIXED_ADD, detection=0.0)
        task = metrics.analyze_task(
            row,
            roots=[tmp_path],
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
            siblings_cache={},
        )
        assert task["status"] == "structural_skip"
        assert task["skip_reason"] == "generated_test_syntax_error"
        assert task["detection_agreement"] == "replay_none"
        assert "generated_test_syntax_error" in task["detection_disagreement_reason"]

    def test_invalid_program_name_is_structural_skip(self, tmp_path: Path):
        root = _make_qxb_root(tmp_path)
        row = _task_row("123bad", "def test_x():\n    assert True\n", _FIXED_ADD)
        task = metrics.analyze_task(
            row,
            roots=[root],
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
            siblings_cache={},
        )
        assert task["status"] == "structural_skip"
        assert task["skip_reason"] == "invalid_program_name"


# ─── main() 端到端（微型工件；真实本地 pytest 子进程）───────────────────
_ADD_TEST = """from add import add

def test_effective():
    assert add(2, 3) == 5

def test_misguided():
    assert add(3, 2) == 1

def test_both_pass():
    assert add(0, 0) == 0

def test_both_fail():
    assert add(1, 1) == 99
"""
_MUL_BUGGY = "def mul(a, b):\n    return a\n"
_MUL_FIXED = "def mul(a, b):\n    return a * b\n"
_MUL_TEST = "from mul import mul\n\ndef test_mul():\n    assert mul(3, 4) == 12\n"


@pytest.fixture(scope="module")
def integrated(tmp_path_factory):
    """一次端到端 main()：2 个已知行为任务（四分类矩阵 + 干净检出）。"""
    tmp = tmp_path_factory.mktemp("integrated")
    root = _make_qxb_root(tmp)
    (root / "python_programs" / "mul.py").write_text(_MUL_BUGGY, encoding="utf-8")
    (root / "correct_python_programs" / "mul.py").write_text(_MUL_FIXED, encoding="utf-8")
    artifact = _write_artifact(
        tmp / "bench.json",
        {
            "plain_llm_df": [
                _task_row("add", _ADD_TEST, _FIXED_ADD, detection=0.0, verdict="over_red", passed=False),
                _task_row("mul", _MUL_TEST, _MUL_FIXED, detection=1.0, verdict="specific_red", passed=False),
            ]
        },
    )
    out = tmp / "out"
    rc = metrics.main(
        [
            "--artifact",
            str(artifact),
            "--out",
            str(out),
            "--quixbugs-root",
            str(root),
            "--jobs",
            "2",
            "--per-test-timeout",
            "5",
            "--file-timeout",
            "60",
            "--quiet",
        ]
    )
    payload = json.loads((out / "MISGUIDED_REPORT.json").read_text(encoding="utf-8"))
    return {
        "tmp": tmp,
        "root": root,
        "artifact": artifact,
        "out": out,
        "rc": rc,
        "payload": payload,
        "md": (out / "MISGUIDED_REPORT.md").read_text(encoding="utf-8"),
    }


class TestMainEndToEnd:
    def test_exit_code_and_files(self, integrated):
        assert integrated["rc"] == 0
        assert (integrated["out"] / "MISGUIDED_REPORT.json").is_file()
        assert (integrated["out"] / "MISGUIDED_REPORT.md").is_file()

    def test_report_schema_and_inputs_sha(self, integrated):
        payload = integrated["payload"]
        assert payload["schema_version"] == metrics.SCHEMA_VERSION
        report = payload["report"]
        assert set(report) >= {"tool", "metric_definition", "config", "command", "inputs", "arms", "limitations"}
        assert report["inputs"][0]["sha256"] == metrics.sha256_file(integrated["artifact"])
        assert report["command"][:3] == ["python", "-m", "experiments.misguided_metrics"]

    def test_four_way_counts_reproduced(self, integrated):
        arm = integrated["payload"]["report"]["arms"][0]
        assert arm["arm"] == "plain_llm_df"
        task_add = next(t for t in arm["tasks"] if t["task_id"] == "quixbugs__add")
        assert task_add["status"] == "ok"
        assert task_add["counts"] == {"effective": 1, "misguided": 1, "both_pass": 1, "both_fail": 1}
        assert task_add["n_classifiable"] == 4
        task_mul = next(t for t in arm["tasks"] if t["task_id"] == "quixbugs__mul")
        assert task_mul["counts"] == {"effective": 1, "misguided": 0, "both_pass": 0, "both_fail": 0}

    def test_cross_check_with_artifact_fields(self, integrated):
        arm = integrated["payload"]["report"]["arms"][0]
        assert arm["cross_check"]["detection_agreement_counts"] == {"match": 2}
        assert arm["cross_check"]["verdict_agreement_counts"] == {"match": 2}
        task_add = next(t for t in arm["tasks"] if t["task_id"] == "quixbugs__add")
        assert task_add["replay_detection"] == 0.0
        assert task_add["artifact_detection_rate"] == 0.0
        task_mul = next(t for t in arm["tasks"] if t["task_id"] == "quixbugs__mul")
        assert task_mul["replay_detection"] == 1.0

    def test_denominator_disclosure_and_determinism_meta(self, integrated):
        payload = integrated["payload"]
        agg = payload["report"]["arms"][0]["aggregate"]["all_tasks"]
        assert agg["n_tests_collected"] == 5
        assert agg["n_tests_classifiable"] == 5
        assert agg["n_tests_unclassifiable"] == 0
        meta = payload["run_meta"]
        assert meta["generated_at"]
        assert meta["determinism"]["repeat"] == 1
        assert meta["body_digest"] == metrics.body_digest(payload["report"])

    def test_markdown_sections(self, integrated):
        md = integrated["md"]
        assert "# misguided/effective" in md
        assert "## 2. 口径定义" in md
        assert "可分类测试数（分母）" in md
        assert "## 5. 与工件既有字段的交叉校验" in md
        assert "## 8. 确定性声明" in md
        assert "非" in md  # 性质声明（描述性、非预注册确认性）

    def test_rerender_markdown_from_body_is_stable(self, integrated):
        payload = integrated["payload"]
        md2 = metrics.render_markdown(payload["report"], payload["run_meta"])
        assert md2 == integrated["md"]

    def test_main_missing_artifact_returns_2(self, tmp_path: Path):
        rc = metrics.main(["--artifact", str(tmp_path / "absent.json"), "--out", str(tmp_path / "out"), "--quiet"])
        assert rc == 2
