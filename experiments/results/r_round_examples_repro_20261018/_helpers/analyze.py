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
prereg_text = (out / "PREREG_REPRO.md").read_text(encoding="utf-8") if (out / "PREREG_REPRO.md").exists() else ""

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
L.append("> **性质：预注册判定测量（单次运行、小样本）**。判定规则在 `PREREG_REPRO.md` 跑前冻结；结果只按该规则报告 "
         "`confirmed` / `not_confirmed`，并披露 MDE/功效/局限；不做超出规则的 confirmatory 因果主张。")
L.append("")
L.append("## 1. 协议与切点")
L.append("")
L.append(f"- 切点：`{(pf.get('git') or {}).get('root_head', '')}`（Q-1 q-examples；跑前/跑后 worktree dirty=0）")
L.append(f"- 两臂并发、同秒启动、独立 namespace、`AITESTER_LLM_CACHE=0`；`AITESTER_PROFILE=logic`、TEMPERATURE=0.0、"
         "LLM_THINKING_MODE=disabled、`BENCHMARK_PARALLELISM={p}`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、"
         "`AITESTER_BATCH_MAX_CALLS=200`、watchdog 3600s/臂。".format(p=(report["protocol"] or {}).get("parallelism")))
L.append("- A（control）：`SPEC_ORACLE_EXEC_ENABLE=true` + `SPEC_ORACLE_EXAMPLES_ENABLE=false`；"
         "B（examples）：两者均 `true`；`--dataset quixbugs --task-limit {n} --seed 43 --baselines aitester`。".format(
             n=(report["protocol"] or {}).get("task_limit")))
L.append(f"- 预注册：`PREREG_REPRO.md`（sha256 `{report['prereg_sha256']}`）；预算 ≤${(report['protocol'] or {}).get('budget_usd')}，"
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
L.append("| `PREREG_REPRO.md` | 跑前冻结的预注册（判定规则/MDE/局限） |")
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
