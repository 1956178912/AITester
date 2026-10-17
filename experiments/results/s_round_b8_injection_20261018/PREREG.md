# S-2 / B8 / A-19 预注册：覆盖率停滞检测开/关消融 + 实验层确定性失败注入

> **状态：跑前冻结（2026-10-18，06:21+08:00；主批启动前落盘）**。
> 本文件 sha256 由驱动在跑批启动时读入并写入两臂 `arm_*.meta.json` 与
> `REPORT.json.prereg.sha256`（时间戳证据链）；跑批后不得修改本文件。
>
> 切点：干净 worktree `/Users/wangchenyu/Workspace/AITester-s2-b8-566f973`
> HEAD=`566f97339b0b9728f8a948afbf449a2eb87408c2`（detached，dirty=0，
> 复制 `.env.local`）；驱动 `experiments/run_b8_injection.py` 在主仓（untracked），
> 以 `--root` 指向该 worktree 运行。

## 1. 问题与背景

P-2（`experiments/results/p_round_b8_ablation_20261018/`）的 B8 消融中，synthetic+fast+seed=42
前 10 任务两臂均 10/10 首轮全绿（detection=0/10、false_fix=1.0），workflow 从未进入修复
循环 → A-19 停滞判据（最近 K=2 轮 failed 且 |coverage_delta|<eps）**结构上不可达**，
B8 无法回答"停滞检测能否提前停止"。

**本轮问题**：当任务确实多轮失败且覆盖率停滞时，P-2 已接线的 stagnation 检测
（`COVERAGE_STALL_DETECT_ENABLE=true`）是否真的提前停止、省多少迭代？

## 2. 设计：实验层确定性失败注入（不改生产逻辑）

- **注入机制（仅驱动进程内 monkeypatch）**：
  1. `src.graph.nodes._executor_node`（及 `src.graph.workflow` 模块级引用）→ 仅透传
     当前 `state` 到线程局部变量，原函数逻辑原样执行（不改变任何路由/节点语义）；
  2. `src.agents.executor.ExecutorAgent.execute` → 按 `state["iteration"]`：
     - `iteration < inject_rounds` 的轮次返回**确定性强制失败**：
       `passed=False`、`output="INJECTED_FAILURE…"`、`failed_cases=[{name,error}]`、
       `coverage = 上一轮 coverage`（首轮 0.0）→ `_record_execution_trace` 产生的
       `coverage_delta` 从第 2 轮起恒为 `0.0`（|Δ|<eps=0.5），使停滞窗口可触发；
     - `iteration >= inject_rounds` 的轮次**恢复真实执行**（调原方法）。
- **两臂注入完全相同**；唯一差异 = `COVERAGE_STALL_DETECT_ENABLE=true`(on) /
  `=false`(off)。其余 env 完全一致。
- **`inject_rounds=3` 的理由**：停滞窗口 K=2（默认 `COVERAGE_STALL_ROUNDS=2`）要求
  "最近 2 轮"均有 `coverage_delta`，而首轮 delta=None（无可比前值）不计数 → 需要
  ≥3 个强制失败轮，ON 臂在第 3 轮 executor 后（iteration=2）命中停滞。
- **`PATCH_EVIDENCE_GATE_ENABLE=false`（两臂同设）的理由（跑前冒烟实证）**：
  默认 fast 协议下证据门（`PATCH_EVIDENCE_GATE_ENABLE` 默认 true）会拒绝 synthetic
  任务（无 gold/sbfl 证据等级）的 LLM 补丁（`patch_applied=False`），两轮后
  `_should_debug` 的 **repair-invalid 分支在停滞窗口同一迭代收敛**，ON 臂
  仅经 `determine_stop_reason` 得到 `coverage_stall` 标签而无真正提前停止
  （冒烟 2 任务：on/off 均 iterations=2，Δ=0）。为测"停滞检测**可达**时是否
  真省迭代"，本批两臂同设 `PATCH_EVIDENCE_GATE_ENABLE=false`（解除前置抢占，
  不改变 A-19 判定逻辑；单变量仍只有 stall 开关）。**默认协议下的抢占现象与
  "标签语义≠提前停止"作为伴生发现如实报告，不混入主判定。**

## 3. 判定规则（跑前冻结）

设 `on` = `COVERAGE_STALL_DETECT_ENABLE=true` 臂，`off` = `false` 臂；任务级
`stop_reason` 取批次 JSON `details[].stop_reason`，`iterations` 取
`details[].iterations`；crash 定义 = `error_category ∈ {exception,
unexpected_exception, harness_error, crash, timeout, recursion_limit}` 的行数
（另加：臂进程异常退出/watchdog 视为该臂 crash）。

- **主判据（M1）**：`on` 臂 `coverage_stall` 触发率 ≥ **80%**（`stop_reason=="coverage_stall"`
  的任务数 / 可判定任务数）**且** `off` 臂触发率 = **0%**。
- **次判据（M2）**：`mean(iterations_on) < mean(iterations_off)` 且差值
  `mean(off) − mean(on) ≥ 1.0` 轮；**且**两臂 crash 数均 = 0。
- **判定**：
  - `confirmed` = M1 ∧ M2；
  - `not_confirmed` = 至少一条不满足（逐项报告实测值与未满足项）；
  - `not_confirmed_harness_limitation` = 注入未达覆盖要求（on 臂
    `tasks_with_injection < 80%` 任务 或 `injected_rounds==0`）→ 明确归因"harness
    无法稳定构造多轮失败"，不读作机制否定。
- **次级/描述性指标**（不参与判定）：`stop_reason` 分布、coverage 均值、tokens/成本、
  墙钟、逐任务配对 Δ、注入轮数与真实执行轮数、provenance（git_sha/dirty/env_snapshot）。

## 4. 协议（两臂并发、同批同日）

| 项 | 值 |
|---|---|
| 数据集 | `synthetic`，`--task-count 10 --seed 42`（与 P-2 同任务集） |
| 档位 | `AITESTER_PROFILE=fast`（与 P-2 同：隔离 workflow 停止路由单变量）；`TEMPERATURE=0.0`、`LLM_THINKING_MODE=disabled` |
| 并行 | `BENCHMARK_PARALLELISM=4`；两臂**并发**（两进程） |
| 真实 LLM | 是；`AITESTER_LLM_CACHE=0`；两臂独立 `AITESTER_CACHE_NAMESPACE=s2_b8_injection_on/off` |
| 止损 | `AITESTER_BATCH_MAX_CALLS=150/臂`、`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`、watchdog **1500s/臂** |
| 注入 | `--inject-rounds 3`（两臂相同） |
| 额外 env | `PATCH_EVIDENCE_GATE_ENABLE=false`（两臂相同；理由见 §2） |
| 预算 | **≤ $0.3**（估算：冒烟 2 任务 on≈14.4k tokens/off≈18k → 10 任务两臂 ≈180–220k tokens ≈ $0.10–0.15；价目 deepseek-flash 标准价 $0.3/$1.2 per Mtok） |
| 墙钟 | **≤ 45min**（冒烟 2 任务每臂 23–31s；10 任务并发预计 2–5min） |
| 失败处置 | 单臂失败/watchdog 触发 → 保留日志与部分工件、**不重跑**、如实报告 |

### 跑前冒烟（非主判定；harness 有效性证据，跑前完成）

| 冒烟 | 设置 | 结果 |
|---|---|---|
| A：默认协议（证据门 ON） | 2 任务 on/off | on：`coverage_stall`×2, iterations=2；off：`skip_debugger_repair_invalid`×2, iterations=2 → **Δ=0**（repair-invalid 同迭代抢占；ON 仅标签） |
| B：可达性（证据门 OFF） | 2 任务 on/off | **on：`coverage_stall`×2, iterations=2；off：`test_passed`×1 + `max_iterations`×1, iterations=3 → Δ=+1** |

冒烟工件：`_harness_smoke/`（默认协议）与 `_harness_smoke_gateoff/`（可达性）；
两者均在主 README 披露，不计入主判定。

## 5. 分析口径与产物

- 判定由驱动 `--aggregate-only` 零 LLM 复算：`REPORT.json`（两臂汇总/配对/逐项判据/
  成本/隔离）+ `README.md` + `ISOLATION.json`（生产文件零 diff 证据）+ `SHA256SUMS`。
- 隔离证明：worktree 跑前/跑后 `git status --porcelain` 与 `git diff --stat` 均为空；
  驱动运行时校验 `config/src/...` 模块 `__file__` 全部来自 worktree；注入仅在本进程内
  monkeypatch（`AITESTER_B8_INJECTION_ENABLE=1` 门控），生产文件零改动。
- 数字纪律：判定数字一律由 `REPORT.json`/批次 JSON 复算，不手写；偏差（若必须）在
  README 逐条披露并说明理由。

## 6. 范围与限制（预先披露）

- **注入失败 ≠ 自然失败**：结论只关于 A-19 停止逻辑在"多轮失败 + 覆盖率停滞"条件下
  的行为，**不外推**真实任务收益/代价；不代表 logic/scientific 档（fast 档单变量）。
- synthetic + fast + 单 seed（42）+ 单模型（deepseek-flash）；n=10 配对，探索性机制验证，
  不做 confirmatory/因果主张；无 MDE 功效主张（确定性注入，非抽样效应估计）。
- 两臂并发共享 CPU；LLM 侧仍有服务端非确定性（temp=0 非严格确定）。
- debugger/planner 仍真实 LLM 调用，其补丁行为可能引入额外停止分支；`stop_reason`
  分布如实报告，不事后筛选。
- `PATCH_EVIDENCE_GATE_ENABLE=false` 仅为本消融可达性设置；默认生产口径（gate=true）
  下停滞检测是否被 repair-invalid 抢占 → 伴生发现如实披露（见 §2/README）。
