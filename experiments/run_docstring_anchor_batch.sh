#!/usr/bin/env bash
# =============================================================================
# P1 docstring 锚三臂正式批跑批脚本（L 轮 T5 可复现入口；2026-10-17）
#
# 用途：在**干净树**上顺序执行三臂（df 对照 → df_doc → df_doc_union），
#       每臂独立 AITESTER_CACHE_NAMESPACE、同 seed/判分口径；跑完调用 T1
#       分析脚本直出预注册判定（三态 verdict），并打印成本/墙钟汇总。
#       本脚本**不自己执行正式批**：由操作者在 Lead 批准后运行（T5）。
#
# 协议（T5 / 预注册 docs/emse/EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md）：
#   AITESTER_PROFILE=logic / TEMPERATURE=0.0 / LLM_THINKING_MODE=disabled /
#   BENCHMARK_PARALLELISM=4（可调但记录）/ seed=42 / QuixBugs 50 任务 /
#   三臂互异 cache namespace / provenance 必须 git_dirty=false。
#
# 用法：
#   bash experiments/run_docstring_anchor_batch.sh --dry-run
#   bash experiments/run_docstring_anchor_batch.sh
#   bash experiments/run_docstring_anchor_batch.sh --parallelism 2 --check-quota
#
# 选项（--help 查看全部）：
#   --parallelism N          BENCHMARK_PARALLELISM（默认 4，T5 协议值；实际值入 manifest）
#   --task-count N           计划任务数（默认 50；见下方 KNOWN BUG——仅用于前置闸估算与记录）
#   --seed N                 随机种子（默认 42）
#   --output-dir DIR         输出目录（默认 experiments/results/emse_docstring_anchor_20261017）
#   --arms LIST              逗号分隔臂列表（默认 df,doc,union）
#   --analysis-script PATH   T1 分析脚本（默认 experiments/emse_docstring_anchor_analysis.py；
#                            以 `python -m experiments.emse_docstring_anchor_analysis` 调用，
#                            CLI 约定：--df/--doc/[--union]/--out/--markdown）
#   --allow-dirty            仅调试：豁免干净树门禁（provenance 记 git_dirty=true；正式批禁止）
#   --dirty-reason STR       与 --allow-dirty 配套（必填；写入 provenance.dirty_reason）
#   --skip-preflight         跳过前置闸（不推荐；干净树检查仍强制执行，除非 --allow-dirty）
#   --build-anchor-tables    缺失时先跑零 LLM 锚表构建（默认：表缺失即失败并给命令）
#   --check-quota            前置闸追加一次最小 LLM 探测（消耗 1 次调用）
#   --skip-analysis          只跑批，不调分析脚本（判定可事后单独跑，命令会打印）
#   --dry-run                只打印将执行的命令/当前检查结果，不执行任何跑批
#   -h, --help               本帮助
#
# KNOWN BUG（T4 真实 LLM pilot 实测 2026-10-17）：`run_main_batch.py --task-count`
# 对非合成数据集**不生效**——它把参数透传给 run_benchmark(task_count=...)，而
# run_benchmark 的 task_count 仅用于 synthetic 数据集；真实数据集限任务数用的是
# task_limit（run_main_batch 未暴露该 CLI）。实测 `--dataset quixbugs --task-count 3`
# 仍跑满 50 任务。因此本脚本的 --task-count 仅用于前置闸任务量估算/manifest 记录；
# 三臂实际都跑 QuixBugs 全量 50 行（41 缺陷程序 + 9 测试驱动，与 T5 预注册一致）。
# **T5 不得用 --task-count <50 做"省钱小批"**——它不会生效，只会误导成本预估。
# 复现：`AITESTER_CACHE_NAMESPACE=x .venv/bin/python experiments/run_main_batch.py
#   --dataset quixbugs --task-count 3 --baselines plain_llm_df --output-dir /tmp/x
#   --skip-stats --allow-dirty --dirty-reason repro` → 进度条 0/50。
#
# 前置条件（脚本逐项检查，缺一即非零退出）：
#   1. 干净工作树（或显式 --allow-dirty --dirty-reason）；
#   2. 前置闸 `scripts/tools/run_preflight.py --strict`（配额/指纹/孤儿进程；
#      等价 `make preflight`）；
#   3. doc/union 臂锚表在场（默认锚表路径与 run_benchmark 臂默认路径一致：
#      ${OUT_DIR}/DOCSTRING_ANCHOR_TABLE.json 与 ..._UNION.json；零 LLM 构建：
#      `.venv/bin/python experiments/build_docstring_anchor_table.py [--union]`）；
#   4. run_benchmark.BASELINE_REGISTRY 已注册 plain_llm_df_doc / _union（T1 交付）；
#   5. T1 分析脚本存在（除非 --skip-analysis）。
#
# 产物（RUN_STAMP = UTC 时间戳；每次运行独立目录/文件名，**绝不覆盖既有工件**）：
#   ${OUT_DIR}/benchmark_quixbugs_<ts>.json                   三臂批次工件（run_benchmark 自带时间戳）
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/arm_<arm>.log          每臂完整日志（命令+stdout/stderr）
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/arm_<arm>.meta.json    每臂结构化元数据（provenance/token/成本/判分/逐任务）
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/preflight.log          前置闸输出
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/orphan_procs_after.json 跑后孤儿进程只读巡检（detect_orphan_procs.py）
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/RUN_MANIFEST_${RUN_STAMP}.json 本次运行总清单（命令/env/工件/token/成本/墙钟）
#   ${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.json/.md    分析脚本直出判定报告（预注册三态）
#   ${OUT_DIR}/run_artifacts_${RUN_STAMP}/SHA256SUMS            本次新增工件 + 锚表 sha256
#
# 退出码：0=成功；2=参数/前置条件失败；3=前置闸未通过；4=某臂跑批失败（日志保留）；
#         5=分析失败；6=跑批成功但收尾检查有告警（如发现孤儿进程）。
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
SCRIPT_VERSION="l-round-t4-v1"

OUT_DIR_DEFAULT="${ROOT}/experiments/results/emse_docstring_anchor_20261017"
ANALYSIS_SCRIPT_DEFAULT="${ROOT}/experiments/emse_docstring_anchor_analysis.py"
ANCHOR_BUILDER="${ROOT}/experiments/build_docstring_anchor_table.py"
PLANNER_ANCHOR_TABLE="${ROOT}/experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"

PARALLELISM="${BENCHMARK_PARALLELISM:-4}"
TASK_COUNT=50
SEED=42
OUT_DIR="${OUT_DIR_DEFAULT}"
ARMS_LIST="df,doc,union"
ANALYSIS_SCRIPT="${ANALYSIS_SCRIPT_DEFAULT}"
ALLOW_DIRTY=0
DIRTY_REASON=""
SKIP_PREFLIGHT=0
CHECK_QUOTA=0
BUILD_ANCHOR_TABLES=0
SKIP_ANALYSIS=0
DRY_RUN=0

usage() {
    # 打印文件头部连续注释块（shebang 之后、第一行非注释之前），避免正文重复
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
    exit 0
}

log() { printf '%s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }
die() {
    printf '✗ %s\n' "$*" >&2
    exit 2
}

# ─── 臂 → (baseline, cache namespace) 映射（T5 协议固定，改臂需同步预注册） ───
arm_baseline() {
    case "$1" in
        df) printf '%s' "plain_llm_df" ;;
        doc) printf '%s' "plain_llm_df_doc" ;;
        union) printf '%s' "plain_llm_df_doc_union" ;;
        *) return 1 ;;
    esac
}
arm_namespace() {
    case "$1" in
        df) printf '%s' "l_round_doca_20261017_df" ;;
        doc) printf '%s' "l_round_doca_20261017_doc" ;;
        union) printf '%s' "l_round_doca_20261017_union" ;;
        *) return 1 ;;
    esac
}
arm_anchor_table() {
    case "$1" in
        df) printf '%s' "" ;;
        doc) printf '%s' "${OUT_DIR}/DOCSTRING_ANCHOR_TABLE.json" ;;
        union) printf '%s' "${OUT_DIR}/DOCSTRING_ANCHOR_TABLE_UNION.json" ;;
        *) return 1 ;;
    esac
}

# ─── 参数解析 ────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --parallelism)
            [ $# -ge 2 ] || die "--parallelism 需要一个正整数参数"
            PARALLELISM="$2"
            shift 2
            ;;
        --task-count)
            [ $# -ge 2 ] || die "--task-count 需要一个正整数参数"
            TASK_COUNT="$2"
            shift 2
            ;;
        --seed)
            [ $# -ge 2 ] || die "--seed 需要一个整数参数"
            SEED="$2"
            shift 2
            ;;
        --output-dir)
            [ $# -ge 2 ] || die "--output-dir 需要一个目录参数"
            OUT_DIR="$2"
            shift 2
            ;;
        --arms)
            [ $# -ge 2 ] || die "--arms 需要一个逗号分隔列表"
            ARMS_LIST="$2"
            shift 2
            ;;
        --analysis-script)
            [ $# -ge 2 ] || die "--analysis-script 需要一个路径参数"
            ANALYSIS_SCRIPT="$2"
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
        --skip-preflight)
            SKIP_PREFLIGHT=1
            shift
            ;;
        --build-anchor-tables)
            BUILD_ANCHOR_TABLES=1
            shift
            ;;
        --check-quota)
            CHECK_QUOTA=1
            shift
            ;;
        --skip-analysis)
            SKIP_ANALYSIS=1
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

case "${PARALLELISM}" in '' | *[!0-9]*) die "--parallelism 必须为正整数（当前 '${PARALLELISM}'）" ;; esac
[ "${PARALLELISM}" -ge 1 ] || die "--parallelism 必须 >= 1"
case "${TASK_COUNT}" in '' | *[!0-9]*) die "--task-count 必须为正整数（当前 '${TASK_COUNT}'）" ;; esac
[ "${TASK_COUNT}" -ge 1 ] || die "--task-count 必须 >= 1"
case "${SEED}" in '' | *[!0-9]*) die "--seed 必须为非负整数（当前 '${SEED}'）" ;; esac
[ -n "${OUT_DIR}" ] || die "--output-dir 不能为空"
if [ "${ALLOW_DIRTY}" -eq 1 ]; then
    [ -n "${DIRTY_REASON}" ] || die "--allow-dirty 必须同时给 --dirty-reason '<原因>'（写入 provenance，可审计）"
fi
[ -x "${PY}" ] || die "未找到可执行 ${PY}（先在仓库根目录创建 .venv）"
[ -d "${ROOT}/experiments" ] || die "仓库根解析异常：${ROOT}"

# 臂列表 → 数组（bash 3.2：不用关联数组）
OLD_IFS="${IFS}"
IFS=','
ARM_LABELS=()
for _a in ${ARMS_LIST}; do
    [ -n "${_a}" ] && ARM_LABELS+=("${_a}")
done
IFS="${OLD_IFS}"
[ "${#ARM_LABELS[@]}" -ge 1 ] || die "--arms 为空"
SEEN_ARMS=" "
for _a in "${ARM_LABELS[@]}"; do
    arm_baseline "${_a}" >/dev/null 2>&1 || die "未知臂 '${_a}'（支持 df / doc / union）"
    case "${SEEN_ARMS}" in
        *" ${_a} "*) die "重复臂 '${_a}'" ;;
    esac
    SEEN_ARMS="${SEEN_ARMS}${_a} "
done

mkdir -p "${OUT_DIR}"
# RUN_STAMP：UTC 时间戳；同秒重跑加序号后缀（绝不覆盖既有工件）
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ART_DIR="${OUT_DIR}/run_artifacts_${RUN_STAMP}"
_n=2
while [ -e "${ART_DIR}" ]; do
    RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)-${_n}"
    ART_DIR="${OUT_DIR}/run_artifacts_${RUN_STAMP}"
    _n=$((_n + 1))
done

echo "================================================================================"
echo "P1 docstring 锚三臂正式批（${SCRIPT_VERSION}）$( [ "${DRY_RUN}" -eq 1 ] && echo '【DRY-RUN】' )"
echo "  仓库：${ROOT}"
echo "  分支/git：$(git -C "${ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?') @ $(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo '?')"
echo "  协议：AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled"
echo "        BENCHMARK_PARALLELISM=${PARALLELISM} seed=${SEED} 计划任务数=${TASK_COUNT}"
echo "  臂：${ARMS_LIST}"
echo "  输出：${OUT_DIR}"
echo "  本次 RUN_STAMP：${RUN_STAMP}"
echo "================================================================================"

# ─── 0. 干净工作树门禁 ───────────────────────────────────────────────────────
echo ""
echo "[0/6] 干净树检查"
DIRTY_LINES="$(git -C "${ROOT}" status --porcelain 2>/dev/null || true)"
if [ -n "${DIRTY_LINES}" ]; then
    if [ "${ALLOW_DIRTY}" -ne 1 ]; then
        printf '%s\n' "${DIRTY_LINES}" | head -20 >&2
        die "工作树不干净（见上）——正式批要求干净提交（provenance git_dirty=false）。
     请先由 Lead 提交/清理；如确需调试，用 --allow-dirty --dirty-reason '<原因>'。"
    fi
    if [ "${DRY_RUN}" -eq 1 ]; then
        warn "dry-run：当前工作树脏（$(printf '%s' "${DIRTY_LINES}" | wc -l | tr -d ' ') 个变更），正式跑批会被 --allow-dirty 豁免并记入 provenance"
    else
        warn "脏树豁免（--allow-dirty）：provenance 将记 git_dirty=true；原因：${DIRTY_REASON}"
    fi
else
    log "  ✓ 工作树干净（git_dirty=false）"
fi

# ─── 1. 前置闸（等价 make preflight） ────────────────────────────────────────
echo ""
echo "[1/6] 前置闸（配额/指纹/孤儿进程；等价 make preflight）"
if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  （dry-run 跳过实际前置闸；正式运行将执行：）"
    echo "  ${PY} scripts/tools/run_preflight.py --strict --expect-tasks $((TASK_COUNT * ${#ARM_LABELS[@]})) --parallelism ${PARALLELISM}$( [ "${CHECK_QUOTA}" -eq 1 ] && echo ' --check-quota' )"
elif [ "${SKIP_PREFLIGHT}" -eq 1 ]; then
    warn "跳过前置闸（--skip-preflight）——正式批不推荐；干净树检查已单独执行"
else
    mkdir -p "${ART_DIR}"
    PREFLIGHT_EXTRA=()
    if [ "${CHECK_QUOTA}" -eq 1 ]; then
        PREFLIGHT_EXTRA+=(--check-quota)
    fi
    set +e
    "${PY}" "${ROOT}/scripts/tools/run_preflight.py" --strict \
        --expect-tasks "$((TASK_COUNT * ${#ARM_LABELS[@]}))" \
        --parallelism "${PARALLELISM}" ${PREFLIGHT_EXTRA[@]+"${PREFLIGHT_EXTRA[@]}"} \
        2>&1 | tee "${ART_DIR}/preflight.log"
    PRE_RC=${PIPESTATUS[0]}
    set -e
    if [ "${PRE_RC}" -ne 0 ]; then
        die "前置闸未通过（exit ${PRE_RC}，见 ${ART_DIR}/preflight.log）——修正后重跑；
     不得用 --skip-preflight 绕过正式批门禁。"
    fi
    log "  ✓ 前置闸通过（log：${ART_DIR}/preflight.log）"
fi

# ─── 2. 锚表检查（doc / union 臂；零 LLM 构建物） ────────────────────────────
echo ""
echo "[2/6] 锚表检查（doc / union 臂）"
NEED_DOC_TABLE=0
NEED_UNION_TABLE=0
for _a in "${ARM_LABELS[@]}"; do
    case "${_a}" in
        doc) NEED_DOC_TABLE=1 ;;
        union) NEED_UNION_TABLE=1 ;;
    esac
done
if [ "${NEED_DOC_TABLE}" -eq 1 ] || [ "${NEED_UNION_TABLE}" -eq 1 ]; then
    if [ ! -d "$(dirname "${PLANNER_ANCHOR_TABLE}")" ] && [ "${NEED_UNION_TABLE}" -eq 1 ]; then
        warn "Planner 锚表目录不存在（union 臂的并集材料）：${PLANNER_ANCHOR_TABLE}"
    fi
    _need_build=0
    TABLES_TO_CHECK=()
    if [ "${NEED_DOC_TABLE}" -eq 1 ]; then
        TABLES_TO_CHECK+=("${OUT_DIR}/DOCSTRING_ANCHOR_TABLE.json")
    fi
    if [ "${NEED_UNION_TABLE}" -eq 1 ]; then
        TABLES_TO_CHECK+=("${OUT_DIR}/DOCSTRING_ANCHOR_TABLE_UNION.json")
    fi
    for _table in "${TABLES_TO_CHECK[@]}"; do
        if [ -s "${_table}" ]; then
            log "  ✓ 锚表在场：${_table}"
        else
            if [ "${BUILD_ANCHOR_TABLES}" -eq 1 ]; then
                _need_build=1
            elif [ "${DRY_RUN}" -eq 1 ]; then
                warn "dry-run：锚表缺失，正式运行会失败（或加 --build-anchor-tables）：${_table}"
            else
                die "锚表缺失：${_table}
     先运行零 LLM 构建（与臂默认路径同目录）：
       ${PY} experiments/build_docstring_anchor_table.py
       ${PY} experiments/build_docstring_anchor_table.py --union
     或加 --build-anchor-tables 让本脚本自动构建（会覆盖同内容文件；确定性逐字节一致）。"
            fi
        fi
    done
    if [ "${_need_build}" -eq 1 ]; then
        echo "  构建锚表（零 LLM，确定性）…"
        "${PY}" "${ANCHOR_BUILDER}"
        if [ "${NEED_UNION_TABLE}" -eq 1 ]; then
            "${PY}" "${ANCHOR_BUILDER}" --union
        fi
    fi
else
    log "  （该运行未选 doc/union 臂，跳过锚表检查）"
fi

# ─── 3. 臂注册与分析脚本可用性检查（T1 交付前置） ────────────────────────────
echo ""
echo "[3/6] 依赖交付检查（run_benchmark 臂注册 / T1 分析脚本）"
BASELINE_LIST=()
for _a in "${ARM_LABELS[@]}"; do
    BASELINE_LIST+=("$(arm_baseline "${_a}")")
done
set +e
REGISTRY_OUT="$("${PY}" - "${ROOT}" "${BASELINE_LIST[@]}" <<'PY'
import sys
root = sys.argv[1]
arms = sys.argv[2:]
sys.path.insert(0, root)
try:
    import experiments.run_benchmark as rb
except Exception as e:  # noqa: BLE001
    print(f"IMPORT_FAIL {type(e).__name__}: {e}")
    raise SystemExit(1)
reg = getattr(rb, "BASELINE_REGISTRY", {})
missing = [a for a in arms if a not in reg]
if missing:
    print("MISSING " + ",".join(missing))
    raise SystemExit(1)
print("OK " + ",".join(arms))
PY
)"
REGISTRY_RC=$?
set -e
if [ "${REGISTRY_RC}" -ne 0 ]; then
    die "run_benchmark.BASELINE_REGISTRY 未注册所需臂（T1 未交付/未合并）：${REGISTRY_OUT}
     需要： ${BASELINE_LIST[*]}"
fi
log "  ✓ 臂已注册：${REGISTRY_OUT}"
if [ "${SKIP_ANALYSIS}" -eq 1 ]; then
    warn "跳过末尾分析（--skip-analysis）——判定须另跑，命令见脚本末尾"
elif [ ! -f "${ANALYSIS_SCRIPT}" ]; then
    if [ "${DRY_RUN}" -eq 1 ]; then
        warn "dry-run：T1 分析脚本尚不存在：${ANALYSIS_SCRIPT}（正式运行会失败退出）"
    else
        die "T1 分析脚本不存在：${ANALYSIS_SCRIPT}（T5 前置）。先交付 T1，或 --skip-analysis 只跑批。"
    fi
else
    log "  ✓ 分析脚本在场：${ANALYSIS_SCRIPT}"
fi

# ─── 4. 三臂顺序执行 ────────────────────────────────────────────────────────
echo ""
echo "[4/6] 三臂顺序执行（每臂独立 cache namespace；每臂完整 log）"
if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  （dry-run：以下为将执行的实际命令，不执行）"
fi
_arm_idx=0
START_ALL_EPOCH="$(date +%s)"
START_ALL_ISO="$(date -u +%FT%TZ)"

for _a in "${ARM_LABELS[@]}"; do
    _arm_idx=$((_arm_idx + 1))
    _baseline="$(arm_baseline "${_a}")"
    _ns="$(arm_namespace "${_a}")"
    _log="${ART_DIR}/arm_${_a}.log"
    _dirty_args=()
    if [ "${ALLOW_DIRTY}" -eq 1 ]; then
        _dirty_args=(--allow-dirty --dirty-reason "${DIRTY_REASON}")
    fi
    _cmd=(env "AITESTER_PROFILE=logic" "TEMPERATURE=0.0" "LLM_THINKING_MODE=disabled"
        "BENCHMARK_PARALLELISM=${PARALLELISM}" "AITESTER_CACHE_NAMESPACE=${_ns}"
        "${PY}" "${ROOT}/experiments/run_main_batch.py"
        --dataset quixbugs --task-count "${TASK_COUNT}" --seed "${SEED}"
        --baselines "${_baseline}" --output-dir "${OUT_DIR}" --skip-stats
        ${_dirty_args[@]+"${_dirty_args[@]}"})
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "  [${_arm_idx}/${#ARM_LABELS[@]}] 臂 ${_a} → ${_baseline}（ns=${_ns}）"
        printf '      %q' "${_cmd[@]}"
        printf '\n      log → %s\n' "${_log}"
        continue
    fi

    mkdir -p "${ART_DIR}"
    _before="${ART_DIR}/.before_${_a}.txt"
    : > "${_before}"
    for _f in "${OUT_DIR}"/benchmark_*.json; do
        [ -e "${_f}" ] || continue
        printf '%s\n' "${_f}" >> "${_before}"
    done
    _start_epoch="$(date +%s)"
    _start_iso="$(date -u +%FT%TZ)"
    {
        echo "=== T5 ARM=${_a} baseline=${_baseline} namespace=${_ns} ==="
        echo "START_ISO_UTC=${_start_iso} START_EPOCH=${_start_epoch}"
        printf 'CMD:'
        printf '%q ' "${_cmd[@]}"
        printf '\n'
    } >> "${_log}"
    log "  [${_arm_idx}/${#ARM_LABELS[@]}] 臂 ${_a} → ${_baseline}（ns=${_ns}）开始…"
    set +e
    "${_cmd[@]}" >> "${_log}" 2>&1
    _rc=$?
    set -e
    _end_epoch="$(date +%s)"
    _end_iso="$(date -u +%FT%TZ)"
    {
        echo "END_ISO_UTC=${_end_iso} END_EPOCH=${_end_epoch} EXIT_CODE=${_rc}"
        echo "WALL_SECONDS=$((_end_epoch - _start_epoch))"
    } >> "${_log}"
    if [ "${_rc}" -ne 0 ]; then
        echo "✗ 臂 ${_a} 失败（exit ${_rc}）；日志完整保留：${_log}" >&2
        # 失败也写 manifest 片段（如实记录，不删日志/工件）
        "${PY}" - "${ART_DIR}" "${_a}" "${_baseline}" "${_ns}" "${_rc}" "${_start_iso}" "${_end_iso}" \
            "$((_end_epoch - _start_epoch))" <<'PY' || true
import json
import sys
from pathlib import Path

art_dir, arm, baseline, ns, rc, start_iso, end_iso, wall = sys.argv[1:9]
meta = {
    "arm": arm,
    "baseline": baseline,
    "cache_namespace": ns,
    "status": "failed",
    "exit_code": int(rc),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds": int(wall),
}
Path(art_dir, f"arm_{arm}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
PY
        exit 4
    fi
    _wall=$((_end_epoch - _start_epoch))

    # 定位本臂新增的批次 JSON（精确差集；run_benchmark 自带时间戳文件名）
    _after="${ART_DIR}/.after_${_a}.txt"
    : > "${_after}"
    for _f in "${OUT_DIR}"/benchmark_*.json; do
        [ -e "${_f}" ] || continue
        printf '%s\n' "${_f}" >> "${_after}"
    done
    _new_batch=""
    _new_count=0
    while IFS= read -r _f; do
        [ -n "${_f}" ] || continue
        if [ ! -s "${_before}" ] || ! grep -qxF "${_f}" "${_before}"; then
            _new_batch="${_f}"
            _new_count=$((_new_count + 1))
        fi
    done < "${_after}"
    if [ "${_new_count}" -ne 1 ] || [ -z "${_new_batch}" ]; then
        die "臂 ${_a} 跑批结束但无法唯一定位新增批次 JSON（新增 ${_new_count} 个）；请人工检查 ${OUT_DIR}"
    fi
    printf '%s\n' "${_new_batch}" > "${ART_DIR}/arm_${_a}.batch_path.txt"

    # 每臂结构化元数据（provenance/token/成本/判分/逐任务）
    "${PY}" - "${_new_batch}" "${_a}" "${_baseline}" "${_ns}" "${_start_epoch}" "${_end_epoch}" \
        "${_start_iso}" "${_end_iso}" "${ROOT}/experiments/price_table.json" "${ART_DIR}/arm_${_a}.meta.json" \
        "quixbugs" "${SEED}" "${PARALLELISM}" "${TASK_COUNT}" "${SCRIPT_VERSION}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

(batch_path, arm, baseline, ns, start_epoch, end_epoch, start_iso, end_iso,
 price_path, out_path, dataset, seed, parallelism, planned_tasks, script_version) = sys.argv[1:17]

data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
prov = data.get("provenance") or {}
rd = (data.get("results") or {}).get(baseline)
if rd is None:
    raise SystemExit(f"批次工件中缺少臂 '{baseline}' 结果键（baselines={list((data.get('results') or {}).keys())}）")
details = rd.get("details") or []
tm = rd.get("token_metrics") or {}

# 成本（价目表；模型未登记 → 不编造，cost_usd=null）
model = prov.get("model_name") or ""
price = {}
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

# 判分口径（41 缺陷程序可判定子集：detection_rate 非 None 才进分母）
meas = [r for r in details if r.get("detection_rate") is not None]
det = [r for r in meas if r.get("detection_rate") == 1.0]
rep = [r for r in meas if r.get("repair_rate") == 1.0]
ff = [r for r in meas if r.get("false_fix_rate") == 1.0]
none_ids = [r.get("task_id") for r in details if r.get("detection_rate") is None]
spec_hits = [r.get("spec_replace_applied") for r in details if r.get("spec_replace_applied")]
per_task = []
for r in details:
    per_task.append(
        {
            "task_id": r.get("task_id"),
            "detection_rate": r.get("detection_rate"),
            "repair_rate": r.get("repair_rate"),
            "false_fix_rate": r.get("false_fix_rate"),
            "verdict": r.get("specificity_gate_verdict"),
            "spec_replace_applied": r.get("spec_replace_applied"),
            "token_usage": r.get("token_usage"),
            "elapsed_seconds": r.get("elapsed_seconds"),
            "stop_reason": r.get("stop_reason"),
        }
    )
meta = {
    "script_version": script_version,
    "arm": arm,
    "baseline": baseline,
    "cache_namespace": ns,
    "dataset": dataset,
    "seed": int(seed),
    "parallelism": int(parallelism),
    "planned_task_count_flag": int(planned_tasks),
    "batch_file": str(batch_path),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "status": "completed",
    "start_epoch": int(start_epoch),
    "end_epoch": int(end_epoch),
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds": int(end_epoch) - int(start_epoch),
    "provenance": {
        "git_sha": prov.get("git_sha"),
        "git_dirty": prov.get("git_dirty"),
        "dirty_reason": prov.get("dirty_reason"),
        "model_name": prov.get("model_name"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "temperature": prov.get("temperature"),
        "profile": prov.get("profile"),
        "env_snapshot": prov.get("env_snapshot"),
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
        "detection_none_task_ids": none_ids,
        "spec_replace_applied_counts": {
            k: spec_hits.count(k) for k in sorted({str(x) for x in spec_hits})
        },
    },
    "per_task": per_task,
}
Path(out_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    f"[arm {arm}] 墙钟 {meta['wall_seconds']}s｜tasks={len(details)}｜"
    f"detection={meta['detection']['detected']}/{meta['detection']['measurable']}"
    f"={meta['detection']['detection_rate']}｜tokens={tm.get('total_tokens')}｜cost≈${cost_usd}｜"
    f"git_dirty={prov.get('git_dirty')}"
)
PY
    log "  ✓ 臂 ${_a} 完成：$(cat "${ART_DIR}/arm_${_a}.batch_path.txt")（墙钟 ${_wall}s）"
done

# ─── 5. 跑后卫生 + 成本汇总 ─────────────────────────────────────────────────
echo ""
echo "[5/6] 跑后卫生（孤儿进程只读巡检）＋成本汇总"
END_ALL_EPOCH="$(date +%s)"
END_ALL_ISO="$(date -u +%FT%TZ)"
WARN_EXIT=0
ORPHAN_RC=0
if [ "${DRY_RUN}" -eq 0 ]; then
    ORPHAN_JSON="${ART_DIR}/orphan_procs_after.json"
    set +e
    "${PY}" "${ROOT}/scripts/tools/detect_orphan_procs.py" --json > "${ORPHAN_JSON}" 2> "${ART_DIR}/orphan_procs_after.err"
    ORPHAN_RC=$?
    set -e
    # 退出码 0=无泄漏 / 1=发现泄漏（只读巡检，不自动 kill）
    if [ "${ORPHAN_RC}" -eq 1 ]; then
        WARN_EXIT=6
        warn "孤儿进程巡检发现泄漏（只读；不自动清理）：见 ${ORPHAN_JSON}"
        warn "  清理命令（人工确认后）：${PY} scripts/tools/detect_orphan_procs.py --kill"
    elif [ "${ORPHAN_RC}" -eq 0 ]; then
        log "  ✓ 孤儿进程巡检：未发现泄漏的嵌套测试子进程"
    else
        warn "孤儿进程巡检工具异常（exit ${ORPHAN_RC}，见 ${ART_DIR}/orphan_procs_after.err）"
    fi

    # 成本/墙钟汇总（读各臂 meta；数字一律来自工件，不手写）
    "${PY}" - "${ART_DIR}" <<'PY'
import glob
import json
import sys
from pathlib import Path

art_dir = Path(sys.argv[1])
metas = []
for p in sorted(art_dir.glob("arm_*.meta.json")):
    try:
        metas.append(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        continue
metas = [m for m in metas if m.get("status") == "completed"]
if not metas:
    raise SystemExit("没有可汇总的臂元数据")
print("\n成本/墙钟汇总（标准价目表口径；实际账单可能因缓存/错峰价不同）：")
print(f"  {'arm':<6} {'tasks':>5} {'输入tok':>10} {'输出tok':>10} {'缓存命中':>8} {'墙钟(min)':>9} {'成本($)':>9} {'detection':>10}")
total_cost = 0.0
total_wall = 0.0
unknown_price = False
for m in metas:
    tm = m.get("token_metrics") or {}
    c = m.get("cost_usd_standard_price")
    if c is None:
        unknown_price = True
        c = 0.0
    total_cost += float(c)
    total_wall += float(m.get("wall_seconds") or 0)
    det = m.get("detection") or {}
    det_s = f"{det.get('detected')}/{det.get('measurable')}"
    hits = tm.get("total_cache_hits", tm.get("cache_hits"))
    print(
        f"  {m['arm']:<6} {m.get('tasks_total_rows', 0):>5} {tm.get('total_input_tokens', 0):>10} "
        f"{tm.get('total_output_tokens', 0):>10} {str(hits):>8} {float(m.get('wall_seconds') or 0)/60:>9.1f} "
        f"${float(c):>8.4f} {det_s:>10}"
    )
print(f"  {'合计':<6} {'':>5} {'':>10} {'':>10} {'':>8} {total_wall/60:>9.1f} ${total_cost:>8.4f}")
if unknown_price:
    print("  ⚠️ 部分臂模型未在 experiments/price_table.json 登记价格 → 成本不参与合计（不编造）")
print("\n墙钟/成本估算口径：单臂墙钟来自每臂 START/END EPOCH；成本=token×(价目表单价)，")
print("  缓存命中省下的调用另见 token_metrics.total_cache_avoided_tokens。")
PY
else
    echo "  （dry-run 跳过跑后巡检与成本汇总）"
fi

# ─── 6. T1 分析脚本直出判定 + RUN_MANIFEST + SHA256SUMS ─────────────────────
echo ""
echo "[6/6] T1 分析脚本直出判定（预注册三态）"
ANALYSIS_RC=0
if [ "${DRY_RUN}" -eq 0 ] && [ "${SKIP_ANALYSIS}" -ne 1 ]; then
    _df_file=""
    _doc_file=""
    _union_file=""
    for _a in "${ARM_LABELS[@]}"; do
        _bp="$(cat "${ART_DIR}/arm_${_a}.batch_path.txt" 2>/dev/null || true)"
        case "${_a}" in
            df) _df_file="${_bp}" ;;
            doc) _doc_file="${_bp}" ;;
            union) _union_file="${_bp}" ;;
        esac
    done
    if [ -z "${_df_file}" ] || [ -z "${_doc_file}" ]; then
        die "分析需要 df 与 doc 两臂批次工件（当前缺：${_df_file} / ${_doc_file}）"
    fi
    _union_arg=()
    if [ -n "${_union_file}" ]; then
        _union_arg=(--union "${_union_file}")
    fi
    _report_json="${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.json"
    _report_md="${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.md"
    set +e
    (cd "${ROOT}" && "${PY}" -m experiments.emse_docstring_anchor_analysis \
        --df "${_df_file}" --doc "${_doc_file}" ${_union_arg[@]+"${_union_arg[@]}"} \
        --out "${_report_json}" --markdown "${_report_md}") >> "${ART_DIR}/analysis.log" 2>&1
    ANALYSIS_RC=$?
    set -e
    if [ "${ANALYSIS_RC}" -ne 0 ]; then
        warn "分析脚本失败（exit ${ANALYSIS_RC}，见 ${ART_DIR}/analysis.log）——跑批工件已保留，可事后重跑分析"
        WARN_EXIT=5
    else
        log "  ✓ 判定报告：${_report_json}"
        log "  ✓ Markdown：${_report_md}"
        tail -1 "${ART_DIR}/analysis.log" 2>/dev/null | sed 's/^/  /' || true
    fi
elif [ "${SKIP_ANALYSIS}" -eq 1 ]; then
    warn "已 --skip-analysis：判定须另跑（用下面命令，参数替换为本批批次 JSON）"
else
    echo "  （dry-run：将执行）"
    echo "  ${PY} -m experiments.emse_docstring_anchor_analysis --df <df.json> --doc <doc.json> [--union <union.json>] --out ${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.json --markdown ${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.md"
fi

# RUN_MANIFEST（命令/env/工件/成本/墙钟一站式审计；时间戳文件名不覆盖）
if [ "${DRY_RUN}" -eq 0 ]; then
    "${PY}" - "${ART_DIR}" "${RUN_STAMP}" "${SCRIPT_VERSION}" "${ROOT}" "${OUT_DIR}" \
        "$((END_ALL_EPOCH - START_ALL_EPOCH))" "${START_ALL_ISO}" "${END_ALL_ISO}" \
        "${ORPHAN_RC}" "${ANALYSIS_RC}" "${SEED}" "${PARALLELISM}" "${TASK_COUNT}" "${ARMS_LIST}" <<'PY'
import glob
import json
import subprocess
import sys
from pathlib import Path

(art_dir, run_stamp, script_version, root, out_dir, wall_total, start_iso, end_iso,
 orphan_rc, analysis_rc, seed, parallelism, task_count_flag, arms_list) = sys.argv[1:15]
art = Path(art_dir)
out = Path(out_dir)

def _sha(p):
    import hashlib
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None

git_sha = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
git_dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True).stdout.strip())

arm_metas = []
for p in sorted(art.glob("arm_*.meta.json")):
    try:
        arm_metas.append(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        continue
batch_files = sorted(glob.glob(str(out / "benchmark_*.json")))
run_batch_files = []
for m in arm_metas:
    if m.get("batch_file"):
        run_batch_files.append(m["batch_file"])
anchor_tables = {}
for name in ("DOCSTRING_ANCHOR_TABLE.json", "DOCSTRING_ANCHOR_TABLE_UNION.json"):
    p = out / name
    if p.is_file():
        anchor_tables[str(p)] = _sha(p)
reports = sorted(glob.glob(str(out / f"DOCSTRING_ANCHOR_REPORT_{run_stamp}.*")))
manifest = {
    "run_stamp": run_stamp,
    "script_version": script_version,
    "protocol": {
        "AITESTER_PROFILE": "logic",
        "TEMPERATURE": "0.0",
        "LLM_THINKING_MODE": "disabled",
        "BENCHMARK_PARALLELISM": int(parallelism),
        "seed": int(seed),
        "task_count_flag": int(task_count_flag),
        "known_bug": "run_main_batch --task-count 对真实数据集不生效（见脚本头 KNOWN BUG）；实际跑满 QuixBugs 全量 50 行",
        "arms": arms_list,
    },
    "repo": {"root": root, "git_sha": git_sha, "git_dirty": git_dirty},
    "start_iso_utc": start_iso,
    "end_iso_utc": end_iso,
    "wall_seconds_total": int(wall_total),
    "arms": arm_metas,
    "batch_files_this_run": run_batch_files,
    "anchor_tables": anchor_tables,
    "analysis_reports": reports,
    "analysis_exit_code": int(analysis_rc),
    "orphan_procs_exit_code": int(orphan_rc),
    "artifacts_dir": str(art),
}
manifest_path = art / f"RUN_MANIFEST_{run_stamp}.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"RUN_MANIFEST：{manifest_path}")

# SHA256SUMS（本次新增工件 + 锚表；相对 output dir 路径）
sum_path = art / "SHA256SUMS"
lines = []
for p in run_batch_files + sorted(art.glob("*.log")) + sorted(art.glob("arm_*.meta.json")) + [
    art / "orphan_procs_after.json",
    manifest_path,
] + [Path(r) for r in reports]:
    p = Path(p)
    if not p.is_file():
        continue
    try:
        rel = p.relative_to(out)
    except ValueError:
        rel = p
    lines.append(f"{_sha(p)}  {rel}")
for p, digest in anchor_tables.items():
    if digest:
        lines.append(f"{digest}  {Path(p).relative_to(out)}")
sum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"SHA256SUMS：{sum_path}（{len(lines)} 条）")
PY
fi

echo ""
echo "================================================================================"
if [ "${DRY_RUN}" -eq 1 ]; then
    echo "DRY-RUN 结束：未执行任何跑批/未产生 LLM 调用。"
    echo "正式运行（T5，Lead 批准后）：bash experiments/run_docstring_anchor_batch.sh"
    exit 0
fi
echo "三臂批次完成。RUN_STAMP=${RUN_STAMP}"
echo "  输出目录：${OUT_DIR}"
echo "  运行清单：${ART_DIR}/RUN_MANIFEST_${RUN_STAMP}.json"
echo "  逐臂日志：${ART_DIR}/arm_<arm>.log"
echo "  判定报告：${OUT_DIR}/DOCSTRING_ANCHOR_REPORT_${RUN_STAMP}.json/.md"
echo "  sha256：  ${ART_DIR}/SHA256SUMS"
echo "  后续：把本 RUN_STAMP 对应工件冻结并复制回主工作树（T5 要求），不得手改结果数字。"
echo "================================================================================"
if [ "${WARN_EXIT}" -ne 0 ]; then
    echo "⚠️ 收尾告警（exit=${WARN_EXIT}）：请检查上方日志（孤儿进程/分析失败）。"
    exit "${WARN_EXIT}"
fi
exit 0
