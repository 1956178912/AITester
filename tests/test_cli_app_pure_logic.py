"""cli/app 纯逻辑函数分支补齐（2026-10-02 批次·十四）。

锁定 cli/app.py 未覆盖的纯逻辑 / mock 隔离分支（零工作流执行 / 零 LLM / 零网络）：
- _validate_run_args：parallel / max_iterations / coverage_threshold / timeout 非法值
- _expand_target_files：glob 命中 / 普通路径 / 不存在文件三分支
- _dump_trace_on_failure：有快照写盘（json / 非 json 提示差异）/ 无快照 None
- _print_quality_report：有报告（含超 10 条截断）/ 无报告
- _print_missing_source：缺失源码（含超 20 条截断）/ 全部含源码
"""

from __future__ import annotations

from unittest.mock import patch

# ─── _validate_run_args 非法参数分支 ───────────────────────────────────────


class TestValidateRunArgsBranches:
    def _val(self, parallel=1, max_iterations=1, coverage_threshold=80, timeout=None):
        from src.cli.app import _validate_run_args

        _validate_run_args(parallel, max_iterations, coverage_threshold, timeout)

    def test_valid_args_no_raise(self):
        self._val()  # 合法 → 不抛

    def test_parallel_below_one_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(parallel=0)

    def test_max_iterations_below_one_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(max_iterations=0)

    def test_coverage_threshold_out_of_range_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(coverage_threshold=101)

    def test_coverage_threshold_negative_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(coverage_threshold=-1)

    def test_timeout_zero_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(timeout=0)

    def test_timeout_negative_raises(self):
        import pytest

        with pytest.raises(SystemExit):
            self._val(timeout=-5)

    def test_timeout_none_allowed(self):
        """timeout=None（未指定）→ 走配置默认值，不校验不抛。"""
        self._val(timeout=None)


# ─── _expand_target_files 三分支 ──────────────────────────────────────────


class TestExpandTargetFilesBranches:
    def test_existing_plain_path(self, tmp_path):
        from src.cli.app import _expand_target_files

        f = tmp_path / "target.py"
        f.write_text("def f():\n    return 1\n")
        out = _expand_target_files((str(f),))
        assert str(f) in out

    def test_glob_pattern_matches(self, tmp_path):
        from src.cli.app import _expand_target_files

        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        out = _expand_target_files((str(tmp_path) + "/*.py",))
        names = [p.rsplit("/", 1)[-1] for p in out]
        assert "a.py" in names and "b.py" in names
        assert "c.txt" not in names

    def test_nonexistent_path_returns_empty(self, tmp_path):
        from src.cli.app import _expand_target_files

        out = _expand_target_files((str(tmp_path / "no_such_file_xyz.py"),))
        assert out == []  # 不存在 → 仅告警，不纳入


# ─── _dump_trace_on_failure 分支 ──────────────────────────────────────────


class TestDumpTraceOnFailureBranches:
    def test_snapshot_written_returns_path(self, monkeypatch):
        """有内存快照 → 写盘成功返回路径（output_json 时静默不 echo）。"""
        from src.cli import app as cli_app

        monkeypatch.setattr(cli_app, "_quiet_console_logs", lambda: _null_ctx())

        with patch("src.observability.trace.dump_recent_to", return_value="/tmp/x.jsonl"):
            out = cli_app._dump_trace_on_failure(output_json=True)
        assert out == "/tmp/x.jsonl"

    def test_no_snapshot_returns_none(self):
        """无内存快照（dump_recent_to → None）→ 返回 None。"""
        from src.cli import app as cli_app

        with patch("src.observability.trace.dump_recent_to", return_value=None):
            out = cli_app._dump_trace_on_failure(output_json=True)
        assert out is None

    def test_non_json_mode_echoes_diagnostic(self, monkeypatch, capsys):
        """output_json=False → 额外 echo 诊断路径到 stdout。"""
        from src.cli import app as cli_app

        with patch("src.observability.trace.dump_recent_to", return_value="/tmp/y.jsonl"):
            out = cli_app._dump_trace_on_failure(output_json=False)
        captured = capsys.readouterr()
        assert out == "/tmp/y.jsonl"
        assert "诊断追踪" in captured.out


# ─── _print_quality_report 分支 ───────────────────────────────────────────


class TestPrintQualityReportBranches:
    def test_no_report_no_loader_method(self):
        """loader 无 quality_report 属性 → 视为通过（无加载问题）。"""
        from src.cli.app import _print_quality_report

        class _Loader:
            pass

        _print_quality_report(_Loader(), [1, 2, 3])  # 不抛

    def test_report_present_shows_issues(self, capsys):
        from src.cli.app import _print_quality_report

        class _Loader:
            def quality_report(self):
                return {"t1": ["issue_a"], "t2": ["issue_b"]}

        _print_quality_report(_Loader(), [1, 2, 3, 4])
        # warning_msg 输出到 stderr（err=True）
        out = capsys.readouterr().err
        assert "t1" in out and "issue_a" in out

    def test_report_over_ten_truncates(self, capsys):
        """报告条目 > 10 → 显示前 10 + 截断提示。"""
        from src.cli.app import _print_quality_report

        class _Loader:
            def quality_report(self):
                return {f"t{i}": [f"issue_{i}"] for i in range(15)}

        _print_quality_report(_Loader(), list(range(15)))
        out = capsys.readouterr().err
        assert "t0" in out
        assert "其余 5 个略" in out  # 15 - 10 = 5

    def test_empty_report_shows_pass(self, capsys):
        """loader.quality_report 返回空 dict → 全量通过提示（info_msg 走 stdout）。"""
        from src.cli.app import _print_quality_report

        class _Loader:
            def quality_report(self):
                return {}

        _print_quality_report(_Loader(), [1, 2])
        out = capsys.readouterr().out
        assert "全量质量检查通过" in out


# ─── _print_missing_source 分支 ───────────────────────────────────────────


class TestPrintMissingSourceBranches:
    def test_no_missing_source_method(self):
        """loader 无 tasks_missing_source 属性 → 静默（无缺失信息）。"""
        from src.cli.app import _print_missing_source

        class _Loader:
            pass

        _print_missing_source(_Loader(), [1, 2, 3])  # 不抛

    def test_missing_source_present_shows_list(self, capsys):
        from src.cli.app import _print_missing_source

        class _Loader:
            def tasks_missing_source(self):
                return ["t1", "t2", "t3"]

        _print_missing_source(_Loader(), [1, 2, 3, 4, 5])
        # warning_msg 输出到 stderr（err=True）
        out = capsys.readouterr().err
        assert "缺失被测源码" in out
        assert "t1" in out

    def test_missing_source_over_twenty_truncates(self, capsys):
        """缺失源码 > 20 → 显示前 20 + 截断提示。"""
        from src.cli.app import _print_missing_source

        class _Loader:
            def tasks_missing_source(self):
                return [f"t{i}" for i in range(25)]

        _print_missing_source(_Loader(), list(range(25)))
        out = capsys.readouterr().err
        assert "t0" in out
        assert "其余 5 个略" in out  # 25 - 20 = 5

    def test_no_missing_source_shows_pass(self, capsys):
        """tasks_missing_source 返回空列表 → 全部含被测源码（info_msg 走 stdout）。"""
        from src.cli.app import _print_missing_source

        class _Loader:
            def tasks_missing_source(self):
                return []

        _print_missing_source(_Loader(), [1, 2, 3])
        out = capsys.readouterr().out
        assert "均含被测源码" in out


# ─── 辅助：空 contextlib 上下文（静默 _quiet_console_logs mock）──────────


def _null_ctx():
    import contextlib

    return contextlib.nullcontext()
