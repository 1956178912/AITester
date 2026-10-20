#!/usr/bin/env python3
"""AK1（2026-10-06 第十二轮审查 R9/R12）：R-P0-2 修复上限归因 + 缺失敏感性双界。

纯离线分析（零 LLM 成本），消费生死实验三种子批次工件，回答两个
预注册遗留问题：

1. repair 全线 0.000 的"上限归因"（R9）：repair=0 不是单点事实，需
   分解为通道漏斗——detection_first_status 分桶 → 修复循环进入
   （red 任务）→ patch 产出 → patch_plausible → patch_correct，附
   patch_evidence_level / stop_reason / error_category 分布与
   fl_at_k、mutation_detection_rate 的观测覆盖率（口径缺口行数），
   供 E7 设计与论文"修复上限"表述消费；
2. 21 行 detection=None 差异性缺失的最好/最坏双界（R12）：None→1 /
   None→0 填充后重算 aitester vs plain_llm / plain_llm_df 的配对差
   与 McNemar——定性结论（+14pp 正向 / −28pp 负向）在双界下是否
   保持，写入 pooled 报告勘误节。

数据口径与 statistical_report_3seed_pooled.md 完全一致：同一加载器
（load_experiment_results_with_sources，--batches 白名单 + --pool-seeds
多种子拼接）、同一 McNemar 实现（连续性校正，None 行跳过）。

用法（与预注册 E2 就绪命令同参口径）::

    python experiments/repair_ceiling_analysis.py \
        --results-dir experiments/results/main_batch \
        --batches benchmark_synthetic_20261006_140906.json,benchmark_synthetic_20261006_151907.json,benchmark_synthetic_20261006_164357.json \
        --pool-seeds

输出：experiments/results/main_batch/repair_ceiling_report.md（--output 可改）。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.statistical_analysis import (  # noqa: E402
    _pair_by_task,
    load_experiment_results_with_sources,
    mcnemar_test,
)

_DEFAULT_BATCHES = (
    "benchmark_synthetic_20261006_140906.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_164357.json",
)
_COMPARISONS = (("aitester", "plain_llm"), ("aitester", "plain_llm_df"))


def _bucket_of(row: dict[str, Any]) -> str:
    """行级漏斗桶键：detection_first_status 优先，缺失回落 None。"""
    status = row.get("detection_first_status")
    return str(status) if status is not None else "None"


def build_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """AK1：修复通道漏斗与 repair=0 归因分解。

    漏斗层（口径与 M1/ADR-0015 一致）：
    - total：全部任务行；
    - by_status：detection_first_status 四桶计数（red_then_green /
      red_not_repaired / all_green_unverified / None）；
    - repair_loop_entered：red_then_green + red_not_repaired（buggy 上
      出现过红 = 修复循环有可修对象）；
    - patch_produced：修复循环行中 patch 字段非空（Debugger/多候选
      实际产出补丁文本）；
    - patch_plausible：patch_plausible==1（补丁通过证据门/合理性）；
    - patch_correct：patch_correct==1（gold 材料独立裁决（自动化 oracle，无人工参与）修复正确——
      R-P0-2 实测恒 0，本漏斗的"上限"层）。

    附分布（repair=0 的横向归因）：patch_evidence_level / stop_reason /
    error_category 计数，fl_at_k 与 mutation_detection_rate 的观测
    覆盖率（非 None 行数——批内未接线即为口径缺口行）。
    """
    funnel: dict[str, Any] = {
        "total": len(rows),
        "by_status": Counter(_bucket_of(r) for r in rows),
        "repair_loop_entered": sum(1 for r in rows if _bucket_of(r) in ("red_then_green", "red_not_repaired")),
        "patch_produced": 0,
        "patch_plausible": 0,
        "patch_correct": 0,
        "patch_evidence_level": Counter(),
        "stop_reason": Counter(),
        "error_category": Counter(),
        "fl_at_k_observed": 0,
        "mutation_rate_observed": 0,
    }
    for row in rows:
        if _bucket_of(row) not in ("red_then_green", "red_not_repaired"):
            continue
        if row.get("patch"):
            funnel["patch_produced"] += 1
        if row.get("patch_plausible") == 1:
            funnel["patch_plausible"] += 1
        if row.get("patch_correct") == 1:
            funnel["patch_correct"] += 1
        funnel["patch_evidence_level"][str(row.get("patch_evidence_level"))] += 1
        funnel["stop_reason"][str(row.get("stop_reason"))] += 1
        funnel["error_category"][str(row.get("error_category"))] += 1
        if row.get("fl_at_k") is not None:
            funnel["fl_at_k_observed"] += 1
        if row.get("mutation_detection_rate") is not None:
            funnel["mutation_rate_observed"] += 1
    return funnel


def _filled_rows(rows: list[dict[str, Any]], fill: int) -> list[dict[str, Any]]:
    """R12：detection_rate=None 行按 fill（0/1）填充（浅拷贝行，不改原数据）。"""
    return [{**r, "detection_rate": fill} if r.get("detection_rate") is None else r for r in rows]


def sensitivity_bounds(results: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """R12：aitester None 行双界敏感性（vs plain_llm / plain_llm_df）。

    对每个对比输出四行口径：原口径（None 跳过 = mcnemar_test 语义）、
    None→0（最坏）、None→1（最好）；差异率 = (Σ_A − Σ_B)/n_common。

    2026-10-19 勘误（Z 轮第三方审查 F02）：旧实现三种情形都用**整臂**
    阳性数（A/B 两臂各自全量求和）除以**配对**共同任务数 n_common——分子
    与分母不同源，把被排除任务（B 臂可测、A 臂 None）的阳性计入分子。
    现三种情形统一经 `_pair_by_task` 同源配对原语取配对列表：分子
    Σ_A / Σ_B 与分母 n_common 都来自同一共同（去重后、非 None）任务总体；
    worst/best 情形先对 None 行填充再配对（填充后共同任务数 = 全量配对
    总体）。实测 aitester vs plain_llm_df：base 共同 n=240、A/B 阳性
    38/106、经验差 −68/240 = −0.283333（旧整臂口径 −0.329167，误差
    4.5833pp——df 臂有 11 个阳性位于被排除的 21 个任务中）。
    """
    out: list[dict[str, Any]] = []
    for arm_a, arm_b in _COMPARISONS:
        rows_a = results.get(arm_a) or []
        rows_b = results.get(arm_b) or []
        n_none = sum(1 for r in rows_a if r.get("detection_rate") is None)
        scenarios: list[tuple[str, list[dict[str, Any]]]] = [
            ("base", rows_a),
            ("worst(None→0)", _filled_rows(rows_a, 0)),
            ("best(None→1)", _filled_rows(rows_a, 1)),
        ]
        entry: dict[str, Any] = {"comparison": f"{arm_a} vs {arm_b}", "n_none": n_none, "rows": []}
        for label, filled in scenarios:
            chi2, p, _, n_common = mcnemar_test(filled, rows_b, field="detection_rate")
            # 分子与分母同源：配对列表直接来自 _pair_by_task（去重 + None
            # 过滤后的共同任务 0/1 值），不再对整臂求和（F02 修复）。
            paired_a, paired_b, _common = _pair_by_task(filled, rows_b, field="detection_rate")
            sum_a = sum(paired_a)
            sum_b = sum(paired_b)
            diff = (sum_a - sum_b) / n_common if n_common else float("nan")
            entry["rows"].append(
                {
                    "scenario": label,
                    "n_common": n_common,
                    "sum_a": sum_a,
                    "sum_b": sum_b,
                    "risk_diff": diff,
                    "mcnemar_chi2": chi2,
                    "mcnemar_p": p,
                }
            )
        out.append(entry)
    return out


def _fmt_counter(counter: Counter[str], total: int) -> str:
    if not counter:
        return "（无行）"
    return "，".join(f"{k}: {v}（{v / total * 100:.1f}%）" for k, v in counter.most_common())


def render_markdown(
    source_files: list[str],
    funnel: dict[str, Any],
    bounds: list[dict[str, Any]],
    iteration_hist: Counter[int],
) -> str:
    """AK1：报告 Markdown（数字全部由上游函数产出，本函数零计算）。"""
    n = funnel["total"]
    loop_n = funnel["repair_loop_entered"]
    lines = [
        "# R-P0-2 修复上限归因分析（AK1，2026-10-06）",
        "",
        f"数据来源（与 statistical_report_3seed_pooled.md 同参口径）：{len(source_files)} 个批次",
    ]
    lines += [f"- {src}" for src in source_files]
    lines += [
        "",
        "## 2026-10-19 勘误（Z 轮第三方审查 F02：base 行分子改为配对口径）",
        "",
        "本报告 §3 的 `base` 行在 2026-10-06 版中把 A/B 两臂**整臂**阳性数",
        "当作分子、再除以**配对**共同任务数（aitester vs plain_llm_df：n=240，",
        "旧配对差 −0.329167）。分子与分母不同源：df 臂有 11 个阳性位于 A 臂",
        "None 被排除的 21 个任务中，被错误计入分子，导致效应差偏移 4.5833pp。",
        "2026-10-19 起 base 行的分子改用与 McNemar 检验同源的 `_pair_by_task`",
        "配对列表（共同任务内 A 阳性 38、B 阳性 106），正确经验差 =",
        "−68/240 = **−0.283333**。",
        "",
        "填充情形（None→0 / None→1）的配对总体本来就是全量 261 任务，数值与",
        "2026-10-06 版一致；双界不变式（风险差口径 worst ≤ base ≤ best）保持。",
        "本勘误只修正统计派生量；原始三批 JSON、漏斗计数及其它历史数字均未改动。",
        "",
        "## 1. 修复通道漏斗（aitester 臂，多种子拼接）",
        "",
        "| 漏斗层 | 行数 | 占比（分母=上行） |",
        "|------|----|----|",
        f"| 总任务 | {n} | — |",
    ]
    for bucket, count in funnel["by_status"].most_common():
        lines.append(f"| └ detection_first_status={bucket} | {count} | {count / n * 100:.1f}% |")
    lines += [
        f"| 修复循环进入（red 两桶合计） | {loop_n} | {loop_n / n * 100:.1f}% |",
        f"| patch 产出（patch 非空） | {funnel['patch_produced']} | {funnel['patch_produced'] / loop_n * 100:.1f}% |",
        f"| patch_plausible=1 | {funnel['patch_plausible']} | {funnel['patch_plausible'] / loop_n * 100:.1f}% |",
        f"| patch_correct=1（gold 裁决） | {funnel['patch_correct']} | {funnel['patch_correct'] / loop_n * 100:.1f}% |",
        "",
        "## 2. repair=0 归因分布（修复循环行）",
        "",
        f"- patch_evidence_level：{_fmt_counter(funnel['patch_evidence_level'], loop_n)}",
        f"- stop_reason：{_fmt_counter(funnel['stop_reason'], loop_n)}",
        f"- error_category：{_fmt_counter(funnel['error_category'], loop_n)}",
        f"- fl_at_k 观测覆盖：{funnel['fl_at_k_observed']}/{loop_n}"
        "（R-P0-2 批 FL_SPECTRAL_ENABLE 未接线——AI 批次已补，E2 起产出）",
        f"- mutation_detection_rate 观测覆盖：{funnel['mutation_rate_observed']}/{loop_n}",
        "",
        "## 3. 21 行 detection=None 敏感性双界（R12）",
        "",
        "| 对比 | 情形 | 共同任务 | A 阳性 | B 阳性 | 配对差 | McNemar χ² | p |",
        "|------|------|----|----|----|----|----|----|",
    ]
    for entry in bounds:
        for row in entry["rows"]:
            lines.append(
                f"| {entry['comparison']}（None {entry['n_none']} 行） | {row['scenario']} "
                f"| {row['n_common']} | {row['sum_a']} | {row['sum_b']} "
                f"| {row['risk_diff']:+.3f} | {row['mcnemar_chi2']:.2f} | {row['mcnemar_p']:.2g} |"
            )
    lines += [
        "",
        "## 4. iteration-to-stop 分布（aitester 臂，收敛性观测）",
        "",
        "| 迭代数 | 任务数 |",
        "|----|----|",
    ]
    lines += [f"| {it} | {count} |" for it, count in sorted(iteration_hist.items())]
    lines += [
        "",
        "## 5. 结论口径",
        "",
        "- repair=0 的漏斗分解见 §1/§2：上限层（patch_correct）之前的各层",
        "  行数即 E7 实验设计的分层抽样框；观测覆盖为 0 的指标（fl_at_k、",
        "  mutation）属批内口径缺口而非真实为 0，不得按 0 解读。",
        "- §3 双界若与原口径同号且均显著，则 pooled 报告两定性结论",
        "  （+14pp 正向 / −28pp 负向）对差异性缺失稳健，勘误节引用本表。",
        "- 本报告纯离线生成（零 LLM 成本），随批次工件入 SHA256SUMS。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", default="experiments/results/main_batch")
    parser.add_argument(
        "--batches",
        default=",".join(_DEFAULT_BATCHES),
        help="批次白名单（逗号分隔，相对 results_dir；与 pooled 报告同参）",
    )
    parser.add_argument("--pool-seeds", action="store_true", default=True, help="多种子拼接（默认开）")
    parser.add_argument(
        "--output",
        default=None,
        help="Markdown 输出路径（默认 <results-dir>/repair_ceiling_report.md）",
    )
    args = parser.parse_args()

    batch_files = [b.strip() for b in args.batches.split(",") if b.strip()]
    results, source_files = load_experiment_results_with_sources(
        args.results_dir, batch_files, allow_schema_mixed=False, pool_seeds=args.pool_seeds
    )
    aitester_rows = results.get("aitester") or []
    if not aitester_rows:
        print("错误：aitester 臂无数据（检查 --batches 白名单与 M1 schema 过滤）", file=sys.stderr)
        return 1

    funnel = build_funnel(aitester_rows)
    bounds = sensitivity_bounds(results)
    iteration_hist = Counter(int(r.get("iterations") or 0) for r in aitester_rows)
    report = render_markdown(source_files, funnel, bounds, iteration_hist)

    output = Path(args.output) if args.output else Path(args.results_dir) / "repair_ceiling_report.md"
    output.write_text(report, encoding="utf-8")
    print(f"已写入 {output}（{len(aitester_rows)} 任务行，{len(source_files)} 批次）")
    for entry in bounds:
        for row in entry["rows"]:
            print(
                f"  {entry['comparison']:<28} {row['scenario']:<14} "
                f"diff={row['risk_diff']:+.3f}  χ²={row['mcnemar_chi2']:.2f}  p={row['mcnemar_p']:.2g}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
