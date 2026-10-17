# misguided/effective 逐测试三分度量报告（零 LLM 重放）

> **性质**：描述性机制度量（ISSTA'26 操作化），**非**预注册确认性证据；
> 不做显著性推断。所有比率的分母为可分类测试数，不可分类原因单列。
> **生成时间**：2026-10-17T14:25:11+00:00　**body digest**：`0df41d2400d3eee31be46e1c6788b4ec00eafafdd0991f1bd22f078933529127`
> **工具**：experiments.misguided_metrics v1.0.0　**schema**：`misguided_effective_metric/1`

复算命令：

```bash
python -m experiments.misguided_metrics --artifact /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json --artifact /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json --out /Users/wangchenyu/Workspace/AITester-m-batch-fae8f45/experiments/results/emse_misguided_augment_20261017 --jobs 8
```

## 1. 输入工件

| 工件 | sha256 | 臂 | 行数 |
|---|---|---|---|
| `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json` | `80f8a54f097b65b53b57621ffbb5826fdb7784c436752e1304fc328919a09c2b` | `plain_llm_df` | 50 |
| `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json` | `b6303604bfb640ec20083b7384525e255461ba0f52e91a7439281f6d58128be7` | `plain_llm_df_doc_augment` | 50 |

## 2. 口径定义

| 类别 | 定义 |
|---|---|
| `effective` | buggy 失败 ∧ fixed 通过（真正区分缺陷版与修复版） |
| `misguided` | buggy 通过 ∧ fixed 失败（把缺陷行为断言成期望行为） |
| `both_pass` | 两侧都通过（零检出信号的刻画性测试） |
| `both_fail` | 两侧都失败（在正确代码上即失败 → 测试自身无效/恒红） |

可分类测试 = 两侧均有 pass/fail 结果；以下原因**单列**、不进分母：
`timeout`、`collect_error`、`import_error`、`syntax_error`、`skipped`、`test_error`、`missing_side`、`unknown`。

> 分母纪律：所有比率的分母 = 可分类测试数（两侧均有 pass/fail 结果的测试）；超时/收集失败/import 失败/语法错误/skipped/test_error/missing_side/unknown 单列，不进分母；任务级结构跳过单独计数，不混入任务级可判定集合

## 3. 臂级汇总

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| 工件行数 / 分析任务数 | 50 / 50 | 50 / 50 |
| 可分类任务数（ok） | 39 | 39 |
| 结构跳过任务数 | 11 | 11 |
| 总收集测试数（并集，含跳过任务） | 946 | 1333 |
| 可分类测试数（分母） | 849 | 970 |
| 不可分类测试数 | 97 | 363 |
| AST test_* 定义数（披露） | 611 | 649 |
| `effective` 计数 / 占比 | 400 / 47.11% | 543 / 55.98% |
| `misguided` 计数 / 占比 | 11 / 1.30% | 3 / 0.31% |
| `both_pass` 计数 / 占比 | 424 / 49.94% | 413 / 42.58% |
| `both_fail` 计数 / 占比 | 14 / 1.65% | 11 / 1.13% |

任务级汇总（同一分母披露）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| 含 effective 测试的任务数 | 38 | 38 |
| 含 misguided 测试的任务数 | 4 | 3 |
| 每任务 misguided 占比（mean/median） | 0.0185 / 0.0000 | 0.0052 / 0.0000 |

### 3.1 主分析集（40 缺陷程序：非 *_test 且 buggy≠fixed；41 口径兼容行见末行）

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| 任务行数（主分析集 / 41 口径） | 40 / 41 | 40 / 41 |
| ok 任务数 | 38 | 38 |
| 可分类测试数（分母） | 836 | 954 |
| effective 占比 | 47.85% | 56.92% |
| misguided 占比 | 1.32% | 0.31% |
| both_pass 占比 | 50.00% | 41.93% |
| both_fail 占比 | 0.84% | 0.84% |

### 3.2 不可分类原因计数

| 原因 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `timeout` | 97 | 363 |
| `collect_error` | 0 | 0 |
| `import_error` | 0 | 0 |
| `syntax_error` | 0 | 0 |
| `skipped` | 0 | 0 |
| `test_error` | 0 | 0 |
| `missing_side` | 0 | 0 |
| `unknown` | 0 | 0 |

### 3.3 结构跳过原因分布

| 原因 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `file_timeout` | 2 | 2 |
| `import_error` | 9 | 9 |

## 4. 臂间描述性对比

臂：`plain_llm_df`（`experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221948.json`）；`plain_llm_df_doc_augment`（`experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261017_221735.json`）

**plain_llm_df → plain_llm_df_doc_augment**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` | delta_pp |
|---|---|---|---|
| `effective_share` | 47.85% | 56.92% | 9.0713 |
| `misguided_share` | 1.32% | 0.31% | -1.0013 |
| `both_pass_share` | 50.00% | 41.93% | -8.0713 |
| `both_fail_share` | 0.84% | 0.84% | 0.0013 |
| 可分类测试数 | 849 | 970 | — |
| 含 effective 测试的任务数 | 38 | 38 | — |
| 含 misguided 测试的任务数 | 4 | 3 | — |

> 描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据，不含显著性/效应量推断；数值解读必须结合分母披露与交叉校验表。

## 5. 与工件既有字段的交叉校验

| 对账项 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| detection 对账 `artifact_none` | 3 | 4 |
| detection 对账 `both_none` | 11 | 11 |
| detection 对账 `match` | 36 | 35 |

`specificity_gate_verdict` 对账（归档 verdict 与重放 fixed 侧绿/红是否一致）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `match` | 39 | 38 |
| `not_applicable` | 11 | 12 |

archived `passed` 与重放 fixed 侧绿/红对账（`passed` 为归档字段，非本工具口径）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `passed=False/green` | 31 | 31 |
| `passed=False/none` | 9 | 9 |
| `passed=False/red` | 10 | 10 |

**`plain_llm_df` detection 对账差异（3 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=4、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=1、fixed timeout=1）→ 归档 None 变为可判 0.0 |

**`plain_llm_df_doc_augment` detection 对账差异（4 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=5、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__longest_common_subsequence` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=1、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=2、fixed timeout=2）→ 归档 None 变为可判 0.0 |

## 6. 结构跳过任务（不静默跳过）

**`plain_llm_df`（11 个）**：

- `quixbugs__bitcount` [defect_program] `file_timeout`: buggy 侧整文件执行超时（整文件墙钟超时，逐测试结果不可判（保守全部记 timeout））
- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__sqrt` [defect_program] `file_timeout`: buggy 侧整文件执行超时（整文件墙钟超时，逐测试结果不可判（保守全部记 timeout））
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

**`plain_llm_df_doc_augment`（11 个）**：

- `quixbugs__bitcount` [defect_program] `file_timeout`: buggy 侧整文件执行超时（整文件墙钟超时，逐测试结果不可判（保守全部记 timeout））
- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__sqrt` [defect_program] `file_timeout`: buggy 侧整文件执行超时（整文件墙钟超时，逐测试结果不可判（保守全部记 timeout））
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

## 7. 逐任务明细

### `plain_llm_df`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | structural_skip (file_timeout) | True | 74 | 0 | 0 | 0 | 0 | 0 | 74 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__breadth_first_search` | ok | True | 12 | 12 | 4 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 16 | 16 | 13 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search` | ok | True | 10 | 10 | 2 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 19 | 19 | 5 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 31 | 27 | 5 | 0 | 22 | 0 | 4 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 13 | 13 | 3 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 14 | 14 | 9 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 24 | 24 | 20 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 70 | 70 | 33 | 0 | 37 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 17 | 17 | 5 | 0 | 11 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 43 | 43 | 8 | 0 | 35 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 18 | 18 | 13 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 17 | 17 | 3 | 1 | 13 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 15 | 15 | 7 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 35 | 35 | 13 | 0 | 22 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 19 | 19 | 11 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 14 | 14 | 3 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 25 | 25 | 4 | 0 | 21 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 20 | 20 | 5 | 0 | 15 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 22 | 22 | 20 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 17 | 17 | 16 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 27 | 27 | 8 | 0 | 19 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 16 | 16 | 10 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 13 | 13 | 0 | 0 | 6 | 7 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 49 | 49 | 39 | 0 | 8 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__possible_change` | ok | True | 29 | 29 | 22 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__powerset` | ok | True | 17 | 17 | 10 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 21 | 21 | 4 | 0 | 17 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 9 | 9 | 8 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 16 | 16 | 2 | 3 | 11 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length` | ok | True | 11 | 11 | 3 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 16 | 16 | 6 | 0 | 9 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 9 | 9 | 6 | 0 | 2 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 29 | 29 | 24 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sieve` | ok | True | 16 | 16 | 9 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | structural_skip (file_timeout) | True | 18 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 0 | — | — | specific_red | match |
| `quixbugs__subsequences` | ok | True | 17 | 17 | 7 | 2 | 8 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 63 | 63 | 31 | 0 | 32 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering` | ok | True | 10 | 10 | 4 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 15 | 14 | 5 | 5 | 2 | 2 | 1 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

### `plain_llm_df_doc_augment`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | structural_skip (file_timeout) | True | 335 | 0 | 0 | 0 | 0 | 0 | 335 | 0 | 0 | — | — | specific_red | match |
| `quixbugs__breadth_first_search` | ok | True | 11 | 11 | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 26 | 26 | 21 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search` | ok | True | 12 | 12 | 1 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 10 | 10 | 2 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 37 | 32 | 7 | 0 | 25 | 0 | 5 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 23 | 23 | 5 | 0 | 18 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 13 | 13 | 10 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 46 | 46 | 42 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 106 | 106 | 67 | 0 | 39 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 51 | 51 | 39 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 26 | 26 | 6 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 27 | 27 | 21 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 15 | 15 | 5 | 0 | 9 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 21 | 21 | 7 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 23 | 23 | 12 | 1 | 9 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__levenshtein` | ok | True | 26 | 26 | 14 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 19 | 19 | 3 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 21 | 20 | 2 | 0 | 18 | 0 | 1 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__max_sublist_sum` | ok | True | 20 | 20 | 5 | 0 | 14 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__mergesort` | ok | True | 22 | 22 | 20 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 12 | 12 | 10 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 12 | 12 | 5 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 24 | 24 | 23 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 16 | 16 | 0 | 0 | 13 | 3 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 45 | 45 | 37 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 38 | 38 | 33 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__powerset` | ok | True | 25 | 25 | 11 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 17 | 17 | 3 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 11 | 11 | 9 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 19 | 19 | 11 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length` | ok | True | 7 | 7 | 3 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 14 | 14 | 8 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 12 | 12 | 10 | 0 | 1 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 22 | 22 | 19 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sieve` | ok | True | 61 | 61 | 26 | 0 | 35 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | structural_skip (file_timeout) | True | 20 | 0 | 0 | 0 | 0 | 0 | 20 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__subsequences` | ok | True | 12 | 12 | 6 | 1 | 5 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 48 | 48 | 23 | 0 | 25 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering` | ok | True | 13 | 13 | 6 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 15 | 13 | 7 | 1 | 2 | 3 | 2 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

## 8. 确定性声明

- 报告 body 不含时间戳/墙钟（这些只进 run_meta）；body digest = `0df41d2400d3eee31be46e1c6788b4ec00eafafdd0991f1bd22f078933529127`。
- 重复重放次数 `repeat=1`，各次 body digest：`0df41d2400d3eee31be46e1c6788b4ec00eafafdd0991f1bd22f078933529127`；**deterministic=True**。

## 9. 已知限制

- 生成测试之间的全局状态污染与收集顺序照旧存在（仅按版本隔离临时目录）
- 官方金测试 test_cases 不参与四分类，仅用于 detection_rate 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无官方金测试）在平铺口径下无法 import → 结构跳过；项目既有 41 口径（defect_program_ids，仅排除 *_test）中的 node 辅助模块任务 buggy==fixed（无缺陷信号），主分析集取 40 个有缺陷信号任务，41 口径兼容聚合单列可见
- per-test timeout 把挂死测试记为不可分类 timeout（不并入 both_fail），与 A-06 '超时记红' 的判分口径有意不同
- 两臂对比为描述性（非预注册确认性），不做显著性推断；跨批次随机性见交叉校验表
- 生成测试若使用未播种随机源，重复重放可能出现分类漂移（run_meta.determinism 如实披露）

