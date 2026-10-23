"""分析集流量账的单一事实源（BY）。

背景：报告面的 `## 数据来源` 只列**纳入**的批次文件，而加载器在到达该清单
之前已经做了四层剔除，配对前又做了两层折叠：

1. 扫描面：只认 `benchmark_*.json`（归档里另有非 benchmark 命名的结果文件）；
2. 数据集白名单：`synthetic` / `quixbugs` 之外的文件整份丢弃；
3. schema 完备（默认）：`detection_rate` 全 None 的批次整份丢弃
   （`--allow-schema-mixed` 恢复）；
4. 基线白名单：未登记的臂整臂丢弃（`plain_llm_df_spec` 等）；
5. 行级去重：同一 `task_id` 只保留最新批次一行（`latest_rows_by_task`）；
6. 字段 None：去重后、配对前剔除该字段为 None 的任务（不是 0）。

这些层在归档上可复算，但报告面此前一层也不显示：读者看到「110 个批次 /
n=187」无法知道 10,659 行里哪 3,649 行被哪条规则挡在门外，也无法知道
7,010 行里 6,449 行被去重折叠。外部口径（PRISMA 2020 流程图：逐阶段数量
+ 排除理由，且流程图与正文数字必须一致；Hurlbert 1984 伪重复：n 只数独立
观测单元）要求把「整份剔除」与「行内折叠」分开报。

本模块只做记账：不改变 `_load_batch_file` 的任何判定，不回填归档行，
不把任何剔除层折成「通过」或「失败」。
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from experiments._row_pairing import latest_rows_by_task

BATCH_GLOB = "benchmark_*.json"
FLOW_FIELDS = ("passed", "detection_rate", "repair_rate")
LAYER_ORDER = (
    "included",
    "unsupported_dataset",
    "schema_incomplete",
    "read_error",
    "load_error",
)


def batch_is_m1_schema_complete(data: Mapping[str, Any]) -> bool:
    """批次是否携带 M1 诚实指标（任一基线任一行的 `detection_rate` 非 None）。

    与 `statistical_analysis._batch_is_m1_schema_complete` 同一判据；放在本
    模块是为了让「流量账」与「加载器」引用同一段逻辑而不是各写一份。
    """
    for baseline_data in data.get("results", {}).values():
        if not isinstance(baseline_data, dict):
            continue
        for row in baseline_data.get("details", []):
            if isinstance(row, dict) and row.get("detection_rate") is not None:
                return True
    return False


def classify_document(
    doc: Any,
    *,
    supported_datasets: Collection[str],
    tracked_baselines: Collection[str],
    allow_schema_mixed: bool,
) -> tuple[str, dict[str, str]]:
    """按 `_load_batch_file` 的判定顺序给一份已解析文档归层。

    判定顺序必须与加载器一致，否则流量账会和「实际纳入」清单对不上：
    先数据集白名单，再 schema 完备（仅默认口径），最后才触达 `results`
    并校验将被加载的基线块。任何在加载器里会让整份文件返回 False 的
    异常，这里都归为 `load_error`，不猜成 schema 或数据集原因。

    Returns:
        (层名, 附加信息)；层名 ∈ LAYER_ORDER。
    """
    if not isinstance(doc, dict):
        return "load_error", {"error": f"top-level {type(doc).__name__}"}
    dataset = doc.get("dataset", "")
    try:
        if dataset not in supported_datasets:
            name = dataset if isinstance(dataset, str) and dataset else "<缺失>"
            return "unsupported_dataset", {"dataset": name}
        if not allow_schema_mixed and not batch_is_m1_schema_complete(doc):
            return "schema_incomplete", {}
        results = doc.get("results", {})
        if not isinstance(results, dict):
            return "load_error", {"error": f"results {type(results).__name__}"}
        for baseline, block in results.items():
            if baseline not in tracked_baselines:
                continue
            if not isinstance(block, dict):
                return "load_error", {"error": f"{baseline} block {type(block).__name__}"}
            details = block.get("details", [])
            if not isinstance(details, list):
                return "load_error", {"error": f"{baseline}.details {type(details).__name__}"}
            for row in details:
                if not isinstance(row, dict):
                    return "load_error", {"error": f"{baseline}.details row {type(row).__name__}"}
        return "included", {}
    except Exception as exc:  # 与 _load_batch_file 的兜底一致：整份失败，不半加载
        return "load_error", {"error": f"{type(exc).__name__}: {exc}"}


def _row_counts(doc: Any) -> tuple[int, dict[str, int]]:
    """统计一份文档的结果行（仅 dict 行；与普查口径一致）。"""
    total = 0
    per_baseline: dict[str, int] = {}
    if not isinstance(doc, dict):
        return 0, per_baseline
    results = doc.get("results")
    if not isinstance(results, dict):
        return 0, per_baseline
    for baseline, block in results.items():
        if not isinstance(block, dict):
            continue
        details = block.get("details")
        if not isinstance(details, list):
            continue
        n = sum(1 for row in details if isinstance(row, dict))
        per_baseline[baseline] = n
        total += n
    return total, per_baseline


def flow_stats(
    results_dir: str | Path,
    *,
    supported_datasets: Collection[str],
    tracked_baselines: Collection[str],
    batch_files: Sequence[str] | None = None,
    allow_schema_mixed: bool = False,
) -> dict[str, Any]:
    """文件级流量账：扫描面 → 各剔除层 → 纳入清单与行数。

    白名单模式与加载器同口径：只认给定文件（重复路径只算一次），不存在或
    解析失败的文件记 `read_error`，不再回退到 glob。
    """
    root = Path(results_dir)
    if batch_files is None:
        paths = sorted(root.glob(f"**/{BATCH_GLOB}"))
        mode = "glob"
    else:
        paths = []
        seen: set[Path] = set()
        for batch_file in batch_files:
            path = root / batch_file
            if path not in seen:
                seen.add(path)
                paths.append(path)
        mode = "whitelist"

    status_files: Counter[str] = Counter()
    status_rows: Counter[str] = Counter()
    datasets: Counter[str] = Counter()
    untracked: Counter[str] = Counter()
    read_errors: list[dict[str, str]] = []
    included_rows_all = 0
    included_rows_tracked = 0
    scan_rows = 0
    schema_default_files = 0
    schema_default_rows = 0

    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            status_files["read_error"] += 1
            read_errors.append({"file": path.name, "error": type(exc).__name__})
            continue
        rows_all, per_baseline = _row_counts(doc)
        scan_rows += rows_all
        status, info = classify_document(
            doc,
            supported_datasets=supported_datasets,
            tracked_baselines=tracked_baselines,
            allow_schema_mixed=allow_schema_mixed,
        )
        status_files[status] += 1
        status_rows[status] += rows_all
        if status == "unsupported_dataset":
            datasets[info["dataset"]] += 1
        elif status == "included":
            included_rows_all += rows_all
            for baseline, n_rows in per_baseline.items():
                if baseline in tracked_baselines:
                    included_rows_tracked += n_rows
                else:
                    untracked[baseline] += n_rows
            # 混批口径下仍记一笔"默认口径会剔除多少"，避免报告里 schema 行
            # 显示 −0 被读成"没有 schema 不完备批次"。
            if allow_schema_mixed and not batch_is_m1_schema_complete(doc):
                schema_default_files += 1
                schema_default_rows += rows_all

    return {
        "mode": mode,
        "allow_schema_mixed": allow_schema_mixed,
        "scan": {"files": len(paths), "rows": scan_rows},
        "status": {
            layer: {"files": status_files.get(layer, 0), "rows": status_rows.get(layer, 0)} for layer in LAYER_ORDER
        },
        "schema_incomplete_if_default": {"files": schema_default_files, "rows": schema_default_rows},
        "datasets": dict(datasets),
        "untracked_baselines": dict(untracked),
        "included": {
            "files": status_files.get("included", 0),
            "rows_all": included_rows_all,
            "rows_tracked": included_rows_tracked,
        },
        "read_errors": read_errors,
        "whitelist": [str(path) for path in paths] if mode == "whitelist" else None,
    }


def loaded_flow(
    results: Mapping[str, Sequence[dict[str, Any]]],
    fields: Sequence[str] = FLOW_FIELDS,
) -> dict[str, Any]:
    """行级流量账：载入行 → 去重折叠 → 唯一 task 行 → 字段 None。

    去重与配对同一原语（`latest_rows_by_task`，最新批次优先）。这里不调用
    `_pair_by_task`，因为后者按字段过滤 None；流量账要把「去重」与「None」
    分成两步，才能回答「折叠了多少行」与「哪个字段丢了多少任务」。
    """
    rows_total = 0
    duplicates = 0
    unique = 0
    no_task_id = 0
    per_baseline: dict[str, dict[str, Any]] = {}
    fields_total = {field: {"none": 0, "measurable": 0} for field in fields}

    for baseline, rows in results.items():
        latest = latest_rows_by_task(rows)
        n_rows = len(rows)
        n_duplicates = sum(1 for row in rows if row.get("task_id")) - len(latest)
        n_no_task_id = sum(1 for row in rows if not row.get("task_id"))
        rows_total += n_rows
        duplicates += n_duplicates
        unique += len(latest)
        no_task_id += n_no_task_id
        per_field: dict[str, dict[str, int]] = {}
        for field in fields:
            n_none = sum(1 for row in latest.values() if row.get(field) is None)
            per_field[field] = {"none": n_none, "measurable": len(latest) - n_none}
            fields_total[field]["none"] += n_none
            fields_total[field]["measurable"] += len(latest) - n_none
        per_baseline[baseline] = {
            "rows": n_rows,
            "unique": len(latest),
            "duplicates": n_duplicates,
            "no_task_id": n_no_task_id,
            "fields": per_field,
        }

    return {
        "rows": rows_total,
        "duplicates": duplicates,
        "unique": unique,
        "no_task_id": no_task_id,
        "per_baseline": per_baseline,
        "fields": fields_total,
    }


def archive_universe(results_dir: str | Path) -> dict[str, Any]:
    """全归档带 `results` 字典的 JSON 盘点（与普查口径一致）。

    加载器的扫描面只认 `benchmark_*.json`；本函数回答「同一归档里还有多少
    结果文件连扫描面都没进」。只读、不做任何加载或判定。
    """
    root = Path(results_dir)
    files = 0
    rows = 0
    non_benchmark_files = 0
    non_benchmark_rows = 0
    for path in sorted(root.rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 — 解析不了的 JSON 不是盘点对象
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
            continue
        n_rows, _ = _row_counts(doc)
        files += 1
        rows += n_rows
        if not path.name.startswith("benchmark_"):
            non_benchmark_files += 1
            non_benchmark_rows += n_rows
    return {
        "files": files,
        "rows": rows,
        "non_benchmark_files": non_benchmark_files,
        "non_benchmark_rows": non_benchmark_rows,
    }


def _fmt(n: int) -> str:
    return f"{n:,}"


def _breakdown(counter: Mapping[str, int], *, limit: int = 6) -> str:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = items[:limit]
    text = " / ".join(f"{name or '<缺失>'} {_fmt(n)}" for name, n in shown)
    if len(items) > limit:
        text += f" / 其余 {len(items) - limit} 项"
    return text


def flow_console_line(flow: Mapping[str, Any]) -> str:
    """批次/报告控制台的一行摘要（不落盘）。"""
    loaded = flow["loaded"]
    status = flow["status"]
    unsupported = status["unsupported_dataset"]["rows"]
    schema = status["schema_incomplete"]["rows"]
    failed = status["read_error"]["rows"] + status["load_error"]["rows"]
    untracked = sum(flow["untracked_baselines"].values())
    field_text = " / ".join(f"{field} None {_fmt(value['none'])}" for field, value in loaded["fields"].items())
    return (
        f"分析集流量（BY）：扫描 {_fmt(flow['scan']['files'])} 份 / {_fmt(flow['scan']['rows'])} 行"
        f" → 剔除 数据集外 {_fmt(unsupported)} 行、schema {_fmt(schema)} 行、"
        f"读取/加载失败 {_fmt(failed)} 行、未登记基线 {_fmt(untracked)} 行"
        f" → 载入 {_fmt(flow['included']['files'])} 份 / {_fmt(loaded['rows'])} 行"
        f" → 折叠重复 {_fmt(loaded['duplicates'])} 行 → 唯一 {_fmt(loaded['unique'])} 行"
        f"（{field_text}）"
    )


def render_analysis_flow_lines(flow: Mapping[str, Any]) -> list[str]:
    """把流量账渲染成 `## 数据来源` 内的 Markdown 子章节。"""
    scan = flow["scan"]
    included = flow["included"]
    loaded = flow["loaded"]
    status = flow["status"]
    unsupported = status["unsupported_dataset"]
    schema = status["schema_incomplete"]
    read_error = status["read_error"]
    load_error = status["load_error"]
    failed_files = read_error["files"] + load_error["files"]
    failed_rows = read_error["rows"] + load_error["rows"]
    untracked = flow["untracked_baselines"]
    untracked_rows = sum(untracked.values())
    archive = flow.get("archive")
    reconciles = flow.get("reconciles")

    lines = [
        "",
        "### 分析集流量（BY：逐层剔除与去重）",
        "",
        "| 层 | 文件 | 行 | 说明 |",
        "|---|---:|---:|---|",
        f"| 扫描（{'glob `benchmark_*.json`' if flow['mode'] == 'glob' else '白名单'}） "
        f"| {_fmt(scan['files'])} | {_fmt(scan['rows'])} | 加载器唯一扫描面 |",
        f"| 数据集白名单外 | −{_fmt(unsupported['files'])} | −{_fmt(unsupported['rows'])} "
        f"| {_breakdown(flow['datasets']) or '无'} |",
        f"| schema 不完备（默认剔除） | −{_fmt(schema['files'])} | −{_fmt(schema['rows'])} "
        f"| `detection_rate` 全 None；`--allow-schema-mixed` 恢复 |",
    ]
    if failed_files:
        lines.append(
            f"| 读取/加载失败 | −{_fmt(failed_files)} | −{_fmt(failed_rows)} "
            f"| 解析失败或结果块形状不合法（整份不加载） |"
        )
    lines += [
        f"| 基线未登记 | 0 | −{_fmt(untracked_rows)} | {_breakdown(untracked) or '无'} |",
        f"| **载入** | **{_fmt(included['files'])}** | **{_fmt(loaded['rows'])}** "
        f"| 实际进入统计（`## 数据来源` 清单） |",
        f"| 重复 task_id 折叠 | — | −{_fmt(loaded['duplicates'])} | 最新批次优先；此前只有 DEBUG 日志 |",
        f"| **唯一 task 行** | — | **{_fmt(loaded['unique'])}** | 配对单元（含缺 task_id 剔除） |",
    ]
    for field, value in loaded["fields"].items():
        lines.append(
            f"| `{field}`：None / 可测 | — | {_fmt(value['none'])} / {_fmt(value['measurable'])} "
            f"| None 在去重后、配对前剔除；**None ≠ 0** |"
        )

    left = scan["rows"] - unsupported["rows"] - schema["rows"] - failed_rows - untracked_rows
    lines += [
        "",
        f"> 对账：扫描 {_fmt(scan['rows'])} − 数据集外 {_fmt(unsupported['rows'])} − schema "
        f"{_fmt(schema['rows'])} − 读取/加载失败 {_fmt(failed_rows)} − 未登记基线 "
        f"{_fmt(untracked_rows)} = **{_fmt(left)}**（载入 {_fmt(loaded['rows'])}）；"
        f"载入 − 重复 {_fmt(loaded['duplicates'])} − 缺 task_id {_fmt(loaded['no_task_id'])} "
        f"= **{_fmt(loaded['unique'])}**（唯一行）。"
        + ("两项均闭合。" if reconciles else "**对账未闭合，见下方差异。**"),
    ]
    if flow["mode"] == "glob" and archive is not None:
        lines.append(
            f"> 扫描面之外：全归档带 `results` 的 JSON **{_fmt(archive['files'])} 份 / "
            f"{_fmt(archive['rows'])} 行**；其中非 `benchmark_*` 命名 **"
            f"{_fmt(archive['non_benchmark_files'])} 份 / {_fmt(archive['non_benchmark_rows'])} 行**"
            f"不在本表的扫描面（本表首行为 {_fmt(scan['files'])} 份 / {_fmt(scan['rows'])} 行）。"
        )
    if flow.get("allow_schema_mixed"):
        default = flow["schema_incomplete_if_default"]
        lines.append(
            f"> 本报告以 `--allow-schema-mixed` 口径运行：schema 层**不剔除**——"
            f"默认口径会剔除的 **{_fmt(default['files'])} 份 / {_fmt(default['rows'])} 行**"
            "已并入上表；两个口径的读数不可混用。"
        )
    elif schema["files"]:
        lines.append(
            f"> 混批口径（`--allow-schema-mixed`）会把 schema 层 **{_fmt(schema['files'])} 份 / "
            f"{_fmt(schema['rows'])} 行**并入：载入行 **{_fmt(loaded['rows'])} + "
            f"{_fmt(schema['rows'])} = {_fmt(loaded['rows'] + schema['rows'])}**；"
            "两个口径不混用，混批口径的去重与字段读数须重跑后另报。"
        )
    lines += [
        "> 外部口径（联网核对）：PRISMA 2020 流程图要求逐阶段记录数量与排除理由，且流程图数字"
        "必须与正文/结果表逐一对账；Hurlbert（1984）的伪重复定义要求 n 只数独立观测单元——"
        "重复 task_id 折叠本身是对的，但折叠量必须披露，否则读者无法判断唯一行数是不是独立"
        "单元数。",
        "> 本表只记账：不改任何判定值、不改 passed / repair / 分母，也不回填归档行。",
    ]
    return lines
