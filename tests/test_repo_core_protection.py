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


class TestS6ConftestGuardWiring:
    """G 轮：S6 conftest 危险调用扫描接线到 repo 级 pytest 咽喉点。

    接线前 ``scan_conftest_ast_safety`` 只有测试调用、无生产调用点——守卫形同
    不存在，而 repo 级链路正是在宿主上执行第三方仓库自带 conftest.py 的路径
    （pytest 收集期即执行，早于任何断言）。
    """

    @staticmethod
    def _executor():
        from src.agents.executor_repo import RepoExecutor

        return RepoExecutor(timeout=1, setup_timeout=1)

    @staticmethod
    def _write_conftest(root, code, rel="conftest.py"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        return path

    def test_benign_conftest_allows(self, tmp_path, monkeypatch):
        """干净 conftest：无硬拒命中（默认开关开启）。"""
        monkeypatch.delenv("CONTEST_AST_SCAN_ENABLE", raising=False)
        self._write_conftest(tmp_path, "import pytest\n\n@pytest.fixture\ndef db():\n    return []\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path)) == []

    def test_tier1_shell_call_hard_refuse(self, tmp_path):
        """Tier 1（shell 字符串执行）→ 硬拒，返回相对路径 + 特征名。"""
        self._write_conftest(tmp_path, "import os\nos.system('id')\n", rel="tests/conftest.py")
        hits = self._executor()._scan_repo_conftests(str(tmp_path))
        assert hits == [(os.path.join("tests", "conftest.py"), ["os.system"])]

    def test_tier1_getattr_bypass_hard_refuse(self, tmp_path):
        """Tier 1（getattr 取危险属性名）→ 硬拒。"""
        self._write_conftest(tmp_path, "import os\nf = getattr(os, 'system')\nf('id')\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path))[0][1] == ["getattr"]

    def test_benign_getattr_not_flagged(self, tmp_path):
        """良性 getattr（真实 conftest 主流写法）不得命中——旧口径的 18.9% 误报源。"""
        self._write_conftest(tmp_path, "import hypothesis\np = getattr(hypothesis.Phase, 'explain', None)\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path)) == []

    def test_tier2_subprocess_warn_only(self, tmp_path):
        """Tier 2（subprocess 等真实测试基建）→ 仅告警，不阻断。"""
        self._write_conftest(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path)) == []

    def test_unparseable_conftest_fail_closed(self, tmp_path):
        """读不懂 → fail-closed（宿主 AST 解析失败 ≠ venv 里不会执行）。"""
        self._write_conftest(tmp_path, "def f(:\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path))[0][1] == ["<unparseable>"]

    def test_switch_off_skips_scan(self, tmp_path, monkeypatch):
        """CONTEST_AST_SCAN_ENABLE=false → 跳过扫描（历史口径可复现）。"""
        monkeypatch.setenv("CONTEST_AST_SCAN_ENABLE", "false")
        self._write_conftest(tmp_path, "import os\nos.system('id')\n")
        assert self._executor()._scan_repo_conftests(str(tmp_path)) == []

    def test_vcs_and_venv_dirs_skipped(self, tmp_path):
        """.git / .venv 内的 conftest.py 不参与（非被测仓库代码，且量大会拖慢）。"""
        for rel in (".git/conftest.py", ".venv/conftest.py", "node_modules/conftest.py"):
            self._write_conftest(tmp_path, "import os\nos.system('id')\n", rel=rel)
        assert self._executor()._scan_repo_conftests(str(tmp_path)) == []

    def test_run_test_nodes_refuses_without_invoking_pytest(self, tmp_path, monkeypatch):
        """守卫拒绝时子进程零调用，全节点记失败（不会假过）。"""
        from src.agents import executor_repo as mod

        monkeypatch.delenv("CONTEST_AST_SCAN_ENABLE", raising=False)
        self._write_conftest(tmp_path, "import os\nos.system('id')\n")
        calls: list = []
        monkeypatch.setattr(mod, "_run", lambda *a, **k: calls.append(a))
        out = self._executor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::test_b"])
        assert calls == []
        assert out["expected"] == 1
        assert out["passed"] == 0
        assert "S6 conftest" in out["failed_cases"][0]["error"]

    def test_run_test_nodes_proceeds_when_clean(self, tmp_path, monkeypatch):
        """干净仓库：守卫放行，照常进入 pytest 调用（不改变历史行为）。"""
        from src.agents import executor_repo as mod

        monkeypatch.delenv("CONTEST_AST_SCAN_ENABLE", raising=False)
        self._write_conftest(tmp_path, "import pytest\n")
        calls: list = []

        class _Res:
            returncode = 0
            stdout = "1 passed"
            stderr = ""

        monkeypatch.setattr(mod, "_run", lambda *a, **k: (calls.append(a), _Res())[1])
        monkeypatch.setattr(mod.RepoExecutor, "_venv_python", lambda *a, **k: None)
        out = self._executor()._run_test_nodes(str(tmp_path), ["tests/test_a.py::test_b"])
        assert len(calls) == 1
        assert out["passed"] == 1
