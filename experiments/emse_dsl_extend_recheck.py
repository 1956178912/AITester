#!/usr/bin/env python3
"""emse_dsl_extend_recheck.py — v4 文法扩展前后对账（EMSE 批次六，2026-10-15，零 LLM）。

口径：
- 语料与去重规则与 emse_dsl_diag3 **逐字相同**（同一 iter_planner_entries，
  同一函数名三级解析 / 签名提取 / 通道选择复刻）；
- **旧门精确复刻**（非标记猜测）：临时把 spec_ir_v2 的三个模块级常量换回
  v4 前值再调用同一 clause_reject_reason——
  * _EXPR_TOKEN_RE 去掉冒号（字符门回 v4 前）；
  * _ALLOWED_CALL_NAMES 去掉 sum/set/bool/hasattr；
  * _ALLOWED_ATTRS 去掉 values/keys/items/get/isupper/islower/bit_length；
  （lambda/海象护栏在旧门下不可达——两类子句都含冒号、旧字符门即拒，
  故旧门无需摘护栏；这正是"冒号放行 ⇒ 护栏必须配对"的结构性原因。）
- 新门 = 当前源码（v4 扩展版）；
- 输出：experiments/results/emse_dsl_extend_recheck_20261015/（JSON + README）。

判读纪律（与 10-14 校准批次一致）：
- 子句级对账是**受控估计**（同子句两门对比），不等于端到端任务级增益
  （后者需 LLM 重跑，本批次不做——v4 只改度量/编译门，注入侧经 P0-3
  单一事实源自动跟随同一判定）；
- 语料是"LLM 已形式化的子句"（有 *_expr 产出的计划），非全部规约——
  它回答"编译器对形式化产物的接受率"，不回答"LLM 形式化意愿"。

复现路径（2026-10-19 X 轮补齐，供 fresh clone / 工件包消费）：
- 语料派生于作者机 `~/.cache/aitester/llm` 的 Planner 缓存（不在工件包内）；
  本脚本提供 `--dump-corpus` 把去重后的子句语料（dataset/function_name/kind/
  clause/params）导出为归档 JSON，`--from-corpus` 从该归档**完整重放**
  （重打分不依赖缓存，逐位复现归档报告）——论文"可复算"主张以此闭合；
- 归档语料：`experiments/results/emse_dsl_extend_recheck_20261015/CORPUS_607.json`；
- 默认路径（读缓存）行为不变，输出逐位兼容。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments"))

from emse_dsl_diag3 import (  # noqa: E402
    DEFAULT_CACHE,
    iter_planner_entries,
    load_dataset_index,
    resolve_signature_params,
    tag_dataset,
)

import src.specs.spec_ir_v2 as v2  # noqa: E402
from src.specs.spec_ir import parse_logic_analysis  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# v4 新增项（旧门复刻的摘除集——与 spec_ir_v2 v4 注释逐字对应）
_V4_CALLS = frozenset({"sum", "set", "bool", "hasattr"})
_V4_ATTRS = frozenset({"values", "keys", "items", "get", "isupper", "islower", "bit_length"})
_EXPR_TOKEN_RE_PRE_V4 = re.compile(r"^\s*[A-Za-z_\d\[\]\(\).\-+*/%<>=!&|~^, \"]*$")


def _prior_gate_reason(clause: Any, kind: str, params: list[str] | None) -> str | None:
    """旧门（v4 前）判定：常量摘除后调用同一判定函数（判定逻辑零复刻）。"""
    saved = (v2._EXPR_TOKEN_RE, v2._ALLOWED_CALL_NAMES, v2._ALLOWED_ATTRS)
    try:
        v2._EXPR_TOKEN_RE = _EXPR_TOKEN_RE_PRE_V4
        v2._ALLOWED_CALL_NAMES = saved[1] - _V4_CALLS
        v2._ALLOWED_ATTRS = saved[2] - _V4_ATTRS
        return v2.clause_reject_reason(clause, kind, params)
    finally:
        v2._EXPR_TOKEN_RE, v2._ALLOWED_CALL_NAMES, v2._ALLOWED_ATTRS = saved


def _extract_rows() -> list[dict]:
    """从 Planner 缓存提取去重子句行（dataset/function_name/kind/clause/params）。"""
    index = load_dataset_index()
    plans = list(iter_planner_entries(DEFAULT_CACHE))

    seen: set[tuple[str, str, str, str]] = set()
    rows: list[dict] = []
    for _path, source, plan in plans:
        sig_params, _func_path = resolve_signature_params(source, plan)
        spec = parse_logic_analysis(plan.get("logic_analysis"))
        if spec is None:
            continue
        # 数据集标签与 diag3 同口径（def 行匹配）
        dataset = tag_dataset(source, index) if source else "other"
        pre, post, inv = v2._select_compile_channels(spec)
        for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
            for clause in clauses:
                if not clause.strip():
                    continue
                key = (dataset, str(plan.get("function_name") or ""), kind, clause)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "dataset": dataset,
                        "function_name": str(plan.get("function_name") or ""),
                        "kind": kind,
                        "clause": clause,
                        "params": sig_params,
                    }
                )
    return rows


def _score_rows(rows: list[dict]) -> list[dict]:
    """对语料行逐条打两门判分（params 缺失按历史默认集合处理，与在线口径一致）。"""
    scored: list[dict] = []
    for r in rows:
        params = r.get("params")
        scored.append(
            {
                **r,
                "prior_reason": _prior_gate_reason(r["clause"], r["kind"], params),
                "new_reason": v2.clause_reject_reason(r["clause"], r["kind"], params),
            }
        )
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(description="v4 文法扩展前后对账（零 LLM）")
    parser.add_argument(
        "--dump-corpus", type=Path, default=None, help="从本地 Planner 缓存导出去重子句语料 JSON 后退出（不打分）"
    )
    parser.add_argument(
        "--from-corpus", type=Path, default=None, help="从归档语料 JSON 重放打分（不读缓存；逐位复现归档报告）"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="报告输出目录（默认 experiments/results/emse_dsl_extend_recheck_20261015）",
    )
    args = parser.parse_args()

    if args.dump_corpus is not None:
        rows = _extract_rows()
        atomic_write_json(args.dump_corpus, rows, indent=1, mode=0o644)
        print(f"[recheck] 语料已导出：{args.dump_corpus}（{len(rows)} 去重子句）")
        return 0

    if args.from_corpus is not None:
        corpus = json.loads(args.from_corpus.read_text(encoding="utf-8"))
        if not isinstance(corpus, list):
            print(f"[recheck] 语料文件结构错误（期望 JSON 数组）：{args.from_corpus}", file=sys.stderr)
            return 1
        rows = _score_rows(corpus)
        print(f"[recheck] 从归档语料重放：{args.from_corpus}（{len(rows)} 子句）")
    else:
        rows = _score_rows(_extract_rows())
        print(f"[recheck] 语料与 diag3 同源：{len(rows)} 去重子句")

    def _rate(rows: list[dict], field: str) -> tuple[float, Counter]:
        reasons = Counter(r[field] or "compilable" for r in rows)
        total = len(rows)
        return (round(reasons.get("compilable", 0) / total, 4) if total else 0.0), reasons

    prior_rate, prior_reasons = _rate(rows, "prior_reason")
    new_rate, new_reasons = _rate(rows, "new_reason")

    # 逐子句迁移矩阵
    transitions: Counter[str] = Counter()
    recovered: list[dict] = []
    regressed: list[dict] = []
    for r in rows:
        transitions[f"{r['prior_reason']}→{r['new_reason']}"] += 1
        if r["prior_reason"] is not None and r["new_reason"] is None:
            recovered.append(r)
        if r["prior_reason"] is None and r["new_reason"] is not None:
            regressed.append(r)  # 预期恒空（v4 只放行不收紧既有形态；lambda/海象旧门亦拒）

    datasets = sorted({r["dataset"] for r in rows})
    by_dataset = {}
    for ds in datasets:
        sub = [r for r in rows if r["dataset"] == ds]
        p, _ = _rate(sub, "prior_reason")
        n, _ = _rate(sub, "new_reason")
        by_dataset[ds] = {"n": len(sub), "prior": p, "new": n}

    # 任务级对账（论文引用口径=任务级 spec_compile_rate）：
    # 每任务 rate = 可编译非空子句 / 非空子句（与 compile_readiness 同式），
    # 语料任务=有 *_expr 产出的任务（不含零 expr 任务，故绝对值高于全人口径）。
    task_rows: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        task_rows.setdefault((r["dataset"], r["function_name"]), []).append(r)
    task_deltas: list[float] = []
    for clauses in task_rows.values():
        total = len(clauses)
        p = sum(1 for c in clauses if c["prior_reason"] is None) / total
        n = sum(1 for c in clauses if c["new_reason"] is None) / total
        task_deltas.append(n - p)
    task_level = {
        "tasks": len(task_rows),
        "mean_rate_prior": round(sum(1 for r in rows if r["prior_reason"] is None) / len(rows), 4),
        "mean_task_rate_prior": round(
            sum(sum(1 for c in cl if c["prior_reason"] is None) / len(cl) for cl in task_rows.values())
            / len(task_rows),
            4,
        ),
        "mean_task_rate_new": round(
            sum(sum(1 for c in cl if c["new_reason"] is None) / len(cl) for cl in task_rows.values()) / len(task_rows),
            4,
        ),
        "tasks_improved": sum(1 for d in task_deltas if d > 0),
        "tasks_unchanged": sum(1 for d in task_deltas if d == 0),
        "tasks_regressed": sum(1 for d in task_deltas if d < 0),
    }

    report = {
        "meta": {
            "date": "2026-10-15",
            "batch": "emse-batch6-dsl-extend-recheck",
            "corpus": "identical extraction/dedup as emse_dsl_diag3",
            "gate_prior": "pre-v4 (char class w/o colon, whitelists w/o v4 entries)",
            "gate_new": "v4 (colon + guardrails + whitelist extensions)",
        },
        "overall": {
            "unique_clauses": len(rows),
            "compile_rate_prior": prior_rate,
            "compile_rate_new": new_rate,
            "delta_pp": round((new_rate - prior_rate) * 100, 2),
            "prior_reasons": dict(prior_reasons.most_common()),
            "new_reasons": dict(new_reasons.most_common()),
        },
        "transitions": dict(transitions.most_common()),
        "recovered_count": len(recovered),
        "recovered": [
            {"dataset": r["dataset"], "kind": r["kind"], "clause": r["clause"], "prior_reason": r["prior_reason"]}
            for r in recovered
        ],
        "regressed_count": len(regressed),
        "regressed": [{"clause": r["clause"], "new_reason": r["new_reason"]} for r in regressed],
        "by_dataset": by_dataset,
        "task_level": task_level,
    }

    out_dir = args.out if args.out is not None else REPO_ROOT / "experiments/results/emse_dsl_extend_recheck_20261015"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_dir / "RECHECK_REPORT.json", report, indent=2, mode=0o644)

    print("\n===== v4 前后对账（同语料受控估计） =====")
    print(f"子句级可编译率：{prior_rate} → {new_rate}（Δ={report['overall']['delta_pp']}pp）")
    print(f"旧门拒绝分布：{report['overall']['prior_reasons']}")
    print(f"新门拒绝分布：{report['overall']['new_reasons']}")
    print(f"收复 {len(recovered)} 条 / 回退 {len(regressed)} 条（回退应为 0）")
    print("\n迁移矩阵（prior→new）：")
    for key, count in transitions.most_common():
        print(f"  {key:55s} {count}")
    print("\n分数据集：")
    for ds, sub in by_dataset.items():
        print(f"  {ds:10s} n={sub['n']:5d}  {sub['prior']} → {sub['new']}")
    print("\n任务级（论文引用口径；语料任务=有 *_expr 产出的任务）：")
    print(
        f"  {task_level['tasks']} 任务：mean {task_level['mean_task_rate_prior']} → "
        f"{task_level['mean_task_rate_new']}；改善 {task_level['tasks_improved']} / "
        f"不变 {task_level['tasks_unchanged']} / 回退 {task_level['tasks_regressed']}"
    )
    print(f"\nJSON：{out_dir / 'RECHECK_REPORT.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
