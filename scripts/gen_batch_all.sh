#!/usr/bin/env bash
# 一次性跑完全部生成（404 任务）：df 104 + B3 300，顺序执行、逐任务断点
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] gen_batch_all start" >> /tmp/genall.log
for S in 1 2 3 4 5 6 7 8; do
  bash scripts/gen_batch_driver.sh ~/.cache/aitester/bugsinpy/df_shard${S}.jsonl \
    experiments/results/minimal_gen/df_s${S}.jsonl df 0 12
done
for S in 1 2 3 4 5 6; do
  bash scripts/gen_batch_driver.sh ~/.cache/aitester/swe_bench/b3_enrich_shard${S}.jsonl \
    experiments/results/minimal_gen/b3_s${S}.jsonl swebench 0 49
done
total=$(cat experiments/results/minimal_gen/df_s*.jsonl experiments/results/minimal_gen/b3_s*.jsonl 2>/dev/null | wc -l | tr -d ' ')
echo "[$(date)] gen_batch_all END: $total/404" >> /tmp/genall.log
echo "ALL GENERATION DONE: $total/404"
