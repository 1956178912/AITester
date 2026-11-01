#!/usr/bin/env bash
# gen_batch_driver.sh — per-task 循环驱动（每任务独立短进程，checkpoint 断点）
# 用法：gen_batch_driver.sh <manifest> <out_jsonl> <kind> <start> <end>
set -u
cd /Users/wangchenyu/Workspace/AITester
MANIFEST="$1"; OUT="$2"; KIND="$3"; START="$4"; END="$5"
NAME="$(basename $OUT .jsonl)"
for i in $(seq $START $END); do
  .venv/bin/python3 scripts/tools/gen_task_minimal.py --manifest "$MANIFEST" --out "$OUT" --task-index "$i" --kind "$KIND" >> "/tmp/gen_${NAME}.log" 2>&1
done
echo "[$(date +%H:%M:%S)] batch $NAME done" >> /tmp/gen_driver.log
