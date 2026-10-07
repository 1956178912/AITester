"""修正口径重估总报告（修复引擎批次 XIII，ADR-0027，零 LLM）。

背景（ADR-0021 勘误义务的执行收口）：
    ADR-0021 定案 "repair 全线 0" 系测量伪影（patch 字段围栏残留）后，
    以下历史结论全部带连锁修正义务——本工具按**修正口径**一次性重估：
        1. false_fix 分布：原值由受染 repair_rate 推导（passed 行恒
           false_fix=1.0），修正后须重算；
        2. CPR（正确补丁保留率）：correct=0 时「诚实未定义」——修正
           correct>0 后首次可定义（弃权门阻断档转正判据 ② 的分母）；
        3. 弃权精确率：原「correct=0 按构造 = 1.0」是平凡值——修正后
           首次有信息量（阻断档转正判据 ① 的分子分母）；
        4. ADR-0024 归因结论的 bug_type 分层——谱系 FL 命中与缺陷难度
           混杂的解混杂检验（负相关是否在难度层内仍然成立）。

口径（全部零 LLM、可复算）：
    - 行级修正（correct_row）：patch 空 → 原指标即正确语义（repair=0
      非伪影），保留原值；patch 非空 → repair_replay.replay_row 重放：
      correct → patch_correct=1/repair_rate=1.0/false_fix=0.0；
      wrong_patch → 0/0.0/(passed?1.0:0.0)；diff 形态/无 gold 材料/
      执行异常 → 三键改 None（不可测，诚实降级）+ corrected_verdict
      标记；原口径对这些行恒 0/1.0（受染值）。
    - CPR/IDR/弃权：复用 cpr_idr_report._analyze（负信号集不受伪影
      影响）喂修正行；
    - bug_type 分层 CF：cf_upper_bound.fl_hit_value × 修正 correct 的
      2×2 按 metadata.bug_type 分层。

用法：
    python -m experiments.corrected_metrics experiments/results/main_batch \\
        --arm aitester [--out corrected_report.md] [--timeout 60]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _iter_batch_files(results_dir: str | Path) -> list[Path]:
    root = Path(results_dir)
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("benchmark_*.json") if p.is_file())


def _batch_label(name: str) -> str:
    """批次归属标签（按日期段划分实验代际，供分层报告）。

    20261006 = R-P0-2 生死实验三种子（seed 42/43/44，无 profile 门）；
    20261007 = E1/E2 迭代批（logic profile 双门）；其余 = 早期批次。
    """
    for marker, label in (
        ("20261006", "R-P0-2（10-06 三种子）"),
        ("20261007", "E1/E2 logic 档（10-07）"),
    ):
        if marker in name:
            return label
    return "早期批次"


def correct_row(row: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    """行级修正（ADR-0021 口径）：返回带 corrected_* 键的副本（纯函数）。

    修正规则见模块 docstring；无补丁行原指标语义本就正确（repair=0
    非伪影），键值原样保留并标 corrected_verdict=no_patch。
    """
    from experiments.repair_replay import replay_row

    corrected = dict(row)
    patch = str(row.get("patch") or "")
    if not patch.strip():
        corrected["corrected_verdict"] = "no_patch"
        return corrected
    verdict = replay_row(row, timeout=timeout)
    status = verdict["status"]
    corrected["corrected_verdict"] = status
    if status == "correct":
        corrected["patch_correct"] = 1
        corrected["repair_rate"] = 1.0
        corrected["false_fix_rate"] = 0.0
    elif status == "wrong_patch":
        corrected["patch_correct"] = 0
        corrected["repair_rate"] = 0.0
        corrected["false_fix_rate"] = 1.0 if row.get("passed") else 0.0
    else:
        # not_replayable_diff / skipped_no_material / unverifiable
        # ——原口径恒 patch_correct=0/false_fix=1.0 系受染值，改 None
        # （不可测诚实降级，与 M1 None 口径一致）
        corrected["patch_correct"] = None
        corrected["repair_rate"] = None
        corrected["false_fix_rate"] = None
    return corrected


def analyze_arm(results_dir: str | Path, arm: str, timeout: int = 60) -> dict[str, Any]:
    """单臂全量修正分析（确定性，无随机成分）。"""
    from experiments.cf_upper_bound import fl_hit_value
    from experiments.cpr_idr_report import _analyze

    files = _iter_batch_files(results_dir)
    corrected_rows: list[tuple[str, dict[str, Any]]] = []
    for f in files:
        try:
            batch = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        details = ((batch.get("results") or {}).get(arm) or {}).get("details") or []
        corrected_rows.extend((f.name, correct_row(row, timeout=timeout)) for row in details if isinstance(row, dict))

    # ── 1. 修正 repair（按批次代际）─────────────────────────────────
    gen: dict[str, dict[str, int | None]] = {}
    for name, row in corrected_rows:
        verdict = row.get("corrected_verdict")
        label = _batch_label(name)
        g = gen.setdefault(label, {"rows": 0, "patched": 0, "replayable": 0, "correct": 0, "repair_rate": None})
        g["rows"] = int(g["rows"]) + 1
        if verdict not in ("no_patch", "skipped_no_material"):
            g["patched"] = int(g["patched"]) + 1
        if verdict in ("correct", "wrong_patch"):
            g["replayable"] = int(g["replayable"]) + 1
            g["correct"] = int(g["correct"]) + int(verdict == "correct")
    for g in gen.values():
        replayable, correct = int(g["replayable"]), int(g["correct"])
        g["repair_rate"] = round(correct / replayable, 4) if replayable else None

    # ── 2. 修正 false_fix（passed 行，可测 correct 分母）────────────
    passed_total = passed_false_fix = passed_unknown = 0
    for _name, row in corrected_rows:
        if not row.get("passed"):
            continue
        if row.get("corrected_verdict") in ("correct", "wrong_patch", "no_patch"):
            passed_total += 1
            passed_false_fix += int(row.get("false_fix_rate") == 1.0 or row.get("patch_correct") == 0)
        else:
            passed_unknown += 1

    # ── 3. CPR/IDR/弃权修正视角（复用 cpr_idr 判定核）──────────────
    cpr_view = _analyze(corrected_rows)

    # ── 4. bug_type 分层 CF（解混杂检验）───────────────────────────
    strata: dict[str, dict[str, int]] = {}
    for _name, row in corrected_rows:
        verdict = row.get("corrected_verdict")
        if verdict not in ("correct", "wrong_patch"):
            continue
        fl_hit, _fl_source = fl_hit_value(row)
        if fl_hit is None:
            continue
        bug_type = str((row.get("task_metadata") or {}).get("bug_type") or "unknown")
        s = strata.setdefault(bug_type, {"hit": 0, "hit_correct": 0, "miss": 0, "miss_correct": 0})
        if fl_hit:
            s["hit"] += 1
            s["hit_correct"] += int(verdict == "correct")
        else:
            s["miss"] += 1
            s["miss_correct"] += int(verdict == "correct")

    return {
        "arm": arm,
        "n_files": len(files),
        "n_rows": len(corrected_rows),
        "verdict_dist": dict(Counter(str(r.get("corrected_verdict")) for _n, r in corrected_rows)),
        "generations": gen,
        "false_fix": {
            "passed_measurable": passed_total,
            "passed_false_fix": passed_false_fix,
            "passed_unknown": passed_unknown,
            "rate": round(passed_false_fix / passed_total, 4) if passed_total else None,
        },
        "cpr_view": cpr_view,
        "cf_strata": strata,
    }


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.4f}"


def build_report(results_dir: str | Path, arm: str, timeout: int = 60) -> str:
    """修正口径重估总报告（Markdown）。"""
    a = analyze_arm(results_dir, arm, timeout=timeout)
    cpr = a["cpr_view"]
    lines = [
        "# 修正口径重估总报告（ADR-0027，批次 XIII，零 LLM 存量回放）",
        "",
        f"- 目录：`{results_dir}`（{a['n_files']} 批次）；臂：`{a['arm']}`；行数：{a['n_rows']}",
        "- 口径：ADR-0021 修正（normalize_patch_text 清理后 gold 裁决）；"
        "无补丁行的原指标语义正确（repair=0 非伪影），保留原值。",
        f"- 行级裁决分布：{a['verdict_dist']}",
        "",
        "## 1. 修正 repair_rate（按实验代际）",
        "",
        "| 代际 | 行数 | 带补丁 | 可重放 | 修正 correct | 修正 repair_rate |",
        "|---|---|---|---|---|---|",
    ]
    for label, g in sorted(a["generations"].items()):
        lines.append(
            f"| {label} | {g['rows']} | {g['patched']} | {g['replayable']} "
            f"| {g['correct']} | {_pct(g['repair_rate'])} |"
        )
    ff = a["false_fix"]
    lines += [
        "",
        "## 2. 修正 false_fix 分布（passed 行）",
        "",
        f"- passed 可测行：{ff['passed_measurable']}（不可测 {ff['passed_unknown']} 行不计入分母）；",
        f"- **修正 false_fix 率：{_pct(ff['rate'])}**（{ff['passed_false_fix']}/{ff['passed_measurable']}）"
        "——历史口径（受染 repair 推导）下 passed 行恒 false_fix=1.0；",
        "",
        "## 3. CPR / IDR / 弃权视角（修正 correct 口径）",
        "",
        f"- plausible 行：{cpr['plausible_total']}；IDR（错误补丁带负信号比例）：{_pct(cpr['idr'])}",
        f"- **CPR（正确补丁保留率，correct>0 后首次可定义）：{_pct(cpr['cpr'])}**"
        f"（{cpr['correct_retained']}/{cpr['correct_total']}）——弃权阻断档转正判据 ② 的分母",
        f"- 弃权视角：plausible 拦截面 {_pct(cpr['abstain_plausible_rate'])}；"
        f"passed 压制 {cpr['passed_abstained']}/{cpr['passed_total']}",
        f"- **弃权精确率（修正，非平凡）：{_pct(cpr['abstain_precision'])}**"
        "——阻断档转正判据 ①（历史口径 correct=0 按构造=1.0 无信息量）",
        "",
        "## 4. ADR-0024 归因的 bug_type 分层（解混杂检验）",
        "",
        "谱系 FL 命中与修复成功的负相关是否为缺陷难度混杂——层内检验：",
        "",
        "| bug_type | FL命中(对/总) | P(corr\\|hit) | FL未命中(对/总) | P(corr\\|miss) |",
        "|---|---|---|---|---|",
    ]
    for bug, s in sorted(a["cf_strata"].items(), key=lambda kv: -(kv[1]["hit"] + kv[1]["miss"])):
        p_hit = round(s["hit_correct"] / s["hit"], 4) if s["hit"] else None
        p_miss = round(s["miss_correct"] / s["miss"], 4) if s["miss"] else None
        lines.append(
            f"| {bug} | {s['hit_correct']}/{s['hit']} | {_pct(p_hit)} "
            f"| {s['miss_correct']}/{s['miss']} | {_pct(p_miss)} |"
        )
    lines += [
        "",
        "> 解读：若负相关在多数层内仍成立（P(corr|hit) < P(corr|miss)），",
        "「ADR-0024 的生成侧主导结论非纯难度混杂；若层内消失，则 FL 命中率",
        "本身是难度代理，归因须回到运行时反事实臂。」",
        "",
        "## 5. 四开关转正判据重定建议（**建议非预注册**——正式判据须预注册文档修订）",
        "",
        "修正基线（repair 38.7% 而非 0）下，既有转正判据须重定后才能跑 A/B：",
        "- EDIT_INTENT_ENABLE / DETERMINISTIC_REPAIR_FIRST_ENABLE"
        "（ADR-0018/0019 判据「接管率>0 且 intent/确定性臂 patch_correct 不低于对照」）：",
        "  修正口径下 patch_correct 非平凡——判据结构保留，分母口径改修正 correct；",
        "- 弃权阻断档（ADR-0020）：转正判据 ①② 现有真实分母（本报告 §3），阈值取值待预注册；",
        "- ORACLE_CONTEXT_TIER（ADR-0025）：不受伪影影响（spec_compile_rate 通道未受染），判据原样有效。",
        "",
        "---",
        "*报告生成：experiments/corrected_metrics.py（批次 XIII，ADR-0027）*",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="修正口径重估总报告（ADR-0027，零 LLM）")
    parser.add_argument("results", help="批次 JSON 文件或所在目录")
    parser.add_argument("--arm", default="aitester", help="重估臂名（默认 aitester）")
    parser.add_argument("--out", default=None, help="报告写盘路径（缺省打印到 stdout）")
    parser.add_argument("--timeout", type=int, default=60, help="单行 pytest 超时（秒）")
    args = parser.parse_args(argv)
    report = build_report(args.results, args.arm, timeout=args.timeout)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"修正口径重估报告已写入：{args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
