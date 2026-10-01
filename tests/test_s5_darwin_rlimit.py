"""
S5 平台兜底回归（2026-10-01 主批次实跑发现）：
macOS（Darwin）上**任何** resource.setrlimit(RLIMIT_AS, ...) 调用都会
抛 SubprocessError（本机 Python 3.14 实测：2GB/128GB/current+1 均失败——
Darwin 对该 rlimit 的限制整体不支持）——此前 S5 在 Darwin 上也设 AS
限制导致**所有**子进程 pytest 直接 SubprocessError 失败
（主批次 0/5 全失败即此原因）。

本测试锁死口径：
- Darwin 平台 _make_resource_preexec_fn 返回的闭包**跳过** RLIMIT_AS
  （保留 CPU/NPROC/FSIZE/NOFILE 四项），直接调用不抛；
- 显式 EXECUTOR_RLIMIT_AS_FORCE=1 可在 Darwin 上强制启用 AS（自担风险）；
- 非 POSIX / 无 resource 模块时 _make_resource_preexec_fn 返回 None。
"""

from __future__ import annotations

import os
import platform
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.agents.executor_runtime as er


def _spy_setrlimit():
    """返回 (called_names, spy_fn)：记录闭包实际设置了哪些 rlimit。"""
    import resource

    called: list[str] = []
    _names = {
        resource.RLIMIT_CPU: "CPU",
        resource.RLIMIT_AS: "AS",
        resource.RLIMIT_NPROC: "NPROC",
        resource.RLIMIT_FSIZE: "FSIZE",
        resource.RLIMIT_NOFILE: "NOFILE",
    }

    def _spy(which, limits):
        called.append(_names.get(which, str(which)))

    return called, _spy, resource


class TestDarwinASSkip:
    """macOS 上 RLIMIT_AS 兜底跳过。"""

    def test_preexec_fn_returns_callable_on_posix(self):
        """POSIX（Linux/Darwin）下 preexec_fn 返回可调用对象（非 None）。

        注意：**不在宿主进程直接调用该闭包**——调用会实际 setrlimit
        宿主 pytest 进程（CPU/NOFILE/NPROC 等），污染后续子进程测试
        （历史版本曾在宿主调用导致后续 M1 子进程 pytest fd 受限失败）。
        仅验证返回类型 + Darwin 跳过 AS 的口径（经 spy 子测试覆盖）。
        """
        fn = er._make_resource_preexec_fn()
        if fn is None:
            # Windows / 无 resource 模块：返回 None（历史口径）
            return
        assert callable(fn)

    def test_darwin_skips_as_by_default(self, monkeypatch):
        """Darwin 平台默认 → AS 限制被跳过（_enable_as=False）。"""
        monkeypatch.setattr(er, "_IS_DARWIN", True)
        monkeypatch.delenv("EXECUTOR_RLIMIT_AS_FORCE", raising=False)
        monkeypatch.setenv("EXECUTOR_RLIMIT_AS_MB", "512")
        fn = er._make_resource_preexec_fn()
        assert fn is not None
        called, spy, resource = _spy_setrlimit()
        with patch.object(resource, "setrlimit", side_effect=spy, autospec=False):
            fn()
        # Darwin 默认：AS 不在被设置列表中，其余四项在
        assert "AS" not in called, "Darwin 默认应跳过 RLIMIT_AS"
        assert "CPU" in called
        assert "NPROC" in called
        assert "FSIZE" in called
        assert "NOFILE" in called

    def test_darwin_force_enables_as(self, monkeypatch):
        """Darwin + EXECUTOR_RLIMIT_AS_FORCE=1 → 强制启用 AS（自担风险）。"""
        monkeypatch.setattr(er, "_IS_DARWIN", True)
        monkeypatch.setenv("EXECUTOR_RLIMIT_AS_FORCE", "1")
        monkeypatch.setenv("EXECUTOR_RLIMIT_AS_MB", "512")
        fn = er._make_resource_preexec_fn()
        assert fn is not None
        called, spy, resource = _spy_setrlimit()
        with patch.object(resource, "setrlimit", side_effect=spy, autospec=False):
            fn()
        assert "AS" in called, "EXECUTOR_RLIMIT_AS_FORCE=1 应强制启用 AS"

    def test_linux_keeps_as_by_default(self, monkeypatch):
        """非 Darwin（Linux 口径）默认 → AS 限制保留（全五项）。"""
        monkeypatch.setattr(er, "_IS_DARWIN", False)
        monkeypatch.delenv("EXECUTOR_RLIMIT_AS_FORCE", raising=False)
        monkeypatch.setenv("EXECUTOR_RLIMIT_AS_MB", "512")
        fn = er._make_resource_preexec_fn()
        assert fn is not None
        called, spy, resource = _spy_setrlimit()
        with patch.object(resource, "setrlimit", side_effect=spy, autospec=False):
            fn()
        assert "AS" in called, "Linux 默认应保留 RLIMIT_AS"


class TestNonPosixNoPreexec:
    """非 POSIX / 无 resource 模块时 _make_resource_preexec_fn 返回 None。"""

    def test_windows_returns_none(self, monkeypatch):
        monkeypatch.setattr(er, "_RLIMIT_AVAILABLE", True)
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        fn = er._make_resource_preexec_fn()
        assert fn is None

    def test_no_rlimit_module_returns_none(self, monkeypatch):
        monkeypatch.setattr(er, "_RLIMIT_AVAILABLE", False)
        fn = er._make_resource_preexec_fn()
        assert fn is None
