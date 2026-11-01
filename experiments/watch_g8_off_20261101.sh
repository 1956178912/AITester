#!/bin/bash
# G8 off 臂看护程序（2026-11-01）
# 背景：off 臂跑到 177/178 时最后一个任务卡死过久，被用户强制关闭。
#       run_benchmark.py 无断点续跑（无 checkpoint），重启即整批重来（一批约 60-80 分钟）。
#       看护策略 = stall 即整组击杀 + 自动重启，次数/总时限封顶，超限交人工。
#
# 用法（Terminal 前台）:
#   bash experiments/watch_g8_off_20261101.sh            # 正式跑（on 臂在跑时自动等待）
#   bash experiments/watch_g8_off_20261101.sh --selftest # 验证启动封装/PGID 击杀/wait 退出码
#   G8_ALLOW_CONCURRENT=1 bash ...                       # 允许与 on 臂并行（默认禁止，fail-closed）
#   STALL_MIN=10 LIMIT_MIN=270 MAX_ATTEMPTS=3 POLL_SEC=30 均可用 env 覆盖
set -u

REPO="/Users/wangchenyu/Workspace/AITester"
OUT="$REPO/experiments/results/g8_fullstack_full178"
ARM="off"
RUN="$OUT/$ARM"
LOG="$RUN/WATCHDOG_LOG.txt"
RUNNER="${G8_WATCHDOG_RUNNER:-experiments/run_g8_full178.sh}"
ON_PAT="g8_fullstack_full178/on"
OFF_PAT="g8_fullstack_full178/off"

STALL_MIN="${STALL_MIN:-10}"
LIMIT_MIN="${LIMIT_MIN:-270}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
POLL_SEC="${POLL_SEC:-30}"
REPORT_EVERY="${REPORT_EVERY:-8}"   # 每 N 次 poll 打一条心跳（默认 4 分钟）
G8_ALLOW_CONCURRENT="${G8_ALLOW_CONCURRENT:-0}"

mkdir -p "$RUN"
log() { echo "[watchdog $(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ---- 防自身重复启动 ----
LOCK="$RUN/watchdog.lock"
if mkdir "$LOCK" 2>/dev/null; then
  trap 'rmdir "$LOCK" 2>/dev/null' EXIT
else
  log "REFUSE: 已有看护在运行（$LOCK 存在）"; exit 2
fi

# ---- 跑批进程组封装：独立会话（os.setsid）⇒ PGID=PID，可整组击杀 ----
# 注意：必须直接后台化 python 本体（heredoc 后 &），不得经函数中转——
# 函数 & 会插入一层子 shell，$! 拿到的是子 shell PID 而非 setsid 组长 PID，
# 击杀信号将打偏（真跑批组孤儿化存活），wait 亦会阻塞在非子进程 PID 上。
launch_batch() {  # $1=进度日志路径；产生新进程组，$! = 组长 PID
  python3 - "$REPO" "$RUNNER" "$ARM" <<'PYEOF' >> "$1" 2>&1 &
import os, sys
repo, runner, arm = sys.argv[1], sys.argv[2], sys.argv[3]
os.setsid()
os.chdir(repo)
os.execvp("bash", ["bash", runner, arm])
PYEOF
}

# ---- --selftest：验证 setsid 封装 + PGID 击杀 + wait 退出码 ----
if [ "${1:-}" = "--selftest" ]; then
  STAMP="$RUN/.selftest_prog.log"
  python3 -c 'import os,time; os.setsid(); print("selftest alive", flush=True); time.sleep(600)' >> "$STAMP" 2>&1 &
  spid=$!
  sleep 2
  if ! kill -0 "$spid" 2>/dev/null; then echo "SELFTEST FAIL: 进程未存活"; exit 1; fi
  kill -TERM -- "-$spid" 2>/dev/null
  wait "$spid"; rc=$?
  if [ "$rc" -eq 143 ] || [ "$rc" -eq 137 ]; then
    echo "SELFTEST PASS: PGID=$spid 整组击杀生效，wait rc=$rc"; exit 0
  fi
  echo "SELFTEST FAIL: wait rc=$rc（期望 143/137）"; exit 1
fi

log "======== G8 off 臂看护启动（STALL=${STALL_MIN}min LIMIT=${LIMIT_MIN}min ATTEMPTS=${MAX_ATTEMPTS}）========"
log "事故背景: off 臂 177/178 卡死被强杀；无断点续跑，stall 即整批重启"

# ---- fail-closed：on 臂在跑则等待（进程存活 或 其 WATCHDOG_LOG 5 分钟内有心跳）----
wait_on_arm() {
  pgrep -f "$ON_PAT" >/dev/null 2>&1 && return 0
  find "$OUT/on" -type f -name 'WATCHDOG_LOG.txt' -newermt '-5 minutes' 2>/dev/null | grep -q . && return 0
  return 1
}
if [ "$G8_ALLOW_CONCURRENT" != "1" ] && wait_on_arm; then
  log "on 臂仍在跑（或其看护 5 分钟内有心跳），等待其退出后自动开始 off 臂"
  log "如需并行: G8_ALLOW_CONCURRENT=1 重启本看护（注意两臂共享 repo_envs，不建议）"
  while wait_on_arm; do sleep 60; done
  log "on 臂已退出，开始 off 臂"
fi

# ---- 残留 off 进程清理（精确路径匹配，不伤 on 臂/H1/其他实验）----
if pgrep -f "$OFF_PAT" >/dev/null 2>&1; then
  log "清理 off 臂残留进程: $(pgrep -f "$OFF_PAT" | tr '\n' ' ')"
  pkill -TERM -f "$OFF_PAT" 2>/dev/null; sleep 5
  pkill -KILL -f "$OFF_PAT" 2>/dev/null; sleep 2
fi

# ---- Ctrl-C / TERM：连同跑批进程组一起中止 ----
pgid=""
cleanup() {
  log "收到中断信号，中止看护与跑批进程组（PGID=${pgid:-无}）"
  [ -n "$pgid" ] && { kill -TERM -- "-$pgid" 2>/dev/null; sleep 3; kill -KILL -- "-$pgid" 2>/dev/null; }
  exit 130
}
trap cleanup INT TERM

overall_deadline=$(( $(date +%s) + LIMIT_MIN * 60 ))
success=0

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  PROG="$RUN/PROGRESS_attempt${attempt}.log"
  : > "$PROG"
  launch_batch "$PROG"
  pgid=$!
  log "attempt $attempt/$MAX_ATTEMPTS 启动（PGID=${pgid}，进度日志 PROGRESS_attempt${attempt}.log）"

  last_fp=""
  stall_since=$(date +%s)
  polls=0
  rc=""
  while :; do
    sleep "$POLL_SEC"
    polls=$((polls+1))
    now=$(date +%s)

    # 进程组已退出 → wait 收尸
    if ! kill -0 "$pgid" 2>/dev/null; then
      wait "$pgid"; rc=$?
      break
    fi

    # 总时限（跨 attempt 共享）
    if [ "$now" -ge "$overall_deadline" ]; then
      log "超总时限 ${LIMIT_MIN}min，放弃（击杀进程组后退出）"
      kill -TERM -- "-$pgid" 2>/dev/null; sleep 5; kill -KILL -- "-$pgid" 2>/dev/null
      exit 1
    fi

    # 活性指纹：进度日志字节 + 输出树文件数（tqdm 刷新即变化）
    fp="$(wc -c < "$PROG" | tr -d ' ')|$(find "$RUN" -type f 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$fp" != "$last_fp" ]; then
      last_fp="$fp"; stall_since=$now
    fi
    stalled_min=$(( (now - stall_since) / 60 ))

    if [ $((polls % REPORT_EVERY)) -eq 0 ]; then
      progress="$(tail -c 4096 "$PROG" 2>/dev/null | grep -oE '[0-9]+/178' | tail -1)"
      log "elapsed=$(( (now - overall_deadline + LIMIT_MIN*60) / 60 ))min stalled=${stalled_min}min progress=${progress:-?} fp=$fp"
    fi

    # stall 判定：指纹 ${STALL_MIN} 分钟不变（进程死活不论）→ 整组击杀重启
    if [ "$stalled_min" -ge "$STALL_MIN" ]; then
      log "stall ${stalled_min}min（指纹 $fp 不变）→ 击杀进程组 PGID=${pgid}，准备重启"
      kill -TERM -- "-$pgid" 2>/dev/null; sleep 10
      kill -0 "$pgid" 2>/dev/null && kill -KILL -- "-$pgid" 2>/dev/null
      wait "$pgid" 2>/dev/null; rc=$?
      break
    fi
  done

  if [ "$rc" -eq 0 ]; then
    success=1
    log "attempt $attempt 正常退出 rc=0"
    break
  fi
  log "attempt $attempt 失败（rc=${rc:-unknown}），$( [ "$attempt" -lt "$MAX_ATTEMPTS" ] && echo "自动重启" || echo "已达重启上限" )"
done

if [ "$success" -eq 1 ]; then
  log "off 臂完成。产出清点:"
  ls -lt "$RUN" 2>/dev/null | head -12 | tee -a "$LOG" >/dev/null
  log "下一步: 两臂齐后跑 G8 判定流水（off-on 唯一差异=四开关）"
  exit 0
fi
log "看护放弃：$MAX_ATTEMPTS 次尝试均失败或超总时限——需人工介入（排查卡死任务根因，如 LLM 挂死/环境锁）"
exit 1
