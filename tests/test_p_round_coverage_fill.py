#!/usr/bin/env python3
"""P 轮覆盖率补齐：oracle 示例通道 / A-19 停止原因 / doctor 辅助分支。

背景：P 轮新增约 446 行源码（示例解析/归一/编译、doctor 命令、停滞短路），
全量覆盖率从 96.54% 降到 96.38%（低于 ratchet 水位 96.40%）。本文件只补
**未覆盖的既有分支**（不改产品语义），确保 ratchet 只升不降。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.specs.spec_ir import (
    compile_to_hypothesis,
    is_literal_value,
    parse_examples,
    parse_logic_analysis,
    validate_spec_ir,
)


class TestLiteralAndExamplesParsing:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, True),
            (True, True),
            (False, True),
            (7, True),
            (-1, True),
            (1.5, True),
            (float("nan"), False),
            (float("inf"), False),
            (float("-inf"), False),
            ("text", True),
            ([1, "a"], True),
            ([1, object()], False),
            ({"k": [1, True]}, True),
            ({1: "bad-key"}, False),
            (object(), False),
        ],
    )
    def test_is_literal_value_branches(self, value: Any, expected: bool) -> None:
        assert is_literal_value(value) is expected

    def test_parse_examples_non_list_and_zero_limit(self) -> None:
        assert parse_examples("not-a-list") == []
        assert parse_examples(None) == []
        assert parse_examples([{"input": [1], "expected": 1}], max_examples=0) == []

    def test_parse_examples_dedup_and_invalid_subset(self) -> None:
        raw = [
            {"input": [1], "expected": 2},
            {"input": [1], "expected": 2},  # 完全重复 → 去重
            {"input": [float("nan")], "expected": 2},  # NaN 非法
            {"input": [2]},  # 缺 expected
            "not-a-dict",
            {"input": [3], "expected": [4]},
        ]
        parsed = parse_examples(raw, max_examples=5)
        assert parsed == [{"input": [1], "expected": 2}, {"input": [3], "expected": [4]}]

    def test_parse_logic_analysis_examples_all_invalid_no_key(self) -> None:
        spec = parse_logic_analysis(
            {"function_name": "f", "examples": [{"input": [float("inf")], "expected": 1}, {"bad": 1}]}
        )
        assert spec is not None
        assert "examples" not in spec


class TestValidateAndCompileToHypothesis:
    def test_validate_spec_ir_findings(self) -> None:
        assert validate_spec_ir(None) == ["empty_spec"]
        bad = {
            "schema_version": 99,
            "function_name": "",
            "boundaries": [{"expected": 1}],
            "oracle_kind": "unknown_kind",
        }
        findings = validate_spec_ir(bad)
        assert any(f.startswith("schema_version_invalid") for f in findings)
        assert "function_name_missing" in findings
        assert any("boundary_0_missing_input_or_expected" in f for f in findings)
        assert any(f.startswith("oracle_kind_invalid") for f in findings)

    def test_compile_to_hypothesis_shapes(self) -> None:
        assert compile_to_hypothesis(None, "m", "f") == ""
        spec_no_boundaries = {"boundaries": [], "function_name": "f", "oracle_kind": "postcondition"}
        assert compile_to_hypothesis(spec_no_boundaries, "m", "f") == ""
        spec = {
            "function_name": "f",
            "oracle_kind": "boundary",
            "boundaries": [{"input": [1], "expected": 2}],
            "invariants": ["x > 0"],
        }
        code = compile_to_hypothesis(spec, "m", "f")
        assert "test_specir_boundary" in code
        assert "invariant（未机器化" in code


class TestOracleNormalizationAndWitness:
    def test_normalize_return_value_branches(self) -> None:
        from src.specs.spec_ir_v2 import normalize_return_value

        assert normalize_return_value((1, (2, 3))) == [1, [2, 3]]
        assert normalize_return_value([1, (2,)]) == [1, [2]]
        assert normalize_return_value({"k": (1, 2)}) == {"k": [1, 2]}
        assert normalize_return_value("str") == "str"
        assert normalize_return_value(b"bytes") == b"bytes"
        assert normalize_return_value(x for x in [1, 2, 3]) == [1, 2, 3]
        assert normalize_return_value(7) == 7
        # one-shot：同一 generator 不得二次消费（第二次已耗尽 → 空 list）
        gen = (x for x in [1])
        assert normalize_return_value(gen) == [1]
        assert normalize_return_value(gen) == []

    def test_multi_param_smt_witness_binding_path(self) -> None:
        from src.specs.spec_ir_v2 import compile_spec_oracle

        spec = parse_logic_analysis(
            {
                "function_name": "add",
                "preconditions": ["a > 0", "b > 0"],
                "preconditions_expr": ["a > 0", "b > 0"],
                "postconditions_expr": ["r == a + b"],
            }
        )
        assert spec is not None
        code = compile_spec_oracle(spec, "target_mod", "add", signature_params=["a", "b"])
        # 有 SMT 见证时多参绑定为 `a, b = <witness>`（覆盖 _precondition_witness_binding 多参分支）；
        # 无见证时退化为 0 绑定并注释前件——两种形态都必须 ast 合法且崩溃安全。
        assert "def test_specir_v2_oracle" in code
        assert "pytest.skip(" in code
        import ast

        ast.parse(code)


class TestDoctorHelperBranches:
    def test_llm_endpoints_variants(self, monkeypatch, tmp_path) -> None:
        from src.cli import app as cli_app

        monkeypatch.setattr(cli_app, "_DOCTOR_REPO_ROOT", tmp_path)
        empty = cli_app._doctor_check_llm_endpoints(environ={})
        assert empty["status"] == "warn"
        assert empty["evidence"]["configured"] == 0
        (tmp_path / ".env.local").write_text("LLM_1_API_KEY=x\n", encoding="utf-8")
        partial = cli_app._doctor_check_llm_endpoints(environ={"LLM_1_API_KEY": "k"})
        assert partial["status"] == "warn"
        assert partial["evidence"]["incomplete_indices"] == [1]
        full = cli_app._doctor_check_llm_endpoints(
            environ={
                "LLM_1_API_KEY": "k",
                "LLM_1_BASE_URL": "https://example.invalid",
                "LLM_1_MODEL_NAME": "m",
            }
        )
        assert full["status"] == "pass"

    def test_kernel_sandbox_variants(self) -> None:
        from src.cli import app as cli_app

        unsupported = cli_app._doctor_check_kernel_sandbox(supported=False, capabilities={})
        assert unsupported["status"] == "warn"
        supported = cli_app._doctor_check_kernel_sandbox(
            supported=True, capabilities={"platform": "test", "backends": ["fake"]}
        )
        assert supported["status"] == "pass"

    def test_datasets_variants(self) -> None:
        from src.cli import app as cli_app

        class _Ds:
            def __init__(self, size: int) -> None:
                self.size = size
                self.tasks: list[Any] = []

        def _load(name: str) -> Any:
            if name == "ult":
                raise RuntimeError("ULT 数据缺失（降级）")
            return _Ds(3 if name == "examples" else 50)

        check = cli_app._doctor_check_datasets(load_dataset_fn=_load)
        assert check["status"] in ("pass", "warn")
        assert "ult" in check["evidence"].get("errors", {}) or check["status"] == "pass"

    def test_collect_checks_isolates_exceptions(self, monkeypatch) -> None:
        from src.cli import app as cli_app

        def _boom() -> dict[str, Any]:
            raise RuntimeError("boom")

        monkeypatch.setattr(cli_app, "_doctor_check_python", _boom)
        checks = cli_app._doctor_collect_checks()
        assert checks and any(c["name"] == "python" and c["status"] == "warn" for c in checks)

    def _probe_result(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "report": {
                "probes": [
                    {"status": "pass", "group": "cli", "name": "ok", "requires_llm": False},
                    {"status": "skip", "group": "executor", "name": "cap-b", "requires_llm": False},
                    {"status": "skip", "group": "cli", "name": "llm-a", "requires_llm": True},
                ],
                "load_errors": [],
            },
            "detail": "",
            "duration_s": 0.1,
            "returncode": 0,
            "stderr_tail": "",
        }

    def test_print_human_renders_skip_sections(self, capsys) -> None:
        from src.cli import app as cli_app

        report = cli_app._doctor_build_report(
            groups=[],
            timeout_s=1,
            strict=False,
            checks=[cli_app._doctor_check("x", "X", "pass", "ok")],
            probe_result=self._probe_result(),
        )
        cli_app._doctor_print_human(report)
        out = capsys.readouterr().out
        assert "真实 LLM" in out or "跳过" in out
        assert "环境能力差异" in out or "cap-b" in out

    def test_aggregate_unknown_status_and_non_dict_rows(self) -> None:
        from src.cli import app as cli_app

        agg = cli_app._doctor_aggregate_probe_result(
            {
                "status": "ok",
                "report": {"probes": ["bad-row", {"status": "weird", "group": "g", "name": "n"}], "load_errors": []},
                "detail": "",
                "duration_s": 0.1,
                "returncode": 0,
                "stderr_tail": "",
            }
        )
        assert agg["summary"]["error"] == 1

    def test_run_probe_matrix_backend_failure(self, monkeypatch) -> None:
        from src.cli import app as cli_app

        class _Proc:
            returncode = 1
            stdout = "not-json"
            stderr = "boom"

        monkeypatch.setattr("subprocess.run", lambda *a, **k: _Proc())
        result = cli_app._doctor_run_probe_matrix(groups=["budget"], timeout_s=5)
        assert result["status"] == "error"

    def test_report_json_roundtrip_schema(self) -> None:
        from src.cli import app as cli_app

        report = cli_app._doctor_build_report(
            groups=["budget"],
            timeout_s=1,
            strict=True,
            checks=[cli_app._doctor_check("x", "X", "pass", "ok")],
            probe_result={
                "status": "error",
                "report": None,
                "detail": "backend down",
                "duration_s": 0.0,
                "returncode": 1,
                "stderr_tail": "",
            },
        )
        assert report["schema"] == "aitester_doctor/1"
        assert report["exit_code"] == 1
        json.dumps(report)
