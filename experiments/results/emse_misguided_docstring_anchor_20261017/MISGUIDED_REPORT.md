# misguided/effective 逐测试三分度量报告（零 LLM 重放）

> **性质**：描述性机制度量（ISSTA'26 操作化），**非**预注册确认性证据；
> 不做显著性推断。所有比率的分母为可分类测试数，不可分类原因单列。
> **生成时间**：2026-10-17T12:42:04+00:00　**body digest**：`678463c84c4d9b8ac79d4ecd9a627ec20b54046bfd364b4c5bff91397ee10625`
> **工具**：experiments.misguided_metrics v1.0.0　**schema**：`misguided_effective_metric/1`

复算命令：

```bash
python -m experiments.misguided_metrics --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json --artifact experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json --out experiments/results/emse_misguided_docstring_anchor_20261017 --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 2
```

## 1. 输入工件

| 工件 | sha256 | 臂 | 行数 |
|---|---|---|---|
| `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json` | `9405176136db2c2e4e7885ca4e6a7116d1647893c31ddd0b8e76b512f1239672` | `plain_llm_df` | 50 |
| `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json` | `3e2a69896d308d389bdd35ed5ce38ae532b9accf89109b297391c265696f78b2` | `plain_llm_df_doc` | 50 |
| `experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json` | `746090a277cc6a91fa12151aa1a01f4702efc5e4df1289ceb1afc18bf7e842b2` | `plain_llm_df_doc_union` | 50 |

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

| 指标 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| 工件行数 / 分析任务数 | 50 / 50 | 50 / 50 | 50 / 50 |
| 可分类任务数（ok） | 41 | 41 | 40 |
| 结构跳过任务数 | 9 | 9 | 10 |
| 总收集测试数（并集，含跳过任务） | 845 | 1175 | 1421 |
| 可分类测试数（分母） | 777 | 1034 | 1276 |
| 不可分类测试数 | 68 | 141 | 145 |
| AST test_* 定义数（披露） | 582 | 659 | 600 |
| `effective` 计数 / 占比 | 379 / 48.78% | 406 / 39.27% | 519 / 40.67% |
| `misguided` 计数 / 占比 | 9 / 1.16% | 2 / 0.19% | 7 / 0.55% |
| `both_pass` 计数 / 占比 | 369 / 47.49% | 515 / 49.81% | 705 / 55.25% |
| `both_fail` 计数 / 占比 | 20 / 2.57% | 111 / 10.73% | 45 / 3.53% |

任务级汇总（同一分母披露）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| 含 effective 测试的任务数 | 37 | 35 | 37 |
| 含 misguided 测试的任务数 | 2 | 2 | 4 |
| 每任务 misguided 占比（mean/median） | 0.0119 / 0.0000 | 0.0018 / 0.0000 | 0.0056 / 0.0000 |

### 3.1 主分析集（40 缺陷程序：非 *_test 且 buggy≠fixed；41 口径兼容行见末行）

| 指标 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| 任务行数（主分析集 / 41 口径） | 40 / 41 | 40 / 41 | 39 / 41 |
| ok 任务数 | 40 | 40 | 39 |
| 可分类测试数（分母） | 764 | 1007 | 1264 |
| effective 占比 | 49.61% | 40.32% | 41.06% |
| misguided 占比 | 1.18% | 0.20% | 0.55% |
| both_pass 占比 | 47.51% | 50.84% | 55.30% |
| both_fail 占比 | 1.70% | 8.64% | 3.09% |

### 3.2 不可分类原因计数

| 原因 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| `timeout` | 67 | 141 | 145 |
| `collect_error` | 0 | 0 | 0 |
| `import_error` | 0 | 0 | 0 |
| `syntax_error` | 0 | 0 | 0 |
| `skipped` | 1 | 0 | 0 |
| `test_error` | 0 | 0 | 0 |
| `missing_side` | 0 | 0 | 0 |
| `unknown` | 0 | 0 | 0 |

### 3.3 结构跳过原因分布

| 原因 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| `generated_test_syntax_error` | 0 | 0 | 1 |
| `import_error` | 9 | 9 | 9 |

## 4. 臂间描述性对比

臂：`plain_llm_df`（`experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_194444.json`）；`plain_llm_df_doc`（`experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_193626.json`）；`plain_llm_df_doc_union`（`experiments/results/emse_docstring_anchor_20261017/benchmark_quixbugs_20261017_201928.json`）

**plain_llm_df → plain_llm_df_doc**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc` | delta_pp |
|---|---|---|---|
| `effective_share` | 49.61% | 40.32% | -9.2895 |
| `misguided_share` | 1.18% | 0.20% | -0.9794 |
| `both_pass_share` | 47.51% | 50.84% | 3.3310 |
| `both_fail_share` | 1.70% | 8.64% | 6.9379 |
| 可分类测试数 | 777 | 1034 | — |
| 含 effective 测试的任务数 | 37 | 35 | — |
| 含 misguided 测试的任务数 | 2 | 2 | — |

**plain_llm_df → plain_llm_df_doc_union**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：

| 指标 | `plain_llm_df` | `plain_llm_df_doc_union` | delta_pp |
|---|---|---|---|
| `effective_share` | 49.61% | 41.06% | -8.5472 |
| `misguided_share` | 1.18% | 0.55% | -0.6242 |
| `both_pass_share` | 47.51% | 55.30% | 7.7875 |
| `both_fail_share` | 1.70% | 3.09% | 1.3838 |
| 可分类测试数 | 777 | 1276 | — |
| 含 effective 测试的任务数 | 37 | 37 | — |
| 含 misguided 测试的任务数 | 2 | 4 | — |

**plain_llm_df_doc → plain_llm_df_doc_union**（`delta_pp` = B − A，百分点；缺陷程序主分析集口径，行数见 §3.1）：

| 指标 | `plain_llm_df_doc` | `plain_llm_df_doc_union` | delta_pp |
|---|---|---|---|
| `effective_share` | 40.32% | 41.06% | 0.7423 |
| `misguided_share` | 0.20% | 0.55% | 0.3552 |
| `both_pass_share` | 50.84% | 55.30% | 4.4565 |
| `both_fail_share` | 8.64% | 3.09% | -5.5541 |
| 可分类测试数 | 1034 | 1276 | — |
| 含 effective 测试的任务数 | 35 | 37 | — |
| 含 misguided 测试的任务数 | 2 | 4 | — |

> 描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据，不含显著性/效应量推断；数值解读必须结合分母披露与交叉校验表。

## 5. 与工件既有字段的交叉校验

| 对账项 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| detection 对账 `artifact_none` | 5 | 6 | 7 |
| detection 对账 `both_none` | 9 | 9 | 9 |
| detection 对账 `match` | 36 | 35 | 33 |
| detection 对账 `replay_none` | 0 | 0 | 1 |

`specificity_gate_verdict` 对账（归档 verdict 与重放 fixed 侧绿/红是否一致）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| `match` | 39 | 37 | 35 |
| `not_applicable` | 11 | 13 | 15 |

archived `passed` 与重放 fixed 侧绿/红对账（`passed` 为归档字段，非本工具口径）：

| 对账标签 | `plain_llm_df` | `plain_llm_df_doc` | `plain_llm_df_doc_union` |
|---|---|---|---|
| `passed=False/green` | 33 | 22 | 22 |
| `passed=False/none` | 9 | 9 | 10 |
| `passed=False/red` | 8 | 19 | 18 |

**`plain_llm_df` detection 对账差异（5 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__bitcount` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=40、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=7、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=18、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=2、fixed timeout=2）→ 归档 None 变为可判 0.0 |

**`plain_llm_df_doc` detection 对账差异（6 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__bitcount` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=102、fixed timeout=2）→ 归档 None 变为可判 0.0 |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=8、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=20、fixed timeout=5）→ 归档 None 变为可判 0.0 |
| `quixbugs__to_base` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=1、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__wrap` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=8、fixed timeout=8）→ 归档 None 变为可判 0.0 |

**`plain_llm_df_doc_union` detection 对账差异（8 条）**：

| task_id | 归档 | 重放 | 重放(strict) | 归因 |
|---|---|---|---|---|
| `quixbugs__bitcount` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=101、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=9、fixed timeout=0）→ 归档 None 变为可判 1.0 |
| `quixbugs__longest_common_subsequence` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=1、fixed timeout=1）→ 归档 None 变为可判 0.0 |
| `quixbugs__node` | — | 0.0000 | 0.0000 | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__powerset` | 0.0000 | — | — | 结构跳过（generated_test_syntax_error）→ 无法重放；归档 detection=0.0 |
| `quixbugs__sqrt` | — | 0.0000 | — | per-test 超时改写整文件超时判定（buggy timeout=21、fixed timeout=4）→ 归档 None 变为可判 0.0 |
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

**`plain_llm_df_doc`（9 个）**：

- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

**`plain_llm_df_doc_union`（10 个）**：

- `quixbugs__breadth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__depth_first_search_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__detect_cycle_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__minimum_spanning_tree_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__powerset` [defect_program] `generated_test_syntax_error`: generated_test 无法通过 ast.parse（语法错误）
- `quixbugs__reverse_linked_list_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_length_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_path_lengths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__shortest_paths_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package
- `quixbugs__topological_ordering_test` [driver_or_unknown] `import_error`: buggy 侧收集失败: E   ImportError: attempted relative import with no known parent package

## 7. 逐任务明细

### `plain_llm_df`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | True | 43 | 3 | 0 | 0 | 3 | 0 | 40 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__breadth_first_search` | ok | True | 10 | 10 | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 18 | 18 | 13 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__depth_first_search` | ok | True | 10 | 10 | 2 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 12 | 12 | 2 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 33 | 26 | 5 | 0 | 21 | 0 | 7 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 21 | 21 | 5 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 11 | 11 | 7 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 18 | 18 | 16 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 72 | 72 | 33 | 0 | 39 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 18 | 18 | 7 | 0 | 4 | 7 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 37 | 37 | 13 | 0 | 24 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 19 | 19 | 13 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 20 | 20 | 5 | 0 | 15 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kth` | ok | True | 15 | 15 | 9 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 24 | 24 | 13 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 19 | 19 | 12 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 14 | 14 | 3 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 22 | 22 | 2 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 15 | 15 | 2 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 21 | 21 | 19 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 15 | 15 | 14 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 17 | 17 | 3 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__next_permutation` | ok | True | 17 | 17 | 14 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 13 | 13 | 0 | 0 | 6 | 7 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 63 | 63 | 53 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 16 | 16 | 11 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__powerset` | ok | True | 15 | 15 | 9 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 14 | 14 | 3 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 14 | 14 | 11 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 22 | 22 | 10 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length` | ok | True | 11 | 11 | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 12 | 12 | 5 | 0 | 6 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 10 | 10 | 6 | 0 | 3 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 21 | 21 | 17 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sieve` | ok | True | 15 | 15 | 9 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | ok | True | 24 | 5 | 0 | 0 | 5 | 0 | 18 | 1 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__subsequences` | ok | True | 17 | 17 | 7 | 2 | 8 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 27 | 27 | 15 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering` | ok | True | 9 | 9 | 2 | 0 | 7 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 21 | 19 | 0 | 7 | 9 | 3 | 2 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

### `plain_llm_df_doc`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | True | 106 | 4 | 0 | 0 | 4 | 0 | 102 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__breadth_first_search` | ok | True | 18 | 18 | 5 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 15 | 15 | 14 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search` | ok | True | 18 | 18 | 2 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 21 | 21 | 1 | 0 | 0 | 20 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 37 | 29 | 4 | 0 | 25 | 0 | 8 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 37 | 37 | 8 | 0 | 29 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 14 | 14 | 10 | 0 | 4 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 23 | 23 | 19 | 1 | 3 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__get_factors` | ok | True | 66 | 66 | 37 | 0 | 28 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__hanoi` | ok | True | 61 | 61 | 31 | 0 | 21 | 9 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 30 | 30 | 5 | 0 | 25 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 25 | 25 | 17 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 17 | 17 | 4 | 0 | 12 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 22 | 22 | 11 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 37 | 37 | 7 | 0 | 30 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__levenshtein` | ok | True | 50 | 50 | 14 | 0 | 36 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 18 | 18 | 3 | 0 | 15 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 19 | 19 | 3 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__max_sublist_sum` | ok | True | 31 | 31 | 6 | 1 | 17 | 7 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__mergesort` | ok | True | 15 | 15 | 13 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 14 | 14 | 12 | 0 | 2 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 50 | 50 | 2 | 0 | 47 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__next_permutation` | ok | True | 27 | 27 | 21 | 0 | 2 | 4 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__node` | ok | False | 27 | 27 | 0 | 0 | 3 | 24 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 12 | 12 | 9 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__possible_change` | ok | True | 17 | 17 | 13 | 0 | 3 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__powerset` | ok | True | 25 | 25 | 14 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__quicksort` | ok | True | 25 | 25 | 4 | 0 | 21 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 13 | 13 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 15 | 15 | 7 | 0 | 8 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length` | ok | True | 18 | 18 | 0 | 0 | 6 | 12 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 14 | 14 | 6 | 0 | 6 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 13 | 13 | 8 | 0 | 5 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 45 | 45 | 40 | 0 | 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__sieve` | ok | True | 41 | 41 | 18 | 0 | 23 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | ok | True | 27 | 5 | 0 | 0 | 4 | 1 | 22 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__subsequences` | ok | True | 17 | 17 | 4 | 0 | 13 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__to_base` | ok | True | 58 | 57 | 18 | 0 | 32 | 7 | 1 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__topological_ordering` | ok | True | 11 | 11 | 0 | 0 | 3 | 8 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 26 | 18 | 16 | 0 | 2 | 0 | 8 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

### `plain_llm_df_doc_union`

| task_id | 状态 | signal | collected | classifiable | eff | mis | bp | bf | timeout | skipped | other | 归档det | 重放det | 归档verdict | verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | True | 106 | 5 | 0 | 0 | 5 | 0 | 101 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__breadth_first_search` | ok | True | 20 | 20 | 8 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__breadth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__bucketsort` | ok | True | 45 | 45 | 28 | 0 | 16 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__depth_first_search` | ok | True | 14 | 14 | 3 | 0 | 11 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__depth_first_search_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__detect_cycle` | ok | True | 20 | 20 | 6 | 0 | 14 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__detect_cycle_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__find_first_in_sorted` | ok | True | 51 | 42 | 12 | 0 | 30 | 0 | 9 | 0 | 0 | — | 1.0000 | specific_red | match |
| `quixbugs__find_in_sorted` | ok | True | 30 | 30 | 5 | 0 | 25 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__flatten` | ok | True | 22 | 22 | 13 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__gcd` | ok | True | 94 | 94 | 78 | 0 | 16 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__get_factors` | ok | True | 42 | 42 | 36 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__hanoi` | ok | True | 87 | 87 | 32 | 0 | 55 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__is_valid_parenthesization` | ok | True | 34 | 34 | 1 | 0 | 33 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__kheapsort` | ok | True | 30 | 30 | 18 | 0 | 12 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__knapsack` | ok | True | 31 | 30 | 1 | 1 | 28 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__kth` | ok | True | 44 | 44 | 11 | 0 | 33 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lcs_length` | ok | True | 59 | 59 | 19 | 0 | 39 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__levenshtein` | ok | True | 59 | 59 | 10 | 0 | 49 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__lis` | ok | True | 23 | 23 | 3 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__longest_common_subsequence` | ok | True | 30 | 29 | 3 | 0 | 26 | 0 | 1 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__max_sublist_sum` | ok | True | 39 | 39 | 11 | 0 | 28 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__mergesort` | ok | True | 35 | 35 | 32 | 0 | 3 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree` | ok | True | 14 | 14 | 13 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__minimum_spanning_tree_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__next_palindrome` | ok | True | 35 | 35 | 3 | 1 | 25 | 6 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__next_permutation` | ok | True | 24 | 24 | 14 | 0 | 10 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__node` | ok | False | 12 | 12 | 0 | 0 | 6 | 6 | 0 | 0 | 0 | — | 0.0000 | over_red | match |
| `quixbugs__pascal` | ok | True | 32 | 32 | 19 | 0 | 9 | 4 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__possible_change` | ok | True | 24 | 24 | 13 | 1 | 10 | 0 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__powerset` | structural_skip (generated_test_syntax_error) | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0000 | — | unavailable | not_applicable |
| `quixbugs__quicksort` | ok | True | 28 | 28 | 7 | 0 | 21 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list` | ok | True | 16 | 16 | 10 | 0 | 6 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__reverse_linked_list_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__rpn_eval` | ok | True | 27 | 27 | 10 | 0 | 16 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_length` | ok | True | 15 | 15 | 6 | 0 | 9 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__shortest_path_length_test` | structural_skip (import_error) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_path_lengths` | ok | True | 15 | 15 | 6 | 0 | 8 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_path_lengths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shortest_paths` | ok | True | 14 | 14 | 6 | 0 | 5 | 3 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__shortest_paths_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__shunting_yard` | ok | True | 35 | 35 | 8 | 0 | 9 | 18 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__sieve` | ok | True | 46 | 46 | 17 | 0 | 29 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | specific_red | match |
| `quixbugs__sqrt` | ok | True | 25 | 3 | 0 | 0 | 3 | 0 | 22 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__subsequences` | ok | True | 33 | 33 | 11 | 4 | 16 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__to_base` | ok | True | 70 | 69 | 24 | 0 | 45 | 0 | 1 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |
| `quixbugs__topological_ordering` | ok | True | 10 | 10 | 2 | 0 | 6 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | over_red | match |
| `quixbugs__topological_ordering_test` | structural_skip (import_error) | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | unavailable | not_applicable |
| `quixbugs__wrap` | ok | True | 31 | 21 | 20 | 0 | 1 | 0 | 10 | 0 | 0 | — | 0.0000 | unavailable | not_applicable |

## 8. 确定性声明

- 报告 body 不含时间戳/墙钟（这些只进 run_meta）；body digest = `678463c84c4d9b8ac79d4ecd9a627ec20b54046bfd364b4c5bff91397ee10625`。
- 重复重放次数 `repeat=2`，各次 body digest：`678463c84c4d9b8ac79d4ecd9a627ec20b54046bfd364b4c5bff91397ee10625`、`678463c84c4d9b8ac79d4ecd9a627ec20b54046bfd364b4c5bff91397ee10625`；**deterministic=True**。

## 9. 已知限制

- 生成测试之间的全局状态污染与收集顺序照旧存在（仅按版本隔离临时目录）
- 官方金测试 test_cases 不参与四分类，仅用于 detection_rate 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无官方金测试）在平铺口径下无法 import → 结构跳过；项目既有 41 口径（defect_program_ids，仅排除 *_test）中的 node 辅助模块任务 buggy==fixed（无缺陷信号），主分析集取 40 个有缺陷信号任务，41 口径兼容聚合单列可见
- per-test timeout 把挂死测试记为不可分类 timeout（不并入 both_fail），与 A-06 '超时记红' 的判分口径有意不同
- 两臂对比为描述性（非预注册确认性），不做显著性推断；跨批次随机性见交叉校验表
- 生成测试若使用未播种随机源，重复重放可能出现分类漂移（run_meta.determinism 如实披露）

