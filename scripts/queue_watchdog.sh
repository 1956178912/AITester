#!/usr/bin/env bash
# watchdog（极简版）：14 driver 活性检查 + 完成判定
cd /Users/wangchenyu/Workspace/AITester
WDLOG=/tmp/watchdog.log
DONE=experiments/results/minimal_gen/ALL_DONE.marker
if [ -f "$DONE" ]; then echo "[$(date +%H:%M:%S)] all done" >> "$WDLOG"; exit 0; fi
alive=$(ps ax 2>/dev/null | /usr/bin/grep -c "[g]en_task_minimal" | tr -d ' ')
if [ "$alive" -ge 1 ]; then
  total=$(cat experiments/results/minimal_gen/df_s*.jsonl experiments/results/minimal_gen/b3_s*.jsonl 2>/dev/null | wc -l | tr -d ' ')
  echo "[$(date +%H:%M:%S)] alive proc=$alive done_tasks=$total/404" >> "$WDLOG"
  exit 0
fi
# driver 全死：还有未完成任务则重启 driver 组
total=$(cat experiments/results/minimal_gen/df_s*.jsonl experiments/results/minimal_gen/b3_s*.jsonl 2>/dev/null | wc -l | tr -d ' ')
echo "[$(date +%H:%M:%S)] drivers dead at $total/404 — relaunching" >> "$WDLOG"
for S in 1 2 3 4 5 6 7 8; do
  D=experiments/results/minimal_gen/df_s${S}.jsonl
  ST=$(( (S-1)*13 ))
  bash scripts/gen_batch_driver.sh ~/.cache/aitester/bugsinpy/df_shard${S}.jsonl "$D" df $ST $(( S*13-1 )) >> /tmp/wd_df_s${S}.log 2>&1 &
done
for S in 1 2 3 4 5 6; do
  D=experiments/results/minimal_gen/b3_s${S}.jsonl
  ST=$(( (S-1)*50 ))
  bash scripts/gen_batch_driver.sh ~/.cache/aitester/swe_bench/b3_enrich_shard${S}.jsonl "$D" swebench $ST $(( S*50-1 )) >> /tmp/wd_b3_s${S}.log 2>&1 &
done
echo "[$(date +%H:%M:%S)] drivers relaunched" >> "$WDLOG"
