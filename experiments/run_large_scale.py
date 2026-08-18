"""
大规模实验脚本：运行 100 个合成任务，收集完整实验数据用于论文。

使用方式：
    python experiments/run_large_scale.py --task-count 100 --baselines aitester,plain_llm,single_agent
    python experiments/run_large_scale.py --task-count 100 --ablations planner,debugger,rag
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import click  # noqa: E402

from experiments.run_benchmark import run_benchmark  # noqa: E402
from src.synthetic_dataset import SyntheticDataset  # noqa: E402

logger = logging.getLogger(__name__)


@click.command()
@click.option("--task-count", "-c", default=100, type=int, help="合成数据集任务数量（默认 100）")
@click.option("--baselines", "-b", default="aitester,plain_llm,single_agent", help="基线方法列表（逗号分隔）")
@click.option("--seed", "-s", default=42, type=int, help="随机种子（默认 42）")
@click.option("--output-dir", "-o", default="experiments/results/large_scale", help="结果输出目录")
@click.option("--parallel", "-p", default=0, type=int, help="并行任务数（0=顺序执行）")
@click.option("--verbose", "-v", is_flag=True, help="详细日志")
def cli(task_count: int, baselines: str, seed: int, output_dir: str, parallel: int, verbose: bool):
    """大规模合成实验：生成 task_count 个任务并运行所有基线对比。"""
    bl_list = [b.strip() for b in baselines.split(",") if b.strip()]

    # 生成合成数据集
    logger.info("生成合成数据集: %d 个任务, seed=%d", task_count, seed)
    dataset = SyntheticDataset(task_count=task_count, seed=seed)
    tasks = dataset.tasks

    # 运行完整实验
    logger.info("开始大规模实验: %d 任务 x %d 基线", len(tasks), len(bl_list))
    start_time = time.time()

    summary = run_benchmark(
        dataset_name="synthetic",
        subset=None,
        baselines=bl_list,
        output_dir=output_dir,
        verbose=verbose,
        task_limit=None,
        task_count=task_count,
        parallel=parallel,
    )

    elapsed = time.time() - start_time
    logger.info("实验完成，总耗时: %.1f 秒 (%.1f 分钟)", elapsed, elapsed / 60)

    # 保存实验元数据
    meta = {
        "experiment_type": "large_scale_synthetic",
        "timestamp": datetime.now().isoformat(),
        "task_count": task_count,
        "seed": seed,
        "baselines": bl_list,
        "elapsed_seconds": round(elapsed, 2),
        "results_summary": {
            bl: {
                "success_rate": summary["results"][bl]["success_rate"],
                "avg_coverage": summary["results"][bl]["avg_coverage"],
                "avg_iterations": summary["results"][bl]["avg_iterations"],
                "total_time": summary["results"][bl]["total_time"],
            }
            for bl in bl_list
            if bl in summary.get("results", {})
        },
    }
    meta_file = Path(output_dir) / "experiment_meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info("实验元数据已保存: %s", meta_file)

    print("\n" + "=" * 70)
    print("大规模实验完成")
    print("=" * 70)
    for bl in bl_list:
        if bl in summary.get("results", {}):
            r = summary["results"][bl]
            print(f"  [{bl}] 成功率: {r['success_rate']}%, 覆盖率: {r['avg_coverage']}%, 耗时: {r['total_time']:.0f}s")
    print(f"总耗时: {elapsed:.1f}s")
    print(f"结果目录: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    cli()
