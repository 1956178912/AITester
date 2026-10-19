#!/usr/bin/env python3
"""emse_dsl_diag3.py — SpecExpr DSL 拒绝分布诊断（EMSE 批次六，2026-10-15，零 LLM）。

动机（2026-10-14 分层叙事收口后的下一优化方向）：
    M4 QuixBugs 扩样阴性（δ=−8.57pp/p=0.4531）+ synthetic 确认性阴性
    （δ=−0.57pp/p=1.0）之后，"规格优先 + 形式化规约"主张按数据集分层，
    项目自述下一步 = **扩受限表达式 DSL 覆盖率（白名单/文法）**，
    非换数据集刷显著性。本脚本为该扩文法提供实测依据。

语料（真实 LLM 产物，零新调用）：
    ~/.cache/aitester/llm 的 **Planner** 缓存条目（system 含"测试规划师"）：
    - prompt 内首个 ``` 块 = 被测源码（签名提取材料源）；
    - response = 计划 JSON，logic_analysis 含 *_expr 形式化子句
      （SPEC_EXPR_CONTRACT_SECTION 契约产物，即 compile_readiness 的靶）。

判定口径（与在线管线逐字一致）：
    1. 函数名解析：plan.function_name；空或字面量 "unknown" 时按
       src/graph/nodes.py 度量侧第三级回退 sole_top_level_function_name；
    2. 签名：extract_signature_params(source, func)（三态口径）；
    3. 通道：_select_compile_channels（expr 优先，空则回退 NL）；
    4. 逐子句 clause_reject_reason（当前门，含 2026-10-14 修复：
       _BUILTIN_TYPE_NAMES 值位置放行 + sole 回退）。

对照门（旧门 = 2026-10-14 修复前）：
    known = params or 默认集；known_with_calls = known | _ALLOWED_CALL_NAMES
    （无 _BUILTIN_TYPE_NAMES、无 sole 回退）——复刻 spec_ir_v2 修复前逻辑。

输出：experiments/results/emse_dsl_diag3_20261015/
    - DIAG3_REPORT.json（全量聚合 + 样本 + 三口径对账）；
    - README.md（人读分布表）。

去重口径：同一 (dataset, function_name, kind, clause) 在不同跑批/臂中重复
出现只计一次（防 A/B 臂双计）；任务级按 (dataset, function_name) 去重。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.specs.spec_ir import extract_signature_params, parse_logic_analysis  # noqa: E402
from src.specs.spec_ir_v2 import (  # noqa: E402
    _ALLOWED_CALL_NAMES,
    _clause_reject_reason_for_known,
    _form_gate_reject_reason,
    _free_names,
    _known_names_for_signature,
    _normalize_result_alias,
    _select_compile_channels,
    _whitelist_check,
)
from src.tools.spec_first import sole_top_level_function_name  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402

DEFAULT_CACHE = Path.home() / ".cache" / "aitester" / "llm"
QUIXBUGS_DIR = Path.home() / ".cache" / "aitester" / "quixbugs" / "python_programs"
ULT_MANIFEST = Path.home() / ".cache" / "aitester" / "ult" / "ult_manifest.jsonl"

_PLANNER_MARKER = "测试规划师"
_SOURCE_BLOCK_RE = re.compile(r"请分析以下代码并制定测试计划：\s*```[a-zA-Z]*\s*\n(.*?)```", re.DOTALL)


# ─── 数据集索引（按 def 行匹配，防跨数据集函数名碰撞）────────────────────────


def _def_lines(source: str) -> list[str]:
    """源码的全部顶层 def 行（含类内直接方法，与 extract_signature_params 同口径）。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"def {node.name}(")
        elif isinstance(node, ast.ClassDef):
            lines.extend(
                f"def {sub.name}(" for sub in node.body if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return lines


def load_dataset_index() -> dict[str, str]:
    """def 行 → 数据集名（quixbugs / ult）。synthetic 等无本地索引的留空。"""
    index: dict[str, str] = {}
    if QUIXBUGS_DIR.is_dir():
        for path in sorted(QUIXBUGS_DIR.glob("*.py")):
            if path.name.endswith("_test.py"):
                continue  # 测试文件非被测程序
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in _def_lines(source):
                index.setdefault(line, "quixbugs")
    if ULT_MANIFEST.is_file():
        with ULT_MANIFEST.open(encoding="utf-8") as handle:
            for raw in handle:
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                source = str(row.get("source_code") or "")
                for line in _def_lines(source):
                    index.setdefault(line, "ult")
    return index


def tag_dataset(source: str, index: dict[str, str]) -> str:
    """按 prompt 源码的 def 行匹配数据集；无匹配 → other（合成集等）。"""
    for line in _def_lines(source):
        if line in index:
            return index[line]
    return "other"


# ─── 缓存语料提取 ────────────────────────────────────────────────────────────


def _parse_plan_response(response: str) -> dict[str, Any] | None:
    """解析 Planner 响应 JSON（容忍 ```json 围栏与前后杂文本）。"""
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def iter_planner_entries(cache_dir: Path):
    """产出 (cache_file, source, plan) —— Planner 缓存条目。"""
    for path in sorted(cache_dir.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(entry, dict):
            continue
        system = str(entry.get("system") or "")
        if _PLANNER_MARKER not in system:
            continue
        plan = _parse_plan_response(str(entry.get("response") or ""))
        if plan is None:
            continue
        logic = plan.get("logic_analysis")
        if not isinstance(logic, dict):
            continue
        # 只收契约产物（任一 *_expr 字段含 str 子句）——NL-only 计划不是 DSL 的靶
        has_expr = any(
            isinstance(logic.get(field), list) and any(isinstance(c, str) and c.strip() for c in logic[field])
            for field in ("preconditions_expr", "postconditions_expr", "invariants_expr")
        )
        if not has_expr:
            continue
        prompt = str(entry.get("prompt") or "")
        match = _SOURCE_BLOCK_RE.search(prompt)
        source = match.group(1) if match else ""
        yield path, source, plan


# ─── 判定口径复刻 ────────────────────────────────────────────────────────────


def resolve_signature_params(source: str, plan: dict[str, Any]) -> tuple[list[str] | None, str]:
    """复刻 nodes.py 度量侧函数名三级解析 + 签名提取。

    返回 (signature_params, 解析路径标签)：params 为 None 表示签名未知
    （调用方按历史默认集合 {r,x,a,b,y} 处理，与在线口径一致）。
    """
    raw_func = str(plan.get("function_name") or "")
    if raw_func and raw_func != "unknown":
        return extract_signature_params(source, raw_func), "plan_name"
    if not source:
        return None, "no_source"
    sole = sole_top_level_function_name(source)
    if sole:
        return extract_signature_params(source, sole), "sole_fallback"
    return None, "no_func"


def _old_gate_reject_reason(clause: Any, kind: str, known: frozenset[str]) -> str | None:
    """旧门（2026-10-14 修复前 + v4 前字符类/白名单）：known_with_calls = known | _ALLOWED_CALL_NAMES。

    与现行 _clause_reject_reason_for_known 的差别（三处常量全部摘除才复刻
    "10-14 修复前"的逐字行为——v4 上线后旧门复刻若只摘字符类/白名单之一，
    会把切片或 v4 新条目放行、旧门可编译率被高估；2026-10-15 归档重建时
    先后发现并修正这两处）：
    ① 字符类无冒号（v4 前）；
    ② 未知标识符门的已知集无 _BUILTIN_TYPE_NAMES；
    ③ 白名单无 v4 新增调用/属性（sum/set/bool/hasattr、values/keys/items/
       get/isupper/islower/bit_length——它们在旧代码里不存在）。
    """
    import src.specs.spec_ir_v2 as v2

    saved = (v2._EXPR_TOKEN_RE, v2._ALLOWED_CALL_NAMES, v2._ALLOWED_ATTRS)
    v2._EXPR_TOKEN_RE = _EXPR_TOKEN_RE_PRE_V4
    v2._ALLOWED_CALL_NAMES = saved[1] - _V4_CALLS
    v2._ALLOWED_ATTRS = saved[2] - _V4_ATTRS
    try:
        if not isinstance(clause, str):
            return "not_a_string"
        text = clause.strip()
        if not text:
            return "empty"
        if not v2.is_expression_clause(clause):
            return _form_gate_reject_reason(text)
        if _whitelist_check(clause):
            return "unsupported_operator"
        normalized = _normalize_result_alias(clause, kind, known)
        tree = ast.parse(normalized, mode="eval")
        identifiers = _free_names(tree)
        if identifiers - (known | saved[1]):
            return "unknown_name"
        return None
    finally:
        v2._EXPR_TOKEN_RE, v2._ALLOWED_CALL_NAMES, v2._ALLOWED_ATTRS = saved


def evaluate_plan(source: str, plan: dict[str, Any], index: dict[str, str]) -> dict[str, Any]:
    """对单个计划逐子句三口径判定（当前门 / 旧门）+ 未知名与算子违例明细。"""
    dataset = tag_dataset(source, index) if source else "other"
    sig_params, func_path = resolve_signature_params(source, plan)
    spec = parse_logic_analysis(plan.get("logic_analysis"))
    if spec is None:
        return {"dataset": dataset, "func_path": func_path, "clauses": []}
    known = _known_names_for_signature(sig_params)
    pre, post, inv = _select_compile_channels(spec)
    rows: list[dict[str, Any]] = []
    for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
        for clause in clauses:
            if not clause.strip():
                continue  # 空白不进分母（与在线口径一致）
            reason = _clause_reject_reason_for_known(clause, kind, known)
            old_reason = _old_gate_reject_reason(clause, kind, known)
            detail: dict[str, Any] = {"kind": kind, "clause": clause, "reason": reason, "old_reason": old_reason}
            if reason == "unknown_name":
                # 复刻当前门的未知标识符计算（含 result 别名归一）
                normalized = _normalize_result_alias(clause, kind, known)
                free = _free_names(ast.parse(normalized, mode="eval"))
                detail["unknown_names"] = sorted(free - (known | _ALLOWED_CALL_NAMES | _builtin_type_names()))
            elif reason == "unsupported_operator":
                detail["violations"] = _whitelist_check(clause)
            rows.append(detail)
    return {
        "dataset": dataset,
        "func_path": func_path,
        "function_name": str(plan.get("function_name") or ""),
        "clauses": rows,
    }


def _builtin_type_names():
    from src.specs.spec_ir_v2 import _BUILTIN_TYPE_NAMES

    return _BUILTIN_TYPE_NAMES


# v4 新增项（--prior-gate 快照的摘除集——与 spec_ir_v2 v4 注释逐字对应）。
# 归档纪律：DIAG3_REPORT.json 是 **v4 实施前**的诊断快照；v4 后重跑本脚本
# 会用新门覆盖它，故快照必须用 --prior-gate 重建（与 v4 前门逐字等价：
# 字符类去冒号 + 两个白名单摘除；lambda/海象护栏在旧字符门下不可达——
# 两类子句都含冒号、旧门即拒，这正是"冒号放行 ⇒ 护栏必须配对"的结构性原因）。
_V4_CALLS = frozenset({"sum", "set", "bool", "hasattr"})
_V4_ATTRS = frozenset({"values", "keys", "items", "get", "isupper", "islower", "bit_length"})
_EXPR_TOKEN_RE_PRE_V4 = re.compile(r"^\s*[A-Za-z_\d\[\]\(\).\-+*/%<>=!&|~^, \"]*$")


class _prior_gate_patch:
    """上下文管理器：把 spec_ir_v2 的三个模块级常量换回 v4 前值。

    判定逻辑零复刻——clause_reject_reason 及其下游全部经模块全局查找常量，
    临时换值即得旧门逐字行为（与 emse_dsl_extend_recheck 同法）。
    """

    def __enter__(self) -> None:
        import src.specs.spec_ir_v2 as v2

        self._v2 = v2
        self._saved = (v2._EXPR_TOKEN_RE, v2._ALLOWED_CALL_NAMES, v2._ALLOWED_ATTRS)
        v2._EXPR_TOKEN_RE = _EXPR_TOKEN_RE_PRE_V4
        v2._ALLOWED_CALL_NAMES = self._saved[1] - _V4_CALLS
        v2._ALLOWED_ATTRS = self._saved[2] - _V4_ATTRS

    def __exit__(self, *_exc: object) -> None:
        self._v2._EXPR_TOKEN_RE, self._v2._ALLOWED_CALL_NAMES, self._v2._ALLOWED_ATTRS = self._saved


# ─── 聚合 ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="SpecExpr DSL 拒绝分布诊断（零 LLM）")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments/results/emse_dsl_diag3_20261015")
    parser.add_argument(
        "--prior-gate",
        action="store_true",
        help="用 v4 前门（字符类去冒号 + 白名单摘除 v4 新增项）判定——用于重建 v4 实施前的诊断快照",
    )
    args = parser.parse_args()
    if args.prior_gate:
        print("[diag3] 门口径：v4 前门（--prior-gate，常量摘除法）")

    index = load_dataset_index()
    print(f"[diag3] 数据集索引：{len(index)} 个 def 行（quixbugs/ult）")

    plans = list(iter_planner_entries(args.cache_dir))
    print(f"[diag3] Planner 缓存条目（含 *_expr 契约产物）：{len(plans)}")

    # 去重：(dataset, function_name, kind, clause) 唯一计一次
    seen: set[tuple[str, str, str, str]] = set()
    unique_rows: list[dict[str, Any]] = []
    task_keys: set[tuple[str, str]] = set()
    func_path_counter: Counter[str] = Counter()
    gate_ctx = _prior_gate_patch() if args.prior_gate else None
    if gate_ctx is not None:
        gate_ctx.__enter__()
    try:
        for _path, source, plan in plans:
            result = evaluate_plan(source, plan, index)
            dataset = result["dataset"]
            func_path_counter[result["func_path"]] += 1
            for row in result["clauses"]:
                task_keys.add((dataset, result["function_name"]))
                key = (dataset, result["function_name"], row["kind"], row["clause"])
                if key in seen:
                    continue
                seen.add(key)
                row = dict(row)
                row["dataset"] = dataset
                unique_rows.append(row)
    finally:
        if gate_ctx is not None:
            gate_ctx.__exit__()

    print(f"[diag3] 去重后子句实例：{len(unique_rows)}；涉及任务（dataset×函数）：{len(task_keys)}")
    print(f"[diag3] 函数名解析路径分布：{dict(func_path_counter)}")

    # 聚合：总体 + 分数据集
    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        reasons = Counter(r["reason"] or "compilable" for r in rows)
        old_reasons = Counter(r["old_reason"] or "compilable" for r in rows)
        unknown_names: Counter[str] = Counter()
        violations: Counter[str] = Counter()
        for r in rows:
            for name in r.get("unknown_names") or []:
                unknown_names[name] += 1
            for v in r.get("violations") or []:
                violations[v] += 1
        total = len(rows)
        return {
            "total_clauses": total,
            "reasons": dict(reasons.most_common()),
            "old_gate_reasons": dict(old_reasons.most_common()),
            "compile_rate_new": round(reasons.get("compilable", 0) / total, 4) if total else None,
            "compile_rate_old": round(old_reasons.get("compilable", 0) / total, 4) if total else None,
            "unknown_name_identifiers": dict(unknown_names.most_common(30)),
            "operator_violations": dict(violations.most_common(30)),
        }

    datasets = sorted({r["dataset"] for r in unique_rows})
    gate_current_label = (
        "pre-v4 (colon removed, v4 whitelist entries removed; --prior-gate snapshot)"
        if args.prior_gate
        else "post-2026-10-14-fix + v4 (sole fallback + builtin type names + colon/slices + v4 whitelists)"
    )
    report: dict[str, Any] = {
        "meta": {
            "date": "2026-10-15",
            "batch": "emse-batch6-dsl-diag3",
            "cache_dir": str(args.cache_dir),
            "planner_entries": len(plans),
            "unique_clause_instances": len(unique_rows),
            "unique_tasks": len(task_keys),
            "func_path_distribution": dict(func_path_counter),
            "gate_current": gate_current_label,
            "gate_old": "pre-2026-10-14-fix (default known set, no type names)",
            "prior_gate_snapshot": bool(args.prior_gate),
        },
        "overall": aggregate(unique_rows),
        "by_dataset": {ds: aggregate([r for r in unique_rows if r["dataset"] == ds]) for ds in datasets},
        "samples": {},
    }
    # 每原因样本（去重文本，截断展示）
    for reason in (
        "natural_language",
        "unsupported_syntax",
        "unsupported_operator",
        "unknown_name",
        "parse_error",
        "too_long",
    ):
        texts = sorted({r["clause"] for r in unique_rows if r["reason"] == reason})
        report["samples"][reason] = texts[:20]

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "DIAG3_REPORT.json"
    atomic_write_json(json_path, report, indent=2, mode=0o644)
    print(f"[diag3] JSON 报告：{json_path}")

    # 人读摘要
    print("\n===== 拒绝分布（当前门，去重子句） =====")
    overall = report["overall"]
    for reason, count in overall["reasons"].items():
        pct = count / overall["total_clauses"] * 100
        print(f"  {reason:24s} {count:5d}  ({pct:5.1f}%)")
    print(f"  旧门可编译率 {overall['compile_rate_old']} → 当前门 {overall['compile_rate_new']}")
    print("\n===== unknown_name 未知名 Top =====")
    for name, count in list(overall["unknown_name_identifiers"].items())[:15]:
        print(f"  {name:24s} {count:5d}")
    print("\n===== 算子级违例 Top =====")
    for v, count in list(overall["operator_violations"].items())[:15]:
        print(f"  {v:32s} {count:5d}")
    print("\n===== 分数据集 =====")
    for ds in datasets:
        sub = report["by_dataset"][ds]
        print(
            f"  {ds:10s} n={sub['total_clauses']:5d} "
            f"compile={sub['compile_rate_new']} (old {sub['compile_rate_old']}) "
            f"top={list(sub['reasons'].items())[:4]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
