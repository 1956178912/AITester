"""`main.py doctor`（P-3）零 LLM 自检命令回归测试。

覆盖分层（全部零网络 / 零 LLM / 不真实跑探针矩阵）：
1. 命令注册/help（doctor 在 group 帮助与自身 --help 可见）；
2. 环境检查各分支（Python 版本 / 可选依赖缺失 / LLM 端点空与不完整 / 数据集
   可加载性 / 内核沙箱 supported/unsupported / git HEAD+dirty）；
3. 探针矩阵聚合（全 pass → 0、含 fail → 1、error → 1、strict+skip → 1）；
4. CLI 行为（--json stdout 纯 JSON、schema 与探针报告兼容、--groups 透传、
   子进程超时/坏 JSON fail-closed）；
5. 密钥不泄漏（构造假 LLM_N_API_KEY 环境变量，断言 human/JSON 输出均不含其值）。
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app

#: 真实矩阵子进程入口（autouse fixture 会用桩替换；本文件捕获原始引用供子进程用例使用）
_REAL_RUN_PROBE_MATRIX = cli_app._doctor_run_probe_matrix


def _check(name: str = "check", status: str = "pass", detail: str = "ok") -> dict[str, Any]:
    return {"name": name, "label": name, "status": status, "detail": detail, "evidence": {}}


def _probe_report(
    rows: list[dict[str, Any]] | None = None,
    *,
    load_errors: list[str] | None = None,
) -> dict[str, Any]:
    rows = rows or [{"name": "probe-a", "group": "budget", "status": "pass", "detail": "ok", "requires_llm": False}]
    summary = {"pass": 0, "fail": 0, "skip": 0, "error": 0}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    return {
        "schema": "e2e_probe_report/1",
        "include_llm": False,
        "probes": rows,
        "summary": summary,
        "load_errors": load_errors or [],
    }


def _probe_result_ok(report: dict[str, Any] | None = None, duration: float = 1.0) -> dict[str, Any]:
    return {
        "status": "ok",
        "report": report if report is not None else _probe_report(),
        "duration_s": duration,
        "returncode": 0,
        "detail": "",
        "stderr_tail": "",
    }


@pytest.fixture(autouse=True)
def _stub_doctor_heavy_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI 级用例默认不跑真实探针矩阵/环境检查（各用例可覆盖）。

    doctor 的真实矩阵入口由专门用例单测；这里保证其余用例快速、确定性、
    无网络/无重依赖 import。
    """
    monkeypatch.setattr(
        cli_app,
        "_doctor_collect_checks",
        lambda: [_check("python", "pass", "Python 3.14.6"), _check("git", "warn", "工作树有 1 项未提交改动")],
    )
    monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", lambda groups, timeout_s: _probe_result_ok())


# ─────────────────────────── 1. 命令注册 ───────────────────────────


class TestDoctorRegistration:
    def test_doctor_visible_in_group_help(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output
        assert "零 LLM 自检" in result.output

    def test_doctor_help_lists_all_options(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--help"])
        assert result.exit_code == 0
        for option in ("--json", "--groups", "--timeout", "--strict"):
            assert option in result.output

    def test_timeout_rejects_below_range(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--timeout", "1"])
        assert result.exit_code == 2  # click IntRange(min=5) 参数校验失败


# ─────────────────────────── 2. 环境检查分支 ───────────────────────────


class TestPythonCheck:
    def test_supported_version_pass(self) -> None:
        check = cli_app._doctor_check_python((3, 14, 6))
        assert check["status"] == "pass"
        assert "3.14.6" in check["detail"]

    def test_legacy_version_warn(self) -> None:
        check = cli_app._doctor_check_python((3, 11, 9))
        assert check["status"] == "warn"
        assert "3.12" in check["detail"]

    def test_unsupported_version_fail(self) -> None:
        check = cli_app._doctor_check_python((3, 8, 18))
        assert check["status"] == "fail"


class TestOptionalDepsCheck:
    def test_all_available_pass(self) -> None:
        check = cli_app._doctor_check_optional_deps(find_spec=lambda module: object())
        assert check["status"] == "pass"

    def test_missing_dependency_warn_with_install_hint(self) -> None:
        check = cli_app._doctor_check_optional_deps(find_spec=lambda module: None if module == "z3" else object())
        assert check["status"] == "warn"
        assert "z3" in check["detail"]
        assert "pip install z3-solver" in check["detail"]
        assert check["evidence"]["missing"][0]["module"] == "z3"

    def test_find_spec_exception_treated_missing(self) -> None:
        def _boom(module: str) -> Any:
            raise ValueError(module)

        check = cli_app._doctor_check_optional_deps(find_spec=_boom)
        assert check["status"] == "warn"
        assert len(check["evidence"]["missing"]) == len(cli_app._DOCTOR_OPTIONAL_DEPS)


class TestLlmEndpointCheck:
    def test_no_endpoint_warn_but_zero_llm_ok(self) -> None:
        check = cli_app._doctor_check_llm_endpoints(environ={})
        assert check["status"] == "warn"
        assert check["evidence"]["configured"] == 0
        assert "零 LLM 自检不受影响" in check["detail"]

    def test_complete_endpoint_pass(self) -> None:
        environ = {
            "LLM_1_API_KEY": "sk-fake-should-never-print",
            "LLM_1_BASE_URL": "https://api.example.invalid/v1",
            "LLM_1_MODEL_NAME": "fake-model",
        }
        check = cli_app._doctor_check_llm_endpoints(environ=environ)
        assert check["status"] == "pass"
        assert check["evidence"]["configured"] == 1
        assert "sk-fake-should-never-print" not in json.dumps(check, ensure_ascii=False)

    def test_incomplete_endpoint_reported_by_index_only(self) -> None:
        environ = {"LLM_2_API_KEY": "sk-fake-partial-value"}
        check = cli_app._doctor_check_llm_endpoints(environ=environ)
        assert check["status"] == "warn"
        assert check["evidence"]["incomplete_indices"] == [2]
        assert "sk-fake-partial-value" not in json.dumps(check, ensure_ascii=False)


class TestDatasetCheck:
    def test_all_loaded_pass(self) -> None:
        sizes = {"examples": 3, "quixbugs": 50, "ult": 200}

        class _Ds:
            def __init__(self, size: int) -> None:
                self.size = size
                self.tasks: list[Any] = []

        check = cli_app._doctor_check_datasets(load_dataset_fn=lambda name: _Ds(sizes[name]))
        assert check["status"] == "pass"
        assert check["evidence"]["sizes"] == sizes

    def test_quixbugs_missing_warn(self) -> None:
        class _Ds:
            def __init__(self, size: int) -> None:
                self.size = size
                self.tasks: list[Any] = []

        sizes = {"examples": 3, "quixbugs": 0, "ult": 0}
        check = cli_app._doctor_check_datasets(load_dataset_fn=lambda name: _Ds(sizes[name]))
        assert check["status"] == "warn"
        assert "AITESTER_QUIXBUGS_DATA" in check["detail"]

    def test_examples_missing_fail(self) -> None:
        class _Ds:
            def __init__(self, size: int) -> None:
                self.size = size
                self.tasks: list[Any] = []

        sizes = {"examples": 0, "quixbugs": 50, "ult": 0}
        check = cli_app._doctor_check_datasets(load_dataset_fn=lambda name: _Ds(sizes[name]))
        assert check["status"] == "fail"

    def test_loader_exception_degrades_without_crash(self) -> None:
        class _Ds:
            def __init__(self, size: int) -> None:
                self.size = size
                self.tasks: list[Any] = []

        def _load(name: str) -> Any:
            if name == "ult":
                raise ImportError("datasets missing")
            return _Ds(50)

        check = cli_app._doctor_check_datasets(load_dataset_fn=_load)
        assert check["status"] == "pass"
        assert "ImportError" in check["detail"]


class TestKernelSandboxCheck:
    def test_supported_pass_with_backends(self) -> None:
        check = cli_app._doctor_check_kernel_sandbox(
            supported=True, capabilities={"platform": "darwin", "backends": ["seatbelt"]}
        )
        assert check["status"] == "pass"
        assert "seatbelt" in check["detail"]

    def test_unsupported_warn_explicit_degrade(self) -> None:
        check = cli_app._doctor_check_kernel_sandbox(
            supported=False, capabilities={"platform": "windows", "backends": []}
        )
        assert check["status"] == "warn"
        assert "fail-closed" in check["detail"]


class TestGitCheck:
    class _Proc:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def test_clean_tree_pass(self) -> None:
        out = {"rev-parse": self._Proc(0, "14a9662\n"), "status": self._Proc(0, "")}
        check = cli_app._doctor_check_git(runner=lambda cmd, **kwargs: out[cmd[1]])
        assert check["status"] == "pass"
        assert check["evidence"]["head"] == "14a9662"

    def test_dirty_tree_warn(self) -> None:
        out = {"rev-parse": self._Proc(0, "14a9662\n"), "status": self._Proc(0, " M a.py\n?? b.py\n")}
        check = cli_app._doctor_check_git(runner=lambda cmd, **kwargs: out[cmd[1]])
        assert check["status"] == "warn"
        assert check["evidence"]["dirty_lines"] == 2

    def test_not_git_repo_warn(self) -> None:
        check = cli_app._doctor_check_git(runner=lambda cmd, **kwargs: self._Proc(128, "", "not a git repo"))
        assert check["status"] == "warn"
        assert "非 git 工作树" in check["detail"]

    def test_runner_exception_warn(self) -> None:
        def _boom(cmd: list[str], **kwargs: Any) -> Any:
            raise FileNotFoundError("git")

        check = cli_app._doctor_check_git(runner=_boom)
        assert check["status"] == "warn"
        assert check["evidence"]["available"] is False


# ─────────────────────────── 3. 矩阵聚合与退出码 ───────────────────────────


class TestMatrixAggregation:
    def _build(self, probe_result: dict[str, Any], *, strict: bool = False, checks: list[dict[str, Any]] | None = None):
        return cli_app._doctor_build_report(
            groups=[],
            timeout_s=30,
            strict=strict,
            checks=checks if checks is not None else [_check("python", "pass")],
            probe_result=probe_result,
        )

    def test_all_pass_exit_zero(self) -> None:
        report = self._build(_probe_result_ok())
        assert report["ok"] is True
        assert report["exit_code"] == 0
        assert report["matrix"]["summary"]["pass"] == 1

    def test_fail_row_exit_one(self) -> None:
        rows = [{"name": "p1", "group": "budget", "status": "fail", "detail": "boom", "requires_llm": False}]
        report = self._build(_probe_result_ok(_probe_report(rows)))
        assert report["ok"] is False
        assert report["exit_code"] == 1
        assert report["matrix"]["failures"][0]["name"] == "p1"
        assert report["conclusion"] == "fail"

    def test_error_row_exit_one(self) -> None:
        rows = [{"name": "p1", "group": "budget", "status": "error", "detail": "timeout", "requires_llm": False}]
        report = self._build(_probe_result_ok(_probe_report(rows)))
        assert report["exit_code"] == 1

    def test_probe_subprocess_error_fail_closed(self) -> None:
        report = self._build(
            {
                "status": "error",
                "report": None,
                "duration_s": 0.1,
                "returncode": 2,
                "detail": "no json",
                "stderr_tail": "x",
            }
        )
        assert report["exit_code"] == 1
        assert report["matrix"]["status"] == "error"
        assert report["matrix"]["summary"]["error"] == 1

    def test_timeout_fail_closed(self) -> None:
        report = self._build(
            {
                "status": "timeout",
                "report": None,
                "duration_s": 5.0,
                "returncode": 124,
                "detail": "超时",
                "stderr_tail": "",
            }
        )
        assert report["exit_code"] == 1
        assert "超时" in report["matrix"]["detail"]

    def test_skip_only_non_strict_exit_zero(self) -> None:
        rows = [{"name": "p1", "group": "budget", "status": "skip", "detail": "llm off", "requires_llm": True}]
        report = self._build(_probe_result_ok(_probe_report(rows)), strict=False)
        assert report["exit_code"] == 0

    def test_skip_only_strict_exit_one(self) -> None:
        rows = [{"name": "p1", "group": "budget", "status": "skip", "detail": "llm off", "requires_llm": True}]
        report = self._build(_probe_result_ok(_probe_report(rows)), strict=True)
        assert report["exit_code"] == 1

    def test_warn_check_non_strict_zero_strict_one(self) -> None:
        checks = [_check("git", "warn", "dirty")]
        assert self._build(_probe_result_ok(), strict=False, checks=checks)["exit_code"] == 0
        assert self._build(_probe_result_ok(), strict=True, checks=checks)["exit_code"] == 1

    def test_groups_parsing(self) -> None:
        parsed = cli_app._doctor_parse_groups(("budget,executor", "cache", "budget", " "))
        assert parsed == ["budget", "executor", "cache"]


# ─────────────────────────── 4. CLI 行为（--json/--groups/失败路径） ───────────────────────────


class TestDoctorCli:
    def test_json_output_is_pure_json(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)  # stdout 纯 JSON（无其它文本）
        assert report["schema"] == cli_app._DOCTOR_SCHEMA
        assert "AITester Doctor" not in result.output
        assert report["matrix"]["status"] == "ok"
        assert isinstance(report["matrix"]["probe_report"], dict)

    def test_json_contains_all_sections(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json"])
        report = json.loads(result.output)
        for key in ("checks", "check_summary", "matrix", "conclusion", "exit_code", "ok", "command"):
            assert key in report
        assert report["command"]["zero_llm"] is True

    def test_human_output_has_icons_and_conclusion(self) -> None:
        result = CliRunner().invoke(cli_app.cli, ["doctor"])
        assert result.exit_code == 0
        assert "AITester Doctor — 零 LLM 自检" in result.output
        assert "结论" in result.output
        assert "✅" in result.output
        assert "功能矩阵（零 LLM 子集" in result.output

    def test_fail_matrix_exit_one_and_human_detail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [
            {"name": "executor-local", "group": "executor", "status": "fail", "detail": "boom", "requires_llm": False}
        ]
        monkeypatch.setattr(
            cli_app, "_doctor_run_probe_matrix", lambda groups, timeout_s: _probe_result_ok(_probe_report(rows))
        )
        result = CliRunner().invoke(cli_app.cli, ["doctor"])
        assert result.exit_code == 1
        assert "失败明细" in result.output
        assert "executor-local" in result.output

    def test_strict_skip_exit_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [{"name": "p1", "group": "budget", "status": "skip", "detail": "llm off", "requires_llm": True}]
        monkeypatch.setattr(
            cli_app, "_doctor_run_probe_matrix", lambda groups, timeout_s: _probe_result_ok(_probe_report(rows))
        )
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--strict", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["exit_code"] == 1

    def test_groups_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _fake(groups: list[str], timeout_s: int) -> dict[str, Any]:
            captured["groups"] = groups
            captured["timeout"] = timeout_s
            return _probe_result_ok()

        monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", _fake)
        result = CliRunner().invoke(
            cli_app.cli, ["doctor", "--json", "--groups", "budget,executor", "--groups", "cache", "--timeout", "30"]
        )
        assert result.exit_code == 0
        assert captured["groups"] == ["budget", "executor", "cache"]
        assert captured["timeout"] == 30

    def test_matrix_timeout_json_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cli_app,
            "_doctor_run_probe_matrix",
            lambda groups, timeout_s: {
                "status": "timeout",
                "report": None,
                "duration_s": 5.0,
                "returncode": 124,
                "detail": f"探针矩阵执行超时（>{timeout_s}s）",
                "stderr_tail": "",
            },
        )
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json"])
        assert result.exit_code == 1
        report = json.loads(result.output)
        assert report["matrix"]["status"] == "timeout"
        assert report["exit_code"] == 1

    def test_doctor_internal_exception_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kwargs: Any) -> Any:
            raise RuntimeError("doctor boom")

        monkeypatch.setattr(cli_app, "_doctor_build_report", _boom)
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "doctor boom" in payload["error"]


# ─────────────────────────── 5. 密钥不泄漏 ───────────────────────────


class TestNoSecretLeak:
    def test_json_output_never_contains_fake_llm_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_key = "sk-doctor-fake-key-0123456789abcdef"
        monkeypatch.setenv("LLM_1_API_KEY", fake_key)
        monkeypatch.setenv("LLM_1_BASE_URL", "https://api.example.invalid/v1")
        monkeypatch.setenv("LLM_1_MODEL_NAME", "fake-model")
        monkeypatch.setattr(cli_app, "_doctor_collect_checks", lambda: [cli_app._doctor_check_llm_endpoints()])
        result = CliRunner().invoke(cli_app.cli, ["doctor", "--json"])
        assert result.exit_code == 0
        assert fake_key not in result.output
        report = json.loads(result.output)
        assert report["checks"][0]["evidence"]["configured"] == 1

    def test_human_output_never_contains_fake_llm_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_key = "sk-doctor-fake-key-human-9876543210"
        monkeypatch.setenv("LLM_1_API_KEY", fake_key)
        monkeypatch.setenv("LLM_1_BASE_URL", "https://api.example.invalid/v1")
        monkeypatch.setenv("LLM_1_MODEL_NAME", "fake-model")
        monkeypatch.setattr(cli_app, "_doctor_collect_checks", lambda: [cli_app._doctor_check_llm_endpoints()])
        result = CliRunner().invoke(cli_app.cli, ["doctor"])
        assert result.exit_code == 0
        assert fake_key not in result.output


# ─────────────────────────── 6. 矩阵子进程调用（cmd/env/超时/坏 JSON） ───────────────────────────


class TestProbeSubprocessInvocation:
    @pytest.fixture(autouse=True)
    def _use_real_matrix_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """本类直接单测真实矩阵子进程入口（覆盖 autouse 的桩）。"""
        monkeypatch.setattr(cli_app, "_doctor_run_probe_matrix", _REAL_RUN_PROBE_MATRIX)

    def test_cmd_groups_and_force_zero_llm(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        captured: dict[str, Any] = {}

        def _fake_run(cmd: list[str], **kwargs: Any) -> Any:
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env") or {}
            captured["timeout"] = kwargs.get("timeout")
            json_path = cmd[cmd.index("--json-out") + 1]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(_probe_report(), f)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setenv("AITESTER_E2E_LLM", "true")  # 外部误设也必须被 doctor 剥掉
        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = cli_app._doctor_run_probe_matrix(["budget", "executor"], 30)
        assert result["status"] == "ok"
        cmd = captured["cmd"]
        assert cmd[1].endswith("scripts/tools/e2e_probe.py")
        assert cmd[2:4] == ["--all", "--json-out"]
        assert cmd.count("--group") == 2
        assert "AITESTER_E2E_LLM" not in captured["env"]
        assert captured["env"]["AITESTER_LLM_CACHE"] == "0"
        assert captured["timeout"] == 30

    def test_subprocess_timeout_returns_timeout_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _timeout(cmd: list[str], **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 5)

        monkeypatch.setattr(subprocess, "run", _timeout)
        result = cli_app._doctor_run_probe_matrix([], 5)
        assert result["status"] == "timeout"
        assert result["returncode"] == 124

    def test_missing_json_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_run(cmd: list[str], **kwargs: Any) -> Any:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = cli_app._doctor_run_probe_matrix([], 30)
        assert result["status"] == "error"
        assert "未产出可解析 JSON" in result["detail"]

    def test_corrupt_json_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_run(cmd: list[str], **kwargs: Any) -> Any:
            json_path = cmd[cmd.index("--json-out") + 1]
            with open(json_path, "w", encoding="utf-8") as f:
                f.write("{not-json")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = cli_app._doctor_run_probe_matrix([], 30)
        assert result["status"] == "error"

    def test_oserror_start_failure_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(cmd: list[str], **kwargs: Any) -> Any:
            raise OSError("exec failed")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = cli_app._doctor_run_probe_matrix([], 30)
        assert result["status"] == "error"
        assert "无法启动探针子进程" in result["detail"]
