"""CPR/IDR 补丁检测有效性离线分析（修复引擎路线第三阶段前置，零 LLM）。

背景（2026-10-07 修复引擎批次 II）：
    repair 全线 0 的漏斗（patch 产出 94.2% → plausible 46.8% → correct 0）
    表明系统的补丁「验证/门控通道」对 plausible-but-wrong 补丁的拦截
    效果从未被独立量化。前沿口径（Passerine 合理 73% vs 语义等价 43%、
    Wang/Pradel 虚高 6.2pp）把「弃权与验证」列为修复引擎的核心能力，
    本脚本把既有批次工件中的负信号转为两个可跟踪指标：

    - IDR（Incorrect-patch Detection Rate，错误补丁检测率）：
      plausible-but-wrong 行（patch_plausible=1 且 gold 裁决
      patch_correct=0）中，被至少一个系统负信号标记的比例。
      负信号集合（字段缺失不计）：
        patch_evidence_level == "none"（证据门无背书）
        source_patched_unverified is True（写盘无验证）
        patch_rolled_back is True（回滚通道触发）
        red_regression_violation 为真（红回归门拦截）
        specificity_gate_verdict == "over_red"（特异性门过红）
        stop_reason == "regression_detected"（回归停止）
    - CPR（Correct-patch Retention Rate，正确补丁保留率）：
      patch_correct=1 行中未被任何负信号/回滚误伤的比例。
      当前主批次 correct=0 → CPR 无定义（诚实输出 None，不编造）。

用法（确定性、无网络、无 LLM；报告只打 stdout，落盘用 shell 重定向）：
    python experiments/cpr_idr_report.py \
        [--results-dir experiments/results/main_batch] [--arm aitester]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# 仓库根入 sys.path（直接 `python experiments/cpr_idr_report.py` 执行时
# 脚本目录是 experiments/，src 不可导入——与 bayesian_paired 等既有
# experiments 脚本同款引导）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 负信号判定：行级字段 → 是否构成「系统检测到该补丁可疑」
_NEGATIVE_SIGNALS: tuple[tuple[str, str], ...] = (
    ("patch_evidence_level", "none"),
    ("specificity_gate_verdict", "over_red"),
    ("stop_reason", "regression_detected"),
)
_FLAG_FIELDS: tuple[str, ...] = (
    "source_patched_unverified",
    "patch_rolled_back",
    "red_regression_violation",
)


def _row_flagged(row: dict[str, Any]) -> bool:
    """该结果行是否携带至少一个系统负信号（字段缺失 = 无信号，保守不计）。"""
    for field, value in _NEGATIVE_SIGNALS:
        if row.get(field) == value:
            return True
    return any(row.get(field) is True for field in _FLAG_FIELDS)


def _load_rows(results_dir: str, arm: str) -> list[tuple[str, dict[str, Any]]]:
    """加载目录下所有批次 JSON 指定臂的 details 行（(批次文件名, 行) 列表）。

    仅接受含 results.<arm>.details 的批次（schema 过滤与统计层同思路：
    缺字段批次不进分母，避免混入异构 schema）。
    """
    rows: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        if os.path.basename(path).startswith("SHA256"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        details = ((data.get("results") or {}).get(arm) or {}).get("details")
        if not isinstance(details, list):
            continue
        base = os.path.basename(path)
        rows.extend((base, row) for row in details if isinstance(row, dict) and "patch_plausible" in row)
    return rows


def _analyze(rows: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """聚合 IDR/CPR/弃权视角与漏斗分母（确定性，无随机成分）。"""
    from src.tools.patch_abstain import evaluate_patch_abstention

    incorrect_total = incorrect_flagged = 0
    correct_total = correct_retained = 0
    signal_dist: Counter[str] = Counter()
    plausible_total = 0
    # 弃权视角（批次 V，ADR-0020 观测层）：would-be abstention——用弃权
    # 信号集在存量工件上回放"若弃权门开启会压制什么"。两口径：
    #   plausible 命中率：plausible 行中命中弃权信号的比例（拦截面）；
    #   passed 压制数：passed=True 行中命中数（被压制的"成功"，其
    #   中 false_fix 占比 = 弃权精确率的存量估计——correct=0 时为 100%）。
    abstain_plausible_hits = 0
    passed_total = 0
    passed_abstained = 0
    passed_abstained_incorrect = 0
    for _batch, row in rows:
        would_abstain = evaluate_patch_abstention(row)["abstain"]
        if row.get("passed"):
            passed_total += 1
            if would_abstain:
                passed_abstained += 1
                # 弃权精确率分子：被压制的"成功"中 gold 裁决失败的部分
                # （false_fix 或 repair=0）
                if row.get("patch_correct") == 0 or row.get("false_fix_rate") == 1.0:
                    passed_abstained_incorrect += 1
        if row.get("patch_plausible") != 1:
            continue
        plausible_total += 1
        abstain_plausible_hits += int(would_abstain)
        flagged = _row_flagged(row)
        if flagged:
            for field, value in _NEGATIVE_SIGNALS:
                if row.get(field) == value:
                    signal_dist[field] += 1
            for field in _FLAG_FIELDS:
                if row.get(field) is True:
                    signal_dist[field] += 1
        if row.get("patch_correct") == 0:
            incorrect_total += 1
            incorrect_flagged += int(flagged)
        elif row.get("patch_correct") == 1:
            correct_total += 1
            correct_retained += int(not flagged)
    return {
        "plausible_total": plausible_total,
        "incorrect_total": incorrect_total,
        "incorrect_flagged": incorrect_flagged,
        "idr": (incorrect_flagged / incorrect_total) if incorrect_total else None,
        "correct_total": correct_total,
        "correct_retained": correct_retained,
        # correct=0 时 CPR 无定义（None ≠ 0.0：无分母与「全部误伤」是两回事）
        "cpr": (correct_retained / correct_total) if correct_total else None,
        "signal_dist": dict(signal_dist),
        # 弃权视角（ADR-0020 观测层回放）
        "abstain_plausible_hits": abstain_plausible_hits,
        "abstain_plausible_rate": (abstain_plausible_hits / plausible_total) if plausible_total else None,
        "passed_total": passed_total,
        "passed_abstained": passed_abstained,
        "passed_abstained_incorrect": passed_abstained_incorrect,
        "abstain_precision": (passed_abstained_incorrect / passed_abstained) if passed_abstained else None,
    }


def _fmt_ratio(value: float | None) -> str:
    return "—（无分母，未定义）" if value is None else f"{value:.4f}"


def build_report(results_dir: str, arm: str) -> str:
    """生成 Markdown 报告（内容确定性：只依赖工件，不含时间戳）。"""
    rows = _load_rows(results_dir, arm)
    stats = _analyze(rows)
    batches = sorted({batch for batch, _ in rows})
    lines = [
        "# CPR/IDR 补丁检测有效性报告（离线，零 LLM）",
        "",
        f"- 数据：`{results_dir}` × 臂 `{arm}`，批次 {len(batches)} 个，",
        f"  plausible 行 {stats['plausible_total']} 条（负信号口径见脚本 docstring）。",
        "- 指标：IDR = 错误补丁检测率（plausible-but-wrong 中被系统负信号",
        "  标记的比例）；CPR = 正确补丁保留率（correct 中未被误伤的比例）。",
        "",
        "## 汇总",
        "",
        "| 指标 | 值 | 分母 |",
        "|---|---|---|",
        f"| IDR（错误补丁检测率） | {_fmt_ratio(stats['idr'])} | incorrect = {stats['incorrect_total']}（flagged {stats['incorrect_flagged']}） |",
        f"| CPR（正确补丁保留率） | {_fmt_ratio(stats['cpr'])} | correct = {stats['correct_total']}（retained {stats['correct_retained']}） |",
        "",
        "## 负信号分布（plausible 行上各信号命中数）",
        "",
    ]
    if stats["signal_dist"]:
        lines.append("| 信号 | 命中数 |")
        lines.append("|---|---|")
        lines.extend(f"| `{key}` | {stats['signal_dist'][key]} |" for key in sorted(stats["signal_dist"]))
    else:
        lines.append("（无：plausible 行上没有任何负信号命中）")
    lines += [
        "",
        "## 弃权视角（would-be abstention，ADR-0020 观测层回放）",
        "",
        "| 口径 | 值 | 分母 |",
        "|---|---|---|",
        f"| plausible 命中弃权信号 | {_fmt_ratio(stats['abstain_plausible_rate'])} | plausible = {stats['plausible_total']}（命中 {stats['abstain_plausible_hits']}） |",
        f"| passed 将被压制 | {stats['passed_abstained']} | passed = {stats['passed_total']} |",
        f"| 弃权精确率（被压制的「成功」中 gold 裁决失败占比） | {_fmt_ratio(stats['abstain_precision'])} | 被压制 {stats['passed_abstained']}（其中裁决失败 {stats['passed_abstained_incorrect']}） |",
        "",
        "说明：would-be abstention 是弃权门若开启时的存量回放（信号集见",
        "src/tools/patch_abstain.py）；correct=0 的批次上弃权精确率按构造",
        "为 1.0（所有被压制的「成功」均为 false fix）——修复率破零后该指标",
        "才开始真实区分「压制假修复」与「误伤真修复」。",
        "",
        "## 诚实披露",
        "",
        "- CPR 在 correct=0 的批次上无定义（None ≠ 0.0）；修复率破零前",
        "  该指标仅随 repair 产出自动可用，不应手工填数。",
        "- IDR 只统计「系统侧已落地的信号通道」；未接线的检测能力",
        "  （如行为差分、gold 官方测试复跑）不在此口径内，提升空间",
        "  体现为 IDR 上升而非口径放宽。",
        f"- 批次清单：{', '.join(batches) if batches else '（无有效批次）'}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口（报告打 stdout；返回 0 供 CI/测试消费）。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", default="experiments/results/main_batch", help="批次工件目录")
    parser.add_argument("--arm", default="aitester", help="基线臂名（如 aitester / plain_llm_df）")
    args = parser.parse_args(argv)
    print(build_report(args.results_dir, args.arm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
