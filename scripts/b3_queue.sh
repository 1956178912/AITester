#!/usr/bin/env bash
# b3_queue.sh — 流 B：B3 Lite 生成 + 判定（与流 A 的 df/TGE 并行）
set -u
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/b3_queue.log
echo "[$(date +%H:%M:%S)] b3 stream start" >> "$LOG"

# 步骤 B1：B3 Lite aitester 单臂生成（300 任务，-p 1 串行稳定口径）
mkdir -p experiments/results/b3_lite_20261031/aitester
if ! ls experiments/results/b3_lite_20261031/aitester/benchmark_*.json >/dev/null 2>&1; then
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    SWE_BENCH_ENRICHMENT="$HOME/.cache/aitester/swe_bench/swe_bench_lite_enrichment.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 \
    ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=b3lite \
    .venv/bin/python3 experiments/run_benchmark.py -d swe_bench --subset lite \
    -b aitester --seed 42 -n 300 -p 1 -o experiments/results/b3_lite_20261031/aitester --no-rag \
    >> /tmp/b3lite_aitester.log 2>&1
  echo "[$(date +%H:%M:%S)] B1 b3 gen exit=$?" >> "$LOG"
fi

# 步骤 B2：B3 判定（零 LLM，repo 级红绿翻转）
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
  --bench-dir experiments/results/b3_lite_20261031 \
  --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/b3_lite_20261031/B3_JUDGE.json >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] B2 b3 judge exit=$?" >> "$LOG"
echo "[$(date +%H:%M:%S)] b3 stream end" >> "$LOG"
echo "B3 STREAM DONE"
