#!/usr/bin/env bash
# b3_queue.sh — 流 B：B3 Lite 生成 + 判定（与流 A 的 df/TGE 并行）
#
# 2026-11-02 事故修复（实测 6425 次重启 / 983 个孤儿判定进程 / load 737）：
#   本脚本是一次性批处理，却被 launchd 以 KeepAlive=true 托管（com.aitester.queueB），
#   正常退出即被重拉；而判定步骤不幂等，每轮重拉都新起全量判定进程并互写同一 out。
#   两道防护：① 重入锁（并发实例直接退出）② 完成标记（跑过即退出，需重跑手工删标记）。
#   仍须配合 plist 的 KeepAlive=false；锁只兜底，不替代正确调度。
set -u
export HOME=/Users/wangchenyu
cd /Users/wangchenyu/Workspace/AITester
LOG=/tmp/b3_queue.log

DONE_MARK=experiments/results/b3_lite_20261031/QUEUE_DONE.marker
if [ -f "$DONE_MARK" ]; then
  echo "[$(date +%H:%M:%S)] done marker present, skip (rm ${DONE_MARK} to rerun)" >> "$LOG"
  exit 0
fi
LOCK=/tmp/b3_queue.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[$(date +%H:%M:%S)] another instance holds ${LOCK}, exit" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
echo "[$(date +%H:%M:%S)] b3 stream start" >> "$LOG"

# 步骤 B1：B3 Lite aitester 单臂生成（300 任务，-p 1 串行稳定口径）
mkdir -p experiments/results/b3_lite_20261031/aitester
if ! ls experiments/results/b3_lite_20261031/aitester/benchmark_*.json >/dev/null 2>&1; then
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    SWE_BENCH_ENRICHMENT="$HOME/.cache/aitester/swe_bench/swe_bench_lite_enrichment.jsonl" \
    AITESTER_PROFILE=logic TEMPERATURE=0.0 MAX_ITERATIONS=3 \
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
# 读数口径警告：本通道（repo 级 py3.8 venv）已被 judge_b3_docker_v2.py 取代——
# 官方 docker 环境读数见 overnight_20261101/V2_B3_DOCKER_s*.json（222 red + 78 env_error）；
# 本通道 env_error 占比实测 30%~100%，只能作流水自检，不得作 B3 读数来源。
B3_JUDGE_OUT=experiments/results/b3_lite_20261031/B3_JUDGE.json
JUDGE_RC=1
if [ -f "$B3_JUDGE_OUT" ]; then
  echo "[$(date +%H:%M:%S)] B2 judge output exists, skip" >> "$LOG"
  JUDGE_RC=0
else
  env -u CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS -u CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    .venv/bin/python3 scripts/tools/judge_swebench_generated_tests.py \
    --bench-dir experiments/results/b3_lite_20261031 \
    --instances ~/.cache/aitester/swe_bench/swe_bench_lite_instances.jsonl \
    --py /tmp/mm_py38/bin/python \
    --out "$B3_JUDGE_OUT" >> "$LOG" 2>&1
  JUDGE_RC=$?
  echo "[$(date +%H:%M:%S)] B2 b3 judge exit=${JUDGE_RC}" >> "$LOG"
fi
echo "[$(date +%H:%M:%S)] b3 stream end" >> "$LOG"
# 仅当判定真正成功才落完成标记：失败保留可重跑路径
if [ "$JUDGE_RC" -eq 0 ]; then
  : > "$DONE_MARK"
  echo "[$(date +%H:%M:%S)] done marker written: ${DONE_MARK}" >> "$LOG"
fi
echo "B3 STREAM DONE"
