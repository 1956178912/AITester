# R-1 预注册（FROZEN，跑前冻结）：Q-2 检出损失复现批（seed=43，二臂 A/B）

> **状态：FROZEN（2026-10-18，跑前落盘；PREREG sha256 记入 PREFLIGHT.json）**。判定规则冻结后不改。
> 性质：**复现性判定测量**（单次运行、二臂同批）；回答"Q-2 的 LLM-suite 检出损失是真实 trade-off 还是单次运行噪声"。

## 0. 切点与运行环境

| 项 | 值 |
|---|---|
| 切点 commit | `282b361fcba1bfc0f55566883eb44969795cb572`（R 轮终稿；`git rev-parse HEAD` 校验） |
| 干净 worktree | `/Users/wangchenyu/Workspace/AITester-r1-repro-282b361`（detached HEAD=切点；跑前 `git status --porcelain`=0；`.env.local` 已复制） |
| 复核脚本 | `experiments/run_r1_repro.sh`（主仓；sha256=`bda5faf1a7d2f6911a184951ad916845015f5c11dbc9a541886c88e19fbd78eb`；由 Q-2 runner 参数化：seed=43、out=r_round_examples_repro_20261018、预算/墙钟/估算常量针对本批） |
| 模型/档位 | deepseek-flash；`AITESTER_PROFILE=logic`；`TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`；`BENCHMARK_PARALLELISM=4`；`AITESTER_LLM_CACHE=0` |
| 预算/墙钟 | **≤ $0.35**；墙钟 **≤ 70min**；watchdog **3600s/臂**；单臂失败/超时如实报告、不重跑 |
| 任务 | `--dataset quixbugs --task-limit 20 --seed 43 --baselines aitester`（预检估算 = $0.30912 / 48.3min → 保持 20 任务；若实际预检超限则降 15 并披露） |

## 1. 设计（两臂 A/B；与 Q-2 同 env，仅 examples 开关不同）

| 项 | A（control） | B（examples） |
|---|---|---|
| `SPEC_ORACLE_EXEC_ENABLE` | `true`（显式） | `true`（显式） |
| `SPEC_ORACLE_EXAMPLES_ENABLE` | **`false`**（显式） | **`true`**（显式） |
| 命令 | `python -m experiments.run_benchmark --dataset quixbugs --task-limit 20 --seed 43 --baselines aitester --output-dir <staging_A>` | 同左（staging_B） |
| 调度 | 两臂并发、同秒启动、独立 `AITESTER_CACHE_NAMESPACE`/`AITESTER_TRACE_DIR`（`r_round_examples_repro_20261018_control` / `_examples`） | 同左 |
| 公共 env | `AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=200` | 同左 |

## 2. 复现判定（冻结规则）

- 可判定 detection：行字段 `llm_suite_detection_rate`（缺失回退 `detection_rate`；非 None 才计入）；
  `A_det = 检出可判任务数 / A 可判任务数`；`B_det` 同口径。
- **direction_consistent = (B_det < A_det) 且 损失_pp = (A_det − B_det)×100 ≥ 10**。
- 若 **direction_consistent** → 判定 **`reproducible_tradeoff`**：LLM-suite 检出损失可复现；生产开关保持关，登记为真实风险（写清 magnitude/seed/任务）。
- 否则 → 判定 **`not_reproduced`**：本轮未复现 Q-2 的检出损失，视为单次运行噪声；**仍不自动生产化**，登记下一轮 3 臂复核（A/B/关 examples + 更多 seed）。
- **同时报告**（不参与判定）：oracle-correct 任务数 Δ（B−A）、配对 McNemar 单侧 p（b/c/b_only）、examples source/count 分布、注入率、oracle_suite_verdict 五类分布、成本/墙钟、异常。
- 若某臂失败/超时/数据缺失 → 判定为 `not_reproduced`（无法复现证据）并如实报告，不重跑。

## 3. 诊断上下文（跑前已知，零 LLM 诊断）

- Q-2 结果（seed42，20 任务）：oracle-correct +6（McNemar p=0.0156），LLM-suite detection A 15/15=100% vs B 12/15=80%（3 任务损失：detect_cycle/hanoi/knapsack）→ not_confirmed（判据②非劣失败）。
- 零 LLM 诊断（`DIAGNOSIS.md`）：两臂 20/20 任务 generated_test 均不同（Jaccard 均值 0.197）；3 个损失任务的生成差异与普通任务同级；`hanoi` A=1 轮 test_passed vs B=3 轮 max_iterations（B oracle 也变 correct）提示契约段可能改变修复/生成轨迹；候选机制排序：(a) 契约段改变 Planner→生成/修复行为 > (b) 随机性 > (c) oracle-suite 直接影响（口径上排除）。
- 本批评测 seed=43 的方向一致性，用于区分 (a) 系统 trade-off 与 (b) 单次噪声。

## 4. 预检门禁（真实跑批前；零 LLM）

- 真实模式强制：ROOT dirty=0、PREREG 已冻结且含切点 sha、两臂 env 实测可区分（A: exec=true/examples=false；B: true/true）；
- Q-1 接线标记（env snapshot、行字段、planner 契约）+ Q-1 契约测试（零 LLM）+ import-source 解析到 ROOT + TOCTOU 源码 sha256；
- 成本/墙钟估算（tokens/task=14000、in_share=0.72、deepseek-flash 价目）→ 超 $0.35 或 >70min 则降 15 任务并写 `PREREG_DOWNGRADE.md`；
- 预注册 sha256 记入 `PREFLIGHT.json`。零 LLM 自测只用 `--preflight-only` 或临时副本（事故后纪律）。

## 5. 局限

- 单次运行、n=20、seed=43（quixbugs 任务子集可能与 seed42 不同 → 属"臂级方向复现"而非逐任务复现；如实披露）；
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受影响）；
- detection 口径为 LLM-suite（N-3 起）；oracle-correct 使用冻结判定规则，不做事后改规则；
- 预算/墙钟上限见 §0；单臂失败不重跑。

## 6. 产物

`experiments/results/r_round_examples_repro_20261018/`：`PREREG_REPRO.md`（本件）/`DIAGNOSIS.md`/`DIAGNOSIS_EVIDENCE.json`/
`PREFLIGHT.json`/`README.md`/`ANALYSIS_REPORT.json`/两臂 `benchmark_quixbugs_*.json`/logs/traces/meta/`SHA256SUMS`（verify 通过）；
`experiments/run_r1_repro.sh`（主仓，未 commit）。不 commit、不跑全量、不重跑失败臂；worktree 保留待 Lead 清理。
