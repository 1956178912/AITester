#!/usr/bin/env bash
# 2026-10-10 独立审查落地批次 · 逻辑通道 A/B（SPEC_ORACLE_EXEC_ENABLE off/on）
#
# 目的：回答"确定性规约 oracle 通道对检出是否有净贡献"——这是审查报告
#       §6.8 更正框留下的核心未决问题（此前用错字段导致误判为"零注入"）。
#
# 设计（单变量）：
#   - 唯一自变量：SPEC_ORACLE_EXEC_ENABLE
#       control 臂 = false（不注入规约 oracle）
#       treat   臂 = true （注入；与 logic 档历史口径一致）
#   - 其余全部固定：AITESTER_PROFILE=logic、TEMPERATURE=0、seed=42、
#     LLM_THINKING_MODE=disabled、冷缓存（AITESTER_LLM_CACHE=0）。
#     config.py 用 os.environ.setdefault 注入档位预设，故显式 env 不被覆盖。
#   - 基准：QuixBugs（50 任务 = 41 缺陷程序 + 9 测试驱动脚本；M1 口径）
#   - 主终点：detection_rate（M1 三段判定 F2P，gold 独立裁决）
#   - 机制指标：spec_oracle_injected / spec_oracle_verdict（本次审查新增，
#     用于**证明干预确实生效**——A1 首跑正是因缺此证据而被误判为零效应）
#
# 用法：
#   bash scripts/tools/run_logic_channel_ab.sh smoke   # 3 任务双跑 ≈$0.2
#   bash scripts/tools/run_logic_channel_ab.sh full    # 50 任务双跑 ≈$2.4
#
# 硬约束：cold cache 每臂独立（AITESTER_LLM_CACHE=0），防止跨臂响应复用污染。

set -euo pipefail

MODE="${1:-smoke}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY=".venv/bin/python"
OUT_BASE="experiments/results/llm_logic_ab_20261010"

case "$MODE" in
  smoke) LIMIT=3 ;;
  full)  LIMIT=50 ;;
  *) echo "用法: $0 [smoke|full]" >&2; exit 2 ;;
esac

if [[ -z "${DEEPSEEK_API_KEY:-}" ]] && [[ ! -f .env.local ]]; then
  echo "[FAIL] 未发现 DEEPSEEK_API_KEY 且无 .env.local —— 拒绝无凭证跑批" >&2
  exit 3
fi

# M1 判分数（experiments/_m1_metrics.py）即本项目 detection 的权威实现，
# 无需额外开关；此处只固定协议变量。
export AITESTER_PROFILE=logic
export TEMPERATURE=0
export LLM_THINKING_MODE=disabled
export AITESTER_LLM_CACHE=0          # 冷缓存：臂间零复用，杜绝 A1/RT1 式污染
export BENCHMARK_PARALLELISM=4
export MAX_ITERATIONS=3              # 与 logic 档主批次同口径

# ⚠️ 数据集落点必须显式给定：QuixBugsDataset 在 AITESTER_QUIXBUGS_DATA 未设时
# **静默回退到 InMemoryDataset(examples)**（src/datasets/dataset_realbugs.py:92-101），
# 于是 `--dataset quixbugs` 会安静地跑成 examples——本审查首跑即踩中此坑
# （工件名 benchmark_examples_*.json 暴露）。这与 F7 的 SWE-bench `instance_code=0`
# 是同一类"管道缺陷被当成实验结果"的风险，故此处显式导出 + 事后断言。
export AITESTER_QUIXBUGS_DATA="${AITESTER_QUIXBUGS_DATA:-$ROOT/data/quixbugs}"
if [[ ! -d "$AITESTER_QUIXBUGS_DATA/python_programs" ]]; then
  echo "[FAIL] QuixBugs 数据目录无 python_programs/: $AITESTER_QUIXBUGS_DATA" >&2
  exit 3
fi

echo "==================================================================="
echo " 逻辑通道 A/B · mode=$MODE · task_limit=$LIMIT · 冷缓存 · profile=logic"
echo " 输出根目录: $OUT_BASE"
echo "==================================================================="

for ARM in control treat; do
  if [[ "$ARM" == "control" ]]; then
    export SPEC_ORACLE_EXEC_ENABLE=false
  else
    export SPEC_ORACLE_EXEC_ENABLE=true
  fi

  DEST="$OUT_BASE/$ARM"
  mkdir -p "$DEST"
  LOG="$DEST/run.log"

  echo
  echo "──────── 臂: $ARM （SPEC_ORACLE_EXEC_ENABLE=${SPEC_ORACLE_EXEC_ENABLE}）────────"
  echo "  输出: $DEST"

  set +e
  # 硬墙钟兜底：跑批层不依赖被测代码不出错（变异层挂死已于 2026-10-10 修复，
  # 但此处再提供独立上限，超时即 killpg 整树，绝不无限占用时间与预算）。
  "$PY" scripts/tools/run_arm_with_cap.py \
      --timeout "${ARM_TIMEOUT:-2700}" \
      --log "$LOG" \
      -- "$PY" experiments/run_benchmark.py \
      --dataset quixbugs \
      --task-limit "$LIMIT" \
      --baselines aitester \
      --output-dir "$DEST" \
      --parallel 4 \
      --seed 42 \
      --verbose
  RC=$?
  set -e

  echo "  exit=$RC · 日志: $LOG"
  if [[ $RC -ne 0 ]]; then
    echo "  [WARN] 非零退出，检查日志尾部："
    tail -15 "$LOG" || true
  fi
done

echo
echo "==================================================================="
echo " 双臂完成。后置断言（零 LLM）："
echo "==================================================================="
"$PY" - "$OUT_BASE" <<'PYEOF'
import glob, json, os, sys
base = sys.argv[1]
ok = True
for arm in ("control", "treat"):
    fs = sorted(glob.glob(f"{base}/{arm}/benchmark_quixbugs_*.json"))
    if not fs:
        got = sorted(os.path.basename(p) for p in glob.glob(f"{base}/{arm}/benchmark_*.json"))
        print(f"[FAIL] {arm}: 无 benchmark_quixbugs_*.json（实得: {got}）——数据集回退未生效？")
        ok = False
        continue
    d = json.load(open(fs[-1]))
    env = d.get("provenance", {}).get("env_snapshot") or {}
    rows = d["results"]["aitester"]["details"]
    inj = [r.get("spec_oracle_injected") for r in rows]
    ver = [r.get("spec_oracle_verdict") for r in rows]
    det = [r.get("detection_rate") for r in rows if r.get("detection_rate") is not None]
    print(f"[{arm}] dataset={d.get('dataset')} n={len(rows)} "
          f"SPEC_ORACLE_EXEC_ENABLE={env.get('SPEC_ORACLE_EXEC_ENABLE')}")
    print(f"        verdict={ver}")
    print(f"        injected 计数={sum(1 for v in inj if v is True)} / det_measured={len(det)}")
    if str(env.get("SPEC_ORACLE_EXEC_ENABLE")).lower() not in ("true", "false"):
        print("        [FAIL] 快照缺 SPEC_ORACLE_EXEC_ENABLE —— 干预生效性不可证明（A1 同类风险）")
        ok = False
print("后置断言通过：双臂工件齐备且开关已入快照" if ok else "后置断言失败——结果不可用于配对分析")
PYEOF
