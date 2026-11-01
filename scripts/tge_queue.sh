#!/usr/bin/env bash
# tge_queue.sh — 流 C：TestGenEval-Lite 2 臂生成（accuracy 口径）
set -u
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/tge_queue.log
echo "[$(date +%H:%M:%S)] tge stream start" >> "$LOG"
for arm in aitester plain_llm_df; do
  mkdir -p experiments/results/tge_lite_20261031/$arm
  if ls experiments/results/tge_lite_20261031/$arm/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] C1 $arm done, skip" >> "$LOG"; continue
  fi
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 \
    ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=tge_${arm} \
    .venv/bin/python3 experiments/run_benchmark.py -d testgeneval \
    -b $arm --seed 42 -n 160 -p 1 -o experiments/results/tge_lite_20261031/$arm --no-rag \
    >> /tmp/tge_${arm}.log 2>&1
  echo "[$(date +%H:%M:%S)] C1 $arm exit=$?" >> "$LOG"
done
echo "[$(date +%H:%M:%S)] tge stream end" >> "$LOG"
echo "TGE STREAM DONE"
