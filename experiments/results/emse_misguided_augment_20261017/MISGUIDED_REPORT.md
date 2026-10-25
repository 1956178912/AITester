# misguided/effective 逐测试三分度量报告（零 LLM 重放）

> **性质**：描述性机制度量（ISSTA'26 操作化），**非**预注册确认性证据；
> 不做显著性推断。所有比率的分母为可分类测试数，不可分类原因单列。
> **生成时间**：2026-10-24T16:43:52+00:00　**body digest**：`8be49ec78dccde1e441e82a6dc6f5ada5d2987a250d40f640d0d449cb0f4d36a`
> **工具**：experiments.misguided_metrics v1.0.0　**schema**：`misguided_effective_metric/1`

复算命令：

```bash
python -m experiments.misguided_metrics --artifact /Users/wangchenyu/Workspace/AITester/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003250.json --artifact /Users/wangchenyu/Workspace/AITester/experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003844.json --out /Users/wangchenyu/Workspace/AITester/experiments/results/emse_misguided_augment_20261017 --jobs 8
```

## 1. 输入工件

| 工件 | sha256 | 臂 | 行数 |
|---|---|---|---|
| `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003250.json` | `9fc3b1fdf811da30ebb6aadd6139ff9101e353fe9f217b10e04b2b4375fc052e` | `plain_llm_df` | 50 |
| `experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003844.json` | `f60b56d0de33ec93f311feea32cb90fcb50e3a8a7aa07b7d698bf17e9e20c26f` | `plain_llm_df_doc_augment` | 50 |

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
| 总收集测试数（并集，含跳过任务） | 909 | 1051 |
| 可分类测试数（分母） | 810 | 979 |
| 不可分类测试数 | 99 | 72 |
| AST test_* 定义数（披露） | 579 | 637 |
| `effective` 计数 / 占比 | 412 / 50.86% | 536 / 54.75% |
| `misguided` 计数 / 占比 | 6 / 0.74% | 9 / 0.92% |
| `both_pass` 计数 / 占比 | 382 / 47.16% | 424 / 43.31% |
| `both_fail` 计数 / 占比 | 10 / 1.23% | 10 / 1.02% |

任务级汇总（同一分母披露）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| 含 effective 测试的任务数 | 38 | 37 |
| 含 misguided 测试的任务数 | 3 | 3 |
| 每任务 misguided 占比（mean/median） | 0.0106 / 0.0000 | 0.0157 / 0.0000 |

### 3.1 主分析集（40 缺陷程序：非 *_test 且 buggy≠fixed；41 口径兼容行见末行）

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| 任务行数（主分析集 / 41 口径） | 40 / 41 | 40 / 41 |
| ok 任务数 | 38 | 38 |
| 可分类测试数（分母） | 800 | 965 |
| effective 占比 | 51.50% | 55.54% |
| misguided 占比 | 0.75% | 0.93% |
| both_pass 占比 | 46.88% | 43.11% |
| both_fail 占比 | 0.88% | 0.41% |

### 3.2 不可分类原因计数

| 原因 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `timeout` | 99 | 72 |
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

臂：`plain_llm_df`（`experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003250.json`）；`plain_llm_df_doc_augment`（`experiments/results/emse_docstring_augment_20261017/benchmark_quixbugs_20261025_003844.json`）

**plain_llm_df → plain_llm_df_doc_augment**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc_augment` | delta_pp |
|---|---|---|---|
| `effective_share` | 51.50% | 55.54% | 4.0440 |
| `misguided_share` | 0.75% | 0.93% | 0.1826 |
| `both_pass_share` | 46.88% | 43.11% | -3.7662 |
| `both_fail_share` | 0.88% | 0.41% | -0.4605 |
| 可分类测试数 | 810 | 979 | — |
| 含 effective 测试的任务数 | 38 | 37 | — |
| 含 misguided 测试的任务数 | 3 | 3 | — |

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
| `match` | 39 | 39 |
| `not_applicable` | 11 | 11 |

archived `passed` 与重放 fixed 侧绿/红对账（`passed` 为归档字段，非本工具口径）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_doc_augment` |
|---|---|---|
| `passed=False/green` | 34 | 33 |
| `passed=False/none` | 15 | 16 |
| `passed=False/red` | 1 | 1 |

**`plain_llm_df` detection 对账差异（3 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=6、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=3、fixed timeout=3）→ 归档 None 变为可判 0.0 |

**`plain_llm_df_doc_augment` detection 对账差异（4 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=4、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__longest_common_subsequence` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=2、fixed timeout=2）→ 归档 None 变为可判 0.0 |
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
| `quixbugs__bitcount` | structural_skip (file_timeout) | True | 71 | 0 | 0 | 0 | 0 | 0 | 71 | 0 | 0 | — | — | specific_red | match |
| `quixbugs__breadth_first_search` | ok | True | 15 | 15 | 7 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 16 | 16 | 14 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search` | ok | True | 10 | 10 | 2 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 11 | 11 | 3 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 27 | 21 | 4 | 0 | 17 | 0 | 6 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 21 | 21 | 4 | 0 | 17 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 14 | 14 | 10 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 22 | 22 | 20 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 81 | 81 | 43 | 0 | 38 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 20 | 20 | 12 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 25 | 25 | 5 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 18 | 18 | 12 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 17 | 17 | 4 | 1 | 12 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 17 | 17 | 8 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 37 | 37 | 15 | 0 | 22 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 26 | 26 | 13 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 14 | 14 | 3 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 25 | 25 | 4 | 0 | 21 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 21 | 21 | 5 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 23 | 23 | 21 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 11 | 11 | 10 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 16 | 16 | 5 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 21 | 21 | 16 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 10 | 10 | 0 | 0 | 7 | 3 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 39 | 39 | 30 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 16 | 16 | 13 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__powerset` | ok | True | 24 | 24 | 10 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 16 | 16 | 4 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 13 | 13 | 10 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 16 | 16 | 7 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length` | ok | True | 11 | 11 | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 14 | 14 | 5 | 0 | 8 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 9 | 9 | 5 | 0 | 2 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 28 | 28 | 24 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sieve` | ok | True | 18 | 18 | 13 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | structural_skip (file_timeout) | True | 19 | 0 | 0 | 0 | 0 | 0 | 19 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__subsequences` | ok | True | 16 | 16 | 4 | 2 | 6 | 4 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 56 | 56 | 30 | 0 | 26 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering` | ok | True | 9 | 9 | 4 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 16 | 13 | 9 | 3 | 1 | 0 | 3 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

### `plain_llm_df_doc_augment`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | structural_skip (file_timeout) | True | 40 | 0 | 0 | 0 | 0 | 0 | 40 | 0 | 0 | — | — | specific_red | match |
| `quixbugs__breadth_first_search` | ok | True | 14 | 14 | 6 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 22 | 22 | 19 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search` | ok | True | 13 | 13 | 2 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 20 | 20 | 4 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 27 | 23 | 4 | 0 | 19 | 0 | 4 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 43 | 43 | 16 | 0 | 27 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 18 | 18 | 12 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 80 | 80 | 78 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 103 | 103 | 52 | 0 | 51 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 31 | 31 | 23 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 29 | 29 | 5 | 0 | 24 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 17 | 17 | 12 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 16 | 16 | 6 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kth` | ok | True | 16 | 16 | 7 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 31 | 31 | 14 | 0 | 17 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 35 | 35 | 12 | 0 | 23 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 17 | 17 | 4 | 0 | 12 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 18 | 16 | 2 | 0 | 14 | 0 | 2 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__max_sublist_sum` | ok | True | 27 | 27 | 5 | 0 | 22 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 33 | 33 | 31 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 12 | 12 | 10 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 16 | 16 | 5 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 18 | 18 | 14 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 14 | 14 | 0 | 0 | 8 | 6 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 38 | 38 | 31 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 24 | 24 | 20 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__powerset` | ok | True | 31 | 31 | 14 | 0 | 17 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 16 | 16 | 6 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 10 | 10 | 9 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 19 | 19 | 9 | 2 | 8 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length` | ok | True | 10 | 10 | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 12 | 12 | 7 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 10 | 10 | 7 | 0 | 1 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 25 | 25 | 22 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sieve` | ok | True | 18 | 18 | 13 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | structural_skip (file_timeout) | True | 24 | 0 | 0 | 0 | 0 | 0 | 24 | 0 | 0 | — | — | specific_red | match |
| `quixbugs__subsequences` | ok | True | 13 | 13 | 9 | 1 | 3 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 64 | 64 | 35 | 0 | 29 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering` | ok | True | 11 | 11 | 6 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 16 | 14 | 0 | 6 | 8 | 0 | 2 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

## 8. 确定性声明

- 报告 body 不含时间戳/墙钟（这些只进 run_meta）；body digest = `8be49ec78dccde1e441e82a6dc6f5ada5d2987a250d40f640d0d449cb0f4d36a`。
- 重复重放次数 `repeat=1`，各次 body digest：`8be49ec78dccde1e441e82a6dc6f5ada5d2987a250d40f640d0d449cb0f4d36a`；**deterministic=True**。

## 9. 已知限制

- 生成测试之间的全局状态污染与收集顺序照旧存在（仅按版本隔离临时目录）
- 官方金测试 test_cases 不参与四分类，仅用于 detection_rate 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无官方金测试）在平铺口径下无法 import → 结构跳过；项目既有 41 口径（defect_program_ids，仅排除 *_test）中的 node 辅助模块任务 buggy==fixed（无缺陷信号），主分析集取 40 个有缺陷信号任务，41 口径兼容聚合单列可见
- per-test timeout 把挂死测试记为不可分类 timeout（不并入 both_fail），与 A-06 '超时记红' 的判分口径有意不同
- 两臂对比为描述性（非预注册确认性），不做显著性推断；跨批次随机性见交叉校验表
- 生成测试若使用未播种随机源，重复重放可能出现分类漂移（run_meta.determinism 如实披露）
- BC（2026-10-21）：任务级重放判绿（replay_detection / replay_fixed_green / verdict 对账）要求 rc==0 且含有效通过（≥1 个真实 passed，共享谓词 _suite_has_effective_pass 同口径）——全 skip/xfail/deselect 的套件 rc==0 但无断言执行，不判绿（None / not_applicable）；归档侧若按旧口径记 1.0，对账落 replay_none 并在 detection_disagreement_reason 说明口径修正

