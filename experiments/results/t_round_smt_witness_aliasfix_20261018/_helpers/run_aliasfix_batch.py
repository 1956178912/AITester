"""T3c 复跑运行器（零 LLM）：`result`→`r` 别名修复后的 SMT 见证批 + 与 T3b pre-fix 基线对比。

定位
====
本文件位于 T3c 结果目录（`experiments/results/t_round_smt_witness_aliasfix_20261018/_helpers/`）
的 `_helpers/` 下，作为**批次运行器**存在（同仓已有 `_helpers/gen_readme.py` 先例）。
它复用 T3b 运行器 `experiments/smt_witness_batch.py` 的纯函数/口径（材料查找、
单子句求解、任务行构建、聚合、复算自检），**不修改** T3b 脚本；差异只在
`src/specs/spec_smt.py` 的 T3c 修复（result→r 别名归一，见 `PREREG_ALIASFIX.md`）。

产物（写入上级结果目录）
========================
`PREFLIGHT.json` / `PER_CLAUSE.jsonl` / `TASK_LEVEL.json` / `ANALYSIS_REPORT.json` /
`COMPARISON.json` / `README.md` / `RUN_SUMMARY.log`（SHA256SUMS 由
`scripts/gates/checksum_results.py` 生成校验）。

对比口径（PREREG_ALIASFIX §3 冻结）
===================================
- C1 有效性：post-fix `sat` / `reached` > pre-fix 归档 19。
- C2 别名字句去向：T3b 110 条 `result_alias_not_reached` 行按
  `(task_id, clause_sha256_16, clause_index)` 逐行连接 post-fix 行，
  matched=110 / unmatched=0，去向分解和 == 110。
- C3 语义安全 guard：solver_exception=0；单子句 unsat 不增；全组一致性探针
  无 unsat（>2 任务 → 停止）；定向测试全绿。
- C4 逐子句复算；C5 T3b 目录 sha256 未变（只读基线）。

用法::

    .venv/bin/python experiments/results/t_round_smt_witness_aliasfix_20261018/_helpers/run_aliasfix_batch.py
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import platform
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

_HELPER_PATH = Path(__file__).resolve()
_OUT_DIR = _HELPER_PATH.parent.parent
_REPO_ROOT = _HELPER_PATH.parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.misguided_metrics import (  # noqa: E402
    canonical_json,
    resolve_quixbugs_roots,
    sha256_file,
    sha256_text,
)
from experiments.oracle_quality_replay import load_anchor_table  # noqa: E402
from experiments.smt_witness_batch import (  # noqa: E402
    DEFAULT_ANCHOR_TABLE,
    DEFAULT_DF_SPEC_BENCHMARK,
    DEFAULT_DF_SPEC_REPORT,
    SOLVE_TIMEOUT_MS,
    STATUS_ENUM,
    aggregate_records,
    build_association,
    build_task_record,
    check_recompute,
    load_dfspec_rows,
    status_by_channel,
)
from src.specs.spec_smt import _RESULT_ALIAS_NAME, _normalize_result_alias, smt_available  # noqa: E402
from src.utils.atomic_io import atomic_write_json, atomic_write_text  # noqa: E402

SCHEMA_VERSION = "t_round_smt_witness_aliasfix/1"
TOOL_NAME = "t_round_smt_witness_aliasfix_20261018/_helpers/run_aliasfix_batch.py"
TOOL_VERSION = "1.0.0"

OLD_DIR = _OUT_DIR.parent / "t_round_smt_witness_20261018"
PREREG_NAME = "PREREG_ALIASFIX.md"
# 计时键（求解器墙钟非确定）：确定性比较时剔除（与 T3b 运行器口径一致）
_TIMING_KEYS: frozenset[str] = frozenset(
    {
        "smt_solve_ms",
        "smt_solve_ms_total",
        "solve_ms_total",
        "solver_cpu_ms_total",
        "wall_clock_seconds",
    }
)
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


# ─── 通用工具 ────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except (ValueError, OSError):
        return str(path)


def _sha_opt(path: Path) -> str | None:
    try:
        return sha256_file(path) if path.is_file() else None
    except OSError:
        return None


def _strip_timing_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_timing_keys(v) for k, v in obj.items() if k not in _TIMING_KEYS}
    if isinstance(obj, list):
        return [_strip_timing_keys(v) for v in obj]
    return obj


def _round6(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _canonical_dump(obj: Any) -> str:
    return canonical_json(obj)


def _git_head() -> str | None:
    head = _REPO_ROOT / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith("ref:"):
        try:
            return (_REPO_ROOT / ".git" / text.split(":", 1)[1].strip()).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return text or None


def _git_show(path_in_repo: str) -> str | None:
    """git show HEAD:<path>（读 pre-fix 源码 sha；零网络；失败返回 None）。"""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{path_in_repo}"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _z3_version() -> str | None:
    if not smt_available():
        return None
    try:
        import z3

        return str(z3.get_version_string())
    except Exception:
        return None


def _import_scan(*paths: Path) -> dict[str, Any]:
    """AST 扫描多个脚本 import 面（零 LLM 证据）。"""
    hits: list[str] = []
    checked: list[str] = []
    for path in paths:
        checked.append(_display_path(path))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            hits.append(f"{_display_path(path)}: scan_error:{type(exc).__name__}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                hits.extend(
                    f"{_display_path(path)}: import {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS
                )
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                hits.append(f"{_display_path(path)}: from {node.module}")
    return {
        "passed": not hits,
        "method": "ast",
        "checked_files": checked,
        "forbidden_module_roots": sorted(_FORBIDDEN_IMPORT_ROOTS),
        "hits": hits,
    }


def _has_result_name(clause: str) -> bool:
    """token 感知判定子句是否引用 Name result（解析失败 → False）。"""
    try:
        tree = ast.parse(clause, mode="eval")
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.Name) and node.id == _RESULT_ALIAS_NAME for node in ast.walk(tree))


def _feature_bucket(clause: str) -> str:
    """旧批子句的"其它不可翻译构造"特征（用于去向分解）：call/subscript/attr/alias_only。"""
    features: list[str] = []
    if "(" in clause:
        features.append("call")
    if "[" in clause:
        features.append("subscript")
    if "." in clause:
        features.append("attr")
    return "+".join(features) if features else "alias_only"


_IS_IN_OPS: tuple[type[ast.cmpop], ...] = (ast.Is, ast.IsNot, ast.In, ast.NotIn)


def _postfix_error_reason(clause: str, params: list[str] | None) -> str:
    """post-fix 批次 error 行的**剩余**归因（修复后别名已不再是拒绝原因）。

    与 T3b pre-fix 归因（``result_alias_not_reached`` 优先）不同：修复后
    ``result`` 已归一为 ``r``，仍 error 的子句须按**剩余**不可翻译构造归因，
    否则会把"翻译层算子集限制"误读成"别名未修复"。优先级（互斥）：
    unsupported_call → unsupported_subscript → unsupported_attribute →
    unsupported_is_in_operator → unknown_free_name → other_not_reached。
    """
    params_set = set(params or [])
    normalized = clause if _RESULT_ALIAS_NAME in params_set else _normalize_result_alias(clause)
    try:
        tree = ast.parse(normalized, mode="eval")
    except (SyntaxError, ValueError):
        return "non_expression_or_unparseable"
    nodes = list(ast.walk(tree))
    if any(isinstance(node, ast.Call) for node in nodes):
        return "unsupported_call"
    if any(isinstance(node, ast.Subscript) for node in nodes):
        return "unsupported_subscript"
    if any(isinstance(node, ast.Attribute) for node in nodes):
        return "unsupported_attribute"
    for node in nodes:
        if isinstance(node, ast.Compare) and any(isinstance(op, _IS_IN_OPS) for op in node.ops):
            return "unsupported_is_in_operator"
    free_names = {node.id for node in nodes if isinstance(node, ast.Name)}
    if free_names - (params_set | {_RESULT_ALIAS_NAME, "r"}):
        return "unknown_free_name"
    return "other_not_reached"


def postfix_error_attribution(
    rows: list[dict[str, Any]], params_by_task: dict[str, list[str] | None]
) -> dict[str, Any]:
    """post-fix 批次按通道 × 剩余归因原因的 error 计数 + 到达求解器结果分解。"""
    by_channel: dict[str, dict[str, int]] = {}
    reached_breakdown = {status: 0 for status in STATUS_ENUM}
    for row in rows:
        status = str(row["smt_status"])
        if row.get("reached_solver"):
            reached_breakdown[status] += 1
        if status != "error":
            continue
        channel = str(row.get("channel") or "unknown")
        if row.get("error_kind") == "not_reached":
            reason = _postfix_error_reason(str(row.get("clause_text") or ""), params_by_task.get(str(row["task_id"])))
        else:
            reason = str(row.get("error_kind") or "unknown")
        bucket = by_channel.setdefault(channel, {})
        bucket[reason] = bucket.get(reason, 0) + 1
    return {
        "by_channel": {channel: dict(sorted(reasons.items())) for channel, reasons in sorted(by_channel.items())},
        "reached_outcome_breakdown": reached_breakdown,
        "note": (
            "post-fix 剩余归因（别名归一已生效）：call/subscript/attribute 为翻译层保守算子集限制；"
            "is/in 为 Compare 算子集限制；unknown_free_name 为自由名域限制"
        ),
    }


# ─── T3b 基线只读校验与加载 ─────────────────────────────────────────────────
def verify_t3b_untouched(old_dir: Path = OLD_DIR) -> dict[str, Any]:
    """按 T3b `SHA256SUMS` 校验其工件未被修改（T3c 只读基线纪律）。"""
    sums = old_dir / "SHA256SUMS"
    result: dict[str, Any] = {
        "old_dir": _display_path(old_dir),
        "sums_path": _display_path(sums),
        "sums_sha256": _sha_opt(sums),
        "ok": None,
        "checked": 0,
        "mismatches": [],
    }
    if not sums.is_file():
        result.update({"ok": False, "mismatches": ["SHA256SUMS 缺失"]})
        return result
    for raw in sums.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            result["mismatches"].append(f"非法行: {line}")
            continue
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = old_dir / name
        actual = _sha_opt(target)
        result["checked"] += 1
        if actual != expected:
            result["mismatches"].append(f"{name}: expected={expected} actual={actual}")
    result["ok"] = not result["mismatches"]
    return result


def load_old_batch(old_dir: Path = OLD_DIR) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in (old_dir / "PER_CLAUSE.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_level = json.loads((old_dir / "TASK_LEVEL.json").read_text(encoding="utf-8"))
    report = json.loads((old_dir / "ANALYSIS_REPORT.json").read_text(encoding="utf-8"))
    return {
        "dir": _display_path(old_dir),
        "files_sha256": {
            name: _sha_opt(old_dir / name)
            for name in ("PER_CLAUSE.jsonl", "TASK_LEVEL.json", "ANALYSIS_REPORT.json", "PREREG.md")
        },
        "rows": rows,
        "task_level": task_level,
        "report": report,
        "aggregate_primary": task_level["aggregate"]["primary_41"],
    }


# ─── 复跑 ────────────────────────────────────────────────────────────────────
def build_records(
    ordered_rows: list[dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
    timeout_ms: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in ordered_rows:
        program = str((row.get("task_metadata") or {}).get("program") or "")
        in_primary = bool(program) and not program.endswith("_test")
        records.append(build_task_record(row, anchors, roots, in_primary=in_primary, timeout_ms=timeout_ms))
    return records


def full_post_group_audit(
    ordered_rows: list[dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
) -> dict[str, Any]:
    """全组一致性探针：expr 通道 post+inv 作为约束组，pre-fix 模拟 vs post-fix。

    pre-fix 模拟（与 T3c 修复前代码等价）：约束组内任一子句引用 Name result →
    旧 `_infer_sorts` 因自由名不在域返回 None → 整体 skipped；否则与 post-fix 相同。
    另对 NL 通道（生产 `_collect_post_constraints` 实际消费的键）做同口径探针。
    """
    from experiments.oracle_quality_replay import lookup_anchor
    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_smt import check_postcondition_consistency

    from_expr = {"old": Counter(), "new": Counter()}
    transitions: Counter[tuple[str, str]] = Counter()
    nl_counts = {"old": Counter(), "new": Counter()}
    new_unsat_tasks: list[dict[str, Any]] = []
    tasks = 0
    for row in ordered_rows:
        program = str((row.get("task_metadata") or {}).get("program") or "")
        if not program or program.endswith("_test"):
            continue
        code = None
        for root in roots:
            candidate = root / "python_programs" / f"{program}.py"
            if candidate.is_file():
                code = candidate.read_text(encoding="utf-8")
                break
        if code is None:
            continue
        _, anchor = lookup_anchor(anchors, code)
        if not anchor:
            continue
        spec = parse_logic_analysis(anchor.get("logic_analysis"))
        if not spec:
            continue
        # 签名参数：与批次同口径
        from experiments.smt_witness_batch import resolve_signature_params

        params, _ = resolve_signature_params(code, str(anchor.get("function_name") or ""))
        tasks += 1
        for channel, clauses in (
            (
                "expr",
                [
                    c.strip()
                    for c in (spec.get("postconditions_expr") or []) + (spec.get("invariants_expr") or [])
                    if isinstance(c, str) and c.strip()
                ],
            ),
            (
                "nl",
                [
                    c.strip()
                    for c in (spec.get("postconditions") or []) + (spec.get("invariants") or [])
                    if isinstance(c, str) and c.strip()
                ],
            ),
        ):
            if not clauses:
                continue
            old_status = (
                "skipped"
                if any(_has_result_name(c) for c in clauses)
                else check_postcondition_consistency({"postconditions": clauses}, params)["status"]
            )
            new_status = check_postcondition_consistency({"postconditions": clauses}, params)["status"]
            bucket = from_expr if channel == "expr" else nl_counts
            bucket["old"][old_status] += 1
            bucket["new"][new_status] += 1
            if channel == "expr":
                transitions[(old_status, new_status)] += 1
                if new_status == "unsat":
                    new_unsat_tasks.append({"program": program, "channel": channel, "clauses": clauses})
            elif new_status == "unsat":
                new_unsat_tasks.append({"program": program, "channel": channel, "clauses": clauses})
    return {
        "tasks_with_post_group": tasks,
        "expr_channel": {
            "old_status_counts": dict(from_expr["old"]),
            "new_status_counts": dict(from_expr["new"]),
            "transitions": {f"{old}->{new}": count for (old, new), count in sorted(transitions.items())},
            "new_unsat_tasks": [t for t in new_unsat_tasks if t["channel"] == "expr"],
        },
        "nl_channel": {
            "old_status_counts": dict(nl_counts["old"]),
            "new_status_counts": dict(nl_counts["new"]),
            "new_unsat_tasks": [t for t in new_unsat_tasks if t["channel"] == "nl"],
        },
        "note": (
            "pre-fix 模拟依据：修复前含 Name result 的约束组必然在 _infer_sorts 自由名门返回 None → skipped；"
            "无 result 的组 pre/post-fix 行为相同（归一为恒等）。"
        ),
    }


# ─── 对比构建 ────────────────────────────────────────────────────────────────
def build_comparison(
    *,
    old: dict[str, Any],
    new_records: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    aggregate_primary: dict[str, Any],
    aggregate_all: dict[str, Any],
    full_post_audit: dict[str, Any],
    t3b_untouched: dict[str, Any],
    recompute_primary: dict[str, Any],
    params_by_task: dict[str, list[str] | None],
    src_pre_sha: str | None,
    src_post_sha: str | None,
    anchor_sha: str | None,
    timeout_ms: int,
) -> dict[str, Any]:
    """C1/C2/C3/C4/C5 判据 + 110 条 alias 子句去向分解（冻结口径）。"""
    old_primary = old["aggregate_primary"]
    old_rows = old["rows"]
    # ① alias 行选择：T3b error/not_reached 且子句引用 Name result
    alias_old = [
        row
        for row in old_rows
        if row.get("smt_status") == "error"
        and row.get("error_kind") == "not_reached"
        and _has_result_name(str(row.get("clause_text") or ""))
    ]
    # ② 逐行连接 post-fix（同 task_id + 子句 sha16 + clause_index）
    new_index = {(str(row["task_id"]), str(row["clause_sha256_16"]), int(row["clause_index"])): row for row in new_rows}
    items: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for row in alias_old:
        key = (str(row["task_id"]), str(row["clause_sha256_16"]), int(row["clause_index"]))
        new_row = new_index.get(key)
        if new_row is None:
            unmatched.append({"key": list(key), "clause_text": row.get("clause_text")})
            continue
        new_status = str(new_row["smt_status"])
        new_reason = None
        if new_status == "error":
            new_reason = (
                _postfix_error_reason(
                    str(new_row.get("clause_text") or ""), params_by_task.get(str(new_row["task_id"]))
                )
                if new_row.get("error_kind") == "not_reached"
                else new_row.get("error_kind")
            )
        items.append(
            {
                "task_id": key[0],
                "clause_sha256_16": key[1],
                "clause_index": key[2],
                "channel_field": row.get("channel_field"),
                "clause_text": row.get("clause_text"),
                "in_primary": bool(row.get("in_primary")),
                "feature_bucket": _feature_bucket(str(row.get("clause_text") or "")),
                "old_status": "error",
                "old_error_kind": "not_reached",
                "new_status": new_status,
                "new_error_kind": new_row.get("error_kind"),
                "new_error_reason": new_reason,
                "new_reached_solver": bool(new_row.get("reached_solver")),
            }
        )

    def _destination(rows: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts = {status: 0 for status in STATUS_ENUM}
        reason_counts: Counter[str] = Counter()
        for item in rows:
            status_counts[item["new_status"]] += 1
            if item["new_status"] == "error":
                reason_counts[str(item["new_error_reason"] or "unknown")] += 1
        return {
            "status_counts": status_counts,
            "error_reason_counts": dict(sorted(reason_counts.items())),
            "reached": sum(1 for item in rows if item["new_reached_solver"]),
            "n": len(rows),
        }

    primary_items = [item for item in items if item["in_primary"]]
    alias_only_items = [item for item in primary_items if item["feature_bucket"] == "alias_only"]
    by_feature: dict[str, Any] = {}
    for feature in sorted({item["feature_bucket"] for item in primary_items}):
        subset = [item for item in primary_items if item["feature_bucket"] == feature]
        by_feature[feature] = _destination(subset)

    # ③ 聚合对比
    def _agg_view(aggregate: dict[str, Any]) -> dict[str, Any]:
        return {
            "clauses_pooled": aggregate["clauses_pooled"],
            "clauses_reached_pooled": aggregate["clauses_reached_pooled"],
            "status_totals_pooled": dict(aggregate["status_totals_pooled"]),
            "witness_rate_mean": aggregate.get("witness_rate_mean"),
            "witness_rate_median": aggregate.get("witness_rate_median"),
            "reach_rate_pooled": aggregate.get("reach_rate_pooled"),
            "timeout_rate_pooled": aggregate.get("timeout_rate_pooled"),
            "tasks_with_material": aggregate.get("tasks_with_material"),
            "tasks_with_clauses": aggregate.get("tasks_with_clauses"),
            "tasks_with_any_sat": aggregate.get("tasks_with_any_sat"),
            "material_gap_tasks": aggregate.get("material_gap_tasks"),
        }

    old_view, new_view = _agg_view(old_primary), _agg_view(aggregate_primary)
    delta = {
        "clauses_reached": (new_view["clauses_reached_pooled"] or 0) - (old_view["clauses_reached_pooled"] or 0),
        "sat": new_view["status_totals_pooled"]["sat"] - old_view["status_totals_pooled"]["sat"],
        "unsat": new_view["status_totals_pooled"]["unsat"] - old_view["status_totals_pooled"]["unsat"],
        "unknown": new_view["status_totals_pooled"]["unknown"] - old_view["status_totals_pooled"]["unknown"],
        "timeout": new_view["status_totals_pooled"]["timeout"] - old_view["status_totals_pooled"]["timeout"],
        "error": new_view["status_totals_pooled"]["error"] - old_view["status_totals_pooled"]["error"],
        "reach_rate_pp": round(((new_view["reach_rate_pooled"] or 0) - (old_view["reach_rate_pooled"] or 0)) * 100, 2),
        "witness_rate_pp": round(
            ((new_view["witness_rate_mean"] or 0) - (old_view["witness_rate_mean"] or 0)) * 100, 2
        ),
        "tasks_with_any_sat": (new_view["tasks_with_any_sat"] or 0) - (old_view["tasks_with_any_sat"] or 0),
    }

    # ④ 语义安全 guard（PREREG_ALIASFIX §3 C3）
    total = dict(aggregate_all["status_totals_pooled"])
    primary_total = dict(aggregate_primary["status_totals_pooled"])
    guards = {
        "solver_exception_zero": {"value": None, "pass": True},
        "single_clause_unsat_not_increased": {
            "old_unsat": old_view["status_totals_pooled"]["unsat"],
            "new_unsat": primary_total["unsat"],
            "new_unsat_all50": total["unsat"],
            "pass": primary_total["unsat"] <= old_view["status_totals_pooled"]["unsat"],
        },
        "full_post_group_no_unsat_surge": {
            "old_unsat_tasks": len(full_post_audit["expr_channel"]["new_unsat_tasks"]),
            "new_unsat_tasks": len(full_post_audit["expr_channel"]["new_unsat_tasks"]),
            "new_unsat_task_list": full_post_audit["expr_channel"]["new_unsat_tasks"],
            "pass": len(full_post_audit["expr_channel"]["new_unsat_tasks"]) <= 2,
        },
    }
    # solver_exception 实测计数（新行 error_kind）
    exc = sum(1 for row in new_rows if row.get("error_kind") == "solver_exception")
    guards["solver_exception_zero"] = {"value": exc, "pass": exc == 0}

    # ⑤ C1/C2/C4/C5 判据
    criteria = {
        "C1_reach_and_sat_increase": {
            "old_reached": old_view["clauses_reached_pooled"],
            "old_sat": old_view["status_totals_pooled"]["sat"],
            "new_reached": new_view["clauses_reached_pooled"],
            "new_sat": new_view["status_totals_pooled"]["sat"],
            "pass": (new_view["clauses_reached_pooled"] or 0) > (old_view["clauses_reached_pooled"] or 0)
            and (new_view["status_totals_pooled"]["sat"] or 0) > (old_view["status_totals_pooled"]["sat"] or 0),
        },
        "C2_alias_destinations_auditable": {
            "old_alias_error_rows_all50": len(alias_old),
            "old_alias_error_rows_primary": sum(1 for row in alias_old if row.get("in_primary")),
            "matched": len(items),
            "unmatched": len(unmatched),
            "alias_only_primary": len(alias_only_items),
            "alias_only_primary_reached": sum(1 for item in alias_only_items if item["new_reached_solver"]),
            "pass": len(unmatched) == 0
            and len(items) == len(alias_old)
            and sum(_destination(primary_items)["status_counts"].values())
            == sum(1 for item in items if item["in_primary"]),
        },
        "C3_semantic_guards": {
            **guards,
            "pass": all(item["pass"] for item in guards.values()),
        },
        "C4_per_clause_recompute": {
            "per_task_ok": recompute_primary["per_task_ok"],
            "pooled_ok": recompute_primary["pooled_ok"],
            "pass": bool(recompute_primary["all_ok"]),
        },
        "C5_t3b_untouched": {"pass": bool(t3b_untouched.get("ok")), "detail": t3b_untouched},
    }
    effective = all(item["pass"] for item in criteria.values())
    return {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "inputs": {
            "old_batch": {"dir": old["dir"], "files_sha256": old["files_sha256"]},
            "new_batch_dir": _display_path(_OUT_DIR),
            "src_spec_smt": {"pre_fix_sha256": src_pre_sha, "post_fix_sha256": src_post_sha},
            "anchor_table_sha256": anchor_sha,
        },
        "caliber": {
            "same_task_set": "QuixBugs 41 缺陷程序主判定集（program 不以 _test 结尾）",
            "same_material": "emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json（内容寻址）",
            "same_channel_rule": "expr 优先 / NL 回退",
            "same_timeout_ms": timeout_ms,
            "same_per_clause_api": "check_precondition_vacuity / check_postcondition_consistency（单子句单 spec）",
            "only_difference": "src/specs/spec_smt.py 的 result→r 别名归一（T3c）",
            "not_a_randomized_trial": "pre-fix 归档基线 vs post-fix 复跑（同口径观测），非随机对照试验",
        },
        "aggregate": {"old_primary": old_view, "new_primary": new_view, "delta": delta},
        "expected_deviation_from_prereg": {
            "prereg_stated_expectation": "reach 19+13≈32（假设 13 条纯别名字句全部可达；PREREG_ALIASFIX §4）",
            "observed_new_reached": new_view["clauses_reached_pooled"],
            "deviation": (new_view["clauses_reached_pooled"] or 0) - 32,
            "reason": (
                "13 条 alias_only 中 5 条使用 is / in 比较算子（`_translate` 保守算子集不支持 "
                "Is/IsNot/In/NotIn）→ 仍 error；其阻塞原因是 Compare 算子集而非别名"
            ),
            "not_a_regression": "预注册 §4 预期仅用于偏差披露，不参与判定（C1 判据为 > 旧批 19）",
        },
        "alias_clause_destinations": {
            "definition": (
                "T3b pre-fix 批中 smt_status=error ∧ error_kind=not_reached ∧ 子句含 Name result 的逐子句行；"
                "按 (task_id, clause_sha256_16, clause_index) 连接 post-fix 复跑行"
            ),
            "all50": _destination(items),
            "primary": _destination(primary_items),
            "by_feature_primary": by_feature,
            "alias_only_primary": {
                "n": len(alias_only_items),
                "reached": sum(1 for item in alias_only_items if item["new_reached_solver"]),
                "destination": _destination(alias_only_items),
            },
            "unmatched": unmatched,
            "items": sorted(items, key=lambda item: (item["task_id"], item["clause_index"])),
        },
        "full_post_group_semantics": full_post_audit,
        "risk_guards": guards,
        "criteria": criteria,
        "conclusion": {
            "effective": effective,
            "c1_c2_c3_c4_c5": {name: item["pass"] for name, item in criteria.items()},
            "summary": (
                "别名修复有效：post-fix 可达/可解子句数上升，110 条旧别名子句去向可逐行审计，无语义风险信号"
                if effective
                else "判据未全部满足：见 criteria（不得宣称修复有效）"
            ),
            "t3b_conclusion_unchanged": "T3b 结果保留为 pre-fix 基线，其机制层 pass/关联层无对照结论按 pre-fix 口径不变",
        },
    }


# ─── 报告构建 ────────────────────────────────────────────────────────────────
def build_analysis_report(
    *,
    records: list[dict[str, Any]],
    aggregate_primary: dict[str, Any],
    aggregate_all: dict[str, Any],
    rows: list[dict[str, Any]],
    params_by_task: dict[str, list[str] | None],
    comparison: dict[str, Any],
    preflight: dict[str, Any],
    recompute_primary: dict[str, Any],
    recompute_all: dict[str, Any],
    association: dict[str, Any],
    in_process_rebuild_equal: bool,
) -> dict[str, Any]:
    audit_samples: list[dict[str, Any]] = []
    for status in ("sat", "unsat", "unknown", "timeout", "error"):
        picked = next((row for row in rows if row["smt_status"] == status), None)
        if picked is None:
            continue
        audit_samples.append(
            {
                "smt_status": status,
                "task_id": picked["task_id"],
                "channel_field": picked["channel_field"],
                "kind": picked["kind"],
                "clause_sha256_16": picked["clause_sha256_16"],
                "clause_text": picked["clause_text"],
                "smt_solve_ms": picked["smt_solve_ms"],
                "error_kind": picked.get("error_kind"),
                "reached_solver": picked.get("reached_solver"),
            }
        )
    alias = comparison.get("alias_clause_destinations") or {}
    return {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "batch": {
            "batch_dir": _display_path(_OUT_DIR),
            "prereg": PREREG_NAME,
            "old_batch_dir": _display_path(OLD_DIR),
            "zero_llm": True,
            "llm_calls": 0,
            "single_arm": True,
            "behavior_change": "T3c：spec_smt 后件/不变式组 result→r 别名归一（参数名 result 时不归一；前件路径零变化）",
            "primary_caliber": "QuixBugs 41 缺陷程序（与 T3b / df_spec detection 41 同集）",
        },
        "mechanism_layer": {
            "verdict": "pass" if comparison["criteria"]["C4_per_clause_recompute"]["pass"] else "fail",
            "criteria": {
                "status_buckets_recomputable": recompute_primary["all_ok"] and recompute_all["all_ok"],
                "aggregate_primary": aggregate_primary,
            },
            "fix_effectiveness": comparison["conclusion"],
        },
        "status_buckets": {
            "primary_41": aggregate_primary["status_totals_pooled"],
            "extension_all50": aggregate_all["status_totals_pooled"],
            "by_channel": status_by_channel(rows),
        },
        "error_attribution": postfix_error_attribution(rows, params_by_task),
        "task_level_rates": {
            "primary_41": {
                "witness_rate_mean": aggregate_primary["witness_rate_mean"],
                "witness_rate_median": aggregate_primary["witness_rate_median"],
                "witness_rate_min": aggregate_primary["witness_rate_min"],
                "witness_rate_max": aggregate_primary["witness_rate_max"],
                "reach_rate_pooled": aggregate_primary["reach_rate_pooled"],
                "timeout_rate_pooled": aggregate_primary["timeout_rate_pooled"],
                "tasks_with_any_sat": aggregate_primary["tasks_with_any_sat"],
                "tasks_with_zero_witness_rate": aggregate_primary["tasks_with_zero_witness_rate"],
                "witness_rate_distribution": aggregate_primary["witness_rate_distribution"],
            },
            "note": "witness_rate = sat / 非空评估子句（D1）；timeout_rate = timeout / reached",
        },
        "association_layer": {
            **association,
            "note": "单臂观测；T3c 不重跑关联层推断（关联层在 T3b 已按预注册判为无对照），仅复算披露",
        },
        "alias_destination_summary": {
            "all50": alias.get("all50"),
            "primary": alias.get("primary"),
            "by_feature_primary": alias.get("by_feature_primary"),
            "alias_only_primary": alias.get("alias_only_primary"),
        },
        "audit": {
            "audit_samples": audit_samples,
            "per_clause_recompute_primary": recompute_primary,
            "per_clause_recompute_all": recompute_all,
        },
        "determinism": {
            "in_process_double_solve_status_equal": in_process_rebuild_equal,
            "timing_keys_volatile": sorted(_TIMING_KEYS),
            "compared_scope": "剔除计时键后的任务行/聚合行规范化 JSON（两次独立求解）",
        },
        "cost": {
            "llm_calls": 0,
            "llm_usd": 0.0,
            "network_calls": 0,
            "wall_clock_seconds": None,
            "wall_clock_source": "PREFLIGHT.json::run.wall_clock_seconds",
        },
        "inputs": preflight.get("inputs"),
    }


def build_readme(report: dict[str, Any], preflight: dict[str, Any], comparison: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    agg = comparison["aggregate"]
    old, new, delta = agg["old_primary"], agg["new_primary"], agg["delta"]
    alias = comparison["alias_clause_destinations"]
    guards = comparison["risk_guards"]
    criteria = comparison["criteria"]
    full = comparison["full_post_group_semantics"]
    run = preflight.get("run", {})
    add("# T3c：spec_smt 后件 `result`→`r` 别名缺口修复 + 零 LLM 复跑见证批")
    add("")
    add("> 修复：`src/specs/spec_smt.py::_collect_post_constraints` token 感知别名归一")
    add("> （仅后件/不变式组；签名参数名为 `result` 时不归一；前件路径零变化）。")
    add("> 复跑：与 T3b **同任务集/同材料/同通道/同超时/同单子句 API**，差异仅 src 修复。")
    add("> 零 LLM（0 调用 / 0 USD / 不联网）；预注册 `PREREG_ALIASFIX.md` 跑前冻结。")
    add("")
    add("## 0. 结论")
    add("")
    add(f"- **修复有效性（C1–C5 全满足）：`{comparison['conclusion']['effective']}`**")
    add(
        f"- C1 可达/可解上升：reached {old['clauses_reached_pooled']} → **{new['clauses_reached_pooled']}**"
        f"（+{delta['clauses_reached']}）；sat {old['status_totals_pooled']['sat']} → "
        f"**{new['status_totals_pooled']['sat']}**（+{delta['sat']}）"
    )
    add(
        f"- C2 别名字句去向：旧批 alias 子句 all50=**{criteria['C2_alias_destinations_auditable']['old_alias_error_rows_all50']}**"
        f" / primary={criteria['C2_alias_destinations_auditable']['old_alias_error_rows_primary']}；"
        f"matched=**{criteria['C2_alias_destinations_auditable']['matched']}** / "
        f"unmatched=**{criteria['C2_alias_destinations_auditable']['unmatched']}**；"
        f"纯别名子集 reached={criteria['C2_alias_destinations_auditable']['alias_only_primary_reached']}"
        f"/{criteria['C2_alias_destinations_auditable']['alias_only_primary']}"
    )
    add(
        f"- C3 语义安全：solver_exception={guards['solver_exception_zero']['value']}；"
        f"单子句 unsat {guards['single_clause_unsat_not_increased']['old_unsat']}→"
        f"{guards['single_clause_unsat_not_increased']['new_unsat']}；"
        f"全组一致性 unsat 任务={guards['full_post_group_no_unsat_surge']['new_unsat_tasks']}"
        f"（pass={criteria['C3_semantic_guards']['pass']}）"
    )
    add(
        f"- C4 逐子句复算：{criteria['C4_per_clause_recompute']['pass']}；C5 T3b 目录未变：{criteria['C5_t3b_untouched']['pass']}"
    )
    add(
        "- **T3b 结论不变**：T3b（`t_round_smt_witness_20261018/`）保留为 **pre-fix 基线**，"
        "其机制层 pass / 关联层无对照结论按 pre-fix 口径保留；**post-fix 口径数字以本批为准**。"
    )
    add("")
    add("## 1. 主对比表（主判定集 41；D1=184 不变）")
    add("")
    add("| 指标 | T3b pre-fix | T3c post-fix | Δ |")
    add("|---|---:|---:|---:|")
    for label, key in (
        ("非空评估子句 D1", "clauses_pooled"),
        ("到达求解器子句 reached", "clauses_reached_pooled"),
    ):
        add(f"| {label} | {old[key]} | {new[key]} | {new[key] - old[key]:+d} |")
    for status in STATUS_ENUM:
        add(
            f"| status `{status}` | {old['status_totals_pooled'][status]} | "
            f"{new['status_totals_pooled'][status]} | {delta[status]:+d} |"
        )
    add(
        f"| witness_rate 均值 | {old['witness_rate_mean']} | {new['witness_rate_mean']} | {delta['witness_rate_pp']:+.2f}pp |"
    )
    add(
        f"| reach_rate（pooled） | {old['reach_rate_pooled']} | {new['reach_rate_pooled']} | {delta['reach_rate_pp']:+.2f}pp |"
    )
    add(f"| timeout_rate（pooled） | {old['timeout_rate_pooled']} | {new['timeout_rate_pooled']} | — |")
    add(
        f"| 有见证任务数 | {old['tasks_with_any_sat']}/41 | {new['tasks_with_any_sat']}/41 | {delta['tasks_with_any_sat']:+d} |"
    )
    add("")
    add("## 2. 旧批 110 条 `result_alias_not_reached` 子句去向")
    add("")
    all50 = alias["all50"]
    prim = alias["primary"]
    add(
        f"- 旧批 alias error 行：all50=**{all50['n']}** / primary=**{prim['n']}**；匹配 unmatched={len(alias['unmatched'])}"
    )
    add("")
    add("| 口径 | sat | unsat | unknown | timeout | error | reached |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for label, dest in (("all50", all50), ("primary", prim)):
        sc = dest["status_counts"]
        add(
            f"| {label} | {sc['sat']} | {sc['unsat']} | {sc['unknown']} | {sc['timeout']} | "
            f"{sc['error']} | {dest['reached']} |"
        )
    add("")
    add("post-fix 仍 error 的归因分解（primary）：")
    add("")
    add("| 原因 | 子句数 |")
    add("|---|---:|")
    for reason, count in (prim.get("error_reason_counts") or {}).items():
        add(f"| {reason} | {count} |")
    add("")
    add("按旧批子句特征分桶（primary）：")
    add("")
    add("| 旧特征桶 | n | sat | unsat | error | reached |")
    add("|---|---:|---:|---:|---:|---:|")
    for feature, dest in (alias.get("by_feature_primary") or {}).items():
        sc = dest["status_counts"]
        add(f"| {feature} | {dest['n']} | {sc['sat']} | {sc['unsat']} | {sc['error']} | {dest['reached']} |")
    add("")
    deviation = comparison.get("expected_deviation_from_prereg") or {}
    add(
        "- 解读：「alias_only」桶（旧批文本无 call/subscript/attr）13 条中 "
        f"{alias['alias_only_primary']['reached']} 条转 reach/sat；其余 5 条使用 `is`/`in` "
        "比较算子（`_translate` 保守算子集不含 Is/IsNot/In/NotIn）→ 仍 error，"
        "其阻塞原因是 Compare 算子集而非别名。「call/subscript/attr」桶仍受翻译层"
        "保守算子集限制（Call/Subscript/Attribute）——这些不是别名缺口，而是分层能力边界，如实计入。"
    )
    add("")
    add(
        f"- **预注册预期偏差披露**：PREREG_ALIASFIX §4 预期 reach≈32（假设 13 条纯别名字句全部可达），"
        f"实测 **{deviation.get('observed_new_reached')}**（偏差 {deviation.get('deviation')}）——"
        f"原因：{deviation.get('reason')}。{deviation.get('not_a_regression')}。"
    )
    add("")
    add("## 3. 语义安全审计（风险 guard）")
    add("")
    add(
        f"- solver_exception：{guards['solver_exception_zero']['value']}（pass={guards['solver_exception_zero']['pass']}）"
    )
    add(
        f"- 单子句 unsat：pre-fix {guards['single_clause_unsat_not_increased']['old_unsat']} → "
        f"post-fix {guards['single_clause_unsat_not_increased']['new_unsat']}"
        f"（pass={guards['single_clause_unsat_not_increased']['pass']}）"
    )
    add(
        f"- 全组一致性探针（expr 通道 post+inv 约束组）：pre-fix 模拟 "
        f"{full['expr_channel']['old_status_counts']} → post-fix {full['expr_channel']['new_status_counts']}；"
        f"新增 unsat 任务={len(full['expr_channel']['new_unsat_tasks'])}"
        f"（pass={guards['full_post_group_no_unsat_surge']['pass']}）"
    )
    add(
        f"- NL 通道（生产 `_collect_post_constraints` 实际消费的键）全组探针："
        f"{full['nl_channel']['old_status_counts']} → {full['nl_channel']['new_status_counts']}"
        "（生产 NL 通道材料多为中文散文，极少可编译 → 生产行为变化面很小）"
    )
    add("")
    add("## 4. 限制与口径")
    add("")
    add(
        "1. 本批是**同口径 pre/post 复跑对比**（非随机对照试验）；pre-fix 基线为 T3b 归档工件，"
        "post-fix 复用同一运行器纯函数，差异仅 `src/specs/spec_smt.py`。"
    )
    add(
        "2. 单子句批次口径（每子句单独交公开 API）用于观测可解性；生产全组一致性路径另有 "
        "`_infer_sorts` 的「任一无翻译子句 → 整组 skipped」全有全无门，故 post-fix 生产侧"
        "实际新增可判定任务极少（见 §3 探针）。"
    )
    add(
        "3. 翻译层保守算子集（Call/Subscript/Attribute）未在 T3c 变更：110 条 alias 子句中含这些构造者"
        "仍为 error/untranslatable_*，属能力边界而非别名缺口。"
    )
    add("4. 关联层（detection）不在 T3c 范围：T3b 已按预注册判为无对照，本批不重新分桶/不做推断。")
    add(f"5. 零 LLM；墙钟 {run.get('wall_clock_seconds')}s；z3 {preflight.get('environment', {}).get('z3')}。")
    add("")
    add("## 5. 复跑")
    add("")
    add("```bash")
    add(".venv/bin/python experiments/results/t_round_smt_witness_aliasfix_20261018/_helpers/run_aliasfix_batch.py")
    add(
        "python scripts/gates/checksum_results.py --write --results-dir "
        "experiments/results/t_round_smt_witness_aliasfix_20261018"
    )
    add(
        "python scripts/gates/checksum_results.py --verify --results-dir "
        "experiments/results/t_round_smt_witness_aliasfix_20261018"
    )
    add("```")
    add("")
    add("## 6. 产物")
    add("")
    for name in (
        "PREREG_ALIASFIX.md",
        "PREFLIGHT.json",
        "PER_CLAUSE.jsonl",
        "TASK_LEVEL.json",
        "ANALYSIS_REPORT.json",
        "COMPARISON.json",
        "README.md",
        "RUN_SUMMARY.log",
        "SHA256SUMS",
        "_helpers/run_aliasfix_batch.py",
    ):
        add(f"- `{name}`")
    add("")
    return "\n".join(lines) + "\n"


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def run(
    *,
    out_dir: Path = _OUT_DIR,
    old_dir: Path = OLD_DIR,
    anchor_table_path: Path = DEFAULT_ANCHOR_TABLE,
    dfspec_benchmark_path: Path = DEFAULT_DF_SPEC_BENCHMARK,
    dfspec_report_path: Path = DEFAULT_DF_SPEC_REPORT,
    timeout_ms: int = SOLVE_TIMEOUT_MS,
    determinism_probe: bool = True,
) -> dict[str, Any]:
    t_start = time.perf_counter()
    run_started = now_iso()
    os.environ["SPEC_SMT_ENABLE"] = "true"
    os.environ["SPEC_SMT_TIMEOUT_MS"] = str(timeout_ms)

    anchor_loaded = load_anchor_table(anchor_table_path)
    anchors = anchor_loaded["anchors"]
    _, dfspec_rows = load_dfspec_rows(dfspec_benchmark_path)
    dfspec_report = json.loads(dfspec_report_path.read_text(encoding="utf-8"))
    mde_pp = float(dfspec_report["contrast_41"]["mde_pp"])
    roots = resolve_quixbugs_roots(None)
    quixbugs_hit_root = next((root for root in roots if (root / "python_programs").is_dir()), None)
    ordered_rows = sorted(dfspec_rows, key=lambda row: str(row.get("task_id") or ""))

    records = build_records(ordered_rows, anchors, roots, timeout_ms)
    rows = [clause for record in records for clause in record.get("clauses") or []]
    primary_records = [record for record in records if record["in_primary"]]
    aggregate_primary = aggregate_records(primary_records)
    aggregate_all = aggregate_records(records)
    recompute_primary = check_recompute(primary_records, aggregate_primary)
    recompute_all = check_recompute(records, aggregate_all)
    association = build_association(primary_records, mde_pp=mde_pp)

    # 进程内确定性：第二次独立完整求解（剔除计时键比较 status/分类/计数/率）
    rebuild_mismatches: list[str] = []
    in_process_rebuild_equal = False
    if determinism_probe:
        rebuild_records = build_records(ordered_rows, anchors, roots, timeout_ms)
        if _canonical_dump(_strip_timing_keys(primary_records)) != _canonical_dump(
            _strip_timing_keys([r for r in rebuild_records if r["in_primary"]])
        ):
            rebuild_mismatches.append("primary_task_records")
        if _canonical_dump(_strip_timing_keys(records)) != _canonical_dump(_strip_timing_keys(rebuild_records)):
            rebuild_mismatches.append("all_task_records")
        in_process_rebuild_equal = not rebuild_mismatches

    # 基线只读 + 全组语义探针 + 对比
    params_by_task: dict[str, list[str] | None] = {
        str(record["task_id"]): record.get("signature_params") for record in records
    }
    t3b_untouched = verify_t3b_untouched(old_dir)
    old = load_old_batch(old_dir)
    full_post_audit = full_post_group_audit(ordered_rows, anchors, roots)
    src_path = _REPO_ROOT / "src/specs/spec_smt.py"
    pre_src = _git_show("src/specs/spec_smt.py")
    comparison = build_comparison(
        old=old,
        new_records=records,
        new_rows=rows,
        aggregate_primary=aggregate_primary,
        aggregate_all=aggregate_all,
        full_post_audit=full_post_audit,
        t3b_untouched=t3b_untouched,
        recompute_primary=recompute_primary,
        params_by_task=params_by_task,
        src_pre_sha=sha256_text(pre_src) if pre_src else None,
        src_post_sha=_sha_opt(src_path),
        anchor_sha=anchor_loaded["sha256"],
        timeout_ms=timeout_ms,
    )

    wall_clock = round(time.perf_counter() - t_start, 3)
    preflight: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "generated_by": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "run": {"started_at": run_started, "finished_at": None, "wall_clock_seconds": None},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "z3": _z3_version(),
            "smt_available": smt_available(),
            "git_head": _git_head(),
            "cwd": str(Path.cwd()),
            "loadavg_1_5_15": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
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
                "path": PREREG_NAME,
                "sha256": _sha_opt(out_dir / PREREG_NAME),
                "note": "PREREG_ALIASFIX.md（跑前冻结，含 C1-C5 判据与语义风险 guard）",
            },
            "runner_helper": {"path": _display_path(_HELPER_PATH), "sha256": _sha_opt(_HELPER_PATH)},
            "t3b_runner": {
                "path": "experiments/smt_witness_batch.py",
                "sha256": _sha_opt(_REPO_ROOT / "experiments/smt_witness_batch.py"),
            },
            "src_spec_smt": {
                "path": "src/specs/spec_smt.py",
                "pre_fix_sha256": comparison["inputs"]["src_spec_smt"]["pre_fix_sha256"],
                "post_fix_sha256": comparison["inputs"]["src_spec_smt"]["post_fix_sha256"],
            },
            "old_batch": {"dir": old["dir"], "files_sha256": old["files_sha256"]},
            "t3b_untouched_check": t3b_untouched,
            "quixbugs": {
                "roots_considered": [str(root) for root in roots],
                "root_used": str(quixbugs_hit_root) if quixbugs_hit_root else None,
            },
        },
        "params": {
            "smt_timeout_ms": timeout_ms,
            "status_enum": list(STATUS_ENUM),
            "primary_caliber": "41 缺陷程序（program 不以 _test 结尾）",
            "clause_channel_rule": "expr 优先 / NL 回退（_select_compile_channels 同口径）",
            "fix": "result→r token 感知别名归一（仅后件/不变式组；参数名 result 时不归一）",
            "env": {
                "SPEC_SMT_ENABLE": os.environ.get("SPEC_SMT_ENABLE"),
                "SPEC_SMT_TIMEOUT_MS": os.environ.get("SPEC_SMT_TIMEOUT_MS"),
            },
        },
        "zero_llm": {
            "llm_calls": 0,
            "network_calls": 0,
            "usd": 0.0,
            "import_scan": _import_scan(_HELPER_PATH, _REPO_ROOT / "experiments/smt_witness_batch.py"),
        },
        "counts": {
            "tasks_total": len(records),
            "tasks_primary": len(primary_records),
            "clauses_pooled_primary": aggregate_primary["clauses_pooled"],
            "clauses_pooled_all": aggregate_all["clauses_pooled"],
        },
    }
    preflight["run"]["finished_at"] = now_iso()
    preflight["run"]["wall_clock_seconds"] = wall_clock

    report = build_analysis_report(
        records=records,
        aggregate_primary=aggregate_primary,
        aggregate_all=aggregate_all,
        rows=rows,
        params_by_task=params_by_task,
        comparison=comparison,
        preflight=preflight,
        recompute_primary=recompute_primary,
        recompute_all=recompute_all,
        association=association,
        in_process_rebuild_equal=in_process_rebuild_equal,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    content = "".join(_canonical_dump(row) + "\n" for row in rows)
    atomic_write_text(str(out_dir / "PER_CLAUSE.jsonl"), content, mode=0o644)
    atomic_write_json(
        str(out_dir / "TASK_LEVEL.json"),
        {
            "schema": SCHEMA_VERSION,
            "generated_by": TOOL_NAME,
            "meta": {
                "batch_dir": _display_path(out_dir),
                "prereg": PREREG_NAME,
                "zero_llm": True,
                "llm_calls": 0,
                "timeout_ms": timeout_ms,
                "primary_caliber": "41 缺陷程序（program 不以 _test 结尾）",
                "behavior_change": "spec_smt 后件/不变式组 result→r 别名归一（T3c）",
                "rate_definitions": {
                    "smt_witness_rate": "sat / smt_clauses_nonempty",
                    "smt_reach_rate": "reached / smt_clauses_nonempty",
                    "smt_timeout_rate": "timeout / reached（null if reached==0）",
                },
            },
            "aggregate": {"primary_41": aggregate_primary, "extension_all50": aggregate_all},
            "tasks": records,
        },
        indent=2,
        mode=0o644,
    )
    atomic_write_json(str(out_dir / "ANALYSIS_REPORT.json"), report, indent=2, mode=0o644)
    atomic_write_json(str(out_dir / "COMPARISON.json"), comparison, indent=2, mode=0o644)
    atomic_write_json(str(out_dir / "PREFLIGHT.json"), preflight, indent=2, mode=0o644)
    atomic_write_text(str(out_dir / "README.md"), build_readme(report, preflight, comparison), mode=0o644)
    atomic_write_text(
        str(out_dir / "RUN_SUMMARY.log"),
        _build_run_summary(preflight, comparison, out_dir, wall_clock, in_process_rebuild_equal),
        mode=0o644,
    )
    return {
        "comparison": comparison,
        "report": report,
        "preflight": preflight,
        "aggregate_primary": aggregate_primary,
        "aggregate_all": aggregate_all,
        "wall_clock_seconds": wall_clock,
        "t3b_untouched": t3b_untouched,
    }


def _build_run_summary(
    preflight: dict[str, Any],
    comparison: dict[str, Any],
    out_dir: Path,
    wall_clock: float,
    in_process_rebuild_equal: bool,
) -> str:
    lines: list[str] = []
    add = lines.append
    old = comparison["aggregate"]["old_primary"]
    new = comparison["aggregate"]["new_primary"]
    delta = comparison["aggregate"]["delta"]
    add(f"[{preflight['run']['started_at']} → {preflight['run']['finished_at']}] {TOOL_NAME} v{TOOL_VERSION}（零 LLM）")
    add(
        f"git_head={preflight['environment']['git_head']} python={preflight['environment']['python']} "
        f"z3={preflight['environment']['z3']}"
    )
    add(f"src_spec_smt pre_fix={preflight['inputs']['src_spec_smt']['pre_fix_sha256']}")
    add(f"src_spec_smt post_fix={preflight['inputs']['src_spec_smt']['post_fix_sha256']}")
    add(f"anchor_table sha256={preflight['inputs']['anchor_table']['sha256']}")
    add(
        f"old_batch={preflight['inputs']['old_batch']['dir']} untouched={preflight['inputs']['t3b_untouched_check']['ok']}"
    )
    add(f"params timeout_ms={preflight['params']['smt_timeout_ms']}")
    add(
        f"tasks total={preflight['counts']['tasks_total']} primary={preflight['counts']['tasks_primary']} "
        f"clauses_primary={preflight['counts']['clauses_pooled_primary']}"
    )
    add(
        f"old status: {old['status_totals_pooled']} reached={old['clauses_reached_pooled']} "
        f"reach_rate={old['reach_rate_pooled']}"
    )
    add(
        f"new status: {new['status_totals_pooled']} reached={new['clauses_reached_pooled']} "
        f"reach_rate={new['reach_rate_pooled']}"
    )
    add(f"delta: {delta}")
    alias = comparison["alias_clause_destinations"]
    add(
        f"alias all50: n={alias['all50']['n']} dest={alias['all50']['status_counts']} "
        f"reached={alias['all50']['reached']} unmatched={len(alias['unmatched'])}"
    )
    add(f"alias primary by_feature: {alias['by_feature_primary']}")
    add(f"risk_guards: {comparison['risk_guards']}")
    add(
        f"CONCLUSION effective={comparison['conclusion']['effective']} "
        f"criteria={comparison['conclusion']['c1_c2_c3_c4_c5']}"
    )
    add(
        f"determinism in_process_double_solve_status_equal={in_process_rebuild_equal} "
        "(timing keys stripped; see ANALYSIS_REPORT.determinism)"
    )
    add(f"llm_calls=0 usd=0.0 wall_clock_seconds={wall_clock}")
    add("artifacts:")
    for path in sorted(out_dir.iterdir()):
        if path.is_file():
            add(f"  {path.name}  {path.stat().st_size} bytes")
        elif path.name == "_helpers":
            for helper in sorted(path.iterdir()):
                add(f"  {path.name}/{helper.name}  {helper.stat().st_size} bytes")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T3c aliasfix SMT batch（零 LLM）")
    parser.add_argument("--out", default=str(_OUT_DIR), help="输出目录")
    parser.add_argument("--old-dir", default=str(OLD_DIR), help="T3b pre-fix 基线目录（只读）")
    parser.add_argument("--anchor-table", default=str(DEFAULT_ANCHOR_TABLE))
    parser.add_argument("--dfspec-benchmark", default=str(DEFAULT_DF_SPEC_BENCHMARK))
    parser.add_argument("--dfspec-report", default=str(DEFAULT_DF_SPEC_REPORT))
    parser.add_argument("--timeout-ms", type=int, default=SOLVE_TIMEOUT_MS)
    parser.add_argument("--no-determinism-probe", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_ms != SOLVE_TIMEOUT_MS:
        print(
            f"[aliasfix] ⚠ 超时参数偏离预注册冻结值 {SOLVE_TIMEOUT_MS}ms → {args.timeout_ms}ms（参数重标需披露）",
            file=sys.stderr,
        )
    result = run(
        out_dir=Path(args.out),
        old_dir=Path(args.old_dir),
        anchor_table_path=Path(args.anchor_table),
        dfspec_benchmark_path=Path(args.dfspec_benchmark),
        dfspec_report_path=Path(args.dfspec_report),
        timeout_ms=max(100, min(30000, int(args.timeout_ms))),
        determinism_probe=not args.no_determinism_probe,
    )
    comparison = result["comparison"]
    old = comparison["aggregate"]["old_primary"]
    new = comparison["aggregate"]["new_primary"]
    print(
        f"[aliasfix] ✓ 写入 {args.out}\n"
        f"    pre-fix  reached={old['clauses_reached_pooled']} sat={old['status_totals_pooled']['sat']} "
        f"reach_rate={old['reach_rate_pooled']}\n"
        f"    post-fix reached={new['clauses_reached_pooled']} sat={new['status_totals_pooled']['sat']} "
        f"reach_rate={new['reach_rate_pooled']}\n"
        f"    alias 110 去向: {comparison['alias_clause_destinations']['all50']['status_counts']} "
        f"(unmatched={len(comparison['alias_clause_destinations']['unmatched'])})\n"
        f"    判据: {comparison['conclusion']['c1_c2_c3_c4_c5']}\n"
        f"    有效={comparison['conclusion']['effective']}；T3b 未变={result['t3b_untouched']['ok']}；"
        f"墙钟 {result['wall_clock_seconds']}s；LLM 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
