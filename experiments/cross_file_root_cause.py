"""P3 跨文件修复根因分析脚本（2026-10 改进，A/B 正向但幅度有限）。

背景：
    跨文件 A/B（CROSS_FILE_ENABLE=true vs false，level3 双模块）显示
    level3 成功率 88% → 98%（+10pp），未达 T1 验收阈值 +15pp。
    本脚本提取 level3 ON 组"未修复的 2%"任务，按失败根因分类，
    定位 cross_file.py 的依赖分析粒度 / 拓扑排序 / 回滚机制哪一环
    是瓶颈，为下一步优化提供数据依据。

分析维度（纯数据，零 LLM 成本）：
    1. 失败任务列表：level3 ON 组 passed=False 的 task_id；
    2. 错误分类：从 result["error_category"] / final_state 提取
       （LLM_BREAKS_IMPORT / EMPTY_LLM_PATCH / 依赖图不完整 / 拓扑排序错误）；
    3. 依赖图完整性：cross_file_deps 边数 vs 任务 num_files（缺边 = 依赖图不完整）；
    4. 回滚保守度：patch_applier 是否因"任一文件失败则整体回滚"而放弃有效补丁；
    5. 拓扑序正确性：per_module_patches 的应用顺序是否符合"被调用方先改"。

使用方式：
    # 分析已有 level3 A/B 结果（ON 组 JSON + 原始 state 目录）
    python experiments/cross_file_root_cause.py \
        --results-on experiments/results/cross_file_ab/cross_file_on/benchmark_*.json \
        --raw-dir experiments/results/cross_file_ab/cross_file_on/raw \
        --difficulty level3

    # 仅读 ON 组结果 JSON（无 raw state 时降级为"仅错误分类"口径）
    python experiments/cross_file_root_cause.py \
        --results-on <path.json> --difficulty level3
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


def _load_results(path: str) -> list[dict[str, Any]]:
    """读 benchmark_*.json 的 details 列表（兼容三种形态）。

    1. 旧形态：顶层直接是 details list；
    2. 顶层 dict 含 "details" 键（rag_ab 聚合报告）；
    3. 2026-10 改进：嵌套结构 {"results": {"aitester": {"details": [...]}}}
       （run_benchmark 标准输出，cross_file_ab.py 产物的实际形态）——
       历史 _load_results 只认形态 1/2，cross_file_ab 的 OFF/ON 组
       benchmark JSON 全部走"旧形态无 details"分支返回空，导致
       total_failed 恒 0（根因分析对真实失败任务全盲）。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "details" in data:
            return data["details"]
        # 嵌套形态：results.<baseline>.details（取 aiterster 基线）
        results = data.get("results") or {}
        for bl_name, bl_data in results.items():
            if isinstance(bl_data, dict) and "details" in bl_data:
                return bl_data["details"] or []
        # 兼容 results 直接是 list 的旧口径
        if isinstance(results, list):
            return results
    return []


def _classify_root_cause(result: dict[str, Any], state: dict[str, Any] | None) -> str:
    """单任务失败根因分类（保守、零 LLM 成本，纯数据规则）。

    优先级（首个命中即返回）：
    1. LLM_BREAKS_IMPORT：patch 应用后 import 被破坏（error_category /
       补丁文本含 "import " 删除 / 缺失符号）；
    2. EMPTY_LLM_PATCH：LLM 输出空补丁 / 无法解析（error_category 命中）；
    3. DEP_GRAPH_INCOMPLETE：cross_file_deps 边数 < num_files - 1（依赖图不完整）；
    4. ROLLBACK_CONSERVATIVE：多文件补丁中仅 1 文件失败导致整体回滚；
    5. TOPOLOGICAL_ORDER：拓扑序违规（调用方先改、被调用方后改）；
    6. LLM_CAPABILITY：以上皆非命中（LLM 引擎能力边界，需 GPT-4 级模型）。
    """
    err_cat = str(result.get("error_category") or "").upper()
    patch = result.get("patch") or ""
    num_files = int((result.get("task_metadata") or {}).get("num_files", 1))
    deps = (state or {}).get("cross_file_deps") or []

    # 1. LLM_BREAKS_IMPORT：补丁删除/破坏 import 语句
    if "LLM_BREAKS_IMPORT" in err_cat or "IMPORT" in err_cat:
        return "LLM_BREAKS_IMPORT"
    # 2. EMPTY_LLM_PATCH：LLM 输出空
    if "EMPTY" in err_cat or len(patch.strip()) < 20:
        return "EMPTY_LLM_PATCH"
    # 3. 依赖图不完整：边数 < 文件数 - 1
    if num_files > 1 and len(deps) < num_files - 1:
        return "DEP_GRAPH_INCOMPLETE"
    # 4. 回滚保守度：多文件补丁且 per_module_patches 非全应用
    per_module = (state or {}).get("per_module_patches") or {}
    applied = (state or {}).get("applied_modules") or []
    if num_files > 1 and per_module and len(applied) < len(per_module):
        return "ROLLBACK_CONSERVATIVE"
    # 5. 拓扑序违规：调用方模块先于被调用方应用
    if applied and deps:
        call_targets = {d.get("source_module") for d in deps}
        target_sources = {d.get("target_module") for d in deps}
        for i in range(len(applied)):
            for j in range(i + 1, len(applied)):
                # 若 applied[i] 是调用方（source）且 applied[j] 是被调用方（target），
                # 且 target 依赖 source 的符号 → 拓扑序违规
                if applied[i] in call_targets and applied[j] in target_sources:
                    # 进一步检查是否真的有依赖边 source->target
                    has_edge = any(
                        d.get("source_module") == applied[i] and d.get("target_module") == applied[j]
                        for d in deps
                    )
                    if has_edge:
                        return "TOPOLOGICAL_ORDER"
    # 6. 兜底：LLM 引擎能力边界
    return "LLM_CAPABILITY"


def analyze(results: list[dict[str, Any]], raw_dir: str | None, difficulty: str = "level3") -> dict[str, Any]:
    """汇总 level3 ON 组失败任务的根因分布。

    Args:
        results: benchmark 结果 details 列表。
        raw_dir: 原始 state 落盘目录（raw/<task_id>/aitester.json），可为 None。
        difficulty: 难度级别（用于日志标注与过滤）。

    Returns:
        根因分布 dict（{root_cause: count} + 失败任务列表 + 详情）。
    """
    failed = [r for r in results if not r.get("passed")]
    # 按 difficulty 过滤（task_metadata.difficulty）
    # 2026-10 改进：task_metadata.difficulty 在 L3.5 存的是数字 35（非字符串
    # "level3.5"），历史过滤 str(...) == difficulty 永远不命中导致失败任务
    # 全被过滤掉。现改为：先按原始值精确匹配（兼容数字/字符串），再按
    # "level3.5"↔35 / "level3"↔3 的数字码等价匹配。
    if difficulty:
        _difficulty_to_code = {"level1": 1, "level2": 2, "level2.5": 25, "level3": 3, "level3.5": 35, "level4": 4, "level4.5": 45}
        want_code = _difficulty_to_code.get(difficulty)

        def _match(r: dict[str, Any]) -> bool:
            d = (r.get("task_metadata") or {}).get("difficulty", "")
            # 原始值精确匹配（数字 35 / 字符串 "35" / "level3.5" 直接相等）
            if str(d) == difficulty or str(d) == str(want_code):
                return True
            # 数字码等价：level3.5 ↔ 35，level3 ↔ 3
            if want_code is not None and d == want_code:
                return True
            # 字符串 difficulty ↔ 数字码双向
            if difficulty in _difficulty_to_code and d == _difficulty_to_code[difficulty]:
                return True
            return False

        failed = [r for r in failed if _match(r)]
    dist: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    for r in failed:
        state = None
        if raw_dir:
            raw_file = os.path.join(raw_dir, r.get("task_id", ""), "aitester.json")
            if os.path.exists(raw_file):
                try:
                    with open(raw_file, encoding="utf-8") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    state = None
        cause = _classify_root_cause(r, state)
        dist[cause] += 1
        details.append(
            {
                "task_id": r.get("task_id"),
                "root_cause": cause,
                "error_category": r.get("error_category"),
                "iterations": r.get("iterations"),
                "num_files": int((r.get("task_metadata") or {}).get("num_files", 1)),
                "dep_edges": len((state or {}).get("cross_file_deps") or []),
                "patch_len": len(r.get("patch") or ""),
            }
        )
    return {
        "difficulty": difficulty,
        "total_failed": len(failed),
        "root_cause_distribution": dict(dist.most_common()),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="跨文件修复根因分析（P3）")
    parser.add_argument("--results-on", required=True, help="level3 ON 组 benchmark_*.json 路径（或 glob）")
    parser.add_argument("--raw-dir", default=None, help="原始 state 落盘目录 raw/（可选）")
    parser.add_argument("--difficulty", default="level3", help="难度级别（默认 level3）")
    parser.add_argument("--output", default=None, help="输出 JSON 路径（默认 stdout）")
    args = parser.parse_args()

    results = _load_results(args.results_on)
    if not results:
        logger.warning("未找到结果 details（路径=%s），降级为空分析", args.results_on)

    report = analyze(results, args.raw_dir, difficulty=args.difficulty)

    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"根因分析已写入: {args.output}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
