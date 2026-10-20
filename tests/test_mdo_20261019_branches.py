"""覆盖率补口：`mdo.py` 的探针/执行失败与不可测分支（2026-10-19）。

目标：把"子进程超时 / 进程异常 / 无输出 / 不可解析 / 基线不可测 / 变异体
执行不可判定"等 fail-closed 路径固化为契约。所有子进程入口均以
monkeypatch 注入 `CompletedProcess`，不启动真实 pytest，测试快速且确定性。

零 LLM、零网络；`compute_mdo` 的测试只 mock 执行/探针两个边界，指标计算
仍走真实代码路径。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.measurement import mdo
from src.utils import process_utils
from src.utils.process_utils import CompletedProcess


class _M:
    """最小变异体替身（与 test_mdo_metrics 同口径）。"""

    def __init__(self, code: str, mutant_type: str = "probe") -> None:
        self.code = code
        self.mutant_type = mutant_type
        self.description = mutant_type
        self.line_no = 1


_GREEN = mdo.TestRunResult(0, "", 0, 0, True)


def _base_args(mutants: list[_M]) -> dict[str, object]:
    return {
        "base_code": "def f():\n    return 1\n",
        "test_code": "from m import f\n\ndef test_f():\n    assert f() == 1\n",
        "module_name": "m",
        "mutants": mutants,
        "timeout_seconds": 1,
    }


def _completed(returncode: int = 0, *, stdout: str = "", stderr: str = "", timed_out: bool = False) -> CompletedProcess:
    return CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr, timed_out=timed_out)


class TestPoolFloor:
    def test_alpha_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            mdo.pool_floor(0.10, 1.0)


class TestLoadTestOutcomeReport:
    def test_non_list_payload_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "report.json"
        path.write_text("{}", encoding="utf-8")
        assert mdo._load_test_outcome_report(str(path)) is None

    def test_non_dict_items_are_filtered(self, tmp_path: Path) -> None:
        path = tmp_path / "report.json"
        path.write_text(json.dumps([{"outcome": "failed"}, 2]), encoding="utf-8")
        assert mdo._load_test_outcome_report(str(path)) == [{"outcome": "failed"}]

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert mdo._load_test_outcome_report(str(tmp_path / "missing.json")) is None


class TestExecutionErrorClassification:
    @pytest.mark.parametrize(
        ("rc", "output"),
        [(-9, ""), (2, ""), (5, ""), (3, ""), (1, "errors during collection")],
    )
    def test_abnormal_termination_is_execution_error(self, rc: int, output: str) -> None:
        assert mdo._is_execution_error(rc, output) is True

    def test_plain_assertion_failure_is_not_execution_error(self) -> None:
        assert mdo._is_execution_error(1, "assert f() == 2") is False


class TestRunProbeFailures:
    def test_timeout_marks_non_terminating(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(process_utils, "run_with_timeout", lambda *_a, **_k: _completed(-9, timed_out=True))
        sink: list[mdo.ProbeOutcome] = []
        assert mdo._run_probe("x = 1\n", "m", 1, outcome_sink=sink) is None
        assert sink[-1].timed_out is True
        assert sink[-1].invalid_reason == "probe_timeout"

    def test_nonzero_returncode_is_probe_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(process_utils, "run_with_timeout", lambda *_a, **_k: _completed(2, stderr="boom"))
        sink: list[mdo.ProbeOutcome] = []
        assert mdo._run_probe("x = 1\n", "m", 1, outcome_sink=sink) is None
        assert sink[-1].invalid_reason == "probe_rc_2"

    def test_execution_exception_is_probe_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*_a: object, **_k: object) -> CompletedProcess:
            raise RuntimeError("boom")

        monkeypatch.setattr(process_utils, "run_with_timeout", _boom)
        sink: list[mdo.ProbeOutcome] = []
        assert mdo._run_probe("x = 1\n", "m", 1, outcome_sink=sink) is None
        assert sink[-1].invalid_reason == "probe_exception"


class TestRunTestsOnCodeFailures:
    def test_timeout_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(process_utils, "run_with_timeout", lambda *_a, **_k: _completed(-9, timed_out=True))
        assert mdo._run_tests_on_code("def test_x(): pass\n", "x = 1\n", "m", 1) is None

    def test_execution_exception_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*_a: object, **_k: object) -> CompletedProcess:
            raise RuntimeError("boom")

        monkeypatch.setattr(process_utils, "run_with_timeout", _boom)
        assert mdo._run_tests_on_code("def test_x(): pass\n", "x = 1\n", "m", 1) is None


class TestComputeMdoFailClosed:
    def test_baseline_timeout_is_not_measurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: None)
        result = mdo.compute_mdo(**_base_args([_M("x = 2\n")]))
        assert result.available is False
        assert result.not_available_reason == "baseline_timeout"

    def test_baseline_execution_error_is_not_measurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo, "_run_tests_on_code", lambda *_a, **_k: mdo.TestRunResult(2, "errors during collection")
        )
        result = mdo.compute_mdo(**_base_args([_M("x = 2\n")]))
        assert result.available is False
        assert result.not_available_reason == "baseline_execution_error"

    def test_base_probe_invalid_is_not_measurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: _GREEN)
        monkeypatch.setattr(
            mdo,
            "_run_probe_detailed",
            lambda *_a, **_k: mdo.ProbeOutcome(behavior=None, invalid_reason="probe_error"),
        )
        result = mdo.compute_mdo(**_base_args([_M("x = 2\n")]))
        assert result.available is False
        assert result.not_available_reason == "probe_unavailable"


class TestComputeMdoMutantOutcomes:
    def test_empty_mutant_code_recorded_without_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: _GREEN)
        probe_calls: list[tuple[object, ...]] = []

        def _probe(*args: object, **_kwargs: object) -> mdo.ProbeOutcome:
            probe_calls.append(args)
            return mdo.ProbeOutcome(behavior='{"calls": []}')

        monkeypatch.setattr(mdo, "_run_probe_detailed", _probe)
        result = mdo.compute_mdo(**_base_args([_M("")]))
        assert result.available is True
        assert len(result.outcomes) == 1
        assert result.outcomes[0].ran is False
        assert len(probe_calls) == 1  # 空代码变异体不跑探针

    def test_mutant_run_not_determinable_is_unjudged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = iter([_GREEN, None])
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: next(runs))
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda *_a, **_k: mdo.ProbeOutcome(behavior="b"))
        result = mdo.compute_mdo(**_base_args([_M("x = 2\n")]))
        outcome = result.outcomes[0]
        assert outcome.ran is False
        assert outcome.crashed is False
        assert outcome.assertion_failed is False

    def test_mutant_usage_error_is_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = iter([_GREEN, mdo.TestRunResult(3, "usage error")])
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: next(runs))
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda *_a, **_k: mdo.ProbeOutcome(behavior="b"))
        result = mdo.compute_mdo(**_base_args([_M("x = 2\n")]))
        assert result.outcomes[0].crashed is True
        assert result.crash_rate == 1.0
