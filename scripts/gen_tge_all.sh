#!/usr/bin/env bash
# gen_tge_all.sh — TGE 160 任务生成（2 臂顺序，逐任务断点）
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] tge start" >> /tmp/tge_genall.log
for ARM in aitester plain_llm_df; do
  for i in $(seq 0 159); do
    .venv/bin/python3 scripts/tools/gen_task_minimal.py \
      --manifest ~/.cache/aitester/testgeneval/tge_manifest.jsonl \
      --out experiments/results/minimal_gen/tge_${ARM}.jsonl \
      --task-index $i --kind tge \
      >> /tmp/tge_gen_${ARM}.log 2>&1
  done
  echo "[$(date)] tge $ARM done" >> /tmp/tge_genall.log
done
total=$(cat experiments/results/minimal_gen/tge_*.jsonl 2>/dev/null | wc -l | tr -d ' ')
echo "[$(date)] TGE ALL DONE: $total/320" >> /tmp/tge_genall.log
echo "TGE GENERATION DONE: $total/320"
