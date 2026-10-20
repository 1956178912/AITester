"""M-1 规格增广双臂实验分析（预注册件，2026-10-17）。

零 LLM：读 2 臂批次 JSON（``plain_llm_df`` 对照 / ``plain_llm_df_doc_augment``
处理），产出：

- **主对比**：augment vs df 配对 McNemar（精确；单向 H1: augment > df）+ BF10 + MDE；
- **绝对线核对**：augment detection（41 缺陷程序口径可判定子集）vs 88% 成功线 /
  78% 失败线；
- **non-inferiority（独立标记）**：配对 δ ≥ −5pp（不改变三态 verdict，但必须
  显式报告——即使未提升，不劣化 ≥5pp 即保留"代码保留假设成立"的方向证据）；
- **审计面**：``spec_augment_applied`` 命中统计（增广覆盖分母）、
  ``spec_replace_applied`` 互斥核验（模式未串）、特异性门 verdict 分布、
  输入工件 sha256；
- **判定**：confirmed / trend / not_confirmed（预注册 §3 逐条锁定）；
- **机制指标声明**：misguided/effective 逐测试三分由 T2 工具
  ``experiments/misguided_metrics.py`` 跑后重放（本脚本只登记路径/口径/sha256，
  不复算、不以 over_red proxy 顶替）。

预注册：``docs/study/DOCSTRING_AUGMENT_PREREG_2026-10-17.md``（本地件）；
判据常量与 §3 表逐项对齐，改动须同步预注册（脚本内含一致性注释锚）。

用法：
    python -m experiments.emse_docstring_augment_analysis \\
        --df <df.json> --augment <augment.json> \\
        [--out report.json] [--markdown report.md] [--misguided-report <T2工件>]

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

from experiments.emse_docstring_anchor_analysis import (  # noqa: E402
    MissingArtifactError,
    contrast,
    defect_program_ids,
    detection_summary,
    domain_stats,
    load_arm_rows,
    validate_arm_rows,
)
from experiments.emse_quixbugs_specir_expand import mde_two_proportion  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# ─── 预注册常量（DOCSTRING_AUGMENT_PREREG_2026-10-17.md §3；改此表必须同步预注册）──
SUCCESS_LINE = 0.88  # C1：augment detection ≥ 88%（41 口径可判定子集）
FAIL_LINE = 0.78  # 失败线（独立标记）：detection < 78%（相对同批 df 明显损失）
CONFIRM_P = 0.05  # C2：单向 H1（augment > df）精确 p < 0.05
TREND_P = 0.10  # trend：绝对线达标 ∧ p < 0.10 ∧ δ > 0
NON_INFERIORITY_MARGIN_PP = -5.0  # 非劣边界（配对 δ pp；独立于三态 verdict）
MDE_REFERENCE_N = 35  # L 轮可判定配对先例（MDE 披露基准 n）

# 臂名与口径（预注册 §2；与 run_benchmark.BASELINE_REGISTRY 一致）
CONTROL_ARM = "plain_llm_df"
PRIMARY_ARM = "plain_llm_df_doc_augment"
PRIMARY_CONTRAST = "augment_vs_df"
PREREG_FILE = "docs/study/DOCSTRING_AUGMENT_PREREG_2026-10-17.md"
MECHANISM_PRODUCER = "experiments/misguided_metrics.py"
MECHANISM_CALIBER_DOC = "docs/design/misguided_effective_metric.md"
MDE_DISCLOSURE = (
    "n≈35（L 轮可判定配对先例）时 80% power / α=0.05 的双比例 MDE≈16.6pp；"
    "本设计属边缘功效——小于 MDE 的效应不可判定，阴性结果不得读作'无效应'"
)

# 常量的"单一事实源"复述进报告（审计可核对；测试锁 v1）
PREREG_CONSTANTS: dict[str, Any] = {
    "success_line": SUCCESS_LINE,
    "fail_line": FAIL_LINE,
    "confirm_p": CONFIRM_P,
    "trend_p": TREND_P,
    "non_inferiority_margin_pp": NON_INFERIORITY_MARGIN_PP,
    "mde_reference_n": MDE_REFERENCE_N,
    "primary_contrast": PRIMARY_CONTRAST,
}


def _file_sha256(path: Path) -> str:
    """输入工件内容 sha256（报告可追到具体字节；零 LLM）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


AUDIT_KEY_ABSENT = "key_absent"
AUDIT_UNREADABLE = "audit_unreadable"


def load_augment_rows(path: Path, arm_key: str) -> dict[str, dict[str, Any]]:
    """加载臂行摘要并补 ``spec_augment_applied`` 字段（复用共享 loader）。

    复用 ``emse_df_spec_analysis.load_arm_rows``（定义处；anchor 与 augment 都只 import 它，
    AB-11/AB-12c 的登记曾把定义处误写成 anchor）的臂解析 / fail-closed
    口径（缺失 / 损坏 / 臂键错配 → ``MissingArtifactError``）；该 loader 的行
    摘要不含本轮的增广审计字段，故二次读取原始 JSON 补齐（只增字段，不改
    既有行摘要语义）。

    值域三态（AB-11）：判定只用 detection，审计面用本字段，故读不动时**不**
    抛错、而是落到不会与产物值混淆的桶——生产者写下的 ``null`` 仍是 ``None``
    （``domain_stats`` 的 ``none`` 桶 = 真的没触发）；详情行根本没有这个键 →
    ``key_absent``；第二遍原始读取失败或 task_id 对不上行集 → ``audit_unreadable``
    并向 stderr 报一条命名 WARN。三者都不参与判定，但后两者不得再被读成
    "增广零命中"（缺席 / 读不动 ≠ 零命中）。
    """
    rows = load_arm_rows(path, arm_key)
    for summary in rows.values():
        summary["spec_augment_applied"] = AUDIT_UNREADABLE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        details = raw["results"][arm_key]["details"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(
            f"[WARN] {path.name}：臂 {arm_key!r} 审计字段第二遍读取失败（{type(e).__name__}: {e}）——"
            f"{len(rows)} 行全部按 {AUDIT_UNREADABLE!r} 记账，不得读成'增广零命中'",
            file=sys.stderr,
        )
        return rows
    matched = 0
    for row in details:
        tid = str(row.get("task_id", ""))
        if tid in rows:
            matched += 1
            rows[tid]["spec_augment_applied"] = row.get("spec_augment_applied", AUDIT_KEY_ABSENT)
    if matched != len(rows) or len(details) != len(rows):
        gap = len(rows) - matched
        tail = (
            f"其中 {gap} 行未回填，按 {AUDIT_UNREADABLE!r} 记账"
            if gap > 0
            else "行集本身已缩，且后出现的同 id 行会覆盖先出现的审计值"
        )
        print(
            f"[WARN] {path.name}：臂 {arm_key!r} 审计字段回填与行集对不上"
            f"（details 行 {len(details)} / 回填 {matched} / 行摘要 {len(rows)}）——"
            f"重复或类型不符的 task_id 会静默缩分母，{tail}，不得读成'增广零命中'",
            file=sys.stderr,
        )
    return rows


# ─── 判定（预注册 §3 三态 + 失败线 + non-inferiority 独立标记）─────────────
def decide(contrast_result: dict[str, Any], rate: float | None) -> dict[str, Any]:
    """按预注册规则判定（M-1 主判定）。

    - confirmed：augment detection ≥ 88% ∧ 单向 p < 0.05；
    - trend：augment detection ≥ 88% ∧ 单向 p < 0.10 ∧ δ > 0（方向为正、未达显著）；
    - not_confirmed：其余；
    - fail_line_triggered：rate < 78%（独立标记，与三态并列报告）；
    - non_inferiority：配对 δ ≥ −5pp（**独立标记，不参与三态 verdict**）。
    """
    p1 = contrast_result["p_one_sided"]
    delta = contrast_result["delta_pp"]
    if rate is None:
        verdict = "not_confirmed"
        confirmed = trend = False
    else:
        confirmed = rate >= SUCCESS_LINE and p1 < CONFIRM_P
        trend = (not confirmed) and rate >= SUCCESS_LINE and p1 < TREND_P and delta > 0
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
        "non_inferiority": {
            "margin_pp": NON_INFERIORITY_MARGIN_PP,
            "delta_pp": delta,
            "met": None if rate is None else delta >= NON_INFERIORITY_MARGIN_PP,
            "role": "independent_marker",
            "note": "非劣标记独立于三态判定，不改变 verdict；用于保留'代码保留假设'方向证据",
        },
    }


# ─── 机制指标声明（T2 工具产出，本脚本只登记口径/工件，不复算）────────────
def mechanism_declaration(misguided_report: Path | None = None) -> dict[str, Any]:
    """预注册机制指标的来源声明（guided/effective 三分，T2 口径对齐）。

    M-1 机制指标 = ISSTA'26 的逐测试三分：effective（buggy 败 ∧ fixed 过）/
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
        "primary_arm": PRIMARY_ARM,
        "control_arm": CONTROL_ARM,
        "expectation": (
            "描述性：augment 臂 misguided 占比不高于 df 臂（同一缺陷代码仍在 prompt 中，"
            "misguidance 可能无法消除；增广的预期是'不额外增加 misguided 且检出不降'）"
        ),
        "note": "机制指标为描述性/次级信号，不参与主判定；与 detection 分开报告，不得互相顶替",
    }
    if misguided_report is not None:
        decl["report"] = str(misguided_report)
        decl["report_sha256"] = _file_sha256(misguided_report) if misguided_report.is_file() else None
    return decl


# ─── 完整分析 ────────────────────────────────────────────────────────────────
def build_analysis(
    df_path: Path,
    augment_path: Path,
    *,
    df_arm: str = CONTROL_ARM,
    augment_arm: str = PRIMARY_ARM,
    misguided_report: Path | None = None,
) -> dict[str, Any]:
    """完整分析：加载 → 行集校验 → 41 口径主判定 + non-inferiority + 审计面。

    Args:
        df_path: 对照臂（plain_llm_df）批次 JSON。
        augment_path: 处理臂（plain_llm_df_doc_augment）批次 JSON。
        df_arm / augment_arm: 工件内臂键名（单臂文件由臂键显式指定）。
        misguided_report: 可选 T2 机制指标工件（只登记指纹，不解析口径）。

    Raises:
        MissingArtifactError: 缺臂 / 行数或行集合异常 / 可判定配对为 0 /
            41 缺陷程序口径交集为空。
    """
    df_rows = load_augment_rows(df_path, df_arm)
    augment_rows = load_augment_rows(augment_path, augment_arm)
    expected_rows = len(df_rows)
    expected_ids = set(df_rows)
    validate_arm_rows(CONTROL_ARM, df_rows)
    validate_arm_rows(PRIMARY_ARM, augment_rows, expected_rows=expected_rows, expected_ids=expected_ids)

    main41 = defect_program_ids(df_rows) & defect_program_ids(augment_rows)
    if not main41:
        raise MissingArtifactError("41 缺陷程序口径交集为空（task_id 命名口径异常，拒绝产出判定）")

    det_df = detection_summary(df_rows, main41)
    det_aug = detection_summary(augment_rows, main41)
    c_main = contrast(augment_rows, df_rows, main41)
    if c_main["n_pairs"] == 0:
        raise MissingArtifactError("augment vs df 可判定配对为 0（两侧 detection 全 None，判定无分母）")
    primary = decide(c_main, det_aug["rate"])

    audit: dict[str, Any] = {
        "caliber": "QuixBugs 41 缺陷程序（task_id 非 _test 后缀）；可判定子集（detection 非 None）",
        "denominators": {
            "arm_rows": expected_rows,
            "defect_program_ids_41": len(main41),
            "measurable_pairs_augment_vs_df": c_main["n_pairs"],
        },
        "spec_augment_applied": {
            "df": domain_stats(df_rows, "spec_augment_applied"),
            "augment": domain_stats(augment_rows, "spec_augment_applied"),
            "augment_41": domain_stats(augment_rows, "spec_augment_applied", main41),
        },
        # 互斥核验：augment 臂不应出现 replace 审计值（模式未串）
        "spec_replace_applied": {
            "df": domain_stats(df_rows, "spec_replace_applied"),
            "augment": domain_stats(augment_rows, "spec_replace_applied"),
        },
        "specificity_gate_verdict": {
            "df_41": domain_stats(df_rows, "specificity_gate_verdict", main41),
            "augment_41": domain_stats(augment_rows, "specificity_gate_verdict", main41),
        },
        "detection_none_rows": {
            "df_41": det_df["denominator_rows"] - det_df["measurable"],
            "augment_41": det_aug["denominator_rows"] - det_aug["measurable"],
        },
    }

    inputs: dict[str, Any] = {
        "df": {"path": str(df_path), "arm": df_arm, "sha256": _file_sha256(df_path)},
        "augment": {"path": str(augment_path), "arm": augment_arm, "sha256": _file_sha256(augment_path)},
    }

    return {
        "verdict": primary["verdict"],
        "conditions": primary["conditions"],
        "fail_line_triggered": primary["fail_line_triggered"],
        "non_inferiority": primary["non_inferiority"],
        "contrast": {PRIMARY_CONTRAST: c_main},
        "detection": {"df": det_df, "augment": det_aug},
        "mde": {
            "reference_n": MDE_REFERENCE_N,
            "mde_pp_at_reference_n": mde_two_proportion(MDE_REFERENCE_N),
            "observed_n_pairs": c_main["n_pairs"],
            "observed_mde_pp": c_main["mde_pp"],
            "disclosure": MDE_DISCLOSURE,
        },
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
    c = result["contrast"][PRIMARY_CONTRAST]
    non_inf = result["non_inferiority"]
    lines: list[str] = [
        "# 规格增广双臂实验判定报告（M-1，2026-10-17）",
        "",
        f"> 预注册：`{result['prereg']['file']}`；本报告由 "
        "`experiments/emse_docstring_augment_analysis.py` 直出（数字不得手写）。",
        "",
        "## 1. 主判定（augment vs df）",
        "",
        f"**verdict：`{result['verdict']}`**"
        + ("（失败线触发：augment detection < 78%）" if result["fail_line_triggered"] else ""),
        "",
        "| 条件 | 结果 |",
        "|---|---|",
        f"| 绝对线 augment detection ≥ {SUCCESS_LINE:.0%} | "
        f"{_fmt_percent(result['conditions']['absolute_line']['rate'])}"
        f"（met={result['conditions']['absolute_line']['met']}） |",
        f"| 单向 McNemar p < {CONFIRM_P} | {result['conditions']['one_sided_p_lt_0.05']} |",
        f"| 方向 δ > 0 | {result['conditions']['direction_positive']} |",
        f"| 失败线（独立标记）augment detection < {FAIL_LINE:.0%} | "
        f"{'⚠️ 触发' if result['fail_line_triggered'] else '未触发'} |",
        "",
        "## 2. non-inferiority（独立标记，不参与 verdict）",
        "",
        f"- 边界：配对 δ ≥ **{non_inf['margin_pp']:+.1f}pp**；实测 δ = **{non_inf['delta_pp']:+.2f}pp**；"
        f"met = **{non_inf['met']}**",
        "",
        "## 3. 检出率（41 缺陷程序口径，可判定子集）",
        "",
        "| 臂 | detection | 可判定/41 行 |",
        "|---|---|---|",
        f"| df（对照） | {_fmt_rate(result['detection']['df'])} | "
        f"{result['detection']['df']['measurable']}/{result['detection']['df']['denominator_rows']} |",
        f"| augment（处理） | {_fmt_rate(result['detection']['augment'])} | "
        f"{result['detection']['augment']['measurable']}/{result['detection']['augment']['denominator_rows']} |",
        "",
        "## 4. 配对对比（精确 McNemar）",
        "",
        "| 对比 | 配对 n | a 独有 : b 独有 | δ | 单向 p | 双向 p | BF10 | MDE |",
        "|---|---|---|---|---|---|---|---|",
        f"| {PRIMARY_CONTRAST}（主） | {c['n_pairs']} | {c['ratio']} | {c['delta_pp']:+.2f}pp | "
        f"{c['p_one_sided']} | {c['p_two_sided']} | {c['bf10']} | {c['mde_pp']}pp |",
        "",
        "## 5. 审计面",
        "",
    ]
    for arm in ("df", "augment"):
        dist = result["audit"]["spec_augment_applied"][arm]
        lines.append(f"- `spec_augment_applied` {arm}：{json.dumps(dist, ensure_ascii=False, sort_keys=True)}")
    lines.append(
        "- `spec_replace_applied`（互斥核验，应全为 none）："
        + json.dumps(result["audit"]["spec_replace_applied"], ensure_ascii=False, sort_keys=True)
    )
    denominators = result["audit"]["denominators"]
    lines += [
        f"- 分母：臂行 {denominators['arm_rows']} / 41 口径任务 "
        f"{denominators['defect_program_ids_41']} / augment-vs-df 可判定配对 "
        f"{denominators['measurable_pairs_augment_vs_df']}",
        f"- 机制指标（次级，描述性）：由 `{result['mechanism']['producer']}` 产出（口径见 "
        f"`{result['mechanism']['caliber_doc']}`）——与 detection 分开报告。",
        "",
        "## 6. 披露",
        "",
        f"- MDE：{result['mde']['disclosure']}；本批配对 n={result['mde']['observed_n_pairs']}，"
        f"MDE={result['mde']['observed_mde_pp']}pp（reference n={result['mde']['reference_n']} 时 "
        f"{result['mde']['mde_pp_at_reference_n']}pp）。",
        "- 单模型（deepseek-flash）/ QuixBugs 单数据集 / 单 seed；跨批波动与 MDE 解读见预注册 §4。",
        "- 数字由脚本从输入 JSON 复算，输入 sha256 见 JSON 报告 `inputs` 块。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--df", required=True, help="对照臂（plain_llm_df）批次 JSON")
    ap.add_argument("--augment", required=True, help="处理臂（plain_llm_df_doc_augment）批次 JSON")
    ap.add_argument("--df-arm", default=CONTROL_ARM, help=f"对照臂键名（默认 {CONTROL_ARM}）")
    ap.add_argument("--augment-arm", default=PRIMARY_ARM, help=f"处理臂键名（默认 {PRIMARY_ARM}）")
    ap.add_argument("--misguided-report", default=None, help="可选 T2 机制指标工件（只登记路径/sha256）")
    ap.add_argument("--out", default=None, help="结果落盘路径（JSON）")
    ap.add_argument("--markdown", default=None, help="Markdown 摘要落盘路径")
    args = ap.parse_args(argv)

    try:
        result = build_analysis(
            Path(args.df),
            Path(args.augment),
            df_arm=args.df_arm,
            augment_arm=args.augment_arm,
            misguided_report=Path(args.misguided_report) if args.misguided_report else None,
        )
    except MissingArtifactError as e:
        print(f"[emse_docstring_augment_analysis] ✗ {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        atomic_write_json(str(args.out), result)
        print(f"[emse_docstring_augment_analysis] 已落盘 JSON：{args.out}")
    if args.markdown:
        md = render_markdown(result)
        Path(args.markdown).write_text(md, encoding="utf-8")
        print(f"[emse_docstring_augment_analysis] 已落盘 Markdown：{args.markdown}")
    print(
        f"[emse_docstring_augment_analysis] verdict={result['verdict']} "
        f"fail_line={result['fail_line_triggered']} "
        f"non_inferiority={result['non_inferiority']['met']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
