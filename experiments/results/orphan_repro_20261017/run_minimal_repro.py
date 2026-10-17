#!/usr/bin/env python3
"""M-3 最小复现：`run_with_timeout` 调用方被外部 SIGKILL 后嵌套 pytest 变孤儿（ppid=1）。

背景（L 轮 2026-10-17 正式批实测 + 现场残留证据）
--------------------------------------------------
L 轮批次期发现 PID 57034 的孤儿进程：`pytest -q --no-header -p no:cacheprovider
/var/folders/.../T/aitester_m1_bitcount_*/python_testcases/test_bitcount.py`，
ppid=1、~98% CPU、age 9m42s。现场残留证据（本目录 `evidence_l_batch_leftovers.log`）：

- `aitester_m1_bitcount_07q05sj_`（M1 判分 tmpdir）birth = 2026-10-17 18:36:02；
- 同秒 birth 的 `aitester_proc__v8n618p`（`run_with_timeout` 文件后端 tmpdir），
  其 stdout 在 18:36:03 写出 1 个 "."（pytest 已启动并跑过 1 条测试）；
- 两个 tmpdir 的 `finally` 清理**都没有执行** ⇒ 调用进程在超时分支之前被**外部异常杀死**；
- M1 判分 tmpdir 的 pytest 子进程因 `start_new_session=True` 自成会话，
  父进程死亡时不会随父进程组被回收 → 被 init 收养继续运行。

结论（本脚本用最小可控实验证实/证伪候选机制）
----------------------------------------------
- 候选 A（"超时路径直接 SIGKILL 进程组、无 SIGTERM 宽限"）**不是**本事件根因：
  本事件里超时分支从未执行（tmpdir 残留为证）；且 SIGTERM 宽限只作用于仍存活的
  调用方，对"调用方被外部 SIGKILL"无任何作用。
- 真根因 = **父进程死亡缺口**：`run_with_timeout` 用 `start_new_session=True` 让
  子进程自成会话（为整树 killpg 服务），代价是**调用方进程被外部杀死时子进程不会
  被连带回收**（macOS 无 PR_SET_PDEATHSIG 等价物）→ 嵌套 pytest 变 ppid=1 孤儿。

场景与预期
----------
S1 父进程被 SIGKILL（L 批现场签名；用真实生产入口 `_run_pytest_in_tmp`）：
   pre-fix = 嵌套 pytest 以 ppid=1 存活（复现）；post-fix = 1s 内被看门狗回收。
S2 A→B→C 外层 run_with_timeout 超时（任务书骨架）：
   pre-fix = C（嵌套 pytest）被 init 收养存活；post-fix = 无孤儿。
S3 SIGTERM 宽限（仅 post-fix 参数存在时跑）：忽略 SIGTERM 的子进程在 grace 后
   被 SIGKILL（timed_out=True、耗时等于 timeout+grace 量级）；响应 SIGTERM 的
   子进程在 grace 内退出（耗时接近 timeout）。
S4 子进程自建新会话（残余风险边界）：孙进程 `start_new_session=True` 时，
   killpg/SIGTERM 宽限都无法触达 → 仍会残留（证明候选 A 的覆盖面边界；
   生产 M1 链路的 pytest 不进入该形态，看门狗覆盖"调用方死亡"这一真实缺口）。

用法（避免高 CPU；可 nice -n 15 运行）::

    nice -n 15 .venv/bin/python experiments/results/orphan_repro_20261017/run_minimal_repro.py \
        --out experiments/results/orphan_repro_20261017/repro_before.json | tee repro_before.log
"""

from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.process_utils import run_with_timeout  # noqa: E402

#: 本复现全部子进程命令行里都带该标记——用于 `ps` 定位与兜底清理（绝不误杀无关进程）。
MARKER = "aitester_m1_orphanrepro_"
#: 挂死测试（低 CPU：sleep 循环，不学 bitcount 的 100% 空转，避免干扰跑批窗口）。
_HANG_TEST = "import time\n\ndef test_hang_forever():\n    while True:\n        time.sleep(0.2)\n"
#: 生产入口 `_run_pytest_in_tmp` 的模块名（进入 tmpdir 前缀 aitester_m1_orphanrepro_）。
_MODULE = "orphanrepro"
_TARGET = "def f():\n    return 1\n"

_FEATURE_PARAMS = inspect.signature(run_with_timeout).parameters
_HAS_ORPHAN_GUARD = "orphan_guard" in _FEATURE_PARAMS
_HAS_TERMINATE_GRACE = "terminate_grace" in _FEATURE_PARAMS


# ─────────────────────────── ps 观测工具 ───────────────────────────


def _ps_rows() -> list[dict[str, Any]]:
    """读取进程表（pid/ppid/etime/command），用于观测进程树和孤儿。"""
    proc = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,etime=,command="],
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
        rows.append({"pid": pid, "ppid": ppid, "etime": parts[2], "command": parts[3]})
    return rows


def _marker_procs() -> list[dict[str, Any]]:
    """命中复现标记的全部进程（含 pytest 与看门狗；用命令行标记识别，避免误杀）。"""
    return [row for row in _ps_rows() if MARKER in row["command"]]


def _pytest_procs() -> list[dict[str, Any]]:
    """命中标记的 pytest 形态进程（命令行含 `-m pytest` 或可执行名 pytest）。"""
    return [row for row in _marker_procs() if "pytest" in row["command"]]


def _kill_marker_procs() -> list[int]:
    """兜底清理：对本复现标记命中的全部进程先 SIGTERM 再 SIGKILL（含进程组）。"""
    pids = sorted({row["pid"] for row in _marker_procs()})
    for pid in pids:
        with _suppress_oserror():
            os.kill(pid, signal.SIGTERM)
    time.sleep(0.2)
    for pid in pids:
        with _suppress_oserror():
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        with _suppress_oserror():
            os.kill(pid, signal.SIGKILL)
    return pids


class _suppress_oserror:  # noqa: N801 - 上下文管理器小写风格与 contextlib.suppress 对齐
    """吞掉 OS 级竞态异常（进程已退出/无权限），仅供复现脚本兜底清理使用。"""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, OSError)


def _tmpdir_snapshot() -> dict[str, float]:
    """Temp 目录下 aitester 前缀目录快照（路径 → mtime；观测 cleanup 是否执行）。"""
    root = tempfile.gettempdir()
    snapshot: dict[str, float] = {}
    for path in glob.glob(os.path.join(root, "aitester_*")):
        if os.path.isdir(path):
            try:
                snapshot[path] = os.stat(path).st_mtime
            except OSError:
                continue
    return snapshot


def _own_leftover_tmpdirs(before: set[str], after: dict[str, float]) -> list[str]:
    """从窗口内新增目录中挑出**本复现自身**的（m1 前缀含标记 + 同秒的 proc dir）。

    避免把并发进程（跑批/其他测试）新建的 aitester_* 目录误记为本复现痕迹。
    """
    own_m1 = [path for path in after if path not in before and MARKER in os.path.basename(path)]
    own_m1_mtimes = [after[path] for path in own_m1]
    own_proc = [
        path
        for path in after
        if path not in before
        and os.path.basename(path).startswith("aitester_proc_")
        and any(abs(after[path] - mtime) <= 3.0 for mtime in own_m1_mtimes)
    ]
    return sorted(own_m1 + own_proc)


def _clean_own_tmpdirs(paths: list[str]) -> None:
    """清理本复现自身的残留 tmpdir（父进程被杀 → 其 finally 未执行，属预期残留）。"""
    import shutil

    for path in paths:
        shutil.rmtree(path, ignore_errors=True)




def _wait_for(predicate: Any, timeout: float, interval: float = 0.1) -> bool:
    """轮询 predicate 直到为真或超时（返回是否命中）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ─────────────────────────── 场景 1 / 2：父进程死亡 ───────────────────────────


def _parent_script() -> str:
    """"被外部杀死的调用方"脚本：走真实生产入口 `_run_pytest_in_tmp` 挂死。"""
    return (
        "import sys\n"
        "from experiments._m1_metrics import _run_pytest_in_tmp\n"
        f"HANG = {_HANG_TEST!r}\n"
        f"_run_pytest_in_tmp(HANG, {_TARGET!r}, {_MODULE!r}, timeout=600)\n"
    )


def _child_env() -> dict[str, str]:
    """子进程环境：保证可 import `experiments.*`（含 PYTHONPATH=仓库根）。"""
    return {**os.environ, "PYTHONPATH": str(_REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}


def _record_tree(label: str, parent_pid: int) -> list[dict[str, Any]]:
    """打印并返回与 parent_pid 相关的标记进程树快照。"""
    rows = _marker_procs()
    print(f"  [{label}] marker 进程 {len(rows)} 个：")
    for row in rows:
        rel = "child-of-parent" if row["ppid"] == parent_pid else f"ppid={row['ppid']}"
        print(f"    pid={row['pid']} ppid={row['ppid']} etime={row['etime']} ({rel}) {row['command'][:120]}")
    return rows


def scenario_s1_parent_killed() -> dict[str, Any]:
    """S1：调用方（父进程）被 SIGKILL —— L 轮现场签名的最小复现。"""
    print("\n== S1：父进程外部 SIGKILL（真实入口 _run_pytest_in_tmp；pre-fix 预期复现孤儿）")
    tmp_before = set(_tmpdir_snapshot())
    parent = subprocess.Popen(
        [sys.executable, "-c", _parent_script()],
        cwd=str(_REPO_ROOT),
        env=_child_env(),
        start_new_session=True,
    )
    try:
        started = _wait_for(lambda: bool(_pytest_procs()), timeout=30)
        if not started:
            return {"scenario": "S1", "error": "嵌套 pytest 未在 30s 内启动（复现前提不成立）"}
        rows = _record_tree("kill 前", parent.pid)
        pytest_rows = _pytest_procs()
        # 关键动作：只 kill 父进程（模拟 harness/人工 kill -9），不 kill 其进程组
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=10)
        print(f"  已对调用方 pid={parent.pid} 发送 SIGKILL；观测嵌套 pytest 是否被 init 收养…")
        survivors: list[dict[str, Any]] = []
        for _ in range(8):
            time.sleep(0.25)
            current = _pytest_procs()
            if current:
                survivors = current
            elif survivors:
                # 曾观测到存活、随后消失 → 有看门狗在父死后回收（post-fix 时序证据）
                break
        print(f"  父进程死后：存活 pytest {len(survivors)} 个 {[r['pid'] for r in survivors]}")
        # 归属判别：临时目录快照会把**并发进程正在使用的临时目录**也算进来，
        # 故要求候选目录在 1.2s 后仍存在（父进程死亡 ⇒ 其 finally 永不执行 ⇒ 残留）。
        snapshot_after = _tmpdir_snapshot()
        time.sleep(1.2)
        persistent = set(_tmpdir_snapshot())
        leftovers = _own_leftover_tmpdirs(
            tmp_before, {path: mtime for path, mtime in snapshot_after.items() if path in persistent}
        )
        leaked = bool(survivors)
        if leaked:
            print(f"  复现成功（pre-fix 预期）：孤儿 pytest 存活且 ppid={survivors[0]['ppid']}：")
            for row in survivors:
                print(f"    pid={row['pid']} ppid={row['ppid']} etime={row['etime']} {row['command'][:140]}")
        else:
            print("  未观测到孤儿：嵌套 pytest 已被回收（post-fix 预期）")
        print(f"  新增 aitester_* tmp 目录（cleanup 未执行 = 父进程异常死亡的直接痕迹）：{len(leftovers)} 个")
        for path in leftovers:
            print(f"    {path}")
        _clean_own_tmpdirs(leftovers)
        return {
            "scenario": "S1",
            "parent_pid": parent.pid,
            "pytest_before_kill": [{"pid": r["pid"], "ppid": r["ppid"]} for r in pytest_rows],
            "leaked": leaked,
            "survivors": [{"pid": r["pid"], "ppid": r["ppid"], "etime": r["etime"]} for r in survivors],
            "leftover_tmpdirs": leftovers,
        }
    finally:
        _kill_marker_procs()


def scenario_s2_outer_timeout() -> dict[str, Any]:
    """S2：A（外层 run_with_timeout）超时 kill 中间进程 B，观测嵌套 pytest C。"""
    print("\n== S2：A→B→C 外层超时（任务书骨架；pre-fix 预期 C 被 init 收养）")
    res = run_with_timeout(
        [sys.executable, "-c", _parent_script()],
        timeout=2,
        cwd=str(_REPO_ROOT),
        env=_child_env(),
        logger_name="repro-outer",
    )
    print(f"  外层返回：timed_out={res.timed_out} returncode={res.returncode}")
    survivors: list[dict[str, Any]] = []
    for _ in range(10):
        time.sleep(0.25)
        current = _pytest_procs()
        if current:
            survivors = current
        elif survivors:
            break
    print(f"  外层超时后：存活 pytest {len(survivors)} 个 {[r['pid'] for r in survivors]}")
    leaked = bool(survivors)
    if leaked:
        print(f"  复现成功（pre-fix 预期）：C 存活且 ppid={survivors[0]['ppid']}")
    else:
        print("  未观测到孤儿（post-fix 预期：中间进程死亡被看门狗感知）")
    return {
        "scenario": "S2",
        "outer_timed_out": bool(res.timed_out),
        "outer_returncode": res.returncode,
        "leaked": leaked,
        "survivors": [{"pid": r["pid"], "ppid": r["ppid"]} for r in survivors],
    }


# ─────────────────────────── 场景 3：SIGTERM 宽限 ───────────────────────────


def scenario_s3_terminate_grace() -> dict[str, Any]:
    """S3：SIGTERM 先给、grace 后 SIGKILL（仅 post-fix 支持 terminate_grace 时跑）。"""
    print("\n== S3：SIGTERM 宽限（pre-fix 无此参数 → 跳过；post-fix 预期两段式终止）")
    if not _HAS_TERMINATE_GRACE:
        print("  当前 run_with_timeout 无 terminate_grace 参数（pre-fix）——跳过")
        return {"scenario": "S3", "supported": False}
    # 3a：忽略 SIGTERM 的子进程 → 必须 grace 后 SIGKILL
    stubborn = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('repro-stubborn-ready', flush=True)\n"
        "time.sleep(600)\n"
    )
    t0 = time.monotonic()
    res_a = run_with_timeout(
        [sys.executable, "-c", stubborn],
        timeout=1.0,
        terminate_grace=0.4,
        logger_name="repro-s3a",
    )
    elapsed_a = round(time.monotonic() - t0, 3)
    print(f"  3a 忽略 SIGTERM：timed_out={res_a.timed_out} elapsed={elapsed_a}s（预期 ≥1.0 且 <2.5）")
    # 3b：响应 SIGTERM 的子进程 → grace 内退出，不该等满 grace
    graceful = (
        "import signal, sys\n"
        "signal.signal(signal.SIGTERM, lambda *a: sys.exit(7))\n"
        "print('repro-graceful-ready', flush=True)\n"
        "import time\n"
        "time.sleep(600)\n"
    )
    t0 = time.monotonic()
    res_b = run_with_timeout(
        [sys.executable, "-c", graceful],
        timeout=1.0,
        terminate_grace=1.0,
        logger_name="repro-s3b",
    )
    elapsed_b = round(time.monotonic() - t0, 3)
    print(f"  3b 响应 SIGTERM：timed_out={res_b.timed_out} elapsed={elapsed_b}s（预期 ≈1.0，远小于 1.0+1.0）")
    return {
        "scenario": "S3",
        "supported": True,
        "stubborn": {"timed_out": bool(res_a.timed_out), "elapsed_s": elapsed_a},
        "graceful": {"timed_out": bool(res_b.timed_out), "elapsed_s": elapsed_b},
    }


# ─────────────────────────── 场景 4：自建会话边界 ───────────────────────────


def scenario_s4_self_session_descendant() -> dict[str, Any]:
    """S4：孙进程自建新会话 → 进程组信号触达不到（残余风险边界，非回归）。"""

    print("\n== S4：子进程自建新会话（残余风险边界：killpg/SIGTERM 宽限都覆盖不到）")
    escaped_argv = [sys.executable, "-c", "import time; time.sleep(600)", MARKER + "escaped"]
    script = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen({escaped_argv!r}, start_new_session=True)\n"
        "print('repro-self-session-ready', flush=True)\n"
        "time.sleep(600)\n"
    )
    res = run_with_timeout([sys.executable, "-c", script], timeout=1.0, logger_name="repro-s4")
    time.sleep(0.3)
    escaped = [row for row in _marker_procs() if MARKER + "escaped" in row["command"]]
    print(f"  外层 timed_out={res.timed_out}；自建会话孙进程存活 {len(escaped)} 个（预期 1 = 已知边界）")
    for row in escaped:
        print(f"    pid={row['pid']} ppid={row['ppid']} {row['command'][:120]}")
    return {
        "scenario": "S4",
        "outer_timed_out": bool(res.timed_out),
        "escaped_alive": len(escaped),
        "escaped": [{"pid": r["pid"], "ppid": r["ppid"]} for r in escaped],
    }


# ─────────────────────────── 主入口 ───────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M-3 孤儿 pytest 最小复现（无 LLM、低 CPU）")
    parser.add_argument("--out", default=None, help="JSON 结果输出路径（缺省仅打印）")
    parser.add_argument("--skip-s4", action="store_true", help="跳过自建会话边界场景（默认跑，用于披露残余风险）")
    args = parser.parse_args(argv)

    print(f"run_with_timeout 参数面：orphan_guard={_HAS_ORPHAN_GUARD} terminate_grace={_HAS_TERMINATE_GRACE}")
    results: list[dict[str, Any]] = []
    try:
        results.append(scenario_s1_parent_killed())
        results.append(scenario_s2_outer_timeout())
        results.append(scenario_s3_terminate_grace())
        if not args.skip_s4:
            results.append(scenario_s4_self_session_descendant())
        # A→B→C 场景里 B 也被杀，可能留下 1 个孤儿需要清理
        leftover = _pytest_procs()
        if leftover:
            print(f"\n（收尾）清理残余标记进程 {[r['pid'] for r in leftover]}（复现证据已记录）")
        _kill_marker_procs()
    finally:
        _kill_marker_procs()

    leaked_count = sum(1 for item in results if item.get("leaked"))
    print("\n== 汇总：复现出孤儿的场景数 =", leaked_count)
    payload = {
        "marker": MARKER,
        "run_with_timeout_has_orphan_guard": _HAS_ORPHAN_GUARD,
        "run_with_timeout_has_terminate_grace": _HAS_TERMINATE_GRACE,
        "leaked_scenarios": leaked_count,
        "results": results,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"结果已写入：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
