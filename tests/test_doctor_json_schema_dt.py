"""DT 轮：doctor `--json` 三条出口路径（成功 / 用法错误 / 内部异常）schema 同构。

改前实测：成功与 `--groups " , "` 用法错误都输出 12 个键，而 `_doctor_build_report`
内部异常时只输出 ``{"schema", "ok", "error", "exit_code"}`` 4 个键——崩溃报告缺
``checks`` / ``check_summary`` / ``matrix`` / ``conclusion`` / ``command`` 等 9 个键，
``jq -e '.conclusion == "pass"'`` 在崩溃时不是判假而是直接报「取不到键」；成功报告
反过来缺 ``error``，消费方仍要按「键是否存在」分支，与 DS 轮（任务结果面）同族的
「JSON 面在失败路径换了一套 schema」。

本轮的判定口径：三条路径键集合逐键相同；崩溃时**未知**的聚合值记 ``null``
（不是 0 / 空列表——那会把「没跑」说成「跑了且全过」）；异常原因脱敏进 ``error``；
``matrix.status`` 记 ``internal`` 并保留 ``command`` / ``python`` / ``strict`` 上下文。
"""

from __future__ import annotations

import json
import os
import re

import pytest
from click.testing import CliRunner

import src.cli.app as cli_app

REPORT_KEYS = {
    "schema",
    "generated_at",
    "cwd",
    "command",
    "python",
    "checks",
    "check_summary",
    "matrix",
    "conclusion",
    "ok",
    "strict",
    "exit_code",
    "error",
}

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{4})?$")


def _probe_ok() -> dict[str, object]:
    return {
        "status": "ok",
        "report": {
            "probes": [{"name": "p1", "group": "budget", "status": "pass", "detail": "ok"}],
            "load_errors": [],
        },
        "duration_s": 0.1,
        "returncode": 0,
        "detail": "",
        "stderr_tail": "",
    }


def _one_check() -> list[dict[str, object]]:
    return [cli_app._doctor_check("python", "Python 版本", "pass", "ok")]


@pytest.fixture()
def success_invoke(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", lambda groups, timeout_s: _probe_ok())
    monkeypatch.setattr(cli_app, "_doctor_collect_checks", _one_check)

    def _invoke(*args: str):
        return CliRunner().invoke(cli_app.cli, ["doctor", "--json", *args])

    return _invoke


@pytest.fixture()
def crash_invoke(monkeypatch: pytest.MonkeyPatch):
    def _boom(groups: list[str], timeout_s: int) -> dict[str, object]:
        raise RuntimeError("doctor boom sk-dt-placeholder-0123456789abcdef")

    monkeypatch.setattr(cli_app, "_doctor_collect_checks", _one_check)
    monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", _boom)

    def _invoke(*args: str):
        return CliRunner().invoke(cli_app.cli, ["doctor", "--json", *args])

    return _invoke


def _parse(result) -> dict:
    return json.loads(result.stdout)


class TestKeySetIsomorphism:
    def test_success_report_carries_error_null(self, success_invoke) -> None:
        result = success_invoke()
        assert result.exit_code == 0
        report = _parse(result)
        assert set(report) == REPORT_KEYS
        assert report["error"] is None

    def test_crash_report_has_same_key_set(self, crash_invoke) -> None:
        result = crash_invoke()
        assert result.exit_code == 1
        report = _parse(result)
        assert set(report) == REPORT_KEYS

    def test_usage_error_report_has_same_key_set(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json", "--groups", " , "])
        assert result.exit_code == 2
        report = _parse(result)
        assert set(report) == REPORT_KEYS
        assert report["error"] is None

    def test_three_paths_share_identical_keys(self, success_invoke, crash_invoke) -> None:
        success = _parse(success_invoke())
        crash = _parse(crash_invoke())
        usage = _parse(CliRunner().invoke(cli_app.cli, ["doctor", "--json", "--groups", " , "]))
        assert set(success) == set(crash) == set(usage) == REPORT_KEYS


class TestCrashReportContent:
    def test_crash_conclusion_and_exit_code(self, crash_invoke) -> None:
        result = crash_invoke()
        report = _parse(result)
        assert report["ok"] is False
        assert report["conclusion"] == "fail"
        assert report["exit_code"] == 1
        assert report["schema"] == cli_app._DOCTOR_SCHEMA

    def test_crash_error_is_masked(self, crash_invoke) -> None:
        report = _parse(crash_invoke())
        assert "RuntimeError" in report["error"]
        assert "doctor boom" in report["error"]
        assert "sk-dt-placeholder-0123456789abcdef" not in json.dumps(report, ensure_ascii=False)

    def test_crash_unknown_aggregates_are_null_not_zero(self, crash_invoke) -> None:
        report = _parse(crash_invoke())
        assert report["checks"] is None
        assert report["check_summary"] is None
        matrix = report["matrix"]
        assert matrix["status"] == "internal"
        for key in ("duration_s", "returncode", "summary", "groups", "failures", "skips", "load_errors"):
            assert matrix[key] is None, f"{key} 未知时必须记 null，不得用 0/[] 冒充实测"
        assert matrix["probe_report"] is None
        assert matrix["stderr_tail"] == ""

    def test_crash_matrix_detail_carries_reason(self, crash_invoke) -> None:
        report = _parse(crash_invoke())
        detail = report["matrix"]["detail"]
        assert "doctor 内部异常" in detail
        assert "RuntimeError" in detail
        assert "sk-dt-placeholder-0123456789abcdef" not in detail

    def test_crash_keeps_command_context(self, crash_invoke) -> None:
        report = _parse(crash_invoke("--groups", "budget", "--groups", "cache,budget", "--timeout", "45"))
        assert report["command"] == {
            "groups": ["budget", "cache"],
            "timeout_s": 45,
            "strict": False,
            "zero_llm": True,
        }

    def test_crash_keeps_strict_flag_and_still_fails(self, crash_invoke) -> None:
        result = crash_invoke("--strict")
        report = _parse(result)
        assert report["strict"] is True
        assert report["exit_code"] == 1
        assert result.exit_code == 1

    def test_crash_report_still_carries_environment_context(self, crash_invoke) -> None:
        report = _parse(crash_invoke())
        assert _TIMESTAMP_RE.match(report["generated_at"])
        assert report["cwd"] == os.getcwd()
        assert report["python"]["version"].count(".") == 2

    def test_crash_json_is_single_document(self, crash_invoke) -> None:
        result = crash_invoke()
        assert result.stderr == ""
        assert len(json.loads(result.stdout)) == len(REPORT_KEYS)


class TestHumanModeCrash:
    def test_human_crash_reason_on_stderr_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(groups: list[str], timeout_s: int) -> dict[str, object]:
            raise RuntimeError("doctor boom")

        monkeypatch.setattr(cli_app, "_doctor_collect_checks", _one_check)
        monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", _boom)
        result = CliRunner().invoke(cli_app.cli, ["doctor"])
        assert result.exit_code == 1
        assert "doctor 执行失败" in result.stderr
        assert "doctor boom" in result.stderr
        assert "doctor 执行失败" not in result.stdout
