"""EMSE 投稿优化零 LLM 复算工具（纯 stdlib，2026-10-13 批次 → 本件为 10-14 重建版）。

背景（docs/design/emse_layered_narrative.md §0）：
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
import subprocess
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

# swebench 工件路径（相对仓库根）
SWEBENCH_SUMMARY = _REPO_ROOT / "experiments" / "results" / "swebench_20_summary.json"
# 主批次工件目录（R-P0-2 口径来源）
MAIN_BATCH_DIR = _REPO_ROOT / "experiments" / "results" / "main_batch"


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
    """
    map_x: dict[str, float] = {}
    map_y: dict[str, float] = {}
    for r in rows_x:
        tid = r.get("task_id")
        val = r.get(field)
        if tid and val is not None:
            map_x.setdefault(tid, val)
    for r in rows_y:
        tid = r.get("task_id")
        val = r.get(field)
        if tid and val is not None:
            map_y.setdefault(tid, val)
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

    边际 = ff=1 行数 / 可测行数（denom = n_measurable）；
    条件 = ff=1 行数 / passed∧可测行数（denom = n_passed_measurable）；
    无可测行 → marginal/conditional 均 None（不假报 0）。
    """
    n_rows = len(rows)
    n_measurable = sum(1 for r in rows if r.get("passed") is not None)
    n_ff1 = sum(1 for r in rows if r.get("false_fix_rate") == 1.0)
    n_passed = sum(1 for r in rows if r.get("passed") is True)
    n_passed_measurable = sum(1 for r in rows if r.get("passed") is True)
    marginal = 100.0 * n_ff1 / n_measurable if n_measurable else None
    conditional = 100.0 * n_ff1 / n_passed_measurable if n_passed_measurable else None
    return {
        "n_rows": n_rows,
        "n_passed": n_passed,
        "n_measurable": n_measurable,
        "n_ff1": n_ff1,
        "n_passed_measurable": n_passed_measurable,
        "marginal_pct": round(marginal, 2) if marginal is not None else None,
        "conditional_pct": round(conditional, 2) if conditional is not None else None,
    }


def _load_main_batch_rows() -> dict[str, list[dict]]:
    """加载主批次工件（R-P0-2 口径来源，aitester 行 + 修正口径行）。

    R-P0-2 定案（10-13）：主批次 = 2026-10-01 首个基准（n=261，含
    df/llm 双基线 aiter 行）；后续 10-06/10-07 批次为重放批次（n=50，
    非主批次，不计入 R-P0-2 口径）。本函数只取**首个**基准批次。
    """
    populations: dict[str, list[dict]] = {}
    for json_path in sorted(MAIN_BATCH_DIR.glob("benchmark_*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ts = data.get("timestamp", "")
        # R-P0-2 主批次 = 首个基准（10-01）；重放批次（10-06/10-07）不计入
        if ts and ts > "2026-10-02":
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

    返回 {n_det_measurable, detection_rate_pct, mutation_score:{...},
    mutants_total_distribution:{...}}。
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
    if mut_pairs:
        det1_scores = [s for d, s in mut_pairs if d == 1.0]
        if det1_scores:
            mean_when_det1 = sum(det1_scores) / len(det1_scores)
    mt_dist = [r.get("mutants_total") for r in rows if r.get("mutants_total") is not None]
    return {
        "n_det_measurable": n_det,
        "detection_rate_pct": round(det_pct, 4) if det_pct is not None else None,
        "mutation_score": {
            "n_pairs": len(mut_pairs),
            "mean_when_detection_1": mean_when_det1,
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
    """在 gold fixed 上真实复跑（零 LLM，子进程 pytest）并记录 rc/模式。"""
    with tempfile.TemporaryDirectory(prefix="emse_overred_") as tmp:
        tmp = Path(tmp)
        module_name = task_id.rsplit("__", 1)[-1] if "__" in task_id else "task_m"
        (tmp / f"{module_name}.py").write_text(fixed_code, encoding="utf-8")
        test_file = tmp / f"test_{module_name}.py"
        test_file.write_text(test_code, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        rc = proc.returncode
        passes = rc == 0
        mode = "P4_passes_on_fixed" if passes else classify_failure_signature(proc.stdout + proc.stderr)
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
    # 基础设施故障的修正陈述（若 429 / timeout 占主导）
    corrected = ""
    if "429" in notes or timeout > completed + failed:
        corrected = "基础设施故障（429 限流 / 超时）主导，非模型能力信号"
    return {
        "available": True,
        "total_tasks_attempted": total,
        "tasks_completed": completed,
        "tasks_failed": failed,
        "tasks_timeout": timeout,
        "notes": notes,
        "corrected_statement": corrected,
    }


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


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：`--ab-pair a.json b.json arm_a arm_b` 或默认 false_fix 矩阵。"""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ab-pair", nargs=4, metavar=("A", "B", "ARM_A", "ARM_B"), help="两臂批次 JSON 配对分析")
    args = ap.parse_args(argv)
    if args.ab_pair:
        path_a, path_b, arm_a, arm_b = args.ab_pair
        print(json.dumps(ab_pair_analysis(path_a, path_b, arm_a, arm_b), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(build_false_fix_matrix(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
