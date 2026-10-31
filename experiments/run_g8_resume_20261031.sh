#!/bin/bash
# G8 全开链路复测——恢复重跑 runner（2026-10-31）
#
# 背景：2026-10-30 主批（g8_fullstack_20261030/）两臂 exit=1，中断点为
# 沙箱 safe-delete broker 守卫拦截 repo_env/openlibrary 大批量清理
# （SAFE_DELETE_BULK_CONFIRM_REQUIRED，1747 文件 > 阈值 50）。
# 修复：① 启动时禁 broker env（与全量 pytest 同款纪律）；
#       ② repo_envs/openlibrary 已隔离至 repo_envs_quarantine_20261031/。
#
# 口径：预注册 docs/preregistration_g8_fullstack_20261030.md 冻结判据；
# 环境逐键复刻 10-30 off 臂 provenance.env_snapshot（115 键），仅修正
# "四 G8 开关未显式导出"缺陷（上次快照为 None，靠代码默认）。
# 任务集：复用 g8_ready10/（10-30 已物化的 10 个就绪任务）——偏离表
# 登记：主批规模 10（预注册 30），原因=30 任务选样规则未冻结 + 中断
# 恢复以完成既有任务集为先。
#
# 用法：run_g8_resume_20261031.sh off|on   （先 off 后 on，串行同代码态）
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OUT="$REPO/experiments/results/g8_fullstack_20261031"
PY="$REPO/.venv/bin/python3"

ARM="${1:-}"
case "$ARM" in
  off|on) ;;
  *) echo "usage: $0 off|on" >&2; exit 64 ;;
esac
RUN="$OUT/$ARM"

# 幂等：已完成则拒绝重跑（防覆盖，E8 runner 同款纪律）
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

# ---- 公共口径（复刻 10-30 provenance.env_snapshot 非 None 键）----
export AITESTER_PROFILE=logic
export TEMPERATURE=0.0
export LLM_THINKING_MODE=disabled
export MAX_ITERATIONS=3
export EXECUTION_TIMEOUT=30
export LLM_TIMEOUT=60
export ENABLE_RAG=false
export AITESTER_LLM_CACHE=0
export ENABLE_PLANNER=true
export ENABLE_DEBUGGER=true
export ENABLE_MUTATION_SCORING=true
export MUTATION_ADVISOR_ENABLE=true
export COST_BUDGET_ENABLE=true
# 预注册预算闸（fail-closed；禁止 --allow-over-budget 豁免）
export COST_BUDGET_USD=1.0
export AITESTER_BATCH_MAX_USD=6.0
# 数据目录：复用 10-30 主批物化任务集
export AITESTER_SWE_BENCH_PRO_DIR="$HOME/.cache/aitester/swe_bench_pro/g8_ready10"
# 臂独立缓存命名空间
export AITESTER_CACHE_NAMESPACE="g8_${ARM}_resume_$(date +%s)"

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

echo "[g8-resume $ARM] start $(date '+%F %T')"
echo "[g8-resume $ARM] sha=$(git rev-parse HEAD)"
echo "[g8-resume $ARM] out=$RUN"

exec "$PY" "$REPO/experiments/run_benchmark.py" \
  -d swe_bench_pro \
  -b aitester \
  --seed 42 \
  -n 10 \
  -o "$RUN" \
  --no-rag
