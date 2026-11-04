#!/bin/bash
# G8 全栈复测——全量 178 任务（2026-11-01 用户指令：跑全量不抽 30）
# 预注册偏离：docs/preregistration_g8_fullstack_20261030.md 偏离表 D2（30 → 178 全池原序）
# 任务清单：~/.cache/aitester/swe_bench_pro/g8_full178/（178 行，enrichment_g8 全池原序冻结）
# 并发：--parallel 32（用户确认 DeepSeek 并发限额 2500）
# 判据：预注册冻结不变（M3 P2P 门禁 / REPO_LEVEL_EXECUTION / 四开关 off-on 唯一差异）
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OUT="$REPO/experiments/results/g8_fullstack_full178"
PY="$REPO/.venv/bin/python3"

ARM="${1:-}"
PAR="${G8_PARALLEL:-32}"
case "$ARM" in
  off|on) ;;
  *) echo "usage: $0 off|on   (env: G8_PARALLEL=32)" >&2; exit 64 ;;
esac
RUN="$OUT/$ARM"

# 幂等：已完成则拒绝重跑（防覆盖）
if [ -f "$RUN/RUN_SUMMARY.log" ]; then
  echo "REFUSE: $RUN/RUN_SUMMARY.log 已存在（该臂已完成）" >&2
  exit 2
fi
mkdir -p "$RUN"

cd "$REPO" || exit 3
# 干净树强制（真实模式纪律：dirty=0）
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "REFUSE: 工作树 dirty，拒绝真实跑批" >&2
  git status --porcelain --untracked-files=no >&2
  exit 3
fi

# ---- 公共口径（与 run_g8_resume_20261031.sh 同款）----
export AITESTER_PROFILE=logic
export TEMPERATURE=0.0

export EXECUTION_TIMEOUT=30
export LLM_TIMEOUT=60
export ENABLE_RAG=false
export AITESTER_LLM_CACHE=0
export ENABLE_PLANNER=true
export ENABLE_DEBUGGER=true
export ENABLE_MUTATION_SCORING=true
export MUTATION_ADVISOR_ENABLE=true
export COST_BUDGET_ENABLE=true
# 预算闸（178 任务上界：任务级 $1.0 不变；批次闸 $10——10 任务实测外推 + 上界余量，fail-closed）
export COST_BUDGET_USD=1.0
export AITESTER_BATCH_MAX_USD=10.0
# 数据目录：全量 178 任务（冻结清单）
export AITESTER_SWE_BENCH_PRO_DIR="$HOME/.cache/aitester/swe_bench_pro/g8_full178"
# 臂独立缓存命名空间
export AITESTER_CACHE_NAMESPACE="g8_${ARM}_full178_$(date +%s)"

# ---- G8 四开关：臂间唯一差异（显式导出）----
if [ "$ARM" = "on" ]; then
  export RUNTIME_PROBE_ENABLE=true
  export STRATEGY_BANK_ENABLE=true
  export EXPERT_POOL_ENABLE=true
  export CROSS_FILE_ENABLE=true
else
  export RUNTIME_PROBE_ENABLE=false
  export STRATEGY_BANK_ENABLE=false
  export EXPERT_POOL_ENABLE=false
  export CROSS_FILE_ENABLE=false
fi

echo "[g8-full178 $ARM] start $(date '+%F %T') sha=$(git rev-parse --short HEAD) parallel=$PAR"
exec "$PY" "$REPO/experiments/run_benchmark.py" \
  -d swe_bench_pro \
  -b aitester \
  --seed 42 \
  -n 178 \
  --parallel "$PAR" \
  -o "$RUN" \
  --no-rag
