import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
stamp, arm_baseline, task_limit, parallelism = sys.argv[2:6]
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
if arm_baseline != "plain_llm_df":
    add("")
    add(f"**验证性协议修正（Lead 批准 2026-10-17，方案 a）**：任务书默认 baseline `plain_llm_df` 修正为 `{arm_baseline}`。")
    add("原因：N-3 oracle 材料优先级 = `spec_ir` → `test_plan.logic_analysis` → `spec_anchor.logic_analysis / human_spec`；")
    add("`plain_llm_df` 无 planner（无 `test_plan`）且不加载锚表（无 `spec_anchor`）→ 材料为空 → `SPEC_ORACLE_EXEC_ENABLE=true`")
    add("只会记 `not_attempted`，无法验证 oracle 注入；`plain_llm_df_spec` 携带 `spec_anchor.logic_analysis`（随库 `SPEC_ANCHOR_TABLE`）")
    add("为可编译锚材料 → 才能真实验证 oracle-enabled 通道。**该修正属验证性协议修正，不改变任何判定规则/判分口径。**")
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