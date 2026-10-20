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

S13/S11（2026-10-11 独立评审落地，均为增量；历史数字与默认输出不变）：

- **唯一程序体聚类稳健统计（S13/F2；A06 2026-10-18 映射修正）**：
  `build_cluster_map`（优先用归档 `task_metadata.pattern_name` 程序身份；缺失时
  按 `s<seed>__` 前缀在与跑批同参 `(task_count, seed, max_pattern_repeat)` 的
  重建数据集里查 `instance_code` 去注释后 sha256 簇 ID）与
  `cluster_robust_paired_test`（**先按簇求均值、再在簇级做配对检验**：t + 精确
  符号检验 + Cliff's δ/A12 效应量 + 簇内判定一致率）。由 `--cluster-robust`
  开关启用，**默认关闭**（历史口径逐位不变）；报告新增 `cluster_robust` 节。
  正确事实（主批 R-P0-2/R-P0-4：87 任务 × seed 42/43/44、`max_pattern_repeat=2`）：
  单 seed 87 个任务标签 → **29** 个唯一程序体；三种子拼接 261 个任务标签 →
  **31** 个唯一程序体。历史实现漏 `max_pattern_repeat` 且剥离 seed 前缀后统一
  查单 seed 表，把 261 行中的 223 行映射错、得错误 26 簇（符号检验 2:21:3 /
  p≈6.6e-05）；修正后 31 簇 / 5:17:9 / p≈0.0169（与归档三种子报告一致）。
  动机：把同一程序体的多个相关任务当独立样本会高估精确度（任务标签/程序体比
  ≈ 3.0（单 seed）/ 8.4（三种子池化））。
- **token 记账健全性（S11/F9）**：`token_accounting_sanity` —— 某臂 ≥50% 行的
  `token_usage` 为 0/缺失（且有结果行）时判 `NOT_COMPUTABLE`，成本列一律输出
  `NOT_COMPUTABLE` + 原因（**不输出数字**），`$/solved` 同步诚实降级。
  实测：7 份批次中 `plain_llm` / `plain_llm_df` 的 `token_usage` 整臂全为 0
  （含 `llm_calls`）而 `generated_test` 非空——成本结论不可计算却仍被输出。

用法：
    python experiments/statistical_analysis.py
    python experiments/statistical_analysis.py \
        --results-dir experiments/results \
        --batches main_batch/benchmark_synthetic_20261001_112528.json,main_batch/benchmark_synthetic_20261001_112801.json
    python experiments/statistical_analysis.py --results-dir experiments/results \
        --output experiments/results/statistical_report_cluster_robust.md \
        --pool-seeds --cluster-robust --cluster-max-pattern-repeat 2
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
import math
import random
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
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
from experiments._row_pairing import latest_binary_by_task, latest_rows_by_task  # noqa: E402
from experiments.bayesian_paired import bayesian_paired_analysis, interpret_bayes  # noqa: E402

# AB-14（2026-10-20）：币种判定的唯一事实源在 `src.budget.pricing.currency_status`。
# 本文件此前对取到的币种再加一次美元兜底——键缺席、值为 null、值为空白三种事实一律印成
# "USD"，且币种集合大小写敏感（`USD` 与 `usd` 并存时整臂成本静默降为 None 而
# `missing_models` 为空，报告落一行"未计价——（缺: ）"无因可查）。
from src.budget import pricing  # noqa: E402

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

# ───── S13（2026-10-11 独立评审落地）：唯一程序体聚类稳健统计的配置常量 ─────
# 常量集中在模块配置区（`run_all_statistics` 的默认参数在导入期求值，须先于
# 其定义存在）；簇级实现见文件后部 S13 区块（build_cluster_map /
# cluster_robust_paired_test / cluster_robust_analysis）。
_CLUSTER_ROBUST_BATCH = "S13（2026-10-11 独立评审落地；A06 2026-10-18 映射修正）"
_DEFAULT_CLUSTER_TASK_COUNT = 87
_DEFAULT_CLUSTER_SEED = 42
# A06（2026-10-18 第三方评审 P1）：主批协议（R-P0-2/R-P0-4）实测跑批参数为
# `--task-count 87 --max-pattern-repeat 2 --seed {42,43,44}`。旧实现重建时漏掉
# 该参数，得到错误的程序体分组；现以真实参数为默认值，并允许调用方显式传入
# （None = 无重复上限的历史口径，仅用于 2026-10-06 之前的旧批次）。
_DEFAULT_CLUSTER_MAX_PATTERN_REPEAT = 2
_UNMAPPED_CLUSTER_PREFIX = "unmapped::"
# AB4 多种子拼接口径的 task_id 前缀（`s<seed>__`）：A06 起前缀同时是"该行属于
# 哪个 seed 的重建"的依据——同编号任务跨种子不是同一程序，必须映射到各自 seed
# 的重建表；剥离前缀后的同一程序体跨种子再合并为同一簇。
_SEED_PREFIX_RE = re.compile(r"^s(\d+)__(.+)$")
# 报告的簇级对比顺序（与历史 comparisons 的基线顺序一致）
_CLUSTER_ROBUST_BASELINES = ("plain_llm", "plain_llm_df", "single_agent")
# 簇级稳健分析默认覆盖的指标（诚实指标在前，passed 自指口径仅作诊断）
_CLUSTER_ROBUST_FIELDS: tuple[tuple[str, str], ...] = (
    ("detection_rate", "detection（F2P 检出，gold 裁决）"),
    ("passed", "passed（自指，仅诊断）"),
)


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
    A07（2026-10-18 第三方评审 P1）：“最新批次优先”此前只在 None 值行上
    失效——旧实现在记录去重（`seen[tid] = ...`）**之前**就 `continue` 跳过
    None 行，于是"最新记录为 None、旧记录可测"的任务会回退到旧值，改变
    分母与配对计数（M8 可复现：最新 None 仍形成 1 对）。现口径分两步：
    **先对全部行按 task_id 去重（最新批次优先，与 field 值无关），再排除
    None**——最新记录不可测 = 该任务整体不可测（不回退旧值，与 M1
    “None 不进分母”一致）。

    Args:
        results_a: 基线 A（通常为 AITester）结果列表。
        results_b: 基线 B 结果列表。
        field: 配对所用的二值结果行字段（2026-10-05 独立审查 P0：
            "passed"（历史默认，自指指标）外新增 "detection_rate" /
            "repair_rate" 等 M1 诚实指标——逐任务值 0.0/1.0/None，
            None（无 gold 材料，M1 分母外）在**去重之后**跳过该任务，
            不并入分母；同 task_id 的旧可测值不得顶替最新 None）。

    Returns:
        (paired_a, paired_b, common_task_ids)
    """
    _logger = logging.getLogger(__name__)

    def _dedup(rows: list[dict], label: str) -> tuple[dict[str, int], int]:
        """返回 (可测二值映射, 重复行数)；去重与 None 过滤严格分两步（A07）。

        选择逻辑收敛到 `experiments._row_pairing.latest_rows_by_task`——与
        模板敏感性分支、贝叶斯配对共用同一实现（2026-10-19 复核残留补修：
        三处各自维护曾导致模板分支继续"跳过 None + 后写覆盖"）。
        """
        latest = latest_rows_by_task(rows)
        # 重复行数 = 带 task_id 的行数 − 去重后条目数（缺 task_id 的行不参与配对）
        n_duplicates = sum(1 for r in rows if r.get("task_id")) - len(latest)
        if n_duplicates:
            _logger.debug("%s 重复 task_id %d 行跳过（首见=最新批次优先去重）", label, n_duplicates)
        seen: dict[str, int] = {}
        for tid, r in latest.items():
            val = r.get(field)
            if val is None:
                # M1 诚实指标的 None = 无 gold 材料（分母外），非"未通过"——
                # 记 0 会把"无法测量"混入"测量为失败"，分母口径失真
                continue
            seen[tid] = 1 if val else 0
        return seen, n_duplicates

    pass_a, dup_a = _dedup(results_a, "基线A")
    pass_b, dup_b = _dedup(results_b, "基线B")

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
    field: str = "passed",
) -> tuple[float, int]:
    """
    计算配对版 Cohen's d 效应量（差值均值 / 差值标准差）

    配对设计的效应量应基于配对差值（而非两独立样本的合并标准差），
    与 paired_t_test 使用同一套 task_id 配对。

    Args:
        aitester_results: AITester 结果列表
        baseline_results: 基线结果列表
        field: 配对所用行字段（2026-10-16 B6：默认 "passed" 保持历史口径；
            呈现层改用 "detection_rate" 等 M1 诚实指标——None 剔除语义
            与 _pair_by_task 一致，且须与 t 检验的 field 保持一致）

    Returns:
        (d, n_pairs)；共同任务数 < 2 时返回 (nan, n_pairs)（n_pairs 恒为 0 或
        1，round10 P2 文档修正：旧注释误写 "返回 (nan, 0)"，实际返回当前
        n_pairs 值，便于调用方区分"无共同任务"与"仅 1 对"）
    """
    paired_a, paired_b, common_tasks = _pair_by_task(aitester_results, baseline_results, field=field)
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
    p = chi2.sf(stat, df=1)（**2026-10-20 AC 轮修复：旧实现 `1 - chi2.cdf`
    在 χ²≳71 时浮点下溢为精确 0.0**——p < ~6e-17 已低于 float64 相对 1 的
    机器精度，`1.0 - cdf` 恒等于 1.0；主批 plain_llm_df vs plain_llm
    （χ²=111.01）实测旧路径返回 p=0.0 / BH q=0.0，而精确值 p=5.890715e-26 /
    q=1.767215e-25（erfc(√(χ²/2)) 与 scipy sf 逐位一致）。sf 为生存函数，
    尾部数值稳定；结论（p≪α）不变，但 p/q 量级可复算）。
    n01 + n10 == 0（两组逐任务完全一致）时
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
    # AC 轮（2026-10-20）：sf 而非 1-cdf——后者在 χ²≳71 时浮点下溢为 0.0
    # （主批 plain-df 实测），使 p/BH q 的量级不可复算（详见 docstring）。
    p_value = float(stats.chi2.sf(chi2, df=1))
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
    假阳性"概率膨胀（3 组 × 0.05 = 14% 假阳性）。标准 BH 程序：
    1. 排序 p 值 p_(1) ≤ ... ≤ p_(m)；
    2. 找最大 rank 使 p_(rank) ≤ rank/m × alpha，该 rank 及之前全部拒绝
       （step-up 拒绝集，与调整 q 的 q ≤ alpha 严格等价）；
    3. 调整 q 值按**逆序累积最小**给出：
       q_(rank) = min(1, min_{j ≥ rank} m × p_(j) / j)——
       q 值只由 p 值排序位置决定，**不依赖本次 alpha 的拒绝位置**。

    2026-10-19 勘误（Z 轮第三方审查 F01）：旧实现按"最大被拒绝 p"和
    拒绝排名构造 q（无拒绝时直接返回原 p），不是标准 BH：旧 q 会依赖
    alpha 的拒绝位置，甚至在拒绝集非空时出现"q 与 rejected 标记矛盾"
    （例：[0.03, 0.20, 0.30] 旧 q=[0.03, 0.20, 0.30] 但 rejected 全 False，
    首项 q<alpha；标准 q=[0.09, 0.30, 0.30]）。本实现已改为标准 BH，
    拒绝集合语义（step-up）与 nan 处理（含 nan 的组跳过校正、q=nan）
    保持不变。

    Args:
        p_values: 各组原始 p 值列表（含 nan 时该组跳过校正，记 q=nan）。
        alpha: FDR 控制水平（默认 0.05），只决定 rejected 标记，不进入
            q 值公式。

    Returns:
        (q_values, rejected)：q_values 与输入同序（标准 BH 调整值，非
        nan 项满足 q ≥ p 且不超过 1）；rejected 为与输入同序的布尔列表
        （rejected[i] 等价于 q_values[i] ≤ alpha）。
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
    # BH step-up：找最大 rank（1-based）使 p_(rank) ≤ rank/m × alpha
    reject_rank = 0
    for rank in range(1, m + 1):
        if p_values[order[rank - 1]] <= rank / m * alpha:
            reject_rank = rank
    for rank in range(1, reject_rank + 1):
        rejected[order[rank - 1]] = True
    # 标准 BH 调整 q：从最大 rank 逆序累积最小 m*p_(rank)/rank（单调化），
    # 再截断到 1——q_(rank) = min(1, min_{j≥rank} m*p_(j)/j)。
    running_min = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running_min = min(running_min, m * p_values[i] / rank)
        q_values[i] = min(1.0, running_min)
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

    AD-1（2026-10-20）：**非零小量级改科学计数法**——`{:.4f}` 把
    |v| < 5e-5 的非零值一律印成 "0.0000"，量级信息被静默销毁。AC-1 的
    教训正是如此：p=5.890715e-26（χ²=111.01 的精确值）与下溢的 p=0.0 在
    报告里同形（都显示 "0.0000 (***)"），读者无法从账面区分"精确算出的
    极小值"与"精度丢失"。现值域 |v| < 1e-4 且 v != 0 → `{:.2e}`
    （如 5.890715e-26 → "5.89e-26"、1.811017e-07 → "1.81e-07"）；
    精确 0.0 仍渲染 "0.0000"（零是合法统计值，如 χ²=0 / 无不一致对）。
    """
    import math

    if math.isnan(value):
        return "n/a"
    if math.isinf(value):
        return "+inf" if value > 0 else "-inf"
    if value != 0.0 and abs(value) < 1e-4:
        return f"{value:.2e}"
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

    AB-17（2026-10-20）：文件级与形状判定收口到共享事实源——改前文件路径三种形状机制
    **全程无痕**（静默塌成空表，读起来与"表里真的没登记"同形），而参数路径
    （`_price_models_layer`）点名：同一份坏表两条路径两种读法。现两条路径共用
    `models_layer` 与同一套机制码；`isinstance(v, dict)` 静默过滤一并移除（坏条目不再
    无声消失，交 `cost_analysis` 按条目谓词点名）。`path=None` 是"未给价目表"的既有
    约定，保持静默空表。
    """
    if path is None:
        return {"models": {}}
    data, reason = pricing.load_table_json(path)
    if reason is not None:
        print(f"[WARN] 价目表不可用（{reason}）⇒ 按空表处理（成本节按未登记口径输出）。")
        return {"models": {}}
    models, shape_reason = pricing.models_layer(data)
    if shape_reason is not None:
        print(f'[WARN] 价目表形状不可用（{shape_reason}）⇒ 按空表处理：这是形状问题，不是"价目未登记"。')
        return {"models": {}}
    return {"models": models}


def _model_is_priced(entry: Any) -> bool:
    """AE2：模型条目是否具备完整可用价目（数字域收口到 `pricing.price_block_reason`，AB-16）。

    改前自写 `isinstance + p >= 0`——`inf` 满足 `inf >= 0` 被收下（金额变 `inf`），
    与其余消费点的域不一致；现在只改这一处读数（`nan`/负数/`bool`/非数在改前也已
    不计价，逐位保持）。桶级词汇（`missing_models`）本轮不动，见分册 §5。
    """
    return (
        isinstance(entry, dict)
        and pricing.price_block_reason(entry.get("input_per_mtok"), entry.get("output_per_mtok")) is None
    )


def _price_models_layer(price_table: Any) -> dict[str, Any]:
    """取价目表的 models 层，并把**形状错传**按机制点名到 stdout（AB-14）。

    `cost_analysis` 的入参约定是 `{"models": {...}}` 包装体（与 `load_price_table`
    产物同形）。改前三条形状通道一律静默塌成空表，下游于是把**其实已登记**的模型列进
    `missing_models`，报告据"价目未登记"的口径让人去补一份本来就补好了的价目表——
    归因错位（AB-11 判据）。这里只增加点名，**返回值口径一字不动**（坏形状仍是空表 ⇒
    诚实降级为未计价）；空对象没有形状可说，故 `{}` / `{"models": {}}` 保持静默，
    "真的没登记"与"传错了形状"仍分得开。

    AB-17（2026-10-20）：形状判定收口到 `pricing.models_layer`，三套中文短语换成共享机制码
    （`price_table_not_object:<T>` / `models_key_absent` / `models_not_object:<T>`），
    与文件路径读出同一个名字；"顶层像是 模型名 → 条目 的映射"提示随 `models_key_absent`
    保留。
    """
    models, reason = pricing.models_layer(price_table)
    if reason is not None:
        hint = "（顶层像是 模型名 → 条目 的映射）" if reason == "models_key_absent" else ""
        print(f'[WARN] 价目表形状不可用{hint}（{reason}）⇒ 按空表处理：这是形状问题，不是"价目未登记"。')
    return models


# ───────── S11（2026-10-11 独立评审落地）：token 记账健全性检查 ─────────
#
# 背景（独立评审实测 F9）：7 份批次中 `plain_llm` / `plain_llm_df` 的
# `token_usage` **整臂全为 0**（含 `llm_calls`），而这些行的 `generated_test`
# 非空——生成了测试却没有任何 token 记账，成本结论不可计算，报告却照常
# 输出 $/task 数字。本节的判定在**呈现层**拦截（成本表 + $/solved），
# `cost_analysis` 的行级数学口径保持不变（AE2 历史口径锁定：缺 token_usage
# 的行仍计 0 token 并进任务数分母），另在成本行上携带判定供下游消费。

# 判定阈值：某臂"无记账行"占比 ≥ 50% 即判 NOT_COMPUTABLE（评审要求口径）
_TOKEN_ACCOUNTING_ZERO_SHARE_THRESHOLD = 0.5

# 成本列在记账断裂时的占位符（**不得**替换为 0 或 "—"：前者会被读成免费，
# 后者会被读成"未计价"，两者都掩盖"记账缺失"这一根因）
_NOT_COMPUTABLE_CELL = "NOT_COMPUTABLE"


def _row_has_token_accounting(row: dict) -> bool:
    """S11：该结果行是否有**任何正向** token 记账。

    `token_usage` 缺失 / 非 dict / 各计数字段全为 0（或无 by_model 正向项）
    → 视为"无记账"。只看 token 数字，**不采信 `llm_calls`**：正是它整臂全为 0
    才暴露记账缺失，若以"调用次数 > 0"作正向证据，反而会把缺失行误判为已记账。
    """
    tu = row.get("token_usage")
    if not isinstance(tu, dict):
        return False
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = tu.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return True
    by_model = tu.get("by_model")
    if isinstance(by_model, dict):
        return any(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in by_model.values())
    return False


def token_accounting_sanity(rows: list[dict]) -> dict[str, Any]:
    """S11：单臂 token 记账健全性判定（成本结论可否计算）。

    判定：`n_rows > 0` 且"无记账行"占比 **≥ 50%** → `computable=False`，
    该臂成本列一律输出 `NOT_COMPUTABLE` + 原因（**不得输出数字**）。
    `n_rows == 0`（无结果行）→ `computable=True`：无行即无成本可谈，
    历史 "—" 降级口径不变（不把"空臂"误报成"记账断裂"）。

    Returns:
        {n_rows, n_without_accounting, zero_share, computable, reason}
    """
    rows = rows or []
    n_rows = len(rows)
    n_missing = sum(1 for r in rows if not _row_has_token_accounting(r))
    zero_share = n_missing / n_rows if n_rows else 0.0
    computable = not (n_rows > 0 and zero_share >= _TOKEN_ACCOUNTING_ZERO_SHARE_THRESHOLD)
    reason = ""
    if not computable:
        reason = (
            f"{n_missing}/{n_rows} 行（{zero_share * 100:.1f}%）的 token_usage 为 0 或缺失"
            f"（阈值 ≥{_TOKEN_ACCOUNTING_ZERO_SHARE_THRESHOLD * 100:.0f}%）"
            "——token 记账断裂（实测形态：generated_test 非空而 llm_calls/token 全为 0），"
            "成本结论不可计算：先修记账再重跑，不得在缺失记账上出 $/task 数字"
        )
    return {
        "n_rows": n_rows,
        "n_without_accounting": n_missing,
        "zero_share": zero_share,
        "computable": computable,
        "reason": reason,
    }


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
        unattributed_tokens, cost, cost_per_task, currency, priced}，
        以及 S11 记账健全性三元组 {token_accounting_ok,
        token_accounting_reason, token_zero_rows}——`token_accounting_ok=False`
        时呈现层（成本表 / $/solved）一律输出 NOT_COMPUTABLE，不得输出数字。
        AB-14 只在**真有模型币种不可判定**时追加 `unpriced_currency_models`
        （模型名 → `currency_status` 读数）；币种可判定的行返回域逐键不变，
        故受保护报告文本一字不动。币种可判定但登记为非 USD 的行**仍可计价**，
        前提是表里带币种列（呈现层另加单位提醒）；这与 `emse_stats_report`
        的 `total_usd`（单一美元列，非 USD 一律剔除）有意不同，见分册。
    """
    models = _price_models_layer(price_table)
    cost_rows: list[dict] = []
    for baseline in sorted(results):
        rows = results[baseline] or []
        accounting = token_accounting_sanity(rows)
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
        # AB-14：币种判定改用共享谓词。"价目不全"（`missing`）与"币种不可判定"
        # （`currency_blocked`）是两种事实，分桶记账、不得互吞；价目表里根本没有的模型
        # 只进 `missing`——"未登记"与"登记了但没写单位"是两件事。
        statuses = {m: pricing.currency_status(models[m]) for m in used_models if m in models}
        currency_blocked = {m: status for m, status in statuses.items() if pricing.currency_label(status) is None}
        labels = sorted(
            {pricing.currency_label(status) for status in statuses.values() if pricing.currency_label(status)}
        )
        cost: float | None = None
        currency: str | None = None
        if used_models and not missing and not currency_blocked and len(labels) == 1:
            price_pairs = {(models[m]["input_per_mtok"], models[m]["output_per_mtok"]) for m in used_models}
            # 单一价目组合（常见：单模型批次）才可按基线级 in/out 拆分计价
            if len(price_pairs) == 1:
                p_in, p_out = price_pairs.pop()
                cost = input_total / 1_000_000 * float(p_in) + output_total / 1_000_000 * float(p_out)
                currency = labels[0]
        cost_per_task = cost / len(rows) if cost is not None and rows else None
        row = {
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
            # S11（2026-10-11 独立评审落地）：记账健全性判定随行携带
            "token_accounting_ok": accounting["computable"],
            "token_accounting_reason": accounting["reason"],
            "token_zero_rows": accounting["n_without_accounting"],
        }
        # AB-14：披露键只在真发生时写入 ⇒ 币种可判定的行（含真批次）返回域逐键不变。
        if currency_blocked:
            row["unpriced_currency_models"] = dict(sorted(currency_blocked.items()))
        cost_rows.append(row)
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
    gold 材料独立裁决（自动化 oracle，无人工参与）主口径；passed = 自指口径仅供对照）。k 上界取全臂
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

    S11（2026-10-11 独立评审落地）：`token_accounting_ok=False` 的臂
    （token 记账断裂）同样 → None——$ 数字与 $/task 同源，记账缺失时
    $/solved 也必须诚实降级（手写 cost_rows 缺该键按 True，历史不变）。
    """
    out: dict[str, float | None] = {}
    for row in cost_rows:
        baseline = row.get("baseline")
        cost = row.get("cost")
        rows = data.get(baseline) or []
        solved = sum(1 for r in rows if r.get("patch_correct") == 1)
        if cost is None or solved == 0 or not row.get("token_accounting_ok", True):
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


def _currency_mechanism_lines(cost_rows: list[dict]) -> list[str]:
    """币种不可判定的机制点名（AB-14）：0 机制时一行不加，有机制时不得只给"补价目"指引。

    没有任何可计价行时 `_cost_report_lines` 走"价目未登记"早退分支，那里原本只教读者去填
    `input_per_mtok` / `output_per_mtok`——而真正缺的是 `currency`。照那句提示去补，
    补完仍然是未计价（缺的是单位不是价格）。
    """
    blocked = {r["baseline"]: r["unpriced_currency_models"] for r in cost_rows if r.get("unpriced_currency_models")}
    if not blocked:
        return []
    lines = [
        "",
        "**币种不可判定**（AB-14）——下列基线用到的模型没有写出可用单位；"
        "缺席 / null / 空白 / 非字符串一律不当成任何单位：",
    ]
    lines += [
        f"- `{baseline}`：" + "、".join(f"{m}（{blocked[baseline][m]}）" for m in sorted(blocked[baseline]))
        for baseline in sorted(blocked)
    ]
    lines.append("解读：补齐价目表的 `currency` 字段才可计价；只补 `input_per_mtok` 不改变本结论。")
    return lines


def _unpriced_row_reason(row: dict) -> str:
    """未计价行的成因串（AB-14）。

    `missing_models`（价目不全）与 `unpriced_currency_models`（币种不可判定）是两种机制，
    必须在同一行各自点名——否则读者以为"补价目"就能救回来，而实际缺的是单位登记。
    `（缺: ）` 的空写法是历史格式（真批次 `single_agent` 无 token 归属 ⇒ 空清单），
    本轮**不改**：改它会动到受 `SHA256SUMS` 保护的报告文本，另轮处置。
    """
    label = f"{row['baseline']}（缺: {', '.join(row['missing_models'])}"
    blocked = row.get("unpriced_currency_models") or {}
    if blocked:
        label += "；币种不可判定: " + ", ".join(f"{m}（{blocked[m]}）" for m in sorted(blocked))
    return label + "）"


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

    S11（2026-10-11 独立评审落地）：成本行携带 `token_accounting_ok`
    判定（token_accounting_sanity 产物）。为 False（该臂 ≥50% 行的
    token_usage 为 0/缺失）时，成本/任务与成本/检出一律渲染
    `NOT_COMPUTABLE`（**不输出数字**），并追加原因清单。手写 cost_rows
    （不含该键）按 True 处理 → 历史格式与既有测试逐位不变。
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
    # S11：记账断裂的臂（成本列一律 NOT_COMPUTABLE，不输出数字）
    _bad_accounting = [r for r in cost_rows if not r.get("token_accounting_ok", True)]

    def _cost_cells(r: dict) -> tuple[str, str]:
        """成本/任务与成本/检出单元格：记账断裂 → NOT_COMPUTABLE。"""
        if not r.get("token_accounting_ok", True):
            return _NOT_COMPUTABLE_CELL, _NOT_COMPUTABLE_CELL
        cpt_cell = f"{r['cost_per_task']:.4f}" if r["cost_per_task"] is not None else "—"
        if det_rates is None:
            return cpt_cell, ""
        cpd_val = cost_per_detection(r["cost_per_task"], det_rates.get(r["baseline"]))
        return cpt_cell, (f"{cpd_val:.4f}" if cpd_val is not None else "—")

    def _currency_cell(r: dict) -> str:
        """币种单元格：记账断裂时无成本数字 → 币种一并置 —（不留 USD 误导）。

        AB-14：手写行（不经 `cost_analysis`）的币种可能是非字符串，声明返回 `str`
        就必须真的返回 `str`，不得把原始对象丢给 f-string 蒙过去。
        """
        if not r.get("token_accounting_ok", True):
            return "—"
        return str(r["currency"] or "—")

    def _s11_note_lines() -> list[str]:
        """S11 原因清单（有记账断裂的臂时才追加——历史报告文本零变化）。"""
        if not _bad_accounting:
            return []
        note = [
            "",
            "**NOT_COMPUTABLE（S11 token 记账健全性，2026-10-11 独立评审落地）**"
            "——下列臂的 token 记账断裂，成本列**不输出数字**：",
        ]
        note += [f"- `{r['baseline']}`：{r.get('token_accounting_reason') or '记账缺失'}" for r in _bad_accounting]
        note.append("解读：仅「输入/输出 token」为 0 时成本/任务看似为 0，那是记账缺失而**非**免费；须先修记账再重跑。")
        return note

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
        lines += _currency_mechanism_lines(cost_rows)
        lines += _s11_note_lines()
        return lines
    if det_rates is None:
        lines += [
            "",
            "| Baseline | 任务数 | 输入 token | 输出 token | 成本/任务 | 币种 |",
            "|----------|--------|-----------|-----------|-----------|------|",
        ]
        for r in cost_rows:
            cpt, _ = _cost_cells(r)
            cur = _currency_cell(r)
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
            cpt, cpd = _cost_cells(r)
            cur = _currency_cell(r)
            lines.append(
                f"| {r['baseline']} | {r['n_tasks']} | {r['input_tokens']} | {r['output_tokens']} "
                f"| {cpt} | {cpd} | {cur} |"
            )
    # 未计价（价目缺失/多模型异价）与"记账断裂"是两种不同的降级，不得混为一谈：
    # 记账断裂的臂已由上方的 S11 NOT_COMPUTABLE 清单单独披露
    partial = [r for r in cost_rows if not r["priced"] and r.get("token_accounting_ok", True)]
    # AB-14：币种可判定的非 USD 行仍可计价（表里有币种列），但单位必须由文本自己说清楚
    priced_labels = [str(r.get("currency") or "").strip().upper() for r in priced]
    non_usd = sorted({label for label in priced_labels if label and label != "USD"})
    if non_usd:
        lines += [
            "",
            f"单位提醒：表内 {'、'.join(non_usd)} 行的金额按价目表登记币种原样呈现，未做汇率换算，",
            "不得与 USD 行相加或直接比较（成本/任务列名本身不暗示单位）。",
        ]
    if partial:
        missing_desc = "；".join(_unpriced_row_reason(r) for r in partial)
        lines += ["", f"注：{len(partial)} 个基线未计价——{missing_desc}。"]
    lines += _s11_note_lines()
    return lines


def run_all_statistics(
    results_dir: str,
    output_file: str | None = None,
    batch_files: list[str] | None = None,
    allow_schema_mixed: bool = False,
    pool_seeds: bool = False,
    price_table: dict[str, dict] | None = None,
    cluster_robust: bool = False,
    cluster_task_count: int = _DEFAULT_CLUSTER_TASK_COUNT,
    cluster_seed: int = _DEFAULT_CLUSTER_SEED,
    cluster_max_pattern_repeat: int | None = _DEFAULT_CLUSTER_MAX_PATTERN_REPEAT,
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
        cluster_robust: S13（2026-10-11 独立评审落地）——True 时追加
            `cluster_robust` 节（唯一程序体聚类稳健统计：簇内先取均值再在
            簇级做 t + 符号检验，含效应量与簇内一致率）。**默认 False**：
            历史报告与既有非聚类数字逐位不变（历史可比性）。
        cluster_task_count: S13——重建合成数据集的任务数（与实验一致，
            默认 87；仅 cluster_robust=True 时使用）。
        cluster_seed: S13——无 `s<seed>__` 前缀时的默认重建种子
            （与实验一致，默认 42）。
        cluster_max_pattern_repeat: A06（2026-10-18）——重建合成数据集的同池
            模板重复上限，**须与跑批一致**：主批 R-P0-2/R-P0-4 真实参数为 2
            （默认值）；None = 2026-10-06 之前无上限的历史口径。旧实现漏掉
            该参数并剥离 seed 前缀后统一查单 seed 表，导致主批 261 行错映射
            223 行（错误 26 簇），A06 修复为元数据优先 + 分 seed 重建 → 31 簇。

    Returns:
        比较结果列表，每项含 comparison / n_pairs / t_stat / p_value / sig /
        cohens_d / effect，以及 R14 的 mcnemar_* / fdr_* 与 R2 的
        cliffs_delta / cliffs_effect / bootstrap_* 字段（S13 开启时**不**
        改动本返回值——簇级结果只进报告，避免下游误把簇级数字当任务级）。
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
    # 直接来源），detection/repair 为 gold 材料独立裁决（自动化 oracle，无人工参与），报告读者第一眼应看
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
                f"  诚实指标（gold 材料独立裁决／自动化 oracle）: detection {sum(det_vals)}/{len(det_vals)}"
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
    # EMSE 批次（2026-10-15）：BH-FDR 扩到首要结论口径——此前校正只作用于
    # passed（自指、已降级为诊断参考）口径，而 detection/repair（报告声明
    # 的首要结论口径）的 p 值无 q 值。审稿可判性要求主结论自带多重比较
    # 校正。校正按**指标族**独立进行（detection 族 3 个比较、repair 族 3 个
    # 比较）——跨指标混池会改变各族内的 FDR 分母语义。
    for _field in {h["field"] for h in honest_comparisons}:
        _family = [h for h in honest_comparisons if h["field"] == _field]
        _q, _rej = bh_fdr_correct([h["p"] for h in _family])
        for _h, _qi, _ri in zip(_family, _q, _rej, strict=True):
            _h["fdr_adjusted_p"] = _qi
            _h["fdr_rejected"] = _ri
    if honest_comparisons:
        print("\n" + "=" * 70)
        print("诚实指标 McNemar（M1 三指标，gold 材料独立裁决 / 自动化 oracle——首要结论口径）")
        print("=" * 70)
        for h in honest_comparisons:
            _q_txt = f"，BH-FDR q={_fmt_stat_num(h['fdr_adjusted_p'])}" if h.get("fdr_adjusted_p") is not None else ""
            print(
                f"  [{h['metric']}] {h['comparison']}: 共同任务 {h['n_common']}"
                f"，不一致对 {h['n_diff']}，χ²={_fmt_stat_num(h['chi2'])}"
                f"，p={_fmt_stat_num(h['p'])} ({h['sig']}){_q_txt}"
            )
            if h.get("bayes_p_greater") is not None:
                print(
                    f"    贝叶斯后验: δ均值={_fmt_stat_num(h['bayes_mean'])}, "
                    f"95% CI [{_fmt_stat_num(h['bayes_ci_low'])}, {_fmt_stat_num(h['bayes_ci_high'])}], "
                    f"P(δ>0)={h['bayes_p_greater']:.4f}, P(ROPE)={h['bayes_p_rope']:.4f} "
                    f"({h['bayes_verdict']})"
                )

    # S13（2026-10-11 独立评审落地）：唯一程序体聚类稳健统计——**默认关闭**，
    # 开启时只**追加**报告节与控制台输出，不改动上方任何历史数字。
    # A06（2026-10-18）：重建参数传真实 max_pattern_repeat（默认 2），并让
    # cluster_robust_analysis 从结果行的 task_metadata 取归档程序身份。
    cluster_analysis: dict[str, Any] | None = None
    if cluster_robust:
        cluster_analysis = cluster_robust_analysis(
            data,
            task_count=cluster_task_count,
            seed=cluster_seed,
            max_pattern_repeat=cluster_max_pattern_repeat,
        )
        _csum = cluster_analysis["cluster_map_summary"]
        _ires = cluster_analysis.get("identity_resolution") or {}
        print("\n" + "=" * 70)
        print(f"聚类稳健统计（S13：唯一程序体口径；任务 {_csum['n_tasks']} → 簇 {_csum['n_clusters']}）")
        print("=" * 70)
        print(
            f"  身份来源：归档元数据 {_ires.get('n_from_metadata', 0)} / 分 seed 重建 "
            f"{_ires.get('n_from_rebuild', 0)} / 未映射（各成单例簇）{_csum['n_unmapped']}"
            f"；元数据-重建组成逐项一致 {_ires.get('n_composition_verified', 0)}/{_csum['n_tasks']}"
        )
        for _c in cluster_analysis["comparisons"]:
            print(
                f"  [{_c['metric']}] {_c['comparison']}: 任务级 n={_c['n_pairs']} → 簇级 n={_c['n_clusters']}"
                f"，δ={_fmt_stat_num(_c['delta'])}"
                f"，95% CI(t) [{_fmt_stat_num(_c['ci_low'])}, {_fmt_stat_num(_c['ci_high'])}]"
                f"，符号检验 p={_fmt_stat_num(_c['sign_p'])}"
                f"，Cliff's δ={_fmt_stat_num(_c['cliffs_delta'])}"
                f"，A12={_fmt_stat_num(_c['a12'])}"
                f"，簇内一致率={_fmt_stat_num(_c['concordance'])}"
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
            # S13/A06：聚类稳健口径的复算命令须带同参（否则簇级数字不可复现）；
            # CLI 以 0 表示 None（历史无 max_pattern_repeat 上限口径）。
            + (
                f" --cluster-robust --cluster-task-count {cluster_task_count}"
                f" --cluster-seed {cluster_seed}"
                f" --cluster-max-pattern-repeat "
                f"{0 if cluster_max_pattern_repeat is None else cluster_max_pattern_repeat}"
                if cluster_robust
                else ""
            )
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
            # gold 材料独立裁决／自动化 oracle）并列——分母为该指标可测任务数（None = 无 gold
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
            "## 诚实指标 McNemar 检验（M1 三指标，gold 材料独立裁决）",
            "",
            "2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上",
            "通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair",
            "由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与",
            "下方 passed 系列检验并列呈现，解读冲突时以本节为准。",
            "",
            "口径说明（EMSE 批次，防止读者误读）：本节'独立裁决'指**判据材料",
            "独立于被测系统**（留出 gold 测试与 gold 补丁），**不含任何人工",
            "裁决**——全流程为零 LLM 的自动化 oracle 判定。人工复核（E7）为",
            "预注册项但尚未执行，不得据此声称人工参与。",
            "",
            "多重比较校正（EMSE 批次 2026-10-15）：本节 p 值按**指标族**独立做",
            "BH-FDR 校正（detection 族与 repair 族各自构成 FDR 分母），q 值见",
            "末两列；此前校正只覆盖下方 passed 口径。",
            "",
            "| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 | BH-FDR q值 | FDR后显著 |",
            "|------|------|-----------|---------|------------------|-----|--------|-----------|----------|",
        ]
        for h in honest_comparisons:
            _fd = "是" if h.get("fdr_rejected") else "否"
            report_lines.append(
                f"| {h['metric']} | {h['comparison']} | {h['n_common']} | {h['n_diff']} "
                f"| {_fmt_stat_num(h['chi2'])} | {_fmt_stat_num(h['p'])} | {h['sig']} "
                f"| {_fmt_stat_num(h.get('fdr_adjusted_p', float('nan')))} | {_fd} |"
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

        # S13（2026-10-11 独立评审落地）：簇级（唯一程序体）稳健统计节——
        # 仅在 --cluster-robust 时出现；不改动上方任何历史数字（可比性）。
        if cluster_analysis is not None:
            report_lines += _cluster_robust_report_lines(cluster_analysis)

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
            "口径：同任务跨批次行 = 采样轮次；成功 = patch_correct（gold 材料独立裁决／自动化 oracle）。",
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
            _cell = (
                f"{_v:.6f}"
                if _v is not None
                else "未定义（correct=0 / 未计价 / token 记账不可用）——与 $/detection 同口径诚实降级"
            )
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

    A07（2026-10-19 复核残留补修）：去重/None 过滤与规范的 `_pair_by_task`
    完全同源——`_row_pairing.latest_binary_by_task` 先按 task_id 首见占位
    （最新批次在前），再排除 None；模板元数据从**同一条**最新行读取。
    历史实现"先跳过 None 再后写覆盖"会让最新 None 被旧 0 顶替、最新可测值
    被旧值覆盖，且模板归属取到旧行。
    """
    lines = [f"### {label_a} vs {label_b}（模板聚类稳健敏感性）", ""]

    bin_a, latest_a = latest_binary_by_task(rows_a, field="detection_rate")
    bin_b, latest_b = latest_binary_by_task(rows_b, field="detection_rate")
    common = sorted(set(bin_a) & set(bin_b), key=str)
    b_cnt = sum(1 for t in common if bin_a[t] > bin_b[t])
    c_cnt = sum(1 for t in common if bin_b[t] > bin_a[t])
    chi2 = (b_cnt - c_cnt) ** 2 / (b_cnt + c_cnt) if (b_cnt + c_cnt) > 0 else 0.0

    # 模板簇结构（按臂内可测行聚合；两臂合并估计 ICC 更稳健）
    clusters: dict[Any, list[float]] = {}
    for bin_map, latest_map in ((bin_a, latest_a), (bin_b, latest_b)):
        for t, v in bin_map.items():
            pat = _rows_pattern_name(latest_map.get(t, {})) or "unknown"
            clusters.setdefault(pat, []).append(float(v))
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

    # 模板级配对符号检验（元数据与数值同源：均取各自最新行）
    tmpl_a: dict[Any, list[float]] = {}
    for t, v in bin_a.items():
        pat = _rows_pattern_name(latest_a.get(t, {})) or "unknown"
        tmpl_a.setdefault(pat, []).append(float(v))
    tmpl_b: dict[Any, list[float]] = {}
    for t, v in bin_b.items():
        pat = _rows_pattern_name(latest_b.get(t, {})) or "unknown"
        tmpl_b.setdefault(pat, []).append(float(v))
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


# ──────────── S13（2026-10-11 独立评审落地）：唯一程序体聚类稳健统计 ────────────
#
# 背景（独立评审实测 F2；A06 2026-10-18 修正映射）：项目把任务标签当独立样本
# 做配对检验，但标签只对应少数唯一程序体——同一模板的逐任务"噪声"只是行尾
# 注释（`# noise_seed=`），去注释后程序体逐字节相同。簇内任务高度相关，独立性
# 假设不成立 → 方差被低估、精确度被高估。
# 正确事实（主批 R-P0-2/R-P0-4：87 任务 × seed 42/43/44、max_pattern_repeat=2）：
# 单 seed 87 个任务标签 → **29** 个唯一程序体（任务标签/程序体比 ≈ 3.0）；
# 三种子拼接 261 个任务标签 → **31** 个唯一程序体（且任务级 n=240 的
# δ=−28.3pp；按唯一程序体聚类后 31 簇 δ≈−18.2pp、95% CI [−33.5,−2.9]pp
# （t 口径）、符号检验 5:17:9 / p≈0.0169）。
# 历史实现（A06 缺陷）漏掉真实 `max_pattern_repeat` 且剥离 `s<seed>__` 前缀后
# 统一查单个 seed 的重建表——同编号任务跨 seed 不是同一程序，主批 261 行中
# 223 行被映射错、得错误 26 簇（符号检验 2:21:3 / p≈6.6e-05，夸大显著性）。
#
# 本节做法（`--cluster-robust` 开关，**默认关闭** → 历史口径逐位不变）：
# 1. **簇的构造可从工件复现**：优先用归档 task_metadata 中的程序身份
#    （pattern_name），缺失时按 `s<seed>__` 前缀在与跑批同参 (task_count,
#    seed, max_pattern_repeat) 的重建数据集里查表，对 `instance_code` 去注释后
#    sha256 取簇 ID（`build_cluster_map` / `_resolve_cluster_identity`）；
# 2. **簇内先取均值，再在簇级做配对检验**（等价于"每个程序体只投一票"）：
#    簇级配对 t（CI 给 t 与百分位 bootstrap 双口径）+ 精确符号检验；
# 3. 报告同时给**效应量**（Cliff's δ + A12）与**簇内判定一致率**
#    （concordance：同一程序体的任务是否给出同一方向判定——直接量化
#    "把相关观测当独立样本"的严重程度）。
#
# 诚实边界：本节的簇级数字**不替换**任何历史任务级数字（两者并列，冲突时
# 以簇级保守口径为准）；簇的构造若换成真实基准（task_id/元数据无法映射）则
# 退化为单例簇（见 build_cluster_map 的保守降级）。

# S13 常量定义在文件头部模块配置区（`_DEFAULT_CLUSTER_TASK_COUNT` 等需在
# run_all_statistics 的默认参数求值前就存在）；下方为簇级实现。


def strip_line_comments(code: str) -> str:
    """S13：去除行尾注释（`#` 至行尾）后 strip。

    与独立评审的簇构造口径逐位一致（`re.sub(r"#.*", "", code).strip()`）：
    合成数据集的逐任务差异**只在**行尾注释（`# noise_seed=`），程序体本身
    逐字节相同 → 去注释后相同即同一程序体。

    保守边界：字符串字面量内的 `#` 也会被剥离（合成模板不含 `#`，无影响）；
    真实基准上则会把"仅注释不同"的实现合并为同簇——簇数偏少 → CI 偏宽，
    属保守方向（不高估精确度）。
    """
    return re.sub(r"#.*", "", code or "").strip()


def program_fingerprint(code: str) -> str:
    """S13：程序体指纹 = 去注释后内容的 sha256（hex，64 字符）。"""
    return hashlib.sha256(strip_line_comments(code).encode("utf-8")).hexdigest()


def _split_seed_prefix(task_id: str) -> tuple[int | None, str]:
    """拆分 AB4 多种子拼接口径的 `s<seed>__` 前缀 → (seed, 无前缀 task_id)。

    无前缀时返回 (None, 原 task_id)。A06 起该前缀同时是"该行属于哪个 seed
    的重建"的依据（同编号任务跨 seed 不是同一程序）。
    """
    m = _SEED_PREFIX_RE.match(task_id)
    if m is None:
        return None, task_id
    return int(m.group(1)), m.group(2)


@functools.lru_cache(maxsize=32)
def _rebuilt_task_table(
    task_count: int,
    seed: int,
    max_pattern_repeat: int | None,
) -> tuple[tuple[str, str, str, int | None], ...]:
    """A06：用**真实跑批参数**重建合成数据集。

    返回 ((task_id, 程序体指纹, 模板名, noise_seed), ...)。

    - `max_pattern_repeat` 必须与跑批一致（主批 R-P0-2/R-P0-4 = 2；
      None = 2026-10-06 之前无重复上限的历史口径）——A06 根因即旧实现
      重建时漏掉该参数，导致同编号任务被映射到错误程序；
    - `pattern_name` / `noise_seed` 进入重建表用于**校验归档 task_metadata**
      （程序身份等价性证据：任务编号 + 模板名 + noise_seed 三项逐项一致）；
    - lru_cache：同参数只重建一次（87 任务，开销可忽略）；返回 tuple
      保证缓存值不可变（调用方不得原地修改）。
    """
    from src.datasets.synthetic_dataset import SyntheticDataset

    tasks = list(SyntheticDataset(task_count=task_count, seed=seed, max_pattern_repeat=max_pattern_repeat))
    return tuple(
        (
            str(t.task_id),
            program_fingerprint(t.instance_code),
            str(t.metadata.get("pattern_name") or ""),
            t.metadata.get("noise_seed"),
        )
        for t in tasks
    )


def _resolve_cluster_identity(
    task_ids: Iterable[str],
    *,
    task_count: int = _DEFAULT_CLUSTER_TASK_COUNT,
    seed: int = _DEFAULT_CLUSTER_SEED,
    max_pattern_repeat: int | None = _DEFAULT_CLUSTER_MAX_PATTERN_REPEAT,
    task_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, str], dict[str, int]]:
    """A06：task_id → 唯一程序体簇 ID，并统计身份解析来源。

    每个 task_id 的解析优先级：
    1. **归档元数据程序身份**（`task_metadata.pattern_name`，工件内不可变）：
       指纹 = 本次重建表并集中该模板名对应的程序体指纹（模板名 → 指纹必须
       唯一；歧义模板不参与解析）。这优先于 task_id 查表——A06 的错映射
       正是"同编号任务跨 seed 不是同一程序"造成的，pattern_name 才是程序
       身份。与重建同编号任务冲突时打 warning、以元数据为准（并计数）；
    2. **分 seed 重建表**：仅当该行**没有**可用元数据身份时（元数据缺失或
       未提供 pattern_name），按 `s<seed>__` 前缀确定该行所属 seed（无前缀
       用默认 `seed`），剥离前缀后查**该 seed** 的 (task_count,
       max_pattern_repeat) 重建 task_id 表；
    3. **保守降级**：均无法命中 → `unmapped::<task_id>` 单例簇（宁可多算
       簇、不臆造相关性）。特别地：**元数据存在但按给定重建参数无法复现其
       程序身份**（pattern_name 不在重建并集中/歧义）时不得回退 task_id
       查表——那正是跨 seed 错映射的来源；计 `n_metadata_unresolved` 并
       落单例簇（重建参数与批次不一致的诚实信号）。

    等价性证据（主批实测，见 tests/test_cluster_robust_stats.py）：三批次归档
    `task_metadata` 与对应 seed 的 (87, cap=2) 重建在 task_id/pattern_name/
    noise_seed 三项上逐行一致（87/87 × 3）；且模板名 → 指纹 1:1（单 seed 29
    个模板/29 个指纹，三种子并集 31/31）——因此"元数据模板身份"与"重建
    程序体指纹"分组等价。

    Returns:
        (cluster_map, stats)；stats 含 n_tasks / n_from_metadata /
        n_from_rebuild / n_unmapped / n_metadata_unresolved /
        n_metadata_conflicts / n_composition_verified（归档元数据与重建三项
        逐项一致的行数）。
    """
    unique_ids = list(dict.fromkeys(str(t) for t in task_ids))
    stats: dict[str, int] = {
        "n_tasks": len(unique_ids),
        "n_from_metadata": 0,
        "n_from_rebuild": 0,
        "n_unmapped": 0,
        "n_metadata_unresolved": 0,
        "n_metadata_conflicts": 0,
        "n_composition_verified": 0,
    }
    if not unique_ids:
        return {}, stats

    metadata_by_id: Mapping[str, Mapping[str, Any]] = task_metadata or {}

    base_of: dict[str, str] = {}
    seed_of: dict[str, int] = {}
    for tid in unique_ids:
        eff_seed, base = _split_seed_prefix(tid)
        seed_of[tid] = seed if eff_seed is None else int(eff_seed)
        base_of[tid] = base

    # 每个涉及的 seed 各重建一份（A06：分 seed 映射；漏 cap 的旧实现是根因之一）
    tables: dict[int, tuple[tuple[str, str, str, int | None], ...]] = {
        eff_seed: _rebuilt_task_table(task_count, eff_seed, max_pattern_repeat)
        for eff_seed in sorted(set(seed_of.values()))
    }
    by_id: dict[int, dict[str, tuple[str, str, int | None]]] = {
        eff_seed: {tid: (fp, pattern, noise) for tid, fp, pattern, noise in table} for eff_seed, table in tables.items()
    }
    # 本次涉及的全部 seed 重建并集：模板名 → 程序体指纹（歧义模板名不参与解析）
    pattern_fps: dict[str, set[str]] = {}
    for table in tables.values():
        for _tid, fp, pattern, _noise in table:
            if pattern:
                pattern_fps.setdefault(pattern, set()).add(fp)
    pattern_fp: dict[str, str] = {p: next(iter(fps)) for p, fps in pattern_fps.items() if len(fps) == 1}

    _logger = logging.getLogger(__name__)
    cluster_map: dict[str, str] = {}
    for tid in unique_ids:
        eff_seed = seed_of[tid]
        rebuilt = by_id[eff_seed].get(base_of[tid])
        metadata = metadata_by_id.get(tid)
        pattern = (
            str(metadata.get("pattern_name")) if isinstance(metadata, Mapping) and metadata.get("pattern_name") else ""
        )
        noise = metadata.get("noise_seed") if isinstance(metadata, Mapping) else None
        fp_meta = pattern_fp.get(pattern) if pattern else None
        fp_rebuild = rebuilt[0] if rebuilt is not None else None

        if rebuilt is not None and metadata is not None and pattern and rebuilt[1] == pattern and rebuilt[2] == noise:
            # 等价性证据：归档任务编号 + 模板名 + noise_seed 与重建三项一致
            stats["n_composition_verified"] += 1

        if fp_meta is not None:
            if fp_rebuild is not None and fp_rebuild != fp_meta:
                stats["n_metadata_conflicts"] += 1
                _logger.warning(
                    "聚类映射：task_id=%r 的归档 task_metadata.pattern_name=%r 与重建同编号任务不一致；"
                    "按归档程序身份（元数据优先）映射",
                    tid,
                    pattern,
                )
            cluster_map[tid] = fp_meta
            stats["n_from_metadata"] += 1
        elif pattern:
            # 元数据存在但按给定重建参数无法复现该程序身份 → 保守单例簇；
            # 不回退 task_id 查表（跨 seed 同编号错映射的来源）。
            stats["n_metadata_unresolved"] += 1
            cluster_map[tid] = f"{_UNMAPPED_CLUSTER_PREFIX}{tid}"
        elif fp_rebuild is not None:
            cluster_map[tid] = fp_rebuild
            stats["n_from_rebuild"] += 1
        else:
            cluster_map[tid] = f"{_UNMAPPED_CLUSTER_PREFIX}{tid}"
    # n_unmapped 与实际单例簇总数对齐（含元数据无法复现的保守降级行）
    stats["n_unmapped"] = sum(
        1 for cluster_id in cluster_map.values() if cluster_id.startswith(_UNMAPPED_CLUSTER_PREFIX)
    )
    return cluster_map, stats


def build_cluster_map(
    task_ids: Iterable[str],
    task_count: int = _DEFAULT_CLUSTER_TASK_COUNT,
    seed: int = _DEFAULT_CLUSTER_SEED,
    *,
    max_pattern_repeat: int | None = _DEFAULT_CLUSTER_MAX_PATTERN_REPEAT,
    task_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """A06（2026-10-18）：task_id → 唯一程序体簇 ID（**可从工件复现**）。

    口径（A06 修复后）：
    - **优先用归档任务元数据中的不可变程序身份**：`task_metadata.pattern_name`
      映射到该模板的程序体指纹（去注释 sha256；模板名 → 指纹在本次重建
      并集中必须唯一）——程序身份优先于 task_id，因为 seed42/43/44 的
      **同编号任务不是同一程序**；
    - 元数据缺失时按 `s<seed>__` 前缀映射到**该 seed** 的、带真实
      `max_pattern_repeat` 的 (task_count, seed) 重建表查 `task_id`；
    - 同一程序体**跨种子合并**为同一簇（这正是聚类稳健性要修正的相关性
      来源）；簇 ID = `instance_code` 去注释后 sha256（`program_fingerprint`）；
    - **保守降级**：查不到的任务不并入任何簇、也不丢弃，而是各成
      `unmapped::<task_id>` 单例簇——宁可多算簇（CI 偏宽）也不臆造相关性
      （把无关任务并簇会人为抬高簇内一致率）。成因：重建参数与批次不一致
      （如漏 `max_pattern_repeat`）、旧命名 task_id（2026-10-05 P1-4 前末段
      为 pattern 名）、真实基准（QuixBugs）任务——重建数据集无法命中。

    实测（主批 R-P0-2/R-P0-4，2026-10-06 三批次 = 87 任务 × seed 42/43/44，
    cap=2）：单 seed 87 个任务标签 → **29** 个唯一程序体（簇规模分布
    1×6 / 2×11 / 3×3 / 4×4 / 6×2 / 7×2 / 8×1）；三种子拼接 261 个任务标签
    → **31** 个唯一程序体。历史实现（漏 cap + 剥前缀后统一查 seed=42 表）
    把 261 行中的 223 行映射错、错误分组 26 簇（符号检验 2:21:3 /
    p≈6.6e-05）；A06 修复后为 31 簇 / 5:17:9 / p≈0.0169（与归档三种子
    报告的模板聚类一致）。`max_pattern_repeat=None`（历史口径）时单 seed
    87 → 26 簇——26 是**不在主批协议内**的旧重建参数产物，不得当作主批事实。

    Args:
        task_ids: 待映射的任务 ID（可重复、顺序无关；多种子拼接口径带
            `s<seed>__` 前缀）。
        task_count: 重建数据集的任务数（与实验一致，默认 87）。
        seed: 无 `s<seed>__` 前缀时的默认重建种子（默认 42）。
        max_pattern_repeat: 重建数据集的同池模板重复上限（须与跑批一致；
            默认 2 = 主批 R-P0-2/R-P0-4 真实参数；None = 历史无上限口径）。
        task_metadata: 可选 {task_id: task_metadata}（结果行原样携带的
            归档程序身份；`cluster_robust_analysis` 自动从数据行收集）。

    Returns:
        {task_id: cluster_id}；空输入返回空 dict（不抛异常）。
    """
    cluster_map, _stats = _resolve_cluster_identity(
        task_ids,
        task_count=task_count,
        seed=seed,
        max_pattern_repeat=max_pattern_repeat,
        task_metadata=task_metadata,
    )
    return cluster_map


def cluster_map_summary(cluster_map: dict[str, str]) -> dict[str, Any]:
    """S13：簇映射摘要（任务数 / 簇数 / 簇规模分布 / 未映射数）。

    Returns:
        {n_tasks, n_clusters, n_unmapped, size_distribution}；size_distribution
        为 {簇规模: 该规模的簇数}（升序键）。空输入 → 全 0 / 空分布。
    """
    sizes: Counter[str] = Counter(cluster_map.values())
    distribution: Counter[int] = Counter(sizes.values())
    return {
        "n_tasks": len(cluster_map),
        "n_clusters": len(sizes),
        "n_unmapped": sum(1 for cid in sizes if cid.startswith(_UNMAPPED_CLUSTER_PREFIX)),
        "size_distribution": dict(sorted(distribution.items())),
    }


def _cluster_pairs_from_rows(
    rows_a: list[dict], rows_b: list[dict], field: str = "passed"
) -> list[tuple[str, float, float]]:
    """S13：结果行 → 簇级配对输入 [(task_id, 值A, 值B)]。

    复用规范配对原语 `_pair_by_task`（task_id 配对 + 最新批次优先去重 +
    None 不进分母），保证簇级与任务级共用同一套配对口径。
    """
    paired_a, paired_b, common_tasks = _pair_by_task(rows_a, rows_b, field=field)
    return [(str(t), float(a), float(b)) for t, a, b in zip(common_tasks, paired_a, paired_b, strict=True)]


def _cliffs_delta_from_values(values_a: list[float], values_b: list[float]) -> float:
    """S13：簇级配对 Cliff's δ = (n⁺ − n⁻) / n（与 cliffs_delta 同口径）。

    输入为**簇级均值**（每个程序体一票），而非逐任务行；n=0 → nan。
    """
    n = len(values_a)
    if n == 0:
        return float("nan")
    n_pos = sum(1 for a, b in zip(values_a, values_b, strict=True) if a > b)
    n_neg = sum(1 for a, b in zip(values_a, values_b, strict=True) if a < b)
    return (n_pos - n_neg) / n


def cluster_robust_paired_test(
    pairs: Iterable[tuple[str, float, float]],
    cluster_key_fn: Callable[[str], str],
    *,
    bootstrap_resamples: int = _BOOTSTRAP_N_RESAMPLES,
    seed: int = _BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """S13（A06 修正）：聚类稳健配对检验——**簇内先取均值，再在簇级做配对检验**。

    为什么必须聚类：任务标签只对应少数唯一程序体（簇内高度相关）——主批
    R-P0-2/R-P0-4（87 任务、max_pattern_repeat=2）单 seed 87 标签 → 29 个
    程序体，三种子拼接 261 标签 → 31 个程序体（A06 修正后的正确事实；旧实现
    因漏 cap + 跨 seed 错映射得到 26 簇，见 build_cluster_map docstring）。
    逐任务配对检验的独立性假设不成立，方差被低估、精确度被高估。
    本函数把每个程序体压缩成一个观测（簇内均值），再做 k=簇数 的配对检验
    ——等价于"每个程序体只投一票"，是评审要求的保守口径。

    检验与效应量（全部在**簇级**计算）：
    - 配对 t：`scipy.stats.ttest_rel`（簇级均值对），df = k − 1；
    - 95% CI 双口径：学生 t（`δ ± t_{0.975,k−1}·s/√k`）与百分位 bootstrap
      （`random.Random(seed)` 固定 seed=42、10000 次重采样，逐位可复现）；
    - 精确符号检验：簇级差值的正/负计数（0 差值不贡献符号），
      全部持平 → p=1（与 `_exact_sign_test_p` 同口径）；
    - 效应量：Cliff's δ =（n⁺ − n⁻)/k 与 A12 =（n⁺ + 0.5·n⁰)/k
      （**必须有**——p 值不是效应量）；
    - `concordance`：簇内判定方向一致率——size≥2 的簇内"最多数方向"占比，
      按簇内配对数加权平均（1.0 = 同一程序体的所有任务方向一致）。

    保守降级（不抛异常）：空输入 → n_clusters=0、delta/CI/t/df 全 nan、
    `status="insufficient_data"`；k=1 → t/CI 为 nan（df=0）；簇级差值
    零方差（全同向）→ t=±inf、p=0（与历史 t 检验的退化处理同口径），
    全平 → t/p 均为 nan、`sign_p=1.0`。

    Args:
        pairs: [(task_id, 值A, 值B), ...]；None 值的对**跳过**（不可测，
            与 M1 "None 不进分母"口径一致），不计入 n_pairs/n_clusters。
        cluster_key_fn: task_id → 簇 ID（`build_cluster_map` 的产物字典
            配 `lambda t: cmap.get(t, ...)` 使用）。
        bootstrap_resamples: bootstrap 重采样次数（默认 10000）。
        seed: bootstrap 随机种子（默认 42）。

    Returns:
        {n_pairs, n_clusters, delta, ci_low, ci_high, t, df, p_value, sign_p,
        sign_wins, sign_losses, sign_ties, concordance, cliffs_delta,
        cliffs_effect, a12, boot_ci_low, boot_ci_high, bootstrap_resamples,
        bootstrap_seed, cluster_size_distribution, status}
    """
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    signs_by_cluster: dict[str, list[int]] = {}
    n_pairs = 0
    for task_id, value_a, value_b in pairs:
        if value_a is None or value_b is None:
            continue  # 不可测对跳过（不并入分母）
        cluster = str(cluster_key_fn(str(task_id)))
        slot = grouped.setdefault(cluster, ([], []))
        a_val, b_val = float(value_a), float(value_b)
        slot[0].append(a_val)
        slot[1].append(b_val)
        signs_by_cluster.setdefault(cluster, []).append(1 if a_val > b_val else (-1 if a_val < b_val else 0))
        n_pairs += 1

    cluster_ids = sorted(grouped)
    n_clusters = len(cluster_ids)
    mean_a = [sum(grouped[c][0]) / len(grouped[c][0]) for c in cluster_ids]
    mean_b = [sum(grouped[c][1]) / len(grouped[c][1]) for c in cluster_ids]
    diffs = [a - b for a, b in zip(mean_a, mean_b, strict=True)]

    result: dict[str, Any] = {
        "n_pairs": n_pairs,
        "n_clusters": n_clusters,
        "delta": float("nan"),
        "ci_low": float("nan"),
        "ci_high": float("nan"),
        "t": float("nan"),
        "df": float("nan"),
        "p_value": float("nan"),
        "sign_p": 1.0,
        "sign_wins": 0,
        "sign_losses": 0,
        "sign_ties": 0,
        "concordance": float("nan"),
        "cliffs_delta": float("nan"),
        "cliffs_effect": "unknown",
        "a12": float("nan"),
        "boot_ci_low": float("nan"),
        "boot_ci_high": float("nan"),
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": seed,
        "cluster_size_distribution": dict(sorted(Counter(len(v[0]) for v in grouped.values()).items())),
        "status": "insufficient_data",
    }
    if n_clusters == 0:
        return result

    # 簇内判定方向一致率（concordance）：只统计 size≥2 的簇，按簇内配对数加权
    concordant = 0
    weight = 0
    for c in cluster_ids:
        signs = signs_by_cluster[c]
        if len(signs) < 2:
            continue
        concordant += max(Counter(signs).values())
        weight += len(signs)

    delta = sum(diffs) / n_clusters
    wins_a = sum(1 for d in diffs if d > 0)
    wins_b = sum(1 for d in diffs if d < 0)
    ties = n_clusters - wins_a - wins_b
    cliffs = _cliffs_delta_from_values(mean_a, mean_b)

    result.update(
        {
            "delta": delta,
            "sign_wins": wins_a,
            "sign_losses": wins_b,
            "sign_ties": ties,
            "sign_p": _exact_sign_test_p(wins_a, wins_b),
            "concordance": (concordant / weight) if weight else float("nan"),
            "cliffs_delta": cliffs,
            "cliffs_effect": interpret_cliffs_delta(cliffs),
            "a12": (wins_a + 0.5 * ties) / n_clusters,
            "status": "ok" if n_clusters >= 2 else "single_cluster",
            "df": n_clusters - 1,
        }
    )

    if n_clusters >= 2:
        arr = np.asarray(diffs, dtype=float)
        se = float(arr.std(ddof=1)) / math.sqrt(n_clusters)
        if se == 0:
            # 簇级差值零方差：全平 → 无证据（nan）；全同向 → t=±inf、p=0
            if delta != 0:
                result["t"] = math.copysign(float("inf"), delta)
                result["p_value"] = 0.0
            result["ci_low"] = result["ci_high"] = delta
        else:
            t_stat, p_value = stats.ttest_rel(mean_a, mean_b)
            t_crit = float(stats.t.ppf(0.975, n_clusters - 1))
            result["t"] = float(t_stat)
            result["p_value"] = float(p_value)
            result["ci_low"] = delta - t_crit * se
            result["ci_high"] = delta + t_crit * se
        # 百分位 bootstrap（固定 seed，逐位可复现；与主口径并列呈现）
        rng = random.Random(seed)
        boot_means: list[float] = []
        for _ in range(bootstrap_resamples):
            total = 0.0
            for _ in range(n_clusters):
                total += diffs[rng.randrange(n_clusters)]
            boot_means.append(total / n_clusters)
        boot_means.sort()
        result["boot_ci_low"] = _percentile(boot_means, 0.025)
        result["boot_ci_high"] = _percentile(boot_means, 0.975)
    return result


def cluster_robust_analysis(
    data: dict[str, list[dict]],
    *,
    task_count: int = _DEFAULT_CLUSTER_TASK_COUNT,
    seed: int = _DEFAULT_CLUSTER_SEED,
    max_pattern_repeat: int | None = _DEFAULT_CLUSTER_MAX_PATTERN_REPEAT,
    fields: tuple[tuple[str, str], ...] = _CLUSTER_ROBUST_FIELDS,
) -> dict[str, Any]:
    """S13（A06 修正）：对全部基线对比产出簇级配对检验（报告与下游共用的唯一入口）。

    步骤：收集全部任务 ID 与**归档 task_metadata**（程序身份）→
    `_resolve_cluster_identity`（元数据优先 + 分 seed 重建，一次构建、全臂
    共用）→ 逐 (指标, 基线) 调 `cluster_robust_paired_test`。

    Args:
        data: {baseline: [结果行]}（load_experiment_results* 加载）。
        task_count / seed / max_pattern_repeat: 重建参数；须与跑批一致
            （主批 R-P0-2/R-P0-4：87 / seed 前缀决定 / 2）。
        fields: 参与簇级分析的 (field, 报告标签) 列表。

    Returns:
        {task_count, dataset_seed, max_pattern_repeat, cluster_map_summary,
         identity_resolution, comparisons:[...]}；
        `comparisons` 每项为 `cluster_robust_paired_test` 的返回字典 +
        {metric, field, comparison, baseline}；`identity_resolution` 为 A06
        身份来源统计（元数据 / 分 seed 重建 / 未映射 / 组成验证数）。
    """
    task_ids = [str(r["task_id"]) for rows in data.values() for r in (rows or []) if r.get("task_id")]
    # A06：归档 task_metadata 是程序身份的首选依据；同一 task_id 跨臂元数据
    # 相同，首见即可（跨批次重复行由 _pair_by_task 的去重口径另行处理）。
    task_metadata: dict[str, Mapping[str, Any]] = {}
    for rows in data.values():
        for row in rows or []:
            tid = row.get("task_id")
            if not tid or str(tid) in task_metadata:
                continue
            metadata = row.get("task_metadata")
            if isinstance(metadata, Mapping):
                task_metadata[str(tid)] = metadata
    cluster_map, identity_resolution = _resolve_cluster_identity(
        task_ids,
        task_count=task_count,
        seed=seed,
        max_pattern_repeat=max_pattern_repeat,
        task_metadata=task_metadata or None,
    )

    def _key(tid: str) -> str:
        """簇键：映射命中取簇 ID；未映射任务各成单例簇（保守降级）。"""
        return cluster_map.get(tid) or f"{_UNMAPPED_CLUSTER_PREFIX}{tid}"

    comparisons: list[dict[str, Any]] = []
    for field, metric_label in fields:
        for baseline in _CLUSTER_ROBUST_BASELINES:
            if not data.get("aitester") or not data.get(baseline):
                continue
            pairs = _cluster_pairs_from_rows(data["aitester"], data[baseline], field=field)
            res = cluster_robust_paired_test(pairs, _key)
            res.update(
                {
                    "metric": metric_label,
                    "field": field,
                    "baseline": baseline,
                    "comparison": f"AITester vs {baseline}",
                }
            )
            comparisons.append(res)
    return {
        "task_count": task_count,
        "dataset_seed": seed,
        "max_pattern_repeat": max_pattern_repeat,
        "cluster_map_summary": cluster_map_summary(cluster_map),
        "identity_resolution": identity_resolution,
        "comparisons": comparisons,
    }


def _cluster_robust_report_lines(analysis: dict[str, Any]) -> list[str]:
    """A06（2026-10-18）：报告 `cluster_robust` 节（簇结构披露 + 簇级配对检验表）。

    文案中的程序体数/簇规模/身份来源全部取自本次分析结果（动态），不再写死
    历史错误分组数（旧文案的 “26 个唯一程序体 / 3.35 倍” 是漏 `max_pattern_repeat`
    且剥离 seed 前缀后统一查单 seed 表的产物，见 A06）。
    """
    summary = analysis["cluster_map_summary"]
    identity = analysis.get("identity_resolution") or {}
    dist_text = (
        " / ".join(f"{size}×{count}" for size, count in sorted(summary["size_distribution"].items())) or "（无）"
    )
    max_pattern_repeat = analysis.get("max_pattern_repeat", _DEFAULT_CLUSTER_MAX_PATTERN_REPEAT)
    cap_text = "None（历史口径，无同池模板重复上限）" if max_pattern_repeat is None else str(max_pattern_repeat)
    ratio_text = f"{summary['n_tasks'] / summary['n_clusters']:.2f}" if summary["n_clusters"] else "n/a"
    n_metadata = int(identity.get("n_from_metadata", 0))
    n_rebuild = int(identity.get("n_from_rebuild", 0))
    n_conflicts = int(identity.get("n_metadata_conflicts", 0))
    n_unresolved = int(identity.get("n_metadata_unresolved", 0))
    n_verified = int(identity.get("n_composition_verified", 0))
    conflict_text = f"（元数据与重建同编号任务冲突 {n_conflicts} 行，按元数据程序身份为准）" if n_conflicts else ""
    lines = [
        "",
        "## 聚类稳健统计（cluster_robust，S13——唯一程序体口径）",
        "",
        f"{_CLUSTER_ROBUST_BATCH}：历史上的配对检验把任务标签当独立样本，但实测"
        f"这些标签只对应 **{summary['n_clusters']} 个唯一程序体**（同一模板逐任务差异"
        "只是行尾注释 `# noise_seed=`，去注释后逐字节相同）——簇内观测高度相关，"
        f"独立性假设不成立，任务级精确度被高估（任务标签/程序体比 ≈ {ratio_text}）。",
        "",
        "- **A06（2026-10-18）映射修正**：旧实现用 `SyntheticDataset(task_count, seed)` "
        "重建（遗漏真实 `max_pattern_repeat`），且把多种子拼接的 `s<seed>__` 前缀剥离后"
        "统一查**单个** seed 的重建表——seed42/43/44 的同编号任务不是同一程序"
        "（主批 261 行实测错映射 223 行、错误分组 26 簇/2:21:3/p≈6.6e-05；修正后 "
        "31 簇/5:17:9/p≈0.0169，与归档三种子报告的模板聚类一致）。现口径：",
        "  1. **优先**采用归档任务元数据中的不可变程序身份（`task_metadata.pattern_name`"
        " → 去注释程序体指纹；模板名→指纹须唯一）；",
        "  2. 元数据缺失时按 `s<seed>__` 前缀映射到**该 seed** 的、带真实 "
        f"`max_pattern_repeat={cap_text}` 的 (task_count={analysis['task_count']}, seed) 重建表；",
        "  3. 仍无法命中 → `unmapped::<task_id>` 单例簇（保守降级，不臆造相关性）。",
        f"- 身份解析来源：归档元数据 {n_metadata} / 分 seed 重建 {n_rebuild} / "
        f"未映射 {int(identity.get('n_unmapped', summary['n_unmapped']))}"
        f"（其中元数据存在但按当前重建参数无法复现程序身份 {n_unresolved} 行——不回退"
        f" task_id 查表，保守单例）{conflict_text}；"
        f"元数据与重建在 task_id/pattern_name/noise_seed 三项逐项一致 {n_verified}/"
        f"{summary['n_tasks']} 行（组成验证 = 元数据身份与程序体指纹分组等价的证据）。",
        f"- 簇结构：任务 {summary['n_tasks']} 个 → 簇 {summary['n_clusters']} 个；"
        f"簇规模分布（规模×簇数）：{dist_text}；未映射任务 {summary['n_unmapped']} 个"
        "（各成单例簇——保守降级；常见成因 = 重建参数与批次不一致、旧命名 task_id"
        "（2026-10-05 P1-4 前末段为 pattern 名）或真实基准任务，重建数据集无法命中）；",
        "- 口径：**簇内先取均值，再在簇级做配对检验**（每个程序体只投一票）。"
        "本节的簇级数字**不替换**上方任务级数字；冲突时以本节（保守）为准。",
        "",
        "| 指标 | 比较 | 任务级 n | 簇级 n | δ（簇级均值差） | 95% CI（t） | 95% CI（bootstrap） "
        "| df | 簇级 t | p | 符号检验 p | Cliff's δ | A12 | 簇内一致率 |",
        "|------|------|---------|--------|-----------------|-------------|---------------------"
        "|----|--------|-----|-----------|-----------|-----|-----------|",
    ]
    lines += [
        (
            f"| {comp['metric']} | {comp['comparison']} | {comp['n_pairs']} | {comp['n_clusters']} "
            f"| {_fmt_stat_num(comp['delta'])} "
            f"| [{_fmt_stat_num(comp['ci_low'])}, {_fmt_stat_num(comp['ci_high'])}] "
            f"| [{_fmt_stat_num(comp['boot_ci_low'])}, {_fmt_stat_num(comp['boot_ci_high'])}] "
            f"| {_fmt_stat_num(comp['df'], '{:.0f}')} | {_fmt_stat_num(comp['t'])} "
            f"| {_fmt_stat_num(comp['p_value'])} | {_fmt_stat_num(comp['sign_p'])} "
            f"| {_fmt_stat_num(comp['cliffs_delta'])} | {_fmt_stat_num(comp['a12'])} "
            f"| {_fmt_stat_num(comp['concordance'])} |"
        )
        for comp in analysis["comparisons"]
    ]
    lines += [
        "",
        "读法：δ 为**簇级**均值差（每程序体一票），CI 不含 0 方向才稳健；"
        "符号检验 p 只看簇级胜负符号（最保守）；Cliff's δ / A12 为效应量"
        "（阈值见文末效应量说明）；簇内一致率 = size≥2 的簇内「最多数方向」"
        "占比按簇内配对数加权平均——1.0 表示同一程序体的所有任务方向一致，"
        "越低说明任务级 n 的独立性假设越不可信。",
        "",
    ]
    return lines


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
    parser.add_argument(
        "--cluster-robust",
        action="store_true",
        help="S13（2026-10-11 独立评审落地）：追加「唯一程序体」聚类稳健统计节"
        "（簇内先取均值再在簇级做 t + 符号检验，含效应量/簇内一致率）；"
        "默认关闭——现有报告数字逐位不变（历史可比性）",
    )
    parser.add_argument(
        "--cluster-task-count",
        type=int,
        default=_DEFAULT_CLUSTER_TASK_COUNT,
        help="S13：重建合成数据集的任务数（须与实验一致，默认 87）",
    )
    parser.add_argument(
        "--cluster-seed",
        type=int,
        default=_DEFAULT_CLUSTER_SEED,
        help="S13/A06：无 s<seed>__ 前缀时的默认重建种子（须与实验一致，默认 42）",
    )
    parser.add_argument(
        "--cluster-max-pattern-repeat",
        type=int,
        default=_DEFAULT_CLUSTER_MAX_PATTERN_REPEAT,
        help="A06（2026-10-18）：重建合成数据集的同池模板重复上限，须与跑批一致"
        "（主批 R-P0-2/R-P0-4 = 2，默认）；传 0 表示 None（2026-10-06 之前"
        "无重复上限的历史口径）——旧实现漏掉该参数是错误任务—程序映射的根因之一",
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
        # S13：聚类稳健节（默认关闭 → 历史口径逐位不变）
        cluster_robust=args.cluster_robust,
        cluster_task_count=args.cluster_task_count,
        cluster_seed=args.cluster_seed,
        # A06：CLI 以 0 表示 None（历史无 max_pattern_repeat 上限口径）
        cluster_max_pattern_repeat=(None if args.cluster_max_pattern_repeat < 1 else args.cluster_max_pattern_repeat),
    )


if __name__ == "__main__":
    main()
