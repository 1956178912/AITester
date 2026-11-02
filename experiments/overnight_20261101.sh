#!/bin/bash
# 过夜无人值守总控（2026-11-01 深夜，用户指令：能跑的过夜全部跑掉，超时跳过，无人重启）
#
# 覆盖范围（机器可跑项）：
#   Phase 1  G8 full178 on 臂续命（现有看护 LIMIT=150min 到限后接管，重试上限 3）
#            H1 三臂 + REF 臂（现有看护到限后接管，三臂重拉上限 2，REF 幂等）
#   Phase 2  B3 docker 判定 6 分片（3+3 两批，判定不烧 LLM，待 Phase 1 释放 CPU 后串行）
#            TGE-Lite 重判 2 臂（env_error 分层修复后的预期改善读数）
#   收尾     OVERNIGHT_REPORT.md
#
# 不覆盖（本质人工活/无入口，机器无法代办——见报告披露）：
#   E7 人工裁决 / B5 段落目检 / 投稿动作（人工）；G8 Docker per-instance（无现成入口，
#   不在无人值守时段现写不可验证代码）；N05/H1 原口径（已收口，无需跑）。
#
# 纪律：幂等（完成标志检测）/ 超时跳过（guarded_run deadline）/ 失败不阻塞 /
#       重试封顶（LLM 费用兜底：G8 批次闸 $10/次 × 重试上限）/ 全程落盘。
# 用法（Terminal 前台，防睡眠）：
#   caffeinate -is bash experiments/overnight_20261101.sh
# 可调 env：TOTAL_LIMIT_MIN（默认 660）、G8_ATTEMPTS（默认 3）、H1_ATTEMPTS（默认 2）
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OV="$REPO/experiments/results/overnight_20261101"
MG="$REPO/experiments/results/minimal_gen"
G8OUT="$REPO/experiments/results/g8_fullstack_full178"
H1OUT="$REPO/experiments/results/e3_h1_payload_r2"
SB="$HOME/.cache/aitester/swe_bench"
PY="$REPO/.venv/bin/python3"
TOTAL_LIMIT_MIN="${TOTAL_LIMIT_MIN:-660}"
G8_ATTEMPTS="${G8_ATTEMPTS:-3}"
H1_ATTEMPTS="${H1_ATTEMPTS:-2}"
START_TS=$(date +%s)

mkdir -p "$OV"
LOG="$OV/OVERNIGHT_LOG.txt"

# ---- 防总控自身重复启动 ----
if mkdir "$OV/.controller.lock" 2>/dev/null; then
  trap 'rmdir "$OV/.controller.lock" 2>/dev/null' EXIT
else
  echo "REFUSE: 过夜总控已在运行（$OV/.controller.lock 存在）" >&2
  exit 2
fi

log() { echo "[overnight $(date '+%F %T')] $*" >> "$LOG"; }
left_min() { echo $(( TOTAL_LIMIT_MIN - ($(date +%s) - START_TS) / 60 )); }

# guarded_run <log> <deadline_min> <cmd...>：前台语义跑命令，到 deadline 杀主进程返回 124
# 注意：已退出的后台子进程在 wait 收割前是 zombie，kill -0 仍返回成功——
# 必须配合 ps stat= 的 Z 状态检测，否则快速失败的命令会空等到 deadline。
guarded_run() {
  local logf="$1"; shift
  local dmin="$1"; shift
  local deadline=$(( $(date +%s) + dmin * 60 ))
  "$@" >> "$logf" 2>&1 &
  local pid=$!
  local st
  while kill -0 "$pid" 2>/dev/null; do
    st=$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ')
    if [ "$st" = "Z" ]; then
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      kill -TERM "$pid" 2>/dev/null
      sleep 10
      kill -9 "$pid" 2>/dev/null
      echo "[guarded] TIMEOUT after ${dmin}min" >> "$logf"
      log "TIMEOUT: ${dmin}min 到限，已跳过（log=${logf}）"
      wait "$pid" 2>/dev/null
      return 124
    fi
    sleep 20
  done
  wait "$pid"
  return $?
}

# wait_gone <egrep模式> <最长等待min>：等 pgrep -f 匹配的进程全部消失
wait_gone() {
  local pat="$1"
  local dmin="$2"
  local deadline=$(( $(date +%s) + dmin * 60 ))
  while pgrep -f "$pat" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      log "wait_gone 超时（${dmin}min）：$pat 仍在运行"
      return 124
    fi
    sleep 30
  done
  return 0
}

# ---------------- Track: G8 full178 on 臂 ----------------
# 2026-11-02 完成标志修正：增量模式（84899665）不写 RUN_SUMMARY.log，
# 以 INCREMENTAL_RESULTS.jsonl 行数 ≥178 为准
g8_arm_done() {
  local inc="$G8OUT/$1/INCREMENTAL_RESULTS.jsonl"
  [ -f "$inc" ] || return 1
  local n
  n=$(wc -l < "$inc" | tr -d ' ')
  [ "$n" -ge 178 ]
}

g8_on_track() {
  local run="$G8OUT/on"
  if g8_arm_done on; then
    log "G8 on 臂已完成（INCREMENTAL ≥178），跳过"
    return 0
  fi
  # 现有看护 LIMIT=150min（22:17 启动，约 00:47 到限）；等它的跑批进程消失
  log "G8 on：等待现有看护收尾（最长 170min）"
  wait_gone "run_benchmark.py.*full178/on" 170
  if g8_arm_done on; then
    log "G8 on 臂已完成（现有看护跑完）"
    return 0
  fi
  local attempt=1
  while [ $attempt -le "$G8_ATTEMPTS" ]; do
    if [ "$(left_min)" -lt 90 ]; then
      log "G8 on：总时限不足 90min，放弃剩余重试（attempt=${attempt}）"
      return 124
    fi
    log "G8 on：第 $attempt/$G8_ATTEMPTS 次接管启动（deadline 110min；注意批次闸 \$10 fail-closed 为预注册设计）"
    guarded_run "$OV/g8_on_attempt${attempt}.log" 110 bash "$REPO/experiments/run_g8_full178.sh" on
    if g8_arm_done on; then
      log "G8 on 臂完成（第 $attempt 次尝试）"
      return 0
    fi
    attempt=$((attempt + 1))
  done
  log "G8 on：重试 ${G8_ATTEMPTS} 次仍未完成，交人工（产物在 ${run}）"
  return 1
}

# ---------------- Track: H1 三臂 + REF ----------------
count_h1_arms() {
  local n=0
  local arm
  # 2026-11-02 完成标志修正：臂完成 = 臂目录有 INCREMENTAL_RESULTS.jsonl（run_payload_ab 整体完成另写 SHA256SUMS）
  for arm in p_df_parity__o_logic p_df_parity__o_mono p_full__o_logic; do
    if [ -f "$H1OUT/$arm/INCREMENTAL_RESULTS.jsonl" ]; then
      n=$((n + 1))
    fi
  done
  echo "$n"
}

h1_track() {
  # 现有看护 LIMIT=150min（22:18 启动）；三臂当前串行推进第一臂
  log "H1：等待现有看护收尾（最长 170min）"
  wait_gone "run_payload_ab.py.*confirm-budget" 170
  local n_ok
  n_ok=$(count_h1_arms)
  if [ "$n_ok" -lt 3 ]; then
    local attempt=1
    while [ $attempt -le "$H1_ATTEMPTS" ] && [ "$(count_h1_arms)" -lt 3 ]; do
      if [ "$(left_min)" -lt 100 ]; then
        log "H1 三臂：总时限不足 100min，放弃剩余重试"
        break
      fi
      log "H1 三臂：缺 $((3 - $(count_h1_arms))) 臂，第 $attempt/$H1_ATTEMPTS 次重拉（deadline 150min）"
      guarded_run "$OV/h1_arms_attempt${attempt}.log" 150 \
        env BENCHMARK_PARALLELISM=16 "$PY" "$REPO/experiments/run_payload_ab.py" --confirm-budget --out-dir "$H1OUT"
      attempt=$((attempt + 1))
    done
  else
    log "H1 三臂已完成（3/3）"
  fi
  # REF 臂重建（幂等：脚本自带 REFUSE）
  # 2026-11-02 完成标志修正：REF 完成 = ref_df_stored/INCREMENTAL_RESULTS.jsonl 存在
  if [ -f "$H1OUT/ref_df_stored/INCREMENTAL_RESULTS.jsonl" ]; then
    log "H1 REF 臂已完成，跳过"
    return 0
  fi
  if [ "$(left_min)" -lt 70 ]; then
    log "H1 REF：总时限不足 70min，跳过"
    return 124
  fi
  log "H1 REF 臂启动（deadline 90min，quixbugs 50 单元 plain_llm_df）"
  guarded_run "$OV/h1_ref.log" 90 bash "$REPO/experiments/run_h1_ref_20261101.sh"
  if [ -f "$H1OUT/ref_df_stored/INCREMENTAL_RESULTS.jsonl" ]; then
    log "H1 REF 臂完成"
    return 0
  fi
  log "H1 REF 臂未完成（超时或失败），交人工"
  return 1
}

# ---------------- Track: B3 docker 判定（Phase 2）----------------
b3_track() {
  # 2026-11-02 修正：judge_one 期望 inst["repo"]/["base_commit"]——enrich 版无此字段，
  # 必须用 b3_shard*（与 manifest 300 任务全对齐实证）
  local inst_all="$OV/b3_instances_shard_all.jsonl"
  if ! cat "$SB"/b3_shard*.jsonl > "$inst_all" 2>/dev/null; then
    log "B3：instances（b3_shard*）缺失，跳过"
    return 1
  fi
  if [ "$(left_min)" -lt 150 ]; then
    log "B3：总时限不足 150min，跳过"
    return 124
  fi
  local s
  # 第一批 s1-s3 并行：bash -c 内部 wait 等全部子 shell，外层 guarded_run 管总 deadline
  log "B3 docker：第一批 s1-s3 已并行（deadline 130min）"
  guarded_run "$OV/b3_batch1.log" 130 bash -c '
    for s in 1 2 3; do
      ("$1" "$2/scripts/tools/judge_b3_docker.py" --manifest "$3/b3_s${s}.jsonl" \
        --instances "$4" --out "$5/B3_DOCKER_s${s}.json" >> "$5/b3_s${s}.log" 2>&1) &
    done
    wait
  ' _ "$PY" "$REPO" "$MG" "$inst_all" "$OV"
  # 第二批 s4-s6
  log "B3 docker：第二批 s4-s6 已并行（deadline 130min）"
  guarded_run "$OV/b3_batch2.log" 130 bash -c '
    for s in 4 5 6; do
      ("$1" "$2/scripts/tools/judge_b3_docker.py" --manifest "$3/b3_s${s}.jsonl" \
        --instances "$4" --out "$5/B3_DOCKER_s${s}.json" >> "$5/b3_s${s}.log" 2>&1) &
    done
    wait
  ' _ "$PY" "$REPO" "$MG" "$inst_all" "$OV"
  local done_n=0
  for s in 1 2 3 4 5 6; do
    if [ -f "$OV/B3_DOCKER_s${s}.json" ]; then
      done_n=$((done_n + 1))
    fi
  done
  log "B3 docker：$done_n/6 分片产出落盘（$OV/B3_DOCKER_s*.json）"
  return 0
}

# ---------------- Track: TGE 重判（Phase 2）----------------
tge_track() {
  if [ "$(left_min)" -lt 100 ]; then
    log "TGE：总时限不足 100min，跳过"
    return 124
  fi
  log "TGE 重判：2 臂启动（deadline 90min）"
  # 2026-11-02 修正：judge_tge_accuracy 必需 --arm（aitester/plain_llm_df，用于 venv 命名）
  guarded_run "$OV/tge_batch.log" 90 bash -c '
    ("$1" "$2/scripts/tools/judge_tge_accuracy.py" \
      --manifest "$3/tge_aitester.jsonl" --arm aitester --py "$1" \
      --out "$4/TGE_ACC_aitester_r2.json" >> "$4/tge_aitester.log" 2>&1) &
    ("$1" "$2/scripts/tools/judge_tge_accuracy.py" \
      --manifest "$3/tge_plain_llm_df.jsonl" --arm plain_llm_df --py "$1" \
      --out "$4/TGE_ACC_df_r2.json" >> "$4/tge_df.log" 2>&1) &
    wait
  ' _ "$PY" "$REPO" "$MG" "$OV"
  if [ -f "$OV/TGE_ACC_aitester_r2.json" ] && [ -f "$OV/TGE_ACC_df_r2.json" ]; then
    log "TGE 重判：双臂产物落盘"
    return 0
  fi
  log "TGE 重判：部分/全部未产出，交人工（log=$OV/tge_*.log）"
  return 1
}

# ---------------- 主流程 ----------------
log "=== 过夜总控启动：总时限 ${TOTAL_LIMIT_MIN}min，G8 重试上限 ${G8_ATTEMPTS}，H1 重试上限 ${H1_ATTEMPTS} ==="
log "Phase 1（LLM 批次）：G8 on 接管 + H1 三臂/REF 并行协调"

g8_on_track &
G8_PID=$!
h1_track &
H1_PID=$!
wait "$G8_PID"; G8_RC=$?
wait "$H1_PID"; H1_RC=$?
log "Phase 1 收尾：G8_on rc=${G8_RC}，H1 rc=${H1_RC}，剩余 $(left_min)min"

log "Phase 2（判定批次）：B3 docker + TGE 重判（判定不烧 LLM，待 CPU 释放）"
b3_track
B3_RC=$?
tge_track
TGE_RC=$?
log "Phase 2 收尾：B3 rc=${B3_RC}，TGE rc=${TGE_RC}，剩余 $(left_min)min"

# ---------------- 收尾报告 ----------------
REPORT="$OV/OVERNIGHT_REPORT.md"
n_b3=$(ls "$OV"/B3_DOCKER_s*.json 2>/dev/null | wc -l | tr -d ' ')
{
  echo "# 过夜无人值守报告（$(date '+%F %T')）"
  echo
  echo "| Track | 结果 | 产物/日志 |"
  echo "|---|---|---|"
  echo "| G8 full178 on 臂 | rc=${G8_RC}（0=完成 124=超时跳过 1=重试耗尽） | $G8OUT/on/RUN_SUMMARY.log；尝试日志 $OV/g8_on_attempt*.log |"
  echo "| H1 三臂+REF | rc=$H1_RC | $H1OUT/*/RUN_SUMMARY.log；$OV/h1_*.log |"
  echo "| B3 docker 判定 | rc=${B3_RC}，产出 ${n_b3}/6 分片 | $OV/B3_DOCKER_s*.json；$OV/b3_s*.log |"
  echo "| TGE 重判 | rc=$TGE_RC | $OV/TGE_ACC_*_r2.json；$OV/tge_*.log |"
  echo
  echo "## 未覆盖项（机器无法代办）"
  echo "- E7 人工裁决 / B5 段落目检 / 投稿动作：人工活，无人值守不可代办"
  echo "- G8 Docker per-instance（30 任务）：无现成入口脚本，未现写不可验证代码"
  echo "- N05/H1 原口径：已于 e8-2x2 收口（δ=+27.78pp），无需重跑"
  echo
  echo "## 已知设计内约束（非故障）"
  echo "- G8 批次预算闸 \$10 fail-closed：178 任务可能中途截断（预注册口径，重启即重置计数）"
  echo "- run_benchmark.py 已有增量断点续跑（84899665）：重拉只补未完成任务，不整批重来"
  echo "- B3/TGE 判定为 docker/Rosetta x86 通道，env_error 结构性残留会在 verdict 中披露"
} > "$REPORT"
log "=== 过夜总控结束，报告：$REPORT ==="
