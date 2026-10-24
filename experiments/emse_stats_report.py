"""EMSE 统计报告补口：主对比的 MDE/功效 + 比例型端点 bootstrap 95% CI（2026-10-15 批次）。

背景（EMSE 投稿量化审查提出的两处报告缺口）：
    (a) 主对比只报点估计与 p 值，**未报最小可检测效应（MDE）与功效**——读者无法
        区分"不显著 = 无效应"与"不显著 = 样本量注定检不出"；
    (b) repair / false_fix 等**比例型端点只有点估计、没有不确定区间**。

本工具在**不改动任何既有报告**的前提下补齐上述两项：零 LLM、零网络，只读已归档
批次 JSON（默认路径不触发任何子进程；`--corrected-repair` 才会跑本地 pytest 重放），
只向 `--out` 目录写报告与 JSON；全部数字现算——报告中不出现任何硬编码的定案统计量。

口径（与报告头部 `## 0. 口径` 逐条对应，二者同源）：
    - 主数据 = R-P0-2 三种子合并（`benchmark_synthetic_20261006_*.json`，seed 42/43/44）；
      行 `task_id` 加 `s<seed>__` 前缀后池化——与 `statistical_analysis.py --pool-seeds`
      的多种子拼接口径一致（否则跨种子同名 task_id 会被最新批次优先去重折叠成单种子）；
    - MDE（σ_d² 口径，主口径）= 项目既有配对比例正态近似的**闭式反演**：
      σ_d² = p_a + p_b − δ² − 2·p11、MDE = (z_{1−α/2} + z_power)·√(σ_d²/n)
      （源：`scripts/tools/power_analysis.py` 的 n_required 公式；该模块只提供
      二分变体 `detectable_delta_paired`，其 σ_d² 随候选 δ 变动，见 §1 口径说明）；
    - MDE（ψ/4 口径，交叉核对）= `experiments/emse_optimization.mde_paired_pp`
      （10-13 定案公式，未乘 (1−ψ) 项）；
    - 功效 = `power_analysis.power_paired`（σ_d² 口径）与
      `emse_optimization.power_at_delta`（ψ 口径）并列；
    - 比例型端点 95% CI = `statistical_analysis.bootstrap_paired_diff_ci`
      （配对差值均值，百分位法，10000 次重采样，seed=42，order-statistic 分位）；
    - 缺失值 = M1 诚实口径：端点字段为 None 的行**剔除**（不计 0、不进分母），
      配对要求两侧该字段均可测。

用法：
    .venv/bin/python -m experiments.emse_stats_report
    .venv/bin/python -m experiments.emse_stats_report --results-dir DIR --out DIR \\
        --batches a.json,b.json [--corrected-repair]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

# 项目根加入 sys.path（脚本可经 `python -m experiments.emse_stats_report`
# 或测试导入两种方式运行；与 experiments/emse_optimization.py 同口径）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 既有统计原语（全部复用，不另起副本）：
# - σ_d² 口径：配对比例正态近似（power_analysis）
# - ψ/4 口径：10-13 定案 MDE/功效（emse_optimization）
# - 比例型端点 CI：配对 bootstrap（statistical_analysis）
from experiments.emse_optimization import (  # noqa: E402
    mde_paired_pp,
    paired_contrast,
    power_at_delta,
)
from experiments.statistical_analysis import (  # noqa: E402
    bootstrap_paired_diff_ci,
    token_accounting_sanity,
)
from scripts.tools.power_analysis import (  # noqa: E402
    detectable_delta_paired,
    power_paired,
    required_n_paired,
)
from src.budget.pricing import entry_block_reason, load_table_json, models_layer  # noqa: E402

# AJ（2026-10-21）：缓存口径读取的唯一事实源（与 statistical_analysis / ext 共享）。
# AL（2026-10-21）：行级 token 三元组读取与 §4.1 共用同一份值域判定。
from src.budget.token_usage import (  # noqa: E402
    by_model_reason,
    cache_caliber,
    cache_totals,
    row_token_counts,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# ─── 口径常量（默认值 = 预注册 R-P0-2 三种子合并口径） ────────────────────
_DEFAULT_RESULTS_DIR = _REPO_ROOT / "experiments" / "results" / "main_batch"
_DEFAULT_OUT_DIR = _REPO_ROOT / "experiments" / "results" / "emse_stats_2026-10-15"
# 三主要对比的批次文件（R-P0-2 生死实验：synthetic n=87 × seed{42,43,44}）
_RP02_DEFAULT_BATCHES: tuple[str, ...] = (
    "benchmark_synthetic_20261006_140906.json",
    "benchmark_synthetic_20261006_151907.json",
    "benchmark_synthetic_20261006_164357.json",
)
# 三臂（检出优先协议归因基线 X1：aitester / plain_llm / plain_llm_df）
_ARMS: tuple[str, ...] = ("aitester", "plain_llm", "plain_llm_df")
# 三组主要配对（前臂 − 后臂；与 statistical_report_3seed_pooled.md 同序）
_PRIMARY_PAIRS: tuple[tuple[str, str], ...] = (
    ("aitester", "plain_llm"),
    ("aitester", "plain_llm_df"),
    ("plain_llm_df", "plain_llm"),
)
# 主端点 = detection_rate（F2P 检出，gold 独立裁决）；比例型端点的 CI 亦覆盖
# repair_rate 与 false_fix_rate 的边际/条件两口径
_PRIMARY_FIELD = "detection_rate"
_ALPHA = 0.05
_POWER = 0.8
_BOOTSTRAP_N_RESAMPLES = 10000
_BOOTSTRAP_SEED = 42
_NORM = NormalDist()

# 比例型端点（标签, 行字段, 是否限制 passed=True）
_ENDPOINTS: tuple[tuple[str, str, bool], ...] = (
    ("detection_rate（边际）", "detection_rate", False),
    ("repair_rate（边际）", "repair_rate", False),
    ("false_fix_rate（边际）", "false_fix_rate", False),
    ("false_fix_rate（条件：passed=True）", "false_fix_rate", True),
)


# ─── 闭式原语（源：scripts/tools/power_analysis.py 的 n_required 公式） ────
def mde_sigma_closed_form_pp(
    n_pairs: int,
    sigma_d2: float,
    alpha: float = _ALPHA,
    power: float = _POWER,
) -> float | None:
    """σ_d² 口径 MDE（百分点）：闭式反演 `n_required = (z_{1−α/2}+z_power)²·σ_d²/δ²`。

    源公式与 `scripts/tools/power_analysis.py` 模块 docstring 逐字一致；该模块
    只暴露**二分变体** `detectable_delta_paired`（其 σ_d² 随候选 δ 重新求值），
    本函数实为同一公式在**观测不一致结构固定**（σ_d² = p_a+p_b−δ²−2·p11 取观测值）
    下的直接反演——这正是"给定该 n 与该不一致结构"的最小可检测效应。

    n_pairs ≤ 0 或 σ_d² ≤ 0（无不一致结构）→ None（不臆造数字）。
    """
    if n_pairs <= 0 or sigma_d2 <= 0:
        return None
    z_crit = _NORM.inv_cdf(1.0 - alpha / 2.0)
    z_power = _NORM.inv_cdf(power)
    return 100.0 * (z_crit + z_power) * math.sqrt(sigma_d2 / n_pairs)


def sigma_d2_paired(p_a: float, p_b: float, p11: float) -> float:
    """配对差 δ = p_a − p_b 的单任务方差 σ_d² = p_a + p_b − δ² − 2·p11。

    与 `scripts/tools/power_analysis._var_paired_diff` 同式（该函数为模块私有，
    此处按同一公式现算并在报告中标注出处；数值一致性由 tests 锁定）。
    """
    delta = p_a - p_b
    return p_a + p_b - delta * delta - 2.0 * p11


# ─── Wilson score 区间（比例型端点单臂 CI；A-07 2026-10-17）────────────────
# 审稿人常规要求：小样本比例（如 17/37、19/35）必须给 CI。配对差已有 bootstrap
# （§3），单臂点估计此前无区间——此处补 Wilson score 区间（小样本覆盖率优于
# Wald 正态近似；n=0 或比例在边界时行为良定义）。z=1.959963984540054 为
# NormalDist().inv_cdf(0.975)，与模块 _NORM 同源避免双实现。
_Z95 = _NORM.inv_cdf(0.975)


def wilson_ci(k: int, n: int, z: float = _Z95) -> tuple[float, float] | None:
    """比例的 Wilson score 95% 区间（返回 (lo, hi) 百分比；n=0 → None）。

    不臆造区间：n=0 时 None（与全模块"不可计算记 None 不记 0"纪律一致）。
    """
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5) / denom
    return (100.0 * max(0.0, center - half), 100.0 * min(1.0, center + half))


# ─── 工件加载（只读；种子前缀池化） ───────────────────────────────────────
def _sha256(path: Path) -> str:
    """批次工件 sha256（审计用，报告头部登记）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_batch_files(results_dir: Path, batches: str | None) -> list[Path]:
    """批次文件清单：`--batches`（逗号分隔，相对 results-dir）或 R-P0-2 默认三批次。

    缺文件**不静默降级**（少数一个批次会改变全部数字）：由调用方判定为口径错误。
    """
    names = [p.strip() for p in (batches or "").split(",") if p.strip()]
    if not names:
        names = list(_RP02_DEFAULT_BATCHES)
    files: list[Path] = []
    for name in names:
        raw = Path(name)
        files.append(raw if raw.is_absolute() else results_dir / name)
    return files


def load_pooled_rows(
    results_dir: Path,
    batch_files: list[Path],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """读取批次 JSON 并做**种子前缀池化**（`s<seed>__<task_id>`），返回 (行, 批次元数据)。

    行按臂聚合（`results[arm].details[]`）；seed 取 `provenance.seed`，缺失时回退
    顶层 `seed`，再缺失回退文件名 stem——与 `statistical_analysis._load_batch_file`
    的 fallback 同序（口径可追溯）。
    """
    rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in _ARMS}
    meta: list[dict[str, Any]] = []
    for path in batch_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        provenance = data.get("provenance") or {}
        seed = provenance.get("seed", data.get("seed"))
        prefix = f"s{seed}__" if seed is not None else f"{path.stem}__"
        results = data.get("results") or {}
        per_arm: dict[str, int] = {}
        for arm in _ARMS:
            details = (results.get(arm) or {}).get("details") or []
            kept = [r for r in details if isinstance(r, dict)]
            per_arm[arm] = len(kept)
            rows[arm].extend({**r, "task_id": f"{prefix}{r.get('task_id', '')}"} for r in kept)
        meta.append(
            {
                "file": path.name,
                "seed": seed,
                "prefix": prefix,
                "sha256": _sha256(path),
                "n_rows_per_arm": per_arm,
                "extra_arms": sorted(set(results) - set(_ARMS)),
            }
        )
    return rows, meta


# ─── 端点聚合（None 剔除，不进分母） ─────────────────────────────────────
def endpoint_point(rows: list[dict[str, Any]], field: str, restrict_passed: bool = False) -> dict[str, Any]:
    """单臂端点点估计（分子/分母/百分点）。

    None 口径（M1 诚实指标）：`field` 为 None 的行**剔除**（既不计入分子也不计入
    分母，绝不记 0）；`restrict_passed=True` 时再限制 `passed is True`（条件口径）。

    分母定义 = **被度量指标本身可测的行**（`field is not None`）——与
    `emse_optimization.false_fix_caliber` 的 2026-10-15 修复口径一致，亦与
    R-P0-2 定案边际 59.58%（143/240，而非 143/261）同分母；R-P0-2 实测两口径
    在 false_fix 上数值相同（21 行 `detection_rate`/`false_fix_rate` 同时为 None）。
    """
    denom = [r for r in rows if r.get(field) is not None and (not restrict_passed or r.get("passed") is True)]
    numer = [r for r in denom if r.get(field) == 1.0]
    n = len(denom)
    ci = wilson_ci(len(numer), n)
    return {
        "field": field,
        "restrict_passed": restrict_passed,
        "numerator": len(numer),
        "denominator": n,
        "rate_pct": round(100.0 * len(numer) / n, 4) if n else None,
        "wilson95_pct": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
    }


def _restrict(rows: list[dict[str, Any]], restrict_passed: bool) -> list[dict[str, Any]]:
    """条件口径的行子集（`passed is True`）；边际口径原样返回。"""
    if not restrict_passed:
        return rows
    return [r for r in rows if r.get("passed") is True]


def _project_endpoint_field(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """把端点字段投影到 `passed` 键上，以复用 `bootstrap_paired_diff_ci`。

    该 helper 的签名只接受 `passed` 字段（无 field 参数）——此处做**投影适配**
    （浅拷贝副本，不改原行），配对（`_pair_by_task`）与重采样（10000×seed=42）
    全部由既有 helper 完成，未重实现 bootstrap。
    """
    return [{**r, "passed": r.get(field)} for r in rows]


def paired_diff_ci(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    field: str,
    restrict_passed: bool = False,
) -> dict[str, Any]:
    """配对差值 bootstrap 95% CI（百分点）：复用 `bootstrap_paired_diff_ci`。

    条件口径的实现：两侧都先限制到 `passed is True` 的行，再交给 helper 按
    task_id 配对（两侧该字段为 None 的任务自动退出分母）。
    n_pairs < 2 → helper 返回 nan（样本不足）→ 本函数记 None（不臆造 CI）。
    """
    a = _restrict(rows_a, restrict_passed)
    b = _restrict(rows_b, restrict_passed)
    mean_diff, ci_low, ci_high, n_pairs = bootstrap_paired_diff_ci(
        _project_endpoint_field(a, field),
        _project_endpoint_field(b, field),
        n_resamples=_BOOTSTRAP_N_RESAMPLES,
        seed=_BOOTSTRAP_SEED,
    )
    if n_pairs < 2 or math.isnan(mean_diff):
        return {
            "endpoint": field,
            "restrict_passed": restrict_passed,
            "n_pairs": n_pairs,
            "diff_pp": None,
            "ci_low_pp": None,
            "ci_high_pp": None,
            "excludes_zero": None,
        }
    return {
        "endpoint": field,
        "restrict_passed": restrict_passed,
        "n_pairs": n_pairs,
        "diff_pp": round(100.0 * mean_diff, 4),
        "ci_low_pp": round(100.0 * ci_low, 4),
        "ci_high_pp": round(100.0 * ci_high, 4),
        "excludes_zero": bool(ci_low > 0.0 or ci_high < 0.0),
    }


# ─── MDE / 功效（三主要对比） ────────────────────────────────────────────
def mde_block(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]], field: str = _PRIMARY_FIELD
) -> dict[str, Any]:
    """单组配对的 MDE/功效块（σ_d² 闭式为主口径 + 两个既有函数交叉核对）。

    配对结构由 `emse_optimization.paired_contrast` 给出（共同可测子集，
    任一侧 None 不进分母）：n10 = 前臂 1/后臂 0（McNemar b），n01 = 反向（c），
    n11 = 均 1。δ = (n10 − n01)/n（前臂 − 后臂，标签方向）。

    MDE 三口径（全部现算，不硬编码）：
      1. `mde_sigma_closed_form_pp`（**主口径**）：观测 σ_d² 固定的闭式反演；
      2. `power_analysis.detectable_delta_paired`（二分）：σ_d² 随候选 δ 重算——
         在不一致结构退化（如 n01=0 且 p11=p_b）时会把 MDE 压到远小于闭式值，
         故只作交叉核对（报告 §1 有说明）；
      3. `emse_optimization.mde_paired_pp`（ψ/4 定案口径）：只用不一致率 ψ，
         不区分 n10/n01 的分布，与 σ_d² 口径不可互推。
    方向约定：MDE 恒为非负量，故按 |δ| 取较大臂为 a 侧（p11 与臂序无关）。
    """
    contrast = paired_contrast(rows_a, rows_b, field)
    n_pairs = contrast["n_pairs"]
    out: dict[str, Any] = {
        "field": field,
        "n_common": n_pairs,
        "n10": contrast["only_first"],
        "n01": contrast["only_second"],
        "n11": contrast["both"],
        "n00": contrast["neither"],
        "delta_pp": round(contrast["delta_pp"], 4) if n_pairs else None,
        "psi": None,
        "p_a": None,
        "p_b": None,
        "p11": None,
        "sigma_d2": None,
        "mde_sigma_closed_pp": None,
        "mde_sigma_bisect_pp": None,
        "mde_psi_pp": None,
        "ratio_delta_over_mde_sigma": None,
        "ratio_delta_over_mde_psi": None,
        "power_at_delta_sigma": None,
        "power_at_delta_psi": None,
        "required_n_sigma_observed_delta": None,
        "notes": [],
    }
    if n_pairs == 0:
        out["notes"].append("零配对：MDE/功效不可计算（不代入代理值）")
        return out

    n10, n01, n11 = contrast["only_first"], contrast["only_second"], contrast["both"]
    p_a = (n11 + n10) / n_pairs
    p_b = (n11 + n01) / n_pairs
    p11 = n11 / n_pairs
    delta = (n10 - n01) / n_pairs
    psi = (n10 + n01) / n_pairs
    sigma2 = sigma_d2_paired(p_a, p_b, p11)
    p_hi, p_lo = (p_a, p_b) if p_a >= p_b else (p_b, p_a)

    mde_closed = mde_sigma_closed_form_pp(n_pairs, sigma2)
    mde_bisect: float | None
    try:
        bisect = detectable_delta_paired(n_pairs, p_lo, p11, _ALPHA, _POWER)
        mde_bisect = None if math.isnan(bisect) else round(100.0 * bisect, 4)
    except ValueError as exc:  # p11 在 δ→0 处越界（Fréchet）→ 该口径不可计算
        mde_bisect = None
        out["notes"].append(f"二分口径不可计算：{exc}")
    mde_psi = mde_paired_pp(n_pairs, psi)
    try:
        n_required = required_n_paired(p_hi, p_lo, p11, _ALPHA, _POWER)
    except ValueError as exc:
        n_required = None
        out["notes"].append(f"所需 n 不可计算：{exc}")

    power_psi = power_at_delta(abs(delta) * 100.0, n_pairs, psi)
    out.update(
        {
            "psi": round(psi, 6),
            "p_a": round(p_a, 6),
            "p_b": round(p_b, 6),
            "p11": round(p11, 6),
            "sigma_d2": round(sigma2, 6),
            "mde_sigma_closed_pp": round(mde_closed, 4) if mde_closed is not None else None,
            "mde_sigma_bisect_pp": mde_bisect,
            "mde_psi_pp": round(mde_psi, 4) if mde_psi is not None else None,
            "power_at_delta_sigma": round(power_paired(n_pairs, p_a, p_b, p11, _ALPHA), 4),
            "power_at_delta_psi": round(power_psi, 4) if power_psi is not None else None,
            "required_n_sigma_observed_delta": n_required,
        }
    )
    abs_delta = abs(out["delta_pp"]) if out["delta_pp"] is not None else 0.0
    if mde_closed:
        out["ratio_delta_over_mde_sigma"] = round(abs_delta / mde_closed, 4)
    if mde_psi:
        out["ratio_delta_over_mde_psi"] = round(abs_delta / mde_psi, 4)
    if psi == 0.0:
        out["notes"].append("不一致对为 0（ψ=0）：正态近似退化，MDE/功效无对象——不是缺失而是零不一致结构")
    return out


# ─── 成本分布（中位数 + IQR，不只报均值） ────────────────────────────────
def _cache_disclosure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """缓存口径披露字段（AJ，2026-10-21）：行内无缓存字段 ⇒ 空字典。

    只对带生产者缓存字段（`cache_hits` / `cache_avoided_tokens`）的批次增键：
    旧批次（主批次 / E6 / E4 的 token_usage 都没有这两个键）的 cost_block 与
    cost_effectiveness_block 返回域逐键不变。读取不完整 ⇒ 金额为 `None` 并给机制名，
    不给部分和。
    """
    cache = cache_totals([r.get("token_usage") for r in rows])
    if not cache["present"]:
        return {}
    out: dict[str, Any] = {
        "cache_hits": cache["hits"],
        "cache_avoided_tokens": cache["avoided"],
        "n_cache_hit_rows": cache["n_hit_rows"],
        "n_cache_rows": cache["n_rows_with_fields"],
    }
    if not cache["complete"]:
        out["cache_reading_reasons"] = {**cache["missing"], **cache["reasons"]}
    return out


def cost_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """单臂 token 成本分布（中位数/IQR/均值）＋ 记账健全性（复用 S11 判定）。

    - 记账断裂（`statistical_analysis.token_accounting_sanity` 判 `computable=False`）
      → 一律输出 NOT_COMPUTABLE + 原因，**不给数字**（不得在缺失记账上出成本结论）；
    - 只对**有正向 token 记账**的行求分布（与 sanity 判定同口径），行数与分母一并登记。
    """
    sanity = token_accounting_sanity(rows)
    tokens: list[float] = []
    for r in rows:
        usage = r.get("token_usage")
        if not isinstance(usage, dict):
            continue
        value = usage.get("total_tokens")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            tokens.append(float(value))
    out: dict[str, Any] = {
        "n_rows": len(rows),
        "n_tokens_positive": len(tokens),
        "token_accounting": sanity,
        "median_tokens": None,
        "q1_tokens": None,
        "q3_tokens": None,
        "iqr_tokens": None,
        "mean_tokens": None,
    }
    # AJ：缓存披露键只在行内真带缓存字段时写入（旧批次返回域逐键不变）。
    out.update(_cache_disclosure(rows))
    if not sanity["computable"]:
        return out
    if not tokens:
        return out
    out["median_tokens"] = round(statistics.median(tokens), 2)
    out["mean_tokens"] = round(sum(tokens) / len(tokens), 2)
    if len(tokens) >= 2:
        q1, _q2, q3 = statistics.quantiles(tokens, n=4, method="inclusive")
        out["q1_tokens"] = round(q1, 2)
        out["q3_tokens"] = round(q3, 2)
        out["iqr_tokens"] = round(q3 - q1, 2)
    return out


# ─── 成本-效果（$/detection；A-07 2026-10-17）─────────────────────────────
_PRICE_TABLE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "price_table.json"


def _load_price_table(path: Path = _PRICE_TABLE_PATH) -> dict[str, dict[str, Any]]:
    """读取价目表（不可用时按空表计，但**每种机制各点一名**；调用方按"价目未登记"口径输出，不编造价格）。

    AB-13（2026-10-20）改前实测：本函数原声称"缺失/损坏 → 空表"，而 `json.loads` 的六种合法非对象
    顶层（list / str / int / float / bool / null）全部在 `data.get` 上抛 `AttributeError`——静默点与
    崩溃点分岔；同时"文件不存在 / 语法错 / `models` 键缺席 / `models` 值为非对象"四种机制一律**无痕**
    返回 `{}`，读起来跟"表里真的一个模型都没登记"同形。现按机制逐一点名后仍返回空表：返回域不变
    （受保护读数仍可比），只是不再无痕。

    AB-17（2026-10-20）：六套中文短语换成共享机制码——文件 → `models` 层的判定收口到
    `load_table_json` / `models_layer`（`price_table_file_missing` /
    `price_table_json_invalid:<T>` / `price_table_file_unreadable:<T>` /
    `price_table_not_object:<T>` / `models_key_absent` / `models_not_object:<T>`），
    同一份坏表在七个读点读出同一个名字；`{}` / `{"models": {}}` 保持静默（空对象没有形状可说，
    沿用 statistical AB-14 已注册口径）。
    """
    data, reason = load_table_json(path)
    if reason is None:
        models, reason = models_layer(data)
        if reason is None:
            return models
    print(
        f"[emse-stats] 价目表不可用（{reason}）⇒ 按空表计；未登记模型的成本是 None，不是 0",
        file=sys.stderr,
    )
    return {}


class _UnsetPriceTable:
    """`price_table` 形参的"未提供"哨兵，与调用方显式传下的 `None` 分开（AB-13，同 AB-12e 口径）。"""

    def __repr__(self) -> str:
        return "<unset>"


_UNSET_PRICE_TABLE = _UnsetPriceTable()


def cost_effectiveness_block(
    rows: list[dict[str, Any]],
    price_table: dict[str, dict[str, Any]] | _UnsetPriceTable | None = _UNSET_PRICE_TABLE,
) -> dict[str, Any]:
    """单臂成本-效果：总 token / 检出数 / $/detection / tokens/detection。

    诚实条款（与价目表 _comment 同口径）：
    - 行的计费模型 = `token_usage.by_model` 的**单一**键（多模型混合行不猜，
      记 unpriceable）；该模型价目未登记（input/output 任一为 null）→ 不编造；
    - **只把 USD 价目计入 `total_usd`**（AB-13）：改前实测一条 CNY 价目（当时真表登记为 CNY 0.5/2.0）
      被原样累加进名为 `total_usd` 的字段（1M in + 1M out 读出 2.5），币种不参与判定；
      非 USD 与币种键缺席现在各归各的 reason 并剔除。字段名是 `usd` ⇒ 这里没有币种列可以
      交代，非 USD 一律剔除；`statistical_analysis.cost_analysis` 的成本表**带币种列**，
      同一个条目在那边可以计价但必须标成登记币种（AB-14 起两处共用同一个判定谓词，
      差异只剩"有没有地方把单位写出来"，不再是两套口径）；
    - 条目形状不合（非对象 / 空对象）不与"模型未登记"混成同一条 reason；条目级判定
      （形状 → 空 → 币种 → 数字）与数字域（AB-16）收口到共享谓词 `entry_block_reason`——
      `bool`/字符串/负数/`nan`/`inf` 不再被 `float()` 收下计价，按机制剔除而非崩溃；
    - 单模型行的行级 input/output 拆分归因于该模型（主批次即此情形，精确）；
    - 检出数 = `detection_rate == 1.0` 且 detection_rate 非 None 的行数；
    - $/detection = 可计价成本合计 / 检出数；检出数为 0 → None（不除零）；
    - tokens/detection 为无价目伴侣指标（不依赖价目表，永可计算——检出>0 时）。

    AB-13 哨兵分离：改前 `price_table=None` 兼作"未提供"哨兵，实测**显式传 None 与省略形参
    同样回头读盘**并给出金额（1M+1M token 读出 1.5），调用方的"这次不要计价"被读成"按
    experiments/price_table.json 计费"。现在只有省略该形参才读盘；显式 `None` 与非对象价目
    一律按空表计并留痕。真批次只用到 USD 已登记的 `deepseek-flash`，故三臂 $/task 读数一字不变。

    AK（2026-10-21）：显式零 token 行（input/output/total 全 0）本来就被 `total_tokens > 0`
    过滤掉，却没有计数——主批 plain_llm_df 35/261 行生成测试后零记账，§4.1 仍显示
    "226 行计价 / 0 行不可计价"，读者无从知道 35 行消失了。现在另计
    `n_zero_token_rows` 与其中有 generated_test 的 `n_zero_token_output_rows`（仅 >0 时
    写入；全记账臂返回域逐键不变），呈现层据此声明 `total_usd` / `$/detection` /
    `tokens/detection` 是已记录花费下界。检出分母仍收全部行（AE2 口径不变）。

    AL（2026-10-21）：行级读取改走共享 `row_token_counts`（与 ext / S11 同一值域）：
    - 改前 `usage.get(...) or 0` 把缺席、null、`"100"`、`True`、负数、`nan`/`inf`
      折成可计价数字——现在三元组任一项读不动 ⇒ `total_tokens` / `total_usd` /
      两个比值一律 `None`（机制名见 `token_reading_reasons`），不给部分和；
    - 检出计数与 token 可读性解耦：改前 `token_usage` 非对象的行在计数前被
      `continue`，检出分母随记账好坏缩水；现在 `n_detections` 只看 `detection_rate`；
    - `input+output != total`、`by_model` 形状/键/值域坏、`by_model` 求和与 total
      不符、正 token 行无归因 ⇒ 只废金额（`token_money_reasons`），token 总量与
      `tokens/detection` 仍可读（金额给 `None`，不拿局部和冒充全额）；
    - 缓存证据行（命中数 > 0 解释的真实零消耗）不计入 AK 零行下界（AK 边界⑥）。
    真批次 783 行全部三元组合法、归因一致，故三臂读数与返回域逐键不变。
    """
    table: dict[str, dict[str, Any]]
    if isinstance(price_table, _UnsetPriceTable):
        table = _load_price_table()
    elif price_table is None:
        print(
            "[emse-stats] cost_effectiveness_block 收到显式 price_table=None ⇒ 按空表计、不回头读盘"
            "（改前这个 None 会去读盘上的真表并给出金额）",
            file=sys.stderr,
        )
        table = {}
    elif not isinstance(price_table, dict):
        print(
            f"[emse-stats] cost_effectiveness_block 收到非对象价目表（{type(price_table).__name__}）⇒ 按空表计",
            file=sys.stderr,
        )
        table = {}
    else:
        table = price_table
    total_tokens = 0.0
    total_usd = 0.0
    n_unpriceable = 0
    n_priced = 0
    n_detections = 0
    n_detect_measurable = 0
    n_zero_token_rows = 0
    n_zero_token_output_rows = 0
    n_unreadable = 0
    n_money_blocked = 0
    reasons: dict[str, int] = {}
    token_reasons: dict[str, int] = {}
    money_reasons: dict[str, int] = {}
    tokens_readable = True
    money_readable = True

    def _unpriceable(reason: str) -> None:
        nonlocal n_unpriceable
        n_unpriceable += 1
        reasons[reason] = reasons.get(reason, 0) + 1

    def _block_money(reason: str) -> None:
        nonlocal n_money_blocked, money_readable
        n_money_blocked += 1
        money_readable = False
        money_reasons[reason] = money_reasons.get(reason, 0) + 1

    def _attribution_reason(by_model: dict[Any, Any], total: int) -> str | None:
        # AM（2026-10-21）：判定体迁到 `src/budget/token_usage.by_model_reason`，
        # 与成本表聚合共用一份；本地保留函数名，AL 的既有锁与调用点零改动。
        return by_model_reason(by_model, total)

    for r in rows:
        # AL：检出数只由 detection_rate 决定——token_usage 是否可读不得缩水分母。
        det = r.get("detection_rate")
        if det is not None:
            n_detect_measurable += 1
            if det == 1.0:
                n_detections += 1
        counts, row_reasons = row_token_counts(r)
        if counts is None:
            # AL：任一项读不动 ⇒ 总量与金额都不给部分和（改前 `or 0` 把它折成可计价 0）。
            tokens_readable = False
            money_readable = False
            n_unreadable += 1
            for code in row_reasons:
                token_reasons[code] = token_reasons.get(code, 0) + 1
            continue
        total, inp, out = counts
        total_tokens += float(total)
        usage = r["token_usage"]
        # AK：显式三元组全 0 的行不进 token 合计、也不产生金额，但仍进检出分母。
        # 有 generated_test 的是"有产出、无花费记录"，必须在 §4.1 单独披露。
        # AL：缓存命中解释的真实零消耗不是记账缺口，不得落进 AK 下界口径（边界⑥）。
        if total == 0 and inp == 0 and out == 0 and not cache_caliber(usage)["evidence"]:
            n_zero_token_rows += 1
            if isinstance(r.get("generated_test"), str) and r["generated_test"].strip():
                n_zero_token_output_rows += 1
        if inp + out != total:
            # AL：拆分与总量自相矛盾 ⇒ token 总量仍可读，但金额没有可信的输入口径。
            _block_money("token_split_mismatch")
            continue
        by_model = usage.get("by_model")
        if not isinstance(by_model, dict):
            # 正 token 行没有归因对象 ⇒ 金额不可读；零 token 行无需归因（原行为）。
            if total > 0:
                _block_money(
                    "token_field_absent:by_model"
                    if "by_model" not in usage
                    else f"by_model_not_object:{type(by_model).__name__}"
                )
            continue
        if not by_model:
            if total > 0:
                _block_money("by_model_empty")
            continue
        attribution_reason = _attribution_reason(by_model, total)
        if attribution_reason is not None:
            if total > 0:
                _block_money(attribution_reason)
            continue
        if len(by_model) != 1:
            _unpriceable("multi_model_row")
            continue
        model = next(iter(by_model))
        # AB-17：改前 `table.get(model)` 的 `is None` 把"键缺席"与"值为 null"共读成
        # `model_unregistered`（AB-11 判据）；现在值 null 交条目谓词读
        # `entry_not_object:NoneType`，"未登记"只剩"真的没这个键"。
        if model not in table:
            _unpriceable("model_unregistered")
            continue
        price = table[model]
        # AB-14 判定、AB-15d 机制名与 AB-16 数字域都取自共享事实源（`src.budget.pricing`）。
        # 改前这里是仓内第二套归因词汇（本文件自派 `currency_absent` / `currency_not_usd:*`
        # 的 if/elif 链）+ `float()` 直收（`True` 当 1、`"1.0"` 收下、`-1.0` 编出负数金额、
        # `[1.0]` 抛 TypeError、`nan`/`inf` 累成非有限 `total_usd`）；替换后对可达状态逐码不变，
        # 坏数字从"计价"改成按机制剔除。
        reason = entry_block_reason(price)
        if reason is not None:
            _unpriceable(reason)
            continue
        total_usd += (
            float(inp) * float(price["input_per_mtok"]) + float(out) * float(price["output_per_mtok"])
        ) / 1_000_000.0
        n_priced += 1
    out: dict[str, Any] = {
        "total_tokens": round(total_tokens, 2) if tokens_readable else None,
        "n_rows_with_tokens_positive": n_priced + n_unpriceable,
        "n_priced_rows": n_priced,
        "n_unpriceable_rows": n_unpriceable,
        "total_usd": round(total_usd, 6) if money_readable else None,
        "n_detections": n_detections,
        "n_detection_measurable": n_detect_measurable,
        "usd_per_detection": (round(total_usd / n_detections, 6) if money_readable and n_detections else None),
        "tokens_per_detection": (round(total_tokens / n_detections, 2) if tokens_readable and n_detections else None),
    }
    # 披露键只在真发生剔除时写入：真批次三臂 n_unpriceable 均为 0，返回域因此逐键不变。
    if reasons:
        out["n_unpriceable_reasons"] = dict(sorted(reasons.items()))
    # AL：行级读取缺口只在真发生时披露（真批次 783 行全部可读、归因一致 ⇒ 逐键不变）。
    if token_reasons:
        out["n_token_unreadable_rows"] = n_unreadable
        out["token_reading_reasons"] = dict(sorted(token_reasons.items()))
    if money_reasons:
        out["n_token_money_blocked_rows"] = n_money_blocked
        out["token_money_reasons"] = dict(sorted(money_reasons.items()))
    # AK：显式零 token 行不进 token/金额合计；有产出零记账的行另计数。
    # 只在真发生时写入 ⇒ 全记账臂（主批 aitester / plain_llm）返回域逐键不变。
    if n_zero_token_rows:
        out["n_zero_token_rows"] = n_zero_token_rows
        if n_zero_token_output_rows:
            out["n_zero_token_output_rows"] = n_zero_token_output_rows
    # AJ：缓存口径披露（仅行内带缓存字段时增键；主批次三臂返回域逐键不变）。
    out.update(_cache_disclosure(rows))
    return out


# ─── 修正口径（可选，opt-in） ────────────────────────────────────────────
def corrected_endpoints(
    rows: dict[str, list[dict[str, Any]]],
    timeout: int = 60,
) -> dict[str, dict[str, Any]]:
    """ADR-0021/0027 修正口径端点（调用 `corrected_metrics.correct_row`，只读）。

    重型路径：带补丁行逐行 `normalize_patch_text` + gold `test_cases` 重放
    （本地 pytest 子进程，零 LLM），145 行量级约 1–2 分钟，故默认关闭。
    返回 {臂: {repair_marginal, repair_replayable, false_fix_marginal,
    false_fix_conditional, verdict_dist}}；无补丁臂原值即正确语义（保留）。
    """
    from collections import Counter

    from experiments.corrected_metrics import correct_row

    out: dict[str, dict[str, Any]] = {}
    for arm in _ARMS:
        corrected = [correct_row(r, timeout=timeout) for r in rows.get(arm, [])]
        replayable = sum(1 for r in corrected if r.get("corrected_verdict") in ("correct", "wrong_patch"))
        correct = sum(1 for r in corrected if r.get("corrected_verdict") == "correct")
        out[arm] = {
            "rows": corrected,
            "verdict_dist": dict(Counter(str(r.get("corrected_verdict")) for r in corrected)),
            "n_replayable": replayable,
            "n_correct": correct,
            "replayable_repair_pct": round(100.0 * correct / replayable, 4) if replayable else None,
            "repair_marginal": endpoint_point(corrected, "repair_rate", False),
            "false_fix_marginal": endpoint_point(corrected, "false_fix_rate", False),
            "false_fix_conditional": endpoint_point(corrected, "false_fix_rate", True),
        }
    return out


# ─── 报告渲染 ────────────────────────────────────────────────────────────
def _f(value: float | None, nd: int = 2) -> str:
    """数值渲染：None → "—"（不把不可计算渲染成 0）。"""
    return "—" if value is None else f"{value:.{nd}f}"


def _pair_label(a: str, b: str) -> str:
    return f"`{a}` vs `{b}`"


def _render_caliber_block(
    results_dir: Path,
    batch_meta: list[dict[str, Any]],
    arms: tuple[str, ...],
    command: str,
) -> list[str]:
    """口径头块：批次文件（含 sha256）/臂/种子处理/缺失口径/来源/派生证据声明。"""
    lines = [
        "## 0. 口径（caliber）",
        "",
        "- **派生证据声明**：本报告由 `experiments/emse_stats_report.py` 从下述**已归档批次 JSON**"
        "派生（零 LLM / 零网络 / 只读工件），全部数字现算；它**不替代**预注册主报告，"
        "引用时须标注为派生证据（canonical 口径以 `statistical_report_3seed_pooled.md` 为准）。",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（本地时间）；复算命令：`{command}`",
        f"- 批次目录：`{results_dir}`；批次文件（{len(batch_meta)}）：",
    ]
    lines.extend(
        f"  - `{meta['file']}`（seed={meta['seed']}，行前缀 `{meta['prefix']}`，"
        f"sha256=`{meta['sha256'][:16]}…`，每臂行数 "
        + "、".join(f"{arm}:{count}" for arm, count in meta["n_rows_per_arm"].items())
        + "）"
        for meta in batch_meta
    )
    lines += [
        f"- 臂（{len(arms)}）：{' / '.join(f'`{a}`' for a in arms)}",
        "- **种子处理**：跨种子池化——行 `task_id` 加 `s<seed>__` 前缀（seed 取批次 "
        "`provenance.seed`，回退顶层 `seed`，再回退文件名），与 `statistical_analysis.py --pool-seeds` "
        "同口径；3 种子 × 87 任务 → 261 配对单元/臂（同种子重复跑仍按最新批次优先去重）。",
        "- **缺失值口径**：M1 诚实口径——端点字段为 `None` 的行**剔除**（不计 0、不进分母）；"
        "配对要求两侧该字段均可测（`emse_optimization.paired_contrast` 同口径）。",
        f"- **统计口径来源**：MDE σ_d² 闭式 = `scripts/tools/power_analysis.py` 的 n_required 公式反演"
        f"（α={_ALPHA} 双侧，power={_POWER}）；MDE ψ/4 = `experiments/emse_optimization.mde_paired_pp`；"
        f"比例型端点 95% CI = `experiments/statistical_analysis.bootstrap_paired_diff_ci`"
        f"（配对差值均值，百分位法，{_BOOTSTRAP_N_RESAMPLES} 次重采样，seed={_BOOTSTRAP_SEED}，"
        "order-statistic 分位）。",
        "- **未含聚类校正**：模板聚类稳健性见 canonical 报告 AC4 节；簇数取决于批次真实生成参数"
        "（主批 `max_pattern_repeat=2` 口径为 31 模板簇，见 `statistical_analysis.cluster_robust_analysis`；"
        "2026-10-18 A06 修复后按归档任务元数据 / 分 seed 重建解析程序身份，本报告不硬编码簇数），"
        "本报告的 n 与 CI 均为逐任务独立口径（名义偏乐观）。",
        "",
    ]
    return lines


def _render_mde_section(mde_rows: list[dict[str, Any]]) -> list[str]:
    """§1 结构表 + MDE 表。"""
    lines = [
        "## 1. 三主要对比的 MDE / 功效（主端点 detection_rate）",
        "",
        "配对结构（McNemar 2×2 的不一致单元；n10 = 前臂检出=1 且后臂=0，n01 = 反向，n11 = 均检出）：",
        "",
        "| 对比（前臂 − 后臂） | n_common | n10 | n01 | n11 | n00 | ψ（不一致率） | 观测 δ(pp) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {row['label']} | {row['n_common']} | {row['n10']} | {row['n01']} | {row['n11']} | {row['n00']} "
        f"| {_f(row['psi'], 4)} | {_f(row['delta_pp'], 4)} |"
        for row in mde_rows
    )
    lines += [
        "",
        "MDE（α=0.05 双侧 / power=0.8，单位 pp）与观测效应比值——**观测/MDE < 1 表示该对比在当前 n 下本就检不出**：",
        "",
        "| 对比 | MDE_σ(pp)（闭式，主口径） | MDE_σ(pp)（二分） | MDE_ψ(pp)（ψ/4 口径） "
        "| 观测/MDE_σ | 观测/MDE_ψ | 功效@观测δ（σ_d²） | 功效@观测δ（ψ） | 达 80% 功效所需 n（σ_d²） |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in mde_rows:
        lines.append(
            f"| {row['label']} | {_f(row['mde_sigma_closed_pp'], 4)} | {_f(row['mde_sigma_bisect_pp'], 4)} "
            f"| {_f(row['mde_psi_pp'], 4)} | {_f(row['ratio_delta_over_mde_sigma'], 4)} "
            f"| {_f(row['ratio_delta_over_mde_psi'], 4)} | {_f(row['power_at_delta_sigma'], 4)} "
            f"| {_f(row['power_at_delta_psi'], 4)} | {row['required_n_sigma_observed_delta'] or '—'} |"
        )
    lines += [
        "",
        "**口径说明（三个 MDE 列不可混用）**：",
        "",
        "1. `MDE_σ` 闭式（主口径）= `(z_{1−α/2}+z_power)·√(σ_d²/n)`，σ_d² = p_a + p_b − δ² − 2·p11 "
        "取**观测不一致结构**（源：`scripts/tools/power_analysis.py` 的 n_required 公式，闭式反演）。",
        "2. `MDE_σ` 二分 = `power_analysis.detectable_delta_paired`：该函数在候选 δ 上**重算** "
        "σ_d²（p_a = p_b + δ，p11 固定），当不一致结构退化（如 n01=0 且 p11≈p_b，σ_d²→0）时会把 "
        "MDE 压到远小于闭式值——属「结构随 δ 漂移」的乐观口径，仅作交叉核对，**不用于主结论**。",
        "3. `MDE_ψ` = `emse_optimization.mde_paired_pp`（10-13 定案公式，只用不一致率 ψ、不区分 "
        "n10/n01 的分布，未乘 (1−ψ) 项），与 σ_d² 口径不可互推，只作定案口径对照。",
        "",
        "功效与所需 n 的 σ_d² 口径分别复用 `power_analysis.power_paired` 与 "
        "`power_analysis.required_n_paired`（后者在闭式 n 上自增直到达标功效）。",
        "",
    ]
    degenerate = [row for row in mde_rows if row.get("notes")]
    for row in degenerate:
        for note in row["notes"]:
            lines.append(f"- **{row['label']}**：{note}")
    if degenerate:
        lines.append("")
    return lines


def _render_endpoint_section(
    arms_data: dict[str, dict[str, Any]],
    ci_rows: list[dict[str, Any]],
) -> list[str]:
    """§2 各臂点估计 + §3 配对差 CI。"""
    lines = [
        "## 2. 比例型端点：各臂点估计（None 剔除，不计 0）",
        "",
        "| 臂 | 端点 | 可测分子/分母 | 点估计(%) | Wilson 95% CI(%) |",
        "|---|---|---|---|---|",
    ]
    for arm, data in arms_data.items():
        for label, point in data["endpoints"].items():
            ci = point.get("wilson95_pct")
            ci_s = "—" if ci is None else f"[{_f(ci[0], 4)}, {_f(ci[1], 4)}]"
            lines.append(
                f"| `{arm}` | {label} | {point['numerator']}/{point['denominator']} | {_f(point['rate_pct'], 4)} | {ci_s} |"
            )
    lines += [
        "",
        "## 3. 比例型端点：配对差 95% CI（bootstrap，10000 次重采样，seed=42）",
        "",
        "配对差 = 前臂 − 后臂（pp）；条件口径 = 两侧皆 `passed=True` 的行子集（配对不变）。",
        "",
        "| 对比（前臂 − 后臂） | 端点 | n_pairs | 配对差(pp) | 95% CI(pp) | 排除 0？ |",
        "|---|---|---|---|---|---|",
    ]
    for row in ci_rows:
        ci = "—" if row["ci_low_pp"] is None else f"[{_f(row['ci_low_pp'], 4)}, {_f(row['ci_high_pp'], 4)}]"
        excludes = "—" if row["excludes_zero"] is None else ("是" if row["excludes_zero"] else "否")
        lines.append(
            f"| {row['label']} | {row['endpoint_label']} | {row['n_pairs']} | {_f(row['diff_pp'], 4)} "
            f"| {ci} | {excludes} |"
        )
    lines += [
        "",
        "`—` = 不可计算（n_pairs<2：helper 返回 nan），**不是 0**；`[0.0000, 0.0000]` 则是真实的"
        "零宽区间（逐任务差值全为 0，如原口径 repair）。",
        "",
        "口径备注：CI 由 `bootstrap_paired_diff_ci` 计算——该 helper 的签名只接受 `passed` 字段"
        "（无 field 参数），故本工具把端点字段**投影**到 `passed` 键上再调用（浅拷贝适配，"
        "配对与重采样逻辑完全复用，未重实现 bootstrap）；`None` 行在配对阶段即退出分母。",
        "条件 false_fix 的两臂点估计按各臂自身 passed 行计算（§2），而 §3 的配对差限制在"
        "**两侧皆 passed** 的子集（保持配对结构），故 §3 的点估计与 §2 两臂点估计之差不必然相等。",
        "CI 为百分位法（order-statistic）区间，非基本 bootstrap；`n_pairs<2` 时 helper 返回 nan，"
        "本报告记 `—`（不臆造区间）。",
        "",
    ]
    return lines


def _render_cache_lines(arms_data: dict[str, dict[str, Any]]) -> list[str]:
    """§4 缓存口径披露（AJ）：无缓存字段的臂 ⇒ []，历史报告文本逐字不变。"""
    shown: list[str] = []
    for arm, data in arms_data.items():
        cost = data.get("cost") or {}
        if "cache_hits" not in cost:
            continue
        if cost.get("cache_hits") is None:
            codes = cost.get("cache_reading_reasons") or {}
            detail = "；".join(f"{code}←{n} 行" for code, n in sorted(codes.items())) or "未登记机制名"
            shown.append(f"- `{arm}`：缓存读数不可用（{detail}）⇒ 命中/避免 token 无读数（不是 0）。")
            continue
        shown.append(
            f"- `{arm}`：命中 {cost['cache_hits']} 次、避免 {cost['cache_avoided_tokens']} tokens"
            f"（{cost['n_cache_rows']}/{cost['n_rows']} 行带缓存字段，{cost['n_cache_hit_rows']} 行命中）。"
        )
    if not shown:
        return []
    return [
        "",
        "**缓存口径（AJ）**——缓存命中不是记账断裂，也不是免费：命中服务的行真实 API 消耗为 0"
        "（记 0 是对的），避免的 token 另记且不计入成本，两种口径须同读；S11 记账健全性把"
        "缓存命中行计为有记账，而 §4 的分布仍只统计真实 `total_tokens > 0` 的行。",
        *shown,
        "",
    ]


def _render_cost_section(arms_data: dict[str, dict[str, Any]]) -> list[str]:
    """§4 成本分布。"""
    lines = [
        "## 4. 成本分布：每任务 tokens（中位数 + IQR，不只报均值）",
        "",
        "| 臂 | 行数 | 有正向记账行 | 中位数 tokens | Q1 | Q3 | IQR | 均值 | 记账健全性 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, data in arms_data.items():
        cost = data["cost"]
        sanity = cost["token_accounting"]
        if not sanity["computable"]:
            lines.append(
                f"| `{arm}` | {cost['n_rows']} | {cost['n_tokens_positive']} | NOT_COMPUTABLE | — | — | — | — "
                f"| 记账断裂：{sanity['reason']} |"
            )
            continue
        cache_note = f"；{cost['n_cache_hit_rows']} 行缓存命中记账" if cost.get("n_cache_hit_rows") else ""
        zero_out = sanity.get("n_zero_output_rows") or 0
        output_note = f"；其中 {zero_out} 行 generated_test 非空、有产出无花费记录" if zero_out else ""
        lines.append(
            f"| `{arm}` | {cost['n_rows']} | {cost['n_tokens_positive']} | {_f(cost['median_tokens'], 1)} "
            f"| {_f(cost['q1_tokens'], 1)} | {_f(cost['q3_tokens'], 1)} | {_f(cost['iqr_tokens'], 1)} "
            f"| {_f(cost['mean_tokens'], 1)} | 可计算（{sanity['n_without_accounting']} 行无记账{output_note}{cache_note}） |"
        )
    lines += [
        "",
        "分位口径：`statistics.quantiles(..., n=4, method='inclusive')`（线性插值）；"
        "只统计 `token_usage.total_tokens > 0` 的行（与 S11 记账健全性判定同口径）；"
        "记账断裂的臂一律输出 NOT_COMPUTABLE，不给成本数字。",
        "",
    ]
    lines += _render_cache_lines(arms_data)
    lines += [
        "### 4.1 成本-效果：$/detection（A-07，2026-10-17 增补）",
        "",
        "| 臂 | 检出数/可测 | 总 tokens | 总 $（可计价行） | $/detection | tokens/detection | 计价健全性 |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, data in arms_data.items():
        eff = data.get("cost_eff")
        if not eff:
            continue
        tokens = _f(eff["total_tokens"], 0)
        usd = "—" if eff["total_usd"] is None else _f(eff["total_usd"], 6)
        usd_per_det = "—" if eff["usd_per_detection"] is None else _f(eff["usd_per_detection"], 6)
        tok_per_det = "—" if eff["tokens_per_detection"] is None else _f(eff["tokens_per_detection"], 1)
        lines.append(
            f"| `{arm}` | {eff['n_detections']}/{eff['n_detection_measurable']} "
            f"| {tokens} | {usd} | {usd_per_det} | {tok_per_det} "
            f"| {eff['n_priced_rows']} 行计价 / {eff['n_unpriceable_rows']} 行不可计价 |"
        )
    lines += [
        "",
        "计价口径（与 `experiments/price_table.json` 的诚实条款一致）：行的计费模型取 "
        "`token_usage.by_model` 的**单一**键（多模型混合行不猜，计不可计价）；"
        "该模型价目未登记（input/output 任一为 null）→ 不编造价格；"
        "**只有币种为 USD 的价目参与 `total_usd`**（AB-13：非 USD 与币种键缺席一律计不可计价，"
        "本表不存在把人民币价目累加进美元字段这条通道）；"
        "单模型行的行级 input/output 拆分归因于该模型（主批次即此情形，精确）。",
        "检出数 = `detection_rate == 1.0` 且非 None 的行（None 不进分母）；"
        "检出数为 0 时 $/detection 与 tokens/detection 均记 `—`（不除零、不臆造）。",
        "tokens/detection 为无价目伴侣指标（不依赖价目表），可与 $/detection 互证。",
    ]
    al_arms: list[tuple[str, dict[str, Any]]] = [
        (arm, data.get("cost_eff") or {})
        for arm, data in arms_data.items()
        if (data.get("cost_eff") or {}).get("n_token_unreadable_rows")
        or (data.get("cost_eff") or {}).get("n_token_money_blocked_rows")
    ]
    if al_arms:
        lines.append(
            "**token 行级读取（AL）**——下列臂有行无法读出完整三元组或金额归因不一致："
            "读不动 ⇒ `total_tokens` / 总 $ / 两个比值一律 `—`（不给部分和；"
            "改前缺席/坏值被 `or 0` 折成 0 并计价）；拆分或归因不一致 ⇒ token 总量与 "
            "tokens/detection 仍可读，金额与 $/detection 记 `—`。"
            "检出数只由 `detection_rate` 决定，不随 token 可读性缩水。"
        )
        for arm, eff in al_arms:
            parts: list[str] = []
            if eff.get("n_token_unreadable_rows"):
                codes = eff.get("token_reading_reasons") or {}
                detail = "、".join(f"{k}×{v}" for k, v in sorted(codes.items())) or "未登记机制名"
                parts.append(f"{eff['n_token_unreadable_rows']} 行 token 不可读（{detail}）")
            if eff.get("n_token_money_blocked_rows"):
                codes = eff.get("token_money_reasons") or {}
                detail = "、".join(f"{k}×{v}" for k, v in sorted(codes.items())) or "未登记机制名"
                parts.append(f"{eff['n_token_money_blocked_rows']} 行金额被阻断（{detail}）")
            lines.append(f"- `{arm}`：" + "；".join(parts) + "。")
        lines.append("")
    if any("cache_hits" in (data.get("cost") or {}) for data in arms_data.values()):
        lines.append(
            "缓存命中行的 tokens / $ / detection 均为**真实 API 消耗**口径：0 是真的 0，但不是免费"
            "——命中次数与避免的 token 见上（§4 缓存口径）。"
        )
    lines += [
        "",
    ]
    zero_arms = [
        (arm, data) for arm, data in arms_data.items() if (data.get("cost_eff") or {}).get("n_zero_token_rows")
    ]
    if zero_arms:
        lines.append(
            "**零 token 行的成本口径（AK）**——下列臂有行 token 全 0：这些行不进 "
            "`total_tokens` / `total_usd`，但检出数仍计入分母 ⇒ 总 $、$/detection 与 "
            "tokens/detection 是**已记录花费的下界**（缺记账行按 0 计），不是真实均值，更不是免费。"
        )
        for arm, data in zero_arms:
            eff = data["cost_eff"]
            n_zero = eff["n_zero_token_rows"]
            n_out = eff.get("n_zero_token_output_rows") or 0
            total = (data.get("cost") or {}).get("n_rows")
            ratio = f"{n_zero}/{total}" if isinstance(total, int) and total > 0 else f"{n_zero}"
            detail = f"，其中 {n_out} 行 generated_test 非空（有产出、无花费记录）" if n_out else ""
            lines.append(f"- `{arm}`：{ratio} 行 token 全 0{detail}。")
        lines.append("")
    for arm, data in arms_data.items():
        eff = data.get("cost_eff") or {}
        reasons = eff.get("n_unpriceable_reasons")
        if reasons:
            shown = "、".join(f"{k}×{v}" for k, v in reasons.items())
            lines += [f"- `{arm}` 不可计价行的机制点名：{shown}（`total_usd` 只含 USD 已登记价目行）。", ""]
    return lines


def _render_corrected_section(corrected: dict[str, Any] | None) -> list[str]:
    """§5 修正口径（opt-in；默认关闭时输出显式说明）。"""
    if corrected is None:
        return [
            "## 5. 修正口径（repair / false_fix，ADR-0021/0027）",
            "",
            "**本报告默认输出原口径（raw）数字**：修正口径需按 ADR-0021 对带补丁行做 "
            "`normalize_patch_text` + gold `test_cases` 重放（`experiments/corrected_metrics.correct_row`，"
            "本地 pytest 子进程、零 LLM），属重型路径——请运行 `make corrected-metrics`，"
            "或本工具 `--corrected-repair` 开关（同一函数、只读工件）后再引用修正值。",
            "",
            "已知影响面：R-P0-2 的「repair 全线 0」系 patch 字段围栏残留导致的测量伪影（ADR-0021），"
            "原口径 `repair_rate` 因此系统性压零；本报告 §2/§3 的 repair 行须与该勘误同读。",
            "",
        ]
    lines = [
        "## 5. 修正口径（repair / false_fix，ADR-0021/0027；`--corrected-repair` 现算）",
        "",
        "| 臂 | 行级裁决分布 | 可重放 | 修正 correct | 修正 repair（可重放分母 %） "
        "| 修正 repair（可测分母 %） | 修正 false_fix 边际(%) | 修正 false_fix 条件(%) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for arm, data in corrected["arms"].items():
        lines.append(
            f"| `{arm}` | {data['verdict_dist']} | {data['n_replayable']} | {data['n_correct']} "
            f"| {_f(data['replayable_repair_pct'], 4)} | {_f(data['repair_marginal']['rate_pct'], 4)} "
            f"| {_f(data['false_fix_marginal']['rate_pct'], 4)} "
            f"| {_f(data['false_fix_conditional']['rate_pct'], 4)} |"
        )
    lines += [
        "",
        "修正口径由 `corrected_metrics.correct_row` 逐行现算（只读工件；无补丁行原值即正确语义，保留）；"
        "两列 repair 分母不同——「可重放分母」= correct/(correct+wrong_patch)（ADR-0027 报告口径），"
        "「可测分母」= 修正后 `repair_rate` 非 None 的行（与本报告 §2 同口径）。",
        "",
        "修正口径下的配对差 95% CI（同一 bootstrap 口径）：",
        "",
        "| 对比（前臂 − 后臂） | 端点 | n_pairs | 配对差(pp) | 95% CI(pp) | 排除 0？ |",
        "|---|---|---|---|---|---|",
    ]
    for row in corrected["paired_diff_ci"]:
        ci = "—" if row["ci_low_pp"] is None else f"[{_f(row['ci_low_pp'], 4)}, {_f(row['ci_high_pp'], 4)}]"
        excludes = "—" if row["excludes_zero"] is None else ("是" if row["excludes_zero"] else "否")
        lines.append(
            f"| {row['label']} | {row['endpoint_label']} | {row['n_pairs']} | {_f(row['diff_pp'], 4)} "
            f"| {ci} | {excludes} |"
        )
    lines.append("")
    return lines


def _render_limitations(
    mde_rows: list[dict[str, Any]],
    ci_rows: list[dict[str, Any]],
    corrected: dict[str, Any] | None,
    repair_structure: dict[str, dict[str, Any]],
) -> list[str]:
    """§6 不可计算项与局限（显式列出，不用代理值）。"""
    lines = ["## 6. 不可计算项与局限（显式登记，不用代理值替代）", ""]
    items: list[str] = [
        f"- {row['label']}：σ_d² 口径 MDE 不可计算（σ_d²={row['sigma_d2']}，无不一致结构）——"
        "该端点在当前工件下无功效分析对象。"
        for row in mde_rows
        if row["mde_sigma_closed_pp"] is None
    ]
    items.extend(
        f"- {row['label']} · {row['endpoint_label']}：n_pairs={row['n_pairs']} < 2，CI 不可计算。"
        for row in ci_rows
        if row["ci_low_pp"] is None
    )
    structure_text = "；".join(
        f"`{pair}` n10/n01={value['only_first']}/{value['only_second']}" for pair, value in repair_structure.items()
    )
    items.append(
        f"- **repair_rate 端点的功效分析无对象（现算）**：三对比配对结构 {structure_text}——"
        "不一致对全为 0（ψ=0），正态近似退化，故本报告不为 repair 端点报 MDE/功效"
        "（`emse_optimization.mde_paired_pp` 在 ψ=0 时按设计返回 None；不以 0 冒充 MDE），"
        "对应 §3 的配对差亦为真实的零宽区间 [0, 0]。"
    )
    if corrected is None:
        items.append("- 修正口径 repair/false_fix：默认未现算（重型重放路径），见 §5 说明。")
    items.append(
        "- 本报告为**逐任务独立口径**：跨种子同模板任务为相关观测（簇数取决于批次真实生成参数，"
        '主批 `max_pattern_repeat=2` 口径为 31 模板簇；2026-10-18 A06 修复前"26 个唯一程序体"'
        "系漏 cap 的重建伪影，已废弃），n 与 CI 名义偏乐观；聚类稳健结论以 canonical 报告 AC4 节为准。"
    )
    items.append(
        "- MDE 为**正态近似**（无精确检验对应物），且假定不一致结构在备择下不变；"
        "观测 δ 远大于 MDE 时该近似不影响定性结论，接近 MDE 量级时须谨慎。"
    )
    lines += items
    lines.append("")
    return lines


def build_report(
    results_dir: Path,
    batch_meta: list[dict[str, Any]],
    data: dict[str, Any],
    command: str,
) -> str:
    """Markdown 报告（口径头块 + §1 MDE/功效 + §2/§3 端点与 CI + §4 成本 + §5 修正 + §6 局限）。"""
    lines = [
        "# EMSE 统计补口报告：主对比 MDE/功效 + 比例型端点 bootstrap/Wilson 95% CI + 成本-效果",
        "",
        "（2026-10-15 批次；A-07 增补 Wilson CI 与 $/detection，2026-10-17；零 LLM / 零网络 / 只读归档工件；全部数字由 `experiments/emse_stats_report.py` 现算）",
        "",
    ]
    lines += _render_caliber_block(results_dir, batch_meta, _ARMS, command)
    lines += _render_mde_section(data["mde"])
    lines += _render_endpoint_section(data["arms"], data["paired_diff_ci"])
    lines += _render_cost_section(data["arms"])
    lines += _render_corrected_section(data.get("corrected"))
    lines += _render_limitations(data["mde"], data["paired_diff_ci"], data.get("corrected"), data["repair_structure"])
    lines += [
        "---",
        "",
        "*报告生成：`experiments/emse_stats_report.py`（EMSE 统计补口批次 2026-10-15；"
        "派生证据，不得替代预注册主报告）*",
        "",
    ]
    return "\n".join(lines)


# ─── 主流程 ──────────────────────────────────────────────────────────────
def analyze(
    results_dir: Path,
    batch_files: list[Path],
    corrected_repair: bool = False,
    timeout: int = 60,
) -> dict[str, Any]:
    """全量分析（纯计算 + 只读工件；`corrected_repair=True` 时附加修正口径重放）。

    返回与 JSON 输出同构的字典（报告与 JSON 由同一份数字渲染，二者不分裂）。
    """
    rows, batch_meta = load_pooled_rows(results_dir, batch_files)
    arms_data: dict[str, dict[str, Any]] = {}
    for arm in _ARMS:
        endpoints = {label: endpoint_point(rows[arm], field, restrict) for label, field, restrict in _ENDPOINTS}
        arms_data[arm] = {
            "n_rows": len(rows[arm]),
            "endpoints": endpoints,
            "cost": cost_block(rows[arm]),
            "cost_eff": cost_effectiveness_block(rows[arm]),
        }

    mde_rows: list[dict[str, Any]] = []
    ci_rows: list[dict[str, Any]] = []
    for arm_a, arm_b in _PRIMARY_PAIRS:
        label = _pair_label(arm_a, arm_b)
        block = mde_block(rows[arm_a], rows[arm_b], _PRIMARY_FIELD)
        block["pair"] = f"{arm_a} vs {arm_b}"
        block["label"] = label
        mde_rows.append(block)
        for label_ep, field, restrict in _ENDPOINTS:
            ci = paired_diff_ci(rows[arm_a], rows[arm_b], field, restrict)
            ci["pair"] = f"{arm_a} vs {arm_b}"
            ci["label"] = label
            ci["endpoint_label"] = label_ep
            ci_rows.append(ci)

    # repair 端点的 MDE 退化说明（如需）：不一致结构为 0 → ψ=0 → 定案函数返回 None
    repair_structure = {f"{a} vs {b}": paired_contrast(rows[a], rows[b], "repair_rate") for a, b in _PRIMARY_PAIRS}

    corrected: dict[str, Any] | None = None
    if corrected_repair:
        # 重型只读路径：逐行 correct_row（normalize_patch_text + gold 重放，零 LLM）
        raw_corrected = corrected_endpoints(rows, timeout=timeout)
        corrected_rows = {arm: raw_corrected[arm].pop("rows") for arm in _ARMS}
        corrected_ci: list[dict[str, Any]] = []
        for arm_a, arm_b in _PRIMARY_PAIRS:
            for label_ep, field, restrict in _ENDPOINTS:
                if field not in ("repair_rate", "false_fix_rate"):
                    continue  # detection 端点不受修正口径影响（ADR-0021 只改 repair/false_fix）
                ci = paired_diff_ci(corrected_rows[arm_a], corrected_rows[arm_b], field, restrict)
                ci["pair"] = f"{arm_a} vs {arm_b}"
                ci["label"] = _pair_label(arm_a, arm_b)
                ci["endpoint_label"] = f"{label_ep}（修正口径）"
                corrected_ci.append(ci)
        corrected = {"arms": raw_corrected, "paired_diff_ci": corrected_ci}

    return {
        "batch_meta": batch_meta,
        "arms": arms_data,
        "mde": mde_rows,
        "paired_diff_ci": ci_rows,
        "repair_structure": repair_structure,
        "corrected": corrected,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：默认在 R-P0-2 三种子合并数据上产出报告 + JSON（零 LLM）。"""
    parser = argparse.ArgumentParser(
        description="EMSE 统计补口：MDE/功效 + 比例型端点 bootstrap CI（零 LLM，只读工件）"
    )
    parser.add_argument(
        "--results-dir",
        default=str(_DEFAULT_RESULTS_DIR),
        help="批次 JSON 所在目录（默认 experiments/results/main_batch）",
    )
    parser.add_argument(
        "--out",
        default=str(_DEFAULT_OUT_DIR),
        help="输出目录（默认 experiments/results/emse_stats_2026-10-15；写入报告与同名 JSON）",
    )
    parser.add_argument(
        "--batches",
        default=None,
        help="逗号分隔的批次文件白名单（相对 --results-dir）；缺省 = R-P0-2 三批次（seed 42/43/44）",
    )
    parser.add_argument(
        "--corrected-repair",
        action="store_true",
        help="附加 ADR-0027 修正口径 repair/false_fix（逐行 pytest 重放，约 1–2 分钟，零 LLM）",
    )
    args = parser.parse_args(argv)

    results_dir = Path(args.results_dir)
    batch_files = resolve_batch_files(results_dir, args.batches)
    missing = [str(p) for p in batch_files if not p.is_file()]
    if missing:
        print(f"[emse-stats] 口径错误：批次文件缺失（不静默降级）：{missing}", file=sys.stderr)
        print(f"[emse-stats] 请检查 --results-dir={results_dir} 与 --batches", file=sys.stderr)
        return 2
    if not batch_files:
        print("[emse-stats] 口径错误：未解析到任何批次文件", file=sys.stderr)
        return 2

    data = analyze(results_dir, batch_files, corrected_repair=args.corrected_repair)
    command = (
        " ".join(["python -m experiments.emse_stats_report", *sys.argv[1:]])
        if argv is None
        else ("python -m experiments.emse_stats_report " + " ".join(argv)).strip()
    )
    report = build_report(results_dir, data["batch_meta"], data, command)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "emse_stats_report.md"
    json_path = out_dir / "emse_stats_report.json"
    report_path.write_text(report, encoding="utf-8")
    payload = {
        "generated_by": "experiments/emse_stats_report.py",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "caliber": {
            "results_dir": str(results_dir),
            "batches": data["batch_meta"],
            "arms": list(_ARMS),
            "primary_pairs": [f"{a} vs {b}" for a, b in _PRIMARY_PAIRS],
            "seed_handling": "task_id 前缀 s<seed>__（跨种子池化，与 statistical_analysis --pool-seeds 同口径）",
            "missing_value_policy": "端点字段 None 剔除（不计 0、不进分母）；配对要求两侧均可测",
            "alpha": _ALPHA,
            "power": _POWER,
            "bootstrap_n_resamples": _BOOTSTRAP_N_RESAMPLES,
            "bootstrap_seed": _BOOTSTRAP_SEED,
            "derived_evidence": True,
            "statistic_sources": [
                "scripts/tools/power_analysis.py（σ_d² 配对比例正态近似）",
                "experiments/emse_optimization.py（mde_paired_pp / power_at_delta / paired_contrast）",
                "experiments/statistical_analysis.py（bootstrap_paired_diff_ci / token_accounting_sanity）",
            ],
        },
        "arms": data["arms"],
        "mde": data["mde"],
        "paired_diff_ci": data["paired_diff_ci"],
        "repair_structure": data["repair_structure"],
        "corrected": _jsonable_corrected(data["corrected"]),
    }
    atomic_write_json(json_path, payload, indent=2, mode=0o644)

    _print_console_summary(data, report_path, json_path)
    return 0


def _jsonable_corrected(corrected: dict[str, Any] | None) -> dict[str, Any] | None:
    """修正口径结果的 JSON 化（`corrected_endpoints` 已剔除行级明细，此处原样透传）。"""
    return corrected


def _print_console_summary(data: dict[str, Any], report_path: Path, json_path: Path) -> None:
    """紧凑控制台摘要（口径 → MDE → CI 关键项 → 成本 → 产物路径）。"""
    meta = data["batch_meta"]
    print("=" * 78)
    print("EMSE 统计补口：MDE/功效 + 比例型端点 bootstrap CI（零 LLM，只读归档工件）")
    print("=" * 78)
    print(
        f"口径：{len(meta)} 批次（"
        + "、".join(f"{m['file']}#seed={m['seed']}" for m in meta)
        + f"）；臂 {'/'.join(_ARMS)}；种子前缀池化 s<seed>__"
    )
    print(f"端点缺失口径：None 剔除不计 0；bootstrap {_BOOTSTRAP_N_RESAMPLES} 次 / seed={_BOOTSTRAP_SEED}")
    print()
    print("① 主端点 detection_rate：配对结构 + MDE（α=0.05 双侧 / power=0.8）")
    for row in data["mde"]:
        if row["n_common"] == 0:
            print(f"   {row['pair']}: 零配对 → MDE 不可计算")
            continue
        print(
            f"   {row['pair']}: n={row['n_common']} n10/n01={row['n10']}/{row['n01']} n11={row['n11']} "
            f"δ={row['delta_pp']:+.2f}pp ψ={row['psi']:.4f}"
        )
        print(
            f"      MDE_σ(闭式)={_f(row['mde_sigma_closed_pp'], 4)}pp → 观测/MDE={_f(row['ratio_delta_over_mde_sigma'], 3)}"
            f"；MDE_ψ={_f(row['mde_psi_pp'], 4)}pp → 观测/MDE={_f(row['ratio_delta_over_mde_psi'], 3)}"
            f"；功效@观测δ(σ)={_f(row['power_at_delta_sigma'], 4)}"
            f"；达 80% 功效所需 n={row['required_n_sigma_observed_delta'] or '—'}"
        )
        for note in row["notes"]:
            print(f"      · {note}")
    print()
    print("② 比例型端点配对差 95% CI（仅列 CI 排除 0 或不可计算的项，全量见报告/JSON）")
    for row in data["paired_diff_ci"]:
        flag = row["excludes_zero"]
        if flag is None or flag:
            if row["ci_low_pp"] is None:
                print(
                    f"   {row['pair']} · {row['endpoint_label']}: n_pairs={row['n_pairs']} "
                    "→ CI 不可计算（n_pairs<2，不以 0 冒充）"
                )
                continue
            print(
                f"   {row['pair']} · {row['endpoint_label']}: n_pairs={row['n_pairs']} "
                f"差={_f(row['diff_pp'], 4)}pp CI=[{_f(row['ci_low_pp'], 4)}, {_f(row['ci_high_pp'], 4)}]"
            )
    print()
    print("③ 成本分布（tokens/任务，中位数 + IQR；只统计有正向记账行）")
    for arm, arm_data in data["arms"].items():
        cost = arm_data["cost"]
        if not cost["token_accounting"]["computable"]:
            print(f"   {arm}: NOT_COMPUTABLE（{cost['token_accounting']['reason']}）")
            continue
        print(
            f"   {arm}: median={_f(cost['median_tokens'], 1)} IQR=[{_f(cost['q1_tokens'], 1)}, "
            f"{_f(cost['q3_tokens'], 1)}] (IQR={_f(cost['iqr_tokens'], 1)}) mean={_f(cost['mean_tokens'], 1)}"
            + (
                (
                    f"；缓存命中 {cost['cache_hits']} 次、避免 {cost['cache_avoided_tokens']} tokens"
                    "（真实消耗口径，0 ≠ 免费）"
                )
                if cost.get("cache_hits") is not None
                else ("；缓存读数不可用（机制见报告 §4）" if "cache_hits" in cost else "")
            )
        )
    print()
    if data.get("corrected") is None:
        print("④ 修正口径 repair/false_fix：未现算（默认关闭）——见报告 §5 与 `make corrected-metrics`")
    else:
        print("④ 修正口径 repair/false_fix（--corrected-repair 现算）")
        for arm, cdata in data["corrected"]["arms"].items():
            print(
                f"   {arm}: verdict={cdata['verdict_dist']} 修正 repair(可重放)={_f(cdata['replayable_repair_pct'], 4)}% "
                f"修正 false_fix 边际={_f(cdata['false_fix_marginal']['rate_pct'], 4)}%"
            )
    print()
    print(f"报告：{report_path}")
    print(f"JSON：{json_path}")


if __name__ == "__main__":
    sys.exit(main())
