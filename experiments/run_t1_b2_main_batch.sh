#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# T1（B2）：主批次锁指纹复现批（3 seed × 3 臂，synthetic 87 任务，真实 LLM）
#
# 性质：复现性测量（见 OUT/PREREG.md，跑前冻结）。回答"R-P0-2 头条三种子结论在
# 干净树 + model_fingerprint.pinned=true 的现代 harness 上是否方向性复现"。
#
# 用法：
#   bash experiments/run_t1_b2_main_batch.sh \
#     --root /Users/wangchenyu/Workspace/AITester-t-b2-a93c1f6 \
#     --expect-sha a93c1f60ee31b9582e0146f73e3038e6ce0f01a1 \
#     [--out <结果目录>] [--dry-run] [--preflight-only] [--allow-over-budget]
#
# 失败策略（预注册冻结）：单 seed 失败/超时如实记录、不重跑；跑完剩余 seed。
# 真实模式强制：ROOT HEAD=切点、dirty=0、PREREG 已冻结且含切点 sha、TOCTOU 源码哈希。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT=""
OUT="${SCRIPT_REPO}/experiments/results/t_round_b2_main_batch_20261018"
EXPECT_SHA=""
SEEDS="42 43 44"
PARALLELISM=4
WATCHDOG_SECONDS=7200
WALL_LIMIT_MIN=240
BUDGET_USD=6.0
DRY_RUN=0
PREFLIGHT_ONLY=0
ALLOW_OVER_BUDGET=0
# R-P0-2 三批实测总 token（价目表上界估算的参考量；只用于跑前成本闸）
REF_TOKENS=8755871

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --root) [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }; ROOT="$2"; shift 2 ;;
        --out) [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --expect-sha) [ $# -ge 2 ] || { echo "--expect-sha 需要完整 sha" >&2; exit 2; }; EXPECT_SHA="$2"; shift 2 ;;
        --seeds) [ $# -ge 2 ] || { echo "--seeds 需要空格分隔 seed 列表" >&2; exit 2; }; SEEDS="$2"; shift 2 ;;
        --parallelism) [ $# -ge 2 ] || { echo "--parallelism 需要正整数" >&2; exit 2; }; PARALLELISM="$2"; shift 2 ;;
        --watchdog-seconds) [ $# -ge 2 ] || { echo "--watchdog-seconds 需要正整数" >&2; exit 2; }; WATCHDOG_SECONDS="$2"; shift 2 ;;
        --budget-usd) [ $# -ge 2 ] || { echo "--budget-usd 需要数值" >&2; exit 2; }; BUDGET_USD="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift ;;
        --allow-over-budget) ALLOW_OVER_BUDGET=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

for _v in PARALLELISM WATCHDOG_SECONDS; do
    case "${!_v:-}" in '' | *[!0-9]*) echo "--${_v} 必须正整数" >&2; exit 2 ;; esac
done

[ -n "${ROOT}" ] || { echo "✗ 必须给 --root（干净 worktree）" >&2; exit 2; }
[ -d "${ROOT}" ] || { echo "✗ ROOT 不存在：${ROOT}" >&2; exit 2; }
[ -n "${EXPECT_SHA}" ] || { echo "✗ 必须给 --expect-sha（切点校验）" >&2; exit 2; }
ROOT="$(cd "${ROOT}" && pwd)"
OUT="$(cd "${SCRIPT_REPO}" && mkdir -p "${OUT}" && cd "${OUT}" && pwd)"
PREREG_MD="${OUT}/PREREG.md"
[ -f "${ROOT}/experiments/run_main_batch.py" ] || { echo "✗ ROOT 不像 aitester 仓库：${ROOT}" >&2; exit 2; }
[ -f "${ROOT}/.env.local" ] || { echo "✗ ROOT/.env.local 缺失（真实 LLM 需要）" >&2; exit 2; }
[ -f "${PREREG_MD}" ] || { echo "✗ 预注册缺失：${PREREG_MD}（跑前必须落盘）" >&2; exit 2; }

if [ -x "${SCRIPT_REPO}/.venv/bin/python" ]; then PY="${SCRIPT_REPO}/.venv/bin/python"
elif [ -x "${ROOT}/.venv/bin/python" ]; then PY="${ROOT}/.venv/bin/python"
else echo "✗ 找不到 python 解释器" >&2; exit 2; fi
PRICE="${ROOT}/experiments/price_table.json"
[ -f "${PRICE}" ] || { echo "✗ 价目表缺失：${PRICE}" >&2; exit 2; }

# 导出 LLM 凭证到子进程环境：preflight 的配额探测按 os.environ 读取（不自行加载 .env*）；
# 批次本体由 config.load_env_local() 自行加载 worktree 内 .env.local。只导出 LLM_1_*，不打印值。
if [ -f "${ROOT}/.env.local" ]; then
    while IFS='=' read -r _k _v; do
        case "${_k}" in
            LLM_1_API_KEY | LLM_1_BASE_URL | LLM_1_MODEL_NAME | DEEPSEEK_API_KEY) export "${_k}=${_v}" ;;
        esac
    done < <(grep -E '^(LLM_1_(API_KEY|BASE_URL|MODEL_NAME)|DEEPSEEK_API_KEY)=' "${ROOT}/.env.local" 2>/dev/null || true)
fi

ROOT_HEAD="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || true)"
ROOT_DIRTY_BEFORE="$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ "${ROOT_HEAD}" = "${EXPECT_SHA}" ] || { echo "✗ 切点不符：ROOT HEAD=${ROOT_HEAD} ≠ expect=${EXPECT_SHA}" >&2; exit 2; }

if [ "${DRY_RUN}" -eq 0 ]; then
    if [ "${ROOT_DIRTY_BEFORE}" != "0" ]; then
        echo "✗ 真实跑批要求干净树：ROOT dirty=${ROOT_DIRTY_BEFORE} 行" >&2; exit 2
    fi
    if grep -qE "状态：DRAFT|<切点 sha|<Lead 提供>" "${PREREG_MD}"; then
        echo "✗ PREREG 尚未冻结（含 DRAFT/占位符）" >&2; exit 2
    fi
    if ! grep -q "${EXPECT_SHA}" "${PREREG_MD}"; then
        echo "✗ PREREG 未记录切点 sha（${EXPECT_SHA}）" >&2; exit 2
    fi
fi

mkdir -p "${OUT}/_helpers" "${OUT}/_preflight"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PREREG_SHA="$(shasum -a 256 "${PREREG_MD}" | awk '{print $1}')"
SUMMARY_LOG="${OUT}/RUN_SUMMARY.log"
if [ "${DRY_RUN}" -eq 1 ]; then
    PREFLIGHT_JSON="${OUT}/PREFLIGHT_dryrun.json"
else
    PREFLIGHT_JSON="${OUT}/PREFLIGHT.json"
    if [ -e "${OUT}/RUN_SUMMARY.log" ]; then
        echo "✗ 结果目录已有跑批工件（拒绝覆盖）：${OUT}" >&2; exit 2
    fi
fi

# ─── 看门狗（超时 SIGTERM→SIGKILL 进程组，不静默挂死）────────────────────────
cat > "${OUT}/_helpers/limited_run.py" <<'PY'
"""有限墙钟看门狗：超时 SIGTERM→SIGKILL 进程组，不静默挂死。"""
import os, signal, subprocess, sys, time
limit = float(sys.argv[1]); cmd = sys.argv[2:]
t0 = time.time()
proc = subprocess.Popen(cmd, start_new_session=True)
try:
    rc = proc.wait(timeout=limit)
except subprocess.TimeoutExpired:
    print(f"\n[watchdog] 超过墙钟上限 {limit:.0f}s：SIGTERM 进程组…", file=sys.stderr, flush=True)
    try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError: pass
    try: rc = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        print("[watchdog] SIGTERM 未退，SIGKILL 进程组…", file=sys.stderr, flush=True)
        try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError: pass
        rc = proc.wait(timeout=30)
    print(f"[watchdog] 超时终止 rc={rc} wall={time.time()-t0:.1f}s", file=sys.stderr, flush=True)
    sys.exit(124)
print(f"[watchdog] rc={rc} wall={time.time()-t0:.1f}s", file=sys.stderr, flush=True)
sys.exit(rc)
PY

# ─── TOCTOU 源码哈希（preflight → launch → 每 seed 前复核）───────────────────
SOURCE_HASHES_JSON="$("${PY}" - "${ROOT}" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
rels = [
    "config.py",
    "experiments/run_benchmark.py",
    "experiments/run_main_batch.py",
    "experiments/statistical_analysis.py",
    "src/datasets/synthetic_dataset.py",
    "src/graph/nodes.py",
    "src/graph/workflow.py",
    "src/budget/cost_budget.py",
    "src/utils/env_utils.py",
]
out = {}
for rel in rels:
    p = root / rel
    out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
print(json.dumps(out, ensure_ascii=False))
PY
)"

toctou_check() {
    "${PY}" - "${ROOT}" "${SOURCE_HASHES_JSON}" <<'PY'
import hashlib, json, sys
from pathlib import Path
root, recorded = Path(sys.argv[1]), json.loads(sys.argv[2])
issues = []
for rel, digest in recorded.items():
    p = root / rel
    cur = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    if cur != digest:
        issues.append(f"changed/missing: {rel}")
if issues:
    print("TOCTOU_GUARD_FAIL: " + "; ".join(issues)); raise SystemExit(1)
print("TOCTOU_GUARD_OK")
PY
}

# ─── 成本估算（价目表上界；只做跑前闸）──────────────────────────────────────
COST_EST_JSON="$("${PY}" - "${PRICE}" "${REF_TOKENS}" <<'PY'
import json, sys
from pathlib import Path
price = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ref_tokens = float(sys.argv[2])
m = (price.get("models") or {}).get("deepseek-flash") or {}
p_in, p_out = m.get("input_per_mtok"), m.get("output_per_mtok")
in_share = 0.76  # 与 S-1/R-1 同口径（历史批次 in/out 观测比例）
if isinstance(p_in, (int, float)) and isinstance(p_out, (int, float)):
    cost = ref_tokens * (in_share * p_in + (1 - in_share) * p_out) / 1e6
    print(json.dumps({"est_usd": round(cost, 4), "input_share": in_share,
                      "price": {"input_per_mtok": p_in, "output_per_mtok": p_out, "as_of": m.get("as_of")}}))
else:
    print(json.dumps({"est_usd": None, "error": "price_missing"}))
PY
)"
EST_USD="$("${PY}" -c 'import json,sys; print(json.loads(sys.argv[1]).get("est_usd") or 0)' "${COST_EST_JSON}")"

echo "[1/6] 预检：ROOT=${ROOT}"
echo "      HEAD=${ROOT_HEAD} dirty=${ROOT_DIRTY_BEFORE} PREREG_SHA=${PREREG_SHA}"
echo "      成本估算（上界）：\$${EST_USD} / 预算 \$${BUDGET_USD}；参考 tokens=${REF_TOKENS}"
if [ "${DRY_RUN}" -eq 0 ]; then
    if [ "${ALLOW_OVER_BUDGET}" -eq 0 ] && "${PY}" -c 'import sys; sys.exit(0 if float(sys.argv[1]) <= float(sys.argv[2]) else 1)' "${EST_USD}" "${BUDGET_USD}"; then
        :
    else
        echo "✗ 成本估算超预算（$\$${EST_USD} > $\$${BUDGET_USD}）——中止（--allow-over-budget 可显式豁免）" >&2; exit 2
    fi
fi

# ─── 前置闸（零网络，strict）+ 独立最小配额探测 ─────────────────────────────
# 注：`scripts/tools/run_preflight.py --check-quota` 当前实现 import 不存在的
# `src.agents.llm_client.LLMClient`（T 轮登记的探针缺陷，已另行修复），故本 runner
# 的连通性探测改为独立的 1 次最小 chat 调用，结果记入 PREFLIGHT.json。
PREFLIGHT_RUN_LOG="${OUT}/_preflight/preflight_run.log"
PREFLIGHT_RC=0
(
    cd "${ROOT}"
    env AITESTER_PROFILE=logic \
        COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 \
        AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true \
        "${PY}" scripts/tools/run_preflight.py --expect-tasks 261 --strict
) > "${PREFLIGHT_RUN_LOG}" 2>&1 || PREFLIGHT_RC=$?
echo "[2/6] 前置闸 rc=${PREFLIGHT_RC}（日志：${PREFLIGHT_RUN_LOG}）"

QUOTA_PROBE_JSON="${OUT}/_preflight/quota_probe.json"
QUOTA_PROBE_RC=0
"${PY}" - "${QUOTA_PROBE_JSON}" <<'PY' || QUOTA_PROBE_RC=$?
import json, os, sys, time
from pathlib import Path
out = Path(sys.argv[1])
base = (os.environ.get("LLM_1_BASE_URL") or "").rstrip("/")
key = os.environ.get("LLM_1_API_KEY") or ""
model = os.environ.get("LLM_1_MODEL_NAME") or "deepseek-flash"
payload = {"ok": False, "probe": "minimal_chat_completion", "model": model,
           "base_url_host": base.split("//")[-1].split("/")[0] if base else None,
           "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
if not base or not key:
    payload["reason"] = "LLM_1_BASE_URL / LLM_1_API_KEY 未设置"
else:
    try:
        import requests
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "Reply with the single token: OK"}],
                  "max_tokens": 8, "temperature": 0},
            timeout=60,
        )
        payload.update({"http_status": r.status_code, "ok": r.status_code == 200})
        if r.status_code == 200:
            data = r.json()
            payload["usage"] = data.get("usage")
            payload["response_model"] = data.get("model")
        else:
            payload["reason"] = (r.text or "")[:200]
    except Exception as exc:
        payload["reason"] = f"{type(exc).__name__}: {exc}"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
raise SystemExit(0 if payload["ok"] else 1)
PY
echo "[2/6] 配额探测 rc=${QUOTA_PROBE_RC}（结果：${QUOTA_PROBE_JSON}；独立缺陷替代实现，见 runner 注释）"

"${PY}" - "${OUT}" "${PREFLIGHT_JSON}" "${ROOT}" "${ROOT_HEAD}" "${ROOT_DIRTY_BEFORE}" \
    "${PREREG_SHA}" "${PREREG_MD}" "${SOURCE_HASHES_JSON}" "${COST_EST_JSON}" \
    "${BUDGET_USD}" "${REF_TOKENS}" "${PREFLIGHT_RC}" "${QUOTA_PROBE_RC}" "${QUOTA_PROBE_JSON}" \
    "${SEEDS}" "${PARALLELISM}" "${WATCHDOG_SECONDS}" "${RUN_STAMP}" "${DRY_RUN}" <<'PY'
import json, sys
from pathlib import Path
(out, pre_path, root, head, dirty, prereg_sha, prereg_md, src_hashes, cost_json,
 budget, ref_tokens, pre_rc, quota_rc, quota_path, seeds, parallelism, watchdog,
 stamp, dry_run) = sys.argv[1:20]
payload = {
    "schema": "aitester_t1_b2_preflight/1",
    "generated_at_utc": stamp,
    "dry_run": bool(int(dry_run)),
    "root": root,
    "root_head": head,
    "root_dirty_lines": int(dirty),
    "prereg_path": prereg_md,
    "prereg_sha256": prereg_sha,
    "seeds": [int(s) for s in seeds.split()],
    "parallelism": int(parallelism),
    "watchdog_seconds": int(watchdog),
    "budget_usd": float(budget),
    "reference_total_tokens": int(ref_tokens),
    "cost_estimate": json.loads(cost_json),
    "preflight_rc": int(pre_rc),
    "preflight_log": str(Path(out) / "_preflight" / "preflight_run.log"),
    "quota_probe_rc": int(quota_rc),
    "quota_probe": json.loads(Path(quota_path).read_text(encoding="utf-8")) if Path(quota_path).exists() else None,
    "quota_probe_note": "run_preflight.py --check-quota 的 LLMClient 引用缺陷（T 轮登记）；本 runner 以独立 1 次最小 chat 调用替代",
    "source_hashes": json.loads(src_hashes),
    "protocol": {
        "dataset": "synthetic", "task_count": 87, "max_pattern_repeat": 2,
        "baselines": ["aitester", "plain_llm", "plain_llm_df"],
        "cli": "python -m experiments.run_main_batch --dataset synthetic --task-count 87 "
               "--max-pattern-repeat 2 --seed <seed> --baselines aitester,plain_llm,plain_llm_df "
               "--skip-stats --output-dir <ROOT>/experiments/results/main_batch --staging-dir <OUT>/_staging_seed<seed>",
    },
    "env": {
        "AITESTER_PROFILE": "logic", "TEMPERATURE": "0.0", "LLM_THINKING_MODE": "disabled",
        "MAX_ITERATIONS": "3", "LLM_TIMEOUT": "60", "EXECUTION_TIMEOUT": "30",
        "ENABLE_PLANNER": "true", "ENABLE_DEBUGGER": "true", "ENABLE_RAG": "false",
        "BENCHMARK_PARALLELISM": str(parallelism), "AITESTER_LLM_CACHE": "0",
        "AITESTER_CACHE_NAMESPACE": "t_b2_main_<seed>", "AITESTER_TRACE_DIR": "<OUT>/traces_seed<seed>",
        "COST_BUDGET_ENABLE": "true", "COST_BUDGET_TOKENS": "200000", "COST_BUDGET_USD": "1.0",
        "AITESTER_BATCH_MAX_CALLS": "6000", "AITESTER_BATCH_MAX_USD": "6.0",
        "AITESTER_RUN_PREFLIGHT": "true",
    },
}
Path(pre_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PREFLIGHT.json 写入：{pre_path}")
PY

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[dry-run] 预检与冻结校验通过；不启动真实 LLM。"
    exit 0
fi
if [ "${PREFLIGHT_RC}" -ne 0 ]; then
    echo "✗ 前置闸未通过（rc=${PREFLIGHT_RC}）——真实跑批中止（strict 语义）" >&2
    exit 2
fi
if [ "${QUOTA_PROBE_RC}" -ne 0 ]; then
    echo "✗ 配额/连通性探测未通过（rc=${QUOTA_PROBE_RC}，见 ${QUOTA_PROBE_JSON}）——中止" >&2
    exit 2
fi
if [ "${PREFLIGHT_ONLY}" -eq 1 ]; then
    echo "[preflight-only] 前置闸 + 配额探测通过；不启动真实 LLM。"
    exit 0
fi

toctou_check

# ─── 逐 seed 顺序跑批（固定 42→43→44，不按结果择序）────────────────────────
echo "[3/6] 顺序跑批 seeds=${SEEDS}（每 seed watchdog=${WATCHDOG_SECONDS}s）"
: > "${SUMMARY_LOG}"
GATE_FILES=""
for SEED in ${SEEDS}; do
    SEED_STAGING="${OUT}/_staging_seed${SEED}"
    SEED_TRACE="${OUT}/traces_seed${SEED}"
    SEED_LOG="${OUT}/_preflight/log_seed${SEED}.log"
    mkdir -p "${SEED_STAGING}" "${SEED_TRACE}"
    SEED_START_EPOCH="$(date +%s)"; SEED_START_ISO="$(date -u +%FT%TZ)"
    NS="t_b2_main_${SEED}"
    {
        echo "===== T1/B2 main-batch replication seed=${SEED} ====="
        echo "START_ISO_UTC=${SEED_START_ISO}"
        echo "ROOT=${ROOT} HEAD=${ROOT_HEAD}"
        echo "CMD=${PY} -m experiments.run_main_batch --dataset synthetic --task-count 87 --max-pattern-repeat 2 --seed ${SEED} --baselines aitester,plain_llm,plain_llm_df --skip-stats --output-dir ${ROOT}/experiments/results/main_batch --staging-dir ${SEED_STAGING}"
        echo "ENV=AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled MAX_ITERATIONS=3 LLM_TIMEOUT=60 EXECUTION_TIMEOUT=30 ENABLE_PLANNER=true ENABLE_DEBUGGER=true ENABLE_RAG=false BENCHMARK_PARALLELISM=${PARALLELISM} AITESTER_LLM_CACHE=0 AITESTER_CACHE_NAMESPACE=${NS} AITESTER_TRACE_DIR=${SEED_TRACE} COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true"
    } > "${SEED_LOG}"
    toctou_check >> "${SEED_LOG}" 2>&1 || { echo "✗ TOCTOU 守卫失败（跑批期间源码变化）——中止" >&2; exit 3; }
    set +e
    (
        cd "${ROOT}" && env \
            AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled \
            MAX_ITERATIONS=3 LLM_TIMEOUT=60 EXECUTION_TIMEOUT=30 \
            ENABLE_PLANNER=true ENABLE_DEBUGGER=true ENABLE_RAG=false \
            "BENCHMARK_PARALLELISM=${PARALLELISM}" AITESTER_LLM_CACHE=0 \
            "AITESTER_CACHE_NAMESPACE=${NS}" "AITESTER_TRACE_DIR=${SEED_TRACE}" \
            COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 \
            AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true \
            "${PY}" "${OUT}/_helpers/limited_run.py" "${WATCHDOG_SECONDS}" \
            "${PY}" -m experiments.run_main_batch --dataset synthetic --task-count 87 \
            --max-pattern-repeat 2 --seed "${SEED}" \
            --baselines aitester,plain_llm,plain_llm_df --skip-stats \
            --output-dir "${ROOT}/experiments/results/main_batch" \
            --staging-dir "${SEED_STAGING}"
    ) >> "${SEED_LOG}" 2>&1
    SEED_RC=$?
    set -e
    SEED_END_EPOCH="$(date +%s)"; SEED_END_ISO="$(date -u +%FT%TZ)"; SEED_WALL=$((SEED_END_EPOCH - SEED_START_EPOCH))
    echo "END_ISO_UTC=${SEED_END_ISO} END_EPOCH=${SEED_END_EPOCH} EXIT_CODE=${SEED_RC} WALL_SECONDS=${SEED_WALL}" >> "${SEED_LOG}"

    # 把 staging 内本 seed 新增工件移入最终目录
    mkdir -p "${OUT}/seed${SEED}"
    if [ -d "${SEED_STAGING}" ]; then
        (shopt -s nullglob; for f in "${SEED_STAGING}"/*; do mv "${f}" "${OUT}/seed${SEED}/"; done)
    fi

    # §1.1 门槛校验（结构/provenance/行数/task_id 集合）
    GATE_JSON="${OUT}/seed${SEED}_GATE.json"
    "${PY}" - "${SEED}" "${SEED_RC}" "${SEED_WALL}" "${OUT}/seed${SEED}" \
        "${SEED_START_ISO}" "${SEED_END_ISO}" "${SEED_LOG}" "${GATE_JSON}" \
        "${SCRIPT_REPO}/experiments/results/main_batch" <<'PY' || true
import glob, json, sys
from pathlib import Path
seed, rc, wall, seed_dir, start_iso, end_iso, log_path, gate_out, orig_dir = sys.argv[1:10]
seed = int(seed); rc = int(rc); wall = int(wall)
batches = sorted(glob.glob(str(Path(seed_dir) / "benchmark_*.json")), key=lambda p: Path(p).stat().st_mtime)
issues, facts = [], {}
batch = None
if not batches:
    issues.append("no_batch_json")
else:
    batch = json.loads(Path(batches[-1]).read_text(encoding="utf-8"))
    prov = batch.get("provenance") or {}
    fp = prov.get("model_fingerprint") or {}
    facts.update({
        "batch": batches[-1],
        "git_sha": prov.get("git_sha"), "git_dirty": prov.get("git_dirty"),
        "fingerprint_pinned": fp.get("pinned"),
        "fingerprint": fp,
        "profile": prov.get("profile"),
        "cache_namespace": prov.get("cache_namespace"),
        "seed": batch.get("seed"),
    })
    if prov.get("git_dirty") is not False:
        issues.append(f"git_dirty={prov.get('git_dirty')} (须 false)")
    if fp.get("pinned") is not True:
        issues.append(f"fingerprint_pinned={fp.get('pinned')} (须 true)")
    row_counts = {arm: len((res or {}).get("details") or []) for arm, res in (batch.get("results") or {}).items()}
    facts["row_counts"] = row_counts
    for arm, n in row_counts.items():
        if n != 87:
            issues.append(f"rows[{arm}]={n} (须 87)")
    arm_ids = {arm: sorted(r.get("task_id") for r in (res.get("details") or []))
               for arm, res in (batch.get("results") or {}).items()}
    if orig_dir and Path(orig_dir).is_dir():
        # 原批次按 seed 定位（文件名含时间戳；取该 seed 的最小 mtime 批次）
        cands = []
        for p in Path(orig_dir).glob("benchmark_synthetic_*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("seed") == seed and d.get("total_tasks") == 87:
                cands.append((p.stat().st_mtime, p, d))
        if cands:
            cands.sort()
            ref = cands[0][2]
            ref_ids = sorted(r.get("task_id") for r in (ref["results"].get("aitester") or {}).get("details") or [])
            for arm, ids in arm_ids.items():
                if ids != ref_ids:
                    issues.append(f"task_ids_mismatch[{arm}] vs {cands[0][1].name}")
            facts["original_batch"] = str(cands[0][1])
        else:
            facts["original_batch"] = None
    # 主指标逐臂计数（M1 detection：行 detection_rate >= 1.0）
    per_arm = {}
    for arm, res in (batch.get("results") or {}).items():
        rows = (res or {}).get("details") or []
        det = [r.get("llm_suite_detection_rate", r.get("detection_rate")) for r in rows]
        det = [v for v in det if isinstance(v, (int, float))]
        per_arm[arm] = {"measurable": len(det), "detected": sum(1 for v in det if float(v) >= 1.0),
                        "rate": round(sum(1 for v in det if float(v) >= 1.0) / len(det), 4) if det else None,
                        "tokens": sum((r.get("token_usage") or {}).get("total_tokens", 0) for r in rows),
                        "calls": sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in rows)}
    facts["per_arm"] = per_arm
if rc != 0:
    issues.append(f"exit_code={rc}")
payload = {
    "schema": "aitester_t1_b2_seed_gate/1", "seed": seed, "exit_code": rc,
    "wall_seconds": wall, "start_iso_utc": start_iso, "end_iso_utc": end_iso,
    "log": log_path, "criteria": "§1.1 硬门槛（git_dirty=false / pinned=true / 每臂 87 行 / task_id 与原批一致 / exit_code=0）",
    "pass": not issues, "issues": issues, "facts": facts,
}
Path(gate_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[seed{seed}] gate {'PASS' if not issues else 'FAIL: ' + '; '.join(issues)}")
PY
    GATE_FILES="${GATE_FILES} ${GATE_JSON}"
    GATE_STATUS="$("${PY}" -c 'import json,sys; print("PASS" if json.load(open(sys.argv[1])).get("pass") else "FAIL")' "${GATE_JSON}")"
    echo "[seed ${SEED}] exit=${SEED_RC} wall=${SEED_WALL}s gate=${GATE_STATUS} 日志=${SEED_LOG}"
    echo "${SEED} ${SEED_START_ISO} ${SEED_END_ISO} ${SEED_RC} ${SEED_WALL} ${GATE_STATUS}" >> "${SUMMARY_LOG}"
done

# ─── 汇总门禁 + 校验和 ──────────────────────────────────────────────────────
"${PY}" - "${OUT}" ${GATE_FILES} <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
gates = [json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:]]
expected = [42, 43, 44]
by_seed = {g["seed"]: g for g in gates}
issues = []
for s in expected:
    if s not in by_seed:
        issues.append(f"seed{s}_missing")
payload = {
    "schema": "aitester_t1_b2_gates/1",
    "criteria": "§1.1 硬门槛（三 seed 全过才可作复现性证据）",
    "seeds_expected": expected,
    "seeds_present": sorted(by_seed),
    "all_pass": not issues and all(g.get("pass") for g in gates),
    "issues": issues + [f"seed{s}" for s, g in by_seed.items() if not g.get("pass")],
    "per_seed": {str(s): {"pass": g.get("pass"), "exit_code": g.get("exit_code"),
                          "wall_seconds": g.get("wall_seconds"), "issues": g.get("issues")}
                 for s, g in by_seed.items()},
}
(out / "GATES.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print("GATES:", "ALL_PASS" if payload["all_pass"] else "FAIL", payload["issues"])
PY

if [ -f "${SCRIPT_REPO}/scripts/gates/checksum_results.py" ]; then
    "${PY}" "${SCRIPT_REPO}/scripts/gates/checksum_results.py" --write --results-dir "${OUT}" >/dev/null 2>&1 || true
    echo "[6/6] SHA256SUMS 已写出（checksum_results.py --write）"
fi

echo "[DONE] T1/B2 跑批结束；工件目录：${OUT}"
echo "       逐 seed 摘要：${SUMMARY_LOG}"
echo "       门禁汇总：${OUT}/GATES.json"
