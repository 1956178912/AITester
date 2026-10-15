"""M4：QuixBugs SpecExpr 扩样确认性实验分析脚本（零 LLM，纯 stdlib）。

背景（EMSE 批次四 M4，预注册 `docs/study/QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md`）：
    QuixBugs specir pilot 阳性趋势 δ=+14.29pp / p=0.125（n=35，标准口径
    6:1），功效不足需扩样确认。本脚本对 4 臂（specir ×2 + nl ×2）的
    JSON 工件做零 LLM 复算：
    - McNemar 配对（specir 臂 vs NL 臂，同 task_id 配对，n = 双方
      detection 非 None 的有效配对子集）；
    - 跨批次方差（C vs D，specir vs NL 的独立 cache namespace 复跑）；
    - 合并分析（A∪C vs B∪D）；
    - 预注册判定规则（p<0.05 ∧ δ≥8pp = confirmed / p<0.10 ∧ δ>0 =
      trend / 其余 = not_confirmed，与 61a7e04 同族）；
    - provenance 校验（4 臂 cache namespace 互异，防缓存命中退化）；
    - 设计敏感性（MDE / 不一致对期望值）。

零 LLM 纪律：只消费已归档 JSON 工件（details 行），不触发任何 LLM 调用；
全部统计量为纯函数（McNemar 精确检验 + Jeffreys 先验贝叶斯因子 + MDE），
与 `experiments/emse_optimization.py` 的统计原语同族。

CLI 三模式（互斥；2026-10-15 批次七修复 C/D 复跑链，此前 orchestrator 的
`--verify-provenance` / `--arm-jsons` 调用均不存在于本 CLI）：
    1. 显式模式：--specir A.json --nl B.json [--specir-repeat C.json --nl-repeat D.json]
    2. 自动映射：--auto-map <4 臂工件...>（按 cache namespace 臂字母 A/B/C/D 映射）
    3. provenance 校验：--verify-provenance <工件...>（namespace 互异，退出码承载结果）
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ─── 预注册常量（与 QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md 一致）──
CONFIRM_P = 0.05
CONFIRM_DELTA_PP = 8.0
TREND_P = 0.10
# 4 臂标签
ARM_SPECIR = "specir"
ARM_NL = "nl"
ARM_SPECIR_REPEAT = "specir_repeat"
ARM_NL_REPEAT = "nl_repeat"


class MissingArtifactError(Exception):
    """4 臂 JSON 工件缺失或结构不完整。"""


# ─── McNemar 精确检验 + 贝叶斯因子（与 emse_optimization.py 统计原语同族）──
def mcnemar_exact_p(b_pos: int, b_neg: int) -> float:
    """McNemar 精确检验（binomial p 值，双侧）。

    b_pos = 仅处理组检出（1→0，specir 检出而 NL 未）；
    b_neg = 仅对照组检出（0→1，NL 检出而 specir 未）；
    p = P(X ≤ min(b_pos, b_neg)) 双侧（二项 n=b_pos+b_neg, p0=0.5）。
    """
    n = b_pos + b_neg
    if n == 0:
        return 1.0
    from math import comb

    k = min(b_pos, b_neg)
    # 双侧精确 p = 2 * Σ_{i=0}^{k} C(n,i) * 0.5^n（截断于 min 对称）
    one_sided = sum(comb(n, i) for i in range(k + 1)) * (0.5**n)
    p = 2.0 * one_sided
    return min(p, 1.0)


def bayes_factor_10(b_pos: int, b_neg: int) -> float:
    """McNemar 二项模型下的贝叶斯因子 BF10（Jeffreys 先验 Beta(0.5,0.5)）。

    模型：不一致对计数 (b_pos, b_neg) 服从二项 Bin(n, θ)，
    θ = 处理组（specir）占不一致对的比例；H0: θ=0.5（无差异） vs
    H1: θ≠0.5（Jeffreys 先验）。

    数值实现：log 域 Beta 函数 + 组合项（防溢出）；
    保守口径：b_pos==b_neg → 1.0（完全对称无证据偏向）；
    返回范围限制 [0.01, 100.0]（极端值截断，防浮点误差放大）。
    """
    if b_pos == b_neg:
        return 1.0
    n = b_pos + b_neg
    if n == 0:
        return 1.0
    from math import comb, lgamma

    def _log_beta(x: float, y: float) -> float:
        return lgamma(x) + lgamma(y) - lgamma(x + y)

    # H1: P(data | Jeffreys prior) = ∫ C(n,b)·θ^b(1-θ)^(n-b)·Beta(θ;0.5,0.5) dθ
    #   = C(n,b) · B(b+0.5, n-b+0.5) / B(0.5, 0.5)
    log_p_h1 = math.log(comb(n, b_pos)) + _log_beta(b_pos + 0.5, b_neg + 0.5) - _log_beta(0.5, 0.5)
    # H0: P(data | θ=0.5) = C(n,b) · 0.5^n
    log_p_h0 = math.log(comb(n, b_pos)) + n * math.log(0.5)
    bf10 = math.exp(log_p_h1 - log_p_h0)
    return max(0.01, min(bf10, 100.0))


def mde_two_proportion(n_pairs: int, power: float = 0.80, alpha: float = 0.05) -> float:
    """两比例（配对）最小可检测效应（MDE，百分点）。

    保守近似：MDE ≈ 1.96 * sqrt(2 * p*(1-p)/n)（双侧 α=0.05 近似），
    取 p=0.5 最保守（p*(1-p) 最大）。
    """
    if n_pairs <= 0:
        return float("inf")
    return round(1.96 * math.sqrt(0.25 / n_pairs) * 100, 2)


# ─── 工件加载 ───────────────────────────────────────────────────────────
def _load_arm_rows(path: Path) -> dict[str, dict[str, Any]]:
    """从批次 JSON 工件提取 task_id → detection_rate 映射。"""
    if not path.exists():
        raise MissingArtifactError(f"工件缺失: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", {})
    aiter = results.get("aitester", {})
    details = aiter.get("details", [])
    if not isinstance(details, list):
        raise MissingArtifactError(f"工件 details 非 list: {path}")
    out: dict[str, dict[str, Any]] = {}
    for row in details:
        tid = row.get("task_id", "")
        out[tid] = {
            "detection_rate": row.get("detection_rate"),
            "spec_replace_applied": row.get("spec_replace_applied"),
            "spec_compile_rate": row.get("spec_compile_rate"),
        }
    return out


def _effective_pair(a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]]) -> tuple[int, int, int]:
    """有效配对子集（双方 detection 非 None）：返回 (b_pos, b_neg, n_pairs)。"""
    common_ids = set(a.keys()) & set(b.keys())
    b_pos = 0  # specir 检出(1) 而 NL 未(0)
    b_neg = 0  # NL 检出(1) 而 specir 未(0)
    n_pairs = 0
    for tid in common_ids:
        det_a = a[tid]["detection_rate"]
        det_b = b[tid]["detection_rate"]
        if det_a is None or det_b is None:
            continue
        n_pairs += 1
        a1, b1 = int(det_a == 1.0), int(det_b == 1.0)
        if a1 and not b1:
            b_pos += 1
        elif b1 and not a1:
            b_neg += 1
    return b_pos, b_neg, n_pairs


def mcnemar_contrast(specir_rows: dict[str, dict[str, Any]], nl_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """McNemar 配对对比（specir 臂 vs NL 臂，标准口径：双方非 None）。"""
    b_pos, b_neg, n_pairs = _effective_pair(specir_rows, nl_rows)
    p = mcnemar_exact_p(b_pos, b_neg)
    delta_pp = (b_pos - b_neg) / n_pairs * 100 if n_pairs else 0.0
    bf10 = bayes_factor_10(b_pos, b_neg)
    mde = mde_two_proportion(n_pairs)
    return {
        "n_pairs": n_pairs,
        "b_pos_specir_only": b_pos,
        "b_neg_nl_only": b_neg,
        "delta_pp": round(delta_pp, 2),
        "p_value": round(p, 4),
        "bf10": round(bf10, 4),
        "mde_pp": mde,
        "ratio": f"{b_pos}:{b_neg}",
    }


# ─── provenance 校验 ────────────────────────────────────────────────────
def verify_provenance(arm_paths: dict[str, Path]) -> dict[str, Any]:
    """校验 4 臂 cache namespace 互异（防缓存命中退化）。

    返回 {"ok": bool, "namespaces": {arm: ns}, "duplicate": [arm...] }。
    """
    namespaces: dict[str, str] = {}
    for arm, path in arm_paths.items():
        if not path.exists():
            namespaces[arm] = "MISSING"
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        prov = data.get("provenance") or data.get("environment") or {}
        ns = prov.get("cache_namespace") or prov.get("aitester_cache") or f"(none:{arm})"
        namespaces[arm] = ns
    seen: dict[str, list[str]] = {}
    for arm, ns in namespaces.items():
        seen.setdefault(ns, []).append(arm)
    duplicates = [ns for ns, arms in seen.items() if len(arms) > 1 and not ns.startswith("(none")]
    return {"ok": len(duplicates) == 0, "namespaces": namespaces, "duplicate": duplicates}


# ─── 工件 → 臂自动映射（C/D 复跑链修复，2026-10-15 批次七）──────────────
# 背景：M4 C/D 复跑编排链此前**整体断裂**——arms 编排器传
# `--verify-provenance <paths>`、batch5 编排器传 `--arm-jsons <paths>`，
# 而本脚本 CLI 只有 `--specir/--nl/...` ⇒ 两者都 argparse 失败 ⇒
# C/D 复跑臂与分析链不可复现（EMSE artifact 复现性缺陷，正是外部
# 审稿人/复现审计会抓的一类问题）。本节补两个 CLI 模式 + 映射助手：
#   --verify-provenance PATHS...：臂级 namespace 互异校验（退出码承载结果）；
#   --auto-map PATHS...：按 namespace 臂字母自动映射后跑完整分析。
# 臂字母判据：namespace 按 "_" 分词后取 ∈ {A,B,C,D} 的段——对
# "emse_qbug_specir_expand_A_20261014" 等形式稳健（日期段/前缀变化不影响）。
_ARM_LETTERS: tuple[str, ...] = ("A", "B", "C", "D")


def extract_cache_namespace(path: Path) -> str:
    """从批次 JSON 工件提取 cache namespace（缺失/损坏返回空串）。"""
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    prov = data.get("provenance") or data.get("environment") or {}
    return str(prov.get("cache_namespace") or prov.get("aitester_cache") or "")


def arm_letter_for_path(path: Path) -> str:
    """工件 → 臂字母（A/B/C/D；无法判定返回空串）。

    刻意不用文件序兜底标签（"file0" 类标签无臂语义，调用方应显式缺臂
    报错而非静默错配）。
    """
    for token in extract_cache_namespace(path).split("_"):
        if token in _ARM_LETTERS:
            return token
    return ""


def map_arm_paths(paths: list[Path]) -> dict[str, Path]:
    """工件列表 → {臂字母: 工件}（同臂多文件取 mtime 最新，防重跑混淆）。"""
    latest: dict[str, tuple[float, Path]] = {}
    for path in paths:
        letter = arm_letter_for_path(path)
        if not letter:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if letter not in latest or mtime > latest[letter][0]:
            latest[letter] = (mtime, path)
    return {letter: pair[1] for letter, pair in latest.items()}


# ─── 判定规则 ───────────────────────────────────────────────────────────
def verdict(contrast: dict[str, Any]) -> str:
    """预注册判定（与 61a7e04 同族）。"""
    p = contrast["p_value"]
    delta = contrast["delta_pp"]
    if p < CONFIRM_P and delta >= CONFIRM_DELTA_PP:
        return "confirmed"
    if p < TREND_P and delta > 0:
        return "trend"
    return "not_confirmed"


# ─── 主分析 ─────────────────────────────────────────────────────────────
def build_analysis(
    specir_path: Path,
    nl_path: Path,
    specir_repeat_path: Path | None = None,
    nl_repeat_path: Path | None = None,
) -> dict[str, Any]:
    """4 臂（或 2 臂）主分析。"""
    specir_rows = _load_arm_rows(specir_path)
    nl_rows = _load_arm_rows(nl_path)
    analysis: dict[str, Any] = {
        "primary": mcnemar_contrast(specir_rows, nl_rows),
        "verdict": verdict(mcnemar_contrast(specir_rows, nl_rows)),
    }
    if specir_repeat_path and nl_repeat_path:
        specir_rep_rows = _load_arm_rows(specir_repeat_path)
        nl_rep_rows = _load_arm_rows(nl_repeat_path)
        repeat_contrast = mcnemar_contrast(specir_rep_rows, nl_rep_rows)
        analysis["repeat"] = repeat_contrast
        # 合并（A∪C vs B∪D）：两侧复跑样本须使用**同一后缀**，`_effective_pair`
        # 的键交集才能同时命中 A↔B 与 C↔D 两组配对（n≤2×任务数）。
        # 2026-10-15 批次八修复：原实现 specir 侧后缀 `_c`、NL 侧后缀 `_d`，
        # 两侧后缀不同 ⇒ `{task}_c` 与 `{task}_d` 永不进入交集 ⇒ C/D 配对
        # 静默缺失，merged 逐位退化为 primary（C/D 白跑；预注册主分析之一
        # 失真）。修复后 merged n_pairs = A/B 有效对 + C/D 有效对。
        merged_specir = {**specir_rows, **{f"{k}_rep": v for k, v in specir_rep_rows.items()}}
        merged_nl = {**nl_rows, **{f"{k}_rep": v for k, v in nl_rep_rows.items()}}
        merged_contrast = mcnemar_contrast(merged_specir, merged_nl)
        analysis["merged"] = merged_contrast
        analysis["merged_verdict"] = verdict(merged_contrast)
    return analysis


def main(argv: list[str] | None = None) -> int:
    """CLI 三模式（互斥）：显式四臂 / --auto-map 自动映射 / --verify-provenance。

    显式模式（--specir + --nl，历史口径不变）与两种自动模式可复现 C/D
    复跑链（2026-10-15 修复，见 map_arm_paths 注释）。
    """
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--specir", default=None, help="specir 臂 JSON 工件（显式模式，与 --nl 配对）")
    ap.add_argument("--nl", default=None, help="NL 臂 JSON 工件（显式模式，与 --specir 配对）")
    ap.add_argument("--specir-repeat", default=None, help="specir 复跑臂 JSON（可选）")
    ap.add_argument("--nl-repeat", default=None, help="NL 复跑臂 JSON（可选）")
    ap.add_argument(
        "--auto-map",
        nargs="+",
        default=None,
        metavar="JSON",
        help="按 cache namespace 臂字母自动映射后分析（A=specir/B=NL/C/D=复跑）",
    )
    ap.add_argument(
        "--verify-provenance",
        nargs="+",
        default=None,
        metavar="JSON",
        help="校验各工件 cache namespace 互异（防跨臂缓存命中退化），退出码承载结果",
    )
    ap.add_argument("--out", default=None, help="结果落盘路径（JSON）")
    args = ap.parse_args(argv)

    modes = [bool(args.auto_map), bool(args.verify_provenance), bool(args.specir or args.nl)]
    if sum(modes) != 1:
        ap.error("三模式互斥且必选其一：--specir/--nl（显式）| --auto-map | --verify-provenance")

    # 模式 1：provenance 校验（C/D 复跑链的前置门）
    if args.verify_provenance:
        arm_paths = map_arm_paths([Path(p) for p in args.verify_provenance])
        if not arm_paths:
            print("[emse_quixbugs_specir_expand] ✗ 无工件可判定臂字母（namespace 缺 A/B/C/D 段）")
            return 1
        result = verify_provenance(arm_paths)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["ok"]:
            print(f"[emse_quixbugs_specir_expand] ✗ namespace 重复：{result['duplicate']}")
            return 1
        print(f"[emse_quixbugs_specir_expand] ✓ {len(arm_paths)} 臂 namespace 互异校验通过")
        return 0

    # 模式 2/3：分析（自动映射 or 显式）
    if args.auto_map:
        arm_paths = map_arm_paths([Path(p) for p in args.auto_map])
        missing_primary = [letter for letter in ("A", "B") if letter not in arm_paths]
        if missing_primary:
            print(f"[emse_quixbugs_specir_expand] ✗ 主分析臂缺失：{missing_primary}（A=specir/B=NL 必需）")
            return 1
        result = build_analysis(
            arm_paths["A"],
            arm_paths["B"],
            arm_paths.get("C"),
            arm_paths.get("D"),
        )
        arms_found = sorted(arm_paths)
        print(f"[emse_quixbugs_specir_expand] 自动映射臂：{arms_found}")
    else:
        result = build_analysis(
            Path(args.specir),
            Path(args.nl),
            Path(args.specir_repeat) if args.specir_repeat else None,
            Path(args.nl_repeat) if args.nl_repeat else None,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[emse_quixbugs_specir_expand] 结果已落盘 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
