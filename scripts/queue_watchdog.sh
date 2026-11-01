#!/usr/bin/env bash
# watchdog (shard version)
cd /Users/wangchenyu/Workspace/AITester
WDLOG=/tmp/watchdog.log
PLOG=/tmp/parallel_launcher.log
if [ -f experiments/results/c8_full_20261031/C8_JUDGE.json ] && [ -f experiments/results/b3_lite_20261031/B3_JUDGE.json ]; then
  echo "complete" >> "$WDLOG"; exit 0
fi
log_mtime=$(stat -f %m "$PLOG" 2>/dev/null || echo 0)
now=$(date +%s)
age=$(( now - log_mtime ))
alive=$(ps ax 2>/dev/null | grep -c "[r]un_benchmark" | tr -d ' ')
if [ "$alive" -ge 1 ] && [ "$age" -lt 1200 ]; then
  echo "alive proc=$alive age=$age" >> "$WDLOG"; exit 0
fi
echo "restarting (proc=$alive age=$age)" >> "$WDLOG"
bash scripts/parallel_launcher.sh >> /tmp/pl_wd.log 2>&1 &
echo "restarted" >> "$WDLOG"
