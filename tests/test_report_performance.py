"""
报告生成器性能基准测试。

本模块测试报告生成器的性能表现，
确保在大规模场景下仍能保持高效响应。
"""

import statistics
import time

import pytest

from src.reports import ReportFormat, ReportGenerator


class TestReportPerformance:
    """报告生成器性能测试。"""

    @pytest.fixture
    def generator(self) -> ReportGenerator:
        """创建报告生成器实例。"""
        return ReportGenerator()

    def test_single_report_generation_time(self, generator: ReportGenerator) -> None:
        """测试单次报告生成时间。"""
        error_output = "AssertionError: expected 1, got 2"

        # 预热
        generator.generate(
            task_id="warmup",
            target_file="test.py",
            target_function="func",
            error_output=error_output,
        )

        # 测量多次取平均
        times = []
        iterations = 100
        for i in range(iterations):
            start = time.perf_counter()
            report = generator.generate(
                task_id=f"perf_test_{i}",
                target_file="test.py",
                target_function="func",
                error_output=error_output,
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = statistics.mean(times)
        max_time = max(times)

        # 断言：平均生成时间应 < 10ms
        assert avg_time < 0.01, f"平均生成时间 {avg_time*1000:.2f}ms 超过 10ms 阈值"
        # 断言：最大生成时间应 < 50ms
        assert max_time < 0.05, f"最大生成时间 {max_time*1000:.2f}ms 超过 50ms 阈值"

    def test_large_error_output_processing(self, generator: ReportGenerator) -> None:
        """测试处理大错误输出的性能。"""
        # 生成一个很大的错误输出（1000 行）
        large_error = "\n".join([f"Error line {i}: Detailed error message with lots of text" for i in range(1000)])

        start = time.perf_counter()
        report = generator.generate(
            task_id="large_error_test",
            target_file="test.py",
            target_function="func",
            error_output=large_error,
        )
        elapsed = time.perf_counter() - start

        # 验证错误消息被截断
        assert len(report.error_message) <= 500
        # 断言：处理时间应 < 100ms
        assert elapsed < 0.1, f"处理大错误输出耗时 {elapsed*1000:.2f}ms 超过 100ms 阈值"

    def test_multiple_format_generation(self, generator: ReportGenerator) -> None:
        """测试多种格式生成的性能。"""
        report = generator.generate(
            task_id="format_perf_test",
            target_file="test.py",
            target_function="func",
            error_output="Test error",
        )

        # 测量三种格式生成时间
        formats = [
            ("text", lambda: report.to_text()),
            ("json", lambda: report.to_json()),
            ("markdown", lambda: report.to_markdown()),
        ]

        for format_name, generate_fn in formats:
            times = []
            for _ in range(50):
                start = time.perf_counter()
                generate_fn()
                elapsed = time.perf_counter() - start
                times.append(elapsed)

            avg_time = statistics.mean(times)
            # 断言：每种格式生成时间应 < 5ms
            assert avg_time < 0.005, f"{format_name} 格式平均生成时间 {avg_time*1000:.2f}ms 超过 5ms 阈值"

    def test_report_save_performance(self, generator: ReportGenerator, tmp_path) -> None:
        """测试报告保存性能。"""
        report = generator.generate(
            task_id="save_perf_test",
            target_file="test.py",
            target_function="func",
            error_output="Test error",
        )

        output_dir = tmp_path / "perf_reports"

        # 测量保存时间
        times = []
        for i in range(20):
            start = time.perf_counter()
            generator.save_report(report, output_dir=str(output_dir), format=ReportFormat.TEXT)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = statistics.mean(times)
        # 断言：平均保存时间应 < 10ms
        assert avg_time < 0.01, f"平均保存时间 {avg_time*1000:.2f}ms 超过 10ms 阈值"

    def test_concurrent_report_generation(self, generator: ReportGenerator) -> None:
        """测试并发报告生成的性能。"""
        import threading

        reports = []
        errors = []

        def generate_report(task_id: int) -> None:
            try:
                report = generator.generate(
                    task_id=f"concurrent_{task_id}",
                    target_file="test.py",
                    target_function="func",
                    error_output=f"Error {task_id}",
                )
                reports.append(report)
            except Exception as e:
                errors.append(e)

        # 创建 10 个线程并发生成报告
        threads = []
        for i in range(10):
            t = threading.Thread(target=generate_report, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join(timeout=5)

        # 验证所有报告生成成功
        assert len(errors) == 0, f"并发生成出现错误: {errors}"
        assert len(reports) == 10, f"应生成 10 个报告，实际生成 {len(reports)} 个"

    def test_memory_usage_estimate(self, generator: ReportGenerator) -> None:
        """估算内存使用情况。"""
        import sys

        # 生成一个报告
        report = generator.generate(
            task_id="memory_test",
            target_file="test.py",
            target_function="func",
            error_output="Test error with some details",
        )

        # 估算报告对象大小
        report_size = sys.getsizeof(report)
        report_dict_size = sys.getsizeof(report.to_dict())

        # 断言：报告对象大小应合理（< 10KB）
        assert report_size < 10240, f"报告对象大小 {report_size} bytes 超出预期"
        assert report_dict_size < 10240, f"报告字典大小 {report_dict_size} bytes 超出预期"
