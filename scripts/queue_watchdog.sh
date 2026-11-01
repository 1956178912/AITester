#!/usr/bin/env bash
# 队列 watchdog：队列死则重启（skip 逻辑断点续跑），队列完成则跳过
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/recovery_queue.log
# 队列完成的判定：R5 TGE df 臂有产物 json = 全部完成
if ls experiments/results/tge_lite_20261031/plain_llm_df/benchmark_*.json >/dev/null 2>&1; then
  echo "[$(date +%H:%M:%S)] watchdog: queue complete, no action" >> /tmp/watchdog.log
  exit 0
fi
# 活性判定：最近 12 分钟内有新日志行 且 有 run_benchmark 进程 → 活着
last_epoch=$(python3 -c "
import re,datetime,sys
lines=[l for l in open('$LOG') if 'recovery start' in l or 'exit=' in l or 'done' in l]
if not lines: print(0); sys.exit()
m=re.match(r'\[(\d+):(\d+):(\d+)\]', lines[-1])
if not m: print(0); sys.exit()
h,mi,s=map(int,m.groups())
print(h*3600+mi*60+s)
" 2>/dev/null || echo 0)
now_epoch=$(date +%H)*3600 + $(date +%M)*60 + $(date +%S)
alive_proc=$(ps ax 2>/dev/null | /usr/bin/grep -c "[r]un_benchmark" || echo 0)
stale=$(( now_epoch - ${last_epoch:-0} ))
if [ "$alive_proc" -gt 0 ] && [ "$stale" -lt 1800 ]; then
  echo "[$(date +%H:%M:%S)] watchdog: alive (proc=$alive_proc stale=${stale}s), no action" >> /tmp/watchdog.log
  exit 0
fi
echo "[$(date +%H:%M:%S)] watchdog: restarting queue (proc=$alive_proc stale=${stale}s)" >> /tmp/watchdog.log
bash scripts/recovery_queue.sh >> /tmp/recovery_main_wd.log 2>&1 &
echo "[$(date +%H:%M:%S)] watchdog: restarted" >> /tmp/watchdog.log
