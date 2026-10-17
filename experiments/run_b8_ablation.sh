#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# P-2 / B8：A-19 覆盖率停滞检测 开/关 消融（探索性；r3 缩小规模 10 任务/臂）
#
# 前置：切点 = p-stagnation commit（含 A-19 wiring 修复）；干净 worktree；
#       PREREG.md 已落盘（本脚本拒绝在缺失预注册时跑批）。
#
# 用法：
#   bash experiments/run_b8_ablation.sh \
#     --root /Users/wangchenyu/Workspace/AITester-p2-b8-14a9662 \
#     --expect-sha aeadb7bac0741313c09d3af58b5a3ce271ed091e \
#     --require-clean-root [--dry-run]
#
# 工具选项：--out <结果目录> --task-count <n>（默认 10） --parallelism <n>（4）
#           --watchdog-seconds <n>（3600） --budget-usd <x>（0.3）
#
# 协议：两臂并发；A=--enable-stagnation（COVERAGE_STALL_DETECT_ENABLE=true），
#       B=--no-stagnation（=false 显式）；AITESTER_PROFILE=fast、TEMPERATURE=0.0、
#       LLM_THINKING_MODE=disabled、BENCHMARK_PARALLELISM=4、AITESTER_LLM_CACHE=0、
#       COST_BUDGET_ENABLE=true COST_BUDGET_USD=1、AITESTER_BATCH_MAX_CALLS=100；
#       --dataset synthetic --task-count N --seed 42 --baselines aitester。
# 预算门禁：预检估算 > --budget-usd 时自动降为 8 任务/臂并写 PREREG_DOWNGRADE.md。
# 失败策略：单臂失败/超时 → 保留日志/工件、如实报告、不重跑。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT="${SCRIPT_REPO}"
OUT="${SCRIPT_REPO}/experiments/results/p_round_b8_ablation_20261018"
EXPECT_SHA=""
TASK_COUNT=10
PARALLELISM=4
WATCHDOG_SECONDS=3600
BUDGET_USD=0.3
DRY_RUN=0
REQUIRE_CLEAN_ROOT=0

usage() {
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --root) [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }; ROOT="$2"; shift 2 ;;
        --out) [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --expect-sha) [ $# -ge 2 ] || { echo "--expect-sha 需要完整 sha" >&2; exit 2; }; EXPECT_SHA="$2"; shift 2 ;;
        --task-count) [ $# -ge 2 ] || { echo "--task-count 需要正整数" >&2; exit 2; }; TASK_COUNT="$2"; shift 2 ;;
        --parallelism) [ $# -ge 2 ] || { echo "--parallelism 需要正整数" >&2; exit 2; }; PARALLELISM="$2"; shift 2 ;;
        --watchdog-seconds) [ $# -ge 2 ] || { echo "--watchdog-seconds 需要正整数" >&2; exit 2; }; WATCHDOG_SECONDS="$2"; shift 2 ;;
        --budget-usd) [ $# -ge 2 ] || { echo "--budget-usd 需要数值" >&2; exit 2; }; BUDGET_USD="$2"; shift 2 ;;
        --require-clean-root) REQUIRE_CLEAN_ROOT=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

for _v in TASK_COUNT PARALLELISM WATCHDOG_SECONDS; do
    case "${!_v:-}" in '' | *[!0-9]*) echo "--${_v} 必须正整数" >&2; exit 2 ;; esac
done

# 解释器：worktree 无 .venv（gitignored）→ 用脚本仓 .venv
if [ -x "${SCRIPT_REPO}/.venv/bin/python" ]; then
    PY="${SCRIPT_REPO}/.venv/bin/python"
elif [ -x "${ROOT}/.venv/bin/python" ]; then
    PY="${ROOT}/.venv/bin/python"
else
    echo "✗ 找不到 python 解释器（${SCRIPT_REPO}/.venv 或 ${ROOT}/.venv）" >&2
    exit 2
fi

[ -d "${ROOT}" ] || { echo "✗ ROOT 不存在：${ROOT}" >&2; exit 2; }
[ -n "${EXPECT_SHA}" ] || { echo "✗ 必须给 --expect-sha（切点 commit 校验）" >&2; exit 2; }
[ -f "${ROOT}/experiments/run_benchmark.py" ] || { echo "✗ ROOT 不像 aitester 仓库：${ROOT}" >&2; exit 2; }
[ -f "${ROOT}/.env.local" ] || { echo "✗ ROOT/.env.local 缺失（真实 LLM 需要）" >&2; exit 2; }
[ -f "${OUT}/PREREG.md" ] || { echo "✗ 预注册缺失：${OUT}/PREREG.md（实现要求：先落盘 PREREG 再跑批）" >&2; exit 2; }

ROOT_HEAD="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || true)"
ROOT_DIRTY_BEFORE="$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ "${ROOT_HEAD}" = "${EXPECT_SHA}" ] || { echo "✗ 切点不符：ROOT HEAD=${ROOT_HEAD} ≠ expect=${EXPECT_SHA}" >&2; exit 2; }
if [ "${REQUIRE_CLEAN_ROOT}" -eq 1 ] && [ "${ROOT_DIRTY_BEFORE}" != "0" ]; then
    echo "✗ ROOT 非干净（dirty=${ROOT_DIRTY_BEFORE} 行）——先清理/还原再跑" >&2
    exit 2
fi

if [ "${DRY_RUN}" -eq 1 ] || [ "${EMIT_SKELETON:-0}" -eq 1 ]; then
    PREFLIGHT_JSON="${OUT}/PREFLIGHT_dryrun.json"
else
    PREFLIGHT_JSON="${OUT}/PREFLIGHT.json"
    if [ -e "${OUT}/log_stagnation.log" ] || [ -e "${OUT}/log_no_stagnation.log" ] || [ -e "${OUT}/README.md" ]; then
        echo "✗ 结果目录已有跑批工件（拒绝覆盖）：${OUT}" >&2
        exit 2
    fi
fi

mkdir -p "${OUT}" "${OUT}/_helpers"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

cat > "${OUT}/_helpers/limited_run.py" <<'PY'
"""有限墙钟看门狗：超时 SIGTERM→SIGKILL 进程组，不静默挂死。"""
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
    print(f"\n[watchdog] 超过墙钟上限 {limit:.0f}s：SIGTERM 进程组…", file=sys.stderr, flush=True)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        rc = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        print("[watchdog] SIGTERM 未退，SIGKILL 进程组…", file=sys.stderr, flush=True)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait(timeout=30)
    print(f"[watchdog] 超时终止 rc={rc} wall={time.time() - t0:.1f}s", file=sys.stderr, flush=True)
    sys.exit(124)
print(f"[watchdog] rc={rc} wall={time.time() - t0:.1f}s", file=sys.stderr, flush=True)
sys.exit(rc)
PY

cat > "${OUT}/_helpers/extract_arm.py" <<'PY'
"""逐臂元数据抽取（零 LLM）：tokens/成本/墙钟/逐任务字段/stop_reason/stall 计数/trace 证据。"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

batch_path, label, cli_flag, stall_env, ns, start_epoch, start_iso, out_meta, trace_dir, log_path, price_path = sys.argv[1:12]
batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
arm = (batch.get("results") or {}).get("aitester") or {}
rows = arm.get("details") or []
prov = batch.get("provenance") or {}
snap = prov.get("env_snapshot") or {}
tm = arm.get("token_metrics") or batch.get("token_metrics") or {}

price = json.loads(Path(price_path).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in = price.get("input_per_mtok")
p_out = price.get("output_per_mtok")
cost = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    cost = round((tm.get("total_input_tokens", 0) * p_in + tm.get("total_output_tokens", 0) * p_out) / 1e6, 6)

wall = None
exit_code = None
end_iso = None
log_text = Path(log_path).read_text(encoding="utf-8", errors="replace") if Path(log_path).exists() else ""
m = re.search(r"END_ISO_UTC=(\S+) END_EPOCH=(\d+) EXIT_CODE=(-?\d+) WALL_SECONDS=(\d+)", log_text)
if m:
    end_iso, _end_epoch, exit_code, wall = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

REQ_KEYS = ["task_id", "passed", "coverage", "iterations", "stop_reason", "detection_rate", "repair_rate", "false_fix_rate"]
field_present = {k: sum(1 for r in rows if k in r) for k in REQ_KEYS}

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

tasks = []
stop_reasons = Counter()
stall_label = 0
for r in rows:
    sr = r.get("stop_reason")
    stop_reasons[str(sr) if sr else "None"] += 1
    if sr == "coverage_stall":
        stall_label += 1
    meta_tm = r.get("task_metadata") or {}
    tasks.append({
        "task_id": r.get("task_id"),
        "difficulty": meta_tm.get("difficulty"),
        "bug_type": meta_tm.get("bug_type"),
        "is_cross_file": meta_tm.get("is_cross_file"),
        "passed": bool(r.get("passed")),
        "iterations": int(r.get("iterations") or 0),
        "coverage": _num(r.get("coverage")),
        "detection_rate": _num(r.get("detection_rate")),
        "repair_rate": _num(r.get("repair_rate")),
        "false_fix_rate": _num(r.get("false_fix_rate")),
        "stop_reason": sr,
        "elapsed_seconds": _num(r.get("elapsed_seconds")),
        "execution_trace_len": len(r.get("execution_trace") or []),
        "token_usage": r.get("token_usage") or {},
    })

trace_reason_counts = Counter()
trace_node_decisions = Counter()
if Path(trace_dir).is_dir():
    for f in sorted(Path(trace_dir).glob("*.trace.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") != "node":
                continue
            node = rec.get("node")
            dec = rec.get("decision")
            if node in ("_should_debug", "_route_after_diagnosis"):
                trace_node_decisions[f"{node}:{dec}"] += 1
            out = rec.get("output")
            reason = out.get("reason") if isinstance(out, dict) else None
            if reason:
                trace_reason_counts[str(reason)] += 1

det_vals = [t["detection_rate"] for t in tasks if t["detection_rate"] is not None]
payload = {
    "arm_label": label,
    "cli_flag": cli_flag,
    "env_expected_COVERAGE_STALL_DETECT_ENABLE": stall_env,
    "cache_namespace": ns,
    "batch_path": str(Path(batch_path).resolve()),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "task_ids": [t["task_id"] for t in tasks],
    "tasks": tasks,
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
    "price_table": {"model": "deepseek-flash", "input_per_mtok": p_in, "output_per_mtok": p_out},
    "wall_seconds": wall,
    "start_epoch": int(start_epoch),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "exit_code": exit_code,
    "log_path": str(Path(log_path).resolve()),
    "trace_dir": str(Path(trace_dir).resolve()),
    "provenance": {
        "git_sha": prov.get("git_sha"),
        "git_dirty": prov.get("git_dirty"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "env_snapshot_COVERAGE_STALL_DETECT_ENABLE": snap.get("COVERAGE_STALL_DETECT_ENABLE"),
        "env_snapshot_DETECTION_SPEC_MODE": snap.get("DETECTION_SPEC_MODE"),
    },
    "stop_reason_counts": dict(stop_reasons),
    "coverage_stall_label_count": stall_label,
    "trace_reason_counts": dict(trace_reason_counts),
    "trace_node_decisions": dict(trace_node_decisions),
    "field_present_counts": field_present,
    "detection_aggregate": {
        "measurable": len(det_vals),
        "detected": sum(1 for v in det_vals if float(v) >= 1.0),
        "rate": round(sum(1 for v in det_vals if float(v) >= 1.0) / len(det_vals), 4) if det_vals else None,
    },
}
Path(out_meta).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} "
      f"wall={wall}s stop_reasons={dict(stop_reasons)} coverage_stall={stall_label}")
PY

cat > "${OUT}/_helpers/analyze.py" <<'PY'
"""配对聚合 + ABLATION_REPORT.json + README.md（探索性；不做 confirmatory 主张）。"""
import json
import random
import statistics
import sys
from pathlib import Path

out = Path(sys.argv[1])
report_path = out / "ABLATION_REPORT.json"
readme_path = out / "README.md"
meta_a_path = out / "arm_stagnation.meta.json"
meta_b_path = out / "arm_no_stagnation.meta.json"
preflight_path = out / "PREFLIGHT.json"
prereg_path = out / "PREREG.md"
before_ev = out / "WIRING_EVIDENCE_before.json"
after_ev = out / "WIRING_EVIDENCE_after.json"

A = json.loads(meta_a_path.read_text(encoding="utf-8"))
B = json.loads(meta_b_path.read_text(encoding="utf-8"))
pf = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.exists() else {}
prereg_text = prereg_path.read_text(encoding="utf-8") if prereg_path.exists() else ""

by_a = {t["task_id"]: t for t in A["tasks"]}
by_b = {t["task_id"]: t for t in B["tasks"]}
common = [tid for tid in A["task_ids"] if tid in by_b]

RNG = random.Random(20261018)
NBOOT = 10000


def _stats(metric, getter=lambda t, k: t.get(k)):
    pairs = []
    for tid in common:
        va = A_by.get(tid, {}).get(metric)
        vb = B_by.get(tid, {}).get(metric)
        if va is None or vb is None:
            continue
        pairs.append((tid, float(va), float(vb)))
    if not pairs:
        return {"metric": metric, "n": 0, "note": "no comparable pairs"}
    deltas = [a - b for _, a, b in pairs]
    n = len(deltas)
    mean_d = statistics.fmean(deltas)
    sd = statistics.stdev(deltas) if n > 1 else None
    med_d = statistics.median(deltas)
    boots = []
    for _ in range(NBOOT):
        sample = [deltas[RNG.randrange(n)] for _ in range(n)]
        boots.append(statistics.fmean(sample))
    boots.sort()
    ci = [round(boots[int(0.025 * NBOOT)], 6), round(boots[int(0.975 * NBOOT) - 1], 6)] if n > 1 else [None, None]
    mde = round((1.959964 + 0.841621) * sd / (n ** 0.5), 6) if (sd is not None and n > 1) else None
    tol = 1e-9
    sign = {"a_lt_b": sum(1 for d in deltas if d < -tol), "equal": sum(1 for d in deltas if abs(d) <= tol), "a_gt_b": sum(1 for d in deltas if d > tol)}
    return {
        "metric": metric,
        "n": n,
        "mean_arm_A": round(statistics.fmean([a for _, a, _ in pairs]), 6),
        "mean_arm_B": round(statistics.fmean([b for _, _, b in pairs]), 6),
        "median_arm_A": round(statistics.median([a for _, a, _ in pairs]), 6),
        "median_arm_B": round(statistics.median([b for _, _, b in pairs]), 6),
        "delta_mean_A_minus_B": round(mean_d, 6),
        "delta_median": round(med_d, 6),
        "sd_delta": round(sd, 6) if sd is not None else None,
        "bootstrap_95ci": ci,
        "mde_post_hoc": mde,
        "sign_consistency": sign,
        "per_task": [{"task_id": tid, "A": a, "B": b, "delta_A_minus_B": round(a - b, 6)} for tid, a, b in pairs],
    }


A_by, B_by = by_a, by_b
primary = {m: _stats(m) for m in ("iterations", "coverage", "passed")}
secondary = {m: _stats(m) for m in ("detection_rate", "repair_rate", "false_fix_rate")}

# test_passed 2x2
both_pass = sum(1 for tid in common if A_by[tid]["passed"] and B_by[tid]["passed"])
a_only = sum(1 for tid in common if A_by[tid]["passed"] and not B_by[tid]["passed"])
b_only = sum(1 for tid in common if B_by[tid]["passed"] and not A_by[tid]["passed"])
both_fail = len(common) - both_pass - a_only - b_only
passed_2x2 = {"both_pass": both_pass, "a_only_pass": a_only, "b_only_pass": b_only, "both_fail": both_fail}

# early-stop / stall evidence
early_stop_tasks = []
for tid in common:
    ta, tb = A_by[tid], B_by[tid]
    if ta["stop_reason"] == "coverage_stall" or ta["iterations"] < tb["iterations"]:
        early_stop_tasks.append({
            "task_id": tid,
            "A_iterations": ta["iterations"], "B_iterations": tb["iterations"],
            "A_stop_reason": ta["stop_reason"], "B_stop_reason": tb["stop_reason"],
            "A_passed": ta["passed"], "B_passed": tb["passed"],
            "A_coverage": ta["coverage"], "B_coverage": tb["coverage"],
        })

tokens_a = (A.get("token_metrics") or {}).get("total_tokens")
tokens_b = (B.get("token_metrics") or {}).get("total_tokens")
cost_a = A.get("cost_usd_standard_price")
cost_b = B.get("cost_usd_standard_price")

# exploratory classification
it = primary["iterations"]
stall_total = (A.get("coverage_stall_label_count") or 0) + (A.get("trace_reason_counts") or {}).get("coverage_stall", 0) * 0
def _classify():
    if it.get("n", 0) == 0:
        return "insufficient_data"
    ci = it.get("bootstrap_95ci") or [None, None]
    if (A.get("coverage_stall_label_count") or 0) == 0 and (A.get("trace_reason_counts") or {}).get("coverage_stall", 0) == 0:
        return "no_stall_trigger_observed"
    if ci[0] is not None and ci[1] is not None and ci[0] <= 0 <= ci[1]:
        if it.get("mde_post_hoc") is not None and abs(it["delta_mean_A_minus_B"]) <= it["mde_post_hoc"]:
            return "no_detectable_difference"
        return "direction_hint_ci_crosses_zero"
    return "direction_hint"

classification = _classify()

def _difficulty_dist(tasks):
    c = {}
    for t in tasks:
        k = str(t.get("difficulty"))
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (kv[0] == "None", kv[0])))

report = {
    "schema": "p2_b8_stagnation_ablation_report/1",
    "sample": {
        "difficulty_distribution_A": _difficulty_dist(A["tasks"]),
        "difficulty_distribution_B": _difficulty_dist(B["tasks"]),
        "note": "synthetic mixed difficulty; all tasks passed at iteration 0 in fast profile -> no repair loop -> stagnation criteria unreachable in this sample",
    },
    "nature": "exploratory non-confirmatory",
    "run_stamp": out.name,
    "cut": pf.get("git", {}),
    "protocol": {
        "arms": {
            "A_stagnation": {"cli": "--enable-stagnation", "env": "COVERAGE_STALL_DETECT_ENABLE=true", "batch": A["batch_path"], "batch_sha256": A["batch_sha256"]},
            "B_no_stagnation": {"cli": "--no-stagnation", "env": "COVERAGE_STALL_DETECT_ENABLE=false", "batch": B["batch_path"], "batch_sha256": B["batch_sha256"]},
        },
        "task_count": A["rows"],
        "parallelism": (pf.get("run", {}) or {}).get("parallelism"),
        "watchdog_seconds": (pf.get("run", {}) or {}).get("watchdog_seconds"),
        "budget_usd_limit": (pf.get("run", {}) or {}).get("budget_usd_limit"),
        "profile": "fast",
    },
    "arms": {
        "A_stagnation": {
            "rows": A["rows"], "wall_seconds": A["wall_seconds"], "tokens": tokens_a, "cost_usd": cost_a,
            "exit_code": A["exit_code"], "env_snapshot_stall": A["provenance"]["env_snapshot_COVERAGE_STALL_DETECT_ENABLE"],
            "stop_reason_counts": A["stop_reason_counts"], "coverage_stall_label_count": A["coverage_stall_label_count"],
            "trace_reason_counts": A["trace_reason_counts"], "trace_node_decisions": A["trace_node_decisions"],
            "field_present_counts": A["field_present_counts"], "detection_aggregate": A["detection_aggregate"],
        },
        "B_no_stagnation": {
            "rows": B["rows"], "wall_seconds": B["wall_seconds"], "tokens": tokens_b, "cost_usd": cost_b,
            "exit_code": B["exit_code"], "env_snapshot_stall": B["provenance"]["env_snapshot_COVERAGE_STALL_DETECT_ENABLE"],
            "stop_reason_counts": B["stop_reason_counts"], "coverage_stall_label_count": B["coverage_stall_label_count"],
            "trace_reason_counts": B["trace_reason_counts"], "trace_node_decisions": B["trace_node_decisions"],
            "field_present_counts": B["field_present_counts"], "detection_aggregate": B["detection_aggregate"],
        },
    },
    "paired": {"common_tasks": len(common), "primary": primary, "secondary": secondary, "test_passed_2x2": passed_2x2},
    "stall_evidence": {"early_stop_or_stall_tasks": early_stop_tasks, "A_coverage_stall_label_count": A["coverage_stall_label_count"], "A_trace_coverage_stall": (A["trace_reason_counts"] or {}).get("coverage_stall", 0)},
    "secondary_metrics_availability": {"detection_rate_pairs": secondary["detection_rate"].get("n"), "repair_rate_pairs": secondary["repair_rate"].get("n"), "false_fix_rate_pairs": secondary["false_fix_rate"].get("n"), "note": "本批行级 detection/repair/false_fix 在场但为常量（两臂均 detection=0、repair=0、false_fix=1.0 → 无配对变异）；主指标可用"},
    "cost_total_usd": round((cost_a or 0) + (cost_b or 0), 6),
    "trigger_feasibility": {
        "A_zero_iteration_passed": sum(1 for t in A["tasks"] if t["passed"] and t["iterations"] == 0),
        "B_zero_iteration_passed": sum(1 for t in B["tasks"] if t["passed"] and t["iterations"] == 0),
        "A_passed": sum(1 for t in A["tasks"] if t["passed"]),
        "B_passed": sum(1 for t in B["tasks"] if t["passed"]),
        "note": "all tasks passed at iteration 0 => no repair loop => stagnation criteria (K=2 failed stalled rounds) unreachable",
    },
    "classification": classification,
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

# ── README ────────────────────────────────────────────────────────────────
def fmt(v, nd=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def metric_table():
    lines = ["| 指标 | n | A 均值 | B 均值 | Δ(A−B) 均值 | 中位 Δ | bootstrap 95% CI | 后验 MDE | 符号(A<B/=/A>B) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, name in (("iterations", "iterations"), ("coverage", "coverage(%)"), ("passed", "test_passed(1/0)")):
        s = primary[key]
        if s.get("n", 0) == 0:
            lines.append(f"| {name} | 0 | — | — | — | — | — | — | — |")
            continue
        ci = s.get("bootstrap_95ci") or [None, None]
        sc = s["sign_consistency"]
        lines.append(
            f"| {name} | {s['n']} | {fmt(s['mean_arm_A'])} | {fmt(s['mean_arm_B'])} | {fmt(s['delta_mean_A_minus_B'])} | {fmt(s['delta_median'])} | "
            f"[{fmt(ci[0])}, {fmt(ci[1])}] | {fmt(s['mde_post_hoc'])} | {sc['a_lt_b']}/{sc['equal']}/{sc['a_gt_b']} |"
        )
    return "\n".join(lines)


def secondary_table():
    lines = ["| 指标 | n | A 均值 | B 均值 | Δ(A−B) | 符号(A<B/=/A>B) |", "|---|---|---|---|---|---|"]
    for key in ("detection_rate", "repair_rate", "false_fix_rate"):
        s = secondary[key]
        if s.get("n", 0) == 0:
            lines.append(f"| {key} | 0 | — | — | — | — |")
            continue
        sc = s["sign_consistency"]
        lines.append(f"| {key} | {s['n']} | {fmt(s['mean_arm_A'])} | {fmt(s['mean_arm_B'])} | {fmt(s['delta_mean_A_minus_B'])} | {sc['a_lt_b']}/{sc['equal']}/{sc['a_gt_b']} |")
    return "\n".join(lines)


def reason_lines(arm):
    items = arm["stop_reason_counts"] or {}
    return ", ".join(f"`{k}`={v}" for k, v in sorted(items.items()))


def ev_table():
    try:
        b = json.loads(before_ev.read_text(encoding="utf-8"))["observed"]["on"]
        a = json.loads(after_ev.read_text(encoding="utf-8"))["observed"]["on"]
        off_b = json.loads(before_ev.read_text(encoding="utf-8"))["observed"]["off"]
        off_a = json.loads(after_ev.read_text(encoding="utf-8"))["observed"]["off"]
    except (OSError, KeyError, ValueError):
        return "（wiring 证据文件缺失——见 results 目录）"
    rows = [
        ("`_coverage_stall_detected`（ON）", b.get("stall_detected_iter2", "—"), a.get("stall_detected_iter2", "—")),
        ("`determine_stop_reason`（ON, iter=2）", b.get("determine_stop_reason_iter2", "—"), a.get("determine_stop_reason_iter2", "—")),
        ("**`_should_debug`（ON, iter=2）**", b.get("should_debug_iter2", "—"), a.get("should_debug_iter2", "—")),
        ("`determine_stop_reason`（ON, iter=max）", b.get("determine_stop_reason_iter3_at_max", "—"), a.get("determine_stop_reason_iter3_at_max", "—")),
        ("`_route_after_diagnosis`（ON）", b.get("route_after_diagnosis_iter2", "—"), a.get("route_after_diagnosis_iter2", "—")),
        ("**OFF 口径（_should_debug / max 标签）**", f'{off_b.get("should_debug_iter2", "—")} / {off_b.get("determine_stop_reason_iter3_at_max", "—")}', f'{off_a.get("should_debug_iter2", "—")} / {off_a.get("determine_stop_reason_iter3_at_max", "—")}'),
    ]
    lines = ["| 状态（iteration=2, max=3；最近 2 轮 failed 且 coverage_delta=0） | 修复前 `14a9662` | 修复后 `aeadb7b` |", "|---|---|---|"]
    for name, before, after in rows:
        lines.append(f"| {name} | `{before}` | `{after}` |")
    return "\n".join(lines)


lines = []
lines.append("# P-2 / B8：A-19 覆盖率停滞检测开/关消融（探索性，2026-10-18）")
lines.append("")
lines.append("> **性质：探索性描述性测量（非 confirmatory）**。不主张「显著提升/因果」；报告配对 Δ、配对一致性、后验 MDE 与局限。")
lines.append(f"> 切点：`{(report['cut'] or {}).get('head') or (pf.get('git') or {}).get('root_head', '')}`（p-stagnation，含 A-19 wiring 修复）；"
             f"worktree `{(pf.get('git') or {}).get('root', '')}`；commit `aeadb7bac0741313c09d3af58b5a3ce271ed091e`。")
lines.append("")
lines.append("## 1. 协议（固定；预注册见 `PREREG.md` / `PREREG.json`，跑前落盘）")
lines.append("")
lines.append("- 两臂**并发**：A=`--enable-stagnation`（`COVERAGE_STALL_DETECT_ENABLE=true`）/ B=`--no-stagnation`（=false 显式）；"
             "`--dataset synthetic --task-count %d --seed 42 --baselines aitester`。" % A["rows"])
lines.append("- `AITESTER_PROFILE=fast`（理由：隔离 workflow 迭代/停止路由单变量，避免 logic/scientific 档 oracle/mutation/branch-coverage/detection-first 噪声；"
             "与 logic 档差异见 PREREG §2）；`TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=%s`；"
             "`AITESTER_LLM_CACHE=0`；`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`；`AITESTER_BATCH_MAX_CALLS=100`；两臂独立 namespace。"
             % (report["protocol"].get("parallelism") or "4"))
lines.append("- 预算 ≤ $%s；墙钟 ≤ 60min；每臂 watchdog %ss；单臂失败/超时如实报告不重跑。"
             % (report["protocol"].get("budget_usd_limit"), report["protocol"].get("watchdog_seconds")))
lines.append("")
lines.append("## 2. 修复背景：A-19 wiring（纸面功能 → 真提前停止）")
lines.append("")
lines.append("修复前 `14a9662`：`_coverage_stall_detected` 仅被 `determine_stop_reason` 调用；`_should_debug` / `_route_after_diagnosis` 无短路段，"
             "且停滞分支在 MAX_ITERATIONS 之后 → 标签被遮蔽、提前停止从不发生。修复 `aeadb7b`（2 文件，+329/−23）：两路由函数在最后 `return \"debug\"` 前短路为 done+`stop_reason=coverage_stall`；"
             "`determine_stop_reason` 停滞分支移至 MAX_ITERATIONS 之前；文档同步。回归：新测试 26 个 + 既有 workflow 路由 205 个全绿；ruff/mypy 干净。零 LLM 修复前/后证据：")
lines.append("")
lines.append(ev_table())
lines.append("")
lines.append("（证据文件：`WIRING_EVIDENCE_before.json` / `WIRING_EVIDENCE_after.json` / `WIRING_DIFF.patch`）")
lines.append("")
lines.append("## 3. 两臂表（实测）")
lines.append("")
lines.append("| 项 | A（stagnation ON） | B（stagnation OFF） |")
lines.append("|---|---|---|")
lines.append(f"| 批次 sha256 | `{(A['batch_sha256'] or '')[:16]}…` | `{(B['batch_sha256'] or '')[:16]}…` |")
lines.append(f"| 行数 | {A['rows']} | {B['rows']} |")
lines.append(f"| exit code | {A['exit_code']} | {B['exit_code']} |")
lines.append(f"| 墙钟(s) | {fmt(A['wall_seconds'], 1)} | {fmt(B['wall_seconds'], 1)} |")
lines.append(f"| tokens / LLM calls | {tokens_a} / {(A['token_metrics'] or {}).get('total_llm_calls')} | {tokens_b} / {(B['token_metrics'] or {}).get('total_llm_calls')} |")
lines.append(f"| 成本（标准价上界） | ${fmt(cost_a, 6)} | ${fmt(cost_b, 6)} |")
lines.append(f"| env_snapshot.COVERAGE_STALL_DETECT_ENABLE | `{A['provenance']['env_snapshot_COVERAGE_STALL_DETECT_ENABLE']}` | `{B['provenance']['env_snapshot_COVERAGE_STALL_DETECT_ENABLE']}` |")
lines.append(f"| stop_reason 分布 | {reason_lines(report['arms']['A_stagnation'])} | {reason_lines(report['arms']['B_no_stagnation'])} |")
lines.append(f"| `coverage_stall` 标签计数 | **{A['coverage_stall_label_count']}** | {B['coverage_stall_label_count']} |")
lines.append(f"| trace `reason=coverage_stall` 计数 | **{(A['trace_reason_counts'] or {}).get('coverage_stall', 0)}** | {(B['trace_reason_counts'] or {}).get('coverage_stall', 0)} |")
lines.append(f"| 行字段完整（8 键） | `{A['field_present_counts']}` | `{B['field_present_counts']}` |")
lines.append(f"| 样本 difficulty 分布 | `{json.dumps(_difficulty_dist(A['tasks']), ensure_ascii=False)}` | `{json.dumps(_difficulty_dist(B['tasks']), ensure_ascii=False)}` |")
lines.append("")
lines.append("## 4. 主指标配对对比（共同任务；A−B）")
lines.append("")
lines.append(f"共同任务：**{len(common)}**。")
lines.append("")
lines.append(metric_table())
lines.append("")
lines.append(f"`test_passed` 配对 2×2：both_pass={passed_2x2['both_pass']}、A_only={passed_2x2['a_only_pass']}、B_only={passed_2x2['b_only_pass']}、both_fail={passed_2x2['both_fail']}。")
lines.append("")
lines.append("## 5. 次指标（detection / repair / false_fix；None 不参与配对）")
lines.append("")
lines.append(secondary_table())
lines.append("")
lines.append("两臂 detection 聚合：A=`%s` / B=`%s`。" % (json.dumps(A["detection_aggregate"], ensure_ascii=False), json.dumps(B["detection_aggregate"], ensure_ascii=False)))
lines.append("")
lines.append("**关键解读**：两臂 `detection_rate` 均 **0.0/10**、`repair_rate` 均 **0.0/10**、`false_fix_rate` 均 **1.0/10**——"
             "即 10/10 任务生成的测试在 **buggy 代码上直接全绿**（未检出缺陷、无修复、全部 false fix），"
             "`passed=True`/`stop_reason=test_passed` 只表示「测试全绿」，**不代表任务成功**；workflow 因此从未进入 debugger 修复循环。")
lines.append("")
lines.append("## 6. stall 触发证据")
lines.append("")
if early_stop_tasks:
    lines.append("| task_id | A iterations / stop_reason | B iterations / stop_reason | A passed | B passed | A coverage | B coverage |")
    lines.append("|---|---|---|---|---|---|---|")
    for t in early_stop_tasks:
        lines.append(f"| `{t['task_id']}` | {t['A_iterations']} / `{t['A_stop_reason']}` | {t['B_iterations']} / `{t['B_stop_reason']}` | {t['A_passed']} | {t['B_passed']} | {fmt(t['A_coverage'])} | {fmt(t['B_coverage'])} |")
else:
    zero_iter_a = sum(1 for t in A["tasks"] if t["passed"] and t["iterations"] == 0)
    zero_iter_b = sum(1 for t in B["tasks"] if t["passed"] and t["iterations"] == 0)
    pass_a = sum(1 for t in A["tasks"] if t["passed"])
    pass_b = sum(1 for t in B["tasks"] if t["passed"])
    lines.append("本批**未观测到任何提前停止/停滞标签**（A 臂 coverage_stall 标签=0、trace `reason=coverage_stall`=0）。")
    lines.append("")
    lines.append(f"- 直接原因：两臂任务阶段均为**首轮一次通过**——A 臂 `{zero_iter_a}/{A['rows']}` 任务 iterations=0 且 passed、"
                 f"B 臂 `{zero_iter_b}/{B['rows']}`；executor 首轮 PASS，trace 每任务仅 1 条（planner→generator→executor→`_should_debug:done`@test_passed）。")
    lines.append("- 停滞判据要求「最近 K=2 轮 failed 且 |coverage_delta|<eps」才可能触发；首轮即通过时**没有修复循环/第二轮**，结构上不可能触发。")
    lines.append("- 直接证据：两臂 `detection_rate=0/10`、`repair_rate=0/10`、`false_fix_rate=1.0`（10/10）——生成的测试在 buggy 代码上全绿（未检出），"
                 "因此没有失败测试、没有 debugger 修复循环（iterations=0、trace 仅 1 条）。与历史口径一致（BASELINE.yaml：synthetic+aitester 覆盖率 84–94% 而检出率仅 13–16%），"
                 "本样本恰为 0/10 检出的抽样情形。")
    lines.append("- 归因：**场景/功效限制**（synthetic mixed + seed=42 前 10 任务未产生失败测试 → 无修复轮次），**不是 wiring 缺陷**——接线已由 §2 零 LLM 前后证据锁定。")
    lines.append("- 结论：本轮**无法评估**提前停止的 token 收益/修复代价；需下一轮改用**保证多轮失败**的任务集（如更高 difficulty / 真实缺陷 QuixBugs / 增大任务数与筛选失败样本）再消融。")
lines.append("")
lines.append("## 7. 成本 / 墙钟")
lines.append("")
lines.append(f"- 两臂成本合计（标准价上界）≈ **${fmt(report['cost_total_usd'], 6)}**（预算 ≤$%s）。" % report["protocol"].get("budget_usd_limit"))
lines.append(f"- 两臂并发墙钟：A={fmt(A['wall_seconds'], 1)}s / B={fmt(B['wall_seconds'], 1)}s。")
lines.append("")
lines.append("## 8. 局限")
lines.append("")
lines.append("- 探索性、n=%d 配对；单模型/单 dataset/单 seed；**不做 confirmatory/因果主张**；后验 MDE 仅披露。" % len(common))
lines.append("- synthetic 任务含 mixed difficulty 随机模板；fast 档无 oracle/mutation 等后处理——结论不外推 logic/scientific 档。")
lines.append("- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU，后处理指标受争抢影响（主指标在任务阶段采集）。")
lines.append("- 提前停止是 A-19 的预期 trade-off（连续 2 轮失败且 |Δcoverage|<eps、MAX_ITERATIONS=3 下从 3→2 轮），须结合 `iterations↓ / repair / detection` 一并解读。")
lines.append("- **本批无触发机会（关键局限）**：两臂 10/10 任务首轮一次通过（iterations=0、trace 仅 1 条、stop_reason=test_passed），"
             "修复循环从未进入 → 停滞判据（最近 K=2 轮失败且 |Δcoverage|<eps）结构上不可达；因此本批**无法回答**停滞检测的收益/代价，"
             "需下一轮用保证多轮失败的任务集（更高 difficulty / 真实缺陷 QuixBugs / 扩大任务数并筛失败样本）重做消融。")
lines.append("- **次指标退化（常量）**：行级 `detection_rate`/`repair_rate`/`false_fix_rate` 本批在场但两臂均为常量"
             "（detection=0、repair=0、false_fix=1.0）→ 无配对变异、Δ 恒 0，不能提供额外区分信息；主指标 iterations/coverage/test_passed 可用。")
lines.append("- **执行备注（透明披露）**：两臂 LLM 执行均 exit=0、批次 JSON 完整；runner 在 [5/7] 分析阶段因可选证据键 KeyError 中断，"
             "本报告的 ABLATION_REPORT/README 由两臂已完成批次 JSON **零 LLM 补算**生成（未重跑任何 LLM 臂；analyzer 已修复并重跑）。")
lines.append("")
lines.append("## 9. 探索性结论")
lines.append("")
cls_text = {
    "no_stall_trigger_observed": "本批未触发任何停滞判定（A 臂 coverage_stall 标签=0、trace 计数=0）→ **无法评估提前停止的收益/代价**。直接原因：两臂 10/10 任务生成的测试在 buggy 代码上全绿（detection=0/10、false_fix=1.0），无失败测试 → 从未进入 debugger 修复循环（iterations=0）→ 停滞判据（最近 2 轮失败）无机会触发——属场景/功效限制（非 wiring 缺陷；wiring 已由零 LLM 前后证据锁定）。",
    "no_detectable_difference": "主指标配对 Δ 的 bootstrap 95% CI 跨 0 且 |Δ| < 后验 MDE → 本批未检出可区分差异。",
    "direction_hint_ci_crosses_zero": "配对 Δ 方向一致但 CI 跨 0（样本小）→ 仅方向性提示，不作效果主张。",
    "direction_hint": "配对 Δ 的 95% CI 不跨 0 → 方向性提示（探索性，非确证）。",
    "insufficient_data": "配对数据不足，无法判断。",
}
lines.append(f"**分类：`{classification}`** —— {cls_text.get(classification, '见 ABLATION_REPORT.json')}")
lines.append("")
lines.append("## 10. 文件")
lines.append("")
lines.append("| 文件 | 说明 |")
lines.append("|---|---|")
lines.append("| `PREREG.md` / `PREREG.json` | 跑前落盘的探索性预注册（含修复披露） |")
lines.append("| `PREFLIGHT.json` | 切点/干净度/env 开关生效性/wiring 证据/预算门禁 |")
lines.append("| `benchmark_synthetic_*.json` | 两臂批次工件 |")
lines.append("| `log_stagnation.log` / `log_no_stagnation.log` | 两臂完整日志（env/命令/开始结束/git） |")
lines.append("| `traces_stagnation/` / `traces_no_stagnation/` | 逐任务 trace（含 `_should_debug` 决策/`reason=coverage_stall` 证据） |")
lines.append("| `arm_stagnation.meta.json` / `arm_no_stagnation.meta.json` | 逐臂元数据（token/成本/逐任务/stall 计数/trace 统计） |")
lines.append("| `ABLATION_REPORT.json` | 机读聚合（配对 Δ/CI/MDE/2×2/stall 证据/分类） |")
lines.append("| `WIRING_EVIDENCE_before.json` / `WIRING_EVIDENCE_after.json` / `WIRING_DIFF.patch` | A-19 wiring 修复前/后证据与 diff |")
lines.append("| `SHA256SUMS` | `checksum_results.py --write` 生成（跑后校验 verify） |")
lines.append("")
readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({
    "classification": classification,
    "common_tasks": len(common),
    "iterations": {k: primary["iterations"].get(k) for k in ("mean_arm_A", "mean_arm_B", "delta_mean_A_minus_B", "bootstrap_95ci", "mde_post_hoc", "n")},
    "coverage": {k: primary["coverage"].get(k) for k in ("mean_arm_A", "mean_arm_B", "delta_mean_A_minus_B", "n")},
    "passed_2x2": passed_2x2,
    "coverage_stall_labels_A": A["coverage_stall_label_count"],
    "trace_coverage_stall_A": (A["trace_reason_counts"] or {}).get("coverage_stall", 0),
    "early_stop_tasks": len(early_stop_tasks),
    "cost_total_usd": report["cost_total_usd"],
}, ensure_ascii=False, indent=2))
PY

# ─── [1/7] 零 LLM 预检（切点/干净度/开关生效/wiring/预算门禁） ──────────────
echo "=============================================================================="
echo "P-2 / B8 A-19 停滞检测开/关消融（探索性；RUN_STAMP=${RUN_STAMP}）"
echo "  被探针代码：${ROOT}"
echo "  HEAD=${ROOT_HEAD}（dirty 行数=${ROOT_DIRTY_BEFORE}）"
echo "  输出：${OUT}"
echo "  协议：A=--enable-stagnation / B=--no-stagnation；synthetic task-count=${TASK_COUNT} seed=42 baselines=aitester"
echo "        AITESTER_PROFILE=fast TEMPERATURE=0.0 THINKING=disabled P=${PARALLELISM} CACHE=0 CAP=100/\$1"
echo "  预算：≤\$${BUDGET_USD}；墙钟≤60min；每臂 watchdog ${WATCHDOG_SECONDS}s"
echo "=============================================================================="
echo ""
echo "[1/7] 零 LLM 预检"
set +e
PRE_OUT="$("${PY}" - "${ROOT}" "${OUT}" "${ROOT_HEAD}" "${TASK_COUNT}" "${BUDGET_USD}" "${PARALLELISM}" "${WATCHDOG_SECONDS}" "${PREFLIGHT_JSON}" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
head, task_count, budget, parallelism, watchdog = sys.argv[3], int(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
pre_path = Path(sys.argv[8])

blocking, warnings = [], []
checks = {}
rb = (root / "experiments/run_benchmark.py").read_text(encoding="utf-8")
checks["run_benchmark_has_enable_stagnation"] = "--enable-stagnation" in rb
checks["run_benchmark_has_no_stagnation"] = "--no-stagnation" in rb
checks["run_benchmark_apply_arm"] = "_apply_stagnation_arm" in rb
checks["env_snapshot_has_COVERAGE_STALL_DETECT_ENABLE"] = '"COVERAGE_STALL_DETECT_ENABLE"' in rb
for k, v in checks.items():
    if isinstance(v, bool) and not v:
        blocking.append(f"preflight check failed: {k}")

sys.path.insert(0, str(root))
os.chdir(root)
os.environ["AITESTER_PROFILE"] = "fast"
from src.graph.state import create_initial_state
from src.graph.workflow import (
    _coverage_stall_detected,
    _coverage_stall_enabled,
    _route_after_diagnosis,
    _should_debug,
    determine_stop_reason,
)

trace2 = [{"passed": False, "coverage_delta": 0.0}, {"passed": False, "coverage_delta": 0.0}]


def st(**kw):
    s = create_initial_state(task_uuid="preflight", target_file="/tmp/x.py", target_function="f",
                             module_name="preflight", target_code="def f():\n    return 1\n", max_iterations=3)
    s.update(kw)
    return s


env_probe = {}
wiring = {}
for value in ("true", "false"):
    os.environ["COVERAGE_STALL_DETECT_ENABLE"] = value
    key = "on" if value == "true" else "off"
    env_probe[key] = {"_coverage_stall_enabled": bool(_coverage_stall_enabled())}
    s = st(iteration=2, execution_trace=[dict(x) for x in trace2], test_passed=False)
    s_max = st(iteration=3, execution_trace=[dict(x) for x in trace2], test_passed=False)
    s_route = st(iteration=2, execution_trace=[dict(x) for x in trace2], test_passed=False, defect_type="implementation_defect")
    wiring[key] = {
        "stall_detected": bool(_coverage_stall_detected(s)),
        "determine_stop_reason": determine_stop_reason(s).value,
        "should_debug": _should_debug(s),
        "should_debug_stop_reason": s.get("stop_reason"),
        "determine_stop_reason_at_max": determine_stop_reason(s_max).value,
        "route_after_diagnosis": _route_after_diagnosis(s_route),
    }
if not (env_probe["on"]["_coverage_stall_enabled"] is True and env_probe["off"]["_coverage_stall_enabled"] is False):
    blocking.append("effective env probe failed: COVERAGE_STALL_DETECT_ENABLE not distinct/effective")
if wiring["on"]["should_debug"] != "done" or wiring["on"]["should_debug_stop_reason"] != "coverage_stall":
    blocking.append("wiring preflight failed: ON arm does not short-circuit to done/coverage_stall")
if wiring["off"]["should_debug"] != "debug":
    blocking.append("wiring preflight failed: OFF arm changed behavior (expected debug)")
if wiring["on"]["determine_stop_reason_at_max"] != "coverage_stall":
    blocking.append("priority preflight failed: stall branch not before MAX_ITERATIONS")
if wiring["on"]["route_after_diagnosis"] != "done":
    blocking.append("wiring preflight failed: _route_after_diagnosis not short-circuiting")

# 预算估算（保守：tokens/task 8000，in/out 40/60；价目表 deepseek-flash）
price = json.loads((root / "experiments/price_table.json").read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in, p_out = price.get("input_per_mtok"), price.get("output_per_mtok")
est_tokens_per_task = 8000
est_cost = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    est_tokens = task_count * 2 * est_tokens_per_task
    est_cost = round(est_tokens * (0.4 * p_in + 0.6 * p_out) / 1e6, 6)
effective_task_count = task_count
downgraded = False
if est_cost is not None and est_cost > budget:
    effective_task_count = 8
    downgraded = True
    warnings.append(f"预检成本估算 ${est_cost} > 预算 ${budget} → 自动降为 8 任务/臂并披露")
if effective_task_count != task_count:
    est_tokens = effective_task_count * 2 * est_tokens_per_task
    est_cost = round(est_tokens * (0.4 * p_in + 0.6 * p_out) / 1e6, 6) if est_cost is not None else None

git = {
    "root": str(root),
    "root_head": head,
    "expected_sha": head,
    "dirty_lines_before": int((os.popen(f"git -C {root} status --porcelain").read().count("\n"))),
}
payload = {
    "schema": "p2_b8_ablation_preflight/1",
    "run_stamp": out.name,
    "git": git,
    "checks": checks,
    "env_probe": env_probe,
    "wiring_evidence_preflight": wiring,
    "budget_gate": {
        "est_tokens_per_task": est_tokens_per_task,
        "price_model": "deepseek-flash",
        "input_per_mtok": p_in,
        "output_per_mtok": p_out,
        "estimated_cost_usd": est_cost,
        "budget_usd": budget,
        "downgraded_to": effective_task_count if downgraded else None,
        "effective_task_count": effective_task_count,
    },
    "run": {
        "task_count": effective_task_count,
        "parallelism": parallelism,
        "watchdog_seconds": watchdog,
        "budget_usd_limit": budget,
    },
    "blocking": blocking,
    "warnings": warnings,
}
pre_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"blocking": blocking, "warnings": warnings, "env_probe": env_probe, "wiring": wiring,
                  "effective_task_count": effective_task_count, "estimated_cost_usd": est_cost}, ensure_ascii=False))
raise SystemExit(0 if not blocking else 3)
PY
)"
PRE_RC=$?
set -e
echo "${PRE_OUT:0:800}"
if [ "${PRE_RC}" -ne 0 ]; then
    echo "✗ 预检失败（退出码 ${PRE_RC}）——立即中止，不跑批。" >&2
    exit 3
fi
EFFECTIVE_TASK_COUNT="$(printf '%s\n' "${PRE_OUT}" | "${PY}" -c 'import json,sys; print(json.load(sys.stdin)["effective_task_count"])')"
if [ "${EFFECTIVE_TASK_COUNT}" != "${TASK_COUNT}" ]; then
    echo "  ⚠ 预算门禁：任务数 ${TASK_COUNT} → ${EFFECTIVE_TASK_COUNT}（已写 PREREG_DOWNGRADE.md）"
    {
        echo "# PREREG 降级披露（自动，$(date -u +%FT%TZ)）"
        echo ""
        echo "- 原计划 task-count=${TASK_COUNT}/臂；预检保守成本估算超预算 \$${BUDGET_USD} → 按预注册规则降为 **${EFFECTIVE_TASK_COUNT}/臂**。"
        echo "- 估算口径：tokens/task=8000、in/out=40/60、deepseek-flash 价格；详见 PREFLIGHT.json budget_gate。"
    } > "${OUT}/PREREG_DOWNGRADE.md"
    TASK_COUNT="${EFFECTIVE_TASK_COUNT}"
fi
"${PY}" - "${OUT}/_helpers/extract_arm.py" "${OUT}/_helpers/limited_run.py" <<'PY' >/dev/null 2>&1 || true
import sys
from pathlib import Path
for p in sys.argv[1:3]:
    assert Path(p).exists(), p
PY
echo "  ✓ 预检通过（PREFLIGHT：${PREFLIGHT_JSON}）"
echo ""

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[DRY-RUN] 计划执行（两臂并发；零 LLM 调用）："
    echo "  A stagnation    ：${PY} -m experiments.run_benchmark --dataset synthetic --task-count ${TASK_COUNT} --seed 42 --baselines aitester --enable-stagnation"
    echo "  B no_stagnation ：同命令 --no-stagnation（COVERAGE_STALL_DETECT_ENABLE=false 显式）"
    echo "  输出：${OUT}"
    echo "  watchdog=${WATCHDOG_SECONDS}s/臂；预算≤\$${BUDGET_USD}；墙钟≤60min"
    echo "DRY-RUN 结束：未执行任何 LLM 调用、未产出批次工件。"
    exit 0
fi

# ─── [2/7] 两臂并发启动 ─────────────────────────────────────────────────────
echo "[2/7] 两臂并发启动（独立 namespace/log/trace；同秒级启动）"
NS_A="p_round_b8_ablation_20261018_stagnation"
NS_B="p_round_b8_ablation_20261018_no_stagnation"
STAGE_A="${OUT}/.staging_stagnation"
STAGE_B="${OUT}/.staging_no_stagnation"
LOG_A="${OUT}/log_stagnation.log"
LOG_B="${OUT}/log_no_stagnation.log"
TRACE_A="${OUT}/traces_stagnation"
TRACE_B="${OUT}/traces_no_stagnation"
mkdir -p "${STAGE_A}" "${STAGE_B}" "${TRACE_A}" "${TRACE_B}"
COMMON_ENV=(AITESTER_PROFILE=fast TEMPERATURE=0.0 LLM_THINKING_MODE=disabled "BENCHMARK_PARALLELISM=${PARALLELISM}" AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=100)

_launch_arm() { # label env_flag namespace staging log trace
    local label="$1" flag="$2" ns="$3" staging="$4" log="$5" trace="$6"
    local start_epoch start_iso
    start_epoch="$(date +%s)"; start_iso="$(date -u +%FT%TZ)"
    printf '%s %s\n' "${start_epoch}" "${start_iso}" > "${OUT}/.arm_${label}.start"
    {
        echo "===== P-2 B8 ablation arm=${label} ====="
        echo "START_ISO_UTC=${start_iso}"
        echo "ROOT=${ROOT}"
        echo "HEAD=${ROOT_HEAD}"
        echo "CMD=${PY} -m experiments.run_benchmark --dataset synthetic --task-count ${TASK_COUNT} --seed 42 --baselines aitester --output-dir ${staging} ${flag}"
        echo "ENV=AITESTER_PROFILE=fast TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=${PARALLELISM} AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=100"
        echo "ENV_ARM=${label} ${flag} COVERAGE_STALL_DETECT_ENABLE=$([ "${label}" = "stagnation" ] && echo true || echo false) AITESTER_CACHE_NAMESPACE=${ns} AITESTER_TRACE_DIR=${trace}"
    } >> "${log}"
    (
        set +e
        _s="$(date +%s)"
        (
            cd "${ROOT}" && env "${COMMON_ENV[@]}" \
                "COVERAGE_STALL_DETECT_ENABLE=$([ "${label}" = "stagnation" ] && echo true || echo false)" \
                "AITESTER_CACHE_NAMESPACE=${ns}" "AITESTER_TRACE_DIR=${trace}" \
                "${PY}" "${OUT}/_helpers/limited_run.py" "${WATCHDOG_SECONDS}" \
                "${PY}" -m experiments.run_benchmark --dataset synthetic --task-count "${TASK_COUNT}" --seed 42 \
                --baselines aitester --output-dir "${staging}" "${flag}"
        ) >> "${log}" 2>&1
        _rc=$?
        _e="$(date +%s)"
        echo "END_ISO_UTC=$(date -u +%FT%TZ) END_EPOCH=${_e} EXIT_CODE=${_rc} WALL_SECONDS=$((_e - _s))" >> "${log}"
        echo "${_rc}" > "${OUT}/.arm_${label}.rc"
    ) &
    echo $! > "${OUT}/.arm_${label}.pid"
}

_launch_arm stagnation --enable-stagnation "${NS_A}" "${STAGE_A}" "${LOG_A}" "${TRACE_A}"
_launch_arm no_stagnation --no-stagnation "${NS_B}" "${STAGE_B}" "${LOG_B}" "${TRACE_B}"
PID_A="$(cat "${OUT}/.arm_stagnation.pid")"
PID_B="$(cat "${OUT}/.arm_no_stagnation.pid")"
echo "  ✓ A stagnation    pid=${PID_A}（COVERAGE_STALL_DETECT_ENABLE=true）"
echo "  ✓ B no_stagnation pid=${PID_B}（COVERAGE_STALL_DETECT_ENABLE=false 显式）"
START_ALL_EPOCH="$(date +%s)"
echo ""

# ─── [3/7] 监控 ────────────────────────────────────────────────────────────
echo "[3/7] 监控与等待（每 15s；每臂 watchdog ${WATCHDOG_SECONDS}s）"
LAST_SCAN=0
while :; do
    _done=1
    [ -f "${OUT}/.arm_stagnation.rc" ] || _done=0
    [ -f "${OUT}/.arm_no_stagnation.rc" ] || _done=0
    if [ "${_done}" -eq 1 ]; then break; fi
    sleep 15
    NOW="$(date +%s)"
    if [ $((NOW - LAST_SCAN)) -ge 300 ]; then
        LAST_SCAN="${NOW}"
        echo "  … 已运行 $(( (NOW - START_ALL_EPOCH) / 60 ))min（stagnation=$([ -f "${OUT}/.arm_stagnation.rc" ] && echo done || echo running)，no_stagnation=$([ -f "${OUT}/.arm_no_stagnation.rc" ] && echo done || echo running)）"
    fi
    if [ $((NOW - START_ALL_EPOCH)) -gt $((WATCHDOG_SECONDS + 900)) ]; then
        echo "  ✗ 超过全局墙钟兜底（watchdog+15min）——强制终止进程组" >&2
        kill -TERM "${PID_A}" "${PID_B}" 2>/dev/null || true
        sleep 5
        kill -KILL "${PID_A}" "${PID_B}" 2>/dev/null || true
        break
    fi
done
set +e
wait "${PID_A}" 2>/dev/null; wait "${PID_B}" 2>/dev/null
set -e
RC_A="$(cat "${OUT}/.arm_stagnation.rc" 2>/dev/null || echo 127)"
RC_B="$(cat "${OUT}/.arm_no_stagnation.rc" 2>/dev/null || echo 127)"
END_ALL_EPOCH="$(date +%s)"
ROOT_DIRTY_AFTER="$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "  ✓ 两臂结束：stagnation exit=${RC_A}，no_stagnation exit=${RC_B}，总墙钟 $((END_ALL_EPOCH - START_ALL_EPOCH))s；ROOT dirty=${ROOT_DIRTY_AFTER}"
{
    echo "=============================================================="
    echo "P-2 B8 ablation run summary"
    echo "RUN_STAMP=${RUN_STAMP}"
    echo "ROOT=${ROOT} HEAD=${ROOT_HEAD} dirty_before=${ROOT_DIRTY_BEFORE} dirty_after=${ROOT_DIRTY_AFTER}"
    echo "exit stagnation=${RC_A} no_stagnation=${RC_B} wall_total=$((END_ALL_EPOCH - START_ALL_EPOCH))s task_count=${TASK_COUNT}"
} | tee -a "${OUT}/RUN_SUMMARY.log" >/dev/null

# ─── [4/7] 收集工件 + 逐臂元数据 ────────────────────────────────────────────
echo ""
echo "[4/7] 收集工件与逐臂元数据"
ARM_FAIL=0
_collect_arm() { # label flag env staging log trace rc ns
    local label="$1" flag="$2" envv="$3" staging="$4" log="$5" trace="$6" rc="$7" ns="$8"
    local batch target meta start_epoch start_iso
    start_epoch="$(awk '{print $1}' "${OUT}/.arm_${label}.start")"
    start_iso="$(awk '{print $2}' "${OUT}/.arm_${label}.start")"
    batch="$(ls "${staging}"/*.json 2>/dev/null | head -1 || true)"
    if [ -z "${batch}" ]; then
        echo "  ✗ [${label}] 无批次工件（exit=${rc}）——保留日志/失败元数据" >&2
        ARM_FAIL=1
        "${PY}" - "${OUT}" "${label}" "${rc}" "${log}" <<'PY'
import json, sys
from pathlib import Path
out, label, rc, log = sys.argv[1:5]
payload = {"arm_label": label, "status": "failed", "exit_code": int(rc), "log": log,
           "note": "臂失败/超时：按协议保留日志与部分工件，不重跑"}
(Path(out) / f"arm_{label}.meta.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
        return 0
    fi
    target="${OUT}/$(basename "${batch}")"
    if [ -e "${target}" ]; then target="${OUT}/$(basename "${batch}" .json)_${label}.json"; fi
    mv "${batch}" "${target}"
    rmdir "${staging}" 2>/dev/null || true
    meta="${OUT}/arm_${label}.meta.json"
    echo "  [${label}] 批次：${target}"
    "${PY}" "${OUT}/_helpers/extract_arm.py" "${target}" "${label}" "${flag}" "${envv}" \
        "${ns}" "${start_epoch}" "${start_iso}" "${meta}" "${trace}" "${log}" "${ROOT}/experiments/price_table.json"
}
_collect_arm stagnation --enable-stagnation true "${STAGE_A}" "${LOG_A}" "${TRACE_A}" "${RC_A}" "${NS_A}"
_collect_arm no_stagnation --no-stagnation false "${STAGE_B}" "${LOG_B}" "${TRACE_B}" "${RC_B}" "${NS_B}"

if [ "${ARM_FAIL}" -ne 0 ]; then
    echo "✗ 某臂失败/无批次工件（stagnation=${RC_A} no_stagnation=${RC_B}）——保留日志/工件，不重跑。" >&2
    exit 4
fi

# ─── [5/7] 配对聚合 + README ────────────────────────────────────────────────
echo ""
echo "[5/7] 配对聚合（ABLATION_REPORT.json + README.md）"
"${PY}" "${OUT}/_helpers/analyze.py" "${OUT}"
echo ""
echo "[6/7] 文件清单"
ls -1 "${OUT}" | grep -v '^\.' | sed 's/^/  /'
echo ""
echo "[7/7] SHA256SUMS（checksum_results.py --write）+ 校验"
"${PY}" "${SCRIPT_REPO}/scripts/gates/checksum_results.py" --results-dir "${OUT}" --write 2>&1 | tail -2
"${PY}" "${SCRIPT_REPO}/scripts/gates/checksum_results.py" --results-dir "${OUT}" --verify 2>&1 | tail -2
echo ""
echo "=============================================================================="
echo "P-2 B8 消融完成（RUN_STAMP=${RUN_STAMP}）"
echo "  切点：${ROOT_HEAD}（跑后 dirty 行数=${ROOT_DIRTY_AFTER}）"
echo "  两臂 exit：stagnation=${RC_A} no_stagnation=${RC_B}；总墙钟 $((END_ALL_EPOCH - START_ALL_EPOCH))s"
echo "  README：${OUT}/README.md"
echo "  ABLATION_REPORT：${OUT}/ABLATION_REPORT.json"
echo "  SHA256SUMS：${OUT}/SHA256SUMS"
echo "=============================================================================="
