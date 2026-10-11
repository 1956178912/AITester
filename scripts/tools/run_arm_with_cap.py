#!/usr/bin/env python
"""带硬墙钟上限的单臂跑批包装器（2026-10-10 独立审查）。

为什么需要它：
    2026-10-10 逻辑通道 A/B 首跑时，`run_benchmark.py` 在 **50/50 任务全部完成
    之后**卡死 25+ 分钟（%CPU 0.0），根因是变异层 `subprocess.run(timeout=...)`
    超时只 kill 直接子进程，陷入死循环的变异体 pytest 继续持有管道写端 →
    `communicate()` 等 EOF **永久阻塞**，批次 JSON 从未写出。
    该缺陷已修复（`experiments/mutation_testing.py` 改建在
    `src.utils.process_utils.run_with_timeout` 之上，killpg 整树 + 有界收口），
    但**跑批层不应依赖被测代码不出错**——本包装器提供独立的墙钟兜底：
    超时即 kill 整个进程组，绝不让一次跑批无限占用时间与预算。

用法：
    python scripts/tools/run_arm_with_cap.py --timeout 3000 --log <log> -- \\
        .venv/bin/python experiments/run_benchmark.py ...
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="单臂跑批 + 硬墙钟上限")
    parser.add_argument("--timeout", type=float, required=True, help="墙钟上限（秒）")
    parser.add_argument("--log", required=True, help="日志文件路径（stdout+stderr 合并）")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后的实际命令")
    args = parser.parse_args(argv)

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("[FAIL] 未提供命令（用法：... -- <cmd>）", file=sys.stderr)
        return 2

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    with open(log_path, "wb") as logf:
        # start_new_session：独立进程组，超时后可 killpg 整树
        proc = subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
            start_new_session=True,
        )
        try:
            rc = proc.wait(timeout=args.timeout)
            elapsed = time.monotonic() - t0
            print(f"[OK] 退出码={rc} 耗时={elapsed:.1f}s（上限 {args.timeout:.0f}s）")
            return rc
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            print(
                f"[WARN] 触及硬墙钟上限 {args.timeout:.0f}s（已耗时 {elapsed:.1f}s）"
                "——kill 整个进程组（含孙进程），防止无限占用",
                file=sys.stderr,
            )
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(5)
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            with open(log_path, "ab") as f:
                f.write(f"\n[WRAPPER] 触及硬墙钟上限 {args.timeout:.0f}s，进程组已终止\n".encode())
            return 124  # 与 GNU timeout 约定一致


if __name__ == "__main__":
    sys.exit(main())
