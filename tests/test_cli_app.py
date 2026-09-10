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


class TestSensitiveFilterWiring:
    """SensitiveFilter 日志脱敏接入验证（此前 logging_utils 模块从未被引用，脱敏不生效）。"""

    def test_root_logger_has_sensitive_filter(self):
        import logging

        from src.utils.logging_utils import SensitiveFilter

        assert any(
            isinstance(f, SensitiveFilter) for f in logging.getLogger().filters
        ), "导入 src.cli.app 后 root logger 应挂有 SensitiveFilter"

    def test_api_key_masked_in_logs(self, caplog):
        """日志消息中的 API Key 被替换为占位符。"""
        import logging

        from src.utils.logging_utils import mask_sensitive_info

        with caplog.at_level(logging.INFO):
            logging.getLogger("aitester.test").info(
                "调用失败 sk-%s 认证错误", "A" * 32
            )
        assert "sk-" + "A" * 32 not in caplog.text
        assert "<REDACTED_API_KEY>" in mask_sensitive_info("sk-" + "A" * 32)


class TestRunSequentialResilience:
    """run 命令顺序（parallel=1）模式：单任务异常不中断整个批次。"""

    def _make_files(self, tmp_path, n: int = 2) -> list[str]:
        files = []
        for i in range(n):
            p = tmp_path / f"mod{i}.py"
            p.write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
            files.append(str(p))
        return files

    def test_first_task_exception_does_not_stop_batch(self, tmp_path, monkeypatch):
        """首个文件任务抛异常时，后续文件仍被处理（旧实现整批崩溃）。"""
        files = self._make_files(tmp_path)
        ok_result = {"success": True, "file": files[1], "func": "all", "passed": True}
        calls: list[str] = []

        def fake_run_single_task(target_file, *args, **kwargs):
            calls.append(target_file)
            if target_file == files[0]:
                raise RuntimeError("模拟工作流崩溃")
            return ok_result

        monkeypatch.setattr(cli_app, "_run_single_task", fake_run_single_task)
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--json"])
        assert r.exit_code == 0, f"顺序模式批次应正常结束: {r.output}"
        assert calls == files, "两个文件都应被处理"

    def test_timeout_zero_rejected(self, tmp_path):
        """--timeout 0（或负数）应被参数校验拦截，而不是传到 subprocess。"""
        files = self._make_files(tmp_path, n=1)
        r = CliRunner().invoke(cli_app.cli, ["run", files[0], "--timeout=0", "--json"])
        assert r.exit_code == 1
        assert "--timeout 必须 >= 1 秒" in r.output

    def test_timeout_negative_rejected(self, tmp_path):
        files = self._make_files(tmp_path, n=1)
        r = CliRunner().invoke(cli_app.cli, ["run", files[0], "--timeout=-5", "--json"])
        assert r.exit_code == 1
        assert "--timeout 必须 >= 1 秒" in r.output
