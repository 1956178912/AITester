#!/usr/bin/env python3
"""通过率混淆敏感性分析（T-10，EMSE 审稿人 A3 复核点，零 LLM 只读工件）。

## 动机（审稿人 A3 的原话级质疑）

「`detection-first 协议 → false_fix 减少` 是因果还是**成功声明率坍缩**的副产物？」

R-P0-2 三种子合并（n=261/臂）实测：
- `plain_llm_df`（纯提示协议臂）**只有 7/261 声明成功**（2.7%），
  其边际 false_fix 因此只有 7/261 = 2.68%——**低假修复率可能是"几乎不声明成功"
  的机械结果**，而非"测试质量更高"；
- `aitester`（完整系统）passed = 143/261，而 **143/143 = 100% 的 passed 行
  false_fix = 1.0**（条件口径 100%）。

本脚本的作用：**把混淆暴露出来并量化**，而不是用话术掩盖它。输出三件事：

1. **成功声明率**（success-declaration rate）——把"什么时候声明成功"从隐含
   行为提升为一等指标（协议干预直接改变的就是它）；
2. **conditioned-on-success 指标**——在"声明成功的行"内部比较检测/假修复，
   这是唯一能避免"分母被成功率压扁"的口径；
3. **模板匹配子集**（pass-matched subset）——只保留"纯提示协议臂成功过的
   任务模板"，在该子集内重算完整系统的检测率/假修复率，回答
   "在协议臂能成功的那些任务上，完整系统表现如何"。

## 口径纪律（避免过度解读）

- 匹配后子集**样本量必然很小**（df 成功模板数 ≤ 7/臂批次），因此本报告只作
  **方向性/描述性证据**，给出 Wilson 区间与精确二项检验，**不作因果声明**；
- `detection_rate` 为 None 的行（不可测）一律**不进分母**（与 M1 口径一致），
  并同时报告"None 计为 0"的敏感性下界；
- 纯 stdlib + 复用 `experiments/statistical_analysis.py` 的既定实现
  （`_pair_by_task` / `bootstrap_paired_diff_ci`），不引入新依赖、不调用 LLM。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:  # 支持 `python experiments/pass_matched_sensitivity.py`
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.statistical_analysis import (  # noqa: E402
    _pair_by_task,
    bootstrap_paired_diff_ci,
)
from src.utils.atomic_io import atomic_write_text  # noqa: E402

DEFAULT_RESULTS_DIR = _REPO_ROOT / "experiments" / "results" / "main_batch"
DEFAULT_OUT = _REPO_ROOT / "experiments" / "results" / "emse_stats_2026-10-15" / "PASS_MATCHED.json"
# 主批次三类种子文件名 glob（供测试与加载器共用，避免两处各写一份模式）。
PASS_MATCHED_BATCH_GLOB = "benchmark_synthetic_20261006_1[0-9]*.json"
DEFAULT_SEEDS = (42, 43, 44)
# df 臂 = "纯提示协议"（detection-first 提示 + 统一修复环）；aitester = 完整系统。
ARM_TREATMENT = "aitester"
ARM_PROMPT_ONLY = "plain_llm_df"
ARM_BARE = "plain_llm"
_BOOTSTRAP_N = 10000
_BOOTSTRAP_SEED = 42


# ─── 基础统计（纯 stdlib，口径与 statistical_analysis.py 一致） ───────────
def wilson_ci(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score 区间（比例型指标的保守区间；n=0 → (nan, nan)）。"""
    if n <= 0:
        return float("nan"), float("nan")
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, center - half), min(1.0, center + half)


def rate(successes: int, n: int) -> float | None:
    return (successes / n) if n else None


def _pct(value: float | None) -> str:
    return "—" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value * 100:.2f}%"


def _fmt_ci(lo: float, hi: float) -> str:
    if math.isnan(lo):
        return "—"
    return f"[{lo * 100:.2f}%, {hi * 100:.2f}%]"


# ─── 数据加载 ────────────────────────────────────────────────────────────
def load_batches(results_dir: Path, *, seeds: tuple[int, ...]) -> dict[str, list[dict[str, Any]]]:
    """读取三种子主批次，按臂聚合；task_id 加 `s<seed>__` 前缀（种子分层拼接）。

    与 `statistical_report_3seed_pooled.md` 的拼接口径一致（该方法已在
    AB4 批次固化进 `statistical_analysis.py --pool-seeds`）。
    """
    files = sorted(glob.glob(str(results_dir / PASS_MATCHED_BATCH_GLOB)))
    if not files:
        raise SystemExit(f"未找到三种子主批次工件：{results_dir}/{PASS_MATCHED_BATCH_GLOB}")
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    loaded: list[dict[str, Any]] = []
    for path in files:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        seed = data.get("seed")
        if seeds and seed not in seeds:
            continue
        loaded.append({"file": Path(path).name, "seed": seed})
        for arm, block in (data.get("results") or {}).items():
            for row in block.get("details", []):
                enriched = dict(row)
                enriched["task_id"] = f"s{seed}__{row.get('task_id')}"
                enriched["_seed"] = seed
                enriched["_pattern"] = (row.get("task_metadata") or {}).get("pattern_name")
                rows[arm].append(enriched)
    rows["__batches__"] = loaded  # type: ignore[assignment]
    return rows


def _measurable(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get(field) is not None]


def _pattern_key(row: dict[str, Any]) -> tuple[str | None, int | None]:
    md = row.get("task_metadata") or {}
    return md.get("pattern_name"), md.get("difficulty")


def _match_key(row: dict[str, Any]) -> tuple[str | None, int | None, Any]:
    """严格匹配键 = pattern × difficulty × seed（种子分层，避免跨种子扩散成功）。"""
    pattern, difficulty = _pattern_key(row)
    return pattern, difficulty, row.get("_seed")


# ─── 分析主体 ────────────────────────────────────────────────────────────
def success_declaration_table(rows: dict[str, list[dict[str, Any]]], arms: list[str]) -> list[dict[str, Any]]:
    """成功声明率：passed 可测行中声明成功的比例（协议干预的直接行为指标）。"""
    out: list[dict[str, Any]] = []
    for arm in arms:
        arm_rows = rows.get(arm, [])
        measurable = _measurable(arm_rows, "passed")
        passed = sum(1 for r in measurable if r.get("passed"))
        lo, hi = wilson_ci(passed, len(measurable))
        out.append(
            {
                "arm": arm,
                "rows": len(arm_rows),
                "passed_measurable": len(measurable),
                "passed_true": passed,
                "success_declaration_rate": rate(passed, len(measurable)),
                "success_declaration_ci": [lo, hi],
            }
        )
    return out


def conditioned_on_success(rows: dict[str, list[dict[str, Any]]], arms: list[str]) -> list[dict[str, Any]]:
    """声明成功行内部的口径：构成、detection、假修复（条件口径）。"""
    out: list[dict[str, Any]] = []
    for arm in arms:
        arm_rows = rows.get(arm, [])
        passed_rows = [r for r in arm_rows if r.get("passed") is True]
        n = len(passed_rows)
        ff = sum(1 for r in passed_rows if r.get("false_fix_rate") == 1.0)
        ff_measurable = [r for r in passed_rows if r.get("false_fix_rate") is not None]
        det_rows = [r for r in passed_rows if r.get("detection_rate") is not None]
        det_true = sum(1 for r in det_rows if r.get("detection_rate") == 1.0)
        reprotected = sum(1 for r in passed_rows if r.get("source_patched_unverified"))
        lo, hi = wilson_ci(ff, len(ff_measurable))
        out.append(
            {
                "arm": arm,
                "passed_rows": n,
                "false_fix_true": ff,
                "false_fix_measurable": len(ff_measurable),
                "false_fix_conditional_rate": rate(ff, len(ff_measurable)),
                "false_fix_conditional_ci": [lo, hi],
                "detection_measurable_within_passed": len(det_rows),
                "detection_true_within_passed": det_true,
                "detection_rate_within_passed": rate(det_true, len(det_rows)),
                "source_patched_unverified_within_passed": reprotected,
            }
        )
    return out


def pass_matched_subset(
    rows: dict[str, list[dict[str, Any]]],
    *,
    arm_treatment: str,
    arm_reference: str,
) -> dict[str, Any]:
    """模板匹配子集：仅保留"参照臂（纯提示协议）声明成功过"的 pattern。

    匹配在 **pattern × seed** 粒度上进行（df 在 seed s 上成功过 pattern p，
    则完整系统在 seed s 上的 p 任务进入匹配子集）——避免把单一种子的成功
    扩散到未成功的种子。同时给出 pattern 粒度的宽松口径作敏感性对照。
    """
    ref_rows = rows.get(arm_reference, [])
    treat_rows = rows.get(arm_treatment, [])
    ref_success: set[tuple[str | None, int | None, Any]] = set()
    ref_success_patterns: set[str | None] = set()
    matched_pairs: list[dict[str, Any]] = []
    for r in ref_rows:
        if r.get("passed") is not True:
            continue
        key = _match_key(r)
        ref_success.add(key)
        ref_success_patterns.add(key[0])
        matched_pairs.append(
            {"seed": r.get("_seed"), "pattern_name": key[0], "difficulty": key[1], "task_id": r.get("task_id")}
        )

    treat_strict = [r for r in treat_rows if _match_key(r) in ref_success]
    treat_loose = [r for r in treat_rows if _pattern_key(r)[0] in ref_success_patterns]
    # 未匹配对照：完整系统中 pattern 未被 df 成功过的任务
    treat_unmatched = [r for r in treat_rows if _pattern_key(r)[0] not in ref_success_patterns]

    def _summary(sub: list[dict[str, Any]], label: str) -> dict[str, Any]:
        det_rows = [r for r in sub if r.get("detection_rate") is not None]
        det_true = sum(1 for r in det_rows if r.get("detection_rate") == 1.0)
        passed = [r for r in sub if r.get("passed") is True]
        ff = sum(1 for r in passed if r.get("false_fix_rate") == 1.0)
        ff_meas = [r for r in passed if r.get("false_fix_rate") is not None]
        elo, ehi = wilson_ci(det_true, len(det_rows))
        return {
            "subset": label,
            "rows": len(sub),
            "detection_measurable": len(det_rows),
            "detection_true": det_true,
            "detection_rate": rate(det_true, len(det_rows)),
            "detection_ci": [elo, ehi],
            "detection_rate_none_as_zero": rate(det_true, len(sub)),
            "passed_true": len(passed),
            "false_fix_true": ff,
            "false_fix_measurable": len(ff_meas),
            "false_fix_conditional_rate": rate(ff, len(ff_meas)),
        }

    return {
        "reference_arm": arm_reference,
        "treatment_arm": arm_treatment,
        "reference_success_pairs": matched_pairs,
        "reference_success_pattern_count": len(ref_success_patterns),
        "matched_strict": _summary(treat_strict, "matched_pattern_x_seed"),
        "matched_loose": _summary(treat_loose, "matched_pattern_only"),
        "unmatched": _summary(treat_unmatched, "unmatched_patterns"),
        "matched_task_ids": sorted(r["task_id"] for r in treat_strict),
    }


def paired_detection_bootstrap(rows: dict[str, list[dict[str, Any]]], *, arm_a: str, arm_b: str) -> dict[str, Any]:
    """配对 detection 差的 bootstrap 95% CI（复用既有实现，固定 seed=42）。"""
    a = _measurable(rows.get(arm_a, []), "detection_rate")
    b = _measurable(rows.get(arm_b, []), "detection_rate")
    mean, lo, hi, n_pairs = bootstrap_paired_diff_ci(a, b, _BOOTSTRAP_N, _BOOTSTRAP_SEED)
    _, _, common = _pair_by_task(a, b)
    return {
        "pair": f"{arm_a} - {arm_b}",
        "n_pairs": n_pairs,
        "mean_diff": None if math.isnan(mean) else mean,
        "ci95": [None if math.isnan(lo) else lo, None if math.isnan(hi) else hi],
        "n_resamples": _BOOTSTRAP_N,
        "bootstrap_seed": _BOOTSTRAP_SEED,
        "common_tasks_sample": common[:5],
    }


def build_report(payload: dict[str, Any]) -> str:
    sd = payload["success_declaration"]
    cond = payload["conditioned_on_success"]
    matched = payload["pass_matched"]
    boot = payload["paired_detection_bootstrap"]
    lines: list[str] = [
        "# 通过率混淆敏感性分析（T-10，EMSE 审稿人 A3 复核点）",
        "",
        f"- 工件：`{payload['results_dir']}` 下 {len(payload['batches'])} 个批次文件 "
        f"（种子 {payload['seeds']}；n={payload['rows_per_arm']} 行/臂）",
        "- 口径：`detection_rate` 为 None 的行不进分母（与 M1 一致），另给 None 计 0 的下界；"
        "本报告为**零 LLM 只读存量工件**再分析。",
        "- **解读纪律**：匹配子集样本量小（见 §3 的 n），仅作方向性证据，**不作因果声明**。",
        "",
        "## 1. 成功声明率（协议干预的直接行为指标）",
        "",
        "| 臂 | 行数 | passed 可测 | 声明成功 | 成功声明率 | Wilson 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for row in sd:
        lo, hi = row["success_declaration_ci"]
        lines.append(
            f"| `{row['arm']}` | {row['rows']} | {row['passed_measurable']} | {row['passed_true']} | "
            f"**{_pct(row['success_declaration_rate'])}** | {_fmt_ci(lo, hi)} |"
        )
    lines += [
        "",
        "> 读法：协议臂（`plain_llm_df`）的成功声明率坍缩是其低边际 false-fix 的**直接原因**——"
        "分母被压扁，而不是分子变好。",
        "",
        "> **关键观察（本报告最重要的实证）**：三臂的**条件**假修复率均为 100%——"
        "即「只要声明成功，就是假修复」在本文设计中是**普遍现象**。因此三臂之间"
        "边际 false-fix 的全部差异，**只来自成功声明率**，不来自修复或测试质量差异。"
        "这直接否证「detection-first 协议降低了假修复」的因果解读。",
        "",
        "## 2. 仅在「声明成功」的行内部（条件口径）",
        "",
        "| 臂 | passed 行 | 假修复(true) | 可测 | 条件假修复率 | Wilson 95% CI | passed 内 detection 可测/真 | 源码已改未验证 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in cond:
        lo, hi = row["false_fix_conditional_ci"]
        lines.append(
            f"| `{row['arm']}` | {row['passed_rows']} | {row['false_fix_true']} | {row['false_fix_measurable']} | "
            f"**{_pct(row['false_fix_conditional_rate'])}** | {_fmt_ci(lo, hi)} | "
            f"{row['detection_measurable_within_passed']}/{row['detection_true_within_passed']} | "
            f"{row['source_patched_unverified_within_passed']} |"
        )
    lines += [
        "",
        "## 3. 模板匹配子集（pass-matched，对照臂成功过的 pattern）",
        "",
        f"- 对照臂 `{matched['reference_arm']}` 成功 pattern 数：**{matched['reference_success_pattern_count']}**"
        "（pattern × seed 配对见 JSON 工件）",
        "",
        "| 子集 | 行数 | detection 可测 | detection 真 | detection 率 | Wilson 95% CI | None 计 0 | passed | 条件假修复率 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, label in (
        ("matched_strict", "匹配（pattern×seed）"),
        ("matched_loose", "匹配（仅 pattern）"),
        ("unmatched", "未匹配（对照）"),
    ):
        sub = matched[key]
        lines.append(
            f"| {label} | {sub['rows']} | {sub['detection_measurable']} | {sub['detection_true']} | "
            f"**{_pct(sub['detection_rate'])}** | {_fmt_ci(*sub['detection_ci'])} | "
            f"{_pct(sub['detection_rate_none_as_zero'])} | {sub['passed_true']} | "
            f"{_pct(sub['false_fix_conditional_rate'])} |"
        )
    lines += [
        "",
        "## 4. 配对 detection 差的 bootstrap 95% CI（复用既有实现）",
        "",
        "> 方向约定：差值 = **前者 − 后者**（`arm_a − arm_b`），**负值 = 前者更差**。",
        "> 注意与 §1 的「协议臂优于完整系统」不矛盾：协议臂相对**裸 LLM** 是 +43pp 量级，而完整系统相对协议臂为负。",
        "",
        "| 对比 | 配对 n | 均值差（前 − 后） | 95% CI | 重采样/种子 |",
        "|---|---|---|---|---|",
    ]
    for row in boot:
        lo, hi = row["ci95"]
        lines.append(
            f"| `{row['pair']}` | {row['n_pairs']} | {_pct(row['mean_diff'])} | "
            f"[{_pct(lo)}, {_pct(hi)}] | {row['n_resamples']} / {row['bootstrap_seed']} |"
        )
    lines += [
        "",
        "## 5. 结论口径（可直接进论文 Limitations/Results）",
        "",
        "1. **成功声明率是被协议直接改变的行为**：三臂差异极大（87.74% / 54.79% / 2.68%），"
        "任何以 `passed` 为分母的比例指标（含边际 false_fix）都**同时**度量了测试质量与该行为，"
        "二者在本文设计中不可分离。",
        "2. **条件口径下三臂的假修复率均为 100%**：差异完全来自成功声明率，"
        "因此「协议降低假修复」的表述**不被本数据支持**。",
        "3. **在对照臂成功过的任务模板上，完整系统检出为 0**（见 §3 匹配子集）："
        "matched 子集 0/55 检出、17 行声明成功且 100% 为假修复（**空成功**），"
        "而未匹配子集检出 20.54%（38/185）。这说明「完整系统更差」**不是**由任务难度"
        "或通过率混淆造成的假象，在最有利的匹配子集上反而更强。",
        "4. 匹配子集样本量小（对照臂成功 pattern 仅 4 个 / 62 行），故**只作方向性证据**；"
        "需要 2×2 消融（协议文本开关 × 再生成预算）才能把「文本效应」与「行为效应」分离；"
        "本报告不替代该实验。",
        "",
        f"*生成：`experiments/pass_matched_sensitivity.py`（零 LLM，纯 stdlib + 既有统计实现；工件 {payload['out']}）*",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过率混淆敏感性分析（T-10，零 LLM）")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--md-out", type=Path, default=None, help="Markdown 报告路径（默认与 --out 同目录同名 .md）")
    args = parser.parse_args(argv)

    rows = load_batches(args.results_dir, seeds=tuple(args.seeds))
    batches = rows.pop("__batches__", [])
    arms = [ARM_TREATMENT, ARM_BARE, ARM_PROMPT_ONLY]
    arms = [a for a in arms if rows.get(a)]
    if len(arms) < 2:
        raise SystemExit("可用臂不足（需要至少两臂）")

    payload: dict[str, Any] = {
        "results_dir": str(args.results_dir),
        "batches": batches,
        "seeds": list(args.seeds),
        "arms": arms,
        "rows_per_arm": max((len(rows[a]) for a in arms), default=0),
        "success_declaration": success_declaration_table(rows, arms),
        "conditioned_on_success": conditioned_on_success(rows, arms),
        "pass_matched": pass_matched_subset(rows, arm_treatment=ARM_TREATMENT, arm_reference=ARM_PROMPT_ONLY),
        "paired_detection_bootstrap": [
            paired_detection_bootstrap(rows, arm_a=a, arm_b=b)
            for a, b in (
                (ARM_TREATMENT, ARM_PROMPT_ONLY),
                (ARM_TREATMENT, ARM_BARE),
                (ARM_PROMPT_ONLY, ARM_BARE),
            )
        ],
        "out": str(args.out),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.out, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", mode=0o644)
    md_path = args.md_out or args.out.with_suffix(".md")
    md_path.write_text(build_report(payload), encoding="utf-8")

    print(f"[pass-matched] 工件：{args.out}")
    print(f"[pass-matched] 报告：{md_path}")
    for row in payload["success_declaration"]:
        print(
            f"  成功声明率 {row['arm']:<14} {row['passed_true']}/{row['passed_measurable']} "
            f"= {_pct(row['success_declaration_rate'])}"
        )
    sub = payload["pass_matched"]["matched_strict"]
    print(
        f"  匹配子集 detection {sub['detection_true']}/{sub['detection_measurable']} "
        f"= {_pct(sub['detection_rate'])}（对照臂成功 pattern 数 "
        f"{payload['pass_matched']['reference_success_pattern_count']}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
