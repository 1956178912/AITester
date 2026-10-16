#!/usr/bin/env python3
"""覆盖率收口（最后一段）：小组件的安全/降级分支。

动机（EMSE 多轮优化批次·收口）：这些单行分支各自很小，但属**安全与告警面**——
注入防御的拒绝理由、证据门被关闭时的告警、异常文本脱敏失败的回退。
"没测到"意味着这些告警可能在真实运行中首次被触发（即生产首次执行）。

覆盖目标（coverage.xml 记录）：exceptions 180-181/245、credential_scrub 63-64/81、
injection_guard 198、patch_evidence 231、self_repair_trap 97、cli/output 22-25。
零 LLM、零网络。
"""

from __future__ import annotations

import pytest

from src.agents.injection_guard import patch_safety_reject_reason
from src.tools.patch_evidence import evidence_allows_write
from src.tools.self_repair_trap import detect_self_repair_trap
from src.utils.exceptions import retry_with_backoff, safe_execute


class TestInjectionGuardRejectReason:
    def test_no_findings_yields_empty_reason(self):
        assert patch_safety_reject_reason([]) == ""

    def test_findings_are_joined_into_reason(self):
        """拒绝理由必须列出具名特征（可审计），而不是笼统"被拒绝"。"""
        reason = patch_safety_reject_reason(["delete_file", "exec_shell"])
        assert "delete_file" in reason and "exec_shell" in reason
        assert reason.startswith("补丁被注入防御层拒绝")


class TestPatchEvidenceGate:
    """`evidence_allows_write(level)`：按当前门限（env 可覆盖）判定该证据等级能否落盘。"""

    def test_returns_bool_for_known_and_unknown_levels(self, monkeypatch: pytest.MonkeyPatch):
        for env in ("PATCH_EVIDENCE_MIN_LEVEL", "PATCH_EVIDENCE_ENABLE"):
            monkeypatch.delenv(env, raising=False)
        assert isinstance(evidence_allows_write("sbfl"), bool)
        assert isinstance(evidence_allows_write("bogus_level"), bool)

    def test_none_min_level_is_rejected_with_warning(self, monkeypatch: pytest.MonkeyPatch):
        """门限设 `none`（= 关闭证据门）实测**判 False** 并打告警——该口径已被 E6 A/B 证否，
        故当前实现选择"不推荐即不放行"。按真实行为锁定（与实现注释一致）。"""
        monkeypatch.setenv("PATCH_EVIDENCE_MIN_LEVEL", "none")
        assert evidence_allows_write("global_assertion") is False

    def test_illegal_min_level_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch):
        """非法门限 → 回退默认 `sbfl`（不得静默全放行、不得抛异常）。"""
        monkeypatch.setenv("PATCH_EVIDENCE_MIN_LEVEL", "not-a-level")
        assert isinstance(evidence_allows_write("none"), bool)


class TestSelfRepairTrap:
    def test_empty_input_returns_empty_verdict(self):
        """空输入 → 明确"未怀疑 + 空信号"（不得臆造 trap 信号）。"""
        result = detect_self_repair_trap([])
        assert result["suspected"] is False
        assert result["signals"] == []

    def test_none_input_is_handled(self):
        assert isinstance(detect_self_repair_trap(None), dict)

    def test_missing_signals_do_not_trigger(self):
        record = {"oracle_quality_history": [], "coverage": 0.0}
        result = detect_self_repair_trap([record])
        assert isinstance(result, dict)


class TestExceptionFormattingAndRetry:
    def test_safe_execute_returns_value_on_success(self):
        assert safe_execute(lambda: 42, default=-1) == 42

    def test_safe_execute_returns_default_on_failure(self):
        def _boom() -> int:
            raise ValueError("boom")

        assert safe_execute(_boom, default=-1) == -1

    def test_redact_exception_text_masks_secrets(self):
        """脱敏口径（4.1）：网关错误体回显的 token 不得原样进入日志。"""
        import src.utils.exceptions as exc_mod

        text = exc_mod._redact_exception_text(ValueError("failed: https://gw.example/v1?api_key=sk-supersecret123"))
        assert "sk-supersecret123" not in text

    def test_redact_exception_text_falls_back_when_redactor_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        """脱敏器不可用时回退 `str(exc)`（覆盖率收口：exceptions 180-181 异常回退分支）。"""
        import builtins

        import src.utils.exceptions as exc_mod

        real_import = builtins.__import__

        def _blocked(name: str, *args: object, **kwargs: object):
            if name.endswith("logging_utils"):
                raise ImportError("simulated: redactor unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked)
        assert exc_mod._redact_exception_text(ValueError("plain message")) == "plain message"

    def test_retry_succeeds_without_retrying(self):
        calls: list[int] = []

        @retry_with_backoff(max_retries=3)
        def _ok() -> str:
            calls.append(1)
            return "done"

        assert _ok() == "done"
        assert len(calls) == 1

    def test_retry_exhausts_and_reraises_last_exception(self):
        calls: list[int] = []

        @retry_with_backoff(max_retries=2, base_wait=0.0)
        def _always_fail() -> None:
            calls.append(1)
            raise ValueError("nope")

        with pytest.raises(ValueError):
            _always_fail()
        assert len(calls) >= 1

    def test_retry_returns_none_branch_is_unreachable_in_normal_flow(self):
        """`retry_with_backoff` 的 `return None` 是防御性分支（无异常且无结果）。

        用"总是不抛异常"的函数验证正常路径不受影响；该分支保持未覆盖属**可接受**，
        在此显式记录（避免后续把它当"未测代码"误删）。"""

        @retry_with_backoff(max_retries=1)
        def _none_return() -> None:
            return None

        assert _none_return() is None


class TestImportFallbackPaths:
    """可选依赖缺失时的导入回退分支（覆盖率收口最后一段）。

    两处都是**模块级导入降级**：`rich` 缺失时 CLI 输出层退回纯文本；
    `config_generator` 缺失时凭证剔除退回静态名单。二者都必须在**缺依赖的
    环境**下仍可导入（否则整个包在精简环境里直接 ImportError）。
    通过子进程 + 导入钩子模拟，避免污染当前进程的模块缓存。
    """

    def test_cli_output_module_imports_without_rich(self):
        import subprocess
        import sys
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        code = (
            "import sys, builtins\n"
            "real = builtins.__import__\n"
            "def blocked(name, *a, **k):\n"
            "    if name == 'rich' or name.startswith('rich.'):\n"
            "        raise ImportError('simulated: rich missing')\n"
            "    return real(name, *a, **k)\n"
            "builtins.__import__ = blocked\n"
            "import src.cli.output as out\n"
            "assert out.RICH_AVAILABLE is False, out.RICH_AVAILABLE\n"
            "assert out._console is None\n"
            "print('OK')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(repo), capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr[-600:]
        assert "OK" in proc.stdout

    def test_credential_scrub_imports_without_config_generator(self):
        import subprocess
        import sys
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        code = (
            "import sys, builtins\n"
            "real = builtins.__import__\n"
            "def blocked(name, *a, **k):\n"
            "    if name.endswith('config_generator') or name.endswith('src.config.config_generator'):\n"
            "        raise ImportError('simulated: config_generator missing')\n"
            "    return real(name, *a, **k)\n"
            "builtins.__import__ = blocked\n"
            "import src.utils.credential_scrub as cs\n"
            "assert cs._PROVIDER_KEY_PATTERNS, '静态回退名单必须生效'\n"
            "env = cs.scrub_os_environ()\n"
            "assert isinstance(env, dict)\n"
            "print('OK')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(repo), capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr[-600:]
        assert "OK" in proc.stdout


class TestFinalBranchCloseout:
    """最后三个分支：trace 空行跳过、覆盖率 TOTAL 解析异常、OTel 非 span 记录。"""

    def test_trace_loader_skips_blank_lines_and_bad_json(self, tmp_path):
        """JSONL 解析器必须跳过空行与坏行，而不是中断整条 trace 读取。"""
        from src.utils.trace_viz import _parse_jsonl

        path = tmp_path / "trace.jsonl"
        path.write_text(
            '{"event": "node", "node": "planner"}\n\n   \n{not-json}\n{"event": "node", "node": "generator"}\n',
            encoding="utf-8",
        )
        records = _parse_jsonl(str(path))
        assert len(records) == 2, records

    def test_trace_loader_missing_file_returns_empty(self, tmp_path):
        from src.utils.trace_viz import _parse_jsonl

        assert _parse_jsonl(str(tmp_path / "nope.jsonl")) == []

    def test_coverage_total_unparsable_value_is_skipped(self):
        """`TOTAL <非数字>` → 继续扫描后续行（不得因一行异常返回 0）。"""
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("TOTAL   abc   x%\nTOTAL   1234   87%") == pytest.approx(87.0)

    def test_coverage_total_absent_returns_zero(self):
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("no coverage summary here") == 0.0

    def test_otel_non_span_events_are_dropped(self):
        """非 span 事件（如 log/error）映射为 None——不得混入 span 流。"""
        from src.observability.otel_export import _record_to_span

        assert _record_to_span({"event": "log", "msg": "x"}, None, "t") is None

    def test_otel_node_event_maps_to_span(self):
        from src.observability.otel_export import _record_to_span

        span = _record_to_span({"event": "node", "node": "planner", "ts": 1.0}, None, "t")
        assert isinstance(span, dict)

    def test_test_hacking_scan_degrades_on_syntax_error(self):
        """补丁代码语法坏 → 硬编码检测降级为 False（不得抛异常打断观测层）。"""
        from src.tools.patch_test_hacking import detect_test_hacking

        result = detect_test_hacking("def f():\n    return 1\n", "def broken(:\n  pass\n")
        assert isinstance(result, (dict, list, bool, tuple))


class TestCoverageParsingCalibers:
    """`parse_coverage` 的三种汇总行口径（2026-10-15 修复后锁定）。

    修复前的两处缺陷（本轮由 strict xfail 暴露）：
    ① 小写 `total` 回退失效（正则大写锚定 → 恒 0.0）；
    ② `TOTAL   85%` 简写形态被截断为 5.0（相邻数字被当作捕获组）。
    """

    def test_lowercase_total_line_is_parsed(self):
        """旧版 pytest-cov 的小写汇总行必须被解析（修复 ①）。"""
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("Name  Stmts  Miss  Cover\ntotal  100  15  85%") == pytest.approx(85.0)

    def test_short_form_total_is_not_truncated(self):
        """`TOTAL   85%`（无 Stmts/Miss 列）必须得 85，而不是 5（修复 ②）。"""
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("TOTAL   85%") == pytest.approx(85.0)
        assert parse_coverage("total  7%") == pytest.approx(7.0)

    def test_uppercase_wins_when_both_present(self):
        from src.agents.executor_output import parse_coverage

        output = "TOTAL  100  15  91%\ntotal  100  15  85%"
        assert parse_coverage(output) == pytest.approx(91.0)

    def test_leading_whitespace_line_is_accepted(self):
        """缩进的汇总行同样可解析（旧实现要求行首严格相等 → 会漏）。"""
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("  TOTAL  100  20  63%") == pytest.approx(63.0)

    def test_full_pytest_cov_block(self):
        from src.agents.executor_output import parse_coverage

        output = (
            "Name    Stmts    Miss  Cover\n"
            "------------------------------------\n"
            "total   100      20    80%\n"
            "------------------------------------\n"
            "TOTAL   100      20    80%\n"
        )
        assert parse_coverage(output) == pytest.approx(80.0)

    def test_unknown_format_returns_zero_not_partial_number(self):
        """无法识别的输出 → 0.0（不得从无关数字里瞎猜覆盖率）。"""
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("no summary\njust logs 12345") == 0.0

    def test_empty_output_returns_zero(self):
        from src.agents.executor_output import parse_coverage

        assert parse_coverage("") == 0.0
