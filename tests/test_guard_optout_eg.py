"""EG 轮（2026-10-27）：默认开启的安全/质量守卫对坏值必须 fail-closed。

背景：以下 10 个开关（11 处读取）默认开启，历史统一用
``env_flag(name, True)`` 读取。env_flag 是**正集语义**（true/1/on），
于是任何非规范值——``yes`` / ``enabled`` / 拼错 / 空串——都会把守卫
**静默关闭**：危险 API 守卫放行危险补丁、凭证白名单退回黑名单
（子进程重新拿到 MYSQL_PASSWORD 等未列名变量）、venv 沙箱退回宿主
Python、Docker 容器丢掉只读根文件系统与断网。各 docstring 承诺的只是
「设 false 可显式退回」，坏值不在承诺范围内。

本轮按 J-2 既有口径迁到 ``env_flag_opt_out``：只有 false/0/off 关闭
守卫，其余值（含无法识别的坏值）保持开启——意图不可确认时选择保护。

边界（刻意不改，本文件同时锁定）：
- 默认关的特征/成本开关（``FL_SPECTRAL_ENABLE`` /
  ``TRACE_MEMORY_BUFFER_ENABLE`` / ``API_HEALTH_CHECKER_ENABLE`` 等）
  保持正集语义：坏值不得隐式**开启**功能（拼错不应启动后台配额消耗
  或实验特性）；
- testless 的 ``_layer_enabled`` 层开关属于「测量层是否运行」，关闭会在
  status 通道显式披露（VALIDATION_DISABLED），不属于「守卫静默放行」族。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
# 坏值族：自然写法（yes/enabled）、拼错、空串——都不是 env_flag 的正集字面量
JUNK_VALUES = ("yes", "enabled", "ture", "")


# ─── 凭证白名单（CREDENTIAL_SCRUB_WHITELIST_ENABLE）───────────────────────────


@pytest.mark.parametrize("raw", JUNK_VALUES)
def test_credential_whitelist_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.utils.credential_scrub import whitelist_enabled

    monkeypatch.setenv("CREDENTIAL_SCRUB_WHITELIST_ENABLE", raw)
    assert whitelist_enabled() is True


def test_credential_whitelist_junk_keeps_secrets_out_of_child_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：坏值不得把白名单退回黑名单（MYSQL_PASSWORD 不进子进程环境）。"""
    from src.utils.credential_scrub import scrub_os_environ

    monkeypatch.setenv("CREDENTIAL_SCRUB_WHITELIST_ENABLE", "yes")
    monkeypatch.setenv("MYSQL_PASSWORD", "eg-dummy-not-a-secret")
    env = scrub_os_environ()
    assert "MYSQL_PASSWORD" not in env
    # 白名单基本变量仍在（失败形态是"白名单没生效"而非"环境被清空"）
    assert env.get("PATH") == os.environ.get("PATH")


# ─── pip 包名白名单（PIP_PACKAGE_WHITELIST_ENABLE）────────────────────────────


def test_pip_whitelist_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools.dependency import suggest_package_names

    monkeypatch.setenv("PIP_PACKAGE_WHITELIST_ENABLE", "yes")
    monkeypatch.delenv("PIP_PACKAGE_WHITELIST", raising=False)
    assert suggest_package_names({"eg_definitely_not_whitelisted_pkg"}) == []


# ─── 危险 API 守卫（PATCH_DANGEROUS_API_GUARD）────────────────────────────────


@pytest.mark.parametrize("raw", JUNK_VALUES)
def test_dangerous_api_guard_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.tools.patch_applier import _dangerous_api_guard_enabled

    monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", raw)
    assert _dangerous_api_guard_enabled() is True


def test_dangerous_api_guard_junk_still_rejects_dangerous_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools.patch_applier import safe_apply_patch

    monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "yes")
    original = "def foo():\n    return 0\n"
    patch_code = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
    new_code, success = safe_apply_patch(original, patch_code)
    assert success is False
    assert new_code == original


# ─── 命名契约检查（PATCH_CONTRACT_CHECK，两处消费点）──────────────────────────


def test_contract_check_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools.patch_applier import check_naming_contract

    monkeypatch.setenv("PATCH_CONTRACT_CHECK", "yes")
    original = "def kept():\n    return 0\n\n\ndef dropped():\n    return 1\n"
    patched = "def kept():\n    return 0\n"
    ok, missing = check_naming_contract(original, patched)
    assert (ok, missing) == (False, ["dropped"])


def test_testless_contract_layer_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.tools.testless_validation import VALIDATION_DISABLED, _run_naming_contract_layer

    monkeypatch.setenv("PATCH_CONTRACT_CHECK", "yes")
    out = _run_naming_contract_layer("def dropped():\n    return 1\n", "x = 1\n")
    assert out["status"] != VALIDATION_DISABLED
    assert out["passed"] is False


# ─── 输出侧注入守卫（INJECTION_GUARD_OUTPUT_ENABLE）───────────────────────────


@pytest.mark.parametrize("raw", JUNK_VALUES)
def test_injection_output_guard_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.agents.injection_guard import check_llm_patch_safety, injection_guard_output_enabled

    monkeypatch.setenv("INJECTION_GUARD_OUTPUT_ENABLE", raw)
    assert injection_guard_output_enabled() is True
    assert "dangerous_shell" in check_llm_patch_safety("import os\nos.system('ls')\n")


# ─── 证据门（PATCH_EVIDENCE_GATE_ENABLE）──────────────────────────────────────


@pytest.mark.parametrize("raw", JUNK_VALUES)
def test_evidence_gate_junk_keeps_guard(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.tools.patch_evidence import patch_evidence_gate_enabled

    monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", raw)
    assert patch_evidence_gate_enabled() is True


# ─── config 导入期常量（EXECUTOR_USE_VENV / SWE_BENCH_P2P_GATE_ENABLE）───────


def _config_constants_with_env(extra: dict[str, str]) -> str:
    """在子进程里带指定环境变量重新 import config，读两个守卫常量的布尔值。"""
    env = dict(os.environ)
    env.update(extra)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config; print(config.EXECUTOR_USE_VENV, config.SWE_BENCH_P2P_GATE_ENABLE)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return proc.stdout.strip()


def test_config_sandbox_guards_junk_fail_closed() -> None:
    out = _config_constants_with_env(
        {"EXECUTOR_USE_VENV": "yes", "SWE_BENCH_P2P_GATE_ENABLE": "enabled"},
    )
    assert out == "True True"


def test_config_sandbox_guards_explicit_off_preserved() -> None:
    out = _config_constants_with_env(
        {"EXECUTOR_USE_VENV": "false", "SWE_BENCH_P2P_GATE_ENABLE": "off"},
    )
    assert out == "False False"


# ─── Docker 沙箱（DOCKER_READ_ONLY / DOCKER_DEFAULT_NETWORK_NONE）────────────


def _execute_docker_cmd(extra_env: dict[str, str]) -> list[str]:
    from src.agents.executor import ExecutorAgent
    from tests.test_sandbox_hardening import _call_execute_docker

    agent = ExecutorAgent(timeout=30, use_docker=True, docker_image="aitester:latest")
    out = _call_execute_docker(agent, extra_env)
    cmd = out["cmd"]
    assert isinstance(cmd, list)
    return cmd


def test_docker_read_only_junk_keeps_flag() -> None:
    cmd = _execute_docker_cmd({"DOCKER_READ_ONLY": "yes"})
    assert "--read-only" in cmd
    assert "/tmp:size=256m" in cmd


def test_docker_network_none_junk_keeps_flag() -> None:
    # 显式置 DOCKER_NETWORK_ISOLATION=false：确保 --network=none 只可能来自
    # DOCKER_DEFAULT_NETWORK_NONE，不被宿主环境影响成假绿
    cmd = _execute_docker_cmd(
        {"DOCKER_DEFAULT_NETWORK_NONE": "yes", "DOCKER_NETWORK_ISOLATION": "false"},
    )
    assert "--network=none" in cmd


# ─── 边界：显式关闭仍按文档生效（防矫枉过正）─────────────────────────────────


@pytest.mark.parametrize("raw", ["false", "0", "off", "OFF"])
def test_explicit_off_still_disables_guards(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.agents.injection_guard import injection_guard_output_enabled
    from src.tools.patch_applier import _dangerous_api_guard_enabled
    from src.tools.patch_evidence import patch_evidence_gate_enabled
    from src.utils.credential_scrub import whitelist_enabled

    monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", raw)
    monkeypatch.setenv("INJECTION_GUARD_OUTPUT_ENABLE", raw)
    monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", raw)
    monkeypatch.setenv("CREDENTIAL_SCRUB_WHITELIST_ENABLE", raw)
    assert _dangerous_api_guard_enabled() is False
    assert injection_guard_output_enabled() is False
    assert patch_evidence_gate_enabled() is False
    assert whitelist_enabled() is False


# ─── 边界：特征/诊断开关保持正集语义（坏值不得隐式开启）──────────────────────


def test_measurement_feature_flag_positive_set_semantics_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.agents.fl_spectral import fl_spectral_enabled

    monkeypatch.setenv("FL_SPECTRAL_ENABLE", "yes")
    assert fl_spectral_enabled() is False


def test_diagnostic_buffer_flag_positive_set_semantics_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.observability.trace import _memory_buffer_enabled

    monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "yes")
    assert _memory_buffer_enabled() is False
