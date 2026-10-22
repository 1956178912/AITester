"""BG（2026-10-21）：静态类型检查器"不可测量 ≠ 干净"收口锁。

缺陷族：`_run_mypy_findings` / `_run_pyright_findings` 在检查器未安装、
崩溃、超时、退出码异常、报告损坏时全部返回 `[]`，与"检查器正常跑完且
确实没有类型疑点"在返回值上完全一致；`mypy_findings_count=0` 同样把
"未启用 / 未安装 / 检查通过 / 检查失败"四种状态折成一个 0。下游只能
把"检查器故障"读成"无类型问题"（假干净）。

修复口径：两条后端函数接受 `outcome_sink`（与 MDO `_run_probe` 同模式），
每个返回路径记录 `{backend, status, reason}`；`type_repair_layer` 聚合为
`static_check_status` / `static_check_outcomes` 并写入 state 观测键。
"""

from __future__ import annotations

import builtins
import json
from unittest.mock import MagicMock, patch

import pytest

from src.graph.state import AITesterState, create_initial_state
from src.tools.type_repair import (
    _run_mypy_findings,
    _run_pyright_findings,
    type_repair_layer,
)

_DIAGNOSTIC = {
    "severity": "error",
    "rule": "reportUndefinedVariable",
    "message": "x is not defined",
    "range": {"start": {"line": 1}},
}


def _proc(stdout: str, *, returncode: int = 0, timed_out: bool = False) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = ""
    proc.returncode = returncode
    proc.timed_out = timed_out
    return proc


def _pyright_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
    monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")


class TestMypyOutcome:
    def test_disabled_records_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        sink: list[dict[str, object]] = []
        out = _run_mypy_findings("def f():\n    return 1\n", "def f():\n    return 1\n", outcome_sink=sink)
        assert out == []
        assert sink == [{"backend": "mypy", "status": "disabled", "reason": "type_check_disabled"}]

    def test_empty_input_records_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        sink: list[dict[str, object]] = []
        assert _run_mypy_findings("o", "   \n", outcome_sink=sink) == []
        assert sink[0]["status"] == "disabled"
        assert sink[0]["reason"] == "empty_input"

    def test_import_error_records_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name in {"mypy.api", "mypy"}:
                raise ImportError("mypy not installed")
            return real_import(name, *args, **kwargs)

        sink: list[dict[str, object]] = []
        with patch("builtins.__import__", side_effect=_import):
            out = _run_mypy_findings("o", "def f():\n    return 1\n", outcome_sink=sink)
        assert out == []
        assert sink[0]["status"] == "unavailable"
        assert sink[0]["reason"] == "mypy_not_installed"

    def test_fatal_exit_code_records_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        sink: list[dict[str, object]] = []
        with patch("mypy.api.run", return_value=(2, "", "error: cannot read file")):
            out = _run_mypy_findings("o", "def f():\n    return x\n", outcome_sink=sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "mypy_rc_2"

    def test_exception_records_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        sink: list[dict[str, object]] = []
        with patch("mypy.api.run", side_effect=RuntimeError("boom")):
            out = _run_mypy_findings("o", "def f():\n    return 1\n", outcome_sink=sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "mypy_exception"

    def test_errors_found_records_ok(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        out_text = "patched_code.py:2:1: error: Name 'x' is not defined [name-defined]\n"
        sink: list[dict[str, object]] = []
        with patch("mypy.api.run", return_value=(1, out_text, "")):
            findings = _run_mypy_findings("o", "def f():\n    return x\n", outcome_sink=sink)
        assert len(findings) == 1
        assert sink == [{"backend": "mypy", "status": "ok", "reason": ""}]

    def test_clean_exit_records_ok(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        sink: list[dict[str, object]] = []
        with patch("mypy.api.run", return_value=(0, "", "")):
            findings = _run_mypy_findings("o", "def f():\n    return 1\n", outcome_sink=sink)
        assert findings == []
        assert sink == [{"backend": "mypy", "status": "ok", "reason": ""}]


class TestPyrightOutcome:
    def _run(self, proc: MagicMock, sink: list[dict[str, object]]):
        with (
            patch("shutil.which", return_value="/usr/bin/pyright"),
            patch("src.utils.process_utils.run_with_timeout", return_value=proc),
        ):
            return _run_pyright_findings("o", "def f():\n    return x\n", outcome_sink=sink)

    def test_timeout_records_error(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc("", returncode=-9, timed_out=True), sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_timeout"

    @pytest.mark.parametrize("rc", [2, 3, -9])
    def test_unexpected_exit_code_records_error(self, monkeypatch: pytest.MonkeyPatch, rc: int):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc(json.dumps({"generalDiagnostics": [_DIAGNOSTIC]}), returncode=rc), sink)
        # 报告本身可解析时仍消费 findings（诊断不丢），但状态不得是 ok。
        assert len(out) == 1
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == f"pyright_rc_{rc}"

    def test_empty_output_records_error(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc("", returncode=0), sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_empty_output"

    def test_invalid_json_records_error(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc("not a json report", returncode=0), sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_invalid_json"

    def test_non_object_report_records_error(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc("[]", returncode=0), sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_invalid_json"

    def test_missing_diagnostics_key_records_error(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc(json.dumps({"version": "1.1.0"}), returncode=0), sink)
        assert out == []
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_missing_diagnostics"

    def test_clean_report_records_ok(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc(json.dumps({"generalDiagnostics": []}), returncode=0), sink)
        assert out == []
        assert sink == [{"backend": "pyright", "status": "ok", "reason": ""}]

    def test_reported_errors_record_ok(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        out = self._run(_proc(json.dumps({"generalDiagnostics": [_DIAGNOSTIC]}), returncode=1), sink)
        assert len(out) == 1
        assert sink == [{"backend": "pyright", "status": "ok", "reason": ""}]

    def test_text_fallback_keeps_finding_but_not_ok(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        sink: list[dict[str, object]] = []
        line = "path:2:3 - error: x not defined [reportUndefinedVariable]\n"
        out = self._run(_proc(line, returncode=0), sink)
        assert len(out) == 1  # 诊断不丢
        assert sink[0]["status"] == "error"
        assert sink[0]["reason"] == "pyright_invalid_json"

    def test_unavailable_records_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        _pyright_env(monkeypatch)
        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name == "pyright":
                raise ImportError("pyright-python not installed")
            return real_import(name, *args, **kwargs)

        sink: list[dict[str, object]] = []
        with patch("shutil.which", return_value=None), patch("builtins.__import__", side_effect=_import):
            out = _run_pyright_findings("o", "def f():\n    return 1\n", outcome_sink=sink)
        assert out == []
        assert sink[0]["status"] == "unavailable"
        assert sink[0]["reason"] == "pyright_not_found"


class TestLayerAggregation:
    def _fake_backend(self, status: str, reason: str, findings: list[dict] | None = None):
        def _fake(original, patched, file_path="patched_code.py", outcome_sink=None):
            if outcome_sink is not None:
                outcome_sink.append({"backend": "pyright", "status": status, "reason": reason})
            return list(findings or [])

        return _fake

    def test_layer_reports_error_when_only_checker_failed(self, monkeypatch: pytest.MonkeyPatch):
        """核心缺陷锁：检查器崩溃时 findings=[]/count=0，但状态必须是 error。"""
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        monkeypatch.delenv("TYPE_REPAIR_LLM_ENABLE", raising=False)
        with patch("mypy.api.run", side_effect=RuntimeError("boom")):
            result = type_repair_layer("def f():\n    return 1\n", "def f():\n    return 1\n")
        assert result["findings"] == []
        assert result["mypy_findings_count"] == 0
        assert result["static_check_status"] == "error"
        assert result["static_check_outcomes"] == [{"backend": "mypy", "status": "error", "reason": "mypy_exception"}]

    def test_layer_warns_on_unmeasurable(self, monkeypatch: pytest.MonkeyPatch, caplog):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        with (
            patch("mypy.api.run", side_effect=RuntimeError("boom")),
            caplog.at_level("WARNING", logger="src.tools.type_repair"),
        ):
            type_repair_layer("def f():\n    return 1\n", "def f():\n    return 1\n")
        assert "静态类型层不可测量" in caplog.text

    def test_layer_pyright_error_falls_back_to_ok_mypy(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        with (
            patch(
                "src.tools.type_repair._run_pyright_findings",
                side_effect=self._fake_backend("error", "pyright_rc_3"),
            ),
            patch(
                "src.tools.type_repair._run_mypy_findings",
                side_effect=lambda *a, outcome_sink=None, **k: (
                    outcome_sink.append({"backend": "mypy", "status": "ok", "reason": ""}) or []
                ),
            ),
        ):
            result = type_repair_layer("def f():\n    return 1\n", "def f():\n    return 1\n")
        assert result["static_check_status"] == "ok"
        assert [o["backend"] for o in result["static_check_outcomes"]] == ["pyright", "mypy"]
        assert [o["status"] for o in result["static_check_outcomes"]] == ["error", "ok"]

    def test_layer_disabled_switch_records_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        result = type_repair_layer("def f():\n    return 1\n", "def f():\n    return 1\n")
        assert result["static_check_status"] == "disabled"
        assert result["static_check_outcomes"][0]["status"] == "disabled"


class TestStateObservationKeys:
    def test_state_declares_static_check_keys(self):
        assert "static_check_status" in AITesterState.__annotations__
        assert "static_check_outcomes" in AITesterState.__annotations__

    def test_initial_state_defaults_to_none(self):
        state = create_initial_state("bg_state", "m.py", "x = 1\n", 1)
        assert state["static_check_status"] is None
        assert state["static_check_outcomes"] is None
