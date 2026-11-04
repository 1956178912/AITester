#!/usr/bin/env bash
# parallel_launcher.sh — 14 分片进程级并行（df 8×13 + B3 6×50；DeepSeek 并发 2500 上限内）
# 分片级断点续跑：分片 json 存在即跳过；watchdog（automation 每小时）按分片补跑
cd /Users/wangchenyu/Workspace/AITester
PLOG=/tmp/parallel_launcher.log
echo "[$(date +%H:%M:%S)] parallel launcher start" >> "$PLOG"

ENV_PREFIX=(env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND
  -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy)

# ── df 8 分片 ──
for S in 1 2 3 4 5 6 7 8; do
  D="experiments/results/c8_full_20261031/plain_llm_df/shard${S}"
  mkdir -p "$D"
  if ls "$D"/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] df shard$S done, skip" >> "$PLOG"; continue
  fi
  env "${ENV_PREFIX[@]}" \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/df_shard${S}.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 ENABLE_RAG=false \
    AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=10.0 AITESTER_BATCH_MAX_USD=30.0 \
    AITESTER_CACHE_NAMESPACE=c8full_df_s${S} \
    .venv/bin/python3 experiments/run_benchmark.py -d bugsinpy -b plain_llm_df --seed 42 \
    -n 13 -p 1 -o "$D" --no-rag >> "/tmp/pf_df_s${S}.log" 2>&1 &
  echo "[$(date +%H:%M:%S)] df shard$S launched" >> "$PLOG"
done

# ── B3 6 分片 ──
for S in 1 2 3 4 5 6; do
  D="experiments/results/b3_lite_20261031/aitester/shard${S}"
  mkdir -p "$D"
  if ls "$D"/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] b3 shard$S done, skip" >> "$PLOG"; continue
  fi
  env "${ENV_PREFIX[@]}" \
    SWE_BENCH_ENRICHMENT="$HOME/.cache/aitester/swe_bench/b3_enrich_shard${S}.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 ENABLE_RAG=false \
    AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=10.0 AITESTER_BATCH_MAX_USD=30.0 \
    AITESTER_CACHE_NAMESPACE=b3lite_s${S} \
    .venv/bin/python3 experiments/run_benchmark.py -d swe_bench --subset lite \
    -b aitester --seed 42 -n 50 -p 1 -o "$D" --no-rag >> "/tmp/pf_b3_s${S}.log" 2>&1 &
  echo "[$(date +%H:%M:%S)] b3 shard$S launched" >> "$PLOG"
done

wait
echo "[$(date +%H:%M:%S)] all shards done" >> "$PLOG"

# ── 聚合判定（df 两臂 + B3）──
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/c8_full_20261031 \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/c8_full_20261031/C8_JUDGE.json >> "$PLOG" 2>&1
echo "[$(date +%H:%M:%S)] c8 judge exit=$?" >> "$PLOG"
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
  --bench-dir experiments/results/b3_lite_20261031 \
  --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/b3_lite_20261031/B3_JUDGE.json >> "$PLOG" 2>&1
echo "[$(date +%H:%M:%S)] b3 judge exit=$?" >> "$PLOG"
echo "PARALLEL LAUNCHER DONE"
