#!/usr/bin/env bash
# recovery_queue.sh — 2026-11-01 晨：恢复中断的晚间队列（aitester 臂已完成）
set -u
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/recovery_queue.log
echo "[$(date +%H:%M:%S)] recovery start" >> "$LOG"

# ── 步骤 R1：C8 plain_llm_df 臂生成（173 任务，并行 4）──
mkdir -p experiments/results/c8_full_20261031/plain_llm_df
if ! ls experiments/results/c8_full_20261031/plain_llm_df/benchmark_*.json >/dev/null 2>&1; then
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=c8full_df \
    .venv/bin/python3 experiments/run_benchmark.py -d bugsinpy -b plain_llm_df --seed 42 \
    -n 173 -p 1 -o experiments/results/c8_full_20261031/plain_llm_df --no-rag \
    >> /tmp/c8full_df.log 2>&1
  echo "[$(date +%H:%M:%S)] R1 df gen exit=$?" >> "$LOG"
fi

# ── 步骤 R2：C8 判定（两臂）──
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/c8_full_20261031 \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/c8_full_20261031/C8_JUDGE.json >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] R2 c8 judge exit=$?" >> "$LOG"

# ── 步骤 R3/R4（B3）已拆至 b3_queue.sh 并行流 ──

# ── 步骤 R5：TestGenEval 2 臂生成 ──
for arm in aitester plain_llm_df; do
  mkdir -p experiments/results/tge_lite_20261031/$arm
  if ls experiments/results/tge_lite_20261031/$arm/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] R5 $arm done, skip" >> "$LOG"; continue
  fi
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=tge_${arm} \
    .venv/bin/python3 experiments/run_benchmark.py -d testgeneval \
    -b $arm --seed 42 -n 160 -p 1 -o experiments/results/tge_lite_20261031/$arm --no-rag \
    >> /tmp/tge_${arm}.log 2>&1
  echo "[$(date +%H:%M:%S)] R5 $arm exit=$?" >> "$LOG"
done

echo "[$(date +%H:%M:%S)] recovery end" >> "$LOG"
echo "RECOVERY QUEUE DONE"
