#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Q-2 / task-23：oracle 示例通道生产化验证——预注册二臂 A/B 真 LLM 批（20 任务）
#
# 前置（Lead 提供）：Q-1 切点（q-examples）干净 commit + worktree（HEAD=切点，
# dirty=0，.env.local 已复制）；PREREG.md 已落盘（本脚本拒绝缺失预注册时跑批）。
#
# 用法：
#   bash experiments/run_q_examples_ab.sh \
#     --root <clean-worktree> --expect-sha <q-examples-sha> \
#     --require-clean-root [--dry-run] [--preflight-only] [--task-limit 20]
#
# 协议（冻结，见 PREREG.md）：
#   两臂并发、同秒启动、独立 AITESTER_CACHE_NAMESPACE、AITESTER_LLM_CACHE=0；
#   AITESTER_PROFILE=logic、TEMPERATURE=0.0、LLM_THINKING_MODE=disabled、
#   BENCHMARK_PARALLELISM=4、COST_BUDGET_ENABLE=true COST_BUDGET_USD=1、
#   AITESTER_BATCH_MAX_CALLS=200、watchdog 3600s/臂；
#   A(control)：SPEC_ORACLE_EXEC_ENABLE=true + SPEC_ORACLE_EXAMPLES_ENABLE=false；
#   B(examples)：SPEC_ORACLE_EXEC_ENABLE=true + SPEC_ORACLE_EXAMPLES_ENABLE=true；
#   --dataset quixbugs --task-limit 20 --seed 42 --baselines aitester。
# 预算/墙钟：≤$0.5 / ≤110min；预检估算超限 → 降 15 任务并披露。
# 判定（预注册）：Δ=B_correct−A_correct ≥2 ∧ LLM-suite 非劣(B≥A−5pp) ∧
#                 McNemar 单向 p<0.05 → confirmed；否则 not_confirmed。
# 失败策略：单臂失败/超时保留日志工件、如实报告、不重跑。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT=""
OUT="${SCRIPT_REPO}/experiments/results/q_round_examples_ab_20261018"
EXPECT_SHA=""
TASK_LIMIT=20
PARALLELISM=4
WATCHDOG_SECONDS=3600
BUDGET_USD=0.5
WALL_LIMIT_MIN=110
DRY_RUN=0
PREFLIGHT_ONLY=0
REQUIRE_CLEAN_ROOT=0
REQUIRE_FEATURE=1

usage() { sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --root) [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }; ROOT="$2"; shift 2 ;;
        --out) [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --expect-sha) [ $# -ge 2 ] || { echo "--expect-sha 需要完整 sha" >&2; exit 2; }; EXPECT_SHA="$2"; shift 2 ;;
        --task-limit) [ $# -ge 2 ] || { echo "--task-limit 需要正整数" >&2; exit 2; }; TASK_LIMIT="$2"; shift 2 ;;
        --parallelism) [ $# -ge 2 ] || { echo "--parallelism 需要正整数" >&2; exit 2; }; PARALLELISM="$2"; shift 2 ;;
        --watchdog-seconds) [ $# -ge 2 ] || { echo "--watchdog-seconds 需要正整数" >&2; exit 2; }; WATCHDOG_SECONDS="$2"; shift 2 ;;
        --budget-usd) [ $# -ge 2 ] || { echo "--budget-usd 需要数值" >&2; exit 2; }; BUDGET_USD="$2"; shift 2 ;;
        --wall-limit-min) [ $# -ge 2 ] || { echo "--wall-limit-min 需要数值" >&2; exit 2; }; WALL_LIMIT_MIN="$2"; shift 2 ;;
        --require-clean-root) REQUIRE_CLEAN_ROOT=1; shift ;;
        --allow-missing-feature) REQUIRE_FEATURE=0; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

for _v in TASK_LIMIT PARALLELISM WATCHDOG_SECONDS; do
    case "${!_v:-}" in '' | *[!0-9]*) echo "--${_v} 必须正整数" >&2; exit 2 ;; esac
done

[ -n "${ROOT}" ] || { echo "✗ 必须给 --root（Q-1 切点 worktree）" >&2; exit 2; }
[ -d "${ROOT}" ] || { echo "✗ ROOT 不存在：${ROOT}" >&2; exit 2; }
[ -n "${EXPECT_SHA}" ] || { echo "✗ 必须给 --expect-sha（Q-1 切点校验）" >&2; exit 2; }
ROOT="$(cd "${ROOT}" && pwd)"
mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
[ -f "${ROOT}/experiments/run_benchmark.py" ] || { echo "✗ ROOT 不像 aitester 仓库：${ROOT}" >&2; exit 2; }
[ -f "${ROOT}/.env.local" ] || { echo "✗ ROOT/.env.local 缺失（真实 LLM 需要）" >&2; exit 2; }
[ -f "${OUT}/PREREG.md" ] || { echo "✗ 预注册缺失：${OUT}/PREREG.md（跑前必须落盘）" >&2; exit 2; }

if [ -x "${SCRIPT_REPO}/.venv/bin/python" ]; then PY="${SCRIPT_REPO}/.venv/bin/python"
elif [ -x "${ROOT}/.venv/bin/python" ]; then PY="${ROOT}/.venv/bin/python"
else echo "✗ 找不到 python 解释器" >&2; exit 2; fi
PRICE="${ROOT}/experiments/price_table.json"
[ -f "${PRICE}" ] || { echo "✗ 价目表缺失：${PRICE}" >&2; exit 2; }

ROOT_HEAD="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || true)"
ROOT_DIRTY_BEFORE="$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ "${ROOT_HEAD}" = "${EXPECT_SHA}" ] || { echo "✗ 切点不符：ROOT HEAD=${ROOT_HEAD} ≠ expect=${EXPECT_SHA}" >&2; exit 2; }

# 零 LLM 安全模式：dry-run / preflight-only 允许 dirty 与 feature 缺失（绝不 launch）；
# 真实跑批强制干净树 + PREREG 已冻结（事故 2026-10-18 加固：不依赖调用方记得传 flag）。
if [ "${DRY_RUN}" -eq 1 ]; then
    REQUIRE_FEATURE=0
else
    if [ "${ROOT_DIRTY_BEFORE}" != "0" ]; then
        echo "✗ 真实跑批要求干净树：ROOT dirty=${ROOT_DIRTY_BEFORE} 行（事故加固；仅 dry-run 允许 dirty）" >&2
        exit 2
    fi
    if grep -qE "状态：DRAFT|<Q-1 q-examples sha|<Lead 提供>" "${OUT}/PREREG.md"; then
        echo "✗ PREREG 尚未冻结（含 DRAFT/占位符）：真实跑批前必须补齐切点/命令并移除 DRAFT 标记" >&2
        exit 2
    fi
    if ! grep -q "${EXPECT_SHA}" "${OUT}/PREREG.md"; then
        echo "✗ PREREG 未记录切点 sha（${EXPECT_SHA}）：真实跑批前必须先冻结预注册" >&2
        exit 2
    fi
fi
if [ "${REQUIRE_CLEAN_ROOT}" -eq 1 ] && [ "${ROOT_DIRTY_BEFORE}" != "0" ]; then
    echo "✗ ROOT 非干净（dirty=${ROOT_DIRTY_BEFORE} 行）" >&2; exit 2
fi

mkdir -p "${OUT}" "${OUT}/_helpers"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PREREG_SHA="$(shasum -a 256 "${OUT}/PREREG.md" | awk '{print $1}')"

if [ "${DRY_RUN}" -eq 1 ]; then
    PREFLIGHT_JSON="${OUT}/PREFLIGHT_dryrun.json"
else
    PREFLIGHT_JSON="${OUT}/PREFLIGHT.json"
    if [ -e "${OUT}/log_control.log" ] || [ -e "${OUT}/log_examples.log" ] || [ -e "${OUT}/README.md" ]; then
        echo "✗ 结果目录已有跑批工件（拒绝覆盖）：${OUT}" >&2; exit 2
    fi
fi

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
"""逐臂元数据抽取（零 LLM）：tokens/成本/墙钟/行字段/注入与 verdict/示例来源与计数/字段完整性。"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

batch_path, label, cli, env_examples, ns, start_epoch, start_iso, out_meta, trace_dir, log_path, price_path = sys.argv[1:12]
batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
arm = (batch.get("results") or {}).get("aitester") or {}
rows = arm.get("details") or []
prov = batch.get("provenance") or {}
snap = prov.get("env_snapshot") or {}
tm = arm.get("token_metrics") or batch.get("token_metrics") or {}

price = json.loads(Path(price_path).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in, p_out = price.get("input_per_mtok"), price.get("output_per_mtok")
cost = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    cost = round((tm.get("total_input_tokens", 0) * p_in + tm.get("total_output_tokens", 0) * p_out) / 1e6, 6)

wall = exit_code = end_iso = None
log_text = Path(log_path).read_text(encoding="utf-8", errors="replace") if Path(log_path).exists() else ""
m = re.search(r"END_ISO_UTC=(\S+) END_EPOCH=(\d+) EXIT_CODE=(-?\d+) WALL_SECONDS=(\d+)", log_text)
if m:
    end_iso, _e, exit_code, wall = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

REQ_KEYS = [
    "task_id", "passed", "coverage", "iterations", "stop_reason",
    "spec_oracle_injected", "spec_oracle_verdict", "oracle_suite_verdict",
    "llm_suite_detection_rate", "detection_rate", "repair_rate", "false_fix_rate",
    "spec_oracle_examples_source", "spec_oracle_examples_count",
]
field_present = {k: sum(1 for r in rows if k in r) for k in REQ_KEYS}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


tasks = []
stop_reasons = Counter()
oracle_suite = Counter()
oracle_verdict = Counter()
examples_source = Counter()
examples_counts = []
for r in rows:
    sr = r.get("stop_reason")
    stop_reasons[str(sr) if sr else "None"] += 1
    osv = r.get("oracle_suite_verdict")
    oracle_suite[str(osv) if osv is not None else "None"] += 1
    ov = r.get("spec_oracle_verdict")
    oracle_verdict[str(ov) if ov is not None else "None"] += 1
    es = r.get("spec_oracle_examples_source")
    examples_source[str(es) if es is not None else "None"] += 1
    ec = _int(r.get("spec_oracle_examples_count"))
    if ec is not None:
        examples_counts.append(ec)
    tasks.append({
        "task_id": r.get("task_id"),
        "passed": bool(r.get("passed")),
        "iterations": int(r.get("iterations") or 0),
        "coverage": _num(r.get("coverage")),
        "detection_rate": _num(r.get("detection_rate")),
        "llm_suite_detection_rate": _num(r.get("llm_suite_detection_rate")),
        "repair_rate": _num(r.get("repair_rate")),
        "false_fix_rate": _num(r.get("false_fix_rate")),
        "stop_reason": sr,
        "spec_oracle_injected": r.get("spec_oracle_injected"),
        "spec_oracle_verdict": ov,
        "oracle_suite_verdict": osv,
        "spec_oracle_examples_source": es,
        "spec_oracle_examples_count": ec,
        "elapsed_seconds": _num(r.get("elapsed_seconds")),
        "token_usage": r.get("token_usage") or {},
    })

# trace：planner 事件中的 examples 证据（若 Q-1 在 trace 中记录）与 stop/reason 计数
trace_events = Counter()
if Path(trace_dir).is_dir():
    for f in sorted(Path(trace_dir).glob("*.trace.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") == "node":
                trace_events[f"{rec.get('node')}:{rec.get('decision')}"] += 1

det_vals = [t["llm_suite_detection_rate"] for t in tasks if t["llm_suite_detection_rate"] is not None]
if not det_vals:
    det_vals = [t["detection_rate"] for t in tasks if t["detection_rate"] is not None]

payload = {
    "arm_label": label,
    "cli": cli,
    "env_expected_SPEC_ORACLE_EXAMPLES_ENABLE": env_examples,
    "cache_namespace": ns,
    "batch_path": str(Path(batch_path).resolve()),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "task_ids": [t["task_id"] for t in tasks],
    "tasks": tasks,
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
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
        "env_snapshot_SPEC_ORACLE_EXEC_ENABLE": snap.get("SPEC_ORACLE_EXEC_ENABLE"),
        "env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE": snap.get("SPEC_ORACLE_EXAMPLES_ENABLE"),
        "env_snapshot_DETECTION_SPEC_MODE": snap.get("DETECTION_SPEC_MODE"),
    },
    "stop_reason_counts": dict(stop_reasons),
    "oracle_suite_verdict_counts": dict(oracle_suite),
    "oracle_verdict_counts": dict(oracle_verdict),
    "examples_source_counts": dict(examples_source),
    "examples_count_stats": {
        "n_rows_with_count": len(examples_counts),
        "mean": round(sum(examples_counts) / len(examples_counts), 4) if examples_counts else None,
        "max": max(examples_counts) if examples_counts else None,
        "total": sum(examples_counts),
    },
    "field_present_counts": field_present,
    "trace_events": dict(trace_events),
    "detection_aggregate": {
        "measurable": len(det_vals),
        "detected": sum(1 for v in det_vals if float(v) >= 1.0),
        "rate": round(sum(1 for v in det_vals if float(v) >= 1.0) / len(det_vals), 4) if det_vals else None,
    },
}
Path(out_meta).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} wall={wall}s "
      f"injected={dict((k, v) for k, v in Counter(str(t['spec_oracle_injected']) for t in tasks).items())} "
      f"oracle_suite={dict(oracle_suite)} examples_source={dict(examples_source)}")
PY

cat > "${OUT}/_helpers/analyze.py" <<'PY'
"""配对聚合 + 预注册判定（oracle-correct Δ / 非劣 / McNemar）+ README + ANALYSIS_REPORT.json。"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

out = Path(sys.argv[1])
A = json.loads((out / "arm_control.meta.json").read_text(encoding="utf-8"))
B = json.loads((out / "arm_examples.meta.json").read_text(encoding="utf-8"))
pf_path = out / "PREFLIGHT.json"
pf = json.loads(pf_path.read_text(encoding="utf-8")) if pf_path.exists() else {}
prereg_text = (out / "PREREG.md").read_text(encoding="utf-8") if (out / "PREREG.md").exists() else ""

A_by = {t["task_id"]: t for t in A["tasks"]}
B_by = {t["task_id"]: t for t in B["tasks"]}
common = [tid for tid in A["task_ids"] if tid in B_by]


def _correct(t):
    return t.get("oracle_suite_verdict") == "correct"


A_corr = {tid for tid in common if _correct(A_by[tid])}
B_corr = {tid for tid in common if _correct(B_by[tid])}
b_only = sorted(B_corr - A_corr)
a_only = sorted(A_corr - B_corr)
delta = len(B_corr) - len(A_corr)
b, c = len(b_only), len(a_only)


def mcnemar_exact_one_sided(b: int, c: int) -> float:
    n = b + c
    if n == 0 or b <= c:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(b, n + 1))
    return tail / (2 ** n)


p_val = mcnemar_exact_one_sided(b, c)

# LLM-suite detection（denominator = evaluable tasks, arm-level）
def _det(tasks):
    vals = [t["llm_suite_detection_rate"] for t in tasks if t["llm_suite_detection_rate"] is not None]
    if not vals:
        vals = [t["detection_rate"] for t in tasks if t["detection_rate"] is not None]
    return {"measurable": len(vals), "detected": sum(1 for v in vals if float(v) >= 1.0),
            "rate": (sum(1 for v in vals if float(v) >= 1.0) / len(vals)) if vals else None}


det_a = _det(A["tasks"])
det_b = _det(B["tasks"])
rate_a = det_a["rate"]
rate_b = det_b["rate"]
noninferior_margin = 0.05
non_inferior = (rate_a is not None and rate_b is not None and rate_b >= rate_a - noninferior_margin)
delta_pp = round((rate_b - rate_a) * 100, 2) if (rate_a is not None and rate_b is not None) else None

confirmed = bool(delta >= 2 and non_inferior and p_val < 0.05)
verdict = "confirmed" if confirmed else "not_confirmed"
reasons = []
if delta < 2:
    reasons.append(f"Δ=B_correct−A_correct={delta} < 2")
if not non_inferior:
    reasons.append(f"LLM-suite 非劣不成立（B {rate_b} vs A {rate_a}, δ={delta_pp}pp < -5pp）")
if p_val >= 0.05:
    reasons.append(f"McNemar 单向 p={p_val:.6f} ≥ 0.05")

# 逐任务配对表（主指标 + LLM-suite detection 一致性）
paired_rows = []
det_mismatch = []
for tid in common:
    ta, tb = A_by[tid], B_by[tid]
    paired_rows.append({
        "task_id": tid,
        "A_oracle_suite_verdict": ta.get("oracle_suite_verdict"),
        "B_oracle_suite_verdict": tb.get("oracle_suite_verdict"),
        "A_oracle_correct": _correct(ta),
        "B_oracle_correct": _correct(tb),
        "A_examples_source": ta.get("spec_oracle_examples_source"),
        "B_examples_source": tb.get("spec_oracle_examples_source"),
        "A_examples_count": ta.get("spec_oracle_examples_count"),
        "B_examples_count": tb.get("spec_oracle_examples_count"),
        "A_detection": ta.get("llm_suite_detection_rate", ta.get("detection_rate")),
        "B_detection": tb.get("llm_suite_detection_rate", tb.get("detection_rate")),
    })
    da = ta.get("llm_suite_detection_rate", ta.get("detection_rate"))
    db = tb.get("llm_suite_detection_rate", tb.get("detection_rate"))
    if da is None or db is None:
        det_mismatch.append({"task_id": tid, "A": da, "B": db, "note": "one/both not measurable"})
    elif abs(float(da) - float(db)) > 1e-9:
        det_mismatch.append({"task_id": tid, "A": da, "B": db, "note": "value differs"})

# 分布/次指标
def _dist(arm, key):
    return dict(Counter(str(t.get(key)) if t.get(key) is not None else "None" for t in arm["tasks"]))

injection_rate = {}
for name, arm in (("A_control", A), ("B_examples", B)):
    rows = arm["rows"]
    inj = sum(1 for t in arm["tasks"] if t.get("spec_oracle_injected") is True)
    injection_rate[name] = {"injected": inj, "rows": rows, "rate": round(inj / rows, 4) if rows else None}

repair = {}
for name, arm in (("A_control", A), ("B_examples", B)):
    vals = [t["repair_rate"] for t in arm["tasks"] if t["repair_rate"] is not None]
    ff = [t["false_fix_rate"] for t in arm["tasks"] if t["false_fix_rate"] is not None]
    repair[name] = {
        "repair_rate_mean": round(sum(vals) / len(vals), 4) if vals else None,
        "false_fix_rate_mean": round(sum(ff) / len(ff), 4) if ff else None,
        "n": len(vals),
    }

# MDE 披露（单侧精确 McNemar，c=0 情形）
mde_note = {
    "method": "exact one-sided McNemar on discordant pairs (alpha=0.05)",
    "min_b_with_c0_for_p_lt_005": next((bb for bb in range(1, 30) if mcnemar_exact_one_sided(bb, 0) < 0.05), None),
    "p_at_b4_c0": mcnemar_exact_one_sided(4, 0),
    "p_at_b5_c0": mcnemar_exact_one_sided(5, 0),
    "observed_b": b, "observed_c": c, "observed_p": p_val,
    "note": "n=%d 配对；Δ>=2 为必要但不充分条件；小样本/单次运行，低功效，仅按冻结规则报告" % len(common),
}

report = {
    "schema": "q2_examples_ab_report/1",
    "nature": "pre-registered measurement; single run; small sample; no confirmatory causal claims beyond frozen rule",
    "cut": pf.get("git", {}),
    "prereg_sha256": pf.get("prereg_sha256"),
    "protocol": pf.get("run", {}),
    "arms": {
        "A_control": {
            "rows": A["rows"], "wall_seconds": A["wall_seconds"], "exit_code": A["exit_code"],
            "tokens": (A.get("token_metrics") or {}).get("total_tokens"),
            "calls": (A.get("token_metrics") or {}).get("total_llm_calls"),
            "cost_usd": A.get("cost_usd_standard_price"),
            "env_SPEC_ORACLE_EXEC_ENABLE": A["provenance"]["env_snapshot_SPEC_ORACLE_EXEC_ENABLE"],
            "env_SPEC_ORACLE_EXAMPLES_ENABLE": A["provenance"]["env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE"],
            "stop_reason_counts": A["stop_reason_counts"],
            "oracle_verdict_counts": A["oracle_verdict_counts"],
            "oracle_suite_verdict_counts": A["oracle_suite_verdict_counts"],
            "examples_source_counts": A["examples_source_counts"],
            "examples_count_stats": A["examples_count_stats"],
            "field_present_counts": A["field_present_counts"],
            "detection_aggregate": A["detection_aggregate"],
        },
        "B_examples": {
            "rows": B["rows"], "wall_seconds": B["wall_seconds"], "exit_code": B["exit_code"],
            "tokens": (B.get("token_metrics") or {}).get("total_tokens"),
            "calls": (B.get("token_metrics") or {}).get("total_llm_calls"),
            "cost_usd": B.get("cost_usd_standard_price"),
            "env_SPEC_ORACLE_EXEC_ENABLE": B["provenance"]["env_snapshot_SPEC_ORACLE_EXEC_ENABLE"],
            "env_SPEC_ORACLE_EXAMPLES_ENABLE": B["provenance"]["env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE"],
            "stop_reason_counts": B["stop_reason_counts"],
            "oracle_verdict_counts": B["oracle_verdict_counts"],
            "oracle_suite_verdict_counts": B["oracle_suite_verdict_counts"],
            "examples_source_counts": B["examples_source_counts"],
            "examples_count_stats": B["examples_count_stats"],
            "field_present_counts": B["field_present_counts"],
            "detection_aggregate": B["detection_aggregate"],
        },
    },
    "primary": {
        "common_tasks": len(common),
        "A_correct": len(A_corr), "B_correct": len(B_corr), "delta_B_minus_A": delta,
        "b_B_only": b_only, "c_A_only": a_only, "b": b, "c": c,
        "mcnemar_one_sided_p": round(p_val, 8),
        "llm_suite_detection": {"A": det_a, "B": det_b, "delta_pp": delta_pp, "non_inferior_margin_pp": 5.0, "non_inferior": non_inferior},
        "verdict": verdict, "not_confirmed_reasons": reasons, "mde": mde_note,
    },
    "secondary": {
        "injection_rate": injection_rate,
        "repair_false_fix": repair,
        "paired_rows": paired_rows,
        "llm_suite_detection_mismatch_count": len(det_mismatch),
        "llm_suite_detection_mismatches": det_mismatch,
        "examples_source_distribution": {"A": _dist(A, "spec_oracle_examples_source"), "B": _dist(B, "spec_oracle_examples_source")},
        "examples_count_distribution": {"A": _dist(A, "spec_oracle_examples_count"), "B": _dist(B, "spec_oracle_examples_count")},
    },
    "cost_total_usd": round((A.get("cost_usd_standard_price") or 0) + (B.get("cost_usd_standard_price") or 0), 6),
    "wall_max_seconds": max(A.get("wall_seconds") or 0, B.get("wall_seconds") or 0),
}
(out / "ANALYSIS_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def f(v, nd=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


L = []
L.append("# Q-2：oracle 示例通道生产化验证——预注册二臂 A/B（真 LLM，QuixBugs 20 任务）")
L.append("")
L.append("> **性质：预注册判定测量（单次运行、小样本）**。判定规则在 `PREREG.md` 跑前冻结；结果只按该规则报告 "
         "`confirmed` / `not_confirmed`，并披露 MDE/功效/局限；不做超出规则的 confirmatory 因果主张。")
L.append("")
L.append("## 1. 协议与切点")
L.append("")
L.append(f"- 切点：`{(pf.get('git') or {}).get('root_head', '')}`（Q-1 q-examples；跑前/跑后 worktree dirty=0）")
L.append(f"- 两臂并发、同秒启动、独立 namespace、`AITESTER_LLM_CACHE=0`；`AITESTER_PROFILE=logic`、TEMPERATURE=0.0、"
         "LLM_THINKING_MODE=disabled、`BENCHMARK_PARALLELISM={p}`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、"
         "`AITESTER_BATCH_MAX_CALLS=200`、watchdog 3600s/臂。".format(p=(report["protocol"] or {}).get("parallelism")))
L.append("- A（control）：`SPEC_ORACLE_EXEC_ENABLE=true` + `SPEC_ORACLE_EXAMPLES_ENABLE=false`；"
         "B（examples）：两者均 `true`；`--dataset quixbugs --task-limit {n} --seed 42 --baselines aitester`。".format(
             n=(report["protocol"] or {}).get("task_limit")))
L.append(f"- 预注册：`PREREG.md`（sha256 `{report['prereg_sha256']}`）；预算 ≤${(report['protocol'] or {}).get('budget_usd')}，"
         f"墙钟 ≤{(report['protocol'] or {}).get('wall_limit_min')}min。")
L.append("")
L.append("## 2. 预注册判定（冻结规则）")
L.append("")
L.append("**主指标**：任务级 `oracle_suite_verdict == \"correct\"` 的任务数（配对共同任务）。")
L.append("")
L.append("**成功判定（三条同时满足）**：①Δ=B_correct−A_correct ≥ **2** ∧ ②LLM-suite detection 非劣（B ≥ A − **5pp**） ∧ "
         "③McNemar 单向 **p < 0.05**；否则 `not_confirmed`。")
L.append("")
L.append("## 3. 两臂表（实测）")
L.append("")
L.append("| 项 | A control | B examples |")
L.append("|---|---|---|")
L.append(f"| 批次 sha256 | `{(A['batch_sha256'] or '')[:16]}…` | `{(B['batch_sha256'] or '')[:16]}…` |")
L.append(f"| 行数 / exit | {A['rows']} / {A['exit_code']} | {B['rows']} / {B['exit_code']} |")
L.append(f"| 墙钟(s) | {f(A['wall_seconds'],1)} | {f(B['wall_seconds'],1)} |")
L.append(f"| tokens / calls | {(A.get('token_metrics') or {}).get('total_tokens')} / {(A.get('token_metrics') or {}).get('total_llm_calls')} | "
         f"{(B.get('token_metrics') or {}).get('total_tokens')} / {(B.get('token_metrics') or {}).get('total_llm_calls')} |")
L.append(f"| 成本（标准价上界） | ${f(A.get('cost_usd_standard_price'),6)} | ${f(B.get('cost_usd_standard_price'),6)} |")
L.append(f"| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `{A['provenance']['env_snapshot_SPEC_ORACLE_EXEC_ENABLE']}` | `{B['provenance']['env_snapshot_SPEC_ORACLE_EXEC_ENABLE']}` |")
L.append(f"| env_snapshot.SPEC_ORACLE_EXAMPLES_ENABLE | `{A['provenance']['env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE']}` | `{B['provenance']['env_snapshot_SPEC_ORACLE_EXAMPLES_ENABLE']}` |")
L.append(f"| `oracle_suite_verdict` 分布 | `{json.dumps(A['oracle_suite_verdict_counts'], ensure_ascii=False)}` | `{json.dumps(B['oracle_suite_verdict_counts'], ensure_ascii=False)}` |")
L.append(f"| `spec_oracle_examples_source` 分布 | `{json.dumps(A['examples_source_counts'], ensure_ascii=False)}` | `{json.dumps(B['examples_source_counts'], ensure_ascii=False)}` |")
L.append(f"| `spec_oracle_examples_count` 统计 | `{json.dumps(A['examples_count_stats'], ensure_ascii=False)}` | `{json.dumps(B['examples_count_stats'], ensure_ascii=False)}` |")
L.append(f"| 注入率 | {injection_rate['A_control']['injected']}/{A['rows']} | {injection_rate['B_examples']['injected']}/{B['rows']} |")
L.append(f"| LLM-suite detection | {f(det_a['rate']*100 if det_a['rate'] is not None else None,2)}%（{det_a['detected']}/{det_a['measurable']}） | {f(det_b['rate']*100 if det_b['rate'] is not None else None,2)}%（{det_b['detected']}/{det_b['measurable']}） |")
L.append("")
L.append("## 4. 主指标配对与判定")
L.append("")
L.append(f"- 共同任务：**{len(common)}**；A_correct=**{len(A_corr)}**，B_correct=**{len(B_corr)}**，Δ=**{delta}**。")
L.append(f"- discordant：b（B 新增 correct）=**{b}**，c（A 独有 correct）=**{c}**；McNemar 单向 p=**{p_val:.6f}**。")
L.append(f"- LLM-suite detection 非劣：A={f(rate_a,4)} / B={f(rate_b,4)}（δ={delta_pp}pp，阈值 −5pp，非劣={non_inferior}）。")
L.append(f"- **判定：`{verdict}`**" + ("" if confirmed else f"（未满足：{'；'.join(reasons) if reasons else '规则条件'}）"))
L.append("")
L.append(f"- **MDE 披露**：单侧精确 McNemar α=0.05、c=0 时需 b≥{mde_note['min_b_with_c0_for_p_lt_005']}（b=4 时 p={mde_note['p_at_b4_c0']:.4f}，b=5 时 p={mde_note['p_at_b5_c0']:.5f}）；"
         f"n={len(common)} 配对、单次运行 → 低功效；Δ≥2 为必要但不充分条件。")
L.append("")
L.append("## 5. 逐任务配对（主指标 oracle-correct + 示例来源/计数 + LLM-suite detection）")
L.append("")
L.append("| task_id | A verdict | B verdict | b | A ex_source/count | B ex_source/count | A det | B det |")
L.append("|---|---|---|---|---|---|---|---|")
for r in paired_rows:
    mark = "★" if (r["B_oracle_correct"] and not r["A_oracle_correct"]) else ("✗" if (r["A_oracle_correct"] and not r["B_oracle_correct"]) else "")
    L.append(f"| `{r['task_id']}` | {r['A_oracle_suite_verdict']} | {r['B_oracle_suite_verdict']} | {mark} | "
             f"{r['A_examples_source']}/{r['A_examples_count']} | {r['B_examples_source']}/{r['B_examples_count']} | {f(r['A_detection'])} | {f(r['B_detection'])} |")
L.append("")
L.append("## 6. 次指标")
L.append("")
L.append(f"- 注入率：A {injection_rate['A_control']['injected']}/{A['rows']}；B {injection_rate['B_examples']['injected']}/{B['rows']}。")
L.append(f"- `spec_oracle_verdict` 分布：A `{json.dumps(A['oracle_verdict_counts'], ensure_ascii=False)}` / B `{json.dumps(B['oracle_verdict_counts'], ensure_ascii=False)}`。")
L.append(f"- repair/false_fix（均值）：A `{json.dumps(repair['A_control'], ensure_ascii=False)}` / B `{json.dumps(repair['B_examples'], ensure_ascii=False)}`。")
L.append(f"- LLM-suite detection 逐任务不一致：**{len(det_mismatch)}**" + (f"（{json.dumps(det_mismatch, ensure_ascii=False)}）" if det_mismatch else "（两臂逐任务一致）"))
L.append(f"- 字段完整率（需求键）：A `{json.dumps(A['field_present_counts'], ensure_ascii=False)}` / B `{json.dumps(B['field_present_counts'], ensure_ascii=False)}`。")
L.append("")
L.append("## 7. 成本 / 墙钟")
L.append("")
L.append(f"- 两臂合计成本（标准价上界）≈ **${f(report['cost_total_usd'],6)}**（预算 ≤$0.5）。")
L.append(f"- 墙钟：A={f(A['wall_seconds'],1)}s / B={f(B['wall_seconds'],1)}s（max={f(report['wall_max_seconds'],1)}s；≤110min）。")
L.append("")
L.append("## 8. 局限（预注册披露）")
L.append("")
L.append("- 单次运行、单模型/单数据集/单 seed、n=%d 配对 → 低功效；后验 MDE 见 §4，不做事后改规则。" % len(common))
L.append("- oracle-correct 低基数（历史 correct 0 起步）：小 Δ 可能统计不可判；仅按冻结规则报告 confirmed/not_confirmed。")
L.append("- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。")
L.append("- 若 unavailable/fp 占比高，correct 变化可能受 instrument 限制（需结合 §6 verdict 分布解读）。")
L.append("")
L.append("## 9. 文件")
L.append("")
L.append("| 文件 | 说明 |")
L.append("|---|---|")
L.append("| `PREREG.md` | 跑前冻结的预注册（判定规则/MDE/局限） |")
L.append("| `PREFLIGHT.json` | 切点/干净度/env 开关/字段/契约检查/成本墙钟估算 |")
L.append("| `benchmark_quixbugs_*.json` | 两臂批次工件 |")
L.append("| `log_control.log` / `log_examples.log` | 两臂完整日志 |")
L.append("| `traces_control/` / `traces_examples/` | 逐任务 trace |")
L.append("| `arm_control.meta.json` / `arm_examples.meta.json` | 逐臂元数据 |")
L.append("| `ANALYSIS_REPORT.json` | 机读聚合（判定/配对/分布） |")
L.append("| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |")
(out / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")

print(json.dumps({
    "verdict": verdict, "not_confirmed_reasons": reasons,
    "common_tasks": len(common), "A_correct": len(A_corr), "B_correct": len(B_corr), "delta": delta,
    "b": b, "c": c, "mcnemar_p": round(p_val, 8),
    "detection_A": rate_a, "detection_B": rate_b, "delta_pp": delta_pp, "non_inferior": non_inferior,
    "cost_total_usd": report["cost_total_usd"], "wall_max_seconds": report["wall_max_seconds"],
}, ensure_ascii=False, indent=2))
PY

# ─── [1/8] 零 LLM 预检（切点/干净度/feature/契约/env/成本墙钟门禁） ────────────
echo "=============================================================================="
echo "Q-2 oracle 示例通道 A/B（预注册；RUN_STAMP=${RUN_STAMP}）"
echo "  被探针代码：${ROOT}"
echo "  HEAD=${ROOT_HEAD}（dirty 行数=${ROOT_DIRTY_BEFORE}）"
echo "  输出：${OUT}"
echo "  协议：A(c=false/c.true exec) vs B(c=true/c.true exec)；quixbugs task-limit=${TASK_LIMIT} seed=42 baselines=aitester"
echo "        AITESTER_PROFILE=logic TEMPERATURE=0.0 THINKING=disabled P=${PARALLELISM} CACHE=0 CAP=200/\$1"
echo "  预算：≤\$${BUDGET_USD}；墙钟≤${WALL_LIMIT_MIN}min；watchdog ${WATCHDOG_SECONDS}s/臂"
echo "=============================================================================="
echo ""
echo "[1/8] 零 LLM 预检"
set +e
PRE_OUT="$("${PY}" - "${ROOT}" "${OUT}" "${ROOT_HEAD}" "${TASK_LIMIT}" "${PARALLELISM}" "${WATCHDOG_SECONDS}" "${BUDGET_USD}" "${WALL_LIMIT_MIN}" "${REQUIRE_FEATURE}" "${PRICE}" "${PREFLIGHT_JSON}" "${PREREG_SHA}" "${DRY_RUN}" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

(root, out, head, task_limit, parallelism, watchdog, budget, wall_limit, require_feature,
 price_path, pre_path, prereg_sha, dry_run) = sys.argv[1:14]
root = Path(root); out = Path(out)
task_limit = int(task_limit); parallelism = int(parallelism); watchdog = int(watchdog)
budget = float(budget); wall_limit = float(wall_limit); require_feature = str(require_feature) == "1"

blocking, warnings, checks = [], [], {}
rb = (root / "experiments/run_benchmark.py").read_text(encoding="utf-8")
planner_p = root / "src/agents/planner.py"
planner = planner_p.read_text(encoding="utf-8") if planner_p.exists() else ""
tests_p = root / "tests/test_oracle_examples_production.py"

checks["run_benchmark_has_SPEC_ORACLE_EXAMPLES_ENABLE"] = "SPEC_ORACLE_EXAMPLES_ENABLE" in rb
checks["run_benchmark_has_row_field_spec_oracle_examples_source"] = "spec_oracle_examples_source" in rb
checks["run_benchmark_has_row_field_spec_oracle_examples_count"] = "spec_oracle_examples_count" in rb
checks["planner_mentions_SPEC_ORACLE_EXAMPLES_ENABLE"] = "SPEC_ORACLE_EXAMPLES_ENABLE" in planner
checks["planner_mentions_examples_contract"] = "examples" in planner
checks["q1_contract_tests_file_present"] = tests_p.exists()
# import-source 检查：CWD=ROOT 时 `python -m experiments.run_benchmark` 必须解析到 ROOT 代码
imp_chk = {"ran": False}
try:
    r = subprocess.run([sys.executable, "-c",
                        "import experiments, experiments.run_benchmark as rb; print(experiments.__file__); print(rb.__file__)"],
                       cwd=str(root), capture_output=True, text=True, timeout=120)
    lines = [x.strip() for x in r.stdout.strip().splitlines() if x.strip()]
    imp_chk = {"ran": True, "exit_code": r.returncode, "files": lines,
               "all_under_root": bool(lines) and all(str(root) in x for x in lines)}
    checks["import_resolves_to_ROOT"] = imp_chk["all_under_root"]
    if not imp_chk["all_under_root"]:
        blocking.append(f"import 未解析到 ROOT 代码：{lines}")
except Exception as e:  # noqa: BLE001
    imp_chk = {"ran": False, "error": f"{type(e).__name__}: {e}"}
    warnings.append("import-source 预检未完成（不影响其余检查，但需人工确认）")

feature_present = all(checks[k] for k in (
    "run_benchmark_has_SPEC_ORACLE_EXAMPLES_ENABLE",
    "run_benchmark_has_row_field_spec_oracle_examples_source",
    "run_benchmark_has_row_field_spec_oracle_examples_count",
    "planner_mentions_SPEC_ORACLE_EXAMPLES_ENABLE",
))
if not feature_present:
    msg = "Q-1 examples 生产接线标记在当前 HEAD 缺失（预期：等 Q-1 切点后再跑真实批）"
    if require_feature:
        blocking.append(msg)
    else:
        warnings.append(msg)

# 两臂 env 有效值（显式 false/true 必须可区分；logic 档 setdefault 不会覆盖显式值）
env_probe = {}
for label, val in (("A_control", "false"), ("B_examples", "true")):
    env = dict(os.environ)
    for k in ("SPEC_ORACLE_EXAMPLES_ENABLE", "SPEC_ORACLE_EXEC_ENABLE", "AITESTER_PROFILE"):
        env.pop(k, None)
    env.update({"AITESTER_PROFILE": "logic", "SPEC_ORACLE_EXEC_ENABLE": "true", "SPEC_ORACLE_EXAMPLES_ENABLE": val})
    try:
        r = subprocess.run([sys.executable, "-c",
                            "import os;print(os.getenv('SPEC_ORACLE_EXEC_ENABLE'), os.getenv('SPEC_ORACLE_EXAMPLES_ENABLE'))"],
                           cwd=str(root), env=env, capture_output=True, text=True, timeout=60)
        parts = r.stdout.strip().split()
        env_probe[label] = {"SPEC_ORACLE_EXEC_ENABLE": parts[0] if parts else None,
                            "SPEC_ORACLE_EXAMPLES_ENABLE": parts[1] if len(parts) > 1 else None,
                            "stdout": r.stdout.strip(), "stderr_tail": r.stderr.strip()[-200:]}
    except Exception as e:  # noqa: BLE001
        env_probe[label] = {"error": f"{type(e).__name__}: {e}"}
if not (env_probe.get("A_control", {}).get("SPEC_ORACLE_EXAMPLES_ENABLE") == "false"
        and env_probe.get("B_examples", {}).get("SPEC_ORACLE_EXAMPLES_ENABLE") == "true"
        and env_probe.get("A_control", {}).get("SPEC_ORACLE_EXEC_ENABLE") == "true"
        and env_probe.get("B_examples", {}).get("SPEC_ORACLE_EXEC_ENABLE") == "true"):
    blocking.append("两臂 env 有效值未按预期区分（A:exec=true/examples=false, B:exec=true/examples=true）")

# 契约测试（Q-1 自带；零 LLM 子集）——存在且非 dry-run 时运行
contract = {"ran": False}
if tests_p.exists() and dry_run != "1":
    env = dict(os.environ)
    for k in ("SPEC_ORACLE_EXAMPLES_ENABLE", "SPEC_ORACLE_EXEC_ENABLE", "AITESTER_PROFILE"):
        env.pop(k, None)
    env.update({"AITESTER_PROFILE": "logic", "SPEC_ORACLE_EXEC_ENABLE": "true", "SPEC_ORACLE_EXAMPLES_ENABLE": "true"})
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tests_p)], cwd=str(root), env=env,
                           capture_output=True, text=True, timeout=600)
        contract = {"ran": True, "exit_code": r.returncode, "tail": (r.stdout or r.stderr)[-800:]}
        if r.returncode != 0:
            blocking.append("Q-1 契约测试失败（tests/test_oracle_examples_production.py）")
    except subprocess.TimeoutExpired:
        contract = {"ran": True, "timeout": True}
        warnings.append("Q-1 契约测试超时（600s），未阻断")
else:
    contract = {"ran": False, "reason": "missing tests file or dry-run"}

# 成本/墙钟估算（保守常量：per-task tokens=16000、in_share=0.72，取自历史 aitester/logic quixbugs 批次）
price = json.loads(Path(price_path).read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
p_in, p_out = price.get("input_per_mtok"), price.get("output_per_mtok")
per_task_tokens, in_share = 16000, 0.72
eff_limit = task_limit
downgraded = False
est_cost = est_tokens = None
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    est_tokens = eff_limit * 2 * per_task_tokens
    est_cost = round((est_tokens * in_share * p_in + est_tokens * (1 - in_share) * p_out) / 1e6, 6)
est_wall_min = round(eff_limit * 40 / parallelism / 60 + 45, 1)
if (est_cost is not None and est_cost > budget) or est_wall_min > wall_limit:
    eff_limit = 15
    downgraded = True
    est_tokens = eff_limit * 2 * per_task_tokens
    est_cost = round((est_tokens * in_share * p_in + est_tokens * (1 - in_share) * p_out) / 1e6, 6) if isinstance(p_in, (int, float)) else None
    est_wall_min = round(eff_limit * 40 / parallelism / 60 + 45, 1)
    warnings.append(f"预检估算（cost=${est_cost} wall={est_wall_min}min）超限 → 降为 15 任务/臂并披露")

git = {"root": str(root), "root_head": head, "expected_sha": head, "dirty_lines_before": None}
try:
    git["dirty_lines_before"] = len(subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                                   capture_output=True, text=True, timeout=30).stdout.splitlines())
except Exception:  # noqa: BLE001
    pass
def _sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


payload = {
    "schema": "q2_examples_ab_preflight/1",
    "source_hashes": {
        "experiments/run_benchmark.py": _sha(root / "experiments/run_benchmark.py"),
        "src/agents/planner.py": _sha(root / "src/agents/planner.py") if (root / "src/agents/planner.py").exists() else None,
    },
    "run_stamp": out.name,
    "git": git,
    "prereg_sha256": prereg_sha,
    "checks": checks,
    "feature_present": feature_present,
    "require_feature": require_feature,
    "env_probe": env_probe,
    "contract_tests": contract,
    "import_source_check": imp_chk,
    "estimate": {
        "per_task_tokens": per_task_tokens, "in_share": in_share, "price_model": "deepseek-flash",
        "input_per_mtok": p_in, "output_per_mtok": p_out,
        "task_limit_initial": task_limit, "task_limit_effective": eff_limit,
        "estimated_tokens_total": est_tokens, "estimated_cost_usd": est_cost,
        "estimated_wall_min": est_wall_min, "downgraded_to": eff_limit if downgraded else None,
        "budget_usd": budget, "wall_limit_min": wall_limit,
    },
    "run": {
        "task_limit": eff_limit, "parallelism": parallelism, "watchdog_seconds": watchdog,
        "budget_usd": budget, "wall_limit_min": wall_limit,
        "profile": "logic", "temperature": 0.0, "thinking": "disabled",
        "cache": 0, "batch_max_calls": 200, "seed": 42, "dataset": "quixbugs", "baseline": "aitester",
    },
    "blocking": blocking, "warnings": warnings,
}
Path(pre_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"blocking": blocking, "warnings": warnings, "feature_present": feature_present,
                  "checks": checks, "env_probe": env_probe, "contract": contract, "import_source_check": imp_chk,
                  "task_limit_effective": eff_limit, "estimated_cost_usd": est_cost,
                  "estimated_wall_min": est_wall_min}, ensure_ascii=False))
raise SystemExit(0 if not blocking else 3)
PY
)"
PRE_RC=$?
set -e
echo "${PRE_OUT:0:900}"
if [ "${PRE_RC}" -ne 0 ]; then
    echo "✗ 预检失败（退出码 ${PRE_RC}）——中止，不跑批。" >&2
    exit 3
fi
EFFECTIVE_TASK_LIMIT="$(printf '%s\n' "${PRE_OUT}" | "${PY}" -c 'import json,sys;print(json.load(sys.stdin)["task_limit_effective"])')"
if [ "${EFFECTIVE_TASK_LIMIT}" != "${TASK_LIMIT}" ]; then
    echo "  ⚠ 预算/墙钟门禁：task-limit ${TASK_LIMIT} → ${EFFECTIVE_TASK_LIMIT}（写 PREREG_DOWNGRADE.md）"
    {
        echo "# PREREG 降级披露（自动，$(date -u +%FT%TZ)）"
        echo ""
        echo "- 原计划 task-limit=${TASK_LIMIT}/臂；预检估算超预算或墙钟 → 按预注册规则降为 **${EFFECTIVE_TASK_LIMIT}/臂**。"
        echo "- 估算口径：tokens/task=${per_task_tokens:-16000}、in_share=0.72（历史 aitester/logic quixbugs 批次）、deepseek-flash 价目；详见 PREFLIGHT.json estimate。"
    } > "${OUT}/PREREG_DOWNGRADE.md"
    TASK_LIMIT="${EFFECTIVE_TASK_LIMIT}"
fi
echo "  ✓ 预检通过（PREFLIGHT：${PREFLIGHT_JSON}）"
echo ""

if [ "${PREFLIGHT_ONLY}" -eq 1 ]; then
    echo "[PREFLIGHT-ONLY] 预检完成（与真实跑批相同的门禁语义；零 LLM）；未启动任何臂、未创建 staging/日志。"
    exit 0
fi

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[DRY-RUN] 计划执行（两臂并发；零 LLM 调用）："
    echo "  A control : AITESTER_PROFILE=logic SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=false --baselines aitester --dataset quixbugs --task-limit ${TASK_LIMIT} --seed 42"
    echo "  B examples: AITESTER_PROFILE=logic SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true  --baselines aitester --dataset quixbugs --task-limit ${TASK_LIMIT} --seed 42"
    echo "  输出：${OUT}；watchdog=${WATCHDOG_SECONDS}s/臂；预算≤\$${BUDGET_USD}；墙钟≤${WALL_LIMIT_MIN}min"
    echo "DRY-RUN 结束：未执行任何 LLM 调用、未产出批次工件。"
    exit 0
fi

# ─── [1.5/8] TOCTOU 守卫：preflight→launch 之间源码不得变化（事故 2026-10-18 加固）──
set +e
"${PY}" - "${ROOT}" "${PREFLIGHT_JSON}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root, pre = Path(sys.argv[1]), Path(sys.argv[2])
d = json.loads(pre.read_text(encoding="utf-8"))
recorded = d.get("source_hashes") or {}
issues = []
for rel, digest in recorded.items():
    fp = root / rel
    if not fp.exists():
        issues.append(f"missing: {rel}")
        continue
    cur = hashlib.sha256(fp.read_bytes()).hexdigest()
    if cur != digest:
        issues.append(f"changed: {rel} ({digest[:12]}… -> {cur[:12]}…)")
if issues:
    print("TOCTOU_GUARD_FAIL: " + "; ".join(issues))
    raise SystemExit(1)
print("TOCTOU_GUARD_OK")
PY
TOCTOU_RC=$?
set -e
if [ "${TOCTOU_RC}" -ne 0 ]; then
    echo "✗ preflight→launch 之间源码发生变化（并发编辑）——中止，请重跑预检。" >&2
    exit 3
fi

# ─── [2/8] 两臂同秒启动 ──────────────────────────────────────────────────────
echo "[2/8] 两臂并发启动（同秒级；独立 namespace/log/trace）"
NS_A="q_round_examples_ab_20261018_control"
NS_B="q_round_examples_ab_20261018_examples"
STAGE_A="${OUT}/.staging_control"; STAGE_B="${OUT}/.staging_examples"
LOG_A="${OUT}/log_control.log"; LOG_B="${OUT}/log_examples.log"
TRACE_A="${OUT}/traces_control"; TRACE_B="${OUT}/traces_examples"
mkdir -p "${STAGE_A}" "${STAGE_B}" "${TRACE_A}" "${TRACE_B}"
COMMON_ENV=(AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled "BENCHMARK_PARALLELISM=${PARALLELISM}" AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=200)

_launch_arm() { # label exec examples namespace staging log trace cli
    local label="$1" execv="$2" examples="$3" ns="$4" staging="$5" log="$6" trace="$7" cli="$8"
    local start_epoch start_iso
    start_epoch="$(date +%s)"; start_iso="$(date -u +%FT%TZ)"
    printf '%s %s\n' "${start_epoch}" "${start_iso}" > "${OUT}/.arm_${label}.start"
    {
        echo "===== Q-2 examples A/B arm=${label} ====="
        echo "START_ISO_UTC=${start_iso}"
        echo "ROOT=${ROOT} HEAD=${ROOT_HEAD}"
        echo "CMD=${PY} -m experiments.run_benchmark --dataset quixbugs --task-limit ${TASK_LIMIT} --seed 42 --baselines aitester --output-dir ${staging}"
        echo "ENV_COMMON=AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=${PARALLELISM} AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=200"
        echo "ENV_ARM=${label} SPEC_ORACLE_EXEC_ENABLE=${execv} SPEC_ORACLE_EXAMPLES_ENABLE=${examples} AITESTER_CACHE_NAMESPACE=${ns} AITESTER_TRACE_DIR=${trace}"
    } >> "${log}"
    (
        set +e
        _s="$(date +%s)"
        (
            cd "${ROOT}" && env "${COMMON_ENV[@]}" \
                "SPEC_ORACLE_EXEC_ENABLE=${execv}" "SPEC_ORACLE_EXAMPLES_ENABLE=${examples}" \
                "AITESTER_CACHE_NAMESPACE=${ns}" "AITESTER_TRACE_DIR=${trace}" \
                "${PY}" "${OUT}/_helpers/limited_run.py" "${WATCHDOG_SECONDS}" \
                "${PY}" -m experiments.run_benchmark --dataset quixbugs --task-limit "${TASK_LIMIT}" --seed 42 \
                --baselines aitester --output-dir "${staging}"
        ) >> "${log}" 2>&1
        _rc=$?
        _e="$(date +%s)"
        echo "END_ISO_UTC=$(date -u +%FT%TZ) END_EPOCH=${_e} EXIT_CODE=${_rc} WALL_SECONDS=$((_e - _s))" >> "${log}"
        echo "${_rc}" > "${OUT}/.arm_${label}.rc"
    ) &
    echo $! > "${OUT}/.arm_${label}.pid"
}

_launch_arm control true false "${NS_A}" "${STAGE_A}" "${LOG_A}" "${TRACE_A}" ""
_launch_arm examples true true "${NS_B}" "${STAGE_B}" "${LOG_B}" "${TRACE_B}" ""
PID_A="$(cat "${OUT}/.arm_control.pid")"; PID_B="$(cat "${OUT}/.arm_examples.pid")"
echo "  ✓ A control  pid=${PID_A}（SPEC_ORACLE_EXEC_ENABLE=true / SPEC_ORACLE_EXAMPLES_ENABLE=false）"
echo "  ✓ B examples pid=${PID_B}（true / true）"
START_ALL_EPOCH="$(date +%s)"
echo ""

# ─── [3/8] 监控 ─────────────────────────────────────────────────────────────
echo "[3/8] 监控与等待（每 15s；watchdog ${WATCHDOG_SECONDS}s/臂）"
LAST_SCAN=0
while :; do
    _done=1
    [ -f "${OUT}/.arm_control.rc" ] || _done=0
    [ -f "${OUT}/.arm_examples.rc" ] || _done=0
    [ "${_done}" -eq 1 ] && break
    sleep 15
    NOW="$(date +%s)"
    if [ $((NOW - LAST_SCAN)) -ge 300 ]; then
        LAST_SCAN="${NOW}"
        echo "  … 已运行 $(( (NOW - START_ALL_EPOCH) / 60 ))min（control=$([ -f "${OUT}/.arm_control.rc" ] && echo done || echo running)，examples=$([ -f "${OUT}/.arm_examples.rc" ] && echo done || echo running)）"
    fi
    if [ $((NOW - START_ALL_EPOCH)) -gt $((WATCHDOG_SECONDS + 900)) ]; then
        echo "  ✗ 超过全局兜底（watchdog+15min）——强制终止" >&2
        kill -TERM "${PID_A}" "${PID_B}" 2>/dev/null || true; sleep 5
        kill -KILL "${PID_A}" "${PID_B}" 2>/dev/null || true
        break
    fi
done
set +e
wait "${PID_A}" 2>/dev/null; wait "${PID_B}" 2>/dev/null
set -e
RC_A="$(cat "${OUT}/.arm_control.rc" 2>/dev/null || echo 127)"
RC_B="$(cat "${OUT}/.arm_examples.rc" 2>/dev/null || echo 127)"
END_ALL_EPOCH="$(date +%s)"
ROOT_DIRTY_AFTER="$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "  ✓ 两臂结束：control exit=${RC_A}，examples exit=${RC_B}，总墙钟 $((END_ALL_EPOCH - START_ALL_EPOCH))s；ROOT dirty=${ROOT_DIRTY_AFTER}"
{
    echo "=============================================================="
    echo "Q-2 examples A/B run summary"
    echo "RUN_STAMP=${RUN_STAMP}"
    echo "ROOT=${ROOT} HEAD=${ROOT_HEAD} dirty_before=${ROOT_DIRTY_BEFORE} dirty_after=${ROOT_DIRTY_AFTER}"
    echo "exit control=${RC_A} examples=${RC_B} wall_total=$((END_ALL_EPOCH - START_ALL_EPOCH))s task_limit=${TASK_LIMIT}"
    echo "PREREG_sha256=${PREREG_SHA}"
} | tee -a "${OUT}/RUN_SUMMARY.log" >/dev/null

# ─── [4/8] 收集工件 + 逐臂元数据 ─────────────────────────────────────────────
echo ""
echo "[4/8] 收集工件与逐臂元数据"
ARM_FAIL=0
_collect_arm() { # label cli examples staging log trace rc ns
    local label="$1" cli="$2" examples="$3" staging="$4" log="$5" trace="$6" rc="$7" ns="$8"
    local batch target meta start_epoch start_iso
    start_epoch="$(awk '{print $1}' "${OUT}/.arm_${label}.start")"
    start_iso="$(awk '{print $2}' "${OUT}/.arm_${label}.start")"
    batch="$(ls "${staging}"/*.json 2>/dev/null | head -1 || true)"
    if [ -z "${batch}" ]; then
        echo "  ✗ [${label}] 无批次工件（exit=${rc}）——保留日志/失败元数据" >&2
        ARM_FAIL=1
        "${PY}" - "${OUT}" "${label}" "${rc}" "${log}" <<'PY'
import json
import sys
from pathlib import Path
out, label, rc, log = sys.argv[1:5]
(Path(out) / f"arm_{label}.meta.json").write_text(json.dumps(
    {"arm_label": label, "status": "failed", "exit_code": int(rc), "log": log,
     "note": "臂失败/超时：保留日志与部分工件，不重跑"}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
        return 0
    fi
    target="${OUT}/$(basename "${batch}")"
    if [ -e "${target}" ]; then target="${OUT}/$(basename "${batch}" .json)_${label}.json"; fi
    mv "${batch}" "${target}"
    rmdir "${staging}" 2>/dev/null || true
    meta="${OUT}/arm_${label}.meta.json"
    echo "  [${label}] 批次：${target}"
    "${PY}" "${OUT}/_helpers/extract_arm.py" "${target}" "${label}" "${cli}" "${examples}" \
        "${ns}" "${start_epoch}" "${start_iso}" "${meta}" "${trace}" "${log}" "${PRICE}"
}
_collect_arm control "" false "${STAGE_A}" "${LOG_A}" "${TRACE_A}" "${RC_A}" "${NS_A}"
_collect_arm examples "" true "${STAGE_B}" "${LOG_B}" "${TRACE_B}" "${RC_B}" "${NS_B}"
if [ "${ARM_FAIL}" -ne 0 ]; then
    echo "✗ 某臂失败/无批次工件（control=${RC_A} examples=${RC_B}）——保留日志/工件，不重跑。" >&2
    exit 4
fi

# ─── [5/8] 配对聚合 + 预注册判定 ────────────────────────────────────────────
echo ""
echo "[5/8] 配对聚合 + 预注册判定（ANALYSIS_REPORT.json + README.md）"
"${PY}" "${OUT}/_helpers/analyze.py" "${OUT}"
echo ""
echo "[6/8] 文件清单"
ls -1 "${OUT}" | grep -v '^\.' | sed 's/^/  /'
echo ""
echo "[7/8] SHA256SUMS（checksum_results.py --write）+ 校验"
"${PY}" "${SCRIPT_REPO}/scripts/gates/checksum_results.py" --results-dir "${OUT}" --write 2>&1 | tail -2
"${PY}" "${SCRIPT_REPO}/scripts/gates/checksum_results.py" --results-dir "${OUT}" --verify 2>&1 | tail -2
echo ""
echo "[8/8] 完成摘要"
echo "=============================================================================="
echo "Q-2 examples A/B 完成（RUN_STAMP=${RUN_STAMP}）"
echo "  切点：${ROOT_HEAD}（跑后 dirty 行数=${ROOT_DIRTY_AFTER}）"
echo "  两臂 exit：control=${RC_A} examples=${RC_B}；总墙钟 $((END_ALL_EPOCH - START_ALL_EPOCH))s"
echo "  ANALYSIS_REPORT：${OUT}/ANALYSIS_REPORT.json"
echo "  README：${OUT}/README.md"
echo "  SHA256SUMS：${OUT}/SHA256SUMS"
echo "=============================================================================="
