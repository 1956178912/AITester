# M-4 机制重放：misguided/effective 逐测试度量（零 LLM 重放）

> 性质：M-1 augment 臂的机制侧指标工件（ISSTA'26 逐测试四分类重放），**不参与主判定**。
> 工具：`experiments/misguided_metrics.py`（零 LLM/零网络，只跑本地 pytest 子进程）。
> 本 README 的计数/占比由重放报告的 `report.arms[*].aggregate` 直出，不手写。

## 输入工件

| 臂 | 工件 | sha256（前 16） |
|---|---|---|
| `plain_llm_df` | `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003250.json` | `9fc3b1fdf811da30…` |
| `plain_llm_df_doc_augment` | `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003844.json` | `f60b56d0de33ec93…` |

## 逐臂汇总（all_tasks 口径）

| 臂 | 可分析任务 | 可分类测试 | effective | misguided | both_pass | both_fail | effective 占比 | misguided 占比 |
|---|---|---|---|---|---|---|---|---|
| `plain_llm_df` | 39/50 | 810 | 412 | 6 | 382 | 10 | 0.508642 | 0.007407 |
| `plain_llm_df_doc_augment` | 39/50 | 979 | 536 | 9 | 424 | 10 | 0.547497 | 0.009193 |

## 命令

```bash
['python', '-m', 'experiments.misguided_metrics', '--artifact', '/Users/wangchenyu/Workspace/AITester/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003250.json', '--artifact', '/Users/wangchenyu/Workspace/AITester/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003844.json', '--out', '/Users/wangchenyu/Workspace/AITester/experiments/results/emse_misguided_augment_20261017', '--jobs', '8']
```

> 限制：逐测试分类为机制侧描述性信号，不替代 detection 主判定；分母（可分类测试数）与
> 不可分类原因（timeout/collect_error 等）见 MISGUIDED_REPORT.json 的 `aggregate`/`tasks`。

