#!/bin/bash
# G8 门禁 + B3 v2 重判接力（2026-11-02 晨）
#
# 排队原因与顺序：
#   1. B3 v2 重判（daypatch 的 B3 判定批报废：judge_b3_docker line build 用 shell 单引号
#      传 environment-marker 依赖 → 嵌套引号断裂 → 全 env_error，s2 50/50 实证）。
#      v2 = 克隆修复版（reqs 传容器内文件，pip -r 自解析 markers），不动跟踪文件
#      （off 臂看护依赖干净树，judge_b3_docker.py 属跟踪文件）。
#   2. G8 per-instance 门禁验证（full178 两臂 effective=0，三 repo smoke 全 harness_valid）。
#   两者均不烧 LLM。等待 daypatch 判定进程消失（上限 6h）后自动接力。
# 用法：bash experiments/g8_gate_relay_20261102.sh
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OV="$REPO/experiments/results/overnight_20261101"
MG="$REPO/experiments/results/minimal_gen"
PY="$REPO/.venv/bin/python3"
B3V2="$REPO/scripts/tools/judge_b3_docker_v2.py"
G8J="$REPO/scripts/tools/judge_g8_docker.py"
mkdir -p "$OV"
LOG="$OV/G8_GATE_RELAY_LOG.txt"
log() { echo "[relay $(date '+%F %T')] $*" >> "$LOG"; echo "[relay $(date '+%F %T')] $*"; }

log "等待 daypatch 判定批结束（judge_b3/judge_tge 进程消失，上限 6h）"
deadline=$(( $(date +%s) + 21600 ))
while pgrep -f "judge_b3_docker.py|judge_tge_accuracy.py" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "等待超时——强制接力（docker 资源争抢风险披露）"
    break
  fi
  sleep 120
done
log "判定批已收尾（或超时放行），接力启动"

# ---- 段 1：B3 v2 重判（六分片 3+3，产出 V2_B3_DOCKER_s*.json）----
log "B3 v2 重判：第一批 s1-s3（deadline 130min）"
for s in 1 2 3; do
  ("$PY" "$B3V2" --manifest "$MG/b3_s${s}.jsonl" \
    --instances "$OV/b3_instances_shard_all.jsonl" \
    --out "$OV/V2_B3_DOCKER_s${s}.json" >> "$OV/v2_b3_s${s}.log" 2>&1) &
done
wait
log "B3 v2 第一批收尾；第二批 s4-s6 启动"
for s in 4 5 6; do
  ("$PY" "$B3V2" --manifest "$MG/b3_s${s}.jsonl" \
    --instances "$OV/b3_instances_shard_all.jsonl" \
    --out "$OV/V2_B3_DOCKER_s${s}.json" >> "$OV/v2_b3_s${s}.log" 2>&1) &
done
wait
n_b3=$(ls "$OV"/V2_B3_DOCKER_s*.json 2>/dev/null | wc -l | tr -d ' ')
log "B3 v2 重判收尾：${n_b3}/6 分片产出"

# ---- 段 2：G8 per-instance 门禁验证（3 repo 并行，178 任务）----
log "G8 门禁全量启动：3 repo 并行"
for repo in ansible openlibrary qutebrowser; do
  ("$PY" "$G8J" --repo "$repo" --tag "$repo" \
    --out "$OV/G8_GATE_DOCKER_${repo}.json" >> "$OV/g8_gate_${repo}.log" 2>&1) &
done
wait

# daemon 残留收尾（上限 4h）
dl=$(( $(date +%s) + 14400 ))
while pgrep -f "judge_g8_docker.py|judge_b3_docker_v2.py" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$dl" ]; then log "残留进程等待超时（4h），以落盘文件为准"; break; fi
  sleep 120
done
n_g8=0
for repo in ansible openlibrary qutebrowser; do
  [ -f "$OV/G8_GATE_DOCKER_${repo}.json" ] && n_g8=$((n_g8+1))
done
log "=== 接力全部收尾：B3 v2 ${n_b3}/6 分片，G8 门禁 ${n_g8}/3 repo（$OV/V2_B3_DOCKER_*.json + G8_GATE_DOCKER_*.json）==="
