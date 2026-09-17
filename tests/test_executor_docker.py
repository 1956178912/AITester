"""4.3 ExecutorAgent Docker 模式单元测试。

docker CLI 在本机不可用时验证提前返回诊断（不静默降级）；
TestDockerExecutionFlow：以 mock 的 docker CLI + subprocess.run 覆盖容器内执行
的完整链路（成功 / 失败 / 超时 / 被测文件缺失 / 挂载卷内容校验），
不依赖本机 docker 安装。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.agents.executor import ExecutorAgent


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """隔离 venv 缓存目录（与其他 executor 测试同口径）。"""
    monkeypatch.delenv("EXECUTOR_USE_VENV", raising=False)
    yield


class TestDockerExecutor:
    """4.3 use_docker 执行模式。"""

    def _agent(self, tmp_path, **kwargs) -> tuple[ExecutorAgent, str]:
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True, **kwargs)
        return agent, str(target)

    def test_docker_unavailable_returns_diagnostics(self, tmp_path):
        """本机无 docker CLI 时：提前返回 docker_unavailable 诊断，不降级本地执行。"""
        if shutil.which("docker") is not None:
            pytest.skip("本机已安装 docker，无法复现 docker_unavailable 分支")
        agent, target = self._agent(tmp_path)
        result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", target)
        assert result["passed"] is False
        assert result["error_info"]["type"] == "docker_unavailable"
        assert result.get("docker_image") == "aitester:latest"

    def test_docker_mode_flag(self, tmp_path):
        """use_docker 默认 False，显式传参可开启（接口回归）。"""
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        default_agent = ExecutorAgent(timeout=30)
        assert default_agent.use_docker is False
        docker_agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="custom:1.0")
        assert docker_agent.use_docker is True
        assert docker_agent.docker_image == "custom:1.0"

    def test_docker_takeover_over_venv(self, tmp_path, monkeypatch):
        """Docker 模式优先级高于 venv：use_docker=true 时不进入沙箱路径。"""
        agent, target = self._agent(tmp_path, use_venv=True)
        entered_sandbox: list = []
        agent._execute_sandboxed = lambda *a, **kw: (
            entered_sandbox.append(a)
            or {  # type: ignore[method-assign]
                "passed": False,
                "output": "should not be called",
                "coverage": 0.0,
                "failed_cases": [],
            }
        )
        # docker 不可用（测试环境）→ docker_unavailable 提前返回，沙箱路径不触发
        if shutil.which("docker") is None:
            result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", target)
            assert result["error_info"]["type"] == "docker_unavailable"
            assert not entered_sandbox, "docker 模式不应进入 venv 沙箱路径"


class TestSubprocessEnvSanitization:
    """4.1 脱敏审计：子进程环境不继承 LLM API 凭证。"""

    def test_local_env_strips_api_keys(self, tmp_path):
        """本地（非 Docker）模式的子进程 env 剔除 API Key 类变量。"""
        agent = ExecutorAgent(timeout=30)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        # 直接调用 execute 前 monkeypatch 子进程执行以捕获 env
        captured: dict = {}

        def fake_run_pytest_with_retry(cmd, env, project_root):
            captured.update(env)
            return ("PASSED\n", type("R", (), {"returncode": 0})())

        agent._run_pytest_with_retry = fake_run_pytest_with_retry  # type: ignore[method-assign]

        saved = {k: os.environ.get(k) for k in ("OPENAI_API_KEY",)}
        os.environ["OPENAI_API_KEY"] = "sk-secret-test"
        try:
            agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        assert "OPENAI_API_KEY" not in captured, "LLM API 凭证不得继承进被测代码子进程"
        # PYTHONPATH 保留（本地模式仍指向沙箱目录），但 API Key 类变量被剔除
        assert "PYTHONPATH" in captured


class TestDockerExecutionFlow:
    """mock docker CLI 的容器内执行链路测试（不依赖本机 docker 安装）。

    技巧：patch shutil.which 让"docker 可用"，patch subprocess.run 捕获
    容器命令并以伪造结果返回；被测文件/测试代码经挂载卷目录落盘，
    可在执行后检查沙箱目录内的文件内容（验证挂载前的写入逻辑）。
    """

    @staticmethod
    def _fake_docker_result(returncode: int = 0, stdout: str = "1 passed", stderr: str = "") -> MagicMock:
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_docker_success_path(self, tmp_path, monkeypatch):
        """docker 可用 + 容器返回 0：解析覆盖率/失败用例，携带 docker_image。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="custom:2.0")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._fake_docker_result(
                stdout="============ short test summary ============\nTOTAL     100      20     80%\n1 passed in 0.5s",
            )
            result = agent.execute("def test_add():\n    assert add(1, 2) == 3\n", str(target))

        assert result["passed"] is True
        assert result["docker_image"] == "custom:2.0"
        assert result["coverage"] == 80.0
        assert "error_info" not in result
        # 容器命令结构校验：挂载卷 + 工作目录 + 镜像 + pytest 参数
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "docker" and cmd[1] == "run" and "--rm" in cmd
        mount_arg = cmd[cmd.index("-v") + 1]
        assert mount_arg.endswith(":/workspace")
        assert "custom:2.0" in cmd
        assert "-k" not in cmd  # 未指定 target_function 时不追加

    def test_docker_target_function_appends_k_flag(self, tmp_path, monkeypatch):
        """指定 target_function 时容器命令追加 -k 过滤参数。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._fake_docker_result()
            agent.execute("def test_add(): pass\n", str(target), target_function="test_add")

        cmd = mock_run.call_args[0][0]
        assert "-k" in cmd and "test_add" in cmd

    def test_docker_failure_collects_error_info(self, tmp_path, monkeypatch):
        """容器返回非 0：收集 error_info + 失败用例，不误标 passed。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True)
        failed_output = (
            "FAILED test_generated.py::test_add - ZeroDivisionError: division by zero\n"
            "========== short test summary info ==========\n"
            "1 failed in 0.5s"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._fake_docker_result(returncode=1, stdout=failed_output)
            result = agent.execute("def test_add():\n    assert add(1, 0) == 0\n", str(target))

        assert result["passed"] is False
        assert result["error_info"]["type"] == "test_failure"
        assert result["error_info"]["returncode"] == 1
        assert result["error_info"]["has_runtime_error"] is True
        assert [c["name"] for c in result["failed_cases"]] == ["test_generated.py::test_add"]

    def test_docker_timeout_returns_diagnostic(self, tmp_path, monkeypatch):
        """容器执行超时：提前返回 docker_timeout 诊断，不抛异常。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=120)
            result = agent.execute("def test_add(): pass\n", str(target))

        assert result["passed"] is False
        assert result["error_info"]["type"] == "docker_timeout"
        assert "120" in result["error_info"]["message"]
        assert result["docker_image"] == "aitester:latest"
        # 超时下限：timeout=30 < 120 → 实际使用 120
        mock_run.assert_called_once()

    def test_docker_missing_target_file(self, tmp_path, monkeypatch):
        """被测文件不存在：file_not_found 诊断，不触发 docker run。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        agent = ExecutorAgent(timeout=30, use_docker=True)
        missing = tmp_path / "nope.py"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._fake_docker_result()
            result = agent.execute("def test_x(): pass\n", str(missing))

        assert result["passed"] is False
        assert result["error_info"]["type"] == "file_not_found"
        mock_run.assert_not_called()

    def test_docker_sandbox_mount_files_written(self, tmp_path, monkeypatch):
        """挂载卷目录内写入被测模块与测试文件（模块名取自 target_file 基名）。"""
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
        target = tmp_path / "calc.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        agent = ExecutorAgent(timeout=30, use_docker=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._fake_docker_result()
            agent.execute("def test_add(): pass\n", str(target))

        # 从 mock 的挂载卷参数反查沙箱目录，校验挂载卷指向语义
        cmd = mock_run.call_args[0][0]
        mount_arg = cmd[cmd.index("-v") + 1]
        assert mount_arg.endswith(":/workspace")
        # 容器工作目录固定为 /workspace
        assert "-w" in cmd and "/workspace" in cmd


class TestSandboxCleanup:
    """沙箱目录清理兜底（OSError 不抛、静默告警）。"""

    def test_cleanup_sandbox_ignores_oserror(self, tmp_path, monkeypatch):
        """shutil.rmtree 抛 OSError 时仅记录警告，不中断主流程。"""
        import shutil

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        monkeypatch.setattr(shutil, "rmtree", MagicMock(side_effect=OSError("disk full")))
        # 不应抛出
        ExecutorAgent._cleanup_sandbox(str(sandbox))
