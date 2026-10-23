"""BZ 轮（2026-10-23）：归档语料与 git 历史深度的在场守卫（单一事实源）。

背景——CI 的 actions/checkout 默认 fetch-depth=1（shallow clone），归档重
产物按 .gitignore:172 + Zenodo 纪律不入库。两类测试的运行前提在 fresh
clone 里不成立，而此前它们的失败形态是 AssertionError / FileNotFoundError
（把"环境里没有"报成"锁被打破"）：

① 语料面普查：要全归档 246 份 `benchmark_*.json` / 138 个 `traces*` 目录 /
   8539 个 `*.trace.jsonl` 才够扫描面（`test_corpus_counts_are_stable`、
   `test_no_real_batch_collapses_any_row`、
   `test_non_arm_batches_are_admitted_by_name_not_dropped`、
   `test_repo_wide_non_object_census_is_zero_and_instrument_covered`）；
② 历史切点对账：`git show <历史 rev>:config.py` 要 rev 在对象库里
   （`test_absent_profile_name_is_not_read_as_no_drift`、
   `test_real_revs_still_report_drift`）。

处置口径（BD→BP 纪律的延伸）：**"没看"必须与"判干净"分形**——前提不成立时
显式 `pytest.skip` 且理由带实测读数（benchmark X/246、trace Y/8539、缺哪个
rev），不折叠成通过、也不折叠成失败。本地全量环境（作者机，归档与完整历史
均在盘）两项前提均成立，守卫不触发，行为与 BZ 轮之前逐位相同。

契约锁定的单文件工件（pinned 批次 / 损坏 trace 目录 / 逐位复现的报告）不在
本守卫范围——BZ 轮已按 .gitignore 放行入库（406 个文件 / 4.2 MB），fresh
clone 在场，那些锁照常执行。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# 全归档实测下界（2026-10-23 本机 macOS，Python 3.14.6；与 BY 轮登记口径
# 同源：扫描面 246 份 / 10,659 行）。低于下界 ⇒ 本环境没有完整语料。
_FULL_CORPUS_BENCHMARK_FILES = 246
_FULL_CORPUS_TRACE_DIRS = 138
_FULL_CORPUS_TRACE_FILES = 8539


def _measure_corpus() -> tuple[int, int, int]:
    bench = len(list(_ROOT.glob("experiments/results/**/benchmark_*.json")))
    trace_dirs = [d for d in _ROOT.glob("experiments/results/**/traces*") if d.is_dir()]
    trace_files = sum(len(list(d.glob("*.trace.jsonl"))) for d in trace_dirs)
    return bench, len(trace_dirs), trace_files


def require_full_corpus() -> None:
    """全归档语料在场守卫：低于实测下界 ⇒ 显式 skip（理由带读数）。

    调用方应为语料面普查类测试（扫描面下界断言以全归档校准）。完整语料
    环境（作者机 / 复现包解包后）三项全过，守卫静默；fresh clone 触发
    skip，CI 的 skipped 计数与理由均可见。
    """
    bench, dirs, files = _measure_corpus()
    if bench < _FULL_CORPUS_BENCHMARK_FILES or dirs < _FULL_CORPUS_TRACE_DIRS or files < _FULL_CORPUS_TRACE_FILES:
        pytest.skip(
            f"全归档语料不在场（benchmark_*.json {bench}/{_FULL_CORPUS_BENCHMARK_FILES}、"
            f"traces* 目录 {dirs}/{_FULL_CORPUS_TRACE_DIRS}、"
            f"trace 文件 {files}/{_FULL_CORPUS_TRACE_FILES}）——归档重产物按 Zenodo "
            "纪律不入库（.gitignore:172），本锁仅在完整语料环境执行"
        )


def require_history(*revs: str) -> None:
    """git 历史在场守卫：rev 不在对象库（shallow clone）⇒ 显式 skip。

    调用方应为跨历史切点的对账测试（`git show <rev>:config.py`）。
    fetch-depth=1 的 fresh clone 只有 HEAD 一个 commit，历史 rev 全部缺席。
    """
    for rev in revs:
        proc = subprocess.run(
            ["git", "-C", str(_ROOT), "cat-file", "-e", f"{rev}^{{commit}}"],
            capture_output=True,
        )
        if proc.returncode != 0:
            pytest.skip(
                f"历史切点 {rev[:12]} 不在场（shallow clone：actions/checkout 默认 "
                "fetch-depth=1）——本锁仅在完整历史环境执行"
            )
