"""N-2 追加回归锁：执行器内核沙箱接线修复（KERNEL_SANDBOX_ENABLE=true 可用）。

背景（N-2 e2e 探针发现的 P0 静默失效，Lead 批准追加修复）
--------------------------------------------------------
`security-kernel-sandbox` 探针 + 真实执行暴露：内核沙箱 profile 语法修好后，
执行器仍 100% 失败——`src/agents/executor.py:239`（本地）与
`src/agents/executor_modes.py:148`（venv）的接线只放行任务目录，未放行
**解释器自身**（venv/bin/python 字面路径、framework Python.app、venv 根/
pyvenv.cfg、stdlib）与 pytest 临时目录 → `sandbox-exec: execvp() of
'.../.venv/bin/python' failed: Operation not permitted`（rc=71），而该失败被
`build_error_info` 统一归类为 `test_failure`（Debugger 会去"修代码"而不是
发现沙箱不可用，失败归因/M1 观测口径被污染）。

本文件锁定修复后的四类行为：
1. **解释器放行面**（`interpreter_sandbox_allowances`：exec/read 分离、venv 根
   只在 pyvenv.cfg 存在时只读放行）；
2. **profile 细粒度规则**（exec 用 literal 文件/subpath 目录；realpath 变体；
   凭证 DENY 修正后 `.venv` 可读、`.env` 仍被拒）；
3. **执行器真实可用**（local + venv 两种模式在 KERNEL_SANDBOX_ENABLE=true 下
   真实 execute 必须 passed；cwd 只读、不写仓库根）；
4. **错误分类**（沙箱配置/启动失败 → `error_info.type=kernel_sandbox_unavailable`，
   不再 `test_failure`；不新增 ErrorCategory 枚举值；默认关闭零行为变化）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from src.agents import kernel_sandbox
from src.agents.error_classifier import ErrorCategory
from src.agents.executor import ExecutorAgent
from src.agents.executor_output import build_error_info
from src.agents.kernel_sandbox import (
    SandboxUnavailable,
    _seatbelt_profile,
    build_sandbox_command,
    interpreter_sandbox_allowances,
    sandbox_launch_failure,
    sandbox_supported,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TINY_TARGET = "def add(a, b):\n    return a + b\n"
_TINY_TEST = "from tinymod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"

_SEATBELT_OK = sandbox_supported() and sys.platform == "darwin"
_ANY_SANDBOX_OK = sandbox_supported()


def _write_tiny_target(tmpdir: str) -> str:
    target = os.path.join(tmpdir, "tinymod.py")
    Path(target).write_text(_TINY_TARGET, encoding="utf-8")
    return target


# ─────────────────────────── 1. 解释器放行面 ───────────────────────────


class TestInterpreterAllowances:
    def test_exec_and_read_keys_present(self) -> None:
        allow = interpreter_sandbox_allowances(sys.executable)
        assert set(allow) == {"exec_paths", "read_paths", "write_paths"}
        assert allow["write_paths"] == [], "解释器放行面不得包含可写路径（临时目录由调用方加）"
        assert allow["exec_paths"] and allow["read_paths"]

    def test_exec_contains_literal_and_realpath_and_install_root(self) -> None:
        exe = sys.executable
        real = os.path.realpath(exe)
        allow = interpreter_sandbox_allowances(exe)
        assert exe in allow["exec_paths"], "解释器字面路径（venv/bin/python）必须在 exec 面"
        assert real in allow["exec_paths"], "解释器 realpath（framework python）必须在 exec 面"
        install_root = os.path.dirname(os.path.dirname(os.path.abspath(real)))
        assert install_root in allow["exec_paths"], "framework/系统安装根必须在 exec 面（含 Python.app）"
        assert os.path.dirname(os.path.abspath(exe)) in allow["exec_paths"]

    def test_venv_root_read_only_only_when_pyvenv_cfg_exists(self, tmp_path: Path) -> None:
        # 构造真实 venv 布局：venv/bin/python 是指向真实解释器的符号链接
        # （realpath 落在 venv 之外 → install_root 是 framework 根，不会混淆断言）
        venv = tmp_path / "fakevenv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").symlink_to(sys.executable)
        fake_python = venv / "bin" / "python"
        (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
        with_venv = interpreter_sandbox_allowances(str(fake_python))
        assert str(venv) in with_venv["read_paths"], "venv 根（pyvenv.cfg 所在）必须只读放行"
        assert str(venv) not in with_venv["write_paths"], "venv 根不得进入可写面"
        (venv / "pyvenv.cfg").unlink()
        without_venv = interpreter_sandbox_allowances(str(fake_python))
        assert str(venv) not in without_venv["read_paths"]

    def test_system_python_has_no_fake_venv_root(self) -> None:
        allow = interpreter_sandbox_allowances("/usr/bin/python3")
        assert "/usr" in allow["read_paths"] or "/usr/bin" in allow["read_paths"]


# ─────────────────────────── 2. profile 细粒度规则 ───────────────────────────


class TestProfileScopedRules:
    def test_exec_file_uses_literal_dir_uses_subpath(self, tmp_path: Path) -> None:
        exe_file = tmp_path / "bin" / "python"
        exe_file.parent.mkdir(parents=True)
        exe_file.write_text("", encoding="utf-8")
        profile = _seatbelt_profile([str(tmp_path)], exec_paths=[str(exe_file), str(exe_file.parent)])
        quoted = str(exe_file)
        assert f'(allow process-exec (literal "{quoted}"))' in profile, "文件 exec 必须用 literal（subpath 对文件无效）"
        assert f'(allow process-exec (subpath "{exe_file.parent}"))' in profile, "目录 exec 必须用 subpath"

    def test_read_and_write_scopes_are_separate(self, tmp_path: Path) -> None:
        read_dir = tmp_path / "readonly"
        write_dir = tmp_path / "writable"
        read_dir.mkdir()
        write_dir.mkdir()
        profile = _seatbelt_profile([str(tmp_path / "task")], read_paths=[str(read_dir)], write_paths=[str(write_dir)])
        assert f'(allow file-read* (subpath "{read_dir}"))' in profile
        assert f'(allow file-write* (subpath "{read_dir}"))' not in profile, "只读放行不得隐含可写"
        assert f'(allow file-write* (subpath "{write_dir}"))' in profile

    def test_realpath_variants_emitted_for_symlinked_paths(self, tmp_path: Path) -> None:
        """/tmp → /private/tmp、/var → /private/var 等符号链接需双形式放行（实测 TMPDIR scandir 被拒根因）。"""
        target = tmp_path / "real_dir"
        target.mkdir()
        link = tmp_path / "link_dir"
        link.symlink_to(target)
        profile = _seatbelt_profile([str(link)])
        real = os.path.realpath(str(link))
        assert real != str(link)
        assert f'(subpath "{real}")' in profile, "符号链接路径必须同时放行 realpath 形式"
        assert f'(subpath "{link}")' in profile

    def test_credential_deny_regex_does_not_block_venv(self) -> None:
        """N-2 二次修复：历史 `.env.*` 会把 `.venv/` 整棵树 DENY（pyvenv.cfg PermissionError）。"""
        profile = _seatbelt_profile(["/tmp"])
        deny_line = next(line for line in profile.splitlines() if "deny file-read*" in line)
        # 语义验证：SBPL 正则 #"..." 中 `.env` 不应匹配 `.venv`
        import re as _re

        raw = deny_line.split('#"', 1)[1].rsplit('"', 1)[0]
        pattern = _re.compile(raw)
        assert pattern.search("/Users/x/project/.venv/pyvenv.cfg") is None, f"DENY 误伤 .venv：{raw}"
        assert pattern.search("/Users/x/project/.env") is not None, "DENY 必须仍命中 .env"
        assert pattern.search("/Users/x/project/.env.local") is not None, "DENY 必须仍命中 .env.local"

    def test_deny_still_blocks_ssh_aws_credentials(self) -> None:
        profile = _seatbelt_profile(["/tmp"])
        deny_line = next(line for line in profile.splitlines() if "deny file-read*" in line)
        import re as _re

        pattern = _re.compile(deny_line.split('#"', 1)[1].rsplit('"', 1)[0])
        for path in ("/Users/x/.ssh/id_rsa", "/Users/x/.aws/credentials", "/Users/x/llm_configs.json"):
            assert pattern.search(path) is not None, f"凭证路径未被 DENY：{path}"


# ─────────────────────────── 3. build_sandbox_command 扩展参数 ───────────────────────────


class TestBuildSandboxCommandScopes:
    def test_cwd_rw_false_keeps_cwd_read_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(kernel_sandbox, "_seatbelt_available", lambda: True)
        monkeypatch.setattr(kernel_sandbox, "_landlock_available", lambda: False)
        cmd, obs = build_sandbox_command(
            ["/bin/echo", "x"],
            cwd="/repo/root",
            allowed_paths=["/tmp/task"],
            cwd_rw=False,
            read_paths=["/repo/root"],
        )
        assert "/repo/root" not in obs["allowed_paths"], "cwd 不得写成可写 allowed_paths（防写仓库根）"
        assert "/repo/root" in obs["read_paths"]
        assert obs["cwd_rw"] is False
        profile = cmd[2]
        assert '(allow file-write* (subpath "/repo/root"))' not in profile

    def test_cwd_rw_true_backward_compatible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(kernel_sandbox, "_seatbelt_available", lambda: True)
        monkeypatch.setattr(kernel_sandbox, "_landlock_available", lambda: False)
        _cmd, obs = build_sandbox_command(["/bin/echo", "x"], cwd="/tmp/task")
        assert "/tmp/task" in obs["allowed_paths"]
        assert obs["cwd_rw"] is True

    def test_obs_reports_scopes_for_audit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(kernel_sandbox, "_seatbelt_available", lambda: True)
        monkeypatch.setattr(kernel_sandbox, "_landlock_available", lambda: False)
        _, obs = build_sandbox_command(
            ["/bin/echo"],
            cwd="/tmp",
            exec_paths=["/usr/bin/python3"],
            read_paths=["/opt/lib"],
            write_paths=["/tmp/w"],
        )
        for key in ("allowed_paths", "exec_paths", "read_paths", "write_paths", "cwd_rw", "profile_summary"):
            assert key in obs, f"obs 缺审计字段：{key}"


# ─────────────────────────── 4. 沙箱启动失败分类 ───────────────────────────


class TestSandboxLaunchFailureDetection:
    @pytest.mark.parametrize(
        ("output", "expect"),
        [
            ("sandbox-exec: execvp() of '/x/python' failed: Operation not permitted", True),
            ("sandbox-exec: unexpected symbol argument\n<input string>:3:20:", True),
            ("bwrap: Creating new namespace failed", True),
            ("failed: Operation not permitted", True),
            ("1 passed in 0.30s", False),
            ("FAILED test_x.py::test_a - AssertionError: assert 1 == 2", False),
            ("", False),
        ],
    )
    def test_detects_launcher_failures_only(self, output: str, expect: bool) -> None:
        found = sandbox_launch_failure(output)
        assert (found is not None) is expect, f"分类错误：output={output!r} found={found!r}"

    def test_build_error_info_still_test_failure_for_real_test_failures(self) -> None:
        """真实测试失败仍走 test_failure（分类只在沙箱场景覆盖，不影响既有口径）。"""
        proc = subprocess.CompletedProcess(["pytest"], 1, stdout="", stderr="")
        info = build_error_info(proc, "FAILED test_x.py::test_a - AssertionError")
        assert info["type"] == "test_failure"


# ─────────────────────────── 5. 执行器真实可用（正/负控） ───────────────────────────


def _run_executor(*, use_venv: bool, sandbox: bool) -> dict:
    tmpdir = tempfile.mkdtemp(prefix="n2_exec_sandbox_")
    try:
        target = _write_tiny_target(tmpdir)
        env_backup = os.environ.get("KERNEL_SANDBOX_ENABLE")
        if sandbox:
            os.environ["KERNEL_SANDBOX_ENABLE"] = "true"
        else:
            os.environ.pop("KERNEL_SANDBOX_ENABLE", None)
        try:
            agent = ExecutorAgent(timeout=120, use_docker=False, use_venv=use_venv)
            return agent.execute(_TINY_TEST, target)
        finally:
            if env_backup is None:
                os.environ.pop("KERNEL_SANDBOX_ENABLE", None)
            else:
                os.environ["KERNEL_SANDBOX_ENABLE"] = env_backup
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


class TestExecutorSandboxRealExecute:
    def test_default_off_zero_behavior_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """默认关（KERNEL_SANDBOX_ENABLE 未设）：不构建沙箱、无 obs、零行为变化。"""
        calls: list[bool] = []

        def _spy(*args, **kwargs):  # pragma: no cover - 默认关时不应被调用
            calls.append(True)
            raise AssertionError("默认关时不得调用 build_sandbox_command")

        monkeypatch.setattr(kernel_sandbox, "build_sandbox_command", _spy)
        result = _run_executor(use_venv=False, sandbox=False)
        assert result["passed"] is True
        assert calls == [], "默认关路径调用了沙箱构建（行为变化）"
        assert "kernel_sandbox_obs" not in result

    @pytest.mark.skipif(not _ANY_SANDBOX_OK, reason="当前平台无可用内核沙箱（显式 skip）")
    def test_local_sandbox_execute_passes(self) -> None:
        """**修复锁**（原缺陷：execvp Operation not permitted / rc=71）。"""
        result = _run_executor(use_venv=False, sandbox=True)
        assert result["passed"] is True, (
            f"内核沙箱下本地执行器未通过：error_info={result.get('error_info')} "
            f"output_tail={(result.get('output') or '')[-500:]}"
        )
        assert result.get("kernel_sandbox_obs"), "缺失 kernel_sandbox_obs 观测层"
        assert result["coverage"] == pytest.approx(100.0)

    @pytest.mark.skipif(not _ANY_SANDBOX_OK, reason="当前平台无可用内核沙箱（显式 skip）")
    def test_venv_sandbox_execute_passes(self) -> None:
        result = _run_executor(use_venv=True, sandbox=True)
        assert result["passed"] is True, (
            f"内核沙箱下 venv 执行器未通过：error_info={result.get('error_info')} "
            f"output_tail={(result.get('output') or '')[-500:]}"
        )
        assert result.get("kernel_sandbox_obs")

    def test_sandbox_cwd_read_only_no_repo_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """沙箱模式不得把仓库根写成可写（executor 传 cwd_rw=False）。"""
        captured: dict = {}
        from src.agents import executor as executor_module

        real_build = executor_module.ExecutorAgent._execute_local  # 仅用于类型引用

        def _spy_build(cmd, cwd=None, allowed_paths=None, **kwargs):
            captured.update({"cwd": cwd, "allowed_paths": allowed_paths, **kwargs})
            raise SandboxUnavailable("stop-after-capture")

        monkeypatch.setattr(kernel_sandbox, "build_sandbox_command", _spy_build)
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")
        try:
            tmpdir = tempfile.mkdtemp(prefix="n2_exec_cwd_")
            target = _write_tiny_target(tmpdir)
            result = ExecutorAgent(timeout=60, use_docker=False, use_venv=False).execute(_TINY_TEST, target)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
        assert result["error_info"]["type"] == "kernel_sandbox_unavailable"
        assert captured["cwd_rw"] is False, "executor 必须传 cwd_rw=False（仓库根只读）"
        assert captured["cwd"] not in (captured.get("allowed_paths") or [])
        assert real_build  # 使用一次，避免 lint 未使用

    def test_unsupported_platform_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无沙箱后端且未 ALLOW_UNSANDBOXED → 显式 kernel_sandbox_unavailable（不裸跑）。"""
        monkeypatch.setattr(kernel_sandbox, "_seatbelt_available", lambda: False)
        monkeypatch.setattr(kernel_sandbox, "_landlock_available", lambda: False)
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")
        monkeypatch.delenv("ALLOW_UNSANDBOXED", raising=False)
        try:
            tmpdir = tempfile.mkdtemp(prefix="n2_exec_unsup_")
            target = _write_tiny_target(tmpdir)
            result = ExecutorAgent(timeout=60, use_docker=False, use_venv=False).execute(_TINY_TEST, target)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
        assert result["passed"] is False
        assert result["error_info"]["type"] == "kernel_sandbox_unavailable"
        assert "ALLOW_UNSANDBOXED" in result["output"] or "不可用" in result["output"]

    def test_launcher_failure_classified_not_test_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """沙箱启动失败（execvp/syntax error）→ kernel_sandbox_unavailable，不误报 test_failure。"""
        fake_obs = {"platform": "darwin", "backend": "seatbelt", "supported": True, "profile_summary": "fake"}

        def _fake_build(cmd, cwd=None, allowed_paths=None, **kwargs):
            return (
                [
                    "/bin/sh",
                    "-c",
                    'echo "sandbox-exec: execvp() of x failed: Operation not permitted" >&2; exit 71',
                ],
                fake_obs,
            )

        monkeypatch.setattr(kernel_sandbox, "build_sandbox_command", _fake_build)
        monkeypatch.setenv("KERNEL_SANDBOX_ENABLE", "true")
        tmpdir = tempfile.mkdtemp(prefix="n2_exec_launchfail_")
        try:
            target = _write_tiny_target(tmpdir)
            result = ExecutorAgent(timeout=60, use_docker=False, use_venv=False).execute(_TINY_TEST, target)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
        assert result["passed"] is False
        assert result["error_info"]["type"] == "kernel_sandbox_unavailable", result.get("error_info")
        assert result["error_info"]["returncode"] == 71
        assert "execvp" in result["error_info"]["message"]
        assert result.get("kernel_sandbox_launch_failed") is True


class TestSafeProfileEndToEnd:
    """safe 档（AITESTER_PROFILE=safe，KERNEL_SANDBOX_ENABLE=true 默认注入）端到端。"""

    @pytest.mark.skipif(not _ANY_SANDBOX_OK, reason="当前平台无可用内核沙箱（显式 skip）")
    def test_safe_profile_executor_passes_zero_llm(self) -> None:
        """子进程按 safe 档启动 → 执行器真实沙箱执行最小测试必须 passed。

        子进程隔离以确保 `config._apply_profile_presets()`（进程 import 期注入）
        真实生效；零 LLM（不经过 generator）。
        """
        script = (
            "import json, os, sys, tempfile\n"
            "from src.agents.executor import ExecutorAgent\n"
            "tmp = tempfile.mkdtemp(prefix='n2_safe_'); target = os.path.join(tmp, 'tinymod.py')\n"
            "open(target, 'w').write('def add(a, b):\\n    return a + b\\n')\n"
            "res = ExecutorAgent(timeout=120, use_docker=False, use_venv=False).execute(\n"
            "    'from tinymod import add\\n\\ndef test_add():\\n    assert add(1, 2) == 3\\n', target)\n"
            "print(json.dumps({'passed': res.get('passed'), 'kernel_sandbox_obs': res.get('kernel_sandbox_obs'), "
            "'error_info': res.get('error_info'), 'coverage': res.get('coverage'), "
            "'kernel_sandbox_enabled': os.environ.get('KERNEL_SANDBOX_ENABLE'), "
            "'active_profile': __import__('config').ACTIVE_PROFILE}, ensure_ascii=False))\n"
        )
        env = {**os.environ, "AITESTER_PROFILE": "safe", "PYTHONPATH": str(_REPO_ROOT)}
        env.pop("KERNEL_SANDBOX_ENABLE", None)  # 由 safe 档预设注入（验证预设真实生效）
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=300, cwd=str(_REPO_ROOT), env=env
        )
        assert proc.returncode == 0, f"safe 档子进程失败：{proc.stderr[-800:]}"
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["active_profile"] == "safe"
        assert payload["kernel_sandbox_enabled"] == "true", "safe 档未注入 KERNEL_SANDBOX_ENABLE"
        assert payload["passed"] is True, f"safe 档执行器未通过：{payload}"
        assert (payload.get("kernel_sandbox_obs") or {}).get("supported") is True
        assert float(payload.get("coverage") or 0.0) > 0.0


# ─────────────────────────── 6. 枚举/口径不变 + deny 行为真实验证 ───────────────────────────


class TestNoEnumChange:
    def test_error_category_enum_unchanged(self) -> None:
        """最小方案：只用 error_info.type 显式字符串，不新增 ErrorCategory 枚举值。"""
        assert len(ErrorCategory) == 18, (
            f"ErrorCategory 枚举数量变化（BASELINE error_categories=18）：{len(ErrorCategory)}"
        )
        assert not hasattr(ErrorCategory, "KERNEL_SANDBOX_UNAVAILABLE")
        assert "kernel_sandbox_unavailable" not in {item.value for item in ErrorCategory}


@pytest.mark.skipif(not _SEATBELT_OK, reason="需要 macOS Seatbelt（显式 skip）")
class TestSeatbeltDangerousPathRealDeny:
    """真实执行验证：修正后的 DENY 正则不误伤 .venv，但 .env/.ssh 仍被拒。"""

    def _run_in_sandbox(self, allowed_root: Path, target: Path) -> int:
        # /bin/cat 需要 process-exec 放行（profile 默认只放行 /usr；/bin 为真实目录）
        profile = _seatbelt_profile([str(allowed_root), "/bin"])
        cmd = ["sandbox-exec", "-p", profile, "/bin/cat", str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return proc.returncode

    def test_venv_pyvenv_cfg_readable_but_env_denied(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        pyvenv = venv / "pyvenv.cfg"
        pyvenv.write_text("home = /usr\n", encoding="utf-8")
        secret = tmp_path / ".env"
        secret.write_text("API_KEY=sk-should-not-leak\n", encoding="utf-8")
        profile = _seatbelt_profile([str(tmp_path), "/bin"])
        # .venv 内容必须可读（此前 DENY 正则误伤 → pyvenv.cfg PermissionError）
        ok = subprocess.run(
            ["sandbox-exec", "-p", profile, "/bin/cat", str(pyvenv)], capture_output=True, text=True, timeout=60
        )
        assert ok.returncode == 0, f".venv/pyvenv.cfg 在沙箱内不可读（DENY 误伤）：{ok.stderr[:300]}"
        # 凭证文件仍必须被拒（S2 防线不回退）
        denied = subprocess.run(
            ["sandbox-exec", "-p", profile, "/bin/cat", str(secret)], capture_output=True, text=True, timeout=60
        )
        assert denied.returncode != 0, "沙箱内仍可读 .env（凭证 DENY 失效）"
        assert "sk-should-not-leak" not in denied.stdout
