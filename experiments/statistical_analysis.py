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
from typing import Any

import numpy as np
import scipy.stats as stats

# 与 run_benchmark.py 一致的路径引导：本文件既可被作为包导入（experiments.statistical_analysis），
# 也可直接以脚本方式运行（python experiments/statistical_analysis.py）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Z9（2026-10-06 审查落地）：贝叶斯配对分析（Dirichlet 后验，纯 stdlib）。
# 与 NHST 并列呈现、不替换——详见 bayesian_paired.py 模块 docstring
# （方法学依据：Furia et al., TSE 2019 对 SE 实验 NHST 的批评）。
from experiments.bayesian_paired import bayesian_paired_analysis, interpret_bayes  # noqa: E402

# 参与对比的基线（AITester 完整管线 + 两个简化基线）
# AC4（2026-10-06 第十轮审查 T-P0-5 伴随修复）：plain_llm_df（检出优先
# 协议归因基线，X1）升为统计加载一等基线——生死实验（n=87×3 臂×3 种子）
# 的核心对比即 aitester vs plain_llm_df（−28pp），此前该臂被 _BASELINES
# 名单漏收，canonical 报告只能靠仓外脚本补对比（statistical_report_3seed_
# pooled.md 的已知缺口）。历史批次无该臂时自动空集，行为向后兼容。
_BASELINES = ("aitester", "plain_llm", "single_agent", "plain_llm_df")

# R17（2026-10-08 R2）：统计加载的数据集支持集。此前 _load_batch_file 硬编码
# dataset == "synthetic"，QuixBugs（E4 真实基准）批次被静默剔除 → E4 正式执行
# 时"统计报告无法生成"（P0 阻塞）。改为白名单判定并集中在此登记扩展点：
# 新增基准（如 BugsInPy / TestGenEval）在此加入即接入统计协议。
# 注意：SWE-bench 批次的 task_id 前缀与合成集冲突风险由调用侧 glob 路径隔离
# （历史注释所述），不在本支持集范围。
_SUPPORTED_DATASETS = frozenset({"synthetic", "quixbugs"})


def load_experiment_results(
    results_dir: str,
    batch_files: list[str] | None = None,
    allow_schema_mixed: bool = False,
    pool_seeds: bool = False,
) -> dict[str, list[dict]]:
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
    results, _ = load_experiment_results_with_sources(
        results_dir, batch_files, allow_schema_mixed=allow_schema_mixed, pool_seeds=pool_seeds
    )
    return results


def load_experiment_results_with_sources(
    results_dir: str,
    batch_files: list[str] | None = None,
    allow_schema_mixed: bool = False,
    pool_seeds: bool = False,
) -> tuple[dict[str, list[dict]], list[str]]:
    """R2（2026-10-05 审查）：加载实验结果并返回"实际纳入"的批次文件清单。

    与 load_experiment_results 同一套加载逻辑（该函数退化为薄壳委托，
    历史调用方零变化），额外返回审计信息：实际纳入统计的批次文件路径
    列表（按加载顺序 = mtime 降序，N5）。"实际纳入"口径：
    - 白名单模式：指定的文件中 dataset ∈ _SUPPORTED_DATASETS 且成功解析的
      （R17：支持集含 synthetic 与 quixbugs）；
    - glob 模式：递归扫描的 benchmark_*.json 中同样实际加载了数据的。
    - X2（P0-4b）：默认还要求 M1 schema 完备（结果行含 detection_rate，
      见 _batch_is_m1_schema_complete）；allow_schema_mixed=True 恢复
      历史"混批"口径。

    报告头部"数据来源"章节消费本清单（审计用：读者可核对 p 值背后
    恰好是哪些批次，避免混批次结论不可复现）。

    Args:
        results_dir: 实验结果目录路径
        batch_files: 批次文件白名单（相对 results_dir；None 时走 glob）
        allow_schema_mixed: X2——True 时纳入 schema 不完备批次（历史口径）

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
                if _load_batch_file(results, _bp, allow_schema_mixed=allow_schema_mixed, pool_seeds=pool_seeds):
                    included_files.append(_display_path(_bp))
        return results, included_files

    # 递归查找所有 benchmark JSON 文件（M13：确定性遍历；2026-10-05 P0：
    # 排序主键 = 文件名内嵌时间戳降序（实验属性，跨机可复算），mtime 兜底；
    # "最新批次先加载"使 _pair_by_task 首见去重语义成立；
    # R2：记录实际纳入的文件供"数据来源"审计章节消费；
    # X2：schema 不完备批次默认剔除（allow_schema_mixed 恢复历史口径））
    included_files.extend(
        _display_path(json_file)
        for json_file in _sort_batch_files_deterministic(results_path.glob("**/benchmark_*.json"))
        if _load_batch_file(results, json_file, allow_schema_mixed=allow_schema_mixed, pool_seeds=pool_seeds)
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


def _batch_is_m1_schema_complete(data: dict) -> bool:
    """X2（2026-10-05 审查 P0-4b）：批次是否携带 M1 诚实指标字段。

    判据：任一基线的任一 detail 行的 "detection_rate" **非 None**——键存在
    但全 None 的批次（如 main_batch/benchmark_synthetic_20261001_112528.json
    等 n=5 冒烟批次：schema 已落盘但 M1 三指标从未在该批次上计算）与
    M1 批次混合会把 None 行并入"detection 可测数"分母口径（历史报告
    "60 任务/可测 49"即 2 个 n=5 冒烟批次混入所致），故默认剔除。
    """
    for baseline_data in data.get("results", {}).values():
        if not isinstance(baseline_data, dict):
            continue
        for row in baseline_data.get("details", []):
            if isinstance(row, dict) and row.get("detection_rate") is not None:
                return True
    return False


def _load_batch_file(
    results: dict[str, list[dict]], json_file: Path, allow_schema_mixed: bool = False, pool_seeds: bool = False
) -> bool:
    """M13（2026-09-29 审查 P0）：加载单个批次文件并写入 results。

    仅纳入 dataset ∈ _SUPPORTED_DATASETS 的批次（R17：synthetic + quixbugs；
    口径见 load_experiment_results 的 2026-09-26 round9 注释）。

    X2（2026-10-05 审查 P0-4b）：默认同时要求批次为 M1 schema 完备
    （结果行含 detection_rate 键，见 _batch_is_m1_schema_complete）——
    schema 不完备的早期/冒烟批次默认剔除（warning 可见），历史混批口径
    可经 allow_schema_mixed=True 显式恢复。

    AB4（2026-10-06 生死实验方法学修复）：pool_seeds=True 时给每行
    task_id 加 `s<seed>__` 前缀（seed 取批次 provenance.seed；缺失时用
    文件名 stem 兜底）——多种子批次 task_id 跨种子同名（中性化命名，
    设计使然）不再被 _pair_by_task"最新批次优先"去重折叠成单种子
    （生死实验实测 3 种子 261 对折叠为 87 对）；同种子重复跑仍折叠
    （前缀相同，重跑协议语义保留）。

    Returns:
        该文件是否实际纳入（R2 审计口径：dataset 不在支持集、schema
        不完备（默认口径）或解析失败时返回 False，不进入"数据来源"清单）
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        dataset = data.get("dataset", "")
        # R17（2026-10-08 R2）：数据集白名单泛化——此前硬编码 synthetic-only，
        # 导致 QuixBugs（E4 真实基准阶梯）批次**无法进入统计协议**（E4 正式
        # 执行/出报告的前置阻塞）。现改为支持集判定，留扩展点 _SUPPORTED_DATASETS
        # （新增基准在此登记即接入，避免多点散改）。
        if dataset not in _SUPPORTED_DATASETS:
            return False
        if not allow_schema_mixed and not _batch_is_m1_schema_complete(data):
            print(
                f"警告：批次 {json_file.name} 无任何非 None 的 detection_rate 行——"
                "M1 指标未计算（早期/冒烟批次），默认剔除；如需历史混批口径传 "
                "--allow-schema-mixed"
            )
            return False
        _seed_prefix: str | None = None
        if pool_seeds:
            _seed = (data.get("provenance") or {}).get("seed")
            _seed_prefix = f"s{_seed}__" if _seed is not None else f"{json_file.stem}__"
        for baseline, baseline_data in data.get("results", {}).items():
            if baseline in results:
                details = baseline_data.get("details", [])
                if _seed_prefix is not None:
                    details = [{**row, "task_id": f"{_seed_prefix}{row.get('task_id', '')}"} for row in details]
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


# ----------------------------- AE2：成本口径（$/task，价目表驱动） -----------------------------


def load_price_table(path: str | Path | None) -> dict[str, dict[str, Any]]:
    """AE2（2026-10-06 第十一轮审查 N8）：加载 $/task 成本口径价目表。

    文件结构（experiments/price_table.json）::

        {"models": {"<model_name>": {"input_per_mtok": float | None,
                                     "output_per_mtok": float | None,
                                     "currency": "USD",
                                     "source": "<官方价目页 URL>",
                                     "as_of": "YYYY-MM-DD"}}}

    诚实条款：模型未登记或任一价格为 null → 该模型不参与成本计算
    （不编造价格）；文件缺失/解析失败/结构不符 → 返回空表（报告成本
    节降级为"价目未登记"提示，不阻断报告生成）。
    """
    if path is None:
        return {"models": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"警告：价目表 {path} 加载失败（成本节按未登记口径输出）: {e}")
        return {"models": {}}
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        return {"models": {}}
    return {"models": {str(k): v for k, v in models.items() if isinstance(v, dict)}}


def _model_is_priced(entry: Any) -> bool:
    """AE2：模型条目是否具备完整可用价目（in/out 均为非负数值）。"""
    if not isinstance(entry, dict):
        return False
    p_in = entry.get("input_per_mtok")
    p_out = entry.get("output_per_mtok")
    return all(isinstance(p, (int, float)) and not isinstance(p, bool) and p >= 0 for p in (p_in, p_out))


def cost_analysis(results: dict[str, list[dict]], price_table: dict[str, dict]) -> list[dict]:
    """AE2：按基线汇总 token_usage 并计算 $/task（None 安全，不编造价格）。

    行级口径：row["token_usage"]["input_tokens" / "output_tokens"]（缺失
    按 0 计，行本身仍计入任务数分母）；模型归属按 row["token_usage"]
    ["by_model"]（模型名 → 该任务 token 总数）。成本计算采用基线级
    in/out 拆分（sum(input) × 输入单价 + sum(output) × 输出单价）——
    当基线内出现**多个价目不同**的模型时，行级 in/out 无法按模型拆分
    归属，此时成本诚实降级为 None（宁缺毋错）；缺 by_model 但有总
    token 的行计入 token 汇总但不计入成本（unattributed_tokens 披露）。

    Returns:
        每个 baseline 一行（按 baseline 名排序）：{baseline, n_tasks,
        input_tokens, output_tokens, by_model, missing_models,
        unattributed_tokens, cost, cost_per_task, currency, priced}
    """
    models = price_table.get("models", {}) if isinstance(price_table, dict) else {}
    cost_rows: list[dict] = []
    for baseline in sorted(results):
        rows = results[baseline] or []
        input_total = 0
        output_total = 0
        unattributed = 0
        by_model: dict[str, int] = {}
        for row in rows:
            tu = row.get("token_usage")
            if not isinstance(tu, dict):
                continue
            input_total += tu.get("input_tokens") or 0
            output_total += tu.get("output_tokens") or 0
            bm = tu.get("by_model")
            if isinstance(bm, dict) and bm:
                for model_name, tokens in bm.items():
                    by_model[str(model_name)] = by_model.get(str(model_name), 0) + (tokens or 0)
            elif (tu.get("total_tokens") or 0) > 0:
                unattributed += tu.get("total_tokens") or 0
        used_models = [m for m, t in by_model.items() if t > 0]
        missing = sorted(m for m in used_models if not _model_is_priced(models.get(m)))
        cost: float | None = None
        currency: str | None = None
        if used_models and not missing:
            price_pairs = {(models[m].get("input_per_mtok"), models[m].get("output_per_mtok")) for m in used_models}
            currencies = {models[m].get("currency") or "USD" for m in used_models}
            # 单一价目组合（常见：单模型批次）才可按基线级 in/out 拆分计价
            if len(price_pairs) == 1 and len(currencies) == 1:
                p_in, p_out = price_pairs.pop()
                cost = input_total / 1_000_000 * float(p_in) + output_total / 1_000_000 * float(p_out)
                currency = currencies.pop()
        cost_per_task = cost / len(rows) if cost is not None and rows else None
        cost_rows.append(
            {
                "baseline": baseline,
                "n_tasks": len(rows),
                "input_tokens": input_total,
                "output_tokens": output_total,
                "by_model": by_model,
                "missing_models": missing,
                "unattributed_tokens": unattributed,
                "cost": cost,
                "cost_per_task": cost_per_task,
                "currency": currency,
                "priced": cost is not None,
            }
        )
    return cost_rows


def cost_per_detection(cost_per_task: float | None, det_rate_pct: float | None) -> float | None:
    """AN5：$/detection 推导——成本/任务 ÷ 检出率（检出优先口径的成本对偶）。

    领域口径对齐 SWE-bench 生态的 $/resolved（2026 六前沿模型同分位展布
    $0.46–$74）：本项目的自然对偶是"每检出一个缺陷的成本"。

    任一输入缺失（未计价 / 检出率为 0 或 None）→ None（诚实降级为 "—"）；
    检出率 0% 在语义上是 ∞，不得显示为有限数字误导读者。

    Args:
        cost_per_task: 每任务成本（cost_analysis 产物，None = 未计价）。
        det_rate_pct: detection 率百分比（stats_summary["det_rate"] 口径，
            0-100；None = 无可测行）。

    Returns:
        $/detection 数值；不可推导时 None。
    """
    if cost_per_task is None or det_rate_pct is None or det_rate_pct <= 0:
        return None
    return cost_per_task / (det_rate_pct / 100.0)


# ─── 修复引擎批次 IX（ADR-0023）：pass@k / $/solved / 污染视角 ────────────────


def _pass_at_k_value(n: int, c: int, k: int) -> float | None:
    """标准 pass@k（HumanEval 官方口径的无偏估计）。

    pass@k = 1 - ∏_{i=n-c+1}^{n} (1 - k/i)（k > n-c 时恒 1.0）；
    k > n 时无定义（采样不足）→ None。
    """
    if k > n or k < 1:
        return None
    if n - c < k:
        return 1.0
    prod = 1.0
    for i in range(n - c + 1, n + 1):
        prod *= 1.0 - k / i
    return 1.0 - prod


def pass_at_k_summary(data: dict[str, list[dict]], field: str = "patch_correct") -> dict[str, dict[str, Any]]:
    """批次 IX（ADR-0023）：按臂的 pass@k（多轮采样并集解决率）。

    口径：同 task_id 的跨批次行 = 同一任务的多个采样轮次（默认加载
    模式保留全部轮次行）；行级成功 = row[field] 真值（patch_correct =
    gold 独立裁决主口径；passed = 自指口径仅供对照）。k 上界取全臂
    各任务轮次数的最小值（轮次不足 k 的任务无法参与该档，诚实截断）
    并披露轮次分布（min/中位/max）。

    注意（ADR-0021 披露义务）：存量批次的 patch_correct 恒 0（围栏
    伪影）——存量数据下本节的 correct 口径 pass@k 无信息量，修复后
    跑批起有效；存量修正数字用 make repair-replay。
    """
    summary: dict[str, dict[str, Any]] = {}
    for baseline in sorted(data):
        rounds_by_task: dict[str, list[bool]] = {}
        for row in data[baseline] or []:
            tid = str(row.get("task_id", ""))
            if not tid:
                continue
            val = row.get(field)
            if val is None:
                continue  # 不可测行不入轮次（M1 None 口径一致）
            rounds_by_task.setdefault(tid, []).append(bool(val))
        if not rounds_by_task:
            summary[baseline] = {"n_tasks": 0}
            continue
        ns = [len(v) for v in rounds_by_task.values()]
        cs = [sum(v) for v in rounds_by_task.values()]
        n_min, n_max = min(ns), max(ns)
        n_median = sorted(ns)[len(ns) // 2]
        k_values = sorted({k for k in (1, 2, 3, 5, 10) if k <= n_min})
        table: dict[int, float | None] = {}
        for k in k_values:
            per_task = [_pass_at_k_value(n_i, c_i, k) for n_i, c_i in zip(ns, cs, strict=True)]
            vals = [v for v in per_task if v is not None]
            table[k] = (sum(vals) / len(vals)) if vals else None
        summary[baseline] = {
            "n_tasks": len(rounds_by_task),
            "rounds_min": n_min,
            "rounds_median": n_median,
            "rounds_max": n_max,
            "pass_at": table,
        }
    return summary


def _pass_at_k_report_lines(summary: dict[str, dict[str, Any]], field_label: str) -> list[str]:
    """pass@k 章节 Markdown 行。"""
    lines = [
        "| 基线 | 任务数 | 轮次 (min/中位/max) | " + " | ".join(f"pass@{k}" for k in (1, 2, 3, 5, 10)) + " |",
        "|---|---|---|" + "---|" * 5,
    ]
    for baseline, s in summary.items():
        if not s.get("n_tasks"):
            lines.append(f"| {baseline} | 0 | — | — | — | — | — | — |")
            continue
        rounds = f"{s['rounds_min']}/{s['rounds_median']}/{s['rounds_max']}"
        cells = []
        for k in (1, 2, 3, 5, 10):
            v = s["pass_at"].get(k)
            cells.append(f"{v:.4f}" if isinstance(v, float) else "—")
        lines.append(f"| {baseline} | {s['n_tasks']} | {rounds} | " + " | ".join(cells) + " |")
    return lines


def cost_per_solved(cost_rows: list[dict], data: dict[str, list[dict]]) -> dict[str, float | None]:
    """批次 IX（ADR-0023）：$/solved task——总成本 ÷ gold 裁决 correct 总数。

    与 $/task 的区别：分母从任务数换成 patch_correct=1 的行数（SWE-bench
    生态 $/resolved 对齐）。correct=0（未解决任何任务）→ None（语义 ∞，
    与 cost_per_detection 的诚实降级同口径）；未计价 → None。
    存量批次 correct 恒 0 系 ADR-0021 伪影，修复后跑批起有效。
    """
    out: dict[str, float | None] = {}
    for row in cost_rows:
        baseline = row.get("baseline")
        cost = row.get("cost")
        rows = data.get(baseline) or []
        solved = sum(1 for r in rows if r.get("patch_correct") == 1)
        if cost is None or solved == 0:
            out[baseline] = None
        else:
            out[baseline] = cost / solved
    return out


def contamination_view_summary(data: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
    """批次 IX（ADR-0023）：污染视角按臂聚合（行级 contamination_risk_level）。

    行级来源：run_benchmark._compute_contamination_risk_level 写回的
    contamination_risk_level（high/medium/low/unknown/not_applicable）。
    聚合：各档计数 + 含污染（high/medium）vs 干净（low）的 passed 率
    对照（not_applicable/unknown 不入两组分母，诚实披露）。
    """
    summary: dict[str, dict[str, Any]] = {}
    for baseline in sorted(data):
        counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0, "not_applicable": 0}
        cont_pass = cont_n = clean_pass = clean_n = 0
        for row in data[baseline] or []:
            level = row.get("contamination_risk_level") or "unknown"
            counts[level] = counts.get(level, 0) + 1
            if level in ("high", "medium"):
                cont_n += 1
                cont_pass += 1 if row.get("passed") else 0
            elif level == "low":
                clean_n += 1
                clean_pass += 1 if row.get("passed") else 0
        summary[baseline] = {
            "counts": counts,
            "contaminated_passed_rate": round(cont_pass / cont_n, 4) if cont_n else None,
            "clean_passed_rate": round(clean_pass / clean_n, 4) if clean_n else None,
        }
    return summary


def _contamination_view_report_lines(summary: dict[str, dict[str, Any]]) -> list[str]:
    """污染视角章节 Markdown 行。"""
    lines = [
        "| 基线 | high | medium | low | unknown | not_applicable | 含污染 passed 率 | 干净 passed 率 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for baseline, s in summary.items():
        c = s["counts"]
        cp = s["contaminated_passed_rate"]
        kp = s["clean_passed_rate"]
        lines.append(
            f"| {baseline} | {c.get('high', 0)} | {c.get('medium', 0)} | {c.get('low', 0)} "
            f"| {c.get('unknown', 0)} | {c.get('not_applicable', 0)} "
            f"| {cp if cp is not None else '—'} | {kp if kp is not None else '—'} |"
        )
    return lines


def mutation_reliability_summary(data: dict[str, list[dict]]) -> dict[str, dict[str, float | int | None]]:
    """AN2：按臂聚合 mutation_detection_rate（测试套件可靠性）。

    行级来源：run_benchmark ENABLE_MUTATION_SCORING 写回的
    mutation_detection_rate（float | None——None = 不可测：缺 gold fixed
    材料 / 生成测试在 gold fixed 上不绿 / 无变异体，保守不误报 0）与
    mutants_killed / mutants_total 占位对。聚合口径：可测行均值（百分比）
    + 可测率分母（None 不进分母，M1 同则）+ 杀灭/变异体合计。

    Returns:
        baseline → {n_total, n_measurable, mean_pct（None=无可测行）,
        mutants_killed, mutants_total}（按 baseline 名排序）。
    """
    summary: dict[str, dict[str, float | int | None]] = {}
    for baseline in sorted(data):
        rows = data[baseline] or []
        vals = [r["mutation_detection_rate"] for r in rows if r.get("mutation_detection_rate") is not None]
        killed = sum(int(r.get("mutants_killed") or 0) for r in rows)
        total = sum(int(r.get("mutants_total") or 0) for r in rows)
        summary[baseline] = {
            "n_total": len(rows),
            "n_measurable": len(vals),
            "mean_pct": (sum(vals) / len(vals) * 100.0) if vals else None,
            "mutants_killed": killed,
            "mutants_total": total,
        }
    return summary


def _mutation_report_lines(mutation_summary: dict[str, dict]) -> list[str]:
    """AN2：测试套件可靠性章节 Markdown 行（呈现性增补，非主终点变更）。

    与 SWE-Mutation（2026）的"变异分作为 LLM 测试套件可靠性主信号"口径
    同向：检出优先协议下，测试有效性需要独立于 detection 的客观测量。
    """
    lines = [
        "口径：mutation_detection_rate = 生成的测试在 gold 修复代码上全绿、且在其",
        "AST 变异体上变红的比例（ENABLE_MUTATION_SCORING 写回；None = 不可测，",
        "按不可测跳过不进分母——保守不误报 0）。领域口径与 SWE-Mutation（2026）",
        "的测试套件可靠性主信号同向：检出优先协议下，测试有效性需要独立于",
        "detection 的客观测量（变异检出提供该测量，纯子进程零 LLM）。",
        "**呈现性增补（AN2，2026-10-07）**：本节为报告呈现口径，非预注册主终点",
        "变更；主终点仍为 detection 配对差（见预注册）。增补时点早于 E2 数据产生。",
        "",
        "| Baseline | 可测行 | 总行 | 均值 (%) | 杀灭/变异体合计 |",
        "|----------|--------|------|----------|-----------------|",
    ]
    for baseline, s in mutation_summary.items():
        mean_disp = f"{s['mean_pct']:.2f}" if s["mean_pct"] is not None else "—"
        lines.append(
            f"| {baseline} | {s['n_measurable']} | {s['n_total']} | {mean_disp} | {s['mutants_killed']}/{s['mutants_total']} |"
        )
    if all(s["n_measurable"] == 0 for s in mutation_summary.values()):
        lines += ["", "注：全部臂无可测行——本批该指标不可测（诚实披露，而非 0 检出）。"]
    return lines


def _cost_report_lines(
    cost_rows: list[dict], price_table: dict[str, dict], det_rates: dict[str, float] | None = None
) -> list[str]:
    """AE2：报告成本章节 Markdown 行；AN5：可选 $/detection 推导列。

    价目齐全 → 输出 $/task 表；价目缺失 → 诚实降级为"未登记"提示并
    列出待计价模型清单（绝不编造价格）。历史报告不回写：本节仅在
    新报告生成时出现。

    AN5（2026-10-07 第十四轮审查 N5）：det_rates（baseline → detection
    率百分比，stats_summary["det_rate"] 口径 0-100）非 None 时表格追加
    "成本/检出"列（= cost_per_task ÷ (det_rate/100)，推导见
    cost_per_detection）并附口径说明——呈现性增补，非新测量；
    det_rates=None（缺省）时输出与 AE2 逐位一致的历史格式（向后兼容）。
    """
    lines = [
        "成本口径：$/task = (Σ输入 token × 输入单价 + Σ输出 token × 输出单价) / 任务数；",
        "价目来自 experiments/price_table.json（模型级登记，含来源与生效日期）；",
        "token 行级来源 = 结果行 token_usage（input_tokens / output_tokens）；",
        "多模型异价的基线无法按 in/out 拆分归属，成本诚实降级为未计价（—）。",
    ]
    if det_rates is not None:
        lines += [
            "$/detection（成本/检出）= $/task ÷ 检出率——AN5 呈现性推导（两次已登记",
            "测量的商，非独立测量；领域口径对齐 SWE-bench 生态 $/resolved）。检出率",
            "0% 的基线该列为 —（语义上趋于无穷，不得显示为有限数字）。",
        ]
    priced = [r for r in cost_rows if r["priced"]]
    if not priced:
        models_seen = sorted({m for r in cost_rows for m, t in r["by_model"].items() if t > 0})
        lines += [
            "",
            "**价目未登记**——本报告不含 $/task 数字（诚实条款：不编造价格）。",
            f"待计价模型：{', '.join(models_seen) if models_seen else '（无 token 观测）'}。",
            "补齐方式：在 experiments/price_table.json 对应模型条目填入",
            "input_per_mtok / output_per_mtok / source / as_of 后重跑本脚本。",
        ]
        return lines
    if det_rates is None:
        lines += [
            "",
            "| Baseline | 任务数 | 输入 token | 输出 token | 成本/任务 | 币种 |",
            "|----------|--------|-----------|-----------|-----------|------|",
        ]
        for r in cost_rows:
            cpt = f"{r['cost_per_task']:.4f}" if r["cost_per_task"] is not None else "—"
            cur = r["currency"] or "—"
            lines.append(
                f"| {r['baseline']} | {r['n_tasks']} | {r['input_tokens']} | {r['output_tokens']} | {cpt} | {cur} |"
            )
    else:
        lines += [
            "",
            "| Baseline | 任务数 | 输入 token | 输出 token | 成本/任务 | 成本/检出 | 币种 |",
            "|----------|--------|-----------|-----------|-----------|-----------|------|",
        ]
        for r in cost_rows:
            cpt = f"{r['cost_per_task']:.4f}" if r["cost_per_task"] is not None else "—"
            cpd_val = cost_per_detection(r["cost_per_task"], det_rates.get(r["baseline"]))
            cpd = f"{cpd_val:.4f}" if cpd_val is not None else "—"
            cur = r["currency"] or "—"
            lines.append(
                f"| {r['baseline']} | {r['n_tasks']} | {r['input_tokens']} | {r['output_tokens']} "
                f"| {cpt} | {cpd} | {cur} |"
            )
    partial = [r for r in cost_rows if not r["priced"]]
    if partial:
        missing_desc = "；".join(f"{r['baseline']}（缺: {', '.join(r['missing_models'])}）" for r in partial)
        lines += ["", f"注：{len(partial)} 个基线未计价——{missing_desc}。"]
    return lines


def run_all_statistics(
    results_dir: str,
    output_file: str | None = None,
    batch_files: list[str] | None = None,
    allow_schema_mixed: bool = False,
    pool_seeds: bool = False,
    price_table: dict[str, dict] | None = None,
) -> list[dict]:
    """
    运行所有统计检验并生成报告

    Args:
        results_dir: 实验结果目录
        output_file: Markdown 报告输出路径（None 时仅打印控制台，不落盘）
        batch_files: R2 可选的批次文件白名单（相对 results_dir 的路径，
            透传 load_experiment_results_with_sources；None 时保持历史
            glob 全目录行为不变）
        allow_schema_mixed: X2（P0-4b）——True 时纳入 schema 不完备批次
            （结果行缺 detection_rate 的早期/冒烟批次；历史混批口径）。
            默认 False：仅纳入 M1 schema 完备批次，防 None/缺失行混入
            诚实指标分母（"detection 可测数"口径失真）。
        pool_seeds: AB4（2026-10-06）——多种子拼接口径（task_id 按批次
            seed 加前缀，多种子批次不再被去重折叠；语义见
            load_experiment_results docstring）。
        price_table: AE2（2026-10-06）——价目表（load_price_table 产物，
            {"models": {...}}）；None 时按"价目未登记"口径输出成本节
            （诚实降级，不编造价格）。

    Returns:
        比较结果列表，每项含 comparison / n_pairs / t_stat / p_value / sig /
        cohens_d / effect，以及 R14 的 mcnemar_* / fdr_* 与 R2 的
        cliffs_delta / cliffs_effect / bootstrap_* 字段
    """
    print("=" * 70)
    print("统计显著性检验报告")
    print("=" * 70)

    # 加载数据（R2：同时取"实际纳入"的批次清单，供审计章节与控制台输出）
    data, source_files = load_experiment_results_with_sources(
        results_dir, batch_files, allow_schema_mixed=allow_schema_mixed, pool_seeds=pool_seeds
    )
    _mode = "白名单" if batch_files is not None else "glob 全目录"
    _pool_note = "，多种子拼接（seed 前缀）" if pool_seeds else ""
    print(f"\n数据来源：{len(source_files)} 个批次文件（{_mode}模式{_pool_note}）")
    for _src in source_files:
        print(f"  - {_src}")

    # AE2（2026-10-06 第十一轮审查 N8）：$/task 成本口径（价目表驱动，
    # 价目缺失时诚实降级；None 参数 → "价目未登记"口径）
    _effective_price_table = price_table if price_table is not None else {"models": {}}
    cost_rows = cost_analysis(data, _effective_price_table)
    _priced_n = sum(1 for r in cost_rows if r["priced"])
    print(f"成本口径（AE2）：{_priced_n}/{len(cost_rows)} 基线价目齐全（$/task 见报告成本节）")

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
    for baseline in ("plain_llm", "single_agent", "plain_llm_df"):
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

        # Z9：贝叶斯配对后验（与 McNemar 并列呈现；n=50 级样本量下 p 值
        # 无分辨力时，后验直接量化效应量不确定度——P(δ>0) 与 ROPE 概率）
        _bayes = bayesian_paired_analysis(data["aitester"], data[baseline], field="passed")
        comparisons[-1].update(
            {
                "bayes_mean_diff": _bayes["post_mean"],
                "bayes_ci_low": _bayes["ci_low"],
                "bayes_ci_high": _bayes["ci_high"],
                "bayes_p_greater": _bayes["p_greater"],
                "bayes_p_rope": _bayes["p_rope"],
                "bayes_verdict": interpret_bayes(_bayes),
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
        # Z9：贝叶斯配对后验（并列呈现；δ = AITester − 基线的后验边际差）
        if comparisons[-1].get("bayes_p_greater") is not None:
            print(
                f"  贝叶斯后验（Dirichlet，MC seed=42）: δ均值="
                f"{_fmt_stat_num(comparisons[-1]['bayes_mean_diff'])}, "
                f"95% CI [{_fmt_stat_num(comparisons[-1]['bayes_ci_low'])}, "
                f"{_fmt_stat_num(comparisons[-1]['bayes_ci_high'])}], "
                f"P(δ>0)={comparisons[-1]['bayes_p_greater']:.4f}, "
                f"P(ROPE)={comparisons[-1]['bayes_p_rope']:.4f} "
                f"({comparisons[-1]['bayes_verdict']})"
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
        for baseline in ("plain_llm", "single_agent", "plain_llm_df"):
            if stats_summary[baseline]["n"] == 0:
                continue
            h_chi2, h_p, h_ndiff, h_ncommon = mcnemar_test(data["aitester"], data[baseline], field=metric_field)
            # Z9：诚实指标的贝叶斯配对后验（与 McNemar 并列；detection/repair
            # 的 0.0/1.0 逐任务值直接构成列联表，None 无 gold 材料任务已跳过）
            h_bayes = bayesian_paired_analysis(data["aitester"], data[baseline], field=metric_field)
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
                    "bayes_mean": h_bayes["post_mean"],
                    "bayes_ci_low": h_bayes["ci_low"],
                    "bayes_ci_high": h_bayes["ci_high"],
                    "bayes_p_greater": h_bayes["p_greater"],
                    "bayes_p_rope": h_bayes["p_rope"],
                    "bayes_verdict": interpret_bayes(h_bayes),
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
            if h.get("bayes_p_greater") is not None:
                print(
                    f"    贝叶斯后验: δ均值={_fmt_stat_num(h['bayes_mean'])}, "
                    f"95% CI [{_fmt_stat_num(h['bayes_ci_low'])}, {_fmt_stat_num(h['bayes_ci_high'])}], "
                    f"P(δ>0)={h['bayes_p_greater']:.4f}, P(ROPE)={h['bayes_p_rope']:.4f} "
                    f"({h['bayes_verdict']})"
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
        # X2（P0-4b）：allow_schema_mixed 时复算命令须带同名旗标（否则
        # 默认口径会剔除 schema 不完备批次，数值不可复现）
        _recompute_cmd = (
            "python experiments/statistical_analysis.py "
            f"--results-dir {results_dir} --output <report.md>"
            + (f" --batches {','.join(source_files)}" if source_files else "")
            + (" --allow-schema-mixed" if allow_schema_mixed else "")
            + (" --pool-seeds" if pool_seeds else "")
        )
        report_lines += [
            "",
            f"复算命令（工件与代码齐备时数值逐位可复现）：`{_recompute_cmd}`",
            "",
            "去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次",
            "文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。",
        ]
        if pool_seeds:
            report_lines += [
                "",
                "AB4 多种子拼接口径（--pool-seeds）：行 task_id 已按批次",
                "provenance.seed 加 `s<seed>__` 前缀——多种子批次（task_id 跨种子",
                "同名是中性化命名的设计使然）按种子分层全量进入配对检验；同种子",
                "重复跑仍按上述去重口径折叠（重跑协议语义保留）。",
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

        # Z9（2026-10-06 审查落地）：贝叶斯配对分析落盘——n=50 级样本量下
        # NHST p 值无分辨力（"不显著"≠"无差异"），后验分布直接量化效应量
        # 不确定度。诚实指标（detection/repair）与 passed（自指，仅诊断）
        # 并列呈现；解读冲突时与 McNemar 节同序——以诚实指标为准。
        report_lines += [
            "",
            "## 贝叶斯配对分析（Z9，Dirichlet 后验——与 NHST 并列）",
            "",
            "Z9 协议：配对二值列联表 (n11, n01, n10, n00) 上取均匀先验的",
            "Dirichlet 后验，报告边际差 δ = p(AITester) − p(基线) 的后验均值、",
            "95% 可信区间、P(δ>0) 与 ROPE 概率（|δ| ≤ 0.05 视为实践等价）。",
            "Monte Carlo 20000 次、random.Random(seed=42)（纯 stdlib，逐位可复现）。",
            "结论标签：bayes_pos / bayes_neg（方向稳健）、bayes_equiv（实践等价）、",
            "bayes_inconclusive（证据不足——小样本最常见结局，诚实标注而非",
            "强行二分）。方法学依据：Furia et al., TSE 2019（arXiv:1811.05422）。",
            "",
            "### 诚实指标（首要结论口径）",
            "",
            "| 指标 | 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |",
            "|------|------|-----------|--------|--------|---------|------|",
        ]
        for h in honest_comparisons:
            if h.get("bayes_mean") is None:
                continue
            report_lines.append(
                f"| {h['metric']} | {h['comparison']} | {_fmt_stat_num(h['bayes_mean'])} "
                f"| [{_fmt_stat_num(h['bayes_ci_low'])}, {_fmt_stat_num(h['bayes_ci_high'])}] "
                f"| {h['bayes_p_greater']:.4f} | {h['bayes_p_rope']:.4f} | {h['bayes_verdict']} |"
            )
        report_lines += [
            "",
            "### passed（自指指标，仅作诊断参考）",
            "",
            "| 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |",
            "|------|-----------|--------|--------|---------|------|",
        ]
        for comp in comparisons:
            if comp.get("bayes_mean_diff") is None:
                continue
            report_lines.append(
                f"| {comp['comparison']} | {_fmt_stat_num(comp['bayes_mean_diff'])} "
                f"| [{_fmt_stat_num(comp['bayes_ci_low'])}, {_fmt_stat_num(comp['bayes_ci_high'])}] "
                f"| {comp['bayes_p_greater']:.4f} | {comp['bayes_p_rope']:.4f} | {comp['bayes_verdict']} |"
            )

        # AE2（2026-10-06 第十一轮审查 N8）：$/task 成本口径章节——价目表
        # 驱动，价目缺失时诚实降级为"未登记"提示（不编造价格）。历史
        # 报告不回写：本节仅在新报告生成时出现。
        # AN5（2026-10-07 第十四轮审查 N5）：追加 $/detection 推导列——
        # 呈现性增补（两次已登记测量的商），主终点与判定规则不变。
        report_lines += ["", "## 成本口径（$/task，价目表驱动——AE2）", ""]
        _det_rates = {b: s["det_rate"] for b, s in stats_summary.items()}
        report_lines += _cost_report_lines(cost_rows, _effective_price_table, det_rates=_det_rates)

        # AN2（2026-10-07 第十四轮审查 N2）：测试套件可靠性章节——
        # mutation_detection_rate 按臂聚合（SWE-Mutation 2026 口径对齐）；
        # 呈现性增补，增补时点早于 E2 数据产生，主终点不变。
        report_lines += [
            "",
            "## 测试套件可靠性（mutation_detection_rate 按臂聚合——AN2 呈现性增补）",
            "",
        ]
        report_lines += _mutation_report_lines(mutation_reliability_summary(data))

        # 修复引擎批次 IX（ADR-0023，呈现性增补）：pass@k / $/solved /
        # 污染视角三节——多轮采样并集解决率、每解决一任务的成本、
        # 含污染 vs 干净样本对照。主终点与判定规则零变化。
        # 披露义务（ADR-0021）：存量批次 patch_correct 恒 0 系围栏伪影，
        # correct 口径的 pass@k 与 $/solved 须以修复后跑批解读；存量修正
        # 数字用 make repair-replay。
        report_lines += [
            "",
            "## pass@k（多轮采样并集解决率——批次 IX / ADR-0023 呈现性增补）",
            "",
            "口径：同任务跨批次行 = 采样轮次；成功 = patch_correct（gold 独立裁决）。",
            "k 上界 = 各任务轮次数的最小值（轮次不足诚实截断为 —）。",
            "",
        ]
        report_lines += _pass_at_k_report_lines(pass_at_k_summary(data, field="patch_correct"), "patch_correct")
        report_lines += [
            "",
            "> 注：存量批次的 patch_correct 恒 0 系 ADR-0021 围栏伪影——本节",
            "> correct 口径以修复后跑批解读；存量修正数字见 `make repair-replay`。",
            "",
            "## $/solved task（每解决一任务成本——批次 IX / ADR-0023）",
            "",
        ]
        _solved_costs = cost_per_solved(cost_rows, data)
        for _b in sorted(_solved_costs):
            _v = _solved_costs[_b]
            _cell = f"{_v:.6f}" if _v is not None else "未定义（correct=0 或未计价）——与 $/detection 同口径诚实降级"
            report_lines.append("- " + _b + ": " + _cell)
        report_lines += [
            "",
            "## 污染视角（contamination_risk_level 按臂聚合——批次 IX / ADR-0023）",
            "",
        ]
        report_lines += _contamination_view_report_lines(contamination_view_summary(data))
        report_lines += [
            "",
            "> 口径：行级三维相似度（token Jaccard + AST 骨架 LCS + 语义词袋）",
            "> 综合分级；含污染组成功率显著高于干净组（Δ≥0.2）时，结果归因",
            "> 须剔除含污染样本单独报告（experiments/contamination_check.py）。",
            "",
        ]

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


def _icc_one_way_binary(values_by_cluster: dict[Any, list[float]]) -> float | None:
    """AC4（2026-10-06 第十轮审查 T-P0-5）：单因素随机效应 ICC(1,1)（ANOVA 估计量）。

    用于二值观测（detection 0/1）按模板聚类的组内相关估计——多种子
    拼接口径下同模板任务跨种子是相关观测（261 对 McNemar 的独立性假设
    需以设计效应校正做敏感性检验）。负估计量裁剪到 0（保守）；
    退化解（单簇 / 全同值 / k<2）返回 None。
    """
    clusters = [v for v in values_by_cluster.values() if len(v) > 0]
    k = len(clusters)
    n_total = sum(len(c) for c in clusters)
    if k < 2 or n_total <= k:
        return None
    grand = sum(sum(c) for c in clusters) / n_total
    msb = sum(len(c) * (sum(c) / len(c) - grand) ** 2 for c in clusters) / (k - 1)
    msw = sum(sum((x - sum(c) / len(c)) ** 2 for x in c) for c in clusters) / (n_total - k)
    n0 = (n_total - sum(len(c) ** 2 for c in clusters) / n_total) / (k - 1)
    denom = msb + (n0 - 1) * msw
    if denom <= 0:
        return None
    return max(0.0, (msb - msw) / denom)


def _exact_sign_test_p(wins_a: int, wins_b: int) -> float:
    """精确双侧符号检验 p 值（二项分布，n=wins_a+wins_b，p=0.5）。"""
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    from math import comb

    tail = sum(comb(n, i) for i in range(min(wins_a, wins_b) + 1))
    return min(1.0, 2.0 * tail / (2**n))


def _rows_pattern_name(row: dict) -> Any:
    """提取行级模板标识（task_metadata.pattern_name；缺失→None）。"""
    md = row.get("task_metadata") or {}
    return md.get("pattern_name")


def template_cluster_sensitivity(
    rows_a: list[dict],
    rows_b: list[dict],
    label_a: str,
    label_b: str,
) -> str:
    """AC4：模板聚类稳健敏感性分析（单对比，返回 Markdown 段）。

    内容：
    1. 逐对 McNemar（与规范 _pair_by_task 同口径的二值 discordant 计数）
       + 设计效应校正后的保守 χ²（χ²_adj = χ² × n_eff/n，DEFF=1+(m̄-1)·ICC）；
    2. 模板级聚合配对符号检验（每模板臂内 detection 均值，公共模板
       逐一比较胜负，精确二项 p）——完全摆脱逐对独立性假设的非参数口径。

    仅消费行级 detection_rate 与 task_metadata.pattern_name；缺失
    pattern_name 的行按 "unknown" 簇处理（敏感性口径，不丢弃观测）。
    """
    lines = [f"### {label_a} vs {label_b}（模板聚类稳健敏感性）", ""]

    def _binary(rows: list[dict]) -> dict[Any, float]:
        out: dict[Any, float] = {}
        for r in rows:
            det = r.get("detection_rate")
            if det is None:
                continue
            out[r.get("task_id")] = 1.0 if det > 0 else 0.0
        return out

    bin_a, bin_b = _binary(rows_a), _binary(rows_b)
    common = sorted(set(bin_a) & set(bin_b), key=str)
    b_cnt = sum(1 for t in common if bin_a[t] > bin_b[t])
    c_cnt = sum(1 for t in common if bin_b[t] > bin_a[t])
    chi2 = (b_cnt - c_cnt) ** 2 / (b_cnt + c_cnt) if (b_cnt + c_cnt) > 0 else 0.0

    # 模板簇结构（按臂内可测行聚合；两臂合并估计 ICC 更稳健）
    clusters: dict[Any, list[float]] = {}
    for bin_map in (bin_a, bin_b):
        row_by_id = {r.get("task_id"): r for r in (rows_a if bin_map is bin_a else rows_b)}
        for t, v in bin_map.items():
            pat = _rows_pattern_name(row_by_id.get(t, {})) or "unknown"
            clusters.setdefault(pat, []).append(v)
    k = len(clusters)
    n_obs = sum(len(v) for v in clusters.values())
    m_bar = n_obs / k if k else 0.0
    icc = _icc_one_way_binary(clusters)
    if icc is None:
        lines.append(f"- ICC 不可估（簇结构退化：k={k}），逐对口径维持原判。")
        return "\n".join(lines) + "\n"
    deff = 1.0 + (m_bar - 1.0) * icc
    n_eff = n_obs / deff if deff > 0 else n_obs
    chi2_adj = chi2 * (n_eff / n_obs)

    # 模板级配对符号检验
    tmpl_a: dict[Any, list[float]] = {}
    row_by_id_a = {r.get("task_id"): r for r in rows_a}
    for t, v in bin_a.items():
        pat = _rows_pattern_name(row_by_id_a.get(t, {})) or "unknown"
        tmpl_a.setdefault(pat, []).append(v)
    tmpl_b: dict[Any, list[float]] = {}
    row_by_id_b = {r.get("task_id"): r for r in rows_b}
    for t, v in bin_b.items():
        pat = _rows_pattern_name(row_by_id_b.get(t, {})) or "unknown"
        tmpl_b.setdefault(pat, []).append(v)
    common_pats = sorted(set(tmpl_a) & set(tmpl_b), key=str)
    wins_a = sum(1 for p in common_pats if sum(tmpl_a[p]) / len(tmpl_a[p]) > sum(tmpl_b[p]) / len(tmpl_b[p]))
    wins_b = sum(1 for p in common_pats if sum(tmpl_b[p]) / len(tmpl_b[p]) > sum(tmpl_a[p]) / len(tmpl_a[p]))
    ties = len(common_pats) - wins_a - wins_b
    sign_p = _exact_sign_test_p(wins_a, wins_b)

    lines.append(
        f"- 逐对 McNemar：discordant {b_cnt}:{c_cnt}，χ²={chi2:.4f}；"
        f"聚类校正（k={k} 模板簇，m̄={m_bar:.2f}，ICC={icc:.3f}，DEFF={deff:.3f}，"
        f"n_eff={n_eff:.1f}/{n_obs}）→ 保守 χ²_adj≈{chi2_adj:.4f}"
    )
    lines.append(
        f"- 模板级符号检验（{label_a} 胜 {wins_a} / {label_b} 胜 {wins_b} / 平 {ties}，"
        f"共 {len(common_pats)} 公共模板）：精确二项 p={sign_p:.6g}"
    )
    return "\n".join(lines) + "\n"


def run_cluster_sensitivity(
    results_dir: str = "experiments/results",
    output_file: str | None = None,
    batch_files: list[str] | None = None,
    allow_schema_mixed: bool = False,
    pool_seeds: bool = True,
) -> str:
    """AC4 运行器：对全部基线对比产出聚类稳健敏感性 Markdown 章节。

    数据口径与 run_all_statistics 完全一致（load_experiment_results_with_sources
    + pool_seeds 拼接）；默认 pool_seeds=True（敏感性分析主要服务多种子
    合并口径）。output_file 提供时落盘（追加模式），恒打印控制台。
    """
    data, source_files = load_experiment_results_with_sources(
        results_dir, batch_files, allow_schema_mixed=allow_schema_mixed, pool_seeds=pool_seeds
    )
    header = [
        "## 模板聚类稳健敏感性分析（AC4，T-P0-5）",
        "",
        f"数据来源：{len(source_files)} 个批次（pool_seeds={pool_seeds}）。",
        "动机：多种子拼接口径下同模板任务跨种子为相关观测，逐对 McNemar 的",
        "独立性假设名义偏乐观；本节以设计效应校正 + 模板级符号检验做敏感性检验，",
        "方向与量级一致即结论稳健。",
        "",
    ]
    sections: list[str] = []
    pairs = [("plain_llm_df", "plain_llm"), ("aitester", "plain_llm"), ("aitester", "plain_llm_df")]
    for a, b in pairs:
        if data.get(a) and data.get(b):
            sections.append(template_cluster_sensitivity(data[a], data[b], a, b))
    body = "\n".join(header + sections)
    print(body)
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write("\n" + body + "\n")
    return body


def main() -> None:
    """R2：命令行入口（--batches 批次白名单；未提供时行为与历史完全一致）。

    参数：
        --results-dir: 实验结果目录（默认 experiments/results）
        --output: Markdown 报告输出路径（默认 experiments/results/statistical_report.md，gitignore 区）
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
        default="experiments/results/statistical_report.md",
        help="Markdown 报告输出路径（默认 experiments/results/statistical_report.md，gitignore 区）",
    )
    parser.add_argument(
        "--batches",
        default=None,
        help="R2：逗号分隔的批次文件白名单（相对 --results-dir 的路径），"
        "仅纳入指定文件；未提供时递归 glob 全目录（历史行为）",
    )
    parser.add_argument(
        "--allow-schema-mixed",
        action="store_true",
        help="X2（P0-4b）：纳入 schema 不完备批次（结果行缺 detection_rate 的早期/冒烟批次）——历史混批口径，默认剔除",
    )
    parser.add_argument(
        "--pool-seeds",
        action="store_true",
        help="AB4（2026-10-06）：多种子拼接口径——行 task_id 按批次 provenance.seed 加前缀，"
        "多种子批次不再被 task_id 去重折叠成单种子；同种子重复跑仍折叠（重跑协议语义保留）",
    )
    parser.add_argument(
        "--cluster-by-template",
        action="store_true",
        help="AC4（2026-10-06，T-P0-5）：仅产出模板聚类稳健敏感性分析章节"
        "（设计效应校正 + 模板级符号检验；默认 pool_seeds=True 口径）",
    )
    parser.add_argument(
        "--sensitivity-output",
        default=None,
        help="AC4：敏感性章节落盘路径（追加模式；缺省仅打印控制台）",
    )
    parser.add_argument(
        "--price-table",
        default="experiments/price_table.json",
        help="AE2（2026-10-06）：$/task 价目表路径（默认 experiments/price_table.json；"
        "文件不存在或价格未登记时成本节按'价目未登记'口径输出，不编造价格）",
    )
    args = parser.parse_args()

    if args.cluster_by_template:
        run_cluster_sensitivity(
            args.results_dir,
            output_file=args.sensitivity_output,
            batch_files=[p.strip() for p in (args.batches or "").split(",") if p.strip()] or None,
            allow_schema_mixed=args.allow_schema_mixed,
            pool_seeds=True,
        )
        return

    batch_files: list[str] | None = None
    if args.batches:
        batch_files = [p.strip() for p in args.batches.split(",") if p.strip()]
    run_all_statistics(
        args.results_dir,
        args.output,
        batch_files=batch_files,
        allow_schema_mixed=args.allow_schema_mixed,
        pool_seeds=args.pool_seeds,
        price_table=load_price_table(args.price_table),
    )


if __name__ == "__main__":
    main()
