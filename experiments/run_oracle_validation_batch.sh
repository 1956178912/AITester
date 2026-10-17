#!/usr/bin/env bash
# =============================================================================
# O-2 oracle-enabled 二臂真实 LLM 验证批（验证性测量，非 confirmatory）
# 2026-10-17（O 轮；承接 O-1 oracle 仪器加固）
#
# 目的：在**干净切点 worktree**（HEAD = O-1 完成后的 commit）上并发跑两臂：
#   A（control）：--baselines <ARM>（协议默认 plain_llm_df）——oracle 关闭；
#   B（oracle） ：同一 baseline + SPEC_ORACLE_EXEC_ENABLE=true——仅 oracle 注入开关不同；
# 验证：① oracle 注入与独立判读字段（spec_oracle_* / oracle_suite_verdict /
#       llm_suite_detection_rate）逐行在场；② LLM-suite 检出两臂基本一致（oracle
#       不改变 LLM 检出）；③ 成本/墙钟/异常；④ 找功能静默失效。
#
# 协议（固定，验证性；口径见 README）：
#   --dataset quixbugs --task-limit 20 --seed 42
#   AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled
#   BENCHMARK_PARALLELISM=4 AITESTER_BATCH_MAX_CALLS=100
#   COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0
#   两臂独立 AITESTER_CACHE_NAMESPACE；均不设 DETECTION_SPEC_MODE。
#   ⚠️ control 臂必须**显式** SPEC_ORACLE_EXEC_ENABLE=false：AITESTER_PROFILE=logic
#      的档位预设会 setdefault 注入 true（O-2 首跑实测：仅 unset 导致两臂都 oracle-on，
#      对照无效）——本脚本已修复为先 unset 再显式赋值。
#   预算 ≤$0.2 / 墙钟 ≤60min（两臂并发，各臂墙钟看门狗 2400s）。
#
# ⚠️ 协议前置（本脚本进行**零 LLM 可行性门禁**，dry-run 可查）：
#   N-3 的 oracle 材料优先级 = spec_ir → test_plan.logic_analysis →
#   spec_anchor.logic_analysis / spec_anchor.human_spec。**plain_llm_df 臂无
#   planner、无锚表** → 材料为空 → SPEC_ORACLE_EXEC_ENABLE=true 也只会得到
#   not_attempted（不注入）。若需真实验证 oracle 注入，应使用**有锚材料的同
#   baseline 二臂**（该切点可用 `plain_llm_df_spec`：SPEC_ANCHOR_TABLE 随库，
#   材料=spec_anchor.logic_analysis，可编译注入；A/B 仍仅 oracle 开关不同）。
#   本脚本默认按任务书 plain_llm_df，但 real run 在材料探测失败时**拒绝开跑**
#   （除非显式 --allow-degenerate-oracle 表示已知并接受"不注入"的退化验证）。
#
# 用法：
#   bash experiments/run_oracle_validation_batch.sh --dry-run
#   bash experiments/run_oracle_validation_batch.sh --emit-readme-skeleton
#   bash experiments/run_oracle_validation_batch.sh \
#       --root <clean-worktree> --require-clean-root \
#       [--arm-baseline plain_llm_df_spec]   # 经 Lead 批准的协议修正
#
# 产物（默认主仓 gitignored 目录，最后 Lead force-add）：
#   <OUT>/log_control.log / log_oracle.log      每臂完整日志（命令/env/开始结束/git 状态）
#   <OUT>/benchmark_quixbugs_*.json             两臂批次工件（唯一时间戳命名）
#   <OUT>/arm_control.meta.json / arm_oracle.meta.json   每臂结构化元数据
#   <OUT>/ARM_COMPARISON.json                   LLM-suite 一致性 + 注入/verdict 分布 + 字段完整性
#   <OUT>/PREFLIGHT.json                        切点/门禁/材料探测/锚表 sha256
#   <OUT>/README.md                             报告（协议/两臂表/注入与 verdict/一致性/成本/局限）
#   <OUT>/SHA256SUMS                            checksum_results.py --write 生成
#   <OUT>/traces/                               两臂逐任务 trace
#
# 退出码：0=成功；2=参数/前置失败；3=零 LLM 可行性门禁失败（材料/字段/依赖）；
#         4=某臂跑批失败（保留日志，不重跑）；5=provenance/完整性校验失败；6=收尾告警。
# =============================================================================

set -euo pipefail

_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "${_SELF_DIR}/.." && pwd)"
ROOT="${SCRIPT_REPO}"
PY="${SCRIPT_REPO}/.venv/bin/python"
OUT="${SCRIPT_REPO}/experiments/results/emse_oracle_enabled_validation_20261017"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
START_ALL_EPOCH="$(date +%s)"
TASK_LIMIT=20
PARALLELISM=4
ARM_BASELINE="plain_llm_df"
REQUIRE_CLEAN_ROOT=0
ALLOW_DEGENERATE_ORACLE=0
DRY_RUN=0
EMIT_SKELETON=0
WATCHDOG_SECONDS=2400
ONLY_CONTROL=0
REUSE_ORACLE_BATCH=""

usage() {
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --root)
            [ $# -ge 2 ] || { echo "--root 需要目录" >&2; exit 2; }
            ROOT="$2"; shift 2 ;;
        --out)
            [ $# -ge 2 ] || { echo "--out 需要目录" >&2; exit 2; }
            OUT="$2"; shift 2 ;;
        --arm-baseline)
            [ $# -ge 2 ] || { echo "--arm-baseline 需要 baseline 名" >&2; exit 2; }
            ARM_BASELINE="$2"; shift 2 ;;
        --task-limit)
            [ $# -ge 2 ] || { echo "--task-limit 需要正整数" >&2; exit 2; }
            TASK_LIMIT="$2"; shift 2 ;;
        --parallelism)
            [ $# -ge 2 ] || { echo "--parallelism 需要正整数" >&2; exit 2; }
            PARALLELISM="$2"; shift 2 ;;
        --watchdog-seconds)
            [ $# -ge 2 ] || { echo "--watchdog-seconds 需要正整数" >&2; exit 2; }
            WATCHDOG_SECONDS="$2"; shift 2 ;;
        --only-control)
            ONLY_CONTROL=1; shift ;;
        --reuse-oracle-batch)
            [ $# -ge 2 ] || { echo "--reuse-oracle-batch 需要批次 JSON 路径" >&2; exit 2; }
            REUSE_ORACLE_BATCH="$2"; shift 2 ;;
        --require-clean-root)
            REQUIRE_CLEAN_ROOT=1; shift ;;
        --allow-degenerate-oracle)
            ALLOW_DEGENERATE_ORACLE=1; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --emit-readme-skeleton)
            EMIT_SKELETON=1; shift ;;
        -h | --help)
            usage ;;
        *)
            echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
done

case "${TASK_LIMIT}" in '' | *[!0-9]*) echo "--task-limit 必须正整数" >&2; exit 2 ;; esac
case "${PARALLELISM}" in '' | *[!0-9]*) echo "--parallelism 必须正整数" >&2; exit 2 ;; esac
case "${WATCHDOG_SECONDS}" in '' | *[!0-9]*) echo "--watchdog-seconds 必须正整数" >&2; exit 2 ;; esac
[ "${WATCHDOG_SECONDS}" -ge 60 ] || { echo "--watchdog-seconds 必须 >= 60" >&2; exit 2; }
if [ "${ONLY_CONTROL}" -eq 1 ]; then
    [ -n "${REUSE_ORACLE_BATCH}" ] || { echo "✗ --only-control 必须同时给 --reuse-oracle-batch <已完成的 oracle 批次 JSON>" >&2; exit 2; }
    [ -f "${REUSE_ORACLE_BATCH}" ] || { echo "✗ --reuse-oracle-batch 文件不存在：${REUSE_ORACLE_BATCH}" >&2; exit 2; }
fi
[ -x "${PY}" ] || { echo "✗ 未找到解释器 ${PY}" >&2; exit 2; }
[ -d "${ROOT}" ] || { echo "✗ --root 不是目录：${ROOT}" >&2; exit 2; }
ROOT="$(cd "${ROOT}" && pwd)"
mkdir -p "$(dirname "${OUT}")" 2>/dev/null || true
OUT="$(cd "$(dirname "${OUT}")" 2>/dev/null && pwd)/$(basename "${OUT}")"
[ -n "${OUT}" ] || { echo "✗ --out 解析失败" >&2; exit 2; }
[ -f "${ROOT}/experiments/run_main_batch.py" ] || { echo "✗ 代码根缺 experiments/run_main_batch.py：${ROOT}" >&2; exit 2; }

ROOT_GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo '?')"
ROOT_DIRTY="$(git -C "${ROOT}" status --porcelain 2>/dev/null || true)"
if [ -n "${ROOT_DIRTY}" ] && [ "${REQUIRE_CLEAN_ROOT}" -eq 1 ] && [ "${DRY_RUN}" -eq 0 ] && [ "${EMIT_SKELETON}" -eq 0 ]; then
    printf '%s\n' "${ROOT_DIRTY}" >&2
    echo "✗ 代码根不干净（--require-clean-root）：${ROOT}" >&2
    exit 2
fi

echo "================================================================================"
echo "O-2 oracle-enabled 二臂验证批（${RUN_STAMP}）$( [ "${DRY_RUN}" -eq 1 ] && echo '【DRY-RUN：零 LLM】' )"
echo "  代码根（被探针）：${ROOT}"
echo "  HEAD=${ROOT_GIT_HEAD}（dirty 行数=$(printf '%s\n' "${ROOT_DIRTY}" | grep -c . || true)）"
echo "  脚本仓/解释器：${SCRIPT_REPO}"
echo "  输出：${OUT}"
echo "  协议：arm_baseline=${ARM_BASELINE} | task_limit=${TASK_LIMIT} seed=42 | "
echo "        AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled P=${PARALLELISM}"
echo "        AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0"
echo "  两臂：A=control（oracle off） / B=oracle（SPEC_ORACLE_EXEC_ENABLE=true），同 baseline、独立 namespace"
echo "  预算：≤\$0.2；墙钟：≤60min（各臂看门狗 ${WATCHDOG_SECONDS}s）"
if [ "${ONLY_CONTROL}" -eq 1 ]; then
    echo "  运行模式：control-only 补跑（reuse oracle 批次：${REUSE_ORACLE_BATCH}）——sequential pairing，非同一并发时刻"
fi
echo "================================================================================"

# ─── 零 LLM 结构性预检（import 代码根；不调 LLM） ───────────────────────────
echo ""
echo "[1/7] 零 LLM 结构性预检（baseline 注册 / 行字段 / env_snapshot / 材料可行性）"
mkdir -p "${OUT}"
if [ "${DRY_RUN}" -eq 1 ] || [ "${EMIT_SKELETON}" -eq 1 ]; then
    PREFLIGHT_JSON="${OUT}/PREFLIGHT_dryrun.json"
else
    PREFLIGHT_JSON="${OUT}/PREFLIGHT.json"
fi
set +e
"${PY}" - "${ROOT}" "${PREFLIGHT_JSON}" "${ARM_BASELINE}" "${TASK_LIMIT}" "${PARALLELISM}" "${ROOT_GIT_HEAD}" <<'PY'
"""O-2 零 LLM 预检：baseline 注册 / oracle 行字段 / env_snapshot / 材料可行性 / 锚表 sha256。

真 LLM 前置门禁：全部只读（import 代码根 + 读源码/工件），零网络。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

root, out_path, arm_baseline, task_limit, parallelism, git_head = sys.argv[1:7]
root = Path(root)
out_path = Path(out_path)

payload: dict = {
    "run": "O-2 oracle-enabled validation batch",
    "code_root": str(root),
    "git_head": git_head,
    "arm_baseline": arm_baseline,
    "task_limit": int(task_limit),
    "parallelism": int(parallelism),
    "checks": {},
    "material_probe": {},
    "blocking": [],
    "warnings": [],
}

# 1) baseline 注册（import 代码根 run_benchmark）
try:
    sys.path.insert(0, str(root))
    import experiments.run_benchmark as rb  # noqa: E402

    reg = getattr(rb, "BASELINE_REGISTRY", {})
    payload["checks"]["baseline_registered"] = arm_baseline in reg
    payload["registered_baselines"] = sorted(reg.keys())
    if arm_baseline not in reg:
        payload["blocking"].append(f"baseline 未注册：{arm_baseline}（可选：{sorted(reg.keys())}）")
except Exception as exc:  # noqa: BLE001
    payload["checks"]["baseline_registered"] = False
    payload["blocking"].append(f"import experiments.run_benchmark 失败：{type(exc).__name__}: {exc}")

# 2) 行字段 & env_snapshot 键（读源码文本；零 LLM）
src_rb = (root / "experiments/run_benchmark.py").read_text(encoding="utf-8")
src_m1 = (root / "experiments/_m1_metrics.py").read_text(encoding="utf-8")
row_fields = {
    "spec_oracle_injected": '"spec_oracle_injected"' in src_rb,
    "spec_oracle_verdict": '"spec_oracle_verdict"' in src_rb,
    "oracle_suite_verdict": '"oracle_suite_verdict"' in src_rb and '"oracle_suite_verdict"' in src_m1,
    "llm_suite_detection_rate": '"llm_suite_detection_rate"' in src_rb and '"llm_suite_detection_rate"' in src_m1,
}
payload["checks"]["row_fields"] = row_fields
for k, ok in row_fields.items():
    if not ok:
        payload["blocking"].append(f"结果行字段缺失：{k}")
env_snapshot_has_oracle_switch = '"SPEC_ORACLE_EXEC_ENABLE"' in src_rb
payload["checks"]["env_snapshot_has_SPEC_ORACLE_EXEC_ENABLE"] = env_snapshot_has_oracle_switch
_cfg_text = (root / "config.py").read_text(encoding="utf-8")
_logic_block = re.search(r'"logic": \{(.*?)\n    \}', _cfg_text, re.S)
payload["checks"]["profile_logic_presets_SPEC_ORACLE_EXEC_ENABLE"] = bool(
    _logic_block and "SPEC_ORACLE_EXEC_ENABLE" in _logic_block.group(1)
)
if payload["checks"]["profile_logic_presets_SPEC_ORACLE_EXEC_ENABLE"]:
    payload["warnings"].append(
        "AITESTER_PROFILE=logic 的档位预设默认注入 SPEC_ORACLE_EXEC_ENABLE=true；control 臂必须显式 false（脚本已处理）。"
    )
if not env_snapshot_has_oracle_switch:
    payload["blocking"].append("env_snapshot 未登记 SPEC_ORACLE_EXEC_ENABLE（无法审计开关值）")

# 3) oracle 材料可行性探测（决定 arm B 是否真的可能注入）：用真实锚表/状态零 LLM 模拟
probe: dict = {"arm_baseline": arm_baseline}
try:
    from src.graph.nodes import _append_spec_oracle_to_test_with_verdict, _resolve_spec_oracle_material  # noqa: E402
    from src.graph.state import create_initial_state  # noqa: E402

    cache_prog = Path.home() / ".cache/aitester/quixbugs/python_programs/bitcount.py"
    target_code = cache_prog.read_text(encoding="utf-8") if cache_prog.is_file() else "def bitcount(n):\n    return 0\n"

    # 3a) 无锚（plain_llm_df / aitester 类：无 planner、无 spec_anchor）
    st_plain = create_initial_state(
        task_uuid="quixbugs__bitcount", target_file="/tmp/bitcount.py", target_function="bitcount",
        module_name="bitcount", target_code=target_code, max_iterations=1,
    )
    mat, src_label, verdict0 = _resolve_spec_oracle_material(st_plain)
    merged, injected, verdict = _append_spec_oracle_to_test_with_verdict("def test_ok():\n    assert True\n", st_plain)
    probe["no_anchor_state"] = {
        "material_found": mat is not None, "source": src_label, "initial_verdict": verdict0,
        "injected": bool(injected), "verdict": verdict,
    }

    # 3b) spec_anchor=SPEC_ANCHOR_TABLE.logic_analysis（df_spec 类臂）
    spec_table_path = root / "experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"
    spec_probe = {"table": str(spec_table_path), "table_present": spec_table_path.is_file()}
    if spec_table_path.is_file():
        spec_probe["table_sha256"] = hashlib.sha256(spec_table_path.read_bytes()).hexdigest()
        table = json.loads(spec_table_path.read_text(encoding="utf-8"))
        entry = None
        for _h, cand in (table.get("anchors") or {}).items():
            if isinstance(cand, dict) and cand.get("function_name") == "bitcount":
                entry = dict(cand)
                break
        if entry is not None:
            st_spec = dict(st_plain)
            st_spec["spec_anchor"] = entry
            mat2, src2, v0 = _resolve_spec_oracle_material(st_spec)
            merged2, injected2, verdict2 = _append_spec_oracle_to_test_with_verdict(
                "def test_ok():\n    assert True\n", st_spec
            )
            spec_probe.update({
                "material_found": mat2 is not None, "source": src2, "initial_verdict": v0,
                "injected": bool(injected2), "verdict": verdict2,
                "oracle_test_in_merged": "test_specir_v2_oracle" in merged2,
            })
        else:
            spec_probe["warning"] = "SPEC_ANCHOR_TABLE 中未找到 bitcount 条目"
    probe["spec_anchor_state"] = spec_probe

    # 3c) docstring 锚（human_spec-only，不可编译）——说明为何 doc/augment 锚也不能注入
    st_doc = dict(st_plain)
    st_doc["spec_anchor"] = {"function_name": "bitcount", "human_spec": "Input: n nonneg\nOutput: count", "logic_analysis": None}
    _, src_doc, v_doc = _resolve_spec_oracle_material(st_doc)
    probe["human_spec_only_state"] = {"source": src_doc, "verdict": v_doc}

    # 门禁判定：arm_baseline 是否可能注入
    if arm_baseline in ("plain_llm_df", "aitester", "plain_llm", "single_agent"):
        probe["arm_can_inject_oracle"] = False
        probe["reason"] = (
            f"{arm_baseline} 臂无 planner（无 test_plan.logic_analysis）且不加载锚表（无 spec_anchor）"
            "→ oracle 材料为空 → SPEC_ORACLE_EXEC_ENABLE=true 只会记 not_attempted，不注入。"
        )
    elif arm_baseline in ("plain_llm_df_spec",):
        probe["arm_can_inject_oracle"] = bool(probe["spec_anchor_state"].get("injected"))
    elif arm_baseline in ("plain_llm_df_doc", "plain_llm_df_doc_union", "plain_llm_df_doc_augment"):
        probe["arm_can_inject_oracle"] = False
        probe["reason"] = (
            f"{arm_baseline} 臂 spec_anchor 为人类 docstring（human_spec），N-3 明确"
            " not_attempted_human_spec_only（人类规格→可执行断言的翻译不在接线范围）→ 不注入。"
        )
    else:
        probe["arm_can_inject_oracle"] = None
except Exception as exc:  # noqa: BLE001
    probe["error"] = f"{type(exc).__name__}: {exc}"
    probe["arm_can_inject_oracle"] = None
payload["material_probe"] = probe

# 协议修正（Lead 2026-10-17 批准方案 a）：任务书默认 baseline 修正为 df_spec
if arm_baseline != "plain_llm_df":
    payload["protocol_correction"] = {
        "approved_by": "Lead",
        "approved_at_utc": "2026-10-17",
        "default_baseline_in_task": "plain_llm_df",
        "effective_baseline": arm_baseline,
        "kind": "验证性协议修正（不改变任何判定规则/判分口径）",
        "reason": (
            "N-3 oracle 材料优先级 = spec_ir → test_plan.logic_analysis → "
            "spec_anchor.logic_analysis / spec_anchor.human_spec；plain_llm_df 无 planner"
            "（无 test_plan）且不加载锚表（无 spec_anchor）→ 材料为空 → "
            "SPEC_ORACLE_EXEC_ENABLE=true 只会记 not_attempted，无法验证 oracle 注入；"
            "plain_llm_df_spec 携带 spec_anchor.logic_analysis（SPEC_ANCHOR_TABLE）为可编译锚材料。"
        ),
    }

# 3d) LLM 配置层（零 LLM）：.env.local 与 config.LLM_CONFIGS 数
try:
    sys.path.insert(0, str(root))
    import config as _cfg  # noqa: E402

    payload["checks"]["llm_configs_count"] = len(getattr(_cfg, "LLM_CONFIGS", []) or [])
    payload["checks"]["env_local_present"] = (root / ".env.local").is_file()
    if payload["checks"]["llm_configs_count"] < 1:
        payload["blocking"].append("代码根无可用 LLM 配置（config.LLM_CONFIGS 为空；.env.local 缺失？）")
    if not payload["checks"]["env_local_present"]:
        payload["warnings"].append("代码根缺 .env.local（若 shell 环境已配置 LLM_* 可忽略；否则先复制）")
except Exception as exc:  # noqa: BLE001
    payload["checks"]["llm_configs_count"] = None
    payload["warnings"].append(f"config 导入失败（LLM 配置未知）：{type(exc).__name__}: {exc}")

# 4) 结论
if probe.get("arm_can_inject_oracle") is False:
    payload["blocking"].append(
        "arm B 可行性门禁失败：" + probe.get("reason", "") +
        " 建议（经 Lead 批准的协议修正）：A/B 均用 plain_llm_df_spec（同 baseline、仅 oracle 开关不同）。"
    )
elif probe.get("arm_can_inject_oracle") is None:
    payload["warnings"].append("材料可行性探测未得出结论（见 material_probe.error），需人工确认。")

out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "baseline_registered": payload["checks"].get("baseline_registered"),
    "row_fields": row_fields,
    "env_snapshot_has_oracle_switch": env_snapshot_has_oracle_switch,
    "no_anchor_verdict": probe.get("no_anchor_state", {}).get("verdict"),
    "spec_anchor_injected": probe.get("spec_anchor_state", {}).get("injected"),
    "spec_anchor_verdict": probe.get("spec_anchor_state", {}).get("verdict"),
    "arm_can_inject_oracle": probe.get("arm_can_inject_oracle"),
    "blocking": payload["blocking"],
    "warnings": payload["warnings"],
}, ensure_ascii=False, indent=2))
raise SystemExit(0 if not payload["blocking"] else 1)
PY
PRE_RC=$?
set -e
if [ "${PRE_RC}" -ne 0 ]; then
    echo "  ✗ 预检存在阻断项（见 ${PREFLIGHT_JSON}）"
else
    echo "  ✓ 预检通过（${PREFLIGHT_JSON}）"
fi

# 材料门禁：明确区分 dry-run / real-run
ARM_CAN_INJECT="$("${PY}" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("material_probe",{}).get("arm_can_inject_oracle"))' "${PREFLIGHT_JSON}")"
if [ "${DRY_RUN}" -eq 1 ] || [ "${EMIT_SKELETON}" -eq 1 ]; then
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "  [门禁] arm_can_inject_oracle=${ARM_CAN_INJECT}（dry-run 只报告不阻断）"
    fi
else
    if [ "${ARM_CAN_INJECT}" = "False" ] && [ "${ALLOW_DEGENERATE_ORACLE}" -ne 1 ]; then
        echo "✗ 材料可行性门禁失败：当前 arm_baseline=${ARM_BASELINE} 下 SPEC_ORACLE_EXEC_ENABLE 不会注入 oracle（详见 ${PREFLIGHT_JSON}）。" >&2
        echo "  建议：--arm-baseline plain_llm_df_spec（同 baseline 二臂、仅 oracle 开关不同；SPEC_ANCHOR_TABLE 随库）。" >&2
        echo "  如已获 Lead 批准跑\"已知不注入\"的退化验证，可加 --allow-degenerate-oracle（README 必须披露）。" >&2
        exit 3
    fi
fi

# ─── [0b/7] 复用 oracle 批次校验（--only-control；不重跑） ───────────────────
if [ "${ONLY_CONTROL}" -eq 1 ]; then
    echo ""
    echo "[0b/7] 复用 oracle 批次校验（同 cut / 20 行 / env_snapshot=true；不重跑）"
    set +e
    "${PY}" - "${REUSE_ORACLE_BATCH}" "${ROOT_GIT_HEAD}" "${ARM_BASELINE}" "${TASK_LIMIT}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

path, head, arm_baseline, task_limit = sys.argv[1:5]
p = Path(path)
data = json.loads(p.read_text(encoding="utf-8"))
issues = []
results = data.get("results") or {}
arm = results.get(arm_baseline)
if arm is None:
    issues.append(f"缺少臂结果键 {arm_baseline!r}（baselines={list(results)}）")
    rows = []
else:
    rows = arm.get("details") or []
prov = data.get("provenance") or {}
snap = prov.get("env_snapshot") or {}
if int(task_limit) > 0 and len(rows) != int(task_limit):
    issues.append(f"行数 {len(rows)} ≠ task_limit {task_limit}")
if str(prov.get("git_sha")) != head:
    issues.append(f"git_sha {prov.get('git_sha')} ≠ 切点 {head}")
if prov.get("git_dirty") is True:
    issues.append("provenance.git_dirty=true（复用批次必须干净）")
if str(snap.get("SPEC_ORACLE_EXEC_ENABLE")).lower() != "true":
    issues.append(f"env_snapshot.SPEC_ORACLE_EXEC_ENABLE={snap.get('SPEC_ORACLE_EXEC_ENABLE')!r} ≠ 'true'（复用的必须是 oracle 臂）")
summary = {
    "reuse_batch": str(p.resolve()),
    "reuse_batch_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    "rows": len(rows),
    "git_sha": prov.get("git_sha"),
    "git_dirty": prov.get("git_dirty"),
    "env_snapshot_SPEC_ORACLE_EXEC_ENABLE": snap.get("SPEC_ORACLE_EXEC_ENABLE"),
    "issues": issues,
}
# 注：不向复用批次所在目录写任何文件（归档保持原样/可校验）；校验结果仅打印并随运行日志归档。
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(0 if not issues else 1)
PY
    REUSE_RC=$?
    set -e
    if [ "${REUSE_RC}" -ne 0 ]; then
        echo "✗ 复用 oracle 批次校验失败——立即中止（不跑 control）。" >&2
        exit 3
    fi
fi

# ─── 显式 env 有效性门禁（profile preset footgun 防呆；零 LLM）──────────────
echo ""
echo "[1b/7] 显式 env 有效性门禁（control 必须 false / oracle 必须 true，且两者不同）"
( cd "${ROOT}" && env -u SPEC_ORACLE_EXEC_ENABLE AITESTER_PROFILE=logic SPEC_ORACLE_EXEC_ENABLE=false \
    "${PY}" -c 'import os, config; print((os.getenv("SPEC_ORACLE_EXEC_ENABLE") or "").strip().lower())' ) > /tmp/o2_eff_ctl.$$ 2>/dev/null || true
( cd "${ROOT}" && env -u SPEC_ORACLE_EXEC_ENABLE AITESTER_PROFILE=logic SPEC_ORACLE_EXEC_ENABLE=true \
    "${PY}" -c 'import os, config; print((os.getenv("SPEC_ORACLE_EXEC_ENABLE") or "").strip().lower())' ) > /tmp/o2_eff_orc.$$ 2>/dev/null || true
EFF_CTL="$(cat /tmp/o2_eff_ctl.$$ 2>/dev/null || true)"; EFF_ORC="$(cat /tmp/o2_eff_orc.$$ 2>/dev/null || true)"
rm -f /tmp/o2_eff_ctl.$$ /tmp/o2_eff_orc.$$
echo "  control effective SPEC_ORACLE_EXEC_ENABLE=${EFF_CTL:-<probe-failed>} | oracle effective=${EFF_ORC:-<probe-failed>}"
if [ "${EFF_CTL}" != "false" ] || [ "${EFF_ORC}" != "true" ]; then
    echo "✗ 预检失败：显式 env 未按预期生效（control=${EFF_CTL:-?} oracle=${EFF_ORC:-?}）——立即中止，不跑批（profile preset 陷阱？）。" >&2
    exit 3
fi
"${PY}" - "${PREFLIGHT_JSON}" "${EFF_CTL}" "${EFF_ORC}" <<'PY'
import json
import sys
from pathlib import Path

path, ctl, orc = sys.argv[1:4]
try:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
except (OSError, ValueError):
    d = {}
d.setdefault("checks", {})["effective_env_probe"] = {
    "control_SPEC_ORACLE_EXEC_ENABLE": ctl,
    "oracle_SPEC_ORACLE_EXEC_ENABLE": orc,
    "distinct": (ctl != orc),
}
Path(path).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("  ✓ PREFLIGHT.effective_env_probe:", d["checks"]["effective_env_probe"])
PY

# ─── 运行模式写入 PREFLIGHT（only-control/watchdog/reuse；审计） ─────────────
if [ -f "${PREFLIGHT_JSON}" ]; then
    "${PY}" - "${PREFLIGHT_JSON}" "${ONLY_CONTROL}" "${WATCHDOG_SECONDS}" "${REUSE_ORACLE_BATCH}" <<'PY'
import json
import sys
from pathlib import Path

path, only_control, watchdog, reuse = sys.argv[1:5]
try:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
except (OSError, ValueError):
    d = {}
d["run_mode"] = {
    "only_control": str(only_control) == "1",
    "watchdog_seconds": int(watchdog),
    "reuse_oracle_batch": reuse or None,
}
Path(path).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PY
fi

# ─── README 骨架（--emit-readme-skeleton，零 LLM） ──────────────────────────
if [ "${EMIT_SKELETON}" -eq 1 ]; then
    "${PY}" - "${OUT}/README_SKELETON.md" "${ARM_BASELINE}" "${TASK_LIMIT}" "${ROOT_GIT_HEAD}" "${PREFLIGHT_JSON}" <<'PY'
import json
import sys
from pathlib import Path

out_md, arm, limit, head, pre_path = sys.argv[1:6]
pre = json.loads(Path(pre_path).read_text(encoding="utf-8"))
lines = [
    f"# O-2 oracle-enabled 二臂验证批（20 任务）— README 骨架（真跑前生成，{head[:12]}）",
    "",
    "> 本文件是零 LLM 骨架；真实跑批完成后由 `run_oracle_validation_batch.sh` 生成正式 `README.md`（数字全部来自两臂批次 JSON）。",
    "",
    "## 1. 协议（固定，验证性非 confirmatory）",
    "",
    f"- 切点 worktree：`{pre.get('code_root')}`，HEAD=`{head}`，跑前/跑后 `git status --porcelain` 0 行。",
    f"- 臂 A（control）：`--baselines {arm}`（oracle 关闭）；臂 B（oracle）：同一 baseline + `SPEC_ORACLE_EXEC_ENABLE=true`；两臂不设 `DETECTION_SPEC_MODE`。",
    f"- `--dataset quixbugs --task-limit {limit} --seed 42`；`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4`。",
    "- `AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE`（`..._control` / `..._oracle`）。",
    f"- 零 LLM 材料可行性探测：arm_can_inject_oracle=**{pre.get('material_probe', {}).get('arm_can_inject_oracle')}**。",
    "",
]
if arm != "plain_llm_df":
    lines += [
        f"**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `{arm}`。",
        "原因：oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis/human_spec`；",
        "`plain_llm_df` 无 planner/无锚表 → 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true` 只会 `not_attempted`，无法验证注入；",
        "`plain_llm_df_spec` 的 `spec_anchor.logic_analysis`（SPEC_ANCHOR_TABLE）为可编译锚材料。该修正不改任何判定规则/判分口径。",
        "",
    ]
lines += [
    "## 2. 两臂结果（真跑后填）",
    "",
    "| 项 | A（control） | B（oracle） |",
    "|---|---|---|",
    "| baseline / namespace | | |",
    "| 批次工件 / sha256 | | |",
    "| 墙钟(s) / tokens / 成本($) | | |",
    "| LLM-suite detection（41 口径） | | |",
    "| `spec_oracle_injected` 分布 | | |",
    "| `spec_oracle_verdict` 分布 | | |",
    "| `oracle_suite_verdict` 分布 | | |",
    "| 行字段完整率 | | |",
    "",
    "## 3. LLM-suite 一致性（逐任务两臂对比）",
    "",
    "（真跑后填：detection_rate / llm_suite_detection_rate 逐任务是否一致 + 不一致清单）",
    "",
    "## 4. 成本与墙钟",
    "",
    "（真跑后填）",
    "",
    "## 5. 异常/局限/披露",
    "",
    "- 验证性测量：不作为 confirmatory 判定；预算 ≤$0.2、墙钟 ≤60min。",
    "- 并发调度（两臂并发、各自 P4）；次指标含 CPU 争抢噪声，LLM-suite detection 主指标在任务阶段采集。",
    "- 若协议修正（如 arm baseline 改为 plain_llm_df_spec）已获 Lead 批准，须在此披露。",
    "",
    "## 6. 复现",
    "",
    "```bash",
    "bash experiments/run_oracle_validation_batch.sh --root <clean-worktree> --require-clean-root \\",
    f"  --arm-baseline {arm}",
    "```",
    "",
]
Path(out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"README_SKELETON：{out_md}")
PY
    echo "  ✓ README 骨架：${OUT}/README_SKELETON.md"
    exit 0
fi

if [ "${DRY_RUN}" -eq 1 ]; then
    echo ""
    echo "[DRY-RUN] 计划执行（两臂并发；每臂独立 namespace/log；零 LLM 调用）："
    echo "  A control：--baselines ${ARM_BASELINE}（SPEC_ORACLE_EXEC_ENABLE=false，显式关闭）"
    if [ "${ONLY_CONTROL}" -eq 1 ]; then
        echo "  B oracle ：**复用** attempt#2 批次（不启动、不消耗 LLM）：${REUSE_ORACLE_BATCH}"
        echo "  模式：control-only 补跑（sequential pairing；看门狗 ${WATCHDOG_SECONDS}s）"
    else
        echo "  B oracle ：--baselines ${ARM_BASELINE} + SPEC_ORACLE_EXEC_ENABLE=true"
    fi
    echo "  输出：${OUT}"
    echo "  真实跑批前：等 Lead 给出 O-1 切点 sha + 干净 worktree，再执行"
    echo "  bash experiments/run_oracle_validation_batch.sh --root <worktree> --require-clean-root [--arm-baseline <approved>]"
    echo "DRY-RUN 结束：未执行任何 LLM 调用、未产出批次工件。"
    exit 0
fi

# ─── 既有工件保护 ────────────────────────────────────────────────────────────
if [ -e "${OUT}/log_control.log" ] || [ -e "${OUT}/log_oracle.log" ] || [ -e "${OUT}/README.md" ]; then
    echo "✗ 输出目录已存在正式批工件（${OUT}）——禁止覆盖；如需重跑请换 --out 或由 Lead 裁决。" >&2
    exit 2
fi
mkdir -p "${OUT}/_helpers"

# ─── 辅助：墙钟看门狗 + 逐臂元数据/SHA ──────────────────────────────────────
cat > "${OUT}/_helpers/limited_run.py" <<'PY'
"""有限墙钟看门狗：超时 SIGTERM→SIGKILL 进程组，不静默挂死。"""

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
    print(f"\n[watchdog] 超过墙钟上限 {limit:.0f}s：SIGTERM 进程组…", file=sys.stderr, flush=True)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait()
    sys.exit(124)
print(f"[watchdog] rc={rc} wall={time.time() - t0:.1f}s", file=sys.stderr, flush=True)
sys.exit(rc)
PY

cat > "${OUT}/_helpers/extract_arm.py" <<'PY'
"""逐臂元数据抽取（零 LLM）：tokens/成本/注入与 verdict 分布/字段完整率/env_snapshot。"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

batch_path, arm_label, arm_baseline, ns, oracle_enabled, price_path, out_path = sys.argv[1:8]
data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
rd = (data.get("results") or {}).get(arm_baseline) or {}
rows = rd.get("details") or []
tm = rd.get("token_metrics") or {}
prov = data.get("provenance") or {}
try:
    price = (json.loads(Path(price_path).read_text(encoding="utf-8")).get("models") or {}).get(prov.get("model_name") or "") or {}
except (OSError, ValueError):
    price = {}
cost = None
if isinstance(price.get("input_per_mtok"), (int, float)) and isinstance(price.get("output_per_mtok"), (int, float)):
    cost = round(
        float(tm.get("total_input_tokens") or 0) / 1e6 * price["input_per_mtok"]
        + float(tm.get("total_output_tokens") or 0) / 1e6 * price["output_per_mtok"], 6
    )

required = ("spec_oracle_injected", "spec_oracle_verdict", "oracle_suite_verdict",
            "llm_suite_detection_rate", "detection_rate")
field_complete = {k: sum(1 for r in rows if k in r) for k in required}
injected_counts: dict[str, int] = {}
verdict_counts: dict[str, int] = {}
oracle_suite_counts: dict[str, int] = {}
for r in rows:
    iv = str(r.get("spec_oracle_injected"))
    injected_counts[iv] = injected_counts.get(iv, 0) + 1
    vv = str(r.get("spec_oracle_verdict"))
    verdict_counts[vv] = verdict_counts.get(vv, 0) + 1
    ov = str(r.get("oracle_suite_verdict"))
    oracle_suite_counts[ov] = oracle_suite_counts.get(ov, 0) + 1

meta = {
    "arm_label": arm_label,
    "arm_baseline": arm_baseline,
    "cache_namespace": ns,
    "spec_oracle_exec_enabled_requested": oracle_enabled,
    "batch_file": str(batch_path),
    "batch_sha256": hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
    "rows": len(rows),
    "token_metrics": tm,
    "cost_usd_standard_price": cost,
    "provenance": {
        "git_sha": prov.get("git_sha"), "git_dirty": prov.get("git_dirty"),
        "dirty_reason": prov.get("dirty_reason"),
        "model_name": prov.get("model_name"),
        "model_fingerprint": prov.get("model_fingerprint"),
        "temperature": prov.get("temperature"), "profile": prov.get("profile"),
        "env_snapshot_spec_oracle_exec_enable": (prov.get("env_snapshot") or {}).get("SPEC_ORACLE_EXEC_ENABLE"),
        "env_snapshot_cache_namespace": (prov.get("env_snapshot") or {}).get("AITESTER_CACHE_NAMESPACE"),
        "env_snapshot_detection_spec_mode": (prov.get("env_snapshot") or {}).get("DETECTION_SPEC_MODE"),
    },
    "field_completeness": {k: f"{v}/{len(rows)}" for k, v in field_complete.items()},
    "spec_oracle_injected_counts": injected_counts,
    "spec_oracle_verdict_counts": verdict_counts,
    "oracle_suite_verdict_counts": oracle_suite_counts,
    "llm_suite_detection": {
        "measurable": sum(1 for r in rows if r.get("llm_suite_detection_rate") is not None),
        "detected": sum(1 for r in rows if r.get("llm_suite_detection_rate") == 1.0),
    },
    "per_task_llm_suite": {
        str(r.get("task_id")): {
            "detection_rate": r.get("detection_rate"),
            "llm_suite_detection_rate": r.get("llm_suite_detection_rate"),
            "spec_oracle_injected": r.get("spec_oracle_injected"),
            "spec_oracle_verdict": r.get("spec_oracle_verdict"),
            "oracle_suite_verdict": r.get("oracle_suite_verdict"),
        }
        for r in rows
    },
}
Path(out_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{arm_label}] rows={len(rows)} tokens={tm.get('total_tokens')} cost=${cost} "
      f"injected={injected_counts} oracle_suite={oracle_suite_counts}")
PY

# ─── 两臂并发执行 ────────────────────────────────────────────────────────────
echo ""
echo "[2/7] 两臂并发启动（同 baseline、仅 oracle 开关不同；独立 namespace/log/trace）"
STAGE_A="${OUT}/.staging_control"
STAGE_B="${OUT}/.staging_oracle"
LOG_A="${OUT}/log_control.log"
LOG_B="${OUT}/log_oracle.log"
NS_A="emse_oracle_enabled_validation_20261017_control"
NS_B="emse_oracle_enabled_validation_20261017_oracle"

_launch_arm() { # label oracle_enabled namespace staging logfile
    local label="$1" oracle="$2" ns="$3" staging="$4" log="$5"
    local start_epoch start_iso
    start_epoch="$(date +%s)"; start_iso="$(date -u +%FT%TZ)"
    mkdir -p "${staging}" "${OUT}/traces_${label}"
    local -a _env_args
    _env_args=(-u DOC_ANCHOR_TABLE -u DF_SPEC_ANCHOR_TABLE -u AITESTER_QUIXBUGS_DATA -u DETECTION_SPEC_MODE -u SPEC_ORACLE_EXEC_ENABLE
        "AITESTER_PROFILE=logic" "TEMPERATURE=0.0" "LLM_THINKING_MODE=disabled"
        "BENCHMARK_PARALLELISM=${PARALLELISM}" "AITESTER_BATCH_MAX_CALLS=100"
        "COST_BUDGET_ENABLE=true" "COST_BUDGET_USD=1" "AITESTER_LLM_CACHE=0"
        "AITESTER_CACHE_NAMESPACE=${ns}" "AITESTER_TRACE_DIR=${OUT}/traces_${label}")
    if [ "${oracle}" = "1" ]; then
        _env_args+=("SPEC_ORACLE_EXEC_ENABLE=true")
    else
        # 关键修复（O-2 实测）：AITESTER_PROFILE=logic 的档位预设默认注入
        # SPEC_ORACLE_EXEC_ENABLE=true（config.py setdefault），"unset"无法关闭——
        # control 必须**显式 false** 才能与 oracle 臂构成有效 A/B 对照。
        _env_args+=("SPEC_ORACLE_EXEC_ENABLE=false")
    fi
    local cmd=(env "${_env_args[@]}" "${PY}" "${ROOT}/experiments/run_main_batch.py"
        --dataset quixbugs --task-limit "${TASK_LIMIT}" --seed 42 --baselines "${ARM_BASELINE}"
        --output-dir "${staging}" --skip-stats ${_DIRTY_ARGS[@]+"${_DIRTY_ARGS[@]}"})
    {
        echo "=== O-2 ARM=${label} baseline=${ARM_BASELINE} oracle=${oracle} namespace=${ns} ==="
        echo "START_ISO_UTC=${start_iso} START_EPOCH=${start_epoch}"
        echo "CODE_ROOT=${ROOT} GIT_HEAD=${ROOT_GIT_HEAD}"
        echo "GIT_STATUS_PRE=${ROOT_DIRTY:-<clean>}"
        echo "CMD:"; printf ' %q' "${cmd[@]}"; printf '\n'
    } >> "${log}"
    printf '%s %s\n' "${start_epoch}" "${start_iso}" > "${OUT}/.arm_${label}.start"
    rm -f "${OUT}/.arm_${label}.rc"
    (
        set +e
        ( cd "${ROOT}" && "${PY}" "${OUT}/_helpers/limited_run.py" "${WATCHDOG_SECONDS}" "${cmd[@]}" ) >> "${log}" 2>&1
        echo $? > "${OUT}/.arm_${label}.rc"
    ) &
    echo "$!" > "${OUT}/.arm_${label}.pid"
}

# dirty args：代码根不干净时（非 --require-clean-root 场景）允许并记录
if [ -n "${ROOT_DIRTY}" ]; then _DIRTY_ARGS=(--allow-dirty --dirty-reason "O-2 validation batch: code root not clean (${#ROOT_DIRTY} lines) — user-approved"); else _DIRTY_ARGS=(); fi

_launch_arm control 0 "${NS_A}" "${STAGE_A}" "${LOG_A}"
PID_A="$(cat "${OUT}/.arm_control.pid")"
echo "  ✓ A control 已启动 pid=${PID_A}（ns=${NS_A}，SPEC_ORACLE_EXEC_ENABLE=false 显式）"
if [ "${ONLY_CONTROL}" -eq 1 ]; then
    PID_B=""
    rm -f "${OUT}/.arm_oracle.rc"
    echo "  ✓ B oracle  ：复用既存批次（不启动，不消耗 LLM）：${REUSE_ORACLE_BATCH}"
else
    _launch_arm oracle 1 "${NS_B}" "${STAGE_B}" "${LOG_B}"
    PID_B="$(cat "${OUT}/.arm_oracle.pid")"
    echo "  ✓ B oracle  已启动 pid=${PID_B}（ns=${NS_B}，SPEC_ORACLE_EXEC_ENABLE=true）"
fi

echo ""
echo "[3/7] 监控与等待（每 15s 检查完成；每臂看门狗 ${WATCHDOG_SECONDS}s）"
LAST_SCAN=0
while :; do
    _done=1
    [ -f "${OUT}/.arm_control.rc" ] || _done=0
    if [ "${ONLY_CONTROL}" -eq 0 ]; then [ -f "${OUT}/.arm_oracle.rc" ] || _done=0; fi
    if [ "${_done}" -eq 1 ]; then break; fi
    sleep 15
    NOW="$(date +%s)"
    if [ $((NOW - LAST_SCAN)) -ge 300 ]; then
        LAST_SCAN="${NOW}"
        if [ "${ONLY_CONTROL}" -eq 1 ]; then
            echo "  … 已运行 $(( (NOW - START_ALL_EPOCH) / 60 ))min（control=$([ -f "${OUT}/.arm_control.rc" ] && echo done || echo running)；oracle 复用不运行）"
        else
            echo "  … 已运行 $(( (NOW - START_ALL_EPOCH) / 60 ))min（control=$([ -f "${OUT}/.arm_control.rc" ] && echo done || echo running)，oracle=$([ -f "${OUT}/.arm_oracle.rc" ] && echo done || echo running)）"
        fi
    fi
done
set +e
wait "${PID_A}" 2>/dev/null
if [ -n "${PID_B}" ]; then wait "${PID_B}" 2>/dev/null; fi
set -e
RC_A="$(cat "${OUT}/.arm_control.rc" 2>/dev/null || echo 127)"
if [ "${ONLY_CONTROL}" -eq 1 ]; then RC_B=0; else RC_B="$(cat "${OUT}/.arm_oracle.rc" 2>/dev/null || echo 127)"; fi
case "${RC_A}" in '' | *[!0-9]*) RC_A=127 ;; esac
case "${RC_B}" in '' | *[!0-9]*) RC_B=127 ;; esac
END_ALL_EPOCH="$(date +%s)"
GIT_STATUS_AFTER="$(git -C "${ROOT}" status --porcelain 2>/dev/null || true)"
echo "  ✓ 两臂结束：control exit=${RC_A}，oracle exit=${RC_B}，总墙钟 $((END_ALL_EPOCH - START_ALL_EPOCH))s"

# ─── 收集工件 + 逐臂元数据 ──────────────────────────────────────────────────
echo ""
echo "[4/7] 收集工件与逐臂元数据"
ARM_FAIL=0
BATCH_A=""
BATCH_B=""

_collect_arm() { # label baseline ns oracle staging rc
    local label="$1" baseline="$2" ns="$3" oracle="$4" staging="$5" rc="$6"
    local log="${OUT}/log_${label}.log"
    local start_epoch start_iso end_epoch end_iso wall _batch="" _target=""
    _FOUND=()
    start_epoch="$(awk '{print $1}' "${OUT}/.arm_${label}.start")"
    start_iso="$(awk '{print $2}' "${OUT}/.arm_${label}.start")"
    end_epoch="$(date +%s)"; end_iso="$(date -u +%FT%TZ)"
    wall=$((end_epoch - start_epoch))
    if [ -d "${staging}" ]; then
        while IFS= read -r f; do [ -n "${f}" ] && _FOUND+=("${f}"); done \
            < <(find "${staging}" -maxdepth 1 -type f -name 'benchmark_*.json' 2>/dev/null | sort)
    fi
    if [ "${#_FOUND[@]}" -eq 1 ]; then
        _batch="${_FOUND[0]}"
        _target="${OUT}/$(basename "${_batch}")"
        if [ -e "${_target}" ]; then _target="${OUT}/$(basename "${_batch}" .json)_${label}.json"; fi
        if [ -e "${_target}" ]; then warn_msg="目标存在，拒绝覆盖：${_target}"; _target=""; fi
        if [ -n "${_target}" ]; then mv "${_batch}" "${_target}"; _batch="${_target}"; fi
    fi
    rmdir "${staging}" 2>/dev/null || true
    {
        echo "END_ISO_UTC=${end_iso} END_EPOCH=${end_epoch} EXIT_CODE=${rc} WALL_SECONDS=${wall}"
        echo "GIT_STATUS_AFTER=$(printf '%s' "${GIT_STATUS_AFTER}" | tr '\n' ';' || true)"
        echo "BATCH_FILE=${_batch:-<missing>}"
    } >> "${log}"
    if [ "${rc}" -ne 0 ] || [ -z "${_batch}" ]; then
        "${PY}" - "${label}" "${baseline}" "${ns}" "${rc}" "${end_iso}" "${wall}" "${log}" "${OUT}/arm_${label}.meta.json" <<'PY'
import json, sys
from pathlib import Path
label, baseline, ns, rc, end_iso, wall, log_path, out_path = sys.argv[1:9]
Path(out_path).write_text(json.dumps({
    "arm_label": label, "arm_baseline": baseline, "cache_namespace": ns,
    "status": "failed", "exit_code": int(rc), "end_iso_utc": end_iso,
    "wall_seconds": int(wall), "log": log_path,
    "note": "臂失败/中断：日志与部分工件保留，按协议不重跑",
}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
        ARM_FAIL=1
        return 0
    fi
    "${PY}" "${OUT}/_helpers/extract_arm.py" "${_batch}" "${label}" "${baseline}" "${ns}" "${oracle}" \
        "${ROOT}/experiments/price_table.json" "${OUT}/arm_${label}.meta.json"
    if [ "${label}" = "control" ]; then BATCH_A="${_batch}"; else BATCH_B="${_batch}"; fi
}

_collect_arm control "${ARM_BASELINE}" "${NS_A}" 0 "${STAGE_A}" "${RC_A}"
if [ "${ONLY_CONTROL}" -eq 1 ]; then
    _reuse_target="${OUT}/$(basename "${REUSE_ORACLE_BATCH}")"
    if [ -e "${_reuse_target}" ]; then
        _reuse_target="${OUT}/$(basename "${REUSE_ORACLE_BATCH}" .json)_reused_oracle.json"
    fi
    if [ -e "${_reuse_target}" ]; then
        echo "✗ 复用目标已存在，拒绝覆盖：${_reuse_target}" >&2
        ARM_FAIL=1
    else
        cp -p "${REUSE_ORACLE_BATCH}" "${_reuse_target}"
        BATCH_B="${_reuse_target}"
        echo "  oracle（复用批次已复制入工件目录）：${BATCH_B}"
        "${PY}" "${OUT}/_helpers/extract_arm.py" "${BATCH_B}" oracle "${ARM_BASELINE}" "${NS_B}" 1 \
            "${ROOT}/experiments/price_table.json" "${OUT}/arm_oracle.meta.json"
    fi
else
    _collect_arm oracle "${ARM_BASELINE}" "${NS_B}" 1 "${STAGE_B}" "${RC_B}"
fi
echo "  control 批次：${BATCH_A:-<缺失>}"
echo "  oracle  批次：${BATCH_B:-<缺失>}"

if [ "${ARM_FAIL}" -ne 0 ]; then
    echo "✗ 某臂失败（control=${RC_A} oracle=${RC_B}）——保留日志/工件，不重跑。" >&2
    exit 4
fi

# ─── provenance / env_snapshot 核验 + LLM-suite 一致性 ──────────────────────
echo ""
echo "[5/7] provenance / env_snapshot / 字段完整性 / LLM-suite 一致性核验"
set +e
"${PY}" - "${OUT}" "${ROOT}" "${ARM_BASELINE}" "${ROOT_GIT_HEAD}" <<'PY'
"""两臂核验：provenance/env_snapshot、字段完整率、LLM-suite 一致性、注入/verdict 分布。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

out, root, arm_baseline, git_head = sys.argv[1:5]
out = Path(out)
meta_a = json.loads((out / "arm_control.meta.json").read_text(encoding="utf-8"))
meta_b = json.loads((out / "arm_oracle.meta.json").read_text(encoding="utf-8"))
issues: list[str] = []
warnings: list[str] = []

# provenance
for meta, expected_oracle in ((meta_a, "false"), (meta_b, "true")):
    prov = meta.get("provenance") or {}
    fp = prov.get("model_fingerprint") or {}
    label = meta["arm_label"]
    if prov.get("git_dirty") is True:
        issues.append(f"{label}: provenance.git_dirty=true")
    if str(prov.get("git_sha")) != git_head:
        issues.append(f"{label}: git_sha={prov.get('git_sha')} ≠ 切点 {git_head}")
    if fp.get("pinned") is not True:
        warnings.append(f"{label}: 模型指纹 pinned≠true（{fp.get('pinned')}）")
    snap = prov.get("env_snapshot_spec_oracle_exec_enable")
    if expected_oracle is not None and str(snap).lower() != expected_oracle:
        issues.append(f"{label}: env_snapshot.SPEC_ORACLE_EXEC_ENABLE={snap!r}，期望 {expected_oracle!r}")
    if expected_oracle == "false" and str(snap).lower() != "false":
        issues.append(
            f"{label}: control 臂 env_snapshot.SPEC_ORACLE_EXEC_ENABLE={snap!r}，期望显式 'false'"
            "（注意：AITESTER_PROFILE=logic 预设会默认开启 oracle，unset 不等于关闭）"
        )
    if prov.get("env_snapshot_detection_spec_mode") not in (None, ""):
        issues.append(f"{label}: 不应设置 DETECTION_SPEC_MODE，实际 {prov.get('env_snapshot_detection_spec_mode')!r}")

# 字段完整率
for meta in (meta_a, meta_b):
    rows = meta["rows"]
    bad = {k: v for k, v in (meta.get("field_completeness") or {}).items() if v != f"{rows}/{rows}"}
    if bad:
        issues.append(f"{meta['arm_label']}: 行字段不完整 {bad}")

# LLM-suite 一致性（逐任务）
per_a = meta_a.get("per_task_llm_suite") or {}
per_b = meta_b.get("per_task_llm_suite") or {}
common = sorted(set(per_a) & set(per_b))
mismatch = []
for tid in common:
    a = per_a[tid].get("llm_suite_detection_rate")
    b = per_b[tid].get("llm_suite_detection_rate")
    if a != b:
        mismatch.append({"task_id": tid, "control": a, "oracle": b})
only_a = sorted(set(per_a) - set(per_b))
only_b = sorted(set(per_b) - set(per_a))

def _detection(meta):
    m = meta.get("llm_suite_detection") or {}
    return {"measurable": m.get("measurable"), "detected": m.get("detected"),
            "rate": round(m["detected"] / m["measurable"], 4) if m.get("measurable") else None}

comparison = {
    "arm_baseline": arm_baseline,
    "git_head": git_head,
    "control": {
        "rows": meta_a["rows"], "tokens": meta_a.get("token_metrics"),
        "cost_usd_standard_price": meta_a.get("cost_usd_standard_price"),
        "llm_suite_detection": _detection(meta_a),
        "spec_oracle_injected_counts": meta_a.get("spec_oracle_injected_counts"),
        "spec_oracle_verdict_counts": meta_a.get("spec_oracle_verdict_counts"),
        "oracle_suite_verdict_counts": meta_a.get("oracle_suite_verdict_counts"),
        "batch_sha256": meta_a.get("batch_sha256"),
        "env_snapshot_spec_oracle_exec_enable": (meta_a.get("provenance") or {}).get("env_snapshot_spec_oracle_exec_enable"),
    },
    "oracle": {
        "rows": meta_b["rows"], "tokens": meta_b.get("token_metrics"),
        "cost_usd_standard_price": meta_b.get("cost_usd_standard_price"),
        "llm_suite_detection": _detection(meta_b),
        "spec_oracle_injected_counts": meta_b.get("spec_oracle_injected_counts"),
        "spec_oracle_verdict_counts": meta_b.get("spec_oracle_verdict_counts"),
        "oracle_suite_verdict_counts": meta_b.get("oracle_suite_verdict_counts"),
        "batch_sha256": meta_b.get("batch_sha256"),
        "env_snapshot_spec_oracle_exec_enable": (meta_b.get("provenance") or {}).get("env_snapshot_spec_oracle_exec_enable"),
    },
    "llm_suite_consistency": {
        "common_tasks": len(common), "mismatch_count": len(mismatch), "mismatches": mismatch,
        "only_in_control": only_a, "only_in_oracle": only_b,
    },
    "issues": issues,
    "warnings": warnings,
}
(out / "ARM_COMPARISON.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "control": comparison["control"]["llm_suite_detection"],
    "oracle": comparison["oracle"]["llm_suite_detection"],
    "consistency": comparison["llm_suite_consistency"],
    "control_injected": comparison["control"]["spec_oracle_injected_counts"],
    "oracle_injected": comparison["oracle"]["spec_oracle_injected_counts"],
    "oracle_verdict": comparison["oracle"]["spec_oracle_verdict_counts"],
    "oracle_suite": comparison["oracle"]["oracle_suite_verdict_counts"],
    "issues": issues, "warnings": warnings,
}, ensure_ascii=False, indent=2))
raise SystemExit(0 if not issues else 1)
PY
CHECK_RC=$?
set -e
if [ "${CHECK_RC}" -ne 0 ]; then
    echo "  ✗ 核验发现阻断问题（见 ARM_COMPARISON.json issues）" >&2
    WARN_EXIT=5
else
    echo "  ✓ 核验通过（issues 为空）"
    WARN_EXIT=0
fi

# ─── README（数字全部来自工件） ─────────────────────────────────────────────
echo ""
echo "[6/7] 生成 README.md（协议/两臂表/注入与 verdict/一致性/成本/局限）"
"${PY}" - "${OUT}" "${RUN_STAMP}" "${ARM_BASELINE}" "${TASK_LIMIT}" "${PARALLELISM}" "${ONLY_CONTROL}" "${REUSE_ORACLE_BATCH}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
stamp, arm_baseline, task_limit, parallelism, only_control, reuse_oracle = sys.argv[2:8]
pre = json.loads((out / "PREFLIGHT.json").read_text(encoding="utf-8"))
cmp = json.loads((out / "ARM_COMPARISON.json").read_text(encoding="utf-8"))
mac = json.loads((out / "arm_control.meta.json").read_text(encoding="utf-8"))
meo = json.loads((out / "arm_oracle.meta.json").read_text(encoding="utf-8"))


def _fmt_rate(d):
    rate = (d or {}).get("rate")
    return "n/a" if rate is None else f"{rate * 100:.2f}%"


def _cost(x):
    return "n/a" if x is None else f"${x:.4f}"


lines: list[str] = []
add = lines.append
add("# O-2 oracle-enabled 二臂验证批（真 LLM，验证性测量，2026-10-17）")
add("")
add(f"> 运行 {stamp}；切点 worktree `{pre.get('code_root')}`，HEAD=`{pre.get('git_head')}`；")
add("> 本报告数字全部由脚本从两臂批次 JSON 直出（不手写）；协议见 §1。")
add("")
add("## 1. 协议（固定，验证性非 confirmatory）")
add("")
add(f"- 臂 A（control）：`--baselines {arm_baseline}`，oracle 关闭；臂 B（oracle）：同一 baseline + `SPEC_ORACLE_EXEC_ENABLE=true`；均不设 `DETECTION_SPEC_MODE`。")
add(f"- `--dataset quixbugs --task-limit {task_limit} --seed 42`；`AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM={parallelism}`。")
add("- `AITESTER_BATCH_MAX_CALLS=100 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE`。")
add(f"- 零 LLM 材料可行性探测：arm_can_inject_oracle=`{pre.get('material_probe', {}).get('arm_can_inject_oracle')}`；"
    f"no_anchor_verdict=`{pre.get('material_probe', {}).get('no_anchor_state', {}).get('verdict')}`；"
    f"spec_anchor_injected=`{pre.get('material_probe', {}).get('spec_anchor_state', {}).get('injected')}`。")
if pre.get("material_probe", {}).get("spec_anchor_state", {}).get("table_sha256"):
    add(f"- SPEC_ANCHOR_TABLE sha256=`{pre['material_probe']['spec_anchor_state']['table_sha256']}`（仅 arm_baseline=plain_llm_df_spec 时涉及）。")
add("- 调度：两臂**并发**执行（各 P" + str(parallelism) + "、独立 namespace/log/trace；主指标在任务阶段采集，次指标含并发 CPU 噪声）。")
if str(only_control) == "1":
    add("")
    add("> **sequential pairing 披露**：本轮为 **control-only 补跑**（attempt#2 的 control 臂在 MDO 后处理阶段撞 2400s 看门狗失败），")
    add(f"> oracle 臂批次**复用** attempt#2 已完成工件（`{reuse_oracle}`），未重跑。两臂同切点/同协议/独立 namespace，")
    add("> 但 control 补跑与 oracle 运行**不是同一并发时刻**（sequential pairing，非 same-batch concurrent），解释时须注意。")
if arm_baseline != "plain_llm_df":
    add("")
    add(f"**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `{arm_baseline}`。")
    add("原因：N-3 oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis / human_spec`；")
    add("`plain_llm_df` 无 planner（无 `test_plan`）且不加载锚表（无 `spec_anchor`）→ 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true`")
    add("只会记 `not_attempted`，无法验证 oracle 注入；`plain_llm_df_spec` 携带 `spec_anchor.logic_analysis`（随库 `SPEC_ANCHOR_TABLE`）")
    add("为可编译锚材料 → 才能真实验证 oracle-enabled 通道。**该修正属验证性协议修正，不改变任何判定规则/判分口径。**")
add("")
add("> **profile preset 陷阱（O-2 实测，AITESTER_PROFILE=logic）**：档位预设会用 `setdefault` 注入")
add("> `SPEC_ORACLE_EXEC_ENABLE=true`（`config.py` logic 预设）——关闭 oracle 的 control 臂必须**显式**")
add("> `SPEC_ORACLE_EXEC_ENABLE=false`，仅 unset 会被预设重新打开（O-2 首跑即因此 invalid，见附录 / `_invalid_control_attempt_20261018/`）。")
add("")
add("## 2. 两臂结果")
add("")
add("| 项 | A（control） | B（oracle） |")
add("|---|---|---|")
add(f"| baseline / namespace | `{mac.get('arm_baseline')}` / `{mac.get('cache_namespace')}` | `{meo.get('arm_baseline')}` / `{meo.get('cache_namespace')}` |")
add(f"| 批次工件 sha256 | `{str(mac.get('batch_sha256'))[:16]}…` | `{str(meo.get('batch_sha256'))[:16]}…` |")
add(f"| 行数 | {mac.get('rows')} | {meo.get('rows')} |")
add("| 墙钟(s) | 见 `log_control.log` START/END | 见 `log_oracle.log` START/END |")
tm_a, tm_b = mac.get("token_metrics") or {}, meo.get("token_metrics") or {}
add(f"| tokens（in/out/total） | {tm_a.get('total_input_tokens')}/{tm_a.get('total_output_tokens')}/{tm_a.get('total_tokens')} | {tm_b.get('total_input_tokens')}/{tm_b.get('total_output_tokens')}/{tm_b.get('total_tokens')} |")
add(f"| LLM calls / cache hits | {tm_a.get('total_llm_calls')}/{tm_a.get('total_cache_hits')} | {tm_b.get('total_llm_calls')}/{tm_b.get('total_cache_hits')} |")
add(f"| 成本（标准价上界） | {_cost(mac.get('cost_usd_standard_price'))} | {_cost(meo.get('cost_usd_standard_price'))} |")
add(f"| LLM-suite detection | {_fmt_rate(cmp['control']['llm_suite_detection'])} | {_fmt_rate(cmp['oracle']['llm_suite_detection'])} |")
add("")
add("## 3. oracle 注入与独立判读分布")
add("")
add("| 字段分布 | A（control） | B（oracle） |")
add("|---|---|---|")
add(f"| `spec_oracle_injected` | `{json.dumps(cmp['control']['spec_oracle_injected_counts'], ensure_ascii=False)}` | `{json.dumps(cmp['oracle']['spec_oracle_injected_counts'], ensure_ascii=False)}` |")
add(f"| `spec_oracle_verdict` | `{json.dumps(cmp['control']['spec_oracle_verdict_counts'], ensure_ascii=False)}` | `{json.dumps(cmp['oracle']['spec_oracle_verdict_counts'], ensure_ascii=False)}` |")
add(f"| `oracle_suite_verdict` | `{json.dumps(cmp['control']['oracle_suite_verdict_counts'], ensure_ascii=False)}` | `{json.dumps(cmp['oracle']['oracle_suite_verdict_counts'], ensure_ascii=False)}` |")
add("")
add("- 期望（材料可行性成立时）：B 臂 `spec_oracle_injected` 有 True/injected 行、`oracle_suite_verdict` 出现 correct/fp/silent/unavailable 分布；")
add("  O-1 加固后**崩溃应落 unavailable/skipped 而非 fp**（验证时请对照分布）。")
add("")
add("## 4. LLM-suite 一致性（oracle 不改变 LLM 检出）")
add("")
cons = cmp["llm_suite_consistency"]
add(f"- 两臂共同任务：{cons['common_tasks']}；逐任务 `detection_rate`/`llm_suite_detection_rate` 不一致：**{cons['mismatch_count']}**；")
add(f"- only_in_control={cons['only_in_control']}；only_in_oracle={cons['only_in_oracle']}。")
if cons["mismatches"]:
    add("")
    add("| task | control | oracle |")
    add("|---|---|---|")
    for mm in cons["mismatches"]:
        add(f"| `{mm['task_id']}` | {mm['control']} | {mm['oracle']} |")
add("")
add("## 5. provenance / env_snapshot / 完整性")
add("")
add("| 项 | A（control） | B（oracle） |")
add("|---|---|---|")
pa, pb = mac.get("provenance") or {}, meo.get("provenance") or {}
add(f"| git_sha / dirty | `{pa.get('git_sha')}` / {pa.get('git_dirty')} | `{pb.get('git_sha')}` / {pb.get('git_dirty')} |")
fa = (pa.get("model_fingerprint") or {}).get("pinned"); fb = (pb.get("model_fingerprint") or {}).get("pinned")
add(f"| fingerprint pinned / returned | {fa} / {(pa.get('model_fingerprint') or {}).get('returned_model')} | {fb} / {(pb.get('model_fingerprint') or {}).get('returned_model')} |")
add(f"| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `{pa.get('env_snapshot_spec_oracle_exec_enable')}` | `{pb.get('env_snapshot_spec_oracle_exec_enable')}` |")
add(f"| env_snapshot.DETECTION_SPEC_MODE | `{pa.get('env_snapshot_detection_spec_mode')}` | `{pb.get('env_snapshot_detection_spec_mode')}` |")
add(f"| 行字段完整率 | `{json.dumps(mac.get('field_completeness'), ensure_ascii=False)}` | `{json.dumps(meo.get('field_completeness'), ensure_ascii=False)}` |")
add("")
if cmp.get("issues"):
    add("**核验 issues（阻断）**：")
    for it in cmp["issues"]:
        add(f"- {it}")
else:
    add("核验 issues：无。")
if cmp.get("warnings"):
    add("")
    add("警告：")
    for it in cmp["warnings"]:
        add(f"- {it}")
add("")
add("## 6. 成本 / 墙钟 / 异常与局限")
add("")
add(f"- 两臂成本合计（标准价上界）≈ {_cost((mac.get('cost_usd_standard_price') or 0) + (meo.get('cost_usd_standard_price') or 0))}；预算 ≤$0.2。")
add("- 两臂并发 P4；墙钟以各臂日志 START/END 为准；验证性测量（非 confirmatory），小样本 20 任务不作显著性结论。")
add("- 局限：单模型/单数据集/单 seed；并发噪声影响次指标；oracle-suite 分类为机制侧描述性信号，不替代 LLM-suite detection 主判定。")
add("")
add("## 7. 复现")
add("")
add("```bash")
add("bash experiments/run_oracle_validation_batch.sh \\")
add(f"  --root <clean-worktree> --require-clean-root --arm-baseline {arm_baseline}")
add("# 判定/核验（零 LLM 复算）：读 arm_*.meta.json + ARM_COMPARISON.json")
add("```")
add("")
add("## 8. 文件")
add("")
add("| 文件 | 说明 |")
add("|---|---|")
add("| `log_control.log` / `log_oracle.log` | 两臂完整日志（命令/env/开始结束/git 状态） |")
add("| `benchmark_quixbugs_*.json` | 两臂批次工件 |")
add("| `arm_control.meta.json` / `arm_oracle.meta.json` | 每臂结构化元数据（token/成本/字段/逐任务） |")
add("| `ARM_COMPARISON.json` | 一致性/注入分布/核验 issues |")
add("| `PREFLIGHT.json` | 切点/门禁/材料可行性探测 |")
add("| `traces_control/` / `traces_oracle/` | 逐任务 trace |")
add("| `SHA256SUMS` | checksum_results.py --write 生成 |")
add("")
(out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"README：{out / 'README.md'}")
PY

# ─── SHA256SUMS（任务书指定 checksum_results.py --write） ───────────────────
echo ""
echo "[7/7] SHA256SUMS（checksum_results.py --write）+ 收尾"
CHECKSUM_TOOL="${ROOT}/scripts/gates/checksum_results.py"
if [ -f "${CHECKSUM_TOOL}" ]; then
    set +e
    ( cd "${ROOT}" && "${PY}" "${CHECKSUM_TOOL}" --results-dir "${OUT}" --write ) 2>&1 | tail -3
    SUMS_RC=${PIPESTATUS[0]}
    set -e
    if [ "${SUMS_RC}" -ne 0 ]; then
        echo "  ⚠️ checksum_results.py 失败（exit ${SUMS_RC}），回退 python 递归哈希" >&2
        "${PY}" - "${OUT}" <<'PY'
import hashlib, sys
from pathlib import Path
out = Path(sys.argv[1])
lines = []
for p in sorted(out.rglob('*')):
    if not p.is_file() or p.name == 'SHA256SUMS':
        continue
    lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}")
(out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f"SHA256SUMS（fallback）：{len(lines)} 条")
PY
    fi
else
    echo "  ⚠️ 未找到 ${CHECKSUM_TOOL}，回退 python 递归哈希" >&2
    "${PY}" - "${OUT}" <<'PY'
import hashlib, sys
from pathlib import Path
out = Path(sys.argv[1])
lines = []
for p in sorted(out.rglob('*')):
    if not p.is_file() or p.name == 'SHA256SUMS':
        continue
    lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}")
(out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f"SHA256SUMS（fallback）：{len(lines)} 条")
PY
fi
WALL_TOTAL=$(( $(date +%s) - START_ALL_EPOCH ))
GIT_STATUS_POST="$(git -C "${ROOT}" status --porcelain 2>/dev/null || true)"

echo ""
echo "================================================================================"
echo "O-2 验证批完成（RUN_STAMP=${RUN_STAMP}）"
echo "  切点：${ROOT_GIT_HEAD}（跑后 dirty 行数=$(printf '%s\n' "${GIT_STATUS_POST}" | grep -c . || true)）"
echo "  两臂 exit：control=${RC_A} oracle=${RC_B}；总墙钟 ${WALL_TOTAL}s（$((WALL_TOTAL / 60))min）"
echo "  control：${BATCH_A}"
echo "  oracle ：${BATCH_B}"
echo "  README：${OUT}/README.md"
echo "  SHA256SUMS：${OUT}/SHA256SUMS"
echo "  核验：ARM_COMPARISON.json（issues 见 README §5）"
echo "  预算：≤\$0.2；若超预算/异常见 README §6"
echo "================================================================================"
if [ "${WARN_EXIT}" -ne 0 ]; then
    echo "⚠️ 收尾告警（exit=${WARN_EXIT}）：见 README §5 与 ARM_COMPARISON.json"
    exit "${WARN_EXIT}"
fi
exit 0
