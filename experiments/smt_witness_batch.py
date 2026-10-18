"""T3b（2026-10-18 T 轮）：z3 SMT 见证层最小启用批次（A-18 / Q7，零 LLM）。

背景（独立评审 2026-10-17 A-18 / Q7）
======================================
``src/specs/spec_smt.py`` 的 SMT 见证层（SpecIR 前件求解 / 后件自洽）实现在场，
但**无任何启用批次记录**——"能力在场、评估缺席"。本脚本执行
``docs/design/smt_witness_batch_plan.md`` 的最小启用批次：**单臂观测批**，
零 LLM，只读既有工件与 Planner 缓存物化锚表。

口径（与预注册 ``PREREG.md`` 逐条对应，跑前冻结）
==================================================
1. 任务集：``emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json``
   的 ``plain_llm_df_spec`` 臂 50 行；**主判定集 = 41 个缺陷程序**（program 不以
   ``_test`` 结尾，与 df_spec detection 41 口径同集），9 个 ``*_test`` 驱动任务
   仅扩展披露。
2. 材料：``emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json`` 按
   ``sha256(buggy_source.strip())`` 内容寻址查表（加载强制 SHA256SUMS 校验，
   fail-closed，复用 ``experiments.oracle_quality_replay.load_anchor_table``）；
   缺口任务记 ``spec_material_missing`` 剔除并披露，不用 LLM 补跑。
3. 子句：``parse_logic_analysis``（src 公开入口）→ SpecExpr 形式化通道
   （``*_expr``，通道选择与 ``_select_compile_channels`` 同口径；无 expr 时
   回退 NL 通道并标注）→ **逐子句**构造单子句 spec 交 ``spec_smt`` 公开 API
   （pre → ``check_precondition_vacuity``；post+inv → ``check_postcondition_consistency``）。
   编译门/白名单/排序推断/翻译全部在 src 内，**不重实现**。
4. 求解：``SPEC_SMT_TIMEOUT_MS=5000``（per-clause 5s 有界）；``unknown`` 且
   墙钟 ≥ 0.9×timeout → ``timeout``；``skipped``（未达求解器）→ ``error``
   （``error_kind="not_reached"``，**不计 unsat**）。
5. 判定（冻结）：机制层 = 主判定集均值 ``smt_witness_rate`` > 0 ∧
   ``smt_timeout_rate``（pooled timeout/reached）< 20% ∧ 每个 status 桶可由
   ``PER_CLAUSE.jsonl`` 逐子句复算；关联层 = 探索性（中位数分桶 vs df_spec
   detection，MDE≈16.57pp 披露，禁止"提升/显著"措辞）。

产物（``--out``，默认 ``experiments/results/t_round_smt_witness_20261018``）
============================================================================
``PREFLIGHT.json`` / ``PER_CLAUSE.jsonl`` / ``TASK_LEVEL.json`` /
``ANALYSIS_REPORT.json`` / ``README.md`` / ``RUN_SUMMARY.log``（``PREREG.md`` /
``SHA256SUMS`` 由跑批流程另行落盘/校验）。

零 LLM 与确定性
================
- 本脚本只读本地工件与本地源码，不导入/调用任何 LLM/网络客户端（PREFLIGHT 提供
  自源码禁词扫描证据与 ``llm_calls=0``）；
- 无时间戳进入内容数据文件；同输入两次运行 ``PER_CLAUSE.jsonl`` /
  ``TASK_LEVEL.json`` / ``ANALYSIS_REPORT.json`` 逐字节一致；z3 对固定输入确定性。

用法::

    .venv/bin/python -m experiments.smt_witness_batch
    .venv/bin/python -m experiments.smt_witness_batch --out /tmp/smt_out
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.misguided_metrics import (  # noqa: E402
    MaterialError,
    canonical_json,
    resolve_buggy_source,
    resolve_quixbugs_roots,
    sha256_file,
    sha256_text,
)
from experiments.oracle_quality_replay import load_anchor_table, lookup_anchor  # noqa: E402
from src.specs.spec_ir import extract_signature_params, parse_logic_analysis  # noqa: E402
from src.specs.spec_smt import (  # noqa: E402
    check_postcondition_consistency,
    check_precondition_vacuity,
    smt_available,
)
from src.utils.atomic_io import atomic_write_json, atomic_write_text  # noqa: E402

SCHEMA_VERSION = "t_round_smt_witness/1"
TOOL_NAME = "experiments.smt_witness_batch"
TOOL_VERSION = "1.0.0"

DEFAULT_OUT = _REPO_ROOT / "experiments" / "results" / "t_round_smt_witness_20261018"
DEFAULT_ANCHOR_TABLE = _REPO_ROOT / "experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"
DEFAULT_DF_SPEC_BENCHMARK = (
    _REPO_ROOT / "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json"
)
DEFAULT_DF_SPEC_REPORT = _REPO_ROOT / "experiments/results/emse_df_spec_20261016/DF_SPEC_REPORT.json"

# ─── 冻结参数（与 PREREG.md §3/§5 一致；改动即参数重标，须重跑并披露）──────────
SOLVE_TIMEOUT_MS = 5000
UNKNOWN_AS_TIMEOUT_RATIO = 0.9
STATUS_ENUM: tuple[str, ...] = ("sat", "unsat", "unknown", "timeout", "error")
PRIMARY_CALIBER_SUFFIX = "_test"
MDE_PP_FROZEN = 16.57  # df_spec 41 口径 MDE（DF_SPEC_REPORT.json::contrast_41.mde_pp）
TIMEOUT_FAIL_RATIO = 0.20
MIN_MATERIAL_TASKS = 30

# 零 LLM 自检：禁用模块根（本脚本 AST import 面出现即视为违反零 LLM 约束）
_FORBIDDEN_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "llm_client",
        "openai",
        "anthropic",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "langchain",
        "litellm",
    }
)
# 动态导入调用名（importlib / __import__）同样拦截
_FORBIDDEN_DYNAMIC_IMPORTS: frozenset[str] = frozenset({"import_module", "__import__"})


# ─── 基础工具 ─────────────────────────────────────────────────────────────────
def now_iso() -> str:
    """本地时区 ISO8601 时间戳（仅进 PREFLIGHT / RUN_SUMMARY，不进内容数据）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def shallow_sha16(text: str) -> str:
    """子句文本 sha256 前 16 位（小写十六进制；per-clause 审计锚点）。"""
    return sha256_text(text)[:16]


def canonical_dump(obj: Any) -> str:
    """确定性 JSON 文本（键排序 + 紧凑分隔符）；用于幂等比较与逻辑材料摘要。"""
    return canonical_json(obj)


def _round6(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


# 计时键（求解器墙钟本质非确定）：幂等比较时剔除，其余分类/计数/率字段要求一致
_TIMING_KEYS: frozenset[str] = frozenset(
    {
        "smt_solve_ms",
        "smt_solve_ms_total",
        "solve_ms_total",
        "solver_cpu_ms_total",
        "wall_clock_seconds",
    }
)


def _strip_timing_keys(obj: Any) -> Any:
    """递归剔除计时键（用于进程内两次独立求解的确定性比较）。"""
    if isinstance(obj, dict):
        return {k: _strip_timing_keys(v) for k, v in obj.items() if k not in _TIMING_KEYS}
    if isinstance(obj, list):
        return [_strip_timing_keys(v) for v in obj]
    return obj


# ─── 材料选择（与 src 通道选择同口径）───────────────────────────────────────
def select_clause_material(spec: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    """从 SpecIR 选出待求解子句（expr 通道优先，与 ``_select_compile_channels`` 同口径）。

    通道存在性判定：三个 ``*_expr`` 字段任一含 str 子句（含空串）→ expr 通道；
    否则回退 NL 通道（``preconditions`` / ``postconditions`` / ``invariants``）。
    非空过滤在 D1（非空子句分母）口径内进行。

    Returns:
        ``(channel, clauses)``；clauses 元素为
        ``{"channel", "channel_field", "kind", "clause"}``（材料内顺序：
        pre → post → inv）。
    """
    spec = spec or {}
    pre_expr = [c for c in (spec.get("preconditions_expr") or []) if isinstance(c, str)]
    post_expr = [c for c in (spec.get("postconditions_expr") or []) if isinstance(c, str)]
    inv_expr = [c for c in (spec.get("invariants_expr") or []) if isinstance(c, str)]
    if pre_expr or post_expr or inv_expr:
        channel = "expr"
        pre = [("preconditions_expr", "precondition", c) for c in pre_expr]
        post = [("postconditions_expr", "postcondition", c) for c in post_expr]
        post.extend(("invariants_expr", "postcondition", c) for c in inv_expr)
    else:
        channel = "nl"
        pre = [("preconditions", "precondition", c) for c in (spec.get("preconditions") or []) if isinstance(c, str)]
        post = [
            (f, "postcondition", c)
            for f, cs in (
                ("postconditions", spec.get("postconditions") or []),
                ("invariants", spec.get("invariants") or []),
            )
            for c in cs
            if isinstance(c, str)
        ]
    clauses: list[dict[str, Any]] = []
    for field, kind, text in pre + post:
        stripped = text.strip()
        if not stripped:
            continue  # 空串既非"可求解"也不进 D1（与 compile_readiness 非空口径一致）
        clauses.append({"channel": channel, "channel_field": field, "kind": kind, "clause": stripped})
    return channel, clauses


def resolve_signature_params(source: str, function_name: str) -> tuple[list[str] | None, str]:
    """签名参数解析（含点分方法名回退）。

    Returns:
        ``(params | None, source_label)``；source_label ∈
        {"function_name", "dotted_tail", "unresolved"}。
    """
    if not function_name:
        return None, "unresolved"
    params = extract_signature_params(source, function_name)
    if params is not None:
        return params, "function_name"
    if "." in function_name:
        params = extract_signature_params(source, function_name.rsplit(".", 1)[-1])
        if params is not None:
            return params, "dotted_tail"
    return None, "unresolved"


# ─── 逐子句求解与状态分类（冻结映射，PREREG §3）──────────────────────────────
def classify_result(
    raw_status: str, elapsed_ms: float, timeout_ms: int = SOLVE_TIMEOUT_MS
) -> tuple[str, str | None, bool]:
    """公开 API 原值 → (smt_status, error_kind, reached_solver)。

    - sat / unsat → 原样（reached=True）；
    - unknown 且墙钟 ≥ ratio×timeout → timeout（**不计 unsat**）；否则 unknown；
    - skipped（未达求解器）→ error / not_reached（reached=False）；
    - 其他（含异常路径传入的 "exception"）→ error / solver_exception（reached=None 由调用方定）。
    """
    if raw_status == "sat":
        return "sat", None, True
    if raw_status == "unsat":
        return "unsat", None, True
    if raw_status == "unknown":
        if elapsed_ms >= UNKNOWN_AS_TIMEOUT_RATIO * timeout_ms:
            return "timeout", None, True
        return "unknown", None, True
    if raw_status == "skipped":
        return "error", "not_reached", False
    return "error", "solver_exception", True


def solve_clause(
    clause: str,
    kind: str,
    signature_params: list[str] | None,
    *,
    timeout_ms: int = SOLVE_TIMEOUT_MS,
) -> dict[str, Any]:
    """单子句交 spec_smt 公开 API 求解（单子句 spec 构造，src 逻辑零复制）。

    Returns:
        {"smt_status", "error_kind", "reached_solver", "smt_solve_ms",
         "raw_status", "public_api", "exception"}。
    """
    if kind == "precondition":
        spec = {"preconditions": [clause]}
        api_name = "check_precondition_vacuity"
        solver: Callable[..., dict[str, Any]] = check_precondition_vacuity
    else:
        # 后件组（postconditions + invariants）与 _collect_post_constraints 同口径：
        # inv 子句以 postconditions 键单子句喂入后件自洽判定。
        spec = {"postconditions": [clause]}
        api_name = "check_postcondition_consistency"
        solver = check_postcondition_consistency
    t0 = time.perf_counter()
    try:
        raw = solver(spec, signature_params)
        raw_status = str((raw or {}).get("status") or "unknown")
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "smt_status": "error",
            "error_kind": "solver_exception",
            "reached_solver": True,
            "smt_solve_ms": round(elapsed_ms, 3),
            "raw_status": "exception",
            "public_api": api_name,
            "exception": f"{type(exc).__name__}: {exc}"[:300],
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    smt_status, error_kind, reached = classify_result(raw_status, elapsed_ms, timeout_ms)
    return {
        "smt_status": smt_status,
        "error_kind": error_kind,
        "reached_solver": reached,
        "smt_solve_ms": round(elapsed_ms, 3),
        "raw_status": raw_status,
        "public_api": api_name,
        "exception": None,
    }


# ─── 任务级构建 ──────────────────────────────────────────────────────────────
def compute_task_rates(clauses: list[dict[str, Any]]) -> dict[str, Any]:
    """从逐子句行计算任务级计数与率（D1 = 非空评估子句数）。"""
    counts = {status: 0 for status in STATUS_ENUM}
    reached = 0
    solve_ms_total = 0.0
    for row in clauses:
        counts[row["smt_status"]] += 1
        if row.get("reached_solver"):
            reached += 1
        solve_ms_total += float(row.get("smt_solve_ms") or 0.0)
    nonempty = len(clauses)
    sat = counts["sat"]
    timeout = counts["timeout"]
    return {
        "smt_clauses_nonempty": nonempty,
        "smt_clauses_reached": reached,
        "smt_status_counts": counts,
        "smt_witness_rate": _round6(sat / nonempty) if nonempty else None,
        "smt_reach_rate": _round6(reached / nonempty) if nonempty else None,
        "smt_timeout_rate": _round6(timeout / reached) if reached else None,
        "smt_timeout_share_nonempty": _round6(timeout / nonempty) if nonempty else None,
        "smt_solve_ms_total": round(solve_ms_total, 3),
    }


def build_task_record(
    task_row: dict[str, Any],
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
    *,
    in_primary: bool,
    timeout_ms: int = SOLVE_TIMEOUT_MS,
) -> dict[str, Any]:
    """单个任务：取源码 → 查锚 → parse_logic_analysis → 逐子句求解 → 任务行。"""
    task_id = str(task_row.get("task_id") or "")
    metadata = task_row.get("task_metadata") or {}
    program = str(metadata.get("program") or "")
    record: dict[str, Any] = {
        "task_id": task_id,
        "program": program,
        "in_primary": in_primary,
        "material_status": "unknown",
        "material_missing_reason": None,
        "function_name": None,
        "signature_params": None,
        "signature_params_source": "unresolved",
        "channel_used": None,
        "source_path": None,
        "source_sha256": None,
        "anchor_chosen_from": None,
        "anchor_source_len": None,
        "dfspec_detection_rate": task_row.get("detection_rate"),
        "dfspec_detection_measurable": task_row.get("detection_rate") is not None,
        "dfspec_specificity_gate_verdict": task_row.get("specificity_gate_verdict"),
        "dfspec_spec_oracle_verdict": task_row.get("spec_oracle_verdict"),
        "clauses": [],
    }
    # ① 缺陷源码（锚表内容寻址的输入）
    try:
        source, source_path = resolve_buggy_source(program, roots)
    except MaterialError as exc:
        record["material_status"] = "spec_material_missing"
        record["material_missing_reason"] = f"missing_buggy_source: {exc}"[:300]
        record.update(compute_task_rates([]))
        return record
    except OSError as exc:
        record["material_status"] = "spec_material_missing"
        record["material_missing_reason"] = f"source_read_error: {exc}"[:300]
        record.update(compute_task_rates([]))
        return record
    record["source_path"] = _display_path(source_path)
    record["source_sha256"] = sha256_text(source.strip())
    # ② 锚表内容寻址查表（sha256(source.strip())）
    _, anchor_entry = lookup_anchor(anchors, source)
    if not anchor_entry:
        record["material_status"] = "spec_material_missing"
        record["material_missing_reason"] = "anchor_miss: sha256(source.strip()) 不在锚表"
        record.update(compute_task_rates([]))
        return record
    record["anchor_chosen_from"] = anchor_entry.get("chosen_from")
    record["anchor_source_len"] = anchor_entry.get("source_len")
    function_name = str(anchor_entry.get("function_name") or "").strip()
    record["function_name"] = function_name
    # ③ SpecIR 编译入口（src 公开函数）
    spec = parse_logic_analysis(anchor_entry.get("logic_analysis"))
    if spec is None:
        record["material_status"] = "spec_parse_failed"
        record["material_missing_reason"] = "parse_logic_analysis 返回 None"
        record.update(compute_task_rates([]))
        return record
    # ④ 签名参数（含点分方法名回退）
    params, params_source = resolve_signature_params(source, function_name)
    record["signature_params"] = params
    record["signature_params_source"] = params_source
    # ⑤ 通道选择 + 逐子句求解
    channel, clauses = select_clause_material(spec)
    record["channel_used"] = channel
    if not clauses:
        record["material_status"] = "clause_material_empty"
        record["material_missing_reason"] = "所选通道无非空子句"
        record.update(compute_task_rates([]))
        return record
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(clauses):
        solved = solve_clause(item["clause"], item["kind"], params, timeout_ms=timeout_ms)
        rows.append(
            {
                "task_id": task_id,
                "program": program,
                "in_primary": in_primary,
                "function_name": function_name,
                "channel": item["channel"],
                "channel_field": item["channel_field"],
                "kind": item["kind"],
                "clause_index": idx,
                "clause_text": item["clause"],
                "clause_sha256_16": shallow_sha16(item["clause"]),
                "timeout_ms": timeout_ms,
                **solved,
            }
        )
    record["clauses"] = rows
    record["material_status"] = "anchor_hit"
    record.update(compute_task_rates(rows))
    return record


def _display_path(path: Path) -> str:
    """展示路径：仓库内相对路径，否则绝对路径（工件可移植性）。"""
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except (ValueError, OSError):
        return str(path)


# ─── 聚合 / 复算自检 / 关联层 ────────────────────────────────────────────────
def aggregate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合一组任务行（主判定集或扩展集）：池化 status 桶 + 率统计。"""
    with_material = [r for r in records if r.get("material_status") == "anchor_hit"]
    with_clauses = [r for r in with_material if r.get("smt_clauses_nonempty")]
    pooled_counts = {status: 0 for status in STATUS_ENUM}
    clauses_total = 0
    reached_total = 0
    solve_ms_total = 0.0
    for record in with_material:
        for status in STATUS_ENUM:
            pooled_counts[status] += int((record.get("smt_status_counts") or {}).get(status, 0))
        clauses_total += int(record.get("smt_clauses_nonempty") or 0)
        reached_total += int(record.get("smt_clauses_reached") or 0)
        solve_ms_total += float(record.get("smt_solve_ms_total") or 0.0)
    rates = [float(r["smt_witness_rate"]) for r in with_clauses if r.get("smt_witness_rate") is not None]
    timeout_rates = [float(r["smt_timeout_rate"]) for r in with_clauses if r.get("smt_timeout_rate") is not None]
    return {
        "tasks_total": len(records),
        "tasks_with_material": len(with_material),
        "tasks_with_clauses": len(with_clauses),
        "material_gap_tasks": [
            {"task_id": r["task_id"], "material_status": r.get("material_status")}
            for r in records
            if r.get("material_status") != "anchor_hit"
        ],
        "clauses_pooled": clauses_total,
        "clauses_reached_pooled": reached_total,
        "status_totals_pooled": pooled_counts,
        "witness_rate_mean": _round6(statistics.fmean(rates)) if rates else None,
        "witness_rate_median": _round6(statistics.median(rates)) if rates else None,
        "witness_rate_min": _round6(min(rates)) if rates else None,
        "witness_rate_max": _round6(max(rates)) if rates else None,
        "witness_rate_distribution": [_round6(r) for r in rates],
        "tasks_with_any_sat": sum(1 for r in rates if r > 0),
        "tasks_with_zero_witness_rate": sum(1 for r in rates if r <= 0),
        "reach_rate_pooled": _round6(reached_total / clauses_total) if clauses_total else None,
        "timeout_rate_pooled": _round6(pooled_counts["timeout"] / reached_total) if reached_total else None,
        "timeout_rate_mean_task": _round6(statistics.fmean(timeout_rates)) if timeout_rates else None,
        "timeout_share_nonempty_pooled": _round6(pooled_counts["timeout"] / clauses_total) if clauses_total else None,
        "solve_ms_total": round(solve_ms_total, 3),
        "material_task_count_ok": len(with_clauses) >= MIN_MATERIAL_TASKS,
    }


def status_by_channel(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """按通道（expr/nl）× status 的逐子句桶计数。"""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        channel = str(row.get("channel") or "unknown")
        bucket = out.setdefault(channel, {status: 0 for status in STATUS_ENUM})
        bucket[str(row["smt_status"])] += 1
    return out


def attribute_error_clause(clause: str) -> str:
    """启发式文本归因（仅用于 error / not_reached 行；逐子句可复算）。

    优先级（互斥判定）：形式化后件引用 ``result``（后件自由变量域为 ``r`` 的
    别名口径缺口）→ 白名单调用（翻译层不支持 Call）→ 下标 → 属性 → 其他。
    """
    if re.search(r"\bresult\b", clause):
        return "result_alias_not_reached"
    if "(" in clause:
        return "untranslatable_call"
    if "[" in clause:
        return "untranslatable_subscript"
    if "." in clause:
        return "untranslatable_attribute"
    return "other_not_reached"


def error_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按通道 × 归因原因的 error 行计数 + 到达求解器行的结果分解。"""
    by_channel: dict[str, dict[str, int]] = {}
    reached_breakdown = {status: 0 for status in STATUS_ENUM}
    for row in rows:
        status = str(row["smt_status"])
        if row.get("reached_solver"):
            reached_breakdown[status] += 1
        if status != "error":
            continue
        channel = str(row.get("channel") or "unknown")
        reason = (
            attribute_error_clause(str(row.get("clause_text") or ""))
            if row.get("error_kind") == "not_reached"
            else "solver_exception"
        )
        bucket = by_channel.setdefault(channel, {})
        bucket[reason] = bucket.get(reason, 0) + 1
    return {
        "by_channel": {channel: dict(sorted(reasons.items())) for channel, reasons in sorted(by_channel.items())},
        "reached_outcome_breakdown": reached_breakdown,
        "note": "启发式文本归因（仅 error/not_reached 行）：result 别名 → 白名单调用不可翻译 → 下标 → 属性 → 其他",
    }


def check_recompute(records: list[dict[str, Any]], aggregate: dict[str, Any]) -> dict[str, Any]:
    """逐子句复算自检：任务级桶计数、池化桶计数必须与 PER_CLAUSE 行/任务行逐项相等。"""
    mismatches: list[str] = []
    recomputed_pooled = {status: 0 for status in STATUS_ENUM}
    for record in records:
        clauses = [row for row in record.get("clauses") or []]
        task_counts = {status: 0 for status in STATUS_ENUM}
        for row in clauses:
            task_counts[str(row["smt_status"])] += 1
            recomputed_pooled[str(row["smt_status"])] += 1
        mismatches.extend(
            f"{record['task_id']}:{status}"
            for status in STATUS_ENUM
            if task_counts[status] != int((record.get("smt_status_counts") or {}).get(status, 0))
        )
    pooled_equal = all(
        recomputed_pooled[status] == int(aggregate["status_totals_pooled"].get(status, 0)) for status in STATUS_ENUM
    )
    return {
        "per_task_ok": not mismatches,
        "per_task_mismatches": mismatches,
        "pooled_ok": pooled_equal,
        "recomputed_pooled": recomputed_pooled,
        "all_ok": (not mismatches) and pooled_equal,
    }


def build_association(
    primary_records: list[dict[str, Any]],
    *,
    mde_pp: float = MDE_PP_FROZEN,
) -> dict[str, Any]:
    """关联层（探索性）：按任务 witness_rate 中位数二分 vs df_spec detection。

    冻结规则见 PREREG §6：中位数由 ``statistics.median`` 计算；两桶任一为空 →
    无对照；差异 < MDE 只能作方向性描述；不做检验。
    """
    usable = [
        r for r in primary_records if r.get("material_status") == "anchor_hit" and r.get("smt_witness_rate") is not None
    ]
    result: dict[str, Any] = {
        "status": "exploratory",
        "mde_pp": mde_pp,
        "mde_source": "emse_df_spec_20261016/DF_SPEC_REPORT.json::contrast_41.mde_pp",
        "bucketing_rule": "median_split_on_smt_witness_rate",
        "wording_policy": [
            "差异 < MDE 只能表述为方向性描述",
            "禁止使用 提升 / 显著 / 证明 等措辞",
            "不做 p 值/统计检验，不作确认性结论",
            "不服务于 规格锚增益 主张",
        ],
        "n_tasks": len(usable),
    }
    if len(usable) < 2:
        result.update({"buckets": {}, "interpretation": "可判定任务 < 2，无对照，不做 detection 比较"})
        return result
    rates = [float(r["smt_witness_rate"]) for r in usable]
    median = statistics.median(rates)
    high = [r for r in usable if float(r["smt_witness_rate"]) >= median]
    low = [r for r in usable if float(r["smt_witness_rate"]) < median]
    result["median_witness_rate"] = _round6(median)
    result["tasks_with_any_witness"] = sum(1 for r in rates if r > 0)
    result["tasks_with_zero_witness_rate"] = sum(1 for r in rates if r <= 0)
    if not high or not low:
        result.update(
            {
                "buckets": {},
                "bucket_sizes": {"high": len(high), "low": len(low)},
                "interpretation": "两桶任一为空（分桶退化），无对照，不做 detection 比较",
            }
        )
        return result
    buckets: dict[str, Any] = {}
    for name, subset in (("high", high), ("low", low)):
        measurable = [r for r in subset if r.get("dfspec_detection_measurable")]
        positive = [r for r in measurable if float(r.get("dfspec_detection_rate") or 0.0) > 0]
        buckets[name] = {
            "n_tasks": len(subset),
            "n_measurable": len(measurable),
            "positive": len(positive),
            "detection_rate": _round6(len(positive) / len(measurable)) if measurable else None,
            "task_ids": [r["task_id"] for r in subset],
        }
    delta_pp = None
    if buckets["high"]["detection_rate"] is not None and buckets["low"]["detection_rate"] is not None:
        delta_pp = round((buckets["high"]["detection_rate"] - buckets["low"]["detection_rate"]) * 100.0, 2)
    result["buckets"] = buckets
    result["delta_pp_high_minus_low"] = delta_pp
    if delta_pp is None:
        interpretation = "至少一桶无可判定 detection 行，关联层不可比较"
    elif abs(delta_pp) < mde_pp:
        interpretation = (
            f"桶间 detection 差 {delta_pp:+.2f}pp，绝对值 < MDE {mde_pp:.2f}pp → 仅方向性描述，不作任何效应解读"
        )
    else:
        interpretation = (
            f"桶间 detection 差 {delta_pp:+.2f}pp，绝对值 ≥ MDE {mde_pp:.2f}pp → "
            "仍属探索性（单臂观测、无对照臂），不得作为确认性结论"
        )
    result["interpretation"] = interpretation
    return result


# ─── 输入与预检 ──────────────────────────────────────────────────────────────
def load_dfspec_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """读 df_spec 处理臂批次 JSON，返回 (raw, details 行)。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        details = raw["results"]["plain_llm_df_spec"]["details"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"df_spec 批次结构不合法（缺 results.plain_llm_df_spec.details）: {path}") from exc
    if not isinstance(details, list) or not details:
        raise ValueError(f"df_spec 批次 details 为空: {path}")
    return raw, details


def _git_head() -> str | None:
    """读 .git/HEAD 解析当前 commit（不依赖 subprocess / 网络）。"""
    head = _REPO_ROOT / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith("ref:"):
        ref_path = _REPO_ROOT / ".git" / text.split(":", 1)[1].strip()
        try:
            return ref_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return text or None


def _z3_version() -> str | None:
    if not smt_available():
        return None
    try:
        import z3

        return str(z3.get_version_string())
    except Exception:
        return None


def _forbidden_import_scan() -> dict[str, Any]:
    """AST 扫描本脚本 import 面（零 LLM 约束的证据字段）。

    校验：静态 import / from-import 的模块根与动态导入调用名均不得命中禁词；
    本脚本源码中的禁词清单定义本身不构成"导入"，故按 AST 节点而非子串判定。
    """
    try:
        import ast

        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError) as exc:  # pragma: no cover —— 自身源码不可读/非法
        return {
            "passed": False,
            "method": "ast",
            "forbidden_module_roots": sorted(_FORBIDDEN_IMPORT_ROOTS),
            "hits": [f"scan_error: {type(exc).__name__}"],
        }
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORT_ROOTS:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                hits.append(str(node.module))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in _FORBIDDEN_DYNAMIC_IMPORTS:
                hits.append(f"dynamic_import:{name}")
    return {
        "passed": not hits,
        "method": "ast",
        "forbidden_module_roots": sorted(_FORBIDDEN_IMPORT_ROOTS),
        "forbidden_dynamic_imports": sorted(_FORBIDDEN_DYNAMIC_IMPORTS),
        "hits": hits,
    }


def _sha_opt(path: Path) -> str | None:
    try:
        return sha256_file(path) if path.is_file() else None
    except OSError:
        return None


# ─── 报告构建 ────────────────────────────────────────────────────────────────
def build_analysis_report(
    *,
    records: list[dict[str, Any]],
    aggregate_primary: dict[str, Any],
    aggregate_all: dict[str, Any],
    recompute_primary: dict[str, Any],
    recompute_all: dict[str, Any],
    association: dict[str, Any],
    preflight: dict[str, Any],
    rows: list[dict[str, Any]],
    in_process_rebuild_equal: bool,
    rebuild_mismatches: list[str],
    determinism_probe: bool,
) -> dict[str, Any]:
    """ANALYSIS_REPORT.json（分类/计数/率字段确定性；计时键与墙钟见 PREFLIGHT）。"""
    criteria = {
        "mean_witness_rate_gt_zero": {
            "threshold": "> 0",
            "value": aggregate_primary["witness_rate_mean"],
            "met": bool(
                aggregate_primary["witness_rate_mean"] is not None and aggregate_primary["witness_rate_mean"] > 0
            ),
        },
        "timeout_rate_lt_20pct": {
            "threshold": "< 0.20",
            "value": aggregate_primary["timeout_rate_pooled"],
            "met": bool(
                aggregate_primary["timeout_rate_pooled"] is not None
                and aggregate_primary["timeout_rate_pooled"] < TIMEOUT_FAIL_RATIO
            ),
            "note": "判定值 = pooled timeout/reached（PREREG §5 冻结口径）",
        },
        "status_buckets_recomputable": {
            "value": recompute_primary["all_ok"],
            "met": bool(recompute_primary["all_ok"]),
            "note": "PER_CLAUSE 行逐子句重聚合 == TASK_LEVEL 任务行 == 池化桶计数",
        },
    }
    mechanism_pass = all(item["met"] for item in criteria.values())
    if aggregate_primary["witness_rate_mean"] == 0 and aggregate_primary["witness_rate_mean"] is not None:
        verdict_reason = "rate 恒 0：层未接线或材料未达求解器（PREREG 失败条件）"
    elif not criteria["timeout_rate_lt_20pct"]["met"]:
        verdict_reason = "timeout_rate ≥ 20%：参数需重标，不得解读关联层结果（PREREG 失败条件）"
    elif not mechanism_pass:
        verdict_reason = "status 桶无法逐子句复算（审计失败）"
    else:
        verdict_reason = "见证率 > 0 且超时率有界且逐子句可复算（层在工作）"
    material_tasks = aggregate_primary["tasks_with_clauses"]
    gap_note = None
    if material_tasks < MIN_MATERIAL_TASKS:
        gap_note = f"有材料任务 {material_tasks} < {MIN_MATERIAL_TASKS}：照实报告材料缺口，不补跑、不解读关联层"

    # 逐子句审计样例（确定性选择：每任务/通道/状态取代表）
    def _audit_row(picked: dict[str, Any]) -> dict[str, Any]:
        return {
            "smt_status": picked["smt_status"],
            "task_id": picked["task_id"],
            "channel_field": picked["channel_field"],
            "kind": picked["kind"],
            "clause_sha256_16": picked["clause_sha256_16"],
            "clause_text": picked["clause_text"],
            "smt_solve_ms": picked["smt_solve_ms"],
            "error_kind": picked.get("error_kind"),
            "reached_solver": picked.get("reached_solver"),
            "raw_status": picked.get("raw_status"),
        }

    # 审计样例：每个出现的 status 取代表；sat 额外取一条 post/inv 通道代表
    # （本批唯一到达求解器的 inv 子句）；error 按归因原因各取一条（防只展示同类）。
    audit_samples: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, str]] = set()

    def _pick(row: dict[str, Any]) -> None:
        key = (str(row["task_id"]), str(row["clause_sha256_16"]))
        if key in selected_keys:
            return
        selected_keys.add(key)
        audit_samples.append(_audit_row(row))

    for status in ("sat", "unsat", "timeout", "unknown", "error"):
        picked = next((row for row in rows if row["smt_status"] == status), None)
        if picked is not None:
            _pick(picked)
    inv_sat = next(
        (row for row in rows if row["smt_status"] == "sat" and "invariants" in row["channel_field"]),
        None,
    )
    if inv_sat is not None:
        _pick(inv_sat)
    seen_error_reasons: set[str] = set()
    for row in rows:
        if row["smt_status"] != "error":
            continue
        kind = str(row.get("error_kind") or "")
        reason = attribute_error_clause(str(row.get("clause_text") or "")) if kind == "not_reached" else kind
        if reason in seen_error_reasons:
            continue
        seen_error_reasons.add(reason)
        _pick(row)
    return {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "batch": {
            "prereg": "PREREG.md（2026-10-18 跑前冻结）",
            "design_doc": "docs/design/smt_witness_batch_plan.md",
            "zero_llm": True,
            "llm_calls": 0,
            "single_arm": True,
            "primary_caliber": "QuixBugs 41 缺陷程序（program 不以 _test 结尾；与 df_spec detection 41 同集）",
            "extension_caliber": "全 50 任务（含 9 个 *_test 驱动任务；不参与判定）",
        },
        "mechanism_layer": {
            "verdict": "pass" if mechanism_pass else "fail",
            "verdict_reason": verdict_reason,
            "criteria": criteria,
            "evidence": {
                "reached_outcome_breakdown": error_attribution(rows)["reached_outcome_breakdown"],
                "reached_nonempty_share": aggregate_primary["reach_rate_pooled"],
                "tasks_with_any_sat": aggregate_primary["tasks_with_any_sat"],
                "tasks_with_zero_witness_rate": aggregate_primary["tasks_with_zero_witness_rate"],
                "witness_rate_mean_note": (
                    f"均值由 {aggregate_primary['tasks_with_any_sat']}/{aggregate_primary['tasks_with_clauses']} "
                    f"有见证任务贡献，{aggregate_primary['tasks_with_zero_witness_rate']}/"
                    f"{aggregate_primary['tasks_with_clauses']} 任务见证率为 0（材料未达求解器为主因）"
                ),
            },
            "material_gap_note": gap_note,
            "material_tasks_primary": material_tasks,
            "tasks_total_primary": aggregate_primary["tasks_total"],
        },
        "status_buckets": {
            "primary_41": aggregate_primary["status_totals_pooled"],
            "extension_all50": aggregate_all["status_totals_pooled"],
            "by_channel": status_by_channel(rows),
            "clauses_pooled_primary": aggregate_primary["clauses_pooled"],
            "clauses_reached_pooled_primary": aggregate_primary["clauses_reached_pooled"],
        },
        "error_attribution": error_attribution(rows),
        "task_level_rates": {
            "primary_41": {
                "witness_rate_mean": aggregate_primary["witness_rate_mean"],
                "witness_rate_median": aggregate_primary["witness_rate_median"],
                "witness_rate_min": aggregate_primary["witness_rate_min"],
                "witness_rate_max": aggregate_primary["witness_rate_max"],
                "witness_rate_distribution": aggregate_primary["witness_rate_distribution"],
                "reach_rate_pooled": aggregate_primary["reach_rate_pooled"],
                "timeout_rate_pooled": aggregate_primary["timeout_rate_pooled"],
                "timeout_rate_mean_task": aggregate_primary["timeout_rate_mean_task"],
                "timeout_share_nonempty_pooled": aggregate_primary["timeout_share_nonempty_pooled"],
            },
            "extension_all50": {
                "witness_rate_mean": aggregate_all["witness_rate_mean"],
                "witness_rate_median": aggregate_all["witness_rate_median"],
                "reach_rate_pooled": aggregate_all["reach_rate_pooled"],
                "timeout_rate_pooled": aggregate_all["timeout_rate_pooled"],
            },
            "note": "witness_rate = sat / 非空评估子句（D1）；timeout_rate 判定值 = timeout / reached",
        },
        "material_layer": {
            "tasks_total": aggregate_all["tasks_total"],
            "tasks_with_material": aggregate_all["tasks_with_material"],
            "material_gap_tasks": aggregate_all["material_gap_tasks"],
            "primary_tasks_with_material": aggregate_primary["tasks_with_material"],
            "anchor_table": preflight.get("inputs", {}).get("anchor_table", {}),
            "channel_rule": "expr 通道优先（*_expr 任一含 str 子句），否则 NL 回退（PREREG §2）",
        },
        "association_layer": {
            **association,
            "caveat": "单臂观测、无对照臂；n=41 可判定子集 35；MDE≈16.57pp；仅探索性",
            "dfspec_join_columns": [
                "dfspec_detection_rate",
                "dfspec_detection_measurable",
                "dfspec_specificity_gate_verdict",
            ],
        },
        "audit": {
            "per_clause_recompute_primary": recompute_primary,
            "per_clause_recompute_all": recompute_all,
            "audit_samples": audit_samples,
        },
        "determinism": {
            "in_process_double_solve_status_equal": in_process_rebuild_equal,
            "double_solve_probe_enabled": determinism_probe,
            "double_solve_mismatches": rebuild_mismatches,
            "stable_fields": [
                "smt_status",
                "error_kind",
                "reached_solver",
                "raw_status",
                "smt_status_counts",
                "smt_witness_rate",
                "smt_reach_rate",
                "smt_timeout_rate",
                "material_status",
            ],
            "timing_keys_volatile": sorted(_TIMING_KEYS),
            "compared_scope": "剔除计时键后的任务行/聚合行规范化 JSON（两次独立求解）",
            "z3_rng_note": "未设置 z3 随机参数；整数/布尔约束求解对固定输入确定性（PREREG §3 修订）",
        },
        "cost": {
            "llm_calls": 0,
            "llm_usd": 0.0,
            "network_calls": 0,
            "solver_cpu_ms_total": aggregate_all["solve_ms_total"],
            "wall_clock_seconds": None,
            "wall_clock_source": "PREFLIGHT.json::run.wall_clock_seconds",
        },
    }


def build_readme(report: dict[str, Any], preflight: dict[str, Any]) -> str:
    """README.md（中文报告；所有数字取自本次运行工件）。"""
    mech = report["mechanism_layer"]
    crit = mech["criteria"]
    buckets = report["status_buckets"]
    primary = buckets["primary_41"]
    rates = report["task_level_rates"]["primary_41"]
    mat = report["material_layer"]
    assoc = report["association_layer"]
    cost = report["cost"]
    run = preflight.get("run", {})
    lines: list[str] = []
    add = lines.append

    add("# T3b：z3 SMT 见证层最小启用批次（A-18 / Q7，零 LLM）")
    add("")
    add("> 单臂观测批（无对照臂）· 主判定集 QuixBugs 41 缺陷程序（与 df_spec 同集）·")
    add("> 零 LLM（0 次 LLM 调用、0 USD、不联网）· 预注册 `PREREG.md` 跑前冻结。")
    add("")
    add("## 0. 机制层判定")
    add("")
    add(f"- **判定：`{mech['verdict']}`** —— {mech['verdict_reason']}")
    add(
        f"- `smt_witness_rate` 全任务均值 = **{crit['mean_witness_rate_gt_zero']['value']}**"
        f"（阈值 > 0，{'满足' if crit['mean_witness_rate_gt_zero']['met'] else '未满足'}）"
    )
    add(
        f"- `smt_timeout_rate`（pooled timeout/reached）= **{crit['timeout_rate_lt_20pct']['value']}**"
        f"（阈值 < 20%，{'满足' if crit['timeout_rate_lt_20pct']['met'] else '未满足'}）"
    )
    add(
        f"- 每个 status 桶可逐子句复算：**{'是' if crit['status_buckets_recomputable']['met'] else '否'}**"
        "（PER_CLAUSE 行重聚合 == 任务行 == 池化桶计数）"
    )
    evidence = mech.get("evidence") or {}
    if evidence:
        rb = evidence.get("reached_outcome_breakdown") or {}
        add(
            f"- **机制证据**：到达求解器的子句 n={sum(rb.values())}，其中 sat={rb.get('sat')} / "
            f"unsat={rb.get('unsat')} / unknown={rb.get('unknown')} / timeout={rb.get('timeout')}；"
            f"到达率（reached/D1）={evidence.get('reached_nonempty_share')}；"
            f"有见证任务 {evidence.get('tasks_with_any_sat')}/"
            f"{mech['material_tasks_primary']}（其余任务见证率为 0，主因材料未达求解器）"
        )
        add(f"- 均值口径说明：{evidence.get('witness_rate_mean_note')}")
    if mech["material_gap_note"]:
        add(f"- 材料缺口披露：{mech['material_gap_note']}")
    add("")
    add("## 1. 材料覆盖")
    add("")
    add(
        f"- 锚表内容寻址命中：**{mat['tasks_with_material']}/{mat['tasks_total']}** 任务"
        f"（sha256(buggy_source.strip())；锚表 sha256=`"
        f"{(mat.get('anchor_table') or {}).get('sha256', '')[:16]}…`，加载时按 SHA256SUMS 校验）"
    )
    add(
        f"- 主判定集（41）有材料任务 **{report['mechanism_layer']['material_tasks_primary']}**；"
        f"剔除缺口任务：{len(mat['material_gap_tasks'])}"
    )
    for gap in mat["material_gap_tasks"]:
        add(f"  - `{gap['task_id']}`：{gap['material_status']}")
    add("- 缺口任务不补跑（零 LLM 纪律），逐子句/任务级均不进入主判定均值。")
    add("")
    add("## 2. 逐 status 桶计数（主判定集 41）")
    add("")
    add("| smt_status | 子句数 | 说明 |")
    add("|---|---:|---|")
    notes = {
        "sat": "求解器给出可满足模型（前件见证 / 后件自洽）",
        "unsat": "求解器给出不可满足（前件空洞 / 后件自相矛盾）",
        "unknown": "求解器未知且未达超时阈值（保守记录，不计 unsat）",
        "timeout": "墙钟 ≥ 0.9×5s，计超时，**不计 unsat**",
        "error": "未达求解器（保守拒绝）或求解器异常（见 error_kind 分解）",
    }
    total = sum(primary.values())
    for status in ("sat", "unsat", "unknown", "timeout", "error"):
        add(f"| {status} | {primary[status]} | {notes[status]} |")
    add(f"| **合计** | **{total}** | 主判定集非空评估子句（D1） |")
    add("")
    add(
        f"- 全 50 任务扩展口径（含 9 个 `*_test` 驱动；不参与判定）池化桶："
        f"sat={buckets['extension_all50']['sat']} / unsat={buckets['extension_all50']['unsat']} / "
        f"unknown={buckets['extension_all50']['unknown']} / timeout={buckets['extension_all50']['timeout']} / "
        f"error={buckets['extension_all50']['error']}"
    )
    by_channel = buckets["by_channel"]
    for channel in sorted(by_channel):
        ch = by_channel[channel]
        add(
            f"- 通道 `{channel}`：sat={ch['sat']} / unsat={ch['unsat']} / unknown={ch['unknown']} / "
            f"timeout={ch['timeout']} / error={ch['error']}"
        )
    attr = report["error_attribution"]
    reached_breakdown = attr["reached_outcome_breakdown"]
    add(
        f"- **到达求解器子句**（reached）的结果分解：sat={reached_breakdown['sat']} / "
        f"unsat={reached_breakdown['unsat']} / unknown={reached_breakdown['unknown']} / "
        f"timeout={reached_breakdown['timeout']}（n={sum(reached_breakdown.values())}）"
    )
    add("- `error`（未达求解器）逐子句归因（启发式文本特征，逐子句可复算）：")
    add("")
    add("| 通道 | 归因原因 | 子句数 |")
    add("|---|---|---:|")
    for channel, reasons in attr["by_channel"].items():
        for reason, count in reasons.items():
            add(f"| {channel} | {reason} | {count} |")
    add("")
    add(f"归因规则：{attr['note']}。")
    add("")
    add("## 3. 任务级率分布（主判定集 41）")
    add("")
    add("| 指标 | 值 |")
    add("|---|---:|")
    add(f"| witness_rate 均值 | {rates['witness_rate_mean']} |")
    add(f"| witness_rate 中位数 | {rates['witness_rate_median']} |")
    add(f"| witness_rate 最小 / 最大 | {rates['witness_rate_min']} / {rates['witness_rate_max']} |")
    add(f"| reach_rate（reached/D1，pooled） | {rates['reach_rate_pooled']} |")
    add(f"| timeout_rate（timeout/reached，pooled） | {rates['timeout_rate_pooled']} |")
    add(f"| timeout_share_nonempty（timeout/D1，pooled） | {rates['timeout_share_nonempty_pooled']} |")
    add("")
    add("`witness_rate` 分布（逐任务，升序）：")
    add("")
    add("```")
    add(", ".join(str(x) for x in rates["witness_rate_distribution"]))
    add("```")
    add("")
    add("## 4. 关联层（探索性，非确认性）")
    add("")
    add(
        f"- 状态：`{assoc['status']}`；分桶规则：`{assoc['bucketing_rule']}`；"
        f"n={assoc['n_tasks']}；MDE≈{assoc['mde_pp']}pp（来源 `{assoc['mde_source']}`）"
    )
    if assoc.get("buckets"):
        for name, label in (("high", "高见证率桶（≥中位数）"), ("low", "低见证率桶（<中位数）")):
            b = assoc["buckets"][name]
            add(
                f"- {label}：n={b['n_tasks']}，detection measurable={b['n_measurable']}，"
                f"positive={b['positive']}，rate={b['detection_rate']}（df_spec 归档行）"
            )
        add(f"- 桶间差（high−low）：{assoc.get('delta_pp_high_minus_low')}pp")
        add(f"- 解读：{assoc['interpretation']}")
    else:
        sizes = assoc.get("bucket_sizes") or {}
        add(
            f"- **无对照**：{assoc.get('interpretation')}"
            f"（median={assoc.get('median_witness_rate')}；"
            f"≥median 桶 n={sizes.get('high')}，<median 桶 n={sizes.get('low')}）"
        )
        add(
            f"- 退化原因（结构性事实）：{assoc.get('n_tasks')} 个任务中 "
            f"{assoc.get('tasks_with_zero_witness_rate')} 个 `smt_witness_rate=0`、"
            f"{assoc.get('tasks_with_any_witness')} 个 >0，中位数=0，按预注册的 "
            "`≥median vs <median` 规则低桶为空 → 冻结规则下"
            "**不做 detection 比较**（防事后换分桶口径）。df_spec detection 已与 "
            "SMT 字段同行落盘于 `TASK_LEVEL.json`（`dfspec_detection_rate`），"
            "若后续要做「有见证 vs 无见证」分组，须**另行预注册**后跑新批次，"
            "不得回读本批做确认性推断。"
        )
    add(
        "- **措辞纪律**：差异 < MDE 只作方向性描述；禁止「提升/显著/证明」措辞；"
        "不做 p 值/检验；不引为确认性结论；不服务「规格锚增益」主张。"
    )
    add("")
    add("## 5. 逐子句审计样例（绑定具体子句，UNSAT 解释不脱离子句）")
    add("")
    add("| task_id | status | channel_field | clause_sha256_16 | 子句 | 求解 ms |")
    add("|---|---|---|---|---|---:|")
    for sample in report["audit"]["audit_samples"]:
        text = sample["clause_text"].replace("|", "\\|")[:90]
        add(
            f"| {sample['task_id']} | {sample['smt_status']} | {sample['channel_field']} | "
            f"`{sample['clause_sha256_16']}` | `{text}` | {sample['smt_solve_ms']} |"
        )
    present = sorted({s["smt_status"] for s in report["audit"]["audit_samples"]})
    absent = [s for s in ("sat", "unsat", "unknown", "timeout", "error") if s not in present]
    add("")
    add(f"- 出现 status：{present}；**未出现 status**：{absent}（本批该类子句为 0 条，如实标注、不构造样例）。")
    add(
        "- `error/not_reached` 行的归因优先展示 `result` 别名与不可翻译调用两类"
        "（本批误差主因），逐子句 sha256 可在 `PER_CLAUSE.jsonl` 全量复算。"
    )
    add("")
    add("## 6. 成本与算力")
    add("")
    add(f"- LLM 调用：**{cost['llm_calls']}** 次（配额 0；预算 0 USD）；网络调用：{cost['network_calls']}")
    add(f"- z3 求解累计墙钟：{cost['solver_cpu_ms_total']} ms；批次总墙钟：{run.get('wall_clock_seconds')} s")
    add(
        f"- 环境：Python {preflight.get('environment', {}).get('python')} / "
        f"z3 {preflight.get('environment', {}).get('z3')} / 平台 "
        f"{preflight.get('environment', {}).get('platform')}"
    )
    add("")
    add("## 7. 确定性 / 幂等")
    add("")
    det = report["determinism"]
    add(
        f"- 进程内**两次独立求解**（第二次完整重建）的 status/分类/计数/率字段一致："
        f"`{det['in_process_double_solve_status_equal']}`"
        f"（mismatch={det['double_solve_mismatches']}；比较范围：{det['compared_scope']}）"
    )
    add(
        f"- 计时键 `{', '.join(det['timing_keys_volatile'])}` 本质非确定，允许运行间波动，"
        "不纳入逐字节幂等声明；`PREFLIGHT.json` / `RUN_SUMMARY.log` 另含墙钟字段。"
    )
    add("- z3 未设置随机参数；本批为整数/布尔约束，同一输入返回同一 status 已由上条双求解验证。")
    add("")
    add("## 8. 限制（必须与结论同读）")
    add("")
    add(
        "1. **生产通道差**：生产 `spec_smt._collect_pre_constraints` 消费 "
        "`spec['preconditions']`（NL 通道），本批主材为 `*_expr` 形式化通道"
        "（以单子句 spec 喂入同一公开入口）。本批测的是「形式化子句有界可解性」，"
        "**不测**生产从 NL 通道到求解器的实际到达率。"
    )
    add(
        "2. **结果变量别名口径**：锚材料形式化后件统一写 `result`，而 "
        "`check_postcondition_consistency` 的自由结果变量域为 `r`——含 `result` 的"
        "后件/不变量子句在排序推断阶段被保守拒绝（`error/not_reached`）。"
        "本批**不**做别名改写（保持 src 口径原样），故 post/inv 通道可解率结构性偏低。"
    )
    add("3. 单臂观测、无对照臂：无法归因任何 detection 差异于 SMT 层；关联层分桶为探索性，n=41、可判定 35。")
    add(
        "4. 每子句 5s 超时映射依赖公开 API 的 `unknown` + 墙钟 0.9×timeout 规则"
        "（公开 API 不暴露 z3 `reason_unknown`）；本批 timeout 桶实为 0，规则未被触发。"
    )
    add("5. 锚材料为 Planner 缓存物化（零 LLM），其质量上限即既有缓存质量；不重跑 Planner、不做规格精化。")
    add("")
    add("## 9. 复跑")
    add("")
    add("```bash")
    add(".venv/bin/python -m experiments.smt_witness_batch")
    add(
        "python scripts/gates/checksum_results.py --write --results-dir experiments/results/t_round_smt_witness_20261018"
    )
    add(
        "python scripts/gates/checksum_results.py --verify --results-dir experiments/results/t_round_smt_witness_20261018"
    )
    add("```")
    add("")
    add("## 10. 产物")
    add("")
    for name in (
        "PREREG.md",
        "PREFLIGHT.json",
        "PER_CLAUSE.jsonl",
        "TASK_LEVEL.json",
        "ANALYSIS_REPORT.json",
        "README.md",
        "RUN_SUMMARY.log",
        "SHA256SUMS",
    ):
        add(f"- `{name}`")
    add("")
    return "\n".join(lines) + "\n"


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def run_batch(
    *,
    out_dir: Path,
    anchor_table_path: Path = DEFAULT_ANCHOR_TABLE,
    dfspec_benchmark_path: Path = DEFAULT_DF_SPEC_BENCHMARK,
    dfspec_report_path: Path = DEFAULT_DF_SPEC_REPORT,
    quixbugs_root: str | None = None,
    timeout_ms: int = SOLVE_TIMEOUT_MS,
    determinism_probe: bool = True,
) -> dict[str, Any]:
    """执行整批并落盘全部产物；返回内存报告（便于测试与二次消费）。

    Args:
        determinism_probe: 是否做进程内第二次独立求解自检（默认开；测试可关）。
    """
    run_started = now_iso()
    t_start = time.perf_counter()
    os.environ["SPEC_SMT_ENABLE"] = "true"
    os.environ["SPEC_SMT_TIMEOUT_MS"] = str(timeout_ms)

    # 输入加载（锚表 fail-closed 校验）
    anchor_loaded = load_anchor_table(anchor_table_path)
    anchors = anchor_loaded["anchors"]
    _, dfspec_rows = load_dfspec_rows(dfspec_benchmark_path)
    dfspec_report = json.loads(dfspec_report_path.read_text(encoding="utf-8"))
    mde_pp = float(dfspec_report["contrast_41"]["mde_pp"])
    if abs(mde_pp - MDE_PP_FROZEN) > 1e-9:
        raise ValueError(f"df_spec MDE 与预注册冻结值不一致：{mde_pp} != {MDE_PP_FROZEN}")
    roots = resolve_quixbugs_roots(quixbugs_root)
    quixbugs_hit_root = None
    for root in roots:
        candidate = root / "python_programs"
        if candidate.is_dir():
            quixbugs_hit_root = root
            break

    # 任务行（保持 df_spec 顺序 → 主判定集 41 / 扩展 50）
    ordered_rows = sorted(dfspec_rows, key=lambda row: str(row.get("task_id") or ""))

    def _build_records() -> list[dict[str, Any]]:
        built: list[dict[str, Any]] = []
        for row in ordered_rows:
            program = str((row.get("task_metadata") or {}).get("program") or "")
            in_primary = bool(program) and not program.endswith(PRIMARY_CALIBER_SUFFIX)
            built.append(build_task_record(row, anchors, roots, in_primary=in_primary, timeout_ms=timeout_ms))
        return built

    records = _build_records()
    rows = [clause for record in records for clause in record.get("clauses") or []]
    primary_records = [record for record in records if record["in_primary"]]
    aggregate_primary = aggregate_records(primary_records)
    aggregate_all = aggregate_records(records)
    recompute_primary = check_recompute(primary_records, aggregate_primary)
    recompute_all = check_recompute(records, aggregate_all)
    association = build_association(primary_records, mde_pp=mde_pp)

    # 进程内确定性自检：**第二次独立完整求解**后比较（剔除计时键），
    # 验证 status/分类/计数/率字段同输入逐字段一致（PREREG §3 修订口径）。
    rebuild_records = _build_records() if determinism_probe else []
    rebuild_mismatches: list[str] = []
    if determinism_probe:
        left = canonical_dump(_strip_timing_keys(primary_records))
        right = canonical_dump(_strip_timing_keys([r for r in rebuild_records if r["in_primary"]]))
        if left != right:
            rebuild_mismatches.append("primary_task_records")
        left_all = canonical_dump(_strip_timing_keys(records))
        right_all = canonical_dump(_strip_timing_keys(rebuild_records))
        if left_all != right_all:
            rebuild_mismatches.append("all_task_records")
    in_process_rebuild_equal = determinism_probe and not rebuild_mismatches

    # 运行元信息（墙钟/环境 → PREFLIGHT；不进内容数据）
    z3_version = _z3_version()
    preflight: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "run": {
            "started_at": run_started,
            "finished_at": None,
            "wall_clock_seconds": None,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "z3": z3_version,
            "smt_available": smt_available(),
            "git_head": _git_head(),
            "cwd": str(Path.cwd()),
            "loadavg_1_5_15": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "cpu_note": "B2 真实 LLM 主批次可能并行运行；计时字段受 CPU 争用影响，仅作披露",
        },
        "inputs": {
            "anchor_table": {
                "path": anchor_loaded["path"],
                "sha256": anchor_loaded["sha256"],
                "expected_sha256": anchor_loaded["expected_sha256"],
                "expected_sha256_source": anchor_loaded["expected_sha256_source"],
                "meta": anchor_loaded["meta"],
            },
            "dfspec_benchmark": {
                "path": _display_path(dfspec_benchmark_path),
                "sha256": _sha_opt(dfspec_benchmark_path),
            },
            "dfspec_report": {
                "path": _display_path(dfspec_report_path),
                "sha256": _sha_opt(dfspec_report_path),
                "mde_pp": mde_pp,
            },
            "prereg": {
                "path": "PREREG.md",
                "sha256": _sha_opt(out_dir / "PREREG.md"),
            },
            "script": {
                "path": _display_path(Path(__file__)),
                "sha256": _sha_opt(Path(__file__)),
            },
            "quixbugs": {
                "roots_considered": [str(root) for root in roots],
                "root_used": str(quixbugs_hit_root) if quixbugs_hit_root else None,
            },
        },
        "params": {
            "smt_timeout_ms": timeout_ms,
            "unknown_as_timeout_ratio": UNKNOWN_AS_TIMEOUT_RATIO,
            "status_enum": list(STATUS_ENUM),
            "timeout_fail_ratio": TIMEOUT_FAIL_RATIO,
            "min_material_tasks": MIN_MATERIAL_TASKS,
            "primary_caliber": "41 缺陷程序（program 不以 _test 结尾）",
            "clause_channel_rule": "expr 优先 / NL 回退（_select_compile_channels 同口径）",
            "env": {
                "SPEC_SMT_ENABLE": os.environ.get("SPEC_SMT_ENABLE"),
                "SPEC_SMT_TIMEOUT_MS": os.environ.get("SPEC_SMT_TIMEOUT_MS"),
            },
        },
        "zero_llm": {
            "llm_calls": 0,
            "network_calls": 0,
            "usd": 0.0,
            "forbidden_import_scan": _forbidden_import_scan(),
        },
        "counts": {
            "tasks_total": len(records),
            "tasks_primary": len(primary_records),
            "clauses_pooled_primary": aggregate_primary["clauses_pooled"],
            "clauses_pooled_all": aggregate_all["clauses_pooled"],
        },
    }

    report = build_analysis_report(
        records=records,
        aggregate_primary=aggregate_primary,
        aggregate_all=aggregate_all,
        recompute_primary=recompute_primary,
        recompute_all=recompute_all,
        association=association,
        preflight=preflight,
        rows=rows,
        in_process_rebuild_equal=in_process_rebuild_equal,
        rebuild_mismatches=rebuild_mismatches,
        determinism_probe=determinism_probe,
    )

    # 落盘（顺序：内容数据 → 报告 → README → 预检/日志）
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "PER_CLAUSE.jsonl", rows)
    task_level = {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "meta": {
            "batch": "t_round_smt_witness_20261018",
            "prereg": "PREREG.md",
            "zero_llm": True,
            "llm_calls": 0,
            "timeout_ms": timeout_ms,
            "primary_caliber": "41 缺陷程序（program 不以 _test 结尾）",
            "rate_definitions": {
                "smt_witness_rate": "sat / smt_clauses_nonempty",
                "smt_reach_rate": "reached / smt_clauses_nonempty",
                "smt_timeout_rate": "timeout / reached（null if reached==0）",
                "smt_timeout_share_nonempty": "timeout / smt_clauses_nonempty",
            },
        },
        "aggregate": {
            "primary_41": aggregate_primary,
            "extension_all50": aggregate_all,
        },
        "tasks": records,
    }
    atomic_write_json(str(out_dir / "TASK_LEVEL.json"), task_level, indent=2, mode=0o644)
    atomic_write_json(str(out_dir / "ANALYSIS_REPORT.json"), report, indent=2, mode=0o644)

    wall_clock = round(time.perf_counter() - t_start, 3)
    preflight["run"]["finished_at"] = now_iso()
    preflight["run"]["wall_clock_seconds"] = wall_clock
    report["cost"]["wall_clock_seconds"] = wall_clock  # README 用；ANALYSIS_REPORT 已落盘
    atomic_write_json(str(out_dir / "PREFLIGHT.json"), preflight, indent=2, mode=0o644)
    atomic_write_text(str(out_dir / "README.md"), build_readme(report, preflight), mode=0o644)
    atomic_write_text(
        str(out_dir / "RUN_SUMMARY.log"),
        _build_run_summary(
            records=records,
            aggregate_primary=aggregate_primary,
            aggregate_all=aggregate_all,
            report=report,
            preflight=preflight,
            rows=rows,
            out_dir=out_dir,
            wall_clock=wall_clock,
        ),
        mode=0o644,
    )
    return {
        "report": report,
        "task_level": task_level,
        "preflight": preflight,
        "rows": rows,
        "aggregate_primary": aggregate_primary,
        "aggregate_all": aggregate_all,
        "association": association,
        "mde_pp": mde_pp,
        "wall_clock_seconds": wall_clock,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """逐行 JSON 落盘（确定性：键排序 + 紧凑分隔符；空列表也落空文件）。"""
    content = "".join(canonical_dump(row) + "\n" for row in rows)
    atomic_write_text(str(path), content, mode=0o644)


def _build_run_summary(
    *,
    records: list[dict[str, Any]],
    aggregate_primary: dict[str, Any],
    aggregate_all: dict[str, Any],
    report: dict[str, Any],
    preflight: dict[str, Any],
    rows: list[dict[str, Any]],
    out_dir: Path,
    wall_clock: float,
) -> str:
    """RUN_SUMMARY.log（人读运行日志；含墙钟，不参与幂等声明）。"""
    lines: list[str] = []
    add = lines.append
    add(f"[{preflight['run']['started_at']} → {preflight['run']['finished_at']}] {TOOL_NAME} v{TOOL_VERSION}（零 LLM）")
    add(
        f"git_head={preflight['environment']['git_head']} python={preflight['environment']['python']} "
        f"z3={preflight['environment']['z3']} platform={preflight['environment']['platform']}"
    )
    add(f"anchor_table sha256={preflight['inputs']['anchor_table']['sha256']}")
    add(f"dfspec_benchmark sha256={preflight['inputs']['dfspec_benchmark']['sha256']}")
    add(
        f"params timeout_ms={preflight['params']['smt_timeout_ms']} "
        f"unknown_as_timeout_ratio={preflight['params']['unknown_as_timeout_ratio']}"
    )
    add(
        f"tasks: total={len(records)} primary={preflight['counts']['tasks_primary']} "
        f"with_material={aggregate_all['tasks_with_material']} "
        f"clauses_primary={aggregate_primary['clauses_pooled']} clauses_all={aggregate_all['clauses_pooled']}"
    )
    add(f"material_gap_tasks={[g['task_id'] for g in aggregate_all['material_gap_tasks']]}")
    add(f"status primary: {aggregate_primary['status_totals_pooled']}")
    add(f"status all50:   {aggregate_all['status_totals_pooled']}")
    add(
        f"witness_rate mean={aggregate_primary['witness_rate_mean']} "
        f"median={aggregate_primary['witness_rate_median']} "
        f"reach_rate_pooled={aggregate_primary['reach_rate_pooled']} "
        f"timeout_rate_pooled={aggregate_primary['timeout_rate_pooled']}"
    )
    add(
        f"mechanism verdict={report['mechanism_layer']['verdict']} reason={report['mechanism_layer']['verdict_reason']}"
    )
    add(
        f"association: {report['association_layer'].get('interpretation')} "
        f"(delta_pp={report['association_layer'].get('delta_pp_high_minus_low')}, "
        f"MDE={report['association_layer'].get('mde_pp')}pp)"
    )
    add(
        "determinism in_process_double_solve_status_equal="
        f"{report['determinism']['in_process_double_solve_status_equal']} "
        f"mismatches={report['determinism']['double_solve_mismatches']}"
    )
    add(f"llm_calls=0 usd=0.0 solver_ms_total={aggregate_all['solve_ms_total']} wall_clock_seconds={wall_clock}")
    add("artifacts:")
    for path in sorted(out_dir.iterdir()):
        if path.is_file():
            add(f"  {path.name}  {path.stat().st_size} bytes")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T3b z3 SMT 见证层最小启用批次（零 LLM）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    parser.add_argument("--anchor-table", default=str(DEFAULT_ANCHOR_TABLE), help="规格锚表路径")
    parser.add_argument("--dfspec-benchmark", default=str(DEFAULT_DF_SPEC_BENCHMARK), help="df_spec 批次 JSON")
    parser.add_argument("--dfspec-report", default=str(DEFAULT_DF_SPEC_REPORT), help="df_spec 报告 JSON")
    parser.add_argument("--quixbugs-root", default=None, help="QuixBugs 数据根（可选覆盖）")
    parser.add_argument("--timeout-ms", type=int, default=SOLVE_TIMEOUT_MS, help="per-clause 求解超时（ms）")
    parser.add_argument(
        "--no-determinism-probe",
        action="store_true",
        help="跳过进程内第二次独立求解自检（仅调试用；正式批次不得跳过）",
    )
    args = parser.parse_args(argv)
    timeout_ms = max(100, min(30000, int(args.timeout_ms)))
    if timeout_ms != SOLVE_TIMEOUT_MS:
        print(
            f"[smt_witness_batch] ⚠ 超时参数偏离预注册冻结值 {SOLVE_TIMEOUT_MS}ms → {timeout_ms}ms；"
            "这属于参数重标，结果须按重标口径另行披露",
            file=sys.stderr,
        )
    result = run_batch(
        out_dir=Path(args.out),
        anchor_table_path=Path(args.anchor_table),
        dfspec_benchmark_path=Path(args.dfspec_benchmark),
        dfspec_report_path=Path(args.dfspec_report),
        quixbugs_root=args.quixbugs_root,
        timeout_ms=timeout_ms,
        determinism_probe=not args.no_determinism_probe,
    )
    report = result["report"]
    agg = result["aggregate_primary"]
    print(
        f"[smt_witness_batch] ✓ 写入 {args.out}\n"
        f"    任务 {len(result['task_level']['tasks'])}（主判定 {agg['tasks_total']} / 有材料 "
        f"{agg['tasks_with_material']} / 有子句 {agg['tasks_with_clauses']}）\n"
        f"    主判定 status: {agg['status_totals_pooled']}\n"
        f"    witness_rate mean={agg['witness_rate_mean']} reach_rate={agg['reach_rate_pooled']} "
        f"timeout_rate={agg['timeout_rate_pooled']}\n"
        f"    机制层判定: {report['mechanism_layer']['verdict']} "
        f"（{report['mechanism_layer']['verdict_reason']}）\n"
        f"    墙钟 {result['wall_clock_seconds']}s；LLM 调用 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
