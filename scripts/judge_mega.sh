#!/usr/bin/env bash
# judge_mega.sh — 31 判定进程全并行（767 单元 ≈ 18 分钟）
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
PLOG=/tmp/judge_mega.log
echo "[$(date +%H:%M:%S)] mega judge start (31 procs)" >> "$PLOG"

# ── C8 aitester 10 切片 ──
for S in $(seq 0 9); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms aitester --slice $S --nslices 10 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_aitester_s$S.json > /tmp/jm_a$S.log 2>&1 &
done
# ── C8 df 6 切片 ──
for S in $(seq 0 5); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms plain_llm_df --slice $S --nslices 6 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_df_s$S.json > /tmp/jm_d$S.log 2>&1 &
done
# ── B3 10 切片 ──
for S in $(seq 0 9); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
    --bench-dir experiments/results/b3_lite_20261031 \
    --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
    --py /tmp/mm_py38/bin/python --slice $S --nslices 10 \
    --out experiments/results/b3_lite_20261031/B3_JUDGE_s$S.json > /tmp/jm_b$S.log 2>&1 &
done
# ── rescue 1 + TGE 4 切片 ──
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/rescue31_manifest.jsonl" \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/rescue31_20261101 \
  --py /tmp/mm_py38/bin/python --arms plain_llm_df \
  --out experiments/results/rescue31_20261101/RESCUE_JUDGE.json > /tmp/jm_r.log 2>&1 &
for S in 0 1 2 3; do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 scripts/tools/judge_tge_accuracy.py \
    --manifest ~/.cache/aitester/testgeneval/tge_manifest.jsonl \
    --arm aitester --py /tmp/mm_py38/bin/python --slice $S --nslices 4 \
    --out experiments/results/minimal_gen/TGE_ACC_aitester_s$S.json > /tmp/jm_t$S.log 2>&1 &
done

wait
echo "[$(date +%H:%M:%S)] ALL 31 JUDGE PROCESSES DONE" >> "$PLOG"
echo "MEGA JUDGE DONE"
