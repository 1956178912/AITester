"""
单元测试：测试 ExecutorAgent 解析方法。

覆盖范围：
    - _parse_coverage：正常、无 TOTAL 行、多行
    - _parse_failed_cases：正常解析、多个失败用例、无失败
"""

import pytest
from src.agents.executor import ExecutorAgent


# ─── TestParseCoverage：覆盖率解析 ─────────────────────────────────────────────
class TestParseCoverage:
    """测试 ExecutorAgent._parse_coverage 静态方法。"""

    def test_normal_coverage_output(self):
        """正常输出中包含 TOTAL 行时正确解析百分比。"""
        output = """
Name       Stmts   Miss  Cover
--------------------------------
module.py     10      2    80%
--------------------------------
TOTAL         10      2    80%
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 80.0

    def test_no_total_line(self):
        """无 TOTAL 行时返回 0.0。"""
        output = """
Name       Stmts   Miss  Cover
--------------------------------
module.py     10      2    80%
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 0.0

    def test_multiple_total_lines(self):
        """多个 TOTAL 行时返回第一个匹配值。"""
        output = """
------- Coverage: module_a -------
TOTAL         20      4    80%
------- Coverage: module_b -------
TOTAL         30      3    90%
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 80.0

    def test_coverage_with_decimal(self):
        """含小数的覆盖率正确解析。"""
        output = "TOTAL          50      3   94%"
        result = ExecutorAgent._parse_coverage(output)
        assert result == 94.0

    def test_empty_output(self):
        """空输出返回 0.0。"""
        result = ExecutorAgent._parse_coverage("")
        assert result == 0.0

    def test_no_coverage_section(self):
        """无覆盖率信息的输出返回 0.0。"""
        output = """
============================= tests =============================
passed: 5
failed: 0
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 0.0


# ─── TestParseFailedCases：失败用例解析 ───────────────────────────────────────
class TestParseFailedCases:
    """测试 ExecutorAgent._parse_failed_cases 静态方法。"""

    def test_normal_parse(self):
        """正常解析单个失败用例。"""
        output = """
============================= test session ==============================
FAILED test_foo.py::test_bar - AssertionError: expected 1, got 2
=========================== short test summary ============================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 1
        assert result[0]["name"] == "test_foo.py::test_bar"
        assert "AssertionError" in result[0]["error"]

    def test_multiple_failed_cases(self):
        """解析多个失败用例。"""
        output = """
FAILED test_a.py::test_one - AssertionError: fail 1
FAILED test_b.py::test_two - ValueError: wrong value
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 2
        assert result[0]["name"] == "test_a.py::test_one"
        assert result[1]["name"] == "test_b.py::test_two"

    def test_no_failed_cases(self):
        """无失败用例时返回空列表。"""
        output = """
============================= test session ==============================
passed: 5
========================= 5 passed in 0.1s =========================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert result == []

    def test_failed_case_with_multiline_error(self):
        """失败用例含多行错误信息时正确收集。"""
        output = """
FAILED test_foo.py::test_complex - AssertionError:
    Expected: 10
    Actual:   5
    Traceback: line 42
=========================== short test summary ============================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 1
        assert "Expected: 10" in result[0]["error"]
        assert "Actual:   5" in result[0]["error"]

    def test_failed_case_stops_at_separator(self):
        """遇到分隔线后停止收集错误信息。"""
        output = """
FAILED test_foo.py::test_one - AssertionError: first fail
=========================== short test summary ============================
PASSED test_bar.py::test_two
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 1
        assert result[0]["name"] == "test_foo.py::test_one"
