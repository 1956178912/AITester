#!/usr/bin/env python3
"""E7 候选的客观证据预筛（零 LLM）——**只提取事实，不做判定**。

## 定位

E7 人工裁决的瓶颈是"逐条读 patch vs gold 的 diff"（n=72 约 6-12 小时）。本脚本
把其中**机械可算**的部分提前算好，让审阅者把注意力放在真正需要判断的地方：

1. `AST 结构等价`：剥离围栏语言标签、去掉 docstring/注释后，两份代码的 AST
   dump 是否逐节点相同；
2. `差异行数`：unified diff 的增删行数；
3. `差异仅注释/空行`：所有差异行是否都是注释或空行。

## 纪律（必须遵守）

- **不输出判定、不输出建议、不做排序**——避免锚定偏差污染人工裁决。输出顺序与
  `e7_review_worksheet_n72.md` 完全一致，便于交叉核对。
- 预注册的判定口径（equivalent / plausible_overfit / wrong_location / test_only /
  incomplete）**不因本文件改变**；`equivalent` 仍须人工确认语义。
- `AST 结构等价` 是**强证据**（语法层结构相同）但**不是判定**：运行时行为还受
  导入、全局状态、装饰器等影响，须人工确认。
- gold 取值必须走 `repair_sample_selection.gold_reference_code()` 单点解析：
  跨文件任务的 gold 在 `fixed_module_code` 而非 `fixed`，直接读 `fixed` 会得到
  空串并把"取错字段"伪装成"上游素材缺失"（2026-10-19 n41/n72 实测踩过）。

## 用法

    python experiments/e7_evidence_prepass.py \
        --results-dir experiments/results/main_batch \
        --fraction 1.0 --seed 42 \
        --output experiments/results/main_batch/e7_evidence_prepass_n72.md
"""

from __future__ import annotations

import argparse
import ast
import difflib
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.repair_sample_selection import (  # noqa: E402
    _DEFAULT_BATCHES,
    build_sampling_frame,
    gold_reference_code,
    select_stratified_sample,
    stratify,
)
from experiments.statistical_analysis import (  # noqa: E402
    load_experiment_results_with_sources,
)

_FENCE_LANGS = frozenset({"python", "py", "python3"})


def strip_fence_language(code: str) -> str:
    """剥离 LLM 输出伪影：首行若是代码围栏的语言标签则去掉。

    注意 ``python`` 首行本身是**合法表达式**（``Name(id='python')``），不是语法
    错误——若按"解析失败才剥离"的顺序处理，patch 会永远多一个表达式节点，使
    AST 等价判定恒为 False（2026-10-19 实测踩过该坑）。

    只摘掉首行，正文（含尾换行）逐字节原样保留——与"首行非标签则原样返回"
    的分支同形，避免两条路径对同一份正文给出不一致的字面量。
    """
    lines = code.splitlines(keepends=True)
    if lines and lines[0].strip().lower() in _FENCE_LANGS:
        return "".join(lines[1:])
    return code


def _drop_docstrings(tree: ast.AST) -> ast.AST:
    """移除模块/类/函数体的首条字符串常量（docstring）。"""
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return tree


def ast_signature(code: str) -> str | None:
    """归一化 AST 签名（去 docstring、不记录行号）；无法解析时返回 None。"""
    for candidate in (strip_fence_language(code), code):
        try:
            return ast.dump(_drop_docstrings(ast.parse(candidate)), annotate_fields=False)
        except SyntaxError:
            continue
    return None


def diff_facts(patch: str, gold: str) -> tuple[int, bool]:
    """返回 (增删行数, 差异是否仅注释/空行)。"""
    patch_lines = strip_fence_language(patch).splitlines()
    gold_lines = gold.splitlines()
    diff_lines = [
        line
        for line in difflib.unified_diff(patch_lines, gold_lines, lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    trivial = True
    for line in diff_lines:
        text = line[1:].strip()
        if text and not text.startswith("#"):
            trivial = False
            break
    return len(diff_lines), trivial


def collect_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """对单个候选提取三项客观证据。

    素材缺失（patch 或 gold 为空）时 ``n_diff``/``trivial_only`` 为 ``None``：
    此时不存在可比对的两侧，任何整数都会被读成事实（0 = 逐行相同、21 = 有 21
    行差异），故用 None 让"无可比"在类型上可表达，渲染为「—」。
    """
    patch = str(row.get("patch") or "")
    gold = gold_reference_code(row.get("task_metadata"))
    patch_missing, gold_missing = not patch.strip(), not gold.strip()

    if patch_missing or gold_missing:
        # 必须先短路：空串能被 ast.parse 接受（空模块），照常比对会把"素材
        # 缺失"渲染成"有差异"，与本行末列自相矛盾（2026-10-19 实测踩过）。
        return {
            "task_id": row.get("task_id"),
            "ast_state": "素材缺失",
            "ast_equal": False,
            "n_diff": None,
            "trivial_only": None,
            "patch_missing": patch_missing,
            "gold_missing": gold_missing,
        }

    sig_patch, sig_gold = ast_signature(patch), ast_signature(gold)
    if sig_patch is None or sig_gold is None:
        ast_state = "无法解析"
    elif sig_patch == sig_gold:
        ast_state = "**结构等价**"
    else:
        ast_state = "有差异"
    n_diff, trivial = diff_facts(patch, gold)
    return {
        "task_id": row.get("task_id"),
        "ast_state": ast_state,
        "ast_equal": sig_patch is not None and sig_patch == sig_gold,
        "n_diff": n_diff,
        "trivial_only": trivial,
        "patch_missing": patch_missing,
        "gold_missing": gold_missing,
    }


def render(rows: list[dict[str, Any]]) -> str:
    equivalent = sum(1 for r in rows if r["ast_equal"])
    trivial = sum(1 for r in rows if r["trivial_only"])
    lines = [
        "# E7 候选客观证据预筛（零 LLM，**非判定**）",
        "",
        "> **本文件不是判定结果**，只把机械可算的事实提前列好，供人工裁决时对照。",
        "> 预注册的五选一口径不变；`equivalent` 仍须人工确认语义。",
        "> 输出顺序与 `e7_review_worksheet_n72.md` 完全一致，便于交叉核对。",
        "",
        f"- 候选总数：{len(rows)}",
        f"- AST 结构等价（去 docstring/注释后逐节点相同）：**{equivalent}**（{equivalent / max(len(rows), 1):.1%}）",
        f"- 差异仅注释/空行：**{trivial}**（{trivial / max(len(rows), 1):.1%}）",
        "",
        "> gold 取值口径：单文件任务取 `task_metadata.fixed`，跨文件任务"
        "（`is_cross_file=True`）取 `task_metadata.fixed_module_code`——后者的 `fixed`"
        " 字段为空，只读 `fixed` 会把取错字段误报成素材缺失。",
        "",
        "## 如何读这三列",
        "",
        "| 列 | 含义 | 使用建议 |",
        "|---|---|---|",
        "| AST 结构等价 | 两份代码去掉 docstring/注释后，AST 逐节点相同 | 语法层结构相同，**不是**语义判定——仍需确认运行时行为（导入、全局状态、装饰器） |",
        "| 差异行数 | unified diff 的增删行数 | 0 = 逐行相同；越大越需要逐行看 |",
        "| 差异仅注释/空行 | 所有差异是否都是 `#` 注释或空行 | 是 → 语义极可能相同，但仍须人工确认 |",
        "| 素材缺失 | patch / gold 哪一侧为空 | 非「—」→ 该行**无可比对素材**，差异两列同时记「—」，不得读成「有差异」 |",
        "",
        "## 逐条证据",
        "",
        "| # | task_id | AST 结构等价 | 差异行数 | 差异仅注释/空行 | 素材缺失 |",
        "|---|---|---|---|---|---|",
    ]
    for idx, r in enumerate(rows, start=1):
        missing = []
        if r["patch_missing"]:
            missing.append("patch")
        if r["gold_missing"]:
            missing.append("gold")
        n_diff = "—" if r["n_diff"] is None else str(r["n_diff"])
        trivial = "—" if r["trivial_only"] is None else ("是" if r["trivial_only"] else "否")
        lines.append(
            f"| {idx} | {r['task_id']} | {r['ast_state']} | {n_diff} | {trivial} | {'、'.join(missing) or '—'} |"
        )
    lines += [
        "",
        "## 复核完成后",
        "",
        "把每行判定回填 `e7_repair_sample_candidates_n72.md` 的「人工判定」列，按预注册",
        "判定规则更新 `docs/preregistration.md` 执行记录表 E7 行，并追记全局决策日志。",
        "",
        "**若确认的出现 equivalent ≥ 1**：E7 判定规则要求勘误 repair 口径并给出修正后",
        "上界（原「repair=0 为真零」表述不再成立）。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", default="experiments/results/main_batch")
    parser.add_argument("--batches", default=",".join(_DEFAULT_BATCHES), help="批次白名单（与候选清单同参）")
    parser.add_argument("--fraction", type=float, default=1.0, help="抽样比例（须与目标候选清单一致）")
    parser.add_argument("--seed", type=int, default=42, help="抽样种子（须与目标候选清单一致）")
    parser.add_argument("--output", default="-", help="输出路径（默认 - = stdout）")
    args = parser.parse_args(argv)

    batch_files = [b.strip() for b in args.batches.split(",") if b.strip()]
    results, _sources = load_experiment_results_with_sources(
        args.results_dir, batch_files, allow_schema_mixed=False, pool_seeds=True
    )
    frame = build_sampling_frame(results.get("aitester") or [])
    if not frame:
        print("错误：抽样框为空", file=sys.stderr)
        return 1

    selected = select_stratified_sample(stratify(frame), args.fraction, args.seed)
    rows = [collect_evidence(row) for row in selected]
    report = render(rows)

    if args.output == "-":
        sys.stdout.write(report)
    else:
        Path(args.output).write_text(report, encoding="utf-8")
        eq = sum(1 for r in rows if r["ast_equal"])
        print(f"已写入 {args.output}（{len(rows)} 候选；AST 结构等价 {eq} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
