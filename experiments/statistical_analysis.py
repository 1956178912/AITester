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

R2（2026-10-05 审查：统计协议完整性）新增（全部为增量，历史 t 检验表不变）：
- 报告落盘 McNemar / BH-FDR 章节（此前仅打印控制台）；
- bootstrap_paired_diff_ci：配对差值均值的百分位法 95% CI（纯 Python，
  random.Random(seed) 固定 seed=42，10000 次重采样）；
- cliffs_delta：非参数效应量，与 Cohen's d 并列输出；
- --batches 批次白名单 CLI + 报告头部"数据来源"审计章节。

用法：
    python experiments/statistical_analysis.py
    python experiments/statistical_analysis.py \
        --results-dir experiments/results \
        --batches main_batch/benchmark_synthetic_20261001_112528.json,main_batch/benchmark_synthetic_20261001_112801.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterable
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
    加载实验结果数据（历史入口，语义与 R2 之前完全一致）

    Args:
        results_dir: 实验结果目录路径
        batch_files: M13（2026-09-29 审查 P0）可选的批次文件白名单
            （相对 results_dir 的路径列表）。指定后**仅加载**这些文件
            （按 mtime 降序加载，N5），消除"p 值由 glob 顺序决定"的致命
            可复现性缺陷——历史口径中 glob 未排序 + "首见优先"去重使
            同一数据只打乱文件遍历顺序即让 p 在 0.0062~0.3764 间跳动
            （跨度 0.3702）。默认 None 时保持递归 glob 全部
            benchmark_*.json（N5：mtime 降序 + 路径名平局打破，确定性遍历）。
        仅纳入 dataset 为 "synthetic" 的批次（2026-09-26 round9 注释：
        synthetic 固定 task_id 前缀，可复现；SWE-bench 批次由
        SWE_BENCH_DATASET_PATH 单独加载，不纳入本函数的 glob 路径）。

    Returns:
        按基线分组的实验结果字典
    """
    results, _ = load_experiment_results_with_sources(results_dir, batch_files)
    return results


def load_experiment_results_with_sources(
    results_dir: str, batch_files: list[str] | None = None
) -> tuple[dict[str, list[dict]], list[str]]:
    """R2（2026-10-05 审查）：加载实验结果并返回"实际纳入"的批次文件清单。

    与 load_experiment_results 同一套加载逻辑（该函数退化为薄壳委托，
    历史调用方零变化），额外返回审计信息：实际纳入统计的批次文件路径
    列表（按加载顺序 = mtime 降序，N5）。"实际纳入"口径：
    - 白名单模式：指定的文件中 dataset == "synthetic" 且成功解析的；
    - glob 模式：递归扫描的 benchmark_*.json 中同样实际加载了数据的。

    报告头部"数据来源"章节消费本清单（审计用：读者可核对 p 值背后
    恰好是哪些批次，避免混批次结论不可复现）。

    Args:
        results_dir: 实验结果目录路径
        batch_files: 批次文件白名单（相对 results_dir；None 时走 glob）

    Returns:
        (按基线分组的结果字典, 实际纳入的批次文件路径字符串列表——
        位于 results_dir 内的文件返回相对 posix 路径，其余返回绝对路径)
    """
    results: dict[str, list[dict]] = {baseline: [] for baseline in _BASELINES}
    results_path = Path(results_dir)
    included_files: list[str] = []

    def _display_path(p: Path) -> str:
        """审计清单用的展示路径：目录内相对 posix，目录外绝对路径。"""
        try:
            return p.relative_to(results_path).as_posix()
        except ValueError:
            return str(p)

    # M13：显式批次白名单（2026-10-05 P0：确定性排序 = 内嵌时间戳降序，
    # mtime 兜底；同一文件多次出现仅加载一次）
    if batch_files is not None:
        _seen_files: set[Path] = set()
        for _bp in _sort_batch_files_deterministic(results_path / _bf for _bf in batch_files):
            if _bp not in _seen_files:
                _seen_files.add(_bp)
                if _load_batch_file(results, _bp):
                    included_files.append(_display_path(_bp))
        return results, included_files

    # 递归查找所有 benchmark JSON 文件（M13：确定性遍历；2026-10-05 P0：
    # 排序主键 = 文件名内嵌时间戳降序（实验属性，跨机可复算），mtime 兜底；
    # "最新批次先加载"使 _pair_by_task 首见去重语义成立；
    # R2：记录实际纳入的文件供"数据来源"审计章节消费）
    included_files.extend(
        _display_path(json_file)
        for json_file in _sort_batch_files_deterministic(results_path.glob("**/benchmark_*.json"))
        if _load_batch_file(results, json_file)
    )

    return results, included_files


def _sort_batch_files_deterministic(files: Iterable[Path]) -> list[Path]:
    """批次文件确定性排序（2026-10-05 独立审查 P0：去重口径可复算化）。

    N5 的"最新批次优先"语义保留，但主键从 mtime（文件系统属性，clone/
    重命名/拷贝即漂移——同一份工件在开发机与 CI 上可解出不同去重顺序，
    χ²=12.96 vs 15.04 的报告不可复算即源于此）改为**批次文件名内嵌
    时间戳**（benchmark_*_YYYYMMDD_HHMMSS.json，run_benchmark 写盘时
    固化的实验属性）：

    - 有内嵌时间戳（规范命名批次）：按时间戳降序（最新先加载），平局按
      路径名升序稳定打破；
    - 无内嵌时间戳（历史/外部批次）：排在规范批次之后，组内按 mtime 降序
      （N5 兜底语义），再按路径名升序平局；stat 失败排最后保持路径序。

    同一目录树在任意机器/任意时刻的加载顺序逐位一致——"最新批次优先"
    从文件系统巧合变为工件自描述。
    """
    import re

    _TS_RE = re.compile(r"_(\d{8}_\d{6})\.json$")

    keyed: list[tuple[int, int, int, str, Path]] = []
    for p in files:
        m = _TS_RE.search(p.name)
        if m:
            keyed.append((0, -_ts_rank(m.group(1)), 0, str(p), p))
        else:
            try:
                keyed.append((1, -p.stat().st_mtime_ns, 0, str(p), p))
            except OSError:
                keyed.append((2, 0, 0, str(p), p))
    keyed.sort(key=lambda k: (k[0], k[1], k[3]))
    return [k[4] for k in keyed]


def _ts_rank(ts: str) -> int:
    """YYYYMMDD_HHMMSS → 可比较整数（20261001_121523 → 20261001121523）。"""
    try:
        return int(ts.replace("_", ""))
    except ValueError:
        return 0


def _load_batch_file(results: dict[str, list[dict]], json_file: Path) -> bool:
    """M13（2026-09-29 审查 P0）：加载单个批次文件并写入 results。

    仅纳入 dataset 为 "synthetic" 的批次（口径见 load_experiment_results
    的 2026-09-26 round9 注释）。

    Returns:
        该文件是否实际纳入（R2 审计口径：dataset 非 synthetic 或解析
        失败时返回 False，不进入"数据来源"清单）
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        dataset = data.get("dataset", "")
        if dataset != "synthetic":
            return False
        for baseline, baseline_data in data.get("results", {}).items():
            if baseline in results:
                details = baseline_data.get("details", [])
                results[baseline].extend(details)
        return True
    except Exception as e:
        print(f"警告：加载 {json_file} 失败: {e}")
        return False


def _pair_by_task(
    results_a: list[dict],
    results_b: list[dict],
    field: str = "passed",
) -> tuple[list[int], list[int], list[str]]:
    """
    按 task_id 将两个基线的结果配成同一任务的观测对。

    返回配对后的二值列表（0/1）与共同任务 ID 列表（按 task_id 排序，
    保证两次运行配对顺序一致）。位置配对（min_len 截断）在两个基线结果
    顺序不一致时会错配任务，故废弃。

    2026-09-27 round10 P1：跨批次重复 task_id（load_experiment_results
    递归加载多份 benchmark_*.json 且不去重，synthetic 固定 task_id 前缀
    反复运行时天然重复）旧 dict 推导"末者胜"静默丢弃早期批次数据——
    配对样本量被截断且哪条数据胜出取决于文件 glob 顺序（不确定）。
    现改为**首见优先**去重并打 warning，口径可预期、可追溯。
    M13（2026-09-29 审查 P0）：进一步改为**最新批次优先**——历史"首见
    优先"在排序 glob 下语义为"最早批次胜出"，跨版本数据混入会稀释最新
    结果；现口径为"同一 task_id 以最新批次为准，旧批次作对照"，与实验
    科学惯例一致（最新数据代表当前系统行为）。
    N5（2026-10-05 复审）：该口径此前仅存在于 docstring——加载顺序实为
    路径序而非 mtime 序。2026-10-05 独立审查 P0 进一步把排序主键从 mtime
    （文件系统属性，不可复算）改为文件名内嵌时间戳降序（实验属性，
    _sort_batch_files_deterministic），本函数首见 = 最新批次，docstring、
    实现与可复算性三者一致。

    Args:
        results_a: 基线 A（通常为 AITester）结果列表。
        results_b: 基线 B 结果列表。
        field: 配对所用的二值结果行字段（2026-10-05 独立审查 P0：
            "passed"（历史默认，自指指标）外新增 "detection_rate" /
            "repair_rate" 等 M1 诚实指标——逐任务值 0.0/1.0/None，
            None（无 gold 材料，M1 分母外）跳过该任务，不并入分母）。

    Returns:
        (paired_a, paired_b, common_task_ids)
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
                # 首见优先：最新批次的数据胜出（排序主键 = 内嵌时间戳降序），重复行跳过
                _logger.debug("%s task_id=%r 重复行跳过（首见=最新批次优先去重）", label, tid)
                continue
            val = r.get(field)
            if val is None:
                # M1 诚实指标的 None = 无 gold 材料（分母外），非"未通过"——
                # 记 0 会把"无法测量"混入"测量为失败"，分母口径失真
                continue
            seen[tid] = 1 if val else 0
        return seen

    pass_a = _dedup(results_a, "基线A")
    pass_b = _dedup(results_b, "基线B")

    n_a, n_b = len(pass_a), len(pass_b)
    dup_a = sum(1 for r in results_a if r.get("task_id") and r.get("task_id") in pass_a) - n_a
    dup_b = sum(1 for r in results_b if r.get("task_id") and r.get("task_id") in pass_b) - n_b
    if dup_a > 0 or dup_b > 0:
        _logger.warning(
            "task_id 去重：基线A %d 行/基线B %d 行（重复 task_id 最新批次优先），建议检查是否存在跨批次重复运行",
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
    field: str = "passed",
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

    Args:
        aitester_results: AITester 结果列表。
        baseline_results: 基线结果列表。
        field: 二值结果行字段（2026-10-05 独立审查 P0："passed"（历史
            默认，自指指标）外新增 "detection_rate" / "repair_rate"——
            M1 诚实指标的独立裁决检验；None 值任务（无 gold 材料）跳过）。

    Returns:
        (chi2, p_value, n_concordant_diff, n_common)
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results, field=field)
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


# ─── R2（2026-10-05 审查：统计协议完整性）新增统计原语 ──────────────────────
# 补齐三块协议缺口（均为增量输出，历史 t 检验表与既有 comparisons 字段不变）：
# 1. cliffs_delta：非参数效应量（不假设差值正态，与 Cohen's d 并列呈现，
#    二值配对场景比 d 更稳健）；
# 2. bootstrap_paired_diff_ci：配对差值均值的百分位法置信区间（点估计的
#    不确定度此前完全未量化）；
# 3. 报告落盘 + 审计章节（见 run_all_statistics 与 main）。

# bootstrap 重采样默认参数（R2 固定口径：可复现优先）
_BOOTSTRAP_N_RESAMPLES = 10000
_BOOTSTRAP_SEED = 42


def cliffs_delta(
    aitester_results: list[dict],
    baseline_results: list[dict],
) -> tuple[float, int]:
    """R2：配对差值符号版 Cliff's delta（非参数效应量）。

    δ = (n⁺ − n⁻) / n_pairs，其中 n⁺/n⁻ 为配对差值（AITester − 基线，
    0/1 通过率的逐任务差）中正值/负值的个数（差值为 0 的对不贡献符号）。
    这是 Romano et al.（2006）的 Cliff's delta P(X>Y) − P(X<Y) 在**配对**
    场景的自然推广：与 cohens_d 共用 _pair_by_task 的 task_id 配对，
    不假设差值正态分布——二值配对数据（差值仅取 −1/0/1）下比基于
    差值标准差的 Cohen's d 更稳健（d 在零方差差值时退化为 ±inf）。

    边界：全正差值 → +1.0；全负差值 → −1.0；正负个数相等（或全 0）→ 0.0。

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表

    Returns:
        (delta, n_pairs)；共同任务数 < 2 时返回 (nan, n_pairs)（样本不足，
        与 cohens_d 同口径）
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)
    if n_pairs < 2:
        return float("nan"), n_pairs
    n_pos = sum(1 for a, b in zip(paired_a, paired_b, strict=True) if a > b)
    n_neg = sum(1 for a, b in zip(paired_a, paired_b, strict=True) if a < b)
    return (n_pos - n_neg) / n_pairs, n_pairs


def interpret_cliffs_delta(delta: float) -> str:
    """根据 Cliff's delta 返回效应量描述（Romano et al. 2006 阈值）。

    nan（无法计算）→ "unknown"；|δ| 阈值：0.147 / 0.33 / 0.474。
    """
    import math

    if math.isnan(delta):
        return "unknown"
    abs_d = abs(delta)
    if abs_d >= 0.474:
        return "large"
    if abs_d >= 0.33:
        return "medium"
    if abs_d >= 0.147:
        return "small"
    return "negligible"


def bootstrap_paired_diff_ci(
    aitester_results: list[dict],
    baseline_results: list[dict],
    n_resamples: int = _BOOTSTRAP_N_RESAMPLES,
    seed: int = _BOOTSTRAP_SEED,
) -> tuple[float, float, float, int]:
    """R2：配对差值均值的百分位法 bootstrap 置信区间（95%）。

    对 task_id 配对后的逐任务差值（AITester − 基线）做有放回重采样，
    每次重采样计算差值均值，取全部重采样均值的 2.5% / 97.5% 百分位
    作为 CI 上下界。纯 Python 实现（random.Random(seed) 固定种子，
    默认 seed=42、重采样 10000 次）——不引入 numpy.random 等新依赖
    路径，且同参数多次调用结果**逐位可复现**（报告可审计）。

    百分位口径（order-statistic）：对升序排序的 B 个重采样均值，
    p 分位取索引 round(p × (B−1)) 处的次序统计量（端点收缩，避免
    线性插值在重数少的桶内产生"数据中不存在的值"）。

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表
        n_resamples: 重采样次数（默认 10000，R2 固定口径）
        seed: 随机种子（默认 42，R2 固定口径）

    Returns:
        (mean_diff, ci_low, ci_high, n_pairs)——配对差值均值的点估计与
        95% CI 下/上界；共同任务数 < 2 时返回 (nan, nan, nan, n_pairs)
        （样本不足，与 paired_t_test / cohens_d 同口径）
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results)
    n_pairs = len(common_tasks)
    if n_pairs < 2:
        return float("nan"), float("nan"), float("nan"), n_pairs

    differences = [a - b for a, b in zip(paired_a, paired_b, strict=True)]
    mean_diff = sum(differences) / n_pairs

    # 纯 Python bootstrap：random.Random(seed) 独立实例（不受全局 random
    # 状态影响），rng.choice 有放回抽索引等价于均匀重采样
    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n_pairs):
            total += differences[rng.randrange(n_pairs)]
        boot_means.append(total / n_pairs)
    boot_means.sort()

    ci_low = _percentile(boot_means, 0.025)
    ci_high = _percentile(boot_means, 0.975)
    return mean_diff, ci_low, ci_high, n_pairs


def _percentile(sorted_values: list[float], p: float) -> float:
    """升序列表的 p 分位（order-statistic 口径，见 bootstrap_paired_diff_ci）。

    空列表返回 nan（防御：调用方已保证非空）。
    """
    if not sorted_values:
        return float("nan")
    k = int(p * (len(sorted_values) - 1) + 0.5)
    k = min(max(k, 0), len(sorted_values) - 1)
    return sorted_values[k]


def _fmt_stat_num(value: float, fmt: str = "{:.4f}") -> str:
    """统计量渲染：nan → "n/a"，±inf → "+inf"/"-inf"，其余按格式化串。

    R2 抽为模块级函数（此前在报告生成循环内逐次定义，McNemar / bootstrap
    / Cliff's delta 等新章节复用同一渲染口径）。2026-09-26 round9：inf
    渲染为 "+inf"/"-inf"（此前 p=0 被格式化为 "0.0000 (***)" 误显显著）。
    """
    import math

    if math.isnan(value):
        return "n/a"
    if math.isinf(value):
        return "+inf" if value > 0 else "-inf"
    return fmt.format(value)


def run_all_statistics(
    results_dir: str,
    output_file: str | None = None,
    batch_files: list[str] | None = None,
) -> list[dict]:
    """
    运行所有统计检验并生成报告

    Args:
        results_dir: 实验结果目录
        output_file: Markdown 报告输出路径（None 时仅打印控制台，不落盘）
        batch_files: R2 可选的批次文件白名单（相对 results_dir 的路径，
            透传 load_experiment_results_with_sources；None 时保持历史
            glob 全目录行为不变）

    Returns:
        比较结果列表，每项含 comparison / n_pairs / t_stat / p_value / sig /
        cohens_d / effect，以及 R14 的 mcnemar_* / fdr_* 与 R2 的
        cliffs_delta / cliffs_effect / bootstrap_* 字段
    """
    print("=" * 70)
    print("统计显著性检验报告")
    print("=" * 70)

    # 加载数据（R2：同时取"实际纳入"的批次清单，供审计章节与控制台输出）
    data, source_files = load_experiment_results_with_sources(results_dir, batch_files)
    _mode = "白名单" if batch_files is not None else "glob 全目录"
    print(f"\n数据来源：{len(source_files)} 个批次文件（{_mode}模式）")
    for _src in source_files:
        print(f"  - {_src}")

    # 计算基本统计量（2026-10-05 P0：并列统计 M1 诚实指标——passed 为
    # 自指指标（系统自产测试在未修复代码上通过，false_fix 主批次 89.8% 的
    # 直接来源），detection/repair 为 gold 独立裁决，报告读者第一眼应看
    # 诚实口径）
    stats_summary: dict[str, dict[str, float]] = {}
    for baseline in _BASELINES:
        if data[baseline]:
            passed = sum(1 for r in data[baseline] if r.get("passed"))
            total = len(data[baseline])
            rate = passed / total * 100 if total > 0 else 0
            det_vals = [r["detection_rate"] for r in data[baseline] if r.get("detection_rate") is not None]
            rep_vals = [r["repair_rate"] for r in data[baseline] if r.get("repair_rate") is not None]
            stats_summary[baseline] = {
                "n": total,
                "passed": passed,
                "rate": rate,
                "det_n": len(det_vals),
                "det_rate": sum(det_vals) / len(det_vals) * 100 if det_vals else 0.0,
                "rep_n": len(rep_vals),
                "rep_rate": sum(rep_vals) / len(rep_vals) * 100 if rep_vals else 0.0,
            }
            print(f"\n{baseline}: {passed}/{total} 通过 ({rate:.1f}%)")
            print(
                f"  诚实指标（gold 独立裁决）: detection {sum(det_vals)}/{len(det_vals)}"
                f" ({stats_summary[baseline]['det_rate']:.1f}%)"
                f" / repair {sum(rep_vals)}/{len(rep_vals)}"
                f" ({stats_summary[baseline]['rep_rate']:.1f}%)"
            )
        else:
            stats_summary[baseline] = {
                "n": 0,
                "passed": 0,
                "rate": 0,
                "det_n": 0,
                "det_rate": 0.0,
                "rep_n": 0,
                "rep_rate": 0.0,
            }
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

        # R2：Cliff's delta 非参数效应量（与 Cohen's d 并列，二值配对更稳健）
        delta, _ = cliffs_delta(data["aitester"], data[baseline])
        comparisons[-1].update(
            {
                "cliffs_delta": delta,
                "cliffs_effect": interpret_cliffs_delta(delta),
            }
        )

        # R2：配对差值均值的 bootstrap 95% CI（seed=42、10000 次重采样，可复现）
        boot_mean, boot_low, boot_high, _ = bootstrap_paired_diff_ci(data["aitester"], data[baseline])
        comparisons[-1].update(
            {
                "bootstrap_mean_diff": boot_mean,
                "bootstrap_ci_low": boot_low,
                "bootstrap_ci_high": boot_high,
                "bootstrap_n_resamples": _BOOTSTRAP_N_RESAMPLES,
                "bootstrap_seed": _BOOTSTRAP_SEED,
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
        # R2：Cliff's delta 与 bootstrap CI（并列呈现；nan 时 _fmt_stat_num 渲染 n/a）
        print(f"  Cliff's δ: {_fmt_stat_num(delta)} ({interpret_cliffs_delta(delta)})")
        print(
            f"  Bootstrap 95% CI（差值均值）: [{_fmt_stat_num(boot_low)}, {_fmt_stat_num(boot_high)}]"
            f"（{_BOOTSTRAP_N_RESAMPLES} 次重采样，seed={_BOOTSTRAP_SEED}）"
        )
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

    # 2026-10-05 独立审查 P0：M1 诚实指标（detection / repair，gold 独立
    # 裁决）的 McNemar 检验——历史口径只对 passed（自指）做推断统计，
    # 而主批次 honest 指标下 aitester 与 plain_llm 为 2% vs 2% / 0% vs 0%
    # 的平手，该事实从未被检验。本节使报告主结论与科学主张对齐。
    honest_metric_fields: tuple[tuple[str, str], ...] = (
        ("detection_rate", "detection（F2P 检出）"),
        ("repair_rate", "repair（gold 裁决修复）"),
    )
    honest_comparisons: list[dict] = []
    for metric_field, metric_label in honest_metric_fields:
        for baseline in ("plain_llm", "single_agent"):
            if stats_summary[baseline]["n"] == 0:
                continue
            h_chi2, h_p, h_ndiff, h_ncommon = mcnemar_test(data["aitester"], data[baseline], field=metric_field)
            honest_comparisons.append(
                {
                    "metric": metric_label,
                    "field": metric_field,
                    "comparison": f"AITester vs {baseline}",
                    "n_common": h_ncommon,
                    "n_diff": h_ndiff,
                    "chi2": h_chi2,
                    "p": h_p,
                    "sig": interpret_p(h_p),
                }
            )
    if honest_comparisons:
        print("\n" + "=" * 70)
        print("诚实指标 McNemar（M1 三指标，gold 独立裁决——首要结论口径）")
        print("=" * 70)
        for h in honest_comparisons:
            print(
                f"  [{h['metric']}] {h['comparison']}: 共同任务 {h['n_common']}"
                f"，不一致对 {h['n_diff']}，χ²={_fmt_stat_num(h['chi2'])}"
                f"，p={_fmt_stat_num(h['p'])} ({h['sig']})"
            )

    if output_file:
        # 生成 Markdown 报告（R2：新增"数据来源 / McNemar / Bootstrap CI /
        # 效应量对比（Cliff's δ）/ BH-FDR"五个章节——历史 t 检验表原样保留）
        report_lines = [
            "# 统计显著性检验报告",
            "",
            "## 数据来源",
            "",
            # R2 审计章节：p 值背后"恰好是哪些批次"的可核对清单（glob 混批次
            # 曾导致不可复现结论，见 load_experiment_results 的 M13 注释）
            f"R2 审计：本报告实际纳入 {len(source_files)} 个批次文件"
            f"（{'--batches 白名单模式' if batch_files is not None else '递归 glob 全目录模式'}）：",
            "",
        ]
        report_lines.extend(f"- `{src}`" for src in source_files)

        # 2026-10-05 P0：可复算声明——排序主键为文件名内嵌时间戳（实验
        # 属性），报告数值可用如下命令从入库工件逐位复现
        _recompute_cmd = (
            "python experiments/statistical_analysis.py "
            f"--results-dir {results_dir} --output <report.md>"
            + (f" --batches {','.join(source_files)}" if source_files else "")
        )
        report_lines += [
            "",
            f"复算命令（工件与代码齐备时数值逐位可复现）：`{_recompute_cmd}`",
            "",
            "去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次",
            "文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。",
        ]

        report_lines += [
            "",
            "## 数据概览",
            "",
            # 2026-10-05 P0：passed（自指）与 M1 诚实指标（detection/repair，
            # gold 独立裁决）并列——分母为该指标可测任务数（None = 无 gold
            # 材料，不计入分母）
            "| Baseline | 任务数 | 通过数 (passed) | 通过率 | detection 可测数 | detection 率 | repair 可测数 | repair 率 |",
            "|----------|--------|-----------------|--------|------------------|--------------|---------------|-----------|",
        ]

        for baseline in _BASELINES:
            s = stats_summary[baseline]
            report_lines.append(
                f"| {baseline} | {s['n']} | {s['passed']} | {s['rate']:.1f}% "
                f"| {s['det_n']} | {s['det_rate']:.1f}% | {s['rep_n']} | {s['rep_rate']:.1f}% |"
            )

        report_lines += [
            "",
            "## 诚实指标 McNemar 检验（M1 三指标，gold 独立裁决）",
            "",
            "2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上",
            "通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair",
            "由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与",
            "下方 passed 系列检验并列呈现，解读冲突时以本节为准。",
            "",
            "| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 |",
            "|------|------|-----------|---------|------------------|-----|--------|",
        ]
        for h in honest_comparisons:
            report_lines.append(
                f"| {h['metric']} | {h['comparison']} | {h['n_common']} | {h['n_diff']} "
                f"| {_fmt_stat_num(h['chi2'])} | {_fmt_stat_num(h['p'])} | {h['sig']} |"
            )

        report_lines += [
            "",
            "## 配对t检验结果",
            "",
            "| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |",
            "|------|--------|---------|-----|--------|-----------|--------|",
        ]

        for comp in comparisons:
            t_disp = _fmt_stat_num(comp["t_stat"])
            p_disp = _fmt_stat_num(comp["p_value"])
            d_disp = _fmt_stat_num(comp["cohens_d"])
            report_lines.append(
                f"| {comp['comparison']} | {comp['n_pairs']} | {t_disp} | {p_disp} | "
                f"{comp['sig']} | {d_disp} | {comp['effect']} |"
            )

        # R2：McNemar 配对检验落盘（此前仅打印控制台——二值配对的正确检验
        # 不进报告等于"算而未报"，报告读者只能看到口径错误的 t 检验）
        # 2026-10-05 P0：标题加"自指指标"限定——passed 系列仅作诊断参考，
        # 首要结论口径见上方"诚实指标 McNemar"节
        report_lines += [
            "",
            "## McNemar 配对检验（passed，自指指标——仅作诊断参考）",
            "",
            "R14 协议：二值配对数据（passed 0/1）的检验（Arcuri & Briand,",
            "ICSE 2011）。注意：passed 为系统自产测试在（未修复的）缺陷代码",
            "上的通过（自指口径，false_fix 主批次 89.8% 的直接来源），本节",
            "不作为架构增益主张的依据；与上方 t 检验并列呈现，t 检验表保持",
            "历史口径不变。",
            "",
            "| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |",
            "|------|-----------|-------------------|------------------|-----|--------|",
        ]
        for comp in comparisons:
            report_lines.append(
                f"| {comp['comparison']} | {comp['n_pairs']} "
                f"| {comp['mcnemar_n_concordant_diff']} | {_fmt_stat_num(comp['mcnemar_chi2'])} "
                f"| {_fmt_stat_num(comp['mcnemar_p'])} | {comp['mcnemar_sig']} |"
            )

        # R2：BH-FDR 多重比较校正落盘（多组同时检验时的假发现率控制）
        report_lines += [
            "",
            "## 多重比较校正（BH-FDR）",
            "",
            "对上表各 McNemar p 值做 Benjamini-Hochberg FDR 校正（α=0.05）；",
            "q 为校正后 p 值，拒绝 H0 表示校正后仍显著。",
            "",
            "| 比较 | 原始 p（McNemar） | BH-FDR q | 拒绝 H0 |",
            "|------|-------------------|----------|---------|",
        ]
        for comp in comparisons:
            reject_disp = "是" if comp.get("fdr_rejected") else "否"
            report_lines.append(
                f"| {comp['comparison']} | {_fmt_stat_num(comp['mcnemar_p'])} "
                f"| {_fmt_stat_num(comp.get('fdr_adjusted_p', float('nan')))} | {reject_disp} |"
            )

        # R2：bootstrap 置信区间落盘（点估计的不确定度量化）
        report_lines += [
            "",
            "## Bootstrap 95% 置信区间",
            "",
            "R2 协议：配对差值均值（AITester − 基线，逐任务 0/1 差）的有放回",
            "重采样百分位法 95% CI（默认 10000 次，random.Random(seed=42) 固定，",
            "结果逐位可复现）。CI 不含 0 即方向稳健。",
            "",
            "| 比较 | 配对数 | 差值均值 | 95% CI 下界 | 95% CI 上界 | 重采样次数 | seed |",
            "|------|--------|---------|------------|------------|-----------|------|",
        ]
        for comp in comparisons:
            report_lines.append(
                f"| {comp['comparison']} | {comp['n_pairs']} "
                f"| {_fmt_stat_num(comp['bootstrap_mean_diff'])} | {_fmt_stat_num(comp['bootstrap_ci_low'])} "
                f"| {_fmt_stat_num(comp['bootstrap_ci_high'])} "
                f"| {comp['bootstrap_n_resamples']} | {comp['bootstrap_seed']} |"
            )

        # R2：效应量对比落盘（Cohen's d 与 Cliff's δ 并列；δ 为非参数口径，
        # 零方差差值下 d 退化为 ±inf 而 δ 仍有界）
        report_lines += [
            "",
            "## 效应量对比（Cohen's d 与 Cliff's δ）",
            "",
            "R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；",
            "阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。",
            "",
            "| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |",
            "|------|-----------|--------|-----------|--------|",
        ]
        for comp in comparisons:
            report_lines.append(
                f"| {comp['comparison']} | {_fmt_stat_num(comp['cohens_d'])} | {comp['effect']} "
                f"| {_fmt_stat_num(comp['cliffs_delta'])} | {comp['cliffs_effect']} |"
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
            "- Cohen's d（配对差值口径）：",
            "  - `negligible`: |d| < 0.2",
            "  - `small`: 0.2 ≤ |d| < 0.5",
            "  - `medium`: 0.5 ≤ |d| < 0.8",
            "  - `large`: |d| ≥ 0.8",
            "- Cliff's δ（R2，非参数，Romano et al. 2006）：",
            "  - `negligible`: |δ| < 0.147",
            "  - `small`: 0.147 ≤ |δ| < 0.33",
            "  - `medium`: 0.33 ≤ |δ| < 0.474",
            "  - `large`: |δ| ≥ 0.474",
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


def main() -> None:
    """R2：命令行入口（--batches 批次白名单；未提供时行为与历史完全一致）。

    参数：
        --results-dir: 实验结果目录（默认 experiments/results）
        --output: Markdown 报告输出路径（默认 experiments/statistical_report.md）
        --batches: 逗号分隔的批次文件白名单（相对 --results-dir 的路径，
            如 main_batch/benchmark_a.json,main_batch/benchmark_b.json）。
            显式指定后仅纳入这些文件（dataset 非 synthetic 的仍会被
            _load_batch_file 过滤），报告头部"数据来源"章节记录实际
            纳入清单（审计用）；未提供时保持递归 glob 全目录行为不变。
    """
    parser = argparse.ArgumentParser(description="统计显著性检验（R2 统计协议完整性）")
    parser.add_argument("--results-dir", default="experiments/results", help="实验结果目录（默认 experiments/results）")
    parser.add_argument(
        "--output",
        default="experiments/statistical_report.md",
        help="Markdown 报告输出路径（默认 experiments/statistical_report.md）",
    )
    parser.add_argument(
        "--batches",
        default=None,
        help="R2：逗号分隔的批次文件白名单（相对 --results-dir 的路径），"
        "仅纳入指定文件；未提供时递归 glob 全目录（历史行为）",
    )
    args = parser.parse_args()

    batch_files: list[str] | None = None
    if args.batches:
        batch_files = [p.strip() for p in args.batches.split(",") if p.strip()]
    run_all_statistics(args.results_dir, args.output, batch_files=batch_files)


if __name__ == "__main__":
    main()
