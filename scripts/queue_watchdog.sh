#!/usr/bin/env bash
# 队列 watchdog（双流版）：流 A（df→判定→TGE）与流 B（B3 生成→判定）各自断点续跑
cd /Users/wangchenyu/Workspace/AITester
WDLOG=/tmp/watchdog.log
now_epoch=$(date +%s)

check_stream() {
  local name="$1" log="$2" done_glob="$3" script="$4"
  # 完成判定
  if ls $done_glob >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] watchdog: [$name] complete, skip" >> "$WDLOG"
    return 0
  fi
  local log_mtime=$(stat -f %m "$log" 2>/dev/null || echo 0)
  local age=$(( now_epoch - log_mtime ))
  local proc_pat="$5"
  local alive=$(ps ax 2>/dev/null | /usr/bin/grep -c "$proc_pat" | tr -d ' ')
  if [ "$alive" -ge 1 ] && [ "$age" -lt 1200 ]; then
    echo "[$(date +%H:%M:%S)] watchdog: [$name] alive (proc=$alive log_age=${age}s)" >> "$WDLOG"
    return 0
  fi
  echo "[$(date +%H:%M:%S)] watchdog: [$name] restarting (proc=$alive log_age=${age}s)" >> "$WDLOG"
  bash "$script" >> "/tmp/${name}_wd.log" 2>&1 &
  echo "[$(date +%H:%M:%S)] watchdog: [$name] restarted" >> "$WDLOG"
}

# 流 A：df→C8判定→TGE（完成=TGE df 臂产物）
check_stream "streamA" /tmp/recovery_queue.log \
  "experiments/results/tge_lite_20261031/plain_llm_df/benchmark_*.json" \
  scripts/recovery_queue.sh "run_benchmark.*plain_llm_df\|judge_c8"
# 流 B：B3 生成→判定（完成=B3_JUDGE.json）
check_stream "streamB" /tmp/b3_queue.log \
  "experiments/results/b3_lite_20261031/B3_JUDGE.json" \
  scripts/b3_queue.sh "run_benchmark.*swe_bench\|judge_swebench"
