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

注：需 LLM API 配置（config.LLM_API_*）；无 API 时 run_benchmark 的
各基线会按 rate_limit/error 占位，本脚手架仍会落盘工件 + 跑统计
（供人工补跑后重算）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_TASK_COUNT = 50
DEFAULT_SEED = 42
DEFAULT_BASELINES = "aitester,plain_llm,single_agent"
MAIN_BATCH_DIR = "experiments/results/main_batch"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="R4 主批次 runner（固定 seed n≥50，工件入 main_batch/ 白名单）",
    )
    p.add_argument("--dataset", default="synthetic", help="数据集名称（默认 synthetic，固定 task_id 前缀可复现）")
    p.add_argument(
        "--task-count", type=int, default=DEFAULT_TASK_COUNT, help=f"合成任务数（默认 {DEFAULT_TASK_COUNT}）"
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"合成数据集随机种子（默认 {DEFAULT_SEED}）")
    p.add_argument("--baselines", default=DEFAULT_BASELINES, help="基线方法列表（逗号分隔）")
    p.add_argument("--output-dir", default=MAIN_BATCH_DIR, help="输出目录（默认 main_batch/ 白名单）")
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
    return p.parse_args()


def _check_repo_clean() -> None:
    """P0-1（2026-10-05 独立审查）：dirty tree 硬失败。

    主批次 provenance 记录 git sha + git_dirty，但 sha 不足以复现工作树
    （历史主批次 provenance git_dirty=true——工件与代码态脱钩）。现把
    "干净树"前置为硬门禁（与 U2 复现硬失败同口径），豁免仅经
    --allow-dirty 显式给出。
    """
    import subprocess

    try:
        out = subprocess.run(
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


def main() -> None:
    args = _parse_args()
    if not args.allow_dirty:
        _check_repo_clean()
    _warn_llm_cache_if_enabled()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 导入 run_benchmark（副作用：加载 config 开关、校验 API 配置）
    import experiments.run_benchmark as rb

    deterministic = not args.no_deterministic
    print(f"R4 主批次：dataset={args.dataset} task_count={args.task_count} seed={args.seed}")
    print(
        f"基线：{args.baselines}；输出：{out_dir}；确定性采样：{'开（temp=0.0）' if deterministic else '关（对照口径）'}"
    )

    # 跑批次（run_benchmark.run_benchmark 内部已含 provenance 块 + M9 快照）
    summary = rb.run_benchmark(
        dataset_name=args.dataset,
        baselines=args.baselines.split(","),
        output_dir=str(out_dir),
        task_count=args.task_count,
        seed=args.seed,
        deterministic=deterministic,
    )

    # 定位刚产出的批次文件（按 mtime 最大定位）
    batch_files = sorted(out_dir.glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
    if not batch_files:
        print("⚠️ 未找到批次 JSON（API 缺失时各基线占位，统计将全 nan）", file=sys.stderr)
        return

    batch_path = batch_files[-1]
    print(f"批次工件：{batch_path}")
    _print_r4_summary(batch_path)

    if args.skip_stats:
        print("--skip-stats：跳过 R14 统计协议")
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


def _print_r4_summary(batch_path: Path) -> None:
    """R4：批次 M1 指标 + 三指标 + R52/R53 摘要打印（供人工/CI 判定批次质量）。"""
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
        regr_rate = round(sum(1 for r in det if r.get("regression_rate") == 1.0) / n * 100, 1) if n else None
        te_rate = round(sum(1 for r in det if r.get("test_error_rate") == 1.0) / n * 100, 1) if n else None
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
        print(f"    R4 regression_rate={regr_rate}% / N1 test_error_rate={te_rate}%")
        if fl1_meas:
            print(f"    R8 FL@1 命中率: {fl1_hit}/{fl1_meas} ({round(fl1_hit / fl1_meas * 100, 1)}%)")


if __name__ == "__main__":
    main()
