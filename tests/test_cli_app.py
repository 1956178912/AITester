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

        assert any(isinstance(f, SensitiveFilter) for f in logging.getLogger().filters), (
            "导入 src.cli.app 后 root logger 应挂有 SensitiveFilter"
        )

    def test_api_key_masked_in_logs(self, caplog):
        """日志消息中的 API Key 被替换为占位符。"""
        import logging

        from src.utils.logging_utils import mask_sensitive_info

        with caplog.at_level(logging.INFO):
            logging.getLogger("aitester.test").info("调用失败 sk-%s 认证错误", "A" * 32)
        assert "sk-" + "A" * 32 not in caplog.text
        assert "<REDACTED_API_KEY>" in mask_sensitive_info("sk-" + "A" * 32)


class TestSensitiveFormatter:
    """SensitiveFormatter：对 exc_info 异常堆栈也脱敏（SensitiveFilter 覆盖不到的盲区）。"""

    def test_exc_info_traceback_masked(self):
        import io
        import logging

        from src.utils.logging_utils import SensitiveFormatter

        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(SensitiveFormatter("%(message)s"))
        logger = logging.getLogger("aitester.sensfmt")
        logger.setLevel(logging.ERROR)
        logger.handlers = [handler]
        logger.propagate = False
        try:
            secret = "sk-" + "B" * 32
            try:
                raise RuntimeError(f"认证失败 {secret}")
            except RuntimeError:
                logger.exception("出错了")
        finally:
            logger.handlers = []
        text = buf.getvalue()
        # 异常消息与堆栈里的密钥都应被脱敏（堆栈经 SensitiveFormatter 覆盖）
        assert secret not in text
        assert "<REDACTED_API_KEY>" in text

    def test_sensitive_formatter_attached_to_cli_handlers(self):
        """src.cli.app 创建的控制台/文件 handler 应挂 SensitiveFormatter（保证落盘日志也脱敏）。"""
        from src.cli import app as cli_app
        from src.utils.logging_utils import SensitiveFormatter

        assert isinstance(cli_app._log_formatter, SensitiveFormatter)
        assert cli_app._console_handler.formatter is cli_app._log_formatter
        for handler in cli_app._log_handlers:
            assert handler.formatter is cli_app._log_formatter


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
        """首个文件任务抛异常时，后续文件仍被处理（旧实现整批崩溃）。

        新增失败门控后：批次里有失败任务 → 进程 exit 1（供 CI 门控），
        但批次本身不被中断（两个文件都被处理）。
        """
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
        assert r.exit_code == 1, f"存在失败任务应 exit 1（门控），但批次不应中断: {r.output}"
        assert calls == files, "两个文件都应被处理"

    def test_all_passed_exits_zero(self, tmp_path, monkeypatch):
        """全部任务通过 → exit 0（门控工具成功时不应误报失败）。"""
        files = self._make_files(tmp_path, n=2)

        def fake_run_single_task(target_file, *args, **kwargs):
            return {"success": True, "file": target_file, "func": "all", "passed": True}

        monkeypatch.setattr(cli_app, "_run_single_task", fake_run_single_task)
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--json"])
        assert r.exit_code == 0, f"全部通过应 exit 0: {r.output}"

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


class TestRunParamValidation:
    """run 命令参数校验分支（此前 61% 覆盖中未触及的非法参数）。"""

    def test_parallel_zero_rejected(self, tmp_path):
        """--parallel=0 应被拦截（并发数必须 >0）。"""
        files = [str(tmp_path / "mod.py")]
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--parallel=0", "--json"])
        assert r.exit_code == 1
        assert "--parallel 必须大于 0" in r.output

    def test_max_iterations_zero_rejected(self, tmp_path):
        """--max-iterations=0 应被拦截（至少迭代 1 次）。"""
        files = [str(tmp_path / "mod.py")]
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--max-iterations=0", "--json"])
        assert r.exit_code == 1
        assert "--max-iterations 必须大于 0" in r.output

    def test_coverage_threshold_out_of_range_rejected(self, tmp_path):
        """--coverage-threshold 超出 [0,100] 应被拦截。"""
        files = [str(tmp_path / "mod.py")]
        (tmp_path / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--coverage-threshold=150", "--json"])
        assert r.exit_code == 1
        assert "必须在 0-100 范围内" in r.output

    def test_nonexistent_file_intercepted_by_click(self, tmp_path):
        """目标文件不存在时由 click.Path(exists=True) 在解析层拦截（exit 2），
        不会进入 app.py 的 expanded_files 空判分支。"""
        r = CliRunner().invoke(cli_app.cli, ["run", str(tmp_path / "no_such_file.py"), "--json"])
        assert r.exit_code == 2
        assert "does not exist" in r.output


class TestRunParallelJsonBoundaries:
    """run 命令 --parallel / --json / glob 展开的边界分支（1.5 覆盖率补强）。"""

    def _make_files(self, tmp_path, n: int = 2) -> list[str]:
        files = []
        for i in range(n):
            p = tmp_path / f"m{i}.py"
            p.write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
            files.append(str(p))
        return files

    def test_single_file_with_parallel_and_json_is_sequential(self, tmp_path, monkeypatch):
        """--parallel>1 但仅 1 个文件 → 走顺序分支（并发需 len(files)>1），仍产出纯 JSON。"""
        files = self._make_files(tmp_path, n=1)
        dispatch_calls: list[str] = []
        ok = {"success": True, "file": files[0], "func": "all", "passed": True, "coverage": 90.0}

        monkeypatch.setattr(cli_app, "_run_single_task", lambda *a, **k: ok)
        monkeypatch.setattr(cli_app, "_dispatch_parallel_tasks", lambda **kw: dispatch_calls.append("dispatch"))

        r = CliRunner().invoke(cli_app.cli, ["run", files[0], "--parallel=4", "--json"])
        assert r.exit_code == 0
        # 仅 1 文件不触发并发派发器（走顺序分支）
        assert dispatch_calls == []

    def test_parallel_gt1_multi_file_uses_dispatch(self, tmp_path, monkeypatch):
        """--parallel>1 且多文件 → 走 _dispatch_parallel_tasks（rich 不可用时的降级路径）。"""
        files = self._make_files(tmp_path, n=3)
        dispatch_calls: list[dict] = []
        ok = {"success": True, "file": files[0], "func": "all", "passed": True, "coverage": 90.0}

        def fake_dispatch(**kwargs):
            dispatch_calls.append(kwargs)
            kwargs["results"].append(ok)

        monkeypatch.setattr(cli_app, "_run_single_task", lambda *a, **k: ok)
        monkeypatch.setattr(cli_app, "_dispatch_parallel_tasks", fake_dispatch)
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)  # 强制降级路径

        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--parallel=2", "--json"])
        assert r.exit_code == 0
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["parallel"] == 2

    def test_glob_pattern_intercepted_by_click_exists_check(self, tmp_path):
        """glob 通配字符串被 click.Path(exists=True) 在解析层判为不存在（exit 2）。

        真实行为：click 的 exists 校验作用于字面路径（通配符本身不是真实文件），
        未进入命令体的 glob_module.glob 展开分支。shell 侧若已展开为具体文件，
        则字面路径真实存在，正常执行。此用例锁定该解析层拦截语义。
        """
        self._make_files(tmp_path, n=2)
        pattern = str(tmp_path / "m*.py")
        r = CliRunner().invoke(cli_app.cli, ["run", pattern, "--json"])
        assert r.exit_code == 2, f"通配符字面路径应被 click 拦截, 实际 exit={r.exit_code}"

    def test_all_passed_parallel_exits_zero(self, tmp_path, monkeypatch):
        """并发模式全部通过 → exit 0（门控工具成功语义）。"""
        files = self._make_files(tmp_path, n=2)
        ok = {"success": True, "file": files[0], "func": "all", "passed": True, "coverage": 90.0}

        def fake_task(target_file, *a, **kw):
            r = dict(ok)
            r["file"] = target_file
            return r

        monkeypatch.setattr(cli_app, "_run_single_task", fake_task)
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--parallel=2", "--json"])
        assert r.exit_code == 0

    def test_failed_task_in_parallel_exits_one(self, tmp_path, monkeypatch):
        """并发模式有失败任务 → exit 1（门控工具失败语义，与顺序分支一致）。"""
        files = self._make_files(tmp_path, n=2)

        def fake_task(target_file, *a, **kw):
            return {"success": True, "file": target_file, "func": "all", "passed": False, "coverage": 0.0}

        monkeypatch.setattr(cli_app, "_run_single_task", fake_task)
        monkeypatch.setattr(cli_app, "_rich_available", lambda: False)
        r = CliRunner().invoke(cli_app.cli, ["run", *files, "--parallel=2", "--json"])
        assert r.exit_code == 1
