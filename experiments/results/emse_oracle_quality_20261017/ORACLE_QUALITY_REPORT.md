# A-05 确定性规约 oracle 质量度量报告（零 LLM 重放）

> **性质**：描述性机制度量（A-05/G6 缺口补齐），**非**预注册确认性证据；
> oracle 质量反映确定性规约通道，**不是 LLM 生成能力指标**；不做显著性推断。
> **生成时间**：2026-10-17T13:18:31+00:00　**body digest**：`ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376`
> **工具**：experiments.oracle_quality_replay v1.0.0　**schema**：`oracle_quality_metric/1`

复算命令：

```bash
python -m experiments.oracle_quality_replay --out experiments/results/emse_oracle_quality_20261017 --jobs 4 --per-test-timeout 1 --file-timeout 240 --repeat 1
```

## 1. 输入与锚表

| 工件 | sha256 | 臂 | 行数 |
|---|---|---|---|
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json` | `813c437fc53a84c1517cce234b12184e5047bf483fb982cb9382d1c61307245a` | `plain_llm_df_spec` | 50 |
| `experiments/results/emse_df_spec_20261016/benchmark_quixbugs_20261017_003023.json` | `536da803dbb290dab9dff26ae14302a8ce8d452e058b1d2c4c1705852900d0ec` | `plain_llm_df` | 50 |

锚表：`experiments/results/emse_spec_anchor_20261016/SPEC_ANCHOR_TABLE.json`　sha256=`3e90b2ad5ed365ad5ee989c73c92b84956a83c0fa8cb51368d288ae3ea53bf22`　校验来源=`experiments/results/emse_spec_anchor_20261016/SHA256SUMS`
锚表规模：416 条锚；构建器 `experiments/build_spec_anchor_table.py`；缓存扫描 6754 / Planner 条目 1534

## 2. 口径定义

| oracle 类别 | 定义 |
|---|---|
| `correct` | oracle 测试 buggy 失败 ∧ fixed 通过（真检出：区分缺陷版与修复版） |
| `fp` | oracle 在正确实现（fixed）上失败 = 假阳；含 buggy 失败 ∧ fixed 失败的恒红型 oracle |
| `silent` | 两侧都通过（对该缺陷零信号，oracle 断言未触达缺陷行为） |
| `misguided` | oracle 测试 buggy 通过 ∧ fixed 失败（把缺陷行为断言成期望行为） |

> 分母纪律：四分类占比分母 = 可分类 oracle 测试数（buggy/fixed 两侧均有 pass/fail 结果）；timeout/collect_error/import_error/syntax_error/skipped/test_error/missing_side/unknown 单列、不进分母；任务级结构跳过单独计数，不混入可判定集合

> 注入路径：生产函数 src.graph.nodes._append_spec_oracle_to_test_with_verdict 原样调用；state 由锚表重建（test_plan={function_name, logic_analysis}、target_function、module_name=task_id 末段、target_code=缺陷版源码；不写现场 spec_ir/boundary_triplets）

> 交叉校验：0 mismatch：① LLM-only 重放 detection vs 归档 detection_rate 两侧均可判时必须一致；② 归档 spec_oracle_verdict 用『归档 state 语义』重放生产注入口必须一致；差异逐条归因，不静默

## 3. 注入统计

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 任务行数 | 50 | 50 |
| 锚命中数 | 50 | 50 |
| 尝试注入任务数 | 49 | 49 |
| 注入成功任务数 | 38 | 38 |
| 编译产物为空任务数 | 11 | 11 |
| 注入率（占任务行） | 76.00% | 76.00% |
| 编译产物非空率（占尝试） | 77.55% | 77.55% |
| 可测 oracle 任务数 | 38 | 38 |

各臂注入 verdict 分布：

- `plain_llm_df_spec`：`compiled_empty`=11、`injected`=38、`not_attempted`=1
- `plain_llm_df`：`compiled_empty`=11、`injected`=38、`not_attempted`=1

## 4. oracle 四分类（分母 = 可分类 oracle 测试数）

### 4.1 40 缺陷程序主分析集（非 *_test 且 buggy≠fixed）

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 可测任务数 | 38 | 38 |
| 可分类 oracle 测试数（分母） | 38 | 38 |
| `correct` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| `fp` 计数 / 占比 | 29 / 76.32% | 29 / 76.32% |
| `silent` 计数 / 占比 | 9 / 23.68% | 9 / 23.68% |
| `misguided` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| 含 `correct` 的任务数 | 0 | 0 |
| 含 `fp` 的任务数 | 29 | 29 |
| 每任务 oracle 测试数（mean/median） | 1.0000 / 1.0000 | 1.0000 / 1.0000 |

### 4.2 全量任务行

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 可测任务数 | 38 | 38 |
| 可分类 oracle 测试数（分母） | 38 | 38 |
| `correct` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| `fp` 计数 / 占比 | 29 / 76.32% | 29 / 76.32% |
| `silent` 计数 / 占比 | 9 / 23.68% | 9 / 23.68% |
| `misguided` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| 含 `correct` 的任务数 | 0 | 0 |
| 含 `fp` 的任务数 | 29 | 29 |
| 每任务 oracle 测试数（mean/median） | 1.0000 / 1.0000 | 1.0000 / 1.0000 |

### 4.3 可测注入任务

| 指标 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 可测任务数 | 38 | 38 |
| 可分类 oracle 测试数（分母） | 38 | 38 |
| `correct` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| `fp` 计数 / 占比 | 29 / 76.32% | 29 / 76.32% |
| `silent` 计数 / 占比 | 9 / 23.68% | 9 / 23.68% |
| `misguided` 计数 / 占比 | 0 / 0.00% | 0 / 0.00% |
| 含 `correct` 的任务数 | 0 | 0 |
| 含 `fp` 的任务数 | 29 | 29 |
| 每任务 oracle 测试数（mean/median） | 1.0000 / 1.0000 | 1.0000 / 1.0000 |

### 4.4 不可分类原因与失败类型（诊断）

| 项 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| fixed 侧失败类型 `assertion` | 2 | 2 |
| fixed 侧失败类型 `exception` | 27 | 27 |
| fixed 侧失败类型 `timeout` | 0 | 0 |
| fixed 侧失败类型 `other` | 0 | 0 |

fixed 侧失败异常类型分布（假阳根因诊断）：

| 异常类型 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| `AttributeError` | 2 | 2 |
| `TypeError` | 24 | 24 |
| `ZeroDivisionError` | 1 | 1 |

## 5. 注入任务检出贡献（任务级，M1 detection 口径）

| 指标（40 缺陷程序口径） | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| 归档 detection（LLM-only） | 19 / 35 = 54.29% | 28 / 36 = 77.78% |
| LLM-only 重放 detection | 20 / 40 = 50.00% | 31 / 40 = 77.50% |
| oracle-augmented 重放 detection | 4 / 38 = 10.53% | 7 / 38 = 18.42% |
| Δ augmented − llm_only（配对，pp） | -36.8421 | -57.8947 |
| 配对 LLM-only 重放 vs 归档（n_paired / n_changed） | 35 / 0 | 36 / 0 |

转移表（任务级 0/1，LLM-only → oracle-augmented）：

| 转移 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| `lost` | 14 | 22 |
| `none` | 20 | 9 |
| `preserved` | 4 | 7 |
| `undecidable` | 2 | 2 |

`plain_llm_df_spec` 检出损失任务（oracle 假阳使 fixed 转红，共 14）：

- `quixbugs__detect_cycle`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__find_first_in_sorted`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__find_in_sorted`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__is_valid_parenthesization`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__kth`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__lcs_length`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__lis`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__longest_common_subsequence`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__mergesort`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__next_permutation`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__quicksort`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__reverse_linked_list`：oracle fp=1 misguided=0 fixed 侧失败类型={'assertion': 1}
- `quixbugs__shortest_path_length`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__topological_ordering`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}

`plain_llm_df` 检出损失任务（oracle 假阳使 fixed 转红，共 22）：

- `quixbugs__detect_cycle`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__find_first_in_sorted`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__find_in_sorted`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__gcd`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__is_valid_parenthesization`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__kheapsort`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__knapsack`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__kth`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__lcs_length`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__levenshtein`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__lis`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__longest_common_subsequence`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__mergesort`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__minimum_spanning_tree`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__next_palindrome`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__next_permutation`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__pascal`：oracle fp=1 misguided=0 fixed 侧失败类型={'assertion': 1}
- `quixbugs__powerset`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__quicksort`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__reverse_linked_list`：oracle fp=1 misguided=0 fixed 侧失败类型={'assertion': 1}
- `quixbugs__rpn_eval`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}
- `quixbugs__topological_ordering`：oracle fp=1 misguided=0 fixed 侧失败类型={'exception': 1}

## 6. 交叉校验（0 mismatch 要求）

| 对账项 | `plain_llm_df_spec` | `plain_llm_df` |
|---|---|---|
| detection 对账 `artifact_none` | 6 | 5 |
| detection 对账 `both_none` | 9 | 9 |
| detection 对账 `match` | 35 | 36 |
| oracle verdict 对账 `match` | 50 | 50 |
| 归档字段自洽性违规 | 0 | 0 |
| **all_ok（0 mismatch）** | **True** | **True** |

**`plain_llm_df_spec` detection 对账差异/非匹配（6 条，逐条归因）**：

| task_id | 归档 | 重放 | 重放(strict) | 标签 | 归因 |
|---|---|---|---|---|---|
| `quixbugs__bitcount` | — | 0.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__node` | — | 0.0000 | 0.0000 | artifact_none | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 0.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__to_base` | — | 0.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__wrap` | — | 0.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |

**`plain_llm_df` detection 对账差异/非匹配（5 条，逐条归因）**：

| task_id | 归档 | 重放 | 重放(strict) | 标签 | 归因 |
|---|---|---|---|---|---|
| `quixbugs__bitcount` | — | 1.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__find_first_in_sorted` | — | 1.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__node` | — | 0.0000 | 0.0000 | artifact_none | 归档 None 但历史口径重放可判——需人工核对（可能为跨批次随机性） |
| `quixbugs__sqrt` | — | 1.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |
| `quixbugs__wrap` | — | 0.0000 | — | artifact_none | 归档 None、重放可判（材料/执行环境差异，需人工核对） |

## 7. 臂间描述性对比（oracle 质量与检出贡献）

**plain_llm_df_spec → plain_llm_df**（`delta_pp` = B − A，百分点；40 缺陷程序口径）：

| 指标 | `plain_llm_df_spec` | `plain_llm_df` | delta_pp |
|---|---|---|---|
| `correct_share` | 0.00% | 0.00% | 0.0000 |
| `fp_share` | 76.32% | 76.32% | 0.0000 |
| `silent_share` | 23.68% | 23.68% | 0.0000 |
| `misguided_share` | 0.00% | 0.00% | 0.0000 |
| `injection_rate_of_rows` | 95.00% | 95.00% | 0.0000 |
| `compiled_nonempty_rate_of_attempted` | 95.00% | 95.00% | 0.0000 |
| `archived_rate` | 54.29% | 77.78% | 23.4921 |
| `llm_only_replay_rate` | 50.00% | 77.50% | 27.5000 |
| `oracle_augmented_replay_rate` | 10.53% | 18.42% | 7.8948 |

> 描述性对比：delta_pp = 臂 B − 臂 A（百分点），不构成预注册确认性证据、无显著性/效应量推断；数值须结合分母披露与交叉校验表解读。oracle 质量反映确定性通道，不是 LLM 生成能力指标。

## 8. 结构跳过 / oracle 未测量任务（不静默跳过）

**`plain_llm_df_spec`（0 个）**：

- 无

**`plain_llm_df`（0 个）**：

- 无

### 8.1 oracle 未测量原因（注入未成功 / 增强重放不可分类）

**`plain_llm_df_spec`（可测 38 / 未测量 12）**：

- `not_injected`：12

**`plain_llm_df`（可测 38 / 未测量 12）**：

- `not_injected`：12

> 未测量任务不进四分类分母；上述原因与注入 verdict 分布（§3）一并披露。

## 9. 逐任务明细

### `plain_llm_df_spec`

| task_id | 状态 | 注入 | oracle测试 | correct | fp | silent | mis | 不可分类 | 归档det | LLM重放det | 增强重放det | 转移 | 归档verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | — | 0.0000 | 0.0000 | none | match |
| `quixbugs__breadth_first_search` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__breadth_first_search_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__bucketsort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__depth_first_search` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__depth_first_search_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__detect_cycle` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__detect_cycle_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__find_first_in_sorted` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | — | 1.0000 | 0.0000 | lost | match |
| `quixbugs__find_in_sorted` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__flatten` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | — | undecidable | match |
| `quixbugs__gcd` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__get_factors` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__hanoi` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__is_valid_parenthesization` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__kheapsort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__knapsack` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__kth` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__lcs_length` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__levenshtein` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__lis` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__longest_common_subsequence` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__max_sublist_sum` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | — | undecidable | match |
| `quixbugs__mergesort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__minimum_spanning_tree` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__minimum_spanning_tree_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__next_palindrome` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__next_permutation` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__node` | ok | not_attempted | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.0000 | — | undecidable | match |
| `quixbugs__pascal` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__possible_change` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__powerset` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__quicksort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__reverse_linked_list` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__reverse_linked_list_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__rpn_eval` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_path_length` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__shortest_path_length_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shortest_path_lengths` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_path_lengths_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shortest_paths` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_paths_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shunting_yard` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__sieve` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__sqrt` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | — | 0.0000 | 0.0000 | none | match |
| `quixbugs__subsequences` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__to_base` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | — | 0.0000 | 0.0000 | none | match |
| `quixbugs__topological_ordering` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__topological_ordering_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__wrap` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | — | 0.0000 | 0.0000 | none | match |

### `plain_llm_df`

| task_id | 状态 | 注入 | oracle测试 | correct | fp | silent | mis | 不可分类 | 归档det | LLM重放det | 增强重放det | 转移 | 归档verdict对账 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__bitcount` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | — | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__breadth_first_search` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__breadth_first_search_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__bucketsort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__depth_first_search` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__depth_first_search_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__detect_cycle` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__detect_cycle_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__find_first_in_sorted` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | — | 1.0000 | 0.0000 | lost | match |
| `quixbugs__find_in_sorted` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__flatten` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | — | undecidable | match |
| `quixbugs__gcd` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__get_factors` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__hanoi` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__is_valid_parenthesization` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__kheapsort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__knapsack` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__kth` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__lcs_length` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__levenshtein` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__lis` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__longest_common_subsequence` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__max_sublist_sum` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | — | undecidable | match |
| `quixbugs__mergesort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__minimum_spanning_tree` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__minimum_spanning_tree_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__next_palindrome` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__next_permutation` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__node` | ok | not_attempted | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.0000 | — | undecidable | match |
| `quixbugs__pascal` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__possible_change` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__powerset` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__quicksort` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__reverse_linked_list` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__reverse_linked_list_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__rpn_eval` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__shortest_path_length` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_path_length_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shortest_path_lengths` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_path_lengths_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shortest_paths` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__shortest_paths_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__shunting_yard` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__sieve` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__sqrt` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | — | 1.0000 | 1.0000 | preserved | match |
| `quixbugs__subsequences` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__to_base` | ok | injected | 1 | 0 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | none | match |
| `quixbugs__topological_ordering` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 | lost | match |
| `quixbugs__topological_ordering_test` | ok | compiled_empty | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | undecidable | match |
| `quixbugs__wrap` | ok | injected | 1 | 0 | 1 | 0 | 0 | 0 | — | 0.0000 | 0.0000 | none | match |

## 10. 确定性声明

- 报告 body 不含时间戳/墙钟；body digest = `ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376`。
- 重复重放次数 `repeat=1`，各次 body digest：`ce10e33bc54b56c00c26cd5fd5f7f741649a52554e579d0f154f4a46fd372376`；**deterministic=True**。

## 11. 已知限制

- 反事实注入口径：锚表材料直接重建 test_plan（无 Planner 现场 spec_ir / boundary_triplets），不声称等同完整 logic 链路生产注入质量
- 归档批次（plain_llm_df*，Planner 关闭）生产注入口未实际尝试注入；本报告质量数字来自零 LLM 重放
- oracle 与 LLM 测试同文件、同 pytest session 执行（生产口径），全局状态污染与收集顺序照旧
- 官方金测试 test_cases 不参与本分类，仅用于任务级 detection 交叉校验口径说明
- 9 个 QuixBugs *_test 驱动任务（相对 import、无金测试）与辅助模块 node 在平铺执行口径下结构性不可 replay → 结构跳过单列；41 口径兼容行（node，buggy==fixed）无缺陷信号，主分析集为 40 口径
- per-test timeout 把挂死 oracle 测试记为不可分类 timeout（不并入四分类），与 M1 判分口径有意不同
- oracle 假阳/误导若因编译器提供的 0 字面量绑定导致（如 TypeError），属确定性通道自身缺陷，由 failure_stats.fixed_side_exception_types 逐类披露，不在本工具内修复
- 描述性对比，不提供显著性推断；两臂差异仅作机制侧方向参考

