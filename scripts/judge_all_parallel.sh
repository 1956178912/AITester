#!/usr/bin/env bash
# judge_all_parallel.sh — 21 判定进程全并行（C8 aitester 3 + C8 df 3 + B3 14 + luigi 1）
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date)] 21-slice judge start" >> /tmp/judge_par.log

# ── C8 aitester 3 切片 ──
for S in 0 1 2; do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms aitester --slice $S --nslices 3 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_aitester_s$S.json > /tmp/jp_a$S.log 2>&1 &
done
# ── C8 df 3 切片 ──
for S in 0 1 2; do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms plain_llm_df --slice $S --nslices 3 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_df_s$S.json > /tmp/jp_d$S.log 2>&1 &
done
# ── B3 14 切片 ──
for S in $(seq 1 14); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
    --bench-dir experiments/results/b3_lite_20261031 \
    --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
    --py /tmp/mm_py38/bin/python --slice $S --nslices 15 \
    --out experiments/results/b3_lite_20261031/B3_JUDGE_s$S.json > /tmp/jp_b$S.log 2>&1 &
done
# ── luigi 1 进程（33 单元 df 单臂）──
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/luigi_manifest.jsonl" \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/luigi_20261101 \
  --py /tmp/mm_py38/bin/python --arms plain_llm_df --nslices 1 \
  --out experiments/results/luigi_20261101/LUIGI_JUDGE.json > /tmp/jp_l.log 2>&1 &

wait
echo "[$(date)] all 21 judge processes done" >> /tmp/judge_par.log
echo "ALL 21 JUDGE PROCESSES DONE"
