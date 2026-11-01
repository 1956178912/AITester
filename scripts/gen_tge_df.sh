#!/usr/bin/env bash
# gen_tge_df.sh — TGE df 臂 160 任务（与 gen_tge_all 的 aitester 臂并行）
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] tge df arm start" >> /tmp/tge_genall.log
for i in $(seq 0 159); do
  .venv/bin/python3 scripts/tools/gen_task_minimal.py \
    --manifest ~/.cache/aitester/testgeneval/tge_manifest.jsonl \
    --out experiments/results/minimal_gen/tge_plain_llm_df.jsonl \
    --task-index $i --kind tge \
    >> /tmp/tge_gen_plain_llm_df.log 2>&1
done
echo "[$(date)] tge df arm done" >> /tmp/tge_genall.log
echo "TGE DF ARM DONE"
