"""测试 src/cli/app.py 的 click 命令（此前 29% 覆盖，run 命令需重度 mock 暂不覆盖）

覆盖 list_examples 命令的正常/缺目录分支，以及 cli group 的 --version。
"""

import os

from click.testing import CliRunner

from src.cli import app as cli_app


class TestListExamples:
    """list-examples 命令"""

    def test_lists_py_files(self):
        r = CliRunner().invoke(cli_app.cli, ["list-examples"])
        assert r.exit_code == 0
        assert "可用示例文件" in r.output
        assert "calculator.py" in r.output

    def test_missing_examples_dir(self, monkeypatch):
        """examples 目录不存在 → 友好提示而非崩溃。"""
        real_exists = os.path.exists

        def fake_exists(p):
            if "examples" in os.path.basename(p):
                return False
            return real_exists(p)

        monkeypatch.setattr(os.path, "exists", fake_exists)
        r = CliRunner().invoke(cli_app.cli, ["list-examples"])
        assert r.exit_code == 0
        assert "examples 目录不存在" in r.output


class TestCliGroup:
    """cli group 基本行为"""

    def test_version_option(self):
        r = CliRunner().invoke(cli_app.cli, ["--version"])
        assert r.exit_code == 0
        assert "version" in r.output.lower()
