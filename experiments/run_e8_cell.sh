#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# E8：T 轮漂移归因 2×2 消融——单格 runner（预注册 docs/preregistration.md §E8）
#
# 格 = {legacy@b533cff1, current@a93c1f60} × {thinking on/off}。
# 已知结构性约束（执行披露，见 OUT/PREREG.md）：legacy 切点无
# LLM_THINKING_MODE 开关（git grep b533cff1 零命中），其默认推理模式即 on 格
# 口径；legacy-off 格在 b533cff1 代码下不可取得，本 runner 只负责
# legacy-on / current-on / current-off 三格，legacy-off 的处置在执行记录留痕。
#
# 用法（每格一次调用；真实跑批由外层编排逐格执行）：
#   bash experiments/run_e8_cell.sh \
#     --root <worktree路径> \
#     --expect-sha <完整切点sha> \
#     --thinking <disabled|enabled|legacy-default> \
#     --out experiments/results/e8_2x2_20261028/<cell> \
#     --budget-usd <格预算上界> --ref-tokens <格参考token量> \
#     [--dry-run] [--preflight-only] [--allow-over-budget]
#
# 守卫（与 T 轮同源，预注册冻结）：干净 worktree、PREREG 冻结且含切点 sha、
# TOCTOU 源码哈希、任务级/批次级预算硬闸、独立 1 次最小配额探测、
# 每格 watchdog、GATE 结构校验（provenance/行数 87/task_id 集合）。
# 失败策略（预注册冻结）：单格失败/超时如实记录、不重跑；跑完剩余格。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT=""
OUT=""
EXPECT_SHA=""
THINKING=""
SEEDS="42"
PARALLELISM=4
WATCHDOG_SECONDS=14400
WALL_LIMIT_MIN=240
BUDGET_USD=""
REF_TOKENS=""
DRY_RUN=0
PREFLIGHT_ONLY=0
ALLOW_OVER_BUDGET=0

usage() { sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --root) [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }; ROOT="$2"; shift 2 ;;
        --out) [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --expect-sha) [ $# -ge 2 ] || { echo "--expect-sha 需要完整 sha" >&2; exit 2; }; EXPECT_SHA="$2"; shift 2 ;;
        --thinking) [ $# -ge 2 ] || { echo "--thinking 需要值" >&2; exit 2; }; THINKING="$2"; shift 2 ;;
        --seeds) [ $# -ge 2 ] || { echo "--seeds 需要空格分隔 seed 列表" >&2; exit 2; }; SEEDS="$2"; shift 2 ;;
        --parallelism) [ $# -ge 2 ] || { echo "--parallelism 需要正整数" >&2; exit 2; }; PARALLELISM="$2"; shift 2 ;;
        --watchdog-seconds) [ $# -ge 2 ] || { echo "--watchdog-seconds 需要正整数" >&2; exit 2; }; WATCHDOG_SECONDS="$2"; shift 2 ;;
        --budget-usd) [ $# -ge 2 ] || { echo "--budget-usd 需要数值" >&2; exit 2; }; BUDGET_USD="$2"; shift 2 ;;
        --ref-tokens) [ $# -ge 2 ] || { echo "--ref-tokens 需要整数" >&2; exit 2; }; REF_TOKENS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift ;;
        --allow-over-budget) ALLOW_OVER_BUDGET=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

case "${THINKING}" in
    disabled | enabled | legacy-default) ;;
    '') echo "✗ 必须给 --thinking（disabled|enabled|legacy-default）" >&2; exit 2 ;;
    *) echo "✗ --thinking 非法：${THINKING}" >&2; exit 2 ;;
esac
for _v in PARALLELISM WATCHDOG_SECONDS; do
    case "${!_v:-}" in '' | *[!0-9]*) echo "--${_v} 必须正整数" >&2; exit 2 ;; esac
done
case "${REF_TOKENS:-}" in '' | *[!0-9]*) echo "--ref-tokens 必须正整数" >&2; exit 2 ;; esac
[ -n "${BUDGET_USD}" ] || { echo "✗ 必须给 --budget-usd" >&2; exit 2; }

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
# TGE 修复轮：legacy 切点（b533cff1）无价目表文件（后加入库）——回退主仓登记
# （价目表是登记数据非代码协议，成本估算与跑批代码分离，不影响切点语义）
if [ ! -f "${PRICE}" ]; then
    PRICE="${SCRIPT_REPO}/experiments/price_table.json"
fi
[ -f "${PRICE}" ] || { echo "✗ 价目表缺失（ROOT 与 SCRIPT_REPO 均无）：${PRICE}" >&2; exit 2; }

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

# legacy 切点无 LLM_THINKING_MODE 开关：legacy-default 格必须落在 b533cff1 上
if [ "${THINKING}" = "legacy-default" ]; then
    echo "${EXPECT_SHA}" | grep -q "^b533cff1" || { echo "✗ legacy-default 格的切点必须为 b533cff1（获得 ${EXPECT_SHA}）" >&2; exit 2; }
fi

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
    "src/agents/llm_client.py",
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
    if digest is None:
        continue  # legacy 切点可能缺个别文件（如 cost_budget.py），以 None 登记不判失败
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

# ─── thinking 注入（legacy-default 不注入——b533cff1 无开关，请求形状同历史）──
THINK_ENV=()
THINK_LOGIC="(未注入)"
case "${THINKING}" in
    disabled) THINK_ENV=("LLM_THINKING_MODE=disabled"); THINK_LOGIC="disabled（成本保护口径，请求体 thinking={type: disabled}）" ;;
    enabled)  THINK_ENV=("LLM_THINKING_MODE=enabled");  THINK_LOGIC="enabled（质量敏感口径，请求体 thinking={type: enabled}）" ;;
    legacy-default) THINK_LOGIC="legacy-default（b533cff1 代码无开关、不注入变量，API 默认思考开启=R-P0-2 历史口径）" ;;
esac

echo "[1/6] 预检：ROOT=${ROOT}"
echo "      HEAD=${ROOT_HEAD} dirty=${ROOT_DIRTY_BEFORE} PREREG_SHA=${PREREG_SHA}"
echo "      格=${THINKING}（${THINK_LOGIC}）"
echo "      成本估算（上界）：\$${EST_USD} / 预算 \$${BUDGET_USD}；参考 tokens=${REF_TOKENS}"
if [ "${DRY_RUN}" -eq 0 ]; then
    if [ "${ALLOW_OVER_BUDGET}" -eq 0 ] && "${PY}" -c 'import sys; sys.exit(0 if float(sys.argv[1]) <= float(sys.argv[2]) else 1)' "${EST_USD}" "${BUDGET_USD}"; then
        :
    else
        echo "✗ 成本估算超预算（\$${EST_USD} > \$${BUDGET_USD}）——中止（--allow-over-budget 可显式豁免）" >&2; exit 2
    fi
fi

# ─── 前置闸（零网络，strict）+ 独立最小配额探测 ─────────────────────────────
PREFLIGHT_RUN_LOG="${OUT}/_preflight/preflight_run.log"
PREFLIGHT_RC=0
# legacy 切点（b533cff1）无 scripts/tools/run_preflight.py（后加入库）——
# 回退主仓脚本、cwd 保持 ROOT（git 检查仍对准跑批 worktree）
PREFLIGHT_SCRIPT="${ROOT}/scripts/tools/run_preflight.py"
[ -f "${PREFLIGHT_SCRIPT}" ] || PREFLIGHT_SCRIPT="${SCRIPT_REPO}/scripts/tools/run_preflight.py"
(
    cd "${ROOT}"
    env AITESTER_PROFILE=logic \
        COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 \
        AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true \
        "${PY}" "${PREFLIGHT_SCRIPT}" --expect-tasks 87 --strict
) > "${PREFLIGHT_RUN_LOG}" 2>&1 || PREFLIGHT_RC=$?
echo "[2/6] 前置闸 rc=${PREFLIGHT_RC}（日志：${PREFLIGHT_RUN_LOG}）"

QUOTA_PROBE_JSON="${OUT}/_preflight/quota_probe.json"
QUOTA_PROBE_RC=0
"${PY}" - "${QUOTA_PROBE_JSON}" <<'PY' || QUOTA_PROBE_RC=$?
import json, os, sys, time
from pathlib import Path
out = Path(sys.argv[1])
base = (os.environ.get("LLM_1_BASE_URL") or "").rstrip("/")
env_name = "LLM_1_API" + "_KEY"
key = os.environ.get(env_name) or ""
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
echo "[2/6] 配额探测 rc=${QUOTA_PROBE_RC}（结果：${QUOTA_PROBE_JSON}）"

"${PY}" - "${OUT}" "${PREFLIGHT_JSON}" "${ROOT}" "${ROOT_HEAD}" "${ROOT_DIRTY_BEFORE}" \
    "${PREREG_SHA}" "${PREREG_MD}" "${SOURCE_HASHES_JSON}" "${COST_EST_JSON}" \
    "${BUDGET_USD}" "${REF_TOKENS}" "${PREFLIGHT_RC}" "${QUOTA_PROBE_RC}" "${QUOTA_PROBE_JSON}" \
    "${SEEDS}" "${PARALLELISM}" "${WATCHDOG_SECONDS}" "${RUN_STAMP}" "${DRY_RUN}" \
    "${THINKING}" "${THINK_LOGIC}" <<'PY'
import json, sys
from pathlib import Path
(out, pre_path, root, head, dirty, prereg_sha, prereg_md, src_hashes, cost_json,
 budget, ref_tokens, pre_rc, quota_rc, quota_path, seeds, parallelism, watchdog,
 stamp, dry_run, thinking, think_logic) = sys.argv[1:22]
payload = {
    "schema": "aitester_e8_cell_preflight/1",
    "generated_at_utc": stamp,
    "dry_run": bool(int(dry_run)),
    "root": root,
    "root_head": head,
    "root_dirty_lines": int(dirty),
    "prereg_path": prereg_md,
    "prereg_sha256": prereg_sha,
    "cell_thinking": thinking,
    "cell_thinking_logic": think_logic,
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
    "source_hashes": json.loads(src_hashes),
    "protocol": {
        "dataset": "synthetic", "task_count": 87,
        "baselines": ["aitester", "plain_llm", "plain_llm_df"],
        "cli": "python -m experiments.run_main_batch --dataset synthetic --task-count 87 "
               "--seed 42 --baselines aitester,plain_llm,plain_llm_df --skip-stats "
               "--output-dir <ROOT>/experiments/results/main_batch"
               "（legacy 切点无 --max-pattern-repeat/--staging-dir；current 切点追加两者）",
    },
}
Path(pre_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PREFLIGHT 写入：{pre_path}")
PY

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[dry-run] 预检与冻结校验通过；不启动真实 LLM。"
    exit 0
fi
if [ "${PREFLIGHT_RC}" -ne 0 ]; then
    # legacy 切点回退主仓预检脚本时，dirty 检查按 __file__ 定位主仓树
    # （并发会话改动使主仓 dirty），而跑批树是 ROOT——runner 第 [1/6] 步
    # 已单独强制 ROOT dirty=0。唯一阻断项为 dirty 且 ROOT 实测干净时
    # 披露放行；其余阻断（预算/指纹/探测）仍严格拦截。
    if [ "${ROOT_DIRTY_BEFORE}" = "0" ] \
        && grep -q "工作树不干净" "${PREFLIGHT_RUN_LOG}" \
        && [ "$(grep -c '✗' "${PREFLIGHT_RUN_LOG}")" = "1" ]; then
        echo "前置闸 dirty 阻断系主仓树（预检脚本回退定位），ROOT 实测干净——披露放行"
    else
        echo "✗ 前置闸未通过（rc=${PREFLIGHT_RC}）——真实跑批中止（strict 语义）" >&2
        exit 2
    fi
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

# ─── 逐 seed 顺序跑批（E8 预注册：1 seed 42 起步）───────────────────────────
echo "[3/6] 顺序跑批 seeds=${SEEDS}（每 seed watchdog=${WATCHDOG_SECONDS}s）"
: > "${SUMMARY_LOG}"
GATE_FILES=""
for SEED in ${SEEDS}; do
    SEED_TRACE="${OUT}/traces_seed${SEED}"
    SEED_LOG="${OUT}/_preflight/log_seed${SEED}.log"
    mkdir -p "${SEED_TRACE}"
    SEED_START_EPOCH="$(date +%s)"; SEED_START_ISO="$(date -u +%FT%TZ)"
    NS="e8_${THINKING}_${SEED}"
    # legacy 切点无 --max-pattern-repeat/--staging-dir；current 切点两者都加
    EXTRA_ARGS=""
    if [ "${THINKING}" != "legacy-default" ]; then
        EXTRA_ARGS="--max-pattern-repeat 2 --staging-dir ${OUT}/_staging_seed${SEED}"
        mkdir -p "${OUT}/_staging_seed${SEED}"
    fi
    {
        echo "===== E8 cell=${THINKING} main-batch seed=${SEED} ====="
        echo "START_ISO_UTC=${SEED_START_ISO}"
        echo "ROOT=${ROOT} HEAD=${ROOT_HEAD}"
        echo "CMD=${PY} -m experiments.run_main_batch --dataset synthetic --task-count 87 --seed ${SEED} --baselines aitester,plain_llm,plain_llm_df --skip-stats --output-dir ${ROOT}/experiments/results/main_batch ${EXTRA_ARGS}"
        echo "THINK=${THINK_LOGIC}"
        echo "ENV=AITESTER_PROFILE=logic TEMPERATURE=0.0 ${THINK_ENV[*]+${THINK_ENV[*]}} MAX_ITERATIONS=3 LLM_TIMEOUT=60 EXECUTION_TIMEOUT=30 ENABLE_PLANNER=true ENABLE_DEBUGGER=true ENABLE_RAG=false BENCHMARK_PARALLELISM=${PARALLELISM} AITESTER_LLM_CACHE=0 AITESTER_CACHE_NAMESPACE=${NS} AITESTER_TRACE_DIR=${SEED_TRACE} COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true"
    } > "${SEED_LOG}"
    toctou_check >> "${SEED_LOG}" 2>&1 || { echo "✗ TOCTOU 守卫失败（跑批期间源码变化）——中止" >&2; exit 3; }
    set +e
    (
        cd "${ROOT}" && env \
            AITESTER_PROFILE=logic TEMPERATURE=0.0 \
            ${THINK_ENV[@]+"${THINK_ENV[@]}"} \
            ENABLE_MUTATION_SCORING=false MUTATION_ADVISOR_ENABLE=false \
            MAX_ITERATIONS=3 LLM_TIMEOUT=60 EXECUTION_TIMEOUT=30 \
            ENABLE_PLANNER=true ENABLE_DEBUGGER=true ENABLE_RAG=false \
            "BENCHMARK_PARALLELISM=${PARALLELISM}" AITESTER_LLM_CACHE=0 \
            "AITESTER_CACHE_NAMESPACE=${NS}" "AITESTER_TRACE_DIR=${SEED_TRACE}" \
            COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=200000 COST_BUDGET_USD=1.0 \
            AITESTER_BATCH_MAX_CALLS=6000 AITESTER_BATCH_MAX_USD=6.0 AITESTER_RUN_PREFLIGHT=true \
            "${PY}" "${OUT}/_helpers/limited_run.py" "${WATCHDOG_SECONDS}" \
            "${PY}" -m experiments.run_main_batch --dataset synthetic --task-count 87 \
            --seed "${SEED}" \
            --baselines aitester,plain_llm,plain_llm_df --skip-stats \
            --output-dir "${ROOT}/experiments/results/main_batch" \
            ${EXTRA_ARGS}
    ) >> "${SEED_LOG}" 2>&1
    SEED_RC=$?
    set -e
    SEED_END_EPOCH="$(date +%s)"; SEED_END_ISO="$(date -u +%FT%TZ)"; SEED_WALL=$((SEED_END_EPOCH - SEED_START_EPOCH))
    echo "END_ISO_UTC=${SEED_END_ISO} END_EPOCH=${SEED_END_EPOCH} EXIT_CODE=${SEED_RC} WALL_SECONDS=${SEED_WALL}" >> "${SEED_LOG}"

    # 收集工件：current 格从 staging 搬运；legacy/worktree main_batch 只拷
    # 本次新增（mtime 晚于 PREFLIGHT.json 的批次 JSON——TGE 修复轮实证：
    # worktree 自带历史入库工件，全量 cp + mtime 平局会让 GATE 读错批次）
    mkdir -p "${OUT}/seed${SEED}"
    if [ -d "${OUT}/_staging_seed${SEED}" ]; then
        (shopt -s nullglob; for f in "${OUT}/_staging_seed${SEED}"/*; do mv "${f}" "${OUT}/seed${SEED}/"; done)
    fi
    PREFLIGHT_MTIME=$(stat -f %m "${PREFLIGHT_JSON}")
    (shopt -s nullglob; for f in "${ROOT}/experiments/results/main_batch"/benchmark_*.json; do
        f_mtime=$(stat -f %m "${f}")
        if [ "${f_mtime}" -gt "${PREFLIGHT_MTIME}" ]; then
            cp "${f}" "${OUT}/seed${SEED}/"
        fi
    done)

    # GATE 校验（结构/provenance/行数/task_id 集合）
    GATE_JSON="${OUT}/seed${SEED}_GATE.json"
    "${PY}" - "${SEED}" "${SEED_RC}" "${SEED_WALL}" "${OUT}/seed${SEED}" \
        "${SEED_START_ISO}" "${SEED_END_ISO}" "${SEED_LOG}" "${GATE_JSON}" \
        "${EXPECT_SHA}" <<'PY' || true
import glob, json, sys
from pathlib import Path
seed, rc, wall, seed_dir, start_iso, end_iso, log_path, gate_out, expect_sha = sys.argv[1:10]
seed = int(seed); rc = int(rc); wall = int(wall)
batches = sorted(glob.glob(str(Path(seed_dir) / "benchmark_*.json")), key=lambda p: Path(p).stat().st_mtime)
issues, facts = [], {}
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
    facts["task_id_set_consistent"] = len({tuple(v) for v in arm_ids.values()}) == 1
gate = {
    "schema": "aitester_e8_cell_gate/1", "seed": seed, "exit_code": rc,
    "wall_seconds": wall, "start_iso_utc": start_iso, "end_iso_utc": end_iso,
    "log": log_path, "issues": issues, "facts": facts,
    "hard_gate_pass": (rc == 0 and not issues),
}
Path(gate_out).write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"GATE 写入：{gate_out} pass={gate['hard_gate_pass']} issues={issues}")
PY
    GATE_FILES="${GATE_FILES} ${GATE_JSON}"
done

echo "[4/6] 全部 seed 完成；GATE 文件：${GATE_FILES}"
echo "RUN_COMPLETE_UTC=$(date -u +%FT%TZ)" >> "${SUMMARY_LOG}"
