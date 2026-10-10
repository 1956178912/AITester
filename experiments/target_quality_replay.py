"""目标质量存量重放（R5 审查 2026-10-09，零 LLM）。

背景（本次审查实测到的"数字已存在但从未登记"缺口）：
    项目此前对外（BASELINE.yaml / 统计报告 / README）**从未登记被测代码的
    覆盖率与变异得分**，而 2025–2026 前沿（CoverUp/FSE'25 90% line+branch、
    TestAgent 88.85% line / 55.4% mutation、ULT/TOSEM'26 45.10% stmt /
    40.21% mutation）全部以这两项为一等公民指标——缺它们即无法与前沿对话。

    实测核实：受影响批次的行级明细（`results.<arm>.details[]`）**早已采集**
    了 ``coverage`` / ``mutation_score`` / ``mutants_killed`` / ``mutants_total``
    / ``mutation_detection_rate``，臂级汇总也已有 ``avg_coverage``；logic 档
    批次另含 ``spec_compile_rate`` / ``spec_expr_coverage`` /
    ``specificity_gate_verdict``。缺口不是"没采集"，而是**没登记、没进报告**。

    本工具零 LLM、只读存量工件，把这些数字一次性重放为可引用表格，供
    BASELINE.yaml 登记与论文引用。

口径（诚实）：
    - 每项指标同时给出 **mean / n / 覆盖行数**，n < 臂内任务数即表示部分行
      未采集（不得按 0 解读，遵循 repair_ceiling_report.md §5 的既有纪律）；
    - 变异得分若出现天花板饱和（mean ≈ 1.0），明确标注**无鉴别力**——合成
      集变异体过弱，该指标在此数据集上不能作为测试有效性证据；
    - 只做聚合与呈现，不做任何推断、不补值、不外推。

用法：
    python -m experiments.target_quality_replay experiments/results/main_batch \\
        [--out target_quality_report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# 关注的臂（与 run_benchmark 的三臂口径一致）
_ARMS = ("aitester", "plain_llm", "plain_llm_df")

# 重放指标：(字段名, 展示名, 是否为"越大越好"的前沿对标项)
_METRICS: list[tuple[str, str]] = [
    ("coverage", "被测代码覆盖率"),
    ("mutation_score", "变异得分"),
    ("mutation_detection_rate", "变异体检出率"),
    ("spec_compile_rate", "规约可编译率"),
    ("spec_expr_coverage", "表达式通道覆盖率"),
]

# 天花板饱和阈值：均值 ≥ 该值且样本 ≥ 20 时标注"饱和/无鉴别力"。
# 注意各指标量纲不同——`coverage` 是百分数（0–100），其余为比率（0–1），
# 统一用 0.98 会把 88% 覆盖率误判为饱和，故按指标分别给阈值。
_SATURATION_THRESHOLDS: dict[str, float] = {
    "coverage": 98.0,
    "mutation_score": 0.98,
    "mutation_detection_rate": 0.98,
    "spec_compile_rate": 0.98,
    "spec_expr_coverage": 0.98,
}
_SATURATION_MIN_N = 20


def _iter_batch_files(results_dir: str | Path) -> list[Path]:
    """列出结果目录下的批次 JSON（目录或单文件均可）。"""
    root = Path(results_dir)
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("*.json") if p.is_file())


def _num(rows: list[dict[str, Any]], key: str) -> list[float]:
    """抽取数值字段，跳过 None / 非数值（不补 0、不插值）。"""
    out: list[float] = []
    for r in rows:
        v = r.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _fmt(mean: float | None, n: int) -> str:
    if mean is None:
        return "n/a"
    return f"{mean:.3f}" if mean <= 1.0 else f"{mean:.1f}"


def _arm_rows(batch: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    """取指定臂的行级明细；结构异常时返回空列表（不抛、不猜）。"""
    results = batch.get("results")
    if not isinstance(results, dict):
        return []
    node = results.get(arm)
    if not isinstance(node, dict):
        return []
    details = node.get("details")
    return details if isinstance(details, list) else []


def _collect(results_dir: str | Path) -> dict[str, Any]:
    """聚合全部批次的指标，返回 {批次名: {臂: {指标: (mean, n)}}} 及门控分布。"""
    per_batch: dict[str, dict[str, dict[str, tuple[float | None, int]]]] = {}
    gates: dict[str, Counter] = {}
    totals = Counter()
    detection: dict[str, dict[str, tuple[int, int]]] = {}
    all_values: dict[str, list[float]] = {key: [] for key, _ in _METRICS}

    for path in _iter_batch_files(results_dir):
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(batch, dict):
            continue
        name = path.name
        per_batch[name] = {}
        for arm in _ARMS:
            rows = _arm_rows(batch, arm)
            if not rows:
                continue
            stats: dict[str, tuple[float | None, int]] = {}
            for key, _label in _METRICS:
                xs = _num(rows, key)
                stats[key] = (_mean(xs), len(xs))
                all_values[key].extend(xs)
            per_batch[name][arm] = stats

            # 特异性门终审分布（AC2 双门观测）
            g = gates.setdefault(arm, Counter())
            for r in rows:
                v = r.get("specificity_gate_verdict")
                if v is not None:
                    g[str(v)] += 1

            # 检出（detection_rate 为 0/1 或 None）
            det = detection.setdefault(arm, {"pos": 0, "n": 0})
            for r in rows:
                v = r.get("detection_rate")
                if v is None:
                    continue
                det["n"] += 1
                if isinstance(v, (int, float)) and v > 0:
                    det["pos"] += 1

            totals[arm] += len(rows)
    return {
        "per_batch": per_batch,
        "gates": gates,
        "detection": detection,
        "totals": totals,
        "all_values": all_values,
    }


def _render(data: dict[str, Any], results_dir: str) -> str:
    per_batch: dict[str, dict[str, dict[str, tuple[float | None, int]]]] = data["per_batch"]
    gates: dict[str, Counter] = data["gates"]
    detection: dict[str, dict[str, tuple[int, int]]] = data["detection"]
    totals: Counter = data["totals"]

    lines: list[str] = []
    lines.append("# 目标质量存量重放报告（零 LLM，只读工件）")
    lines.append("")
    lines.append(
        "> 生成：`python -m experiments.target_quality_replay "
        f"{results_dir}`　口径：只读存量批次 JSON，不补值、不外推、不调用 LLM。"
    )
    lines.append(
        "> 用途：把**已采集但未登记**的被测代码覆盖率 / 变异得分 / 规约可编译率"
        "固化为可引用数字，供 BASELINE.yaml 登记与对外对标。"
    )
    lines.append("")

    # ── 逐批次表 ───────────────────────────────────────────────────────────
    for key, label in _METRICS:
        lines.append(f"## {label}（`{key}`）")
        lines.append("")
        lines.append("| 批次 | " + " | ".join(_ARMS) + " |")
        lines.append("|------|" + "|".join(["------"] * len(_ARMS)) + "|")
        for name, arms in per_batch.items():
            cells = []
            for arm in _ARMS:
                st = arms.get(arm, {}).get(key)
                cells.append(f"{_fmt(st[0], st[1])}（n={st[1]}）" if st else "—")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")

    # ── 饱和告警 ───────────────────────────────────────────────────────────
    lines.append("## 天花板饱和告警")
    lines.append("")
    saturated = False
    all_values: dict[str, list[float]] = data["all_values"]
    for key, label in _METRICS:
        xs = all_values.get(key) or []
        if len(xs) < _SATURATION_MIN_N:
            continue
        mean_of_means = sum(xs) / len(xs)
        threshold = _SATURATION_THRESHOLDS.get(key, 0.98)
        if mean_of_means >= threshold:
            saturated = True
            lines.append(
                f"- **{label}（`{key}`）饱和**：全量行均值 {mean_of_means:.3f} ≥{threshold}，"
                "指标在当前合成数据集上已达天花板，**无鉴别力**，不得作为测试有效性证据"
                "（参照 ULT/TOSEM'26：无污染基准上 LLM 变异得分均值仅 40.21%）。"
                "结论：必须在 ULT / TestGenEval 等外部基准上重测。"
            )
    if not saturated:
        lines.append("- 未发现饱和指标。")
    lines.append("")

    # ── 检出与特异性门 ─────────────────────────────────────────────────────
    lines.append("## 检出与特异性门（跨批次合计）")
    lines.append("")
    lines.append("| 臂 | 检出阳性/可测 | 检出率 | 特异性门分布 |")
    lines.append("|----|--------------|--------|--------------|")
    for arm in _ARMS:
        d = detection.get(arm)
        if not d or d["n"] == 0:
            continue
        rate = d["pos"] / d["n"]
        g = gates.get(arm, Counter())
        gtxt = "、".join(f"{k}={v}" for k, v in sorted(g.items())) or "—"
        lines.append(f"| {arm} | {d['pos']}/{d['n']} | {rate:.1%} | {gtxt} |")
    lines.append("")
    lines.append(
        "> 读法：`specific_red` = 测试在 buggy 上红且在 fixed 上绿（缺陷特异）；"
        "`over_red` = 过红（buggy/fixed 均红，非特异）。两者之比是检出质量的核心观测。"
    )
    lines.append("")
    lines.append(
        "> **口径警告**：上表跨全部批次**跨代际**合计（含早期 10-01 批次与 E1/E2 "
        "logic 档），仅作**描述性概览**，**不是当前对外口径**。对外引用 detection "
        "一律以 `docs/design/repair_caliber_matrix.md` 与 "
        "`statistical_report_3seed_pooled.md` 的口径编号为准"
        "（aitester 15.8% / plain_llm_df 44.8%，n=261/臂）。遵守该矩阵 §3 引用纪律。"
    )
    lines.append("")

    lines.append("- 各臂累计任务行数：" + "、".join(f"{a}={totals[a]}" for a in _ARMS if totals[a]))
    lines.append("")
    lines.append("*报告生成：experiments/target_quality_replay.py（R5 审查批次，零 LLM）*")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="目标质量存量重放：把已采集的覆盖率/变异/规约指标固化为可引用数字（零 LLM）"
    )
    parser.add_argument("results_dir", help="批次 JSON 目录（或单个 JSON 文件）")
    parser.add_argument("--out", default="target_quality_report.md", help="输出 Markdown 路径")
    args = parser.parse_args(argv)

    data = _collect(args.results_dir)
    if not data["per_batch"]:
        print(f"[FAIL] {args.results_dir} 下未找到可解析的批次 JSON", file=sys.stderr)
        return 1

    text = _render(data, args.results_dir)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(args.results_dir) / out_path.name
    out_path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n[OK] 报告已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
