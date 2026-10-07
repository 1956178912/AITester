"""反事实 FL 上界归因分解（修复引擎批次 X，ADR-0024，零 LLM）。

背景：
    RGFL 式反事实上界分析——把"修复失败"严格分解为**定位侧瓶颈**
    （FL 未命中）与**生成侧瓶颈**（FL 命中但补丁未通过 gold 裁决），
    回答"如果 FL 给出正确位置，修复能否成功"。ADR-0021 修复 correct
    口径后，存量工件即可分解（此前 correct 恒 0 无法归因）。

两件套：
    1. 本模块（存量回放，零 LLM 立即出数）：localization_hit_function
       × 修正口径 correct（repair_replay 同源判定）的 2×2 分解；
    2. 运行时反事实臂（FL_GOLD_INJECTION_ENABLE，默认关，跑批用）：
       定位段直接用 gold 函数构造（fault_localizer.
       build_gold_injection_localization），对照臂差 = FL 的端到端贡献。

回放口径（保守、可复算）：
    - 行纳入条件：localization_hit_function 非 None（LLM 定位产出过）
      ∧ patch 非空 ∧ gold test_cases 非空（与 repair_replay 一致）；
    - 分解表：
        FL 命中 ∧ correct  → 双对（a）
        FL 命中 ∧ ¬correct → 生成侧瓶颈（b）——给对位置仍修不好
        ¬FL 命中 ∧ correct → 碰巧修对（c）
        ¬FL 命中 ∧ ¬correct → 定位侧瓶颈上界（d）
    - 关键比率：
        P(correct | FL 命中) = a/(a+b)——"完美 FL"下修复率的存量代理
        （上界估计的观测成分；严格上界需运行时反事实臂）；
        FL 归因损失 = (a+b)/(a+b+c+d) − a/(a+b+c+d) 的定位差分。

用法：
    python -m experiments.cf_upper_bound experiments/results/main_batch \
        --arm aitester [--out cf_report.md] [--timeout 60]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _iter_batch_files(results_dir: str | Path) -> list[Path]:
    root = Path(results_dir)
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("benchmark_*.json") if p.is_file())


def _iter_rows(batch: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    arm_data = (batch.get("results") or {}).get(arm) or {}
    return [r for r in (arm_data.get("details") or []) if isinstance(r, dict)]


def fl_hit_value(row: dict[str, Any]) -> tuple[bool | None, str]:
    """行级 FL 命中值提取（批次 XIII 抽出供 corrected_metrics 复用）。

    口径：优先 LLM 函数级命中（批次 I 起 localization_hit_function）；
    存量批次（批次 I 前跑批）无该字段时回退谱系行级 FL@1（E2 批次
    19/53 可测）——两口径粒度不同，第二返回值标注来源
    （"localization_hit_function" | "fl_at_1_spectral"）；均缺 →
    (None, "none")（不可测）。
    """
    fl_hit = row.get("localization_hit_function")
    if fl_hit is not None:
        return bool(fl_hit), "localization_hit_function"
    fl_at_k = row.get("fl_at_k")
    if isinstance(fl_at_k, dict) and fl_at_k.get("fl_at_1") is not None:
        return bool(fl_at_k.get("fl_at_1")), "fl_at_1_spectral"
    return None, "none"


def decompose_batch(batch_path: Path, arm: str, timeout: int = 60) -> dict[str, Any]:
    """单批次 2×2 分解（确定性；修正 correct 复用 repair_replay 判定）。"""
    from experiments.repair_replay import replay_row

    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    cells = {"a_both": 0, "b_gen_bottleneck": 0, "c_lucky": 0, "d_fl_bottleneck": 0}
    fl_sources: dict[str, int] = {}
    skipped = 0
    for row in _iter_rows(batch, arm):
        fl_hit, fl_source = fl_hit_value(row)
        if fl_hit is None:
            skipped += 1
            continue
        verdict = replay_row(row, timeout=timeout)
        status = verdict["status"]
        if status not in ("correct", "wrong_patch"):
            skipped += 1  # 无补丁 / 无 gold 材料 / diff 不可重放 / 异常
            continue
        fl_sources[fl_source] = fl_sources.get(fl_source, 0) + 1
        correct = status == "correct"
        if fl_hit and correct:
            cells["a_both"] += 1
        elif fl_hit and not correct:
            cells["b_gen_bottleneck"] += 1
        elif not fl_hit and correct:
            cells["c_lucky"] += 1
        else:
            cells["d_fl_bottleneck"] += 1
    return {"file": batch_path.name, "cells": cells, "skipped": skipped, "fl_sources": fl_sources}


def build_report(results_dir: str | Path, arm: str, timeout: int = 60) -> str:
    """多批次归因分解报告（Markdown）。"""
    files = _iter_batch_files(results_dir)
    lines = [
        "# 反事实 FL 上界归因分解（ADR-0024，批次 X，零 LLM 存量回放）",
        "",
        f"- 回放目录：`{results_dir}`（{len(files)} 个批次文件）；臂：`{arm}`",
        "- correct 口径：ADR-0021 修正（normalize_patch_text 清理后 gold 裁决）；",
        "  FL 口径：结果行 localization_hit_function（LLM 推理定位首位候选 ∈ gold 函数）。",
        "",
        "| 批次文件 | a 双对 | b 生成侧瓶颈 | c 碰巧修对 | d 定位侧瓶颈 | 跳过 |",
        "|---|---|---|---|---|---|",
    ]
    total = {"a_both": 0, "b_gen_bottleneck": 0, "c_lucky": 0, "d_fl_bottleneck": 0, "skipped": 0}
    for f in files:
        try:
            r = decompose_batch(f, arm, timeout=timeout)
        except Exception as e:  # —— 单文件异常不阻断整体
            lines.append(f"| {f.name} | 读取失败：{e} | — | — | — | — |")
            continue
        c = r["cells"]
        for k in total:
            total[k] += c.get(k, 0) if k != "skipped" else r.get("skipped", 0)
        lines.append(
            f"| {r['file']} | {c['a_both']} | {c['b_gen_bottleneck']} "
            f"| {c['c_lucky']} | {c['d_fl_bottleneck']} | {r['skipped']} |"
        )
    a, b, c, d = total["a_both"], total["b_gen_bottleneck"], total["c_lucky"], total["d_fl_bottleneck"]
    fl_hit_n, fl_miss_n = a + b, c + d
    n = fl_hit_n + fl_miss_n
    p_cond = round(a / fl_hit_n, 4) if fl_hit_n else None
    p_overall = round((a + c) / n, 4) if n else None
    lines += [
        "",
        f"**合计**（可分解 {n} 行，跳过 {total['skipped']}）：",
        f"- FL 命中率（可分解行）：{round(fl_hit_n / n, 4) if n else None}",
        f"- **P(correct | FL 命中) = {p_cond}**（完美 FL 下修复率的存量代理——a/(a+b)）",
        f"- P(correct | FL 未命中) = {round(c / fl_miss_n, 4) if fl_miss_n else None}（c/(c+d)，碰巧修对）",
        f"- 实测 repair（修正口径）：{p_overall}（(a+c)/n）",
        "",
        "> 解读：b/(a+b) 为生成侧瓶颈占比（给对位置仍修不好——Debugger",
        "> 合成段的优化空间）；d/(c+d) 为定位侧瓶颈占比（FL 改进的潜在",
        "> 收益上界代理）。严格反事实上界（gold 注入臂 vs LLM 臂的端到端",
        "> 差分）须跑批：FL_GOLD_INJECTION_ENABLE=true（ADR-0024 运行时臂）。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="反事实 FL 上界归因分解（ADR-0024，零 LLM）")
    parser.add_argument("results", help="批次 JSON 文件或所在目录")
    parser.add_argument("--arm", default="aitester", help="分解臂名（默认 aitester）")
    parser.add_argument("--out", default=None, help="报告写盘路径（缺省打印到 stdout）")
    parser.add_argument("--timeout", type=int, default=60, help="单行 pytest 超时（秒）")
    args = parser.parse_args(argv)
    report = build_report(args.results, args.arm, timeout=args.timeout)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"归因分解报告已写入：{args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
