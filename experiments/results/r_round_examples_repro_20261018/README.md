# R-1：Q-2 检出损失诊断 + seed-43 复现批（预注册二臂 A/B，真 LLM，QuixBugs 20 任务）

> **性质：预注册复现判定测量（单次运行、小样本）**。判定规则在 `PREREG_REPRO.md` 跑前冻结；结果只按该规则报告 **`reproducible_tradeoff` / `not_reproduced`**，并披露 MDE/功效/局限；不做超出规则的 confirmatory 因果主张。

## 0. R-1 摘要：诊断 + seed-43 复现判定

> 本批回答 Q-2 判定 `not_confirmed` 的直接原因——LLM-suite detection A 15/15=100% vs B 12/15=80%（3 任务）——是**真实 trade-off** 还是**单次运行噪声**。
> 判定规则跑前冻结于 `PREREG_REPRO.md`（seed=43、20 任务、A/B env 同 Q-2、预算 ≤$0.35/墙钟 ≤70min/watchdog 3600s）。

### A. 零 LLM 诊断（完整见 `DIAGNOSIS.md`）
- 两臂 **20/20** 任务 generated_test 均不同（test-name Jaccard 均值 0.197）；3 个损失任务的生成差异与普通任务同级（Jaccard 0.189，gt_len 相对差 0.445）——单次运行无法与一般随机性分离。
- `hanoi` 轨迹差异最强：A=1 轮 test_passed（detection=1）vs B=3 轮 max_iterations（detection=0，B oracle 也变 correct）→ 契约段可能改变 Planner→生成/修复行为；`detect_cycle`（B 测试 15 vs A 9）与 `knapsack`（A 24 vs B 10）均属生成内容差异。
- 候选机制排序：(a) 契约段改变下游生成/修复行为（正证据：oracle-correct 0→6、examples 17/20 来自 planner；但无法与随机性分离） > (b) 随机性（全量生成差异同级） > (c) oracle-suite 直接影响（N-3 口径上排除）。

### B. seed-43 复现判定（冻结规则）

| 项 | 值 |
|---|---|
| A_detection | 13/15 = 0.8666666666666667 |
| B_detection | 13/15 = 0.8666666666666667 |
| 损失 (pp) = (A−B)×100 | **0.0**（阈值 ≥10pp） |
| direction_consistent | **False** |
| **复现判定** | **`not_reproduced`** |
| oracle-correct（参考） | A=0 / B=6（Δ=6；b=6, c=0, McNemar p=0.015625） |

- **解释**：若 `reproducible_tradeoff` → 检出损失在独立 seed 下方向一致（≥10pp），登记为真实风险、生产开关保持关；
  若 `not_reproduced` → 本轮未复现，视为单次运行噪声，**仍不自动生产化**，登记下一轮 3 臂复核。
- Q-2 冻结规则（non-inferiority/McNemar）的参考判定：`confirmed`（仅参考，不用于 R-1 判定）。

## 1. 协议与切点

- 切点：`282b361fcba1bfc0f55566883eb44969795cb572`（Q-1 q-examples；跑前/跑后 worktree dirty=0）
- 两臂并发、同秒启动、独立 namespace、`AITESTER_LLM_CACHE=0`；`AITESTER_PROFILE=logic`、TEMPERATURE=0.0、LLM_THINKING_MODE=disabled、`BENCHMARK_PARALLELISM=4`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、`AITESTER_BATCH_MAX_CALLS=200`、watchdog 3600s/臂。
- A（control）：`SPEC_ORACLE_EXEC_ENABLE=true` + `SPEC_ORACLE_EXAMPLES_ENABLE=false`；B（examples）：两者均 `true`；`--dataset quixbugs --task-limit 20 --seed 43 --baselines aitester`。
- 预注册：`PREREG_REPRO.md`（sha256 `242e08da847b8708ee6e6033b9ca21c8347fea7e459bd1fff42be151829588ea`）；预算 ≤$0.35，墙钟 ≤70.0min。

## 2. 预注册判定（冻结规则，R-1）

**可判定 detection 口径**：行字段 `llm_suite_detection_rate`（缺失回退 `detection_rate`；非 None 才计入）；
`A_det = A 检出可判任务数 / A 可判任务数`，`B_det` 同口径（本批 A=B=13/15）。

**复现判定规则（跑前冻结）**：
- **`direction_consistent` = (B_det < A_det) 且 损失_pp = (A_det − B_det)×100 ≥ 10**；
- 若 `direction_consistent` → **`reproducible_tradeoff`**（检出损失可复现 → 生产开关保持关、登记真实风险）；
- 否则 → **`not_reproduced`**（本轮未复现 → 视为单次运行噪声；仍不自动生产化，登记下一轮 3 臂复核）。

**同时报告（不参与判定）**：oracle-correct 任务数 Δ（B−A）与配对 McNemar 单侧 p、examples source/count 分布、注入率、
`oracle_suite_verdict` 五类分布、成本/墙钟、异常。

## 3. 两臂表（实测）

| 项 | A control | B examples |
|---|---|---|
| 批次 sha256 | `d57a947bdcbc51dd…` | `b730e602b4a2057e…` |
| 行数 / exit | 20 / 0 | 20 / 0 |
| 墙钟(s) | 2214 | 2209 |
| tokens / calls | 274186 / 97 | 291428 / 102 |
| 成本（标准价上界） | $0.140701 | $0.145256 |
| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `true` | `true` |
| env_snapshot.SPEC_ORACLE_EXAMPLES_ENABLE | `false` | `true` |
| `oracle_suite_verdict` 分布 | `{"unavailable": 18, "silent": 2}` | `{"correct": 6, "unavailable": 11, "silent": 3}` |
| `spec_oracle_examples_source` 分布 | `{"none": 20}` | `{"planner": 17, "none": 3}` |
| `spec_oracle_examples_count` 统计 | `{"n_rows_with_count": 20, "mean": 0.0, "max": 0, "total": 0}` | `{"n_rows_with_count": 20, "mean": 2.25, "max": 3, "total": 45}` |
| 注入率 | 16/20 | 17/20 |
| LLM-suite detection | 86.67%（13/15） | 86.67%（13/15） |

## 4. 主指标配对与判定（R-1：复现规则 + 参考指标）

**R-1 冻结复现判定**（`PREREG_REPRO.md`）：
- A_detection = **13/15 = 0.8666666666666667**；B_detection = **13/15 = 0.8666666666666667**；损失 = **0.0pp**（阈值 ≥10pp）；
- `direction_consistent` = **False** → **`not_reproduced`**。

**参考（Q-2 冻结规则口径，不用于 R-1 判定）**：共同任务 **20**；A_correct=**0**，
B_correct=**6**（Δ=**6**；b=**6**，c=**0**，
McNemar 单向 p=**0.015625**）；Q-2 规则 verdict=`confirmed`。

- **MDE 披露（oracle-correct）**：n=20、单次运行；c=0 时需 b≥5 才 p<0.05（b=4 时 p=0.0625，b=5 时 p=0.03125）。
- **复现批的 seed 差异**：seed=43 的 quixbugs 任务子集/顺序可能与 seed=42 不同 → 本批评测"臂级方向复现"，非逐任务复现；任务集合以本批批次 JSON 为准。

## 5. 逐任务配对（主指标 oracle-correct + 示例来源/计数 + LLM-suite detection）

| task_id | A verdict | B verdict | b | A ex_source/count | B ex_source/count | A det | B det |
|---|---|---|---|---|---|---|---|
| `quixbugs__breadth_first_search` | unavailable | unavailable |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__breadth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__bucketsort` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__depth_first_search` | silent | unavailable |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__depth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__detect_cycle` | unavailable | unavailable |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__detect_cycle_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__flatten` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__find_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 0.0000 |
| `quixbugs__gcd` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__get_factors` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__is_valid_parenthesization` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 0.0000 |
| `quixbugs__hanoi` | unavailable | correct | ★ | none/0 | planner/3 | 0.0000 | 1.0000 |
| `quixbugs__kheapsort` | unavailable | correct | ★ | none/0 | planner/3 | 0.0000 | 1.0000 |
| `quixbugs__knapsack` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__lcs_length` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__kth` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__levenshtein` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__bitcount` | silent | unavailable |  | none/0 | planner/3 | — | — |
| `quixbugs__find_first_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | — | — |

## 6. 次指标

- 注入率：A 16/20；B 17/20。
- `spec_oracle_verdict` 分布：A `{"compiled_empty": 4, "injected_and_passed": 9, "injected": 7}` / B `{"injected_and_passed": 9, "compiled_empty": 3, "injected": 8}`。
- repair/false_fix（均值）：A `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 7}` / B `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 7}`。
- LLM-suite detection 逐任务不一致：**9**（[{"task_id": "quixbugs__breadth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__depth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__detect_cycle_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__find_in_sorted", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__is_valid_parenthesization", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__hanoi", "A": 0.0, "B": 1.0, "note": "value differs"}, {"task_id": "quixbugs__kheapsort", "A": 0.0, "B": 1.0, "note": "value differs"}, {"task_id": "quixbugs__bitcount", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__find_first_in_sorted", "A": null, "B": null, "note": "one/both not measurable"}]）
- 字段完整率（需求键）：A `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}` / B `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}`。

## 7. 成本 / 墙钟

- 两臂合计成本（标准价上界）≈ **$0.285957**（预算 ≤$0.5）。
- 墙钟：A=2214s / B=2209s（max=2214s；≤110min）。

## 8. 局限（预注册披露）

- 单次运行、单模型/单数据集/单 seed、n=20 配对 → 低功效；后验 MDE 见 §4，不做事后改规则。
- oracle-correct 低基数（历史 correct 0 起步）：小 Δ 可能统计不可判；仅按冻结规则报告 confirmed/not_confirmed。
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。
- R-1 为单次 seed-43 复现批：只判定方向一致性（≥10pp），不做事后改规则/不做 confirmatory 主张。
- 若 unavailable/fp 占比高，correct 变化可能受 instrument 限制（需结合 §6 verdict 分布解读）。

## 9. 文件

| 文件 | 说明 |
|---|---|
| `PREREG_REPRO.md` | 跑前冻结的复现预注册（seed=43/判定规则/局限） |
| `PREFLIGHT.json` | 切点/干净度/env 开关/字段/契约检查/成本墙钟估算 |
| `benchmark_quixbugs_*.json` | 两臂批次工件 |
| `log_control.log` / `log_examples.log` | 两臂完整日志 |
| `traces_control/` / `traces_examples/` | 逐任务 trace |
| `arm_control.meta.json` / `arm_examples.meta.json` | 逐臂元数据 |
| `ANALYSIS_REPORT.json` | 机读聚合（判定/配对/分布） |
| `DIAGNOSIS.md` / `DIAGNOSIS_EVIDENCE.json` | 零 LLM 诊断报告 + 机读证据（逐任务表/mismatch 时间线/机制判断） |
| `_helpers/` | 诊断/复现判定脚本（零 LLM，可复算） |
| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |
