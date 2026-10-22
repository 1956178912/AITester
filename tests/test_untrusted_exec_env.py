"""A08／P0（2026-10-18 第三方评审）：不可信代码执行环境统一最小化 —— 回归锁。

缺陷（评审 G/A08、J/A08、M4）
------------------------------
- ``src/utils/process_utils.py::nested_pytest_env`` 历史实现只剔除
  ``PYTEST_PLUGINS`` / ``PYTEST_ADDOPTS``，其余宿主环境**整体继承**；宿主若
  配置了 ``LLM_*_API_KEY`` / ``OPENAI_API_KEY`` / ``AWS_*`` /
  ``MYSQL_PASSWORD`` / ``SSH_AUTH_SOCK`` 等，评分等旁路执行 LLM 生成测试 /
  补丁 / 探针的子进程可直接读取（威胁模型承诺的"不可信代码只得最小环境"
  在这些入口失效）。
- 主基准必经的评分旁路全部命中：M1 判分
  （``experiments/_m1_metrics.py::_run_pytest_in_tmp``）、MDO
  （``src/measurement/mdo.py::_run_probe`` 显式 ``**os.environ`` 与
  ``_run_tests_on_code``）、P2P 回归
  （``src/tools/patch_rollback.py::run_p2p_regression`` 未传 env → 继承宿主）。

修复
----
新增 ``process_utils.untrusted_exec_env()``（最小白名单
``credential_scrub.build_minimal_env`` + 嵌套 pytest 运行期必需键 + 显式
overrides）；``nested_pytest_env`` 保留为兼容别名。上述三个文件的所有执行
入口改走该构造器（其余冻结实验站点经别名自动收敛）。

A08 收尾追加（Lead 批准扩写域）：``experiments/solver_directed_trigger.py::
_probe`` 与 ``experiments/spec_ambiguity.py::_behavior`` 两处执行候选/生成
代码行为探针的 ``{**os.environ, ...}`` 同根因入口也改走该构造器。

本文件锁三层（零 LLM / 零网络 / 零真实密钥）：
1. **M4 伪凭证脚本**：``nested_pytest_env`` 输出不得含 ``AUDIT_SENTINEL``
   （评审 M4 验收命令逐字复刻）；
2. **构造器契约**：凭证 / 宿主 pytest 配置 / 任意非白名单键零继承，嵌套
   pytest 必需项保留，显式 overrides 优先；
3. **各调用点最终子进程 env 截获**：M1 / MDO（探针 + 测试执行）/ P2P /
   SDTS / SAI 的 ``run_with_timeout(env=...)`` 实参不含伪凭证，且仍带
   ``PYTHONPATH=tmpdir`` 等执行必需项。
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.utils.process_utils import (
    CompletedProcess,
    nested_pytest_env,
    run_with_timeout,
    untrusted_exec_env,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: 评审 A08 点名的凭证家族 + 常见宿主凭证（伪值，非真实密钥）。
_CREDENTIAL_SENTINELS: dict[str, str] = {
    "LLM_1_API_KEY": "AUDIT_SENTINEL",
    "LLM_27_API_KEY": "AUDIT_SENTINEL",
    "OPENAI_API_KEY": "AUDIT_SENTINEL",
    "OPENAI_API_KEY_2": "AUDIT_SENTINEL",
    "ANTHROPIC_API_KEY": "AUDIT_SENTINEL",
    "DEEPSEEK_API_KEY": "AUDIT_SENTINEL",
    "ZAI_API_KEY": "AUDIT_SENTINEL",
    "AWS_ACCESS_KEY_ID": "AUDIT_SENTINEL",
    "AWS_SECRET_ACCESS_KEY": "AUDIT_SENTINEL",
    "AWS_SESSION_TOKEN": "AUDIT_SENTINEL",
    "MYSQL_PASSWORD": "AUDIT_SENTINEL",
    "DATABASE_PASSWORD": "AUDIT_SENTINEL",
    "SSH_AUTH_SOCK": "/tmp/audit_agent.sock",
    "GITHUB_TOKEN": "AUDIT_SENTINEL",
    "HF_TOKEN": "AUDIT_SENTINEL",
}

#: 不可信子进程**必须保留**的嵌套 pytest 运行期键（按宿主实际存在断言）。
_REQUIRED_PRESERVED_KEYS = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "PYTHONPATH",
    "PYTHONIOENCODING",
    "PYTHONUNBUFFERED",
)


def _poison_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入伪凭证 + 宿主 pytest 配置 + 一个非白名单宿主键。"""
    for key, value in _CREDENTIAL_SENTINELS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PYTEST_PLUGINS", "audit_host_plugin")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--audit-host-option")
    monkeypatch.setenv("AUDIT_HOST_ONLY_VARIABLE", "audit-host-value")


def _assert_no_credentials(env: dict[str, str], source: str) -> None:
    leaked = sorted(key for key in _CREDENTIAL_SENTINELS if key in env)
    assert not leaked, f"{source} 的不可信子进程 env 仍含宿主凭证：{leaked}"
    assert "PYTEST_PLUGINS" not in env, f"{source} 的嵌套 env 仍含宿主 PYTEST_PLUGINS"
    assert "PYTEST_ADDOPTS" not in env, f"{source} 的嵌套 env 仍含宿主 PYTEST_ADDOPTS"
    assert "AUDIT_HOST_ONLY_VARIABLE" not in env, f"{source} 仍继承非白名单宿主键（最小环境失效）"


# ───────────────────────── 1) M4 伪凭证脚本（评审验收口径） ─────────────────────────


@pytest.mark.unit
class TestM4AuditSentinel:
    def test_m4_audit_sentinel_not_inherited(self) -> None:
        """评审 M4 脚本逐字复刻：sentinel inherited 必须为 False。"""
        with patch.dict(os.environ, {"LLM_1_API_KEY": "AUDIT_SENTINEL"}):
            env = nested_pytest_env(PYTHONDONTWRITEBYTECODE="1")
            sentinel_inherited = env.get("LLM_1_API_KEY") == "AUDIT_SENTINEL"
            assert sentinel_inherited is False
            assert "LLM_1_API_KEY" not in env

    @pytest.mark.parametrize("key", sorted(_CREDENTIAL_SENTINELS))
    def test_each_credential_family_is_stripped(self, key: str) -> None:
        """凭证家族逐个验证：任何凭证键都不进入不可信执行环境。"""
        with patch.dict(os.environ, {key: _CREDENTIAL_SENTINELS[key]}):
            assert key not in nested_pytest_env()
            assert key not in untrusted_exec_env()

    def test_default_env_is_stripped_even_without_overrides(self) -> None:
        """M4 之外补充：无 overrides 时同样不得继承凭证。"""
        with patch.dict(os.environ, {"LLM_1_API_KEY": "AUDIT_SENTINEL"}, clear=False):
            assert "LLM_1_API_KEY" not in nested_pytest_env()


# ───────────────────────── 2) 构造器契约（白名单 + 必需项 + overrides） ─────────────────────────


@pytest.mark.unit
class TestUntrustedExecEnvContract:
    def test_pytest_runtime_environment_is_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """嵌套 pytest 必需项按需保留（PATH/HOME/TMP*/PYTHONPATH/编码等）。"""
        expected: dict[str, str] = {}
        for key in _REQUIRED_PRESERVED_KEYS:
            expected[key] = f"/audit/{key.lower()}"
            monkeypatch.setenv(key, expected[key])
        for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "COLUMNS"):
            expected[key] = f"audit-{key.lower()}"
            monkeypatch.setenv(key, expected[key])
        env = untrusted_exec_env()
        for key, value in expected.items():
            assert env.get(key) == value, f"嵌套 pytest 必需键 {key} 未被保留"

    def test_explicit_overrides_win(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """显式 overrides 是可信调用点声明，优先于白名单/宿主值。"""
        monkeypatch.setenv("PYTHONPATH", "/host/pythonpath")
        env = untrusted_exec_env(
            PYTHONPATH="/tmp/audit_tmpdir",
            PYTHONDONTWRITEBYTECODE="1",
        )
        assert env["PYTHONPATH"] == "/tmp/audit_tmpdir"
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"

    def test_clean_host_env_is_not_wholesale_inherited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """白名单外任意宿主键（不论是否凭证）默认拒绝——新增凭证无需改名单。"""
        monkeypatch.setenv("AUDIT_FUTURE_TOOL_CREDENTIAL", "leak")
        monkeypatch.setenv("AUDIT_ARBITRARY_HOST_KEY", "leak")
        env = untrusted_exec_env()
        assert "AUDIT_FUTURE_TOOL_CREDENTIAL" not in env
        assert "AUDIT_ARBITRARY_HOST_KEY" not in env

    def test_real_subprocess_does_not_see_host_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端：真实子进程（不可信执行形态）读不到宿主凭证。"""
        monkeypatch.setenv("LLM_1_API_KEY", "AUDIT_SENTINEL")
        script = "import os; print(os.environ.get('LLM_1_API_KEY', 'MISSING'))"
        res = run_with_timeout(
            [sys.executable, "-c", script],
            timeout=30,
            text=True,
            env=nested_pytest_env(),
        )
        assert res.timed_out is False
        assert res.returncode == 0
        assert (res.stdout or "").strip() == "MISSING", f"子进程仍看到宿主凭证：{res.stdout!r}"


# ─────────────── 3) 各调用点最终子进程 env 截获（M1/MDO/P2P/SDTS/SAI） ───────────────


def _capture_run_with_timeout(monkeypatch: pytest.MonkeyPatch, *, stdout: str = "") -> list[dict[str, Any]]:
    """把 process_utils.run_with_timeout 替换成 env 截获器（返回可控 stdout）。"""
    calls: list[dict[str, Any]] = []

    def _fake_run(cmd: list[str], **kwargs: Any) -> CompletedProcess:
        calls.append({"cmd": list(cmd), **kwargs})
        return CompletedProcess(list(cmd), 0, stdout=stdout, stderr="", timed_out=False)

    monkeypatch.setattr("src.utils.process_utils.run_with_timeout", _fake_run)
    return calls


def _pytest_spawn_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留 ``... -m pytest ...`` 形态的调用（排除解释器探活等辅助子进程）。"""
    return [call for call in calls if "-m" in call["cmd"] and "pytest" in call["cmd"]]


def _assert_untrusted_child_env(call: dict[str, Any], source: str) -> dict[str, str]:
    env = call.get("env")
    assert isinstance(env, dict), f"{source} 的子进程未显式传 env（会继承宿主凭证）"
    _assert_no_credentials(env, source)
    # 判分必需项：PYTHONPATH 必须覆盖为 tmpdir（cwd），且不落 .pyc
    assert env.get("PYTHONPATH") == call.get("cwd"), f"{source} 的 PYTHONPATH 未覆盖为 tmpdir（H2 回退）"
    assert env.get("PYTHONDONTWRITEBYTECODE") == "1", f"{source} 缺少 PYTHONDONTWRITEBYTECODE=1"
    # PATH 等基础运行环境保留（不可信子进程派生进程仍可用）
    if "PATH" in os.environ:
        assert env.get("PATH") == os.environ["PATH"], f"{source} 未保留 PATH"
    return env


@pytest.mark.unit
class TestExecutionSitesInterceptFinalEnv:
    def test_m1_isolation_pytest_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """M1 判分（主基准必经路径）：嵌套 pytest 子进程 env 无宿主凭证。"""
        from experiments import _m1_metrics

        _poison_host_env(monkeypatch)
        calls = _capture_run_with_timeout(monkeypatch)
        result = _m1_metrics._run_pytest_in_tmp(
            "def test_ok():\n    assert True\n",
            "def f():\n    return 1\n",
            "audit_mod",
        )
        assert result is not None and result[0] == 0
        spawns = _pytest_spawn_calls(calls)
        assert len(spawns) == 1, f"M1 站点应恰好启动一次嵌套 pytest，实际 {len(spawns)}"
        env = _assert_untrusted_child_env(spawns[0], "M1 _run_pytest_in_tmp")
        # M1 的 py 探活子进程同样不应继承凭证（env=None 的静态探活不在本断言面内）
        assert "audit_host_plugin" not in env.values()

    def test_mdo_probe_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MDO 行为探针（显式 **os.environ 历史缺陷点）：子进程 env 无宿主凭证。"""
        from src.measurement import mdo

        _poison_host_env(monkeypatch)
        calls = _capture_run_with_timeout(monkeypatch)
        stdout = mdo._run_probe("def f(x):\n    return x + 1\n", "audit_mod", timeout_seconds=30)
        # F13（2026-10-19 第三方审查 P1）：_run_probe 现在对"非 JSON / 空输出 /
        # probe_error 诊断"按契约返回 None（拒绝把探针诊断当行为摘要）；本用例
        # 的 fake run_with_timeout 返回空 stdout，故这里断言 None（此前为 ""）。
        assert stdout is None
        probe_calls = [call for call in calls if any(str(part).endswith("_mdo_probe.py") for part in call["cmd"])]
        assert len(probe_calls) == 1, f"MDO 探针站点应恰好启动一次探针子进程，实际 {len(probe_calls)}"
        call = probe_calls[0]
        env = call.get("env")
        assert isinstance(env, dict), "MDO _run_probe 未显式传 env（**os.environ 回退）"
        _assert_no_credentials(env, "MDO _run_probe")
        assert env.get("PYTHONPATH") == call.get("cwd")
        assert env.get("PYTHONDONTWRITEBYTECODE") == "1"

    def test_mdo_tests_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MDO 测试执行（LLM 生成测试套件）：子进程 env 无宿主凭证。"""
        from src.measurement import mdo

        _poison_host_env(monkeypatch)
        calls = _capture_run_with_timeout(monkeypatch)
        result = mdo._run_tests_on_code(
            "from audit_mod import f\n\ndef test_f():\n    assert f(1) == 2\n",
            "def f(x):\n    return x + 1\n",
            "audit_mod",
            timeout_seconds=30,
        )
        assert result is not None and result[0] == 0
        spawns = _pytest_spawn_calls(calls)
        assert len(spawns) == 1
        _assert_untrusted_child_env(spawns[0], "MDO _run_tests_on_code")

    def test_p2p_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """P2P 回归（历史未传 env → 继承宿主）：子进程 env 无宿主凭证。"""
        from src.tools import patch_rollback

        _poison_host_env(monkeypatch)
        # BE（2026-10-21）：rc==0 的 P2P 裁决要求摘要含真实 passed；本用例
        # 关注 env 截获，夹具给出真实 pytest 摘要（旧夹具空 stdout 在新口径
        # 下属"无有效通过"）。
        calls = _capture_run_with_timeout(monkeypatch, stdout="1 passed in 0.01s")
        result = patch_rollback.run_p2p_regression(
            "def add(a, b):\n    return a + b\n",
            "from module_under_test import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            "module_under_test",
        )
        assert result["verdict"] == "verified", result
        spawns = _pytest_spawn_calls(calls)
        assert len(spawns) == 1
        env = _assert_untrusted_child_env(spawns[0], "P2P run_p2p_regression")
        assert env.get("PYTHONPATH") == spawns[0].get("cwd")

    def test_solver_directed_trigger_probe_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDTS 候选代码行为探针（历史 **os.environ 直传）：子进程 env 无宿主凭证。"""
        from experiments import solver_directed_trigger

        _poison_host_env(monkeypatch)
        calls = _capture_run_with_timeout(monkeypatch, stdout='{"kind": "ok", "value": "1"}')
        result = solver_directed_trigger._probe(
            "def f(x):\n    return x + 1\n",
            "audit_mod",
            "f",
            [1],
            timeout=10,
        )
        assert result == "ok:1"
        probe_calls = [call for call in calls if any(str(part).endswith("_probe.py") for part in call["cmd"])]
        assert len(probe_calls) == 1, f"SDTS 探针站点应恰好启动一次探针子进程，实际 {len(probe_calls)}"
        _assert_untrusted_child_env(probe_calls[0], "SDTS _probe")

    def test_spec_ambiguity_behavior_child_env_has_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SAI 行为探针（历史 **os.environ 直传）：子进程 env 无宿主凭证。"""
        from experiments import spec_ambiguity

        _poison_host_env(monkeypatch)
        calls = _capture_run_with_timeout(monkeypatch, stdout='{"kind": "ok", "value": "1"}')
        result = spec_ambiguity._behavior(
            "def f(x):\n    return x + 1\n",
            "f",
            "audit_mod",
            [1],
            timeout=10,
        )
        assert result is not None and result.startswith("ok:")
        probe_calls = [call for call in calls if any(str(part).endswith("_sai_probe.py") for part in call["cmd"])]
        assert len(probe_calls) == 1, f"SAI 探针站点应恰好启动一次探针子进程，实际 {len(probe_calls)}"
        _assert_untrusted_child_env(probe_calls[0], "SAI _behavior")

    def test_real_sdts_and_sai_probes_cannot_read_host_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端（真实子进程）：两处候选代码探针执行"读 env 的被测代码"也读不到凭证。"""
        from experiments import solver_directed_trigger, spec_ambiguity

        monkeypatch.setenv("LLM_1_API_KEY", "AUDIT_SENTINEL")
        # 被测代码主动尝试读取凭证：旧口径（**os.environ）会返回 AUDIT_SENTINEL。
        code = "import os\n\ndef f(x):\n    return os.environ.get('LLM_1_API_KEY', 'MISSING')\n"
        sdts = solver_directed_trigger._probe(code, "audit_env_mod", "f", [1], 30)
        sai = spec_ambiguity._behavior(code, "f", "audit_env_mod", [1], 30)
        for label, result in (("SDTS", sdts), ("SAI", sai)):
            assert result is not None, f"{label} 真实探针未返回结果"
            assert "AUDIT_SENTINEL" not in result, f"{label} 探针子进程仍能读取宿主凭证（A08 回归）：{result}"
            assert "MISSING" in result, f"{label} 探针结果不符合预期：{result}"


# ───────────────────────── 4) 静态接线锁：新入口必须引用统一构造器 ─────────────────────────


_IN_SCOPE_EXECUTION_SITES: tuple[tuple[str, str], ...] = (
    ("experiments/_m1_metrics.py", "_run_pytest_in_tmp"),
    ("src/measurement/mdo.py", "_run_probe"),
    ("src/measurement/mdo.py", "_run_tests_on_code"),
    ("src/tools/patch_rollback.py", "run_p2p_regression"),
    # A08 收尾追加（Lead 批准扩写域）：候选/生成代码行为探针的真实不可信入口。
    ("experiments/solver_directed_trigger.py", "_probe"),
    ("experiments/spec_ambiguity.py", "_behavior"),
)


def _function_node(rel_path: str, func_name: str) -> ast.FunctionDef:
    tree = ast.parse((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == func_name]
    assert len(matches) == 1, f"{rel_path}::{func_name} 无法唯一定位（{len(matches)} 处）"
    return matches[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel_path", "func_name"),
    _IN_SCOPE_EXECUTION_SITES,
    ids=[f"{path.split('/')[-1]}::{func}" for path, func in _IN_SCOPE_EXECUTION_SITES],
)
def test_in_scope_execution_site_uses_untrusted_exec_env(rel_path: str, func_name: str) -> None:
    """A08 接线锁：不可信执行入口的 env 必须由统一构造器构造（防回退到裸继承）。"""
    func = _function_node(rel_path, func_name)
    calls = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "untrusted_exec_env"
    ]
    assert calls, f"{rel_path}::{func_name} 未使用 untrusted_exec_env（A08 回退风险）"
