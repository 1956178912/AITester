"""
单元测试：测试 ExecutorAgent 的执行逻辑。

覆盖范围：
    - _parse_coverage: 覆盖率解析
    - _parse_failed_cases: 失败用例解析
"""

import pytest
from unittest.mock import patch, MagicMock


class TestParseCoverage:
    """测试 ExecutorAgent._parse_coverage 静态方法。"""

    def test_normal_coverage(self):
        """正常覆盖率解析。"""
        from src.agents.executor import ExecutorAgent
        output = """
============================= test session starts ==============================
collected 1 item

test_foo.py .                                                              [100%]

---------- coverage: platform darwin, python 3.14.6 --------------------------
Name                      Stmts   Miss  Cover
---------------------------------------------
src/agents/executor.py      89     36    60%
---------------------------------------------
TOTAL                      1043    223    79%
============================== 1 passed in 0.5s ===============================
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 79.0

    def test_no_coverage_info(self):
        """无覆盖率信息时返回 0.0。"""
        from src.agents.executor import ExecutorAgent
        output = """
============================= test session starts ==============================
collected 1 item
test_foo.py .                                                              [100%]
============================== 1 passed in 0.5s ===============================
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 0.0

    def test_coverage_int_only(self):
        """覆盖率只有整数时正确解析。"""
        from src.agents.executor import ExecutorAgent
        output = """
TOTAL                      100     10    90%
"""
        result = ExecutorAgent._parse_coverage(output)
        assert result == 90.0


class TestParseFailedCases:
    """测试 ExecutorAgent._parse_failed_cases 静态方法。"""

    def test_normal_failures(self):
        """正常解析失败用例。"""
        from src.agents.executor import ExecutorAgent
        output = """
FAILED test_foo.py::test_bar - AssertionError: expected 1, got 2
FAILED test_baz.py::test_qux - ValueError: invalid literal
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert len(result) == 2
        assert "test_bar" in result[0]["name"]
        assert "test_qux" in result[1]["name"]

    def test_no_failures(self):
        """无失败用例时返回空列表。"""
        from src.agents.executor import ExecutorAgent
        output = """
============================== 1 passed in 0.5s ===============================
"""
        result = ExecutorAgent._parse_failed_cases(output)
        assert result == []


class TestExecutorNode:
    """测试 ExecutorAgent 节点函数。"""

    def test_executor_node_pass(self):
        """测试通过时标记为 PASS。"""
        from src.graph.workflow import _executor_node
        with patch("src.graph.workflow.ExecutorAgent") as mock_exec_class:
            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": True,
                "output": "1 passed",
                "coverage": 85.0,
                "failed_cases": [],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): pass",
                "target_file": "examples/calculator.py",
                "iteration": 0,
            }
            result = _executor_node(state)
            assert result["test_passed"] is True
            assert result["coverage_report"] == 85.0

    def test_executor_node_fail(self):
        """测试失败时记录失败用例。"""
        from src.graph.workflow import _executor_node
        with patch("src.graph.workflow.ExecutorAgent") as mock_exec_class:
            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": False,
                "output": "1 failed",
                "coverage": 60.0,
                "failed_cases": [{"name": "test_foo", "error": "AssertionError"}],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): assert False",
                "target_file": "examples/calculator.py",
                "iteration": 0,
            }
            result = _executor_node(state)
            assert result["test_passed"] is False
            assert len(result["failed_cases"]) == 1
