#!/usr/bin/env python3
"""
R14（2026-10-05 审查批次）：性能基准回归比对（weekly perf.yml 配套，non-blocking）。

背景：
    scripts/tools/performance_benchmark.py 只输出当次跑分（experiments/results/
    performance_benchmark.json），无基线比对逻辑——性能劣化只能靠人工翻
    历史产物发现。本脚本把当次跑分与 docs/performance_baseline.json 基线
    逐指标（category -> metric -> avg_ms）比对，超过阈值输出告警。

口径（为什么是 non-blocking）：
    1. 跑分受运行机硬件 / 负载影响（基线在 macOS arm64 开发机生成，CI 在
       ubuntu-latest 执行），亚毫秒级指标跨机相对偏差天然大于 15%，
       阻断会造成假阳性红 CI；
    2. 因此默认仅告警（退出码恒 0），供 weekly 巡检人工研判；确需阻断时
       显式传 --strict（本地/独立环境同机比对场景）。
    过滤噪声：相对劣化超阈值 且 绝对劣化超过绝对下限（默认 0.05ms）才告警
    ——基线中多个 avg_ms < 0.01ms 的指标（纯函数解析路径）处于定时器噪声
    量级，单纯相对阈值必然误报。

用法：
    python scripts/gates/check_perf_regression.py \
        --baseline docs/performance_baseline.json \
        --current experiments/results/performance_benchmark.json
    可选：--threshold 0.15（相对阈值）  --abs-floor-ms 0.05（绝对下限）
          --strict（有告警时退出码 1）
          --update-baseline（把 current 刷写为新的基线文件，用于基线漂移后
          从 CI 产物重建——CI 无推送权限，需下载产物后本地执行再提交）

退出码：0 = 通过或仅有告警（non-blocking 默认）；1 = --strict 下有告警，
    或产物/基线文件缺失、结构不兼容（快速失败口径，避免静默跳过比对）。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASELINE = PROJECT_ROOT / "docs" / "performance_baseline.json"
DEFAULT_CURRENT = PROJECT_ROOT / "experiments" / "results" / "performance_benchmark.json"


def _load_results(path: Path) -> dict:
    """加载跑分 JSON（category -> metric -> {avg_ms, ...}）。

    顶层 _meta 键（基线文件里的生成环境说明）跳过，不算跑分类目。
    """
    if not path.exists():
        print(f"[错误] 文件不存在: {path}")
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[错误] JSON 解析失败: {path} ({e})")
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"[错误] 顶层结构应为对象: {path}")
        sys.exit(2)
    return data


def _iter_metrics(data: dict):
    """展开 (类目, 指标名, avg_ms) 三元组；无 avg_ms 的条目忽略。"""
    for category, metrics in data.items():
        if category.startswith("_") or not isinstance(metrics, dict):
            continue
        for metric, values in metrics.items():
            if isinstance(values, dict) and "avg_ms" in values:
                yield category, metric, float(values["avg_ms"])


def main() -> int:
    parser = argparse.ArgumentParser(description="性能基准回归比对（默认 non-blocking）")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="基线 JSON 路径")
    parser.add_argument("--current", default=str(DEFAULT_CURRENT), help="当次跑分 JSON 路径")
    parser.add_argument("--threshold", type=float, default=0.15, help="相对劣化阈值（默认 0.15 = 15%%）")
    parser.add_argument("--abs-floor-ms", type=float, default=0.05, help="绝对劣化下限 ms（过滤定时器噪声）")
    parser.add_argument("--strict", action="store_true", help="有告警时退出码 1（默认仅告警）")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="把 current 刷写为新的基线文件（含 _meta 生成信息）后退出",
    )
    args = parser.parse_args()

    current_path = Path(args.current)
    baseline_path = Path(args.baseline)
    current = _load_results(current_path)

    if args.update_baseline:
        current["_meta"] = {
            "description": "R14 性能基准基线：结构与 scripts/tools/performance_benchmark.py 的输出一致（category -> metric -> {avg_ms, ...})。",
            "generated_at": datetime.now(tz=UTC).date().isoformat(),
            "generated_on": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
            "note": "由 scripts/gates/check_perf_regression.py --update-baseline 生成；跨机偏差说明见 docs/performance_baseline.json 原始注释与脚本 docstring。",
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[基线刷新] 已写入 {baseline_path}（请提交该文件使新基线生效）")
        return 0

    baseline = _load_results(baseline_path)

    base_metrics = {f"{c}/{m}": v for c, m, v in _iter_metrics(baseline)}
    cur_metrics = {f"{c}/{m}": v for c, m, v in _iter_metrics(current)}

    if not base_metrics or not cur_metrics:
        print("[错误] 基线或当次跑分中未找到任何含 avg_ms 的指标（结构不兼容）")
        return 2

    warnings: list[str] = []
    improvements: list[str] = []
    for key, base_v in sorted(base_metrics.items()):
        cur_v = cur_metrics.get(key)
        if cur_v is None:
            warnings.append(f"指标在当次跑分中缺失（脚本输出结构变更？）: {key}")
            continue
        delta_ms = cur_v - base_v
        delta_rel = delta_ms / base_v if base_v > 0 else 0.0
        if delta_rel > args.threshold and delta_ms > args.abs_floor_ms:
            warnings.append(
                f"性能劣化: {key} 基线 {base_v:.4f}ms -> 当前 {cur_v:.4f}ms "
                f"(+{delta_rel * 100:.1f}%, +{delta_ms:.4f}ms)"
            )
        elif delta_rel < -args.threshold and -delta_ms > args.abs_floor_ms:
            improvements.append(f"性能改善: {key} {base_v:.4f}ms -> {cur_v:.4f}ms ({delta_rel * 100:.1f}%)")

    warnings.extend(
        f"新增指标（基线未登记，可考虑 --update-baseline 刷新基线）: {key}"
        for key in sorted(set(cur_metrics) - set(base_metrics))
    )

    print(
        f"比对完成: 基线 {len(base_metrics)} 项 / 当次 {len(cur_metrics)} 项, 阈值 {args.threshold * 100:.0f}% + {args.abs_floor_ms}ms"
    )
    for w in warnings:
        print(f"  [warn] {w}")
    for i in improvements:
        print(f"  [info] {i}")
    if not warnings:
        print("无性能劣化告警")
        return 0
    print(f"共 {len(warnings)} 条告警（non-blocking 口径，供 weekly 巡检人工研判；--strict 可转阻断）")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
