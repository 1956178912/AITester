"""M-3 回归锁（2026-10-17）：`run_with_timeout` 父进程死亡缺口 + 孤儿 pytest 根因修复。

背景（L 轮正式批实测，现场证据见
`experiments/results/orphan_repro_20261017/`）：

    PID 57034 ppid=1 ~98% CPU age 9m42s
    pytest -q --no-header -p no:cacheprovider /var/folders/.../aitester_m1_bitcount_*/python_testcases/test_bitcount.py

现场残留 evidence 显示 M1 判分 tmpdir 与 `run_with_timeout` 文件后端 tmpdir
**同秒出生且都未被 finally 清理** ⇒ 调用进程在超时分支**之前**被外部异常杀死；
`start_new_session=True` 让 pytest 自成会话（killpg 整树终止所需），代价是
**调用方死亡时子进程不被连带回收**（macOS 无 PR_SET_PDEATHSIG 等价物）。

本文件锁定四类行为（零 LLM/零网络、确定性、子进程短命且有界清理）：

1. **复现/证伪**：无保护时"父进程被 SIGKILL"与"外层超时杀中间进程"都会留下
   ppid=1 的孤儿（说明候选 A「超时路径直接 SIGKILL、无 SIGTERM 宽限」不是根因）；
   启用 `orphan_guard=True` 后同一路径下孤儿在秒级被看门狗回收。
2. **SIGTERM 宽限**：先 SIGTERM 再短宽限、仍存活则 SIGKILL；整树终止语义不变。
3. **看门狗契约**：stdout/stderr/rc/cwd/env 透传、`args` 仍为原命令、
   `preexec_fn` 冲突 fail-closed、监督进程/命令两层的进程树形态。
4. **非僵尸进程判定**：被杀后的进程应"消失"而不是仅变为僵尸；僵尸不得被
   当作存活孤儿（否则巡检/回归断言会误报）。
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from src.utils.process_utils import (
    _TERMINATE_GRACE_SECONDS,
    CompletedProcess,
    _resolve_terminate_grace,
    run_with_timeout,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: 每次测试独立的命令行标记（避免并发测试/真实进程互相误杀）。
_TOKEN_PREFIX = "aitester_m3_repro_"

#: 低 CPU 挂死脚本（sleep 循环，不学 bitcount 的 100% 空转）。
_HANG_SCRIPT = "import time\nwhile True:\n    time.sleep(0.2)\n"


# ─────────────────────────── 进程观测工具 ───────────────────────────


def _ps_works() -> bool:
    """ps 不仅存在，而且当前进程真的能读进程表（A-09，2026-10-18 独立评审）。

    实测：某些沙箱/容器宿主 `ps` 二进制存在但执行即
    `PermissionError: [Errno 1] Operation not permitted`（WorkBuddy 沙箱、
    受限 CI 镜像）。此时孤儿/僵尸观测类用例无法判定——属环境能力缺失而非
    代码缺陷，按项目既有 skipif 降级惯例（与缺可选依赖时 importorskip 同
    口径）显式 skip，不得以 fail 冒充"回归"。
    """
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,stat=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


_PS_OK = _ps_works()
_PS_SKIP_REASON = "宿主环境禁止 ps 读取进程表（沙箱/容器限制），孤儿观测用例无法判定——非代码缺陷（A-09）"


def _token(name: str) -> str:
    """生成进程唯一标记（pid+微秒，保证并发测试之间不串）。"""
    return f"{_TOKEN_PREFIX}{name}_{os.getpid()}_{int(time.time() * 1_000_000) % 1_000_000}"


def _ps_rows() -> list[dict[str, Any]]:
    """读取进程表（pid/ppid/stat/command；stat 用于僵尸判定）。"""
    proc = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,stat=,command="],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows.append({"pid": pid, "ppid": ppid, "stat": parts[2], "command": parts[3]})
    return rows


def _token_rows(token: str) -> list[dict[str, Any]]:
    """命令行命中本测试标记的全部进程（含看门狗层与命令层）。"""
    return [row for row in _ps_rows() if token in row["command"]]


def _is_zombie(stat: str) -> bool:
    """ps 的 stat 字段是否僵尸（Z 开头）。"""
    return bool(stat) and stat.upper().startswith("Z")


def _pid_stat(pid: int) -> str | None:
    """读取单进程的 ps stat 字段（进程不存在返回 None）。

    macOS 上僵尸进程的 command 会被改写为 `<defunct>`（标记丢失），
    故"是否僵尸"必须按 pid 查 stat，而不能靠命令行标记扫描。
    """
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    text = (proc.stdout or "").strip()
    return text.split()[0] if text else None


def _live_token_rows(token: str) -> list[dict[str, Any]]:
    """存活（非僵尸）的标记进程——僵尸不占 CPU、不构成泄漏。"""
    return [row for row in _token_rows(token) if not _is_zombie(row["stat"])]


def _wait_until(predicate: Any, timeout: float, interval: float = 0.1) -> bool:
    """轮询 predicate 直到为真或超时（返回是否命中）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def _kill_token_procs(token: str) -> None:
    """兜底清理：对本测试标记命中的进程 SIGKILL（仅**会话/进程组组长**才 killpg）。

    绝不能对所有命中进程 killpg：父进程/中间进程本身可能是 pytest 的同组子进程，
    对其 killpg 会误杀测试进程自己（组号 = 继承来的 pytest 进程组）。
    看门狗/孤儿 pytest 是 start_new_session 的组长（pgid == pid），killpg 才安全。
    """
    for row in _token_rows(token):
        pid = row["pid"]
        try:
            pgid = os.getpgid(pid)
        except OSError:
            continue
        if pgid == pid:  # 会话/进程组组长：整组回收（含未带标记的孙进程）
            with contextlib.suppress(OSError):
                os.killpg(pgid, signal.SIGKILL)
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)


# ─────────────────────────── 1. 复现 / 证伪 ───────────────────────────


def _parent_script(*, guard: bool) -> str:
    """构造"父进程"脚本：内部用 run_with_timeout 起一个挂死子进程（可开关看门狗）。

    标记 token 经**环境变量** `M3_TOKEN` 传入、不写进脚本文本——否则"父进程"自身
    命令行会含标记，观测/清理时与子进程混淆（父进程继承 pytest 进程组，
    误 killpg 会杀掉测试进程自己）。
    """
    return (
        "import os, sys\n"
        "from src.utils.process_utils import run_with_timeout\n"
        "token = os.environ['M3_TOKEN']\n"
        f"child = [sys.executable, '-c', {_HANG_SCRIPT!r}, token]\n"
        "run_with_timeout(child, timeout=120, "
        f"orphan_guard={guard!r}, logger_name=token)\n"
    )


def _spawn_parent(script: str, token: str) -> subprocess.Popen[str]:
    """以独立子进程运行"父进程"脚本（cwd=仓库根；PYTHONPATH 可 import src.*）。"""
    return subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(_REPO_ROOT), "M3_TOKEN": token},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.mark.skipif(not _PS_OK, reason=_PS_SKIP_REASON)
class TestParentDeathGap:
    """父进程死亡缺口的复现与修复锁（真子进程，短命、finally 清理）。"""

    def test_sigkill_parent_leaves_orphan_without_guard(self) -> None:
        """**复现**：无保护时父进程被 SIGKILL → 子进程被 init 收养（ppid=1）仍存活。

        这正是 L 轮 PID 57034 的机制（也是"候选 A 不是根因"的证据：
        父进程死在超时分支之前，超时路径的 SIGTERM/SIGKILL 根本不会执行）。
        """
        token = _token("noguard")
        parent = _spawn_parent(_parent_script(guard=False), token)
        try:
            assert _wait_until(lambda: len(_live_token_rows(token)) >= 1, timeout=20), (
                "复现前提不成立：子进程未在 20s 内启动"
            )
            child = _live_token_rows(token)[0]
            assert child["ppid"] == parent.pid
            os.kill(parent.pid, signal.SIGKILL)
            parent.wait(timeout=10)
            assert _wait_until(lambda: any(row["ppid"] == 1 for row in _live_token_rows(token)), timeout=5), (
                "预期子进程被 init 收养（ppid=1）——若无保护却未复现，说明机制已变，需重审修复口径"
            )
        finally:
            _kill_token_procs(token)
            with contextlib.suppress(OSError):
                parent.kill()
            parent.wait(timeout=10)

    def test_sigkill_parent_is_reaped_by_orphan_guard(self) -> None:
        """**修复锁**：orphan_guard=True 时父进程被 SIGKILL → 看门狗秒级回收命令进程组。"""
        token = _token("guard")
        parent = _spawn_parent(_parent_script(guard=True), token)
        try:
            assert _wait_until(lambda: len(_live_token_rows(token)) >= 2, timeout=20), (
                "复现前提不成立：看门狗 + 命令两层进程未在 20s 内出现"
            )
            os.kill(parent.pid, signal.SIGKILL)
            parent.wait(timeout=10)
            assert _wait_until(lambda: not _live_token_rows(token), timeout=5), (
                f"看门狗未回收子进程：{_live_token_rows(token)}"
            )
        finally:
            _kill_token_procs(token)
            with contextlib.suppress(OSError):
                parent.kill()
            parent.wait(timeout=10)

    def test_outer_timeout_without_guard_leaves_nested_orphan(self) -> None:
        """**证伪候选 A**：A（外层）超时 killpg 杀死中间进程 B 时，
        B 用 `start_new_session` 起的 C 不在 A 的 killpg 覆盖面内 → C 成孤儿。
        即"超时路径直接 SIGKILL 无宽限"不是 L 轮事件根因（事件里超时分支根本没执行）。
        """
        token = _token("outer_noguard")
        middle = _parent_script(guard=False)
        outer = run_with_timeout(
            [sys.executable, "-c", middle],
            timeout=1.5,
            env={**os.environ, "M3_TOKEN": token},
            logger_name="m3-outer",
        )
        try:
            assert outer.timed_out is True
            assert _wait_until(lambda: any(row["ppid"] == 1 for row in _live_token_rows(token)), timeout=5), (
                "预期外层超时后嵌套子进程成为孤儿（无保护路径）"
            )
        finally:
            _kill_token_procs(token)

    def test_outer_timeout_reaps_nested_with_guard(self) -> None:
        """**修复锁**：中间进程 B 被外层超时杀死后，B 起命令的看门狗感知父死亡并回收。"""
        token = _token("outer_guard")
        middle = _parent_script(guard=True)
        outer = run_with_timeout(
            [sys.executable, "-c", middle],
            timeout=1.5,
            env={**os.environ, "M3_TOKEN": token},
            logger_name="m3-outer-guard",
        )
        try:
            assert outer.timed_out is True
            assert _wait_until(lambda: not _live_token_rows(token), timeout=6), (
                f"外层超时后仍残留嵌套进程：{_live_token_rows(token)}"
            )
        finally:
            _kill_token_procs(token)


# ─────────────────────────── 2. SIGTERM 宽限 ───────────────────────────


class TestSigtermGrace:
    """超时路径：SIGTERM 宽限（可配）→ 仍存活才 SIGKILL；整树终止语义不变。"""

    def test_responsive_child_exits_within_grace(self) -> None:
        """可响应 SIGTERM 的子进程应在 grace 内退出（不白等满宽限）。"""
        script = (
            "import signal, sys, time\n"
            "signal.signal(signal.SIGTERM, lambda *a: sys.exit(7))\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n"
        )
        t0 = time.monotonic()
        res = run_with_timeout(
            [sys.executable, "-c", script], timeout=0.5, terminate_grace=2.0, logger_name="m3-grace-fast"
        )
        elapsed = time.monotonic() - t0
        assert res.timed_out is True
        assert "ready" in (res.stdout or ""), "超时前输出应保留（文件后端）"
        assert elapsed < 0.5 + 1.2, f"响应 SIGTERM 的进程未被宽限内回收：{elapsed:.2f}s"

    def test_stubborn_child_is_sigkilled_after_grace(self) -> None:
        """忽略 SIGTERM 的子进程 → 宽限结束后必须被 SIGKILL（整树终止语义不变）。"""
        script = "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(60)\n"
        t0 = time.monotonic()
        res = run_with_timeout(
            [sys.executable, "-c", script], timeout=0.5, terminate_grace=0.4, logger_name="m3-grace-slow"
        )
        elapsed = time.monotonic() - t0
        assert res.timed_out is True
        assert res.returncode == -9
        assert elapsed >= 0.5 + 0.4 - 0.05, f"忽略 SIGTERM 时未等满宽限：{elapsed:.2f}s"
        assert elapsed < 0.5 + 0.4 + 2.5, f"两段式终止耗时异常：{elapsed:.2f}s"

    def test_zero_grace_keeps_historic_fast_semantics(self) -> None:
        """grace=0 → 等价历史口径（立即 SIGKILL），并仍然保证返回。"""
        t0 = time.monotonic()
        res = run_with_timeout([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.4, terminate_grace=0)
        elapsed = time.monotonic() - t0
        assert res.timed_out is True
        assert elapsed < 0.4 + 1.5, f"grace=0 时不应有额外等待：{elapsed:.2f}s"

    def test_grace_sweeps_grandchildren_in_group(self) -> None:
        """组内孙进程（同会话）也须被两段式终止清扫（killpg 整树语义保留）。"""
        marker = os.path.join(str(_REPO_ROOT), f".m3_grandchild_{os.getpid()}.marker")
        with contextlib.suppress(OSError):
            os.unlink(marker)
        script = (
            "import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', "
            f"\"import time; time.sleep(3); open({marker!r}, 'w').write('alive')\"])\n"
            "time.sleep(60)\n"
        )
        try:
            res = run_with_timeout([sys.executable, "-c", script], timeout=0.5, terminate_grace=0.3)
            assert res.timed_out is True
            # 等过孙进程的 3s 睡眠点：整树终止生效则标记文件不会出现
            assert _wait_until(lambda: not os.path.exists(marker), timeout=4.5)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(marker)


# ─────────────────────────── 3. 看门狗契约 ───────────────────────────


class TestOrphanGuardContract:
    """orphan_guard 的透明性：语义与历史 `subprocess.run` 兼容面一致。"""

    def test_guard_propagates_stdout_stderr_returncode(self) -> None:
        script = "import sys\nprint('out')\nprint('err', file=sys.stderr)\nraise SystemExit(3)\n"
        res = run_with_timeout([sys.executable, "-c", script], timeout=30, orphan_guard=True)
        assert res.timed_out is False
        assert res.returncode == 3
        assert res.stdout.strip() == "out"
        assert res.stderr.strip() == "err"

    def test_guard_preserves_cwd_env_and_text_mode(self, tmp_path: Path) -> None:
        res = run_with_timeout(
            [sys.executable, "-c", "import os; print(os.getcwd()); print(os.environ['M3_MARKER'])"],
            timeout=30,
            cwd=str(tmp_path),
            env={**os.environ, "M3_MARKER": "xyz"},
            orphan_guard=True,
        )
        assert str(tmp_path) in res.stdout
        assert "xyz" in res.stdout

    def test_guard_args_is_original_command(self) -> None:
        """看门狗是内部实现，`CompletedProcess.args` 必须仍是**原命令**（可审计）。"""
        cmd = [sys.executable, "-c", "print('ok')"]
        res = run_with_timeout(cmd, timeout=30, orphan_guard=True)
        assert list(res.args) == cmd

    def test_guard_rejects_preexec_fn_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="orphan_guard"):
            run_with_timeout([sys.executable, "-c", "pass"], timeout=30, orphan_guard=True, preexec_fn=lambda: None)

    def test_guard_exit_code_from_signal_is_normalized(self) -> None:
        """命令被信号杀死时归一为 128+signum（异常退出可被 >=2 判据识别，不静默成 0）。"""
        res = run_with_timeout(
            [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"], timeout=30
        )
        assert res.returncode == -9, "无 guard 时保持历史口径（信号退出码为负）"
        guarded = run_with_timeout(
            [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"],
            timeout=30,
            orphan_guard=True,
        )
        assert guarded.returncode == 128 + 9, f"guard 下信号退出应归一为 128+n，实际 {guarded.returncode}"

    @pytest.mark.skipif(not _PS_OK, reason=_PS_SKIP_REASON)
    def test_guard_timeout_still_returns_and_kills_tree(self) -> None:
        """看门狗不改变超时语义：timed_out=True、rc=-9、整树回收、及时返回。"""
        token = _token("guard_timeout")
        t0 = time.monotonic()
        res = run_with_timeout(
            [sys.executable, "-c", _HANG_SCRIPT, token], timeout=0.5, orphan_guard=True, terminate_grace=0.1
        )
        elapsed = time.monotonic() - t0
        assert res.timed_out is True and res.returncode == -9
        assert elapsed < 0.5 + 2.5, f"guard 超时返回过慢：{elapsed:.2f}s"
        assert _wait_until(lambda: not _live_token_rows(token), timeout=4), "看门狗超时后残留进程"

    @pytest.mark.skipif(not _PS_OK, reason=_PS_SKIP_REASON)
    def test_guard_two_process_layer_shape(self) -> None:
        """进程树形态锁定：父→看门狗（新会话组长）→命令；命令与看门狗同进程组。"""
        token = _token("shape")
        script = (
            "import os, sys\n"
            "from src.utils.process_utils import run_with_timeout\n"
            "run_with_timeout([sys.executable, '-c', 'import time; time.sleep(3)', os.environ['M3_TOKEN']], "
            "timeout=30, orphan_guard=True)\n"
        )
        parent = _spawn_parent(script, token)
        try:
            assert _wait_until(lambda: len(_live_token_rows(token)) >= 2, timeout=20)
            rows = _live_token_rows(token)
            pids = {row["pid"] for row in rows}
            top = [row for row in rows if row["ppid"] not in pids]
            assert len(top) == 1 and top[0]["ppid"] == parent.pid, f"看门狗层形态异常：{rows}"
            watcher = top[0]
            child = next(row for row in rows if row["ppid"] == watcher["pid"])
            # 同进程组 = 超时 killpg 能一次回收两层
            assert os.getpgid(child["pid"]) == os.getpgid(watcher["pid"])
        finally:
            _kill_token_procs(token)
            with contextlib.suppress(OSError):
                parent.kill()
            parent.wait(timeout=10)


# ─────────────────────────── 4. 非僵尸进程判定 ───────────────────────────


@pytest.mark.skipif(not _PS_OK, reason=_PS_SKIP_REASON)
class TestNonZombieJudgement:
    """ "已被回收"不得被僵尸进程伪装：僵尸不占 CPU、不算存活孤儿。"""

    def test_zombie_is_not_counted_as_live(self) -> None:
        """未 wait 的已退出子进程是僵尸——巡检/回归断言必须把它与"存活"区分。

        macOS 上僵尸 command 被改写为 `<defunct>`（命令行标记消失），因此
        "是否僵尸"必须按 pid 查 stat；本测试锁定 `_is_zombie` 与"僵尸不算存活"
        的口径（`_live_token_rows` 只统计非僵尸的标记进程）。
        """
        token = _token("zombie")
        zombie = subprocess.Popen([sys.executable, "-c", "pass", token], stdout=subprocess.DEVNULL)
        try:
            assert _wait_until(lambda: _is_zombie(_pid_stat(zombie.pid) or ""), timeout=5), (
                "前提不成立：未 wait 的子进程未进入僵尸态"
            )
            assert _live_token_rows(token) == [], "僵尸进程不得被判定为存活"
        finally:
            with contextlib.suppress(OSError):
                zombie.wait(timeout=5)

    def test_killed_orphan_disappears_not_just_zombifies(self) -> None:
        """回收断言必须检查"非僵尸且不存在"：killpg 后进程应被真正回收。"""
        token = _token("reaped")
        child = subprocess.Popen(
            [sys.executable, "-c", _HANG_SCRIPT, token],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
        )
        try:
            assert _wait_until(lambda: len(_live_token_rows(token)) >= 1, timeout=10)
            os.killpg(os.getpgid(child.pid), signal.SIGKILL)
            assert _wait_until(lambda: not _live_token_rows(token), timeout=5)
            # 直系子进程在本测试内尚未 wait → 允许僵尸，但 stat 必须已是 Z 或进程已不存在
            stat = _pid_stat(child.pid)
            assert stat is None or _is_zombie(stat), f"killpg 后直系子进程仍非僵尸存活：stat={stat}"
        finally:
            with contextlib.suppress(OSError):
                child.wait(timeout=5)


# ─────────────────────────── 5. 参数归一 + 接线锁 ───────────────────────────


class TestGraceNormalization:
    def test_none_defaults_to_module_constant(self) -> None:
        assert _resolve_terminate_grace(None) == _TERMINATE_GRACE_SECONDS

    @pytest.mark.parametrize(("raw", "expected"), [(-1.0, 0.0), (0.0, 0.0), (1.5, 1.5), (99.0, 10.0)])
    def test_clamped_to_safe_range(self, raw: float, expected: float) -> None:
        assert _resolve_terminate_grace(raw) == expected


class TestM1Wiring:
    """接线锁：M1 嵌套 pytest 必须启用 orphan_guard（L 轮泄漏点）。"""

    def test_m1_run_pytest_in_tmp_passes_orphan_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from experiments import _m1_metrics

        captured: dict[str, Any] = {}

        def _fake_run(cmd: list[str], **kwargs: Any) -> CompletedProcess:
            captured["cmd"] = cmd
            captured.update(kwargs)
            return CompletedProcess(cmd, 0, stdout="", stderr="", timed_out=False)

        monkeypatch.setattr("src.utils.process_utils.run_with_timeout", _fake_run)
        rc = _m1_metrics._run_pytest_in_tmp("def test_ok():\n    assert True\n", "def f():\n    return 1\n", "m3mod")
        assert rc is not None and rc[0] == 0
        assert captured.get("orphan_guard") is True, "M1 嵌套 pytest 未启用父死亡看门狗（L 轮孤儿复发风险）"
