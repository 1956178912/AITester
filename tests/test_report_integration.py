"""
集成测试：验证错误报告生成器与工作流的集成。

本模块测试报告生成器在实际工作流场景中的表现，
确保报告能正确生成并保存。
"""

import json
from pathlib import Path

import pytest

from src.agents.error_classifier import ErrorCategory
from src.reports import ReportFormat, ReportGenerator


class TestReportGeneratorIntegration:
    """报告生成器集成测试。"""

    @pytest.fixture
    def generator(self) -> ReportGenerator:
        """创建报告生成器实例。"""
        return ReportGenerator()

    def test_full_workflow_simulation(self, generator: ReportGenerator, tmp_path: Path) -> None:
        """模拟完整工作流：生成错误 → 创建报告 → 保存 → 读取验证。"""
        # 模拟测试失败场景
        error_output = """
============================= test session ==============================
collected 3 items

test_calc.py::test_divide_by_zero FAILED                              [ 33%]
test_calc.py::test_negative_input PASSED                              [ 66%]
test_calc.py::test_valid_input PASSED                                 [100%]

=========================== short test summary ============================
FAILED test_calc.py::test_divide_by_zero - ZeroDivisionError: division by zero
========================= 1 failed, 2 passed in 0.1s =========================
"""
        # 生成报告
        report = generator.generate(
            task_id="integration_test_001",
            target_file="examples/calculator.py",
            target_function="divide",
            error_output=error_output,
            coverage=66.7,
            iteration_count=1,
        )

        # 验证报告内容
        assert report.error_category == ErrorCategory.RUNTIME
        assert report.task_id == "integration_test_001"
        assert len(report.failed_cases) >= 1
        assert "除零错误" in report.root_cause

        # 保存到临时目录
        output_dir = tmp_path / "reports"
        json_path = generator.save_report(report, output_dir=str(output_dir), format=ReportFormat.JSON)

        # 验证文件存在
        assert json_path.exists()
        assert json_path.suffix == ".json"

        # 读取并验证 JSON 内容
        content = json_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["task_id"] == "integration_test_001"
        assert data["error_category"] == "runtime"
        assert "coverage" in data
        assert "created_at" in data

    def test_multiple_error_types(self, generator: ReportGenerator) -> None:
        """测试多种错误类型的报告生成。"""
        # 定义错误消息和预期分类（使用更明确的匹配模式）
        test_cases = [
            ("SyntaxError: invalid syntax", ErrorCategory.SYNTAX),
            ("ImportError: cannot import name", ErrorCategory.SYNTAX),
            ("ZeroDivisionError: division by zero", ErrorCategory.RUNTIME),
            ("TypeError: unsupported operand type", ErrorCategory.RUNTIME),
            ("AssertionError: expected 1, got 2", ErrorCategory.ASSERTION),
            ("pytest-timeout: test timed out", ErrorCategory.TIMEOUT),  # 需要包含 timeout 关键字
        ]

        for error_msg, expected_category in test_cases:
            report = generator.generate(
                task_id=f"test_{expected_category.value}",
                target_file="test.py",
                target_function="func",
                error_output=error_msg,
            )
            assert report.error_category == expected_category, f"Failed for: {error_msg}"

    def test_report_format_consistency(self, generator: ReportGenerator) -> None:
        """验证三种输出格式的内容一致性。"""
        report = generator.generate(
            task_id="format_test",
            target_file="test.py",
            target_function="test_func",
            error_output="AssertionError: test failed",
        )

        # 文本格式
        text = report.to_text()
        assert "AITester 错误诊断报告" in text
        assert "format_test" in text

        # JSON 格式
        data = json.loads(report.to_json())
        assert data["task_id"] == "format_test"
        assert data["error_category"] == "assertion"

        # Markdown 格式
        md = report.to_markdown()
        assert "# AITester 错误诊断报告" in md
        assert "format_test" in md

    def test_large_error_output_handling(self, generator: ReportGenerator) -> None:
        """测试长错误输出的处理。"""
        # 生成一个很长的错误输出
        long_error = "\n".join([f"Error line {i}: Some detailed error message" for i in range(100)])

        report = generator.generate(
            task_id="large_error_test",
            target_file="test.py",
            target_function="func",
            error_output=long_error,
        )

        # 验证错误消息被截断（最多 500 字符）
        assert len(report.error_message) <= 500
        assert "Error line 0" in report.error_message

    def test_empty_and_edge_cases(self, generator: ReportGenerator) -> None:
        """测试空输入和边界情况。"""
        # 空错误输出
        report1 = generator.generate(
            task_id="empty_test",
            target_file="test.py",
            target_function="func",
            error_output="",
        )
        assert report1.error_message == ""
        assert "未知错误类型" in report1.root_cause

        # 仅空白字符
        report2 = generator.generate(
            task_id="whitespace_test",
            target_file="test.py",
            target_function="func",
            error_output="   \n\t  ",
        )
        assert report2.error_message == ""

    def test_history_tracking(self, generator: ReportGenerator) -> None:
        """测试历史修复记录跟踪。"""
        history = [
            {"iteration": 1, "action": "fix_import", "result": "success"},
            {"iteration": 2, "action": "fix_assertion", "result": "partial"},
        ]

        report = generator.generate(
            task_id="history_test",
            target_file="test.py",
            target_function="func",
            error_output="Error",
            history=history,
            iteration_count=2,
        )

        assert len(report.history) == 2
        assert report.history[0]["iteration"] == 1
        assert report.iteration_count == 2

    def test_save_all_formats(self, generator: ReportGenerator, tmp_path: Path) -> None:
        """测试保存所有三种格式。"""
        report = generator.generate(
            task_id="format_save_test",
            target_file="test.py",
            target_function="func",
            error_output="Test error",
        )

        output_dir = tmp_path / "all_formats"

        # 保存文本格式
        txt_path = generator.save_report(report, output_dir=str(output_dir), format=ReportFormat.TEXT)
        assert txt_path.exists()
        assert txt_path.suffix == ".txt"

        # 保存 JSON 格式
        json_path = generator.save_report(report, output_dir=str(output_dir), format=ReportFormat.JSON)
        assert json_path.exists()
        assert json_path.suffix == ".json"

        # 保存 Markdown 格式
        md_path = generator.save_report(report, output_dir=str(output_dir), format=ReportFormat.MARKDOWN)
        assert md_path.exists()
        assert md_path.suffix == ".md"

        # 验证所有文件非空
        assert txt_path.stat().st_size > 0
        assert json_path.stat().st_size > 0
        assert md_path.stat().st_size > 0
