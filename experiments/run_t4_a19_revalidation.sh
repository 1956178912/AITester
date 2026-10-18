#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# T4（T 轮 2026-10-18）：A-19 抢占优先级修复的**默认协议**真实 LLM 复验
#
# 复验对象（承接 S-2 登记缺陷）：生产默认协议（PATCH_EVIDENCE_GATE_ENABLE=true）
# 下 repair-invalid 与停滞窗口在**同一迭代**收敛；修复前停滞分支永不执行，
# ON 臂的 coverage_stall 只是 determine_stop_reason 的标签兜底（日志仍写
# "连续多次修复无效"）。T4 修复后，ON 臂应由"停滞优先"分支拥有终止决定。
#
# 本脚本复用 S-2 的确定性失败注入 harness（experiments/run_b8_injection.py），
# 两臂**并发**、唯一差异 = COVERAGE_STALL_DETECT_ENABLE=true|false；
# **不设** --extra-env PATCH_EVIDENCE_GATE_ENABLE=false（默认闸协议，与 S-2 主批
# 的 gate-off 口径相反，正是本复验要覆盖的场景）。
#
# 真实 LLM 执行由 Lead 在**干净切点 worktree** 上跑（跑前 PREREG 冻结，见
# experiments/results/t_round_semantic_fixes_20261018/A19_REVALIDATION_PREREG.md）。
# 预算上界 ≤$0.15（两臂合计；参考 S-2 默认闸冒烟 2 任务 ≈$0.016 → 10 任务 ≈$0.08）。
#
# 用法：
#   bash experiments/run_t4_a19_revalidation.sh \
#     --root /Users/wangchenyu/Workspace/AITester-t-t4-<sha> \
#     --expect-sha <cutpoint-sha> \
#     [--out experiments/results/t_round_a19_default_gate_20261018] \
#     [--tasks 10] [--seed 42] [--parallel 4] [--inject-rounds 3] \
#     [--watchdog-seconds 1500] [--strict] [--dry-run]
#
# 产物（--out 下）：PREREG.md / RUN_SUMMARY.log / log_arm_on.log /
# log_arm_off.log / arm_on/ arm_off/（批次 JSON + 注入记录 + traces）/
# REPORT.json（S-2 harness 聚合，**非本批判据**）/ ANALYSIS.json（本批判定）/
# SHA256SUMS。
#
# 退出码：0=复验执行完成（判定写入 ANALYSIS.json）；2=参数/前置条件失败；
#         3=--strict 且 classification != confirmed_priority；4=单臂运行失败。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT=""
EXPECT_SHA=""
OUT="${SCRIPT_REPO}/experiments/results/t_round_a19_default_gate_20261018"
TASKS=10
SEED=42
PARALLEL=4
INJECT_ROUNDS=3
WATCHDOG_SECONDS=1500
STRICT=0
DRY_RUN=0

# PREREG 模板（跑前冻结文本；脚本会复制到 OUT/PREREG.md 并记录 sha256）
PREREG_TEMPLATE="${SCRIPT_REPO}/experiments/results/t_round_semantic_fixes_20261018/A19_REVALIDATION_PREREG.md"

usage() { sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --root) [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }; ROOT="$2"; shift 2 ;;
        --expect-sha) [ $# -ge 2 ] || { echo "--expect-sha 需要完整 sha" >&2; exit 2; }; EXPECT_SHA="$2"; shift 2 ;;
        --out) [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --tasks) [ $# -ge 2 ] || { echo "--tasks 需要正整数" >&2; exit 2; }; TASKS="$2"; shift 2 ;;
        --seed) [ $# -ge 2 ] || { echo "--seed 需要整数" >&2; exit 2; }; SEED="$2"; shift 2 ;;
        --parallel) [ $# -ge 2 ] || { echo "--parallel 需要正整数" >&2; exit 2; }; PARALLEL="$2"; shift 2 ;;
        --inject-rounds) [ $# -ge 2 ] || { echo "--inject-rounds 需要正整数" >&2; exit 2; }; INJECT_ROUNDS="$2"; shift 2 ;;
        --watchdog-seconds) [ $# -ge 2 ] || { echo "--watchdog-seconds 需要数值" >&2; exit 2; }; WATCHDOG_SECONDS="$2"; shift 2 ;;
        --strict) STRICT=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

for _v in TASKS SEED PARALLEL INJECT_ROUNDS; do
    case "${!_v:-}" in '' | *[!0-9]*) echo "--${_v} 必须整数" >&2; exit 2 ;; esac
done

[ -n "${ROOT}" ] || { echo "✗ 必须给 --root（干净切点 worktree）" >&2; exit 2; }
[ -d "${ROOT}" ] || { echo "✗ ROOT 不存在：${ROOT}" >&2; exit 2; }
ROOT="$(cd "${ROOT}" && pwd)"
[ -f "${ROOT}/experiments/run_benchmark.py" ] || { echo "✗ ROOT 不像 AITester 仓库：${ROOT}" >&2; exit 2; }
[ -x "${SCRIPT_REPO}/.venv/bin/python" ] || { echo "✗ 缺 python：${SCRIPT_REPO}/.venv/bin/python" >&2; exit 2; }
PY="${SCRIPT_REPO}/.venv/bin/python"
HARNESS="${SCRIPT_REPO}/experiments/run_b8_injection.py"
[ -f "${HARNESS}" ] || { echo "✗ 缺注入 harness：${HARNESS}" >&2; exit 2; }
[ -f "${PREREG_TEMPLATE}" ] || { echo "✗ 缺 PREREG 模板：${PREREG_TEMPLATE}" >&2; exit 2; }

# ── 真实模式前置校验（干净切点 + 切点 sha + .env.local）──────────────────────
SNAP_SHA="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo "")"
DIRTY="$(git -C "${ROOT}" status --porcelain 2>/dev/null || echo "<git-error>")"
ROOT_HAS_ENV=0
[ -f "${ROOT}/.env.local" ] && ROOT_HAS_ENV=1

if [ "${DRY_RUN}" -eq 0 ]; then
    [ -n "${EXPECT_SHA}" ] || { echo "✗ 真实模式必须给 --expect-sha（切点校验）" >&2; exit 2; }
    [ "${SNAP_SHA}" = "${EXPECT_SHA}" ] || { echo "✗ ROOT HEAD=${SNAP_SHA} 与 --expect-sha=${EXPECT_SHA} 不一致" >&2; exit 2; }
    [ -z "${DIRTY}" ] || { echo "✗ ROOT 工作树不干净（dirty_lines=$(printf '%s\n' "${DIRTY}" | grep -c . || true)）：${DIRTY}" >&2; exit 2; }
    [ "${ROOT_HAS_ENV}" -eq 1 ] || { echo "✗ ROOT 缺 .env.local（真实 LLM 需要）" >&2; exit 2; }
else
    [ -n "${EXPECT_SHA}" ] && [ "${SNAP_SHA}" != "${EXPECT_SHA}" ] && echo "⚠ dry-run：ROOT HEAD 与 --expect-sha 不一致（仅提示）"
    [ -n "${DIRTY}" ] && echo "⚠ dry-run：ROOT 工作树不干净（真实模式会拒绝）"
fi

mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
PREREG_MD="${OUT}/PREREG.md"
if [ ! -f "${PREREG_MD}" ]; then
    cp "${PREREG_TEMPLATE}" "${PREREG_MD}"
fi
PREREG_SHA="$(shasum -a 256 "${PREREG_MD}" | awk '{print $1}')"
TEMPLATE_SHA="$(shasum -a 256 "${PREREG_TEMPLATE}" | awk '{print $1}')"
if [ "${PREREG_SHA}" != "${TEMPLATE_SHA}" ]; then
    echo "✗ ${PREREG_MD} 与冻结模板不一致（预注册被改动/陈旧）：拒绝跑批" >&2
    echo "  OUT/PREREG.md sha256=${PREREG_SHA}" >&2
    echo "  模板       sha256=${TEMPLATE_SHA}" >&2
    exit 2
fi

echo "================================================================"
echo "T4 A-19 默认协议复验（注入 harness；两臂并发）"
echo "  ROOT=${ROOT}"
echo "  HEAD=${SNAP_SHA}  dirty=$([ -z "${DIRTY}" ] && echo false || echo true)"
echo "  OUT=${OUT}"
echo "  PREREG sha256=${PREREG_SHA}"
echo "  tasks=${TASKS} seed=${SEED} parallel=${PARALLEL} inject_rounds=${INJECT_ROUNDS}"
echo "  协议：默认 PATCH_EVIDENCE_GATE_ENABLE（不设 --extra-env 关闭）；唯一差异=COVERAGE_STALL_DETECT_ENABLE"
echo "================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[dry-run] 将执行（不产生 LLM 调用）："
    echo "  ${PY} ${HARNESS} --root ${ROOT} --out ${OUT} --arm on  --tasks ${TASKS} --seed ${SEED} --profile fast --parallel ${PARALLEL} --inject-rounds ${INJECT_ROUNDS} --watchdog-seconds ${WATCHDOG_SECONDS}"
    echo "  ${PY} ${HARNESS} --root ${ROOT} --out ${OUT} --arm off --tasks ${TASKS} --seed ${SEED} --profile fast --parallel ${PARALLEL} --inject-rounds ${INJECT_ROUNDS} --watchdog-seconds ${WATCHDOG_SECONDS}"
    echo "  ${PY} ${HARNESS} --out ${OUT} --aggregate-only"
    echo "[dry-run] 通过（真实模式将导出 ROOT/.env.local 的 LLM_1_* 到子进程环境，不打印值）"
    exit 0
fi

# ── 导出 LLM 凭证到子进程环境（只导出 LLM_1_* / DEEPSEEK_API_KEY，不打印值）──
while IFS='=' read -r _k _v; do
    case "${_k}" in
        LLM_1_API_KEY | LLM_1_BASE_URL | LLM_1_MODEL_NAME | DEEPSEEK_API_KEY) export "${_k}=${_v}" ;;
    esac
done < "${ROOT}/.env.local"

# 工具链 python 选择：优先主仓 venv（驱动脚本所在仓），其次 ROOT venv
if [ -x "${ROOT}/.venv/bin/python" ] && [ ! -x "${SCRIPT_REPO}/.venv/bin/python" ]; then
    PY="${ROOT}/.venv/bin/python"
fi

SUMMARY="${OUT}/RUN_SUMMARY.log"
{
    echo "START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "ROOT=${ROOT}"
    echo "ROOT_HEAD=${SNAP_SHA}"
    echo "PREREG_SHA256=${PREREG_SHA}"
    echo "HARNESS=${HARNESS}"
    echo "ARGS=--tasks ${TASKS} --seed ${SEED} --parallel ${PARALLEL} --inject-rounds ${INJECT_ROUNDS} --watchdog-seconds ${WATCHDOG_SECONDS}"
    echo "PROTOCOL=default_gate_on (PATCH_EVIDENCE_GATE_ENABLE 未显式关闭)"
} > "${SUMMARY}"

# ── 两臂并发（独立进程；stdout+stderr 落各自日志，供分支归属 grep 证据）─────
set +e
( cd "${SCRIPT_REPO}" && "${PY}" "${HARNESS}" \
    --root "${ROOT}" --out "${OUT}" --arm on \
    --tasks "${TASKS}" --seed "${SEED}" --profile fast --parallel "${PARALLEL}" \
    --inject-rounds "${INJECT_ROUNDS}" --watchdog-seconds "${WATCHDOG_SECONDS}" \
    > "${OUT}/log_arm_on.log" 2>&1 ) &
PID_ON=$!
( cd "${SCRIPT_REPO}" && "${PY}" "${HARNESS}" \
    --root "${ROOT}" --out "${OUT}" --arm off \
    --tasks "${TASKS}" --seed "${SEED}" --profile fast --parallel "${PARALLEL}" \
    --inject-rounds "${INJECT_ROUNDS}" --watchdog-seconds "${WATCHDOG_SECONDS}" \
    > "${OUT}/log_arm_off.log" 2>&1 ) &
PID_OFF=$!
wait "${PID_ON}"; RC_ON=$?
wait "${PID_OFF}"; RC_OFF=$?
set -e
echo "EXIT_ARM_ON=${RC_ON}" >> "${SUMMARY}"
echo "EXIT_ARM_OFF=${RC_OFF}" >> "${SUMMARY}"
echo "END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${SUMMARY}"

if [ "${RC_ON}" -ne 0 ] || [ "${RC_OFF}" -ne 0 ]; then
    echo "✗ 单臂运行失败（on=${RC_ON} off=${RC_OFF}），不重跑（遵守不重跑纪律）；见 ${OUT}/log_arm_*.log" >&2
    echo "  REPORT/ANALYSIS 不生成（失败如实保留日志与半成品工件）" >&2
    exit 4
fi

# ── 零 LLM 聚合（S-2 harness 工件；其 verdict 非本批判据）──────────────────
( cd "${SCRIPT_REPO}" && "${PY}" "${HARNESS}" --out "${OUT}" --aggregate-only ) >> "${SUMMARY}" 2>&1 || true

# ── 本批判定（零 LLM；读两臂批次 JSON + 日志分支归属计数）──────────────────
ANALYSIS_RC=0
( cd "${SCRIPT_REPO}" && "${PY}" - "${OUT}" <<'PYEOF'
import json
import re
import sys
from pathlib import Path

out = Path(sys.argv[1]).resolve()
n_expect = None
for line in (out / "RUN_SUMMARY.log").read_text(encoding="utf-8").splitlines():
    m = re.match(r"ARGS=.*--tasks (\d+)", line)
    if m:
        n_expect = int(m.group(1))
if n_expect is None:
    raise SystemExit("RUN_SUMMARY.log 缺 ARGS= 行")

PREEMPT = "同迭代优先于 repair-invalid"
STALL = "P2-4 覆盖率停滞"
REPAIR = "连续多次修复无效"


def load_batch(arm: str):
    files = sorted((out / f"arm_{arm}").glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"arm_{arm} 缺批次 JSON")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return files[-1].name, data


def rows(arm: str):
    _, data = load_batch(arm)
    details = (((data.get("results") or {}).get("aitester") or {}).get("details")) or []
    return [r for r in details if isinstance(r, dict)]


def log_counts(arm: str) -> dict:
    text = (out / f"log_arm_{arm}.log").read_text(encoding="utf-8", errors="replace")
    return {
        "preempt": text.count(PREEMPT),
        "stall": text.count(STALL),
        "repair_invalid": text.count(REPAIR),
    }


def summarize(arm: str) -> dict:
    rs = rows(arm)
    stop = {}
    for r in rs:
        key = str(r.get("stop_reason"))
        stop[key] = stop.get(key, 0) + 1
    iters = [r.get("iterations") for r in rs if isinstance(r.get("iterations"), (int, float))]
    crash = {
        str(r.get("task_id"))
        for r in rs
        if str(r.get("error_category") or "") in {"exception", "unexpected_exception", "harness_error", "crash", "timeout", "recursion_limit"}
    }
    return {
        "n": len(rs),
        "stop_reason_counts": stop,
        "iterations": iters,
        "iterations_mean": round(sum(iters) / len(iters), 4) if iters else None,
        "stall_rate": round(stop.get("coverage_stall", 0) / len(rs), 4) if rs else None,
        "repair_invalid_rate": round(stop.get("skip_debugger_repair_invalid", 0) / len(rs), 4) if rs else None,
        "crash_count": len(crash),
        "injected_rounds": None,
        "real_rounds": None,
        "per_task": [
            {
                "task_id": r.get("task_id"),
                "stop_reason": r.get("stop_reason"),
                "iterations": r.get("iterations"),
                "error_category": r.get("error_category"),
            }
            for r in rs
        ],
    }


def injection_stats(arm: str) -> dict:
    path = out / f"arm_{arm}" / f"injection_records_{arm}.jsonl"
    injected = real = 0
    tasks = set()
    if not path.is_file():
        return {"records": 0, "injected_rounds": 0, "real_rounds": 0, "tasks_with_injection": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("injected"):
            injected += 1
            tasks.add(str(rec.get("task_id")))
        else:
            real += 1
    return {
        "records": injected + real,
        "injected_rounds": injected,
        "real_rounds": real,
        "tasks_with_injection": len(tasks),
    }


on = summarize("on")
off = summarize("off")
on_log, off_log = log_counts("on"), log_counts("off")
on["injection"] = injection_stats("on")
off["injection"] = injection_stats("off")

delta_iter = None
if on["iterations_mean"] is not None and off["iterations_mean"] is not None:
    delta_iter = round(off["iterations_mean"] - on["iterations_mean"], 4)

criteria = {
    "P1_priority_ownership_on": {
        "rule": f"ON 臂 stop_reason=coverage_stall 率=1.0 且 停滞优先日志计数={n_expect} 且 repair-invalid 日志计数=0",
        "on_stall_rate": on["stall_rate"],
        "on_preempt_log": on_log["preempt"],
        "on_repair_invalid_log": on_log["repair_invalid"],
        "met": bool(
            on["n"] == n_expect
            and on["stall_rate"] == 1.0
            and on_log["preempt"] == n_expect
            and on_log["repair_invalid"] == 0
        ),
    },
    "P2_off_unchanged": {
        "rule": f"OFF 臂 stop_reason=skip_debugger_repair_invalid 率=1.0 且 repair-invalid 日志计数={n_expect} 且 停滞日志计数=0 且 crash=0",
        "off_repair_invalid_rate": off["repair_invalid_rate"],
        "off_repair_invalid_log": off_log["repair_invalid"],
        "off_stall_log": off_log["stall"],
        "off_crash": off["crash_count"],
        "met": bool(
            off["n"] == n_expect
            and off["repair_invalid_rate"] == 1.0
            and off_log["repair_invalid"] == n_expect
            and off_log["stall"] == 0
            and off["crash_count"] == 0
        ),
    },
    "P3_zero_iteration_savings": {
        "rule": "零迭代节省预注册：iterations_mean(on) == iterations_mean(off)（Δ=off−on=0）",
        "iterations_mean_on": on["iterations_mean"],
        "iterations_mean_off": off["iterations_mean"],
        "delta_iterations_off_minus_on": delta_iter,
        "note": "Δ≠0 → classification=unexpected_delta（调查项，不得当作收益）；本修复不承诺迭代节省",
        "met": delta_iter == 0,
    },
    "P4_harness_validity": {
        "rule": f"两臂注入覆盖任务={n_expect} 且 injected_rounds>0 且 crash=0",
        "on_injection": on["injection"],
        "off_injection": off["injection"],
        "met": bool(
            on["injection"]["tasks_with_injection"] == n_expect
            and off["injection"]["tasks_with_injection"] == n_expect
            and on["injection"]["injected_rounds"] > 0
            and off["injection"]["injected_rounds"] > 0
            and on["crash_count"] == 0
            and off["crash_count"] == 0
        ),
    },
}

p1, p2, p3, p4 = (criteria[k]["met"] for k in ("P1_priority_ownership_on", "P2_off_unchanged", "P3_zero_iteration_savings", "P4_harness_validity"))
if not p3:
    classification = "unexpected_delta"
elif p1 and p2 and p3 and p4:
    classification = "confirmed_priority"
else:
    classification = "not_confirmed"

analysis = {
    "experiment": "T4 / A-19 抢占优先级修复默认协议复验（S-2 注入 harness 复用）",
    "protocol": {
        "prereg_sha256": None,
        "patch_evidence_gate": "default(true)——未设 PATCH_EVIDENCE_GATE_ENABLE=false",
        "arm_env_diff": "COVERAGE_STALL_DETECT_ENABLE=true(on) / false(off)",
        "n_expect": n_expect,
        "s2_harness_verdict_note": "REPORT.json 的 S-2 verdict 判据（含 1.2 迭代节省）在默认协议下结构上不可满足，仅保留为工件，不作本批判定",
    },
    "arms": {"on": on, "off": off},
    "logs": {"on": on_log, "off": off_log},
    "criteria": criteria,
    "paired": {
        "iterations_saved_off_minus_on": delta_iter,
        "direction_off_gt_on": sum(
            1 for a, b in zip(on["per_task"], off["per_task"], strict=False) if (b.get("iterations") or 0) > (a.get("iterations") or 0)
        ),
        "direction_equal": sum(
            1 for a, b in zip(on["per_task"], off["per_task"], strict=False) if (b.get("iterations") or 0) == (a.get("iterations") or 0)
        ),
    },
    "classification": classification,
}

prereg = out / "PREREG.md"
if prereg.is_file():
    import hashlib

    analysis["protocol"]["prereg_sha256"] = hashlib.sha256(prereg.read_bytes()).hexdigest()

(out / "ANALYSIS.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

print("── T4 A-19 默认协议复验判定 ──────────────────────────────────")
print(f"P1 停滞优先分支归属（ON）：{criteria['P1_priority_ownership_on']['met']}  "
      f"stall_rate={on['stall_rate']} preempt_log={on_log['preempt']} repair_log={on_log['repair_invalid']}")
print(f"P2 默认关零变化（OFF）    ：{criteria['P2_off_unchanged']['met']}  "
      f"repair_invalid_rate={off['repair_invalid_rate']} repair_log={off_log['repair_invalid']} stall_log={off_log['stall']}")
print(f"P3 零迭代节省（预注册）   ：{criteria['P3_zero_iteration_savings']['met']}  "
      f"Δ(off−on)={delta_iter}（on={on['iterations_mean']} off={off['iterations_mean']}）")
print(f"P4 harness 有效性         ：{criteria['P4_harness_validity']['met']}")
print(f"classification = {classification}")
print(f"ANALYSIS.json → {out / 'ANALYSIS.json'}")
PYEOF
) || ANALYSIS_RC=$?

# ── 工件校验和（含日志/分析；覆盖 harness 聚合写出的 SHA256SUMS）────────────
if [ "${ANALYSIS_RC}" -eq 0 ]; then
    ( cd "${OUT}" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS )
    echo "SHA256SUMS → ${OUT}/SHA256SUMS"
else
    echo "✗ 分析脚本失败（rc=${ANALYSIS_RC}）；ANALYSIS.json 可能缺失" >&2
    exit 5
fi

if [ "${STRICT}" -eq 1 ]; then
    if grep -q '"classification": "confirmed_priority"' "${OUT}/ANALYSIS.json"; then
        echo "strict：classification=confirmed_priority"
        exit 0
    fi
    echo "strict：classification != confirmed_priority → 退出码 3" >&2
    exit 3
fi
exit 0
