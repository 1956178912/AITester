"""P-1（2026-10-18）规格可执行示例通道质量重放：**A=无示例 vs B=LLM spec-only 示例**。

背景
----
O-1 仪器治疗后 oracle 分类从 `fp 29` 降到 `fp 2`（仅断言型），但 **correct
仍为 0**：语义质量瓶颈 = "机器化断言不触达缺陷行为"。P-1 给 oracle 增加
**规格可执行示例**通道（`src/specs/spec_ir.py::parse_logic_analysis` 透传
`examples` → `compile_spec_oracle` 逐示例断言），本工具对 df_spec 归档双臂
做受控 A/B 质量重放：

    A = 无示例（O-1 当前编译产物）
    B = 同一锚材料 + **LLM spec-only 生成**的示例（不发送缺陷代码）

逐测试分类复用 O-1 口径：oracle 测试在 buggy/fixed 两侧执行，崩溃由 harness
转为 skipped（单列 unavailable，不混入 fp）；断言失败保留为 fp/correct 等。
非法/生成失败示例透传空（B 回退 A），生成状态可审计。

预算与纪律
----------
- 示例生成 **每任务 1 次 LLM 调用**（默认小 max_tokens=512；`--no-llm-cache`
  强制真实调用以便成本可测；预算目标 ≤ $0.1，`--limit` 默认 20）；
- 分类零 LLM（仅本地 pytest 子进程）；
- 禁止外推：B 臂示例来自 LLM **spec-only** 生成，n 小、探索性；
  生成器只看规约（Planner 锚 `logic_analysis` / 人类 docstring），**不发送
  缺陷代码**（防 oracle-from-implementation / misguided 固化）。

输出
----
`--out` 目录下 `ORACLE_EXAMPLES_REPORT.json`（本文件生成）+ `README.md`
（人工撰写，含协议/表/成本/限制）+ `SHA256SUMS`（checksum_results.py 口径）。

用法::

    .venv/bin/python -m experiments.oracle_examples_replay \
        --out experiments/results/p_round_oracle_examples_20261018 \
        --limit 20 --jobs 4 --no-llm-cache
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments import misguided_metrics as mm  # noqa: E402
from experiments import oracle_quality_replay as oq  # noqa: E402
from experiments import spec_examples_generator as gen  # noqa: E402
from experiments.misguided_metrics import (  # noqa: E402
    _display_path,
    _now_iso,
    _task_program,
    _truncate,
    body_digest,
    collect_siblings,
    list_artifact_arms,
    load_artifact,
    materialize_version,
    resolve_buggy_source,
    resolve_quixbugs_roots,
    run_side,
    select_rows,
    sha256_file,
    sha256_text,
)
from src.specs import extract_signature_params, parse_logic_analysis  # noqa: E402
from src.specs.spec_ir_v2 import self_validate_examples  # noqa: E402

SCHEMA_VERSION = "oracle_examples_metric/1"
TOOL_NAME = "experiments.oracle_examples_replay"
TOOL_VERSION = "1.0.0"
DEFAULT_OUT = _REPO_ROOT / "experiments/results/p_round_oracle_examples_20261018"
DEFAULT_ANCHOR_TABLE = _REPO_ROOT / "experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json"
_DEFAULT_DF_SPEC = _REPO_ROOT / "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json"
_DEFAULT_DF = _REPO_ROOT / "experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json"
DEFAULT_ARTIFACTS: tuple[Path, ...] = (_DEFAULT_DF_SPEC, _DEFAULT_DF)
CONDITION_A = "A_no_examples"
CONDITION_B = "B_llm_examples"
CONDITIONS: tuple[str, ...] = (CONDITION_A, CONDITION_B)
# 权威分母口径：oracle 测试级四分类 + unavailable（不可用单列）
ORACLE_CATEGORIES: tuple[str, ...] = ("correct", "fp", "silent", "misguided", "unavailable")


class ReuseExamplesError(RuntimeError):
    """P-1.1 复用既有 P-1 报告失败（缺失/非法 JSON/结构不符；fail-closed）。"""


_STRUCTURAL_REASONS = (
    "artifact_row_malformed",
    "empty_generated_test",
    "invalid_program_name",
    "generated_test_syntax_error",
    "missing_buggy_source",
    "buggy_source_unvalidated",
    "anchor_miss",
    "anchor_malformed",
    "anchor_spec_unparseable",
    "missing_fixed_material",
    "fixed_material_unparseable",
    "injection_failed",
    "replay_unavailable",
    "materialize_failed",
    "unknown",
)


def _skip(record: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    record["status"] = "structural_skip"
    record["skip_reason"] = reason
    record["skip_detail"] = _truncate(detail, 500)
    return record


def _enrich_oracle_rows(
    rows: list[dict[str, Any]],
    buggy_notes: dict[str, dict[str, Any]],
    fixed_notes: dict[str, dict[str, Any]],
) -> None:
    """O-1 口径归因：fp 细分（断言型/仪器失效型）与 skip 原因（就地写 rows）。"""
    for row in rows:
        node = str(row.get("node"))
        buggy_note = buggy_notes.get(node) or {}
        fixed_note = fixed_notes.get(node) or {}
        row["buggy_failure_kind"] = buggy_note.get("kind")
        row["fixed_failure_kind"] = fixed_note.get("kind")
        row["fp_kind"] = oq.classify_fp_kind(fixed_note) if row.get("cls") == "fp" else None
        row["buggy_skip_reason"] = buggy_note.get("skip_reason") if buggy_note.get("tag") == "skipped" else None
        row["fixed_skip_reason"] = fixed_note.get("skip_reason") if fixed_note.get("tag") == "skipped" else None


def _classify_condition(
    *,
    merged_test: str,
    program: str,
    buggy_code: str,
    fixed_code: str,
    siblings: dict[str, str],
    pytest_timeout_s: float,
    collect_timeout_s: float,
    file_timeout_s: float,
) -> dict[str, Any]:
    """对单个条件（A 或 B）的注入产物做 O-1 式逐测试分类。"""
    tmpdir = Path(tempfile.mkdtemp(prefix=f"p1_{program}_"))
    try:
        buggy_dir = tmpdir / "buggy"
        fixed_dir = tmpdir / "fixed"
        try:
            materialize_version(buggy_dir, program, buggy_code, merged_test, siblings)
            materialize_version(fixed_dir, program, fixed_code, merged_test, siblings)
        except OSError as e:
            return {
                "status": "not_run",
                "skip_reason": "materialize_failed",
                "skip_detail": str(e),
                "counts": {},
                "unclassifiable": {},
            }
        buggy_side = run_side(
            version_dir=buggy_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
        fixed_side = run_side(
            version_dir=fixed_dir,
            pytest_timeout_s=pytest_timeout_s,
            collect_timeout_s=collect_timeout_s,
            file_timeout_s=file_timeout_s,
        )
        buggy_notes = oq.parse_junit_failure_notes(buggy_dir / "junit.xml")
        fixed_notes = oq.parse_junit_failure_notes(fixed_dir / "junit.xml")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    side_failure = mm._side_failure_reason(buggy_side, fixed_side)
    if side_failure is not None:
        return {
            "status": "not_run",
            "skip_reason": "replay_unavailable",
            "skip_detail": f"{side_failure[0]}: {side_failure[1]}",
            "counts": dict.fromkeys(ORACLE_CATEGORIES, 0),
            "unclassifiable": {},
        }
    nodes = sorted(
        {
            *[str(n) for n in (buggy_side.get("collected") or [])],
            *[str(n) for n in (fixed_side.get("collected") or [])],
            *[str(n) for n in (buggy_side.get("outcomes") or {})],
            *[str(n) for n in (fixed_side.get("outcomes") or {})],
        }
    )
    oracle_nodes = [n for n in nodes if oq.is_oracle_node(n)]
    if not oracle_nodes:
        return {
            "status": "not_run",
            "skip_reason": "replay_unavailable",
            "skip_detail": "注入产物未收集到 oracle 测试节点",
            "counts": dict.fromkeys(ORACLE_CATEGORIES, 0),
            "unclassifiable": {},
        }
    rows, counts, unclassifiable = oq.classify_oracle_outcomes(
        oracle_nodes,
        buggy_side.get("outcomes") or {},
        fixed_side.get("outcomes") or {},
        buggy_missing_reason=buggy_side.get("missing_reason") or "missing_side",
        fixed_missing_reason=fixed_side.get("missing_reason") or "missing_side",
    )
    _enrich_oracle_rows(rows, buggy_notes, fixed_notes)
    counts_out = {cls: int(counts.get(cls, 0)) for cls in oq.ORACLE_CLASSES}
    counts_out["unavailable"] = int(sum(v for v in unclassifiable.values() if v))
    fp_kinds = Counter(str(r.get("fp_kind") or oq.FP_UNATTRIBUTED) for r in rows if r.get("cls") == "fp")
    skip_reasons = Counter(
        str(r.get("fixed_skip_reason") or r.get("buggy_skip_reason") or "skipped_other")
        for r in rows
        if r.get("buggy") == "skip" or r.get("fixed") == "skip"
    )
    return {
        "status": "ok",
        "skip_reason": None,
        "skip_detail": "",
        "counts": counts_out,
        "fp_kind_counts": dict(sorted(fp_kinds.items())),
        "skip_reason_counts": dict(sorted(skip_reasons.items())),
        "unclassifiable": {k: v for k, v in unclassifiable.items() if v},
        "n_oracle_tests": len(oracle_nodes),
        "n_collected_total": len(nodes),
        "tests": rows,
        "merged_test_sha256": sha256_text(merged_test),
    }


def _condition_examples(generation: dict[str, Any], condition: str) -> list[dict[str, Any]]:
    """条件臂使用的示例：A 恒空；B 取生成记录里的 examples（含 reuse 模式）。

    注意：不能只认 ``status=="ok"``——P-1.1 `--reuse-examples` 的记录
    status 为 ``"reused"``（零 LLM），示例同样必须进入 B 臂。
    """
    if condition != CONDITION_B:
        return []
    return list(generation.get("examples") or [])


def _build_spec(material: dict[str, Any], examples: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """把锚材料 + 示例（可选）解析为 SpecIR（examples=None 时去掉任何既有示例）。"""
    payload = dict(material)
    payload.pop("examples", None)
    if examples:
        payload["examples"] = list(examples)
    return parse_logic_analysis(payload)


def analyze_row(
    row: dict[str, Any],
    *,
    anchors: dict[str, dict[str, Any]],
    roots: list[Path],
    examples_by_task: dict[str, dict[str, Any]],
    config: dict[str, Any],
    siblings_cache: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """单任务 A/B 双臂重放分析（每臂独立物化 buggy/fixed 两侧）。"""
    task_id = str(row.get("task_id") or "")
    raw_meta = row.get("task_metadata")
    task_metadata: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    generated_test = str(row.get("generated_test") or "")
    program = _task_program(task_id, task_metadata)
    record: dict[str, Any] = {
        "task_id": task_id or "(缺失 task_id)",
        "program": program or None,
        "analysis_set": "defect_program" if program and not program.endswith("_test") else "driver_or_unknown",
        "status": "ok",
        "skip_reason": None,
        "skip_detail": "",
        "examples_generation": examples_by_task.get(task_id)
        or {"status": "missing", "examples": [], "reason": "not_generated"},
        "injection": {CONDITION_A: None, CONDITION_B: None},
        "conditions": {CONDITION_A: None, CONDITION_B: None},
        "examples_self_validation": None,
        "timing": {"wall_s": 0.0},
    }
    t0 = time.time()

    if not task_id or not task_metadata:
        return _finish_skip(_skip(record, "artifact_row_malformed", "归档行缺 task_id/task_metadata"), t0)
    if not generated_test.strip():
        return _finish_skip(_skip(record, "empty_generated_test", "归档 generated_test 为空"), t0)
    if not oq._PY_IDENT_RE.match(program or ""):
        return _finish_skip(_skip(record, "invalid_program_name", f"程序名非法: {program!r}"), t0)
    if mm._count_ast_test_defs(generated_test) < 0:
        return _finish_skip(_skip(record, "generated_test_syntax_error", "generated_test 无法 ast.parse"), t0)
    fixed_code = str(task_metadata.get("fixed") or "")
    if not fixed_code.strip():
        return _finish_skip(_skip(record, "missing_fixed_material", "task_metadata.fixed 为空"), t0)
    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        return _finish_skip(_skip(record, "fixed_material_unparseable", f"fixed 语法错误: {e}"), t0)
    try:
        buggy_code, buggy_path = resolve_buggy_source(program, roots)
    except mm.MaterialError as e:
        return _finish_skip(_skip(record, "missing_buggy_source", e.detail), t0)
    digest, anchor_entry = oq.lookup_anchor(anchors, buggy_code)
    if anchor_entry is None:
        return _finish_skip(_skip(record, "anchor_miss", f"缺陷版源码哈希不在锚表: {digest[:16]}…"), t0)
    logic_analysis = anchor_entry.get("logic_analysis")
    function_name = anchor_entry.get("function_name")
    if not isinstance(logic_analysis, dict) or not isinstance(function_name, str):
        return _finish_skip(_skip(record, "anchor_malformed", "锚表条目缺 logic_analysis/function_name"), t0)
    record["anchor"] = {
        "key_sha256": digest,
        "function_name": function_name,
        "human_spec": isinstance(anchor_entry.get("human_spec"), str),
    }
    if program not in siblings_cache:
        siblings_cache[program] = collect_siblings(buggy_path)
    siblings = siblings_cache[program]
    module_name = str(task_id).split("__")[-1].replace("-", "_")[:50]
    suggested = task_metadata.get("suggested_function")
    target_function = str(suggested).strip() if isinstance(suggested, str) and suggested.strip() else function_name
    gen_record = record["examples_generation"]
    for condition in CONDITIONS:
        examples = _condition_examples(gen_record, condition)
        spec = _build_spec(logic_analysis, examples)
        if condition == CONDITION_B and spec is not None:
            # R-2：示例自校验审计（与编译器同一纯函数；不改变示例内容本身）
            _sig = extract_signature_params(buggy_code, target_function)
            _kept, _validation = self_validate_examples(spec, _sig, spec.get("examples") or [])
            record["examples_self_validation"] = _validation
        if spec is None:
            record["injection"][condition] = {"verdict": "not_attempted", "injected": False}
            record["conditions"][condition] = {
                "status": "not_run",
                "skip_reason": "anchor_spec_unparseable",
                "counts": dict.fromkeys(ORACLE_CATEGORIES, 0),
                "unclassifiable": {},
            }
            continue
        state = {
            "target_code": buggy_code,
            "module_name": module_name,
            "target_function": target_function,
            "spec_ir": spec,
        }
        merged, injected, verdict = oq.production_inject_oracle(generated_test, state)  # type: ignore[arg-type]
        record["injection"][condition] = {
            "verdict": verdict,
            "injected": bool(injected),
            "oracle_code_sha256": sha256_text(merged[len(generated_test) :]) if injected else None,
        }
        if not injected:
            record["conditions"][condition] = {
                "status": "not_run",
                "skip_reason": "injection_failed",
                "counts": dict.fromkeys(ORACLE_CATEGORIES, 0),
                "unclassifiable": {},
            }
            continue
        record["conditions"][condition] = _classify_condition(
            merged_test=merged,
            program=program,
            buggy_code=buggy_code,
            fixed_code=fixed_code,
            siblings=siblings,
            pytest_timeout_s=float(config["per_test_timeout_s"]),
            collect_timeout_s=float(config["collect_timeout_s"]),
            file_timeout_s=float(config["file_timeout_s"]),
        )
    return _finish_skip(record, t0)


def _finish_skip(record: dict[str, Any], t0: float) -> dict[str, Any]:
    record["timing"]["wall_s"] = round(time.time() - t0, 3)
    return record


def _condition_public(record: dict[str, Any], condition: str) -> dict[str, Any]:
    """导出条件记录（去掉逐测试明细，控制报告体积；明细在 JSON 逐任务保留摘要）。"""
    payload = dict(record.get("conditions", {}).get(condition) or {})
    payload.pop("tests", None)
    return payload


def _category_of(record: dict[str, Any], condition: str) -> str:
    """任务级主类别（用于 A→B 转移）：correct > fp > silent > unavailable。"""
    cond = record.get("conditions", {}).get(condition) or {}
    if cond.get("status") != "ok":
        return "unavailable"
    counts = cond.get("counts") or {}
    # 任务级主类别优先级：correct > fp > misguided > silent（P-1：misguided 是
    # "oracle 把 buggy 判过、fixed 判败"的独立信号，不能并入 unavailable）。
    for cls in ("correct", "fp", "misguided", "silent"):
        if int(counts.get(cls, 0) or 0) > 0:
            return cls
    return "unavailable"


def aggregate_arm(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """臂级聚合：A/B 条件逐类计数 + 任务级转移 + 示例注入审计。"""
    conditions: dict[str, Any] = {}
    for condition in CONDITIONS:
        counts = dict.fromkeys(ORACLE_CATEGORIES, 0)
        fp_kinds: Counter[str] = Counter()
        skip_reasons: Counter[str] = Counter()
        injected_tasks = 0
        measurable_tasks = 0
        n_oracle_tests = 0
        for task in tasks:
            injection = (task.get("injection") or {}).get(condition) or {}
            if injection.get("injected"):
                injected_tasks += 1
            cond = (task.get("conditions") or {}).get(condition) or {}
            for cls in ORACLE_CATEGORIES:
                counts[cls] += int((cond.get("counts") or {}).get(cls, 0) or 0)
            if cond.get("status") == "ok":
                measurable_tasks += 1
                n_oracle_tests += int(cond.get("n_oracle_tests") or 0)
                for kind, value in (cond.get("fp_kind_counts") or {}).items():
                    fp_kinds[str(kind)] += int(value or 0)
                for reason, value in (cond.get("skip_reason_counts") or {}).items():
                    skip_reasons[str(reason)] += int(value or 0)
        classifiable = counts["correct"] + counts["fp"] + counts["silent"] + counts["misguided"]
        conditions[condition] = {
            "n_tasks": len(tasks),
            "n_tasks_injected": injected_tasks,
            "n_tasks_measurable": measurable_tasks,
            "n_oracle_tests_measured": n_oracle_tests,
            "counts": counts,
            "n_classifiable": classifiable,
            "n_unavailable": counts["unavailable"],
            "rates_of_classifiable": {
                cls: (round(counts[cls] / classifiable, 6) if classifiable else None)
                for cls in ("correct", "fp", "silent", "misguided")
            },
            "fp_kind_counts": dict(sorted(fp_kinds.items())),
            "skip_reason_counts": dict(sorted(skip_reasons.items())),
        }
    filter_totals: Counter[str] = Counter()
    filter_reasons: Counter[str] = Counter()
    n_filter_tasks = 0
    n_drop_tasks = 0
    for task in tasks:
        validation = task.get("examples_self_validation") or {}
        if not validation:
            continue
        n_filter_tasks += 1
        for key in (
            "n_input",
            "n_kept",
            "n_dropped",
            "n_fully_validated",
            "n_partially_validated",
            "n_no_post_clause",
            "n_unevaluable",
            "n_precondition_false_kept",
        ):
            filter_totals[key] += int(validation.get(key) or 0)
        if int(validation.get("n_dropped") or 0) > 0:
            n_drop_tasks += 1
        for reason, count in (validation.get("reasons") or {}).items():
            filter_reasons[str(reason)] += int(count or 0)
    transitions: Counter[str] = Counter()
    transition_tasks: list[dict[str, Any]] = []
    for task in tasks:
        cat_a = _category_of(task, CONDITION_A)
        cat_b = _category_of(task, CONDITION_B)
        transitions[f"{cat_a}->{cat_b}"] += 1
        if cat_a != cat_b:
            transition_tasks.append(
                {
                    "task_id": task.get("task_id"),
                    "A": cat_a,
                    "B": cat_b,
                    "examples_n": len(task["examples_generation"].get("examples") or []),
                }
            )
    return {
        "conditions": conditions,
        "examples_self_validation": {
            "n_tasks_with_examples": n_filter_tasks,
            "n_tasks_with_drop": n_drop_tasks,
            **{key: int(value) for key, value in sorted(filter_totals.items())},
            "reasons": dict(sorted(filter_reasons.items())),
        },
        "task_category_transitions": dict(sorted(transitions.items())),
        "transition_tasks": transition_tasks,
    }


def generation_summary(generations: list[dict[str, Any]], price_table: dict[str, Any]) -> dict[str, Any]:
    """示例生成审计：状态分布、示例数、LLM 调用/token/成本、prompt 规模。"""
    status_counts = Counter(str(g.get("status")) for g in generations)
    usages = [g.get("usage") or {} for g in generations]
    input_tokens = sum(int(u.get("input_tokens", 0) or 0) for u in usages)
    output_tokens = sum(int(u.get("output_tokens", 0) or 0) for u in usages)
    llm_calls = sum(int(u.get("llm_calls", 0) or 0) for u in usages)
    cache_hits = sum(int(u.get("cache_hits", 0) or 0) for u in usages)
    model = str(generations[0].get("model") or "unknown") if generations else "unknown"
    cost = gen.estimate_cost_usd(
        model,
        {"input_tokens": input_tokens, "output_tokens": output_tokens},
        price_table,
    )
    tasks_with_examples = [g for g in generations if g.get("examples")]
    summary = {
        "n_tasks": len(generations),
        "status_counts": dict(sorted(status_counts.items())),
        "n_tasks_with_examples": len(tasks_with_examples),
        "n_examples_total": sum(len(g.get("examples") or []) for g in generations),
        "examples_per_ok_task": _mean([len(g.get("examples") or []) for g in tasks_with_examples]),
        "llm_calls": llm_calls,
        "cache_hits": cache_hits,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost,
        "model": model,
        "per_task": [
            {
                "task_id": g.get("task_id"),
                "status": g.get("status"),
                "reason": g.get("reason"),
                "n_examples": len(g.get("examples") or []),
                "prompt_sha256": g.get("prompt_sha256"),
                "wall_s": g.get("wall_s"),
                "llm_calls": (g.get("usage") or {}).get("llm_calls"),
            }
            for g in generations
        ],
    }
    # AB-15c：算不出钱时把**机制名**随工件带走（判定与归因同源，见
    # `spec_examples_generator.price_block_reason_for`）。披露键只在真拒绝时写入
    # ⇒ 已入库的 P-1 工件（USD 已计价）返回域逐键不变。
    if cost is None:
        summary["cost_unpriced_reason"] = gen.price_block_reason_for(model, price_table)
    return summary


def _mean(values: list[Any]) -> float | None:
    nums = [float(v) for v in values]
    return round(sum(nums) / len(nums), 3) if nums else None


def render_readme(report: dict[str, Any]) -> str:
    """从 JSON report 渲染 README（数字全部来自工件，不手写）。"""
    lines: list[str] = []
    add = lines.append
    add("# P-1 规格可执行示例通道：质量重放（A=无示例 vs B=LLM spec-only 示例）")
    add("")
    add("> **性质**：探索性机制验证（**不作 confirmatory**）。B 臂示例由 LLM（deepseek-flash）")
    add("> **spec-only** 生成（只发规约材料，**不发缺陷代码**），n 小；结论不得外推为能力主张。")
    add("> 逐测试分类复用 O-1 口径（崩溃→skipped/unavailable 单列，断言失败保留）。")
    add("")
    add("## 1. 输入与命令")
    add("")
    add("| 输入 | sha256 |")
    add("|---|---|")
    for entry in report.get("inputs") or []:
        add(f"| `{entry['path']}` | `{entry['sha256']}` |")
    anchor = report.get("anchor_table") or {}
    add(f"| `{anchor.get('path')}` | `{anchor.get('sha256')}` |")
    add("")
    add("复算命令：")
    add("")
    add("```bash")
    add(" ".join(str(x) for x in report.get("command") or []))
    add("```")
    add("")
    add("## 2. 示例生成审计（spec-only；每任务 1 次调用）")
    add("")
    generation = report.get("generation") or {}
    add(
        f"- 任务数 {generation.get('n_tasks')}；状态分布 {generation.get('status_counts')}；"
        f"有示例任务 {generation.get('n_tasks_with_examples')}；示例总数 {generation.get('n_examples_total')}"
    )
    est_cost = generation.get("estimated_cost_usd")
    if est_cost is None:
        # AB-15c：改前这里无条件给 `estimated_cost_usd` 加 `$` 前缀，实测未登记模型与
        # `qwen-long`（CNY）都落 `**$None**`、`0.0` 落 `**$0.0**`——"无法估算"与"确实没花钱"
        # 只差一个词，却共用同一个美元形状，且没有一行说清是哪条机制。
        cost_txt = f"**无法估算（{generation.get('cost_unpriced_reason') or '机制未记录'}）**"
    else:
        cost_txt = f"**${est_cost}**"
    add(
        f"- LLM 调用 {generation.get('llm_calls')}（缓存命中 {generation.get('cache_hits')}）；"
        f"tokens in/out = {generation.get('input_tokens')}/{generation.get('output_tokens')}；"
        f"估算成本 {cost_txt}（价目：experiments/price_table.json）"
    )
    add("")
    add("## 3. A/B 前后对照（oracle 测试级；分母 = 可分类 oracle 测试数）")
    add("")
    add("| 指标 | A 无示例 | B 加示例 |")
    add("|---|---|---|")
    arms = report.get("arms") or []
    for arm in arms:
        cond = arm["aggregate"]["conditions"]
        add(f"| — `{arm['arm']}` — | | |")
        for key in ("n_tasks_injected", "n_tasks_measurable", "n_oracle_tests_measured", "n_classifiable"):
            add(f"| {key} | {cond[CONDITION_A].get(key)} | {cond[CONDITION_B].get(key)} |")
        for cls in ORACLE_CATEGORIES:
            add(f"| `{cls}` 计数 | {cond[CONDITION_A]['counts'].get(cls)} | {cond[CONDITION_B]['counts'].get(cls)} |")
        add(f"| A→B 任务级转移 | {arm['aggregate']['task_category_transitions']} | |")
    add("")
    add("## 4. 口径与限制")
    add("")
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add("")
    return "\n".join(lines) + "\n"


def build_report(
    *,
    inputs: list[dict[str, Any]],
    anchor_info: dict[str, Any],
    arms: list[dict[str, Any]],
    generation: dict[str, Any],
    config: dict[str, Any],
    reuse_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装确定性报告 body（时间戳/墙钟只进 run_meta）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "metric_definition": {
            "name": "P-1 规格可执行示例通道（A=无示例 vs B=LLM spec-only 示例）",
            "condition_A": "O-1 现状编译产物（锚材料 logic_analysis → pre/post/boundary 通道；无示例）",
            "condition_B": "同一锚材料 + LLM spec-only 生成的 examples（parse_logic_analysis 透传 → compile_spec_oracle 逐示例断言）",
            "classification": (
                "oracle 测试在 buggy/fixed 两侧执行：correct=buggy 败∧fixed 过；"
                "misguided=buggy 过∧fixed 败；silent=两侧过；fp=fixed 败（断言型，含两侧败）；"
                "unavailable=skipped/timeout/collect/import/材料等不可判（O-1 harness：崩溃→skip）"
            ),
            "denominator": "可分类 oracle 测试数（correct/fp/silent/misguided）；unavailable 单列、不进分母",
            "evidence_status": "探索性验证（非 confirmatory）；B 臂示例为 LLM spec-only 生成、n 小，不得外推",
        },
        "config": config,
        "inputs": inputs,
        "anchor_table": anchor_info,
        "reuse_examples": reuse_info,
        "generation": generation,
        "arms": arms,
        "limitations": [
            "B 臂示例来自 LLM spec-only 生成（不发送缺陷代码）；示例正确性完全取决于规约可执行程度，n≤limit、探索性",
            "每任务仅 1 次生成调用（无重试采样）；生成失败/为空的任务 B 回退为 A（逐任务可审计，不作静默替换）",
            "分类复用 O-1 口径：崩溃→skip/unavailable 单列；断言失败保留为 fp（断言型）/correct 等",
            "正确率不提升 ≠ 通道无效：示例通道能力由单测自含 demo（buggy/fixed fixture）证明——若生产侧 correct 仍 0，应归因示例质量/规约可执行程度，而非通道不存在",
            "B 臂 LLM 调用存在模型随机性（temperature=0 但服务端非严格确定）；工件记录了 prompt/response sha256 与 usage",
            "描述性度量；不提供显著性推断；与 M-2/O-1 数字不同口径（A 臂是 O-1 后编译产物）",
            "df_spec 归档两臂的锚材料相同（oracle 与源臂无关），B 臂示例按 task_id 生成一次、两臂复用（预算纪律）",
            "B 臂治疗同时包含：示例断言通道 + 有示例时丢弃 0 字面量退化绑定（避免 fixed 侧自伤 crash）；"
            "无示例 A 臂保持 O-1 行为，因此 A/B 是整包治疗对比、不是单变量消融",
            "实现偏差：P-1 同时修复 O-1 multi-param boundary pre 断言的 NameError（参数名绑定），"
            "故『无示例与 O-1 逐字节不变』在 multi-param boundary 子集上不再成立（详见 README §8）",
        ],
    }


def _resolve_selection(artifacts: list[Path], arms_requested: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in artifacts:
        resolved = str(path.resolve())
        if resolved in seen:
            raise mm.ArtifactError(f"工件重复传入: {path}")
        seen.add(resolved)
        artifact = load_artifact(path)
        available = list_artifact_arms(artifact)
        selected = arms_requested or available
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise mm.ArtifactError(f"工件 {path} 内不存在臂 {unknown}（可用: {available}）")
        entries.append(
            {
                "path": path,
                "artifact_label": _display_path(path),
                "sha256": sha256_file(path),
                "arms": selected,
                "data": artifact,
            }
        )
    return entries


def _filter_rows(
    rows: list[dict[str, Any]], *, limit: int, include_driver: bool, task_ids: list[str]
) -> list[dict[str, Any]]:
    """按驱动任务开关/--task-id 过滤 + task_id 排序 + --limit 截断。"""
    wanted = set(task_ids or [])
    candidates = [
        r
        for r in rows
        if (include_driver or not str(r.get("task_id", "")).endswith("_test"))
        and (not wanted or str(r.get("task_id")) in wanted)
    ]
    candidates.sort(key=lambda r: str(r.get("task_id") or ""))
    if limit > 0:
        candidates = candidates[:limit]
    return candidates


def _load_reused_examples(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """P-1.1：从既有 P-1 报告复用已生成的 examples（**不再调用 LLM**）。

    Args:
        path: 既有 `ORACLE_EXAMPLES_REPORT.json`。

    Returns:
        (task_id → 生成记录, provenance{path,sha256,body_digest})。

    Raises:
        SystemExit 值由调用方转成 return 2（fail-closed）。
    """
    if not path.is_file():
        raise ReuseExamplesError(f"复用报告不存在: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ReuseExamplesError(f"复用报告无法解析: {path}: {e}") from e
    report = payload.get("report") if isinstance(payload, dict) else None
    if not isinstance(report, dict) or not isinstance(report.get("arms"), list):
        raise ReuseExamplesError(f"复用报告结构不合法（缺 report.arms）: {path}")
    records: dict[str, dict[str, Any]] = {}
    for arm in report["arms"]:
        for task in arm.get("tasks") or []:
            task_id = str(task.get("task_id") or "")
            generation = task.get("examples_generation") or {}
            examples = generation.get("examples") or []
            if not task_id or task_id in records:
                continue
            records[task_id] = {
                "task_id": task_id,
                "status": "reused",
                "examples": examples,
                "reason": None,
                "prompt_sha256": generation.get("prompt_sha256"),
                "usage": {},
                "wall_s": 0.0,
                "reused_from": str(task_id),
            }
    provenance = {
        "path": _display_path(path),
        "sha256": sha256_file(path),
        "body_digest": (payload.get("run_meta") or {}).get("body_digest") if isinstance(payload, dict) else None,
        "n_reused_tasks": len(records),
    }
    return records, provenance


def _resolve_buggy_and_anchor(
    row: dict[str, Any], anchors: dict[str, dict[str, Any]], roots: list[Path]
) -> tuple[str, dict[str, Any], str] | None:
    """提取 (buggy_code, anchor_entry, program) 供示例生成（失败 → None）。"""
    task_id = str(row.get("task_id") or "")
    raw_meta = row.get("task_metadata")
    tm: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    program = _task_program(task_id, tm)
    if not task_id or not tm or not oq._PY_IDENT_RE.match(program or ""):
        return None
    try:
        buggy_code, _path = resolve_buggy_source(program, roots)
    except mm.MaterialError:
        return None
    _digest, anchor = oq.lookup_anchor(anchors, buggy_code)
    if not isinstance(anchor, dict):
        return None
    return buggy_code, anchor, program


def _command_line() -> list[str]:
    return ["python", "-m", "experiments.oracle_examples_replay", *sys.argv[1:]]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oracle_examples_replay",
        description=(
            "P-1 规格可执行示例通道质量重放：df_spec 归档双臂 A=无示例 vs "
            "B=LLM spec-only 示例（零 LLM 分类 + 每任务 1 次示例生成）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--artifact", action="append", default=[], metavar="PATH", help="批次 JSON（可重复；缺省 df_spec 两臂）"
    )
    parser.add_argument("--arm", action="append", default=[], metavar="NAME", help="只分析指定臂（可重复）")
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        metavar="TASK_ID",
        help="只分析指定 task_id（可重复；调试/受控子集用）",
    )
    parser.add_argument("--anchor-table", default=str(DEFAULT_ANCHOR_TABLE), metavar="PATH")
    parser.add_argument("--sha256sums", default=None, metavar="PATH", help="锚表 SHA256SUMS 覆盖")
    parser.add_argument("--quixbugs-root", default=None, metavar="DIR")
    parser.add_argument("--out", default=str(DEFAULT_OUT), metavar="DIR")
    parser.add_argument("--limit", type=int, default=20, help="每臂分析前 N 个缺陷程序任务（默认 20；0=全部）")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="并行任务数（默认 min(4,CPU)）")
    parser.add_argument("--per-test-timeout", type=float, default=1.0, metavar="SEC")
    parser.add_argument("--collect-timeout", type=float, default=60.0, metavar="SEC")
    parser.add_argument("--file-timeout", type=float, default=120.0, metavar="SEC")
    parser.add_argument("--examples-max-output-tokens", type=int, default=gen.DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--examples-cache-namespace", default="p1_oracle_examples_20261018")
    parser.add_argument(
        "--no-llm-cache", action="store_true", help="禁用 LLM 缓存（AITESTER_LLM_CACHE=0，确保真实调用/成本可测）"
    )
    parser.add_argument("--include-driver-tasks", action="store_true", help="包含 *_test 驱动任务（默认仅缺陷程序）")
    parser.add_argument("--skip-generation", action="store_true", help="跳过示例生成（调试：B 退化为 A）")
    parser.add_argument(
        "--reuse-examples",
        default=None,
        metavar="PATH",
        help="P-1.1：复用既有 P-1 报告的 examples（不再调用 LLM，仅重跑分类）",
    )
    parser.add_argument(
        "--report-name",
        default="ORACLE_EXAMPLES_REPORT",
        metavar="NAME",
        help="输出 JSON 文件名（不含 .json；P-1.1 用 ORACLE_EXAMPLES_REPORT_norm）",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--skip-markdown", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    out_dir = Path(args.out)
    try:
        anchor_table = oq.load_anchor_table(
            Path(args.anchor_table).expanduser(),
            sums_path=Path(args.sha256sums).expanduser() if args.sha256sums else None,
        )
        artifact_paths = [Path(p).expanduser() for p in args.artifact] or list(DEFAULT_ARTIFACTS)
        selection = _resolve_selection(artifact_paths, list(args.arm or []))
    except (oq.OracleQualityError, mm.ArtifactError) as e:
        print(f"[p1-examples] 错误: {e}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    roots = resolve_quixbugs_roots(args.quixbugs_root)
    anchors = anchor_table["anchors"]
    # 环境：示例生成预算/缓存口径
    if args.no_llm_cache:
        os.environ["AITESTER_LLM_CACHE"] = "0"
    os.environ.setdefault("LLM_MAX_OUTPUT_TOKENS", str(int(args.examples_max_output_tokens)))
    config = {
        "limit": int(args.limit),
        "jobs": int(args.jobs),
        "per_test_timeout_s": float(args.per_test_timeout),
        "collect_timeout_s": float(args.collect_timeout),
        "file_timeout_s": float(args.file_timeout),
        "examples": {
            "mode": "spec-only（不发送缺陷代码）",
            "max_examples": 5,
            "max_output_tokens": os.environ.get("LLM_MAX_OUTPUT_TOKENS"),
            "cache_namespace": args.examples_cache_namespace,
            "llm_cache_enabled": os.environ.get("AITESTER_LLM_CACHE", ""),
            "per_task_calls": 1,
            "generator": "experiments/spec_examples_generator.py",
        },
        "quixbugs_roots": [str(p) for p in roots],
        "example_assertion_comparison": (
            "normalized（P-1.1：tuple/list 递归→list、Iterator→list 一次性消费、str/bytes/dict 不误归）"
        ),
        "reuse_examples": args.reuse_examples,
        "examples_self_validation": {
            "enabled_default": True,
            "env": os.environ.get("SPEC_EXAMPLES_SELF_VALIDATE", "<unset: default true>"),
            "mode": "guarded_AST（比较/布尔/算术/常量/Name/List/Tuple；拒绝 Call/属性/下标/lambda/推导式）",
        },
        # R-2 起生产 injection 受 Q-1 双门守门：重放必须显式开启 EXAMPLES/EXEC，
        # 否则 B 臂示例会被 nodes 剥离（本报告配置记录实际 env 供复核）。
        "production_env": {
            "SPEC_ORACLE_EXEC_ENABLE": os.environ.get("SPEC_ORACLE_EXEC_ENABLE"),
            "SPEC_ORACLE_EXAMPLES_ENABLE": os.environ.get("SPEC_ORACLE_EXAMPLES_ENABLE"),
            "SPEC_EXAMPLES_SELF_VALIDATE": os.environ.get("SPEC_EXAMPLES_SELF_VALIDATE"),
        },
    }

    # ── 选择任务集合（按 task_id 排序，缺陷程序优先；limit 控制预算）────────
    task_rows: dict[str, dict[str, Any]] = {}
    for entry in selection:
        for arm in entry["arms"]:
            rows = select_rows(entry["data"], arm)
            candidates = _filter_rows(
                rows,
                limit=int(args.limit),
                include_driver=bool(args.include_driver_tasks),
                task_ids=list(args.task_id or []),
            )
            for row in candidates:
                task_rows.setdefault(str(row.get("task_id")), row)
    ordered_task_ids = sorted(task_rows)

    # ── 阶段 1：示例生成（每任务 1 次；跨臂复用，预算纪律）──────────────────
    # P-1.1：--reuse-examples 时完全跳过 LLM（零调用/零成本），仅复用示例。
    started = time.time()
    generations: list[dict[str, Any]] = []
    examples_by_task: dict[str, dict[str, Any]] = {}
    reuse_info: dict[str, Any] | None = None
    reuse_records: dict[str, dict[str, Any]] = {}
    if args.reuse_examples:
        try:
            reuse_records, reuse_info = _load_reused_examples(Path(args.reuse_examples).expanduser())
        except ReuseExamplesError as e:
            print(f"[p1-examples] 错误: {e}", file=sys.stderr)
            return 2
        for task_id in ordered_task_ids:
            record = reuse_records.get(task_id) or {
                "task_id": task_id,
                "status": "missing_reuse",
                "examples": [],
                "reason": "task_not_in_reuse_report",
                "usage": {},
            }
            generations.append(record)
            examples_by_task[task_id] = record
        if not args.quiet:
            print(
                f"[p1-examples] 复用 {reuse_info['n_reused_tasks']} 个任务的既有示例（零 LLM）：{reuse_info['path']}",
                flush=True,
            )
    elif not args.skip_generation:
        for index, task_id in enumerate(ordered_task_ids):
            row = task_rows[task_id]
            resolved = _resolve_buggy_and_anchor(row, anchors, roots)
            if resolved is None:
                record = {
                    "task_id": task_id,
                    "status": "error",
                    "examples": [],
                    "reason": "anchor_or_source_missing",
                    "usage": {},
                }
                generations.append(record)
                examples_by_task[task_id] = record
                continue
            buggy_code, anchor, program = resolved
            material = dict(anchor.get("logic_analysis") or {})
            if isinstance(anchor.get("human_spec"), str) and anchor.get("human_spec", "").strip():
                material["human_spec"] = anchor["human_spec"]
            function_name = str(anchor.get("function_name") or material.get("function_name") or program)
            signature_params = extract_signature_params(buggy_code, function_name)
            record = gen.generate_spec_examples(
                material,
                signature_params=signature_params,
                task_id=task_id,
                cache_namespace=args.examples_cache_namespace,
            )
            generations.append(record)
            examples_by_task[task_id] = record
            if not args.quiet:
                print(
                    f"[p1-examples] 生成 {index + 1}/{len(ordered_task_ids)} {task_id}: "
                    f"{record.get('status')} n={len(record.get('examples') or [])} "
                    f"reason={record.get('reason')}",
                    flush=True,
                )
    else:
        for task_id in ordered_task_ids:
            record = {"task_id": task_id, "status": "skipped", "examples": [], "reason": "skip_generation", "usage": {}}
            generations.append(record)
            examples_by_task[task_id] = record

    # ── 阶段 2：A/B 逐任务重放（零 LLM；分类复用 O-1 口径）────────────────
    arms_out: list[dict[str, Any]] = []
    siblings_cache: dict[str, dict[str, str]] = {}
    for entry in selection:
        for arm in entry["arms"]:
            rows = select_rows(entry["data"], arm)
            candidates = _filter_rows(
                rows,
                limit=int(args.limit),
                include_driver=bool(args.include_driver_tasks),
                task_ids=list(args.task_id or []),
            )
            arm_tasks: list[dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(args.jobs))) as pool:
                futures = [
                    pool.submit(
                        analyze_row,
                        row,
                        anchors=anchors,
                        roots=roots,
                        examples_by_task=examples_by_task,
                        config=config,
                        siblings_cache=siblings_cache,
                    )
                    for row in candidates
                ]
                arm_tasks = [future.result() for future in concurrent.futures.as_completed(futures)]
            arm_tasks.sort(key=lambda t: str(t.get("task_id") or ""))
            aggregate = aggregate_arm(arm_tasks)
            arms_out.append(
                {
                    "artifact": entry["artifact_label"],
                    "artifact_sha256": entry["sha256"],
                    "arm": arm,
                    "n_rows": len(candidates),
                    "aggregate": aggregate,
                    "tasks": [
                        {
                            **{
                                k: t.get(k)
                                for k in ("task_id", "program", "analysis_set", "status", "skip_reason", "skip_detail")
                            },
                            "examples_generation": {
                                "status": (t.get("examples_generation") or {}).get("status"),
                                "reason": (t.get("examples_generation") or {}).get("reason"),
                                "n_examples": len((t.get("examples_generation") or {}).get("examples") or []),
                                # P-1 审计：保留实际生成的示例（LLM spec-only 产物；不落 prompt 原文）
                                "examples": (t.get("examples_generation") or {}).get("examples") or [],
                                "prompt_sha256": (t.get("examples_generation") or {}).get("prompt_sha256"),
                            },
                            "injection": t.get("injection"),
                            "examples_self_validation": t.get("examples_self_validation"),
                            "conditions": {c: _condition_public(t, c) for c in CONDITIONS},
                            "category": {c: _category_of(t, c) for c in CONDITIONS},
                        }
                        for t in arm_tasks
                    ],
                }
            )
            if not args.quiet:
                cond = aggregate["conditions"]
                print(
                    f"[p1-examples] {arm} 完成：A correct={cond[CONDITION_A]['counts']['correct']} "
                    f"B correct={cond[CONDITION_B]['counts']['correct']}；"
                    f"A 可分类={cond[CONDITION_A]['n_classifiable']} B 可分类={cond[CONDITION_B]['n_classifiable']}",
                    flush=True,
                )

    # ── 报告 ────────────────────────────────────────────────────────────────
    price_table = gen.load_price_table()
    generation_info = generation_summary(generations, price_table)
    inputs = [
        {"path": entry["artifact_label"], "sha256": entry["sha256"], "arms": entry["arms"]} for entry in selection
    ]
    anchor_info = {
        "path": anchor_table["path"],
        "sha256": anchor_table["sha256"],
        "expected_sha256_source": anchor_table["expected_sha256_source"],
        "n_anchors": len(anchors),
    }
    body = build_report(
        inputs=inputs,
        anchor_info=anchor_info,
        arms=arms_out,
        generation=generation_info,
        config=config,
        reuse_info=reuse_info,
    )
    wall_s = round(time.time() - started, 3)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report": body,
        "run_meta": {
            "generated_at": _now_iso(),
            "tool_wall_s": wall_s,
            "body_digest": body_digest(body),
            "argv": list(sys.argv),
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "command": _command_line(),
        },
    }
    from src.utils.atomic_io import atomic_write_json, atomic_write_text

    json_path = out_dir / f"{args.report_name}.json"
    atomic_write_json(str(json_path), payload)
    print(f"[p1-examples] JSON 报告: {json_path}（墙钟 {wall_s}s）", flush=True)
    if not args.skip_markdown:
        readme_path = out_dir / "README.md"
        atomic_write_text(str(readme_path), render_readme(body))
        print(f"[p1-examples] README: {readme_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
