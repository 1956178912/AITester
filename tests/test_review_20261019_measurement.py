"""Z 轮（2026-10-19 第四轮第三方全量静态审查）测量与 LLM 参数修复回归锁。

对应审查报告的三个 P1：

- **F12**（§G、§M5、§H）：`compute_mdo` 把 ``rc==1`` 无差别标
  ``assertion_failed``——"测试无断言 + 变异体抛 ValueError"也产生 MDR
  （报告最小反例）。修复后只有"全部 call 阶段失败均为断言型（AssertionError /
   pytest.fail 的 Failed）"才记判别，纯运行异常记 CRASH（MDR 不增）。
- **F13**（§G、§M6、§H）：行为探针硬依赖 SIGALRM/setitimer，Windows 上输出
  ``{"probe_error": ...}`` 被当相同行为摘要 → measured 伪零值。修复后探针
  自带能力守卫 + 父进程 schema 校验；base 探针无效 → not_measurable，单变异体
  探针无效 → 排除分母（全无效 → not_measurable）。
- **F14**（§G、§M4、§H）：负 rc（信号终止）穿过守卫，``buggy=-15 ∧ fixed=0``
  推导出 detection=1.0。修复后负 rc 一律判为异常终止/执行错误。

纪律：零 LLM、零网络；探针无效场景全部 mock；MDO 真实 pytest 子进程只用
最小合成函数（单次 <1s），M1 用例 mock 执行原语（不拉真实套件）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ═════════════════════════════════════════════════════════════════════════════
#  F12：断言失败 vs 运行异常（MDR 构念）
# ═════════════════════════════════════════════════════════════════════════════


def _valid_probe_behavior(call_repr: str) -> str:
    """构造一份 schema 合法的行为摘要 JSON（探针 stdout 形态）。"""
    return json.dumps({"calls": [["f", ["1"], "ok", call_repr]], "state": []}, sort_keys=True)


_BASE_CODE = "def f(x):\n    if x > 0:\n        return x + 1\n    return 0\n"
_NO_ASSERT_TEST = "from t import f\n\ndef test_f():\n    f(1)\n"
_STRONG_TEST = "from t import f\n\ndef test_f():\n    assert f(1) == 2\n"
_RUNTIME_MUTANT = "def f(x):\n    if x > 0:\n        raise ValueError('boom')\n    return 0\n"
_OFFSET_MUTANT = "def f(x):\n    if x > 0:\n        return x + 2\n    return 0\n"


class _Mutant:
    """最小变异体替身（compute_mdo 消费的属性集）。"""

    def __init__(self, code: str, mutant_type: str = "probe", desc: str = "") -> None:
        self.code = code
        self.mutant_type = mutant_type
        self.description = desc or mutant_type
        self.line_no = 1


@pytest.mark.unit
class TestF12AssertionVsRuntimeException:
    """F12：rc==1 不再等于断言失败；运行异常不得产生 MDR。"""

    def test_report_m5_29_runtime_mutants_mdr_zero_crash_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """报告 §M5 mock 反例：29 个运行异常变异体，修复前 mdr=1，修复后 mdr=0。

        29 个 mock 变异体仅用于越过序列化阈值（pool_floor=29），不证明真实
        变异池独立性；真实最小反例见下方端到端用例。
        """
        from src.measurement import mdo

        base_behavior = _valid_probe_behavior("2")
        mutant_behavior = _valid_probe_behavior("3")

        def _fake_probe(code: str, module_name: str, timeout_seconds: int, **_kwargs: Any) -> str:
            return base_behavior if code == "base_code" else mutant_behavior

        def _fake_tests(test_code: str, code: str, module_name: str, timeout_seconds: int) -> tuple[int, str]:
            # 无断言运行异常：pytest rc=1 + ValueError，非断言失败
            return (0, "1 passed") if code == "base_code" else (1, "ValueError: boom")

        monkeypatch.setattr(mdo, "_run_probe", _fake_probe)
        monkeypatch.setattr(mdo, "_run_tests_on_code", _fake_tests)

        mutants = [_Mutant("runtime_error", mutant_type="runtime", desc=str(i)) for i in range(29)]
        result = mdo.compute_mdo(
            base_code="base_code",
            test_code="suite",
            module_name="t",
            mutants=mutants,
        )
        exported = result.as_dict()
        assert exported["mdo_available"] is True
        assert exported["mdo_pool_floor_ok"] is True, "29 个变异体应达池下限（便于观察出口值）"
        assert exported["mdr"] == 0.0, "F12：无断言运行异常不得计入 MDR（修复前为 1.0）"
        assert exported["crash_rate"] == 1.0, "F12：运行异常应体现在 CRASH/异常类别"
        assert exported["mtr"] == 1.0, "MTR 语义保留：行为发生了偏差"

    def test_real_pytest_no_assert_valueerror_is_crash_not_mdr(self) -> None:
        """真实最小反例（§G 原文）：无断言测试 + 变异体抛 ValueError → MDR=0。

        端到端跑真实 pytest：base 绿、mutant rc=1 且失败异常为 ValueError
        → 不能记断言判别；修复前此处会把 rc==1 当 assertion_failed。
        """
        from src.measurement import mdo

        result = mdo.compute_mdo(
            base_code=_BASE_CODE,
            test_code=_NO_ASSERT_TEST,
            module_name="t",
            mutants=[_Mutant(_RUNTIME_MUTANT, mutant_type="runtime", desc="raise ValueError")],
            timeout_seconds=30,
        )
        assert result.available is True
        assert result.crash_rate == 1.0, "ValueError 运行异常应记 CRASH"
        assert result.mutant_discrimination_rate == 0.0, "无断言测试不得获得判别率"

    def test_real_pytest_assertion_failure_still_discriminates(self) -> None:
        """真实断言失败仍必须计入 MDR（不误伤：强断言 + 返回值偏移变异体）。"""
        from src.measurement import mdo

        result = mdo.compute_mdo(
            base_code=_BASE_CODE,
            test_code=_STRONG_TEST,
            module_name="t",
            mutants=[_Mutant(_OFFSET_MUTANT, mutant_type="numeric_offset")],
            timeout_seconds=30,
        )
        assert result.available is True
        assert result.mutant_trigger_rate == 1.0
        assert result.mutant_discrimination_rate == 1.0, "真断言失败必须仍计入 MDR"
        assert result.crash_rate == 0.0

    def test_run_tests_on_code_records_failure_types(self) -> None:
        """真实 pytest 两次运行：conftest 落盘能区分 AssertionError 与 ValueError。"""
        from src.measurement import mdo

        # 强断言 + 返回值偏移变异体 → 断言失败（非运行异常）
        assertion_run = mdo._run_tests_on_code(_STRONG_TEST, _OFFSET_MUTANT, "t", 30)
        assert assertion_run is not None
        assert assertion_run.rc == 1
        assert assertion_run.report_available is True, "conftest 结构化失败记录必须可用"
        assert assertion_run.assertion_failures >= 1
        assert assertion_run.runtime_errors == 0

        runtime_run = mdo._run_tests_on_code(_NO_ASSERT_TEST, _RUNTIME_MUTANT, "t", 30)
        assert runtime_run is not None
        assert runtime_run.rc == 1
        assert runtime_run.report_available is True
        assert runtime_run.assertion_failures == 0
        assert runtime_run.runtime_errors >= 1

    @pytest.mark.parametrize(
        ("run", "expected"),
        [
            (
                # 结构化记录：全部断言型
                lambda m: m.TestRunResult(
                    rc=1,
                    output="",
                    assertion_failures=1,
                    runtime_errors=0,
                    report_available=True,
                ),
                "assertion",
            ),
            (
                # 结构化记录：混合失败 → 保守归运行异常（不计判别）
                lambda m: m.TestRunResult(
                    rc=1,
                    output="",
                    assertion_failures=1,
                    runtime_errors=1,
                    report_available=True,
                ),
                "runtime",
            ),
            (
                # 结构化记录：纯运行异常
                lambda m: m.TestRunResult(
                    rc=1,
                    output="",
                    assertion_failures=0,
                    runtime_errors=1,
                    report_available=True,
                ),
                "runtime",
            ),
            # 历史二元组 mock（无结构化记录）→ 回退输出解析
            (lambda m: (1, "ValueError: boom"), "unknown"),
            (lambda m: (1, "FAILED test_t.py::test_f - TypeError: bad"), "runtime"),
            (lambda m: (1, "FAILED test_t.py::test_f - assert 3 == 2"), "assertion"),
            (lambda m: (1, "FAILED test_t.py::test_f - Failed: DID NOT RAISE ValueError"), "assertion"),
            (lambda m: (1, "E   AssertionError: assert 3 == 2"), "assertion"),
        ],
        ids=[
            "structured-assertion",
            "structured-mixed",
            "structured-runtime",
            "legacy-tuple-no-marker",
            "legacy-summary-type-error",
            "legacy-summary-assert",
            "legacy-summary-failed",
            "legacy-traceback-assertion",
        ],
    )
    def test_rc1_failure_classification_policy(self, run: Any, expected: str) -> None:
        """F12 分类策略：只有"可证明全部为断言失败"才返回 assertion。"""
        from src.measurement import mdo

        assert mdo._classify_rc1_failure(run(mdo)) == expected


# ═════════════════════════════════════════════════════════════════════════════
#  F13：探针无效不得折叠为 measured 零值
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestF13ProbeValidity:
    """F13：探针能力守卫 + schema 校验 + 不可测语义。"""

    def test_probe_source_has_capability_guard(self) -> None:
        """探针源码必须显式做 POSIX alarm 能力探测（Windows 上不进入不可用逻辑）。"""
        from src.measurement import mdo

        source = mdo._behavior_probe_source("t")
        assert 'hasattr(signal, "SIGALRM")' in source
        assert 'hasattr(signal, "setitimer")' in source
        assert 'hasattr(signal, "ITIMER_REAL")' in source
        assert "probe_unsupported" in source

    def test_probe_guard_runs_under_windows_like_signal_module(self, tmp_path: Path) -> None:
        """无 SIGALRM 的假 signal 模块（模拟 Windows）→ 探针打印 probe_unsupported。

        macOS 无法实跑 Windows，故用 PYTHONPATH 注入 fake signal.py 遮蔽标准库
        signal；探针应走能力守卫分支正常退出（不是把 AttributeError 当行为）。
        """
        from src.measurement import mdo

        (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        # fake signal：不带 SIGALRM/setitimer/ITIMER_REAL（等价 Windows 能力面）
        (tmp_path / "signal.py").write_text(
            '"""fake signal module without POSIX alarm APIs (windows-like)."""\n',
            encoding="utf-8",
        )
        probe_path = tmp_path / "_probe.py"
        probe_path.write_text(mdo._behavior_probe_source("m"), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(probe_path)],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"能力守卫分支应正常退出: {proc.stderr[-500:]}"
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload.get("probe_unsupported"), "无 alarm 能力必须显式报 probe_unsupported"

    def test_run_probe_rejects_unsupported_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_probe 拒绝 probe_unsupported 诊断（返回 None，不返回诊断文本）。"""
        from src.measurement import mdo

        fake_source = 'import json, sys\nprint(json.dumps({"probe_unsupported": "no_posix_alarm"}))\nsys.exit(0)\n'
        monkeypatch.setattr(mdo, "_behavior_probe_source", lambda module_name: fake_source)
        assert mdo._run_probe("def f(x):\n    return x\n", "t", 30) is None

    def test_real_run_probe_returns_valid_behavior(self) -> None:
        """正常平台（POSIX）：_run_probe 仍返回含 calls 列表的合法行为摘要。"""
        from src.measurement import mdo

        behavior = mdo._run_probe("def f(x):\n    return x + 1\n", "fmod", 30)
        assert isinstance(behavior, str) and behavior, "正常平台探针必须可用"
        payload = json.loads(behavior)
        assert isinstance(payload.get("calls"), list)
        # 同一代码两次探针摘要必须逐字节相同（可比较性）
        assert mdo._run_probe("def f(x):\n    return x + 1\n", "fmod", 30) == behavior

    @pytest.mark.parametrize(
        ("raw", "expected_reason"),
        [
            (None, "probe_not_run"),
            ("", "empty_output"),
            ("not-json", "invalid_json"),
            ('["calls"]', "non_object_payload"),
            ('{"probe_error": "AttributeError"}', "probe_error"),
            ('{"import_error": "SyntaxError"}', "import_error"),
            ('{"probe_unsupported": "no_posix_alarm"}', "probe_unsupported"),
            ('{"state": []}', "missing_calls"),
            ('{"calls": "not-a-list"}', "missing_calls"),
        ],
        ids=[
            "none",
            "empty",
            "invalid-json",
            "non-object",
            "probe-error",
            "import-error",
            "probe-unsupported",
            "no-calls",
            "calls-not-list",
        ],
    )
    def test_normalize_probe_output_rejects_invalid(self, raw: str | None, expected_reason: str) -> None:
        """修复前后差异：历史父进程把诊断原文当行为摘要；现在必须拒绝。"""
        from src.measurement import mdo

        behavior, reason = mdo._normalize_probe_output(raw)
        assert behavior is None
        assert reason == expected_reason

    def test_normalize_probe_output_accepts_valid_and_is_idempotent(self) -> None:
        from src.measurement import mdo

        raw = _valid_probe_behavior("2")
        behavior, reason = mdo._normalize_probe_output(raw)
        assert behavior is not None and reason == ""
        assert mdo._normalize_probe_output(behavior) == (behavior, "")

    def test_report_m6_probe_error_mock_makes_mdo_not_measurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """报告 §M6 反例：mock _run_probe 返回 probe_error → 不可测（不再是 measured 0）。"""
        from src.measurement import mdo

        def _fake_probe(code: str, module_name: str, timeout_seconds: int, **_kwargs: Any) -> str:
            return '{"probe_error": "AttributeError"}'

        monkeypatch.setattr(mdo, "_run_probe", _fake_probe)
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            lambda *a, **k: (0, "1 passed"),
        )
        result = mdo.compute_mdo(
            base_code="base",
            test_code="suite",
            module_name="t",
            mutants=[_Mutant("mutant")],
        )
        assert result.available is False
        assert result.not_available_reason == "probe_unavailable"
        assert result.mutant_trigger_rate is None
        assert result.mutant_discrimination_rate is None

    def test_all_mutants_probe_invalid_makes_mdo_not_measurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """base 探针有效但全部变异体探针无效（全无效）→ not_measurable。"""
        from src.measurement import mdo

        base_behavior = _valid_probe_behavior("2")

        def _fake_probe(code: str, module_name: str, timeout_seconds: int, **_kwargs: Any) -> str:
            return base_behavior if code == "base_code" else '{"import_error": "SyntaxError"}'

        monkeypatch.setattr(mdo, "_run_probe", _fake_probe)
        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *a, **k: (0, "1 passed"))
        result = mdo.compute_mdo(
            base_code="base_code",
            test_code="suite",
            module_name="t",
            mutants=[_Mutant("broken_a"), _Mutant("broken_b")],
        )
        assert result.available is False
        assert result.not_available_reason == "probe_unavailable"
        assert result.as_dict()["mdr"] is None, "不可测不得输出数字零值"

    def test_single_mutant_probe_invalid_excluded_from_denominator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """单个变异体探针无效 → 排除分母；其余有效变异体照常计算 MTR/MDR。"""
        from src.measurement import mdo

        base_behavior = _valid_probe_behavior("2")
        mutant_behavior = _valid_probe_behavior("3")

        def _fake_probe(code: str, module_name: str, timeout_seconds: int, **_kwargs: Any) -> str:
            if code == "base_code":
                return base_behavior
            if code == "broken_mutant":
                return '{"probe_unsupported": "no_posix_alarm"}'
            return mutant_behavior

        def _fake_tests(test_code: str, code: str, module_name: str, timeout_seconds: int) -> tuple[int, str]:
            if code == "base_code":
                return (0, "1 passed")
            if code == "broken_mutant":
                # 探针无效不影响测试执行证据（此处语法坏 → 收集错误 → CRASH）
                return (2, "errors during collection")
            return (1, "FAILED test_t.py::test_f - assert 3 == 2")

        monkeypatch.setattr(mdo, "_run_probe", _fake_probe)
        monkeypatch.setattr(mdo, "_run_tests_on_code", _fake_tests)
        result = mdo.compute_mdo(
            base_code="base_code",
            test_code="suite",
            module_name="t",
            mutants=[_Mutant("broken_mutant"), _Mutant("valid_mutant")],
        )
        exported = result.as_dict()
        assert exported["mdo_available"] is True
        assert exported["mdo_probe_invalid"] == 1
        assert exported["mdo_evaluable"] == 1
        assert exported["mdo_pool_size"] == 2
        # 分母只有有效变异体 → MDR/MTR 由它决定（池不足 → 出口 None，审计字段有值）
        assert result.mutant_trigger_rate == 1.0
        assert result.mutant_discrimination_rate == 1.0
        assert exported["mdo_raw"]["mdr"] == 1.0


# ═════════════════════════════════════════════════════════════════════════════
#  F14：负 rc（信号终止）不得进入正常检出路径
# ═════════════════════════════════════════════════════════════════════════════

_M1_BUGGY_CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"
_M1_FIXED_CODE = "def add(a: int, b: int) -> int:\n    return a + b + 1\n"
_M1_GOLD_TEST = "from add_off_by_one import add\n\n\ndef test_gold():\n    assert add(1, 2) == 4\n"
_M1_LEGIT_F2P = "from add_off_by_one import add\n\n\ndef test_f2p():\n    assert add(1, 2) == 4\n"


@dataclass
class _FakeTask:
    """_extract_gold_material 消费的最小任务替身。"""

    _task_id: str
    instance_code: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def repo_name(self) -> str:
        return "synthetic/_probe"


def _make_m1_task() -> _FakeTask:
    return _FakeTask(
        _task_id="probe__add_off_by_one",
        instance_code=_M1_BUGGY_CODE,
        metadata={
            "source": "synthetic",
            "test_cases": _M1_GOLD_TEST,
            "fixed": _M1_FIXED_CODE,
            "is_cross_file": False,
        },
    )


@pytest.mark.unit
class TestF14NegativeReturnCode:
    """F14：被信号终止（负 rc）= 异常终止，不得计为有效检出。"""

    def test_looks_like_execution_error_negative_rc(self) -> None:
        """报告 §M4 验收口径：-15 必须判为执行错误（修复前返回 False）。"""
        from experiments._m1_metrics import _looks_like_test_execution_error

        assert _looks_like_test_execution_error(-15, "") is True
        assert _looks_like_test_execution_error(-9, "") is True
        # 正常退出码语义不变
        assert _looks_like_test_execution_error(0, "") is False
        assert _looks_like_test_execution_error(1, "assert 1 == 2") is False
        assert _looks_like_test_execution_error(2, "") is True
        assert _looks_like_test_execution_error(5, "") is True

    def test_detection_rate_buggy_negative_rc_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端反例：buggy=(-15, "", "") ∧ fixed=(0, "1 passed", "") → 0.0。

        修复前两条守卫都不命中，函数落到 `return 1.0`——异常进程终止被计成
        有效检出（F14 的核心危害）。
        """
        from experiments import _m1_metrics as m1

        monkeypatch.setattr(
            m1,
            "_run_pytest_in_tmp",
            mock.Mock(side_effect=[(-15, "", ""), (0, "1 passed", "")]),
        )
        task = _make_m1_task()
        state: dict[str, Any] = {"generated_test": _M1_LEGIT_F2P, "test_passed": False}
        assert m1._compute_detection_rate(task, state) == 0.0
        # 只跑了 buggy 侧就提前返回（不消耗 fixed 侧结果）
        call_count = m1._run_pytest_in_tmp.call_count
        assert call_count in (1, 2)

    def test_test_error_rate_counts_negative_rc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """test_error_rate 消费同一判据：负 rc → 1.0（异常终止单列）。"""
        from experiments import _m1_metrics as m1

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", mock.Mock(return_value=(-15, "", "")))
        task = _make_m1_task()
        state: dict[str, Any] = {"generated_test": _M1_LEGIT_F2P, "test_passed": False}
        assert m1._compute_test_error_rate(task, state) == 1.0

    def test_oracle_suite_verdict_negative_rc_is_unavailable(self) -> None:
        """oracle 判读层同口径：负 rc → unavailable（不得当 fail/silent）。"""
        from experiments import _m1_metrics as m1

        assert m1._suite_run_verdict((-15, "", "")) == "unavailable"

    def test_detection_gate_negative_rc_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detection_gates 委托同一判据：负 rc 判 unavailable（不得判 over_red）。"""
        from experiments import _m1_metrics as m1
        from src.tools import detection_gates

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", mock.Mock(return_value=(-15, "", "")))
        result = detection_gates._run_test_against_code(
            "def test_x():\n    assert True\n",
            _M1_FIXED_CODE,
            "add_off_by_one",
        )
        assert result is not None
        assert result["unavailable"] is True
        assert result["green"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
