#!/usr/bin/env python
"""T3（2026-10-18）：oracle 示例通道 K=3 多数一致 + canonical input 约束真实采样。

用途
----
对 P-1 的 20 个任务做 **K=3** 次 spec-only 采样（每任务 3 次 LLM 调用、≤3 条/样本、
`temperature=0.0`、`LLM_MAX_OUTPUT_TOKENS=512`、**关闭 LLM 缓存**），按
**≥2/3 多数一致**（归一化 JSON 键）保留示例；canonical input 约束通过
``generate_examples_multisample(..., canonical_inputs=True)`` 的 prompt 变体实现。

失败回退（PREREG 冻结）：某任务 3/3 样本 `status != "ok"` → 用旧 prompt 回退重采样
K=3 一次（`canonical_inputs=False`），审计 `fallback_tasks`；其它情况不回退。

材料/任务解析**复用** `experiments.oracle_examples_replay` 与
`experiments.misguided_metrics` 的 helper（与 P-1 重放生成路径逐字节一致；
链路校准：重建的旧 prompt 与 S-3 工件 sample0 prompt_sha256 20/20 相同）。

预算/墙钟（PREREG 冻结）：成本 ≤$0.05、采样墙钟 ≤15min；超限即中止并如实落盘。

输出（写入 --out）：
- ``K3_STATS.json``：逐任务采样/多数一致/回退/usage/墙钟/幻觉明细 + 汇总；
- ``K3_REUSE_REPORT.json``：多数一致示例的 reuse 报告（供零 LLM 重放）；
- ``PREFLIGHT_PROMPTS.json``：--dry-run 产物（两种 prompt 的逐任务 sha256）。

用法::

    # 预检（零 LLM）：任务解析 + prompt sha 校验（含与 S-3 工件校准）
    .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py --dry-run
    # 真实采样（60 次小调用；cache off）
    AITESTER_LLM_CACHE=0 .venv/bin/python experiments/results/t_round_oracle_k3_20261018/_helpers/run_k3_sampling.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments import misguided_metrics as mm  # noqa: E402
from experiments import oracle_examples_replay as ox  # noqa: E402
from experiments import oracle_quality_replay as oq  # noqa: E402
from experiments import spec_examples_generator as gen  # noqa: E402
from src.specs import extract_signature_params  # noqa: E402

DEFAULT_OUT = _REPO_ROOT / "experiments/results/t_round_oracle_k3_20261018"
S3_STATS = _REPO_ROOT / "experiments/results/s_round_examples_multisample_20261018/MULTISAMPLE_STATS.json"
# P-1 的 2 条 hallucination 期望（PREREG 冻结定义）
HALLUCINATIONS: dict[str, dict[str, Any]] = {
    "quixbugs__is_valid_parenthesization": {"input": ["((("], "expected": True},
    "quixbugs__knapsack": {"input": [5, [[5, 10]]], "expected": 0},
}


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve_tasks(limit: int) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, Any]]:
    """按 P-1 重放同口径解析 20 个缺陷程序任务（锚材料 + 参数名）。"""
    anchor_table = oq.load_anchor_table(ox.DEFAULT_ANCHOR_TABLE)
    anchors = anchor_table["anchors"]
    roots = mm.resolve_quixbugs_roots(None)
    selection = ox._resolve_selection(list(ox.DEFAULT_ARTIFACTS), [])
    task_rows: dict[str, dict[str, Any]] = {}
    inputs: list[dict[str, Any]] = []
    for entry in selection:
        inputs.append({"path": entry["artifact_label"], "sha256": entry["sha256"], "arms": entry["arms"]})
        for arm in entry["arms"]:
            rows = mm.select_rows(entry["data"], arm)
            for row in ox._filter_rows(rows, limit=limit, include_driver=False, task_ids=[]):
                task_rows.setdefault(str(row.get("task_id")), row)
    ordered = sorted(task_rows)
    resolved: dict[str, dict[str, Any]] = {}
    for task_id in ordered:
        item = ox._resolve_buggy_and_anchor(task_rows[task_id], anchors, roots)
        if item is None:
            raise SystemExit(f"任务 {task_id} 材料解析失败（锚/缺陷源缺失）")
        buggy_code, anchor, program = item
        material = dict(anchor.get("logic_analysis") or {})
        if isinstance(anchor.get("human_spec"), str) and anchor.get("human_spec", "").strip():
            material["human_spec"] = anchor["human_spec"]
        function_name = str(anchor.get("function_name") or material.get("function_name") or program)
        resolved[task_id] = {
            "material": material,
            "signature_params": extract_signature_params(buggy_code, function_name),
            "function_name": function_name,
            "program": program,
            "anchor_key_sha256": anchor.get("key_sha256") or "",
        }
    selection_meta = {
        "artifacts": inputs,
        "anchor_table": {
            "path": mm._display_path(ox.DEFAULT_ANCHOR_TABLE),
            "sha256": mm.sha256_file(str(ox.DEFAULT_ANCHOR_TABLE)),
        },
        "n_tasks": len(ordered),
        "task_ids": ordered,
        "args": {"limit": int(limit)},
    }
    return ordered, resolved, selection_meta


def _prompt_audit(ordered: list[str], resolved: dict[str, dict[str, Any]], max_examples: int) -> dict[str, Any]:
    """两变体 prompt 的逐任务 sha256 + 与 S-3 工件校准（零 LLM）。"""
    s3_prompts: dict[str, str] = {}
    if S3_STATS.is_file():
        stats = json.loads(S3_STATS.read_text(encoding="utf-8"))
        for task in stats.get("per_task") or []:
            samples = task.get("samples") or []
            if samples:
                s3_prompts[str(task.get("task_id"))] = str(samples[0].get("prompt_sha256") or "")
    per_task: list[dict[str, Any]] = []
    n_s3_match = 0
    for task_id in ordered:
        item = resolved[task_id]
        base = gen.build_spec_examples_prompt(item["material"], item["signature_params"], max_examples=max_examples)
        canonical = gen.build_spec_examples_prompt(
            item["material"], item["signature_params"], max_examples=max_examples, canonical_inputs=True
        )
        base_sha = gen._sha256_text(base)
        canonical_sha = gen._sha256_text(canonical)
        marker = "\n\n请只输出 JSON"
        expected_canonical = base.replace(marker, f"\n\n{gen.CANONICAL_INPUT_SECTION}{marker}", 1)
        section_ok = (
            canonical == expected_canonical
            and canonical.count(gen.CANONICAL_INPUT_SECTION) == 1
            and gen.CANONICAL_INPUT_SECTION not in base
        )
        s3_sha = s3_prompts.get(task_id)
        match = bool(s3_sha) and base_sha == s3_sha
        n_s3_match += int(match)
        per_task.append(
            {
                "task_id": task_id,
                "prompt_sha256_default": base_sha,
                "prompt_sha256_canonical": canonical_sha,
                "canonical_section_appended": section_ok,
                "s3_sample0_prompt_sha256": s3_sha,
                "matches_s3_default_prompt": match,
            }
        )
    return {
        "k": 3,
        "max_examples": int(max_examples),
        "canonical_section_sha256": gen._sha256_text(gen.CANONICAL_INPUT_SECTION),
        "n_tasks": len(ordered),
        "n_default_prompt_matches_s3": n_s3_match,
        "all_default_prompts_match_s3": n_s3_match == len(ordered),
        "per_task": per_task,
    }


def _usage_add(total: dict[str, int], part: dict[str, Any]) -> None:
    for key in total:
        total[key] += int((part or {}).get(key, 0) or 0)


def _sample_brief(record: dict[str, Any]) -> dict[str, Any]:
    """采样记录精简审计（保留 samples 逐样本示例，供工件复核）。"""
    return {
        "task_id": record.get("task_id"),
        "k": record.get("k"),
        "status": record.get("status"),
        "examples": record.get("examples") or [],
        "samples": record.get("samples") or [],
        "audit": record.get("audit") or {},
        "usage_totals": record.get("usage_totals") or {},
        "wall_s": record.get("wall_s"),
        "model": record.get("model"),
    }


def _hallucination_presence(
    task_id: str, record: dict[str, Any], final_examples: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if task_id not in HALLUCINATIONS:
        return None
    target = HALLUCINATIONS[task_id]
    key = gen.normalize_example_key(target)
    samples = record.get("samples") or []
    presence = [key in {gen.normalize_example_key(ex) for ex in (sample.get("examples") or [])} for sample in samples]
    final_keys = {gen.normalize_example_key(ex) for ex in final_examples}
    return {
        "p1_hallucination_example": target,
        "normalized_key": key,
        "present_in_samples": presence,
        "n_samples_present": sum(1 for flag in presence if flag),
        "in_final_examples": key in final_keys,
        "in_final_intersection": key in final_keys,
    }


def _build_reuse_report(per_task: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    """K=3 多数一致最终示例 → replay --reuse-examples 报告（结构同 S-3）。"""
    tasks: list[dict[str, Any]] = []
    for task in per_task:
        final = task.get("final") or {}
        examples = final.get("examples") or []
        tasks.append(
            {
                "task_id": task.get("task_id"),
                "examples_generation": {
                    "status": "ok" if examples else "empty",
                    "reason": None,
                    "examples": examples,
                    "prompt_sha256": task.get("final_prompt_sha256"),
                },
                "examples_self_validation": None,
            }
        )
    report = {"arms": [{"arm": "plain_llm_df_spec", "tasks": tasks}]}
    payload = {
        "schema_version": "oracle_examples_metric/1",
        "report": report,
        "run_meta": {
            "generated_at": _now_iso(),
            "source": "T3 K=3 majority(>=2/3)+canonical sampling: K3_STATS.json",
            "body_digest": mm.body_digest(report),
        },
    }
    from src.utils.atomic_io import atomic_write_json

    atomic_write_json(str(out_dir / "K3_REUSE_REPORT.json"), payload)
    return payload


def _build_stats(
    *,
    ordered: list[str],
    selection_meta: dict[str, Any],
    prompt_audit: dict[str, Any],
    per_task: list[dict[str, Any]],
    generator_meta: dict[str, Any],
    fallback_tasks: list[dict[str, Any]],
    started_at: str,
    wall_s: float,
    aborted: str | None,
    budget_usd: float,
    wall_limit_s: float,
) -> dict[str, Any]:
    n_tasks = len(per_task)
    final_examples = [len(task.get("final", {}).get("examples") or []) for task in per_task]
    union_total = sum(int(task["final"].get("audit", {}).get("n_examples_union") or 0) for task in per_task)
    inter_total = sum(int(task["final"].get("audit", {}).get("n_examples_intersection") or 0) for task in per_task)
    dropped_total = sum(int(task["final"].get("audit", {}).get("n_dropped_non_intersection") or 0) for task in per_task)
    statuses = [task["canonical"].get("status") for task in per_task]
    hallucination = {
        task["task_id"]: task["hallucination"] for task in per_task if task.get("hallucination") is not None
    }
    return {
        "purpose": "T3 K=3 多数一致（≥2/3）+ canonical input 约束：20 任务真实 spec-only 采样统计",
        "prereg": "PREREG.md（跑前冻结；sha256 见 PREFLIGHT.json.prereg_sha256）",
        "generator": generator_meta,
        "selection": selection_meta,
        "prompt_audit": prompt_audit,
        "fallback": {
            "rule": "3/3 样本 status != ok → 旧 prompt 回退重采样 K=3 一次（PREREG 冻结）",
            "n_tasks": len(fallback_tasks),
            "tasks": fallback_tasks,
        },
        "audit_totals": {
            "n_tasks": n_tasks,
            "n_tasks_with_final_examples": sum(1 for n in final_examples if n > 0),
            "n_examples_final_total": sum(final_examples),
            "n_examples_union_total": union_total,
            "n_examples_intersection_total": inter_total,
            "n_dropped_non_intersection_total": dropped_total,
            "canonical_status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
            "per_task_sample_counts": {
                task["task_id"]: (task["canonical"].get("audit") or {}).get("per_sample_counts") for task in per_task
            },
            "per_task_intersection_counts": {
                task["task_id"]: len(task["final"].get("examples") or []) for task in per_task
            },
            "fallback_task_ids": [task["task_id"] for task in fallback_tasks],
        },
        "hallucination_tasks": hallucination,
        "per_task": per_task,
        "aborted": aborted is not None,
        "abort_reason": aborted,
        "budget_usd_limit": float(budget_usd),
        "wall_limit_s": float(wall_limit_s),
        "run_meta": {
            "started_at": started_at,
            "finished_at": _now_iso(),
            "wall_s": round(wall_s, 3),
            "argv": list(sys.argv),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T3 K=3 多数一致 + canonical input 约束采样")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--dry-run", action="store_true", help="只解析任务/构造 prompt（零 LLM），写 PREFLIGHT_PROMPTS.json"
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--majority", type=int, default=2)
    parser.add_argument("--max-examples", type=int, default=3)
    parser.add_argument("--namespace", default="t_round_k3_20261018")
    parser.add_argument("--max-output-tokens", type=int, default=gen.DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--budget-usd", type=float, default=0.05)
    parser.add_argument("--wall-limit-s", type=float, default=900.0)
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ordered, resolved, selection_meta = _resolve_tasks(int(args.limit))
    prompt_audit = _prompt_audit(ordered, resolved, int(args.max_examples))
    if not prompt_audit["all_default_prompts_match_s3"]:
        print(
            f"[k3-sample] 警告：默认 prompt 与 S-3 工件仅 {prompt_audit['n_default_prompt_matches_s3']}/{len(ordered)} 匹配",
            file=sys.stderr,
        )
    if args.dry_run:
        from src.utils.atomic_io import atomic_write_json

        atomic_write_json(str(out_dir / "PREFLIGHT_PROMPTS.json"), prompt_audit)
        print(
            f"[k3-sample] dry-run 完成：{len(ordered)} 任务；默认 prompt 与 S-3 匹配 "
            f"{prompt_audit['n_default_prompt_matches_s3']}/{len(ordered)}；canonical 段 sha256="
            f"{prompt_audit['canonical_section_sha256'][:16]}… → {out_dir / 'PREFLIGHT_PROMPTS.json'}",
            flush=True,
        )
        return 0

    # ── 真实采样（60 次小调用；cache off；PREREG 预算/墙钟中止条件）────────
    os.environ["AITESTER_LLM_CACHE"] = "0"
    os.environ.setdefault("LLM_MAX_OUTPUT_TOKENS", str(int(args.max_output_tokens)))
    price_table = gen.load_price_table()
    started_wall = time.time()
    started_at = _now_iso()
    per_task: list[dict[str, Any]] = []
    fallback_tasks: list[dict[str, Any]] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0, "cache_hits": 0}
    aborted: str | None = None
    model = "unknown"
    for index, task_id in enumerate(ordered):
        item = resolved[task_id]
        canonical = gen.generate_examples_multisample(
            item["material"],
            signature_params=item["signature_params"],
            task_id=task_id,
            k=int(args.k),
            majority=int(args.majority),
            max_examples=int(args.max_examples),
            cache_namespace=args.namespace,
            canonical_inputs=True,
        )
        model = str(canonical.get("model") or model)
        _usage_add(usage_total, canonical.get("usage_totals") or {})
        final = canonical
        final_source = "canonical"
        fallback_info: dict[str, Any] | None = None
        if gen.should_fallback_canonical(canonical):
            fallback = gen.generate_examples_multisample(
                item["material"],
                signature_params=item["signature_params"],
                task_id=task_id,
                k=int(args.k),
                majority=int(args.majority),
                max_examples=int(args.max_examples),
                cache_namespace=args.namespace,
                canonical_inputs=False,
            )
            _usage_add(usage_total, fallback.get("usage_totals") or {})
            fallback_info = {
                "task_id": task_id,
                "reason": "all_canonical_samples_not_ok",
                "canonical_statuses": list((canonical.get("audit") or {}).get("sample_statuses") or []),
                "canonical_reasons": list((canonical.get("audit") or {}).get("sample_reasons") or []),
                "fallback_status": fallback.get("status"),
                "fallback_statuses": list((fallback.get("audit") or {}).get("sample_statuses") or []),
                "fallback_examples": len(fallback.get("examples") or []),
            }
            fallback_tasks.append(fallback_info)
            final = fallback
            final_source = "fallback"
        final_examples = list(final.get("examples") or [])
        final_samples = final.get("samples") or []
        final_prompt_sha = next(
            (sample.get("prompt_sha256") for sample in final_samples if sample.get("status") == "ok"),
            (final_samples[0].get("prompt_sha256") if final_samples else None),
        )
        per_task.append(
            {
                "task_id": task_id,
                "program": item["program"],
                "function_name": item["function_name"],
                "signature_params": item["signature_params"],
                "canonical": _sample_brief(canonical),
                "fallback": fallback_info,
                "final_source": final_source,
                "final": _sample_brief(final),
                "final_prompt_sha256": final_prompt_sha,
                "hallucination": _hallucination_presence(task_id, final, final_examples),
            }
        )
        cost_now = gen.estimate_cost_usd(model, usage_total, price_table)
        print(
            f"[k3-sample] {index + 1}/{len(ordered)} {task_id}: canonical={canonical.get('status')} "
            f"n={len(canonical.get('examples') or [])} final={final_source} n_final={len(final_examples)} "
            f"calls={usage_total['llm_calls']} cost≈{cost_now}",
            flush=True,
        )
        # 中止条件（PREREG 冻结）：预算超限 / 墙钟超限
        if cost_now is not None and cost_now > float(args.budget_usd):
            aborted = f"budget_exceeded:{cost_now}>{args.budget_usd}"
            break
        if time.time() - started_wall > float(args.wall_limit_s):
            aborted = f"wall_limit_exceeded:{round(time.time() - started_wall, 1)}s>{args.wall_limit_s}s"
            break
    wall_s = time.time() - started_wall
    cost = gen.estimate_cost_usd(model, usage_total, price_table)
    generator_meta = {
        "function": "experiments.spec_examples_generator.generate_examples_multisample",
        "k": int(args.k),
        "majority": int(args.majority),
        "threshold_rule": "示例出现于 ≥majority 个采样（K=3 → ≥2/3 多数一致）",
        "max_examples": int(args.max_examples),
        "canonical_inputs": True,
        "canonical_section_sha256": gen._sha256_text(gen.CANONICAL_INPUT_SECTION),
        "model": model,
        "llm_cache": os.environ.get("AITESTER_LLM_CACHE"),
        "cache_namespace": args.namespace,
        "temperature": 0.0,
        "max_output_tokens": os.environ.get("LLM_MAX_OUTPUT_TOKENS"),
        "key_normalization": gen.EXAMPLE_KEY_NORMALIZATION,
        "llm_calls": usage_total["llm_calls"],
        "input_tokens": usage_total["input_tokens"],
        "output_tokens": usage_total["output_tokens"],
        "total_tokens": usage_total["total_tokens"],
        "cache_hits": usage_total["cache_hits"],
        "cost_estimated_usd": cost,
        "price_table": "experiments/price_table.json",
        "wall_s": round(wall_s, 3),
    }
    stats = _build_stats(
        ordered=ordered,
        selection_meta=selection_meta,
        prompt_audit=prompt_audit,
        per_task=per_task,
        generator_meta=generator_meta,
        fallback_tasks=fallback_tasks,
        started_at=started_at,
        wall_s=wall_s,
        aborted=aborted,
        budget_usd=float(args.budget_usd),
        wall_limit_s=float(args.wall_limit_s),
    )
    from src.utils.atomic_io import atomic_write_json

    stats_path = out_dir / "K3_STATS.json"
    atomic_write_json(str(stats_path), stats)
    reuse = _build_reuse_report(per_task, out_dir)
    print(
        f"[k3-sample] 完成：tasks={len(per_task)}/{len(ordered)} calls={usage_total['llm_calls']} "
        f"tokens in/out={usage_total['input_tokens']}/{usage_total['output_tokens']} "
        f"cost≈${cost} wall={wall_s:.1f}s fallback={len(fallback_tasks)} aborted={aborted}",
        flush=True,
    )
    print(f"[k3-sample] stats: {stats_path}", flush=True)
    print(
        f"[k3-sample] reuse: {out_dir / 'K3_REUSE_REPORT.json'}（body_digest={reuse['run_meta']['body_digest'][:16]}…）",
        flush=True,
    )
    if aborted:
        print(f"[k3-sample] 中止：{aborted}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
