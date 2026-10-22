#!/usr/bin/env python
"""
R4（2026-09-30 独立审查 P0）：主批次运行脚手架。

固定 seed n≥50 的主批次 runner——把"跑主批次 + 工件入库 + provenance
快照"固化为可复现命令（论文数字可追溯、可复算）：

    .venv/bin/python experiments/run_main_batch.py \
        --dataset synthetic --task-count 50 --seed 42 \
        --baselines aitester,plain_llm,single_agent \
        --output-dir experiments/results/main_batch

工件落在 experiments/results/main_batch/（.gitignore 白名单入库），
含：
- benchmark_synthetic_*.json（完整结果 + provenance 块）
- statistical_report.md（R14 二值统计协议：McNemar/binomtest/FDR）

统计协议自动跑 run_all_statistics（含 M13 批次白名单锁定——仅统计
本批次产出的文件，消除"p 值由 glob 顺序决定"的可复现性缺陷）。

本脚本是 run_benchmark.py 的薄壳包装：不修改任何指标口径，仅
- 固定 seed / task-count（可复现）；
- 输出目录锁定 main_batch/（.gitignore 白名单）；
- 跑完后自动调 statistical_analysis.run_all_statistics（R14 协议）。

用法（CI / 夜间）：
    .venv/bin/python experiments/run_main_batch.py --dataset synthetic \
        --task-count 50 --seed 42 --baselines aitester,plain_llm,single_agent

    # 真实数据集（如 quixbugs / ult）的任务数截断（L 轮 2026-10-17 修复）：
    .venv/bin/python experiments/run_main_batch.py --dataset quixbugs \
        --task-limit 3 --baselines plain_llm_df        # 或 --task-count 3（等价）
    注：--task-count 在真实数据集上历史口径被静默忽略（只对合成数据集生成任务数
    生效）；L 轮起显式给出时按任务上限生效（等价 --task-limit），不显式给出则全量。

注：需 LLM API 配置（config.LLM_API_*）；无 API 时 run_benchmark 的
各基线会按 rate_limit/error 占位，本脚手架仍会落盘工件 + 跑统计
（供人工补跑后重算）。
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.analysis_parts.check_leg_analysis import (  # noqa: E402
    CHECK_LEG_CHANNELS,
    CHECK_LEG_LABELS,
    _check_leg_measurability,
)

DEFAULT_TASK_COUNT = 50
DEFAULT_SEED = 42
DEFAULT_BASELINES = "aitester,plain_llm,single_agent"
MAIN_BATCH_DIR = "experiments/results/main_batch"

# L 轮（2026-10-17）CLI 语义修复：run_benchmark 里 task_count 只对合成数据集
# 生效（生成 N 个任务），真实数据集的"限制运行任务数"是 task_limit；本脚手架
# 此前只暴露 --task-count 且原样透传，导致 `--task-count 3 --dataset quixbugs`
# **静默跑满 50 任务**（pilot 实测：进度条从 0/50 开始，--task-count 3 被忽略；
# 缺陷证据见 experiments/results/l_round_pilot_20261017/defect_repro/）。
# 修复口径（最小惊讶 + 历史命令向后兼容）：
#   - --task-count 默认改 None（不显式给 = 历史默认行为）；
#   - 合成数据集：None → DEFAULT_TASK_COUNT（与历史默认 50 一致）；
#   - 真实数据集：显式 --task-count 现在**按任务上限生效**（等价 --task-limit，
#     这是用户写该参数时的本意）；不显式给则全量（历史行为不变）；
#   - 新增 --task-limit 显式入口（对任意数据集生效，优先于 --task-count）。
_SYNTHETIC_DATASETS = ("synthetic", "synth")


def resolve_task_scope(
    dataset: str,
    task_count: int | None,
    task_limit: int | None,
) -> tuple[int | None, int | None, list[str]]:
    """把 CLI 的 ``--task-count`` / ``--task-limit`` 解析为 run_benchmark 的两个入参。

    主批次 runner 的 ``--task-count`` 历史语义只覆盖合成数据集（生成任务数），
    但真实数据集上它会被 run_benchmark **静默忽略**（真实数据集限任务是
    ``task_limit``）——L 轮 pilot 实测 ``--task-count 3 --dataset quixbugs``
    跑满 50 任务。本函数把口径收敛为一处、可单测：

    Args:
        dataset: 数据集名（大小写/空白不敏感）。
        task_count: CLI 显式给出的任务数（None = 未给出）。
        task_limit: CLI 显式给出的任务上限（None = 未给出）。

    Returns:
        ``(effective_task_count, effective_task_limit, notices)``：
        - 合成数据集：effective_task_count = 显式值或 DEFAULT_TASK_COUNT；
          effective_task_limit 原样透传（两者可叠加：先生成后截断）；
        - 真实数据集：effective_task_count = None（不生成）；limit 取
          ``task_limit``，未给时回退显式 ``task_count``（修复静默忽略）；
        - notices: 面向操作者的告警/说明行（不阻断）。

    边界归一（与 run_benchmark.task_limit 口径一致）：<1 视为无效并归 None，
    同时追加 notice（不静默改变任务数）。
    """
    name = (dataset or "").strip().lower()
    notices: list[str] = []

    def _normalize(value: int | None, flag: str) -> int | None:
        if value is None:
            return None
        if value < 1:
            notices.append(f"{flag}={value} 无效（需正整数），按未给出处理")
            return None
        return value

    count = _normalize(task_count, "--task-count")
    limit = _normalize(task_limit, "--task-limit")

    if name in _SYNTHETIC_DATASETS:
        effective_count = count if count is not None else DEFAULT_TASK_COUNT
        return effective_count, limit, notices

    effective_limit = limit
    if limit is None and count is not None:
        effective_limit = count
        notices.append(
            f"非合成数据集 {name}：--task-count={count} 按任务上限生效"
            "（等价 --task-limit；历史口径该参数被静默忽略，L 轮修复）"
        )
    elif limit is not None and count is not None and limit != count:
        notices.append(f"非合成数据集 {name}：--task-limit={limit} 优先，--task-count={count} 被忽略")
    return None, effective_limit, notices


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="R4 主批次 runner（固定 seed n≥50，工件入 main_batch/ 白名单）",
    )
    p.add_argument("--dataset", default="synthetic", help="数据集名称（默认 synthetic，固定 task_id 前缀可复现）")
    p.add_argument(
        "--task-count",
        type=int,
        default=None,
        help=(
            f"任务数：合成数据集=生成任务数（缺省 {DEFAULT_TASK_COUNT}）；"
            "真实数据集=按上限截断（等价 --task-limit，显式给出时生效）"
        ),
    )
    p.add_argument(
        "--task-limit",
        type=int,
        default=None,
        help="限制运行任务数量（对任意数据集生效；优先于 --task-count；缺省=全量）",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"合成数据集随机种子（默认 {DEFAULT_SEED}）")
    p.add_argument("--baselines", default=DEFAULT_BASELINES, help="基线方法列表（逗号分隔）")
    p.add_argument("--output-dir", default=MAIN_BATCH_DIR, help="输出目录（默认 main_batch/ 白名单）")
    p.add_argument(
        "--staging-dir",
        default=None,
        help=(
            "跑批后把本次新增工件自动移到该目录（仓库外），保持工作树干净——"
            "多种子顺序跑批（第二批不被干净树门禁拒绝）的代码化"
            "（E2 双种子'暂移-恢复'两次手工实操的固化）。禁止含 .. 的路径；"
            "不得位于输出目录内。移回：mv <staging>/* <output-dir>/"
        ),
    )
    p.add_argument("--skip-stats", action="store_true", help="跳过 R14 统计协议（仅跑批次）")
    # P0-1（2026-10-05 独立审查）：主批次 = 论文数字通道，确定性采样为默认
    # 协议（R11：temp 强制 0.0 三处级联）；--no-deterministic 显式退出
    # （对照实验用，provenance 仍如实记录生效温度）。
    p.add_argument(
        "--no-deterministic",
        action="store_true",
        help="退出确定性采样协议（默认强制 TEMPERATURE=0.0；仅对照实验使用）",
    )
    # P0-1：dirty tree 拒绝——git sha 不足以复现代码态时硬失败（U2 先例），
    # --allow-dirty 显式豁免（provenance 记录 git_dirty=true 供审计）
    p.add_argument("--allow-dirty", action="store_true", help="豁免 dirty tree 拒绝（不推荐，仅调试）")
    # R15（2026-10-08 R2）：脏树豁免原因登记——与 --allow-dirty 配套，写入
    # provenance.dirty_reason（供工件审计）；未给原因时填 "unspecified"
    # （保持向后兼容，但豁免本身可见）。
    p.add_argument(
        "--dirty-reason",
        default=None,
        help="--allow-dirty 的豁免原因（写入 provenance.dirty_reason；缺省 unspecified）",
    )
    # R-P0-4（2026-10-06 第九轮审查）：主批次应带同池模板重复上限，防单
    # pattern 分布塌缩（旧批次 import_chain_type_contract×10 病理）。透传
    # run_benchmark.max_pattern_repeat（AA 批次已实现）；默认 None=历史口径。
    p.add_argument(
        "--max-pattern-repeat",
        dest="max_pattern_repeat",
        type=int,
        default=None,
        help="合成数据集同池模板重复上限（仅 synthetic 生效；>=1 时同 (difficulty, pattern) 至多出现 N 次；默认 None=历史口径）",
    )
    # AM1（2026-10-06 第十三轮审查 / 预注册 E6 执行前置）：臂级每任务
    # token 硬上限映射（"aitester=4223,plain_llm_df=26115"），透传
    # run_benchmark.per_task_token_caps；默认 None=历史口径无上限。
    # E6 预算匹配臂专用——standard 臂口径不受影响。
    p.add_argument(
        "--per-task-token-caps",
        dest="per_task_token_caps",
        default=None,
        help="臂级每任务 token 硬上限映射（arm=cap 逗号分隔，如 'aitester=4223'；默认 None=历史口径；超限走 budget_exceeded 停止通道；预注册 E6 预算匹配臂专用）",
    )
    return p.parse_args()


def _check_repo_clean() -> None:
    """P0-1（2026-10-05 独立审查）：dirty tree 硬失败。

    主批次 provenance 记录 git sha + git_dirty，但 sha 不足以复现工作树
    （历史主批次 provenance git_dirty=true——工件与代码态脱钩）。现把
    "干净树"前置为硬门禁（与 U2 复现硬失败同口径），豁免仅经
    --allow-dirty 显式给出。
    """
    import subprocess

    from src.utils.process_utils import run_with_timeout

    try:
        out = run_with_timeout(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"⚠️ git status 不可用（{e}），跳过 dirty tree 检查（非 git 环境合法）")
        return
    if out.stdout.strip():
        print(
            "❌ 工作树不干净——主批次实验要求 git 干净树（provenance git sha 才足以复现代码态）：\n"
            f"{out.stdout}\n"
            "请先 commit/stash 全部改动；如确需带脏树跑（调试用），加 --allow-dirty。",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _assert_provenance_dirty(batch_path: Path, *, allow_dirty: bool) -> None:
    """R15（2026-10-08 R2）：跑批后 provenance 脏树断言（防御竞态/绕过）。

    前置 `_check_repo_clean` 在跑批**开始前**硬拒绝脏树，但存在两类残余风险：
    ① 跑批期间工作树被外部改动（竞态）；② 其他路径绕过门禁直接调用
    run_benchmark。本断言在批次工件落盘后复核 provenance：
    - 未给 --allow-dirty 而 provenance.git_dirty=True → 抛错（拒绝把代码态
      不可复现的批次当作干净批次工件留存）；
    - 给了 --allow-dirty → provenance 必须含 dirty_reason（豁免可审计；
      缺省应为 "unspecified"）。
    provenance 不可读时仅告警跳过（不因辅助断言阻断主流程）。
    """
    try:
        prov = json.loads(batch_path.read_text(encoding="utf-8")).get("provenance") or {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ 无法读取 provenance 做脏树断言（{e}），跳过", file=sys.stderr)
        return
    if not allow_dirty and bool(prov.get("git_dirty")):
        raise SystemExit(
            "❌ 未使用 --allow-dirty 但 provenance.git_dirty=True——工作树在跑批期间变脏"
            "（竞态/绕过干净树门禁）。请清理工作树后重跑，或显式加"
            " --allow-dirty --dirty-reason '<原因>'（并随工件登记豁免）。"
        )
    if allow_dirty and not prov.get("dirty_reason"):
        raise SystemExit(
            "❌ --allow-dirty 已给出但 provenance.dirty_reason 缺失——豁免必须登记原因（缺省应填 'unspecified'）。"
        )


def _warn_llm_cache_if_enabled() -> None:
    """P0-1：LLM 文件缓存开启时警告（缓存命中使"重复实验"非独立样本）。

    不阻断：首批运行缓存是合法的省钱手段；重跑协议（同 prompt 重测）必须
    AITESTER_LLM_CACHE=0，此处仅提示，避免"看起来重跑了实际全是缓存"。
    """
    if os.getenv("AITESTER_LLM_CACHE", "1").strip().lower() not in ("0", "false", "off"):
        print(
            "⚠️ AITESTER_LLM_CACHE 未禁用：LLM 文件缓存（TTL 7 天）命中时同 prompt 不再调用 LLM——\n"
            "   重跑/重复实验请设 AITESTER_LLM_CACHE=0，否则观测非独立样本（p 值失真）。",
            file=sys.stderr,
        )


def _validated_staging_dir(staging: str, out_dir: Path) -> Path:
    """校验 --staging-dir（路径穿越防御：拒绝 .. 分量；禁止位于输出目录内）。

    Returns:
        解析后的绝对 Path。

    Raises:
        SystemExit: 校验失败（含原因）。
    """
    candidate = Path(staging).expanduser()
    if ".." in candidate.parts:
        print(f"❌ --staging-dir 含 '..' 分量（{staging}）——禁止路径穿越。", file=sys.stderr)
        raise SystemExit(2)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(out_dir.resolve())
    except ValueError:
        pass
    else:
        print(f"❌ --staging-dir（{staging}）不得位于输出目录（{out_dir}）内。", file=sys.stderr)
        raise SystemExit(2)
    return resolved


def _snapshot_files(root: Path) -> set[Path]:
    """递归快照 root 下既有文件集合（跑批前调用，供跑后差集定位新工件）。"""
    return {p for p in root.rglob("*") if p.is_file()}


def _stage_out_new_artifacts(out_dir: Path, staging_dir: Path, before: set[Path]) -> list[Path]:
    """把跑批新增工件移入 staging 目录（保持相对路径结构），返回移动清单。

    E2 双种子实操固化的代码版：第一批产物落在 tracked 目录即令工作树变脏，
    第二批被 _check_repo_clean 拒绝——此前两次手工"暂移-恢复"，现固化。
    只移动新文件，不触碰既有工件（SHA256SUMS 等入库物不受影响）。
    """
    import shutil

    moved: list[Path] = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path in before:
            continue
        target = staging_dir / path.relative_to(out_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moved.append(target)
    return moved


def _sweep_own_patch_snap_dirs() -> None:
    """删除**本进程**遗留的 `aitester_patch_snap_<pid>_*` 目录（仅当已空）。

    2026-10-09（审查报告 §11.1b 结果十八：临时目录泄漏）：`_safe_write_patch`
    的快照目录按 `pid_thread` 命名、**跨任务复用**，而只有"回滚"路径会
    `os.remove` 快照**文件**（且从不删目录）；未回滚的快照文件会一直留存 →
    长跑批在 TMPDIR 下持续累积。

    保守口径：① 只匹配 `aitester_patch_snap_<本进程pid>_` 前缀——绝不触碰
    其他进程/其他前缀的目录；② 只 `os.rmdir`（非空即抛错跳过），**不递归
    删除**——残留快照文件不会被误删（其内容可能仍被 state 引用）；
    ③ 任何异常静默忽略（纯清理路径，不得影响批次退出码）。
    """
    pattern = os.path.join(tempfile.gettempdir(), f"aitester_patch_snap_{os.getpid()}_*")
    for d in glob.glob(pattern):
        # 仅空目录成功；非空抛 OSError 被 suppress 吞掉（保留残留快照文件）
        with contextlib.suppress(OSError):
            os.rmdir(d)


def main() -> None:
    args = _parse_args()
    if not args.allow_dirty:
        _check_repo_clean()
    # R15：脏树豁免原因（仅 allow_dirty 时生效）——未给原因填 "unspecified"
    dirty_reason = None
    if args.allow_dirty:
        dirty_reason = (args.dirty_reason or "").strip() or "unspecified"
    _warn_llm_cache_if_enabled()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 批次 VI（2026-10-07）：--staging-dir 前置——跑前快照既有工件，
    # 跑后把新增工件外移（多种子顺序跑批不再触发干净树门禁）
    staging_dir = _validated_staging_dir(args.staging_dir, out_dir) if args.staging_dir else None
    files_before = _snapshot_files(out_dir) if staging_dir is not None else set()

    def _stage_and_report() -> None:
        """批次 VI 收尾：新工件外移 + 移回提示（--skip-stats 早退同样执行）。"""
        if staging_dir is None:
            return
        moved = _stage_out_new_artifacts(out_dir, staging_dir, files_before)
        print(f"\n--staging-dir：本次新增工件 {len(moved)} 件已外移至 {staging_dir}")
        for target in moved:
            print(f"  - {target}")
        print(f"移回入库：mv {staging_dir}/* {out_dir}/（随后重算 SHA256SUMS）")

    # 导入 run_benchmark（副作用：加载 config 开关、校验 API 配置）
    import experiments.run_benchmark as rb

    deterministic = not args.no_deterministic
    # L 轮：任务范围解析（--task-count 在真实数据集上的静默忽略缺陷修复；
    # 两个入参分开透传：task_count=生成数 / task_limit=截断数）。
    effective_task_count, effective_task_limit, _task_notices = resolve_task_scope(
        args.dataset, args.task_count, args.task_limit
    )
    for _notice in _task_notices:
        print(f"⚠️ {_notice}", file=sys.stderr)
    _scope_desc = (
        f"生成 {effective_task_count} 个"
        if effective_task_count is not None
        else ("全量任务" if effective_task_limit is None else f"全量数据集前 {effective_task_limit} 个任务")
    )
    print(f"R4 主批次：dataset={args.dataset} task_count={args.task_count} seed={args.seed}（{_scope_desc}）")
    print(
        f"基线：{args.baselines}；输出：{out_dir}；确定性采样：{'开（temp=0.0）' if deterministic else '关（对照口径）'}"
    )

    # 跑批次（run_benchmark.run_benchmark 内部已含 provenance 块 + M9 快照）
    summary = rb.run_benchmark(
        dataset_name=args.dataset,
        baselines=args.baselines.split(","),
        output_dir=str(out_dir),
        task_count=effective_task_count,
        task_limit=effective_task_limit,
        seed=args.seed,
        deterministic=deterministic,
        max_pattern_repeat=args.max_pattern_repeat,
        per_task_token_caps=args.per_task_token_caps,
        dirty_reason=dirty_reason,
    )

    # 定位刚产出的批次文件（按 mtime 最大定位）
    batch_files = sorted(out_dir.glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
    if not batch_files:
        print("⚠️ 未找到批次 JSON（API 缺失时各基线占位，统计将全 nan）", file=sys.stderr)
        return

    batch_path = batch_files[-1]
    print(f"批次工件：{batch_path}")
    _assert_provenance_dirty(batch_path, allow_dirty=bool(args.allow_dirty))
    _print_r4_summary(batch_path)

    if args.skip_stats:
        print("--skip-stats：跳过 R14 统计协议")
        _stage_and_report()
        return

    # R14 统计协议（M13 批次白名单锁定：仅统计本批次文件）
    print("\n" + "=" * 60)
    print("R14 统计协议（McNemar/binomtest/FDR，M13 批次白名单锁定）")
    print("=" * 60)
    from experiments.statistical_analysis import load_experiment_results, run_all_statistics

    # M13：批次白名单（相对 results_dir 的路径——本批次在 main_batch/ 子目录，
    # batch_path.name 缺父目录会解析不到；用 relative_to 生成正确相对路径）
    batch_rel = batch_path.relative_to(out_dir.parent).as_posix()
    results = load_experiment_results(str(out_dir.parent), [batch_rel])
    # P0-1（2026-10-05 独立审查）修复：run_all_statistics 同步传入批次白名单
    # ——此前仅 load_experiment_results 用白名单（结果只喂 task_counts 计数），
    # 报告本体走 glob 全目录，统计分母与白名单脱钩（跨批次重复任务混入）
    run_all_statistics(
        str(out_dir.parent),
        str(out_dir / "statistical_report.md"),
        batch_files=[batch_rel],
    )
    summary["r14_batch_whitelist"] = {
        "batch_file": batch_rel,
        "task_counts": {bl: len(rows) for bl, rows in results.items()},
    }
    print(f"\nR14 统计报告：{out_dir / 'statistical_report.md'}")
    print(f"批次白名单锁定：{json.dumps(summary['r14_batch_whitelist'], ensure_ascii=False)}")

    # 批次 VI：--staging-dir 后置——新工件外移（含统计报告），工作树保持
    # 干净（第二批种子可直接顺序执行）；提交前 mv 回 output-dir 入库。
    _stage_and_report()


def _print_r4_summary(batch_path: Path) -> None:
    """R4：批次 M1 指标 + 三指标 + R52/R53 摘要打印（供人工/CI 判定批次质量）。

    BM 轮（2026-10-22）口径：R4/N1 与 M1 三指标一样带"可测 k/n"——分母只数
    该指标真正可测的行，不可测（None/缺键）行不再被算成"没回归/没测试错误"。
    """
    with open(batch_path, encoding="utf-8") as f:
        d = json.load(f)
    print("\n" + "=" * 60)
    print("R4 批次摘要（M1 三指标 + R52/R53/R8）")
    print("=" * 60)
    for bl, rd in d.get("results", {}).items():
        det = rd.get("details", [])
        n = len(det)
        if n == 0:
            continue
        m1_meas = [r for r in det if r.get("detection_rate") is not None]
        m1_denom = len(m1_meas)
        det_rate = (
            round(sum(1 for r in m1_meas if r["detection_rate"] == 1.0) / m1_denom * 100, 1) if m1_denom else None
        )
        rep_rate = round(sum(1 for r in m1_meas if r["repair_rate"] == 1.0) / m1_denom * 100, 1) if m1_denom else None
        ff_rate = round(sum(1 for r in m1_meas if r["false_fix_rate"] == 1.0) / m1_denom * 100, 1) if m1_denom else None
        # BM 轮（2026-10-22）：R4/N1 与上面 M1 三指标同口径——分母只用**可测**行。
        # 此前用 n（全部行）：None/缺键行等于按"没回归 / 没测试错误"计分，而 0.0%
        # 恰好是最好看的读数。实测归档 11197 行里 regression_rate 可测 0 行
        # （8012 None + 3185 缺键），故这一路恒打印 0.0%；test_error_rate 可测
        # 7206/11197，现口径 7.3% vs 可测口径 11.3%。不可测时明写"不可测"，
        # 不再输出会被读成"零回归"的 0.0%。
        regr_meas = [r for r in det if r.get("regression_rate") is not None]
        te_meas = [r for r in det if r.get("test_error_rate") is not None]
        regr_k, te_k = len(regr_meas), len(te_meas)
        regr_rate = (
            round(sum(1 for r in regr_meas if r["regression_rate"] == 1.0) / regr_k * 100, 1) if regr_k else None
        )
        te_rate = round(sum(1 for r in te_meas if r["test_error_rate"] == 1.0) / te_k * 100, 1) if te_k else None
        fl1 = [r.get("fl_at_k") or {} for r in det]
        fl1_hit = sum(1 for x in fl1 if x.get("fl_at_1") == 1.0)
        fl1_meas = sum(1 for x in fl1 if x.get("fl_at_1") is not None)
        print(
            f"  [{bl}] success={rd.get('success_rate', 0)}% "
            f"(有效 {rd.get('effective_total', n)}/{n}，剔除 harness_invalid={rd.get('harness_invalid_count', 0)})"
        )
        print(
            f"    M1 三指标（可测 {m1_denom}/{n} 任务）: detection={det_rate}% repair={rep_rate}% false_fix={ff_rate}%"
        )
        regr_text = f"{regr_rate}%" if regr_rate is not None else "不可测（无可测行）"
        te_text = f"{te_rate}%" if te_rate is not None else "不可测（无可测行）"
        print(
            f"    R4 regression_rate={regr_text}（可测 {regr_k}/{n}） / N1 test_error_rate={te_text}（可测 {te_k}/{n}）"
        )
        # BQ 轮（2026-10-22）：四个 status 通道的可测量性披露（与 R4/N1 同风格）。
        # 改前摘要块对四键零读者：归档/新批次里"四腿跑过且干净"与"崩了 / 按设计
        # 没跑 / 没记录"在批次摘要里同形。只加分档计数，不改任何判定——四键不
        # 进入通过/拒绝，recorded=0 时明写"未记录"而非 0（0 会被读成"干净"）。
        leg = _check_leg_measurability(det)
        if leg["recorded_rows"]:
            parts = [
                f"{CHECK_LEG_LABELS[channel]} ok={ch['ok']} 没测成={ch['error'] + ch['unavailable']}"
                f" 没跑={ch['disabled']} 未记录={ch['null'] + ch['absent']}"
                for channel in CHECK_LEG_CHANNELS
                for ch in [leg["channels"][channel]]
            ]
            print(
                f"    BQ 检查腿（记录 {leg['recorded_rows']}/{n} 行，任一腿没测成"
                f" {leg['rows_any_unmeasurable']} 行）: {'；'.join(parts)}"
            )
        else:
            print("    BQ 检查腿: 未记录（早于 BN 轮落盘，不可读作「干净」）")
        if fl1_meas:
            print(f"    R8 FL@1 命中率: {fl1_hit}/{fl1_meas} ({round(fl1_hit / fl1_meas * 100, 1)}%)")


if __name__ == "__main__":
    # 2026-10-09（审查报告 §11.1b 结果十九）：批次级临时目录清扫放在入口侧，
    # **不改动 main() 函数体**——既有接线锁（tests/test_batch_vi.py
    # TestWiringLocks）以 inspect.getsource(main) 断言 staging 双出口接线，
    # 若把 main() 包进 try/finally 并抽出 _main_body，会误伤该锁的语义。
    # 此处 try/finally 保证正常退出、异常退出、--skip-stats 早退都执行清扫。
    try:
        main()
    finally:
        _sweep_own_patch_snap_dirs()
