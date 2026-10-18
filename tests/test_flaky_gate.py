"""
R35/R31（2026-09-30 独立审查 P0）：flaky 门禁单元测试。

覆盖：
- classify_flaky 纯数据分类（全 pass / 全 fail / 混合 / 空列表）
- flaky_repeat_count 默认值 / 环境变量覆盖 / 非法值兜底
- flaky_check_enabled 开关解析
- detect_flaky 对 mock executor 的重复执行（flaky / 稳定失败 / 异常降级）
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.flaky_gate import (
    classify_flaky,
    detect_flaky,
    flaky_check_enabled,
    flaky_repeat_count,
)


class TestClassifyFlaky:
    """纯数据分类口径。"""

    def test_all_pass_not_flaky(self):
        cls = classify_flaky([True, True, True])
        assert cls["flaky"] is False
        assert cls["pass_count"] == 3
        assert cls["fail_count"] == 0

    def test_all_fail_not_flaky(self):
        cls = classify_flaky([False, False])
        assert cls["flaky"] is False
        assert cls["pass_count"] == 0
        assert cls["fail_count"] == 2

    def test_mixed_is_flaky(self):
        cls = classify_flaky([True, False, True])
        assert cls["flaky"] is True
        assert cls["pass_count"] == 2
        assert cls["fail_count"] == 1

    def test_empty_list_not_flaky(self):
        cls = classify_flaky([])
        assert cls["flaky"] is False
        assert cls["total"] == 0


class TestSwitches:
    def test_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("FLAKY_CHECK_ENABLE", raising=False)
        assert flaky_check_enabled() is False

    def test_enabled_truthy(self, monkeypatch):
        monkeypatch.setenv("FLAKY_CHECK_ENABLE", "true")
        assert flaky_check_enabled() is True

    def test_repeat_default_and_override(self, monkeypatch):
        monkeypatch.delenv("FLAKY_REPEAT_COUNT", raising=False)
        assert flaky_repeat_count() == 3
        monkeypatch.setenv("FLAKY_REPEAT_COUNT", "30")
        assert flaky_repeat_count() == 30

    def test_repeat_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("FLAKY_REPEAT_COUNT", "not_a_number")
        assert flaky_repeat_count() == 3


class TestDetectFlaky:
    """对 mock executor 的重复执行检测。"""

    def test_stable_failure(self):
        """全 fail：flaky=False，稳定失败结果可信。"""
        executor = MagicMock()
        executor.execute.return_value = {"passed": False}
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        assert cls["flaky"] is False
        assert cls["pass_count"] == 0

    def test_flaky_detected(self):
        """混合：flaky=True，pass_count > 0。"""
        executor = MagicMock()
        # 首轮 fail（base），后续 [True, False, True] → 混合
        executor.execute.side_effect = [
            {"passed": True},
            {"passed": False},
            {"passed": True},
        ]
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        assert cls["flaky"] is True
        assert cls["pass_count"] >= 1
        assert cls["fail_count"] >= 1

    def test_exception_degrades_conservatively(self):
        """重复执行异常时保守降级（不阻断，results 截断）。"""
        executor = MagicMock()
        executor.execute.side_effect = [Exception("boom"), {"passed": False}]
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        # 首轮 fail + 第一次异常 break → 结果 [False, False] 全 fail，稳定
        assert cls["flaky"] is False
        assert cls["fail_count"] >= 1


# ─── A16（2026-10-18 第三方评审 P1）：fail→pass 证据保留与 nodes 侧消费 ───────
# 背景：重试层旧实现只保留 last_result，首败次过（fail→pass）证据被最后一次
# 成功结果抹掉，flaky 门（仅对 passed=False 生效）永远看不到。本组测试锁定：
# 1) run_pytest_with_retry 保留每次尝试记录（rc / timed_out / passed）且返回
#    二元组结构不变；2) 本地 / venv 沙箱链路把证据并入结果 dict；
# 3) _executor_node 按真实序列写 flaky 标记并保守处理 test_passed，
#    无 fail→pass 证据时历史字段不变。

import subprocess  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from src.agents.executor_runtime import (  # noqa: E402
    extract_execution_attempts,
    observed_fail_then_pass,
    run_pytest_with_retry,
    summarize_execution_attempts,
)


class _RetrySelf:
    """run_pytest_with_retry 所需的最小 self（仅 timeout）。"""

    timeout = 5


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _run_retry_sequence(monkeypatch, outcomes):
    """用给定序列（CompletedProcess 或异常）驱动 run_pytest_with_retry。"""
    from src.agents import executor_runtime as er

    items = iter(outcomes)

    def _fake_run_with_timeout(*_args, **_kwargs):
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(er, "run_with_timeout", _fake_run_with_timeout)
    return run_pytest_with_retry(_RetrySelf(), ["pytest"], {}, ".")


class TestExecutionAttemptRecords:
    """run_pytest_with_retry：每次尝试记录（A16 根因层）。"""

    def test_fail_then_pass_preserves_both_attempts(self, monkeypatch):
        """首败次过：两次尝试都保留；返回 rc 仍是最后一次（历史契约不变）。"""
        output, last_result = _run_retry_sequence(
            monkeypatch,
            [_fake_completed(1, "1 failed"), _fake_completed(0, "1 passed")],
        )

        assert output == "1 passed"  # 历史输出口径：最后一次执行输出
        assert last_result.returncode == 0  # 历史 passed 语义：最后一次 rc==0
        attempts = extract_execution_attempts(last_result)
        assert [a["attempt"] for a in attempts] == [1, 2]
        assert [a["returncode"] for a in attempts] == [1, 0]
        assert [a["passed"] for a in attempts] == [False, True]
        assert all(a["timed_out"] is False for a in attempts)
        assert observed_fail_then_pass(attempts) is True
        assert summarize_execution_attempts(attempts) == {
            "attempts": 2,
            "pass_count": 1,
            "fail_count": 1,
            "timed_out_count": 0,
            "fail_then_pass": True,
        }

    def test_single_success_records_one_attempt_not_flaky(self, monkeypatch):
        """首试即过：单条尝试记录，不是 fail→pass。"""
        _output, last_result = _run_retry_sequence(monkeypatch, [_fake_completed(0, "1 passed")])
        attempts = extract_execution_attempts(last_result)
        assert len(attempts) == 1
        assert attempts[0]["passed"] is True
        assert observed_fail_then_pass(attempts) is False

    def test_stable_double_failure_not_fail_then_pass(self, monkeypatch):
        """连续失败：保留两次失败记录，但不构成 fail→pass。"""
        _output, last_result = _run_retry_sequence(
            monkeypatch,
            [_fake_completed(1, "1 failed"), _fake_completed(2, "2 failed")],
        )
        attempts = extract_execution_attempts(last_result)
        assert [a["passed"] for a in attempts] == [False, False]
        assert observed_fail_then_pass(attempts) is False
        assert last_result.returncode == 2

    def test_timeout_early_return_embeds_attempts(self, monkeypatch):
        """早退（超时）无返回对象可挂属性：尝试记录内嵌 error_info（结构不变）。"""
        timeout_exc = subprocess.TimeoutExpired(cmd="pytest", output="partial", stderr="err", timeout=5)
        output, last_result = _run_retry_sequence(
            monkeypatch,
            [_fake_completed(1, "1 failed"), timeout_exc],
        )
        assert isinstance(last_result, tuple) and last_result[0] == "EARLY_RETURN"
        assert last_result[1]["type"] == "timeout"
        attempts = last_result[1]["attempts"]
        assert [a["passed"] for a in attempts] == [False, False]
        assert attempts[1]["timed_out"] is True
        assert "partial" in output

    def test_generic_exception_first_attempt_keeps_unavailable_marker(self, monkeypatch):
        """首试即抛通用异常：UNAVAILABLE 标记语义不变，attempts 内嵌。"""
        _output, last_result = _run_retry_sequence(monkeypatch, [RuntimeError("boom")])
        assert isinstance(last_result, tuple) and last_result[0] == "UNAVAILABLE"
        assert last_result[1]["type"] == "execution_exception"
        attempts = last_result[1]["attempts"]
        assert attempts[-1]["error_type"] == "execution_exception"
        assert attempts[-1]["passed"] is False

    def test_generic_exception_after_failed_attempt_retains_last_result(self, monkeypatch):
        """第二次抛通用异常：保留第 1 次有效结果（round9 P2 契约不变），
        第二次异常记录以 error_type 标注且不构成 fail→pass。"""
        _output, last_result = _run_retry_sequence(
            monkeypatch,
            [_fake_completed(1, "1 failed"), RuntimeError("boom")],
        )
        assert not isinstance(last_result, tuple)
        assert last_result.returncode == 1
        attempts = extract_execution_attempts(last_result)
        assert attempts[-1]["error_type"] == "execution_exception"
        assert observed_fail_then_pass(attempts) is False

    def test_summarize_empty_attempts_conservative(self):
        summary = summarize_execution_attempts([])
        assert summary["fail_then_pass"] is False and summary["attempts"] == 0


class TestExecutorAttemptPropagation:
    """executor 本地 / venv 沙箱链路：attempts 与 fail→pass 标记并入结果 dict。"""

    @staticmethod
    def _last_result_with_attempts(returncode: int) -> SimpleNamespace:
        last_result = _fake_completed(returncode, "1 passed")
        last_result.execution_attempts = [
            {"attempt": 1, "returncode": 1, "timed_out": False, "passed": False},
            {"attempt": 2, "returncode": returncode, "timed_out": False, "passed": returncode == 0},
        ]
        return last_result

    def test_local_path_propagates_fail_then_pass(self, monkeypatch, tmp_path):
        from src.agents.executor import ExecutorAgent

        target = tmp_path / "a16_local_mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=10, use_venv=False)
        monkeypatch.setattr(
            agent,
            "_run_pytest_with_retry",
            lambda *a, **k: ("1 passed", self._last_result_with_attempts(0)),
        )
        result = agent.execute("def test_f():\n    assert f() == 1\n", str(target))

        assert result["passed"] is True  # passed 语义不变（最后一次 rc==0）
        assert result["flaky_fail_then_pass"] is True
        assert [a["passed"] for a in result["execution_attempts"]] == [False, True]

    def test_sandbox_path_propagates_fail_then_pass(self, monkeypatch, tmp_path):
        import src.agents.executor_modes as executor_modes
        from src.agents.executor import ExecutorAgent

        target = tmp_path / "a16_sandbox_mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=10, use_venv=True)

        # 跳过真实依赖检测 / venv 创建（本用例只验证结果字段传递）
        monkeypatch.setattr(
            executor_modes,
            "_prepare_dependencies",
            lambda *a, **k: ({"PATH": ""}, str(__import__("sys").executable), "", None, set()),
        )
        monkeypatch.setattr(
            agent,
            "_run_pytest_with_retry",
            lambda *a, **k: ("1 passed", self._last_result_with_attempts(0)),
        )
        result = agent.execute("def test_f():\n    assert f() == 1\n", str(target))

        assert result["passed"] is True
        assert result["flaky_fail_then_pass"] is True
        assert result["execution_attempts"][0]["passed"] is False


class TestExecutorNodeFailThenPassConsumption:
    """_executor_node：按真实序列写 flaky 标记 + 保守处理 test_passed。"""

    @staticmethod
    def _state() -> dict:
        return {
            "target_file": "/tmp/does_not_exist_a16.py",
            "module_name": "a16_target_mod",
            "target_code": "def f():\n    return 1\n",
            "target_function": "f",
            "generated_test": "def test_f():\n    assert f() == 1\n",
            "iteration": 0,
            "max_iterations": 2,
        }

    def _run_node(self, monkeypatch, result: dict) -> dict:
        from src.graph import nodes as nodes_mod

        agent = MagicMock()
        agent.execute.return_value = dict(result)
        monkeypatch.setattr(nodes_mod, "ENABLE_RAG", False)
        monkeypatch.setattr(nodes_mod, "_trace_node", lambda *a, **k: None)
        monkeypatch.setattr(nodes_mod, "publish_tests_executed", lambda *a, **k: None)
        monkeypatch.setattr(nodes_mod, "_get_or_create_executor_agent", lambda **k: agent)
        monkeypatch.delenv("FLAKY_CHECK_ENABLE", raising=False)
        monkeypatch.delenv("RUNTIME_PROBE_ENABLE", raising=False)
        monkeypatch.delenv("ROGUE_MONITOR_ENABLE", raising=False)
        monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
        return nodes_mod._executor_node(self._state())

    @staticmethod
    def _fail_then_pass_result() -> dict:
        return {
            "passed": True,
            "output": "1 passed",
            "coverage": 100.0,
            "failed_cases": [],
            "execution_attempts": [
                {"attempt": 1, "returncode": 1, "timed_out": False, "passed": False},
                {"attempt": 2, "returncode": 0, "timed_out": False, "passed": True},
            ],
            "flaky_fail_then_pass": True,
        }

    def test_fail_then_pass_marks_flaky_and_conservative_failure(self, monkeypatch):
        update = self._run_node(monkeypatch, self._fail_then_pass_result())

        assert update["test_passed"] is False  # 保守：不稳定结果不作修复正确证据
        assert update["flaky_detected"] is True
        assert update["flaky_unverified"] is True
        assert update["flaky_pass_count"] == 1
        assert update["flaky_total_count"] == 2

    def test_attempt_sequence_alone_suffices_without_explicit_flag(self, monkeypatch):
        """证据也可从真实序列推导（兼容只带 execution_attempts 的调用方）。"""
        result = self._fail_then_pass_result()
        result.pop("flaky_fail_then_pass")
        update = self._run_node(monkeypatch, result)
        assert update["test_passed"] is False
        assert update["flaky_detected"] is True
        assert update["flaky_unverified"] is True

    def test_normal_pass_keeps_history_fields(self, monkeypatch):
        update = self._run_node(
            monkeypatch,
            {"passed": True, "output": "1 passed", "coverage": 100.0, "failed_cases": []},
        )
        assert update["test_passed"] is True
        assert "flaky_detected" not in update
        assert "flaky_unverified" not in update

    def test_single_attempt_pass_keeps_history_fields(self, monkeypatch):
        update = self._run_node(
            monkeypatch,
            {
                "passed": True,
                "output": "1 passed",
                "coverage": 100.0,
                "failed_cases": [],
                "execution_attempts": [
                    {"attempt": 1, "returncode": 0, "timed_out": False, "passed": True},
                ],
            },
        )
        assert update["test_passed"] is True
        assert "flaky_detected" not in update

    def test_stable_failure_with_switch_off_keeps_history_fields(self, monkeypatch):
        update = self._run_node(
            monkeypatch,
            {
                "passed": False,
                "output": "1 failed",
                "coverage": 40.0,
                "failed_cases": [{"name": "test_f"}],
                "execution_attempts": [
                    {"attempt": 1, "returncode": 1, "timed_out": False, "passed": False},
                    {"attempt": 2, "returncode": 1, "timed_out": False, "passed": False},
                ],
            },
        )
        assert update["test_passed"] is False
        assert "flaky_detected" not in update
        assert "flaky_unverified" not in update

    def test_switch_on_does_not_rerun_detect_when_evidence_present(self, monkeypatch):
        """fail→pass 证据已在手：不再重复 detect_flaky 重测（省 subprocess）。"""
        spy = MagicMock(return_value={"flaky": False, "pass_count": 0, "total": 3, "fail_count": 3})
        monkeypatch.setattr("src.agents.flaky_gate.detect_flaky", spy)
        from src.graph import nodes as nodes_mod

        agent = MagicMock()
        agent.execute.return_value = dict(self._fail_then_pass_result())
        monkeypatch.setattr(nodes_mod, "ENABLE_RAG", False)
        monkeypatch.setattr(nodes_mod, "_trace_node", lambda *a, **k: None)
        monkeypatch.setattr(nodes_mod, "publish_tests_executed", lambda *a, **k: None)
        monkeypatch.setattr(nodes_mod, "_get_or_create_executor_agent", lambda **k: agent)
        monkeypatch.setenv("FLAKY_CHECK_ENABLE", "true")
        monkeypatch.delenv("RUNTIME_PROBE_ENABLE", raising=False)
        monkeypatch.delenv("ROGUE_MONITOR_ENABLE", raising=False)
        monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
        update = nodes_mod._executor_node(self._state())
        assert spy.call_count == 0
        assert update["flaky_unverified"] is True
