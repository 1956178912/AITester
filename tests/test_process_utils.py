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

from src.utils.process_utils import CompletedProcess, run_with_timeout

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
        """**关键回归锁**：孙进程持有管道时仍须在超时后返回。"""
        t0 = time.monotonic()
        proc = run_with_timeout(
            [sys.executable, "-c", _GRANDCHILD_SCRIPT],
            timeout=3,
            logger_name="test-grandchild",
        )
        elapsed = time.monotonic() - t0
        assert proc.timed_out is True, "必须标记超时"
        # 必须显著早于孙进程的 300s 睡眠返回（留足收口宽限 5s + 余量）
        assert elapsed < 60, f"超时后仍等待过久：{elapsed:.1f}s"
        # 注：父进程可能在到期前已正常退出（returncode=0），但孙进程仍持有
        # 管道 → 这正是挂死场景；本函数必须仍能返回，故此处不断言 returncode。

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
