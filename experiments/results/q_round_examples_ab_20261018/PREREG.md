# Q-2 预注册（草案，跑前冻结）：oracle 示例通道生产化验证——二臂同批 A/B

> **状态：FROZEN（2026-10-18 跑前冻结；PREREG sha256 已记入 PREFLIGHT.json）**。切点/命令/成本估算已补齐，
> 判定规则不再改动。
> **性质：预注册判定测量（单次运行，小样本）**。判定规则在跑前冻结；结果只按本规则报告
> confirmed / not_confirmed，并把 MDE、小样本、单次运行、探索性局限一并披露；不做超出该规则
> 的 confirmatory 因果主张。
> 任务：task-23 / 依赖 task-22（Q-1：示例通道生产接线）。

## 0. 切点与运行环境（FROZEN）

| 项 | 值 |
|---|---|
| 切点 commit | `a48a53ffe1844d098b5a84e59ab70fb6375e661c`（Q-1 `q-examples`；跑前 `git rev-parse HEAD` 校验） |
| 干净 worktree | `/Users/wangchenyu/Workspace/AITester-q2-examples-a48a53f`（detached HEAD=切点；跑前 `git status --porcelain`=0；`.env.local` 已复制） |
| 模型 | deepseek-flash；`TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`；`AITESTER_LLM_CACHE=0`（真实调用） |
| 档位/并发 | `AITESTER_PROFILE=logic`；`BENCHMARK_PARALLELISM=4`；两臂**同秒启动**、独立 `AITESTER_CACHE_NAMESPACE`/log/trace |
| 预算/墙钟 | **≤ $0.5**；墙钟 **≤ 110min**（含两并发臂）；watchdog **3600s/臂**；单臂失败/超时如实报告、不重跑 |
| 任务 | `--dataset quixbugs --task-limit 20 --seed 42 --baselines aitester`（如预检估算 >$0.5 或预计 >110min → 降 **15 任务/臂**并披露；本批预检估算 $0.35328/48.3min → 保持 20） |
| 复核脚本 | `experiments/run_q_examples_ab.sh`（主仓，未 commit；sha256=`6214bd9aace1dc75f71d108a223a2e50b51c4c1a2664dbab5a80dcd2712c99c6`） |
| 说明 | cut worktree **不含** Q-3 的 `run_benchmark` 后处理 hook（终稿集成内容），不影响 Q-2；Q-1 的 `SPEC_ORACLE_EXAMPLES_ENABLE` 与行字段已在 cut 中。 |

## 1. 设计（两臂 A/B；同一 baseline，仅示例开关不同）

| 项 | A（control） | B（treatment） |
|---|---|---|
| `SPEC_ORACLE_EXEC_ENABLE` | `true`（显式） | `true`（显式） |
| `SPEC_ORACLE_EXAMPLES_ENABLE` | **`false`**（显式） | **`true`**（显式） |
| 其余协议 | 相同（同 cut/同命令/同 seed/同判分口径） | 相同 |
| 命令 | `python -m experiments.run_benchmark --dataset quixbugs --task-limit 20 --seed 42 --baselines aitester --output-dir <staging_A>` | 同左（`<staging_B>`） |
| 说明 | logic 档 `AITESTER_PROFILE=logic` 会 setdefault `SPEC_ORACLE_EXEC_ENABLE=true`，故**两臂都显式设**，避免隐式默认；两臂 `SPEC_ORACLE_EXAMPLES_ENABLE` 显式 false/true 构成唯一处理变量。 |
| 公共 env | `AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4 AITESTER_LLM_CACHE=0 COST_BUDGET_ENABLE=true COST_BUDGET_USD=1 AITESTER_BATCH_MAX_CALLS=200`；独立 `AITESTER_CACHE_NAMESPACE`/`AITESTER_TRACE_DIR` | 同左 |

- Q-1 生产接线：`SPEC_ORACLE_EXAMPLES_ENABLE=true` 且 `SPEC_ORACLE_EXEC_ENABLE=true` 时，Planner spec 契约段请求
  `logic_analysis.examples`（≤3 条），经 `parse_logic_analysis → compile_spec_oracle` 生成逐示例 oracle 断言，
  由 N-3 独立判读在行字段 `oracle_suite_verdict` 中给出 correct/fp/silent/misguided/unavailable；行字段
  `spec_oracle_examples_source`（planner/spec_generator/none）与 `spec_oracle_examples_count` 提供来源/计数审计。
- 预期（Q-1 传播链有效时）：B 臂 oracle 示例增多 → `oracle_suite_verdict=="correct"` 的任务数相对 A 上升；
  LLM-suite detection 不应受损（N-3 独立判读口径，oracle 测试被排除在主判定之外）。

## 2. 主指标与预注册判定（冻结）

**主指标**：任务级 **oracle-correct 检出数**——行字段 `oracle_suite_verdict == "correct"` 的任务数
（配对共同任务；两臂任务集合应一致）。记：
- `A_correct` = A 臂 correct 任务数；`B_correct` = B 臂 correct 任务数；
- 配对差异 `Δ = B_correct − A_correct`（等价于 net discordant = b − c，见下）；
- 不一致对：`b = |correct_B \ correct_A|`（B 新增）、`c = |correct_A \ correct_B|`（A 独有）。

**成功判定（三条同时满足，否则 not_confirmed）**：
1. **Δ = B_correct − A_correct ≥ 2**（B 相对 A 至少多 2 个 correct 任务）；
2. **LLM-suite detection 非劣**：B 的 LLM-suite detection ≥ A 的 LLM-suite detection − **5pp**
   （口径：行字段 `llm_suite_detection_rate`/`detection_rate`，N-3 后语义=LLM-suite；按两臂可判定任务聚合率计算，分母并列报）；
3. **配对 McNemar（oracle-correct 新增）单向 p < 0.05**：对 b/c 做精确单项二项检验
   `p = P(X ≥ b | n=b+c, p=0.5)`（`b > c` 时；否则 p=1），报告 b、c、p。
- 其余情况（含 Δ≥2 但 McNemar 不显著、非劣不成立、数据缺失/不可判定）一律 **not_confirmed**，并给原因。
- **MDE 披露（小样本）**：n=20 配对下，单侧精确 McNemar α=0.05 在 c=0 时需 b≥5（p=0.5^5=0.03125<0.05）；
  c=0、b=4 时 p=0.0625>0.05。即本设计对"Δ=2~4 且无 A 独有"的效应**统计上不可判**（Δ≥2 是必要但不充分条件）；
  单次运行、二值小样本、oracle-correct 低基数（历史 correct 0 起步）→ 低功效，只按冻结规则报告，不做事后改规则。

## 3. 次要指标（描述性，不参与判定）

- `spec_oracle_examples_source` 分布（planner/spec_generator/none）、`spec_oracle_examples_count` 分布（均值/中位/总数）；
- `spec_oracle_injected` 注入率、`spec_oracle_verdict` 分布；
- `oracle_suite_verdict` 五类分布（correct/fp/silent/misguided/unavailable，两臂对照）；
- LLM-suite detection（两臂；配对逐任务一致性：一致/不一致清单）；
- `detection_rate` / `repair_rate` / `false_fix_rate`（行级，两臂）；
- tokens / 成本（deepseek-flash 价目表）/ 墙钟（每臂 watchdog 实测）；
- 异常与字段完整性：8+ 审计键逐行在场率；错误/超时/缺失任务单列。

## 4. 判定纪律与风险

> 预算上下文：Q 轮 LLM 预算上限 $0.7（Lead 批）：Q-2 预检估算 $0.35328 + Q 轮已知事故粗估 $0.15–0.20 + 探针/其它 ≈$0.05 ≈ $0.6；本批按 ≤$0.5 硬门禁执行。

- **单次运行、n=20（或降级 15）、单模型/单数据集/单 seed**：不做跨批/confirmatory 外推；
- 判定只在**本 PREREG 冻结规则**下执行；事后不增删规则、不改分母；
- 若 B 臂 correct 上升但 McNemar 不显著 → not_confirmed（不得写成 "trend/positive" 结论）；
- 若两臂 `oracle_suite_verdict` 均无 correct 或 correct 计数受 instrument 异常影响（unavailable 高），
  如实报告为 not_confirmed + 原因（instrument/覆盖限制）；
- 若某臂失败/超时：保留日志与部分工件，如实报告，**不重跑**；
- 预检若发现 Q-1 开关/字段/契约缺失或两臂 env 无法区分：**中止跑批**并报告（不硬跑）；
- 预算/墙钟上限：$0.5 / 110min；预检估算超限 → 降 15 任务并披露（PREREG_DOWNGRADE.md）。

## 5. 产物

`experiments/results/q_round_examples_ab_20261018/`：`PREREG.md`（本件）/ `PREFLIGHT.json` / `README.md` /
`ANALYSIS_REPORT.json` / 两臂 `benchmark_quixbugs_*.json` / `log_control.log` / `log_examples.log` /
`traces_control/` / `traces_examples/` / `arm_*.meta.json` / `SHA256SUMS`（checksum verify 通过）；
复核脚本 `experiments/run_q_examples_ab.sh`。不 commit、不跑全量、不重跑失败臂。

## 4.1 零 LLM 预检（真实跑批前阻断条件；runner 内实现，事故后加固）

真实跑批前，`run_q_examples_ab.sh` 的 [1/8] 预检（零 LLM）执行并落盘 `PREFLIGHT.json`；以下任一不满足 → **中止、不跑批**：
1. **切点/干净度/预注册冻结（强制）**：ROOT HEAD == `--expect-sha`；**ROOT dirty=0**（真实模式强制，事故加固）；
   `PREREG.md` 必须已冻结（不含 `DRAFT`/`<Q-1 …>` 占位符）且包含切点 sha；`.env.local` 在场；
2. **Q-1 生产接线在场**（静态）：`experiments/run_benchmark.py` 含 `SPEC_ORACLE_EXAMPLES_ENABLE`（env snapshot 登记）与行字段
   `spec_oracle_examples_source` / `spec_oracle_examples_count`；`src/agents/planner.py` 含契约标记；
   `tests/test_oracle_examples_production.py` 存在并通过（零 LLM 契约测试）；
3. **两臂 env 有效值可区分**（子进程实测）：A = `SPEC_ORACLE_EXEC_ENABLE=true`/`SPEC_ORACLE_EXAMPLES_ENABLE=false`，
   B = `true`/`true`；
4. **预算/墙钟门禁**：按保守常量（tokens/task=16000、in_share=0.72，历史 aitester/logic QuixBugs 批次；deepseek-flash 价目）
   估算；> $0.5 或 >110min → 自动降 **15 任务/臂**并写 `PREREG_DOWNGRADE.md`；
5. **TOCTOU 守卫（事故加固）**：记录 `run_benchmark.py`/`planner.py` sha256，launch 前复核；preflight→launch 之间源码变化 → 中止。

零 LLM 自测模式：`--dry-run`（机制自检、允许 dirty/feature 缺失）与 `--preflight-only`（与真实跑批相同门禁语义、**绝不 launch**）。
自测必须在**独立临时仓库副本**进行，不得对活的主树用真实模式（见 `_incident_unintended_llm_launch_20261018/README_INCIDENT.md`）。
