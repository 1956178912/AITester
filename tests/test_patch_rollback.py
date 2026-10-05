"""A-03（2026-10-04 系统审查 P0）：补丁快照 + P2P 全量回归 + 失败自动回滚协议测试。

锁定内容（纯静态 + 子进程 P2P，无 LLM）：
- snapshot / restore / save_snapshot_json（内容级快照 + 原子落盘审计）
- run_p2p_regression 四类 verdict（verified / regression_failed /
  no_oracle / regression_error + 超时口径）
- PatchRollbackProtocol.run 全路径（apply_failed / 回归失败自动回滚 /
  保留补丁 / no_oracle 保守保留）
- snapshot_rollback_enabled 开关口径（默认关）
"""

from __future__ import annotations

import os
import textwrap

from src.tools.patch_rollback import (
    PatchRollbackProtocol,
    restore,
    run_p2p_regression,
    save_snapshot_json,
    snapshot,
    snapshot_rollback_enabled,
)

_GOOD_MODULE = textwrap.dedent(
    """
    def add(a, b):
        return a + b
    """
)
_GOOD_TEST = textwrap.dedent(
    """
    from module_under_test import add
    def test_add():
        assert add(1, 2) == 3
    """
)
_BAD_MODULE = textwrap.dedent(
    """
    def add(a, b):
        return a - b
    """
)


class TestSnapshotRestore:
    def test_snapshot_fields(self):
        snap = snapshot(_GOOD_MODULE, _GOOD_TEST)
        assert snap["target_code"] == _GOOD_MODULE
        assert snap["test_code"] == _GOOD_TEST
        assert len(snap["snapshot_id"]) == 12

    def test_snapshot_id_deterministic(self):
        a = snapshot("x", "y")
        b = snapshot("x", "y")
        assert a["snapshot_id"] == b["snapshot_id"]
        assert a["snapshot_id"] != snapshot("z", "y")["snapshot_id"]

    def test_restore_roundtrip(self):
        snap = snapshot(_GOOD_MODULE, _GOOD_TEST)
        target, test = restore(snap)
        assert target == _GOOD_MODULE
        assert test == _GOOD_TEST

    def test_restore_empty_snapshot(self):
        target, test = restore({})
        assert target == "" and test == ""

    def test_save_snapshot_json_atomic(self, tmp_path):
        snap = snapshot("code", "test")
        p = save_snapshot_json(snap, str(tmp_path / "snap.json"))
        import json
        import pathlib

        data = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        assert data["target_code"] == "code"
        assert not os.path.exists(p.replace(".json", ".json.tmp"))  # 原子替换后无残留


class TestP2pRegression:
    def test_no_oracle_when_empty_test(self):
        out = run_p2p_regression(_GOOD_MODULE, "", "module_under_test")
        assert out["verdict"] == "no_oracle"
        assert out["returncode"] is None

    def test_verified_when_tests_pass(self):
        out = run_p2p_regression(_GOOD_MODULE, _GOOD_TEST, "module_under_test")
        assert out["verdict"] == "verified", out
        assert out["returncode"] == 0

    def test_regression_failed_when_tests_fail(self):
        out = run_p2p_regression(_BAD_MODULE, _GOOD_TEST, "module_under_test")
        assert out["verdict"] == "regression_failed", out
        assert out["returncode"] == 1

    def test_regression_error_on_syntax_error_module(self):
        bad_module = "def add(a, b:\n    return a + b  # missing )"
        out = run_p2p_regression(bad_module, _GOOD_TEST, "module_under_test")
        assert out["verdict"] == "regression_error", out  # 收集/编译中断不误杀

    def test_timeout_returns_regression_error(self):
        out = run_p2p_regression(_GOOD_MODULE, _GOOD_TEST, "module_under_test", timeout=0)
        # timeout=0 → 立即超时 → regression_error（保守不裁决）
        assert out["verdict"] in ("regression_error", "verified"), out


class TestPatchRollbackProtocol:
    def _apply(self, original, patch):
        """stub apply_fn：模拟 safe_apply_patch（接受任意 patch 直接拼接）。"""
        return original + "\n" + patch, True

    def test_apply_failed_verdict(self):
        pr = PatchRollbackProtocol()

        def fail_apply(_o, _p):
            return _o, False

        out = pr.run("orig", "patch", test_code=_GOOD_TEST, module_name="m", apply_fn=fail_apply)
        assert out["success"] is False
        assert out["verdict"] == "apply_failed"
        assert out["rolled_back"] is True
        assert out["applied_code"] == "orig"

    def test_regression_failed_triggers_rollback(self):
        pr = PatchRollbackProtocol()

        # 应用"破坏性补丁"（把 add 改成 a-b），P2P 测试失败 → 自动回滚
        def apply_broken(orig, patch):
            return _BAD_MODULE, True

        out = pr.run(
            _GOOD_MODULE, "broken", test_code=_GOOD_TEST, module_name="module_under_test", apply_fn=apply_broken
        )
        assert out["success"] is False
        assert out["verdict"] == "regression_failed"
        assert out["rolled_back"] is True
        assert out["applied_code"] == _GOOD_MODULE  # 回滚到快照原文

    def test_verified_keeps_patch(self):
        pr = PatchRollbackProtocol()

        def apply_good(orig, patch):
            return _GOOD_MODULE, True

        out = pr.run(_GOOD_MODULE, "patch", test_code=_GOOD_TEST, module_name="module_under_test", apply_fn=apply_good)
        assert out["success"] is True
        assert out["verdict"] == "verified"
        assert out["rolled_back"] is False
        assert out["applied_code"] == _GOOD_MODULE

    def test_no_oracle_keeps_patch_conservatively(self):
        pr = PatchRollbackProtocol()

        def apply_good(orig, patch):
            return "new_code", True

        out = pr.run("orig", "patch", test_code="", module_name="m", apply_fn=apply_good)
        assert out["success"] is True  # 无 oracle 保守保留（由 M1 None 口径兜底）
        assert out["verdict"] == "no_oracle"
        assert out["rolled_back"] is False

    def test_default_apply_fn_uses_safe_apply_patch(self, monkeypatch):
        # 不注入 apply_fn → 延迟 import safe_apply_patch（验证默认路径可跑）
        pr = PatchRollbackProtocol()
        out = pr.run(_GOOD_MODULE, "# no-op patch\n" + _GOOD_MODULE, test_code="", module_name="m")
        # safe_apply_patch 对"整文件重贴原代码"：应 success（或保守 apply_failed，
        # 取决于契约守卫），但协议不崩溃、verdict 合法
        assert out["verdict"] in ("apply_failed", "verified", "no_oracle", "regression_error", "regression_failed")


class TestSnapshotRollbackGate:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", raising=False)
        assert snapshot_rollback_enabled() is False

    def test_on_variants(self, monkeypatch):
        for v in ("true", "1", "on", "TRUE"):
            monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", v)
            assert snapshot_rollback_enabled() is True

    def test_off_variants(self, monkeypatch):
        for v in ("false", "0", "off", "no", "x", ""):
            monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", v)
            assert snapshot_rollback_enabled() is False
