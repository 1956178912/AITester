"""specs/spec_ir 分支覆盖补齐（2026-10-02 批次，P0-1 后续）。

锁定 SpecIR 核心纯静态逻辑（不引入 hypothesis 依赖）：
- parse_logic_analysis 各退化分支（空 dict / 非 dict / 各种三元组形态）
- validate_spec_ir findings 路径
- compile_to_hypothesis 各空返回 + 参数化编译产物路径
- _as_str_list 各类型归一化
"""

from __future__ import annotations

import pytest


class TestParseLogicAnalysisBranches:
    def test_none_input_returns_none(self):
        from src.specs.spec_ir import parse_logic_analysis

        assert parse_logic_analysis(None) is None

    def test_non_dict_input_returns_none(self):
        from src.specs.spec_ir import parse_logic_analysis

        assert parse_logic_analysis("not a dict") is None  # type: ignore[arg-type]

    def test_empty_dict_returns_none(self):
        from src.specs.spec_ir import parse_logic_analysis

        assert parse_logic_analysis({}) is None

    def test_no_material_returns_none(self):
        # 只有 function_name 以外的规约材料全空 → None
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis({"foo": "bar"})
        assert out is None

    def test_basic_spec_with_pre_post(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {
                "function_name": "add",
                "preconditions": ["a > 0"],
                "postconditions": ["result > 0"],
            }
        )
        assert out is not None
        assert out["function_name"] == "add"
        assert out["preconditions"] == ["a > 0"]
        assert out["postconditions"] == ["result > 0"]
        assert out["invariants"] == []
        assert out["oracle_kind"] == "postcondition"

    def test_alias_field_names(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {
                "target_function": "f",
                "pre_conditions": ["p1"],
                "post_conditions": ["p2"],
                "invariant": ["i1"],
            }
        )
        assert out is not None
        assert out["function_name"] == "f"
        assert out["preconditions"] == ["p1"]
        assert out["postconditions"] == ["p2"]
        assert out["invariants"] == ["i1"]

    def test_boundary_triplets_dict_form(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {"function_name": "f"},
            boundary_triplets=[{"input": 1, "expected": 2, "rationale": "r"}],
        )
        assert out is not None
        assert out["boundaries"] == [{"input": 1, "expected": 2, "rationale": "r"}]

    def test_boundary_triplets_tuple_form_2_and_3(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {"function_name": "f"},
            boundary_triplets=[
                (1, 2),  # 二元
                (3, 4, "why"),  # 三元
                {"input": 5, "expected": 6, "rationale": "x"},  # dict
                "junk",  # 非 dict 非 tuple → 跳过
                [1, 2, 3, 4],  # 列表 4 元素 → input/expected 取前 2
            ],
        )
        assert out is not None
        assert len(out["boundaries"]) == 4  # 4 个有效条目

    def test_edge_cases_structured_mapping(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {
                "function_name": "f",
                "edge_cases": [
                    {"input": 0, "expected": 1},
                    {"input": "a", "expected": "b"},
                    "junk_str",  # 非 dict → 跳过
                    {"unrelated": "x"},  # 无 input/expected → 跳过
                ],
            }
        )
        assert out is not None
        assert len(out["boundaries"]) == 2

    def test_no_pre_only_invariant(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis({"function_name": "f", "invariants": ["i"]})
        assert out is not None
        assert out["oracle_kind"] == "invariant"

    def test_boundaries_make_boundary_oracle(self):
        from src.specs.spec_ir import parse_logic_analysis

        out = parse_logic_analysis(
            {"function_name": "f", "invariants": ["i"], "postconditions": ["p"]},
            boundary_triplets=[(1, 2, "r")],
        )
        assert out is not None
        # boundary 优先于 invariant / postcondition
        assert out["oracle_kind"] == "boundary"


class TestValidateSpecIrBranches:
    def test_empty_spec(self):
        from src.specs.spec_ir import validate_spec_ir

        assert validate_spec_ir({}) == ["empty_spec"]
        assert validate_spec_ir(None) == ["empty_spec"]

    def test_missing_schema_version(self):
        from src.specs.spec_ir import validate_spec_ir

        findings = validate_spec_ir({"function_name": "f", "boundaries": [], "oracle_kind": "boundary"})
        assert "schema_version_invalid:None" in findings

    def test_missing_function_name(self):
        from src.specs.spec_ir import validate_spec_ir

        findings = validate_spec_ir(
            {"schema_version": "1", "function_name": "", "boundaries": [], "oracle_kind": "boundary"}
        )
        assert "function_name_missing" in findings

    def test_boundary_missing_input_or_expected(self):
        from src.specs.spec_ir import validate_spec_ir

        findings = validate_spec_ir(
            {
                "schema_version": "1",
                "function_name": "f",
                "boundaries": [{"input": 1}, {"expected": 2}, {"input": 3, "expected": 4}],
                "oracle_kind": "boundary",
            }
        )
        assert "boundary_0_missing_input_or_expected" in findings
        assert "boundary_1_missing_input_or_expected" in findings
        assert "boundary_2" not in " ".join(findings)  # 完整条目不报

    def test_invalid_oracle_kind(self):
        from src.specs.spec_ir import validate_spec_ir

        findings = validate_spec_ir(
            {"schema_version": "1", "function_name": "f", "boundaries": [], "oracle_kind": "bogus"}
        )
        assert "oracle_kind_invalid:bogus" in findings

    def test_all_pass_empty_findings(self):
        from src.specs.spec_ir import validate_spec_ir

        findings = validate_spec_ir(
            {
                "schema_version": "1",
                "function_name": "f",
                "boundaries": [{"input": 1, "expected": 2}],
                "oracle_kind": "boundary",
            }
        )
        assert findings == []


class TestCompileToHypothesisBranches:
    def test_none_spec_returns_empty(self):
        from src.specs.spec_ir import compile_to_hypothesis

        assert compile_to_hypothesis(None) == ""

    def test_missing_function_returns_empty(self):
        from src.specs.spec_ir import compile_to_hypothesis

        assert compile_to_hypothesis({"boundaries": []}, target_module="m", target_function="") == ""

    def test_missing_module_returns_empty(self):
        from src.specs.spec_ir import compile_to_hypothesis

        assert compile_to_hypothesis({"boundaries": []}, target_module="", target_function="f") == ""

    def test_no_material_returns_empty(self):
        from src.specs.spec_ir import compile_to_hypothesis

        # 无 boundaries、无 invariants、无 postconditions → 空
        assert (
            compile_to_hypothesis(
                {
                    "function_name": "f",
                    "boundaries": [],
                    "invariants": [],
                    "postconditions": [],
                    "oracle_kind": "boundary",
                },
                target_module="m",
            )
            == ""
        )

    def test_boundaries_parametrize_compiles(self):
        from src.specs.spec_ir import compile_to_hypothesis

        code = compile_to_hypothesis(
            {
                "function_name": "f",
                "boundaries": [
                    {"input": 1, "expected": 2},
                    {"input": 3, "expected": 4},
                    {"input": 5, "expected": None},  # expected=None → 过滤
                ],
                "invariants": [],
                "postconditions": [],
                "oracle_kind": "boundary",
            },
            target_module="mymod",
        )
        assert "from mymod import f" in code
        assert "@pytest.mark.parametrize" in code
        assert "(1, 2)" in code
        assert "(3, 4)" in code
        # expected=None 的边界被过滤掉
        assert "(5, None)" not in code

    def test_postconditions_only_compiles(self):
        from src.specs.spec_ir import compile_to_hypothesis

        code = compile_to_hypothesis(
            {
                "function_name": "f",
                "boundaries": [],
                "invariants": [],
                "postconditions": ["result > 0"],
                "oracle_kind": "postcondition",
            },
            target_module="m",
        )
        assert "from m import f" in code
        # 无边界 → 无 parametrize；有 postcondition → 仍出非空产物
        assert code != ""

    def test_invariants_require_hypothesis(self):
        from src.specs.spec_ir import compile_to_hypothesis

        # 无 hypothesis 时 invariants 分支不进产物；保守仍出非空边界/后置产物
        code = compile_to_hypothesis(
            {
                "function_name": "f",
                "boundaries": [{"input": 1, "expected": 2}],
                "invariants": ["always positive"],
                "postconditions": [],
                "oracle_kind": "invariant",
            },
            target_module="m",
        )
        assert "from m import f" in code


class TestAsStrListBranches:
    def test_none_returns_empty(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list(None) == []

    def test_str_wraps_in_list(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list("hello") == ["hello"]
        assert _as_str_list("  ") == []

    def test_list_filters_blank(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list(["a", "  ", "b"]) == ["a", "b"]

    def test_tuple(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list(("x", "y")) == ["x", "y"]

    def test_dict_values(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list({"k1": "v1", "k2": "  "}) == ["v1"]

    def test_scalar_wrapped(self):
        from src.specs.spec_ir import _as_str_list

        assert _as_str_list(42) == ["42"]
        assert _as_str_list("") == []


class TestSpecIrEnabledAndBoundariesMaxBranches:
    def test_spec_ir_enabled_default_false(self, monkeypatch):
        from src.specs.spec_ir import spec_ir_enabled

        monkeypatch.delenv("SPEC_IR_ENABLE", raising=False)
        assert spec_ir_enabled() is False

    @pytest.mark.parametrize("val", ["true", "1", "on"])
    def test_spec_ir_enabled_true(self, monkeypatch, val):
        from src.specs.spec_ir import spec_ir_enabled

        monkeypatch.setenv("SPEC_IR_ENABLE", val)
        assert spec_ir_enabled() is True

    def test_spec_ir_enabled_false_values(self, monkeypatch):
        from src.specs.spec_ir import spec_ir_enabled

        monkeypatch.setenv("SPEC_IR_ENABLE", "false")
        assert spec_ir_enabled() is False

    def test_boundaries_max_default(self, monkeypatch):
        from src.specs.spec_ir import _boundaries_max

        monkeypatch.delenv("SPEC_IR_BOUNDARIES_MAX", raising=False)
        assert _boundaries_max() == 20

    def test_boundaries_max_env_override(self, monkeypatch):
        from src.specs.spec_ir import _boundaries_max

        monkeypatch.setenv("SPEC_IR_BOUNDARIES_MAX", "5")
        assert _boundaries_max() == 5

    def test_boundaries_max_invalid_env(self, monkeypatch):
        from src.specs.spec_ir import _boundaries_max

        monkeypatch.setenv("SPEC_IR_BOUNDARIES_MAX", "not_a_number")
        assert _boundaries_max() == 20


class TestHypothesisAvailabilityBranch:
    def test_hypothesis_available_bool(self):
        from src.specs.spec_ir import _hypothesis_available

        out = _hypothesis_available()
        assert out in (True, False)
