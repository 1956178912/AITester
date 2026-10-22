"""BD 轮：MDO 的两个 ``rc==0`` 判绿点接共享「有效通过」谓词（2026-10-21）。

F03 同族：pytest 对"没有任何断言执行"的套件同样返回 rc==0（全 skip /
xfail / xpass / deselect / 空输出）。MDO 里有**两个**只看退出码的判绿点：

1. **基线**：旧实现通过 rc==0 后直接进入度量；全 skip 基线在变异体上同样
   rc==0 → ``measured`` 且 MDR=0（把"没跑起来"记成"测了 0 判别"）。
2. **变异体**：旧实现把 rc==0 记 ``ran=True`` 并留在分母，skip 被当成
   "未判别"，压低 MDR 而不是"无证据"。

收口口径与 BA/BB/BC 完全一致：至少 1 个真实 ``passed`` 且 0 个 ``failed``
才算有效运行；部分 skip 与真实 passed 并存仍算有效。基线不满足 → 整体
``not_measurable``；变异体不满足 → 单列 ``no_effective_pass`` 并排除出
MTR/MDR 分母。

零 LLM、零网络。行为测试走 mock 边界（执行/探针），另有一条真实 pytest
端到端锁（module-level skip，rc==0）。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from experiments import _m1_metrics as m1
from src.measurement import mdo

_GREEN = mdo.TestRunResult(0, "1 passed in 0.01s", 0, 0, True)
_NO_EFFECTIVE_PASS_REASON = "test_not_green_on_base(no_effective_pass)"


class _M:
    def __init__(self, code: str, mutant_type: str = "probe") -> None:
        self.code = code
        self.mutant_type = mutant_type
        self.description = mutant_type
        self.line_no = 1


def _args(mutants: list[_M]) -> dict[str, Any]:
    return {
        "base_code": "def f():\n    return 1\n",
        "test_code": "from m import f\n\ndef test_f():\n    assert f() == 1\n",
        "module_name": "m",
        "mutants": mutants,
        "timeout_seconds": 1,
    }


def _runs(*results: Any):
    it = iter(results)
    return lambda *_a, **_k: next(it)


class TestSingleSource:
    def test_m1_alias_is_the_shared_predicate(self) -> None:
        from src.utils import pytest_output

        assert m1.pytest_summary_counts is pytest_output.pytest_summary_counts
        assert m1._suite_has_effective_pass is pytest_output.suite_has_effective_pass

    def test_mdo_uses_the_shared_predicate(self) -> None:
        from src.utils import pytest_output

        assert mdo.suite_has_effective_pass is pytest_output.suite_has_effective_pass
        src = inspect.getsource(mdo)
        assert "from src.utils.pytest_output import suite_has_effective_pass" in src


class TestBaselineEffectivePass:
    @pytest.mark.parametrize(
        "output",
        [
            "1 skipped in 0.01s",
            "1 xfailed in 0.01s",
            "1 xpassed in 0.01s",
            "3 deselected in 0.01s",
            "no tests ran in 0.01s",
            "1 passed, 1 failed in 0.02s",
            "",
        ],
    )
    def test_rc0_without_effective_pass_is_not_measurable(self, output: str, monkeypatch: pytest.MonkeyPatch) -> None:
        probe_calls: list[object] = []

        def _probe(*args: object, **_kwargs: object) -> mdo.ProbeOutcome:
            probe_calls.append(args)
            return mdo.ProbeOutcome(behavior="b")

        monkeypatch.setattr(mdo, "_run_tests_on_code", lambda *_a, **_k: mdo.TestRunResult(0, output))
        monkeypatch.setattr(mdo, "_run_probe_detailed", _probe)

        result = mdo.compute_mdo(**_args([_M("x = 2\n")]))

        assert result.available is False
        assert result.not_available_reason == _NO_EFFECTIVE_PASS_REASON
        assert result.mutant_discrimination_rate is None
        assert result.status == "not_measurable"
        assert probe_calls == [], "基线非有效通过必须在探针/变异体执行前短路"

    def test_execution_error_keeps_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            lambda *_a, **_k: mdo.TestRunResult(2, "1 skipped in 0.01s"),
        )
        result = mdo.compute_mdo(**_args([_M("x = 2\n")]))
        assert result.not_available_reason == "baseline_execution_error"

    def test_partial_skip_with_real_pass_still_measures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            _runs(
                mdo.TestRunResult(0, "1 passed, 1 skipped in 0.02s"),
                mdo.TestRunResult(0, "1 passed in 0.01s"),
            ),
        )
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda code, *_a, **_k: mdo.ProbeOutcome(behavior=code))
        result = mdo.compute_mdo(**_args([_M("x = 2\n")]))
        assert result.available is True
        assert result.outcomes[0].ran is True
        assert result.mutant_discrimination_rate == 0.0

    def test_real_pytest_runtime_skip_is_not_measurable(self) -> None:
        # 运行期 skip 才是 rc==0 的真实通道：module-level skip 无测试收集 → rc=5。
        test_code = "import pytest\n\ndef test_f():\n    pytest.skip('conditional suite')\n"
        result = mdo.compute_mdo(
            base_code="def f():\n    return 1\n",
            test_code=test_code,
            module_name="m",
            mutants=[_M("def f():\n    return 2\n")],
            timeout_seconds=30,
        )
        assert result.available is False
        assert result.not_available_reason == _NO_EFFECTIVE_PASS_REASON
        assert result.mutant_discrimination_rate is None


class TestMutantEffectivePass:
    def test_all_skip_mutant_is_not_measurable_and_not_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            _runs(_GREEN, mdo.TestRunResult(0, "1 skipped in 0.01s")),
        )
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda code, *_a, **_k: mdo.ProbeOutcome(behavior=code))

        result = mdo.compute_mdo(**_args([_M("x = 2\n")]))

        assert result.available is False
        assert result.not_available_reason == "mutant_runs_no_effective_pass"
        assert result.mutant_discrimination_rate is None
        assert result.outcomes[0].no_effective_pass is True
        assert result.outcomes[0].ran is False
        assert result.outcomes[0].crashed is False

    def test_partial_skip_mutant_with_real_pass_still_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            _runs(_GREEN, mdo.TestRunResult(0, "1 passed, 1 skipped in 0.02s")),
        )
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda code, *_a, **_k: mdo.ProbeOutcome(behavior=code))

        result = mdo.compute_mdo(**_args([_M("x = 2\n")]))

        assert result.available is True
        assert result.outcomes[0].ran is True
        assert result.outcomes[0].no_effective_pass is False
        assert result.mutant_discrimination_rate == 0.0

    def test_mixed_pool_excludes_skipped_mutant_and_discloses_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mdo,
            "_run_tests_on_code",
            _runs(
                _GREEN,
                mdo.TestRunResult(0, "1 skipped in 0.01s"),
                mdo.TestRunResult(0, "1 passed in 0.01s"),
            ),
        )
        monkeypatch.setattr(mdo, "_run_probe_detailed", lambda code, *_a, **_k: mdo.ProbeOutcome(behavior=code))

        result = mdo.compute_mdo(**_args([_M("x = 2\n"), _M("x = 3\n")]))
        exported = result.as_dict()

        assert result.available is True
        assert result.mutant_discrimination_rate == 0.0
        assert exported["mdo_no_effective_pass"] == 1
        assert exported["mdo_evaluable"] == 1
        assert exported["mdo_pool_size"] == 2
