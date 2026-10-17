#!/usr/bin/env python3
"""嵌套测试子进程泄漏检测（K 轮 2026-10-17）：孤儿 pytest 进程的发现与清理。

## 为什么需要它（本机实测，非假设）

2026-10-17 全量测试巡检时在开发机上实测到**两个孤儿进程**：

    PID 69946 (PPID=1)  Python -m pytest /var/folders/…/tmpu8nw4j1j/test_mutant.py --tb=no -q
    PID 73256 (PPID=1)  Python -m pytest /var/folders/…/tmpwfr6sm9z/test_mutant.py --tb=no -q

启动于 09:53 / 10:04，已分别运行 **7h04m / 6h53m**、各占 ~97% CPU（合计浪费
约 14 CPU·小时），期间所有全量测试被拖慢一倍以上。`experiments/mutation_testing.py`
的变异体沙箱对每个变异体起一次嵌套 pytest；沙箱自身已用
`src.utils.process_utils.run_with_timeout`（`start_new_session` + 超时
`killpg`）自保，但**父进程被外部 SIGKILL**（agent 会话超时、用户 kill -9、
CI 取消）时，超时分支永远不会执行 → 子进程被 launchd/init(1) 收养后继续空转。
这是"父进程死亡"缺口，不是 killpg 缺口，代码侧无法在子进程内检测（macOS 无
`PR_SET_PDEATHSIG` 等价物）。因此用运行期卫生工具兜底：发现 → 报告 → 可选清理。

## 识别口径（宁可漏报，不误杀）

四条**同时**成立才判为泄漏：

1. 命令行含本项目嵌套测试沙箱标记（`tempfile.mkdtemp` 前缀 / 变异体文件名）：
   `aitester_proc_` / `aitester_mdo_` / `aitester_m1_` / `aitester_branch_cov_` /
   `aitester_fl_spectral_` / `aitester_probe_` / `aitester_p2p_` /
   `aitester_docker_` / `test_mutant.py`；
2. 命令行是 pytest 调用（`-m pytest` 或可执行文件名为 pytest）；
3. `PPID == 1`（父进程已死、被 init/launchd 收养）；
4. 存活时长 ≥ `--min-age`（默认 600s；正常嵌套 pytest 单用例级运行通常 <60s）。

**为什么不以"命令行含本仓库路径"为主判据**：合法的后台长跑（`nohup python -m
experiments.run_benchmark`）同样会被收养成 PPID=1，而本项目"全量跑批"动辄
小时级——用仓库路径会误杀真实批次。沙箱前缀是本项目嵌套测试调用独有的，
合法批次命令行不会出现。

## 用法

    python scripts/tools/detect_orphan_procs.py                 # 只读巡检（默认）
    python scripts/tools/detect_orphan_procs.py --json          # 结构化输出
    python scripts/tools/detect_orphan_procs.py --kill          # SIGTERM→SIGKILL 清理
    python scripts/tools/detect_orphan_procs.py --min-age 300   # 放宽/收紧龄期阈值

退出码：0 = 无泄漏（或 `ps` 不可用而跳过——部分沙箱禁止 ps，属已知环境限制）；
1 = 发现泄漏（`--kill` 后全部回收则仍为 0，未回收者留在报告里）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.process_utils import run_with_timeout  # noqa: E402

#: 本项目嵌套测试沙箱的目录前缀 / 文件名标记（与各调用点 `tempfile.mkdtemp`
#: 前缀逐一对齐；新增嵌套 pytest 调用点时须同步追加，否则该路径的泄漏看不见。
NESTED_TEST_MARKERS: tuple[str, ...] = (
    "aitester_proc_",  # src/utils/process_utils.py：文件后端子进程回收目录
    "aitester_mdo_",  # src/measurement/mdo.py：MDO 判分探针
    "aitester_m1_",  # experiments/_m1_metrics.py：M1 判分（detection/repair）
    "aitester_branch_cov_",  # src/tools/branch_coverage_inject.py：分支覆盖注入
    "aitester_fl_spectral_",  # src/agents/fl_spectral.py：谱系故障定位
    "aitester_probe_",  # src/agents/runtime_probe.py：运行时探针
    "aitester_p2p_",  # src/tools/patch_rollback.py：补丁回滚 P2P 验证
    "aitester_docker_",  # src/agents/executor_modes.py：Docker 执行沙箱
    "test_mutant.py",  # experiments/mutation_testing.py：变异体沙箱
)

#: `ps -axo pid=,ppid=,etime=,command=` 的行格式（command 可含任意空格）。
_PS_ROW_PATTERN = re.compile(r"^\s*(\d+)\s+(\d+)\s+([0-9:\-]+)\s+(.*)$")

#: etime 口径：`MM:SS` / `HH:MM:SS` / `DD-HH:MM:SS`（macOS/Linux procps 同口径）。
_ETIME_PATTERN = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$")


def parse_etime(raw: str) -> int | None:
    """把 `ps` 的 etime 字段解析为秒数（无法解析返回 None，不猜）。

    Args:
        raw: `MM:SS` / `HH:MM:SS` / `DD-HH:MM:SS` 形态的 etime。

    Returns:
        存活秒数；格式不符时 None（调用方按"无法判定龄期"跳过，宁可漏报）。
    """
    match = _ETIME_PATTERN.match(raw.strip())
    if match is None:
        return None
    days, hours, minutes, seconds = (int(part) if part is not None else 0 for part in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def parse_ps_output(stdout: str) -> list[dict[str, Any]]:
    """解析 `ps -axo pid=,ppid=,etime=,command=` 输出为进程字典列表。

    Args:
        stdout: ps 原始文本输出。

    Returns:
        进程列表（`pid` / `ppid` / `etime` / `age_seconds` / `command`）。
        格式不符的行直接跳过（ps 头部/空行/截断行不得让巡检崩溃）。
    """
    processes: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        match = _PS_ROW_PATTERN.match(line)
        if match is None:
            continue
        pid, ppid, etime, command = match.groups()
        processes.append(
            {
                "pid": int(pid),
                "ppid": int(ppid),
                "etime": etime,
                "age_seconds": parse_etime(etime),
                "command": command.strip(),
            }
        )
    return processes


def list_processes(ps_timeout: float = 10.0) -> list[dict[str, Any]]:
    """读取当前进程表（`ps` 不可用时抛 RuntimeError，由调用方按"不可用"降级）。

    Args:
        ps_timeout: ps 子进程超时秒数（防 ps 自身异常挂住巡检）。

    Returns:
        进程字典列表。

    Raises:
        RuntimeError: ps 返回非 0 / 超时 / 输出为空——巡检器不得把"读不到"
            当作"无泄漏"来静默判绿（与项目 G1/G2 门禁 fail-closed 纪律同构：
            不可用必须在报告里区分出来）。
    """
    proc = run_with_timeout(
        ["ps", "-axo", "pid=,ppid=,etime=,command="],
        timeout=ps_timeout,
        logger_name="detect_orphan_procs",
    )
    if proc.timed_out:
        raise RuntimeError(f"ps 执行超时（>{ps_timeout}s）")
    if proc.returncode != 0:
        raise RuntimeError(f"ps 退出码 {proc.returncode}：{(proc.stderr or '').strip()[:120]}")
    processes = parse_ps_output(proc.stdout or "")
    if not processes:
        raise RuntimeError("ps 输出为空或格式不可解析")
    return processes


def _looks_like_pytest(command: str) -> bool:
    """命令行是否为 pytest 调用（嵌套测试沙箱只可能是 pytest 子进程）。"""
    if "-m pytest" in command or "-m  pytest" in command:
        return True
    first_token = command.split(" ", 1)[0]
    return Path(first_token).name == "pytest"


def classify_leaks(processes: list[dict[str, Any]], min_age_seconds: int = 600) -> list[dict[str, Any]]:
    """按四条件交集判定"泄漏的嵌套测试子进程"。

    Args:
        processes: `list_processes()` 的输出。
        min_age_seconds: 龄期下限（秒）；短于该值的认定为在跑的正常嵌套测试。

    Returns:
        命中进程列表（含 `matched_marker` 便于人工复核命中原因）。
    """
    leaked: list[dict[str, Any]] = []
    for process in processes:
        age = process.get("age_seconds")
        if age is None or age < min_age_seconds:
            continue
        # 收养判据：PPID=1 表示原父进程已消亡（macOS launchd / Linux init）。
        # 不把"父进程仍在但卡死"纳入——那属于父进程自身健康问题，且误杀风险高。
        if process.get("ppid") != 1:
            continue
        command = str(process.get("command") or "")
        if not _looks_like_pytest(command):
            continue
        marker = next((m for m in NESTED_TEST_MARKERS if m in command), None)
        if marker is None:
            continue
        leaked.append({**process, "matched_marker": marker})
    return leaked


def terminate_pids(
    pids: list[int],
    *,
    grace_seconds: float = 2.0,
    kill_fn: Any = os.kill,
    sleep_fn: Any = time.sleep,
) -> list[dict[str, Any]]:
    """先 SIGTERM 给优雅退出机会，宽限期后对仍存活者 SIGKILL。

    为什么两步：pytest 收到 SIGTERM 会做清理（删除 tempdir / 写缓存），
    直接 SIGKILL 会留下半写文件；而写死循环的变异体可能对 SIGTERM 无响应，
    故必须保留 SIGKILL 兜底（本项目已知"变异体死循环"形态，见
    `experiments/mutation_testing._run_mutant_tests` 注释）。

    Args:
        pids: 待终止 PID 列表（调用方保证只传入 `classify_leaks()` 结果）。
        grace_seconds: SIGTERM 后的宽限期。
        kill_fn: 注入点（测试用假实现；生产默认 `os.kill`）。
        sleep_fn: 注入点（测试用假实现；生产默认 `time.sleep`）。

    Returns:
        逐 PID 的处置结果：`{"pid", "sigterm", "sigkill"}`（bool 表示是否发出）。
    """
    results: list[dict[str, Any]] = []
    sent: dict[int, dict[str, Any]] = {pid: {"pid": pid, "sigterm": False, "sigkill": False} for pid in pids}
    for pid in pids:
        try:
            kill_fn(pid, signal.SIGTERM)
            sent[pid]["sigterm"] = True
        except (ProcessLookupError, PermissionError, OSError):
            # 进程已自行退出 / 无权限（无权限时不强杀，如实记录）
            results.append(sent[pid])
            del sent[pid]
    if sent and grace_seconds > 0:
        sleep_fn(grace_seconds)
    for pid, row in sent.items():
        try:
            kill_fn(pid, 0)  # 0 号信号 = 存活探测（不发信号）
        except (ProcessLookupError, PermissionError, OSError):
            results.append(row)
            continue
        try:
            kill_fn(pid, signal.SIGKILL)
            row["sigkill"] = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
        results.append(row)
    # 保持与输入 pids 一致的顺序，便于报告与人工对照
    order = {pid: index for index, pid in enumerate(pids)}
    return sorted(results, key=lambda item: order.get(int(item["pid"]), 0))


def _format_seconds(seconds: int | None) -> str:
    """把秒数格式化为人类可读的 `Hh Mm` 形态（报告可读性）。"""
    if seconds is None:
        return "unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{remainder % 60:02d}s"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口（退出码语义见模块 docstring）。"""
    parser = argparse.ArgumentParser(description="嵌套测试子进程泄漏检测（孤儿 pytest 巡检）")
    parser.add_argument("--json", action="store_true", help="结构化 JSON 输出（供 preflight / 自动化消费）")
    parser.add_argument("--kill", action="store_true", help="清理命中的孤儿进程（SIGTERM→SIGKILL）")
    parser.add_argument("--min-age", type=int, default=600, help="龄期下限秒数（默认 600）")
    parser.add_argument("--ps-timeout", type=float, default=10.0, help="ps 子进程超时秒数（默认 10）")
    parser.add_argument("--grace", type=float, default=2.0, help="SIGTERM 宽限期秒数（默认 2）")
    args = parser.parse_args(argv)

    try:
        processes = list_processes(args.ps_timeout)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        payload: dict[str, Any] = {"available": False, "reason": str(exc), "leaked": [], "scanned": 0}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"[SKIP] ps 不可用，跳过孤儿进程巡检：{exc}")
        return 0

    leaked = classify_leaks(processes, args.min_age)
    report: dict[str, Any] = {
        "available": True,
        "scanned": len(processes),
        "min_age_seconds": args.min_age,
        "leaked": leaked,
        "leaked_count": len(leaked),
    }
    exit_code = 1 if leaked else 0

    if args.kill and leaked:
        report["termination"] = terminate_pids(
            [int(item["pid"]) for item in leaked],
            grace_seconds=args.grace,
        )
        unrecovered = [row for row in report["termination"] if not row["sigterm"] and not row["sigkill"]]
        report["unrecovered"] = unrecovered
        exit_code = 1 if unrecovered else 0

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return exit_code

    if not leaked:
        print(f"[OK] 未发现泄漏的嵌套测试子进程（扫描 {len(processes)} 个进程，龄期下限 {args.min_age}s）")
        return 0
    print(f"[LEAK] 发现 {len(leaked)} 个泄漏的嵌套测试子进程（扫描 {len(processes)} 个进程）：")
    for row in leaked:
        print(
            f"  - pid={row['pid']} ppid={row['ppid']} 存活={_format_seconds(row['age_seconds'])} "
            f"命中={row['matched_marker']}\n    {row['command'][:160]}"
        )
    if args.kill:
        for row in report.get("termination", []):
            actions = "+".join(
                name.upper() for name, flag in (("sigterm", row["sigterm"]), ("sigkill", row["sigkill"])) if flag
            )
            print(f"  已处理 pid={row['pid']}：{actions or '进程已自行退出'}")
        if report.get("unrecovered"):
            print(f"  ⚠️ {len(report['unrecovered'])} 个进程未回收（无权限或已僵死），需人工处理")
    else:
        print("  提示：加 --kill 清理（先 SIGTERM，宽限期后 SIGKILL）")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
