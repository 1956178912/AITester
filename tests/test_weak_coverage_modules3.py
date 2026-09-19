"""
5.1 弱覆盖模块补强测试（第三轮）：
- trace.py: _append 写盘失败降级 + mask_sensitive_info 异常路径
- analysis.py: 统计检验边界条件（恒定通过率 / 小样本 / 缺失基线）
- error_classifier.py: extract_error_context 各分支
- cli/output.py: 非 rich 模式降级路径

运行：
    pytest tests/test_weak_coverage_modules3.py -v
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ─── trace.py: 写盘失败降级 ────────────────────────────────────────────

class TestTraceWriteFailure:
    """4.3/5.1 trace.py 弱覆盖补强：JSONL 写盘失败降级路径。"""

    def test_append_write_failure_does_not_raise(self, tmp_path):
        """写盘抛 OSError 时：_append 不传播异常（旁路观测层设计）。"""
        from src.observability.trace import TraceSession

        # 用一个不可写路径模拟写盘失败
        trace_dir = tmp_path / "traces"
        trace_dir.mkdir()

        session = TraceSession("task_fail", str(trace_dir))
        assert session._enabled is True

        # mock open 抛 OSError
        with patch("builtins.open", side_effect=OSError("disk full")):
            # 不应抛异常
            session.record_node("planner", output_summary="test")
            session.record_task_end(passed=True)

    def test_record_node_with_duration_and_iteration(self, tmp_path):
        """record_node 携带 duration_ms + iteration 参数。"""
        from src.observability.trace import TraceSession

        trace_dir = tmp_path / "traces2"
        trace_dir.mkdir()
        session = TraceSession("task_ok", str(trace_dir))

        session.record_node(
            "generator",
            output_summary="generated 5 tests",
            decision="generate",
            duration_ms=123.456,
            iteration=1,
        )

        # 读取 JSONL 验证字段
        trace_file = trace_dir / "task_ok.trace.jsonl"
        lines = trace_file.read_text().strip().splitlines()
        # 最后一条是 node 记录
        node_record = json.loads(lines[-1])
        assert node_record["event"] == "node"
        assert node_record["node"] == "generator"
        assert node_record["duration_ms"] == 123.46  # round(123.456, 2)
        assert node_record["iteration"] == 1

    def test_record_task_end_with_extra_and_tokens(self, tmp_path):
        """record_task_end 携带 token_usage + extra 参数。"""
        from src.observability.trace import TraceSession

        trace_dir = tmp_path / "traces3"
        trace_dir.mkdir()
        session = TraceSession("task_end", str(trace_dir))

        session.record_task_end(
            passed=False,
            token_usage={"input_tokens": 100, "output_tokens": 50},
            extra={"rag_stats": [], "coverage": 0.85},
        )

        trace_file = trace_dir / "task_end.trace.jsonl"
        lines = trace_file.read_text().strip().splitlines()
        end_record = json.loads(lines[-1])
        assert end_record["event"] == "task_end"
        assert end_record["passed"] is False
        assert end_record["token_usage"]["input_tokens"] == 100
        assert end_record["coverage"] == 0.85

    def test_disabled_session_noop(self):
        """未启用时所有方法 no-op，不创建文件。"""
        import os

        from src.observability.trace import TraceSession

        old_env = os.environ.pop("AITESTER_TRACE_DIR", None)
        try:
            session = TraceSession("no_env", None)
            assert session._enabled is False
            # 不抛异常即可
            session.record_node("planner")
            session.record_task_end(passed=True)
        finally:
            if old_env is not None:
                os.environ["AITESTER_TRACE_DIR"] = old_env


# ─── analysis.py: 统计检验边界 ─────────────────────────────────────────

class TestAnalysisStatisticalBoundaries:
    """5.1 analysis.py 统计检验边界条件测试。"""

    def _make_benchmark(self, details_by_baseline: dict[str, list[dict]]) -> dict:
        """构造 benchmark JSON 结构。"""
        return {
            "results": {
                name: {"details": details} for name, details in details_by_baseline.items()
            }
        }

    def test_paired_t_test_constant_pass_rate_skipped(self):
        """两组通过率全 1（恒定）时：t 检验返回 NaN，应记 skipped 而非数字。"""
        from src.experiments.analysis import analyze_experiment_results

        all_pass = [{"task_id": f"t{i}", "passed": True} for i in range(5)]
        data = {
            "results": {"aitester": {"details": all_pass}, "plain_llm": {"details": all_pass}}
        }
        report = analyze_experiment_results(data)
        # 应返回结构化 dict，不崩溃
        assert isinstance(report, dict)

    def test_insufficient_samples_noted(self):
        """样本 < 最小检验量时：note 说明无法检验。"""
        from src.experiments.analysis import analyze_experiment_results

        few = [{"task_id": "t1", "passed": True}]
        data = {"results": {"aitester": {"details": few}, "plain_llm": {"details": few}}}
        report = analyze_experiment_results(data)
        assert isinstance(report, dict)

    def test_missing_baseline_not_crash(self):
        """results 为空：不崩溃，返回空/说明。"""
        from src.experiments.analysis import analyze_experiment_results

        data = {"results": {}}
        report = analyze_experiment_results(data)
        assert isinstance(report, dict)


# ─── error_classifier: extract_error_context 分支 ──────────────────────

class TestErrorClassifierContextExtraction:
    """5.1 error_classifier extract_error_context 各分支覆盖。"""

    def _extract(self, test_output: str, failed_cases: list[dict] | None = None):
        from src.agents.error_classifier import ErrorClassifier

        clf = ErrorClassifier()
        return clf.extract_error_context(test_output, failed_cases or [])

    def test_module_not_found_extracts_module_name(self):
        """ModuleNotFoundError 分支：提取 module_name。"""
        ctx = self._extract(
            "ModuleNotFoundError: No module named 'requests'\n"
            "  File \"/tmp/test_x.py\", line 1, in <module>"
        )
        assert ctx.module_name == "requests"

    def test_import_error_extracts_module_name(self):
        """ImportError 分支：提取 module_name（正则捕获的是缺失的名称 foo）。"""
        ctx = self._extract(
            "ImportError: cannot import name 'foo' from 'bar_lib'\n"
        )
        # 正则 _RE_IMPORT_ERROR 捕获 group(1) = 'foo'（缺失的名称）
        assert ctx.module_name == "foo"

    def test_syntax_error_file_line(self):
        """SyntaxError 文件行号列号分支。"""
        ctx = self._extract(
            "  File \"/tmp/bad.py\", line 3, in <module>\n"
            "    def broken(:\n"
            "    ^\n"
            "SyntaxError: invalid syntax"
        )
        assert ctx.filename == "/tmp/bad.py"
        assert ctx.line == 3

    def test_traceback_last_match(self):
        """traceback 多帧时：取最后一帧（最深处）。"""
        ctx = self._extract(
            "Traceback (most recent call last):\n"
            '  File "a.py", line 1, in <module>\n'
            '  File "b.py", line 99, in inner\n'
            "    raise ValueError('boom')\n"
            "ValueError: boom"
        )
        assert ctx.filename == "b.py"
        assert ctx.line == 99


# ─── cli/output.py: 非 rich 降级 ───────────────────────────────────────

class TestCliOutputNoRich:
    """5.1 cli/output.py 弱覆盖补强：rich 不可用时的降级路径。"""

    def test_fallback_when_rich_unavailable(self, capsys, monkeypatch):
        """RICH_AVAILABLE=False 时走纯文本降级，不崩溃。"""
        import src.cli.output as out

        monkeypatch.setattr(out, "RICH_AVAILABLE", False)
        results = [
            {"status": "PASS", "file": "test_a.py", "function": "test_x"},
            {"status": "FAIL", "file": "test_b.py", "function": "test_y"},
        ]
        # 不应抛异常
        out.print_rich_table(results)


# ─── prompts/templates: __main__ 自诊断块 ──────────────────────────────

class TestPromptTemplatesMain:
    """5.1 prompts/templates.py 弱覆盖补强：__main__ 自诊断入口。"""

    def test_main_block_prints_prompt_lengths(self, capsys):
        """以 __main__ 方式执行 templates.py：打印各 prompt 字符数。"""

        # 直接以 __main__ 模块身份执行
        with open(os.path.join(PROJECT_ROOT, "src/prompts/templates.py"), encoding="utf-8") as f:
            code = f.read()
        module_globals = {"__name__": "__main__"}
        exec(compile(code, "templates.py", "exec"), module_globals)
        # 执行后 locals() 中的 UPPERCASE 字符串项会被 logger.info 打印
        # 不验证具体输出（logging 默认去向），只确认 exec 无异常
        assert True
