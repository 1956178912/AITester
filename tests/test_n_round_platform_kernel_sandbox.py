"""N-2 回归锁：内核沙箱 Seatbelt profile 语法（macOS）与真实执行能力。

背景（N-2 e2e 探针实跑发现，2026-10-17）
------------------------------------------
`scripts/tools/e2e_probes_platform.py::security-kernel-sandbox` 首次把
`build_sandbox_command` 的产物**真实执行**（此前单元测试只断言 argv 形状），
在 macOS 27 上暴露两处静默失效：

1. `_seatbelt_profile` 用 Python `repr()`（`f"(subpath {path!r})"`）生成路径字面量，
   写成**单引号**字符串；SBPL 只接受双引号字符串 →
   `sandbox-exec -p ...` 直接 rc=65：
   `sandbox-exec: unexpected symbol argument ... (subpath '/tmp')`。
   即 `KERNEL_SANDBOX_ENABLE=true` 的所有执行链路 100% 失效，且错误只出现在
   pytest 输出里，被归类为"测试失败"而不是"沙箱不可用"。
2. `(deny default)` 下缺少根目录/祖先目录 metadata 与根目录本身的 read 放行 →
   沙箱进程在 dyld/路径解析阶段直接 SIGABRT（rc=-6，无任何错误输出）。

修复：`_sbpl_quote()`（JSON 双引号转义）+ profile 增加
`(allow file-read* (literal "/"))` / `(allow file-read-metadata (subpath "/"))`。

本文件锁定：SBPL 字面量转义、profile 不再含单引号 subpath、沙箱命令**真实可执行**；
平台不支持时显式 skip（不得崩溃）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from src.agents import kernel_sandbox
from src.agents.kernel_sandbox import (
    SandboxUnavailable,
    _sbpl_quote,
    _seatbelt_profile,
    build_sandbox_command,
    describe_capabilities,
    sandbox_supported,
)


class TestSbplQuote:
    """SBPL 字符串字面量：双引号 + 反斜杠/引号转义（单引号是 rc=65 的根因）。"""

    def test_plain_path_is_double_quoted(self) -> None:
        assert _sbpl_quote("/tmp/foo") == '"/tmp/foo"'

    def test_no_single_quote_literals(self) -> None:
        quoted = _sbpl_quote("/tmp/foo")
        assert not quoted.startswith("'") and "'" not in quoted

    def test_backslash_escaped(self) -> None:
        # SBPL 双引号字符串中的反斜杠需要转义（JSON 口径）
        assert _sbpl_quote("C:\\tmp\\x") == '"C:\\\\tmp\\\\x"'

    def test_double_quote_escaped(self) -> None:
        assert _sbpl_quote('/tmp/a"b') == '"/tmp/a\\"b"'

    @pytest.mark.parametrize("path", ["/tmp/with space/dir", "/tmp/a'b", "/tmp/中文路径", "/tmp/./x"])
    def test_quoted_forms_parse_in_real_profile(self, path: str) -> None:
        """含空格/单引号/非 ASCII 的路径也必须生成可被 SBPL 解析的 profile。

        单引号在路径内容中出现是合法的（SBPL 字符串内部字符），关键是不能用
        单引号作为字面量定界符——这里断言 profile 里该行是双引号定界。
        """
        profile = _seatbelt_profile([path])
        line = next(item for item in profile.splitlines() if "file-read*" in item and "literal" not in item)
        assert line.startswith('(allow file-read* (subpath "'), f"非双引号定界：{line}"
        assert not line.startswith("(allow file-read* (subpath '")


class TestSeatbeltProfileSyntax:
    """profile 语法结构锁（真实可执行性的最小必要条件）。"""

    def test_profile_has_no_single_quoted_subpath(self) -> None:
        profile = _seatbelt_profile(["/tmp", "/workspace"])
        assert "(subpath '" not in profile, "Seatbelt profile 出现单引号 subpath（SBPL 语法错误，rc=65）"
        assert '(subpath "/tmp")' in profile
        assert '(subpath "/workspace")' in profile

    def test_root_rules_present_for_dyld_path_resolution(self) -> None:
        """缺根目录 read/metadata 时沙箱进程 SIGABRT（rc=-6，无错误输出）。"""
        profile = _seatbelt_profile(["/tmp"])
        assert '(allow file-read* (literal "/"))' in profile
        assert '(allow file-read-metadata (subpath "/"))' in profile

    def test_credential_deny_kept(self) -> None:
        """修复不得削弱 S2 凭证防线（.env/.ssh/.aws 等显式 DENY 必须保留）。"""
        profile = _seatbelt_profile(["/tmp"])
        assert "deny file-read*" in profile
        assert "llm_configs" in profile

    def test_unsupported_platform_still_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """平台不支持且未显式 ALLOW_UNSANDBOXED → 仍 fail-closed 抛 SandboxUnavailable。"""
        monkeypatch.setattr(kernel_sandbox, "_seatbelt_available", lambda: False)
        monkeypatch.setattr(kernel_sandbox, "_landlock_available", lambda: False)
        monkeypatch.delenv("ALLOW_UNSANDBOXED", raising=False)
        with pytest.raises(SandboxUnavailable):
            build_sandbox_command([sys.executable, "-c", "pass"], cwd="/tmp")


# ─── 真实执行锁（平台支持时；不支持时显式 skip，不静默通过） ───────────────


def _sandbox_exec_available() -> bool:
    """Seatbelt 存在且**生产 profile 真的能 apply**（A-09，2026-10-18 独立评审）。

    仅查 `shutil.which("sandbox-exec")` 不够：某些沙箱/容器宿主二进制存在、
    极简 profile 也可 apply，但**生产 profile**（`build_sandbox_command` 产物，
    含 subpath/deny 规则）以 `sandbox_apply: Operation not permitted`（rc=71）
    失败（嵌套沙箱限制）。此时真实执行锁无法判定——环境能力缺失而非代码缺陷，
    按项目既有 skipif 惯例显式 skip。
    """
    cap = describe_capabilities()
    if not (
        bool(cap.get("supported")) and cap.get("platform") == "darwin" and shutil.which("sandbox-exec") is not None
    ):
        return False
    try:
        cmd, _obs = build_sandbox_command(["/usr/bin/true"], cwd="/tmp", allowed_paths=["/tmp", "/bin", "/usr/bin"])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (SandboxUnavailable, OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


@pytest.mark.skipif(
    not _sandbox_exec_available(), reason="当前平台无可用 Seatbelt sandbox-exec（含 apply 被禁，显式 skip）"
)
def test_sandboxed_command_really_executes() -> None:
    """N-2 根因回归：`build_sandbox_command` 产物必须**真实可执行**（rc=0）。

    修复前该断言在 macOS 上 rc=65（profile 单引号语法错误）或 SIGABRT；
    仅断言 `cmd[0] == "sandbox-exec"` 的旧测试无法发现该失效。
    """
    cmd, obs = build_sandbox_command(
        ["/bin/echo", "sbpl-real-exec-ok"], cwd="/tmp", allowed_paths=["/tmp", "/bin", "/usr/bin"]
    )
    assert obs.get("supported") is True
    assert cmd[0] == "sandbox-exec"
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"沙箱命令执行失败 rc={proc.returncode}: {proc.stderr[:400]}"
    assert "sbpl-real-exec-ok" in proc.stdout


def test_sandbox_supported_implication() -> None:
    """capability 描述与 sandbox_supported() 一致（探针/执行器据此判定的单一事实源）。"""
    cap = describe_capabilities()
    assert isinstance(cap, dict)
    assert set(cap) >= {"platform", "supported", "backends", "notes"}
    assert bool(cap["supported"]) is bool(sandbox_supported())
    if cap["supported"]:
        assert cap["backends"], "supported=True 但 backends 为空"
