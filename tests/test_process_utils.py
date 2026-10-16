"""`run_with_timeout` 测试：超时后**可靠返回**（kill 整进程组 + 有界收口）。

背景（2026-10-09 审查报告 §11.1b 结果十二）：`subprocess.run(timeout=N)` 超时只
kill **直接子进程**，孙进程继承管道写端后 `communicate()` 需等 EOF 才返回 →
**永久阻塞**。实测 QuixBugs 批次因此挂死 30+ 分钟、批次 JSON 从未写出。

本测试用"子进程再 spawn 一个长睡孙进程并继承 stdout"精确复现该机制，
断言 `run_with_timeout` 在超时后**必须返回**。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from src.utils.process_utils import CompletedProcess, nested_pytest_env, run_with_timeout

# 复现脚本：spawn 一个长睡孙进程（继承 stdout/stderr 管道），父进程随即退出。
# subprocess.run(timeout=) 会 kill 父进程，但孙进程仍持有写端 → communicate 挂死。
_GRANDCHILD_SCRIPT = """
import subprocess, sys
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
print("parent done", flush=True)
"""


class TestReturnsOnTimeout:
    """核心契约：超时后保证返回。"""

    def test_grandchild_holding_pipe_does_not_hang(self) -> None:
        """**关键回归锁**：孙进程持有输出写端时仍须立即返回。

        2026-10-10 语义更新（根因级修复后）：
            脚本的**父进程立即正常退出**（打印 "parent done"），挂死只源于
            **管道**——孙进程继承了 stdout 写端，旧实现的 `communicate()`
            要等 EOF，于是即便父进程已退出也永久阻塞。

            新实现改用**临时文件**承接 stdout/stderr，父进程读取不依赖 EOF，
            因此该场景**根本不会触发超时**：`timed_out=False` 且能读到
            "parent done"——这正是修复成功的证据（旧实现会永久阻塞）。
            原断言 `timed_out is True` 编码的是"旧实现必须靠中止才能返回"，
            对文件后端已不适用。

            "父进程自身超时"的场景由 `test_simple_timeout_returns` 与
            `test_grandchild_holding_pipe_with_live_parent_times_out` 覆盖。
        """
        t0 = time.monotonic()
        proc = run_with_timeout(
            [sys.executable, "-c", _GRANDCHILD_SCRIPT],
            timeout=3,
            logger_name="test-grandchild",
        )
        elapsed = time.monotonic() - t0
        # 核心回归锁：必须迅速返回（旧实现在此永久阻塞，孙进程睡眠 300s）
        assert elapsed < 30, f"仍未及时返回：{elapsed:.1f}s"
        # 文件后端下父进程正常退出即可读到其输出——证明输出未被管道阻塞吞掉
        assert "parent done" in proc.stdout, f"未捕获到父进程输出：{proc.stdout!r}"
        assert proc.timed_out is False

    def test_grandchild_holding_pipe_with_live_parent_times_out(self) -> None:
        """父进程自身不退出 + 孙进程持写端：必须超时返回且不挂死。

        这是实跑中真正致命的组合（被测缺陷死循环 + pytest 孙进程持管道）。
        文件后端下即使孙进程存活，父进程超时后 killpg 整树并立即返回。
        """
        script = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
            "print('parent alive', flush=True)\n"
            "while True:\n"
            "    time.sleep(0.5)\n"
        )
        t0 = time.monotonic()
        proc = run_with_timeout(
            [sys.executable, "-c", script],
            timeout=3,
            logger_name="test-grandchild-live-parent",
        )
        elapsed = time.monotonic() - t0
        assert proc.timed_out is True, "父进程未退出 → 必须标记超时"
        assert elapsed < 30, f"超时后仍等待过久：{elapsed:.1f}s"
        assert "parent alive" in proc.stdout, f"超时前输出应被保留：{proc.stdout!r}"

    def test_simple_timeout_returns(self) -> None:
        proc = run_with_timeout(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout=2,
            logger_name="test-simple",
        )
        assert proc.timed_out is True

    def test_no_grandchild_matches_run_semantics(self) -> None:
        """对照组：无孙进程时行为应与 subprocess.run 一致（正常返回、不误标超时）。"""
        proc = run_with_timeout(
            [sys.executable, "-c", "print('hello')"],
            timeout=30,
            logger_name="test-normal",
        )
        assert proc.timed_out is False
        assert proc.returncode == 0
        assert "hello" in (proc.stdout or "")


class TestNormalPath:
    """正常路径：返回值形状与 subprocess.run 兼容。"""

    def test_stdout_stderr_captured(self) -> None:
        proc = run_with_timeout(
            [sys.executable, "-c", "import sys; print('o'); print('e', file=sys.stderr)"],
            timeout=30,
        )
        assert proc.stdout.strip() == "o"
        assert proc.stderr.strip() == "e"

    def test_nonzero_returncode_propagated(self) -> None:
        proc = run_with_timeout([sys.executable, "-c", "raise SystemExit(3)"], timeout=30)
        assert proc.returncode == 3
        assert proc.timed_out is False

    def test_env_and_cwd_honored(self, tmp_path) -> None:
        proc = run_with_timeout(
            [sys.executable, "-c", "import os; print(os.getcwd()); print(os.environ['MARKER'])"],
            timeout=30,
            cwd=str(tmp_path),
            env={**os.environ, "MARKER": "xyz"},
        )
        assert "xyz" in proc.stdout
        assert str(tmp_path) in proc.stdout

    def test_returns_completed_process_type(self) -> None:
        proc = run_with_timeout([sys.executable, "-c", "pass"], timeout=30)
        assert isinstance(proc, subprocess.CompletedProcess)
        assert isinstance(proc, CompletedProcess)


class TestGroupTermination:
    """超时后整棵进程树应被终止（不留孤儿子进程）。"""

    def test_grandchild_is_reaped(self) -> None:
        """killpg 应连带终止孙进程——用一个可探测的标记文件验证。"""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "alive.txt")
            script = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', "
                f"\"import time; time.sleep(8); open({marker!r},'w').write('alive')\"])\n"
                "time.sleep(60)\n"
            )
            proc = run_with_timeout([sys.executable, "-c", script], timeout=2)
            assert proc.timed_out is True
            # 等过孙进程的 8s 睡眠点：若 killpg 生效，标记文件不会出现
            time.sleep(10)
            assert not os.path.exists(marker), "孙进程未被终止（killpg 未生效）"


class TestEdgeCases:
    @pytest.mark.parametrize("timeout", [1, 2])
    def test_various_timeouts(self, timeout: int) -> None:
        proc = run_with_timeout([sys.executable, "-c", "import time; time.sleep(30)"], timeout=timeout)
        assert proc.timed_out is True

    def test_text_mode_disabled(self) -> None:
        proc = run_with_timeout([sys.executable, "-c", "print('bytes')"], timeout=30, text=False)
        assert isinstance(proc.stdout, bytes)

    def test_empty_cmd_label_fallback(self) -> None:
        """空 argv 不应因取 label 而抛异常于日志路径（保守：由 Popen 报错）。"""
        with pytest.raises((IndexError, ValueError, OSError)):
            run_with_timeout([], timeout=1)


# ─── H 轮（2026-10-16）：nested_pytest_env —— 宿主 pytest 配置不得污染嵌套测量 ───

_TRIVIAL_TEST = "def test_ok():\n    assert True\n"


def _run_nested_pytest(tmp_path, env: dict[str, str]) -> int:
    """在 tmp 目录里跑一次最小 pytest，返回 rc（复现 M1/mdo 的嵌套口径）。"""
    test_path = tmp_path / "test_nested.py"
    test_path.write_text(_TRIVIAL_TEST, encoding="utf-8")
    proc = run_with_timeout(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", str(test_path)],
        timeout=120,
        cwd=str(tmp_path),
        text=True,
        env=env,
    )
    assert proc.timed_out is False
    return int(proc.returncode)


class TestNestedPytestEnv:
    def test_host_pytest_keys_are_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PYTEST_PLUGINS", "some_host_plugin")
        monkeypatch.setenv("PYTEST_ADDOPTS", "--color=no")
        env = nested_pytest_env()
        assert "PYTEST_PLUGINS" not in env
        assert "PYTEST_ADDOPTS" not in env

    def test_overrides_win_and_other_env_is_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("PYTHONPATH", "/host/path")
        env = nested_pytest_env(PYTHONPATH="/tmp/nested", PYTHONDONTWRITEBYTECODE="1")
        assert env["PYTHONPATH"] == "/tmp/nested"
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["PATH"] == "/usr/bin"

    def test_clean_env_is_bitwise_identical_to_legacy_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """干净环境下与历史 `{**os.environ, **overrides}` 逐位等价（零行为变化）。"""
        monkeypatch.delenv("PYTEST_PLUGINS", raising=False)
        monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
        overrides = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/tmp/x"}
        assert nested_pytest_env(**overrides) == {**os.environ, **overrides}

    def test_unimportable_host_plugin_breaks_legacy_env_but_not_helper(self, tmp_path, monkeypatch) -> None:
        """端到端复现：宿主插件不可导入 → 旧口径 rc≠0（被测代码根本没跑），新口径 rc=0。

        这正是 specificity_verdict 把"没跑起来"误读成 over_red 的机制。
        """
        monkeypatch.setenv("PYTEST_PLUGINS", "no_such_host_plugin_xyz")
        legacy = _run_nested_pytest(tmp_path, {**os.environ, "PYTHONPATH": str(tmp_path)})
        assert legacy != 0, "前提不成立：宿主 PYTEST_PLUGINS 未能让嵌套 pytest 失败"
        fixed = _run_nested_pytest(tmp_path, nested_pytest_env(PYTHONPATH=str(tmp_path)))
        assert fixed == 0, "剔除宿主 pytest 配置后嵌套运行应正常通过"
