"""BZ 轮（2026-10-23）：归档语料与 git 历史深度的在场守卫（单一事实源）。

背景——CI 的 actions/checkout 默认 fetch-depth=1（shallow clone），归档重
产物按 .gitignore:172 + Zenodo 纪律不入库。两类测试的运行前提在 fresh
clone 里不成立，而此前它们的失败形态是 AssertionError / FileNotFoundError
（把"环境里没有"报成"锁被打破"）：

① 语料面普查：要全归档 239 份 `benchmark_*.json` / 138 个 `traces*` 目录 /
   8216 个 `*.trace.jsonl` 才够扫描面（`test_corpus_counts_are_stable`、
   `test_no_real_batch_collapses_any_row`、
   `test_non_arm_batches_are_admitted_by_name_not_dropped`、
   `test_repo_wide_non_object_census_is_zero_and_instrument_covered`）；
② 历史切点对账：`git show <历史 rev>:config.py` 要 rev 在对象库里
   （`test_absent_profile_name_is_not_read_as_no_drift`、
   `test_real_revs_still_report_drift`）。
③ 语料形状锁的**判定面**（EZ 轮，2026-10-27）：形状断言（文件数 / span 总数 /
   token 属性数）是对**入库语料**的断言，判定面必须是 `git ls-files`（fresh
   clone 逐位可达），不是作者机盘面。旧口径在盘面 `rglob` 上钉死数字，而盘面
   会随本地重跑增长（实测 1,456 → 1,495 份），入库面却只有 760 份 ⇒ 作者机必红、
   CI 被 ① 判 skip——两边都不判定。

处置口径（BD→BP 纪律的延伸）：**"没看"必须与"判干净"分形**——前提不成立时
显式 `pytest.skip` 且理由带实测读数（benchmark X/239、trace Y/8216、缺哪个
rev），不折叠成通过、也不折叠成失败。本地全量环境（作者机，归档与完整历史
均在盘）两项前提均成立，守卫不触发，行为与 BZ 轮之前逐位相同。

**作者机专属锁必须登记**（EZ 轮）：仍以「全归档在盘」为前提的锁（扫描面本身
就是全归档，例如「任何真批次都不折叠行集」的 0 实例断言）列在
`AUTHOR_ONLY_LOCKS`，理由逐条写明；`tests/test_corpus_census_ez.py` 用 AST
普查锁住「调用点集合 == 登记表」，新增未登记的作者机专属锁即红——不让
「CI 里永不执行」变成新增测试的默认形态。

契约锁定的单文件工件（pinned 批次 / 损坏 trace 目录 / 逐位复现的报告）不在
本守卫范围——BZ 轮已按 .gitignore 放行入库（406 个文件 / 4.2 MB），fresh
clone 在场，那些锁照常执行。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_TRACE_GLOB = "*.trace.jsonl"

# 全归档实测下界（2026-10-23 provider 清理后本机 macOS，Python 3.14.6；清理
# 删除了 7 份 benchmark 归档 + 323 份 trace，读数按删除后重算）。
# CI 轮重建（2026-10-24）：历史全量语料（239/138/8216）随数据清除退出，新完整
# 语料 = DeepSeek 重跑批（基础三批 + 补跑九族 + 两正式批，已全量入库）。
# **口径（EZ 轮更正）**：本下界只回答「作者机的重归档在不在盘」，量的是**盘面**
# （`rglob`），不承担任何形状断言——形状断言见下方 `ARCHIVED_*`（入库面）。
# 语料再增长时上调本下界（只升不降，防语料静默缩水）。
_FULL_CORPUS_BENCHMARK_FILES = 34
_FULL_CORPUS_TRACE_DIRS = 21
_FULL_CORPUS_TRACE_FILES = 1456

# —— EZ 轮（2026-10-27）：语料形状锁的判定面 = 入库面 ——
# 实测口径（本机 macOS / Python 3.14.6，`git ls-files` 与 `rglob` 同一次读）：
#   入库面 760 份 / 4,139 span / 2,280 token 属性 / 2,280 逐字段核对
#   盘面   1,495 份 / 9,658 span（+735 份本地重跑语料，按 .gitignore 不入库）
# 只升不降：语料入库后同步刷新；盘面增长不改变这些数字。
# B1 批（2026-10-30）：specir/gold probe 归档 25 份 trace 随证据整批入库
# （emse_ult_specir_probe_20261014/traces/，见 f725a3d2）⇒ 785 / 4,487；
# token 属性与逐字段核对 2,280 → 2,355（otel 形状测试实测报数，同批刷新）。
ARCHIVED_TRACE_FILES = 785
ARCHIVED_SPANS = 4487
ARCHIVED_TOKEN_ATTRS = 2355
ARCHIVED_TOKEN_FIELD_CHECKS = 2355

# 作者机专属锁登记表：(测试文件, 为什么不能改判入库面)。
# 这些锁的扫描面本身就是「全归档」（含未入库批次），改吃入库面会把断言静默
# 缩面；它们在 fresh clone 里 skip 是**声明过的**形态，不是遗漏。
AUTHOR_ONLY_LOCKS: tuple[tuple[str, str], ...] = (
    (
        "tests/test_effective_green_ba.py",
        "「全仓非 oracle 标记行 111 条 / detection=1.0 共 12 条」是对全归档 34 份批次的普查；"
        "入库面只有 16 份，改判入库面会把 0 实例断言静默缩成子集断言",
    ),
    (
        "tests/test_experiments_arm_row_collapse_ab12.py",
        "「任何真批次都不折叠行集」的 0 实例断言与分桶平账都以全归档为扫描面；入库面子集不足以支撑「任何」这个量词",
    ),
    (
        "tests/test_experiments_mast_nonobject_ab12.py",
        "「全仓非对象 JSONL 行 0 实例」同上：量词是全仓，入库面无法替代",
    ),
    (
        "tests/test_model_fingerprint.py",
        "同一断言里同时读盘面 on_disk=34 与入库面 tracked=16 两个面；前者天然是作者机专属读数，判据要求两面都成立",
    ),
    (
        "tests/test_token_usage_summary_ax.py",
        "顶层 benchmark 的 12 个 token 块是全盘面读数（入库面不含未入库批次），改判入库面会让均值复算丢样本",
    ),
)


def disk_trace_files(root: Path | None = None) -> list[Path]:
    """盘面 trace 语料（作者机的全部重产物，含未入库批次）。"""
    base = _ROOT if root is None else root
    return sorted(p for p in base.rglob(_TRACE_GLOB) if p.is_file())


def archived_trace_files(root: Path | None = None) -> list[Path]:
    """入库面 trace 语料：`git ls-files` ∩ 盘面。

    fresh clone 与本机同口径可达（本机多出来的未入库批次不在其中）。git 不可用
    时**不降级到盘面**——那会把「入库面」偷换成「盘面」，正是 EZ 轮修掉的缺陷；
    取不到就显式 skip 并说明。
    """
    base = _ROOT if root is None else root
    proc = subprocess.run(
        ["git", "-C", str(base), "ls-files", "-z", "--", _TRACE_GLOB],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(
            f"git 不可用，无法判定入库面（{proc.stderr.strip() or 'rc=' + str(proc.returncode)}）"
            "——形状锁只在能区分入库面与盘面时执行"
        )
    names = [name for name in proc.stdout.split("\0") if name]
    return sorted(path for path in (base / name for name in names) if path.is_file())


def local_extra_trace_files(root: Path | None = None) -> list[Path]:
    """本地未入库的 trace 语料（盘面 − 入库面）：只跑不变量，不进形状分母。"""
    archived = set(archived_trace_files(root))
    return [path for path in disk_trace_files(root) if path not in archived]


def shape_problem(observed: int, pinned: int, label: str) -> str:
    """形状断言的问题描述（空串 = 一致）。判定面必须已由调用方定为入库面。"""
    if observed == pinned:
        return ""
    return (
        f"{label}与入库面锁定值不一致：{observed} != {pinned}——"
        "形状锁的判定面是 `git ls-files`（入库面），不是本机盘面；"
        "先复测入库面再改锁"
    )


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

    **EZ 轮约束**：新增调用点必须同时登记进 `AUTHOR_ONLY_LOCKS`（写明为什么
    不能改判入库面）——`tests/test_corpus_census_ez.py` 会做 AST 普查。
    """
    bench, dirs, files = _measure_corpus()
    if bench < _FULL_CORPUS_BENCHMARK_FILES or dirs < _FULL_CORPUS_TRACE_DIRS or files < _FULL_CORPUS_TRACE_FILES:
        pytest.skip(
            f"全归档语料不在场（benchmark_*.json {bench}/{_FULL_CORPUS_BENCHMARK_FILES}、"
            f"traces* 目录 {dirs}/{_FULL_CORPUS_TRACE_DIRS}、"
            f"trace 文件 {files}/{_FULL_CORPUS_TRACE_FILES}）——归档重产物按 Zenodo "
            "纪律不入库（.gitignore:172），本锁仅在完整语料环境执行；"
            "形状类断言请改吃 `archived_trace_files()`（入库面）"
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
