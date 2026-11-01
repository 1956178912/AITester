#!/usr/bin/env bash
# 队列 watchdog：队列死则重启（skip 逻辑断点续跑），队列完成则跳过
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/recovery_queue.log
WDLOG=/tmp/watchdog.log
# 队列完成判定：TGE df 臂产物 json 存在 = 全部完成
if ls experiments/results/tge_lite_20261031/plain_llm_df/benchmark_*.json >/dev/null 2>&1; then
  echo "[$(date +%H:%M:%S)] watchdog: queue complete, no action" >> "$WDLOG"
  exit 0
fi
# 活性判定：recovery_queue.log mtime 距今 < 20 分钟 且 有 run_benchmark 进程
log_mtime=$(stat -f %m "$LOG" 2>/dev/null || echo 0)
now_epoch=$(date +%s)
age=$(( now_epoch - log_mtime ))
alive_proc=$(ps ax 2>/dev/null | /usr/bin/grep "[r]un_benchmark" | wc -l | tr -d ' ')
if [ "$alive_proc" -ge 1 ] && [ "$age" -lt 1200 ]; then
  echo "[$(date +%H:%M:%S)] watchdog: alive (proc=$alive_proc log_age=${age}s), no action" >> "$WDLOG"
  exit 0
fi
echo "[$(date +%H:%M:%S)] watchdog: restarting queue (proc=$alive_proc log_age=${age}s)" >> "$WDLOG"
bash scripts/recovery_queue.sh >> /tmp/recovery_main_wd.log 2>&1 &
echo "[$(date +%H:%M:%S)] watchdog: restarted" >> "$WDLOG"
