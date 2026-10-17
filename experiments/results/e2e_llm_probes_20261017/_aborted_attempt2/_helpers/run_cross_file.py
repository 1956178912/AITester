"""item03 包装：run_benchmark(synthetic, difficulty=level3) —— 跨文件双模块任务。"""

from __future__ import annotations

import sys

root, out_dir, reason = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
from experiments.run_benchmark import run_benchmark  # noqa: E402

run_benchmark(
    dataset_name="synthetic",
    baselines=["aitester"],
    output_dir=out_dir,
    task_count=2,
    parallel=1,
    seed=42,
    difficulty="level3",
    deterministic=True,
    dirty_reason=(reason or None),
)
