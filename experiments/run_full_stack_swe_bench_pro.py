"""
G8 全开链路 SWE-bench Pro 复测脚本。

用途（gap_report_2026-09-28 P0 缺口 G8）：
    开启"全开链路"开关后运行 SWE-bench Pro（或 SWE-bench 子集）基准复测，
    验证 ②⑦⑧ 方向（跨文件修复 / 运行时探针 / 策略银行 / 专家池）在真实
    数据上是否产生正向收益，是判断"默认关模块开启后收益"的唯一数据入口。

全开开关（环境变量，均默认 false；本脚本在运行时显式导出为 true）：
    - RUNTIME_PROBE_ENABLE=true        运行时探针采集层（src/agents/runtime_probe.py）
    - STRATEGY_BANK_ENABLE=true        策略银行（src/tools/strategy_bank.py）
    - EXPERT_POOL_ENABLE=true          并行专家 Agent 池（src/graph/expert_pool.py）
    - CROSS_FILE_ENABLE=true           跨文件修复（src/tools/cross_file.py）
    - CROSS_FILE_BIDIRECTIONAL=true    双向依赖图（可选，默认关）
    - REPO_LEVEL_EXECUTION=true        仓库级执行器（src/agents/executor_repo.py）
    - SWE_REPO_VENV_ISOLATION=true     仓库级 venv 隔离（可选）
    - AITESTER_TRACE_DIR=<dir>         节点级 JSONL 追踪（供事后分析）

数据前置（必须先通过）：
    SWE-bench Pro 数据目录需经 `scripts/check_swe_bench_pro_ready.py` 校验
    （"数据集无可用源码"阻塞已解决：SWE_BENCH_ENRICHMENT 注入真实
    instance_code + RepoExecutor 仓库级验证）。本脚本执行前会先调用该
    检查，未通过时直接退出（不浪费 LLM token 跑无信息量批次）。

使用方式：
    python experiments/run_full_stack_swe_bench_pro.py --data-dir /path/to/pro_data
    python experiments/run_full_stack_swe_bench_pro.py --data-dir ... --task-limit 5 --on-only
    python experiments/run_full_stack_swe_bench_pro.py --dataset swe_bench --subset lite --task-limit 7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _apply_full_stack_env(output_dir: str) -> dict[str, str]:
    """导出全开链路环境变量（含追踪目录），返回实际生效的配置 dict。

    Args:
        output_dir: 结果输出目录（追踪目录落在其下）。

    Returns:
        生效的环境变量 dict（供结果 JSON 记录，可复现）。
    """
    trace_dir = os.path.join(output_dir, "traces")
    env = {
        "RUNTIME_PROBE_ENABLE": "true",
        "STRATEGY_BANK_ENABLE": "true",
        "EXPERT_POOL_ENABLE": "true",
        "CROSS_FILE_ENABLE": "true",
        "CROSS_FILE_BIDIRECTIONAL": "true",
        "REPO_LEVEL_EXECUTION": "true",
        "SWE_REPO_VENV_ISOLATION": "true",
        "AITESTER_TRACE_DIR": trace_dir,
    }
    for key, value in env.items():
        os.environ[key] = value
    os.makedirs(trace_dir, exist_ok=True)
    return env


def _check_pro_data_ready(data_dir: str | None, dataset: str) -> bool:
    """执行 G8 数据前置检查（scripts/check_swe_bench_pro_ready.py）。

    仅当 dataset 为 SWE-bench Pro / SWE-bench 时执行；内置 examples /
    synthetic 数据集无 Pro 数据前置要求，直接返回 True（跳过检查）。

    Args:
        data_dir: 数据目录（Pro 场景需非空；SWE-bench 场景读环境变量）。
        dataset: 数据集名（swe_bench_pro / swe_bench / examples / synthetic）。

    Returns:
        数据是否就绪（True = 可执行全开链路复测）。
    """
    if dataset in ("examples", "synthetic", "synth"):
        return True
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
    from check_swe_bench_pro_ready import check_pro_ready

    resolved_dir = data_dir or os.getenv("AITESTER_SWE_BENCH_PRO_DIR") or os.getenv("SWE_BENCH_DATA_DIR")
    if not resolved_dir:
        resolved_dir = os.path.join(os.path.expanduser("~"), ".cache", "aitester", "swe_bench_pro")
    enrichment = os.getenv("SWE_BENCH_ENRICHMENT")
    report = check_pro_ready(resolved_dir, enrichment=enrichment)
    print(f"\n[G8 前置检查] 数据目录: {resolved_dir}")
    print(f"[G8 前置检查] 任务总数: {report['total_tasks']}，就绪: {report['ready_tasks']}")
    if not report["ready"]:
        for task_id, issues in list(report["task_issues"].items())[:10]:
            print(f"  - {task_id}: {'; '.join(issues)}")
        print("[G8 前置检查] ❌ 数据未就绪，终止全开链路复测（先补齐 instance_code / test_patch / FAIL_TO_PASS）")
        return False
    print("[G8 前置检查] ✅ 数据就绪，开始全开链路复测")
    return True


def _run_full_stack_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    """调用 run_benchmark 执行全开链路基准测试。

    Args:
        args: 解析后的命令行参数。

    Returns:
        基准测试汇总 dict（含 results / token_metrics 等）。
    """
    from experiments.run_benchmark import run_benchmark

    baselines = [b.strip() for b in args.baselines.split(",") if b.strip()]
    enable_rag: bool | None
    if args.no_rag:
        enable_rag = False
    elif args.enable_rag:
        enable_rag = True
    else:
        enable_rag = None

    summary = run_benchmark(
        dataset_name=args.dataset,
        subset=args.subset,
        baselines=baselines,
        output_dir=args.output_dir,
        verbose=args.verbose,
        task_limit=args.task_limit,
        task_count=args.task_count,
        parallel=args.parallel,
        seed=args.seed,
        enable_rag=enable_rag,
        save_state=args.save_state,
        enable_mutation_scoring=None,
        difficulty=args.difficulty,
    )
    # 记录全开链路配置（可复现性）
    summary["full_stack_config"] = _apply_full_stack_env(args.output_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="G8 全开链路 SWE-bench Pro 复测")
    parser.add_argument("--dataset", default="swe_bench_pro", help="数据集名称（默认 swe_bench_pro）")
    parser.add_argument("--data-dir", default=None, help="SWE-bench Pro 数据目录（默认读环境变量）")
    parser.add_argument("--subset", default=None, help="数据子集（默认 None = 全部）")
    parser.add_argument("--baselines", default="aitester", help="基线方法列表（逗号分隔，默认 aitester）")
    parser.add_argument(
        "--output-dir", default=os.path.join(PROJECT_ROOT, "experiments", "results"), help="结果输出目录"
    )
    parser.add_argument("--task-limit", type=int, default=None, help="限制运行任务数量")
    parser.add_argument("--task-count", type=int, default=None, help="合成数据集任务数量（仅 synthetic 生效）")
    parser.add_argument("--parallel", type=int, default=None, help="并行任务数")
    parser.add_argument("--seed", type=int, default=42, help="合成数据集随机种子")
    parser.add_argument("--enable-rag", action="store_true", help="显式开启 RAG")
    parser.add_argument("--no-rag", action="store_true", help="显式关闭 RAG（默认关）")
    parser.add_argument("--save-state", action="store_true", help="把环节级状态落盘到 output_dir/raw/")
    parser.add_argument(
        "--difficulty",
        default="mixed",
        choices=["mixed", "level1", "level2", "level3", "level4"],
        help="合成数据集分层难度",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--skip-data-check", action="store_true", help="跳过 G8 数据前置检查（仅调试用，生产禁用）")
    args = parser.parse_args()

    if not args.skip_data_check and not _check_pro_data_ready(args.data_dir, args.dataset):
        return 1

    _apply_full_stack_env(args.output_dir)
    summary = _run_full_stack_benchmark(args)

    # 写出全开链路汇总（JSON + Markdown）
    os.makedirs(args.output_dir, exist_ok=True)
    ts = summary.get("timestamp", "").replace(":", "-").replace("T", "_").split(".")[0]
    json_path = os.path.join(args.output_dir, f"full_stack_{args.dataset}_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    md_lines = [
        f"# G8 全开链路复测汇总（{args.dataset}）",
        "",
        f"- 数据目录: {args.data_dir or '(环境变量)'}",
        f"- 基线: {args.baselines}",
        f"- 任务数: {summary.get('total_tasks')}",
        f"- 全开配置: {json.dumps(summary.get('full_stack_config', {}), ensure_ascii=False)}",
        "",
        "## 各基线成功率",
        "",
        "| 基线 | 成功率 | 平均覆盖率 | 平均迭代 | 总 token |",
        "|------|--------|------------|----------|----------|",
    ]
    for baseline, bl in summary.get("results", {}).items():
        tm = bl.get("token_metrics", {})
        md_lines.append(
            f"| {baseline} | {bl.get('success_rate')}% | {bl.get('avg_coverage')}% "
            f"| {bl.get('avg_iterations')} | {tm.get('total_tokens')} |"
        )
    md_lines.extend(["", "## 失败类别分布", ""])
    for baseline, bl in summary.get("results", {}).items():
        dist = bl.get("failure_category_distribution", {})
        md_lines.append(f"### {baseline}")
        for category, count in dist.items():
            md_lines.append(f"- {category}: {count}")
        md_lines.append("")
    md_path = os.path.join(args.output_dir, f"full_stack_{args.dataset}_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print("\n[G8] 全开链路复测完成")
    print(f"[G8] 结果 JSON: {json_path}")
    print(f"[G8] 汇总 Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
