#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# E8 剩余格 + ULT 200 定标：顺序编排（2026-10-28 用户授权配额批）
#
# 顺序（预注册纪律：固定顺序，不按结果择序；失败如实记录、不重跑）：
#   0. 等 current-off（另一进程）完成或 45 分钟超时
#   1. E8 current-on  （a93c1f60 + LLM_THINKING_MODE=enabled）
#   2. E8 legacy-on   （b533cff1 默认推理口径）
#   3. ULT 200 定标   （HEAD worktree，plain_llm_df 臂，accuracy 判定用）
# 每步退出码与工件目录逐一登记到 STEP_LOG；任一步失败继续下一步（披露式）。
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO=/Users/wangchenyu/Workspace/AITester
E8ROOT_CUR=/Users/wangchenyu/Workspace/AITester-e8-current-a93c1f6
E8ROOT_LEG=/Users/wangchenyu/Workspace/AITester-e8-legacy-b533cff
WHEAD=/Users/wangchenyu/Workspace/AITester-w-head
RES="${REPO}/experiments/results/e8_2x2_20261028"
LOG="${RES}/REMAINING_RUN.log"
CUR_SHA="$(git -C "$SCRIPT_REPO" rev-parse a93c1f60)"
LEG_SHA="$(git -C "$SCRIPT_REPO" rev-parse b533cff1)"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "${LOG}"; }

# ── 步 0：等 current-off 完成（RUN_SUMMARY.log 含 RUN_COMPLETE）或超时 ──────
log "步0：等待 current-off 完成（上限 45 分钟）"
DEADLINE=$(( $(date +%s) + 45 * 60 ))
while [ "$(date +%s)" -lt "${DEADLINE}" ]; do
    if grep -q "RUN_COMPLETE_UTC" "${RES}/current-off/RUN_SUMMARY.log" 2>/dev/null; then
        log "步0：current-off 已完成"
        break
    fi
    sleep 60
done
if ! grep -q "RUN_COMPLETE_UTC" "${RES}/current-off/RUN_SUMMARY.log" 2>/dev/null; then
    log "步0：⚠️ current-off 45 分钟未完成（仍在跑或挂死）——按顺序继续 current-on（并行风险自担披露）"
fi

# ── 步 1：E8 current-on ──────────────────────────────────────────────────────
log "步1：启动 E8 current-on"
bash "${REPO}/experiments/run_e8_cell.sh" \
    --root "${E8ROOT_CUR}" --expect-sha "${CUR_SHA}" \
    --thinking enabled \
    --out "${RES}/current-on" \
    --budget-usd 4.5 --ref-tokens 7000000 \
    >> "${LOG}" 2>&1
log "步1：current-on 退出码=$?"

# ── 步 2：E8 legacy-on ───────────────────────────────────────────────────────
log "步2：启动 E8 legacy-on"
bash "${REPO}/experiments/run_e8_cell.sh" \
    --root "${E8ROOT_LEG}" --expect-sha "${LEG_SHA}" \
    --thinking legacy-default \
    --out "${RES}/legacy-on" \
    --budget-usd 4.5 --ref-tokens 7000000 \
    >> "${LOG}" 2>&1
log "步2：legacy-on 退出码=$?"

# ── 步 3：ULT 200 定标（plain_llm_df 臂，accuracy 判定料）────────────────────
log "步3：启动 ULT 200 定标（HEAD worktree，df 臂）"
(
    cd "${WHEAD}" && env \
        AITESTER_ULT_DATA="${HOME}/.cache/aitester/ult_repo/datasets" \
        AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
        MAX_ITERATIONS=3 LLM_TIMEOUT=60 EXECUTION_TIMEOUT=30 \
        ENABLE_PLANNER=true ENABLE_DEBUGGER=true ENABLE_RAG=false \
        BENCHMARK_PARALLELISM=4 AITESTER_LLM_CACHE=0 \
        AITESTER_CACHE_NAMESPACE=ult200_calib_20261028 \
        AITESTER_TRACE_DIR="${WHEAD}/experiments/results/ult200_calib_20261028/traces" \
        COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=150000 COST_BUDGET_USD=0.5 \
        AITESTER_BATCH_MAX_CALLS=3000 AITESTER_BATCH_MAX_USD=4.0 \
        AITESTER_RUN_PREFLIGHT=true \
        "${REPO}/.venv/bin/python" -m experiments.run_benchmark \
        --dataset ult --subset lite \
        --baselines plain_llm_df \
        --output-dir experiments/results/ult200_calib_20261028 \
        --parallel 4
) >> "${LOG}" 2>&1
log "步3：ULT 200 定标退出码=$?"

log "全部顺序步完成（各步退出码与 GATE 见 ${RES}/ 与 ult200_calib_20261028/）"
