# misguided/effective 逐测试三分度量报告（零 LLM 重放）

> **性质**：描述性机制度量（ISSTA'26 操作化），**非**预注册确认性证据；
> 不做显著性推断。所有比率的分母为可分类测试数，不可分类原因单列。
> **生成时间**：2026-10-17T10:33:29+00:00　**body digest**：`c3e2db3745b7376d5469c173a2f0d4252945681a618e4f4d086e914b5b2bad83`
> **工具**：experiments.misguided_metrics v1.0.0　**schema**：`misguided_effective_metric/1`

复算命令：

```bash
python -m experiments.misguided_metrics --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json --artifact experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json --out experiments/results/emse_misguided_20261017 --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2
```

## 1. 输入工件

| 工件 | sha256 | 臂 | 行数 |
|---|---|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` | `plain_llm_df` | 50 |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` | `plain_llm_df_spec` | 50 |

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

| 指标 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| 工件行数 / 分析任务数 | 50 / 50 | 50 / 50 |
| 可分类任务数（ok） | 41 | 41 |
| 结构跳过任务数 | 9 | 9 |
| 总收集测试数（并集，含跳过任务） | 851 | 1353 |
| 可分类测试数（分母） | 793 | 1230 |
| 不可分类测试数 | 58 | 123 |
| AST test_* 定义数（披露） | 654 | 636 |
| `effective` 计数 / 占比 | 347 / 43.76% | 389 / 31.63% |
| `misguided` 计数 / 占比 | 10 / 1.26% | 9 / 0.73% |
| `both_pass` 计数 / 占比 | 419 / 52.84% | 677 / 55.04% |
| `both_fail` 计数 / 占比 | 17 / 2.14% | 155 / 12.60% |

任务级汇总（同一分母披露）：

| 指标 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| 含 effective 测试的任务数 | 37 | 37 |
| 含 misguided 测试的任务数 | 4 | 4 |
| 每任务 misguided 占比（mean/median） | 0.0153 / 0.0000 | 0.0076 / 0.0000 |

### 3.1 主分析集（40 缺陷程序：非 *_test 且 buggy≠fixed；41 口径兼容行见末行）

| 指标 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| 任务行数（主分析集 / 41 口径） | 40 / 41 | 40 / 41 |
| ok 任务数 | 40 | 40 |
| 可分类测试数（分母） | 776 | 1213 |
| effective 占比 | 44.72% | 32.07% |
| misguided 占比 | 1.29% | 0.74% |
| both_pass 占比 | 52.71% | 55.15% |
| both_fail 占比 | 1.29% | 12.04% |

### 3.2 不可分类原因计数

| 原因 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| `timeout` | 56 | 122 |
| `collect_error` | 0 | 0 |
| `import_error` | 0 | 0 |
| `syntax_error` | 0 | 0 |
| `skipped` | 2 | 0 |
| `test_error` | 0 | 1 |
| `missing_side` | 0 | 0 |
| `unknown` | 0 | 0 |

### 3.3 结构跳过原因分布

| 原因 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| `import_error` | 9 | 9 |

## 4. 两臂描述性对比

臂 A = `plain_llm_df`（`experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json`）；臂 B = `plain_llm_df_spec`（`experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json`）。`delta_pp` = 臂 B − 臂 A（百分点）。

| 指标（all_tasks 口径） | 臂 A | 臂 B | delta_pp (B−A) |
|---|---|---|---|
| `effective_share` | 43.76% | 31.63% | -12.1319 |
| `misguided_share` | 1.26% | 0.73% | -0.5293 |
| `both_pass_share` | 52.84% | 55.04% | 2.2034 |
| `both_fail_share` | 2.14% | 12.60% | 10.4578 |
| 可分类测试数 | 793 | 1230 | — |

任务级（all_tasks 口径）：

| 指标 | 臂 A | 臂 B |
|---|---|---|
| 含 effective 测试的任务数 | 37 | 37 |
| 含 misguided 测试的任务数 | 4 | 4 |


主分析集（40 缺陷程序口径，逐测试占比）：

| 指标 | 臂 A | 臂 B | delta_pp (B−A) |
|---|---|---|---|
| `effective_share` | 44.72% | 32.07% | -12.6473 |
| `misguided_share` | 1.29% | 0.74% | -0.5467 |
| `both_pass_share` | 52.71% | 55.15% | 2.4463 |
| `both_fail_share` | 1.29% | 12.04% | 10.7476 |

> 描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据，不含显著性/效应量推断；数值解读必须结合分母披露与交叉校验表。

## 5. 与工件既有字段的交叉校验

| 对账项 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| detection 对账 `artifact_none` | 5 | 6 |
| detection 对账 `both_none` | 9 | 9 |
| detection 对账 `match` | 36 | 35 |

`specificity_gate_verdict` 对账（归档 verdict 与重放 fixed 侧绿/红是否一致）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| `match` | 40 | 37 |
| `not_applicable` | 10 | 13 |

archived `passed` 与重放 fixed 侧绿/红对账（`passed` 为归档字段，非本工具口径）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_spec` |
|---|---|---|
| `passed=False/green` | 31 | 20 |
| `passed=False/none` | 9 | 9 |
| `passed=False/red` | 10 | 21 |

**`plain_llm_df` detection 对账差异（5 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__bitcount` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=30、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=7、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=14、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=5、fixed timeout=5）→ 归档 None 变为可判 0.0 |

**`plain_llm_df_spec` detection 对账差异（6 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__bitcount` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=91、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=8、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=11、fixed timeout=2）→ 归档 None 变为可判 0.0 |
| `quixbugs__to_base` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=1、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=10、fixed timeout=10）→ 归档 None 变为可判 0.0 |

## 6. 结构跳过任务（不静默跳过）

**`plain_llm_df`（9 个）**：

- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

**`plain_llm_df_spec`（9 个）**：

- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

## 7. 逐任务明细

### `plain_llm_df`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | True | 32 | 2 | 0 | 0 | 2 | 0 | 30 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search` | ok | True | 13 | 13 | 5 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 17 | 17 | 12 | 1 | 4 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__depth_first_search` | ok | True | 10 | 10 | 2 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 24 | 24 | 5 | 0 | 19 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 34 | 27 | 5 | 0 | 22 | 0 | 7 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 21 | 21 | 5 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 11 | 11 | 7 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 21 | 21 | 18 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 77 | 77 | 40 | 0 | 37 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 35 | 35 | 11 | 1 | 20 | 3 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 23 | 23 | 4 | 0 | 19 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 18 | 18 | 12 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 13 | 13 | 2 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kth` | ok | True | 24 | 24 | 8 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 32 | 32 | 14 | 0 | 18 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 36 | 36 | 19 | 0 | 17 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 23 | 23 | 3 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 16 | 16 | 3 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 22 | 22 | 4 | 0 | 18 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 22 | 22 | 20 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 10 | 10 | 9 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 21 | 21 | 6 | 0 | 15 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 32 | 32 | 27 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 17 | 17 | 0 | 0 | 10 | 7 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 14 | 14 | 12 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 19 | 19 | 14 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__powerset` | ok | True | 11 | 11 | 5 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 17 | 17 | 2 | 0 | 15 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 10 | 10 | 8 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 23 | 23 | 11 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length` | ok | True | 12 | 12 | 5 | 0 | 6 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 12 | 12 | 4 | 0 | 7 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 8 | 8 | 3 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 15 | 15 | 10 | 0 | 2 | 3 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__sieve` | ok | True | 16 | 16 | 9 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | ok | True | 18 | 2 | 0 | 0 | 2 | 0 | 14 | 2 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__subsequences` | ok | True | 18 | 18 | 9 | 2 | 7 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 26 | 26 | 12 | 0 | 13 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__topological_ordering` | ok | True | 9 | 9 | 2 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 19 | 14 | 0 | 6 | 8 | 0 | 5 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

### `plain_llm_df_spec`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | True | 95 | 4 | 0 | 0 | 4 | 0 | 91 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__breadth_first_search` | ok | True | 15 | 15 | 5 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 23 | 23 | 18 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__depth_first_search` | ok | True | 11 | 11 | 2 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 18 | 18 | 6 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 37 | 29 | 10 | 0 | 19 | 0 | 8 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 29 | 29 | 5 | 0 | 24 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 19 | 19 | 12 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 56 | 56 | 38 | 0 | 13 | 5 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__get_factors` | ok | True | 53 | 53 | 27 | 0 | 26 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 23 | 23 | 2 | 0 | 13 | 8 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 38 | 38 | 2 | 0 | 36 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 41 | 41 | 0 | 0 | 1 | 40 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__knapsack` | ok | True | 23 | 22 | 4 | 2 | 16 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 22 | 22 | 4 | 0 | 18 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 44 | 44 | 9 | 0 | 35 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 70 | 70 | 7 | 0 | 61 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__lis` | ok | True | 21 | 21 | 1 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 34 | 34 | 4 | 0 | 30 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 26 | 26 | 7 | 0 | 19 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 56 | 56 | 51 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 13 | 13 | 10 | 0 | 2 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 82 | 82 | 4 | 3 | 48 | 27 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__next_permutation` | ok | True | 52 | 52 | 39 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 17 | 17 | 0 | 0 | 8 | 9 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 12 | 12 | 6 | 0 | 2 | 4 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__possible_change` | ok | True | 14 | 14 | 5 | 1 | 8 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__powerset` | ok | True | 19 | 19 | 11 | 0 | 7 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__quicksort` | ok | True | 18 | 18 | 6 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 16 | 16 | 14 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 24 | 24 | 5 | 0 | 17 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length` | ok | True | 12 | 12 | 3 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 23 | 23 | 4 | 0 | 16 | 3 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 16 | 16 | 9 | 0 | 4 | 3 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 78 | 78 | 10 | 0 | 21 | 47 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__sieve` | ok | True | 51 | 51 | 3 | 0 | 48 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | ok | True | 16 | 5 | 0 | 0 | 4 | 1 | 11 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__subsequences` | ok | True | 27 | 27 | 6 | 3 | 17 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 55 | 53 | 12 | 0 | 41 | 0 | 1 | 0 | 1 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__topological_ordering` | ok | True | 17 | 17 | 5 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 37 | 27 | 23 | 0 | 4 | 0 | 10 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

## 8. 确定性声明

- 报告 body 不含时间戳/墙钟（这些只进 run_meta）；body digest = `c3e2db3745b7376d5469c173a2f0d4252945681a618e4f4d086e914b5b2bad83`。
- 重复重放次数 `repeat=2`，各次 body digest：`c3e2db3745b7376d5469c173a2f0d4252945681a618e4f4d086e914b5b2bad83`、`c3e2db3745b7376d5469c173a2f0d4252945681a618e4f4d086e914b5b2bad83`；**deterministic=True**。

## 9. 已知限制

- 生成测试之间的全局状态污染与收集顺序照旧存在（仅按版本隔离临时目录）
- 官方金测试 test_cases 不参与四分类，仅用于 detection_rate 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无官方金测试）在平铺口径下无法 import → 结构跳过；项目既有 41 口径（defect_program_ids，仅排除 *_test）中的 node 辅助模块任务 buggy==fixed（无缺陷信号），主分析集取 40 个有缺陷信号任务，41 口径兼容聚合单列可见
- per-test timeout 把挂死测试记为不可分类 timeout（不并入 both_fail），与 A-06 '超时记红' 的判分口径有意不同
- 两臂对比为描述性（非预注册确认性），不做显著性推断；跨批次随机性见交叉校验表
- 生成测试若使用未播种随机源，重复重放可能出现分类漂移（run_meta.determinism 如实披露）

