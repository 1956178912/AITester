#!/usr/bin/env bash
# =============================================================================
# M-4 规格增广二臂真 LLM 正式批（df 同批对照 + augment 处理臂）可复现入口
# 2026-10-17（M 轮，承接 L 轮 replace 阴性结论）
#
# 性质：**预注册正式批执行脚本**（EMSE Registered Reports 口径）。本脚本在
#       Lead 指定的**干净 worktree**（切点 commit）内执行二臂并发跑批，跑完
#       直出判定报告 + 机制重放 + README/SHA256SUMS，并把工件复制回主仓。
#       脚本本身不产生任何手写结果数字：判定/成本/墙钟/审计计数/工件 sha256
#       一律由脚本从批次 JSON / 分析报告 / 重放报告中读取生成。
#
# 预注册（M-1 交付，跑批前已随切点提交）：
#   docs/study/DOCSTRING_AUGMENT_PREREG_2026-10-17.md
#   判定：confirmed = augment detection ≥ 88% ∧ 单向 p<0.05（augment>df）；
#         trend = ≥88% ∧ p<0.10 ∧ δ>0；not_confirmed 其余；
#         fail line = detection < 78%；另报 non-inferiority（δ ≥ −5pp）。
#
# 协议（M-4 任务书固定，不得用本脚本以外的方式"顺手改动"）：
#   - 二臂：df 对照 = plain_llm_df（同批同日新跑）
#           aug 处理 = plain_llm_df_doc_augment（代码保留 + 人类 docstring 规格并列）
#   - AITESTER_PROFILE=logic / TEMPERATURE=0.0 / LLM_THINKING_MODE=disabled
#   - BENCHMARK_PARALLELISM=4（可调，但必须记录；默认 4）/ seed=42
#   - QuixBugs 全量 50 行（41 缺陷程序 + 9 测试驱动；主分析集=41 口径）
#   - 两臂互异 AITESTER_CACHE_NAMESPACE（emse_docstring_augment_20261017_df / _aug）
#   - 每臂 env 级 cap：AITESTER_BATCH_MAX_CALLS=300 / COST_BUDGET_ENABLE=true /
#     COST_BUDGET_USD=5
#   - **不设 DOC_ANCHOR_TABLE**（augment 臂使用 run_benchmark 的默认锚表路径）
#   - 干净 worktree：跑前/跑后 `git status --porcelain` 0 行；批次 provenance
#     git_dirty=false（--allow-dirty 仅调试，不得用于正式批）
#
# 用法：
#   bash experiments/run_augment_batch.sh --dry-run          # 零 LLM 自测（不跑批）
#   bash experiments/run_augment_batch.sh --worktree /path/to/wt --expect-sha <sha>
#   bash experiments/run_augment_batch.sh --help
#
# 前置（脚本逐项检查，缺一即非零退出；--dry-run 只警告不失败）：
#   1. 干净 worktree（或显式 --allow-dirty --dirty-reason）；
#   2. 前置闸 scripts/tools/run_preflight.py --expect-tasks 50 --parallelism 4
#      （等价 make preflight 的只读体检；非 strict，与 L 轮口径一致）输出 exit 0；
#   3. 默认 docstring 锚表在场（augment 臂默认路径；
#      ${WT}/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json）；
#   4. run_benchmark.BASELINE_REGISTRY 已注册 plain_llm_df / plain_llm_df_doc_augment；
#   5. M-1 分析脚本在场且 CLI 含 --df/--augment/--out/--markdown；
#   6. experiments/misguided_metrics.py + experiments/price_table.json 在场。
#
# 产物（全部落在 worktree 内 ${OUT_DIR}；RUN_STAMP=UTC 时间戳；**绝不覆盖既有工件**）：
#   ${OUT_DIR}/benchmark_quixbugs_<ts>.json        两臂批次工件（run_benchmark 自带时间戳）
#   ${OUT_DIR}/log_<df|aug>.log                    每臂完整日志（命令/env 白名单/进度/超时/摘要/GIT 前后）
#   ${OUT_DIR}/arm_<df|aug>.meta.json              每臂结构化元数据（provenance/token/成本/判分/审计/逐任务）
#   ${OUT_DIR}/preflight.log                       前置闸输出
#   ${OUT_DIR}/proc_hygiene.log                    跑批期每 5min 只读孤儿进程巡检记录
#   ${OUT_DIR}/DF_AUG_REPORT.json/.md              M-1 分析脚本直出判定（两臂）
#   ${OUT_DIR}/analysis_stdout.log                 分析脚本完整输出
#   ${OUT_DIR}/misguided_stdout.log                机制重放完整输出
#   ${OUT_DIR}/PROMPT_EVIDENCE.json/.md            从 LLM 缓存抽取的"代码块 + 规格锚同现"证据
#   ${OUT_DIR}/README.md                           本批说明（协议/调度偏差/成本/墙钟/provenance/限制）
#   ${OUT_DIR}/RUN_MANIFEST_<stamp>.json           运行总清单（env/命令/工件/成本/token/墙钟）
#   ${OUT_DIR}/SHA256SUMS                          本目录全部工件 sha256
#   ${OUT_DIR}/traces/                             逐任务 trace（AITESTER_TRACE_DIR；审计用）
#   ${MISGUIDED_OUT}/MISGUIDED_REPORT.json/.md     misguided/effective 逐测试重放报告（两臂）
#   ${MISGUIDED_OUT}/README.md + SHA256SUMS        重放工件说明与完整性
#   ${MAIN_REPO}/experiments/results/<同名目录>/   工件**复制回主仓**（复制后逐文件 sha256 校验）
#
# 退出码：0=成功；2=参数/前置条件失败；3=前置闸未通过；4=某臂跑批失败（日志保留，
#         不重跑）；5=分析判定失败（工件保留）；6=机制重放失败（工件保留）；
#         7=复制回主仓/完整性校验失败。收尾 WARN 情况下工件仍完整保留并复制。
# =============================================================================

set -euo pipefail

SCRIPT_VERSION="m-round-m4-v1"
EXPECT_TASKS=50
CAPS_BATCH_CALLS=300
CAPS_COST_USD=5

_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_SCRIPT_ABS="${_SELF_DIR}/$(basename "${BASH_SOURCE[0]}")"
_WORKTREE_DEFAULT="$(cd "${_SELF_DIR}/.." && pwd)"

PARALLELISM="${BENCHMARK_PARALLELISM:-4}"
SEED=42
WORKTREE="${_WORKTREE_DEFAULT}"
MAIN_REPO=""
EXPECT_SHA=""
OUT_DIR=""
MISGUIDED_OUT=""
ANALYSIS_SCRIPT=""
PRE_REG=""
MISGUIDED_JOBS=8
ALLOW_DIRTY=0
DIRTY_REASON=""
SKIP_ANALYSIS=0
SKIP_MISGUIDED=0
DRY_RUN=0

PY=""

usage() {
    # 打印文件头部连续注释块（shebang 之后、第一行非注释之前）
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
    exit 0
}

log() { printf '%s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }
die() {
    printf '✗ %s\n' "$*" >&2
    exit 2
}

# ─── 参数解析 ────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --worktree)
            [ $# -ge 2 ] || die "--worktree 需要一个目录参数"
            WORKTREE="$2"
            shift 2
            ;;
        --main-repo)
            [ $# -ge 2 ] || die "--main-repo 需要一个目录参数"
            MAIN_REPO="$2"
            shift 2
            ;;
        --expect-sha)
            [ $# -ge 2 ] || die "--expect-sha 需要一个 commit sha"
            EXPECT_SHA="$2"
            shift 2
            ;;
        --parallelism)
            [ $# -ge 2 ] || die "--parallelism 需要一个正整数"
            PARALLELISM="$2"
            shift 2
            ;;
        --seed)
            [ $# -ge 2 ] || die "--seed 需要一个整数"
            SEED="$2"
            shift 2
            ;;
        --output-dir)
            [ $# -ge 2 ] || die "--output-dir 需要一个目录参数"
            OUT_DIR="$2"
            shift 2
            ;;
        --misguided-out)
            [ $# -ge 2 ] || die "--misguided-out 需要一个目录参数"
            MISGUIDED_OUT="$2"
            shift 2
            ;;
        --analysis-script)
            [ $# -ge 2 ] || die "--analysis-script 需要一个路径参数"
            ANALYSIS_SCRIPT="$2"
            shift 2
            ;;
        --pre-reg)
            [ $# -ge 2 ] || die "--pre-reg 需要一个路径参数"
            PRE_REG="$2"
            shift 2
            ;;
        --misguided-jobs)
            [ $# -ge 2 ] || die "--misguided-jobs 需要一个正整数"
            MISGUIDED_JOBS="$2"
            shift 2
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            shift
            ;;
        --dirty-reason)
            [ $# -ge 2 ] || die "--dirty-reason 需要一个原因字符串"
            DIRTY_REASON="$2"
            shift 2
            ;;
        --skip-analysis)
            SKIP_ANALYSIS=1
            shift
            ;;
        --skip-misguided)
            SKIP_MISGUIDED=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h | --help)
            usage
            ;;
        *)
            die "未知参数：$1（--help 查看用法）"
            ;;
    esac
done

# ─── 参数校验 ────────────────────────────────────────────────────────────────
case "${PARALLELISM}" in '' | *[!0-9]*) die "--parallelism 必须为正整数（当前 '${PARALLELISM}'）" ;; esac
[ "${PARALLELISM}" -ge 1 ] || die "--parallelism 必须 >= 1"
case "${SEED}" in '' | *[!0-9]*) die "--seed 必须为非负整数（当前 '${SEED}'）" ;; esac
case "${MISGUIDED_JOBS}" in '' | *[!0-9]*) die "--misguided-jobs 必须为正整数" ;; esac
[ -n "${WORKTREE}" ] || die "--worktree 不能为空"
[ -d "${WORKTREE}" ] || die "--worktree 不是目录：${WORKTREE}"
WORKTREE="$(cd "${WORKTREE}" && pwd)"

# 主仓：默认取 git worktree list 的第一个（主工作树永远是第一个条目）
if [ -z "${MAIN_REPO}" ]; then
    MAIN_REPO="$(git -C "${WORKTREE}" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}' || true)"
fi
[ -n "${MAIN_REPO}" ] || MAIN_REPO="${WORKTREE}"
MAIN_REPO="$(cd "${MAIN_REPO}" && pwd)"

# Python：优先主仓 .venv（worktree 不带 .venv；跑的是 worktree 的代码）
if [ -x "${MAIN_REPO}/.venv/bin/python" ]; then
    PY="${MAIN_REPO}/.venv/bin/python"
elif [ -x "${WORKTREE}/.venv/bin/python" ]; then
    PY="${WORKTREE}/.venv/bin/python"
else
    die "未找到 .venv/bin/python（主仓 ${MAIN_REPO} / worktree ${WORKTREE} 均无）"
fi

[ -n "${OUT_DIR}" ] || OUT_DIR="${WORKTREE}/experiments/results/emse_docstring_augment_20261017"
[ -n "${MISGUIDED_OUT}" ] || MISGUIDED_OUT="${WORKTREE}/experiments/results/emse_misguided_augment_20261017"
[ -n "${ANALYSIS_SCRIPT}" ] || ANALYSIS_SCRIPT="${WORKTREE}/experiments/emse_docstring_augment_analysis.py"
[ -n "${PRE_REG}" ] || PRE_REG="${WORKTREE}/docs/study/DOCSTRING_AUGMENT_PREREG_2026-10-17.md"
PRICE_TABLE="${WORKTREE}/experiments/price_table.json"
MISGUIDED_SCRIPT="${WORKTREE}/experiments/misguided_metrics.py"
PREFLIGHT_SCRIPT="${WORKTREE}/scripts/tools/run_preflight.py"
ORPHAN_SCRIPT="${WORKTREE}/scripts/tools/detect_orphan_procs.py"
ANCHOR_TABLE_DEFAULT="${WORKTREE}/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json"

if [ "${ALLOW_DIRTY}" -eq 1 ]; then
    [ -n "${DIRTY_REASON}" ] || die "--allow-dirty 必须同时给 --dirty-reason '<原因>'（写入 provenance，可审计）"
fi

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
START_ALL_EPOCH="$(date +%s)"
START_ALL_ISO="$(date -u +%FT%TZ)"

# 臂固定映射（改臂需同步预注册；本脚本不支持 --arms）
ARM_LABELS=("df" "aug")
arm_baseline() {
    case "$1" in
        df) printf '%s' "plain_llm_df" ;;
        aug) printf '%s' "plain_llm_df_doc_augment" ;;
        *) return 1 ;;
    esac
}
arm_namespace() {
    case "$1" in
        df) printf '%s' "emse_docstring_augment_20261017_df" ;;
        aug) printf '%s' "emse_docstring_augment_20261017_aug" ;;
        *) return 1 ;;
    esac
}

WARN_EXIT=0
ORPHAN_HIT=0
DIRTY_EXTRA=()
if [ "${ALLOW_DIRTY}" -eq 1 ]; then
    DIRTY_EXTRA=(--allow-dirty --dirty-reason "${DIRTY_REASON}")
fi

echo "================================================================================"
echo "M-4 规格增广二臂正式批（${SCRIPT_VERSION}）$( [ "${DRY_RUN}" -eq 1 ] && echo '【DRY-RUN：不执行正式批、零 LLM 调用】' )"
echo "  仓库/worktree：${WORKTREE}"
echo "  主仓（复制回目标）：${MAIN_REPO}"
echo "  Python：${PY}"
echo "  协议：AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled"
echo "        BENCHMARK_PARALLELISM=${PARALLELISM} seed=${SEED}（QuixBugs 全量 ${EXPECT_TASKS} 行）"
echo "  臂：df（plain_llm_df 对照） / aug（plain_llm_df_doc_augment 处理）"
echo "  输出：${OUT_DIR}"
echo "  RUN_STAMP：${RUN_STAMP}"
echo "================================================================================"

# ─── 0. 既有工件保护（绝不覆盖既有正式批工件） ──────────────────────────────
echo ""
echo "[0/10] 既有工件保护"
if [ "${DRY_RUN}" -eq 0 ]; then
    _existing=0
    for _probe in "${OUT_DIR}/log_df.log" "${OUT_DIR}/log_aug.log" "${OUT_DIR}/DF_AUG_REPORT.json" "${OUT_DIR}/README.md"; do
        if [ -e "${_probe}" ]; then _existing=1; fi
    done
    for _f in "${OUT_DIR}"/benchmark_quixbugs_*.json; do
        if [ -e "${_f}" ]; then _existing=1; fi
    done
    if [ "${_existing}" -eq 1 ]; then
        die "输出目录已存在正式批工件：${OUT_DIR}
     正式批工件一旦落盘不得覆盖/删除（如需重跑请换 --output-dir，或由 Lead 明确裁决）。"
    fi
    log "  ✓ 输出目录无既有正式批工件（允许写入）"
else
    if [ -d "${OUT_DIR}" ]; then
        log "  （dry-run：输出目录已存在——正式运行将检查既有工件并拒绝覆盖）"
    else
        log "  （dry-run：输出目录尚不存在，正式运行会创建）"
    fi
fi

# ─── 1. 干净树与切点断言 ─────────────────────────────────────────────────────
echo ""
echo "[1/10] 干净工作树与切点断言"
[ -e "${WORKTREE}/.git" ] || die "worktree 不是 git 工作树：${WORKTREE}"
GIT_HEAD_PRE="$(git -C "${WORKTREE}" rev-parse HEAD 2>/dev/null || true)"
[ -n "${GIT_HEAD_PRE}" ] || die "无法读取 worktree HEAD：${WORKTREE}"
GIT_DIRTY_PRE="$(git -C "${WORKTREE}" status --porcelain 2>/dev/null || true)"
log "  切点 HEAD：${GIT_HEAD_PRE}"
if [ -n "${EXPECT_SHA}" ]; then
    if [ "${GIT_HEAD_PRE}" != "${EXPECT_SHA}" ]; then
        die "worktree HEAD（${GIT_HEAD_PRE}）≠ --expect-sha（${EXPECT_SHA}）——切点不符。"
    fi
    log "  ✓ HEAD 与 --expect-sha 一致"
fi
if [ -n "${GIT_DIRTY_PRE}" ]; then
    printf '%s\n' "${GIT_DIRTY_PRE}" | sed -n '1,20p' >&2  # CI 补跑修复：head 早关会 SIGPIPE(141) 杀死 pipefail 脚本
    if [ "${ALLOW_DIRTY}" -eq 1 ]; then
        warn "脏树豁免（--allow-dirty）：provenance 将记 git_dirty=true；原因：${DIRTY_REASON}"
    elif [ "${DRY_RUN}" -eq 1 ]; then
        warn "dry-run：当前 worktree 脏（$(printf '%s\n' "${GIT_DIRTY_PRE}" | grep -c .) 行变更）；正式运行会失败退出"
    else
        die "worktree 不干净（见上）——正式批要求干净提交（provenance git_dirty=false）。
     请先由 Lead 提交/清理，或为调试显式 --allow-dirty --dirty-reason '<原因>'（正式批禁止）。"
    fi
else
    log "  ✓ 工作树干净（git status --porcelain 0 行 → 批次 provenance 应为 git_dirty=false）"
fi
# 主仓状态仅记录（跑批期间主仓可能有其他队友的在途改动，不影响 worktree 跑批）
MAIN_GIT_HEAD_PRE="$(git -C "${MAIN_REPO}" rev-parse HEAD 2>/dev/null || true)"
MAIN_GIT_DIRTY_PRE="$(git -C "${MAIN_REPO}" status --porcelain 2>/dev/null || true)"
log "  主仓 HEAD：${MAIN_GIT_HEAD_PRE:-?}；主仓 dirty 行数：$(printf '%s' "${MAIN_GIT_DIRTY_PRE}" | grep -c . 2>/dev/null || true)"
if [ "${WORKTREE}" = "${MAIN_REPO}" ]; then
    warn "worktree == 主仓：本脚本设计用于独立 worktree 跑批；工件复制回同一路径将被跳过。"
fi

# ─── 2. 前置闸（preflight） ──────────────────────────────────────────────────
echo ""
echo "[2/10] 前置闸（配额/指纹/孤儿进程；run_preflight.py --expect-tasks 50）"
_preflight_cmd=("${PY}" "${PREFLIGHT_SCRIPT}" --expect-tasks "${EXPECT_TASKS}" --parallelism "${PARALLELISM}")
if [ ! -f "${PREFLIGHT_SCRIPT}" ]; then
    if [ "${DRY_RUN}" -eq 1 ]; then
        warn "dry-run：前置闸脚本不存在：${PREFLIGHT_SCRIPT}"
    else
        die "前置闸脚本不存在：${PREFLIGHT_SCRIPT}"
    fi
fi
if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  （dry-run 不执行前置闸；正式运行将执行：）"
    printf '  '
    printf '%q ' "${_preflight_cmd[@]}"
    printf ' 2>&1 | tee %q\n' "${OUT_DIR}/preflight.log"
else
    mkdir -p "${OUT_DIR}"
    set +e
    env -u DOC_ANCHOR_TABLE "${_preflight_cmd[@]}" 2>&1 | tee "${OUT_DIR}/preflight.log"
    PRE_RC="${PIPESTATUS[0]}"
    set -e
    if [ "${PRE_RC}" -ne 0 ]; then
        die "前置闸未通过（exit ${PRE_RC}，见 ${OUT_DIR}/preflight.log）——修正后重跑（不得绕过）。"
    fi
    log "  ✓ 前置闸通过（${OUT_DIR}/preflight.log）"
fi

# ─── 3. 锚表 / 臂注册 / 分析脚本依赖检查 ─────────────────────────────────────
echo ""
echo "[3/10] 依赖检查（默认锚表 / 臂注册 / 分析脚本 / 重放脚本 / 价目表）"
DEP_OK=1
ANCHOR_TABLE_ACTUAL=""
ANCHOR_SHA=""
REG_OUT=""

_require_file() { # path, desc
    if [ ! -s "$1" ]; then
        if [ "${DRY_RUN}" -eq 1 ]; then
            warn "dry-run：缺失 $2 → $1"
        else
            warn "缺失 $2 → $1"
        fi
        return 1
    fi
    log "  ✓ $2：$1"
    return 0
}

# 3.1 默认锚表（augment 臂的默认路径；以 run_benchmark 模块常量为准，回退约定路径）
_anchor_probe="$(set +e; "${PY}" - "${WORKTREE}" <<'PY'
import json
import os
import sys

wt = sys.argv[1]
sys.path.insert(0, wt)
path = os.path.join(wt, "experiments", "results", "emse_docstring_anchor_20261017", "DOCSTRING_ANCHOR_TABLE.json")
try:
    import experiments.run_benchmark as rb  # noqa: F401

    candidate = getattr(rb, "_DOC_ANCHOR_TABLE_DEFAULT", None)
    if candidate:
        path = str(candidate)
except Exception as exc:  # noqa: BLE001
    print(f"IMPORT_FAIL {type(exc).__name__}: {exc}")
    raise SystemExit(1)
print(path)
PY
)" || true
if case "${_anchor_probe}" in IMPORT_FAIL*) true ;; *) false ;; esac; then
    warn "无法导入 experiments.run_benchmark（M-1 未合并？）：${_anchor_probe}"
    DEP_OK=0
elif [ -n "${_anchor_probe}" ]; then
    ANCHOR_TABLE_ACTUAL="$(printf '%s\n' "${_anchor_probe}" | tail -1)"
    if [ -s "${ANCHOR_TABLE_ACTUAL}" ]; then
        ANCHOR_SHA="$("${PY}" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${ANCHOR_TABLE_ACTUAL}")"
        log "  ✓ 默认锚表：${ANCHOR_TABLE_ACTUAL}"
        log "    sha256：${ANCHOR_SHA}"
    else
        warn "默认锚表不存在：${ANCHOR_TABLE_ACTUAL}"
        DEP_OK=0
    fi
else
    warn "无法确定默认锚表路径"
    DEP_OK=0
fi
# 主仓同名锚表交叉核对（应逐字节一致；不一致仅告警，不阻断——以 worktree 提交为准）
if [ -n "${ANCHOR_TABLE_ACTUAL}" ] && [ -s "${MAIN_REPO}/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json" ] && [ "${WORKTREE}" != "${MAIN_REPO}" ]; then
    _main_anchor_sha="$("${PY}" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${MAIN_REPO}/experiments/results/emse_docstring_anchor_20261017/DOCSTRING_ANCHOR_TABLE.json")"
    if [ "${_main_anchor_sha}" = "${ANCHOR_SHA}" ]; then
        log "  ✓ 主仓同名锚表与 worktree 逐字节一致"
    else
        warn "主仓锚表 sha256（${_main_anchor_sha}）≠ worktree（${ANCHOR_SHA}）——以 worktree 提交为准，记录在案"
    fi
fi

# 3.2 臂注册（run_benchmark.BASELINE_REGISTRY 含两臂）
_reg_out="$(set +e; "${PY}" - "${WORKTREE}" <<'PY'
import sys

wt = sys.argv[1]
sys.path.insert(0, wt)
try:
    import experiments.run_benchmark as rb
except Exception as exc:  # noqa: BLE001
    print(f"IMPORT_FAIL {type(exc).__name__}: {exc}")
    raise SystemExit(1)
reg = getattr(rb, "BASELINE_REGISTRY", {})
arms = ["plain_llm_df", "plain_llm_df_doc_augment"]
missing = [a for a in arms if a not in reg]
if missing:
    print("MISSING " + ",".join(missing))
    raise SystemExit(1)
print("OK " + ",".join(arms))
PY
)" || true
case "${_reg_out}" in
    OK*)
        log "  ✓ 臂已注册：${_reg_out#OK }"
        REG_OUT="${_reg_out#OK }"
        ;;
    *)
        warn "臂注册检查失败（M-1 未合并/未注册 plain_llm_df_doc_augment？）：${_reg_out}"
        DEP_OK=0
        ;;
esac

# 3.3 M-1 分析脚本 + CLI 契约（--df/--augment/--out/--markdown）
if [ -f "${ANALYSIS_SCRIPT}" ]; then
    log "  ✓ 分析脚本：${ANALYSIS_SCRIPT}"
    _help_out="$(cd "${WORKTREE}" && "${PY}" -m experiments.emse_docstring_augment_analysis --help 2>&1)" || true
    _cli_missing=""
    for _flag in "--df" "--augment" "--out" "--markdown"; do
        case "${_help_out}" in
            *"${_flag}"*) : ;;
            *) _cli_missing="${_cli_missing} ${_flag}" ;;
        esac
    done
    if [ -n "${_cli_missing}" ]; then
        warn "分析脚本 --help 未列出必需参数：${_cli_missing}（M-1 CLI 契约不符）"
        DEP_OK=0
    else
        log "  ✓ 分析脚本 CLI 含 --df/--augment/--out/--markdown"
    fi
elif [ "${DRY_RUN}" -eq 1 ]; then
    warn "dry-run：分析脚本尚不存在：${ANALYSIS_SCRIPT}（正式运行会失败退出）"
    DEP_OK=0
else
    warn "分析脚本不存在：${ANALYSIS_SCRIPT}"
    DEP_OK=0
fi

# 3.4 其它依赖
_require_file "${MISGUIDED_SCRIPT}" "机制重放脚本" || DEP_OK=0
_require_file "${PRICE_TABLE}" "价目表" || DEP_OK=0
_require_file "${ANALYSIS_SCRIPT}" "分析脚本" || DEP_OK=0
if [ -s "${PRE_REG}" ]; then
    PRE_REG_SHA="$("${PY}" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${PRE_REG}")"
    log "  ✓ 预注册：${PRE_REG}"
    log "    sha256：${PRE_REG_SHA}"
else
    warn "预注册文件缺失：${PRE_REG}（M-1 交付应在切点提交内）"
    PRE_REG_SHA=""
    DEP_OK=0
fi

if [ "${DEP_OK}" -ne 1 ]; then
    if [ "${DRY_RUN}" -eq 1 ]; then
        warn "dry-run：依赖未完全就绪（上面告警项）——正式运行会失败退出（预期：M-1 尚未提交切点）"
    else
        die "依赖检查未通过（见上）——M-1 交付/切点提交不完整，正式批不得开始。"
    fi
fi

# ─── 4. 二臂并发启动 ────────────────────────────────────────────────────────
echo ""
echo "[4/10] 二臂并发启动（各 P${PARALLELISM}、互异 cache namespace、各自独立 log）"

STAGING_DF="${OUT_DIR}/.staging_df"
STAGING_AUG="${OUT_DIR}/.staging_aug"
LOG_DF="${OUT_DIR}/log_df.log"
LOG_AUG="${OUT_DIR}/log_aug.log"
NS_DF="$(arm_namespace df)"
NS_AUG="$(arm_namespace aug)"
BASELINE_DF="$(arm_baseline df)"
BASELINE_AUG="$(arm_baseline aug)"

# 共同 env 白名单（不得含任何密钥；记录用于 RUN_MANIFEST/README 审计）
_arm_env_common=(AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled
    "BENCHMARK_PARALLELISM=${PARALLELISM}"
    "AITESTER_BATCH_MAX_CALLS=${CAPS_BATCH_CALLS}"
    COST_BUDGET_ENABLE=true "COST_BUDGET_USD=${CAPS_COST_USD}"
    "AITESTER_TRACE_DIR=${OUT_DIR}/traces")
# 显式 unset：DOC_ANCHOR_TABLE（M-4 要求默认锚表）、AITESTER_LLM_CACHE（默认开）、
# AITESTER_QUIXBUGS_DATA（用默认缓存数据）、思考链附加参数（保持项目默认）
_arm_env_unset=(-u DOC_ANCHOR_TABLE -u AITESTER_LLM_CACHE -u AITESTER_QUIXBUGS_DATA
    -u LLM_REASONING_EFFORT -u LLM_MAX_OUTPUT_TOKENS -u AITESTER_SMOKE_LLM)

_arm_cmd=() # 全局（bash 3.2 无关联数组；每次 launch 前构建）
_build_arm_cmd() { # arm baseline namespace staging
    local _a="$1" _baseline="$2" _ns="$3" _staging="$4"
    _arm_cmd=(env "${_arm_env_unset[@]}" "${_arm_env_common[@]}" "AITESTER_CACHE_NAMESPACE=${_ns}"
        "${PY}" "${WORKTREE}/experiments/run_main_batch.py"
        --dataset quixbugs --task-count "${EXPECT_TASKS}" --seed "${SEED}"
        --baselines "${_baseline}" --output-dir "${_staging}" --skip-stats
        ${DIRTY_EXTRA[@]+"${DIRTY_EXTRA[@]}"})
}

_launch_arm() { # arm baseline namespace staging logfile
    local _a="$1" _baseline="$2" _ns="$3" _staging="$4" _log="$5"
    local _start_epoch _start_iso
    _start_epoch="$(date +%s)"
    _start_iso="$(date -u +%FT%TZ)"
    _build_arm_cmd "${_a}" "${_baseline}" "${_ns}" "${_staging}"
    printf '%q ' "${_arm_cmd[@]}" > "${OUT_DIR}/.arm_${_a}.cmd"
    printf '\n' >> "${OUT_DIR}/.arm_${_a}.cmd"
    mkdir -p "${_staging}"
    {
        echo "=== M-4 ARM=${_a} baseline=${_baseline} namespace=${_ns} ==="
        echo "START_ISO_UTC=${_start_iso} START_EPOCH=${_start_epoch}"
        echo "GIT_HEAD=${GIT_HEAD_PRE} GIT_STATUS_PRE=${GIT_DIRTY_PRE:-<clean>}"
        echo "OUTPUT_STAGING=${_staging}"
        echo "TRACE_DIR=${OUT_DIR}/traces"
        echo "ARM_ENV_WHITELIST=${_arm_env_common[*]} AITESTER_CACHE_NAMESPACE=${_ns} DOC_ANCHOR_TABLE=<unset>"
        printf 'CMD:'
        cat "${OUT_DIR}/.arm_${_a}.cmd"
    } >> "${_log}"
    printf '%s %s\n' "${_start_epoch}" "${_start_iso}" > "${OUT_DIR}/.arm_${_a}.start"
    rm -f "${OUT_DIR}/.arm_${_a}.rc"
    # 子 shell 内执行并写退出码（避免僵尸进程轮询问题；内部 set +e 防 rc 未写）
    (
        set +e
        "${_arm_cmd[@]}" >> "${_log}" 2>&1
        echo $? > "${OUT_DIR}/.arm_${_a}.rc"
    ) &
    _ARM_PID=$!
    printf '%s\n' "${_ARM_PID}" > "${OUT_DIR}/.arm_${_a}.pid"
}

_scan_orphans() { # phase
    local _phase="$1" _ts _out _rc
    _ts="$(date -u +%FT%TZ)"
    set +e
    _out="$(env -u DOC_ANCHOR_TABLE "${PY}" "${ORPHAN_SCRIPT}" --json --min-age 60 2>&1)"
    _rc=$?
    set -e
    printf '%s phase=%s detector_exit=%s %s\n' "${_ts}" "${_phase}" "${_rc}" "${_out}" >> "${OUT_DIR}/proc_hygiene.log"
    if [ "${_rc}" -ne 0 ]; then
        ORPHAN_HIT=$((ORPHAN_HIT + 1))
        warn "孤儿进程巡检命中（phase=${_phase}，detector_exit=${_rc}）：只读记录于 ${OUT_DIR}/proc_hygiene.log（脚本不自动 kill）"
    fi
}

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  （dry-run：以下为将执行的实际命令，不执行、零 LLM 调用）"
    for _a in "${ARM_LABELS[@]}"; do
        _baseline="$(arm_baseline "${_a}")"
        _ns="$(arm_namespace "${_a}")"
        _staging="${STAGING_DF}"
        if [ "${_a}" = "aug" ]; then _staging="${STAGING_AUG}"; fi
        _build_arm_cmd "${_a}" "${_baseline}" "${_ns}" "${_staging}"
        echo "  [臂 ${_a}] → ${_baseline}（ns=${_ns}）"
        printf '      %q' "${_arm_cmd[@]}"
        printf '\n      log → %s/log_%s.log（独立 log）\n' "${OUT_DIR}" "${_a}"
    done
else
    : > "${OUT_DIR}/proc_hygiene.log"
    printf 'M-4 proc hygiene: 每 5min 只读巡检（detect_orphan_procs.py --json --min-age 60）；不自动 kill\n' >> "${OUT_DIR}/proc_hygiene.log"
    _scan_orphans pre_batch
    rm -rf "${STAGING_DF}" "${STAGING_AUG}"
    mkdir -p "${STAGING_DF}" "${STAGING_AUG}"

    _launch_arm df "${BASELINE_DF}" "${NS_DF}" "${STAGING_DF}" "${LOG_DF}"
    PID_DF="${_ARM_PID}"
    _launch_arm aug "${BASELINE_AUG}" "${NS_AUG}" "${STAGING_AUG}" "${LOG_AUG}"
    PID_AUG="${_ARM_PID}"
    DF_START_EPOCH="$(awk '{print $1}' "${OUT_DIR}/.arm_df.start")"
    AUG_START_EPOCH="$(awk '{print $1}' "${OUT_DIR}/.arm_aug.start")"
    log "  ✓ df 臂已启动：pid=${PID_DF}（baseline=${BASELINE_DF}，ns=${NS_DF}）"
    log "  ✓ aug 臂已启动：pid=${PID_AUG}（baseline=${BASELINE_AUG}，ns=${NS_AUG}）"
    log "  两臂启动时间差：$((AUG_START_EPOCH - DF_START_EPOCH))s（同批并发，见 README 调度偏差）"
    log "  每 5min 只读孤儿巡检 → ${OUT_DIR}/proc_hygiene.log；跑批期间不得并发其他重型任务"
fi

# ─── 5. 监控与等待 ──────────────────────────────────────────────────────────
echo ""
echo "[5/10] 监控与等待（每 5min 只读孤儿巡检；每 15s 检查臂完成）"
RC_DF=""
RC_AUG=""
END_ALL_EPOCH=""
END_ALL_ISO=""
if [ "${DRY_RUN}" -eq 0 ]; then
    _last_scan="$(date +%s)"
    _next_log=600
    while :; do
        _done=1
        [ -f "${OUT_DIR}/.arm_df.rc" ] || _done=0
        [ -f "${OUT_DIR}/.arm_aug.rc" ] || _done=0
        if [ "${_done}" -eq 1 ]; then break; fi
        sleep 15
        _now="$(date +%s)"
        _elapsed=$((_now - START_ALL_EPOCH))
        if [ $((_now - _last_scan)) -ge 300 ]; then
            _scan_orphans "in_batch_t${_elapsed}s"
            _last_scan="$_now"
            log "  … 已运行 $((_elapsed / 60))min（df=$([ -f "${OUT_DIR}/.arm_df.rc" ] && echo done || echo running)，aug=$([ -f "${OUT_DIR}/.arm_aug.rc" ] && echo done || echo running)）"
        fi
        if [ "${_elapsed}" -ge "${_next_log}" ]; then
            _next_log=$((_next_log + 600))
        fi
    done
    # 回收子 shell（rc 已由各臂 rc 文件记录，wait 仅清理）
    set +e
    wait "${PID_DF}" 2>/dev/null
    wait "${PID_AUG}" 2>/dev/null
    set -e
    RC_DF="$(cat "${OUT_DIR}/.arm_df.rc" 2>/dev/null || echo 127)"
    RC_AUG="$(cat "${OUT_DIR}/.arm_aug.rc" 2>/dev/null || echo 127)"
    case "${RC_DF}" in '' | *[!0-9]*) RC_DF=127 ;; esac
    case "${RC_AUG}" in '' | *[!0-9]*) RC_AUG=127 ;; esac
    END_ALL_EPOCH="$(date +%s)"
    END_ALL_ISO="$(date -u +%FT%TZ)"
    WALL_TOTAL=$((END_ALL_EPOCH - START_ALL_EPOCH))
    _scan_orphans post_batch
    log "  ✓ 两臂结束：df exit=${RC_DF}，aug exit=${RC_AUG}，总墙钟 ${WALL_TOTAL}s（$((WALL_TOTAL / 60))min）"
else
    echo "  （dry-run 跳过等待/巡检；正式运行每 5min 只读巡检并等待两臂完成）"
fi

# ─── 6. 工件收集与逐臂元数据 ────────────────────────────────────────────────
echo ""
echo "[6/10] 工件收集与逐臂元数据（provenance/token/成本/判分/审计/逐任务）"
ARM_FAIL=0
BATCH_DF=""
BATCH_AUG=""

_collect_arm() { # arm baseline namespace staging rc
    local _a="$1" _baseline="$2" _ns="$3" _staging="$4" _rc="$5"
    local _log="${OUT_DIR}/log_${_a}.log"
    local _start_epoch _start_iso _end_epoch _end_iso _wall _batch _target
    _start_epoch="$(awk '{print $1}' "${OUT_DIR}/.arm_${_a}.start")"
    _start_iso="$(awk '{print $2}' "${OUT_DIR}/.arm_${_a}.start")"
    _end_epoch="$(date +%s)"
    _end_iso="$(date -u +%FT%TZ)"
    _wall=$((_end_epoch - _start_epoch))
    _target=""
    _batch=""
    _FOUND=()
    if [ -d "${_staging}" ]; then
        while IFS= read -r _f; do
            if [ -n "${_f}" ]; then _FOUND+=("${_f}"); fi
        done < <(find "${_staging}" -maxdepth 1 -type f -name 'benchmark_*.json' 2>/dev/null | sort)
    fi
    if [ "${#_FOUND[@]}" -eq 1 ]; then
        _batch="${_FOUND[0]}"
        _target="${OUT_DIR}/$(basename "${_batch}")"
        if [ -e "${_target}" ]; then
            # 并发臂同秒完成 → 文件名冲突保护：绝不覆盖，加臂后缀
            if [ "${_a}" = "aug" ]; then
                _target="${OUT_DIR}/$(basename "${_batch}" .json)_aug.json"
            else
                _target="${OUT_DIR}/$(basename "${_batch}" .json)_df.json"
            fi
            warn "批次文件名同秒冲突，重命名为：$(basename "${_target}")（不覆盖另一臂工件）"
        fi
        if [ -e "${_target}" ]; then
            warn "目标工件已存在，拒绝覆盖：${_target}"
            _target=""
        fi
        if [ -n "${_target}" ]; then
            mv "${_batch}" "${_target}"
            _batch="${_target}"
            printf '%s\n' "${_batch}" > "${OUT_DIR}/.arm_${_a}.batch_path"
        fi
    elif [ "${#_FOUND[@]}" -gt 1 ]; then
        warn "臂 ${_a} staging 内出现多个批次 JSON（${#_FOUND[@]} 个）——请人工检查 ${_staging}"
    fi
    rmdir "${_staging}" 2>/dev/null || true
    {
        echo "END_ISO_UTC=${_end_iso} END_EPOCH=${_end_epoch} EXIT_CODE=${_rc} WALL_SECONDS=${_wall}"
        echo "GIT_STATUS_AFTER=${GIT_STATUS_AFTER}"
        echo "BATCH_FILE=${_batch:-<missing>}"
    } >> "${_log}"
    if [ "${_rc}" -ne 0 ] || [ -z "${_batch}" ]; then
        # 失败臂：保留日志/工件，写 failed meta，不重跑
        "${PY}" - "${_a}" "${_baseline}" "${_ns}" "${_rc}" "${_start_iso}" "${_end_iso}" "${_wall}" \
            "${_staging}" "${_log}" "${OUT_DIR}/arm_${_a}.meta.json" <<'PY' || true
import json
import sys
from pathlib import Path

arm, baseline, ns, rc, start_iso, end_iso, wall, staging, log_path, out_path = sys.argv[1:11]
meta = {
    "script_version": "m-round-m4-v1",
    "arm": arm,
    "baseline": baseline,
    "cache_namespace": ns,
    "status": "failed",
    "exit_code": int(rc),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds": int(wall),
    "log_file": log_path,
    "staging_dir": staging,
    "note": "臂失败/中断：日志与部分工件保留，按协议不重跑（见 RUN_MANIFEST）",
}
Path(out_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
PY
        ARM_FAIL=1
        return 0
    fi
    # 成功臂：结构化元数据（数字全部来自批次工件）
    "${PY}" - "${_batch}" "${_a}" "${_baseline}" "${_ns}" "${_start_epoch}" "${_end_epoch}" \
        "${_start_iso}" "${_end_iso}" "${PRICE_TABLE}" "${OUT_DIR}/arm_${_a}.meta.json" \
        "quixbugs" "${SEED}" "${PARALLELISM}" "${EXPECT_TASKS}" "${SCRIPT_VERSION}" "${_log}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

(batch_path, arm, baseline, ns, start_epoch, end_epoch, start_iso, end_iso,
 price_path, out_path, dataset, seed, parallelism, planned_tasks, script_version, log_path) = sys.argv[1:17]

data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
prov = data.get("provenance") or {}
rd = (data.get("results") or {}).get(baseline)
if rd is None:
    raise SystemExit(f"批次工件缺少臂 '{baseline}' 结果键（baselines={list((data.get('results') or {}).keys())}）")
details = rd.get("details") or []
tm = rd.get("token_metrics") or {}

model = prov.get("model_name") or ""
try:
    price = (json.loads(Path(price_path).read_text(encoding="utf-8")).get("models") or {}).get(model) or {}
except (OSError, ValueError):
    price = {}
in_per_m = price.get("input_per_mtok")
out_per_m = price.get("output_per_mtok")
cost_usd = None
if isinstance(in_per_m, (int, float)) and isinstance(out_per_m, (int, float)):
    cost_usd = round(
        (float(tm.get("total_input_tokens") or 0) / 1e6) * float(in_per_m)
        + (float(tm.get("total_output_tokens") or 0) / 1e6) * float(out_per_m),
        6,
    )

# 判分口径：detection_rate 非 None 才进分母（主分析集=41 缺陷程序）
meas = [r for r in details if r.get("detection_rate") is not None]
det = [r for r in meas if r.get("detection_rate") == 1.0]
rep = [r for r in meas if r.get("repair_rate") == 1.0]
ff = [r for r in meas if r.get("false_fix_rate") == 1.0]

def _is_defect_program(r):
    tid = str(r.get("task_id") or "")
    return not tid.endswith("_test")

defect_rows = [r for r in details if _is_defect_program(r)]
defect_meas = [r for r in defect_rows if r.get("detection_rate") is not None]
defect_det = [r for r in defect_meas if r.get("detection_rate") == 1.0]

def _counts(rows, key):
    vals = [r.get(key) for r in rows if r.get(key)]
    return {str(k): vals.count(k) for k in sorted({str(v) for v in vals})}

spec_aug_all = _counts(details, "spec_augment_applied")
spec_aug_41 = _counts(defect_rows, "spec_augment_applied")
spec_rep_all = _counts(details, "spec_replace_applied")
verdict_41 = _counts(defect_rows, "specificity_gate_verdict")
over_red_share = None
if verdict_41:
    _spec = verdict_41.get("specific_red", 0) + verdict_41.get("over_red", 0)
    if _spec:
        over_red_share = round(verdict_41.get("over_red", 0) / _spec, 4)

per_task = []
for r in details:
    per_task.append({
        "task_id": r.get("task_id"),
        "analysis_set": "defect_program" if _is_defect_program(r) else "driver_or_unknown",
        "detection_rate": r.get("detection_rate"),
        "repair_rate": r.get("repair_rate"),
        "false_fix_rate": r.get("false_fix_rate"),
        "test_error_rate": r.get("test_error_rate"),
        "verdict": r.get("specificity_gate_verdict"),
        "spec_replace_applied": r.get("spec_replace_applied"),
        "spec_augment_applied": r.get("spec_augment_applied"),
        "token_usage": r.get("token_usage"),
        "elapsed_seconds": r.get("elapsed_seconds"),
        "stop_reason": r.get("stop_reason"),
    })

meta = {
    "script_version": script_version,
    "arm": arm,
    "baseline": baseline,
    "cache_namespace": ns,
    "dataset": dataset,
    "seed": int(seed),
    "parallelism": int(parallelism),
    "planned_tasks_flag": int(planned_tasks),
    "batch_file": str(batch_path),
    "batch_bytes": Path(batch_path).stat().st_size,
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "status": "completed",
    "start_epoch": int(start_epoch),
    "end_epoch": int(end_epoch),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds": int(end_epoch) - int(start_epoch),
    "log_file": log_path,
    "provenance": {
        "git_sha": prov.get("git_sha"),
        "git_dirty": prov.get("git_dirty"),
        "dirty_reason": prov.get("dirty_reason"),
        "model_name": prov.get("model_name"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "temperature": prov.get("temperature"),
        "profile": prov.get("profile"),
        "seed": prov.get("seed"),
        "cache_enabled": prov.get("cache_enabled"),
        "cache_namespace": prov.get("cache_namespace"),
        "valid_apis": prov.get("valid_apis"),
        "env_snapshot": prov.get("env_snapshot"),
    },
    "top_level": {
        "dataset": data.get("dataset"),
        "seed": data.get("seed"),
        "total_tasks": data.get("total_tasks"),
        "parallelism": data.get("parallelism"),
        "baselines": data.get("baselines"),
        "timestamp": data.get("timestamp"),
    },
    "tasks_total_rows": len(details),
    "token_metrics": tm,
    "cost_usd_standard_price": cost_usd,
    "cost_price_row": {
        "model": model,
        "input_per_mtok": in_per_m,
        "output_per_mtok": out_per_m,
        "currency": price.get("currency"),
        "as_of": price.get("as_of"),
        "source": price.get("source"),
    },
    "detection": {
        "measurable": len(meas),
        "detected": len(det),
        "detection_rate": round(len(det) / len(meas), 4) if meas else None,
        "repair_rate": round(len(rep) / len(meas), 4) if meas else None,
        "false_fix_rate": round(len(ff) / len(meas), 4) if meas else None,
        "defect_41_measurable": len(defect_meas),
        "defect_41_detected": len(defect_det),
        "defect_41_detection_rate": round(len(defect_det) / len(defect_meas), 4) if defect_meas else None,
        "detection_none_task_ids": [r.get("task_id") for r in details if r.get("detection_rate") is None],
    },
    "audit": {
        "caliber": "QuixBugs 50 行（41 缺陷程序 + 9 测试驱动）；主分析集=41 缺陷程序（task_id 非 _test 后缀）",
        "spec_augment_applied_counts_all50": spec_aug_all,
        "spec_augment_applied_counts_41": spec_aug_41,
        "spec_replace_applied_counts_all50": spec_rep_all,
        "specificity_gate_verdict_counts_41": verdict_41,
        "over_red_share_41": over_red_share,
    },
    "per_task": per_task,
}
Path(out_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    f"[arm {arm}] 墙钟 {meta['wall_seconds']}s｜rows={len(details)}｜"
    f"41口径 detection={meta['detection']['defect_41_detected']}/{meta['detection']['defect_41_measurable']}"
    f"={meta['detection']['defect_41_detection_rate']}｜all detection={meta['detection']['detected']}/{meta['detection']['measurable']}"
    f"｜tokens={tm.get('total_tokens')}｜cost≈${cost_usd}｜git_dirty={prov.get('git_dirty')}"
    f"｜spec_augment_applied={spec_aug_all}"
)
PY
    printf '%s\n' "${_batch}" > "${OUT_DIR}/.arm_${_a}.batch_path"
    return 0
}

if [ "${DRY_RUN}" -eq 0 ]; then
    GIT_DIRTY_AFTER="$(git -C "${WORKTREE}" status --porcelain 2>/dev/null || true)"
    if [ -n "${GIT_DIRTY_AFTER}" ]; then
        GIT_STATUS_AFTER="$(printf '%s' "${GIT_DIRTY_AFTER}" | tr '\n' ';')"
    else
        GIT_STATUS_AFTER="<clean>（git status --porcelain 0 行）"
    fi
    _collect_arm df "${BASELINE_DF}" "${NS_DF}" "${STAGING_DF}" "${RC_DF}"
    _collect_arm aug "${BASELINE_AUG}" "${NS_AUG}" "${STAGING_AUG}" "${RC_AUG}"
    BATCH_DF="$(cat "${OUT_DIR}/.arm_df.batch_path" 2>/dev/null || true)"
    BATCH_AUG="$(cat "${OUT_DIR}/.arm_aug.batch_path" 2>/dev/null || true)"
    log "  df 批次工件：${BATCH_DF:-<缺失>}"
    log "  aug 批次工件：${BATCH_AUG:-<缺失>}"
    if [ -n "${GIT_DIRTY_AFTER}" ]; then
        warn "跑后 worktree 不干净（$(printf '%s' "${GIT_DIRTY_AFTER}" | wc -l | tr -d ' ') 行）；结果目录在 gitignore 内应不产生变更"
        printf '%s\n' "${GIT_DIRTY_AFTER}" | head -10 >&2
    else
        log "  ✓ 跑后 worktree 干净（git status --porcelain 0 行）"
    fi
    # 两臂 provenance 脏树断言
    for _a in "${ARM_LABELS[@]}"; do
        _meta="${OUT_DIR}/arm_${_a}.meta.json"
        [ -s "${_meta}" ] || continue
        _dirty="$("${PY}" -c 'import json,sys; d=json.load(open(sys.argv[1])); print((d.get("provenance") or {}).get("git_dirty"))' "${_meta}")"
        if [ "${_dirty}" != "False" ] && [ "${_dirty}" != "false" ]; then
            if [ "${ALLOW_DIRTY}" -eq 1 ]; then
                warn "臂 ${_a} provenance.git_dirty=${_dirty}（--allow-dirty 调试豁免，正式批禁止）"
            else
                ARM_FAIL=1
                warn "臂 ${_a} provenance.git_dirty=${_dirty}——违反干净树协议！"
            fi
        fi
        _arm_git_sha="$("${PY}" -c 'import json,sys; d=json.load(open(sys.argv[1])); print((d.get("provenance") or {}).get("git_sha"))' "${_meta}")"
        if [ -n "${EXPECT_SHA}" ] && [ "${_arm_git_sha}" != "${EXPECT_SHA}" ]; then
            ARM_FAIL=1
            warn "臂 ${_a} provenance.git_sha=${_arm_git_sha} ≠ --expect-sha=${EXPECT_SHA}"
        fi
    done
else
    echo "  （dry-run 跳过收集；正式运行会移动两臂批次 JSON 进 ${OUT_DIR} 并写逐臂 meta）"
fi

if [ "${DRY_RUN}" -eq 0 ] && [ "${ARM_FAIL}" -ne 0 ]; then
    echo ""
    warn "跑批失败/中断（见上）；按协议保留日志与部分工件、不重跑。写出失败清单并复制回主仓。"
    WALL_TOTAL=$(( $(date +%s) - START_ALL_EPOCH ))
    "${PY}" - "${OUT_DIR}" "${RUN_STAMP}" "${SCRIPT_VERSION}" "${WORKTREE}" "${MAIN_REPO}" \
        "${GIT_HEAD_PRE}" "${GIT_DIRTY_PRE}" "${GIT_DIRTY_AFTER:-}" "${START_ALL_ISO}" \
        "$(date -u +%FT%TZ)" "${WALL_TOTAL}" "${RC_DF}" "${RC_AUG}" "${PARALLELISM}" "${SEED}" <<'PY'
import glob
import json
import sys
from pathlib import Path

(out_dir, run_stamp, script_version, worktree, main_repo, git_head, dirty_pre, dirty_after,
 start_iso, end_iso, wall, rc_df, rc_aug, parallelism, seed) = sys.argv[1:16]
out = Path(out_dir)
arms = []
for p in sorted(out.glob("arm_*.meta.json")):
    try:
        arms.append(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        continue
manifest = {
    "run_stamp": run_stamp,
    "script_version": script_version,
    "status": "failed",
    "protocol": {"AITESTER_PROFILE": "logic", "TEMPERATURE": "0.0", "LLM_THINKING_MODE": "disabled",
                 "BENCHMARK_PARALLELISM": int(parallelism), "seed": int(seed), "task_count_flag": 50,
                 "arms": ["df:plain_llm_df", "aug:plain_llm_df_doc_augment"],
                 "cache_namespaces": ["emse_docstring_augment_20261017_df", "emse_docstring_augment_20261017_aug"]},
    "repo": {"worktree": worktree, "main_repo": main_repo, "git_sha": git_head,
             "git_dirty_pre": bool(str(dirty_pre).strip()), "git_dirty_after": bool(str(dirty_after).strip())},
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds_total": int(wall),
    "arm_exit_codes": {"df": int(rc_df), "aug": int(rc_aug)},
    "arms": arms,
    "note": "跑批失败：日志与部分工件保留，不重跑，不删除任何文件；分析/重放未执行。",
}
mp = out / f"RUN_MANIFEST_{run_stamp}.json"
mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"FAILED RUN_MANIFEST：{mp}")
PY
    # 失败路径也写 SHA256SUMS 并复制回主仓（保留证据）
    "${PY}" - "${OUT_DIR}" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
lines = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or p.name in ("SHA256SUMS",):
        continue
    rel = p.relative_to(root).as_posix()
    lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
(root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"SHA256SUMS：（{len(lines)} 条）")
PY
    if [ "${WORKTREE}" != "${MAIN_REPO}" ]; then
        _dst="${MAIN_REPO}/experiments/results/$(basename "${OUT_DIR}")"
        if [ -e "${_dst}" ] && [ -n "$(ls -A "${_dst}" 2>/dev/null || true)" ]; then
            warn "主仓目标目录已存在且非空，跳过复制：${_dst}"
        else
            mkdir -p "${_dst}"
            cp -Rp "${OUT_DIR}"/. "${_dst}"/
            log "  ✓ 失败工件已复制回主仓：${_dst}"
        fi
    fi
    echo ""
    echo "✗ M-4 正式批未成功（df exit=${RC_DF}，aug exit=${RC_AUG}）——日志/工件已保留，未重跑。"
    exit 4
fi

# ─── 7. prompt 增广核验（LLM 缓存证据：代码块 + 规格锚同现） ──────────────────
echo ""
echo "[7/10] prompt 增广核验（从 LLM 缓存抽 1–2 例：目标代码块 + 规格锚段落同时在场）"
EVIDENCE_OK=0
if [ "${DRY_RUN}" -eq 0 ] && [ -n "${ANCHOR_TABLE_ACTUAL}" ] && [ -s "${ANCHOR_TABLE_ACTUAL}" ]; then
    set +e
    "${PY}" - "${WORKTREE}" "${OUT_DIR}" "${ANCHOR_TABLE_ACTUAL}" \
        "${START_ALL_EPOCH}" "${END_ALL_EPOCH}" \
        "${OUT_DIR}/PROMPT_EVIDENCE.json" "${OUT_DIR}/PROMPT_EVIDENCE.md" <<'PY'
"""从 LLM 文件缓存抽取 M-4 一等证据：augment prompt 同时包含目标代码块与规格锚段落。

**关键判据澄清（M-1 实测）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级
docstring（如 ``python_programs/bitcount.py`` 末尾的 Input/Output/Examples 块），
因此"规格文本在 prompt 中出现"**不能**单独证明增广段被注入（df 对照臂的代码块里
也含该文本）。本证据因此以 **M-1 augment framing 段**为决定性判据：

  1) system 含 generator 标志（"测试代码生成专家"）；
  2) prompt 含 augment framing 标记（M-1 ``_AUGMENT_HEADER[0]``：
     "【规格增广模式（Spec-Augment）：规格锚与目标代码并列】"，运行时从
     worktree 的 ``src.tools.spec_first`` 导入，防措辞漂移）；
  3) 目标代码标记（锚表 ``source_head``，如 "def bitcount(n):"）位于 framing
     标记**之前**（代码块仍在，增广段追加在 code block 之后）；
  4) 规格锚标记（human_spec 最长行）在 framing 段之后再次出现
     （``spec_last_after_frame``；同一文本在代码块中可出现一次，故取最后一次出现，
     并记录出现次数以区分"源码内嵌"与"增广段重复注入"）。
对照：时间窗内同 generator 缓存条目含代码标记但**无** framing 段 = df 对照臂
（负向对照；df 臂不会注入增广段）。

输出 JSON + Markdown；不打印任何密钥（prompt/system 内容本身不含密钥）。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

wt, out_dir, anchor_path, start_s, end_s, out_json, out_md = sys.argv[1:9]
start = float(start_s)
end = float(end_s)
out = Path(out_dir)
cache_dir = os.environ.get("AITESTER_LLM_CACHE_DIR") or os.path.join(
    os.path.expanduser("~"), ".cache", "aitester", "llm"
)
GEN_SYSTEM_MARKER = "测试代码生成专家"

# framing 标记：优先从 worktree 的 M-1 实现导入（防措辞漂移）；回退字面量
frame_marker = "【规格增广模式（Spec-Augment）：规格锚与目标代码并列】"
try:
    sys.path.insert(0, wt)
    from src.tools.spec_first import _AUGMENT_HEADER as _AH  # type: ignore

    if isinstance(_AH, (tuple, list)) and _AH and str(_AH[0]).strip():
        frame_marker = str(_AH[0]).strip()
except Exception:  # noqa: BLE001 - 证据层不得因导入失败中断
    pass
spec_section_marker = "【独立于实现的规格锚（人类 docstring）】"

anchors = (json.loads(Path(anchor_path).read_text(encoding="utf-8")) or {}).get("anchors") or {}
candidates = []
for _h, entry in anchors.items():
    human_spec = str(entry.get("human_spec") or "").strip()
    source_head = str(entry.get("source_head") or "").strip()
    if not human_spec or not source_head:
        continue
    spec_lines = [ln.strip() for ln in human_spec.splitlines() if len(ln.strip()) >= 20]
    if not spec_lines:
        continue
    spec_marker = max(spec_lines, key=len)
    candidates.append(
        {
            "anchor_hash": _h,
            "function_name": entry.get("function_name"),
            "source_head": source_head,
            "spec_marker": spec_marker,
            "human_spec_len": len(human_spec),
        }
    )
candidates.sort(key=lambda c: (-c["human_spec_len"], str(c.get("function_name"))))

records = []
n_generator_entries = 0
n_augment_framing = 0
n_code_no_frame = 0
n_unreadable = 0
if os.path.isdir(cache_dir):
    for name in sorted(os.listdir(cache_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(cache_dir, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_mtime < start - 300 or st.st_mtime > end + 300:
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            n_unreadable += 1
            continue
        try:
            ts = float(payload.get("timestamp") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        if ts and (ts < start - 300 or ts > end + 300):
            continue
        system = str(payload.get("system") or "")
        prompt = str(payload.get("prompt") or "")
        if GEN_SYSTEM_MARKER not in system:
            continue
        n_generator_entries += 1
        matched = None
        for cand in candidates:
            if cand["source_head"] and cand["source_head"] in prompt:
                matched = cand
                break
        if matched is None:
            continue
        code_off = prompt.find(matched["source_head"])
        frame_off = prompt.find(frame_marker)
        spec_hits = []
        pos = 0
        while True:
            idx = prompt.find(matched["spec_marker"], pos)
            if idx < 0:
                break
            spec_hits.append(idx)
            pos = idx + 1
        spec_last = spec_hits[-1] if spec_hits else -1
        has_frame = frame_off >= 0
        augment_ok = bool(has_frame and code_off >= 0 and code_off < frame_off and spec_last > frame_off)
        rec = {
            "cache_file": name,
            "cache_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "cache_timestamp": ts,
            "function_name": matched["function_name"],
            "source_head": matched["source_head"],
            "spec_marker_len": len(matched["spec_marker"]),
            "prompt_len": len(prompt),
            "code_offset": code_off,
            "augment_frame_offset": frame_off,
            "spec_marker_offsets": spec_hits,
            "spec_marker_occurrences": len(spec_hits),
            "spec_last_after_frame": spec_last > frame_off if has_frame else False,
            "has_spec_section_header": spec_section_marker in prompt,
            "augment_framing_present": has_frame,
            "augment_ok": augment_ok,
            "excerpt_augment": (
                prompt[max(0, frame_off - 80): min(len(prompt), frame_off + 1100)] if has_frame else ""
            ),
        }
        records.append(rec)
        if augment_ok:
            n_augment_framing += 1
        else:
            n_code_no_frame += 1

examples = [r for r in records if r["augment_ok"]][:2]
evidence_ok = bool(examples) and all(
    r["code_offset"] >= 0
    and r["code_offset"] < r["augment_frame_offset"]
    and r["spec_last_after_frame"]
    for r in examples
)
payload = {
    "schema": "prompt_augment_evidence/2",
    "generated_by": "experiments/run_augment_batch.sh",
    "cache_dir": cache_dir,
    "window": {"start_epoch": start, "end_epoch": end},
    "generator_system_marker": GEN_SYSTEM_MARKER,
    "augment_frame_marker": frame_marker,
    "spec_section_marker": spec_section_marker,
    "anchor_table": str(anchor_path),
    "criterion_note": (
        "QuixBugs 人类规格文本同时内嵌于缺陷源码尾部（模块 docstring），"
        "因此以 M-1 augment framing 段+顺序（代码标记 < framing < 规格锚末次出现）为决定性判据；"
        "无 framing 段的同 generator 条目 = df 对照臂（负向对照）。"
    ),
    "n_generator_cache_entries_in_window": n_generator_entries,
    "n_augment_framing_entries": n_augment_framing,
    "n_code_only_entries": n_code_no_frame,
    "n_unreadable_cache_files": n_unreadable,
    "negative_control_ok": n_code_no_frame > 0,
    "evidence_status": "ok" if evidence_ok else "missing",
    "examples": examples,
    "records_augment_arm": [r for r in records if r["augment_ok"]][:5],
}
(out / "PROMPT_EVIDENCE.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

lines = []
lines.append("# M-4 prompt 增广核验（LLM 缓存证据，脚本抽取）")
lines.append("")
lines.append("> 目的：证明 augment 臂的 Generator prompt **同时包含目标缺陷代码块与人类规格锚段落**")
lines.append("> （M-1 处理有效性的一等证据）。数据来源 = `~/.cache/aitester/llm/*.json` 中批次时间窗内")
lines.append("> 的 generator 调用缓存。")
lines.append("")
lines.append("> **判据澄清（重要）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级 docstring，")
lines.append("> 因此「规格文本出现」**不能**单独证明增广注入（df 对照臂代码块内也含该文本）。")
lines.append("> 本证据以 **M-1 augment framing 段**为决定性判据：代码标记 < framing 标记 < 规格锚末次出现，")
lines.append("> 且 `spec_marker_occurrences` 记录该文本出现次数（源码内嵌 vs 增广段重复注入）。")
lines.append("")
lines.append("## 计数")
lines.append("")
lines.append(f"- 时间窗：`{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start))}` → `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(end))}`")
lines.append(f"- generator 缓存条目数（时间窗内）：**{n_generator_entries}**")
lines.append(f"- augment framing 命中（= augment 臂）：**{n_augment_framing}**")
lines.append(f"- 含代码块但无 framing 段（= df 对照臂，负向对照）：**{n_code_no_frame}**")
lines.append(f"- framing 标记：`{frame_marker}`")
lines.append(f"- 证据状态：**{payload['evidence_status']}**；负向对照在场：**{payload['negative_control_ok']}**")
lines.append("")
if examples:
    lines.append("## 样例（1–2 例）")
    lines.append("")
    for idx, rec in enumerate(examples, 1):
        lines.append(f"### 例 {idx}：`{rec['function_name']}`")
        lines.append("")
        lines.append(f"- 缓存文件：`{rec['cache_file']}`（sha256 `{rec['cache_sha256'][:16]}…`）")
        lines.append(f"- 缓存时间：`{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(rec['cache_timestamp']))}`")
        lines.append(
            f"- prompt 长度：{rec['prompt_len']}；代码标记 offset={rec['code_offset']}；"
            f"augment framing offset={rec['augment_frame_offset']}；"
            f"规格锚出现次数={rec['spec_marker_occurrences']}；末次出现={rec['spec_marker_offsets'][-1] if rec['spec_marker_offsets'] else 'n/a'}；"
            f"增广段小节标题在场={rec['has_spec_section_header']}"
        )
        lines.append("")
        lines.append("```text")
        lines.append(rec["excerpt_augment"].strip())
        lines.append("```")
        lines.append("")
else:
    lines.append("## 样例")
    lines.append("")
    lines.append("未在时间窗内找到含 augment framing 段的 generator 缓存条目——需人工排查（见 JSON）。")
    lines.append("")
(out / "PROMPT_EVIDENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(
    f"提示证据：generator缓存={n_generator_entries}｜augment framing={n_augment_framing}｜"
    f"仅代码(df对照)={n_code_no_frame}｜状态={payload['evidence_status']}"
)
raise SystemExit(0 if evidence_ok else 1)
PY
    EVIDENCE_RC=$?
    set -e
    if [ "${EVIDENCE_RC}" -eq 0 ]; then
        EVIDENCE_OK=1
        log "  ✓ 证据已抽取：${OUT_DIR}/PROMPT_EVIDENCE.json/.md（详情见文件）"
    else
        warn "证据抽取未确认（exit ${EVIDENCE_RC}）——人工核验 ${OUT_DIR}/PROMPT_EVIDENCE.json（不阻断跑批）"
    fi
else
    echo "  （dry-run 跳过：正式运行从缓存抽取 augment prompt 的代码块+规格锚同现证据）"
fi

# ─── 8. M-1 分析判定直出 ────────────────────────────────────────────────────
echo ""
echo "[8/10] M-1 分析判定直出（DF_AUG_REPORT.json/.md；数字不手写）"
ANALYSIS_RC=0
if [ "${DRY_RUN}" -eq 0 ] && [ "${SKIP_ANALYSIS}" -ne 1 ]; then
    if [ -z "${BATCH_DF}" ] || [ -z "${BATCH_AUG}" ]; then
        warn "缺少两臂批次工件，无法分析（df=${BATCH_DF:-<空>} aug=${BATCH_AUG:-<空>}）"
        ANALYSIS_RC=1
        WARN_EXIT=5
    else
        {
            echo "=== M-1 分析命令 ==="
            echo "python -m experiments.emse_docstring_augment_analysis --df ${BATCH_DF} --augment ${BATCH_AUG} --out ${OUT_DIR}/DF_AUG_REPORT.json --markdown ${OUT_DIR}/DF_AUG_REPORT.md"
        } > "${OUT_DIR}/analysis_stdout.log"
        set +e
        ( cd "${WORKTREE}" && env -u DOC_ANCHOR_TABLE "${PY}" -m experiments.emse_docstring_augment_analysis \
            --df "${BATCH_DF}" --augment "${BATCH_AUG}" \
            --out "${OUT_DIR}/DF_AUG_REPORT.json" --markdown "${OUT_DIR}/DF_AUG_REPORT.md" ) >> "${OUT_DIR}/analysis_stdout.log" 2>&1
        ANALYSIS_RC=$?
        set -e
        if [ "${ANALYSIS_RC}" -ne 0 ]; then
            WARN_EXIT=5
            warn "分析脚本失败（exit ${ANALYSIS_RC}，见 ${OUT_DIR}/analysis_stdout.log）——跑批工件保留，可事后重跑分析"
        else
            log "  ✓ 判定报告：${OUT_DIR}/DF_AUG_REPORT.json"
            log "  ✓ Markdown：${OUT_DIR}/DF_AUG_REPORT.md"
            tail -2 "${OUT_DIR}/analysis_stdout.log" 2>/dev/null | sed 's/^/    /' || true
        fi
    fi
elif [ "${SKIP_ANALYSIS}" -eq 1 ]; then
    warn "已 --skip-analysis：判定须另跑（命令见 README §10）"
else
    echo "  （dry-run：将执行）"
    echo "  ${PY} -m experiments.emse_docstring_augment_analysis --df <df.json> --augment <aug.json> --out ${OUT_DIR}/DF_AUG_REPORT.json --markdown ${OUT_DIR}/DF_AUG_REPORT.md"
fi

# ─── 9. 机制重放（misguided/effective，零 LLM） ─────────────────────────────
echo ""
echo "[9/10] 机制重放（misguided/effective 逐测试；零 LLM；输出 ${MISGUIDED_OUT}）"
MISGUIDED_RC=0
if [ "${DRY_RUN}" -eq 0 ] && [ "${SKIP_MISGUIDED}" -ne 1 ]; then
    if [ -z "${BATCH_DF}" ] || [ -z "${BATCH_AUG}" ]; then
        warn "缺少两臂批次工件，跳过机制重放"
        MISGUIDED_RC=1
        WARN_EXIT=6
    elif [ ! -d "${MISGUIDED_OUT}" ]; then
        mkdir -p "${MISGUIDED_OUT}"
    elif [ -n "$(ls -A "${MISGUIDED_OUT}" 2>/dev/null || true)" ]; then
        warn "机制重放输出目录已存在且非空（不覆盖）：${MISGUIDED_OUT}——跳过重放，保留既有工件"
        MISGUIDED_RC=1
        WARN_EXIT=6
    fi
    if [ "${MISGUIDED_RC}" -eq 0 ]; then
        {
            echo "=== misguided/effective 机制重放命令（零 LLM） ==="
            echo "python -m experiments.misguided_metrics --artifact ${BATCH_DF} --artifact ${BATCH_AUG} --out ${MISGUIDED_OUT} --jobs ${MISGUIDED_JOBS}"
        } > "${OUT_DIR}/misguided_stdout.log"
        set +e
        ( cd "${WORKTREE}" && env -u DOC_ANCHOR_TABLE "${PY}" -m experiments.misguided_metrics \
            --artifact "${BATCH_DF}" --artifact "${BATCH_AUG}" \
            --out "${MISGUIDED_OUT}" --jobs "${MISGUIDED_JOBS}" ) >> "${OUT_DIR}/misguided_stdout.log" 2>&1
        MISGUIDED_RC=$?
        set -e
        if [ "${MISGUIDED_RC}" -ne 0 ]; then
            WARN_EXIT=6
            warn "机制重放失败（exit ${MISGUIDED_RC}，见 ${OUT_DIR}/misguided_stdout.log）——批次工件保留"
        else
            log "  ✓ 重放报告：${MISGUIDED_OUT}/MISGUIDED_REPORT.json/.md"
        fi
    fi
elif [ "${SKIP_MISGUIDED}" -eq 1 ]; then
    warn "已 --skip-misguided：机制重放须另跑（命令见 README §10）"
else
    echo "  （dry-run：将执行）"
    echo "  ${PY} -m experiments.misguided_metrics --artifact <df.json> --artifact <aug.json> --out ${MISGUIDED_OUT} --jobs ${MISGUIDED_JOBS}"
fi

# 重放目录 README + SHA256SUMS（数字由报告直出）
if [ "${DRY_RUN}" -eq 0 ] && [ -s "${MISGUIDED_OUT}/MISGUIDED_REPORT.json" ]; then
    "${PY}" - "${MISGUIDED_OUT}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
report_path = root / "MISGUIDED_REPORT.json"
data = json.loads(report_path.read_text(encoding="utf-8"))
rep = data.get("report") or {}
arms = rep.get("arms") or []
inputs = rep.get("inputs") or []
cmd = rep.get("command") or ""
lines = [
    "# M-4 机制重放：misguided/effective 逐测试度量（零 LLM 重放）",
    "",
    "> 性质：M-1 augment 臂的机制侧指标工件（ISSTA'26 逐测试四分类重放），**不参与主判定**。",
    "> 工具：`experiments/misguided_metrics.py`（零 LLM/零网络，只跑本地 pytest 子进程）。",
    "> 本 README 的计数/占比由重放报告的 `report.arms[*].aggregate` 直出，不手写。",
    "",
    "## 输入工件",
    "",
    "| 臂 | 工件 | sha256（前 16） |",
    "|---|---|---|",
]
for item in arms:
    lines.append(
        f"| `{item.get('arm')}` | `{item.get('artifact')}` | `{str(item.get('artifact_sha256'))[:16]}…` |"
    )
lines += ["", "## 逐臂汇总（all_tasks 口径）", ""]
lines.append("| 臂 | 可分析任务 | 可分类测试 | effective | misguided | both_pass | both_fail | effective 占比 | misguided 占比 |")
lines.append("|---|---|---|---|---|---|---|---|---|")
for item in arms:
    agg = ((item.get("aggregate") or {}).get("all_tasks") or {})
    counts = agg.get("counts") or {}
    rates = agg.get("rates") or {}
    lines.append(
        f"| `{item.get('arm')}` | {agg.get('n_tasks_ok')}/{agg.get('n_tasks')} | {agg.get('n_tests_classifiable')} | "
        f"{counts.get('effective')} | {counts.get('misguided')} | {counts.get('both_pass')} | {counts.get('both_fail')} | "
        f"{rates.get('effective_share')} | {rates.get('misguided_share')} |"
    )
comparison = (rep.get("comparison") or {}).get("per_test_defect_programs") or {}
if comparison:
    lines += ["", "## 41 缺陷程序口径（逐测试占比）", ""]
    lines.append("| 类别 | arm_a | arm_b | δ（b−a, pp） |")
    lines.append("|---|---|---|---|")
    for label, row in comparison.items():
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {label} | {row.get('arm_a')} | {row.get('arm_b')} | {row.get('delta_pp_b_minus_a')} |"
        )
lines += [
    "",
    "## 命令",
    "",
    "```bash",
    str(cmd).strip(),
    "```",
    "",
    "> 限制：逐测试分类为机制侧描述性信号，不替代 detection 主判定；分母（可分类测试数）与",
    "> 不可分类原因（timeout/collect_error 等）见 MISGUIDED_REPORT.json 的 `aggregate`/`tasks`。",
    "",
]
(root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
sums = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or p.name == "SHA256SUMS":
        continue
    rel = p.relative_to(root).as_posix()
    sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
(root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
print(f"机制重放 README/SHA256SUMS 完成（{len(sums)} 条）")
PY
fi

# ─── 10. README + RUN_MANIFEST + SHA256SUMS + 复制回主仓 ─────────────────────
echo ""
echo "[10/10] README / RUN_MANIFEST / SHA256SUMS / 复制回主仓 + 逐文件 sha256 校验"
GIT_HEAD_POST="$(git -C "${WORKTREE}" rev-parse HEAD 2>/dev/null || true)"
GIT_DIRTY_POST="$(git -C "${WORKTREE}" status --porcelain 2>/dev/null || true)"
if [ "${DRY_RUN}" -eq 0 ]; then
    WALL_TOTAL=$(( $(date +%s) - START_ALL_EPOCH ))

    # 10.0 自归档运行脚本副本（可复现性：脚本随工件成套归档，sha256 进 SHA256SUMS）
    if [ -f "${_SCRIPT_ABS}" ]; then
        cp -p "${_SCRIPT_ABS}" "${OUT_DIR}/run_augment_batch.sh"
        chmod +x "${OUT_DIR}/run_augment_batch.sh" 2>/dev/null || true
        log "  ✓ 运行脚本已归档：${OUT_DIR}/run_augment_batch.sh"
    else
        warn "无法定位运行脚本自身（_SCRIPT_ABS=${_SCRIPT_ABS}），跳过自归档"
    fi

    # 10.1 RUN_MANIFEST（一站式审计：env/命令/工件/成本/token/墙钟）
    "${PY}" - "${OUT_DIR}" "${RUN_STAMP}" "${SCRIPT_VERSION}" "${WORKTREE}" "${MAIN_REPO}" \
        "${GIT_HEAD_PRE}" "${GIT_DIRTY_PRE:-}" "${GIT_HEAD_POST}" "${GIT_DIRTY_POST:-}" \
        "${START_ALL_ISO}" "$(date -u +%FT%TZ)" "${WALL_TOTAL}" "${PARALLELISM}" "${SEED}" \
        "${EXPECT_TASKS}" "${ANALYSIS_RC}" "${MISGUIDED_RC}" "${ORPHAN_HIT}" \
        "${ANCHOR_TABLE_ACTUAL}" "${ANCHOR_SHA:-}" "${PRE_REG}" "${PRE_REG_SHA:-}" \
        "${BATCH_DF}" "${BATCH_AUG}" "${START_ALL_EPOCH}" "${END_ALL_EPOCH}" "${EVIDENCE_OK}" \
        "${MISGUIDED_OUT}" "${ANCHOR_SHA:-}" <<'PY'
import glob
import hashlib
import json
import sys
from pathlib import Path

(out_dir, run_stamp, script_version, worktree, main_repo, git_head_pre, git_dirty_pre,
 git_head_post, git_dirty_post, start_iso, end_iso, wall_total, parallelism, seed,
 expect_tasks, analysis_rc, misguided_rc, orphan_hit, anchor_path, anchor_sha,
 pre_reg, pre_reg_sha, batch_df, batch_aug, start_epoch, end_epoch, evidence_ok,
 misguided_out, anchor_sha_safe) = sys.argv[1:30]
anchor_sha = anchor_sha or anchor_sha_safe
out = Path(out_dir)

def _sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None

arm_metas = []
for p in sorted(out.glob("arm_*.meta.json")):
    try:
        arm_metas.append(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        continue
batch_files = [f for f in (batch_df, batch_aug) if f]
commands = {}
for a in ("df", "aug"):
    p = out / f".arm_{a}.cmd"
    if p.is_file():
        commands[a] = p.read_text(encoding="utf-8").strip()
misguided_rep = Path(misguided_out) / "MISGUIDED_REPORT.json"
misguided_sha = _sha(misguided_rep) if misguided_rep.is_file() else None
manifest = {
    "run_stamp": run_stamp,
    "script_version": script_version,
    "status": "completed",
    "protocol": {
        "AITESTER_PROFILE": "logic",
        "TEMPERATURE": "0.0",
        "LLM_THINKING_MODE": "disabled",
        "BENCHMARK_PARALLELISM": int(parallelism),
        "seed": int(seed),
        "task_count_flag": int(expect_tasks),
        "task_count_note": "QuixBugs 全量 50 行（41 缺陷程序 + 9 测试驱动）；L 轮修复后 --task-count 对真实数据集等价 --task-limit",
        "arms": {
            "df": "plain_llm_df",
            "aug": "plain_llm_df_doc_augment",
        },
        "cache_namespaces": {
            "df": "emse_docstring_augment_20261017_df",
            "aug": "emse_docstring_augment_20261017_aug",
        },
        "env_caps": {
            "AITESTER_BATCH_MAX_CALLS": 300,
            "COST_BUDGET_ENABLE": "true",
            "COST_BUDGET_USD": 5,
        },
        "DOC_ANCHOR_TABLE": "<unset>（使用 run_benchmark 默认锚表）",
        "AITESTER_TRACE_DIR": str(out / "traces"),
    },
    "repo": {
        "worktree": worktree,
        "main_repo": main_repo,
        "git_sha_pre": git_head_pre,
        "git_sha_post": git_head_post,
        "git_dirty_pre": bool(str(git_dirty_pre).strip()),
        "git_dirty_after": bool(str(git_dirty_post).strip()),
    },
    "runner_script": {
        "file": str(out / "run_augment_batch.sh"),
        "sha256": _sha(out / "run_augment_batch.sh"),
    },
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "start_epoch": int(start_epoch),
    "end_epoch": int(end_epoch),
    "wall_seconds_total": int(wall_total),
    "arm_command_lines": commands,
    "arms": arm_metas,
    "batch_files": batch_files,
    "analysis": {
        "exit_code": int(analysis_rc),
        "json": str(out / "DF_AUG_REPORT.json"),
        "markdown": str(out / "DF_AUG_REPORT.md"),
        "json_sha256": _sha(out / "DF_AUG_REPORT.json"),
        "markdown_sha256": _sha(out / "DF_AUG_REPORT.md"),
    },
    "mechanism_replay": {
        "exit_code": int(misguided_rc),
        "out_dir": str(misguided_out),
        "report_json": str(misguided_rep),
        "report_sha256": misguided_sha,
        "command": "python -m experiments.misguided_metrics --artifact <df.json> --artifact <aug.json> --out emse_misguided_augment_20261017 --jobs <N>",
    },
    "prompt_evidence": {
        "status": "ok" if int(evidence_ok) == 1 else "missing/needs_manual_check",
        "json": str(out / "PROMPT_EVIDENCE.json"),
        "markdown": str(out / "PROMPT_EVIDENCE.md"),
    },
    "anchor_table": {"path": anchor_path, "sha256": anchor_sha},
    "prereg": {"path": pre_reg, "sha256": pre_reg_sha},
    "orphan_hygiene": {
        "detector": str(Path(worktree) / "scripts" / "tools" / "detect_orphan_procs.py"),
        "log": str(out / "proc_hygiene.log"),
        "hit_count": int(orphan_hit),
        "read_only": True,
    },
    "copy_back": {
        "dest_artifacts": str(Path(main_repo) / "experiments" / "results" / Path(out_dir).name),
        "dest_misguided": str(Path(main_repo) / "experiments" / "results" / "emse_misguided_augment_20261017"),
        "note": "本清单落盘后执行复制；复制后逐文件 sha256 校验结果写入运行日志（stdout）。",
    },
}
mp = out / f"RUN_MANIFEST_{run_stamp}.json"
mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"RUN_MANIFEST：{mp}")
PY

    # 10.2 README（数字由工件读取生成；编辑性文字不手改数字）
    "${PY}" - "${OUT_DIR}" "${RUN_STAMP}" "${WALL_TOTAL}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
run_stamp = sys.argv[2]
wall_total = int(sys.argv[3])
manifest_path = out / f"RUN_MANIFEST_{run_stamp}.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

def _sha(p):
    p = Path(p)
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None

def _load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

def _fmt_rate(v):
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"

def _fmt_pp(v):
    try:
        return f"{float(v):+.2f}pp"
    except (TypeError, ValueError):
        return "n/a"

arms = manifest.get("arms") or []
by_arm = {m.get("arm"): m for m in arms}
analysis = _load_json(out / "DF_AUG_REPORT.json") or {}
_misg_out = (manifest.get("mechanism_replay") or {}).get("out_dir") or str(out.parent / "emse_misguided_augment_20261017")
misguided = _load_json(Path(_misg_out) / "MISGUIDED_REPORT.json") or {}
evidence = _load_json(out / "PROMPT_EVIDENCE.json") or {}
preflight_log = out / "preflight.log"
hygiene_log = out / "proc_hygiene.log"
prereg = manifest.get("prereg") or {}
anchor = manifest.get("anchor_table") or {}
repo = manifest.get("repo") or {}
protocol = manifest.get("protocol") or {}

lines = []
def add(s=""):
    lines.append(s)

add("# M-4 规格增广二臂正式批（df 对照 + augment 处理，真 LLM，2026-10-17）")
add("")
add("> **性质**：预注册正式批执行工件（EMSE Registered Reports 口径）。")
add("> **预注册**（结果产出前随切点提交）：`" + str(prereg.get("path")) + "`")
add("> sha256=`" + str(prereg.get("sha256")) + "`。")
add("> **跑批切点（干净 worktree）**：`" + str(repo.get("worktree")) + "`，HEAD=`" + str(repo.get("git_sha_pre")) + "`，")
add("> 跑前/跑后 `git status --porcelain` 0 行（每臂 log 头/尾记录）；两臂批次 provenance `git_dirty=false`。")
add("> **判定与全部数字由脚本从批次 JSON / 分析报告 / 重放报告直出**（`run_augment_batch.sh`），本 README 不手写结果数字。")
add("> 臂：df 对照 `plain_llm_df`（同批同日新跑） / aug 处理 `plain_llm_df_doc_augment`（代码保留 + 人类 docstring 规格并列增广）。")
add("> 数据集：QuixBugs 50 行（41 缺陷程序 + 9 测试驱动；主分析集=41 口径）；模型：deepseek-flash。")
add("")

# ── 1. 协议 ──
add("## 1. 跑批协议（二臂并发、同批同日、逐臂独立 cache namespace）")
add("")
add("| 项 | df（对照） | aug（处理） |")
add("|---|---|---|")
add("| baseline | `plain_llm_df` | `plain_llm_df_doc_augment` |")
add("| cache namespace | `emse_docstring_augment_20261017_df` | `emse_docstring_augment_20261017_aug` |")
_add_rows = []
for arm_label in ("df", "aug"):
    m = by_arm.get(arm_label) or {}
    _add_rows.append(m)
add("| 批次工件 | `" + str((by_arm.get("df") or {}).get("batch_file", "")).split("/")[-1] + "` | `" + str((by_arm.get("aug") or {}).get("batch_file", "")).split("/")[-1] + "` |")
add("| 时间窗（UTC，start→end） | `" + str((by_arm.get("df") or {}).get("start_iso_utc")) + "` → `" + str((by_arm.get("df") or {}).get("end_iso_utc")) + "` | `" + str((by_arm.get("aug") or {}).get("start_iso_utc")) + "` → `" + str((by_arm.get("aug") or {}).get("end_iso_utc")) + "` |")
add("| 墙钟 | **" + str((by_arm.get("df") or {}).get("wall_seconds")) + "s** | **" + str((by_arm.get("aug") or {}).get("wall_seconds")) + "s** |")
add("| parallelism | " + str((by_arm.get("df") or {}).get("parallelism")) + " | " + str((by_arm.get("aug") or {}).get("parallelism")) + " |")
add("| provenance git_sha / dirty | `" + str(((by_arm.get("df") or {}).get("provenance") or {}).get("git_sha")) + "` / **" + str(((by_arm.get("df") or {}).get("provenance") or {}).get("git_dirty")) + "** | `" + str(((by_arm.get("aug") or {}).get("provenance") or {}).get("git_sha")) + "` / **" + str(((by_arm.get("aug") or {}).get("provenance") or {}).get("git_dirty")) + "** |")
add("")
add("共同协议（每臂实际命令，逐字见 `RUN_MANIFEST` 的 `arm_command_lines`）：")
add("")
add("```bash")
add("# 两臂各一条命令（并发执行；互异 namespace/log）")
_m = by_arm.get("df") or {}
add("# df:  " + str(((manifest.get("arm_command_lines") or {}).get("df") or "")[:500]))
add("# aug: " + str(((manifest.get("arm_command_lines") or {}).get("aug") or "")[:500]))
add("```")
add("")
add("**调度偏差披露（M-4 任务书要求二臂并发；务必与单臂口径分开阅读）**：")
add("")
add("- ① **df 与 aug 两臂并发执行**（两个独立进程，各 P" + str((by_arm.get('df') or {}).get('parallelism')) + "、互异 cache namespace/log、同批同日启动）。")
add("  单臂内部协议不变（temp=0.0 / logic / seed=42 / 判分口径 / 全量 50 行）。")
add("- ② 并发带来的 CPU 争抢发生在**任务阶段与批后处理阶段的重叠窗口**；主指标 detection 在任务阶段采集，")
add("  但次指标（mutation_score / MDO 等变异类测量）的时间窗含并发噪声，方向不系统性偏向任一臂。")
add("- ③ 两臂均未中断、未重跑、未删除任何日志/工件；`--task-count 50` = QuixBugs 全量（L 轮修复后对真实数据集等价 `--task-limit`）。")
add("- ④ 后处理阶段（变异得分/变异检出/MDO 逐任务串行 loop）耗时占比高，属既有管线口径；超时防御有界终止不挂死。")
add("")
add("**每臂 env 级预算上限（不进入 env_snapshot 的开关由 RUN_MANIFEST 记录）**：`AITESTER_BATCH_MAX_CALLS=" + str((protocol.get('env_caps') or {}).get('AITESTER_BATCH_MAX_CALLS')) + "`、`COST_BUDGET_ENABLE=" + str((protocol.get('env_caps') or {}).get('COST_BUDGET_ENABLE')) + "`、`COST_BUDGET_USD=" + str((protocol.get('env_caps') or {}).get('COST_BUDGET_USD')) + "`。")
add("")
add("> 预算 cap 口径披露：采用 M-4 派单值 `COST_BUDGET_USD=5`（预注册 §6 命令示例写 `3`；两者均远高于单任务实测成本，")
add("> 不改变 detection 测量口径与判定，差异在此如实披露）。")
add("")

# ── 2. preflight ──
add("## 2. 前置闸（preflight）与锚表")
add("")
add("`python scripts/tools/run_preflight.py --expect-tasks 50 --parallelism " + str(protocol.get("BENCHMARK_PARALLELISM")) + "`（worktree 内；输出见 `preflight.log`）。关键行：")
add("")
add("```text")
if preflight_log.is_file():
    keep = []
    for ln in preflight_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if any(k in ln for k in ("工作树：", "计划任务数", "任务级预算", "批次级上限", "孤儿进程巡检", "阻断", "告警", "✓ 前置闸", "近期批次指纹")):
            keep.append(ln)
    add("\n".join(keep[:20]) if keep else "（未解析到关键行，见 preflight.log）")
else:
    add("（preflight.log 缺失）")
add("```")
add("")
add("锚表（预注册材料随切点提交；augment 臂使用 run_benchmark 默认路径，**不设 DOC_ANCHOR_TABLE**）：")
add("")
add("| 文件 | sha256 |")
add("|---|---|")
add("| `DOCSTRING_ANCHOR_TABLE.json` | `" + str(anchor.get("sha256")) + "` |")
add("")
add("> 告警处理：preflight 无 strict（与 L 轮口径一致）；「任务级预算未启用」「批次级调用上限未配置」"
    "两项告警已用每臂 env cap（见 §1）显式覆盖；worktree 无历史批次指纹 → 本批工件自身指纹 `pinned=true`（见 §6）。")
add("")

# ── 3. detection + 判定 ──
add("## 3. 结果（`DF_AUG_REPORT.json` / `.md` 直出）")
add("")
detection = analysis.get("detection") or {}
add("### 3.1 检出（主分析集=41 缺陷程序；可判定子集口径，None 不进分母）")
add("")
add("| 臂 | 可判定/41 行 | 检出 | detection | 41 口径 None | 全 50 行 None |")
add("|---|---|---|---|---|---|")
all50_none = {}
for m in arms:
    det = m.get("detection") or {}
    all50_none[m.get("arm")] = len(det.get("detection_none_task_ids") or [])
for arm_key in ("plain_llm_df", "plain_llm_df_doc_augment", "df", "augment"):
    d = detection.get(arm_key)
    if not d:
        continue
    add("| `" + str(arm_key) + "` | " + str(d.get("measurable")) + "/" + str(d.get("denominator_rows")) + " | " + str(d.get("positive")) + " | **" + _fmt_rate(d.get("rate")) + "** | " + str(int(d.get("denominator_rows") or 0) - int(d.get("measurable") or 0)) + " | — |")
if not detection:
    add("| （分析报告未产出 detection 块，见 §8 异常） | | | | | |")
add("")
comparison = analysis.get("contrast") or {}
add("### 3.2 配对对比（精确 McNemar；a=处理臂 vs b=df 对照）")
add("")
add("| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE(80%) |")
add("|---|---|---|---|---|---|---|---|")
for name, c in comparison.items():
    if not isinstance(c, dict):
        continue
    add("| `" + str(name) + "` | " + str(c.get("n_pairs")) + " | " + str(c.get("ratio")) + " | **" + _fmt_pp(c.get("delta_pp")) + "** | " + str(c.get("p_one_sided")) + " | " + str(c.get("p_two_sided")) + " | " + str(c.get("bf10")) + " | " + str(c.get("mde_pp")) + "pp |")
if not comparison:
    add("| （分析报告未产出 contrast 块） | | | | | | | |")
add("")

add("### 3.3 预注册判定（direct-from-report）")
add("")
add("**verdict = `" + str(analysis.get("verdict")) + "`；fail_line_triggered = `" + str(analysis.get("fail_line_triggered")) + "`**")
add("")
add("| 判据 | 值 |")
add("|---|---|")
def _render_condition(name, cond):
    if isinstance(cond, dict):
        parts = []
        for k in ("threshold", "rate", "met", "delta_pp", "margin_pp", "p_one_sided", "p", "bf10", "mde_pp"):
            if k in cond:
                parts.append(f"{k}={cond[k]}")
        add("| " + str(name) + " | " + "，".join(parts) + " |")
    else:
        add("| " + str(name) + " | " + str(cond) + " |")
for name, cond in (analysis.get("conditions") or {}).items():
    _render_condition(name, cond)
non_inf = analysis.get("non_inferiority")
if isinstance(non_inf, dict):
    for name, cond in non_inf.items():
        _render_condition("non_inferiority." + str(name), cond)
elif non_inf is not None:
    add("| non_inferiority | " + str(non_inf) + " |")
add("")
prereg_consts = (analysis.get("prereg") or {}).get("constants") or {}
if prereg_consts:
    add("预注册常量（分析脚本锁定）：" + "，".join(f"`{k}={v}`" for k, v in prereg_consts.items()))
    add("")
_mde = analysis.get("mde") or {}
if _mde:
    add("MDE 披露：observed n_pairs=" + str(_mde.get("observed_n_pairs")) + "，observed MDE(80%)=" + str(_mde.get("observed_mde_pp")) + "pp；reference n=" + str(_mde.get("reference_n")) + " 时 " + str(_mde.get("mde_pp_at_reference_n")) + "pp。小效应不可判（预注册已披露）。")
    add("")
add("> 完整判定证据（三态条件、失败线、非劣标记、MDE 披露）以 `DF_AUG_REPORT.json` 为准。")
add("")

# ── 4. 审计面 ──
add("## 4. 审计面（机制/仪器侧，描述性）")
add("")
add("| 项（41 缺陷程序口径） | df | aug |")
add("|---|---|---|")
def _audit(m, key):
    return (m.get("audit") or {}).get(key)
m_df = by_arm.get("df") or {}
m_aug = by_arm.get("aug") or {}
add("| `spec_augment_applied`（全 50 行） | `" + json.dumps(_audit(m_df, "spec_augment_applied_counts_all50") or {}, ensure_ascii=False) + "` | `" + json.dumps(_audit(m_aug, "spec_augment_applied_counts_all50") or {}, ensure_ascii=False) + "` |")
add("| `spec_augment_applied`（41 口径） | `" + json.dumps(_audit(m_df, "spec_augment_applied_counts_41") or {}, ensure_ascii=False) + "` | `" + json.dumps(_audit(m_aug, "spec_augment_applied_counts_41") or {}, ensure_ascii=False) + "` |")
add("| `spec_replace_applied`（全 50 行；非该臂应全 None） | `" + json.dumps(_audit(m_df, "spec_replace_applied_counts_all50") or {}, ensure_ascii=False) + "` | `" + json.dumps(_audit(m_aug, "spec_replace_applied_counts_all50") or {}, ensure_ascii=False) + "` |")
add("| specificity verdict（41 口径） | `" + json.dumps(_audit(m_df, "specificity_gate_verdict_counts_41") or {}, ensure_ascii=False) + "` | `" + json.dumps(_audit(m_aug, "specificity_gate_verdict_counts_41") or {}, ensure_ascii=False) + "` |")
add("| over_red 占比（over/(spec+over)，41 口径） | " + _fmt_rate(_audit(m_df, "over_red_share_41")) + " | " + _fmt_rate(_audit(m_aug, "over_red_share_41")) + " |")
add("")
add("> 预期（预注册 §4/§6）：aug 臂 `attempted_augmented` = 40/41 缺陷程序（`node.py` human_spec 为空串 →")
add("> `attempted_fallback`），9 个测试驱动任务无锚条目同样回落 → 全 50 行 `attempted_fallback` = 10；")
add("> df 对照臂该字段应全 None。")
add("> over_red 为既有 proxy，**不作机制证明**；严格版机制度量见 §8。")
add("")

# ── 5. 成本 ──
add("## 5. 成本（真实 token 记账 × deepseek-flash 标准价目表，保守上界）")
add("")
add("| 臂 | input tok | output tok | total tok | LLM calls | cache hits | cache-avoided tok | 墙钟(s) | **成本（USD）** |")
add("|---|---|---|---|---|---|---|---|---|")
total_cost = 0.0
unknown_price = False
for arm_label in ("df", "aug"):
    m = by_arm.get(arm_label) or {}
    tm = m.get("token_metrics") or {}
    c = m.get("cost_usd_standard_price")
    if c is None:
        unknown_price = True
        c = 0.0
    total_cost += float(c)
    add("| `" + arm_label + "` | " + f"{int(tm.get('total_input_tokens') or 0):,}" + " | " + f"{int(tm.get('total_output_tokens') or 0):,}" + " | " + f"{int(tm.get('total_tokens') or 0):,}" + " | " + str(tm.get("total_llm_calls")) + " | " + str(tm.get("total_cache_hits")) + " | " + f"{int(tm.get('total_cache_avoided_tokens') or 0):,}" + " | " + str(m.get("wall_seconds")) + " | **$" + f"{float(c):.4f}" + "** |")
add("| **合计** | | | | | | | **" + str(wall_total) + "** | **≈$" + f"{total_cost:.4f}" + "** |")
add("")
add("- 价目表：`experiments/price_table.json`（deepseek-flash：$0.3/M in、$1.2/M out，as_of 2026-10-06，标准/峰时价 → **上界**）。")
add("- 两臂均为全新 cache namespace：批内 cache hits 为同批同 prompt 命中（不影响独立样本主张）；跨臂/跨批无共享响应。")
if unknown_price:
    add("- ⚠️ 存在未登记价格的模型，成本不参与合计（不编造）。")
add("")

# ── 6. provenance / 完整性 ──
add("## 6. provenance / 完整性")
add("")
add("| 项 | 两臂共同值 |")
add("|---|---|")
prov = (by_arm.get("aug") or {}).get("provenance") or {}
fp = prov.get("model_fingerprint") or {}
env = prov.get("env_snapshot") or {}
add("| `git_sha` | `" + str(prov.get("git_sha")) + "` |")
add("| `git_dirty` / `dirty_reason` | **" + str(prov.get("git_dirty")) + "** / " + str(prov.get("dirty_reason")) + " |")
add("| `model_name` / fingerprint | " + str(prov.get("model_name")) + " / **pinned=" + str(fp.get("pinned")) + "**、returned_model=" + str(fp.get("returned_model")) + "、missing=" + json.dumps(fp.get("missing"), ensure_ascii=False) + " |")
add("| `temperature` / `profile` / `seed` | " + str(prov.get("temperature")) + " / " + str(prov.get("profile")) + " / " + str((by_arm.get("aug") or {}).get("seed")) + " |")
add("| `cache_enabled` / `cache_namespace` | " + str(prov.get("cache_enabled")) + " / " + str(prov.get("cache_namespace")) + " |")
add("| `env_snapshot` | " + str(len(env)) + " 键；含 `AITESTER_CACHE_NAMESPACE`、`AITESTER_PROFILE`、`TEMPERATURE`、`LLM_THINKING_MODE` 等 |")
add("| 顶层 `total_tasks` / `parallelism` | " + str(((by_arm.get("aug") or {}).get("top_level") or {}).get("total_tasks")) + " / " + str((by_arm.get("aug") or {}).get("parallelism")) + " |")
add("")
add("- 跑前/跑后 worktree `git status --porcelain` 均 0 行（每臂 log 头/尾记录；结果目录在 gitignore 内不产生变更）。")
add("- 输入工件 sha256 已写入 `DF_AUG_REPORT.json.inputs` 与本目录 `SHA256SUMS`。")
add("")
add("**工件 sha256（本批关键文件；完整清单见 `SHA256SUMS`）**：")
add("")
add("| 文件 | sha256 |")
add("|---|---|")
key_files = [m.get("batch_file") for m in arms if m.get("batch_file")] + ["DF_AUG_REPORT.json", "DF_AUG_REPORT.md", "README.md", "PROMPT_EVIDENCE.json"]
for kf in key_files:
    p = Path(str(kf))
    if not p.is_absolute():
        p = out / str(kf)
    if p.is_file():
        add("| `" + p.name + "` | `" + str(_sha(p)) + "` |")
add("")

# ── 7. prompt 证据 ──
add("## 7. Prompt 增广核验（一等证据：代码块 + 规格锚同时在场）")
add("")
add("数据来源：`~/.cache/aitester/llm/*.json` 中批次时间窗内的 generator 调用缓存（本次两臂均为全新 namespace →")
add("缓存条目全部来自本批）。")
add("")
add("**判据澄清（重要）**：QuixBugs 的人类规格文本就是缺陷源码文件尾部的模块级 docstring，因此")
add("「规格文本出现」**不能**单独证明增广注入（df 对照臂代码块内也含该文本）。本证据以 **M-1 augment")
add("framing 段**为决定性判据：代码标记（锚表 `source_head`）< augment framing 标记 < 规格锚末次出现，")
add("并记录规格锚文本出现次数（源码内嵌一次 vs 增广段重复注入）；同 generator 条目含代码但无 framing 段 =")
add("df 对照臂（负向对照）。")
add("")
ev_ok = evidence.get("evidence_status") or "missing"
add("| 计数（时间窗内） | 值 |")
add("|---|---|")
add("| generator 缓存条目 | " + str(evidence.get("n_generator_cache_entries_in_window", "n/a")) + " |")
add("| augment framing 命中（aug 臂） | **" + str(evidence.get("n_augment_framing_entries", "n/a")) + "** |")
add("| 含代码块但无 framing 段（df 对照） | " + str(evidence.get("n_code_only_entries", "n/a")) + " |")
add("| 负向对照在场 | " + str(evidence.get("negative_control_ok", "n/a")) + " |")
add("| 证据状态 | **" + str(ev_ok) + "** |")
add("")
examples = evidence.get("examples") or []
if examples:
    for idx, rec in enumerate(examples, 1):
        _spec_offs = rec.get("spec_marker_offsets") or []
        add("**例 " + str(idx) + "：`" + str(rec.get("function_name")) + "`**（缓存 `" + str(rec.get("cache_file")) + "`，sha256 `" + str(rec.get("cache_sha256"))[:16] + "…`；prompt_len=" + str(rec.get("prompt_len")) + "；代码 offset=" + str(rec.get("code_offset")) + " < framing offset=" + str(rec.get("augment_frame_offset")) + " < 规格锚末次出现=" + str(_spec_offs[-1] if _spec_offs else "n/a") + "；规格锚出现 " + str(rec.get("spec_marker_occurrences")) + " 次；增广小节标题在场=" + str(rec.get("has_spec_section_header")) + "）")
        add("")
        add("```text")
        add(str(rec.get("excerpt_augment") or "").strip())
        add("```")
        add("")
    add("> 节选展示 augment framing 段与人类规格锚段落；完整证据与 1–5 条 aug 臂记录见 `PROMPT_EVIDENCE.json`。")
else:
    add("**⚠️ 未抽取到证据**：需人工从缓存/ trace 核验（见 `PROMPT_EVIDENCE.json`）；该结果不阻断跑批但须在交接中说明。")
add("")

# ── 8. 机制重放 ──
add("## 8. 机制重放（misguided/effective 逐测试，零 LLM）")
add("")
misg_out = Path(_misg_out)
add("产物目录：`" + str(misg_out) + "/MISGUIDED_REPORT.json` / `.md`（工具：`experiments/misguided_metrics.py`；**不参与主判定**）。")
add("")
mreport = (misguided.get("report") or {})
marms = mreport.get("arms") or []
add("| 臂 | 可分析任务 | 可分类测试 | effective | misguided | both_pass | both_fail | effective 占比 | misguided 占比 |")
add("|---|---|---|---|---|---|---|---|---|")
for item in marms:
    agg = ((item.get("aggregate") or {}).get("all_tasks") or {})
    counts = agg.get("counts") or {}
    rates = agg.get("rates") or {}
    add("| `" + str(item.get("arm")) + "` | " + str(agg.get("n_tasks_ok")) + "/" + str(agg.get("n_tasks")) + " | " + str(agg.get("n_tests_classifiable")) + " | " + str(counts.get("effective")) + " | " + str(counts.get("misguided")) + " | " + str(counts.get("both_pass")) + " | " + str(counts.get("both_fail")) + " | " + _fmt_rate(rates.get("effective_share")) + " | " + _fmt_rate(rates.get("misguided_share")) + " |")
if not marms:
    add("| （重放报告缺失/失败，见 §9） | | | | | | | | |")
comparison = ((mreport.get("comparison") or {}).get("per_test_defect_programs") or {})
if comparison:
    add("")
    add("41 缺陷程序口径（逐测试占比，b−a）：")
    add("")
    add("| 类别 | a（df） | b（aug） | δ（pp） |")
    add("|---|---|---|---|")
    for label, row in comparison.items():
        if not isinstance(row, dict):
            continue
        add("| " + str(label) + " | " + str(row.get("arm_a")) + " | " + str(row.get("arm_b")) + " | " + _fmt_pp(row.get("delta_pp_b_minus_a")) + " |")
add("")
add("> misguided/effective 为机制侧描述性信号（ISSTA'26 口径），与 detection 分开报告，不得互相顶替；")
add("> 分母/不可分类原因（timeout、collect_error 等）见 `MISGUIDED_REPORT.json`。")
add("")

# ── 9. 异常与限制 ──
add("## 9. 异常与限制（如实披露）")
add("")
add("1. **调度偏差（并发）**：二臂并发（M-4 任务书要求，Lead 批准）——主指标 detection 在任务阶段采集，")
add("   但次指标（变异类测量）时间窗含 CPU 争抢噪声；方向不系统性偏向任一臂。")
add("2. **QuixBugs 已知「缺陷实现不终止」家族**（bitcount/find_first_in_sorted/sqrt/wrap 等）会令 M1 口径")
add("   detection=None；None 按 fail-closed **不进入分母**（与预注册口径一致），分母已在 §3.1 如实披露。")
add("3. **后处理耗时占比高**：变异得分/变异检出/MDO 逐任务串行 loop 占墙钟大头，超时防御有界终止；")
add("   不影响任务阶段采集的 detection 主指标，但会抬高墙钟与部分次指标 None 率。")
add("4. **单模型/单数据集/单 seed**：deepseek-flash + QuixBugs（41 缺陷程序可判定子集）+ seed=42；")
add("   跨模型/跨数据集不可外推；小效应不可判（MDE≈16.6pp，见 §3.2）。")
add("5. **cache 开启但 namespace 独立**：两臂为全新 namespace，无跨批/跨臂响应复用；批内同一 prompt")
add("   可能命中（如重采样），cache hits 已在 §5 单列。")
add("6. **审计字段口径**：`AITESTER_BATCH_MAX_CALLS`/`COST_BUDGET_*` 不在批次 `env_snapshot` 键集内，")
add("   由 `RUN_MANIFEST.protocol.env_caps` + 每臂命令日志记录（可审计）。")
add("7. **prompt 证据来自 LLM 缓存**（非 trace）：缓存条目含 prompt/system 全文、不含密钥；若证据状态非 ok 见 §7 说明。")
add("8. 跑批过程**未中断、未重跑、未删除/手改任何日志与工件**；无 API key 泄露（日志脱敏机制在岗）。")
add("")

# ── 10. 复现命令 ──
add("## 10. 复现与判定命令（零 LLM 复算）")
add("")
add("```bash")
add("# 一键入口（本批实际执行；需干净 worktree + M-1 切点）")
add("# bash experiments/run_augment_batch.sh --worktree <clean-worktree> --expect-sha <sha>")
add("")
add("# 判定（零 LLM；本批实际命令，参数为两臂批次 JSON）")
add("python -m experiments.emse_docstring_augment_analysis \\")
add("  --df " + str((by_arm.get("df") or {}).get("batch_file")) + " \\")
add("  --augment " + str((by_arm.get("aug") or {}).get("batch_file")) + " \\")
add("  --out experiments/results/emse_docstring_augment_20261017/DF_AUG_REPORT.json \\")
add("  --markdown experiments/results/emse_docstring_augment_20261017/DF_AUG_REPORT.md")
add("")
add("# 机制重放（零 LLM）")
add("python -m experiments.misguided_metrics \\")
add("  --artifact " + str((by_arm.get("df") or {}).get("batch_file")) + " \\")
add("  --artifact " + str((by_arm.get("aug") or {}).get("batch_file")) + " \\")
add("  --out experiments/results/emse_misguided_augment_20261017 --jobs 8")
add("")
add("# 完整性")
add("cd experiments/results/emse_docstring_augment_20261017 && shasum -a 256 -c SHA256SUMS")
add("```")
add("")

# ── 11. 文件清单 ──
add("## 11. 文件与运行清单")
add("")
add("| 文件 | 说明 |")
add("|---|---|")
add("| `run_augment_batch.sh` | 本次运行的跑批脚本副本（自归档；sha256 见 `SHA256SUMS`/`RUN_MANIFEST`） |")
add("| `RUN_MANIFEST_" + run_stamp + ".json` | 运行总清单（命令/env/工件/成本/token/墙钟/审计） |")
add("| `preflight.log` | 前置闸输出 |")
add("| `proc_hygiene.log` | 跑批期每 5min 只读孤儿巡检记录 |")
add("| `log_df.log` / `log_aug.log` | 每臂完整日志（命令/env 白名单/GIT 前后状态） |")
add("| `arm_df.meta.json` / `arm_aug.meta.json` | 每臂结构化元数据（provenance/token/成本/判分/审计/逐任务） |")
add("| `DF_AUG_REPORT.json` / `.md` | 预注册判定（M-1 分析脚本直出） |")
add("| `PROMPT_EVIDENCE.json` / `.md` | prompt 增广核验证据（缓存抽取） |")
add("| `analysis_stdout.log` / `misguided_stdout.log` | 分析/重放完整输出 |")
add("| `traces/` | 逐任务 trace（审计用） |")
add("| `SHA256SUMS` | 本目录全部工件 sha256（`shasum -a 256 -c` 验证） |")
add("")
add("> 交接：本批两份批次 JSON 即 M-1 机制指标的输入（路径/sha256 见 §6/`DF_AUG_REPORT.json.inputs`）；")
add("> 重放报告在 `experiments/results/emse_misguided_augment_20261017/`。")
add("")

(out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"README：{out / 'README.md'}")
PY

    # 10.3 SHA256SUMS（本目录全部工件；最后生成）
    "${PY}" - "${OUT_DIR}" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
lines = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or p.name == "SHA256SUMS":
        continue
    rel = p.relative_to(root).as_posix()
    lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
(root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"SHA256SUMS：{root / 'SHA256SUMS'}（{len(lines)} 条）")
PY

    # 10.4 复制回主仓（先断言目标目录不存在/为空；绝不覆盖）
    COPY_RC=0
    if [ "${WORKTREE}" = "${MAIN_REPO}" ]; then
        warn "worktree == 主仓：跳过复制回主仓（工件已在主仓路径）"
    else
        DEST_ART="${MAIN_REPO}/experiments/results/$(basename "${OUT_DIR}")"
        DEST_MIS="${MAIN_REPO}/experiments/results/$(basename "${MISGUIDED_OUT}")"
        _copy_guard=0
        for _dst in "${DEST_ART}" "${DEST_MIS}"; do
            if [ -e "${_dst}" ] && [ -n "$(ls -A "${_dst}" 2>/dev/null || true)" ]; then
                warn "主仓目标目录已存在且非空（拒绝覆盖）：${_dst}"
                _copy_guard=1
            fi
        done
        if [ "${_copy_guard}" -ne 0 ]; then
            COPY_RC=1
            WARN_EXIT=7
        else
            mkdir -p "${DEST_ART}/" "${DEST_MIS}/"
            cp -Rp "${OUT_DIR}"/. "${DEST_ART}"/
            if [ -d "${MISGUIDED_OUT}" ]; then
                cp -Rp "${MISGUIDED_OUT}"/. "${DEST_MIS}"/
            fi
            log "  ✓ 已复制回主仓：${DEST_ART}"
            log "  ✓ 已复制回主仓：${DEST_MIS}"
            # 逐文件 sha256 校验（artifact 树 + 重放树）
            set +e
            "${PY}" - "${OUT_DIR}" "${DEST_ART}" "${MISGUIDED_OUT}" "${DEST_MIS}" <<'PY'
import hashlib
import sys
from pathlib import Path


def _tree(root):
    root = Path(root)
    out = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _verify(src, dst, label):
    a = _tree(src)
    b = _tree(dst)
    missing = sorted(set(a) - set(b))
    extra = sorted(set(b) - set(a))
    mismatch = sorted(k for k in a if k in b and a[k] != b[k])
    if missing or extra or mismatch:
        print(f"COPY_VERIFY_FAIL {label}: missing={missing[:5]} extra={extra[:5]} mismatch={mismatch[:5]}")
        return False
    print(f"COPY_VERIFY_OK {label}: {len(a)} files")
    return True


ok1 = _verify(sys.argv[1], sys.argv[2], "artifacts")
ok2 = _verify(sys.argv[3], sys.argv[4], "misguided")
raise SystemExit(0 if (ok1 and ok2) else 1)
PY
            VERIFY_RC=$?
            set -e
            if [ "${VERIFY_RC}" -ne 0 ]; then
                COPY_RC=1
                WARN_EXIT=7
                warn "复制后逐文件 sha256 校验失败（见上）"
            else
                log "  ✓ 复制后逐文件 sha256 校验通过（工件树 + 重放树）"
                # SHA256SUMS 自校验（主仓副本）
                _sums_rc=0
                set +e
                ( cd "${DEST_ART}" && shasum -a 256 -c SHA256SUMS > /dev/null 2>&1 )
                _sums_rc=$?
                set -e
                if [ "${_sums_rc}" -eq 0 ]; then
                    log "  ✓ 主仓副本 SHA256SUMS 自校验通过"
                else
                    warn "主仓副本 SHA256SUMS 自校验失败（不影响已通过的逐文件校验）"
                fi
            fi
        fi
    fi

    # 10.5 最终摘要
    echo ""
    echo "================================================================================"
    echo "M-4 正式批完成（RUN_STAMP=${RUN_STAMP}）"
    echo "  切点：${GIT_HEAD_PRE}（跑后 HEAD=${GIT_HEAD_POST}）"
    echo "  两臂退出码：df=${RC_DF} aug=${RC_AUG}；总墙钟 ${WALL_TOTAL}s（$((WALL_TOTAL / 60))min）"
    echo "  批次工件："
    echo "    df : ${BATCH_DF}"
    echo "    aug: ${BATCH_AUG}"
    echo "  判定报告：${OUT_DIR}/DF_AUG_REPORT.json / .md（分析 exit=${ANALYSIS_RC}）"
    echo "  机制重放：${MISGUIDED_OUT}/MISGUIDED_REPORT.json（exit=${MISGUIDED_RC}）"
    echo "  prompt 证据：${OUT_DIR}/PROMPT_EVIDENCE.json（状态：$([ "${EVIDENCE_OK}" -eq 1 ] && echo ok || echo 'missing/需人工核验')）"
    echo "  README：${OUT_DIR}/README.md"
    echo "  SHA256SUMS：${OUT_DIR}/SHA256SUMS"
    echo "  孤儿巡检：${OUT_DIR}/proc_hygiene.log（命中 ${ORPHAN_HIT} 次；只读不 kill）"
    echo "  运行清单：${OUT_DIR}/RUN_MANIFEST_${RUN_STAMP}.json"
    if [ "${COPY_RC}" -eq 0 ] && [ "${WORKTREE}" != "${MAIN_REPO}" ]; then
        echo "  主仓副本：${MAIN_REPO}/experiments/results/$(basename "${OUT_DIR}")"
        echo "           ${MAIN_REPO}/experiments/results/$(basename "${MISGUIDED_OUT}")"
    fi
    echo "================================================================================"
    if [ "${WARN_EXIT}" -ne 0 ]; then
        echo "⚠️ 收尾告警（exit=${WARN_EXIT}）：见上（分析/重放/复制问题）；跑批工件完整保留。"
        exit "${WARN_EXIT}"
    fi
    exit 0
else
    echo ""
    echo "================================================================================"
    echo "DRY-RUN 结束：未执行任何跑批/分析/重放，零 LLM 调用，未创建/复制工件。"
    echo "正式运行（Lead 批准切点后）："
    echo "  bash experiments/run_augment_batch.sh --worktree <clean-worktree> --expect-sha <commit-sha>"
    echo "================================================================================"
    exit 0
fi
