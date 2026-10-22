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

证据分级（BO，2026-10-22）：
    维度 3/4/5 的判据全部来自 raw 环节级工件，工件不可用时**不做归因**，
    只给可区分的披露档：
      - `RAW_UNAVAILABLE`：未提供 --raw-dir / 该任务件不存在 / 件不可读；
      - `DEP_INPUT_ABSENT`：件在但 `cross_file_deps` 键不存在（该批次跑批早于
        `run_benchmark.py` 把此键写进 raw 白名单）；
      - `DEP_INPUT_NULL`：键在但值为 null（BN 起白名单恒写该键，null = 依赖图
        分析环节从未记录）——只有节点真写过 `[]`（`src/graph/nodes.py:2211`
        "AST 与预置边都分析过、确实没边"）才配得上 `DEP_GRAPH_INCOMPLETE`。
    改前三级"读不到"都被折成 `len([]) == 0` 的一次实测：不带 raw 复放 9 臂
    29 例失败里 14 例被判 `DEP_GRAPH_INCOMPLETE`（level1 单文件对照 0 例），
    而带 raw 的 `cross_file_ab_level3` 两臂 7/7 失败任务该键根本不存在。
    单文件任务不经结构档，其判定逐位不变。
    维度 4/5 的输入 `per_module_patches` / `applied_modules` 都不在 raw 白名单
    里（`applied_modules` 更是全仓库无写方）⇒ 两档在**任何**批次都不可达。
    报告新增 `rule_evidence` / `unreachable_rules` 显式披露，不再让"分布里没有
    这两档"被读成"这两环没问题"。逐条可重跑：
    `python scripts/tools/bo_raw_readside_fold_probe.py`（B / B2 段）。

使用方式：
    # 分析已有 level3 A/B 结果（ON 组 JSON + 原始 state 目录）
    python experiments/cross_file_root_cause.py \
        --results-on experiments/results/cross_file_ab/cross_file_on/benchmark_*.json \
        --raw-dir experiments/results/cross_file_ab/cross_file_on/raw \
        --difficulty level3

    # 仅读 ON 组结果 JSON：无 raw state 时**只出错误分类档**（LLM_BREAKS_IMPORT /
    # EMPTY_LLM_PATCH / LLM_CAPABILITY），多文件失败落 RAW_UNAVAILABLE 而非根因
    python experiments/cross_file_root_cause.py \
        --results-on <path.json> --difficulty level3
"""

from __future__ import annotations

import argparse
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

# 结构档（DEP_GRAPH_INCOMPLETE / ROLLBACK_CONSERVATIVE / TOPOLOGICAL_ORDER）的
# 判据输入。BO（2026-10-22）实测：`run_benchmark._dump_state_artifacts` 的 raw
# 白名单只含 cross_file_deps，后两键从未落盘（applied_modules 更是全仓库无写方）
# ⇒ analyze() 据此逐批披露哪些档"零证据"，不再让分布里的缺失读成"没问题"。
STRUCTURAL_INPUTS = ("cross_file_deps", "per_module_patches", "applied_modules")


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
        for bl_data in results.values():
            if isinstance(bl_data, dict) and "details" in bl_data:
                return bl_data["details"] or []
        # 兼容 results 直接是 list 的旧口径
        if isinstance(results, list):
            return results
    return []


def _load_state(raw_dir: str | None, task_id: str) -> tuple[dict[str, Any] | None, str]:
    """读单任务环节级工件，返回 (state, status)。

    status ∈ {"ok", "no_raw_dir", "file_absent", "unreadable"}——BO（2026-10-22）
    之前这四种"读不到"在 analyze() 里全塌成 `state = None`，于是"没落盘"、
    "件损坏"与"确实没有依赖边"在报告里不可区分，模块 docstring 承诺的降级
    口径也不存在。缺席只做披露，不做归因。
    """
    if not raw_dir:
        return None, "no_raw_dir"
    raw_file = os.path.join(raw_dir, task_id, "aitester.json")
    if not os.path.exists(raw_file):
        return None, "file_absent"
    try:
        with open(raw_file, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, "unreadable"
    # 顶层不是对象（历史手改 / 截断件）同样按"不可用"披露，而非让下游 .get 炸穿。
    if not isinstance(state, dict):
        return None, "unreadable"
    return state, "ok"


def _classify_root_cause(result: dict[str, Any], state: dict[str, Any] | None) -> str:
    """单任务失败根因分类（保守、零 LLM 成本，纯数据规则）。

    优先级（首个命中即返回）：
    1. LLM_BREAKS_IMPORT：patch 应用后 import 被破坏（error_category /
       补丁文本含 "import " 删除 / 缺失符号）；
    2. EMPTY_LLM_PATCH：LLM 输出空补丁 / 无法解析（error_category 命中）；
    3a. RAW_UNAVAILABLE / DEP_INPUT_ABSENT / DEP_INPUT_NULL：多文件任务的结构档
       **零证据**（raw 件不可用 / 件在但 cross_file_deps 键不存在 / 键在但值为
       null）⇒ 不归因，只披露；
    3b. DEP_GRAPH_INCOMPLETE：cross_file_deps 边数 < num_files - 1（依赖图不完整）；
    4. ROLLBACK_CONSERVATIVE：多文件补丁中仅 1 文件失败导致整体回滚；
    5. TOPOLOGICAL_ORDER：拓扑序违规（调用方先改、被调用方后改）；
    6. LLM_CAPABILITY：以上皆非命中（LLM 引擎能力边界，需 GPT-4 级模型）。

    1/2/6 只用结果行，4/5 的输入从未进过 raw 白名单（见 analyze 的
    rule_evidence）——3a 因此必须在 3b 之前判，否则"没读到"会被当成"0 条边"。
    """
    err_cat = str(result.get("error_category") or "").upper()
    patch = result.get("patch") or ""
    num_files = int((result.get("task_metadata") or {}).get("num_files", 1))

    # 1. LLM_BREAKS_IMPORT：补丁删除/破坏 import 语句
    if "LLM_BREAKS_IMPORT" in err_cat or "IMPORT" in err_cat:
        return "LLM_BREAKS_IMPORT"
    # 2. EMPTY_LLM_PATCH：LLM 输出空
    if "EMPTY" in err_cat or len(patch.strip()) < 20:
        return "EMPTY_LLM_PATCH"
    # 3. 依赖图不完整：边数 < 文件数 - 1。判据只能在 raw 工件上成立：
    #    state 不可用 → RAW_UNAVAILABLE，件在但 cross_file_deps 键不存在
    #    （批次早于该键进 raw 白名单）→ DEP_INPUT_ABSENT，键在但值为 null
    #    （BN 起白名单恒写该键，null = 该环节从未记录依赖图）→ DEP_INPUT_NULL。
    #    三种缺席改前都被折成 `len([]) == 0` 的"实测 0 条边"，于是多文件失败整批
    #    落 DEP_GRAPH_INCOMPLETE。复放读数（scripts/tools/bo_raw_readside_fold_probe.py
    #    B 段，9 臂 29 例失败）分两口径说清：改前 14 例判定随 raw 目录翻转，另有
    #    4 例进到本档的"件在但 cross_file_deps 键不存在"行在带 raw / 不带 raw 两臂下
    #    同折成 DEP_GRAPH_INCOMPLETE、因此翻不出来（level3 两臂 7 例键缺席里另有 3 例
    #    先落 EMPTY_LLM_PATCH，不经本档）；本轮分档后同一臂集 18 例翻转，多出的正是那
    #    4 例键级缺席。level1（单文件）两臂恒 0 例翻转。只有节点真写过空列表
    #    （nodes.py:2211 `cross_file_deps: []` = "AST 与预置边都分析过、确实没边"）
    #    才配得上 DEP_GRAPH_INCOMPLETE。单文件任务不经本档，判定逐位不变。
    if num_files > 1:
        if state is None:
            return "RAW_UNAVAILABLE"
        if "cross_file_deps" not in state:
            return "DEP_INPUT_ABSENT"
        if state.get("cross_file_deps") is None:
            return "DEP_INPUT_NULL"
    deps = (state or {}).get("cross_file_deps") or []
    if num_files > 1 and len(deps) < num_files - 1:
        return "DEP_GRAPH_INCOMPLETE"
    # 4. 回滚保守度：多文件补丁且 per_module_patches 非全应用。
    # 5. 拓扑序违规：调用方模块先于被调用方应用。
    #    BO（2026-10-22）披露：这两档的输入 per_module_patches / applied_modules
    #    都不在 `run_benchmark._dump_state_artifacts` 的 raw 白名单里
    #    （`applied_modules` 更是全仓库无任何写方），所以对任何真实批次它们都
    #    不可达。不在这里伪判，改由 analyze() 的 rule_evidence /
    #    unreachable_rules 把"这一档零证据"显式说出来。
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
                        d.get("source_module") == applied[i] and d.get("target_module") == applied[j] for d in deps
                    )
                    if has_edge:
                        return "TOPOLOGICAL_ORDER"
    # 6. 兜底：LLM 引擎能力边界
    return "LLM_CAPABILITY"


def analyze(results: list[dict[str, Any]], raw_dir: str | None, difficulty: str = "level3") -> dict[str, Any]:
    """汇总 level3 ON 组失败任务的根因分布。

    Args:
        results: benchmark 结果 details 列表。
        raw_dir: 原始 state 落盘目录（<raw>/<task_id>/aitester.json），可为 None；
            BO 起 None 与"目录在但件缺"与"件损坏"分别记为 no_raw_dir /
            file_absent / unreadable，不再塌成同一种"读不到"。
        difficulty: 难度级别（用于日志标注与过滤）。

    Returns:
        根因分布 dict：`root_cause_distribution` + `details`（每项含
        `raw_state_status` 与可为 null 的 `dep_edges`），外加 BO 新增的自证面
        `raw_coverage`（这批到底用了多少 raw）与 `rule_evidence` /
        `unreachable_rules`（哪些结构档在本批零证据——`states_with_key` 说键在场，
        `states_recorded` 说真有价值，BN 起两者可以差一整批）。改前返回值里没有
        任何覆盖度字段，"整批没读 raw"与"读了但确实 0 条边"产出的 JSON 逐字段同形。
    """
    failed = [r for r in results if not r.get("passed")]
    # 按 difficulty 过滤（task_metadata.difficulty）
    # 2026-10 改进：task_metadata.difficulty 在 L3.5 存的是数字 35（非字符串
    # "level3.5"），历史过滤 str(...) == difficulty 永远不命中导致失败任务
    # 全被过滤掉。现改为：先按原始值精确匹配（兼容数字/字符串），再按
    # "level3.5"↔35 / "level3"↔3 的数字码等价匹配。
    if difficulty:
        _difficulty_to_code = {
            "level1": 1,
            "level2": 2,
            "level2.5": 25,
            "level3": 3,
            "level3.5": 35,
            "level4": 4,
            "level4.5": 45,
        }
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
            return difficulty in _difficulty_to_code and d == _difficulty_to_code[difficulty]

        failed = [r for r in failed if _match(r)]
    dist: Counter[str] = Counter()
    coverage: Counter[str] = Counter()
    inputs: Counter[str] = Counter()
    recorded: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    for r in failed:
        state, status = _load_state(raw_dir, str(r.get("task_id", "")))
        coverage[status] += 1
        if state is not None:
            for _key in STRUCTURAL_INPUTS:
                if _key in state:
                    inputs[_key] += 1
                    # BN 起白名单恒写 cross_file_deps（未记录落 null）⇒ "键在场"
                    # 不等于"这一档有证据"，reachable 只认非 null 的取值。
                    if state[_key] is not None:
                        recorded[_key] += 1
        cause = _classify_root_cause(r, state)
        dist[cause] += 1
        deps_raw = state.get("cross_file_deps") if isinstance(state, dict) else None
        deps = deps_raw if isinstance(deps_raw, list) else None
        details.append(
            {
                "task_id": r.get("task_id"),
                "root_cause": cause,
                "error_category": r.get("error_category"),
                "iterations": r.get("iterations"),
                "num_files": int((r.get("task_metadata") or {}).get("num_files", 1)),
                # BO（2026-10-22）：件不可用 / 键不存在时 dep_edges=None（"没测"），
                # 不再写 0（"实测 0 条边"）——那个被折出来的 0 正是把 14 例多文件
                # 失败判成 DEP_GRAPH_INCOMPLETE 的那一步。
                "dep_edges": None if deps is None else len(deps),
                "raw_state_status": status,
                "patch_len": len(r.get("patch") or ""),
            }
        )
    n_state = coverage["ok"]
    rule_evidence = {
        key: {
            "states_available": n_state,
            "states_with_key": inputs[key],
            "states_recorded": recorded[key],
            "reachable": recorded[key] > 0,
        }
        for key in STRUCTURAL_INPUTS
    }
    unreachable_rules = [
        rule
        for rule, key in (
            ("DEP_GRAPH_INCOMPLETE", "cross_file_deps"),
            ("ROLLBACK_CONSERVATIVE", "per_module_patches"),
            ("TOPOLOGICAL_ORDER", "applied_modules"),
        )
        if not rule_evidence[key]["reachable"]
    ]
    return {
        "difficulty": difficulty,
        "total_failed": len(failed),
        # BO：报告自证用了多少 raw——改前 analyze() 里没有任何覆盖度字段，
        # "整批没读 raw"与"读了但确实都是 0 条边"产出的 JSON 逐字段同形。
        "raw_coverage": {
            "raw_dir": raw_dir,
            "by_status": dict(coverage.most_common()),
            "state_available": n_state,
            "state_unavailable": len(failed) - n_state,
        },
        "rule_evidence": rule_evidence,
        "unreachable_rules": unreachable_rules,
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
    if not args.raw_dir:
        # BO：docstring 承诺的"无 raw 降级"必须可见，而不是静默换档。
        logger.warning("未提供 --raw-dir：多文件失败只落 RAW_UNAVAILABLE 披露档，不做依赖图归因")

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
