#!/usr/bin/env bash
# final_judge_all.sh — 全部判定收官（27 进程两波）：C8 18 切片 + B3 10（py3.14 基座）+ rescue + luigi + TGE df 4
cd /Users/wangchenyu/Workspace/AITester
export HOME=/Users/wangchenyu
echo "[$(date +%H:%M:%S)] final judge start" >> /tmp/final_judge.log

# ═══ 第一波：C8 双臂 6 切片（跳过已完成）═══
for S in $(seq 0 9); do
  [ -f "experiments/results/c8_full_20261031/C8_JUDGE_aitester_s$S.json" ] && continue
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms aitester --slice $S --nslices 10 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_aitester_s$S.json > /tmp/fj_a$S.log 2>&1 &
done
for S in $(seq 0 5); do
  [ -f "experiments/results/c8_full_20261031/C8_JUDGE_df_s$S.json" ] && continue
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
    --bench-dir experiments/results/c8_full_20261031 \
    --py /tmp/mm_py38/bin/python --arms plain_llm_df --slice $S --nslices 6 \
    --out experiments/results/c8_full_20261031/C8_JUDGE_df_s$S.json > /tmp/fj_d$S.log 2>&1 &
done
wait
echo "[$(date +%H:%M:%S)] wave1 C8 done" >> /tmp/final_judge.log

# ═══ 第二波：B3 重判 10 切片（py3.14 基座）+ rescue + luigi + TGE df 4 ═══
rm -rf /tmp/b3_venv_* 2>/dev/null
for S in $(seq 0 9); do
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
    --bench-dir experiments/results/b3_lite_20261031 \
    --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
    --py /tmp/mm_py38/bin/python --slice $S --nslices 10 \
    --out experiments/results/b3_lite_20261031/B3_JUDGE_s$S.json > /tmp/fj_b$S.log 2>&1 &
done
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/rescue31_manifest.jsonl" \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/rescue31_20261101 \
  --py /tmp/mm_py38/bin/python --arms plain_llm_df \
  --out experiments/results/rescue31_20261101/RESCUE_JUDGE.json > /tmp/fj_r.log 2>&1 &
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/luigi_manifest.jsonl" \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/luigi_20261101 \
  --py /tmp/mm_py38/bin/python --arms plain_llm_df \
  --out experiments/results/luigi_20261101/LUIGI_JUDGE.json > /tmp/fj_l.log 2>&1 &
for S in 0 1 2 3; do
  JUDGE_NO_DAEMON=1 .venv/bin/python3 scripts/tools/judge_tge_accuracy.py \
    --manifest experiments/results/minimal_gen/tge_plain_llm_df.jsonl \
    --arm plain_llm_df --py /tmp/mm_py38/bin/python --slice $S --nslices 4 \
    --out experiments/results/minimal_gen/TGE_ACC_df_s$S.json > /tmp/fj_t$S.log 2>&1 &
done
wait
echo "[$(date +%H:%M:%S)] wave2 done" >> /tmp/final_judge.log
echo "FINAL JUDGE ALL DONE"
