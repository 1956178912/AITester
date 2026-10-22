"""EMSE 投稿优化零 LLM 复算工具（纯 stdlib，2026-10-13 批次 → 本件为 10-14 重建版）。

背景（docs/design/layered_narrative.md §0）：
    EMSE（Empirical Software Engineering）投稿优化批次交付的**零 LLM 复算
    工具**——把 2026-10-13 批次定案的统计原语、口径聚合、贝叶斯因子、
    false_fix 双口径矩阵、mutation 相关性、swebench 事实提取、过红案例
    抽样等确定性分析函数固化为可导入的单一事实源，供
    `experiments/emse_optimization.py`（10-13 原始版，gitignored 后删除）
    的 40 例回归测试（`tests/test_emse_optimization.py`）与 EMSE 主报告
    §5.2"投稿前必须完成的五项修复"离线收口。

零 LLM 纪律：本模块只消费已归档 JSON 工件（results/ 下的批次 JSON +
swebench_20_summary.json），不触发任何 LLM 调用；全部统计量为纯函数
（McNemar 精确检验 / χ² 连续性校正 / MDE / 贝叶斯因子 / false_fix 双口径
/ Pearson / Spearman / 过红抽样），逐位与 10-13 批次定案值对齐
（测试锁定）。
"""

from __future__ import annotations

import json
import math
import random
import sys
import tempfile
from math import comb
from pathlib import Path
from typing import Any

# 项目根加入 sys.path（脚本可经 `python experiments/emse_optimization.py`
# 或测试导入两种方式运行）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments._row_pairing import latest_rows_by_task  # noqa: E402  （须在 sys.path 注入之后）

# swebench 工件路径（相对仓库根）
SWEBENCH_SUMMARY = _REPO_ROOT / "experiments" / "results" / "swebench_20_summary.json"
# 主批次工件目录（R-P0-2 口径来源）
MAIN_BATCH_DIR = _REPO_ROOT / "experiments" / "results" / "main_batch"

# BB（2026-10-21，F03 同型）：rc==0 判绿前的有效通过证据谓词
# （BA 轮建立于 _m1_metrics，此处为同族消费点复用，勿复制第二套判据）
from experiments._m1_metrics import _suite_has_effective_pass  # noqa: E402


# ─── McNemar 统计原语（对照 statistical_report 已定案值） ─────────────────
def mcnemar_exact_p(b: int, c: int) -> float:
    """McNemar 精确双侧 p 值（二项检验）。

    b = 仅处理组检出（n01），c = 仅对照组检出（n10）；
    p = 2 * Σ_{i=0}^{min(b,c)} C(n,i) * 0.5^n（n=b+c，双侧对称截断）。

    对照定案值（10-13 批次）：(2,3)→1.0、(8,5)→0.5811、(4,8)→0.3877、
    (0,0)→1.0、(113,0)→2×0.5^113≈1.93e-34。
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    one_sided = sum(comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(2.0 * one_sided, 1.0)


def mcnemar_chi2_cc(b: int, c: int) -> float:
    """McNemar χ² 连续性校正（|b−c|−1）²/(b+c)；|b−c|≤1 → 0.0。

    对照定案值（10-13 批次）：(12,80)→48.79、(37,3)→27.23、(113,0)→111.01、
    (2,3)→0.0。
    """
    n = b + c
    if n == 0:
        return 0.0
    diff = abs(b - c)
    if diff <= 1:
        return 0.0
    return (diff - 1) ** 2 / n


def paired_contrast(rows_x: list[dict], rows_y: list[dict], field: str = "detection_rate") -> dict[str, Any]:
    """配对对比（X vs Y，标准口径：共同可测子集，任一侧 None 不进分母）。

    δ = X − Y（第一臂 − 第二臂，标签方向）；
    返回 {n_pairs, only_first, only_second, both, neither, delta_pp}。

    N05（2026-10-22 第三方复审 P1）：必须**先按 task_id 选最新行、再排除 None**。
    历史实现"val 非 None 才 setdefault"→ 最新行的 None 不占位，旧批次的可测值
    顶替上来（构造例 n=3/δ=0pp，正确 n=2/δ=+50pp），同份报告的不同统计块会
    使用不同人群。选择逻辑委托共享原语 `latest_rows_by_task`（A07 单一事实源）。
    """
    latest_x = latest_rows_by_task(rows_x)
    latest_y = latest_rows_by_task(rows_y)
    map_x: dict[str, float] = {}
    map_y: dict[str, float] = {}
    for tid, row in latest_x.items():
        val = row.get(field)
        if val is not None:
            map_x[tid] = val
    for tid, row in latest_y.items():
        val = row.get(field)
        if val is not None:
            map_y[tid] = val
    common = set(map_x) & set(map_y)
    only_first = only_second = both = neither = 0
    for tid in common:
        x1 = 1 if map_x[tid] == 1.0 else 0
        y1 = 1 if map_y[tid] == 1.0 else 0
        if x1 and not y1:
            only_first += 1
        elif y1 and not x1:
            only_second += 1
        elif x1 and y1:
            both += 1
        else:
            neither += 1
    n = len(common)
    delta_pp = (only_first - only_second) / n * 100 if n else 0.0
    return {
        "n_pairs": n,
        "only_first": only_first,
        "only_second": only_second,
        "both": both,
        "neither": neither,
        "delta_pp": delta_pp,
    }


# ─── 功效分析原语（正态近似） ────────────────────────────────────────────
def mde_paired_pp(n_pairs: int, psi: float) -> float | None:
    """配对最小可检测效应（MDE，百分点；保守正态近似）。

    MDE = 100 * (z_{α/2} + z_β) * sqrt(ψ/(4n))（10-13 定案公式，ψ 为
    不一致率，未乘 (1−ψ) 项）；n=0 或 ψ=0 → None。
    对照定案值：n=35, ψ=5/35 → 8.95pp（= 100*(1.959964+0.841621)*
    sqrt((5/35)/(4*35))）。
    """
    if n_pairs <= 0 or psi <= 0:
        return None
    z_alpha = 1.959964  # 双侧 0.05
    z_beta = 0.841621  # 80% 功效
    return 100.0 * (z_alpha + z_beta) * math.sqrt(psi / (4 * n_pairs))


def required_pairs(delta_pp: float, psi: float) -> int | None:
    """检出 delta_pp（百分点）的 80% 功效所需配对数（向上取整）。

    n = (z_{α/2}+z_β)² * ψ / (4*(δ/100)²)（与 mde_paired_pp 同口径，
    未乘 (1−ψ) 项）；delta≤0 或 ψ≤0 → None。
    对照定案值：δ=8pp, ψ=5/35 → 44。
    """
    if delta_pp <= 0 or psi <= 0:
        return None
    z_alpha = 1.959964
    z_beta = 0.841621
    n = ((z_alpha + z_beta) ** 2) * psi / (4 * ((delta_pp / 100) ** 2))
    return math.ceil(n)


def power_at_delta(delta_pp: float, n_pairs: int, psi: float) -> float | None:
    """n_pairs 配对下检出 delta_pp 的统计功效（正态近似）。

    power = Φ((|δ|/100)/sqrt(ψ/(4n)) − z_{α/2})（与 mde/required_pairs
    同口径，未乘 (1−ψ) 项）；δ<0 或 n≤0 或 ψ≤0 → None。
    对照定案值：δ=8pp, n=35, ψ=5/35 → 0.7068。
    """
    if n_pairs <= 0 or psi <= 0 or delta_pp < 0:
        return None
    z_alpha = 1.959964
    se = math.sqrt(psi / (4 * n_pairs))
    if se == 0:
        return None
    z = abs(delta_pp) / 100 / se - z_alpha
    # 标准正态 CDF（erf 近似）
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ─── 贝叶斯因子（McNemar 二项模型，Jeffreys 先验 Beta(0.5,0.5)） ──────────
def _log_beta_func(x: float, y: float) -> float:
    from math import lgamma

    return lgamma(x) + lgamma(y) - lgamma(x + y)


def bayes_factor_discordant(b: int, c: int) -> dict[str, Any]:
    """McNemar 不一致对 (b,c) 的贝叶斯因子 BF10（Jeffreys 先验）。

    H0: θ=0.5（无差异）vs H1: θ≠0.5（Beta(0.5,0.5) 先验）；
    返回 {bf10_jeffreys, verdict}；n=0 → {None, "不可判定"}。

    对照定案值（10-13 批次数值积分对照）：
    (2,3)→0.375、(8,5)→0.3076、(4,8)→0.4443、(50,50)→0.0796、(20,2)→853.6。
    """
    n = b + c
    if n == 0:
        return {"bf10_jeffreys": None, "verdict": "不可判定（无不一致对）"}
    # H1: P(data|Jeffreys) = C(n,b) * B(b+0.5, c+0.5) / B(0.5, 0.5)
    log_p_h1 = math.log(comb(n, b)) + _log_beta_func(b + 0.5, c + 0.5) - _log_beta_func(0.5, 0.5)
    # H0: P(data|θ=0.5) = C(n,b) * 0.5^n
    log_p_h0 = math.log(comb(n, b)) + n * math.log(0.5)
    bf10 = math.exp(log_p_h1 - log_p_h0)
    # 判读（Jeffreys 1961 经典区间）
    if bf10 >= 10:
        verdict = "强支持 H1（效应存在）"
    elif bf10 >= 3:
        verdict = "支持 H1（效应存在）"
    elif bf10 <= 0.1:
        verdict = "强支持 H0（无差异）"
    elif bf10 <= 1 / 3:
        verdict = "支持 H0（无差异）"
    else:
        verdict = "证据不足（不可判定）"
    return {"bf10_jeffreys": round(bf10, 6), "verdict": verdict}


# ─── false_fix 双口径矩阵 ────────────────────────────────────────────────
def false_fix_caliber(rows: list[dict]) -> dict[str, Any]:
    """false_fix 双口径（边际 / 条件）。

    边际 = ff=1 行数 / **该指标可测的行数**；
    条件 = ff=1 行数 / passed ∧ 该指标可测的行数；
    无可测行 → marginal/conditional 均 None（不假报 0）。

    分母口径修复（2026-10-15，M3 审计发现）：原实现用 `passed is not None`
    作为"可测"判据，得到 R-P0-2 aitester 分母 261 → 边际 54.79%，与历史定案值
    59.58%（分母 240）不一致。根因是**分母必须是"被度量指标本身可测"的行**：
    R-P0-2 有 21 行 `error_category='error'`（M10 第 0 轮整任务死亡，iterations=0、
    patch_evidence_level=None）→ `false_fix_rate is None`、`repair_rate is None`，
    这些行**不能进入 false-fix 率的分母**（它们既不是"无假修复"，也不是"有假修复"）。
    旧口径与本修复在 R-P0-2 上给出同一答案的巧合来自 `false_fix_rate is None`
    ⟺ `detection_rate is None`（本例 21 行重叠），因此必须在代码中显式表达，
    不能依赖巧合。两类分母同时输出：`n_passed_measurable`（passed 且指标可测）
    与 `n_passed`（仅 passed 为 True），供读者核对差异。
    """
    n_rows = len(rows)
    n_measurable = sum(1 for r in rows if r.get("false_fix_rate") is not None)
    n_ff1 = sum(1 for r in rows if r.get("false_fix_rate") == 1.0)
    n_passed = sum(1 for r in rows if r.get("passed") is True)
    n_passed_measurable = sum(1 for r in rows if r.get("passed") is True and r.get("false_fix_rate") is not None)
    n_passed_but_unmeasurable = sum(1 for r in rows if r.get("passed") is not None and r.get("false_fix_rate") is None)
    marginal = 100.0 * n_ff1 / n_measurable if n_measurable else None
    conditional = 100.0 * n_ff1 / n_passed_measurable if n_passed_measurable else None
    return {
        "n_rows": n_rows,
        "n_passed": n_passed,
        "n_measurable": n_measurable,
        "n_ff1": n_ff1,
        "n_passed_measurable": n_passed_measurable,
        "n_passed_but_unmeasurable": n_passed_but_unmeasurable,
        "marginal_pct": round(marginal, 2) if marginal is not None else None,
        "conditional_pct": round(conditional, 2) if conditional is not None else None,
    }


def _load_main_batch_rows() -> dict[str, list[dict]]:
    """加载 R-P0-2 三种子主批次行（aitester 等臂的逐任务行）。

    口径（2026-10-15 修复）：R-P0-2 主批次 = `benchmark_synthetic_20261006_1*.json`
    三种子批次（seed 42/43/44，各 87 行 → **261 行/臂**），即
    `statistical_report_3seed_pooled.md` 与 `BASELINE.yaml` `benchmark` 节所指的
    当前对外口径。

    缺陷史（本函数第一版）：过滤条件为 `timestamp > "2026-10-02"` 即整批跳过，
    随后按 docstring 以为"主批次 = 2026-10-01 首个基准"，而 R-P0-2 三种子批次的
    timestamp 是 2026-10-06 → **自动复算分支永不触发**，矩阵长期以
    `source="10-13_caliber_fallback"` 返回硬编码定案值（数值恰好相同，故无人察觉）。
    今日由 M3 审计发现；修复后 R-P0-2 行可从仓内工件实时复算，回退分支仅在
    工件真缺席时生效。
    """
    populations: dict[str, list[dict]] = {}
    for json_path in sorted(MAIN_BATCH_DIR.glob("benchmark_synthetic_20261006_1*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for arm_key, arm_data in (data.get("results") or {}).items():
            details = arm_data.get("details") if isinstance(arm_data, dict) else None
            if not isinstance(details, list):
                continue
            populations.setdefault(f"{arm_key}", []).extend(details)
    return populations


def build_false_fix_matrix() -> dict[str, Any]:
    """false_fix 口径矩阵（主批次工件 → R-P0-2 / ADR-0027 双口径定案值）。

    对照定案值（10-13 批次）：R-P0-2 aitester n=261/143/240/143 →
    marginal 59.58% / conditional 100%；ADR-0027 corrected 380/436 →
    conditional 87.16%。
    """
    populations = _load_main_batch_rows()
    out_populations: dict[str, dict[str, Any]] = {}
    # R-P0-2 口径（主批次 aitester，10-13 定案 n=261）：主批次 JSON 工件
    # 已被清理（gitignored 目录删除）时回退 10-13 定案值（保守口径：
    # 数字来源标注为"10-13 定案"，不静默改变数值；工件在场且完整时
    # 才用工件复算）。
    rp02_rows = populations.get("aitester", [])
    if len(rp02_rows) == 261:
        out_populations["RP02_aitester"] = false_fix_caliber(rp02_rows)
        out_populations["RP02_aitester"]["source"] = "main_batch_artifact"
    else:
        # 10-13 定案值（R-P0-2 aitester 主批次，n=261）
        out_populations["RP02_aitester"] = {
            "n_rows": 261,
            "n_passed": 143,
            "n_measurable": 240,
            "n_ff1": 143,
            "n_passed_measurable": 143,
            "marginal_pct": 59.58,
            "conditional_pct": 100.0,
            "source": "10-13_caliber_fallback",
        }
    # ADR-0027 修正口径（380/436 定案，来自 corrected_metrics 重放）
    out_populations["ADR0027_corrected"] = {
        "n_rows": 436,
        "n_passed": 436,
        "n_measurable": 436,
        "n_ff1": 380,
        "n_passed_measurable": 436,
        "marginal_pct": round(100.0 * 380 / 436, 2),
        "conditional_pct": 87.16,
    }
    return {"populations": out_populations}


# ─── 相关性（Pearson / Spearman，纯 stdlib） ─────────────────────────────
def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson 相关系数（n<2 或零方差 → None）。"""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman 秩相关（含 ties 平均秩；n≤2 或零方差 → None）。

    退化纪律（10-13 定案）：n=2 的秩相关恒为 ±1.0 或 0.0（只有两种
    排序），无判别力——按 None 保守口径（与 pearson n<2 同族扩展，
    防"2 点拟合出虚假相关"的审稿人质疑）。
    """
    n = len(xs)
    if n <= 2 or n != len(ys):
        return None
    if len(set(xs)) == 1 or len(set(ys)) == 1:
        return None

    def _ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg_rank = (i + 1 + j + 1) / 2.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    rx = _ranks(list(xs))
    ry = _ranks(list(ys))
    return pearson(rx, ry)


def mutation_correlation(rows: list[dict]) -> dict[str, Any]:
    """mutation 族 × detection 相关性（Pearson/Spearman + 分层均值）。

    EMSE 批次（2026-10-15）修复：此前本函数 docstring 声称计算
    Pearson/Spearman，**函数体实际只返回计数与检出=1 时的变异均值**——
    论文若据此声称"detection_rate 与 mutation score 已交叉验证"即为
    不实陈述（审稿人 1/3 的构念效度质疑点）。现补齐真实系数。

    返回 {n_det_measurable, detection_rate_pct, mutation_score:{...},
    mutants_total_distribution:{...}}；mutation_score 子字典新增
    pearson / spearman / spearman_reason（退化原因）与分组均值。

    **已知统计局限（必须随数字一并披露）**：detection 在合成主批次为
    强不平衡二值（aitester ≈ 15.8% 检出），与连续 mutation_score 的
    Pearson 在低基率下对少数类不敏感；Spearman 含大量 ties。故本表
    只作**收敛效度（convergent validity）的辅助证据**，不得单独作为
    "detection_rate 是有效质量代理"的证据；解读须与分层均值（检出=1
    组 vs 检出=0 组）并列。
    """
    det = [r.get("detection_rate") for r in rows if r.get("detection_rate") is not None]
    n_det = len(det)
    det_pct = 100.0 * sum(1 for d in det if d == 1.0) / n_det if n_det else None
    mut_pairs = [
        (r["detection_rate"], r.get("mutation_score"))
        for r in rows
        if r.get("detection_rate") is not None and r.get("mutation_score") is not None
    ]
    mean_when_det1 = None
    mean_when_det0 = None
    if mut_pairs:
        det1_scores = [s for d, s in mut_pairs if d == 1.0]
        det0_scores = [s for d, s in mut_pairs if d != 1.0]
        if det1_scores:
            mean_when_det1 = sum(det1_scores) / len(det1_scores)
        if det0_scores:
            mean_when_det0 = sum(det0_scores) / len(det0_scores)
    # 真实相关系数（仅在有足够配对且双方非零方差时给出，否则 None 保守降级）
    dets = [d for d, _s in mut_pairs]
    muts = [s for _d, s in mut_pairs]
    r_pearson = pearson(dets, muts) if len(mut_pairs) >= 2 else None
    r_spearman = spearman(dets, muts) if len(mut_pairs) >= 3 else None
    spearman_reason = None
    if r_spearman is None:
        if len(mut_pairs) < 3:
            spearman_reason = "n_pairs_lt_3"
        elif len(set(dets)) == 1:
            spearman_reason = "detection_zero_variance"
        elif len(set(muts)) == 1:
            spearman_reason = "mutation_zero_variance"
    mt_dist = [r.get("mutants_total") for r in rows if r.get("mutants_total") is not None]
    return {
        "n_det_measurable": n_det,
        "detection_rate_pct": round(det_pct, 4) if det_pct is not None else None,
        "mutation_score": {
            "n_pairs": len(mut_pairs),
            "mean_when_detection_1": mean_when_det1,
            "mean_when_detection_0": mean_when_det0,
            "mean_delta_det1_minus_det0": (
                mean_when_det1 - mean_when_det0 if mean_when_det1 is not None and mean_when_det0 is not None else None
            ),
            "pearson": r_pearson,
            "spearman": r_spearman,
            "spearman_reason": spearman_reason,
            "interpretation_caveat": (
                "convergent-validity auxiliary evidence only: detection is a "
                "strongly imbalanced binary at this base rate, and ties dominate "
                "the mutation ranks; read alongside the stratified means, never alone"
            ),
        },
        "mutants_total_distribution": {
            "n": len(mt_dist),
            "max": max(mt_dist) if mt_dist else None,
            "min": min(mt_dist) if mt_dist else None,
        },
    }


# ─── 过红案例抽样与 fixed 上复跑 ─────────────────────────────────────────
def over_red_cases(rows: list[tuple[str, dict]], k: int = 5, seed: int = 42) -> list[dict[str, Any]]:
    """过红案例确定性抽样（固定 seed；同 task 三种子行不串行）。

    rows = [(source_file, row_dict), ...]；过滤
    detection_first_status=="red_not_repaired" 的行；seed 确定性抽 k 例；
    返回 [{task_id, source_file, test_head, detection_first_status}]。
    """
    eligible = [(src, row) for src, row in rows if row.get("detection_first_status") == "red_not_repaired"]
    if not eligible:
        return []
    rng = random.Random(seed)
    sampled = rng.sample(eligible, min(k, len(eligible)))
    out = []
    for src, row in sampled:
        test_head = (row.get("generated_test") or "")[:200]
        out.append(
            {
                "task_id": row.get("task_id"),
                "source_file": src,
                "test_head": test_head,
                "detection_first_status": row.get("detection_first_status"),
            }
        )
    return out


def _rerun_on_fixed(task_id: str, fixed_code: str, test_code: str) -> dict[str, Any]:
    """在 gold fixed 上真实复跑（零 LLM，子进程 pytest）并记录 rc/模式。

    BB（2026-10-21，F03 同型）：``rc == 0`` 不等于套件真的跑过——全
    skip / xfail / deselect 的 pytest 运行同样 rc==0 且摘要 ``passed==0``。
    此类运行记 ``passes_on_fixed=None`` + ``P5_no_effective_pass_on_fixed``
    （不可测，既不算"在 fixed 上通过"也不算失败签名），与 BA 轮
    ``_suite_has_effective_pass`` 同口径。
    """
    with tempfile.TemporaryDirectory(prefix="emse_overred_") as tmp:
        tmp = Path(tmp)
        module_name = task_id.rsplit("__", 1)[-1] if "__" in task_id else "task_m"
        (tmp / f"{module_name}.py").write_text(fixed_code, encoding="utf-8")
        test_file = tmp / f"test_{module_name}.py"
        test_file.write_text(test_code, encoding="utf-8")
        from src.utils.process_utils import run_with_timeout

        proc = run_with_timeout(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        rc = proc.returncode
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if rc == 0 and not _suite_has_effective_pass(output):
            passes: bool | None = None
            mode = "P5_no_effective_pass_on_fixed"
        else:
            passes = rc == 0
            mode = "P4_passes_on_fixed" if passes else classify_failure_signature(output)
        return {
            "task_id": task_id,
            "status": "ok" if proc is not None else "error",
            "rc": rc,
            "passes_on_fixed": passes,
            "failure_mode": mode,
        }


def over_red_failure_modes(cases: list[dict], rows: list[tuple[str, dict]]) -> list[dict[str, Any]]:
    """过红案例在 fixed 上的复跑失败模式分类（material_missing / P1-P4）。"""
    row_map: dict[str, dict] = {}
    for _src, row in rows:
        tid = row.get("task_id")
        if tid:
            row_map.setdefault(tid, row)
    out = []
    for case in cases:
        tid = case.get("task_id")
        row = row_map.get(tid)
        if row is None or not (row.get("task_metadata") or {}).get("fixed"):
            out.append(
                {
                    "task_id": tid,
                    "status": "material_missing",
                    "source_file": case.get("source_file"),
                }
            )
            continue
        fixed = row["task_metadata"]["fixed"]
        test_code = row.get("generated_test") or ""
        result = _rerun_on_fixed(tid, fixed, test_code)
        result["source_file"] = case.get("source_file")
        out.append(result)
    return out


def classify_failure_signature(text: str) -> str:
    """失败签名 → 模式分类（P3 > P2 > P1 优先序；其余 P0_unclassified）。"""
    t = text.lower()
    if "attributeerror" in t and "has no attribute" in t:
        return "P3_implementation_coupling"
    if "valueerror: invalid literal" in t or "cannot parse" in t:
        return "P2_over_specification"
    if "assertionerror" in t and "assert" in t:
        return "P1_bug_coupled_expectation"
    return "P0_unclassified"


# ─── swebench 基础设施事实提取 ───────────────────────────────────────────
def swebench_infra_facts(summary_path: Path | None = None) -> dict[str, Any]:
    """swebench_20_summary.json 的结构化事实提取（缺文件 → available=False）。

    字段映射（10-13 定案工件 schema）：total_tasks_attempted / tasks_completed
    / tasks_failed / tasks_timeout；notes 字段缺失时从 raw 字段（429 /
    infrastructure_failure）派生。
    """
    path = summary_path or SWEBENCH_SUMMARY
    if not path.is_file():
        return {"available": False, "note": f"swebench summary not found: {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    total = data.get("total_tasks", data.get("total_tasks_attempted", 0))
    completed = data.get("tasks_completed", data.get("completed", 0))
    failed = data.get("tasks_failed", data.get("failed", 0))
    timeout = data.get("tasks_timeout", data.get("timeout", 0))
    # notes 字段缺失时从 issues / raw_notes 字段派生（10-13 工件 schema：
    # issues 列表含 429 rate limit 字符串；raw_notes 为备选标量字段）
    notes = data.get("notes", "")
    if not notes:
        issues = data.get("issues") or []
        if isinstance(issues, list):
            notes = "; ".join(str(i) for i in issues)
        elif issues:
            notes = str(issues)
        if not notes:
            notes = str(data.get("raw_notes") or "")
    # EMSE 批次（2026-10-15）：把"基础设施失败 ≠ 能力结论"从**字符串包含**
    # 判据升级为**结构化判据 + 结构化字段**。
    # 修复动机（审稿人 2/3 复核点）：旧判据 `timeout > completed + failed`
    # 在超时占多数时恒真、且依赖 notes 里的 "429" 字面量；且结论只落在
    # `corrected_statement` 文本里，结果行仍以 pass_rate 为一等指标。
    attempted = total or (completed + failed + timeout)
    non_capability = completed + failed + timeout
    timeout_ratio = (timeout / non_capability) if non_capability else None
    # 限流信号优先取**结构化嵌套字段** results_summary.notes（单次运行的权威
    # 定性说明），其次 issues/notes 自由文本——避免结论只依赖一个大字符串。
    run_notes = str((data.get("results_summary") or {}).get("notes") or "")
    issues_raw = data.get("issues") or []
    issues_text = "; ".join(str(i) for i in issues_raw) if isinstance(issues_raw, list) else str(issues_raw)
    # EMSE 批次（2026-10-15，一致性修复）：**计数口径必须覆盖全部结构化文本源**。
    # 缺陷（审稿人 2/3 复核点）：旧实现 `notes.count("429") + run_notes.count("429")`
    # 在 `notes` 已由 issues 派生的场景下**不会重复计入 issues 之外的文本**，
    # 且当 notes 非空时 issues 完全不参与计数——真实工件（swebench_20_summary.json）
    # 的 issues 列表含 5 条限流/端点条目，而 notes 与 run_notes 各含 1 次 "429"，
    # 旧口径输出 2，与散文叙述"7 次完成全部因 429 失败"不一致（曾构成
    # "披露工件 vs README 表述"数字分裂）。
    # 新口径：分源计数 + 去重后的并集文本计数，并在返回体给出 breakdown 供对账。
    signal_breakdown = {
        "run_notes": run_notes.count("429"),
        "notes": notes.count("429"),
        "issues": issues_text.count("429"),
        "issues_rate_limit_entries": sum(
            1
            for i in (issues_raw if isinstance(issues_raw, list) else [])
            if "rate limit" in str(i).lower() or "429" in str(i)
        ),
    }
    # 去重语义：notes 可能由 issues 派生（见上方 fallback），同一文本只计一次，
    # 否则"分源之和"会重复计数。breakdown 为**诊断用**，总数以去重并集为准。
    distinct_sources = {t for t in (run_notes, notes, issues_text) if t}
    combined_text = " ".join(sorted(distinct_sources))
    rate_limit_signals = combined_text.count("429")
    rate_limited = rate_limit_signals > 0 or "rate limit" in combined_text.lower()
    # 有效能力结论的必要条件：存在"真实执行完成"的样本，且基础设施故障不占主导。
    # 本工件（20 次尝试：7 完成 / 3 失败 / 10 超时，7/7 完成者均因 429 失败）
    # 不满足该条件 → 明确输出"无有效能力结论"，且**不得**引用其 pass_rate。
    infra_failure = rate_limited or (timeout_ratio is not None and timeout_ratio > 0.5)
    capability_conclusion = "none_valid_infrastructure_failure" if infra_failure else "valid_conclusion_available"
    corrected = "基础设施故障（429 限流 / 超时）主导，非模型能力信号" if infra_failure else ""
    return {
        "available": True,
        "total_tasks_attempted": attempted,
        "tasks_completed": completed,
        "tasks_failed": failed,
        "tasks_timeout": timeout,
        "timeout_ratio": timeout_ratio,
        "rate_limit_signals": rate_limit_signals,
        "rate_limit_signal_breakdown": signal_breakdown,
        "capability_conclusion": capability_conclusion,
        "pass_rate_must_not_be_quoted": infra_failure,
        "notes": notes,
        "corrected_statement": corrected,
    }


def swebench_disclosure_report() -> str:
    """SWE-bench Lite 基础设施失败披露（四分账 + 无有效能力结论）。

    论文用途：真实基准失败必须**如实分账**并明确标注"无有效能力结论"
    （不得作为阴性证据，也不得把 pass_rate 画进对比图）。
    """
    facts = swebench_infra_facts()
    if not facts.get("available"):
        return "# SWE-bench Lite 披露\n\n工件缺失，无法生成披露表。\n"
    attempted = facts["total_tasks_attempted"]
    completed = facts["tasks_completed"]
    failed = facts["tasks_failed"]
    timeout = facts["tasks_timeout"]
    conclusion = facts["capability_conclusion"]
    lines = [
        "# SWE-bench Lite 基础设施失败披露（EMSE 批次 2026-10-15）",
        "",
        f"- 尝试任务数：**{attempted}**",
        f"- 完成：**{completed}**；任务级失败：**{failed}**；超时：**{timeout}**",
        f"- 超时占比：{facts['timeout_ratio']:.2%}" if facts["timeout_ratio"] is not None else "- 超时占比：—",
        f"- 限流（429）信号计数：**{facts['rate_limit_signals']}**",
        f"- 信号分源（对账用）：`{facts['rate_limit_signal_breakdown']}`"
        "——计数口径为**全结构化文本源（run_notes / notes / issues）去重后统计 `429` 字面量**；"
        "单源计数会低估（旧口径仅 2，曾与叙述分裂）。",
        f"- **能力结论：`{conclusion}`**",
        "",
        "## 结论性陈述（须逐字进入论文 Limitations）",
        "",
        f"> {facts['corrected_statement'] or '（无基础设施故障信号）'}",
        "",
        "## 引用纪律",
        "",
        f"- 本数据集的 `pass_rate` **{'不得引用' if facts['pass_rate_must_not_be_quoted'] else '可引用（无基础设施故障信号）'}**"
        "——它度量的是配额瓶颈，不是能力。",
        "- 该数据集**不得进入任何跨方法能力对比图/表**；只能出现在 Limitations 与复跑清单中。",
        "- 复跑前置：客户端已具备 429 退避（`src/agents/base_agent.py` 按 `Retry-After` 退避 + 跨模型 failover），"
        "但下载器/跑批入口无配额预算控制——重跑前需先补配额闸。",
        "",
    ]
    return "\n".join(lines)


# ─── A/B 配对分析（--ab-pair 入口，D1 QuixBugs 复算用） ──────────────────
def ab_pair_analysis(path_a: str, path_b: str, arm_a: str, arm_b: str) -> dict[str, Any]:
    """两臂批次 JSON 的配对分析（δ = 第一臂 − 第二臂 + MDE + 贝叶斯）。

    臂缺失 / 无有效配对 → delta_pp=None + marginal rate_pct=None（不假报 0）。
    """

    def _load(path_str: str, arm: str) -> list[dict]:
        p = Path(path_str)
        if not p.is_file():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        details = (data.get("results") or {}).get(arm, {}).get("details", [])
        return details if isinstance(details, list) else []

    rows_a = _load(path_a, arm_a)
    rows_b = _load(path_b, arm_b)
    n_pairs = 0
    if rows_a and rows_b:
        contrast = paired_contrast(rows_a, rows_b)
        n_pairs = contrast["n_pairs"]
        psi = (contrast["only_first"] + contrast["only_second"]) / n_pairs if n_pairs else 0.0
        mde = mde_paired_pp(n_pairs, psi)
        bf = bayes_factor_discordant(contrast["only_first"], contrast["only_second"])
        hits_a = sum(1 for r in rows_a if r.get("detection_rate") == 1.0)
        hits_b = sum(1 for r in rows_b if r.get("detection_rate") == 1.0)
        return {
            "n_pairs": n_pairs,
            "only_first": contrast["only_first"],
            "only_second": contrast["only_second"],
            "both": contrast["both"],
            "neither": contrast["neither"],
            "delta_pp": contrast["delta_pp"],
            "marginal_first": {
                "n": n_pairs,
                "hits": hits_a,
                "rate_pct": round(100.0 * hits_a / n_pairs, 2) if n_pairs else None,
            },
            "marginal_second": {
                "n": n_pairs,
                "hits": hits_b,
                "rate_pct": round(100.0 * hits_b / n_pairs, 2) if n_pairs else None,
            },
            "mde_pp_80power": mde,
            "bayes": bf,
        }
    # 臂缺失 / 零配对：保守 None 口径
    return {
        "n_pairs": 0,
        "only_first": 0,
        "only_second": 0,
        "both": 0,
        "neither": 0,
        "delta_pp": None,
        "marginal_first": {"n": 0, "hits": 0, "rate_pct": None},
        "marginal_second": {"n": 0, "hits": 0, "rate_pct": None},
        "mde_pp_80power": None,
        "bayes": {"bf10_jeffreys": None, "verdict": "不可判定（无配对）"},
    }


def _load_arm_rows(paths: list[str], arm: str) -> tuple[list[dict], list[str]]:
    """读取一个或多个批次 JSON，取 results[arm].details[] 行（缺失 → 跳过）。

    与 repair_replay/_m1_metrics 同族口径：只读已归档工件，不触发 LLM。
    返回 (rows, 参与的文件名列表) —— 文件名随报告输出，保证口径可追溯
    （避免"不知混了哪些批次"的口径漂移）。
    """
    rows: list[dict] = []
    used: list[str] = []
    for p in paths:
        path = Path(p)
        files = sorted(path.glob("benchmark_*.json")) if path.is_dir() else [path]
        for f in files:
            if not f.is_file():
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            arm_data = (data.get("results") or {}).get(arm) or {}
            details = arm_data.get("details") or []
            rows.extend(r for r in details if isinstance(r, dict))
            used.append(f.name)
    return rows, used


# 饱和阈值：与 experiments/target_quality_replay.py 既有纪律同口径
_MUTATION_SATURATION = 0.98


def mutation_correlation_report(
    paths: list[str], arms: tuple[str, ...] = ("aitester", "plain_llm", "plain_llm_df")
) -> str:
    """mutation × detection 交叉验证 Markdown 报告（EMSE 构念效度辅助证据）。

    收敛效度证据：若 detection_rate 与 mutation_score 同向，则"检出率"与
    "变异检出"在方向上一致；**但不构成"detection_rate 是通用质量代理"的
    证明**——合成集变异体强度与被测任务模板耦合（饱和时该指标无鉴别力，
    遵循 target_quality_replay 的诚实纪律）。本报告只呈现数字与局限。
    """
    lines = [
        "# mutation × detection 交叉验证（EMSE 构念效度辅助证据，零 LLM）",
        "",
        "来源：已归档批次 JSON 的 `results[arm].details[]`；detection_rate 与",
        "mutation_score 均非 None 的行才进配对（None = 不可测，遵循保守口径，",
        "不计为 0）。变异得分饱和阈值 0.98（与 `experiments/target_quality_replay.py`",
        "同口径）——饱和即标注**无鉴别力**，不得作为测试有效性证据。",
        "",
        "**解读纪律**：detection 为强不平衡二值（合成主批次检出率低），与连续",
        "mutation_score 的 Pearson 对少数类不敏感、Spearman 受 ties 支配；本表",
        "**只作收敛效度的辅助证据**，须与分层均值并列阅读，不得单独用于主张",
        "detection_rate 是有效质量代理。",
        "",
        "| 臂 | 批次文件数 | 配对 n | detection 可测 n | detection 率 | mean(MS\\|det=1) | mean(MS\\|det=0) | Δ均值 | Pearson | Spearman | 饱和判定 |",
        "|----|-----------|--------|------------------|--------------|------------------|------------------|--------|---------|----------|----------|",
    ]
    for arm in arms:
        rows, used = _load_arm_rows(paths, arm)
        if not rows:
            lines.append(f"| {arm} | 0 | 0 | 0 | — | — | — | — | — | — | 无数据 |")
            continue
        out = mutation_correlation(rows)
        ms = out["mutation_score"]

        def _f(v: float | None, nd: int = 4) -> str:
            return "—" if v is None else f"{v:.{nd}f}"

        all_scores = [r.get("mutation_score") for r in rows if r.get("mutation_score") is not None]
        mean_all = sum(all_scores) / len(all_scores) if all_scores else None
        saturation = (
            "**无鉴别力（饱和）**"
            if mean_all is not None and mean_all >= _MUTATION_SATURATION
            else ("近饱和，谨慎解读" if mean_all is not None and mean_all >= 0.95 else "可鉴别")
        )
        lines.append(
            f"| {arm} | {len(used)} | {ms['n_pairs']} | {out['n_det_measurable']} | "
            f"{_f(out['detection_rate_pct'], 2)}% | {_f(ms['mean_when_detection_1'])} | "
            f"{_f(ms['mean_when_detection_0'])} | {_f(ms['mean_delta_det1_minus_det0'])} | "
            f"{_f(ms['pearson'])} | {_f(ms['spearman'])} | {saturation} |"
        )
    lines += [
        "",
        "退化与不可测说明：Spearman 在 n<3 或任一侧零方差时记 None（不臆造）；",
        "退化原因字符串由 `experiments/emse_optimization.py::mutation_correlation()` 的返回体",
        "键 `mutation_score.spearman_reason` 承载（本报告为派生物，不额外落盘 JSON）。",
        "",
        "**方向性发现（须与上表同读，不得单独引用）**：Δ均值（det=1 组减 det=0 组）",
        "为正表示「检出组变异得分更高」（收敛），为负表示**不一致**——负号出现时须",
        "如实披露，不得以 Pearson 的弱正号掩盖分层方向。",
        "",
    ]
    return "\n".join(lines)


def _write_report(path_text: str, text: str) -> None:
    """写报告文件：收尾统一为**恰好一个**换行。

    报告正文（lines 列表经 join）末尾已含一个 ``\\n``；若调用方再 ``+ "\\n"``
    会引入 EOF 空行（``git diff --check`` 报警 + 与同目录其他报告工件口径
    不一，2026-10-16 修复）。本助手对两者统一收尾。
    """
    Path(path_text).write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：`--ab-pair a.json b.json arm_a arm_b`、`--mutation-correlation` 或默认 false_fix 矩阵。"""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ab-pair", nargs=4, metavar=("A", "B", "ARM_A", "ARM_B"), help="两臂批次 JSON 配对分析")
    ap.add_argument(
        "--mutation-correlation",
        nargs="+",
        metavar="PATH",
        help="mutation × detection 交叉验证（批次 JSON 或目录，零 LLM）",
    )
    ap.add_argument(
        "--swebench-disclosure",
        action="store_true",
        help="输出 SWE-bench Lite 基础设施失败披露（四分账 + 无有效能力结论）",
    )
    ap.add_argument("--out", help="报告写盘路径（缺省 stdout）")
    args = ap.parse_args(argv)
    if args.swebench_disclosure:
        report = swebench_disclosure_report()
        if args.out:
            _write_report(args.out, report)
            print(f"written: {args.out}")
        else:
            print(report)
    elif args.mutation_correlation:
        report = mutation_correlation_report(list(args.mutation_correlation))
        if args.out:
            _write_report(args.out, report)
            print(f"written: {args.out}")
        else:
            print(report)
    elif args.ab_pair:
        path_a, path_b, arm_a, arm_b = args.ab_pair
        print(json.dumps(ab_pair_analysis(path_a, path_b, arm_a, arm_b), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(build_false_fix_matrix(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
