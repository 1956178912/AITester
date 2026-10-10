"""
L-1 仓库核心路径保护 + 危险 API 接线（2026-09-29 审查批次）单元测试。

覆盖：
- _is_repo_core_path：basename 黑名单 / 一级目录黑名单 / 临时目录放行 / 开关关闭；
- _repo_core_protection_enabled：默认开 + 显式关闭（含大小写变体）；
- _safe_write_patch 安全检查 4：命中仓库核心路径时拒绝写入。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from unittest.mock import patch

from src.graph import nodes as nodes_mod
from src.graph import patch_io


class TestRepoCoreProtection:
    """L-1 安全加固：_is_repo_core_path 黑名单判定。"""

    def test_root_config_py_blocked(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        assert nodes_mod._is_repo_core_path(os.path.join(root, "config.py")) is True
        assert nodes_mod._is_repo_core_path(os.path.join(root, "main.py")) is True
        assert nodes_mod._is_repo_core_path(os.path.join(root, "init_db.py")) is True

    def test_git_dir_blocked(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        assert nodes_mod._is_repo_core_path(os.path.join(root, ".git")) is True

    def test_src_dir_blocked(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        assert nodes_mod._is_repo_core_path(os.path.join(root, "src", "graph", "nodes.py")) is True
        assert nodes_mod._is_repo_core_path(os.path.join(root, "scripts", "check_x.py")) is True
        assert nodes_mod._is_repo_core_path(os.path.join(root, ".github", "workflows", "ci.yml")) is True

    def test_ordinary_task_dir_allowed(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        # 仓库根内非核心目录 → 放行（黑名单仅拦截 basename/一级目录命中）
        assert nodes_mod._is_repo_core_path(os.path.join(root, "data", "task_1", "target.py")) is False

    def test_temp_dir_allowed(self, monkeypatch):
        """临时目录（数据集沙箱）不受黑名单作用域限制（历史全临时目录可写口径）。"""
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        tmp_task = os.path.join(tempfile.gettempdir(), "aitester_task", "target.py")
        assert nodes_mod._is_repo_core_path(tmp_task) is False

    def test_disabled_switch_passes_all(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        assert nodes_mod._is_repo_core_path(os.path.join(root, "config.py")) is False

    def test_switch_default_on(self, monkeypatch):
        monkeypatch.delenv("PATCH_PROTECT_REPO_CORE", raising=False)
        assert nodes_mod._repo_core_protection_enabled() is True

    def test_switch_case_insensitive_off(self, monkeypatch):
        """2026-09-29 审查 R3 优化：开关判定统一 .lower() 口径（与同文件
        其他开关一致），历史实现 `not in ("0", "false", "False")` 大小写敏感，
        "FALSE" 未被识别为关闭（保护未生效，保守方向错误）。修正后
        "0"/"false"/"FALSE" 等价。"""
        for off_val in ("0", "false", "FALSE", "False"):
            monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", off_val)
            assert nodes_mod._repo_core_protection_enabled() is False
        monkeypatch.delenv("PATCH_PROTECT_REPO_CORE", raising=False)
        assert nodes_mod._repo_core_protection_enabled() is True

    def test_switch_false_blocks_source_write(self, monkeypatch):
        """开关 false（"0"/"false" 任一形态）时 _safe_write_patch 检查 4 放行。"""
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        with patch.dict(os.environ, {"PATCH_PROTECT_REPO_CORE": "0"}):
            state = {"target_file": os.path.join(root, "config.py"), "iteration": 1}
            # 开关关闭时 _is_repo_core_path 恒 False，安全检查 4 不命中；
            # 但安全检查 1-3 仍生效——构造能通过长度/函数定义/白名单的
            # 输入，验证"开关关闭即放行核心路径"的口径。
            with patch.object(patch_io, "_write_file_atomic") as write_fn:
                write_fn.return_value = None
                result = nodes_mod._safe_write_patch(
                    original_code="def f():\n    return 1\n" * 20,
                    new_code="def f():\n    return 2\n" * 20,
                    applied=True,
                    state=state,
                )
            assert result is True
            write_fn.assert_called_once()


class TestSafeWritePatchRepoCoreGuard:
    """_safe_write_patch 安全检查 4：命中仓库核心路径时拒绝写入。"""

    def test_write_blocked_when_repo_core(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        state = {
            "target_file": os.path.join(root, "config.py"),
            "iteration": 1,
        }
        # 检查 1-2 通过（长度 ≥10%、含函数定义），检查 3 通过（在白名单内），
        # 检查 4 命中 → 拒绝（返回 False，不写盘）
        result = nodes_mod._safe_write_patch(
            original_code="def f():\n    return 1\n" * 20,
            new_code="def f():\n    return 2\n" * 20,
            applied=True,
            state=state,
        )
        assert result is False

    def test_write_allowed_for_ordinary_task(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        # 临时目录内的任务路径：白名单 + 黑名单（不在仓库根内）双通过
        with tempfile.TemporaryDirectory() as task_dir:
            target = os.path.join(task_dir, "target.py")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("def f():\n    return 1\n" * 20)
            state = {
                "target_file": target,
                "iteration": 1,
            }
            result = nodes_mod._safe_write_patch(
                original_code="def f():\n    return 1\n" * 20,
                new_code="def f():\n    return 2\n" * 20,
                applied=True,
                state=state,
            )
            # 临时目录在白名单内（tempfile.gettempdir()）+ 不在仓库根内 → 放行写盘
            assert result is True
            with open(target, encoding="utf-8") as fh:
                assert "return 2" in fh.read()

    def test_write_blocked_for_src_path(self, monkeypatch):
        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "1")
        root = os.path.abspath(nodes_mod._ALLOWED_WRITE_ROOTS[0])
        src_path = os.path.join(root, "src", "graph", "nodes.py")
        state = {"target_file": src_path, "iteration": 1}
        result = nodes_mod._safe_write_patch(
            original_code="def f():\n    return 1\n" * 20,
            new_code="def f():\n    return 2\n" * 20,
            applied=True,
            state=state,
        )
        assert result is False


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
