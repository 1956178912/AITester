#!/usr/bin/env python3
"""B9（2026-11-05）：P2P 回归裁决必须说清"为什么没裁决"——超时/被杀/无有效通过与断言失败不是一件事。

背景（冒烟实测 + 代码核查）：`logic` 与 `safe` 两档都设 `PATCH_ROLLBACK_FAIL_CLOSED=true`，
冒烟 `test_run_20261105T115002Z` 里 8 条 `A-03 P2P 回归失败（rc=None）` 全部紧跟一条
`执行超时（>60s）`。超时在 fail-closed 下回滚是 R4b 的**既定策略**（"无法裁决 = 不能证明
补丁安全 = 回滚"），本轮不动它；本轮修的是两件让读数不可用的事：

1. **裁决不留理由**：`regression_failed` 出参只有 rc，而 rc 在超时腿被写成 None。于是
   结果行的 `patch_rollback_verdict="regression_failed"` 无法分辨"这版补丁真把测试跑坏了"
   与"本地 60s 没跑完"——前者是模型能力读数，后者是墙钟读数（本项目的墙钟瓶颈恰恰就在
   30/60/120s 档）。审计只能回到日志逐行对齐 snapshot 哈希。
2. **非超时的负 rc 落进断言失败腿**：`rc is not None and rc >= 2` 与 `rc == 0` 都不成立时
   一律 `regression_failed`，因此被信号杀死（OOM/rlimit，rc<0 且 `timed_out=False`）的套件
   被判"断言级回归"——与本仓 `_looks_like_test_execution_error` 的口径（rc>=2 / 负 rc =
   "根本没跑起来"）相反。fail-closed 关闭的历史档下这会**误杀**好补丁。

全部用例零 LLM；子进程真执行（被信号杀死用 `os.kill(getpid(), SIGKILL)` 真实复现，不 mock
退出码）。
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

import experiments.run_benchmark as rb_mod
import src.tools.patch_rollback as pr_mod
from src.tools.patch_rollback import PatchRollbackProtocol, run_p2p_regression

_TARGET = "def add(a, b):\n    return a + b\n"
_PASSING_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
_FAILING_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 99\n"
_BROKEN_TEST = "def broken(:\n    pass\n"
# rc=0 但没有任何断言真的执行（全 skip）——"没跑起来"，不是"通过"
_SKIPPED_TEST = "import pytest\n\n\n@pytest.mark.skip(reason='no material')\ndef test_a():\n    pass\n"
# 套件自己把自己杀掉：pytest 进程 rc=-9 且 timed_out=False（OOM/rlimit 的真实形状）
_KILLED_TEST = "import os\nimport signal\n\nos.kill(os.getpid(), signal.SIGKILL)\n"
# 必然超时（timeout=1）
_SLOW_TEST = "import time\n\n\ndef test_slow():\n    time.sleep(30)\n"


def _verdict(test_code: str, monkeypatch: pytest.MonkeyPatch, *, fail_closed: bool, timeout: int = 60) -> dict:
    monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "true" if fail_closed else "false")
    return run_p2p_regression(_TARGET, test_code, module_name="target_mod", timeout=timeout)


class TestUnrunSuiteIsNotAssertionFailure:
    """负 rc（被信号杀死）属"根本没跑起来"，不得走断言失败腿。"""

    def test_killed_suite_is_regression_error_when_fail_open(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_KILLED_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_error", f"被信号杀死的套件被当成断言级回归：{out}"
        assert out["returncode"] is not None and out["returncode"] < 0

    def test_killed_suite_still_fails_closed_when_enabled(self, monkeypatch: pytest.MonkeyPatch):
        """fail-closed 策略不变（无法裁决仍回滚），但理由必须留下。"""
        out = _verdict(_KILLED_TEST, monkeypatch, fail_closed=True)
        assert out["verdict"] == "regression_failed", out
        assert out["reason"] == "killed_by_signal", out

    def test_killed_suite_reason_is_not_assertion_failure(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_KILLED_TEST, monkeypatch, fail_closed=False)
        assert out["reason"] == "killed_by_signal", out

    def test_assertion_failure_keeps_its_own_reason(self, monkeypatch: pytest.MonkeyPatch):
        """反向腿：真断言失败不得被折进"没跑起来"——否则坏补丁被放行。"""
        out = _verdict(_FAILING_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_failed", out
        assert out["returncode"] == 1
        assert out["reason"] == "assertion_failure", out


class TestReasonOnEveryVerdict:
    """每条裁决都自带理由，且理由值域固定（供行级对账与归因）。"""

    def test_no_oracle_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict("   ", monkeypatch, fail_closed=False)
        assert out["verdict"] == "no_oracle" and out["reason"] == "no_oracle", out

    def test_verified_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_PASSING_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "verified" and out["reason"] == "verified", out

    def test_collect_error_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_BROKEN_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_error" and out["reason"] == "collect_error", out

    def test_no_effective_pass_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_SKIPPED_TEST, monkeypatch, fail_closed=False)
        assert out["reason"] == "no_effective_pass", out
        assert out["verdict"] == "regression_error", out

    def test_timeout_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        out = _verdict(_SLOW_TEST, monkeypatch, fail_closed=False, timeout=1)
        assert out["verdict"] == "regression_error" and out["reason"] == "timeout", out

    def test_timeout_fail_closed_keeps_rollback_and_names_the_reason(self, monkeypatch: pytest.MonkeyPatch):
        """冒烟里那 8 条的形状：回滚照旧，但读数能分辨它是墙钟不是能力。"""
        out = _verdict(_SLOW_TEST, monkeypatch, fail_closed=True, timeout=1)
        assert out["verdict"] == "regression_failed" and out["reason"] == "timeout", out
        assert out["returncode"] is None

    def test_io_error_leg_has_reason(self, monkeypatch: pytest.MonkeyPatch):
        """IO 异常用真异常触发（不 mock 退出码，只让底层必抛）。"""

        class _Boom:
            def __call__(self, *a, **kw):
                raise OSError("disk full")

        monkeypatch.setattr("src.utils.process_utils.run_with_timeout", _Boom())
        out = _verdict(_PASSING_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_error" and out["reason"] == "io_error", out


class TestProtocolPropagatesReason:
    """协议出参把理由交给调用方（图内节点与行级工件的唯一来源）。"""

    @staticmethod
    def _apply(code: str, _patch: str):
        return code, True

    def test_reason_reaches_the_protocol_result(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "false")
        pr = PatchRollbackProtocol()
        res = pr.run(
            original_code=_TARGET,
            patch="# patched\n",
            test_code=_FAILING_TEST,
            module_name="target_mod",
            apply_fn=self._apply,
        )
        assert res["verdict"] == "regression_failed", res
        assert res["p2p_reason"] == "assertion_failure", res
        assert res["rolled_back"] is True

    def test_timeout_reason_reaches_the_protocol_under_fail_closed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "true")
        monkeypatch.setattr(pr_mod, "_p2p_timeout", lambda: 1)
        res = PatchRollbackProtocol().run(
            original_code=_TARGET,
            patch="# patched\n",
            test_code=_SLOW_TEST,
            module_name="target_mod",
            apply_fn=self._apply,
        )
        assert res["verdict"] == "regression_failed" and res["p2p_reason"] == "timeout", res
        assert res["rolled_back"] is True, "fail-closed 的回滚行为不得因新增理由字段而漂移"

    def test_apply_failed_has_no_p2p_reason(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "false")

        def _reject(_code: str, _patch: str):
            return _code, False

        res = PatchRollbackProtocol().run(
            original_code=_TARGET,
            patch="bad",
            test_code=_PASSING_TEST,
            module_name="target_mod",
            apply_fn=_reject,
        )
        assert res["verdict"] == "apply_failed" and res["p2p_reason"] is None, res


class TestSourceLocks:
    """源码锁：口径写进代码，不靠注释。"""

    def test_negative_rc_leg_exists_in_source(self):
        src = inspect.getsource(pr_mod.run_p2p_regression)
        assert '"killed_by_signal"' in src, "负 rc 腿不存在 ⇒ 被信号杀死仍落断言失败腿"
        assert src.index('"killed_by_signal"') < src.index('"assertion_failure"'), "断言失败腿排在前面会吞掉负 rc"


class TestStateCarriesTheReason:
    """图内把理由写进 state（行级工件的唯一来源；缺席记 None，不写"unknown"）。"""

    @staticmethod
    def _state(tmp_path, original: str) -> dict:
        target = tmp_path / "mod.py"
        target.write_text(original)
        return {
            "target_code": original,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
        }

    def _env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "true")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out：本用例主题是 A-03 回滚协议的读数，需要补丁先成功写盘
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")

    def test_reason_from_the_protocol_reaches_the_update(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        from src.graph.nodes import _patch_applier_node
        from src.tools.patch_rollback import PatchRollbackProtocol

        self._env(monkeypatch)
        state = self._state(tmp_path, "def f():\n    return 1\n")
        with patch.object(
            PatchRollbackProtocol,
            "run",
            return_value={
                "verdict": "regression_failed",
                "p2p_reason": "timeout",
                "rolled_back": True,
                "snapshot_id": "snap1",
                "p2p_returncode": None,
            },
        ):
            update = _patch_applier_node(state)  # type: ignore[arg-type]
        assert update["patch_rollback_verdict"] == "regression_failed"
        assert update["patch_rollback_reason"] == "timeout", "超时回滚与断言回滚在行里必须能分开"

    def test_missing_reason_is_recorded_as_none_not_dropped(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        from src.graph.nodes import _patch_applier_node
        from src.tools.patch_rollback import PatchRollbackProtocol

        self._env(monkeypatch)
        state = self._state(tmp_path, "def f():\n    return 1\n")
        with patch.object(
            PatchRollbackProtocol,
            "run",
            return_value={"verdict": "verified", "rolled_back": False, "snapshot_id": "snap2"},
        ):
            update = _patch_applier_node(state)  # type: ignore[arg-type]
        assert "patch_rollback_reason" in update, "键不得因上游没给就消失"
        assert update["patch_rollback_reason"] is None

    def test_switch_off_records_none_reason(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """开关关（协议未执行）⇒ 理由为 None，不写任何结论文本。"""
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "false")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        state = self._state(tmp_path, "def f():\n    return 1\n")
        update = _patch_applier_node(state)  # type: ignore[arg-type]
        assert update["patch_rollback_verdict"] == "not_enabled"
        assert update["patch_rollback_reason"] is None


class TestChannelIsDeclared:
    """未声明的键会被 LangGraph 静默丢弃（M14/O35 家族）——声明与初始化必须在场。"""

    def test_create_initial_state_has_the_channel(self):
        from src.graph.state import create_initial_state

        state = create_initial_state("b9-provenance", target_file="x.py", target_code="x = 1\n", max_iterations=1)
        assert "patch_rollback_reason" in state, "未声明 ⇒ 写入被丢弃，行里永远没有这一列"
        assert state["patch_rollback_reason"] is None


class TestRowExposesTheReason:
    """结果行与失败模板同键集（缺列即"这轮没记"，不是"没发生"）。"""

    def test_row_and_failure_template_carry_the_key(self):
        src = inspect.getsource(rb_mod)
        assert '"patch_rollback_reason": final_state.get("patch_rollback_reason")' in src, "成功分支漏列"
        assert '"patch_rollback_reason": None' in src, "失败分支漏占位 ⇒ 两分支键集合不同构"
