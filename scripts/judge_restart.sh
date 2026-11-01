#!/usr/bin/env bash
# judge_restart.sh — 判定重启（新版含 venv 切片隔离）：C8 双臂 6 切片 → B3 14 切片
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] judge restart start" >> /tmp/judgerestart.log

# ── C8 aitester 3 切片 ──
for S in 0 1 2; do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms aitester --slice $S --nslices 3 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_aitester_s$S.json \
    > /tmp/jr_a$S.log 2>&1 &
done
wait
echo "[$(date)] C8 aitester 3 slices done" >> /tmp/judgerestart.log

# ── C8 df 3 切片 ──
for S in 0 1 2; do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms plain_llm_df --slice $S --nslices 3 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_df_s$S.json \
    > /tmp/jr_d$S.log 2>&1 &
done
wait
echo "[$(date)] C8 df 3 slices done" >> /tmp/judgerestart.log

# ── B3 14 切片（slice 0 已有 /tmp/verify_b3s0.json）──
for S in $(seq 1 14); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
    --bench-dir experiments/results/b3_lite_20261031 \
    --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
    --py /tmp/mm_py38/bin/python --slice $S --nslices 15 \
    --out experiments/results/b3_lite_20261031/B3_JUDGE_s$S.json \
    > /tmp/jr_b$S.log 2>&1 &
done
wait
echo "[$(date)] B3 14 slices done" >> /tmp/judgerestart.log
echo "JUDGE RESTART ALL DONE"
