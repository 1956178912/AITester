"""
M10（2026-09-29 审查 P0）：可检查规约——schema 强校验 + AST 边界三元组推导。
"""

from __future__ import annotations

import pytest

from src.tools.logic_spec import (
    build_boundary_triplets_section,
    build_logic_spec_findings_section,
    derive_boundary_triplets,
    logic_spec_strict_enabled,
    validate_logic_spec,
)


class TestValidateLogicSpec:
    @pytest.mark.unit
    def test_none_input(self):
        findings = validate_logic_spec(None)
        assert len(findings) == 1
        assert findings[0]["type"] == "missing"

    @pytest.mark.unit
    def test_empty_dict(self):
        findings = validate_logic_spec({})
        assert len(findings) >= 1
        assert findings[0]["type"] in ("missing", "empty_field", "missing_field")

    @pytest.mark.unit
    def test_valid_spec(self):
        spec = {
            "input_domain": "int",
            "output_domain": "float",
            "preconditions": ["x > 0"],
            "postconditions": ["result >= 0"],
            "edge_cases": ["x == 0", "x < 0"],
        }
        findings = validate_logic_spec(spec)
        assert findings == []

    @pytest.mark.unit
    def test_missing_fields(self):
        spec = {
            "input_domain": "int",
            "output_domain": "float",
            # preconditions / postconditions / edge_cases 缺失
        }
        findings = validate_logic_spec(spec)
        missing_types = [f for f in findings if f["type"] == "missing_field"]
        assert len(missing_types) == 3

    @pytest.mark.unit
    def test_empty_list_field(self):
        spec = {
            "input_domain": "int",
            "output_domain": "float",
            "preconditions": [],
            "postconditions": ["p"],
            "edge_cases": ["e"],
        }
        findings = validate_logic_spec(spec)
        empty_types = [f for f in findings if f["type"] == "empty_field" and f["field"] == "preconditions"]
        assert len(empty_types) == 1

    @pytest.mark.unit
    def test_wrong_type(self):
        spec = {
            "input_domain": "int",
            "output_domain": "float",
            "preconditions": "not a list",
            "postconditions": ["p"],
            "edge_cases": ["e"],
        }
        findings = validate_logic_spec(spec)
        wrong_types = [f for f in findings if f["type"] == "wrong_type"]
        assert len(wrong_types) == 1


class TestBuildLogicSpecFindingsSection:
    @pytest.mark.unit
    def test_empty(self):
        assert build_logic_spec_findings_section(None) == ""
        assert build_logic_spec_findings_section([]) == ""

    @pytest.mark.unit
    def test_non_empty(self):
        findings = [{"type": "missing_field", "field": "preconditions", "message": "缺失"}]
        section = build_logic_spec_findings_section(findings)
        assert "missing_field" in section
        assert "preconditions" in section


class TestDeriveBoundaryTriplets:
    @pytest.mark.unit
    def test_empty_code(self):
        assert derive_boundary_triplets("") == []

    @pytest.mark.unit
    def test_invalid_syntax(self):
        assert derive_boundary_triplets("def broken(:") == []

    @pytest.mark.unit
    def test_no_compare(self):
        code = "def add(a, b):\n    return a + b\n"
        assert derive_boundary_triplets(code) == []

    @pytest.mark.unit
    def test_gte_boundary(self):
        code = """
def check(x):
    if x >= 10:
        return "big"
    return "small"
"""
        triplets = derive_boundary_triplets(code)
        assert len(triplets) >= 1
        # 找 x >= 10 的三元组：input 应为 9（10-1）
        found = [t for t in triplets if t["line"] == 3]
        assert found
        assert found[0]["input"] == "9"

    @pytest.mark.unit
    def test_lte_boundary(self):
        code = """
def check(x):
    if x <= 5:
        return "small"
    return "big"
"""
        triplets = derive_boundary_triplets(code)
        found = [t for t in triplets if t["line"] == 3]
        assert found
        assert found[0]["input"] == "6"  # 5+1

    @pytest.mark.unit
    def test_eq_boundary(self):
        code = """
def check(x):
    if x == 42:
        return "answer"
    return "no"
"""
        triplets = derive_boundary_triplets(code)
        found = [t for t in triplets if t["line"] == 3]
        assert found
        assert found[0]["input"] == "42"

    @pytest.mark.unit
    def test_negative_constant(self):
        code = """
def check(x):
    if x > -1:
        return "positive"
    return "non-positive"
"""
        triplets = derive_boundary_triplets(code)
        found = [t for t in triplets if t["line"] == 3]
        assert found
        assert found[0]["input"] == "0"  # -1+1

    @pytest.mark.unit
    def test_focus_function_filtering(self):
        code = """
def fn_a(x):
    if x >= 1:
        return 1
    return 0

def fn_b(y):
    if y <= 100:
        return 1
    return 0
"""
        # 仅提取 fn_b 内的三元组
        triplets = derive_boundary_triplets(code, focus_function="fn_b")
        assert len(triplets) == 1
        assert triplets[0]["line"] == 8

    @pytest.mark.unit
    def test_max_triplets_limit(self):
        code = "\n".join(f"def fn{i}(x):\n    if x > {i}:\n        return 1\n    return 0\n" for i in range(30))
        triplets = derive_boundary_triplets(code, max_triplets=5)
        assert len(triplets) <= 5


class TestBuildBoundaryTripletsSection:
    @pytest.mark.unit
    def test_empty(self):
        assert build_boundary_triplets_section(None) == ""
        assert build_boundary_triplets_section([]) == ""

    @pytest.mark.unit
    def test_non_empty(self):
        triplets = [{"input": "9", "expected": "< 10", "rationale": "line 3", "line": 3}]
        section = build_boundary_triplets_section(triplets)
        assert "9" in section
        assert "确定性边界锚点" in section


class TestLogicSpecStrictEnabled:
    @pytest.mark.unit
    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("LOGIC_SPEC_STRICT_ENABLE", raising=False)
        assert logic_spec_strict_enabled() is False

    @pytest.mark.unit
    def test_true(self, monkeypatch):
        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "true")
        assert logic_spec_strict_enabled() is True

    @pytest.mark.unit
    def test_false_explicit(self, monkeypatch):
        monkeypatch.setenv("LOGIC_SPEC_STRICT_ENABLE", "false")
        assert logic_spec_strict_enabled() is False
