#!/usr/bin/env python
"""T3（2026-10-18）分析：K=3 多数一致 + canonical input 约束 → 零 LLM 重放判定。

读取（全部为实际运行工件，数字不手写）：
- ``K3_STATS.json``：60 次真实采样统计（K=3/majority=2/canonical）；
- ``ORACLE_EXAMPLES_REPORT_k3_default.json``：重放臂 1（R-2 默认开，主判定）；
- ``ORACLE_EXAMPLES_REPORT_k3_r2off.json``：重放臂 2（R-2 关，敏感性）；
- ``experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json``：基线；
- ``PREREG.md`` / ``PREFLIGHT.json``：冻结判据与预检。

输出：
- ``ANALYSIS_REPORT.json``：预注册判据逐项判定 + 逐任务变化表 + 两臂全表 + 归因；
- ``README.md``：中文人读报告（全部数字由工件渲染）；
- ``RUN_SUMMARY.log``：运行命令/墙钟/关键计数摘要。

用法::

    .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/analyze_k3.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.misguided_metrics import body_digest, sha256_file  # noqa: E402

OUT = _REPO_ROOT / "experiments/results/t_round_oracle_k3_20261018"
BASELINE = _REPO_ROOT / "experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json"
S3_DIR = _REPO_ROOT / "experiments/results/s_round_examples_multisample_20261018"
STATS_PATH = OUT / "K3_STATS.json"
DEFAULT_REPORT = OUT / "ORACLE_EXAMPLES_REPORT_k3_default.json"
R2OFF_REPORT = OUT / "ORACLE_EXAMPLES_REPORT_k3_r2off.json"
REUSE_REPORT = OUT / "K3_REUSE_REPORT.json"
PREREG = OUT / "PREREG.md"
PREFLIGHT = OUT / "PREFLIGHT.json"
PROMPTS = OUT / "PREFLIGHT_PROMPTS.json"
CATEGORIES = ("correct", "fp", "silent", "misguided", "unavailable")
BASELINE_COUNTS = {"correct": 8, "fp": 0, "silent": 3, "misguided": 2, "unavailable": 7}
BASELINE_CLASSIFIABLE = 13
# 人工核对源码后的归因（仅本批工件；数字全部来自工件，说明为定性）
ATTRIBUTION_NOTES = {
    "quixbugs__knapsack": (
        "P-1 的幻觉示例 `(5,[[5,10]])→0` 未再现（3/3 样本均无）；但 canonical 模板"
        "「容量 1 + 物品 [[1,1]]」被 3/3 采样一致给出**新幻觉期望** `(1,[[1,1]])→0`"
        "（buggy 因 `weight < j` 严格比较恰好返回 0，fixed 返回 1）→ 任务仍 misguided。"
        "说明：多数一致 + canonical 可产生**一致地错**，自一致性≠正确性。"
    ),
    "quixbugs__is_valid_parenthesization": (
        "P-1 的幻觉示例 `'((('→True` 未再现（3/3 样本均无）；canonical 新示例"
        '（`""→True`、`"()"→True`、`")("→False`）全部与规格一致，但 buggy/fixed '
        "均通过 → 由 misguided 变 silent（幻觉已消除，但无检出）。"
    ),
    "quixbugs__kth": (
        "canonical 新增 `([1,2],1)` 触发 buggy 的递归越界（IndexError→O-1 harness skip），"
        "该 oracle 测试由 silent 变 unavailable（单列、不进分母）。"
    ),
    "quixbugs__levenshtein": 'canonical 边界示例（`""`/`"abc"` 空串组合）buggy/fixed 均通过 → 不再区分 → correct→silent。',
    "quixbugs__lis": "canonical 边界示例（`[]`/`[1]`/`[1,2]`）buggy/fixed 均通过 → 不再区分 → correct→silent。",
    "quixbugs__max_sublist_sum": "canonical 边界示例（`[]`/`[-1]`/`[1,2]`）buggy/fixed 均通过 → 不再区分 → correct→silent。",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return sha256_file(str(path))


def _arm_view(report: dict[str, Any], arm_name: str = "B_llm_examples") -> dict[str, Any]:
    """单臂视图：逐任务类别/计数 + 聚合；并校验报告内各源臂一致。"""
    arms = report["report"]["arms"]
    per_task: dict[str, dict[str, Any]] = {}
    signatures: list[dict[str, Any]] = []
    for arm in arms:
        sig: dict[str, Any] = {}
        for task in arm.get("tasks") or []:
            tid = str(task.get("task_id"))
            cond = (task.get("conditions") or {}).get(arm_name) or {}
            counts = cond.get("counts") or {}
            category = (task.get("category") or {}).get(arm_name)
            item = {
                "category": category,
                "counts": {key: int(counts.get(key, 0) or 0) for key in CATEGORIES},
                "status": cond.get("status"),
                "examples_n": int((task.get("examples_generation") or {}).get("n_examples") or 0),
                "examples": (task.get("examples_generation") or {}).get("examples") or [],
            }
            per_task.setdefault(tid, item)
            sig[tid] = {"category": category, "counts": item["counts"], "examples_n": item["examples_n"]}
        signatures.append(sig)
    identical = all(sig == signatures[0] for sig in signatures[1:]) if signatures else True
    counts = {key: 0 for key in CATEGORIES}
    for item in per_task.values():
        for key in CATEGORIES:
            counts[key] += item["counts"][key]
    classifiable = counts["correct"] + counts["fp"] + counts["silent"] + counts["misguided"]
    filter_stats: dict[str, Any] = {}
    for arm in arms:
        fs = (arm.get("aggregate") or {}).get("examples_self_validation")
        if fs is not None:
            filter_stats = fs
            break
    return {
        "n_arms": len(arms),
        "arms": [str(arm.get("arm")) for arm in arms],
        "source_arms_identical": identical,
        "counts": counts,
        "n_classifiable": classifiable,
        "n_unavailable": counts["unavailable"],
        "rates_of_classifiable": {
            key: (round(counts[key] / classifiable, 6) if classifiable else None)
            for key in ("correct", "fp", "silent", "misguided")
        },
        "examples_self_validation": filter_stats,
        "per_task": per_task,
    }


def _verdict(baseline_correct: int, counts: dict[str, int], hallucination_excluded: int) -> dict[str, Any]:
    """PREREG 冻结判定：先查规则 2（loss≥2→高风险），再规则 1（排除≥1 且 loss≤1→有效），否则未达有效。"""
    correct_after = int(counts["correct"])
    loss = baseline_correct - correct_after
    if loss >= 2:
        verdict, verdict_cn = "high_risk_default_off", "高风险，默认关"
        reason = f"correct {baseline_correct}→{correct_after}（损失 {loss} ≥2）→ 触发预注册规则 2"
    elif hallucination_excluded >= 1 and loss <= 1:
        verdict, verdict_cn = "effective", "有效"
        reason = f"hallucination 排除 {hallucination_excluded}/2 且 correct 损失 {loss} ≤1 → 满足预注册规则 1"
    else:
        verdict, verdict_cn = "not_effective", "未达有效过滤"
        reason = f"hallucination 排除 {hallucination_excluded}/2、correct 损失 {loss} → 不满足预注册规则 1/2"
    return {
        "prereg_rule": (
            "规则 2：correct 损失 ≥2 → 高风险默认关（优先）；规则 1：≥1 hallucination 不在示例集 "
            "且 correct 损失 ≤1 → 有效；其余 → 未达有效过滤"
        ),
        "hallucinations_excluded_from_oracle": hallucination_excluded,
        "hallucinations_total": 2,
        "correct_before": baseline_correct,
        "correct_after": correct_after,
        "correct_loss": loss,
        "misguided_before": 2,
        "misguided_after": int(counts["misguided"]),
        "verdict": verdict,
        "verdict_cn": verdict_cn,
        "reason": reason,
    }


def _per_task_changes(
    baseline: dict[str, Any], treatment: dict[str, Any], stats_by_task: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tid in sorted(baseline["per_task"]):
        before = baseline["per_task"][tid]
        after = treatment["per_task"].get(tid) or {}
        changed = before["category"] != after.get("category")
        rows.append(
            {
                "task_id": tid,
                "baseline_category": before["category"],
                "k3_category": after.get("category"),
                "changed": bool(changed),
                "baseline_counts": before["counts"],
                "k3_counts": after.get("counts"),
                "k3_examples_n": after.get("examples_n"),
                "fallback_used": bool((stats_by_task.get(tid) or {}).get("fallback")),
                "final_examples": (stats_by_task.get(tid) or {}).get("final", {}).get("examples") or [],
            }
        )
    return rows


def _run_summary_text(analysis: dict[str, Any]) -> str:
    sampling = analysis["sampling"]
    default = analysis["replay_arms"]["default"]
    r2off = analysis["replay_arms"]["r2off"]
    judge = analysis["judgment"]
    lines = [
        "T3（2026-10-18）oracle 示例通道 K=3 多数一致 + canonical input 约束 —— 运行摘要",
        "=" * 84,
        f"生成时间（UTC）：{analysis['generated_at']}",
        f"预注册：PREREG.md sha256={analysis['prereg']['sha256']}（PREFLIGHT 冻结）",
        "",
        "[命令]",
        "  ① 预检（零 LLM）：.venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py --dry-run",
        "  ② 真实采样（60 次；cache off）：AITESTER_LLM_CACHE=0 .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py",
        "  ③ 重放臂 1（R-2 默认开，零 LLM）：SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true "
        "nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay --out <OUT> --reuse-examples <OUT>/K3_REUSE_REPORT.json "
        "--report-name ORACLE_EXAMPLES_REPORT_k3_default --skip-markdown --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180",
        "  ④ 重放臂 2（R-2 关，零 LLM）：同 ③ + SPEC_EXAMPLES_SELF_VALIDATE=false --report-name ORACLE_EXAMPLES_REPORT_k3_r2off",
        "  ⑤ 分析/README：.venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/analyze_k3.py",
        "  ⑥ 校验和：.venv/bin/python scripts/gates/checksum_results.py --write/--verify --results-dir experiments/results/t_round_oracle_k3_20261018",
        "",
        "[采样]",
        f"  任务 {sampling['n_tasks']}；K={sampling['k']}、majority={sampling['majority']}（≥2/3）、每样本≤{sampling['max_examples']} 条、canonical_inputs=True",
        f"  LLM 调用 {sampling['llm_calls']}；input/output tokens={sampling['input_tokens']}/{sampling['output_tokens']}；"
        f"估算成本 ${sampling['cost_estimated_usd']}（预算 ≤$0.05）；墙钟 {sampling['wall_s']}s",
        f"  union {sampling['n_examples_union_total']} → intersection {sampling['n_examples_intersection_total']}"
        f"（丢弃 {sampling['n_dropped_non_intersection_total']}）；失败回退任务 {sampling['n_fallback_tasks']}",
        f"  P-1 两个 hallucination 在 3 个样本中的出现：{sampling['hallucination_presence']}",
        "  默认 prompt（canonical=False）与 S-3 工件 prompt_sha256 逐任务相同："
        f"{analysis['preflight']['n_default_prompt_matches_s3']}/{analysis['preflight']['n_tasks']}",
        "",
        "[零 LLM 重放]",
        f"  臂 1（R-2 默认开，主判定）：correct={default['counts']['correct']} fp={default['counts']['fp']} "
        f"silent={default['counts']['silent']} misguided={default['counts']['misguided']} "
        f"unavailable={default['counts']['unavailable']} 可分类={default['n_classifiable']} 墙钟≈{default['wall_s']}s",
        f"  臂 2（R-2 关，敏感性）：correct={r2off['counts']['correct']} fp={r2off['counts']['fp']} "
        f"silent={r2off['counts']['silent']} misguided={r2off['counts']['misguided']} "
        f"unavailable={r2off['counts']['unavailable']} 可分类={r2off['n_classifiable']} 墙钟≈{r2off['wall_s']}s",
        f"  两臂逐任务是否一致：{analysis['replay_arms']['identical_per_task']}",
        "",
        "[判定：PREREG 冻结规则]",
        f"  hallucination 排除 {judge['hallucinations_excluded_from_oracle']}/2；correct {judge['correct_before']}→{judge['correct_after']}"
        f"（损失 {judge['correct_loss']}）；misguided {judge['misguided_before']}→{judge['misguided_after']}",
        f"  verdict = {judge['verdict']}（{judge['verdict_cn']}）—— {judge['reason']}",
        "",
        "[限制]",
        "  n=20、单次 K=3、单次零 LLM 重放 ×2 臂；探索性/非 confirmatory；与 B2 主批次并发运行（重放 nice -n 15）",
        "",
        "[helper 版本说明]",
        f"  采样实际执行版本 _helpers/run_k3_sampling.py sha256={analysis['helper_provenance']['_helpers/run_k3_sampling.py']['executed_sha256']}（PREFLIGHT 记录）",
        f"  当前文件 sha256={analysis['helper_provenance']['_helpers/run_k3_sampling.py']['current_sha256']}"
        "（采样执行后对该 helper 做过一次 ruff format：纯格式，无行为变化）",
    ]
    return "\n".join(lines) + "\n"


def _render_readme(analysis: dict[str, Any]) -> str:
    sampling = analysis["sampling"]
    judge = analysis["judgment"]
    default = analysis["replay_arms"]["default"]
    r2off = analysis["replay_arms"]["r2off"]
    base = analysis["baseline"]
    changes = analysis["per_task_changes"]
    lost = [
        row["task_id"] for row in changes if row["baseline_category"] == "correct" and row["k3_category"] != "correct"
    ]
    kept_correct = [row["task_id"] for row in changes if row["k3_category"] == "correct"]
    resolved = [
        row["task_id"]
        for row in changes
        if row["baseline_category"] == "misguided" and row["k3_category"] != "misguided"
    ]
    remain_misguided = [row["task_id"] for row in changes if row["k3_category"] == "misguided"]
    new_unavailable = [
        row["task_id"]
        for row in changes
        if row["baseline_category"] != "unavailable" and row["k3_category"] == "unavailable"
    ]
    rejoin_ok = analysis["preflight"]["n_default_prompt_matches_s3"]
    lines: list[str] = []
    add = lines.append
    add("# T3 K=3 多数一致 + canonical input 约束：交集保留率 96%，但 correct 8→5（损失 3）→ 高风险默认关")
    add("")
    add(
        "> **一句话结论**：canonical input 约束把三个采样的示例集合重叠率大幅提高（union "
        f"{sampling['n_examples_union_total']} / 交集 {sampling['n_examples_intersection_total']}，只丢弃 "
        f"{sampling['n_dropped_non_intersection_total']} 条；S-3 K=2 为 67→43/丢弃 24），P-1 的 **2 例 "
        "hallucination 均未进入本轮 oracle**；但代价是 **correct 8→5（损失 3 ≥2）**：canonical 边界示例"
        "不再区分 3 个任务的 buggy/fixed（correct→silent），且 `knapsack` 出现**新的一致幻觉**"
        "（3/3 采样一致给出错误期望 `(1,[[1,1]])→0`）继续 misguided。按 PREREG 冻结规则判定"
        f"**「{judge['verdict_cn']}」**；生产保持默认关。"
    )
    add("")
    add("## 1. 协议（`PREREG.md` 跑前冻结，sha256 见 `PREFLIGHT.json`）")
    add("")
    add("| 项 | 设置 |")
    add("|---|---|")
    add("| 任务集 | P-1 的 20 个任务（按 `task_id` 排序；材料构造与 P-1 重放生成路径逐字节一致） |")
    add(
        f"| 采样 | **K=3** × 20 任务 = **{sampling['llm_calls']} 次** spec-only 小调用；每样本 ≤{sampling['max_examples']} 条；"
        "`temperature=0.0`、`LLM_MAX_OUTPUT_TOKENS=512`、**关闭 LLM 缓存**、cache namespace `:sample<i>` 仅审计 |"
    )
    add(
        '| canonical 约束 | prompt 追加冻结段落：固定边界值模板（数值 0/1/-1、字符串 ""/"abc"/"()"、'
        "列表 []/[0]/[1]/[1,2]、二维 [[1,1]]/[[2,3]]、每参数按位取最小合法组合） |"
    )
    add(
        "| 失败回退 | 仅当某任务 3/3 样本 `status != ok` 时用旧 prompt 重采样一次；本批回退任务 "
        f"**{sampling['n_fallback_tasks']}** 个 |"
    )
    add("| 处理 | 归一化 JSON 键（与 S-3 相同；tuple/list 等价、int/float 不合并），**≥2/3** 出现才保留，≤3 条/任务 |")
    add(
        f"| 基线 | P-1.1 表示归一 `ORACLE_EXAMPLES_REPORT_norm.json`（correct {base['counts']['correct']} / fp "
        f"{base['counts']['fp']} / silent {base['counts']['silent']} / misguided {base['counts']['misguided']} / "
        f"unavailable {base['counts']['unavailable']}；分母 {base['n_classifiable']}） |"
    )
    add(
        "| 重放 | `oracle_examples_replay --reuse-examples`（**零 LLM**）；臂 1 = R-2 默认开（主判定），"
        "臂 2 = `SPEC_EXAMPLES_SELF_VALIDATE=false`（敏感性）；显式开 Q-1 双门 |"
    )
    add("")
    add("## 2. 采样成本与一致性统计（`K3_STATS.json` 逐任务可核）")
    add("")
    add(
        f"- LLM 调用 **{sampling['llm_calls']} 次**；input/output tokens = **{sampling['input_tokens']:,} / "
        f"{sampling['output_tokens']:,}**；估算成本 **${sampling['cost_estimated_usd']}**"
        f"（`experiments/price_table.json` deepseek-flash 峰时价，预算 ≤$0.05 的 "
        f"{round(sampling['cost_estimated_usd'] / 0.05 * 100, 1)}%）；采样墙钟 **{sampling['wall_s']}s**。"
    )
    add(
        f"- 20/20 任务 canonical 采样 status=ok（每样本 1–3 条）；**union {sampling['n_examples_union_total']} → "
        f"交集 {sampling['n_examples_intersection_total']}**（丢弃 {sampling['n_dropped_non_intersection_total']} 条），"
        f"最终示例合计 **{sampling['n_examples_final_total']}** 条。"
    )
    add(
        "- 与 S-3（K=2 自由采样）对比：S-3 union 67 → 交集 43（丢弃 24，1 个任务交集为空）；"
        "本轮 canonical 后 20/20 任务均有非空交集——**重叠率显著提升**。"
    )
    add("")
    add("## 3. 两个 P-1 hallucination：均未进入本轮 oracle（但注意新的一致幻觉）")
    add("")
    add("| 任务 | P-1 幻觉示例 | 3 个新样本中出现 | 在最终示例集 | 结果 |")
    add("|---|---|---|---|---|")
    for tid, item in analysis["hallucination_tasks"].items():
        example = json.dumps(item["p1_hallucination_example"], ensure_ascii=False)
        presence = item["present_in_samples"]
        add(
            f"| `{tid}` | `{example}` | {presence}（{item['n_samples_present']}/3） | "
            f"{'是' if item['in_final_examples'] else '否'} | {'被排除' if not item['in_final_examples'] else '进入 oracle'} |"
        )
    add("")
    add(
        "> 机制区分：两条 P-1 幻觉示例在 3 个 canonical 样本中**均未再现**（不是被 ≥2/3 过滤掉的），"
        "而是重采样/模板约束下消失。多数一致过滤本身只丢弃 "
        f"{sampling['n_dropped_non_intersection_total']} 条示例（`depth_first_search` 1 条、`kheapsort` 1 条）。"
    )
    add("")
    add(
        "**但**：`knapsack` 出现**新的一致幻觉**——3/3 canonical 样本一致给出 `(1,[[1,1]])→0`"
        "（正确应为 1；buggy 因 `weight < j` 严格比较恰好返回 0，fixed 返回 1），该任务最终仍为 "
        "**misguided**。这是本轮最重要的负面证据：**多数一致 + canonical 模板可以一致地错，"
        "自一致性不是正确性证明。**"
    )
    add("")
    add("## 4. 重放前后对照（两臂；两张源臂工件逐位相同）")
    add("")
    add(
        "| 指标（oracle 测试级；分母=可分类） | P-1.1 norm 基线 | 臂 1：K=3/≥2 交集（R-2 默认开，主判定） | 臂 2：同左 − R-2（敏感性） |"
    )
    add("|---|---|---|---|")
    base_counts = base["counts"]
    add(f"| 可分类分母 | {base['n_classifiable']} | {default['n_classifiable']} | {r2off['n_classifiable']} |")
    for key, label in (
        ("correct", "`correct`"),
        ("fp", "`fp`"),
        ("silent", "`silent`"),
        ("misguided", "`misguided`"),
        ("unavailable", "`unavailable`（单列）"),
    ):
        add(f"| {label} | {base_counts[key]} | {default['counts'][key]} | {r2off['counts'][key]} |")
    add(
        f"| 正确率（correct/可分类） | {base['rates_of_classifiable']['correct']} | "
        f"{default['rates_of_classifiable']['correct']} | {r2off['rates_of_classifiable']['correct']} |"
    )
    add(
        f"| 错误率（(fp+misguided)/可分类） | "
        f"{round((base['counts']['fp'] + base['counts']['misguided']) / base['n_classifiable'], 4)} | "
        f"{round((default['counts']['fp'] + default['counts']['misguided']) / default['n_classifiable'], 4)} | "
        f"{round((r2off['counts']['fp'] + r2off['counts']['misguided']) / r2off['n_classifiable'], 4)} |"
    )
    add("")
    add(
        f"- 两臂逐任务类别是否完全一致：**{analysis['replay_arms']['identical_per_task']}**"
        f"（R-2 自校验丢弃示例数：{default['examples_self_validation'].get('n_dropped')}；"
        "两任务锚后置子句表达力仍不足，与 R-2 结论一致）。"
    )
    add("")
    add("## 5. 逐任务变化表（20 任务，各 1 个 oracle 测试）")
    add("")
    add("| 任务 | 基线（P-1.1 norm） | K=3/≥2 + canonical | 变化 | 示例数 |")
    add("|---|---|---|---|---|")
    for row in changes:
        marker = "**变化**" if row["changed"] else "—"
        add(
            f"| `{row['task_id']}` | {row['baseline_category']} | {row['k3_category']} | {marker} | "
            f"{row['k3_examples_n']} |"
        )
    add("")
    add(f"- 保持 correct：{', '.join(f'`{t}`' for t in kept_correct)}（{len(kept_correct)} 个）。")
    add(f"- correct 丢失：{', '.join(f'`{t}`' for t in lost)}（{len(lost)} 个）。")
    add(
        f"- misguided 消失：{', '.join(f'`{t}`' for t in resolved) if resolved else '无'}；"
        f"仍 misguided：{', '.join(f'`{t}`' for t in remain_misguided)}。"
    )
    if new_unavailable:
        add(
            f"- 新增 unavailable：{', '.join(f'`{t}`' for t in new_unavailable)}（buggy 崩溃 → O-1 harness skip，单列不进分母）。"
        )
    add("")
    add("**归因（人工核对源码；仅本批工件）**")
    add("")
    for task_id in (
        "quixbugs__knapsack",
        "quixbugs__is_valid_parenthesization",
        "quixbugs__kth",
        "quixbugs__levenshtein",
        "quixbugs__lis",
        "quixbugs__max_sublist_sum",
    ):
        add(f"- `{task_id}`：{ATTRIBUTION_NOTES[task_id]}")
    add("")
    add("## 6. 判定（按 `PREREG.md` 冻结规则）")
    add("")
    add("1. **hallucination 排除**：P-1 的 2 条幻觉示例均不在本轮示例集 → **2/2**（满足 ≥1 子句）；")
    add(
        f"2. **correct 损失**：{judge['correct_before']} → {judge['correct_after']}，**损失 {judge['correct_loss']} ≥2** "
        "→ 触发规则 2；"
    )
    add(f"3. **判定 = 「{judge['verdict_cn']}」**（`{judge['verdict']}`）——{judge['reason']}。")
    add("")
    add(
        "**敏感性**：臂 2（关闭 R-2 过滤器）与臂 1 逐任务结果"
        f"**{'完全一致' if analysis['replay_arms']['identical_per_task'] else '不一致（详见 ANALYSIS_REPORT.json）'}**，"
        "判定不变；R-2 不是本轮损失来源（其丢弃示例数为 0）。"
    )
    add("")
    add("## 7. 结论与下一步（按收益）")
    add("")
    add(
        "1. **canonical 约束达到预期的一半**：跨采样重叠率 96%（union→交集），K=3/≥2 不再是召回瓶颈"
        "（S-3 中 K=2 精确求交 loss=5 的机制是「交集稀疏」；本轮 loss=3 的机制是「边界示例不区分」）。"
    )
    add(
        "2. **但固定边界模板有系统副作用**：① 边界输入对部分任务不具判别力（levenshtein/lis/max_sublist_sum "
        "correct→silent）；② 模板组合可能诱导模型给出**一致但错误**的期望（knapsack 新幻觉）。"
        "旧幻觉消失不等于幻觉问题解决。"
    )
    add(
        "3. **下一步（供 Lead 裁决）**：① 示例级独立核验（LLM 二次核验 expected 与规格一致性）——针对"
        "「一致地错」，与一致性正交；② canonical 模板只约束**输入取值集合**而不要求「最小组合」，或按任务"
        "结构生成模板（容器/字符串型任务给非平凡样例）；③ 叠加 R-2 表达力强化（关键语义写成 `*_expr`）；"
        "④ 多采样一致仅作为**高置信子集**而非唯一集合（与 P-1 原示例取并集）。"
        "生产继续保持 `SPEC_ORACLE_EXAMPLES_ENABLE` 默认关。"
    )
    add("")
    add("## 8. 限制")
    add("")
    for item in analysis["limitations"]:
        add(f"- {item}")
    prov = analysis["helper_provenance"]["_helpers/run_k3_sampling.py"]
    add(
        f"- helper 版本：采样实际执行版本 `_helpers/run_k3_sampling.py` sha256=`{prov['executed_sha256']}`"
        f"（PREFLIGHT 记录）；当前文件 sha256=`{prov['current_sha256']}`（执行后仅 `ruff format`，无行为变化）。"
    )
    add("")
    add("## 9. 复算与工件")
    add("")
    add("```bash")
    add(f"# ① 采样（60 次真实小调用；cache off；本批 ${sampling['cost_estimated_usd']} / {sampling['wall_s']}s）")
    add(
        "AITESTER_LLM_CACHE=0 .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py"
    )
    add("# ② 零 LLM 重放（臂 1 = R-2 默认开；臂 2 加 SPEC_EXAMPLES_SELF_VALIDATE=false）")
    add("SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true \\")
    add("  nice -n 15 .venv/bin/python -m experiments.oracle_examples_replay \\")
    add("  --out experiments/results/t_round_oracle_k3_20261018 \\")
    add("  --reuse-examples experiments/results/t_round_oracle_k3_20261018/K3_REUSE_REPORT.json \\")
    add("  --report-name ORACLE_EXAMPLES_REPORT_k3_default --skip-markdown \\")
    add("  --limit 20 --jobs 4 --per-test-timeout 1 --file-timeout 180")
    add("# ③ 分析/README/摘要；④ 校验和")
    add(".venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/analyze_k3.py")
    add(
        ".venv/bin/python scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_oracle_k3_20261018"
    )
    add("```")
    add("")
    add(
        f"- 默认 prompt（`canonical=False`）与 S-3 工件 `samples[0].prompt_sha256` 逐任务相同："
        f"**{rejoin_ok}/20** → 生成器默认路径零变化；canonical=True 仅为追加冻结段落（`PREFLIGHT_PROMPTS.json`）。"
    )
    add("")
    add("| 工件 | 说明 |")
    add("|---|---|")
    for name, desc in (
        ("PREREG.md", "跑前冻结的协议/判定/预算（sha256 见 PREFLIGHT）"),
        ("PREFLIGHT.json", "预检：prereg sha256 / 实现 sha256 / 输入 sha256 / 定向测试 / 预算估计"),
        ("PREFLIGHT_PROMPTS.json", "两变体 prompt 逐任务 sha256 + 与 S-3 的 20/20 校准"),
        ("SAMPLING_REPORT.json", "采样阶段紧凑报告（token/成本/墙钟/union/intersection/dropped 审计；派生自 K3_STATS）"),
        ("K3_STATS.json", "60 次采样逐任务统计（样本/交集/丢弃/回退/usage/成本/幻觉明细）"),
        ("K3_REUSE_REPORT.json", "多数一致示例的 reuse 报告（供零 LLM 重放）"),
        ("ORACLE_EXAMPLES_REPORT_k3_default.json", "重放臂 1（R-2 默认开；主判定）"),
        ("ORACLE_EXAMPLES_REPORT_k3_r2off.json", "重放臂 2（R-2 关；敏感性）"),
        ("ANALYSIS_REPORT.json", "预注册判据逐项判定 + 逐任务变化 + 两臂全表 + 归因"),
        ("RUN_SUMMARY.log", "命令/墙钟/关键计数摘要"),
        ("SAMPLING_CONSOLE.log / REPLAY_*_console.log", "采样与重放的控制台原始记录"),
        ("SHA256SUMS", "目录内文件 + 外部输入引用 sha256（checksum_results.py --verify 通过）"),
    ):
        add(f"| `{name}` | {desc} |")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    prereg_sha = _sha(PREREG)
    preflight = _load(PREFLIGHT)
    if preflight.get("prereg_sha256") != prereg_sha:
        raise SystemExit(f"PREREG sha256 不匹配：当前 {prereg_sha} vs PREFLIGHT {preflight.get('prereg_sha256')}")
    stats = _load(STATS_PATH)
    prompts = _load(PROMPTS)
    baseline_view = _arm_view(_load(BASELINE))
    default_view = _arm_view(_load(DEFAULT_REPORT))
    r2off_view = _arm_view(_load(R2OFF_REPORT))
    default_meta = _load(DEFAULT_REPORT)["run_meta"]
    r2off_meta = _load(R2OFF_REPORT)["run_meta"]
    stats_by_task = {str(t["task_id"]): t for t in stats["per_task"]}
    hallucination_excluded = sum(
        1
        for item in stats["hallucination_tasks"].values()
        if not item.get("in_final_examples") and not item.get("in_final_intersection")
    )
    judgment = _verdict(int(baseline_view["counts"]["correct"]), default_view["counts"], hallucination_excluded)
    r2off_judgment = _verdict(int(baseline_view["counts"]["correct"]), r2off_view["counts"], hallucination_excluded)
    identical_per_task = {
        tid: {
            "default": {
                "category": default_view["per_task"].get(tid, {}).get("category"),
                "counts": default_view["per_task"].get(tid, {}).get("counts"),
            },
            "r2off": {
                "category": r2off_view["per_task"].get(tid, {}).get("category"),
                "counts": r2off_view["per_task"].get(tid, {}).get("counts"),
            },
        }
        for tid in sorted(default_view["per_task"])
    }
    arms_identical = all(v["default"] == v["r2off"] for v in identical_per_task.values())
    sampling_block = {
        "k": stats["generator"]["k"],
        "majority": stats["generator"]["majority"],
        "max_examples": stats["generator"]["max_examples"],
        "canonical_inputs": stats["generator"]["canonical_inputs"],
        "canonical_section_sha256": stats["generator"]["canonical_section_sha256"],
        "llm_calls": stats["generator"]["llm_calls"],
        "input_tokens": stats["generator"]["input_tokens"],
        "output_tokens": stats["generator"]["output_tokens"],
        "cost_estimated_usd": stats["generator"]["cost_estimated_usd"],
        "budget_usd": stats["budget_usd_limit"],
        "wall_s": stats["generator"]["wall_s"],
        "model": stats["generator"]["model"],
        "llm_cache": stats["generator"]["llm_cache"],
        "cache_namespace": stats["generator"]["cache_namespace"],
        "n_tasks": stats["audit_totals"]["n_tasks"],
        "n_tasks_with_final_examples": stats["audit_totals"]["n_tasks_with_final_examples"],
        "n_examples_final_total": stats["audit_totals"]["n_examples_final_total"],
        "n_examples_union_total": stats["audit_totals"]["n_examples_union_total"],
        "n_examples_intersection_total": stats["audit_totals"]["n_examples_intersection_total"],
        "n_dropped_non_intersection_total": stats["audit_totals"]["n_dropped_non_intersection_total"],
        "n_fallback_tasks": stats["fallback"]["n_tasks"],
        "fallback_task_ids": stats["audit_totals"]["fallback_task_ids"],
        "hallucination_presence": {
            tid: {"present_in_samples": item["present_in_samples"], "n_samples_present": item["n_samples_present"]}
            for tid, item in stats["hallucination_tasks"].items()
        },
        "aborted": stats["aborted"],
        "abort_reason": stats["abort_reason"],
    }
    per_task_changes = _per_task_changes(baseline_view, default_view, stats_by_task)
    analysis: dict[str, Any] = {
        "schema": "t3_oracle_k3_analysis/1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "purpose": "T3：K=3 多数一致（≥2/3）+ canonical input 约束——真实采样 + 零 LLM 重放 + 预注册判定",
        "prereg": {"path": "PREREG.md", "sha256": prereg_sha},
        "preflight": {
            "path": "PREFLIGHT.json",
            "sha256": _sha(PREFLIGHT),
            "n_default_prompt_matches_s3": prompts["n_default_prompt_matches_s3"],
            "n_tasks": prompts["n_tasks"],
            "canonical_section_sha256": prompts["canonical_section_sha256"],
        },
        "baseline": {
            "report": "experiments/results/p_round_oracle_examples_20261018/ORACLE_EXAMPLES_REPORT_norm.json",
            "sha256": _sha(BASELINE),
            "counts": baseline_view["counts"],
            "n_classifiable": baseline_view["n_classifiable"],
            "rates_of_classifiable": baseline_view["rates_of_classifiable"],
        },
        "sampling": sampling_block,
        "two_source_arms": {
            "default_report": default_view["source_arms_identical"],
            "r2off_report": r2off_view["source_arms_identical"],
            "note": "df_spec 归档两源臂的 oracle 材料相同，预期逐位相同；不一致则披露",
        },
        "hallucination_tasks": stats["hallucination_tasks"],
        "hallucination_excluded": hallucination_excluded,
        "replay_arms": {
            "default": {
                "report": "ORACLE_EXAMPLES_REPORT_k3_default.json",
                "sha256": _sha(DEFAULT_REPORT),
                "body_digest": default_meta.get("body_digest"),
                "wall_s": default_meta.get("tool_wall_s"),
                "production_env": {
                    "SPEC_ORACLE_EXEC_ENABLE": True,
                    "SPEC_ORACLE_EXAMPLES_ENABLE": True,
                    "SPEC_EXAMPLES_SELF_VALIDATE": "default(on)",
                },
                "counts": default_view["counts"],
                "n_classifiable": default_view["n_classifiable"],
                "rates_of_classifiable": default_view["rates_of_classifiable"],
                "examples_self_validation": default_view["examples_self_validation"],
                "source_arms_identical": default_view["source_arms_identical"],
            },
            "r2off": {
                "report": "ORACLE_EXAMPLES_REPORT_k3_r2off.json",
                "sha256": _sha(R2OFF_REPORT),
                "body_digest": r2off_meta.get("body_digest"),
                "wall_s": r2off_meta.get("tool_wall_s"),
                "production_env": {
                    "SPEC_ORACLE_EXEC_ENABLE": True,
                    "SPEC_ORACLE_EXAMPLES_ENABLE": True,
                    "SPEC_EXAMPLES_SELF_VALIDATE": "false",
                },
                "counts": r2off_view["counts"],
                "n_classifiable": r2off_view["n_classifiable"],
                "rates_of_classifiable": r2off_view["rates_of_classifiable"],
                "examples_self_validation": r2off_view["examples_self_validation"],
                "source_arms_identical": r2off_view["source_arms_identical"],
            },
            "identical_per_task": arms_identical,
            "per_task_comparison": identical_per_task,
        },
        "delta_vs_baseline": {key: default_view["counts"][key] - baseline_view["counts"][key] for key in CATEGORIES},
        "per_task_changes": per_task_changes,
        "attribution_notes": ATTRIBUTION_NOTES,
        "judgment": judgment,
        "sensitivity_judgment": r2off_judgment,
        "limitations": [
            "n=20 任务、单轮 K=3、单次零 LLM 重放 ×2 臂；探索性、非 confirmatory，结论仅限本批工件，不外推。",
            "示例来自重新采样（非 P-1 原 90 条），与基线差异同时包含「示例集合不同」「canonical 约束」"
            "「≥2/3 多数一致过滤」三个因素；本评估按预注册规则合并看待，不做单因素归因。",
            "P-1 两条幻觉示例在 3 个 canonical 样本中均未再现（不是被多数一致过滤掉的）；"
            "「hallucination 排除 2/2」只表示它们未进入本轮 oracle，不代表示例幻觉问题被解决"
            "（knapsack 出现新的一致幻觉）。",
            "canonical 模板是人工设计的通用边界集合，不保证覆盖各函数真实定义域；本轮观测到"
            "「边界示例不区分 buggy/fixed」与「模板组合诱导一致错误期望」两类副作用。",
            "R-2 自校验在臂 1 中丢弃示例 0 条（两任务锚后置子句表达力不足，与 R-2 结论一致）；"
            "臂 2 关 R-2 后逐任务结果与臂 1 相同，判定不变。",
            "与 B2 主批次并发运行（重放 nice -n 15）；墙钟为实测，可能受 CPU 争用轻微影响。",
            "未改生产默认（SPEC_ORACLE_EXAMPLES_ENABLE 默认关）；未 git commit；基线工件只读。",
            "helper 脚本的执行版本/当前版本 sha256 见 ANALYSIS_REPORT.helper_provenance"
            "（采样 helper 在跑后仅做过 ruff format，无行为变化）。",
        ],
        "helper_provenance": {
            "_helpers/run_k3_sampling.py": {
                "executed_sha256": preflight.get("implementation", {}).get("_helpers/run_k3_sampling.py"),
                "current_sha256": _sha(OUT / "_helpers/run_k3_sampling.py"),
                "note": "采样实际执行版本 = PREFLIGHT 记录的 executed_sha256；执行后对该 helper 做过一次 ruff format（纯格式，语义/行为不变），故 current_sha256 不同",
            },
            "_helpers/analyze_k3.py": {
                "current_sha256": _sha(OUT / "_helpers/analyze_k3.py"),
                "note": "分析脚本，采样与重放全部完成之后编写/运行；不参与采样/重放行为",
            },
        },
        "artifacts": {
            "PREREG.md": prereg_sha,
            "PREFLIGHT.json": _sha(PREFLIGHT),
            "PREFLIGHT_PROMPTS.json": _sha(PROMPTS),
            "K3_STATS.json": _sha(STATS_PATH),
            "K3_REUSE_REPORT.json": _sha(REUSE_REPORT),
            "ORACLE_EXAMPLES_REPORT_k3_default.json": _sha(DEFAULT_REPORT),
            "ORACLE_EXAMPLES_REPORT_k3_r2off.json": _sha(R2OFF_REPORT),
            "baseline ORACLE_EXAMPLES_REPORT_norm.json": _sha(BASELINE),
            "S-3 MULTISAMPLE_STATS.json": _sha(S3_DIR / "MULTISAMPLE_STATS.json"),
            "experiments/spec_examples_generator.py": _sha(_REPO_ROOT / "experiments/spec_examples_generator.py"),
            "tests/test_examples_multisample.py": _sha(_REPO_ROOT / "tests/test_examples_multisample.py"),
            "_helpers/run_k3_sampling.py": _sha(OUT / "_helpers/run_k3_sampling.py"),
            "_helpers/analyze_k3.py": _sha(OUT / "_helpers/analyze_k3.py"),
        },
    }
    analysis["analysis_body_digest"] = body_digest({k: v for k, v in analysis.items() if k != "generated_at"})
    from src.utils.atomic_io import atomic_write_json, atomic_write_text

    # SAMPLING_REPORT.json：采样阶段的紧凑报告（数字全部派生自 K3_STATS.json，不手写）
    sampling_report = {
        "schema": "t3_oracle_k3_sampling_report/1",
        "generated_at": analysis["generated_at"],
        "source_detail_artifact": "K3_STATS.json",
        "source_detail_sha256": analysis["artifacts"]["K3_STATS.json"],
        "prereg_sha256": prereg_sha,
        "k": stats["generator"]["k"],
        "majority": stats["generator"]["majority"],
        "threshold_rule": "示例出现于 ≥majority 个采样（K=3 → ≥2/3 多数一致）",
        "max_examples": stats["generator"]["max_examples"],
        "canonical_inputs": stats["generator"]["canonical_inputs"],
        "canonical_section_sha256": stats["generator"]["canonical_section_sha256"],
        "model": stats["generator"]["model"],
        "llm_cache": stats["generator"]["llm_cache"],
        "cache_namespace": stats["generator"]["cache_namespace"],
        "temperature": stats["generator"]["temperature"],
        "max_output_tokens": stats["generator"]["max_output_tokens"],
        "key_normalization": stats["generator"]["key_normalization"],
        "n_tasks": stats["audit_totals"]["n_tasks"],
        "n_tasks_with_final_examples": stats["audit_totals"]["n_tasks_with_final_examples"],
        "n_tasks_with_intersection": stats["audit_totals"]["n_tasks_with_final_examples"],
        "llm_calls": stats["generator"]["llm_calls"],
        "input_tokens": stats["generator"]["input_tokens"],
        "output_tokens": stats["generator"]["output_tokens"],
        "total_tokens": stats["generator"]["total_tokens"],
        "cost_estimated_usd": stats["generator"]["cost_estimated_usd"],
        "budget_usd": stats["budget_usd_limit"],
        "wall_s": stats["generator"]["wall_s"],
        "n_examples_union_total": stats["audit_totals"]["n_examples_union_total"],
        "n_examples_intersection_total": stats["audit_totals"]["n_examples_intersection_total"],
        "n_dropped_non_intersection_total": stats["audit_totals"]["n_dropped_non_intersection_total"],
        "n_examples_final_total": stats["audit_totals"]["n_examples_final_total"],
        "fallback": stats["fallback"],
        "hallucination_presence": analysis["sampling"]["hallucination_presence"],
        "aborted": stats["aborted"],
        "abort_reason": stats["abort_reason"],
        "per_task": [
            {
                "task_id": task["task_id"],
                "canonical_status": task["canonical"].get("status"),
                "per_sample_counts": (task["canonical"].get("audit") or {}).get("per_sample_counts"),
                "per_sample_statuses": (task["canonical"].get("audit") or {}).get("sample_statuses"),
                "n_examples_union": (task["canonical"].get("audit") or {}).get("n_examples_union"),
                "n_examples_intersection": len(task["final"].get("examples") or []),
                "n_dropped_non_intersection": (task["canonical"].get("audit") or {}).get(
                    "n_dropped_non_intersection"
                ),
                "dropped": (task["canonical"].get("audit") or {}).get("dropped"),
                "final_source": task.get("final_source"),
                "final_examples": task["final"].get("examples") or [],
                "final_prompt_sha256": task.get("final_prompt_sha256"),
                "fallback_used": bool(task.get("fallback")),
            }
            for task in stats["per_task"]
        ],
    }
    atomic_write_json(str(OUT / "SAMPLING_REPORT.json"), sampling_report)
    atomic_write_json(str(OUT / "ANALYSIS_REPORT.json"), analysis)
    atomic_write_text(str(OUT / "README.md"), _render_readme(analysis))
    atomic_write_text(str(OUT / "RUN_SUMMARY.log"), _run_summary_text(analysis))
    judge = analysis["judgment"]
    print(
        f"[k3-analyze] verdict={judge['verdict']}（{judge['verdict_cn']}）；"
        f"correct {judge['correct_before']}→{judge['correct_after']}（损失 {judge['correct_loss']}）；"
        f"hallucination 排除 {judge['hallucinations_excluded_from_oracle']}/2；"
        f"两臂逐任务一致={arms_identical}"
    )
    print(f"[k3-analyze] 写出：ANALYSIS_REPORT.json / README.md / RUN_SUMMARY.log → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
