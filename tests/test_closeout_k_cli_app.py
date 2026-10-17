"""KB 覆盖率收口：`src/cli/app.py` 的日志降级 / 帮助模板 / 输出降级分支。

动机：cli/app 补口前 18 行未覆盖，缺口是**用户可见输出与启动降级**——只读环境
下文件日志 handler 创建失败、自定义分组帮助的示例段、--verbose 与 --json 组合
的语义提示、无效目标文件的报错出口、glob 展开的存在性兜底、rich 缺失时的纯文本
结果表、空 examples 目录提示。这些分支不涉及业务逻辑，但决定 CLI 在异常环境
下的可用性与可解释性。

纪律：零真实工作流执行（run 命令在"目标文件无效"处提前退出）、零真实网络；
CliRunner 捕获输出；tmp_path 内构造文件。
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from src.cli import app as cli_app

# 本文件的 autouse fixture 会把 CLI 入口的惰性日志初始化替换为 no-op
# （避免测试在 CWD 打开 aitester.log）；需要验证该函数本体的用例
# 在模块导入期捕获真实引用。
_REAL_CONFIGURE_CLI_LOGGING = cli_app._configure_cli_logging


@pytest.fixture(autouse=True)
def _disable_cli_logging_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """拦截 CLI 入口的惰性日志初始化（避免测试在 CWD 打开 aitester.log）。"""
    monkeypatch.setattr(cli_app, "_configure_cli_logging", lambda: None)


@pytest.mark.unit
class TestConfigureCliLoggingDegradation:
    """只读环境下 FileHandler 创建失败 → 降级为仅控制台 handler。"""

    def test_file_handler_oserror_falls_back_to_console(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cli_app, "_LOGGING_CONFIGURED", False)
        monkeypatch.setattr(
            logging,
            "FileHandler",
            lambda *a, **k: (_ for _ in ()).throw(OSError("只读文件系统（模拟）")),
        )
        _REAL_CONFIGURE_CLI_LOGGING()
        assert cli_app._LOGGING_CONFIGURED is True
        # 只剩控制台 handler（stdout StreamHandler），文件 handler 未挂载
        # 注意：本用例用 lambda 替换了 logging.FileHandler（isinstance 不可用），
        # 按类名断言"只挂载了控制台 StreamHandler"
        assert len(cli_app._ACTIVE_CLI_HANDLERS) == 1
        assert type(cli_app._ACTIVE_CLI_HANDLERS[0]).__name__ == "StreamHandler"


@pytest.mark.unit
class TestUxGroupHelp:
    """自定义 CLI 分组帮助：在默认帮助后追加示例命令段。"""

    def test_get_help_appends_examples(self):
        group = cli_app.UXGroup(name="cli")
        ctx = click.Context(group, info_name="cli")
        help_text = group.get_help(ctx)
        assert "示例命令" in help_text
        assert "python main.py run examples/calculator.py" in help_text


@pytest.mark.unit
class TestRunCommandEarlyExits:
    """run 的 verbose 提示与"无有效目标文件"报错出口（不进入工作流）。"""

    @staticmethod
    def _invoke_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, json_output: bool, verbose: bool) -> None:
        """直接调 run 命令回调（绕过 click Path(exists=True) 的入参校验）。

        click 侧 `TARGET_FILES` 声明 exists=True，不存在路径会在进入函数前
        被 click 拦下（exit 2）；本用例要验证的是函数内部"glob 展开后为空"
        的报错出口，故直接调回调并把展开结果注入为空列表。
        """
        existing = tmp_path / "exists.py"
        existing.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "_expand_target_files", lambda target_files: [])
        cli_app.run.callback(
            target_files=(str(existing),),
            func=None,
            max_iterations=1,
            coverage_threshold=80.0,
            parallel=1,
            timeout=None,
            json_output=json_output,
            verbose=verbose,
            dump_trace_on_failure=False,
        )

    def test_verbose_with_json_prints_conflict_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        with pytest.raises(SystemExit) as exc_info:
            self._invoke_run(monkeypatch, tmp_path, json_output=True, verbose=True)
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "--json 模式下控制台日志被静音" in out
        assert "没有有效的目标文件" in out
        assert "list-examples" in out

    def test_verbose_without_json_enables_debug_logging(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        logging.getLogger().setLevel(logging.INFO)  # 先复位，避免全局 DEBUG 级别外溢
        with pytest.raises(SystemExit) as exc_info:
            self._invoke_run(monkeypatch, tmp_path, json_output=False, verbose=True)
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "已启用详细日志模式" in out
        assert "没有有效的目标文件" in out


@pytest.mark.unit
class TestExpandTargetFiles:
    """glob 展开：glob 不命中但路径原样存在时按字面量收下。"""

    def test_literal_existing_path_with_glob_metachars(self, tmp_path: Path):
        weird = tmp_path / "[x].py"
        weird.write_text("def f():\n    return 1\n", encoding="utf-8")
        expanded = cli_app._expand_target_files((str(weird),))
        assert expanded == [str(weird)]

    def test_missing_pattern_only_warns(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        assert cli_app._expand_target_files((str(tmp_path / "absent_*.py"),)) == []
        captured = capsys.readouterr()
        assert "文件不存在" in captured.out + captured.err


@pytest.mark.unit
class TestPrintRunSummaryFallback:
    """rich 缺失时结果表的纯文本降级（覆盖率为 0% 也必须显示为 0%）。"""

    def test_rich_missing_prints_plain_text_table(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)
        results = [
            {"file": "a.py", "func": "f", "passed": True, "coverage": 0.0},
            {"file": "b.py", "func": "g", "passed": False},
        ]
        cli_app._print_run_summary(results, total=2, passed=1, failed=1, elapsed_time=1.5)
        out = capsys.readouterr().out
        assert "批量测试完成" in out
        assert "✓ a.py (func=f, coverage=0.0%)" in out
        assert "✗ b.py (func=g, coverage=N/A)" in out


@pytest.mark.unit
class TestListExamplesEmptyDir:
    """examples 目录存在但无 Python 文件时的提示分支。"""

    def test_empty_examples_dir_warns(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cli_app.os.path, "exists", lambda path: True)
        monkeypatch.setattr(cli_app.os, "listdir", lambda path: ["README.md", "data.json"])
        result = CliRunner().invoke(cli_app.cli, ["list-examples"])
        assert result.exit_code == 0
        assert "examples 目录下没有找到 Python 文件" in result.output
