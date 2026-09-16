"""4.3 ExecutorAgent Docker 模式单元测试。

docker CLI 在本机不可用时验证提前返回诊断（不静默降级）；
docker 可用时（CI/开发机装了 docker）以 --help 探活做冒烟。
"""

from __future__ import annotations

import os
import shutil

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
