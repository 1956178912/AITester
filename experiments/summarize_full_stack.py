"""
G8 全开链路对比汇总脚本。

用途（gap_report_2026-09-28 P0 缺口 G8 的"结果分析"配套）：
    读取多个全开链路 benchmark JSON（ON / OFF 各开关组合），输出
    "哪一开关带来正向 delta"的保守结论（避免过度归因）。

设计口径（保守、零 LLM 成本）：
    - 对比粒度：按 `summary["full_stack_config"]` 中的开关键做分组聚合；
    - 正向收益判定：成功率先按基线对齐（同一 baseline 对比），
      再按"平均覆盖率 / 平均迭代 / 失败类别 top-3"辅助解读；
    - 错误类型分桶：按 `results[baseline].details[].error_category`
      分桶（assertion / runtime / import_error / syntax / unknown / 其他），
      输出"哪类错误在全开组合下收益最大"；
    - 不强行跑 0/N 的无信息量 A/B（与 assessment_2026-09-25 §2.2 P1
      单源诊断一致：跨文件任务在引擎能力突破前 ON/OFF 都会 0/N，
      本脚本仅在 ON 组成功率 > 0 时才输出"正向收益"结论，否则标记
      "无正向信息量（模型能力边界）"）。

使用方式：
    python experiments/summarize_full_stack.py \
        --on-experiments experiments/results/full_stack_swe_bench_pro_*.json \
        --off-experiments experiments/results/benchmark_swe_bench_pro_*.json \
        --output experiments/results/full_stack_summary.md

    # 或仅对比"全开 ON vs 全开 OFF（默认关链路）"两组文件（各自多文件聚合）
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 关注的"全开"开关键（与 run_full_stack_swe_bench_pro._apply_full_stack_env 对齐）
_FULL_STACK_KEYS: tuple[str, ...] = (
    "RUNTIME_PROBE_ENABLE",
    "STRATEGY_BANK_ENABLE",
    "EXPERT_POOL_ENABLE",
    "CROSS_FILE_ENABLE",
    "CROSS_FILE_BIDIRECTIONAL",
    "REPO_LEVEL_EXECUTION",
)

# 错误类型分桶（与 gap_report G8 "按错误类型分析哪类收益最大"对齐）
# 2026-10-01 全面审查 P1 修复：此前 5 桶硬编码与 ErrorCategory 17 值枚举
# 零交集漂移——实测 experiments/results/ 63 个 benchmark JSON 中 88% 失败行
# （type_error / index_error / timeout / llm_* / patch_validation_failed /
# execution_trace_missing / multi_candidate_all_rejected / patch_syntax_invalid
# 等）全落 "other"，分桶失去区分度。现直接 import ErrorCategory 动态分桶
# （枚举值单一来源，消除硬编码漂移），"other" 仅保留给真正未分类值。
# import 须放在 sys.path 注入之后（PROJECT_ROOT 已入 sys.path），
# 模块顶层 import 无法在 experiments/ 脚本运行时解析 src.* 包。
from src.agents.error_classifier import ErrorCategory  # noqa: E402

# 全量枚举值（动态，与 error_classifier 单一来源）
_ERROR_BUCKETS: tuple[str, ...] = tuple(v.value for v in ErrorCategory)


def _load_summaries(paths: list[str]) -> list[dict[str, Any]]:
    """读取 benchmark JSON 列表（容错：缺失 / 损坏文件跳过并 warning）。"""
    loaded: list[dict[str, Any]] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warning] 无法读取 {path}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict) or "results" not in data:
            print(f"[warning] {path} 不是合法的 benchmark 结果 JSON，跳过", file=sys.stderr)
            continue
        loaded.append(data)
    return loaded


def _aggregate_group(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """把同组（ON 或 OFF）的多个 benchmark JSON 聚合为单一统计。

    聚合口径（保守、可复算）：
        - 每基线：成功任务数 / 总任务数（成功率先按基线对齐再对比）；
        - 失败类别分布：逐基线 details[].error_category 计数；
        - 错误类型分桶：归一到 _ERROR_BUCKETS 五桶 + "other"；
        - 平均迭代 / 平均耗时 / 总 token：逐基线求均值。

    Args:
        summaries: 同组（全开 ON 或全开 OFF）的 benchmark 结果 JSON 列表。

    Returns:
        聚合 dict（含 baselines / success_rate / error_buckets / avg_iterations 等）。
    """
    per_baseline_tasks: dict[str, int] = Counter()
    per_baseline_passed: dict[str, int] = Counter()
    per_baseline_errors: dict[str, Counter[str, int]] = {}
    per_baseline_iterations: dict[str, list[float]] = {}
    per_baseline_elapsed: dict[str, list[float]] = {}
    per_baseline_tokens: dict[str, list[float]] = {}

    for summary in summaries:
        results = summary.get("results", {})
        for baseline, bl in results.items():
            details = bl.get("details", [])
            # O23（2026-09-29 审查 P2）：分母分子同源——历史口径
            # `per_baseline_tasks[baseline] += len(details)`（分母 = details
            # 总行数）与 `per_baseline_passed[baseline] += bl.get("passed_count", 0)`
            # （分子 = 汇总层 passed_count）来自不同层：_build_task_result
            # 在 details 为空时仍写 passed_count=0，但 len(details)=0 的分母
            # 与 passed_count 不同源 → 若某基线 details 缺失而 passed_count
            # 非 0（或反之），success_rate 分母/分子口径漂移。现统一为
            # details 同源：total = len(details)，passed = 统计 details 中
            # row.get("passed") 为 True 的行数（与分子同一来源），
            # 消除"分母取 len(details)、分子取 passed_count"的跨层口径。
            _detail_passed = sum(1 for row in details if row.get("passed"))
            per_baseline_tasks[baseline] += len(details)
            per_baseline_passed[baseline] += _detail_passed
            per_baseline_errors.setdefault(baseline, Counter())
            per_baseline_iterations.setdefault(baseline, [])
            per_baseline_elapsed.setdefault(baseline, [])
            per_baseline_tokens.setdefault(baseline, [])
            for row in details:
                if not row.get("passed") and row.get("error_category"):
                    category = str(row["error_category"]).lower()
                    bucket = category if category in _ERROR_BUCKETS else "other"
                    per_baseline_errors[baseline][bucket] += 1
            if bl.get("avg_iterations") is not None:
                per_baseline_iterations[baseline].append(float(bl["avg_iterations"]))
            if bl.get("avg_elapsed_seconds") is not None:
                per_baseline_elapsed[baseline].append(float(bl["avg_elapsed_seconds"]))
            token_total = (bl.get("token_metrics") or {}).get("total_tokens")
            if token_total is not None:
                per_baseline_tokens[baseline].append(float(token_total))

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    aggregation: dict[str, Any] = {
        "baselines": {},
        "total_benchmark_files": len(summaries),
    }
    for baseline in sorted(per_baseline_tasks):
        total = per_baseline_tasks[baseline]
        passed = per_baseline_passed[baseline]
        success_rate = round(passed / total * 100, 2) if total > 0 else 0.0
        aggregation["baselines"][baseline] = {
            "total_tasks": total,
            "passed_count": passed,
            "success_rate": success_rate,
            "error_buckets": dict(per_baseline_errors.get(baseline, {})),
            "avg_iterations": _avg(per_baseline_iterations.get(baseline, [])),
            "avg_elapsed_seconds": _avg(per_baseline_elapsed.get(baseline, [])),
            "avg_total_tokens": _avg(per_baseline_tokens.get(baseline, [])),
        }
    return aggregation


def _switch_fingerprint(summary: dict[str, Any]) -> dict[str, bool]:
    """提取单个 benchmark 的全开开关指纹（ON/OFF 组合标识）。"""
    config = summary.get("full_stack_config", {})
    fingerprint: dict[str, bool] = {}
    for key in _FULL_STACK_KEYS:
        value = config.get(key, "false")
        fingerprint[key] = str(value).lower() in ("true", "1", "on")
    return fingerprint


def _render_on_vs_off(on_agg: dict[str, Any], off_agg: dict[str, Any]) -> str:
    """渲染"全开 ON vs 全开 OFF"对比 Markdown（保守归因口径）。

    归因口径（避免过度归因）：
        - 成功率 delta = ON 组成功率 - OFF 组成功率（按基线对齐）；
        - delta > 0 时标注"全开链路对该基线有正向信号"，但仍需结合
          样本量（total_tasks 小 → 统计置信度低）解读；
        - delta <= 0 时标注"全开链路未带来正向收益（或负向）"；
        - 若 ON 组所有基线 success_rate 均 = 0，标注"无正向信息量
          （模型能力边界，与 assessment_2026-09-25 §2.2 P1 单源诊断一致）"。
    """
    lines = [
        "## 全开链路 ON vs OFF 对比（按基线对齐）",
        "",
        "| 基线 | OFF 成功率 | ON 成功率 | delta | 样本量(ON/OFF) | 结论 |",
        "|------|-----------|----------|-------|----------------|------|",
    ]
    any_positive = False
    for baseline in sorted(set(on_agg.get("baselines", {})) | set(off_agg.get("baselines", {}))):
        off_bl = off_agg.get("baselines", {}).get(baseline)
        on_bl = on_agg.get("baselines", {}).get(baseline)
        off_rate = off_bl["success_rate"] if off_bl else 0.0
        on_rate = on_bl["success_rate"] if on_bl else 0.0
        delta = round(on_rate - off_rate, 2)
        on_total = on_bl["total_tasks"] if on_bl else 0
        off_total = off_bl["total_tasks"] if off_bl else 0
        if on_rate > 0 and delta > 0:
            verdict = "正向信号（需结合样本量解读）"
            any_positive = True
        elif on_rate == 0:
            verdict = "无正向信息量（模型能力边界）"
        elif delta > 0:
            verdict = "正向信号（需结合样本量解读）"
            any_positive = True
        else:
            verdict = "未带来正向收益（delta <= 0）"
        lines.append(f"| {baseline} | {off_rate}% | {on_rate}% | {delta:+.2f} | {on_total}/{off_total} | {verdict} |")

    lines.append("")
    if any_positive:
        lines.append("> 注：上表 delta 为样本级差异，**未做统计显著性检验**——样本量小时结论保守解读。")
    else:
        lines.append("> 注：所有基线在 ON 组成功率均为 0——全开链路在当前模型能力下未突破正向信息量边界。")
    return "\n".join(lines)


def _render_error_buckets(on_agg: dict[str, Any], off_agg: dict[str, Any]) -> str:
    """渲染"按错误类型分桶的失败分布对比"（哪类错误在 ON 组占比下降最大）。"""
    lines = [
        "## 失败类型分桶对比（ON vs OFF，按基线合计）",
        "",
        "| 错误桶 | OFF 占比 | ON 占比 | 占比 delta | 解读 |",
        "|--------|---------|--------|-----------|------|",
    ]

    # 跨基线合计
    def _bucket_totals(agg: dict[str, Any]) -> Counter:
        totals: Counter = Counter()
        for bl in agg.get("baselines", {}).values():
            for bucket, count in bl.get("error_buckets", {}).items():
                totals[bucket] += int(count)
        return totals

    off_totals = _bucket_totals(off_agg)
    on_totals = _bucket_totals(on_agg)
    off_total_count = sum(off_totals.values()) or 1
    on_total_count = sum(on_totals.values()) or 1

    for bucket in (*_ERROR_BUCKETS, "other"):
        off_count = off_totals.get(bucket, 0)
        on_count = on_totals.get(bucket, 0)
        off_pct = off_count / off_total_count * 100 if off_total_count > 0 else 0.0
        on_pct = on_count / on_total_count * 100 if on_total_count > 0 else 0.0
        delta = on_pct - off_pct
        if delta < -5:
            interpretation = f"⬇ 该桶失败占比下降 {abs(delta):.1f}pp（全开链路对该类错误有修复贡献）"
        elif delta > 5:
            interpretation = f"⬆ 该桶失败占比上升 {delta:.1f}pp（需排查全开链路是否引入新失败模式）"
        else:
            interpretation = "≈ 占比基本持平"
        lines.append(
            f"| {bucket} | {off_count} ({off_pct:.1f}%) | {on_count} ({on_pct:.1f}%) | {delta:+.1f}pp | {interpretation} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="G8 全开链路对比汇总（ON vs OFF）")
    parser.add_argument(
        "--on-experiments",
        default="",
        help="全开 ON 组 benchmark JSON 文件（支持 glob，逗号分隔；默认 experiments/results/full_stack_*.json）",
    )
    parser.add_argument(
        "--off-experiments",
        default="",
        help="全开 OFF 组 benchmark JSON 文件（支持 glob，逗号分隔；默认 experiments/results/benchmark_*_*.json）",
    )
    parser.add_argument("--output", default="experiments/results/full_stack_summary.md", help="输出 Markdown 路径")
    args = parser.parse_args()

    # 默认 glob（相对 PROJECT_ROOT）
    if not args.on_experiments:
        args.on_experiments = os.path.join("experiments", "results", "full_stack_*.json")
    if not args.off_experiments:
        args.off_experiments = os.path.join("experiments", "results", "benchmark_*.json")

    def _expand(patterns: str) -> list[str]:
        files: list[str] = []
        for pattern in (p.strip() for p in patterns.split(",") if p.strip()):
            matched = (
                sorted(glob.glob(os.path.join(PROJECT_ROOT, pattern)))
                if not os.path.isabs(pattern)
                else sorted(glob.glob(pattern))
            )
            files.extend(matched)
        return files

    on_files = _expand(args.on_experiments)
    off_files = _expand(args.off_experiments)
    print(f"[G8] 全开 ON 组文件数: {len(on_files)}（{args.on_experiments}）")
    print(f"[G8] 全开 OFF 组文件数: {len(off_files)}（{args.off_experiments}）")

    on_summaries = _load_summaries(on_files)
    off_summaries = _load_summaries(off_files)
    if not on_summaries or not off_summaries:
        print("[G8] ❌ ON 或 OFF 组无合法 benchmark JSON，无法对比", file=sys.stderr)
        return 1

    on_agg = _aggregate_group(on_summaries)
    off_agg = _aggregate_group(off_summaries)

    # O23（2026-09-29 审查 P2）：按开关指纹真分组——历史 ON/OFF 组把**所有**
    # 文件整体池化（_aggregate_group 汇总全部 summaries），混合不同开关
    # 组合（如 RUNTIME_PROBE_ENABLE=true + CROSS_FILE_ENABLE=false 与
    # RUNTIME_PROBE_ENABLE=false + CROSS_FILE_ENABLE=true 池化在一起），
    # 导致"全开"结论被部分开组合稀释/混淆。现按指纹分组：同一指纹的
    # 文件聚合为一组，不同指纹各自独立报告，消除整体池化。
    on_fingerprints = [_switch_fingerprint(s) for s in on_summaries]
    off_fingerprints = [_switch_fingerprint(s) for s in off_summaries]

    # 按指纹分组 ON 组
    on_groups: dict[tuple[tuple[str, bool], ...], list[dict[str, Any]]] = {}
    for summary, fp in zip(on_summaries, on_fingerprints, strict=True):
        key = tuple(sorted(fp.items()))
        on_groups.setdefault(key, []).append(summary)

    # 按指纹分组 OFF 组
    off_groups: dict[tuple[tuple[str, bool], ...], list[dict[str, Any]]] = {}
    for summary, fp in zip(off_summaries, off_fingerprints, strict=True):
        key = tuple(sorted(fp.items()))
        off_groups.setdefault(key, []).append(summary)

    # O23：若 ON 组仅有一种指纹（最常见情况：全开 ON 组所有文件开关一致），
    # 行为与历史整体池化等价（on_agg 不变）；若多种指纹，输出时标注
    # "多开关组合池化，结论不可归因到单一开关"（保守口径）。
    _multi_fingerprint_warning = len(on_groups) > 1 or len(off_groups) > 1
    on_keys = Counter(tuple(sorted(fp.items())) for fp in on_fingerprints)
    off_keys = Counter(tuple(sorted(fp.items())) for fp in off_fingerprints)

    md_lines = [
        "# G8 全开链路对比汇总",
        "",
        "- 生成自 experiments/summarize_full_stack.py",
        f"- ON 组 benchmark 文件数: {len(on_summaries)}",
        f"- OFF 组 benchmark 文件数: {len(off_summaries)}",
        "",
        "## 全开开关指纹（ON 组）",
        "",
    ]
    for key, count in on_keys.most_common():
        enabled = [k for k, v in key if v]
        md_lines.append(f"- {', '.join(enabled) or '(无)'} × {count}")
    md_lines.extend(["", "## 全开开关指纹（OFF 组）", ""])
    for key, count in off_keys.most_common():
        enabled = [k for k, v in key if v]
        md_lines.append(f"- {', '.join(enabled) or '(无)'} × {count}")
    md_lines.append("")

    # O23（2026-09-29 审查 P2）：多开关组合池化警告——当 ON 组或 OFF 组
    # 含多种不同开关指纹时，整体池化结论不可归因到单一开关组合，
    # 保守标注提示用户按指纹分组查看。
    if _multi_fingerprint_warning:
        md_lines.append(
            f"> ⚠ O23 多开关组合池化警告：ON 组含 {len(on_groups)} 种指纹，"
            f"OFF 组含 {len(off_groups)} 种指纹。整体池化结论不可归因到单一开关"
            "组合。以下按指纹分组输出各组合的独立对比表：\n"
        )
        md_lines.append("")
        for group_key, group_summaries in sorted(on_groups.items(), key=lambda x: x[0]):
            enabled = [k for k, v in group_key if v]
            label = ", ".join(enabled) if enabled else "(全关)"
            group_agg = _aggregate_group(group_summaries)
            md_lines.append(f"### ON 组指纹：{label}（{len(group_summaries)} 文件）")
            md_lines.append("")
            md_lines.append(_render_on_vs_off(group_agg, off_agg))
            md_lines.append("")
        for group_key, group_summaries in sorted(off_groups.items(), key=lambda x: x[0]):
            enabled = [k for k, v in group_key if v]
            label = ", ".join(enabled) if enabled else "(全关)"
            group_agg = _aggregate_group(group_summaries)
            md_lines.append(f"### OFF 组指纹：{label}（{len(group_summaries)} 文件）")
            md_lines.append("")
            md_lines.append(_render_on_vs_off(on_agg, group_agg))
            md_lines.append("")
    else:
        # 单一指纹：整体池化口径（与历史等价）
        md_lines.append(_render_on_vs_off(on_agg, off_agg))
        md_lines.append("")
        md_lines.append(_render_error_buckets(on_agg, off_agg))

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"[G8] 汇总已写入: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
