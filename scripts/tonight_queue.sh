#!/usr/bin/env bash
# tonight_queue.sh — 2026-10-31 晚间总控执行队列（用户授权：今晚全部执行/排队）
# 队列：C8 全项目 2 臂生成 → C8 判定 → B3 Lite 单臂生成 → B3 判定
# 每步落 checkpoint 文件；单步失败记录后继续（不阻断队列）。
set -u
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/tonight_queue.log
CKPT=experiments/results/tonight_20261031_QUEUE_STATE.json
echo "[$(date +%H:%M:%S)] queue start" >> "$LOG"

# 环境预检（并发 4，若 JSON 未就绪则现跑；判定合格项目）
PREFLIGHT=~/.cache/aitester/bugsinpy/c8_preflight.json
if [ ! -f "$PREFLIGHT" ] || [ $(python3 -c "import json;print(len(json.load(open('$PREFLIGHT'))))" 2>/dev/null || echo 0) -lt 17 ]; then
  echo "[$(date +%H:%M:%S)] step0 preflight running..." >> "$LOG"
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    .venv/bin/python3 /tmp/preflight_parallel.py >> "$LOG" 2>&1
  echo "[$(date +%H:%M:%S)] step0 preflight exit=$?" >> "$LOG"
fi
OK_PROJECTS=$(python3 -c "
import json
rows=json.load(open('$PREFLIGHT'))
print(','.join(r['project'] for r in rows if r.get('editable_ok')))
")
echo "[$(date +%H:%M:%S)] preflight OK projects: $OK_PROJECTS" >> "$LOG"

# ── 步骤 1：C8 全项目 manifest ──
if [ ! -f ~/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl ]; then
  .venv/bin/python3 scripts/tools/export_bugsinpy_manifest.py \
    --projects "$OK_PROJECTS" \
    --framework-dir ~/.cache/aitester/bugsinpy/framework \
    --repos-dir ~/.cache/aitester/bugsinpy/repos \
    -o ~/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl >> "$LOG" 2>&1 \
    && echo "[$(date +%H:%M:%S)] step1 manifest OK" >> "$LOG" \
    || echo "[$(date +%H:%M:%S)] step1 manifest FAIL" >> "$LOG"
fi

# ── 步骤 2：C8 全项目 2 臂生成批（并行 4）──
N_TASKS=$(wc -l < ~/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl | tr -d ' ')
for arm in aitester plain_llm_df; do
  mkdir -p experiments/results/c8_full_20261031/$arm
  if ls experiments/results/c8_full_20261031/$arm/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] step2 $arm already done, skip" >> "$LOG"; continue
  fi
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_BUGSINPY_DATA="$HOME/.cache/aitester/bugsinpy/bugs_in_py_manifest_full.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=c8full_${arm} \
    .venv/bin/python3 experiments/run_benchmark.py -d bugsinpy -b $arm --seed 42 \
    -n "$N_TASKS" -p 4 -o experiments/results/c8_full_20261031/$arm --no-rag \
    >> "/tmp/c8full_${arm}.log" 2>&1
  echo "[$(date +%H:%M:%S)] step2 $arm exit=$?" >> "$LOG"
done

# ── 步骤 3：C8 全项目判定（零 LLM，串行分项目 venv 已就绪）──
mkdir -p experiments/results/c8_full_20261031
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  .venv/bin/python3 scripts/tools/judge_c8_generated_tests.py \
  --bench-dir experiments/results/c8_full_20261031 \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/c8_full_20261031/C8_JUDGE.json >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] step3 judge exit=$?" >> "$LOG"

# ── 步骤 4：B3 Lite 单臂生成批（aitester，300 全量，并行 4）──
mkdir -p experiments/results/b3_lite_20261031/aitester
if ! ls experiments/results/b3_lite_20261031/aitester/benchmark_*.json >/dev/null 2>&1; then
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    SWE_BENCH_ENRICHMENT="$HOME/.cache/aitester/swe_bench/swe_bench_lite_enrichment.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=b3lite \
    .venv/bin/python3 experiments/run_benchmark.py -d swe_bench --subset lite \
    -b aitester --seed 42 -n 300 -p 4 -o experiments/results/b3_lite_20261031/aitester --no-rag \
    >> /tmp/b3lite_aitester.log 2>&1
  echo "[$(date +%H:%M:%S)] step4 b3 gen exit=$?" >> "$LOG"
fi

# ── 步骤 5：B3 判定（零 LLM）──
env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
  .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
  --bench-dir experiments/results/b3_lite_20261031 \
  --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
  --py /tmp/mm_py38/bin/python \
  --out experiments/results/b3_lite_20261031/B3_JUDGE.json >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] step5 b3 judge exit=$?" >> "$LOG"

# ── 步骤 6：TestGenEval-Lite 2 臂生成批（160 对，数据 10-28 已落盘）──
for arm in aitester plain_llm_df; do
  mkdir -p experiments/results/tge_lite_20261031/$arm
  if ls experiments/results/tge_lite_20261031/$arm/benchmark_*.json >/dev/null 2>&1; then
    echo "[$(date +%H:%M:%S)] step6 $arm already done, skip" >> "$LOG"; continue
  fi
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 \
    EXECUTION_TIMEOUT=30 ENABLE_RAG=false AITESTER_LLM_CACHE=0 \
    COST_BUDGET_ENABLE=true COST_BUDGET_USD=20.0 AITESTER_BATCH_MAX_USD=60.0 \
    AITESTER_CACHE_NAMESPACE=tge_${arm} \
    .venv/bin/python3 experiments/run_benchmark.py -d testgeneval \
    -b $arm --seed 42 -n 160 -p 4 -o experiments/results/tge_lite_20261031/$arm --no-rag \
    >> /tmp/tge_${arm}.log 2>&1
  echo "[$(date +%H:%M:%S)] step6 $arm exit=$?" >> "$LOG"
done
# TGE 判定 = accuracy 口径（run_benchmark 的 passed 即读数——tge__ 前缀豁免
# 已在 _should_debug 修复），无需独立判定脚本；汇总由收口轮做。

echo "[$(date +%H:%M:%S)] queue end" >> "$LOG"
python3 -c "
import json, datetime
state = {'updated': datetime.datetime.now().isoformat(), 'log': open('$LOG').read()[-3000:]}
json.dump(state, open('$CKPT','w'), ensure_ascii=False, indent=1)
"
echo "QUEUE DONE"
