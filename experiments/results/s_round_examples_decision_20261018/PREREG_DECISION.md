# S-1 预注册（FROZEN，跑前冻结）：seed-44 复现批 + 3-seed 生产化决策

> **状态：FROZEN（2026-10-18，跑前落盘；PREREG sha256 记入 PREFLIGHT.json）**。决策规则冻结后不改。
> **性质：决策支持（decision support），非能力主张（not a capability claim）**。生产开关 `SPEC_ORACLE_EXAMPLES_ENABLE` **默认关不变**；
> enabling 需要另行变更 + 回归，并引用本决策批。
> 本批 = 第 3 个 seed 的复现测量（seed44，协议与 Q-2/R-1 完全相同，只换 seed）；决策 = 三 seed 合并规则（只读合并既有工件 + 本批）。

## 0. 切点与运行环境

| 项 | 值 |
|---|---|
| 切点 commit | `566f97339b0b9728f8a948afbf449a2eb87408c2`（S 轮终稿；`git rev-parse HEAD` 校验） |
| 干净 worktree | `/Users/wangchenyu/Workspace/AITester-s1-decision-566f973`（detached HEAD=切点；跑前 `git status --porcelain`=0；`.env.local` 已复制） |
| 复核脚本 | `experiments/run_s1_decision.sh`（主仓；sha256=`6eb1cae5657c81e04b21d60a6c00a9a77162b53746fb7a66093a0c18719d0023`；由 R-1 runner 参数化：seed=44、out=s_round_examples_decision_20261018、预算 0.30、估算 in_share=0.76） |
| 模型/档位 | deepseek-flash；`AITESTER_PROFILE=logic`；`TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`；`BENCHMARK_PARALLELISM=4`；`AITESTER_LLM_CACHE=0` |
| 预算/墙钟 | **≤ $0.30**；墙钟 **≤ 70min**；watchdog **3600s/臂**；单臂失败/超时如实报告、不重跑 |
| 任务 | `--dataset quixbugs --task-limit 20 --seed 44 --baselines aitester`（预检估算 = $0.28896 / 48.3min → 保持 20 任务；若预检超限则降 15 并披露） |

## 1. 设计（两臂 A/B；与 Q-2/R-1 相同，仅 seed=44）

| 项 | A（control） | B（examples） |
|---|---|---|
| `SPEC_ORACLE_EXEC_ENABLE` | `true`（显式） | `true`（显式） |
| `SPEC_ORACLE_EXAMPLES_ENABLE` | **`false`**（显式） | **`true`**（显式） |
| 命令 | `python -m experiments.run_benchmark --dataset quixbugs --task-limit 20 --seed 44 --baselines aitester --output-dir <staging_A>` | 同左（staging_B） |
| 调度 | 两臂并发、同秒启动、独立 `AITESTER_CACHE_NAMESPACE`/`AITESTER_TRACE_DIR`（`s_round_examples_decision_20261018_control`/`_examples`） | 同左 |
| 公共 env | `AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=200` | 同左 |

## 2. 三 seed 合并表（主指标；seed42/43 只读既有工件，seed44 本批）

| seed | 来源 | A/B env | A_correct | B_correct | Δ=B−A | A_det | B_det | loss_pp=(A−B)×100 | b/c | McNemar 单侧 p | Q-2 规则判定（参考） |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 42 | Q-2 `q_round_examples_ab_20261018/` | false/true | 0 | 6 | **+6** | 15/15=100% | 12/15=80% | **20.0** | 6/0 | 0.015625 | not_confirmed |
| 43 | R-1 `r_round_examples_repro_20261018/` | false/true | 0 | 6 | **+6** | 13/15=86.7% | 13/15=86.7% | **0.0** | 6/0 | 0.015625 | confirmed |
| 44 | **本批（跑前冻结，待测）** | false/true | — | — | — | — | — | — | — | — | — |

- 口径：`A_det = A 检出可判任务数 / A 可判任务数`（行字段 `llm_suite_detection_rate`，缺失回退 `detection_rate`；非 None 计入）；
  `loss_pp = (A_det_rate − B_det_rate) × 100`（正=损失，负=B 更好）。
- 跑前已知：① Δ≥5 已在 seed42/43 两 seed 达成（2/3）；② loss ≤5pp 目前仅 seed43 达成（1/3）→ **seed44 的 `loss_pp ≤ 5` 是 enable 与否的关键**。

## 3. 决策规则（预注册，冻结）

- **`enable_candidate`** = ① oracle-correct 增益 **Δ = B_correct − A_correct ≥ 5 任务** in **≥2/3 seeds**
  **∧** ② LLM-suite 损失 **loss_pp ≤ 5pp**（即 A−B ≤5pp，允许 B 更好）in **≥2/3 seeds**。
- 否则 → **`keep_off`**。
- **声明**：本决策是**决策支持**（是否值得进入下一阶段/是否开 candidate），**不是能力主张**；不做事后改规则；
  生产开关默认关不变；enabling = 另行变更 + 回归 + 本决策批引用。
- 逐 seed 同时报告（不参与决策规则）：Q-2 冻结规则口径（Δ≥2 ∧ 非劣 ∧ McNemar p<0.05）的判定、McNemar b/c/p、
  `oracle_suite_verdict` 五类分布、`spec_oracle_examples_source/count` 分布、注入率、成本/墙钟/异常。

## 4. 预检门禁（真实跑批前；零 LLM）

- 真实模式强制：ROOT dirty=0、PREREG 已冻结且含切点 sha、两臂 env 实测可区分（A: exec=true/examples=false；B: true/true）；
- 切点特征标记 + Q-1 契约测试（零 LLM）+ import-source 解析到 ROOT + TOCTOU 源码 sha256；
- 成本/墙钟估算（tokens/task=14000、in_share=0.76、deepseek-flash 价目）→ 超 $0.30 或 >70min 则降 15 任务并写 `PREREG_DOWNGRADE.md`；
- 预注册 sha256 记入 `PREFLIGHT.json`；零 LLM 自测只用 `--preflight-only` 或临时副本。

## 5. 局限

- 单次运行/seed、n=20；seed44 的 quixbugs 任务子集/顺序可能与前两 seed 不同 → 属"臂级方向/量级"复现，不是逐任务复现（如实披露任务集合）；
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受影响）；
- detection 口径=LLM-suite（N-3 起）；决策仅基于预注册两条判据，不外推其他数据集/档位；
- 单臂失败/超时 → 判定按规则如实报告（可能 `keep_off`，因数据不完整），不重跑。

## 6. 产物

`experiments/results/s_round_examples_decision_20261018/`：`PREREG_DECISION.md`（本件）/ `PREFLIGHT.json` / `README.md` /
`ANALYSIS_REPORT.json`（含本批 + 三 seed 决策）/ 本批两臂 `benchmark_quixbugs_*.json` / logs / traces / meta /
`SHA256SUMS`（`checksum_results.py --write` 且 `--verify` 通过）；`experiments/run_s1_decision.sh`（主仓，未 commit）。
不 commit、不跑全量、不重跑失败臂；worktree 保留待 Lead 清理。
