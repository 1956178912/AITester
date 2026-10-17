#!/usr/bin/env bash
# =============================================================================
# N-4 真实 LLM 重型功能探针（覆盖零 LLM 探针无法覆盖的装配路径）
# 2026-10-17（N 轮）
#
# 目标：用真实 LLM 顺序执行 7 项重型功能探针，**找功能静默失效**
#       （字段恒 None / 路径从不进入 / 状态丢失 / 开关不生效），
#       产出可审计证据（命令/开关/墙钟/tokens/成本/关键 state 字段/日志/trace）。
#
# 纪律（N-4 任务书）：
#   - 预算 ≤ $0.5、墙钟 ≤ 90min；**顺序执行**（避免并发争抢）；每项独立 cache namespace；
#   - 不改源码、不 commit、不删既有工件、不做无界重试；
#   - 所有产物写 experiments/results/e2e_llm_probes_20261017/（gitignored，Lead 统一 git add -f）；
#   - 每项独立日志 + 逐项 meta（含批次 JSON 的 token/成本/字段观测）；
#   - 任务挂死用有限墙钟看门狗拦截（SIGTERM→SIGKILL 进程组），如实记录，不重跑。
#
# 探针清单（真实 LLM，除 item7 blocked 可能跳过；顺序执行）：
#   00  LLM 连通性冒烟（1 次极小调用；失败则中止）
#   01  logic 档全链路 aitester × 3 QuixBugs 任务（planner/debugger/patch/repair/
#       spec_ir・DSL・oracle/stop_reason/trace/成本）
#   02  RAG 开（ENABLE_RAG=true）× 2 任务（rag_stats/检索次数/降级/完整错误）
#   03  跨文件 synthetic level3 × 2 任务（CROSS_FILE_ENABLE=true；cross_file_analyzer/
#       多文件补丁路径）
#   04  venv 执行器 × 1 任务（EXECUTOR_USE_VENV=true；venv 缓存目录时间窗证据）
#   05a 预算停止（USD 路径）× 1 任务（COST_BUDGET_ENABLE=true COST_BUDGET_USD=0.0001
#       + COST_USD_PER_1K=0.3 → 期望 budget_exceeded；**重点核验是否真触发**）
#   05b 预算停止（token 路径阳性对照）× 1 任务（COST_BUDGET_TOKENS=100 → 期望
#       BudgetExceededError/budget_exceeded 停止通道与行字段）
#   06  安全档 × 1 任务（AITESTER_PROFILE=safe → 内核沙箱/注入守卫/回滚开关生效或
#       明确降级而非静默）
#   07  oracle 冒烟（**依赖 N-3 提交**；未就绪记录 blocked 并跳过）：
#       df_spec 臂 + SPEC_ORACLE_EXEC_ENABLE=true task-limit=1
#
# 用法：
#   bash experiments/run_e2e_llm_probes.sh --dry-run     # 只打印计划，零 LLM
#   bash experiments/run_e2e_llm_probes.sh               # 正式执行（顺序，≤90min）
#
# 产物：<OUT>/<item>/（批次 JSON + run.log + traces/ + item_meta.json）
#       <OUT>/PREFLIGHT.json、ITEM_RESULTS.json/.md、README.md（人工结论）、SHA256SUMS
# 退出码：0 = 探针全部执行完成（含 fail/blocked；结论见报告）；2 = 前置失败；3 = LLM 冒烟失败。
# =============================================================================

set -euo pipefail

_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${_SELF_DIR}/.." && pwd)"   # 脚本所在仓（主仓；提供 .venv/价目表等）
ROOT="${SCRIPT_REPO}"                            # 被探针的代码根（--root 可指向冻结 worktree）
PY="${SCRIPT_REPO}/.venv/bin/python"
OUT="${SCRIPT_REPO}/experiments/results/e2e_llm_probes_20261017"  # 产物根（--out 可覆盖）
REQUIRE_CLEAN_ROOT=0
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
START_ALL_EPOCH="$(date +%s)"
DIRTY_REASON="N-4 真实 LLM 功能探针：工作树含其他并行任务的在途交付（Makefile e2e-probe target、scripts/tools/e2e_probe.py、tests/test_e2e_probe.py），与所探针代码路径无关"
DRY_RUN=0
SKIP_ITEMS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --skip-items)
            [ $# -ge 2 ] || { echo "--skip-items 需要逗号分隔列表" >&2; exit 2; }
            SKIP_ITEMS=",$2,"
            shift 2
            ;;
        --root)
            [ $# -ge 2 ] || { echo "--root 需要一个目录" >&2; exit 2; }
            ROOT="$2"
            shift 2
            ;;
        --out)
            [ $# -ge 2 ] || { echo "--out 需要一个目录" >&2; exit 2; }
            OUT="$2"
            shift 2
            ;;
        --require-clean-root)
            REQUIRE_CLEAN_ROOT=1
            shift
            ;;
        -h | --help)
            awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "未知参数：$1（--help 查看用法）" >&2
            exit 2
            ;;
    esac
done

[ -x "${PY}" ] || { echo "✗ 未找到解释器 ${PY}" >&2; exit 2; }
[ -d "${ROOT}" ] || { echo "✗ --root 不是目录：${ROOT}" >&2; exit 2; }
ROOT="$(cd "${ROOT}" && pwd)"
OUT="$(cd "$(dirname "${OUT}")" 2>/dev/null && pwd)/$(basename "${OUT}")" 2>/dev/null || true
[ -n "${OUT}" ] || OUT="${SCRIPT_REPO}/experiments/results/e2e_llm_probes_20261017"
[ -f "${ROOT}/experiments/run_main_batch.py" ] || { echo "✗ 代码根解析异常（缺 experiments/run_main_batch.py）：${ROOT}" >&2; exit 2; }
[ -f "${ROOT}/experiments/price_table.json" ] || { echo "✗ 代码根缺 experiments/price_table.json：${ROOT}" >&2; exit 2; }

# 冻结快照口径：--require-clean-root 时 ROOT 必须 0 dirty（正式探针证据要求可归因）
ROOT_GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo '?')"
ROOT_DIRTY="$(git -C "${ROOT}" status --porcelain 2>/dev/null || true)"
if [ -n "${ROOT_DIRTY}" ]; then
    if [ "${REQUIRE_CLEAN_ROOT}" -eq 1 ]; then
        printf '%s\n' "${ROOT_DIRTY}" >&2
        echo "✗ 代码根不干净（--require-clean-root）：${ROOT}" >&2
        exit 2
    fi
    _DIRTY_ARGS=(--allow-dirty --dirty-reason "${DIRTY_REASON}")
else
    _DIRTY_ARGS=()
fi
if [ -n "${ROOT_DIRTY}" ]; then _CROSS_REASON="${DIRTY_REASON}"; else _CROSS_REASON=""; fi

echo "================================================================================"
echo "N-4 真实 LLM 重型功能探针（${RUN_STAMP}）$( [ "${DRY_RUN}" -eq 1 ] && echo '【DRY-RUN：零 LLM】' )"
echo "  代码根（被探针）：${ROOT}"
echo "  脚本所在仓/解释器：${SCRIPT_REPO}"
echo "  输出：${OUT}"
echo "  预算：≤\$0.5；墙钟：≤90min；顺序执行；每项独立 cache namespace"
echo "  探针成本裁剪：MAX_ITERATIONS=1 / ENABLE_MUTATION_SCORING=false / BRANCH_COVERAGE_INJECT_ENABLE=false"
echo "                  / MUTATION_ADVISOR_ENABLE=false（仅关非目标后处理测量；logic 主链路装配不变，详见 README）"
echo "================================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo ""
    echo "[计划] 顺序执行以下探针（正式运行会真实调用 LLM）："
    cat <<'EOF'
  00 LLM 冒烟（1 调用）                        namespace=e2e_llm_probes_20261017_00_smoke
  01 logic 全链路 aitester ×3 QuixBugs          namespace=…_01_logic
  02 RAG 开 aitester ×2（ENABLE_RAG=true）      namespace=…_02_rag
  03 跨文件 synthetic level3 aitester ×2        namespace=…_03_cross_file
  04 venv 执行器 aitester ×1                    namespace=…_04_venv
  05a 预算 USD 路径 aitester ×1（$0.0001）       namespace=…_05a_budget_usd
  05b 预算 token 阳性对照 aitester ×1（100 tok） namespace=…_05b_budget_tokens
  06 safe 档 aitester ×1                        namespace=…_06_safe
  07 oracle 冒烟（N-3 未提交则 blocked 跳过）    namespace=…_07_oracle
EOF
    echo ""
    echo "依赖检查（只读）："
    echo "  代码根 HEAD：${ROOT_GIT_HEAD}（dirty 行数=$(printf '%s\n' "${ROOT_DIRTY}" | grep -c . || true)）"
    echo "  run_main_batch: $([ -f "${ROOT}/experiments/run_main_batch.py" ] && echo OK || echo MISSING)"
    echo "  run_benchmark:  $([ -f "${ROOT}/experiments/run_benchmark.py" ] && echo OK || echo MISSING)"
    echo "  N-3 就绪（oracle 独立判读）: $(if [ -f "${ROOT}/tests/test_oracle_independent_judging.py" ] && grep -q "oracle_suite_verdict" "${ROOT}/src/graph/nodes.py" 2>/dev/null; then echo YES; else echo "NO（item07 将 blocked）"; fi)"
    echo "  LLM 配置：$([ -f "${ROOT}/.env.local" ] && echo '.env.local 在场' || echo 'MISSING .env.local')"
    echo ""
    echo "DRY-RUN 结束：未执行任何 LLM 调用、未写任何产物。"
    exit 0
fi

# ─── 既有工件保护 ────────────────────────────────────────────────────────────
if [ -e "${OUT}/ITEM_RESULTS.json" ] || [ -e "${OUT}/README.md" ]; then
    echo "✗ 输出目录已存在正式探针结论（${OUT}）——禁止覆盖；如需重跑请先由 Lead 裁决。" >&2
    exit 2
fi
mkdir -p "${OUT}/_helpers"

# ─── 辅助脚本 1：有限墙钟看门狗（SIGTERM→SIGKILL 进程组） ────────────────────
cat > "${OUT}/_helpers/limited_run.py" <<'PY'
"""有限墙钟看门狗：运行子进程，超时先 SIGTERM 进程组、宽限后 SIGKILL；不静默挂死。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

limit = float(sys.argv[1])
cmd = sys.argv[2:]
t0 = time.time()
proc = subprocess.Popen(cmd, start_new_session=True)
try:
    rc = proc.wait(timeout=limit)
except subprocess.TimeoutExpired:
    print(f"\n[watchdog] 超过墙钟上限 {limit:.0f}s：SIGTERM 整个进程组…", file=sys.stderr, flush=True)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print("[watchdog] SIGTERM 宽限后仍存活：SIGKILL 进程组", file=sys.stderr, flush=True)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait()
    print(f"[watchdog] 探针被墙钟看门狗终止（wall={time.time() - t0:.0f}s）", file=sys.stderr, flush=True)
    sys.exit(124)
print(f"[watchdog] 子进程正常结束 rc={rc} wall={time.time() - t0:.1f}s", file=sys.stderr, flush=True)
sys.exit(rc)
PY

# ─── 辅助脚本 2：逐项证据抽取（批次 JSON + 日志关键词 + trace 节点） ───────
cat > "${OUT}/_helpers/extract_item.py" <<'PY'
"""逐项证据抽取：批次 JSON 指标/字段 → item_meta.json；日志关键词 + trace 节点计数。

只读取工件，零网络/零 LLM；输出为可审计 JSON（数字均来自工件，不手写）。
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

item_dir, log_path, out_meta, price_path, start_epoch, end_epoch = sys.argv[1:7]
item = Path(item_dir)
log = Path(log_path)

price = {}
try:
    price = (json.loads(Path(price_path).read_text(encoding="utf-8")).get("models") or {}).get("deepseek-flash") or {}
except (OSError, ValueError):
    pass

batches = sorted(glob.glob(str(item / "benchmark_*.json")))
meta: dict = {
    "item": item.name,
    "item_dir": str(item),
    "log": str(log),
    "start_epoch": int(start_epoch),
    "end_epoch": int(end_epoch),
    "wall_seconds": int(end_epoch) - int(start_epoch),
    "batch_files": [],
}

# ── 批次工件（可能 0 个 = 失败/未产出）──
details_all: list[dict] = []
token_totals = {"total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0, "total_llm_calls": 0,
                "total_cache_hits": 0, "total_cache_avoided_tokens": 0}
for bp in batches:
    try:
        data = json.loads(Path(bp).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    sha = hashlib.sha256(Path(bp).read_bytes()).hexdigest()
    results = data.get("results") or {}
    arms = {}
    for arm, rd in results.items():
        if not isinstance(rd, dict):
            continue
        tm = rd.get("token_metrics") or {}
        for k in token_totals:
            token_totals[k] += int(tm.get(k) or 0)
        det = rd.get("details") or []
        details_all.extend(det)
        arms[arm] = {
            "rows": len(det),
            "token_metrics": tm,
            "agg_rag_metrics": rd.get("rag_metrics"),
        }
    meta["batch_files"].append({"path": str(bp), "sha256": sha, "dataset": data.get("dataset"),
                                "total_tasks": data.get("total_tasks"), "provenance": data.get("provenance"),
                                "arms": arms})

in_tok = token_totals["total_input_tokens"]
out_tok = token_totals["total_output_tokens"]
cost = None
if isinstance(price.get("input_per_mtok"), (int, float)) and isinstance(price.get("output_per_mtok"), (int, float)):
    cost = round(in_tok / 1e6 * price["input_per_mtok"] + out_tok / 1e6 * price["output_per_mtok"], 6)
meta["tokens"] = token_totals
meta["cost_usd_standard_price"] = cost

# ── 逐任务字段观测（关键 state 字段是否恒 None/路径是否进入）──
def _is_none(v):
    return v is None or v == "" or v == [] or v == {}

rows_obs = []
for r in details_all:
    rh = r.get("repair_history")
    et = r.get("execution_trace")
    rows_obs.append({
        "task_id": r.get("task_id"),
        "passed": r.get("passed"),
        "iterations": r.get("iterations"),
        "detection_rate": r.get("detection_rate"),
        "repair_rate": r.get("repair_rate"),
        "false_fix_rate": r.get("false_fix_rate"),
        "test_error_rate": r.get("test_error_rate"),
        "stop_reason": r.get("stop_reason"),
        "error_category": r.get("error_category"),
        "token_budget_capped": r.get("token_budget_capped"),
        "diagnosis_present": not _is_none(r.get("diagnosis")),
        "patch_present": not _is_none(r.get("patch")),
        "repair_history_len": len(rh) if isinstance(rh, list) else None,
        "execution_trace_len": len(et) if isinstance(et, list) else None,
        "spec_compile_rate": r.get("spec_compile_rate"),
        "spec_oracle_injected": r.get("spec_oracle_injected"),
        "spec_oracle_verdict": r.get("spec_oracle_verdict"),
        "spec_expr_coverage": r.get("spec_expr_coverage"),
        "spec_replace_applied": r.get("spec_replace_applied"),
        "specificity_gate_verdict": r.get("specificity_gate_verdict"),
        "detection_first_status": r.get("detection_first_status"),
        "rag_stats": r.get("rag_stats"),
        "cross_file_deps": r.get("cross_file_deps"),
        "task_metadata_keys": sorted((r.get("task_metadata") or {}).keys())[:40],
        "task_metadata_difficulty": (r.get("task_metadata") or {}).get("difficulty"),
        "task_metadata_is_cross_file": (r.get("task_metadata") or {}).get("is_cross_file"),
        "patched_files": len(re.findall(r"^--- ", str(r.get("patch") or ""), flags=re.MULTILINE)) or None,
        "harness_invalid": r.get("harness_invalid"),
    })
meta["rows"] = rows_obs
meta["field_none_counts"] = {
    key: sum(1 for row in rows_obs if _is_none(row.get(key)))
    for key in (
        "detection_rate", "repair_rate", "false_fix_rate", "stop_reason", "diagnosis_present",
        "patch_present", "spec_compile_rate", "spec_oracle_injected", "spec_oracle_verdict",
        "spec_expr_coverage", "rag_stats", "cross_file_deps", "task_metadata_difficulty",
    )
}

# ── 日志关键词命中（观察 vs 期望的原始证据；只记命中行行号与截断文本）──
log_text = ""
try:
    log_text = log.read_text(encoding="utf-8", errors="replace")
except OSError:
    pass
keywords = [
    "venv", "aitester_sandbox", "sandbox-exec", "Seatbelt", "内核沙箱", "沙箱",
    "rag", "RAG", "检索", "chroma", "Chroma",
    "预算", "超限", "budget", "BudgetExceeded", "cost_budget",
    "cross_file", "跨文件", "多文件",
    "降级", "未支持", "not supported", "不可用",
    "trace", "生成计划", "planner", "debugger", "补丁", "repair",
]
log_hits = {}
for kw in keywords:
    hits = [ln.rstrip() for ln in log_text.splitlines() if kw in ln]
    if hits:
        log_hits[kw] = {"count": len(hits), "examples": [h[:220] for h in hits[:3]]}
meta["log_keyword_hits"] = log_hits
meta["log_warnings_errors"] = [
    ln.rstrip()[:260] for ln in log_text.splitlines()
    if re.search(r"⚠️|WARNING|ERROR|Traceback|超时|失败", ln) and len(ln.strip()) > 0
][:40]

# ── trace 节点事件计数（证明节点真的进入：planner/generator/executor/debugger/…）──
node_counts: dict[str, int] = {}
event_counts: dict[str, int] = {}
trace_files = sorted(glob.glob(str(item / "traces" / "*.jsonl")))
for tf in trace_files:
    try:
        for line in Path(tf).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            n = ev.get("node")
            if n:
                node_counts[str(n)] = node_counts.get(str(n), 0) + 1
            e = ev.get("event")
            if e:
                event_counts[str(e)] = event_counts.get(str(e), 0) + 1
    except OSError:
        continue
meta["trace"] = {"files": len(trace_files), "node_event_counts": node_counts, "event_counts": event_counts}

# ── venv 缓存目录时间窗证据（venv 执行器路径是否真的创建/复用 venv）──
venv_root = Path(os.path.expanduser("~")) / ".cache" / "aitester" / "venvs"
venv_touched = []
if venv_root.is_dir():
    for p in sorted(venv_root.iterdir()):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if int(start_epoch) - 5 <= mt <= int(end_epoch) + 5:
            venv_touched.append({"name": p.name, "mtime": mt})
meta["venv_cache_touched_in_window"] = venv_touched[:20]

Path(out_meta).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[extract] {item.name}: batches={len(batches)} rows={len(rows_obs)} wall={meta['wall_seconds']}s "
      f"tokens={token_totals['total_tokens']} cost=${cost} trace_files={len(trace_files)} "
      f"venv_touched={len(venv_touched)}")
PY

# ─── 辅助脚本 3：跨文件 synthetic 包装（run_benchmark difficulty=level3） ────
cat > "${OUT}/_helpers/run_cross_file.py" <<'PY'
"""item03 包装：run_benchmark(synthetic, difficulty=level3) —— 跨文件双模块任务。"""

from __future__ import annotations

import sys

root, out_dir, reason = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
from experiments.run_benchmark import run_benchmark  # noqa: E402

run_benchmark(
    dataset_name="synthetic",
    baselines=["aitester"],
    output_dir=out_dir,
    task_count=2,
    parallel=1,
    seed=42,
    difficulty="level3",
    deterministic=True,
    dirty_reason=(reason or None),
)
PY

# ─── 辅助脚本 4：汇总（ITEM_RESULTS.json/.md；数字全部来自 item_meta.json） ──
cat > "${OUT}/_helpers/summarize.py" <<'PY'
"""汇总全部探针 item_meta.json → ITEM_RESULTS.json/.md（不手写数字）。"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
root = Path(sys.argv[2])
run_stamp = sys.argv[3]
start_epoch = int(sys.argv[4])
end_epoch = int(sys.argv[5])

preflight = {}
try:
    preflight = json.loads((out / "PREFLIGHT.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    pass

items = []
for meta_path in sorted(out.glob("*/item_meta.json")):
    try:
        items.append(json.loads(meta_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        items.append({"item": meta_path.parent.name, "status": "meta_unreadable"})

# rc 文件（runner 写入）
for item in items:
    rc_path = out / item["item"] / ".rc"
    item["exit_code"] = int(rc_path.read_text().strip()) if rc_path.is_file() else None

total_cost = 0.0
cost_known = True
for item in items:
    c = item.get("cost_usd_standard_price")
    if c is None:
        cost_known = False
    else:
        total_cost += float(c)

result = {
    "schema": "n4_e2e_llm_probes/1",
    "code_root": str(root),
    "run_stamp": run_stamp,
    "wall_seconds_total": end_epoch - start_epoch,
    "wall_minutes_total": round((end_epoch - start_epoch) / 60, 2),
    "preflight": preflight,
    "items": items,
    "total_cost_usd_standard_price": round(total_cost, 6) if cost_known else None,
    "cost_note": "标准价目表上界（非错峰/缓存价）；未登记价格时 None",
}
(out / "ITEM_RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

lines = []
add = lines.append
add("# N-4 真实 LLM 重型功能探针：逐项观测汇总（脚本直出）")
add("")
add(f"> 运行 {run_stamp}；总墙钟 {result['wall_minutes_total']}min；总成本（标准价上界）≈ ${result['total_cost_usd_standard_price']}")
add("> 数字均来自各 item 的批次 JSON / 日志 / trace，不手写；结论与缺陷清单见 README.md。")
add("")
add("| item | exit | 墙钟(s) | tokens | 成本($) | 行数 | stop_reason | trace 节点命中 |")
add("|---|---|---|---|---|---|---|---|")
for item in items:
    tm = item.get("tokens") or {}
    rows = item.get("rows") or []
    stops = sorted({str(r.get("stop_reason")) for r in rows if r.get("stop_reason") is not None})
    nodes = sorted((item.get("trace") or {}).get("node_event_counts", {}).keys())
    add(
        f"| `{item.get('item')}` | {item.get('exit_code')} | {item.get('wall_seconds')} | "
        f"{tm.get('total_tokens', 0)} | {item.get('cost_usd_standard_price')} | {len(rows)} | "
        f"{', '.join(stops) if stops else '—'} | {', '.join(nodes) if nodes else '—'} |"
    )
add("")
add("## 逐项关键观测（字段恒 None / 路径进入证据）")
add("")
for item in items:
    add(f"### `{item.get('item')}`")
    add("")
    if item.get("status") == "blocked":
        add(f"- **blocked**：{item.get('reason')}")
        add("")
        continue
    add(f"- exit={item.get('exit_code')}，墙钟 {item.get('wall_seconds')}s，batches={len(item.get('batch_files') or [])}，rows={len(item.get('rows') or [])}")
    if item.get("cost_usd_standard_price") is not None:
        add(f"- tokens={item.get('tokens')}，成本≈${item.get('cost_usd_standard_price')}")
    fn = item.get("field_none_counts") or {}
    if fn:
        add("- 字段 None/空计数：" + "，".join(f"`{k}`={v}" for k, v in fn.items()))
    trace = item.get("trace") or {}
    add(f"- trace：{trace.get('files')} 文件；节点事件计数={trace.get('node_event_counts')}")
    venv = item.get("venv_cache_touched_in_window") or []
    if venv:
        add(f"- venv 缓存时间窗命中：{len(venv)} 个（{', '.join(v['name'] for v in venv[:5])}…）")
    hits = item.get("log_keyword_hits") or {}
    if hits:
        add("- 日志关键词命中：" + "，".join(f"`{k}`×{v.get('count')}" for k, v in list(hits.items())[:12]))
    for row in (item.get("rows") or [])[:5]:
        add(f"  - row `{row.get('task_id')}`：passed={row.get('passed')} iterations={row.get('iterations')} "
            f"stop_reason={row.get('stop_reason')} diagnosis={'✓' if row.get('diagnosis_present') else '✗'} "
            f"patch={'✓' if row.get('patch_present') else '✗'} repair_history_len={row.get('repair_history_len')} "
            f"spec_compile_rate={row.get('spec_compile_rate')} spec_oracle_injected={row.get('spec_oracle_injected')} "
            f"spec_oracle_verdict={row.get('spec_oracle_verdict')} rag_stats={'✓' if row.get('rag_stats') else '✗'} "
            f"cross_file_deps={row.get('cross_file_deps')} difficulty={row.get('task_metadata_difficulty')} "
            f"token_budget_capped={row.get('token_budget_capped')}")
    if item.get("log_warnings_errors"):
        add("- 日志告警/错误样本：")
        for ln in item["log_warnings_errors"][:5]:
            add(f"  - `{ln}`")
    add("")

(out / "ITEM_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"ITEM_RESULTS：{out / 'ITEM_RESULTS.json'} / .md（items={len(items)}，总成本≈${result['total_cost_usd_standard_price']}）")
PY

# ─── 公共 env（顺序执行、每项独立 namespace/trace；显式 unset 可能串味的开关）──
_UNSETS=(-u DOC_ANCHOR_TABLE -u AITESTER_QUIXBUGS_DATA -u ENABLE_RAG -u CROSS_FILE_ENABLE
    -u COST_BUDGET_ENABLE -u COST_BUDGET_TOKENS -u COST_BUDGET_USD -u COST_USD_PER_1K
    -u EXECUTOR_USE_VENV -u AITESTER_PROFILE -u AITESTER_TRACE_DIR -u AITESTER_CACHE_NAMESPACE
    -u LLM_REASONING_EFFORT -u LLM_MAX_OUTPUT_TOKENS -u AITESTER_SMOKE_LLM -u AITESTER_E2E_LLM)
_BASE_ENV=("AITESTER_PROFILE=logic" "TEMPERATURE=0.0" "LLM_THINKING_MODE=disabled" "BENCHMARK_PARALLELISM=1" "AITESTER_LLM_CACHE=0"
    # 探针成本裁剪（如实记录于每项 log/env）：只关非目标的后处理测量/迭代上限，
    # 不改 logic 主链路装配（planner/generator/executor/debugger/spec_ir/DSL/oracle/守卫全在）。
    # 动机：QuixBugs bitcount 等"缺陷实现不终止"家族在默认 MAX_ITERATIONS=3 +
    # 变异/O3 后处理下每任务可达数分钟，7 项顺序探针会超 90min 墙钟上限。
    "MAX_ITERATIONS=1" "ENABLE_MUTATION_SCORING=false" "BRANCH_COVERAGE_INJECT_ENABLE=false" "MUTATION_ADVISOR_ENABLE=false")
ITEM_ENV=()

_ITEM_IDS=()
_ITEM_NAMES=()
_ITEM_RCS=()

_run_item() { # id name timeout_seconds cache_ns cmd...
    local id="$1" name="$2" to="$3" ns="$4"
    shift 4
    local dir="${OUT}/${id}"
    local log="${dir}/run.log"
    mkdir -p "${dir}/traces"
    local start_epoch start_iso end_epoch end_iso wall
    start_epoch="$(date +%s)"
    start_iso="$(date -u +%FT%TZ)"
    {
        echo "=== N-4 ${id} ${name} ==="
        echo "START_ISO_UTC=${start_iso} START_EPOCH=${start_epoch}"
        echo "CODE_ROOT=${ROOT} RUNNER_REPO=${SCRIPT_REPO}"
        echo "GIT_HEAD=$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo '?')"
        echo "GIT_DIRTY_LINES=$(git -C "${ROOT}" status --porcelain 2>/dev/null | grep -c . || true)"
        echo "CACHE_NAMESPACE=${ns}"
        echo "TRACE_DIR=${dir}/traces"
        printf 'ITEM_ENV:'
        printf ' %q' "${_BASE_ENV[@]}" ${ITEM_ENV[@]+"${ITEM_ENV[@]}"}
        printf '\nCMD:'
        printf ' %q' "$@"
        printf '\n'
    } >> "${log}"
    echo "  [${id}] ${name} …"
    local rc
    set +e
    ( cd "${ROOT}" && "${PY}" "${OUT}/_helpers/limited_run.py" "${to}" env "${_UNSETS[@]}" "${_BASE_ENV[@]}" \
        "AITESTER_CACHE_NAMESPACE=${ns}" "AITESTER_TRACE_DIR=${dir}/traces" ${ITEM_ENV[@]+"${ITEM_ENV[@]}"} "$@" ) \
        2>&1 | tee -a "${log}"
    rc=${PIPESTATUS[0]}
    set -e
    end_epoch="$(date +%s)"
    end_iso="$(date -u +%FT%TZ)"
    wall=$((end_epoch - start_epoch))
    {
        echo "END_ISO_UTC=${end_iso} END_EPOCH=${end_epoch} EXIT_CODE=${rc} WALL_SECONDS=${wall}"
        echo "GIT_STATUS_AFTER_LINES=$(git -C "${ROOT}" status --porcelain 2>/dev/null | grep -c . || true)"
    } >> "${log}"
    echo "${rc}" > "${OUT}/${id}/.rc"
    "${PY}" "${OUT}/_helpers/extract_item.py" "${dir}" "${log}" "${dir}/item_meta.json" \
        "${ROOT}/experiments/price_table.json" "${start_epoch}" "${end_epoch}" || true
    _ITEM_IDS+=("${id}")
    _ITEM_NAMES+=("${name}")
    _ITEM_RCS+=("${rc}")
    echo "  [${id}] 结束：exit=${rc} wall=${wall}s（log：${log}）"
}

# ─── 00 LLM 连通性冒烟（失败即中止，避免烧钱空跑） ──────────────────────────
echo ""
echo "[00] LLM 连通性冒烟（1 次极小调用）"
mkdir -p "${OUT}/00_llm_smoke"
SMOKE_START="$(date +%s)"
set +e
( cd "${ROOT}" && env "${_UNSETS[@]}" "AITESTER_SMOKE_LLM=true" "AITESTER_LLM_CACHE=0" "AITESTER_PROFILE=logic" \
    "TEMPERATURE=0.0" "LLM_THINKING_MODE=disabled" "AITESTER_CACHE_NAMESPACE=e2e_llm_probes_20261017_00_smoke" \
    "${PY}" "${ROOT}/experiments/run_smoke_llm.py" --require-json ) 2>&1 | tee "${OUT}/00_llm_smoke/run.log"
SMOKE_RC=${PIPESTATUS[0]}
set -e
SMOKE_WALL=$(( $(date +%s) - SMOKE_START ))
echo "SMOKE_RC=${SMOKE_RC} WALL_SECONDS=${SMOKE_WALL}" >> "${OUT}/00_llm_smoke/run.log"
if [ "${SMOKE_RC}" -ne 0 ]; then
    echo "✗ LLM 冒烟失败（exit=${SMOKE_RC}）——真实 LLM 探针中止（不烧钱空跑）。见 ${OUT}/00_llm_smoke/run.log" >&2
    exit 3
fi

# ─── N-3 就绪判定（item07） ─────────────────────────────────────────────────
ORACLE_READY=0
if [ -f "${ROOT}/tests/test_oracle_independent_judging.py" ] \
    && grep -q "oracle_suite_verdict" "${ROOT}/src/graph/nodes.py" 2>/dev/null \
    && grep -q "llm_suite_detection_rate" "${ROOT}/experiments/_m1_metrics.py" 2>/dev/null; then
    ORACLE_READY=1
fi

# ─── PREFLIGHT（只读记录：git/依赖/冒烟/N-3/LLM 配置） ──────────────────────
"${PY}" - "${ROOT}" "${OUT}/PREFLIGHT.json" "${ORACLE_READY}" "${SMOKE_RC}" "${SMOKE_WALL}" "${SCRIPT_REPO}" "${OUT}" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root, out_path, oracle_ready, smoke_rc, smoke_wall, runner_repo, out_dir = sys.argv[1:8]
root = Path(root)


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


payload = {
    "run": "N-4 e2e llm probes",
    "code_root": str(root),
    "runner_repo": runner_repo,
    "out_dir": out_dir,
    "probe_context_note": "代码根为冻结快照（--root worktree）；产物写入主仓 results 目录（gitignored）。",
    "git": {"head": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain")),
            "dirty_lines": [ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()]},
    "llm_smoke": {"exit_code": int(smoke_rc), "wall_seconds": int(smoke_wall),
                  "log": "00_llm_smoke/run.log"},
    "oracle_ready_n3": bool(int(oracle_ready)),
    "python": sys.version.split()[0],
    "price_table": str(root / "experiments/price_table.json"),
}
Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload["git"], ensure_ascii=False))
PY

# ─── 01 logic 档全链路（3 个 QuixBugs buggy 任务） ───────────────────────────
if [[ "${SKIP_ITEMS}" != *",01,"* ]]; then
    ITEM_ENV=()
    _run_item "01_logic_fullchain" "logic 档全链路 aitester ×3" 1200 \
        "e2e_llm_probes_20261017_01_logic" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 3 --seed 42 \
        --baselines aitester --output-dir "${OUT}/01_logic_fullchain" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 02 RAG 开（2 任务） ─────────────────────────────────────────────────────
if [[ "${SKIP_ITEMS}" != *",02,"* ]]; then
    ITEM_ENV=("ENABLE_RAG=true")
    _run_item "02_rag_enabled" "RAG 开 aitester ×2" 1200 \
        "e2e_llm_probes_20261017_02_rag" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 2 --seed 42 \
        --baselines aitester --output-dir "${OUT}/02_rag_enabled" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 03 跨文件 synthetic level3（2 任务） ────────────────────────────────────
if [[ "${SKIP_ITEMS}" != *",03,"* ]]; then
    ITEM_ENV=("CROSS_FILE_ENABLE=true")
    _run_item "03_cross_file" "跨文件 synthetic level3 aitester ×2" 1500 \
        "e2e_llm_probes_20261017_03_cross_file" \
        "${PY}" "${OUT}/_helpers/run_cross_file.py" "${ROOT}" "${OUT}/03_cross_file" "${_CROSS_REASON}"
fi

# ─── 04 venv 执行器（1 任务） ────────────────────────────────────────────────
if [[ "${SKIP_ITEMS}" != *",04,"* ]]; then
    ITEM_ENV=("EXECUTOR_USE_VENV=true")
    _run_item "04_venv_executor" "venv 执行器 aitester ×1" 1200 \
        "e2e_llm_probes_20261017_04_venv" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 1 --seed 42 \
        --baselines aitester --output-dir "${OUT}/04_venv_executor" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 05a 预算停止（USD 路径；重点核验是否真触发） ────────────────────────────
if [[ "${SKIP_ITEMS}" != *",05a,"* ]]; then
    ITEM_ENV=("COST_BUDGET_ENABLE=true" "COST_BUDGET_USD=0.0001" "COST_USD_PER_1K=0.3")
    _run_item "05a_budget_usd" "预算 USD 路径 aitester ×1" 900 \
        "e2e_llm_probes_20261017_05a_budget_usd" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 1 --seed 42 \
        --baselines aitester --output-dir "${OUT}/05a_budget_usd" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 05b 预算停止（token 路径阳性对照） ──────────────────────────────────────
if [[ "${SKIP_ITEMS}" != *",05b,"* ]]; then
    ITEM_ENV=("COST_BUDGET_ENABLE=true" "COST_BUDGET_TOKENS=100")
    _run_item "05b_budget_tokens" "预算 token 路径阳性对照 aitester ×1" 900 \
        "e2e_llm_probes_20261017_05b_budget_tokens" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 1 --seed 42 \
        --baselines aitester --output-dir "${OUT}/05b_budget_tokens" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 06 安全档（safe profile） ──────────────────────────────────────────────
if [[ "${SKIP_ITEMS}" != *",06,"* ]]; then
    ITEM_ENV=("AITESTER_PROFILE=safe")
    _run_item "06_safe_profile" "safe 档 aitester ×1" 1200 \
        "e2e_llm_probes_20261017_06_safe" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 1 --seed 42 \
        --baselines aitester --output-dir "${OUT}/06_safe_profile" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
fi

# ─── 07 oracle 冒烟（依赖 N-3；未就绪 → blocked） ────────────────────────────
echo ""
echo "[07] oracle 冒烟（依赖 N-3 提交）"
if [ "${ORACLE_READY}" -eq 1 ] && [[ "${SKIP_ITEMS}" != *",07,"* ]]; then
    ITEM_ENV=("SPEC_ORACLE_EXEC_ENABLE=true")
    _run_item "07_oracle_smoke" "oracle 冒烟 df_spec 臂 ×1" 900 \
        "e2e_llm_probes_20261017_07_oracle" \
        "${PY}" "${ROOT}/experiments/run_main_batch.py" --dataset quixbugs --task-limit 1 --seed 42 \
        --baselines plain_llm_df_spec --output-dir "${OUT}/07_oracle_smoke" --skip-stats \
        ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"}
else
    mkdir -p "${OUT}/07_oracle_smoke"
    "${PY}" - "${OUT}/07_oracle_smoke/item_meta.json" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "item": "07_oracle_smoke",
    "status": "blocked",
    "reason": "N-3 未提交（tests/test_oracle_independent_judging.py 缺失 / oracle_suite_verdict·llm_suite_detection_rate 接线未落地）——按 N-4 任务书记录 blocked 并跳过；未消耗 LLM 调用。",
    "checked_markers": [
        "tests/test_oracle_independent_judging.py",
        "src/graph/nodes.py::oracle_suite_verdict",
        "experiments/_m1_metrics.py::llm_suite_detection_rate",
    ],
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("[07] blocked：N-3 未就绪，跳过（不消耗 LLM）")
PY
fi

# ─── 汇总（ITEM_RESULTS.json/.md） ──────────────────────────────────────────
echo ""
echo "[汇总] ITEM_RESULTS.json / ITEM_RESULTS.md"
"${PY}" "${OUT}/_helpers/summarize.py" "${OUT}" "${ROOT}" "${RUN_STAMP}" \
    "${START_ALL_EPOCH}" "$(date +%s)" 2>/dev/null || true

WALL_TOTAL=$(( $(date +%s) - START_ALL_EPOCH ))
echo ""
echo "================================================================================"
echo "N-4 探针执行完成（RUN_STAMP=${RUN_STAMP}，总墙钟 ${WALL_TOTAL}s ≈ $((WALL_TOTAL / 60))min）"
echo "  逐项 rc："
_idx=0
while [ "${_idx}" -lt "${#_ITEM_IDS[@]}" ]; do
    echo "    ${_ITEM_IDS[${_idx}]}  ${_ITEM_NAMES[${_idx}]}  exit=${_ITEM_RCS[${_idx}]}"
    _idx=$((_idx + 1))
done
echo "  输出：${OUT}"
echo "  下一步：由操作者审阅 item_meta.json/日志后写 README（缺陷清单），再生成 SHA256SUMS。"
echo "================================================================================"
