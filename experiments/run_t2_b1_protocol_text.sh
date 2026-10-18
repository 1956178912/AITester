#!/usr/bin/env bash
# T2/B1（2026-10-18）：RT1 协议文本消融的指纹级复现 —— 3 格 × 2 seed 真 LLM 跑批 runner
#
# 用法：
#   bash experiments/run_t2_b1_protocol_text.sh --dry-run     # 零 LLM 自测（preflight + 6 条命令打印）
#   bash experiments/run_t2_b1_protocol_text.sh               # 真实跑批（后台建议：nohup ... &）
#   bash experiments/run_t2_b1_protocol_text.sh --resume      # 续跑：跳过已存在且 run_status=ok 的格（不重跑）
#
# 运行参数修订（见 PREREG_CONTINUATION.md，判据未改）：共享 env 增加
#   ENABLE_MUTATION_SCORING=false —— 只关闭批后辅助测量（mutation_score/MDO），
#   不改变 detection / 生成 / 再生成 / 提示段落 / 预算 / seeds 的任何口径。
#
# 铁律：
#   - 跑批发生在独立 worktree（切点 a93c1f6），主仓工作区与生产源码零修改；
#   - 真实模式启动前强制 worktree HEAD=切点、dirty=0、PREREG 已冻结且含切点 sha；
#   - 单跑失败/超时如实记录、不重跑；预算/墙钟触达硬停止即停剩余跑批；
#   - 所有输出落主仓结果目录（worktree 保持 clean）。
set -uo pipefail

ROOT="/Users/wangchenyu/Workspace/AITester"
WT="/Users/wangchenyu/Workspace/AITester-t-b1-a93c1f6"
EXPECT_SHA="a93c1f60ee31b9582e0146f73e3038e6ce0f01a1"
OUT="$ROOT/experiments/results/t_round_b1_protocol_text_20261018"
PY="$ROOT/.venv/bin/python"
HELPERS="$OUT/_helpers"
PRICE="$ROOT/experiments/price_table.json"
RUN_SUMMARY="$OUT/RUN_SUMMARY.log"
PER_RUN_TIMEOUT=1800

DRY_RUN=0
RESUME=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --resume) RESUME=1 ;;
    *) echo "[runner][FAIL] 未知参数: $arg" >&2; exit 2 ;;
  esac
done
RESUME_ARG=""
if [ "$RESUME" = "1" ]; then RESUME_ARG="--resume"; fi

iso_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ── 0) 预检（dry-run / real 都跑；real 要求 dry-run 已全过） ──────────────
if [ "$DRY_RUN" = "1" ]; then PF_MODE="dry-run"; else PF_MODE="real"; fi
echo "[runner] preflight mode=$PF_MODE ..."
if ! "$PY" "$HELPERS/preflight.py" --mode "$PF_MODE" --out "$OUT" --wt "$WT" --expect-sha "$EXPECT_SHA" --py "$PY" $RESUME_ARG; then
  echo "[runner][FAIL] preflight 未通过：禁止继续（真实模式不会产生任何 LLM 调用）" >&2
  exit 1
fi

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "==================== DRY-RUN：6 条待跑命令（未执行、零 LLM 调用） ===================="
  "$PY" - "$OUT" <<'PYEOF'
import json, sys
pf = json.load(open(sys.argv[1] + "/PREFLIGHT.json", encoding="utf-8"))
for i, cmd in enumerate(pf["dry_run_commands"], 1):
    env_line = " ".join(f"{k}={v}" for k, v in cmd["env"].items())
    print(f"[{i}/6] {cmd['label']}")
    print(f"      cwd={cmd['cwd']}")
    print(f"      env {env_line}")
    print(f"      cmd {' '.join(cmd['argv'])}")
print("")
print(f"checks={len(pf['checks'])} blocking={pf['blocking']} warnings={pf['warnings']}")
print(f"estimate: cost_2seeds=${pf['estimate']['cost_2seeds_usd']} upper=${pf['estimate']['cost_upper_bound_usd']} "
      f"wall≈{pf['estimate']['wall_estimate_minutes']}min（硬停止 {pf['estimate']['wall_hard_stop_seconds']}s）")
PYEOF
  echo "[runner] dry-run 自测完成（零 LLM 调用）。真实跑批：bash $0"
  exit 0
fi

# ── 1) 真实模式硬检查（再次断言，防 preflight 与实际之间被改动） ─────────
HEAD_NOW="$(git -C "$WT" rev-parse HEAD 2>/dev/null || true)"
DIRTY_NOW="$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
if [ "$HEAD_NOW" != "$EXPECT_SHA" ]; then
  echo "[runner][FAIL] worktree HEAD=$HEAD_NOW ≠ 切点 $EXPECT_SHA" >&2
  exit 1
fi
if [ "$DIRTY_NOW" != "0" ]; then
  echo "[runner][FAIL] worktree dirty=$DIRTY_NOW ≠ 0" >&2
  exit 1
fi
PREREG_SHA="$(shasum -a 256 "$OUT/PREREG.md" | awk '{print $1}')"
if ! grep -q "$EXPECT_SHA" "$OUT/PREREG.md"; then
  echo "[runner][FAIL] PREREG.md 未包含切点 sha" >&2
  exit 1
fi

# 每格环境（仅 C2 额外关强化段落）
common_env=(
  "AITESTER_PROFILE=logic"
  "TEMPERATURE=0.0"
  "LLM_THINKING_MODE=disabled"
  "BENCHMARK_PARALLELISM=4"
  "AITESTER_LLM_CACHE=0"
  "COST_BUDGET_ENABLE=true"
  "COST_BUDGET_TOKENS=200000"
  "COST_BUDGET_USD=1.0"
  "AITESTER_BATCH_MAX_CALLS=4000"
  "AITESTER_BATCH_MAX_USD=2.0"
  # 执行性修订（PREREG_CONTINUATION.md）：只关闭批后辅助测量（mutation/MDO），
  # 不改变 detection/生成/再生成/提示/预算 —— C1_seed42 为修订前已跑（保留不重跑）。
  "ENABLE_MUTATION_SCORING=false"
)

BATCH_START_EPOCH="$(date +%s)"
BATCH_START_ISO="$(iso_utc)"
{
  echo "T2/B1（2026-10-18）：RT1 协议文本消融 —— 3 格 × 2 seed 真 LLM 跑批"
  echo "CUT_SHA=$EXPECT_SHA"
  echo "WORKTREE=$WT"
  echo "OUT=$OUT"
  echo "PREREG_SHA256=$PREREG_SHA"
  echo "BATCH_START_ISO_UTC=$BATCH_START_ISO BATCH_START_EPOCH=$BATCH_START_EPOCH"
  echo "PLAN=C1_seed42,C1_seed44,C2_seed42,C2_seed44,C3_seed42,C3_seed44（cell-major，seed 42→44）"
  echo "BUDGET_USD_MAX=2.0 COST_HARD_STOP_USD=1.8 WALL_HARD_STOP_SECONDS=5100 PER_RUN_TIMEOUT=${PER_RUN_TIMEOUT}s"
  echo "AMENDMENT=PREREG_CONTINUATION.md（判据未改；C1_seed44 起 ENABLE_MUTATION_SCORING=false 关闭批后辅助测量）RESUME=$RESUME"
  echo "================================================================"
} > "$RUN_SUMMARY"

CUM_COST="0"
ALL_RUNS_OK=1
STOP=0
STOP_REASON=""
RUN_INDEX=0

for cell in C1 C2 C3; do
  case "$cell" in
    C1) arm="plain_llm"; tag="plain_llm" ;;
    C2) arm="plain_llm_df"; tag="rt1" ;;
    C3) arm="plain_llm_df"; tag="df_full" ;;
  esac
  for seed in 42 44; do
    RUN_INDEX=$((RUN_INDEX + 1))
    label="${cell}_seed${seed}"
    od="$OUT/staging/$label"
    tr="$OUT/traces/$label"
    log="$OUT/logs/$label.log"
    meta="$OUT/seed${seed}/meta_${cell}.json"
    mkdir -p "$od" "$tr" "$OUT/seed${seed}"

    # 续跑：已有 ok 元数据的格不再跑（不重跑纪律；其费用仍计入预算累计）
    if [ "$RESUME" = "1" ] && [ -f "$meta" ]; then
      KEPT_STATUS="$("$PY" -c "import json,sys; print((json.load(open(sys.argv[1], encoding='utf-8')).get('run_status') or ''))" "$meta" 2>/dev/null || echo '')"
      if [ "$KEPT_STATUS" = "ok" ]; then
        KEPT_COST="$("$PY" -c "import json,sys; m=json.load(open(sys.argv[1], encoding='utf-8')); c=m.get('cost_usd_standard_price'); print(c if isinstance(c,(int,float)) else 0.0)" "$meta" 2>/dev/null || echo '0.0')"
        CUM_COST="$("$PY" -c "print(round(float('${CUM_COST}') + float('${KEPT_COST}'), 6))")"
        {
          echo "[$RUN_INDEX/6] $label KEPT（resume：已存在 run_status=ok 的元数据，不重跑、沿用原工件）"
          echo "          meta=$meta cost_usd=$KEPT_COST"
        } >> "$RUN_SUMMARY"
        continue
      fi
    fi

    if [ "$STOP" = "1" ]; then
      {
        echo "[$RUN_INDEX/6] $label SKIPPED（触达硬停止：$STOP_REASON，未执行、不含任何数据）"
      } >> "$RUN_SUMMARY"
      # 写占位元数据：不伪造指标
      "$PY" - "$meta" "$label" "$cell" "$seed" "$arm" "$od" "$tr" "$log" "$STOP_REASON" <<'PYEOF'
import json, sys
meta, label, cell, seed, arm, od, tr, log, reason = sys.argv[1:10]
json.dump({
    "label": label, "cell": cell, "seed": int(seed), "arm": arm,
    "batch_dir": od, "batch_path": None, "batch_sha256": None,
    "run_status": "skipped_due_to_stop_rule", "rows": 0, "task_ids": [], "tasks": [],
    "token_metrics": {}, "cost_usd_standard_price": None, "provenance": {},
    "run_log": {"log_path": log, "start_iso_utc": None, "end_iso_utc": None, "exit_code": None, "wall_seconds": None},
    "trace_dir": tr, "trace_files": 0, "failure_note": f"stopped before run: {reason}",
}, open(meta, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
      continue
    fi

    START_ISO="$(iso_utc)"
    START_EPOCH="$(date +%s)"
    run_env=("${common_env[@]}" \
      "AITESTER_CACHE_NAMESPACE=t_b1_${cell}_${seed}" \
      "AITESTER_TRACE_DIR=$tr")
    if [ "$cell" = "C2" ]; then
      run_env+=("DETECTION_FIRST_SECTION_ENABLE=false")
    fi
    CMD_STR="env $(printf '%s ' "${run_env[@]}")"$'\n'"    $PY -m experiments.run_benchmark --dataset synthetic --task-count 87 --max-pattern-repeat 2 --seed $seed --baselines $arm --output-dir $od"
    {
      echo ""
      echo "================ [$RUN_INDEX/6] RUN START $label ================"
      echo "LABEL=$label CELL=$cell TAG=$tag ARM=$arm SEED=$seed"
      echo "CWD=$WT"
      echo "COMMAND=$CMD_STR"
      echo "ENV=$(printf '%s ' "${run_env[@]}")"
      echo "START_ISO_UTC=$START_ISO START_EPOCH=$START_EPOCH"
      echo "----------------------------------------------------------------"
    } > "$log"

    # 真实调用（worktree cwd；输出/追踪全部指向主仓结果目录）
    ( cd "$WT" && "$PY" "$HELPERS/limited_run.py" "$PER_RUN_TIMEOUT" \
        env "${run_env[@]}" "$PY" -m experiments.run_benchmark \
        --dataset synthetic --task-count 87 --max-pattern-repeat 2 \
        --seed "$seed" --baselines "$arm" --output-dir "$od" ) >> "$log" 2>&1
    rc=$?

    END_ISO="$(iso_utc)"
    END_EPOCH="$(date +%s)"
    WALL=$((END_EPOCH - START_EPOCH))
    {
      echo "----------------------------------------------------------------"
      echo "END_ISO_UTC=$END_ISO END_EPOCH=$END_EPOCH EXIT_CODE=$rc WALL_SECONDS=$WALL"
    } >> "$log"

    batch_json="$(ls -t "$od"/benchmark_synthetic_*.json 2>/dev/null | head -1 || true)"
    if [ -z "$batch_json" ]; then
      batch_json="-"
      ALL_RUNS_OK=0
    fi

    # 抽元数据（含 provenance/model_fingerprint/行数/task_id 集合）
    "$PY" "$HELPERS/extract_arm.py" "$batch_json" "$label" "$cell" "$seed" "$arm" \
      "$meta" "$log" "$tr" "$PRICE" "$od" >> "$log" 2>&1
    EXTRACT_RC=$?

    # 摘要行（数值从 meta 读回，不手填）
    read -r M_STATUS M_ROWS M_DET M_COST M_GITSHA M_DIRTY M_PINNED M_WALL M_EXIT <<<"$(
      "$PY" - "$meta" <<'PYEOF'
import json, sys
try:
    m = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("meta_unreadable 0 - - - - - - -"); raise SystemExit
s = m.get("summary") or {}
p = m.get("provenance") or {}
fp = p.get("model_fingerprint") or {}
rl = m.get("run_log") or {}
print(
    m.get("run_status"), m.get("rows"),
    f"{s.get('detected','-')}/{s.get('measurable','-')}",
    m.get("cost_usd_standard_price"), p.get("git_sha"), p.get("git_dirty"),
    fp.get("pinned"), rl.get("wall_seconds"), rl.get("exit_code"),
)
PYEOF
)"
    {
      echo "[$RUN_INDEX/6] $label status=$M_STATUS rows=$M_ROWS det=$M_DET cost_usd=$M_COST wall=${M_WALL}s exit=$M_EXIT"
      echo "          provenance: git_sha=$M_GITSHA git_dirty=$M_DIRTY model_fingerprint.pinned=$M_PINNED"
      echo "          log=$log"
      echo "          batch=${batch_json}"
      echo "          meta=$meta"
    } >> "$RUN_SUMMARY"

    if [ "$M_STATUS" != "ok" ] || [ "$rc" -ne 0 ]; then
      ALL_RUNS_OK=0
    fi
    if [ "$EXTRACT_RC" -ne 0 ]; then
      ALL_RUNS_OK=0
    fi

    # 预算/墙钟累计 + 硬停止
    CUM_COST="$("$PY" -c "c=float('${CUM_COST}'); x='${M_COST}'; print(round(c + (float(x) if x not in ('-','None','') else 0.0), 6))")"
    ELAPSED=$(( $(date +%s) - BATCH_START_EPOCH ))
    if "$PY" -c "import sys; sys.exit(0 if ($CUM_COST > 1.8 or $ELAPSED > 5100) else 1)"; then
      STOP=1
      if "$PY" -c "import sys; sys.exit(0 if $CUM_COST > 1.8 else 1)"; then
        STOP_REASON="cumulative_cost>1.8USD(cost=${CUM_COST})"
      else
        STOP_REASON="batch_wall>5100s(elapsed=${ELAPSED}s)"
      fi
      {
        echo ">>> HARD STOP 触发：$STOP_REASON；剩余跑批将标记 skipped（如实记录，不重跑）"
      } >> "$RUN_SUMMARY"
      ALL_RUNS_OK=0
    fi

    sleep 3
  done
done

BATCH_END_EPOCH="$(date +%s)"
BATCH_END_ISO="$(iso_utc)"
BATCH_WALL=$((BATCH_END_EPOCH - BATCH_START_EPOCH))

# 汇总 totals（token/cost 从 meta 读回）
"$PY" - "$OUT" >> "$RUN_SUMMARY" <<'PYEOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
cells, seeds = ("C1", "C2", "C3"), (42, 44)
tot_in = tot_out = tot_tok = tot_calls = 0
tot_cost = 0.0
total_wall = 0
tot_rows = 0
reg = {}
for s in seeds:
    for c in cells:
        p = out / f"seed{s}" / f"meta_{c}.json"
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        tm = m.get("token_metrics") or {}
        for k in ("total_input_tokens", "total_output_tokens", "total_tokens", "total_llm_calls"):
            v = tm.get(k)
            if isinstance(v, (int, float)):
                if k == "total_input_tokens": tot_in += v
                elif k == "total_output_tokens": tot_out += v
                elif k == "total_tokens": tot_tok += v
                else: tot_calls += v
        if isinstance(m.get("cost_usd_standard_price"), (int, float)):
            tot_cost += m["cost_usd_standard_price"]
        w = (m.get("run_log") or {}).get("wall_seconds")
        if isinstance(w, (int, float)): total_wall += w
        sm = m.get("summary") or {}
        tot_rows += m.get("rows") or 0
    for c in cells:
        p = out / f"seed{s}" / f"meta_{c}.json"
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        tasks = m.get("tasks") or []
        reg[f"seed{s}_{c}"] = sum(1 for t in tasks if isinstance(t.get("regeneration_count"), (int, float)) and t["regeneration_count"] > 0)
print("")
print("================ 批次汇总（从工件读回，非手填） ================")
print(f"TOTAL_ROWS={tot_rows} TOTAL_INPUT_TOKENS={tot_in} TOTAL_OUTPUT_TOKENS={tot_out} TOTAL_TOKENS={tot_tok} TOTAL_LLM_CALLS={tot_calls}")
print(f"TOTAL_COST_USD_STANDARD_PRICE={round(tot_cost, 6)}（价目表标准价，上界口径）")
print(f"RUNS_WALL_SUM_SECONDS={total_wall}")
print(f"REGENERATED_ROWS={reg}")
print("================================================================")
PYEOF

{
  echo ""
  echo "BATCH_END_ISO_UTC=$BATCH_END_ISO BATCH_END_EPOCH=$BATCH_END_EPOCH BATCH_WALL_SECONDS=$BATCH_WALL"
  echo "WORKTREE_POST_RUN_DIRTY=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  echo "WORKTREE_POST_RUN_HEAD=$(git -C "$WT" rev-parse HEAD 2>/dev/null || echo '?')"
  echo "ALL_RUNS_OK=$ALL_RUNS_OK STOP_TRIGGERED=$STOP STOP_REASON=${STOP_REASON:-none}"
} >> "$RUN_SUMMARY"

# ── 2) 硬门禁（零 LLM）：GATES.json ──────────────────────────────────────
echo "[runner] gates ..."
"$PY" "$HELPERS/gates.py" --out "$OUT" --expect-sha "$EXPECT_SHA"
GATES_RC=$?
echo "[runner] gates rc=$GATES_RC（GATES.json=$( [ -f "$OUT/GATES.json" ] && echo '已生成' || echo '缺失')）" | tee -a "$RUN_SUMMARY"

if [ "$ALL_RUNS_OK" = "1" ] && [ "$GATES_RC" -eq 0 ]; then
  echo "RUNNER_EXIT=0" >> "$RUN_SUMMARY"
  echo "[runner] 完成：6/6 跑批 ok，gates 通过"
  exit 0
else
  echo "RUNNER_EXIT=4" >> "$RUN_SUMMARY"
  echo "[runner] 完成但有异常：ALL_RUNS_OK=$ALL_RUNS_OK GATES_RC=$GATES_RC（详见 $RUN_SUMMARY 与 $OUT/GATES.json）" >&2
  exit 4
fi
