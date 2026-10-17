"""有限墙钟看门狗：超时 SIGTERM→SIGKILL 进程组，不静默挂死。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

limit = float(sys.argv[1])
cmd = sys.argv[2:]
t0 = time.time()
proc = subprocess.Popen(cmd, start_new_session=True)
try:
    rc = proc.wait(timeout=limit)
except subprocess.TimeoutExpired:
    print(f"\n[watchdog] 超过墙钟上限 {limit:.0f}s：SIGTERM 进程组…", file=sys.stderr, flush=True)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait()
    sys.exit(124)
print(f"[watchdog] rc={rc} wall={time.time() - t0:.1f}s", file=sys.stderr, flush=True)
sys.exit(rc)
