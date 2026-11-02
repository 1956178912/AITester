#!/bin/bash
# 白班判定补跑（2026-11-02 晨）——修复夜间总控两处调用错误后的 B3 docker + TGE 重判
#
# 夜间失败归因（OVERNIGHT_LOG 03:41）：
#   B3: KeyError 'repo' —— instances 误用 b3_enrich_shard*（无 repo/base_commit 字段）
#       正确输入 = b3_shard*.jsonl（与 manifest 300 任务全对齐，2026-11-02 实证）
#   TGE: judge_tge_accuracy.py 必需 --arm（用于判定 venv 命名），夜间调用缺失
#
# 纪律：判定不烧 LLM；先等 G8 off 臂收尾（避免与 EXECUTION_TIMEOUT=30s 抢 CPU
#       污染正式读数），等待上限 90min，超时披露后继续。
# 用法：bash experiments/daypatch_b3_tge_20261102.sh   （前台；判定进程可能
#       daemonize，脚本会轮询等待，终端可 Ctrl-C 但判定会继续在后台收尾）
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OV="$REPO/experiments/results/overnight_20261101"
MG="$REPO/experiments/results/minimal_gen"
SB="$HOME/.cache/aitester/swe_bench"
PY="$REPO/.venv/bin/python3"
mkdir -p "$OV"
LOG="$OV/DAYPATCH_LOG.txt"

log() { echo "[daypatch $(date '+%F %T')] $*" >> "$LOG"; echo "[daypatch $(date '+%F %T')] $*"; }

# ---- 等 G8 off 收尾（最长 90min）----
log "等待 G8 off 臂收尾（最长 90min）"
deadline=$(( $(date +%s) + 5400 ))
while pgrep -f "run_benchmark.py.*full178/off" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "等待超时：off 臂仍在跑——继续判定（CPU 争抢风险披露：off 剩余任务的 30s 执行超时读数可能受扰）"
    break
  fi
  sleep 60
done
log "off 臂已收尾（或超时放行），启动判定补跑"

# ---- 等判定进程全部消失的通用轮询 ----
wait_judges() {
  local dmin="$1"
  local dl=$(( $(date +%s) + dmin * 60 ))
  while pgrep -f "judge_b3_docker.py|judge_tge_accuracy.py" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$dl" ]; then
      log "判定进程等待 ${dmin}min 超时——daemon 可能仍在后台，产物以落盘文件为准"
      return 124
    fi
    sleep 60
  done
  return 0
}

# ---- B3 docker：6 分片 3+3 ----
inst_all="$OV/b3_instances_shard_all.jsonl"
cat "$SB"/b3_shard*.jsonl > "$inst_all" || { log "FATAL: b3_shard* 缺失"; exit 3; }
log "B3 instances 合并完成：$(wc -l < "$inst_all" | tr -d ' ') 行"

log "B3 第一批 s1-s3 启动（deadline 130min）"
for s in 1 2 3; do
  ("$PY" "$REPO/scripts/tools/judge_b3_docker.py" --manifest "$MG/b3_s${s}.jsonl" \
    --instances "$inst_all" --out "$OV/DAYPATCH_B3_s${s}.json" \
    >> "$OV/daypatch_b3_s${s}.log" 2>&1) &
done
wait
wait_judges 130
log "B3 第一批收尾"

log "B3 第二批 s4-s6 启动（deadline 130min）"
for s in 4 5 6; do
  ("$PY" "$REPO/scripts/tools/judge_b3_docker.py" --manifest "$MG/b3_s${s}.jsonl" \
    --instances "$inst_all" --out "$OV/DAYPATCH_B3_s${s}.json" \
    >> "$OV/daypatch_b3_s${s}.log" 2>&1) &
done
wait
wait_judges 130
n_b3=$(ls "$OV"/DAYPATCH_B3_s*.json 2>/dev/null | wc -l | tr -d ' ')
log "B3 全部收尾：${n_b3}/6 分片产出"

# ---- TGE 重判：2 臂 ----
log "TGE 双臂启动（deadline 90min）"
("$PY" "$REPO/scripts/tools/judge_tge_accuracy.py" --manifest "$MG/tge_aitester.jsonl" \
  --arm aitester --py "$PY" --out "$OV/DAYPATCH_TGE_ACC_aitester.json" \
  >> "$OV/daypatch_tge_aitester.log" 2>&1) &
("$PY" "$REPO/scripts/tools/judge_tge_accuracy.py" --manifest "$MG/tge_plain_llm_df.jsonl" \
  --arm plain_llm_df --py "$PY" --out "$OV/DAYPATCH_TGE_ACC_df.json" \
  >> "$OV/daypatch_tge_df.log" 2>&1) &
wait
wait_judges 90

# ---- 收尾 ----
tge_ok=0
[ -f "$OV/DAYPATCH_TGE_ACC_aitester.json" ] && tge_ok=$((tge_ok+1))
[ -f "$OV/DAYPATCH_TGE_ACC_df.json" ] && tge_ok=$((tge_ok+1))
log "=== 白班补跑结束：B3 ${n_b3}/6 分片，TGE ${tge_ok}/2 臂（DAYPATCH_*.json @ ${OV}）==="
