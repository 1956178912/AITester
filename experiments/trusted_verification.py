"""可信验证报告（评估范式：从"完成率"转向"可信验证"）。

背景（2026 前沿，用户优化建议第一方向）：
    "完成率"与"可信度"存在系统性偏离——代理常 100% 提交补丁但验证通过率
    仅 44%（GPT-5）/ 18%（Llama 4），且 10.7% 的"通过"轨迹实为"幸运通过"。
    本项目 `passed`（自产测试通过）是**自指指标**，与 detection（gold 裁决）
    反向——故"通过率"不能作为 headline。

本脚本是纯离线后处理层，从既有批次 JSON 出发，产出三个**可信验证**维度：

1. **弃权调整后通过率（trusted_pass_rate）**——passed 且未命中弃权信号的占比。
   弃权信号复用 `src.tools.patch_abstain.evaluate_patch_abstention`（五信号：
   假通过 / 全程全绿未检出 / 终审过红 / 证据 none / 写盘未验证）。把"正确弃权"
   （弃权且该任务 gold 层面本就不可信）从表观成功率中剥离，得到**可信通过率**。
2. **缓存命中率 + 无缓存理论成本**——从 token_usage 的 cache_hits /
   cache_avoided_tokens（P0-1 止血后新增字段）还原"缓存命中率漂移导致的
   成本不可比"。
3. **轨迹质量分级**——复用 trace_quality_grade（Lucky/Solid/Ideal），可选。

设计纪律（ADR-0003）：纯只读，不改核心工作流；字段缺失时保守不弃权
（与 evaluate_patch_abstention 语义一致）；所有口径为描述性观测，不参与
实验主终点裁决。

用法：
    python -m experiments.trusted_verification \
        --batch experiments/results/main_batch/benchmark_synthetic_20261006_140906.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from src.tools.patch_abstain import evaluate_patch_abstention


def _load_rows(path: str) -> dict[str, list[dict[str, Any]]]:
    """读取批次 JSON，返回 {arm: [result_row, ...]}（只读）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results", {})
    if not isinstance(results, dict):
        return {}
    return {arm: v.get("details", []) for arm, v in results.items() if isinstance(v, dict)}


def arm_trusted_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """计算单臂的可信验证指标（弃权调整 + 缓存命中，纯推导）。"""
    total = len(rows)
    passed = sum(1 for r in rows if r.get("passed"))
    # 弃权 = "通过但命中不可信信号"的行（从表观成功率中剥离）。对未通过的行，
    # 弃权无意义（它们本就失败，不算"不可信通过"）——故只在 passed 行上判弃权。
    # 现场重算（不依赖结果行是否已落 patch_abstained 字段；字段缺失时该信号
    # 不命中，与 evaluate_patch_abstention 的保守语义一致）。
    abstain_count = sum(1 for r in rows if r.get("passed") and evaluate_patch_abstention(r)["abstain"])
    # 可信通过 = 通过且未弃权（弃权 + 可信通过 = passed，可自洽校验）
    trusted_pass = sum(1 for r in rows if r.get("passed") and not evaluate_patch_abstention(r)["abstain"])

    # 缓存命中（P0-1 后 token_usage.as_dict() 携带；历史批次缺字段记 0）
    cache_hits = sum((r.get("token_usage") or {}).get("cache_hits", 0) for r in rows)
    cache_avoided = sum((r.get("token_usage") or {}).get("cache_avoided_tokens", 0) for r in rows)
    total_tokens = sum((r.get("token_usage") or {}).get("total_tokens", 0) for r in rows)
    llm_calls = sum((r.get("token_usage") or {}).get("llm_calls", 0) for r in rows)

    def _pct(n: int, d: int) -> float | None:
        return round(n / d * 100, 2) if d > 0 else None

    return {
        "total": total,
        "passed": passed,
        "passed_rate_pct": _pct(passed, total),
        "abstained": abstain_count,
        "trusted_pass": trusted_pass,
        "trusted_pass_rate_pct": _pct(trusted_pass, total),
        "cache_hits": cache_hits,
        "cache_avoided_tokens": cache_avoided,
        "cache_hit_rate_pct": _pct(cache_hits, cache_hits + llm_calls),
        "uncached_theoretical_tokens": total_tokens + cache_avoided,
    }


def build_report(batch_path: str) -> dict[str, Any]:
    """产出可信验证报告（弃权调整 + 缓存命中，按臂分组）。"""
    rows_by_arm = _load_rows(batch_path)
    return {arm: arm_trusted_metrics(rows) for arm, rows in rows_by_arm.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="可信验证报告（弃权调整 + 缓存命中）")
    parser.add_argument("--batch", required=True, help="批次 JSON 路径")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = build_report(args.batch)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for arm, m in report.items():
        print(f"=== {arm} ===")
        print(f"  任务数: {m['total']}")
        print(f"  passed（自指通过率）: {m['passed']} ({m['passed_rate_pct']}%)")
        print(f"  弃权（剥离不可信通过）: {m['abstained']}")
        print(f"  trusted_pass（可信通过）: {m['trusted_pass']} ({m['trusted_pass_rate_pct']}%)")
        print(f"  缓存命中率: {m['cache_hit_rate_pct']}%（命中 {m['cache_hits']} / 调用 {m['cache_hits']} + 真实）")
        print(f"  无缓存理论 token: {m['uncached_theoretical_tokens']}（真实 + 避免 {m['cache_avoided_tokens']}）")
        print()


if __name__ == "__main__":
    main()
