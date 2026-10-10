"""临时目录泄漏修复测试（2026-10-09 审查报告 §11.1b 结果十八）。

两处泄漏（实测：多轮跑批后 TMPDIR 下累积上千个 `aitester_*` 目录）：

1. `_safe_write_patch` 的快照目录按 `pid_thread` 命名、**跨任务复用**，
   而只有"回滚"路径 `os.remove` 快照**文件**、从不删目录
   （`src/graph/patch_io.py`）→ 本轮为回滚路径补空目录剪枝，并在
   `run_main_batch.main()` 的 `finally` 加**批次级**清扫。
2. 病态任务被强杀时 `aitester_sandbox_*` 可能残留（正常路径已有
   `finally → cleanup_sandbox`，故只登记不新增改动）。

保守口径（本测试锁定）：只删**本进程 pid** 的、**已空**的、**约定前缀**的
目录；非空不删、他人不删、异前缀不删。
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from experiments.run_main_batch import _sweep_own_patch_snap_dirs  # noqa: E402
from src.graph.patch_io import _prune_empty_snapshot_dir  # noqa: E402


class TestPruneEmptySnapshotDir:
    """`patch_io._prune_empty_snapshot_dir`：回滚后剪枝空快照目录。"""

    def test_removes_empty_conventional_dir(self) -> None:
        d = tempfile.mkdtemp(prefix="aitester_patch_snap_1_1")
        _prune_empty_snapshot_dir(d)
        assert not os.path.exists(d)

    def test_keeps_non_empty_dir(self) -> None:
        """非空目录必须保留——残留快照文件可能仍被 state 引用。"""
        d = tempfile.mkdtemp(prefix="aitester_patch_snap_1_2")
        f = os.path.join(d, "iter0_mod.py")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("x")
        _prune_empty_snapshot_dir(d)
        assert os.path.exists(f)
        import shutil

        shutil.rmtree(d, ignore_errors=True)

    def test_keeps_foreign_prefix(self) -> None:
        """异前缀目录绝不触碰（防误删调用方目录）。"""
        d = tempfile.mkdtemp(prefix="not_a_snapshot_")
        _prune_empty_snapshot_dir(d)
        assert os.path.exists(d)
        os.rmdir(d)

    def test_missing_dir_is_noop(self) -> None:
        """不存在的路径 → 静默 no-op（清理路径不得抛异常）。

        2026-10-09：补显式断言。此前仅"调用不抛"隐含通过，属零断言用例
        （`scripts/gates/check_zero_assert_tests.py` 违规）。改为捕获异常并断言为
        None——语义仍是"必须不抛"，但变成可检出的断言信号。
        """
        exc: BaseException | None = None
        try:
            _prune_empty_snapshot_dir(os.path.join(tempfile.gettempdir(), "aitester_patch_snap_0_0_absent"))
        except BaseException as e:
            exc = e
        assert exc is None, f"清理路径不应抛异常，实际抛出 {exc!r}"


class TestSweepOwnPatchSnapDirs:
    """`run_main_batch._sweep_own_patch_snap_dirs`：批次级清扫。"""

    def test_sweeps_empty_dir_of_own_pid(self) -> None:
        d = os.path.join(tempfile.gettempdir(), f"aitester_patch_snap_{os.getpid()}_t1")
        os.makedirs(d, exist_ok=True)
        _sweep_own_patch_snap_dirs()
        assert not os.path.exists(d)

    def test_keeps_non_empty_dir(self) -> None:
        d = os.path.join(tempfile.gettempdir(), f"aitester_patch_snap_{os.getpid()}_t2")
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, "iter0_mod.py")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("x")
        _sweep_own_patch_snap_dirs()
        assert os.path.exists(f), "非空快照目录不得被删（内容可能仍被引用）"
        import shutil

        shutil.rmtree(d, ignore_errors=True)

    def test_keeps_other_pid_dir(self) -> None:
        """**关键安全性**：只清扫本进程 pid，绝不触碰其他进程目录。"""
        other_pid = os.getpid() + 424242
        d = os.path.join(tempfile.gettempdir(), f"aitester_patch_snap_{other_pid}_x")
        os.makedirs(d, exist_ok=True)
        _sweep_own_patch_snap_dirs()
        assert os.path.exists(d), "他进程快照目录被误删"
        os.rmdir(d)

    @pytest.mark.parametrize("prefix", ["aitester_sandbox_", "aitester_branch_cov_", "other_"])
    def test_ignores_other_prefixes(self, prefix: str) -> None:
        d = tempfile.mkdtemp(prefix=prefix)
        _sweep_own_patch_snap_dirs()
        assert os.path.exists(d)
        os.rmdir(d)
