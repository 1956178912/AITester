"""BE 轮：生产路径的 ``rc==0`` 判绿点接"有效通过"谓词（2026-10-21）。

F03 同族（BA→BD 已收口 metrics / MDO）：pytest 对"没有任何断言执行"的
套件同样返回 rc==0（全 skip / xfail / xpass / deselect），只看退出码会把
"没跑起来"记成"修复正确"。本轮收口 **生产路径** 的判绿点：

1. ``detection_gates._run_test_against_code``：gold fixed 上全 skip →
   ``unavailable``（不是 "specific_red"，更不是 "over_red"）；
2. ``executor`` 本地路径 / venv 沙箱 / Docker：``passed`` 需有效通过，
   rc==0 但无证据时显式 ``error_info.type=no_effective_pass``；
3. ``executor_repo._run_test_nodes``：节点 rc==0 但全 skip 不得计 passed
   （F2P/P2P 的"无失败用例"判据随之失去假绿通道）；
4. ``patch_rollback.run_p2p_regression``：回归测试全 skip 不能证明补丁安全 →
   默认 ``regression_error`` / fail-closed 时 ``regression_failed``；
5. ``executor_runtime`` 尝试记录：新增 ``effective_pass``，fail→pass 的
   flaky 证据只认"含真实 passed"的 rc==0。

边界（与 BA→BD 完全一致）：部分 skip 与真实 passed 并存仍算有效通过；
摘要不可解析（空输出 / 自定义运行器）不算有效通过（fail-closed）。

零 LLM、零网络；行为用例走 mock 边界，另有真实 pytest 端到端锁。
"""

from __future__ import annotations

import inspect
import shutil
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.agents.executor_repo as repo_mod
from src.agents import executor as executor_mod
from src.agents import executor_modes as executor_modes_mod
from src.agents import executor_runtime as executor_runtime_mod
from src.agents.executor import ExecutorAgent
from src.agents.executor_repo import RepoExecutor
from src.tools import detection_gates, patch_rollback
from src.utils.pytest_output import run_has_effective_pass, suite_has_effective_pass

_GREEN = "1 passed in 0.01s"
_SKIPPED = "1 skipped in 0.01s"
_PARTIAL = "1 passed, 2 skipped in 0.02s"


class TestSharedPredicate:
    """单一口径：所有生产判绿点必须委托共享谓词，不得各写一套。"""

    @pytest.mark.parametrize(
        ("returncode", "output", "expected"),
        [
            (0, _GREEN, True),
            (0, _PARTIAL, True),
            (0, _SKIPPED, False),
            (0, "1 xfailed in 0.01s", False),
            (0, "1 xpassed in 0.01s", False),
            (0, "3 deselected in 0.01s", False),
            (0, "", False),
            (0, "1 passed, 1 failed in 0.02s", False),
            (1, _GREEN, False),
            (2, _GREEN, False),
            (None, _GREEN, False),
        ],
    )
    def test_run_has_effective_pass(self, returncode: int | None, output: str, expected: bool) -> None:
        assert run_has_effective_pass(returncode, output) is expected

    @pytest.mark.parametrize(
        "module",
        [executor_mod, executor_modes_mod, executor_runtime_mod, detection_gates, patch_rollback],
    )
    def test_sites_import_the_shared_predicate(self, module: Any) -> None:
        src = inspect.getsource(module)
        assert "src.utils.pytest_output" in src, f"{module.__name__} 未接共享谓词"
        assert "effective_pass" in src


class TestWarningBodyPollution:
    """R04（2026-10-23 全量集中复审 P1）：标准 warning 正文不得冒充测试结果。

    pytest 标准输出含 warnings summary 与源代码原文（官方文档可核）；旧共享
    解析对整个输出 finditer 取首个计数匹配，warning 正文可制造假绿（反例 A）
    或假红（反例 B）。修复后计数只从权威摘要行解析（剥掉计数 token 后只剩
    分隔符的行，多条命中取最后一条），无权威摘要行 fail-closed 空 dict。

    对应报告 M02 复现命令：A 当前 True/正确 False；B 当前 False/正确 True。
    """

    # 反例 A：warning 正文 "1 passed" + 真实全 skip（rc0）——不得假绿
    _CASE_A = "warnings summary\nUserWarning: 1 passed\n=== 1 skipped, 1 warning in 0.01s ==="
    # 反例 B：warning 正文 "1 failed validation" + 真实 1 passed（rc0）——不得假红
    _CASE_B = "warnings summary\nUserWarning: 1 failed validation\n=== 1 passed, 1 warning in 0.01s ==="

    def test_case_a_full_skip_not_poisoned_by_warning(self):
        assert suite_has_effective_pass(self._CASE_A) is False
        assert run_has_effective_pass(0, self._CASE_A) is False

    def test_case_b_real_pass_not_poisoned_by_warning(self):
        assert suite_has_effective_pass(self._CASE_B) is True
        assert run_has_effective_pass(0, self._CASE_B) is True

    def test_counts_from_authoritative_line_only(self):
        from src.utils.pytest_output import pytest_summary_counts

        assert pytest_summary_counts(self._CASE_A) == {"skipped": 1}
        assert pytest_summary_counts(self._CASE_B) == {"passed": 1}

    def test_warning_body_without_summary_line_fails_closed(self):
        """无权威摘要行（warning 正文含计数）→ 空 dict，不判有效通过。"""
        from src.utils.pytest_output import pytest_summary_counts

        assert pytest_summary_counts("UserWarning: 1 passed\nUserWarning: 2 failed") == {}
        assert suite_has_effective_pass("UserWarning: 1 passed") is False

    def test_standard_full_output_still_parses(self):
        """对照：完整标准输出（session 头 + warnings summary + 终末摘要）正常解析。"""
        from src.utils.pytest_output import pytest_summary_counts

        full = (
            "============================= test session starts ==============================\n"
            "platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0\n"
            "collected 2 items\n\n"
            "test_x.py .s                                                      [100%]\n\n"
            "=========================== warnings summary ===========================\n"
            "test_x.py::test_a\n"
            "  /tmp/test_x.py:3: UserWarning: 1 passed\n"
            '    warnings.warn("1 passed")\n\n'
            "========================= 1 passed, 1 skipped, 1 warning in 0.02s =========================\n"
        )
        assert pytest_summary_counts(full) == {"passed": 1, "skipped": 1}

    def test_bare_summary_without_decorations_still_parses(self):
        """对照：BE 既有夹具的裸摘要（-q 模式 / 单测拼接）保持可解析。"""
        from src.utils.pytest_output import pytest_summary_counts

        assert pytest_summary_counts("1 passed in 0.01s") == {"passed": 1}
        assert pytest_summary_counts("2 passed, 1 skipped in 0.30s") == {"passed": 2, "skipped": 1}
        assert pytest_summary_counts("1 xfailed in 0.01s") == {"xfailed": 1}

    def test_last_summary_line_wins(self):
        """多条摘要命中取最后一条（终末状态），不取 warning 正文或早期行。"""
        from src.utils.pytest_output import pytest_summary_counts

        output = "1 passed in 0.01s\n=== 1 failed in 0.01s ==="
        assert pytest_summary_counts(output) == {"failed": 1}


class TestDetectionGateEffectivePass:
    """门①：gold fixed 上 rc==0 但无有效通过 → unavailable。"""

    @staticmethod
    def _patch_runner(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
        import experiments._m1_metrics as m1

        monkeypatch.setattr(m1, "_run_pytest_in_tmp", lambda *_a, **_k: result, raising=True)

    def test_all_skip_fixed_side_is_unavailable_not_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_runner(monkeypatch, (0, _SKIPPED, ""))
        out = detection_gates._run_test_against_code("def test_x(): pass", "X = 1", "mod")
        assert out is not None
        assert out["green"] is False
        assert out["unavailable"] is True

    def test_partial_skip_with_real_pass_is_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_runner(monkeypatch, (0, _PARTIAL, ""))
        out = detection_gates._run_test_against_code("def test_x(): pass", "X = 1", "mod")
        assert out is not None
        assert out["green"] is True and out["unavailable"] is False

    def test_specificity_verdict_treats_skip_as_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_runner(monkeypatch, (0, _SKIPPED, ""))
        verdict = detection_gates.specificity_verdict("def test_x(): pass", "X = 1", "mod")
        assert verdict == "unavailable"

    def test_execution_error_keeps_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_runner(monkeypatch, (2, "ERROR: collection failed", ""))
        out = detection_gates._run_test_against_code("def test_x(): pass", "X = 1", "mod")
        assert out is not None
        assert out["green"] is False and out["unavailable"] is True

    def test_real_pytest_runtime_skip_is_unavailable(self) -> None:
        """真实 pytest 端到端：运行期 skip 返回 rc==0 + "1 skipped"。"""
        test_code = "import pytest\n\ndef test_x():\n    pytest.skip('conditional')\n"
        out = detection_gates._run_test_against_code(test_code, "def f():\n    return 1\n", "mod")
        assert out is not None
        assert out["rc"] == 0
        assert out["green"] is False and out["unavailable"] is True


class TestExecutorLocalEffectivePass:
    """executor 本地路径：rc==0 但全 skip 不得记 passed。"""

    @staticmethod
    def _execute(tmp_path: Any, output: str) -> dict[str, Any]:
        target = tmp_path / "target.py"
        target.write_text("def x():\n    return 1\n", encoding="utf-8")
        with (
            patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry") as mock_retry,
            patch("src.agents.executor.ExecutorAgent._auto_fix_imports") as mock_fix,
        ):
            mock_fix.return_value = "def test_x(): pass"
            mock_retry.return_value = (output, MagicMock(returncode=0))
            return ExecutorAgent(use_venv=False).execute("def test_x(): pass", str(target))

    def test_all_skip_is_not_passed_and_discloses_type(self, tmp_path: Any) -> None:
        result = self._execute(tmp_path, _SKIPPED)
        assert result["passed"] is False
        assert result["failed_cases"] == []
        assert result["error_info"]["type"] == "no_effective_pass"

    def test_real_pass_is_passed_without_error_info(self, tmp_path: Any) -> None:
        result = self._execute(tmp_path, _GREEN)
        assert result["passed"] is True
        assert "error_info" not in result

    def test_partial_skip_with_real_pass_is_passed(self, tmp_path: Any) -> None:
        result = self._execute(tmp_path, _PARTIAL)
        assert result["passed"] is True
        assert "error_info" not in result


class TestExecutorSandboxEffectivePass:
    """venv 沙箱：同一判据（rc==0 + 有效通过）。"""

    @patch("src.agents.executor_runtime.run_with_timeout")
    def test_all_skip_is_not_passed(self, mock_run: MagicMock, tmp_path: Any) -> None:
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=_SKIPPED, stderr="")
        agent = ExecutorAgent(timeout=30, use_venv=True, auto_install_deps=False)
        result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))
        assert result["passed"] is False
        assert result["error_info"]["type"] == "no_effective_pass"

    @patch("src.agents.executor_runtime.run_with_timeout")
    def test_real_pass_is_passed(self, mock_run: MagicMock, tmp_path: Any) -> None:
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="2 passed\nTOTAL 100%", stderr="")
        agent = ExecutorAgent(timeout=30, use_venv=True, auto_install_deps=False)
        result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))
        assert result["passed"] is True
        assert "error_info" not in result


class TestExecutorDockerEffectivePass:
    """Docker 链路：同一判据（rc==0 + 有效通过）。"""

    @staticmethod
    def _execute(tmp_path: Any, stdout: str) -> dict[str, Any]:
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True)
        with (
            patch.object(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None),
            patch("src.utils.process_utils.run_with_timeout") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=stdout, stderr="")
            return agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))

    def test_all_skip_is_not_passed(self, tmp_path: Any) -> None:
        result = self._execute(tmp_path, _SKIPPED)
        assert result["passed"] is False
        assert result["error_info"]["type"] == "no_effective_pass"

    def test_real_pass_is_passed(self, tmp_path: Any) -> None:
        result = self._execute(tmp_path, _GREEN)
        assert result["passed"] is True
        assert "error_info" not in result


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> Any:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestRepoTestNodesEffectivePass:
    """仓库级节点执行：rc==0 + 全 skip 不得计入 passed。"""

    @staticmethod
    def _patch_run(monkeypatch: pytest.MonkeyPatch, *results: Any) -> None:
        items = iter(results)
        monkeypatch.setattr(repo_mod, "_run", lambda *_a, **_k: next(items), raising=True)

    def test_all_skip_node_is_recorded_as_failure(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_run(monkeypatch, _proc(0, _SKIPPED))
        out = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::t"])
        assert out["expected"] == 1 and out["passed"] == 0
        assert len(out["failed_cases"]) == 1
        assert "无有效通过" in out["failed_cases"][0]["error"]

    def test_real_pass_node_still_counts(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_run(monkeypatch, _proc(0, _GREEN))
        out = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::t"])
        assert out["passed"] == 1 and out["failed_cases"] == []

    def test_partial_skip_node_still_counts(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_run(monkeypatch, _proc(0, _PARTIAL))
        out = RepoExecutor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::t"])
        assert out["passed"] == 1 and out["failed_cases"] == []

    def test_real_pytest_runtime_skip_is_failure(self, tmp_path: Any) -> None:
        (tmp_path / "test_skip.py").write_text(
            "import pytest\n\ndef test_x():\n    pytest.skip('conditional')\n",
            encoding="utf-8",
        )
        out = RepoExecutor(use_venv=False)._run_test_nodes(str(tmp_path), ["test_skip.py::test_x"])
        assert out["passed"] == 0
        assert len(out["failed_cases"]) == 1
        assert "无有效通过" in out["failed_cases"][0]["error"]


class TestPatchRollbackEffectivePass:
    """P2P 回归：全 skip 的"通过"不能证明补丁安全。"""

    _TARGET = "def add(a, b):\n    return a + b\n"
    _SKIP_TEST = "import pytest\nfrom target_mod import add\n\n\ndef test_add():\n    pytest.skip('conditional')\n"
    _PARTIAL_TEST = (
        "import pytest\nfrom target_mod import add\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_skip():\n    pytest.skip('partial')\n"
    )

    def test_all_skip_is_regression_error_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PATCH_ROLLBACK_FAIL_CLOSED", raising=False)
        out = patch_rollback.run_p2p_regression(self._TARGET, self._SKIP_TEST, module_name="target_mod", timeout=60)
        assert out["verdict"] == "regression_error", out
        assert out["returncode"] == 0
        assert out.get("no_effective_pass") is True

    def test_all_skip_fails_closed_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "true")
        out = patch_rollback.run_p2p_regression(self._TARGET, self._SKIP_TEST, module_name="target_mod", timeout=60)
        assert out["verdict"] == "regression_failed", out

    def test_partial_skip_with_real_pass_is_verified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PATCH_ROLLBACK_FAIL_CLOSED", raising=False)
        out = patch_rollback.run_p2p_regression(self._TARGET, self._PARTIAL_TEST, module_name="target_mod", timeout=60)
        assert out["verdict"] == "verified", out
        assert "no_effective_pass" not in out


class TestExecutionAttemptEffectivePass:
    """重试层尝试记录：新增 effective_pass，fail→pass 只认有效通过。"""

    class _Self:
        timeout = 5

    def _run(self, monkeypatch: pytest.MonkeyPatch, *outcomes: Any):
        items = iter(outcomes)

        def _fake_run(*_args: Any, **_kwargs: Any) -> Any:
            item = next(items)
            if isinstance(item, BaseException):
                raise item
            return item

        monkeypatch.setattr(executor_runtime_mod, "run_with_timeout", _fake_run)
        return executor_runtime_mod.run_pytest_with_retry(self._Self(), ["pytest"], {}, ".")

    def test_rc0_without_effective_pass_is_not_fail_then_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _output, last = self._run(
            monkeypatch,
            _proc(1, "1 failed in 0.01s"),
            _proc(0, _SKIPPED),
        )
        attempts = executor_runtime_mod.extract_execution_attempts(last)
        assert [a["passed"] for a in attempts] == [False, True]
        assert [a["effective_pass"] for a in attempts] == [False, False]
        assert executor_runtime_mod.observed_fail_then_pass(attempts) is False

    def test_rc0_with_real_pass_is_fail_then_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _output, last = self._run(
            monkeypatch,
            _proc(1, "1 failed in 0.01s"),
            _proc(0, _GREEN),
        )
        attempts = executor_runtime_mod.extract_execution_attempts(last)
        assert [a["effective_pass"] for a in attempts] == [False, True]
        assert executor_runtime_mod.observed_fail_then_pass(attempts) is True

    def test_rc0_without_effective_pass_breaks_retry_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """执行层 rc==0 即停止重试（all-skip 重跑不会变成有效通过）。"""
        output, last = self._run(
            monkeypatch,
            _proc(0, _SKIPPED),
            _proc(0, _GREEN),  # 不应被消费
        )
        attempts = executor_runtime_mod.extract_execution_attempts(last)
        assert len(attempts) == 1
        assert attempts[0]["effective_pass"] is False
        assert output == _SKIPPED

    def test_timeout_attempt_has_no_effective_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        _output, last = self._run(
            monkeypatch,
            subprocess.TimeoutExpired(cmd="pytest", output="partial", timeout=5),
        )
        assert isinstance(last, tuple) and last[0] == "EARLY_RETURN"
        assert last[1]["attempts"][0]["effective_pass"] is False


class TestNoEffectivePassInfo:
    def test_error_info_is_json_serializable_and_typed(self) -> None:
        from src.agents.executor_output import build_no_effective_pass_info

        info = build_no_effective_pass_info(0, _SKIPPED)
        assert info["type"] == "no_effective_pass"
        assert info["returncode"] == 0
        assert info["summary"]["skipped"] == 1
        assert suite_has_effective_pass(_SKIPPED) is False
