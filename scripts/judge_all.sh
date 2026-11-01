#!/usr/bin/env bash
# judge_all.sh — 全部判定（零 LLM）：C8 df 两臂 + B3（生成完成后再跑）
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] judge_all start" >> /tmp/judgeall.log

# C8 判定（aitester 173 + df 104）
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/c8_full_20261031 \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/c8_full_20261031/C8_JUDGE.json
echo "[$(date)] C8 judge exit=$?" >> /tmp/judgeall.log

# B3 判定（若生成完成；未完成则此步会判已有产物——补跑覆盖）
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
  --bench-dir experiments/results/b3_lite_20261031 \
  --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/b3_lite_20261031/B3_JUDGE.json
echo "[$(date)] B3 judge exit=$?" >> /tmp/judgeall.log
echo "JUDGE ALL DONE"
