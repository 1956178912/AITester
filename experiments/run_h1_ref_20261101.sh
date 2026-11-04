#!/bin/bash
# H1 修订版 REF 臂——plain_llm_df 单臂复刻（当前快照，2026-11-01）
# 判据：docs/design/payload_equivalence_prereg_amendment_20261101.md（冻结）
set -u
REPO="/Users/wangchenyu/Workspace/AITester"
OUT="$REPO/experiments/results/e3_h1_payload_r2/ref_df_stored"
RUN="$OUT"

if [ -f "$RUN/RUN_SUMMARY.log" ]; then echo "REFUSE: 已完成" >&2; exit 2; fi
mkdir -p "$RUN"
cd "$REPO" || exit 3
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "REFUSE: 工作树 dirty" >&2; exit 3
fi

export AITESTER_PROFILE=logic
export TEMPERATURE=0.0

export AITESTER_LLM_CACHE=0
export ENABLE_MUTATION_SCORING=false
export MUTATION_ADVISOR_ENABLE=false
export COST_BUDGET_ENABLE=true
export COST_BUDGET_USD=1.0
export AITESTER_BATCH_MAX_USD=3.0
export AITESTER_CACHE_NAMESPACE="h1_ref_r2_$(date +%s)"

echo "[h1-ref] start $(date '+%F %T') sha=$(git rev-parse --short HEAD)"
exec "$REPO/.venv/bin/python3" "$REPO/experiments/run_benchmark.py" \
  -d quixbugs -b plain_llm_df --seed 42 -n 50 \
  --parallel "${H1_PARALLEL:-16}" \
  -o "$RUN" --no-rag
