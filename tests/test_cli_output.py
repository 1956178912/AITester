"""src/cli/output.py 行为回归测试（O-01：CLI 输出层覆盖率 58% → 目标 75%+）。

覆盖面：
- colorize 的 TTY 双分支（isatty False 直通 / True 包裹 ANSI）
- success/error/warning/info 四条消息路径的图标前缀与 stderr 路由
- print_rich_table 的空列表、缺键兜底、coverage=0.0 不被误判 N/A
"""

from __future__ import annotations

from typing import Any

from src.cli.output import Colors, colorize, error_msg, info_msg, print_rich_table, success_msg, warning_msg


class TestColorize:
    """colorize：仅在 TTY 模式下包裹 ANSI 序列"""

    def test_non_tty_returns_plain_text(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        assert colorize("hello", Colors.GREEN) == "hello"

    def test_tty_wraps_with_reset(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert colorize("hello", Colors.RED) == f"{Colors.RED}hello{Colors.RESET}"


class TestMessageHelpers:
    """success/error/warning/info：图标前缀 + stderr 路由（rich/非 rich 行为一致）"""

    def test_success_msg_prefix(self, capsys):
        success_msg("done")
        assert "✓ done" in capsys.readouterr().out

    def test_error_msg_goes_to_stderr(self, capsys):
        error_msg("boom")
        captured = capsys.readouterr()
        assert "✗ boom" in captured.err
        assert "✗ boom" not in captured.out

    def test_warning_msg_goes_to_stderr(self, capsys):
        warning_msg("careful")
        assert "⚠ careful" in capsys.readouterr().err

    def test_info_msg_goes_to_stdout(self, capsys):
        info_msg("note")
        captured = capsys.readouterr()
        assert "ℹ note" in captured.out
        assert "ℹ note" not in captured.err


class TestPrintRichTable:
    """print_rich_table：空列表、缺键兜底、0.0 覆盖率不被误判 N/A"""

    def test_empty_results_prints_nothing(self, capsys):
        print_rich_table([])
        # 空列表 rich 表头仍会渲染（无数据行）；非 rich 环境直接 return
        out = capsys.readouterr().out
        assert "N/A" not in out

    def test_missing_keys_fall_back_to_defaults(self, capsys):
        # 缺 file/func/iterations/coverage 键时走 get 默认值（"all" / 0 / N/A），不抛 KeyError
        print_rich_table([{"passed": True}])
        out = capsys.readouterr().out
        assert "all" in out  # func 缺失兜底
        assert "N/A" in out  # coverage 缺失兜底

    def test_zero_coverage_rendered_as_0_percent_not_na(self, capsys):
        # 0.0 是合法覆盖率：falsy 判断会把 0% 误显示为 N/A，此处锁定 is-not-None 语义
        print_rich_table([{"passed": False, "coverage": 0.0}])
        out = capsys.readouterr().out
        assert "0.0%" in out
        assert "N/A" not in out

    def test_results_rows_include_status_icon(self, capsys):
        results: list[dict[str, Any]] = [
            {"passed": True, "file": "a/b.py", "func": "f", "coverage": 80.5, "iterations": 2},
            {"passed": False, "file": "c/d.py", "func": "g", "coverage": None, "iterations": 0},
        ]
        print_rich_table(results)
        out = capsys.readouterr().out
        assert "✓" in out  # passed 行状态图标
        assert "b.py" in out  # file 取 basename
        assert "80.5%" in out
