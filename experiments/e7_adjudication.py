#!/usr/bin/env python3
"""E7（AA 轮 2026-10-19）：人工裁决执行面——录入模板、量表校验、Cohen's κ 合并（零 LLM）。

协议 `docs/HUMAN_ADJUDICATION_PROTOCOL.md` 把"该怎么做"写全了，但执行面缺一件
可机器校验的工件：§4 要两份独立副本、§5 要"合并前不对表"、§6 把主统计量与
bootstrap 口径钉死、§7 步骤 3-4 实际落在**勾选式 Markdown**上。勾选栏的问题不是
难用，而是**静默失效**：漏勾一行、把 `plausible_overfit` 打成 `plausible`、
临时新增第六类、两份副本的候选顺序弄反——每一种都不报错，却直接进入 κ 的分母与
混淆矩阵。本模块把裁决面换成 CSV（一行一候选、判定值限定量表），只做三件事：
模板生成、填后校验、合并算 κ。

**本模块不产生任何裁决结果**：它读裁决人填的空表；判定属人（协议 §3）。
在 E7 真正执行并登记前，对外口径仍是"E7 未执行、无 Kappa 工件"。

用法::

    # 1) 由工作表生成两份独立录入表（裁决人各持一份，互不可见）
    python experiments/e7_adjudication.py template \
        --worksheet experiments/results/main_batch/e7_review_worksheet.md --rater A \
        --output experiments/results/main_batch/e7_entry_A.csv
    # 2) 填完各自固化校验（缺行/越界/重复一律报错，不静默补默认）
    python experiments/e7_adjudication.py validate --sheet <filled.csv>
    # 3) 第三方合并：首轮 κ + bootstrap CI + 5×5 矩阵 + 分歧行清单
    python experiments/e7_adjudication.py merge --sheet-a A.csv --sheet-b B.csv \
        --output-dir experiments/results/e7_adjudication_<date>
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 预注册 E7 五选一量表（协议 §3 逐字口径，顺序即混淆矩阵行列序）。
RUBRIC: tuple[str, ...] = ("equivalent", "plausible_overfit", "wrong_location", "test_only", "incomplete")
# 协议 §4 第 5 条："不可判"行不进 κ 分母，但必须登记为材料缺口。
UNJUDGEABLE = "unjudgeable"
UNJUDGEABLE_ZH = "不可判"
VALID_LABELS: tuple[str, ...] = (*RUBRIC, UNJUDGEABLE, UNJUDGEABLE_ZH)

# 与 `experiments/statistical_analysis.py` 同口径（协议 §6 要求）；等值关系由
# tests/test_e7_adjudication.py 钉成回归锁，从而无需为两个常量把 numpy/scipy
# 拉进本模块的导入链。
BOOTSTRAP_N_RESAMPLES = 10000
BOOTSTRAP_SEED = 42

SHEET_COLUMNS: tuple[str, ...] = (
    "candidate_no",
    "task_id",
    "stratum",
    "judgment",
    "reason",
    "finished_at_utc",
    "rater",
)

_CANDIDATE_HEADING = re.compile(r"^## 候选\s+(\d+)：(\S+)\s*$")
_STRATUM_LINE = re.compile(r"^- 分层（evidence）：\s*([^｜\s]+)")
# Landis & Koch (1977) 通用约定（协议 §6 明示为外部约定，非本项目数据结论）。
_KAPPA_BANDS: tuple[tuple[float, str], ...] = (
    (0.0, "Poor"),
    (0.20, "Slight"),
    (0.40, "Fair"),
    (0.60, "Moderate"),
    (0.80, "Substantial"),
)


def parse_worksheet(text: str) -> list[dict[str, Any]]:
    """从复核工作表提取候选行元数据（只读；绝不回写工作表本体——协议 §4 第 2 条）。

    Returns:
        ``[{"candidate_no": int, "task_id": str, "stratum": str}, ...]``，按候选号
        升序。候选号重复属工件异常，直接抛错而不是静默去重。
    """
    found: dict[int, dict[str, Any]] = {}
    pending: int | None = None
    for line in text.splitlines():
        m = _CANDIDATE_HEADING.match(line)
        if m is not None:
            no = int(m.group(1))
            if no in found:
                raise ValueError(f"工作表候选号重复：{no}")
            found[no] = {"candidate_no": no, "task_id": m.group(2), "stratum": ""}
            pending = no
            continue
        if pending is not None:
            s = _STRATUM_LINE.match(line)
            if s is not None:
                found[pending]["stratum"] = s.group(1)
                pending = None
    if not found:
        raise ValueError("工作表未解析到任何候选节（应形如 `## 候选 1：<task_id>`）")
    return [found[no] for no in sorted(found)]


def render_entry_sheet(candidates: list[dict[str, Any]], rater: str) -> str:
    """生成空白录入表（CSV）：judgment/reason 留空由裁决人填写，余为备料元数据。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(SHEET_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for cand in candidates:
        writer.writerow(
            {
                "candidate_no": cand["candidate_no"],
                "task_id": cand["task_id"],
                "stratum": cand["stratum"],
                "judgment": "",
                "reason": "",
                "finished_at_utc": "",
                "rater": rater,
            }
        )
    return buf.getvalue()


def load_entry_sheet(path: str | Path) -> list[dict[str, str]]:
    """读取录入表（结构校验：表头必须恰为 SHEET_COLUMNS；BOM 容忍，Excel 常加）。"""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"录入表为空：{path}")
        if tuple(reader.fieldnames) != SHEET_COLUMNS:
            raise ValueError(f"录入表表头不符（应为 {','.join(SHEET_COLUMNS)}）：{reader.fieldnames}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError(f"录入表无候选行：{path}")
    return rows


def validate_entry_rows(
    rows: list[dict[str, str]],
    candidates: list[dict[str, Any]] | None = None,
    *,
    require_complete: bool = True,
) -> list[str]:
    """返回错误清单（空即通过）。刻意不"顺手修好"任何行——问题必须回到裁决人。"""
    errors: list[str] = []
    seen: dict[str, int] = {}
    present: set[int] = set()
    for idx, row in enumerate(rows, start=2):  # 第 1 行为表头
        raw_no = (row.get("candidate_no") or "").strip()
        if raw_no in seen:
            errors.append(f"第 {idx} 行 candidate_no 重复（首见第 {seen[raw_no]} 行）")
            continue
        seen[raw_no] = idx
        try:
            no = int(raw_no)
        except ValueError:
            errors.append(f"第 {idx} 行 candidate_no 非整数：{raw_no!r}")
            continue
        if no < 1:
            errors.append(f"第 {idx} 行 candidate_no 应为正整数：{no}")
            continue
        present.add(no)
        judgment = (row.get("judgment") or "").strip()
        if not judgment:
            if require_complete:
                errors.append(f"第 {idx} 行（候选 {no}）judgment 未填")
        elif judgment not in VALID_LABELS:
            errors.append(f"第 {idx} 行（候选 {no}）judgment 越界量表：{judgment!r}（允许 {','.join(VALID_LABELS)}）")
        if candidates is not None:
            expected = {int(c["candidate_no"]): c for c in candidates}
            if no not in expected:
                errors.append(f"第 {idx} 行候选 {no} 不在抽样清单中")
            elif (row.get("task_id") or "").strip() != str(expected[no]["task_id"]):
                errors.append(f"第 {idx} 行候选 {no} 的 task_id 被改写（应为 {expected[no]['task_id']}）")
    if candidates is not None:
        missing = sorted({int(c["candidate_no"]) for c in candidates} - present)
        if missing:
            errors.append(f"缺候选行：{missing}（不得删行；缺材料请填 {UNJUDGEABLE}）")
    return errors


def _label_of(row: dict[str, str]) -> str:
    return (row.get("judgment") or "").strip()


def is_unjudgeable(label: str) -> bool:
    return label in (UNJUDGEABLE, UNJUDGEABLE_ZH)


def _sorted_by_no(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: int((r.get("candidate_no") or "0").strip()))


def align_pairs(
    rows_a: list[dict[str, str]], rows_b: list[dict[str, str]]
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """按 candidate_no 对齐两表 → (进入 κ 的标签对, 被排除行清单)。

    排除口径（协议 §4 第 5 条 / §6）：任一侧为"不可判"或未填 → 该行不进分母，
    但逐行登记进 excluded（材料缺口清单）。两表候选集不一致属**结构性错误**，
    直接抛错而非静默取交集——取交集会把"某一侧漏做 3 行"洗成一次合法的 N 缩小。
    """
    ids_a = [str(r.get("candidate_no") or "").strip() for r in rows_a]
    ids_b = [str(r.get("candidate_no") or "").strip() for r in rows_b]
    if sorted(ids_a) != sorted(ids_b):
        only_a = sorted(set(ids_a) - set(ids_b))
        only_b = sorted(set(ids_b) - set(ids_a))
        raise ValueError(f"两表候选集不一致：仅 A 有 {only_a}，仅 B 有 {only_b}")
    by_no_b = {str(r.get("candidate_no") or "").strip(): r for r in rows_b}
    pairs: list[tuple[str, str]] = []
    excluded: list[dict[str, Any]] = []
    for row_a in _sorted_by_no(rows_a):
        row_b = by_no_b[str(row_a["candidate_no"]).strip()]
        label_a, label_b = _label_of(row_a), _label_of(row_b)
        if not label_a or not label_b or is_unjudgeable(label_a) or is_unjudgeable(label_b):
            excluded.append(
                {
                    "candidate_no": int(str(row_a["candidate_no"]).strip()),
                    "task_id": row_a.get("task_id", ""),
                    "label_a": label_a,
                    "label_b": label_b,
                    "reason": "unjudgeable" if (is_unjudgeable(label_a) or is_unjudgeable(label_b)) else "blank",
                }
            )
            continue
        pairs.append((label_a, label_b))
    return pairs, excluded


def cohen_kappa(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """未加权 Cohen's κ（协议 §6 主口径）。N=0 或 p_e=1 时 κ=None（不编造数字）。"""
    n = len(pairs)
    categories = list(RUBRIC) + sorted({lab for pair in pairs for lab in pair} - set(RUBRIC))
    if n == 0:
        return {"n": 0, "p_o": None, "p_e": None, "kappa": None, "categories": categories}
    joint: Counter[tuple[str, str]] = Counter(pairs)
    p_o = sum(joint[(c, c)] for c in categories) / n
    marginal_a: Counter[str] = Counter(a for a, _ in pairs)
    marginal_b: Counter[str] = Counter(b for _, b in pairs)
    p_e = sum(marginal_a[c] * marginal_b[c] for c in categories) / (n * n)
    return {
        "n": n,
        "p_o": p_o,
        "p_e": p_e,
        "kappa": None if p_e >= 1.0 else (p_o - p_e) / (1.0 - p_e),
        "categories": categories,
        "confusion_matrix": {a: {b: joint.get((a, b), 0) for b in categories} for a in categories},
        "marginal_a": {c: marginal_a.get(c, 0) for c in categories},
        "marginal_b": {c: marginal_b.get(c, 0) for c in categories},
    }


def bootstrap_kappa_ci(
    pairs: list[tuple[str, str]],
    n_resamples: int = BOOTSTRAP_N_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """κ 的 95% bootstrap 百分位 CI（重采样行数 = N；口径同 statistical_analysis）。

    退化重采样（p_e=1 → κ 无定义）不计入分布，但如实登记 `degenerate_replicates`。
    """
    n = len(pairs)
    base = {"n_resamples": n_resamples, "seed": seed}
    if n == 0:
        return {**base, "ci95": None, "valid_replicates": 0, "degenerate_replicates": 0}
    rng = random.Random(seed)
    values: list[float] = []
    degenerate = 0
    for _ in range(n_resamples):
        sample = [pairs[i] for i in rng.choices(range(n), k=n)]
        kappa = cohen_kappa(sample)["kappa"]
        if kappa is None:
            degenerate += 1
        else:
            values.append(float(kappa))
    if not values:
        return {**base, "ci95": None, "valid_replicates": 0, "degenerate_replicates": degenerate}
    values.sort()
    lo = values[min(int(0.025 * len(values)), len(values) - 1)]
    hi = values[min(int(0.975 * len(values)), len(values) - 1)]
    return {**base, "ci95": [lo, hi], "valid_replicates": len(values), "degenerate_replicates": degenerate}


def interpret_kappa(kappa: float | None) -> str:
    """Landis & Koch (1977) 通用约定（外部约定，非本项目结论；协议 §6 解释带表）。"""
    if kappa is None:
        return "undefined（p_e=1，κ 无定义——须显式披露而非报 1.0）"
    for upper, label in _KAPPA_BANDS:
        if kappa <= upper:
            return label
    return "Almost perfect"


def _disagreement_rows(rows_a: list[dict[str, str]], rows_b: list[dict[str, str]]) -> list[dict[str, Any]]:
    """双方都有效判定且取值不同的行（协议 §5：只有这些行进入对表讨论）。"""
    by_no_b = {str(r["candidate_no"]).strip(): r for r in rows_b}
    out: list[dict[str, Any]] = []
    for row_a in _sorted_by_no(rows_a):
        row_b = by_no_b[str(row_a["candidate_no"]).strip()]
        label_a, label_b = _label_of(row_a), _label_of(row_b)
        if not label_a or not label_b or label_a == label_b:
            continue
        if is_unjudgeable(label_a) or is_unjudgeable(label_b):
            continue
        out.append(
            {
                "candidate_no": int(str(row_a["candidate_no"]).strip()),
                "task_id": row_a.get("task_id", ""),
                "label_a": label_a,
                "label_b": label_b,
            }
        )
    return out


def merge_sheets(
    path_a: str | Path,
    path_b: str | Path,
    path_c: str | Path | None = None,
    *,
    n_resamples: int = BOOTSTRAP_N_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """首轮（未讨论）合并：主口径 = A vs B；C 在场时仅作附加两两 κ（次要分析）。"""
    rows_a, rows_b = load_entry_sheet(path_a), load_entry_sheet(path_b)
    for tag, rows in (("A", rows_a), ("B", rows_b)):
        errors = validate_entry_rows(rows)
        if errors:
            raise ValueError(f"表 {tag} 未通过校验（先 validate 再 merge）：{errors[:5]}")
    pairs, excluded = align_pairs(rows_a, rows_b)
    primary = cohen_kappa(pairs)
    report: dict[str, Any] = {
        "protocol": "docs/HUMAN_ADJUDICATION_PROTOCOL.md §6",
        "scale": list(RUBRIC),
        "unjudgeable_label": UNJUDGEABLE,
        "primary_pair": ["A", "B"],
        "kappa": primary["kappa"],
        "p_o": primary["p_o"],
        "p_e": primary["p_e"],
        "n_scored": primary["n"],
        "n_rows": len(pairs) + len(excluded),
        "excluded_rows": excluded,
        "confusion_matrix": primary.get("confusion_matrix", {}),
        "marginal_a": primary.get("marginal_a", {}),
        "marginal_b": primary.get("marginal_b", {}),
        "bootstrap": bootstrap_kappa_ci(pairs, n_resamples=n_resamples, seed=seed),
        "interpretation_band_external": interpret_kappa(primary["kappa"]),
        "disagreement_rows": _disagreement_rows(rows_a, rows_b),
    }
    if path_c is not None:
        rows_c = load_entry_sheet(path_c)
        pairs_ac, excluded_ac = align_pairs(rows_a, rows_c)
        pairs_bc, excluded_bc = align_pairs(rows_b, rows_c)
        report["secondary_pairwise"] = {
            "A_C": cohen_kappa(pairs_ac)["kappa"],
            "B_C": cohen_kappa(pairs_bc)["kappa"],
            "c_validation_errors": validate_entry_rows(rows_c),
            "c_excluded_rows": {"A_C": excluded_ac, "B_C": excluded_bc},
            "note": "协议 §6 第 5 条：主口径仍是 A vs B；C 仅附加，不得替换主统计量",
        }
    return report


def render_report_md(report: dict[str, Any]) -> str:
    """人类可读报告：数字全部取自 report，本函数零再计算。"""
    ci = report["bootstrap"].get("ci95")
    ci_text = f"[{ci[0]:.6f}, {ci[1]:.6f}]" if ci else "不可用（无有效重采样）"
    boot = report["bootstrap"]
    lines = [
        "# E7 人工裁决首轮信度报告（合并自两份独立录入表）",
        "",
        f"- 主口径：未加权 Cohen's κ（{report['protocol']}）= **{report['kappa']}**",
        f"- p_o = {report['p_o']}，p_e = {report['p_e']}，进入分母 N = {report['n_scored']}（表行 {report['n_rows']}）",
        f"- bootstrap 95% CI：{ci_text}（{boot['n_resamples']} 次，seed={boot['seed']}；"
        f"有效重采样 {boot['valid_replicates']}，退化 {boot['degenerate_replicates']}）",
        f"- 解释带（外部约定 Landis & Koch 1977，非本项目结论）：{report['interpretation_band_external']}",
        f"- 分歧行：{len(report['disagreement_rows'])}（协议 §5：仅这些行进入对表讨论）",
        f"- 不进分母的行：{len(report['excluded_rows'])}（不可判 / 未填；属材料缺口，须登记）",
        "",
        "> κ 只回答「该量表在两人间是否可复现」，**不**回答 equivalent 占比是否为 0；",
        "> 后者须按终判标签分布单独报告（协议 §6 第 3 条）。",
        "",
        "## 混淆矩阵（行 = A，列 = B）",
        "",
    ]
    matrix: dict[str, dict[str, int]] = report["confusion_matrix"]
    if matrix:
        cats = list(matrix)
        lines += ["| A\\B | " + " | ".join(cats) + " |", "| --- |" + " --- |" * len(cats)]
        lines += ["| " + a + " | " + " | ".join(str(matrix[a][b]) for b in cats) + " |" for a in cats]
    else:
        lines.append("（两侧无一有效判定 → 混淆矩阵为空、κ 无定义；全部行按材料缺口登记）")
    lines += ["", "## 分歧行", "", "| candidate_no | task_id | A | B |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {d['candidate_no']} | {d['task_id']} | {d['label_a']} | {d['label_b']} |"
        for d in report["disagreement_rows"]
    ]
    lines += [
        "",
        "## 不进分母的行",
        "",
        "| candidate_no | task_id | A | B | 排除原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {e['candidate_no']} | {e['task_id']} | {e['label_a'] or '—'} | {e['label_b'] or '—'} | {e['reason']} |"
        for e in report["excluded_rows"]
    ]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tpl = sub.add_parser("template", help="由工作表生成空白录入表（只读工作表）")
    p_tpl.add_argument("--worksheet", required=True)
    p_tpl.add_argument("--rater", required=True, help="裁决人标识（A/B/…）")
    p_tpl.add_argument("--output", default="-")

    p_val = sub.add_parser("validate", help="校验已填录入表")
    p_val.add_argument("--sheet", required=True)
    p_val.add_argument("--worksheet", default=None, help="给定则同时核对候选集与元数据未被改写")
    p_val.add_argument("--allow-incomplete", action="store_true", help="允许未填行（进度检查用）")

    p_mrg = sub.add_parser("merge", help="合并两份（可选第三份）录入表并计算 κ")
    p_mrg.add_argument("--sheet-a", required=True)
    p_mrg.add_argument("--sheet-b", required=True)
    p_mrg.add_argument("--sheet-c", default=None)
    p_mrg.add_argument("--output-dir", default="-", help="写 E7_KAPPA.{json,md}；- 表示仅 stdout")
    p_mrg.add_argument("--n-resamples", type=int, default=BOOTSTRAP_N_RESAMPLES)
    p_mrg.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)

    args = parser.parse_args()

    if args.cmd == "template":
        candidates = parse_worksheet(Path(args.worksheet).read_text(encoding="utf-8"))
        text = render_entry_sheet(candidates, args.rater)
        if args.output == "-":
            sys.stdout.write(text)
        else:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"已写入 {args.output}（{len(candidates)} 候选行）")
        return 0

    if args.cmd == "validate":
        rows = load_entry_sheet(args.sheet)
        sheet_candidates = parse_worksheet(Path(args.worksheet).read_text(encoding="utf-8")) if args.worksheet else None
        errors = validate_entry_rows(rows, sheet_candidates, require_complete=not args.allow_incomplete)
        filled = sum(1 for r in rows if (r.get("judgment") or "").strip())
        print(f"共 {len(rows)} 行，已填 {filled} 行")
        for err in errors:
            print(f"[ERR] {err}", file=sys.stderr)
        return 1 if errors else 0

    report = merge_sheets(args.sheet_a, args.sheet_b, args.sheet_c, n_resamples=args.n_resamples, seed=args.seed)
    md = render_report_md(report)
    if args.output_dir == "-":
        sys.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        sys.stdout.write(md)
    else:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "E7_KAPPA.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
        (out_dir / "E7_KAPPA.md").write_text(md, encoding="utf-8")
        print(f"已写入 {out_dir}/E7_KAPPA.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
