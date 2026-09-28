"""P1 内核沙箱升级（网络出口管控 + venv 环境变量隔离）单元测试。

覆盖：
- DOCKER_NETWORK_ISOLATION=true 时 Docker 命令加 --network=none
- DOCKER_NETWORK_ISOLATION=allowlist 未配白名单 → fail-closed（--network=none）
- DOCKER_NETWORK_ISOLATION=allowlist 配白名单 → --network=bridge + docker_network_obs
- DOCKER_NETWORK_ISOLATION=false（默认）→ 命令不变（历史口径）
- SANDBOX_ENV_ISOLATION=true 时 _prepare_dependencies 置空敏感环境变量
- SANDBOX_ENV_ISOLATION=false（默认）→ env 不变
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch


def _call_execute_docker(agent: MagicMock, monkeypatch_environ: dict[str, str]) -> dict[str, Any]:
    """调用 execute_docker 并捕获 subprocess.run 收到的 cmd，返回结果字典。

    把被测代码文件与测试文件通过 patch.open 写入 tmp sandbox，
    让函数主体走到 subprocess.run（被 mock 成成功），从而 inspect cmd。
    """
    import tempfile

    sandbox_dir = tempfile.mkdtemp(prefix="aitester_sandbox_hardening_")
    # 写被测模块与测试文件
    module_file = os.path.join(sandbox_dir, "mod.py")
    test_file = os.path.join(sandbox_dir, "test_generated.py")
    with open(module_file, "w") as f:
        f.write("def add(a,b): return a+b\n")
    with open(test_file, "w") as f:
        f.write("def test_add(): assert add(1,2)==3\n")

    captured: dict[str, Any] = {"cmd": None}

    def _fake_run(cmd: list[str], *a, **kw):
        captured["cmd"] = list(cmd)
        return MagicMock(returncode=0, stdout="1 passed", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run", side_effect=_fake_run),
        patch("tempfile.mkdtemp", return_value=sandbox_dir),
        patch.dict(os.environ, monkeypatch_environ),
    ):
        # execute_docker 是模块函数（executor.py 里 ExecutorAgent._execute_docker
        # 的类属性绑定）；这里直接调模块函数 execute_docker(self, ...) 形式
        from src.agents.executor_modes import execute_docker

        result = execute_docker(
            agent,
            test_code="def test_add(): assert add(1,2)==3",
            target_file=module_file,
        )
    return {"result": result, "cmd": captured["cmd"]}


def test_docker_network_isolation_true_adds_none() -> None:
    from src.agents.executor import ExecutorAgent

    agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="aitester:latest")
    out = _call_execute_docker(agent, {"DOCKER_NETWORK_ISOLATION": "true"})
    assert "--network=none" in out["cmd"]


def test_docker_network_isolation_allowlist_fail_closed() -> None:
    """allowlist 模式未配白名单 → fail-closed（--network=none）。"""
    from src.agents.executor import ExecutorAgent

    agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="aitester:latest")
    out = _call_execute_docker(
        agent,
        {
            "DOCKER_NETWORK_ISOLATION": "allowlist",
            "DOCKER_NETWORK_ALLOWLIST": "",
        },
    )
    assert "--network=none" in out["cmd"]
    # 观测层：记录 fail-closed 配置
    obs = out["result"].get("docker_network_obs", {})
    assert obs.get("isolation_mode") == "allowlist"


def test_docker_network_isolation_allowlist_with_entries() -> None:
    """allowlist 模式配白名单 → --network=bridge + 观测层记录白名单。"""
    from src.agents.executor import ExecutorAgent

    agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="aitester:latest")
    out = _call_execute_docker(
        agent,
        {
            "DOCKER_NETWORK_ISOLATION": "allowlist",
            "DOCKER_NETWORK_ALLOWLIST": "8.8.8.8:53,1.1.1.1:53",
        },
    )
    assert "--network=bridge" in out["cmd"]
    assert "--network=none" not in out["cmd"]
    obs = out["result"].get("docker_network_obs", {})
    assert obs.get("isolation_mode") == "allowlist"
    assert obs.get("allowlist") == ["8.8.8.8:53", "1.1.1.1:53"]


def test_docker_network_isolation_default_off() -> None:
    """默认（false）→ 命令无网络标志（历史口径逐字节不变）。"""
    from src.agents.executor import ExecutorAgent

    agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="aitester:latest")
    out = _call_execute_docker(agent, {})  # 未设 DOCKER_NETWORK_ISOLATION
    assert "--network=none" not in out["cmd"]
    assert "--network=bridge" not in out["cmd"]
    # 默认 false 时不写 docker_network_obs（历史口径不变）
    assert "docker_network_obs" not in out["result"]


def test_sandbox_env_isolation_blanks_sensitive_vars() -> None:
    """SANDBOX_ENV_ISOLATION=true → _prepare_dependencies 置空敏感变量。"""
    from src.agents.executor_modes import _prepare_dependencies

    agent = MagicMock()
    agent.use_venv = False
    agent.auto_install_deps = False
    agent.dep_install_timeout = 60

    with (
        patch.dict(
            os.environ,
            {
                "SANDBOX_ENV_ISOLATION": "true",
                "HOME": "/Users/tester",
                "SSH_AUTH_SOCK": "/tmp/ssh.sock",
                "AWS_ACCESS_KEY_ID": "AKIA_FAKE",
                "PYTHONPATH": "/sandbox",
            },
        ),
        patch("src.agents.executor_modes.scrub_os_environ") as scrub,
    ):
        scrub.return_value = dict(
            HOME="/Users/tester",
            SSH_AUTH_SOCK="/tmp/ssh.sock",
            AWS_ACCESS_KEY_ID="AKIA_FAKE",
            PYTHONPATH="/sandbox",
        )
        env, _python, _note, _err, _missing = _prepare_dependencies(
            agent,
            target_source="import os\n",
            fixed_test_code="import os\n",
            module_file="/tmp/mod.py",
            sandbox_dir="/tmp/sandbox",
        )
    # 敏感变量被置空，PYTHONPATH 含 sandbox 前缀（_prepare_dependencies 会
    # 在 PYTHONPATH 前插入 sandbox_dir）
    assert env["HOME"] == ""
    assert env["SSH_AUTH_SOCK"] == ""
    assert env["AWS_ACCESS_KEY_ID"] == ""
    assert "/sandbox" in env["PYTHONPATH"]


def test_sandbox_env_isolation_default_off() -> None:
    """SANDBOX_ENV_ISOLATION 未设 → env 不变（历史口径）。"""
    from src.agents.executor_modes import _prepare_dependencies

    agent = MagicMock()
    agent.use_venv = False
    agent.auto_install_deps = False
    agent.dep_install_timeout = 60

    with (
        patch.dict(
            os.environ,
            {
                "HOME": "/Users/tester",
                "PYTHONPATH": "/sandbox",
            },
        ),
        patch("src.agents.executor_modes.scrub_os_environ") as scrub,
    ):
        scrub.return_value = dict(HOME="/Users/tester", PYTHONPATH="/sandbox")
        env, _python, _note, _err, _missing = _prepare_dependencies(
            agent,
            target_source="import os\n",
            fixed_test_code="import os\n",
            module_file="/tmp/mod.py",
            sandbox_dir="/tmp/sandbox",
        )
    # 默认关 → HOME 不变
    assert env["HOME"] == "/Users/tester"
