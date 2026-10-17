"""P1 docstring 独立锚三臂实验分析（预注册件，2026-10-17）。

零 LLM：读 3 臂批次 JSON（``plain_llm_df`` 对照 / ``plain_llm_df_doc`` /
``plain_llm_df_doc_union``），产出：

- **主对比**：doc vs df 配对 McNemar（精确；单向 H2: doc > df）+ BF10 + MDE；
- **绝对线核对**：doc detection（41 缺陷程序口径可判定子集）vs 65% 成功线 /
  55% 失败线；
- **次级对比**：union vs df（同口径，明示 secondary——不参与主判定）；
- **审计面**：``spec_replace_applied`` 命中统计（锚覆盖分母）、特异性门
  verdict 分布、输入工件 sha256；
- **判定**：confirmed / trend / not_confirmed（预注册 §3 逐条锁定）。

预注册：``docs/emse/EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md``（本地件）；
判据常量与 §3 表逐项对齐，改动须同步预注册（脚本内含一致性注释锚）。
机制指标（misguided/effective 逐测试三分）由 T2 工具
``experiments/misguided_metrics.py`` 独立产出（口径见
``docs/design/misguided_effective_metric.md``），本脚本**不**复算该指标，
只在报告中声明其口径与（可选的）工件路径/sha256——两套数字不得互相顶替。

用法：
    python -m experiments.emse_docstring_anchor_analysis \\
        --df <df.json> --doc <doc.json> [--union <union.json>] \\
        [--out report.json] [--markdown report.md]

fail-closed：缺臂 / 臂内无任务行 / 行数或行集合与对照臂不一致 / 可判定配对
为 0 → 明确报错并 exit 1（不产出口径残缺的判定）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.emse_df_spec_analysis import (  # noqa: E402
    MissingArtifactError,
    contrast,
    defect_program_ids,
    detection_summary,
    domain_stats,
    load_arm_rows,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# ─── 预注册常量（EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md §3；改此表必须同步预注册）──
SUCCESS_LINE = 0.65  # C1：doc detection ≥ 65%（41 口径可判定子集）
FAIL_LINE = 0.55  # 失败线（独立标记）：detection < 55%
CONFIRM_P = 0.05  # C2：单向 H2（doc > df）精确 p < 0.05
TREND_P = 0.10  # trend：p < 0.10 ∧ δ > 0
MISGUIDED_DROP_TARGET = 0.30  # 机制指标（T2 产出）：misguided 占比相对 df 降 ≥30%

# 臂名与口径（预注册 §2；与 run_benchmark.BASELINE_REGISTRY 一致）
CONTROL_ARM = "plain_llm_df"
PRIMARY_ARM = "plain_llm_df_doc"
UNION_ARM = "plain_llm_df_doc_union"
PRIMARY_CONTRAST = "doc_vs_df"
SECONDARY_CONTRAST = "union_vs_df"
PREREG_FILE = "docs/emse/EMSE_DOCSTRING_ANCHOR_PREREG_2026-10-17.md"
MECHANISM_PRODUCER = "experiments/misguided_metrics.py"
MECHANISM_CALIBER_DOC = "docs/design/misguided_effective_metric.md"

# 常量的"单一事实源"复述进报告（审计可核对；测试锁 v1）
PREREG_CONSTANTS: dict[str, Any] = {
    "success_line": SUCCESS_LINE,
    "fail_line": FAIL_LINE,
    "confirm_p": CONFIRM_P,
    "trend_p": TREND_P,
    "misguided_drop_target": MISGUIDED_DROP_TARGET,
    "primary_contrast": PRIMARY_CONTRAST,
    "secondary_contrast": SECONDARY_CONTRAST,
}


def _file_sha256(path: Path) -> str:
    """输入工件内容 sha256（报告可追到具体字节；零 LLM）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_arm_rows(
    label: str,
    rows: dict[str, dict[str, Any]],
    *,
    expected_rows: int | None = None,
    expected_ids: set[str] | None = None,
) -> None:
    """fail-closed 行数/行集合校验（缺臂与半写工件不得产出判定）。

    Args:
        label: 臂标签（错误消息用）。
        rows: 该臂 task_id → 行摘要映射。
        expected_rows: 对照臂行数（None = 不校验，用于对照臂自身）。
        expected_ids: 对照臂 task_id 集合（None = 不校验）。

    Raises:
        MissingArtifactError: 空臂 / 行数不符 / task_id 集合与对照臂不一致。
    """
    if not rows:
        raise MissingArtifactError(f"臂 {label!r} 无任务行（空工件或臂键错配）")
    if expected_rows is not None and len(rows) != expected_rows:
        raise MissingArtifactError(
            f"臂 {label!r} 行数异常：{len(rows)} ≠ 对照臂 {expected_rows}（批次不完整或臂文件错配）"
        )
    if expected_ids is not None and set(rows) != expected_ids:
        missing = sorted(expected_ids - set(rows))[:5]
        extra = sorted(set(rows) - expected_ids)[:5]
        raise MissingArtifactError(f"臂 {label!r} task_id 集合与对照臂不一致（缺 {missing} / 多 {extra}）")


# ─── 判定（预注册 §3 三态 + 绝对线/失败线）─────────────────────────────────
def decide(contrast_result: dict[str, Any], rate: float | None) -> dict[str, Any]:
    """按预注册规则判定（主判定与次级对比共用同一判定函数）。

    - confirmed：rate ≥ 0.65 ∧ 单向 p < 0.05；
    - trend：单向 p < 0.10 ∧ δ > 0（方向为正、未达显著性）；
    - not_confirmed：其余；
    - fail_line_triggered：rate < 0.55（独立标记，与三态并列报告）。
    """
    p1 = contrast_result["p_one_sided"]
    delta = contrast_result["delta_pp"]
    if rate is None:
        verdict = "not_confirmed"
        confirmed = trend = False
    else:
        confirmed = rate >= SUCCESS_LINE and p1 < CONFIRM_P
        trend = (not confirmed) and p1 < TREND_P and delta > 0
        verdict = "confirmed" if confirmed else ("trend" if trend else "not_confirmed")
    return {
        "verdict": verdict,
        "conditions": {
            "absolute_line": {
                "threshold": SUCCESS_LINE,
                "rate": rate,
                "met": None if rate is None else rate >= SUCCESS_LINE,
            },
            "one_sided_p_lt_0.05": p1 < CONFIRM_P,
            "direction_positive": delta > 0,
        },
        "fail_line_triggered": None if rate is None else rate < FAIL_LINE,
    }


# ─── 机制指标声明（T2 工具产出，本脚本只登记口径/工件，不复算）────────────
def mechanism_declaration(misguided_report: Path | None = None) -> dict[str, Any]:
    """预注册机制指标的来源声明（guided/effective 三分，T2 口径对齐）。

    P1 机制指标 = ISSTA'26 的逐测试三分：effective（buggy 败 ∧ fixed 过）/
    misguided（buggy 过 ∧ fixed 败）/ both_pass / both_fail（不可分类单列）。
    该指标由 ``experiments/misguided_metrics.py``（T2）产出；本脚本只声明
    口径与可选工件指纹，**不**以 over_red proxy 替代机制结论。
    """
    decl: dict[str, Any] = {
        "metric": "misguided_effective_per_test",
        "status": "external_declared",
        "producer": MECHANISM_PRODUCER,
        "caliber_doc": MECHANISM_CALIBER_DOC,
        "classes": ["effective", "misguided", "both_pass", "both_fail"],
        "misguided_drop_target": MISGUIDED_DROP_TARGET,
        "primary_arm": PRIMARY_ARM,
        "control_arm": CONTROL_ARM,
        "note": "机制指标为描述性/次级信号，不参与主判定；与 detection 分开报告，不得互相顶替",
    }
    if misguided_report is not None:
        decl["report"] = str(misguided_report)
        decl["report_sha256"] = _file_sha256(misguided_report) if misguided_report.is_file() else None
    return decl


# ─── 完整分析 ────────────────────────────────────────────────────────────────
def build_analysis(
    df_path: Path,
    doc_path: Path,
    union_path: Path | None = None,
    *,
    df_arm: str = CONTROL_ARM,
    doc_arm: str = PRIMARY_ARM,
    union_arm: str = UNION_ARM,
    misguided_report: Path | None = None,
) -> dict[str, Any]:
    """完整分析：加载 → 行集校验 → 41 口径主判定 + 次级对比 + 审计面。

    Args:
        df_path: 对照臂（plain_llm_df）批次 JSON。
        doc_path: 处理臂 A（plain_llm_df_doc）批次 JSON。
        union_path: 处理臂 B（plain_llm_df_doc_union）批次 JSON（可选；缺省
            时次级对比标 null 并在报告中披露）。
        df_arm/doc_arm/union_arm: 工件内臂键名（单臂文件由臂键显式指定）。
        misguided_report: 可选 T2 机制指标工件（只登记指纹，不解析口径）。

    Raises:
        MissingArtifactError: 缺臂/行数异常/可判定配对为 0。
    """
    df_rows = load_arm_rows(df_path, df_arm)
    doc_rows = load_arm_rows(doc_path, doc_arm)
    expected_rows = len(df_rows)
    expected_ids = set(df_rows)
    validate_arm_rows(CONTROL_ARM, df_rows)
    validate_arm_rows(PRIMARY_ARM, doc_rows, expected_rows=expected_rows, expected_ids=expected_ids)
    union_rows: dict[str, dict[str, Any]] | None = None
    if union_path is not None:
        union_rows = load_arm_rows(union_path, union_arm)
        validate_arm_rows(UNION_ARM, union_rows, expected_rows=expected_rows, expected_ids=expected_ids)

    main41 = defect_program_ids(df_rows) & defect_program_ids(doc_rows)
    if not main41:
        raise MissingArtifactError("41 缺陷程序口径交集为空（task_id 命名口径异常，拒绝产出判定）")

    det_df = detection_summary(df_rows, main41)
    det_doc = detection_summary(doc_rows, main41)
    c_doc = contrast(doc_rows, df_rows, main41)
    if c_doc["n_pairs"] == 0:
        raise MissingArtifactError("doc vs df 可判定配对为 0（两侧 detection 全 None，判定无分母）")
    primary = decide(c_doc, det_doc["rate"])

    detection: dict[str, Any] = {"df": det_df, "doc": det_doc}
    contrast_map: dict[str, Any] = {PRIMARY_CONTRAST: c_doc}
    secondary: dict[str, Any] | None = None
    if union_rows is not None:
        det_union = detection_summary(union_rows, main41)
        c_union = contrast(union_rows, df_rows, main41)
        if c_union["n_pairs"] == 0:
            raise MissingArtifactError("union vs df 可判定配对为 0（判定无分母）")
        detection["union"] = det_union
        contrast_map[SECONDARY_CONTRAST] = c_union
        secondary = decide(c_union, det_union["rate"])
        secondary["role"] = "secondary"
        secondary["note"] = "次级对比（预注册声明），不参与主判定"

    audit: dict[str, Any] = {
        "caliber": "QuixBugs 41 缺陷程序（task_id 非 _test 后缀）；可判定子集（detection 非 None）",
        "denominators": {
            "arm_rows": expected_rows,
            "defect_program_ids_41": len(main41),
            "measurable_pairs_doc_vs_df": c_doc["n_pairs"],
        },
        "spec_replace_applied": {
            "df": domain_stats(df_rows, "spec_replace_applied"),
            "doc": domain_stats(doc_rows, "spec_replace_applied"),
            "doc_41": domain_stats(doc_rows, "spec_replace_applied", main41),
        },
        "specificity_gate_verdict": {
            "df_41": domain_stats(df_rows, "specificity_gate_verdict", main41),
            "doc_41": domain_stats(doc_rows, "specificity_gate_verdict", main41),
        },
        "detection_none_rows": {
            "df_41": det_df["denominator_rows"] - det_df["measurable"],
            "doc_41": det_doc["denominator_rows"] - det_doc["measurable"],
        },
    }
    if union_rows is not None:
        audit["spec_replace_applied"]["union"] = domain_stats(union_rows, "spec_replace_applied")
        audit["spec_replace_applied"]["union_41"] = domain_stats(union_rows, "spec_replace_applied", main41)
        audit["specificity_gate_verdict"]["union_41"] = domain_stats(union_rows, "specificity_gate_verdict", main41)
        audit["detection_none_rows"]["union_41"] = det_union["denominator_rows"] - det_union["measurable"]

    inputs: dict[str, Any] = {
        "df": {"path": str(df_path), "arm": df_arm, "sha256": _file_sha256(df_path)},
        "doc": {"path": str(doc_path), "arm": doc_arm, "sha256": _file_sha256(doc_path)},
    }
    if union_path is not None:
        inputs["union"] = {"path": str(union_path), "arm": union_arm, "sha256": _file_sha256(union_path)}

    return {
        "verdict": primary["verdict"],
        "conditions": primary["conditions"],
        "fail_line_triggered": primary["fail_line_triggered"],
        "secondary": secondary,
        "contrast": contrast_map,
        "detection": detection,
        "audit": audit,
        "prereg": {"file": PREREG_FILE, "constants": PREREG_CONSTANTS},
        "mechanism": mechanism_declaration(misguided_report),
        "inputs": inputs,
    }


# ─── Markdown 摘要 ───────────────────────────────────────────────────────────
def _fmt_rate(summary: dict[str, Any]) -> str:
    rate = summary["rate"]
    return (
        "n/a（无可判定子集）" if rate is None else f"{rate * 100:.1f}%（{summary['positive']}/{summary['measurable']}）"
    )


def _fmt_percent(rate: float | None) -> str:
    """比例 → 百分比文本（None → n/a）。"""
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def render_markdown(result: dict[str, Any]) -> str:
    """把分析结果渲染为可粘贴的 Markdown 摘要（判定 + 对比 + 审计披露）。"""
    lines: list[str] = [
        "# docstring 独立锚三臂实验判定报告（P1 / A-02）",
        "",
        f"> 预注册：`{result['prereg']['file']}`；本报告由 "
        "`experiments/emse_docstring_anchor_analysis.py` 直出（数字不得手写）。",
        "",
        "## 1. 主判定（doc vs df）",
        "",
        f"**verdict：`{result['verdict']}`**"
        + ("（失败线触发：doc detection < 55%）" if result["fail_line_triggered"] else ""),
        "",
        "| 条件 | 结果 |",
        "|---|---|",
        f"| 绝对线 doc detection ≥ {SUCCESS_LINE:.0%} | "
        f"{_fmt_percent(result['conditions']['absolute_line']['rate'])}"
        f"（met={result['conditions']['absolute_line']['met']}） |",
        f"| 单向 McNemar p < {CONFIRM_P} | {result['conditions']['one_sided_p_lt_0.05']} |",
        f"| 方向 δ > 0 | {result['conditions']['direction_positive']} |",
        "",
        "## 2. 检出率（41 缺陷程序口径，可判定子集）",
        "",
        "| 臂 | detection | 可判定/41 行 |",
        "|---|---|---|",
        f"| df（对照） | {_fmt_rate(result['detection']['df'])} | "
        f"{result['detection']['df']['measurable']}/{result['detection']['df']['denominator_rows']} |",
        f"| doc（处理 A） | {_fmt_rate(result['detection']['doc'])} | "
        f"{result['detection']['doc']['measurable']}/{result['detection']['doc']['denominator_rows']} |",
    ]
    if "union" in result["detection"]:
        lines.append(
            f"| union（处理 B） | {_fmt_rate(result['detection']['union'])} | "
            f"{result['detection']['union']['measurable']}/{result['detection']['union']['denominator_rows']} |"
        )
    lines += [
        "",
        "## 3. 配对对比（精确 McNemar）",
        "",
        "| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, role in ((PRIMARY_CONTRAST, "主"), (SECONDARY_CONTRAST, "次级")):
        c = result["contrast"].get(name)
        if c is None:
            continue
        lines.append(
            f"| {name}（{role}） | {c['n_pairs']} | {c['ratio']} | {c['delta_pp']:+.2f}pp | "
            f"{c['p_one_sided']} | {c['p_two_sided']} | {c['bf10']} | {c['mde_pp']}pp |"
        )
    if result["secondary"] is None:
        lines += ["", "> union 臂未提供：次级对比缺失（预注册允许的缺省，报告如实披露）。"]
    lines += ["", "## 4. 审计面", ""]
    for arm in ("df", "doc"):
        dist = result["audit"]["spec_replace_applied"][arm]
        lines.append(f"- `spec_replace_applied` {arm}：{json.dumps(dist, ensure_ascii=False, sort_keys=True)}")
    if "union" in result["audit"]["spec_replace_applied"]:
        dist = result["audit"]["spec_replace_applied"]["union"]
        lines.append(f"- `spec_replace_applied` union：{json.dumps(dist, ensure_ascii=False, sort_keys=True)}")
    denominators = result["audit"]["denominators"]
    lines += [
        f"- 分母：臂行 {denominators['arm_rows']} / 41 口径任务 "
        f"{denominators['defect_program_ids_41']} / doc-vs-df 可判定配对 "
        f"{denominators['measurable_pairs_doc_vs_df']}",
        f"- 机制指标（次级，描述性）：由 `{result['mechanism']['producer']}` 产出（口径见 "
        f"`{result['mechanism']['caliber_doc']}`；目标 misguided 占比降幅 ≥"
        f"{result['mechanism']['misguided_drop_target']:.0%}）——与 detection 分开报告。",
        "",
        "## 5. 披露",
        "",
        "- MDE（n=可判定配对、80% power、α=0.05 近似）：见上表；设计敏感性与失败线见预注册 §3/§4。",
        "- 单模型（deepseek-flash）/ QuixBugs 单数据集；跨批波动与 MDE 解读见预注册 §4。",
        "- 数字由脚本从输入 JSON 复算，输入 sha256 见 JSON 报告 `inputs` 块。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--df", required=True, help="对照臂（plain_llm_df）批次 JSON")
    ap.add_argument("--doc", required=True, help="处理臂 A（plain_llm_df_doc）批次 JSON")
    ap.add_argument("--union", default=None, help="处理臂 B（plain_llm_df_doc_union）批次 JSON（可选）")
    ap.add_argument("--df-arm", default=CONTROL_ARM, help=f"对照臂键名（默认 {CONTROL_ARM}）")
    ap.add_argument("--doc-arm", default=PRIMARY_ARM, help=f"处理臂 A 键名（默认 {PRIMARY_ARM}）")
    ap.add_argument("--union-arm", default=UNION_ARM, help=f"处理臂 B 键名（默认 {UNION_ARM}）")
    ap.add_argument("--misguided-report", default=None, help="可选 T2 机制指标工件（只登记路径/sha256）")
    ap.add_argument("--out", default=None, help="结果落盘路径（JSON）")
    ap.add_argument("--markdown", default=None, help="Markdown 摘要落盘路径")
    args = ap.parse_args(argv)

    try:
        result = build_analysis(
            Path(args.df),
            Path(args.doc),
            Path(args.union) if args.union else None,
            df_arm=args.df_arm,
            doc_arm=args.doc_arm,
            union_arm=args.union_arm,
            misguided_report=Path(args.misguided_report) if args.misguided_report else None,
        )
    except MissingArtifactError as e:
        print(f"[emse_docstring_anchor_analysis] ✗ {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        atomic_write_json(str(args.out), result)
        print(f"[emse_docstring_anchor_analysis] 已落盘 JSON：{args.out}")
    if args.markdown:
        md = render_markdown(result)
        Path(args.markdown).write_text(md, encoding="utf-8")
        print(f"[emse_docstring_anchor_analysis] 已落盘 Markdown：{args.markdown}")
    print(
        f"[emse_docstring_anchor_analysis] verdict={result['verdict']} "
        f"fail_line={result['fail_line_triggered']} "
        f"secondary={result['secondary']['verdict'] if result['secondary'] else None}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
