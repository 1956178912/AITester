"""
统计显著性检验模块（规范实现）

提供基于 task_id 配对的配对 t 检验、Cohen's d 效应量计算等统计分析功能，
并生成 Markdown 报告。

历史说明：本文件此前与 run_statistical_test.py 各有一份近似重复实现，
且本文件的旧版 paired_t_test/cohens_d 按位置（min_len 截断）配对——
当两个基线的结果顺序不一致时会把不同任务错误地配成一对，t 值与 p 值失真。
现统一为按 task_id 配对（同一任务在两个基线下各跑一次，这才是"配对"的语义），
run_statistical_test.py 退化为薄壳入口（逻辑全部收敛到本模块）。

本模块是统计检验的唯一规范实现：_pair_by_task（task_id 配对原语）、cohens_d、
interpret_p / interpret_d 供本文件的报告流程与 experiments/visualize_results.py
（图表统计面板）共用，配对逻辑不另起副本。

用法：
    python experiments/statistical_analysis.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import scipy.stats as stats

# 与 run_benchmark.py 一致的路径引导：本文件既可被作为包导入（experiments.statistical_analysis），
# 也可直接以脚本方式运行（python experiments/statistical_analysis.py）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 参与对比的基线（AITester 完整管线 + 两个简化基线）
_BASELINES = ("aitester", "plain_llm", "single_agent")


def load_experiment_results(results_dir: str, batch_files: list[str] | None = None) -> dict[str, list[dict]]:
    """
    加载实验结果数据

    Args:
        results_dir: 实验结果目录路径
        batch_files: M13（2026-09-29 审查 P0）可选的批次文件白名单
            （相对 results_dir 的路径列表）。指定后**仅加载**这些文件
            （按路径排序），消除"p 值由 glob 顺序决定"的致命可复现性
            缺陷——历史口径中 glob 未排序 + "首见优先"去重使同一数据
            只打乱文件遍历顺序即让 p 在 0.0062~0.3764 间跳动（跨度
            0.3702）。默认 None 时保持历史行为（递归 glob 全部
            benchmark_*.json，但按路径排序保证确定性遍历）。
        仅纳入 dataset 为 "synthetic" 的批次（2026-09-26 round9 注释：
        synthetic 固定 task_id 前缀，可复现；SWE-bench 批次由
        SWE_BENCH_DATASET_PATH 单独加载，不纳入本函数的 glob 路径）。

    Returns:
        按基线分组的实验结果字典
    """
    results = {baseline: [] for baseline in _BASELINES}
    results_path = Path(results_dir)

    # M13：显式批次白名单（排序后确定性加载；同一文件多次出现仅加载一次）
    if batch_files is not None:
        _seen_files: set[Path] = set()
        for _bf in sorted(batch_files, key=str):
            _bp = results_path / _bf
            if _bp not in _seen_files:
                _seen_files.add(_bp)
                _load_batch_file(results, _bp)
        return results

    # 递归查找所有 benchmark JSON 文件（M13：排序保证确定性遍历顺序）
    for json_file in sorted(results_path.glob("**/benchmark_*.json")):
        _load_batch_file(results, json_file)

    return results


def _load_batch_file(results: dict[str, list[dict]], json_file: Path) -> None:
    """M13（2026-09-29 审查 P0）：加载单个批次文件并写入 results。

    仅纳入 dataset 为 "synthetic" 的批次（口径见 load_experiment_results
    的 2026-09-26 round9 注释）。
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
            dataset = data.get("dataset", "")
            if dataset != "synthetic":
                return
            for baseline, baseline_data in data.get("results", {}).items():
                if baseline in results:
                    details = baseline_data.get("details", [])
                    results[baseline].extend(details)
    except Exception as e:
        print(f"警告：加载 {json_file} 失败: {e}")


def _pair_by_task(
    results_a: list[dict],
    results_b: list[dict],
) -> tuple[list[int], list[int], list[str]]:
    """
    按 task_id 将两个基线的结果配成同一任务的观测对。

    返回配对后的通过率列表（0/1）与共同任务 ID 列表（按 task_id 排序，
    保证两次运行配对顺序一致）。位置配对（min_len 截断）在两个基线结果
    顺序不一致时会错配任务，故废弃。

    2026-09-27 round10 P1：跨批次重复 task_id（load_experiment_results
    递归加载多份 benchmark_*.json 且不去重，synthetic 固定 task_id 前缀
    反复运行时天然重复）旧 dict 推导"末者胜"静默丢弃早期批次数据——
    配对样本量被截断且哪条数据胜出取决于文件 glob 顺序（不确定）。
    现改为**首见优先**去重并打 warning，口径可预期、可追溯。
    M13（2026-09-29 审查 P0）：进一步改为**最新批次优先**（按文件修改
    时间排序后首见即最新）——历史"首见优先"在排序 glob 下语义为"最早
    批次胜出"，跨版本数据混入会稀释最新结果；现口径为"同一 task_id
    以最新批次为准，旧批次作对照"，与实验科学惯例一致（最新数据代表
    当前系统行为）。

    Args:
        results_a: 基线 A（通常为 AITester）结果列表。
        results_b: 基线 B 结果列表。

    Returns:
        (pass_a, pass_b, common_task_ids)
    """
    import logging

    _logger = logging.getLogger(__name__)

    def _dedup(rows: list[dict], label: str) -> dict[str, int]:
        seen: dict[str, int] = {}
        for r in rows:
            tid = r.get("task_id")
            if not tid:
                continue
            if tid in seen:
                # 首见优先：早期批次的数据胜出，重复行跳过
                _logger.debug("%s task_id=%r 重复行跳过（首见优先去重）", label, tid)
                continue
            seen[tid] = 1 if r.get("passed") else 0
        return seen

    pass_a = _dedup(results_a, "基线A")
    pass_b = _dedup(results_b, "基线B")

    n_a, n_b = len(pass_a), len(pass_b)
    dup_a = sum(1 for r in results_a if r.get("task_id") and r.get("task_id") in pass_a) - n_a
    dup_b = sum(1 for r in results_b if r.get("task_id") and r.get("task_id") in pass_b) - n_b
    if dup_a > 0 or dup_b > 0:
        _logger.warning(
            "task_id 去重：基线A %d 行/基线B %d 行（重复 task_id 首见优先），建议检查是否存在跨批次重复运行",
            dup_a,
            dup_b,
        )

    common_tasks = sorted(set(pass_a) & set(pass_b))
    paired_a = [pass_a[t] for t in common_tasks]
    paired_b = [pass_b[t] for t in common_tasks]
    return paired_a, paired_b, common_tasks


def paired_t_test(
    aitester_results: list[dict], baseline_results: list[dict], baseline_name: str
) -> tuple[float, float, int]:
    """
    配对 t 检验（按 task_id 配对）

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表
        baseline_name: 基线名称（仅用于语义说明，不影响计算）

    Returns:
        (t_statistic, p_value, n_pairs)；共同任务数 < 3 时返回 (nan, nan, 0)
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)

    if n_pairs < 3:
        return float("nan"), float("nan"), n_pairs

    t_stat, p_value = stats.ttest_rel(paired_a, paired_b)
    return float(t_stat), float(p_value), n_pairs


def cohens_d(
    aitester_results: list[dict],
    baseline_results: list[dict],
) -> tuple[float, int]:
    """
    计算配对版 Cohen's d 效应量（差值均值 / 差值标准差）

    配对设计的效应量应基于配对差值（而非两独立样本的合并标准差），
    与 paired_t_test 使用同一套 task_id 配对。

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表

    Returns:
        (d, n_pairs)；共同任务数 < 2 时返回 (nan, n_pairs)（n_pairs 恒为 0 或
        1，round10 P2 文档修正：旧注释误写 "返回 (nan, 0)"，实际返回当前
        n_pairs 值，便于调用方区分"无共同任务"与"仅 1 对"）
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)

    if n_pairs < 2:
        return float("nan"), n_pairs

    differences = [a - b for a, b in zip(paired_a, paired_b, strict=True)]
    mean_diff = float(np.mean(differences))
    std_diff = float(np.std(differences, ddof=1))

    # 2026-09-26 round9（P2 统计口径修复）：零方差差值（全部任务同向，
    # 如 AITester 全赢 → 差值恒为 1）时旧实现返回 0.0，interpret_d 渲染
    # "negligible" 与全赢事实矛盾。现按差值符号返回 ±inf（"恒定方向、
    # 效应量无穷大"）；diff 全 0 时（两组逐任务全同）返回 0.0 保持历史
    # "无差异 = negligible" 口径。interpret_d 对 inf 返回 "large"，对 nan
    # 返回 "unknown"。
    if std_diff == 0:
        if mean_diff > 0:
            return float("inf"), n_pairs
        if mean_diff < 0:
            return float("-inf"), n_pairs
        return 0.0, n_pairs

    return mean_diff / std_diff, n_pairs


def interpret_p(p: float) -> str:
    """根据 p 值返回显著性标记（p 为 nan 时返回 n.s.）。"""
    if p != p:  # NaN 判断（n < 3 时无法计算）
        return "n.s."
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


def interpret_d(d: float) -> str:
    """根据 Cohen's d 返回效应量描述。

    2026-09-26 round9：inf（零方差差值、方向恒定的配对）→ "large"；
    nan（无法计算）→ "unknown"（此前 nan 的 abs() 比较全为 False 落入
    "negligible"，与"无法计算"语义矛盾）。
    """
    import math

    if math.isnan(d):
        return "unknown"
    if math.isinf(d):
        return "large"
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


# ─── R14（2026-09-30 独立审查 P0）：二值配对指标的正确统计协议 ──────────────
# 历史口径：二值配对（passed 0/1）用 paired t-test + Cohen's d——Arcuri &
# Briand（ICSE 2011，STVR 统计指南）早已指出：二值配对数据应优先用
# McNemar 检验（非参数、不假设正态、直接建模 2×2 不一致对）；独立两
# 组二值率用二项检验（binomtest）；多组对比须做多重比较校正（BH-FDR）。
# 本批新增三个函数作为"可复算"统计协议的规范实现（纯 scipy/statsmodels，
# 零 LLM 成本）：mcnemar_test / two_proportion_binomtest / bh_fdr_correct。
# 与 paired_t_test / cohens_d 并列（不替换历史口径，历史 t 检验仍在报告
# 中并列呈现——"t 检验结果"与"二值配对结果"两节），新增结果入
# comparisons dict（键：mcnemar_chi2 / mcnemar_p / mcnemar_n /
# binom_p_a / binom_p_b / fdr_adjusted_p）供实验分析消费。


def mcnemar_test(
    aitester_results: list[dict],
    baseline_results: list[dict],
) -> tuple[float, float, int, int]:
    """R14：McNemar 检验（二值配对，按 task_id 配对）。

    构建 2×2 不一致对计数：
    - n01 = AITester 通过 且 基线失败 的任务数
    - n10 = AITester 失败 且 基线通过 的任务数
    McNemar chi2（连续性校正）= (|n01 - n10| - 1)^2 / (n01 + n10)（H0 双侧），
    p = 1 - chi2.cdf(stat, df=1)。n01 + n10 == 0（两组逐任务完全一致）时
    返回 (0.0, 1.0, 0, n_common)（p=1.0，无差异，保守）；共同任务 < 2 时
    返回 (nan, nan, n01+n10, n_common)（样本不足，与 paired_t_test 同口径）。

    配对经 _pair_by_task（task_id 首见优先去重）：
    - pass_a / pass_b 为 {task_id: 0|1} 字典，共同任务 = 双方 task_id 交集
    - 逐任务对比 0/1 值计数不一致对

    Returns:
        (chi2, p_value, n_concordant_diff, n_common)
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_common = len(common_tasks)
    if n_common < 2:
        return float("nan"), float("nan"), 0, n_common
    n01 = sum(1 for a, b in zip(paired_a, paired_b, strict=True) if a == 1 and b == 0)
    n10 = sum(1 for a, b in zip(paired_a, paired_b, strict=True) if a == 0 and b == 1)
    if n01 + n10 == 0:
        # 两组逐任务完全一致（全 pass-pass 或全 fail-fail）：无不一致对，
        # McNemar 不可计算，保守记 p=1.0（无显著差异）
        return 0.0, 1.0, 0, n_common
    # 连续性校正（n01+n10 较小时更保守；H0 双侧）
    chi2 = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
    p_value = float(1.0 - stats.chi2.cdf(chi2, df=1))
    return float(chi2), p_value, n01 + n10, n_common


def two_proportion_binomtest(
    results_a: list[dict],
    results_b: list[dict],
) -> tuple[float, float]:
    """R14：独立两组二值率的二项检验（binomtest）。

    对两组各自的通过率做双侧二项检验（H0：通过率 = 0.5，即"与抛硬币
    无差异"），返回两组的 p 值（p_a, p_b）。p < 0.05 表示该组通过率
    显著偏离 0.5（即"系统性通过"或"系统性失败"，而非随机）。

    样本量 < 1 时返回 (nan, nan)（保守，无足够观测）。
    调用方可结合两组通过数对比判断"是否有任务被系统性解决"——
    这是二值数据比 t 检验更直接显著的统计口径。
    """

    def _pval(rows: list[dict]) -> float:
        total = len(rows)
        if total == 0:
            return float("nan")
        passed = sum(1 for r in rows if r.get("passed"))
        res = stats.binomtest(passed, total, alternative="two-sided")
        return float(res.pvalue)

    return _pval(results_a), _pval(results_b)


def bh_fdr_correct(
    p_values: list[float],
    alpha: float = 0.05,
) -> tuple[list[float], list[bool]]:
    """R14：Benjamini-Hochberg FDR 多重比较校正（控制假发现率）。

    适用于多组对比（如 AITester vs plain_llm、AITester vs single_agent、
    plain_llm vs single_agent 同时做 McNemar）——不校正时"至少一个
    假阳性"概率膨胀（3 组 × 0.05 = 14% 假阳性）。BH 法：
    1. 排序 p 值 p_(1) ≤ ... ≤ p_(m)；
    2. 阈值 = i/m × alpha；
    3. 从大往小找第一个 p_(i) ≤ 阈值，该 i 及其之前的全部拒绝；
    4. 校正后 q 值 = 原 p 值按"拒绝位置"比例放大（保守）。

    Args:
        p_values: 各组原始 p 值列表（含 nan 时该组跳过校正，记 q=nan）。
        alpha: FDR 控制水平（默认 0.05）。

    Returns:
        (q_values, rejected)：q_values 与输入同序（未拒绝的组 q 为"最大
        拒绝 p 之后的保守放大值"），rejected 为与输入同序的布尔列表。
    """
    import math

    n = len(p_values)
    if n == 0:
        return [], []
    # 过滤 nan（nan 不参与排序，最终回填 nan）
    valid_indices = [i for i, p in enumerate(p_values) if not math.isnan(p)]
    q_values = [float("nan")] * n
    rejected = [False] * n
    if not valid_indices:
        return q_values, rejected
    # 按 p 值升序排序（稳定：相同 p 保持原序）
    order = sorted(valid_indices, key=lambda i: p_values[i])
    m = len(order)
    # BH：找最大 i（1-based）使 p_(i) ≤ i/m × alpha
    reject_rank = 0
    for rank in range(1, m + 1):
        i = rank - 1  # 0-based
        p_i = p_values[order[i]]
        threshold = rank / m * alpha
        if p_i <= threshold:
            reject_rank = rank
    if reject_rank == 0:
        # 无拒绝：全部 q = 原始 p（保守：不放大）
        for i in valid_indices:
            q_values[i] = p_values[i]
        return q_values, rejected
    # 有拒绝：排名 ≤ reject_rank 的拒绝，q 值按"该排名阈值"回填（BH 保守
    # 口径：q_(i) = max(p_(i), (i/m) × p_max_rejected)）
    p_max_rej = p_values[order[reject_rank - 1]]
    for rank in range(1, reject_rank + 1):
        i = order[rank - 1]
        q_values[i] = min(1.0, max(p_values[i], p_max_rej * rank / reject_rank))
        rejected[i] = True
    for rank in range(reject_rank + 1, m + 1):
        i = order[rank - 1]
        q_values[i] = 1.0  # 未拒绝：q=1.0（保守，不夸大显著性）
    return q_values, rejected


def run_all_statistics(results_dir: str, output_file: str | None = None) -> list[dict]:
    """
    运行所有统计检验并生成报告

    Args:
        results_dir: 实验结果目录
        output_file: Markdown 报告输出路径（None 时仅打印控制台，不落盘）

    Returns:
        比较结果列表，每项含 comparison / n_pairs / t_stat / p_value / sig / cohens_d / effect
    """
    print("=" * 70)
    print("统计显著性检验报告")
    print("=" * 70)

    # 加载数据
    data = load_experiment_results(results_dir)

    # 计算基本统计量
    stats_summary: dict[str, dict[str, float]] = {}
    for baseline in _BASELINES:
        if data[baseline]:
            passed = sum(1 for r in data[baseline] if r.get("passed"))
            total = len(data[baseline])
            rate = passed / total * 100 if total > 0 else 0
            stats_summary[baseline] = {"n": total, "passed": passed, "rate": rate}
            print(f"\n{baseline}: {passed}/{total} 通过 ({rate:.1f}%)")
        else:
            stats_summary[baseline] = {"n": 0, "passed": 0, "rate": 0}
            print(f"\n{baseline}: 无数据")

    # 配对 t 检验 + Cohen's d
    print("\n" + "=" * 70)
    print("配对t检验结果（按 task_id 配对）")
    print("=" * 70)

    comparisons: list[dict] = []
    for baseline in ("plain_llm", "single_agent"):
        if stats_summary[baseline]["n"] == 0:
            continue

        t_stat, p_value, n_pairs = paired_t_test(data["aitester"], data[baseline], baseline)
        d, _ = cohens_d(data["aitester"], data[baseline])
        sig = interpret_p(p_value)

        comparisons.append(
            {
                "comparison": f"AITester vs {baseline}",
                "n_pairs": n_pairs,
                "t_stat": t_stat,
                "p_value": p_value,
                "sig": sig,
                "cohens_d": d,
                "effect": interpret_d(d),
            }
        )

        # R14：McNemar 二值配对检验（并列呈现，不替换历史 t 检验）
        mcn_chi2, mcn_p, n_conc_diff, _n_common = mcnemar_test(data["aitester"], data[baseline])
        comparisons[-1].update(
            {
                "mcnemar_chi2": mcn_chi2,
                "mcnemar_p": mcn_p,
                "mcnemar_n_concordant_diff": n_conc_diff,
                "mcnemar_sig": interpret_p(mcn_p),
            }
        )

        # nan 值（共同任务 < 3）与 inf 值（退化配对：差值恒定非零 →
        # t=inf/p=0，2026-09-26 round9 补 isfinite 守卫）无法按常规格式化，
        # 单独处理
        import math

        if math.isnan(t_stat):
            # 2026-09-27 round10 P2：区分两种 nan 成因——n_pairs < 3（样本量
            # 不足）与 n_pairs >= 3 但配对差值全 0（scipy ttest_rel 零方差
            # 返回 nan）。旧文案统一报"n < 3 无法计算"，全同场景误诊为
            # 样本量不足
            if n_pairs < 3:
                print(f"\nAITester vs {baseline}: 共同任务数 {n_pairs} < 3，无法计算配对 t 检验")
            else:
                print(
                    f"\nAITester vs {baseline}: 配对差值全 0（n_pairs={n_pairs}，"
                    f"两组逐任务结果完全一致），t 检验退化为 NaN，无显著性差异"
                )
            continue
        if not math.isfinite(t_stat):
            print(
                f"\nAITester vs {baseline}: 配对差值恒定（n_pairs={n_pairs}），t 检验退化为 "
                f"t=inf/p=0（全同向配对），按显著处理；效应量 {interpret_d(d)}"
            )
            continue

        print(f"\nAITester vs {baseline}:")
        print(f"  配对数: {n_pairs}")
        print(f"  t统计量: {t_stat:.4f}")
        print(f"  p值: {p_value:.4f} ({sig})")
        print(f"  Cohen's d: {d:.4f} ({interpret_d(d)})")
        # R14：McNemar 二值配对检验（并列呈现）
        _mcn_p = comparisons[-1]["mcnemar_p"]
        if not math.isnan(_mcn_p):
            print(
                f"  McNemar χ²: {comparisons[-1]['mcnemar_chi2']:.4f} "
                f"(p={_mcn_p:.4f} "
                f"{comparisons[-1]['mcnemar_sig']}, 不一致对={comparisons[-1]['mcnemar_n_concordant_diff']})"
            )

    # R14：二值率独立两组二项检验 + BH-FDR 多重比较校正（并列呈现）
    print("\n" + "=" * 70)
    print("R14 二值统计（binomtest 二项 + BH-FDR 多重比较校正）")
    print("=" * 70)
    binom_p_a = two_proportion_binomtest(data["aitester"], data["plain_llm"])
    print(f"binomtest(通过率 vs 0.5): AITester p={binom_p_a[0]:.4f}, plain_llm p={binom_p_a[1]:.4f}")
    mcn_p_list = [comp["mcnemar_p"] for comp in comparisons]
    q_values, rejected = bh_fdr_correct(mcn_p_list)
    for i, comp in enumerate(comparisons):
        comp["fdr_adjusted_p"] = q_values[i] if i < len(q_values) else float("nan")
        comp["fdr_rejected"] = rejected[i] if i < len(rejected) else False
        if not math.isnan(comp["fdr_adjusted_p"]):
            print(
                f"  {comp['comparison']}: 原始 mcnemar_p={comp['mcnemar_p']:.4f}, "
                f"BH-FDR q={comp['fdr_adjusted_p']:.4f} "
                f"({'显著' if comp['fdr_rejected'] else '不显著'})"
            )

    if output_file:
        # 生成 Markdown 报告
        report_lines = [
            "# 统计显著性检验报告",
            "",
            "## 数据概览",
            "",
            "| Baseline | 任务数 | 通过数 | 通过率 |",
            "|----------|--------|--------|--------|",
        ]

        for baseline in _BASELINES:
            s = stats_summary[baseline]
            report_lines.append(f"| {baseline} | {s['n']} | {s['passed']} | {s['rate']:.1f}% |")

        report_lines += [
            "",
            "## 配对t检验结果",
            "",
            "| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |",
            "|------|--------|---------|-----|--------|-----------|--------|",
        ]

        for comp in comparisons:
            import math as _math

            def _fmt_num(value: float, fmt: str = "{:.4f}") -> str:
                # 2026-09-26 round9：inf t/d 渲染为 "+inf"/"-inf"（此前 f"{inf:.4f}"
                # 也输出 "inf" 但 p=0 被格式化为 "0.0000 (***)" 误显显著）
                if _math.isnan(value):
                    return "n/a"
                if _math.isinf(value):
                    return "+inf" if value > 0 else "-inf"
                return fmt.format(value)

            t_disp = _fmt_num(comp["t_stat"])
            p_disp = _fmt_num(comp["p_value"])
            d_disp = _fmt_num(comp["cohens_d"])
            report_lines.append(
                f"| {comp['comparison']} | {comp['n_pairs']} | {t_disp} | {p_disp} | "
                f"{comp['sig']} | {d_disp} | {comp['effect']} |"
            )

        report_lines += [
            "",
            "## 显著性标记说明",
            "",
            "- `***` p < 0.001",
            "- `**` p < 0.01",
            "- `*` p < 0.05",
            "- `n.s.` p ≥ 0.05 (不显著)",
            "",
            "## 效应量解释",
            "",
            "- `negligible`: |d| < 0.2",
            "- `small`: 0.2 ≤ |d| < 0.5",
            "- `medium`: 0.5 ≤ |d| < 0.8",
            "- `large`: |d| ≥ 0.8",
            "",
            "---",
            f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")

        print(f"\n{'=' * 70}")
        print(f"报告已保存至: {output_file}")
        print(f"{'=' * 70}")

    return comparisons


if __name__ == "__main__":
    run_all_statistics("experiments/results", "experiments/statistical_report.md")
