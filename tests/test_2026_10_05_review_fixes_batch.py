"""2026-10-05 系统审查修复批次回归测试（C6 / W12）。

背景（对应审查报告编号）：
- C6a：M6 回滚只恢复磁盘不恢复 state["target_code"]——下一轮 Debugger
  分析/补丁基底仍是坏补丁代码（"测原码/修补码"幻象迭代）。
  修复：_rollback_last_patch 经 restored_out 出参携带快照原文，
  _executor_node 把它写回 state["target_code"]。
- C6b：A-03 P2P 回归失败回滚只改 state（effective_code=original_code）
  不写回 target_file——磁盘仍保留坏补丁，下一轮 executor 读盘测到的
  是"已回滚"的代码。修复：回滚分支原子写回原文；落盘失败时如实记
  rolled_back=False。
- W12：M6 快照失败仅 WARNING 后照常写盘——无快照即无回滚能力，
  坏补丁永久落盘。修复：fail-closed 拒绝写盘。

全部零 LLM / 零网络（A-03 协议经 patch.object mock，写盘走 tmp_path）。
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

# ─── C6a：_rollback_last_patch restored_out 出参 ─────────────────────────────


class TestRollbackRestoredOut:
    def test_restored_out_carries_snapshot_content(self, tmp_path):
        """回滚成功时 restored_out["content"] = 快照原文（供 executor 写回 target_code）。"""
        from src.graph.nodes import _rollback_last_patch

        target = tmp_path / "f.py"
        target.write_text("bad_patched_code\n")
        snap = tmp_path / "snap"
        snap.write_text("original_code\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(snap)}
        restored: dict = {}
        out = _rollback_last_patch(state, restored_out=restored)
        assert out is True
        assert restored.get("content") == "original_code\n"

    def test_restored_out_omitted_keeps_bool_contract(self, tmp_path):
        """不传 restored_out 时行为与历史口径一致（bool 返回值）。"""
        from src.graph.nodes import _rollback_last_patch

        target = tmp_path / "f.py"
        target.write_text("bad\n")
        snap = tmp_path / "snap"
        snap.write_text("good\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(snap)}
        assert _rollback_last_patch(state) is True
        assert target.read_text() == "good\n"

    def test_rollback_failure_leaves_restored_out_empty(self, tmp_path, monkeypatch):
        """回滚失败（写盘异常）→ False 且 restored_out 不携带内容。"""
        import src.graph.nodes as nodes_mod
        import src.graph.patch_io as patch_io

        target = tmp_path / "f.py"
        target.write_text("patched\n")
        snap = tmp_path / "snap"
        snap.write_text("original\n")
        state = {"target_file": str(target), "_last_patch_snapshot": str(snap)}

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(patch_io, "_write_file_atomic", _boom)
        restored: dict = {}
        assert nodes_mod._rollback_last_patch(state, restored_out=restored) is False
        assert "content" not in restored


# ─── W12：_safe_write_patch 快照失败 fail-closed ─────────────────────────────


class TestSafeWritePatchSnapshotFailClosed:
    def test_snapshot_failure_refuses_write(self, tmp_path, monkeypatch):
        """快照 copy2 异常 → 拒绝写盘（W12：无快照即无回滚能力）。"""
        import src.graph.nodes as nodes_mod
        import src.graph.patch_io as patch_io

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        original = "def f():\n    return 1\n"
        target.write_text(original)
        state = {"target_file": str(target), "iteration": 0}

        def _boom(*_a, **_k):
            raise OSError("snapshot io error")

        monkeypatch.setattr(patch_io.shutil, "copy2", _boom)
        out = nodes_mod._safe_write_patch(original, "def f():\n    return 2\n", True, state)
        assert out is False
        assert target.read_text() == original, "快照失败时不得写入新代码"

    def test_snapshot_ok_still_writes(self, tmp_path, monkeypatch):
        """快照正常 → 写盘行为不变（回归守卫）。"""
        from src.graph.nodes import _safe_write_patch

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        target = tmp_path / "f.py"
        original = "def f():\n    return 1\n"
        target.write_text(original)
        state = {"target_file": str(target), "iteration": 0}
        out = _safe_write_patch(original, "def f():\n    return 2\n", True, state)
        assert out is True
        assert target.read_text() == "def f():\n    return 2\n"


# ─── C6b：A-03 回归失败回滚必须恢复磁盘 ──────────────────────────────────────


class TestA03RollbackRestoresDisk:
    """节点级：P2P 回归失败 → 磁盘与 state 同步恢复原文。"""

    def _state(self, tmp_path, original: str) -> dict:
        target = tmp_path / "mod.py"
        target.write_text(original)
        return {
            "target_code": original,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
        }

    def test_regression_failed_restores_disk_and_state(self, tmp_path, monkeypatch):
        """C6b 回归锁：回滚分支必须把原文原子写回 target_file。"""
        from src.graph.nodes import _patch_applier_node
        from src.tools.patch_rollback import PatchRollbackProtocol

        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "true")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out（2026-10-05 P0 真阻断）：本用例主题是 A-03 回滚协议，
        # 需要补丁先成功写盘；无证据补丁在 gate 默认开时会被证据门先行拒绝
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original)
        target = tmp_path / "mod.py"

        with patch.object(
            PatchRollbackProtocol,
            "run",
            return_value={"verdict": "regression_failed", "rolled_back": True, "snapshot_id": "snap42"},
        ):
            update = _patch_applier_node(state)  # type: ignore[arg-type]

        # 磁盘恢复原文（此前 bug：磁盘保留坏补丁）
        assert target.read_text() == original, "A-03 回滚后磁盘必须恢复原文"
        # state 侧同口径
        assert update["target_code"] == original
        assert update["patch_rollback_verdict"] == "regression_failed"
        assert update["patch_rolled_back"] is True

    def test_disk_restore_failure_reports_not_rolled_back(self, tmp_path, monkeypatch):
        """C6b 诚实口径：回滚落盘失败 → patch_rolled_back=False（不虚报已恢复）。"""
        import src.graph.nodes as nodes_mod
        from src.tools.patch_rollback import PatchRollbackProtocol

        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "true")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out（同 test_a03_rollback_restores_disk）：本用例主题是
        # A-03 回滚落盘失败，需要补丁先成功写盘（否则证据门先行拒绝，written=False，
        # A-03 分支不触发 → verdict 恒 not_enabled，无法测"回滚落盘失败"口径）。
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original)
        target = tmp_path / "mod.py"

        # S4 拆分后：补丁落盘走 patch_io._write_file_atomic（真实写盘，成功），
        # A-03 回滚恢复原文走 nodes_mod._write_file_atomic（本测试 mock 成恒抛
        # 异常）——验证回滚落盘失败时 patch_rolled_back=False 的诚实口径
        # （磁盘如实保留坏补丁，state 侧仍恢复原文）。
        def _boom_write(*_a, **_k):
            raise OSError("disk full")

        with (
            patch.object(
                PatchRollbackProtocol,
                "run",
                return_value={"verdict": "regression_failed", "rolled_back": True, "snapshot_id": "snap42"},
            ),
            patch.object(nodes_mod, "_write_file_atomic", _boom_write),
        ):
            update = nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]

        assert update["patch_rollback_verdict"] == "regression_failed"
        assert update["patch_rolled_back"] is False, "落盘失败不得虚报 rolled_back=True"
        # 磁盘如实保留坏补丁（恢复失败），state 侧仍恢复原文
        # （下一轮以原文为基底，不再叠加坏补丁）
        assert target.read_text() == "def f():\n    return 2\n"
        assert update["target_code"] == original

    def test_verified_verdict_keeps_patch_on_disk(self, tmp_path, monkeypatch):
        """回归守卫：verdict=verified → 保留补丁（磁盘为新代码）。"""
        from src.graph.nodes import _patch_applier_node
        from src.tools.patch_rollback import PatchRollbackProtocol

        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "true")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out（2026-10-05 P0 真阻断）：同上，A-03 主题需要补丁先写盘
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original)
        target = tmp_path / "mod.py"

        with patch.object(
            PatchRollbackProtocol,
            "run",
            return_value={"verdict": "verified", "rolled_back": False, "snapshot_id": "snap42"},
        ):
            update = _patch_applier_node(state)  # type: ignore[arg-type]

        assert target.read_text() == "def f():\n    return 2\n"
        assert update["patch_rolled_back"] is False
        assert update["target_code"] == "def f():\n    return 2\n"


# ─── C8：任务级记账跨线程传播（专家池预算绕过修复）──────────────────────────


class TestCrossThreadAccounting:
    def test_attach_usage_propagates_to_worker_thread(self):
        """工作线程 attach 任务实例后，记账回到任务作用域。"""
        from src.graph.token_usage import attach_usage, get_usage, record_usage, reset

        reset()
        record_usage(100, 50, "main")
        task_usage = get_usage()

        def worker():
            attach_usage(task_usage)
            record_usage(10, 5, "expert")

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert get_usage().total_tokens == 165, "父线程必须看到工作线程的记账"

    def test_global_usage_no_double_count_for_shared_instance(self):
        """共享实例不因多线程绑定在 global_usage 中重复累计。"""
        from src.graph.token_usage import attach_usage, get_usage, global_usage, record_usage, reset

        reset()
        task_usage = get_usage()
        before = global_usage().total_tokens

        def worker():
            attach_usage(task_usage)
            record_usage(10, 5, "expert")

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 3 个工作线程各记 15：全局只累计一次实例（45），不按线程数翻倍
        assert global_usage().total_tokens - before == 45

    def test_attach_budget_enforces_limit_across_threads(self, monkeypatch):
        """专家池场景回归锁：worker 超额消耗必须触发任务级预算超限。"""
        import src.graph.cost_budget as cb

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100")
        cb.reset_budget()
        assert cb.record_usage_and_check(90, 0) is True
        snap = cb.current_budget()

        def worker():
            cb.attach_budget(snap)
            assert cb.record_usage_and_check(20, 0) is False  # 110 >= 100

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert cb.is_budget_exceeded() is True, "父线程（任务）必须看到 worker 触发的超限"

    def test_budget_concurrent_records_no_lost_update(self, monkeypatch):
        """C8 并发正确性：多线程共享实例并发记账无丢更新。"""
        import src.graph.cost_budget as cb

        monkeypatch.setenv("COST_BUDGET_ENABLE", "true")
        monkeypatch.setenv("COST_BUDGET_TOKENS", "100000")
        cb.reset_budget()
        snap = cb.current_budget()
        barrier = threading.Barrier(8)

        def worker():
            cb.attach_budget(snap)
            barrier.wait()
            for _ in range(50):
                cb.record_usage_and_check(10, 0)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert cb.current_budget().consumed_tokens == 8 * 50 * 10

    def test_expert_pool_wiring_attaches_accounting(self):
        """源码接线锁：_run_expert 工作线程首行绑定任务记账实例。"""
        import inspect

        import src.graph.expert_pool as ep

        src = inspect.getsource(ep)
        assert "attach_usage(_task_usage)" in src
        assert "attach_budget(_task_budget)" in src


# ─── C10：修复案例验证门入库（RAG 记忆去污染）─────────────────────────────────


class TestRepairCaseVerificationGate:
    """补丁只有经 executor 验证通过才进入修复案例库（add_repair）。

    此前 _debugger_node 每轮无条件 add_repair——失败/被回滚的补丁成为
    后续任务的"参考修复案例"（记忆污染）。修复后链路：
    _patch_applier_node 暂存 last_applied_repair → executor 验证通过
    才入库并消费；失败轮清除暂存。
    """

    def test_applier_stashes_repair_on_successful_write(self, tmp_path, monkeypatch):
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out（2026-10-05 P0 真阻断）：本用例主题是暂存协议，
        # 需要无证据补丁也能成功写盘（历史口径）
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        target = tmp_path / "mod.py"
        target.write_text(original)
        state = {
            "target_code": original,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "error_category": "logic_error",
            "iteration": 0,
        }
        update = _patch_applier_node(state)  # type: ignore[arg-type]
        stash = update.get("last_applied_repair")
        assert stash is not None, "写盘成功必须暂存待验证补丁"
        assert stash["original_code"] == original
        assert stash["patch"] == "def f():\n    return 2\n"
        assert stash["error_category"] == "logic_error"

    def test_applier_clears_stash_on_rollback(self, tmp_path, monkeypatch):
        """A-03 回归失败回滚（written=False）→ 暂存清除（不入库）。"""
        from src.graph.nodes import _patch_applier_node
        from src.tools.patch_rollback import PatchRollbackProtocol

        monkeypatch.setenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE", "true")
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        # 证据门 opt-out（2026-10-05 P0 真阻断）：本用例主题是暂存协议，
        # 需要无证据补丁也能成功写盘（历史口径）
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        target = tmp_path / "mod.py"
        target.write_text(original)
        state = {
            "target_code": original,
            "patch": "def f():\n    return 2\n",
            "target_file": str(target),
            "module_name": "mod",
            "error_category": "logic_error",
            "iteration": 0,
        }
        with patch.object(
            PatchRollbackProtocol,
            "run",
            return_value={"verdict": "regression_failed", "rolled_back": True, "snapshot_id": "snap"},
        ):
            update = _patch_applier_node(state)  # type: ignore[arg-type]
        assert update.get("last_applied_repair") is None, "回滚轮不得暂存补丁"

    def test_applier_clears_stash_when_write_rejected(self, tmp_path, monkeypatch):
        """命名契约拒绝（applied=False 不写盘）→ 暂存清除。"""
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        original = "def f():\n    return 1\n"
        target = tmp_path / "mod.py"
        target.write_text(original)
        state = {
            "target_code": original,
            "patch": "def g():\n    return 2\n",  # 删除原符号 f → 契约拒绝
            "target_file": str(target),
            "module_name": "mod",
            "iteration": 0,
        }
        update = _patch_applier_node(state)  # type: ignore[arg-type]
        assert update.get("last_applied_repair") is None

    def test_debugger_no_longer_calls_add_repair(self):
        """接线锁：_debugger_node 不再无条件 add_repair（验证门移至 executor）。"""
        import inspect

        from src.graph.nodes import _debugger_node

        src = inspect.getsource(_debugger_node)
        assert "r.add_repair" not in src, "debugger 节点不得直接入库未验证补丁"
        assert '"add_repair"' not in src

    def test_executor_commits_on_pass_and_clears_on_fail(self):
        """接线锁：executor 验证通过消费暂存 / 失败轮清除暂存。"""
        import inspect

        from src.graph.nodes import _executor_node

        src = inspect.getsource(_executor_node)
        assert '"add_repair"' in src, "executor 必须承载验证门入库"
        assert "last_applied_repair" in src
        # 失败轮清除（M6 分支同段）
        assert 'update["last_applied_repair"] = None' in src


# ─── O1：AITESTER_PROFILE=logic 逻辑链全开档 ──────────────────────────────────


class TestLogicProfilePreset:
    """logic 档 = scientific 超集 + 逻辑链强化开关（2026-10-05 审查 O1）。

    setdefault 绕过 monkeypatch 追踪——本类自带 env 保存/恢复（与 R15
    测试的 _cleanup_env 同模式）。
    """

    _INJECTED: tuple[str, ...] = (
        "SPEC_IR_ENABLE",
        "SPEC_IR_DSL_ENABLE",
        "SPEC_ORACLE_EXEC_ENABLE",
        "ENABLE_MUTATION_SCORING",
        "ORACLE_VALIDATE_ENABLE",
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE",
        "LOGIC_SPEC_STRICT_ENABLE",
        "DETERMINISTIC_GUARD_ENABLE",
        "BRANCH_COVERAGE_INJECT_ENABLE",
        "ROUTE_STRUCTURED_ENABLE",
        # U12（2026-10-05 系统性审查落地）：logic/scientific 档补齐项
        "SPEC_SMT_ENABLE",
        "PATCH_ROLLBACK_FAIL_CLOSED",
    )

    def test_logic_profile_injects_full_logic_chain(self, monkeypatch):
        import os as _os

        from config import _apply_profile_presets

        saved = {k: _os.environ.get(k) for k in self._INJECTED}
        try:
            monkeypatch.setenv("AITESTER_PROFILE", "logic")
            assert _apply_profile_presets() == "logic"
            for key in self._INJECTED:
                assert _os.environ.get(key) == "true", f"logic 档应注入 {key}=true"
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v

    def test_logic_profile_respects_explicit_override(self, monkeypatch):
        import os as _os

        from config import _apply_profile_presets

        saved = {k: _os.environ.get(k) for k in self._INJECTED}
        try:
            monkeypatch.setenv("AITESTER_PROFILE", "logic")
            monkeypatch.setenv("ROUTE_STRUCTURED_ENABLE", "false")  # 显式关闭优先
            _apply_profile_presets()
            assert _os.environ.get("ROUTE_STRUCTURED_ENABLE") == "false"
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v


@pytest.mark.unit
class TestExecutorRollbackRestoresStateTargetCode:
    """executor 节点 M6 回滚分支：update dict 携带恢复后的 target_code。

    直接驱动 _executor_node 成本高（需 mock ExecutorAgent 全链路），此处
    锁定"分支组合口径"：_rollback_last_patch 出参 → update["target_code"]
    的接线由 A-03/C6b 节点级测试与上面 restored_out 单测共同覆盖；
    本类提供 update dict 合同的轻量静态断言（源码含接线行），防止
    未来重构静默丢弃该键。
    """

    def test_executor_wiring_present(self):
        import inspect

        from src.graph.nodes import _executor_node

        src = inspect.getsource(_executor_node)
        assert 'update["target_code"] = _restored["content"]' in src
        assert "_rollback_last_patch(state, restored_out=_restored)" in src
