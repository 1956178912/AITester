"""O-1 仪器加固契约测试：崩溃安全 harness + 前件校验输入选择 + replay 分类细化。

覆盖四块：
1. **崩溃安全 harness**（`src/specs/spec_ir_v2.compile_spec_oracle`）：执行体
   try/except——AssertionError 原样 re-raise（语义判定保留为 fail）、其余
   Exception → ``pytest.skip("oracle-unavailable: <ExcType>: ...")``（不静默
   pass、不伪装 fail）；BaseException（如 KeyboardInterrupt）不捕获；产物
   ast 合法且正常路径仍有 assert（防"全 skip 假安全"）。
2. **前件校验输入选择**：boundaries 候选按序用受限安全求值筛选（零 eval/exec）；
   违反前件的候选不绑定、换下一个；全不满足 → SMT 见证；仍无 → 带可审计
   ``oracle-unavailable: no-valid-input`` 的保守骨架（不产假断言）。
3. **安全求值**：`spec_smt.safe_eval_clause` 拒绝属性/下标/import/任意调用等
   逃逸面；未知名称 → 不可判定（保守拒绝候选）。
4. **replay/生产判分细化**：fp 拆出 `instrument_error` / `fp_assertion_fail`
   （旧四分类键兼容）；pytest skipped 在 M1 `oracle_suite_verdict` 记
   unavailable（不混入 fp/silent）；before/after 对照构建。

零 LLM/零网络；仅 1 例真实 pytest 子进程（本地，<1s）。
"""

from __future__ import annotations

import json
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import experiments._m1_metrics as m1
import experiments.oracle_quality_replay as oq
import src.specs.spec_ir_v2 as v2
import src.specs.spec_smt as smt

# ─── 工具 ──────────────────────────────────────────────────────────────────
_TARGET_MOD = "o1_probe_mod"


def _spec(
    *,
    pre_expr: list[str] | None = None,
    post_expr: list[str] | None = None,
    boundaries: list[dict[str, Any]] | None = None,
    function_name: str = "f",
) -> dict[str, Any]:
    spec: dict[str, Any] = {"function_name": function_name}
    if pre_expr:
        spec["preconditions_expr"] = list(pre_expr)
    if post_expr:
        spec["postconditions_expr"] = list(post_expr)
    if boundaries:
        spec["boundaries"] = list(boundaries)
    return spec


def _compile(spec: dict[str, Any], params: list[str] | None = None) -> str:
    return v2.compile_spec_oracle(
        spec,
        target_module=_TARGET_MOD,
        target_function=spec.get("function_name", "f"),
        signature_params=params,
    )


def _exec_oracle(code: str, module_attrs: dict[str, Any]) -> dict[str, Any]:
    """在受控命名空间 exec 生成的 oracle 代码（模块以 sys.modules 桩注入）。"""
    module = types.ModuleType(_TARGET_MOD)
    for name, value in module_attrs.items():
        setattr(module, name, value)
    previous = sys.modules.get(_TARGET_MOD)
    sys.modules[_TARGET_MOD] = module
    try:
        namespace: dict[str, Any] = {}
        exec(compile(code, "<o1-oracle>", "exec"), namespace)
    finally:
        if previous is None:
            sys.modules.pop(_TARGET_MOD, None)
        else:
            sys.modules[_TARGET_MOD] = previous
    return namespace


def _run_generated(code: str, module_attrs: dict[str, Any]) -> Any:
    """exec 生成的代码并调用 test_specir_v2_oracle（异常/断言透传）。"""
    namespace = _exec_oracle(code, module_attrs)
    return namespace["test_specir_v2_oracle"]()


def _fake_run_factory(*, buggy: tuple[Any, ...] | None, fixed: tuple[Any, ...] | None):
    """构造 _run_pytest_in_tmp 替身（按 target_code 区分 buggy/fixed 侧）。"""
    calls: list[dict[str, Any]] = []

    def fake(test_code: str, target_code: str, module_name: str, **kwargs: Any) -> tuple[Any, ...] | None:
        calls.append({"target_code": target_code, **kwargs})
        if "a + b + 1" in str(target_code):
            return fixed
        return buggy

    return fake, calls


def _synth_task() -> Any:
    from src.datasets.dataset_loader import BenchmarkTask

    return BenchmarkTask(
        task_id="probe__add_off_by_one",
        repo_name="synthetic/_probe",
        problem_statement="off-by-one",
        instance_code="def add(a: int, b: int) -> int:\n    return a + b\n",
        test_code="from add_off_by_one import add\n\n\ndef test_gold():\n    assert add(1, 2) == 4\n",
        expected_pass_count=1,
        total_test_count=1,
        metadata={
            "source": "synthetic",
            "test_cases": "from add_off_by_one import add\n\n\ndef test_gold():\n    assert add(1, 2) == 4\n",
            "fixed": "def add(a: int, b: int) -> int:\n    return a + b + 1\n",
            "is_cross_file": False,
        },
    )


_ORACLE_BLOCK = (
    "\n\n\n# SpecIR v2 确定性 oracle\n"
    "from add_off_by_one import add\n\n"
    "def test_specir_v2_oracle():\n"
    "    assert add(1, 2) == 4\n"
)


# ═══ 1. 崩溃安全 harness ═══════════════════════════════════════════════════
class TestCrashSafeHarness:
    def test_generated_code_contains_harness_and_asserts(self) -> None:
        code = _compile(_spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 3}]), ["x"])
        assert code
        assert "try:" in code
        assert "except AssertionError:" in code
        assert "except Exception as exc:" in code
        assert 'pytest.skip(f"oracle-unavailable:' in code
        assert "import pytest" in code
        assert any(line.strip().startswith("assert") for line in code.splitlines())
        import ast

        ast.parse(code)  # 产物必须可解析

    def test_assertion_error_propagates_as_fail(self) -> None:
        """断言失败是语义判定信号：不得被 harness 降级为 skip。"""
        code = _compile(_spec(post_expr=["result == x + 100"], boundaries=[{"input": 2}]), ["x"])
        namespace = _exec_oracle(code, {"f": lambda x: x})
        with pytest.raises(AssertionError):
            namespace["test_specir_v2_oracle"]()

    def test_crash_becomes_pytest_skip(self) -> None:
        """仪器失效（TypeError）→ pytest.skip("oracle-unavailable: ...")。"""
        code = _compile(_spec(post_expr=["result == len(items)"]), ["items"])
        namespace = _exec_oracle(code, {"f": lambda items: len(items)})
        with pytest.raises(pytest.skip.Exception, match=r"oracle-unavailable: TypeError"):
            namespace["test_specir_v2_oracle"]()

    def test_skip_message_contains_exception_type(self) -> None:
        code = _compile(_spec(post_expr=["result == len(items)"]), ["items"])
        namespace = _exec_oracle(code, {"f": lambda items: len(items)})
        with pytest.raises(pytest.skip.Exception) as exc_info:
            namespace["test_specir_v2_oracle"]()
        assert "oracle-unavailable: TypeError:" in str(exc_info.value)

    def test_base_exception_not_caught(self) -> None:
        """BaseException（如 KeyboardInterrupt）不得被异常 harness 吞掉。"""

        class _Fatal(BaseException):
            pass

        def _boom(x: Any) -> Any:
            raise _Fatal("fatal")

        code = _compile(_spec(post_expr=["result == x"]), ["x"])
        namespace = _exec_oracle(code, {"f": _boom})
        with pytest.raises(_Fatal):
            namespace["test_specir_v2_oracle"]()

    def test_skip_only_inside_except_block(self) -> None:
        """skip 不得出现在函数体顶层（否则等于全 skip 假安全）。"""
        code = _compile(_spec(post_expr=["result == x * 2"], boundaries=[{"input": 2}]), ["x"])
        except_pos = code.index("except Exception as exc:")
        skip_pos = code.index("pytest.skip(")
        assert except_pos < skip_pos
        # 函数体第一个非注释/非空语句是 try（不是 skip）
        body_lines = [line.strip() for line in code.splitlines() if line.strip()]
        def_idx = body_lines.index("def test_specir_v2_oracle():")
        assert body_lines[def_idx + 1] == "try:"

    def test_generated_code_assert_count_sample_matrix(self) -> None:
        samples = [
            _spec(post_expr=["result == x"], boundaries=[{"input": 1}]),
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 2}]),
            _spec(post_expr=["result == len(xs)"], boundaries=[{"input": [1, 2]}]),
        ]
        for spec in samples:
            params = ["xs"] if "xs" in str(spec.get("postconditions_expr")) else ["x"]
            code = _compile(spec, params)
            assert code
            import ast

            ast.parse(code)
            assert any(line.strip().startswith("assert") for line in code.splitlines())

    def test_pytest_records_skipped_in_junit(self, tmp_path: Path) -> None:
        """真实 pytest 子进程：崩溃 → junit skipped（非 failure/error）。"""
        code = _compile(_spec(post_expr=["result == len(items)"]), ["items"])
        assert code
        (tmp_path / f"{_TARGET_MOD}.py").write_text("def f(items):\n    return len(items)\n", encoding="utf-8")
        (tmp_path / "test_oracle.py").write_text(code, encoding="utf-8")
        import os
        import subprocess

        env = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}
        junit = tmp_path / "junit.xml"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_oracle.py", "-q", f"--junitxml={junit}", "-p", "no:cacheprovider"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        tree = ET.parse(str(junit))
        cases = list(tree.getroot().iter("testcase"))
        assert len(cases) == 1
        skipped = [child for child in cases[0] if child.tag == "skipped"]
        assert skipped, "崩溃安全 harness 应产出 skipped（而非 failure/error）"
        assert "oracle-unavailable: TypeError" in (skipped[0].get("message") or "")


# ═══ 2. 前件校验输入选择 ═══════════════════════════════════════════════════
class TestPreconditionAwareInputSelection:
    def test_candidate_violating_precondition_is_skipped(self) -> None:
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 0}, {"input": 5}]),
            ["x"],
        )
        assert code
        assert "x = 5" in code
        assert "x = 0" not in code

    def test_first_valid_candidate_selected(self) -> None:
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 3}, {"input": 7}]),
            ["x"],
        )
        assert "x = 3" in code

    def test_no_preconditions_keeps_first_candidate(self) -> None:
        """无可机检前件 = 空真 → 历史口径（绑第一个候选）不变。"""
        code = _compile(
            _spec(post_expr=["result == x * 2"], boundaries=[{"input": 4}, {"input": 7}]),
            ["x"],
        )
        assert "x = 4" in code

    def test_all_invalid_falls_back_to_smt_witness(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_SMT_ENABLE", "true")
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 0}, {"input": -1}]),
            ["x"],
        )
        assert code
        assert "no-valid-input" not in code
        assert "assert x > 0" in code
        assert "try:" in code
        # 见证值必须满足前件（x > 0），不能绑 0/-1
        assert "x = 0" not in code and "x = -1" not in code

    def test_all_invalid_without_smt_returns_skip_skeleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 0}, {"input": -1}]),
            ["x"],
        )
        assert "oracle-unavailable: no-valid-input" in code
        assert "instrument: no-valid-input" in code
        assert 'pytest.skip("oracle-unavailable: no-valid-input")' in code
        import ast

        ast.parse(code)
        assert not any(line.strip().startswith("assert") for line in code.splitlines())

    def test_skip_skeleton_raises_skip_not_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 0}]),
            ["x"],
        )
        namespace = _exec_oracle(code, {"f": lambda x: x * 2})
        with pytest.raises(pytest.skip.Exception, match="no-valid-input"):
            namespace["test_specir_v2_oracle"]()

    def test_arity_mismatch_candidate_skipped_then_next_used(self) -> None:
        code = _compile(
            _spec(pre_expr=["a + b > 0"], post_expr=["result == a + b"], boundaries=[{"input": 5}, {"input": [2, 3]}]),
            ["a", "b"],
        )
        assert code
        assert "args = [2, 3]" in code
        assert "args = 5" not in code

    def test_multi_param_scalar_no_smt_skip_skeleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        code = _compile(
            _spec(pre_expr=["a + b > 0"], post_expr=["result == a + b"], boundaries=[{"input": 5}]),
            ["a", "b"],
        )
        assert "oracle-unavailable: no-valid-input" in code

    def test_precondition_violating_input_not_executed(self) -> None:
        """端到端：旧口径绑 0 会触发前件断言失败；新口径选满足前件的候选并通过。"""
        code = _compile(
            _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 0}, {"input": 4}]),
            ["x"],
        )
        # 新口径必须绑定满足前件的候选 x=4（旧口径会绑首个候选 x=0 → 前件断言失败）
        assert "x = 4" in code
        assert "x = 0" not in code
        namespace = _exec_oracle(code, {"f": lambda x: x * 2})
        assert namespace["test_specir_v2_oracle"]() is None  # 不抛异常（x=4 满足前件且后件成立）

    def test_nl_precondition_kept_as_provenance_comment(self) -> None:
        # 纯 NL 通道（无 *_expr 字段）才会选 NL 通道并把不可编译前件降为注释
        spec = {
            "function_name": "f",
            "preconditions": ["输入必须为正"],
            "postconditions": ["r == x * 2"],
            "boundaries": [{"input": 3}],
        }
        code = _compile(spec, ["x"])
        assert code
        assert "# NL provenance (uncompiled pre): 输入必须为正" in code
        assert "x = 3" in code

    def test_machine_checkable_precondition_exprs_compiled_only(self) -> None:
        known = v2._known_names_for_signature(["x"])
        exprs = v2._machine_checkable_precondition_exprs(
            ["x > 0", "输入必须为正", "open('/tmp/x') > 0"], _TARGET_MOD, "f", known
        )
        assert exprs == ["x > 0"]

    def test_evaluate_precondition_exprs_conservative_none(self) -> None:
        assert v2._evaluate_precondition_exprs(["x > 0"], {"x": 1}) is True
        assert v2._evaluate_precondition_exprs(["x > 0"], {"x": 0}) is False
        # 未知名称 → 不可安全判定（None，不当 False 也不当 True）
        assert v2._evaluate_precondition_exprs(["y > 0"], {"x": 1}) is None

    def test_select_valid_boundary_candidate_rejects_unverifiable(self) -> None:
        rejected = v2._select_valid_boundary_candidate([{"input": 1}, {"input": 2}], ["y > 0"], ["x"])
        assert rejected is None  # y 不在绑定环境 → 不可证明满足 → 全部拒绝（保守）

    def test_boundary_candidate_binding_arity(self) -> None:
        assert v2._boundary_candidate_binding(["x"], 3) == {"x": 3}
        assert v2._boundary_candidate_binding(["a", "b"], [1, 2]) == {"a": 1, "b": 2}
        assert v2._boundary_candidate_binding(["a", "b"], 3) is None
        assert v2._boundary_candidate_binding([], 3) is None


# ═══ 3. 受限安全求值（零 eval/exec） ═══════════════════════════════════════
class TestSafeEval:
    def test_safe_eval_allows_whitelisted_expression(self) -> None:
        assert smt.safe_eval_clause("x > 0", {"x": 1}) is True
        assert smt.safe_eval_clause("len(xs) == 2", {"xs": [1, 2]}) is True

    @pytest.mark.parametrize(
        "clause",
        [
            "__import__('os').system('true')",
            "x.__class__",
            "x[0]",
            "open('/tmp/x','w')",
            "(lambda: 1)()",
            "[i for i in range(3)]",
        ],
    )
    def test_safe_eval_rejects_escape_surfaces(self, clause: str) -> None:
        with pytest.raises(ValueError):
            smt.safe_eval_clause(clause, {"x": 1})

    def test_safe_eval_unknown_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            smt.safe_eval_clause("y > 0", {"x": 1})


# ═══ 4. replay/生产判分分类细化 ═════════════════════════════════════════════
class TestReplayClassificationSplit:
    def test_classify_fp_kind_assertion(self) -> None:
        assert oq.classify_fp_kind({"tag": "failure", "kind": "assertion"}) == oq.FP_FLAG_ASSERTION

    def test_classify_fp_kind_instrument_error(self) -> None:
        assert oq.classify_fp_kind({"tag": "failure", "kind": "exception"}) == oq.FP_INSTRUMENT_ERROR
        assert oq.classify_fp_kind({"tag": "error", "kind": "other"}) == oq.FP_INSTRUMENT_ERROR

    def test_classify_fp_kind_unattributed(self) -> None:
        assert oq.classify_fp_kind(None) == oq.FP_UNATTRIBUTED
        assert oq.classify_fp_kind({}) == oq.FP_UNATTRIBUTED

    def test_parse_junit_failure_notes_skipped_reason(self, tmp_path: Path) -> None:
        xml = tmp_path / "junit.xml"
        xml.write_text(
            "<?xml version='1.0'?><testsuites><testsuite>"
            "<testcase classname='test_generated' name='test_specir_v2_oracle'>"
            "<skipped message='oracle-unavailable: TypeError: bad input'/></testcase>"
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        notes = oq.parse_junit_failure_notes(xml)
        note = notes["test_generated.py::test_specir_v2_oracle"]
        assert note["tag"] == "skipped"
        assert note["skip_reason"] == "oracle-unavailable: TypeError"

    def test_aggregate_oracle_fp_breakdown_and_skips(self) -> None:
        tasks = [
            {
                "oracle": {
                    "status": "ok",
                    "n_oracle_nodes": 4,
                    "counts": {"correct": 0, "fp": 2, "silent": 0, "misguided": 0},
                    "unclassifiable": {"skipped": 2},
                    "failure_stats": {"skip_reason_counts": {"oracle-unavailable: TypeError": 2}},
                    "tests": [
                        {"node": "n1", "cls": "fp", "fp_kind": oq.FP_FLAG_ASSERTION},
                        {"node": "n2", "cls": "fp", "fp_kind": oq.FP_INSTRUMENT_ERROR},
                        {"node": "n3", "cls": None, "fixed_skip_reason": "oracle-unavailable: TypeError"},
                        {"node": "n4", "cls": None, "fixed_skip_reason": "oracle-unavailable: TypeError"},
                    ],
                }
            }
        ]
        aggregate = oq.aggregate_oracle(tasks)
        assert aggregate["counts"]["fp"] == 2
        assert aggregate["counts_legacy_mapping"]["fp"] == 2
        breakdown = aggregate["counts_legacy_mapping"]["fp_breakdown"]
        assert breakdown[oq.FP_FLAG_ASSERTION] == 1
        assert breakdown[oq.FP_INSTRUMENT_ERROR] == 1
        assert aggregate["skipped_count"] == 2
        assert aggregate["skip_reason_counts"]["oracle-unavailable: TypeError"] == 2

    def test_aggregate_includes_not_run_with_classifiable_zero(self) -> None:
        """O-1：collection 到 oracle 但全不可分类的任务，skipped 不得从聚合消失。"""
        tasks = [
            {
                "oracle": {
                    "status": "not_run",
                    "skip_reason": "no_classifiable_oracle_tests",
                    "n_oracle_nodes": 1,
                    "counts": {"correct": 0, "fp": 0, "silent": 0, "misguided": 0},
                    "unclassifiable": {"skipped": 1},
                    "failure_stats": {"skip_reason_counts": {"oracle-unavailable: TypeError": 1}},
                    "tests": [
                        {"node": "n1", "cls": None, "fixed_skip_reason": "oracle-unavailable: TypeError"},
                    ],
                }
            }
        ]
        aggregate = oq.aggregate_oracle(tasks)
        assert aggregate["n_oracle_tests_classifiable"] == 0
        assert aggregate["unclassifiable_counts"] == {"skipped": 1}
        assert aggregate["skipped_count"] == 1
        assert aggregate["skip_reason_counts"]["oracle-unavailable: TypeError"] == 1

    def test_baseline_breakdown_derivation(self) -> None:
        oracle = {
            "counts": {"correct": 0, "fp": 29, "silent": 9, "misguided": 0},
            "failure_stats": {
                "fixed_side_failure_kinds": {"assertion": 2, "exception": 27},
                "fixed_side_exception_types": {"TypeError": 24, "AttributeError": 2, "ZeroDivisionError": 1},
            },
        }
        breakdown = oq._baseline_oracle_breakdown(oracle)
        assert breakdown["fp_assertion_fail"] == 2
        assert breakdown["instrument_error"] == 27
        assert breakdown["fp_unattributed"] == 0

    def test_instrument_comparison_build(self) -> None:
        arms = [
            {
                "arm": "plain_llm_df_spec",
                "subsets": {
                    "all_tasks": {
                        "oracle": {
                            "n_oracle_tests_classifiable": 11,
                            "counts": {"correct": 0, "fp": 2, "silent": 9, "misguided": 0},
                            "counts_legacy_mapping": {
                                "fp_breakdown": {oq.FP_FLAG_ASSERTION: 2, oq.FP_INSTRUMENT_ERROR: 0}
                            },
                            "unclassifiable_counts": {"skipped": 27},
                            "skip_reason_counts": {"oracle-unavailable: TypeError": 27},
                        }
                    }
                },
            }
        ]
        baseline = {
            "path": "baseline.json",
            "sha256": "a" * 64,
            "report": {
                "arms": [
                    {
                        "arm": "plain_llm_df_spec",
                        "subsets": {
                            "all_tasks": {
                                "oracle": {
                                    "n_oracle_tests_classifiable": 38,
                                    "counts": {"correct": 0, "fp": 29, "silent": 9, "misguided": 0},
                                    "unclassifiable_counts": {},
                                    "failure_stats": {
                                        "fixed_side_failure_kinds": {"assertion": 2, "exception": 27},
                                        "fixed_side_exception_types": {"TypeError": 27},
                                    },
                                }
                            }
                        },
                    }
                ]
            },
        }
        comparison = oq.build_instrument_hardening_comparison(arms, baseline)
        row = comparison["arms"][0]
        assert row["before"]["counts"]["fp"] == 29
        assert row["after"]["counts"]["fp"] == 2
        assert row["after"]["skipped_count"] == 27
        assert row["delta"]["classifiable"] == 11 - 38
        assert "仪器治疗" in comparison["honesty_note"]
        rows = oq._render_comparison_rows(comparison)
        assert any("fp_assertion_fail" in label for label, _b, _a in rows)
        assert any("skipped" in label for label, _b, _a in rows)

    def test_compare_report_fail_closed(self, tmp_path: Path) -> None:
        with pytest.raises(oq.OracleQualityError, match="对照基线报告不存在"):
            oq.load_oracle_quality_report(tmp_path / "missing.json")

    def test_main_compare_report_fail_closed_before_replay(self, tmp_path: Path) -> None:
        code = oq.main(
            [
                "--compare-report",
                str(tmp_path / "missing.json"),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        assert code == 2


# ═══ 5. 生产 M1 判分：skipped → unavailable，不混入 fp/silent ══════════════
class TestM1SkipAware:
    def test_pytest_summary_counts(self) -> None:
        counts = m1.pytest_summary_counts("2 passed, 1 skipped in 0.30s")
        assert counts["passed"] == 2 and counts["skipped"] == 1

    def test_skip_only_suite_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, calls = _fake_run_factory(buggy=(0, "1 skipped in 0.10s", ""), fixed=(0, "1 skipped in 0.10s", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = "def test_llm():\n    assert True\n" + _ORACLE_BLOCK
        assert m1._compute_oracle_suite_verdict(_synth_task(), {"generated_test": generated}) == "unavailable"
        assert len(calls) == 2

    def test_assertion_failure_still_fp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _calls = _fake_run_factory(buggy=(1, "1 failed in 0.10s", ""), fixed=(1, "1 failed in 0.10s", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = "def test_llm():\n    assert True\n" + _ORACLE_BLOCK
        assert m1._compute_oracle_suite_verdict(_synth_task(), {"generated_test": generated}) == "fp"

    def test_pass_only_suite_silent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _calls = _fake_run_factory(buggy=(0, "1 passed in 0.10s", ""), fixed=(0, "1 passed in 0.10s", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = "def test_llm():\n    assert True\n" + _ORACLE_BLOCK
        assert m1._compute_oracle_suite_verdict(_synth_task(), {"generated_test": generated}) == "silent"

    def test_partial_skip_without_failure_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _calls = _fake_run_factory(
            buggy=(0, "1 passed, 1 skipped in 0.20s", ""), fixed=(0, "1 passed in 0.10s", "")
        )
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = "def test_llm():\n    assert True\n" + _ORACLE_BLOCK
        assert m1._compute_oracle_suite_verdict(_synth_task(), {"generated_test": generated}) == "unavailable"

    def test_mixed_detection_not_rewritten_by_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """oracle skipped（仪器不可用）不得影响 LLM-suite detection（两键仍分离）。"""
        fake, calls = _fake_run_factory(buggy=(1, "1 failed in 0.10s", ""), fixed=(0, "1 passed in 0.10s", ""))
        monkeypatch.setattr(m1, "_run_pytest_in_tmp", fake)
        generated = "def test_llm():\n    assert True\n" + _ORACLE_BLOCK
        state = {"generated_test": generated}
        detection = m1._compute_detection_rate(_synth_task(), state)
        verdict = m1._compute_oracle_suite_verdict(_synth_task(), state)
        assert detection == 1.0
        assert verdict == "correct"
        assert len(calls) == 4  # LLM-suite 2 次 + oracle-suite 2 次（独立执行）


# ═══ 6. 开关关闭零差异 ═════════════════════════════════════════════════════
def test_switch_off_anchor_state_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPEC_ORACLE_EXEC_ENABLE=false：即使锚材料齐备也不注入（历史口径零差异）。"""
    from src.graph.nodes import _spec_oracle_injection_verdict

    monkeypatch.delenv("SPEC_ORACLE_EXEC_ENABLE", raising=False)
    state = {
        "target_code": "def f(x):\n    return x\n",
        "module_name": "m",
        "target_function": "f",
        "spec_anchor": {
            "function_name": "f",
            "logic_analysis": {"function_name": "f", "postconditions_expr": ["result == x"]},
        },
    }
    merged, injected, verdict = _spec_oracle_injection_verdict("def test_x():\n    assert True\n", state)  # type: ignore[arg-type]
    assert merged == "def test_x():\n    assert True\n"
    assert injected is None
    assert verdict == "not_attempted"


def test_skeleton_count_zero_when_inputs_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """有有效输入时不得退化为 no-valid-input 骨架（防全 skip 假安全）。"""
    monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
    code = _compile(
        _spec(pre_expr=["x > 0"], post_expr=["result == x * 2"], boundaries=[{"input": 4}]),
        ["x"],
    )
    assert "no-valid-input" not in code
    assert any(line.strip().startswith("assert") for line in code.splitlines())


def test_hardening_outputs_render_in_replay_report() -> None:
    """replay 报告渲染器在 comparison 在场时给出 before/after 表。"""
    comparison = {
        "baseline": {"path": "m2.json", "sha256": "c" * 64},
        "arms": [
            {
                "arm": "plain_llm_df_spec",
                "before": {
                    "n_oracle_tests_classifiable": 38,
                    "counts": {"correct": 0, "fp": 29, "silent": 9, "misguided": 0},
                    "fp_breakdown": {"fp_assertion_fail": 2, "instrument_error": 27},
                    "unclassifiable_counts": {},
                },
                "after": {
                    "n_oracle_tests_classifiable": 11,
                    "counts": {"correct": 0, "fp": 2, "silent": 9, "misguided": 0},
                    "fp_breakdown": {"fp_assertion_fail": 2, "instrument_error": 0},
                    "skipped_count": 27,
                },
                "delta": {},
            }
        ],
        "expected_mapping": "fp = assertion + instrument",
        "honesty_note": "仪器治疗 ≠ 检出能力提升",
    }
    body = oq.build_report(
        artifact_entries=[],
        anchor_info={"path": "t.json", "sha256": "b" * 64, "n_anchors": 1, "meta": {}},
        arms=[],
        config={},
        command=["python", "-m", "x"],
        instrument_comparison=comparison,
    )
    run_meta = {
        "body_digest": "d" * 64,
        "tool_wall_s": 1.0,
        "determinism": {"repeat": 1, "deterministic": True, "body_digests": ["d" * 64]},
    }
    markdown = oq.render_markdown(body, run_meta)
    assert "O-1 仪器加固前后对照" in markdown
    assert "instrument_error" in markdown
    assert "仪器治疗 ≠ 检出能力提升" in markdown
    readme = oq.render_readme(body, run_meta)
    assert "O-1 仪器加固前后对照" in readme
    assert "fp_assertion_fail" in readme


def test_compare_report_json_shape(tmp_path: Path) -> None:
    payload = {"report": {"arms": []}, "run_meta": {"body_digest": "x"}}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = oq.load_oracle_quality_report(path)
    assert loaded["path"].endswith("baseline.json")
    assert loaded["body_digest"] == "x"
    assert loaded["sha256"]


class TestSkipVerdictIsNotPassed:
    """O-1 配套（Lead 补）：oracle 被 skip 时行级 verdict 不得升级为 passed。"""

    def _state(self):
        from src.graph.nodes import _SPEC_ORACLE_VERDICT_INJECTED

        return {"spec_oracle_verdict": _SPEC_ORACLE_VERDICT_INJECTED, "spec_oracle_injected": True}

    def test_all_skipped_keeps_unresolved(self):
        from src.graph.nodes import _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED, _spec_oracle_verdict_after_run

        result = {
            "passed": True,
            "failed_cases": [],
            "output": "test_generated.py::test_specir_v2_oracle\n"
            "test_generated.py::test_llm_behavior PASSED\n"
            "test_generated.py::test_specir_v2_oracle SKIPPED [1] oracle-unavailable: TypeError: ...\n",
        }
        assert _spec_oracle_verdict_after_run(self._state(), result) is None
        assert _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED != "injected"  # 常量存在性

    def test_real_passed_still_upgrades(self):
        from src.graph.nodes import _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED, _spec_oracle_verdict_after_run

        result = {"passed": True, "failed_cases": [], "output": "test_generated.py::test_specir_v2_oracle PASSED\n"}
        assert _spec_oracle_verdict_after_run(self._state(), result) == _SPEC_ORACLE_VERDICT_INJECTED_AND_PASSED

    def test_failed_oracle_still_detects(self):
        from src.graph.nodes import _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED, _spec_oracle_verdict_after_run

        result = {
            "passed": False,
            "failed_cases": [{"name": "test_generated.py::test_specir_v2_oracle"}],
            "output": "",
        }
        assert _spec_oracle_verdict_after_run(self._state(), result) == _SPEC_ORACLE_VERDICT_INJECTED_AND_FAILED
