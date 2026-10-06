"""MAST 失效模式分布分析（AG1，2026-10-06 第十一轮审查遗留项 → 论文 C2 轴素材）。

目的：对既有批次的逐任务 trace（experiments/results/main_batch/traces/）
离线聚合 MAST（Cemri et al., arXiv 2503.13657）失效模式分布——按臂
（aitester / plain_llm / plain_llm_df）统计每种失效模式命中的任务文件
数与命中率。回答"编排管线在检出口径下为何净负"的分类学问题，为论文
分析节提供可发表素材（与 MAST 标注的多智能体研究横向可比）。

口径：
- 观测单元 = 单个 trace 文件（= 单任务×单臂×单次运行；多种子批次
  天然按文件分列）；
- 模式判定复用 src/observability/agent_telemetry.match_failure_patterns
  （Y2 MAST 14 类映射，纯离线零 LLM；budget_early_stop / 伞形两类
  显式 None——诚实口径不为全覆盖硬凑）；
- 臂归属优先取 trace 内 task_start 事件的 meta.baseline（脱敏管道
  保留该字段），缺失时回退文件名约定（*_aitester_<ts>.trace.jsonl），
  均不可得归入 unknown 桶并如实报告；
- 损坏 / 空文件计入 damaged，不静默丢弃。

用法：
    python experiments/mast_trace_analysis.py \
        --traces-dir experiments/results/main_batch/traces \
        --output experiments/results/main_batch/mast_distribution_report.md

纯离线：零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.observability.agent_telemetry import (  # noqa: E402
    _flatten_record,
    match_failure_patterns,
)

# 文件名回退口径：meta.baseline 缺失时从文件名解析臂（与 run_benchmark
# 落盘命名约定一致：<dataset>__<task>_<arm>_<ts>.trace.jsonl）。
_ARM_FROM_FILENAME_RE = re.compile(r"_(?P<arm>aitester|plain_llm|plain_llm_df)_\d+\.trace\.jsonl$")


def _arm_from_filename(name: str) -> str | None:
    """从 trace 文件名回退解析臂（约定不匹配 → None）。"""
    m = _ARM_FROM_FILENAME_RE.search(name)
    return m.group("arm") if m else None


def parse_trace_file(path: Path) -> dict[str, Any] | None:
    """读取单个 trace JSONL 文件。

    Returns:
        {"arm": str | None, "task_id": str | None, "records": [...]}；
        文件损坏 / 非法 JSON → None（调用方计入 damaged，不静默丢弃）。
    """
    records: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if isinstance(rec, dict):
                    records.append(rec)
                    if rec.get("event") == "task_start" and isinstance(rec.get("meta"), dict):
                        meta = rec["meta"]
    except (OSError, json.JSONDecodeError):
        return None
    arm = str(meta.get("baseline") or "").strip() or None
    task_id = str(meta.get("dataset_task_id") or "").strip() or None
    return {"arm": arm, "task_id": task_id, "records": records}


def analyze_traces(traces_dir: Path) -> dict[str, Any]:
    """遍历 trace 目录，按臂聚合失效模式命中面。

    Returns:
        {
          "total_files": int, "damaged_files": int,
          "arms": {臂名: {"files": int, "damaged": int,
                          "pattern_files": {模式名: 命中文件数}}},
          "patterns_meta": {模式名: {"mast_class": ..., "mast_category": ...}},
        }
    """
    files = sorted(traces_dir.glob("*.trace.jsonl"))
    arms: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"files": 0, "damaged": 0, "pattern_files": defaultdict(int), "category_files": defaultdict(int)}
    )
    patterns_meta: dict[str, dict[str, Any]] = {}
    total = 0
    damaged_total = 0
    for path in files:
        total += 1
        parsed = parse_trace_file(path)
        if parsed is None:
            damaged_total += 1
            arms["unknown"]["damaged"] += 1
            continue
        arm = parsed["arm"] or _arm_from_filename(path.name) or "unknown"
        stats = arms[arm]
        if not parsed["records"]:
            # 空 trace（无事件）——计入该臂文件数但无模式命中面
            stats["files"] += 1
            continue
        stats["files"] += 1
        report = match_failure_patterns(parsed["records"])
        for name, info in report["patterns"].items():
            patterns_meta[name] = {"mast_class": info.get("mast_class"), "mast_category": info.get("mast_category")}
            if info["count"] > 0:
                stats["pattern_files"][name] += 1
        # error_category 原始值分布（按文件计——每文件每类别至多计 1，
        # 与"命中文件数"观测单元一致；展平口径与模式判定相同）
        categories_in_file: set[str] = set()
        for rec in parsed["records"]:
            if not isinstance(rec, dict):
                continue
            cat = _flatten_record(rec).get("error_category")
            if cat:
                categories_in_file.add(str(cat).strip().lower())
        for cat in categories_in_file:
            stats["category_files"][cat] += 1
    return {
        "total_files": total,
        "damaged_files": damaged_total,
        "arms": dict(arms),
        "patterns_meta": patterns_meta,
    }


def render_markdown(result: dict[str, Any], traces_dir: Path) -> list[str]:
    """渲染 Markdown 分布报告（按臂分节，模式按命中数降序）。"""
    lines = [
        "# MAST 失效模式分布报告（trace 离线聚合——AG1）",
        "",
        f"- 数据源：`{traces_dir}`（{result['total_files']} 个 trace 文件，"
        f"损坏 {result['damaged_files']} 个——损坏计入各臂 damaged，不静默丢弃）",
        "- 判定口径：src/observability/agent_telemetry.match_failure_patterns"
        "（Y2 MAST 14 类映射；budget_early_stop / 伞形两类无对应类显式 None）",
        "- 观测单元 = 单 trace 文件（单任务×单臂×单次运行）；命中率 = 命中文件数 / 该臂有效文件数",
        "- 纯离线静态匹配：零 LLM / 零网络；本报告为衍生工件，可用本脚本从入库 trace 逐位复算",
        "",
        "**解读警示（诚实口径）**：模式与 error_category 值来自 trace 中"
        "debugger 节点事件的落盘字段——plain_llm / plain_llm_df 臂无 "
        'debugger 节点，trace 天然不含该字段，其"零命中"反映 **trace '
        "schema 差异而非零失败**（plain_llm_df 的 44.8% 任务未检出是既有"
        "结论）；跨臂对比仅在 aitester 与历史含 debugger 节点的批次内有效。",
        "",
    ]
    for arm in sorted(result["arms"]):
        stats = result["arms"][arm]
        n_files = stats["files"]
        lines += [f"## 臂：{arm}", "", f"有效文件数：{n_files}（损坏 {stats['damaged']}）", ""]
        if n_files == 0:
            lines += ["（无有效 trace——无分布可报）", ""]
            continue
        pattern_files: dict[str, int] = stats["pattern_files"]
        ranked = sorted(pattern_files.items(), key=lambda kv: (-kv[1], kv[0]))
        if not ranked:
            lines += ["（零模式命中）", ""]
            continue
        lines += [
            "| 失效模式 | MAST 类 | MAST 大类 | 命中文件数 | 命中率 |",
            "|----------|---------|-----------|------------|--------|",
        ]
        for name, count in ranked:
            meta = result["patterns_meta"].get(name, {})
            mast_class = meta.get("mast_class") or "—"
            mast_cat = meta.get("mast_category") or "—"
            lines.append(f"| {name} | {mast_class} | {mast_cat} | {count} | {count / n_files * 100:.1f}% |")
        lines.append("")
        # error_category 原始值分布（按文件计）——模式库之外的细粒度素材
        category_files: dict[str, int] = stats["category_files"]
        if category_files:
            lines += [
                "### error_category 原始值分布（按文件计，每文件每类别至多计 1）",
                "",
                "| error_category | 文件数 | 占比 |",
                "|----------------|--------|------|",
            ]
            for cat, count in sorted(category_files.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"| {cat} | {count} | {count / n_files * 100:.1f}% |")
            lines.append("")
        lines.append("")
    lines += [
        "---",
        "*报告生成：experiments/mast_trace_analysis.py（AG1，2026-10-06）*",
    ]
    return lines


def main() -> None:
    """CLI 入口（--traces-dir / --output；缺省打印控制台不落盘）。"""
    parser = argparse.ArgumentParser(description="MAST 失效模式分布分析（trace 离线聚合，零 LLM）")
    parser.add_argument(
        "--traces-dir",
        default="experiments/results/main_batch/traces",
        help="trace JSONL 目录（默认 experiments/results/main_batch/traces）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Markdown 报告落盘路径（缺省仅打印控制台）",
    )
    args = parser.parse_args()

    traces_dir = Path(args.traces_dir)
    if not traces_dir.is_dir():
        print(f"错误：trace 目录不存在：{traces_dir}")
        sys.exit(1)
    result = analyze_traces(traces_dir)
    lines = render_markdown(result, traces_dir)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"报告已保存至: {out_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
