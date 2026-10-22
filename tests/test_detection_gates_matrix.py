#!/usr/bin/env python3
"""覆盖率补口 + 行为锁定：`src/tools/detection_gates.py`（检出优先双门）。

动机（EMSE 多轮优化批次）：这两个门是**检测协议的路内判定器**——
门①（特异性门）决定"红灯是否缺陷特异"，门②（红回归门）决定"再生成是否
抹掉了红证人"。它们的**降级分支**（无 gold 材料 / 执行错误不可判定 /
模块名非法）此前未覆盖，而这些分支正是"保守放行 vs 误判 over_red"的边界：
ADR-0033 第四起测量伪影的教训就是"判分侧与执行侧口径分叉 → rc=2 被误读"。

覆盖目标（coverage.xml 记录）：93-95、97、105-107 行与对应分支。
真实执行用例走 `experiments._m1_metrics._run_pytest_in_tmp`（本地 pytest 子进程，零 LLM）。
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from src.tools.detection_gates import (
    _run_test_against_code,
    detection_specificity_gate_enabled,
    red_regression_check,
    red_regression_gate_enabled,
    specificity_verdict,
)

_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED = "def add(a, b):\n    return a + b\n"
# buggy 红 + fixed 绿（缺陷特异）
_SPECIFIC_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
# buggy 红 + fixed 也红（过红：断言与缺陷无关）
_OVER_RED_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 99\n"


class TestGateSwitches:
    def test_specificity_gate_default_off(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DETECTION_SPECIFICITY_GATE_ENABLE", raising=False)
        assert detection_specificity_gate_enabled() is False

    def test_specificity_gate_truthy_values(self, monkeypatch: pytest.MonkeyPatch):
        # 实现只认 true/1/on（不含 yes）——测试按真实口径锁定，避免"以为开了其实没开"。
        for raw in ("true", "1", "on"):
            monkeypatch.setenv("DETECTION_SPECIFICITY_GATE_ENABLE", raw)
            assert detection_specificity_gate_enabled() is True, raw

    def test_specificity_gate_ignores_yes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DETECTION_SPECIFICITY_GATE_ENABLE", "yes")
        assert detection_specificity_gate_enabled() is False

    def test_red_regression_gate_default_off(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RED_REGRESSION_GATE_ENABLE", raising=False)
        assert red_regression_gate_enabled() is False

    def test_red_regression_gate_truthy(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RED_REGRESSION_GATE_ENABLE", "true")
        assert red_regression_gate_enabled() is True


class TestRunAgainstCodeGuards:
    """执行原语的**守卫分支**：非法模块名 / 缺失入参一律 None（保守），不得抛异常。"""

    @pytest.mark.parametrize("module_name", [None, "", "pkg/mod", "a-b", "1abc", "with space", "os.path"])
    def test_unsafe_module_name_returns_none(self, module_name: str | None):
        assert _run_test_against_code("def test_x(): pass", _FIXED, module_name) is None

    def test_valid_module_name_but_empty_test_is_not_green(self):
        """空测试 → 执行原语仍返回结构（非 None），且不得被判为 green。"""
        res = _run_test_against_code("", _FIXED, "target_mod")
        assert res is None or res.get("green") is False


class TestSpecificityVerdictGuards:
    def test_missing_gold_material_is_unavailable(self):
        assert specificity_verdict(_SPECIFIC_TEST, None, "target_mod") == "unavailable"
        assert specificity_verdict(_SPECIFIC_TEST, "   \n ", "target_mod") == "unavailable"

    def test_missing_test_code_is_unavailable(self):
        assert specificity_verdict("", _FIXED, "target_mod") == "unavailable"
        assert specificity_verdict("   ", _FIXED, "target_mod") == "unavailable"

    def test_unsafe_module_name_is_unavailable(self):
        """模块名非法 → 委托层拒绝 → 门必须保守放行（unavailable），不得判 over_red。"""
        assert specificity_verdict(_SPECIFIC_TEST, _FIXED, "bad-name") == "unavailable"


class TestSpecificityVerdictExecution:
    """真实执行路径（本地 pytest 子进程，零 LLM）：三段判定的两端。"""

    def test_specific_red_when_fixed_turns_green(self):
        verdict = specificity_verdict(_SPECIFIC_TEST, _FIXED, "target_mod")
        assert verdict == "specific_red", verdict

    def test_over_red_when_fixed_stays_red(self):
        verdict = specificity_verdict(_OVER_RED_TEST, _FIXED, "target_mod")
        assert verdict == "over_red", verdict

    def test_collection_error_is_unavailable_not_over_red(self):
        """ADR-0033 教训：测试根本跑不起来（收集错误）必须判 **unavailable**，
        不得因 rc!=0 误判为 over_red（那会把"测量不可用"记成"测试非特异"）。"""
        verdict = specificity_verdict("def broken(:\n    pass\n", _FIXED, "target_mod")
        assert verdict == "unavailable", verdict


class TestRedRegressionCheck:
    """门②（纯状态比较，零执行）：再生成是否抹掉既有红证人。

    判定的**五个必要条件**（全部满足才判抹红）：
    门开启 ∧ 曾见红 ∧ 有红证人快照 ∧ 当前测试≠红证人 ∧ 再生成计数>0 ∧ 源码未修补。
    逐条锁死，防止"少判一条"导致误报（误报会把修复循环卡回红证人）。
    """

    _WITNESS: ClassVar[str] = "def test_x():\n    assert 1 == 2\n"
    _NEW: ClassVar[str] = "def test_x():\n    assert True\n"
    _RED_STATE: ClassVar[dict[str, object]] = {
        "detection_first_red_seen": True,
        "red_witness_test_code": _WITNESS,
        "regeneration_count": 1,
        "target_code": "def f():\n    return 1\n",
        "original_target_code": "def f():\n    return 1\n",
    }

    def _enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RED_REGRESSION_GATE_ENABLE", "true")

    def test_gate_off_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RED_REGRESSION_GATE_ENABLE", raising=False)
        assert red_regression_check(self._RED_STATE, self._NEW) is None

    def test_no_red_witness_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        assert red_regression_check({}, self._NEW) is None
        assert red_regression_check({"detection_first_red_seen": True}, self._NEW) is None

    def test_missing_red_seen_flag_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        state = dict(self._RED_STATE, detection_first_red_seen=False)
        assert red_regression_check(state, self._NEW) is None

    def test_same_test_is_not_a_violation(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        assert red_regression_check(self._RED_STATE, self._WITNESS) is None

    def test_zero_regeneration_count_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        state = dict(self._RED_STATE, regeneration_count=0)
        assert red_regression_check(state, self._NEW) is None

    def test_patched_source_defers_to_gold_adjudication(self, monkeypatch: pytest.MonkeyPatch):
        """已落地补丁 → 门内不判（交 M1 gold 事后裁决），防止双重口径。"""
        self._enable(monkeypatch)
        state = dict(self._RED_STATE, target_code="def f():\n    return 2\n")
        assert red_regression_check(state, self._NEW) is None

    def test_all_conditions_met_reports_violation(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        out = red_regression_check(self._RED_STATE, self._NEW)
        assert isinstance(out, dict), out
        assert out["red_regression_violation"] is True
        assert out["generated_test"] == self._WITNESS, "必须恢复红证人而非放行新测试"
        assert out["test_passed"] is False

    def test_whitespace_only_replacement_is_treated_as_changed_test(self, monkeypatch: pytest.MonkeyPatch):
        self._enable(monkeypatch)
        out = red_regression_check(self._RED_STATE, "   \n  ")
        assert isinstance(out, dict) and out["generated_test"] == self._WITNESS


class TestDelegationFailurePaths:
    """委托层异常的两条 fail-open 分支（覆盖率收口）。

    `_run_test_against_code` 委托 `experiments._m1_metrics._run_pytest_in_tmp` 执行，
    并额外消费 `_looks_like_test_execution_error` 做"根本没跑起来"的判据。
    **两条 import/调用失败路径**必须保守 fail-open（返回 None → 门判 unavailable），
    否则一次测量层异常会被误判为 `over_red`（把"不可测"记成"非特异"，
    正是 ADR-0033 那类伪影的同族风险）。
    """

    def _patch_runner(self, monkeypatch: pytest.MonkeyPatch, behavior: object):
        import experiments._m1_metrics as m1

        calls: dict[str, int] = {"n": 0}

        def _fake(*_args: object, **_kwargs: object):
            calls["n"] += 1
            if isinstance(behavior, BaseException):
                raise behavior
            return behavior

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", _fake, raising=True)
        return calls

    def test_runner_exception_fails_open(self, monkeypatch: pytest.MonkeyPatch):
        calls = self._patch_runner(monkeypatch, RuntimeError("measurement layer exploded"))
        assert _run_test_against_code("def test_x(): assert True", _FIXED, "target_mod") is None
        assert calls["n"] == 1

    def test_runner_returning_none_is_propagated(self, monkeypatch: pytest.MonkeyPatch):
        self._patch_runner(monkeypatch, None)
        assert _run_test_against_code("def test_x(): assert True", _FIXED, "target_mod") is None

    def test_exec_error_predicate_failure_falls_back_to_rc_caliber(self, monkeypatch: pytest.MonkeyPatch):
        """执行错误判据不可用时不得抛异常；真 passed 的 rc==0 仍判绿。

        BE（2026-10-21）：rc==0 同时须满足共享"有效通过"谓词——夹具改用
        真实摘要行（旧夹具 ``"ok"`` 无摘要，按新口径属不可判定）。本用例
        仍锁定"判据自身异常不阻断返回结构"这一历史意图。
        """
        import experiments._m1_metrics as m1

        self._patch_runner(monkeypatch, (0, "1 passed in 0.01s", ""))

        def _boom(*_args: object, **_kwargs: object) -> bool:
            raise RuntimeError("predicate unavailable")

        monkeypatch.setattr(m1, "_looks_like_test_execution_error", _boom, raising=True)
        out = _run_test_against_code("def test_x(): assert True", _FIXED, "target_mod")
        assert isinstance(out, dict)
        assert out["green"] is True and out["unavailable"] is False

    def test_gate_maps_delegation_failure_to_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        """委托失败时门①必须判 `unavailable`（不是 over_red）。"""
        self._patch_runner(monkeypatch, RuntimeError("boom"))
        assert specificity_verdict(_SPECIFIC_TEST, _FIXED, "target_mod") == "unavailable"
