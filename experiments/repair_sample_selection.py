#!/usr/bin/env python3
"""AL10/E7（2026-10-06 第十三轮审查）：修复上限分层抽样候选行清单。

纯离线（零 LLM 成本），消费 R-P0-2 三种子批次工件（与
repair_ceiling_analysis.py 同一加载器与行口径），按预注册 E7
（docs/preregistration.md "E7" 节）从 patch_plausible=1 的修复循环行中
做分层确定性抽样，输出人工比对清单。

预注册口径：
- 抽样框：aitester 臂、修复循环进入（detection_first_status ∈
  {red_then_green, red_not_repaired}）且 patch_plausible == 1 的行；
- 分层键：patch_evidence_level（none / sbfl / keyword / 其他值按原样成层）；
- 每层样本量：ceil(层行数 × fraction)（默认 10%）；
- 确定性：层内按 task_id 排序后 random.Random(seed).sample——同一
  (行集合, fraction, seed) 恒产出同一样本；
- 复核判定（人工，不在本脚本）：equivalent / plausible_overfit /
  wrong_location / test_only / incomplete（equivalent>0 → repair 口径
  存在低估，须勘误；=0 → repair=0 为真零）。

用法::

    python experiments/repair_sample_selection.py \
        --results-dir experiments/results/main_batch \
        --batches benchmark_synthetic_20261006_140906.json,benchmark_synthetic_20261006_151907.json,benchmark_synthetic_20261006_164357.json \
        --fraction 0.10 --seed 42 --output -

输出：Markdown 候选清单（默认 stdout；--output 指定路径时写文件）。
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.statistical_analysis import (  # noqa: E402
    load_experiment_results_with_sources,
)

_DEFAULT_BATCHES = (
    "benchmark_synthetic_20261006_140906.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_164357.json",
)
_REVIEW_RUBRIC = "equivalent / plausible_overfit / wrong_location / test_only / incomplete"


def build_sampling_frame(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """E7 抽样框：修复循环进入（red 两桶）且 patch_plausible==1 的行。"""
    return [
        row
        for row in rows
        if row.get("detection_first_status") in ("red_then_green", "red_not_repaired")
        and row.get("patch_plausible") == 1
    ]


def stratify(frame: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按 patch_evidence_level 分层；层内按 task_id 排序保证列表序确定。"""
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frame:
        strata[str(row.get("patch_evidence_level"))].append(row)
    for stratum in strata.values():
        stratum.sort(key=lambda r: str(r.get("task_id")))
    return dict(strata)


def select_stratified_sample(
    strata: dict[str, list[dict[str, Any]]], fraction: float, seed: int
) -> list[dict[str, Any]]:
    """每层 ceil(层行数 × fraction) 的确定性抽样（seed 驱动，层序按名排序）。"""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction 须在 [0, 1]，收到 {fraction}")
    # 预注册 E7 要求确定性抽样（同 seed 复算一致）——刻意不使用密码学随机源。
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for stratum_name in sorted(strata):
        members = strata[stratum_name]
        n_pick = math.ceil(len(members) * fraction)
        if n_pick <= 0:
            continue
        selected.extend({**row, "_stratum": stratum_name} for row in rng.sample(members, min(n_pick, len(members))))
    return selected


def render_markdown(
    selected: list[dict[str, Any]],
    strata_counts: dict[str, int],
    source_files: list[str],
    fraction: float,
    seed: int,
) -> str:
    """E7 候选清单 Markdown（数字全部由上游产出，本函数零计算）。"""
    lines = [
        "# E7 修复上限分层抽样候选清单（AL10，2026-10-06）",
        "",
        f"- 数据来源（与 repair_ceiling_report.md 同参口径）：{len(source_files)} 个批次",
    ]
    lines += [f"  - {src}" for src in source_files]
    counts = "，".join(f"{k}: {v}" for k, v in sorted(strata_counts.items()))
    lines += [
        f"- 分层框（patch_plausible=1 行）：{sum(strata_counts.values())} 行〔{counts}〕",
        f"- 抽样参数：fraction={fraction:.0%}（每层 ceil 上取整）、seed={seed}（确定性）",
        f"- 复核判定口径：{_REVIEW_RUBRIC}",
        "",
        "| task_id | 分层（evidence） | stop_reason | error_category | iterations | patch 长度 | 人工判定 |",
        "|----|----|----|----|----|----|----|",
    ]
    for row in selected:
        patch_len = len(str(row.get("patch") or ""))
        lines.append(
            f"| {row.get('task_id')} | {row.get('_stratum')} | {row.get('stop_reason')} "
            f"| {row.get('error_category')} | {row.get('iterations')} | {patch_len} | （待复核） |"
        )
    lines += [
        "",
        "判定规则（预注册）：equivalent 占比 > 0 → repair 口径存在低估，须勘误并给",
        "出修正后上界；= 0 → repair=0 为真零（上限卡在合理性与 gold 正确性）。",
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
    parser.add_argument("--fraction", type=float, default=0.10, help="每层抽样比例（默认 0.10）")
    parser.add_argument("--seed", type=int, default=42, help="确定性抽样种子（默认 42）")
    parser.add_argument("--output", default="-", help="输出路径（默认 - = stdout）")
    args = parser.parse_args()

    batch_files = [b.strip() for b in args.batches.split(",") if b.strip()]
    results, source_files = load_experiment_results_with_sources(
        args.results_dir, batch_files, allow_schema_mixed=False, pool_seeds=args.pool_seeds
    )
    aitester_rows = results.get("aitester") or []
    frame = build_sampling_frame(aitester_rows)
    if not frame:
        print("错误：抽样框为空（aitester 臂无 patch_plausible=1 的修复循环行）", file=sys.stderr)
        return 1

    strata = stratify(frame)
    selected = select_stratified_sample(strata, args.fraction, args.seed)
    strata_counts = {name: len(members) for name, members in strata.items()}
    report = render_markdown(selected, strata_counts, source_files, args.fraction, args.seed)

    if args.output == "-":
        sys.stdout.write(report)
    else:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"已写入 {args.output}（{len(selected)} 候选行 / {len(frame)} 框行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
