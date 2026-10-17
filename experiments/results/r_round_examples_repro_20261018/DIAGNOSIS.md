# R-1 A：Q-2 “LLM-suite 检出下降” 零 LLM 诊断（DIAGNOSIS）

> 输入：`experiments/results/q_round_examples_ab_20261018/` 两臂批次 JSON + traces。**零 LLM 调用**（仅本地读工件 + 文本/结构化对比）。
> 目的：判断 Q-2 的 detection 损失（A 15/15=100% → B 12/15=80%，3 任务 `detect_cycle`/`hanoi`/`knapsack`）是真实 trade-off 还是单次重跑噪声，并给 seed-43 复现批提供候选机制。

## 0. 输入与口径

- A（control，EXAMPLES=false）：`experiments/results/q_round_examples_ab_20261018/benchmark_quixbugs_20261018_045812.json`
- B（examples，EXAMPLES=true）：`experiments/results/q_round_examples_ab_20261018/benchmark_quixbugs_20261018_045359.json`
- 共同任务 20；detection 取行字段 `llm_suite_detection_rate`（缺失时回退 `detection_rate`；可判定=非 None）。
- 说明：结果行**不落 `test_plan` 原对象**（只有 planner 相关审计字段/ trace 摘要），故"契约是否改变 test_plan"只能从 generated_test 内容/长度、trace 节点决策、iteration/stop_reason/repair 轨迹间接推断；已如实标注。

## 1. 全量逐任务对比表（20 任务）

| task_id | det A→B | oracle A→B | iter A→B | stop A→B | gt_len A→B | #tests A→B | test-name Jaccard | trace A→B | repair_hist A→B | B examples src/count |
|---|---|---|---|---|---|---|---|---|---|---|
| `quixbugs__breadth_first_search_test` | —→— | unavailable→unavailable | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 2454→1552 | 7→6 | 0.300 | 3→3 | 2→2 | none/0 |
| `quixbugs__bucketsort` | 1.0→1.0 | unavailable→correct | 1→1 | test_passed→test_passed | 4385→4505 | 13→11 | 0.200 | 3→2 | 1→1 | planner/3 |
| `quixbugs__depth_first_search` | 1.0→1.0 | silent→silent | 1→2 | test_passed→test_passed | 4942→4300 | 13→12 | 0.562 | 2→3 | 1→2 | planner/1 |
| `quixbugs__depth_first_search_test` | —→— | unavailable→unavailable | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 2192→2217 | 8→8 | 0.067 | 3→3 | 2→2 | none/0 |
| `quixbugs__breadth_first_search` | 1.0→1.0 | silent→unavailable | 1→1 | test_passed→test_passed | 4221→3361 | 13→10 | 0.150 | 3→2 | 1→1 | planner/1 |
| `quixbugs__detect_cycle_test` | —→— | unavailable→unavailable | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 2487→2597 | 8→9 | 0.062 | 3→3 | 2→2 | none/0 |
| `quixbugs__detect_cycle` | 1.0→0.0 | unavailable→unavailable | 1→1 | test_passed→test_passed | 2604→5329 | 9→15 | 0.263 | 2→3 | 1→1 | planner/1 |
| `quixbugs__find_in_sorted` | 1.0→1.0 | unavailable→unavailable | 1→1 | test_passed→test_passed | 3816→4591 | 13→16 | 0.160 | 2→2 | 1→1 | planner/3 |
| `quixbugs__flatten` | 1.0→1.0 | unavailable→unavailable | 1→1 | test_passed→test_passed | 2513→2784 | 12→9 | 0.400 | 2→2 | 1→1 | planner/3 |
| `quixbugs__gcd` | 1.0→1.0 | unavailable→unavailable | 1→1 | test_passed→test_passed | 2556→3441 | 8→11 | 0.056 | 3→3 | 1→1 | planner/3 |
| `quixbugs__get_factors` | 1.0→1.0 | unavailable→correct | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 2896→3862 | 11→11 | 0.158 | 4→3 | 2→2 | planner/3 |
| `quixbugs__hanoi` | 1.0→0.0 | unavailable→correct | 1→3 | test_passed→max_iterations | 3430→3432 | 13→11 | 0.043 | 2→5 | 1→3 | planner/3 |
| `quixbugs__kheapsort` | 1.0→1.0 | unavailable→correct | 2→1 | skip_debugger_repair_invalid→test_passed | 2993→4139 | 13→14 | 0.080 | 3→2 | 2→1 | planner/3 |
| `quixbugs__is_valid_parenthesization` | 1.0→1.0 | unavailable→silent | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 3668→4367 | 14→16 | 0.071 | 4→4 | 2→2 | planner/3 |
| `quixbugs__kth` | 1.0→1.0 | unavailable→silent | 1→1 | test_passed→test_passed | 3246→3906 | 13→12 | 0.250 | 2→2 | 1→1 | planner/3 |
| `quixbugs__knapsack` | 1.0→0.0 | unavailable→silent | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 4299→3059 | 24→10 | 0.259 | 4→4 | 2→2 | planner/3 |
| `quixbugs__lcs_length` | 1.0→1.0 | unavailable→correct | 1→1 | test_passed→test_passed | 4275→4538 | 17→16 | 0.138 | 2→2 | 1→1 | planner/3 |
| `quixbugs__levenshtein` | 1.0→1.0 | unavailable→correct | 1→1 | test_passed→test_passed | 4612→3811 | 16→14 | 0.154 | 2→2 | 1→1 | planner/3 |
| `quixbugs__bitcount` | —→— | silent→unavailable | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 2490→2959 | 10→10 | 0.176 | 3→3 | 2→2 | planner/3 |
| `quixbugs__find_first_in_sorted` | —→— | unavailable→unavailable | 2→2 | skip_debugger_repair_invalid→skip_debugger_repair_invalid | 3921→4010 | 16→13 | 0.381 | 3→3 | 2→2 | planner/3 |

**全量差异幅度**：两臂 **20/20** 任务的 generated_test 均不同（test-name Jaccard 均值 **0.197**）；gt_len 相对差均值 **0.217**；3 个不一致任务的 Jaccard 均值 **0.189**、gt_len 相对差均值 **0.445**——与全量分布同级（不一致任务的生成差异并不比普通任务更"异常"）。B 臂 examples 来源：`{"none": 3, "planner": 17}`；examples count 分布：`{"0": 3, "3": 14, "1": 3}`。

## 2. 3 个 detection 损失任务逐任务时间线

### `quixbugs__detect_cycle`

| 维度 | A（EXAMPLES=false） | B（EXAMPLES=true） |
|---|---|---|
| detection | 1.00 | 0.00 |
| oracle_suite_verdict | unavailable | unavailable |
| spec_oracle_verdict | injected_and_passed | injected_and_passed |
| iterations | 1 | 1 |
| stop_reason | test_passed | test_passed |
| passed | True | True |
| generated_test 长度 | 2604 | 5329 |
| 测试函数数 | 9 | 15 |
| assert/pytest.raises 数 | 10 | 19 |
| execution_trace 轮数 | 2 | 3 |
| repair_history 长度 | 1 | 1 |
| patch_correct | 0 | 0 |
| error_category | runtime | test_regenerated_pass_unverified |
| examples_source | none | planner |
| examples_count | 0 | 1 |

**A trace 轮次**：None:False,cov_delta=None；None:True,cov_delta=1.0

**B trace 轮次**：None:False,cov_delta=None；None:False,cov_delta=-4.0；None:True,cov_delta=6.0

- A diagnosis: `detect_cycle 中 while True 循环内，第 5 行 hare = hare.successor.successor 在 hare.successor 为 None 时会抛出 AttributeError（对 None 取 .successor）。第 4 行只检查了 hare.successor is None，但未检查 hare.successor.successor 是否为 `
- B diagnosis: `detect_cycle 中 hare 每次前进两步（第 9 行 `hare = hare.successor.successor`），但只检查了 `hare.successor is None`（第 5 行），未检查 `hare.successor.successor` 是否为 None。对于偶数长度的无环链表，hare 会先到达最后一个节点，此时 hare.successor 为 None，但`

### `quixbugs__hanoi`

| 维度 | A（EXAMPLES=false） | B（EXAMPLES=true） |
|---|---|---|
| detection | 1.00 | 0.00 |
| oracle_suite_verdict | unavailable | correct |
| spec_oracle_verdict | injected_and_passed | injected |
| iterations | 1 | 3 |
| stop_reason | test_passed | max_iterations |
| passed | True | False |
| generated_test 长度 | 3430 | 3432 |
| 测试函数数 | 13 | 11 |
| assert/pytest.raises 数 | 15 | 16 |
| execution_trace 轮数 | 2 | 5 |
| repair_history 长度 | 1 | 3 |
| patch_correct | 0 | 0 |
| error_category | assertion | assertion |
| examples_source | none | planner |
| examples_count | 0 | 3 |

**A trace 轮次**：None:False,cov_delta=None；None:True,cov_delta=0.0

**B trace 轮次**：None:False,cov_delta=None；None:False,cov_delta=0.0；None:False,cov_delta=0.0；None:False,cov_delta=0.0；None:False,cov_delta=0.0

- A diagnosis: `hanoi 函数第 6 行 `steps.append((start, helper))` 错误：递归分解应为「将 height-1 个盘从 start 移到 helper，再将最大盘从 start 移到 end，最后将 height-1 个盘从 helper 移到 end」。原代码把最大盘的目标写成了 helper，导致所有步骤序列错误，首步/末步断言失败。`
- B diagnosis: `hanoi 函数第 6 行 `steps.append((start, helper))` 记录的是从 start 移到辅助柱 helper 的步骤，但根据汉诺塔算法，递归移动 height-1 个盘到 helper 后，应把最大的盘从 start 移到目标柱 end，即应为 `steps.append((start, end))`。当前实现导致 height=1 时返回 [(1,2)] 而非期望`

### `quixbugs__knapsack`

| 维度 | A（EXAMPLES=false） | B（EXAMPLES=true） |
|---|---|---|
| detection | 1.00 | 0.00 |
| oracle_suite_verdict | unavailable | silent |
| spec_oracle_verdict | injected | injected |
| iterations | 2 | 2 |
| stop_reason | skip_debugger_repair_invalid | skip_debugger_repair_invalid |
| passed | False | False |
| generated_test 长度 | 4299 | 3059 |
| 测试函数数 | 24 | 10 |
| assert/pytest.raises 数 | 28 | 13 |
| execution_trace 轮数 | 4 | 4 |
| repair_history 长度 | 2 | 2 |
| patch_correct | 0 | 0 |
| error_category | patch_validation_failed | patch_validation_failed |
| examples_source | none | planner |
| examples_count | 0 | 3 |

**A trace 轮次**：None:True,cov_delta=None；None:False,cov_delta=3.0；None:False,cov_delta=0.0；None:False,cov_delta=0.0

**B trace 轮次**：None:False,cov_delta=None；None:False,cov_delta=-4.0；None:False,cov_delta=0.0；None:False,cov_delta=0.0

- A diagnosis: `knapsack 函数第 12 行条件 `if weight < j:` 使用了严格小于，导致物品重量恰好等于当前容量 j 时被错误排除。正确条件应为 `weight <= j`。这解释了 test_knapsack_weight_equal_capacity_boundary、test_knapsack_capacity_one_weight_one 等失败用例（重量等于容量时返回 0 而非物品`
- B diagnosis: `knapsack 函数第 13 行（`if weight < j:`）使用了严格小于比较，导致当物品重量恰好等于当前容量 j（weight == j）时该物品被跳过；更关键的是零重量物品（weight == 0）时，条件 `0 < j` 对 j>=1 成立，但 `j - weight = j`，此时 memo[i-1][j] 与 memo[i][j] 相同，无法体现「取该物品」的收益，且当 j 从`

## 3. 候选机制判断（a/b/c）

### a) Planner 契约段改变下游行为（Prompt 内容/注意力挤占 → test_plan/生成测试差异）
- **有正证据**：B 臂 `spec_oracle_examples_source=planner`（17/20 任务；45 条 examples），oracle `correct` 0→6（`bucketsort/get_factors/hanoi/kheapsort/lcs_length/levenshtein`），说明契约段确实改变了 Planner 输出并被 oracle 编译消费。
- **下游影响证据（强候选）**：`hanoi` A=1 轮 test_passed/detection=1，B=3 轮 max_iterations/detection=0（B oracle 也变 correct）——同一任务在 B 的修复轨迹/生成测试完全不同，说明契约段可能通过 plan 改变了生成/修复行为；这不是"仅 oracle 测试"层面的影响。
- **局限**：结果行不落 test_plan 原对象，无法直接逐字段比对 plan；且所有 20 任务两臂 generated_test 均不同（Jaccard 均值 0.20），单次运行无法把"契约导致的系统差异"与"一般随机性"分离。

### b) 随机性（temp=0 仍非确定）
- **有正证据**：20/20 任务两臂生成的测试内容均不同（Jaccard<1）；gt_len 相对差均值 0.22；同类配置在 O/P 轮重跑中也出现过 1–2 任务级差异。
- **量级**：本批 detection 损失 3/15=20pp；历史同配置重复跑小样本差异约 2/20=10pp 量级；单次运行不足以排除随机性，但 20pp 略高于既往噪声量级 → 需 seed-43 复现裁决（预注册规则）。

### c) examples 注入只改 oracle-suite、对 LLM-suite 无直接影响（arm 间生成差异导致）
- **与判定口径一致**：N-3 起 `detection_rate` 语义=LLM-suite（排除 oracle 测试）；oracle correct +6 但只 `hanoi` 与 detection 损失重叠，说明 detection 损失**不是 oracle 测试注入/误判**所致。
- **解释**：B 的 LLM-suite 测试内容与 A 不同（生成器受 planner 输出影响），M1 重放判分因此不同；这是"生成差异"而非 oracle 判分错误。

## 4. 初步结论（跑 seed-43 前）

- **不能判定为 reproducible trade-off**：单次运行、全 20 任务生成均不同、3 个损失任务的生成差异幅度与普通任务同级；但 `hanoi` 的 A/B 轨迹差异（1 轮 test_passed vs 3 轮 max_iterations）提示契约段可能真实改变了修复/测试策略，值得复现。
- **候选机制排序（暂定）**：(a) 契约段改变 Planner→生成/修复行为（有 oracle-correct 正证据 + hanoi 轨迹证据，但无法与随机性分离） > (b) 随机性（全量生成差异同级） > (c) oracle-suite 直接影响（口径上排除）。
- **裁决依赖**：按 `PREREG_REPRO.md` 冻结规则跑 seed-43：`direction_consistent = B_det < A_det 且损失 ≥10pp`；若复现 → `reproducible_tradeoff`（生产保持关/登记真实风险）；否则 `not_reproduced`（视为单次噪声；仍不自动生产化，登记 3 臂复核）。

## 5. 证据路径

| 文件 | 说明 |
|---|---|
| `experiments/results/q_round_examples_ab_20261018/benchmark_quixbugs_*.json` | 两臂批次（行级 generated_test/verdict/iteration/stop/error 等） |
| `experiments/results/q_round_examples_ab_20261018/traces_control/` / `traces_examples/` | 逐任务 trace（节点决策/迭代） |
| `experiments/results/q_round_examples_ab_20261018/ANALYSIS_REPORT.json` | Q-2 机读聚合（detection/verdict/McNemar） |
| `experiments/results/r_round_examples_repro_20261018/DIAGNOSIS_EVIDENCE.json` | 本诊断的机读证据（逐任务表/mismatch detail/aggregate） |
| `experiments/results/r_round_examples_repro_20261018/_helpers/write_diagnosis.py` | 本报告生成脚本（可复算） |

> 复算命令：`.venv/bin/python experiments/results/r_round_examples_repro_20261018/_helpers/write_diagnosis.py`（零 LLM）。
