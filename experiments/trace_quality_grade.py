"""轨迹质量分级（Lucky / Solid / Ideal，纯离线后处理）。

背景（2026 前沿，评估范式从"完成率"转向"可信验证"）：
    前沿研究发现 10.7% 的"通过"轨迹实为"幸运通过"——回归循环、盲目重试、
    缺失验证、无序探索。仅按"是否通过"评分会系统性奖励"行动偏差"，把
    "改对正确代码"与"碰巧改对"混为一谈。本脚本在既有 trace JSONL 上增加
    一个后处理分析层，把每条"通过"轨迹分为三级：

    Ideal —— 单次执行即通过：恰好 1 个 executor 事件且 passed=true
             （首轮干净通过，零循环、零再生成）。
    Solid —— 有序修复后通过：多次 executor 且最终通过，中间含 debug
             （修复循环）且 regenerate ≤ 1，属"定位→修复→验证"的合理迭代。
    Lucky —— 幸运/可疑通过：最终通过但存在以下任一可疑信号：
             a) 反复再生成（regenerate ≥ 2，可能"换掉失败测试"抹红/弱化断言）；
             b) 反复试错（≥ 3 次 executor 才通过，盲目重试）；
             c) 失败后无 debug 直接重试通过（executor 失败后未进修复循环）。
    failed —— task_end passed=false（不计入三级，单独统计）。

设计纪律（与项目 ADR-0003 一致）：
    - 纯只读后处理：只读 trace 文件，不改任何核心工作流、不产副作用；
    - 判定仅依赖 trace 内可观测信号（executor 的 passed、_should_debug 的
      decision），不臆测未记录的行为；
    - 分级是**描述性**的（报告层展示），不参与任何实验主终点裁决。

用法：
    python -m experiments.trace_quality_grade --trace-dir experiments/results/main_batch/traces
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter
from typing import Any


def _load_events(path: str) -> list[dict[str, Any]]:
    """逐行读取一个 trace JSONL，返回事件列表（坏行跳过，不中断整体）。"""
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _regen_reasons(events: list[dict[str, Any]]) -> list[str]:
    """提取 regenerate 决策对应的 reason 列表（细分再生成性质）。"""
    return [
        str(e.get("output", {}).get("reason", ""))
        for e in events
        if e.get("node") == "_should_debug" and e.get("decision") == "regenerate"
    ]


def grade_trace(events: list[dict[str, Any]]) -> str:
    """按可观测信号判定单条轨迹的质量等级（ideal/solid/lucky/failed）。

    Args:
        events: 该任务的 trace 事件列表（含 task_start / node / task_end）。

    Returns:
        "ideal" | "solid" | "lucky" | "failed"。无 task_end 或无法判定时
        保守返回 "failed"（不臆测通过）。
    """
    executors = [e for e in events if e.get("node") == "executor"]
    decisions = [e.get("decision") for e in events if e.get("node") == "_should_debug"]
    regen_reasons = _regen_reasons(events)
    task_end = next((e for e in events if e.get("event") == "task_end"), None)

    if task_end is None or task_end.get("passed") is not True:
        return "failed"

    debug_count = sum(1 for d in decisions if d == "debug")
    passed_flags = [bool(e.get("output", {}).get("passed")) for e in executors]
    # 测试生成错误类的再生成（可疑抹红/弱化：把失败归因到测试侧、换掉失败测试）。
    # 注意：detection_first_all_green / specificity_gate_over_red 两类再生成是
    # 检出优先协议的正常信号，不计为 Lucky。
    test_gen_regen = any("test_gen" in r for r in regen_reasons)

    # Ideal：单次执行即通过（零循环、零再生成）
    if len(executors) == 1 and passed_flags and passed_flags[0] and not decisions:
        return "ideal"

    # Lucky 信号 a：测试生成错误类再生成（抹红/弱化断言）
    if test_gen_regen:
        return "lucky"
    # Lucky 信号 b：反复试错（≥ 3 次 executor 才通过，用满/超过迭代预算）
    if len(executors) >= 3:
        return "lucky"
    # Lucky 信号 c：失败后未进修复循环就直接重试通过（盲目重试）
    if len(executors) >= 2 and debug_count == 0 and any(not p for p in passed_flags[:-1]) and passed_flags[-1]:
        return "lucky"

    # Solid：有序修复后通过（含 debug 修复循环或检出优先再生成）
    return "solid"


def _lucky_signal(events: list[dict[str, Any]]) -> str:
    """返回 Lucky 轨迹命中的具体可疑信号（诊断用，与 grade_trace 同口径）。"""
    executors = [e for e in events if e.get("node") == "executor"]
    decisions = [e.get("decision") for e in events if e.get("node") == "_should_debug"]
    regen_reasons = _regen_reasons(events)
    debug_count = sum(1 for d in decisions if d == "debug")
    passed_flags = [bool(e.get("output", {}).get("passed")) for e in executors]
    if any("test_gen" in r for r in regen_reasons):
        return "regen_test_gen"
    if len(executors) >= 3:
        return "repeated_retry"
    if len(executors) >= 2 and debug_count == 0 and any(not p for p in passed_flags[:-1]) and passed_flags[-1]:
        return "retry_without_debug"
    return "other"


def grade_dir(trace_dir: str) -> dict[str, Any]:
    """扫描 trace 目录，返回分级统计（只读）。"""
    pattern = os.path.join(trace_dir, "*.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        return {"traces": 0, "counts": {}, "lucky_signals": {}, "samples": {}}

    counts: Counter[str] = Counter()
    lucky_signals: Counter[str] = Counter()
    samples: dict[str, str] = {}  # 每级保留一个样例文件名，供人工复核
    per_trace: dict[str, str] = {}

    for path in files:
        events = _load_events(path)
        grade = grade_trace(events)
        counts[grade] += 1
        per_trace[os.path.basename(path)] = grade
        samples.setdefault(grade, os.path.basename(path))
        if grade == "lucky":
            lucky_signals[_lucky_signal(events)] += 1

    total = len(files)
    return {
        "traces": total,
        "counts": dict(counts),
        "rates": {g: round(c / total * 100, 2) for g, c in counts.items()},
        "lucky_signals": dict(lucky_signals),
        "samples": samples,
        "per_trace": per_trace,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="轨迹质量分级（Lucky/Solid/Ideal，纯离线）")
    parser.add_argument(
        "--trace-dir", required=True, help="trace JSONL 目录（如 experiments/results/main_batch/traces）"
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（供下游消费）")
    args = parser.parse_args()

    result = grade_dir(args.trace_dir)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    counts = result["counts"]
    rates = result["rates"]
    print(f"轨迹总数: {result['traces']}")
    print("分级分布:")
    for grade in ("ideal", "solid", "lucky", "failed"):
        c = counts.get(grade, 0)
        r = rates.get(grade, 0.0)
        print(f"  {grade:<6} {c:>5}  ({r:>5.2f}%)")
    # 通过轨迹中的 Lucky 占比（前沿口径：10.7% 幸运通过）
    passed_total = counts.get("ideal", 0) + counts.get("solid", 0) + counts.get("lucky", 0)
    if passed_total > 0:
        lucky_share = counts.get("lucky", 0) / passed_total * 100
        print(f"  —— 通过轨迹中 Lucky 占比: {lucky_share:.2f}%（前沿基线 ~10.7%）")
    if result["lucky_signals"]:
        print("Lucky 子信号分布:")
        for sig, c in sorted(result["lucky_signals"].items(), key=lambda kv: -kv[1]):
            print(f"  {sig:<22} {c}")
    if result["samples"]:
        print("各级样例（供人工复核）:")
        for g, f in sorted(result["samples"].items()):
            print(f"  {g:<6} {f}")


if __name__ == "__main__":
    main()
