# S-1：seed-44 复现批 + 3-seed 生产化决策（预注册二臂 A/B，真 LLM，QuixBugs 20 任务）

> **性质：预注册决策支持（decision support，非能力主张）**。决策规则在 `PREREG_DECISION.md` 跑前冻结；本批只按该规则报告 `enable_candidate` / `keep_off`；生产开关默认关不变，enabling 需另行变更+回归。

## 0. S-1 决策摘要（三 seed 合并）

> 决策规则跑前冻结于 `PREREG_DECISION.md`：`enable_candidate` = ① oracle-correct Δ≥5 任务 in ≥2/3 seeds ∧ ② LLM-suite 损失 loss_pp≤5pp in ≥2/3 seeds；否则 `keep_off`。
> **决策支持、非能力主张；生产开关 `SPEC_ORACLE_EXAMPLES_ENABLE` 默认关不变。**

### 三 seed 合并表（主指标）

| seed | 来源 | A_correct | B_correct | Δ=B−A | A_det | B_det | loss_pp | b/c | McNemar p | Q-2 规则判定（参考） |
|---|---|---|---|---|---|---|---|---|---|---|
| 42 | Q-2 q_round_examples_ab_20261018 | 0 | 6 | **+6** | 15/15 | 12/15 | **20.00** | 6/0 | 0.015625 | not_confirmed |
| 43 | R-1 r_round_examples_repro_20261018 | 0 | 6 | **+6** | 13/15 | 13/15 | **0.00** | 6/0 | 0.015625 | confirmed |
| 44 | S-1 本批 | 0 | 6 | **+6** | 11/15 | 11/15 | **0.00** | 6/0 | 0.015625 | confirmed |

### 两条判据逐项

| 判据 | 结果 | 达成 seeds |
|---|---|---|
| ① oracle-correct Δ≥5 in ≥2/3 seeds | **PASS** | 42, 43, 44 |
| ② LLM-suite loss_pp≤5pp in ≥2/3 seeds | **PASS** | 43, 44 |

### **决策：`enable_candidate`**

- 两条判据均满足 → 进入 candidate 阶段（enabling 仍需另行变更+回归；生产默认关不变）。
- 逐 seed Q-2 冻结规则口径判定（仅参考，不参与本决策规则）：seed42=not_confirmed; seed43=confirmed; seed44=confirmed。

## 1. 协议与切点

- 切点：`566f97339b0b9728f8a948afbf449a2eb87408c2`（Q-1 q-examples；跑前/跑后 worktree dirty=0）
- 两臂并发、同秒启动、独立 namespace、`AITESTER_LLM_CACHE=0`；`AITESTER_PROFILE=logic`、TEMPERATURE=0.0、LLM_THINKING_MODE=disabled、`BENCHMARK_PARALLELISM=4`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、`AITESTER_BATCH_MAX_CALLS=200`、watchdog 3600s/臂。
- A（control）：`SPEC_ORACLE_EXEC_ENABLE=true` + `SPEC_ORACLE_EXAMPLES_ENABLE=false`；B（examples）：两者均 `true`；`--dataset quixbugs --task-limit 20 --seed 44 --baselines aitester`。
- 预注册：`PREREG_DECISION.md`（sha256 `95a790160763b46a7567b61b9e658aafb92c6de33316b6d0377d01056669bf1b`）；预算 ≤$0.3，墙钟 ≤70.0min。

## 2. 预注册决策规则（冻结，S-1）

**本批（seed44）只提供第三个 seed 的测量；决策 = 三 seed 合并规则（只读合并，不重跑 seed42/43）：**
- **`enable_candidate`** = ① Δ=B_correct−A_correct ≥ **5 任务** in **≥2/3 seeds** ∧ ② LLM-suite 损失 loss_pp=(A_det−B_det)×100 ≤ **5pp** in **≥2/3 seeds**；
- 否则 → **`keep_off`**。
- 声明：决策支持、非能力主张；生产开关默认关不变；enabling 需另行变更+回归。
- 同时报告逐 seed 的 Q-2 冻结规则口径判定/McNemar/verdict 分布/examples 来源/成本墙钟（见 §0/§4）。

## 3. 两臂表（实测）

| 项 | A control | B examples |
|---|---|---|
| 批次 sha256 | `f2b826274225b1f1…` | `0bafbfbb59615f95…` |
| 行数 / exit | 20 / 0 | 20 / 0 |
| 墙钟(s) | 2122 | 2108 |
| tokens / calls | 274405 / 97 | 271208 / 94 |
| 成本（标准价上界） | $0.142296 | $0.136544 |
| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `true` | `true` |
| env_snapshot.SPEC_ORACLE_EXAMPLES_ENABLE | `false` | `true` |
| `oracle_suite_verdict` 分布 | `{"unavailable": 17, "silent": 3}` | `{"correct": 6, "unavailable": 10, "silent": 4}` |
| `spec_oracle_examples_source` 分布 | `{"none": 20}` | `{"planner": 17, "none": 3}` |
| `spec_oracle_examples_count` 统计 | `{"n_rows_with_count": 20, "mean": 0.0, "max": 0, "total": 0}` | `{"n_rows_with_count": 20, "mean": 2.25, "max": 3, "total": 45}` |
| 注入率 | 15/20 | 17/20 |
| LLM-suite detection | 73.33%（11/15） | 73.33%（11/15） |

## 4. 主指标配对与判定（S-1：决策 + 本批参考指标）

**三 seed 决策**：① Δ≥5 in ≥2/3 seeds = **PASS**（seeds 42, 43, 44）；
② loss_pp≤5pp in ≥2/3 seeds = **PASS**（seeds 43, 44）→ **决策 `enable_candidate`**。

**本批（seed44）参考指标（Q-2 冻结规则口径，不参与 S-1 决策）**：
- 共同任务 **20**；A_correct=**0**，B_correct=**6**（Δ=**6**；b=**6**，c=**0**，McNemar p=**0.015625**）；
- LLM-suite detection：A=11/15，B=11/15，loss_pp=**0.00**；
- 本批 Q-2 规则 verdict（参考）：`confirmed`。

## 5. 逐任务配对（主指标 oracle-correct + 示例来源/计数 + LLM-suite detection）

| task_id | A verdict | B verdict | b | A ex_source/count | B ex_source/count | A det | B det |
|---|---|---|---|---|---|---|---|
| `quixbugs__bucketsort` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__breadth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__breadth_first_search` | silent | unavailable |  | none/0 | planner/1 | 1.0000 | 0.0000 |
| `quixbugs__depth_first_search` | silent | silent |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__depth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__detect_cycle_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__find_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__detect_cycle` | unavailable | unavailable |  | none/0 | planner/1 | 0.0000 | 0.0000 |
| `quixbugs__flatten` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__gcd` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__get_factors` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__is_valid_parenthesization` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 0.0000 |
| `quixbugs__hanoi` | unavailable | correct | ★ | none/0 | planner/3 | 0.0000 | 1.0000 |
| `quixbugs__kheapsort` | unavailable | correct | ★ | none/0 | planner/3 | 0.0000 | 1.0000 |
| `quixbugs__knapsack` | unavailable | silent |  | none/0 | planner/3 | 0.0000 | 0.0000 |
| `quixbugs__kth` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__lcs_length` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__levenshtein` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__bitcount` | silent | unavailable |  | none/0 | planner/3 | — | — |
| `quixbugs__find_first_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | — | — |

## 6. 次指标

- 注入率：A 15/20；B 17/20。
- `spec_oracle_verdict` 分布：A `{"injected_and_passed": 8, "compiled_empty": 4, "injected": 7, "not_attempted": 1}` / B `{"injected_and_passed": 10, "compiled_empty": 3, "injected": 7}`。
- repair/false_fix（均值）：A `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 7}` / B `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 7}`。
- LLM-suite detection 逐任务不一致：**9**（[{"task_id": "quixbugs__breadth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__breadth_first_search", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__depth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__detect_cycle_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__is_valid_parenthesization", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__hanoi", "A": 0.0, "B": 1.0, "note": "value differs"}, {"task_id": "quixbugs__kheapsort", "A": 0.0, "B": 1.0, "note": "value differs"}, {"task_id": "quixbugs__bitcount", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__find_first_in_sorted", "A": null, "B": null, "note": "one/both not measurable"}]）
- 字段完整率（需求键）：A `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}` / B `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}`。

## 7. 成本 / 墙钟

- 两臂合计成本（标准价上界）≈ **$0.278840**（预算 ≤$0.5）。
- 墙钟：A=2122s / B=2108s（max=2122s；≤110min）。

## 8. 局限（预注册披露）

- 单次运行、单模型/单数据集/单 seed、n=20 配对 → 低功效；后验 MDE 见 §4，不做事后改规则。
- oracle-correct 低基数（历史 correct 0 起步）：小 Δ 可能统计不可判；仅按冻结规则报告 confirmed/not_confirmed。
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。
- 若 unavailable/fp 占比高，correct 变化可能受 instrument 限制（需结合 §6 verdict 分布解读）。

## 9. 文件

| 文件 | 说明 |
|---|---|
| `PREREG_DECISION.md` | 跑前冻结的决策预注册（三 seed 规则/局限） |
| `PREFLIGHT.json` | 切点/干净度/env 开关/字段/契约检查/成本墙钟估算 |
| `benchmark_quixbugs_*.json` | 两臂批次工件 |
| `log_control.log` / `log_examples.log` | 两臂完整日志 |
| `traces_control/` / `traces_examples/` | 逐任务 trace |
| `arm_control.meta.json` / `arm_examples.meta.json` | 逐臂元数据 |
| `ANALYSIS_REPORT.json` | 机读聚合（判定/配对/分布） |
| `_helpers/` | 本批 runner 辅助 + finalize_s1.py（零 LLM 可复算三 seed 决策） |
| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |
