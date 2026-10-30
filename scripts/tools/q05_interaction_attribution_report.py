#!/usr/bin/env python3
"""Q05 交互中心失败归因：跨批次聚合 attribution_edge × attribution_fault_side。

背景（登记册 Q05 = "维度已实装；无专门批次与读数"）：
    `src/observability/failure_taxonomy.py` 的 `summarize_batch` 已把
    `fault_side_counts` / `edge_counts` 写进每个批次的
    `results.<arm>.failure_bucket_distribution`，但从未有跨批次汇总。
    本脚本只读既有工件做分层聚合，不产生新的归因判定。

口径纪律：
- 聚合单元 = "批次目录 × 臂"（一次 run_benchmark 产物的一个臂）；
- **分层是硬要求**：交互边（planner_to_generator 等）只在编排臂上被标注，
  单臂（plain_llm / plain_llm_df / single_agent…）的失败天然落在 harness /
  uncategorized，跨臂合并会把"维度没被触发"读成"维度测过且为 0"；
- 数字全部来自工件字面量（memory 纪律 #1：文档数字必须来自工件）。

用法：
    .venv/bin/python3 scripts/tools/q05_interaction_attribution_report.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "experiments" / "results"

EDGES = (
    "planner_to_generator",
    "generator_to_executor",
    "debugger_to_executor",
    "harness",
    "uncategorized",
)
SIDES = ("model_side", "harness_side", "environment", "grader", "uncategorized")

# 臂分层（与登记册/报告的臂语义一致）：
#   orchestration = 完整多智能体编排（aitester）
#   baseline      = 非编排对照臂（plain_llm / plain_llm_df* / single_agent / 其他）
# 判定用 _tier() 的名字比对，勿另建名字集合（曾留拼写错误的死常量，已删）。


def _tier(arm: str) -> str:
    return "orchestration" if arm.strip().lower() == "aitester" else "baseline"


def collect() -> tuple[list[dict], int, int]:
    """读全部批次工件，返回 (聚合单元列表, 批次文件数, 含归因字段文件数)。"""
    units: list[dict] = []
    n_files = 0
    n_have = 0
    for path in sorted(RESULTS.rglob("benchmark_*.json")):
        n_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        got = False
        rel = path.parent.relative_to(RESULTS).as_posix()
        for arm, blk in (payload.get("results") or {}).items():
            if not isinstance(blk, dict):
                continue
            fbd = blk.get("failure_bucket_distribution")
            if not isinstance(fbd, dict) or "edge_counts" not in fbd:
                continue
            got = True
            units.append(
                {
                    "batch": rel,
                    "file": path.name,
                    "arm": arm,
                    "tier": _tier(arm),
                    "total": int(fbd.get("total") or 0),
                    "unclassified_rows": int(fbd.get("unclassified_rows") or 0),
                    "harness_invalid_rows": int(fbd.get("harness_invalid_rows") or 0),
                    "edge_counts": {k: int(fbd["edge_counts"].get(k, 0) or 0) for k in EDGES},
                    "fault_side_counts": {k: int(fbd["fault_side_counts"].get(k, 0) or 0) for k in SIDES},
                }
            )
        if got:
            n_have += 1
    return units, n_files, n_have


def summarize(units: list[dict]) -> dict:
    """按层聚合 + 全量聚合（全量仅供对账，不作结论口径）。"""

    def _agg(rows: list[dict]) -> dict:
        edge = Counter()
        side = Counter()
        total = 0
        for u in rows:
            total += u["total"]
            edge.update(u["edge_counts"])
            side.update(u["fault_side_counts"])
        denom = total or 1
        return {
            "units": len(rows),
            "total_rows": total,
            "edge_counts": dict(edge),
            "fault_side_counts": dict(side),
            "edge_shares": {k: round(v / denom, 4) for k, v in edge.items()},
            "fault_side_shares": {k: round(v / denom, 4) for k, v in side.items()},
        }

    tiers = {t: _agg([u for u in units if u["tier"] == t]) for t in ("orchestration", "baseline")}
    return {"orchestration": tiers["orchestration"], "baseline": tiers["baseline"], "all": _agg(units)}


def render_markdown(payload: dict) -> str:
    """渲染人类可读摘要（分层口径 + 结构发现）。"""
    s = payload["summary"]
    lines = [
        "# Q05 交互中心失败归因：跨批次分层聚合（2026-10-30）",
        "",
        "> 口径：只读 `experiments/results/**/benchmark_*.json` 的既有"
        " `failure_bucket_distribution.{edge_counts,fault_side_counts}`，"
        "不产生新归因判定。聚合单元 = 批次目录 × 臂。",
        "",
        f"- 批次文件：{payload['n_files']} 份（含归因字段 {payload['n_have']} 份）；聚合单元 {len(payload['units'])} 个",
        f"- 可分类任务行合计：{s['all']['total_rows']}（编排臂 {s['orchestration']['total_rows']} / 对照臂 {s['baseline']['total_rows']}）",
        "",
        "## 分层汇总（结论口径）",
        "",
        "| 层 | 单元数 | 任务行 | planner→gen | gen→exec | debugger→exec | harness | uncategorized |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tier, label in (("orchestration", "编排臂 (aitester)"), ("baseline", "对照臂"), ("all", "全量(仅对账)")):
        a = s[tier]
        c = a["edge_counts"]
        lines.append(
            f"| {label} | {a['units']} | {a['total_rows']} | {c.get('planner_to_generator', 0)} "
            f"| {c.get('generator_to_executor', 0)} | {c.get('debugger_to_executor', 0)} "
            f"| {c.get('harness', 0)} | {c.get('uncategorized', 0)} |"
        )
    orch = s["orchestration"]
    oc = orch["edge_counts"]
    orch_total = orch["total_rows"] or 1
    lines += [
        "",
        "## 结构发现",
        "",
        f"1. **对照臂几乎不产出交互边归因**（维度只在编排链路上被标注）——"
        f"对照臂 uncategorized = {s['baseline']['fault_side_counts'].get('uncategorized', 0)}",
        "   行中的绝大多数；跨臂合并会把「维度没被触发」读成「维度测过且为 0」，故结论只取编排臂层。",
        f"2. 编排臂内 edge 分布（占比按编排臂任务行 {orch_total} 计）：",
        f"   planner_to_generator {oc.get('planner_to_generator', 0)}（{orch['edge_shares'].get('planner_to_generator', 0):.2%}）、"
        f"debugger_to_executor {oc.get('debugger_to_executor', 0)}（{orch['edge_shares'].get('debugger_to_executor', 0):.2%}）、"
        f"harness {oc.get('harness', 0)}（{orch['edge_shares'].get('harness', 0):.2%}）、"
        f"generator_to_executor {oc.get('generator_to_executor', 0)}（{orch['edge_shares'].get('generator_to_executor', 0):.2%}）。",
        "3. fault_side：environment 与 grader 两侧在全部工件中恒为 0"
        "（标注器当前不产出这两类）——读「0」前必须先读这条，这是标注器覆盖上限，不是实测为零。",
        "",
        "## 工件",
        "",
        "- 机器可读：`q05_interaction_attribution_20261030/Q05_AGGREGATE.json`",
        "- 本摘要：`q05_interaction_attribution_20261030/Q05_SUMMARY.md`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(RESULTS / "q05_interaction_attribution_20261030"))
    args = ap.parse_args()

    units, n_files, n_have = collect()
    if not units:
        print("未找到含归因字段的批次工件", flush=True)
        return 1
    summary = summarize(units)
    payload = {
        "schema": "aitester_q05_interaction_attribution/1",
        "generated_on": datetime.now(tz=UTC).date().isoformat(),
        "caliber": "聚合单元=批次目录×臂；分层=编排臂(aitester)/对照臂；数字全部来自工件 failure_bucket_distribution",
        "n_files": n_files,
        "n_have": n_have,
        "units": units,
        "summary": summary,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "Q05_AGGREGATE.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    out_md = out_dir / "Q05_SUMMARY.md"
    out_md.write_text(render_markdown(payload), encoding="utf-8")
    print(f"批次 {n_files} 份（含字段 {n_have}）/ 单元 {len(units)} / 任务行 {summary['all']['total_rows']}")
    print(f"编排臂行 {summary['orchestration']['total_rows']} / 对照臂行 {summary['baseline']['total_rows']}")
    print(f"写入：{out_json}")
    print(f"写入：{out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
