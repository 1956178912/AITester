"""
G8 前置校验：检查 SWE-bench Pro 数据集是否可用于全开链路复测。

背景（gap_report 2026-09-28 P0 缺口 G8）：
    全开链路复测（RUNTIME_PROBE_ENABLE + STRATEGY_BANK_ENABLE +
    EXPERT_POOL_ENABLE + CROSS_FILE_ENABLE）的前置阻塞是
    docs/design/swe_bench_probe.md 记录的"数据集无可用源码"问题——
    官方 SWE-bench JSONL 无 instance_code 字段，需经
    SWE_BENCH_ENRICHMENT 补全后才可产生有效修复对比。本脚本把该校验
    做成独立入口，供实验流程在执行前确认数据就绪。

检查项（逐项报告，全部通过时退出码 0，否则 1）：
    1. 数据目录存在且非空（AITESTER_SWE_BENCH_PRO_DIR 或
       SWE_BENCH_DATA_DIR，SWE-bench Pro 数据文件命名约定与
       SWE-bench 同构：swe_bench_*_instances.jsonl / swe_bench_pro*.jsonl）；
    2. 至少一条任务可解析为 JSON **对象**（合法 JSON 但不是对象的行按任务级问题计入
       non_object_*，与解析失败同口径保持 fail-closed）；
    3. 任务级就绪度：
       - 有官方源码字段（instance_code / base_code）或配置了
         SWE_BENCH_ENRICHMENT 补充文件；
       - test_patch / test_code 非空；
       - FAIL_TO_PASS 非空（SWE-bench 官方通过判定口径）；
       - base_commit 非空（RepoExecutor 仓库级验证所需）；
    4. 输出任务级缺失清单（JSON，供人工补全或 scripts/tools/export_swe_bench_source.py
       的 --instance-ids 批量导出筛选消费）；
    5. 补充文件健康度（enrichment_stats：exists / 计入条数 / 四类坏行计数）——
       "没配补充文件"、"配了但路径不存在"、"路径在但零行落到映射"三种状态必须
       在报表里可分辨，否则 G8 前置阻塞的归因会指错地方。

使用方式：
    python scripts/gates/check_swe_bench_pro_ready.py
    python scripts/gates/check_swe_bench_pro_ready.py --data-dir ~/.cache/aitester/swe_bench_pro
    python scripts/gates/check_swe_bench_pro_ready.py --enrichment /path/to/enrichment.jsonl --json

说明：本脚本只读，不修改任何数据；退出码 1 表示"数据未就绪"，
调用方（CI / 实验流程）应据此阻止全开链路复测执行，避免无信息量批次。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _parse_test_list(value: Any) -> list[str]:
    """解析 SWE-bench 测试节点列表字段（兼容 list 与 JSON 编码字符串）。"""
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _find_data_files(data_dir: str) -> list[str]:
    """查找数据目录下的 SWE-bench JSONL 文件（Pro / 通用命名约定）。"""
    if not os.path.isdir(data_dir):
        return []
    # 主口径：swe_bench_*_instances.jsonl 命名约定（含 Pro 子集）
    paths = [os.path.join(data_dir, name) for name in sorted(os.listdir(data_dir)) if name.endswith("_instances.jsonl")]
    # 兼容直接命名为 swe_bench_pro.jsonl / *.jsonl 的目录
    if not paths:
        paths = [os.path.join(data_dir, name) for name in sorted(os.listdir(data_dir)) if name.endswith(".jsonl")]
    return paths


def _load_enrichment_paths(enrichment: str | None) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """加载 enrichment JSONL（与 dataset_loader._load_enrichment 同口径）。

    Returns:
        (补充映射, 分类计数)。计数键固定为 exists / loaded / parse_error /
        non_object / missing_id / bad_key 六项，其中中间四项是"配了但没生效"的量级
        ——本门禁此前对四类坏行**整段静默吞掉**（无痕迹），报表里无法区分
        "没配补充文件"与"配了但一行都没认出来"；exists 再把"文件不存在"与
        "文件在但空/全废"分开，否则这三者的计数全是零、仍不可分辨。
    """
    enriched: dict[str, dict[str, Any]] = {}
    stats = {"exists": 0, "loaded": 0, "parse_error": 0, "non_object": 0, "missing_id": 0, "bad_key": 0}
    if not enrichment or not os.path.exists(enrichment):
        return enriched, stats
    stats["exists"] = 1
    with open(enrichment, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                stats["parse_error"] += 1
                continue
            if not isinstance(row, dict):
                stats["non_object"] += 1
                continue
            row_id = row.get("instance_id")
            if not row_id:
                stats["missing_id"] += 1
                continue
            if isinstance(row_id, (list, dict)):
                stats["bad_key"] += 1
                continue
            # 标量主键归一为 str，与产品侧 _load_enrichment / _build_task_from_swe_row
            # 同源：不归一时 int 键能写进映射却永不命中，list/dict 直接 TypeError。
            enriched[str(row_id)] = {k: v for k, v in row.items() if v not in (None, "")}
    # 按映射大小计，与产品侧同口径：重复 instance_id 后者胜出（两侧都不另设计
    # 合并策略），故"认出来的行数"就是 len(enriched)，不是通过守卫的行数。
    stats["loaded"] = len(enriched)
    return enriched, stats


def check_pro_ready(
    data_dir: str,
    enrichment: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """执行就绪检查，返回结构化报告。

    Args:
        data_dir: SWE-bench Pro 数据目录（含 JSONL 文件）。
        enrichment: 可选的 enrichment JSONL 路径（补 instance_code / test_code）。
        limit: 仅检查前 N 个任务（None = 全部）。

    Returns:
        报告 dict：
            data_dir / data_files / total_tasks / ready_tasks /
            task_issues（task_id → 问题列表）/ ready（bool）/
            missing_source（缺源码的 instance_id 清单）/
            enrichment_stats（补充文件分类计数，见 _load_enrichment_paths）
    """
    data_files = _find_data_files(data_dir)
    enriched, enrichment_stats = _load_enrichment_paths(enrichment)
    has_enrichment = bool(enriched)

    total_tasks = 0
    task_issues: dict[str, list[str]] = {}
    missing_source: list[str] = []

    for path in data_files:
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                if limit is not None and total_tasks >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    task_issues[f"unparsed_{os.path.basename(path)}_line{line_num}"] = ["JSON 解析失败（行无法解析）"]
                    total_tasks += 1
                    continue
                if not isinstance(data, dict):
                    # 对齐本函数自己的 unparsed_ 先例（计入 total_tasks 与问题清单）：
                    # 保持 fail-closed——非对象行是数据缺陷，不得因为"能解析"就判就绪。
                    # 此前 data.get 直接 AttributeError，门禁崩溃、只留 traceback 不留报告。
                    task_issues[f"non_object_{os.path.basename(path)}_line{line_num}"] = [
                        "该行不是 JSON 对象（合法 JSON，但不是任务记录）"
                    ]
                    total_tasks += 1
                    continue
                task_id = str(data.get("instance_id") or f"line_{line_num}")
                if task_id in ("unparsed",) or task_id.startswith("unparsed_"):
                    continue
                issues: list[str] = []
                merged = {**data, **enriched.get(task_id, {})}
                instance_code = merged.get("instance_code") or merged.get("base_code") or ""
                # 2026-10-01 全面审查 P1 修复：strip 后再比较——dataset_loader 兜底
                # 口径是 instance_code = problem_statement 的直接引用（可能带
                # BOM / 尾换行），全等比较会因首尾空白误判"已就绪"，放行无效批次。
                if not instance_code.strip() or instance_code.strip() == merged.get("problem_statement", "").strip():
                    issues.append("instance_code 缺失（需 SWE_BENCH_ENRICHMENT 或官方源码字段）")
                    missing_source.append(task_id)
                test_code = (
                    merged.get("test_code") or merged.get("test_patch") or merged.get("test_before_patches") or ""
                )
                if not str(test_code).strip():
                    issues.append("test_patch / test_code 为空")
                if not _parse_test_list(merged.get("FAIL_TO_PASS")):
                    issues.append("FAIL_TO_PASS 为空（无法做 SWE-bench 官方口径判定）")
                if not merged.get("base_commit"):
                    issues.append("base_commit 缺失（RepoExecutor 仓库级验证所需）")
                total_tasks += 1
                if issues:
                    task_issues[task_id] = issues

    ready = total_tasks > 0 and len(task_issues) == 0
    report: dict[str, Any] = {
        "data_dir": data_dir,
        "data_files": [os.path.basename(p) for p in data_files],
        "enrichment": enrichment or "",
        "enrichment_loaded": has_enrichment,
        "enrichment_stats": enrichment_stats,
        "total_tasks": total_tasks,
        "ready_tasks": total_tasks - len(task_issues),
        "task_issues": task_issues,
        "missing_source": missing_source,
        "ready": ready,
    }
    return report


# 坏行计数的展示顺序与中文标签：口径与 _load_enrichment_paths 的 stats 键一一对应。
# 旧文本把"文件不存在 / 空文件 / 全废"压成一句"未加载 / 不存在"，正是本轮补的静默面。
_DROP_KEYS: tuple[str, ...] = ("parse_error", "non_object", "missing_id", "bad_key")
_DROP_LABELS: dict[str, str] = {
    "parse_error": "解析失败",
    "non_object": "非 JSON 对象",
    "missing_id": "缺 instance_id",
    "bad_key": "主键是列表或字典",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 SWE-bench Pro 数据集是否可用于全开链路复测")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="SWE-bench Pro 数据目录（默认读 AITESTER_SWE_BENCH_PRO_DIR / SWE_BENCH_DATA_DIR / 默认缓存目录）",
    )
    parser.add_argument("--enrichment", default=None, help="可选 enrichment JSONL 路径（补 instance_code / test_code）")
    parser.add_argument("--limit", type=int, default=None, help="仅检查前 N 个任务")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整报告")
    args = parser.parse_args()

    data_dir = args.data_dir or os.getenv("AITESTER_SWE_BENCH_PRO_DIR") or os.getenv("SWE_BENCH_DATA_DIR")
    if not data_dir:
        data_dir = os.path.join(os.path.expanduser("~"), ".cache", "aitester", "swe_bench_pro")

    report = check_pro_ready(data_dir, enrichment=args.enrichment, limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"数据目录: {data_dir}")
        print(f"数据文件: {', '.join(report['data_files']) or '（未找到 JSONL）'}")
        if report.get("enrichment"):
            st = report["enrichment_stats"]
            dropped = "；".join(f"{_DROP_LABELS[k]} {st[k]}" for k in _DROP_KEYS if st[k])
            if not st["exists"]:
                detail = "文件不存在"
            elif st["loaded"]:
                detail = f"已加载 {st['loaded']} 条" + (f"（丢弃 {dropped}）" if dropped else "")
            else:
                detail = "零行落到映射" + (f"（丢弃 {dropped}）" if dropped else "（空文件）")
            print(f"Enrichment: {report['enrichment']}（{detail}）")
        print(f"任务总数: {report['total_tasks']}，就绪: {report['ready_tasks']}，有问题: {len(report['task_issues'])}")
        for task_id, issues in list(report["task_issues"].items())[:20]:
            print(f"  - {task_id}: {'; '.join(issues)}")
        if report["missing_source"]:
            print(
                f"缺失源码的 instance_id（{len(report['missing_source'])} 个，可用 scripts/tools/export_swe_bench_source.py 批量补）:"
            )
            for task_id in report["missing_source"][:20]:
                print(f"  - {task_id}")

    print()
    print(
        "结论: ✅ 数据就绪，可执行全开链路复测"
        if report["ready"]
        else "结论: ❌ 数据未就绪（先补齐上述缺失项再执行复测）"
    )
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
