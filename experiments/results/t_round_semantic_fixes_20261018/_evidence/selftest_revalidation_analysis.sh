#!/usr/bin/env bash
# T4（T 轮 2026-10-18）：A-19 复验脚本 **零 LLM 判定逻辑自测**。
#
# 目的：在 Lead 花真实 LLM 预算跑复验之前，用**构造工件**验证
# experiments/run_t4_a19_revalidation.sh 内嵌判定逻辑（P1–P4 + classification）
# 正确：正例（修复后预期工件）→ confirmed_priority；负例（修复前工件 / 迭代
# 差异异常 / 注入缺失）→ 对应分类。
#
# 注意：本自测**不是**实验证据（工件是构造的），只锁定脚本判定逻辑；
# 真实结论以 Lead 在干净切点 worktree 的实跑 ANALYSIS.json 为准。
# 零 LLM、零网络。用法：bash <此文件>（在任意目录执行均可）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
PY="${REPO}/.venv/bin/python"
REVAL="${REPO}/experiments/run_t4_a19_revalidation.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/t4_selftest.XXXXXX")"
trap 'rm -rf "${TMP}"' EXIT

# 抽取内嵌判定逻辑（<<'PYEOF' 与行首 PYEOF 之间）为独立脚本
awk '/<<.PYEOF.$/{flag=1; next} /^PYEOF$/{flag=0} flag' "${REVAL}" > "${TMP}/judge.py"
[ -s "${TMP}/judge.py" ] || { echo "✗ 未能从复验脚本抽取判定逻辑" >&2; exit 1; }

make_batch() {
    # $1=arm $2=stop_reason $3=iterations $4=任务数
    local arm="$1" stop="$2" iters="$3" n="$4" dir="${TMP}/$5/arm_${1}"
    mkdir -p "${dir}"
    "${PY}" - "${dir}" "${stop}" "${iters}" "${n}" <<'PY'
import json
import sys
from pathlib import Path

dir_p, stop, iters, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
details = [
    {"task_id": f"synthetic__task_{i:04d}", "stop_reason": stop, "iterations": iters, "error_category": ""}
    for i in range(n)
]
payload = {"results": {"aitester": {"details": details}}}
(dir_p / "benchmark_synthetic_20261018_120000.json").write_text(json.dumps(payload), encoding="utf-8")
PY
}

make_records() {
    # $1=arm $2=任务数 $3=out root
    local arm="$1" n="$2" out="$3"
    : > "${out}/arm_${arm}/injection_records_${arm}.jsonl"
    "${PY}" - "${out}" "${arm}" "${n}" <<'PY'
import json
import sys
from pathlib import Path

out, arm, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
lines = [
    {"task_id": f"synthetic__task_{i:04d}", "iteration": it, "injected": True, "passed": False}
    for i in range(n)
    for it in range(3)
]
(out / f"arm_{arm}" / f"injection_records_{arm}.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in lines) + "\n", encoding="utf-8"
)
PY
}

make_log() {
    # $1=路径 $2=preempt 次数 $3=stall 次数 $4=repair 次数
    local path="$1" pre="$2" stall="$3" repair="$4" i
    : > "${path}"
    for ((i = 0; i < stall; i++)); do
        echo "2026-10-18 12:00:00,000 INFO src.graph.workflow: P2-4 覆盖率停滞（连续 2 轮 |delta|<eps 且测试未通过）：跳过 Debugger 提前结束" >> "${path}"
    done
    for ((i = 0; i < pre; i++)); do
        echo "2026-10-18 12:00:00,000 INFO src.graph.workflow: P2-4 覆盖率停滞（同迭代优先于 repair-invalid，连续 2 轮 |delta|<eps 且测试未通过）：跳过 Debugger 提前结束" >> "${path}"
    done
    for ((i = 0; i < repair; i++)); do
        echo "2026-10-18 12:00:00,000 INFO src.graph.workflow: 连续多次修复无效，跳过 Debugger" >> "${path}"
    done
}

run_judge() {
    # $1=fixture 根；返回 classification 字符串（读 ANALYSIS.json）
    "${PY}" "${TMP}/judge.py" "$1" > "${1}/judge.stdout" 2>&1
    "${PY}" - "$1" <<'PY'
import json
import sys
from pathlib import Path

analysis = json.loads((Path(sys.argv[1]) / "ANALYSIS.json").read_text(encoding="utf-8"))
print(analysis["classification"], file=sys.stdout)
PY
}

assert_class() {
    # $1=fixture 名 $2=实际 $3=期望
    if [ "$2" = "$3" ]; then
        echo "  ✓ $1：classification=$2（期望 $3）"
    else
        echo "  ✗ $1：classification=$2（期望 $3）" >&2
        echo "    ---- judge stdout ----" >&2
        cat "${TMP}/$1/judge.stdout" >&2 || true
        exit 1
    fi
}

N=2

# ── 正例：修复后默认协议预期工件（ON 停滞优先 2 次 / OFF repair-invalid 2 次）──
F="${TMP}/case_confirmed"
mkdir -p "${F}/arm_on" "${F}/arm_off"
make_batch on coverage_stall 2 "${N}" case_confirmed
make_batch off skip_debugger_repair_invalid 2 "${N}" case_confirmed
make_records on "${N}" "${F}"
make_records off "${N}" "${F}"
make_log "${F}/log_arm_on.log" 2 0 0
make_log "${F}/log_arm_off.log" 0 0 2
printf 'ARGS=--tasks %d --seed 42\n' "${N}" > "${F}/RUN_SUMMARY.log"
assert_class case_confirmed "$(run_judge "${F}")" "confirmed_priority"

# ── 负例 1：修复前工件（ON 臂 repair-invalid 分支拥有终止；标签仍是 coverage_stall）──
F="${TMP}/case_prefix_repair_invalid"
mkdir -p "${F}/arm_on" "${F}/arm_off"
make_batch on coverage_stall 2 "${N}" case_prefix_repair_invalid
make_batch off skip_debugger_repair_invalid 2 "${N}" case_prefix_repair_invalid
make_records on "${N}" "${F}"
make_records off "${N}" "${F}"
make_log "${F}/log_arm_on.log" 0 0 2
make_log "${F}/log_arm_off.log" 0 0 2
printf 'ARGS=--tasks %d --seed 42\n' "${N}" > "${F}/RUN_SUMMARY.log"
assert_class case_prefix_repair_invalid "$(run_judge "${F}")" "not_confirmed"

# ── 负例 2：ON 臂多省一轮 ⇒ P3 预注册失败 → unexpected_delta（不得当收益）──
F="${TMP}/case_delta"
mkdir -p "${F}/arm_on" "${F}/arm_off"
make_batch on coverage_stall 1 "${N}" case_delta
make_batch off skip_debugger_repair_invalid 2 "${N}" case_delta
make_records on "${N}" "${F}"
make_records off "${N}" "${F}"
make_log "${F}/log_arm_on.log" 2 0 0
make_log "${F}/log_arm_off.log" 0 0 2
printf 'ARGS=--tasks %d --seed 42\n' "${N}" > "${F}/RUN_SUMMARY.log"
assert_class case_delta "$(run_judge "${F}")" "unexpected_delta"

# ── 负例 3：注入未生效（records 空）⇒ P4 失败 → not_confirmed（harness_limitation）──
F="${TMP}/case_no_injection"
mkdir -p "${F}/arm_on" "${F}/arm_off"
make_batch on coverage_stall 2 "${N}" case_no_injection
make_batch off skip_debugger_repair_invalid 2 "${N}" case_no_injection
: > "${F}/arm_on/injection_records_on.jsonl"
: > "${F}/arm_off/injection_records_off.jsonl"
make_log "${F}/log_arm_on.log" 2 0 0
make_log "${F}/log_arm_off.log" 0 0 2
printf 'ARGS=--tasks %d --seed 42\n' "${N}" > "${F}/RUN_SUMMARY.log"
assert_class case_no_injection "$(run_judge "${F}")" "not_confirmed"

echo "✓ 复验脚本判定逻辑自测全部通过（4/4 构造夹具，零 LLM）"
