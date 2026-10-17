# Q-2：oracle 示例通道生产化验证——预注册二臂 A/B（真 LLM，QuixBugs 20 任务）

> **性质：预注册判定测量（单次运行、小样本）**。判定规则在 `PREREG.md` 跑前冻结；结果只按该规则报告 `confirmed` / `not_confirmed`，并披露 MDE/功效/局限；不做超出规则的 confirmatory 因果主张。

## 1. 协议与切点

- 切点：`a48a53ffe1844d098b5a84e59ab70fb6375e661c`（Q-1 q-examples；跑前/跑后 worktree dirty=0）
- 两臂并发、同秒启动、独立 namespace、`AITESTER_LLM_CACHE=0`；`AITESTER_PROFILE=logic`、TEMPERATURE=0.0、LLM_THINKING_MODE=disabled、`BENCHMARK_PARALLELISM=4`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、`AITESTER_BATCH_MAX_CALLS=200`、watchdog 3600s/臂。
- A（control）：`SPEC_ORACLE_EXEC_ENABLE=true` + `SPEC_ORACLE_EXAMPLES_ENABLE=false`；B（examples）：两者均 `true`；`--dataset quixbugs --task-limit 20 --seed 42 --baselines aitester`。
- 预注册：`PREREG.md`（sha256 `f30f8f61ca00c9ac4d7d08a285a4ee464383e3040e5a2d0a755af9b5bedeb2e8`）；预算 ≤$0.5，墙钟 ≤110.0min。

## 2. 预注册判定（冻结规则）

**主指标**：任务级 `oracle_suite_verdict == "correct"` 的任务数（配对共同任务）。

**成功判定（三条同时满足）**：①Δ=B_correct−A_correct ≥ **2** ∧ ②LLM-suite detection 非劣（B ≥ A − **5pp**） ∧ ③McNemar 单向 **p < 0.05**；否则 `not_confirmed`。

## 3. 两臂表（实测）

| 项 | A control | B examples |
|---|---|---|
| 批次 sha256 | `80f90e9b28ebb500…` | `20bf13fb28fb1756…` |
| 行数 / exit | 20 / 0 | 20 / 0 |
| 墙钟(s) | 2336 | 2084 |
| tokens / calls | 267640 / 94 | 276377 / 97 |
| 成本（标准价上界） | $0.137792 | $0.138086 |
| env_snapshot.SPEC_ORACLE_EXEC_ENABLE | `true` | `true` |
| env_snapshot.SPEC_ORACLE_EXAMPLES_ENABLE | `false` | `true` |
| `oracle_suite_verdict` 分布 | `{"unavailable": 17, "silent": 3}` | `{"correct": 6, "unavailable": 10, "silent": 4}` |
| `spec_oracle_examples_source` 分布 | `{"none": 20}` | `{"planner": 17, "none": 3}` |
| `spec_oracle_examples_count` 统计 | `{"n_rows_with_count": 20, "mean": 0.0, "max": 0, "total": 0}` | `{"n_rows_with_count": 20, "mean": 2.25, "max": 3, "total": 45}` |
| 注入率 | 16/20 | 17/20 |
| LLM-suite detection | 100.00%（15/15） | 80.00%（12/15） |

## 4. 主指标配对与判定

- 共同任务：**20**；A_correct=**0**，B_correct=**6**，Δ=**6**。
- discordant：b（B 新增 correct）=**6**，c（A 独有 correct）=**0**；McNemar 单向 p=**0.015625**。
- LLM-suite detection 非劣：A=1.0000 / B=0.8000（δ=-20.0pp，阈值 −5pp，非劣=False）。
- **判定：`not_confirmed`**（未满足：LLM-suite 非劣不成立（B 0.8 vs A 1.0, δ=-20.0pp < -5pp））。

**三条判据逐项（预注册冻结规则）**：

| 判据 | 结果 | 数值 |
|---|---|---|
| ① Δ=B_correct−A_correct ≥ 2 | **PASS** | Δ=6（A=0 / B=6） |
| ② LLM-suite detection 非劣（B ≥ A − 5pp） | **FAIL** | A=15/15=100.0% / B=12/15=80.0%，δ=**−20.0pp** |
| ③ McNemar 单向 p < 0.05 | **PASS** | b=6, c=0, p=**0.015625** |

> 结论：oracle-correct 新增 6 任务（b=6, c=0, p=0.0156，达到判据 ①③），但 **LLM-suite detection 下降 20pp（判据 ② 不成立）→ 按冻结规则 not_confirmed**。即：
> "示例通道显著提升 oracle-correct，但本批同时观测到 LLM-suite 检出损失（15→12 可判任务），非劣性未通过，不能宣称成功；需下一轮复核该检出损失（是真实 trade-off 还是单次运行/噪声）。"

- **MDE 披露**：单侧精确 McNemar α=0.05、c=0 时需 b≥5（b=4 时 p=0.0625，b=5 时 p=0.03125）；n=20 配对、单次运行 → 低功效；Δ≥2 为必要但不充分条件。

## 5. 逐任务配对（主指标 oracle-correct + 示例来源/计数 + LLM-suite detection）

| task_id | A verdict | B verdict | b | A ex_source/count | B ex_source/count | A det | B det |
|---|---|---|---|---|---|---|---|
| `quixbugs__breadth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__bucketsort` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__depth_first_search` | silent | silent |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__depth_first_search_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__breadth_first_search` | silent | unavailable |  | none/0 | planner/1 | 1.0000 | 1.0000 |
| `quixbugs__detect_cycle_test` | unavailable | unavailable |  | none/0 | none/0 | — | — |
| `quixbugs__detect_cycle` | unavailable | unavailable |  | none/0 | planner/1 | 1.0000 | 0.0000 |
| `quixbugs__find_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__flatten` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__gcd` | unavailable | unavailable |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__get_factors` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__hanoi` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 0.0000 |
| `quixbugs__kheapsort` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__is_valid_parenthesization` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__kth` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__knapsack` | unavailable | silent |  | none/0 | planner/3 | 1.0000 | 0.0000 |
| `quixbugs__lcs_length` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__levenshtein` | unavailable | correct | ★ | none/0 | planner/3 | 1.0000 | 1.0000 |
| `quixbugs__bitcount` | silent | unavailable |  | none/0 | planner/3 | — | — |
| `quixbugs__find_first_in_sorted` | unavailable | unavailable |  | none/0 | planner/3 | — | — |

## 6. 次指标

- 注入率：A 16/20；B 17/20。
- `spec_oracle_verdict` 分布：A `{"compiled_empty": 4, "injected_and_passed": 11, "injected": 5}` / B `{"injected_and_passed": 11, "compiled_empty": 3, "injected": 6}`。
- repair/false_fix（均值）：A `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 6}` / B `{"repair_rate_mean": 0.0, "false_fix_rate_mean": 0.0, "n": 5}`。
- LLM-suite detection 逐任务核对：A 可判 15 任务全部检出（15/15=100%），B 可判 15 任务检出 12（12/15=80%）。**真实不一致 3 个任务**：
  `quixbugs__detect_cycle`、`quixbugs__hanoi`、`quixbugs__knapsack`（均 A=1.0 → B=0.0）；其余 5 个"不可判"任务两臂相同（3 个 `*_test` 测试驱动任务 + `bitcount` + `find_first_in_sorted`，均 None）——不是不一致。
- 原始 mismatch 记录（含不可判项）：**8**（[{"task_id": "quixbugs__breadth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__depth_first_search_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__detect_cycle_test", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__detect_cycle", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__hanoi", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__knapsack", "A": 1.0, "B": 0.0, "note": "value differs"}, {"task_id": "quixbugs__bitcount", "A": null, "B": null, "note": "one/both not measurable"}, {"task_id": "quixbugs__find_first_in_sorted", "A": null, "B": null, "note": "one/both not measurable"}]）
- 字段完整率（需求键）：A `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}` / B `{"task_id": 20, "passed": 20, "coverage": 20, "iterations": 20, "stop_reason": 20, "spec_oracle_injected": 20, "spec_oracle_verdict": 20, "oracle_suite_verdict": 20, "llm_suite_detection_rate": 20, "detection_rate": 20, "repair_rate": 20, "false_fix_rate": 20, "spec_oracle_examples_source": 20, "spec_oracle_examples_count": 20}`。

## 7. 成本 / 墙钟

- 两臂合计成本（标准价上界）≈ **$0.275878**（预算 ≤$0.5）。
- 墙钟：A=2336s / B=2084s（max=2336s；≤110min）。

## 8. 局限（预注册披露）

- 单次运行、单模型/单数据集/单 seed、n=20 配对 → 低功效；后验 MDE 见 §4，不做事后改规则。
- oracle-correct 低基数（历史 correct 0 起步）：小 Δ 可能统计不可判；仅按冻结规则报告 confirmed/not_confirmed。
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受争抢影响）。
- 若 unavailable/fp 占比高，correct 变化可能受 instrument 限制（需结合 §6 verdict 分布解读）。
- **LLM-suite detection 下降（3 任务 A=1→B=0）仅单次运行观测**：不能区分"examples 导致的真实 trade-off"与"temp=0 重跑噪声"（历史同配置重跑曾出现 2/20 级差异；本批 3/15 超出该量级，值得下一轮复核）；这也是判据 ② 未通过的直接原因。

### 8.1 执行备注（透明披露）

- **首次执行 quick-fail（零 LLM、零成本）**：2026-10-18T04:18Z 两臂 exit=2、wall 0s；原因 = runner 在 `cd <ROOT>` 子 shell 后仍用**相对** `--out` 调用 `_helpers/limited_run.py`（解析到 worktree 下不存在的路径）。
  已修为 **ROOT/OUT 绝对路径规范化 + import-source 预检**（`experiments.__file__` 必须解析到 ROOT），`--preflight-only` 复验通过后重跑；原始证据归档 `_quickfail_zero_llm_20261018/`。不影响判定（无数据产生）。
- **事故披露（Q 轮流程事故，非 Q-2 数据）**：零 LLM 自测阶段曾意外启动真实 LLM 调用（另一目录，见 `_incident_unintended_llm_launch_20261018/`），Lead 已裁决计入 Q 轮预算（粗估 $0.15–0.20）；该目录**禁止**作为任何研究证据引用。本批 A/B 数据未受其影响（独立 worktree/命名空间/时间窗）。
- **Q 轮预算对账（估算）**：事故 ≈$0.15–0.20 + 本批实测 **$0.275878** + 探针/其它 ≈$0.05 ≈ **$0.48–0.53**（Q 轮上限 $0.7 ✓）。

## 9. 文件

| 文件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的预注册（判定规则/MDE/局限） |
| `PREFLIGHT.json` | 切点/干净度/env 开关/字段/契约检查/成本墙钟估算 |
| `benchmark_quixbugs_*.json` | 两臂批次工件 |
| `log_control.log` / `log_examples.log` | 两臂完整日志 |
| `traces_control/` / `traces_examples/` | 逐任务 trace |
| `arm_control.meta.json` / `arm_examples.meta.json` | 逐臂元数据 |
| `ANALYSIS_REPORT.json` | 机读聚合（判定/配对/分布） |
| `PREFLIGHT_DESIGN.md` / `DRY_RUN_EVIDENCE.json` | 零 LLM 预检设计 + dry-run 证据（准备阶段） |
| `_quickfail_zero_llm_20261018/` | 首次执行 quick-fail 原始证据（零 LLM、零成本；runner 路径 bug，已修） |
| `_incident_unintended_llm_launch_20261018/` | Q 轮流程事故证据（**非 Q-2 数据，禁止引用**；Lead 已裁决计入 Q 轮预算） |
| `proc_hygiene.log` | 跑批期孤儿 pytest 巡检记录（全 0 泄漏） |
| `SHA256SUMS` | checksum_results.py --write 生成（verify 通过） |
