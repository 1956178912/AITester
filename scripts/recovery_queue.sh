#!/usr/bin/env bash
# recovery_queue.sh — 2026-11-01 晨：恢复中断的晚间队列（aitester 臂已完成）
#
# 2026-11-02 事故修复（实测 772 次重启，与 b3_queue.sh 同因）：一次性批处理被
#   launchd 以 KeepAlive=true 托管（com.aitester.queueA），退出即重拉，判定步骤
#   不幂等 ⇒ 每轮新起全量判定并互写同一 out。防护同 b3_queue.sh：重入锁 + 完成标记。
set -u
export HOME=/Users/wangchenyu
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/recovery_queue.log

DONE_MARK=experiments/results/c8_full_20261031/QUEUE_DONE.marker
if [ -f "$DONE_MARK" ]; then
  echo "[$(date +%H:%M:%S)] done marker present, skip (rm ${DONE_MARK} to rerun)" >> "$LOG"
  exit 0
fi
LOCK=/tmp/recovery_queue.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[$(date +%H:%M:%S)] another instance holds ${LOCK}, exit" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
echo "[$(date +%H:%M:%S)] recovery start" >> "$LOG"

# ── 步骤 R1：C8 df 臂生成（4 分片容错，单片死不丢全批）──
for SHARD in 1 2 3 4; do
  SHARD_DIR="experiments/results/c8_full_20261031/plain_llm_df/shard${SHARD}"
  mkdir -p "$SHARD_DIR"
  if ls "$SHARD_DIR"/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] R1 shard${SHARD} done, skip" >> "$LOG"; continue
  fi
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full_shard${SHARD}.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 PYTEST_TIMEOUT_ENABLE=true PYTEST_TIMEOUT_SECONDS=20 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=c8full_df_shard${SHARD} \
    .venv/bin/python3 experiments/run_benchmark.py -d bugsinpy -b plain_llm_df --seed 42 \
    -n 26 -p 1 -o "$SHARD_DIR" --no-rag \
    >> "/tmp/c8full_df_shard${SHARD}.log" 2>&1
  echo "[$(date +%H:%M:%S)] R1 shard${SHARD} exit=$?" >> "$LOG"
done
echo "[$(date +%H:%M:%S)] R1 df gen all shards done" >> "$LOG"

# ── 步骤 R2：C8 判定（两臂）──
# 幂等判据按 16 个分片计：分片齐备即视为已判（JUDGE_REPORT 由分片聚合，
# 全量 C8_JUDGE.json 非权威产物；重跑只会并发写同一 out）。
JUDGE_RC=1
N_SLICE=$(ls experiments/results/c8_full_20261031/C8_JUDGE_*_s*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$N_SLICE" -ge 16 ]; then
  echo "[$(date +%H:%M:%S)] R2 ${N_SLICE}/16 slices present, skip full judge" >> "$LOG"
  JUDGE_RC=0
else
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python \
    --out experiments/results/c8_full_20261031/C8_JUDGE.json >> "$LOG" 2>&1
  JUDGE_RC=$?
  echo "[$(date +%H:%M:%S)] R2 c8 judge exit=${JUDGE_RC}" >> "$LOG"
fi

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
# 仅当判定步骤成功才落完成标记：失败保留可重跑路径
if [ "$JUDGE_RC" -eq 0 ]; then
  : > "$DONE_MARK"
  echo "[$(date +%H:%M:%S)] done marker written: ${DONE_MARK}" >> "$LOG"
fi
echo "RECOVERY QUEUE DONE"
