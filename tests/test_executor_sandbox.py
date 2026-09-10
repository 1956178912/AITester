"""
ExecutorAgent 沙箱执行路径单元测试（P1：依赖隔离）。

覆盖：
- use_venv 时走 _execute_sandboxed（mock 子进程）
- 沙箱目录结构（被测模块 + 测试文件写入临时目录）
- 缺失依赖检测写入 error_info.missing_dependencies
- auto_install_deps 安装失败时 error_info 类型为 dependency_install_failed
- use_venv=False 时保持原本地执行路径（不创建沙箱）
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.executor import ExecutorAgent


def _make_target_file(tmp_path, source="def add(a, b):\n    return a + b\n"):
    target = tmp_path / "mycalc.py"
    target.write_text(source)
    return str(target)


class TestSandboxRouting:
    """use_venv 开关的路由行为。"""

    @patch("src.agents.executor.subprocess.run")
    def test_use_venv_routes_to_sandbox(self, mock_run, tmp_path):
        target = _make_target_file(tmp_path)
        mock_run.return_value = type("P", (), {"returncode": 0, "stdout": "2 passed\nTOTAL 100%", "stderr": ""})
        agent = ExecutorAgent(timeout=30, use_venv=True, auto_install_deps=False)
        result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", target, target_function=None)
        assert result["passed"] is True
        # 沙箱路径：pytest 命令的工作目录应是临时沙箱（而非项目根）
        kwargs = mock_run.call_args.kwargs
        cwd = kwargs.get("cwd")
        assert cwd is not None and "aitester_sandbox_" in cwd

    @patch("src.agents.executor.subprocess.run")
    def test_default_mode_keeps_local_path(self, mock_run, tmp_path):
        target = _make_target_file(tmp_path)
        mock_run.return_value = type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})
        agent = ExecutorAgent(timeout=30)  # use_venv=False 默认
        result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", target)
        assert result["passed"] is True
        kwargs = mock_run.call_args.kwargs
        assert "aitester_sandbox_" not in str(kwargs.get("cwd", ""))


class TestSandboxDependencyDetection:
    """沙箱内的依赖检测与安装。"""

    @patch("src.agents.executor.subprocess.run")
    def test_missing_dependency_recorded(self, mock_run, tmp_path):
        """缺失第三方依赖写入 error_info.missing_dependencies。"""
        target = _make_target_file(tmp_path, source="import definitely_not_real_zzz\n\ndef f():\n    return 1\n")
        mock_run.return_value = type(
            "P",
            (),
            {"returncode": 1, "stdout": "ModuleNotFoundError: No module named 'definitely_not_real_zzz'", "stderr": ""},
        )
        agent = ExecutorAgent(timeout=30, use_venv=False, auto_install_deps=False)
        result = agent._execute_sandboxed("def test_f():\n    assert f() == 1\n", target)
        assert result["passed"] is False
        assert "definitely_not_real_zzz" in result["error_info"].get("missing_dependencies", [])

    @patch("src.agents.executor.ExecutorAgent._execute_sandboxed")
    def test_execute_delegates_sandbox(self, mock_sandbox):
        """execute(use_venv=True) 完整委托给沙箱路径。"""
        mock_sandbox.return_value = {"passed": True, "output": "", "coverage": 0.0, "failed_cases": []}
        agent = ExecutorAgent(timeout=30, use_venv=True)
        result = agent.execute("def test_x(): pass", "/nonexistent/target.py")
        assert result["passed"] is True
        mock_sandbox.assert_called_once()


class TestSandboxAutoInstall:
    """auto_install_deps 的安装失败处理。"""

    @patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry")
    @patch("src.tools.dependency.install_packages")
    @patch("src.tools.dependency.create_venv")
    @patch("src.tools.dependency.find_missing_modules")
    @patch("src.tools.dependency.extract_imported_modules")
    def test_install_failure_short_circuits(
        self, mock_extract, mock_find_missing, mock_create, mock_install, mock_run_retry, tmp_path
    ):
        """依赖安装失败时提前返回 dependency_install_failed（结果不可信，不执行 pytest）。"""
        target = _make_target_file(tmp_path)
        mock_extract.return_value = {"pandas"}
        mock_find_missing.return_value = {"pandas"}
        mock_create.return_value = "/fake/venv/bin/python"
        mock_install.return_value = (False, "Could not find pandas")

        agent = ExecutorAgent(timeout=30, use_venv=True, auto_install_deps=True)
        result = agent._execute_sandboxed("def test_x(): pass", target)
        assert result["passed"] is False
        assert result["error_info"]["type"] == "dependency_install_failed"
        # 安装失败不执行 pytest（避免误导性的测试输出）
        mock_run_retry.assert_not_called()

    @patch("src.agents.executor.ExecutorAgent._run_pytest_with_retry")
    @patch("src.tools.dependency.install_packages")
    @patch("src.tools.dependency.create_venv")
    @patch("src.tools.dependency.find_missing_modules")
    @patch("src.tools.dependency.extract_imported_modules")
    def test_install_success_runs_pytest(
        self, mock_extract, mock_find_missing, mock_create, mock_install, mock_run_retry, tmp_path
    ):
        """依赖安装成功后正常执行 pytest。"""
        target = _make_target_file(tmp_path)
        mock_extract.return_value = {"pandas"}
        mock_find_missing.return_value = {"pandas"}
        mock_create.return_value = "/fake/venv/bin/python"
        mock_install.return_value = (True, "installed")
        mock_run_retry.return_value = (
            "2 passed",
            type("P", (), {"returncode": 0, "stdout": "TOTAL 90%", "stderr": ""}),
        )

        agent = ExecutorAgent(timeout=30, use_venv=True, auto_install_deps=True)
        result = agent._execute_sandboxed("def test_x(): pass", target)
        assert result["passed"] is True
        assert "missing_dependencies" not in (result.get("error_info") or {})
        mock_run_retry.assert_called_once()


class TestSandboxFileReadFailure:
    """被测文件不可读时优雅失败。"""

    def test_target_file_missing(self, tmp_path):
        agent = ExecutorAgent(timeout=30, use_venv=True)
        result = agent._execute_sandboxed("def test_x(): pass", str(tmp_path / "nope.py"))
        assert result["passed"] is False
        assert result["error_info"]["type"] == "file_not_found"
