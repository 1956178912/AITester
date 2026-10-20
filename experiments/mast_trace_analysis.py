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
- 损坏文件计入**所属臂**的 damaged（归臂口径同完好文件），并在报告里披露
  "坏行前已解析却被作废的记录数"；空文件（能读、无事件）计入该臂文件数而
  不是 damaged——两者口径不同，不得混写。
- 可解析但不是对象的行（AB-12c）既不是坏行、也不参与判定，必须逐行计数并按类型
  留痕；**整份都是非对象行**的文件不计入有效文件数，也不与"能读、无事件"的空文件
  混同——后者才是真的零事件。披露行只在非对象行真的出现时才写进报告，
  因此 0 实例时入库报告逐字节不变（由锁执行，不靠措辞承诺）。

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


def parse_trace_file(path: Path) -> dict[str, Any]:
    """读取单个 trace JSONL 文件（读到坏行也返回结构，坏点留痕）。

    Returns:
        {
          "arm": str | None, "task_id": str | None, "records": [...],
          "damaged": bool，                    # True = 打不开 / 读到坏行
          "damage": str | None,                # 机制名（异常类型）；未损坏为 None
          "records_before_damage": int,        # 坏行之前已解析出的记录数
          "non_object_records": int,           # 可解析但不是对象的行数（AB-12c）
          "non_object_shapes": {类型名: 行数},  # 机制留痕：整份是数组还是逐行是字符串
          "non_object_only": bool,             # 无对象记录却有非对象行（≠ 零事件）
        }

    损坏文件的 ``records`` 仍不参与模式判定（判定分母口径不变），但"坏行前已
    解析出 N 条"必须留痕并上报——**整份作废是一个读数，静默作废才是缺陷**。

    非对象行（AB-12c）与坏行是两类通道：坏行走 ``damage``（语法层面读不出来），
    非对象行是"读得出来但形状不合"。二者都不得无痕消失——尤其"整份都是非对象行"
    必须与"文件真的没有任何事件"分开，否则形状不合会被读成零命中。
    """
    records: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    damage: str | None = None
    non_object_records = 0
    non_object_shapes: dict[str, int] = {}
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
                else:
                    shape = type(rec).__name__
                    non_object_records += 1
                    non_object_shapes[shape] = non_object_shapes.get(shape, 0) + 1
    except (OSError, json.JSONDecodeError) as e:
        damage = type(e).__name__
    arm = str(meta.get("baseline") or "").strip() or None
    task_id = str(meta.get("dataset_task_id") or "").strip() or None
    return {
        "arm": arm,
        "task_id": task_id,
        "records": records,
        "damaged": damage is not None,
        "damage": damage,
        "records_before_damage": len(records) if damage is not None else 0,
        "non_object_records": non_object_records,
        "non_object_shapes": non_object_shapes,
        "non_object_only": damage is None and not records and non_object_records > 0,
    }


def analyze_traces(traces_dir: Path) -> dict[str, Any]:
    """遍历 trace 目录，按臂聚合失效模式命中面。

    Returns:
        {
          "total_files": int, "damaged_files": int,
          "damaged_files_with_records": int, "damaged_records_before_damage": int,
          "non_object_only_files": int, "files_with_non_object_lines": int,
          "non_object_lines": int, "non_object_shapes": {类型名: 行数},
          "non_object_files": [文件名],
          "arms": {臂名: {"files": int, "damaged": int, "non_object_only": int,
                          "pattern_files": {模式名: 命中文件数}}},
          "patterns_meta": {模式名: {"mast_class": ..., "mast_category": ...}},
        }
    """
    files = sorted(traces_dir.glob("*.trace.jsonl"))
    arms: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "files": 0,
            "damaged": 0,
            "non_object_only": 0,
            "pattern_files": defaultdict(int),
            "category_files": defaultdict(int),
        }
    )
    patterns_meta: dict[str, dict[str, Any]] = {}
    total = 0
    damaged_total = 0
    damaged_with_records = 0
    damaged_records = 0
    non_object_only_total = 0
    files_with_non_object_lines = 0
    non_object_lines = 0
    non_object_shapes: dict[str, int] = {}
    non_object_files: list[str] = []
    for path in files:
        total += 1
        parsed = parse_trace_file(path)
        # 归臂口径与完好文件一致（meta.baseline → 文件名 → unknown）：损坏文件
        # 不得整体落到 unknown 桶，否则报告说"计入各臂 damaged"而代码在做另一件事。
        arm = parsed["arm"] or _arm_from_filename(path.name) or "unknown"
        stats = arms[arm]
        if parsed["non_object_records"]:
            non_object_lines += parsed["non_object_records"]
            for shape, n in parsed["non_object_shapes"].items():
                non_object_shapes[shape] = non_object_shapes.get(shape, 0) + n
            non_object_files.append(path.name)
        if parsed["damaged"]:
            damaged_total += 1
            stats["damaged"] += 1
            if parsed["records_before_damage"]:
                damaged_with_records += 1
                damaged_records += parsed["records_before_damage"]
            continue
        if parsed["non_object_only"]:
            # 一行对象记录都没有：这是"形状不合的读数"，不是"零事件的有效 trace"，
            # 计入该臂文件数会把分母撑大、把命中率压低（AB-12c）。
            non_object_only_total += 1
            stats["non_object_only"] += 1
            continue
        stats["files"] += 1
        if parsed["non_object_records"]:
            files_with_non_object_lines += 1
        if not parsed["records"]:
            # 空 trace（无事件）——计入该臂文件数但无模式命中面
            continue
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
        "damaged_files_with_records": damaged_with_records,
        "damaged_records_before_damage": damaged_records,
        "non_object_only_files": non_object_only_total,
        "files_with_non_object_lines": files_with_non_object_lines,
        "non_object_lines": non_object_lines,
        "non_object_shapes": non_object_shapes,
        "non_object_files": non_object_files,
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
    ]
    if result["damaged_files"]:
        lines.append(
            f"- 损坏留痕：{result['damaged_files_with_records']} 个损坏文件在坏行之前已解析出 "
            f"{result['damaged_records_before_damage']} 条记录；这些记录不参与模式判定"
            "（该文件整体按损坏计），此处只披露被作废的量，归臂口径与完好文件一致"
        )
    if result["non_object_only_files"] or result["non_object_lines"]:
        shapes = "、".join(f"{k} {v} 行" for k, v in sorted(result["non_object_shapes"].items()))
        lines.append(
            f"- 非对象行留痕：{result['non_object_lines']} 行可解析但不是对象（{shapes}），"
            f"分布在 {len(result['non_object_files'])} 个文件——非对象行不是坏行（坏行走损坏通道），"
            f"但也不能当成一次有效读数；其中 {result['non_object_only_files']} 个文件一行对象记录都没有，"
            f"**不计入下面的有效文件数**（另有 {result['files_with_non_object_lines']} 个有效文件混有非对象行，"
            "其对象记录仍参与判定，被丢弃的行数已在上面的总数里）"
        )
    lines += [
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
        n_shape = stats["non_object_only"]
        head = f"有效文件数：{n_files}（损坏 {stats['damaged']}）"
        if n_shape:
            head = f"有效文件数：{n_files}（损坏 {stats['damaged']}、非对象行独占 {n_shape} 份不计入分母）"
        lines += [f"## 臂：{arm}", "", head, ""]
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
