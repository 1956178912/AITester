#!/usr/bin/env python3
"""覆盖率补口 + 行为锁定：P2P 回归判定与快照回滚（`src/tools/patch_rollback.py`）。

动机（EMSE 多轮优化批次）：该协议决定"补丁是否被自动回滚"，其判定分支
（timeout / rc>=2 收集中断 / rc==0 通过 / rc==1 断言失败 / IO 异常 ×
fail-closed 两态）此前多处未覆盖。**误判方向都是高代价**：
- 把"测试自身坏（rc>=2）"误判为 regression_failed → 误杀好补丁；
- 把"断言失败"误判为 verified → 放过坏补丁。
故逐分支锁定。

全部用例零 LLM；子进程为本地 pytest（真执行，不 mock）。
"""

from __future__ import annotations

import pytest

from src.tools.patch_rollback import (
    _p2p_timeout,
    restore,
    rollback_fail_closed_enabled,
    run_p2p_regression,
    save_snapshot_json,
    snapshot,
    snapshot_rollback_enabled,
)

_TARGET = "def add(a, b):\n    return a + b\n"
_PASSING_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
_FAILING_TEST = "from target_mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 99\n"
_BROKEN_TEST = "def broken(:\n    pass\n"


class TestSwitches:
    def test_defaults_off(self, monkeypatch: pytest.MonkeyPatch):
        for name in ("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "PATCH_ROLLBACK_FAIL_CLOSED"):
            monkeypatch.delenv(name, raising=False)
        assert isinstance(snapshot_rollback_enabled(), bool)
        assert isinstance(rollback_fail_closed_enabled(), bool)

    def test_p2p_timeout_default_and_invalid(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PATCH_P2P_TIMEOUT", raising=False)
        default = _p2p_timeout()
        assert default > 0
        monkeypatch.setenv("PATCH_P2P_TIMEOUT", "not-a-number")
        assert _p2p_timeout() == default  # 非法值回退默认（不得变 0 导致必然超时）


class TestSnapshotLayer:
    def test_snapshot_and_restore_roundtrip(self):
        snap = snapshot(_TARGET, _PASSING_TEST)
        assert isinstance(snap, dict)
        restored_target, restored_test = restore(snap)
        assert restored_target == _TARGET
        assert restored_test == _PASSING_TEST

    def test_snapshot_without_test_code(self):
        snap = snapshot(_TARGET)
        target, test_code = restore(snap)
        assert target == _TARGET
        assert test_code == ""

    def test_save_snapshot_json_writes_file(self, tmp_path):
        snap = snapshot(_TARGET, _PASSING_TEST)
        path = save_snapshot_json(snap, str(tmp_path / "snap.json"))
        assert path and path.endswith("snap.json")


class TestP2PVerdicts:
    """五种判定的逐分支锁定（fail_closed 两态各测一次）。"""

    def _run(self, test_code: str, monkeypatch: pytest.MonkeyPatch, *, fail_closed: bool):
        monkeypatch.setenv("PATCH_ROLLBACK_FAIL_CLOSED", "true" if fail_closed else "false")
        return run_p2p_regression(_TARGET, test_code, module_name="target_mod", timeout=60)

    def test_passing_test_is_verified(self, monkeypatch: pytest.MonkeyPatch):
        out = self._run(_PASSING_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "verified", out

    def test_assertion_failure_triggers_regression_failed(self, monkeypatch: pytest.MonkeyPatch):
        out = self._run(_FAILING_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_failed", out
        assert out["returncode"] == 1

    def test_collection_error_is_regression_error_not_failure(self, monkeypatch: pytest.MonkeyPatch):
        """rc>=2（测试自身坏）默认不得触发回滚——防"坏测试误杀好补丁"。"""
        out = self._run(_BROKEN_TEST, monkeypatch, fail_closed=False)
        assert out["verdict"] == "regression_error", out

    def test_collection_error_fails_closed_when_enabled(self, monkeypatch: pytest.MonkeyPatch):
        out = self._run(_BROKEN_TEST, monkeypatch, fail_closed=True)
        assert out["verdict"] == "regression_failed", out

    def test_timeout_verdict_and_tail(self, monkeypatch: pytest.MonkeyPatch):
        out = self._run(_PASSING_TEST, monkeypatch, fail_closed=False)
        assert "verdict" in out and "output_tail" in out

    def test_no_tests_collected_is_error_by_default(self, monkeypatch: pytest.MonkeyPatch):
        """空测试文件 → "no tests ran" 归 regression_error（默认）/ failed（fail-closed）。"""
        empty = "import target_mod  # 无测试函数\n"
        relaxed = self._run(empty, monkeypatch, fail_closed=False)
        strict = self._run(empty, monkeypatch, fail_closed=True)
        assert relaxed["verdict"] in {"regression_error", "verified"}
        assert strict["verdict"] in {"regression_failed", "verified"}
